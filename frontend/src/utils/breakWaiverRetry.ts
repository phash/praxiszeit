import { getErrorMessage } from './errorMessage';
import { useSystemStore } from '../stores/systemStore';

/**
 * #499: Wortgleich zu ``BREAK_EXCEPTION_DISABLED_HINT`` im Backend
 * (break_validation_service.py) — Formular und Server sollen dasselbe sagen.
 */
export const BREAK_EXCEPTION_DISABLED_HINT =
  'Die Ausnahme „Pflicht-Pause war nicht möglich“ ist in dieser Praxis abgeschaltet – bitte die Pause erfassen.';

/**
 * #499: Meldet der Server, dass die Ausnahme „Pflicht-Pause war nicht möglich"
 * in dieser Praxis abgeschaltet ist? Dann darf keine Oberfläche mehr nach einer
 * Begründung fragen — sie würde ohnehin abgelehnt. Dient als Rückfall, falls
 * der im Browser geladene Schalter (systemStore) veraltet ist.
 */
export function isBreakExceptionDisabledMessage(msg: string): boolean {
  return msg.includes('abgeschaltet');
}

/**
 * #200: §4-Pausen-Ausnahme für Admin-Korrekturen.
 *
 * Führt `submit(extra)` aus. Schlägt es mit einem §4-Pausenfehler fehl, wird
 * der/die Admin um eine dokumentierte Begründung gebeten und der Aufruf EINMAL
 * mit `break_waiver_reason` wiederholt. Bei Abbruch (oder leerer Begründung)
 * bleibt der ursprüngliche Fehler erhalten und wird vom Aufrufer angezeigt.
 *
 * #499: Hat die Praxis die Ausnahme abgeschaltet (`allowed: false`, Default aus
 * dem systemStore), wird nicht gefragt — der §4-Fehler geht direkt zurück.
 *
 * Erkennung: die §4-Meldung des Backends enthält stets „Pause"; der §3-10h-Cap
 * („Höchstgrenze … §3 ArbZG") NICHT — der harte §3-Block bleibt also bestehen.
 */
export async function submitWithBreakWaiver<T = void>(
  submit: (extra: { break_waiver_reason?: string }) => Promise<T>,
  options: { allowed?: boolean } = {},
): Promise<T> {
  const allowed = options.allowed ?? useSystemStore.getState().isBreakExceptionAllowed();
  try {
    return await submit({});
  } catch (err) {
    const msg = getErrorMessage(err, '');
    if (!allowed || !msg.includes('Pause') || isBreakExceptionDisabledMessage(msg)) throw err;
    const reason = window.prompt(
      `${msg}\n\nWenn die Pflicht-Pause (§4 ArbZG) nachweislich nicht möglich war, ` +
        'begründen Sie dies hier – die Abweichung wird dokumentiert. ' +
        'Abbrechen lässt den Eintrag unverändert.',
    );
    if (!reason || !reason.trim()) throw err;
    return await submit({ break_waiver_reason: reason.trim() });
  }
}
