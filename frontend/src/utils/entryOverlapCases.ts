/**
 * #538 (A1-02): Falltabelle der Überschneidungsregel — Zwilling von
 * `backend/tests/entry_overlap_cases.py` (gleiche IDs, gleiche Werte).
 * `a`/`b`: [Beginn, Ende] als "HH:MM"; Ende `null` = laufender Eintrag
 * (heute bis `now`, an einem früheren Tag bis Tagesende — `aPastDay`).
 */
export interface OverlapCase {
  id: string;
  a: [string, string | null];
  b: [string, string | null];
  now: string;
  aPastDay: boolean;
  overlap: boolean;
}

export const O_CASES: OverlapCase[] = [
  { id: 'O1', a: ['08:00', '12:00'], b: ['12:00', '13:00'], now: '18:00', aPastDay: false, overlap: false },
  { id: 'O2', a: ['08:00', '12:00'], b: ['11:59', '13:00'], now: '18:00', aPastDay: false, overlap: true },
  { id: 'O3', a: ['08:00', '12:00'], b: ['09:00', '10:00'], now: '18:00', aPastDay: false, overlap: true },
  { id: 'O4', a: ['08:00', '12:00'], b: ['07:00', '08:00'], now: '18:00', aPastDay: false, overlap: false },
  { id: 'O5', a: ['10:00', '10:00'], b: ['09:00', '11:00'], now: '18:00', aPastDay: false, overlap: true },
  { id: 'O6', a: ['08:00', null], b: ['09:30', '09:45'], now: '10:00', aPastDay: false, overlap: true },
  { id: 'O7', a: ['08:00', null], b: ['10:00', '11:00'], now: '10:00', aPastDay: false, overlap: false },
  { id: 'O8', a: ['08:00', null], b: ['20:00', '21:00'], now: '10:00', aPastDay: true, overlap: true },
  { id: 'O9', a: ['08:00', '12:00'], b: ['12:00', null], now: '12:00', aPastDay: false, overlap: false },
  { id: 'O10', a: ['08:00', '12:00'], b: ['11:59', null], now: '11:59', aPastDay: false, overlap: true },
];

export const MSG_CLOSED =
  'Überschneidung mit dem Eintrag 08:00–12:00 am 02.06.2026: Zeiteinträge einer ' +
  'Person dürfen sich nicht überschneiden. Bitte die Zeiten anpassen oder den ' +
  'vorhandenen Eintrag bearbeiten.';
export const MSG_RUNNING =
  'Überschneidung mit dem laufenden Eintrag ab 08:00 am 02.06.2026: Zeiteinträge ' +
  'einer Person dürfen sich nicht überschneiden. Bitte die Zeiten anpassen oder den ' +
  'vorhandenen Eintrag bearbeiten.';
