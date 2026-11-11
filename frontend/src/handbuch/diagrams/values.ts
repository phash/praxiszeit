/**
 * Feste Beispielwerte der Diagramme „So rechnet PraxisZeit".
 * Eine Quelle für Diagramme, rechenbeispiele.json (Task 12) und den Backend-Test,
 * der jede Zahl nachrechnet. Abschnittsnummern: docs/BERECHNUNGEN.md.
 */

// ---- tag-zeitstrahl: §4.1 Arbeitszeit-Blöcke und Kappung (work_window_service.clamp) ----
/** Puffer `work_window_grace_minutes` (Default 15). */
export const GRACE = 15;
export const hm = (h: number, m = 0) => h * 60 + m;
/** Minuten → "HH:MM". */
export const hhmm = (min: number) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;
/** Arbeitszeit-Blöcke des Tages (08:00–12:00, 15:00–16:00), Pause im Plan 0. */
export const BLOCKS = [
  { start: hm(8), end: hm(12) },
  { start: hm(15), end: hm(16) },
] as const;
/** Hülle = erster Block − g … letzter Block + g. */
export const HULL = { start: BLOCKS[0].start - GRACE, end: BLOCKS[1].end + GRACE };
/**
 * Lücke zwischen zwei Blöcken (Ende A, Beginn B), an beiden Rändern um `grace` geschrumpft
 * (`credit_gaps`); eine Lücke ≤ 2 × grace verschwindet (`null`).
 */
export function shrinkGap(endA: number, startB: number, grace: number): { start: number; end: number } | null {
  const start = endA + grace;
  const end = startB - grace;
  return end > start ? { start, end } : null;
}
/** Die geschrumpfte Lücke der Beispiel-Blöcke (12:00–15:00 → 12:15–14:45). */
export const GAP_SHRUNK = shrinkGap(BLOCKS[0].end, BLOCKS[1].start, GRACE);

/**
 * Kappung eines Zeiteintrags wie `work_window_service._clamp_core`: Beginn/Ende an der Hülle
 * verschoben (ein Beginn in der Lücke bleibt), Überlappung mit der geschrumpften Lücke =
 * `uncredited`, net = Ende − Beginn − uncredited, „nicht angerechnet" = uncredited + an der Hülle
 * abgeschnittene Minuten (§4.1).
 */
export function clampEntry(start: number, end: number) {
  const effStart = Math.max(start, HULL.start);
  const effEnd = Math.min(end, HULL.end);
  const gs = GAP_SHRUNK ? Math.max(effStart, GAP_SHRUNK.start) : 0;
  const ge = GAP_SHRUNK ? Math.min(effEnd, GAP_SHRUNK.end) : 0;
  const gapOverlap = ge > gs ? { start: gs, end: ge } : null;
  const uncreditedMin = gapOverlap ? gapOverlap.end - gapOverlap.start : 0;
  const netMin = effEnd - effStart - uncreditedMin;
  return {
    start, end, effStart, effEnd, gapOverlap, uncreditedMin, netMin,
    credited: `${Math.floor(netMin / 60)}:${String(netMin % 60).padStart(2, '0')}`,
    creditedHours: Math.round((netMin / 60) * 100) / 100,
    notCreditedMin: uncreditedMin + (effStart - start) + (end - effEnd),
    stamp: `${hhmm(start)}–${hhmm(end)}`,
  };
}
/** Zeiteintrag 1: 07:30–12:10 → 07:45–12:10; 12:10 liegt noch im Puffer (vor 12:15), keine Lücke. */
export const ENTRY_A = clampEntry(hm(7, 30), hm(12, 10));
/** Zeiteintrag 2: 13:00–16:30 → 13:00–16:15 (Beginn in der Lücke wird nie verschoben). */
export const ENTRY_B = clampEntry(hm(13), hm(16, 30));

// ---- soll-ist: §13.1 Beispiel Monatssaldo (Vollzeit 40 h / 5 Tage, Tagessoll 8,00 h, §3.1) ----
export const WORKDAYS = 22;
export const HOLIDAYS = 1;
export const VACATION_DAYS_TAKEN = 4;
/** 22 − 1 − 4 = 17 Soll-relevante Arbeitstage. */
export const SOLL_DAYS = WORKDAYS - HOLIDAYS - VACATION_DAYS_TAKEN;
export const DAY_TARGET = 8;
/** 17 × 8,00 h = 136,00 h. */
export const SOLL_HOURS = SOLL_DAYS * DAY_TARGET;
/** 14 Tage × 8,00 h + 3 Tage × 8,50 h = 137,50 h. */
export const IST_PARTS = [{ days: 14, hours: 8 }, { days: 3, hours: 8.5 }] as const;
export const IST_HOURS = IST_PARTS.reduce((s, p) => s + p.days * p.hours, 0);
/** §7.1 Monatssaldo = Ist − Soll = +1,50 h. */
export const SALDO_HOURS = IST_HOURS - SOLL_HOURS;

// ---- saldo-monat: §7.1 Monatssaldo, §7.2 kumuliertes Konto (ohne Übertrag, Startwert 0) ----
/**
 * Jan = +1,50 h (Beispiel 13.1), Feb = −8,00 h (ein Tag Überstundenausgleich, Beispiel 13.3);
 * Mär/Apr erfundene Beispielwerte. Konto = Σ Monatssalden.
 */
export const MONTHS = [
  { name: 'Jan.', saldo: 1.5, konto: 1.5 },
  { name: 'Feb.', saldo: -8, konto: -6.5 },
  { name: 'Mär.', saldo: 6, konto: -0.5 },
  { name: 'Apr.', saldo: 2.5, konto: 2 },
] as const;

// ---- urlaubskonto: §8.1 Budget, §8.2 Verbrauch, §8.3 Rest, Beispiel 13.4 ----
/** Anspruch Vollzeit 30 × 5/5 = 30 Tage. */
export const VAC_ENTITLEMENT = 30;
/** Übertrag aus dem Vorjahr (Beispielwert; Formel budget_days = vacation_days + carryover_days). */
export const VAC_CARRYOVER = 2;
export const VAC_BUDGET = VAC_ENTITLEMENT + VAC_CARRYOVER;
/** 4 volle Urlaubstage (Beispiel 13.4, je 8,00 h ÷ 8,00 h = 1,0 Tag). */
export const VAC_USED = 4;
export const VAC_REMAINING = VAC_BUDGET - VAC_USED;

// ---- betriebsferien-split: §9.4 (#314), chronologisch, Tageskosten 1,0 ----
/** Resturlaub vor der Schließung (Beispielwert), Schließung Mo–Fr = 5 Arbeitstage. */
export const CLOSURE_REST_BEFORE = 3;
export const CLOSURE_WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr'] as const;
/** Chronologisch: Urlaub, solange Rest ≥ 1 (Tageskosten 1,0), danach OVERTIME. */
export const CLOSURE_DAYS = (() => {
  let rest = CLOSURE_REST_BEFORE;
  return CLOSURE_WEEKDAYS.map((label) => {
    const type = rest >= 1 ? ('VACATION' as const) : ('OVERTIME' as const);
    const restBefore = rest;
    if (type === 'VACATION') rest -= 1;
    return { label, type, restBefore, restAfter: rest };
  });
})();
/** Anzahl Überstundenausgleich-Tage × Tagessoll (Beispiel 13.3: Konto sinkt um das Tagessoll) = 16,00 h. */
export const CLOSURE_OVERTIME_DAYS = CLOSURE_DAYS.filter((d) => d.type === 'OVERTIME').length;
export const CLOSURE_OVERTIME_HOURS = CLOSURE_OVERTIME_DAYS * DAY_TARGET;
