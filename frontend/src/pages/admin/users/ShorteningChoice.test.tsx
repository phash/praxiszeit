import { describe, it, expect } from 'vitest';
import { losslessLabel, retroLabel, shorteningHeadlines } from './ShorteningChoice';
import type { WorkingHoursChangePreview } from './workingHoursTypes';

const P = (o: Partial<WorkingHoursChangePreview>): WorkingHoursChangePreview => ({
  is_retroactive: true, period_start: '2026-09-01', period_end: '2026-10-08',
  current_daily_target: 7, new_daily_target: 6, day_targets_current: [7, 4, 0, 4, 0], day_targets_new: [6, 4, 0, 4, 0],
  overtime_before: 12.5, overtime_after: 14.25, vacation_days_before: 10, vacation_days_after: 10,
  affected_absences: 0, blocked_reason: null, closed_years: [], closed_year_warning: null,
  is_shortening: true, ...o,
});
const losing = (id: string) => ({
  entry_id: id, date: '2026-09-14', old_start: '15:00:00', old_end: '18:00:00', old_uncredited: 0, old_net: 3,
  new_start: '15:00:00', new_end: '17:15:00', new_uncredited: 0, new_net: 2.25, not_extendable: null,
});

describe('shorteningHeadlines (Spec 12.1)', () => {
  it('(a) Einträge mit Summe', () => {
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries'], lost_credited_hours: 2.25,
      time_entry_changes: [losing('a'), losing('b'), losing('c')],
    }))).toEqual(['3 Einträge verlieren angerechnete Zeit (zusammen 2:15 h)']);
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries'], lost_credited_hours: 0.75, time_entry_changes: [losing('a')],
    }))).toEqual(['1 Eintrag verliert angerechnete Zeit (zusammen 0:45 h)']);
  });

  it('(a) nur der heute offene Eintrag verliert (P1): ein Eintrag, ohne Summe', () => {
    // Der offene Eintrag steht nicht in `time_entry_changes`, sein Verlust ist
    // nicht bezifferbar (das Ende ist unbekannt).
    expect(shorteningHeadlines(P({ shortening_reasons: ['entries'], lost_credited_hours: 0, time_entry_changes: [] })))
      .toEqual(['1 Eintrag verliert angerechnete Zeit']);
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries'], lost_credited_hours: 0, time_entry_changes: [], open_entry_loses: true,
    }))).toEqual(['1 Eintrag verliert angerechnete Zeit']);
  });

  it('(a) offener Eintrag UND geschlossene verlieren: Anzahl wie die 400-Meldung, Summe nur der geschlossenen', () => {
    // Review Task 19: `criteria_text` zählt den offenen Eintrag mit (9.5 (a)) —
    // der Kasten darf keine kleinere Zahl nennen als die Meldung des Servers.
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries'], lost_credited_hours: 1.5, time_entry_changes: [losing('a'), losing('b')],
      open_entry_loses: true,
    }))).toEqual(['3 Einträge verlieren angerechnete Zeit (zusammen 1:30 h)']);
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries'], lost_credited_hours: 0.75, time_entry_changes: [losing('a')],
      open_entry_loses: false,
    }))).toEqual(['1 Eintrag verliert angerechnete Zeit (zusammen 0:45 h)']);
  });

  it('(a) gewinnende Einträge zählen nicht mit', () => {
    const gaining = { ...losing('g'), new_end: '18:15:00', new_net: 3.25 };
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries'], lost_credited_hours: 0.75, time_entry_changes: [losing('a'), gaining],
    }))).toEqual(['1 Eintrag verliert angerechnete Zeit (zusammen 0:45 h)']);
  });

  it('(b) Saldo mit Soll-Zusatz, nur wenn kein Eintrag verliert (dritter Zustand)', () => {
    expect(shorteningHeadlines(P({ shortening_reasons: ['saldo'], saldo_delta_hours: -3.75, target_delta_hours: 4 })))
      .toEqual(['Das Überstundenkonto sinkt im Wirkungsbereich um 3:45 h (höheres Soll), obwohl kein Eintrag angerechnete Zeit verliert']);
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries', 'saldo'], saldo_delta_hours: -1, target_delta_hours: 0, lost_credited_hours: 1,
      time_entry_changes: [losing('a')],
    }))[1]).toBe('Das Überstundenkonto sinkt im Wirkungsbereich um 1:00 h');
  });

  it('(b) offener Tag heute und Anteil eines abgeschlossenen Jahres', () => {
    expect(shorteningHeadlines(P({ shortening_reasons: ['saldo'], saldo_delta_hours: 0, open_day_saldo_delta_hours: -1 })))
      .toEqual(['Heute steigt das Soll um 1:00 h, während die Person eingestempelt ist – das Überstundenkonto sinkt beim Ausstempeln.']);
    expect(shorteningHeadlines(P({
      shortening_reasons: ['saldo'], saldo_delta_hours: 0.5, open_day_saldo_delta_hours: 0, shortening_closed_years: [2025],
    }))).toEqual(['Das Überstundenkonto sinkt im abgeschlossenen Jahr 2025']);
  });

  it('(b) Saldo und offener Tag zugleich: beide Sätze untereinander', () => {
    expect(shorteningHeadlines(P({
      shortening_reasons: ['saldo'], saldo_delta_hours: -2, target_delta_hours: 2, open_day_saldo_delta_hours: -0.5,
    }))).toEqual([
      'Das Überstundenkonto sinkt im Wirkungsbereich um 2:00 h (höheres Soll), obwohl kein Eintrag angerechnete Zeit verliert',
      'Heute steigt das Soll um 0:30 h, während die Person eingestempelt ist – das Überstundenkonto sinkt beim Ausstempeln.',
    ]);
  });

  it('(c) Gutschriften, mehrere Kriterien untereinander', () => {
    const lines = shorteningHeadlines(P({
      shortening_reasons: ['entries', 'saldo', 'absence_credit'], lost_credited_hours: 0.75,
      time_entry_changes: [losing('a')], saldo_delta_hours: -2, target_delta_hours: 0,
      absence_credit_reductions: [
        { absence_id: 'x', date: '2026-09-21', old_hours: 8, new_hours: 4 },
        { absence_id: 'y', date: '2026-09-28', old_hours: 8, new_hours: 4 },
      ],
    }));
    expect(lines).toHaveLength(3);
    expect(lines[2]).toBe('2 Abwesenheits-Gutschriften sinken stärker als das Tagessoll (Arbeit und Gutschrift am selben Tag)');
    expect(shorteningHeadlines(P({
      shortening_reasons: ['absence_credit'],
      absence_credit_reductions: [{ absence_id: 'x', date: '2026-09-21', old_hours: 8, new_hours: 4 }],
    }))).toEqual(['1 Abwesenheits-Gutschrift sinkt stärker als das Tagessoll (Arbeit und Gutschrift am selben Tag)']);
  });
});

describe('Optionsbeschriftungen (P1, P25)', () => {
  it('„Ab heute (…)", „Ab ‹Datum›", null', () => {
    expect(losslessLabel(P({ shortening_reasons: ['entries'], earliest_lossless_date: '2026-10-08' }), '2026-10-08'))
      .toBe('Ab heute (08.10.2026) wirksam – vergangene Einträge bleiben unverändert');
    expect(losslessLabel(P({ shortening_reasons: ['saldo'], earliest_lossless_date: '2026-10-09' }), '2026-10-08'))
      .toBe('Ab 09.10.2026 wirksam – vergangene Tage bleiben unverändert');
    expect(losslessLabel(P({ earliest_lossless_date: null }), '2026-10-08')).toBeNull();
    expect(retroLabel('2026-09-01')).toBe('Rückwirkend ab 01.09.2026 mit Neuberechnung');
  });
});
