import { useEffect, useState } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { getErrorMessage } from '../utils/errorMessage';
import { showResponseWarning } from '../utils/arbzgWarnings';
import LoadingSpinner from './LoadingSpinner';

interface ReducedDay {
  id: string;
  date: string; // ISO YYYY-MM-DD
  label: string;
  max_hours: number;
}

function formatGermanDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  if (!y || !m || !d) return iso;
  return `${d}.${m}.${y}`;
}

const INPUT = 'px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary';

export default function ReducedDaysCard() {
  const toast = useToast();
  const currentYear = new Date().getFullYear();
  const yearOptions = [currentYear - 1, currentYear, currentYear + 1, currentYear + 2];
  const [year, setYear] = useState(currentYear);
  const [days, setDays] = useState<ReducedDay[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [newDate, setNewDate] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [newHours, setNewHours] = useState('4');
  // Entwürfe der Zeilen: id -> {label, hours}
  const [drafts, setDrafts] = useState<Record<string, { label: string; hours: string }>>({});

  const load = async (y: number) => {
    setLoading(true);
    try {
      const res = await apiClient.get<ReducedDay[]>(`/admin/reduced-days?year=${y}`);
      setDays(res.data);
      setDrafts({});
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  // Nur beim Mount und Jahreswechsel laden, nie über die toast-Referenz.
  useEffect(() => {
    void load(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  const parseHours = (v: string) => Number(v.replace(',', '.'));

  const add = async () => {
    if (!newDate || !newLabel.trim()) return;
    setBusy(true);
    try {
      const res = await apiClient.post('/admin/reduced-days', {
        date: newDate,
        label: newLabel.trim(),
        max_hours: parseHours(newHours),
      });
      showResponseWarning(toast, res?.data);
      setNewDate('');
      setNewLabel('');
      await load(year);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const save = async (d: ReducedDay) => {
    const draft = drafts[d.id];
    if (!draft) return;
    setBusy(true);
    try {
      const res = await apiClient.put(`/admin/reduced-days/${d.id}`, {
        date: d.date,
        label: draft.label.trim(),
        max_hours: parseHours(draft.hours),
      });
      showResponseWarning(toast, res?.data);
      await load(year);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (d: ReducedDay) => {
    setBusy(true);
    try {
      const res = await apiClient.delete(`/admin/reduced-days/${d.id}`);
      showResponseWarning(toast, res?.data);
      await load(year);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const setDraft = (d: ReducedDay, patch: Partial<{ label: string; hours: string }>) =>
    setDrafts((prev) => ({
      ...prev,
      [d.id]: { ...{ label: d.label, hours: String(d.max_hours) }, ...prev[d.id], ...patch },
    }));

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
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
          <input id="reduced-new-hours" type="number" step="0.25" min="0.25" max="12" value={newHours}
            onChange={(e) => setNewHours(e.target.value)} className={`${INPUT} w-28`} />
        </div>
        <button
          onClick={add}
          disabled={busy || !newDate || !newLabel.trim()}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Plus size={16} />
          Hinzufügen
        </button>
      </div>

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
                return (
                  <tr key={d.id} className="border-b last:border-0">
                    <td className="py-2 pr-4">{formatGermanDate(d.date)}</td>
                    <td className="py-2 pr-4">
                      {draft ? (
                        <input type="text" maxLength={100} aria-label={`Bezeichnung ${formatGermanDate(d.date)}`}
                          value={draft.label} onChange={(e) => setDraft(d, { label: e.target.value })}
                          className={INPUT} />
                      ) : (
                        <span
                          role="button" tabIndex={0}
                          onClick={() => setDraft(d, {})}
                          onKeyDown={(e) => { if (e.key === 'Enter') setDraft(d, {}); }}
                          className="cursor-text"
                        >{d.label}</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <input type="number" step="0.25" min="0.25" max="12"
                        aria-label={`Höchstens (Stunden) ${formatGermanDate(d.date)}`}
                        value={draft ? draft.hours : String(d.max_hours)}
                        onChange={(e) => setDraft(d, { hours: e.target.value })}
                        className={`${INPUT} w-28`} />
                    </td>
                    <td className="py-2">
                      <div className="flex gap-2 justify-end">
                        {dirty && (
                          <button onClick={() => save(d)} disabled={busy}
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
