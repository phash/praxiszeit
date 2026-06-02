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

  // NF-1: a declared break < 15 min must NOT count toward the mandatory break
  // (§4 Satz 2), mirroring the backend A-M2 fix. Single-entry net using the raw
  // break would be 358 ≤ 360 and slip through; aggregate net (ignoring the
  // sub-15 break) is 372 > 360 → 30-min error.
  it('ignores a sub-15-min declared break when computing net time (§4 Satz 2)', () => {
    // 08:00–14:12 = 372 min gross, 14 min "break" → backend net 372 > 6h.
    const error = computeBreakError([], '08:00', '14:12', 14, false);
    expect(error).toMatch(/30 Min/);
  });

  // NF-2: the over-threshold decision must be made on the AGGREGATE of all
  // same-day blocks, not just the single new entry. Each block here is <6h net
  // but the day in aggregate is >6h with a <15-min (ignored) gap.
  it('checks the aggregate day even when the new entry alone is under 6h', () => {
    // existing 08:00–12:00 (4h) + new 12:05–15:10 (3h05) → gross 7h05, 5-min
    // gap ignored, net 7h05 > 6h, no break → 30-min error.
    const existing = [{ start: 8 * 60, end: 12 * 60, brk: 0 }];
    const error = computeBreakError(existing, '12:05', '15:10', 0, false);
    expect(error).toMatch(/30 Min/);
  });

  // The new entry's own declared break, if 0 < x < 15, is itself a §4 Satz 2
  // violation regardless of net time — the backend returns a (waiver-able)
  // error here, so the client must surface it too (consistency with the
  // break-waiver UI gate).
  it('flags a sub-15-min break segment on a short day (§4 Satz 2)', () => {
    // 08:00–10:00 = 2h, 10-min break → under 6h, but the 10-min segment is
    // itself invalid.
    const error = computeBreakError([], '08:00', '10:00', 10, false);
    expect(error).toMatch(/15 Min/);
  });

  // Review R3: a shift crossing midnight (end < start as HH:MM) must still be
  // measured correctly — otherwise the duration goes negative and the §4 break
  // gate silently never fires (night/on-call clock-out bypassed the gate).
  it('measures an overnight shift correctly (end before start)', () => {
    // 22:00 → 06:00 = 8h gross, 0 break → >6h, no break → must flag §4.
    const error = computeBreakError([], '22:00', '06:00', 0, false);
    expect(error).toMatch(/30 Min/);
  });

  it('flags >9h overnight shift needing 45 min break', () => {
    // 20:00 → 06:00 = 10h gross, 30 break → 9.5h net (>9h) → must flag 45 min.
    const error = computeBreakError([], '20:00', '06:00', 30, false);
    expect(error).toMatch(/45 Min/);
  });
});
