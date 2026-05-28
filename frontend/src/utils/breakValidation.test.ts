import { describe, it, expect } from 'vitest';
import { computeBreakError } from './breakValidation';

describe('computeBreakError', () => {
  // 07:00–17:00 = 10h gross, 30 min break → 9.5h net, well over the 9h limit.
  const longDayStart = '07:00';
  const longDayEnd = '17:00';
  const insufficientBreak = 30; // < 45 min required for >9h

  it('flags a non-exempt user working >9h with <45 min break (§4)', () => {
    const error = computeBreakError([], longDayStart, longDayEnd, insufficientBreak, false);
    expect(error).toMatch(/45 Min/);
    expect(error).toMatch(/§4/);
  });

  it('returns no error for an exempt user (§18) with the same >9h input', () => {
    const error = computeBreakError([], longDayStart, longDayEnd, insufficientBreak, true);
    expect(error).toBeNull();
  });

  it('flags >6h with <30 min break for a non-exempt user', () => {
    // 08:00–15:00 = 7h gross, 0 break → 7h net (>6h), no break at all.
    const error = computeBreakError([], '08:00', '15:00', 0, false);
    expect(error).toMatch(/30 Min/);
  });

  it('accepts a non-exempt user with a sufficient 45 min break for a >9h day', () => {
    const error = computeBreakError([], longDayStart, longDayEnd, 45, false);
    expect(error).toBeNull();
  });

  it('does not check days of 6h net or less', () => {
    // 08:00–14:00 = 6h gross, 0 break → 6h net, exactly at the threshold.
    const error = computeBreakError([], '08:00', '14:00', 0, false);
    expect(error).toBeNull();
  });

  it('counts a >=15 min gap between same-day entries as break time (§4 Satz 2)', () => {
    // Existing block 08:00–10:00 (0 break, 2h), new block 10:30–17:30 (7h gross,
    // net 7h > 6h so the check runs). 30 min gap counts as break. Total net 9h,
    // effective break 30 min: >6h needs >=30 (satisfied), not >9h → no error.
    const existing = [{ start: 8 * 60, end: 10 * 60, brk: 0 }];
    const okError = computeBreakError(existing, '10:30', '17:30', 0, false);
    expect(okError).toBeNull();

    // Shrink the gap below 15 min so it no longer counts: 08:00–10:00 +
    // 10:10–17:30 → 10 min gap (ignored), total net 9h20m > 9h, effective
    // break 0 → >9h with <45 min → error.
    const tooShort = [{ start: 8 * 60, end: 10 * 60, brk: 0 }];
    const error = computeBreakError(tooShort, '10:10', '17:30', 0, false);
    expect(error).toMatch(/45 Min/);
  });

  it('exempts a user even when same-day gaps would otherwise trigger an error', () => {
    const existing = [{ start: 8 * 60, end: 10 * 60, brk: 0 }];
    const error = computeBreakError(existing, '10:10', '17:30', 0, true);
    expect(error).toBeNull();
  });
});
