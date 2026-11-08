import { describe, expect, it } from 'vitest';
import { entryInterval, findOverlap, interval, overlapMessage, overlaps } from './entryOverlap';
import { MSG_CLOSED, MSG_RUNNING, O_CASES } from './entryOverlapCases';

const DAY = '2026-06-02';
const NEXT = '2026-06-03';

describe('entryOverlap (Zwilling entry_guard_service, #538)', () => {
  it.each(O_CASES)('$id', (c) => {
    const today = c.aPastDay ? NEXT : DAY;
    const a = interval(c.a[0], c.a[1], { onDate: DAY, today, now: c.now });
    const b = c.b[1] === null
      ? interval(c.b[0], null, { onDate: DAY, today: DAY, now: c.b[0] })
      : interval(c.b[0], c.b[1], { onDate: DAY, today, now: c.now });
    expect(overlaps(a, b)).toBe(c.overlap);
    expect(overlaps(b, a)).toBe(c.overlap);
  });

  it('nennt den kollidierenden Eintrag wortgleich zum Server', () => {
    expect(overlapMessage({ start: 480, end: 720, running: false }, DAY)).toBe(MSG_CLOSED);
    expect(overlapMessage({ start: 480, end: 600, running: true }, DAY)).toBe(MSG_RUNNING);
  });

  it('rechnet mit Rohstempeln, beim Auto-Close mit dem wirksamen Ende', () => {
    const e = { date: DAY, start_time: '07:45:00', raw_start_time: '07:00:00', end_time: '18:15:00', raw_end_time: '23:59:00', auto_closed: true };
    expect(entryInterval(e, { today: DAY, now: '20:00' })).toEqual({ start: 420, end: 1095, running: false });
    expect(entryInterval({ ...e, auto_closed: false }, { today: DAY, now: '20:00' })).toEqual({ start: 420, end: 1439, running: false });
  });

  it('findet nur Einträge desselben Tages und überspringt den bearbeiteten', () => {
    const entries = [
      { id: 'a', date: DAY, start_time: '08:00', end_time: '12:00' },
      { id: 'b', date: NEXT, start_time: '09:00', end_time: '10:00' },
    ];
    const cand = interval('09:00', '10:00', { onDate: DAY, today: DAY, now: '20:00' });
    expect(findOverlap(entries, cand, { date: DAY, today: DAY, now: '20:00' })).toEqual({ start: 480, end: 720, running: false });
    expect(findOverlap(entries, cand, { date: DAY, today: DAY, now: '20:00', excludeId: 'a' })).toBeNull();
  });
});
