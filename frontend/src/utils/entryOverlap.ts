/**
 * #538 (A1-02): Überschneidungsregel für Zeiteinträge — Zwilling von
 * `backend/app/services/entry_guard_service.py` (gleiche Falltabelle
 * `entryOverlapCases.ts`, wortgleicher Hinweistext). Verglichen wird die
 * ANWESENHEIT laut Stempel (Rohstempel; beim automatisch geschlossenen Eintrag
 * das wirksame Ende), ein laufender Eintrag reicht bis „jetzt" (heute) bzw. bis
 * Tagesende (früherer Tag). Aneinanderstoßende Einträge sind erlaubt.
 * Der Server entscheidet; das Formular zeigt den Hinweis nur früher.
 */
export const DAY_END_MINUTES = 24 * 60;

export interface PresenceInterval {
  start: number;
  end: number;
  running: boolean;
}

export interface OverlapEntryLike {
  id?: string;
  date: string;
  start_time: string;
  end_time: string | null;
  raw_start_time?: string | null;
  raw_end_time?: string | null;
  auto_closed?: boolean | null;
}

function toMin(hhmm: string): number {
  const [h, m] = hhmm.substring(0, 5).split(':').map(Number);
  return h * 60 + m;
}

function hhmm(minutes: number): string {
  if (minutes >= DAY_END_MINUTES) return '24:00';
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

/** Intervall aus Beginn/Ende (Ende `null` = laufend), wie `entry_guard_service.interval`. */
export function interval(start: string, end: string | null, opts: { onDate: string; today: string; now: string }): PresenceInterval {
  const s = toMin(start);
  if (end === null) {
    const e = opts.onDate === opts.today ? Math.max(toMin(opts.now), s + 1) : DAY_END_MINUTES;
    return { start: s, end: Math.max(e, s + 1), running: true };
  }
  return { start: s, end: toMin(end), running: false };
}

/** Anwesenheit eines gespeicherten Eintrags (`presence_end`-Regel). */
export function entryInterval(e: OverlapEntryLike, opts: { today: string; now: string }): PresenceInterval {
  const start = e.raw_start_time || e.start_time;
  const end = e.end_time === null ? null : (e.auto_closed ? e.end_time : (e.raw_end_time || e.end_time));
  return interval(start, end, { onDate: e.date, ...opts });
}

export function overlaps(a: PresenceInterval, b: PresenceInterval): boolean {
  const aEnd = a.end > a.start ? a.end : a.start + 1;
  const bEnd = b.end > b.start ? b.end : b.start + 1;
  return a.start < bEnd && b.start < aEnd;
}

/** Hinweistext — wortgleich zu `entry_guard_service.overlap_detail`. */
export function overlapMessage(other: PresenceInterval, dateIso: string): string {
  const [y, m, d] = dateIso.split('-');
  const what = other.running
    ? `dem laufenden Eintrag ab ${hhmm(other.start)}`
    : `dem Eintrag ${hhmm(other.start)}–${hhmm(other.end)}`;
  return (
    `Überschneidung mit ${what} am ${d}.${m}.${y}: Zeiteinträge einer Person ` +
    'dürfen sich nicht überschneiden. Bitte die Zeiten anpassen oder den vorhandenen Eintrag bearbeiten.'
  );
}

/** Erste Überschneidung des Kandidaten mit den Einträgen desselben Tages (ohne `excludeId`). */
export function findOverlap(
  entries: OverlapEntryLike[],
  candidate: PresenceInterval,
  opts: { date: string; today: string; now: string; excludeId?: string | null },
): PresenceInterval | null {
  for (const e of entries) {
    if (e.date !== opts.date || (opts.excludeId && e.id === opts.excludeId)) continue;
    const other = entryInterval(e, { today: opts.today, now: opts.now });
    if (overlaps(candidate, other)) return other;
  }
  return null;
}
