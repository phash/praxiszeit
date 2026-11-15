/**
 * Log-Audit 2026-11-15 (Punkt 7, BO-2): Ein Kundenserver hatte alle Sicherungen
 * auf derselben Platte, die Warnung „Sicherung veraltet“ stand nur auf der
 * selten geöffneten Sicherungsseite. Diese Regel entscheidet über das Banner auf
 * allen Seiten der Verwaltung (`components/BackupStatusBanner.tsx`) und über
 * die Warnung auf der Sicherungsseite.
 *
 * `last_result` stammt aus `data/backups/.last-result.json`, die
 * `praxiszeit-server.py create_backup` nach jedem Lauf schreibt (null =
 * Datei fehlt/unlesbar).
 */

/** Ältester noch unauffälliger Stand der letzten Sicherung (Stunden). */
export const STALE_BACKUP_HOURS = 36;

/** Banner-Abfrage höchstens alle 10 Minuten (kein zusätzliches Polling). */
export const BACKUP_STATUS_MIN_INTERVAL_MS = 10 * 60 * 1000;

export interface BackupLastResult {
  ok: boolean;
  finished_at?: string | null;
  file?: string | null;
  size_bytes?: number | null;
  error?: string | null;
  mirror_ok?: boolean | null;
  verified?: boolean;
}

export interface BackupOverviewLike {
  backups?: { created_at: string }[] | null;
  last_result?: BackupLastResult | null;
  /** Zeitplan der App (fehlt = unbekannt, z. B. Sicherungsseite: „veraltet“ immer). */
  config?: { enabled: boolean } | null;
  /**
   * true = ein Zeitplan außerhalb der App-Einstellung sichert (nativ:
   * praxiszeit-server.py bzw. Windows-Aufgabe), auch bei `config.enabled=false`.
   */
  scheduled_externally?: boolean | null;
}

export interface BackupBannerState {
  kind: 'failed' | 'stale';
  /** Zeitpunkt des fehlgeschlagenen Laufs bzw. der neuesten Sicherung (ISO). */
  at: string | null;
  error: string | null;
}

/** Zeitstempel (ms) der neuesten Sicherung oder null. */
export function newestBackupTime(backups: { created_at: string }[] | null | undefined): number | null {
  let newest: number | null = null;
  for (const b of backups ?? []) {
    const t = new Date(b.created_at).getTime();
    if (Number.isFinite(t) && (newest === null || t > newest)) newest = t;
  }
  return newest;
}

/**
 * null = kein Banner. Fehlgeschlagener letzter Lauf hat Vorrang (immer); sonst
 * „veraltet“, wenn die neueste Sicherung älter als 36 h ist und ein Zeitplan
 * läuft (`config.enabled` oder `scheduled_externally`; ohne `config` immer). Ohne jede
 * Sicherung und ohne Fehlschlag (Neuinstallation) kein Banner.
 */
export function backupBannerState(
  overview: BackupOverviewLike | null | undefined,
  now: number,
): BackupBannerState | null {
  if (!overview) return null;
  const last = overview.last_result;
  if (last && last.ok === false) {
    return { kind: 'failed', at: last.finished_at ?? null, error: last.error ?? null };
  }
  // Review-Nachzug Log-Audit Punkt 7: „veraltet“ nur, wenn planmäßig gesichert
  // wird. Docker mit Host-Cron (tools/docker/backup.sh → ./backups, nicht in
  // dieser Liste) oder eine Testinstallation mit einer alten Handsicherung
  // sähen sonst dauerhaft das Banner. Ohne `config` (Sicherungsseite) wie bisher.
  const cfg = overview.config;
  if (cfg && cfg.enabled !== true && overview.scheduled_externally !== true) return null;
  const backups = overview.backups ?? [];
  const newestListed = newestBackupTime(backups);
  // Release-Review 1.24.1: Mit eigenem Sicherungsort listet die Seite nur
  // diesen Ordner, die nächtliche native Sicherung schreibt aber nach
  // data/backups. Ein erfolgreicher letzter Lauf zählt deshalb mit.
  const lastOkAt = last && last.ok === true && last.finished_at ? new Date(last.finished_at).getTime() : NaN;
  const lastOk = Number.isFinite(lastOkAt) ? lastOkAt : null;
  const newest = newestListed === null ? lastOk : lastOk === null ? newestListed : Math.max(newestListed, lastOk);
  if (newest === null) return null;
  if ((now - newest) / 3_600_000 > STALE_BACKUP_HOURS) {
    const at = newest === lastOk ? (last?.finished_at ?? null)
      : (backups.find((b) => new Date(b.created_at).getTime() === newest)?.created_at ?? null);
    return { kind: 'stale', at, error: null };
  }
  return null;
}

/**
 * Modulweiter Abfragestand des Banners: ein erneutes Einhängen (Seitenwechsel,
 * Anmeldung) fragt innerhalb der 10 Minuten nicht erneut.
 */
export const backupStatusCache: { lastFetchAt: number; lastState: BackupBannerState | null } = {
  lastFetchAt: 0,
  lastState: null,
};

/** Nur für Tests: Abfragestand zurücksetzen. */
export function resetBackupStatusCache() {
  backupStatusCache.lastFetchAt = 0;
  backupStatusCache.lastState = null;
}

/** Ereignis: die Sicherungsseite hat einen neuen Stand geladen (Banner sofort angleichen). */
export const BACKUP_STATUS_CHANGED_EVENT = 'backup-status:changed';

/**
 * Die Sicherungsseite meldet ihren frisch geladenen Stand, damit das Banner
 * nach „Sofort sichern“ nicht bis zu 10 Minuten weiter warnt.
 */
export function publishBackupOverview(overview: BackupOverviewLike, now: number) {
  backupStatusCache.lastFetchAt = now;
  backupStatusCache.lastState = backupBannerState(overview, now);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(BACKUP_STATUS_CHANGED_EVENT));
  }
}
