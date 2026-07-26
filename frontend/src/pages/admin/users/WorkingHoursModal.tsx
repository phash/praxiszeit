import { useState, useEffect, useMemo } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../../api/client';
import { Plus, X, Trash2 } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { useConfirm } from '../../../hooks/useConfirm';
import ConfirmDialog from '../../../components/ConfirmDialog';
import { getErrorMessage } from '../../../utils/errorMessage';
import { parseHours } from '../../../utils/formatters';

interface WorkingHoursChange {
  id: string;
  user_id: string;
  effective_from: string;
  weekly_hours: number;
  note?: string;
  created_at: string;
}

// Task 7 (#Wochenstunden-anpassen): Antwortform von
// GET .../working-hours-changes/preview — strikt lesend, schreibt nichts.
interface WorkingHoursChangePreview {
  is_retroactive: boolean;
  period_start: string;
  period_end: string;
  current_daily_target: number;
  new_daily_target: number;
  affected_absences: number;
  blocked_reason: string | null;
  closed_years: number[];
  closed_year_warning: string | null;
}

interface WorkingHoursModalProps {
  userId: string;
  userName: string;
  currentWeeklyHours: number;
  onClose: () => void;
  onChanged: () => void;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

// Kalendertag VOR dem übergebenen ISO-Datum (YYYY-MM-DD) — UTC-basiert, um
// Zeitzonen-/DST-Rollover bei reiner Tagesarithmetik zu vermeiden.
function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().split('T')[0];
}

// „Heute" in der LOKALEN Zeitzone des Browsers (= die des Praxis-Rechners,
// faktisch Europe/Berlin) als YYYY-MM-DD.
//
// M1 (Abschluss-Review): NICHT `toISOString()` — das liefert UTC. Zwischen
// 00:00 und 02:00 Berliner Zeit hielt der Dialog damit das GESTRIGE Datum für
// „heute": keine Vorschau, keine Bestätigungspflicht — während das Backend
// (`today_local()`, Europe/Berlin) dasselbe Datum als rückwirkend behandelt und
// die Abwesenheits-Stunden retargetet. Die laut Spezifikation zwingende
// ausdrückliche Bestätigung war damit umgehbar.
//
// (`dayBefore` rechnet weiterhin bewusst in UTC — dort geht es um reine
// Tagesarithmetik auf einem bereits feststehenden Datum, ohne DST-Rollover.)
function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Debounce (ms), bevor die rein lesende Vorschau abgerufen wird, während der
// Admin Datum/Stunden noch anpasst.
const PREVIEW_DEBOUNCE_MS = 400;

export default function WorkingHoursModal({ userId, userName, currentWeeklyHours, onClose, onChanged }: WorkingHoursModalProps) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [hoursChanges, setHoursChanges] = useState<WorkingHoursChange[]>([]);
  // Guards against double-submit (fast double-click would add duplicate hours changes).
  const [submitting, setSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    effective_from: todayIso(),
    weekly_hours: currentWeeklyHours,
    note: '',
  });

  // Task 7: rückwirkende Vorschau (Zeitraum, altes/neues Tagessoll, betroffene
  // Abwesenheiten, abgeschlossene Jahre, Blockade-Grund) — siehe Backend
  // GET .../working-hours-changes/preview.
  const [preview, setPreview] = useState<WorkingHoursChangePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  // Der Kern des Verständnisproblems: eine rückwirkende Änderung darf erst
  // nach ausdrücklicher Bestätigung der Vorschau gespeichert werden.
  const [confirmedRetroactive, setConfirmedRetroactive] = useState(false);

  const isRetroactive = formData.effective_from < todayIso();

  useEffect(() => {
    fetchHoursChanges();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // Jede Änderung an Datum/Stunden entwertet eine zuvor gegebene Bestätigung
  // — der Admin muss die (ggf. neue) Vorschau erneut bestätigen. Nur bei
  // einem Datum in der Vergangenheit wird überhaupt eine Vorschau geladen;
  // ein zukünftiges Datum betrifft ausschließlich noch nicht gebuchte Tage
  // und zeigt deshalb keinen Warnblock.
  useEffect(() => {
    setConfirmedRetroactive(false);
    if (!isRetroactive) {
      setPreview(null);
      setPreviewLoading(false);
      return;
    }
    setPreviewLoading(true);
    const handle = setTimeout(() => {
      apiClient
        .get(`/admin/users/${userId}/working-hours-changes/preview`, {
          params: { effective_from: formData.effective_from, weekly_hours: formData.weekly_hours },
        })
        .then((res) => setPreview(res.data))
        .catch(() => setPreview(null))
        .finally(() => setPreviewLoading(false));
    }, PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, formData.effective_from, formData.weekly_hours]);

  const fetchHoursChanges = async () => {
    try {
      const response = await apiClient.get(`/admin/users/${userId}/working-hours-changes`);
      setHoursChanges(Array.isArray(response.data) ? response.data : []); // #382
    } catch (error) {
      toast.error('Fehler beim Laden der Stundenhistorie');
    }
  };

  // Task 7: "ab … bis …" statt nur "ab …" — das Ende ergibt sich implizit aus
  // dem jeweils nächsten Eintrag (Vortag), der jüngste Eintrag läuft "bis
  // heute". Genau dieses implizite Ende war der Kern des Verständnisproblems.
  const historyEndDates = useMemo(() => {
    const asc = [...hoursChanges].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
    const map = new Map<string, string | null>();
    asc.forEach((c, idx) => {
      const next = asc[idx + 1];
      map.set(c.id, next ? dayBefore(next.effective_from) : null);
    });
    return map;
  }, [hoursChanges]);

  // I4: Das Backend lehnt das Löschen der FRÜHESTEN Zeile ab, solange spätere
  // existieren — sie verankert den davor gültigen Wert, der sonst nirgends
  // mehr gespeichert ist. Verbieten und trotzdem anbieten ist schlechte
  // Führung: der Löschen-Button ist dort deaktiviert und nennt den Grund.
  // Ist es die EINZIGE Zeile, bleibt das Löschen erlaubt (Backend genauso).
  const lockedEarliestId = useMemo(() => {
    if (hoursChanges.length < 2) return null;
    const asc = [...hoursChanges].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
    return asc[0].id;
  }, [hoursChanges]);

  const LOCKED_EARLIEST_HINT =
    'Die früheste erfasste Stundenänderung verankert den davor gültigen Wert — '
    + 'bitte zuerst die späteren Änderungen löschen.';

  const blockedReason = isRetroactive ? preview?.blocked_reason ?? null : null;
  // Solange die Vorschau für ein rückwirkendes Datum noch lädt/fehlt, blockiert
  // oder noch nicht bestätigt ist, bleibt „Hinzufügen" gesperrt — der Nutzer
  // soll nicht ungeprüft in einen 400 laufen (blocked_reason) oder eine
  // rückwirkende Änderung ohne die Vorschau gesehen zu haben speichern.
  const saveDisabled =
    submitting ||
    (isRetroactive && (previewLoading || !preview || !!preview.blocked_reason || !confirmedRetroactive));

  const handleAddHoursChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saveDisabled) return;
    setSubmitting(true);
    try {
      const res = await apiClient.post(`/admin/users/${userId}/working-hours-changes`, formData);
      await fetchHoursChanges();
      onChanged();
      setFormData({
        effective_from: todayIso(),
        weekly_hours: currentWeeklyHours,
        note: '',
      });
      setPreview(null);
      setConfirmedRetroactive(false);
      // Task 7: adjusted_absences + warning aus der Antwort mit zurückmelden.
      const created: { adjusted_absences?: number; warning?: string | null } = res.data ?? {};
      let message = 'Stundenänderung erfolgreich hinzugefügt';
      if (created.adjusted_absences) {
        message += ` — ${created.adjusted_absences} Abwesenheit(en) auf das neue Tagessoll umgerechnet`;
      }
      toast.success(message);
      if (created.warning) {
        toast.warning(created.warning);
      }
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Hinzufügen'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteHoursChange = (changeId: string) => {
    confirm({
      title: 'Stundenänderung löschen',
      message: 'Möchten Sie diese Stundenänderung wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          const res = await apiClient.delete(`/admin/users/${userId}/working-hours-changes/${changeId}`);
          await fetchHoursChanges();
          onChanged();
          toast.success('Stundenänderung erfolgreich gelöscht');
          // I3: Berührt die Rückrechnung ein bereits abgeschlossenes Jahr,
          // antwortet das Backend mit 200 + {warning} statt 204 ohne Body
          // (Muster von delete_closure / Urlaubs-Storno). Bei 204 setzt axios
          // data auf '' — der Objekt-Check fängt das ab.
          const body = res?.data;
          const warning = body && typeof body === 'object' ? (body as { warning?: string }).warning : undefined;
          if (warning) {
            toast.warning(warning);
          }
        } catch (error: unknown) {
          // I4: Der Grund kommt vom Backend (z. B. „…verankert den davor
          // gültigen Wert… bitte zuerst die späteren Änderungen löschen") —
          // eine hardcodierte Meldung verschluckte ihn. Parität zum Anlegen.
          toast.error(getErrorMessage(error, 'Fehler beim Löschen der Stundenänderung'));
        }
      },
    });
  };

  return (
    <>
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <div
        className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
        onClick={onClose}
      >
        <FocusTrap
          focusTrapOptions={{
            allowOutsideClick: true,
            escapeDeactivates: true,
            onDeactivate: onClose,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="hours-modal-title"
            className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 id="hours-modal-title" className="text-2xl font-bold text-gray-900">Stundenverlauf</h2>
                <p className="text-sm text-gray-600 mt-1">
                  {userName} • Aktuell: {currentWeeklyHours} Std/Woche
                </p>
              </div>
              <button
                onClick={onClose}
                className="text-gray-500 hover:text-gray-700"
                aria-label={`Stundenverlauf für ${userName} schließen`}
              >
                <X size={24} />
              </button>
            </div>

            <div className="p-6">
              {/* Add New Change Form */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <h3 className="font-semibold text-blue-900 mb-3">Neue Stundenänderung</h3>
                <form onSubmit={handleAddHoursChange} className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label htmlFor="wh-effective-from" className="block text-sm font-medium text-gray-700 mb-1">
                      Gültig ab
                    </label>
                    <input
                      id="wh-effective-from"
                      type="date"
                      value={formData.effective_from}
                      onChange={(e) => setFormData({ ...formData, effective_from: e.target.value })}
                      required
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label htmlFor="wh-weekly-hours" className="block text-sm font-medium text-gray-700 mb-1">
                      Wochenstunden
                    </label>
                    <input
                      id="wh-weekly-hours"
                      type="number"
                      step="0.5"
                      value={formData.weekly_hours}
                      onChange={(e) => setFormData({ ...formData, weekly_hours: parseHours(e.target.value) })}
                      required
                      min="0"
                      max="60"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label htmlFor="wh-note" className="block text-sm font-medium text-gray-700 mb-1">
                      Notiz (optional)
                    </label>
                    <input
                      id="wh-note"
                      type="text"
                      value={formData.note}
                      onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                      placeholder="z.B. Teilzeitänderung"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>

                  {/* Task 7: rückwirkender Hinweis — VOR dem Speichern zeigen, was
                      die Änderung anfasst (Zeitraum, altes → neues Tagessoll,
                      betroffene Abwesenheiten, abgeschlossenes Jahr), plus
                      Blockade-Grund bzw. Bestätigungspflicht. */}
                  {isRetroactive && (
                    <div
                      role="status"
                      className={`md:col-span-3 rounded-lg border p-3 text-sm ${
                        blockedReason ? 'bg-red-50 border-red-300' : 'bg-amber-50 border-amber-300'
                      }`}
                    >
                      {previewLoading ? (
                        <p className="text-gray-600">Prüfe Auswirkungen…</p>
                      ) : preview ? (
                        <>
                          <p className="font-semibold text-amber-900">
                            Rückwirkende Änderung: {formatDate(preview.period_start)} – {formatDate(preview.period_end)}
                          </p>
                          <p className="text-amber-800 mt-1">
                            Tagessoll {preview.current_daily_target.toFixed(1)}h → {preview.new_daily_target.toFixed(1)}h.{' '}
                            {preview.affected_absences} Abwesenheit(en) betroffen.
                          </p>
                          {preview.closed_year_warning && (
                            <p className="text-amber-900 font-medium mt-1">{preview.closed_year_warning}</p>
                          )}
                          {blockedReason ? (
                            <p className="text-red-700 font-medium mt-2">{blockedReason}</p>
                          ) : (
                            <label className="flex items-center gap-2 mt-2 text-amber-900 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={confirmedRetroactive}
                                onChange={(e) => setConfirmedRetroactive(e.target.checked)}
                                className="w-4 h-4 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
                              />
                              Ich habe die Auswirkungen geprüft und möchte trotzdem speichern
                            </label>
                          )}
                        </>
                      ) : null}
                    </div>
                  )}

                  <div className="md:col-span-3">
                    <button
                      type="submit"
                      disabled={saveDisabled}
                      className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Plus size={18} />
                      <span>Hinzufügen</span>
                    </button>
                  </div>
                </form>
              </div>

              {/* History List */}
              <div>
                <h3 className="font-semibold text-gray-900 mb-3">Verlauf</h3>
                {hoursChanges.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">Keine Änderungen vorhanden</p>
                ) : (
                  <div className="space-y-3">
                    {hoursChanges.map((change) => {
                      const end = historyEndDates.get(change.id);
                      return (
                        <div
                          key={change.id}
                          className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex items-center justify-between"
                        >
                          <div>
                            <p className="font-medium text-gray-900">
                              Ab {formatDate(change.effective_from)} bis {end ? formatDate(end) : 'heute'}: {change.weekly_hours} Std/Woche
                            </p>
                            {change.note && (
                              <p className="text-sm text-gray-600 mt-1">{change.note}</p>
                            )}
                            <p className="text-xs text-gray-500 mt-1">
                              Erstellt: {new Date(change.created_at).toLocaleDateString('de-DE', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                          </div>
                          {change.id === lockedEarliestId ? (
                            // Der Titel sitzt am umschließenden <span>: ein
                            // disabled <button> feuert keine Hover-Events, der
                            // Tooltip käme dort nie an.
                            <span title={LOCKED_EARLIEST_HINT} className="shrink-0">
                              <button
                                type="button"
                                disabled
                                aria-label="Löschen nicht möglich – früheste Stundenänderung"
                                className="text-gray-300 cursor-not-allowed"
                              >
                                <Trash2 size={18} />
                              </button>
                            </span>
                          ) : (
                            <button
                              onClick={() => handleDeleteHoursChange(change.id)}
                              className="text-red-600 hover:text-red-800"
                              title="Löschen"
                            >
                              <Trash2 size={18} />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-800">
                  <strong>Hinweis:</strong> Die Berechnungen von Soll-Stunden berücksichtigen automatisch die
                  historischen Werte. Wenn z.B. jemand ab 15.03. von 20h auf 30h wechselt, werden für den
                  März die ersten 14 Tage mit 20h und ab dem 15. mit 30h berechnet.
                </p>
              </div>
            </div>
          </div>
        </FocusTrap>
      </div>
    </>
  );
}
