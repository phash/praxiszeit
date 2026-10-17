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
              <li>Zeiterfassung → Tab <strong>Einträge</strong> → <strong>+ Neuer Eintrag</strong> (nur für heute)</li>
              <li>Von, Bis eintragen</li>
              <li>Pause in Minuten (Pflicht!)</li>
              <li>An Sonn-/Feiertagen: <strong>Ausnahmegrund</strong> (§10 ArbZG)</li>
              <li>Speichern</li>
            </ol>
            <p className="text-sm text-gray-500 mt-1">Mobil: <strong>+</strong>-Button oben rechts auf der Seite</p>
            <p className="text-sm text-gray-500 mt-1"><strong>Vergangener Tag</strong> (z. B. Stempeln vergessen): Button <strong>Antrag</strong> (links neben <strong>+ Neuer Eintrag</strong>) oder im Journal <strong>+</strong> in der Zeile des Tages → Änderungsantrag mit Begründung.</p>
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
            <p className="text-sm text-gray-500 mt-1">Gilt für den <strong>ganzen Tag</strong> (alle Einträge zusammen); Lücken unter 15 Min. zählen nicht als Pause.</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Tagesgrenze (§3 ArbZG)</p>
            <ul className="text-sm text-gray-600 space-y-0.5">
              <li>⚠️ Warnung ab 8 Stunden Nettoarbeitszeit</li>
              <li>⚠️ Über 10 Stunden: Warnung beim Live-Ausstempeln</li>
              <li>🚫 Über 10 Stunden bei manueller Eingabe / Antrag: gesperrt</li>
            </ul>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Arbeitszeit-Blöcke</p>
            <ul className="text-sm text-gray-600 space-y-0.5">
              <li>Nur wenn die Praxis Blöcke hinterlegt hat (Profil → „Meine Arbeitszeit"); sonst zählt alles wie gewohnt.</li>
              <li>Angerechnet wird innerhalb der Blöcke, mit Puffer (Std. 15 Min.) an jedem Blockrand. Wochenende und Feiertage haben keine Blöcke.</li>
              <li>Über die Pause zwischen zwei Blöcken gestempelt → „gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet".</li>
              <li>Pause in der Lücke gemacht? Die Lücke zählt als Pause (§4 ArbZG; ab 15 Min. nach Abzug des Puffers) – keine zusätzliche Pause eintragen, sonst wird beides abgezogen („Pause in der Lücke wird zusätzlich abgezogen: …" → Pause auf 0 setzen).</li>
              <li>Dort gearbeitet? Am Eintrag <strong>„Anrechnung beantragen"</strong> (für heute erst nach Arbeitsende). Anerkannte Einträge: am selben Tag gesperrt, danach per Änderungs- bzw. Löschantrag.</li>
              <li>Vergessen auszustempeln? Automatisch geschlossen um 23:59, angerechnet nur bis Blockende + Puffer → tatsächliches Ende per Änderungsantrag nachtragen (auch ein echtes Ende 23:59; die Zeit nach dem Block zählt erst, wenn die Verwaltung anerkennt).</li>
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
        <p className="text-sm text-gray-500 mt-1"><strong>Bearbeiten</strong> und <strong>Löschen</strong> direkt nur bei heutigen Einträgen; das Datum ist dabei gesperrt – gehört die Zeit zu einem anderen Tag: Eintrag löschen und über <strong>Antrag</strong> den richtigen Tag beantragen.</p>
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
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Tagessaldo</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Heute: Ist aller Einträge des Tages (z. B. Vormittag + Nachmittag) vs. Tagessoll (grün = eingestempelt)</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Monatssaldo</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Über-/Unterstunden diesen Monat (H:MM)</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Überstunden</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Kumulierter Jahressaldo</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">Urlaub</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Verbleibende Urlaubstage</td></tr>
          </tbody>
        </table>
        <p className="text-sm text-gray-500 mt-2">Grüner Saldo (+) = Überstunden | Roter Saldo (–) = Fehlstunden</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Monat ↔ Woche:</strong> Umschalter über der Übersichtstabelle → letzte 8 Kalenderwochen mit Soll/Ist/Saldo/Konto (laufende Woche bis heute). Fehlende Einträge fallen pro Woche sofort auf.</p>
        <p className="text-sm text-gray-500 mt-1">Kasten <strong>„Hinweis zu Ihrer Arbeitszeit"</strong>: Die Verwaltung hat Ihre Arbeitszeit geändert (bleibt 30 Tage) → Link „Arbeitszeit im Profil ansehen" bzw. Profil → „Meine Arbeitszeit".</p>
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
              <li>Benutzerverwaltung → „Neue:r Mitarbeiter:in"</li>
              <li>Benutzername, Vor-/Nachname, Passwort</li>
              <li>Wochenstunden + Arbeitstage/Woche (oder Modus „Nach Tagen" / „Nach Arbeitsblöcken"), Urlaubstage</li>
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
            <p className="text-sm font-medium text-gray-700 mb-1">Arbeitszeit ändern</p>
            <p className="text-sm text-gray-600">Benutzer bearbeiten → Button „Arbeitszeit anpassen…" (oder Uhr-Symbol in der Liste) → Dialog „Arbeitszeit &amp; Wochenstunden": „Gültig ab" + „Gleichmäßig", „Nach Tagen" oder „Nach Arbeitsblöcken" (bis zu 3 Blöcke je Wochentag + Pause innerhalb der Blöcke; Tagessoll = Σ Blöcke − Pause; nur bei Stundenzählung) + optional Notiz. Im Formular nur Anzeige (Bereich „Arbeitszeit heute"), beim Anlegen normale Felder bzw. Block-Editor. Verlauf „Ab … bis …".</p>
            <p className="text-sm text-gray-600">Vorab die Auswirkung prüfen (Einträge je Monat alt → neu, Abwesenheiten, Δ Soll / Δ angerechnet / Überstundenkonto / Urlaubsverbrauch; Haken Pflicht, sobald etwas betroffen ist). Rückwirkend werden Einträge an geänderten Wochentagen ab Rohstempel mit dem aktuellen Puffer neu gekappt, danach Abwesenheits-Stunden aufs neue Tagessoll (Urlaubstage bleiben); offene Einträge vergangener Tage werden vorher geschlossen.</p>
            <p className="text-sm text-amber-700">⚠️ Verkürzung (Eintrag verliert Zeit, Konto sinkt – auch durch höheres Soll – oder Misch-Tag-Gutschrift sinkt stärker als das Tagessoll): Standard „Ab heute"; rückwirkend nur mit Grund, Begründung und Haken (Grund, Begründung und Notiz zusammen höchstens 500 Zeichen); in abgeschlossene Jahre gesperrt. Falsche Stempel am Zeiteintrag korrigieren, nicht über die Arbeitszeit.</p>
            <p className="text-sm text-gray-600">Löschen: Papierkorb nur an der jüngsten Zeile des Verlaufs. Verkürzt das Löschen, Standard „auf den vorherigen Stand zurücksetzen" (Knopf „Zurücksetzen") oder „Rückwirkend löschen mit Neuberechnung". Wurde inzwischen eine Änderung dazwischen angelegt, lehnt PraxisZeit die Rücksetzung ab („Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.").</p>
            <p className="text-sm text-gray-600">MA sehen 30 Tage den Dashboard-Kasten „Hinweis zu Ihrer Arbeitszeit"; Protokoll „Neukappung (Arbeitszeit-Änderung)" je Eintrag + Sammelzeile. Berichte zeigen den Wert zu Zeitraumsbeginn plus „ab 15.03.2026: 20,0 Std/Woche" (Tagesplan „ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche", Blöcke „ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche") — im Dashboard wie in Excel/ODS/PDF (Jahresübersicht: Spalte „Stundenänderungen").</p>
            <p className="text-sm text-amber-700">⚠️ Arbeitstage-only-Änderung (gleiche Wochenstunden, andere Arbeitstage): Bei „Gleichmäßig" nennt der Verlaufs-/Berichtstext zwar die neue Arbeitstage-Zahl (z. B. „ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage"), die Wochenstundenzahl bleibt aber gleich – das Tagessoll verschiebt sich trotzdem still. Bei „Nach Tagen"/„Nach Arbeitsblöcken" ändert sich stattdessen der Urlaubsverbrauch (ein wegfallender Wochentag zählt einen dort gebuchten Urlaubstag rückwirkend nicht mehr). Deshalb immer die Auswirkung prüfen, nicht nur die Wochenstundenzahl.</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Nicht angerechnete Zeit</p>
            <p className="text-sm text-gray-600">Zeit vor, nach und zwischen den Blöcken zählt nur bis zum Puffer (an jedem Blockrand, Einstellungen → „Soll-Arbeitszeit-Fenster", Std. 15 Min.). Sichtbar am Eintrag, im Journal („Anwesenheit nicht angerechnet") und in der Export-Spalte „Nicht angerechnet (Min)". Geleistete Arbeit: <strong>„Anerkennen"</strong> (Admin-Dashboard-Detail, Monatsjournal) – dauerhaft, protokolliert. Nichtanrechnung ersetzt keine Vergütungsentscheidung.</p>
            <p className="text-sm text-gray-600"><strong>Auto-Close</strong> (vergessenes Ausstempeln, 23:59) rechnet nur bis zum letzten Block + Puffer an („automatisch geschlossen"); tatsächliches Ende nachtragen (MA per Änderungsantrag) – auch ein echtes Ende 23:59 ist eintragbar (wird gekappt wie jedes Ende, bis 23:59 angerechnet erst nach „Anerkennen").</p>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-sm p-2">
            <p className="text-sm text-amber-800">⚠️ Niemals löschen! In der Benutzerliste auf „Deaktivieren" klicken. 2 Jahre Aufbewahrung (§16 ArbZG).</p>
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
        <p className="text-sm text-gray-500 mt-2">Tageszeilen von Monatsreport und Jahresreport Detailliert: hinten angehängt „Unterbrechung (Min)" und „Zeiteinträge" (Excel/ODS), als letzte Spalte – auch im PDF – „Nicht angerechnet (Min)" (Lücke + vor/nach den Blöcken abgeschnittene Zeit). „Netto" ist die angerechnete Zeit. Der Jahresreport Classic (nur Monatswerte, keine Tageszeilen) hat diese Spalten nicht.</p>
        <p className="text-sm text-gray-500 mt-2">Aufbewahrungspflicht: 2 Jahre (§16 ArbZG)</p>
      </section>

      {/* Änderungsanträge (Menüpunkt „Änderungsanträge", Filter „Offen") */}
      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">✅ Änderungsanträge prüfen</h3>
        <ol className="text-sm text-gray-600 list-decimal list-inside space-y-0.5">
          <li>Änderungsanträge → Filter „Offen" (vorausgewählt)</li>
          <li>Alt- und Neuwerte + Begründung lesen</li>
          <li>Genehmigen oder Ablehnen (mit optionalem Grund)</li>
          <li>„Anrechnung beantragt": „Genehmigen und anerkennen" oder „Ohne Anerkennen genehmigen"; sonst ggf. zusätzlich „Genehmigen und anerkennen"</li>
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
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§3</td><td className="px-3 py-2 border border-gray-200 text-gray-600">8h-Warnung; &gt;10h: Warnung beim Live-Ausstempeln, harte Sperre bei manueller Eingabe/Antrag; 48h-Wochenwarnung</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§4</td><td className="px-3 py-2 border border-gray-200 text-gray-600">30/45 Min. Pausenpflicht – ganzer Tag, Lücken unter 15 Min. zählen nicht; Sperre auch beim Ausstempeln (Ausnahme mit Begründung abschaltbar)</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§5</td><td className="px-3 py-2 border border-gray-200 text-gray-600">11h Mindestruhezeit</td></tr>
            <tr className="bg-gray-50"><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§11</td><td className="px-3 py-2 border border-gray-200 text-gray-600">15 freie Sonntage/Jahr</td></tr>
            <tr><td className="px-3 py-2 border border-gray-200 font-medium text-gray-700">§18</td><td className="px-3 py-2 border border-gray-200 text-gray-600">Ausnahme für leitende Angestellte</td></tr>
          </tbody>
        </table>
        <p className="text-sm text-gray-500 mt-2">Mit Arbeitszeit-Blöcken rechnen die §3/§4-Sperren mit der <strong>angerechneten</strong> Zeit; zusätzlich (nie blockierend) Hinweise „laut Stempel": über die Lücke durchgestempelt ohne erfasste Pause (§4), Anwesenheit über 10 h am Tag bzw. 48 h in der Woche (§3).</p>
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
        <p>Das Dashboard zeigt Ihren <strong>Tagessaldo</strong> (heute: Ist vs. Tagessoll), den <strong>Monatssaldo</strong> (Ist – Soll in H:MM), den kumulierten Jahressaldo, das Urlaubskonto und den <strong>Urlaubscountdown</strong> (Tage bis zum nächsten Urlaub oder zur nächsten Praxisschließung – das frühere Datum zählt).</p>
        <p>Im <strong>laufenden Monat</strong> zählt das Soll nur bis zum <strong>letzten abgeschlossenen Arbeitstag</strong> – Sie starten den Monat also nicht mit einem dicken Minus; der heutige Tag zählt mit, sobald Sie <strong>ausgestempelt</strong> haben. Abgeschlossene Monate entsprechen dem vollen Monat. Das <strong>Überstundenkonto</strong> folgt für den laufenden Monat demselben Stichtag – auch hier entsteht am Monatsanfang kein künstliches Minus.</p>
        <p>Der <strong>Tagessaldo</strong> („x von y h heute") zählt <strong>alle</strong> heute erfassten Einträge – bei geteiltem Dienst Vormittag <strong>und</strong> Nachmittag, auch nach dem Ausstempeln; solange Sie eingestempelt sind, zählt die Anzeige minütlich mit. Rot („Noch nicht eingestempelt") erscheint nur an einem Arbeitstag, an dem Sie heute noch gar nicht gestempelt haben; wer schon gearbeitet hat und gerade nicht eingestempelt ist, sieht neutral „Ausgestempelt". An Feiertagen, bei ganztägiger Abwesenheit (Urlaub, Krankheit, Fortbildung, Überstundenausgleich …), vor dem Eintritt und an einem freien 24./31.12. gibt es heute kein Tagessoll – dann erscheint weder Rot noch „x von y". Ein halber Urlaubstag oder ein halber 24./31.12. halbiert das Tagessoll. Sind Arbeitszeit-Blöcke für Sie hinterlegt und Sie sind in der geplanten Pause zwischen zwei Blöcken nicht eingestempelt, zeigt die Karte neutral „Pause zwischen den Arbeitsblöcken" statt Rot. Auf dem Smartphone listet die Karte <strong>„Letzte Einträge"</strong> Ihre fünf neuesten Einträge, der jüngste zuerst – auch über den Monatswechsel hinweg (am Monatsersten die letzten Einträge des Vormonats).</p>
        <p><strong>Monats-/Wochenübersicht:</strong> Über den Umschalter <strong>„Monat / Woche"</strong> über der Tabelle sehen Sie statt der Monate die <strong>letzten 8 Kalenderwochen</strong> mit Soll, Ist, Saldo und dem Stand Ihres Überstundenkontos am Wochenende. So fällt ein vergessener Nachmittags-Eintrag oder ein automatisch um 23:59 geschlossener Eintrag sofort auf. Die laufende Woche zählt wie der Monatssaldo nur bis heute; Ihre Auswahl bleibt auf dem Gerät gespeichert.</p>
        <p><strong>Hinweis bei Änderungen Ihrer Arbeitszeit:</strong> Ändert die Verwaltung Ihre Arbeitszeit (Wochenstunden, Tagesplan oder Arbeitszeit-Blöcke), steht 30 Tage lang der Kasten <strong>„Hinweis zu Ihrer Arbeitszeit"</strong> auf dem Dashboard – auch wenn die Änderung erst künftig gilt, zurückgesetzt oder wieder gelöscht wurde. Beispiele: <em>„Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00). 3 Einträge neu berechnet, angerechnete Zeit −2:15 h."</em> oder <em>„Ihre Arbeitszeit ändert sich ab 01.11.2026 (neu: 40,0 h/Woche auf 4 Arbeitstage)."</em> (die Arbeitstage stehen nur dabei, wenn sie sich ändern). „Neu berechnet" heißt: Ihre bereits erfassten Einträge im betroffenen Zeitraum wurden mit der neuen Arbeitszeit neu angerechnet – Ihre Stempelzeiten bleiben unverändert gespeichert. Bei einer rückwirkenden Verkürzung nennt der Hinweis die Art des Grundes. Über <strong>„Arbeitszeit im Profil ansehen"</strong> gelangen Sie zu Profil → „Meine Arbeitszeit".</p>
        <p className="text-gray-700"><strong>Offener Urlaub (ab Oktober):</strong> Im letzten Quartal weist das Urlaubskonto gelb auf noch offene Urlaubstage und die Frist hin – erst ab <strong>einem ganzen</strong> offenen Tag. Kleinere Reste (z. B. 0,5 Tage bei Teilzeit) lösen keinen Hinweis aus; sie stehen unverändert in Ihrem Urlaubskonto.</p>
        <p>Grüner Saldo = Überstunden, roter Saldo = Fehlstunden. Auf mobilen Geräten wird die untere Tab-Leiste zur Navigation genutzt.</p>
      </div>
    ),
  },
  {
    title: '3. Zeiterfassung – Einträge erstellen & bearbeiten',
    content: (
      <div className="space-y-2">
        <p>Navigieren Sie zu <strong>Zeiterfassung → Tab „Einträge"</strong>. Klicken Sie auf <strong>+ Neuer Eintrag</strong>. Das Formular erscheint direkt über der Tabelle – Von, Bis und Pause ausfüllen, dann Speichern. So erfassen Sie einen Eintrag für <strong>heute</strong>; einen <strong>vergangenen Tag</strong> beantragen Sie über den Button <strong>Antrag</strong> (links daneben) oder im Journal über das <strong>+</strong> in der Zeile des Tages. Ein anderes Datum lehnt das Formular ab (<em>„Einträge für vergangene Tage können nur per Änderungsantrag erstellt werden"</em>). Sind Arbeitszeit-Blöcke für Sie hinterlegt, sind Von und Bis mit dem Beginn des ersten und dem Ende des letzten Blocks von heute vorbelegt.</p>
        <p>Heutige Einträge können Sie direkt über <strong>Bearbeiten</strong> ändern oder löschen. Ältere oder gesperrte Einträge erfordern einen Korrekturantrag (Änderungs- bzw. Löschantrag). Das <strong>Datum</strong> ist beim Bearbeiten gesperrt: <em>„Das Datum bleibt beim Bearbeiten fest. Gehört die Zeit zu einem anderen Tag: Eintrag löschen und oben über „Antrag“ einen Änderungsantrag für diesen Tag stellen."</em> Ein anderes Datum gibt es also nur per Antrag; bei älteren Einträgen ändern Sie es direkt im Änderungsantrag. Ändern Sie beim Bearbeiten nur die Notiz (Zeiten und Pause bleiben gleich), sperrt die Pausenregel nicht erneut; eine schon dokumentierte Begründung bleibt ohne neue Genehmigung stehen.</p>
        <p><strong>Wochenende/Feiertag (z. B. KV-Dienst):</strong> Am selben Tag stempeln oder normal eintragen – an Sonn- und Feiertagen erscheint zusätzlich das Feld <strong>Ausnahmegrund</strong>. Nachträglich per Antrag: Button <strong>Antrag</strong> im Tab „Einträge" oder im <strong>Journal</strong> das <strong>+</strong> in der Zeile des Tages; an Sonn- und Feiertagen fragen beide Wege (Antragsformular und Journal) nach dem <strong>Ausnahmegrund (§10 ArbZG)</strong>. Das Soll ist an diesen Tagen 0, die angerechneten Stunden erhöhen also den Saldo.</p>
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
        <p><strong>Der ganze Tag zählt:</strong> Geprüft werden alle Einträge des Tages zusammen, nicht nur der laufende Abschnitt. Aus- und sofort wieder einstempeln ist keine Pause – eine Unterbrechung zählt erst ab <strong>15 Minuten</strong>.</p>
        <p><strong>Mit Arbeitszeit-Blöcken:</strong> Eine Pause, die Sie in der Lücke zwischen zwei Blöcken gemacht haben, tragen Sie nicht zusätzlich ein – die Lücke zählt bereits als Pause (→ Abschnitt 5).</p>
        <p className="text-gray-700">Fehlt das Begründungsfeld, hat Ihre Praxis die Ausnahme „Pflicht-Pause war nicht möglich" abgeschaltet – dann klappt das Ausstempeln nur mit eingetragener Pause.</p>
      </div>
    ),
  },
  {
    title: '5. Arbeitszeit-Blöcke & Anrechnung',
    content: (
      <div className="space-y-2">
        <p>Ihre Praxis kann Ihre Arbeitszeit je Wochentag (Mo–Fr) als <strong>Arbeitszeit-Blöcke</strong> hinterlegen (z. B. Mo 08:00–12:00 und 15:00–18:00). Ihr Tagessoll ergibt sich dann aus den Blöcken; Ihre Blöcke und deren Verlauf zeigt <strong>Profil → „Meine Arbeitszeit"</strong>. Ein aus früheren Versionen übernommenes Arbeitszeit-Fenster wirkt wie ein Block je Tag, ändert Ihr Tagessoll aber nicht – das kommt dann weiter aus Ihren Wochen- bzw. Tagesstunden. Ist nichts hinterlegt, zählt Ihre gestempelte Zeit ganz normal.</p>
        <p>Angerechnet wird Ihre gestempelte Zeit <strong>innerhalb</strong> der Blöcke, mit einem Puffer (Standard 15 Min.) an jedem Blockrand. Zu früh eingestempelt? Hinweis <em>„Du hast vor deinem Soll-Beginn eingestempelt — angerechnet ab 07:45."</em>, in der Eintragsliste <em>„gestempelt 07:30 · angerechnet ab 07:45"</em>. Noch einmal bis 07:45 eingestempelt (etwa nach einem Fehlstempel)? Dann fiele der neue Eintrag auf denselben Beginn – PraxisZeit lehnt ab mit <em>„Einstempeln nicht möglich: Ein Zeiteintrag von heute beginnt bereits um 07:45 …"</em>; den vorhandenen Eintrag bearbeiten oder nach 07:45 erneut einstempeln. Über die Pause zwischen zwei Blöcken durchgestempelt (08:00–18:00 bei 08–12 und 15–18)? Dann steht dort <em>„gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet"</em> – wer um 12:05 ausstempelt, verliert keine Minute, und liegen zwei Blöcke höchstens den doppelten Puffer auseinander, zählt die Zeit dazwischen ganz. In der Pause zwischen den Blöcken zeigt das Dashboard neutral „Pause zwischen den Arbeitsblöcken". An Wochenenden und Feiertagen gelten keine Blöcke – Arbeit dort (z. B. Notdienst) wird voll angerechnet.</p>
        <p>Beim <strong>Ausstempeln</strong> und beim Speichern eines eigenen Eintrags erscheint ein Hinweis, sobald etwas nicht angerechnet wird, z. B. <em>„Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."</em> Der Eintrag wird trotzdem gespeichert. <strong>Pause und Lücke:</strong> Die Zeit zwischen zwei Blöcken zählt für die Pausenpflicht (§ 4 ArbZG) als Pause, sobald nach Abzug des Puffers mindestens 15 Minuten übrig bleiben. Haben Sie dort Pause gemacht, tragen Sie sie <strong>nicht zusätzlich</strong> ein – sonst wird beides abgezogen („Pause in der Lücke wird zusätzlich abgezogen: …"; dann die Pause auf 0 setzen).</p>
        <p><strong>Vergessen auszustempeln?</strong> Ein offener Eintrag eines vergangenen Tages wird automatisch geschlossen (um 23:59) und nur bis zum Ende Ihres letzten Blocks plus Puffer angerechnet. Tragen Sie das tatsächliche Ende per Änderungsantrag nach. Auch ein tatsächliches Ende um 23:59 (z. B. nach einem Spät- oder Notdienst) können Sie eintragen; es gilt dann als echter Stempel, wird wie jedes andere Ende an Ihren Blöcken gekürzt und erst bis 23:59 angerechnet, wenn die Verwaltung den Eintrag anerkennt. (Ist das angerechnete Ende bereits 23:59 – etwa an einem Tag ohne Arbeitszeit-Blöcke –, bleibt die Kennzeichnung „automatisch geschlossen" stehen; angerechnet wird dann ohnehin bis 23:59.) Ebenso bleibt die Kennzeichnung, wenn das eingetragene Ende genau dem angerechneten Ende entspricht (z. B. 18:15) – auch wenn Sie tatsächlich um diese Zeit gegangen sind: PraxisZeit kann es nicht vom automatisch gesetzten Wert unterscheiden, und eine Anrechnung lässt sich für diesen Eintrag dann nicht beantragen.</p>
        <p><strong>Dort gearbeitet?</strong> Unter der Zusatzzeile steht in der Zeiterfassung und im Journal der Link <strong>„Anrechnung beantragen"</strong>: kurz begründen und absenden (bei einem automatisch geschlossenen Eintrag im selben Antrag das tatsächliche Ende angeben). Für heute geht das erst nach Arbeitsende. Genehmigt die Verwaltung mit Anerkennen, werden die beantragten Zeiten (vorbelegt sind Ihre Stempel) ohne Kürzung durch die Blöcke angerechnet, und der Eintrag ist „anerkannt"; „ohne Anerkennen genehmigt" heißt, die Zeiten wurden übernommen, aber wie bei jedem Eintrag an Ihren Blöcken gekürzt. Einen anerkannten Eintrag können Sie nicht mehr selbst bearbeiten oder löschen: Am selben Tag steht dort ein Schloss („Anerkannter Eintrag – Änderung ab morgen per Änderungsantrag oder über die Verwaltung"), ab dem nächsten Tag geht es per Änderungs- bzw. Löschantrag. Ändert der Antrag nur die Notiz (Datum, Zeiten und Pause wie gespeichert), scheitert er nicht an § 3 oder § 4 ArbZG; geänderte Zeiten oder Pause werden wieder voll geprüft.</p>
        <p className="text-gray-700">Ihre <strong>echte Stempelzeit geht nicht verloren</strong> (§16 ArbZG) – fürs Stundenkonto zählt die angerechnete Zeit. <strong>Nicht angerechnet heißt nicht unbezahlt:</strong> Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist zu vergüten (§ 611a, § 612 BGB; Mindestlohngesetz).</p>
      </div>
    ),
  },
  {
    title: '6. Korrekturanträge stellen & verwalten',
    content: (
      <div className="space-y-2">
        <p>Wenn ein gesperrter Eintrag korrigiert werden muss: <strong>Zeiterfassung → Tab „Einträge"</strong> → in der Aktionsspalte auf <strong>Änderungsantrag</strong> klicken → korrekte Zeiten + Begründung eingeben (an Sonn- und Feiertagen zusätzlich den <strong>Ausnahmegrund (§10 ArbZG)</strong>) → Antrag stellen.</p>
        <p>Den Status aller Anträge sehen Sie unter <strong>Zeiterfassung → Tab „Anträge"</strong>. Filter: Alle / Offen / Genehmigt / Abgelehnt. Offene Anträge können mit <strong>Zurückziehen</strong> storniert werden.</p>
        <p><strong>Vergangener Tag ohne Eintrag</strong> (z. B. vergessen zu stempeln): Button <strong>Antrag</strong> (links neben <strong>+ Neuer Eintrag</strong>) oder im Journal das <strong>+</strong> in der Zeile des Tages → Datum, Von, Bis, Pause und Begründung eintragen → Antrag stellen.</p>
        <p><strong>Anrechnung beantragen:</strong> Bei einem eigenen Eintrag mit nicht angerechneter Zeit (z. B. „2:30 h zwischen den Blöcken nicht angerechnet") stellen Sie über <strong>„Anrechnung beantragen"</strong> einen Antrag mit Begründung; das Datum ist dabei fest, und bei einem automatisch geschlossenen Eintrag geben Sie das tatsächliche Ende an. Für heute geht das erst nach Arbeitsende. In der Antragsliste trägt der Antrag das Kennzeichen „Anrechnung beantragt", nach der Genehmigung zusätzlich „anerkannt" bzw. „ohne Anerkennen genehmigt". Einen <strong>anerkannten</strong> Eintrag können Sie nicht mehr selbst bearbeiten oder löschen – ab dem nächsten Tag nur per Änderungs- bzw. Löschantrag, am selben Tag nur über die Verwaltung.</p>
        <p className="text-gray-700"><strong>Pflicht-Pause war nicht möglich?</strong> Erfüllen Ihre korrigierten Zeiten die Pausenregel nicht, wird der Antrag nicht abgelehnt – es erscheint das Feld <strong>„Pflicht-Pause war nicht möglich – Begründung"</strong>. Kurz erläutern und mit <strong>Mit dokumentierter Ausnahme senden</strong> abschicken; die Abweichung wird dokumentiert und dem Admin vorgelegt. Hat Ihre Praxis diese Ausnahme abgeschaltet, erscheint das Feld nicht – tragen Sie dann die Pause ein.</p>
      </div>
    ),
  },
  {
    title: '7. Abwesenheiten eintragen',
    content: (
      <div className="space-y-2">
        <p>Navigieren Sie zu <strong>Abwesenheiten</strong> und klicken Sie auf <strong>+ Abwesenheit eintragen</strong>. Wählen Sie den Typ (Urlaub, Krank, Fortbildung, Überstundenausgleich, Sonstiges) und das Datum. Hat Ihre Praxis zusätzliche Gründe eingerichtet (z. B. „Schule"), erscheinen diese in der Typ-Auswahl unter <strong>„Eigene Gründe"</strong>.</p>
        <p className="text-gray-700"><strong>Tag mit anerkanntem Zeiteintrag:</strong> Liegt an einem der zu buchenden Tage ein Zeiteintrag, den die Verwaltung anerkannt hat (→ Abschnitt 5), lehnt PraxisZeit die Buchung ab und nennt den Tag, z. B. „Am 05.10.2026 gibt es einen anerkannten Zeiteintrag – bitte an die Verwaltung wenden." Die Verwaltung trägt die Abwesenheit für diesen Tag ein. Die übrigen Tage können Sie getrennt buchen.</p>
        <p className="text-gray-700"><strong>Kind krank (§45 SGB V):</strong> Ist der Grund „Kind krank" eingerichtet, wählen Sie ihn wie einen normalen Typ. Der Tag gilt als <strong>entschuldigt</strong> – keine Minusstunden, <strong>kein</strong> Urlaubsabzug, aber <strong>unbezahlt</strong> (die Krankenkasse zahlt ggf. Kinderkrankengeld). Ist Ihr Jahresanspruch aufgebraucht, erscheint ein Hinweis – der Tag wird <strong>trotzdem eingetragen</strong>.</p>
        <p>Für Zeiträume aktivieren Sie die Checkbox <strong>„Zeitraum"</strong> und geben ein Enddatum an. Wochenenden und Feiertage werden automatisch ausgeschlossen, ebenso Tage, an denen Sie laut Arbeitsplan nicht arbeiten (z. B. ein freier Wochentag bei Teilzeit) – dort erfasste Arbeitszeit bleibt stehen. Liegt im Zeitraum kein einziger Tag, an dem Sie arbeiten, lehnt PraxisZeit die Buchung ab.</p>
        <p>Hat Ihre Praxis <strong>Heiligabend (24.12.)</strong> oder <strong>Silvester (31.12.)</strong> als arbeitsfrei oder halben Tag eingestellt, sind diese Tage im Kalender entsprechend markiert: grau „Heiligabend (frei)" bzw. amber „Silvester (½ Tag)" – ähnlich einem Feiertag.</p>
        <p>Wenn Urlaubsgenehmigungspflicht aktiv ist, wechselt die App nach dem Absenden automatisch zum Tab <strong>„Meine Anträge"</strong>. Neben dem Zeitraum steht dort, wie viele <strong>Tage</strong> der Antrag kostet – gezählt werden nur Ihre Arbeitstage (wer mittwochs nicht arbeitet, zahlt für Mo–Fr 4 Tage), ein halber Tag zählt 0,5. Bei einem Urlaubsantrag werden genau so viele Urlaubstage nach der Genehmigung abgezogen. Steht dort 0, liegt im Zeitraum kein Tag, an dem Sie arbeiten – ein solcher Antrag kann nicht genehmigt werden.</p>
        <p className="text-gray-700"><strong>So wird Urlaub berechnet:</strong> nach dem Tagesprinzip (§3 BUrlG) – <strong>ein freier Arbeitstag = genau 1 Urlaubstag</strong>, egal wie viele Stunden Sie an dem Tag arbeiten. Eine freie Woche kostet so viele Tage, wie Sie Arbeitstage haben. Ihr Urlaubskonto zeigt die verbleibenden Tage.</p>
        <p className="text-gray-700"><strong>Betriebsferien (Praxisschließung):</strong> Bei Betriebsferien trägt die App Ihre Abwesenheiten an Ihren Arbeitstagen <strong>automatisch</strong> ein – Sie müssen nichts selbst buchen. Je nach Einstellung Ihrer Praxis zählen die Tage als <strong>bezahlte Freistellung</strong> (kein Urlaubsabzug) oder als <strong>Urlaub</strong>. Reicht Ihr Urlaub für die Schließung nicht, wird – wenn Ihre Praxis das so eingestellt hat – zuerst Ihr Urlaub verbraucht und der Rest als <strong>Überstundenabbau</strong> gebucht (Ihr Überstundenkonto sinkt und kann ins Minus gehen), sodass kein Minus-Urlaub entsteht. Die genaue Verrechnung legt die Praxisleitung fest. Fällt ein als „halber Feiertag" eingestellter Sondertag (24./31.12.) in die Schließung, wird dafür nur ein <strong>halber</strong> Urlaubs- bzw. Überstundentag verrechnet. Anders als bei einer selbst eingetragenen Urlaubsbuchung gibt es bei Betriebsferien <strong>keine Budget-Grenze</strong> – Ihre Praxisleitung kann die Schließung auch anordnen, wenn Ihr Resturlaub dafür nicht reicht.</p>
        <p className="text-gray-700"><strong>Urlaubscountdown:</strong> Die Kachel auf dem Dashboard zählt auch bis zur nächsten Praxisschließung – egal, ob die Schließtage als Urlaub, Überstundenabbau oder bezahlte Freistellung gebucht sind. Liegt ein eigener Urlaub früher, zeigt sie diesen.</p>
      </div>
    ),
  },
  {
    title: '8. So werden Ihre Stunden & Ihr Urlaub berechnet',
    content: (
      <div className="space-y-2">
        <p><strong>Tagessoll</strong> = Wochenstunden ÷ Arbeitstage pro Woche (z. B. 40 h auf 5 Tage = 8 h/Tag; 24 h auf 3 Tage = 8 h/Tag). Individuelle Tagesstunden überschreiben das. Wochenende und Feiertag = 0. Bei Arbeitszeit-Blöcken: Summe der Blöcke minus Pause innerhalb der Blöcke (08:00–12:00 und 15:00–18:00 mit 30 Min. Pause = 6:30 h); ein übernommenes Arbeitszeit-Fenster ändert das Tagessoll nicht.</p>
        <p><strong>Ist</strong> = (Ende − Beginn) − Pause je Eintrag, abzüglich nicht angerechneter Zeit vor, nach oder zwischen Ihren Arbeitszeit-Blöcken. <strong>Krankheit</strong> und <strong>Fortbildung</strong> werden so angerechnet, als hätten Sie gearbeitet, und zählen zu Ihrem Ist.</p>
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
        <p><strong>Meine Arbeitszeit:</strong> Die Karte zeigt je Wochentag Ihre heute gültigen Arbeitszeit-Blöcke mit Tagessoll (z. B. „Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Tagessoll 6:30 h"), darunter Ihre Wochenstunden und im Verlauf jede Änderung mit Wirkungsdatum. Ohne Blöcke steht „–" statt der Zeiten; Tagessoll und Wochenstunden sehen Sie trotzdem. Bei einem übernommenen Arbeitszeit-Fenster steht darunter <em>„Diese Zeiten begrenzen nur die Anrechnung der erfassten Zeit; das Tagessoll wird nicht aus ihnen berechnet."</em>, bei fester Monatsarbeitszeit (Minijob) heißen die Tageswerte „geplant", ohne Stundenzählung entfällt das Tagessoll.</p>
        <p>Vorname, Nachname und E-Mail-Adresse ändern Sie selbst über „Bearbeiten" neben Ihrem Namen (→ <strong>Speichern</strong>), das Profilbild per Klick aufs Bild. Benutzername, Rolle, Urlaubstage und Ihre Arbeitszeit legt die Verwaltung fest. Unter <strong>Weitere Einstellungen</strong> finden Sie optionale Darstellungsoptionen.</p>
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
        <p>Mit dem Umschalter <strong>„Monat / Woche"</strong> oben wechseln Sie zwischen Monats- und <strong>Wochenansicht</strong>. In der Wochenansicht steht statt „Juni 2026" die Kalenderwoche (z. B. <em>„22.–28.06.2026 (KW 26)"</em>); die Pfeile blättern wochenweise. Gleiche Spalten wie im Monat – ideal für eine schnelle Plausibilitätsübersicht. Ihre Auswahl bleibt pro Browser/Gerät gespeichert. Mitarbeitende haben auf ihrem Dashboard denselben Umschalter (letzte 8 Wochen, „bis heute") – für dieselbe Woche mit denselben Zahlen.</p>
        <p>Das Dropdown <strong>„Soll: bis heute / Monatsende"</strong> schaltet die Soll-Basis um: <strong>bis heute</strong> (Standard) zählt das Soll des laufenden Monats nur bis zum letzten abgeschlossenen Arbeitstag (kein Monatsanfangs-Minus), <strong>Monatsende</strong> den vollen Monat. Für abgeschlossene Monate identisch; die §16-Datei-Exporte bleiben voll-Monat. In der Wochenansicht heißt die zweite Option entsprechend <strong>„volle Woche"</strong>.</p>
        <p>Klicken Sie auf den Pfeil am Ende einer Zeile für die Detailansicht. Nutzen Sie die Suche zum Filtern nach Name.</p>
        <p><strong>Jahresend-Warnung (ab Oktober):</strong> Über der Jahresübersicht des laufenden Jahres listet ein gelber Hinweis alle Mitarbeitenden, die noch <strong>mindestens einen ganzen Urlaubstag</strong> offen haben. Kleinere Reste (z. B. 0,3 oder 0,5 Tage bei Teilzeit) lösen bewusst keine Warnung aus – sie lassen sich nicht als ganzer Tag nehmen und werden üblicherweise im Folgejahr mit weiteren Bruchteilen zusammengelegt; in Tabelle, Urlaubskonto und Jahresabschluss zählen sie unverändert. Der Hinweis nennt auch das Verfallsdatum (in der Regel den 31.03. des Folgejahres, sonst die für die Person hinterlegte Frist); haben die genannten Personen unterschiedliche Fristen, steht das Datum hinter jedem Namen. Dieselbe Schwelle und dasselbe Datum gelten für den Hinweis im Mitarbeiter-Dashboard.</p>
      </div>
    ),
  },
  {
    title: '2. Benutzerverwaltung',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Benutzerverwaltung</strong> legen Sie Mitarbeiter an (<strong>„Neue:r Mitarbeiter:in"</strong>), bearbeiten und deaktivieren sie. Niemals löschen – in der Aktionsspalte „Deaktivieren" (Aufbewahrungspflicht §16 ArbZG, 2 Jahre). Das <strong>letzte aktive Admin-Konto</strong> lässt sich weder deaktivieren noch herabstufen – sonst käme niemand mehr in die Verwaltung.</p>
        <p>Arbeitszeit ändern (Teilzeit, Tagesplan, Blöcke): Benutzer öffnen → Button „<strong>Arbeitszeit anpassen…</strong>" (oder Uhr-Symbol in der Benutzerliste) → Dialog „<strong>Arbeitszeit &amp; Wochenstunden</strong>": <strong>„Gleichmäßig"</strong> (Wochenstunden + Arbeitstage pro Woche), <strong>„Nach Tagen"</strong> (Stunden je Wochentag Mo–Fr; Wochensumme und Arbeitstage werden abgeleitet) oder <strong>„Nach Arbeitsblöcken"</strong> (bis zu drei Blöcke je Wochentag + Pause innerhalb der Blöcke, nur bei aktiver Stundenzählung, siehe Abschnitt 3) + <strong>„Gültig ab"</strong>-Datum, optional eine Notiz. Im Bearbeiten-Formular sind diese Angaben für <strong>alle</strong> Mitarbeitenden nur Anzeige (Bereich „Arbeitszeit heute") und zeigen den <strong>heute gültigen</strong> Stand – auch nach dem Wirkungsdatum einer zukunftsdatierten Änderung; gelten heute Arbeitszeit-Blöcke, heißt der Modus „Nach Arbeitsblöcken" und die Wochenstunden stehen wie im Kopf des Dialogs mit den Blöcken. Beim <strong>Anlegen</strong> sind es normale Felder bzw. der Block-Editor. Der Verlauf zeigt „Ab … bis …" (z. B. „Mo 08:00–12:00 + 15:00–18:00 / Di 08:00–12:00 = 11,0 h/Woche" oder „Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 Std/Woche · 3 Tage/Woche"). Vor dem Speichern zeigt der Dialog die Auswirkung (neu berechnete Einträge, Abwesenheiten, Soll, angerechnete Zeit, Überstundenkonto, Urlaubsverbrauch; Urlaubs<strong>tage</strong> bleiben unverändert); ein bereits abgeschlossenes Jahr wird nur gemeldet, nicht neu berechnet. Rückwirkung, Verkürzungsschutz und Löschen beschreibt Abschnitt 3. Checkboxen: „ArbZG-Prüfungen aussetzen" für §18, „Nachtarbeitnehmer" für §6, „<strong>Nimmt an Betriebsferien teil</strong>" (Standard an, rollenunabhängig – für reine Verwaltungs-Accounts abwählbar), „Stundenzählung" aus für MA ohne Zeiterfassung (Urlaub/Krank zählen trotzdem tagebasiert).</p>
        <p className="text-amber-700">⚠️ <strong>Arbeitstage-only-Änderung – die Wochenstundenzahl allein verrät sie nicht:</strong> Ändern Sie bei „Gleichmäßig" nur die Arbeitstage pro Woche bei gleichbleibenden Wochenstunden, nennt der Verlauf/Bericht zwar zusätzlich die neue Arbeitstage-Zahl (z. B. „ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage") – aber die Wochenstundenzahl selbst bleibt unverändert, das Tagessoll verschiebt sich trotzdem still (z. B. 40 h auf 5 Tage → 40 h auf 4 Tage: 8 h/Tag → 10 h/Tag). Verschieben Sie bei „Nach Tagen" oder „Nach Arbeitsblöcken" Stunden auf einen anderen Wochentag, ohne die Wochensumme zu ändern, bleibt das Tagessoll der übrigen Tage gleich – hier ändert sich stattdessen der <strong>Urlaubsverbrauch</strong>: ein am wegfallenden Wochentag bereits gebuchter Urlaubstag zählt rückwirkend nicht mehr. Vor dem Speichern deshalb immer die Auswirkung prüfen, nicht nur die angezeigte Wochenstundenzahl.</p>
        <p><strong>Erster/Letzter Arbeitstag</strong> begrenzen die Soll-Berechnung: vor dem Eintritt bzw. nach dem Austritt entsteht kein Stundensoll. Die Übersicht zeigt je MA Urlaubskonto <strong>und</strong> Überstundensaldo (Jahr bis heute; „—" ohne Stundenzählung).</p>
        <p className="text-amber-700">⚠️ Bei <strong>unterjährigem Eintritt</strong> (nicht seit 1. Januar im System) den „Ersten Arbeitstag" unbedingt setzen – sonst zählt das Soll auch Tage vor dem Eintritt und es entstehen Phantom-Minusstunden.</p>
        <p><strong>Arbeitszeit-Blöcke:</strong> Tagessoll, Kappung (auch zwischen den Blöcken), Anerkennen und Rückwirkung beschreibt Abschnitt 3. Frühere Soll-Fenster laufen als „Arbeitszeit-Fenster (Altbestand, nur Kappung)" weiter.</p>
        <p><strong>Minijob / Arbeitszeitkonto (§ 2 Abs. 2 MiLoG):</strong> Für Minijobber:innen auf Arbeitszeitkonto aktivieren Sie im Formular die Checkbox „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)" und tragen optional die „Vereinbarte Monatsarbeitszeit (h)" ein (leer = automatisch aus Wochenstunden × 13/3). Zusätzlich aktivierbar: „<strong>Feste Monatsarbeitszeit</strong>" – dann ist das Monats-Soll jeden Monat fix die vereinbarte Monatszeit, statt aus Wochenstunden/Arbeitstagen zu schwanken (setzt das Arbeitszeitkonto und eine eingetragene Monatszeit voraus). Details zu den weichen MiLoG-Warnungen und zur festen Monatsarbeitszeit: Abschnitt „Eigene Abwesenheitsgründe, Kind krank &amp; Minijob".</p>
        <p><strong>Kalenderfarbe:</strong> Im Benutzerformular können Sie die Kalenderfarbe aus einer Palette für jede:n Mitarbeiter:in vorgeben (Badge-Ring im Teamkalender); der/die Mitarbeiter:in kann sie auch selbst im Profil ändern.</p>
        <p><strong>Monatsjournal:</strong> Das Buch-Symbol in der Aktionsspalte öffnet das Monatsjournal des/der Mitarbeitenden. Die Überschrift trägt den Namen – <strong>„Monatsjournal: Vorname Nachname"</strong> –, damit beim Wechsel zwischen Personen sofort klar ist, wessen Journal angezeigt wird. Einträge lassen sich dort auch an Wochenend- und Feiertagen anlegen und bearbeiten (z. B. KV-Dienst am Sonntag). An Sonn- und Feiertagen erscheint dabei das Feld <strong>„Ausnahmegrund (§10 ArbZG)"</strong>; der Grund steht danach unter der Uhrzeit und in den Exporten.</p>
        <p><strong>Login als … (Ansicht als Mitarbeiter:in):</strong> Das Anmelde-Symbol in der Aktionsspalte (nur bei aktiven Mitarbeitenden) öffnet die App aus deren Sicht – nützlich, um das Mitarbeiter-Dashboard zu prüfen oder ein Problem nachzustellen. Die Ansicht ist <strong>ausschließlich lesend</strong>: Stempeln, Anträge und alle Änderungen sind gesperrt. Ein Hinweisbanner oben zeigt dauerhaft „Sie sehen PraxisZeit als … – nur Lesen"; über <strong>„Zurück zu Admin"</strong> kehren Sie zu Ihrem Konto zurück. Jede solche Sitzung wird protokolliert (wer, wen, wann – DSGVO-Rechenschaftspflicht).</p>
        <p><strong>DSGVO: Anonymisierung &amp; endgültige Löschung (Art. 17):</strong> Ablauf <strong>Deaktivieren → 14-Tage-Sperrfrist → Anonymisieren → endgültig löschen</strong>. <strong>Anonymisieren</strong> (nach der Sperrfrist) entfernt persönliche Daten (Name, E-Mail, Lichtbild, 2FA); die <strong>Zeiteinträge bleiben</strong> erhalten (§16 ArbZG), Abwesenheiten werden gelöscht. <strong>Endgültig löschen (Purge)</strong> löscht den Benutzer samt aller Daten unwiderruflich – erst möglich, wenn die jüngste aufbewahrungspflichtige Aufzeichnung <strong>mindestens 730 Tage</strong> alt ist (sonst blockiert das System). Anonymisierte Nutzer können also erst nach Ablauf der 730 Tage endgültig gelöscht werden; beide Vorgänge werden im Änderungsprotokoll vermerkt.</p>
      </div>
    ),
  },
  {
    title: '3. Arbeitszeit-Blöcke, Rückwirkung & Anerkennen',
    content: (
      <div className="space-y-2">
        <p><strong>Arbeitszeit-Blöcke (ab 1.20.0):</strong> Je Mitarbeiter:in und Wochentag (Mo–Fr) bis zu drei Blöcke „von–bis" (5-Minuten-Raster, nicht überlappend, nicht aneinanderstoßend, nicht über Mitternacht) plus <strong>„Pause innerhalb der Blöcke"</strong>. <strong>Tagessoll = Summe der Blockdauern − Pause innerhalb der Blöcke</strong> (08:00–12:00 + 15:00–18:00 mit 30 Min. Pause = 6:30 h); Wochenstunden, Tagesstunden und Arbeitstage werden abgeleitet, ein Wochentag ohne Block ist kein Arbeitstag. Gepflegt nur mit Wirkungsdatum über <strong>„Arbeitszeit anpassen…"</strong> (Dialog <strong>„Arbeitszeit &amp; Wochenstunden"</strong>, Modus <strong>„Nach Arbeitsblöcken"</strong>, je Tag live mit Gesamtzeit, Pause und Tagessoll; bei fester Monatsarbeitszeit steht „geplant" statt „Tagessoll" bzw. „Wochensoll" – die Werte sind dann geplante Anwesenheit, die Auswirkung nennt sie „Geplante Anwesenheit je Wochentag"); beim Anlegen steht derselbe Modus im Formular.</p>
        <p><strong>Anrechnung:</strong> Gestempelte Zeit vor dem ersten, nach dem letzten und zwischen den Blöcken wird nicht angerechnet – mit dem Puffer (Standard 15 Min.) an <strong>jedem</strong> Blockrand. Beispiel: Blöcke 08:00–12:00 + 15:00–18:00, durchgestempelt 08:00–18:00 → angerechnet <strong>08:00–12:15 und 14:45–18:00 = 7:30 h</strong>, die Lücke 12:15–14:45 (2:30 h) nicht; die Stempel bleiben gespeichert (§16 ArbZG). Eine Lücke bis zum doppelten Puffer wird voll angerechnet – eine geplante Pause deshalb als „Pause innerhalb der Blöcke" erfassen, nicht als kurze Lücke. Keine Kappung an Tagen ohne Block, an Wochenenden, Feiertagen und „freien" Sondertagen („halber Feiertag" behält die Blöcke), bei Mitarbeitenden ohne Stundenzählung und bei anerkannten Einträgen; §18-befreite werden trotzdem gekappt. Bis 1.19.2 wurde ein Feiertag auf einem Werktag gekappt; einen solchen Eintrag rechnet ein unverändertes Speichern im Admin-Dashboard oder Monatsjournal mit der gestempelten Zeit neu. Ebenso nach einer <strong>nachträglichen</strong> Änderung, ob ein Tag frei ist (eigener Feiertag angelegt, verschoben oder gelöscht, Bundesland gewechselt, Sondertag zwischen „frei" und Arbeitstag umgestellt): bestehende Einträge dieser Tage rechnet PraxisZeit nicht von selbst neu, sondern nennt sie nach dem Speichern (<em>„Zeiteinträge an geänderten Tagen behalten ihre bisherige Anrechnung gegen die Arbeitszeit-Blöcke …"</em>); unverändert speichern berechnet sie neu – fehlt dann eine gesetzliche Pause (etwa bei einem über die Blocklücke durchgestempelten Dienst, dessen Tag frei wurde), ergänzen Sie sie. Die Kappung greift an allen Wegen (Stempeln, eigene Einträge, Korrekturen, genehmigte Anträge, XLS-Import – dort schon in der Vorschau sichtbar: „Netto" ist die angerechnete Zeit, darunter steht die nicht angerechnete, die Zeile trägt das Kennzeichen „Hinweis").</p>
        <p><strong>Vergessen auszustempeln:</strong> Ein automatisch (um 23:59) geschlossener Eintrag eines vergangenen Tages wird nur bis zum letzten Block plus Puffer angerechnet und ist als „automatisch geschlossen" gekennzeichnet; das automatische 23:59 gilt nicht als Stempel. Tragen Sie das tatsächliche Ende ein (Mitarbeitende per Änderungsantrag), entfällt die Kennzeichnung. Auch ein tatsächliches Ende um 23:59 (z. B. nach einem Spät- oder Notdienst) lässt sich eintragen – es gilt dann als echter Stempel, wird wie jedes andere Ende gegen die Blöcke gekappt und nach „Anerkennen" bis 23:59 angerechnet. (Hat das automatische Schließen nichts gekappt, etwa an einem Tag ohne Blöcke, steht als Ende schon 23:59; ein erneut gespeichertes 23:59 ist davon nicht zu unterscheiden, die Kennzeichnung bleibt.) Ebenso bleibt die Kennzeichnung, wenn das eingetragene Ende genau dem angerechneten Ende entspricht (z. B. 18:15) – auch wenn die Person tatsächlich um diese Zeit gegangen ist: PraxisZeit kann es nicht vom automatisch gesetzten Wert unterscheiden; „Anerkennen" bzw. „Anrechnung beantragen" ist für diesen Eintrag dann nicht möglich.</p>
        <p><strong>Hinweise beim Speichern</strong> (blockieren nie): z. B. <em>„Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt (Beginn 07:37 → 07:45; Puffer 15 Minuten)."</em> oder <em>„Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."</em> Bei einem Blockbeginn zur vollen Stunde und dem Standardpuffer landet eine zu frühe Eingabe auf <code>hh:45</code> – das ist die Grenze aus Block und Puffer, keine Rundung. <strong>Pausen:</strong> Bleiben von der Lücke nach Abzug des Puffers mindestens 15 Min., zählen sie für §4 ArbZG als Pause; wird zusätzlich eine Pause eingetragen, obwohl über die Lücke durchgestempelt wurde, wird beides abgezogen („Pause in der Lücke wird zusätzlich abgezogen: …").</p>
        <p><strong>Sichtbar und anerkennbar:</strong> Unter jedem gekappten Eintrag (Admin-Dashboard, Monatsjournal, Zeiterfassung) steht z. B. <em>„gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet"</em>; das Journal summiert „Anwesenheit nicht angerechnet", die Exporte haben die letzte Spalte <strong>„Nicht angerechnet (Min)"</strong>. Mit <strong>„Anerkennen"</strong> (Admin-Dashboard-Detail, Monatsjournal) zählt die ganze gestempelte Zeit – dauerhaft, auch nach späteren Neuberechnungen und Zeitänderungen, ohne Rücknahme, protokolliert als „Anrechnung anerkannt". Steht am selben Tag zusätzlich eine Abwesenheit (z. B. vormittags gearbeitet, dann krank), wird deren Gutschrift angeglichen: Arbeit und Gutschrift zusammen überschreiten das Tagessoll nicht, gleich ob zuerst gebucht oder zuerst anerkannt wird (im Protokoll z. B. „Krank 4,0 h — an die anerkannte Arbeitszeit des Tages angeglichen"). Ein offener Eintrag lässt sich erst nach dem Ausstempeln anerkennen, ein automatisch geschlossener erst mit eingetragenem tatsächlichem Ende; Anerkennen blockiert nie an §3/§4 ArbZG (Verstöße erscheinen als Hinweis); auch danach lässt sich ein solcher Eintrag bearbeiten bzw. per Änderungsantrag ändern, solange Datum, Zeiten und Pause gleich bleiben (z. B. nur die Notiz) – geänderte Zeiten oder Pause werden wieder voll geprüft. Mitarbeitende beantragen das über „Anrechnung beantragen"; die Antragsprüfung bietet dann „Genehmigen und anerkennen" oder „Ohne Anerkennen genehmigen", bei anderen Anträgen zu Einträgen mit nicht angerechneter Zeit neben „Genehmigen" zusätzlich „Genehmigen und anerkennen" (Abschnitt 5).</p>
        <p><strong>Altbestand:</strong> Frühere Soll-Fenster laufen als „Arbeitszeit-Fenster (Altbestand, nur Kappung)" weiter – sie kappen wie vorher (neu auch automatisch geschlossene Einträge), ändern das Soll aber nicht – und lassen sich im Dialog über „In Arbeitszeit-Blöcke umwandeln" oder „Fenster entfernen" ablösen.</p>
        <p><strong>Rückwirkend ändern:</strong> Die Auswirkung zeigt vorab die neu berechneten Einträge je Monat (alt → neu), übersprungene Einträge mit Grund, angepasste Abwesenheiten und getrennt Δ Soll, Δ angerechnete Zeit, Δ Überstundenkonto und Urlaubsverbrauch; der Haken „Ich habe die Auswirkungen geprüft und möchte speichern" ist Pflicht, sobald etwas betroffen ist. Neu gekappt wird ab dem Rohstempel, nur an geänderten Wochentagen und mit dem aktuellen Puffer (Einträge ohne Rohstempel werden nicht verlängert, „nicht erweiterbar"); offene Einträge vergangener Tage werden vorher automatisch geschlossen und zählen beim Überstundenkonto schon unter „bisher" (die Differenz zeigt nur die Wirkung der Änderung). Kranken- und Fortbildungstage aus der Zeit vor 1.20.0, die an einem Wochentag ohne Soll noch ihre alten Stunden tragen, setzt jede Änderung, deren Wirkungsbereich sie umfasst, auf 0 – auch an einem unveränderten Wochentag; liegt der Tag in der Vergangenheit, sinkt dabei das Überstundenkonto, und es gilt der Verkürzungsschutz („Ab heute" lässt solche vergangenen Tage unverändert). Abwesenheiten von vor dem Update auf 1.10.0 (per Änderungsantrag: vor 1.16.0) stellt PraxisZeit nie um, auch nicht auf 0 – ein solcher Kranken- oder Fortbildungstag an einem Wochentag ohne Soll zählt weiter zum Überstundenkonto und lässt sich nur von Hand bereinigen (Abwesenheit löschen). Je Eintrag entsteht eine Protokollzeile „Neukappung (Arbeitszeit-Änderung)", je Änderung eine Sammelzeile. Ein Wechsel zu „Gleichmäßig" oder „Nach Tagen" beendet die Blöcke ab dem Wirkungsdatum; ab dann wird nicht mehr gekappt (bei Mitarbeitenden ohne Stundenzählung enden gespeicherte Blöcke mit der nächsten Arbeitszeit-Änderung). Mitarbeitende sehen nach jeder Änderung – auch „ab heute", zukunftsdatiert, zurückgesetzt oder gelöscht – 30 Tage lang den Kasten „Hinweis zu Ihrer Arbeitszeit" auf ihrem Dashboard; bei einer Verkürzung nennt er nur den Grundtyp, nie die Begründung.</p>
        <p className="text-amber-700"><strong>Verkürzung</strong> = ein Eintrag verliert angerechnete Zeit, <strong>oder</strong> das Überstundenkonto sinkt (auch durch ein rückwirkend höheres Soll oder ein höheres Soll für den heutigen Tag, während die Person eingestempelt ist), <strong>oder</strong> eine Misch-Tag-Gutschrift sinkt stärker als das Tagessoll. Standard ist dann „Ab heute (…) wirksam – vergangene Einträge bleiben unverändert" (ab dem frühesten Datum ohne Verlust: meist heute, sonst morgen). Rückwirkend nur mit Grund („Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)" / „Mit der beschäftigten Person vereinbart" / „Sonstiges"), Begründung (10 bis 400 Zeichen) und Bestätigung; im Protokoll als [Erfassungsfehler korrigiert] / [Einvernehmlich vereinbart] / [Sonstiges]. Grund, Begründung und Notiz teilen sich das Notizfeld der Änderung („Notiz und Begründung zusammen höchstens 500 Zeichen."). Unter der Grund-Auswahl steht: „Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit." Falsch gestempelte Zeiten korrigieren Sie also am Eintrag selbst (Admin-Dashboard bzw. Monatsjournal; Mitarbeitende per Änderungsantrag); eine rückwirkende Arbeitszeit-Änderung berichtigt nur eine falsch <strong>hinterlegte</strong> Arbeitszeit. In abgeschlossene Jahre gesperrt. Seit 1.20.0 gilt das auch für eine rückwirkende Erhöhung der Wochenstunden oder des Tagesplans, die das Konto senkt.</p>
        <p><strong>Löschen:</strong> Das Papierkorb-Symbol steht nur an der jüngsten Zeile des Verlaufs; ältere Zeilen lassen sich erst löschen, wenn die späteren gelöscht sind. Das Löschen rechnet Einträge und Abwesenheiten zurück. Verkürzt es, ist der Standard „Ab … auf den vorherigen Stand zurücksetzen" (Knopf „Zurücksetzen": eine neue Verlaufszeile mit dem vorherigen Stand, vergangene Einträge bleiben unverändert); alternativ „Rückwirkend löschen mit Neuberechnung" mit Grund, Begründung und Bestätigung. Wurde inzwischen eine weitere Änderung dazwischen angelegt (z. B. in einem zweiten Fenster), lehnt PraxisZeit die Rücksetzung ab: <em>„Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."</em></p>
        <p><strong>Puffer</strong> (Einstellungen → „Soll-Arbeitszeit-Fenster", Feld „Puffer für Soll-Arbeitszeit-Fenster (Min.)", Standard 15, zulässig 0 bis 1439 Minuten): Eine Änderung des Puffers wirkt auf neue Einträge. Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn, auch wenn er später bearbeitet wird. Nur eine Arbeitszeit-Änderung mit Neuberechnung kappt die betroffenen Einträge mit dem dann gültigen Puffer neu; die Vorschau nennt ihn, und verliert dabei ein Eintrag angerechnete Zeit, gilt der Verkürzungsschutz. Einträge aus der Zeit vor Version 1.20.0 tragen keinen gespeicherten Puffer und werden bei einer Bearbeitung mit dem aktuellen Puffer gekappt. Bereits gespeicherte Einträge ändern sich durch das Speichern dieser Einstellung allein nicht.</p>
        <p className="text-gray-500"><strong>Bekannte Grenze:</strong> Arbeit in der Lücke bleibt in der angerechneten Zeit unsichtbar, bis sie anerkannt wird. Die Nachtarbeits-Erkennung (§6 ArbZG) rechnet weiter mit den gekappten Zeiten; eine Erkennung auf den Rohstempeln folgt separat.</p>
        <p className="text-gray-700"><strong>Vergütung:</strong> Nichtanrechnung ersetzt keine Vergütungsentscheidung. Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde oder zur Erledigung der Arbeit notwendig war, ist zu vergüten (§ 611a Abs. 2, § 612 Abs. 1 BGB; MiLoG). Wurde vor, nach oder zwischen den Blöcken gearbeitet, nutzen Sie „Anerkennen"; wurde nur ein Teil gearbeitet, den Eintrag aufteilen oder korrigieren statt die ganze Zeit anzuerkennen.</p>
        <p className="text-gray-700"><strong>Arbeitsrecht und Mitbestimmung:</strong> Ändert sich durch die Blöcke der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und braucht das Einverständnis der beschäftigten Person (sonst Änderungskündigung, § 2 KSchG; bei Teilzeit §§ 8, 9 TzBfG). Die Lage kann, soweit der Vertrag sie nicht festlegt, im Rahmen des Direktionsrechts (§ 106 GewO) nach billigem Ermessen und mit angemessener Ankündigung nur für die Zukunft geändert werden (Arbeit auf Abruf: mindestens 4 Tage vorher, § 12 Abs. 3 TzBfG). Vereinbarte Arbeitszeiten und Ruhepausen sind wesentliche Vertragsbedingungen (§ 2 Abs. 1 Satz 2 Nr. 7 NachwG); eine Änderung ist spätestens am Tag des Wirksamwerdens schriftlich mitzuteilen (§ 3 NachwG). Mit Betriebsrat sind Lage, Verteilung und Pausen (§ 87 Abs. 1 Nr. 2 BetrVG), vorübergehende Änderungen der betriebsüblichen Arbeitszeit (Nr. 3) und die Kappung als technische Einrichtung (Nr. 6) mitbestimmungspflichtig; ohne Zustimmung ist die Maßnahme gegenüber den Beschäftigten unwirksam. PraxisZeit prüft das nicht.</p>
        <p className="text-gray-500">Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG: 30 Min Pause ab 4,5 h, 60 Min ab 6 h, höchstens 4,5 h ohne Pause, Schichtzeit inklusive Lücke höchstens 10 h); PraxisZeit prüft diese nicht.</p>
      </div>
    ),
  },
  {
    title: '4. Berichte & Exporte',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> stehen drei Export-Typen bereit: <strong>Monatsreport</strong> (Gehaltsabrechnung), <strong>Jahresreport Classic</strong> (12 Monate kompakt) und <strong>Jahresreport Detailliert</strong> (365 Tage, für Steuerberater). Jeder Report ist als <strong>Excel (.xlsx)</strong> und <strong>ODS (.ods)</strong> verfügbar; den Monatsreport gibt es zusätzlich als <strong>PDF (.pdf)</strong>.</p>
        <p><strong>Tageszeilen lesen:</strong> <strong>Netto</strong> ist die angerechnete Arbeitszeit der Zeiteinträge – bei Arbeitszeit-Blöcken die Zeit nach der Kappung („Von"/„Bis" zeigen die vor dem ersten bzw. nach dem letzten Block gekürzten Zeiten, Zeit zwischen den Blöcken ist von Netto abgezogen; der ursprüngliche Stempel bleibt in PraxisZeit gespeichert, steht aber nicht in der Datei). <strong>Differenz</strong> ist der Saldo des Tages – Netto plus Gutschrift für Krankheit/Fortbildung minus Soll; ein Krank- oder Fortbildungstag steht deshalb bei ±0, und die Summe der Spalte ergibt den „Saldo Monat". Ausnahme: Mitarbeitende mit fester Monatsarbeitszeit (Minijob-Modus) – dort ist nur die Zusammenfassung verbindlich. Bei <strong>geteilten Diensten</strong> (mehrere Einträge an einem Tag) zeigen Excel/ODS in „Von"/„Bis" den Rahmen des Tages und in den hinten angehängten Spalten <strong>Unterbrechung (Min)</strong> und <strong>Zeiteinträge</strong> die Zeit zwischen den Einträgen bzw. die einzelnen Einträge; damit gilt Bis − Von − Pause − Unterbrechung = Netto, solange nichts zwischen zwei Arbeitszeit-Blöcken gestempelt wurde (sonst ist Netto um diese Lückenzeit kleiner). Ausnahmen: Überschneiden sich zwei Einträge, zählt Netto die Überschneidung doppelt (die Spalte „Zeiteinträge" zeigt sie); läuft ein Eintrag noch, fehlt seine Zeit in Netto und in „Bis"; außerhalb des Beschäftigungszeitraums ist Netto 0. Im PDF stehen die Einträge in „Von"/„Bis" untereinander, die Unterbrechung direkt neben der Pause. Letzte Spalte in allen Formaten (ab 1.20.0): <strong>Nicht angerechnet (Min)</strong> – die Zeit zwischen den Blöcken plus die vor dem ersten bzw. nach dem letzten Block abgeschnittene Zeit (Beispiel 07:00–19:00 bei Blöcken 08–12 + 15–18: Von 07:45, Bis 18:15, Netto 8,00, Nicht angerechnet 240). Die Abendzeit eines automatisch auf 23:59 geschlossenen Eintrags zählt dort nicht mit, ein anerkannter Eintrag hat 0; die Zusammenfassung nennt die Summe des Monats, der Jahresreport Detailliert je Mitarbeiter:in die Summe des Jahres.</p>
        <p>Mit der Checkbox <strong>„Krankheitsdaten einschließen" (Art. 9 DSGVO)</strong> nehmen Sie Krankheitsstunden/-tage mit in den Export auf. Krankheitsdaten sind besondere Kategorien personenbezogener Daten; jeder Export mit dieser Option wird im Änderungsprotokoll vermerkt.</p>
        <p>Aufbewahrungspflicht: <strong>2 Jahre</strong> (§16 ArbZG). Regelmäßig exportieren und sicher archivieren.</p>
      </div>
    ),
  },
  {
    title: '5. Korrekturanträge genehmigen',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Änderungsanträge</strong> sehen Sie alle offenen Anträge. Antrag öffnen → Alt- und Neuwerte vergleichen → Begründung lesen → <strong>Genehmigen</strong> oder <strong>Ablehnen</strong> (mit optionalem Grund).</p>
        <p>Bei Genehmigung wird der Zeiteintrag sofort geändert. Der Mitarbeiter sieht den Status unter Zeiterfassung → Tab „Anträge".</p>
        <p><strong>Ein- oder Austritt nachträglich eingetragen:</strong> Die Genehmigung prüft den Beschäftigungszeitraum erneut – liegt der Tag eines neuen oder verschobenen Eintrags vor dem ersten bzw. nach dem letzten Arbeitstag, lehnt PraxisZeit sie ab („Datum liegt nach dem letzten Arbeitstag"). Die Korrektur eines bestehenden Eintrags an dessen Tag bleibt genehmigbar.</p>
        <p><strong>Mehrere Anträge auf einmal:</strong> offene Anträge über die Kästchen markieren und gemeinsam genehmigen oder ablehnen. Hinweise wie bei der Einzel-Genehmigung (Kappung, Wochen-/Nachtarbeitszeit, Kind-krank-Kontingent) erscheinen auch dabei, jeweils mit dem Namen der Person.</p>
        <p><strong>Anrechnung beantragt (ab 1.20.0):</strong> Ein Antrag über „Anrechnung beantragen" trägt das Kennzeichen „Anrechnung beantragt" und hat zwei Knöpfe: <strong>„Genehmigen und anerkennen"</strong> – die beantragten Zeiten (vorbelegt sind die gestempelten) werden ungekappt angerechnet, dauerhaft – oder <strong>„Ohne Anerkennen genehmigen"</strong> – nur die beantragten Zeiten werden übernommen, die Zeit vor, nach oder zwischen den Blöcken bleibt nicht angerechnet. Die Prüfung nennt unter „Aktuell" die nicht angerechnete Lücke und die Stempel des Eintrags; weichen die beantragten Zeiten davon ab, steht das rot unter „Gewünscht". Übernimmt ein Antrag die angerechneten Zeiten unverändert (etwa weil er nur Pause oder Notiz korrigiert), ist das keine Abweichung: Die Genehmigung rechnet dann mit den Stempeln weiter, auch beim Anerkennen. Bei anderen Anträgen zu Einträgen mit nicht angerechneter Zeit gibt es neben „Genehmigen" zusätzlich <strong>„Genehmigen und anerkennen"</strong> (bei einem automatisch geschlossenen Eintrag nur, wenn der Antrag ein tatsächliches Ende enthält). Die Sammel-Genehmigung nennt die Zahl der Anrechnungsanträge und fragt vor dem Absenden nach („Alle genehmigen"); einen davon ohne Anerkennen zu genehmigen geht nur einzeln. Ist der Eintrag schon anerkannt, zeigt die Prüfung „Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet."</p>
      </div>
    ),
  },
  {
    title: '6. Urlaubsanträge & Betriebsferien',
    content: (
      <div className="space-y-2">
        <p><strong>Urlaubsanträge:</strong> Toggle „Genehmigungspflicht" aktiviert den Workflow. Anträge erscheinen als „Offen" → Genehmigen (grün) oder Ablehnen (rot, optional Grund). <strong>„Arbeitstage"</strong> auf der Antragskarte ist genau das, was die Genehmigung danach verbucht: nur Tage, an denen die Person laut ihrem zum jeweiligen Datum gültigen Arbeitsplan arbeitet (4-Tage-Woche mit freiem Mittwoch: Mo–Fr = 4 Tage), ohne Wochenenden, Feiertage und „frei"-Sondertage; ein halber Tag und ein „halber Feiertag" (24./31.12.) zählen je 0,5. Tage nach einem inzwischen eingetragenen letzten Arbeitstag zählen nicht mit – ein solcher Antrag lässt sich so aber nicht genehmigen (Fehlermeldung), vorher über „Bearbeiten" auf den Beschäftigungszeitraum kürzen. Bis 1.19.3 zählte die Anzeige stumpf Mo–Fr. Die Genehmigung ersetzt Zeiteinträge nur an den gebuchten Tagen; an freien Tagen (z. B. eine Vertretung am freien Wochentag) bleiben sie stehen. Zeigt die Karte <strong>0</strong>, lehnt PraxisZeit die Genehmigung ab (z. B. „Für ‹Tage› sind 0 Stunden geplant — an einem Tag ohne geplante Arbeitszeit kann keine Abwesenheit gebucht werden.") und der Antrag bleibt offen – ablehnen oder über „Bearbeiten" anpassen. Dasselbe gilt für eine direkt eingetragene Abwesenheit: gebucht wird nur an Arbeitstagen, ein Zeitraum ganz ohne geplante Arbeitszeit wird abgelehnt. <strong>Stornieren:</strong> Im Filter „Genehmigt" lässt sich ein genehmigter Antrag über <strong>„Urlaub stornieren"</strong> rückgängig machen, solange der Zeitraum noch nicht begonnen hat – die erzeugten Abwesenheiten werden dabei <strong>automatisch entfernt</strong>, der Antrag wird auf „Zurückgezogen" gesetzt.</p>
        <p><strong>Betriebsferien:</strong> Abwesenheiten → Tab „Betriebsferien" → Neue Betriebsferien. Alle aktiven Mitarbeiter mit der Option „Nimmt an Betriebsferien teil" (Standard, rollenunabhängig) erhalten automatisch Einträge an ihren <strong>Arbeitstagen</strong>. <strong>Nicht gebucht</strong> wird an Wochenenden, Feiertagen, freien Wochentagen (Teilzeit), in Zeiträumen mit 0 Wochenstunden (z. B. Elternzeit; ältere Einträge an solchen Tagen entfernt ein erneutes Speichern der Betriebsferien), an „Frei"-Sondertagen (24./31.12.), außerhalb des Beschäftigungszeitraums (noch nicht eingetreten / bereits ausgetreten) sowie an Tagen mit bereits vorhandener Abwesenheit. Nachträglich Berechtigte: Option setzen – die Einträge werden automatisch für laufende und künftige Betriebsferien nachgetragen. Beim Löschen werden alle Einträge entfernt. Ändern Anlegen, Speichern oder Löschen Buchungen in einem Jahr mit Jahresabschluss (z. B. entfernt das erneute Speichern alte Einträge mit 0 Stunden), weist PraxisZeit auf den veralteten Übertrag hin („Jahresabschluss 2026 bereits erfolgt — Carryover 2027 ist nun veraltet, bitte Jahresabschluss erneut ausführen.") – den Übertrag unter Jahresabschluss prüfen und ggf. von Hand korrigieren; er wird nie automatisch neu berechnet.</p>
        <p><strong>Verrechnung</strong> (beim Anlegen wählbar): <strong>„Als Urlaub werten"</strong> (Standard) zieht je Schließtag 1 Urlaubstag vom Konto ab; <strong>„Bezahlte Freistellung"</strong> ist saldoneutral – kein Urlaubsabzug, keine Auswirkung aufs Überstundenkonto (wie ein Feiertag).</p>
        <p className="text-gray-700"><strong>Betriebsferien länger als der Jahresurlaub:</strong> Sind als Urlaub zählende Betriebsferien länger als das Resturlaub-Budget, entstehen standardmäßig <strong>Minus-Urlaubstage</strong>. Unter <strong>Einstellungen → „Betriebsferien &amp; Urlaub"</strong> aktivieren Sie optional <strong>„Überzählige Betriebsferien als Überstundenabbau"</strong>: dann wird zuerst der Urlaub aufgezehrt und die überzähligen Tage werden als Überstundenausgleich gebucht (Konto darf ins Minus) – statt Minus-Urlaub. Global, Standard <strong>aus</strong>. Die Zuteilung erfolgt <strong>chronologisch nach Datum</strong> (frühere Schließung zuerst, Überstunden-Tage auf die letzte des Jahres), unabhängig von der Eingabereihenfolge; privater Urlaub wird zuerst verbraucht. Wirkt beim Anlegen/erneuten Speichern – für bestehende Betriebsferien einmal öffnen und neu speichern.</p>
        <p className="text-gray-700"><strong>Urlaubsberechnung (Tagesprinzip, §3 BUrlG):</strong> Urlaub wird nach Arbeitstagen geführt – ein freier Arbeitstag = <strong>1 Urlaubstag</strong>, unabhängig von Tagesstunden und Wochentag (auch bei individuellen Tagesstunden). Jahresanspruch anteilig: <code>30 × Arbeitstage ÷ 5</code> (überschreibbar beim Anlegen). Verbrauch wird tagebasiert gezählt, intern gespeicherte Stunden dienen nur der Soll-/Ist-Berechnung.</p>
      </div>
    ),
  },
  {
    title: '7. Sondertage 24./31.12.',
    content: (
      <div className="space-y-2">
        <p>Heiligabend (24.12.) und Silvester (31.12.) sind keine gesetzlichen Feiertage. Unter <strong>Einstellungen → „Sondertage (24./31.12.)"</strong> legen Sie für <strong>jeden</strong> der beiden Tage getrennt fest, wie er behandelt wird:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li><strong>Normaler Arbeitstag</strong> – kein Sonderverhalten.</li>
          <li><strong>Frei</strong> – arbeitsfrei, kein Stundensoll. Im Kalender grau, nicht buchbar.</li>
          <li><strong>Halbtag</strong> – halbes Tagessoll. Im Kalender amber/gelb.</li>
        </ul>
        <p>Die Einstellung wirkt direkt auf Soll-Berechnung und Kalenderdarstellung bei allen Mitarbeitenden – in <strong>allen</strong> Jahren, auch zurückliegenden. Ändert sie ein Jahr, für das der Jahresabschluss schon erfolgt ist, weist PraxisZeit nach dem Speichern auf den veralteten Übertrag hin; den Übertrag unter „Jahresabschluss“ prüfen und ggf. von Hand korrigieren. Wechselt ein Tag zwischen „Frei" und Arbeitstag bzw. Halbtag, nennt PraxisZeit außerdem bestehende Zeiteinträge an diesem Tag, deren Anrechnung gegen die Arbeitszeit-Blöcke sich ändern müsste – unverändert neu speichern berechnet sie neu.</p>
      </div>
    ),
  },
  {
    title: '8. Pflicht-Pause-Ausnahme (§4 ArbZG)',
    content: (
      <div className="space-y-2">
        <p>Konnte eine vorgeschriebene Pause (§4 ArbZG: 30 Min. ab 6h, 45 Min. ab 9h) nicht eingelegt werden, kann ein Eintrag mit einer <strong>dokumentierten Pflicht-Begründung</strong> erfasst werden, statt blockiert zu werden. Die Begründung landet im Änderungsprotokoll (Quelle „break_waiver").</p>
        <p>Geprüft wird der <strong>ganze Tag</strong>: alle Einträge zusammen, Lücken unter 15 Min. sind keine Pause (§4 Satz 2) – aneinandergereihte Einträge zählen wie ein durchgehender Eintrag. Das gilt seit #499 auch beim <strong>Ausstempeln</strong>: ohne ausreichende Pause oder Begründung wird nicht ausgestempelt.</p>
        <p>Mit <strong>„Ausnahme ‚Pflicht-Pause war nicht möglich' erlauben"</strong> (Standard: an) legen Sie fest, ob es die Ausnahme überhaupt gibt. <strong>Aus</strong> → die Auswahl verschwindet beim Ausstempeln, in Zeiterfassung, Monatsjournal und Anträgen, und der Server lehnt Ausnahmen ab (auch von Admins). Ein Tag über 6/9 h lässt sich dann nur mit eingetragener Pause speichern. Bestehende Ausnahmen bleiben; offene Ausnahme-Anträge gelten danach als Anträge ohne Ausnahme – genehmigen lassen sie sich nur noch, wenn die Pause des Tages jetzt reicht (sonst ablehnen).</p>
        <p>Ist die Ausnahme erlaubt, stellen Sie den Schalter <strong>„Genehmigung erforderlich"</strong> unter <strong>Einstellungen → „Pflicht-Pause-Ausnahme"</strong> ein. Er gilt für Ausnahmen, die Mitarbeitende in der <strong>Zeiterfassung</strong> (Eintrag anlegen oder bearbeiten) begründen:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li><strong>Aus</strong> – die Ausnahme wird sofort wirksam.</li>
          <li><strong>Ein</strong> – der Eintrag wird erst nach Admin-Genehmigung wirksam.</li>
        </ul>
        <p><strong>Beim Ausstempeln</strong> wirkt eine Begründung immer <strong>sofort</strong>, auch bei eingeschalteter Genehmigungspflicht – der Eintrag muss geschlossen werden, weil die Zeit bereits geleistet ist (§16 ArbZG). Diese Ausnahmen prüfen Sie im Änderungsprotokoll (Quelle „break_waiver"). Soll beim Ausstempeln gar keine Ausnahme möglich sein, schalten Sie die Ausnahme ganz ab. Änderungsanträge gehen ohnehin immer zur Genehmigung; Korrekturen durch Admins wirken sofort.</p>
        <p>Bearbeiten Mitarbeitende einen Eintrag, ohne Datum, Zeiten oder Pause zu ändern (z. B. nur die Notiz), ist das keine neue Ausnahme: Der Eintrag wird sofort gespeichert, eine schon dokumentierte Begründung bleibt unverändert stehen – auch bei Genehmigungspflicht oder abgeschalteter Ausnahme. Erst eine geänderte Begründung, Zeit oder Pause wird wieder nach §4 geprüft.</p>
        <p className="text-gray-700"><strong>4-Augen-Prinzip:</strong> Ist die Genehmigungspflicht aktiv, darf ein Admin seine <strong>eigene</strong> Pflicht-Pause-Ausnahme nicht selbst genehmigen – sie muss von einer zweiten Person geprüft werden.</p>
      </div>
    ),
  },
  {
    title: '9. Eigene Abwesenheitsgründe, Kind krank & Minijob',
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
    title: '10. ArbZG-Berichte & Compliance',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Berichte</strong> (nach unten scrollen) finden Sie: <strong>§5 Ruhezeitverstöße</strong> (&lt;11h zwischen Arbeitstagen), <strong>§6 Nachtarbeit</strong> (≥48 Nachtarbeitstage/Jahr), <strong>§11 Sonntagsarbeit</strong> (max. 37/Jahr) und <strong>§11 Ersatzruhetag</strong> (Fristen überwachen). Erfasste Pflicht-Pause-Ausnahmen samt Begründung sind ebenfalls einsehbar.</p>
        <p>Das System prüft bei jeder Eingabe automatisch §3 (8h/10h am Tag, 48h-Wochenwarnung), §4 (Pausenpflicht), §6 (8h für Nachtarbeitnehmer), §9/10 (Sonntagsarbeit).</p>
        <p className="text-amber-700"><strong>§3 Tageshöchstgrenze (10h):</strong> Beim <strong>Live-Ausstempeln</strong> wird ein Tag über 10h nicht blockiert (die Zeit ist bereits geleistet und §16-pflichtig zu dokumentieren) – es erscheint eine deutliche Warnung. Bei <strong>manueller Eingabe oder Antrag</strong> bleibt die 10h-Grenze eine <strong>harte Sperre</strong>.</p>
        <p><strong>Angerechnet vs. laut Stempel (ab 1.20.0):</strong> Die §3- und §4-Sperren rechnen mit der angerechneten Zeit; ein Lückenabschnitt ab 15 Min. zwischen zwei Arbeitszeit-Blöcken zählt als Pause. Damit eine Kappung keinen Verstoß verdeckt, weisen zusätzlich Hinweise auf die <strong>Anwesenheit laut Stempel</strong> hin (über 10 h am Tag, durchgestempelt ohne Pause, über 48 h in der Woche – nie blockierend) sowie auf „Pause in der Lücke wird zusätzlich abgezogen". Die Auswertung <strong>„24-Wochen-Durchschnitt §3 ArbZG"</strong> unter Berichte zeigt neben „Ø angerechnet / Tag" den Wert „Anwesenheit laut Stempel" – die Grenze gilt für die tatsächliche Arbeitszeit; liegt dieser Durchschnitt über 8 h, ist er rot hervorgehoben. Ohne Soll-Arbeitstage im Zeitraum steht „keine Soll-Arbeitstage" statt eines Urteils. Es gelten die Grenzen für Erwachsene; die strengeren Regeln für Jugendliche (§§ 11, 12 JArbSchG) prüft PraxisZeit nicht.</p>
      </div>
    ),
  },
  {
    title: '11. Audit-Log & Fehler-Monitoring',
    content: (
      <div className="space-y-2">
        <p>Das <strong>Änderungsprotokoll</strong> zeichnet Änderungen unveränderlich auf (Zeiteinträge, Abwesenheiten, Korrekturanträge, Arbeitszeit-Änderungen mit „Neukappung (Arbeitszeit-Änderung)" je neu berechnetem Eintrag und einer Sammelzeile je Änderung bzw. Löschung, Anerkennungen als „Anrechnung anerkannt", Stundenänderungen, DSGVO-Vorgänge); Filter nach Monat und Person. Auch Anlegen und Bearbeiten über die <strong>Zeiterfassung</strong> stehen dort – Mitarbeitende am selben Tag, Admins an eigenen Einträgen jedes Tages (bis 1.19.3 nur bei einer Pflicht-Pause-Ausnahme); Spalte „Quelle" dann „Manuell" wie bei Korrekturen durch die Verwaltung (bis 1.19.3 „Admin", auch wenn Mitarbeitende selbst gehandelt hatten – wer gehandelt hat, nennt „Geändert von"), dazu „Ausstempeln" und „Automatisch geschlossen". Fehlgeschlagene Anmeldungen stehen im Server-Protokoll, nicht hier. Dient als Nachweis gem. §16 ArbZG bei Betriebsprüfungen. Darunter stehen die <strong>Konto-Vorgänge</strong>: wer wann ein Konto deaktiviert, reaktiviert, umgestuft oder ein fremdes Passwort gesetzt hat – einschließlich der Notfall-Vorgänge über die Kommandozeile.</p>
        <p>Das <strong>Fehler-Monitoring</strong> zeigt Backend-Fehler mit Häufigkeit und Kontext. Wiederkehrende Fehler als GitHub Issue melden (Button in der Detailansicht).</p>
      </div>
    ),
  },
  {
    title: '12. Berechnungsgrundlagen (Soll, Ist, Überstunden, Urlaub)',
    content: (
      <div className="space-y-2">
        <p><strong>Tagessoll</strong> = Wochenstunden ÷ Arbeitstage pro Woche – der Divisor ist <strong>nicht</strong> fix 5 (24 h auf 3 Tage = 8 h/Tag). Individuelle Tagesstunden je Wochentag sind möglich; Wochenende/Feiertag/außerhalb des Beschäftigungszeitraums = 0. Bei <strong>Arbeitszeit-Blöcken</strong>: Summe der Blöcke − Pause innerhalb der Blöcke (08–12 + 15–18, Pause 30 Min. = 6,50 h).</p>
        <p><strong>Ist</strong> = (Ende − Beginn) − Pause, nie negativ. Arbeitszeit-Blöcke kürzen die Anrechnung: vor dem ersten, nach dem letzten und zwischen den Blöcken zählt Zeit nur bis zum Puffer; nicht angerechnete Lückenzeit wird abgezogen, der Rohstempel bleibt erhalten (§16 ArbZG), anerkannte Einträge zählen voll. Krank und Fortbildung zählen als Ist (§3 EntgFG).</p>
        <p><strong>Abwesenheiten:</strong> Urlaub, bezahlte Freistellung &amp; Sonstige senken das Soll; Krank &amp; Fortbildung füllen das Ist auf (saldo-neutral); der Überstundenausgleich lässt das Soll stehen (Ist 0 h) und baut Überstunden ab.</p>
        <p><strong>Die Gutschrift für Krank/Fortbildung folgt dem Soll des Tages:</strong> voller Betrag nur an einem regulären Arbeitstag – an Wochenenden und Feiertagen <strong>keine</strong> Gutschrift, an einem als „halber Feiertag" konfigurierten 24./31.12. die <strong>Hälfte</strong>. An einem Tag ohne Arbeitspflicht kann keine Arbeitspflicht ausfallen (§ 4 Abs. 2 EntgFG). Beispiel: krank vom 24.12. bis 28.12. ⇒ 4 + 0 + 0 + 0 + 8 = <strong>12 h</strong> gutgeschrieben = genau das Soll dieser Tage, Saldo 0. Eine Fortbildung, die länger dauerte als der Arbeitstag, bleibt echte Mehrarbeit – gedeckelt wird nicht.</p>
        <p><strong>Wo der Fehler im Alltag auftrat.</strong> An Wochenenden und an bereits eingetragenen Feiertagen legt PraxisZeit beim Buchen gar keine Abwesenheit an – im Beispiel oben entstehen nur zwei Zeilen (24.12. und 28.12.). Der Regelfall war deshalb der <strong>Halbtags-Sondertag</strong>: eine normale Krankmeldung am 24.12. brachte bis Version 1.17.0 4 h Soll gegen 8 h Gutschrift = <strong>+4 Überstunden aus dem Nichts</strong>. Auf einem Feiertag kann eine Abwesenheit nachträglich landen (Bundesland umgestellt, eigener Feiertag auf ein gebuchtes Datum gelegt, Buchung in ein noch nicht synchronisiertes Jahr) – dann kam je solchem Tag ein volles Tagessoll dazu.</p>
        <p><strong>Was das Update repariert – und was nicht.</strong> Laufende und noch <strong>nicht abgeschlossene</strong> Jahre korrigieren sich von selbst, weil die Salden bei jedem Aufruf neu berechnet werden. Ein bereits per <strong>Jahresabschluss</strong> abgeschlossenes Jahr <strong>nicht</strong>: der Übertrag ist eingefroren und wird bewusst nie automatisch neu gerechnet (sonst würden manuelle Korrekturen überschrieben). Da der Fehler naturgemäß im Dezember auftrat, ist das der wahrscheinlichste Fall – prüfen Sie nach dem Update den Übertrag betroffener Mitarbeiter:innen unter „Jahresabschluss" und korrigieren Sie ihn dort von Hand.</p>
        <p><strong>Überstundenkonto</strong> = fortlaufende Summe der Monatssalden ab dem Jahresübertrag. Die Spalte „Überstunden (JTD)" zeigt 1. Januar bis heute zzgl. Carryover.</p>
        <p><strong>Voraussichtlicher Saldo zum Jahresende:</strong> Zeigt zusätzlich, wie das Konto zum 31.12. voraussichtlich aussieht – der Saldo bis heute abzüglich der Stunden aller bereits gebuchten künftigen Überstundenausgleich-Tage. Nur Ausgleichstage senken das Konto; Urlaub, Krankheit und Fortbildung sind saldo-neutral und fließen nicht in die Vorschau ein. Unter <strong>Einstellungen → Überstunden-Projektion zum Jahresende</strong> lässt sich das getrennt für das Mitarbeiter-Dashboard und für die Spalte „Überstd. Jahresende" im Admin-Dashboard (Monats-/Wochenbericht) abschalten (Standard: beide an).</p>
        <p><strong>Urlaub (Tagesprinzip §3 BUrlG):</strong> 1 freier Arbeitstag = 1 Tag (Halbtag 0,5), unabhängig von der Stundenzahl. Anspruch <code>30 × Arbeitstage ÷ 5</code>, anteilig bei unterjährigem Eintritt/Austritt, zzgl. Resturlaub-Vortrag (Carryover). Nur Urlaub belastet das Budget; ein als „Frei + zählt als Urlaub" konfigurierter Sondertag (24./31.12.) kostet ebenfalls 1 Tag. Vor Eintritt/nach Austritt: kein Anspruch und kein Verbrauch.</p>
        <p><strong>Feste Monatsarbeitszeit (Minijob-Modus, #377 Baustein 2b):</strong> Für MA mit diesem Opt-in gilt statt der obigen Tagessoll-Summe ein <strong>festes</strong> Monats-Soll (= vereinbarte Monatsarbeitszeit, kalendertag-pro-rata bei Ein-/Austritt); Feiertag/Urlaub/bezahlte Freistellung an geplanten Tagen schreiben die geplanten Stunden dem Ist gut statt das Soll zu senken, unbezahlte Fehltage (Sonstiges) mindern stattdessen das feste Soll. Details in Abschnitt 9 „Eigene Abwesenheitsgründe, Kind krank & Minijob". Im <strong>Monatsjournal</strong> heißt die Tagesspalte in diesem Modus „Geplant" (geplante Anwesenheit, kein Tages-Soll) und der Tages-Saldo entfällt — verbindlich ist die Monatsübersicht unter der Tabelle (#463).</p>
        <p className="text-gray-500">Vollständige Formeln und durchgerechnete Beispiele: <code>docs/BERECHNUNGEN.md</code> bzw. Admin-Handbuch-Anhang „Berechnungsgrundlagen".</p>
      </div>
    ),
  },
  {
    title: '13. Datensicherung (Backup & Restore)',
    content: (
      <div className="space-y-2">
        <p>Unter <strong>Datensicherung</strong> erstellen Sie jederzeit eine vollständige, komprimierte Sicherung der Datenbank (<strong>Jetzt sichern</strong>) oder aktivieren eine <strong>tägliche automatische Sicherung</strong> mit Aufbewahrungsdauer und optionalem Speicherort.</p>
        <p>Vorhandene Sicherungen lassen sich in der Liste <strong>herunterladen</strong> (für eine externe Kopie) oder löschen. Format ist Plain-SQL + gzip (<code>praxiszeit_&lt;Zeitstempel&gt;.sql.gz</code>).</p>
        <p><strong>Wiederherstellung:</strong> im Docker-Betrieb mit <code>bash restore.sh &lt;datei&gt;</code> neben der <code>docker-compose.yml</code>. Das Script legt die Datenbank frisch an, spielt die Sicherung ein und startet das Backend neu – erst dieser Start hebt eine Sicherung einer älteren Version per Migration auf den Stand der installierten Version. Native unter Linux und macOS den Dienst anhalten, die Sicherung mit <code>praxiszeit-server.py restore &lt;datei&gt;</code> einspielen und den Dienst wieder starten – auch hier migriert erst dieser Start; scheitert das Einspielen, bleibt die bisherige Datenbank unverändert. Unter Windows <code>restore-backup.bat &lt;datei&gt;</code>.</p>
        <p><strong>§16 ArbZG:</strong> Zeitaufzeichnungen sind mind. 2 Jahre aufzubewahren — Aufbewahrungsdauer entsprechend setzen und eine Kopie <strong>außerhalb</strong> des Servers vorhalten. Vor jedem Update zusätzlich sichern.</p>
        <p className="text-gray-500">Native installiert läuft die <em>geplante</em> Sicherung über den OS-Timer; der <em>manuelle</em> Trigger und die Liste funktionieren überall. Alle Kommandozeilen-Varianten: <code>docs/BACKUP.md</code>.</p>
      </div>
    ),
  },
  {
    title: '14. Schichtplanung (optional)',
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
        <p>Der Knopf <strong>„PDF"</strong> in der Werkzeugleiste erzeugt einen Aushang im Querformat mit einer Tabelle Arbeitsplatz × Wochentag – zum Aushängen am Schwarzen Brett. Auch Mitarbeitende können darüber den Plan drucken, den sie in ihrer Ansicht sehen. Ein Schwarzes Brett ist oft auch für Patientinnen und Patienten einsehbar – das gehört bei der Wahl des Hinweistexts bedacht. Gilt der gedruckte Plan gerade nicht, trägt der Ausdruck fett in der Kopfzeile den Vermerk <strong>„Vorschau — gilt derzeit nicht"</strong> bzw. <strong>„Nicht mehr gültig"</strong>. Haben alle Arbeitsplätze des Plans denselben Standort, steht er einmal in der Kopfzeile („Standort: Hauptstelle"); bei unterschiedlichen (oder teils fehlenden) Standorten steht er stattdessen hinter jedem betroffenen Arbeitsplatznamen, z. B. „Tresen (Hauptstelle)". Der <strong>Praxisname</strong> in der Kopfzeile ist der bei der Installation angegebene – in der nativen Installation der Eintrag <code>name</code> im Abschnitt <code>[practice]</code> der Datei <code>config/praxiszeit.conf</code>, bei Docker <code>PRACTICE_NAME</code> in der <code>.env</code>. Ändern Sie ihn dort; er gilt nach einem Neustart des Dienstes (Docker: <code>docker compose up -d</code>). Ohne eigenen Eintrag steht dort der Vorgabewert „Praxis".</p>
        <p className="text-gray-500">Die Schichtplanung ist ein reines Planungswerkzeug und berührt <strong>nicht</strong> Zeiterfassung, Soll/Ist-Stunden, ArbZG-Prüfungen, Urlaub oder Überstunden. Details: <code>docs/SCHICHTPLANUNG.md</code>.</p>
      </div>
    ),
  },
  {
    title: '15. Admin-Passwort verloren',
    content: (
      <div className="space-y-2">
        <p>Kommt niemand mehr mit einem Administrator-Konto in die Anwendung, hilft ein Kommando <strong>auf dem Server selbst</strong> — es setzt das Passwort direkt in der Datenbank neu und braucht dafür keine Anmeldung:</p>
        <p><strong>Linux:</strong> <code>sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py reset-admin-password</code></p>
        <p><strong>macOS</strong> (Dienstkonto mit Unterstrich): <code>sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py reset-admin-password</code></p>
        <p><strong>Windows</strong> (Eingabeaufforderung als Administrator im Installationsordner): <code>bin\python\python.exe praxiszeit-server.py reset-admin-password</code></p>
        <p className="text-gray-500">Der lange Pfad ist nötig: das Programm braucht den mitgelieferten Python-Interpreter und liegt nicht als normaler Befehl im Systempfad. Weicht Ihr Installationsverzeichnis von <code>/opt/praxiszeit</code> ab, ersetzen Sie es entsprechend.</p>
        <p>Das neue Passwort wird zweimal abgefragt (nicht mit eingetippt, damit es nicht in der Befehls-Historie landet) und gegen dieselben Regeln geprüft wie in der Anwendung. Danach sind <strong>alle laufenden Sitzungen dieses Kontos ungültig</strong>.</p>
        <p>Ist das Konto <strong>deaktiviert</strong>, genügt ein neues Passwort nicht – die Anmeldung bleibt gesperrt. Dann den Befehl mit <code>--reactivate</code> wiederholen: er setzt das Passwort neu und aktiviert das Konto wieder.</p>
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
        <p className="text-sm text-gray-600">Unter <strong>Einstellungen</strong>: Bundesland (Feiertage – ein späterer Wechsel berechnet die gesetzlichen Feiertage aller Jahre neu, auch zurückliegender), Urlaubsgenehmigung (an/aus), Sondertage 24./31.12., Onboarding-Tour (Standard an).</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Eigene Abwesenheitsgründe</strong> (z. B. „Schule" für Azubis) legen Sie unter <strong>Einstellungen → „Eigene Abwesenheitsgründe"</strong> an: Bezeichnung + Farbe + Basis-Verhalten (<em>zählt als gearbeitet</em> / <em>bezahlt frei</em> / <em>unbezahlt frei</em> / <em>Überstundenabbau</em>; nach dem Anlegen fix). Sie erscheinen beim Buchen unter „Eigene Gründe"; im Team-Kalender werden sie für Kolleg:innen aus Datenschutzgründen als „abwesend" maskiert.</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Kind krank & Sonderurlaub (#376):</strong> Unter „Vorlagen (1-Klick aktivieren)" legen Sie gängige Gründe direkt an (Kind krank, Todesfall, Hochzeit, Umzug …). <strong>Kind krank</strong> (§45 SGB V) ist <em>unbezahlt frei</em> und wird pro Jahr gezählt: Standardanspruch unter <strong>Einstellungen → „Kind-krank-Standardanspruch"</strong> (Voreinstellung 15 Tage), pro Mitarbeiter:in im Benutzerformular überschreibbar. Bei Überschreitung erscheint beim Buchen ein Hinweis – die Abwesenheit wird trotzdem erfasst (nicht blockiert). Verbrauch je Person in der Benutzerübersicht.</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Minijob / Arbeitszeitkonto (§ 2 Abs. 2 MiLoG, #377):</strong> Für Minijobber:innen auf Arbeitszeitkonto aktivieren Sie im Benutzerformular „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)". Die <strong>vereinbarte Monatsarbeitszeit</strong> tragen Sie im Feld „Vereinbarte Monatsarbeitszeit (h)" direkt ein (leer = automatisch aus den Wochenstunden × 13/3). PraxisZeit warnt dann <em>weich</em> (nicht blockierend), wenn die Konto-Plusstunden pro Monat 50 % dieser Monatszeit übersteigen oder die 12-Monats-Ausgleichsfrist reißt – beim Buchen, im eigenen Überstundenkonto und in der Benutzerübersicht. Der aktuelle Mindestlohn steht unter <strong>Einstellungen → „Gesetzlicher Mindestlohn"</strong>. Hinweis: die Grenze bindet nur mindestlohnwirksame Stunden; bei höherer Vergütung ggf. unkritisch. Keine Lohn-/603-€-Prüfung (kein Lohn hinterlegt).</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Feste Monatsarbeitszeit (Minijob-Modus, #377 Baustein 2b):</strong> Bei aktivem Arbeitszeitkonto können Sie zusätzlich „Feste Monatsarbeitszeit (Monats-Soll = vereinbarte Monatsarbeitszeit)" aktivieren – dann macht die vereinbarte Monatszeit zur <strong>Pflichtangabe</strong> und wird jeden Monat fest als Soll gesetzt (anteilig bei unterjährigem Ein-/Austritt), statt aus Wochenstunden/Arbeitstagen zu schwanken. Die Tagesstunden je Wochentag werden dann zur „geplanten Anwesenheit": Feiertag, Urlaub oder bezahlte Freistellung auf einem geplanten Tag schreiben die geplanten Stunden dem Ist gut; ein unbezahlt entschuldigter Tag (Sonstiges) mindert stattdessen das feste Soll. Bei einer <strong>bestehenden</strong> Person tragen Sie diese Tagesstunden ausschließlich über „Arbeitszeit anpassen…" (Modus „Nach Tagen") ein – im Bearbeiten-Formular selbst gibt es keine Tagesstunden-Matrix mehr; beim <strong>Anlegen</strong> sind es weiterhin normale Eingabefelder. Mit Arbeitszeit-Blöcken gilt dasselbe: der Block-Editor beschriftet die Werte je Tag und Woche als „geplant". Weiche Warnung, wenn das Monats-Ist die vereinbarte Zeit übersteigt. <strong>Bekannte Grenze:</strong> Liegen die geplanten Tagesstunden deutlich unter der Monatszeit, deckt die Gutschrift bei einem <em>ganzen</em> Fehlmonat (Urlaub/Krank) nur den geplanten Anteil ab – der flexible Rest bleibt Konto-Defizit und braucht eine manuelle Korrektur; einzelne Fehltage sind korrekt.</p>
      </section>

      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-2">2. Mitarbeiter anlegen</h3>
        <p className="text-sm text-gray-600 mb-1"><strong>Benutzerverwaltung → „Neue:r Mitarbeiter:in"</strong>: Benutzername + Startpasswort, Name, Wochenstunden bzw. Tagesplan, Urlaubsanspruch → Speichern.</p>
        <ul className="text-sm text-gray-500 list-disc list-inside space-y-0.5">
          <li>Ohne Stundenzählung: Häkchen <em>„Stundenzählung aktiv (Soll-Stunden werden berechnet)"</em> entfernen – Urlaub/Krank trotzdem tagebasiert; hat nichts mit § 18 ArbZG zu tun.</li>
          <li>Ein-/Austritt: <em>Erster/Letzter Arbeitstag</em> setzen.</li>
          <li>Optional: Arbeitszeit-Blöcke – Modus „Nach Arbeitsblöcken" (je Wochentag bis zu drei Blöcke + Pause innerhalb der Blöcke; daraus Tagessoll und Anrechnung).</li>
          <li>Spätere Änderungen an Wochenstunden, Tagesplan, Blöcken, Modus oder Arbeitstagen: nur noch über „Arbeitszeit anpassen…" mit Wirkungsdatum.</li>
        </ul>
      </section>

      <section>
        <h3 className="text-base font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-2">3. Betrieb</h3>
        <p className="text-sm text-gray-600">Mitarbeiter stempeln/erfassen (einen vergangenen Tag beantragen sie über „Antrag"); das <strong>Admin-Dashboard</strong> zeigt Salden + fehlende Buchungen. Korrektur-/Urlaubsanträge prüfen, Berichte exportieren. Nicht angerechnete Zeit (vor, nach oder zwischen den Arbeitszeit-Blöcken) steht am Eintrag; geleistete Arbeit dort „Anerkennen" (Admin-Dashboard → Detailansicht oder Monatsjournal).</p>
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
