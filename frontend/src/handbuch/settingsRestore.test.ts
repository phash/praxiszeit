import { describe, expect, it } from 'vitest';
import { SETTING_DEFAULTS, planSettingsRestore } from './settingsRestore';

describe('planSettingsRestore', () => {
  it('restores the stored value when a row exists', () => {
    expect(planSettingsRestore({ break_exception_allowed: false }, { break_exception_allowed: 'false' }))
      .toEqual({ break_exception_allowed: 'false' });
  });

  it('restores the app default when no row is stored', () => {
    expect(planSettingsRestore({ break_exception_allowed: false, work_window_grace_minutes: 5 }, {}))
      .toEqual({ break_exception_allowed: 'true', work_window_grace_minutes: '15' });
  });

  it('throws before any change for a key without stored row and without known default', () => {
    expect(() => planSettingsRestore({ holiday_state: 'BY' }, {})).toThrow(/holiday_state/);
  });

  it('knows defaults for the boolean feature flags', () => {
    expect(SETTING_DEFAULTS.shift_planning_enabled).toBe('false');
    expect(SETTING_DEFAULTS.onboarding_enabled).toBe('true');
  });
});
