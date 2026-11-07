import { describe, expect, it } from 'vitest';
import {
  PAST_DAY_ABSENCE_HINT, isPastDay, mayBookAbsenceDirectly, mayDeleteAbsenceByDate,
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
