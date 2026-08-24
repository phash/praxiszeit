import { useEffect, useState } from 'react';
import { CalendarClock, MapPin } from 'lucide-react';
import { useSystemStore } from '../stores/systemStore';
import * as api from '../api/shiftPlanning';
import type { MyToday } from '../api/shiftPlanning';

/**
 * Dashboard widget "Deine Einteilung heute" (#305).
 *
 * Self-contained: renders nothing when the shift-planning feature flag is off
 * or the user has no assignment today. Fetches `my-today` (union of the user's
 * assignments across all active plans for today's weekday).
 */
export default function ShiftTodayCard() {
  const enabled = useSystemStore((s) => s.isShiftPlanningEnabled());
  const [data, setData] = useState<MyToday | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    api
      .getMyToday()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        /* feature may be off / no data — stay hidden */
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  if (!enabled || !data || data.entries.length === 0) return null;

  return (
    <div className="bg-surface rounded-2xl shadow-card border border-border p-6 mb-8">
      <div className="flex items-center gap-2 mb-4">
        <CalendarClock className="text-primary" size={20} />
        <h3 className="text-sm font-medium text-text-secondary">Deine Einteilung heute</h3>
      </div>
      <ul className="space-y-2">
        {data.entries.map((e, i) => (
          <li key={i} className="rounded-lg bg-muted/60 px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-text-primary">{e.workstation_name}</span>
                {e.location_name && (
                  <span className="flex items-center gap-1 text-xs text-text-secondary">
                    <MapPin size={12} /> {e.location_name}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-text-primary">
                  {e.start_time}–{e.end_time}
                </span>
                <span className="text-xs text-text-secondary">{e.plan_name}</span>
              </div>
            </div>
            {/* #453: Hinweis je Einteilung (#443) — » wie im Wochenraster/PDF-Aushang
                (WeekGrid.tsx / shift_plan_export_service), leer ist serverseitig
                null und zeigt keine Zeile. */}
            {e.note && (
              <div className="mt-1 text-sm italic text-text-secondary opacity-80 break-words">
                » {e.note}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
