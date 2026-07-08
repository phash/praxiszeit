import { describe, it, expect, vi } from 'vitest';
import { showArbzgWarnings } from './arbzgWarnings';

function mockToast() {
  return { warning: vi.fn() };
}

describe('showArbzgWarnings', () => {
  it('does nothing for empty/missing input', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, undefined);
    showArbzgWarnings(toast, null);
    showArbzgWarnings(toast, []);
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('maps DAILY_HOURS_WARNING to a §3-flavoured message', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, ['DAILY_HOURS_WARNING']);
    expect(toast.warning).toHaveBeenCalledOnce();
    expect(toast.warning.mock.calls[0][0]).toMatch(/§3/);
    expect(toast.warning.mock.calls[0][0]).toMatch(/8 Stunden/);
  });

  it('passes through the detail text for REST_TIME_WARNING', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, [
      'REST_TIME_WARNING: Nur 9.5h Ruhezeit seit letztem Arbeitsende (Minimum: 11h, §5 ArbZG)',
    ]);
    expect(toast.warning.mock.calls[0][0]).toContain('9.5h');
    expect(toast.warning.mock.calls[0][0]).toContain('§5');
  });

  it('emits one toast per warning entry', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, [
      'DAILY_HOURS_WARNING',
      'WEEKLY_HOURS_WARNING',
      'SUNDAY_WORK',
    ]);
    expect(toast.warning).toHaveBeenCalledTimes(3);
  });

  it('falls back to the raw entry for unknown codes', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, ['§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten']);
    expect(toast.warning.mock.calls[0][0]).toMatch(/Nachtarbeitnehmer/);
  });

  it('#377 shows MILOG_ACCOUNT_50 detail without the code prefix', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, [
      'MILOG_ACCOUNT_50: Konto-Plusstunden dieses Monats (20.0h) über 50 % der vereinbarten Monatszeit (Grenze 16.5h, § 2 Abs. 2 MiLoG; sofern zur Mindestlohnhöhe vergütet).',
    ]);
    const msg = toast.warning.mock.calls[0][0];
    expect(msg).toContain('§ 2 Abs. 2 MiLoG');
    expect(msg).not.toContain('MILOG_ACCOUNT_50');
  });

  it('#377 maps MILOG_SETTLEMENT_DUE', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, ['MILOG_SETTLEMENT_DUE: Konto-Stunden aus 01/2025 (9.0h) überfällig — Ausgleich binnen 12 Monaten (§ 2 Abs. 2 MiLoG).']);
    expect(toast.warning.mock.calls[0][0]).toContain('überfällig');
  });

  it('#376 strips the code prefix for CHILD_SICK_LIMIT and shows the detail', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, [
      'CHILD_SICK_LIMIT: Kind-krank-Anspruch überschritten (2.0 von 1 Tagen 2026 verbraucht, §45 SGB V).',
    ]);
    expect(toast.warning).toHaveBeenCalledOnce();
    const msg = toast.warning.mock.calls[0][0];
    expect(msg).toContain('Kind-krank-Anspruch überschritten');
    // the raw default branch would keep the "CHILD_SICK_LIMIT:" code prefix — the
    // dedicated case must strip it (proves the case actually ran).
    expect(msg).not.toContain('CHILD_SICK_LIMIT');
  });
});
