import { useState, useEffect } from 'react';
import apiClient from '../../../api/client';
import { Save } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { useAuthStore } from '../../../stores/authStore';
import PasswordInput from '../../../components/PasswordInput';
import { getErrorMessage } from '../../../utils/errorMessage';
import { parseHours } from '../../../utils/formatters';
import { PASTEL_COLORS, DEFAULT_CALENDAR_COLOR } from '../../../utils/calendarColors';

import type { User } from '../../../types/user';

interface UserFormProps {
  editUser: User | null;
  onSaved: () => void;
}

export default function UserForm({ editUser, onSaved }: UserFormProps) {
  const toast = useToast();
  const { user: currentUser, setUser: setCurrentUser } = useAuthStore();
  const [suggestedVacation, setSuggestedVacation] = useState<number | null>(null);
  // Guards against double-submit (fast double-click would create duplicate users).
  const [submitting, setSubmitting] = useState(false);
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
    receives_company_closures: true,
    calendar_color: DEFAULT_CALENDAR_COLOR,
    first_work_day: '',
    last_work_day: '',
    department: '',
    child_sick_days_per_year: null as number | null, // #376 §45 SGB V; null = Tenant-Default
    use_daily_schedule: false,
    hours_monday: 8,
    hours_tuesday: 8,
    hours_wednesday: 8,
    hours_thursday: 8,
    hours_friday: 8,
    scheduled_start_monday: '',
    scheduled_end_monday: '',
    scheduled_start_tuesday: '',
    scheduled_end_tuesday: '',
    scheduled_start_wednesday: '',
    scheduled_end_wednesday: '',
    scheduled_start_thursday: '',
    scheduled_end_thursday: '',
    scheduled_start_friday: '',
    scheduled_end_friday: '',
    overtime_carryover: 0, // #158: Anfangssaldo Überstunden (kein User-Feld, separater Carryover-Call)
  });
  // #158: vorhandener Vortrag zum Startjahr — wird beim Speichern erhalten.
  const [hadCarryover, setHadCarryover] = useState(false);

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
        receives_company_closures: editUser.receives_company_closures ?? true,
        calendar_color: editUser.calendar_color || DEFAULT_CALENDAR_COLOR,
        first_work_day: editUser.first_work_day || '',
        last_work_day: editUser.last_work_day || '',
        department: editUser.department || '',
        child_sick_days_per_year: editUser.child_sick_days_per_year ?? null, // #376
        use_daily_schedule: editUser.use_daily_schedule ?? false,
        hours_monday: editUser.hours_monday ?? 8,
        hours_tuesday: editUser.hours_tuesday ?? 8,
        hours_wednesday: editUser.hours_wednesday ?? 8,
        hours_thursday: editUser.hours_thursday ?? 8,
        hours_friday: editUser.hours_friday ?? 8,
        scheduled_start_monday: editUser.scheduled_start_monday?.substring(0, 5) || '',
        scheduled_end_monday: editUser.scheduled_end_monday?.substring(0, 5) || '',
        scheduled_start_tuesday: editUser.scheduled_start_tuesday?.substring(0, 5) || '',
        scheduled_end_tuesday: editUser.scheduled_end_tuesday?.substring(0, 5) || '',
        scheduled_start_wednesday: editUser.scheduled_start_wednesday?.substring(0, 5) || '',
        scheduled_end_wednesday: editUser.scheduled_end_wednesday?.substring(0, 5) || '',
        scheduled_start_thursday: editUser.scheduled_start_thursday?.substring(0, 5) || '',
        scheduled_end_thursday: editUser.scheduled_end_thursday?.substring(0, 5) || '',
        scheduled_start_friday: editUser.scheduled_start_friday?.substring(0, 5) || '',
        scheduled_end_friday: editUser.scheduled_end_friday?.substring(0, 5) || '',
        overtime_carryover: 0,
      });
    }
  }, [editUser]);

  // #158: beim Bearbeiten den Anfangssaldo (Überstunden-Carryover des Startjahres)
  // laden, damit das Feld den aktuellen Wert zeigt und der Urlaubs-Vortrag erhalten bleibt.
  useEffect(() => {
    if (!editUser) {
      setHadCarryover(false);
      return;
    }
    const startYear = editUser.first_work_day
      ? new Date(editUser.first_work_day).getFullYear()
      : new Date().getFullYear();
    (async () => {
      try {
        const res = await apiClient.get<Array<{ year: number; overtime_hours: number; vacation_days: number }>>(
          `/admin/users/${editUser.id}/carryovers`,
        );
        const row = res.data.find((c) => c.year === startYear);
        if (row) {
          setFormData((prev) => ({ ...prev, overtime_carryover: row.overtime_hours }));
          setHadCarryover(true);
        }
      } catch {
        /* Carryover optional — Fehler hier nicht blockierend */
      }
    })();
  }, [editUser]);

  useEffect(() => {
    if (formData.work_days_per_week > 0) {
      const suggested = Math.round(30 * formData.work_days_per_week / 5);
      setSuggestedVacation(suggested);
    }
  }, [formData.work_days_per_week]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      // #158: overtime_carryover is NOT a user field — it goes to the carryover
      // endpoint separately. Keep it out of the user payload.
      const { overtime_carryover, ...userFields } = formData;
      const payload = {
        ...userFields,
        first_work_day: formData.first_work_day || null,
        last_work_day: formData.last_work_day || null,
        department: formData.department.trim() || null,
        scheduled_start_monday: formData.scheduled_start_monday || null,
        scheduled_end_monday: formData.scheduled_end_monday || null,
        scheduled_start_tuesday: formData.scheduled_start_tuesday || null,
        scheduled_end_tuesday: formData.scheduled_end_tuesday || null,
        scheduled_start_wednesday: formData.scheduled_start_wednesday || null,
        scheduled_end_wednesday: formData.scheduled_end_wednesday || null,
        scheduled_start_thursday: formData.scheduled_start_thursday || null,
        scheduled_end_thursday: formData.scheduled_end_thursday || null,
        scheduled_start_friday: formData.scheduled_start_friday || null,
        scheduled_end_friday: formData.scheduled_end_friday || null,
      };
      const startYear = formData.first_work_day
        ? new Date(formData.first_work_day).getFullYear()
        : new Date().getFullYear();

      // Review M-C1: always preserve the *target year's* own vacation carryover
      // (fetch it fresh) so editing first_work_day can never copy another year's
      // value or clobber an existing one.
      const writeCarryover = async (userId: string) => {
        try {
          let vacationDays = 0;
          try {
            const res = await apiClient.get<Array<{ year: number; vacation_days: number }>>(
              `/admin/users/${userId}/carryovers`,
            );
            const row = res.data.find((c) => c.year === startYear);
            if (row) vacationDays = row.vacation_days ?? 0;
          } catch {
            /* no existing carryover for the target year — keep 0 */
          }
          await apiClient.put(`/admin/users/${userId}/carryovers/${startYear}`, {
            overtime_hours: overtime_carryover,
            vacation_days: vacationDays,
          });
        } catch (e: any) {
          // Primary save succeeded — surface a softer warning, don't abort.
          toast.error(getErrorMessage(e, 'Benutzer gespeichert, aber Anfangssaldo konnte nicht gesetzt werden'));
        }
      };

      if (editUser) {
        // When editing, send only the fields that can be updated (exclude password)
        const { password, ...updateData } = payload;
        await apiClient.put(`/admin/users/${editUser.id}`, updateData);
        // #158: nur schreiben, wenn ein Saldo gesetzt ist oder bereits einer existierte
        // (verhindert leere 0/0-Carryover-Zeilen für unberührte User).
        if (overtime_carryover !== 0 || hadCarryover) {
          await writeCarryover(editUser.id);
        }
        // If the admin edited themselves, refresh the auth store so Dashboard/Layout update
        if (currentUser && editUser.id === currentUser.id) {
          const meRes = await apiClient.get('/auth/me');
          setCurrentUser(meRes.data);
        }
        toast.success('Benutzer erfolgreich aktualisiert');
      } else {
        const res = await apiClient.post('/admin/users', payload);
        const newId: string | undefined = res.data?.user?.id;
        if (newId && overtime_carryover !== 0) {
          await writeCarryover(newId);
        }
        toast.success('Benutzer erfolgreich erstellt');
      }
      onSaved();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
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
              onChange={(e) => setFormData({ ...formData, weekly_hours: parseHours(e.target.value) })}
              required
              min="0"
              max="60"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            />
            {editUser && (
              <p className="mt-1 text-xs text-amber-600">
                ⚠️ Eine Änderung hier wirkt <strong>rückwirkend</strong> auf das Soll aller
                Zeiträume ohne eigenen Stundenhistorie-Eintrag. Für eine stichtagsgenaue
                Änderung ab einem Datum stattdessen die <strong>Stundenhistorie</strong>
                (Wochenstunden-Verlauf) nutzen.
              </p>
            )}
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
              onChange={(e) => setFormData({ ...formData, vacation_days: parseInt(e.target.value) || 0 })}
              required
              min="0"
              max="50"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            />
            {suggestedVacation !== null && formData.vacation_days !== suggestedVacation && (
              <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded-sm text-xs">
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
          <div>
            <label htmlFor="f-child-sick" className="block text-sm font-medium text-gray-700 mb-1">
              Kind-krank-Tage/Jahr (§45 SGB V)
            </label>
            <input
              id="f-child-sick"
              type="number"
              min="0"
              max="70"
              value={formData.child_sick_days_per_year ?? ''}
              placeholder="Standard (Einstellungen)"
              onChange={(e) =>
                setFormData({
                  ...formData,
                  child_sick_days_per_year: e.target.value === '' ? null : parseInt(e.target.value),
                })
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            />
            <p className="mt-1 text-xs text-gray-400">Leer = Standardwert aus den Einstellungen.</p>
          </div>
          {formData.track_hours && (
            <div>
              <label htmlFor="f-overtime-carryover" className="block text-sm font-medium text-gray-700 mb-1">
                Anfangssaldo Überstunden (h)
              </label>
              <input
                id="f-overtime-carryover"
                type="number"
                step="0.25"
                value={formData.overtime_carryover}
                onChange={(e) => setFormData({ ...formData, overtime_carryover: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-gray-500 mt-1">
                Übernommener Überstundensaldo zum Startjahr
                ({formData.first_work_day ? new Date(formData.first_work_day).getFullYear() : new Date().getFullYear()}).
                Negativ = Minusstunden.
              </p>
            </div>
          )}

          <div className="md:col-span-2 flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
            <input
              type="checkbox"
              id="track_hours"
              checked={formData.track_hours}
              onChange={(e) => setFormData({ ...formData, track_hours: e.target.checked })}
              className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary"
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
              className="w-4 h-4 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
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
              className="w-4 h-4 text-blue-600 border-gray-300 rounded-sm focus:ring-blue-500"
            />
            <label htmlFor="is_night_worker" className="text-sm font-medium text-gray-700 cursor-pointer">
              Nachtarbeitnehmer (§6 ArbZG – 8h-Tageslimit bei Nachtarbeit)
            </label>
          </div>

          <div className="md:col-span-2 flex items-center space-x-2 p-3 bg-emerald-50 rounded-lg border border-emerald-200">
            <input
              type="checkbox"
              id="receives_company_closures"
              checked={formData.receives_company_closures ?? true}
              onChange={(e) => setFormData({ ...formData, receives_company_closures: e.target.checked })}
              className="w-4 h-4 text-emerald-600 border-gray-300 rounded-sm focus:ring-emerald-500"
            />
            <label htmlFor="receives_company_closures" className="text-sm font-medium text-gray-700 cursor-pointer">
              Nimmt an Betriebsferien teil (Betriebsferien werden automatisch eingetragen)
            </label>
          </div>

          {/* #297: Kalenderfarbe — vom Admin für jede:n Mitarbeiter:in setzbar
              (ergänzt die Selbst-Auswahl im Profil). */}
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Kalenderfarbe
              <span
                className="ml-2 inline-block w-4 h-4 rounded-full align-middle border border-gray-300"
                style={{ backgroundColor: formData.calendar_color }}
              />
            </label>
            <div className="grid grid-cols-6 sm:grid-cols-12 gap-2">
              {PASTEL_COLORS.map((color) => (
                <button
                  key={color.hex}
                  type="button"
                  onClick={() => setFormData({ ...formData, calendar_color: color.hex })}
                  aria-label={`Farbe ${color.name}`}
                  aria-pressed={formData.calendar_color === color.hex}
                  title={color.name}
                  className={`relative w-full aspect-square rounded-lg transition-all hover:scale-110 ${
                    formData.calendar_color === color.hex
                      ? 'ring-4 ring-primary ring-offset-2 scale-110'
                      : 'hover:ring-2 hover:ring-gray-300'
                  }`}
                  style={{ backgroundColor: color.hex }}
                >
                  {formData.calendar_color === color.hex && (
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-3 h-3 bg-white rounded-full flex items-center justify-center">
                        <div className="w-1.5 h-1.5 bg-primary rounded-full" />
                      </div>
                    </div>
                  )}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Farbe des Badge-Rings im Kalender. Mitarbeitende können sie auch selbst im Profil ändern.
            </p>
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
          <div>
            <label htmlFor="f-department" className="block text-sm font-medium text-gray-700 mb-1">Abteilung/Bereich (optional)</label>
            <input
              id="f-department"
              type="text"
              maxLength={100}
              value={formData.department}
              onChange={(e) => setFormData({ ...formData, department: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              placeholder="z. B. Praxis, Verwaltung, Reinigung"
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
                  className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary"
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
                          step="0.25"
                          min="0"
                          max="24"
                          value={formData[key]}
                          onChange={(e) => setFormData({ ...formData, [key]: parseFloat(e.target.value) || 0 })}
                          aria-label={`Stunden ${day}`}
                          className="w-full px-2 py-1 text-center border border-gray-300 rounded-sm focus:ring-2 focus:ring-primary text-sm"
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

          {/* Soll-Arbeitszeiten (Arbeitszeit-Fenster) */}
          <div className="md:col-span-2 border border-gray-200 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 mb-3">
              Soll-Arbeitszeiten je Wochentag <span className="text-gray-400 font-normal">(optional – leer lassen = kein Fenster)</span>
            </p>
            <div className="grid grid-cols-5 gap-3">
              {(
                [
                  { label: 'Mo', startKey: 'scheduled_start_monday', endKey: 'scheduled_end_monday' },
                  { label: 'Di', startKey: 'scheduled_start_tuesday', endKey: 'scheduled_end_tuesday' },
                  { label: 'Mi', startKey: 'scheduled_start_wednesday', endKey: 'scheduled_end_wednesday' },
                  { label: 'Do', startKey: 'scheduled_start_thursday', endKey: 'scheduled_end_thursday' },
                  { label: 'Fr', startKey: 'scheduled_start_friday', endKey: 'scheduled_end_friday' },
                ] as const
              ).map(({ label, startKey, endKey }) => (
                <div key={label} className="flex flex-col gap-1">
                  <span className="block text-xs font-medium text-gray-600 text-center">{label}</span>
                  <input
                    type="time"
                    value={formData[startKey]}
                    onChange={(e) => setFormData({ ...formData, [startKey]: e.target.value })}
                    aria-label={`Soll-Beginn ${label}`}
                    className="w-full px-1 py-1 text-center border border-gray-300 rounded-sm focus:ring-2 focus:ring-primary text-xs"
                  />
                  <input
                    type="time"
                    value={formData[endKey]}
                    onChange={(e) => setFormData({ ...formData, [endKey]: e.target.value })}
                    aria-label={`Soll-Ende ${label}`}
                    className="w-full px-1 py-1 text-center border border-gray-300 rounded-sm focus:ring-2 focus:ring-primary text-xs"
                  />
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-2">Oben: Soll-Beginn · Unten: Soll-Ende</p>
          </div>

          <div className="md:col-span-2">
            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save size={18} />
              <span>Speichern</span>
            </button>
          </div>
        </form>
    </div>
  );
}
