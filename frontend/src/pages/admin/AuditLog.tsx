import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import apiClient from '../../api/client';
import { ScrollText, ArrowRight } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import MonthSelector from '../../components/MonthSelector';

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
  create: 'Erstellt',
  update: 'Geändert',
  delete: 'Gelöscht',
};

const actionColors: Record<string, string> = {
  create: 'bg-green-100 text-green-800',
  update: 'bg-blue-100 text-blue-800',
  delete: 'bg-red-100 text-red-800',
};

const sourceLabels: Record<string, string> = {
  manual: 'Admin',
  change_request: 'Antrag',
};

export default function AuditLog() {
  const toast = useToast();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
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

  const fetchAuditLog = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('month', currentMonth);
      if (filterUserId) params.set('user_id', filterUserId);
      const response = await apiClient.get(`/admin/audit-log?${params.toString()}`);
      setEntries(response.data);
    } catch (error) {
      toast.error('Fehler beim Laden des Audit-Logs');
    } finally {
      setLoading(false);
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
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
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
                  <td colSpan={7} className="px-4 py-4 text-center text-gray-500">Lade Protokoll...</td>
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
                      <span className={`px-2 py-1 rounded text-xs font-medium ${actionColors[entry.action] || ''}`}>
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
            <div className="p-6 text-center text-gray-500">Lade Protokoll...</div>
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
                    <span className={`px-2 py-1 rounded text-xs font-medium ${actionColors[entry.action] || ''}`}>
                      {actionLabels[entry.action] || entry.action}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500">
                    {format(new Date(entry.created_at), 'dd.MM.yyyy HH:mm')} | von {entry.changed_by_first_name} {entry.changed_by_last_name} | {sourceLabels[entry.source]}
                  </div>
                  <div className="flex items-center space-x-2 text-xs">
                    {entry.old_date && (
                      <span className="bg-gray-100 px-2 py-1 rounded">
                        {entry.old_date} {entry.old_start_time?.substring(0, 5)}-{entry.old_end_time?.substring(0, 5)}
                      </span>
                    )}
                    {entry.old_date && entry.new_date && <ArrowRight size={12} className="text-gray-400" />}
                    {entry.new_date && (
                      <span className="bg-amber-100 px-2 py-1 rounded">
                        {entry.new_date} {entry.new_start_time?.substring(0, 5)}-{entry.new_end_time?.substring(0, 5)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
