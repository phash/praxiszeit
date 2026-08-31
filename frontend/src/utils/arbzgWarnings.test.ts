import { describe, it, expect, vi } from 'vitest';
import { showArbzgWarnings, showResponseWarning, stripWarningCode } from './arbzgWarnings';

describe('#377 stripWarningCode', () => {
  it('strips codes that contain digits (regression: [A-Z_]+ missed the 50)', () => {
    expect(stripWarningCode('MILOG_ACCOUNT_50: Konto über Grenze')).toBe('Konto über Grenze');
  });
  it('strips codes without digits', () => {
    expect(stripWarningCode('MILOG_SETTLEMENT_DUE: bald fällig')).toBe('bald fällig');
  });
  it('leaves a string without a colon unchanged', () => {
    expect(stripWarningCode('kein Code hier')).toBe('kein Code hier');
  });
});

function mockToast() {
  return { warning: vi.fn() };
}

describe('showArbzgWarnings', () => {
  // #462: Die Kappung auf das Soll-Fenster lief stumm — der Melder hielt sie
  // für eine Viertelstunden-Rundung. Der Servertext nennt die konkreten Zeiten
  // und muss deshalb wörtlich durchgereicht werden.
  it('zeigt die Kappungs-Warnung mit den Zeiten aus dem Servertext', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, [
      'WORK_WINDOW_CLAMPED: Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt (Beginn 07:00 \u2192 07:45; Puffer 15 Minuten).',
    ]);
    expect(toast.warning).toHaveBeenCalledTimes(1);
    const text = (toast.warning as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(text).toContain('07:00');
    expect(text).toContain('07:45');
    expect(text).not.toContain('WORK_WINDOW_CLAMPED');
  });

  it('faellt auf einen eigenen Text zurueck, wenn der Server keinen mitschickt', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, ['WORK_WINDOW_CLAMPED']);
    expect(toast.warning).toHaveBeenCalledWith(
      expect.stringContaining('Arbeitszeit-Fenster'),
    );
  });

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

  it('#377 Baustein 2b shows MILOG_MONTHLY_EXCEEDED detail without the code prefix', () => {
    const toast = mockToast();
    showArbzgWarnings(toast, [
      'MILOG_MONTHLY_EXCEEDED: Monatsarbeitszeit (60.0h) übersteigt die vereinbarte Monatszeit (Grenze 55.0h, § 2 Abs. 2 MiLoG).',
    ]);
    const msg = toast.warning.mock.calls[0][0];
    expect(msg).toContain('§ 2 Abs. 2 MiLoG');
    expect(msg).not.toContain('MILOG_MONTHLY_EXCEEDED');
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

describe('U3 showResponseWarning (Audit 2026-07-31)', () => {
  it('shows the warning text of a Fix #5 stale-year-closing 200 response', () => {
    const toast = mockToast();
    showResponseWarning(toast, {
      warning: 'Der Jahresabschluss für Jahr 2025 ist bereits erfolgt, der Übertrag für 2026 ist damit veraltet.',
    });
    expect(toast.warning).toHaveBeenCalledOnce();
    expect(toast.warning.mock.calls[0][0]).toContain('Jahresabschluss für Jahr 2025');
  });

  it('does nothing for a normal 204 response (axios sets data to an empty string)', () => {
    const toast = mockToast();
    showResponseWarning(toast, '');
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('does nothing when there is no warning field, undefined, or null', () => {
    const toast = mockToast();
    showResponseWarning(toast, { some_other_field: 'x' });
    showResponseWarning(toast, undefined);
    showResponseWarning(toast, null);
    showResponseWarning(toast, { warning: '' });
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('ignores a non-string warning field instead of throwing', () => {
    const toast = mockToast();
    expect(() => showResponseWarning(toast, { warning: 42 })).not.toThrow();
    expect(toast.warning).not.toHaveBeenCalled();
  });
});
