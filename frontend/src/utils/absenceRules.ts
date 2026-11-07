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
