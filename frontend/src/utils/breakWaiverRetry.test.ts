import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  BREAK_WAIVER_MIN_LENGTH, BREAK_WAIVER_TOO_SHORT_HINT, breakWaiverReasonError, isBreakWaiverTooShort, submitWithBreakWaiver,
} from './breakWaiverRetry';
import { useSystemStore } from '../stores/systemStore';

// #499: der Retry mit Begründung darf nur angeboten werden, wenn der Mandant die
// Ausnahme „Pflicht-Pause war nicht möglich" erlaubt.

function apiError(detail: string) {
  return Object.assign(new Error(detail), { response: { status: 400, data: { detail } } });
}

const S4 = 'Bei mehr als 6 Stunden Arbeitszeit ist eine Pause von mindestens 30 Minuten erforderlich (ArbZG §4).';

describe('submitWithBreakWaiver', () => {
  let promptSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    promptSpy = vi.spyOn(window, 'prompt');
  });
  afterEach(() => {
    promptSpy.mockRestore();
  });

  it('fragt bei erlaubter Ausnahme nach einer Begründung und wiederholt den Aufruf', async () => {
    promptSpy.mockReturnValue('Notfall ohne Vertretung');
    const submit = vi.fn()
      .mockRejectedValueOnce(apiError(S4))
      .mockResolvedValueOnce('ok');

    await expect(submitWithBreakWaiver(submit, { allowed: true })).resolves.toBe('ok');
    expect(promptSpy).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenLastCalledWith({ break_waiver_reason: 'Notfall ohne Vertretung' });
  });

  // P18, Entschieden 2026-10-11 (Produktinhaber): ein eingereichtes 23:59 gilt
  // beim automatisch geschlossenen Eintrag als echtes Ende. Die §4-Rückfrage darf
  // deshalb nichts an den Zeiten ändern oder ein Ende auffüllen — beide Aufrufe
  // tragen exakt das Ende des Formulars (das WIRKSAME Ende), ergänzt wird nur
  // die Begründung.
  it('ergänzt beim Wiederholen nur die Begründung — das Ende bleibt das des Formulars', async () => {
    promptSpy.mockReturnValue('Notfall ohne Vertretung');
    const put = vi.fn()
      .mockRejectedValueOnce(apiError(S4))
      .mockResolvedValueOnce('ok');
    const base = { start_time: '08:00', end_time: '18:15', break_minutes: 0 };

    await submitWithBreakWaiver((extra) => put('/admin/time-entries/e1', { ...base, ...extra }), { allowed: true });
    expect(put.mock.calls.map((c) => c[1])).toEqual([
      base,
      { ...base, break_waiver_reason: 'Notfall ohne Vertretung' },
    ]);
  });

  it('fragt bei abgeschalteter Ausnahme NICHT nach und reicht den Fehler durch', async () => {
    const err = apiError(S4);
    const submit = vi.fn().mockRejectedValue(err);

    await expect(submitWithBreakWaiver(submit, { allowed: false })).rejects.toBe(err);
    expect(promptSpy).not.toHaveBeenCalled();
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('liest den Schalter ohne Option aus dem systemStore (Monatsjournal/Admin-Dashboard)', async () => {
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', break_exception_allowed: false },
      isLoaded: true,
    });
    const err = apiError(S4);
    const submit = vi.fn().mockRejectedValue(err);

    await expect(submitWithBreakWaiver(submit)).rejects.toBe(err);
    expect(promptSpy).not.toHaveBeenCalled();
    useSystemStore.setState({ info: null, isLoaded: false });
  });

  it('fragt auch dann nicht nach, wenn der Server die Ausnahme als abgeschaltet meldet', async () => {
    const err = apiError(`${S4} Die Ausnahme „Pflicht-Pause war nicht möglich“ ist in dieser Praxis abgeschaltet – bitte die Pause erfassen.`);
    const submit = vi.fn().mockRejectedValue(err);

    await expect(submitWithBreakWaiver(submit, { allowed: true })).rejects.toBe(err);
    expect(promptSpy).not.toHaveBeenCalled();
  });

  // #540 (A1-05): eine zu kurze Begründung lehnt der Server ab — erneut fragen.
  it('fragt bei zu kurzer Begründung erneut und sendet erst die ausreichende', async () => {
    promptSpy.mockReturnValueOnce('Notfall').mockReturnValueOnce('Notfall ohne Vertretung');
    const submit = vi.fn().mockRejectedValueOnce(apiError(S4)).mockResolvedValueOnce('ok');
    await expect(submitWithBreakWaiver(submit, { allowed: true })).resolves.toBe('ok');
    expect(promptSpy).toHaveBeenCalledTimes(2);
    expect(String(promptSpy.mock.calls[1][0])).toContain(BREAK_WAIVER_TOO_SHORT_HINT);
    expect(submit).toHaveBeenCalledTimes(2);
    expect(submit).toHaveBeenLastCalledWith({ break_waiver_reason: 'Notfall ohne Vertretung' });
  });
});

// #540 (A1-05): Zwilling von break_validation_service (gleiche Grenze, gleicher Text).
describe('Mindestlänge der §4-Begründung', () => {
  it('10 Zeichen nach trim', () => {
    expect(BREAK_WAIVER_MIN_LENGTH).toBe(10);
    expect(isBreakWaiverTooShort('x')).toBe(true);
    expect(isBreakWaiverTooShort('  ' + 'a'.repeat(9) + '  ')).toBe(true);
    expect(isBreakWaiverTooShort('a'.repeat(10))).toBe(false);
    expect(isBreakWaiverTooShort('')).toBe(false);
  });

  it('wortgleicher Hinweis wie der Server', () => {
    expect(BREAK_WAIVER_TOO_SHORT_HINT).toBe(
      'Die Begründung ist zu kurz – bitte in mindestens 10 Zeichen angeben, warum die Pflicht-Pause nicht möglich war.',
    );
    expect(breakWaiverReasonError('')).toMatch(/Bitte begründen/);
    expect(breakWaiverReasonError('kurz')).toBe(BREAK_WAIVER_TOO_SHORT_HINT);
    expect(breakWaiverReasonError('ausreichend lang')).toBeNull();
  });
});

describe('isWaivableBreakMessage (antrag-05)', () => {
  it('erkennt §4-Meldungen, nicht den Pause-Längenfehler', async () => {
    const { isWaivableBreakMessage } = await import('./breakWaiverRetry');
    expect(isWaivableBreakMessage('Bei mehr als 6 Stunden Arbeitszeit ist eine Pause von mindestens 30 Minuten erforderlich (ArbZG §4).')).toBe(true);
    expect(isWaivableBreakMessage('Die Pause (45 Min.) ist so lang wie der Eintrag oder länger (30 Min.).')).toBe(false);
    expect(isWaivableBreakMessage('Höchstgrenze §3 ArbZG')).toBe(false);
  });
});
