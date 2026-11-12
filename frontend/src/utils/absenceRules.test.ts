import { describe, expect, it } from 'vitest';
import {
  PAST_DAY_ABSENCE_HINT, isPastDay, mayBookAbsenceDirectly, mayDeleteAbsenceByDate, todayBerlin, graceRemainingDays,
} from './absenceRules';

const TODAY = '2026-06-10';

describe('absenceRules (S1-01)', () => {
  it('vergangener Tag ist gesperrt, heute und künftig nicht', () => {
    expect(isPastDay('2026-06-09', TODAY)).toBe(true);
    expect(isPastDay(TODAY, TODAY)).toBe(false);
    expect(isPastDay('2026-06-11', TODAY)).toBe(false);
    expect(isPastDay('', TODAY)).toBe(false);
  });

  it('Mitarbeitende buchen vergangene Tage nicht direkt, Admins schon', () => {
    expect(mayBookAbsenceDirectly(false, '2026-06-08', TODAY)).toBe(false);
    expect(mayBookAbsenceDirectly(false, TODAY, TODAY)).toBe(true);
    expect(mayBookAbsenceDirectly(true, '2026-06-08', TODAY)).toBe(true);
  });

  it('Mitarbeitende löschen vergangene Tage nicht direkt, Admins schon', () => {
    expect(mayDeleteAbsenceByDate(false, '2026-06-08', TODAY)).toBe(false);
    expect(mayDeleteAbsenceByDate(false, '2026-06-12', TODAY)).toBe(true);
    expect(mayDeleteAbsenceByDate(true, '2026-06-08', TODAY)).toBe(true);
  });

  it('Hinweis ist wortgleich zur Server-Meldung', () => {
    expect(PAST_DAY_ABSENCE_HINT).toBe('Für vergangene Tage bitte einen Änderungsantrag stellen.');
  });
});

describe('todayBerlin (abw-13)', () => {
  it('liefert das Berliner Datum, nicht das UTC-Datum', () => {
    // 23:30 UTC am 10.06. = 01:30 am 11.06. in Berlin (Sommerzeit)
    expect(todayBerlin(new Date('2026-06-10T23:30:00Z'))).toBe('2026-06-11');
    // 22:30 UTC am 10.12. = 23:30 am 10.12. in Berlin (Winterzeit)
    expect(todayBerlin(new Date('2026-12-10T22:30:00Z'))).toBe('2026-12-10');
  });
});

describe('graceRemainingDays (Review F4)', () => {
  it('zählt Berliner Kalendertage, nicht Uhrzeit-Differenzen', () => {
    // 22:30 UTC am 01.06. = 00:30 Berlin am 02.06.; Frist endet am 16.06.
    expect(graceRemainingDays('2026-06-01T22:30:00Z', '2026-06-02')).toBe(14);
    expect(graceRemainingDays('2026-06-01T22:30:00Z', '2026-06-15')).toBe(1);
    expect(graceRemainingDays('2026-06-01T22:30:00Z', '2026-06-16')).toBe(0);
  });
  it('liefert 0 ohne Deaktivierung und nie negativ', () => {
    expect(graceRemainingDays(null)).toBe(0);
    expect(graceRemainingDays('2026-01-01T10:00:00Z', '2026-06-01')).toBe(0);
  });
});
