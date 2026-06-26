import { useState } from 'react';
import FocusTrap from 'focus-trap-react';
import { X, Wand2 } from 'lucide-react';
import Button from '../Button';
import FormInput from '../FormInput';
import { useToast } from '../../contexts/ToastContext';
import { getErrorMessage } from '../../utils/errorMessage';
import * as api from '../../api/shiftPlanning';
import { mondayOfWeek } from './weekGridUtils';

interface Props {
  planId: string;
  onGenerated: () => void;
  onClose: () => void;
}

function thisMonday(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return mondayOfWeek(`${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`);
}

/**
 * Auto-Generierung (#305 M2): wählt eine Zielwoche (für Abwesenheiten/Stunden)
 * und einen Modus; ruft den Greedy-Generator und meldet das Ergebnis.
 */
export default function GenerateDialog({ planId, onGenerated, onClose }: Props) {
  const toast = useToast();
  const [weekDate, setWeekDate] = useState(thisMonday());
  const [mode, setMode] = useState<'replace' | 'fill_gaps'>('replace');
  const [submitting, setSubmitting] = useState(false);

  const monday = weekDate ? mondayOfWeek(weekDate) : '';

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!monday || submitting) return;
    setSubmitting(true);
    try {
      const res = await api.generatePlan(planId, { target_monday: monday, mode });
      const unfilled = res.generation.unfilled_slot_ids.length;
      toast.success(
        `${res.generation.assigned} Zuweisung(en) erstellt` +
          (unfilled > 0 ? ` — ${unfilled} Slot(s) blieben unbesetzt` : ''),
      );
      onGenerated();
      onClose();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Generieren'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: true, onDeactivate: onClose }}>
        <div className="bg-white rounded-xl shadow-lg w-full max-w-md">
          <div className="flex items-center justify-between border-b border-gray-200 p-4">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-gray-900">
              <Wand2 size={18} className="text-primary" /> Automatisch füllen
            </h3>
            <button onClick={onClose} aria-label="Schließen" className="text-gray-400 hover:text-gray-600">
              <X size={20} />
            </button>
          </div>
          <form onSubmit={run} className="p-4 space-y-4">
            <p className="text-sm text-gray-500">
              Der Plan wird automatisch mit eingewiesenen, verfügbaren Mitarbeitenden besetzt (ausgewogen nach Auslastung
              und Überstunden). Sie können den Entwurf danach anpassen. Der Plan wird dabei <strong>nicht</strong> aktiviert.
            </p>
            <FormInput
              label="Zielwoche (für Abwesenheiten/Stunden)"
              type="date"
              value={weekDate}
              onChange={(e) => setWeekDate(e.target.value)}
              required
              helperText={monday ? `Woche ab Montag, ${monday}` : undefined}
            />
            <div>
              <span className="block text-sm font-medium text-gray-700 mb-2">Modus</span>
              <label className="flex items-center gap-2 text-sm py-1 cursor-pointer">
                <input type="radio" checked={mode === 'replace'} onChange={() => setMode('replace')} />
                Alle Zuweisungen neu verteilen
              </label>
              <label className="flex items-center gap-2 text-sm py-1 cursor-pointer">
                <input type="radio" checked={mode === 'fill_gaps'} onChange={() => setMode('fill_gaps')} />
                Nur Lücken auffüllen (vorhandene behalten)
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" type="button" onClick={onClose}>
                Abbrechen
              </Button>
              <Button variant="primary" type="submit" icon={Wand2} loading={submitting} disabled={submitting || !monday}>
                Generieren
              </Button>
            </div>
          </form>
        </div>
      </FocusTrap>
    </div>
  );
}
