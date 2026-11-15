/**
 * Log-Audit 2026-11-15 (Punkt 17, NET-3): nach Ablauf der Sitzung lief das
 * Hintergrund-Polling im Layout weiter (~1400 Abfragen mit 401). Ein 401/403
 * bei einer Abfrage, die der Client nicht mehr per Refresh retten konnte,
 * pausiert das Polling bis zur nächsten erfolgreichen Anmeldung bzw.
 * Token-Erneuerung oder einem Seitenwechsel. Netzfehler, 5xx (Neustart beim
 * Update) und 429 pausieren nicht — dort geht es von selbst weiter.
 */
export function isAuthPollFailure(err: unknown): boolean {
  const status = (err as { response?: { status?: number } } | null | undefined)?.response?.status;
  return status === 401 || status === 403;
}

/** Ereignis, das `api/client.ts` nach jeder erfolgreichen Token-Erneuerung auslöst. */
export const AUTH_REFRESHED_EVENT = 'auth:refreshed';
