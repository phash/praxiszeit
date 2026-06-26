import { useState } from 'react';
import { ChevronDown, ChevronUp, CalendarRange } from 'lucide-react';
import type { PlanSummary } from '../../api/shiftPlanning';
import { colorForWorkstation } from './weekGridUtils';

const MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

/**
 * Ganzjahres-Übersicht (#305 M2): zeigt für das laufende Jahr, in welchem
 * Zeitraum welcher Plan automatisch aktiv ist (Datums-Fenster), als
 * proportionaler Jahres-Balken je Plan. Manuell aktive Pläne (ohne Fenster)
 * werden als durchgehend aktiv dargestellt.
 */
export default function YearTimeline({ plans }: { plans: PlanSummary[] }) {
  const [open, setOpen] = useState(false);

  const relevant = plans.filter((p) => p.is_active || p.active_from_date || p.active_until_date);

  const year = new Date().getFullYear();
  const yearStart = new Date(year, 0, 1).getTime();
  const yearMs = new Date(year + 1, 0, 1).getTime() - yearStart;
  const frac = (iso: string) => Math.max(0, Math.min(1, (new Date(iso + 'T00:00:00').getTime() - yearStart) / yearMs));
  const todayFrac = Math.max(0, Math.min(1, (Date.now() - yearStart) / yearMs));

  return (
    <div className="bg-white rounded-xl shadow-xs border border-gray-200 mb-4">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-700">
          <CalendarRange size={16} className="text-primary" /> Jahresübersicht {year}
        </span>
        {open ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
      </button>

      {open && (
        <div className="px-4 pb-4">
          {relevant.length === 0 ? (
            <p className="text-sm text-gray-500">
              Noch keine zeitgesteuerten Pläne. Setze im Plan unter „Bearbeiten" ein Aktiv-Datums-Fenster.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <div className="min-w-[640px]">
                {/* month axis */}
                <div className="relative h-5 ml-40 border-b border-gray-200">
                  {MONTHS.map((m, i) => (
                    <span
                      key={m}
                      className="absolute -translate-x-1/2 text-[10px] text-gray-400"
                      style={{ left: `${((i + 0.5) / 12) * 100}%` }}
                    >
                      {m}
                    </span>
                  ))}
                </div>
                {relevant.map((p, idx) => {
                  const hasWindow = !!(p.active_from_date || p.active_until_date);
                  const left = p.active_from_date ? frac(p.active_from_date) : 0;
                  const right = p.active_until_date ? frac(p.active_until_date) : 1;
                  const color = colorForWorkstation(null, idx);
                  return (
                    <div key={p.id} className="flex items-center py-1.5">
                      <div className="w-40 shrink-0 truncate text-sm text-gray-700 pr-2">{p.name}</div>
                      <div className="relative flex-1 h-5 rounded bg-gray-100">
                        {/* active segment */}
                        <div
                          className="absolute top-0 bottom-0 rounded"
                          style={{
                            left: `${left * 100}%`,
                            width: `${Math.max(0, right - left) * 100}%`,
                            backgroundColor: hasWindow ? `${color}99` : `${color}40`,
                          }}
                          title={
                            hasWindow
                              ? `aktiv ${p.active_from_date || '…'} – ${p.active_until_date || '…'}`
                              : 'manuell aktiv (ganzjährig)'
                          }
                        />
                        {/* today marker */}
                        <div
                          className="absolute top-0 bottom-0 w-px bg-red-500"
                          style={{ left: `${todayFrac * 100}%` }}
                          title="heute"
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
