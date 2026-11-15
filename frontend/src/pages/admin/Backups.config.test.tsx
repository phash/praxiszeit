import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

/**
 * Code-Review 2026-11-11: ops-02 (Speicherort-Override), ops-12 (kein Spinner
 * nach Aktionen, Zahlenfelder als Text), ops-15 (Warnung bei alter Sicherung),
 * ops-18 (aria-label der Icon-Buttons).
 */
const h = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
}));
vi.mock('../../api/client', () => ({ default: { get: h.get, put: h.put, post: h.post, delete: vi.fn() } }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import Backups from './Backups';

const overview = (override: string, backups: unknown[] = []) => ({
  data: {
    backups,
    config: { enabled: true, hour: 2, retention_days: 30, location: override || '/app/backups', location_override: override },
  },
});

beforeEach(() => {
  h.get.mockReset();
  h.put.mockReset();
  h.post.mockReset();
});

describe('Backups: Konfiguration', () => {
  it('Standardpfad ist kein Feldwert: leeres Feld, Platzhalter nennt den Standard; Zeitänderung sendet keinen Ort', async () => {
    h.get.mockResolvedValue(overview(''));
    h.put.mockResolvedValue({ data: overview('').data.config });
    render(<Backups />);
    const loc = (await screen.findByLabelText(/Speicherort/)) as HTMLInputElement;
    expect(loc.value).toBe('');
    expect(loc.placeholder).toContain('/app/backups');
    fireEvent.change(screen.getByLabelText(/Uhrzeit/), { target: { value: '4' } });
    fireEvent.click(screen.getByText('Einstellungen speichern'));
    await waitFor(() => expect(h.put).toHaveBeenCalled());
    const body = h.put.mock.calls[0][1];
    expect(body.hour).toBe(4);
    expect('location' in body).toBe(false);
  });

  it('Leeren des Override sendet "" (Zurücksetzen auf Standard)', async () => {
    h.get.mockResolvedValue(overview('/data/sicherung'));
    h.put.mockResolvedValue({ data: overview('').data.config });
    render(<Backups />);
    const loc = (await screen.findByLabelText(/Speicherort/)) as HTMLInputElement;
    expect(loc.value).toBe('/data/sicherung');
    fireEvent.change(loc, { target: { value: '' } });
    fireEvent.click(screen.getByText('Einstellungen speichern'));
    await waitFor(() => expect(h.put).toHaveBeenCalled());
    expect(h.put.mock.calls[0][1].location).toBe('');
  });

  it('geleerte Aufbewahrung wird nicht zu 0, sondern meldet inline und sendet nichts', async () => {
    h.get.mockResolvedValue(overview(''));
    render(<Backups />);
    fireEvent.change(await screen.findByLabelText(/Aufbewahrung/), { target: { value: '' } });
    fireEvent.click(screen.getByText('Einstellungen speichern'));
    expect(await screen.findByTestId('backup-config-error')).toHaveTextContent(/1 bis 3650/);
    expect(h.put).not.toHaveBeenCalled();
  });

  it('warnt, wenn die letzte Sicherung älter als 36 Stunden ist, und beschriftet Icon-Buttons', async () => {
    const old = new Date(Date.now() - 50 * 3600_000).toISOString();
    h.get.mockResolvedValue(overview('', [{ filename: 'praxiszeit_20260101_010101.sql.gz', size_bytes: 10, created_at: old }]));
    render(<Backups />);
    expect(await screen.findByTestId('backup-stale-warning')).toBeInTheDocument();
    expect(screen.getByLabelText('praxiszeit_20260101_010101.sql.gz herunterladen')).toBeInTheDocument();
    expect(screen.getByLabelText('praxiszeit_20260101_010101.sql.gz löschen')).toBeInTheDocument();
  });

  it('keine Warnung bei frischer Sicherung', async () => {
    const fresh = new Date(Date.now() - 2 * 3600_000).toISOString();
    h.get.mockResolvedValue(overview('', [{ filename: 'praxiszeit_20260101_010101.sql.gz', size_bytes: 10, created_at: fresh }]));
    render(<Backups />);
    await screen.findByText(/Vorhandene Sicherungen/);
    expect(screen.queryByTestId('backup-stale-warning')).toBeNull();
  });

  // Log-Audit 2026-11-15 (Punkt 7): Ergebnis des letzten Laufs (.last-result.json).
  it('zeigt einen fehlgeschlagenen letzten Lauf mit Fehlertext', async () => {
    const fresh = new Date(Date.now() - 2 * 3600_000).toISOString();
    h.get.mockResolvedValue({ data: { ...overview('', [{ filename: 'a.sql.gz', size_bytes: 10, created_at: fresh }]).data,
      last_result: { ok: false, finished_at: fresh, file: null, size_bytes: null, error: 'pg_dump fehlgeschlagen', mirror_ok: null, verified: false } } });
    render(<Backups />);
    expect(await screen.findByTestId('backup-failed-warning')).toHaveTextContent('pg_dump fehlgeschlagen');
    expect(screen.queryByTestId('backup-stale-warning')).toBeNull();
  });

  it('warnt, wenn die Kopie ins zweite Ziel fehlschlug', async () => {
    const fresh = new Date(Date.now() - 2 * 3600_000).toISOString();
    h.get.mockResolvedValue({ data: { ...overview('', [{ filename: 'a.sql.gz', size_bytes: 10, created_at: fresh }]).data,
      last_result: { ok: true, finished_at: fresh, file: 'a.sql.gz', size_bytes: 10, error: null, mirror_ok: false, verified: true } } });
    render(<Backups />);
    expect(await screen.findByTestId('backup-mirror-warning')).toBeInTheDocument();
    expect(screen.queryByTestId('backup-failed-warning')).toBeNull();
  });

  it('ohne last_result (ältere Server) keine Zusatzwarnung', async () => {
    const fresh = new Date(Date.now() - 2 * 3600_000).toISOString();
    h.get.mockResolvedValue(overview('', [{ filename: 'a.sql.gz', size_bytes: 10, created_at: fresh }]));
    render(<Backups />);
    await screen.findByText(/Vorhandene Sicherungen/);
    expect(screen.queryByTestId('backup-failed-warning')).toBeNull();
    expect(screen.queryByTestId('backup-mirror-warning')).toBeNull();
  });

  // Review-Nachzug Log-Audit Punkt 7: nach fehlgeschlagenem "Sofort sichern"
  // neu laden, damit last_result (ok=false) und das Banner sofort stimmen.
  it('laedt nach fehlgeschlagenem "Sofort sichern" neu und zeigt den Fehlschlag', async () => {
    const fresh = new Date(Date.now() - 2 * 3600_000).toISOString();
    const base = overview('', [{ filename: 'a.sql.gz', size_bytes: 10, created_at: fresh }]);
    h.get
      .mockResolvedValueOnce(base)
      .mockResolvedValueOnce({ data: { ...base.data,
        last_result: { ok: false, finished_at: fresh, file: null, size_bytes: null, error: 'Platte voll', mirror_ok: null, verified: false } } });
    h.post.mockRejectedValue(new Error('500'));
    render(<Backups />);
    await screen.findByText(/Vorhandene Sicherungen/);
    expect(screen.queryByTestId('backup-failed-warning')).toBeNull();
    fireEvent.click(screen.getByText('Jetzt sichern'));
    expect(await screen.findByTestId('backup-failed-warning')).toHaveTextContent('Platte voll');
    expect(h.get).toHaveBeenCalledTimes(2);
  });
});
