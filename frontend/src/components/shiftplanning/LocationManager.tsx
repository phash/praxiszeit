import { useState } from 'react';
import { Plus, Trash2, Check, X, Pencil } from 'lucide-react';
import Button from '../Button';
import FormInput from '../FormInput';
import EmptyState from '../EmptyState';
import ConfirmDialog from '../ConfirmDialog';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import { getErrorMessage } from '../../utils/errorMessage';
import { MapPin } from 'lucide-react';
import * as api from '../../api/shiftPlanning';
import type { Location } from '../../api/shiftPlanning';

interface Props {
  locations: Location[];
  onChanged: () => void;
}

export default function LocationManager({ locations, onChanged }: Props) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [newName, setNewName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || submitting) return;
    setSubmitting(true);
    try {
      await api.createLocation(newName.trim());
      setNewName('');
      toast.success('Standort angelegt');
      onChanged();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Anlegen'));
    } finally {
      setSubmitting(false);
    }
  };

  const saveEdit = async (loc: Location) => {
    if (!editName.trim()) return;
    try {
      await api.updateLocation(loc.id, editName.trim(), loc.sort_order);
      setEditId(null);
      toast.success('Standort gespeichert');
      onChanged();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    }
  };

  const remove = (loc: Location) =>
    confirm({
      title: 'Standort löschen',
      message: `„${loc.name}" wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await api.deleteLocation(loc.id);
          toast.success('Standort gelöscht');
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
      <h3 className="text-lg font-semibold mb-4">Standorte</h3>

      <form onSubmit={add} className="flex items-end gap-2 mb-4">
        <div className="flex-1">
          <FormInput
            label="Neuer Standort"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="z. B. Hauptstelle"
            maxLength={255}  /* #461 K-9: Server-Grenze aus #450 */
          />
        </div>
        <Button type="submit" variant="primary" icon={Plus} loading={submitting} disabled={!newName.trim()}>
          Hinzufügen
        </Button>
      </form>

      {locations.length === 0 ? (
        <EmptyState icon={MapPin} title="Keine Standorte" description="Optional — Arbeitsplätze können auch ohne Standort angelegt werden." />
      ) : (
        <ul className="divide-y divide-gray-100">
          {locations.map((loc) => (
            <li key={loc.id} className="flex items-center justify-between py-2 gap-2">
              {editId === loc.id ? (
                <>
                  <input
                    className="flex-1 rounded-lg border border-gray-300 px-2 py-1 text-sm"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    autoFocus
                    maxLength={255}
                  />
                  <button onClick={() => saveEdit(loc)} aria-label="Speichern" className="text-green-600 p-1">
                    <Check size={18} />
                  </button>
                  <button onClick={() => setEditId(null)} aria-label="Abbrechen" className="text-gray-400 p-1">
                    <X size={18} />
                  </button>
                </>
              ) : (
                <>
                  <span className="flex items-center gap-2 text-sm text-gray-800">
                    <MapPin size={14} className="text-gray-400" />
                    {loc.name}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => {
                        setEditId(loc.id);
                        setEditName(loc.name);
                      }}
                      aria-label="Bearbeiten"
                      className="text-gray-400 hover:text-primary p-1"
                    >
                      <Pencil size={16} />
                    </button>
                    <button onClick={() => remove(loc)} aria-label="Löschen" className="text-gray-400 hover:text-danger p-1">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
