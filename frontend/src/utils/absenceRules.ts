/**
 * Audit 2026-11-07 (S1-01, #542): Frontend-Zwilling der Sperre in
 * ``backend/app/routers/absences.py`` (``_assert_employee_may_book_range`` /
 * ``_assert_employee_may_delete_absence``). Mitarbeitende buchen und löschen
 * Abwesenheiten vergangener Tage nicht direkt, sondern stellen im Journal einen
 * Änderungsantrag („Antrag"). Admins sind ausgenommen. Die Sperren für fremd
 * gebuchte Abwesenheiten und abgeschlossene Jahre kennt nur der Server (409).
 *
 * Wortlaut = ``PAST_DAY_ABSENCE_DETAIL`` im Backend.
 */
export const PAST_DAY_ABSENCE_HINT = 'Für vergangene Tage bitte einen Änderungsantrag stellen.';

/** Ort des Antrags-Wegs (Zeiterfassung → Journal, Zeile des Tages → „Antrag"). */
export const CHANGE_REQUEST_JOURNAL_PATH = '/time-tracking?tab=journal';

/** ``dateStr`` und ``todayStr`` als ``yyyy-MM-dd``. */
export function isPastDay(dateStr: string, todayStr: string): boolean {
  return !!dateStr && dateStr < todayStr;
}

/** Darf die Person diesen Zeitraum direkt buchen? Maßgeblich ist der Beginn. */
export function mayBookAbsenceDirectly(isAdmin: boolean, startDate: string, todayStr: string): boolean {
  return isAdmin || !isPastDay(startDate, todayStr);
}

/** Darf die Person diese Abwesenheit (nach Datum) direkt löschen? */
export function mayDeleteAbsenceByDate(isAdmin: boolean, absenceDate: string, todayStr: string): boolean {
  return isAdmin || !isPastDay(absenceDate, todayStr);
}

/**
 * Heutiges Datum (``yyyy-MM-dd``) in Europe/Berlin — wie ``today_local()`` im
 * Backend. Das Browserdatum weicht bei fremder Zeitzone ab (abw-13); die
 * Stornierbarkeit eines genehmigten Urlaubs entscheidet der Server nach Berliner Datum.
 */
export function todayBerlin(now: Date = new Date()): string {
  // sv-SE formatiert als ``yyyy-MM-dd``.
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Berlin' }).format(now);
}

/** Kalendertag (``yyyy-MM-dd``) eines Zeitstempels in Europe/Berlin. */
export function berlinDateOf(timestamp: string | Date): string {
  const d = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  return todayBerlin(d);
}

/**
 * Verbleibende Sperrfrist-Tage (14 Tage ab Deaktivierung) für die Anonymisierung —
 * reiner Kalendertagsvergleich in Berliner Datum, wie ``_grace_days_since_deactivation``
 * im Backend (kein Rechnen mit Uhrzeit/UTC-Tag).
 */
export function graceRemainingDays(deactivatedAt: string | null | undefined, today: string = todayBerlin()): number {
  if (!deactivatedAt) return 0;
  const start = Date.parse(`${berlinDateOf(deactivatedAt)}T00:00:00Z`);
  const now = Date.parse(`${today}T00:00:00Z`);
  const elapsed = Math.round((now - start) / 86_400_000);
  return Math.max(0, 14 - elapsed);
}
