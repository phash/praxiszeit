import { useEffect, useState, useRef } from 'react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../api/client';
import { Users, Clock, TrendingUp, X, Calendar, FileText, ChevronRight, Mail, Briefcase, ArrowUp, ArrowDown, Search, Plus, Edit2, Trash2, Save, ScrollText, BookCheck } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';
import MonthSelector from '../../components/MonthSelector';
import WeekSelector, { isoWeekMonday, weekLabel } from '../../components/WeekSelector';
import { getErrorMessage } from '../../utils/errorMessage';
import { formatHoursHM, parseHours, formatClockTime, formatWeeklyHoursChanges } from '../../utils/formatters';
import { submitWithBreakWaiver } from '../../utils/breakWaiverRetry';
import LoadingSpinner from '../../components/LoadingSpinner';
import UpdateBanner from '../../components/UpdateBanner';

interface EmployeeReport {
  user_id: string;
  first_name: string;
  last_name: string;
  weekly_hours: number;
  target_hours: number;
  actual_hours: number;
  balance: number;
  overtime_cumulative: number;
  vacation_used_hours: number;
  vacation_used_days: number;
  sick_hours: number;
  sick_days: number;
  exempt_from_arbzg?: boolean;
  track_hours?: boolean;
  // #415: Stundenänderungen INNERHALB des Berichtszeitraums. `weekly_hours` ist
  // der zu Zeitraumsbeginn gültige Wert — ohne diese Liste sähe der Admin eine
  // Wochenstundenzahl, die für den halben Monat gar nicht galt.
  weekly_hours_changes?: { effective_from: string; weekly_hours: number }[];
}

interface TimeEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string | null; // #382: null bei offenem (eingestempeltem) Eintrag — Deref nur über formatClockTime
  break_minutes: number;
  note?: string;
}

interface Absence {
  id: string;
  date: string;
  type: string;
  hours: number;
  note?: string;
}

interface YearlyAbsences {
  user_id: string;
  first_name: string;
  last_name: string;
  vacation_days: number;
  remaining_vacation_days: number;
  sick_days: number;
  training_days: number;
  other_days: number;
  overtime_comp_days?: number;
  overtime_year: number;
  total_days: number;
}

interface UserDetails {
  id: string;
  username: string;
  email: string | null;
  role: 'admin' | 'employee';
  vacation_days: number;
  track_hours: boolean;
}

export default function AdminDashboard() {
  const [report, setReport] = useState<EmployeeReport[]>([]);
  // #159: leitende MA (§18) verzerren den Schnitt — standardmäßig aus dem Ø ausschließen.
  const [includeExemptInAvg, setIncludeExemptInAvg] = useState(false);
  const [yearlyAbsences, setYearlyAbsences] = useState<YearlyAbsences[]>([]);
  const [loading, setLoading] = useState(true);
  const [yearlyLoading, setYearlyLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeReport | null>(null);
  // #329: the detail modal is always MONTH-scoped (entries/audit/absences by month).
  // In week view the clicked row holds WEEK figures, so the summary cards read this
  // month-scoped row instead → header, cards and entry list stay on one scope.
  const [detailSummary, setDetailSummary] = useState<EmployeeReport | null>(null);
  const [selectedUserDetails, setSelectedUserDetails] = useState<UserDetails | null>(null);
  const [employeeTimeEntries, setEmployeeTimeEntries] = useState<TimeEntry[]>([]);
  const [employeeAbsences, setEmployeeAbsences] = useState<Absence[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  // Admin edit state
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null);
  const [showNewEntryForm, setShowNewEntryForm] = useState(false);
  const [entryForm, setEntryForm] = useState({
    date: format(new Date(), 'yyyy-MM-dd'),
    start_time: '08:00',
    end_time: '17:00',
    break_minutes: 0,
    note: '',
    entry_type: 'work' as 'work' | 'sick' | 'training' | 'overtime' | 'other',
    absence_hours: 8,
  });
  const [auditLog, setAuditLog] = useState<any[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  // Sorting & Filtering for monthly report
  const [sortField, setSortField] = useState<keyof EmployeeReport | ''>('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [filterText, setFilterText] = useState('');
  // DSGVO Art. 9: Krankheitstage nur auf ausdrücklichen Opt-in zeigen — das löst
  // serverseitig ein Audit-Log aus (analog zum Reports-Export). Ohne Opt-in
  // liefert das Backend für Krank 0 / wird hier maskiert dargestellt.
  const [showHealthData, setShowHealthData] = useState(false);
  // #313: Soll-Basis — 'bis_heute' (bis zum letzten abgeschlossenen Arbeitstag,
  // kein Monatsanfangs-Minus) oder 'monatsende' (voller Monat).
  const [sollBasis, setSollBasis] = useState<'bis_heute' | 'monatsende'>('bis_heute');
  // #329: Monat ↔ Woche umschalten. Auswahl persistiert pro Browser-User.
  const [viewMode, setViewMode] = useState<'month' | 'week'>(
    () => (localStorage.getItem('adminDashboardViewMode') as 'month' | 'week') || 'month',
  );
  const [currentWeek, setCurrentWeek] = useState<string>(() => isoWeekMonday());

  const changeViewMode = (mode: 'month' | 'week') => {
    setViewMode(mode);
    localStorage.setItem('adminDashboardViewMode', mode);
  };

  // Bei Wochenwechsel auch den Monat mitführen, damit die Mitarbeiter-Detailansicht
  // (monatsbasiert) zum betrachteten Zeitraum passt.
  const handleWeekChange = (mondayIso: string) => {
    setCurrentWeek(mondayIso);
    setCurrentMonth(mondayIso.slice(0, 7));
  };

  useEffect(() => {
    fetchReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, currentMonth, currentWeek, showHealthData, sollBasis]);

  useEffect(() => {
    // Re-fetch des offenen Mitarbeiters bei Monatswechsel. selectedEmployee ist
    // bewusst KEINE Dependency: die Auswahl löst ihren eigenen Fetch aus, hier als
    // Dep ergänzt würde es doppelt fetchen. Der Effect erfasst das aktuelle
    // selectedEmployee (läuft nur bei currentMonth-Änderung).
    if (selectedEmployee) {
      fetchEmployeeDetails(selectedEmployee);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentMonth]);

  useEffect(() => {
    fetchYearlyAbsences();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentYear, showHealthData]);

  // C-2: Out-of-order-Schutz bei schnellem Monatswechsel (Last-Write-Wins).
  const reportSeq = useRef(0);
  const fetchReport = async () => {
    const seq = ++reportSeq.current;
    try {
      const hp = showHealthData ? '&include_health_data=true' : '';
      const url = viewMode === 'week'
        ? `/admin/reports/weekly?week_start=${currentWeek}${hp}&soll_basis=${sollBasis}`
        : `/admin/reports/monthly?month=${currentMonth}${hp}&soll_basis=${sollBasis}`;
      const response = await apiClient.get(url);
      if (seq !== reportSeq.current) return;
      // #382: guard against a non-array 200 body (auth/proxy edge) — the render
      // calls report.filter/.map unconditionally and would white-screen.
      setReport(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      if (seq === reportSeq.current) toast.error('Fehler beim Laden des Berichts');
    } finally {
      if (seq === reportSeq.current) setLoading(false);
    }
  };

  // C-2: Out-of-order-Schutz bei schnellem Jahreswechsel (Last-Write-Wins).
  const yearlySeq = useRef(0);
  const fetchYearlyAbsences = async () => {
    const seq = ++yearlySeq.current;
    try {
      const hp = showHealthData ? '&include_health_data=true' : '';
      const response = await apiClient.get(`/admin/reports/yearly-absences?year=${currentYear}${hp}`);
      if (seq !== yearlySeq.current) return;
      // #382: same guard — yearlyAbsences.filter/.map run unconditionally in render.
      setYearlyAbsences(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      if (seq === yearlySeq.current) toast.error('Fehler beim Laden der Jahresübersicht');
    } finally {
      if (seq === yearlySeq.current) setYearlyLoading(false);
    }
  };

  const handleYearClosing = () => {
    confirm({
      title: `Jahresabschluss ${currentYear}`,
      message: `Überstunden-Saldo und Resturlaub aller aktiven Mitarbeiter werden berechnet und als Übernahme in ${currentYear + 1} gespeichert. Bestehende Übernahmen für ${currentYear + 1} werden überschrieben.\n\nFortfahren?`,
      confirmLabel: 'Jahresabschluss erstellen',
      variant: 'warning',
      onConfirm: async () => {
        try {
          const res = await apiClient.post(`/admin/year-closing/${currentYear}`);
          const count = res.data.employees?.length || 0;
          toast.success(`Jahresabschluss ${currentYear} erstellt: ${count} Mitarbeiter übernommen nach ${currentYear + 1}`);
          fetchYearlyAbsences();
        } catch (error: any) {
          toast.error(getErrorMessage(error, 'Fehler beim Jahresabschluss'));
        }
      },
    });
  };

  const handleDeleteYearClosing = () => {
    confirm({
      title: `Jahresabschluss ${currentYear} löschen`,
      message: `Alle Übernahmen (Überstunden + Resturlaub) für ${currentYear + 1}, die durch den Jahresabschluss ${currentYear} erzeugt wurden, werden unwiderruflich gelöscht.\n\nDies betrifft alle Mitarbeiter. Manuelle Übernahmen für ${currentYear + 1} gehen ebenfalls verloren.\n\nWirklich löschen?`,
      confirmLabel: 'Jahresabschluss löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          const res = await apiClient.delete(`/admin/year-closing/${currentYear}`);
          const count = res.data.deleted_count || 0;
          toast.success(`Jahresabschluss ${currentYear} gelöscht: ${count} Übernahmen für ${currentYear + 1} entfernt`);
          fetchYearlyAbsences();
        } catch (error: any) {
          toast.error(getErrorMessage(error, 'Fehler beim Löschen des Jahresabschlusses'));
        }
      },
    });
  };

  // C-2: Out-of-order-Schutz. Wechselt der Admin bei offenem Detail-Modal schnell
  // den Monat, läuft fetchEmployeeDetails erneut, während der alte Lauf noch
  // pendet — die langsamere Antwort würde sonst die Detaildaten des falschen
  // Monats setzen. Last-Write-Wins über detailSeq.
  const detailSeq = useRef(0);
  const fetchEmployeeDetails = async (employee: EmployeeReport) => {
    const seq = ++detailSeq.current;
    setSelectedEmployee(employee);
    // Month mode: the clicked row IS the monthly row. Week mode: fetch the month
    // row so the modal's Soll/Ist/Saldo cards match its monthly header + entry list.
    setDetailSummary(viewMode === 'week' ? null : employee);
    setDetailLoading(true);
    try {
      const [year] = currentMonth.split('-');

      if (viewMode === 'week') {
        const hp = showHealthData ? '&include_health_data=true' : '';
        const monthly = await apiClient.get(
          `/admin/reports/monthly?month=${currentMonth}${hp}&soll_basis=${sollBasis}`,
        );
        if (seq !== detailSeq.current) return;
        setDetailSummary(
          monthly.data.find((r: EmployeeReport) => r.user_id === employee.user_id) ?? employee,
        );
      }

      // Fetch user details
      const userResponse = await apiClient.get(`/admin/users/${employee.user_id}`);
      if (seq !== detailSeq.current) return;
      setSelectedUserDetails(userResponse.data);

      // Fetch time entries
      const entriesResponse = await apiClient.get('/time-entries', {
        params: {
          user_id: employee.user_id,
          month: currentMonth
        }
      });
      if (seq !== detailSeq.current) return;
      setEmployeeTimeEntries(Array.isArray(entriesResponse.data) ? entriesResponse.data : []); // #382

      // Fetch absences
      const absencesResponse = await apiClient.get('/absences', {
        params: {
          user_id: employee.user_id,
          year: parseInt(year)
        }
      });
      if (seq !== detailSeq.current) return;
      setEmployeeAbsences(Array.isArray(absencesResponse.data) ? absencesResponse.data : []); // #382

      // Fetch audit log
      fetchAuditForUser(employee.user_id);
    } catch (error) {
      if (seq === detailSeq.current) toast.error('Fehler beim Laden der Mitarbeiterdaten');
    } finally {
      if (seq === detailSeq.current) setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setSelectedEmployee(null);
    setDetailSummary(null);
    setSelectedUserDetails(null);
    setEmployeeTimeEntries([]);
    setEmployeeAbsences([]);
    setEditingEntryId(null);
    setShowNewEntryForm(false);
    setAuditLog([]);
  };

  const fetchAuditForUser = async (userId: string) => {
    setAuditLoading(true);
    try {
      // #284: only real changes (create/update/delete) belong in the per-employee
      // change log — access/system events (e.g. DSGVO read-access markers written
      // on every open) otherwise piled up here, rendered as phantom "Gelöscht".
      const response = await apiClient.get(`/admin/audit-log?user_id=${userId}&month=${currentMonth}&changes_only=true`);
      setAuditLog(Array.isArray(response.data) ? response.data : []); // #382
    } catch (error) {
      toast.error('Fehler beim Laden des Audit-Logs');
    } finally {
      setAuditLoading(false);
    }
  };

  const handleAdminEditEntry = (entry: TimeEntry) => {
    setEditingEntryId(entry.id);
    setShowNewEntryForm(false);
    setEntryForm({
      date: entry.date,
      start_time: formatClockTime(entry.start_time, '08:00'),
      end_time: formatClockTime(entry.end_time, '17:00'),
      break_minutes: entry.break_minutes,
      note: entry.note || '',
      entry_type: 'work',
      absence_hours: 8,
    });
  };

  const handleAdminSaveEntry = async () => {
    if (!selectedEmployee) return;
    try {
      if (entryForm.entry_type === 'work') {
        // Normal time entry — #200: §4-Pausen-Ausnahme per Retry mit Begründung.
        const base = {
          date: entryForm.date,
          start_time: entryForm.start_time,
          end_time: entryForm.end_time,
          break_minutes: entryForm.break_minutes,
          note: entryForm.note,
        };
        await submitWithBreakWaiver(async (extra) => {
          if (editingEntryId) {
            await apiClient.put(`/admin/time-entries/${editingEntryId}`, { ...base, ...extra });
          } else {
            await apiClient.post(`/admin/users/${selectedEmployee.user_id}/time-entries`, { ...base, ...extra });
          }
        });
        toast.success(editingEntryId ? 'Eintrag aktualisiert' : 'Eintrag erstellt');
      } else {
        // Absence entry (sick, training, overtime comp, other)
        await apiClient.post('/absences', {
          user_id: selectedEmployee.user_id,
          date: entryForm.date,
          type: entryForm.entry_type,
          hours: entryForm.absence_hours,
          note: entryForm.note || null,
        });
        toast.success('Abwesenheit erstellt');
      }
      setEditingEntryId(null);
      setShowNewEntryForm(false);
      // Refresh entries
      const entriesResponse = await apiClient.get('/time-entries', {
        params: { user_id: selectedEmployee.user_id, month: currentMonth }
      });
      setEmployeeTimeEntries(Array.isArray(entriesResponse.data) ? entriesResponse.data : []); // #382
      // Refresh absences
      const absencesResponse = await apiClient.get('/absences', {
        params: { user_id: selectedEmployee.user_id, year: currentMonth.split('-')[0] }
      });
      setEmployeeAbsences(Array.isArray(absencesResponse.data) ? absencesResponse.data : []); // #382
      fetchAuditForUser(selectedEmployee.user_id);
      // C-2: Monatsbericht (Ist, Saldo, Urlaub/Krank) + Jahresübersicht aktualisieren,
      // damit die Zusammenfassung sofort die Mutation widerspiegelt.
      fetchReport();
      fetchYearlyAbsences();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    }
  };

  const handleAdminDeleteEntry = (entryId: string) => {
    confirm({
      title: 'Eintrag löschen',
      message: 'Möchten Sie diesen Zeiteintrag löschen? Die Änderung wird im Audit-Log protokolliert.',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/admin/time-entries/${entryId}`);
          toast.success('Eintrag gelöscht');
          if (selectedEmployee) {
            const entriesResponse = await apiClient.get('/time-entries', {
              params: { user_id: selectedEmployee.user_id, month: currentMonth }
            });
            setEmployeeTimeEntries(Array.isArray(entriesResponse.data) ? entriesResponse.data : []); // #382
            fetchAuditForUser(selectedEmployee.user_id);
          }
          // C-2: Monatsbericht + Jahresübersicht aktualisieren.
          fetchReport();
          fetchYearlyAbsences();
        } catch (error) {
          toast.error('Fehler beim Löschen');
        }
      },
    });
  };

  // Sorting function
  const handleSort = (field: keyof EmployeeReport) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  // Filter and sort report
  const filteredAndSortedReport = report
    .filter(emp => {
      if (!filterText) return true;
      const searchLower = filterText.toLowerCase();
      return (
        emp.first_name.toLowerCase().includes(searchLower) ||
        emp.last_name.toLowerCase().includes(searchLower)
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
      }

      return sortDirection === 'asc' ? comparison : -comparison;
    });

  const totalEmployees = report.length;
  // #159: Ø Saldo wahlweise ohne leitende Angestellte (Default) — verhindert
  // dass wenige MA mit vielen Stunden den Schnitt verzerren.
  // Finding 14 (Review 2026-07-14): track_hours=false-MA (#191, kein Soll/Ist)
  // haben immer Saldo 0 → IMMER aus dem Schnitt ausschließen (unabhängig vom
  // "Leitende MA einrechnen"-Toggle, der nur exempt_from_arbzg steuert), sonst
  // verwässern sie den Durchschnitt Richtung 0.
  const exemptCount = report.filter((emp) => emp.exempt_from_arbzg).length;
  const avgRows = report.filter(
    (emp) => emp.track_hours !== false && (includeExemptInAvg || !emp.exempt_from_arbzg)
  );
  const avgBalance = avgRows.length > 0
    ? avgRows.reduce((sum, emp) => sum + emp.balance, 0) / avgRows.length
    : 0;

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
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Admin-Dashboard</h1>

      <UpdateBanner />

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-600">Mitarbeitende</h3>
            <Users className="text-primary" size={24} />
          </div>
          <p className="text-3xl font-bold text-gray-900">{totalEmployees}</p>
        </div>

        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-600">Ø Saldo ({viewMode === 'week' ? 'Woche' : 'Monat'})</h3>
            <TrendingUp
              className={avgBalance >= 0 ? 'text-green-600' : 'text-red-600'}
              size={24}
            />
          </div>
          {avgRows.length === 0 ? (
            <p className="text-3xl font-bold text-gray-400" title="Keine Mitarbeitenden in der Berechnung">—</p>
          ) : (
            <p className={`text-3xl font-bold ${avgBalance >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {avgBalance >= 0 ? '+' : ''}
              {formatHoursHM(avgBalance)}
            </p>
          )}
          {exemptCount > 0 && (
            <>
              <p className="text-xs text-gray-400 mt-0.5">
                {includeExemptInAvg ? 'inkl. leitende MA' : 'ohne leitende MA'}
              </p>
              <label className="mt-2 flex items-center gap-2 text-xs text-gray-500 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeExemptInAvg}
                  onChange={(e) => setIncludeExemptInAvg(e.target.checked)}
                  className="w-3.5 h-3.5 rounded-sm border-gray-300 text-primary focus:ring-primary"
                />
                Leitende MA einrechnen ({exemptCount})
              </label>
            </>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-600">{viewMode === 'week' ? 'Woche' : 'Monat'}</h3>
            <Clock className="text-primary" size={24} />
          </div>
          <p className="text-xl font-bold text-gray-900">
            {viewMode === 'week'
              ? weekLabel(currentWeek)
              : format(new Date(currentMonth + '-01T00:00:00'), 'MMMM yyyy')}
          </p>
        </div>
      </div>

      {/* Period selector: Monat ↔ Woche umschalten (#329) */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <div
          className="inline-flex rounded-xl border border-gray-300 overflow-hidden"
          role="group"
          aria-label="Zeitraum-Ansicht"
        >
          <button
            onClick={() => changeViewMode('month')}
            aria-pressed={viewMode === 'month'}
            className={`px-4 py-2 text-sm font-medium transition ${
              viewMode === 'month' ? 'bg-primary text-white' : 'bg-white text-gray-700 hover:bg-muted'
            }`}
          >
            Monat
          </button>
          <button
            onClick={() => changeViewMode('week')}
            aria-pressed={viewMode === 'week'}
            className={`px-4 py-2 text-sm font-medium transition ${
              viewMode === 'week' ? 'bg-primary text-white' : 'bg-white text-gray-700 hover:bg-muted'
            }`}
          >
            Woche
          </button>
        </div>
        {viewMode === 'week' ? (
          <WeekSelector value={currentWeek} onChange={handleWeekChange} />
        ) : (
          <MonthSelector value={currentMonth} onChange={setCurrentMonth} />
        )}
      </div>

      {/* Filter Input */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4 mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={20} aria-hidden="true" />
          <label htmlFor="employee-search" className="sr-only">Mitarbeitende suchen</label>
          <input
            id="employee-search"
            type="text"
            placeholder="Suche nach Name..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>
      </div>

      {/* Employee Table */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between gap-4 flex-wrap">
          <h2 className="text-lg font-semibold">{viewMode === 'week' ? 'Wochenübersicht' : 'Monatsübersicht'}</h2>
          {/* #313: Soll-Basis umschalten — bis heute (kein Anfangs-Minus) oder voller Zeitraum. */}
          <label className="flex items-center gap-2 text-sm text-gray-600">
            Soll:
            <select
              value={sollBasis}
              onChange={(e) => setSollBasis(e.target.value as 'bis_heute' | 'monatsende')}
              className="rounded border-gray-300 text-sm py-1"
              title="Soll nur bis zum letzten abgeschlossenen Arbeitstag oder für den vollen Zeitraum"
            >
              <option value="bis_heute">bis heute</option>
              <option value="monatsende">{viewMode === 'week' ? 'volle Woche' : 'Monatsende'}</option>
            </select>
          </label>
          {/* DSGVO Art. 9: Krankheitstage nur auf ausdrücklichen Opt-in zeigen
              (löst serverseitig einen Audit-Log-Eintrag aus). */}
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={showHealthData}
              onChange={(e) => setShowHealthData(e.target.checked)}
              className="rounded border-gray-300"
            />
            Krankheitstage anzeigen <span className="text-gray-400">(Art. 9 DSGVO – wird protokolliert)</span>
          </label>
        </div>
        
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
                  onClick={() => handleSort('weekly_hours')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Wochenstd.</span>
                    {sortField === 'weekly_hours' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('target_hours')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Soll</span>
                    {sortField === 'target_hours' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('actual_hours')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Ist</span>
                    {sortField === 'actual_hours' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('balance')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Saldo</span>
                    {sortField === 'balance' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('overtime_cumulative')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Überstd. kum.</span>
                    {sortField === 'overtime_cumulative' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('vacation_used_days')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Urlaub (Tage)</span>
                    {sortField === 'vacation_used_days' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 transition"
                  onClick={() => handleSort('sick_days')}
                >
                  <div className="flex items-center space-x-1">
                    <span>Krank (Tage)</span>
                    {sortField === 'sick_days' && (
                      sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                    )}
                  </div>
                </th>
                <th className="px-6 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-6 py-8 text-center">
                    <LoadingSpinner text="Lade Daten..." />
                  </td>
                </tr>
              ) : filteredAndSortedReport.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-6 py-4 text-center text-gray-500">
                    {filterText ? 'Keine Mitarbeitenden gefunden' : 'Keine Daten verfügbar'}
                  </td>
                </tr>
              ) : (
                filteredAndSortedReport.map((emp) => (
                  <tr
                    key={emp.user_id}
                    className="hover:bg-gray-50 cursor-pointer focus:outline-hidden focus:bg-blue-50"
                    onClick={() => fetchEmployeeDetails(emp)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fetchEmployeeDetails(emp); } }}
                    tabIndex={0}
                    role="button"
                    aria-label={`Details für ${emp.last_name}, ${emp.first_name} anzeigen`}
                  >
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {emp.last_name}, {emp.first_name}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {emp.weekly_hours}
                      {formatWeeklyHoursChanges(emp.weekly_hours_changes) && (
                        <span
                          className="block text-xs text-amber-700"
                          title="Die Wochenstunden haben sich im Berichtszeitraum geändert"
                        >
                          {formatWeeklyHoursChanges(emp.weekly_hours_changes)}
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{formatHoursHM(emp.target_hours)}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{formatHoursHM(emp.actual_hours)}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={emp.balance >= 0 ? 'text-green-600' : 'text-red-600'}>
                        {emp.balance >= 0 ? '+' : ''}
                        {formatHoursHM(emp.balance)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={emp.overtime_cumulative >= 0 ? 'text-green-600' : 'text-red-600'}>
                        {emp.overtime_cumulative >= 0 ? '+' : ''}
                        {formatHoursHM(emp.overtime_cumulative)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{emp.vacation_used_days.toFixed(1)}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{showHealthData ? emp.sick_days.toFixed(1) : '—'}</td>
                    <td className="px-6 py-4 text-right">
                      <ChevronRight size={20} className="text-gray-400 inline" />
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
              <LoadingSpinner text="Lade Daten..." />
            </div>
          ) : filteredAndSortedReport.length === 0 ? (
            <div className="p-6 text-center text-gray-500">
              {filterText ? 'Keine Mitarbeitenden gefunden' : 'Keine Daten verfügbar'}
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {filteredAndSortedReport.map((emp) => (
                <div
                  key={emp.user_id}
                  className="p-4 hover:bg-gray-50 cursor-pointer transition focus:outline-hidden focus:bg-blue-50"
                  onClick={() => fetchEmployeeDetails(emp)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fetchEmployeeDetails(emp); } }}
                  tabIndex={0}
                  role="button"
                  aria-label={`Details für ${emp.last_name}, ${emp.first_name} anzeigen`}
                >
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                      <p className="font-semibold text-gray-900">
                        {emp.last_name}, {emp.first_name}
                      </p>
                      <p className="text-sm text-gray-500">{emp.weekly_hours} Std./Woche</p>
                      {formatWeeklyHoursChanges(emp.weekly_hours_changes) && (
                        <p className="text-xs text-amber-700">
                          {formatWeeklyHoursChanges(emp.weekly_hours_changes)}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className={`text-lg font-bold ${
                        emp.overtime_cumulative >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {emp.overtime_cumulative >= 0 ? '+' : ''}
                        {formatHoursHM(emp.overtime_cumulative)}
                      </span>
                      <ChevronRight size={20} className="text-gray-400" />
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div className="grid grid-cols-3 gap-3 text-sm mb-3">
                    <div>
                      <span className="text-gray-500 block">Soll</span>
                      <p className="font-medium">{formatHoursHM(emp.target_hours)}</p>
                    </div>
                    <div>
                      <span className="text-gray-500 block">Ist</span>
                      <p className="font-medium">{formatHoursHM(emp.actual_hours)}</p>
                    </div>
                    <div>
                      <span className="text-gray-500 block">Saldo</span>
                      <p className={`font-medium ${
                        emp.balance >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {emp.balance >= 0 ? '+' : ''}{formatHoursHM(emp.balance)}
                      </p>
                    </div>
                  </div>

                  {/* Absences */}
                  <div className="flex items-center justify-between text-sm pt-3 border-t border-gray-200">
                    <div className="flex items-center space-x-4">
                      <div>
                        <span className="text-gray-500">Urlaub:</span>
                        <span className="font-medium ml-1">{emp.vacation_used_days.toFixed(1)} Tage</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Krank:</span>
                        <span className="font-medium ml-1">{showHealthData ? `${emp.sick_days.toFixed(1)} Tage` : '—'}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Yearly Absences Overview */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-gray-900">Jahresübersicht</h2>
          <div className="flex items-center space-x-3">
            <label htmlFor="year-select" className="sr-only">Jahr auswählen</label>
            <input
              id="year-select"
              type="number"
              value={currentYear}
              onChange={(e) => setCurrentYear(parseInt(e.target.value))}
              min="2020"
              max="2030"
              aria-label="Jahr"
              className="px-4 py-2 border border-gray-300 rounded-lg"
            />
            <button
              onClick={handleYearClosing}
              className="bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
              title={`Jahresabschluss ${currentYear} erstellen`}
            >
              <BookCheck size={20} />
              <span className="hidden sm:inline">Jahresabschluss</span>
            </button>
            <button
              onClick={handleDeleteYearClosing}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
              title={`Jahresabschluss ${currentYear} löschen`}
            >
              <Trash2 size={20} />
              <span className="hidden sm:inline">Abschluss löschen</span>
            </button>
            <Link
              to="/admin/reports"
              className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
              title="Zu Berichte & Export"
            >
              <FileText size={20} />
              <span>Berichte</span>
            </Link>
          </div>
        </div>

        {/* Year-end vacation warning banner (Q4 only) */}
        {new Date().getMonth() >= 9 && currentYear === new Date().getFullYear() && (() => {
          const withRemaining = yearlyAbsences.filter(e => e.remaining_vacation_days > 0);
          return withRemaining.length > 0 ? (
            <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-xl">
              <p className="font-semibold text-amber-800 mb-2">
                ⚠️ Jahresend-Warnung: Offene Urlaubstage
              </p>
              <p className="text-sm text-amber-700 mb-3">
                Folgende Mitarbeiter haben noch offene Urlaubstage, die bis 31.03.{currentYear + 1} verfallen:
              </p>
              <div className="flex flex-wrap gap-2">
                {withRemaining.map(emp => (
                  <span key={emp.user_id} className="px-3 py-1 bg-amber-100 border border-amber-300 rounded-full text-sm font-medium text-amber-900">
                    {emp.first_name} {emp.last_name}: {emp.remaining_vacation_days.toFixed(1)} Tage
                  </span>
                ))}
              </div>
            </div>
          ) : null;
        })()}

        <div className="bg-white rounded-xl shadow-xs border border-gray-200 overflow-hidden">
          {/* Desktop Table */}
          <div className="hidden lg:block overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Urlaub</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-blue-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Resturlaub</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-blue-400"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Krank</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-red-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Fortbildung</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-orange-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>ÜStd.-Ausgl.</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-purple-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Überstunden</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-green-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Gesamt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {yearlyLoading ? (
                  <tr>
                    <td colSpan={8} className="px-6 py-8 text-center">
                      <LoadingSpinner text="Lade Daten..." />
                    </td>
                  </tr>
                ) : yearlyAbsences.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-6 py-4 text-center text-gray-500">
                      Keine Daten verfügbar
                    </td>
                  </tr>
                ) : (
                  yearlyAbsences.map((emp) => (
                    <tr key={emp.user_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm font-medium text-gray-900">
                        {emp.last_name}, {emp.first_name}
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {emp.vacation_days.toFixed(1)} Tage
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          emp.remaining_vacation_days > 5
                            ? 'bg-green-100 text-green-800'
                            : emp.remaining_vacation_days > 0
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {emp.remaining_vacation_days.toFixed(1)} Tage
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                          {showHealthData ? `${emp.sick_days.toFixed(1)} Tage` : '—'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                          {emp.training_days.toFixed(1)} Tage
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                          {emp.overtime_comp_days?.toFixed(1) ?? '0.0'} Tage
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          emp.overtime_year >= 0 ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
                          {emp.overtime_year >= 0 ? '+' : ''}{formatHoursHM(emp.overtime_year)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm font-bold text-gray-900">
                        {emp.total_days.toFixed(1)} Tage
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile Cards */}
          <div className="lg:hidden">
            {yearlyLoading ? (
              <div className="p-6 flex justify-center">
                <LoadingSpinner text="Lade Daten..." />
              </div>
            ) : yearlyAbsences.length === 0 ? (
              <div className="p-6 text-center text-gray-500">
                Keine Daten verfügbar
              </div>
            ) : (
              <div className="divide-y divide-gray-200">
                {yearlyAbsences.map((emp) => (
                  <div key={emp.user_id} className="p-4">
                    <div className="flex justify-between items-start mb-4">
                      <p className="font-semibold text-gray-900">
                        {emp.last_name}, {emp.first_name}
                      </p>
                      <span className="text-sm font-bold text-gray-900">
                        {emp.total_days.toFixed(1)} Tage
                      </span>
                    </div>

                    {/* Absence Badges */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="inline-block w-3 h-3 rounded-full bg-blue-500"></span>
                          <span className="text-sm text-gray-600">Urlaub</span>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {emp.vacation_days.toFixed(1)} Tage
                        </span>
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="inline-block w-3 h-3 rounded-full bg-blue-400"></span>
                          <span className="text-sm text-gray-600">Resturlaub</span>
                        </div>
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          emp.remaining_vacation_days > 5
                            ? 'bg-green-100 text-green-800'
                            : emp.remaining_vacation_days > 0
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {emp.remaining_vacation_days.toFixed(1)} Tage
                        </span>
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="inline-block w-3 h-3 rounded-full bg-red-500"></span>
                          <span className="text-sm text-gray-600">Krank</span>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                          {showHealthData ? `${emp.sick_days.toFixed(1)} Tage` : '—'}
                        </span>
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="inline-block w-3 h-3 rounded-full bg-orange-500"></span>
                          <span className="text-sm text-gray-600">Fortbildung</span>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                          {emp.training_days.toFixed(1)} Tage
                        </span>
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="inline-block w-3 h-3 rounded-full bg-purple-500"></span>
                          <span className="text-sm text-gray-600">ÜStd.-Ausgleich</span>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                          {emp.overtime_comp_days?.toFixed(1) ?? '0.0'} Tage
                        </span>
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className={`inline-block w-3 h-3 rounded-full ${
                            emp.overtime_year >= 0 ? 'bg-green-500' : 'bg-red-500'
                          }`}></span>
                          <span className="text-sm text-gray-600">Überstunden</span>
                        </div>
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          emp.overtime_year >= 0 ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
                          {emp.overtime_year >= 0 ? '+' : ''}{formatHoursHM(emp.overtime_year)}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Employee Detail Modal */}
      {selectedEmployee && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
          onClick={closeDetail}
        >
          <FocusTrap
            focusTrapOptions={{
              allowOutsideClick: true,
              escapeDeactivates: true,
              onDeactivate: closeDetail,
            }}
          >
            <div 
              role="dialog"
              aria-modal="true"
              aria-labelledby="employee-modal-title"
              className="bg-white rounded-xl shadow-2xl max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-primary text-white">
                <div>
                  <h2 id="employee-modal-title" className="text-2xl font-bold">
                    {selectedEmployee.last_name}, {selectedEmployee.first_name}
                  </h2>
                  <p className="text-sm opacity-90">
                    {format(new Date(currentMonth + '-01T00:00:00'), 'MMMM yyyy')} - Details
                  </p>
                </div>
                <button
                  ref={closeButtonRef}
                  onClick={closeDetail}
                  className="hover:bg-white/20 rounded-lg p-2 transition"
                  aria-label={`Details für ${selectedEmployee.first_name} ${selectedEmployee.last_name} schließen`}
                >
                  <X size={24} />
                </button>
              </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {detailLoading ? (
                <div className="py-8 flex justify-center">
                  <LoadingSpinner text="Lade Details..." />
                </div>
              ) : (
                <div className="space-y-6">
                  {/* User Info Section */}
                  {selectedUserDetails && (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                      <h3 className="font-semibold text-gray-900 mb-3 flex items-center space-x-2">
                        <Briefcase size={18} className="text-primary" />
                        <span>Benutzerinformationen</span>
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
                        <div>
                          <p className="text-gray-500 mb-1">Benutzer-ID</p>
                          <p className="font-mono text-gray-900">{selectedUserDetails.id}</p>
                        </div>
                        <div>
                          <p className="text-gray-500 mb-1">Benutzername</p>
                          <p className="text-gray-900">{selectedUserDetails.username}</p>
                        </div>
                        {selectedUserDetails.email && (
                        <div>
                          <p className="text-gray-500 mb-1">E-Mail</p>
                          <p className="text-gray-900 flex items-center space-x-1">
                            <Mail size={14} className="text-gray-400" />
                            <span>{selectedUserDetails.email}</span>
                          </p>
                        </div>
                        )}
                        <div>
                          <p className="text-gray-500 mb-1">Rolle</p>
                          <p className="text-gray-900">
                            {selectedUserDetails.role === 'admin' ? 'Administrator' : 'Mitarbeiter:in'}
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-500 mb-1">Wochenstunden</p>
                          <p className="text-gray-900">{selectedEmployee.weekly_hours} Std.</p>
                          {formatWeeklyHoursChanges(selectedEmployee.weekly_hours_changes) && (
                            <p className="text-xs text-amber-700 mt-0.5">
                              {formatWeeklyHoursChanges(selectedEmployee.weekly_hours_changes)}
                            </p>
                          )}
                        </div>
                        <div>
                          <p className="text-gray-500 mb-1">Urlaubstage (Budget)</p>
                          <p className="text-gray-900">{selectedUserDetails.vacation_days} Tage</p>
                        </div>
                        <div>
                          <p className="text-gray-500 mb-1">Zeiterfassung</p>
                          <p className={`font-medium ${selectedUserDetails.track_hours ? 'text-green-600' : 'text-gray-400'}`}>
                            {selectedUserDetails.track_hours ? 'Aktiv' : 'Deaktiviert'}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Summary Cards — month-scoped (matches the modal's monthly header
                      + entry list); #329: detailSummary holds the monthly row in week view. */}
                  {(() => {
                    const summary = detailSummary ?? selectedEmployee;
                    return (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-gray-50 rounded-lg p-4">
                      <p className="text-xs text-gray-500 mb-1">Soll</p>
                      <p className="text-xl font-bold">{formatHoursHM(summary.target_hours)}</p>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-4">
                      <p className="text-xs text-gray-500 mb-1">Ist</p>
                      <p className="text-xl font-bold">{formatHoursHM(summary.actual_hours)}</p>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-4">
                      <p className="text-xs text-gray-500 mb-1">Saldo</p>
                      <p
                        className={`text-xl font-bold ${
                          summary.balance >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {summary.balance >= 0 ? '+' : ''}
                        {formatHoursHM(summary.balance)}
                      </p>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-4">
                      <p className="text-xs text-gray-500 mb-1">Überstunden kum.</p>
                      <p
                        className={`text-xl font-bold ${
                          summary.overtime_cumulative >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {summary.overtime_cumulative >= 0 ? '+' : ''}
                        {formatHoursHM(summary.overtime_cumulative)}
                      </p>
                    </div>
                  </div>
                    );
                  })()}

                  {/* Time Entries */}
                  <div className="bg-white border border-gray-200 rounded-lg">
                    <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Clock size={20} className="text-primary" />
                        <h3 className="font-semibold">Zeiteinträge ({employeeTimeEntries.length})</h3>
                      </div>
                      <button
                        onClick={() => {
                          setShowNewEntryForm(true);
                          setEditingEntryId(null);
                          setEntryForm({
                            date: format(new Date(), 'yyyy-MM-dd'),
                            start_time: '08:00',
                            end_time: '17:00',
                            break_minutes: 0,
                            note: '',
                            entry_type: 'work',
                            absence_hours: 8,
                          });
                        }}
                        className="text-sm bg-primary hover:bg-primary-dark text-white px-3 py-1 rounded-lg flex items-center space-x-1 transition"
                      >
                        <Plus size={14} />
                        <span>Neuer Eintrag</span>
                      </button>
                    </div>

                    {/* Inline Edit/Create Form */}
                    {(editingEntryId || showNewEntryForm) && (
                      <div className="px-4 py-3 bg-blue-50 border-b border-blue-200">
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-sm">
                          {!editingEntryId && (
                            <select
                              value={entryForm.entry_type}
                              onChange={(e) => setEntryForm({ ...entryForm, entry_type: e.target.value as any })}
                              aria-label="Eintragstyp"
                              className="px-2 py-1 border border-gray-300 rounded-sm text-sm col-span-2 md:col-span-1"
                            >
                              <option value="work">Arbeit</option>
                              <option value="sick">Krank</option>
                              <option value="training">Fortbildung</option>
                              <option value="overtime">Überstundenausgleich</option>
                              <option value="other">Sonstiges</option>
                            </select>
                          )}
                          <input
                            type="date"
                            value={entryForm.date}
                            onChange={(e) => setEntryForm({ ...entryForm, date: e.target.value })}
                            aria-label="Datum"
                            className="px-2 py-1 border border-gray-300 rounded-sm text-sm"
                          />
                          {(entryForm.entry_type === 'work' || editingEntryId) ? (
                            <>
                              <input
                                type="time"
                                value={entryForm.start_time}
                                onChange={(e) => setEntryForm({ ...entryForm, start_time: e.target.value })}
                                aria-label="Von (Uhrzeit)"
                                className="px-2 py-1 border border-gray-300 rounded-sm text-sm"
                              />
                              <input
                                type="time"
                                value={entryForm.end_time}
                                onChange={(e) => setEntryForm({ ...entryForm, end_time: e.target.value })}
                                aria-label="Bis (Uhrzeit)"
                                className="px-2 py-1 border border-gray-300 rounded-sm text-sm"
                              />
                              <input
                                type="number"
                                min="0"
                                value={entryForm.break_minutes}
                                onChange={(e) => setEntryForm({ ...entryForm, break_minutes: parseInt(e.target.value) || 0 })}
                                placeholder="Pause (Min.)"
                                aria-label="Pause in Minuten"
                                className="px-2 py-1 border border-gray-300 rounded-sm text-sm"
                              />
                            </>
                          ) : (
                            <input
                              type="number"
                              step="0.5"
                              min="0"
                              max="24"
                              value={entryForm.absence_hours}
                              onChange={(e) => setEntryForm({ ...entryForm, absence_hours: parseHours(e.target.value) })}
                              placeholder="Stunden"
                              aria-label="Stunden"
                              className="px-2 py-1 border border-gray-300 rounded-sm text-sm"
                            />
                          )}
                          <input
                            type="text"
                            value={entryForm.note}
                            onChange={(e) => setEntryForm({ ...entryForm, note: e.target.value })}
                            placeholder="Notiz"
                            aria-label="Notiz"
                            className="px-2 py-1 border border-gray-300 rounded-sm text-sm"
                          />
                        </div>
                        <div className="flex space-x-2 mt-2">
                          <button
                            onClick={handleAdminSaveEntry}
                            className="text-sm bg-primary hover:bg-primary-dark text-white px-3 py-1 rounded-sm flex items-center space-x-1"
                          >
                            <Save size={14} />
                            <span>Speichern</span>
                          </button>
                          <button
                            onClick={() => { setEditingEntryId(null); setShowNewEntryForm(false); }}
                            className="text-sm bg-gray-200 hover:bg-gray-300 text-gray-700 px-3 py-1 rounded-sm"
                          >
                            Abbrechen
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="max-h-60 overflow-y-auto">
                      {employeeTimeEntries.length === 0 ? (
                        <p className="px-4 py-3 text-sm text-gray-500">Keine Zeiteinträge vorhanden</p>
                      ) : (
                        <table className="w-full">
                          <thead className="bg-gray-50 sticky top-0">
                            <tr>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Datum</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Von</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Bis</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Pause</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Notiz</th>
                              <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">Aktionen</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-200">
                            {employeeTimeEntries.map((entry) => (
                              <tr key={entry.id} className="hover:bg-gray-50">
                                <td className="px-4 py-2 text-sm">{format(new Date(entry.date), 'dd.MM.yyyy')}</td>
                                <td className="px-4 py-2 text-sm">{formatClockTime(entry.start_time)}</td>
                                <td className="px-4 py-2 text-sm">{formatClockTime(entry.end_time, 'offen')}</td>
                                <td className="px-4 py-2 text-sm">{entry.break_minutes} min</td>
                                <td className="px-4 py-2 text-sm text-gray-500">{entry.note || '-'}</td>
                                <td className="px-4 py-2 text-right text-sm space-x-1">
                                  <button
                                    onClick={() => handleAdminEditEntry(entry)}
                                    className="text-primary hover:text-primary-dark p-1 rounded-sm"
                                    aria-label={`Eintrag vom ${format(new Date(entry.date), 'dd.MM.yyyy')} bearbeiten`}
                                  >
                                    <Edit2 size={14} aria-hidden="true" />
                                  </button>
                                  <button
                                    onClick={() => handleAdminDeleteEntry(entry.id)}
                                    className="text-red-600 hover:text-red-800 p-1 rounded-sm"
                                    aria-label={`Eintrag vom ${format(new Date(entry.date), 'dd.MM.yyyy')} löschen`}
                                  >
                                    <Trash2 size={14} aria-hidden="true" />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>

                  {/* Absences */}
                  <div className="bg-white border border-gray-200 rounded-lg">
                    <div className="px-4 py-3 border-b border-gray-200 flex items-center space-x-2">
                      <Calendar size={20} className="text-primary" />
                      <h3 className="font-semibold">Abwesenheiten ({employeeAbsences.length})</h3>
                    </div>
                    <div className="max-h-60 overflow-y-auto">
                      {employeeAbsences.length === 0 ? (
                        <p className="px-4 py-3 text-sm text-gray-500">Keine Abwesenheiten vorhanden</p>
                      ) : (
                        <table className="w-full">
                          <thead className="bg-gray-50 sticky top-0">
                            <tr>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Datum</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Typ</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Stunden</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Notiz</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-200">
                            {employeeAbsences.map((absence) => (
                              <tr key={absence.id}>
                                <td className="px-4 py-2 text-sm">{format(new Date(absence.date), 'dd.MM.yyyy')}</td>
                                <td className="px-4 py-2 text-sm">
                                  <span
                                    className={`px-2 py-1 rounded text-xs font-medium ${
                                      absence.type === 'vacation'
                                        ? 'bg-blue-100 text-blue-800'
                                        : absence.type === 'sick'
                                        ? 'bg-red-100 text-red-800'
                                        : absence.type === 'training'
                                        ? 'bg-orange-100 text-orange-800'
                                        : absence.type === 'overtime'
                                        ? 'bg-purple-100 text-purple-800'
                                        : 'bg-gray-100 text-gray-800'
                                    }`}
                                  >
                                    {absence.type === 'vacation'
                                      ? 'Urlaub'
                                      : absence.type === 'sick'
                                      ? 'Krank'
                                      : absence.type === 'training'
                                      ? 'Fortbildung (außer Haus)'
                                      : absence.type === 'overtime'
                                      ? 'Überstundenausgleich'
                                      : 'Sonstiges'}
                                  </span>
                                </td>
                                <td className="px-4 py-2 text-sm">{formatHoursHM(absence.hours)} h</td>
                                <td className="px-4 py-2 text-sm text-gray-500">{absence.note || '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>

                  {/* Audit Log for this employee */}
                  <div className="bg-white border border-gray-200 rounded-lg">
                    <div className="px-4 py-3 border-b border-gray-200 flex items-center space-x-2">
                      <ScrollText size={20} className="text-primary" />
                      <h3 className="font-semibold">Änderungsprotokoll ({auditLog.length})</h3>
                    </div>
                    <div className="max-h-48 overflow-y-auto">
                      {auditLoading ? (
                        <p className="px-4 py-3 text-sm text-gray-500">Lade...</p>
                      ) : auditLog.length === 0 ? (
                        <p className="px-4 py-3 text-sm text-gray-500">Keine Änderungen protokolliert</p>
                      ) : (
                        <div className="divide-y divide-gray-200">
                          {auditLog.map((log: any) => (
                            <div key={log.id} className="px-4 py-2 text-xs">
                              <div className="flex items-center justify-between">
                                <span className={`px-2 py-0.5 rounded font-medium ${
                                  log.action === 'create' ? 'bg-green-100 text-green-800' :
                                  log.action === 'update' ? 'bg-blue-100 text-blue-800' :
                                  log.action === 'delete' ? 'bg-red-100 text-red-800' :
                                  'bg-gray-100 text-gray-700'
                                }`}>
                                  {log.action === 'create' ? 'Erstellt' : log.action === 'update' ? 'Geändert' : log.action === 'delete' ? 'Gelöscht' : log.action}
                                </span>
                                <span className="text-gray-500">
                                  {format(new Date(log.created_at), 'dd.MM. HH:mm')} | {log.changed_by_first_name} {log.changed_by_last_name}
                                  {log.source === 'change_request' && ' (Antrag)'}
                                </span>
                              </div>
                              {log.old_date && (
                                <p className="text-gray-400 mt-1">Alt: {log.old_date} {log.old_start_time?.substring(0, 5)}-{log.old_end_time?.substring(0, 5)} P:{log.old_break_minutes}min</p>
                              )}
                              {log.new_date && (
                                <p className="text-gray-600">Neu: {log.new_date} {log.new_start_time?.substring(0, 5)}-{log.new_end_time?.substring(0, 5)} P:{log.new_break_minutes}min</p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end">
              <button
                onClick={closeDetail}
                className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg transition"
              >
                Schließen
              </button>
            </div>
          </div>
          </FocusTrap>
        </div>
      )}
    </div>
  );
}
