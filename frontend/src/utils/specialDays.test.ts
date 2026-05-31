import { describe, it, expect } from 'vitest';
import { getSpecialDayInfo, type SpecialDaySettings } from './specialDays';

const free24: SpecialDaySettings = {
  special_day_dec24_mode: 'free',
  special_day_dec24_counts_as_vacation: true,
  special_day_dec31_mode: 'working_day',
  special_day_dec31_counts_as_vacation: true,
};

const half31: SpecialDaySettings = {
  special_day_dec24_mode: 'working_day',
  special_day_dec24_counts_as_vacation: true,
  special_day_dec31_mode: 'half_day',
  special_day_dec31_counts_as_vacation: false,
};

describe('getSpecialDayInfo', () => {
  it('marks 24.12. as free (Heiligabend) when configured free', () => {
    const info = getSpecialDayInfo('2026-12-24', free24);
    expect(info).not.toBeNull();
    expect(info!.mode).toBe('free');
    expect(info!.isFree).toBe(true);
    expect(info!.label).toBe('Heiligabend (frei)');
  });

  it('marks 31.12. as half day (Silvester) when configured half_day', () => {
    const info = getSpecialDayInfo('2026-12-31', half31);
    expect(info).not.toBeNull();
    expect(info!.mode).toBe('half_day');
    expect(info!.isFree).toBe(false);
    expect(info!.label).toBe('Silvester (½ Tag)');
  });

  it('labels a free 31.12. as Silvester (frei)', () => {
    const settings: SpecialDaySettings = {
      ...half31,
      special_day_dec31_mode: 'free',
    };
    expect(getSpecialDayInfo('2026-12-31', settings)!.label).toBe('Silvester (frei)');
  });

  it('returns null for a special day configured as working_day', () => {
    expect(getSpecialDayInfo('2026-12-31', free24)).toBeNull(); // dec31 is working_day here
  });

  it('returns null for a normal date', () => {
    expect(getSpecialDayInfo('2026-03-10', free24)).toBeNull();
  });

  it('returns null when settings are missing', () => {
    expect(getSpecialDayInfo('2026-12-24', null)).toBeNull();
    expect(getSpecialDayInfo('2026-12-24', undefined)).toBeNull();
  });

  it('matches 24./31.12. regardless of year', () => {
    expect(getSpecialDayInfo('2031-12-24', free24)!.label).toBe('Heiligabend (frei)');
  });
});
