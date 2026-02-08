import { useEffect, useState } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, getDay, addMonths } from 'date-fns';
import { de } from 'date-fns/locale';
import apiClient from '../api/client';
import { TrendingUp, TrendingDown, Calendar, Clock } from 'lucide-react';

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

interface OvertimeAccount {
  current_balance: number;
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
  const [teamAbsences, setTeamAbsences] = useState<TeamAbsence[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [dashboardRes, overtimeRes, vacationRes, teamAbsencesRes] = await Promise.all([
          apiClient.get('/dashboard'),
          apiClient.get('/dashboard/overtime'),
          apiClient.get('/dashboard/vacation'),
          apiClient.get('/absences/team/upcoming'),
        ]);

        setDashboardData(dashboardRes.data);
        setOvertimeAccount(overtimeRes.data);
        setVacationAccount(vacationRes.data);
        setTeamAbsences(teamAbsencesRes.data);
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

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
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
      </div>

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

                      {/* Calendar Grid */}
                      <div className="border border-gray-200 rounded-lg overflow-hidden">
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
