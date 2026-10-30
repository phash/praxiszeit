// Spec 2026-10-08: Anzeige-Helfer für Arbeitszeit-Blöcke. PR2/PR3 ergänzen hier
// die Zwillinge der Backend-Rechenhelfer (notCreditedMinutes, gapSegments,
// deriveTargets) — jeweils mit wortgleichen Testfällen.
import type { DayBlocks, TimeBlock, WeekBlocks } from '../types/workBlocks';

export const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr'] as const;

/** Spec 3.3: eine Altzeile (aus Migration 073) trägt an mindestens einem Tag
 * keine Pausenangabe (`pause_minutes === null`). */
export function isLegacyWeek(week: WeekBlocks | null | undefined): boolean {
  return Array.isArray(week) && week.some((day) => day?.pause_minutes === null);
}

/** „Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00" — nur Tage
 * mit Blöcken, „(Pause …)" nur bei Pause > 0; `null`, wenn kein Tag Blöcke hat.
 * Altwerte (07:37, Platzhalter 23:59) werden unverändert angezeigt (Spec 4.4). */
export function formatWeekBlocks(week: WeekBlocks | null | undefined): string | null {
  if (!Array.isArray(week)) return null;
  const parts = week.flatMap((day, index) => {
    const blocks = day?.blocks ?? [];
    if (blocks.length === 0 || index >= WEEKDAY_LABELS.length) return [];
    const spans = blocks.map((block) => `${block.start}–${block.end}`).join(' + ');
    const pause = day.pause_minutes ? ` (Pause ${day.pause_minutes} Min)` : '';
    return [`${WEEKDAY_LABELS[index]} ${spans}${pause}`];
  });
  return parts.length > 0 ? parts.join(' · ') : null;
}

const LAST_MINUTE = 23 * 60 + 59;

/** "HH:MM" bzw. "HH:MM:SS" → Minuten seit Mitternacht (Sekunden ignoriert, wie im Backend). */
export function hhmmToMinutes(value: string): number {
  const [h, m] = value.substring(0, 5).split(':').map(Number);
  return h * 60 + m;
}

/** Minuten seit Mitternacht → "HH:MM". */
function toHHMM(m: number): string {
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function sortedMinutes(blocks: TimeBlock[]): [number, number][] {
  return blocks
    .map((b) => [hhmmToMinutes(b.start), hhmmToMinutes(b.end)] as [number, number])
    .sort((a, b) => a[0] - b[0]);
}

/**
 * Zwilling von `work_window_service.gap_segments` (Spec 6.1/8.4): die nicht
 * angerechneten Minuten je Lücke für einen Eintrag `start`–`end` an einem Tag
 * mit `blocks`. Beginn/Ende werden auf die Hülle (erster Block − Puffer, letzter
 * Block + Puffer) begrenzt; die Lücken schrumpfen an beiden Rändern um den
 * Puffer, eine Lücke ≤ 2 × Puffer verschwindet. Kollaps außerhalb der Hülle → [].
 */
export function gapSegments(
  blocks: TimeBlock[] | null | undefined, grace: number, start: string, end: string,
): number[] {
  if (!blocks || blocks.length === 0) return [];
  const mins = sortedMinutes(blocks);
  const floor = Math.max(0, Math.min(mins[0][0] - grace, LAST_MINUTE));
  const ceil = Math.max(0, Math.min(mins[mins.length - 1][1] + grace, LAST_MINUTE));
  const s = Math.max(hhmmToMinutes(start), floor);
  const e = Math.min(hhmmToMinutes(end), ceil);
  if (s >= e) return [];
  const out: number[] = [];
  for (let i = 0; i + 1 < mins.length; i++) {
    const gs = mins[i][1] + grace;
    const ge = mins[i + 1][0] - grace;
    if (ge <= gs) continue;
    const overlap = Math.min(e, ge) - Math.max(s, gs);
    if (overlap > 0) out.push(overlap);
  }
  return out;
}

/**
 * Zwilling der Hülle in `work_window_service._clamp_core` (Spec 6.1): Beginn vor
 * [erster Block − Puffer] und Ende nach [letzter Block + Puffer] werden darauf
 * gekappt — dieselben floor/ceil-Werte wie `gapSegments`. Ein letzter Block bis
 * 23:59 ist der Ende-Platzhalter eines halboffenen Altfensters und kappt das
 * Ende nicht (Spec 5.3). Liegt der Eintrag ganz außerhalb der Hülle (Kollaps),
 * gilt Beginn = Ende = eingetragener Beginn: angerechnet 0 h, wie der Server.
 *
 * Gesamtreview PR2 (Fund 13): der Server prüft §4 auf der GEKAPPTEN Zeit (E43).
 * Die Vorprüfungen im Browser (StampWidget, TimeTracking) rechnen deshalb mit
 * diesen Zeiten — sonst verlangten sie für Stempelzeit außerhalb der Hülle
 * eine Pause, die angerechnete Zeit kostet. Ohne Blöcke und bei Ende ≤ Beginn
 * (über Mitternacht) unverändert. `blocklessWorkday` (Werktag ohne Blöcke, vom
 * Server als `blockless_workday` gemeldet): Kollaps auf den Beginn, 0 h — wie
 * `work_window_service.credit_blocks` → `[]`.
 */
export function hullClamp(
  blocks: TimeBlock[] | null | undefined, grace: number, start: string, end: string,
  blocklessWorkday = false,
): { start: string; end: string } {
  const startHHMM = start.substring(0, 5);
  const endHHMM = end.substring(0, 5);
  if (!blocklessWorkday && (!blocks || blocks.length === 0)) return { start: startHHMM, end: endHHMM };
  const s = hhmmToMinutes(start);
  const e = hhmmToMinutes(end);
  // Unvollständige Eingabe (leeres Feld) oder über Mitternacht: unverändert.
  if (Number.isNaN(s) || Number.isNaN(e) || e <= s) return { start: startHHMM, end: endHHMM };
  if (blocklessWorkday || !blocks) return { start: startHHMM, end: startHHMM };
  const mins = sortedMinutes(blocks);
  const lastEnd = mins[mins.length - 1][1];
  const floor = Math.max(0, Math.min(mins[0][0] - grace, LAST_MINUTE));
  const ceil = Math.max(0, Math.min(lastEnd + grace, LAST_MINUTE));
  const effS = s < floor ? floor : s;
  const effE = lastEnd < LAST_MINUTE && e > ceil ? ceil : e;
  if (effS >= effE) return { start: startHHMM, end: startHHMM };
  return { start: toHHMM(effS), end: toHHMM(effE) };
}

/**
 * Zwilling von `time_entries._running_credited_minutes` (#494, Ultrareview):
 * angerechnete Minuten des LAUFENDEN Eintrags (gespeicherter Beginn `start`) bis
 * `nowMinutes` (Minuten seit Mitternacht) — wie beim Ausstempeln: Hülle und
 * Lücke zwischen den Blöcken zählen nicht, die schon erfasste Pause wird
 * abgezogen, nie negativ. Liegt „jetzt" nicht nach dem Beginn (gekappter Beginn
 * #201), 0. Anerkannt oder ohne Blöcke: Wanduhrzeit minus Pause. Werktag ohne
 * Blöcke (`blocklessWorkday`), nicht anerkannt: 0.
 */
export function runningCreditedMinutes(
  blocks: TimeBlock[] | null | undefined, grace: number, start: string, nowMinutes: number,
  breakMinutes: number, creditOverride: boolean, blocklessWorkday = false,
): number {
  const s = hhmmToMinutes(start);
  const now = Math.min(Math.floor(nowMinutes), LAST_MINUTE);
  if (Number.isNaN(s) || now <= s) return 0;
  if (blocklessWorkday && !creditOverride) return 0;
  const brk = breakMinutes || 0;
  if (creditOverride || !blocks || blocks.length === 0) return Math.max(0, now - s - brk);
  const nowHHMM = toHHMM(now);
  const eff = hullClamp(blocks, grace, start, nowHHMM);
  const span = hhmmToMinutes(eff.end) - hhmmToMinutes(eff.start);
  const gap = gapSegments(blocks, grace, start, nowHHMM).reduce((a, b) => a + b, 0);
  return Math.max(0, span - gap - brk);
}

/** Spec 14 / E69: liegt `minutes` in einer UNGESCHRUMPFTEN Lücke (Ende Block i
 * bis Beginn Block i+1)? Laut Plan beginnt die Pause am Blockende, nicht erst
 * nach dem Puffer — der geschrumpfte Wert gilt nur für die Anrechnung. */
export function isInBlockGap(blocks: TimeBlock[] | null | undefined, minutes: number): boolean {
  if (!blocks || blocks.length < 2) return false;
  const mins = sortedMinutes(blocks);
  for (let i = 0; i + 1 < mins.length; i++) {
    if (mins[i][1] <= minutes && minutes < mins[i + 1][0]) return true;
  }
  return false;
}

/** Erster Beginn bis letztes Ende (Vorbelegung neuer Einträge, Spec 14).
 * `null` ohne Blöcke UND bei den Platzhaltern halboffener Altfenster (Spec 5.3):
 * Ende 23:59 heißt „kein Ende" (neue Zeilen enden spätestens 23:55, Spec 3.5),
 * Beginn 00:00 heißt „kein Beginn" — wie im Backend (`_clamp_core` kappt das
 * Ende nur bei `blocks[-1][1] < _LAST_MINUTE`). Der Aufrufer behält dann seine
 * bisherige Vorbelegung; sonst stünde 07:30–23:59 im Formular (→ DAILY_HOURS_HARD). */
export function blocksSpan(blocks: TimeBlock[] | null | undefined): { start: string; end: string } | null {
  if (!blocks || blocks.length === 0) return null;
  const mins = sortedMinutes(blocks);
  const first = mins[0][0];
  const last = Math.max(...mins.map(([, e]) => e));
  if (first === 0 || last === LAST_MINUTE) return null;
  return { start: toHHMM(first), end: toHHMM(last) };
}

export interface CreditEntry {
  start_time: string | null;
  end_time: string | null;
  raw_start_time?: string | null;
  raw_end_time?: string | null;
  uncredited_minutes?: number | null;
  auto_closed?: boolean | null;
}

/** Zwilling von `work_window_service.not_credited_minutes` (P19): Lücke +
 * von der Hülle gekappte Minuten; die Endseite eines automatisch geschlossenen
 * Eintrags zählt nicht (23:59 ist kein Stempel, P18). Jede Hüllen-Seite endet an
 * der Rohspanne (Ultrareview): die Startseite zählt nur bis zum
 * Anwesenheitsende, die Endseite erst ab dem Anwesenheitsbeginn — sonst ergab
 * ein Kollaps nach gekapptem Beginn (07:45–07:45, Rohstempel 05:00–06:00)
 * 165 Min. „nicht angerechnet" bei 60 Min. Anwesenheit. */
export function notCreditedMinutes(e: CreditEntry): number {
  let total = e.uncredited_minutes ?? 0;
  if (e.start_time && e.raw_start_time) {
    let cut = hhmmToMinutes(e.start_time);
    // Anwesenheitsende wie `presence_end`: Rohende, bei auto_closed das wirksame Ende.
    const presenceEnd = e.auto_closed ? e.end_time : (e.raw_end_time || e.end_time);
    if (presenceEnd) cut = Math.min(cut, hhmmToMinutes(presenceEnd));
    total += Math.max(0, cut - hhmmToMinutes(e.raw_start_time));
  }
  if (e.end_time && e.raw_end_time && !e.auto_closed) {
    const begin = Math.max(
      hhmmToMinutes(e.end_time),
      hhmmToMinutes(e.raw_start_time || e.start_time || e.end_time),
    );
    total += Math.max(0, hhmmToMinutes(e.raw_end_time) - begin);
  }
  return total;
}

export interface StampEntry extends CreditEntry {
  break_minutes?: number | null;
  net_hours?: number | null;
  not_credited_minutes?: number | null;
  credit_override?: boolean | null;
}

/** Spec 13.1: die Eingaben der Komponente `RawStampNote`. */
export interface StampNoteData {
  uncreditedMinutes: number;
  notCreditedMinutes: number;
  rawSpan: string;       // "08:00–18:00" aus raw_* oder start/end; offen: "07:00–"
  effSpan: string;       // gespeicherte start/end
  creditedHours: number; // net_hours (nach Pause und Lücke)
  breakMinutes: number;
  autoClosed: boolean;
  creditOverride: boolean;
}

export function stampNoteProps(e: StampEntry): StampNoteData {
  const hhmm = (t?: string | null) => (t ? t.substring(0, 5) : '');
  return {
    uncreditedMinutes: e.uncredited_minutes ?? 0,
    notCreditedMinutes: e.not_credited_minutes ?? notCreditedMinutes(e),
    rawSpan: `${hhmm(e.raw_start_time ?? e.start_time)}–${hhmm(e.raw_end_time ?? e.end_time)}`,
    effSpan: `${hhmm(e.start_time)}–${hhmm(e.end_time)}`,
    creditedHours: e.net_hours ?? 0,
    breakMinutes: e.break_minutes ?? 0,
    autoClosed: !!e.auto_closed,
    creditOverride: !!e.credit_override,
  };
}

/** Spec 15.2 — Zwilling von `work_blocks_service.blocks_text` (wortgleich):
 * lang „Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00",
 * kurz „Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00". Nur Tage mit Blöcken,
 * „Pause" nur bei Pause > 0 (Altwerte ohne Pausenangabe); `null` ohne Blöcke.
 * Anders als `formatWeekBlocks` (Spec 12.2, Trenner „·") trennt der Berichtstext
 * die Tage mit „ / " wie der Tagesplan der Vertragshistorie. */
export function formatBlocksText(
  week: WeekBlocks | null | undefined,
  { compact = false }: { compact?: boolean } = {},
): string | null {
  if (!Array.isArray(week)) return null;
  const parts = week.flatMap((day, index) => {
    const blocks = day?.blocks ?? [];
    if (blocks.length === 0 || index >= WEEKDAY_LABELS.length) return [];
    const spans = blocks.map((b) => `${b.start}–${b.end}`);
    const pause = day.pause_minutes;
    const text = compact
      ? spans.join('+') + (pause ? ` P${pause}` : '')
      : spans.join(' + ') + (pause ? ` (Pause ${pause} Min)` : '');
    return [`${WEEKDAY_LABELS[index]} ${text}`];
  });
  return parts.length > 0 ? parts.join(' / ') : null;
}

/** Spec 3.4: Grenze der Σ Tagessoll (gerundete Hundertstel wie 4.1, nicht
 * Netto-Minuten — sonst gäbe die Oberfläche eine Woche mit 60:00 h frei, die
 * gespeichert 60,01 h ergäbe und vom Server abgelehnt würde). */
const WEEK_LIMIT_HOURS = 60;

/** Wortgleich zu `work_blocks_service.WEEK_SHAPE_TEXT`. */
const WEEK_SHAPE_TEXT = 'Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet.';

/** Fünf Tage ohne Blöcke, Pause 0 — Ausgangszustand des Editors. */
export function emptyWeek(): WeekBlocks {
  return WEEKDAY_LABELS.map(() => ({ blocks: [], pause_minutes: 0 }));
}

/** Strenger Zwilling von `work_blocks_service.hhmm_to_minutes`: genau "HH:MM"
 * mit ASCII-Ziffern, 00:00–23:59 → Minuten seit Mitternacht, sonst `null`.
 * Das lockere `hhmmToMinutes` (Anzeige gespeicherter Werte, auch "HH:MM:SS")
 * bleibt unverändert. */
export function parseHhmm(value: string | null | undefined): number | null {
  if (typeof value !== 'string' || !/^[0-9]{2}:[0-9]{2}$/.test(value)) return null;
  const hours = Number(value.slice(0, 2));
  const minutes = Number(value.slice(3));
  return hours > 23 || minutes > 59 ? null : hours * 60 + minutes;
}

/** Minuten → "H:MM" (Anzeige des Editors, Review Focus 5: Minuten-genau, ohne
 * den Umweg über gerundete Stunden). */
export function minutesToHm(minutes: number): string {
  const abs = Math.abs(Math.round(minutes));
  return `${minutes < 0 ? '−' : ''}${Math.floor(abs / 60)}:${String(abs % 60).padStart(2, '0')}`;
}

export interface DayTotals {
  grossMinutes: number;
  pauseMinutes: number;
  netMinutes: number;
}

/** Blöcke eines Tages, ein fehlender/leerer Wert als „keine Blöcke" (wie
 * `day.get("blocks") or []`) — `validateWeekBlocks` reicht die Woche roh durch.
 * DIE eine Regel für Rechnung (`sumBlocks`, `deriveTargets`, `validateWeekBlocks`)
 * UND den `WorkBlocksEditor` — keine eigene Kopie im Aufrufer (Review Task 17). */
export function blocksOf(day: DayBlocks | null | undefined): TimeBlock[] {
  return Array.isArray(day?.blocks) ? day.blocks : [];
}

/** Live-Summen eines Tages; unvollständige Blöcke zählen nicht, eine leere Pause 0. */
export function sumBlocks(day: DayBlocks): DayTotals {
  const blocks = blocksOf(day);
  const gross = blocks.reduce((sum, b) => {
    const s = parseHhmm(b?.start);
    const e = parseHhmm(b?.end);
    return s !== null && e !== null && e > s ? sum + (e - s) : sum;
  }, 0);
  const pause = blocks.length && typeof day.pause_minutes === 'number' ? day.pause_minutes : 0;
  return { grossMinutes: gross, pauseMinutes: pause, netMinutes: Math.max(0, gross - pause) };
}

/** Spec 4.1: Netto-Minuten → Tagessoll in Stunden, 0,01 HALF_EVEN — exakt ohne
 * Fließkomma: Hundertstel = 5n/3, der Rest 5n mod 3 ist nie genau 1,5, ein
 * Gleichstand zum Abrunden auf die gerade Ziffer kommt also nie vor. */
export function minutesToTargetHours(net: number): number {
  const five = 5 * net;
  return (Math.floor(five / 3) + (five % 3 === 2 ? 1 : 0)) / 100;
}

/** Zwilling von `work_blocks_service.derive_targets` (nur Anzeige/Vergleich —
 * gespeichert wird, was der Server ableitet). */
export function deriveTargets(week: WeekBlocks): { hours: number[]; weeklyHours: number; workDays: number } {
  const hours = WEEKDAY_LABELS.map((_, i) => (
    blocksOf(week[i]).length ? minutesToTargetHours(sumBlocks(week[i]).netMinutes) : 0
  ));
  return {
    hours,
    // Σ der Hundertstel als Ganzzahl, damit 11,42 + 11,42 + … nicht als
    // 60,010000000000005 an der 60-h-Grenze vorbeirutscht.
    weeklyHours: hours.reduce((a, b) => a + Math.round(b * 100), 0) / 100,
    workDays: week.filter((d) => blocksOf(d).length > 0).length,
  };
}

function isDayObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Zwilling von `schemas/validators.validate_week_blocks` — wortgleiche Texte
 * (Spec 3.4), Text der ERSTEN verletzten Regel oder `null`. Auch kaputte Formen
 * (kein Tag-Objekt, `blocks` keine Liste) enden in derselben Meldung wie im
 * Backend, nie in einem TypeError beim Tippen. */
export function validateWeekBlocks(week: WeekBlocks | null | undefined): string | null {
  if (!Array.isArray(week) || week.length !== 5) return WEEK_SHAPE_TEXT;
  for (let i = 0; i < 5; i++) {
    const label = WEEKDAY_LABELS[i];
    const rawDay: unknown = week[i];
    if (!isDayObject(rawDay)) return WEEK_SHAPE_TEXT;
    // Wie `day.get("blocks") or []`: ein leerer/fehlender Wert ist „keine Blöcke" —
    // auch ein leeres Objekt, das in Python falsy ist, in JS aber truthy.
    const b = rawDay.blocks;
    const rawBlocks = !b || (isDayObject(b) && Object.keys(b).length === 0) ? [] : b;
    if (!Array.isArray(rawBlocks)) return `${label}: Tag nicht in der Form {blocks, pause_minutes}.`;
    const blocks = rawBlocks as (Partial<TimeBlock> | null | undefined)[];
    if (blocks.length > 3) return `${label}: höchstens drei Blöcke je Tag.`;
    const spans: [number, number][] = [];
    for (let n = 0; n < blocks.length; n++) {
      const s = parseHhmm(blocks[n]?.start);
      const e = parseHhmm(blocks[n]?.end);
      if (s === null || e === null) return `${label}, Block ${n + 1}: Uhrzeit im Format HH:MM angeben.`;
      if (s % 5 || e % 5) return `${label}, Block ${n + 1}: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).`;
      if (s >= e) return `${label}, Block ${n + 1}: Beginn muss vor dem Ende liegen.`;
      spans.push([s, e]);
    }
    for (let n = 1; n < spans.length; n++) {
      if (spans[n][0] <= spans[n - 1][1]) {
        return `${label}: Block ${n + 1} muss nach dem Ende von Block ${n} beginnen; aneinandergrenzende Blöcke bitte als einen Block erfassen.`;
      }
    }
    const pause = rawDay.pause_minutes;
    if (pause === null || pause === undefined) return `${label}: Pause angeben (0, wenn keine).`;
    if (typeof pause !== 'number' || !Number.isInteger(pause) || pause < 0 || pause % 5) {
      return `${label}: Pause in Minuten im 5-Minuten-Raster angeben.`;
    }
    if (!spans.length && pause !== 0) return `${label}: Pause nur an Tagen mit Blöcken.`;
    const gross = spans.reduce((sum, [s, e]) => sum + e - s, 0);
    if (spans.length && pause >= gross) return `${label}: Pause muss kürzer sein als die Gesamtzeit der Blöcke.`;
  }
  if (!week.some((d) => blocksOf(d).length > 0)) return 'Mindestens ein Wochentag braucht einen Block.';
  if (deriveTargets(week).weeklyHours > WEEK_LIMIT_HOURS) return 'Die Wochensumme darf 60 Stunden nicht überschreiten.';
  return null;
}
