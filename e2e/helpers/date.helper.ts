export function today(): string {
  return formatDate(new Date());
}

export function formatDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return formatDate(d);
}

export function daysFromNow(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return formatDate(d);
}

// Ostersonntag (anonymer gregorianischer Algorithmus).
function easterSunday(year: number): Date {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(year, month - 1, day);
}

/**
 * Tage, an denen die App je nach Bundesland/Sondertag-Einstellung keinen
 * Arbeitstag sieht: bundesweite + verbreitete Landesfeiertage, 24./31.12.
 * Lieber einen Tag zu viel auslassen — ein Test braucht nur IRGENDEINEN
 * buchbaren Werktag.
 */
function isLikelyNonWorkday(d: Date): boolean {
  const md = `${d.getMonth() + 1}-${d.getDate()}`;
  if (['1-1', '1-6', '5-1', '8-15', '10-3', '10-31', '11-1', '12-24', '12-25', '12-26', '12-31'].includes(md)) {
    return true;
  }
  const easter = easterSunday(d.getFullYear());
  return [-2, 1, 39, 50, 60].some((offset) => {
    const h = new Date(easter);
    h.setDate(h.getDate() + offset);
    return h.getMonth() === d.getMonth() && h.getDate() === d.getDate();
  });
}

/**
 * Like daysFromNow but lands on a bookable weekday. Useful for tests that
 * submit a single-day vacation request or closure — landing on Sat/Sun or a
 * holiday makes the API reject it with "Keine (gültigen) Arbeitstage im
 * Zeitraum". Holidays matter too: weekdayFromNow(90) landed on 01.01. when
 * run on 03.10. (Release 1.19.2).
 */
export function weekdayFromNow(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  while (d.getDay() === 0 || d.getDay() === 6 || isLikelyNonWorkday(d)) {
    d.setDate(d.getDate() + 1);
  }
  return formatDate(d);
}

export function nextWeekday(): string {
  const d = new Date();
  do {
    d.setDate(d.getDate() + 1);
  } while (d.getDay() === 0 || d.getDay() === 6);
  return formatDate(d);
}

export function previousWeekday(): string {
  const d = new Date();
  do {
    d.setDate(d.getDate() - 1);
  } while (d.getDay() === 0 || d.getDay() === 6);
  return formatDate(d);
}

/**
 * Heute im Anzeigeformat der Oberfläche (dd.MM.yyyy).
 *
 * Gegenstück zu ``today()`` für Tests, die eine Eintragszeile über ihr
 * `aria-label` adressieren (`Eintrag vom 01.08.2026 bearbeiten`).
 *
 * Warum ausgerechnet HEUTE: das Detail-Modal des Admin-Dashboards lädt seine
 * Zeiteinträge MONATSWEISE (`GET /time-entries?month=<currentMonth>`), zeigt
 * also nur den laufenden Monat; gleichzeitig lehnt das Backend jedes Datum in
 * der Zukunft ab (`TimeEntryBase.validate_not_future`). Am Monatsanfang gibt es
 * damit unter Umständen gar keinen zurückliegenden Werktag im Anzeigemonat
 * (1. = Samstag) — heute ist das einzige Datum, das beide Bedingungen IMMER
 * erfüllt. `previousWeekday()` erfüllte die erste nicht und ließ die
 * Eintragszeile am Monatsanfang unsichtbar werden.
 */
export function todayDisplay(): string {
  const [y, m, d] = today().split('-');
  return `${d}.${m}.${y}`;
}

export function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
