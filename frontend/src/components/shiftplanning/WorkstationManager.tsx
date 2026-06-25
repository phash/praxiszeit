import { useState } from 'react';
import { Plus, Trash2, Pencil, X, Monitor } from 'lucide-react';
import Button from '../Button';
import FormInput from '../FormInput';
import FormSelect from '../FormSelect';
import EmptyState from '../EmptyState';
import ConfirmDialog from '../ConfirmDialog';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import { getErrorMessage } from '../../utils/errorMessage';
import { DEFAULT_WS_COLORS } from './weekGridUtils';
import * as api from '../../api/shiftPlanning';
import type { Location, Workstation } from '../../api/shiftPlanning';

interface Props {
  workstations: Workstation[];
  locations: Location[];
  onChanged: () => void;
}

const emptyForm = { name: '', location_id: '', color: DEFAULT_WS_COLORS[0] };

export default function WorkstationManager({ workstations, locations, onChanged }: Props) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [form, setForm] = useState(emptyForm);
  const [editId, setEditId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setForm(emptyForm);
    setEditId(null);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || submitting) return;
    setSubmitting(true);
    const body = {
      name: form.name.trim(),
      location_id: form.location_id || null,
      color: form.color || null,
    };
    try {
      if (editId) {
        await api.updateWorkstation(editId, body);
        toast.success('Arbeitsplatz gespeichert');
      } else {
        await api.createWorkstation(body);
        toast.success('Arbeitsplatz angelegt');
      }
      reset();
      onChanged();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    } finally {
      setSubmitting(false);
    }
  };

  const startEdit = (ws: Workstation) => {
    setEditId(ws.id);
    setForm({ name: ws.name, location_id: ws.location_id || '', color: ws.color || DEFAULT_WS_COLORS[0] });
  };

  const remove = (ws: Workstation) =>
    confirm({
      title: 'Arbeitsplatz löschen',
      message: `„${ws.name}" wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await api.deleteWorkstation(ws.id);
          toast.success('Arbeitsplatz gelöscht');
          onChanged();
        } catch (err) {
          toast.error(getErrorMessage(err, 'Fehler beim Löschen'));
        }
      },
    });

  return (
    <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <h3 className="text-lg font-semibold mb-4">Arbeitsplätze</h3>

      <form onSubmit={submit} className="space-y-3 mb-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FormInput
            label="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="z. B. Tresen"
          />
          <FormSelect
            label="Standort (optional)"
            value={form.location_id}
            onChange={(e) => setForm({ ...form, location_id: e.target.value })}
          >
            <option value="">— ohne Standort —</option>
            {locations.map((loc) => (
              <option key={loc.id} value={loc.id}>
                {loc.name}
              </option>
            ))}
          </FormSelect>
        </div>
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Farbe</label>
            <input
              type="color"
              value={form.color}
              onChange={(e) => setForm({ ...form, color: e.target.value })}
              className="h-9 w-16 rounded border border-gray-300"
              aria-label="Farbe"
            />
          </div>
          <Button type="submit" variant="primary" icon={editId ? Pencil : Plus} loading={submitting} disabled={!form.name.trim()}>
            {editId ? 'Speichern' : 'Hinzufügen'}
          </Button>
          {editId && (
            <Button type="button" variant="ghost" icon={X} onClick={reset}>
              Abbrechen
            </Button>
          )}
        </div>
      </form>

      {workstations.length === 0 ? (
        <EmptyState icon={Monitor} title="Keine Arbeitsplätze" description="Legen Sie z. B. Tresen, Labor oder Springer an." />
      ) : (
        <ul className="divide-y divide-gray-100">
          {workstations.map((ws) => (
            <li key={ws.id} className="flex items-center justify-between py-2 gap-2">
              <span className="flex items-center gap-2 text-sm text-gray-800">
                <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: ws.color || '#9ca3af' }} />
                {ws.name}
                {ws.location_name && <span className="text-xs text-gray-400">· {ws.location_name}</span>}
              </span>
              <div className="flex items-center gap-1">
                <button onClick={() => startEdit(ws)} aria-label="Bearbeiten" className="text-gray-400 hover:text-primary p-1">
                  <Pencil size={16} />
                </button>
                <button onClick={() => remove(ws)} aria-label="Löschen" className="text-gray-400 hover:text-danger p-1">
                  <Trash2 size={16} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
