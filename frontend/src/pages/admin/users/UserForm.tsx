import { useState, useEffect } from 'react';
import apiClient from '../../../api/client';
import { Save } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { useAuthStore } from '../../../stores/authStore';
import PasswordInput from '../../../components/PasswordInput';
import { getErrorMessage } from '../../../utils/errorMessage';

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

interface UserFormProps {
  editUser: User | null;
  onSaved: () => void;
}

export default function UserForm({ editUser, onSaved }: UserFormProps) {
  const toast = useToast();
  const { user: currentUser, setUser: setCurrentUser } = useAuthStore();
  const [suggestedVacation, setSuggestedVacation] = useState<number | null>(null);
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    role: 'employee' as 'admin' | 'employee',
    weekly_hours: 40,
    vacation_days: 30,
    work_days_per_week: 5,
    track_hours: true,
    exempt_from_arbzg: false,
    is_night_worker: false,
    first_work_day: '',
    last_work_day: '',
    use_daily_schedule: false,
    hours_monday: 8,
    hours_tuesday: 8,
    hours_wednesday: 8,
    hours_thursday: 8,
    hours_friday: 8,
  });

  useEffect(() => {
    if (editUser) {
      setFormData({
        username: editUser.username,
        email: editUser.email || '',
        password: '',
        first_name: editUser.first_name,
        last_name: editUser.last_name,
        role: editUser.role,
        weekly_hours: editUser.weekly_hours,
        vacation_days: editUser.vacation_days,
        work_days_per_week: editUser.work_days_per_week || 5,
        track_hours: editUser.track_hours ?? true,
        exempt_from_arbzg: editUser.exempt_from_arbzg ?? false,
        is_night_worker: editUser.is_night_worker ?? false,
        first_work_day: editUser.first_work_day || '',
        last_work_day: editUser.last_work_day || '',
        use_daily_schedule: editUser.use_daily_schedule ?? false,
        hours_monday: editUser.hours_monday ?? 8,
        hours_tuesday: editUser.hours_tuesday ?? 8,
        hours_wednesday: editUser.hours_wednesday ?? 8,
        hours_thursday: editUser.hours_thursday ?? 8,
        hours_friday: editUser.hours_friday ?? 8,
      });
    }
  }, [editUser]);

  useEffect(() => {
    if (formData.work_days_per_week > 0) {
      const suggested = Math.round(30 * formData.work_days_per_week / 5);
      setSuggestedVacation(suggested);
    }
  }, [formData.work_days_per_week]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // Convert empty date strings to null for the API
      const payload = {
        ...formData,
        first_work_day: formData.first_work_day || null,
        last_work_day: formData.last_work_day || null,
      };
      if (editUser) {
        // When editing, send only the fields that can be updated (exclude password)
        const { password, ...updateData } = payload;
        await apiClient.put(`/admin/users/${editUser.id}`, updateData);
        // If the admin edited themselves, refresh the auth store so Dashboard/Layout update
        if (currentUser && editUser.id === currentUser.id) {
          const meRes = await apiClient.get('/auth/me');
          setCurrentUser(meRes.data);
        }
        toast.success('Benutzer erfolgreich aktualisiert');
      } else {
        await apiClient.post('/admin/users', payload);
        toast.success('Benutzer erfolgreich erstellt');
      }
      onSaved();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
      <h3 className="text-lg font-semibold mb-4">
        {editUser ? 'Benutzer bearbeiten' : 'Neue:n Benutzer:in anlegen'}
      </h3>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="f-username" className="block text-sm font-medium text-gray-700 mb-1">Benutzername *</label>
            <input
              id="f-username"
              type="text"
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              required
              autoFocus
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              placeholder="benutzername"
            />
          </div>
          <div>
            <label htmlFor="f-email" className="block text-sm font-medium text-gray-700 mb-1">E-Mail (optional)</label>
            <input
              id="f-email"
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              placeholder="name@example.de"
            />
          </div>
          {!editUser && (
            <div>
              <label htmlFor="f-password" className="block text-sm font-medium text-gray-700 mb-1">Passwort *</label>
              <PasswordInput
                id="f-password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                required
                minLength={10}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                placeholder="Mind. 10 Zeichen"
              />
              <p className="text-xs text-gray-500 mt-1">
                Mind. 10 Zeichen, 1 Großbuchstabe, 1 Kleinbuchstabe, 1 Ziffer
              </p>
            </div>
          )}
          <div>
            <label htmlFor="f-role" className="block text-sm font-medium text-gray-700 mb-1">Rolle</label>
            <select
              id="f-role"
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value as 'admin' | 'employee' })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            >
              <option value="employee">Mitarbeiter:in</option>
              <option value="admin">Administrator</option>
            </select>
          </div>
          <div>
            <label htmlFor="f-firstname" className="block text-sm font-medium text-gray-700 mb-1">Vorname</label>
            <input
              id="f-firstname"
              type="text"
              value={formData.first_name}
              onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            />
          </div>
          <div>
            <label htmlFor="f-lastname" className="block text-sm font-medium text-gray-700 mb-1">Nachname</label>
            <input
              id="f-lastname"
              type="text"
              value={formData.last_name}
              onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            />
          </div>
          <div>
            <label htmlFor="f-weekly-hours" className="block text-sm font-medium text-gray-700 mb-1">Wochenstunden</label>
            <input
              id="f-weekly-hours"
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
            <label htmlFor="f-work-days" className="block text-sm font-medium text-gray-700 mb-1">Arbeitstage pro Woche</label>
            <input
              id="f-work-days"
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
            <label htmlFor="f-vacation" className="block text-sm font-medium text-gray-700 mb-1">Urlaubstage</label>
            <input
              id="f-vacation"
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

          <div className="md:col-span-2 flex items-center space-x-2 p-3 bg-amber-50 rounded-lg border border-amber-200">
            <input
              type="checkbox"
              id="exempt_from_arbzg"
              checked={formData.exempt_from_arbzg}
              onChange={(e) => setFormData({ ...formData, exempt_from_arbzg: e.target.checked })}
              className="w-4 h-4 text-amber-600 border-gray-300 rounded focus:ring-amber-500"
            />
            <label htmlFor="exempt_from_arbzg" className="text-sm font-medium text-gray-700 cursor-pointer">
              ArbZG-Prüfungen aussetzen (§18 ArbZG – leitende Angestellte)
            </label>
          </div>

          <div className="md:col-span-2 flex items-center space-x-2 p-3 bg-blue-50 rounded-lg border border-blue-200">
            <input
              type="checkbox"
              id="is_night_worker"
              checked={formData.is_night_worker ?? false}
              onChange={(e) => setFormData({ ...formData, is_night_worker: e.target.checked })}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <label htmlFor="is_night_worker" className="text-sm font-medium text-gray-700 cursor-pointer">
              Nachtarbeitnehmer (§6 ArbZG – 8h-Tageslimit bei Nachtarbeit)
            </label>
          </div>

          {/* First / Last Work Day */}
          <div>
            <label className="block text-sm font-medium text-gray-700">Erster Arbeitstag</label>
            <input
              type="date"
              value={formData.first_work_day}
              onChange={(e) => setFormData({ ...formData, first_work_day: e.target.value })}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Letzter Arbeitstag</label>
            <input
              type="date"
              value={formData.last_work_day}
              onChange={(e) => setFormData({ ...formData, last_work_day: e.target.value })}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>

          {/* Daily Schedule Toggle */}
          {formData.track_hours && (
            <div className="md:col-span-2 border border-gray-200 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-3">
                <input
                  type="checkbox"
                  id="use_daily_schedule"
                  checked={formData.use_daily_schedule}
                  onChange={(e) => setFormData({ ...formData, use_daily_schedule: e.target.checked })}
                  className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
                />
                <label htmlFor="use_daily_schedule" className="text-sm font-medium text-gray-700 cursor-pointer">
                  Individuelle Tagesstunden (statt einheitlich {(formData.weekly_hours / formData.work_days_per_week).toFixed(1)}h/Tag)
                </label>
              </div>
              {formData.use_daily_schedule && (
                <div className="grid grid-cols-5 gap-2">
                  {(['Mo', 'Di', 'Mi', 'Do', 'Fr'] as const).map((day, idx) => {
                    const keys = ['hours_monday', 'hours_tuesday', 'hours_wednesday', 'hours_thursday', 'hours_friday'] as const;
                    const key = keys[idx];
                    return (
                      <div key={day} className="text-center">
                        <label htmlFor={`f-hours-${key}`} className="block text-xs font-medium text-gray-600 mb-1">{day}</label>
                        <input
                          id={`f-hours-${key}`}
                          type="number"
                          step="0.5"
                          min="0"
                          max="24"
                          value={formData[key]}
                          onChange={(e) => setFormData({ ...formData, [key]: parseFloat(e.target.value) || 0 })}
                          aria-label={`Stunden ${day}`}
                          className="w-full px-2 py-1 text-center border border-gray-300 rounded focus:ring-2 focus:ring-primary text-sm"
                        />
                      </div>
                    );
                  })}
                  <div className="col-span-5 text-xs text-gray-500 mt-1">
                    Summe: {(formData.hours_monday + formData.hours_tuesday + formData.hours_wednesday + formData.hours_thursday + formData.hours_friday).toFixed(1)}h/Woche
                    {formData.weekly_hours > 0 && (formData.hours_monday + formData.hours_tuesday + formData.hours_wednesday + formData.hours_thursday + formData.hours_friday) !== formData.weekly_hours && (
                      <span className="text-amber-600 ml-2">
                        (Gesamtwochenstunden: {formData.weekly_hours}h – bitte anpassen!)
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

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
    </div>
  );
}
