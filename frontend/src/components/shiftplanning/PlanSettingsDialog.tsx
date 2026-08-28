import { useEffect, useState } from 'react';
import FocusTrap from 'focus-trap-react';
import { X } from 'lucide-react';
import Button from '../Button';
import FormInput from '../FormInput';
import FormTextarea from '../FormTextarea';
import { useToast } from '../../contexts/ToastContext';
import { getErrorMessage } from '../../utils/errorMessage';
import * as api from '../../api/shiftPlanning';
import type { PlanDetail } from '../../api/shiftPlanning';

interface Props {
  isOpen: boolean;
  plan: PlanDetail;
  onSaved: () => void;
  onClose: () => void;
}

/**
 * Plan-Einstellungen (#305 M2): Name, Beschreibung und das optionale
 * Aktiv-Datums-Fenster (KW-Planung) eines Schichtplans bearbeiten.
 */
export default function PlanSettingsDialog({ isOpen, plan, onSaved, onClose }: Props) {
  const toast = useToast();
  const [name, setName] = useState(plan.name);
  const [description, setDescription] = useState(plan.description ?? '');
  const [from, setFrom] = useState(plan.active_from_date ?? '');
  const [until, setUntil] = useState(plan.active_until_date ?? '');
  const [visible, setVisible] = useState(plan.visible_to_employees);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setName(plan.name);
      setDescription(plan.description ?? '');
      setFrom(plan.active_from_date ?? '');
      setUntil(plan.active_until_date ?? '');
      setVisible(plan.visible_to_employees);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const windowInvalid = !!from && !!until && from > until;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || windowInvalid || submitting) return;
    setSubmitting(true);
    try {
      await api.updatePlan(plan.id, {
        name: name.trim(),
        description: description.trim() || null,
        active_from_date: from || null,
        active_until_date: until || null,
        visible_to_employees: visible,
      });
      toast.success('Plan gespeichert');
      onSaved();
      onClose();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: true, onDeactivate: onClose }}>
        <div className="bg-white rounded-xl shadow-lg w-full max-w-lg">
          <div className="flex items-center justify-between border-b border-gray-200 p-4">
            <h3 className="text-lg font-semibold text-gray-900">Plan-Einstellungen</h3>
            <button onClick={onClose} aria-label="Schließen" className="text-gray-400 hover:text-gray-600">
              <X size={20} />
            </button>
          </div>
          <form onSubmit={save} className="p-4 space-y-4">
            {/* #461 K-9: 255 wie die Server-Grenze (#450). Ohne sie meldet das
                Hinweisfenster die englische Pydantic-Rohmeldung. */}
            <FormInput label="Name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={255} />
            <FormTextarea
              label="Beschreibung (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
            <div>
              <span className="block text-sm font-medium text-gray-700 mb-1">
                Automatisch aktiv im Zeitraum (optional)
              </span>
              <div className="grid grid-cols-2 gap-4">
                <FormInput label="von" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
                <FormInput
                  label="bis"
                  type="date"
                  value={until}
                  onChange={(e) => setUntil(e.target.value)}
                  error={windowInvalid ? '„bis" darf nicht vor „von" liegen' : undefined}
                />
              </div>
              <p className="mt-1 text-xs text-gray-400">
                Leer lassen für „keine automatische Aktivierung". Eine offene Grenze ist erlaubt (nur „von" oder nur „bis").
                Unabhängig davon kann der Plan jederzeit manuell aktiv geschaltet werden.
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 p-3">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={(e) => setVisible(e.target.checked)}
                  className="mt-0.5 rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">
                  Für Mitarbeitende sichtbar
                  <span className="mt-1 block text-xs text-gray-400">
                    Der Plan erscheint dann in der Mitarbeiteransicht, auch wenn er heute noch nicht gilt —
                    etwa um einen ab September geltenden Plan vorab bekannt zu machen. Ein heute aktiver Plan
                    ist ohnehin sichtbar.
                  </span>
                </span>
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" type="button" onClick={onClose}>
                Abbrechen
              </Button>
              <Button variant="primary" type="submit" loading={submitting} disabled={submitting || windowInvalid || !name.trim()}>
                Speichern
              </Button>
            </div>
          </form>
        </div>
      </FocusTrap>
    </div>
  );
}
