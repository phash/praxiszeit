/**
 * Format decimal hours as H:MM (e.g. 6.5 → "6:30", 0.1 → "0:06", -1.5 → "-1:30").
 *
 * F-048: NaN / non-finite guard. Several form handlers call
 * `parseFloat(e.target.value)` without defaulting empty inputs to 0, which
 * produces NaN that then leaks into setState and finally renders as
 * "NaN:NaN" on dashboard tiles. Any non-finite input is clamped to "0:00".
 */
export function formatHoursHM(hours: number): string {
  if (!Number.isFinite(hours)) {
    return '0:00';
  }
  const sign = hours < 0 ? '-' : '';
  const abs = Math.abs(hours);
  let h = Math.floor(abs);
  let m = Math.round((abs - h) * 60);
  if (m === 60) { h++; m = 0; }
  return `${sign}${h}:${String(m).padStart(2, '0')}`;
}

/**
 * Format decimal hours as "Xh Ymin" text (e.g. 8.5 → "8h 30min", 8 → "8h").
 * Same 60-minute rollover + non-finite guard as formatHoursHM. The monthly
 * journal historically duplicated this and reintroduced both bugs ("7h 60min"
 * at near-whole values; "NaNh NaNmin" on a null/NaN field).
 *
 * @param signed       prefix positive values with '+' (balance display);
 *                     negatives always get '-'. When false, positives have none.
 * @param dashForZero  render exactly 0 (and non-finite) as '–' (journal style).
 */
export function formatHoursHMText(
  hours: number,
  { signed = false, dashForZero = false }: { signed?: boolean; dashForZero?: boolean } = {},
): string {
  if (!Number.isFinite(hours)) return dashForZero ? '–' : '0h';
  if (dashForZero && hours === 0) return '–';
  const sign = hours < 0 ? '-' : signed ? '+' : '';
  const abs = Math.abs(hours);
  let h = Math.floor(abs);
  let m = Math.round((abs - h) * 60);
  if (m === 60) { h++; m = 0; }
  return m > 0 ? `${sign}${h}h ${m}min` : `${sign}${h}h`;
}

/**
 * F-048: Parse a user-entered hours string safely.
 *
 * Drop-in replacement for `parseFloat(v)` in form handlers — returns 0
 * for empty / invalid input instead of NaN.
 */
export function parseHours(value: string): number {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

/**
 * #415/#431: eine Vertragsänderung innerhalb eines Berichtszeitraums, so wie
 * `/admin/reports/monthly|weekly` sie liefert (Backend-Zwilling:
 * `schemas/reports.py::WeeklyHoursChangeInPeriod`).
 */
export interface WeeklyHoursChangeInPeriod {
  effective_from: string;
  weekly_hours: number;
  /** #431: Tagesplan-Modus — dann treiben `day_hours` das Tagessoll, nicht `weekly_hours`. */
  use_daily_schedule?: boolean;
  /** Fünf Einträge, Index 0 = Montag; `null` = kein geplanter Arbeitstag. */
  day_hours?: (number | null)[] | null;
  work_days_per_week?: number | null;
}

const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr'];

/**
 * #431: '8,0' / '8,5' / '8,25' — verlustfreie DE-Schreibweise eines
 * Stundenwerts. Zwilling von `export_service._de_hours_exact`, und die
 * Zahlformatierung der Vertragshistorie in BEIDEN Modi.
 *
 * Wochen- und Tagesstunden sind `Numeric(4,2)`: 8,25 h ist ein realer
 * Vertragswert. Auf eine Nachkommastelle gerundet stünde hier '8,3', im Backend
 * dagegen '8,2' (Python rundet `%.1f` half-even, `toFixed` kaufmännisch) —
 * Bildschirm und Datei sagten Verschiedenes. Bei zwei Nachkommastellen rundet
 * für diesen Spaltentyp gar nichts mehr.
 *
 * Für jeden Wert mit höchstens einer Nachkommastelle — also jeden, den die
 * Spalte vor #431 überhaupt speichern konnte — ist das Ergebnis zeichengleich
 * zur früheren `toFixed(1)`-Fassung.
 *
 * Exportiert, weil auch der Wochenstunden-&-Tagesplan-Dialog jede Stundenzahl
 * so schreiben muss: er zeigt die Wochensumme, die der Server aus denselben
 * Tageswerten berechnet — eine zweite Rundungsregel dort hiesse, dass
 * Bildschirm und gespeicherte Zeile verschiedene Zahlen nennen.
 */
export function deHoursExact(value: number): string {
  if (!Number.isFinite(value)) return '?';
  let text = value.toFixed(2);
  if (text.endsWith('0')) text = text.slice(0, -1);
  return text.replace('.', ',');
}

/**
 * #431: der Tagesplan als Klartext — 'Mo 8,0 / Di 5,0 / Mi 4,0'. Zwilling von
 * `export_service.format_day_plan`.
 *
 * Wochentage ohne Stunden stehen nicht drin (weder `null` noch 0): ein Tag ohne
 * Soll ist kein Arbeitstag.
 *
 * Exportiert für den Wochenstunden-&-Tagesplan-Dialog (Kopfzeile + Verlauf):
 * die Verlaufszeile im Dialog und die Vertragshistorie im Bericht müssen
 * denselben Satz schreiben.
 */
export function formatDayPlan(dayHours?: (number | null)[] | null): string {
  if (!dayHours) return '';
  return WEEKDAY_LABELS.map((label, i) => {
    const hours = dayHours[i];
    if (typeof hours !== 'number' || !Number.isFinite(hours) || hours <= 0) return null;
    return `${label} ${deHoursExact(hours)}`;
  })
    .filter((part): part is string => part !== null)
    .join(' / ');
}

/**
 * #415: Vertragsänderungen eines Berichtszeitraums als Klartext.
 *
 * Der Bericht zeigt als Zahl den zu Zeitraumsbeginn gültigen Wert; wechselt die
 * Stundenzahl mitten im Monat, gilt diese Zahl nur für die erste Hälfte. Diese
 * Funktion rendert den Rest — Wortlaut und Format identisch zu
 * `export_service.format_weekly_hours_history`, damit Bildschirm und
 * Datei-Export dasselbe sagen:
 *
 * - gleichmäßig: `ab 15.03.2026: 20,0 Std/Woche`
 * - Tagesplan (#431): `ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche`
 *
 * Leerstring, wenn es im Zeitraum keine Änderung gab → die Aufrufer rendern
 * dann gar nichts und unveränderte Berichte sehen aus wie vorher.
 */
export function formatWeeklyHoursChanges(
  changes?: WeeklyHoursChangeInPeriod[] | null,
): string {
  if (!changes || changes.length === 0) return '';
  return changes
    .map((c) => {
      const [y, m, d] = c.effective_from.split('-');
      const prefix = `ab ${d}.${m}.${y}: `;
      if (c.use_daily_schedule) {
        const plan = formatDayPlan(c.day_hours);
        if (plan) return `${prefix}${plan} = ${deHoursExact(c.weekly_hours)} h/Woche`;
        // Kein einziger Tageswert → gleichmäßige Formulierung statt leerem Satz.
      }
      // Auch hier verlustfrei (nicht `toFixed(1)`): für jeden vor #431
      // speicherbaren Wert zeichengleich zu #415, und nur so sagt der
      // Bildschirm bei 38,25 h dasselbe wie der Datei-Export.
      return `${prefix}${deHoursExact(c.weekly_hours)} Std/Woche`;
    })
    .join('; ');
}

/**
 * #382: Null-safe "HH:MM" from a backend time string ("HH:MM:SS").
 *
 * A clocked-in (running) TimeEntry has `end_time === null` (the column is
 * nullable). Calling `entry.end_time.substring(0, 5)` on such a row threw
 * `Cannot read properties of null` in the Admin-Dashboard detail view →
 * ErrorBoundary white-screen ("Etwas ist schiefgelaufen") for any employee
 * currently clocked in. This returns `fallback` for null/undefined instead.
 */
export function formatClockTime(
  value: string | null | undefined,
  fallback = '–',
): string {
  return value ? value.substring(0, 5) : fallback;
}
