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
            <li><span className="font-medium text-gray-700">Monatssaldo:</span> Differenz zwischen geleisteten und Soll-Stunden im aktuellen Monat. Grün = Überstunden, Rot = Fehlstunden.</li>
            <li><span className="font-medium text-gray-700">Überstunden gesamt:</span> Kumulierter Saldo über alle Monate.</li>
            <li><span className="font-medium text-gray-700">Urlaub verbleibend:</span> Noch nicht genommene Urlaubstage im laufenden Jahr.</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Überstunden-Diagramm</h3>
          <p className="text-sm text-gray-600">Das Balkendiagramm zeigt den Monatssaldo der letzten 6 Monate. Blau = positiv, Rot = negativ.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Meine heutigen Einträge</h3>
          <p className="text-sm text-gray-600">Zeigt alle Zeiteinträge für heute. Klicken Sie auf „Zur Zeiterfassung" um direkt zu bearbeiten.</p>
        </section>
      </div>
    ),
  },

  '/time-tracking': {
    title: 'Zeiterfassung',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Eintrag erstellen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Klicken Sie auf <span className="font-medium">„Hinzufügen"</span></li>
            <li>Datum, Start- und Endzeit eintragen</li>
            <li>Pause in Minuten eingeben (Pflicht!)</li>
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
          <h3 className="font-semibold text-gray-800 mb-2">Wochenansicht</h3>
          <p className="text-sm text-gray-600">Mit den Pfeilen &larr; &rarr; zwischen Wochen navigieren. Die aktuelle Woche ist vorausgewählt.</p>
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
            <li>Typ wählen: Urlaub / Krank / Fortbildung / Sonstiges</li>
            <li>Einzeltag: nur Startdatum; Zeitraum: Checkbox aktivieren + Enddatum</li>
            <li>Optional: Notiz</li>
            <li>Speichern</li>
          </ol>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Abwesenheitstypen</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>🔵 <span className="font-medium">Urlaub</span> – zieht vom Urlaubskonto ab</li>
            <li>🔴 <span className="font-medium">Krank</span> – keine Urlaubswirkung</li>
            <li>🟠 <span className="font-medium">Fortbildung</span> – gilt als Arbeitszeit</li>
            <li>⚫ <span className="font-medium">Sonstiges</span> – freie Verwendung</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Eintrag löschen</h3>
          <p className="text-sm text-gray-600">Im Kalender auf den farbigen Eintrag klicken → Löschen-Symbol erscheint.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Zeiträume</h3>
          <p className="text-sm text-gray-600">Bei Zeiträumen werden Wochenenden und Feiertage automatisch ausgeschlossen. Nur Werktage werden eingetragen.</p>
        </section>
      </div>
    ),
  },

  '/change-requests': {
    title: 'Korrekturanträge',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Wann ein Antrag nötig ist</h3>
          <p className="text-sm text-gray-600">Vergangene Zeiteinträge können nicht direkt bearbeitet werden. Stellen Sie einen Korrekturantrag, wenn Sie einen Fehler bemerken.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Antrag stellen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Auf <span className="font-medium">„Neuer Antrag"</span> klicken</li>
            <li>Betroffenes Datum wählen</li>
            <li>Korrekte Start-/Endzeit und Pause eintragen</li>
            <li>Begründung schreiben</li>
            <li>Absenden</li>
          </ol>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Status verfolgen</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>🟡 <span className="font-medium">Ausstehend</span> – wartet auf Admin-Entscheidung</li>
            <li>🟢 <span className="font-medium">Genehmigt</span> – Zeiteintrag wurde angepasst</li>
            <li>🔴 <span className="font-medium">Abgelehnt</span> – Ablehnungsgrund prüfen</li>
          </ul>
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
            <li>Altes Passwort eingeben</li>
            <li>Neues Passwort wählen</li>
            <li>Passwort bestätigen</li>
            <li>Auf <span className="font-medium">„Speichern"</span> klicken</li>
          </ol>
          <div className="mt-2 text-xs bg-blue-50 border border-blue-200 rounded p-2 text-blue-700">
            Anforderungen: mind. 10 Zeichen, Groß- + Kleinbuchstabe, mindestens eine Ziffer.
          </div>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Kalenderfarbe</h3>
          <p className="text-sm text-gray-600">Wählen Sie Ihre Farbe im Team-Abwesenheitskalender. Die Farbe hilft dem Team, Einträge schnell zuzuordnen.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Persönliche Daten</h3>
          <p className="text-sm text-gray-600">Persönliche Daten (Name, Wochenstunden) können nur vom Admin geändert werden.</p>
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
          <p className="text-sm text-gray-600">Das Admin-Dashboard zeigt alle aktiven Mitarbeiter mit ihren aktuellen Monatssalden, Überstunden und Urlaubskonten.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Ampel-System</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>🟢 Grün – Resturlaub ≥ 50% des Budgets</li>
            <li>🟡 Gelb – Resturlaub 25–50%</li>
            <li>🔴 Rot – Resturlaub unter 25%</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Schnellzugriff</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>Klick auf Mitarbeiter → Detailansicht (Einträge + Abwesenheiten)</li>
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
            <li>Auf <span className="font-medium">„Neuer Benutzer"</span> klicken</li>
            <li>Benutzername, Name, Passwort eingeben</li>
            <li>Wochenstunden, Arbeitstage, Urlaubstage festlegen</li>
            <li>Rolle: Mitarbeiter oder Admin</li>
            <li>Speichern</li>
          </ol>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Stundenänderung (Teilzeit)</h3>
          <p className="text-sm text-gray-600">Benutzer bearbeiten → Neue Wochenstunden + Wirkungsdatum eintragen. Historische Salden bleiben korrekt erhalten.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Mitarbeiter deaktivieren</h3>
          <div className="text-sm bg-amber-50 border border-amber-200 rounded p-2 text-amber-800">
            ⚠️ Niemals löschen! Nur Status auf „Inaktiv" setzen. Daten müssen 2 Jahre aufbewahrt werden (§16 ArbZG).
          </div>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">ArbZG-Ausnahme (§18)</h3>
          <p className="text-sm text-gray-600">Für leitende Angestellte kann die Checkbox „ArbZG-Ausnahme" aktiviert werden – alle Tages- und Wochengrenzwarnungen werden dann deaktiviert.</p>
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
            <li><span className="font-medium text-gray-700">Monatsreport:</span> Tägliche Einträge aller MA für einen Monat. Ideal für die Gehaltsabrechnung.</li>
            <li><span className="font-medium text-gray-700">Jahresreport Classic:</span> 12 Monate kompakt, schnell (~2 Sek.).</li>
            <li><span className="font-medium text-gray-700">Jahresreport Detailliert:</span> 365 Tage pro MA, für Steuerberater (~5 Sek.).</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">ArbZG-Berichte</h3>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>📋 <span className="font-medium">Ruhezeitverstöße (§5):</span> MA unter 11h Ruhezeit</li>
            <li>📋 <span className="font-medium">Sonntagsarbeit (§11):</span> Freie Sonntage + Ersatzruhetage</li>
            <li>📋 <span className="font-medium">Nachtarbeit (§6):</span> Nachtarbeitnehmer-Tracking</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Aufbewahrung</h3>
          <div className="text-sm bg-blue-50 border border-blue-200 rounded p-2 text-blue-700">
            §16 ArbZG: Exportierte Berichte mind. 2 Jahre aufbewahren.
          </div>
        </section>
      </div>
    ),
  },

  '/admin/change-requests': {
    title: 'Korrekturanträge (Admin)',
    content: (
      <div className="space-y-4">
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Antrag prüfen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Offenen Antrag in der Liste wählen</li>
            <li>Alt- und Neuwerte vergleichen</li>
            <li>Begründung des Mitarbeiters lesen</li>
            <li><span className="font-medium">Genehmigen</span> oder <span className="font-medium">Ablehnen</span></li>
          </ol>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Nach Genehmigung</h3>
          <p className="text-sm text-gray-600">Der Zeiteintrag wird sofort aktualisiert. Der MA sieht den neuen Status in seinem Bereich „Korrekturanträge".</p>
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
            <li>Alle Admin-Aktionen (Benutzer anlegen/bearbeiten)</li>
            <li>Zeiteintrags-Änderungen durch Admins</li>
            <li>Genehmigte/abgelehnte Korrekturanträge</li>
            <li>Passwortänderungen</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Filtern</h3>
          <p className="text-sm text-gray-600">Nach Benutzer, Zeitraum oder Aktionstyp filtern. Das Protokoll ist chronologisch sortiert (neueste zuerst).</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Rechtliche Bedeutung</h3>
          <div className="text-sm bg-blue-50 border border-blue-200 rounded p-2 text-blue-700">
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
          <h3 className="font-semibold text-gray-800 mb-2">Team-Kalender</h3>
          <p className="text-sm text-gray-600">Übersicht aller Mitarbeiter-Abwesenheiten im Monatskalender. Jeder MA hat eine eigene Farbe (in der Benutzerverwaltung festlegbar).</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Betriebsferien eintragen</h3>
          <ol className="space-y-1 text-sm text-gray-600 list-decimal list-inside">
            <li>Auf <span className="font-medium">„Neue Betriebsferien"</span> klicken</li>
            <li>Bezeichnung + Von–Bis eintragen</li>
            <li>Speichern → alle MA erhalten automatisch Einträge</li>
          </ol>
          <p className="text-sm text-gray-500 mt-1">Betriebsferien ziehen keine Urlaubstage ab.</p>
        </section>
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Abwesenheit für MA eintragen</h3>
          <p className="text-sm text-gray-600">Mitarbeiter in der Dropdown-Liste wählen → Formular wie bei MA-Selbsteintragung.</p>
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
          <li>🏠 <span className="font-medium">Dashboard</span> – Ihre Übersicht</li>
          <li>⏱️ <span className="font-medium">Zeiterfassung</span> – Arbeitszeiten eintragen</li>
          <li>📅 <span className="font-medium">Abwesenheiten</span> – Urlaub, Krank, etc.</li>
          <li>📋 <span className="font-medium">Korrekturanträge</span> – Korrekturen beantragen</li>
          <li>👤 <span className="font-medium">Profil</span> – Passwort & Einstellungen</li>
        </ul>
      </section>
      <section>
        <h3 className="font-semibold text-gray-800 mb-2">Weiteres</h3>
        <p className="text-sm text-gray-600">Auf der Hilfe-Seite finden Sie die vollständige Kurzanleitung und das Handbuch.</p>
      </section>
    </div>
  ),
});
