import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import apiClient from '../api/client';
import { Plus, Edit2, Trash2, Save, X } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from '../components/ConfirmDialog';
import LoadingSpinner from '../components/LoadingSpinner';
import MonthSelector from '../components/MonthSelector';

interface TimeEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string;
  break_minutes: number;
  net_hours: number;
  note?: string;
}

export default function TimeTracking() {
  const toast = useToast();
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
    note: '',
  });
  const [errors, setErrors] = useState<{
    start_time?: string;
    end_time?: string;
    overlap?: string;
  }>({});
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  useEffect(() => {
    fetchEntries();
  }, [currentMonth]);

  const fetchEntries = async () => {
    try {
      const response = await apiClient.get(`/time-entries?month=${currentMonth}`);
      setEntries(response.data);
    } catch (error) {
      console.error('Failed to fetch time entries:', error);
    } finally {
      setLoading(false);
    }
  };

  const validateTimeEntry = (): boolean => {
    const newErrors: typeof errors = {};

    // Validate start < end
    if (formData.start_time >= formData.end_time) {
      newErrors.end_time = 'Endzeit muss nach Startzeit liegen';
    }

    // Check for overlapping entries on the same day
    const sameDay = entries.filter(
      (entry) => entry.date === formData.date && entry.id !== editingId
    );

    const newStart = formData.start_time;
    const newEnd = formData.end_time;

    for (const entry of sameDay) {
      const existingStart = entry.start_time.substring(0, 5);
      const existingEnd = entry.end_time.substring(0, 5);

      // Check for overlap: new entry starts before existing ends AND new entry ends after existing starts
      if (newStart < existingEnd && newEnd > existingStart) {
        newErrors.overlap = `Überschneidung mit bestehendem Eintrag (${existingStart} - ${existingEnd})`;
        break;
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validate before submitting
    if (!validateTimeEntry()) {
      return;
    }

    try {
      if (editingId) {
        await apiClient.put(`/time-entries/${editingId}`, formData);
        toast.success('Zeiteintrag erfolgreich aktualisiert');
      } else {
        await apiClient.post('/time-entries', formData);
        toast.success('Zeiteintrag erfolgreich erstellt');
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
      end_time: entry.end_time.substring(0, 5),
      note: entry.note || '',
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

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setFormData({
      date: format(new Date(), 'yyyy-MM-dd'),
      start_time: '08:00',
      end_time: '17:00',
      note: '',
    });
    setErrors({});
  };

  const totalNet = entries.reduce((sum, entry) => sum + entry.net_hours, 0);

  const weekdayNames = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];

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
        <h1 className="text-3xl font-bold text-gray-900">Zeiterfassung</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
        >
          {showForm ? <X size={20} /> : <Plus size={20} />}
          <span>{showForm ? 'Abbrechen' : 'Neuer Eintrag'}</span>
        </button>
      </div>

      {/* Entry Form */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">
            {editingId ? 'Eintrag bearbeiten' : 'Neuer Zeiteintrag'}
          </h3>
          {/* Error Message for Overlapping Times */}
          {errors.overlap && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg" role="alert">
              <p className="text-sm text-red-800 font-medium">{errors.overlap}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Datum</label>
              <input
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
              <label className="block text-sm font-medium text-gray-700 mb-1">&nbsp;</label>
              <button
                type="submit"
                className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition"
              >
                <Save size={18} />
                <span>Speichern</span>
              </button>
            </div>
            <div className="md:col-span-2 lg:col-span-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
              <input
                type="text"
                value={formData.note}
                onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
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
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Netto</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Notiz</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-4 text-center text-gray-500">
                    Lade Einträge...
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-4 text-center text-gray-500">
                    Keine Einträge für diesen Monat
                  </td>
                </tr>
              ) : (
                entries.map((entry) => {
                  const entryDate = new Date(entry.date + 'T00:00:00');
                  const weekday = weekdayNames[entryDate.getDay()];
                  return (
                    <tr key={entry.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {format(entryDate, 'dd.MM.yyyy')}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{weekday}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">{entry.start_time.substring(0, 5)}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">{entry.end_time.substring(0, 5)}</td>
                      <td className="px-6 py-4 text-sm font-medium text-gray-900">
                        {entry.net_hours.toFixed(2)} h
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{entry.note || '-'}</td>
                      <td className="px-6 py-4 text-right text-sm space-x-2">
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
                      </td>
                    </tr>
                  );
                })
              )}
              {entries.length > 0 && (
                <tr className="bg-gray-50 font-semibold">
                  <td colSpan={4} className="px-6 py-4 text-sm text-gray-900">Summe</td>
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
                    <div key={entry.id} className="p-4">
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <p className="font-medium text-gray-900">
                            {format(entryDate, 'dd.MM.yyyy')}
                          </p>
                          <p className="text-sm text-gray-500">{weekday}</p>
                        </div>
                        <div className="flex space-x-2">
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
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <span className="text-gray-500 block">Von</span>
                          <p className="font-medium">{entry.start_time.substring(0, 5)}</p>
                        </div>
                        <div>
                          <span className="text-gray-500 block">Bis</span>
                          <p className="font-medium">{entry.end_time.substring(0, 5)}</p>
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
