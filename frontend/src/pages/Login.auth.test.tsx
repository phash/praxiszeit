import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import Login from './Login';

// Code-Review 2026-11-11 (auth-06/21).
const h = vi.hoisted(() => ({ login: vi.fn(), authed: false }));

vi.mock('../stores/authStore', () => ({
  useAuthStore: (sel?: (s: any) => unknown) => {
    const state = { login: h.login, isAuthenticated: h.authed };
    return sel ? sel(state) : state;
  },
}));
vi.mock('../stores/systemStore', () => ({
  useSystemStore: (sel: (s: any) => unknown) => sel({ info: { deployment_mode: 'onprem' } }),
}));
vi.mock('../components/DocModal', () => ({ DocModal: () => null }));
vi.mock('../components/QrLinkModal', () => ({ default: () => null }));

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search}</div>;
}

function renderLogin(state?: unknown) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/login', state }]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  h.authed = false;
});

describe('<Login />', () => {
  it('auth-06: nach der Anmeldung geht es zum ursprünglichen Ziel', async () => {
    h.login.mockResolvedValue(undefined);
    renderLogin({ from: { pathname: '/admin/reports', search: '?month=3' } });
    fireEvent.change(screen.getByLabelText('Benutzername'), { target: { value: 'a' } });
    fireEvent.change(screen.getByLabelText('Passwort'), { target: { value: 'b' } });
    fireEvent.click(screen.getByRole('button', { name: /Anmelden/ }));
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/admin/reports?month=3'));
  });

  it('auth-06: eine bestehende Sitzung wird von /login weggeleitet', () => {
    h.authed = true;
    renderLogin();
    expect(screen.getByTestId('where')).toHaveTextContent('/');
  });

  it('auth-21: ein Namenswechsel nimmt das 2FA-Feld zurück', async () => {
    h.login.mockRejectedValueOnce({ response: { status: 401, headers: { 'x-requires-totp': 'true' } } });
    renderLogin();
    fireEvent.change(screen.getByLabelText('Benutzername'), { target: { value: 'mit2fa' } });
    fireEvent.change(screen.getByLabelText('Passwort'), { target: { value: 'b' } });
    fireEvent.click(screen.getByRole('button', { name: /Anmelden/ }));
    expect(await screen.findByLabelText(/2FA-Code/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Benutzername'), { target: { value: 'ohne2fa' } });
    expect(screen.queryByLabelText(/2FA-Code/)).not.toBeInTheDocument();
  });
});
