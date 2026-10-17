import { describe, it, expect } from 'vitest';
import { AUDIT_SOURCE_LABELS } from './auditSources';

describe('AUDIT_SOURCE_LABELS (Spec 2026-10-08, 10.3)', () => {
  it('kennt Neukappung und Anerkennen', () => {
    expect(AUDIT_SOURCE_LABELS.wh_reclamp).toBe('Neukappung (Arbeitszeit-Änderung)');
    expect(AUDIT_SOURCE_LABELS.credit_override).toBe('Anrechnung anerkannt');
  });

  it('behält die bisherigen Labels', () => {
    expect(AUDIT_SOURCE_LABELS.wh_change).toBe('Stundenänderung');
    expect(AUDIT_SOURCE_LABELS.break_waiver).toBe('Pausen-Verzicht');
  });

  // Gesamtreview 1.20: `manual` schreibt seit dem Protokoll der Zeiterfassung
  // auch jede Selbsterfassung (Mitarbeitende am selben Tag) — „Admin" neben
  // „Geändert von: <Mitarbeiterin>" widerspräche sich im §16-Nachweis.
  it('nennt `manual` neutral „Manuell" statt „Admin"', () => {
    expect(AUDIT_SOURCE_LABELS.manual).toBe('Manuell');
    expect(Object.values(AUDIT_SOURCE_LABELS)).not.toContain('Admin');
  });

  // Jedes Ausstempeln und jedes automatische Schließen schreibt eine Zeile;
  // bisher stand dort der Rohwert.
  it('kennt Ausstempeln und automatisches Schließen', () => {
    expect(AUDIT_SOURCE_LABELS.clock_out).toBe('Ausstempeln');
    expect(AUDIT_SOURCE_LABELS.auto_close).toBe('Automatisch geschlossen');
  });
});
