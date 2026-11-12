import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

/** Code-Review 2026-11-11: ops-03 (URL ändern), ops-11 (Kürzung, Volltext, Race, Fehlergründe). */
const h = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), toastError: vi.fn() }));
vi.mock('../../api/client', () => ({ default: { get: h.get, patch: h.patch, delete: vi.fn() } }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: h.toastError, warning: vi.fn(), info: vi.fn() }),
}));

import ErrorMonitoring from './ErrorMonitoring';

const mk = (i: number, extra: Record<string, unknown> = {}) => ({
  id: `e${i}`, level: 'error', logger: 'app', message: `Meldung ${i} ` + 'x'.repeat(200), traceback: null,
  path: null, method: null, status_code: 500, count: 1, first_seen: '2026-11-01T10:00:00Z',
  last_seen: '2026-11-01T10:00:00Z', status: 'open', github_issue_url: null, ...extra,
});

beforeEach(() => { h.get.mockReset(); h.patch.mockReset(); h.toastError.mockReset(); });

describe('ErrorMonitoring Aktionen', () => {
  it('„Ändern“ öffnet das Eingabefeld für die Issue-URL', async () => {
    h.get.mockImplementation(async (u: string) =>
      u.startsWith('/admin/errors/summary') ? { data: { open: 1 } }
        : { data: [mk(1, { github_issue_url: 'https://github.com/phash/praxiszeit/issues/5' })] });
    render(<ErrorMonitoring />);
    fireEvent.click(await screen.findByLabelText('Details anzeigen'));
    expect(screen.queryByPlaceholderText(/github.com/)).toBeNull();
    fireEvent.click(screen.getByText('Ändern'));
    const input = (await screen.findByPlaceholderText(/github.com/)) as HTMLInputElement;
    expect(input.value).toBe('https://github.com/phash/praxiszeit/issues/5');
    fireEvent.click(screen.getByText('Abbrechen'));
    expect(screen.queryByPlaceholderText(/github.com/)).toBeNull();
  });

  it('zeigt die volle Meldung im aufgeklappten Bereich und weist Pull-Request-URLs mit Grund ab', async () => {
    h.get.mockImplementation(async (u: string) =>
      u.startsWith('/admin/errors/summary') ? { data: { open: 1 } } : { data: [mk(1)] });
    render(<ErrorMonitoring />);
    fireEvent.click(await screen.findByLabelText('Details anzeigen'));
    expect(screen.getByTestId('error-full-message').textContent).toContain('x'.repeat(200));
    fireEvent.change(screen.getByPlaceholderText(/github.com/), { target: { value: 'https://github.com/phash/praxiszeit/pull/12' } });
    fireEvent.click(screen.getByText('Speichern'));
    expect(h.toastError).toHaveBeenCalledWith(expect.stringMatching(/issues\/<Nummer>/));
    expect(h.patch).not.toHaveBeenCalled();
  });

  it('weist auf gekürzte Liste hin und lädt mit höherem Limit nach', async () => {
    const list = Array.from({ length: 100 }, (_, i) => mk(i));
    h.get.mockImplementation(async (u: string) =>
      u.startsWith('/admin/errors/summary') ? { data: { open: 250 } } : { data: list });
    render(<ErrorMonitoring />);
    expect(await screen.findByTestId('error-list-truncation')).toHaveTextContent('100 von 250');
    fireEvent.click(screen.getByText('Mehr laden'));
    await waitFor(() => expect(h.get).toHaveBeenCalledWith('/admin/errors/?status=open&limit=200'));
  });

  it('verwirft die späte Antwort eines vorherigen Tabs', async () => {
    let resolveOpen: (v: unknown) => void = () => {};
    h.get.mockImplementation((u: string) => {
      if (u.startsWith('/admin/errors/summary')) return Promise.resolve({ data: { open: 1, resolved: 1 } });
      if (u.includes('status=open')) return new Promise(r => { resolveOpen = r; });
      return Promise.resolve({ data: [mk(2, { message: 'BEHOBEN-FEHLER', status: 'resolved' })] });
    });
    render(<ErrorMonitoring />);
    fireEvent.click(await screen.findByText('Behoben'));
    expect(await screen.findByText(/BEHOBEN-FEHLER/)).toBeInTheDocument();
    resolveOpen({ data: [mk(1, { message: 'OFFENER-FEHLER' })] });
    await Promise.resolve();
    await Promise.resolve();
    expect(screen.queryByText(/OFFENER-FEHLER/)).toBeNull();
  });
});
