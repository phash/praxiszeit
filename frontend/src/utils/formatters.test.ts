import { describe, it, expect } from 'vitest';
import { formatHoursHM, formatHoursHMText, parseHours, formatClockTime, formatWeeklyHoursChanges } from './formatters';

describe('formatHoursHM', () => {
  it('formats whole hours', () => {
    expect(formatHoursHM(8)).toBe('8:00');
    expect(formatHoursHM(0)).toBe('0:00');
  });

  it('formats fractional hours', () => {
    expect(formatHoursHM(6.5)).toBe('6:30');
    expect(formatHoursHM(1.25)).toBe('1:15');
    expect(formatHoursHM(0.1)).toBe('0:06');
  });

  it('formats negative hours (overtime deficit)', () => {
    expect(formatHoursHM(-1.5)).toBe('-1:30');
    expect(formatHoursHM(-0.5)).toBe('-0:30');
  });

  it('rolls 60 minutes up to the next hour (rounding edge)', () => {
    // 7.999… rounds minutes to 60 → should read as 8:00 not 7:60
    expect(formatHoursHM(7.9999)).toBe('8:00');
  });

  it('returns "0:00" for NaN / Infinity (F-048 guard)', () => {
    expect(formatHoursHM(NaN)).toBe('0:00');
    expect(formatHoursHM(Infinity)).toBe('0:00');
    expect(formatHoursHM(-Infinity)).toBe('0:00');
  });
});

describe('formatHoursHMText', () => {
  it('formats whole + fractional hours as "Xh Ymin"', () => {
    expect(formatHoursHMText(8)).toBe('8h');
    expect(formatHoursHMText(8.5)).toBe('8h 30min');
  });

  it('rolls 60 minutes up to the next hour (the "7h 60min" bug)', () => {
    expect(formatHoursHMText(7.9999)).toBe('8h');
  });

  it('signed: + for positive, - for negative (balance display)', () => {
    expect(formatHoursHMText(1.5, { signed: true })).toBe('+1h 30min');
    expect(formatHoursHMText(-1.5, { signed: true })).toBe('-1h 30min');
    expect(formatHoursHMText(2, { signed: true })).toBe('+2h');
  });

  it('unsigned: no + prefix for positive', () => {
    expect(formatHoursHMText(2)).toBe('2h');
    expect(formatHoursHMText(-2)).toBe('-2h');
  });

  it('dashForZero renders 0 and non-finite as "–"', () => {
    expect(formatHoursHMText(0, { dashForZero: true })).toBe('–');
    expect(formatHoursHMText(NaN, { dashForZero: true })).toBe('–');
    expect(formatHoursHMText(Infinity, { dashForZero: true })).toBe('–');
  });

  it('non-finite without dashForZero falls back to "0h" (no "NaNh NaNmin")', () => {
    expect(formatHoursHMText(NaN)).toBe('0h');
    expect(formatHoursHMText(Infinity)).toBe('0h');
  });
});

describe('parseHours', () => {
  it('parses valid numeric strings', () => {
    expect(parseHours('8')).toBe(8);
    expect(parseHours('6.5')).toBe(6.5);
  });

  it('returns 0 for empty/invalid input', () => {
    expect(parseHours('')).toBe(0);
    expect(parseHours('abc')).toBe(0);
  });
});

describe('formatClockTime', () => {
  it('truncates a "HH:MM:SS" backend time to "HH:MM"', () => {
    expect(formatClockTime('08:30:00')).toBe('08:30');
    expect(formatClockTime('17:05')).toBe('17:05');
  });

  it('#382: null/undefined end_time (open, running entry) does NOT throw and uses the fallback', () => {
    // A clocked-in entry has end_time=null; `null.substring()` used to crash the
    // Admin-Dashboard detail view (ErrorBoundary "Etwas ist schiefgelaufen").
    expect(formatClockTime(null)).toBe('–');
    expect(formatClockTime(undefined)).toBe('–');
    expect(formatClockTime(null, 'offen')).toBe('offen');
    expect(formatClockTime(undefined, '17:00')).toBe('17:00');
  });
});

describe('formatWeeklyHoursChanges (#415)', () => {
  it('renders nothing when the weekly hours did not change in the period', () => {
    // Unveränderte Berichte müssen exakt so aussehen wie vor #415.
    expect(formatWeeklyHoursChanges([])).toBe('');
    expect(formatWeeklyHoursChanges(undefined)).toBe('');
    expect(formatWeeklyHoursChanges(null)).toBe('');
  });

  it('names date and new value in German format', () => {
    expect(
      formatWeeklyHoursChanges([{ effective_from: '2026-03-15', weekly_hours: 20 }]),
    ).toBe('ab 15.03.2026: 20,0 Std/Woche');
  });

  it('joins multiple changes in order', () => {
    expect(
      formatWeeklyHoursChanges([
        { effective_from: '2026-03-10', weekly_hours: 30 },
        { effective_from: '2026-09-01', weekly_hours: 20.5 },
      ]),
    ).toBe('ab 10.03.2026: 30,0 Std/Woche; ab 01.09.2026: 20,5 Std/Woche');
  });

  it('matches the wording the file exports use, so screen and export agree', () => {
    // Muss byte-identisch zu export_service.format_weekly_hours_history sein.
    expect(
      formatWeeklyHoursChanges([{ effective_from: '2026-03-15', weekly_hours: 30 }]),
    ).toBe('ab 15.03.2026: 30,0 Std/Woche');
  });

  it('keeps quarter hours in the uniform wording, too', () => {
    // Zwilling: TestDeHoursExactIsAByteIdenticalUpgrade::test_uniform_history_keeps_the_full_value.
    // `working_hours_changes.weekly_hours` ist seit #431 Numeric(4,2), 38,25 h
    // also speicherbar. Mit dem früheren toFixed(1) stünde hier "38,3",
    // während der Datei-Export "38,2" schrieb (Python rundet half-even).
    expect(
      formatWeeklyHoursChanges([{ effective_from: '2026-03-01', weekly_hours: 38.25 }]),
    ).toBe('ab 01.03.2026: 38,25 Std/Woche');
  });

  it('renders every value the old column could hold exactly as before', () => {
    // Zwilling: TestDeHoursExactIsAByteIdenticalUpgrade::test_identical_for_every_value_the_old_column_could_hold.
    // Vor #431 war die Spalte Numeric(4,1) → 0,0 bis 60,0 in Zehntelschritten.
    // Für jeden dieser Werte muss die neue Formatierung zeichengleich zur
    // früheren toFixed(1)-Fassung sein.
    for (let i = 0; i <= 600; i++) {
      const value = i / 10;
      expect(
        formatWeeklyHoursChanges([{ effective_from: '2026-03-01', weekly_hours: value }]),
      ).toBe(`ab 01.03.2026: ${value.toFixed(1).replace('.', ',')} Std/Woche`);
    }
  });

  // ── #431: Tagesplan ────────────────────────────────────────────────
  //
  // Jede Erwartung hier hat ihren wortgleichen Zwilling in
  // backend/tests/test_415_working_hours_history_reports.py
  // (TestFormatDayPlanHistory) — Bildschirm und Datei müssen denselben Satz
  // sagen.

  it('names the weekdays when the employee has an individual day plan', () => {
    // Zwilling: TestFormatDayPlanHistory::test_format_names_the_weekdays
    expect(
      formatWeeklyHoursChanges([
        {
          effective_from: '2026-03-01',
          weekly_hours: 17,
          use_daily_schedule: true,
          day_hours: [8, 5, 4, null, null],
          work_days_per_week: 3,
        },
      ]),
    ).toBe('ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche');
  });

  it('leaves out weekdays without hours', () => {
    // Zwilling: TestFormatDayPlanHistory::test_weekdays_without_hours_are_left_out
    expect(
      formatWeeklyHoursChanges([
        {
          effective_from: '2026-03-01',
          weekly_hours: 13,
          use_daily_schedule: true,
          day_hours: [8, 0, 5, null, 0],
          work_days_per_week: 2,
        },
      ]),
    ).toBe('ab 01.03.2026: Mo 8,0 / Mi 5,0 = 13,0 h/Woche');
  });

  it('shows quarter hours exactly, like the file export does', () => {
    // Zwilling: TestFormatDayPlanHistory::test_quarter_hours_are_shown_exactly.
    // Mit toFixed(1) stünde hier "8,3", im Backend dagegen "8,2" — Bildschirm
    // und Datei würden sich widersprechen.
    expect(
      formatWeeklyHoursChanges([
        {
          effective_from: '2026-03-01',
          weekly_hours: 17.75,
          use_daily_schedule: true,
          day_hours: [8.25, 5.5, 4, null, null],
          work_days_per_week: 3,
        },
      ]),
    ).toBe('ab 01.03.2026: Mo 8,25 / Di 5,5 / Mi 4,0 = 17,75 h/Woche');
  });

  it('joins both wordings in one history', () => {
    // Zwilling: TestFormatDayPlanHistory::test_mixed_history_joins_both_wordings
    expect(
      formatWeeklyHoursChanges([
        { effective_from: '2026-03-01', weekly_hours: 20 },
        {
          effective_from: '2026-07-01',
          weekly_hours: 17,
          use_daily_schedule: true,
          day_hours: [8, 5, 4, null, null],
          work_days_per_week: 3,
        },
      ]),
    ).toBe(
      'ab 01.03.2026: 20,0 Std/Woche; ab 01.07.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche',
    );
  });

  it('falls back to the uniform wording when no weekday carries hours', () => {
    // Zwilling: TestFormatDayPlanHistory::test_day_plan_without_any_hours_falls_back_to_the_weekly_sum
    expect(
      formatWeeklyHoursChanges([
        {
          effective_from: '2026-03-01',
          weekly_hours: 0,
          use_daily_schedule: true,
          day_hours: [null, null, null, null, null],
          work_days_per_week: 3,
        },
      ]),
    ).toBe('ab 01.03.2026: 0,0 Std/Woche');
  });

  // ── Abschluss-Review #431, Fund 1: Arbeitstage-Wechsel ──────────────
  //
  // Zwilling: backend/tests/test_415_working_hours_history_reports.py
  // (TestWorkDaysChangeIsNamed). Der Befund „Arbeitstage geändert" kommt vom
  // Server (`work_days_changed`), weil die Antwort nur die Änderungen trägt —
  // das Basissegment davor sieht der Bildschirm nie.

  it('names the work days when they changed at unchanged weekly hours', () => {
    // Zwilling: test_work_days_change_at_equal_weekly_hours_is_named.
    // Vorher stand hier „ab 16.03.2026: 40,0 Std/Woche" neben einer Kopfzeile
    // „40,0" — zweimal dieselbe Zahl, während das Tagessoll von 8,00 auf 10,00
    // sprang.
    expect(
      formatWeeklyHoursChanges([
        {
          effective_from: '2026-03-16',
          weekly_hours: 40,
          work_days_per_week: 4,
          work_days_changed: true,
        },
      ]),
    ).toBe('ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage');
  });

  it('uses the singular for a single work day', () => {
    // Zwilling: test_single_work_day_is_singular
    expect(
      formatWeeklyHoursChanges([
        {
          effective_from: '2026-03-16',
          weekly_hours: 8,
          work_days_per_week: 1,
          work_days_changed: true,
        },
      ]),
    ).toBe('ab 16.03.2026: 8,0 Std/Woche auf 1 Arbeitstag');
  });

  it('keeps the frozen #415 wording when the work days did not change', () => {
    // Zwilling: test_unchanged_work_days_keep_the_frozen_415_wording.
    // Vor #431 waren die Arbeitstage nicht historisiert — alle Segmente trugen
    // denselben Wert, der Zusatz kann dort nie erscheinen.
    for (const workDays of [1, 2, 3, 4, 5, 6, 7]) {
      expect(
        formatWeeklyHoursChanges([
          {
            effective_from: '2026-03-15',
            weekly_hours: 30,
            work_days_per_week: workDays,
            work_days_changed: false,
          },
        ]),
      ).toBe('ab 15.03.2026: 30,0 Std/Woche');
    }
    // Eine Antwort ganz ohne das Feld (Altbestand/Testdouble) behauptet nichts.
    expect(
      formatWeeklyHoursChanges([
        { effective_from: '2026-03-15', weekly_hours: 30, work_days_per_week: 4 },
      ]),
    ).toBe('ab 15.03.2026: 30,0 Std/Woche');
  });

  it('names the work days only on the segment that changes them', () => {
    // Zwilling: test_only_the_changing_segment_names_the_days
    expect(
      formatWeeklyHoursChanges([
        {
          effective_from: '2026-03-10',
          weekly_hours: 40,
          work_days_per_week: 4,
          work_days_changed: true,
        },
        {
          effective_from: '2026-09-01',
          weekly_hours: 30,
          work_days_per_week: 4,
          work_days_changed: false,
        },
      ]),
    ).toBe('ab 10.03.2026: 40,0 Std/Woche auf 4 Arbeitstage; ab 01.09.2026: 30,0 Std/Woche');
  });

  it('leaves the day-plan wording untouched', () => {
    // Zwilling: test_day_plan_wording_is_untouched — im Tagesplan stehen die
    // Arbeitstage bereits als benannte Wochentage da.
    expect(
      formatWeeklyHoursChanges([
        {
          effective_from: '2026-03-01',
          weekly_hours: 17,
          use_daily_schedule: true,
          day_hours: [8, 5, 4, null, null],
          work_days_per_week: 3,
          work_days_changed: true,
        },
      ]),
    ).toBe('ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche');
  });

  it('stays silent when the flag is set but the count is missing', () => {
    // Defensiv, Zwilling: `_work_days_suffix` steigt bei `None` aus.
    expect(
      formatWeeklyHoursChanges([
        { effective_from: '2026-03-16', weekly_hours: 40, work_days_changed: true },
      ]),
    ).toBe('ab 16.03.2026: 40,0 Std/Woche');
  });
});
