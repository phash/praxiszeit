/**
 * Rueckstellen der Mandanten-Einstellungen nach einer Aufnahme (e2e/handbuch/capture.ts).
 *
 * GET /api/admin/settings listet nur gespeicherte Zeilen. Fehlt eine Zeile,
 * gilt der Lese-Default der App — er steht hier, abgelesen aus dem Backend:
 *   break_validation_service (break_exception_allowed True), time_entries
 *   (break_exception_requires_approval False), vacation_requests/absences
 *   (vacation_approval_required False), closure_split_service u. a.
 *   (closure_overtime_after_vacation False), work_window_service (Puffer 15),
 *   main.system_info (onboarding_enabled True), shift_planning (Flag False,
 *   Wochentage Mo–Fr), calculation_service.child_sick_cap (15),
 *   dashboard/reports (Jahresende-Projektion True),
 *   special_days_service (Modus working_day, counts_as_vacation true, max_hours 4).
 * Schluessel ohne festen Default (holiday_state = Konfigurationswert) fehlen
 * absichtlich: sie lassen sich nur zuruecksetzen, wenn eine Zeile existiert.
 */
export const SETTING_DEFAULTS: Readonly<Record<string, string>> = {
  break_exception_allowed: 'true',
  break_exception_requires_approval: 'false',
  vacation_approval_required: 'false',
  closure_overtime_after_vacation: 'false',
  work_window_grace_minutes: '15',
  onboarding_enabled: 'true',
  shift_planning_enabled: 'false',
  shift_planning_weekdays: '0,1,2,3,4',
  child_sick_days_default: '15',
  show_year_end_overtime_employee_dashboard: 'true',
  show_year_end_overtime_admin_dashboard: 'true',
  special_day_dec24_mode: 'working_day',
  special_day_dec31_mode: 'working_day',
  special_day_dec24_counts_as_vacation: 'true',
  special_day_dec31_counts_as_vacation: 'true',
  special_day_dec24_max_hours: '4',
  special_day_dec31_max_hours: '4',
};

/**
 * Werte, auf die nach der Aufnahme zurueckgestellt wird: gespeicherter Wert,
 * sonst der App-Default. Wirft VOR jeder Aenderung, wenn fuer einen Schluessel
 * keins von beiden bekannt ist.
 */
export function planSettingsRestore(
  requested: Record<string, boolean | string | number>,
  stored: Record<string, string>,
): Record<string, string> {
  const plan: Record<string, string> = {};
  for (const key of Object.keys(requested)) {
    if (Object.prototype.hasOwnProperty.call(stored, key)) plan[key] = stored[key];
    else if (Object.prototype.hasOwnProperty.call(SETTING_DEFAULTS, key)) plan[key] = SETTING_DEFAULTS[key];
    else {
      throw new Error(
        `Einstellung ${key}: weder gespeichert noch mit bekanntem Default — nicht wiederherstellbar, ` +
          'deshalb nicht gesetzt (Default in settingsRestore.ts ergaenzen oder Zeile im Seed anlegen)',
      );
    }
  }
  return plan;
}
