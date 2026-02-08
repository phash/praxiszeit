import { useState } from 'react';
import { format } from 'date-fns';
import { Download } from 'lucide-react';

export default function Reports() {
  const [selectedMonth, setSelectedMonth] = useState(format(new Date(), 'yyyy-MM'));

  const handleExport = () => {
    // Download Excel file
    const url = `/api/admin/reports/export?month=${selectedMonth}`;
    window.open(url, '_blank');
  };

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Berichte & Export</h1>

      {/* Export Section */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
        <div className="max-w-2xl">
          <h2 className="text-xl font-semibold mb-4">Monatsreport exportieren</h2>
          <p className="text-gray-600 mb-6">
            Exportieren Sie einen detaillierten Monatsreport für alle Mitarbeiterinnen als Excel-Datei.
            Die Datei enthält für jede Mitarbeiterin ein separates Sheet mit allen Zeiteinträgen,
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
              onClick={handleExport}
              className="bg-primary hover:bg-primary-dark text-white px-6 py-3 rounded-lg flex items-center space-x-2 transition"
            >
              <Download size={20} />
              <span>Excel exportieren</span>
            </button>
          </div>

          <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <h3 className="font-semibold text-blue-900 mb-2">Was enthält der Export?</h3>
            <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
              <li>Ein Sheet pro Mitarbeiterin</li>
              <li>Tägliche Zeiteinträge (Datum, Von, Bis, Pause, Netto)</li>
              <li>Soll-Stunden pro Tag</li>
              <li>Markierung von Wochenenden, Feiertagen und Abwesenheiten</li>
              <li>Monatszusammenfassung (Soll, Ist, Saldo, Überstunden kumuliert, Urlaub)</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Additional Info */}
      <div className="mt-6 bg-gray-50 rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-3">Hinweise</h3>
        <ul className="text-sm text-gray-700 space-y-2">
          <li>• Die Excel-Datei kann direkt an die Lohnbuchhaltung weitergeleitet werden</li>
          <li>• Alle Berechnungen basieren auf den tatsächlichen Arbeitstagen (Mo-Fr minus Feiertage und Abwesenheiten)</li>
          <li>• Bayerische Feiertage werden automatisch berücksichtigt</li>
          <li>• Abwesenheiten reduzieren das Soll entsprechend</li>
        </ul>
      </div>
    </div>
  );
}
