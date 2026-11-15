import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import apiClient from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useSystemStore } from '../stores/systemStore';
import {
  backupBannerState,
  BACKUP_STATUS_MIN_INTERVAL_MS,
  backupStatusCache as cache,
  BACKUP_STATUS_CHANGED_EVENT,
  STALE_BACKUP_HOURS,
  type BackupBannerState,
  type BackupOverviewLike,
} from '../utils/backupStatus';

/**
 * Log-Audit 2026-11-15 (Punkt 7, BO-2): globales Admin-Banner, wenn die letzte
 * Sicherung fehlgeschlagen oder älter als 36 h ist. Bisher stand die Warnung
 * nur auf der Sicherungsseite, die ein Kunde in 7 Monaten ~60 Mal öffnete.
 *
 * Kein eigenes Polling: Abfrage beim Einblenden und bei Fensterfokus, höchstens
 * alle 10 Minuten (Stand modulweit in `backupStatusCache`, damit ein erneutes
 * Einhängen nicht neu fragt). Im SaaS-Modus gibt es `/admin/backups` nicht;
 * jeder Fehler blendet das Banner aus.
 */
function formatAt(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
}

export default function BackupStatusBanner() {
  const role = useAuthStore((s) => s.user?.role);
  const isImpersonating = useAuthStore((s) => s.isImpersonating());
  const deploymentMode = useSystemStore((s) => s.info?.deployment_mode);
  const enabled = role === 'admin' && !isImpersonating && deploymentMode !== 'saas';
  const [state, setState] = useState<BackupBannerState | null>(enabled ? cache.lastState : null);

  useEffect(() => {
    if (!enabled) {
      setState(null);
      return;
    }
    let cancelled = false;
    const load = () => {
      const now = Date.now();
      if (now - cache.lastFetchAt < BACKUP_STATUS_MIN_INTERVAL_MS) {
        setState(cache.lastState);
        return;
      }
      cache.lastFetchAt = now;
      apiClient
        .get<BackupOverviewLike>('/admin/backups')
        .then((r) => {
          cache.lastState = backupBannerState(r.data, Date.now());
          if (!cancelled) setState(cache.lastState);
        })
        .catch(() => {
          cache.lastState = null;
          if (!cancelled) setState(null);
        });
    };
    load();
    const onFocus = () => load();
    const onChanged = () => setState(cache.lastState);
    window.addEventListener('focus', onFocus);
    window.addEventListener(BACKUP_STATUS_CHANGED_EVENT, onChanged);
    return () => {
      cancelled = true;
      window.removeEventListener('focus', onFocus);
      window.removeEventListener(BACKUP_STATUS_CHANGED_EVENT, onChanged);
    };
  }, [enabled]);

  if (!enabled || !state) return null;

  const at = formatAt(state.at);
  return (
    <div
      role="alert"
      data-testid="backup-status-banner"
      className="flex items-start sm:items-center justify-center gap-2 text-sm px-4 py-2 bg-amber-100 text-amber-900"
    >
      <AlertTriangle size={16} className="shrink-0 mt-0.5 sm:mt-0" aria-hidden="true" />
      <span>
        {state.kind === 'failed' ? (
          <>
            Die letzte Datensicherung ist fehlgeschlagen{at ? ` (${at})` : ''}
            {state.error ? `: ${state.error}` : ''}.{' '}
          </>
        ) : (
          <>
            Die letzte Datensicherung ist älter als {STALE_BACKUP_HOURS} Stunden{at ? ` (${at})` : ''}.{' '}
          </>
        )}
        <Link to="/admin/backups" className="font-medium underline">
          Zur Datensicherung
        </Link>
      </span>
    </div>
  );
}
