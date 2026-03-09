import { useState, useEffect } from 'react';
import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';
import apiClient from '../api/client';
import MonthSelector from './MonthSelector';
import LoadingSpinner from './LoadingSpinner';

// ---- Types ----------------------------------------------------------------

interface TimeEntryItem {
  id: string;
  start_time: string | null;
  end_time: string | null;
  break_minutes: number;
  net_hours: number;
}

interface AbsenceItem {
  id: string;
  type: string;
  hours: number;
}

interface JournalDay {
  date: string;
  weekday: string;
  type: 'work' | 'vacation' | 'sick' | 'overtime' | 'training' | 'other' | 'holiday' | 'weekend' | 'empty';
  is_holiday: boolean;
  holiday_name: string | null;
  time_entries: TimeEntryItem[];
  absences: AbsenceItem[];
  actual_hours: number;
  target_hours: number;
  balance: number;
}

interface JournalData {
  user: { id: string; first_name: string; last_name: string };
  year: number;
  month: number;
  days: JournalDay[];
  monthly_summary: { actual_hours: number; target_hours: number; balance: number };
  yearly_overtime: number;
}

// ---- Helper functions -----------------------------------------------------

const TYPE_LABELS: Record<string, string> = {
  work: 'Arbeitszeit',
  vacation: 'Urlaub',
  sick: 'Krank',
  overtime: 'Überstundenausgleich',
  training: 'Fortbildung',
  other: 'Sonstiges',
  holiday: 'Feiertag',
  weekend: '',
  empty: '–',
};

const TYPE_COLORS: Record<string, string> = {
  work: 'text-gray-900',
  vacation: 'text-blue-600',
  sick: 'text-orange-600',
  overtime: 'text-purple-600',
  training: 'text-green-600',
  other: 'text-gray-600',
  holiday: 'text-red-600',
  weekend: 'text-gray-400',
  empty: 'text-gray-400',
};

function formatHours(h: number): string {
  if (h === 0) return '–';
  const sign = h < 0 ? '-' : '+';
  const abs = Math.abs(h);
  const hours = Math.floor(abs);
  const mins = Math.round((abs - hours) * 60);
  return mins > 0 ? `${sign}${hours}h ${mins}min` : `${sign}${hours}h`;
}

function formatHoursSimple(h: number): string {
  if (h === 0) return '–';
  const hours = Math.floor(h);
  const mins = Math.round((h - hours) * 60);
  return mins > 0 ? `${hours}h ${mins}min` : `${hours}h`;
}

// ---- Main component -------------------------------------------------------

interface MonthlyJournalProps {
  userId: string;
  isAdminView: boolean;
}

export default function MonthlyJournal({ userId, isAdminView }: MonthlyJournalProps) {
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState(format(now, 'yyyy-MM'));
  const [data, setData] = useState<JournalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const [year, month] = selectedMonth.split('-').map(Number);
    const url = isAdminView
      ? `/admin/users/${userId}/journal?year=${year}&month=${month}`
      : `/journal/me?year=${year}&month=${month}`;

    setLoading(true);
    setError(null);

    apiClient
      .get(url)
      .then((res) => setData(res.data))
      .catch(() => setError('Journal konnte nicht geladen werden.'))
      .finally(() => setLoading(false));
  }, [selectedMonth, userId, isAdminView]);

  const isNonWorkDay = (day: JournalDay) =>
    day.type === 'weekend' || day.type === 'holiday';

  return (
    <div className="space-y-4">
      <MonthSelector value={selectedMonth} onChange={setSelectedMonth} />

      {loading && <LoadingSpinner />}
      {error && <p className="text-red-600">{error}</p>}

      {data && !loading && (
        <>
          {/* Table */}
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-3 py-2 text-left">Datum</th>
                  <th className="px-3 py-2 text-left hidden sm:table-cell">Tag</th>
                  <th className="px-3 py-2 text-left">Typ</th>
                  <th className="px-3 py-2 text-left hidden md:table-cell">Von–Bis</th>
                  <th className="px-3 py-2 text-right hidden md:table-cell">Pause</th>
                  <th className="px-3 py-2 text-right">Ist</th>
                  <th className="px-3 py-2 text-right">Soll</th>
                  <th className="px-3 py-2 text-right">Saldo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.days.map((day) => {
                  const dateObj = parseISO(day.date);
                  const isGray = isNonWorkDay(day);
                  const rowClass = isGray ? 'bg-gray-50 text-gray-400' : 'bg-white';

                  const entry = day.time_entries[0] ?? null;
                  const vonBis =
                    entry && entry.start_time && entry.end_time
                      ? `${entry.start_time}–${entry.end_time}`
                      : '–';
                  const pause =
                    entry && entry.break_minutes > 0
                      ? `${entry.break_minutes} min`
                      : '–';

                  const multiEntry = day.time_entries.length > 1;

                  const balanceColor =
                    isGray || day.type === 'empty'
                      ? 'text-gray-400'
                      : day.balance > 0
                      ? 'text-green-600 font-medium'
                      : day.balance < 0
                      ? 'text-red-600 font-medium'
                      : 'text-gray-600';

                  return (
                    <tr key={day.date} className={`${rowClass} hover:bg-gray-50 transition-colors`}>
                      <td className="px-3 py-2 font-medium whitespace-nowrap">
                        {format(dateObj, 'dd.MM.', { locale: de })}
                      </td>
                      <td className="px-3 py-2 hidden sm:table-cell">
                        {format(dateObj, 'EEE', { locale: de })}
                      </td>
                      <td className={`px-3 py-2 ${TYPE_COLORS[day.type]}`}>
                        {day.is_holiday && day.holiday_name
                          ? day.holiday_name
                          : TYPE_LABELS[day.type] ?? day.type}
                        {multiEntry && (
                          <span className="ml-1 text-xs text-gray-400">
                            ({day.time_entries.length}×)
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 hidden md:table-cell text-gray-600 whitespace-nowrap">
                        {isGray ? '–' : vonBis}
                      </td>
                      <td className="px-3 py-2 hidden md:table-cell text-right text-gray-500">
                        {isGray ? '' : pause}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-700">
                        {isGray ? '' : formatHoursSimple(day.actual_hours)}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-500">
                        {isGray ? '' : formatHoursSimple(day.target_hours)}
                      </td>
                      <td className={`px-3 py-2 text-right ${balanceColor}`}>
                        {isGray ? '' : formatHours(day.balance)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Aggregates */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Ist (Monat)</p>
              <p className="text-lg font-semibold text-gray-800">
                {formatHoursSimple(data.monthly_summary.actual_hours)}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Soll (Monat)</p>
              <p className="text-lg font-semibold text-gray-800">
                {formatHoursSimple(data.monthly_summary.target_hours)}
              </p>
            </div>
            <div className={`rounded-lg p-3 ${data.monthly_summary.balance >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
              <p className="text-xs text-gray-500 mb-1">Saldo (Monat)</p>
              <p className={`text-lg font-semibold ${data.monthly_summary.balance >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                {formatHours(data.monthly_summary.balance)}
              </p>
            </div>
            <div className={`rounded-lg p-3 ${data.yearly_overtime >= 0 ? 'bg-blue-50' : 'bg-orange-50'}`}>
              <p className="text-xs text-gray-500 mb-1">Überstunden (kumuliert)</p>
              <p className={`text-lg font-semibold ${data.yearly_overtime >= 0 ? 'text-blue-700' : 'text-orange-700'}`}>
                {formatHours(data.yearly_overtime)}
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
