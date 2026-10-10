import { describe, it, expect } from 'vitest';
import { AUDIT_SOURCE_LABELS } from './auditSources';

describe('AUDIT_SOURCE_LABELS (Spec 2026-10-08, 10.3)', () => {
  it('kennt Neukappung und Anerkennen', () => {
    expect(AUDIT_SOURCE_LABELS.wh_reclamp).toBe('Neukappung (Arbeitszeit-Änderung)');
    expect(AUDIT_SOURCE_LABELS.credit_override).toBe('Anrechnung anerkannt');
  });

  it('behält die bisherigen Labels', () => {
    expect(AUDIT_SOURCE_LABELS.wh_change).toBe('Stundenänderung');
    expect(AUDIT_SOURCE_LABELS.manual).toBe('Admin');
    expect(AUDIT_SOURCE_LABELS.break_waiver).toBe('Pausen-Verzicht');
  });
});
