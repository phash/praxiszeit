import { useState } from 'react';
import { format } from 'date-fns';
import { Download, Calendar, FileText, Clock, AlertTriangle, ChevronDown, ChevronUp, Sun } from 'lucide-react';
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

interface SundaySummaryEmployee {
  user_id: string;
  first_name: string;
  last_name: string;
  sundays_worked: number;
  free_sundays: number;
  total_sundays_in_year: number;
  compliant: boolean;
}

interface SundaySummary {
  year: number;
  total_sundays_in_year: number;
  min_free_sundays: number;
  employees: SundaySummaryEmployee[];
  non_compliant_count: number;
}

interface NightWorkEmployee {
  user_id: string;
  first_name: string;
  last_name: string;
  night_work_days: number;
  is_nachtarbeitnehmer: boolean;
  nachtarbeitnehmer_threshold: number;
  by_month: { month: number; days: number }[];
}

interface NightWorkSummary {
  year: number;
  nachtarbeitnehmer_threshold: number;
  employees: NightWorkEmployee[];
  nachtarbeitnehmer_count: number;
}

interface CompensatoryRestEmployee {
  user_id: string;
  first_name: string;
  last_name: string;
  sunday_holiday_days_worked: number;
  violations: { date: string; type: string; window_weeks: number }[];
  violation_count: number;
  compliant: boolean;
}

interface CompensatoryRest {
  year: number;
  employees: CompensatoryRestEmployee[];
  total_violations: number;
  non_compliant_count: number;
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

  // Sunday summary (§11 ArbZG)
  const [sundayYear, setSundayYear] = useState(new Date().getFullYear());
  const [sundaySummary, setSundaySummary] = useState<SundaySummary | null>(null);
  const [sundayLoading, setSundayLoading] = useState(false);

  // Night work summary (§6 ArbZG)
  const [nightYear, setNightYear] = useState(new Date().getFullYear());
  const [nightSummary, setNightSummary] = useState<NightWorkSummary | null>(null);
  const [nightLoading, setNightLoading] = useState(false);

  // Compensatory rest (§11 ArbZG – Ersatzruhetag)
  const [compRestYear, setCompRestYear] = useState(new Date().getFullYear());
  const [compRest, setCompRest] = useState<CompensatoryRest | null>(null);
  const [compRestLoading, setCompRestLoading] = useState(false);

  // DSGVO Art. 9: Gesundheitsdaten-Schutz bei Jahresexport
  const [includeHealthData, setIncludeHealthData] = useState(false);

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

  const checkSundaySummary = async () => {
    setSundayLoading(true);
    try {
      const res = await apiClient.get(`/admin/reports/sunday-summary?year=${sundayYear}`);
      setSundaySummary(res.data);
      if (res.data.non_compliant_count === 0) {
        toast.success('Alle Mitarbeitenden erfüllen die §11 ArbZG Anforderung (≥15 freie Sonntage)');
      }
    } catch {
      toast.error('Fehler beim Laden der Sonntagsauswertung');
    } finally {
      setSundayLoading(false);
    }
  };

  const checkNightWork = async () => {
    setNightLoading(true);
    try {
      const res = await apiClient.get(`/admin/reports/night-work-summary?year=${nightYear}`);
      setNightSummary(res.data);
      if (res.data.nachtarbeitnehmer_count === 0) {
        toast.success('Keine Nachtarbeitnehmer (≥48 Nachtschichten) gefunden');
      }
    } catch {
      toast.error('Fehler beim Laden der Nachtarbeits-Auswertung');
    } finally {
      setNightLoading(false);
    }
  };

  const checkCompensatoryRest = async () => {
    setCompRestLoading(true);
    try {
      const res = await apiClient.get(`/admin/reports/compensatory-rest?year=${compRestYear}`);
      setCompRest(res.data);
      if (res.data.total_violations === 0) {
        toast.success('Alle Ersatzruhetag-Anforderungen (§11 ArbZG) sind erfüllt');
      }
    } catch {
      toast.error('Fehler beim Laden der Ersatzruhetag-Prüfung');
    } finally {
      setCompRestLoading(false);
    }
  };

  const handleMonthlyExport = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(`/admin/reports/export?month=${selectedMonth}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `PraxisZeit_Monatsreport_${selectedMonth}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      toast.error('Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleYearlyExport = async () => {
    setLoading(true);
    try {
      const healthParam = includeHealthData ? '&include_health_data=true' : '';
      const response = await apiClient.get(`/admin/reports/export-yearly?year=${selectedYear}${healthParam}`, {
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
      const healthParam = includeHealthData ? '&include_health_data=true' : '';
      const response = await apiClient.get(`/admin/reports/export-yearly-classic?year=${selectedYear}${healthParam}`, {
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

  const handleMonthlyExportOds = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(`/admin/reports/export-ods?month=${selectedMonth}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `PraxisZeit_Monatsreport_${selectedMonth}.ods`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      toast.error('ODS-Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleYearlyExportOds = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(`/admin/reports/export-yearly-ods?year=${selectedYear}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `PraxisZeit_Jahresreport_${selectedYear}.ods`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      toast.error('ODS-Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleYearlyClassicExportOds = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(`/admin/reports/export-yearly-classic-ods?year=${selectedYear}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `PraxisZeit_Jahresreport_Classic_${selectedYear}.ods`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      toast.error('ODS-Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
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
              disabled={loading}
              className="bg-primary hover:bg-primary-dark text-white px-6 py-3 rounded-lg flex items-center space-x-2 transition disabled:opacity-50"
            >
              <Download size={20} />
              <span>{loading ? 'Wird erstellt...' : 'Excel (.xlsx)'}</span>
            </button>
            <button
              onClick={handleMonthlyExportOds}
              disabled={loading}
              className="bg-white hover:bg-gray-50 text-primary border border-primary px-6 py-3 rounded-lg flex items-center space-x-2 transition disabled:opacity-50"
            >
              <Download size={20} />
              <span>{loading ? 'Wird erstellt...' : 'ODS (.ods)'}</span>
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

          <div className="flex items-end space-x-4 mb-4">
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

          {/* DSGVO Art. 9 – Gesundheitsdaten */}
          <div className="mb-6">
            <label className="flex items-center space-x-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={includeHealthData}
                onChange={(e) => setIncludeHealthData(e.target.checked)}
                className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary cursor-pointer"
              />
              <span className="text-sm font-medium text-gray-700 group-hover:text-gray-900">
                Krankheitsdaten einschließen
              </span>
            </label>
            {includeHealthData && (
              <div className="mt-3 p-4 bg-amber-50 border border-amber-300 rounded-lg flex items-start space-x-3">
                <AlertTriangle size={18} className="text-amber-600 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-amber-800">
                  <strong>Hinweis (Art. 9 DSGVO):</strong> Krankheitsdaten sind besondere Kategorien
                  personenbezogener Daten. Dieser Export wird im Audit-Log verzeichnet.
                  Stellen Sie sicher, dass die Weitergabe auf das notwendige Minimum beschränkt ist.
                </p>
              </div>
            )}
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
              <div className="flex gap-2">
                <button
                  onClick={handleYearlyClassicExport}
                  disabled={loading}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50"
                >
                  <Download size={18} />
                  <span>{loading ? '...' : 'Excel'}</span>
                </button>
                <button
                  onClick={handleYearlyClassicExportOds}
                  disabled={loading}
                  className="flex-1 bg-white hover:bg-gray-50 text-primary border border-primary px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50"
                >
                  <Download size={18} />
                  <span>{loading ? '...' : 'ODS'}</span>
                </button>
              </div>
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
              <div className="flex gap-2">
                <button
                  onClick={handleYearlyExport}
                  disabled={loading}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50"
                >
                  <Download size={18} />
                  <span>{loading ? '...' : 'Excel'}</span>
                </button>
                <button
                  onClick={handleYearlyExportOds}
                  disabled={loading}
                  className="flex-1 bg-white hover:bg-gray-50 text-primary border border-primary px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50"
                >
                  <Download size={18} />
                  <span>{loading ? '...' : 'ODS'}</span>
                </button>
              </div>
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

      {/* Sunday Summary §11 ArbZG */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-3 mb-2">
          <Sun className="text-yellow-500" size={24} />
          <h2 className="text-xl font-semibold">Sonntagsarbeit §11 ArbZG</h2>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          §11 ArbZG fordert mindestens <strong>15 beschäftigungsfreie Sonntage pro Jahr</strong> pro Mitarbeitenden.
        </p>
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
            <input type="number" value={sundayYear} onChange={e => setSundayYear(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg" min="2020" max="2030" />
          </div>
          <button onClick={checkSundaySummary} disabled={sundayLoading}
            className="bg-yellow-500 hover:bg-yellow-600 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition disabled:opacity-50">
            <Sun size={18} />
            <span>{sundayLoading ? 'Prüfe...' : 'Prüfen'}</span>
          </button>
        </div>

        {sundaySummary !== null && (
          <div>
            <div className="mb-3 flex flex-wrap gap-3 text-sm text-gray-600">
              <span>Jahr: <strong>{sundaySummary.year}</strong></span>
              <span>Sonntage gesamt: <strong>{sundaySummary.total_sundays_in_year}</strong></span>
              <span>Pflicht freie Sonntage: <strong>≥{sundaySummary.min_free_sundays}</strong></span>
              {sundaySummary.non_compliant_count > 0 && (
                <span className="text-red-600 font-medium">
                  ⚠ {sundaySummary.non_compliant_count} Mitarbeitende nicht konform
                </span>
              )}
            </div>
            <table className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Mitarbeiter:in</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Gearbeitete So.</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Freie So.</th>
                  <th className="px-4 py-2 text-center text-xs text-gray-500 uppercase">§11 Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sundaySummary.employees.map(emp => (
                  <tr key={emp.user_id} className={`hover:bg-gray-50 ${!emp.compliant ? 'bg-red-50' : ''}`}>
                    <td className="px-4 py-2 font-medium text-gray-900">{emp.first_name} {emp.last_name}</td>
                    <td className="px-4 py-2 text-right text-gray-700">{emp.sundays_worked}</td>
                    <td className="px-4 py-2 text-right font-medium">
                      <span className={emp.compliant ? 'text-green-700' : 'text-red-700'}>
                        {emp.free_sundays}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-center">
                      {emp.compliant
                        ? <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">✓ Konform</span>
                        : <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">✗ Verstoß</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Night Work Summary §6 ArbZG */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-3 mb-2">
          <Clock className="text-indigo-500" size={24} />
          <h2 className="text-xl font-semibold">Nachtarbeit §6 ArbZG</h2>
        </div>
        <p className="text-sm text-gray-600 mb-3">
          Nachtzeit: 23:00–06:00 Uhr. Mitarbeitende mit ≥<strong>48 Nachtschichten/Jahr</strong> gelten als Nachtarbeitnehmer und haben Anspruch auf arbeitsmedizinische Untersuchung sowie Lohnausgleich.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
            <p className="font-semibold text-amber-800 mb-1">§6 Abs. 3 – Arbeitsmedizinische Untersuchung</p>
            <ul className="text-amber-700 space-y-0.5">
              <li>• Pflichtuntersuchung <strong>vor Aufnahme</strong> der Nachtarbeit</li>
              <li>• Wiederholung alle <strong>3 Jahre</strong> (ab 50 Jahren: jährlich)</li>
              <li>• Kosten trägt der Arbeitgeber</li>
              <li>• Auf Verlangen: Versetzung in Tagarbeit (§6 Abs. 4)</li>
            </ul>
          </div>
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm">
            <p className="font-semibold text-blue-800 mb-1">§6 Abs. 5 – Lohnausgleich</p>
            <ul className="text-blue-700 space-y-0.5">
              <li>• Anspruch auf <strong>25 % Lohnzuschlag</strong> oder</li>
              <li>• gleichwertige <strong>bezahlte Freizeit</strong> als Ausgleich</li>
              <li>• Gilt für alle Nachtarbeitnehmer (≥48 Nachtschichten/Jahr)</li>
              <li>• Tarifvertrag kann abweichende Regelung treffen (§6 Abs. 5 S. 2)</li>
            </ul>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
            <input type="number" value={nightYear} onChange={e => setNightYear(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg" min="2020" max="2030" />
          </div>
          <button onClick={checkNightWork} disabled={nightLoading}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition disabled:opacity-50">
            <Clock size={18} />
            <span>{nightLoading ? 'Prüfe...' : 'Auswerten'}</span>
          </button>
        </div>

        {nightSummary !== null && (
          <div>
            <div className="mb-3 flex flex-wrap gap-3 text-sm text-gray-600">
              <span>Jahr: <strong>{nightSummary.year}</strong></span>
              <span>Schwellwert Nachtarbeitnehmer: <strong>≥{nightSummary.nachtarbeitnehmer_threshold} Tage</strong></span>
              {nightSummary.nachtarbeitnehmer_count > 0 && (
                <span className="text-amber-600 font-medium">
                  ⚠ {nightSummary.nachtarbeitnehmer_count} Nachtarbeitnehmer
                </span>
              )}
            </div>
            <table className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Mitarbeiter:in</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Nachtschichten</th>
                  <th className="px-4 py-2 text-center text-xs text-gray-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {nightSummary.employees.map(emp => (
                  <tr key={emp.user_id} className={`hover:bg-gray-50 ${emp.is_nachtarbeitnehmer ? 'bg-amber-50' : ''}`}>
                    <td className="px-4 py-2 font-medium text-gray-900">{emp.first_name} {emp.last_name}</td>
                    <td className="px-4 py-2 text-right text-gray-700">{emp.night_work_days}</td>
                    <td className="px-4 py-2 text-center">
                      {emp.is_nachtarbeitnehmer
                        ? <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">⚠ Nachtarbeitnehmer</span>
                        : <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">✓ Unter Schwellwert</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Compensatory Rest §11 ArbZG */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-3 mb-2">
          <AlertTriangle className="text-orange-500" size={24} />
          <h2 className="text-xl font-semibold">Ersatzruhetage §11 ArbZG</h2>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Nach <strong>Sonntagsarbeit</strong>: Ersatzruhetag innerhalb <strong>2 Wochen</strong>. Nach <strong>Feiertagsarbeit</strong>: Ersatzruhetag innerhalb <strong>8 Wochen</strong>.
        </p>
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
            <input type="number" value={compRestYear} onChange={e => setCompRestYear(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg" min="2020" max="2030" />
          </div>
          <button onClick={checkCompensatoryRest} disabled={compRestLoading}
            className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition disabled:opacity-50">
            <AlertTriangle size={18} />
            <span>{compRestLoading ? 'Prüfe...' : 'Prüfen'}</span>
          </button>
        </div>

        {compRest !== null && (
          <div>
            <div className="mb-3 flex flex-wrap gap-3 text-sm text-gray-600">
              <span>Jahr: <strong>{compRest.year}</strong></span>
              <span>Verstöße gesamt: <strong>{compRest.total_violations}</strong></span>
              {compRest.non_compliant_count > 0 && (
                <span className="text-red-600 font-medium">
                  ⚠ {compRest.non_compliant_count} Mitarbeitende nicht konform
                </span>
              )}
            </div>
            <table className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Mitarbeiter:in</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">So/FT gearbeitet</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Verstöße</th>
                  <th className="px-4 py-2 text-center text-xs text-gray-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {compRest.employees.map(emp => (
                  <tr key={emp.user_id} className={`hover:bg-gray-50 ${!emp.compliant ? 'bg-red-50' : ''}`}>
                    <td className="px-4 py-2 font-medium text-gray-900">{emp.first_name} {emp.last_name}</td>
                    <td className="px-4 py-2 text-right text-gray-700">{emp.sunday_holiday_days_worked}</td>
                    <td className="px-4 py-2 text-right font-medium">
                      <span className={emp.compliant ? 'text-green-700' : 'text-red-700'}>{emp.violation_count}</span>
                    </td>
                    <td className="px-4 py-2 text-center">
                      {emp.compliant
                        ? <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">✓ Konform</span>
                        : <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">✗ Verstoß</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
          <li>• <strong>§16 ArbZG:</strong> Exportierte Berichte und Zeitaufzeichnungen sind mindestens <strong>2 Jahre aufzubewahren</strong></li>
          <li>• Gesetzestext: <a href="https://www.gesetze-im-internet.de/arbzg/" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline hover:text-blue-800">Arbeitszeitgesetz (ArbZG) auf gesetze-im-internet.de</a></li>
        </ul>
      </div>
    </div>
  );
}
