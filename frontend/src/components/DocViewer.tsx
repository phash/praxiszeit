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
            <p className="text-sm text-gray-600">Benutzer bearbeiten → Button „Wochenstunden anpassen…" (oder Uhr-Symbol in der Liste) → Dialog „Wochenstunden &amp; Tagesplan": „Gleichmäßig" (Wochenstunden + Arbeitstage) oder „Nach Tagen" (Stunden je Wochentag, Summe + Arbeitstage werden abgeleitet) + „Gültig ab"-Datum → historische Salden bleiben korrekt. Gilt für alle MA gleich, auch bei individuellem Tagesplan: Wochenstunden, Tagesstunden, Modus und Arbeitstage sind im Formular nur noch Anzeige, Verlauf zeigt „ab … bis …" (bei Tagesplan z. B. „Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 Std/Woche · 3 Tage/Woche").</p>
            <p className="text-sm text-gray-600">Sind im Wirkungszeitraum Abwesenheiten gebucht – bei rückwirkendem wie bei zukünftigem Datum –, zeigt der Dialog vorab Zeitraum, Tagessoll je Wochentag (alt→neu) und betroffene Abwesenheiten, deren Stunden nach Bestätigung umgerechnet werden, sowie Überstundensaldo und Urlaub (mit Jahr) vorher/nachher (Urlaubstage selbst bleiben unverändert). Löschen rechnet zurück – auch bei individuellem Tagesplan; die früheste Änderung ist erst löschbar, wenn keine späteren mehr bestehen.</p>
            <p className="text-sm text-gray-600">Monats- und Jahresbericht zeigen die zu Zeitraumsbeginn gültigen Wochenstunden plus den Hinweis „ab 15.03.2026: 20,0 Std/Woche" (bei individuellem Tagesplan „ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche") — im Dashboard wie in Excel/ODS/PDF (Jahresübersicht: eigene Spalte „Stundenänderungen").</p>
            <p className="text-sm text-amber-700">⚠️ Arbeitstage-only-Änderung (gleiche Wochenstunden, andere Arbeitstage): Bei „Gleichmäßig" nennt der Verlaufs-/Berichtstext zwar zusätzlich die neue Arbeitstage-Zahl (z. B. „ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage"), die Wochenstundenzahl selbst bleibt aber gleich – das Tagessoll verschiebt sich trotzdem still. Bei „Nach Tagen" ändert sich stattdessen nur der Urlaubsverbrauch (ein wegfallender Wochentag zählt einen dort schon gebuchten Urlaubstag rückwirkend nicht mehr). Deshalb vor dem Speichern immer die Vorschau prüfen, nicht nur die Wochenstundenzahl.</p>
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
        <p className="text-sm text-gray-500 mt-1">Alle MA mit „Nimmt an Betriebsferien teil" (Standard) erhalten automatisch Einträge – rollenunabhängig. Die <strong>Verrechnung</strong> wählen Sie beim Anlegen: „Als Urlaub werten" (Standard – 1 Urlaubstag je Schließ-Arbeitstag) oder „Bezahlte Freistellung" (saldoneutral, kostet keinen Urlaub). Nachträglich Berechtigte: Option setzen – Einträge werden automatisch für laufende und künftige Betriebsferien nachgetragen.</p>
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
        <p>Im <strong>laufenden Monat</strong> zählt das Soll nur bis zum <strong>letzten abgeschlossenen Arbeitstag</strong> – Sie starten den Monat also nicht mit einem dicken Minus; der heutige Tag zählt mit, sobald Sie <strong>ausgestempelt</strong> haben. Abgeschlossene Monate entsprechen dem vollen Monat. Das <strong>Überstundenkonto</strong> folgt für den laufenden Monat demselben Stichtag – auch hier entsteht am Monatsanfang kein künstliches Minus.</p>
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
        <p>Beim <strong>Ausstempeln</strong> und beim Speichern eines eigenen Eintrags erscheint zusätzlich ein Hinweis mit den konkreten Zeiten, sobald gekappt wurde (z. B. <em>„… gekappt (Beginn 07:00 → 07:45; Puffer 15 Minuten)"</em>). Der Eintrag wird trotzdem gespeichert — der Hinweis blockiert nichts.</p>
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
        <p>Navigieren Sie zu <strong>Abwesenheiten</strong> und klicken Sie auf <strong>+ Abwesenheit eintragen</strong>. Wählen Sie den Typ (Urlaub, Krank, Fortbildung, Überstundenausgleich, Sonstiges) und das Datum. Hat Ihre Praxis zusätzliche Gründe eingerichtet (z. B. „Schule"), erscheinen diese in der Typ-Auswahl unter <strong>„Eigene Gründe"</strong>.</p>
        <p className="text-gray-700"><strong>Kind krank (§45 SGB V):</strong> Ist der Grund „Kind krank" eingerichtet, wählen Sie ihn wie einen normalen Typ. Der Tag gilt als <strong>entschuldigt</strong> – keine Minusstunden, <strong>kein</strong> Urlaubsabzug, aber <strong>unbezahlt</strong> (die Krankenkasse zahlt ggf. Kinderkrankengeld). Ist Ihr Jahresanspruch aufgebraucht, erscheint ein Hinweis – der Tag wird <strong>trotzdem eingetragen</strong>.</p>
        <p>Für Zeiträume aktivieren Sie die Checkbox <strong>„Zeitraum"</strong> und geben ein Enddatum an. Wochenenden und Feiertage werden automatisch ausgeschlossen.</p>
        <p>Hat Ihre Praxis <strong>Heiligabend (24.12.)</strong> oder <strong>Silvester (31.12.)</strong> als arbeitsfrei oder halben Tag eingestellt, sind diese Tage im Kalender entsprechend markiert: grau „Heiligabend (frei)" bzw. amber „Silvester (½ Tag)" – ähnlich einem Feiertag.</p>
        <p>Wenn Urlaubsgenehmigungspflicht aktiv ist, wechselt die App nach dem Absenden automatisch zum Tab <strong>„Meine Anträge"</strong>.</p>
        <p className="text-gray-700"><strong>So wird Urlaub berechnet:</strong> nach dem Tagesprinzip (§3 BUrlG) – <strong>ein freier Arbeitstag = genau 1 Urlaubstag</strong>, egal wie viele Stunden Sie an dem Tag arbeiten. Eine freie Woche kostet so viele Tage, wie Sie Arbeitstage haben. Ihr Urlaubskonto zeigt die verbleibenden Tage.</p>
        <p className="text-gray-700"><strong>Betriebsferien (Praxisschließung):</strong> Bei Betriebsferien trägt die App Ihre Abwesenheiten an Ihren Arbeitstagen <strong>automatisch</strong> ein – Sie müssen nichts selbst buchen. Je nach Einstellung Ihrer Praxis zählen die Tage als <strong>bezahlte Freistellung</strong> (kein Urlaubsabzug) oder als <strong>Urlaub</strong>. Reicht Ihr Urlaub für die Schließung nicht, wird – wenn Ihre Praxis das so eingestellt hat – zuerst Ihr Urlaub verbraucht und der Rest als <strong>Überstundenabbau</strong> gebucht (Ihr Überstundenkonto sinkt und kann ins Minus gehen), sodass kein Minus-Urlaub entsteht. Die genaue Verrechnung legt die Praxisleitung fest. Fällt ein als „halber Feiertag" eingestellter Sondertag (24./31.12.) in die Schließung, wird dafür nur ein <strong>halber</strong> Urlaubs- bzw. Überstundentag verrechnet. Anders als bei einer selbst eingetragenen Urlaubsbuchung gibt es bei Betriebsferien <strong>keine Budget-Grenze</strong> – Ihre Praxisleitung kann die Schließung auch anordnen, wenn Ihr Resturlaub dafür nicht reicht.</p>
      </div>
    ),
  },
  {
    title: '8. So werden Ihre Stunden & Ihr Urlaub berechnet',
    content: (
      <div className="space-y-2">
        <p><strong>Tagessoll</strong> = Wochenstunden ÷ Arbeitstage pro Woche (z. B. 40 h auf 5 Tage = 8 h/Tag; 24 h auf 3 Tage = 8 h/Tag). Individuelle Tagesstunden überschreiben das. Wochenende und Feiertag = 0.</p>
        <p><strong>Ist</strong> = (Ende − Beginn) − Pause je Eintrag. <strong>Krankheit</strong> und <strong>Fortbildung</strong> werden so angerechnet, als hätten Sie gearbeitet, und zählen zu Ihrem Ist.</p>
        <p className="text-gray-700"><strong>Angerechnet wird nur, soweit Sie an diesem Tag auch hätten arbeiten müssen:</strong> an einem regulären Arbeitstag Ihr volles Tagessoll, an Wochenenden und gesetzlichen Feiertagen <strong>nichts</strong>, an einem als „halber Feiertag" geführten 24./31.12. die <strong>Hälfte</strong>. Ihr Soll bleibt stehen, die Gutschrift gleicht es genau aus – so bewegt eine Krankmeldung Ihren Saldo weder nach oben noch nach unten (§ 4 Abs. 2 EntgFG). Beispiel: 8 h/Tag, 24.12. als halber Feiertag, an diesem Tag krank ⇒ <strong>4 h</strong> angerechnet. Im Kalender bleibt es ein voller Krankheitstag; für den Saldo zählt der halbe. Eine Fortbildung, die länger dauerte als Ihr Arbeitstag, bleibt dagegen in voller Länge Mehrarbeit.</p>
        <p><strong>Saldo</strong> = Ist − Soll (grün = Mehrarbeit, rot = Minusstunden). Das <strong>Überstundenkonto</strong> summiert die Salden seit Jahresbeginn inkl. Vorjahresübertrag.</p>
        <p><strong>Überstundenausgleich:</strong> Das Soll bleibt, der Tag zählt als 0 Stunden → Ihr Überstundenkonto sinkt.</p>
        <p><strong>Voraussichtlicher Stand zum Jahresende:</strong> Saldo bis heute abzüglich der Stunden Ihrer bereits eingetragenen künftigen Überstundenausgleich-Tage bis zum 31.12. Urlaub, Krankheit und Fortbildung senken das Konto nicht und zählen deshalb nicht mit. Ihre Praxisleitung kann diese Anzeige in den Einstellungen abschalten — fehlt die Zeile, ist entweder kein künftiger Ausgleichstag eingetragen oder die Anzeige deaktiviert.</p>
        <p className="text-gray-700"><strong>Urlaub (Tagesprinzip, §3 BUrlG):</strong> 1 freier Arbeitstag = 1 Urlaubstag, egal wie lang der Tag ist (Halbtag = 0,5).</p>
        <p className="text-gray-700"><strong>Minijob mit fester Monatsarbeitszeit:</strong> Führt Ihre Praxis Sie mit einer <strong>festen vereinbarten Monatsarbeitszeit</strong> statt des obigen, aus Wochenstunden berechneten Solls, zeigt Ihr Monatssaldo jeden Monat dasselbe feste Soll (anteilig bei unterjährigem Ein-/Austritt). Feiertage sowie Urlaub oder bezahlte Freistellung an einem für Sie geplanten Arbeitstag werden dabei automatisch mit den geplanten Stunden gutgeschrieben; unbezahlt freie Tage mindern stattdessen das Monatssoll. Am Überstundenkonto kann dann ein weicher, nicht blockierender Hinweis erscheinen (§ 2 Abs. 2 MiLoG). Ob dieses Modell für Sie gilt, legt Ihre Praxisleitung fest.</p>
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
        <p><strong>Zwei-Faktor-Authentifizierung (2FA):</strong> Schützen Sie Ihr Konto zusätzlich mit einem Einmal-Code aus einer Authenticator-App (z. B. Google Authenticator, Authy). <strong>Aktivieren:</strong> Karte „Zwei-Faktor-Authentifizierung" → „2FA aktivieren" → aktuelles Passwort bestätigen → QR-Code scannen (oder Schlüssel manuell eintragen) → 6-stelligen Code bestätigen. <strong>Login:</strong> nach Benutzername + Passwort wird der 6-stellige Code abgefragt. <strong>Deaktivieren:</strong> „2FA deaktivieren" → aktuelles Passwort bestätigen. Bei verlorenem Zugang zur App hilft Ihr Administrator.</p>
        <p>Persönliche Daten wie Name und Wochenstunden können nur vom Administrator geändert werden. Unter <strong>Weitere Einstellungen</strong> finden Sie optionale Darstellungsoptionen.</p>
      </div>
    ),
  },
  {
    title: '11. Schichtplan einsehen',
    content: (
      <div className="space-y-2">
        <p>Wenn Ihre Praxis die <strong>Schichtplanung</strong> nutzt, finden Sie links den Menüpunkt <strong>Schichtplan</strong>. Dort sehen Sie die für Sie sichtbaren Wochenpläne als Übersicht: welcher Arbeitsplatz (z. B. Tresen, Labor) zu welcher Zeit besetzt ist und wer eingeteilt ist. Sichtbar sind Pläne, die heute gelten, sowie Pläne, die Ihr Administrator ausdrücklich <strong>für Mitarbeitende freigegeben</strong> hat – auch wenn sie erst künftig gelten oder ihr Zeitraum bereits abgelaufen ist. Gilt heute mehr als ein Plan (z. B. je ein Plan pro Standort), werden alle untereinander angezeigt. Zusätzlich freigegebene Pläne, die heute nicht gelten, erscheinen darunter in einer eigenen Vorschau-Auswahl: ein dort gewählter Plan ist mit dem Hinweis „Dieser Plan gilt noch nicht — er ist zur Ansicht freigegeben." bzw. „Dieser Plan gilt nicht mehr — er ist zur Ansicht freigegeben." (abgelaufener Zeitraum) als Vorschau gekennzeichnet.</p>
        <p>Manche Einteilungen tragen einen <strong>Hinweis</strong> (z. B. „Einarbeitung Azubi"), erkennbar am vorangestellten <strong>»</strong>. Über den Knopf <strong>„PDF"</strong> drucken Sie den gerade angezeigten Plan als Aushang aus. Nutzt Ihre Praxis mehrere Standorte, zeigt der Ausdruck den Standort entweder einmal in der Kopfzeile (gilt er für den ganzen Plan) oder hinter dem jeweiligen Arbeitsplatznamen, z. B. „Tresen (Hauptstelle)".</p>
        <p>Auf dem <strong>Dashboard</strong> zeigt die Karte <strong>„Deine Einteilung heute"</strong> Ihre heutigen Einsätze mit Arbeitsplatz und Uhrzeit — samt Hinweis (<strong>»</strong>), falls einer gesetzt ist.</p>
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
        <p>Für Teilzeit- und Tagesplan-Anpassungen: Benutzer öffnen → Button „<strong>Wochenstunden anpassen…</strong>" (oder Uhr-Symbol in der Benutzerliste) → Dialog „<strong>Wochenstunden &amp; Tagesplan</strong>": <strong>„Gleichmäßig"</strong> (Wochenstunden + Arbeitstage pro Woche) oder <strong>„Nach Tagen"</strong> (Stunden je Wochentag Mo–Fr; Wochensumme und Arbeitstage werden daraus abgeleitet, nicht frei wählbar) + <strong>„Gültig ab"</strong>-Datum eintragen. Diese Felder sind im Bearbeiten-Formular für <strong>alle</strong> Mitarbeitenden nur noch Anzeige, keine Direkteingabe mehr – auch nicht bei individuellem Tagesplan (beim <strong>Anlegen</strong> bleiben es normale Eingabefelder); historische Salden bleiben korrekt, der Verlauf zeigt „ab … bis …" (bei Tagesplan mit Tagesaufschlüsselung, z. B. „Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 Std/Woche · 3 Tage/Woche"). Sind im Wirkungszeitraum bereits Abwesenheiten gebucht, zeigt der Dialog vorab Zeitraum, das <strong>Tagessoll je Wochentag</strong> (alt→neu) und betroffene Abwesenheiten – nach Bestätigung werden deren Stunden auf das neue Tagessoll umgerechnet, bei rückwirkendem <strong>und</strong> bei zukunftsdatiertem Wirkungsdatum (Ausnahme: Überstundenausgleich und Mitarbeitende ohne Stundenzählung; Urlaubs<strong>tage</strong> bleiben unverändert, Tagesprinzip) – bei Tagesplan werden nur die Abwesenheiten des tatsächlich geänderten Wochentags umgerechnet. Zusätzlich zeigt der Dialog <strong>Überstundensaldo</strong> und <strong>Urlaub</strong> (mit Jahreszahl) jeweils vorher/nachher. Ein bereits abgeschlossenes Jahr wird dabei nur gemeldet, nicht neu berechnet. Löschen einer Änderung rechnet die Stunden ebenso zurück – auch bei individuellem Tagesplan; die <strong>früheste</strong> Änderung lässt sich erst löschen, wenn keine späteren mehr bestehen. Checkboxen: „ArbZG-Prüfungen aussetzen" für §18, „Nachtarbeitnehmer" für §6, „<strong>Nimmt an Betriebsferien teil</strong>" (Standard an, rollenunabhängig – für reine Verwaltungs-Accounts abwählbar), „Stundenzählung" aus für MA ohne Zeiterfassung (Urlaub/Krank zählen trotzdem tagebasiert).</p>
        <p className="text-amber-700">⚠️ <strong>Arbeitstage-only-Änderung – die Wochenstundenzahl allein verrät sie nicht:</strong> Ändern Sie bei „Gleichmäßig" nur die Arbeitstage pro Woche bei gleichbleibenden Wochenstunden, nennt der Verlauf/Bericht zwar zusätzlich die neue Arbeitstage-Zahl (z. B. „ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage") – aber die Wochenstundenzahl selbst bleibt unverändert, das Tagessoll verschiebt sich trotzdem still (z. B. 40 h auf 5 Tage → 40 h auf 4 Tage: 8 h/Tag → 10 h/Tag). Verschieben Sie bei „Nach Tagen" Stunden auf einen anderen Wochentag, ohne die Wochensumme zu ändern, bleibt das Tagessoll der übrigen Tage gleich – hier ändert sich stattdessen der <strong>Urlaubsverbrauch</strong>: ein am wegfallenden Wochentag bereits gebuchter Urlaubstag zählt rückwirkend nicht mehr. Vor dem Speichern deshalb immer die Vorschau prüfen, nicht nur die angezeigte Wochenstundenzahl.</p>
        <p><strong>Erster/Letzter Arbeitstag</strong> begrenzen die Soll-Berechnung: vor dem Eintritt bzw. nach dem Austritt entsteht kein Stundensoll. Die Übersicht zeigt je MA Urlaubskonto <strong>und</strong> Überstundensaldo (Jahr bis heute; „—" ohne Stundenzählung).</p>
        <p className="text-amber-700">⚠️ Bei <strong>unterjährigem Eintritt</strong> (nicht seit 1. Januar im System) den „Ersten Arbeitstag" unbedingt setzen – sonst zählt das Soll auch Tage vor dem Eintritt und es entstehen Phantom-Minusstunden.</p>
        <p><strong>Soll-Arbeitszeiten (Arbeitszeit-Fenster):</strong> Im Benutzerformular können Sie pro MA und Wochentag Soll-Beginn und Soll-Ende hinterlegen. Zeiten außerhalb des Fensters (abzüglich Puffer) werden nicht angerechnet; der gestempelte Rohwert bleibt gespeichert (§16). Der systemweite Puffer (Standard 15 Min.) ist unter <strong>Einstellungen → Arbeitszeit-Fenster Puffer</strong> konfigurierbar. Opt-in: ohne Soll-Zeiten kein Eingriff. MA mit deaktivierter Stundenzählung sind ausgenommen. <strong>Greift die Kappung, erscheint beim Speichern ein Hinweis mit den konkreten Zeiten</strong> (z. B. „Beginn 07:00 → 07:45"); gespeichert wird trotzdem. Bei einem Soll-Beginn zur vollen Stunde landet eine zu frühe Eingabe auf <code>hh:45</code> — das sieht wie eine Viertelstunden-Rundung aus, ist aber die Fenstergrenze. Eine Rundung gibt es nicht, Eingaben sind minutengenau. In der Eintragsliste (Admin-Dashboard, Monatsjournal, Zeiterfassung) steht unter der Uhrzeit dann „gestempelt 07:37 · angerechnet ab 07:45"; beim XLS-Import ist die Zeile bereits in der Vorschau als <em>Hinweis</em> markiert.</p>
        <p><strong>Minijob / Arbeitszeitkonto (§ 2 Abs. 2 MiLoG):</strong> Für Minijobber:innen auf Arbeitszeitkonto aktivieren Sie im Formular die Checkbox „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)" und tragen optional die „Vereinbarte Monatsarbeitszeit (h)" ein (leer = automatisch aus Wochenstunden × 13/3). Zusätzlich aktivierbar: „<strong>Feste Monatsarbeitszeit</strong>" – dann ist das Monats-Soll jeden Monat fix die vereinbarte Monatszeit, statt aus Wochenstunden/Arbeitstagen zu schwanken (setzt das Arbeitszeitkonto und eine eingetragene Monatszeit voraus). Details zu den weichen MiLoG-Warnungen und zur festen Monatsarbeitszeit: Abschnitt „Eigene Abwesenheitsgründe, Kind krank &amp; Minijob".</p>
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
    title: '8. Eigene Abwesenheitsgründe, Kind krank & Minijob',
    content: (
      <div className="space-y-2">
        <p><strong>Eigene Abwesenheitsgründe (#312):</strong> Unter <strong>Einstellungen → „Eigene Abwesenheitsgründe"</strong> legen Sie zusätzliche, frei benannte Gründe an (z. B. „Schule" für Auszubildende) – mit eigener Farbe und einem fixen <strong>Basis-Verhalten</strong>: <em>„Zählt als gearbeitet"</em> (wie Fortbildung, z. B. Berufsschule), <em>„Bezahlt frei"</em> (Tagessoll → 0, saldoneutral, kein Urlaubsabzug), <em>„Unbezahlt frei"</em> (wie „Bezahlt frei", aber Lohn gekürzt – für Kind krank oder unbezahlten Sonderurlaub) oder <em>„Überstundenabbau"</em> (Überstundenkonto sinkt um das Tagessoll). Das Basis-Verhalten ist nach dem Anlegen fix; Gründe lassen sich umbenennen, umfärben und deaktivieren. Sie erscheinen beim Buchen unter „Eigene Gründe".</p>
        <p className="text-gray-700"><strong>Datenschutz:</strong> Da ein eigener Grund sensibel sein kann (z. B. „Reha"), zeigt der Team-Kalender Abwesenheiten mit eigenem Grund für andere Mitarbeitende nur als <strong>„abwesend"</strong> – nur Admins sehen die Bezeichnung.</p>
        <p><strong>Kind krank &amp; Sonderurlaub-Vorlagen (#376):</strong> Unter „Vorlagen (1-Klick aktivieren)" legen Sie gängige Gründe direkt an – Kind krank, Todesfall, Hochzeit, Geburt, Umzug, Arztbesuch, Pflege. <strong>Kind krank</strong> (§45 SGB V) ist „unbezahlt frei" und wird pro Kalenderjahr gezählt: Standardanspruch unter <strong>Einstellungen → „Kind-krank-Standardanspruch"</strong> (Voreinstellung 15 Tage), pro Mitarbeiter:in im Benutzerformular überschreibbar. Bei Überschreitung erscheint beim Buchen ein <strong>Hinweis</strong> – die Abwesenheit wird trotzdem erfasst, nicht blockiert. Verbrauch je Person in der Benutzerübersicht.</p>
        <p><strong>Minijob / Arbeitszeitkonto (§ 2 Abs. 2 MiLoG, #377):</strong> Für Minijobber:innen auf Arbeitszeitkonto aktivieren Sie im Benutzerformular „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)". PraxisZeit warnt dann <strong>weich</strong> (nichts wird blockiert): bei <strong>&gt; 50 %</strong> Konto-Plusstunden der vereinbarten Monatsarbeitszeit und bei überfälligem <strong>12-Monats-Ausgleich</strong>. Die vereinbarte Monatsarbeitszeit tragen Sie im Feld „Vereinbarte Monatsarbeitszeit (h)" ein (leer = automatisch Wochenstunden × 13/3); der aktuelle gesetzliche Mindestlohn steht unter <strong>Einstellungen → „Gesetzlicher Mindestlohn"</strong>. Die Grenze bindet nur mindestlohnwirksame Stunden; PraxisZeit speichert keine Lohndaten und prüft daher nicht die 603-€-Grenze.</p>
        <p className="text-gray-700"><strong>Feste Monatsarbeitszeit (Baustein 2b):</strong> Bei aktivem Arbeitszeitkonto zusätzlich aktivierbar: „Feste Monatsarbeitszeit (Monats-Soll = vereinbarte Monatsarbeitszeit)". Statt der Tagessoll-Summe zählt dann jeden Monat exakt die vereinbarte Monatszeit als Soll (anteilig bei unterjährigem Ein-/Austritt). Feiertag, Urlaub oder bezahlte Freistellung an einem geplanten Tag schreiben die geplanten Stunden dem Ist gut; ein unbezahlt entschuldigter Tag mindert stattdessen das feste Soll. Weiche Warnung, wenn das Monats-Ist die vereinbarte Zeit übersteigt. Bekannte Grenze: Fällt ein <strong>ganzer</strong> Monat durch Urlaub/Krankheit aus und liegen die geplanten Tagesstunden deutlich unter der Monatszeit, deckt die Gutschrift nur den geplanten Anteil ab – der flexible Rest bleibt Konto-Defizit und braucht eine manuelle Korrektur. Details in Abschnitt „Berechnungsgrundlagen".</p>
      </div>
    ),
  },
  {
    title: '9. ArbZG-Berichte & Compliance',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> (nach unten scrollen) finden Sie: <strong>§5 Ruhezeitverstöße</strong> (&lt;11h zwischen Arbeitstagen), <strong>§6 Nachtarbeit</strong> (≥48 Nachtarbeitstage/Jahr), <strong>§11 Sonntagsarbeit</strong> (max. 37/Jahr) und <strong>§11 Ersatzruhetag</strong> (Fristen überwachen). Erfasste Pflicht-Pause-Ausnahmen samt Begründung sind ebenfalls einsehbar.</p>
        <p>Das System prüft bei jeder Eingabe automatisch §3, §4 (Pausenpflicht), §6 (8h für Nachtarbeitnehmer), §9/10 (Sonntagsarbeit), §14 (48h-Wochenwarnung).</p>
        <p className="text-amber-700"><strong>§3 Tageshöchstgrenze (10h):</strong> Beim <strong>Live-Ausstempeln</strong> wird ein Tag über 10h nicht blockiert (die Zeit ist bereits geleistet und §16-pflichtig zu dokumentieren) – es erscheint eine deutliche Warnung. Bei <strong>manueller Eingabe oder Antrag</strong> bleibt die 10h-Grenze eine <strong>harte Sperre</strong>.</p>
      </div>
    ),
  },
  {
    title: '10. Audit-Log & Fehler-Monitoring',
    content: (
      <div className="space-y-2">
        <p>Das <strong>Änderungsprotokoll</strong> zeichnet alle Aktionen unveränderlich auf (Login, Zeiteinträge, Abwesenheiten, Benutzerverwaltung, Korrekturanträge). Dient als Nachweis gem. §16 ArbZG bei Betriebsprüfungen.</p>
        <p>Das <strong>Fehler-Monitoring</strong> zeigt Backend-Fehler mit Häufigkeit und Kontext. Wiederkehrende Fehler als GitHub Issue melden (Button in der Detailansicht).</p>
      </div>
    ),
  },
  {
    title: '11. Berechnungsgrundlagen (Soll, Ist, Überstunden, Urlaub)',
    content: (
      <div className="space-y-2">
        <p><strong>Tagessoll</strong> = Wochenstunden ÷ Arbeitstage pro Woche – der Divisor ist <strong>nicht</strong> fix 5 (24 h auf 3 Tage = 8 h/Tag). Individuelle Tagesstunden je Wochentag sind möglich; Wochenende/Feiertag/außerhalb des Beschäftigungszeitraums = 0.</p>
        <p><strong>Ist</strong> = (Ende − Beginn) − Pause, nie negativ. Ein Soll-Arbeitszeit-Fenster kürzt die Anrechnung auf das Fenster (± Puffer); der Rohstempel bleibt erhalten (§16 ArbZG). Krank und Fortbildung zählen als Ist (§3 EntgFG).</p>
        <p><strong>Abwesenheiten:</strong> Urlaub, bezahlte Freistellung &amp; Sonstige senken das Soll; Krank &amp; Fortbildung füllen das Ist auf (saldo-neutral); der Überstundenausgleich lässt das Soll stehen (Ist 0 h) und baut Überstunden ab.</p>
        <p><strong>Die Gutschrift für Krank/Fortbildung folgt dem Soll des Tages:</strong> voller Betrag nur an einem regulären Arbeitstag – an Wochenenden und Feiertagen <strong>keine</strong> Gutschrift, an einem als „halber Feiertag" konfigurierten 24./31.12. die <strong>Hälfte</strong>. An einem Tag ohne Arbeitspflicht kann keine Arbeitspflicht ausfallen (§ 4 Abs. 2 EntgFG). Beispiel: krank vom 24.12. bis 28.12. ⇒ 4 + 0 + 0 + 0 + 8 = <strong>12 h</strong> gutgeschrieben = genau das Soll dieser Tage, Saldo 0. Eine Fortbildung, die länger dauerte als der Arbeitstag, bleibt echte Mehrarbeit – gedeckelt wird nicht.</p>
        <p><strong>Wo der Fehler im Alltag auftrat.</strong> An Wochenenden und an bereits eingetragenen Feiertagen legt PraxisZeit beim Buchen gar keine Abwesenheit an – im Beispiel oben entstehen nur zwei Zeilen (24.12. und 28.12.). Der Regelfall war deshalb der <strong>Halbtags-Sondertag</strong>: eine normale Krankmeldung am 24.12. brachte bis Version 1.17.0 4 h Soll gegen 8 h Gutschrift = <strong>+4 Überstunden aus dem Nichts</strong>. Auf einem Feiertag kann eine Abwesenheit nachträglich landen (Bundesland umgestellt, eigener Feiertag auf ein gebuchtes Datum gelegt, Buchung in ein noch nicht synchronisiertes Jahr) – dann kam je solchem Tag ein volles Tagessoll dazu.</p>
        <p><strong>Was das Update repariert – und was nicht.</strong> Laufende und noch <strong>nicht abgeschlossene</strong> Jahre korrigieren sich von selbst, weil die Salden bei jedem Aufruf neu berechnet werden. Ein bereits per <strong>Jahresabschluss</strong> abgeschlossenes Jahr <strong>nicht</strong>: der Übertrag ist eingefroren und wird bewusst nie automatisch neu gerechnet (sonst würden manuelle Korrekturen überschrieben). Da der Fehler naturgemäß im Dezember auftrat, ist das der wahrscheinlichste Fall – prüfen Sie nach dem Update den Übertrag betroffener Mitarbeiter:innen unter „Jahresabschluss" und korrigieren Sie ihn dort von Hand.</p>
        <p><strong>Überstundenkonto</strong> = fortlaufende Summe der Monatssalden ab dem Jahresübertrag. Die Spalte „Überstunden (JTD)" zeigt 1. Januar bis heute zzgl. Carryover.</p>
        <p><strong>Voraussichtlicher Saldo zum Jahresende:</strong> Zeigt zusätzlich, wie das Konto zum 31.12. voraussichtlich aussieht – der Saldo bis heute abzüglich der Stunden aller bereits gebuchten künftigen Überstundenausgleich-Tage. Nur Ausgleichstage senken das Konto; Urlaub, Krankheit und Fortbildung sind saldo-neutral und fließen nicht in die Vorschau ein. Unter <strong>Einstellungen → Überstunden-Projektion zum Jahresende</strong> lässt sich das getrennt für das Mitarbeiter-Dashboard und für die Spalte „Überstd. Jahresende" im Admin-Dashboard (Monats-/Wochenbericht) abschalten (Standard: beide an).</p>
        <p><strong>Urlaub (Tagesprinzip §3 BUrlG):</strong> 1 freier Arbeitstag = 1 Tag (Halbtag 0,5), unabhängig von der Stundenzahl. Anspruch <code>30 × Arbeitstage ÷ 5</code>, anteilig bei unterjährigem Eintritt/Austritt, zzgl. Resturlaub-Vortrag (Carryover). Nur Urlaub belastet das Budget; ein als „Frei + zählt als Urlaub" konfigurierter Sondertag (24./31.12.) kostet ebenfalls 1 Tag. Vor Eintritt/nach Austritt: kein Anspruch und kein Verbrauch.</p>
        <p><strong>Feste Monatsarbeitszeit (Minijob-Modus, #377 Baustein 2b):</strong> Für MA mit diesem Opt-in gilt statt der obigen Tagessoll-Summe ein <strong>festes</strong> Monats-Soll (= vereinbarte Monatsarbeitszeit, kalendertag-pro-rata bei Ein-/Austritt); Feiertag/Urlaub/bezahlte Freistellung an geplanten Tagen schreiben die geplanten Stunden dem Ist gut statt das Soll zu senken, unbezahlte Fehltage (Sonstiges) mindern stattdessen das feste Soll. Details in Abschnitt 8 „Eigene Abwesenheitsgründe, Kind krank & Minijob". Im <strong>Monatsjournal</strong> heißt die Tagesspalte in diesem Modus „Geplant" (geplante Anwesenheit, kein Tages-Soll) und der Tages-Saldo entfällt — verbindlich ist die Monatsübersicht unter der Tabelle (#463).</p>
        <p className="text-gray-500">Vollständige Formeln und durchgerechnete Beispiele: <code>docs/BERECHNUNGEN.md</code> bzw. Admin-Handbuch-Anhang „Berechnungsgrundlagen".</p>
      </div>
    ),
  },
  {
    title: '12. Datensicherung (Backup & Restore)',
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
    title: '13. Schichtplanung (optional)',
    content: (
      <div className="space-y-2">
        <p>Die <strong>Schichtplanung</strong> ist <strong>standardmäßig deaktiviert</strong>. Sie aktivieren sie unter <strong>Einstellungen → Schichtplanung</strong>. Erst danach erscheinen die Menüpunkte <strong>Schichtplanung</strong> (Admin) und <strong>Schichtplan</strong> (alle) und das Dashboard-Widget.</p>
        <p>Unter <strong>Schichtplanung → Stammdaten</strong> legen Sie <strong>Standorte</strong> (optional) und <strong>Arbeitsplätze</strong> (z. B. Tresen, Labor, Springer – mit Farbe) an. Unter <strong>Schichtpläne</strong> erstellen Sie beliebig viele benannte <strong>Wochenpläne</strong> (z. B. „Normalzustand", „Azubis Schulferien").</p>
        <p>Im Wochen-Editor verteilen Sie <strong>Zeitslots</strong> per Drag &amp; Drop oder Klick über die Woche und ziehen <strong>Mitarbeitende</strong> aus der Liste auf einen Slot. Optional setzen Sie pro Slot eine <strong>Mindestbesetzung</strong>; unterbesetzte Slots werden markiert (weiche Warnung, blockiert nicht). Im Slot-Dialog gibt es außerdem das Feld <strong>„Hinweis (optional)"</strong> (bis zu 500 Zeichen), z. B. „Einarbeitung Azubi" – der Text erscheint mit vorangestelltem <strong>»</strong> im Wochenraster, im PDF-Ausdruck und auf der Dashboard-Karte „Deine Einteilung heute" der betroffenen Mitarbeitenden, rein informativ ohne Auswirkung auf Berechnungen. <strong>Achtung:</strong> Der Hinweis ist für alle Mitarbeitenden mit Plansicht lesbar und wird beim PDF-Aushang mitgedruckt – keine Gesundheitsangaben oder anderen sensiblen Daten hineinschreiben.</p>
        <p>Im Reiter <strong>Einweisungen</strong> legen Sie per Matrix (Mitarbeiter × Arbeitsplätze) fest, wer für welchen Arbeitsplatz <strong>eingewiesen</strong> ist. Weisen Sie eine nicht eingewiesene Person zu, erscheint die weiche Warnung <strong>„nicht eingewiesen"</strong> (blockiert nicht). Mitarbeitende sehen ihre Einweisungen in ihrem Profil.</p>
        <p>Über <strong>Bearbeiten</strong> setzen Sie pro Plan optional ein <strong>Aktiv-Datums-Fenster</strong> („von/bis") — der Plan wird dann im Zeitraum automatisch aktiv; die <strong>Jahresübersicht</strong> zeigt das als Zeitstrahl. Mit <strong>Automatisch füllen</strong> verteilt der Generator eingewiesene, an dem Tag verfügbare Mitarbeitende greedy auf die Slots (ausgewogen nach Auslastung/Überstunden) — als Entwurf zum Review; der Plan wird dabei nicht aktiviert.</p>
        <p>Der <strong>Woche/Tag</strong>-Umschalter zeigt wahlweise die ganze Woche oder einen einzelnen Wochentag in voller Breite. Beim Bearbeiten eines Slots kopiert <strong>„Auf Wochentage kopieren"</strong> denselben Slot (Arbeitsplatz, Zeit, Mindestbesetzung, Zuweisungen <strong>und Hinweis</strong>) auf weitere Tage — praktisch für wiederkehrende Schichten; ein für den Ursprungstag formulierter Hinweistext wandert wortgleich mit, auf den Zieltagen ggf. anpassen. Mit <strong>„Duplizieren"</strong> kopieren Sie einen kompletten Plan (inkl. Slots und Zuweisungen) als <strong>inaktiven Entwurf ohne Freigabe für Mitarbeitende</strong> — ideal, um Varianten aus einem Bestandsplan abzuleiten, ohne dass die unfertige Kopie versehentlich bei den Mitarbeitenden auftaucht.</p>
        <p><strong>Geplante Wochentage:</strong> Unter <strong>Einstellungen → Schichtplanung</strong> wählen Sie, welche Wochentage der Planer anzeigt und plant (Standard <strong>Mo–Fr</strong>; Sa/So oder ein Schließtag einzeln zu-/abschaltbar, mind. ein Tag aktiv). Ein abgeschalteter Tag verschwindet aus der Wochenansicht, nimmt keine neuen Slots auf und wird von der Auto-Generierung übersprungen. Bereits angelegte Slots bleiben erhalten und kehren beim Reaktivieren des Tages zurück.</p>
        <p>In der Mitarbeiterliste des Editors steht unter jedem Namen die <strong>Auslastung</strong> – zugewiesene Schichtstunden zur Wochenarbeitszeit, z. B. <em>„15,25 / 17 h"</em>: grün bei ±30 Min. zur Vertragszeit, gelb bei ±1 Std., sonst rot. Das erleichtert eine ausgewogene Einteilung.</p>
        <p>Mit <strong>Aktiv schalten</strong> machen Sie einen Plan für alle sichtbar; <strong>mehrere Pläne können gleichzeitig aktiv</strong> sein. Mitarbeitende sehen ihre heutige Einteilung im Dashboard.</p>
        <p>Über den Knopf <strong>„Bearbeiten"</strong> (Stift-Symbol) in der Werkzeugleiste des Plan-Editors öffnen Sie die <strong>Plan-Einstellungen</strong>; dort gibt es zusätzlich den Schalter <strong>„Für Mitarbeitende sichtbar"</strong>. Er macht den Plan in der Mitarbeiteransicht sichtbar – <strong>unabhängig vom Aktiv-Datums-Fenster</strong>, sowohl schon vor dessen Beginn (praktisch, um z. B. einen ab September geltenden Plan schon vorher bekannt zu machen) als auch nach dessen Ende. <strong>Achtung, Falle:</strong> Ein befristeter Plan bleibt für Mitarbeitende sichtbar, solange der Schalter gesetzt ist – auch Wochen nach Ablauf des Zeitfensters; das Zurückschalten müssen Sie selbst erledigen. Ein heute aktiver bzw. im Datums-Fenster liegender Plan ist ohnehin sichtbar, unabhängig vom Schalter. Welche Pläne freigegeben sind, sehen Sie am <strong>Augen-Symbol</strong> in der Planliste sowie am Abzeichen <strong>„Sichtbar"</strong> im Kopf des geöffneten Plans.</p>
        <p>Der Knopf <strong>„PDF"</strong> in der Werkzeugleiste erzeugt einen Aushang im Querformat mit einer Tabelle Arbeitsplatz × Wochentag – zum Aushängen am Schwarzen Brett. Auch Mitarbeitende können darüber den Plan drucken, den sie in ihrer Ansicht sehen. Ein Schwarzes Brett ist oft auch für Patientinnen und Patienten einsehbar – das gehört bei der Wahl des Hinweistexts bedacht. Gilt der gedruckte Plan gerade nicht, trägt der Ausdruck fett in der Kopfzeile den Vermerk <strong>„Vorschau — gilt derzeit nicht"</strong> bzw. <strong>„Nicht mehr gültig"</strong>. Haben alle Arbeitsplätze des Plans denselben Standort, steht er einmal in der Kopfzeile („Standort: Hauptstelle"); bei unterschiedlichen (oder teils fehlenden) Standorten steht er stattdessen hinter jedem betroffenen Arbeitsplatznamen, z. B. „Tresen (Hauptstelle)".</p>
        <p className="text-gray-500">Die Schichtplanung ist ein reines Planungswerkzeug und berührt <strong>nicht</strong> Zeiterfassung, Soll/Ist-Stunden, ArbZG-Prüfungen, Urlaub oder Überstunden. Details: <code>docs/SCHICHTPLANUNG.md</code>.</p>
      </div>
    ),
  },
  {
    title: '14. Admin-Passwort verloren (nur native Installation)',
    content: (
      <div className="space-y-2">
        <p>Kommt niemand mehr mit einem Administrator-Konto in die Anwendung, hilft ein Kommando <strong>auf dem Server selbst</strong> — es setzt das Passwort direkt in der Datenbank neu und braucht dafür keine Anmeldung:</p>
        <p><code>sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py reset-admin-password</code></p>
        <p className="text-gray-500">Der lange Pfad ist nötig: das Programm braucht den mitgelieferten Python-Interpreter und liegt nicht als normaler Befehl im Systempfad. Weicht Ihr Installationsverzeichnis von <code>/opt/praxiszeit</code> ab, ersetzen Sie es entsprechend.</p>
        <p>Das neue Passwort wird zweimal abgefragt (nicht mit eingetippt, damit es nicht in der Befehls-Historie landet) und gegen dieselben Regeln geprüft wie in der Anwendung. Danach sind <strong>alle laufenden Sitzungen dieses Kontos ungültig</strong>.</p>
        <p>Ist auch das Handy mit der <strong>Zwei-Faktor-Anmeldung</strong> weg, reicht das neue Passwort nicht — der Login fragt weiter nach einem Code. Dann <code>--disable-2fa</code> ergänzen und die Zwei-Faktor-Anmeldung anschließend im Profil neu einrichten. Betrifft es ein anderes Konto als <code>admin</code>: <code>--username &lt;name&gt;</code>.</p>
        <p>Jeder solche Vorgang wird mit Zeitpunkt, betroffenem Konto und dem auslösenden Betriebssystem-Konto dauerhaft festgehalten (Nachweispflicht nach Art. 5 Abs. 2 DSGVO) — ein Passwort-Reset ist kein stiller Vorgang.</p>
        <p className="text-gray-500">In der <strong>Docker</strong>-Installation steckt dasselbe Werkzeug im Backend-Abbild: <code>docker compose exec backend python -m app.cli.reset_admin_password</code>. Der Eintrag <code>[admin] password</code> in <code>config/praxiszeit.conf</code> ist <strong>keine</strong> Antwort auf die Frage — er ist nur der Startwert der Erstinstallation und nach der ersten Änderung falsch; das Kommando überschreibt ihn anschließend mit einem Zufallswert.</p>
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
        <p className="text-sm text-gray-500 mt-1"><strong>Eigene Abwesenheitsgründe</strong> (z. B. „Schule" für Azubis) legen Sie unter <strong>Einstellungen → „Eigene Abwesenheitsgründe"</strong> an: Bezeichnung + Farbe + Basis-Verhalten (<em>zählt als gearbeitet</em> / <em>bezahlt frei</em> / <em>unbezahlt frei</em> / <em>Überstundenabbau</em>; nach dem Anlegen fix). Sie erscheinen beim Buchen unter „Eigene Gründe"; im Team-Kalender werden sie für Kolleg:innen aus Datenschutzgründen als „abwesend" maskiert.</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Kind krank & Sonderurlaub (#376):</strong> Unter „Vorlagen (1-Klick aktivieren)" legen Sie gängige Gründe direkt an (Kind krank, Todesfall, Hochzeit, Umzug …). <strong>Kind krank</strong> (§45 SGB V) ist <em>unbezahlt frei</em> und wird pro Jahr gezählt: Standardanspruch unter <strong>Einstellungen → „Kind-krank-Standardanspruch"</strong> (Voreinstellung 15 Tage), pro Mitarbeiter:in im Benutzerformular überschreibbar. Bei Überschreitung erscheint beim Buchen ein Hinweis – die Abwesenheit wird trotzdem erfasst (nicht blockiert). Verbrauch je Person in der Benutzerübersicht.</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Minijob / Arbeitszeitkonto (§ 2 Abs. 2 MiLoG, #377):</strong> Für Minijobber:innen auf Arbeitszeitkonto aktivieren Sie im Benutzerformular „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)". Die <strong>vereinbarte Monatsarbeitszeit</strong> tragen Sie im Feld „Vereinbarte Monatsarbeitszeit (h)" direkt ein (leer = automatisch aus den Wochenstunden × 13/3). PraxisZeit warnt dann <em>weich</em> (nicht blockierend), wenn die Konto-Plusstunden pro Monat 50 % dieser Monatszeit übersteigen oder die 12-Monats-Ausgleichsfrist reißt – beim Buchen, im eigenen Überstundenkonto und in der Benutzerübersicht. Der aktuelle Mindestlohn steht unter <strong>Einstellungen → „Gesetzlicher Mindestlohn"</strong>. Hinweis: die Grenze bindet nur mindestlohnwirksame Stunden; bei höherer Vergütung ggf. unkritisch. Keine Lohn-/603-€-Prüfung (kein Lohn hinterlegt).</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Feste Monatsarbeitszeit (Minijob-Modus, #377 Baustein 2b):</strong> Bei aktivem Arbeitszeitkonto können Sie zusätzlich „Feste Monatsarbeitszeit (Monats-Soll = vereinbarte Monatsarbeitszeit)" aktivieren – dann macht die vereinbarte Monatszeit zur <strong>Pflichtangabe</strong> und wird jeden Monat fest als Soll gesetzt (anteilig bei unterjährigem Ein-/Austritt), statt aus Wochenstunden/Arbeitstagen zu schwanken. Die Tagesstunden je Wochentag werden dann zur „geplanten Anwesenheit": Feiertag, Urlaub oder bezahlte Freistellung auf einem geplanten Tag schreiben die geplanten Stunden dem Ist gut; ein unbezahlt entschuldigter Tag (Sonstiges) mindert stattdessen das feste Soll. Bei einer <strong>bestehenden</strong> Person tragen Sie diese Tagesstunden ausschließlich über „Wochenstunden anpassen…" (Modus „Nach Tagen") ein – im Bearbeiten-Formular selbst gibt es keine Tagesstunden-Matrix mehr; beim <strong>Anlegen</strong> sind es weiterhin normale Eingabefelder. Weiche Warnung, wenn das Monats-Ist die vereinbarte Zeit übersteigt. <strong>Bekannte Grenze:</strong> Liegen die geplanten Tagesstunden deutlich unter der Monatszeit, deckt die Gutschrift bei einem <em>ganzen</em> Fehlmonat (Urlaub/Krank) nur den geplanten Anteil ab – der flexible Rest bleibt Konto-Defizit und braucht eine manuelle Korrektur; einzelne Fehltage sind korrekt.</p>
      </section>

      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-2">2. Mitarbeiter anlegen</h3>
        <p className="text-sm text-gray-600 mb-1"><strong>Benutzerverwaltung → „Neue:r Mitarbeiter:in"</strong>: Benutzername + Startpasswort, Name, Wochenstunden bzw. Tagesplan, Urlaubsanspruch → Speichern.</p>
        <ul className="text-sm text-gray-500 list-disc list-inside space-y-0.5">
          <li>Leitende Angestellte: <em>„Keine Stundenzählung"</em> – Urlaub/Krank trotzdem tagebasiert.</li>
          <li>Ein-/Austritt: <em>Erster/Letzter Arbeitstag</em> setzen.</li>
          <li>Optional: Soll-Arbeitszeit-Fenster (Soll-Beginn/-Ende je Wochentag).</li>
          <li>Spätere Änderungen an Wochenstunden, Tagesplan, Modus oder Arbeitstagen: nur noch über „Wochenstunden anpassen…" mit Wirkungsdatum.</li>
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
