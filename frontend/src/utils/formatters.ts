/**
 * Format decimal hours as H:MM (e.g. 6.5 → "6:30", 0.1 → "0:06", -1.5 → "-1:30")
 */
export function formatHoursHM(hours: number): string {
  const sign = hours < 0 ? '-' : '';
  const abs = Math.abs(hours);
  let h = Math.floor(abs);
  let m = Math.round((abs - h) * 60);
  if (m === 60) { h++; m = 0; }
  return `${sign}${h}:${String(m).padStart(2, '0')}`;
}
