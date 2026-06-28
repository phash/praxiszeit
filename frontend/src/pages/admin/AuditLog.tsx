import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import apiClient from '../../api/client';
import { ScrollText, ArrowRight } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import MonthSelector from '../../components/MonthSelector';
import LoadingSpinner from '../../components/LoadingSpinner';

interface AuditEntry {
  id: string;
  time_entry_id?: string;
  user_id: string;
  user_first_name?: string;
  user_last_name?: string;
  changed_by: string;
  changed_by_first_name?: string;
  changed_by_last_name?: string;
  action: string;
  old_date?: string;
  old_start_time?: string;
  old_end_time?: string;
  old_break_minutes?: number;
  old_note?: string;
  new_date?: string;
  new_start_time?: string;
  new_end_time?: string;
  new_break_minutes?: number;
  new_note?: string;
  source: string;
  created_at: string;
}

interface UserOption {
  id: string;
  first_name: string;
  last_name: string;
}

const actionLabels: Record<string, string> = {
  // Änderungen an Zeiteinträgen/Abwesenheiten
  create: 'Erstellt',
  update: 'Geändert',
  delete: 'Gelöscht',
  import: 'Importiert',
  profile_update: 'Profil geändert',
  // Zugriffs-/Systemereignisse (keine Änderung — #284: NICHT als „Gelöscht" rendern)
  absence_list_read: 'Abwesenheiten gelesen',
  health_data_read: 'Gesundheitsdaten gelesen',
  health_export: 'Gesundheitsdaten exportiert',
  self_data_export: 'Eigene Daten exportiert',
  arbzg_superadmin_export: 'Notfall-Export (§16)',
  dsgvo_anonymize: 'Anonymisiert (Art. 17)',
  dsgvo_purge: 'Endgültig gelöscht (Art. 17)',
  license_readonly_mode_entered: 'Lizenz: Read-Only aktiviert',
};

const actionColors: Record<string, string> = {
  create: 'bg-green-100 text-green-800',
  update: 'bg-blue-100 text-blue-800',
  delete: 'bg-red-100 text-red-800',
  import: 'bg-blue-100 text-blue-800',
  profile_update: 'bg-blue-100 text-blue-800',
  // destruktive DSGVO-Aktionen rot, Zugriffe/Exporte/Systemereignisse neutral
  dsgvo_anonymize: 'bg-red-100 text-red-800',
  dsgvo_purge: 'bg-red-100 text-red-800',
  absence_list_read: 'bg-gray-100 text-gray-700',
  health_data_read: 'bg-amber-100 text-amber-800',
  health_export: 'bg-amber-100 text-amber-800',
  self_data_export: 'bg-gray-100 text-gray-700',
  arbzg_superadmin_export: 'bg-amber-100 text-amber-800',
  license_readonly_mode_entered: 'bg-amber-100 text-amber-800',
};

const sourceLabels: Record<string, string> = {
  manual: 'Admin',
  change_request: 'Antrag',
  import: 'Import',
  dsgvo: 'DSGVO',
  break_waiver: 'Pausen-Verzicht',
  vacation_request_cancel: 'Urlaub storniert',
  license_startup: 'Lizenz',
};

export default function AuditLog() {
  const toast = useToast();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false); // ADM-12: weitere Seiten vorhanden
  const [loadingMore, setLoadingMore] = useState(false);
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [filterUserId, setFilterUserId] = useState('');
  const [users, setUsers] = useState<UserOption[]>([]);

  useEffect(() => {
    fetchUsers();
  }, []);

  useEffect(() => {
    fetchAuditLog();
  }, [currentMonth, filterUserId]);

  const fetchUsers = async () => {
    try {
      const response = await apiClient.get('/admin/users');
      setUsers(response.data);
    } catch (error) {
      toast.error('Fehler beim Laden der Benutzerliste');
    }
  };

  // ADM-12: Keyset-Pagination — das Backend liefert max. AUDIT_PAGE_SIZE Zeilen
  // (created_at DESC). Ohne "Mehr laden" wurden in Monaten mit >100 Änderungen die
  // ältesten Einträge stillschweigend abgeschnitten.
  const AUDIT_PAGE_SIZE = 100;
  const fetchAuditLog = async (append = false) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('month', currentMonth);
      if (filterUserId) params.set('user_id', filterUserId);
      params.set('limit', String(AUDIT_PAGE_SIZE));
      if (append && entries.length > 0) {
        params.set('before', entries[entries.length - 1].created_at); // Cursor = älteste Zeile
      }
      const response = await apiClient.get(`/admin/audit-log?${params.toString()}`);
      const data: AuditEntry[] = response.data;
      setEntries(append ? [...entries, ...data] : data);
      setHasMore(data.length === AUDIT_PAGE_SIZE);
    } catch (error) {
      toast.error('Fehler beim Laden des Audit-Logs');
    } finally {
      if (append) setLoadingMore(false);
      else setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center space-x-3 mb-8">
        <ScrollText size={28} className="text-primary" />
        <h1 className="text-3xl font-bold text-gray-900">Änderungsprotokoll</h1>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-6">
        <MonthSelector value={currentMonth} onChange={setCurrentMonth} />
        <select
          value={filterUserId}
          onChange={(e) => setFilterUserId(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary text-sm"
        >
          <option value="">Alle Mitarbeitende</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.last_name}, {u.first_name}
            </option>
          ))}
        </select>
      </div>

      {/* Audit Log */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 overflow-hidden">
        {/* Desktop Table */}
        <div className="hidden lg:block overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Zeitpunkt</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Mitarbeiter</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Geändert von</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aktion</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Quelle</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Alte Werte</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Neue Werte</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center">
                    <LoadingSpinner text="Lade Protokoll..." />
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-4 text-center text-gray-500">Keine Einträge vorhanden</td>
                </tr>
              ) : (
                entries.map((entry) => (
                  <tr key={entry.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {format(new Date(entry.created_at), 'dd.MM.yyyy HH:mm')}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {entry.user_last_name}, {entry.user_first_name}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {entry.changed_by_last_name}, {entry.changed_by_first_name}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span className={`px-2 py-1 rounded-sm text-xs font-medium ${actionColors[entry.action] || ''}`}>
                        {actionLabels[entry.action] || entry.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {sourceLabels[entry.source] || entry.source}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {entry.old_date ? (
                        <div>
                          <p>{entry.old_date}</p>
                          <p>{entry.old_start_time?.substring(0, 5)} - {entry.old_end_time?.substring(0, 5)}</p>
                          <p>Pause: {entry.old_break_minutes} min</p>
                        </div>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {entry.new_date ? (
                        <div>
                          <p>{entry.new_date}</p>
                          <p>{entry.new_start_time?.substring(0, 5)} - {entry.new_end_time?.substring(0, 5)}</p>
                          <p>Pause: {entry.new_break_minutes} min</p>
                        </div>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Cards */}
        <div className="lg:hidden">
          {loading ? (
            <div className="p-6 flex justify-center">
              <LoadingSpinner text="Lade Protokoll..." />
            </div>
          ) : entries.length === 0 ? (
            <div className="p-6 text-center text-gray-500">Keine Einträge vorhanden</div>
          ) : (
            <div className="divide-y divide-gray-200">
              {entries.map((entry) => (
                <div key={entry.id} className="p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-900">
                      {entry.user_last_name}, {entry.user_first_name}
                    </span>
                    <span className={`px-2 py-1 rounded-sm text-xs font-medium ${actionColors[entry.action] || ''}`}>
                      {actionLabels[entry.action] || entry.action}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500">
                    {format(new Date(entry.created_at), 'dd.MM.yyyy HH:mm')} | von {entry.changed_by_first_name} {entry.changed_by_last_name} | {sourceLabels[entry.source] || entry.source}
                  </div>
                  <div className="flex items-center space-x-2 text-xs">
                    {entry.old_date && (
                      <span className="bg-gray-100 px-2 py-1 rounded-sm">
                        {entry.old_date} {entry.old_start_time?.substring(0, 5)}-{entry.old_end_time?.substring(0, 5)}
                      </span>
                    )}
                    {entry.old_date && entry.new_date && <ArrowRight size={12} className="text-gray-400" />}
                    {entry.new_date && (
                      <span className="bg-amber-100 px-2 py-1 rounded-sm">
                        {entry.new_date} {entry.new_start_time?.substring(0, 5)}-{entry.new_end_time?.substring(0, 5)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ADM-12: weitere (ältere) Einträge nachladen */}
        {hasMore && !loading && (
          <div className="p-4 text-center border-t border-gray-200">
            <button
              onClick={() => fetchAuditLog(true)}
              disabled={loadingMore}
              className="px-4 py-2 text-sm font-medium text-primary hover:bg-primary/5 rounded-lg disabled:opacity-50"
            >
              {loadingMore ? 'Lädt…' : 'Ältere Einträge laden'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
