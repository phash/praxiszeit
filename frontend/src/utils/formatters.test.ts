import { describe, it, expect } from 'vitest';
import { formatHoursHM, formatHoursHMText, parseHours } from './formatters';

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

describe('formatHoursHMText', () => {
  it('formats whole + fractional hours as "Xh Ymin"', () => {
    expect(formatHoursHMText(8)).toBe('8h');
    expect(formatHoursHMText(8.5)).toBe('8h 30min');
  });

  it('rolls 60 minutes up to the next hour (the "7h 60min" bug)', () => {
    expect(formatHoursHMText(7.9999)).toBe('8h');
  });

  it('signed: + for positive, - for negative (balance display)', () => {
    expect(formatHoursHMText(1.5, { signed: true })).toBe('+1h 30min');
    expect(formatHoursHMText(-1.5, { signed: true })).toBe('-1h 30min');
    expect(formatHoursHMText(2, { signed: true })).toBe('+2h');
  });

  it('unsigned: no + prefix for positive', () => {
    expect(formatHoursHMText(2)).toBe('2h');
    expect(formatHoursHMText(-2)).toBe('-2h');
  });

  it('dashForZero renders 0 and non-finite as "–"', () => {
    expect(formatHoursHMText(0, { dashForZero: true })).toBe('–');
    expect(formatHoursHMText(NaN, { dashForZero: true })).toBe('–');
    expect(formatHoursHMText(Infinity, { dashForZero: true })).toBe('–');
  });

  it('non-finite without dashForZero falls back to "0h" (no "NaNh NaNmin")', () => {
    expect(formatHoursHMText(NaN)).toBe('0h');
    expect(formatHoursHMText(Infinity)).toBe('0h');
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
