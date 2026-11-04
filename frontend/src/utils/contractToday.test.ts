import { describe, it, expect } from 'vitest';
import { trackHoursToday, vacationDaysToday } from './contractToday';

describe('contractToday (F011)', () => {
  it('prefers schedule_today over the user row', () => {
    const u = { track_hours: true, vacation_days: 30, schedule_today: { track_hours: false, vacation_days: 24 } };
    expect(trackHoursToday(u)).toBe(false);
    expect(vacationDaysToday(u)).toBe(24);
  });
  it('falls back to the user row for older responses', () => {
    expect(trackHoursToday({ track_hours: false })).toBe(false);
    expect(trackHoursToday({ track_hours: true, schedule_today: { track_hours: null } })).toBe(true);
    expect(vacationDaysToday({ vacation_days: 30, schedule_today: null })).toBe(30);
    expect(trackHoursToday(null)).toBeUndefined();
  });
});
