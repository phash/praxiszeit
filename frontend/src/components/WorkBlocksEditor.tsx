import { Plus, X } from 'lucide-react';
import type { DayBlocks, TimeBlock, WeekBlocks } from '../types/workBlocks';
import {
  WEEKDAY_LABELS, blocksOf, deriveTargets, minutesToHm, sumBlocks, validateWeekBlocks,
} from '../utils/workBlocks';

interface WorkBlocksEditorProps {
  value: WeekBlocks;
  onChange: (week: WeekBlocks) => void;
  idPrefix?: string;
  /**
   * Gesamtreview 1.20 (Fund 14): feste Monatsarbeitszeit (#377 2b) — die
   * Tageswerte sind dann geplante Anwesenheit, kein Soll (wie die Profilkarte
   * „geplant" und die Option „Nach Tagen (geplante Anwesenheit)").
   */
  plannedPresence?: boolean;
}

const MAX_BLOCKS_PER_DAY = 3;

/**
 * Spec 2026-10-08, 12.1 / E59: je Wochentag bis zu drei Blöcke „von–bis" im
 * 5-Minuten-Raster und die „Pause innerhalb der Blöcke"; live je Tag
 * „Gesamtzeit · Pause · Tagessoll" und die Wochensumme. Gemeinsam für den
 * Dialog „Arbeitszeit & Wochenstunden" und das Anlegeformular.
 *
 * Angezeigt wird MINUTENGENAU (7:55 h) — gespeichert rundet der Server auf
 * 0,01 h (7,92 h, Spec 4.1). Validierungstexte wortgleich zum Backend (3.4).
 * Altwerte (07:37, Platzhalter 23:59, Pause NULL) zeigt der Editor unverändert
 * an und meldet sie, statt sie still zu korrigieren (Review Focus 4).
 *
 * Schmale Bildschirme: die Zeile eines Tages bricht um (flex-wrap), ein Block
 * bleibt als „von – bis ×" zusammen — nichts wird abgeschnitten.
 */
export default function WorkBlocksEditor({
  value, onChange, idPrefix = 'wb', plannedPresence = false,
}: WorkBlocksEditorProps) {
  const dayTargetLabel = plannedPresence ? 'geplant' : 'Tagessoll';
  const weekTargetLabel = plannedPresence ? 'geplant' : 'Wochensoll';
  // Immer fünf Tage zurückgeben, auch wenn ein unvollständiger Wert hereinkommt.
  const updateDay = (index: number, day: DayBlocks) =>
    onChange(WEEKDAY_LABELS.map((_, k) => (k === index ? day : value[k] ?? { blocks: [], pause_minutes: 0 })));
  const error = validateWeekBlocks(value);
  const totals = WEEKDAY_LABELS.reduce(
    (acc, _, i) => {
      const t = sumBlocks(value[i]);
      return { gross: acc.gross + t.grossMinutes, pause: acc.pause + t.pauseMinutes, net: acc.net + t.netMinutes };
    },
    { gross: 0, pause: 0, net: 0 },
  );
  // Arbeitstage wie der Server sie ableitet (derive_targets.work_days_per_week).
  const { workDays } = deriveTargets(value);

  return (
    <div className="space-y-2">
      {WEEKDAY_LABELS.map((label, i) => {
        const day = value[i] ?? { blocks: [], pause_minutes: 0 };
        const blocks = blocksOf(day);
        const t = sumBlocks(day);
        const setBlock = (n: number, patch: Partial<TimeBlock>) => updateDay(i, {
          ...day, blocks: blocks.map((b, k) => (k === n ? { ...b, ...patch } : b)),
        });
        return (
          <div key={label} className="rounded-lg border border-gray-200 bg-white p-2">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="w-7 font-medium text-gray-800">{label}</span>
              {blocks.length === 0 && <span className="text-sm text-gray-500">kein Arbeitstag</span>}
              {blocks.map((block, n) => (
                <span key={n} className="flex items-center gap-1">
                  <input
                    type="time"
                    step={300}
                    aria-label={`${label} Block ${n + 1} von`}
                    value={block.start}
                    onChange={(e) => setBlock(n, { start: e.target.value })}
                    className="px-1 py-0.5 border border-gray-300 rounded-sm text-sm focus:ring-2 focus:ring-primary"
                  />
                  <span aria-hidden="true">–</span>
                  <input
                    type="time"
                    step={300}
                    aria-label={`${label} Block ${n + 1} bis`}
                    value={block.end}
                    onChange={(e) => setBlock(n, { end: e.target.value })}
                    className="px-1 py-0.5 border border-gray-300 rounded-sm text-sm focus:ring-2 focus:ring-primary"
                  />
                  <button
                    type="button"
                    aria-label={`${label} Block ${n + 1} entfernen`}
                    title={`Block ${n + 1} entfernen`}
                    onClick={() => {
                      const rest = blocks.filter((_, k) => k !== n);
                      // Spec 3.4: ein Tag ohne Blöcke hat Pause 0.
                      updateDay(i, { blocks: rest, pause_minutes: rest.length ? day.pause_minutes : 0 });
                    }}
                    className="p-1 text-gray-500 hover:text-red-600"
                  >
                    <X size={14} />
                  </button>
                </span>
              ))}
              <button
                type="button"
                aria-label={`${label}: Block hinzufügen`}
                disabled={blocks.length >= MAX_BLOCKS_PER_DAY}
                onClick={() => updateDay(i, {
                  blocks: [...blocks, { start: '', end: '' }],
                  pause_minutes: blocks.length ? day.pause_minutes : 0,
                })}
                className="flex items-center gap-0.5 p-1 text-sm text-primary disabled:text-gray-300"
              >
                <Plus size={14} /> Block
              </button>
              {blocks.length > 0 && (
                <label className="ml-auto flex items-center gap-1 text-sm text-gray-700">
                  Pause innerhalb
                  <input
                    type="number"
                    min={0}
                    step={5}
                    inputMode="numeric"
                    aria-label={`${label} Pause innerhalb der Blöcke (Min)`}
                    value={day.pause_minutes ?? ''}
                    onChange={(e) => updateDay(i, {
                      ...day, pause_minutes: e.target.value === '' ? null : Number(e.target.value),
                    })}
                    className="w-16 px-1 py-0.5 border border-gray-300 rounded-sm text-sm text-right focus:ring-2 focus:ring-primary"
                  />
                  Min
                </label>
              )}
            </div>
            {blocks.length > 0 && (
              <p className="mt-1 text-xs text-gray-600" data-testid={`${idPrefix}-day-${i}`}>
                Gesamtzeit {minutesToHm(t.grossMinutes)} h · Pause {minutesToHm(t.pauseMinutes)} h · {dayTargetLabel}{' '}
                {minutesToHm(t.netMinutes)} h
              </p>
            )}
          </div>
        );
      })}
      <p className="text-sm text-gray-800" data-testid={`${idPrefix}-week`}>
        Woche: Gesamtzeit {minutesToHm(totals.gross)} h · Pause {minutesToHm(totals.pause)} h · {weekTargetLabel}{' '}
        {minutesToHm(totals.net)} h · {workDays} {workDays === 1 ? 'Arbeitstag' : 'Arbeitstage'}
      </p>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
