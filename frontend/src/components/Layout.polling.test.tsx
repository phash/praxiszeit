import { act, render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import Layout from './Layout';
import { useAuthStore } from '../stores/authStore';
import { resetBackupStatusCache } from '../utils/backupStatus';

// Log-Audit 2026-11-15 (Punkt 17, NET-3): ~1400 Polls mit 401 nach Ablauf der
// Sitzung. Nach 401/403 pausiert das Polling bis auth:refreshed oder Seitenwechsel.
const h = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../api/client', () => ({
  default: { get: h.get, post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

let authFails = true;
const pendingCalls = () => h.get.mock.calls.filter(([u]) => String(u).includes('pending-count')).length;
const clockCalls = () => h.get.mock.calls.filter(([u]) => String(u).includes('clock-status')).length;

beforeEach(() => {
  vi.useFakeTimers();
  authFails = true;
  resetBackupStatusCache();
  h.get.mockReset().mockImplementation((url: string) => {
    if (authFails && (url.includes('pending-count') || url.includes('clock-status'))) {
      return Promise.reject({ response: { status: 401 } });
    }
    if (url.includes('pending-count')) return Promise.resolve({ data: { count: 0 } });
    if (url.includes('clock-status')) return Promise.resolve({ data: { is_clocked_in: false } });
    return Promise.resolve({ data: {} });
  });
  useAuthStore.setState({
    user: { role: 'admin', first_name: 'A', last_name: 'B', username: 'ab', track_hours: true } as never,
  });
});

afterEach(() => {
  vi.useRealTimers();
});

function mount() {
  return render(
    <MemoryRouter initialEntries={['/admin']}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="admin" element={<div />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('Layout-Polling nach Auth-Fehler', () => {
  it('pausiert nach 401 und läuft nach auth:refreshed weiter', async () => {
    mount();
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    // Erster Versuch: CR-Zähler 401 → VR-Zähler wird gar nicht mehr gefragt.
    expect(pendingCalls()).toBe(1);
    expect(clockCalls()).toBe(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(3 * 60_000); });
    expect(pendingCalls()).toBe(1);
    expect(clockCalls()).toBe(1);

    authFails = false;
    act(() => { window.dispatchEvent(new CustomEvent('auth:refreshed')); });
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(pendingCalls()).toBe(3);
    expect(clockCalls()).toBe(2);
  });

  it('Netzfehler pausieren nicht', async () => {
    h.get.mockImplementation((url: string) =>
      url.includes('pending-count') || url.includes('clock-status')
        ? Promise.reject(new Error('Network Error'))
        : Promise.resolve({ data: {} }),
    );
    mount();
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    const first = pendingCalls();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(pendingCalls()).toBe(first * 2);
  });
});
