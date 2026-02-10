import { useEffect, useState } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../api/client';
import { Plus, Edit2, Key, UserX, Save, X, Clock, Trash2, Copy, ArrowUp, ArrowDown, Search } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';
import LoadingSpinner from '../../components/LoadingSpinner';
import Badge from '../../components/Badge';

interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'admin' | 'employee';
  weekly_hours: number;
  vacation_days: number;
  work_days_per_week: number;
  suggested_vacation_days?: number;
  track_hours: boolean;
  is_active: boolean;
  created_at: string;
}

interface VacationInfo {
  budget_days: number;
  used_days: number;
  remaining_days: number;
}

interface WorkingHoursChange {
  id: string;
  user_id: string;
  effective_from: string;
  weekly_hours: number;
  note?: string;
  created_at: string;
}

export default function Users() {
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [vacationInfo, setVacationInfo] = useState<Record<string, VacationInfo>>({});
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    email: '',
    first_name: '',
    last_name: '',
    role: 'employee' as 'admin' | 'employee',
    weekly_hours: 40,
    vacation_days: 30,
    work_days_per_week: 5,
    track_hours: true,
  });
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [showHoursModal, setShowHoursModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [hoursChanges, setHoursChanges] = useState<WorkingHoursChange[]>([]);
  const [hoursFormData, setHoursFormData] = useState({
    effective_from: '',
    weekly_hours: 40,
    note: '',
  });

  const [suggestedVacation, setSuggestedVacation] = useState<number | null>(null);
  const [resetPasswordData, setResetPasswordData] = useState<{ password: string; userName: string } | null>(null);
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  // Sorting & Filtering
  const [sortField, setSortField] = useState<keyof User | ''>('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [filterText, setFilterText] = useState('');

  useEffect(() => {
    fetchUsers();
  }, []);

  useEffect(() => {
    if (formData.work_days_per_week > 0) {
      const suggested = Math.round(30 * formData.work_days_per_week / 5);
      setSuggestedVacation(suggested);
    }
  }, [formData.work_days_per_week]);

  const fetchUsers = async () => {
    try {
      const response = await apiClient.get('/admin/users');
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
      console.error('Failed to fetch users:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingId) {
        await apiClient.put(`/admin/users/${editingId}`, formData);
        toast.success('Benutzer erfolgreich aktualisiert');
      } else {
        const response = await apiClient.post('/admin/users', formData);
        setTempPassword(response.data.temporary_password);
        toast.success('Benutzer erfolgreich erstellt');
      }
      fetchUsers();
      if (!tempPassword) resetForm();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Fehler beim Speichern');
    }
  };

  const handleEdit = (user: User) => {
    setEditingId(user.id);
    setFormData({
      email: user.email,
      first_name: user.first_name,
      last_name: user.last_name,
      role: user.role,
      weekly_hours: user.weekly_hours,
      vacation_days: user.vacation_days,
      work_days_per_week: user.work_days_per_week || 5,
      track_hours: user.track_hours ?? true,
    });
    setShowForm(true);
  };

  const handleResetPassword = (userId: string, name: string) => {
    confirm({
      title: 'Passwort zurücksetzen',
      message: `Passwort für ${name} wirklich zurücksetzen? Ein neues temporäres Passwort wird generiert.`,
      confirmLabel: 'Zurücksetzen',
      variant: 'warning',
      onConfirm: async () => {
        try {
          const response = await apiClient.post(`/admin/users/${userId}/reset-password`);
          setResetPasswordData({
            password: response.data.temporary_password,
            userName: name
          });
          toast.success('Passwort erfolgreich zurückgesetzt');
        } catch (error) {
          toast.error('Fehler beim Zurücksetzen des Passworts');
        }
      },
    });
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
          toast.success(`Benutzer ${name} erfolgreich deaktiviert`);
          fetchUsers();
        } catch (error: any) {
          toast.error(error.response?.data?.detail || 'Fehler beim Deaktivieren');
        }
      },
    });
  };

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setTempPassword(null);
    setFormData({
      email: '',
      first_name: '',
      last_name: '',
      role: 'employee',
      weekly_hours: 40,
      vacation_days: 30,
      work_days_per_week: 5,
      track_hours: true,
    });
  };

  const handleOpenHoursModal = async (user: User) => {
    setSelectedUser(user);
    setShowHoursModal(true);
    setHoursFormData({
      effective_from: new Date().toISOString().split('T')[0],
      weekly_hours: user.weekly_hours,
      note: '',
    });
    await fetchHoursChanges(user.id);
  };

  const fetchHoursChanges = async (userId: string) => {
    try {
      const response = await apiClient.get(`/admin/users/${userId}/working-hours-changes`);
      setHoursChanges(response.data);
    } catch (error) {
      console.error('Failed to fetch hours changes:', error);
    }
  };

  const handleAddHoursChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;

    try {
      await apiClient.post(`/admin/users/${selectedUser.id}/working-hours-changes`, hoursFormData);
      await fetchHoursChanges(selectedUser.id);
      await fetchUsers(); // Refresh user list to show updated current hours
      setHoursFormData({
        effective_from: new Date().toISOString().split('T')[0],
        weekly_hours: selectedUser.weekly_hours,
        note: '',
      });
      toast.success('Stundenänderung erfolgreich hinzugefügt');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Fehler beim Hinzufügen');
    }
  };

  const handleDeleteHoursChange = (changeId: string) => {
    if (!selectedUser) return;
    confirm({
      title: 'Stundenänderung löschen',
      message: 'Möchten Sie diese Stundenänderung wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/admin/users/${selectedUser.id}/working-hours-changes/${changeId}`);
          await fetchHoursChanges(selectedUser.id);
          await fetchUsers();
          toast.success('Stundenänderung erfolgreich gelöscht');
        } catch (error) {
          toast.error('Fehler beim Löschen der Stundenänderung');
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
        user.email.toLowerCase().includes(searchLower)
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
        <h1 className="text-3xl font-bold text-gray-900">Benutzerverwaltung</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
        >
          {showForm ? <X size={20} /> : <Plus size={20} />}
          <span>{showForm ? 'Abbrechen' : 'Neue:r Mitarbeiter:in'}</span>
        </button>
      </div>

      {/* User Form */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">
            {editingId ? 'Benutzer bearbeiten' : 'Neue:n Benutzer:in anlegen'}
          </h3>

          {tempPassword && (
            <div className="bg-yellow-50 border border-yellow-200 p-4 rounded-lg mb-4">
              <p className="font-semibold text-yellow-900 mb-2">
                Benutzer erfolgreich angelegt!
              </p>
              <p className="text-yellow-800 mb-2">Temporäres Passwort:</p>
              <code className="bg-white px-3 py-2 rounded border border-yellow-300 text-lg font-mono">
                {tempPassword}
              </code>
              <p className="text-sm text-yellow-700 mt-2">
                Bitte notieren Sie dieses Passwort und geben Sie es der betroffenen Person.
              </p>
              <button
                onClick={resetForm}
                className="mt-4 bg-primary text-white px-4 py-2 rounded-lg"
              >
                Schließen
              </button>
            </div>
          )}

          {!tempPassword && (
            <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">E-Mail</label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Rolle</label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value as any })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                >
                  <option value="employee">Mitarbeiter:in</option>
                  <option value="admin">Administrator</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Vorname</label>
                <input
                  type="text"
                  value={formData.first_name}
                  onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nachname</label>
                <input
                  type="text"
                  value={formData.last_name}
                  onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Wochenstunden</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.weekly_hours}
                  onChange={(e) => setFormData({ ...formData, weekly_hours: parseFloat(e.target.value) })}
                  required
                  min="0"
                  max="60"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Arbeitstage pro Woche</label>
                <input
                  type="number"
                  value={formData.work_days_per_week}
                  onChange={(e) => setFormData({ ...formData, work_days_per_week: parseInt(e.target.value) || 5 })}
                  required
                  min="1"
                  max="7"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Anzahl der Arbeitstage pro Woche (1-7)
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Urlaubstage</label>
                <input
                  type="number"
                  value={formData.vacation_days}
                  onChange={(e) => setFormData({ ...formData, vacation_days: parseInt(e.target.value) })}
                  required
                  min="0"
                  max="50"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
                {suggestedVacation !== null && formData.vacation_days !== suggestedVacation && (
                  <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded text-xs">
                    💡 <strong>Empfehlung:</strong> {suggestedVacation} Tage
                    (basierend auf {formData.work_days_per_week} Arbeitstagen/Woche)
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, vacation_days: suggestedVacation })}
                      className="ml-2 text-blue-600 underline"
                    >
                      Übernehmen
                    </button>
                  </div>
                )}
              </div>
              <div className="md:col-span-2 flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
                <input
                  type="checkbox"
                  id="track_hours"
                  checked={formData.track_hours}
                  onChange={(e) => setFormData({ ...formData, track_hours: e.target.checked })}
                  className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
                />
                <label htmlFor="track_hours" className="text-sm font-medium text-gray-700 cursor-pointer">
                  Stundenzählung aktiv (Soll-Stunden werden berechnet)
                </label>
              </div>
              <div className="md:col-span-2">
                <button
                  type="submit"
                  className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition"
                >
                  <Save size={18} />
                  <span>Speichern</span>
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* Filter Input */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
          <input
            type="text"
            placeholder="Suche nach Name oder E-Mail..."
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
                  onClick={() => handleSort('email')}
                >
                  <div className="flex items-center space-x-1">
                    <span>E-Mail</span>
                    {sortField === 'email' && (
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
                  <tr key={user.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {user.last_name}, {user.first_name}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{user.email}</td>
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
                      {user.is_active ? (
                        <span className="text-green-600">Aktiv</span>
                      ) : (
                        <span className="text-red-600">Inaktiv</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right text-sm space-x-3">
                      <button
                        onClick={() => handleEdit(user)}
                        className="text-primary hover:text-primary-dark"
                        title="Bearbeiten"
                      >
                        <Edit2 size={16} />
                      </button>
                      <button
                        onClick={() => handleOpenHoursModal(user)}
                        className="text-blue-600 hover:text-blue-800"
                        title="Stundenverlauf"
                      >
                        <Clock size={16} />
                      </button>
                      <button
                        onClick={() => handleResetPassword(user.id, `${user.first_name} ${user.last_name}`)}
                        className="text-orange-600 hover:text-orange-800"
                        title="Passwort zurücksetzen"
                      >
                        <Key size={16} />
                      </button>
                      <button
                        onClick={() => handleDeactivate(user.id, `${user.first_name} ${user.last_name}`)}
                        className="text-red-600 hover:text-red-800"
                        title="Deaktivieren"
                      >
                        <UserX size={16} />
                      </button>
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
                <div key={user.id} className="p-4">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                      <p className="font-medium text-gray-900">
                        {user.last_name}, {user.first_name}
                      </p>
                      <p className="text-sm text-gray-600">{user.email}</p>
                      <div className="flex items-center space-x-2 mt-2">
                        <Badge variant={user.role === 'admin' ? 'info' : 'default'} size="sm">
                          {user.role === 'admin' ? 'Admin' : 'Mitarbeiter'}
                        </Badge>
                        <Badge variant={user.is_active ? 'success' : 'error'} size="sm">
                          {user.is_active ? 'Aktiv' : 'Inaktiv'}
                        </Badge>
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
                      onClick={() => handleEdit(user)}
                      className="flex-1 flex items-center justify-center space-x-2 px-3 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition"
                      aria-label={`${user.first_name} ${user.last_name} bearbeiten`}
                    >
                      <Edit2 size={16} />
                      <span>Bearbeiten</span>
                    </button>
                    <button
                      onClick={() => handleOpenHoursModal(user)}
                      className="p-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition"
                      aria-label="Stundenverlauf anzeigen"
                      title="Stundenverlauf"
                    >
                      <Clock size={16} />
                    </button>
                    <button
                      onClick={() => handleResetPassword(user.id, `${user.first_name} ${user.last_name}`)}
                      className="p-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition"
                      aria-label="Passwort zurücksetzen"
                      title="Passwort zurücksetzen"
                    >
                      <Key size={16} />
                    </button>
                    {user.is_active && (
                      <button
                        onClick={() => handleDeactivate(user.id, `${user.first_name} ${user.last_name}`)}
                        className="p-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition"
                        aria-label="Benutzer deaktivieren"
                        title="Deaktivieren"
                      >
                        <UserX size={16} />
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
      {showHoursModal && selectedUser && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowHoursModal(false)}
          aria-hidden="true"
        >
          <FocusTrap
            focusTrapOptions={{
              allowOutsideClick: true,
              escapeDeactivates: true,
              onDeactivate: () => setShowHoursModal(false),
            }}
          >
            <div 
              role="dialog"
              aria-modal="true"
              aria-labelledby="hours-modal-title"
              className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
                <div>
                  <h2 id="hours-modal-title" className="text-2xl font-bold text-gray-900">Stundenverlauf</h2>
                  <p className="text-sm text-gray-600 mt-1">
                    {selectedUser.first_name} {selectedUser.last_name} • Aktuell: {selectedUser.weekly_hours} Std/Woche
                  </p>
                </div>
                <button
                  onClick={() => setShowHoursModal(false)}
                  className="text-gray-500 hover:text-gray-700"
                  aria-label={`Stundenverlauf für ${selectedUser.first_name} ${selectedUser.last_name} schließen`}
                >
                  <X size={24} />
                </button>
              </div>

            <div className="p-6">
              {/* Add New Change Form */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <h3 className="font-semibold text-blue-900 mb-3">Neue Stundenänderung</h3>
                <form onSubmit={handleAddHoursChange} className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Gültig ab
                    </label>
                    <input
                      type="date"
                      value={hoursFormData.effective_from}
                      onChange={(e) => setHoursFormData({ ...hoursFormData, effective_from: e.target.value })}
                      required
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Wochenstunden
                    </label>
                    <input
                      type="number"
                      step="0.5"
                      value={hoursFormData.weekly_hours}
                      onChange={(e) => setHoursFormData({ ...hoursFormData, weekly_hours: parseFloat(e.target.value) })}
                      required
                      min="0"
                      max="60"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Notiz (optional)
                    </label>
                    <input
                      type="text"
                      value={hoursFormData.note}
                      onChange={(e) => setHoursFormData({ ...hoursFormData, note: e.target.value })}
                      placeholder="z.B. Teilzeitänderung"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                    />
                  </div>
                  <div className="md:col-span-3">
                    <button
                      type="submit"
                      className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition"
                    >
                      <Plus size={18} />
                      <span>Hinzufügen</span>
                    </button>
                  </div>
                </form>
              </div>

              {/* History List */}
              <div>
                <h3 className="font-semibold text-gray-900 mb-3">Verlauf</h3>
                {hoursChanges.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">Keine Änderungen vorhanden</p>
                ) : (
                  <div className="space-y-3">
                    {hoursChanges.map((change) => (
                      <div
                        key={change.id}
                        className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex items-center justify-between"
                      >
                        <div>
                          <p className="font-medium text-gray-900">
                            Ab {new Date(change.effective_from).toLocaleDateString('de-DE', {
                              day: '2-digit',
                              month: '2-digit',
                              year: 'numeric',
                            })}: {change.weekly_hours} Std/Woche
                          </p>
                          {change.note && (
                            <p className="text-sm text-gray-600 mt-1">{change.note}</p>
                          )}
                          <p className="text-xs text-gray-500 mt-1">
                            Erstellt: {new Date(change.created_at).toLocaleDateString('de-DE', {
                              day: '2-digit',
                              month: '2-digit',
                              year: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </p>
                        </div>
                        <button
                          onClick={() => handleDeleteHoursChange(change.id)}
                          className="text-red-600 hover:text-red-800"
                          title="Löschen"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-800">
                  <strong>Hinweis:</strong> Die Berechnungen von Soll-Stunden berücksichtigen automatisch die
                  historischen Werte. Wenn z.B. jemand ab 15.03. von 20h auf 30h wechselt, werden für den
                  März die ersten 14 Tage mit 20h und ab dem 15. mit 30h berechnet.
                </p>
              </div>
            </div>
          </div>
          </FocusTrap>
        </div>
      )}

      {/* Password Reset Modal */}
      {resetPasswordData && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
          onClick={() => setResetPasswordData(null)}
        >
          <FocusTrap
            focusTrapOptions={{
              allowOutsideClick: true,
              escapeDeactivates: true,
              onDeactivate: () => setResetPasswordData(null),
            }}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="password-modal-title"
              className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 id="password-modal-title" className="text-xl font-semibold text-gray-900">
                  Temporäres Passwort erstellt
                </h3>
                <button
                  onClick={() => setResetPasswordData(null)}
                  className="text-gray-400 hover:text-gray-600 transition"
                  aria-label="Modal schließen"
                >
                  <X size={24} />
                </button>
              </div>

              <div className="mb-4">
                <p className="text-sm text-gray-600 mb-2">
                  Für <strong>{resetPasswordData.userName}</strong>:
                </p>
                <div className="bg-gray-50 p-4 rounded-lg border-2 border-gray-200">
                  <code className="text-lg font-mono font-bold text-gray-900 break-all">
                    {resetPasswordData.password}
                  </code>
                </div>
              </div>

              <button
                onClick={() => {
                  navigator.clipboard.writeText(resetPasswordData.password);
                  toast.success('Passwort in Zwischenablage kopiert');
                }}
                className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-3 rounded-lg flex items-center justify-center space-x-2 transition mb-4"
              >
                <Copy size={18} />
                <span>In Zwischenablage kopieren</span>
              </button>

              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-sm text-red-800 flex items-start space-x-2">
                  <span className="text-red-600 font-bold flex-shrink-0">⚠️</span>
                  <span>
                    <strong>Wichtig:</strong> Dieses Passwort wird nur einmal angezeigt!
                    Bitte notieren Sie es sorgfältig oder kopieren Sie es in die Zwischenablage.
                  </span>
                </p>
              </div>

              <button
                onClick={() => setResetPasswordData(null)}
                className="w-full mt-4 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg transition"
              >
                Schließen
              </button>
            </div>
          </FocusTrap>
        </div>
      )}
    </div>
  );
}
