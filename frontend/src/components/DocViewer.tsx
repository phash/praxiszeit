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
              ? <ChevronDown size={16} className="text-gray-500 shrink-0" />
              : <ChevronRight size={16} className="text-gray-500 shrink-0" />}
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
              <li>⚠️ Über 10 Stunden: Warnung beim Live-Ausstempeln</li>
              <li>🚫 Über 10 Stunden bei manueller Eingabe / Antrag: gesperrt</li>
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
            <p className="text-sm font-medium text-gray-700 mb-1">Optionen je Mitarbeiter</p>
            <ul className="text-sm text-gray-600 list-disc list-inside space-y-0.5">
              <li><strong>Stundenzählung aus</strong> – Mitarbeitende ohne Soll/Ist-Erfassung; Urlaub/Krank zählen trotzdem tagebasiert.</li>
              <li><strong>Nimmt an Betriebsferien teil</strong> (Standard an) – rollenunabhängig; für reine Verwaltungs-Accounts abwählbar.</li>
              <li><strong>Erster/Letzter Arbeitstag</strong> – Soll wird nur innerhalb dieses Zeitraums berechnet.</li>
            </ul>
            <p className="text-sm text-gray-500 mt-1">Die Übersicht zeigt je MA Urlaubskonto und Überstundensaldo (JTD).</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Stundenänderung</p>
            <p className="text-sm text-gray-600">Benutzer bearbeiten → neue Wochenstunden + Wirkungsdatum → historische Salden bleiben korrekt.</p>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-sm p-2">
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
        <p className="text-sm text-gray-500 mt-1">Alle MA mit „Nimmt an Betriebsferien teil" (Standard) erhalten automatisch Einträge – rollenunabhängig, keine Urlaubstage. Nachträglich Berechtigte: Option setzen – Einträge werden automatisch für laufende und künftige Betriebsferien nachgetragen.</p>
        <p className="text-sm text-gray-500 mt-1">Sind die (urlaubszählenden) Betriebsferien länger als das Resturlaub-Budget, lässt sich unter <strong>Einstellungen → „Betriebsferien &amp; Urlaub"</strong> die Option „Überzählige Betriebsferien als Überstundenabbau" aktivieren: erst Urlaub, dann Überstunden (Konto darf ins Minus) – statt Minus-Urlaub. Global, Standard aus.</p>
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
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§3</td><td className="px-3 py-2 border border-gray-200 text-gray-600">8h-Warnung; &gt;10h: Warnung beim Live-Ausstempeln, harte Sperre bei manueller Eingabe/Antrag</td></tr>
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
        <p><strong>Auf dem Smartphone:</strong> Der Link <strong>„Auf dem Smartphone öffnen (QR-Code)"</strong> auf der Login-Seite zeigt einen QR-Code mit der Server-Adresse. Mit der Handy-Kamera scannen → dieselbe Login-Seite öffnet sich am Handy (gleiches Netzwerk nötig; meldet nicht automatisch an — normal mit Benutzername/Passwort einloggen). Über „Zum Startbildschirm hinzufügen" lässt sich PraxisZeit als App installieren.</p>
      </div>
    ),
  },
  {
    title: '2. Dashboard & Saldo verstehen',
    content: (
      <div className="space-y-2">
        <p>Das Dashboard zeigt Ihren <strong>Tagessaldo</strong> (heute: Ist vs. Tagessoll), den <strong>Monatssaldo</strong> (Ist – Soll in H:MM), den kumulierten Jahressaldo und das Urlaubskonto.</p>
        <p>Im <strong>laufenden Monat</strong> zählt das Soll nur bis zum <strong>letzten abgeschlossenen Arbeitstag</strong> – Sie starten den Monat also nicht mit einem dicken Minus; der heutige Tag zählt mit, sobald Sie <strong>ausgestempelt</strong> haben. Abgeschlossene Monate entsprechen dem vollen Monat.</p>
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
        <p className="text-amber-700 font-medium">ArbZG: Pflichtpause ab 6h (30 Min.), ab 9h (45 Min.). Über 10h Nettoarbeitszeit: beim Live-Ausstempeln Warnung, bei manueller Eingabe/Antrag harte Sperre.</p>
      </div>
    ),
  },
  {
    title: '4. Pause beim Ausstempeln',
    content: (
      <div className="space-y-2">
        <p>Beim <strong>Ausstempeln</strong> erscheint das Feld <strong>Pause (Min.)</strong>. Tragen Sie ein, wie viele Minuten Pause Sie heute gemacht haben (z. B. <code>30</code>).</p>
        <p>Reicht die Pause für die geleistete Arbeitszeit nicht aus (mind. 30 Min. ab 6h, 45 Min. ab 9h, §4 ArbZG), erscheint ein gelber Hinweis. Sie haben zwei Möglichkeiten:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li><strong>Pause nachtragen</strong> – falls Sie tatsächlich länger Pause gemacht haben, Minuten korrigieren.</li>
          <li><strong>Begründung angeben</strong> – falls keine Pause möglich war, kurz erläutern (z. B. „Notfall, keine Vertretung"). Diese <strong>dokumentierte Ausnahme</strong> wird gespeichert.</li>
        </ul>
        <p>Erst nach Pause-Eingabe <strong>oder</strong> Begründung ist das Ausstempeln abgeschlossen. Mit <strong>Abbrechen</strong> schließen Sie das Feld, ohne auszustempeln – die Uhr läuft weiter.</p>
      </div>
    ),
  },
  {
    title: '5. Soll-Arbeitszeiten & Anrechnung',
    content: (
      <div className="space-y-2">
        <p>Hat Ihre Praxis für einen Wochentag eine <strong>Soll-Arbeitszeit</strong> hinterlegt, wird Zeit deutlich vor dem Soll-Beginn bzw. nach dem Soll-Ende <strong>nicht angerechnet</strong>. Ein kleiner Puffer (Standard 15 Min.) ist erlaubt.</p>
        <p>Stempeln Sie z. B. zu früh ein, sehen Sie den Hinweis: <em>„Du hast vor deinem Soll-Beginn eingestempelt – die Anrechnung beginnt ab dem frühestmöglichen Zeitpunkt."</em> In der Eintragsliste steht dann z. B. <em>„gestempelt 07:30 · angerechnet ab 07:45"</em>.</p>
        <p className="text-gray-700">Ihre <strong>echte Stempelzeit geht nicht verloren</strong> (gesetzlich vorgeschrieben, §16 ArbZG) – fürs Stundenkonto zählt nur die angerechnete Zeit.</p>
      </div>
    ),
  },
  {
    title: '6. Korrekturanträge stellen & verwalten',
    content: (
      <div className="space-y-2">
        <p>Wenn ein gesperrter Eintrag korrigiert werden muss: <strong>Zeiterfassung → Tab „Einträge"</strong> → in der Aktionsspalte auf <strong>Änderungsantrag</strong> klicken → korrekte Zeiten + Begründung eingeben → Antrag stellen.</p>
        <p>Den Status aller Anträge sehen Sie unter <strong>Zeiterfassung → Tab „Anträge"</strong>. Filter: Alle / Offen / Genehmigt / Abgelehnt. Offene Anträge können mit <strong>Zurückziehen</strong> storniert werden.</p>
        <p className="text-gray-700"><strong>Pflicht-Pause war nicht möglich?</strong> Erfüllen Ihre korrigierten Zeiten die Pausenregel nicht, wird der Antrag nicht abgelehnt – es erscheint das Feld <strong>„Pflicht-Pause war nicht möglich – Begründung"</strong>. Kurz erläutern und mit <strong>Mit dokumentierter Ausnahme senden</strong> abschicken; die Abweichung wird dokumentiert und dem Admin vorgelegt.</p>
      </div>
    ),
  },
  {
    title: '7. Abwesenheiten eintragen',
    content: (
      <div className="space-y-2">
        <p>Navigieren Sie zu <strong>Abwesenheiten</strong> und klicken Sie auf <strong>+ Abwesenheit eintragen</strong>. Wählen Sie den Typ (Urlaub, Krank, Fortbildung, Sonstiges) und das Datum. Hat Ihre Praxis zusätzliche Gründe eingerichtet (z. B. „Schule"), erscheinen diese in der Typ-Auswahl unter <strong>„Eigene Gründe"</strong>.</p>
        <p>Für Zeiträume aktivieren Sie die Checkbox <strong>„Zeitraum"</strong> und geben ein Enddatum an. Wochenenden und Feiertage werden automatisch ausgeschlossen.</p>
        <p>Hat Ihre Praxis <strong>Heiligabend (24.12.)</strong> oder <strong>Silvester (31.12.)</strong> als arbeitsfrei oder halben Tag eingestellt, sind diese Tage im Kalender entsprechend markiert: grau „Heiligabend (frei)" bzw. amber „Silvester (½ Tag)" – ähnlich einem Feiertag.</p>
        <p>Wenn Urlaubsgenehmigungspflicht aktiv ist, wechselt die App nach dem Absenden automatisch zum Tab <strong>„Meine Anträge"</strong>.</p>
        <p className="text-gray-700"><strong>So wird Urlaub berechnet:</strong> nach dem Tagesprinzip (§3 BUrlG) – <strong>ein freier Arbeitstag = genau 1 Urlaubstag</strong>, egal wie viele Stunden Sie an dem Tag arbeiten. Eine freie Woche kostet so viele Tage, wie Sie Arbeitstage haben. Ihr Urlaubskonto zeigt die verbleibenden Tage.</p>
        <p className="text-gray-700"><strong>Betriebsferien (Praxisschließung):</strong> Bei Betriebsferien trägt die App Ihre Abwesenheiten an Ihren Arbeitstagen <strong>automatisch</strong> ein – Sie müssen nichts selbst buchen. Je nach Einstellung Ihrer Praxis zählen die Tage als <strong>bezahlte Freistellung</strong> (kein Urlaubsabzug) oder als <strong>Urlaub</strong>. Reicht Ihr Urlaub für die Schließung nicht, wird – wenn Ihre Praxis das so eingestellt hat – zuerst Ihr Urlaub verbraucht und der Rest als <strong>Überstundenabbau</strong> gebucht (Ihr Überstundenkonto sinkt und kann ins Minus gehen), sodass kein Minus-Urlaub entsteht. Die genaue Verrechnung legt die Praxisleitung fest.</p>
      </div>
    ),
  },
  {
    title: '8. So werden Ihre Stunden & Ihr Urlaub berechnet',
    content: (
      <div className="space-y-2">
        <p><strong>Tagessoll</strong> = Wochenstunden ÷ Arbeitstage pro Woche (z. B. 40 h auf 5 Tage = 8 h/Tag; 24 h auf 3 Tage = 8 h/Tag). Individuelle Tagesstunden überschreiben das. Wochenende und Feiertag = 0.</p>
        <p><strong>Ist</strong> = (Ende − Beginn) − Pause je Eintrag. <strong>Krankheit</strong> und <strong>Fortbildung</strong> werden so angerechnet, als hätten Sie gearbeitet, und zählen zu Ihrem Ist.</p>
        <p><strong>Saldo</strong> = Ist − Soll (grün = Mehrarbeit, rot = Minusstunden). Das <strong>Überstundenkonto</strong> summiert die Salden seit Jahresbeginn inkl. Vorjahresübertrag.</p>
        <p><strong>Überstundenausgleich:</strong> Das Soll bleibt, der Tag zählt als 0 Stunden → Ihr Überstundenkonto sinkt.</p>
        <p className="text-gray-700"><strong>Urlaub (Tagesprinzip, §3 BUrlG):</strong> 1 freier Arbeitstag = 1 Urlaubstag, egal wie lang der Tag ist (Halbtag = 0,5).</p>
      </div>
    ),
  },
  {
    title: '9. Wenn für Sie keine Stunden gezählt werden',
    content: (
      <div className="space-y-2">
        <p>Für manche Mitarbeitende führt die Praxis bewusst <strong>keine Stundenzählung</strong>. Dann fehlen die Kacheln <strong>Tagessaldo</strong>, <strong>Monatssaldo</strong> und <strong>Überstundenkonto</strong> sowie der Stempel-Button – das ist so eingestellt und kein Fehler.</p>
        <p>Ihr <strong>Urlaubskonto</strong> wird trotzdem geführt: Urlaub und Krankheit zählen weiterhin <strong>tagebasiert</strong> (1 freier Arbeitstag = 1 Urlaubstag).</p>
      </div>
    ),
  },
  {
    title: '10. Profil & Passwort',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Profil</strong> sehen Sie Ihre persönlichen Daten. Über <strong>Passwort ändern → Ändern</strong> setzen Sie ein neues Passwort (mind. 10 Zeichen, Groß-/Kleinbuchstabe, Ziffer).</p>
        <p><strong>Zwei-Faktor-Authentifizierung (2FA):</strong> Schützen Sie Ihr Konto zusätzlich mit einem Einmal-Code aus einer Authenticator-App (z. B. Google Authenticator, Authy). <strong>Aktivieren:</strong> Karte „Zwei-Faktor-Authentifizierung" → „2FA aktivieren" → QR-Code scannen (oder Schlüssel manuell eintragen) → 6-stelligen Code bestätigen. <strong>Login:</strong> nach Benutzername + Passwort wird der 6-stellige Code abgefragt. <strong>Deaktivieren:</strong> „2FA deaktivieren" → aktuelles Passwort bestätigen. Bei verlorenem Zugang zur App hilft Ihr Administrator.</p>
        <p>Persönliche Daten wie Name und Wochenstunden können nur vom Administrator geändert werden. Unter <strong>Weitere Einstellungen</strong> finden Sie optionale Darstellungsoptionen.</p>
      </div>
    ),
  },
  {
    title: '11. Schichtplan einsehen',
    content: (
      <div className="space-y-2">
        <p>Wenn Ihre Praxis die <strong>Schichtplanung</strong> nutzt, finden Sie links den Menüpunkt <strong>Schichtplan</strong>. Dort sehen Sie die aktiven Wochenpläne als Übersicht: welcher Arbeitsplatz (z. B. Tresen, Labor) zu welcher Zeit besetzt ist und wer eingeteilt ist.</p>
        <p>Auf dem <strong>Dashboard</strong> zeigt die Karte <strong>„Deine Einteilung heute"</strong> Ihre heutigen Einsätze mit Arbeitsplatz und Uhrzeit.</p>
        <p>Unter <strong>Profil → „Meine Einweisungen"</strong> sehen Sie, für welche Arbeitsplätze Sie eingewiesen sind. Diese pflegt Ihr Administrator.</p>
        <p>Die Schichtplanung ist ein reines Planungswerkzeug – sie verändert <strong>nicht</strong> Ihre erfassten Arbeitszeiten, Ihren Urlaub oder Ihr Überstundenkonto. Die Einteilung legt Ihr Administrator fest; bei Fragen wenden Sie sich an ihn.</p>
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
        <p>Mit dem Umschalter <strong>„Monat / Woche"</strong> oben wechseln Sie zwischen Monats- und <strong>Wochenansicht</strong>. In der Wochenansicht steht statt „Juni 2026" die Kalenderwoche (z. B. <em>„22.–28.06.2026 (KW 26)"</em>); die Pfeile blättern wochenweise. Gleiche Spalten wie im Monat – ideal für eine schnelle Plausibilitätsübersicht. Ihre Auswahl bleibt pro Browser/Gerät gespeichert.</p>
        <p>Das Dropdown <strong>„Soll: bis heute / Monatsende"</strong> schaltet die Soll-Basis um: <strong>bis heute</strong> (Standard) zählt das Soll des laufenden Monats nur bis zum letzten abgeschlossenen Arbeitstag (kein Monatsanfangs-Minus), <strong>Monatsende</strong> den vollen Monat. Für abgeschlossene Monate identisch; die §16-Datei-Exporte bleiben voll-Monat. In der Wochenansicht heißt die zweite Option entsprechend <strong>„volle Woche"</strong>.</p>
        <p>Klicken Sie auf den Pfeil am Ende einer Zeile für die Detailansicht. Nutzen Sie die Suche zum Filtern nach Name.</p>
      </div>
    ),
  },
  {
    title: '2. Benutzerverwaltung',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Benutzerverwaltung</strong> legen Sie Mitarbeiter an (<strong>Neuer Mitarbeiter:in</strong>), bearbeiten und deaktivieren sie. Niemals löschen – Status auf „Inaktiv" setzen (Aufbewahrungspflicht §16 ArbZG, 2 Jahre).</p>
        <p>Für Teilzeit-Anpassungen: Benutzer öffnen → neue Wochenstunden + <strong>Wirkungsdatum</strong> eintragen. Historische Salden bleiben korrekt. Checkboxen: „ArbZG-Prüfungen aussetzen" für §18, „Nachtarbeitnehmer" für §6, „<strong>Nimmt an Betriebsferien teil</strong>" (Standard an, rollenunabhängig – für reine Verwaltungs-Accounts abwählbar), „Stundenzählung" aus für MA ohne Zeiterfassung (Urlaub/Krank zählen trotzdem tagebasiert).</p>
        <p><strong>Erster/Letzter Arbeitstag</strong> begrenzen die Soll-Berechnung: vor dem Eintritt bzw. nach dem Austritt entsteht kein Stundensoll. Die Übersicht zeigt je MA Urlaubskonto <strong>und</strong> Überstundensaldo (Jahr bis heute; „—" ohne Stundenzählung).</p>
        <p className="text-amber-700">⚠️ Bei <strong>unterjährigem Eintritt</strong> (nicht seit 1. Januar im System) den „Ersten Arbeitstag" unbedingt setzen – sonst zählt das Soll auch Tage vor dem Eintritt und es entstehen Phantom-Minusstunden.</p>
        <p><strong>Soll-Arbeitszeiten (Arbeitszeit-Fenster):</strong> Im Benutzerformular können Sie pro MA und Wochentag Soll-Beginn und Soll-Ende hinterlegen. Zeiten außerhalb des Fensters (abzüglich Puffer) werden nicht angerechnet; der gestempelte Rohwert bleibt gespeichert (§16). Der systemweite Puffer (Standard 15 Min.) ist unter <strong>Einstellungen → Arbeitszeit-Fenster Puffer</strong> konfigurierbar. Opt-in: ohne Soll-Zeiten kein Eingriff. MA mit deaktivierter Stundenzählung sind ausgenommen.</p>
        <p><strong>Kalenderfarbe:</strong> Im Benutzerformular können Sie die Kalenderfarbe aus einer Palette für jede:n Mitarbeiter:in vorgeben (Badge-Ring im Teamkalender); der/die Mitarbeiter:in kann sie auch selbst im Profil ändern.</p>
        <p><strong>Monatsjournal:</strong> Das Buch-Symbol in der Aktionsspalte öffnet das Monatsjournal des/der Mitarbeitenden. Die Überschrift trägt den Namen – <strong>„Monatsjournal: Vorname Nachname"</strong> –, damit beim Wechsel zwischen Personen sofort klar ist, wessen Journal angezeigt wird.</p>
        <p><strong>Login als … (Ansicht als Mitarbeiter:in):</strong> Das Anmelde-Symbol in der Aktionsspalte (nur bei aktiven Mitarbeitenden) öffnet die App aus deren Sicht – nützlich, um das Mitarbeiter-Dashboard zu prüfen oder ein Problem nachzustellen. Die Ansicht ist <strong>ausschließlich lesend</strong>: Stempeln, Anträge und alle Änderungen sind gesperrt. Ein Hinweisbanner oben zeigt dauerhaft „Sie sehen PraxisZeit als … – nur Lesen"; über <strong>„Zurück zu Admin"</strong> kehren Sie zu Ihrem Konto zurück. Jede solche Sitzung wird protokolliert (wer, wen, wann – DSGVO-Rechenschaftspflicht).</p>
        <p><strong>DSGVO: Anonymisierung &amp; endgültige Löschung (Art. 17):</strong> Ablauf <strong>Deaktivieren → 14-Tage-Sperrfrist → Anonymisieren → endgültig löschen</strong>. <strong>Anonymisieren</strong> (nach der Sperrfrist) entfernt persönliche Daten (Name, E-Mail, Lichtbild, 2FA); die <strong>Zeiteinträge bleiben</strong> erhalten (§16 ArbZG), Abwesenheiten werden gelöscht. <strong>Endgültig löschen (Purge)</strong> löscht den Benutzer samt aller Daten unwiderruflich – erst möglich, wenn die jüngste aufbewahrungspflichtige Aufzeichnung <strong>mindestens 730 Tage</strong> alt ist (sonst blockiert das System). Anonymisierte Nutzer können also erst nach Ablauf der 730 Tage endgültig gelöscht werden; beide Vorgänge werden im Änderungsprotokoll vermerkt.</p>
      </div>
    ),
  },
  {
    title: '3. Berichte & Exporte',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> stehen drei Export-Typen bereit: <strong>Monatsreport</strong> (Gehaltsabrechnung), <strong>Jahresreport Classic</strong> (12 Monate kompakt) und <strong>Jahresreport Detailliert</strong> (365 Tage, für Steuerberater). Jeder Report ist als <strong>Excel (.xlsx)</strong> und <strong>ODS (.ods)</strong> verfügbar; den Monatsreport gibt es zusätzlich als <strong>PDF (.pdf)</strong>.</p>
        <p>Mit der Checkbox <strong>„Krankheitsdaten einschließen" (Art. 9 DSGVO)</strong> nehmen Sie Krankheitsstunden/-tage mit in den Export auf. Krankheitsdaten sind besondere Kategorien personenbezogener Daten; jeder Export mit dieser Option wird im Änderungsprotokoll vermerkt.</p>
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
        <p><strong>Urlaubsanträge:</strong> Toggle „Genehmigungspflicht" aktiviert den Workflow. Anträge erscheinen als „Offen" → Genehmigen (grün) oder Ablehnen (rot, optional Grund). <strong>Stornieren:</strong> Im Filter „Genehmigt" lässt sich ein genehmigter Antrag über <strong>„Urlaub stornieren"</strong> rückgängig machen, solange der Zeitraum noch nicht begonnen hat – die erzeugten Abwesenheiten werden dabei <strong>automatisch entfernt</strong>, der Antrag wird auf „Zurückgezogen" gesetzt.</p>
        <p><strong>Betriebsferien:</strong> Abwesenheiten → Tab „Betriebsferien" → Neue Betriebsferien. Alle aktiven Mitarbeiter mit der Option „Nimmt an Betriebsferien teil" (Standard, rollenunabhängig) erhalten automatisch Einträge an ihren <strong>Arbeitstagen</strong>. <strong>Nicht gebucht</strong> wird an Wochenenden, Feiertagen, freien Wochentagen (Teilzeit), „Frei"-Sondertagen (24./31.12.), außerhalb des Beschäftigungszeitraums (noch nicht eingetreten / bereits ausgetreten) sowie an Tagen mit bereits vorhandener Abwesenheit. Nachträglich Berechtigte: Option setzen – die Einträge werden automatisch für laufende und künftige Betriebsferien nachgetragen. Beim Löschen werden alle Einträge entfernt.</p>
        <p><strong>Verrechnung</strong> (beim Anlegen wählbar): <strong>„Als Urlaub werten"</strong> (Standard) zieht je Schließtag 1 Urlaubstag vom Konto ab; <strong>„Bezahlte Freistellung"</strong> ist saldoneutral – kein Urlaubsabzug, keine Auswirkung aufs Überstundenkonto (wie ein Feiertag).</p>
        <p className="text-gray-700"><strong>Betriebsferien länger als der Jahresurlaub:</strong> Sind als Urlaub zählende Betriebsferien länger als das Resturlaub-Budget, entstehen standardmäßig <strong>Minus-Urlaubstage</strong>. Unter <strong>Einstellungen → „Betriebsferien &amp; Urlaub"</strong> aktivieren Sie optional <strong>„Überzählige Betriebsferien als Überstundenabbau"</strong>: dann wird zuerst der Urlaub aufgezehrt und die überzähligen Tage werden als Überstundenausgleich gebucht (Konto darf ins Minus) – statt Minus-Urlaub. Global, Standard <strong>aus</strong>. Die Zuteilung erfolgt <strong>chronologisch nach Datum</strong> (frühere Schließung zuerst, Überstunden-Tage auf die letzte des Jahres), unabhängig von der Eingabereihenfolge; privater Urlaub wird zuerst verbraucht. Wirkt beim Anlegen/erneuten Speichern – für bestehende Betriebsferien einmal öffnen und neu speichern.</p>
        <p className="text-gray-700"><strong>Urlaubsberechnung (Tagesprinzip, §3 BUrlG):</strong> Urlaub wird nach Arbeitstagen geführt – ein freier Arbeitstag = <strong>1 Urlaubstag</strong>, unabhängig von Tagesstunden und Wochentag (auch bei individuellen Tagesstunden). Jahresanspruch anteilig: <code>30 × Arbeitstage ÷ 5</code> (überschreibbar beim Anlegen). Verbrauch wird tagebasiert gezählt, intern gespeicherte Stunden dienen nur der Soll-/Ist-Berechnung.</p>
      </div>
    ),
  },
  {
    title: '6. Sondertage 24./31.12.',
    content: (
      <div className="space-y-2">
        <p>Heiligabend (24.12.) und Silvester (31.12.) sind keine gesetzlichen Feiertage. Unter <strong>Einstellungen → „Sondertage (24./31.12.)"</strong> legen Sie für <strong>jeden</strong> der beiden Tage getrennt fest, wie er behandelt wird:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li><strong>Normaler Arbeitstag</strong> – kein Sonderverhalten.</li>
          <li><strong>Frei</strong> – arbeitsfrei, kein Stundensoll. Im Kalender grau, nicht buchbar.</li>
          <li><strong>Halbtag</strong> – halbes Tagessoll. Im Kalender amber/gelb.</li>
        </ul>
        <p>Die Einstellung wirkt direkt auf Soll-Berechnung und Kalenderdarstellung bei allen Mitarbeitenden.</p>
      </div>
    ),
  },
  {
    title: '7. Pflicht-Pause-Ausnahme (§4 ArbZG)',
    content: (
      <div className="space-y-2">
        <p>Konnte eine vorgeschriebene Pause (§4 ArbZG: 30 Min. ab 6h, 45 Min. ab 9h) nicht eingelegt werden, kann ein Eintrag mit einer <strong>dokumentierten Pflicht-Begründung</strong> erfasst werden, statt blockiert zu werden. Die Begründung landet im Änderungsprotokoll (Quelle „break_waiver").</p>
        <p>Den Schalter <strong>„Genehmigung erforderlich"</strong> stellen Sie unter <strong>Einstellungen → „Pflicht-Pause-Ausnahme"</strong> ein:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li><strong>Aus</strong> – die Ausnahme wird sofort wirksam.</li>
          <li><strong>Ein</strong> – der Eintrag wird erst nach Admin-Genehmigung wirksam.</li>
        </ul>
        <p className="text-gray-700"><strong>4-Augen-Prinzip:</strong> Ist die Genehmigungspflicht aktiv, darf ein Admin seine <strong>eigene</strong> Pflicht-Pause-Ausnahme nicht selbst genehmigen – sie muss von einer zweiten Person geprüft werden.</p>
      </div>
    ),
  },
  {
    title: '8. ArbZG-Berichte & Compliance',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> (nach unten scrollen) finden Sie: <strong>§5 Ruhezeitverstöße</strong> (&lt;11h zwischen Arbeitstagen), <strong>§6 Nachtarbeit</strong> (≥48 Nachtarbeitstage/Jahr), <strong>§11 Sonntagsarbeit</strong> (max. 37/Jahr) und <strong>§11 Ersatzruhetag</strong> (Fristen überwachen). Erfasste Pflicht-Pause-Ausnahmen samt Begründung sind ebenfalls einsehbar.</p>
        <p>Das System prüft bei jeder Eingabe automatisch §3, §4 (Pausenpflicht), §6 (8h für Nachtarbeitnehmer), §9/10 (Sonntagsarbeit), §14 (48h-Wochenwarnung).</p>
        <p className="text-amber-700"><strong>§3 Tageshöchstgrenze (10h):</strong> Beim <strong>Live-Ausstempeln</strong> wird ein Tag über 10h nicht blockiert (die Zeit ist bereits geleistet und §16-pflichtig zu dokumentieren) – es erscheint eine deutliche Warnung. Bei <strong>manueller Eingabe oder Antrag</strong> bleibt die 10h-Grenze eine <strong>harte Sperre</strong>.</p>
      </div>
    ),
  },
  {
    title: '9. Audit-Log & Fehler-Monitoring',
    content: (
      <div className="space-y-2">
        <p>Das <strong>Änderungsprotokoll</strong> zeichnet alle Aktionen unveränderlich auf (Login, Zeiteinträge, Abwesenheiten, Benutzerverwaltung, Korrekturanträge). Dient als Nachweis gem. §16 ArbZG bei Betriebsprüfungen.</p>
        <p>Das <strong>Fehler-Monitoring</strong> zeigt Backend-Fehler mit Häufigkeit und Kontext. Wiederkehrende Fehler als GitHub Issue melden (Button in der Detailansicht).</p>
      </div>
    ),
  },
  {
    title: '10. Berechnungsgrundlagen (Soll, Ist, Überstunden, Urlaub)',
    content: (
      <div className="space-y-2">
        <p><strong>Tagessoll</strong> = Wochenstunden ÷ Arbeitstage pro Woche – der Divisor ist <strong>nicht</strong> fix 5 (24 h auf 3 Tage = 8 h/Tag). Individuelle Tagesstunden je Wochentag sind möglich; Wochenende/Feiertag/außerhalb des Beschäftigungszeitraums = 0.</p>
        <p><strong>Ist</strong> = (Ende − Beginn) − Pause, nie negativ. Ein Soll-Arbeitszeit-Fenster kürzt die Anrechnung auf das Fenster (± Puffer); der Rohstempel bleibt erhalten (§16 ArbZG). Krank und Fortbildung zählen als Ist (§3 EntgFG).</p>
        <p><strong>Abwesenheiten:</strong> Urlaub, bezahlte Freistellung &amp; Sonstige senken das Soll; Krank &amp; Fortbildung füllen das Ist auf (saldo-neutral); der Überstundenausgleich lässt das Soll stehen (Ist 0 h) und baut Überstunden ab.</p>
        <p><strong>Überstundenkonto</strong> = fortlaufende Summe der Monatssalden ab dem Jahresübertrag. Die Spalte „Überstunden (JTD)" zeigt 1. Januar bis heute zzgl. Carryover.</p>
        <p><strong>Urlaub (Tagesprinzip §3 BUrlG):</strong> 1 freier Arbeitstag = 1 Tag (Halbtag 0,5), unabhängig von der Stundenzahl. Anspruch <code>30 × Arbeitstage ÷ 5</code>, anteilig bei unterjährigem Eintritt/Austritt, zzgl. Resturlaub-Vortrag (Carryover). Nur Urlaub belastet das Budget; ein als „Frei + zählt als Urlaub" konfigurierter Sondertag (24./31.12.) kostet ebenfalls 1 Tag. Vor Eintritt/nach Austritt: kein Anspruch und kein Verbrauch.</p>
        <p className="text-gray-500">Vollständige Formeln und durchgerechnete Beispiele: <code>docs/BERECHNUNGEN.md</code> bzw. Admin-Handbuch-Anhang „Berechnungsgrundlagen".</p>
      </div>
    ),
  },
  {
    title: '11. Datensicherung (Backup & Restore)',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Datensicherung</strong> erstellen Sie jederzeit eine vollständige, komprimierte Sicherung der Datenbank (<strong>Jetzt sichern</strong>) oder aktivieren eine <strong>tägliche automatische Sicherung</strong> mit Aufbewahrungsdauer und optionalem Speicherort.</p>
        <p>Vorhandene Sicherungen lassen sich in der Liste <strong>herunterladen</strong> (für eine externe Kopie) oder löschen. Format ist Plain-SQL + gzip (<code>praxiszeit_&lt;Zeitstempel&gt;.sql.gz</code>), mit <code>--clean --if-exists</code> idempotent wiederherstellbar.</p>
        <p><strong>§16 ArbZG:</strong> Zeitaufzeichnungen sind mind. 2 Jahre aufzubewahren — Aufbewahrungsdauer entsprechend setzen und eine Kopie <strong>außerhalb</strong> des Servers vorhalten. Vor jedem Update zusätzlich sichern.</p>
        <p className="text-gray-500">Native installiert läuft die <em>geplante</em> Sicherung über den OS-Timer; der <em>manuelle</em> Trigger und die Liste funktionieren überall. Wiederherstellung &amp; Details: <code>docs/BACKUP.md</code>.</p>
      </div>
    ),
  },
  {
    title: '12. Schichtplanung (optional)',
    content: (
      <div className="space-y-2">
        <p>Die <strong>Schichtplanung</strong> ist <strong>standardmäßig deaktiviert</strong>. Sie aktivieren sie unter <strong>Einstellungen → Schichtplanung</strong>. Erst danach erscheinen die Menüpunkte <strong>Schichtplanung</strong> (Admin) und <strong>Schichtplan</strong> (alle) und das Dashboard-Widget.</p>
        <p>Unter <strong>Schichtplanung → Stammdaten</strong> legen Sie <strong>Standorte</strong> (optional) und <strong>Arbeitsplätze</strong> (z. B. Tresen, Labor, Springer – mit Farbe) an. Unter <strong>Schichtpläne</strong> erstellen Sie beliebig viele benannte <strong>Wochenpläne</strong> (z. B. „Normalzustand", „Azubis Schulferien").</p>
        <p>Im Wochen-Editor verteilen Sie <strong>Zeitslots</strong> per Drag &amp; Drop oder Klick über die Woche und ziehen <strong>Mitarbeitende</strong> aus der Liste auf einen Slot. Optional setzen Sie pro Slot eine <strong>Mindestbesetzung</strong>; unterbesetzte Slots werden markiert (weiche Warnung, blockiert nicht).</p>
        <p>Im Reiter <strong>Einweisungen</strong> legen Sie per Matrix (Mitarbeiter × Arbeitsplätze) fest, wer für welchen Arbeitsplatz <strong>eingewiesen</strong> ist. Weisen Sie eine nicht eingewiesene Person zu, erscheint die weiche Warnung <strong>„nicht eingewiesen"</strong> (blockiert nicht). Mitarbeitende sehen ihre Einweisungen in ihrem Profil.</p>
        <p>Über <strong>Bearbeiten</strong> setzen Sie pro Plan optional ein <strong>Aktiv-Datums-Fenster</strong> („von/bis") — der Plan wird dann im Zeitraum automatisch aktiv; die <strong>Jahresübersicht</strong> zeigt das als Zeitstrahl. Mit <strong>Automatisch füllen</strong> verteilt der Generator eingewiesene, an dem Tag verfügbare Mitarbeitende greedy auf die Slots (ausgewogen nach Auslastung/Überstunden) — als Entwurf zum Review; der Plan wird dabei nicht aktiviert.</p>
        <p>Der <strong>Woche/Tag</strong>-Umschalter zeigt wahlweise die ganze Woche oder einen einzelnen Wochentag in voller Breite. Beim Bearbeiten eines Slots kopiert <strong>„Auf Wochentage kopieren"</strong> denselben Slot (inkl. Zuweisungen) auf weitere Tage — praktisch für wiederkehrende Schichten. Mit <strong>„Duplizieren"</strong> kopieren Sie einen kompletten Plan (inkl. Slots und Zuweisungen) als <strong>inaktiven Entwurf</strong> — ideal, um Varianten aus einem Bestandsplan abzuleiten.</p>
        <p><strong>Geplante Wochentage:</strong> Unter <strong>Einstellungen → Schichtplanung</strong> wählen Sie, welche Wochentage der Planer anzeigt und plant (Standard <strong>Mo–Fr</strong>; Sa/So oder ein Schließtag einzeln zu-/abschaltbar, mind. ein Tag aktiv). Ein abgeschalteter Tag verschwindet aus der Wochenansicht, nimmt keine neuen Slots auf und wird von der Auto-Generierung übersprungen. Bereits angelegte Slots bleiben erhalten und kehren beim Reaktivieren des Tages zurück.</p>
        <p>In der Mitarbeiterliste des Editors steht unter jedem Namen die <strong>Auslastung</strong> – zugewiesene Schichtstunden zur Wochenarbeitszeit, z. B. <em>„15,25 / 17 h"</em>: grün bei ±30 Min. zur Vertragszeit, gelb bei ±1 Std., sonst rot. Das erleichtert eine ausgewogene Einteilung.</p>
        <p>Mit <strong>Aktiv schalten</strong> machen Sie einen Plan für alle sichtbar; <strong>mehrere Pläne können gleichzeitig aktiv</strong> sein. Mitarbeitende sehen ihre heutige Einteilung im Dashboard.</p>
        <p className="text-gray-500">Die Schichtplanung ist ein reines Planungswerkzeug und berührt <strong>nicht</strong> Zeiterfassung, Soll/Ist-Stunden, ArbZG-Prüfungen, Urlaub oder Überstunden. Details: <code>docs/SCHICHTPLANUNG.md</code>.</p>
      </div>
    ),
  },
];

// ── Schnellstart (Admin) ─────────────────────────────────────────────────────
// In-App-Version von docs/handbuch/SCHNELLSTART.md — bei Änderungen BEIDES pflegen.

export function SchnellstartAdmin() {
  return (
    <div className="space-y-6">
      <p className="text-sm text-gray-600">
        In wenigen Minuten von der Installation zur laufenden Zeiterfassung. Details im <strong>Admin-Handbuch</strong>.
      </p>

      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-2">1. Praxis konfigurieren</h3>
        <p className="text-sm text-gray-600">Unter <strong>Einstellungen</strong>: Bundesland (Feiertage), Urlaubsgenehmigung (an/aus), Sondertage 24./31.12., Onboarding-Tour (Standard an).</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Eigene Abwesenheitsgründe</strong> (z. B. „Schule" für Azubis) legen Sie unter <strong>Einstellungen → „Eigene Abwesenheitsgründe"</strong> an: Bezeichnung + Farbe + Basis-Verhalten (<em>zählt als gearbeitet</em> / <em>bezahlt frei</em> / <em>Überstundenabbau</em>; nach dem Anlegen fix). Sie erscheinen beim Buchen unter „Eigene Gründe"; im Team-Kalender werden sie für Kolleg:innen aus Datenschutzgründen als „abwesend" maskiert.</p>
      </section>

      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-2">2. Mitarbeiter anlegen</h3>
        <p className="text-sm text-gray-600 mb-1"><strong>Benutzerverwaltung → „Neue:r Mitarbeiter:in"</strong>: Benutzername + Startpasswort, Name, Wochenstunden bzw. Tagesplan, Urlaubsanspruch → Speichern.</p>
        <ul className="text-sm text-gray-500 list-disc list-inside space-y-0.5">
          <li>Leitende Angestellte: <em>„Keine Stundenzählung"</em> – Urlaub/Krank trotzdem tagebasiert.</li>
          <li>Ein-/Austritt: <em>Erster/Letzter Arbeitstag</em> setzen.</li>
          <li>Optional: Soll-Arbeitszeit-Fenster (Soll-Beginn/-Ende je Wochentag).</li>
        </ul>
      </section>

      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-2">3. Betrieb</h3>
        <p className="text-sm text-gray-600">Mitarbeiter stempeln/erfassen; das <strong>Admin-Dashboard</strong> zeigt Salden + fehlende Buchungen. Korrektur-/Urlaubsanträge prüfen, Berichte exportieren.</p>
      </section>

      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-2">4. Pflichten (§16 ArbZG)</h3>
        <p className="text-sm text-gray-600">Zeitaufzeichnungen <strong>2 Jahre aufbewahren</strong> → Backups sichern. Über 10 h netto gesperrt, ab 8 h Warnung; Pflichtpausen ab 6 h / 9 h.</p>
      </section>
    </div>
  );
}

// ── DocViewerContent ─────────────────────────────────────────────────────────

export type DocTab = 'schnellstart' | 'cheatsheet' | 'handbuch';

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
      {/* Tab bar — Schnellstart nur für Admins */}
      <div className="border-b border-gray-200 px-4 flex gap-6 shrink-0">
        {((isAdmin ? ['schnellstart', 'cheatsheet', 'handbuch'] : ['cheatsheet', 'handbuch']) as DocTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => handleTab(tab)}
            className={`py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab === 'schnellstart' ? 'Schnellstart' : tab === 'cheatsheet' ? 'Kurzanleitung' : 'Handbuch'}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'schnellstart' && isAdmin
          ? <SchnellstartAdmin />
          : activeTab === 'cheatsheet'
          ? (isAdmin ? <CheatsheetAdmin /> : <CheatsheetMitarbeiter />)
          : <Accordion items={isAdmin ? handbuchAdminSections : handbuchMitarbeiterSections} />
        }
      </div>
    </div>
  );
}
