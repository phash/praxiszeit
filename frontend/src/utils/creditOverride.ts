/**
 * Spec 2026-10-08, 13.3 „Anerkennen": feste Texte der Aktion — von
 * `components/CreditOverrideButton.tsx` genutzt und in Tests zitiert. Eigenes
 * Modul, damit die Komponentendatei nur Komponenten exportiert (Fast Refresh,
 * ESLint `react-refresh/only-export-components`).
 */

/** P18: ein automatisch geschlossener Eintrag wird erst nach eingetragenem Ende anerkannt (wortgleich zum Server). */
export const AUTO_CLOSED_HINT = 'Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen.';

/** Bestätigungstext vor dem Anerkennen; `rawSpan` = gestempelte Zeit „HH:MM–HH:MM". */
export function creditConfirmText(rawSpan: string): string {
  return (
    `Die gesamte gestempelte Zeit (${rawSpan}) wird angerechnet. Sie bleibt angerechnet — auch bei `
    + 'späteren Neuberechnungen und wenn die Verwaltung die Zeiten ändert; Mitarbeitende können den '
    + 'Eintrag danach nur noch per Änderungsantrag ändern. Wurde nur ein Teil der Zeit gearbeitet, den '
    + 'Eintrag besser aufteilen oder korrigieren. Der Vorgang wird protokolliert.'
  );
}
