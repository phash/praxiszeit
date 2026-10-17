// Oberflächen-Labels der Protokollquellen (`time_entry_audit_logs.source`).
// Spec 2026-10-08 (10.3): `wh_reclamp` (Neukappung einer Arbeitszeit-Änderung,
// ab PR3) und `credit_override` („Anerkennen") ergänzt. Unbekannte Quellen
// zeigt die Seite roh an.
//
// Gesamtreview 1.20: `manual` heißt „Manuell", nicht mehr „Admin" — seit die
// Zeiterfassung Anlegen und Bearbeiten protokolliert, schreibt die Quelle auch
// jede Selbsterfassung von Mitarbeitenden; „Geändert von" nennt die handelnde
// Person. Den Quellwert selbst NIE umbenennen: er geht in `row_hash` (#121) ein
// und wird an mehreren Stellen gefiltert.
export const AUDIT_SOURCE_LABELS: Record<string, string> = {
  manual: 'Manuell',
  clock_out: 'Ausstempeln',
  auto_close: 'Automatisch geschlossen',
  change_request: 'Antrag',
  import: 'Import',
  dsgvo: 'DSGVO',
  break_waiver: 'Pausen-Verzicht',
  vacation_request_cancel: 'Urlaub storniert',
  license_startup: 'Lizenz',
  wh_change: 'Stundenänderung',
  wh_reclamp: 'Neukappung (Arbeitszeit-Änderung)',
  credit_override: 'Anrechnung anerkannt',
};
