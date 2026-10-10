// Oberflächen-Labels der Protokollquellen (`time_entry_audit_logs.source`).
// Spec 2026-10-08 (10.3): `wh_reclamp` (Neukappung einer Arbeitszeit-Änderung,
// ab PR3) und `credit_override` („Anerkennen") ergänzt. Unbekannte Quellen
// zeigt die Seite roh an.
export const AUDIT_SOURCE_LABELS: Record<string, string> = {
  manual: 'Admin',
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
