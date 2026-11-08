import { useState } from 'react';
import { format } from 'date-fns';
import { Download, Calendar, FileText, Clock, AlertTriangle, ChevronDown, ChevronUp, Sun } from 'lucide-react';
import apiClient from '../../api/client';
import { downloadBlob } from '../../utils/downloadBlob';
import { useToast } from '../../contexts/ToastContext';
import { formatHoursHM, parseHours } from '../../utils/formatters';

interface RestViolation {
  day1_date: string;
  day1_end: string;
  day2_date: string;
  day2_start: string;
  actual_rest_hours: number;
  min_rest_hours: number;
  deficit_hours: number;
}

// A2-6 (Audit 2026-11-07): ausgeblendete Mitarbeitende mit Daten im Zeitraum,
// die eine Auswertung ohne „Ausgeblendete einbeziehen" NICHT enthält.
interface HiddenCount {
  hidden_with_data_count?: number;
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

interface SundaySummary extends HiddenCount {
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
  /** A1-14: laut Zählung Nachtarbeitnehmer, Kennzeichen am Benutzer fehlt. */
  flag_missing?: boolean;
  /** A1-14: § 6 Abs. 2 — Ø je Werktag je Kalendermonat (nur Nachtarbeitnehmer). */
  monthly?: NightWorkMonth[];
  monthly_violation_count?: number;
}

interface NightWorkMonth {
  month: number;
  workdays: number;
  total_hours: number;
  average_daily_hours: number;
  presence_hours: number;
  presence_average: number;
  /** null = kein Werktag im Monat (nur Sonn-/Feiertagsarbeit) — kein Urteil. */
  compliant: boolean | null;
}

interface NightWorkSummary extends HiddenCount {
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
  violations: CompRestItem[];
  violation_count: number;
  /** A1-01: Frist läuft noch, kein Ersatzruhetag bisher. */
  open?: CompRestItem[];
  open_count?: number;
  compliant: boolean;
}

interface CompRestItem {
  date: string;
  type: string;
  window_weeks: number;
  deadline?: string;
}

interface CompensatoryRest extends HiddenCount {
  year: number;
  employees: CompensatoryRestEmployee[];
  total_violations: number;
  total_open?: number;
  non_compliant_count: number;
}

// A1-08 (Audit 2026-11-07): Tage > 10 h, Wochen > 48 h, Pausenausnahmen (§ 3/§ 4).
interface LimitsEmployee {
  user_id: string;
  first_name: string;
  last_name: string;
  days_over_10h: { date: string; presence_hours: number; credited_hours: number; auto_closed: boolean }[];
  weeks_over_48h: { iso_week: string; presence_hours: number }[];
  break_exceptions: { date: string; start_time: string; end_time: string | null; break_minutes: number; reason: string }[];
  // § 4-Fehlbetrag ohne anerkannte Ausnahme (Ausnahme beantragt/abgelehnt, automatisch geschlossen, anerkannt).
  break_shortfalls: {
    date: string; worked_hours: number; break_minutes: number; required_minutes: number;
    shortfall_minutes: number; auto_closed: boolean; credit_override: boolean;
    waiver_request: 'pending' | 'rejected' | null;
  }[];
}

interface LimitsReport extends HiddenCount {
  year: number;
  month: number | null;
  employees: LimitsEmployee[];
  total_days_over_10h: number;
  total_weeks_over_48h: number;
  total_break_exceptions: number;
  total_break_shortfalls: number;
}

const WAIVER_REQUEST_LABELS: Record<string, string> = {
  pending: 'Ausnahme beantragt, noch offen',
  rejected: 'Ausnahme abgelehnt',
};

function shortfallNote(b: LimitsEmployee['break_shortfalls'][number]): string {
  const notes: string[] = [];
  if (b.waiver_request) notes.push(WAIVER_REQUEST_LABELS[b.waiver_request]);
  if (b.auto_closed) notes.push('automatisch geschlossen');
  if (b.credit_override) notes.push('anerkannt');
  return notes.join(', ');
}

// Spec 2026-10-08, 8.1 / P22: 24-Wochen-Durchschnitt (§3 ArbZG) mit einem
// zweiten, eigens gekennzeichneten Wert „Anwesenheit laut Stempel".
interface AverageEmployee {
  user_id: string;
  first_name: string;
  last_name: string;
  total_hours: number;
  scheduled_work_days: number;
  average_daily_hours: number;
  days_over_8h: number;
  compliant: boolean;
  presence_hours: number;
  presence_average: number;
  /** Spec 8.1/11.1 „je Woche": Σ Anwesenheit laut Stempel je ISO-Kalenderwoche. */
  presence_weeks?: { iso_week: string; presence_hours: number }[];
}

// Gesamtreview PR2 (Fund 8): „2026-W05" → „KW 5/2026" wie WeekSelector und
// Dashboard (#500). Das 24-Wochen-Fenster kann einen Jahreswechsel enthalten —
// deshalb immer mit Jahr. Unbekanntes Format bleibt unverändert.
function isoWeekLabel(isoWeek: string): string {
  const m = /^(\d{4})-W(\d{1,2})$/.exec(isoWeek);
  return m ? `KW ${Number(m[2])}/${m[1]}` : isoWeek;
}

// P22: Wochen über der 48-h-Grenze laut Stempel — Text der Spalte, sonst „–".
function weeksOver48Text(weeks: AverageEmployee['presence_weeks']): string {
  const over = (weeks ?? []).filter((w) => w.presence_hours > 48);
  if (over.length === 0) return '–';
  return `${over.length} (${over.map((w) => `${isoWeekLabel(w.iso_week)}: ${formatHoursHM(w.presence_hours)} h`).join(', ')})`;
}

interface AverageReport extends HiddenCount {
  window_start: string;
  window_end: string;
  employees: AverageEmployee[];
  non_compliant_count: number;
}

// Gesamtreview 1.20 (Fund 22): ISO-Datum der Antwort als TT.MM.JJJJ (Mittag,
// damit die Zeitzone den Tag nicht verschiebt).
function isoDateDe(iso: string): string {
  return format(new Date(`${iso}T12:00:00`), 'dd.MM.yyyy');
}

// A2-6: Hinweis, wenn ausgeblendete Mitarbeitende mit Daten fehlen.
function HiddenHint({ report }: { report: HiddenCount | null }) {
  const n = report?.hidden_with_data_count ?? 0;
  if (n <= 0) return null;
  return (
    <p className="mb-3 text-sm text-amber-700">
      {n === 1 ? '1 ausgeblendete:r Mitarbeiter:in' : `${n} ausgeblendete Mitarbeitende`} mit Einträgen im
      Zeitraum {n === 1 ? 'ist' : 'sind'} nicht enthalten – „Ausgeblendete Mitarbeitende einbeziehen“ aktivieren.
    </p>
  );
}

function HiddenToggle({ checked, onChange, id }: { checked: boolean; onChange: (v: boolean) => void; id: string }) {
  return (
    <label htmlFor={id} className="flex items-center space-x-3 cursor-pointer group">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary cursor-pointer"
      />
      <span className="text-sm font-medium text-gray-700 group-hover:text-gray-900">
        Ausgeblendete Mitarbeitende einbeziehen
      </span>
    </label>
  );
}

const MONTH_NAMES_DE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

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

  // 24-Wochen-Durchschnitt §3 ArbZG (Spec 8.1, P22)
  const [avgEndDate, setAvgEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [avgReport, setAvgReport] = useState<AverageReport | null>(null);
  const [avgLoading, setAvgLoading] = useState(false);

  // DSGVO Art. 9: Gesundheitsdaten-Schutz bei Jahresexport
  const [includeHealthData, setIncludeHealthData] = useState(false);

  // A2-6: Ausgeblendete Mitarbeitende nur auf Wunsch (Exporte / ArbZG-Auswertungen getrennt)
  const [exportIncludeHidden, setExportIncludeHidden] = useState(false);
  const [reportIncludeHidden, setReportIncludeHidden] = useState(false);
  const hiddenParam = reportIncludeHidden ? '&include_hidden=true' : '';

  // A1-08: Tage > 10 h, Wochen > 48 h, Pausenausnahmen
  const [limitsYear, setLimitsYear] = useState(new Date().getFullYear());
  const [limitsMonth, setLimitsMonth] = useState<number | ''>('');
  const [limitsReport, setLimitsReport] = useState<LimitsReport | null>(null);
  const [limitsLoading, setLimitsLoading] = useState(false);
  const [expandedLimits, setExpandedLimits] = useState<Record<string, boolean>>({});
  const [restHidden, setRestHidden] = useState<number>(0);

  const checkRestViolations = async () => {
    setRestLoading(true);
    try {
      const params = new URLSearchParams({ year: String(restYear), min_rest_hours: String(minRestHours) });
      if (restMonth) params.set('month', String(restMonth));
      if (reportIncludeHidden) params.set('include_hidden', 'true');
      const res = await apiClient.get(`/admin/reports/rest-time-violations?${params}`);
      setRestViolations(res.data.violations);
      setRestHidden(res.data.hidden_with_data_count ?? 0);
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
      const res = await apiClient.get(`/admin/reports/sunday-summary?year=${sundayYear}${hiddenParam}`);
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
      const res = await apiClient.get(`/admin/reports/night-work-summary?year=${nightYear}${hiddenParam}`);
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
      const res = await apiClient.get(`/admin/reports/compensatory-rest?year=${compRestYear}${hiddenParam}`);
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

  const checkAverage = async () => {
    setAvgLoading(true);
    try {
      const res = await apiClient.get(`/admin/reports/24-week-average?end_date=${avgEndDate}${hiddenParam}`);
      setAvgReport(res.data);
    } catch {
      toast.error('Fehler beim Laden des 24-Wochen-Durchschnitts');
    } finally {
      setAvgLoading(false);
    }
  };

  const checkLimits = async () => {
    setLimitsLoading(true);
    try {
      const params = new URLSearchParams({ year: String(limitsYear) });
      if (limitsMonth) params.set('month', String(limitsMonth));
      if (reportIncludeHidden) params.set('include_hidden', 'true');
      const res = await apiClient.get(`/admin/reports/arbzg-limits?${params}`);
      setLimitsReport(res.data);
    } catch {
      toast.error('Fehler beim Laden der Auswertung (§3/§4 ArbZG)');
    } finally {
      setLimitsLoading(false);
    }
  };

  const handleMonthlyExport = async () => {
    setLoading(true);
    try {
      const healthParam = (includeHealthData ? '&include_health_data=true' : '') + (exportIncludeHidden ? '&include_hidden=true' : '');
      const response = await apiClient.get(`/admin/reports/export?month=${selectedMonth}${healthParam}`, {
        responseType: 'blob',
      });
      downloadBlob(response.data, `PraxisZeit_Monatsreport_${selectedMonth}.xlsx`);
    } catch {
      toast.error('Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleYearlyExport = async () => {
    setLoading(true);
    try {
      const healthParam = (includeHealthData ? '&include_health_data=true' : '') + (exportIncludeHidden ? '&include_hidden=true' : '');
      const response = await apiClient.get(`/admin/reports/export-yearly?year=${selectedYear}${healthParam}`, {
        responseType: 'blob',
      });
      downloadBlob(response.data, `PraxisZeit_Jahresreport_${selectedYear}.xlsx`);
    } catch (error) {
      toast.error('Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleYearlyClassicExport = async () => {
    setLoading(true);
    try {
      const healthParam = (includeHealthData ? '&include_health_data=true' : '') + (exportIncludeHidden ? '&include_hidden=true' : '');
      const response = await apiClient.get(`/admin/reports/export-yearly-classic?year=${selectedYear}${healthParam}`, {
        responseType: 'blob',
      });
      downloadBlob(response.data, `PraxisZeit_Jahresreport_Classic_${selectedYear}.xlsx`);
    } catch (error) {
      toast.error('Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleMonthlyExportPdf = async () => {
    setLoading(true);
    try {
      const healthParam = (includeHealthData ? '&include_health_data=true' : '') + (exportIncludeHidden ? '&include_hidden=true' : '');
      const response = await apiClient.get(`/admin/reports/export-pdf?month=${selectedMonth}${healthParam}`, {
        responseType: 'blob',
      });
      downloadBlob(response.data, `PraxisZeit_Monatsreport_${selectedMonth}.pdf`);
    } catch {
      toast.error('PDF-Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleMonthlyExportOds = async () => {
    setLoading(true);
    try {
      const healthParam = (includeHealthData ? '&include_health_data=true' : '') + (exportIncludeHidden ? '&include_hidden=true' : '');
      const response = await apiClient.get(`/admin/reports/export-ods?month=${selectedMonth}${healthParam}`, {
        responseType: 'blob',
      });
      downloadBlob(response.data, `PraxisZeit_Monatsreport_${selectedMonth}.ods`);
    } catch {
      toast.error('ODS-Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleYearlyExportOds = async () => {
    setLoading(true);
    try {
      const healthParam = (includeHealthData ? '&include_health_data=true' : '') + (exportIncludeHidden ? '&include_hidden=true' : '');
      const response = await apiClient.get(`/admin/reports/export-yearly-ods?year=${selectedYear}${healthParam}`, {
        responseType: 'blob',
      });
      downloadBlob(response.data, `PraxisZeit_Jahresreport_${selectedYear}.ods`);
    } catch {
      toast.error('ODS-Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
    } finally {
      setLoading(false);
    }
  };

  const handleYearlyClassicExportOds = async () => {
    setLoading(true);
    try {
      const healthParam = (includeHealthData ? '&include_health_data=true' : '') + (exportIncludeHidden ? '&include_hidden=true' : '');
      const response = await apiClient.get(`/admin/reports/export-yearly-classic-ods?year=${selectedYear}${healthParam}`, {
        responseType: 'blob',
      });
      downloadBlob(response.data, `PraxisZeit_Jahresreport_Classic_${selectedYear}.ods`);
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
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-8 mb-8">
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
            <button
              onClick={handleMonthlyExportPdf}
              disabled={loading}
              className="bg-red-600 hover:bg-red-700 text-white px-6 py-3 rounded-lg flex items-center space-x-2 transition disabled:opacity-50"
            >
              <Download size={20} />
              <span>{loading ? 'Wird erstellt...' : 'PDF (.pdf)'}</span>
            </button>
          </div>

          {/* DSGVO Art. 9 – Gesundheitsdaten-Schutz für Monatsexport */}
          <div className="mt-4">
            <label className="flex items-center space-x-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={includeHealthData}
                onChange={(e) => setIncludeHealthData(e.target.checked)}
                className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary cursor-pointer"
              />
              <span className="text-sm font-medium text-gray-700 group-hover:text-gray-900">
                Krankheitsdaten einschließen (Art. 9 DSGVO)
              </span>
            </label>
            <p className="mt-1 ml-7 text-xs text-gray-500">
              Umfasst auch das Kennzeichen „Nachtarbeitnehmer (§ 6 ArbZG)“ im Kopf jedes Blatts.
            </p>
            {includeHealthData && (
              <div className="mt-3 p-4 bg-amber-50 border border-amber-300 rounded-lg flex items-start space-x-3">
                <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
                <p className="text-sm text-amber-800">
                  <strong>Hinweis (Art. 9 DSGVO):</strong> Krankheitsdaten sind besondere Kategorien
                  personenbezogener Daten. Dieser Export wird im Audit-Log verzeichnet.
                  Stellen Sie sicher, dass die Weitergabe auf das notwendige Minimum beschränkt ist.
                </p>
              </div>
            )}
          </div>

          <div className="mt-3">
            <HiddenToggle id="export-hidden-month" checked={exportIncludeHidden} onChange={setExportIncludeHidden} />
          </div>

          <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <h3 className="font-semibold text-blue-900 mb-2">Was enthält der Export?</h3>
            <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
              <li>Ein Sheet pro Mitarbeiter:in</li>
              <li>Tägliche Zeiteinträge (Datum, Von, Bis, Pause, Netto)</li>
              <li>Spalte „Nicht angerechnet (Min)": gestempelte, nicht angerechnete Zeit (vor, nach und zwischen den Arbeitszeit-Blöcken)</li>
              <li>Angehängt „Gestempelt (Von–Bis)" und „Anwesenheit laut Stempel (Std)" (über 10 h hervorgehoben) sowie die Begründung einer Pausenausnahme (§ 4 ArbZG); im PDF als Spalte „Gestempelt" und in der Bemerkung</li>
              <li>Soll-Stunden pro Tag</li>
              <li>Markierung von Wochenenden, Feiertagen und Abwesenheiten</li>
              <li>Monatszusammenfassung (Soll, Ist, Saldo, Überstunden kumuliert, Urlaub)</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Yearly Export Section */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-8 mb-8">
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
                onChange={(e) => setSelectedYear(parseInt(e.target.value) || new Date().getFullYear())}
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
                className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary cursor-pointer"
              />
              <span className="text-sm font-medium text-gray-700 group-hover:text-gray-900">
                Krankheitsdaten einschließen
              </span>
            </label>
            <p className="mt-1 ml-7 text-xs text-gray-500">
              Umfasst auch das Kennzeichen „Nachtarbeitnehmer (§ 6 ArbZG)“ im Kopf jedes Blatts.
            </p>
            {includeHealthData && (
              <div className="mt-3 p-4 bg-amber-50 border border-amber-300 rounded-lg flex items-start space-x-3">
                <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
                <p className="text-sm text-amber-800">
                  <strong>Hinweis (Art. 9 DSGVO):</strong> Krankheitsdaten sind besondere Kategorien
                  personenbezogener Daten. Dieser Export wird im Audit-Log verzeichnet.
                  Stellen Sie sicher, dass die Weitergabe auf das notwendige Minimum beschränkt ist.
                </p>
              </div>
            )}
          </div>

          <div className="mb-6 -mt-3">
            <HiddenToggle id="export-hidden-year" checked={exportIncludeHidden} onChange={setExportIncludeHidden} />
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
                Kompakte Übersicht mit allen 12 Monaten je Mitarbeiter:in.
                Ideal für Geschäftsführung und schnellen Überblick.
              </p>
              <ul className="text-xs text-gray-600 space-y-1 mb-4">
                <li>✓ Ein Sheet pro Mitarbeiter:in</li>
                <li>✓ Excel: Monate als Spalten, ODS: eine Zeile je Monat</li>
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

      {/* A2-6: ArbZG-Auswertungen — Personenauswahl für alle Karten darunter */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
        <h2 className="text-xl font-semibold mb-2">ArbZG-Auswertungen</h2>
        <p className="text-sm text-gray-600 mb-3">
          Die Auswertungen enthalten alle aktiven Mitarbeitenden und ausgeschiedene, die im Zeitraum Einträge haben.
          § 18-befreite Mitarbeitende erscheinen nicht.
        </p>
        <HiddenToggle id="report-hidden" checked={reportIncludeHidden} onChange={setReportIncludeHidden} />
      </div>

      {/* Rest Time Violations */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
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
            <input type="number" value={minRestHours} onChange={e => setMinRestHours(parseHours(e.target.value))}
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
            <HiddenHint report={{ hidden_with_data_count: restHidden }} />
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
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
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
            <HiddenHint report={sundaySummary} />
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
                        ? <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-green-100 text-green-800">✓ Konform</span>
                        : <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-red-100 text-red-800">✗ Verstoß</span>
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
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
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
            <HiddenHint report={nightSummary} />
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
                    <td className="px-4 py-2 font-medium text-gray-900">
                      {emp.first_name} {emp.last_name}
                      {emp.flag_missing && (
                        <div className="text-xs font-normal text-amber-700">
                          Kennzeichen „Nachtarbeitnehmer“ beim Benutzer noch nicht gesetzt
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-700">{emp.night_work_days}</td>
                    <td className="px-4 py-2 text-center">
                      {emp.is_nachtarbeitnehmer
                        ? <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-amber-100 text-amber-800">⚠ Nachtarbeitnehmer</span>
                        : <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-green-100 text-green-800">✓ Unter Schwellwert</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* A1-14: § 6 Abs. 2 — Monatsdurchschnitt je Werktag für Nachtarbeitnehmer */}
            {nightSummary.employees.some((e) => (e.monthly ?? []).length > 0) && (
              <div className="mt-4">
                <h3 className="text-sm font-semibold text-gray-900 mb-1">Monatsdurchschnitt für Nachtarbeitnehmer (§ 6 Abs. 2 ArbZG)</h3>
                <p className="text-xs text-gray-600 mb-2">
                  Über 8 Stunden darf die Arbeitszeit nur verlängert werden, wenn im Kalendermonat im Durchschnitt 8 Stunden
                  je Werktag (Mo–Sa ohne Feiertage und ohne Tage mit Urlaub, Krankheit, Fortbildung oder Freistellung) nicht
                  überschritten werden. Es erscheinen nur vergangene Monate mit Arbeit.
                </p>
                <div className="overflow-x-auto">
                  <table aria-label="Monatsdurchschnitt Nachtarbeitnehmer" className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Mitarbeiter:in</th>
                        <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Monat</th>
                        <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Werktage</th>
                        <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Ø angerechnet / Werktag</th>
                        <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Ø laut Stempel / Werktag</th>
                        <th className="px-4 py-2 text-center text-xs text-gray-500 uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {nightSummary.employees.flatMap((emp) => (emp.monthly ?? []).map((m) => (
                        <tr key={`${emp.user_id}-${m.month}`} className={m.compliant === false ? 'bg-red-50' : ''}>
                          <td className="px-4 py-2 text-gray-900">{emp.first_name} {emp.last_name}</td>
                          <td className="px-4 py-2 text-gray-700">{MONTH_NAMES_DE[m.month - 1]}</td>
                          <td className="px-4 py-2 text-right text-gray-700">{m.workdays}</td>
                          <td className="px-4 py-2 text-right text-gray-700">{m.workdays ? formatHoursHM(m.average_daily_hours) : '–'}</td>
                          <td className={`px-4 py-2 text-right ${m.presence_average > 8 ? 'text-red-700 font-medium' : 'text-gray-700'}`}>
                            {m.workdays ? formatHoursHM(m.presence_average) : '–'}
                          </td>
                          <td className="px-4 py-2 text-center">
                            {m.compliant === null
                              ? <span className="text-xs text-gray-500">kein Werktag</span>
                              : m.compliant
                                ? <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-green-100 text-green-800">✓ Konform</span>
                                : <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-red-100 text-red-800">✗ Verstoß</span>}
                          </td>
                        </tr>
                      )))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Compensatory Rest §11 ArbZG */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-3 mb-2">
          <AlertTriangle className="text-orange-500" size={24} />
          <h2 className="text-xl font-semibold">Ersatzruhetage §11 ArbZG</h2>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Nach <strong>Sonntagsarbeit</strong>: Ersatzruhetag innerhalb <strong>2 Wochen</strong>. Nach <strong>Feiertagsarbeit</strong>: Ersatzruhetag innerhalb <strong>8 Wochen</strong>.
          Als Ersatzruhetag zählt nur ein Tag (Mo–Sa), an dem die Person sonst gearbeitet hätte und der frei war –
          ohne Zeiteintrag, kein Feiertag, kein Urlaub und keine Krankheit. Ein gewährter Ersatzruhetag wird als
          Abwesenheit „Sonstiges“ (oder „Überstundenausgleich“ bzw. „Bez. Freistellung“) eingetragen. Ein Ruhetag gleicht genau einen Einsatz aus.
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
            <HiddenHint report={compRest} />
            <div className="mb-3 flex flex-wrap gap-3 text-sm text-gray-600">
              <span>Jahr: <strong>{compRest.year}</strong></span>
              <span>Verstöße gesamt: <strong>{compRest.total_violations}</strong></span>
              {(compRest.total_open ?? 0) > 0 && (
                <span>Frist läuft: <strong>{compRest.total_open}</strong></span>
              )}
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
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Frist läuft</th>
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
                      {emp.violations.length > 0 && (
                        <div className="text-xs font-normal text-red-700">
                          {emp.violations.map((v) => `${isoDateDe(v.date)} (${v.type === 'sunday' ? 'So' : 'FT'})`).join(', ')}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right text-gray-700">
                      {emp.open_count ?? 0}
                      {(emp.open ?? []).length > 0 && (
                        <div className="text-xs text-gray-500">
                          {(emp.open ?? []).map((v) => `${isoDateDe(v.date)} bis ${v.deadline ? isoDateDe(v.deadline) : '?'}`).join(', ')}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {emp.compliant
                        ? <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-green-100 text-green-800">✓ Konform</span>
                        : <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-red-100 text-red-800">✗ Verstoß</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 24-Wochen-Durchschnitt §3 ArbZG (Spec 2026-10-08, 8.1 / P22) */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-3 mb-2">
          <Clock className="text-primary" size={24} />
          <h2 className="text-xl font-semibold">24-Wochen-Durchschnitt §3 ArbZG</h2>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Über 24 Wochen darf die Arbeitszeit im Durchschnitt <strong>8 Stunden je Werktag</strong> nicht
          überschreiten. Werktage sind Montag bis Samstag ohne Feiertage und ohne Tage mit Urlaub, Krankheit,
          Fortbildung oder Freistellung (Überstundenausgleich zählt mit), nur im Beschäftigungszeitraum – auch für Teilzeitkräfte. „Ø angerechnet“ und der Status rechnen mit der angerechneten Zeit. Daneben steht die{' '}
          <strong>Anwesenheit laut Stempel</strong> (abzüglich erfasster Pausen): Sie ändert sich nicht, wenn die
          Anrechnung später neu berechnet wird, und die Grenze gilt für die tatsächliche Arbeitszeit.
        </p>
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label htmlFor="avg-end-date" className="block text-sm font-medium text-gray-700 mb-1">Stichtag</label>
            <input
              id="avg-end-date"
              type="date"
              value={avgEndDate}
              onChange={(e) => {
                setAvgEndDate(e.target.value);
                // Fund 22: das Ergebnis gehört zum alten Stichtag — nicht neben
                // dem neuen Datum stehen lassen.
                setAvgReport(null);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg"
            />
          </div>
          <button
            onClick={checkAverage}
            // Fund 22: ohne Stichtag ginge `end_date=` raus (422, allgemeiner Fehler-Toast).
            disabled={avgLoading || !avgEndDate}
            aria-label="24-Wochen-Durchschnitt prüfen"
            className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition disabled:opacity-50"
          >
            <Clock size={18} />
            <span>{avgLoading ? 'Prüfe...' : 'Prüfen'}</span>
          </button>
        </div>

        <HiddenHint report={avgReport} />
        {avgReport !== null && (
          // Gesamtreview 1.20 (Fund 22): Zeitraum und Zahl der nicht konformen
          // Personen wie bei den Nachbarkarten („Jahr: …"); eine leere Liste
          // (z. B. alle § 18-befreit) wird erklärt statt eines leeren Tabellenkopfs.
          <div className="mb-3 flex flex-wrap gap-3 text-sm text-gray-600">
            <span>
              Zeitraum: <strong>{isoDateDe(avgReport.window_start)} – {isoDateDe(avgReport.window_end)}</strong>
            </span>
            {avgReport.non_compliant_count > 0 && (
              <span className="text-red-600 font-medium">
                ⚠ {avgReport.non_compliant_count} Mitarbeitende nicht konform
              </span>
            )}
          </div>
        )}
        {avgReport !== null && avgReport.employees.length === 0 && (
          <p className="text-sm text-gray-500">
            Keine Mitarbeitenden zu prüfen (§ 18-befreite Mitarbeitende erscheinen nicht).
          </p>
        )}
        {avgReport !== null && avgReport.employees.length > 0 && (
          // Fund 8: acht Spalten — auf Telefonbreite scrollt die Tabelle, nicht die Seite.
          <div className="overflow-x-auto">
            <table aria-label="24-Wochen-Durchschnitt" className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Mitarbeiter:in</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Ø angerechnet / Werktag</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Anwesenheit laut Stempel (Ø / Werktag)</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Angerechnet gesamt</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Anwesenheit laut Stempel gesamt</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Wochen &gt; 48 h laut Stempel</th>
                  <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Tage &gt; 8 h</th>
                  <th className="px-4 py-2 text-center text-xs text-gray-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {avgReport.employees.map((emp) => {
                  // Ohne Werktag im Fenster (A1-13: ganzes Fenster außerhalb der
                  // Beschäftigung oder Urlaub) fehlt der Nenner: das Backend liefert
                  // dann Ø 0 und compliant=true — kein Urteil, keine Ø-Werte zeigen.
                  const noScheduledDays = emp.scheduled_work_days === 0;
                  // P22 / Pflicht 4: Der Status folgt der angerechneten Zeit (Spec 8.1).
                  // Senkt eine Neukappung sie unter 8 h, darf ein Ø laut Stempel über
                  // der Grenze nicht als unauffällige graue Zahl neben „Konform“ stehen.
                  const presenceOver8 = !noScheduledDays && emp.presence_average > 8;
                  return (
                    <tr key={emp.user_id} className={`hover:bg-gray-50 ${!noScheduledDays && !emp.compliant ? 'bg-red-50' : ''}`}>
                      <td className="px-4 py-2 font-medium text-gray-900">{emp.first_name} {emp.last_name}</td>
                      <td className="px-4 py-2 text-right text-gray-700">{noScheduledDays ? '–' : formatHoursHM(emp.average_daily_hours)}</td>
                      <td className={`px-4 py-2 text-right ${presenceOver8 ? 'text-red-700 font-medium' : 'text-gray-700'}`}>
                        {noScheduledDays ? '–' : formatHoursHM(emp.presence_average)}
                      </td>
                      <td className="px-4 py-2 text-right text-gray-700">{formatHoursHM(emp.total_hours)}</td>
                      <td className="px-4 py-2 text-right text-gray-700">{formatHoursHM(emp.presence_hours)}</td>
                      <td className={`px-4 py-2 text-right ${weeksOver48Text(emp.presence_weeks) === '–' ? 'text-gray-700' : 'text-red-700 font-medium'}`}>
                        {weeksOver48Text(emp.presence_weeks)}
                      </td>
                      <td className="px-4 py-2 text-right text-gray-700">{emp.days_over_8h}</td>
                      <td className="px-4 py-2 text-center">
                        {noScheduledDays
                          ? <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-gray-100 text-gray-700">keine Werktage im Zeitraum</span>
                          : emp.compliant
                            ? <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-green-100 text-green-800">✓ Konform</span>
                            : <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-red-100 text-red-800">✗ Verstoß</span>}
                        {presenceOver8 && emp.compliant && (
                          <div className="mt-1 text-xs font-medium text-red-700">laut Stempel Ø &gt; 8 h</div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* A1-08 (Audit 2026-11-07): Tage > 10 h, Wochen > 48 h, Pausenausnahmen §3/§4 ArbZG */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-3 mb-2">
          <AlertTriangle className="text-red-500" size={24} />
          <h2 className="text-xl font-semibold">Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG</h2>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Nachträgliche Auswertung: Tage mit mehr als <strong>10 Stunden</strong>, Kalenderwochen mit mehr als{' '}
          <strong>48 Stunden</strong> (jeweils Anwesenheit laut Stempel abzüglich Pausen, daneben die angerechnete Zeit)
          und alle dokumentierten <strong>Pausenausnahmen</strong> mit ihrer Begründung.
        </p>
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label htmlFor="limits-year" className="block text-sm font-medium text-gray-700 mb-1">Jahr</label>
            <input id="limits-year" type="number" value={limitsYear} onChange={e => setLimitsYear(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg" min="2020" max="2050" />
          </div>
          <div>
            <label htmlFor="limits-month" className="block text-sm font-medium text-gray-700 mb-1">Monat (optional)</label>
            <select id="limits-month" value={limitsMonth} onChange={e => setLimitsMonth(e.target.value ? parseInt(e.target.value) : '')}
              className="px-3 py-2 border border-gray-300 rounded-lg">
              <option value="">Ganzes Jahr</option>
              {MONTH_NAMES_DE.map((name, i) => <option key={i + 1} value={i + 1}>{name}</option>)}
            </select>
          </div>
          <button onClick={checkLimits} disabled={limitsLoading} aria-label="Höchstarbeitszeit und Pausenausnahmen prüfen"
            className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition disabled:opacity-50">
            <AlertTriangle size={18} />
            <span>{limitsLoading ? 'Prüfe...' : 'Prüfen'}</span>
          </button>
        </div>

        {limitsReport !== null && (
          <div>
            <HiddenHint report={limitsReport} />
            <div className="mb-3 flex flex-wrap gap-3 text-sm text-gray-600">
              <span>Tage &gt; 10 h: <strong>{limitsReport.total_days_over_10h}</strong></span>
              <span>Wochen &gt; 48 h: <strong>{limitsReport.total_weeks_over_48h}</strong></span>
              <span>Pausenausnahmen: <strong>{limitsReport.total_break_exceptions}</strong></span>
              <span>Pause zu kurz: <strong>{limitsReport.total_break_shortfalls}</strong></span>
            </div>
            {limitsReport.employees.length === 0 ? (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg text-green-800">
                ✓ Keine Tage über 10 h, keine Wochen über 48 h, keine Pausenausnahmen und keine zu kurzen Pausen
              </div>
            ) : (
              <div className="space-y-3">
                {limitsReport.employees.map((emp) => (
                  <div key={emp.user_id} className="border border-red-200 rounded-lg overflow-hidden">
                    <button
                      onClick={() => setExpandedLimits(p => ({ ...p, [emp.user_id]: !p[emp.user_id] }))}
                      className="w-full px-4 py-3 bg-red-50 flex items-center justify-between hover:bg-red-100 transition"
                    >
                      <span className="font-medium text-red-900">
                        {emp.first_name} {emp.last_name} – {emp.days_over_10h.length} Tag(e) &gt; 10 h, {emp.weeks_over_48h.length} Woche(n) &gt; 48 h, {emp.break_exceptions.length} Pausenausnahme(n), {emp.break_shortfalls.length} Tag(e) mit zu kurzer Pause
                      </span>
                      {expandedLimits[emp.user_id] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                    {expandedLimits[emp.user_id] && (
                      <div className="p-4 space-y-4 text-sm">
                        {emp.days_over_10h.length > 0 && (
                          <table aria-label={`Tage über 10 Stunden ${emp.first_name} ${emp.last_name}`} className="w-full">
                            <thead className="bg-gray-50">
                              <tr>
                                <th className="px-3 py-1 text-left text-xs text-gray-500 uppercase">Tag</th>
                                <th className="px-3 py-1 text-right text-xs text-gray-500 uppercase">Laut Stempel</th>
                                <th className="px-3 py-1 text-right text-xs text-gray-500 uppercase">Angerechnet</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {emp.days_over_10h.map((d) => (
                                <tr key={d.date}>
                                  <td className="px-3 py-1">{isoDateDe(d.date)}{d.auto_closed ? ' (automatisch geschlossen)' : ''}</td>
                                  <td className="px-3 py-1 text-right text-red-700 font-medium">{formatHoursHM(d.presence_hours)} h</td>
                                  <td className="px-3 py-1 text-right">{formatHoursHM(d.credited_hours)} h</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                        {emp.weeks_over_48h.length > 0 && (
                          <p>
                            <strong>Wochen &gt; 48 h laut Stempel:</strong>{' '}
                            {emp.weeks_over_48h.map((w) => `${isoWeekLabel(w.iso_week)}: ${formatHoursHM(w.presence_hours)} h`).join(', ')}
                          </p>
                        )}
                        {emp.break_exceptions.length > 0 && (
                          <table aria-label={`Pausenausnahmen ${emp.first_name} ${emp.last_name}`} className="w-full">
                            <thead className="bg-gray-50">
                              <tr>
                                <th className="px-3 py-1 text-left text-xs text-gray-500 uppercase">Tag</th>
                                <th className="px-3 py-1 text-left text-xs text-gray-500 uppercase">Zeit</th>
                                <th className="px-3 py-1 text-right text-xs text-gray-500 uppercase">Pause</th>
                                <th className="px-3 py-1 text-left text-xs text-gray-500 uppercase">Begründung</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {emp.break_exceptions.map((b, i) => (
                                <tr key={`${b.date}-${i}`}>
                                  <td className="px-3 py-1">{isoDateDe(b.date)}</td>
                                  <td className="px-3 py-1">{b.start_time}–{b.end_time ?? 'offen'}</td>
                                  <td className="px-3 py-1 text-right">{b.break_minutes} Min.</td>
                                  <td className="px-3 py-1 text-gray-700">{b.reason}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                        {emp.break_shortfalls.length > 0 && (
                          <table aria-label={`Zu kurze Pausen ${emp.first_name} ${emp.last_name}`} className="w-full">
                            <thead className="bg-gray-50">
                              <tr>
                                <th className="px-3 py-1 text-left text-xs text-gray-500 uppercase">Tag (Pause zu kurz, § 4)</th>
                                <th className="px-3 py-1 text-right text-xs text-gray-500 uppercase">Arbeitszeit</th>
                                <th className="px-3 py-1 text-right text-xs text-gray-500 uppercase">Pause</th>
                                <th className="px-3 py-1 text-right text-xs text-gray-500 uppercase">Fehlt</th>
                                <th className="px-3 py-1 text-left text-xs text-gray-500 uppercase">Hinweis</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {emp.break_shortfalls.map((b) => (
                                <tr key={b.date}>
                                  <td className="px-3 py-1">{isoDateDe(b.date)}</td>
                                  <td className="px-3 py-1 text-right">{formatHoursHM(b.worked_hours)} h</td>
                                  <td className="px-3 py-1 text-right">{b.break_minutes} von {b.required_minutes} Min.</td>
                                  <td className="px-3 py-1 text-right text-red-700 font-medium">{b.shortfall_minutes} Min.</td>
                                  <td className="px-3 py-1 text-gray-700">{shortfallNote(b)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
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
          <li>• <strong>§16 ArbZG:</strong> Exportierte Berichte und Zeitaufzeichnungen sind mindestens <strong>2 Jahre aufzubewahren</strong></li>
          <li>• Gesetzestext: <a href="https://www.gesetze-im-internet.de/arbzg/" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline hover:text-blue-800">Arbeitszeitgesetz (ArbZG) auf gesetze-im-internet.de</a></li>
        </ul>
      </div>
    </div>
  );
}
