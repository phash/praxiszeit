import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TimeTracking from './TimeTracking';

// ui-17: Formular „Neuer Zeiteintrag“ — ab md Seitenblock (kein modaler Dialog),
// darunter Bottom-Sheet mit role=dialog/aria-modal und Escape.
const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: { get: (...a: unknown[]) => getMock(...a), put: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));
const toastObj = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toastObj }));
vi.mock('../stores/authStore', () => ({
  useAuthStore: () => ({ user: { id: 'u1', role: 'employee', weekly_hours: 40, work_days_per_week: 5, exempt_from_arbzg: false } }),
}));
vi.mock('../stores/uiStore', () => ({ useUIStore: () => ({ stampVersion: 0 }) }));

function stubMatchMedia(desktop: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: desktop,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
    onchange: null,
  })) as unknown as typeof window.matchMedia;
}

const original = window.matchMedia;
beforeEach(() => {
  getMock.mockReset().mockImplementation((url: string) =>
    Promise.resolve({ data: url.includes('/settings') ? {} : [] }),
  );
});
afterEach(() => {
  window.matchMedia = original;
});

const open = async () => {
  render(<MemoryRouter><TimeTracking /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: /Neuer Eintrag/ }));
};

describe('TimeTracking Formular-Semantik (ui-17)', () => {
  it('Desktop: kein role=dialog / aria-modal, die Seite bleibt bedienbar', async () => {
    stubMatchMedia(true);
    await open();
    expect(screen.queryByRole('dialog')).toBeNull();
    const region = screen.getByRole('region', { name: 'Neuer Zeiteintrag' });
    expect(region).not.toHaveAttribute('aria-modal');
  });

  it('Mobil: modaler Dialog, Escape schließt das Formular', async () => {
    stubMatchMedia(false);
    await open();
    const dialog = screen.getByRole('dialog', { name: 'Neuer Zeiteintrag' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
