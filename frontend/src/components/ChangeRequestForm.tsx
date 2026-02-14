import { useState } from 'react';
import { X, ArrowRight } from 'lucide-react';
import apiClient from '../api/client';

interface TimeEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string;
  break_minutes: number;
  note?: string;
}

interface Props {
  entry: TimeEntry | null; // null for CREATE
  requestType: 'create' | 'update' | 'delete';
  onClose: () => void;
  onSuccess: () => void;
}

export default function ChangeRequestForm({ entry, requestType, onClose, onSuccess }: Props) {
  const [formData, setFormData] = useState({
    proposed_date: entry?.date || '',
    proposed_start_time: entry?.start_time?.substring(0, 5) || '08:00',
    proposed_end_time: entry?.end_time?.substring(0, 5) || '17:00',
    proposed_break_minutes: entry?.break_minutes ?? 0,
    proposed_note: entry?.note || '',
    reason: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.reason.trim()) {
      setError('Bitte geben Sie eine Begründung an');
      return;
    }

    setSubmitting(true);
    setError('');

    try {
      await apiClient.post('/change-requests', {
        request_type: requestType,
        time_entry_id: entry?.id || null,
        proposed_date: requestType !== 'delete' ? formData.proposed_date : null,
        proposed_start_time: requestType !== 'delete' ? formData.proposed_start_time : null,
        proposed_end_time: requestType !== 'delete' ? formData.proposed_end_time : null,
        proposed_break_minutes: requestType !== 'delete' ? formData.proposed_break_minutes : null,
        proposed_note: requestType !== 'delete' ? formData.proposed_note : null,
        reason: formData.reason,
      });
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Erstellen des Antrags');
    } finally {
      setSubmitting(false);
    }
  };

  const typeLabels = {
    create: 'Neuer Eintrag (vergangener Tag)',
    update: 'Eintrag ändern',
    delete: 'Eintrag löschen',
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-amber-500 text-white rounded-t-xl">
          <h2 className="text-lg font-bold">Änderungsantrag: {typeLabels[requestType]}</h2>
          <button onClick={onClose} className="hover:bg-white/20 rounded-lg p-1 transition">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {/* For DELETE: show what will be deleted */}
          {requestType === 'delete' && entry && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h3 className="font-semibold text-red-800 mb-2">Eintrag zum Löschen</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-gray-500">Datum:</span> {entry.date}</div>
                <div><span className="text-gray-500">Von:</span> {entry.start_time?.substring(0, 5)}</div>
                <div><span className="text-gray-500">Bis:</span> {entry.end_time?.substring(0, 5)}</div>
                <div><span className="text-gray-500">Pause:</span> {entry.break_minutes} min</div>
              </div>
            </div>
          )}

          {/* For UPDATE: show old vs new side by side */}
          {requestType === 'update' && entry && (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <h3 className="font-semibold text-gray-700 mb-3">Aktuelle Werte</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-gray-500">Datum:</span> {entry.date}</div>
                <div><span className="text-gray-500">Von:</span> {entry.start_time?.substring(0, 5)}</div>
                <div><span className="text-gray-500">Bis:</span> {entry.end_time?.substring(0, 5)}</div>
                <div><span className="text-gray-500">Pause:</span> {entry.break_minutes} min</div>
                {entry.note && <div className="col-span-2"><span className="text-gray-500">Notiz:</span> {entry.note}</div>}
              </div>
              <div className="flex items-center justify-center my-3">
                <ArrowRight className="text-gray-400" size={20} />
                <span className="text-xs text-gray-400 ml-1">Neue Werte</span>
              </div>
            </div>
          )}

          {/* Proposed values form (for CREATE and UPDATE) */}
          {requestType !== 'delete' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Datum</label>
                <input
                  type="date"
                  value={formData.proposed_date}
                  onChange={(e) => setFormData({ ...formData, proposed_date: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Von</label>
                <input
                  type="time"
                  value={formData.proposed_start_time}
                  onChange={(e) => setFormData({ ...formData, proposed_start_time: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
                <input
                  type="time"
                  value={formData.proposed_end_time}
                  onChange={(e) => setFormData({ ...formData, proposed_end_time: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Pause (Min.)</label>
                <input
                  type="number"
                  min="0"
                  value={formData.proposed_break_minutes}
                  onChange={(e) => setFormData({ ...formData, proposed_break_minutes: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
                <input
                  type="text"
                  value={formData.proposed_note}
                  onChange={(e) => setFormData({ ...formData, proposed_note: e.target.value })}
                  placeholder="Optional"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500"
                />
              </div>
            </div>
          )}

          {/* Reason (always required) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Begründung <span className="text-red-500">*</span>
            </label>
            <textarea
              value={formData.reason}
              onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
              rows={3}
              required
              placeholder="Warum ist diese Änderung notwendig?"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500"
            />
          </div>

          {/* Actions */}
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
              {submitting ? 'Wird gesendet...' : 'Antrag stellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
