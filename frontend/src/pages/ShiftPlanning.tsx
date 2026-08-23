import { useEffect, useState } from 'react';
import { CalendarDays, Printer } from 'lucide-react';
import Button from '../components/Button';
import EmptyState from '../components/EmptyState';
import LoadingSpinner from '../components/LoadingSpinner';
import WeekGrid from '../components/shiftplanning/WeekGrid';
import { useToast } from '../contexts/ToastContext';
import { getErrorMessage } from '../utils/errorMessage';
import { useSystemStore } from '../stores/systemStore';
import * as api from '../api/shiftPlanning';
import type { PlanDetail, PlanSummary } from '../api/shiftPlanning';

/** Vermerk neben dem Plannamen in der Auswahl: gilt er heute, oder ab wann? */
function planHint(p: PlanSummary): string {
  if (p.active_today) return 'Aktuell';
  if (p.active_from_date) {
    const d = new Date(`${p.active_from_date}T00:00:00`);
    return `Ab ${d.toLocaleDateString('de-DE')}`;
  }
  return 'Vorschau';
}

export default function ShiftPlanning() {
  const toast = useToast();
  const weekdays = useSystemStore((s) => s.getShiftPlanningWeekdays());
  const [loading, setLoading] = useState(true);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PlanDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // #443: NICHT mehr clientseitig auf active_today filtern. Der Server
        // liefert Mitarbeitenden ohnehin nur Sichtbares (heute gültig ODER
        // ausdrücklich freigegeben) — ein Filter hier würde genau die
        // freigegebenen Zukunftspläne wieder wegwerfen, um die es geht.
        const summaries = await api.listPlans();
        if (cancelled) return;
        setPlans(summaries);
        const preferred = summaries.find((p) => p.active_today) ?? summaries[0];
        setSelectedId(preferred ? preferred.id : null);
      } catch (err) {
        if (!cancelled) toast.error(getErrorMessage(err, 'Fehler beim Laden der Schichtpläne'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Einmalig beim Mounten. `toast` ist eine stabile Referenz und wird nur im
    // catch-Zweig genutzt (vgl. Dashboard.tsx).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    api
      .getPlan(selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((err) => {
        if (!cancelled) toast.error(getErrorMessage(err, 'Fehler beim Laden des Schichtplans'));
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const downloadPdf = async () => {
    if (!detail || downloading) return;
    setDownloading(true);
    try {
      await api.downloadPlanPdf(detail.id, detail.name);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Erstellen des PDF'));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Schichtplan</h1>

      {loading ? (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : plans.length === 0 ? (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
          <EmptyState
            icon={CalendarDays}
            title="Kein Schichtplan verfügbar"
            description="Sobald ein Administrator einen Plan aktiv schaltet oder für Mitarbeitende freigibt, erscheint er hier."
          />
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            {plans.length > 1 ? (
              <select
                aria-label="Schichtplan wählen"
                value={selectedId ?? ''}
                onChange={(e) => setSelectedId(e.target.value)}
                className="rounded-lg border-gray-300 text-sm py-1"
              >
                {plans.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} — {planHint(p)}
                  </option>
                ))}
              </select>
            ) : (
              <h2 className="text-xl font-semibold text-gray-900">{plans[0].name}</h2>
            )}
            {detail && (
              <Button variant="secondary" icon={Printer} loading={downloading} onClick={downloadPdf}>
                PDF
              </Button>
            )}
          </div>

          {detailLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : detail ? (
            <>
              {detail.description && <p className="text-sm text-gray-500 mb-3">{detail.description}</p>}
              {!detail.active_today && (
                <p className="mb-3 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
                  Dieser Plan gilt noch nicht — er ist zur Ansicht freigegeben.
                </p>
              )}
              <WeekGrid slots={detail.slots} weekdays={weekdays} />
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
