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

/** Zwilling von `format_hours_de`: Dezimalkomma, keine Nullen am Ende. */
export function formatHoursDe(h: number): string {
  return String(Math.round(h * 100) / 100).replace('.', ',');
}

/** Zwilling von `reduced_day_label`. */
export function reducedDayLabel(maxHours: number): string {
  return `verkürzter Tag (max. ${formatHoursDe(maxHours)} h)`;
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
    if (!custom) return null;
    return {
      mode: 'max_hours',
      isFree: false,
      maxHours: custom.max_hours,
      label: `${custom.label}: ${reducedDayLabel(custom.max_hours)}`,
    };
  }

  if (mode === 'max_hours') {
    const x = typeof maxHours === 'number' && maxHours > 0 ? maxHours : 4; // DEFAULT_MAX_HOURS
    return { mode, isFree: false, maxHours: x, label: `${name}: ${reducedDayLabel(x)}` };
  }
  if (mode !== 'free' && mode !== 'half_day') return null;

  return {
    mode,
    isFree: mode === 'free',
    label: mode === 'free' ? `${name} (frei)` : `${name} (½ Tag)`,
  };
}
