import { Link } from 'react-router-dom';
import { Shield, ArrowLeft } from 'lucide-react';

export default function Privacy() {
  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <Link
            to="/login"
            className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-6 transition-colors"
          >
            <ArrowLeft size={16} />
            Zurück zur Anmeldung
          </Link>
          <div className="flex items-center gap-3 mb-2">
            <Shield size={28} className="text-primary" />
            <h1 className="text-3xl font-bold text-gray-900">Datenschutzerklärung</h1>
          </div>
          <p className="text-gray-600">PraxisZeit – Zeiterfassungssystem</p>
          <p className="text-sm text-gray-500 mt-1">Stand: Februar 2026</p>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 space-y-8 text-gray-800">

          {/* 1. Verantwortlicher */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">1. Verantwortlicher</h2>
            <p className="text-gray-600">
              Verantwortlicher im Sinne der Datenschutz-Grundverordnung (DSGVO) ist der Betreiber dieser
              Anwendung (Arbeitgeber). Bei Fragen zum Datenschutz wenden Sie sich bitte an Ihren Vorgesetzten
              oder die benannte datenschutzverantwortliche Person in Ihrem Unternehmen.
            </p>
          </section>

          {/* 2. Zweck der Verarbeitung */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">2. Zweck und Rechtsgrundlage der Verarbeitung</h2>
            <p className="text-gray-600 mb-3">
              PraxisZeit verarbeitet personenbezogene Daten ausschließlich zur Erfüllung der gesetzlichen
              Pflichten des Arbeitgebers sowie zur Durchführung des Arbeitsverhältnisses.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="text-left px-4 py-2 border border-gray-200 font-medium">Zweck</th>
                    <th className="text-left px-4 py-2 border border-gray-200 font-medium">Rechtsgrundlage</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="px-4 py-2 border border-gray-200">Arbeitszeiterfassung</td>
                    <td className="px-4 py-2 border border-gray-200">Art. 6 Abs. 1 lit. c DSGVO i.V.m. ArbZG §16</td>
                  </tr>
                  <tr className="bg-gray-50">
                    <td className="px-4 py-2 border border-gray-200">Urlaubsverwaltung</td>
                    <td className="px-4 py-2 border border-gray-200">Art. 6 Abs. 1 lit. b DSGVO (Durchführung Arbeitsverhältnis)</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 border border-gray-200">Krankmeldungen / Abwesenheiten</td>
                    <td className="px-4 py-2 border border-gray-200">Art. 9 Abs. 2 lit. b DSGVO (arbeitsrechtliche Pflichten)</td>
                  </tr>
                  <tr className="bg-gray-50">
                    <td className="px-4 py-2 border border-gray-200">Lohnabrechnung / Überstunden</td>
                    <td className="px-4 py-2 border border-gray-200">Art. 6 Abs. 1 lit. b DSGVO</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 border border-gray-200">ArbZG-Compliance (§3, §4, §5, §6, §9–§11)</td>
                    <td className="px-4 py-2 border border-gray-200">Art. 6 Abs. 1 lit. c DSGVO</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* 3. Datenkategorien */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">3. Verarbeitete Datenkategorien</h2>
            <ul className="space-y-2 text-gray-600">
              <li className="flex gap-2">
                <span className="text-primary mt-1">•</span>
                <span><strong>Stammdaten:</strong> Vor- und Nachname, Benutzername, E-Mail-Adresse (optional), Wochenstunden, Arbeitstage</span>
              </li>
              <li className="flex gap-2">
                <span className="text-primary mt-1">•</span>
                <span><strong>Zeiterfassungsdaten:</strong> Arbeitsbeginn, Arbeitsende, Pausenzeiten, tägliche Arbeitszeit, Bemerkungen</span>
              </li>
              <li className="flex gap-2">
                <span className="text-primary mt-1">•</span>
                <span><strong>Abwesenheitsdaten:</strong> Urlaub, Fortbildung, sonstige Abwesenheiten</span>
              </li>
              <li className="flex gap-2">
                <span className="text-primary mt-1">•</span>
                <span>
                  <strong>Gesundheitsdaten (Art. 9 DSGVO):</strong> Krankmeldungen / Krankheitsabwesenheiten.
                  Diese werden besonders geschützt verarbeitet und sind in Exporten standardmäßig ausgeblendet.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-primary mt-1">•</span>
                <span><strong>Technische Daten:</strong> Passwort (gehasht, nicht lesbar), JWT-Token (nur im Browser)</span>
              </li>
            </ul>
          </section>

          {/* 4. Aufbewahrungsfristen */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">4. Aufbewahrungsfristen</h2>
            <p className="text-gray-600 mb-3">
              Arbeitszeitaufzeichnungen unterliegen gemäß <strong>ArbZG §16 Abs. 2</strong> einer
              gesetzlichen Aufbewahrungspflicht von <strong>mindestens 2 Jahren</strong>.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="text-left px-4 py-2 border border-gray-200 font-medium">Datenkategorie</th>
                    <th className="text-left px-4 py-2 border border-gray-200 font-medium">Aufbewahrungsfrist</th>
                    <th className="text-left px-4 py-2 border border-gray-200 font-medium">Rechtsgrundlage</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="px-4 py-2 border border-gray-200">Zeiteinträge (Arbeitszeitaufzeichnungen)</td>
                    <td className="px-4 py-2 border border-gray-200">Mindestens 2 Jahre</td>
                    <td className="px-4 py-2 border border-gray-200">ArbZG §16 Abs. 2</td>
                  </tr>
                  <tr className="bg-gray-50">
                    <td className="px-4 py-2 border border-gray-200">Urlaubsdaten</td>
                    <td className="px-4 py-2 border border-gray-200">3 Jahre (steuerliche Aufbewahrung)</td>
                    <td className="px-4 py-2 border border-gray-200">§ 147 AO</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 border border-gray-200">Krankmeldungen (Abwesenheiten)</td>
                    <td className="px-4 py-2 border border-gray-200">Bis zur Löschung des Accounts (keine gesetzl. Pflicht)</td>
                    <td className="px-4 py-2 border border-gray-200">Art. 5 Abs. 1 lit. e DSGVO</td>
                  </tr>
                  <tr className="bg-gray-50">
                    <td className="px-4 py-2 border border-gray-200">Benutzerkonto (nach Austritt)</td>
                    <td className="px-4 py-2 border border-gray-200">Anonymisierung nach Deaktivierung; Endlöschung nach 2 Jahren</td>
                    <td className="px-4 py-2 border border-gray-200">Art. 17 DSGVO i.V.m. ArbZG §16</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
              <strong>Hinweis zum Löschkonzept:</strong> Nach Deaktivierung eines Benutzeraccounts werden
              personenbezogene Stammdaten anonymisiert. Zeiteinträge bleiben für die gesetzliche
              Aufbewahrungsfrist (ArbZG §16) ohne Personenbezug erhalten und werden nach Ablauf von
              2 Jahren endgültig gelöscht.
            </div>
          </section>

          {/* 5. Empfänger */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">5. Empfänger der Daten</h2>
            <p className="text-gray-600">
              Personenbezogene Daten werden nicht an Dritte weitergegeben. Die Anwendung wird auf
              dem Server des Arbeitgebers (On-Premises) betrieben. Es findet keine Übermittlung in
              Drittländer außerhalb der EU/EWR statt.
            </p>
          </section>

          {/* 6. Ihre Rechte */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">6. Ihre Rechte als betroffene Person</h2>
            <p className="text-gray-600 mb-4">
              Gemäß DSGVO stehen Ihnen folgende Rechte zu. Bitte wenden Sie sich dazu an Ihren Arbeitgeber:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { title: 'Auskunftsrecht (Art. 15)', desc: 'Welche Daten über Sie gespeichert sind' },
                { title: 'Berichtigungsrecht (Art. 16)', desc: 'Korrektur unrichtiger Daten' },
                { title: 'Löschungsrecht (Art. 17)', desc: 'Löschung nach Ablauf der Aufbewahrungspflichten' },
                { title: 'Einschränkung (Art. 18)', desc: 'Einschränkung der Verarbeitung' },
                { title: 'Datenübertragbarkeit (Art. 20)', desc: 'Export Ihrer Daten in maschinenlesbarem Format' },
                { title: 'Widerspruchsrecht (Art. 21)', desc: 'Widerspruch gegen bestimmte Verarbeitungen' },
              ].map((right) => (
                <div key={right.title} className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                  <p className="font-medium text-sm text-gray-800">{right.title}</p>
                  <p className="text-xs text-gray-600 mt-1">{right.desc}</p>
                </div>
              ))}
            </div>
            <p className="text-gray-600 mt-4 text-sm">
              Sie haben außerdem das Recht, sich bei der zuständigen Datenschutz-Aufsichtsbehörde zu
              beschweren (in Bayern: Bayerisches Landesamt für Datenschutzaufsicht, <em>www.lda.bayern.de</em>).
            </p>
          </section>

          {/* 7. Datensicherheit */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">7. Datensicherheit</h2>
            <ul className="space-y-1 text-gray-600 text-sm">
              <li>• Passwörter werden mittels bcrypt gehasht und sind nicht lesbar</li>
              <li>• Alle Verbindungen werden über HTTPS verschlüsselt (in Produktionsumgebungen)</li>
              <li>• Zugriffsschutz über Rollen (Admin/Mitarbeiter) und JWT-Token-Authentifizierung</li>
              <li>• Automatische Token-Invalidierung bei Passwortänderung oder Deaktivierung</li>
              <li>• Zugriffs- und Änderungsprotokoll (Audit-Log) für alle Zeiterfassungsänderungen</li>
              <li>• Gesundheitsdaten (Art. 9 DSGVO) in Exporten standardmäßig geschwärzt und audit-geloggt</li>
            </ul>
          </section>

          {/* 8. Kontakt */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">8. Kontakt bei Datenschutzfragen</h2>
            <p className="text-gray-600">
              Bei Fragen zur Verarbeitung Ihrer personenbezogenen Daten wenden Sie sich bitte an
              den für Sie zuständigen Vorgesetzten oder an den Betreiber dieser Anwendung.
            </p>
          </section>

        </div>

        <div className="mt-6 text-center">
          <Link
            to="/login"
            className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-primary transition-colors"
          >
            <ArrowLeft size={14} />
            Zurück zur Anmeldung
          </Link>
        </div>
      </div>
    </div>
  );
}
