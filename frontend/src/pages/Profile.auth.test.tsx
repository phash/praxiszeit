import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Profile from './Profile';

// Code-Review 2026-11-11 (auth-01/02/03/08/12/14/15).

const h = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
  store: {
    user: null as any,
    setUser: vi.fn(),
    setTokens: vi.fn(),
    impersonation: null as any,
  },
}));

vi.mock('../api/client', () => ({ default: h.api }));
vi.mock('../contexts/ToastContext', () => ({ useToast: () => h.toast }));
vi.mock('../components/MyWorkScheduleCard', () => ({ default: () => null }));
vi.mock('../components/MyQualificationsCard', () => ({ default: () => null }));
vi.mock('../stores/authStore', () => ({ useAuthStore: () => h.store }));

const USER = {
  id: 'u1', username: 'employee', email: 'employee@test.de', first_name: 'Max', last_name: 'Mustermann',
  role: 'employee', vacation_days: 30, is_active: true, track_hours: true,
  totp_enabled: false, calendar_color: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  h.store.user = { ...USER };
  h.store.impersonation = null;
});

describe('<Profile /> Rückmeldungen und Sitzung', () => {
  it('auth-02: meldet die Passwortänderung per Toast, obwohl das Formular zuklappt', async () => {
    h.api.post.mockResolvedValue({ data: { access_token: 'new' } });
    render(<Profile />);
    fireEvent.click(screen.getByText('Ändern'));
    fireEvent.change(screen.getByLabelText('Aktuelles Passwort'), { target: { value: 'AltesPasswort1' } });
    fireEvent.change(screen.getByLabelText('Neues Passwort'), { target: { value: 'NeuesPasswort2026' } });
    fireEvent.change(screen.getByLabelText('Passwort bestätigen'), { target: { value: 'NeuesPasswort2026' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));
    await waitFor(() => expect(h.toast.success).toHaveBeenCalledWith('Passwort erfolgreich geändert'));
    expect(h.store.setTokens).toHaveBeenCalledWith('new', h.store.user);
  });

  it('auth-03: ein Bild-Fehler erscheint rot, nicht im grünen Erfolgskasten', () => {
    const { container } = render(<Profile />);
    const file = new File([new Uint8Array(600_000)], 'big.png', { type: 'image/png' });
    fireEvent.change(container.querySelector('input[type=file]')!, { target: { files: [file] } });
    const box = screen.getByText('Bild zu groß (max. 500 KB)');
    expect(box.className).toContain('bg-red-50');
  });

  it('auth-03: scheitert die Farbänderung, kommt die alte Farbe zurück und die Meldung ist rot', async () => {
    h.api.put.mockRejectedValue(new Error('boom'));
    render(<Profile />);
    const before = screen.getAllByRole('button', { pressed: true });
    fireEvent.click(screen.getAllByRole('button', { name: /^Farbe / })[3]);
    const alert = await screen.findByRole('alert');
    expect(alert.className).toContain('bg-red-50');
    expect(screen.getAllByRole('button', { pressed: true }).length).toBe(before.length);
    expect(screen.getAllByRole('button', { name: /^Farbe / })[3]).toHaveAttribute('aria-pressed', 'false');
  });

  it('auth-14/15: Labels sind verknüpft, geleerte Namen werden nicht still verworfen', async () => {
    render(<Profile />);
    fireEvent.click(screen.getByText('Bearbeiten'));
    const first = screen.getByLabelText('Vorname');
    fireEvent.change(first, { target: { value: '  ' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));
    expect(await screen.findByText('Vorname und Nachname dürfen nicht leer sein.')).toBeInTheDocument();
    expect(h.api.put).not.toHaveBeenCalled();
    // Abbrechen + erneut öffnen: Entwurf verworfen
    fireEvent.click(screen.getByText('Abbrechen'));
    fireEvent.click(screen.getByText('Bearbeiten'));
    expect(screen.getByLabelText('Vorname')).toHaveValue('Max');
  });

  it('auth-01: 2FA abschalten übernimmt das frische Access-Token', async () => {
    h.store.user = { ...USER, totp_enabled: true };
    h.api.delete.mockResolvedValue({ data: { ...USER, totp_enabled: false, access_token: 'fresh' } });
    render(<Profile />);
    fireEvent.click(screen.getByRole('button', { name: /2FA deaktivieren/ }));
    fireEvent.change(screen.getByPlaceholderText('Ihr aktuelles Passwort'), { target: { value: 'pw' } });
    fireEvent.change(screen.getByLabelText('2FA-Code'), { target: { value: '123456' } });
    fireEvent.click(screen.getAllByRole('button', { name: /2FA deaktivieren/ }).at(-1)!);
    await waitFor(() => expect(h.store.setTokens).toHaveBeenCalled());
    const [token, user] = h.store.setTokens.mock.calls[0];
    expect(token).toBe('fresh');
    expect(user.access_token).toBeUndefined();
    expect(user.totp_enabled).toBe(false);
  });

  it('auth-12: Kopieren ohne navigator.clipboard wirft nicht, sondern gibt einen Hinweis', async () => {
    h.api.post.mockResolvedValue({ data: { otpauth_uri: 'otpauth://x', secret: 'ABCDEF' } });
    const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    render(<Profile />);
    fireEvent.click(screen.getByRole('button', { name: /2FA aktivieren/ }));
    fireEvent.change(screen.getByPlaceholderText('Ihr aktuelles Passwort'), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: 'Weiter' }));
    fireEvent.click(await screen.findByTitle('Kopieren'));
    await waitFor(() => expect(h.toast.info).toHaveBeenCalled());
    if (original) Object.defineProperty(navigator, 'clipboard', original);
    else delete (navigator as any).clipboard;
  });

  it('auth-13: Doppelklick auf „Weiter“ löst nur eine Einrichtung aus', async () => {
    let resolve!: (v: unknown) => void;
    h.api.post.mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<Profile />);
    fireEvent.click(screen.getByRole('button', { name: /2FA aktivieren/ }));
    fireEvent.change(screen.getByPlaceholderText('Ihr aktuelles Passwort'), { target: { value: 'pw' } });
    const next = screen.getByRole('button', { name: 'Weiter' });
    fireEvent.click(next);
    fireEvent.click(next);
    expect(h.api.post).toHaveBeenCalledTimes(1);
    resolve({ data: { otpauth_uri: 'otpauth://x', secret: 'S' } });
  });

  it('auth-08: in „Login als“ gibt es keine Schreibsteuerelemente', () => {
    h.store.impersonation = { targetName: 'Max Mustermann' };
    render(<Profile />);
    expect(screen.queryByText('Bearbeiten')).not.toBeInTheDocument();
    expect(screen.queryByText('Ändern')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /2FA aktivieren/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Änderungen sind hier nicht möglich/)).toBeInTheDocument();
  });
});
