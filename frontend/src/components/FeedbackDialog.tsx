import { useState } from 'react';
import FocusTrap from 'focus-trap-react';
import { Bug, Send, X } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { getErrorMessage } from '../utils/errorMessage';

interface FeedbackDialogProps {
  onClose: () => void;
}

type Severity = 'low' | 'medium' | 'high' | 'critical';

const SEVERITY_OPTIONS: { value: Severity; label: string }[] = [
  { value: 'low', label: 'Niedrig' },
  { value: 'medium', label: 'Mittel' },
  { value: 'high', label: 'Hoch' },
  { value: 'critical', label: 'Kritisch' },
];

/**
 * Fehler-/Feedback-Dialog (#136). Sendet Titel + Beschreibung + Schweregrad an
 * den Backend-Proxy (POST /api/feedback/report), der license_id, App-Version
 * und OS serverseitig ergaenzt und an pzweb weiterleitet.
 */
export default function FeedbackDialog({ onClose }: FeedbackDialogProps) {
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState<Severity>('medium');
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = title.trim().length > 0 && description.trim().length > 0 && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await apiClient.post('/feedback/report', {
        title: title.trim(),
        description: description.trim(),
        severity,
      });
      toast.success('Danke, deine Meldung wurde übermittelt.');
      onClose();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Meldung konnte nicht gesendet werden.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-[60]"
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
          aria-labelledby="feedback-dialog-title"
          className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Bug size={20} className="text-primary" />
              <h3 id="feedback-dialog-title" className="text-xl font-semibold text-gray-900">
                Fehler melden / Feedback
              </h3>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition"
              aria-label="Dialog schließen"
            >
              <X size={24} />
            </button>
          </div>

          <p className="text-sm text-gray-600 mb-4">
            Beschreibe kurz, was nicht funktioniert oder was du dir wünschst. Die Meldung
            geht direkt an das PraxisZeit-Team.
          </p>

          <div className="mb-4">
            <label htmlFor="fb-title" className="block text-sm font-medium text-gray-700 mb-1">
              Titel
            </label>
            <input
              id="fb-title"
              type="text"
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Kurzbeschreibung (max. 200 Zeichen)"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              autoFocus
            />
            <p className="text-xs text-gray-400 mt-1 text-right">{title.length}/200</p>
          </div>

          <div className="mb-4">
            <label htmlFor="fb-desc" className="block text-sm font-medium text-gray-700 mb-1">
              Beschreibung
            </label>
            <textarea
              id="fb-desc"
              value={description}
              rows={5}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Was ist passiert? Welche Schritte führen dazu?"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary resize-y"
            />
          </div>

          <div className="mb-4">
            <label htmlFor="fb-sev" className="block text-sm font-medium text-gray-700 mb-1">
              Schweregrad
            </label>
            <select
              id="fb-sev"
              value={severity}
              onChange={(e) => setSeverity(e.target.value as Severity)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary bg-white"
            >
              {SEVERITY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <p className="text-xs text-gray-400 mb-4">
            Version {__APP_VERSION__} · Betriebssystem wird automatisch mitgesendet. Es werden
            keine personenbezogenen Daten automatisch angehängt.
          </p>

          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-3 rounded-lg flex items-center justify-center space-x-2 transition mb-3 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send size={18} />
            <span>{submitting ? 'Wird gesendet …' : 'Senden'}</span>
          </button>

          <button
            onClick={onClose}
            className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg transition"
          >
            Abbrechen
          </button>
        </div>
      </FocusTrap>
    </div>
  );
}
