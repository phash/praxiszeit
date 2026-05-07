import { useState, useEffect } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { getErrorMessage } from '../utils/errorMessage';
import { parseHours } from '../utils/formatters';

interface VacationRequest {
  id: string;
  date: string;
  end_date?: string;
  hours: number;
  absence_type?: string;
  note?: string;
}

interface VacationRequestEditModalProps {
  request: VacationRequest;
  mode: 'self' | 'admin';
  onClose: () => void;
  onSaved: () => void;
}

export default function VacationRequestEditModal({
  request,
  mode,
  onClose,
  onSaved,
}: VacationRequestEditModalProps) {
  const toast = useToast();
  const [isDateRange, setIsDateRange] = useState<boolean>(!!request.end_date);
  const [date, setDate] = useState<string>(request.date);
  const [endDate, setEndDate] = useState<string>(request.end_date ?? '');
  const [type, setType] = useState<string>(request.absence_type ?? 'vacation');
  const [hours, setHours] = useState<number>(Number(request.hours) || 8);
  const [note, setNote] = useState<string>(request.note ?? '');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setDate(request.date);
    setEndDate(request.end_date ?? '');
    setIsDateRange(!!request.end_date);
    setType(request.absence_type ?? 'vacation');
    setHours(Number(request.hours) || 8);
    setNote(request.note ?? '');
  }, [request.id]);

  const endpoint =
    mode === 'admin'
      ? `/admin/vacation-requests/${request.id}`
      : `/vacation-requests/${request.id}`;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await apiClient.patch(endpoint, {
        date,
        end_date: isDateRange && endDate ? endDate : null,
        hours,
        absence_type: type,
        note: note || null,
      });
      toast.success('Antrag aktualisiert');
      onSaved();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-10000 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <FocusTrap
        focusTrapOptions={{
          escapeDeactivates: true,
          onDeactivate: onClose,
          allowOutsideClick: true,
        }}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-vr-title"
          className="relative bg-white rounded-xl shadow-2xl max-w-lg w-full mx-4 p-6"
        >
          <h3 id="edit-vr-title" className="text-lg font-semibold text-gray-900 mb-4">
            Antrag bearbeiten
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
              <input
                id="edit-vr-isrange"
                type="checkbox"
                checked={isDateRange}
                onChange={(e) => {
                  setIsDateRange(e.target.checked);
                  if (!e.target.checked) setEndDate('');
                }}
                className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary"
              />
              <label htmlFor="edit-vr-isrange" className="text-sm font-medium text-gray-700 cursor-pointer">
                Zeitraum (mehrere Tage)
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {isDateRange ? 'Von' : 'Datum'}
                </label>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              {isDateRange && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    min={date}
                    required={isDateRange}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                  />
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Typ</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                >
                  <option value="vacation">Urlaub</option>
                  <option value="training">Fortbildung (außer Haus)</option>
                  <option value="overtime">Überstundenausgleich</option>
                  <option value="other">Sonstiges</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Stunden {isDateRange && '(pro Tag)'}
                </label>
                <input
                  type="number"
                  inputMode="numeric"
                  step="0.5"
                  value={hours}
                  onChange={(e) => setHours(parseHours(e.target.value))}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-gray-400 mt-1">
                Bitte keine Gesundheitsangaben oder sensiblen Daten eintragen.
              </p>
            </div>

            <div className="mt-6 flex justify-end space-x-3">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                Abbrechen
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium text-white bg-primary hover:bg-primary-dark rounded-lg transition disabled:opacity-50"
              >
                {submitting ? 'Speichern…' : 'Speichern'}
              </button>
            </div>
          </form>
        </div>
      </FocusTrap>
    </div>
  );
}
