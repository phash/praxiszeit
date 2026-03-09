import { useState } from 'react';
import { X } from 'lucide-react';
import apiClient from '../api/client';
import { getErrorMessage } from '../utils/errorMessage';
import { useToast } from '../contexts/ToastContext';
import type { DraftChange } from './MonthlyJournal';

const TYPE_LABEL: Record<DraftChange['type'], string> = {
  create: 'Neu anlegen',
  update: 'Ändern',
  delete: 'Löschen',
};

interface Props {
  changes: DraftChange[];
  onSuccess: () => void;
  onClose: () => void;
}

export default function SubmitChangesModal({ changes, onSuccess, onClose }: Props) {
  const toast = useToast();
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (!reason.trim()) {
      toast.error('Bitte eine Begründung angeben');
      return;
    }
    setSubmitting(true);
    let submittedCount = 0;
    try {
      for (const change of changes) {
        const payload: Record<string, unknown> = {
          request_type: change.type,
          reason: reason.trim(),
        };
        if (change.entryId) payload.time_entry_id = change.entryId;
        if (change.type !== 'delete') {
          payload.proposed_date = change.date;
          payload.proposed_start_time = change.startTime;
          payload.proposed_end_time = change.endTime;
          payload.proposed_break_minutes = change.breakMinutes ?? 0;
        }
        await apiClient.post('/change-requests/', payload);
        submittedCount++;
      }
      toast.success(`${changes.length} Änderungsantrag${changes.length > 1 ? 'anträge' : ''} eingereicht`);
      onSuccess();
    } catch (err) {
      const failedIndex = submittedCount + 1;
      toast.error(
        submittedCount > 0
          ? `Eintrag ${failedIndex} von ${changes.length} fehlgeschlagen: ${getErrorMessage(err, 'Fehler')}`
          : getErrorMessage(err, 'Fehler beim Einreichen')
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Änderungsanträge einreichen</h2>
          <button onClick={onClose} disabled={submitting} className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-50">
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div className="space-y-1">
            <p className="text-sm font-medium text-gray-700">{changes.length} Änderung(en):</p>
            <ul className="text-sm text-gray-600 space-y-0.5">
              {changes.map((c, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-gray-400">{c.date}</span>
                  <span>{TYPE_LABEL[c.type]}</span>
                  {c.startTime && c.endTime && (
                    <span className="text-gray-500">{c.startTime}–{c.endTime}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Begründung <span className="text-red-500">*</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Warum müssen diese Zeiten angepasst werden?"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 text-sm text-gray-700 border rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Abbrechen
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !reason.trim()}
            className="px-4 py-2 text-sm bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50"
          >
            {submitting ? 'Wird eingereicht…' : 'Absenden'}
          </button>
        </div>
      </div>
    </div>
  );
}
