import type { ShiftSlot } from '../../api/shiftPlanning';
import { timeToMinutes } from './weekGridUtils';

/**
 * #330: assigned slot minutes per user across a plan's weekly template.
 * Each slot occurs once per week, so the sum is the weekly assigned time.
 */
export function assignedMinutesByUser(slots: ShiftSlot[]): Map<string, number> {
  const byUser = new Map<string, number>();
  for (const slot of slots) {
    // Same-day slots only: the shift grid is bounded to GRID_START_HOUR..GRID_END_HOUR,
    // so overnight slots (end < start) cannot be created via the UI. A non-positive
    // duration is therefore treated as 0 (skipped), not wrapped past midnight.
    const duration = timeToMinutes(slot.end_time) - timeToMinutes(slot.start_time);
    if (duration <= 0) continue;
    for (const a of slot.assignments) {
      byUser.set(a.user_id, (byUser.get(a.user_id) ?? 0) + duration);
    }
  }
  return byUser;
}

/** German number: comma decimal, up to 2 decimals, trailing zeros trimmed. */
function fmtHours(h: number): string {
  const rounded = Math.round(h * 100) / 100;
  return rounded.toFixed(2).replace(/\.?0+$/, '').replace('.', ',');
}

/** #330 display: e.g. "15,25 / 17 h" (assigned / contract). */
export function formatLoad(assignedMinutes: number, weeklyHours: number): string {
  return `${fmtHours(assignedMinutes / 60)} / ${fmtHours(weeklyHours)} h`;
}

export type LoadColor = 'green' | 'yellow' | 'red' | 'neutral';

/**
 * #330 colour gimmick: green within ±30 min of the contract weekly hours,
 * yellow within ±1 h, red beyond. `neutral` when no contract (weekly_hours 0)
 * — colouring an undefined target would be meaningless.
 */
export function loadColor(assignedMinutes: number, weeklyHours: number): LoadColor {
  if (!weeklyHours || weeklyHours <= 0) return 'neutral';
  const diffMinutes = Math.abs(assignedMinutes - weeklyHours * 60);
  if (diffMinutes <= 30) return 'green';
  if (diffMinutes <= 60) return 'yellow';
  return 'red';
}
