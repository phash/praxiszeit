// #188: Sondertage 24.12. (Heiligabend) und 31.12. (Silvester).
//
// Die Tenant-Konfiguration kommt über das öffentliche /api/settings-Feld
// `special_days`. Das Backend behandelt einen als `free` konfigurierten
// Sondertag bereits wie einen Feiertag (Sollzeit 0, ggf. Urlaubsabzug) und
// einen `half_day` mit halbem Tagessoll — der Kalender muss das nur noch
// sichtbar machen (vorher fehlte das, Issue #188).
//
// Teil B: Modus `max_hours` (verkürzt auf X Stunden) und eigene verkürzte Tage
// (`reduced_days`, nur mit Anmeldung über GET /api/reduced-days — nicht in
// /api/settings; der Aufrufer ergänzt sie clientseitig).

import { formatDecimalDe } from './formatters';

export type SpecialDayMode = 'working_day' | 'half_day' | 'free' | 'max_hours';

export interface ReducedDayEntry {
  date: string; // 'YYYY-MM-DD'
  label: string;
  max_hours: number;
}

export interface SpecialDaySettings {
  special_day_dec24_mode: SpecialDayMode;
  special_day_dec24_counts_as_vacation: boolean;
  special_day_dec24_max_hours: number;
  special_day_dec31_mode: SpecialDayMode;
  special_day_dec31_counts_as_vacation: boolean;
  special_day_dec31_max_hours: number;
  /** Eigene verkürzte Tage (clientseitig aus /api/reduced-days ergänzt). */
  reduced_days?: ReducedDayEntry[];
}

export interface SpecialDayInfo {
  /** 'free' = arbeitsfrei (wie Feiertag), 'half_day' = halber Tag, 'max_hours' = verkürzt. */
  mode: 'free' | 'half_day' | 'max_hours';
  /** Anzeige-Label, z. B. "Heiligabend (frei)" / "Silvester (½ Tag)". */
  label: string;
  /** true für `free` (Kalender grau wie Feiertag), sonst false. */
  isFree: boolean;
  /** Nur bei `max_hours`. */
  maxHours?: number;
}

/** Zwillinge von `special_days_service.DEFAULT_MAX_HOURS` / `MIN_MAX_HOURS` /
 * `MAX_MAX_HOURS` / `MAX_HOURS_ERROR` (F090). */
export const DEFAULT_MAX_HOURS = 4;
export const MIN_MAX_HOURS = 0.25;
export const MAX_MAX_HOURS = 12;
export const MAX_HOURS_ERROR = 'Die Stundenzahl muss zwischen 0,25 und 12 liegen (in Schritten von 0,25).';

/** Zwilling von `parse_max_hours` (ohne Ausnahme): 0,25 ≤ x ≤ 12 in 0,25-Schritten. */
export function isValidMaxHours(x: unknown): x is number {
  return typeof x === 'number' && Number.isFinite(x)
    && x >= MIN_MAX_HOURS && x <= MAX_MAX_HOURS && Math.round(x * 4) === x * 4;
}

/** Zwilling von `_lenient_max_hours` (Lesepfad): ungültig oder fehlend → 4 (F133). */
export function lenientMaxHours(x: unknown): number {
  return isValidMaxHours(x) ? x : DEFAULT_MAX_HOURS;
}

/** Zwilling von `format_max_hours_de` (F903): Dezimalkomma, keine Nullen am Ende —
 * eine benannte Verwendung von `formatters.formatDecimalDe` (F069). */
function formatMaxHoursDe(h: number): string {
  return formatDecimalDe(h);
}

/** Zwilling von `reduced_day_label`. */
export function reducedDayLabel(maxHours: number): string {
  return `verkürzter Tag (max. ${formatMaxHoursDe(maxHours)} h)`;
}

/** Sa/So eines 'YYYY-MM-DD' — kalendarisch, unabhängig von der Zeitzone. */
function isWeekendIso(dateStr: string): boolean {
  const [y, m, d] = dateStr.split('-').map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return wd === 0 || wd === 6;
}

/**
 * Liefert Render-Infos, falls `dateStr` ('YYYY-MM-DD') ein als `free`/`half_day`/
 * `max_hours` konfigurierter 24./31.12. oder ein eigener verkürzter Tag ist —
 * sonst `null`. 24./31.12. werden zuerst aus den Einstellungen aufgelöst (wie im
 * Backend); jedes andere Datum wird exakt in `reduced_days` gesucht.
 */
export function getSpecialDayInfo(
  dateStr: string,
  settings: SpecialDaySettings | null | undefined,
): SpecialDayInfo | null {
  if (!settings || !dateStr) return null;

  const monthDay = dateStr.slice(5); // 'MM-DD'
  let mode: SpecialDayMode | undefined;
  let name: string | undefined;
  let maxHours: number | undefined;
  if (monthDay === '12-24') {
    mode = settings.special_day_dec24_mode;
    name = 'Heiligabend';
    maxHours = settings.special_day_dec24_max_hours;
  } else if (monthDay === '12-31') {
    mode = settings.special_day_dec31_mode;
    name = 'Silvester';
    maxHours = settings.special_day_dec31_max_hours;
  } else {
    const custom = settings.reduced_days?.find((d) => d.date === dateStr);
    // F099: am Wochenende hat ein verkürzter Tag keine Wirkung (Backend
    // `special_day_target`) — dann auch kein Kalenderlabel.
    if (!custom || isWeekendIso(dateStr)) return null;
    const x = lenientMaxHours(custom.max_hours);
    return {
      mode: 'max_hours',
      isFree: false,
      maxHours: x,
      label: `${custom.label}: ${reducedDayLabel(x)}`,
    };
  }

  if (mode === 'max_hours') {
    if (isWeekendIso(dateStr)) return null; // F099: wie oben
    const x = lenientMaxHours(maxHours); // F133: gleiche Gültigkeitsregel wie das Backend
    return { mode, isFree: false, maxHours: x, label: `${name}: ${reducedDayLabel(x)}` };
  }
  if (mode !== 'free' && mode !== 'half_day') return null;

  return {
    mode,
    isFree: mode === 'free',
    label: mode === 'free' ? `${name} (frei)` : `${name} (½ Tag)`,
  };
}
