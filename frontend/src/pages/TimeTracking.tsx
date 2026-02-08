import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import apiClient from '../api/client';
import { Plus, Edit2, Trash2, Save, X } from 'lucide-react';

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
    break_minutes: 30,
    note: '',
  });

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingId) {
        await apiClient.put(`/time-entries/${editingId}`, formData);
      } else {
        await apiClient.post('/time-entries', formData);
      }
      fetchEntries();
      resetForm();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Fehler beim Speichern');
    }
  };

  const handleEdit = (entry: TimeEntry) => {
    setEditingId(entry.id);
    setFormData({
      date: entry.date,
      start_time: entry.start_time.substring(0, 5),
      end_time: entry.end_time.substring(0, 5),
      break_minutes: entry.break_minutes,
      note: entry.note || '',
    });
    setShowForm(true);
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Möchten Sie diesen Eintrag wirklich löschen?')) return;
    try {
      await apiClient.delete(`/time-entries/${id}`);
      fetchEntries();
    } catch (error) {
      alert('Fehler beim Löschen');
    }
  };

  const resetForm = () => {
    setShowForm(false);
    setEditingId(null);
    setFormData({
      date: format(new Date(), 'yyyy-MM-dd'),
      start_time: '08:00',
      end_time: '17:00',
      break_minutes: 30,
      note: '',
    });
  };

  const totalNet = entries.reduce((sum, entry) => sum + entry.net_hours, 0);

  const weekdayNames = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];

  return (
    <div>
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
          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Datum</label>
              <input
                type="date"
                value={formData.date}
                onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Von</label>
              <input
                type="time"
                value={formData.start_time}
                onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
              <input
                type="time"
                value={formData.end_time}
                onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Pause (Min)</label>
              <input
                type="number"
                value={formData.break_minutes}
                onChange={(e) => setFormData({ ...formData, break_minutes: parseInt(e.target.value) })}
                min="0"
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="md:col-span-2 lg:col-span-1">
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
      <div className="mb-4">
        <input
          type="month"
          value={currentMonth}
          onChange={(e) => setCurrentMonth(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-lg"
        />
      </div>

      {/* Entries Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
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
                    <tr key={entry.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {format(entryDate, 'dd.MM.yyyy')}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{weekday}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">{entry.start_time.substring(0, 5)}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">{entry.end_time.substring(0, 5)}</td>
                      <td className="px-6 py-4 text-sm text-gray-900">{entry.break_minutes} min</td>
                      <td className="px-6 py-4 text-sm font-medium text-gray-900">
                        {entry.net_hours.toFixed(2)} h
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">{entry.note || '-'}</td>
                      <td className="px-6 py-4 text-right text-sm space-x-2">
                        <button
                          onClick={() => handleEdit(entry)}
                          className="text-primary hover:text-primary-dark"
                        >
                          <Edit2 size={16} />
                        </button>
                        <button
                          onClick={() => handleDelete(entry.id)}
                          className="text-red-600 hover:text-red-800"
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
                  <td colSpan={5} className="px-6 py-4 text-sm text-gray-900">Summe</td>
                  <td className="px-6 py-4 text-sm text-gray-900">{totalNet.toFixed(2)} h</td>
                  <td colSpan={2}></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
