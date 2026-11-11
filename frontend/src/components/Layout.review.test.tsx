import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Layout from './Layout';
import { useAuthStore } from '../stores/authStore';
import { useUIStore } from '../stores/uiStore';

const h = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../api/client', () => ({
  default: { get: h.get, post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

let clocked = false;
beforeEach(() => {
  clocked = false;
  h.get.mockReset().mockImplementation((url: string) =>
    Promise.resolve({ data: url.includes('clock-status') ? { is_clocked_in: clocked } : {} }),
  );
});

function mount(trackHours: boolean) {
  useAuthStore.setState({
    user: { role: 'employee', first_name: 'A', last_name: 'B', username: 'ab', track_hours: trackHours } as never,
  });
  return render(
    <MemoryRouter initialEntries={['/absences']}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="absences" element={<div />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('Layout Review 2026-11-11', () => {
  it('ui-18: FAB folgt dem Stempeln von der Seite (stampVersion)', async () => {
    mount(true);
    await screen.findByLabelText('Stempeluhr öffnen');
    clocked = true;
    act(() => useUIStore.getState().notifyStampChange());
    await screen.findByLabelText('Eingestempelt – Stempeluhr öffnen');
  });

  it('ui-19: aktive Navigation trägt aria-current, Platzhalter nur mit FAB', async () => {
    const { container, unmount } = mount(true);
    await screen.findByLabelText('Stempeluhr öffnen');
    expect(screen.getAllByRole('link', { name: /Abwesenheiten|Abwes\./ }).some((l) => l.getAttribute('aria-current') === 'page')).toBe(true);
    expect(container.querySelector('nav .w-\\[72px\\]')).not.toBeNull();
    unmount();
    const second = mount(false);
    await waitFor(() => expect(h.get).toHaveBeenCalled());
    expect(second.container.querySelector('nav .w-\\[72px\\]')).toBeNull();
  });

  it('ui-19: geöffnetes Menü ist ein modaler Dialog, geschlossen nicht', async () => {
    mount(true);
    expect(screen.queryByRole('dialog', { name: 'Hauptmenü' })).toBeNull();
    fireEvent.click(screen.getByLabelText('Menü öffnen'));
    expect(screen.getByRole('dialog', { name: 'Hauptmenü' })).toHaveAttribute('aria-modal', 'true');
  });
});
