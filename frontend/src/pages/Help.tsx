import { useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import { Download, HelpCircle, ChevronDown, ChevronRight } from 'lucide-react';

// ── Cheatsheet content ─────────────────────────────────────────────────────────

function CheatsheetMitarbeiter() {
  return (
    <div className="space-y-8">
      {/* Login */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">🔐 Login</h3>
        <p className="text-sm text-gray-600">Benutzernamen und Passwort eingeben → <span className="font-medium">Anmelden</span>.</p>
      </section>

      {/* Zeiterfassung */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">⏱️ Zeiterfassung</h3>
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Neuer Eintrag</p>
            <ol className="text-sm text-gray-600 list-decimal list-inside space-y-0.5">
              <li>Zeiterfassung → Hinzufügen</li>
              <li>Datum, Start- und Endzeit eintragen</li>
              <li>Pause in Minuten (Pflicht!)</li>
              <li>Speichern</li>
            </ol>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Pflichtpausen (§4 ArbZG)</p>
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-50">
                  <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Arbeitszeit</th>
                  <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Mindestpause</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="px-3 py-2 border border-gray-200 text-gray-600">&gt; 6 Stunden</td>
                  <td className="px-3 py-2 border border-gray-200 font-medium text-amber-700">30 Minuten</td>
                </tr>
                <tr className="bg-gray-50">
                  <td className="px-3 py-2 border border-gray-200 text-gray-600">&gt; 9 Stunden</td>
                  <td className="px-3 py-2 border border-gray-200 font-medium text-amber-700">45 Minuten</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Tagesgrenze (§3 ArbZG)</p>
            <ul className="text-sm text-gray-600 space-y-0.5">
              <li>⚠️ Warnung ab 8 Stunden Nettoarbeitszeit</li>
              <li>🚫 Gesperrt ab 10 Stunden Nettoarbeitszeit</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Abwesenheiten */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">🗓️ Abwesenheiten</h3>
        <table className="w-full text-sm border-collapse mb-3">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Aktion</th>
              <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Beschreibung</th>
            </tr>
          </thead>
          <tbody>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Abwesenheit eintragen</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Formular öffnen</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 text-gray-600">Einzeltag</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Nur Startdatum</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 text-gray-600">Zeitraum</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Checkbox „Zeitraum" + Enddatum</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 text-gray-600">Eintrag löschen</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Im Kalender klicken → Löschen-Symbol</td></tr>
          </tbody>
        </table>
      </section>

      {/* Korrekturanträge */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">📋 Korrekturantrag stellen</h3>
        <ol className="text-sm text-gray-600 list-decimal list-inside space-y-0.5">
          <li>Zeiterfassung → Tab „Anträge" → Neuer Antrag</li>
          <li>Betroffenes Datum wählen</li>
          <li>Korrekte Zeiten eintragen</li>
          <li>Begründung schreiben → Absenden</li>
        </ol>
        <p className="text-sm text-gray-500 mt-2">Admin genehmigt oder lehnt ab. Status ist in der Liste sichtbar.</p>
      </section>

      {/* Dashboard */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">📊 Dashboard verstehen</h3>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Karte</th>
              <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Bedeutung</th>
            </tr>
          </thead>
          <tbody>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Monatssaldo</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Über-/Unterstunden diesen Monat</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Überstunden gesamt</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Saldo über alle Monate</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Urlaub verbleibend</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Verfügbare Urlaubstage</td></tr>
          </tbody>
        </table>
        <p className="text-sm text-gray-500 mt-2">Grüner Saldo (+) = Überstunden | Roter Saldo (–) = Fehlstunden</p>
      </section>

      {/* Passwort */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">🔑 Passwort ändern</h3>
        <p className="text-sm text-gray-600">Profil → Abschnitt „Passwort ändern" → Altes + Neues Passwort + Bestätigen → Speichern</p>
        <p className="text-sm text-gray-500 mt-1">Mind. 8 Zeichen, Groß- + Kleinbuchstabe, mind. eine Ziffer.</p>
      </section>
    </div>
  );
}

function CheatsheetAdmin() {
  return (
    <div className="space-y-8">
      {/* Login */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">🔐 Login & Navigation</h3>
        <p className="text-sm text-gray-600">Mitarbeiter: Dashboard · Zeiterfassung (Einträge, Journal, Anträge) · Abwesenheiten · Profil</p>
        <p className="text-sm text-gray-600 mt-1">Admin zusätzlich: Admin-Dashboard · Benutzerverwaltung · Berichte · Abwesenheiten · Audit-Log · Einstellungen</p>
      </section>

      {/* Benutzerverwaltung */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">👤 Benutzerverwaltung</h3>
        <div className="space-y-3">
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Neuen Mitarbeiter anlegen</p>
            <ol className="text-sm text-gray-600 list-decimal list-inside space-y-0.5">
              <li>Benutzerverwaltung → Neuer Benutzer</li>
              <li>Benutzername, Vor-/Nachname, Passwort</li>
              <li>Wochenstunden, Arbeitstage/Woche, Urlaubstage</li>
              <li>Rolle: Mitarbeiter oder Admin</li>
            </ol>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Stundenänderung</p>
            <p className="text-sm text-gray-600">Benutzer bearbeiten → neue Wochenstunden + Wirkungsdatum → historische Salden bleiben korrekt.</p>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded p-2">
            <p className="text-sm text-amber-800">⚠️ Niemals löschen! Status auf „Inaktiv" setzen. 2 Jahre Aufbewahrung (§16 ArbZG).</p>
          </div>
        </div>
      </section>

      {/* Berichte */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">📊 Berichte & Exporte</h3>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Bericht</th>
              <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Verwendung</th>
            </tr>
          </thead>
          <tbody>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Monatsreport</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Gehaltsabrechnung</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Jahresreport Classic</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Jahresüberblick, schnell</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Jahresreport Detailliert</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Steuerberater, Prüfung</td></tr>
          </tbody>
        </table>
        <p className="text-sm text-gray-500 mt-2">Aufbewahrungspflicht: 2 Jahre (§16 ArbZG)</p>
      </section>

      {/* Korrekturanträge */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">✅ Korrekturanträge prüfen</h3>
        <ol className="text-sm text-gray-600 list-decimal list-inside space-y-0.5">
          <li>Korrekturanträge → offene Anträge → Prüfen</li>
          <li>Alt- und Neuwerte + Begründung lesen</li>
          <li>Genehmigen oder Ablehnen (mit optionalem Grund)</li>
        </ol>
      </section>

      {/* Betriebsferien */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">📅 Betriebsferien</h3>
        <p className="text-sm text-gray-600">Abwesenheiten → Neue Betriebsferien → Bezeichnung + Von–Bis → Speichern</p>
        <p className="text-sm text-gray-500 mt-1">Alle MA erhalten automatisch Einträge (keine Urlaubstage!)</p>
      </section>

      {/* ArbZG */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">⚖️ ArbZG-Prüfungen</h3>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">§</th>
              <th className="text-left px-3 py-2 border border-gray-200 font-medium text-gray-700">Prüfung</th>
            </tr>
          </thead>
          <tbody>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§3</td><td className="px-3 py-2 border border-gray-200 text-gray-600">8h-Warnung, 10h-Hard-Stop</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§4</td><td className="px-3 py-2 border border-gray-200 text-gray-600">30/45 Min. Pausenpflicht</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§5</td><td className="px-3 py-2 border border-gray-200 text-gray-600">11h Mindestruhezeit</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§11</td><td className="px-3 py-2 border border-gray-200 text-gray-600">15 freie Sonntage/Jahr</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§14</td><td className="px-3 py-2 border border-gray-200 text-gray-600">48h-Wochenwarnung</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§18</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Ausnahme für leitende Angestellte</td></tr>
          </tbody>
        </table>
      </section>
    </div>
  );
}

// ── Handbuch accordion ─────────────────────────────────────────────────────────

interface AccordionItem {
  title: string;
  content: React.ReactNode;
}

function Accordion({ items }: { items: AccordionItem[] }) {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="divide-y divide-gray-200 border border-gray-200 rounded-lg overflow-hidden">
      {items.map((item, i) => (
        <div key={i}>
          <button
            onClick={() => setOpen(open === i ? null : i)}
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition-colors"
          >
            <span className="font-medium text-gray-800 text-sm">{item.title}</span>
            {open === i
              ? <ChevronDown size={16} className="text-gray-500 flex-shrink-0" />
              : <ChevronRight size={16} className="text-gray-500 flex-shrink-0" />}
          </button>
          {open === i && (
            <div className="px-4 py-3 text-sm text-gray-600 bg-gray-50 border-t border-gray-200">
              {item.content}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

const handbuchMitarbeiterSections: AccordionItem[] = [
  {
    title: '1. Erste Schritte & Login',
    content: (
      <div className="space-y-2">
        <p>Öffnen Sie PraxisZeit im Browser und melden Sie sich mit Ihrem Benutzernamen und Passwort an. Nach dem Login landen Sie automatisch auf dem Dashboard.</p>
        <p>Falls Sie Ihr Passwort vergessen haben, wenden Sie sich an Ihren Administrator.</p>
      </div>
    ),
  },
  {
    title: '2. Zeiterfassung – Einträge erstellen & bearbeiten',
    content: (
      <div className="space-y-2">
        <p>Navigieren Sie zu <strong>Zeiterfassung</strong>. Klicken Sie auf <strong>Hinzufügen</strong>, wählen Sie Datum, Start- und Endzeit, tragen Sie die Pause in Minuten ein und speichern Sie den Eintrag.</p>
        <p>Einträge der aktuellen Woche können direkt bearbeitet werden. Ältere Einträge erfordern einen Korrekturantrag.</p>
        <p className="text-amber-700 font-medium">ArbZG: Pflichtpause ab 6h (30 Min.), ab 9h (45 Min.). Maximum 10h Nettoarbeitszeit.</p>
      </div>
    ),
  },
  {
    title: '3. Abwesenheiten eintragen',
    content: (
      <div className="space-y-2">
        <p>Navigieren Sie zu <strong>Abwesenheiten</strong> und klicken Sie auf <strong>Abwesenheit eintragen</strong>. Wählen Sie den Typ (Urlaub, Krank, Fortbildung, Überstundenausgleich, Sonstiges) und das Datum.</p>
        <p>Für Zeiträume aktivieren Sie die Checkbox „Zeitraum" und geben Sie ein Enddatum an. Wochenenden und Feiertage werden automatisch ausgeschlossen.</p>
      </div>
    ),
  },
  {
    title: '4. Korrekturanträge stellen',
    content: (
      <div className="space-y-2">
        <p>Wenn ein vergangener Zeiteintrag korrigiert werden muss, navigieren Sie zu <strong>Zeiterfassung → Tab „Anträge" → Neuer Antrag</strong>.</p>
        <p>Wählen Sie das betroffene Datum, tragen Sie die korrekten Werte ein und schreiben Sie eine Begründung. Der Administrator prüft und genehmigt oder lehnt den Antrag ab.</p>
      </div>
    ),
  },
  {
    title: '5. Dashboard & Saldo verstehen',
    content: (
      <div className="space-y-2">
        <p>Das Dashboard zeigt Ihren Monatssaldo (Ist – Soll), den kumulierten Gesamtsaldo und das Urlaubskonto. Ein positiver Saldo bedeutet Überstunden, ein negativer Fehlstunden.</p>
        <p>Das Balkendiagramm zeigt die letzten 6 Monate auf einen Blick.</p>
      </div>
    ),
  },
  {
    title: '6. Profil & Passwort',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Profil</strong> können Sie Ihr Passwort ändern (mind. 8 Zeichen, Groß-/Kleinbuchstabe, Ziffer) und Ihre Kalenderfarbe für den Team-Kalender festlegen.</p>
        <p>Persönliche Daten wie Name und Wochenstunden können nur vom Administrator geändert werden.</p>
      </div>
    ),
  },
];

const handbuchAdminSections: AccordionItem[] = [
  {
    title: '1. Benutzerverwaltung',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Benutzerverwaltung</strong> können Sie Mitarbeiter anlegen, bearbeiten und deaktivieren. Löschen Sie Mitarbeiter nie – setzen Sie stattdessen den Status auf „Inaktiv" (Aufbewahrungspflicht §16 ArbZG, 2 Jahre).</p>
        <p>Für Teilzeit-Anpassungen tragen Sie bei „Benutzer bearbeiten" die neuen Wochenstunden mit Wirkungsdatum ein. Historische Salden bleiben korrekt.</p>
      </div>
    ),
  },
  {
    title: '2. Berichte & Excel-Exporte',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> können Sie drei Export-Typen erstellen: Monatsreport (für Gehaltsabrechnung), Jahresreport Classic (kompakt) und Jahresreport Detailliert (vollständig, für Steuerberater).</p>
        <p>Die exportierten Berichte müssen gemäß §16 ArbZG mindestens 2 Jahre aufbewahrt werden.</p>
      </div>
    ),
  },
  {
    title: '3. Korrekturanträge genehmigen',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Korrekturanträge</strong> sehen Sie alle offenen Anträge. Vergleichen Sie Alt- und Neuwerte, lesen Sie die Begründung und genehmigen oder lehnen Sie den Antrag ab.</p>
        <p>Bei Ablehnung können Sie optional einen Grund eingeben, der dem Mitarbeiter angezeigt wird.</p>
      </div>
    ),
  },
  {
    title: '4. Betriebsferien einrichten',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Abwesenheiten</strong> können Betriebsferien angelegt werden. Nach dem Speichern erhalten alle aktiven Mitarbeiter automatisch Abwesenheitseinträge (ohne Urlaubsabzug).</p>
        <p>Beim Löschen von Betriebsferien werden die Einträge bei allen Mitarbeitern automatisch entfernt.</p>
      </div>
    ),
  },
  {
    title: '5. ArbZG-Berichte & Compliance',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> finden Sie spezialisierte ArbZG-Berichte: Ruhezeitverstöße (§5), Sonntagsarbeit mit 15-freie-Sonntage-Tracking (§11) und Nachtarbeit-Übersicht (§6).</p>
        <p>Das System prüft automatisch alle gesetzlichen Grenzen bei der Eingabe von Zeiteinträgen. Mitarbeiter mit ArbZG-Ausnahme (§18) sind von den Prüfungen ausgenommen.</p>
      </div>
    ),
  },
  {
    title: '6. Audit-Log & Fehler-Monitoring',
    content: (
      <div className="space-y-2">
        <p>Das <strong>Änderungsprotokoll</strong> zeichnet alle Admin-Aktionen auf und kann nicht gelöscht werden. Es dient als Nachweis gemäß §16 ArbZG.</p>
        <p>Das <strong>Fehler-Monitoring</strong> zeigt automatisch erfasste Backend-Fehler mit Stacktrace und ermöglicht die direkte Meldung als GitHub Issue.</p>
      </div>
    ),
  },
];

// ── Main Help page ─────────────────────────────────────────────────────────────

export default function Help() {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'cheatsheet' | 'handbuch'>('cheatsheet');
  const isAdmin = user?.role === 'admin';

  const cheatsheetFile = isAdmin
    ? '/help/CHEATSHEET-ADMIN.md'
    : '/help/CHEATSHEET-MITARBEITER.md';
  const handbuchFile = isAdmin
    ? '/help/HANDBUCH-ADMIN.md'
    : '/help/HANDBUCH-MITARBEITER.md';

  return (
    <div>
      {/* Header */}
      <div className="flex items-center space-x-3 mb-6">
        <HelpCircle size={28} className="text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Hilfe &amp; Dokumentation</h1>
          <p className="text-sm text-gray-500">
            {isAdmin ? 'Administratoren-Dokumentation' : 'Mitarbeiter-Dokumentation'}
          </p>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="border-b border-gray-200 mb-6">
        <div className="flex space-x-6">
          {(['cheatsheet', 'handbuch'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab === 'cheatsheet' ? 'Kurzanleitung' : 'Handbuch'}
            </button>
          ))}
        </div>
      </div>

      {/* Cheatsheet Tab */}
      {activeTab === 'cheatsheet' && (
        <div>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-semibold text-gray-800">
              {isAdmin ? 'Kurzanleitung für Administratoren' : 'Kurzanleitung für Mitarbeiter'}
            </h2>
            <a
              href={cheatsheetFile}
              download
              className="flex items-center space-x-1.5 px-3 py-1.5 text-sm text-primary border border-primary rounded-lg hover:bg-primary hover:text-white transition-colors"
            >
              <Download size={14} />
              <span>Herunterladen (.md)</span>
            </a>
          </div>
          {isAdmin ? <CheatsheetAdmin /> : <CheatsheetMitarbeiter />}
        </div>
      )}

      {/* Handbuch Tab */}
      {activeTab === 'handbuch' && (
        <div>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-semibold text-gray-800">
              {isAdmin ? 'Administrator-Handbuch' : 'Mitarbeiter-Handbuch'}
            </h2>
            <a
              href={handbuchFile}
              download
              className="flex items-center space-x-1.5 px-3 py-1.5 text-sm text-primary border border-primary rounded-lg hover:bg-primary hover:text-white transition-colors"
            >
              <Download size={14} />
              <span>Vollständiges Handbuch (.md)</span>
            </a>
          </div>
          <p className="text-sm text-gray-500 mb-5">
            Klicken Sie auf einen Abschnitt, um ihn aufzuklappen. Das vollständige Handbuch können Sie als Markdown-Datei herunterladen.
          </p>
          <Accordion items={isAdmin ? handbuchAdminSections : handbuchMitarbeiterSections} />
        </div>
      )}
    </div>
  );
}
