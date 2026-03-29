import { useState, useEffect } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../../api/client';
import { Save, X } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { getErrorMessage } from '../../../utils/errorMessage';

interface YearCarryover {
  id: string;
  user_id: string;
  year: number;
  overtime_hours: number;
  vacation_days: number;
  created_at: string;
  updated_at: string;
}

interface CarryoverModalProps {
  userId: string;
  userName: string;
  onClose: () => void;
  onSaved: () => void;
}

export default function CarryoverModal({ userId, userName, onClose, onSaved }: CarryoverModalProps) {
  const toast = useToast();
  const [carryovers, setCarryovers] = useState<YearCarryover[]>([]);
  const [formData, setFormData] = useState({
    year: new Date().getFullYear(),
    overtime_hours: 0,
    vacation_days: 0,
  });

  useEffect(() => {
    fetchCarryovers();
  }, [userId]);

  const fetchCarryovers = async () => {
    try {
      const res = await apiClient.get(`/admin/users/${userId}/carryovers`);
      setCarryovers(res.data);

      // Pre-fill form with current year's carryover if it exists
      const currentYear = new Date().getFullYear();
      const existing = res.data.find((c: YearCarryover) => c.year === currentYear);
      if (existing) {
        setFormData({
          year: currentYear,
          overtime_hours: existing.overtime_hours,
          vacation_days: existing.vacation_days,
        });
      }
    } catch {
      setCarryovers([]);
    }
  };

  const handleYearChange = (year: number) => {
    const existing = carryovers.find(c => c.year === year);
    setFormData({
      year,
      overtime_hours: existing?.overtime_hours ?? 0,
      vacation_days: existing?.vacation_days ?? 0,
    });
  };

  const handleSubmit = async () => {
    try {
      await apiClient.put(
        `/admin/users/${userId}/carryovers/${formData.year}`,
        {
          overtime_hours: formData.overtime_hours,
          vacation_days: formData.vacation_days,
        }
      );
      toast.success(`Übernahme für ${formData.year} gespeichert`);
      // Refresh list
      const res = await apiClient.get(`/admin/users/${userId}/carryovers`);
      setCarryovers(res.data);
      onSaved();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, onDeactivate: onClose, initialFocus: false }}>
        <div className="bg-white rounded-xl shadow-lg max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900">
              Vorjahresübernahme: {userName}
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600"
            >
              <X size={20} />
            </button>
          </div>

          <p className="text-sm text-gray-600 mb-4">
            Überstunden und Resturlaub aus dem Vorjahr übernehmen. Die Werte werden auf das Stundenkonto bzw. den Jahresurlaub angerechnet.
          </p>

          {/* Year selector */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
            <select
              value={formData.year}
              onChange={(e) => handleYearChange(parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            >
              {Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i).map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Werte gelten als Übernahme <strong>in</strong> das gewählte Jahr
            </p>
          </div>

          {/* Overtime hours */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Überstunden aus Vorjahr (Stunden)</label>
            <input
              type="number"
              step="0.5"
              value={formData.overtime_hours}
              onChange={(e) => setFormData({ ...formData, overtime_hours: parseFloat(e.target.value) || 0 })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            />
            <p className="text-xs text-gray-500 mt-1">
              Positive Werte = Überstunden-Guthaben, negative = Minusstunden
            </p>
          </div>

          {/* Vacation days */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">Resturlaub aus Vorjahr (Tage)</label>
            <input
              type="number"
              step="0.5"
              value={formData.vacation_days}
              onChange={(e) => setFormData({ ...formData, vacation_days: parseFloat(e.target.value) || 0 })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            />
            <p className="text-xs text-gray-500 mt-1">
              Wird zum Jahresurlaub {formData.year} addiert
            </p>
          </div>

          <button
            onClick={handleSubmit}
            className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-3 rounded-lg flex items-center justify-center space-x-2 transition mb-3"
          >
            <Save size={18} />
            <span>Speichern</span>
          </button>

          {/* Existing carryovers table */}
          {carryovers.length > 0 && (
            <div className="mt-4 border-t border-gray-200 pt-4">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Gespeicherte Übernahmen</h4>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b">
                    <th className="py-1 pr-4">Jahr</th>
                    <th className="py-1 pr-4">Überstunden</th>
                    <th className="py-1">Resturlaub</th>
                  </tr>
                </thead>
                <tbody>
                  {carryovers.map(c => (
                    <tr
                      key={c.id}
                      className={`border-b border-gray-100 cursor-pointer hover:bg-gray-50 ${c.year === formData.year ? 'bg-blue-50' : ''}`}
                      onClick={() => handleYearChange(c.year)}
                    >
                      <td className="py-1.5 pr-4 font-medium">{c.year}</td>
                      <td className={`py-1.5 pr-4 ${c.overtime_hours >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {c.overtime_hours >= 0 ? '+' : ''}{c.overtime_hours.toFixed(1)}h
                      </td>
                      <td className="py-1.5">{c.vacation_days.toFixed(1)} Tage</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <button
            onClick={onClose}
            className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg transition mt-3"
          >
            Schließen
          </button>
        </div>
      </FocusTrap>
    </div>
  );
}
