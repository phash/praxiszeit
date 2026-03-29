import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/client';
import { Plus, Edit2, Key, UserX, UserCheck, X, Clock, Trash2, ArrowUp, ArrowDown, Search, Eye, EyeOff, UserMinus, BookOpen, ArrowLeftRight } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';
import LoadingSpinner from '../../components/LoadingSpinner';
import Badge from '../../components/Badge';
import { getErrorMessage } from '../../utils/errorMessage';
import SetPasswordModal from './users/SetPasswordModal';
import CarryoverModal from './users/CarryoverModal';
import WorkingHoursModal from './users/WorkingHoursModal';
import UserForm from './users/UserForm';

interface User {
  id: string;
  username: string;
  email: string | null;
  first_name: string;
  last_name: string;
  role: 'admin' | 'employee';
  weekly_hours: number;
  vacation_days: number;
  work_days_per_week: number;
  suggested_vacation_days?: number;
  track_hours: boolean;
  exempt_from_arbzg: boolean;
  is_night_worker: boolean;
  use_daily_schedule: boolean;
  hours_monday: number | null;
  hours_tuesday: number | null;
  hours_wednesday: number | null;
  hours_thursday: number | null;
  hours_friday: number | null;
  first_work_day: string | null;
  last_work_day: string | null;
  is_active: boolean;
  is_hidden: boolean;
  deactivated_at: string | null;
  created_at: string;
}

interface VacationInfo {
  budget_days: number;
  used_days: number;
  remaining_days: number;
}

/** Verbleibende Grace-Period-Tage (0 = abgelaufen / kein deactivated_at). */
function graceRemainingDays(user: User): number {
  if (!user.deactivated_at) return 0;
  const deactivated = new Date(user.deactivated_at);
  const graceEnd = new Date(deactivated.getTime() + 14 * 24 * 60 * 60 * 1000);
  const remaining = Math.ceil((graceEnd.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
  return Math.max(0, remaining);
}

export default function Users() {
  const navigate = useNavigate();
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [vacationInfo, setVacationInfo] = useState<Record<string, VacationInfo>>({});
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  const [setPasswordModal, setSetPasswordModal] = useState<{ userId: string; userName: string } | null>(null);
  const [carryoverUser, setCarryoverUser] = useState<User | null>(null);
  const [hoursModalUser, setHoursModalUser] = useState<User | null>(null);

  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  // Sorting & Filtering
  const [sortField, setSortField] = useState<keyof User | ''>('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [filterText, setFilterText] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [showHidden, setShowHidden] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, [showInactive, showHidden]);

  const fetchUsers = async () => {
    try {
      const params: Record<string, boolean> = {};
      if (showInactive) params.include_inactive = true;
      if (showHidden) params.include_hidden = true;
      const response = await apiClient.get('/admin/users', { params });
      setUsers(response.data);

      // Fetch vacation info for each user
      const currentYear = new Date().getFullYear();
      const vacationPromises = response.data.map((user: User) =>
        apiClient.get(`/dashboard/vacation`, {
          params: { user_id: user.id, year: currentYear }
        }).then(res => ({ userId: user.id, data: res.data }))
        .catch(() => ({ userId: user.id, data: null }))
      );

      const vacationResults = await Promise.all(vacationPromises);
      const vacationMap: Record<string, VacationInfo> = {};
      vacationResults.forEach(result => {
        if (result.data) {
          vacationMap[result.userId] = result.data;
        }
      });
      setVacationInfo(vacationMap);
    } catch (error) {
      toast.error('Fehler beim Laden der Benutzer');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (user: User) => {
    setEditingUser(user);
    setShowForm(true);
  };

  const handleFormSaved = () => {
    fetchUsers();
    setShowForm(false);
    setEditingUser(null);
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingUser(null);
  };

  const handleSetPassword = (userId: string, name: string) => {
    setSetPasswordModal({ userId, userName: name });
  };

  const handleDeactivate = (userId: string, name: string) => {
    confirm({
      title: 'Benutzer deaktivieren',
      message: `${name} wirklich deaktivieren? Der Benutzer kann sich danach nicht mehr anmelden.`,
      confirmLabel: 'Deaktivieren',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/admin/users/${userId}`);
          toast.success(`${name} deaktiviert`);
          fetchUsers();
        } catch (error: any) {
          toast.error(getErrorMessage(error, 'Fehler beim Deaktivieren'));
        }
      },
    });
  };

  const handleReactivate = (userId: string, name: string) => {
    confirm({
      title: 'Benutzer reaktivieren',
      message: `${name} wieder aktivieren? Der Benutzer kann sich danach erneut anmelden.`,
      confirmLabel: 'Reaktivieren',
      variant: 'warning',
      onConfirm: async () => {
        try {
          await apiClient.post(`/admin/users/${userId}/reactivate`);
          toast.success(`${name} reaktiviert`);
          fetchUsers();
        } catch (error: any) {
          toast.error(getErrorMessage(error, 'Fehler beim Reaktivieren'));
        }
      },
    });
  };

  const handleToggleHidden = (userId: string, name: string, currentlyHidden: boolean) => {
    confirm({
      title: currentlyHidden ? 'Benutzer sichtbar schalten' : 'Benutzer ausblenden',
      message: currentlyHidden
        ? `${name} wieder in Berichten und Übersichten anzeigen?`
        : `${name} aus Berichten und Übersichten ausblenden? Der Benutzer kann sich weiterhin anmelden.`,
      confirmLabel: currentlyHidden ? 'Sichtbar schalten' : 'Ausblenden',
      variant: currentlyHidden ? 'warning' : 'danger',
      onConfirm: async () => {
        try {
          await apiClient.post(`/admin/users/${userId}/toggle-hidden`);
          toast.success(currentlyHidden ? `${name} ist jetzt sichtbar` : `${name} ausgeblendet`);
          fetchUsers();
        } catch (error: any) {
          toast.error(getErrorMessage(error, 'Fehler beim Ändern der Sichtbarkeit'));
        }
      },
    });
  };

  const handleAnonymize = (userId: string, name: string) => {
    confirm({
      title: 'Benutzer anonymisieren (DSGVO Art. 17)',
      message: `Soll ${name} gemäß DSGVO Art. 17 anonymisiert werden?\n\nDabei werden:\n• Name, Benutzername und E-Mail-Adresse unwiderruflich gelöscht\n• Abwesenheiten (Urlaub, Krankheit) gelöscht\n• Zeiteinträge bleiben für ArbZG §16 (2 Jahre) erhalten\n\nDieser Vorgang kann nicht rückgängig gemacht werden.`,
      confirmLabel: 'Jetzt anonymisieren',
      variant: 'warning',
      onConfirm: async () => {
        try {
          await apiClient.post(`/admin/users/${userId}/anonymize`);
          toast.success(`${name} wurde anonymisiert (Art. 17 DSGVO)`);
          fetchUsers();
        } catch (error: any) {
          toast.error(getErrorMessage(error, 'Fehler bei der Anonymisierung'));
        }
      },
    });
  };

  const handlePurge = (userId: string, name: string) => {
    confirm({
      title: 'Benutzer endgültig löschen (DSGVO Art. 17)',
      message: `Soll ${name} endgültig und unwiderruflich gelöscht werden?\n\nAlle verbleibenden Daten (Zeiteinträge, Abwesenheiten, Benutzerkonto) werden dauerhaft entfernt.\n\nDieser Vorgang kann NICHT rückgängig gemacht werden.`,
      confirmLabel: 'Endgültig löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/admin/users/${userId}/purge`);
          toast.success(`${name} wurde endgültig gelöscht (Art. 17 DSGVO)`);
          fetchUsers();
        } catch (error: any) {
          toast.error(getErrorMessage(error, 'Fehler beim Löschen'));
        }
      },
    });
  };

  // Sorting function
  const handleSort = (field: keyof User) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  // Filter and sort users
  const filteredAndSortedUsers = users
    .filter(user => {
      if (!filterText) return true;
      const searchLower = filterText.toLowerCase();
      return (
        user.first_name.toLowerCase().includes(searchLower) ||
        user.last_name.toLowerCase().includes(searchLower) ||
        user.username.toLowerCase().includes(searchLower) ||
        (user.email || '').toLowerCase().includes(searchLower)
      );
    })
    .sort((a, b) => {
      if (!sortField) return 0;

      const aValue = a[sortField];
      const bValue = b[sortField];

      if (aValue === undefined || bValue === undefined) return 0;

      let comparison = 0;
      if (typeof aValue === 'string' && typeof bValue === 'string') {
        comparison = aValue.localeCompare(bValue);
      } else if (typeof aValue === 'number' && typeof bValue === 'number') {
        comparison = aValue - bValue;
      } else if (typeof aValue === 'boolean' && typeof bValue === 'boolean') {
        comparison = (aValue === bValue) ? 0 : aValue ? 1 : -1;
      }

      return sortDirection === 'asc' ? comparison : -comparison;
    });

  return (
    <div>
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Benutzerverwaltung</h1>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
            />
            Inaktive anzeigen
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showHidden}
              onChange={(e) => setShowHidden(e.target.checked)}
              className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
            />
            Ausgeblendete anzeigen
          </label>
          <button
            onClick={() => {
              if (showForm) {
                handleFormCancel();
              } else {
                setEditingUser(null);
                setShowForm(true);
              }
            }}
            className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
          >
            {showForm ? <X size={20} /> : <Plus size={20} />}
            <span>{showForm ? 'Abbrechen' : 'Neue:r Mitarbeiter:in'}</span>
          </button>
        </div>
      </div>

      {/* User Form */}
      {showForm && (
        <UserForm
          editUser={editingUser}
          onSaved={handleFormSaved}
        />
      )}

      {/* Filter Input */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
          <input
            type="text"
            placeholder="Suche nach Name oder Benutzername..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>
      </div>

      {/* Users Table/Cards */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {/* Desktop Table */}
        <div className="hidden lg:block overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('last_name')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Name</span>
                    {sortField === 'last_name' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('username')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Benutzername</span>
                    {sortField === 'username' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('role')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Rolle</span>
                    {sortField === 'role' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('weekly_hours')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Wochenstd.</span>
                    {sortField === 'weekly_hours' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Arbeitstage</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Urlaubskonto</th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('track_hours')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Stundenzählung</span>
                    {sortField === 'track_hours' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('is_active')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Status</span>
                    {sortField === 'is_active' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-6 py-4 text-center text-gray-500">
                    Lade Benutzer...
                  </td>
                </tr>
              ) : filteredAndSortedUsers.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-6 py-4 text-center text-gray-500">
                    {filterText ? 'Keine Benutzer gefunden' : 'Keine Benutzer vorhanden'}
                  </td>
                </tr>
              ) : (
                filteredAndSortedUsers.map((user) => (
                  <tr key={user.id} className={`hover:bg-gray-50 ${!user.is_active ? 'opacity-50' : ''} ${user.is_hidden ? 'bg-gray-50/70' : ''}`}>
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-gray-900">{user.last_name}, {user.first_name}</div>
                      {(user.first_work_day || user.last_work_day) && (
                        <div className="text-xs text-gray-400 mt-0.5">
                          {user.first_work_day && <span>ab {new Date(user.first_work_day + 'T00:00:00').toLocaleDateString('de-DE')}</span>}
                          {user.first_work_day && user.last_work_day && <span> — </span>}
                          {user.last_work_day && <span>bis {new Date(user.last_work_day + 'T00:00:00').toLocaleDateString('de-DE')}</span>}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{user.username}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {user.role === 'admin' ? 'Admin' : 'Mitarbeiter:in'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{user.weekly_hours}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{user.work_days_per_week} Tage/Wo</td>
                    <td className="px-6 py-4 text-sm">
                      {vacationInfo[user.id] ? (
                        <div className="space-y-1">
                          <div className="flex items-center space-x-2">
                            <span className="text-gray-600">Budget:</span>
                            <span className="font-medium text-gray-900">
                              {vacationInfo[user.id].budget_days} Tage
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            <span className="text-gray-600">Genommen:</span>
                            <span className="font-medium text-orange-600">
                              {vacationInfo[user.id].used_days.toFixed(1)} Tage
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            <span className="text-gray-600">Übrig:</span>
                            <span className={`font-semibold ${
                              vacationInfo[user.id].remaining_days > 5
                                ? 'text-green-600'
                                : vacationInfo[user.id].remaining_days > 0
                                ? 'text-yellow-600'
                                : 'text-red-600'
                            }`}>
                              {vacationInfo[user.id].remaining_days.toFixed(1)} Tage
                            </span>
                          </div>
                          {/* Progress bar */}
                          <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                            <div
                              className={`h-2 rounded-full ${
                                vacationInfo[user.id].remaining_days > 5
                                  ? 'bg-green-500'
                                  : vacationInfo[user.id].remaining_days > 0
                                  ? 'bg-yellow-500'
                                  : 'bg-red-500'
                              }`}
                              style={{
                                width: `${Math.max(0, (vacationInfo[user.id].remaining_days / vacationInfo[user.id].budget_days) * 100)}%`
                              }}
                            ></div>
                          </div>
                        </div>
                      ) : (
                        <span className="text-gray-400">Lädt...</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {user.track_hours ? (
                        <span className="text-green-600">✓ Aktiv</span>
                      ) : (
                        <span className="text-gray-500">✗ Deaktiviert</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <div className="flex flex-col gap-1">
                        {user.is_active ? (
                          <span className="text-green-600">Aktiv</span>
                        ) : (
                          <span className="text-red-600">Inaktiv</span>
                        )}
                        {user.is_hidden && (
                          <span className="text-gray-400 text-xs flex items-center gap-1">
                            <EyeOff size={11} /> Ausgeblendet
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right text-sm space-x-3">
                      {/* Journal button */}
                      <button
                        onClick={() => navigate(`/admin/users/${user.id}/journal`)}
                        className="text-blue-600 hover:text-blue-800"
                        title="Monatsjournal anzeigen"
                      >
                        <BookOpen size={16} />
                      </button>
                      <button
                        onClick={() => handleEdit(user)}
                        className="text-primary hover:text-primary-dark"
                        title="Bearbeiten"
                      >
                        <Edit2 size={16} />
                      </button>
                      <button
                        onClick={() => setHoursModalUser(user)}
                        className="text-blue-600 hover:text-blue-800"
                        title="Stundenverlauf"
                      >
                        <Clock size={16} />
                      </button>
                      <button
                        onClick={() => setCarryoverUser(user)}
                        className="text-teal-600 hover:text-teal-800"
                        title="Vorjahresübernahme"
                      >
                        <ArrowLeftRight size={16} />
                      </button>
                      <button
                        onClick={() => handleSetPassword(user.id, `${user.first_name} ${user.last_name}`)}
                        className="text-orange-600 hover:text-orange-800"
                        title="Passwort setzen"
                      >
                        <Key size={16} />
                      </button>
                      {user.is_active ? (
                        <button
                          onClick={() => handleDeactivate(user.id, `${user.first_name} ${user.last_name}`)}
                          className="text-red-600 hover:text-red-800"
                          title="Deaktivieren"
                        >
                          <UserX size={16} />
                        </button>
                      ) : (
                        <button
                          onClick={() => handleReactivate(user.id, `${user.first_name} ${user.last_name}`)}
                          className="text-green-600 hover:text-green-800"
                          title="Reaktivieren"
                        >
                          <UserCheck size={16} />
                        </button>
                      )}
                      <button
                        onClick={() => handleToggleHidden(user.id, `${user.first_name} ${user.last_name}`, user.is_hidden)}
                        className={user.is_hidden ? 'text-gray-400 hover:text-gray-600' : 'text-gray-500 hover:text-gray-700'}
                        title={user.is_hidden ? 'Sichtbar schalten' : 'Ausblenden'}
                      >
                        {user.is_hidden ? <Eye size={16} /> : <EyeOff size={16} />}
                      </button>
                      {!user.is_active && !user.username.startsWith('deleted_') && (() => {
                        const remaining = graceRemainingDays(user);
                        return remaining > 0 ? (
                          <span
                            className="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 cursor-default"
                            title={`Sperrfrist: Anonymisierung erst in ${remaining} Tag(en) möglich`}
                          >
                            🔒 {remaining}d
                          </span>
                        ) : (
                          <button
                            onClick={() => handleAnonymize(user.id, `${user.first_name} ${user.last_name}`)}
                            className="text-amber-600 hover:text-amber-800"
                            title="Anonymisieren (DSGVO Art. 17)"
                          >
                            <UserMinus size={16} />
                          </button>
                        );
                      })()}
                      {!user.is_active && user.username.startsWith('deleted_') && (
                        <button
                          onClick={() => handlePurge(user.id, `${user.first_name} ${user.last_name}`)}
                          className="text-red-700 hover:text-red-900"
                          title="Endgültig löschen (DSGVO Art. 17)"
                        >
                          <Trash2 size={16} />
                        </button>
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
            <div className="p-6">
              <LoadingSpinner text="Lade Benutzer..." />
            </div>
          ) : filteredAndSortedUsers.length === 0 ? (
            <div className="p-6 text-center text-gray-500">
              {filterText ? 'Keine Benutzer gefunden' : 'Keine Benutzer vorhanden'}
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {filteredAndSortedUsers.map((user) => (
                <div key={user.id} className={`p-4 ${!user.is_active ? 'opacity-50' : ''} ${user.is_hidden ? 'bg-gray-50/70' : ''}`}>
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                      <p className="font-medium text-gray-900">
                        {user.last_name}, {user.first_name}
                      </p>
                      <p className="text-sm text-gray-600">{user.username}</p>
                      <div className="flex items-center space-x-2 mt-2 flex-wrap gap-1">
                        <Badge variant={user.role === 'admin' ? 'info' : 'default'} size="sm">
                          {user.role === 'admin' ? 'Admin' : 'Mitarbeiter'}
                        </Badge>
                        <Badge variant={user.is_active ? 'success' : 'error'} size="sm">
                          {user.is_active ? 'Aktiv' : 'Inaktiv'}
                        </Badge>
                        {user.is_hidden && (
                          <Badge variant="default" size="sm">
                            <span className="flex items-center gap-1"><EyeOff size={10} /> Ausgeblendet</span>
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-sm mb-3">
                    <div>
                      <span className="text-gray-500 block">Wochenstunden</span>
                      <p className="font-medium">{user.weekly_hours}</p>
                    </div>
                    <div>
                      <span className="text-gray-500 block">Arbeitstage</span>
                      <p className="font-medium">{user.work_days_per_week}/Wo</p>
                    </div>
                    {user.first_work_day && (
                      <div>
                        <span className="text-gray-500 block">Erster Arbeitstag</span>
                        <p className="font-medium">{new Date(user.first_work_day + 'T00:00:00').toLocaleDateString('de-DE')}</p>
                      </div>
                    )}
                    {user.last_work_day && (
                      <div>
                        <span className="text-gray-500 block">Letzter Arbeitstag</span>
                        <p className="font-medium">{new Date(user.last_work_day + 'T00:00:00').toLocaleDateString('de-DE')}</p>
                      </div>
                    )}
                  </div>

                  {vacationInfo[user.id] && (
                    <div className="bg-gray-50 rounded-lg p-3 mb-3 text-sm">
                      <p className="font-medium text-gray-700 mb-2">Urlaubskonto</p>
                      <div className="space-y-1">
                        <div className="flex justify-between">
                          <span className="text-gray-600">Budget:</span>
                          <span className="font-medium">{vacationInfo[user.id].budget_days} Tage</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">Übrig:</span>
                          <span className={`font-semibold ${
                            vacationInfo[user.id].remaining_days > 5
                              ? 'text-green-600'
                              : vacationInfo[user.id].remaining_days > 0
                              ? 'text-yellow-600'
                              : 'text-red-600'
                          }`}>
                            {vacationInfo[user.id].remaining_days.toFixed(1)} Tage
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => navigate(`/admin/users/${user.id}/journal`)}
                      className="p-2 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition"
                      aria-label="Monatsjournal anzeigen"
                      title="Monatsjournal anzeigen"
                    >
                      <BookOpen size={16} />
                    </button>
                    <button
                      onClick={() => handleEdit(user)}
                      className="flex-1 flex items-center justify-center space-x-2 px-3 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition"
                      aria-label={`${user.first_name} ${user.last_name} bearbeiten`}
                    >
                      <Edit2 size={16} />
                      <span>Bearbeiten</span>
                    </button>
                    <button
                      onClick={() => setHoursModalUser(user)}
                      className="p-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition"
                      aria-label="Stundenverlauf anzeigen"
                      title="Stundenverlauf"
                    >
                      <Clock size={16} />
                    </button>
                    <button
                      onClick={() => setCarryoverUser(user)}
                      className="p-2 bg-teal-50 text-teal-600 rounded-lg hover:bg-teal-100 transition"
                      aria-label="Vorjahresübernahme"
                      title="Vorjahresübernahme"
                    >
                      <ArrowLeftRight size={16} />
                    </button>
                    <button
                      onClick={() => handleSetPassword(user.id, `${user.first_name} ${user.last_name}`)}
                      className="p-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition"
                      aria-label="Passwort setzen"
                      title="Passwort setzen"
                    >
                      <Key size={16} />
                    </button>
                    {user.is_active ? (
                      <button
                        onClick={() => handleDeactivate(user.id, `${user.first_name} ${user.last_name}`)}
                        className="p-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition"
                        aria-label="Benutzer deaktivieren"
                        title="Deaktivieren"
                      >
                        <UserX size={16} />
                      </button>
                    ) : (
                      <button
                        onClick={() => handleReactivate(user.id, `${user.first_name} ${user.last_name}`)}
                        className="p-2 bg-green-50 text-green-600 rounded-lg hover:bg-green-100 transition"
                        aria-label="Benutzer reaktivieren"
                        title="Reaktivieren"
                      >
                        <UserCheck size={16} />
                      </button>
                    )}
                    <button
                      onClick={() => handleToggleHidden(user.id, `${user.first_name} ${user.last_name}`, user.is_hidden)}
                      className="p-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition"
                      aria-label={user.is_hidden ? 'Sichtbar schalten' : 'Ausblenden'}
                      title={user.is_hidden ? 'Sichtbar schalten' : 'Ausblenden'}
                    >
                      {user.is_hidden ? <Eye size={16} /> : <EyeOff size={16} />}
                    </button>
                    {!user.is_active && !user.username.startsWith('deleted_') && (() => {
                      const remaining = graceRemainingDays(user);
                      return remaining > 0 ? (
                        <div
                          className="flex items-center gap-1 px-2 py-1.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700 cursor-default"
                          title={`Sperrfrist: Anonymisierung erst in ${remaining} Tag(en) möglich`}
                        >
                          🔒 Sperrfrist: {remaining}d
                        </div>
                      ) : (
                        <button
                          onClick={() => handleAnonymize(user.id, `${user.first_name} ${user.last_name}`)}
                          className="p-2 bg-amber-50 text-amber-600 rounded-lg hover:bg-amber-100 transition"
                          aria-label="Anonymisieren (DSGVO Art. 17)"
                          title="Anonymisieren"
                        >
                          <UserMinus size={16} />
                        </button>
                      );
                    })()}
                    {!user.is_active && user.username.startsWith('deleted_') && (
                      <button
                        onClick={() => handlePurge(user.id, `${user.first_name} ${user.last_name}`)}
                        className="p-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition"
                        aria-label="Endgültig löschen (DSGVO Art. 17)"
                        title="Endgültig löschen"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Working Hours History Modal */}
      {hoursModalUser && (
        <WorkingHoursModal
          userId={hoursModalUser.id}
          userName={`${hoursModalUser.first_name} ${hoursModalUser.last_name}`}
          currentWeeklyHours={hoursModalUser.weekly_hours}
          onClose={() => setHoursModalUser(null)}
          onChanged={fetchUsers}
        />
      )}

      {/* Set Password Modal */}
      {setPasswordModal && (
        <SetPasswordModal
          userId={setPasswordModal.userId}
          userName={setPasswordModal.userName}
          onClose={() => setSetPasswordModal(null)}
        />
      )}

      {/* Carryover Modal */}
      {carryoverUser && (
        <CarryoverModal
          userId={carryoverUser.id}
          userName={`${carryoverUser.first_name} ${carryoverUser.last_name}`}
          onClose={() => setCarryoverUser(null)}
          onSaved={fetchUsers}
        />
      )}
    </div>
  );
}
