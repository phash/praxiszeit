/**
 * Format decimal hours as H:MM (e.g. 6.5 → "6:30", 0.1 → "0:06", -1.5 → "-1:30").
 *
 * F-048: NaN / non-finite guard. Several form handlers call
 * `parseFloat(e.target.value)` without defaulting empty inputs to 0, which
 * produces NaN that then leaks into setState and finally renders as
 * "NaN:NaN" on dashboard tiles. Any non-finite input is clamped to "0:00".
 */
export function formatHoursHM(hours: number): string {
  if (!Number.isFinite(hours)) {
    return '0:00';
  }
  const sign = hours < 0 ? '-' : '';
  const abs = Math.abs(hours);
  let h = Math.floor(abs);
  let m = Math.round((abs - h) * 60);
  if (m === 60) { h++; m = 0; }
  return `${sign}${h}:${String(m).padStart(2, '0')}`;
}

/**
 * F-048: Parse a user-entered hours string safely.
 *
 * Drop-in replacement for `parseFloat(v)` in form handlers — returns 0
 * for empty / invalid input instead of NaN.
 */
export function parseHours(value: string): number {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}
