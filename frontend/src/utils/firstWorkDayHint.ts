// Plan 2026-11-21 (Task 5, Spec Teil 1): Gilt die heutige Arbeitszeit erst ab
// einem Datum NACH dem ersten Arbeitstag, obwohl es außer ihr keine echte
// Änderung gibt, bietet der Dialog „Ab {erster Arbeitstag} übernehmen" an.
//
// Fall A (noch nichts gespeichert): kein Verlauf außer der automatisch erfassten
//   Ausgangszeile, und das gewählte Wirkungsdatum liegt nach dem ersten
//   Arbeitstag → das Formular bleibt, nur das Datum wird vorgezogen.
// Fall B (schon gespeichert, der Kundenfall): genau eine echte Zeile, nach dem
//   ersten Arbeitstag, und ihr Vertrag weicht von dem am ersten Arbeitstag ab
//   → `source` ist diese Zeile; das Formular übernimmt ihren Vertrag.
// Die Ausgangszeile erkennt das Frontend allein an `is_baseline` (kein Textvergleich).
import { dayBefore } from '../pages/admin/users/workingHoursTexts';
import {
  comparableSnapshot, scheduleAt, scheduleFromChange, type ScheduleSnapshot,
} from '../pages/admin/users/workingHoursSnapshot';
import type { WorkingHoursChange } from '../pages/admin/users/workingHoursTypes';

export interface FirstWorkDayHint {
  /** Neues Wirkungsdatum = erster Arbeitstag. */
  applyFrom: string;
  /** Letzter Tag, an dem noch der Vertrag vom Anlegen gilt. */
  until: string;
  /** Fall B: die zu übernehmende Zeile; Fall A: `null` (Formular bleibt). */
  source: WorkingHoursChange | null;
  /** Der Vertrag am ersten Arbeitstag (für den Klartext im Hinweis). */
  startSchedule: ScheduleSnapshot;
}

/**
 * `fallback` ist der Vertrag aus den Props des Dialogs — derselbe Rückfall wie
 * überall in `scheduleAt` (vor der ersten Verlaufszeile gilt die User-Zeile).
 */
export function firstWorkDayHint(
  firstWorkDay: string | null | undefined,
  changes: WorkingHoursChange[],
  effectiveFrom: string,
  fallback: ScheduleSnapshot,
): FirstWorkDayHint | null {
  if (!firstWorkDay || !effectiveFrom || effectiveFrom <= firstWorkDay) return null;
  const real = changes.filter((c) => !c.is_baseline);
  const startSchedule = scheduleAt(changes, firstWorkDay, fallback);

  if (real.length === 0) {
    return { applyFrom: firstWorkDay, until: dayBefore(effectiveFrom), source: null, startSchedule };
  }
  if (real.length !== 1) return null;
  const source = real[0];
  if (source.effective_from <= firstWorkDay) return null;
  const sourceSchedule = scheduleFromChange(source, fallback);
  // Blöcke zählen nur mit Stundenzählung (P24) — wie der Vergleich im Dialog.
  const withBlocks = sourceSchedule.contract.track_hours || startSchedule.contract.track_hours;
  if (comparableSnapshot(sourceSchedule, withBlocks) === comparableSnapshot(startSchedule, withBlocks)) return null;
  return { applyFrom: firstWorkDay, until: dayBefore(source.effective_from), source, startSchedule };
}
