import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import apiClient from '../../api/client';
import { Users, Clock, TrendingUp, X, Calendar, FileText } from 'lucide-react';

interface EmployeeReport {
  user_id: string;
  first_name: string;
  last_name: string;
  weekly_hours: number;
  target_hours: number;
  actual_hours: number;
  balance: number;
  overtime_cumulative: number;
  vacation_used_hours: number;
  sick_hours: number;
}

interface TimeEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string;
  break_minutes: number;
  note?: string;
}

interface Absence {
  id: string;
  date: string;
  type: string;
  hours: number;
  note?: string;
}

interface YearlyAbsences {
  user_id: string;
  first_name: string;
  last_name: string;
  vacation_days: number;
  sick_days: number;
  training_days: number;
  other_days: number;
  total_days: number;
}

export default function AdminDashboard() {
  const [report, setReport] = useState<EmployeeReport[]>([]);
  const [yearlyAbsences, setYearlyAbsences] = useState<YearlyAbsences[]>([]);
  const [loading, setLoading] = useState(true);
  const [yearlyLoading, setYearlyLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeReport | null>(null);
  const [employeeTimeEntries, setEmployeeTimeEntries] = useState<TimeEntry[]>([]);
  const [employeeAbsences, setEmployeeAbsences] = useState<Absence[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    fetchReport();
  }, [currentMonth]);

  useEffect(() => {
    fetchYearlyAbsences();
  }, [currentYear]);

  const fetchReport = async () => {
    try {
      const response = await apiClient.get(`/admin/reports/monthly?month=${currentMonth}`);
      setReport(response.data);
    } catch (error) {
      console.error('Failed to fetch report:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchYearlyAbsences = async () => {
    try {
      const response = await apiClient.get(`/admin/reports/yearly-absences?year=${currentYear}`);
      setYearlyAbsences(response.data);
    } catch (error) {
      console.error('Failed to fetch yearly absences:', error);
    } finally {
      setYearlyLoading(false);
    }
  };

  const fetchEmployeeDetails = async (employee: EmployeeReport) => {
    setSelectedEmployee(employee);
    setDetailLoading(true);
    try {
      const [year, month] = currentMonth.split('-');

      // Fetch time entries
      const entriesResponse = await apiClient.get('/time-entries', {
        params: {
          user_id: employee.user_id,
          year: parseInt(year),
          month: parseInt(month)
        }
      });
      setEmployeeTimeEntries(entriesResponse.data);

      // Fetch absences
      const absencesResponse = await apiClient.get('/absences', {
        params: {
          user_id: employee.user_id,
          year: parseInt(year),
          month: parseInt(month)
        }
      });
      setEmployeeAbsences(absencesResponse.data);
    } catch (error) {
      console.error('Failed to fetch employee details:', error);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setSelectedEmployee(null);
    setEmployeeTimeEntries([]);
    setEmployeeAbsences([]);
  };

  const totalEmployees = report.length;
  const avgBalance = report.length > 0
    ? report.reduce((sum, emp) => sum + emp.balance, 0) / report.length
    : 0;

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Admin-Dashboard</h1>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-600">Mitarbeiterinnen</h3>
            <Users className="text-primary" size={24} />
          </div>
          <p className="text-3xl font-bold text-gray-900">{totalEmployees}</p>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-600">Ø Saldo (Monat)</h3>
            <TrendingUp
              className={avgBalance >= 0 ? 'text-green-600' : 'text-red-600'}
              size={24}
            />
          </div>
          <p className={`text-3xl font-bold ${avgBalance >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {avgBalance >= 0 ? '+' : ''}
            {avgBalance.toFixed(2)} h
          </p>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-600">Monat</h3>
            <Clock className="text-primary" size={24} />
          </div>
          <p className="text-xl font-bold text-gray-900">
            {format(new Date(currentMonth + '-01'), 'MMMM yyyy')}
          </p>
        </div>
      </div>

      {/* Month Selector */}
      <div className="mb-4">
        <input
          type="month"
          value={currentMonth}
          onChange={(e) => setCurrentMonth(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-lg"
        />
      </div>

      {/* Employee Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold">Mitarbeiterübersicht</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Wochenstd.</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Soll</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ist</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Saldo</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Überstd. kum.</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Urlaub (h)</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Krank (h)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-6 py-4 text-center text-gray-500">
                    Lade Daten...
                  </td>
                </tr>
              ) : report.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-4 text-center text-gray-500">
                    Keine Daten verfügbar
                  </td>
                </tr>
              ) : (
                report.map((emp) => (
                  <tr
                    key={emp.user_id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => fetchEmployeeDetails(emp)}
                  >
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {emp.last_name}, {emp.first_name}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{emp.weekly_hours}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{emp.target_hours.toFixed(2)}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{emp.actual_hours.toFixed(2)}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={emp.balance >= 0 ? 'text-green-600' : 'text-red-600'}>
                        {emp.balance >= 0 ? '+' : ''}
                        {emp.balance.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={emp.overtime_cumulative >= 0 ? 'text-green-600' : 'text-red-600'}>
                        {emp.overtime_cumulative >= 0 ? '+' : ''}
                        {emp.overtime_cumulative.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{emp.vacation_used_hours.toFixed(2)}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{emp.sick_hours.toFixed(2)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Yearly Absences Overview */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-gray-900">Jahresübersicht - Abwesenheiten</h2>
          <div className="flex items-center space-x-3">
            <input
              type="number"
              value={currentYear}
              onChange={(e) => setCurrentYear(parseInt(e.target.value))}
              min="2020"
              max="2030"
              className="px-4 py-2 border border-gray-300 rounded-lg"
            />
            <Link
              to="/admin/reports"
              className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
              title="Zu Berichte & Export"
            >
              <FileText size={20} />
              <span>Berichte</span>
            </Link>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Urlaub</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-blue-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Krank</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-red-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Fortbildung</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-orange-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    <span className="flex items-center justify-end space-x-1">
                      <span>Sonstiges</span>
                      <span className="inline-block w-3 h-3 rounded-full bg-gray-500"></span>
                    </span>
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Gesamt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {yearlyLoading ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-4 text-center text-gray-500">
                      Lade Daten...
                    </td>
                  </tr>
                ) : yearlyAbsences.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-4 text-center text-gray-500">
                      Keine Daten verfügbar
                    </td>
                  </tr>
                ) : (
                  yearlyAbsences.map((emp) => (
                    <tr key={emp.user_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm font-medium text-gray-900">
                        {emp.last_name}, {emp.first_name}
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {emp.vacation_days.toFixed(1)} Tage
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                          {emp.sick_days.toFixed(1)} Tage
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                          {emp.training_days.toFixed(1)} Tage
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                          {emp.other_days.toFixed(1)} Tage
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm font-bold text-gray-900">
                        {emp.total_days.toFixed(1)} Tage
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Employee Detail Modal */}
      {selectedEmployee && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            {/* Header */}
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-primary text-white">
              <div>
                <h2 className="text-2xl font-bold">
                  {selectedEmployee.last_name}, {selectedEmployee.first_name}
                </h2>
                <p className="text-sm opacity-90">
                  {format(new Date(currentMonth + '-01'), 'MMMM yyyy')} - Details
                </p>
              </div>
              <button
                onClick={closeDetail}
                className="hover:bg-white hover:bg-opacity-20 rounded-lg p-2 transition"
              >
                <X size={24} />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {detailLoading ? (
                <div className="text-center py-8 text-gray-500">Lade Details...</div>
              ) : (
                <div className="space-y-6">
                  {/* Summary Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-gray-50 rounded-lg p-4">
                      <p className="text-xs text-gray-500 mb-1">Soll</p>
                      <p className="text-xl font-bold">{selectedEmployee.target_hours.toFixed(2)} h</p>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-4">
                      <p className="text-xs text-gray-500 mb-1">Ist</p>
                      <p className="text-xl font-bold">{selectedEmployee.actual_hours.toFixed(2)} h</p>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-4">
                      <p className="text-xs text-gray-500 mb-1">Saldo</p>
                      <p
                        className={`text-xl font-bold ${
                          selectedEmployee.balance >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {selectedEmployee.balance >= 0 ? '+' : ''}
                        {selectedEmployee.balance.toFixed(2)} h
                      </p>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-4">
                      <p className="text-xs text-gray-500 mb-1">Überstunden kum.</p>
                      <p
                        className={`text-xl font-bold ${
                          selectedEmployee.overtime_cumulative >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {selectedEmployee.overtime_cumulative >= 0 ? '+' : ''}
                        {selectedEmployee.overtime_cumulative.toFixed(2)} h
                      </p>
                    </div>
                  </div>

                  {/* Time Entries */}
                  <div className="bg-white border border-gray-200 rounded-lg">
                    <div className="px-4 py-3 border-b border-gray-200 flex items-center space-x-2">
                      <Clock size={20} className="text-primary" />
                      <h3 className="font-semibold">Zeiteinträge ({employeeTimeEntries.length})</h3>
                    </div>
                    <div className="max-h-60 overflow-y-auto">
                      {employeeTimeEntries.length === 0 ? (
                        <p className="px-4 py-3 text-sm text-gray-500">Keine Zeiteinträge vorhanden</p>
                      ) : (
                        <table className="w-full">
                          <thead className="bg-gray-50 sticky top-0">
                            <tr>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Datum</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Von</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Bis</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Pause</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Notiz</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-200">
                            {employeeTimeEntries.map((entry) => (
                              <tr key={entry.id}>
                                <td className="px-4 py-2 text-sm">{format(new Date(entry.date), 'dd.MM.yyyy')}</td>
                                <td className="px-4 py-2 text-sm">{entry.start_time}</td>
                                <td className="px-4 py-2 text-sm">{entry.end_time}</td>
                                <td className="px-4 py-2 text-sm">{entry.break_minutes} min</td>
                                <td className="px-4 py-2 text-sm text-gray-500">{entry.note || '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>

                  {/* Absences */}
                  <div className="bg-white border border-gray-200 rounded-lg">
                    <div className="px-4 py-3 border-b border-gray-200 flex items-center space-x-2">
                      <Calendar size={20} className="text-primary" />
                      <h3 className="font-semibold">Abwesenheiten ({employeeAbsences.length})</h3>
                    </div>
                    <div className="max-h-60 overflow-y-auto">
                      {employeeAbsences.length === 0 ? (
                        <p className="px-4 py-3 text-sm text-gray-500">Keine Abwesenheiten vorhanden</p>
                      ) : (
                        <table className="w-full">
                          <thead className="bg-gray-50 sticky top-0">
                            <tr>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Datum</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Typ</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Stunden</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Notiz</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-200">
                            {employeeAbsences.map((absence) => (
                              <tr key={absence.id}>
                                <td className="px-4 py-2 text-sm">{format(new Date(absence.date), 'dd.MM.yyyy')}</td>
                                <td className="px-4 py-2 text-sm">
                                  <span
                                    className={`px-2 py-1 rounded text-xs font-medium ${
                                      absence.type === 'vacation'
                                        ? 'bg-blue-100 text-blue-800'
                                        : absence.type === 'sick'
                                        ? 'bg-red-100 text-red-800'
                                        : absence.type === 'training'
                                        ? 'bg-orange-100 text-orange-800'
                                        : 'bg-gray-100 text-gray-800'
                                    }`}
                                  >
                                    {absence.type === 'vacation'
                                      ? 'Urlaub'
                                      : absence.type === 'sick'
                                      ? 'Krank'
                                      : absence.type === 'training'
                                      ? 'Fortbildung'
                                      : 'Sonstiges'}
                                  </span>
                                </td>
                                <td className="px-4 py-2 text-sm">{absence.hours} h</td>
                                <td className="px-4 py-2 text-sm text-gray-500">{absence.note || '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end">
              <button
                onClick={closeDetail}
                className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg transition"
              >
                Schließen
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
