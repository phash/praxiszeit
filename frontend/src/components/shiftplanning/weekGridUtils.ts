/** Shared time-math + layout constants for the weekly shift grid. */

export const GRID_START_HOUR = 6;
export const GRID_END_HOUR = 22;
export const HOUR_PX = 48; // pixel height of one hour row
export const SNAP_MINUTES = 15;

// #443: Grundlage der Schätzung, wie hoch ein Block seinem INHALT nach wäre.
// Sie steuert ausschließlich die Markierung "reicht über das Zeitfenster
// hinaus" — das tatsächliche Wachsen erledigt das CSS (minHeight statt height).
// Deshalb ist eine Schätzung hier ausreichend und einer DOM-Messung vorzuziehen:
// die Funktion bleibt rein, prüfbar und über alle Browser gleich.
export const LINE_PX = 14;
export const BLOCK_PADDING_PX = 8; // p-1 oben + unten
export const NOTE_CHARS_PER_LINE = 20;

export const gridHeightPx = (GRID_END_HOUR - GRID_START_HOUR) * HOUR_PX;

// #371: default planner weekdays (Mo–Fr) when no config is available.
export const DEFAULT_WEEKDAYS = [0, 1, 2, 3, 4];

/**
 * Which weekday columns the grid renders (0=Mo … 6=So).
 * - `singleDay` (Tagesansicht #321) always wins — exactly that one day.
 * - otherwise the configured `weekdays`, sorted; empty/undefined → Mo–Fr.
 */
export function visibleWeekdays(singleDay: number | undefined, weekdays: number[] | undefined): number[] {
  if (singleDay !== undefined) return [singleDay];
  if (weekdays && weekdays.length > 0) return [...weekdays].sort((a, b) => a - b);
  return [...DEFAULT_WEEKDAYS];
}

export function timeToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

export function minutesToTime(min: number): string {
  const clamped = Math.max(0, Math.min(24 * 60 - 1, min));
  const h = Math.floor(clamped / 60);
  const m = clamped % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function snap(min: number, step = SNAP_MINUTES): number {
  return Math.round(min / step) * step;
}

/** Top offset (px) for a given HH:MM, relative to the grid start. */
export function topForTime(hhmm: string): number {
  return ((timeToMinutes(hhmm) - GRID_START_HOUR * 60) / 60) * HOUR_PX;
}

/** Block height (px) for a start/end pair (min 18px so labels stay legible). */
export function heightForRange(start: string, end: string): number {
  const px = ((timeToMinutes(end) - timeToMinutes(start)) / 60) * HOUR_PX;
  return Math.max(18, px);
}

/** Convert a vertical pixel delta into a snapped minutes delta. */
export function pxDeltaToMinutes(deltaPx: number): number {
  return snap((deltaPx / HOUR_PX) * 60);
}

export const HOUR_MARKS = Array.from(
  { length: GRID_END_HOUR - GRID_START_HOUR + 1 },
  (_, i) => GRID_START_HOUR + i,
);

/** A readable default palette for workstations without an explicit colour. */
export const DEFAULT_WS_COLORS = [
  '#2563eb',
  '#16a34a',
  '#db2777',
  '#d97706',
  '#7c3aed',
  '#0891b2',
  '#dc2626',
  '#4b5563',
];

export function colorForWorkstation(color: string | null, fallbackIndex: number): string {
  return color || DEFAULT_WS_COLORS[fallbackIndex % DEFAULT_WS_COLORS.length];
}

/**
 * Monday (YYYY-MM-DD) of the ISO week containing the given YYYY-MM-DD date.
 *
 * Uses LOCAL date components only — it must NOT round-trip through
 * `toISOString()`, which converts local midnight to UTC and rolls a UTC+
 * timezone (e.g. Europe/Berlin) back to the previous day → the wrong week
 * (#305 M2 Auto-Generierung).
 */
export function mondayOfWeek(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  const dow = (d.getDay() + 6) % 7; // 0 = Monday … 6 = Sunday
  d.setDate(d.getDate() - dow);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ── layout engine ─────────────────────────────────────────────────────
// Computes a per-weekday side-by-side ("lane") layout so that concurrent
// slots (e.g. two workstations staffed in parallel) render next to each other
// instead of stacked on top of one another, plus a time window that expands to
// include any slot outside the default 06:00–22:00 range (so nothing renders
// off-grid).

export interface SlotLike {
  id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  // #443: für die Inhaltsschätzung. Optional, damit die reinen Zeit-Tests und
  // ältere Aufrufer unverändert weiterlaufen.
  assignments?: unknown[];
  note?: string | null;
}

export interface SlotBox {
  top: number;
  height: number; // zeitproportional — bleibt die Aussage über die Uhrzeit
  leftPct: number; // 0..100
  widthPct: number; // 0..100
  // #443
  contentHeight: number;
  grown: boolean; // contentHeight > height → Blockhöhe meint nicht mehr die Uhrzeit
}

/**
 * Geschätzte Höhe, die der INHALT eines Blocks braucht (#443).
 *
 * Gezählt werden: die Kopfzeile (Arbeitsplatz), die Zeitzeile, eine Zeile je
 * zugewiesener Person — mindestens eine, weil dort sonst "0/2" oder "—" steht —
 * und der Hinweis in Zeilen zu ``NOTE_CHARS_PER_LINE`` Zeichen.
 *
 * Das Ergebnis ist eine **Untergrenze**: bricht ein langer Name in einer sehr
 * schmalen Spur auf zwei Zeilen um, wächst der Block korrekt, bleibt aber
 * womöglich ohne Markierung. Das ist hingenommen — die Markierung ist ein
 * Hinweis, keine Zusicherung. Der umgekehrte Fehler (Markierung ohne Wachstum)
 * kann nicht auftreten.
 */
export function estimateContentHeight(slot: SlotLike): number {
  const nameLines = Math.max(1, slot.assignments?.length ?? 0);
  const note = (slot.note ?? '').trim();
  const noteLines = note ? Math.ceil(note.length / NOTE_CHARS_PER_LINE) : 0;
  const lines = 1 /* Arbeitsplatz */ + 1 /* Zeit */ + nameLines + noteLines;
  return lines * LINE_PX + BLOCK_PADDING_PX;
}

export interface WeekLayout {
  startHour: number;
  endHour: number;
  height: number;
  hourMarks: number[];
  boxes: Record<string, SlotBox>;
}

export function computeWeekLayout(slots: SlotLike[]): WeekLayout {
  let minStart = GRID_START_HOUR * 60;
  let maxEnd = GRID_END_HOUR * 60;
  for (const s of slots) {
    minStart = Math.min(minStart, timeToMinutes(s.start_time));
    maxEnd = Math.max(maxEnd, timeToMinutes(s.end_time));
  }
  const startHour = Math.floor(minStart / 60);
  const endHour = Math.max(startHour + 1, Math.ceil(maxEnd / 60));
  const height = (endHour - startHour) * HOUR_PX;
  const hourMarks = Array.from({ length: endHour - startHour + 1 }, (_, i) => startHour + i);

  const boxes: Record<string, SlotBox> = {};

  for (let wd = 0; wd < 7; wd++) {
    const day = slots
      .filter((s) => s.weekday === wd)
      .map((s) => ({ s, start: timeToMinutes(s.start_time), end: timeToMinutes(s.end_time) }))
      .sort((a, b) => a.start - b.start || a.end - b.end);

    // Split the day into maximal overlap groups; lane-pack each group so its
    // width is divided only among the slots that actually overlap there.
    let group: { s: SlotLike; start: number; end: number; lane: number }[] = [];
    let groupMaxEnd = -1;
    let laneEnds: number[] = [];

    const flush = () => {
      const lanes = Math.max(1, laneEnds.length);
      for (const item of group) {
        const height = Math.max(18, ((item.end - item.start) / 60) * HOUR_PX);
        const contentHeight = estimateContentHeight(item.s);
        boxes[item.s.id] = {
          top: ((item.start - startHour * 60) / 60) * HOUR_PX,
          height,
          leftPct: (item.lane / lanes) * 100,
          widthPct: (1 / lanes) * 100,
          contentHeight,
          grown: contentHeight > height,
        };
      }
      group = [];
      laneEnds = [];
      groupMaxEnd = -1;
    };

    for (const it of day) {
      if (group.length && it.start >= groupMaxEnd) flush();
      let lane = laneEnds.findIndex((e) => e <= it.start);
      if (lane === -1) {
        lane = laneEnds.length;
        laneEnds.push(it.end);
      } else {
        laneEnds[lane] = it.end;
      }
      group.push({ ...it, lane });
      groupMaxEnd = Math.max(groupMaxEnd, it.end);
    }
    if (group.length) flush();
  }

  return { startHour, endHour, height, hourMarks, boxes };
}
