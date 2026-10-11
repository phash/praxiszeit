import { describe, it, expect } from 'vitest';
import {
  BLOCKS_WITHOUT_EFFECT, EMPTY_REASON, JARBSCHG_HINT, LEGACY_BOX_TITLE, LEGAL_HINT, OTHER_CONFIRM, OTHER_WARNING,
  REASON_HELP, REASON_OPTIONS, SKIP_LABELS, closedYearMessage, formatDate, hm, modeSwitchHint, monthLabel,
  reasonComplete, reasonPayload, savedMessage, shortDate, signedDays, signedHm,
} from './workingHoursTexts';

const WAGE = 'Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist unabhängig von der '
  + 'Anrechnung zu vergüten (§ 611a, § 612 BGB). Auf den Mindestlohn für geleistete Stunden kann nicht verzichtet '
  + 'werden (§ 3 MiLoG).';

describe('workingHoursTexts', () => {
  it('Grundtypen: neue Beschriftungen, unveränderte Schlüssel (19.1 Nr. 7)', () => {
    expect(REASON_OPTIONS.map((o) => [o.value, o.label])).toEqual([
      ['erfassungsfehler', 'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)'],
      ['einvernehmlich', 'Mit der beschäftigten Person vereinbart'],
      ['sonstiges', 'Sonstiges'],
    ]);
    for (const o of REASON_OPTIONS) {
      expect(o.confirm).toMatch(/Auf den Mindestlohn für geleistete Stunden kann nicht verzichtet werden \(§ 3 MiLoG\)\.$/);
    }
  });

  it('Bestätigungstexte je Grundtyp wortgleich zu Spec 12.1 (P26)', () => {
    expect(REASON_OPTIONS.map((o) => o.confirm)).toEqual([
      `Ich habe geprüft, dass die hinterlegte Arbeitszeit falsch war (Fehlerkorrektur). ${WAGE}`,
      `Ich habe geprüft, dass die rückwirkende Änderung mit der beschäftigten Person vereinbart ist. ${WAGE}`,
      `Ich habe die Gründe geprüft. ${WAGE}`,
    ]);
    expect(OTHER_WARNING).toBe(
      'Eine einseitige rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO wirkt nur für die Zukunft); '
      + 'geleistete Arbeit bleibt zu vergüten.',
    );
    expect(OTHER_CONFIRM).toBe(
      'Mir ist bewusst, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht nicht gedeckt ist.',
    );
    expect(REASON_HELP).toBe('Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.');
  });

  it('feste Hinweise wortgleich zu Spec 12.1/4.4 (P24)', () => {
    expect(LEGAL_HINT).toBe(
      'Ändert sich der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und braucht '
      + 'das Einverständnis der beschäftigten Person. Die Lage kann, soweit der Vertrag sie nicht festlegt, im Rahmen '
      + 'des Direktionsrechts (§ 106 GewO) nach billigem Ermessen und mit angemessener Ankündigung nur für die Zukunft '
      + 'geändert werden. Vereinbarte Arbeitszeiten und Pausen sind spätestens am Tag des Wirksamwerdens schriftlich '
      + 'mitzuteilen (§ 3 NachwG). Mit Betriebsrat ist die Änderung mitbestimmungspflichtig (§ 87 Abs. 1 Nr. 2, 3 und '
      + '6 BetrVG). PraxisZeit prüft das nicht.',
    );
    expect(JARBSCHG_HINT).toBe(
      'Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG); PraxisZeit prüft diese nicht.',
    );
    expect(LEGACY_BOX_TITLE).toBe('Arbeitszeit-Fenster (Altbestand, nur Kappung)');
    expect(BLOCKS_WITHOUT_EFFECT).toBe('Arbeitszeit-Blöcke gespeichert, ohne Wirkung (keine Stundenzählung)');
    expect(modeSwitchHint('01.11.2026')).toBe(
      'Die Arbeitszeit-Blöcke enden mit dieser Änderung; ab 01.11.2026 wird nicht mehr gekappt.',
    );
  });

  it('Pflichtangaben je Grundtyp (P15, P26)', () => {
    const ok = { type: 'erfassungsfehler' as const, text: 'zehn Zeichen', wageConfirmed: true, otherConfirmed: false };
    expect(reasonComplete(ok)).toBe(true);
    expect(reasonComplete({ ...ok, text: 'neun Zeic' })).toBe(false);
    expect(reasonComplete({ ...ok, text: 'x'.repeat(400) })).toBe(true);
    expect(reasonComplete({ ...ok, text: 'x'.repeat(401) })).toBe(false);
    // Gezählt wird wie im Backend (Python `len`) in Zeichen, nicht in UTF-16-Einheiten.
    expect(reasonComplete({ ...ok, text: '😀'.repeat(5) })).toBe(false);
    expect(reasonComplete({ ...ok, text: '😀'.repeat(10) })).toBe(true);
    expect(reasonComplete({ ...ok, text: '😀'.repeat(400) })).toBe(true);
    expect(reasonComplete({ ...ok, text: '😀'.repeat(401) })).toBe(false);
    expect(reasonComplete({ ...ok, wageConfirmed: false })).toBe(false);
    expect(reasonComplete({ ...ok, type: 'sonstiges' })).toBe(false);
    expect(reasonComplete({ ...ok, type: 'sonstiges', otherConfirmed: true })).toBe(true);
    expect(reasonComplete(EMPTY_REASON)).toBe(false);
    expect(reasonPayload({ ...ok, text: '  zehn Zeichen  ' })).toEqual({
      retroactive_reason_type: 'erfassungsfehler', retroactive_reason_text: 'zehn Zeichen',
      wage_risk_confirmed: true, other_reason_risk_confirmed: false,
    });
    // Ein Haken aus einer früheren „Sonstiges"-Wahl geht nicht mit einem anderen Grundtyp hinaus.
    expect(reasonPayload({ ...ok, otherConfirmed: true }).other_reason_risk_confirmed).toBe(false);
  });

  it('Stundenformate', () => {
    expect([hm(2.25), signedHm(-3.75), signedHm(1.75), signedHm(0)]).toEqual(['2:15', '−3:45', '+1:45', '0:00']);
    // Unter einer halben Minute bleibt es „0:00" ohne Vorzeichen; 59,6 Min rollen auf die volle Stunde.
    expect([signedHm(-0.001), signedHm(0.9933), hm(Number.NaN)]).toEqual(['0:00', '+1:00', '0:00']);
    // Urlaubstage wie im Rest der App über `formatDayCount` (#496): Einheit und
    // Singular inklusive; was als „0 Tage" erscheint, bekommt kein Vorzeichen.
    expect([signedDays(1), signedDays(-1.5), signedDays(0), signedDays(-0.004)])
      .toEqual(['+1 Tag', '−1,5 Tage', '0 Tage', '0 Tage']);
  });

  it('Datumsformate dd.MM.yyyy, Kurzform und Monat', () => {
    expect([formatDate('2026-09-07'), shortDate('2026-09-07'), monthLabel('2026-09')]).toEqual([
      '07.09.2026', '07.09.', 'Sep 2026',
    ]);
  });

  it('Übersprungen-Gründe wie reclamp_audit.SKIP_LABELS', () => {
    expect(SKIP_LABELS).toEqual({
      credit_override: 'anerkannt',
      open: 'offen',
      soll_free_day: 'Sonn-/Feiertag',
      track_hours_off: 'ohne Stundenzählung',
      outside_employment: 'außerhalb der Beschäftigung',
      unique_collision: 'Überschneidung',
    });
  });

  it('gesperrtes abgeschlossenes Jahr nennt das größte Jahr (11.4)', () => {
    expect(closedYearMessage([2024, 2025])).toBe(
      'Rückwirkende Verkürzung in das abgeschlossene Jahr 2025 ist gesperrt. Bitte die Änderung frühestens ab 01.01.2026 wirksam werden lassen.',
    );
    expect(closedYearMessage([])).toBeNull();
  });

  it('Toast nach dem Speichern (12.1)', () => {
    expect(savedMessage({ adjusted_time_entries: 3, skipped_time_entries: 1, adjusted_absences: 1 })).toBe(
      'Gespeichert. 3 Zeiteinträge neu berechnet, 1 übersprungen, 1 Abwesenheit angepasst.',
    );
    expect(savedMessage({ adjusted_absences: 3 })).toBe('Gespeichert. 3 Abwesenheiten angepasst.');
    expect(savedMessage({})).toBe('Gespeichert.');
    expect(savedMessage({ adjusted_time_entries: 1 }, 'Gelöscht')).toBe('Gelöscht. 1 Zeiteintrag neu berechnet.');
  });
});
