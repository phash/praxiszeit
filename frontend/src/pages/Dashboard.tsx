import { useEffect, useState } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, getDay, addMonths } from 'date-fns';
import { de } from 'date-fns/locale';
import apiClient from '../api/client';
import { TrendingUp, TrendingDown, Calendar, Clock, Palmtree } from 'lucide-react';
import StampWidget from '../components/StampWidget';

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
  other_days: number;
  total_days: number;
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
  type: 'vacation' | 'sick' | 'training' | 'other';
  hours: number;
  note?: string;
}

export default function Dashboard() {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [overtimeAccount, setOvertimeAccount] = useState<OvertimeAccount | null>(null);
  const [vacationAccount, setVacationAccount] = useState<VacationAccount | null>(null);
  const [yearlyAbsences, setYearlyAbsences] = useState<YearlyAbsenceSummary | null>(null);
  const [teamAbsences, setTeamAbsences] = useState<TeamAbsence[]>([]);
  const [nextVacation, setNextVacation] = useState<NextVacation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const currentYear = new Date().getFullYear();
        const [dashboardRes, overtimeRes, vacationRes, teamAbsencesRes, absencesRes, nextVacationRes] = await Promise.all([
          apiClient.get('/dashboard'),
          apiClient.get('/dashboard/overtime'),
          apiClient.get('/dashboard/vacation'),
          apiClient.get('/absences/team/upcoming'),
          apiClient.get('/absences', { params: { year: currentYear } }),
          apiClient.get('/absences/next-vacation'),
        ]);

        setDashboardData(dashboardRes.data);
        setOvertimeAccount(overtimeRes.data);
        setVacationAccount(vacationRes.data);
        setTeamAbsences(teamAbsencesRes.data);
        setNextVacation(nextVacationRes.data);

        // Calculate yearly absence summary
        const absences = absencesRes.data;
        const dailyTarget = dashboardRes.data.target_hours /
          new Date(dashboardRes.data.year, dashboardRes.data.month, 0).getDate();

        const summary = {
          vacation_days: absences.filter((a: any) => a.type === 'vacation').reduce((sum: number, a: any) => sum + a.hours, 0) / dailyTarget,
          sick_days: absences.filter((a: any) => a.type === 'sick').reduce((sum: number, a: any) => sum + a.hours, 0) / dailyTarget,
          training_days: absences.filter((a: any) => a.type === 'training').reduce((sum: number, a: any) => sum + a.hours, 0) / dailyTarget,
          other_days: absences.filter((a: any) => a.type === 'other').reduce((sum: number, a: any) => sum + a.hours, 0) / dailyTarget,
          total_days: 0
        };
        summary.total_days = summary.vacation_days + summary.sick_days + summary.training_days + summary.other_days;

        setYearlyAbsences(summary);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Lade Dashboard...</div>
      </div>
    );
  }

  const monthNames = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
  ];

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Dashboard</h1>

      {/* Stamp Widget */}
      <StampWidget />

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {/* Monthly Balance */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-gray-600">Monatssaldo</h3>
            <Calendar className="text-primary" size={24} />
          </div>
          {dashboardData && (
            <>
              <p className="text-xs text-gray-500 mb-2">
                {monthNames[dashboardData.month - 1]} {dashboardData.year}
              </p>
              <p
                className={`text-3xl font-bold ${
                  dashboardData.balance >= 0 ? 'text-green-600' : 'text-red-600'
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
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-gray-600">Überstundenkonto</h3>
            {overtimeAccount && overtimeAccount.current_balance >= 0 ? (
              <TrendingUp className="text-green-600" size={24} />
            ) : (
              <TrendingDown className="text-red-600" size={24} />
            )}
          </div>
          {overtimeAccount && (
            <>
              <p className="text-xs text-gray-500 mb-2">Kumulierter Saldo</p>
              <p
                className={`text-3xl font-bold ${
                  overtimeAccount.current_balance >= 0 ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {overtimeAccount.current_balance >= 0 ? '+' : ''}
                {overtimeAccount.current_balance.toFixed(2)} h
              </p>
            </>
          )}
        </div>

        {/* Vacation Account */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-gray-600">Urlaubskonto</h3>
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
            </>
          )}
        </div>

        {/* Vacation Countdown */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-gray-600">Urlaubscountdown</h3>
            <Palmtree className="text-green-600" size={24} />
          </div>
          {nextVacation ? (
            <>
              <p className="text-xs text-gray-500 mb-2">
                {nextVacation.days_until === 0
                  ? 'Heute beginnt dein Urlaub!'
                  : `Noch ${nextVacation.days_until === 1 ? '1 Tag' : `${nextVacation.days_until} Tage`}`}
              </p>
              <p className="text-3xl font-bold text-green-600">
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
      </div>

      {/* Monthly Overview Table */}
      {overtimeAccount && overtimeAccount.history.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-8">
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
                        month.balance >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {month.balance >= 0 ? '+' : ''}{month.balance.toFixed(1)}h
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`font-semibold ${
                        month.cumulative >= 0 ? 'text-green-600' : 'text-red-600'
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

      {/* Yearly Absence Overview */}
      {yearlyAbsences && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
          <h2 className="text-xl font-bold text-gray-900 mb-6">Jahresübersicht {new Date().getFullYear()}</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-600">{yearlyAbsences.vacation_days.toFixed(1)}</div>
              <div className="text-sm text-gray-600 mt-1">Urlaub</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-red-600">{yearlyAbsences.sick_days.toFixed(1)}</div>
              <div className="text-sm text-gray-600 mt-1">Krank</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-orange-600">{yearlyAbsences.training_days.toFixed(1)}</div>
              <div className="text-sm text-gray-600 mt-1">Fortbildung</div>
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

      {/* Team Absences Calendar */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-8">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="font-semibold text-gray-900">Geplante Abwesenheiten im Team</h3>
          <p className="text-sm text-gray-500 mt-1">Kalenderübersicht der nächsten 3 Monate</p>
        </div>
        <div className="p-6">
          {teamAbsences.length === 0 ? (
            <p className="text-gray-500 text-center py-4">Keine geplanten Abwesenheiten</p>
          ) : (
            <div className="space-y-8">
              {(() => {
                const typeLabels: Record<string, string> = {
                  vacation: 'Urlaub',
                  sick: 'Krank',
                  training: 'Fortbildung',
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
                                      {absence.user_first_name[0]}. {absence.user_last_name}
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
                          <p className="text-gray-500 text-center py-4 text-sm">
                            Keine Abwesenheiten in diesem Monat
                          </p>
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

      {/* Quick Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-blue-900 mb-2">Willkommen bei PraxisZeit</h3>
        <p className="text-blue-700">
          Nutzen Sie die Navigation links, um Ihre Zeiteinträge zu verwalten, Abwesenheiten einzutragen
          oder Ihre Übersicht anzusehen.
        </p>
      </div>
    </div>
  );
}
