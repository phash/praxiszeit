import { useEffect, useRef, useState } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import { getErrorMessage } from '../utils/errorMessage';
import { showResponseWarning } from '../utils/arbzgWarnings';
import { formatIsoDateDe } from '../utils/formatters';
import {
  DEFAULT_MAX_HOURS, MAX_HOURS_ERROR, MAX_MAX_HOURS, MIN_MAX_HOURS, isValidMaxHours, parseMaxHoursInput,
} from '../utils/specialDays';
import ConfirmDialog from './ConfirmDialog';
import LoadingSpinner from './LoadingSpinner';

interface ReducedDay {
  id: string;
  date: string; // ISO YYYY-MM-DD
  label: string;
  max_hours: number;
}

type Draft = { label: string; hours: string };

const INPUT = 'px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary';

export default function ReducedDaysCard() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  // F097: ein nach dem Hinzufügen angesprungenes Jahr steht immer zur Auswahl.
  const yearOptions = Array.from(new Set([currentYear - 1, currentYear, currentYear + 1, currentYear + 2, year]))
    .sort((a, b) => a - b);
  const [days, setDays] = useState<ReducedDay[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [newDate, setNewDate] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [newHours, setNewHours] = useState(String(DEFAULT_MAX_HOURS));
  // Entwürfe der Zeilen: id -> {label, hours}
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  // F093/F132: nur die Antwort der JÜNGSTEN Anfrage zählt — sonst landet bei
  // schnellem Jahreswechsel die langsamere Vorjahresliste unter dem neuen Jahr.
  const loadSeq = useRef(0);

  /** Lädt das Jahr. `dropDraftId` = die gerade gespeicherte/gelöschte Zeile;
   * Entwürfe anderer, weiter vorhandener Zeilen bleiben stehen (F097). */
  const load = async (y: number, dropDraftId?: string) => {
    const seq = ++loadSeq.current;
    setLoading(true);
    try {
      const res = await apiClient.get<ReducedDay[]>(`/admin/reduced-days?year=${y}`);
      if (seq !== loadSeq.current) return;
      setDays(res.data);
      const ids = new Set(res.data.map((d) => d.id));
      setDrafts((prev) => Object.fromEntries(
        Object.entries(prev).filter(([id]) => id !== dropDraftId && ids.has(id)),
      ));
    } catch (err) {
      if (seq !== loadSeq.current) return;
      toast.error(getErrorMessage(err));
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  };

  // Nur beim Mount und Jahreswechsel laden, nie über die toast-Referenz.
  useEffect(() => {
    void load(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  // F094: ungültige Stunden gehen nie an den Server (0/NaN → 422 mit „Value error,").
  const newHoursValue = parseMaxHoursInput(newHours);
  const newHoursValid = isValidMaxHours(newHoursValue);

  const add = async () => {
    if (!newDate || !newLabel.trim() || !newHoursValid) return;
    setBusy(true);
    try {
      const res = await apiClient.post('/admin/reduced-days', {
        date: newDate,
        label: newLabel.trim(),
        max_hours: newHoursValue,
      });
      toast.success('Verkürzter Tag gespeichert.');
      showResponseWarning(toast, res?.data);
      const addedYear = Number(newDate.slice(0, 4));
      setNewDate('');
      setNewLabel('');
      // F097: ein Tag eines anderen Jahres verschwand sonst still aus der Liste.
      if (addedYear !== year) setYear(addedYear);
      else await load(year);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const save = async (d: ReducedDay) => {
    const draft = drafts[d.id];
    if (!draft) return;
    const hours = parseMaxHoursInput(draft.hours);
    if (!isValidMaxHours(hours) || !draft.label.trim()) return;
    setBusy(true);
    try {
      const res = await apiClient.put(`/admin/reduced-days/${d.id}`, {
        date: d.date,
        label: draft.label.trim(),
        max_hours: hours,
      });
      toast.success('Verkürzter Tag gespeichert.');
      showResponseWarning(toast, res?.data);
      await load(year, d.id);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  // F096: Löschen bucht betroffene Betriebsferien neu — nur nach Rückfrage.
  const remove = (d: ReducedDay) => {
    confirm({
      title: 'Verkürzten Tag löschen',
      message: `Verkürzten Tag „${d.label}“ (${formatIsoDateDe(d.date)}) löschen? Betroffene Betriebsferien werden neu gebucht.`,
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        setBusy(true);
        try {
          const res = await apiClient.delete(`/admin/reduced-days/${d.id}`);
          toast.success('Verkürzter Tag gelöscht.');
          showResponseWarning(toast, res?.data);
          await load(year, d.id);
        } catch (err) {
          toast.error(getErrorMessage(err));
        } finally {
          setBusy(false);
        }
      },
    });
  };

  const setDraft = (d: ReducedDay, patch: Partial<Draft>) =>
    setDrafts((prev) => ({
      ...prev,
      [d.id]: { ...{ label: d.label, hours: String(d.max_hours) }, ...prev[d.id], ...patch },
    }));

  const hoursHint = `${MIN_MAX_HOURS.toString().replace('.', ',')}–${MAX_MAX_HOURS} h in 0,25-Schritten`;

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Verkürzte Tage</h2>
        <div>
          <label htmlFor="reduced-days-year" className="sr-only">Jahr</label>
          <select
            id="reduced-days-year"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className={INPUT}
          >
            {yearOptions.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Für einzelne Tage (z. B. Rosenmontag) beträgt das Soll höchstens die eingetragene
        Stundenzahl. Wer an dem Tag ohnehin weniger Soll hat, behält es. Urlaub an einem
        verkürzten Tag kostet einen halben Tag. Für den 24. und 31.12. die Einstellung
        Sondertage oben verwenden.
      </p>

      <div className="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label htmlFor="reduced-new-date" className="block text-sm font-medium text-gray-700 mb-1">Datum</label>
          <input id="reduced-new-date" type="date" value={newDate}
            onChange={(e) => setNewDate(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label htmlFor="reduced-new-label" className="block text-sm font-medium text-gray-700 mb-1">Bezeichnung</label>
          <input id="reduced-new-label" type="text" maxLength={100} value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label htmlFor="reduced-new-hours" className="block text-sm font-medium text-gray-700 mb-1">Höchstens (Stunden)</label>
          <input id="reduced-new-hours" type="number" step="0.25" min={MIN_MAX_HOURS} max={MAX_MAX_HOURS} value={newHours}
            onChange={(e) => setNewHours(e.target.value)} title={hoursHint}
            aria-invalid={!newHoursValid}
            aria-describedby={newHoursValid ? undefined : 'reduced-new-hours-error'}
            className={`${INPUT} w-28`} />
        </div>
        <button
          onClick={add}
          disabled={busy || !newDate || !newLabel.trim() || !newHoursValid}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Plus size={16} />
          Hinzufügen
        </button>
      </div>
      {!newHoursValid && (
        <p id="reduced-new-hours-error" role="alert" className="-mt-2 mb-4 text-sm text-red-600">{MAX_HOURS_ERROR}</p>
      )}

      {loading ? (
        <LoadingSpinner />
      ) : days.length === 0 ? (
        <p className="text-sm text-gray-500">Keine verkürzten Tage für {year} eingetragen.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-600 border-b">
                <th className="py-2 pr-4">Datum</th>
                <th className="py-2 pr-4">Bezeichnung</th>
                <th className="py-2 pr-4">Höchstens (Stunden)</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {days.map((d) => {
                const draft = drafts[d.id];
                const dirty = !!draft && (draft.label !== d.label || draft.hours !== String(d.max_hours));
                const draftValid = !draft || (isValidMaxHours(parseMaxHoursInput(draft.hours)) && !!draft.label.trim());
                const dateDe = formatIsoDateDe(d.date);
                return (
                  <tr key={d.id} className="border-b last:border-0">
                    <td className="py-2 pr-4">{dateDe}</td>
                    <td className="py-2 pr-4">
                      {draft ? (
                        <input type="text" maxLength={100} aria-label={`Bezeichnung ${dateDe}`}
                          value={draft.label} onChange={(e) => setDraft(d, { label: e.target.value })}
                          className={INPUT} />
                      ) : (
                        // F095: ARIA-Knopf — Enter UND Leertaste, mit Hinweis aufs Bearbeiten.
                        <span
                          role="button" tabIndex={0}
                          aria-label={`Bezeichnung ${dateDe} bearbeiten: ${d.label}`}
                          title="Bezeichnung bearbeiten"
                          onClick={() => setDraft(d, {})}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              setDraft(d, {});
                            }
                          }}
                          className="cursor-text"
                        >{d.label}</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <input type="number" step="0.25" min={MIN_MAX_HOURS} max={MAX_MAX_HOURS}
                        aria-label={`Höchstens (Stunden) ${dateDe}`}
                        aria-invalid={!draftValid}
                        title={hoursHint}
                        value={draft ? draft.hours : String(d.max_hours)}
                        onChange={(e) => setDraft(d, { hours: e.target.value })}
                        className={`${INPUT} w-28`} />
                      {!draftValid && (
                        <p role="alert" className="mt-1 text-xs text-red-600">{MAX_HOURS_ERROR}</p>
                      )}
                    </td>
                    <td className="py-2">
                      <div className="flex gap-2 justify-end">
                        {dirty && (
                          <button onClick={() => save(d)} disabled={busy || !draftValid}
                            className="flex items-center gap-1 px-3 py-1.5 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50">
                            <Save size={14} />
                            Speichern
                          </button>
                        )}
                        <button onClick={() => remove(d)} disabled={busy}
                          className="flex items-center gap-1 px-3 py-1.5 text-red-600 border border-red-200 rounded-lg hover:bg-red-50 disabled:opacity-50">
                          <Trash2 size={14} />
                          Löschen
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
