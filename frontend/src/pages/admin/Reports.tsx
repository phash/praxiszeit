import { useState } from 'react';
import { format } from 'date-fns';
import { Download, Calendar, FileText } from 'lucide-react';
import apiClient from '../../api/client';

export default function Reports() {
  const [selectedMonth, setSelectedMonth] = useState(format(new Date(), 'yyyy-MM'));
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);

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
      console.error('Export failed:', error);
      alert('Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
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
      console.error('Export failed:', error);
      alert('Export fehlgeschlagen. Bitte versuchen Sie es erneut.');
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
