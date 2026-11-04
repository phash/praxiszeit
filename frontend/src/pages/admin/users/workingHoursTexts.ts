// Spec 2026-10-08, 12.1/9.5/P26: feste Texte des Dialogs „Arbeitszeit &
// Wochenstunden" — an EINER Stelle, damit Dialog, Verkürzungs-Kasten und
// Lösch-Dialog wortgleich bleiben. Die Grundtyp-SCHLÜSSEL sind eingefroren
// (Backend `reclamp_audit.REASON_TYPES`), die Oberfläche zeigt nur die Beschriftungen.
import { formatDayCount, formatDayNumber, formatHoursHM } from '../../../utils/formatters';
import type { ContractTerms, WorkingHoursChangePreview } from './workingHoursTypes';

export const LEGAL_HINT =
  'Ändert sich der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und braucht das '
  + 'Einverständnis der beschäftigten Person. Die Lage kann, soweit der Vertrag sie nicht festlegt, im Rahmen des '
  + 'Direktionsrechts (§ 106 GewO) nach billigem Ermessen und mit angemessener Ankündigung nur für die Zukunft '
  + 'geändert werden. Vereinbarte Arbeitszeiten und Pausen sind spätestens am Tag des Wirksamwerdens schriftlich '
  + 'mitzuteilen (§ 3 NachwG). Mit Betriebsrat ist die Änderung mitbestimmungspflichtig (§ 87 Abs. 1 Nr. 2, 3 und 6 '
  + 'BetrVG). PraxisZeit prüft das nicht.';
export const JARBSCHG_HINT =
  'Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG); PraxisZeit prüft diese nicht.';
export const LEGACY_BOX_TITLE = 'Arbeitszeit-Fenster (Altbestand, nur Kappung)';
export const BLOCKS_WITHOUT_EFFECT = 'Arbeitszeit-Blöcke gespeichert, ohne Wirkung (keine Stundenzählung)';
/** Spec 4.4: ein Altfenster heißt auch ohne Stundenzählung nie „Blöcke" (Dialog + UserForm). */
export const LEGACY_WITHOUT_EFFECT = 'Arbeitszeit-Fenster aus dem Altbestand gespeichert, ohne Wirkung (keine Stundenzählung)';
/** P24: Moduswechsel weg von Blöcken; `date` bereits als TT.MM.JJJJ (`formatDate`). */
export const modeSwitchHint = (date: string) =>
  `Die Arbeitszeit-Blöcke enden mit dieser Änderung; ab ${date} wird nicht mehr gekappt.`;

export const REASON_HELP = 'Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.';
export const WAGE_SENTENCE =
  'Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist unabhängig von der Anrechnung '
  + 'zu vergüten (§ 611a, § 612 BGB). Auf den Mindestlohn für geleistete Stunden kann nicht verzichtet werden (§ 3 MiLoG).';
export const OTHER_WARNING =
  'Eine einseitige rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO wirkt nur für die Zukunft); '
  + 'geleistete Arbeit bleibt zu vergüten.';
export const OTHER_CONFIRM = 'Mir ist bewusst, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht nicht gedeckt ist.';

export type RetroReasonKey = 'erfassungsfehler' | 'einvernehmlich' | 'sonstiges';
export const REASON_OPTIONS: { value: RetroReasonKey; label: string; confirm: string }[] = [
  {
    value: 'erfassungsfehler',
    label: 'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)',
    confirm: `Ich habe geprüft, dass die hinterlegte Arbeitszeit falsch war (Fehlerkorrektur). ${WAGE_SENTENCE}`,
  },
  {
    value: 'einvernehmlich',
    label: 'Mit der beschäftigten Person vereinbart',
    confirm: `Ich habe geprüft, dass die rückwirkende Änderung mit der beschäftigten Person vereinbart ist. ${WAGE_SENTENCE}`,
  },
  { value: 'sonstiges', label: 'Sonstiges', confirm: `Ich habe die Gründe geprüft. ${WAGE_SENTENCE}` },
];
/** Notiz-Präfix je Grundtyp — wortgleich `reclamp_audit.REASON_TYPES[…].prefix` (eingefroren, 9.5). */
export const REASON_PREFIXES: Record<RetroReasonKey, string> = {
  erfassungsfehler: '[Erfassungsfehler korrigiert]',
  einvernehmlich: '[Einvernehmlich vereinbart]',
  sonstiges: '[Sonstiges]',
};

/** Spec 9.5 — wortgleich `reclamp_audit.NOTE_MAX_LENGTH` / `NOTE_TOO_LONG_DETAIL`. */
export const NOTE_MAX_LENGTH = 500;
export const NOTE_TOO_LONG = 'Notiz und Begründung zusammen höchstens 500 Zeichen.';

export type ShorteningOption = 'lossless' | 'retro';

export interface ReasonState {
  type: RetroReasonKey | '';
  text: string;
  wageConfirmed: boolean;
  otherConfirmed: boolean;
}

export const EMPTY_REASON: ReasonState = { type: '', text: '', wageConfirmed: false, otherConfirmed: false };

/** P15/P26: Grundtyp, 10–400 Zeichen Begründung, Haken; bei „Sonstiges" zweiter Haken. */
export function reasonComplete(r: ReasonState): boolean {
  // In Zeichen (Codepoints) wie Pydantic/Python `len` — `.length` zählte
  // UTF-16-Einheiten, ein Emoji also doppelt.
  const len = [...r.text.trim()].length;
  return !!r.type && len >= 10 && len <= 400 && r.wageConfirmed && (r.type !== 'sonstiges' || r.otherConfirmed);
}

/**
 * Spec 9.5 (Gesamtreview PR3): passt die gespeicherte Notiz — Grund-Präfix,
 * Begründung und „ · Notiz" — in 500 Zeichen? Dieselbe Zusammensetzung wie
 * `reclamp_audit.compose_change_note` und dieselbe Bedingung wie das
 * Schreibschema (nur mit Grundtyp UND Begründung); gezählt in Codepoints wie
 * Python `len`. Ohne diese Prüfung kam die 422 erst beim Speichern als Toast.
 */
export function composedNoteTooLong(r: ReasonState, note: string): boolean {
  const text = r.text.trim();
  if (!r.type || !text) return false;
  const extra = note.trim();
  const composed = `${REASON_PREFIXES[r.type]} ${text}${extra ? ` · ${extra}` : ''}`;
  return [...composed].length > NOTE_MAX_LENGTH;
}

/** Body-Felder des Schutzpakets (Anlegen und DELETE, Spec 11.2). */
export function reasonPayload(r: ReasonState): Record<string, unknown> {
  return {
    retroactive_reason_type: r.type,
    retroactive_reason_text: r.text.trim(),
    wage_risk_confirmed: r.wageConfirmed,
    other_reason_risk_confirmed: r.type === 'sonstiges' ? r.otherConfirmed : false,
  };
}

/** Wie `reclamp_audit.SKIP_LABELS` (Übersprungen-Gründe der Neukappung). */
export const SKIP_LABELS: Record<string, string> = {
  credit_override: 'anerkannt',
  open: 'offen',
  soll_free_day: 'Sonn-/Feiertag',
  track_hours_off: 'ohne Stundenzählung',
  outside_employment: 'außerhalb der Beschäftigung',
  unique_collision: 'Überschneidung',
};

/**
 * Hinweis bei Verlust in einem abgeschlossenen Jahr. Sperrt NICHT (Kundenfall
 * 2026-11-02, bis 1.21.0 eine harte 400): gespeichert wird mit Grund und Haken
 * wie jede rückwirkende Verkürzung, danach den Jahresabschluss erneut ausführen.
 */
export function closedYearMessage(years: number[] | null | undefined): string | null {
  if (!years || years.length === 0) return null;
  const sorted = [...years].sort((a, b) => a - b);
  const list = sorted.join(', ');
  const plural = sorted.length > 1;
  return `Die Verkürzung reicht in ${plural ? 'die abgeschlossenen Jahre' : 'das abgeschlossene Jahr'} ${list}. `
    + `Gespeichert wird mit Begründung; danach bitte den Jahresabschluss ${list} erneut ausführen.`;
}

/** "2026-09-07" → "07.09.2026" (reine Zeichenkette, keine Zeitzonen-Umrechnung). */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y}`;
}

/** "2026-09-07" → "07.09." (Listen in der Auswirkungs-Box). */
export function shortDate(iso: string): string {
  const [, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.`;
}

const MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
/** "2026-09" → "Sep 2026" (Monatszeilen der Auswirkungs-Box, Spec 12.1). */
export function monthLabel(yyyyMm: string): string {
  const [y, m] = yyyyMm.split('-');
  return `${MONTHS[Number(m) - 1]} ${y}`;
}

/** Betrag in H:MM über `formatHoursHM` (wie im Rest der App), ohne Vorzeichen. */
export function hm(hours: number): string {
  return formatHoursHM(Math.abs(hours));
}

/** „+1:45" / „−3:45" (U+2212) / „0:00" — das Vorzeichen folgt dem angezeigten
 * Wert: was als 0:00 erscheint, bekommt keins. */
export function signedHm(hours: number): string {
  const text = hm(hours);
  if (text === '0:00') return text;
  return `${hours > 0 ? '+' : '−'}${text}`;
}

/** „+1 Tag" / „−1,5 Tage" / „0 Tage" — Urlaubstage-Δ in derselben
 * Schreibweise wie die Spalten „bisher"/„neu" daneben und wie im Rest der App
 * (`formatDayCount`, #496; Einheit inklusive). Was als „0 Tage" erscheint,
 * bekommt kein Vorzeichen. */
export function signedDays(value: number): string {
  const v = Math.round(value * 100) / 100;
  const text = formatDayCount(Math.abs(v));
  return v > 0 ? `+${text}` : v < 0 ? `−${text}` : text;
}

/** Spec 12.1 — Toast nach dem Speichern (bzw. Löschen, gleiche Zählung). */
export function savedMessage(
  created: { adjusted_time_entries?: number; skipped_time_entries?: number; adjusted_absences?: number },
  verb: 'Gespeichert' | 'Gelöscht' = 'Gespeichert',
): string {
  const parts: string[] = [];
  const n = created.adjusted_time_entries ?? 0;
  const k = created.skipped_time_entries ?? 0;
  const a = created.adjusted_absences ?? 0;
  // Wortlaute zusammenhängend im Quelltext — das Doku-Gate (PR4) sucht sie per grep.
  if (n > 0) parts.push(n === 1 ? '1 Zeiteintrag neu berechnet' : `${n} Zeiteinträge neu berechnet`);
  if (k > 0) parts.push(`${k} übersprungen`);
  if (a > 0) parts.push(`${a} ${a === 1 ? 'Abwesenheit' : 'Abwesenheiten'} angepasst`);
  return parts.length ? `${verb}. ${parts.join(', ')}.` : `${verb}.`;
}

/** Kalendertag VOR dem ISO-Datum — UTC-basiert (reine Tagesarithmetik, kein
 * Zeitzonen-/Sommerzeit-Sprung). Verlauf „bis …" und Lösch-Hinweis (12.1). */
export function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().split('T')[0];
}

// Verkürzungs-Kasten (`ShorteningChoice`, Spec 12.1/P1/P25) — hier statt in der
// Komponentendatei, damit diese nur Komponenten exportiert (Fast Refresh).

/** Spec 12.1: Kopfzeile je erfülltem Kriterium aus `shortening_reasons` (9.5). */
export function shorteningHeadlines(p: WorkingHoursChangePreview): string[] {
  const reasons = p.shortening_reasons ?? [];
  const out: string[] = [];
  if (reasons.includes('entries')) {
    // Der heute offene Eintrag (P1) steht nicht in `time_entry_changes`; ob er
    // verliert, sagt `open_entry_loses` — gezählt wie `criteria_text` in der
    // 400-Meldung (9.5 (a)). Sein Verlust ist nicht bezifferbar (das Ende ist
    // unbekannt), die Summe nennt nur die geschlossenen Einträge. `|| 1`: das
    // Kriterium ist erfüllt, also verliert mindestens einer.
    const closedLosing = (p.time_entry_changes ?? []).filter((c) => c.new_net < c.old_net).length;
    const n = closedLosing + (p.open_entry_loses ? 1 : 0) || 1;
    const lost = p.lost_credited_hours ?? 0;
    out.push(`${n === 1 ? '1 Eintrag verliert' : `${n} Einträge verlieren`} angerechnete Zeit`
      + (lost > 0 ? ` (zusammen ${hm(lost)} h)` : ''));
  }
  if (reasons.includes('saldo')) {
    const saldo = p.saldo_delta_hours ?? 0;
    const openDay = p.open_day_saldo_delta_hours ?? 0;
    if (saldo < 0) {
      const extra = !reasons.includes('entries') && (p.target_delta_hours ?? 0) > 0
        ? ' (höheres Soll), obwohl kein Eintrag angerechnete Zeit verliert'
        : '';
      out.push(`Das Überstundenkonto sinkt im Wirkungsbereich um ${hm(saldo)} h${extra}`);
    }
    if (openDay < 0) {
      out.push(`Heute steigt das Soll um ${hm(openDay)} h, während die Person eingestempelt ist – das Überstundenkonto sinkt beim Ausstempeln.`);
    }
    // (b) allein über den Anteil eines abgeschlossenen Jahres (dessen Saldo ist
    // eingefroren, spätere Gewinne gleichen ihn nicht aus) — wie `criteria_text`.
    if (saldo >= 0 && openDay >= 0) {
      out.push(`Das Überstundenkonto sinkt im abgeschlossenen Jahr ${(p.shortening_closed_years ?? []).join(', ')}`);
    }
  }
  if (reasons.includes('absence_credit')) {
    const n = (p.absence_credit_reductions ?? []).length;
    out.push(`${n === 1 ? '1 Abwesenheits-Gutschrift sinkt' : `${n} Abwesenheits-Gutschriften sinken`} stärker als das `
      + 'Tagessoll (Arbeit und Gutschrift am selben Tag)');
  }
  if (reasons.includes('vacation_entitlement')) {
    for (const e of p.vacation_entitlement ?? []) {
      if (e.after < e.before) {
        out.push(`Der Urlaubsanspruch ${e.year} sinkt von ${formatDayNumber(e.before)} auf ${formatDayNumber(e.after)} Tage`);
      }
    }
  }
  return out;
}

/** P1/P25: Beschriftung der verlustfreien Option oder `null` (nicht angeboten). */
export function losslessLabel(p: WorkingHoursChangePreview, today: string): string | null {
  const d = p.earliest_lossless_date;
  if (!d) return null;
  const suffix = (p.shortening_reasons ?? []).includes('entries')
    ? 'vergangene Einträge bleiben unverändert'
    : 'vergangene Tage bleiben unverändert';
  return d === today ? `Ab heute (${formatDate(d)}) wirksam – ${suffix}` : `Ab ${formatDate(d)} wirksam – ${suffix}`;
}

export function retroLabel(requestedDate: string): string {
  return `Rückwirkend ab ${formatDate(requestedDate)} mit Neuberechnung`;
}

/**
 * Teil A (Spec „Dialog"): Vorschlag für den Urlaubsanspruch, sobald sich die
 * Zahl der Arbeitstage ändert — alter Anspruch × neue ÷ alte Arbeitstage, auf
 * 0,1 gerundet (24 × 5 ÷ 4 = 30). Ein praxisindividueller Anspruch bleibt so im
 * Verhältnis erhalten. `null` = kein Vorschlag (keine oder unveränderte Tage).
 */
export function suggestEntitlement(oldDays: number, oldWd: number, newWd: number): number | null {
  if (oldWd <= 0 || newWd <= 0 || newWd === oldWd) return null;
  return Math.round(oldDays * newWd / oldWd * 10) / 10;
}

/** Teil A: die fünf Vertragsfelder aus einem Snapshot (`schedule_today`, User-Zeile)
 * — `undefined`, wenn Anspruch oder Stundenzählung fehlen (ältere Antwort). */
export function contractTermsOf(source: {
  vacation_days?: number | null;
  track_hours?: boolean | null;
  milog_working_time_account?: boolean | null;
  agreed_monthly_hours?: number | null;
  use_fixed_monthly_target?: boolean | null;
} | null | undefined): ContractTerms | undefined {
  if (!source || source.vacation_days == null || source.track_hours == null) return undefined;
  return {
    vacation_days: source.vacation_days,
    track_hours: source.track_hours,
    milog_working_time_account: !!source.milog_working_time_account,
    agreed_monthly_hours: source.agreed_monthly_hours ?? null,
    use_fixed_monthly_target: !!source.use_fixed_monthly_target,
  };
}
