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
}));
vi.mock('../../api/client', () => ({ default: { get: h.get, put: h.put, post: vi.fn(), delete: vi.fn() } }));
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
});
