import { useEffect, useState } from 'react';
import apiClient from '../../api/client';
import { Save, Plus, Trash2, Pencil, X, Check } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import LoadingSpinner from '../../components/LoadingSpinner';
import { getErrorMessage } from '../../utils/errorMessage';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';
import { useTypeColorsStore, pickTextColor } from '../../stores/typeColorsStore';
import AbsenceReasonsManager from '../../components/AbsenceReasonsManager';
import { useSystemStore } from '../../stores/systemStore';

// #371: Wochentag-Labels (Index 0=Mo … 6=So) für den Schichtplaner-Wochentag-Picker.
const SHIFT_WEEKDAY_LABELS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];

// #371: order-unabhängiger Vergleich zweier Wochentag-Listen (für den Dirty-Check).
function sameWeekdays(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  const sb = [...b].sort((x, y) => x - y);
  return [...a].sort((x, y) => x - y).every((v, i) => v === sb[i]);
}

// #157: Reihenfolge + Labels der konfigurierbaren Typ-Farben.
const COLOR_TYPE_ORDER: { key: string; label: string }[] = [
  { key: 'work', label: 'Arbeit (Anwesenheit)' },
  { key: 'training', label: 'Fortbildung' },
  { key: 'vacation', label: 'Urlaub' },
  { key: 'sick', label: 'Krank' },
  { key: 'overtime', label: 'Überstundenausgleich' },
  { key: 'other', label: 'Sonstiges' },
  { key: 'paid_leave', label: 'Bezahlte Freistellung' },
];

interface StatesResponse {
  states: string[];
  current_state: string;
}

interface SettingRow {
  key: string;
  value: string;
}

interface Holiday {
  id: string;
  date: string; // ISO YYYY-MM-DD
  name: string;
  year: number;
  is_custom: boolean;
}

// #146: configurable handling of 24./31.12.
type SpecialDayMode = 'working_day' | 'half_day' | 'free';

interface SpecialDaysConfig {
  special_day_dec24_mode: SpecialDayMode;
  special_day_dec24_counts_as_vacation: boolean;
  special_day_dec31_mode: SpecialDayMode;
  special_day_dec31_counts_as_vacation: boolean;
}

const SPECIAL_DAY_MODE_LABELS: Record<SpecialDayMode, string> = {
  working_day: 'Arbeitstag',
  half_day: 'Halbtag',
  free: 'Frei',
};

function formatGermanDate(iso: string): string {
  // iso is YYYY-MM-DD; render as DD.MM.YYYY without timezone surprises.
  const [y, m, d] = iso.split('-');
  if (!y || !m || !d) return iso;
  return `${d}.${m}.${y}`;
}

export default function Settings() {
  const toast = useToast();
  const minWage = useSystemStore((s) => s.getMinimumWage()); // #377
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [loading, setLoading] = useState(true);
  // L-4: getrennte Busy-Flags, damit das Speichern von Bundesland und
  // Urlaubsgenehmigung sich nicht gegenseitig deaktiviert.
  const [savingHolidayState, setSavingHolidayState] = useState(false);
  const [savingApproval, setSavingApproval] = useState(false);

  // Holiday state
  const [states, setStates] = useState<string[]>([]);
  const [selectedState, setSelectedState] = useState('');
  const [originalState, setOriginalState] = useState('');

  // Vacation approval
  const [approvalRequired, setApprovalRequired] = useState(false);
  const [originalApproval, setOriginalApproval] = useState(false);

  // #146: special days (24./31.12.)
  const [specialDays, setSpecialDays] = useState<SpecialDaysConfig | null>(null);
  const [originalSpecialDays, setOriginalSpecialDays] = useState<SpecialDaysConfig | null>(null);
  const [savingSpecialDays, setSavingSpecialDays] = useState(false);

  // #157 Typ-Farben
  const [typeColors, setTypeColors] = useState<Record<string, string> | null>(null);
  const [originalTypeColors, setOriginalTypeColors] = useState<Record<string, string> | null>(null);
  const [savingColors, setSavingColors] = useState(false);

  // #144 Break-exception approval (Pflicht-Pause war nicht möglich)
  const [breakApprovalRequired, setBreakApprovalRequired] = useState(false);
  const [originalBreakApproval, setOriginalBreakApproval] = useState(false);
  const [savingBreakApproval, setSavingBreakApproval] = useState(false);

  // Onboarding (Erst-Login-Willkommens-Tour) an/aus — Default an.
  const [onboardingEnabled, setOnboardingEnabled] = useState(true);
  const [originalOnboarding, setOriginalOnboarding] = useState(true);
  const [savingOnboarding, setSavingOnboarding] = useState(false);

  // #305 Schichtplanung-Feature an/aus — Default AUS, nur per Admin aktivierbar.
  const [shiftPlanningEnabled, setShiftPlanningEnabled] = useState(false);
  const [originalShiftPlanning, setOriginalShiftPlanning] = useState(false);
  const [savingShiftPlanning, setSavingShiftPlanning] = useState(false);
  // #371 Schichtplaner-Wochentage (0=Mo … 6=So) — Default Mo–Fr.
  const [shiftWeekdays, setShiftWeekdays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [originalShiftWeekdays, setOriginalShiftWeekdays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [savingShiftWeekdays, setSavingShiftWeekdays] = useState(false);
  // #314 Betriebsferien über Urlaub hinaus als Überstundenabbau (Default aus)
  const [closureOvertime, setClosureOvertime] = useState(false);
  const [originalClosureOvertime, setOriginalClosureOvertime] = useState(false);
  const [savingClosureOvertime, setSavingClosureOvertime] = useState(false);

  // #201 Soll-Fenster-Puffer (work_window_grace_minutes)
  const [graceMinutes, setGraceMinutes] = useState('15');
  const [originalGraceMinutes, setOriginalGraceMinutes] = useState('15');
  const [savingGrace, setSavingGrace] = useState(false);

  // #376 Kind-krank-Standardanspruch (child_sick_days_default)
  const [childSickDefault, setChildSickDefault] = useState('15');
  const [originalChildSickDefault, setOriginalChildSickDefault] = useState('15');
  const [savingChildSick, setSavingChildSick] = useState(false);

  // Custom holidays
  const currentYear = new Date().getFullYear();
  const [holidayYear, setHolidayYear] = useState(currentYear);
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [holidaysLoading, setHolidaysLoading] = useState(false);

  // New custom holiday form
  const [newName, setNewName] = useState('');
  const [newDate, setNewDate] = useState('');
  const [creating, setCreating] = useState(false);

  // Jahresende-Projektion der Überstunden.
  // Default an: Nur ein explizites "false" deaktiviert die Anzeige.
  const [showEmployeeYearEndProjection, setShowEmployeeYearEndProjection] =
    useState(true);

  const [
    originalShowEmployeeYearEndProjection,
    setOriginalShowEmployeeYearEndProjection,
  ] = useState(true);

  const [showAdminYearEndProjection, setShowAdminYearEndProjection] =
    useState(true);

  const [
    originalShowAdminYearEndProjection,
    setOriginalShowAdminYearEndProjection,
  ] = useState(true);

  const [savingYearEndProjection, setSavingYearEndProjection] =
    useState(false);

  // Inline edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editDate, setEditDate] = useState('');
  // Busy flag for custom-holiday edit/delete — separate from the Bundesland
  // `saving` so the three sections don't cross-disable each other.
  const [mutating, setMutating] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    loadHolidays(holidayYear);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [holidayYear]);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const [statesRes, settingsRes, specialDaysRes, colorsRes] = await Promise.all([
        apiClient.get<StatesResponse>('/holidays/states'),
        apiClient.get<SettingRow[]>('/admin/settings'),
        apiClient.get<SpecialDaysConfig>('/admin/settings/special-days'),
        apiClient.get<Record<string, string>>('/admin/settings/type-colors'),
      ]);

      // #157 type colours
      setTypeColors(colorsRes.data);
      setOriginalTypeColors(colorsRes.data);

      // Holiday states
      setStates(statesRes.data.states);
      setSelectedState(statesRes.data.current_state);
      setOriginalState(statesRes.data.current_state);

      // Vacation approval
      const approvalSetting = settingsRes.data.find((s) => s.key === 'vacation_approval_required');
      const val = approvalSetting?.value?.toLowerCase() === 'true';
      setApprovalRequired(val);
      setOriginalApproval(val);

      // #146: special days (24./31.12.)
      setSpecialDays(specialDaysRes.data);
      setOriginalSpecialDays(specialDaysRes.data);

      // #144 Break-exception approval
      const breakSetting = settingsRes.data.find((s) => s.key === 'break_exception_requires_approval');
      const breakVal = breakSetting?.value?.toLowerCase() === 'true';
      setBreakApprovalRequired(breakVal);
      setOriginalBreakApproval(breakVal);

      // Onboarding-Tour (Default an: nur ein explizites "false" deaktiviert)
      const obSetting = settingsRes.data.find((s) => s.key === 'onboarding_enabled');
      const obVal = obSetting?.value?.toLowerCase() !== 'false';
      setOnboardingEnabled(obVal);
      setOriginalOnboarding(obVal);

      // #305 Schichtplanung (Default aus: nur explizites "true" aktiviert)
      const spSetting = settingsRes.data.find((s) => s.key === 'shift_planning_enabled');
      const spVal = spSetting?.value?.toLowerCase() === 'true';
      setShiftPlanningEnabled(spVal);
      setOriginalShiftPlanning(spVal);

      // #371 Schichtplaner-Wochentage (CSV 0=Mo…6=So; Default Mo–Fr)
      const wdSetting = settingsRes.data.find((s) => s.key === 'shift_planning_weekdays');
      const wdParsed = wdSetting?.value
        ? wdSetting.value.split(',').map((n) => parseInt(n.trim(), 10)).filter((n) => n >= 0 && n <= 6)
        : [];
      const wdVal = wdParsed.length > 0 ? [...new Set(wdParsed)].sort((a, b) => a - b) : [0, 1, 2, 3, 4];
      setShiftWeekdays(wdVal);
      setOriginalShiftWeekdays(wdVal);

      // #314 Betriebsferien > Urlaub → Überstundenabbau (Default aus)
      const coSetting = settingsRes.data.find((s) => s.key === 'closure_overtime_after_vacation');
      const coVal = coSetting?.value?.toLowerCase() === 'true';
      setClosureOvertime(coVal);
      setOriginalClosureOvertime(coVal);

      // #201 Soll-Fenster-Puffer
      const graceSetting = settingsRes.data.find((s) => s.key === 'work_window_grace_minutes');
      const graceVal = graceSetting?.value ?? '15';
      setGraceMinutes(graceVal);
      setOriginalGraceMinutes(graceVal);

      // #376 Kind-krank-Standardanspruch
      const childSickSetting = settingsRes.data.find((s) => s.key === 'child_sick_days_default');
      const childSickVal = childSickSetting?.value ?? '15';
      setChildSickDefault(childSickVal);
      setOriginalChildSickDefault(childSickVal);
      
      const employeeYearEndSetting = settingsRes.data.find(
	  (s) => s.key === 'show_year_end_overtime_employee_dashboard',
      );

      const employeeYearEndValue =
        employeeYearEndSetting?.value?.toLowerCase() !== 'false';

      setShowEmployeeYearEndProjection(employeeYearEndValue);
      setOriginalShowEmployeeYearEndProjection(employeeYearEndValue);

      const adminYearEndSetting = settingsRes.data.find(
        (s) => s.key === 'show_year_end_overtime_admin_dashboard',
      );

      const adminYearEndValue =
        adminYearEndSetting?.value?.toLowerCase() !== 'false';

      setShowAdminYearEndProjection(adminYearEndValue);
      setOriginalShowAdminYearEndProjection(adminYearEndValue); 
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const loadHolidays = async (year: number) => {
    setHolidaysLoading(true);
    try {
      const res = await apiClient.get<Holiday[]>(`/holidays/?year=${year}`);
      setHolidays(res.data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setHolidaysLoading(false);
    }
  };

  const saveHolidayState = async () => {
    setSavingHolidayState(true);
    try {
      await apiClient.put('/admin/settings/holiday_state', { value: selectedState });
      setOriginalState(selectedState);
      toast.success('Bundesland aktualisiert. Feiertage wurden neu berechnet.');
      // Eigene Feiertage bleiben erhalten, Standard-Feiertage wurden ersetzt.
      await loadHolidays(holidayYear);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingHolidayState(false);
    }
  };

  const saveApproval = async () => {
    setSavingApproval(true);
    try {
      await apiClient.put('/admin/settings/vacation_approval_required', {
        value: String(approvalRequired),
      });
      setOriginalApproval(approvalRequired);
      toast.success('Urlaubsgenehmigung-Einstellung gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingApproval(false);
    }
  };

  const saveSpecialDays = async () => {
    if (!specialDays) return;
    setSavingSpecialDays(true);
    try {
      // Persist all four keys; backend validates mode + bool.
      await apiClient.put('/admin/settings/special_day_dec24_mode', {
        value: specialDays.special_day_dec24_mode,
      });
      await apiClient.put('/admin/settings/special_day_dec24_counts_as_vacation', {
        value: String(specialDays.special_day_dec24_counts_as_vacation),
      });
      await apiClient.put('/admin/settings/special_day_dec31_mode', {
        value: specialDays.special_day_dec31_mode,
      });
      await apiClient.put('/admin/settings/special_day_dec31_counts_as_vacation', {
        value: String(specialDays.special_day_dec31_counts_as_vacation),
      });
      setOriginalSpecialDays(specialDays);
      toast.success('Sondertage (24./31.12.) gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
      // Re-sync from server so the UI reflects which keys actually persisted
      // (the four PUTs are not atomic).
      void loadSettings();
    } finally {
      setSavingSpecialDays(false);
    }
  };

  const saveTypeColors = async () => {
    if (!typeColors) return;
    setSavingColors(true);
    try {
      const { data } = await apiClient.put<Record<string, string>>(
        '/admin/settings/type-colors',
        typeColors,
      );
      setTypeColors(data);
      setOriginalTypeColors(data);
      // Sofort app-weit übernehmen (Kalender/Übersichten/Erfassung).
      useTypeColorsStore.getState().setColors(data);
      toast.success('Farben gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingColors(false);
    }
  };

  const saveBreakApproval = async () => {
    setSavingBreakApproval(true);
    try {
      await apiClient.put('/admin/settings/break_exception_requires_approval', {
        value: String(breakApprovalRequired),
      });
      setOriginalBreakApproval(breakApprovalRequired);
      toast.success('Pflicht-Pause-Ausnahme-Einstellung gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingBreakApproval(false);
    }
  };

  const saveOnboarding = async () => {
    setSavingOnboarding(true);
    try {
      await apiClient.put('/admin/settings/onboarding_enabled', {
        value: String(onboardingEnabled),
      });
      setOriginalOnboarding(onboardingEnabled);
      // systemStore aktualisieren, damit das OnboardingModal sofort auf die neue
      // Einstellung reagiert (sonst erst nach Hard-Refresh sichtbar).
      await useSystemStore.getState().fetch();
      toast.success('Onboarding-Einstellung gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingOnboarding(false);
    }
  };

  const saveShiftPlanning = async () => {
    setSavingShiftPlanning(true);
    try {
      await apiClient.put('/admin/settings/shift_planning_enabled', {
        value: String(shiftPlanningEnabled),
      });
      setOriginalShiftPlanning(shiftPlanningEnabled);
      // systemStore aktualisieren, damit Navigation + Dashboard-Widget sofort
      // auf die neue Einstellung reagieren (sonst erst nach Hard-Refresh).
      await useSystemStore.getState().fetch();
      toast.success('Schichtplanungs-Einstellung gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingShiftPlanning(false);
    }
  };

  const toggleShiftWeekday = (wd: number) => {
    setShiftWeekdays((prev) =>
      prev.includes(wd) ? prev.filter((d) => d !== wd) : [...prev, wd].sort((a, b) => a - b),
    );
  };

  const saveShiftWeekdays = async () => {
    setSavingShiftWeekdays(true);
    try {
      await apiClient.put('/admin/settings/shift_planning_weekdays', {
        value: [...shiftWeekdays].sort((a, b) => a - b).join(','),
      });
      setOriginalShiftWeekdays(shiftWeekdays);
      // systemStore aktualisieren, damit die Wochenansicht sofort die neuen
      // Spalten zeigt (sonst erst nach Hard-Refresh).
      await useSystemStore.getState().fetch();
      toast.success('Schichtplaner-Wochentage gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingShiftWeekdays(false);
    }
  };

  const saveClosureOvertime = async () => {
    setSavingClosureOvertime(true);
    try {
      await apiClient.put('/admin/settings/closure_overtime_after_vacation', {
        value: String(closureOvertime),
      });
      setOriginalClosureOvertime(closureOvertime);
      toast.success('Betriebsferien-Einstellung gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingClosureOvertime(false);
    }
  };

  const saveGraceMinutes = async () => {
    setSavingGrace(true);
    try {
      await apiClient.put('/admin/settings/work_window_grace_minutes', {
        value: String(graceMinutes),
      });
      setOriginalGraceMinutes(graceMinutes);
      toast.success('Soll-Fenster-Puffer gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingGrace(false);
    }
  };

  const saveChildSickDefault = async () => {
    setSavingChildSick(true);
    try {
      await apiClient.put('/admin/settings/child_sick_days_default', {
        value: String(childSickDefault),
      });
      setOriginalChildSickDefault(childSickDefault);
      toast.success('Kind-krank-Standardanspruch gespeichert.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSavingChildSick(false);
    }
  };

const saveYearEndProjection = async () => {
  setSavingYearEndProjection(true);

  try {
    await Promise.all([
      apiClient.put(
        '/admin/settings/show_year_end_overtime_employee_dashboard',
        {
          value: String(showEmployeeYearEndProjection),
        },
      ),
      apiClient.put(
        '/admin/settings/show_year_end_overtime_admin_dashboard',
        {
          value: String(showAdminYearEndProjection),
        },
      ),
    ]);

    setOriginalShowEmployeeYearEndProjection(
      showEmployeeYearEndProjection,
    );
    setOriginalShowAdminYearEndProjection(
      showAdminYearEndProjection,
    );

    toast.success('Überstunden-Projektion gespeichert.');
  } catch (err) {
    toast.error(getErrorMessage(err));

    // Die beiden PUTs sind nicht atomar. Bei einem Teilfehler deshalb
    // den tatsächlich gespeicherten Stand erneut laden.
    void loadSettings();
  } finally {
    setSavingYearEndProjection(false);
  }
};

  const createHoliday = async () => {
    if (!newName.trim() || !newDate) {
      toast.error('Bitte Name und Datum angeben.');
      return;
    }
    setCreating(true);
    try {
      await apiClient.post('/holidays/', { name: newName.trim(), date: newDate });
      toast.success('Eigener Feiertag angelegt.');
      setNewName('');
      setNewDate('');
      const yearOfNew = Number(newDate.slice(0, 4));
      // Falls der neue Feiertag in ein anderes Jahr fällt, dorthin wechseln.
      if (yearOfNew && yearOfNew !== holidayYear) {
        setHolidayYear(yearOfNew);
      } else {
        await loadHolidays(holidayYear);
      }
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const startEdit = (h: Holiday) => {
    setEditingId(h.id);
    setEditName(h.name);
    setEditDate(h.date);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditName('');
    setEditDate('');
  };

  const saveEdit = async (id: string) => {
    if (!editName.trim() || !editDate) {
      toast.error('Bitte Name und Datum angeben.');
      return;
    }
    setMutating(true);
    try {
      await apiClient.put(`/holidays/${id}`, { name: editName.trim(), date: editDate });
      toast.success('Feiertag aktualisiert.');
      cancelEdit();
      const yearOfEdit = Number(editDate.slice(0, 4));
      if (yearOfEdit && yearOfEdit !== holidayYear) {
        setHolidayYear(yearOfEdit);
      } else {
        await loadHolidays(holidayYear);
      }
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setMutating(false);
    }
  };

  const deleteHoliday = (h: Holiday) => {
    confirm({
      title: 'Feiertag löschen',
      message: `Feiertag "${h.name}" (${formatGermanDate(h.date)}) wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        setMutating(true);
        try {
          await apiClient.delete(`/holidays/${h.id}`);
          toast.success('Feiertag gelöscht.');
          await loadHolidays(holidayYear);
        } catch (err) {
          toast.error(getErrorMessage(err));
        } finally {
          setMutating(false);
        }
      },
    });
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  const yearOptions = [currentYear - 1, currentYear, currentYear + 1, currentYear + 2];

  return (
    <div className="space-y-6">
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <h1 className="text-2xl font-bold text-gray-900">Einstellungen</h1>

      {/* #312 Eigene Abwesenheitsgründe */}
      <AbsenceReasonsManager />

      {/* Feiertage */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Feiertage</h2>
        <p className="text-sm text-gray-500 mb-4">
          Wählen Sie das Bundesland aus, dessen gesetzliche Feiertage verwendet werden sollen.
          Bei Änderung werden alle gesetzlichen Feiertage automatisch neu berechnet. Eigene
          Feiertage (siehe unten) bleiben dabei erhalten.
        </p>
        <div className="flex items-end gap-4">
          <div className="flex-1 max-w-sm">
            <label htmlFor="holiday-state" className="block text-sm font-medium text-gray-700 mb-1">
              Bundesland
            </label>
            <select
              id="holiday-state"
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
            >
              {states.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={saveHolidayState}
            disabled={savingHolidayState || selectedState === originalState}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>

      {/* Eigene Feiertage */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Eigene Feiertage</h2>
          <div>
            <label htmlFor="holiday-year" className="sr-only">
              Jahr
            </label>
            <select
              id="holiday-year"
              value={holidayYear}
              onChange={(e) => setHolidayYear(Number(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
            >
              {yearOptions.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Legen Sie lokale/regionale Feiertage an (z.B. Schützenfest, Karneval). Diese reduzieren
          die Soll-Zeit wie gesetzliche Feiertage. Gesetzliche Feiertage werden nur zur
          Information angezeigt und können nicht bearbeitet werden.
        </p>

        {/* Neuer Feiertag */}
        <div className="flex flex-wrap items-end gap-3 mb-4 p-4 bg-gray-50 rounded-lg">
          <div className="flex-1 min-w-[12rem]">
            <label htmlFor="new-holiday-name" className="block text-sm font-medium text-gray-700 mb-1">
              Name
            </label>
            <input
              id="new-holiday-name"
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="z.B. Schützenfest"
              maxLength={255}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
            />
          </div>
          <div>
            <label htmlFor="new-holiday-date" className="block text-sm font-medium text-gray-700 mb-1">
              Datum
            </label>
            <input
              id="new-holiday-date"
              type="date"
              value={newDate}
              onChange={(e) => setNewDate(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
            />
          </div>
          <button
            onClick={createHoliday}
            disabled={creating || !newName.trim() || !newDate}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Plus size={16} />
            Hinzufügen
          </button>
        </div>

        {/* Feiertags-Liste */}
        {holidaysLoading ? (
          <LoadingSpinner />
        ) : holidays.length === 0 ? (
          <p className="text-sm text-gray-500">Keine Feiertage für {holidayYear} gefunden.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200">
                  <th className="py-2 pr-4 font-medium">Datum</th>
                  <th className="py-2 pr-4 font-medium">Name</th>
                  <th className="py-2 pr-4 font-medium">Typ</th>
                  <th className="py-2 font-medium text-right">Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {holidays.map((h) => {
                  const isEditing = editingId === h.id;
                  return (
                    <tr key={h.id} className="border-b border-gray-100">
                      <td className="py-2 pr-4 whitespace-nowrap">
                        {isEditing ? (
                          <input
                            type="date"
                            value={editDate}
                            onChange={(e) => setEditDate(e.target.value)}
                            className="px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-primary focus:border-primary"
                          />
                        ) : (
                          formatGermanDate(h.date)
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        {isEditing ? (
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            maxLength={255}
                            className="w-full px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-primary focus:border-primary"
                          />
                        ) : (
                          h.name
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        {h.is_custom ? (
                          <span className="inline-block px-2 py-0.5 text-xs rounded-full bg-primary/10 text-primary">
                            Eigener
                          </span>
                        ) : (
                          <span className="inline-block px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-500">
                            Gesetzlich
                          </span>
                        )}
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">
                        {h.is_custom ? (
                          isEditing ? (
                            <div className="inline-flex gap-2">
                              <button
                                onClick={() => saveEdit(h.id)}
                                disabled={mutating}
                                title="Speichern"
                                className="p-1.5 text-green-600 hover:bg-green-50 rounded disabled:opacity-50"
                              >
                                <Check size={16} />
                              </button>
                              <button
                                onClick={cancelEdit}
                                disabled={mutating}
                                title="Abbrechen"
                                className="p-1.5 text-gray-500 hover:bg-gray-100 rounded disabled:opacity-50"
                              >
                                <X size={16} />
                              </button>
                            </div>
                          ) : (
                            <div className="inline-flex gap-2">
                              <button
                                onClick={() => startEdit(h)}
                                title="Bearbeiten"
                                className="p-1.5 text-gray-600 hover:bg-gray-100 rounded"
                              >
                                <Pencil size={16} />
                              </button>
                              <button
                                onClick={() => deleteHoliday(h)}
                                disabled={mutating}
                                title="Löschen"
                                className="p-1.5 text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          )
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Sondertage 24./31.12. (#146) */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Sondertage (24./31.12.)</h2>
        <p className="text-sm text-gray-500 mb-4">
          Legen Sie pro Tag fest, ob der 24.12. (Heiligabend) und der 31.12. (Silvester) ein
          ganzer Arbeitstag, ein Halbtag (halbe Sollzeit) oder frei sind. Bei „Frei" wählen Sie
          zusätzlich, ob der Tag als Urlaub (vom Urlaubskonto abgezogen) oder als bezahlte
          Freistellung (kein Abzug, wie ein Feiertag) gilt. Standard: Arbeitstag.
        </p>
        {specialDays && (
          <div className="space-y-4">
            {([
              { key: 'dec24' as const, label: '24.12. (Heiligabend)' },
              { key: 'dec31' as const, label: '31.12. (Silvester)' },
            ]).map(({ key, label }) => {
              const modeField = `special_day_${key}_mode` as keyof SpecialDaysConfig;
              const vacField = `special_day_${key}_counts_as_vacation` as keyof SpecialDaysConfig;
              const mode = specialDays[modeField] as SpecialDayMode;
              const countsAsVacation = specialDays[vacField] as boolean;
              return (
                <div key={key} className="flex flex-wrap items-end gap-4 p-4 bg-gray-50 rounded-lg">
                  <div className="min-w-[12rem]">
                    <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>
                  </div>
                  <div>
                    <label
                      htmlFor={`special-${key}-mode`}
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      Modus
                    </label>
                    <select
                      id={`special-${key}-mode`}
                      value={mode}
                      onChange={(e) =>
                        setSpecialDays({
                          ...specialDays,
                          [modeField]: e.target.value as SpecialDayMode,
                        })
                      }
                      className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
                    >
                      {(Object.keys(SPECIAL_DAY_MODE_LABELS) as SpecialDayMode[]).map((m) => (
                        <option key={m} value={m}>
                          {SPECIAL_DAY_MODE_LABELS[m]}
                        </option>
                      ))}
                    </select>
                  </div>
                  {mode === 'free' && (
                    <div>
                      <label
                        htmlFor={`special-${key}-vacation`}
                        className="block text-sm font-medium text-gray-700 mb-1"
                      >
                        Anrechnung
                      </label>
                      <select
                        id={`special-${key}-vacation`}
                        value={countsAsVacation ? 'vacation' : 'paid_leave'}
                        onChange={(e) =>
                          setSpecialDays({
                            ...specialDays,
                            [vacField]: e.target.value === 'vacation',
                          })
                        }
                        className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
                      >
                        <option value="vacation">Urlaub</option>
                        <option value="paid_leave">Bezahlte Freistellung</option>
                      </select>
                    </div>
                  )}
                </div>
              );
            })}
            <div>
              <button
                onClick={saveSpecialDays}
                disabled={
                  savingSpecialDays ||
                  JSON.stringify(specialDays) === JSON.stringify(originalSpecialDays)
                }
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Save size={16} />
                Speichern
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Urlaubsgenehmigung */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Urlaubsgenehmigung</h2>
        <p className="text-sm text-gray-500 mb-4">
          Wenn aktiviert, müssen Urlaubsanträge von einem Admin genehmigt werden, bevor sie wirksam
          werden.
        </p>
        <div className="flex items-center justify-between max-w-sm">
          <label htmlFor="approval-toggle" className="text-sm font-medium text-gray-700">
            Genehmigung erforderlich
          </label>
          <button
            id="approval-toggle"
            role="switch"
            aria-checked={approvalRequired}
            onClick={() => setApprovalRequired(!approvalRequired)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              approvalRequired ? 'bg-primary' : 'bg-gray-300'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                approvalRequired ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        <div className="mt-4">
          <button
            onClick={saveApproval}
            disabled={savingApproval || approvalRequired === originalApproval}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>

      {/* Pflicht-Pause-Ausnahme (#144) */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Pflicht-Pause-Ausnahme</h2>
        <p className="text-sm text-gray-500 mb-4">
          Konnte eine gesetzlich vorgeschriebene Pause (§4 ArbZG) nicht eingelegt werden, können
          Mitarbeiter den Eintrag mit einer Pflicht-Begründung trotzdem erfassen. Wenn diese Option
          aktiviert ist, wird ein solcher Eintrag erst nach Admin-Genehmigung wirksam (4-Augen-Prinzip);
          andernfalls wird er sofort gespeichert und die Abweichung als Warnung sowie im Änderungsprotokoll
          dokumentiert.
        </p>
        <div className="flex items-center justify-between max-w-sm">
          <label htmlFor="break-approval-toggle" className="text-sm font-medium text-gray-700">
            Genehmigung erforderlich
          </label>
          <button
            id="break-approval-toggle"
            role="switch"
            aria-checked={breakApprovalRequired}
            onClick={() => setBreakApprovalRequired(!breakApprovalRequired)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              breakApprovalRequired ? 'bg-primary' : 'bg-gray-300'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                breakApprovalRequired ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        <div className="mt-4">
          <button
            onClick={saveBreakApproval}
            disabled={savingBreakApproval || breakApprovalRequired === originalBreakApproval}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>

      {/* Onboarding / Willkommens-Tour */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Onboarding / Willkommens-Tour</h2>
        <p className="text-sm text-gray-500 mb-4">
          Beim ersten Login sehen neue Mitarbeitende und Admins eine kurze, rollenspezifische
          Willkommens-Tour mit den wichtigsten Bereichen. Deaktivieren Sie diese Option, wenn die
          Tour nicht angezeigt werden soll. Bereits gesehene Touren erscheinen ohnehin nicht erneut.
        </p>
        <div className="flex items-center justify-between max-w-sm">
          <label htmlFor="onboarding-toggle" className="text-sm font-medium text-gray-700">
            Willkommens-Tour anzeigen
          </label>
          <button
            id="onboarding-toggle"
            role="switch"
            aria-checked={onboardingEnabled}
            onClick={() => setOnboardingEnabled(!onboardingEnabled)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              onboardingEnabled ? 'bg-primary' : 'bg-gray-300'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                onboardingEnabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        <div className="mt-4">
          <button
            onClick={saveOnboarding}
            disabled={savingOnboarding || onboardingEnabled === originalOnboarding}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>

      {/* Schichtplanung (#305) — Default deaktiviert */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Schichtplanung</h2>
        <p className="text-sm text-gray-500 mb-4">
          Die Schichtplanung ist <strong>standardmäßig deaktiviert</strong>. Aktivieren Sie sie,
          um Wochen-Schichtpläne, Arbeitsplätze und Standorte anzulegen und Mitarbeitende auf
          Zeitslots zu verteilen. Solange das Feature aus ist, sehen weder Admins noch
          Mitarbeitende die Schichtplanung. Die Funktion ist ein reines Planungswerkzeug und
          verändert keine Zeiterfassungs-, Urlaubs- oder Überstundendaten.
        </p>
        <div className="flex items-center justify-between max-w-sm">
          <label htmlFor="shift-planning-toggle" className="text-sm font-medium text-gray-700">
            Schichtplanung aktivieren
          </label>
          <button
            id="shift-planning-toggle"
            role="switch"
            aria-checked={shiftPlanningEnabled}
            onClick={() => setShiftPlanningEnabled(!shiftPlanningEnabled)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              shiftPlanningEnabled ? 'bg-primary' : 'bg-gray-300'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                shiftPlanningEnabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        <div className="mt-4">
          <button
            onClick={saveShiftPlanning}
            disabled={savingShiftPlanning || shiftPlanningEnabled === originalShiftPlanning}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>

        {/* #371: konfigurierbare Wochentage — nur sichtbar wenn Schichtplanung an */}
        {shiftPlanningEnabled && (
          <div className="mt-6 pt-6 border-t border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 mb-1">Geplante Wochentage</h3>
            <p className="text-sm text-gray-500 mb-3">
              Wählen Sie, welche Wochentage im Schichtplaner angezeigt und geplant werden. Deaktivierte Tage
              erscheinen nicht in der Wochenansicht und werden bei der Auto-Generierung übersprungen.
              Standard: Montag–Freitag. Mindestens ein Tag muss aktiv bleiben.
            </p>
            <div className="flex flex-wrap gap-2 mb-4">
              {SHIFT_WEEKDAY_LABELS.map((label, i) => {
                const active = shiftWeekdays.includes(i);
                return (
                  <button
                    key={i}
                    type="button"
                    role="checkbox"
                    aria-checked={active}
                    aria-label={label}
                    onClick={() => toggleShiftWeekday(i)}
                    className={`rounded-full px-3 py-1 text-sm border transition-colors ${
                      active
                        ? 'bg-primary text-white border-primary'
                        : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
            <button
              onClick={saveShiftWeekdays}
              disabled={
                savingShiftWeekdays ||
                shiftWeekdays.length === 0 ||
                sameWeekdays(shiftWeekdays, originalShiftWeekdays)
              }
              className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Save size={16} />
              Wochentage speichern
            </button>
          </div>
        )}
      </div>

      {/* Betriebsferien über Urlaub hinaus (#314) — Default deaktiviert */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Betriebsferien &amp; Urlaub</h2>
        <p className="text-sm text-gray-500 mb-4">
          Wenn die Betriebsferien (Praxis geschlossen) <strong>länger als der Jahresurlaub</strong> einer
          Mitarbeiterin sind: Mit dieser Option werden die überzähligen Tage <strong>nicht</strong> als
          Minus-Urlaub gebucht, sondern als <strong>Überstundenabbau</strong> — erst wird der Urlaub
          aufgezehrt, dann die Überstunden (das Überstundenkonto darf dabei ins Minus gehen). Gilt nur für
          Betriebsferien, die als Urlaub zählen. <strong>Standardmäßig deaktiviert</strong> (dann entstehen
          wie bisher Minus-Urlaubstage).
        </p>
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4">
          <strong>Hinweis:</strong> Die Option wirkt beim <strong>Anlegen</strong> von Betriebsferien. Für
          <strong> bereits eingetragene</strong> Betriebsferien greift sie nicht automatisch — öffne sie einmal
          unter „Betriebsferien" und <strong>speichere sie erneut</strong>, dann werden die Tage neu berechnet
          (Urlaub zuerst, danach Überstundenabbau).
        </p>
        <div className="flex items-center justify-between max-w-sm">
          <label htmlFor="closure-overtime-toggle" className="text-sm font-medium text-gray-700">
            Überzählige Betriebsferien als Überstundenabbau
          </label>
          <button
            id="closure-overtime-toggle"
            role="switch"
            aria-checked={closureOvertime}
            onClick={() => setClosureOvertime(!closureOvertime)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              closureOvertime ? 'bg-primary' : 'bg-gray-300'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                closureOvertime ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        <div className="mt-4">
          <button
            onClick={saveClosureOvertime}
            disabled={savingClosureOvertime || closureOvertime === originalClosureOvertime}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>

      {/* Voraussichtlicher Überstundensaldo zum Jahresende */}
<div className="bg-white rounded-xl shadow-sm p-6">
  <h2 className="text-lg font-semibold text-gray-900 mb-4">
    Überstunden-Projektion zum Jahresende
  </h2>

  <p className="text-sm text-gray-500 mb-5">
    PraxisZeit kann den aktuellen Überstundensaldo um bereits
    eingetragenen künftigen Freizeitausgleich vermindern und daraus
    einen voraussichtlichen Saldo zum 31.12. anzeigen. Die Anzeige
    lässt sich für Mitarbeitende und Administratoren getrennt
    aktivieren.
  </p>

  <div className="space-y-5 max-w-xl">
    <div className="flex items-center justify-between gap-6">
      <div>
        <label
          htmlFor="employee-year-end-projection-toggle"
          className="text-sm font-medium text-gray-700"
        >
          Im Mitarbeiter-Dashboard anzeigen
        </label>

        <p className="text-xs text-gray-500 mt-1">
          Mitarbeitende sehen den voraussichtlichen Jahressaldo in
          ihrem eigenen Überstundenkonto.
        </p>
      </div>

      <button
        id="employee-year-end-projection-toggle"
        type="button"
        role="switch"
        aria-checked={showEmployeeYearEndProjection}
        onClick={() =>
          setShowEmployeeYearEndProjection(
            !showEmployeeYearEndProjection,
          )
        }
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          showEmployeeYearEndProjection
            ? 'bg-primary'
            : 'bg-gray-300'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            showEmployeeYearEndProjection
              ? 'translate-x-6'
              : 'translate-x-1'
          }`}
        />
      </button>
    </div>

    <div className="flex items-center justify-between gap-6 pt-5 border-t border-gray-100">
      <div>
        <label
          htmlFor="admin-year-end-projection-toggle"
          className="text-sm font-medium text-gray-700"
        >
          Im Admin-Dashboard anzeigen
        </label>

        <p className="text-xs text-gray-500 mt-1">
          Im Monats- und Wochenbericht erscheint die zusätzliche
          Spalte „Überstd. Jahresende“.
        </p>
      </div>

      <button
        id="admin-year-end-projection-toggle"
        type="button"
        role="switch"
        aria-checked={showAdminYearEndProjection}
        onClick={() =>
          setShowAdminYearEndProjection(
            !showAdminYearEndProjection,
          )
        }
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          showAdminYearEndProjection
            ? 'bg-primary'
            : 'bg-gray-300'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            showAdminYearEndProjection
              ? 'translate-x-6'
              : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  </div>

  <div className="mt-5">
    <button
      onClick={saveYearEndProjection}
      disabled={
        savingYearEndProjection ||
        (
          showEmployeeYearEndProjection ===
            originalShowEmployeeYearEndProjection &&
          showAdminYearEndProjection ===
            originalShowAdminYearEndProjection
        )
      }
      className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      <Save size={16} />
      Speichern
    </button>
  </div>
</div>




      {/* Soll-Fenster-Puffer (#201) */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Soll-Arbeitszeit-Fenster</h2>
        <p className="text-sm text-gray-500 mb-4">
          Anwesenheit vor oder nach dem Soll-Fenster zählt nur bis zu diesem Puffer zur Arbeitszeit.
          Stempel außerhalb des Puffers werden auf die Fenstergrenze gekürzt.
        </p>
        <div className="flex items-end gap-4">
          <div>
            <label
              htmlFor="grace-minutes"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Puffer für Soll-Arbeitszeit-Fenster (Min.)
            </label>
            <input
              id="grace-minutes"
              type="number"
              min="0"
              value={graceMinutes}
              onChange={(e) => setGraceMinutes(e.target.value)}
              className="w-28 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
            />
          </div>
          <button
            onClick={saveGraceMinutes}
            disabled={savingGrace || graceMinutes === originalGraceMinutes}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>

      {/* Kind-krank-Standardanspruch (#376 §45 SGB V) */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Kind-krank-Standardanspruch</h2>
        <p className="text-sm text-gray-500 mb-4">
          Standard-Jahresanspruch an Kind-krank-Tagen (§45 SGB V) für Mitarbeiter ohne
          individuellen Wert. Wird der Anspruch überschritten, erscheint beim Buchen ein
          Hinweis — die Abwesenheit wird trotzdem erfasst (nicht blockiert).
        </p>
        <div className="flex items-end gap-4">
          <div>
            <label
              htmlFor="child-sick-default"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Standard Kind-krank-Tage/Jahr
            </label>
            <input
              id="child-sick-default"
              type="number"
              min="0"
              value={childSickDefault}
              onChange={(e) => setChildSickDefault(e.target.value)}
              className="w-28 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
            />
          </div>
          <button
            onClick={saveChildSickDefault}
            disabled={savingChildSick || childSickDefault === originalChildSickDefault}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>

      {/* Gesetzlicher Mindestlohn (#377 §1 MiLoG) — reine Info */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Gesetzlicher Mindestlohn</h2>
        {minWage ? (
          <p className="text-sm text-gray-600">
            {/* #382: guard against a truthy-but-malformed minimum_wage (no numeric current). */}
            Aktuell <strong>{typeof minWage.current === 'number' ? minWage.current.toFixed(2) : '—'} €/h</strong> (seit{' '}
            {new Date(minWage.since).toLocaleDateString('de-DE')}).
            {minWage.next && typeof minWage.next.value === 'number' && (
              <> Ab {new Date(minWage.next.from).toLocaleDateString('de-DE')}:{' '}
                <strong>{minWage.next.value.toFixed(2)} €/h</strong>.</>
            )}
          </p>
        ) : (
          <p className="text-sm text-gray-500">Mindestlohn wird geladen…</p>
        )}
        <p className="text-xs text-gray-400 mt-2">
          Gesetzlich fixiert (§ 1 MiLoG). Relevant u. a. für Minijob-Arbeitszeitkonten
          (§ 2 Abs. 2 MiLoG) — pro Mitarbeiter:in im Benutzerformular aktivierbar.
        </p>
      </div>

      {/* Typ-Farben (#157) */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Farben</h2>
        <p className="text-sm text-gray-500 mb-4">
          Farbe pro Anwesenheits- und Abwesenheitstyp. Die Farben werden im
          Kalender, in den Übersichten und bei der Zeiterfassung verwendet.
        </p>
        {typeColors && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl">
            {COLOR_TYPE_ORDER.map(({ key, label }) => (
              <div key={key} className="flex items-center justify-between gap-3">
                <label htmlFor={`color-${key}`} className="text-sm font-medium text-gray-700">
                  {label}
                </label>
                <div className="flex items-center gap-2">
                  {/* Lesbarkeits-Vorschau: zeigt, ob die Schrift auf der Farbe lesbar bleibt */}
                  <span
                    className="inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold border border-gray-300"
                    style={{
                      backgroundColor: typeColors[key] ?? '#000000',
                      color: pickTextColor(typeColors[key] ?? '#000000'),
                    }}
                    aria-hidden="true"
                  >
                    Aa
                  </span>
                  <input
                    id={`color-${key}`}
                    type="color"
                    value={typeColors[key] ?? '#000000'}
                    onChange={(e) => setTypeColors({ ...typeColors, [key]: e.target.value })}
                    className="h-8 w-14 rounded border border-gray-300 cursor-pointer"
                    aria-label={`Farbe ${label}`}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="mt-4">
          <button
            onClick={saveTypeColors}
            disabled={
              savingColors ||
              JSON.stringify(typeColors) === JSON.stringify(originalTypeColors)
            }
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={16} />
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}
