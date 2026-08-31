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

/**
 * #376: dedup + flatten the per-row `warnings` of a `POST /absences` response
 * (List[AbsenceResponse]) into a single string[] for showArbzgWarnings. `data`
 * is `any` (axios) → typed narrowing happens here so call sites stay clean.
 */
/**
 * #377: strip a leading stable warning code + colon from a raw warning string
 * for inline display (e.g. "MILOG_ACCOUNT_50: …" → "…"). Matches everything up
 * to the first colon so codes with digits are handled too.
 */
export function stripWarningCode(raw: string): string {
  return raw.replace(/^[^:]+:\s*/, '');
}

export function collectAbsenceWarnings(data: unknown): string[] {
  const rows = Array.isArray(data) ? (data as Array<{ warnings?: string[] }>) : [];
  return [...new Set(rows.flatMap((a) => a.warnings ?? []))];
}

/**
 * U3 (Audit 2026-07-31): some guard endpoints (Fix #5 — cancelling an approved
 * vacation request, deleting a company closure) reply with HTTP 200 +
 * `{ warning: string }` instead of the usual 204 No Content when the action
 * touches an already-closed year (a frozen `YearCarryover` for year+1 is now
 * stale). That is a *singular* `warning: string`, not the plural
 * `warnings: string[]` shape `showArbzgWarnings`/`collectAbsenceWarnings`
 * handle — three call sites were dropping it silently and only reporting
 * success.
 *
 * A 204 response makes axios set `data` to `''` (empty string), and a normal
 * success response may be `undefined`/an unrelated object — this tolerates
 * all of that without throwing.
 */
export function showResponseWarning(toast: WarnToast, data: unknown): void {
  if (!data || typeof data !== 'object') return;
  const warning = (data as { warning?: unknown }).warning;
  if (typeof warning === 'string' && warning) {
    toast.warning(warning);
  }
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
      case 'DAILY_HOURS_HARD':
        // Review R2-b: beim Ausstempeln wird die §3-10h-Höchstgrenze nicht
        // mehr blockiert (sonst bliebe der Eintrag offen) — der Verstoß kommt
        // als deutliche Warnung mit konkreter Stundenzahl zurück.
        toast.warning(
          detail ?? 'Tagesarbeitszeit überschreitet die gesetzliche Höchstgrenze von 10 Stunden (§3 ArbZG).',
        );
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
      case 'EARLY_START':
        toast.warning(
          detail ?? 'Du hast vor deinem Soll-Beginn eingestempelt — die Anrechnung beginnt ab dem frühestmöglichen Zeitpunkt.',
        );
        break;
      case 'WORK_WINDOW_CLAMPED':
        // #462 (Kundenmeldung): Das Kappen auf das Soll-Fenster (#201) ist
        // gewollt, geschah aber stumm — wer 07:37 eintrug, bekam 07:45
        // gespeichert und erfuhr es nie. Bei einer Zeiterfassung ist die
        // unbemerkte Änderung fremder Arbeitszeit das eigentliche Problem.
        // Der Text kommt vom Server und nennt die konkreten Zeiten.
        toast.warning(
          detail ?? 'Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt.',
        );
        break;
      case 'CHILD_SICK_LIMIT':
        // #376 §45 SGB V: weiche Warnung — die Buchung ist durchgegangen.
        toast.warning(detail ?? 'Kind-krank-Jahresanspruch überschritten (§45 SGB V).');
        break;
      case 'MILOG_ACCOUNT_50':
        // #377 §2 Abs.2 MiLoG: Arbeitszeitkonto — 50-%-Grenze (weich, nicht blockierend).
        toast.warning(detail ?? 'Arbeitszeitkonto: 50-%-Grenze überschritten (§ 2 Abs. 2 MiLoG).');
        break;
      case 'MILOG_SETTLEMENT_DUE':
        // #377 §2 Abs.2 MiLoG: 12-Monats-Ausgleichsfrist.
        toast.warning(detail ?? 'Arbeitszeitkonto: 12-Monats-Ausgleichsfrist beachten (§ 2 Abs. 2 MiLoG).');
        break;
      case 'MILOG_MONTHLY_EXCEEDED':
        // #377 Baustein 2b §2 Abs.2 MiLoG: Monatsarbeitszeit überschritten (weich, nicht blockierend).
        toast.warning(detail ?? 'Arbeitszeitkonto: vereinbarte Monatsarbeitszeit überschritten (§ 2 Abs. 2 MiLoG).');
        break;
      default:
        toast.warning(raw);
    }
  }
}
