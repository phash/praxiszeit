/**
 * Display ArbZG compliance warnings returned by backend time-entry endpoints.
 *
 * Backend response shape: `{ warnings?: string[] }` where each string is either
 * a stable code (e.g. `DAILY_HOURS_WARNING`) or a free-form message prefixed
 * with the code (e.g. `REST_TIME_WARNING: Nur 9.0h Ruhezeit…`).
 *
 * Warning-text after the colon (if any) contains localized details from the
 * server and is shown verbatim to the user so they see the concrete numbers.
 *
 * NF-3: toast duration is intentionally NOT passed — ToastContext applies the
 * severity-based default (warning = 6s). Hardcoding a duration here overrode
 * that default and violated the project rule (see CLAUDE.md "Toast-Dauer").
 */
interface WarnToast {
  warning: (message: string, duration?: number) => void;
}

function splitCodeAndDetail(entry: string): { code: string; detail?: string } {
  const idx = entry.indexOf(':');
  if (idx === -1) return { code: entry.trim() };
  return {
    code: entry.slice(0, idx).trim(),
    detail: entry.slice(idx + 1).trim() || undefined,
  };
}

export function showArbzgWarnings(
  toast: WarnToast,
  warnings: string[] | undefined | null,
): void {
  if (!warnings || warnings.length === 0) return;

  for (const raw of warnings) {
    const { code, detail } = splitCodeAndDetail(raw);

    switch (code) {
      case 'REST_TIME_WARNING':
        toast.warning(
          detail ?? 'Zu kurze Ruhezeit seit letztem Arbeitsende (§5 ArbZG, min. 11h).',
        );
        break;
      case 'BREAK_WARNING':
        toast.warning(detail ?? 'Pausenregel verletzt (§4 ArbZG).');
        break;
      case 'BREAK_WAIVER':
        // #144: entry saved with a documented "Pflicht-Pause nicht möglich"
        // exception — surface the §4 deviation so it stays visible.
        toast.warning(
          detail
            ? `Pflicht-Pause-Ausnahme dokumentiert: ${detail}`
            : 'Pflicht-Pause-Ausnahme dokumentiert (§4 ArbZG).',
        );
        break;
      case 'BREAK_WAIVER_PENDING':
        // #144: entry submitted for approval instead of being written.
        toast.warning(
          detail
            ? `Zur Genehmigung eingereicht: ${detail}`
            : 'Pflicht-Pause-Ausnahme zur Genehmigung eingereicht (§4 ArbZG).',
        );
        break;
      case 'DAILY_HOURS_WARNING':
        toast.warning('Tagesarbeitszeit über 8 Stunden (§3 ArbZG).');
        break;
      case 'WEEKLY_HOURS_WARNING':
        toast.warning('Wochenarbeitszeit über 48 Stunden (§3 ArbZG).');
        break;
      case 'SUNDAY_WORK':
        toast.warning('Sonntagsarbeit eingetragen – bitte Ausnahmegrund angeben (§9 ArbZG).');
        break;
      case 'HOLIDAY_WORK':
        toast.warning('Feiertagsarbeit eingetragen – bitte Ausnahmegrund angeben (§9 ArbZG).');
        break;
      default:
        toast.warning(raw);
    }
  }
}
