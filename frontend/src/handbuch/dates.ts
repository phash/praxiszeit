/**
 * Datums-Platzhalter in Aufnahme-Eingaben (PrepareStep `fill.value`), relativ
 * zum Stichtag der Demodaten. Ergebnis immer ISO `yyyy-mm-dd` (Playwright
 * `fill` auf `<input type="date">` verlangt ISO).
 *
 *   {{stichtag}}     der Stichtag
 *   {{stichtag-Nd}}  N Kalendertage davor, {{stichtag+Nd}} danach
 *   {{werktag-N}}    der N-te Werktag (Mo–Fr) vor dem Stichtag
 *
 * Feiertage kennt die Regel nicht. Spiegel im Seed: `workday_before` in
 * backend/create_handbuch_testdata.py.
 */

const TOKEN_RE = /\{\{\s*(stichtag(?:([+-])(\d+)d)?|werktag-(\d+))\s*\}\}/g;

function parseIso(day: string): Date {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error(`Stichtag ist kein ISO-Datum: ${day}`);
  const [y, m, d] = day.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function addDays(d: Date, n: number): Date {
  return new Date(d.getTime() + n * 86_400_000);
}

/** N-ter Werktag (Mo–Fr) vor `stichtag` (ISO). */
export function workdayBefore(stichtag: string, n: number): string {
  if (n < 1) throw new Error(`werktag-${n}: N muss mindestens 1 sein`);
  let d = parseIso(stichtag);
  let left = n;
  while (left > 0) {
    d = addDays(d, -1);
    const wd = d.getUTCDay();
    if (wd !== 0 && wd !== 6) left--;
  }
  return iso(d);
}

/** Ersetzt alle Datums-Platzhalter in `value`; unbekannte `{{…}}` lösen einen Fehler aus. */
export function expandDateTokens(value: string, stichtag: string): string {
  const base = parseIso(stichtag);
  const out = value.replace(TOKEN_RE, (_m, _all, sign?: string, days?: string, wd?: string) => {
    if (wd !== undefined) return workdayBefore(stichtag, Number(wd));
    if (sign === undefined) return iso(base);
    return iso(addDays(base, (sign === '-' ? -1 : 1) * Number(days)));
  });
  const rest = out.match(/\{\{[^}]*\}\}/);
  if (rest) throw new Error(`Unbekannter Platzhalter ${rest[0]} in "${value}"`);
  return out;
}
