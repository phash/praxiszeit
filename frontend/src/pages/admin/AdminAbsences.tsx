import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { Plus, X, Trash2, ChevronDown, ChevronUp } from 'lucide-react';
import apiClient from '../../api/client';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';
import { ABSENCE_TYPE_LABELS, ABSENCE_TYPE_COLORS } from '../../constants/absenceTypes';
import MonthSelector from '../../components/MonthSelector';

interface Employee {
  id: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
}

interface Absence {
  id: string;
  date: string;
  end_date?: string;
  type: 'vacation' | 'sick' | 'training' | 'other';
  hours: number;
  note?: string;
}

export default function AdminAbsences() {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selectedEmployee, setSelectedEmployee] = useState<string>('');
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [absences, setAbsences] = useState<Absence[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [isDateRange, setIsDateRange] = useState(false);
  const [expandedEmployees, setExpandedEmployees] = useState<Record<string, boolean>>({});
  const [allAbsences, setAllAbsences] = useState<Record<string, Absence[]>>({});
  const [formData, setFormData] = useState({
    date: format(new Date(), 'yyyy-MM-dd'),
    end_date: '',
    type: 'vacation' as 'vacation' | 'sick' | 'training' | 'other',
    hours: 8,
    note: '',
  });

  const typeLabels = ABSENCE_TYPE_LABELS;
  const typeColors = ABSENCE_TYPE_COLORS;

  useEffect(() => {
    loadEmployees();
  }, []);

  useEffect(() => {
    if (selectedEmployee) {
      loadAbsences(selectedEmployee);
    } else {
      loadAllAbsences();
    }
  }, [selectedEmployee, currentMonth]);

  const loadEmployees = async () => {
    try {
      const res = await apiClient.get('/admin/users');
      setEmployees(res.data.filter((u: Employee) => u.is_active));
    } catch {
      toast.error('Fehler beim Laden der Mitarbeiter');
    }
  };

  const loadAbsences = async (userId: string) => {
    try {
      const year = currentMonth.split('-')[0];
      const res = await apiClient.get(`/absences?user_id=${userId}&year=${year}`);
      setAbsences(res.data);
    } catch {
      toast.error('Fehler beim Laden der Abwesenheiten');
    }
  };

  const loadAllAbsences = async () => {
    const year = currentMonth.split('-')[0];
    const result: Record<string, Absence[]> = {};
    await Promise.all(
      employees.map(async (emp) => {
        try {
          const res = await apiClient.get(`/absences?user_id=${emp.id}&year=${year}`);
          result[emp.id] = res.data.filter((a: Absence) => {
            const aMonth = a.date.substring(0, 7);
            return aMonth === currentMonth || (a.end_date && a.end_date.substring(0, 7) >= currentMonth && a.date.substring(0, 7) <= currentMonth);
          });
        } catch {
          result[emp.id] = [];
        }
      })
    );
    setAllAbsences(result);
  };

  useEffect(() => {
    if (!selectedEmployee && employees.length > 0) {
      loadAllAbsences();
    }
  }, [employees, currentMonth]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const targetId = selectedEmployee || '';
    if (!targetId) {
      toast.error('Bitte wählen Sie einen Mitarbeiter aus');
      return;
    }
    try {
      await apiClient.post('/absences', {
        user_id: targetId,
        date: formData.date,
        end_date: isDateRange && formData.end_date ? formData.end_date : null,
        type: formData.type,
        hours: formData.hours,
        note: formData.note || null,
      });
      toast.success('Abwesenheit erfolgreich eingetragen');
      setShowForm(false);
      setIsDateRange(false);
      setFormData({ date: format(new Date(), 'yyyy-MM-dd'), end_date: '', type: 'vacation', hours: 8, note: '' });
      loadAbsences(targetId);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Fehler beim Speichern');
    }
  };

  const handleDelete = (id: string, userId: string) => {
    confirm({
      title: 'Abwesenheit löschen',
      message: 'Möchten Sie diese Abwesenheit wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await apiClient.delete(`/absences/${id}`);
          toast.success('Abwesenheit gelöscht');
          if (selectedEmployee) {
            loadAbsences(userId);
          } else {
            loadAllAbsences();
          }
        } catch {
          toast.error('Fehler beim Löschen');
        }
      },
    });
  };

  const toggleEmployee = (empId: string) => {
    setExpandedEmployees(prev => ({ ...prev, [empId]: !prev[empId] }));
  };

  const filteredAbsences = selectedEmployee
    ? absences.filter(a => a.date.startsWith(currentMonth) || (a.end_date && a.end_date >= currentMonth + '-01' && a.date <= currentMonth + '-31'))
    : [];

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
        <h1 className="text-3xl font-bold text-gray-900">Abwesenheiten verwalten</h1>
        {selectedEmployee && (
          <button
            onClick={() => setShowForm(!showForm)}
            className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
          >
            {showForm ? <X size={20} /> : <Plus size={20} />}
            <span>{showForm ? 'Abbrechen' : 'Abwesenheit eintragen'}</span>
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-6">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-48">
            <label className="block text-sm font-medium text-gray-700 mb-1">Mitarbeiter</label>
            <select
              value={selectedEmployee}
              onChange={e => { setSelectedEmployee(e.target.value); setShowForm(false); }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
            >
              <option value="">Alle Mitarbeiter</option>
              {employees.map(emp => (
                <option key={emp.id} value={emp.id}>
                  {emp.first_name} {emp.last_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Monat</label>
            <MonthSelector value={currentMonth} onChange={setCurrentMonth} />
          </div>
        </div>
      </div>

      {/* Form for selected employee */}
      {showForm && selectedEmployee && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">
            Abwesenheit eintragen für{' '}
            {employees.find(e => e.id === selectedEmployee)?.first_name}{' '}
            {employees.find(e => e.id === selectedEmployee)?.last_name}
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
              <input
                type="checkbox"
                id="isDateRange"
                checked={isDateRange}
                onChange={e => { setIsDateRange(e.target.checked); if (!e.target.checked) setFormData(p => ({ ...p, end_date: '' })); }}
                className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
              />
              <label htmlFor="isDateRange" className="text-sm font-medium text-gray-700 cursor-pointer">
                Zeitraum (mehrere Tage)
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{isDateRange ? 'Von' : 'Datum'}</label>
                <input
                  type="date"
                  value={formData.date}
                  onChange={e => setFormData(p => ({ ...p, date: e.target.value }))}
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
                    onChange={e => setFormData(p => ({ ...p, end_date: e.target.value }))}
                    required
                    min={formData.date}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Typ</label>
                <select
                  value={formData.type}
                  onChange={e => setFormData(p => ({ ...p, type: e.target.value as any }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                >
                  <option value="vacation">Urlaub</option>
                  <option value="sick">Krank</option>
                  <option value="training">Fortbildung</option>
                  <option value="other">Sonstiges</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Stunden{isDateRange && ' (pro Tag)'}</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.hours}
                  onChange={e => setFormData(p => ({ ...p, hours: parseFloat(e.target.value) }))}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
              <input
                type="text"
                value={formData.note}
                onChange={e => setFormData(p => ({ ...p, note: e.target.value }))}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>

            <button
              type="submit"
              className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg transition"
            >
              Speichern
            </button>
          </form>
        </div>
      )}

      {/* Single employee view */}
      {selectedEmployee ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="font-semibold">
              Abwesenheiten von {employees.find(e => e.id === selectedEmployee)?.first_name}{' '}
              {employees.find(e => e.id === selectedEmployee)?.last_name} – {currentMonth}
            </h3>
          </div>
          {filteredAbsences.length === 0 ? (
            <div className="p-6 text-center text-gray-500">Keine Abwesenheiten in diesem Monat</div>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Datum</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Typ</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Stunden</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Notiz</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Aktion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {filteredAbsences.map(absence => (
                  <tr key={absence.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {absence.end_date
                        ? `${format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')} – ${format(new Date(absence.end_date + 'T00:00:00'), 'dd.MM.yyyy')}`
                        : format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy, EEEE', { locale: de })}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`px-2 py-1 rounded text-xs ${typeColors[absence.type]}`}>
                        {typeLabels[absence.type]}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{absence.hours} h</td>
                    <td className="px-6 py-4 text-sm text-gray-500">{absence.note || '–'}</td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => handleDelete(absence.id, selectedEmployee)}
                        className="p-1.5 text-red-600 hover:bg-red-50 rounded transition"
                        aria-label="Löschen"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        /* All employees overview */
        <div className="space-y-3">
          {employees.map(emp => {
            const empAbsences = allAbsences[emp.id] || [];
            const isExpanded = expandedEmployees[emp.id];
            return (
              <div key={emp.id} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                <button
                  onClick={() => toggleEmployee(emp.id)}
                  className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-50 transition"
                >
                  <div className="flex items-center space-x-3">
                    <span className="font-semibold text-gray-900">
                      {emp.first_name} {emp.last_name}
                    </span>
                    {empAbsences.length > 0 && (
                      <span className="text-sm text-gray-500">
                        {empAbsences.length} Eintrag{empAbsences.length !== 1 ? 'träge' : ''}
                      </span>
                    )}
                    {empAbsences.length === 0 && (
                      <span className="text-sm text-gray-400">Keine Abwesenheiten</span>
                    )}
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={e => {
                        e.stopPropagation();
                        setSelectedEmployee(emp.id);
                        setShowForm(true);
                      }}
                      className="text-xs bg-primary text-white px-2 py-1 rounded hover:bg-primary-dark transition"
                    >
                      + Eintragen
                    </button>
                    {isExpanded ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
                  </div>
                </button>

                {isExpanded && empAbsences.length > 0 && (
                  <div className="border-t border-gray-200">
                    <table className="w-full">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Datum</th>
                          <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Typ</th>
                          <th className="px-6 py-2 text-left text-xs font-medium text-gray-500 uppercase">Std.</th>
                          <th className="px-6 py-2 text-right text-xs font-medium text-gray-500 uppercase">Aktion</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {empAbsences.map(absence => (
                          <tr key={absence.id} className="hover:bg-gray-50">
                            <td className="px-6 py-3 text-sm text-gray-900">
                              {absence.end_date
                                ? `${format(new Date(absence.date + 'T00:00:00'), 'dd.MM.')} – ${format(new Date(absence.end_date + 'T00:00:00'), 'dd.MM.yyyy')}`
                                : format(new Date(absence.date + 'T00:00:00'), 'dd.MM.yyyy')}
                            </td>
                            <td className="px-6 py-3 text-sm">
                              <span className={`px-2 py-0.5 rounded text-xs ${typeColors[absence.type]}`}>
                                {typeLabels[absence.type]}
                              </span>
                            </td>
                            <td className="px-6 py-3 text-sm text-gray-900">{absence.hours} h</td>
                            <td className="px-6 py-3 text-right">
                              <button
                                onClick={() => handleDelete(absence.id, emp.id)}
                                className="p-1 text-red-600 hover:bg-red-50 rounded transition"
                                aria-label="Löschen"
                              >
                                <Trash2 size={14} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
