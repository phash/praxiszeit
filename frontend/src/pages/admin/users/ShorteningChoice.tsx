import { AlertTriangle } from 'lucide-react';
import type { WorkingHoursChangePreview } from './workingHoursTypes';
import {
  OTHER_CONFIRM, OTHER_WARNING, REASON_HELP, REASON_OPTIONS, formatDate, hm,
  type ReasonState, type RetroReasonKey, type ShorteningOption,
} from './workingHoursTexts';

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

interface RetroReasonFieldsProps {
  value: ReasonState;
  onChange: (value: ReasonState) => void;
  idPrefix: string;
  milogWarnings?: string[];
}

/** Spec 12.1/P26: Grund, Begründung (10–400), Bestätigung je Grundtyp. Ein
 * Wechsel des Grundtyps setzt die Haken zurück — ihr Wortlaut ändert sich. */
export function RetroReasonFields({ value, onChange, idPrefix, milogWarnings = [] }: RetroReasonFieldsProps) {
  const option = REASON_OPTIONS.find((o) => o.value === value.type);
  // In Zeichen (Codepoints) wie `reasonComplete` und das Backend.
  const length = [...value.text.trim()].length;
  return (
    <div className="mt-2 space-y-2 sm:pl-6 min-w-0">
      <div>
        <label htmlFor={`${idPrefix}-reason-type`} className="block text-sm font-medium text-gray-800">Grund</label>
        <select
          id={`${idPrefix}-reason-type`}
          value={value.type}
          onChange={(e) => onChange({
            ...value, type: e.target.value as RetroReasonKey | '', wageConfirmed: false, otherConfirmed: false,
          })}
          className="mt-1 w-full max-w-full px-2 py-1 border border-gray-300 rounded-lg text-sm bg-white"
        >
          <option value="">Bitte wählen…</option>
          {REASON_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {/* P26: fest unter der Auswahl, bei jedem Grundtyp sichtbar. */}
        <p className="text-xs text-gray-600 mt-1">{REASON_HELP}</p>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-reason-text`} className="block text-sm font-medium text-gray-800">Begründung</label>
        <textarea
          id={`${idPrefix}-reason-text`}
          value={value.text}
          maxLength={400}
          rows={2}
          onChange={(e) => onChange({ ...value, text: e.target.value })}
          className="mt-1 w-full px-2 py-1 border border-gray-300 rounded-lg text-sm"
        />
        <p className="text-xs text-gray-500">{`${length}/400 Zeichen (mindestens 10)`}</p>
      </div>
      {option && (
        <label className="flex items-start gap-2 text-gray-900 cursor-pointer">
          <input
            type="checkbox"
            checked={value.wageConfirmed}
            onChange={(e) => onChange({ ...value, wageConfirmed: e.target.checked })}
            className="mt-0.5 w-4 h-4 shrink-0"
          />
          <span>{option.confirm}</span>
        </label>
      )}
      {value.type === 'sonstiges' && (
        <>
          <p className="font-medium text-red-700">{OTHER_WARNING}</p>
          <label className="flex items-start gap-2 text-gray-900 cursor-pointer">
            <input
              type="checkbox"
              checked={value.otherConfirmed}
              onChange={(e) => onChange({ ...value, otherConfirmed: e.target.checked })}
              className="mt-0.5 w-4 h-4 shrink-0"
            />
            <span>{OTHER_CONFIRM}</span>
          </label>
        </>
      )}
      {milogWarnings.map((w) => (
        <p key={w} className="flex gap-1 text-amber-900">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden="true" />
          {w}
        </p>
      ))}
    </div>
  );
}

interface ShorteningChoiceProps {
  preview: WorkingHoursChangePreview;
  /** Option 1 — `null`: nicht angeboten (P25). */
  losslessText: string | null;
  /** Erklärung unter Option 1, wenn gewählt (Rücksetzung beim Löschen). */
  losslessNote?: string | null;
  retroText: string;
  option: ShorteningOption;
  onOptionChange: (option: ShorteningOption) => void;
  /** Text der 400-Meldung bei Verlust in einem abgeschlossenen Jahr. */
  closedText: string | null;
  reason: ReasonState;
  onReasonChange: (reason: ReasonState) => void;
  idPrefix: string;
}

/**
 * Spec 2026-10-08, 9.5/12.1: Kasten „Verkürzung" — gemeinsam für Anlegen und
 * Löschen. Die Optionen leiten sich IMMER aus der Vorschau des eingegebenen
 * Datums ab (F24); was gesendet wird, entscheidet der Aufrufer.
 */
export default function ShorteningChoice({
  preview, losslessText, losslessNote, retroText, option, onOptionChange, closedText, reason, onReasonChange,
  idPrefix,
}: ShorteningChoiceProps) {
  const retroSelected = option === 'retro' || losslessText === null;
  return (
    <section
      aria-labelledby={`${idPrefix}-title`}
      className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm min-w-0 break-words"
    >
      <p id={`${idPrefix}-title`} className="flex items-center gap-1 font-semibold text-red-900">
        <AlertTriangle size={16} className="shrink-0" aria-hidden="true" />
        Verkürzung
      </p>
      <ul className="mt-1 list-disc pl-5 text-red-900">
        {shorteningHeadlines(preview).map((line) => <li key={line}>{line}</li>)}
      </ul>
      <fieldset className="mt-2 space-y-1 min-w-0">
        <legend className="sr-only">Wirksamkeit</legend>
        {losslessText !== null ? (
          <label className="flex items-start gap-2 text-gray-900 cursor-pointer">
            <input
              type="radio"
              name={`${idPrefix}-option`}
              checked={!retroSelected}
              onChange={() => onOptionChange('lossless')}
              className="mt-0.5 w-4 h-4 shrink-0"
            />
            <span>{losslessText}</span>
          </label>
        ) : (
          preview.earliest_lossless_note && <p className="text-gray-800">{preview.earliest_lossless_note}</p>
        )}
        {!retroSelected && losslessNote && <p className="pl-6 text-gray-700">{losslessNote}</p>}
        <label className={`flex items-start gap-2 ${closedText ? 'text-gray-400' : 'text-gray-900 cursor-pointer'}`}>
          <input
            type="radio"
            name={`${idPrefix}-option`}
            checked={retroSelected && !closedText}
            disabled={!!closedText}
            onChange={() => onOptionChange('retro')}
            className="mt-0.5 w-4 h-4 shrink-0"
          />
          <span>{retroText}</span>
        </label>
        {closedText && <p className="pl-6 font-medium text-red-700">{closedText}</p>}
      </fieldset>
      {retroSelected && !closedText && (
        <RetroReasonFields
          value={reason}
          onChange={onReasonChange}
          idPrefix={idPrefix}
          milogWarnings={preview.milog_warning ?? []}
        />
      )}
    </section>
  );
}
