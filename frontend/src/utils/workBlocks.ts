// Spec 2026-10-08: Anzeige-Helfer für Arbeitszeit-Blöcke. PR2/PR3 ergänzen hier
// die Zwillinge der Backend-Rechenhelfer (notCreditedMinutes, gapSegments,
// deriveTargets) — jeweils mit wortgleichen Testfällen.
import type { TimeBlock, WeekBlocks } from '../types/workBlocks';

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

const LAST_MINUTE = 23 * 60 + 59;

/** "HH:MM" bzw. "HH:MM:SS" → Minuten seit Mitternacht (Sekunden ignoriert, wie im Backend). */
export function hhmmToMinutes(value: string): number {
  const [h, m] = value.substring(0, 5).split(':').map(Number);
  return h * 60 + m;
}

function sortedMinutes(blocks: TimeBlock[]): [number, number][] {
  return blocks
    .map((b) => [hhmmToMinutes(b.start), hhmmToMinutes(b.end)] as [number, number])
    .sort((a, b) => a[0] - b[0]);
}

/**
 * Zwilling von `work_window_service.gap_segments` (Spec 6.1/8.4): die nicht
 * angerechneten Minuten je Lücke für einen Eintrag `start`–`end` an einem Tag
 * mit `blocks`. Beginn/Ende werden auf die Hülle (erster Block − Puffer, letzter
 * Block + Puffer) begrenzt; die Lücken schrumpfen an beiden Rändern um den
 * Puffer, eine Lücke ≤ 2 × Puffer verschwindet. Kollaps außerhalb der Hülle → [].
 */
export function gapSegments(
  blocks: TimeBlock[] | null | undefined, grace: number, start: string, end: string,
): number[] {
  if (!blocks || blocks.length === 0) return [];
  const mins = sortedMinutes(blocks);
  const floor = Math.max(0, Math.min(mins[0][0] - grace, LAST_MINUTE));
  const ceil = Math.max(0, Math.min(mins[mins.length - 1][1] + grace, LAST_MINUTE));
  const s = Math.max(hhmmToMinutes(start), floor);
  const e = Math.min(hhmmToMinutes(end), ceil);
  if (s >= e) return [];
  const out: number[] = [];
  for (let i = 0; i + 1 < mins.length; i++) {
    const gs = mins[i][1] + grace;
    const ge = mins[i + 1][0] - grace;
    if (ge <= gs) continue;
    const overlap = Math.min(e, ge) - Math.max(s, gs);
    if (overlap > 0) out.push(overlap);
  }
  return out;
}

/** Spec 14 / E69: liegt `minutes` in einer UNGESCHRUMPFTEN Lücke (Ende Block i
 * bis Beginn Block i+1)? Laut Plan beginnt die Pause am Blockende, nicht erst
 * nach dem Puffer — der geschrumpfte Wert gilt nur für die Anrechnung. */
export function isInBlockGap(blocks: TimeBlock[] | null | undefined, minutes: number): boolean {
  if (!blocks || blocks.length < 2) return false;
  const mins = sortedMinutes(blocks);
  for (let i = 0; i + 1 < mins.length; i++) {
    if (mins[i][1] <= minutes && minutes < mins[i + 1][0]) return true;
  }
  return false;
}

/** Erster Beginn bis letztes Ende (Vorbelegung neuer Einträge, Spec 14).
 * `null` ohne Blöcke UND bei den Platzhaltern halboffener Altfenster (Spec 5.3):
 * Ende 23:59 heißt „kein Ende" (neue Zeilen enden spätestens 23:55, Spec 3.5),
 * Beginn 00:00 heißt „kein Beginn" — wie im Backend (`_clamp_core` kappt das
 * Ende nur bei `blocks[-1][1] < _LAST_MINUTE`). Der Aufrufer behält dann seine
 * bisherige Vorbelegung; sonst stünde 07:30–23:59 im Formular (→ DAILY_HOURS_HARD). */
export function blocksSpan(blocks: TimeBlock[] | null | undefined): { start: string; end: string } | null {
  if (!blocks || blocks.length === 0) return null;
  const mins = sortedMinutes(blocks);
  const first = mins[0][0];
  const last = Math.max(...mins.map(([, e]) => e));
  if (first === 0 || last === LAST_MINUTE) return null;
  const toHHMM = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  return { start: toHHMM(first), end: toHHMM(last) };
}

export interface CreditEntry {
  start_time: string | null;
  end_time: string | null;
  raw_start_time?: string | null;
  raw_end_time?: string | null;
  uncredited_minutes?: number | null;
  auto_closed?: boolean | null;
}

/** Zwilling von `work_window_service.not_credited_minutes` (P19): Lücke +
 * von der Hülle gekappte Minuten; die Endseite eines automatisch geschlossenen
 * Eintrags zählt nicht (23:59 ist kein Stempel, P18). */
export function notCreditedMinutes(e: CreditEntry): number {
  let total = e.uncredited_minutes ?? 0;
  if (e.start_time && e.raw_start_time) {
    total += Math.max(0, hhmmToMinutes(e.start_time) - hhmmToMinutes(e.raw_start_time));
  }
  if (e.end_time && e.raw_end_time && !e.auto_closed) {
    total += Math.max(0, hhmmToMinutes(e.raw_end_time) - hhmmToMinutes(e.end_time));
  }
  return total;
}

export interface StampEntry extends CreditEntry {
  break_minutes?: number | null;
  net_hours?: number | null;
  not_credited_minutes?: number | null;
  credit_override?: boolean | null;
}

/** Spec 13.1: die Eingaben der Komponente `RawStampNote`. */
export interface StampNoteData {
  uncreditedMinutes: number;
  notCreditedMinutes: number;
  rawSpan: string;       // "08:00–18:00" aus raw_* oder start/end; offen: "07:00–"
  effSpan: string;       // gespeicherte start/end
  creditedHours: number; // net_hours (nach Pause und Lücke)
  breakMinutes: number;
  autoClosed: boolean;
  creditOverride: boolean;
}

export function stampNoteProps(e: StampEntry): StampNoteData {
  const hhmm = (t?: string | null) => (t ? t.substring(0, 5) : '');
  return {
    uncreditedMinutes: e.uncredited_minutes ?? 0,
    notCreditedMinutes: e.not_credited_minutes ?? notCreditedMinutes(e),
    rawSpan: `${hhmm(e.raw_start_time ?? e.start_time)}–${hhmm(e.raw_end_time ?? e.end_time)}`,
    effSpan: `${hhmm(e.start_time)}–${hhmm(e.end_time)}`,
    creditedHours: e.net_hours ?? 0,
    breakMinutes: e.break_minutes ?? 0,
    autoClosed: !!e.auto_closed,
    creditOverride: !!e.credit_override,
  };
}
