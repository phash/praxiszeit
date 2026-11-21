// Plan 2026-11-21 (Task 5): der Vertrags-Snapshot des Dialogs „Arbeitszeit &
// Wochenstunden" und seine Auflösung/Vergleichsform — aus `WorkingHoursModal.tsx`
// hierher verschoben, damit auch `utils/firstWorkDayHint.ts` dieselbe Definition
// von „gültiger Vertrag am Datum" und „hat sich etwas geändert" nutzt.
import { blocksOf, emptyWeek, isLegacyWeek } from '../../../utils/workBlocks';
import type { WeekBlocks } from '../../../types/workBlocks';
import type { ContractTerms, WorkingHoursChange } from './workingHoursTypes';

// #431: Die fünf Wochentagsfelder an EINER Stelle — Feldname (= API-Feld),
// Beschriftung des Eingabefelds und Kurzform.
export const DAY_FIELDS = [
  { key: 'hours_monday', label: 'Montag', short: 'Mo' },
  { key: 'hours_tuesday', label: 'Dienstag', short: 'Di' },
  { key: 'hours_wednesday', label: 'Mittwoch', short: 'Mi' },
  { key: 'hours_thursday', label: 'Donnerstag', short: 'Do' },
  { key: 'hours_friday', label: 'Freitag', short: 'Fr' },
] as const;

export type DayFieldKey = typeof DAY_FIELDS[number]['key'];

/** Spec 12.1: „Gleichmäßig" / „Nach Tagen" / „Nach Arbeitsblöcken". */
export type Mode = 'even' | 'days' | 'blocks';

/** #431 + Spec 3.1: der Vertrags-Snapshot, wie ihn Dialog und Backend sehen. */
export interface ScheduleSnapshot {
  weekly_hours: number;
  use_daily_schedule: boolean;
  /** Fünf Werte, Index 0 = Montag. 0 = kein geplanter Arbeitstag (wie `null`). */
  day_hours: number[];
  work_days_per_week: number;
  /** Blöcke der Zeile — neu (mit Pausen) oder Altfenster (Pausen NULL) — oder `null`. */
  blocks: WeekBlocks | null;
  /** Teil A: Urlaubsanspruch, Stundenzählung und Minijob-Felder der Zeile. */
  contract: ContractTerms;
}

export interface FormState {
  effective_from: string;
  mode: Mode;
  weekly_hours: number;
  hours_monday: number;
  hours_tuesday: number;
  hours_wednesday: number;
  hours_thursday: number;
  hours_friday: number;
  work_days_per_week: number;
  blocks: WeekBlocks;
  /** P2: Altfenster ausdrücklich entfernen statt übernehmen. */
  remove_legacy_window: boolean;
  note: string;
  /** Teil A: von der Admin geänderte Vertragsfelder. Was hier fehlt, folgt dem
   * Stand am Wirkungsdatum (der Anspruch dem Vorschlag, solange es einen gibt). */
  contract_edits: Partial<ContractTerms>;
}

export function round2(value: number): number {
  return Number.isFinite(value) ? Math.round(value * 100) / 100 : 0;
}

export function normaliseDayHours(values: (number | null | undefined)[]): number[] {
  return DAY_FIELDS.map((_, i) => {
    const v = values[i];
    return typeof v === 'number' && Number.isFinite(v) ? v : 0;
  });
}

/** Die fünf Tageswerte eines Snapshots als Formularfelder. */
export function dayFieldsFromSnapshot(dayHours: number[]): Record<DayFieldKey, number> {
  return {
    hours_monday: dayHours[0],
    hours_tuesday: dayHours[1],
    hours_wednesday: dayHours[2],
    hours_thursday: dayHours[3],
    hours_friday: dayHours[4],
  };
}

export function hasNewBlocks(week: WeekBlocks | null): boolean {
  return Array.isArray(week) && !isLegacyWeek(week);
}

export function hasLegacyBlocks(week: WeekBlocks | null): boolean {
  return Array.isArray(week) && isLegacyWeek(week);
}

/** Teil A: die fünf Vertragsfelder einer Zeile; was eine ältere Antwort nicht
 * trägt, kommt aus dem Rückfall. */
export function contractFromChange(change: WorkingHoursChange, fallback: ContractTerms): ContractTerms {
  return {
    vacation_days: change.vacation_days ?? fallback.vacation_days,
    track_hours: change.track_hours ?? fallback.track_hours,
    milog_working_time_account: change.milog_working_time_account ?? fallback.milog_working_time_account,
    agreed_monthly_hours: change.agreed_monthly_hours !== undefined
      ? change.agreed_monthly_hours
      : fallback.agreed_monthly_hours,
    use_fixed_monthly_target: change.use_fixed_monthly_target ?? fallback.use_fixed_monthly_target,
  };
}

export function scheduleFromChange(change: WorkingHoursChange, fallback: ScheduleSnapshot): ScheduleSnapshot {
  const fallbackWorkDays = fallback.work_days_per_week;
  return {
    weekly_hours: change.weekly_hours,
    use_daily_schedule: !!change.use_daily_schedule,
    day_hours: normaliseDayHours([
      change.hours_monday, change.hours_tuesday, change.hours_wednesday,
      change.hours_thursday, change.hours_friday,
    ]),
    // NULL heißt beim Backend „Rückfall auf die User-Zeile" (Bestandszeilen vor
    // #431) — hier ist das die Prop.
    work_days_per_week: change.work_days_per_week ?? fallbackWorkDays,
    blocks: Array.isArray(change.blocks) ? change.blocks : null,
    contract: contractFromChange(change, fallback.contract),
  };
}

// Fund 3 (Release-Review 1.17.0), #431: der zu einem Datum gültige Snapshot
// kommt aus dem geladenen Verlauf (jüngste Zeile mit effective_from <= datum),
// nicht aus den Props — die sind ein Stand von vor dem Öffnen des Dialogs und
// werden von Users.tsx nach dem Speichern nicht nachgezogen. Genau die
// Auflösung von `calculation_service.get_schedule_for_date`.
export function scheduleAt(
  changes: WorkingHoursChange[], iso: string, fallback: ScheduleSnapshot,
): ScheduleSnapshot {
  let latest: WorkingHoursChange | null = null;
  let earliest: WorkingHoursChange | null = null;
  for (const c of changes) {
    if (c.effective_from <= iso && (!latest || c.effective_from > latest.effective_from)) {
      latest = c;
    }
    if (!earliest || c.effective_from < earliest.effective_from) earliest = c;
  }
  if (latest) return scheduleFromChange(latest, fallback);
  // Teil A (Auflösungsregel der fünf Vertragsfelder): vor der ersten Zeile gilt
  // deren Vertrag; die Stunden bleiben beim Rückfall (User-Zeile).
  return earliest ? { ...fallback, contract: contractFromChange(earliest, fallback.contract) } : fallback;
}

/** Kanonische Vergleichsform der Blöcke (Schlüsselreihenfolge egal). Ein
 * fehlender „blocks"-Schlüssel heißt „keine Blöcke" (`blocksOf`) — der Server
 * gibt eine solche Verlaufszeile unverändert aus (Gesamtreview B3). */
export function blocksKey(week: WeekBlocks | null): string | null {
  if (!Array.isArray(week)) return null;
  return JSON.stringify(week.map((d) => [blocksOf(d).map((b) => [b.start, b.end]), d?.pause_minutes ?? null]));
}

/**
 * #431 + Spec 12.1: DIE Definition von „hat sich etwas geändert" — wie
 * `admin_users._comparable_snapshot`, jetzt mit Blöcken und Pausen.
 *
 * Im gleichmäßigen Modus sind die Tageswerte inert (das Tagessoll liest sie
 * dort nicht) und werden ausgeblendet, sonst täuschte ein Rest aus einer
 * früheren Tagesplan-Phase eine Änderung vor. Ohne Stundenzählung zählen die
 * Blöcke nicht (sie wirken nicht; beendet werden sie von jeder echten
 * Änderung, P24) — außer beim ausdrücklichen Entfernen eines Altfensters
 * (`compareBlocks` im Aufrufer).
 *
 * Review Focus 5: verglichen wird über die auf 0,01 h gerundeten Tageswerte —
 * 7:55 h im Editor ist gespeichert 7,92 h, beides ist derselbe Stand.
 */
export function comparableSnapshot(s: ScheduleSnapshot, withBlocks: boolean): string {
  return JSON.stringify([
    round2(s.weekly_hours),
    s.use_daily_schedule,
    s.use_daily_schedule ? s.day_hours.map(round2) : [0, 0, 0, 0, 0],
    s.work_days_per_week,
    withBlocks ? blocksKey(s.blocks) : null,
    // Teil A: auch eine reine Vertragsänderung (Anspruch, Stundenzählung,
    // Minijob) ist eine Änderung.
    Number.isFinite(s.contract.vacation_days) ? Math.round(s.contract.vacation_days * 10) / 10 : null,
    s.contract.track_hours,
    s.contract.milog_working_time_account,
    s.contract.agreed_monthly_hours == null ? null : Math.round(s.contract.agreed_monthly_hours * 10) / 10,
    s.contract.use_fixed_monthly_target,
  ]);
}

/** Formularstand aus einem Snapshot: Block-Modus, sobald neue Blöcke gelten
 * (und Stunden gezählt werden, P24). */
export function formFromSnapshot(s: ScheduleSnapshot, effectiveFrom: string): FormState {
  const blocksMode = s.contract.track_hours && hasNewBlocks(s.blocks);
  return {
    effective_from: effectiveFrom,
    mode: blocksMode ? 'blocks' : s.use_daily_schedule ? 'days' : 'even',
    weekly_hours: s.weekly_hours,
    ...dayFieldsFromSnapshot(s.day_hours),
    work_days_per_week: s.work_days_per_week,
    blocks: blocksMode && s.blocks ? s.blocks : emptyWeek(),
    remove_legacy_window: false,
    note: '',
    contract_edits: {},
  };
}
