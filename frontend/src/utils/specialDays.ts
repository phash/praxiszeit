// #188: Sondertage 24.12. (Heiligabend) und 31.12. (Silvester).
//
// Die Tenant-Konfiguration kommt über das öffentliche /api/settings-Feld
// `special_days`. Das Backend behandelt einen als `free` konfigurierten
// Sondertag bereits wie einen Feiertag (Sollzeit 0, ggf. Urlaubsabzug) und
// einen `half_day` mit halbem Tagessoll — der Kalender muss das nur noch
// sichtbar machen (vorher fehlte das, Issue #188).

export type SpecialDayMode = 'working_day' | 'half_day' | 'free';

export interface SpecialDaySettings {
  special_day_dec24_mode: SpecialDayMode;
  special_day_dec24_counts_as_vacation: boolean;
  special_day_dec31_mode: SpecialDayMode;
  special_day_dec31_counts_as_vacation: boolean;
}

export interface SpecialDayInfo {
  /** 'free' = arbeitsfrei (wie Feiertag), 'half_day' = halber Tag. */
  mode: 'free' | 'half_day';
  /** Anzeige-Label, z. B. "Heiligabend (frei)" / "Silvester (½ Tag)". */
  label: string;
  /** true für `free` (Kalender grau wie Feiertag), false für `half_day`. */
  isFree: boolean;
}

/**
 * Liefert Render-Infos, falls `dateStr` ('YYYY-MM-DD') ein als `free`/`half_day`
 * konfigurierter 24./31.12. ist — sonst `null`. `working_day` und fehlende
 * Einstellungen liefern ebenfalls `null` (keine Sonderbehandlung).
 */
export function getSpecialDayInfo(
  dateStr: string,
  settings: SpecialDaySettings | null | undefined,
): SpecialDayInfo | null {
  if (!settings || !dateStr) return null;

  const monthDay = dateStr.slice(5); // 'MM-DD'
  let mode: SpecialDayMode | undefined;
  let name: string | undefined;
  if (monthDay === '12-24') {
    mode = settings.special_day_dec24_mode;
    name = 'Heiligabend';
  } else if (monthDay === '12-31') {
    mode = settings.special_day_dec31_mode;
    name = 'Silvester';
  }

  if (mode !== 'free' && mode !== 'half_day') return null;

  return {
    mode,
    isFree: mode === 'free',
    label: mode === 'free' ? `${name} (frei)` : `${name} (½ Tag)`,
  };
}
