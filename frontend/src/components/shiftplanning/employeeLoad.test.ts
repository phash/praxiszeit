import { describe, it, expect } from 'vitest';
import { assignedMinutesByUser, formatLoad, loadColor } from './employeeLoad';
import type { ShiftSlot } from '../../api/shiftPlanning';

function slot(partial: Partial<ShiftSlot> & { start_time: string; end_time: string; assignments: { user_id: string }[] }): ShiftSlot {
  return {
    id: Math.random().toString(),
    workstation_id: 'ws',
    workstation_name: null,
    color: null,
    weekday: 0,
    min_staff: 1,
    understaffed: false,
    ...partial,
    assignments: partial.assignments.map((a, i) => ({ id: String(i), user_name: 'X', ...a })),
  } as ShiftSlot;
}

describe('assignedMinutesByUser', () => {
  it('sums slot durations per assigned user across the plan', () => {
    const slots = [
      slot({ start_time: '08:00', end_time: '12:00', assignments: [{ user_id: 'a' }, { user_id: 'b' }] }), // 240 min
      slot({ start_time: '13:00', end_time: '16:00', assignments: [{ user_id: 'a' }] }),                    // 180 min
    ];
    const m = assignedMinutesByUser(slots);
    expect(m.get('a')).toBe(420); // 4h + 3h
    expect(m.get('b')).toBe(240); // 4h
    expect(m.get('c')).toBeUndefined();
  });

  it('ignores zero/negative-duration slots', () => {
    const m = assignedMinutesByUser([slot({ start_time: '10:00', end_time: '10:00', assignments: [{ user_id: 'a' }] })]);
    expect(m.get('a')).toBeUndefined();
  });
});

describe('formatLoad', () => {
  it('formats as "assigned / contract h" with German decimal comma', () => {
    expect(formatLoad(915, 17)).toBe('15,25 / 17 h'); // 915 min = 15.25h
    expect(formatLoad(0, 40)).toBe('0 / 40 h');
    expect(formatLoad(630, 10.5)).toBe('10,5 / 10,5 h'); // 630 min = 10.5h
  });
});

describe('loadColor', () => {
  it('green within ±30 min of the contract', () => {
    expect(loadColor(17 * 60, 17)).toBe('green');        // exact
    expect(loadColor(17 * 60 + 30, 17)).toBe('green');   // +30 min
    expect(loadColor(17 * 60 - 30, 17)).toBe('green');   // −30 min
  });
  it('yellow within ±1 h', () => {
    expect(loadColor(17 * 60 + 45, 17)).toBe('yellow');
    expect(loadColor(17 * 60 - 60, 17)).toBe('yellow');
  });
  it('red beyond ±1 h', () => {
    expect(loadColor(17 * 60 + 61, 17)).toBe('red');
    expect(loadColor(0, 17)).toBe('red');
  });
  it('neutral when there is no contract', () => {
    expect(loadColor(240, 0)).toBe('neutral');
  });
});
