import { describe, it, expect } from 'vitest';
import {
  timeToMinutes,
  minutesToTime,
  snap,
  topForTime,
  heightForRange,
  pxDeltaToMinutes,
  colorForWorkstation,
  mondayOfWeek,
  computeWeekLayout,
  visibleWeekdays,
  estimateContentHeight,
  type SlotLike,
  GRID_START_HOUR,
  HOUR_PX,
  DEFAULT_WS_COLORS,
} from './weekGridUtils';

const slot = (id: string, weekday: number, start_time: string, end_time: string): SlotLike => ({
  id,
  weekday,
  start_time,
  end_time,
});

describe('weekGridUtils time math', () => {
  it('round-trips HH:MM through minutes', () => {
    expect(timeToMinutes('08:00')).toBe(480);
    expect(timeToMinutes('14:30')).toBe(870);
    expect(minutesToTime(480)).toBe('08:00');
    expect(minutesToTime(870)).toBe('14:30');
  });

  it('zero-pads single-digit hours/minutes', () => {
    expect(minutesToTime(9 * 60 + 5)).toBe('09:05');
  });

  it('clamps minutesToTime into a valid day range', () => {
    expect(minutesToTime(-30)).toBe('00:00');
    expect(minutesToTime(24 * 60 + 100)).toBe('23:59');
  });

  it('snaps to 15-minute increments', () => {
    expect(snap(7)).toBe(0);
    expect(snap(8)).toBe(15);
    expect(snap(485)).toBe(480);
    expect(snap(488)).toBe(495);
  });

  it('positions a block by its start time relative to the grid start', () => {
    expect(topForTime(`${String(GRID_START_HOUR).padStart(2, '0')}:00`)).toBe(0);
    // one hour after grid start = one HOUR_PX down
    const oneHourAfter = `${String(GRID_START_HOUR + 1).padStart(2, '0')}:00`;
    expect(topForTime(oneHourAfter)).toBe(HOUR_PX);
  });

  it('sizes a block by its duration with a legibility floor', () => {
    expect(heightForRange('08:00', '12:00')).toBe(4 * HOUR_PX);
    // a tiny slot still gets a minimum height
    expect(heightForRange('08:00', '08:05')).toBeGreaterThanOrEqual(18);
  });

  it('converts a pixel drag delta into snapped minutes', () => {
    // dragging down by exactly one hour-row = +60 minutes
    expect(pxDeltaToMinutes(HOUR_PX)).toBe(60);
    // dragging up snaps negative too
    expect(pxDeltaToMinutes(-HOUR_PX)).toBe(-60);
  });

  it('falls back to a palette colour when none is set', () => {
    expect(colorForWorkstation('#abcdef', 0)).toBe('#abcdef');
    expect(colorForWorkstation(null, 0)).toBe(DEFAULT_WS_COLORS[0]);
    expect(colorForWorkstation(null, DEFAULT_WS_COLORS.length)).toBe(DEFAULT_WS_COLORS[0]); // wraps
  });
});

describe('mondayOfWeek (TZ-safe, #305 M2 auto-gen)', () => {
  it('returns the Monday of the week for any weekday', () => {
    expect(mondayOfWeek('2026-06-24')).toBe('2026-06-22'); // Wed → Mon
    expect(mondayOfWeek('2026-06-22')).toBe('2026-06-22'); // Mon → Mon
    expect(mondayOfWeek('2026-06-28')).toBe('2026-06-22'); // Sun → Mon
  });

  it('the result is itself a Monday — regression for the toISOString UTC roll-back', () => {
    // Under a UTC+ TZ the old toISOString() version returned the prior Sunday.
    expect(new Date(mondayOfWeek('2026-06-24') + 'T00:00:00').getDay()).toBe(1);
  });
});

describe('computeWeekLayout', () => {
  it('lays overlapping same-day slots side by side (lanes)', () => {
    const { boxes } = computeWeekLayout([
      slot('a', 0, '08:00', '12:00'),
      slot('b', 0, '08:00', '12:00'),
    ]);
    // two lanes → each half width, at 0% and 50%
    expect(boxes['a'].widthPct).toBe(50);
    expect(boxes['b'].widthPct).toBe(50);
    expect(new Set([boxes['a'].leftPct, boxes['b'].leftPct])).toEqual(new Set([0, 50]));
  });

  it('gives non-overlapping same-day slots full width each', () => {
    const { boxes } = computeWeekLayout([
      slot('a', 0, '08:00', '10:00'),
      slot('b', 0, '10:00', '12:00'), // starts when a ends → no overlap
    ]);
    expect(boxes['a'].widthPct).toBe(100);
    expect(boxes['b'].widthPct).toBe(100);
    expect(boxes['a'].leftPct).toBe(0);
    expect(boxes['b'].leftPct).toBe(0);
  });

  it('does not let different weekdays share lanes', () => {
    const { boxes } = computeWeekLayout([
      slot('mon', 0, '08:00', '12:00'),
      slot('tue', 1, '08:00', '12:00'),
    ]);
    expect(boxes['mon'].widthPct).toBe(100);
    expect(boxes['tue'].widthPct).toBe(100);
  });

  it('expands the time window to include off-default slots', () => {
    const early = computeWeekLayout([slot('x', 0, '05:00', '06:30')]);
    expect(early.startHour).toBe(5); // earlier than default 06
    expect(early.boxes['x'].top).toBe(0); // 05:00 sits at the top of the expanded grid

    const late = computeWeekLayout([slot('y', 0, '21:00', '23:30')]);
    expect(late.endHour).toBe(24); // later than default 22
  });

  it('keeps the default 06–22 window when all slots fit', () => {
    const { startHour, endHour } = computeWeekLayout([slot('a', 2, '09:00', '17:00')]);
    expect(startHour).toBe(GRID_START_HOUR);
    expect(endHour).toBe(22);
  });

  it('packs three overlapping slots into three lanes', () => {
    const { boxes } = computeWeekLayout([
      slot('a', 3, '08:00', '12:00'),
      slot('b', 3, '09:00', '11:00'),
      slot('c', 3, '10:00', '13:00'),
    ]);
    expect(boxes['a'].widthPct).toBeCloseTo(100 / 3, 5);
  });
});

const slotWithContent = (over: Record<string, unknown> = {}) => ({
  id: 's1',
  weekday: 0,
  start_time: '08:00',
  end_time: '12:00',
  assignments: [],
  note: null,
  ...over,
});

describe('estimateContentHeight', () => {
  it('rechnet Kopfzeile, Zeitzeile und eine Namenszeile', () => {
    // 3 Zeilen à 14px + 8px Innenabstand
    expect(estimateContentHeight(slotWithContent())).toBe(3 * 14 + 8);
  });

  it('rechnet eine Zeile je zugewiesener Person', () => {
    const s = slotWithContent({ assignments: [{}, {}, {}] });
    expect(estimateContentHeight(s)).toBe((2 + 3) * 14 + 8);
  });

  it('rechnet den Hinweis in 20-Zeichen-Zeilen', () => {
    const short = slotWithContent({ note: 'Einarbeitung' }); // 1 Zeile
    const long = slotWithContent({ note: 'x'.repeat(45) }); // 3 Zeilen
    expect(estimateContentHeight(short)).toBe((3 + 1) * 14 + 8);
    expect(estimateContentHeight(long)).toBe((3 + 3) * 14 + 8);
  });

  it('ignoriert einen Hinweis aus Leerzeichen', () => {
    expect(estimateContentHeight(slotWithContent({ note: '   ' }))).toBe(
      estimateContentHeight(slotWithContent()),
    );
  });
});

describe('computeWeekLayout: grown', () => {
  it('markiert einen kurzen Slot mit vielen Namen als gewachsen', () => {
    // 30 Minuten = 24px zeitproportional, Inhalt braucht (2+4)*14+8 = 92px
    const s = slotWithContent({
      start_time: '08:00',
      end_time: '08:30',
      assignments: [{}, {}, {}, {}],
    });
    const layout = computeWeekLayout([s]);
    expect(layout.boxes.s1.grown).toBe(true);
    expect(layout.boxes.s1.contentHeight).toBe(92);
  });

  it('markiert einen ausreichend langen Slot NICHT als gewachsen', () => {
    // 4 Stunden = 192px, Inhalt braucht (2+2)*14+8 = 64px
    const s = slotWithContent({ start_time: '08:00', end_time: '12:00', assignments: [{}, {}] });
    const layout = computeWeekLayout([s]);
    expect(layout.boxes.s1.grown).toBe(false);
    expect(layout.boxes.s1.height).toBe(4 * HOUR_PX);
  });

  it('lässt die zeitproportionale Höhe unberührt', () => {
    const s = slotWithContent({
      start_time: '08:00',
      end_time: '08:30',
      assignments: [{}, {}, {}, {}],
    });
    const layout = computeWeekLayout([s]);
    // height bleibt die Zeitdauer (Untergrenze 18px) — das Wachsen macht das CSS
    expect(layout.boxes.s1.height).toBe(24);
  });
});

describe('visibleWeekdays (#371 configurable weekdays)', () => {
  it('single-day view always wins over the weekday config', () => {
    expect(visibleWeekdays(2, [0, 1, 2, 3, 4])).toEqual([2]);
    expect(visibleWeekdays(6, [0, 1, 2, 3, 4])).toEqual([6]);
  });

  it('renders only the configured weekdays, sorted', () => {
    expect(visibleWeekdays(undefined, [0, 2, 4])).toEqual([0, 2, 4]);
    expect(visibleWeekdays(undefined, [4, 0, 2])).toEqual([0, 2, 4]);
  });

  it('falls back to Mo–Fr when the config is empty or missing', () => {
    expect(visibleWeekdays(undefined, [])).toEqual([0, 1, 2, 3, 4]);
    expect(visibleWeekdays(undefined, undefined)).toEqual([0, 1, 2, 3, 4]);
  });
});
