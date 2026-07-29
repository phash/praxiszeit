import { useState, useEffect } from 'react';
import apiClient from '../../../api/client';
import { Save } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { useAuthStore } from '../../../stores/authStore';
import { useSystemStore } from '../../../stores/systemStore';
import PasswordInput from '../../../components/PasswordInput';
import { getErrorMessage } from '../../../utils/errorMessage';
import { parseHours, deHoursExact, formatDayPlan } from '../../../utils/formatters';
import { PASTEL_COLORS, DEFAULT_CALENDAR_COLOR } from '../../../utils/calendarColors';

import type { User } from '../../../types/user';

interface UserFormProps {
  editUser: User | null;
  onSaved: () => void;
  // Task 6 (#Wochenstunden-anpassen): Wochenstunden sind beim Bearbeiten nur
  // noch Anzeige — die Änderung läuft über den Wochenstunden-Dialog, der in
  // Users.tsx lebt (dort auch über das Uhr-Symbol in der Liste erreichbar).
  // Optional, damit bestehende Render-Aufrufe/Tests ohne den Callback nicht
  // brechen; ohne ihn ist der Button praktisch ein No-op.
  onOpenHoursHistory?: (user: User) => void;
  // Release-Review 1.17.0 (Fund 2): der aktuelle Wochenstunden-Wert des
  // bearbeiteten Nutzers, unabhängig von `editUser` nachgeführt (Users.tsx
  // liest ihn live aus `users`). NUR für die read-only-Anzeige unten —
  // `formData.weekly_hours` (und damit alles, was der Admin sonst im
  // Formular eingegeben hat) bleibt davon unberührt. Fehlt der Wert (Anlegen,
  // kein Treffer mehr in `users`), fällt die Anzeige auf `formData.weekly_hours`
  // zurück.
  displayWeeklyHours?: number;
}

export default function UserForm({ editUser, onSaved, onOpenHoursHistory, displayWeeklyHours }: UserFormProps) {
  const toast = useToast();
  const { user: currentUser, setUser: setCurrentUser } = useAuthStore();
  const [suggestedVacation, setSuggestedVacation] = useState<number | null>(null);
  // Guards against double-submit (fast double-click would create duplicate users).
  const [submitting, setSubmitting] = useState(false);
  const minWage = useSystemStore((s) => s.getMinimumWage()); // #377
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
    milog_working_time_account: false, // #377
    agreed_monthly_hours: null as number | null, // #377 Baustein 2a: null = aus weekly_hours
    use_fixed_monthly_target: false, // #377 Baustein 2b: festes Monats-Soll = agreed_monthly_hours
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
    vacation_carryover: 0, // #383: Übertrag Urlaubstage (kein User-Feld, YearCarryover.vacation_days des Startjahres)
  });
  // #158: vorhandener Vortrag zum Startjahr — wird beim Speichern erhalten.
  const [hadCarryover, setHadCarryover] = useState(false);
  // #383: das Jahr, für das die Carryover-Felder erfolgreich geladen wurden.
  // Nur wenn es == carryoverYear ist, dürfen die Feldwerte beim Speichern (Edit)
  // in dieses Jahr geschrieben werden — sonst (Ladefehler oder noch laufender
  // Re-Fetch nach first_work_day-Wechsel) NICHT schreiben, um kein fremdes/
  // altes Jahr zu clobbern.
  const [loadedCarryoverYear, setLoadedCarryoverYear] = useState<number | null>(null);

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
        milog_working_time_account: editUser.milog_working_time_account ?? false, // #377
        agreed_monthly_hours: editUser.agreed_monthly_hours ?? null, // #377 Baustein 2a
        use_fixed_monthly_target: editUser.use_fixed_monthly_target ?? false, // #377 Baustein 2b
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
        vacation_carryover: 0,
      });
    }
  }, [editUser]);

  // #158/#383: das Carryover-Startjahr leitet sich aus dem LIVE-Formular ab
  // (nicht aus editUser), damit ein Ändern von „Erster Arbeitstag" das Jahr
  // mitzieht und die Felder für das neue Jahr neu geladen werden.
  // String-Slice statt new Date(...).getFullYear() — ein 'YYYY-MM-DD' würde als
  // UTC-Mitternacht geparst und in Zeitzonen hinter UTC aufs Vorjahr rutschen.
  const carryoverYear = formData.first_work_day
    ? parseInt(formData.first_work_day.slice(0, 4), 10)
    : new Date().getFullYear();

  // #158/#383: beim Bearbeiten den Anfangssaldo (Überstunden + Urlaub) des
  // Startjahres laden. Kein Row → Felder auf 0 zurücksetzen (M-C1: ein Wechsel
  // von first_work_day über eine Jahresgrenze darf NIE die Werte des alten
  // Jahres ins neue Jahr kopieren/clobbern — die Felder spiegeln immer das
  // aktuelle carryoverYear).
  useEffect(() => {
    if (!editUser) {
      setHadCarryover(false);
      setLoadedCarryoverYear(null);
      return;
    }
    let cancelled = false;
    // #383: solange (neu) geladen wird, gilt das Jahr als NICHT geladen — ein
    // Save in diesem Fenster darf die Feldwerte nicht in carryoverYear schreiben.
    setLoadedCarryoverYear(null);
    (async () => {
      try {
        const res = await apiClient.get<Array<{ year: number; overtime_hours: number; vacation_days: number }>>(
          `/admin/users/${editUser.id}/carryovers`,
        );
        if (cancelled) return;
        const row = res.data.find((c) => c.year === carryoverYear);
        setFormData((prev) => ({
          ...prev,
          overtime_carryover: row ? row.overtime_hours : 0,
          vacation_carryover: row ? row.vacation_days : 0, // #383
        }));
        setHadCarryover(!!row);
        setLoadedCarryoverYear(carryoverYear); // Felder repräsentieren jetzt carryoverYear
      } catch {
        /* Carryover optional — Fehler hier nicht blockierend */
        if (!cancelled) {
          setHadCarryover(false);
          setLoadedCarryoverYear(null); // unbekannter Stand → beim Speichern nicht schreiben
        }
      }
    })();
    return () => { cancelled = true; };
  }, [editUser, carryoverYear]);

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
      // #158/#383: overtime_carryover + vacation_carryover are NOT user fields —
      // they go to the carryover endpoint separately. Keep them out of the payload.
      const { overtime_carryover, vacation_carryover, ...userFields } = formData;
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
      // #383: write overtime_hours AND vacation_days straight from the (prefilled)
      // form. The write TARGET year is passed in — for the edit path it is the
      // year the fields were actually loaded for (loadedCarryoverYear), NOT the
      // live-form carryoverYear, so an in-flight re-fetch or a first_work_day
      // change can never write stale values into a DIFFERENT year's row.
      const writeCarryover = async (userId: string, year: number) => {
        try {
          await apiClient.put(`/admin/users/${userId}/carryovers/${year}`, {
            overtime_hours: overtime_carryover,
            vacation_days: vacation_carryover,
          });
        } catch (e: any) {
          // Primary save succeeded — surface a softer warning, don't abort.
          toast.error(getErrorMessage(e, 'Benutzer gespeichert, aber Anfangssaldo konnte nicht gesetzt werden'));
        }
      };

      if (editUser) {
        // When editing, send only the fields that can be updated (exclude password).
        // Task 5+7 (#431): ALL Soll-driving fields — weekly_hours, the daily-
        // schedule mode/values and work_days_per_week — are edit-only via the
        // Wochenstunden-Dialog now (with an effective date). The backend PUT
        // rejects every one of them outright (400): a direct edit here would
        // silently rewrite the historical fallback for the whole past, which
        // is exactly the bug this redesign fixes. NEVER add them back into
        // updateData.
        //
        // Task 7: the former I2 exception ("weekly_hours allowed via PUT when
        // use_daily_schedule") is gone. It only existed because the change
        // endpoint refused daily-schedule users until Task 6 gave them a
        // proper write path — that write path now covers them like everyone
        // else, so the direct field is excluded unconditionally.
        const {
          password, weekly_hours, use_daily_schedule, work_days_per_week,
          hours_monday, hours_tuesday, hours_wednesday, hours_thursday, hours_friday,
          ...rest
        } = payload;
        const updateData = rest;
        await apiClient.put(`/admin/users/${editUser.id}`, updateData);
        // #158/#383: nur schreiben, wenn (a) die Felder erfolgreich für EIN Jahr
        // geladen sind (loadedCarryoverYear !== null) — sonst würde ein Ladefehler
        // die Felder auf 0 clobbern — UND (b) ein Saldo gesetzt ist oder bereits
        // einer existierte. Ziel ist loadedCarryoverYear (das Jahr, das die Felder
        // repräsentieren), nie das ggf. voreilige live carryoverYear.
        if (
          loadedCarryoverYear !== null &&
          (overtime_carryover !== 0 || vacation_carryover !== 0 || hadCarryover)
        ) {
          await writeCarryover(editUser.id, loadedCarryoverYear);
        } else if (
          loadedCarryoverYear === null &&
          (overtime_carryover !== 0 || vacation_carryover !== 0)
        ) {
          // #383: der Save-Skip (loadedCarryoverYear===null) ist die richtige
          // Clobber-Schutz-Wahl — aber nicht schweigend: sonst glaubt der Admin,
          // der eingegebene Übertrag sei gespeichert (stiller Datenverlust genau
          // im Onboarding-Fall). Klar melden.
          toast.error('Benutzer gespeichert, aber der Übertrag/Anfangssaldo konnte nicht geladen werden und wurde NICHT gesetzt — bitte den Benutzer erneut öffnen und erneut speichern.');
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
        // Create: kein bestehender Row zu clobbern → live carryoverYear ist korrekt.
        if (newId && (overtime_carryover !== 0 || vacation_carryover !== 0)) {
          await writeCarryover(newId, carryoverYear);
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

  // Task 11 (#431): Anzeigetext der read-only Wochenstunden-Box beim
  // Bearbeiten. Bei individuellem Tagesplan der Tagesbreakdown + Summe
  // (`formatDayPlan`/`deHoursExact`, dieselben Helfer wie Dialog-Verlauf und
  // Berichte — Bildschirm sagt hier dasselbe wie Datei-Export/#415), sonst
  // nur die Summe. `displayWeeklyHours` (Release-Review 1.17.0, Fund 2) hält
  // nur die Summe frisch, nicht die einzelnen Tageswerte — nach einer
  // Dialog-Änderung am geöffneten Formular kann der Tagesbreakdown daher bis
  // zum nächsten Öffnen des Formulars den alten Stand zeigen, während die
  // Summe schon aktuell ist. Aus dem Scope dieser Task (nur UserForm.tsx)
  // bewusst nicht behoben — siehe Task-11-Bericht.
  const weeklyHoursTotal = deHoursExact(displayWeeklyHours ?? formData.weekly_hours);
  const dayPlanText = formatDayPlan([
    formData.hours_monday,
    formData.hours_tuesday,
    formData.hours_wednesday,
    formData.hours_thursday,
    formData.hours_friday,
  ]);
  const weeklyHoursDisplay = formData.use_daily_schedule && dayPlanText
    ? `${dayPlanText} = ${weeklyHoursTotal} h/Woche`
    : `${weeklyHoursTotal} h/Woche`;

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
            {editUser ? (
              // Task 6+11 (#431/#Wochenstunden-anpassen): reine Anzeige beim
              // Bearbeiten — für ALLE Mitarbeitenden, auch mit individuellem
              // Tagesplan (Task 6 gab ihnen einen vollwertigen Schreibweg über
              // denselben Dialog; ein direktes Feld hier würde still verworfen,
              // siehe Task 7). Bei Tagesplan zeigt die Box den Tagesbreakdown
              // (`weeklyHoursDisplay`), sonst nur die Summe.
              <div className="flex items-center gap-2">
                <div
                  id="f-weekly-hours"
                  className="flex-1 px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-900"
                >
                  {weeklyHoursDisplay}
                </div>
                <button
                  type="button"
                  onClick={() => onOpenHoursHistory?.(editUser)}
                  className="shrink-0 px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-primary hover:bg-primary/5 transition"
                >
                  Wochenstunden anpassen…
                </button>
              </div>
            ) : (
              // Beim Anlegen: normales Eingabefeld — es gibt noch keine Historie,
              // der Startwert muss direkt gesetzt werden können.
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
            )}
            {formData.use_fixed_monthly_target && (
              <p className="mt-1 text-xs text-gray-500">
                ℹ️ Feste Monatsarbeitszeit aktiv: Nur noch Basisangabe — das Monats-Soll
                kommt aus der vereinbarten Monatsarbeitszeit (siehe Arbeitszeitkonto unten),
                nicht mehr aus den Wochenstunden.
              </p>
            )}
          </div>
          <div>
            <label htmlFor="f-work-days" className="block text-sm font-medium text-gray-700 mb-1">Arbeitstage pro Woche</label>
            {editUser ? (
              // Task 11 (#431): historisiertes Feld — der Update-PUT lehnt es
              // wie weekly_hours ab (Task 7). Änderung nur noch über den
              // Wochenstunden-Dialog; bei Tagesplan leitet der Dialog den Wert
              // aus der Zahl der belegten Wochentage ab, das verschweigt der
              // Hinweis hier nicht.
              <div
                id="f-work-days"
                className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-900"
              >
                {formData.work_days_per_week}
              </div>
            ) : (
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
            )}
            <p className="text-xs text-gray-500 mt-1">
              {editUser
                ? (formData.use_daily_schedule
                  ? 'Wird aus der Zahl der belegten Wochentage im Tagesplan abgeleitet. Änderung über „Wochenstunden anpassen…" mit Wirkungsdatum.'
                  : 'Änderung über „Wochenstunden anpassen…" mit Wirkungsdatum.')
                : 'Anzahl der Arbeitstage pro Woche (1-7)'}
            </p>
          </div>
          <div>
            <label htmlFor="f-vacation" className="block text-sm font-medium text-gray-700 mb-1">Urlaubstage</label>
            <input
              id="f-vacation"
              type="number"
              value={formData.vacation_days}
              onChange={(e) => setFormData({ ...formData, vacation_days: parseFloat(e.target.value) || 0 })}
              required
              min="0"
              max="50"
              step="0.1"
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
                ({carryoverYear}).
                Negativ = Minusstunden.
              </p>
            </div>
          )}

          {/* #383: Übertrag Urlaubstage — gilt für ALLE MA (auch track_hours=false),
              daher NICHT hinter der Überstunden-track_hours-Gate. */}
          <div>
            <label htmlFor="f-vacation-carryover" className="block text-sm font-medium text-gray-700 mb-1">
              Übertrag Urlaubstage
            </label>
            <input
              id="f-vacation-carryover"
              type="number"
              step="0.01"
              min="-50"
              max="50"
              value={formData.vacation_carryover}
              onChange={(e) => setFormData({ ...formData, vacation_carryover: parseFloat(e.target.value) || 0 })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            />
            <p className="text-xs text-gray-500 mt-1">
              Alt-/Vorjahres-Resturlaub, der dem Urlaubsbudget des Startjahres
              ({carryoverYear})
              zugerechnet wird. Minus und Kommastellen möglich.
            </p>
          </div>

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

          {/* #377 Minijob / Arbeitszeitkonto (§2 Abs.2 MiLoG) */}
          <div className="md:col-span-2 p-3 bg-amber-50 rounded-lg border border-amber-200">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="milog_working_time_account"
                checked={formData.milog_working_time_account ?? false}
                onChange={(e) => setFormData({ ...formData, milog_working_time_account: e.target.checked })}
                className="w-4 h-4 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
              />
              <label htmlFor="milog_working_time_account" className="text-sm font-medium text-gray-700 cursor-pointer">
                Arbeitszeitkonto (§ 2 Abs. 2 MiLoG) – 50-%-Prüfung & 12-Monats-Ausgleichsfrist
              </label>
            </div>
            {formData.milog_working_time_account && (
              <div className="mt-2">
                {/* #377 Baustein 2a: vereinbarte Monatsarbeitszeit direkt eingeben */}
                <label htmlFor="f-agreed-monthly" className="block text-sm font-medium text-gray-700 mb-1">
                  Vereinbarte Monatsarbeitszeit (h){formData.use_fixed_monthly_target ? ' *' : ''}
                </label>
                <input
                  id="f-agreed-monthly"
                  type="number"
                  step="0.5"
                  min="0"
                  max="400"
                  placeholder={
                    formData.use_fixed_monthly_target
                      ? 'Pflichtfeld – festes Monats-Soll'
                      : `aus Wochenstunden ≈ ${(formData.weekly_hours * 13 / 3).toFixed(1)}`
                  }
                  value={formData.agreed_monthly_hours ?? ''}
                  onChange={(e) => setFormData({
                    ...formData,
                    // #377 2a: 0/negativ/leer = „keine Monatszahl vereinbart" → null
                    // (aus Wochenstunden ableiten). Backend akzeptiert nur > 0.
                    agreed_monthly_hours: parseFloat(e.target.value) > 0 ? parseFloat(e.target.value) : null,
                  })}
                  required={formData.use_fixed_monthly_target}
                  className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary ${
                    formData.use_fixed_monthly_target ? 'border-amber-400' : 'border-gray-300'
                  }`}
                />
                {(() => {
                  const monthly = formData.agreed_monthly_hours != null
                    ? formData.agreed_monthly_hours
                    : formData.weekly_hours * 13 / 3;
                  return (
                    <p className="mt-1 text-xs text-amber-800">
                      {minWage && typeof minWage.current === 'number'
                        ? `Aktueller Mindestlohn: ${minWage.current.toFixed(2)} €/h (seit ${new Date(minWage.since).toLocaleDateString('de-DE')}). `
                        : ''}
                      Leer = automatisch aus den Wochenstunden (≈ {(formData.weekly_hours * 13 / 3).toFixed(1)} h).
                      Vereinbarte Monatszeit {formData.agreed_monthly_hours != null ? '' : '≈ '}{monthly.toFixed(1)} h
                      → max. Konto ≈ {(monthly / 2).toFixed(1)} h/Monat (50 %, § 2 Abs. 2 MiLoG). Warnung ist weich
                      (nicht blockierend), sofern zur Mindestlohnhöhe vergütet. Keine Verdienst-/603-€-Prüfung.
                    </p>
                  );
                })()}

                {/* #377 Baustein 2b: festes Monats-Soll statt Wochenstunden×Arbeitstage */}
                <div className="mt-3 pt-3 border-t border-amber-200">
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="use_fixed_monthly_target"
                      checked={formData.use_fixed_monthly_target}
                      onChange={(e) => setFormData({ ...formData, use_fixed_monthly_target: e.target.checked })}
                      className="w-4 h-4 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
                    />
                    <label htmlFor="use_fixed_monthly_target" className="text-sm font-medium text-gray-700 cursor-pointer">
                      Feste Monatsarbeitszeit (Monats-Soll = vereinbarte Monatsarbeitszeit)
                    </label>
                  </div>
                  <p className="mt-1 text-xs text-amber-800">
                    Statt aus Wochenstunden/Arbeitstagen/Kalendertagen wird das Monats-Soll fest auf die oben
                    vereinbarte Monatsarbeitszeit gesetzt (Minijob-typisch bei schwankenden Einsatzplänen).
                    Erfordert Stundenzählung und ein gesetztes Feld oben. Wochenstunden bleiben als Basisangabe
                    bestehen, wirken sich in diesem Modus aber nicht mehr auf das Soll aus.
                  </p>
                </div>
              </div>
            )}
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
              {editUser ? (
                // Task 11 (#431): Haken UND Tagesstunden sind historisierte
                // Felder wie weekly_hours/work_days_per_week — der Update-PUT
                // verwirft sie ohnehin (Task 7), ein editierbarer Haken hier
                // hätte dem Admin also eine Wirkung vorgetäuscht, die nie
                // eintritt. Reine Anzeige, Änderung nur über den Dialog; der
                // Tagesbreakdown selbst steht schon oben in der
                // Wochenstunden-Box (`weeklyHoursDisplay`), hier nur der
                // Modus-Status, um ihn nicht zu duplizieren.
                <>
                  <p className="text-sm font-medium text-gray-700">
                    {formData.use_daily_schedule
                      ? (formData.use_fixed_monthly_target ? 'Geplante Anwesenheit aktiv' : 'Individuelle Tagesstunden aktiv')
                      : (formData.use_fixed_monthly_target ? 'Geplante Anwesenheit nicht hinterlegt' : 'Einheitliche Tagesstunden (kein individueller Tagesplan)')}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Änderung über „Wochenstunden anpassen…" mit Wirkungsdatum.
                  </p>
                </>
              ) : (
                <>
                  <div className="flex items-center space-x-2 mb-3">
                    <input
                      type="checkbox"
                      id="use_daily_schedule"
                      checked={formData.use_daily_schedule}
                      onChange={(e) => setFormData({ ...formData, use_daily_schedule: e.target.checked })}
                      className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary"
                    />
                    <label htmlFor="use_daily_schedule" className="text-sm font-medium text-gray-700 cursor-pointer">
                      {formData.use_fixed_monthly_target
                        ? 'Geplante Anwesenheit (für Feiertags-/Fehltags-Gutschrift, statt einheitlich '
                          + (formData.weekly_hours / formData.work_days_per_week).toFixed(1) + 'h/Tag)'
                        : `Individuelle Tagesstunden (statt einheitlich ${(formData.weekly_hours / formData.work_days_per_week).toFixed(1)}h/Tag)`}
                    </label>
                  </div>
                  {formData.use_fixed_monthly_target && !formData.use_daily_schedule && (
                    <p className="text-xs text-amber-600 mb-2">
                      Empfehlung bei fester Monatsarbeitszeit: hier die geplante Anwesenheit hinterlegen, damit
                      Feiertage/Fehltage korrekt gutgeschrieben werden (das Monats-Soll selbst bleibt fest).
                    </p>
                  )}
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
                </>
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
