/**
 * Feste Beispielwerte der Diagramme „So rechnet PraxisZeit".
 * Eine Quelle für Diagramme, rechenbeispiele.json (Task 12) und den Backend-Test,
 * der jede Zahl nachrechnet. Abschnittsnummern: docs/BERECHNUNGEN.md.
 */

// ---- tag-zeitstrahl: §4.1 Arbeitszeit-Blöcke und Kappung (work_window_service.clamp) ----
/** Puffer `work_window_grace_minutes` (Default 15). */
export const GRACE = 15;
/** Arbeitszeit-Blöcke des Tages, Minuten ab 00:00 (08:00–12:00, 15:00–16:00), Pause im Plan 0. */
export const BLOCKS = [
  { start: 8 * 60, end: 12 * 60 },
  { start: 15 * 60, end: 16 * 60 },
] as const;
/** Hülle = erster Block − g … letzter Block + g. */
export const HULL = { start: '07:45', end: '16:15' } as const;
/** Lücke 12:00–15:00, an beiden Rändern um g geschrumpft (`credit_gaps`); eine Lücke ≤ 2 × g verschwindet. */
export const GAP_SHRUNK = { start: '12:15', end: '14:45' } as const;
/**
 * Zeiteintrag 1: gestempelt 07:30–12:10 → gespeichert 07:45–12:10 (Beginn auf Hülle verschoben,
 * Rohstempel 07:30). 12:10 liegt noch im Puffer des Blocks (vor 12:15), also keine Lücke:
 * uncredited 0, net_hours 4:25 h = 4,42 h, nicht angerechnet 15 min (Hülle).
 */
export const ENTRY_A = {
  stamp: '07:30–12:10', stored: '07:45–12:10', credited: '4:25', creditedHours: 4.42,
  uncreditedMin: 0, notCreditedMin: 15,
} as const;
/**
 * Zeiteintrag 2: gestempelt 13:00–16:30 → gespeichert 13:00–16:15 (Beginn in der Lücke wird NIE
 * verschoben; Ende auf Hülle gekappt, Rohende 16:30). uncredited = Überlappung mit der
 * geschrumpften Lücke 13:00–14:45 = 105 min; net 14:45–16:15 = 1:30 h = 1,5 h;
 * nicht angerechnet = 105 + 15 = 120 min.
 */
export const ENTRY_B = {
  stamp: '13:00–16:30', stored: '13:00–16:15', credited: '1:30', creditedHours: 1.5,
  uncreditedMin: 105, notCreditedMin: 120,
} as const;

// ---- soll-ist: §13.1 Beispiel Monatssaldo (Vollzeit 40 h / 5 Tage, Tagessoll 8,00 h, §3.1) ----
export const WORKDAYS = 22;
export const HOLIDAYS = 1;
export const VACATION_DAYS_TAKEN = 4;
/** 22 − 1 − 4 = 17 Soll-relevante Arbeitstage. */
export const SOLL_DAYS = WORKDAYS - HOLIDAYS - VACATION_DAYS_TAKEN;
export const DAY_TARGET = 8;
/** 17 × 8,00 h = 136,00 h. */
export const SOLL_HOURS = SOLL_DAYS * DAY_TARGET;
/** 14 × 8,00 h + 3 × 8,50 h = 137,50 h. */
export const IST_HOURS = 14 * 8 + 3 * 8.5;
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
export const CLOSURE_DAYS = [
  { label: 'Mo', type: 'VACATION', restAfter: 2 },
  { label: 'Di', type: 'VACATION', restAfter: 1 },
  { label: 'Mi', type: 'VACATION', restAfter: 0 },
  { label: 'Do', type: 'OVERTIME', restAfter: 0 },
  { label: 'Fr', type: 'OVERTIME', restAfter: 0 },
] as const;
/** 2 Überstundenausgleich-Tage × 8,00 h (Beispiel 13.3: Konto sinkt um das Tagessoll). */
export const CLOSURE_OVERTIME_HOURS = 2 * DAY_TARGET;
