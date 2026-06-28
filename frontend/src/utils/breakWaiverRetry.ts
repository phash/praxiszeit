import { getErrorMessage } from './errorMessage';

/**
 * #200: §4-Pausen-Ausnahme für Admin-Korrekturen.
 *
 * Führt `submit(extra)` aus. Schlägt es mit einem §4-Pausenfehler fehl, wird
 * der/die Admin um eine dokumentierte Begründung gebeten und der Aufruf EINMAL
 * mit `break_waiver_reason` wiederholt. Bei Abbruch (oder leerer Begründung)
 * bleibt der ursprüngliche Fehler erhalten und wird vom Aufrufer angezeigt.
 *
 * Erkennung: die §4-Meldung des Backends enthält stets „Pause"; der §3-10h-Cap
 * („Höchstgrenze … §3 ArbZG") NICHT — der harte §3-Block bleibt also bestehen.
 */
export async function submitWithBreakWaiver<T = void>(
  submit: (extra: { break_waiver_reason?: string }) => Promise<T>,
): Promise<T> {
  try {
    return await submit({});
  } catch (err) {
    const msg = getErrorMessage(err, '');
    if (!msg.includes('Pause')) throw err;
    const reason = window.prompt(
      `${msg}\n\nWenn die Pflicht-Pause (§4 ArbZG) nachweislich nicht möglich war, ` +
        'begründen Sie dies hier – die Abweichung wird dokumentiert. ' +
        'Abbrechen lässt den Eintrag unverändert.',
    );
    if (!reason || !reason.trim()) throw err;
    return await submit({ break_waiver_reason: reason.trim() });
  }
}
