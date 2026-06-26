import { useEffect, useState, useCallback } from 'react';
import { GraduationCap, AlertTriangle, RefreshCw } from 'lucide-react';
import EmptyState from '../EmptyState';
import LoadingSpinner from '../LoadingSpinner';
import Button from '../Button';
import { useToast } from '../../contexts/ToastContext';
import { getErrorMessage } from '../../utils/errorMessage';
import * as api from '../../api/shiftPlanning';
import type { QualUser, Workstation } from '../../api/shiftPlanning';

/**
 * Einweisungs-/Skill-Matrix (#305 M2d): which workstations each employee is
 * trained for. Rows = employees, columns = workstations, checkbox per cell.
 * Toggling a cell saves that employee's whole row (idempotent set).
 */
export default function QualificationMatrix() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [users, setUsers] = useState<QualUser[]>([]);
  const [workstations, setWorkstations] = useState<Workstation[]>([]);
  // user_id -> Set of qualified workstation_ids
  const [quals, setQuals] = useState<Record<string, Set<string>>>({});
  // user_ids whose row save is currently in flight (cells locked, row dimmed)
  const [savingUsers, setSavingUsers] = useState<Set<string>>(new Set());

  // useCallback with no deps (don't depend on the toast reference — an unstable
  // one would re-run the mount effect in a loop). Captures the first `toast`,
  // which is stable in the real app.
  const load = useCallback(async () => {
    setLoadError(false);
    try {
      const m = await api.getQualifications();
      setUsers(m.users);
      setWorkstations(m.workstations);
      const map: Record<string, Set<string>> = {};
      m.users.forEach((u) => (map[u.id] = new Set()));
      m.qualifications.forEach((q) => {
        (map[q.user_id] ??= new Set()).add(q.workstation_id);
      });
      setQuals(map);
    } catch (err) {
      setLoadError(true);
      toast.error(getErrorMessage(err, 'Fehler beim Laden der Einweisungen'));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (userId: string, wsId: string) => {
    if (savingUsers.has(userId)) return; // serialize per-row saves (avoid racing PUTs)
    const current = quals[userId] ?? new Set<string>();
    const next = new Set(current);
    if (next.has(wsId)) next.delete(wsId);
    else next.add(wsId);
    setQuals((prev) => ({ ...prev, [userId]: next }));
    setSavingUsers((prev) => new Set(prev).add(userId));
    try {
      await api.setUserQualifications(userId, [...next]);
    } catch (err) {
      setQuals((prev) => ({ ...prev, [userId]: current })); // revert
      toast.error(getErrorMessage(err, 'Fehler beim Speichern der Einweisung'));
    } finally {
      setSavingUsers((prev) => {
        const n = new Set(prev);
        n.delete(userId);
        return n;
      });
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 text-center">
        <AlertTriangle className="mx-auto mb-3 text-amber-500" size={28} />
        <p className="text-gray-700 font-medium">Die Einweisungen konnten nicht geladen werden.</p>
        <p className="text-sm text-gray-500 mb-4">Bitte versuchen Sie es erneut.</p>
        <Button variant="secondary" icon={RefreshCw} onClick={() => load()}>
          Erneut laden
        </Button>
      </div>
    );
  }

  if (workstations.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
        <EmptyState
          icon={GraduationCap}
          title="Keine Arbeitsplätze"
          description="Legen Sie zuerst im Reiter Stammdaten Arbeitsplätze an, um Einweisungen zu erfassen."
        />
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <GraduationCap size={18} className="text-primary" />
        <h3 className="text-lg font-semibold">Einweisungen</h3>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Häkchen setzen, für welche Arbeitsplätze ein:e Mitarbeiter:in eingewiesen ist. Beim Zuweisen im Editor wird
        eine fehlende Einweisung als Warnung angezeigt (blockiert nicht).
      </p>
      {users.length === 0 ? (
        <EmptyState icon={GraduationCap} title="Keine Mitarbeiter" description="Es sind keine aktiven Mitarbeitenden vorhanden." />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 bg-white text-left px-3 py-2 font-medium text-gray-600 border-b border-gray-200">
                  Mitarbeiter:in
                </th>
                {workstations.map((ws) => (
                  <th key={ws.id} className="px-3 py-2 text-center font-medium text-gray-600 border-b border-gray-200 whitespace-nowrap">
                    <span className="inline-flex items-center gap-1">
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: ws.color || '#9ca3af' }} />
                      {ws.name}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {users.map((u) => {
                const saving = savingUsers.has(u.id);
                return (
                  <tr key={u.id} className={saving ? 'opacity-60' : ''}>
                    <td className="sticky left-0 bg-white px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100">
                      {u.first_name} {u.last_name}
                    </td>
                    {workstations.map((ws) => {
                      const checked = quals[u.id]?.has(ws.id) ?? false;
                      return (
                        <td key={ws.id} className="px-3 py-2 text-center">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={saving}
                            onChange={() => toggle(u.id, ws.id)}
                            aria-label={`${u.first_name} ${u.last_name} – ${ws.name}`}
                            className="h-4 w-4 rounded border-gray-300 cursor-pointer disabled:cursor-wait"
                          />
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
