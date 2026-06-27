import { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import { getErrorMessage } from '../utils/errorMessage';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from './ConfirmDialog';
import * as api from '../api/absenceReasons';
import type { AbsenceReason, AbsenceReasonBehavior } from '../api/absenceReasons';

const BEHAVIORS: AbsenceReasonBehavior[] = ['worked', 'paid_free', 'overtime_comp'];

/**
 * #312: Verwaltung eigener Abwesenheitsgründe (Einstellungen). Anlegen
 * (Freitext + Basis-Verhalten + Farbe), Umbenennen/Umfärben, (De-)Aktivieren,
 * Löschen (nur wenn unbenutzt). Das Basis-Verhalten ist nach dem Anlegen fix.
 */
export default function AbsenceReasonsManager() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [reasons, setReasons] = useState<AbsenceReason[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // new reason form
  const [name, setName] = useState('');
  const [behavior, setBehavior] = useState<AbsenceReasonBehavior>('worked');
  const [color, setColor] = useState('#3366cc');

  const load = useCallback(async () => {
    try {
      setReasons(await api.listReasons(true));
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Laden der Abwesenheitsgründe'));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      await api.createReason({ name: name.trim(), base_behavior: behavior, color });
      setName('');
      toast.success('Abwesenheitsgrund angelegt');
      await load();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Anlegen'));
    } finally {
      setBusy(false);
    }
  };

  const saveRow = async (r: AbsenceReason, patch: Partial<AbsenceReason>) => {
    try {
      await api.updateReason(r.id, patch);
      await load();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    }
  };

  const remove = (r: AbsenceReason) => {
    confirm({
      title: 'Grund löschen?',
      message: `„${r.name}" wird gelöscht. Geht nur, wenn keine Abwesenheit ihn nutzt — sonst bitte deaktivieren.`,
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await api.deleteReason(r.id);
          toast.success('Grund gelöscht');
          await load();
        } catch (err) {
          toast.error(getErrorMessage(err, 'Konnte nicht gelöscht werden (evtl. in Benutzung — deaktivieren)'));
        }
      },
    });
  };

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-2">Eigene Abwesenheitsgründe</h2>
      <p className="text-sm text-gray-500 mb-4">
        Legen Sie eigene Gründe an (z. B. „Schule" für Azubis). Das <strong>Basis-Verhalten</strong> bestimmt die
        Berechnung und ist nach dem Anlegen fix. Gründe lassen sich umbenennen, umfärben und deaktivieren.
      </p>

      <form onSubmit={add} className="flex flex-wrap items-end gap-2 mb-4">
        <div className="flex-1 min-w-[160px]">
          <label className="block text-xs font-medium text-gray-600 mb-1">Bezeichnung</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
            placeholder="z. B. Schule"
            className="w-full rounded border-gray-300 text-sm"
          />
        </div>
        <div className="min-w-[180px]">
          <label className="block text-xs font-medium text-gray-600 mb-1">Verhalten</label>
          <select
            value={behavior}
            onChange={(e) => setBehavior(e.target.value as AbsenceReasonBehavior)}
            className="w-full rounded border-gray-300 text-sm"
          >
            {BEHAVIORS.map((b) => (
              <option key={b} value={b}>{api.BEHAVIOR_LABELS[b]}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Farbe</label>
          <input type="color" value={color} onChange={(e) => setColor(e.target.value)}
                 className="h-9 w-12 rounded border-gray-300" />
        </div>
        <button type="submit" disabled={busy || !name.trim()}
                className="flex items-center gap-1 px-3 py-2 bg-primary text-white rounded-lg text-sm disabled:opacity-50">
          <Plus size={16} /> Hinzufügen
        </button>
      </form>
      <p className="text-xs text-gray-400 mb-4">{api.BEHAVIOR_HINTS[behavior]}</p>

      {loading ? (
        <p className="text-sm text-gray-500">Lädt…</p>
      ) : reasons.length === 0 ? (
        <p className="text-sm text-gray-500">Noch keine eigenen Gründe angelegt.</p>
      ) : (
        <ul className="divide-y divide-gray-100">
          {reasons.map((r) => (
            <li key={r.id} className="flex items-center gap-3 py-2">
              <input
                type="color"
                value={r.color || '#888888'}
                onChange={(e) => saveRow(r, { color: e.target.value })}
                className="h-7 w-9 rounded border-gray-300 shrink-0"
                title="Farbe ändern"
              />
              <input
                defaultValue={r.name}
                onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== r.name) saveRow(r, { name: v }); }}
                className={`flex-1 rounded border-gray-200 text-sm ${r.is_active ? '' : 'text-gray-400 line-through'}`}
              />
              <span className="text-xs text-gray-500 shrink-0 w-36">{api.BEHAVIOR_LABELS[r.base_behavior]}</span>
              <label className="flex items-center gap-1 text-xs text-gray-600 shrink-0" title="Aktiv">
                <input type="checkbox" checked={r.is_active}
                       onChange={(e) => saveRow(r, { is_active: e.target.checked })} />
                aktiv
              </label>
              <button onClick={() => remove(r)} className="text-gray-400 hover:text-red-600 shrink-0"
                      aria-label="Löschen">
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  );
}
