import { useEffect, useState } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval } from 'date-fns';
import apiClient from '../api/client';
import { Plus, X } from 'lucide-react';

interface CalendarEntry {
  date: string;
  user_first_name: string;
  user_last_name: string;
  type: 'vacation' | 'sick' | 'training' | 'other';
  hours: number;
}

interface Absence {
  id: string;
  date: string;
  end_date?: string;
  type: 'vacation' | 'sick' | 'training' | 'other';
  hours: number;
  note?: string;
}

export default function AbsenceCalendarPage() {
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [calendarEntries, setCalendarEntries] = useState<CalendarEntry[]>([]);
  const [myAbsences, setMyAbsences] = useState<Absence[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [isDateRange, setIsDateRange] = useState(false);
  const [formData, setFormData] = useState({
    date: format(new Date(), 'yyyy-MM-dd'),
    end_date: '',
    type: 'vacation' as 'vacation' | 'sick' | 'training' | 'other',
    hours: 8,
    note: '',
  });

  useEffect(() => {
    fetchData();
  }, [currentMonth]);

  const fetchData = async () => {
    try {
      const [calendarRes, absencesRes] = await Promise.all([
        apiClient.get(`/absences/calendar?month=${currentMonth}`),
        apiClient.get(`/absences?year=${currentMonth.split('-')[0]}`),
      ]);
      setCalendarEntries(calendarRes.data);
      setMyAbsences(absencesRes.data);
    } catch (error) {
      console.error('Failed to fetch calendar data:', error);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const submitData = {
        date: formData.date,
        end_date: isDateRange && formData.end_date ? formData.end_date : null,
        type: formData.type,
        hours: formData.hours,
        note: formData.note || null,
      };
      await apiClient.post('/absences', submitData);
      fetchData();
      setShowForm(false);
      setIsDateRange(false);
      setFormData({
        date: format(new Date(), 'yyyy-MM-dd'),
        end_date: '',
        type: 'vacation',
        hours: 8,
        note: '',
      });
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Fehler beim Speichern');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Möchten Sie diese Abwesenheit wirklich löschen?')) return;
    try {
      await apiClient.delete(`/absences/${id}`);
      fetchData();
    } catch (error) {
      alert('Fehler beim Löschen');
    }
  };

  const typeLabels: Record<string, string> = {
    vacation: 'Urlaub',
    sick: 'Krank',
    training: 'Fortbildung',
    other: 'Sonstiges',
  };

  const typeColors: Record<string, string> = {
    vacation: 'bg-blue-100 text-blue-800 border-blue-300',
    sick: 'bg-red-100 text-red-800 border-red-300',
    training: 'bg-orange-100 text-orange-800 border-orange-300',
    other: 'bg-gray-100 text-gray-800 border-gray-300',
  };

  // Generate calendar days
  const [year, month] = currentMonth.split('-').map(Number);
  const monthStart = startOfMonth(new Date(year, month - 1));
  const monthEnd = endOfMonth(new Date(year, month - 1));
  const days = eachDayOfInterval({ start: monthStart, end: monthEnd });

  const weekdayNames = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Abwesenheitskalender</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
        >
          {showForm ? <X size={20} /> : <Plus size={20} />}
          <span>{showForm ? 'Abbrechen' : 'Abwesenheit eintragen'}</span>
        </button>
      </div>

      {/* Absence Form */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Abwesenheit eintragen</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Zeitraum-Checkbox */}
            <div className="flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
              <input
                type="checkbox"
                id="isDateRange"
                checked={isDateRange}
                onChange={(e) => {
                  setIsDateRange(e.target.checked);
                  if (!e.target.checked) {
                    setFormData({ ...formData, end_date: '' });
                  }
                }}
                className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
              />
              <label htmlFor="isDateRange" className="text-sm font-medium text-gray-700 cursor-pointer">
                Zeitraum (mehrere Tage)
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {isDateRange ? 'Von' : 'Datum'}
                </label>
                <input
                  type="date"
                  value={formData.date}
                  onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>

              {isDateRange && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
                  <input
                    type="date"
                    value={formData.end_date}
                    onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                    required={isDateRange}
                    min={formData.date}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Typ</label>
                <select
                  value={formData.type}
                  onChange={(e) => setFormData({ ...formData, type: e.target.value as any })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                >
                  <option value="vacation">Urlaub</option>
                  <option value="sick">Krank</option>
                  <option value="training">Fortbildung</option>
                  <option value="other">Sonstiges</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Stunden {isDateRange && '(pro Tag)'}
                </label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.hours}
                  onChange={(e) => setFormData({ ...formData, hours: parseFloat(e.target.value) })}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              {!isDateRange && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">&nbsp;</label>
                  <button
                    type="submit"
                    className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition"
                  >
                    Speichern
                  </button>
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
              <input
                type="text"
                value={formData.note}
                onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>

            {isDateRange && (
              <div>
                <button
                  type="submit"
                  className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition"
                >
                  Speichern
                </button>
              </div>
            )}
          </form>
        </div>
      )}

      {/* Month Selector */}
      <div className="mb-4">
        <input
          type="month"
          value={currentMonth}
          onChange={(e) => setCurrentMonth(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-lg"
        />
      </div>

      {/* Calendar */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="grid grid-cols-7 gap-2">
          {/* Weekday headers */}
          {weekdayNames.map((day) => (
            <div key={day} className="text-center font-semibold text-gray-600 py-2">
              {day}
            </div>
          ))}

          {/* Calendar days */}
          {days.map((day) => {
            const dateStr = format(day, 'yyyy-MM-dd');
            const dayEntries = calendarEntries.filter((e) => e.date === dateStr);
            const isWeekend = day.getDay() === 0 || day.getDay() === 6;

            return (
              <div
                key={dateStr}
                className={`min-h-24 border rounded-lg p-2 ${
                  isWeekend ? 'bg-gray-50' : 'bg-white'
                }`}
              >
                <div className="text-sm font-medium text-gray-600 mb-1">
                  {format(day, 'd')}
                </div>
                <div className="space-y-1">
                  {dayEntries.map((entry, idx) => (
                    <div
                      key={idx}
                      className={`text-xs px-2 py-1 rounded border ${typeColors[entry.type]}`}
                    >
                      {entry.user_first_name} {entry.user_last_name[0]}.
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <h3 className="font-semibold mb-3">Legende</h3>
        <div className="flex flex-wrap gap-4">
          {Object.entries(typeLabels).map(([key, label]) => (
            <div key={key} className="flex items-center space-x-2">
              <div className={`w-4 h-4 rounded border ${typeColors[key]}`}></div>
              <span className="text-sm">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* My Absences */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="font-semibold">Meine Abwesenheiten ({currentMonth.split('-')[0]})</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Datum</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Typ</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Stunden</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Notiz</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {myAbsences.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-4 text-center text-gray-500">
                    Keine Abwesenheiten
                  </td>
                </tr>
              ) : (
                myAbsences.map((absence) => (
                  <tr key={absence.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {absence.end_date ? (
                        <>
                          {format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')} - {format(new Date(absence.end_date + 'T00:00:00'), 'dd.MM.yyyy')}
                        </>
                      ) : (
                        format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`px-2 py-1 rounded text-xs ${typeColors[absence.type]}`}>
                        {typeLabels[absence.type]}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{absence.hours} h</td>
                    <td className="px-6 py-4 text-sm text-gray-500">{absence.note || '-'}</td>
                    <td className="px-6 py-4 text-right text-sm">
                      <button
                        onClick={() => handleDelete(absence.id)}
                        className="text-red-600 hover:text-red-800"
                      >
                        Löschen
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
