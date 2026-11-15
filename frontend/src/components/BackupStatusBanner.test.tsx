import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import BackupStatusBanner from './BackupStatusBanner';
import { publishBackupOverview, resetBackupStatusCache } from '../utils/backupStatus';
import { useAuthStore } from '../stores/authStore';
import { useSystemStore } from '../stores/systemStore';

// Log-Audit 2026-11-15 (Punkt 7): globales Admin-Banner zur Datensicherung.
const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: { get: (...args: unknown[]) => getMock(...args) },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();

function mount(role: 'admin' | 'employee', mode: 'onprem' | 'saas' = 'onprem') {
  useAuthStore.setState({ user: { role, first_name: 'A', last_name: 'B', username: 'ab' } as never });
  useSystemStore.setState({ info: { deployment_mode: mode } as never });
  return render(<MemoryRouter><BackupStatusBanner /></MemoryRouter>);
}

beforeEach(() => {
  getMock.mockReset();
  resetBackupStatusCache();
});

describe('<BackupStatusBanner />', () => {
  it('zeigt den Fehlschlag mit Fehlertext und Link', async () => {
    getMock.mockResolvedValue({ data: {
      backups: [{ created_at: hoursAgo(2) }],
      last_result: { ok: false, finished_at: hoursAgo(1), error: 'Platte voll' },
    } });
    mount('admin');
    const banner = await screen.findByTestId('backup-status-banner');
    expect(banner).toHaveTextContent('Die letzte Datensicherung ist fehlgeschlagen');
    expect(banner).toHaveTextContent('Platte voll');
    expect(screen.getByRole('link', { name: 'Zur Datensicherung' })).toHaveAttribute('href', '/admin/backups');
    expect(getMock).toHaveBeenCalledWith('/admin/backups');
  });

  it('zeigt "älter als 36 Stunden"', async () => {
    getMock.mockResolvedValue({ data: { backups: [{ created_at: hoursAgo(50) }], last_result: null } });
    mount('admin');
    expect(await screen.findByTestId('backup-status-banner')).toHaveTextContent('älter als 36 Stunden');
  });

  it('nichts bei frischer Sicherung', async () => {
    getMock.mockResolvedValue({ data: { backups: [{ created_at: hoursAgo(2) }], last_result: { ok: true } } });
    mount('admin');
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(screen.queryByTestId('backup-status-banner')).toBeNull();
  });

  it('nichts für Mitarbeitende und im SaaS-Modus, keine Abfrage', () => {
    mount('employee');
    mount('admin', 'saas');
    expect(getMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId('backup-status-banner')).toBeNull();
  });

  it('Fehler der Abfrage (z. B. 404) blendet aus', async () => {
    getMock.mockRejectedValue({ response: { status: 404 } });
    mount('admin');
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(screen.queryByTestId('backup-status-banner')).toBeNull();
  });

  it('Fensterfokus fragt höchstens alle 10 Minuten neu', async () => {
    getMock.mockResolvedValue({ data: { backups: [], last_result: null } });
    mount('admin');
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));
    act(() => { window.dispatchEvent(new Event('focus')); });
    expect(getMock).toHaveBeenCalledTimes(1);
    const realNow = Date.now;
    try {
      Date.now = () => realNow() + 11 * 60 * 1000;
      act(() => { window.dispatchEvent(new Event('focus')); });
      expect(getMock).toHaveBeenCalledTimes(2);
    } finally {
      Date.now = realNow;
    }
  });

  it('neuer Stand der Sicherungsseite blendet das Banner sofort aus', async () => {
    getMock.mockResolvedValue({ data: { backups: [{ created_at: hoursAgo(50) }], last_result: null } });
    mount('admin');
    await screen.findByTestId('backup-status-banner');
    act(() => publishBackupOverview({ backups: [{ created_at: hoursAgo(0) }], last_result: { ok: true } }, Date.now()));
    expect(screen.queryByTestId('backup-status-banner')).toBeNull();
    expect(getMock).toHaveBeenCalledTimes(1);
  });
});
