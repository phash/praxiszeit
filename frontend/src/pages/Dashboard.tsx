import { useEffect, useState } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, getDay, addMonths } from 'date-fns';
import { de } from 'date-fns/locale';
import { Link } from 'react-router-dom';
import apiClient from '../api/client';
import { TrendingUp, TrendingDown, Calendar, Clock, Palmtree, ChevronDown, ChevronUp } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import { useUIStore } from '../stores/uiStore';
import StampWidget from '../components/StampWidget';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { useAuthStore } from '../stores/authStore';

interface DashboardData {
  year: number;
  month: number;
  target_hours: number;
  actual_hours: number;
  balance: number;
}

interface VacationAccount {
  year: number;
  budget_hours: number;
  budget_days: number;
  used_hours: number;
  used_days: number;
  remaining_hours: number;
  remaining_days: number;
  carryover_deadline?: string;
  has_carryover_warning?: boolean;
}

interface OvertimeHistory {
  year: number;
  month: number;
  target: number;
  actual: number;
  balance: number;
  cumulative: number;
}

interface OvertimeAccount {
  current_balance: number;
  history: OvertimeHistory[];
}

interface YearlyAbsenceSummary {
  vacation_days: number;
  sick_days: number;
  training_days: number;
  overtime_days: number;
  other_days: number;
  total_days: number;
}

interface YtdOvertime {
  year: number;
  target_hours: number;
  actual_hours: number;
  overtime: number;
  carryover_hours: number;
}

interface NextVacation {
  date: string;
  end_date?: string;
  days_until: number;
}

interface TeamAbsence {
  date: string;
  end_date?: string;
  user_first_name: string;
  user_last_name: string;
  user_color: string;
  type: 'vacation' | 'sick' | 'training' | 'overtime' | 'other';
  hours: number;
  note?: string;
}

const MONTH_NAMES = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
];

interface AbsenceEntry {
  type: 'vacation' | 'sick' | 'training' | 'overtime' | 'other';
  hours: number;
}

function sumAbsenceDays(absences: AbsenceEntry[], type: AbsenceEntry['type'], dailyTarget: number): number {
  if (!dailyTarget || dailyTarget <= 0) return 0;
  return absences
    .filter(a => a.type === type)
    .reduce((sum, a) => sum + a.hours, 0) / dailyTarget;
}

export default function Dashboard() {
  const toast = useToast();
  const { user } = useAuthStore();
  const { openStampSheet } = useUIStore();
  const trackHours = user?.track_hours !== false;
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [clockStatus, setClockStatus] = useState<{ is_clocked_in: boolean; current_entry?: { start_time: string } } | null>(null);
  const [recentEntries, setRecentEntries] = useState<Array<{ id: string; date: string; start_time: string; end_time: string | null; net_hours: number }>>([]);
  const [overtimeAccount, setOvertimeAccount] = useState<OvertimeAccount | null>(null);
  const [vacationAccount, setVacationAccount] = useState<VacationAccount | null>(null);
  const [yearlyAbsences, setYearlyAbsences] = useState<YearlyAbsenceSummary | null>(null);
  const [ytdOvertime, setYtdOvertime] = useState<YtdOvertime | null>(null);
  const [teamAbsences, setTeamAbsences] = useState<TeamAbsence[]>([]);
  const [nextVacation, setNextVacation] = useState<NextVacation | null>(null);
  const [loading, setLoading] = useState(true);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const currentYear = new Date().getFullYear();
        const [dashboardRes, overtimeRes, vacationRes, teamAbsencesRes, absencesRes, nextVacationRes, ytdRes] = await Promise.all([
          apiClient.get('/dashboard'),
          apiClient.get('/dashboard/overtime'),
          apiClient.get('/dashboard/vacation'),
          apiClient.get('/absences/team/upcoming'),
          apiClient.get('/absences', { params: { year: currentYear } }),
          apiClient.get('/absences/next-vacation'),
          apiClient.get('/dashboard/ytd-overtime'),
        ]);

        setDashboardData(dashboardRes.data);
        setOvertimeAccount(overtimeRes.data);
        setVacationAccount(vacationRes.data);
        setTeamAbsences(teamAbsencesRes.data);
        setNextVacation(nextVacationRes.data);
        setYtdOvertime(ytdRes.data);

        // Fetch recent entries + clock status for mobile
        try {
          const currentMonth = format(new Date(), 'yyyy-MM');
          const [entriesRes, clockRes] = await Promise.all([
            apiClient.get(`/time-entries?month=${currentMonth}`),
            trackHours ? apiClient.get('/time-entries/clock-status') : Promise.resolve({ data: null }),
          ]);
          setRecentEntries(entriesRes.data.slice(-5).reverse());
          if (clockRes.data) setClockStatus(clockRes.data);
        } catch { /* non-critical */ }

        // Calculate yearly absence summary
        const absences: AbsenceEntry[] = absencesRes.data;
        const daysInMonth = new Date(dashboardRes.data.year, dashboardRes.data.month, 0).getDate();
        const dailyTarget = dashboardRes.data.target_hours / daysInMonth;

        const vacation_days = sumAbsenceDays(absences, 'vacation', dailyTarget);
        const sick_days = sumAbsenceDays(absences, 'sick', dailyTarget);
        const training_days = sumAbsenceDays(absences, 'training', dailyTarget);
        const overtime_days = sumAbsenceDays(absences, 'overtime', dailyTarget);
        const other_days = sumAbsenceDays(absences, 'other', dailyTarget);
        const summary = {
          vacation_days,
          sick_days,
          training_days,
          overtime_days,
          other_days,
          total_days: vacation_days + sick_days + training_days + overtime_days + other_days,
        };

        setYearlyAbsences(summary);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
        toast.error('Fehler beim Laden des Dashboards');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const actualHours = dashboardData?.actual_hours ?? 0;
  const targetHours = dashboardData?.target_hours ?? 8;

  if (loading) {
    return (
      <>
        {/* Mobile skeleton */}
        <div className="md:hidden space-y-4 page-enter">
          <div className="skeleton h-7 w-3/5 mb-1" />
          <div className="skeleton h-4 w-2/5 mb-6" />
          <div className="skeleton h-24 rounded-2xl mb-6" />
          <div className="grid grid-cols-3 gap-3 mb-6">
            <div className="skeleton h-20 rounded-2xl" />
            <div className="skeleton h-20 rounded-2xl" />
            <div className="skeleton h-20 rounded-2xl" />
          </div>
          <div className="skeleton h-12 rounded-2xl mb-2" />
          <div className="skeleton h-12 rounded-2xl mb-2" />
          <div className="skeleton h-12 rounded-2xl" />
        </div>
        {/* Desktop spinner */}
        <div className="hidden md:flex items-center justify-center h-64">
          <LoadingSpinner text="Lade Dashboard..." />
        </div>
      </>
    );
  }


  return (
    <div className="page-enter">
      {/* Greeting - Mobile */}
      <div className="md:hidden mb-6">
        <h1 className="text-2xl font-semibold text-text-primary">
          Hallo, {user?.first_name || 'Willkommen'}
        </h1>
        <p className="text-sm text-text-secondary">
          {format(new Date(), 'EEEE, d. MMMM yyyy', { locale: de })}
        </p>
      </div>

      {/* Greeting - Desktop */}
      <h1 className="hidden md:block text-3xl font-bold text-text-primary mb-8">Dashboard</h1>

      {/* Status Card - Mobile Hero */}
      {trackHours && (
        <div
          className="md:hidden bg-surface rounded-2xl shadow-card p-5 mb-6 cursor-pointer active:shadow-soft transition-shadow"
          onClick={openStampSheet}
        >
          <div className="flex items-center gap-2 mb-3">
            <div className={`w-2 h-2 rounded-full ${clockStatus?.is_clocked_in ? 'bg-success' : 'bg-gray-300'}`} />
            <span className="text-sm font-medium text-text-primary">
              {clockStatus?.is_clocked_in && clockStatus.current_entry
                ? `Eingestempelt seit ${(clockStatus.current_entry.start_time.includes('T') ? clockStatus.current_entry.start_time.split('T')[1] : clockStatus.current_entry.start_time).substring(0, 5)}`
                : 'Nicht eingestempelt'}
            </span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden mb-2">
            <div
              className="h-full bg-gradient-to-r from-primary to-primary-dark rounded-full transition-all duration-1000"
              style={{ width: `${Math.min((actualHours / targetHours) * 100, 100)}%` }}
            />
          </div>
          <p className="text-xs text-text-secondary">
            {actualHours.toFixed(1)} von {targetHours.toFixed(1)} Std
          </p>
        </div>
      )}

      {/* Stat Pills - Mobile */}
      {trackHours && (
        <div className="grid grid-cols-3 gap-3 mb-6 md:hidden">
          <div className="bg-surface rounded-2xl shadow-soft p-4 text-center">
            <div className={`text-xl font-bold tabular-nums ${(overtimeAccount?.current_balance ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
              {(overtimeAccount?.current_balance ?? 0) >= 0 ? '+' : ''}{(overtimeAccount?.current_balance ?? 0).toFixed(1)}
            </div>
            <div className="text-xs text-text-secondary mt-1">Überstd.</div>
          </div>
          <div className="bg-surface rounded-2xl shadow-soft p-4 text-center">
            <div className="text-xl font-bold tabular-nums text-text-primary">
              {vacationAccount?.remaining_days?.toFixed(1) ?? '—'}
            </div>
            <div className="text-xs text-text-secondary mt-1">Urlaub</div>
          </div>
          <div className="bg-surface rounded-2xl shadow-soft p-4 text-center">
            <div className="text-xl font-bold tabular-nums text-text-primary">
              {yearlyAbsences?.sick_days?.toFixed(1) ?? '0'}
            </div>
            <div className="text-xs text-text-secondary mt-1">Krank</div>
          </div>
        </div>
      )}

      {/* Recent Entries - Mobile */}
      {recentEntries.length > 0 && (
        <div className="md:hidden bg-surface rounded-2xl shadow-soft mb-6">
          <div className="px-4 py-3 border-b border-muted">
            <h3 className="text-sm font-semibold text-text-primary">Letzte Einträge</h3>
          </div>
          <div className="divide-y divide-muted">
            {recentEntries.map(entry => (
              <div key={entry.id} className="px-4 py-3 flex items-center justify-between">
                <span className="text-sm text-text-secondary">
                  {format(new Date(entry.date + 'T00:00:00'), 'EE d.MM', { locale: de })}
                </span>
                <span className="text-sm text-text-secondary tabular-nums">
                  {entry.start_time?.slice(0, 5)}–{entry.end_time?.slice(0, 5) || '…'}
                </span>
                <span className="text-sm font-medium tabular-nums text-text-primary">
                  {entry.net_hours.toFixed(1)}h
                </span>
              </div>
            ))}
          </div>
          <Link to="/time-tracking" className="block px-4 py-3 text-sm text-primary font-medium text-center border-t border-muted">
            Alle anzeigen →
          </Link>
        </div>
      )}

      {/* Stamp Widget - Desktop only */}
      <div className="hidden md:block">
        <StampWidget />
      </div>

      {/* Stats Grid */}
      {trackHours && <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {/* Monthly Balance */}
        <div className="bg-surface rounded-2xl shadow-card border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-text-secondary">Monatssaldo</h3>
            <Calendar className="text-primary" size={24} />
          </div>
          {dashboardData && (
            <>
              <p className="text-xs text-gray-500 mb-2">
                {MONTH_NAMES[dashboardData.month - 1]} {dashboardData.year}
              </p>
              <p
                className={`text-3xl font-bold ${
                  dashboardData.balance >= 0 ? 'text-success' : 'text-danger'
                }`}
              >
                {dashboardData.balance >= 0 ? '+' : ''}
                {dashboardData.balance.toFixed(2)} h
              </p>
              <div className="mt-4 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Soll:</span>
                  <span className="font-medium">{dashboardData.target_hours.toFixed(2)} h</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Ist:</span>
                  <span className="font-medium">{dashboardData.actual_hours.toFixed(2)} h</span>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Overtime Account */}
        <div className="bg-surface rounded-2xl shadow-card border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-text-secondary">Überstundenkonto</h3>
            {overtimeAccount && overtimeAccount.current_balance >= 0 ? (
              <TrendingUp className="text-success" size={24} />
            ) : (
              <TrendingDown className="text-danger" size={24} />
            )}
          </div>
          {overtimeAccount && (
            <>
              <p className="text-xs text-gray-500 mb-2">Kumulierter Saldo</p>
              <p
                className={`text-3xl font-bold ${
                  overtimeAccount.current_balance >= 0 ? 'text-success' : 'text-danger'
                }`}
              >
                {overtimeAccount.current_balance >= 0 ? '+' : ''}
                {overtimeAccount.current_balance.toFixed(2)} h
              </p>
            </>
          )}
        </div>

        {/* Vacation Account */}
        <div className="bg-surface rounded-2xl shadow-card border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-text-secondary">Urlaubskonto</h3>
            <Clock className="text-primary" size={24} />
          </div>
          {vacationAccount && (
            <>
              <p className="text-xs text-gray-500 mb-2">Resturlaub {vacationAccount.year}</p>
              <p className="text-3xl font-bold text-primary">
                {vacationAccount.remaining_days.toFixed(1)} Tage
              </p>
              <div className="mt-4 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Budget:</span>
                  <span className="font-medium">{vacationAccount.budget_days} Tage</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Genommen:</span>
                  <span className="font-medium">{vacationAccount.used_days.toFixed(1)} Tage</span>
                </div>
              </div>
              {vacationAccount.has_carryover_warning && vacationAccount.carryover_deadline && (
                <div className="mt-3 p-2 bg-amber-50 border border-amber-200 rounded-lg">
                  <p className="text-xs text-amber-800 font-medium">
                    ⚠️ Noch {vacationAccount.remaining_days.toFixed(1)} Urlaubstage offen!
                  </p>
                  <p className="text-xs text-amber-700 mt-0.5">
                    Bis {new Date(vacationAccount.carryover_deadline + 'T00:00:00').toLocaleDateString('de-DE')} nehmen oder verfällt.
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        {/* Vacation Countdown */}
        <div className="bg-surface rounded-2xl shadow-card border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-text-secondary">Urlaubscountdown</h3>
            <Palmtree className="text-success" size={24} />
          </div>
          {nextVacation ? (
            <>
              <p className="text-xs text-gray-500 mb-2">
                {nextVacation.days_until === 0
                  ? 'Heute beginnt dein Urlaub!'
                  : `Noch ${nextVacation.days_until === 1 ? '1 Tag' : `${nextVacation.days_until} Tage`}`}
              </p>
              <p className="text-3xl font-bold text-success">
                {nextVacation.days_until === 0 ? '🏖️' : nextVacation.days_until}
                {nextVacation.days_until > 0 && <span className="text-lg ml-1">Tage</span>}
              </p>
              <div className="mt-4 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Ab:</span>
                  <span className="font-medium">
                    {format(new Date(nextVacation.date + 'T00:00:00'), 'dd.MM.yyyy', { locale: de })}
                  </span>
                </div>
                {nextVacation.end_date && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Bis:</span>
                    <span className="font-medium">
                      {format(new Date(nextVacation.end_date + 'T00:00:00'), 'dd.MM.yyyy', { locale: de })}
                    </span>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <p className="text-xs text-gray-500 mb-2">Kein Urlaub geplant</p>
              <p className="text-3xl font-bold text-gray-400">--</p>
              <p className="mt-4 text-sm text-gray-500">
                Trage Urlaub im Kalender ein
              </p>
            </>
          )}
        </div>
      </div>}

      {/* Monthly Overview Table */}
      {trackHours && overtimeAccount && overtimeAccount.history.length > 0 && (
        <div className="bg-surface rounded-2xl shadow-card border border-border overflow-hidden mb-8">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-xl font-bold text-gray-900">Monatsübersicht</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Monat</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Soll</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ist</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Saldo</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Überstunden kum.</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {overtimeAccount.history.slice().reverse().map((month) => (
                  <tr key={`${month.year}-${month.month}`} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {format(new Date(month.year, month.month - 1), 'MMMM yyyy', { locale: de })}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{month.target.toFixed(1)}h</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{month.actual.toFixed(1)}h</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`font-medium ${
                        month.balance >= 0 ? 'text-success' : 'text-danger'
                      }`}>
                        {month.balance >= 0 ? '+' : ''}{month.balance.toFixed(1)}h
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`font-semibold ${
                        month.cumulative >= 0 ? 'text-success' : 'text-danger'
                      }`}>
                        {month.cumulative >= 0 ? '+' : ''}{month.cumulative.toFixed(1)}h
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Details Toggle */}
      {trackHours && (
        <div className="mb-4 flex justify-center">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-text-secondary hover:text-gray-900 hover:bg-gray-100 rounded-lg transition"
          >
            {showDetails ? (
              <>
                <ChevronUp size={16} />
                <span>Details ausblenden</span>
              </>
            ) : (
              <>
                <ChevronDown size={16} />
                <span>Details anzeigen (Jahresübersicht & Team-Kalender)</span>
              </>
            )}
          </button>
        </div>
      )}

      {showDetails && (
        <>
          {/* Yearly Overview */}
          {trackHours && (yearlyAbsences || ytdOvertime) && (
            <div className="bg-surface rounded-2xl shadow-card border border-border p-6 mb-8">
              <h2 className="text-xl font-bold text-gray-900 mb-6">Jahresübersicht {new Date().getFullYear()}</h2>

              {/* YTD Overtime Summary */}
              {ytdOvertime && (
                <div className="mb-6 p-4 bg-gray-50 rounded-lg">
                  <h3 className="text-sm font-medium text-text-secondary mb-3">Stunden 01.01. bis heute</h3>
                  <div className={`grid ${ytdOvertime.carryover_hours !== 0 ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-3'} gap-4`}>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-gray-700">{ytdOvertime.target_hours.toFixed(1)}h</div>
                      <div className="text-sm text-gray-500 mt-1">Soll</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-gray-700">{ytdOvertime.actual_hours.toFixed(1)}h</div>
                      <div className="text-sm text-gray-500 mt-1">Ist</div>
                    </div>
                    {ytdOvertime.carryover_hours !== 0 && (
                      <div className="text-center">
                        <div className={`text-2xl font-bold ${ytdOvertime.carryover_hours >= 0 ? 'text-blue-600' : 'text-orange-600'}`}>
                          {ytdOvertime.carryover_hours >= 0 ? '+' : ''}{ytdOvertime.carryover_hours.toFixed(1)}h
                        </div>
                        <div className="text-sm text-gray-500 mt-1">Übertrag Vorjahr</div>
                      </div>
                    )}
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${ytdOvertime.overtime >= 0 ? 'text-success' : 'text-danger'}`}>
                        {ytdOvertime.overtime >= 0 ? '+' : ''}{ytdOvertime.overtime.toFixed(1)}h
                      </div>
                      <div className="text-sm text-gray-500 mt-1">Überstunden</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Absence Summary */}
              {yearlyAbsences && (
                <div>
                  <h3 className="text-sm font-medium text-text-secondary mb-3">Abwesenheiten</h3>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div className="text-center">
                      <div className="text-3xl font-bold text-blue-600">{yearlyAbsences.vacation_days.toFixed(1)}</div>
                      <div className="text-sm text-gray-600 mt-1">Urlaub</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-danger">{yearlyAbsences.sick_days.toFixed(1)}</div>
                      <div className="text-sm text-gray-600 mt-1">Krank</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-orange-600">{yearlyAbsences.training_days.toFixed(1)}</div>
                      <div className="text-sm text-gray-600 mt-1">Fortbildung</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-purple-600">{yearlyAbsences.overtime_days.toFixed(1)}</div>
                      <div className="text-sm text-gray-600 mt-1">Überstunden&shy;ausgleich</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-gray-600">{yearlyAbsences.other_days.toFixed(1)}</div>
                      <div className="text-sm text-gray-600 mt-1">Sonstiges</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-gray-900">{yearlyAbsences.total_days.toFixed(1)}</div>
                      <div className="text-sm text-gray-600 mt-1">Gesamt</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Team Absences Calendar */}
          <div className="bg-surface rounded-2xl shadow-card border border-border overflow-hidden mb-8">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="font-semibold text-gray-900">Geplante Abwesenheiten im Team</h3>
          <p className="text-sm text-gray-500 mt-1">Kalenderübersicht der nächsten 3 Monate</p>
        </div>
        <div className="p-6">
          {teamAbsences.length === 0 ? (
            <EmptyState title="Keine geplanten Abwesenheiten" />
          ) : (
            <div className="space-y-8">
              {(() => {
                const typeLabels: Record<string, string> = {
                  vacation: 'Urlaub',
                  sick: 'Krank',
                  training: 'Fortbildung (außer Haus)',
                  overtime: 'Überstundenausgleich',
                  other: 'Sonstiges',
                };


                // Organize absences by date (backend already created entries for each day)
                const absencesByDate: Record<string, TeamAbsence[]> = {};
                teamAbsences.forEach((absence) => {
                  // Only use the date field - backend already split date ranges into individual days
                  const dateKey = absence.date;
                  if (!absencesByDate[dateKey]) {
                    absencesByDate[dateKey] = [];
                  }
                  absencesByDate[dateKey].push(absence);
                });

                // Generate next 3 months
                const today = new Date();
                const months = [today, addMonths(today, 1), addMonths(today, 2)];

                return months.map((monthDate, monthIdx) => {
                  const monthStart = startOfMonth(monthDate);
                  const monthEnd = endOfMonth(monthDate);
                  const days = eachDayOfInterval({ start: monthStart, end: monthEnd });

                  // Add padding days for calendar grid
                  const firstDayOfWeek = getDay(monthStart);
                  const paddingDays = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1; // Monday = 0

                  return (
                    <div key={monthIdx}>
                      <h4 className="font-semibold text-lg mb-3">
                        {format(monthDate, 'MMMM yyyy', { locale: de })}
                      </h4>

                      {/* Desktop: Calendar Grid */}
                      <div className="hidden sm:block border border-gray-200 rounded-lg overflow-hidden">
                        {/* Weekday Headers */}
                        <div className="grid grid-cols-7 bg-gray-50 border-b border-gray-200">
                          {['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map((day) => (
                            <div key={day} className="text-center text-xs font-semibold text-gray-600 py-2 border-r border-gray-200 last:border-r-0">
                              {day}
                            </div>
                          ))}
                        </div>

                        {/* Calendar Days */}
                        <div className="grid grid-cols-7">
                          {/* Padding days */}
                          {Array.from({ length: paddingDays }).map((_, idx) => (
                            <div key={`pad-${idx}`} className="min-h-20 bg-gray-50 border-r border-b border-gray-200"></div>
                          ))}

                          {/* Actual days */}
                          {days.map((day) => {
                            const dateKey = format(day, 'yyyy-MM-dd');
                            const dayAbsences = absencesByDate[dateKey] || [];
                            const isWeekend = getDay(day) === 0 || getDay(day) === 6;
                            const isToday = format(day, 'yyyy-MM-dd') === format(new Date(), 'yyyy-MM-dd');

                            return (
                              <div
                                key={dateKey}
                                className={`min-h-20 border-r border-b border-gray-200 p-1 ${
                                  isWeekend ? 'bg-gray-50' : 'bg-white'
                                } ${isToday ? 'ring-2 ring-primary ring-inset' : ''}`}
                              >
                                <div className={`text-xs font-medium mb-1 ${isToday ? 'text-primary font-bold' : 'text-gray-600'}`}>
                                  {format(day, 'd')}
                                </div>
                                <div className="space-y-0.5">
                                  {dayAbsences.map((absence, idx) => (
                                    <div
                                      key={idx}
                                      className="text-xs px-1 py-0.5 rounded text-white"
                                      style={{ backgroundColor: absence.user_color }}
                                      title={`${absence.user_first_name} ${absence.user_last_name} - ${typeLabels[absence.type]}${absence.note ? ': ' + absence.note : ''}`}
                                    >
                                      {absence.user_first_name?.[0]}. {absence.user_last_name}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Mobile: List View */}
                      <div className="sm:hidden space-y-2">
                        {days
                          .filter((day) => {
                            const dateKey = format(day, 'yyyy-MM-dd');
                            const dayAbsences = absencesByDate[dateKey] || [];
                            return dayAbsences.length > 0;
                          })
                          .map((day) => {
                            const dateKey = format(day, 'yyyy-MM-dd');
                            const dayAbsences = absencesByDate[dateKey] || [];
                            const isToday = format(day, 'yyyy-MM-dd') === format(new Date(), 'yyyy-MM-dd');

                            return (
                              <div
                                key={dateKey}
                                className={`border rounded-lg p-3 ${
                                  isToday ? 'border-primary bg-blue-50' : 'border-gray-200 bg-white'
                                }`}
                              >
                                <p className={`font-semibold text-sm mb-2 ${isToday ? 'text-primary' : 'text-gray-900'}`}>
                                  {format(day, 'EEEE, dd. MMMM', { locale: de })}
                                </p>
                                <div className="space-y-1">
                                  {dayAbsences.map((absence, idx) => (
                                    <div
                                      key={idx}
                                      className="flex items-center text-sm"
                                    >
                                      <span
                                        className="w-3 h-3 rounded-full mr-2 flex-shrink-0"
                                        style={{ backgroundColor: absence.user_color }}
                                      ></span>
                                      <span className="font-medium text-gray-900">
                                        {absence.user_first_name} {absence.user_last_name}
                                      </span>
                                      <span className="text-gray-500 mx-1">-</span>
                                      <span className="text-gray-600">{typeLabels[absence.type]}</span>
                                      {absence.note && (
                                        <span className="text-gray-500 text-xs ml-1">({absence.note})</span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        {days.filter((day) => {
                          const dateKey = format(day, 'yyyy-MM-dd');
                          return (absencesByDate[dateKey] || []).length > 0;
                        }).length === 0 && (
                          <EmptyState title="Keine Abwesenheiten in diesem Zeitraum" />
                        )}
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          )}
        </div>
        </div>
        </>
      )}

    </div>
  );
}
