/** Shared time-math + layout constants for the weekly shift grid. */

export const GRID_START_HOUR = 6;
export const GRID_END_HOUR = 22;
export const HOUR_PX = 48; // pixel height of one hour row
export const SNAP_MINUTES = 15;

export const gridHeightPx = (GRID_END_HOUR - GRID_START_HOUR) * HOUR_PX;

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
}

export interface SlotBox {
  top: number;
  height: number;
  leftPct: number; // 0..100
  widthPct: number; // 0..100
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
        boxes[item.s.id] = {
          top: ((item.start - startHour * 60) / 60) * HOUR_PX,
          height: Math.max(18, ((item.end - item.start) / 60) * HOUR_PX),
          leftPct: (item.lane / lanes) * 100,
          widthPct: (1 / lanes) * 100,
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
