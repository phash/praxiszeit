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
});
