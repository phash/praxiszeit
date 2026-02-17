import { useState } from 'react';
import { format } from 'date-fns';
import { Download, Calendar, FileText, Clock, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import apiClient from '../../api/client';
import { useToast } from '../../contexts/ToastContext';

interface RestViolation {
  day1_date: string;
  day1_end: string;
  day2_date: string;
  day2_start: string;
  actual_rest_hours: number;
  min_rest_hours: number;
  deficit_hours: number;
}

interface EmployeeViolations {
  user_id: string;
  first_name: string;
  last_name: string;
  violations: RestViolation[];
  violation_count: number;
}

export default function Reports() {
  const [selectedMonth, setSelectedMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  // Rest time violations
  const [restYear, setRestYear] = useState(new Date().getFullYear());
  const [restMonth, setRestMonth] = useState<number | ''>('');
  const [minRestHours, setMinRestHours] = useState(11);
  const [restViolations, setRestViolations] = useState<EmployeeViolations[] | null>(null);
  const [restLoading, setRestLoading] = useState(false);
  const [expandedViolations, setExpandedViolations] = useState<Record<string, boolean>>({});

  const checkRestViolations = async () => {
    setRestLoading(true);
    try {
      const params = new URLSearchParams({ year: String(restYear), min_rest_hours: String(minRestHours) });
      if (restMonth) params.set('month', String(restMonth));
      const res = await apiClient.get(`/admin/reports/rest-time-violations?${params}`);
      setRestViolations(res.data.violations);
      if (res.data.total_violations === 0) {
        toast.success('Keine Ruhezeitverstöße gefunden');
      }
    } catch {
      toast.error('Fehler beim Laden der Ruhezeitprüfung');
    } finally {
      setRestLoading(false);
    }
  };

  const handleMonthlyExport = () => {
    // Download Excel file
    const url = `/api/admin/reports/export?month=${selectedMonth}`;
    window.open(url, '_blank');
  };

  const handleYearlyExport = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(`/admin/reports/export-yearly?year=${selectedYear}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `PraxisZeit_Jahresreport_${selectedYear}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      toast.error('Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleYearlyClassicExport = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(`/admin/reports/export-yearly-classic?year=${selectedYear}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `PraxisZeit_Jahresreport_Classic_${selectedYear}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      toast.error('Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Berichte & Export</h1>

      {/* Monthly Export Section */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 mb-8">
        <div className="flex items-center space-x-3 mb-4">
          <Calendar className="text-primary" size={24} />
          <h2 className="text-xl font-semibold">Monatsreport exportieren</h2>
        </div>
        <div className="max-w-2xl">
          <p className="text-gray-600 mb-6">
            Exportieren Sie einen detaillierten Monatsreport für alle Mitarbeitende als Excel-Datei.
            Die Datei enthält für jede Mitarbeiter:in ein separates Sheet mit allen Zeiteinträgen,
            Abwesenheiten und einer Zusammenfassung.
          </p>

          <div className="flex items-end space-x-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Monat auswählen
              </label>
              <input
                type="month"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
            <button
              onClick={handleMonthlyExport}
              className="bg-primary hover:bg-primary-dark text-white px-6 py-3 rounded-lg flex items-center space-x-2 transition"
            >
              <Download size={20} />
              <span>Excel exportieren</span>
            </button>
          </div>

          <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <h3 className="font-semibold text-blue-900 mb-2">Was enthält der Export?</h3>
            <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
              <li>Ein Sheet pro Mitarbeiter:in</li>
              <li>Tägliche Zeiteinträge (Datum, Von, Bis, Pause, Netto)</li>
              <li>Soll-Stunden pro Tag</li>
              <li>Markierung von Wochenenden, Feiertagen und Abwesenheiten</li>
              <li>Monatszusammenfassung (Soll, Ist, Saldo, Überstunden kumuliert, Urlaub)</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Yearly Export Section */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 mb-8">
        <div className="flex items-center space-x-3 mb-4">
          <FileText className="text-primary" size={24} />
          <h2 className="text-xl font-semibold">Jahresreport exportieren</h2>
        </div>
        <div className="max-w-2xl">
          <p className="text-gray-600 mb-6">
            Exportieren Sie einen Jahresreport mit zwei verschiedenen Formaten zur Auswahl.
          </p>

          <div className="flex items-end space-x-4 mb-6">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Jahr auswählen
              </label>
              <input
                type="number"
                value={selectedYear}
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                min="2020"
                max="2050"
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          {/* Export Options */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Classic Format */}
            <div className="border border-gray-300 rounded-lg p-5 hover:border-primary transition">
              <h3 className="font-semibold text-gray-900 mb-2 flex items-center space-x-2">
                <span>📋</span>
                <span>Classic Format</span>
              </h3>
              <p className="text-sm text-gray-600 mb-4">
                Kompakte Übersicht mit allen 12 Monaten in einer Zeile pro Mitarbeiter:in.
                Ideal für Geschäftsführung und schnellen Überblick.
              </p>
              <ul className="text-xs text-gray-600 space-y-1 mb-4">
                <li>✓ Ein Sheet pro Mitarbeiter:in</li>
                <li>✓ Monate als Spalten</li>
                <li>✓ Überstunden kumuliert</li>
                <li>✓ Resturlaub</li>
              </ul>
              <button
                onClick={handleYearlyClassicExport}
                disabled={loading}
                className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50"
              >
                <Download size={18} />
                <span>{loading ? 'Wird erstellt...' : 'Classic Export'}</span>
              </button>
            </div>

            {/* Detailed Format */}
            <div className="border border-gray-300 rounded-lg p-5 hover:border-primary transition">
              <h3 className="font-semibold text-gray-900 mb-2 flex items-center space-x-2">
                <span>📊</span>
                <span>Detailliertes Format</span>
              </h3>
              <p className="text-sm text-gray-600 mb-4">
                Ausführlicher Report mit täglichem Breakdown über das gesamte Jahr.
                Ideal für Lohnbuchhaltung und detaillierte Analysen.
              </p>
              <ul className="text-xs text-gray-600 space-y-1 mb-4">
                <li>✓ Übersicht + Abwesenheiten</li>
                <li>✓ Pro MA: 365 Tage einzeln</li>
                <li>✓ Alle Zeiteinträge</li>
                <li>✓ Monatstrennungen</li>
              </ul>
              <button
                onClick={handleYearlyExport}
                disabled={loading}
                className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50"
              >
                <Download size={18} />
                <span>{loading ? 'Wird erstellt...' : 'Detailliert Export'}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Rest Time Violations */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-3 mb-4">
          <Clock className="text-orange-500" size={24} />
          <h2 className="text-xl font-semibold">Ruhezeitprüfung</h2>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Prüft ob die gesetzliche Mindestruhezeit zwischen zwei Arbeitstagen eingehalten wurde (§5 ArbZG, Standard: 11 Stunden).
        </p>
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
            <input type="number" value={restYear} onChange={e => setRestYear(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg" min="2020" max="2030" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Monat (optional)</label>
            <select value={restMonth} onChange={e => setRestMonth(e.target.value ? parseInt(e.target.value) : '')}
              className="px-3 py-2 border border-gray-300 rounded-lg">
              <option value="">Ganzes Jahr</option>
              {Array.from({ length: 12 }, (_, i) => (
                <option key={i + 1} value={i + 1}>
                  {new Date(2000, i, 1).toLocaleString('de-DE', { month: 'long' })}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Mindestruhezeit (h)</label>
            <input type="number" value={minRestHours} onChange={e => setMinRestHours(parseFloat(e.target.value))}
              step="0.5" min="1" max="24" className="px-3 py-2 border border-gray-300 rounded-lg w-24" />
          </div>
          <button onClick={checkRestViolations} disabled={restLoading}
            className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition disabled:opacity-50">
            <AlertTriangle size={18} />
            <span>{restLoading ? 'Prüfe...' : 'Prüfen'}</span>
          </button>
        </div>

        {restViolations !== null && (
          <div>
            {restViolations.length === 0 ? (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg text-green-800">
                ✓ Keine Ruhezeitverstöße gefunden
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm font-medium text-orange-700">
                  {restViolations.reduce((sum, v) => sum + v.violation_count, 0)} Verstöße bei {restViolations.length} Mitarbeiter(n)
                </p>
                {restViolations.map(emp => (
                  <div key={emp.user_id} className="border border-orange-200 rounded-lg overflow-hidden">
                    <button
                      onClick={() => setExpandedViolations(p => ({ ...p, [emp.user_id]: !p[emp.user_id] }))}
                      className="w-full px-4 py-3 bg-orange-50 flex items-center justify-between hover:bg-orange-100 transition"
                    >
                      <span className="font-medium text-orange-900">
                        {emp.first_name} {emp.last_name} – {emp.violation_count} Verstoß{emp.violation_count !== 1 ? 'e' : ''}
                      </span>
                      {expandedViolations[emp.user_id] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                    {expandedViolations[emp.user_id] && (
                      <table className="w-full text-sm">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Tag 1 Ende</th>
                            <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Tag 2 Start</th>
                            <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Ruhezeit</th>
                            <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Fehlend</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {emp.violations.map((v, i) => (
                            <tr key={i} className="hover:bg-red-50">
                              <td className="px-4 py-2 text-gray-900">
                                {new Date(v.day1_date + 'T00:00:00').toLocaleDateString('de-DE')} {v.day1_end.substring(0, 5)}
                              </td>
                              <td className="px-4 py-2 text-gray-900">
                                {new Date(v.day2_date + 'T00:00:00').toLocaleDateString('de-DE')} {v.day2_start.substring(0, 5)}
                              </td>
                              <td className="px-4 py-2 text-right font-medium text-red-700">{v.actual_rest_hours}h</td>
                              <td className="px-4 py-2 text-right font-medium text-red-600">-{v.deficit_hours}h</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Additional Info */}
      <div className="bg-gray-50 rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-3">Hinweise</h3>
        <ul className="text-sm text-gray-700 space-y-2">
          <li>• Die Excel-Dateien können direkt an die Lohnbuchhaltung weitergeleitet werden</li>
          <li>• Alle Berechnungen basieren auf den tatsächlichen Arbeitstagen (Mo-Fr minus Feiertage und Abwesenheiten)</li>
          <li>• Bayerische Feiertage werden automatisch berücksichtigt</li>
          <li>• Abwesenheiten reduzieren das Soll entsprechend</li>
          <li>• Historische Stundenänderungen werden korrekt berücksichtigt</li>
        </ul>
      </div>
    </div>
  );
}
