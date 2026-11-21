import type { HandbookId } from '../handbuch/types';

/**
 * Register der „?“-Kurzhilfen neben Feldern (`<HandbookHint hintId="…" />`).
 *
 * Je Eintrag: Handbuch und Sprungmarke (Kapitel- oder Aufgaben-ID, geprüft in
 * `handbookHints.test.ts` über `anchorExists`), Titel und ein Kurztext mit
 * höchstens drei Sätzen in Sie-Form, sinngemäß aus dem verlinkten Abschnitt.
 * Mitarbeiterseiten verlinken `book: 'mitarbeitende'`.
 */
export interface HandbookHintEntry {
  book: HandbookId;
  anchor: string;
  title: string;
  text: string;
}

const HINTS = {
  'wh-effective-date': {
    book: 'praxisleitung',
    anchor: 'rueckwirkend-aendern',
    title: 'Gültig ab',
    text:
      'Ab diesem Tag gilt die neue Arbeitszeit. ' +
      'Liegt das Datum in der Vergangenheit, rechnet PraxisZeit die Zeiteinträge und danach die Abwesenheiten ab diesem Tag neu. ' +
      'Verliert dabei ein Eintrag angerechnete Zeit oder sinkt das Überstundenkonto, gilt die Änderung ab heute – rückwirkend nur mit Grund.',
  },
} satisfies Record<string, HandbookHintEntry>;

export type HintId = keyof typeof HINTS;

export const handbookHints: Record<HintId, HandbookHintEntry> = HINTS;
