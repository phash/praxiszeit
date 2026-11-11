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
              <li>Werktag (Mo–Fr) ohne Block = freier Tag → gestempelte Zeit zählt 0 h, bis die Verwaltung „Anrechnung beantragen" mit „Genehmigen und anerkennen" annimmt (auch ein vergessenes Ausstempeln zählt dort 0 h).</li>
              <li>Über die Pause zwischen zwei Blöcken gestempelt → „gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet".</li>
              <li>Pause in der Lücke gemacht? Die Lücke zählt als Pause (§4 ArbZG; ab 15 Min. nach Abzug des Puffers) – keine zusätzliche Pause eintragen, sonst wird beides abgezogen („Pause in der Lücke wird zusätzlich abgezogen: …" → Pause auf 0 setzen).</li>
              <li>Dort gearbeitet? Am Eintrag <strong>„Anrechnung beantragen"</strong> (für heute erst nach Arbeitsende). Anerkannte Einträge: kein Bearbeiten/Löschen, auch am selben Tag per Änderungs- bzw. Löschantrag.</li>
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
        <p className="text-sm text-gray-600 mt-1">Administration: Admin-Dashboard · Benutzerverwaltung · Arbeitszeiten im Team · Änderungsanträge · Berichte · Abwesenheiten · Änderungsprotokoll · Fehler-Monitoring · Urlaubsanträge · Import · Einstellungen</p>
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
              <li><strong>Stundenzählung aus</strong> (beim Anlegen im Formular, später nur über „Arbeitszeit anpassen…“) – Mitarbeitende ohne Soll/Ist-Erfassung; Urlaub/Krank zählen trotzdem tagebasiert.</li>
              <li><strong>Nimmt an Betriebsferien teil</strong> (Standard an) – rollenunabhängig; für reine Verwaltungs-Accounts abwählbar.</li>
              <li><strong>Erster/Letzter Arbeitstag</strong> – Soll wird nur innerhalb dieses Zeitraums berechnet.</li>
            </ul>
            <p className="text-sm text-gray-500 mt-1">Die Übersicht zeigt je MA Urlaubskonto und Überstundensaldo (JTD).</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Arbeitszeit ändern</p>
            <p className="text-sm text-gray-600">Benutzer bearbeiten → Button „Arbeitszeit anpassen…" (oder Uhr-Symbol in der Liste) → Dialog „Arbeitszeit &amp; Wochenstunden": „Gültig ab" + „Gleichmäßig", „Nach Tagen" oder „Nach Arbeitsblöcken" (bis zu 3 Blöcke je Wochentag + Pause innerhalb der Blöcke; Tagessoll = Σ Blöcke − Pause; nur bei Stundenzählung) + optional Notiz. Im Formular nur Anzeige (Bereich „Arbeitszeit heute"), beim Anlegen normale Felder bzw. Block-Editor. Verlauf „Ab … bis …".</p>
            <p className="text-sm text-gray-600">Vorab die Auswirkung prüfen (Einträge je Monat alt → neu, Abwesenheiten, Δ Soll / Δ angerechnet / Überstundenkonto / Urlaubsverbrauch; Haken Pflicht, sobald etwas betroffen ist). Rückwirkend werden Einträge an geänderten Wochentagen ab Rohstempel mit dem aktuellen Puffer neu gekappt, danach Abwesenheits-Stunden aufs neue Tagessoll (Urlaubstage bleiben); offene Einträge vergangener Tage werden vorher geschlossen.</p>
            <p className="text-sm text-gray-600">Abschnitt „Urlaub und Abrechnung": „Urlaubsanspruch pro Jahr ab diesem Datum", Stundenzählung, Minijob-Einstellungen (nur zum Monatsersten). Vorschlag über „Vorschlag übernehmen (N)".</p>
            <p className="text-sm text-amber-700">⚠️ Verkürzung (Eintrag verliert Zeit, Konto sinkt – auch durch höheres Soll – oder Misch-Tag-Gutschrift sinkt stärker als das Tagessoll): Standard „Ab heute"; rückwirkend nur mit Grund, Begründung und Haken (Grund, Begründung und Notiz zusammen höchstens 500 Zeichen); reicht sie in ein abgeschlossenes Jahr, danach den Jahresabschluss erneut ausführen. Falsche Stempel am Zeiteintrag korrigieren, nicht über die Arbeitszeit.</p>
            <p className="text-sm text-gray-600">Löschen: Papierkorb nur an der jüngsten Zeile des Verlaufs. Verkürzt das Löschen, Standard „auf den vorherigen Stand zurücksetzen" (Knopf „Zurücksetzen") oder „Rückwirkend löschen mit Neuberechnung". Wurde inzwischen eine Änderung dazwischen angelegt, lehnt PraxisZeit die Rücksetzung ab („Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.").</p>
            <p className="text-sm text-gray-600">MA sehen 30 Tage den Dashboard-Kasten „Hinweis zu Ihrer Arbeitszeit"; Protokoll „Neukappung (Arbeitszeit-Änderung)" je Eintrag + Sammelzeile. Berichte zeigen den Wert zu Zeitraumsbeginn plus „ab 15.03.2026: 20,0 Std/Woche" (Tagesplan „ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche", Blöcke „ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche") — im Dashboard wie in Excel/ODS/PDF (Jahresübersicht: Spalte „Stundenänderungen").</p>
            <p className="text-sm text-amber-700">⚠️ Arbeitstage-only-Änderung (gleiche Wochenstunden, andere Arbeitstage): Bei „Gleichmäßig" nennt der Verlaufs-/Berichtstext zwar die neue Arbeitstage-Zahl (z. B. „ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage"), die Wochenstundenzahl bleibt aber gleich – das Tagessoll verschiebt sich trotzdem still. Bei „Nach Tagen"/„Nach Arbeitsblöcken" ändert sich stattdessen der Urlaubsverbrauch (ein wegfallender Wochentag zählt einen dort gebuchten Urlaubstag rückwirkend nicht mehr). Deshalb immer die Auswirkung prüfen, nicht nur die Wochenstundenzahl.</p>
            <p className="text-sm text-gray-600"><strong>Arbeitszeiten im Team</strong> (Menü): Blöcke aller MA je Wochentag + Besetzung je halbe Stunde; Schieber „Bearbeiten" einschalten, Blöcke ziehen → „Änderung speichern…" öffnet den Dialog „Arbeitszeit &amp; Wochenstunden" – wirksam erst dort mit Stichtag „Gültig ab" (+ Vorschau).</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Nicht angerechnete Zeit</p>
            <p className="text-sm text-gray-600">Zeit vor, nach und zwischen den Blöcken zählt nur bis zum Puffer (an jedem Blockrand, Einstellungen → „Soll-Arbeitszeit-Fenster", Std. 15 Min.). Sichtbar am Eintrag, im Journal („Anwesenheit nicht angerechnet") und in der Export-Spalte „Nicht angerechnet (Min)". Geleistete Arbeit: <strong>„Anerkennen"</strong> (Admin-Dashboard-Detail, Monatsjournal) – dauerhaft, protokolliert. Nichtanrechnung ersetzt keine Vergütungsentscheidung.</p>
            <p className="text-sm text-gray-600"><strong>Auto-Close</strong> (vergessenes Ausstempeln, 23:59) rechnet nur bis zum letzten Block + Puffer an („automatisch geschlossen"), an einem Werktag ohne Block 0 h; bis 23:59 nur, wo nichts gekappt wird (keine Blöcke hinterlegt, Wochenende/Feiertag, ohne Stundenzählung); tatsächliches Ende nachtragen (MA per Änderungsantrag) – auch ein echtes Ende 23:59 ist eintragbar (wird gekappt wie jedes Ende, bis 23:59 angerechnet erst nach „Anerkennen").</p>
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
        <p className="text-sm text-gray-500 mt-2">Tageszeilen von Monatsreport und Jahresreport Detailliert: hinten angehängt „Unterbrechung (Min)" und „Zeiteinträge" (Excel/ODS), – auch im PDF – „Nicht angerechnet (Min)" (Lücke + vor/nach den Blöcken abgeschnittene Zeit) und die tatsächlichen Stempel: „Gestempelt (Von–Bis)", „Anwesenheit laut Stempel (Std)" (über 10 h hervorgehoben) und „Pausenausnahme (§4 ArbZG)" (PDF: Spalte „Gestempelt (Anwesenheit)", Begründung in der Bemerkung). „Netto" ist die angerechnete Zeit. Der Jahresreport Classic (nur Monatswerte, keine Tageszeilen) hat diese Spalten nicht.</p>
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
        <p className="text-sm text-gray-600">Unter <strong>Einstellungen</strong>: Bundesland (Feiertage – ein späterer Wechsel berechnet die gesetzlichen Feiertage aller Jahre neu, auch zurückliegender), Urlaubsgenehmigung (an/aus), Sondertage 24./31.12. (auch „Verkürzt auf X Stunden"), Verkürzte Tage (einzelne Tage mit Höchststunden), Onboarding-Tour (Standard an).</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Eigene Abwesenheitsgründe</strong> (z. B. „Schule" für Azubis) legen Sie unter <strong>Einstellungen → „Eigene Abwesenheitsgründe"</strong> an: Bezeichnung + Farbe + Basis-Verhalten (<em>zählt als gearbeitet</em> / <em>bezahlt frei</em> / <em>unbezahlt frei</em> / <em>Überstundenabbau</em>; nach dem Anlegen fix). Sie erscheinen beim Buchen unter „Eigene Gründe"; im Team-Kalender werden sie für Kolleg:innen aus Datenschutzgründen als „abwesend" maskiert.</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Kind krank & Sonderurlaub (#376):</strong> Unter „Vorlagen (1-Klick aktivieren)" legen Sie gängige Gründe direkt an (Kind krank, Todesfall, Hochzeit, Umzug …). <strong>Kind krank</strong> (§45 SGB V) ist <em>unbezahlt frei</em> und wird pro Jahr gezählt: Standardanspruch unter <strong>Einstellungen → „Kind-krank-Standardanspruch"</strong> (Voreinstellung 15 Tage), pro Mitarbeiter:in im Benutzerformular überschreibbar. Bei Überschreitung erscheint beim Buchen ein Hinweis – die Abwesenheit wird trotzdem erfasst (nicht blockiert). Verbrauch je Person in der Benutzerübersicht.</p>
        <p className="text-sm text-gray-500 mt-1"><strong>Minijob / Arbeitszeitkonto (§ 2 Abs. 2 MiLoG, #377):</strong> Für Minijobber:innen auf Arbeitszeitkonto aktivieren Sie „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)" (beim Anlegen im Formular, später über „Arbeitszeit anpassen…“ zum Monatsersten). Die <strong>vereinbarte Monatsarbeitszeit</strong> tragen Sie im Feld „Vereinbarte Monatsarbeitszeit (h)" ein (leer = automatisch aus den Wochenstunden × 13/3). PraxisZeit warnt dann <em>weich</em> (nicht blockierend), wenn die Konto-Plusstunden pro Monat 50 % dieser Monatszeit übersteigen oder die 12-Monats-Ausgleichsfrist reißt – beim Buchen, im eigenen Überstundenkonto und in der Benutzerübersicht. Der aktuelle Mindestlohn steht unter <strong>Einstellungen → „Gesetzlicher Mindestlohn"</strong>. Hinweis: die Grenze bindet nur mindestlohnwirksame Stunden; bei höherer Vergütung ggf. unkritisch. Keine Lohn-/603-€-Prüfung (kein Lohn hinterlegt).</p>
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
          <li>Urlaubsanspruch, Stundenzählung und Minijob-Einstellungen ändern sich ebenfalls nur über „Arbeitszeit anpassen…" (Abschnitt „Urlaub und Abrechnung", Feld „Urlaubsanspruch pro Jahr ab diesem Datum"); Minijob-Änderungen nur zum Monatsersten.</li>
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
  /** Inhalt des Reiters „Handbuch“; ohne ihn entfällt der Reiter (Drawer: Handbuch liegt unter /help). */
  handbuch?: ReactNode;
}

export function DocViewerContent({ isAdmin, initialTab = 'cheatsheet', onTabChange, handbuch }: DocViewerContentProps) {
  // Ohne Handbuch-Inhalt gibt es den Reiter nicht: initialTab='handbuch' fällt auf die Kurzanleitung zurück.
  const [activeTab, setActiveTab] = useState<DocTab>(initialTab === 'handbuch' && !handbuch ? 'cheatsheet' : initialTab);

  function handleTab(tab: DocTab) {
    setActiveTab(tab);
    onTabChange?.(tab);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar — Schnellstart nur für Admins */}
      <div className="border-b border-gray-200 px-4 flex gap-6 shrink-0">
        {((isAdmin ? ['schnellstart', 'cheatsheet'] : ['cheatsheet']).concat(handbuch ? ['handbuch'] : []) as DocTab[]).map((tab) => (
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
          : handbuch
        }
      </div>
    </div>
  );
}
