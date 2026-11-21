import { describe, it, expect } from 'vitest';
import { firstWorkDayHint } from './firstWorkDayHint';
import type { ScheduleSnapshot } from '../pages/admin/users/workingHoursSnapshot';
import type { WorkingHoursChange } from '../pages/admin/users/workingHoursTypes';

const FALLBACK: ScheduleSnapshot = {
  weekly_hours: 16,
  use_daily_schedule: true,
  day_hours: [8, 8, 0, 0, 0],
  work_days_per_week: 2,
  blocks: null,
  contract: {
    vacation_days: 12, track_hours: true, milog_working_time_account: false,
    agreed_monthly_hours: null, use_fixed_monthly_target: false,
  },
};

function row(over: Partial<WorkingHoursChange>): WorkingHoursChange {
  return {
    id: over.id ?? `c-${over.effective_from}`,
    user_id: 'u1',
    effective_from: '2026-10-01',
    weekly_hours: 40,
    use_daily_schedule: false,
    hours_monday: null, hours_tuesday: null, hours_wednesday: null, hours_thursday: null, hours_friday: null,
    work_days_per_week: 5,
    created_at: '2026-11-20T10:00:00Z',
    blocks: null,
    is_baseline: false,
    vacation_days: 30, track_hours: true, milog_working_time_account: false,
    agreed_monthly_hours: null, use_fixed_monthly_target: false,
    ...over,
  };
}

const BASELINE = row({ id: 'base', effective_from: '2026-10-01', is_baseline: true });
const MO_DI = row({
  id: 'modi', effective_from: '2026-11-20', weekly_hours: 16, use_daily_schedule: true,
  hours_monday: 8, hours_tuesday: 8, hours_wednesday: 0, hours_thursday: 0, hours_friday: 0,
  work_days_per_week: 2, vacation_days: 12,
});

describe('firstWorkDayHint', () => {
  it('Fall A: noch nichts gespeichert, Datum nach dem ersten Arbeitstag', () => {
    const hint = firstWorkDayHint('2026-10-01', [], '2026-11-20', FALLBACK);
    expect(hint).toMatchObject({ applyFrom: '2026-10-01', until: '2026-11-19', source: null });
  });

  it('Fall A: eine Ausgangszeile allein zählt nicht als echte Änderung', () => {
    const hint = firstWorkDayHint('2026-10-01', [BASELINE], '2026-11-20', FALLBACK);
    expect(hint).toMatchObject({ applyFrom: '2026-10-01', until: '2026-11-19', source: null });
    expect(hint?.startSchedule.weekly_hours).toBe(40);
  });

  it('Fall B: Ausgangszeile 01.10. (5 Tage) und Zeile 20.11. (Mo + Di)', () => {
    const hint = firstWorkDayHint('2026-10-01', [BASELINE, MO_DI], '2026-11-21', FALLBACK);
    expect(hint).not.toBeNull();
    expect(hint?.source?.effective_from).toBe('2026-11-20');
    expect(hint?.applyFrom).toBe('2026-10-01');
    expect(hint?.until).toBe('2026-11-19');
    expect(hint?.startSchedule.work_days_per_week).toBe(5);
  });

  it('null bei zwei echten Zeilen', () => {
    const second = row({ id: 'x', effective_from: '2026-11-01', weekly_hours: 30 });
    expect(firstWorkDayHint('2026-10-01', [BASELINE, second, MO_DI], '2026-11-21', FALLBACK)).toBeNull();
  });

  it('null, wenn der Vertrag am ersten Arbeitstag gleich ist', () => {
    const sameAsBase = row({ id: 'same', effective_from: '2026-11-20' });
    expect(firstWorkDayHint('2026-10-01', [BASELINE, sameAsBase], '2026-11-21', FALLBACK)).toBeNull();
  });

  it('null, wenn die echte Zeile schon am ersten Arbeitstag beginnt', () => {
    const atStart = { ...MO_DI, effective_from: '2026-10-01' };
    expect(firstWorkDayHint('2026-10-01', [atStart], '2026-11-21', FALLBACK)).toBeNull();
  });

  it('null ohne firstWorkDay', () => {
    expect(firstWorkDayHint(null, [], '2026-11-20', FALLBACK)).toBeNull();
    expect(firstWorkDayHint(undefined, [BASELINE, MO_DI], '2026-11-21', FALLBACK)).toBeNull();
  });

  it('null bei effectiveFrom === firstWorkDay', () => {
    expect(firstWorkDayHint('2026-10-01', [], '2026-10-01', FALLBACK)).toBeNull();
    expect(firstWorkDayHint('2026-10-01', [BASELINE, MO_DI], '2026-10-01', FALLBACK)).toBeNull();
  });
});
