import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { submitWithBreakWaiver } from './breakWaiverRetry';
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
    promptSpy.mockReturnValue('Notfall');
    const submit = vi.fn()
      .mockRejectedValueOnce(apiError(S4))
      .mockResolvedValueOnce('ok');

    await expect(submitWithBreakWaiver(submit, { allowed: true })).resolves.toBe('ok');
    expect(promptSpy).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenLastCalledWith({ break_waiver_reason: 'Notfall' });
  });

  // P18, Entschieden 2026-10-11 (Produktinhaber): ein eingereichtes 23:59 gilt
  // beim automatisch geschlossenen Eintrag als echtes Ende. Die §4-Rückfrage darf
  // deshalb nichts an den Zeiten ändern oder ein Ende auffüllen — beide Aufrufe
  // tragen exakt das Ende des Formulars (das WIRKSAME Ende), ergänzt wird nur
  // die Begründung.
  it('ergänzt beim Wiederholen nur die Begründung — das Ende bleibt das des Formulars', async () => {
    promptSpy.mockReturnValue('Notfall');
    const put = vi.fn()
      .mockRejectedValueOnce(apiError(S4))
      .mockResolvedValueOnce('ok');
    const base = { start_time: '08:00', end_time: '18:15', break_minutes: 0 };

    await submitWithBreakWaiver((extra) => put('/admin/time-entries/e1', { ...base, ...extra }), { allowed: true });
    expect(put.mock.calls.map((c) => c[1])).toEqual([
      base,
      { ...base, break_waiver_reason: 'Notfall' },
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
});
