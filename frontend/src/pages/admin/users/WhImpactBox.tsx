import { useState } from 'react';
import { formatDayCount } from '../../../utils/formatters';
import { WEEKDAY_LABELS } from '../../../utils/workBlocks';
import type { TimeEntryChange, WorkingHoursChangePreview } from './workingHoursTypes';
import { SKIP_LABELS, formatDate, hm, monthLabel, signedDays, signedHm } from './workingHoursTexts';

function round2(value: number): number {
  return Number.isFinite(value) ? Math.round(value * 100) / 100 : 0;
}

const clock = (t: string | null) => (t ? t.slice(0, 5) : '–');

function notExtendableText(c: TimeEntryChange): string {
  if (c.not_extendable === 'start') return `${formatDate(c.date)}, Beginn ${clock(c.old_start)}`;
  if (c.not_extendable === 'both') return `${formatDate(c.date)}, Beginn ${clock(c.old_start)}, Ende ${clock(c.old_end)}`;
  return `${formatDate(c.date)}, Ende ${clock(c.old_end)}`;
}

function skippedSummary(reasons: string[]): string {
  const counts = new Map<string, number>();
  reasons.forEach((r) => counts.set(r, (counts.get(r) ?? 0) + 1));
  return [...counts].map(([r, n]) => `${n} ${SKIP_LABELS[r] ?? r}`).join(', ');
}

/**
 * Spec 9.6 (Zeile aus P27, F1-Klemmung): „n Abwesenheiten an Misch-Tagen
 * angeglichen (Arbeit und Gutschrift am selben Tag)". Der Zusatz gehört dazu —
 * „Misch-Tag" ist sonst nirgends in Oberfläche oder Handbuch erklärt.
 */
const F1_HINT = '(Arbeit und Gutschrift am selben Tag)';
function f1Text(n: number): string {
  return n === 1
    ? `1 Abwesenheit an einem Misch-Tag angeglichen ${F1_HINT}`
    : `${n} Abwesenheiten an Misch-Tagen angeglichen ${F1_HINT}`;
}

/**
 * Spec 2026-10-08, 12.1/9.4: Inhalt der Auswirkungs-Box — gemeinsam für die
 * Vorschau einer Änderung und die `delete-preview`. Ältere Antworten ohne die
 * Felder aus 11.3 zeigen nur Abwesenheiten und Tabelle.
 *
 * Zahlen wie im Rest der App: Stunden H:MM (`formatHoursHM` über `hm`/`signedHm`)
 * — auch das Tagessoll, damit es zum Block-Editor darüber passt (7:55 h, nicht
 * 7,92); Urlaub über `formatDayCount`; Datumsangaben TT.MM.JJJJ (ein
 * Wirkungsbereich kann über den Jahreswechsel reichen).
 */
export default function WhImpactBox({ preview }: { preview: WorkingHoursChangePreview }) {
  const [details, setDetails] = useState(false);
  const changedDays = (preview.changed_weekdays ?? []).map((i) => WEEKDAY_LABELS[i]).join(', ');
  const entries = preview.affected_time_entries ?? 0;
  const months = preview.time_entry_months ?? [];
  const skipped = preview.skipped_time_entries ?? [];
  const notExtendable = preview.not_extendable_entries ?? [];
  const changes = preview.time_entry_changes ?? [];
  const reductions = preview.absence_credit_reductions ?? [];
  const stale = preview.stale_entries_closed ?? 0;
  const f1 = preview.absence_f1_adjustments ?? 0;
  const overtimeDelta = round2(preview.overtime_after - preview.overtime_before);
  const vacationDelta = round2(preview.vacation_days_after - preview.vacation_days_before);
  const vacationYear = preview.period_start.slice(0, 4);
  const arbzg = preview.arbzg_findings;

  // #431: nur Tage, an denen VOR oder NACH der Änderung ein Soll steht — ein
  // durchgehend freier Freitag sagt nichts.
  const dayTargets = (() => {
    const before = preview.day_targets_current;
    const after = preview.day_targets_new;
    if (!Array.isArray(before) || !Array.isArray(after)) return '';
    const parts = WEEKDAY_LABELS.map((label, i) => {
      const cur = before[i] ?? 0;
      const next = after[i] ?? 0;
      return cur <= 0 && next <= 0 ? null : `${label} ${hm(cur)} h → ${hm(next)} h`;
    }).filter((p): p is string => p !== null);
    return parts.length ? `Tagessoll je Wochentag: ${parts.join(' · ')}` : '';
  })();

  const hasDetails = changes.length > 0 || skipped.length > 0 || reductions.length > 0;

  return (
    <div className="mt-1 space-y-1 break-words text-amber-900">
      {preview.grace_minutes !== undefined && (
        <p>{`Auswirkung (Puffer ${preview.grace_minutes} Min)${changedDays ? ` · geänderte Tage: ${changedDays}` : ''}`}</p>
      )}
      {dayTargets && <p className="text-amber-800">{dayTargets}</p>}
      {(entries > 0 || skipped.length > 0) && (
        <p>
          {`Zeiteinträge: ${entries} neu berechnet`
            + (skipped.length ? ` · ${skipped.length} übersprungen (${skippedSummary(skipped.map((s) => s.reason))})` : '')}
        </p>
      )}
      {months.length > 0 && (
        <ul className="pl-4 text-amber-800">
          {months.map((m) => (
            <li key={m.month}>
              {`${monthLabel(m.month)} · ${m.entries} ${m.entries === 1 ? 'Eintrag' : 'Einträge'} · ${hm(m.net_before)} h → ${hm(m.net_after)} h`}
            </li>
          ))}
        </ul>
      )}
      {notExtendable.length > 0 && (
        <p>
          {`${notExtendable.length} ${notExtendable.length === 1 ? 'Eintrag' : 'Einträge'} ohne Rohstempel – nicht erweiterbar (${notExtendable.map(notExtendableText).join('; ')})`}
        </p>
      )}
      {stale > 0 && (
        <p>
          {stale === 1
            ? '1 offener Eintrag eines vergangenen Tages wird vorher automatisch geschlossen.'
            : `${stale} offene Einträge vergangener Tage werden vorher automatisch geschlossen.`}
        </p>
      )}
      <p className="text-amber-800">{`${preview.affected_absences} Abwesenheit(en) betroffen.`}</p>
      {f1 > 0 && <p className="text-amber-800">{f1Text(f1)}</p>}
      {/* Handy: Querscroll statt abgeschnittener Spalten. */}
      <div className="mt-2 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-xs uppercase text-amber-700">
              <th scope="col" className="text-left font-medium">Auswirkung</th>
              <th scope="col" className="text-right font-medium">bisher</th>
              <th scope="col" className="text-right font-medium">neu</th>
              <th scope="col" className="text-right font-medium">
                <span aria-hidden="true">Δ</span>
                <span className="sr-only">Änderung</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {preview.target_delta_hours !== undefined && (
              <tr>
                <th scope="row" className="pr-2 text-left font-medium">Soll im Zeitraum</th>
                <td /><td />
                <td className="whitespace-nowrap pl-2 text-right font-medium">{`${signedHm(preview.target_delta_hours)} h`}</td>
              </tr>
            )}
            {preview.credited_delta_hours !== undefined && (
              <tr>
                <th scope="row" className="pr-2 text-left font-medium">Angerechnet</th>
                <td /><td />
                <td className="whitespace-nowrap pl-2 text-right font-medium">{`${signedHm(preview.credited_delta_hours)} h`}</td>
              </tr>
            )}
            <tr>
              <th scope="row" className="pr-2 text-left font-medium">Überstunden</th>
              <td className="whitespace-nowrap pl-2 text-right">{`${signedHm(preview.overtime_before)} h`}</td>
              <td className="whitespace-nowrap pl-2 text-right">{`${signedHm(preview.overtime_after)} h`}</td>
              <td className="whitespace-nowrap pl-2 text-right font-medium">{`${signedHm(overtimeDelta)} h`}</td>
            </tr>
            <tr>
              {/* Die Urlaubszahlen gehören zum Jahr des Wirkungszeitraums. */}
              <th scope="row" className="pr-2 text-left font-medium">{`Urlaub ${vacationYear}`}</th>
              <td className="whitespace-nowrap pl-2 text-right">{formatDayCount(preview.vacation_days_before)}</td>
              <td className="whitespace-nowrap pl-2 text-right">{formatDayCount(preview.vacation_days_after)}</td>
              <td className="whitespace-nowrap pl-2 text-right font-medium">{signedDays(vacationDelta)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {arbzg && arbzg.days_over_10_credited_before !== arbzg.days_over_10_credited_after && (
        <p>{`Tage > 10 h: angerechnet bisher ${arbzg.days_over_10_credited_before}, neu ${arbzg.days_over_10_credited_after} · laut Stempel ${arbzg.days_over_10_presence}`}</p>
      )}
      {arbzg && arbzg.weeks_over_48_credited_before !== arbzg.weeks_over_48_credited_after && (
        <p>{`Wochen > 48 h: angerechnet bisher ${arbzg.weeks_over_48_credited_before}, neu ${arbzg.weeks_over_48_credited_after} · laut Stempel ${arbzg.weeks_over_48_presence}`}</p>
      )}
      {hasDetails && (
        <>
          <button
            type="button"
            aria-expanded={details}
            onClick={() => setDetails((d) => !d)}
            className="text-sm font-medium text-amber-900 underline hover:no-underline"
          >
            Einzelheiten<span aria-hidden="true">{details ? ' ▴' : ' ▾'}</span>
          </button>
          {details && (
            <ul className="pl-4 text-xs text-amber-900 space-y-0.5">
              {changes.map((c) => (
                <li key={c.entry_id}>
                  {`${formatDate(c.date)} ${clock(c.old_start)}–${clock(c.old_end)} → ${clock(c.new_start)}–${clock(c.new_end)} (${hm(c.old_net)} h → ${hm(c.new_net)} h)`}
                </li>
              ))}
              {skipped.map((s) => (
                <li key={s.entry_id}>{`${formatDate(s.date)} übersprungen: ${SKIP_LABELS[s.reason] ?? s.reason}`}</li>
              ))}
              {reductions.map((r) => (
                <li key={r.absence_id}>{`Gutschrift ${formatDate(r.date)}: ${hm(r.old_hours)} h → ${hm(r.new_hours)} h`}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
