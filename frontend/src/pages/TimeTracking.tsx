import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import apiClient from '../api/client';
import { Plus, Edit2, Trash2, Save, X, Lock, FileEdit } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import { useAuthStore } from '../stores/authStore';
import ConfirmDialog from '../components/ConfirmDialog';
import ChangeRequestForm from '../components/ChangeRequestForm';
import LoadingSpinner from '../components/LoadingSpinner';
import MonthSelector from '../components/MonthSelector';

interface TimeEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string | null;
  break_minutes: number;
  net_hours: number;
  note?: string;
  is_editable: boolean;
  warnings: string[];
  is_sunday_or_holiday: boolean;
  is_night_work: boolean;
  sunday_exception_reason?: string | null;
}

export default function TimeTracking() {
  const toast = useToast();
  const { user } = useAuthStore();
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    date: format(new Date(), 'yyyy-MM-dd'),
    start_time: '08:00',
    end_time: '17:00',
    break_minutes: 0,
    note: '',
    sunday_exception_reason: '',
  });
  const [errors, setErrors] = useState<{
    start_time?: string;
    end_time?: string;
    overlap?: string;
    break_time?: string;
  }>({});
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  // Change request modal
  const [crModalOpen, setCrModalOpen] = useState(false);
  const [crEntry, setCrEntry] = useState<TimeEntry | null>(null);
  const [crType, setCrType] = useState<'create' | 'update' | 'delete'>('update');

  useEffect(() => {
    fetchEntries();
  }, [currentMonth]);

  const fetchEntries = async () => {
    try {
      const response = await apiClient.get(`/time-entries?month=${currentMonth}`);
      setEntries(response.data);
    } catch (error) {
      toast.error('Fehler beim Laden der Zeiteinträge');
    } finally {
      setLoading(false);
    }
  };

  const validateTimeEntry = (): boolean => {
    const newErrors: typeof errors = {};

    if (formData.start_time >= formData.end_time) {
      newErrors.end_time = 'Endzeit muss nach Startzeit liegen';
    }

    // Check for overlapping entries on the same day (skip open entries)
    const sameDay = entries.filter(
      (entry) => entry.date === formData.date && entry.id !== editingId && entry.end_time
    );

    const newStart = formData.start_time;
    const newEnd = formData.end_time;

    for (const entry of sameDay) {
      const existingStart = entry.start_time.substring(0, 5);
      const existingEnd = entry.end_time!.substring(0, 5);

      if (newStart < existingEnd && newEnd > existingStart) {
        newErrors.overlap = `Überschneidung mit bestehendem Eintrag (${existingStart} - ${existingEnd})`;
        break;
      }
    }

    // Client-side break validation
    const startParts = formData.start_time.split(':').map(Number);
    const endParts = formData.end_time.split(':').map(Number);
    const grossMinutes = (endParts[0] * 60 + endParts[1]) - (startParts[0] * 60 + startParts[1]);
    const netMinutes = grossMinutes - formData.break_minutes;

    if (netMinutes > 360 && formData.break_minutes < 30) {
      // Also count gaps between other entries on same day (skip open entries)
      const allBlocks = sameDay.filter(e => e.end_time).map(e => ({
        start: parseInt(e.start_time.substring(0, 2)) * 60 + parseInt(e.start_time.substring(3, 5)),
        end: parseInt(e.end_time!.substring(0, 2)) * 60 + parseInt(e.end_time!.substring(3, 5)),
        brk: e.break_minutes,
      }));
      allBlocks.push({
        start: startParts[0] * 60 + startParts[1],
        end: endParts[0] * 60 + endParts[1],
        brk: formData.break_minutes,
      });
      allBlocks.sort((a, b) => a.start - b.start);

      let totalDeclared = allBlocks.reduce((s, b) => s + b.brk, 0);
      let totalGap = 0;
      for (let i = 1; i < allBlocks.length; i++) {
        const gap = allBlocks[i].start - allBlocks[i - 1].end;
        if (gap > 0) totalGap += gap;
      }
      const totalGross = allBlocks.reduce((s, b) => s + (b.end - b.start), 0);
      const totalNet = totalGross - totalDeclared;
      const totalEffBreak = totalDeclared + totalGap;

      if (totalNet > 360 && totalEffBreak < 30) {
        newErrors.break_time = 'Bei >6h Arbeitszeit sind mind. 30 Min. Pause erforderlich (ArbZG §4)';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateTimeEntry()) {
      return;
    }

    try {
      let response;
      if (editingId) {
        response = await apiClient.put(`/time-entries/${editingId}`, formData);
        toast.success('Zeiteintrag erfolgreich aktualisiert');
      } else {
        response = await apiClient.post('/time-entries', formData);
        toast.success('Zeiteintrag erfolgreich erstellt');
      }
      const saved: TimeEntry = response.data;
      if (saved.warnings?.includes('DAILY_HOURS_WARNING')) {
        toast.warning('Tagesarbeitszeit überschreitet 8 Stunden (§3 ArbZG)');
      }
      if (saved.warnings?.includes('WEEKLY_HOURS_WARNING')) {
        toast.warning('Wochenarbeitszeit überschreitet 48 Stunden (§14 ArbZG)');
      }
      if (saved.warnings?.includes('SUNDAY_WORK')) {
        toast.warning('Achtung: Sonntagsarbeit – Ausnahmegrund nach §10 ArbZG dokumentieren');
      }
      if (saved.warnings?.includes('HOLIDAY_WORK')) {
        toast.warning('Achtung: Feiertagsarbeit – Ausnahmegrund nach §10 ArbZG dokumentieren');
      }
      fetchEntries();
      resetForm();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Fehler beim Speichern');
    }
  };

  const handleEdit = (entry: TimeEntry) => {
    setEditingId(entry.id);
    setFormData({
      date: entry.date,
      start_time: entry.start_time.substring(0, 5),
      end_time: entry.end_time ? entry.end_time.substring(0, 5) : '17:00',
      break_minutes: entry.break_minutes,
      note: entry.note || '',
      sunday_exception_reason: entry.sunday_exception_reason || '',
    });
    setErrors({});
    setShowForm(true);
  };

  const handleDelete = (id: string) => {
    confirm({
      title: 'Eintrag löschen',
      message: 'Möchten Sie diesen Zeiteintrag wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/time-entries/${id}`);
          toast.success('Zeiteintrag erfolgreich gelöscht');
          fetchEntries();
        } catch (error) {
          toast.error('Fehler beim Löschen');
        }
      },
    });
  };

  const openChangeRequest = (entry: TimeEntry, type: 'update' | 'delete') => {
    setCrEntry(entry);
    setCrType(type);
    setCrModalOpen(true);
  };

  const openCreateChangeRequest = () => {
    setCrEntry(null);
    setCrType('create');
    setCrModalOpen(true);
  };

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setFormData({
      date: format(new Date(), 'yyyy-MM-dd'),
      start_time: '08:00',
      end_time: '17:00',
      break_minutes: 0,
      note: '',
      sunday_exception_reason: '',
    });
    setErrors({});
  };

  const totalNet = entries.reduce((sum, entry) => sum + entry.net_hours, 0);
  const weekdayNames = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const isAdmin = user?.role === 'admin';

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

      {crModalOpen && (
        <ChangeRequestForm
          entry={crEntry}
          requestType={crType}
          onClose={() => setCrModalOpen(false)}
          onSuccess={() => {
            setCrModalOpen(false);
            toast.success('Änderungsantrag erfolgreich erstellt');
          }}
        />
      )}

      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Zeiterfassung</h1>
        <div className="flex items-center space-x-2">
          {!isAdmin && (
            <button
              onClick={openCreateChangeRequest}
              className="bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
              title="Antrag für vergangenen Tag stellen"
            >
              <FileEdit size={20} />
              <span className="hidden sm:inline">Antrag</span>
            </button>
          )}
          <button
            onClick={() => setShowForm(!showForm)}
            className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
          >
            {showForm ? <X size={20} /> : <Plus size={20} />}
            <span>{showForm ? 'Abbrechen' : 'Neuer Eintrag'}</span>
          </button>
        </div>
      </div>

      {/* Entry Form */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">
            {editingId ? 'Eintrag bearbeiten' : 'Neuer Zeiteintrag'}
          </h3>
          {errors.overlap && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg" role="alert">
              <p className="text-sm text-red-800 font-medium">{errors.overlap}</p>
            </div>
          )}
          {errors.break_time && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg" role="alert">
              <p className="text-sm text-amber-800 font-medium">{errors.break_time}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            <div>
              <label htmlFor="tt-date" className="block text-sm font-medium text-gray-700 mb-1">Datum</label>
              <input
                id="tt-date"
                type="date"
                value={formData.date}
                onChange={(e) => {
                  setFormData({ ...formData, date: e.target.value });
                  setErrors({});
                }}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label htmlFor="start-time" className="block text-sm font-medium text-gray-700 mb-1">Von</label>
              <input
                id="start-time"
                type="time"
                value={formData.start_time}
                onChange={(e) => {
                  setFormData({ ...formData, start_time: e.target.value });
                  setErrors({});
                }}
                required
                aria-invalid={errors.start_time ? 'true' : 'false'}
                aria-describedby={errors.start_time ? 'start-time-error' : undefined}
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary ${
                  errors.start_time ? 'border-red-500' : 'border-gray-300'
                }`}
              />
              {errors.start_time && (
                <p id="start-time-error" className="text-sm text-red-600 mt-1" role="alert">
                  {errors.start_time}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="end-time" className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
              <input
                id="end-time"
                type="time"
                value={formData.end_time}
                onChange={(e) => {
                  setFormData({ ...formData, end_time: e.target.value });
                  setErrors({});
                }}
                required
                aria-invalid={errors.end_time ? 'true' : 'false'}
                aria-describedby={errors.end_time ? 'end-time-error' : undefined}
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary ${
                  errors.end_time ? 'border-red-500' : 'border-gray-300'
                }`}
              />
              {errors.end_time && (
                <p id="end-time-error" className="text-sm text-red-600 mt-1" role="alert">
                  {errors.end_time}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="break-minutes" className="block text-sm font-medium text-gray-700 mb-1">Pause (Min.)</label>
              <input
                id="break-minutes"
                type="number"
                min="0"
                max="480"
                value={formData.break_minutes}
                onChange={(e) => {
                  setFormData({ ...formData, break_minutes: parseInt(e.target.value) || 0 });
                  setErrors({});
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">&nbsp;</label>
              <button
                type="submit"
                className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition"
              >
                <Save size={18} />
                <span>Speichern</span>
              </button>
            </div>
            <div className="md:col-span-2 lg:col-span-5">
              <label htmlFor="tt-note" className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
              <input
                id="tt-note"
                type="text"
                value={formData.note}
                onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            {(new Date(formData.date + 'T12:00:00').getDay() === 0 ||
              (editingId && entries.find(e => e.id === editingId)?.is_sunday_or_holiday)) && (
              <div className="md:col-span-2 lg:col-span-5">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Ausnahmegrund (§10 ArbZG) <span className="text-gray-400 font-normal">– Sonn-/Feiertagsarbeit</span>
                </label>
                <input
                  type="text"
                  value={formData.sunday_exception_reason}
                  onChange={(e) => setFormData({ ...formData, sunday_exception_reason: e.target.value })}
                  placeholder="z. B. Notdienst, Patientenversorgung (§10 Nr. 1 ArbZG)"
                  className="w-full px-3 py-2 border border-amber-300 rounded-lg focus:ring-2 focus:ring-amber-400 bg-amber-50"
                />
              </div>
            )}
          </form>
        </div>
      )}

      {/* Month Selector */}
      <MonthSelector
        value={currentMonth}
        onChange={setCurrentMonth}
        className="mb-6"
      />

      {/* Entries Table/Cards */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {/* Desktop Table */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Datum</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tag</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Von</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Bis</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Pause</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Netto</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Notiz</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-6 py-4 text-center text-gray-500">
                    Lade Einträge...
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-4 text-center text-gray-500">
                    Keine Einträge für diesen Monat
                  </td>
                </tr>
              ) : (
                entries.map((entry) => {
                  const entryDate = new Date(entry.date + 'T00:00:00');
                  const weekday = weekdayNames[entryDate.getDay()];
                  return (
                    <tr key={entry.id} className={`hover:bg-gray-50 ${!entry.is_editable ? 'bg-gray-50/50' : ''} ${entry.is_sunday_or_holiday ? 'bg-orange-50/40' : ''}`}>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        <div className="flex flex-col gap-1">
                          <span>{format(entryDate, 'dd.MM.yyyy')}</span>
                          <div className="flex gap-1 flex-wrap">
                            {entry.is_sunday_or_holiday && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800" title="Sonn-/Feiertagsarbeit – §9/10 ArbZG">
                                So/FT
                              </span>
                            )}
                            {entry.is_night_work && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800" title="Nachtarbeit (23–6 Uhr) – §6 ArbZG">
                                Nacht
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{weekday}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">{entry.start_time.substring(0, 5)}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {entry.end_time ? entry.end_time.substring(0, 5) : <span className="text-green-600 font-medium">offen</span>}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{entry.break_minutes} min</td>
                      <td className="px-6 py-4 text-sm font-medium text-gray-900">
                        {entry.net_hours.toFixed(2)} h
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{entry.note || '-'}</td>
                      <td className="px-6 py-4 text-right text-sm space-x-1">
                        {entry.is_editable ? (
                          <>
                            <button
                              onClick={() => handleEdit(entry)}
                              className="text-primary hover:text-primary-dark"
                              aria-label={`Eintrag vom ${format(entryDate, 'dd.MM.yyyy')} bearbeiten`}
                            >
                              <Edit2 size={16} />
                            </button>
                            <button
                              onClick={() => handleDelete(entry.id)}
                              className="text-red-600 hover:text-red-800"
                              aria-label={`Eintrag vom ${format(entryDate, 'dd.MM.yyyy')} löschen`}
                            >
                              <Trash2 size={16} />
                            </button>
                          </>
                        ) : (
                          <>
                            <span title="Gesperrt"><Lock size={14} className="inline text-gray-400 mr-1" /></span>
                            <button
                              onClick={() => openChangeRequest(entry, 'update')}
                              className="text-amber-600 hover:text-amber-800"
                              aria-label={`Änderungsantrag für ${format(entryDate, 'dd.MM.yyyy')}`}
                              title="Änderungsantrag stellen"
                            >
                              <FileEdit size={16} />
                            </button>
                            <button
                              onClick={() => openChangeRequest(entry, 'delete')}
                              className="text-red-400 hover:text-red-600"
                              aria-label={`Löschantrag für ${format(entryDate, 'dd.MM.yyyy')}`}
                              title="Löschantrag stellen"
                            >
                              <Trash2 size={16} />
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
              {entries.length > 0 && (
                <tr className="bg-gray-50 font-semibold">
                  <td colSpan={5} className="px-6 py-4 text-sm text-gray-900">Summe</td>
                  <td className="px-6 py-4 text-sm text-gray-900">{totalNet.toFixed(2)} h</td>
                  <td colSpan={2}></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Cards */}
        <div className="md:hidden">
          {loading ? (
            <div className="p-6">
              <LoadingSpinner text="Lade Einträge..." />
            </div>
          ) : entries.length === 0 ? (
            <div className="p-6 text-center text-gray-500">
              Keine Einträge für diesen Monat
            </div>
          ) : (
            <>
              <div className="divide-y divide-gray-200">
                {entries.map((entry) => {
                  const entryDate = new Date(entry.date + 'T00:00:00');
                  const weekday = weekdayNames[entryDate.getDay()];
                  return (
                    <div key={entry.id} className={`p-4 ${!entry.is_editable ? 'bg-gray-50/50' : ''}`}>
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <p className="font-medium text-gray-900">
                            {format(entryDate, 'dd.MM.yyyy')}
                            {!entry.is_editable && (
                              <Lock size={12} className="inline ml-1 text-gray-400" />
                            )}
                          </p>
                          <p className="text-sm text-gray-500">{weekday}</p>
                        </div>
                        <div className="flex space-x-2">
                          {entry.is_editable ? (
                            <>
                              <button
                                onClick={() => handleEdit(entry)}
                                className="p-2 text-primary hover:bg-blue-50 rounded-lg transition"
                                aria-label={`Eintrag vom ${format(entryDate, 'dd.MM.yyyy')} bearbeiten`}
                              >
                                <Edit2 size={18} />
                              </button>
                              <button
                                onClick={() => handleDelete(entry.id)}
                                className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition"
                                aria-label={`Eintrag vom ${format(entryDate, 'dd.MM.yyyy')} löschen`}
                              >
                                <Trash2 size={18} />
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => openChangeRequest(entry, 'update')}
                                className="p-2 text-amber-600 hover:bg-amber-50 rounded-lg transition"
                                title="Änderungsantrag"
                              >
                                <FileEdit size={18} />
                              </button>
                              <button
                                onClick={() => openChangeRequest(entry, 'delete')}
                                className="p-2 text-red-400 hover:bg-red-50 rounded-lg transition"
                                title="Löschantrag"
                              >
                                <Trash2 size={18} />
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                      <div className="grid grid-cols-3 gap-3 text-sm">
                        <div>
                          <span className="text-gray-500 block">Von</span>
                          <p className="font-medium">{entry.start_time.substring(0, 5)}</p>
                        </div>
                        <div>
                          <span className="text-gray-500 block">Bis</span>
                          <p className="font-medium">
                            {entry.end_time ? entry.end_time.substring(0, 5) : <span className="text-green-600">offen</span>}
                          </p>
                        </div>
                        <div>
                          <span className="text-gray-500 block">Pause</span>
                          <p className="font-medium">{entry.break_minutes} min</p>
                        </div>
                      </div>
                      <div className="mt-3 pt-3 border-t border-gray-200">
                        <div className="flex justify-between items-center">
                          <span className="text-sm text-gray-500">Netto-Arbeitszeit</span>
                          <span className="text-lg font-bold text-primary">{entry.net_hours.toFixed(2)} h</span>
                        </div>
                        {entry.note && (
                          <p className="text-sm text-gray-600 mt-2">{entry.note}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              {entries.length > 0 && (
                <div className="p-4 bg-gray-50 border-t border-gray-200">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-gray-900">Summe</span>
                    <span className="text-lg font-bold text-primary">{totalNet.toFixed(2)} h</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
