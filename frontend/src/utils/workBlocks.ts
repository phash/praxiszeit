// Spec 2026-10-08: Anzeige-Helfer für Arbeitszeit-Blöcke. PR2/PR3 ergänzen hier
// die Zwillinge der Backend-Rechenhelfer (notCreditedMinutes, gapSegments,
// deriveTargets) — jeweils mit wortgleichen Testfällen.
import type { WeekBlocks } from '../types/workBlocks';

export const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr'] as const;

/** Spec 3.3: eine Altzeile (aus Migration 073) trägt an mindestens einem Tag
 * keine Pausenangabe (`pause_minutes === null`). */
export function isLegacyWeek(week: WeekBlocks | null | undefined): boolean {
  return Array.isArray(week) && week.some((day) => day?.pause_minutes === null);
}

/** „Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00" — nur Tage
 * mit Blöcken, „(Pause …)" nur bei Pause > 0; `null`, wenn kein Tag Blöcke hat.
 * Altwerte (07:37, Platzhalter 23:59) werden unverändert angezeigt (Spec 4.4). */
export function formatWeekBlocks(week: WeekBlocks | null | undefined): string | null {
  if (!Array.isArray(week)) return null;
  const parts = week.flatMap((day, index) => {
    const blocks = day?.blocks ?? [];
    if (blocks.length === 0 || index >= WEEKDAY_LABELS.length) return [];
    const spans = blocks.map((block) => `${block.start}–${block.end}`).join(' + ');
    const pause = day.pause_minutes ? ` (Pause ${day.pause_minutes} Min)` : '';
    return [`${WEEKDAY_LABELS[index]} ${spans}${pause}`];
  });
  return parts.length > 0 ? parts.join(' · ') : null;
}
