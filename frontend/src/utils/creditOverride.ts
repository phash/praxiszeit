/**
 * Spec 2026-10-08, 13.3 „Anerkennen": feste Texte der Aktion — von
 * `components/CreditOverrideButton.tsx` genutzt und in Tests zitiert. Eigenes
 * Modul, damit die Komponentendatei nur Komponenten exportiert (Fast Refresh,
 * ESLint `react-refresh/only-export-components`).
 */

import { formatHoursHM } from './formatters';
import { notCreditedMinutes, type CreditEntry } from './workBlocks';

/** Felder, an denen die Anerkennen-Regel hängt (Journal- und Dashboard-Einträge). */
export interface RecognizableEntry extends CreditEntry {
  not_credited_minutes?: number | null;
  credit_override?: boolean | null;
}

/** P18: ein automatisch geschlossener Eintrag wird erst nach eingetragenem Ende anerkannt (wortgleich zum Server). */
export const AUTO_CLOSED_HINT = 'Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen.';
/** Ein offener Eintrag wird erst nach dem Ausstempeln anerkannt (wortgleich `credit_override_service.OPEN_ENTRY_DETAIL`). */
export const OPEN_ENTRY_HINT = 'Ein offener Eintrag kann erst nach dem Ausstempeln anerkannt werden.';

/** Bestätigungstext vor dem Anerkennen; `rawSpan` = gestempelte Zeit „HH:MM–HH:MM". */
export function creditConfirmText(rawSpan: string): string {
  return (
    `Die gesamte gestempelte Zeit (${rawSpan}) wird angerechnet. Sie bleibt angerechnet — auch bei `
    + 'späteren Neuberechnungen und wenn die Verwaltung die Zeiten ändert; Mitarbeitende können den '
    + 'Eintrag danach nur noch per Änderungsantrag ändern. Wurde nur ein Teil der Zeit gearbeitet, den '
    + 'Eintrag besser aufteilen oder korrigieren. Der Vorgang wird protokolliert.'
  );
}

/** Nicht angerechnete Minuten eines Eintrags: Serverwert, sonst der Zwilling. */
export function entryNotCreditedMinutes(entry: RecognizableEntry): number {
  return entry.not_credited_minutes ?? notCreditedMinutes(entry);
}

/** Gibt es an diesem Eintrag etwas anzuerkennen? Nicht bei bereits anerkannten,
 * offenen (der Server lehnt sie mit 400 ab) und voll angerechneten Einträgen.
 * Ein automatisch geschlossener Eintrag zählt dazu (Knopf sichtbar, gesperrt). */
export function isRecognizable(entry: RecognizableEntry): boolean {
  return !entry.credit_override && !!entry.end_time && entryNotCreditedMinutes(entry) > 0;
}

/** Jetzt anerkennbar (Häkchen im Monatsjournal): wie `isRecognizable`, aber
 * nicht automatisch geschlossen (P18: erst das tatsächliche Ende eintragen). */
export function canRecognizeNow(entry: RecognizableEntry): boolean {
  return isRecognizable(entry) && !entry.auto_closed;
}

/** Bestätigungstext vor dem Sammel-Anerkennen im Monatsjournal. */
export function bulkConfirmText(count: number, extraMinutes: number): string {
  const subject = count === 1 ? '1 Eintrag wird' : `${count} Einträge werden`;
  return (
    `${subject} mit der ganzen gestempelten Zeit angerechnet (zusätzlich ${formatHoursHM(extraMinutes / 60)} h). `
    + 'Anerkennen lässt sich nicht zurücknehmen. Der Vorgang wird protokolliert.'
  );
}
