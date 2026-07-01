import { useEffect, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import EmptyState from '../components/EmptyState';
import LoadingSpinner from '../components/LoadingSpinner';
import WeekGrid from '../components/shiftplanning/WeekGrid';
import { useToast } from '../contexts/ToastContext';
import { getErrorMessage } from '../utils/errorMessage';
import { useSystemStore } from '../stores/systemStore';
import * as api from '../api/shiftPlanning';
import type { PlanDetail } from '../api/shiftPlanning';

export default function ShiftPlanning() {
  const toast = useToast();
  const weekdays = useSystemStore((s) => s.getShiftPlanningWeekdays());
  const [loading, setLoading] = useState(true);
  const [activePlans, setActivePlans] = useState<PlanDetail[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const summaries = await api.listPlans();
        // #305 M2: "aktiv heute" = manuell aktiv ODER Datums-Fenster deckt heute ab.
        const active = summaries.filter((p) => p.active_today);
        const details = await Promise.all(active.map((p) => api.getPlan(p.id)));
        if (!cancelled) setActivePlans(details);
      } catch (err) {
        if (!cancelled) toast.error(getErrorMessage(err, 'Fehler beim Laden der Schichtpläne'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Load once on mount. `toast` is a stable ref (memoised ToastContext value)
    // and only used in the catch branch — keeping it out of the deps avoids a
    // re-fetch every time an unrelated toast fires (cf. Dashboard.tsx).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Schichtplan</h1>

      {loading ? (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : activePlans.length === 0 ? (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
          <EmptyState
            icon={CalendarDays}
            title="Kein aktiver Schichtplan"
            description="Sobald ein Administrator einen Plan aktiv schaltet, erscheint er hier."
          />
        </div>
      ) : (
        <div className="space-y-6">
          {activePlans.map((plan) => (
            <div key={plan.id} className="bg-white rounded-xl shadow-xs border border-gray-200 p-4">
              <h2 className="text-xl font-semibold text-gray-900 mb-1">{plan.name}</h2>
              {plan.description && <p className="text-sm text-gray-500 mb-3">{plan.description}</p>}
              <WeekGrid slots={plan.slots} weekdays={weekdays} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
