import { useEffect, useMemo, useState } from 'react';
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

/**
 * Lokales Datum (YYYY-MM-DD) — bewusst NICHT über `toISOString()`: das würde
 * lokale Mitternacht nach UTC konvertieren und in einer UTC+-Zone (z. B.
 * Europe/Berlin) auf den Vortag zurückrollen (vgl. weekGridUtils.mondayOfWeek).
 */
function todayIsoLocal(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

type PlanTimeStatus = 'active' | 'upcoming' | 'expired';

/**
 * #443 F-4 (Prüfrunde 2, Minor): "gilt noch nicht" (upcoming) und "gilt nicht
 * mehr" (expired — `active_until_date` liegt in der Vergangenheit) sind zwei
 * verschiedene Aussagen. Vorher behauptete sowohl `planHint` als auch der
 * blaue Kasten für BEIDE Fälle "noch nicht"/"Ab <Datum>" — für einen
 * abgelaufenen, freigegebenen Sommerplan liest sich das wie Zukunft, obwohl
 * es Vergangenheit ist. Das Backend unterscheidet die beiden Fälle im PDF
 * bereits (`shift_plan_export_service._status_note`); dieser Helfer hält den
 * Bildschirm dazu inhaltlich stimmig (keine wortgleiche Pflicht, aber
 * dieselbe Unterscheidung).
 */
function planTimeStatus(p: Pick<PlanSummary, 'active_today' | 'active_until_date'>): PlanTimeStatus {
  if (p.active_today) return 'active';
  if (p.active_until_date && p.active_until_date < todayIsoLocal()) return 'expired';
  return 'upcoming';
}

/** Vermerk neben dem Plannamen in der Vorschau-Auswahl: gilt er noch, ab wann, oder war er's? */
function planHint(p: PlanSummary): string {
  const status = planTimeStatus(p);
  if (status === 'active') return 'Aktuell';
  if (status === 'expired') return 'Nicht mehr gültig';
  if (p.active_from_date) {
    const d = new Date(`${p.active_from_date}T00:00:00`);
    return `Ab ${d.toLocaleDateString('de-DE')}`;
  }
  return 'Vorschau';
}

function StatusBox({ status }: { status: PlanTimeStatus }) {
  if (status === 'active') return null;
  return (
    <p className="mb-3 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
      {status === 'expired'
        ? 'Dieser Plan gilt nicht mehr — er ist zur Ansicht freigegeben.'
        : 'Dieser Plan gilt noch nicht — er ist zur Ansicht freigegeben.'}
    </p>
  );
}

/** Eine Plan-Karte: Überschrift, optionaler PDF-Download, Statushinweis + Wochenraster. */
function PlanBlock({
  heading,
  loading,
  detail,
  weekdays,
  downloading,
  onDownload,
}: {
  heading: string;
  loading: boolean;
  detail: PlanDetail | null;
  weekdays: number[];
  downloading: boolean;
  onDownload: () => void;
}) {
  return (
    <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 className="text-xl font-semibold text-gray-900">{heading}</h2>
        {detail && (
          <Button variant="secondary" icon={Printer} loading={downloading} onClick={onDownload}>
            PDF
          </Button>
        )}
      </div>
      {loading ? (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : detail ? (
        <>
          {detail.description && <p className="text-sm text-gray-500 mb-3">{detail.description}</p>}
          <StatusBox status={planTimeStatus(detail)} />
          <WeekGrid slots={detail.slots} weekdays={weekdays} />
        </>
      ) : null}
    </div>
  );
}

export default function ShiftPlanning() {
  const toast = useToast();
  const weekdays = useSystemStore((s) => s.getShiftPlanningWeekdays());
  const [loading, setLoading] = useState(true);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [activeDetails, setActiveDetails] = useState<Record<string, PlanDetail>>({});
  const [activeDetailsLoading, setActiveDetailsLoading] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewDetail, setPreviewDetail] = useState<PlanDetail | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const activePlans = useMemo(() => plans.filter((p) => p.active_today), [plans]);
  // #461 W-1: `visible_to_employees` MUSS hier mitgeprüft werden. Für
  // Mitarbeitende ist die Bedingung ein No-op — der Server liefert ihnen über
  // `is_plan_visible_to` ohnehin nur Freigegebenes. Für **Admins** filtert der
  // Server bewusst gar nicht: ohne diesen Filter landen deren private Entwürfe
  // unter der Überschrift „Vorschau — freigegeben", also unter einer Aussage,
  // die für sie nicht stimmt. Ausgerechnet hier sieht man nach, ob eine
  // Freigabe angekommen ist.
  const previewPlans = useMemo(
    () => plans.filter((p) => !p.active_today && p.visible_to_employees),
    [plans],
  );
  // #443 F-2: gilt heute gar kein Plan UND ist genau ein sichtbarer
  // (Vorschau-)Plan da, ist er das einzig Anzuzeigende — dann direkt wie einen
  // gewöhnlichen Einzelplan zeigen statt eine Auswahl mit nur einer Option zu
  // erzwingen.
  const solePreview = activePlans.length === 0 && previewPlans.length === 1 ? previewPlans[0] : null;
  const selectablePreviews = solePreview ? [] : previewPlans;

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

  // #443 F-2 (Prüfrunde 2, Important): ALLE heute geltenden Pläne laden — vorher
  // wurde nur ein vorbelegter Plan gezeigt (`summaries.find(active_today) ??
  // summaries[0]`, faktisch der alphabetisch erste), obwohl mehrere gleichzeitig
  // gültige Pläne eine ausdrücklich unterstützte Konfiguration sind (z. B. ein
  // Plan je Standort — Modell-Docstring, `get_my_today` bildet serverseitig
  // ebenfalls die Vereinigung über alle aktiven Pläne). Ohne diesen Fix hält
  // sich eine Mitarbeiterin mit Einträgen in zwei Plänen fälschlich für nicht
  // eingeteilt, sobald der jeweils andere Plan alphabetisch vorn liegt.
  //
  // Prüfrunde 2 (N-2): `Promise.all` liess EINEN fehlgeschlagenen Abruf (z. B.
  // ein Plan wurde zwischen Listen- und Detail-Aufruf gelöscht) die gesamte
  // Zuweisung zu `activeDetails` scheitern — dann blieben ALLE geltenden
  // Pläne als nackte Überschrift ohne Inhalt stehen, nicht nur der betroffene.
  // `Promise.allSettled` lässt jeden Plan für sich fehlschlagen; die
  // erfolgreichen bleiben vollständig sichtbar, der gescheiterte Plan wird aus
  // der Liste entfernt (kein leerer Karten-Stumpf) und einmalig per Toast
  // gemeldet — stillschweigendes Weglassen allein hätte einen echten Fehler
  // (nicht nur "heute nichts eingeteilt") unbemerkt gelassen.
  useEffect(() => {
    const ids = plans.filter((p) => p.active_today).map((p) => p.id);
    if (ids.length === 0) {
      setActiveDetails({});
      return;
    }
    let cancelled = false;
    setActiveDetailsLoading(true);
    Promise.allSettled(ids.map((id) => api.getPlan(id).then((d) => [id, d] as const))).then(
      (results) => {
        if (cancelled) return;
        const entries = results
          .filter(
            (r): r is PromiseFulfilledResult<readonly [string, PlanDetail]> => r.status === 'fulfilled',
          )
          .map((r) => r.value);
        setActiveDetails(Object.fromEntries(entries));
        const failedCount = results.length - entries.length;
        if (failedCount > 0) {
          toast.error(
            failedCount === 1
              ? 'Ein Schichtplan konnte nicht geladen werden und wird nicht angezeigt.'
              : `${failedCount} Schichtpläne konnten nicht geladen werden und werden nicht angezeigt.`,
          );
        }
        setActiveDetailsLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plans]);

  // Genau ein sichtbarer Plan insgesamt, und der ist keiner der heute
  // geltenden → automatisch als die einzige Ansicht laden.
  useEffect(() => {
    if (solePreview) setPreviewId(solePreview.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [solePreview?.id]);

  // #443 F-2: zusätzlich freigegebene, noch nicht geltende Pläne laden ihr
  // Detail erst "bei Bedarf" (Auswahl) — anders als die heute geltenden
  // Pläne, von denen es im Regelfall nur ein bis zwei gibt, könnten hier
  // beliebig viele freigegebene Zukunftspläne aufgelaufen sein.
  useEffect(() => {
    if (!previewId) {
      setPreviewDetail(null);
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    api
      .getPlan(previewId)
      .then((d) => {
        if (!cancelled) setPreviewDetail(d);
      })
      .catch((err) => {
        if (!cancelled) toast.error(getErrorMessage(err, 'Fehler beim Laden des Schichtplans'));
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewId]);

  const downloadPdf = async (plan: { id: string; name: string }) => {
    if (downloadingId) return;
    setDownloadingId(plan.id);
    try {
      await api.downloadPlanPdf(plan.id, plan.name);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Erstellen des PDF'));
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Schichtplan</h1>

      {loading ? (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : activePlans.length === 0 && previewPlans.length === 0 ? (
        /* #461 W-1: nicht `plans.length` — für Admins enthält die Liste auch
           nicht freigegebene Entwürfe, die diese Seite bewusst nicht zeigt.
           Ohne die engere Bedingung bliebe die Seite bei einem reinen
           Entwurfsbestand vollständig leer statt den leeren Zustand zu zeigen. */
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
          <EmptyState
            icon={CalendarDays}
            title="Kein Schichtplan verfügbar"
            description="Sobald ein Administrator einen Plan aktiv schaltet oder für Mitarbeitende freigibt, erscheint er hier."
          />
        </div>
      ) : (
        <div className="space-y-6">
          {/* #443 F-2: alle heute geltenden Pläne untereinander — nicht nur einer.
              N-2: solange noch geladen wird oder ein Detail erfolgreich da ist, Karte
              zeigen; ein einzeln gescheiterter Abruf entfernt NUR seine eigene Karte,
              statt (wie zuvor bei `Promise.all`) alle als nackte Überschrift zu zeigen. */}
          {activePlans
            .filter((p) => activeDetailsLoading || activeDetails[p.id])
            .map((p) => (
              <PlanBlock
                key={p.id}
                heading={p.name}
                loading={activeDetailsLoading && !activeDetails[p.id]}
                detail={activeDetails[p.id] ?? null}
                weekdays={weekdays}
                downloading={downloadingId === p.id}
                onDownload={() => downloadPdf(p)}
              />
            ))}

          {solePreview ? (
            <PlanBlock
              heading={solePreview.name}
              loading={previewLoading && !previewDetail}
              detail={previewDetail}
              weekdays={weekdays}
              downloading={downloadingId === solePreview.id}
              onDownload={() => downloadPdf(solePreview)}
            />
          ) : (
            selectablePreviews.length > 0 && (
              <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2 text-sm text-gray-700">
                    <span className="font-medium">Vorschau — freigegeben, gilt aber (noch) nicht heute:</span>
                    <select
                      aria-label="Vorschau-Schichtplan wählen"
                      value={previewId ?? ''}
                      onChange={(e) => setPreviewId(e.target.value || null)}
                      className="rounded-lg border-gray-300 text-sm py-1"
                    >
                      <option value="">Bitte wählen</option>
                      {selectablePreviews.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} — {planHint(p)}
                        </option>
                      ))}
                    </select>
                  </div>
                  {previewDetail && (
                    <Button
                      variant="secondary"
                      icon={Printer}
                      loading={downloadingId === previewDetail.id}
                      onClick={() => downloadPdf(previewDetail)}
                    >
                      PDF
                    </Button>
                  )}
                </div>
                {previewLoading ? (
                  <div className="flex justify-center py-12">
                    <LoadingSpinner />
                  </div>
                ) : previewDetail ? (
                  <>
                    {previewDetail.description && (
                      <p className="text-sm text-gray-500 mb-3">{previewDetail.description}</p>
                    )}
                    <StatusBox status={planTimeStatus(previewDetail)} />
                    <WeekGrid slots={previewDetail.slots} weekdays={weekdays} />
                  </>
                ) : null}
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
