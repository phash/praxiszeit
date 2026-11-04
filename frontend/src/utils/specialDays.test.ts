import { describe, it, expect } from 'vitest';
import {
  getSpecialDayInfo, isValidMaxHours, lenientMaxHours, reducedDayLabel, type SpecialDaySettings,
} from './specialDays';

const free24: SpecialDaySettings = {
  special_day_dec24_mode: 'free',
  special_day_dec24_counts_as_vacation: true,
  special_day_dec31_mode: 'working_day',
  special_day_dec31_counts_as_vacation: true,
  special_day_dec24_max_hours: 4,
  special_day_dec31_max_hours: 4,
};

const half31: SpecialDaySettings = {
  special_day_dec24_mode: 'working_day',
  special_day_dec24_counts_as_vacation: true,
  special_day_dec31_mode: 'half_day',
  special_day_dec31_counts_as_vacation: false,
  special_day_dec24_max_hours: 4,
  special_day_dec31_max_hours: 4,
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

  it('labels a custom reduced day by date', () => {
    const s = { ...free24, reduced_days: [{ date: '2027-02-08', label: 'Rosenmontag', max_hours: 4 }] };
    const info = getSpecialDayInfo('2027-02-08', s)!;
    expect(info.mode).toBe('max_hours');
    expect(info.isFree).toBe(false);
    expect(info.maxHours).toBe(4);
    expect(info.label).toBe('Rosenmontag: verkürzter Tag (max. 4 h)');
    expect(getSpecialDayInfo('2028-02-08', s)).toBeNull();
  });

  it('labels 24.12. in max_hours mode', () => {
    const s: SpecialDaySettings = {
      ...free24,
      special_day_dec24_mode: 'max_hours',
      special_day_dec24_max_hours: 4.5,
    };
    const info = getSpecialDayInfo('2026-12-24', s)!;
    expect(info.mode).toBe('max_hours');
    expect(info.isFree).toBe(false);
    expect(info.label).toBe('Heiligabend: verkürzter Tag (max. 4,5 h)');
  });

  it('settings entry wins over a reduced_days entry on 24.12.', () => {
    const s = { ...free24, reduced_days: [{ date: '2026-12-24', label: 'X', max_hours: 2 }] };
    expect(getSpecialDayInfo('2026-12-24', s)!.label).toBe('Heiligabend (frei)');
  });

  it('formats hours like the backend', () => {
    expect(reducedDayLabel(4)).toBe('verkürzter Tag (max. 4 h)');
    expect(reducedDayLabel(4.25)).toBe('verkürzter Tag (max. 4,25 h)');
  });

  it('F099: a reduced day on a weekend has no label (backend: no effect)', () => {
    const s = { ...free24, reduced_days: [{ date: '2027-02-06', label: 'Samstag', max_hours: 4 }] };
    expect(getSpecialDayInfo('2027-02-06', s)).toBeNull();
    const dec24 = { ...free24, special_day_dec24_mode: 'max_hours' as const };
    expect(getSpecialDayInfo('2028-12-24', dec24)).toBeNull(); // Sonntag
  });

  it('F133: invalid stored hours fall back to 4 like the backend', () => {
    const s = { ...free24, special_day_dec24_mode: 'max_hours' as const, special_day_dec24_max_hours: 4.3 };
    expect(getSpecialDayInfo('2026-12-24', s)!.maxHours).toBe(4);
    const r = { ...free24, reduced_days: [{ date: '2027-02-08', label: 'R', max_hours: 20 }] };
    expect(getSpecialDayInfo('2027-02-08', r)!.label).toBe('R: verkürzter Tag (max. 4 h)');
  });
});

describe('max-hours validity (twin of parse_max_hours)', () => {
  it('accepts 0,25–12 in 0,25 steps only', () => {
    expect(isValidMaxHours(0.25)).toBe(true);
    expect(isValidMaxHours(12)).toBe(true);
    expect(isValidMaxHours(4.75)).toBe(true);
    expect(isValidMaxHours(0)).toBe(false);
    expect(isValidMaxHours(12.25)).toBe(false);
    expect(isValidMaxHours(4.3)).toBe(false);
    expect(isValidMaxHours(Number.NaN)).toBe(false);
    expect(isValidMaxHours('4')).toBe(false);
    expect(lenientMaxHours(undefined)).toBe(4);
  });
});
