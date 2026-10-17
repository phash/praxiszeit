import type { ReactNode } from 'react';

interface HelpEntry {
  title: string;
  content: ReactNode;
}

export const helpContent: Record<string, HelpEntry> = {
  '/': {
    title: 'Dashboard',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Übersicht der Karten</h3>
          <ul className="space-y-2 text-sm text-gray-600">
            <li><span className="font-medium text-gray-700">Monatssaldo:</span> Ist minus Soll im laufenden Monat – das Soll zählt bis zum letzten abgeschlossenen Arbeitstag (heute, sobald Sie ausgestempelt haben). Grün = Mehrarbeit, Rot = Minusstunden.</li>
            <li><span className="font-medium text-gray-700">Überstundenkonto:</span> Kumulierter Saldo; darunter, falls geplant, der voraussichtliche Stand zum Jahresende nach bereits eingetragenem Freizeitausgleich.</li>
            <li><span className="font-medium text-gray-700">Urlaubskonto:</span> Resturlaub, Budget und genommene Tage im laufenden Jahr.</li>
            <li><span className="font-medium text-gray-700">Urlaubscountdown:</span> Tage bis zum nächsten Urlaub oder zur nächsten Praxisschließung.</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Monats- und Wochenübersicht</h3>
          <p className="text-sm text-gray-600">Tabelle mit Soll, Ist, Saldo und Überstunden kumuliert. Der Umschalter „Monat"/„Woche" zeigt statt der Monate die letzten 8 Kalenderwochen. „Details anzeigen" öffnet Jahresübersicht und Team-Kalender.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Buchung fehlt</h3>
          <p className="text-sm text-gray-600">Ist ein Eintrag eines Vortags noch offen oder fehlt an einem vergangenen Arbeitstag des laufenden Monats jeder Eintrag (und keine Abwesenheit ist eingetragen), steht oben auf der Seite – am Computer wie auf dem Smartphone – der rote Kasten „Buchung fehlt" mit dem Link „Zur Zeiterfassung →".</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Auf dem Smartphone</h3>
          <p className="text-sm text-gray-600">Die Stempelkarte zeigt „x von y h heute" (zählt bei laufendem Eintrag minütlich mit); weiter unten steht die Karte „Letzte Einträge" mit Ihren fünf neuesten Einträgen – auch aus dem Vormonat.</p>
        </section>
      </div>
    ),
  },

  '/time-tracking': {
    title: 'Zeiterfassung',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Tabs</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li><span className="font-medium">Einträge</span> – Monatliche Zeittabelle, neue Einträge</li>
            <li><span className="font-medium">Journal</span> – Tagesübersicht des Monats</li>
            <li><span className="font-medium">Anträge</span> – Korrekturanträge stellen &amp; verfolgen</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Eintrag erstellen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Klicken Sie auf <span className="font-medium">„+ Neuer Eintrag"</span> (Mitarbeitende: nur für heute; einen vergangenen Tag beantragen Sie über <span className="font-medium">„Antrag"</span>)</li>
            <li>„Von" und „Bis" eintragen (sind Arbeitszeit-Blöcke für Sie hinterlegt, sind die Felder daraus vorbelegt)</li>
            <li>Pause in Minuten eingeben – Pflicht bei mehr als 6 Stunden (siehe unten); eine Lücke zwischen Ihren Arbeitszeit-Blöcken zählt als Pause</li>
            <li>Optional: Notiz hinzufügen</li>
            <li>Auf <span className="font-medium">„Speichern"</span> klicken</li>
          </ol>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">ArbZG-Pflichtpausen (§4)</h3>
          <div className="text-sm bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
            <p className="text-amber-800">⚠️ <span className="font-medium">6–9 Stunden Arbeit</span> → mind. 30 Min. Pause</p>
            <p className="text-amber-800">⚠️ <span className="font-medium">Über 9 Stunden Arbeit</span> → mind. 45 Min. Pause</p>
          </div>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Tagesgrenze (§3 ArbZG)</h3>
          <div className="text-sm space-y-1">
            <p className="text-gray-600">🟡 <span className="font-medium">Warnung</span> ab 8 Std. Nettoarbeitszeit</p>
            <p className="text-gray-600">🔴 <span className="font-medium">Gesperrt</span> ab 10 Std. Nettoarbeitszeit</p>
          </div>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Nicht angerechnete Zeit</h3>
          <p className="text-sm text-gray-600">Zeit vor, nach oder zwischen Ihren Arbeitszeit-Blöcken steht unter dem Eintrag als „nicht angerechnet". Haben Sie dort gearbeitet: am Eintrag <span className="font-medium">„Anrechnung beantragen"</span> (für heute erst nach Arbeitsende).</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Datum ändern</h3>
          <p className="text-sm text-gray-600">Für Mitarbeitende ist beim Bearbeiten das Datum gesperrt. Gehört die Zeit zu einem anderen Tag: Eintrag löschen und über <span className="font-medium">„Antrag"</span> einen Änderungsantrag für diesen Tag stellen. Admins ändern das Datum direkt.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Monat wählen</h3>
          <p className="text-sm text-gray-600">Die Liste zeigt einen Monat (unten mit der Summe der Netto-Stunden). Mit „Vorheriger Monat" bzw. „Nächster Monat" (Pfeile &larr; &rarr;) blättern, „Heute" springt zum laufenden Monat zurück. Auf dem Smartphone zeigt eine Wochenleiste Punkte für Tage mit Eintrag – ein Tipp springt zum Eintrag.</p>
        </section>
      </div>
    ),
  },

  '/absences': {
    title: 'Abwesenheiten',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Abwesenheit eintragen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Auf <span className="font-medium">„Abwesenheit eintragen"</span> klicken</li>
            <li>Typ wählen: Urlaub / Krank / Fortbildung / Überstundenausgleich / Sonstiges – oder einen der „Eigene Gründe" Ihrer Praxis</li>
            <li>Einzeltag: nur Datum (optional „Halber Tag", zählt 0,5 Tag); Zeitraum: „Zeitraum (mehrere Tage)" aktivieren + „Bis"</li>
            <li>Optional: Notiz</li>
            <li>Speichern</li>
          </ol>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Abwesenheitstypen</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>🔵 <span className="font-medium">Urlaub</span> – zieht vom Urlaubskonto ab</li>
            <li>🔴 <span className="font-medium">Krank</span> – keine Urlaubswirkung</li>
            <li>🟠 <span className="font-medium">Fortbildung (außer Haus)</span> – gilt als Arbeitszeit</li>
            <li>🟣 <span className="font-medium">Überstundenausgleich</span> – Abbau von Überstunden</li>
            <li>⚫ <span className="font-medium">Sonstiges</span> – freie Verwendung</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Urlaubsantrag</h3>
          <p className="text-sm text-gray-600">Verlangt Ihre Praxis eine Genehmigung, wird aus dem Eintrag ein Antrag. Stand, Bearbeiten und Zurückziehen finden Sie im Reiter „Meine Anträge".</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Eintrag löschen</h3>
          <p className="text-sm text-gray-600">Unten in der Liste „Meine Abwesenheiten" auf „Löschen" klicken (Smartphone: Papierkorb-Symbol).</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Zeiträume</h3>
          <p className="text-sm text-gray-600">Bei Zeiträumen werden Wochenenden, Feiertage und Ihre freien Tage laut Arbeitsplan automatisch ausgeschlossen. Nur Ihre Arbeitstage werden eingetragen – an freien Tagen erfasste Arbeitszeit bleibt stehen.</p>
        </section>
      </div>
    ),
  },

  '/profile': {
    title: 'Profil',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Passwort ändern</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Bei „Passwort ändern" auf <span className="font-medium">„Ändern"</span> klicken</li>
            <li>„Aktuelles Passwort" eingeben</li>
            <li>Neues Passwort wählen und bestätigen</li>
            <li>Auf <span className="font-medium">„Speichern"</span> klicken</li>
          </ol>
          <div className="mt-2 text-xs bg-blue-50 border border-blue-200 rounded-sm p-2 text-blue-700">
            Anforderungen: mind. 10 Zeichen, Groß- + Kleinbuchstabe, mindestens eine Ziffer.
          </div>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Kalenderfarbe</h3>
          <p className="text-sm text-gray-600">Wählen Sie Ihre Farbe im Team-Abwesenheitskalender. Die Farbe hilft dem Team, Einträge schnell zuzuordnen.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Persönliche Daten</h3>
          <p className="text-sm text-gray-600">Vorname, Nachname und E-Mail ändern Sie über „Bearbeiten" neben Ihrem Namen, das Profilbild per Klick aufs Bild. Wochenstunden, Urlaubstage und Rolle legt die Verwaltung fest. Ihre Arbeitszeit-Blöcke und deren Verlauf zeigt die Karte „Meine Arbeitszeit".</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Sicherheit und Daten</h3>
          <p className="text-sm text-gray-600">Unter „Zwei-Faktor-Authentifizierung (2FA)" richten Sie einen zweiten Faktor per Authenticator-App ein (dafür fragt PraxisZeit Ihr Passwort ab). „Meine Daten exportieren" lädt Ihre gespeicherten Daten herunter (DSGVO Art. 15/20).</p>
        </section>
      </div>
    ),
  },

  '/admin': {
    title: 'Admin-Dashboard',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Teamübersicht</h3>
          <p className="text-sm text-gray-600">Monats- bzw. Wochenübersicht aller aktiven Mitarbeitenden mit Wochenstunden, Soll, Ist, Saldo, Überstunden kumuliert und Urlaub. Umschalter „Monat"/„Woche"; die Soll-Basis „bis heute" (Standard, kein Anfangs-Minus) lässt sich auf „Monatsende" bzw. „volle Woche" stellen. Die Suche filtert nach Namen.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Ampel (Jahresübersicht, Resturlaub)</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>🟢 Grün – mehr als 5 Tage Resturlaub</li>
            <li>🟡 Gelb – bis 5 Tage</li>
            <li>🔴 Rot – kein Resturlaub mehr</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Schnellzugriff</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>Klick auf eine Zeile → Detailansicht (Zeiteinträge, Abwesenheiten, Änderungsprotokoll); dort Einträge anlegen und nicht angerechnete Zeit mit „Anerkennen" anrechnen</li>
            <li>Links in der Sidebar führen zu allen Admin-Bereichen</li>
          </ul>
        </section>
      </div>
    ),
  },

  '/admin/users': {
    title: 'Benutzerverwaltung',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Neuen Mitarbeiter anlegen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Auf <span className="font-medium">„Neue:r Mitarbeiter:in"</span> klicken</li>
            <li>Benutzername, Name, Passwort eingeben</li>
            <li>Wochenstunden/Arbeitstage, Tagesplan oder Arbeitszeit-Blöcke sowie Urlaubstage festlegen</li>
            <li>Rolle: Mitarbeiter:in oder Administrator</li>
            <li>Speichern</li>
          </ol>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Arbeitszeit ändern</h3>
          <p className="text-sm text-gray-600">Benutzer bearbeiten → <span className="font-medium">„Arbeitszeit anpassen…"</span> → Gültig ab + Modus (Gleichmäßig / Nach Tagen / Nach Arbeitsblöcken) → Auswirkung prüfen → Speichern. Rückwirkende Verkürzungen nur mit Grund und Bestätigung; historische Salden bleiben korrekt. Löschen nur an der jüngsten Zeile des Verlaufs.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Mitarbeiter deaktivieren</h3>
          <div className="text-sm bg-amber-50 border border-amber-200 rounded-sm p-2 text-amber-800">
            ⚠️ Ausgeschiedene Mitarbeitende nicht löschen, sondern in ihrer Zeile auf „Deaktivieren" klicken: Anmelden ist dann nicht mehr möglich, die Daten bleiben erhalten (§16 ArbZG: 2 Jahre aufbewahren). „Reaktivieren" holt das Konto zurück; „Inaktive anzeigen" blendet deaktivierte Konten ein. Den letzten aktiven Admin kann man nicht deaktivieren.
          </div>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">ArbZG-Ausnahme (§18)</h3>
          <p className="text-sm text-gray-600">Für leitende Angestellte kann die Checkbox „ArbZG-Prüfungen aussetzen (§18 ArbZG – leitende Angestellte)" aktiviert werden – alle Tages- und Wochengrenzwarnungen werden dann deaktiviert. Das ist unabhängig von „Stundenzählung aktiv".</p>
        </section>
      </div>
    ),
  },

  '/admin/reports': {
    title: 'Berichte & Exporte',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Export-Typen</h3>
          <ul className="space-y-2 text-sm text-gray-600">
            <li><span className="font-medium text-gray-700">Monatsreport:</span> Tägliche Einträge aller MA für einen Monat, als Excel, ODS oder PDF. Ideal für die Gehaltsabrechnung.</li>
            <li><span className="font-medium text-gray-700">Jahresreport Classic:</span> 12 Monate kompakt je Mitarbeiter:in, als Excel (Monate als Spalten) oder ODS (eine Zeile je Monat).</li>
            <li><span className="font-medium text-gray-700">Jahresreport Detailliert:</span> 365 Tage pro MA, für Steuerberater, als Excel oder ODS.</li>
          </ul>
          <p className="mt-2 text-sm text-gray-600">Monatsreport und Jahresreport Detailliert: letzte Spalte der Tageszeilen „Nicht angerechnet (Min)" – gestempelte, nicht angerechnete Zeit vor, nach und zwischen den Arbeitszeit-Blöcken. „Netto" ist die angerechnete Zeit. Der Jahresreport Classic (nur Monatswerte, keine Tageszeilen) hat diese Spalte nicht.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">ArbZG-Berichte</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>📋 <span className="font-medium">Ruhezeitverstöße (§5):</span> MA unter 11h Ruhezeit</li>
            <li>📋 <span className="font-medium">Sonntagsarbeit (§11):</span> Freie Sonntage + Ersatzruhetage</li>
            <li>📋 <span className="font-medium">Nachtarbeit (§6):</span> Nachtarbeitnehmer-Tracking</li>
            <li>📋 <span className="font-medium">24-Wochen-Durchschnitt (§3):</span> Ø angerechnet / Tag und Anwesenheit laut Stempel</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Aufbewahrung</h3>
          <div className="text-sm bg-blue-50 border border-blue-200 rounded-sm p-2 text-blue-700">
            §16 ArbZG: Exportierte Berichte mind. 2 Jahre aufbewahren.
          </div>
        </section>
      </div>
    ),
  },

  '/admin/change-requests': {
    title: 'Änderungsanträge',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Antrag prüfen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Filter „Offen" (Standard), optional eine Person wählen</li>
            <li>Alt- und Neuwerte vergleichen</li>
            <li>Begründung des Mitarbeiters lesen</li>
            <li><span className="font-medium">Genehmigen</span> oder <span className="font-medium">Ablehnen</span> – mehrere auf einmal: anhaken bzw. „Alle … auswählen", dann „… genehmigen" oder „… ablehnen"</li>
          </ol>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Nach Genehmigung</h3>
          <p className="text-sm text-gray-600">Der Zeiteintrag wird sofort aktualisiert. Mitarbeitende sehen den neuen Status unter Zeiterfassung im Tab „Anträge".</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Anrechnung beantragt</h3>
          <p className="text-sm text-gray-600">Anträge mit dem Kennzeichen „Anrechnung beantragt": „Genehmigen und anerkennen" (die beantragten Zeiten – vorbelegt die Stempel – zählen ungekappt, dauerhaft) oder „Ohne Anerkennen genehmigen" (nur die beantragten Zeiten, an den Arbeitszeit-Blöcken gekappt). Für andere Anträge zu Einträgen mit nicht angerechneter Zeit gibt es neben „Genehmigen" zusätzlich „Genehmigen und anerkennen". Die Sammel-Genehmigung fragt bei Anrechnungsanträgen nach („Alle genehmigen").</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Bei Ablehnung</h3>
          <p className="text-sm text-gray-600">Optional einen Ablehnungsgrund eingeben – dieser wird dem MA angezeigt.</p>
        </section>
      </div>
    ),
  },

  '/admin/audit-log': {
    title: 'Änderungsprotokoll',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Was wird protokolliert?</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>Änderungen an Zeiteinträgen und Abwesenheiten – Spalte „Quelle": Manuell (von Hand angelegt oder geändert – durch die Verwaltung oder in der Zeiterfassung; wer, steht unter „Geändert von"), Ausstempeln, Automatisch geschlossen, Antrag, Import, Pausen-Verzicht, Stundenänderung, Neukappung (Arbeitszeit-Änderung), Anrechnung anerkannt u. a.</li>
            <li>Zugriffe auf Gesundheitsdaten, Exporte und DSGVO-Vorgänge (Anonymisieren, Endgültig löschen)</li>
            <li>Karte „Konto-Vorgänge": Deaktivieren, Reaktivieren, Rollenwechsel, von der Verwaltung gesetzte Passwörter sowie Notfall-Vorgänge per Kommandozeile (Passwort zurückgesetzt, Zwei-Faktor abgeschaltet)</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Filtern</h3>
          <p className="text-sm text-gray-600">Monat wählen (Pfeile) und optional eine Person („Alle Mitarbeitende"). Das Protokoll ist chronologisch sortiert (neueste zuerst).</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Rechtliche Bedeutung</h3>
          <div className="text-sm bg-blue-50 border border-blue-200 rounded-sm p-2 text-blue-700">
            Das Audit-Log dient als Nachweis für Änderungen gemäß §16 ArbZG. Einträge können nicht gelöscht werden.
          </div>
        </section>
      </div>
    ),
  },

  '/admin/absences': {
    title: 'Abwesenheiten (Admin)',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Mitarbeiter-Abwesenheiten</h3>
          <p className="text-sm text-gray-600">Abteilung, Mitarbeiter und Monat wählen – die Liste zeigt die Abwesenheiten (bei „Alle Mitarbeiter" je Person aufklappbar, mit „+ Eintragen"); Löschen über das Papierkorb-Symbol in der Spalte „Aktion".</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Abwesenheit für MA eintragen</h3>
          <p className="text-sm text-gray-600">Mitarbeiter in der Dropdown-Liste wählen → „Abwesenheit eintragen" → Formular wie bei der Selbsteintragung, zusätzlich mit „Bezahlte Freistellung (kein Urlaubsabzug)".</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Betriebsferien eintragen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Reiter „Betriebsferien" → <span className="font-medium">„Betriebsferien erstellen"</span></li>
            <li>Bezeichnung + Von–Bis eintragen</li>
            <li>Verrechnung wählen: „Als Urlaub werten" (vom Urlaubskonto abgezogen) oder „Bezahlte Freistellung" (wie ein Feiertag, kein Urlaubsabzug)</li>
            <li>„Betriebsferien erstellen &amp; Urlaub eintragen" → alle teilnehmenden MA erhalten automatisch Einträge</li>
          </ol>
        </section>
      </div>
    ),
  },

  '/admin/errors': {
    title: 'Fehler-Monitoring',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Fehler-Log</h3>
          <p className="text-sm text-gray-600">Automatisch erfasste Anwendungsfehler (Backend-Exceptions) mit Zeitstempel, Stacktrace und SHA256-Deduplizierung.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">GitHub-Integration</h3>
          <p className="text-sm text-gray-600">Fehler können direkt als GitHub Issue gemeldet werden. Dazu muss ein GitHub-Token in den Einstellungen hinterlegt sein.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Fehler auflösen</h3>
          <p className="text-sm text-gray-600">Nach Behebung eines Fehlers auf „Auflösen" klicken – der Eintrag wird als erledigt markiert und taucht nicht mehr in der offenen Liste auf.</p>
        </section>
      </div>
    ),
  },
};

export const getFallbackHelp = (): HelpEntry => ({
  title: 'Hilfe & Navigation',
  content: (
    <div className="space-y-4">
      <section>
        <h3 className="font-semibold text-gray-800 mb-2">Navigation</h3>
        <ul className="space-y-1 text-sm text-gray-600">
          <li>🏠 <span className="font-medium">Dashboard</span> – Ihre tägliche Übersicht</li>
          <li>⏱️ <span className="font-medium">Zeiterfassung</span> – Einträge · Journal · Anträge</li>
          <li>📅 <span className="font-medium">Abwesenheiten</span> – Urlaub, Krank, etc.</li>
          <li>👤 <span className="font-medium">Profil</span> – Passwort & Einstellungen</li>
        </ul>
      </section>
      <section>
        <h3 className="font-semibold text-gray-800 mb-2">Änderungsanträge</h3>
        <p className="text-sm text-gray-600">Zeiterfassung → „Antrag" (vergangener Tag) bzw. am gesperrten Eintrag „Änderungsantrag stellen"; den Stand zeigt der Tab „Anträge".</p>
      </section>
      <section>
        <h3 className="font-semibold text-gray-800 mb-2">Journal</h3>
        <p className="text-sm text-gray-600">Zeiterfassung → Tab „Journal" – Monatsübersicht mit allen Tagen.</p>
      </section>
      <section>
        <h3 className="font-semibold text-gray-800 mb-2">Weiteres</h3>
        <p className="text-sm text-gray-600">Klicken Sie auf „Hilfe" in der Sidebar für die vollständige Kurzanleitung und das Handbuch.</p>
      </section>
    </div>
  ),
});
