import { describe, it, expect } from 'vitest';
import { formatHoursHM, parseHours } from './formatters';

describe('formatHoursHM', () => {
  it('formats whole hours', () => {
    expect(formatHoursHM(8)).toBe('8:00');
    expect(formatHoursHM(0)).toBe('0:00');
  });

  it('formats fractional hours', () => {
    expect(formatHoursHM(6.5)).toBe('6:30');
    expect(formatHoursHM(1.25)).toBe('1:15');
    expect(formatHoursHM(0.1)).toBe('0:06');
  });

  it('formats negative hours (overtime deficit)', () => {
    expect(formatHoursHM(-1.5)).toBe('-1:30');
    expect(formatHoursHM(-0.5)).toBe('-0:30');
  });

  it('rolls 60 minutes up to the next hour (rounding edge)', () => {
    // 7.999… rounds minutes to 60 → should read as 8:00 not 7:60
    expect(formatHoursHM(7.9999)).toBe('8:00');
  });

  it('returns "0:00" for NaN / Infinity (F-048 guard)', () => {
    expect(formatHoursHM(NaN)).toBe('0:00');
    expect(formatHoursHM(Infinity)).toBe('0:00');
    expect(formatHoursHM(-Infinity)).toBe('0:00');
  });
});

describe('parseHours', () => {
  it('parses valid numeric strings', () => {
    expect(parseHours('8')).toBe(8);
    expect(parseHours('6.5')).toBe(6.5);
  });

  it('returns 0 for empty/invalid input', () => {
    expect(parseHours('')).toBe(0);
    expect(parseHours('abc')).toBe(0);
  });
});
