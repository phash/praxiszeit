import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import DialogFocusTrap from './DialogFocusTrap';
import apiClient from '../api/client';
import { getErrorMessage } from '../utils/errorMessage';
import { formatIsoDateDe, formatHoursHM } from '../utils/formatters';
import { absenceTypeLabel } from '../constants/absenceTypes';

export interface AbsenceToDelete {
  id: string;
  date: string;
  end_date?: string | null;
  type: string;
  hours: number;
}

interface Props {
  absence: AbsenceToDelete;
  onClose: () => void;
  onSuccess: () => void;
}

/**
 * P1.1: Lösch-Antrag für eine eigene Abwesenheit eines vergangenen Tages.
 * Mitarbeitende löschen sie nicht direkt (Server 409 ``PAST_DAY_ABSENCE_DETAIL``);
 * der Antrag geht an ``POST /change-requests/`` mit ``entry_kind="absence"``.
 * Aufbau und Pflicht-Begründung wie ``ChangeRequestForm`` (Lösch-Antrag eines
 * Zeiteintrags). Die Genehmigung löscht die Abwesenheit samt Protokollzeile,
 * Betriebsferien-Neubuchung und #314-Neuaufteilung (``review_change_request``).
 */
export default function AbsenceDeleteRequestDialog({ absence, onClose, onSuccess }: Props) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) {
      setError('Bitte geben Sie eine Begründung an');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await apiClient.post('/change-requests/', {
        request_type: 'delete',
        entry_kind: 'absence',
        absence_id: absence.id,
        reason: reason.trim(),
      });
      onSuccess();
    } catch (err) {
      setError(getErrorMessage(err, 'Fehler beim Einreichen'));
    } finally {
      setSubmitting(false);
    }
  };

  const dateText = absence.end_date && absence.end_date !== absence.date
    ? `${formatIsoDateDe(absence.date)} – ${formatIsoDateDe(absence.end_date)}`
    : formatIsoDateDe(absence.date);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <DialogFocusTrap focusTrapOptions={{ allowOutsideClick: true, initialFocus: false }}>
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="absence-delete-cr-title"
          className="bg-white rounded-xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto"
        >
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-amber-500 text-white rounded-t-xl">
            <h2 id="absence-delete-cr-title" className="text-lg font-bold">Änderungsantrag: Löschung beantragen</h2>
            <button type="button" onClick={onClose} aria-label="Schließen" className="hover:bg-white/20 rounded-lg p-1 transition">
              <X size={20} aria-hidden="true" />
            </button>
          </div>

          <form onSubmit={handleSubmit} noValidate className="p-6 space-y-6">
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}

            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h3 className="font-semibold text-red-800 mb-2">Abwesenheit zum Löschen</h3>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="text-gray-500">Datum:</dt>
                <dd>{dateText}</dd>
                <dt className="text-gray-500">Art:</dt>
                <dd>{absenceTypeLabel(absence.type)}</dd>
                <dt className="text-gray-500">Stunden:</dt>
                <dd>{`${formatHoursHM(absence.hours)} h`}</dd>
              </dl>
            </div>

            <div>
              <label htmlFor="absence-delete-cr-reason" className="block text-sm font-medium text-gray-700 mb-1">
                Begründung <span className="text-red-500">*</span>
              </label>
              <textarea
                id="absence-delete-cr-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                required
                placeholder="Warum soll die Abwesenheit gelöscht werden?"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500"
              />
              <p className="mt-1 text-xs text-gray-500">
                Die Verwaltung prüft den Antrag. Erst mit der Genehmigung wird die Abwesenheit gelöscht.
              </p>
            </div>

            <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg transition"
              >
                Abbrechen
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition disabled:opacity-50"
              >
                {submitting ? 'Wird gesendet …' : 'Antrag stellen'}
              </button>
            </div>
          </form>
        </div>
      </DialogFocusTrap>
    </div>
  );
}
