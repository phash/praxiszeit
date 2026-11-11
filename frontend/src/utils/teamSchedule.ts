// 1.21 Teamübersicht der Arbeitszeiten: reine Rechenhelfer für Ziehen,
// Zeitachse und Besetzung. Geschrieben wird nie von hier — eine geänderte Woche
// geht als Entwurf in den Dialog „Arbeitszeit anpassen…“ (Stichtag, Vorschau).
import type { WeekBlocks } from '../types/workBlocks';
import { blocksOf, hhmmToMinutes } from './workBlocks';

/** Raster beim Ziehen. Feinere Zeiten (5 Min.) gibt es im Dialog. */
export const DRAG_SNAP_MINUTES = 15;
/** Späteste Blockgrenze (Spec 3.5: Blöcke enden spätestens 23:55). */
const DAY_END = 23 * 60 + 55;
const MIN_BLOCK = 15;
/** Blöcke dürfen sich nicht berühren (Spec 3.4) — kleinster Abstand im 5-Min-Raster. */
const MIN_GAP = 5;

function toHHMM(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function snapMinutes(minutes: number, snap = DRAG_SNAP_MINUTES): number {
  return Math.round(minutes / snap) * snap || 0;
}

function withBlock(week: WeekBlocks, day: number, idx: number, start: number, end: number): WeekBlocks {
  return week.map((d, i) => (i !== day ? d : {
    ...d,
    blocks: blocksOf(d).map((b, j) => (j === idx ? { start: toHHMM(start), end: toHHMM(end) } : b)),
  }));
}

/** Spielraum von Block `idx`: vom Ende des vorigen bis zum Beginn des
 * nächsten Blocks (je 5 Min. Abstand), sonst 00:00 bzw. 23:55. */
function bounds(week: WeekBlocks, day: number, idx: number): { lo: number; hi: number } {
  const s = hhmmToMinutes(blocksOf(week[day])[idx].start);
  let lo = 0;
  let hi = DAY_END;
  blocksOf(week[day]).forEach((o, j) => {
    if (j === idx) return;
    const os = hhmmToMinutes(o.start);
    const oe = hhmmToMinutes(o.end);
    if (oe <= s) lo = Math.max(lo, oe + MIN_GAP);
    else hi = Math.min(hi, os - MIN_GAP);
  });
  return { lo, hi };
}

/** Block `idx` am Tag `day` um `delta` Minuten verschieben; Dauer bleibt. Der
 * Block bleibt im Tag (00:00–23:55) und hält 5 Min. Abstand zu den Nachbarn. */
export function moveBlock(week: WeekBlocks, day: number, idx: number, delta: number): WeekBlocks {
  const b = blocksOf(week[day])[idx];
  const s = hhmmToMinutes(b.start);
  const e = hhmmToMinutes(b.end);
  const len = e - s;
  const { lo, hi } = bounds(week, day, idx);
  const start = Math.max(lo, Math.min(s + delta, hi - len));
  return withBlock(week, day, idx, start, start + len);
}

/** Beginn oder Ende von Block `idx` um `delta` Minuten ziehen (mindestens 15 Min. Dauer). */
export function resizeBlock(
  week: WeekBlocks, day: number, idx: number, edge: 'start' | 'end', delta: number,
): WeekBlocks {
  const b = blocksOf(week[day])[idx];
  const s = hhmmToMinutes(b.start);
  const e = hhmmToMinutes(b.end);
  const { lo, hi } = bounds(week, day, idx);
  if (edge === 'start') return withBlock(week, day, idx, Math.min(Math.max(lo, s + delta), e - MIN_BLOCK), e);
  return withBlock(week, day, idx, s, Math.max(Math.min(hi, e + delta), s + MIN_BLOCK));
}

/** Kurzbeschriftung im Balken: „8–12", „7:30–13", „14:30–18:45". */
export function compactSpan(start: string, end: string): string {
  const short = (t: string) => {
    const [h, m] = t.slice(0, 5).split(':');
    return m === '00' ? String(Number(h)) : `${Number(h)}:${m}`;
  };
  return `${short(start)}–${short(end)}`;
}

/** Zeitachse in Minuten: volle Stunden um alle Blöcke, mindestens 07–19 Uhr. */
export function axisRange(weeks: (WeekBlocks | null | undefined)[]): { start: number; end: number } {
  let lo = 7 * 60;
  let hi = 19 * 60;
  for (const w of weeks) {
    for (const d of w ?? []) {
      for (const b of blocksOf(d)) {
        lo = Math.min(lo, hhmmToMinutes(b.start));
        hi = Math.max(hi, hhmmToMinutes(b.end));
      }
    }
  }
  return { start: Math.floor(lo / 60) * 60, end: Math.min(24 * 60, Math.ceil(hi / 60) * 60) };
}

/** Besetzung am Tag `day`: je Fenster `[from + i·slot, from + (i+1)·slot)` die
 * Zahl der Personen, deren Block das Fenster schneidet. */
export function coverage(
  weeks: (WeekBlocks | null | undefined)[], day: number, from: number, to: number, slot = 30,
): number[] {
  const counts: number[] = [];
  for (let t = from; t < to; t += slot) {
    counts.push(weeks.filter((w) => blocksOf(w?.[day]).some(
      (b) => hhmmToMinutes(b.start) < t + slot && hhmmToMinutes(b.end) > t,
    )).length);
  }
  return counts;
}

/** Abteilungen der Liste (Filter „Alle“ + je Abteilung), sortiert, ohne Leerwerte. */
export function departmentsOf(rows: { department?: string | null }[]): string[] {
  const set = new Set(rows.map((r) => (r.department ?? '').trim()).filter(Boolean));
  return Array.from(set).sort((a, b) => a.localeCompare(b, 'de'));
}

/** Gleiche Blöcke und Pausen? (Entwurf geändert ja/nein) */
export function sameWeek(a: WeekBlocks | null | undefined, b: WeekBlocks | null | undefined): boolean {
  const key = (w: WeekBlocks | null | undefined) => (Array.isArray(w)
    ? JSON.stringify(w.map((d) => [blocksOf(d).map((x) => [x.start, x.end]), d?.pause_minutes ?? null]))
    : null);
  return key(a) === key(b);
}

/** Untere Grenze der Tagesfeld-Breite (px, Rückfall ohne Messung). Herleitung aus TeamSchedule.tsx:
 * Raster `min-w-[56rem]` (896 px) − Personenspalte `14rem` (224 px) = 672 px /
 * 5 Tage = 134,4 px je Tag; abzüglich `border-l` (1 px) und `inset-x-2`
 * (2 × 8 px) bleiben ≈ 117 px. Darunter scrollt das Raster, die Spalte wird
 * also nie schmaler. Ändert sich das Layout, hier mitziehen. */
export const MIN_COLUMN_PX = 117;

/** Nutzbare Breite des Tagesfelds aus der gemessenen Breite des Rasters:
 * (Breite − Personenspalte 14rem = 224 px) / 5 Tage − `border-l` − `inset-x-2`. */
export function dayColumnPx(gridWidth: number): number {
  return Math.max(MIN_COLUMN_PX, (gridWidth - 224) / 5 - 17);
}
/** Zeichenbreite bei 11 px Schrift, großzügig (Ziffern ≈ 6,1 px, Gedankenstrich ≈ 6 px). */
const CHAR_PX = 7;
/** Innenabstand des Balkens: `px-1` (2 × 4 px) + Rahmen (2 × 1 px). */
const LABEL_PAD_PX = 10;

/** Beschriftung eines Balkens je nach Breite (reine Minutenrechnung, kein
 * DOM-Messen): breit → „13–16:30“, mittel → nur der Beginn mit Strich „13–“, schmal → leer.
 * `columnPx` = gemessene Breite des Tagesfelds (`dayColumnPx`), ohne Messung
 * die Mindestbreite. Die volle Zeit steht immer in `title`/`aria-label`. */
export function blockLabel(start: string, end: string, spanMinutes: number, axisMinutes: number,
  columnPx: number = MIN_COLUMN_PX): string {
  const px = (spanMinutes / axisMinutes) * columnPx - LABEL_PAD_PX;
  const full = compactSpan(start, end);
  if (px >= full.length * CHAR_PX) return full;
  const from = `${full.split('–')[0]}–`;
  if (px >= from.length * CHAR_PX) return from;
  return '';
}
