// Re-export from canonical location for backward compatibility
export { formatHoursHM } from './formatters';

/**
 * Extract a readable error message from an API error response.
 * Handles Pydantic validation errors (array of {type, loc, msg, input, ctx})
 * and standard HTTPException errors (string detail).
 */
export function getErrorMessage(error: any, fallback: string = 'Ein Fehler ist aufgetreten'): string {
  const status = error?.response?.status;
  const data = error?.response?.data;
  const detail = data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((err: any) => err.msg || String(err)).join(', ');
  }
  if (typeof detail === 'string') {
    return detail;
  }
  // U4 (Audit 2026-07-31): slowapi's built-in rate-limit handler (login,
  // /auth/refresh, TOTP setup/verify, signup, feedback, …) answers HTTP 429
  // with `{"error": "Rate limit exceeded: 5 per 1 minute"}` — a shape this
  // helper never read, so every rate-limited call fell through to the
  // caller's generic fallback ("Anmeldung fehlgeschlagen. Bitte versuchen Sie
  // es erneut."). That is the worst possible advice for a *rate* limit: every
  // further attempt just extends the lockout window, and because the limiter
  // keys on IP (not account) it blocks every colleague sharing a reception PC
  // at once. Handled centrally here so all callers benefit, not just Login.
  // The separate account-lockout 429 from /auth/login (`_LOCKOUT_ATTEMPTS`)
  // already carries a self-explanatory German `detail` and is returned by the
  // branch above before this is ever reached.
  if (status === 429) {
    return 'Zu viele Versuche in kurzer Zeit. Bitte warten Sie einen Moment, bevor Sie es erneut versuchen — ein sofortiger weiterer Versuch verlängert die Sperre nur.';
  }
  if (typeof data?.error === 'string') {
    return data.error;
  }
  return fallback;
}
