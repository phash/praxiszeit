// Spec 2026-10-08, 11.3: Antwortformen des Dialogs „Arbeitszeit & Wochenstunden".
// Zwilling von `schemas/working_hours_change.py` (`WorkingHoursChangeResponse`,
// `WorkingHoursChangePreview`). Die neuen Vorschau-Felder sind optional — eine
// ältere Antwort (oder ein Testdouble) muss sie nicht tragen.
import type { WeekBlocks } from '../../../types/workBlocks';

/** #431: eine Verlaufszeile ist ein vollständiger Vertrags-Snapshot ab `effective_from`. */
export interface WorkingHoursChange {
  id: string;
  user_id: string;
  effective_from: string;
  weekly_hours: number;
  use_daily_schedule?: boolean;
  hours_monday?: number | null;
  hours_tuesday?: number | null;
  hours_wednesday?: number | null;
  hours_thursday?: number | null;
  hours_friday?: number | null;
  work_days_per_week?: number | null;
  note?: string | null;
  created_at: string;
  /** Spec 11.1/11.5: locker gelesen — Altzeilen tragen 07:37/23:59 und Pause `null`. */
  blocks?: WeekBlocks | null;
}

/** Erfüllte Verkürzungskriterien (Spec 9.5 (a)/(b)/(c)). */
export type ShorteningReason = 'entries' | 'saldo' | 'absence_credit';

/** Ein neu gekappter Eintrag vorher/nachher (`TimeEntryChangeOut`); Zeiten "HH:MM:SS". */
export interface TimeEntryChange {
  entry_id: string;
  date: string;
  old_start: string | null;
  old_end: string | null;
  old_uncredited: number;
  old_net: number;
  new_start: string | null;
  new_end: string | null;
  new_uncredited: number;
  new_net: number;
  not_extendable: 'start' | 'end' | 'both' | null;
}

/** P22: geänderte ArbZG-Befunde im Wirkungsbereich (`ArbzgFindingsOut`). */
export interface ArbzgFindings {
  days_over_10_credited_before: number;
  days_over_10_credited_after: number;
  days_over_10_presence: number;
  weeks_over_48_credited_before: number;
  weeks_over_48_credited_after: number;
  weeks_over_48_presence: number;
}

export interface WorkingHoursChangePreview {
  is_retroactive: boolean;
  period_start: string;
  period_end: string;
  current_daily_target: number;
  new_daily_target: number;
  // #431: Tagessoll je Wochentag (Mo…Fr, immer fünf Einträge) vor und nach der Änderung.
  day_targets_current: number[];
  day_targets_new: number[];
  // #431: Überstundensaldo (Stichtag #313) und verbrauchte Urlaubstage des Jahres
  // von `period_start` — vorher und im simulierten Zustand nach dem Speichern.
  overtime_before: number;
  overtime_after: number;
  vacation_days_before: number;
  vacation_days_after: number;
  affected_absences: number;
  blocked_reason: string | null;
  closed_years: number[];
  closed_year_warning: string | null;
  // Spec 11.3 (neu)
  grace_minutes?: number;
  blocks_current?: WeekBlocks | null;
  blocks_new?: WeekBlocks | null;
  changed_weekdays?: number[];
  affected_time_entries?: number;
  time_entry_months?: { month: string; entries: number; net_before: number; net_after: number }[];
  time_entry_changes?: TimeEntryChange[];
  skipped_time_entries?: { entry_id: string; date: string; reason: string }[];
  not_extendable_count?: number;
  not_extendable_entries?: TimeEntryChange[];
  is_shortening?: boolean;
  shortening_reasons?: ShorteningReason[];
  shortening_closed_years?: number[];
  earliest_lossless_date?: string | null;
  earliest_lossless_note?: string | null;
  lost_credited_hours?: number;
  target_delta_hours?: number;
  credited_delta_hours?: number;
  saldo_delta_hours?: number;
  open_day_saldo_delta_hours?: number;
  absence_f1_adjustments?: number;
  absence_credit_reductions?: { absence_id: string; date: string; old_hours: number; new_hours: number }[];
  /** Nur `delete-preview`: fertiger Anlege-Body „auf vorherigen Stand zurücksetzen" (9.7). */
  reset_body?: Record<string, unknown> | null;
  stale_entries_closed?: number;
  arbzg_findings?: ArbzgFindings;
  milog_warning?: string[];
  block_break_notices?: string[];
}
