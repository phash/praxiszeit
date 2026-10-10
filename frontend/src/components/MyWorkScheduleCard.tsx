import { useEffect, useState } from 'react';
import { Clock } from 'lucide-react';
import apiClient from '../api/client';
import { formatHoursHM } from '../utils/formatters';
import { WEEKDAY_LABELS, formatWeekBlocks, isLegacyWeek } from '../utils/workBlocks';
import type { WeekBlocks } from '../types/workBlocks';

/**
 * Spec 2026-10-08, Abschnitt 14 / E67: „Meine Arbeitszeit" — die heute gültigen
 * Arbeitszeit-Blöcke je Wochentag mit Tagessoll und der Verlauf mit
 * Wirkungsdaten. Datumsaufgelöst vom Server (`GET /auth/me/work-schedule`);
 * der Verwaltungsfreitext steht bewusst nicht hier (P12, Art.-15-Export).
 *
 * Modus (Review Task 10): Im #377-Fix-Modus sind die Tageswerte nur geplante
 * Anwesenheit — „geplant" statt „Tagessoll", das Soll ist die feste
 * Monatsarbeitszeit (wie die Spalte „Geplant" im Monatsjournal, #463). Ohne
 * Stundenzählung (#191) gibt es weder Tagessoll noch Kappung (E35/E63).
 */
interface Snapshot {
  blocks: WeekBlocks | null;
  day_targets: number[];
  weekly_hours: number;
}

interface WorkSchedule {
  today: Snapshot & { date: string };
  history: (Snapshot & { effective_from: string; effective_until: string | null })[];
  track_hours: boolean;
  fixed_monthly_hours: number | null;
}

function deDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

export default function MyWorkScheduleCard() {
  const [data, setData] = useState<WorkSchedule | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get('/auth/me/work-schedule')
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch(() => { /* Karte entfällt — nicht kritisch */ });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) return null;
  const today = data.today;
  const untracked = data.track_hours === false;
  const fixedMonthlyHours = untracked ? null : (data.fixed_monthly_hours ?? null);
  const dayLabel = fixedMonthlyHours != null ? 'geplant' : 'Tagessoll';

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <div className="flex items-center gap-2 mb-3">
        <Clock size={18} className="text-primary" />
        <h2 className="text-lg font-semibold text-gray-900">Meine Arbeitszeit</h2>
      </div>
      <ul className="text-sm text-gray-700 space-y-1" aria-label="Arbeitszeit heute">
        {WEEKDAY_LABELS.map((label, i) => {
          const day = today.blocks?.[i];
          const spans = day && day.blocks.length > 0
            ? day.blocks.map((b) => `${b.start}–${b.end}`).join(' + ')
            : '–';
          const pause = day?.pause_minutes ? ` (Pause ${day.pause_minutes} Min)` : '';
          const target = untracked ? '' : ` · ${dayLabel} ${formatHoursHM(today.day_targets[i] ?? 0)} h`;
          return (
            <li key={label}>
              {`${label} ${spans}${pause}${target}`}
            </li>
          );
        })}
      </ul>
      {fixedMonthlyHours != null ? (
        <>
          <p className="text-sm text-gray-500 mt-2">{`Feste Monatsarbeitszeit: ${formatHoursHM(fixedMonthlyHours)} h`}</p>
          <p className="text-xs text-gray-500 mt-1">
            Die Tageswerte sind geplante Anwesenheit, kein Tagessoll; Ihr Soll ist die feste Monatsarbeitszeit.
          </p>
        </>
      ) : (
        <p className="text-sm text-gray-500 mt-2">{`Wochenstunden: ${formatHoursHM(today.weekly_hours)} h`}</p>
      )}
      {untracked ? (
        <p className="text-xs text-gray-500 mt-1">
          {/* E35/E63: ohne Stundenzählung weder Soll noch Kappung — auch nicht durch Blöcke. */}
          Ohne Stundenzählung: kein Tagessoll; die Arbeitszeit-Blöcke begrenzen die Anrechnung nicht.
        </p>
      ) : isLegacyWeek(today.blocks) && (
        <p className="text-xs text-gray-500 mt-1">
          {/* E10/E18: ein Altfenster kappt nur; das Tagessoll kommt — je nach Modus —
              aus den Wochenstunden oder den Tageswerten, nie aus diesen Zeiten. */}
          Diese Zeiten begrenzen nur die Anrechnung der erfassten Zeit; das Tagessoll wird nicht aus ihnen berechnet.
        </p>
      )}
      {data.history.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Verlauf</h3>
          <ul className="text-sm text-gray-600 space-y-1" aria-label="Verlauf der Arbeitszeit">
            {data.history.map((h) => (
              <li key={h.effective_from}>
                {`ab ${deDate(h.effective_from)}${h.effective_until ? ` bis ${deDate(h.effective_until)}` : ''}: `
                  + `${formatWeekBlocks(h.blocks) ?? 'keine Arbeitszeit-Blöcke'} · ${formatHoursHM(h.weekly_hours)} h/Woche`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
