import { getErrorMessage } from './errorMessage';
import { useSystemStore } from '../stores/systemStore';

/**
 * #499: Wortgleich zu ``BREAK_EXCEPTION_DISABLED_HINT`` im Backend
 * (break_validation_service.py) — Formular und Server sollen dasselbe sagen.
 */
export const BREAK_EXCEPTION_DISABLED_HINT =
  'Die Ausnahme „Pflicht-Pause war nicht möglich“ ist in dieser Praxis abgeschaltet – bitte die Pause erfassen.';

/**
 * #540 (A1-05): Mindestlänge der Begründung einer §4-Ausnahme (nach `trim()`).
 * Zwilling von `BREAK_WAIVER_MIN_LENGTH` / `BREAK_WAIVER_TOO_SHORT_HINT` in
 * `break_validation_service.py` — gleiche Zahl, wortgleicher Hinweis.
 */
export const BREAK_WAIVER_MIN_LENGTH = 10;

export const BREAK_WAIVER_TOO_SHORT_HINT =
  `Die Begründung ist zu kurz – bitte in mindestens ${BREAK_WAIVER_MIN_LENGTH} Zeichen angeben, warum die Pflicht-Pause nicht möglich war.`;

/** Begründung vorhanden, aber kürzer als `BREAK_WAIVER_MIN_LENGTH` (wie `waiver_reason_too_short`). */
export function isBreakWaiverTooShort(reason: string | null | undefined): boolean {
  const text = (reason ?? '').trim();
  return text.length > 0 && text.length < BREAK_WAIVER_MIN_LENGTH;
}

/**
 * Fehlermeldung des Begründungsfelds oder `null`: leer → Pflichtfeld-Hinweis,
 * zu kurz → `BREAK_WAIVER_TOO_SHORT_HINT`.
 */
export function breakWaiverReasonError(reason: string | null | undefined): string | null {
  if (!(reason ?? '').trim()) return 'Bitte begründen Sie, warum die Pflicht-Pause nicht möglich war.';
  if (isBreakWaiverTooShort(reason)) return BREAK_WAIVER_TOO_SHORT_HINT;
  return null;
}

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
    let prompt =
      `${msg}\n\nWenn die Pflicht-Pause (§4 ArbZG) nachweislich nicht möglich war, ` +
      `begründen Sie dies hier (mindestens ${BREAK_WAIVER_MIN_LENGTH} Zeichen) – die Abweichung wird dokumentiert. ` +
      'Abbrechen lässt den Eintrag unverändert.';
    // #540 (A1-05): eine zu kurze Begründung lehnt der Server ab — gleich
    // erneut fragen statt einen sicheren Fehlschlag zu senden.
    for (;;) {
      const reason = window.prompt(prompt);
      if (!reason || !reason.trim()) throw err;
      if (!isBreakWaiverTooShort(reason)) return await submit({ break_waiver_reason: reason.trim() });
      prompt = `${BREAK_WAIVER_TOO_SHORT_HINT}\n\n${prompt}`;
    }
  }
}
