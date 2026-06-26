import { useEffect, useState } from 'react';
import { GraduationCap } from 'lucide-react';
import { useSystemStore } from '../stores/systemStore';
import * as api from '../api/shiftPlanning';
import type { Workstation } from '../api/shiftPlanning';

/**
 * "Meine Einweisungen" (#305 M2d) — the employee's own workstation
 * qualifications. Hidden when the shift-planning feature is off.
 */
export default function MyQualificationsCard() {
  const enabled = useSystemStore((s) => s.isShiftPlanningEnabled());
  const [workstations, setWorkstations] = useState<Workstation[] | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    api
      .getMyQualifications()
      .then((d) => {
        if (!cancelled) setWorkstations(d.workstations);
      })
      .catch(() => {
        if (!cancelled) setWorkstations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  if (!enabled || workstations === null) return null;

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <div className="flex items-center gap-2 mb-3">
        <GraduationCap size={18} className="text-primary" />
        <h2 className="text-lg font-semibold text-gray-900">Meine Einweisungen</h2>
      </div>
      {workstations.length === 0 ? (
        <p className="text-sm text-gray-500">
          Für Sie sind noch keine Arbeitsplatz-Einweisungen hinterlegt. Diese pflegt Ihr Administrator.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {workstations.map((ws) => (
            <span
              key={ws.id}
              className="inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-sm text-text-primary"
            >
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: ws.color || '#9ca3af' }} />
              {ws.name}
              {ws.location_name && <span className="text-xs text-gray-400">· {ws.location_name}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
