import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Login from './Login';
import { useAuthStore } from '../stores/authStore';

// Log-Audit 2026-11-15 (Punkt 12, NET-4): fünf Fehlversuche mit Leerzeichen am
// Ende des Benutzernamens ('mmk ') — das Formular schickt den Namen jetzt getrimmt.
vi.mock('../api/client', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: {} })), post: vi.fn() },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

const loginMock = vi.fn();

beforeEach(() => {
  loginMock.mockReset().mockResolvedValue(undefined);
  useAuthStore.setState({ user: null, isAuthenticated: false, login: loginMock } as never);
});

describe('<Login />', () => {
  it('trimmt den Benutzernamen, das Passwort bleibt unverändert', async () => {
    render(<MemoryRouter><Login /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText('Benutzername'), { target: { value: '  mmk  ' } });
    fireEvent.change(screen.getByLabelText('Passwort'), { target: { value: ' geheim ' } });
    fireEvent.click(screen.getByRole('button', { name: /Anmelden/ }));
    await waitFor(() => expect(loginMock).toHaveBeenCalled());
    expect(loginMock).toHaveBeenCalledWith('mmk', ' geheim ', undefined);
  });
});
