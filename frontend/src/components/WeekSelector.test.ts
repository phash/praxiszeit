import { describe, it, expect } from 'vitest';
import { weekLabel, isoWeekMonday } from './WeekSelector';

describe('weekLabel', () => {
  it('formats a within-month week like the customer requested (#329)', () => {
    // Mon 22.06.2026 .. Sun 28.06.2026 = ISO week 26.
    expect(weekLabel('2026-06-22')).toBe('22.–28.06.2026 (KW 26)');
  });

  it('keeps both months when the week crosses a month boundary', () => {
    // Mon 29.06.2026 .. Sun 05.07.2026.
    expect(weekLabel('2026-06-29')).toBe('29.06.2026–05.07.2026 (KW 27)');
  });

  it('computes the ISO week number at year start (week 1)', () => {
    // Mon 05.01.2026 is in ISO week 2; 29.12.2025 (Mon) is ISO week 1 of 2026.
    expect(weekLabel('2025-12-29')).toContain('(KW 1)');
  });
});

describe('isoWeekMonday', () => {
  it('returns the Monday of the week containing the given date', () => {
    expect(isoWeekMonday(new Date('2026-06-24T12:00:00'))).toBe('2026-06-22'); // Wed → Mon
    expect(isoWeekMonday(new Date('2026-06-28T12:00:00'))).toBe('2026-06-22'); // Sun → Mon
    expect(isoWeekMonday(new Date('2026-06-22T00:00:00'))).toBe('2026-06-22'); // Mon → Mon
  });
});
