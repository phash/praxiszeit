import { useEffect, useState } from 'react';
import apiClient from '../../api/client';
import { Plus, Edit2, Key, UserX, Save, X } from 'lucide-react';

interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'admin' | 'employee';
  weekly_hours: number;
  vacation_days: number;
  track_hours: boolean;
  is_active: boolean;
  created_at: string;
}

export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
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
    track_hours: true,
  });
  const [tempPassword, setTempPassword] = useState<string | null>(null);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await apiClient.get('/admin/users');
      setUsers(response.data);
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
        alert('Benutzer aktualisiert');
      } else {
        const response = await apiClient.post('/admin/users', formData);
        setTempPassword(response.data.temporary_password);
      }
      fetchUsers();
      if (!tempPassword) resetForm();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Fehler beim Speichern');
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
      track_hours: user.track_hours ?? true,
    });
    setShowForm(true);
  };

  const handleResetPassword = async (userId: string, name: string) => {
    if (!confirm(`Passwort für ${name} zurücksetzen?`)) return;
    try {
      const response = await apiClient.post(`/admin/users/${userId}/reset-password`);
      alert(`Neues Passwort: ${response.data.temporary_password}`);
    } catch (error) {
      alert('Fehler beim Zurücksetzen');
    }
  };

  const handleDeactivate = async (userId: string, name: string) => {
    if (!confirm(`${name} wirklich deaktivieren?`)) return;
    try {
      await apiClient.delete(`/admin/users/${userId}`);
      fetchUsers();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Fehler beim Deaktivieren');
    }
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
      track_hours: true,
    });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Benutzerverwaltung</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
        >
          {showForm ? <X size={20} /> : <Plus size={20} />}
          <span>{showForm ? 'Abbrechen' : 'Neue Mitarbeiterin'}</span>
        </button>
      </div>

      {/* User Form */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">
            {editingId ? 'Benutzer bearbeiten' : 'Neue Mitarbeiterin anlegen'}
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
                Bitte notieren Sie dieses Passwort und geben Sie es der Mitarbeiterin.
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
                  <option value="employee">Mitarbeiterin</option>
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

      {/* Users Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">E-Mail</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rolle</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Wochenstd.</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Urlaub</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Stundenzählung</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-6 py-4 text-center text-gray-500">
                    Lade Benutzer...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-4 text-center text-gray-500">
                    Keine Benutzer vorhanden
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {user.last_name}, {user.first_name}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{user.email}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {user.role === 'admin' ? 'Admin' : 'Mitarbeiterin'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{user.weekly_hours}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{user.vacation_days}</td>
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
      </div>
    </div>
  );
}
