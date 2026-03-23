import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────────────

export interface AccordionItem {
  title: string;
  content: ReactNode;
}

// ── Accordion ────────────────────────────────────────────────────────────────

export function Accordion({ items }: { items: AccordionItem[] }) {
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

// ── Cheatsheet content ───────────────────────────────────────────────────────

export function CheatsheetMitarbeiter() {
  return (
    <div className="space-y-8">
      {/* Navigation */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">🔐 Login & Navigation</h3>
        <p className="text-sm text-gray-600 mb-1">Benutzernamen und Passwort eingeben → <span className="font-medium">Anmelden</span>.</p>
        <p className="text-sm text-gray-500">Desktop (links): Dashboard · Zeiterfassung · Abwesenheiten · Profil</p>
        <p className="text-sm text-gray-500">Mobil (unten): Home · Journal · Abwes. · Profil | ☰ öffnet vollständige Navigation</p>
      </section>

      {/* Zeiterfassung */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">⏱️ Zeiterfassung</h3>
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Neuer Eintrag</p>
            <ol className="text-sm text-gray-600 list-decimal list-inside space-y-0.5">
              <li>Zeiterfassung → Tab <strong>Einträge</strong> → <strong>+ Neuer Eintrag</strong></li>
              <li>Datum, Von, Bis eintragen</li>
              <li>Pause in Minuten (Pflicht!)</li>
              <li>Speichern</li>
            </ol>
            <p className="text-sm text-gray-500 mt-1">Mobil: <strong>+</strong>-Button oben rechts auf der Seite</p>
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

      {/* Korrekturanträge */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">📋 Korrekturantrag stellen</h3>
        <p className="text-sm text-gray-600 mb-1">Bei gesperrten oder älteren Einträgen:</p>
        <ol className="text-sm text-gray-600 list-decimal list-inside space-y-0.5">
          <li>Zeiterfassung → Tab <strong>Einträge</strong> → Zeile des Eintrags</li>
          <li>Button <strong>Änderungsantrag</strong> klicken</li>
          <li>Korrekte Zeiten eintragen + Begründung</li>
          <li><strong>Antrag stellen</strong></li>
        </ol>
        <p className="text-sm text-gray-500 mt-2">Status einsehen: Zeiterfassung → Tab <strong>Anträge</strong> (Filter: Alle/Offen/Genehmigt/Abgelehnt)</p>
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
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">+ Abwesenheit eintragen</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Formular öffnen, Typ wählen</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 text-gray-600">Einzeltag</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Nur Startdatum</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 text-gray-600">Zeitraum</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Checkbox „Zeitraum" + Enddatum</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 text-gray-600">Eintrag löschen</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Kalender-Eintrag anklicken → Löschen</td></tr>
          </tbody>
        </table>
        <p className="text-sm text-gray-500">Bei Urlaubsgenehmigungspflicht: Tab <strong>„Meine Anträge"</strong> zeigt Status</p>
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
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Tagessaldo</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Heute: Ist vs. Tagessoll (grün = eingestempelt)</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Monatssaldo</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Über-/Unterstunden diesen Monat (H:MM)</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Überstunden</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Kumulierter Jahressaldo</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Urlaub</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Verbleibende Urlaubstage</td></tr>
          </tbody>
        </table>
        <p className="text-sm text-gray-500 mt-2">Grüner Saldo (+) = Überstunden | Roter Saldo (–) = Fehlstunden</p>
      </section>

      {/* Passwort */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">🔑 Passwort ändern</h3>
        <p className="text-sm text-gray-600">Profil → <strong>Passwort ändern</strong> → Ändern → Altes + Neues Passwort + Bestätigen → Speichern</p>
        <p className="text-sm text-gray-500 mt-1">Mind. 10 Zeichen, Groß- + Kleinbuchstabe + Ziffer.</p>
      </section>
    </div>
  );
}

export function CheatsheetAdmin() {
  return (
    <div className="space-y-8">
      {/* Login */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">🔐 Login & Navigation</h3>
        <p className="text-sm text-gray-600">Mitarbeiter-Bereich: Dashboard · Zeiterfassung · Abwesenheiten · Profil</p>
        <p className="text-sm text-gray-600 mt-1">Administration: Admin-Dashboard · Benutzerverwaltung · Änderungsanträge · Berichte · Abwesenheiten · Änderungsprotokoll · Fehler-Monitoring · Urlaubsanträge · Import · Einstellungen</p>
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

// ── Handbuch sections ────────────────────────────────────────────────────────

export const handbuchMitarbeiterSections: AccordionItem[] = [
  {
    title: '1. Erste Schritte & Login',
    content: (
      <div className="space-y-2">
        <p>Öffnen Sie PraxisZeit im Browser und melden Sie sich mit Ihrem <strong>Benutzernamen</strong> und <strong>Passwort</strong> an. Nach dem Login landen Sie automatisch auf dem Dashboard.</p>
        <p>Falls Sie Ihr Passwort vergessen haben, wenden Sie sich an Ihren Administrator.</p>
      </div>
    ),
  },
  {
    title: '2. Dashboard & Saldo verstehen',
    content: (
      <div className="space-y-2">
        <p>Das Dashboard zeigt Ihren <strong>Tagessaldo</strong> (heute: Ist vs. Tagessoll), den <strong>Monatssaldo</strong> (Ist – Soll in H:MM), den kumulierten Jahressaldo und das Urlaubskonto.</p>
        <p>Grüner Saldo = Überstunden, roter Saldo = Fehlstunden. Auf mobilen Geräten wird die untere Tab-Leiste zur Navigation genutzt.</p>
      </div>
    ),
  },
  {
    title: '3. Zeiterfassung – Einträge erstellen & bearbeiten',
    content: (
      <div className="space-y-2">
        <p>Navigieren Sie zu <strong>Zeiterfassung → Tab „Einträge"</strong>. Klicken Sie auf <strong>+ Neuer Eintrag</strong>. Das Formular erscheint direkt über der Tabelle – Datum, Von, Bis und Pause ausfüllen, dann Speichern.</p>
        <p>Aktuelle entsperrte Einträge können direkt über <strong>Bearbeiten</strong> geändert werden. Ältere oder gesperrte Einträge erfordern einen Korrekturantrag.</p>
        <p className="text-amber-700 font-medium">ArbZG: Pflichtpause ab 6h (30 Min.), ab 9h (45 Min.). Maximum 10h Nettoarbeitszeit.</p>
      </div>
    ),
  },
  {
    title: '4. Korrekturanträge stellen & verwalten',
    content: (
      <div className="space-y-2">
        <p>Wenn ein gesperrter Eintrag korrigiert werden muss: <strong>Zeiterfassung → Tab „Einträge"</strong> → in der Aktionsspalte auf <strong>Änderungsantrag</strong> klicken → korrekte Zeiten + Begründung eingeben → Antrag stellen.</p>
        <p>Den Status aller Anträge sehen Sie unter <strong>Zeiterfassung → Tab „Anträge"</strong>. Filter: Alle / Offen / Genehmigt / Abgelehnt. Offene Anträge können mit <strong>Zurückziehen</strong> storniert werden.</p>
      </div>
    ),
  },
  {
    title: '5. Abwesenheiten eintragen',
    content: (
      <div className="space-y-2">
        <p>Navigieren Sie zu <strong>Abwesenheiten</strong> und klicken Sie auf <strong>+ Abwesenheit eintragen</strong>. Wählen Sie den Typ (Urlaub, Krank, Fortbildung, Sonstiges) und das Datum.</p>
        <p>Für Zeiträume aktivieren Sie die Checkbox <strong>„Zeitraum"</strong> und geben ein Enddatum an. Wochenenden und Feiertage werden automatisch ausgeschlossen.</p>
        <p>Wenn Urlaubsgenehmigungspflicht aktiv ist, wechselt die App nach dem Absenden automatisch zum Tab <strong>„Meine Anträge"</strong>.</p>
      </div>
    ),
  },
  {
    title: '6. Profil & Passwort',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Profil</strong> sehen Sie Ihre persönlichen Daten. Über <strong>Passwort ändern → Ändern</strong> setzen Sie ein neues Passwort (mind. 10 Zeichen, Groß-/Kleinbuchstabe, Ziffer).</p>
        <p>Persönliche Daten wie Name und Wochenstunden können nur vom Administrator geändert werden. Unter <strong>Weitere Einstellungen</strong> finden Sie optionale Darstellungsoptionen.</p>
      </div>
    ),
  },
];

export const handbuchAdminSections: AccordionItem[] = [
  {
    title: '1. Admin-Dashboard & Teamübersicht',
    content: (
      <div className="space-y-2">
        <p>Das <strong>Admin-Dashboard</strong> zeigt alle aktiven Mitarbeiter mit Soll, Ist, Saldo (H:MM), kumulierten Überstunden, verbleibenden Urlaubstagen und Kranktagen für den gewählten Monat.</p>
        <p>Klicken Sie auf den Pfeil am Ende einer Zeile für die Detailansicht. Nutzen Sie die Suche zum Filtern nach Name.</p>
      </div>
    ),
  },
  {
    title: '2. Benutzerverwaltung',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Benutzerverwaltung</strong> legen Sie Mitarbeiter an (<strong>Neuer Mitarbeiter:in</strong>), bearbeiten und deaktivieren sie. Niemals löschen – Status auf „Inaktiv" setzen (Aufbewahrungspflicht §16 ArbZG, 2 Jahre).</p>
        <p>Für Teilzeit-Anpassungen: Benutzer öffnen → neue Wochenstunden + <strong>Wirkungsdatum</strong> eintragen. Historische Salden bleiben korrekt. Checkboxen: „ArbZG-Prüfungen aussetzen" für §18, „Nachtarbeitnehmer" für §6.</p>
      </div>
    ),
  },
  {
    title: '3. Berichte & Excel-Exporte',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> stehen drei Export-Typen bereit: <strong>Monatsreport</strong> (Gehaltsabrechnung), <strong>Jahresreport Classic</strong> (12 Monate kompakt) und <strong>Jahresreport Detailliert</strong> (365 Tage, für Steuerberater). Jeder Report ist als Excel oder CSV verfügbar.</p>
        <p>Aufbewahrungspflicht: <strong>2 Jahre</strong> (§16 ArbZG). Regelmäßig exportieren und sicher archivieren.</p>
      </div>
    ),
  },
  {
    title: '4. Korrekturanträge genehmigen',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Änderungsanträge</strong> sehen Sie alle offenen Anträge. Antrag öffnen → Alt- und Neuwerte vergleichen → Begründung lesen → <strong>Genehmigen</strong> oder <strong>Ablehnen</strong> (mit optionalem Grund).</p>
        <p>Bei Genehmigung wird der Zeiteintrag sofort geändert. Der Mitarbeiter sieht den Status unter Zeiterfassung → Tab „Anträge".</p>
      </div>
    ),
  },
  {
    title: '5. Urlaubsanträge & Betriebsferien',
    content: (
      <div className="space-y-2">
        <p><strong>Urlaubsanträge:</strong> Toggle „Genehmigungspflicht" aktiviert den Workflow. Anträge erscheinen als „Offen" → Genehmigen (grün) oder Ablehnen (rot, optional Grund).</p>
        <p><strong>Betriebsferien:</strong> Abwesenheiten → Tab „Betriebsferien" → Neue Betriebsferien. Alle aktiven Mitarbeiter erhalten automatisch Abwesenheitseinträge (kein Urlaubsabzug). Beim Löschen werden alle Einträge entfernt.</p>
      </div>
    ),
  },
  {
    title: '6. ArbZG-Berichte & Compliance',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> (nach unten scrollen) finden Sie: <strong>§5 Ruhezeitverstöße</strong> (&lt;11h zwischen Arbeitstagen), <strong>§6 Nachtarbeit</strong> (≥48 Nachtarbeitstage/Jahr), <strong>§11 Sonntagsarbeit</strong> (max. 37/Jahr) und <strong>§11 Ersatzruhetag</strong> (Fristen überwachen).</p>
        <p>Das System prüft bei jeder Eingabe automatisch §3 (10h-Hard-Stop), §4 (Pausenpflicht), §6 (8h für Nachtarbeitnehmer), §9/10 (Sonntagsarbeit), §14 (48h-Wochenwarnung).</p>
      </div>
    ),
  },
  {
    title: '7. Audit-Log & Fehler-Monitoring',
    content: (
      <div className="space-y-2">
        <p>Das <strong>Änderungsprotokoll</strong> zeichnet alle Aktionen unveränderlich auf (Login, Zeiteinträge, Abwesenheiten, Benutzerverwaltung, Korrekturanträge). Dient als Nachweis gem. §16 ArbZG bei Betriebsprüfungen.</p>
        <p>Das <strong>Fehler-Monitoring</strong> zeigt Backend-Fehler mit Häufigkeit und Kontext. Wiederkehrende Fehler als GitHub Issue melden (Button in der Detailansicht).</p>
      </div>
    ),
  },
];

// ── DocViewerContent ─────────────────────────────────────────────────────────

export type DocTab = 'cheatsheet' | 'handbuch';

interface DocViewerContentProps {
  isAdmin: boolean;
  initialTab?: DocTab;
  onTabChange?: (tab: DocTab) => void;
}

export function DocViewerContent({ isAdmin, initialTab = 'cheatsheet', onTabChange }: DocViewerContentProps) {
  const [activeTab, setActiveTab] = useState<DocTab>(initialTab);

  function handleTab(tab: DocTab) {
    setActiveTab(tab);
    onTabChange?.(tab);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="border-b border-gray-200 px-4 flex gap-6 flex-shrink-0">
        {(['cheatsheet', 'handbuch'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => handleTab(tab)}
            className={`py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab === 'cheatsheet' ? 'Kurzanleitung' : 'Handbuch'}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'cheatsheet'
          ? (isAdmin ? <CheatsheetAdmin /> : <CheatsheetMitarbeiter />)
          : <Accordion items={isAdmin ? handbuchAdminSections : handbuchMitarbeiterSections} />
        }
      </div>
    </div>
  );
}
