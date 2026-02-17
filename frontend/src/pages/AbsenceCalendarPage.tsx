import { useEffect, useState } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';
import apiClient from '../api/client';
import { Plus, X, Trash2 } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from '../components/ConfirmDialog';
import { AbsenceType, ABSENCE_TYPE_LABELS, ABSENCE_TYPE_COLORS } from '../constants/absenceTypes';
import Badge from '../components/Badge';
import MonthSelector from '../components/MonthSelector';

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

interface PublicHoliday {
  date: string;
  name: string;
}

export default function AbsenceCalendarPage() {
  const toast = useToast();
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [viewMode, setViewMode] = useState<'month' | 'year'>('month');
  const [calendarEntries, setCalendarEntries] = useState<CalendarEntry[]>([]);
  const [myAbsences, setMyAbsences] = useState<Absence[]>([]);
  const [holidays, setHolidays] = useState<PublicHoliday[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [isDateRange, setIsDateRange] = useState(false);
  const [formData, setFormData] = useState({
    date: format(new Date(), 'yyyy-MM-dd'),
    end_date: '',
    type: 'vacation' as 'vacation' | 'sick' | 'training' | 'other',
    hours: 8,
    note: '',
  });
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  useEffect(() => {
    fetchData();
  }, [currentMonth, currentYear, viewMode]);

  const fetchData = async () => {
    try {
      const year = viewMode === 'month' ? parseInt(currentMonth.split('-')[0]) : currentYear;
      
      if (viewMode === 'month') {
        const [calendarRes, absencesRes, holidaysRes] = await Promise.all([
          apiClient.get(`/absences/calendar?month=${currentMonth}`),
          apiClient.get(`/absences?year=${year}`),
          apiClient.get(`/holidays?year=${year}`),
        ]);
        setCalendarEntries(calendarRes.data);
        setMyAbsences(absencesRes.data);
        setHolidays(holidaysRes.data);
      } else {
        // Fetch all months for the year
        const promises = Array.from({ length: 12 }, (_, i) => {
          const month = `${currentYear}-${String(i + 1).padStart(2, '0')}`;
          return apiClient.get(`/absences/calendar?month=${month}`);
        });
        const results = await Promise.all(promises);
        const allEntries = results.flatMap(r => r.data);
        setCalendarEntries(allEntries);

        // Fetch user absences and holidays for the year
        const [absencesRes, holidaysRes] = await Promise.all([
          apiClient.get(`/absences?year=${currentYear}`),
          apiClient.get(`/holidays?year=${currentYear}`),
        ]);
        setMyAbsences(absencesRes.data);
        setHolidays(holidaysRes.data);
      }
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
      toast.success('Abwesenheit erfolgreich eingetragen');
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
      toast.error(error.response?.data?.detail || 'Fehler beim Speichern');
    }
  };

  const handleDelete = (id: string) => {
    confirm({
      title: 'Abwesenheit löschen',
      message: 'Möchten Sie diese Abwesenheit wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/absences/${id}`);
          toast.success('Abwesenheit erfolgreich gelöscht');
          fetchData();
        } catch (error) {
          toast.error('Fehler beim Löschen');
        }
      },
    });
  };

  // Use shared constants
  const typeLabels = ABSENCE_TYPE_LABELS;
  const typeColors = ABSENCE_TYPE_COLORS;

  // Generate calendar days
  const [year, month] = currentMonth.split('-').map(Number);
  const monthStart = startOfMonth(new Date(year, month - 1));
  const monthEnd = endOfMonth(new Date(year, month - 1));
  const days = eachDayOfInterval({ start: monthStart, end: monthEnd });

  // Monday-first calendar (consistent with year view)
  const weekdayNames = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const firstDayOffset = (monthStart.getDay() + 6) % 7; // 0=Mo, 1=Di, ..., 6=So

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

      {/* View Mode Toggle and Selector */}
      <div className="mb-4 flex items-center space-x-4">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setViewMode('month')}
            className={`px-4 py-2 rounded-lg font-medium transition ${
              viewMode === 'month'
                ? 'bg-primary text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Monatsansicht
          </button>
          <button
            onClick={() => setViewMode('year')}
            className={`px-4 py-2 rounded-lg font-medium transition ${
              viewMode === 'year'
                ? 'bg-primary text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Jahresansicht
          </button>
        </div>
        {viewMode === 'month' ? (
          <MonthSelector
            value={currentMonth}
            onChange={setCurrentMonth}
          />
        ) : (
          <input
            type="number"
            value={currentYear}
            onChange={(e) => setCurrentYear(parseInt(e.target.value))}
            min="2020"
            max={new Date().getFullYear() + 1}
            className="px-4 py-2 border border-gray-300 rounded-lg"
          />
        )}
      </div>

      {/* Calendar */}
      {viewMode === 'month' ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 mb-6">
          {/* Desktop Calendar Grid */}
          <div className="hidden sm:block p-6">
            <div className="grid grid-cols-7 gap-2">
              {/* Weekday headers */}
              {weekdayNames.map((day) => (
                <div key={day} className="text-center font-semibold text-gray-600 py-2">
                  {day}
                </div>
              ))}

              {/* Offset cells for first day of month */}
              {Array.from({ length: firstDayOffset }).map((_, i) => (
                <div key={`offset-${i}`} />
              ))}

              {/* Calendar days */}
              {days.map((day) => {
                const dateStr = format(day, 'yyyy-MM-dd');
                const dayEntries = calendarEntries.filter((e) => e.date === dateStr);
                const dayHoliday = holidays.find((h) => h.date === dateStr);
                const isWeekend = day.getDay() === 0 || day.getDay() === 6;

                return (
                  <div
                    key={dateStr}
                    onClick={() => {
                      setFormData(prev => ({ ...prev, date: dateStr }));
                      setShowForm(true);
                      setIsDateRange(false);
                    }}
                    className={`min-h-24 border rounded-lg p-2 cursor-pointer transition hover:border-primary hover:shadow-sm ${
                      isWeekend || dayHoliday ? 'bg-gray-50' : 'bg-white'
                    }`}
                    title="Klicken um Abwesenheit einzutragen"
                  >
                    <div className="text-sm font-medium text-gray-600 mb-1">
                      {format(day, 'd')}
                    </div>
                    <div className="space-y-1">
                      {/* Holiday Badge */}
                      {dayHoliday && (
                        <div className="text-xs px-2 py-1 rounded bg-gray-200 text-gray-700 border border-gray-300 font-medium">
                          {dayHoliday.name}
                        </div>
                      )}
                      {/* Absence Entries */}
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

          {/* Mobile List View */}
          <div className="sm:hidden">
            {days
              .filter((day) => {
                const dateStr = format(day, 'yyyy-MM-dd');
                const dayEntries = calendarEntries.filter((e) => e.date === dateStr);
                const dayHoliday = holidays.find((h) => h.date === dateStr);
                return dayEntries.length > 0 || dayHoliday;
              })
              .map((day) => {
                const dateStr = format(day, 'yyyy-MM-dd');
                const dayEntries = calendarEntries.filter((e) => e.date === dateStr);
                const dayHoliday = holidays.find((h) => h.date === dateStr);
                const isWeekend = day.getDay() === 0 || day.getDay() === 6;

                return (
                  <div key={dateStr} className="border-b border-gray-200 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <p className="font-semibold text-gray-900">
                          {format(day, 'EEEE, dd. MMMM', { locale: de })}
                        </p>
                        {isWeekend && (
                          <span className="text-xs text-gray-500">Wochenende</span>
                        )}
                      </div>
                    </div>
                    <div className="space-y-2">
                      {/* Holiday */}
                      {dayHoliday && (
                        <div className="px-3 py-2 rounded-lg bg-gray-100 border border-gray-200">
                          <p className="text-sm font-medium text-gray-700">
                            🎉 {dayHoliday.name}
                          </p>
                        </div>
                      )}
                      {/* Absence Entries */}
                      {dayEntries.map((entry, idx) => (
                        <div
                          key={idx}
                          className={`px-3 py-2 rounded-lg border ${typeColors[entry.type]}`}
                        >
                          <p className="text-sm font-medium">
                            {entry.user_first_name} {entry.user_last_name}
                          </p>
                          <p className="text-xs text-gray-600 mt-0.5">
                            {typeLabels[entry.type]}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            {days.filter((day) => {
              const dateStr = format(day, 'yyyy-MM-dd');
              const dayEntries = calendarEntries.filter((e) => e.date === dateStr);
              const dayHoliday = holidays.find((h) => h.date === dateStr);
              return dayEntries.length > 0 || dayHoliday;
            }).length === 0 && (
              <div className="p-6 text-center text-gray-500">
                Keine Abwesenheiten oder Feiertage in diesem Monat
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[0,1,2,3,4,5,6,7,8,9,10,11].map(monthIndex => {
              const monthDate = new Date(currentYear, monthIndex, 1);
              const monthStart = startOfMonth(monthDate);
              const monthEnd = endOfMonth(monthDate);
              const days = eachDayOfInterval({ start: monthStart, end: monthEnd });

              // Get absences for this month
              const monthAbsences = calendarEntries.filter(entry => {
                const entryDate = parseISO(entry.date);
                return entryDate >= monthStart && entryDate <= monthEnd;
              });

              // Get first day offset for calendar grid
              const firstDayOfWeek = monthStart.getDay();
              const paddingDays = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1; // Monday = 0

              return (
                <div key={monthIndex} className="bg-white rounded-lg border border-gray-200 p-3">
                  <h3 className="text-sm font-semibold text-gray-900 mb-2 text-center">
                    {format(monthDate, 'MMMM', { locale: de })}
                  </h3>
                  <div className="grid grid-cols-7 gap-1 text-xs">
                    {['M', 'D', 'M', 'D', 'F', 'S', 'S'].map((day, i) => (
                      <div key={i} className="text-center font-medium text-gray-400 py-1">
                        {day}
                      </div>
                    ))}

                    {/* Empty cells for offset */}
                    {Array.from({ length: paddingDays }).map((_, i) => (
                      <div key={`empty-${i}`} />
                    ))}

                    {days.map(day => {
                      const dateStr = format(day, 'yyyy-MM-dd');
                      const dayAbsences = monthAbsences.filter(e => e.date === dateStr);
                      const dayHoliday = holidays.find((h) => h.date === dateStr);
                      const isWeekend = day.getDay() === 0 || day.getDay() === 6;

                      return (
                        <div
                          key={dateStr}
                          onClick={() => {
                            setFormData(prev => ({ ...prev, date: dateStr }));
                            setShowForm(true);
                            setIsDateRange(false);
                          }}
                          className={`aspect-square flex flex-col items-center justify-center rounded text-xs cursor-pointer hover:ring-1 hover:ring-primary ${
                            isWeekend || dayHoliday ? 'bg-gray-100' : 'bg-white'
                          }`}
                          title={dayHoliday ? dayHoliday.name : 'Klicken um Abwesenheit einzutragen'}
                        >
                          <div className={`font-medium ${dayHoliday ? 'text-gray-500' : 'text-gray-700'}`}>
                            {format(day, 'd')}
                          </div>
                          {dayAbsences.length > 0 && (
                            <div className="flex space-x-0.5 mt-0.5">
                              {dayAbsences.slice(0, 3).map((_, idx) => (
                                <div key={idx} className="w-1 h-1 rounded-full bg-blue-500"></div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <h3 className="font-semibold mb-3">Legende</h3>
        <div className="flex flex-wrap gap-4">
          {Object.entries(typeLabels).map(([key, label]) => (
            <div key={key} className="flex items-center space-x-2">
              <div className={`w-4 h-4 rounded border ${typeColors[key as AbsenceType]}`}></div>
              <span className="text-sm">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* My Absences */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="font-semibold">Meine Abwesenheiten ({viewMode === 'month' ? currentMonth.split('-')[0] : currentYear})</h3>
        </div>

        {/* Desktop Table */}
        <div className="hidden md:block overflow-x-auto">
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

        {/* Mobile Cards */}
        <div className="md:hidden">
          {myAbsences.length === 0 ? (
            <div className="p-6 text-center text-gray-500">
              Keine Abwesenheiten
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {myAbsences.map((absence) => (
                <div key={absence.id} className="p-4">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                      <p className="font-medium text-gray-900">
                        {absence.end_date ? (
                          <>
                            {format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')} - {format(new Date(absence.end_date + 'T00:00:00'), 'dd.MM.yyyy')}
                          </>
                        ) : (
                          format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')
                        )}
                      </p>
                      <div className="mt-2">
                        <Badge variant={absence.type} size="sm">
                          {typeLabels[absence.type]}
                        </Badge>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(absence.id)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition"
                      aria-label="Abwesenheit löschen"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>

                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Stunden:</span>
                      <span className="font-medium">{absence.hours} h</span>
                    </div>
                    {absence.note && (
                      <div>
                        <span className="text-gray-600 block mb-1">Notiz:</span>
                        <p className="text-gray-900">{absence.note}</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
