import { describe, it, expect } from 'vitest';
import { backupBannerState, STALE_BACKUP_HOURS, BACKUP_STATUS_MIN_INTERVAL_MS } from './backupStatus';

// Log-Audit 2026-11-15 (Punkt 7, BO-2): Warnung zur Sicherung nicht nur auf der
// Sicherungsseite, sondern als Banner auf allen Seiten der Verwaltung.
const NOW = new Date('2026-11-15T12:00:00+01:00').getTime();
const hoursAgo = (h: number) => new Date(NOW - h * 3_600_000).toISOString();

describe('backupBannerState', () => {
  it('ohne Übersicht kein Banner', () => {
    expect(backupBannerState(null, NOW)).toBeNull();
    expect(backupBannerState(undefined, NOW)).toBeNull();
  });

  it('frische Sicherung und erfolgreicher Lauf: kein Banner', () => {
    expect(backupBannerState({
      backups: [{ created_at: hoursAgo(3) }],
      last_result: { ok: true, finished_at: hoursAgo(3), error: null },
    }, NOW)).toBeNull();
  });

  it('fehlgeschlagener letzter Lauf: Banner "failed" mit Fehlertext', () => {
    const s = backupBannerState({
      backups: [{ created_at: hoursAgo(3) }],
      last_result: { ok: false, finished_at: hoursAgo(1), error: 'pg_dump fehlgeschlagen' },
    }, NOW);
    expect(s).toEqual({ kind: 'failed', at: hoursAgo(1), error: 'pg_dump fehlgeschlagen' });
  });

  it('Fehler hat Vorrang vor veraltet', () => {
    const s = backupBannerState({
      backups: [{ created_at: hoursAgo(100) }],
      last_result: { ok: false, finished_at: null, error: null },
    }, NOW);
    expect(s?.kind).toBe('failed');
  });

  it('neueste Sicherung älter als 36 h: Banner "stale"', () => {
    const s = backupBannerState({
      backups: [{ created_at: hoursAgo(80) }, { created_at: hoursAgo(STALE_BACKUP_HOURS + 1) }],
      last_result: null,
    }, NOW);
    expect(s).toEqual({ kind: 'stale', at: hoursAgo(STALE_BACKUP_HOURS + 1), error: null });
  });

  // Review-Nachzug Log-Audit Punkt 7: Docker-Installationen mit Host-Cron
  // (tools/docker/backup.sh) oder abgeschaltetem Zeitplan sehen sonst dauerhaft
  // "veraltet", obwohl die App gar nicht planmaessig sichert.
  it('Zeitplan aus (Docker, kein externer Zeitplan): kein "stale"-Banner', () => {
    expect(backupBannerState({
      backups: [{ created_at: hoursAgo(40) }],
      config: { enabled: false },
    }, NOW)).toBeNull();
  });

  it('Zeitplan aus, aber nativer Dienst sichert selbst: "stale"-Banner', () => {
    expect(backupBannerState({
      backups: [{ created_at: hoursAgo(40) }],
      config: { enabled: false },
      scheduled_externally: true,
    }, NOW)?.kind).toBe('stale');
  });

  it('Zeitplan an: "stale"-Banner', () => {
    expect(backupBannerState({
      backups: [{ created_at: hoursAgo(40) }],
      config: { enabled: true },
    }, NOW)?.kind).toBe('stale');
  });

  it('Zeitplan aus: fehlgeschlagener Lauf meldet trotzdem', () => {
    expect(backupBannerState({
      backups: [{ created_at: hoursAgo(40) }],
      config: { enabled: false },
      last_result: { ok: false, finished_at: hoursAgo(1), error: 'x' },
    }, NOW)?.kind).toBe('failed');
  });

  it('genau an der Grenze noch kein Banner', () => {
    expect(backupBannerState({ backups: [{ created_at: hoursAgo(STALE_BACKUP_HOURS) }] }, NOW)).toBeNull();
  });

  it('noch keine Sicherung (Neuinstallation) ohne Fehler: kein Banner', () => {
    expect(backupBannerState({ backups: [], last_result: null }, NOW)).toBeNull();
  });

  it('kaputte Datumswerte und fehlende Felder lösen nichts aus', () => {
    expect(backupBannerState({ backups: [{ created_at: 'kaputt' }] }, NOW)).toBeNull();
    expect(backupBannerState({} as never, NOW)).toBeNull();
  });

  it('Abfrage höchstens alle 10 Minuten', () => {
    expect(BACKUP_STATUS_MIN_INTERVAL_MS).toBe(10 * 60 * 1000);
  });
});
