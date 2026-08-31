# Changelog

## [Unreleased]

## [1.19.0] - 2026-08-29

Minor-Release. Notfall-Zugang bei verlorenem Admin-Passwort (#425), ehrlicher
Dienststatus im nativen Betrieb (#427), Freitext-Anonymisierung nach Art. 17
DSGVO (#440) und die Schichtplan-Darstellung (#443/#450/#452/#453). Zwei
Migrationen (070, 071).

### ✨ Neu
- **Admin-Passwort-Reset auf dem Server (#425).** Ist kein Administrator-Konto
  mehr erreichbar, setzt `praxiszeit-server.py reset-admin-password` (nativ)
  bzw. `python -m app.cli.reset_admin_password` (Docker) das Passwort direkt in
  der Datenbank neu — ohne Anmeldung, mit denselben Passwortregeln wie die
  Anwendung, und invalidiert alle Sitzungen des Kontos (`token_version`).
  `--disable-2fa` schaltet im selben Zug den zweiten Faktor ab, `--username`
  wählt ein anderes Konto. Jeder Vorgang landet in `security_events` (Zeitpunkt,
  Konto, auslösendes OS-Konto) — Nachweispflicht nach Art. 5 Abs. 2 DSGVO.
- **Schichtplan freigeben, drucken und lesbar darstellen (#443, #450).**
  Neuer Plan-Schalter „Für Mitarbeitende sichtbar" macht einen Plan unabhängig
  vom Aktiv-Datums-Fenster sichtbar (auch vor Beginn und nach Ablauf; eine Kopie
  erbt die Freigabe nicht). Neues Feld **Hinweis** je Einteilung (500 Zeichen,
  Darstellung mit vorangestelltem `»`) — im Raster, im PDF und auf der
  Dashboard-Kachel (#453). PDF-Aushang im Querformat (Arbeitsplatz × Wochentag),
  auch für Mitarbeitende; nicht geltende Pläne tragen den Vermerk „Vorschau —
  gilt derzeit nicht" bzw. „Nicht mehr gültig". Standort einheitlich in der
  Kopfzeile, bei gemischten Standorten hinter dem Arbeitsplatznamen (#452).
  „Auf Wochentage kopieren" nimmt den Hinweis mit.
- **Jahresende-Überstundenprojektion je Mandant abschaltbar (#430).** Zwei
  getrennte Settings (`SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD` /
  `..._ADMIN_DASHBOARD`, Default `True`) blenden die Projektion im
  Mitarbeiter- bzw. Admin-Dashboard aus; ist sie aus, wird
  `future_freizeitausgleich_impact` gar nicht erst aufgerufen. Reine
  Anzeige-Gates — das Überstundenkonto rechnet unverändert weiter.

### 🐞 Korrekturen
- **Dienststatus meldete `active` bei totem Backend (#427).** Die
  Gesundheitsprüfung akzeptierte jede Antwort auf dem Port — bei belegtem Port
  also die eines fremden Prozesses. Jetzt entscheidet der eigene Prozess, ein
  belegter Port wird vorab im Klartext gemeldet, und nach wiederholten
  Abstürzen endet der Dienst ehrlich in `failed`.
- **Monatsjournal widersprach der Monatssumme im festen Monats-Soll-Modus
  (#463).** Die Tageszeilen tragen dort die geplante Anwesenheit
  (`_fixed_planned_hours`), kein Tages-Soll — ein solches gibt es im flachen
  Monats-Soll nicht. Bezahlte Fehltage (Feiertag + `_FIXED_PAID_CREDIT_TYPES`)
  schreiben die geplanten Stunden jetzt auch in der Tageszeile dem Ist gut,
  dieselbe Menge wie `fixed_month_credit`. Die Antwort trägt
  `use_fixed_monthly_target`, damit die Oberfläche die Spalte als „Geplant"
  beschriften und den bedeutungslosen Tages-Saldo ausblenden kann; verbindlich
  bleibt `monthly_summary`.
- **Schichtplanung: Release-Nachzug (#461).** PDF-Ausdruck mit
  nicht-lateinischen Plannamen, Reihenfolge der Arbeitsplätze im Aushang,
  Entwürfe erschienen fälschlich als freigegeben.
- **Betriebsferien-Zuordnung neuer Mitarbeitender chronologisch aufteilen
  (#448).** Trat jemand mitten in eine Schließung ein, wurden die Schließtage
  nicht am Eintrittsdatum getrennt.
- **`tenants.slug` blieb bei der Mandanten-Anonymisierung stehen (#435).**

### 🔒 Security / DSGVO
- **Freitexte überstehen die Art.-17-Löschung nicht mehr (#440).**
  Begründungen von Änderungs- und Urlaubsanträgen, Notizen und
  Ablehnungsgründe werden geleert; die Vorgänge selbst bleiben nachweisbar.
- Eingebetteter Interpreter aller nativen Pakete auf **CPython 3.13.15 /
  OpenSSL 3.5.8** (vorher 3.13.13 / 3.5.6).

### ⚡ Performance
- Vertrags-Snapshot je Mitarbeitendem einmal laden statt pro Tag (#449).

### 📖 Dokumentation
- Admin-Handbuch: neuer Abschnitt „Admin-Passwort verloren", Journal im
  Fixmodus, Projektions-Schalter, Schichtplan-Freigabe/Hinweis/PDF.
- Mitarbeiter-Handbuch: Schichtplan-Sichtbarkeit und Vorschau-Auswahl,
  abschaltbare Jahresende-Zeile. Cheat-Sheets und In-App-Hilfe synchron.
- `docs/SCHICHTPLANUNG.md`, `INSTALLATION.md`, `NATIVE-BETRIEB.md`,
  `setup-windows.md` nachgezogen.

### 🗄️ Migration
- `070` — Schichtplan: `visible_to_employees` (Plan) + `note` (Einteilung)
- `071` — `security_events` (Nachweis serverseitiger Eingriffe, Art. 5 Abs. 2 DSGVO)

### Tests
Backend 2187, Frontend 371, E2E 147, nativer Lebenszyklus 68, Postgres-only 44.
Installation + echter Login auf Windows 11 (Emulator, PostgreSQL 18.4), Linux
nativ, Docker sowie als Update einer Bestandsinstallation in beiden Varianten.
`validate-release` auf fünf Distributionen.

## [1.18.2] - 2026-08-12

Patch-Release. Update aus jeder 1.18.x ohne Zwischenschritte; **keine neue
Migration** (head bleibt `069_weekly_hours_precision`).

### 🐞 Korrekturen
- **Betriebsferien-Neuspeichern löschte Schließtage mit gebuchter Arbeitszeit
  ersatzlos.** Bei aktivem „Betriebsferien über Urlaub hinaus als
  Überstundenabbau" genügte ein Umbenennen der Schließung, damit ein Urlaubstag
  verschwand, an dem nachträglich Arbeitszeit erfasst worden war — das
  Protokoll behauptete dabei, die Tage würden neu gebucht.
- **Datumskorrektur eines Zeiteintrags** kappte die bereits gekappte Zeit ein
  zweites Mal und überschrieb den Rohstempel. Der Rohstempel ist der Nachweis
  der tatsächlichen Anwesenheit (§ 16 ArbZG) und die Grundlage der
  Ruhezeitprüfung (§ 5) — ein echter Verstoß wäre dadurch unentdeckt geblieben.
- **Halbtags-Urlaubsantrag ließ sich nachträglich zu einem Zeitraum umbauen**
  und wurde dann an jedem Werktag als halber Tag gebucht: fünf freie Tage
  kosteten 2,5 Urlaubstage, und an jedem Tag blieb ein halbes Tagessoll offen.
- **Betriebsferien akzeptierten beliebig lange Zeiträume.** Ein Zahlendreher im
  Jahr hätte in einem Vorgang die rückwirkende Zeiterfassung der ganzen Praxis
  gelöscht. Jetzt wie beim Urlaubsantrag auf ein Jahr begrenzt.
- **ODS-Export** ließ am Wochenende die Bemerkung der Mitarbeitenden weg,
  sobald ein § 10-Ausnahmegrund erfasst war; Excel und PDF zeigten beides.
- **Farbauswahl in der Benutzerverwaltung** überdeckte Beschriftung und
  Hilfetext (aus dem Bug-Tracker).
- **Wochenstunden beim Anlegen** nehmen jetzt Viertelstunden an — der
  Bearbeiten-Dialog konnte das längst (aus dem Bug-Tracker).

### 📦 Dependencies
- Sicherheitsaktualisierungen für undici, js-yaml, fast-uri, ip-address,
  brace-expansion und nanoid (Build-/Test-Abhängigkeiten, nicht Teil der
  ausgelieferten Anwendung). `npm audit`: 0 Schwachstellen.

### 📖 Dokumentation
- `INSTALLATION.md` weist auf `COOKIE_SECURE=false` für den HTTP-Betrieb hin —
  ohne den Eintrag landet man nach jedem Neuladen wieder auf der Anmeldeseite.
- Admin-Handbuch beschreibt die Wochenstunden-Eingabe korrekt in
  Viertelstunden (Datei und In-App-Hilfe).

### Tests
Backend 2051, Postgres-Integration 44 (RLS, Nebenläufigkeit, Art.-17-Löschung),
Frontend 323, `validate-release` auf 5 Distributionen, Docker- und
Native-Update mit inhaltsgleicher Datenbank über alle 26 Tabellen, Windows 11
im Emulator (Installation, Anmeldung, Dienst-Neustart, Rechte-Härtung).

## [1.18.1] - 2026-08-03

Patch-Release. **Keine neue Migration** — Schema bleibt auf `069`.

### 🐞 Korrekturen
- **Betriebsferien: Schließtage wurden fälschlich als Freizeitausgleich
  gebucht.** Wurde ein Eintrittsdatum nachträglich vorgezogen (Datenkorrektur,
  Wiedereinstellung, nachgetragener Eintritt), zehrten die davor liegenden
  Schließtage das Urlaubsbudget auf, und die echten Schließtage landeten auf
  dem Überstundenkonto — gemessen 40 Stunden zulasten des Kontos, während die
  Urlaubsübersicht daneben fünf Resturlaubstage meldete; die ungenutzten Tage
  gingen anschließend in den Jahresübertrag. Laufende Jahre korrigieren sich
  mit dem Update von selbst, bereits abgeschlossene nicht (Übertrag von Hand
  prüfen).
- **Urlaubsverbrauch respektiert das Beschäftigungsfenster (#193).**
  Urlaubstage vor `first_work_day` oder nach `last_work_day` zählen nicht mehr
  als Verbrauch — zuvor kürzte die Funktion nur das Budget anteilig, zählte
  aber jede gebuchte Zeile mit (Resturlaub 10 statt 15). Der Resturlaub ist die
  Grundlage der Urlaubsabgeltung (§ 7 Abs. 4 BUrlG).
- **Rückrechnung wandte den Sondertagsfaktor doppelt an.** Sie schrieb den
  gewichteten statt des ungewichteten Tagessolls in `Absence.hours`; seit
  `credit_day_weight` auf der Leseseite zählte der Faktor damit zweimal — ein
  als halber Feiertag konfigurierter 24.12. mit Krankmeldung stand mit 2,00 h
  Soll gegen 1,00 h Gutschrift. Verschärfend wich der gespeicherte Wert am
  Sondertag dadurch immer vom neu berechneten ab: die Rückrechnung war an
  diesen Tagen nicht idempotent.

### 🔒 Security / DSGVO
- **Anonymisierung ließ den Klarnamen im Änderungsprotokoll stehen.** Beide
  Wege — einzelne Mitarbeitende wie ganzer Mandant — schrubbten die Stammdaten,
  nicht aber E-Mail-Adresse und Benutzername in den Freitext-Notizen des
  Protokolls. Die Manipulationssicherung des Protokolls bleibt intakt.

### 🐞 Bedienung
- **Nur-Lese-Betrieb wurde nicht erklärt.** Bei ungültiger Lizenzsignatur,
  abgelaufener Demo oder unlesbarem Demo-Datum sperrte die Anwendung jedes
  Speichern mit einer 403-Meldung, ohne dass die Oberfläche den Grund nennen
  konnte.

### 📖 Dokumentation
- Berechnungsdoku, Handbücher und In-App-Hilfe auf den tatsächlichen Stand
  gezogen — inklusive der Einschränkung, dass sich abgeschlossene Jahre nicht
  von selbst korrigieren.

### Tests
Backend 2047 lokal / 2096 in der CI, Postgres 44, Frontend 320, E2E 145,
5/5 Linux-Distributionen (PostgreSQL 18.4), Docker lokal + `.131` nativ (HTTPS)
+ `.131` Docker aus dem Paket (Daten byte-identisch, echter Login),
Windows 11 Neuinstallation.

## [1.18.0] - 2026-07-31

Minor-Release. Wochenstunden mit Wirkungsdatum jetzt auch für individuelle
Tagespläne (#431) — samt Vorschau, Revisionssicherheit und Ausweisung in
Berichten. Drei Migrationen (067, 068, 069).

### ✨ Neu
- **Stundenhistorie für individuelle Tagespläne (#431).** Mitarbeitende mit
  Tagesplan hatten bisher keinen Stundenverlauf: der Button fehlte im Formular,
  der Endpunkt lehnte sie ab. Jede Vertragsänderung verschob damit still das
  Soll bereits abgeschlossener Monate — ohne Protokoll, ohne Rückrechnung der
  gebuchten Abwesenheits-Stunden, ohne Warnung bei abgeschlossenen Jahren.
- **Dialog „Wochenstunden & Tagesplan"** für alle Mitarbeitenden, umschaltbar
  zwischen gleichmäßigen Wochenstunden und Tagesplan (Mo–Fr einzeln,
  Viertelstunden) — immer mit Wirkungsdatum.
- **Vorschau vor dem Speichern:** Tagessoll je Wochentag (alt → neu),
  betroffene Abwesenheiten sowie Überstundensaldo und Urlaubstage
  vorher/nachher. Rückwirkende Änderungen und solche, die gebuchte Zeilen
  umschreiben, müssen ausdrücklich bestätigt werden.
- **Wochenstunden, Tagesstunden, Modus und Arbeitstage sind im
  Bearbeiten-Formular nur noch Anzeige** — geändert wird ausschließlich über
  den Dialog. `PUT /api/admin/users/{id}` lehnt diese Felder mit 400 ab.
- **Berichte und Exporte weisen einen Tagesplan-Wechsel aus**
  („ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche", bei reinem
  Arbeitstage-Wechsel „ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage").
- **Revisionssicherheit:** der beim Buchen gesetzte Stundenwert einer
  Abwesenheit bleibt erhalten, und jede von einer Stundenänderung nachgezogene
  Abwesenheit wird einzeln protokolliert (Datum, alt, neu, Auslöser). Das
  Änderungsprotokoll zeigt diese Angaben jetzt auch an — bisher blieb der
  Notiztext dort unsichtbar. Stundenhistorie zusätzlich im DSGVO-Export und im
  §16-Notfall-Export des Superadmins.

### 🐞 Korrekturen
- **Phantom-Saldo** bei einer Abwesenheit auf einem Tag mit erfasster
  Arbeitszeit (volles Tagessoll *und* die gearbeiteten Stunden im Ist).
- **§16-Datei-Exporte ignorierten in den Tageszeilen das
  Beschäftigungsfenster** — im Eintrittsmonat widersprachen sich Detail- und
  Summenzeile desselben Blatts. Die Summenzeilen ziehen ihre Ist-Zahl jetzt
  direkt aus `get_monthly_actual`.
- **`users.weekly_hours` auf `Numeric(4,2)`** — der Resync rundete still.
- **Nativer Betrieb verwarf die Ausgabe der Migrationen bei Erfolg**; dort
  benennen Migrationen Konten, die von Hand nachzuziehen sind.

### 🔒 Security / DSGVO
- Zugriffsvermerk für das Änderungsprotokoll (Art. 5 Abs. 2 DSGVO).

### 🗄️ Migration
- `067` — Tagesplan in der Vertragshistorie (+ Backfill `weekly_hours`)
- `068` — Abwesenheits-Rohwert (revisionssichere Stunden)
- `069` — `weekly_hours`-Präzision

> **Beim Update die Migrations-Ausgabe lesen:** bei Mitarbeitenden, deren
> hinterlegte Tagesstunden zusammen mehr als 60 Stunden pro Woche ergeben,
> lässt die Migration den Vertragswert bewusst unverändert und benennt das
> Konto.

## [1.17.0] - 2026-07-26

Minor-Release. **Keine neue Migration** (Stand bleibt `066`).

### ✨ Neu
- **Wochenstunden werden ausschließlich über den Dialog mit Wirkungsdatum
  geändert (#423).** `PUT /api/admin/users/{id}` weist `weekly_hours` mit 400
  ab.

### 🐞 Korrekturen
- **Rückrechnung der Wochenstunden greift jetzt vollständig (#415).** Sie zog
  die gespeicherten Stunden bereits gebuchter Abwesenheiten nur bis heute nach
  — und lief überhaupt nur bei einem Wirkungsdatum in der Vergangenheit.
  Beides war zu eng: Urlaub, Betriebsferien und Fortbildungen werden
  regelmäßig im Voraus gebucht (bei Krankheit und Fortbildung ergab das einen
  falschen Saldo, bei Urlaub einen widersprüchlichen §16-Nachweis), und der
  Regelfall des Dialogs ist ein Datum in der Zukunft. Urlaubs**tage** bleiben
  unberührt (Tagesprinzip), ebenso Freizeitausgleich und Mitarbeitende ohne
  Stundenzählung.
- **Update der nativen Installation repariert (#421).** Unter macOS wurde beim
  Update der Dienst weder gestoppt noch neu geladen — das Update meldete
  Erfolg, die alte Version lief weiter. Brach ein Update ab, blieb der Dienst
  dauerhaft gestoppt. Der Port aus der bestehenden Konfiguration wurde
  ungeprüft übernommen. Die Abschlussprüfung verwarf ihr Ergebnis:
  „erfolgreich installiert" erschien auch bei nicht ansprechbarem Dienst.
- **Ungespeicherte Eingaben im Benutzerformular** gingen bei
  Hintergrund-Aktualisierungen verloren. Der Warnhinweis erschien nur bei
  Datum in der Vergangenheit, obwohl ein zukünftiges Datum genauso bereits
  gebuchte Abwesenheiten trifft. Dazu: sichtbare Begründung, wenn die Vorschau
  blockiert oder scheitert.

### 📦 Dependencies
- Drei Schwachstellen hoher Einstufung in Frontend-Abhängigkeiten geschlossen
  (js-yaml, fast-uri, postcss).

### Tests
Backend 1524, Frontend 245, 5/5 Linux-Distributionen, Docker-Update
1.16.0 → 1.17.0 (Daten unverändert), Docker-Neuinstallation, natives Update
und native Erstinstallation, Windows-Installation in der VM (PostgreSQL 18.4).

## [1.16.0] - 2026-07-25

Minor-Release. Zwei nutzersichtbare Features, vier Security-Fixes und 21
Korrekturen aus dem Release-Review. **Keine Migration** — das Update ist ein
reiner Programm-Austausch.

### ✨ Neu
- **Voraussichtlicher Überstundensaldo zum Jahresende (#402).** Zeigt den
  aktuellen Saldo abzüglich des bereits gebuchten künftigen
  Freizeitausgleichs, im Mitarbeiter-Dashboard und in der Admin-Übersicht.
- **Stundenänderungen in Monats- und Jahresberichten (#415).** Wechselt die
  Wochenstundenzahl mitten im Berichtszeitraum, weisen die Berichte den zu
  Zeitraumsbeginn gültigen Wert aus und nennen die Änderung daneben
  („ab 15.03.2026: 20,0 Std/Woche") — im Admin-Dashboard ebenso wie in Excel,
  ODS und PDF. Die Jahresübersicht bekommt dafür eine zusätzliche Spalte am
  Ende, bestehende Spaltenpositionen bleiben unverändert.

### 🔒 Security / DSGVO
- **2FA-Einrichtung verlangt jetzt das aktuelle Passwort (#416).** Bisher
  konnte jeder mit einer offenen Sitzung den zweiten Faktor austauschen — der
  Authenticator des Kontoinhabers wurde ungültig, der des Angreifers gültig,
  ohne dass das Passwort je bekannt war.
- **`/api/settings` gibt ohne Login keine Lizenznehmer-Identität mehr preis**
  (Praxisname, Mitarbeiterzahl, Ablaufstatus).
- **Impersonation-Token wird beim Logout des Admins ungültig**, die offene
  Sitzung im Nachweis-Log geschlossen.
- **Fehler-Deduplizierung ist tenant-gescoped (#418)** — im
  Mehrmandanten-Betrieb konnte im Fehler-Monitor sonst ein Traceback aus einem
  fremden Mandanten erscheinen.

### 🐞 Korrekturen mit Datenrelevanz
- **Betriebsferien umbenennen konnte Abwesenheiten unwiederbringlich löschen.**
  Bei aktiviertem Überstunden-Split entfernte schon ein reines Speichern die
  Abwesenheiten ausgeschiedener Mitarbeiter, ohne sie neu anzulegen —
  genommener Urlaub verschwand rückwirkend. Beide Löschpfade schreiben jetzt
  zusätzlich einen Nachweis-Eintrag.
- **Datei-Exporte setzten das Tages-Soll bei jeder Abwesenheit auf 0.** Falsch
  bei halben Tagen, bei Krank/Fortbildung und beim Überstundenausgleich: ein
  halber Urlaubstag plus vier gearbeitete Stunden erschien als +4 Überstunden,
  während „Überstunden kumuliert" im selben Dokument etwas anderes sagte.
- **Ausgeschiedene Mitarbeiter fehlten komplett in den §16-Belegen** — obwohl
  das Handbuch anweist, sie auf inaktiv zu setzen statt zu löschen.
- **Eine Stundenänderung mit Wirkungsdatum „heute" verschob still das Soll
  bereits abgeschlossener Monate.**
- **Änderungsantrags-Pfad** buchte halbe Tage falsch, ignorierte Feiertage und
  verdoppelte bei Zeit-Korrekturen die Ist-Gutschrift halbtägiger
  Abwesenheiten.
- **Ein §18-befreiter Admin konnte für eine nicht befreite Mitarbeiterin einen
  12-Stunden-Tag speichern** (Prüfung lief gegen den Admin statt gegen den
  Eintrags-Eigentümer).

### 📖 Dokumentation
- `bash tools/docker/generate-secrets.sh` brach beim dokumentierten Aufruf
  immer ab — behoben. Backup-Cron und Restore-Befehl in der Doku passten nicht
  zusammen. Die In-App-Kurzanleitung behauptete, Betriebsferien kosteten keine
  Urlaubstage; der Standard ist das Gegenteil.

### Tests
Backend 1458, Frontend 217, `validate-release` auf 5 Distros (Ubuntu 22/24,
Debian 12, Rocky 9, Arch), Docker-Upgrade lokal mit echtem Login und
bit-identischen Daten, Windows 11 auf frisch installierter VM
(PostgreSQL 18.4, Health und Login je HTTP 200).

## [1.15.2] - 2026-07-18

Patch-Release. Ein neues, klein umrissenes Feature (#408) + der als Folge nötige
DSGVO-Export-Fix. Eine Migration (066). Kein weiterer Backend-/Berechnungs-Code.

### ✨ Neu
- **Jahresurlaubsanspruch mit Nachkommastelle (#408).** `User.vacation_days` ist
  jetzt dezimal (Migration 066, `Numeric(4,1)`): eine 3-Tage-Teilzeitkraft kann
  z. B. **16,8** Urlaubstage (28×3/5) exakt eingetragen bekommen, statt auf 17
  gerundet zu werden (das erzeugte 0,2 Tage Ungerechtigkeit vs. Kolleg:innen mit
  unterjährigem Eintritt). Eingabefeld akzeptiert 0,1-Schritte. Die Berechnung
  war bereits dezimalfähig (`Decimal`); nur Speicher/Schema/Eingabe blockierten.

### 🐛 Behoben
- **DSGVO-Export lief nach der #408-Umstellung in einen 500-Fehler.** Zwei rohe
  `json.dumps`-Export-Pfade (Art.-15-Selbstauskunft + Admin-Tenant-Export sowie
  Art.-20-Datenübertragbarkeit `/me/export`) schrieben `vacation_days` als
  `Decimal` → „Object of type Decimal is not JSON serializable". Beide casten
  jetzt `float(...)` (wie das benachbarte `weekly_hours`).

## [1.15.1] - 2026-07-15

Patch-Release. Behebt einen Weißbild-Absturz (#382) in der Admin-Dashboard-
Detailansicht und liefert die auf 1.15.0-Stand gebrachte Nutzer-Doku samt
In-App-Hilfe aus. Kein Backend-/Berechnungs-Code geändert, keine Migration,
keine neuen Abhängigkeiten, keine Installer-Änderungen.

### 🐛 Behoben
- **Weißbild „Etwas ist schiefgelaufen" beim Klick auf einen eingestempelten
  Mitarbeiter (#382).** Ein laufender (eingestempelter, noch nicht
  ausgestempelter) Zeiteintrag hat `end_time = null`. Die Zeiteintrags-Tabelle
  der Admin-Dashboard-Detailansicht rief `end_time.substring(…)` ungeguardet
  auf → Render-Absturz (ErrorBoundary) für jeden Mitarbeiter, der gerade
  eingestempelt ist. Neuer null-sicherer Helper `formatClockTime` (offener
  Eintrag → „offen"); der lokale `TimeEntry`-Typ deklariert `end_time` jetzt
  korrekt als nullbar (Compile-Time-Schutznetz gegen erneutes Auftreten).
  Anders als der Teil-Fix in 1.14.1 (#388, der nur den 200-mit-HTML-Body-Fall
  abfing) ist dies ein Render-Crash auf validen Daten.

### 📖 Dokumentation
- **Berechnungsdoku, Handbücher, Cheat-Sheets & In-App-Hilfe auf 1.15.0-Stand.**
  `docs/BERECHNUNGEN.md` deutlich erweitert (Betriebsferien inkl. #314/#394,
  Minijob/MiLoG inkl. festem Monats-Soll, Saldo-Stichtag #313, eigene
  Abwesenheitsgründe/Kind krank, tagebasierte Zählung); Admin-/Mitarbeiter-
  Handbücher + Cheat-Sheets, In-App-Hilfe (`DocViewer` + downloadbarer
  `/help/*.md`-Mirror) synchron nachgezogen. Faktengeprüft gegen den
  Berechnungs-Code.

## [1.15.0] - 2026-07-14

Minor-Release. Neues Minijob-Feature (#377 Baustein 2b) + projektweiter
Multi-Agent-Review-Durchgang (23 Findings ≤ Low gefixt). Eine Migration (065).
Beide Änderungssätze einzeln erschöpfend reviewt, gemergt und als Ganzes erneut
review-geprüft (Merge-Komposition sauber).

### ✨ Neu
- **Minijob-Modus „feste Monatsarbeitszeit" (#377 Baustein 2b).** Opt-in je
  Mitarbeiter (`use_fixed_monthly_target`, Migration 065): das Monats-Soll ist
  fest die vereinbarte Monatsarbeitszeit (`agreed_monthly_hours`) statt der aus
  Wochenstunden × Arbeitstagen schwankenden Summe. Individuelle Tagesstunden
  sind ein reines Anwesenheitsmuster; bezahlte Fehltage (Feiertag/Urlaub/bez.
  Freistellung) auf geplanten Tagen werden dem Konto gutgeschrieben, unbezahlte
  entschuldigte Tage mindern das feste Soll. Weiche `MILOG_MONTHLY_EXCEEDED`-
  Warnung bei Monats-Ist > vereinbarter Zeit. Für alle Nicht-Modus-Mitarbeiter
  byte-identisch (§16-Berechnung unverändert).

### 🐛 Behoben / 🔒 Härtung (Projekt-Review)
- **Doppelklick beim Einstempeln wirklich abgesichert.** Der bisherige
  `SELECT … FOR UPDATE` sperrte den Race gar nicht (Sperre auf einer noch nicht
  existierenden Zeile); jetzt zusätzlich ein User-Zeilen-Anker-Lock — zwei
  gleichzeitige Stempelversuche erzeugen garantiert nur einen offenen Eintrag.
- **Betriebsferien-Umbuchung** zählte historische Halbtags-Urlaube (vor dem
  `half_day`-Feld) falsch als vollen Tag → konnte einen Betriebsferien-Tag zu
  Unrecht auf Überstundenausgleich statt Urlaub kippen. Korrigiert.
- **Jahres-Abwesenheitsübersicht** zählte Krank/Fortbildung/Sonstiges u. a.
  stundenbasiert (0 Tage bei Personen ohne Stundenzählung) → jetzt tagebasiert.
- **Arbeitszeit-Änderung** aktualisierte die zwischengespeicherten Wochenstunden
  nicht sofort (fehlender Flush) → korrigiert (wirkt auf §16-Export/Self-Export).
- **Urlaub auf 24./31.12. („frei")** wurde in Änderungsanträgen und der
  Antrags-Budgetprüfung fälschlich belastet bzw. abgelehnt → soll-freie
  Sondertage jetzt in allen Buchungspfaden korrekt ausgeschlossen.
- **Kein Startabbruch mehr** bei fehlerhaftem Demo-Ablaufdatum (Read-Only statt
  Prozess-Exit); CORS-Header liegen jetzt auch auf 403/413-Kurzschlussantworten.
- Diverse F-026-Mandantenfilter ergänzt, tote Code-/Import-Stellen entfernt,
  mehrere schwache/irreführende Tests inhaltlich verschärft.

## [1.14.3] - 2026-07-14

Patch-Release. Kundenreport (#394) + adversarial multi-agent-Release-Review
(1 Medium + 4 Low gefixt). Keine Migration.

### 🐛 Behoben
- **Betriebsferien beachten „halbe Feiertage" (24./31.12.) korrekt (#394).** Fiel
  ein als `half_day` konfigurierter Sondertag in eine Betriebsferien-Schließung,
  wurde er als **voller** Tag verbucht — voller Überstundenausgleich bzw. ein
  ganzer Urlaubstag für einen halben Arbeitstag. Jetzt: `0,5 × Tagessoll` gebucht,
  0,5 Urlaubstage/Split-Budget verbraucht. Die 0,5-Tage-Kosten laufen zentral über
  `calculation_service.half_special_day_weight()` in `get_vacation_account`,
  `absence_days`, dem #314-Re-Split **und** allen Urlaubs-Budget-Pre-Checks — byte-
  identisch für alle Nicht-Halbtags-Sondertage.
- **Betriebsferien-Abwesenheiten sind Einzeltage (#394).** Jede generierte
  Abwesenheit trug bisher das Ende der ganzen Schließung als `end_date` — die
  Abwesenheitsliste zeigte je Zeile die komplette Spanne („24.12 – 31.12"). Jetzt
  Einzeltag; die Zugehörigkeit steckt weiter in der Notiz „Betriebsferien: …".

## [1.14.2] - 2026-07-13

Patch-Release. Performance + Kundenreport. Eine Migration (064).

### 🐛 Behoben / ⚡ Performance
- **Benutzerübersicht schneller (#204).** Feiertage und Arbeitszeit-Änderungen
  werden einmal vorab geladen statt pro Mitarbeiter (N+1 eliminiert); die
  Berechnung bleibt byte-identisch.
- **Übertrag Urlaubstage mit 2 Nachkommastellen (#383).** Das Feld akzeptiert nun
  z. B. 3,33 statt nur 0,5-Schritte (`YearCarryover.vacation_days` → `Numeric(5,2)`,
  Migration 064).

## [1.14.1] - 2026-07-13

Feature- und Härtungs-Release, adversarial multi-agent-reviewt (0 High/Medium,
2 Low gefixt). Eine additive Migration (063).

### ✨ Neu
- **Abwesenheit/Eintrag für den laufenden Tag (heute) buchen (#375).** Die per-Tag
  „+"/Bearbeiten-Aktion im Monatsjournal war auf `isPastDay` gegated (strikt vor
  heute) — meldete sich jemand für HEUTE krank, konnte der Admin das nicht direkt
  eintragen. `MonthlyJournal.tsx` unterscheidet jetzt `isPastDay`/`isFutureDay`:
  Admins buchen Vergangenheit **und** heute (Zukunft weiter über den Antragsweg
  gesperrt); die MA-Eigenansicht bleibt unverändert vergangenheits-only.
- **„Übertrag Urlaubstage" im UserForm (#383).** Analog zum „Anfangssaldo
  Überstunden" gibt es in den Mitarbeitereigenschaften ein Feld, das
  `YearCarryover.vacation_days` des Startjahres setzt. Bei unterjährigem Start
  („zum Stichtag eingestellt", `first_work_day`) bleibt so Vorjahres-Resturlaub
  erhalten statt nur anteilig gerechnet zu werden. Reiner Frontend-Change (Backend
  `upsert_carryover` bestand bereits), keine Migration.
- **Minijob-Prüfung: vereinbarte Monatsarbeitszeit (#377 Baustein 2a).** Opt-in
  `User.agreed_monthly_hours` (nullable, Migration 063): ist es gesetzt, nutzt
  `milog_service.agreed_monthly_hours()` exakt diese Zahl für die 50-%-Prüfung nach
  § 2 Abs. 2 MiLoG statt der bisherigen flachen Ableitung aus den Wochenstunden
  (× 13/3). Das Aging bleibt Soll-basiert (unverändert). Ohne Eingabe wie bisher.

### 🐞 Behoben
- **Whitescreen-Härtung — Render-Crash bei „Etwas ist schiefgelaufen" (#382).**
  Systemischer Root-Fix: Der Response-Interceptor in `api/client.ts` rejected jetzt
  jede 200-Antwort mit HTML-String-Body (SPA-`index.html` statt JSON, wie sie im
  Auth-/Proxy-/SPA-Fallback-Grenzfall nach einer `token_version`-Invalidierung
  auftreten kann) → Aufrufer landen in ihrem `.catch` statt die App zu
  white-screenen. Schließt die erreichbare Crash-Klasse überall auf einmal.
- **Duplicate-Start-Guards für Admin-Schreibpfade (Review-Low, #389/#393).**
  `admin_create_time_entry` und `admin_update_time_entry` spiegeln jetzt den
  409-Duplicate-Start-Guard des MA-Pfads (self-excluded beim Edit) → sauberes
  HTTP 409 statt UNIQUE-Constraint-500, wenn das neue Journal-„+" für heute mit
  einem offenen Clock-in derselben Startminute kollidiert.

## [1.14.0] - 2026-07-09

Feature-Release (MINOR — inhaltlich das reviewte/getestete 1.13.1, als MINOR
umbenannt wegen neuer nutzersichtbarer Fläche; #386). Zwei additive Migrationen
(061, 062).

### ✨ Neu
- **„Kind krank" + Sonderurlaub-Gründe (#376).** Baut auf den Custom Absence
  Reasons (#312) auf: neues Verhalten `unpaid_free` → `AbsenceType.OTHER`
  (entschuldigt unbezahlt), ein Preset-Katalog gängiger Gründe (1-Klick aktivieren,
  kein DB-Seed) sowie ein „Kind krank"-Zähler je Mitarbeiter:in mit weicher
  Warnung, wenn die üblichen Grenztage nach § 45 SGB V erreicht sind (per-MA-Cap +
  Tenant-Default). Migration 061.
- **Minijob-Compliance: Mindestlohn + § 2 Abs. 2 MiLoG (#377, Baustein 1+3).**
  Baustein 1 blendet den gültigen gesetzlichen Mindestlohn ein (datumsabhängige
  Konstante 13,90 € → 14,60 € ab 2027). Baustein 3 prüft für Minijobber auf
  Arbeitszeitkonto die 50-%-Arbeitszeitgrenze: month-to-date beim Ausstempeln sowie
  im Monatsreport/Konto, mit 12-Monats-Ausgleichsfrist via FIFO-Aging. Per-User-
  Opt-in-Flag (Migration 062), weiche Warnungen, keine Lohndaten. Baustein 2
  (Monatsmodus) folgte in 1.14.1.

### 🐞 Behoben
- **MiLoG `settlement_aging`-Stichtag-Fix + Review-Härtung (#384).**
- **Export-Korrektheit + DSGVO-Fixes aus dem Export-Prozess-Review (#380).**

## [1.13.0] - 2026-07-02

Feature-Release mit zwei Kundenwünschen, je adversarial multi-agent-reviewt
(alle Findings bis Low-Severity gefixt). Eine additive Migration (060).

### ✨ Neu
- **„Login als …" — read-only Ansicht als Mitarbeiter:in (#370).** Admins können
  die App aus der Sicht einer:s aktiven Mitarbeitenden ansehen (Dashboard prüfen,
  Probleme nachstellen) — über das Anmelde-Symbol in der Benutzerübersicht. Die
  Sitzung ist **strikt nur lesend** (jede Schreib-Aktion wird serverseitig
  blockiert), ein Banner „… – nur Lesen" mit **„Zurück zu Admin"** ist dauerhaft
  sichtbar. Jede Sitzung wird protokolliert (DSGVO-Rechenschaftspflicht,
  Art. 5 Abs. 2); da nichts geschrieben werden kann, ist keine Aktion je fälschlich
  der/dem Mitarbeitenden zurechenbar (§ 16 ArbZG). Nur Mitarbeitende (keine Admins)
  sind ansehbar. Neue Tabelle `impersonation_sessions` (Migration 060).
- **Konfigurierbare Wochentage im Schichtplaner (#371).** Unter
  **Einstellungen → Schichtplanung** wählbar, welche Wochentage der Planer anzeigt
  und plant — Standard **Mo–Fr**, Sa/So oder ein Schließtag einzeln zu-/abschaltbar
  (mind. ein Tag). Ein abgeschalteter Tag verschwindet aus der Wochenansicht, nimmt
  keine Slots auf und wird von der Auto-Generierung, Plan-Validierung und der
  MA-Karte „Deine Einteilung heute" übersprungen. Bestehende Slots bleiben erhalten
  und kehren beim Reaktivieren zurück (kein Datenverlust).

## [1.12.3] - 2026-06-28

Härtungs-Release aus einer mehrtägigen Multi-Agenten-Review-Kampagne (rund 30
Fixes über die PRs #357–#366) — technisch, fachlich und an den Specs. Bringt
zwei additive Migrationen (058/059), die u. a. den DSGVO-Hard-Delete entsperren.

### 🐞 Korrekturen
- **Betriebsferien-Urlaub kalenderchronologisch verteilen (#314).** Beim Split
  „erst Urlaub, dann Überstundenausgleich" werden die Arbeitstage jetzt in echter
  Kalenderreihenfolge belegt; ein Re-Save verteilt bestehende Buchungen neu.
- **Halbtags-Soll zählt 0,5× (#361).** Halbe Abwesenheitstage rechneten zuvor mit
  dem vollen Tagessoll → Phantom-Überstunden. Dazu: WHChange lehnt einen
  inkonsistenten Tagesplan ab, Re-Split filtert sauber auf den jeweiligen Tag,
  Änderungsantrag-Budget/-Resplit korrigiert.
- **Arbeitszeit-Fenster außerhalb → 0h (#364, Anti-Abuse).** Stempelungen außerhalb
  des konfigurierten Fensters werden auf 0h gekappt; die Rohstempel bleiben für die
  §16-Aufzeichnung erhalten.
- **Export-Tage tagebasiert (#364).** Urlaubs-/Kranktage im Export zählen nach dem
  Tagesprinzip statt als Stundensumme ÷ Ø-Tagessoll; ArbZG-Warnungen greifen jetzt
  auch in den Admin-Pfaden.
- **7 weitere Lücken im Urlaubsprozess (#358).** U. a. Budget außerhalb des
  Beschäftigungsfensters, Re-Split-Trigger bei Closure-Löschung/Privaturlaub,
  Jahresabschluss-Antrags-Guard.

### 🔒 Security / DSGVO
- **HIGH — FK-Crash `change_requests.absence_id` → ON DELETE SET NULL (Migration
  059, #359).** Der Fremdschlüssel ohne `ondelete` ließ die Antrags-Genehmigung und
  den DSGVO-Art.-17-Hard-Delete auf Postgres mit `ForeignKeyViolation` abbrechen.
- **Weitere Härtungen (#359):** Journal hinter Art.-9-Gate, Schichtplan-Read-Gating,
  eindeutiger SaaS-Login, robustere Scheduler-Billing-Jobs, Rohstempel in
  `update_time_entry`, saubere Zeiteintrag-Löschung über Änderungsanträge.
- `SECURITY.md` mit echter Policy (unterstützte Versionen + Meldekanal, #360).

### ⚡ Performance
- **7 Perf-Fixes (#363):** Dashboard- und Export-Doppelberechnung (war O(Monate²))
  linearisiert, N+1-Queries entfernt, ToastContext-`useMemo` gegen Re-Fetch-Loops.

### 🧹 Intern
- Migrationen **058** (`year_carryovers.source`) + **059**
  (`change_requests.absence_id`-ondelete); up→down→up auf Wegwerf-PG18 verifiziert.
- Spec-Lücken gefüllt + veraltete Spec-Docs korrigiert (#362); Handbücher und
  In-App-Hilfe zu Urlaubsberechnung + Betriebsferien aktualisiert (#357).

## [1.12.2] - 2026-06-28

Patch-Release: kleinere Komfortfunktionen plus eine umfassende UC-Review-Härtung
(drei adversarial verifizierte Runden, 25 Findings, PRs #346–#352).
Keine DB-Migration (alembic bleibt `057`).

### ✨ Neu
- **Schichtplan duplizieren (#338).**
- **Dashboard-Saldo-Label dynamisch + aktiver Schichtplan öffnet automatisch
  (#339/#340).**
- **Durchsuchbares Use-Case-Verzeichnis (177 UCs, `docs/uc/index.html`)** + neues
  **Projekt-Glossar** (Stunden vs. Tage, Soll/Ist/Urlaub/Überstunden) (#341/#346).

### 🐞 Korrekturen
- **Betriebsferien-Split erzeugt keinen irreführenden 0-Std-Urlaub am Nicht-
  Arbeitstag mehr (#314).**
- `backup-db.sh` ausführbar + `deploy.sh`-Health-Timeout für schwache VMs (#337).
- **UC-Review-Findings (#347–#351):** §5-Same-Day, Genehmigungs-Bypass auf
  `POST /absences`, §18-Konsistenz in Reports, `change_password`-Refresh-Cookie,
  Jahresabschluss ohne `track_hours`-Filter, free-Sondertage (24./31.12.) in
  Betriebsferien + Urlaubsgenehmigung ausgeschlossen, Frontend Gründe-Picker und
  Audit-Pagination.

### 🔒 Security / DSGVO
- **§5-Ruhezeit rechnet jetzt gegen die Rohstempel** statt der work-window-gekappten
  Zeit — sonst blieb ein echter Verstoß bei spätem Ausstempeln unentdeckt (#352).
- **DSGVO-Purge brach die Audit-`row_hash`-Kette** (Bulk-`UPDATE` umging den
  Hash-Hook → legitime Zeilen wurden als „manipuliert" gemeldet) → ORM-Load +
  Recompute (#352).
- §16-Rohstempel im Superadmin-Export, DSGVO-Schichtexport, `reason_id`/
  `reason_names` im Selbst- und §16-Export (#347/#352).

### 🧹 Intern
- Doku-Findings (Import, Reports, DSGVO-Löschung, Urlaubsstorno, 2FA) (#349).

## [1.12.1] - 2026-06-28

Patch-Release: zwei Dashboard-/Schichtplan-Komfortfunktionen plus eine Härtung
nach intensivem Multi-Agenten-Pre-Release-Review. Keine DB-Migration (letzte
Migration bleibt `057`).

### ✨ Neu
- **Admin-Dashboard: Monat ↔ Woche umschalten (#329).**
- **Schichtplaner zeigt je MA zugewiesene vs. Wochenarbeitszeit (Auslastung)
  (#330).**

### 🐞 Korrekturen
- **Betriebsferien-Überstunden-Split (#314)** wird beim erneuten Speichern jetzt
  rückwirkend angewendet — ein nachträglich aktivierter Schalter greift per Re-Save
  auf bestehende Betriebsferien (#331).
- **Out-of-range-Monat liefert 400 statt 500.** `?month=2026-13`/`2026-00` warf in
  allen vier Report-Endpoints und im Kalender einen Server-Fehler; neuer Helper
  `parse_year_month` validiert 1–12 (#335).

### 🔒 Security / DSGVO
- **HIGH — DSGVO-Art.-17-Hard-Delete (`purge_user`) brach für jeden je
  ausgestempelten Nutzer ab.** `time_entry_audit_logs.changed_by` ist NOT NULL — das
  bisherige SET NULL warf `IntegrityError`. Fix: Reassign auf den handelnden Admin;
  drei weitere `users.id`-FKs ohne `ON DELETE` bereinigt
  (`company_closure.created_by`, `change_request.reviewed_by`,
  `signup_tokens.user_id`) (#335).

### 🧹 Intern
- Disaster-Recovery-Doku (INSTALL-NATIVE) auf den socket-only Cluster korrigiert;
  neue Tests (`purge_user`-FK-Cleanup, Monats-Param).

## [1.12.0] - 2026-06-27

Funktions-Release: Schichtplanung **M2** (KW-/Ganzjahres-Planung mit
Auto-Generierung, Einweisungs-Matrix, Tagesansicht, Schicht kopieren) sowie eigene
Abwesenheitsgründe und mehrere Kunden-Wünsche. Migrationen 054–057 (additiv).

### ✨ Neu
- **Schichtplanung M2 (#305).** KW-/Ganzjahres-Planung mit Datums-Fenster
  (`active_from/until`) und greedy **Auto-Generierung** (`POST /plans/{id}/generate`,
  `mode=replace|fill_gaps`), **Einweisungs-/Skill-Matrix** (Arbeitsplatz-
  Qualifikationen als weiche Warnung), **Tagesansicht** und **„Schicht auf
  Wochentage kopieren"** (#315/#316/#321/#322). Weiterhin hinter dem Feature-Flag
  `shift_planning_enabled` (Default AUS) und von ArbZG/Soll-Ist entkoppelt.
- **Eigene Abwesenheitsgründe (#312).** Tenantweit pflegbare Gründe (Name, Farbe,
  Grundverhalten) als reines Label-/Farb-Overlay über die eingebauten Typen — die
  Berechnung bleibt typgetrieben. In den Kollegen-Feeds DSGVO-maskiert.
- **Monatssaldo „bis heute" (#313).** Live-Anzeigen (MA-Dashboard, Team-Tabelle,
  Überstundenkonto, YTD) zeigen den Saldo nur bis zum letzten abgeschlossenen
  Arbeitstag; Admin-Report-Toggle `bis_heute|monatsende`. Datei-Exporte und
  §16-Belege bleiben bewusst voller Monat.
- **Betriebsferien über Urlaub hinaus als Überstundenabbau (#314).** Optionales
  Setting `closure_overtime_after_vacation` (Default aus): Closure-Arbeitstage werden
  zuerst als Urlaub und danach als Überstundenausgleich gebucht — statt Minus-Urlaub.
- **Mitarbeitername in der Monatsjournal-Überschrift (Admin-Sicht) (#311).**

### 🧹 Intern
- Migrationen **054** (`workstation_qualifications`), **055** (Schichtplan-
  Datumsfenster), **056** (`absence_reasons`), **057**
  (`change_requests.proposed_reason_id`).
- Playwright-E2E für #311–#314 (#327).

## [1.11.0] - 2026-06-26

Funktions-Release: die neue (optionale) **Schichtplanung**. Die zuvor versehentlich
als 1.10.6 gecuttete Version wurde zurückgezogen und als MINOR neu aufgelegt
(byte-identischer Code).

### ✨ Neu
- **Schichtplanung (#305), M1.** Standorte, Arbeitsplätze und wochentagbasierte
  Schichtpläne mit Slots und Mitarbeiter-Zuweisungen; Dashboard „meine heutigen
  Schichten". Komplett hinter dem Feature-Flag `shift_planning_enabled` (Default AUS
  → Router liefert 404, das Feature „existiert nicht") und vollständig von
  ArbZG/Soll-Ist entkoppelt (keine Auswirkung auf Zeiterfassung oder Berechnung).
  Migration **053** (5 mandantenisolierte Tabellen, RLS).

### 🐞 Korrekturen
- Namens-Race im Schichtplan-Router liefert 409 statt 500.

## [1.10.5] - 2026-06-24

Patch-Release mit komplettem Pre-Build-Review/Fix/Test-Zyklus.

### ✨ Neu
- **Admin kann die Kalenderfarbe je MA setzen (#297)** (geteilte
  `calendarColors`-Utility).

### 🐞 Korrekturen
- **Betriebsferien bei zukünftigen/ausgetretenen MA (#298).**
  `_create_closure_absences` buchte je Closure-Arbeitstag eine Abwesenheit OHNE
  Prüfung des Beschäftigungsfensters — eine noch nicht eingetretene MA (z. B. eine im
  September startende Azubine) bekam bei urlaubsabziehender Betriebsferien heute schon
  Urlaubstage („34 genommene Urlaubstage"). Fix: Pro-MA-Guard
  `_within_employment_window` auch in der Buchungsschleife; `affected_employees` zählt
  nur tatsächlich gebuchte MA.
- Wording „N Einträge" statt „N Eintragträge" (#296).

## [1.10.4] - 2026-06-24

Patch-Release (erster vollständiger `/buildrelease`-Lauf): Windows-Installer-
Härtung, Betriebsferien-Fix und eine vorsichtige Service-/DB-Härtung.

### 🐞 Korrekturen
- **Betriebsferien-Speichern löscht keine erfassten Arbeitszeiten mehr** + Auto-
  Enrollment neuer MA in offene Betriebsferien (#290).
- **Windows-Installer-Härtung (#286).** `.bat`-Dateien jetzt mit CRLF — LF-
  Zeilenenden ließen `cmd` die Sprungmarken nicht finden → falsche „PostgreSQL
  fehlgeschlagen"-Meldung (PG war tatsächlich installiert). Dazu Docker-Upgrade-
  Skripte + Upgrade-Doku.
- Arbeitsbereich nutzt die volle Breite (kein `max-w-7xl`-Cap mehr) (#287).

### 🔒 Security / DSGVO
- **Service-/DB-Review (#15):** Backup-Router on-prem-gated, F-026-Lücken im
  Dashboard geschlossen, stille `except`-Blöcke loggen, Urlaubs-Schranke „max. 1 Jahr"
  auch im PATCH-Pfad.

### 🧹 Intern
- Code-Duplikation entfernt + N+1 im Audit-Log (#219).
- Handbücher korrigiert: der datenzerstörende „Betriebsferien neu speichern"-
  Workaround ist seit #290 obsolet.

## [1.10.3] - 2026-06-24

Bugfix-Release für ein Audit-Log-Phantom.

### 🐞 Korrekturen
- **Änderungsprotokoll zeigt keine Phantom-„Gelöscht"-Einträge mehr (#284).** Jeder
  Admin-Lesezugriff auf die Abwesenheiten eines MA schreibt (DSGVO Art. 5 (2)) eine
  Audit-Zeile `absence_list_read`, die die Per-MA-Änderungsansicht als „Gelöscht"
  fehlinterpretierte. Fix: neuer Parameter `changes_only` (nur create/update/delete)
  für die Änderungsansicht; die Compliance-Seite bleibt unverändert (mit allen
  Zugriffs-Events) (#285).

## [1.10.2] - 2026-06-23

Bugfix-Release: korrekte Tage-Anzeige in der Admin-Übersicht plus eine umfassende
Härtung der gesamten Admin-Sektion (Review, alle Findings bis *low* behoben).

### 🐞 Korrekturen
- **Admin-Monatsübersicht zeigt Urlaub & Krank in *Tagen* statt Stunden (#281).**
  Bisher wurden Urlaub/Krank in Stunden dargestellt (und Krank dauerhaft als 0).
  Jetzt korrekt in **Tagen** nach dem Tagesprinzip (§3 BUrlG) — konsistent mit der
  Jahresübersicht; ein halber Urlaubs-/Kranktag zählt 0,5, ein voller 1,0,
  unabhängig vom individuellen Tagesplan.
- **Krankheitstage sichtbar machen.** Krank ist aus Datenschutzgründen (Art. 9
  DSGVO) standardmäßig maskiert und lässt sich über die Option **„Krankheitstage
  anzeigen"** einblenden; der Zugriff wird protokolliert.

### 🔒 Sicherheit / Robustheit (Admin-Review)
- Durchgängige Mandanten-Filter (Mehrmandanten-Sicherheit) an allen geprüften
  Admin-Abfragen; korrekte Bulk-Lösch-Strategie; saubere Reihenfolge der
  Genehmigungsprüfungen.
- **Änderungsanträge für Abwesenheiten** prüfen jetzt das Urlaubsbudget (Neuanlage)
  bzw. Datums-Konflikte (Änderung) — keine stillen Überbuchungen oder Server-Fehler.
- §16-Export vollständig (mehrere Abwesenheiten pro Tag werden nicht mehr verworfen);
  Zugriffe auf Gesundheitsdaten werden erst nach erfolgreicher Auslieferung
  protokolliert; Ratenbegrenzung auf den Mandanten-Export.

### 🧹 Intern / UI
- Monats- und Jahresübersicht aktualisieren sofort nach Korrekturen; tagbasierte
  Spalten sind sortierbar; robustere Doppelklick- und Zeitzonen-Behandlung in
  mehreren Admin-Dialogen; ODS-Jahresexport reicht die Gesundheitsdaten-Option durch.

## [1.10.1] - 2026-06-23

Patch-Release: korrigiert die Windows-PostgreSQL-Version und härtet 1.10.0
(Review-Findings bis Schweregrad *medium*).

### 🐞 Korrekturen
- **Windows: PostgreSQL 18.4 statt 16.13.** Das Windows-Paket von 1.10.0 bündelte
  versehentlich PostgreSQL **16.13** (ein veralteter, lokal gecachter EDB-Installer),
  während Linux/macOS/Docker bereits auf PG 18.4 liefen. Der Build lädt den
  Windows-PG-Installer jetzt versioniert per direktem EDB-Link und **verifiziert die
  SHA256** des offiziellen `postgresql-18.4-1-windows-x64.exe`; bei falscher/alter
  Datei bricht er ab. Damit bündeln alle Build-Maschinen identisch PG 18.4 —
  end-to-end im Windows-11-Emulator verifiziert (Installation + Dienst + Login +
  `psql 18.4`).

### 🔒 Security / DSGVO / Robustheit
- DB-Backups werden **atomar** mit `0600` angelegt (`os.open`) statt erst per umask
  `0644` mit nachträglichem `chmod` — das kurze World-Read-Fenster ist geschlossen.
- Fehlender expliziter `tenant_id`-Filter in `get_next_vacation` ergänzt (F-026).
- `delete_all_holidays` nutzt `synchronize_session=False` (verhindert seltene
  `InvalidRequestError` beim Bundesland-Resync).
- Windows-`uninstall.bat`: `pg_dump -w` (sonst Endlos-Hänger an der Passwortabfrage).
- Windows-Update-Assistent schließt `cert.pem`/`key.pem` von der Kopie aus
  (verhinderte, dass ein Paket-Platzhalter das echte SSL-Zertifikat überschreibt).
- `install.sh`: Praxisname mit `/` zerstörte den openssl-`-subj`-String (→ kein TLS,
  Login mit `cookie_secure=true` schlug fehl) — jetzt entschärft.
- PG-Upgrade-Restore: Temp-Dump explizit `0600`; klare Fehlermeldung statt
  `UnboundLocalError`, falls das Entpacken scheitert.

### 🧹 Intern / Build
- Windows-PG-Installer **SHA256-gepinnt** — verhindert, dass verschiedene
  Build-Maschinen still unterschiedliche PostgreSQL-Versionen bündeln.
- `build-release`: fehlende `.sha256` → harter Abbruch; zusätzlicher
  `package-lock.json`-Versions-Check und `POSTGRESQL_VERSION`-Format-Assertion;
  SIGPIPE-sichere `gzip`-Prüfungen in den Docker-Backup-Skripten.
- **`docs/BUILD.md`** (neu): vollständige Build-Anleitung für alle OS inkl. Footguns.

## [1.10.0] - 2026-06-23

Funktions- und Wartungs-Release: PostgreSQL 18, gepflegte Feiertagsberechnung
und ein Zeiterfassungs-Fix.

### ✨ Neu
- **PostgreSQL 16 → 18 (#270).** Natives Bundle (theseus-rs 18.4.0,
  glibc-2.34-portabel; validiert auf Ubuntu 22/24, Debian 12, Rocky 9, Arch) und
  Docker (`postgres:18-alpine` + `postgresql-client-18`). Da ein Major-Upgrade
  nicht in-place läuft, überführt ein automatischer dump/restore-Pfad die Daten:
  `install.sh` erkennt den Versions-Sprung, dumpt den alten Cluster nach
  `data/backups/pre-upgrade-pgXX-*.sql.gz`, legt das alte Datenverzeichnis als
  `data/db.pgXX-*` zur Seite (nie gelöscht) und spielt den Dump in den frischen
  PG18-Cluster ein; bricht bei jedem Fehler ab, ohne Daten anzutasten. `PGDATA`
  bleibt explizit auf `.../data` gepinnt (PG18 würde sonst einen Major-Unterordner
  anlegen). *Echter PG16→18-Upgrade auf einem Realhost steht noch aus.*
- **Feiertage über `python-holidays` (#270).** Ersetzt die bisherige
  Feiertagsberechnung durch eine gepflegte Bibliothek inkl. bundeslandspezifischer
  Feiertage.

### 🐞 Korrekturen
- **Fälschliche §3-Tagesstunden-Warnung beim Bearbeiten (#252).**
  `update_time_entry` berechnete die >8h-Warnung nach dem Commit mit
  `exclude_entry_id=None` — der bearbeitete Eintrag wurde dadurch doppelt gezählt
  (ein 6h-Eintrag las als 12h → „Tagesarbeitszeit über 8 Stunden", obwohl der Tag
  <8h hat; gespeichert wurde korrekt). Fix: Tages- und Wochenberechnung nach dem
  Commit nutzen `exclude_entry_id=entry.id`; die Nachtarbeit-Prüfung profitiert mit.

### 🔒 Security / DSGVO
- **DB-Backups owner-only `0600` (Art. 32, #272).** `#213`-`create_backup` und der
  `install.sh`-PG-Upgrade-Dump legten Sicherungen world-readable (`0644`) an —
  beide jetzt explizit `chmod 0600` (Backups enthalten personenbezogene Daten).
  Regressionstest ergänzt.

### 🧹 Intern
- `system_settings`-Lese-Helfer in `settings_service` gebündelt (#271, #219-Nachzug;
  letzter Inline-`SystemSetting`-Read aus `time_entries.py` entfernt).
- e2e Release-Smoke schließt das Onboarding-Modal + tolerantere Backup-Assertion
  (#273); lokale `screenshots-*/`-Verzeichnisse ignoriert (#274).
- PG18 in den operativen Anleitungen (INSTALL-NATIVE/DOCKER, INFRASTRUCTURE,
  arc42, CLAUDE.md) nachgezogen (#272).

## [1.9.0] - 2026-06-23

Funktions-Release rund um die neue **Datensicherung** sowie Korrekturen an
Zeiterfassung, Urlaub und Installation. Enthält auch die nie an Kunden
ausgelieferte Zwischenversion 1.8.15 (Zeiteintrag-Edit-Fix, Docker-Backup-Skripte).

### ✨ Neu
- **Datensicherung / DB-Backup-Verwaltung (#213).** Neuer Admin-Bereich
  „Datensicherung": Sicherungen lassen sich manuell oder zeitgesteuert anlegen —
  sowohl nativ als auch unter Docker — und bei Bedarf wiederherstellen.
  Backend (#257) + Admin-UI (#258), inkl. Docker-Backup/Restore-Skripte (#231).
- **Audit-Log Tamper-Evidence (#121).** Jeder Audit-Log-Eintrag erhält einen
  per-Row-HMAC, sodass nachträgliche Manipulation erkennbar wird (v1).
- **Linux-Rolling-Distro-Support (#177).** `libxml2.so.2` wird ins Linux-Bundle
  eingebettet → Installation läuft auch auf Rolling-Release-Distributionen.
- **Build-Härtung (#81).** Installer-Build-Flags + `dotnet test`-Gate im Release-Build.

### 🐛 Korrekturen
- **Zeiteintrag bearbeiten schlug mit „Input should be None" fehl (#225).**
- **Tagebasierter Urlaubsverbrauch (#205).** Urlaub wird taggenau inklusive
  halber Tage über ein persistiertes `half_day` verbraucht.
- **Journal-/Export-Berechnung (#198).** Ist-Fensterung in den Journal-Tageszeilen
  und die Zwischensummen in den Exporten korrigiert.
- **404 statt 403 bei fremden Same-Tenant-Ressourcen (#120).**
- **Dienst vor Re-Installation stoppen (#217).** Verhindert „Text file busy" beim
  Update bzw. der Neuinstallation.
- **tzdata gebündelt (#139).** Behebt `ZoneInfoNotFound` auf Minimal-Images (Docker).
- **Mandantentrennung F-026.** Explizite `tenant_id`-Filter ergänzt (belt-and-suspenders
  zusätzlich zu RLS).

### ⚡ Performance
- **Überstunden-Dashboard + Monatsreport (#150).** O(Monate²)/N+1-Abfragen entfernt.
- **Firmenschließtage (#204).** Referenzdaten werden gebündelt vorgeladen statt
  ~3 Abfragen je Mitarbeiter×Tag.
- **Code-Splitting der `/admin/*`-Routen + Hilfe (#147).** Schnellere Ladezeiten.

### 🔒 Security / Härtung
- **Prod-Review-Härtung:** Backend-Korrektheit + Security (#260), Frontend
  (Object-URL-Leaks, NaN, Doppelklick, URL-Guard) (#261), Infra/Build
  (Doppel-Backup-Schutz, Version-Single-Source-of-Truth, PG-Sanity) (#262).
- ABBA-Lock-Reihenfolge + HMAC-Kanonisierung gehärtet.
- Hardening aus intensivem Code-/Security-/ArbZG-Review (#251).
- `/system/info`-Leak-Guard um `onboarding_enabled` ergänzt.
- `md-to-pdf` entfernt (verwundbares `js-yaml@3.14.2` raus).

### 📦 Dependencies
- fastapi `0.136.*` → `0.138` (Versions-Cap aus 1.8.10 entfernt) + sichere
  Frontend-Bumps.
- Prometheus v2.54 (EOL) → v3.12.0 (#175).

### 🧹 Refactor
- Gemeinsame Status-Badge-Config (3 Duplikate → 1, #219).
- Gemeinsamer User-Typ statt 4 Duplikaten im Frontend (#151).

## [1.8.14] - 2026-06-22

Hotfix-Release: Dashboard-Hang nach Sitzungsablauf. Enthält auch die nie an
Kunden ausgelieferte Zwischenversion 1.8.13 (Login-Fehleranzeige).

### 🐞 Korrekturen
- **Dashboard-Hang behoben (#229).** Nach Ablauf der Sitzung geriet die App in
  eine Schleife aus automatischem Abmelden und erneutem Anmelden (logout↔refresh-Storm),
  sodass „Lade Dashboard…" nicht mehr fertig lud. Der Logout wird jetzt sauber beendet.

### 🔑 Anmeldung
- **Klarere Falsch-Passwort-Anzeige + Caps-Lock-Hinweis (#227).** Eine
  fehlgeschlagene Anmeldung wird jetzt deutlich angezeigt — mit Hinweis auf
  Groß-/Kleinschreibung und einer Warnung bei aktiver Feststelltaste. Zuvor war
  eine Falscheingabe leicht als „Dashboard lädt nicht" misszuverstehen.

## [1.8.12] - 2026-06-19

Wartungs-Release: erste Datensicherungs-Bausteine, Onboarding-Schnellstart und
Security-/DSGVO-Härtung. Enthält auch die nie an Kunden ausgelieferte
Zwischenversion 1.8.11.

### ✨ Neu
- **Onboarding-Schnellstart.** Schnellstart-Anleitung + Admin-Toggle zum
  Aktivieren des Onboardings; überarbeitetes Cheat-Sheet.
- **macOS-Auto-Backup (launchd).** Automatische Datensicherung unter macOS;
  `docs/BACKUP.md` dokumentiert Backup und Restore.

### 🐞 Korrekturen
- **Backup-Restore (CRITICAL) behoben** sowie `praxiszeit.conf`-Guard und
  Onboarding-Block korrigiert (Review 2026-06-18).

### 🔒 Security / DSGVO / Härtung
- **TOTP-Secrets werden at-rest verschlüsselt** (Audit-Fix aus dem Code-Review).
- Security-/DSGVO-/ArbZG-Audit-Fixes bis Low; Hilfe-Texte aktualisiert.
- **Dependabot-Security:** `undici` + `js-yaml` aktualisiert.

### 🔧 Sonstiges
- Update-Server-URL auf `mr-development.de` umgestellt; Lizenz-Beta-Cleanup;
  Installations-Doku + §3.1-Verfügbarkeits-Matrix aktualisiert.

## [1.8.10] - 2026-06-16

Hotfix zu 1.8.9: die 1.8.9-Dependency-Aktualisierung machte die App auf allen
Plattformen unbenutzbar.

### 🐞 Korrektur
- **HTTP 500 auf Login und fast der gesamten API behoben.** FastAPI 0.137 führt
  intern `_IncludedRouter`-Routen (ohne `.path`) ein; `prometheus-fastapi-instrumentator`
  8.0.0 griff ungeschützt auf `route.path` zu → `AttributeError` → 500 auf jedem
  Endpoint aus einem included-Router (Login inklusive). `/api/health` ist ein
  Top-Level-Endpoint → blieb 200, was den Fehler verschleierte.
- Fix: `fastapi==0.136.*` (knapp unter der brechenden 0.137; restlicher neuer
  Stack bleibt — Starlette 1.3, uvicorn 0.49, alembic 1.18, instrumentator 8).
  Zurück auf 0.137+, sobald der Instrumentator-Fix (Upstream #370/#371) released ist.
- Auf echtem Linux-Host end-to-end verifiziert (Installation, Dienststart,
  echter Login = 200).

## [1.8.9] - 2026-06-16

Wartungs-Release: Dependency-Aktualisierung und Code-Review-Härtung (Security/DSGVO).

### 📦 Dependencies
- **Frontend:** vite-8-Kompatibilität hergestellt (`@vitejs/plugin-react` 5.1.4 → 5.2.0;
  `npm ci` schlug zuvor mit Peer-Konflikt fehl). Sichere Updates: axios 1.16 → 1.18,
  tailwindcss 4.2 → 4.3, vitest 4.1.0 → 4.1.9, jsdom, focus-trap-react, typescript-eslint.
- **Backend:** fastapi 0.115 → 0.137, uvicorn 0.34 → 0.49, alembic 1.14 → 1.18,
  PyJWT 2.12 → 2.13, prometheus-fastapi-instrumentator 7 → 8. Volle Test-Suite grün.

### 🔒 Security / Härtung
- **`install.sh`:** Praxis-Name, Admin-Benutzer/-Mail und -Passwort werden jetzt
  TOML-escaped in die `praxiszeit.conf` geschrieben (ein `"`/`\` zerstörte zuvor die
  Konfiguration → Dienst startete nicht). Die `hostname`-Ausgabe wird vor der SAN-Bildung
  validiert; `ADMIN_PASSWORD` wird nach dem Schreiben aus dem Shell-Environment entfernt.
- **`build-release.sh`:** `nssm.zip` (web.archive-Quelle) wird gegen einen gepinnten
  SHA256 verifiziert, bevor `nssm.exe` ins Windows-Paket eingebettet wird.
- **`praxiszeit-server.py`:** Fehlgeschlagene Migrationen maskieren die DB-Connection-URL
  im Log (kein Passwort mehr); `.secret-key` wird atomar mit 0600 angelegt.

### 🐛 Korrekturen
- **„Krank während Urlaub" gibt den Urlaub wieder zurück** (`refund_vacation`): Der
  Duplikat-Konflikt-Check warf bisher einen 409, bevor die Urlaubsrückgabe greifen
  konnte — das Feature war faktisch wirkungslos.
- **DSGVO:** Nachtarbeitnehmer-Status (gesundheitsnah, §6 ArbZG) wird in den ODS-Exporten
  nur noch bei `include_health_data` ausgegeben (analog zum XLS-Export). Die endgültige
  Nutzer-Löschung (`purge_user`) schreibt keinen Klarnamen mehr ins Audit-Log.
- **Mandantentrennung:** Zeiterfassungs-Endpunkte (`time_entries`) ergänzen den expliziten
  `tenant_id`-Filter (F-026, belt-and-suspenders zusätzlich zu RLS).

## [1.8.8] - 2026-06-16

Korrektur-Release: native Installation lief auf realen Hosts nicht durch
(End-to-End-Test auf echtem Linux-Mint mit belegtem Port 5432).

### 🖥️ Native Installation
- **Falscher „Rolling-Distro"-Abbruch / Installer bricht ohne Ausgabe ab behoben.**
  Mehrere Shell-Pipes in `install.sh` (`ldconfig | grep -q`, `ldd | head`) lösten
  unter `set -o pipefail` SIGPIPE aus → vorhandene Bibliotheken wurden fälschlich
  als fehlend gemeldet bzw. der Installer brach kommentarlos ab (v. a. auf Systemen
  mit vielen Bibliotheken). Geprüft wird jetzt SIGPIPE-sicher (Here-String / `awk`).
- **Dienst-Crash-Loop in den Datenbank-Migrationen behoben.** Eine `%`-Sequenz in
  der internen DB-Verbindung (Unix-Socket, #174) löste in Alembic
  `invalid interpolation syntax` aus → der Dienst startete nicht. `%` wird jetzt
  für configparser escaped.
- Verifiziert: vollständiger Native-Install + Start aus dem ausgelieferten Tarball
  auf Linux Mint 22.3 (Dienst aktiv, DB verbunden, Login erreichbar).

## [1.8.7] - 2026-06-16

Korrektur-Release rund um das selbstsignierte SSL-Zertifikat (Feldreport: Anwender
kommt im Browser nicht an die Anmeldung) plus Review-Härtung.

### 🔒 SSL / Zertifikat
- **Selbstsigniertes Zertifikat ist jetzt ein gültiges End-Entity-Server-Cert.**
  Bisher wurde ein CA-Zertifikat ohne `serverAuth` erzeugt (und der native
  Linux-Installer nutzte einen Ed25519-Schlüssel, den Browser für TLS-Server-
  Zertifikate nicht unterstützen) → Firefox/Chrome verweigerten die Seite ohne
  Ausnahme-Option. Alle Generatoren (Installer, Docker-Skript, Laufzeit-
  Auto-Generator im Server, Tool) erzeugen jetzt **RSA-2048** mit
  `basicConstraints=CA:FALSE`, `keyUsage` und `extendedKeyUsage=serverAuth`.
- **SAN deckt zusätzlich den Hostnamen ab** (Zugriff via `https://<host>/`), und
  ein leeres `hostname -I` bricht die Cert-Erzeugung nicht mehr still ab.

### 🧰 Intern / Härtung
- `pg_env()` erzwingt `PGHOST` auf das eigene Socket-Verzeichnis (ein vererbtes
  `PGHOST`/`PGPORT` kann psql/pg_dump nicht mehr auf einen fremden Cluster lenken).
- Verbindungs-URL kodiert User/Passwort RFC-3986-konform (Sonderzeichen wie
  Leerzeichen/`+` korrekt).
- `ssl/generate-cert.sh` ohne hartcodierten Kundennamen im Zertifikats-Subject.

## [1.8.6] - 2026-06-16

### 🐳 Docker
- **Dashboard-Ladefehler behoben** („Fehler beim Laden des Dashboards", leere
  Urlaubskonto-Karte). Der nginx-Proxy reicht den Host-Header jetzt mit Port
  weiter (`$http_host`), sodass die internen 307-Weiterleitungen (z. B.
  `/api/dashboard`, `/api/absences`) nicht mehr den Port verlieren. Betrifft nur
  Docker-Installationen; native Installationen waren nicht betroffen.

## [1.8.5] - 2026-06-16

### 🖥️ Native Installation
- **Behebt fehlgeschlagene Installation auf Servern mit vorhandener
  PostgreSQL auf Port 5432** (#174). Die mitgelieferte Datenbank läuft unter
  Linux/macOS jetzt ausschließlich über einen eigenen Unix-Socket und kollidiert
  nicht mehr mit einer System-PostgreSQL. Bestehende Installationen bleiben
  erreichbar; Windows ist unverändert.

## [1.8.4] - 2026-06-13

Kleines Sicherheits- und Korrektur-Update (Empfehlung für alle Installationen).

### 🔒 Sicherheit / DSGVO
- **DSGVO Art. 9:** Auch der Feed „kommende Abwesenheiten des Teams" maskiert
  Kranken-/sonstige sensible Abwesenheiten für Nicht-Admins (zuvor nur der
  Kalender) — kein Krankheits-Indikator mehr aus Fremd-Einträgen.
- PDF-Export: Sonderzeichen werden sauber escaped (reportlab); Host-Allowlist
  gehärtet.

### 🧮 Korrektur
- Update-Banner-Link korrigiert; `formatHoursHM` überlaufsicher; XLS-Import lehnt
  Einträge mit Ende ≤ Start ab.

## [1.8.3] - 2026-06-06

Fix-Release aus einem zweiten Gesamt-Codebase-Review (Korrektheit, DSGVO,
Sicherheit). Enthält **eine Datenbank-Migration (049, RLS-Härtung)** — Update
für alle Installationen empfohlen.

### 🧮 Berechnung / Reports
- **Klassischer Jahresreport (XLSX):** Der StundenSaldo war um die Urlaubsstunden
  zu hoch (Phantom-Überstunden, z. B. +32 h statt 0 h), weil das bereits
  netto-bereinigte Soll noch einmal um Urlaub/Krank reduziert wurde. Der Report
  rechnet jetzt im traditionellen Brutto-Stundenkonto und ist konsistent zu den
  übrigen Reports.
- **Monatsjournal:** Tageszeilen berücksichtigen jetzt Sondertage (24./31.12.)
  und das Eintritts-/Austrittsfenster — die Tagessumme passt wieder zum Monats-Soll.
- **Jahres-Abwesenheitsreport:** „Urlaub genommen" wird tagebasiert gezählt
  (konsistent mit dem Resturlaub im selben Bericht).
- **§3-24-Wochen-Mittel** rechnet in lokaler Zeit (Europe/Berlin) statt UTC —
  keine Fenster-Verschiebung um einen Tag mehr.
- **Teilzeit:** Die Genehmigung eines Abwesenheits-Änderungsantrags bucht das
  Tagessoll des Tages statt eines pauschalen 8-h-Werts — kein doppelter
  Urlaubsverbrauch mehr bei z. B. 4-h-Tagen.

### 🔒 Sicherheit / DSGVO
- **RLS-Härtung (Migration 049):** `stripe_events` und `signup_audit_log`
  erhalten Row-Level-Security (ENABLE + FORCE + Mandanten-Policy) — beide hatten
  bisher `tenant_id` ohne RLS.
- **Art. 9:** Die ODS-Jahresexporte maskieren Krankdaten und schreiben ein
  Zugriffs-Audit-Log wie alle übrigen Exporte.
- **Art. 17:** Löschung/Anonymisierung umfasst jetzt Profilbild, TOTP-Secret und
  Abteilung und invalidiert offene Sitzungen.
- **Art. 32:** Export-Services filtern zusätzlich explizit nach Mandant
  (Belt-and-Suspenders über RLS).
- **Art. 5:** Das Aufräumen alter Fehlerprotokolle läuft als täglicher Job
  (nicht mehr nur beim Start).
- Verarbeitungsverzeichnis / DSFA auf Stand 2026-06-06.

### 🐞 Behoben (Frontend)
- **Dashboard:** Nach dem Stempeln aktualisieren Überstunden-/Saldo-Kacheln und
  die letzten Einträge sofort (vorher blieben sie stehen).
- **Monatsjournal:** Stundenformat ohne „7h 60min"- bzw. „NaNh NaNmin"-Anzeige.

## [1.8.2] - 2026-06-02

Reines Härtungs-Release aus einem ArbZG- und Sicherheits-Audit (OWASP). Keine
neuen Funktionen, keine Datenbank-Migration. Empfohlenes Update für alle
Installationen. (Das Audit ergab **keine** kritischen/hochgradigen Befunde; zwei
ältere offene Punkte — RLS-Mandantentrennung, Content-Security-Policy — wurden
als bereits geschlossen bestätigt.)

### 🔒 Sicherheit
- **Update-Schutz gegen Downgrade:** PraxisZeit aktualisiert sich nur noch auf
  echt neuere Versionen. Ein (auch gültig signiertes) älteres Update-Paket wird
  ignoriert — schützt vor erzwungenem Zurückstufen auf eine schwächere Version.
- **Vier-Augen-Prinzip erweitert:** Wer zugleich Administrator und Mitarbeiter
  ist, kann eigene Zeit-Korrekturanträge und Urlaubsanträge nicht mehr selbst
  genehmigen, solange ein weiterer aktiver Administrator existiert. (In der
  Ein-Personen-Verwaltung bleibt die Selbstgenehmigung möglich.)
- **Protokollierung von Anmelde-Ereignissen:** Erfolgreiche und fehlgeschlagene
  Logins, Konto-Sperren, Abmeldungen und Passwortänderungen werden jetzt
  strukturiert protokolliert (ohne Passwörter/Token) — bessere Nachvollziehbarkeit.
- Interne Härtung der Zwei-Faktor-Prüfung.

### 🧮 Arbeitszeitgesetz / Nachweis
- **§16:** Beim Überschreiben eines Eintrags per Excel-Import bleiben die
  tatsächlich gestempelten Roh-Zeiten erhalten (Nachweis der echten Anwesenheit).
- **§3/§14:** Auch ein Änderungsantrag zeigt jetzt die Warnung bei mehr als 48 h
  Wochenarbeitszeit — wie die direkte Zeiterfassung.

## [1.8.1] - 2026-06-02

Fix-Release aus einem intensiven Gesamtreview (Funktion, Robustheit, Sicherheit).

### 🐞 Behoben
- **Urlaub/Krank für Mitarbeitende ohne Stundenzählung** wurde zwar „genehmigt",
  aber nicht tatsächlich gebucht — jetzt korrekt tagebasiert erfasst.
- **Abwesenheits-Änderungsanträge:** Die Genehmigung konnte fehlschlagen und den
  Antrag dauerhaft blockieren, wenn am Tag bereits eine Abwesenheit bestand —
  jetzt saubere Behandlung (idempotent bzw. klarer Hinweis).
- **Ausstempeln über 10 h** wird nicht mehr blockiert: Der Eintrag wird
  gespeichert und der Verstoß als deutliche Warnung gemeldet (die Arbeitszeit ist
  bereits geleistet). Bei manueller Eingabe bleibt die 10-h-Grenze eine harte Sperre.
- **Urlaubsantrag:** Feiertage werden korrekt nicht vom Budget abgezogen; keine
  doppelte Buchung über verschiedene Abwesenheitstypen am selben Tag.
- **Anzeige:** Pausen-Prüfung bei Schichten über Mitternacht; Urlaubs-Fortschritts­
  balken bei noch fehlendem Anspruch.

### 📚 Sonstiges
- Handbücher, Cheat-Sheets und die In-App-Hilfe vollständig überarbeitet.

## [1.8.0] - 2026-06-01

Erste Produktivversion (Beta — ohne Lizenzpflicht).

### ✨ Neu
- **Soll-Arbeitszeit-Fenster:** Pro Mitarbeiter je Wochentag optionale
  Soll-Beginn-/Soll-Ende-Zeiten. Anwesenheit außerhalb des Fensters (plus Puffer)
  wird nicht angerechnet; die echte Stempelzeit bleibt erhalten.
- **Sondertage 24./31.12.:** Im Kalender als arbeitsfrei oder halber Tag
  markierbar; wirkt auf Soll-Zeit und Urlaubskonto.
- **Betriebsferien-Teilnahme** je Mitarbeiter ein-/ausschaltbar (unabhängig von
  der Rolle).
- **Mitarbeitende ohne Stundenzählung:** Keine Soll-/Ist-/Überstundenrechnung;
  Urlaub und Krankheit zählen tagebasiert.
- **Überstunden-Übersicht** je Mitarbeiter in der Benutzerverwaltung.
- **Pflicht-Pause-Ausnahme:** Bei nicht möglicher Pause kann mit Begründung
  dokumentiert werden (optional genehmigungspflichtig); die Pause wird beim
  Ausstempeln aktiv abgefragt.

### 🧱 Plattform
- **Beta-Modus** (keine Lizenz nötig), mehrere akzeptierte Lizenzschlüssel
  (sanfte Rotation), Docker-Bundle, Härtung der nativen Linux-Installation.

## [1.7.0] - 2026-05-28

### 🧮 Korrekte Soll-Stunden in den Berichten an Sondertagen
- Sind der 24.12. oder 31.12. als **halber Tag** oder **frei** konfiguriert,
  zeigen jetzt **alle** Berichte (Monats-/Jahres-Excel, PDF, ODS) in der
  Soll-Spalte den reduzierten Wert — vorher stand dort der volle Tag, wodurch
  die Soll-Summe im Export von der berechneten Monats-Soll abwich (§16-relevant).
- **Bezahlte Freistellung** wird in den Tageszeilen der Exporte jetzt mit
  Klartext-Label „Bez. Freistellung" ausgewiesen.

### ⏱️ Pflicht-Pause (§4 ArbZG): Eingabe und Server urteilen identisch
- Die clientseitige Pausenprüfung spiegelt jetzt die Server-Logik exakt
  (nur Pausenabschnitte ab 15 Min zählen, Bewertung über den ganzen Tag) —
  zuvor ließ die Eingabemaske manche §4-Verstöße durch und der Begründungs-
  Dialog (Pflicht-Pause-Ausnahme) erschien dadurch nicht.

### 🔒 Sicherheit / Wartung
- Abhängigkeiten der internen Handbuch-/Screenshot-Werkzeuge auf sichere
  Versionen aktualisiert (behebt alle gemeldeten Schwachstellen; betrifft nur
  das Build-Tooling, nicht die ausgelieferte Anwendung).
- Härtung des Änderungsantrag-Genehmigungspfads (Sperre gegen gleichzeitige
  Bearbeitung) und kleinere Korrektheits-/Wortlaut-Fixes aus dem Review.

## [1.6.0] - 2026-05-27

### ✨ Fehler/Feedback direkt aus der App melden
- Neuer Dialog **„Fehler melden / Feedback"** (über das Hilfe-Panel erreichbar):
  Titel, Beschreibung und Schweregrad eingeben und absenden. Die Meldung geht an
  das PraxisZeit-Team. App-Version und Betriebssystem werden automatisch
  mitgesendet; es werden keine personenbezogenen Daten automatisch angehängt.
- Technisch: authentifizierter Backend-Proxy (`POST /api/feedback/report`), der
  die Meldung an den zentralen Bug-Tracker weiterleitet (Lizenz-gebunden,
  rate-limitiert). Bei abgelaufener Lizenz oder Netzwerkproblemen erscheint eine
  verständliche Meldung statt eines Fehlers.

## [1.5.5] - 2026-05-27

### 💅 Setup-Assistent (Windows): Feinschliff auf der Abschluss-Seite
- Umlaute korrigiert („Im Browser **öffnen**"), grüner Haken neu gestaltet.
- **Warten auf Server-Start:** „Im Browser öffnen" wird erst aktiv, wenn der
  Webserver wirklich antwortet (vorher „Server startet …") — kein „nicht
  erreichbar" mehr bei zu frühem Klick.

## [1.5.4] - 2026-05-27

### 🐞 Windows-Update stellt die VC++-Runtime sicher
- In-Place-Updates bündeln jetzt `vc_redist.x64.exe` und installieren die
  Microsoft Visual C++ Runtime idempotent mit — schließt die Lücke, dass nur die
  Erstinstallation (setup.bat) die Runtime installierte.

## [1.5.3] - 2026-05-27

### 🐞 Frische Windows-Installation startet wieder (VC++-Runtime)
- Der gebündelte PostgreSQL-Installer installiert jetzt die Microsoft Visual C++
  Runtime (`--install_runtimes 1`). Auf frischem Windows ohne vorhandene Runtime
  scheiterte `initdb.exe` zuvor mit `0xC0000135` und der Dienst startete nie.
  Sofort-Workaround für Bestands-Installs: `vc_redist.x64.exe` von
  `https://aka.ms/vs/17/release/vc_redist.x64.exe` installieren.

## [1.5.2] - 2026-05-26

### 🐞 Lizenz-Fehler legt den Dienst nicht mehr lahm
- **Read-Only statt Absturz:** Ein ungültiger/nicht verifizierbarer `license.key`
  (z.B. nach einer Key-Rotation, oder abgelaufen) führte bisher zu `sys.exit(1)`
  → das Backend startete nicht → **niemand konnte sich mehr einloggen**. Jetzt
  geht der Server in den **Read-Only-Modus**: Anmeldung und Daten-Export
  funktionieren, nur Schreibvorgänge (Stempeln, Anträge stellen/genehmigen) sind
  gesperrt.
- **Ehrliche Fehlermeldungen:** „License signature is invalid — corrupted or
  tampered" war irreführend. Neu: „Signatur passt nicht zum hinterlegten
  Schlüssel — vermutlich für eine ältere/andere Schlüsselversion ausgestellt;
  bitte aktuelle Lizenz im Shop holen."

### 🐞 Native Windows: PostgreSQL startet nach Update zuverlässig
- **Logs-ACL-Fix:** Nach einem Update konnte der PostgreSQL-Dienst (NetworkService)
  `logs/postgresql.log` nicht mehr öffnen (`Permission denied`) → PG startete
  nicht → Login unmöglich. `pg_start` grantet dem Dienstkonto jetzt vor jedem
  Start Schreibrecht auf `data\db` **und** `logs\`.
- **PG-Start-Timeout 30s → 60s** (langsamer Start durch AV/ASLR-„could not
  reserve shared memory"-Retries auf manchen Maschinen).

## [1.5.1] - 2026-05-25

### 🐞 Native Windows-Installation: Startup-Deadlock behoben (ERR_CONNECTION_REFUSED)
Nach einer Windows-Installation lief der Dienst zwar, aber der Server band keinen
Port — der Browser meldete `ERR_CONNECTION_REFUSED`. Mehrere ineinandergreifende
Ursachen (Details: `docs/specs/native-windows-pg-service-2026-05-25.md`):

- **PostgreSQL läuft jetzt als eigener NetworkService-Dienst.** `postgres.exe`
  verweigert den Start unter dem LocalSystem-Token des PraxisZeit-Dienstes.
  `pg_start()` registriert PostgreSQL auf Windows daher via `pg_ctl register`
  als eigenen Dienst (`NT AUTHORITY\NetworkService`, `icacls`-Grant auf das
  Datenverzeichnis) statt es als Kindprozess zu starten. Unix bleibt bei
  `pg_ctl start`.
- **Self-Healing gegen EDB-Leftover-Cluster.** Ein vom EDB-Installer
  hinterlassenes scram-Datenverzeichnis (Superuser `postgres`) ohne
  `.db-credentials` kollidierte mit der trust-Annahme des Servers. Ein
  Cluster-Marker (`.praxiszeit-cluster`) unterscheidet eigene von fremden
  Clustern; fremde werden **zur Seite verschoben (nie gelöscht)** und sauber neu
  initialisiert. Bestehende, credentialed Cluster bekommen den Marker per
  Migration nachgetragen.
- **`psql -w` in allen Setup-Aufrufen** — kein Hängen mehr an einer interaktiven
  Passwort-Abfrage (die im Dienst-Kontext nie beantwortet werden kann), sondern
  klares Fail-fast.
- **Update/Backup hängt nicht mehr bei uninitialisierter DB.** `create_backup`
  nutzt `pg_dump -w` und bricht bei fehlenden `.db-credentials` sauber ab statt
  am Passwort-Prompt zu blockieren; der Update-Wizard überspringt den
  Backup-Schritt, wenn die Datenbank nie initialisiert wurde.
- **Self-Signed-Zertifikat-Fallback.** Ist SSL konfiguriert (`cookie_secure=true`),
  aber `config/ssl/cert.pem`/`key.pem` fehlen, erzeugt der Server jetzt selbst ein
  Self-Signed-Zert → HTTPS funktioniert, Login-Cookie wird nicht abgelehnt.
- **`PYTHONUNBUFFERED=1`** für den NSSM-Dienst — Startup-Fehler landen sofort in
  `service-stderr.log` statt erst beim Prozess-Ende (oder nie).
- **`.db-credentials` bleibt für SYSTEM lesbar.** `_restrict_file_permissions`
  ist jetzt robust: jeder `icacls`-Schritt läuft unabhängig, SYSTEM (S-1-5-18)
  bekommt das Leserecht zuerst, `/inheritance:r` läuft zuletzt. Vorher konnte ein
  fehlschlagender Grant (Machine-Account) die Datei ohne jede ACE zurücklassen →
  `PermissionError` beim Service-Start.
- **Migrationen robuster:** Alembic wird programmatisch (`alembic.config.main`)
  statt via `python -m alembic` aufgerufen (umgeht das "No module named
  alembic.\_\_main\_\_" direkt nach der Installation, während das Paket noch
  indiziert wird) + bis zu 3 Retries.
- **Dependencies landen im gebündelten Python.** `setup.bat` setzt
  `PYTHONNOUSERSITE=1` für `pip install` (+ der Dienst läuft mit diesem Flag).
  Sonst sah das gebündelte Python ein evtl. vorhandenes versionsgleiches
  System-Python-User-Site, pip wertete die Pakete als „erfüllt" und installierte
  nichts ins Bundle → der LocalSystem-Dienst fand alembic/uvicorn nicht.

### ✨ Installer-Politur
- Korrekte deutsche Umlaute in allen user-sichtbaren Wizard-Texten
  (Seiten-Beschreibungen, Validierungsmeldungen, Headlines, Buttons, Done-Seite).
- **Desktop-Verknüpfung & Startmenü-Eintrag** optional (Checkboxen auf der
  Installationsort-Seite, beide Default an). Erzeugt `.url`-Verknüpfungen, die
  den Browser auf `https://localhost` öffnen.
- **Eintrag in „Apps & Features".** Der Installer registriert PraxisZeit unter
  `HKLM\…\Uninstall\PraxisZeit` (DisplayName, Version, Publisher,
  UninstallString → `uninstall.bat`) → in Windows „Apps" sichtbar und von dort
  deinstallierbar. `uninstall.bat` eleviert sich bei Bedarf selbst und entfernt
  Registry-Eintrag + Verknüpfungen wieder.

### 🔗 Verwandt
- Linux-Impact analysiert (frische Installs nicht betroffen; latentes Defizit
  cross-platform behoben) → Tracking-Issue #130.

## [1.4.3] - 2026-05-03

### 🚀 Wizard — drei neue Pages: Installationsort, Ports, Lizenz
- **Install-Location-Page** zwischen Welcome und Konfiguration. User kann
  den Pfad explizit waehlen (Default `C:\PraxisZeit`), Update-Mode
  blockt das Feld auf den existierenden Pfad. Wenn der User Fresh-Install
  ausgewaehlt hat, der Pfad aber bereits eine Installation enthaelt,
  blendet sich eine rote Warnung ein mit zwei CTAs: "Auf Update
  umschalten" oder "Anderen Pfad waehlen". Continue ist gesperrt bis
  der Konflikt aufgeloest ist — verhindert versehentliches
  Daten-Clobbern.
- **Ports-Page** im Fresh/Repair-Flow. HTTPS-Port (Default 443) und
  HTTP-Redirect-Port (Default 80, abschaltbar). Live-Validation auf
  Range 1..65535 + Identitaets-Konflikt; zusaetzlich nicht-blockierende
  Warnung wenn ein Port laut `IPGlobalProperties.GetActiveTcpListeners`
  bereits belegt ist (z.B. anderer Webserver auf dem Setup-Server).
  Neuer Conf-Key `[server].http_redirect_port`, vom Backend in
  `config.py:_TOML_KEY_MAP` aufgenommen.
- **License-Page** im Fresh- *und* Update-Flow (im Update-Pfad fuer
  Lizenz-Erneuerung). User kann entweder einen Lizenz-Token einfuegen /
  per File-Picker eine `.key` waehlen ODER 30 Tage Demo starten.
  Live-Validierung gegen den gleichen Ed25519-Public-Key wie das Backend
  via BouncyCastle (.NET 10 hat keine native Ed25519-Unterstuetzung).
  Bei erfolgreicher Validierung zeigt der Wizard Kunde, Mitarbeiter-
  Limit und Ablaufdatum an. Bei Demo-Mode wird `demo_expires_at` in
  `praxiszeit.conf` geschrieben; Backend erkennt das in `main.py`
  Lifespan und schaltet ab dem Datum in Read-Only.

### 🐞 Wizard-UX-Fixes (aus Customer-Feedback)
- "Bitte warten..."-Button blieb stehen, obwohl die Installation
  fertig war: `NextButtonText` auf `ProgressPageViewModel` ist jetzt
  state-aware (`IsRunning ? "Bitte warten..." : "Weiter"`) und wird
  via `OnIsRunningChanged` neu emittiert.
- Button-Beschriftungen waren links-aligned trotz fixer MinWidth —
  `HorizontalContentAlignment="Center"` auf `.primary`, `.ghost`,
  `.success` ergaenzt.
- DonePageView ohne aeusseren ScrollViewer; bei DPI ≥ 125 % wurde
  der "Schliessen"-Button abgeschnitten. Wrap im ScrollViewer.
- Default-Window von 820x640 auf 900x720 (Min 780x620) — die jetzt
  vorhandenen 6 Pages und der Step-Indicator brauchten mehr Platz.

### Backend — Demo-Mode + Server-Port-Settings
- `LICENSE_DEMO_EXPIRES_AT` (TOML `[license].demo_expires_at`) und
  `SERVER_PORT` / `SERVER_HTTP_REDIRECT_PORT` (TOML `[server].port` /
  `http_redirect_port`) als neue Settings in `app/config.py`.
- `app/main.py` Lifespan: ohne `LICENSE_KEY_PATH` aber mit
  `LICENSE_DEMO_EXPIRES_AT` → Demo-Mode bis zum Datum, danach
  Read-Only (`set_license_state(None, read_only=True)`). Mit echter
  Lizenz unveraendert.

### Tests
- 31 neue Tests (Total 104 / 104 grün) in
  `installer/setup/tests/PraxisZeit.Setup.Core.Tests`:
  Port-Range/Konflikt-Validation, Conf-Roundtrip mit Custom-Ports,
  `demo_expires_at`-Serialisierung, License-Validator
  Negative-Paths (leerer Token, falsches Segment-Count, Non-EdDSA-
  Algorithm, Random-Signatur). License-Positive-Path-Tests laufen im
  Backend (`test_native_mode.py`) gegen denselben Public-Key.

## [1.4.2] - 2026-05-03

### 🐞 Bugfix — Tailwind v4 Spacing-Regression (alle `p-*`/`m-*`/`space-*`)
- **Symptom**: Karten ohne Innen-Padding, Sidebar-Items ohne `px-4 py-3`,
  `Budget`/`Genommen` ohne Spacing — die Oberflaeche sah komplett "kaputt"
  aus, obwohl Hintergruende, Schatten, Rahmen und runde Ecken alle korrekt
  rendeten. Nur die Spacing-Utilities waren stillgelegt.
- **Root Cause**: `frontend/src/index.css` hatte einen globalen
  `* { margin: 0; padding: 0; box-sizing: border-box; }`-Reset *ausserhalb*
  jedes `@layer`. Tailwind v4 wickelt jede Utility in `:where(...)` ein,
  damit User sie mit einfachen Selektoren ueberschreiben koennen — d.h.
  `:where(.p-6)` hat Specificity 0,0,0. Der unlayered `*`-Selektor hat
  ebenfalls 0,0,0, gewinnt aber trotzdem, weil **unlayered Regeln in der
  Cascade ueber layered Regeln stehen**. Ergebnis: jede `p-*`, `m-*`,
  `px-*`, `space-x-*`, `space-y-*` wurde stillschweigend von dem Reset
  ueberschrieben.
- **Fix**: Reset in `@layer base` packen. `@layer base` steht in der
  Tailwind-v4-Reihenfolge unter `@layer utilities`, also gewinnt
  `:where(.p-6)` wieder ueber das `*`. `box-sizing` ist im Reset entfallen,
  weil Tailwind-v4-Preflight das schon auf `*, ::before, ::after` setzt.
- Verifiziert end-to-end im Browser (Playwright gegen lokalen Docker-
  Stack): Card-Padding `0px → 24px`, Nav-Item-Padding `0px → 12px 16px`.
  Sidebar, Karten und Layout sind wieder so, wie sie vor 1.4.0 aussahen.

## [1.4.1] - 2026-05-03

### 🐞 Bugfix — CSS-Bruch nach Update bei stale Service-Worker
- **Symptom**: Nach Update auf 1.4.0 lieferte ein Native-Install dem Browser
  fuer alte hashed CSS-URLs (`/assets/index-OLDHASH.css`) die `index.html`
  zurueck — `200 OK` mit `Content-Type: text/html`. Browser verwirft das
  als Stylesheet, Seite landet komplett ungestyled, bis der User den
  Service Worker manuell unregistert. Erstmals durch Tailwind v3 → v4 in 1.4.0
  ausgeloest, weil sich saemtliche Asset-Hashes aenderten.
- **Root Cause**: `SPAFallbackMiddleware` in `backend/app/main.py` lieferte
  bei *jedem* GET-404 ausserhalb `/api/` die `index.html` aus — auch fuer
  Asset-Pfade. Stale-SW-Klienten bekamen so HTML als CSS und cachten den
  kaputten Zustand.
- **Fix**: Asset-foermige Requests (letztes Pfad-Segment hat eine Endung,
  kein `Accept: text/html`) bekommen jetzt einen echten 404. `/assets/*`
  short-circuit-t unabhaengig vom Accept-Header. SPA-Navigationen
  (`Accept: text/html`) erhalten weiterhin `index.html`. Damit erholt
  sich jeder Browser beim naechsten Refresh selber.
- **Bonus**: Die SPA-Fallback-Response umging bisher die `SecurityHeaders`-
  Middleware — `/login` & Co. lieferten *keine* CSP/HSTS/X-Frame-Options.
  Die Fallback-Response uebernimmt diese Header jetzt aus der inneren
  Middleware-Kette (Defence-in-Depth-Parity mit Docker-Mode + nginx).
- **Refactor**: `SPAFallbackMiddleware` aus dem `if SERVE_FRONTEND:`-Block
  in `backend/app/main.py` nach `app/middleware/static_serving.py`
  ausgelagert (importierbar, testbar). 10 Unit-Tests in
  `backend/tests/test_spa_fallback.py` decken Asset-404, Navigation-mit-
  index.html, Header-Propagation und SPA-Routes-mit-Punkt ab.

### 🚀 Feature — ConfigPage im Setup-Wizard (Erst-Admin-Setup)
- Neue Wizard-Page **"Konfiguration"** zwischen Welcome und Progress,
  nur im Fresh-Install / Repair-Modus aktiv. Fragt Praxis-Stammdaten
  (Name, Adresse, Bundesland-Dropdown mit allen 16 Bundeslaendern fuer
  Feiertags-Sync) und den Admin-Account (Username, Email, Vor-/Nachname,
  Passwort + Wiederholung) ab. Live-Validation matched 1:1 die
  Backend-Bootstrap-Regeln (`backend/app/main.py:_WEAK_ADMIN_PASSWORDS`,
  Min-Length 12) — der Wizard kann nichts durchwinken, was das Backend
  beim Start ablehnen wuerde.
- **PraxisZeitConfigWriter** (Core) generiert daraus eine vollstaendige
  TOML-`praxiszeit.conf` mit korrekt-escaped Strings (Backslash, Quotes,
  Steuerzeichen via `\uXXXX`). Schreibt UTF-8 **ohne BOM** (sonst bricht
  der Backend-TOML-Parser, F-053). Default-Sektionen ([server],
  [database], [security], [backup] etc.) bleiben bei sicheren Werten.
- **ScriptRunner** akzeptiert optional `PraxisZeitConfigValues`: nach
  dem File-Copy aber **vor** `setup.bat` wird die User-Config nach
  `<installDir>\config\praxiszeit.conf` geschrieben. setup.bat sieht
  das File schon und ueberspringt die `conf.example`-Vorlage —
  Backend-Bootstrap legt beim ersten Service-Start den User-gewaehlten
  Admin an, kein "BITTE_AENDERN"-Crash mehr.
- **Update-Pfad bleibt unangetastet**: ConfigPage wird nur fuer
  Fresh/Repair gebaut, im Update behaelt der Wizard die existierende
  praxiszeit.conf (User-Anpassungen wuerden sonst ueberschrieben).
- Step-Indicator im Footer wird **dynamisch** aus der Page-Anzahl
  generiert (3 Dots fuer Update, 4 Dots fuer Fresh). Welcome,
  ConfigPage und Done bekommen Animation/Brand-Colors fuer aktiven
  und abgeschlossenen Status.
- Done-Page zeigt jetzt eine konkrete Login-Anweisung ("Sie koennen
  sich jetzt mit dem Admin-Account `<username>` anmelden") statt der
  alten Formulierung "muss config\\praxiszeit.conf einmalig angepasst
  werden". Customer-Onboarding-Flow ist damit komplett unattended.
- 30 neue Unit-Tests fuer `PraxisZeitConfigWriter` (TOML-Escaping,
  Validation matched Backend-Regeln, UTF-8-ohne-BOM-Roundtrip).
  Gesamt-Testanzahl im Setup-Projekt: **73 / 73 grün**.

## [1.4.0] - 2026-04-25

### 🚀 Feature — Single-File `setup.exe` mit eingebettetem Payload
- **Eine Datei, ein Doppelklick**: `praxiszeit-1.4.0-setup-windows-x64.exe`
  (~445 MB) enthält jetzt das **komplette Payload** (Python-Embeddable,
  PostgreSQL-Installer, Backend, Frontend, nssm, alle .bat/.ps1-Scripts)
  als embedded resource. Beim Doppelklick (UAC → Admin) extrahiert die
  EXE den Payload nach `%TEMP%\praxiszeit-setup-<guid>` und ruft die
  bestehenden Install-Scripts auf — kein vorheriges ZIP-Entpacken,
  kein .NET-Runtime auf dem Zielserver. Cleanup nach Abschluss.
- **DB-Backup vor Update ist Pflicht** und wird in der Welcome-Page
  explizit beworben. Update-Pfad ruft `update-wizard.ps1 -Headless`
  auf, dessen Schritt 2 ein vollstaendiges `pg_dump` nach
  `data\backups\` schreibt — auch bei spaeterem Fehler bleiben alle
  Daten unversehrt.
- **Architektur-Entscheid**: Wir reimplementieren die 1436+ Zeilen
  bewaehrter `.bat`/`.ps1`-Logik (cp1252-Edge-Cases, Junctions,
  EDB-Aufraeumung, RLS-Kontext, robocopy-Excludes, F-037 ACL-Fix)
  bewusst NICHT in C#. Die EXE ist eine GUI-Huelle, die die getesteten
  Scripts unveraendert ausfuehrt → ZERO Regressionsrisiko fuer die
  Install-Logik beim Kunden.
- `update-wizard.ps1` neuer `-Headless`-Switch: ueberspringt die
  WinForms-GUI komplett und emittiert maschinenlesbare Marker
  (`[STEP] <id> <status>`, `[LOG] <text>`, `[PROGRESS] <0..100>`,
  `[DONE] <success|fail>`) auf stdout. Avalonia-Wizard parst die
  Marker und rendert daraus Step-Liste, Live-Log und Progress-Bar.
  Default-Verhalten (ohne `-Headless`) unveraendert — der bestehende
  WinForms-Wizard ist 1:1 funktional als Fallback verfuegbar.
- `setup.bat` und `install-service.bat` honorieren ab sofort
  `PRAXISZEIT_NONINTERACTIVE=1` und ueberspringen alle `pause`-Aufrufe
  → der Avalonia-Wizard kann beide unattended ausfuehren ohne
  Subprocess-Hang. Default-Verhalten (manuelles Aufrufen) unveraendert.

### 🛠️ Setup-Wizard — neue Pages, Orchestrator, Live-Progress
- **Progress-Page** (`ProgressPageView.axaml`): zwei-spaltiges Layout
  mit checklistartiger Step-Liste (Status-Punkte: Pending grau →
  Running blau → Ok gruen / Warn gelb / Fail rot) links und
  Konsolen-Log rechts (Consolas, 1000-Line-Cap), oben dezenter
  Progress-Bar in Brand-Primary. Refektiert pro Modus die genauen
  Schritte: Update zeigt 7 Schritte (ACL/Backup/Stop/Copy/Pip/Start/
  Task), Fresh-Install 4 (Copy/Setup/Service/Start).
- **MainWindowViewModel**: orchestriert Welcome → Progress → Done.
  Auf Welcome-"Weiter" extrahiert `EmbeddedPayloadExtractor` das
  ZIP, der `ScriptRunner` startet den passenden Subprocess, Marker
  fliessen via `IProgress<RunnerEvent>` als typed events
  (`RunnerStepEvent`/`RunnerLogEvent`/`RunnerProgressEvent`/
  `RunnerDoneEvent`) in die ViewModel-Layer. UI marshaling via
  `Progress<T>`-SyncContext-Capture, kein `Dispatcher.Post`-Boilerplate.
- **DonePage**: differenziert Erfolg (gruener Checkmark + URL-Karte +
  "Im Browser oeffnen"-Button) vs. Fehler (roter X-Kreis + Hinweis
  auf das automatische DB-Backup unter `data\backups`).
- **Welcome-Page**: zeigt im Update-Modus einen prominenten
  Backup-Callout ("Datenbank wird vor dem Update gesichert"), damit
  dem Anwender klar ist, dass `pg_dump` automatisch laeuft.
- **app.manifest**: `requireAdministrator` + `dpiAwareness=PerMonitorV2`
  → automatischer UAC-Prompt beim Doppelklick, scharfes Rendering
  auf High-DPI-Displays.
- **Step-Indicator** im Footer: 3 Dots (Welcome / Installation /
  Fertig) zeigen Fortschritt durch die Wizard-Stages, aktiver Step
  in Brand-Primary, abgeschlossene Steps in Accent-Green.

### 🎨 UI — Installer-Redesign
- Neue zentrale Markenpalette in `App.axaml` (Primary `#0E5BA8`,
  Accent `#13B981`) plus globale Button-Klassen (`primary`, `success`,
  `ghost`) und Card-/Pill-Styles.
- `MainWindow.axaml`: Gradient-Header mit stilisiertem Uhren-Logomark,
  Versions-Pill rechts, Step-Indikator-Punkte im Footer. Fenster auf
  820 × 640 vergrößert, hellgraue Surface-Background-Farbe.
- `WelcomePageView.axaml`: Card-Layout mit Icon-Tiles (Plattform,
  Pfad, aktuelle Version, neue Version), klare Typo-Hierarchie.
- `DonePageView.axaml`: gruener Erfolgs-Checkmark im Gradient-Kreis
  mit Soft-Shadow, "Im Browser oeffnen"-Action-Button, separater
  Fehler-Path mit rotem X-Kreis.

### 🔢 Version-Bump
- `backend/app/core/updater.py`, `frontend/package.json` (+ Lockfile)
  und `tools/build-release.sh` von **1.3.7 → 1.4.0**. Der
  Build-Konsistenz-Check (F-055-Followup) haelt die Stellen synchron.

### 📦 Build-Pipeline
- `tools/build-release.sh` Phase 5: erst Windows-Tree zusammenbauen,
  dann **Payload-ZIP als Build-Artefakt** unter
  `build/payload-X.Y.Z-windows-x64.zip`, dann `dotnet publish` mit
  `-p:PayloadZipPath=...` → EXE bekommt das ZIP als Manifest-Resource
  mit stabilem `LogicalName=praxiszeit_payload.zip`. Output-Naming:
  `praxiszeit-${VERSION}-setup-windows-x64.exe` damit der
  Phase-7-`sha256sum`-Glob die EXE mit aufnimmt. Fallbacks fuer
  fehlendes `.NET-SDK` und fehlendes `zip` (PowerShell
  `Compress-Archive`) sind erhalten.

## [1.3.7] - 2026-04-23

### ✨ Feature — Urlaub / Anträge stornieren (Issue #90)
- **`DELETE /api/vacation-requests/{id}`** erlaubt zusätzlich zur
  bisherigen PENDING-Zurücknahme jetzt auch das Stornieren eines
  bereits **genehmigten** Antrags, solange der Zeitraum noch
  **in der Zukunft** liegt (`vr.date > heute`). Beim Storno werden
  die zugehörigen `Absence`-Tage (matched auf `user_id`, Datumsbereich
  der VR, gleicher `absence_type`) gelöscht, ein Audit-Log-Eintrag pro
  Tag geschrieben (`source=vacation_request_cancel`), und die VR auf
  `withdrawn` geflipt. Angefangene/abgelaufene Urlaube sind bewusst
  nicht stornierbar (Arbeitstag ist bereits ausgefallen).
- **Neuer Admin-Endpoint `DELETE /api/admin/vacation-requests/{id}`**
  mit identischer Semantik für Admin-on-behalf-Storno; tenant-scoped
  und per `with_for_update()` gegen Race-Conditions beim gleichzeitigen
  Approve/Cancel-Click abgesichert.
- **Frontend**: "Stornieren"-Button jetzt auch bei genehmigten
  zukünftigen Urlauben sichtbar — im Mitarbeiter-Kalender
  (`AbsenceCalendarPage`) und auf der Admin-Seite
  (`VacationApprovals`). Bestätigungsdialog erklärt, dass die
  Abwesenheitstage mitgelöscht werden.
- **Tests:** Neues `tests/test_vacation_request_cancel.py` (11 Cases)
  deckt alle 4 VR-Status × {future, today, past} × {employee, admin,
  cross-user} Kombinationen ab.

### 🟡 Security — Dependency-Patches (Issue #85)
- **`python-dotenv` 1.0.* -> >=1.2.2** (GHSA-mf9w-mj56-hr94) —
  Symlink-following in `set_key()` erlaubte Arbitrary-File-Overwrite
  via Cross-Device-Rename-Fallback. Nur indirekt durch
  pydantic-settings `.env`-Loading genutzt; Pin hebt Floor auf das
  gepatchte Release.
- **`Tmds.DBus.Protocol` 0.90.3 -> 0.92.0** (GHSA-xrw6-gwf8-vvr9,
  HIGH) — malicious D-Bus peers konnten Signals spoofen und FDs
  erschoepfen. Transitive Dep von Avalonia 12.0.0 im neuen
  `installer/setup/` Projekt; expliziter `PackageReference`-Pin
  in `PraxisZeit.Setup.csproj` bis Avalonia selbst bumped. Macht
  den `dotnet build` NU1903-Warn-Free.

### 🧹 Cleanup
- Template-Stub `installer/setup/src/PraxisZeit.Setup.Core/Class1.cs`
  aus `dotnet new classlib`-Scaffolding entfernt (Issue #87).

### 📝 Docs
- `CLAUDE.md` "Native Installer" erweitert um Abschnitt zum
  Avalonia-Installer unter `installer/setup/` inkl. Build-Commands,
  .NET 10 Abhaengigkeit und Solution-Struktur; Hinweis auf
  `tools/generate-self-signed-cert.py` und auf die BOM-Falle in
  `praxiszeit.conf` (Issue #86).

## [1.3.6] - 2026-04-17

**Hotfix-Release direkt im Anschluss an 1.3.5.** Behebt zwei Fehler
die beim Live-Update eines Kundenservers sofort aufgefallen sind:
Footer-Versionsanzeige und kaputter `Step-PipInstall` im Update-
Wizard.

### 🔴 Frontend-Footer zeigte falsche Version
- **`frontend/package.json` von 1.3.0 auf 1.3.6** gebumpt. Das Feld
  wird in `vite.config.ts` als `__APP_VERSION__`-Define eingebettet
  und in `Layout.tsx:345` als `v{__APP_VERSION__}` im Footer
  gerendert. Seit Release 1.3.0 hat niemand es mehr hochgezogen —
  alle 1.3.1/1.3.2/1.3.3/1.3.4/1.3.5-Pakete haben Backend-Version
  korrekt aber Footer falsch ("v1.3.0") angezeigt. Backend
  (`/api/health`) war immer korrekt, nur die UI hat gelogen.
- **`tools/build-release.sh` Version-Drift-Check** — vor dem Frontend-
  Build wird jetzt `frontend/package.json` gegen `APP_VERSION`
  validiert und der Build bricht mit klarer Fehlermeldung ab wenn
  die zwei divergieren. Verhindert den Rueckfall.

### 🔴 Update-Wizard pip-Install crashte auf Kundenserver
- **F-056: `installer/windows/update-wizard.ps1 Step-PipInstall`** —
  fuehrt jetzt `get-pip.py --force-reinstall` **vor** dem
  `pip install -r requirements.txt` aus. Ursache war: `Step-CopyFiles`
  nutzt Robocopy mit Excludes fuer `data/`, `config/`, `logs/`, aber
  nicht fuer `bin/python/Lib/site-packages/`. Robocopy merged Files,
  loescht aber keine stale Dateien. Beim 1.3.3 -> 1.3.5 Update ist
  dadurch `pip._vendor.resolvelib/` in einem inkonsistenten Mix aus
  alten + neuen Files gelandet und `pip install` hat mit
  `ImportError: cannot import name 'RequirementInformation' from
  pip._vendor.resolvelib.structs` gecrasht. `get-pip.py
  --force-reinstall` baut pip + vendored deps sauber neu, macht den
  Schritt idempotent.

## [1.3.5] - 2026-04-17

**Audit-Response-Release.** Adressiert die Findings aus einem kritischen
Security-/ArbZG-/UX-/Test-Audit (PR #89). Kern: zwei neue Middleware-
Ebenen (License-Readonly, Request-Size-Limit), neuer Superadmin-Router
fuer §16-Notfall-Export, TOTP-Replay-Schutz per DB-Migration, neue
Admin-Change-Request-UI, sowie ein Frontend-Util das ArbZG-Warnungen
einheitlich anzeigt. Reiner Additiv-Release, keine Breaking Changes
ggue. 1.3.4.

### 🔴 Security — Dependency-CVEs gepatcht
- **`axios` 1.13.5 -> 1.15.0** (GHSA-3p68-rc4w-qgx5, GHSA-fvcv-3m26-pcqx)
  — NO_PROXY Hostname Normalization Bypass + Cloud Metadata
  Exfiltration via Header Injection Chain (beide SSRF-Eskalations-
  Vektoren, beide fixed in 1.15.0).
- **`follow-redirects` 1.15.11 -> 1.16.0** (GHSA-r4q5-vmmm-2653) —
  leaks Custom Authentication Headers to Cross-Domain Redirect
  Targets. Ueber `overrides` in `frontend/package.json` forciert, da
  transitive Dep via axios.
- **`pytest` 8.x -> >=9.0.3** (GHSA-6w46-j5rx-g56g) — vulnerable
  tmpdir handling.

### 🔴 Security
  `users`-Table ein `last_totp_counter` (bzw. Replay-Tracking) hinzu.
  Verhindert, dass ein bereits akzeptierter 6-stelliger TOTP-Code im
  selben 30-Sek-Fenster ein zweites Mal akzeptiert wird.
  Test: `tests/test_totp_replay.py`.
- **LicenseReadOnlyMiddleware** (`app/middleware/license.py`) — blockt
  alle schreibenden HTTP-Methoden (POST/PUT/PATCH/DELETE) bei
  abgelaufener Lizenz mit `403` und liefert nur noch Read-Only-API.
  Registriert global in `main.py`, deckt damit neue Writer-Endpoints
  automatisch ab (keine Per-Route-Dependency noetig).
- **Request-Size-Limit** — Middleware-Enforcement fuer Body-Groesse
  plus Regressions-Test `tests/test_request_size_limit.py`.
- **Cross-Tenant-API-Tests** (`tests/test_cross_tenant_api.py`,
  224 LOC) — systematische Negativ-Tests gegen alle Tenant-ueberquerende
  Angriffsvektoren (Read/Write/Delete auf fremde `tenant_id`).
- **Concurrency-Tests** (`tests/test_concurrency.py`, 170 LOC) —
  Postgres-only Race-Tests fuer `clock_out` / Absence-Unique-Constraint
  / Change-Request-Approval.

### 🟡 Superadmin / DSGVO-Art.20
- **Neuer Superadmin-Router** `/api/superadmin/*`
  (`app/routers/superadmin.py`, 205 LOC). Erfordert User **ohne**
  `tenant_id` (`require_superadmin`-Dependency). Zweck: §16-Notfall-
  Export deaktivierter Tenants. Setzt `set_superadmin_context(db)` um
  RLS zu umgehen und kann tenant-uebergreifend lesen/exportieren.

### 🟡 Change-Request-Workflow
- **Admin-Change-Requests-UI** (`pages/admin/ChangeRequests.tsx`,
  130 LOC) — endlich ein Admin-Frontend fuer die CR-Approval. Davor
  war das nur ueber die API ansteuerbar.
- **Precondition-Checks vor Status-Aenderung** in
  `admin_change_requests.py` (Race-Condition-Fix) +
  `change_request.py` Schema erweitert.

### 🟡 ArbZG-Warnings (Frontend)
- **Neues Util `utils/arbzgWarnings.ts`** + Tests
  (`arbzgWarnings.test.ts`). Alle ArbZG-Warnungen aus API-Responses
  werden ab jetzt zentral ueber `showArbzgWarnings(toast, warnings)`
  angezeigt. `StampWidget` und `TimeTracking` wurden umgestellt —
  statt duplizierten `if warnings.includes(...)`-Bloecken pro Seite.
- **ToastContext**: severity-basierte Default-Dauern (success 3s,
  error 8s, warning 6s, info 5s) damit Ruhezeitwarnungen lang genug
  stehen. Aufrufer muessen die Dauer **nicht** mehr pro Call setzen.

### 🟡 Exporte
- **ODS-Export** (`ods_export_service.py`) — Review-Fixes + neuer Test
  `tests/test_ods_export_service.py` (125 LOC).
- **reports.py** um ~80 LOC erweitert (Multi-Entry-Export + Report-
  Fixes, deckt die Mehrfachbuchung pro Tag korrekt ab).

### 🟡 Middleware / Infrastruktur
- **`middleware/static_serving.py`** — SPA-Fallback-Middleware (+75
  LOC): saubere Trennung zwischen API-Pfaden und SPA-Routes fuer den
  Native-Modus (`SERVE_FRONTEND=True`).
- **`middleware/auth.py`** — kleinere Haerteanpassungen (+15 LOC).
- **`auth_service.py`** +60 LOC, **`auth.py` Router** angepasst fuer
  TOTP-Replay + Login-Haertung.

### 🟡 Build / CI
- **`scripts/local-ci.sh`** gruendlich ueberarbeitet — split nach
  SQLite-Unit vs Postgres-Integration (RLS + Concurrency),
  vitest/tsc/eslint/vite build/e2e in einem Wrapper.
- **`frontend/vite.config.ts` + `tsconfig.json`** — Test-Pfade
  integriert, neue Frontend-Utils (`errorMessage.test.ts`,
  `formatters.test.ts`) laufen jetzt in der CI.
- **`deploy.sh`** um Smoke-Test-Steps erweitert (+14 LOC).

### 📝 Vorbereitung fuer 1.4.0
- **Avalonia-UI-Installer-Scaffolding** unter `installer/setup/`
  (C# / Avalonia, `1.4.0-alpha.1`). Noch **nicht** Teil des
  ausgelieferten Pakets — wird ab 1.4.0 als `praxiszeit-setup.exe`
  den NSSM/setup.bat-Stack bei Neuinstallationen ersetzen.

## [1.3.4] - 2026-04-11

**Massives Cleanup-Release nach einer Live-Debugging-Session auf einem
Kunden-Windows-Server.** Alle 1.3.x-ZIPs davor (1.3.0 bis 1.3.3) hatten
einen kritischen Auslieferungs-Bug: das **Frontend-Bundle** war ein
uralter vor-Sprint-1.3.0-Build (ohne CSRF-Interceptor), weil
`tools/build-release.sh` bei existierender `frontend/dist/` den
vite-Build uebersprang. Kombiniert mit dem neuen CSRF-Middleware-Check
im Backend hat das jede mutating Operation aus dem Browser zum 403
gemacht. Der gesamte Tag war im Wesentlichen eine Kaskade aus diesem
einen Auslieferungsfehler + Follow-up-Bugs.

### 🔴 Auslieferungs-Bug (hoch kritisch)
- **F-055: `tools/build-release.sh`** baut das Frontend jetzt **immer**
  neu (vite build, 5-10 Sek). Die alte "skip if dist/ exists"-
  Optimierung wird nur noch greifen wenn explizit `--skip-frontend`
  uebergeben wird, und selbst dann prueft sie dass dist/ wirklich da
  ist. Ohne diesen Fix haben alle 1.3.0-1.3.3-ZIPs stale Frontend
  mitausgeliefert. Der Symptom ist jede mutating Operation -> 403
  CSRF, obwohl Backend+Middleware korrekt waren.

### 🔴 Process Manager Fixes
- **F-053: `praxiszeit-server.py` ssl_cert Pfad-Resolution** —
  relative Pfade in `praxiszeit.conf` (z.B. `"config/ssl/cert.pem"`)
  werden jetzt relativ zu `BASE_DIR` (Install-Root) aufgeloest, nicht
  mehr relativ zu `CONFIG_DIR`. Der alte Code hat aus
  `config/ssl/cert.pem` -> `<install>/config/config/ssl/cert.pem`
  gemacht und die Datei nie gefunden. Resultat: `SSL cert/key not
  found` trotz vorhandener Dateien, Startup ohne TLS.
- **F-054: `praxiszeit-server.py` Health-Check Protocol** — die
  Health-Check-URL wird jetzt an `ssl_enabled` (tatsaechlicher State)
  gekoppelt, nicht an die Truthiness der Config-Strings `ssl_cert` /
  `ssl_key`. Wenn die Config auf Cert-Dateien zeigte die nicht
  existierten, pollte der alte Code `https://localhost:443/api/health`
  gegen einen Plain-HTTP-Server -> TLS-Handshake-Fehler -> 30 Sek
  Timeout -> `uvicorn failed to become healthy` -> NSSM-Restart-Loop.
- **`load_config()` BOM-Toleranz** — `praxiszeit.conf` die mit Notepad
  editiert wurde hat ein UTF-8 BOM am Anfang, `tomllib` knallt dann
  mit `TOMLDecodeError: Invalid statement (at line 1, column 1)` und
  der Service crasht sofort nach dem Start. `load_config` strippt den
  BOM jetzt automatisch mit einer WARN-Meldung und faengt ungueltiges
  UTF-8 / TOML-Syntax-Fehler mit lesbarer Fehlermeldung ab.

### 🔴 Update-Wizard Fixes
- **`update-wizard.ps1` Step-Backup** nutzte
  `$psi.ArgumentList.Add(...)` — das ist eine **.NET 5+ API**, die auf
  Windows-built-in PowerShell 5.1 (.NET Framework 4.x) nicht
  existiert. `$psi.ArgumentList` ist dort `$null`, `.Add()` crasht mit
  "Es ist nicht moeglich, eine Methode fuer einen Ausdruck
  aufzurufen, der den Wert NULL hat". Fix: `$psi.Arguments` als String
  (mit Quoting fuer Pfade mit Spaces).
- **Neue `Step-PipInstall`** — laeuft idempotent nach dem Robocopy
  Dateien-Update und vor dem Service-Start. Fuehrt
  `python -m pip install --quiet -r requirements.txt` aus. Ohne diesen
  Schritt hatten Updates zwischen Releases mit neuen Python-
  Dependencies keine Chance zu funktionieren, weil der Wizard die
  Files kopiert hat aber das site-packages nie aktualisiert wurde.
- **em-dashes entfernt** aus den Script-Strings (war die 1.3.3
  Hotfix-Ursache, dokumentiert hier fuer den Kontext).

### 🟡 Neues Tool
- **`tools/generate-self-signed-cert.py`** — offizielles CLI-Tool zum
  Generieren von self-signed SSL-Certs via `cryptography`. Parameter:
  `<ip> [<practice_name>] [<out_dir>]`. Setzt Subject CN=IP, SAN mit
  `localhost` + `127.0.0.1` + IP, 10 Jahre gueltig, RSA 2048 +
  SHA-256. Auf Unix zusaetzlich `chmod 0600` auf `key.pem`. Ersetzt
  die Linux-install.sh-openssl-Generation cross-platform und wird in
  der kommenden 1.4.0 `praxiszeit.exe` als optionaler Installer-Step
  eingebaut.
- `datetime.utcnow()` -> `datetime.now(timezone.utc)` im Tool (die
  inline-Variante aus der Live-Debugging-Session hatte
  DeprecationWarnings in Python 3.13).

### 🟡 Build
- `tools/build-release.sh` hat jetzt `--skip-frontend` als Flag (als
  Escape-Hatch, nicht als Default). Default-Version auf `1.3.4`.

### 📝 Bekannte Baustellen fuer 1.4.0
- **Service-Worker + self-signed Cert**: Chrome weigert sich, einen SW
  ueber HTTPS mit untrusted Cert zu registrieren. Fuer Offline-/PWA-
  Features muss das Cert als Trusted Root auf jedem Client installiert
  werden. Workaround fuer die Praxis: SW-Registrierung defensiv
  abschalten wenn das Cert nicht trusted ist.
- **`praxiszeit.exe` als Single-File-Installer** (Inno Setup) — war
  schon im Native-Installer-Design (Spec §6) vorgesehen, ersetzt dann
  `setup.bat` + `install-service.bat` + `update-wizard.*` durch einen
  echten Windows-Installer mit Wizard-Pages. Baustelle fuer 1.4.0.

---

## [1.3.3] - 2026-04-11

**Hotfix: update-wizard.ps1 Parse-Fehler auf deutschem Windows.**

### 🔴 Fix
- **`update-wizard.ps1`**: drei em-dashes (`U+2014`) in Warn-Meldungen
  entfernt (Zeile 373, 391, 396). PowerShell 5.1 auf de-DE Windows
  liest PS1-Dateien ohne BOM als Windows-1252; die UTF-8-kodierten
  em-dashes (`0xE2 0x80 0x94`) wurden als ungueltige String-Abschluesse
  interpretiert und rissen die gesamte Funktion `Step-ACLFix` /
  `Step-Backup` mit einer Kaskade von "missing catch / unterminated
  string / missing closing brace"-Fehlern auseinander. Der Wizard war
  in 1.3.2 deshalb ueberhaupt nicht lauffaehig. Jetzt durchgaengig
  7-bit ASCII in allen Meldungsstrings; `parse-file` vor jedem Build
  sicherstellen.

### Hinweis fuer Dev
Beim Ausliefern von PS1-Dateien via Repo: entweder strikt ASCII oder
UTF-8 **mit BOM** — sonst ueberrascht dich PS 5.1 mit
encoding-abhaengigen Parse-Fehlern auf Kunden-Servern.

---

## [1.3.2] - 2026-04-11

**Grafischer Update-Wizard fuer Windows.**

### 🟢 Neue Features
- **`installer/windows/update-wizard.bat` + `update-wizard.ps1`** —
  WinForms-GUI-Wizard, der eine bestehende Installation auf die
  gebuendelte Version aktualisiert. Erkennt Install-Verzeichnis
  automatisch (Fallback: Folder-Browser), zeigt alte/neue Version im
  Welcome-Screen, walkt durch sechs Schritte mit Live-Log und
  Progress-Bar:
  1. **ACL-Fix** auf `.db-credentials` (F-037, idempotent — greift auch
     bei bestehenden 1.3.0-Installs)
  2. **DB-Backup** via `praxiszeit-server.py backup` (Service laeuft
     noch → pg_dump funktioniert)
  3. **Service stoppen**
  4. **`robocopy`** mit Excludes fuer `data/`, `logs/`, `ssl/`,
     `praxiszeit.conf`, `.db-credentials`, `.secret-key`, `license.key`
     → User-Daten bleiben unangetastet
  5. **Service starten** (Alembic-Migrationen laufen beim Start)
  6. **Scheduled Task `PraxisZeit-Backup`** registrieren/aktualisieren
  Der Wizard refust, aus dem Installationsverzeichnis selbst gestartet
  zu werden (verhindert Self-Overwrite-Korruption). Launcher erzwingt
  Admin-Rechte via `net session`-Check und UAC-Prompt.

### 🟡 Build
- **`tools/build-release.sh`** kopiert `update-wizard.bat` und
  `update-wizard.ps1` ins Windows-Paket. Default-Version auf 1.3.2
  gebumpt. End-of-build-Summary unterscheidet jetzt Erstinstallation
  und Update-Flow.

---

## [1.3.1] - 2026-04-11

**Windows Native: Automatisches DB-Backup + ACL-Fix.**

### 🟢 Neue Features
- **`installer/windows/backup.bat`** — dünner Wrapper um
  `praxiszeit-server.py backup`, loggt nach `logs/backup.log`, erzwingt
  `PYTHONUTF8=1`. Manuell aufrufbar oder via Scheduled Task.
- **`install-service.bat`** legt jetzt neben dem NSSM-Service und der
  Firewall-Regel eine Scheduled Task `PraxisZeit-Backup` an (täglich
  03:00, läuft als `SYSTEM`, damit `.db-credentials` gelesen werden
  kann). Retention (31 Tage default, konfigurierbar via
  `[backup] retention_days`) war bereits in 1.3.0 in `create_backup()`.
- **`uninstall-service.bat` + `uninstall.bat`** entfernen die Scheduled
  Task sauber mit `schtasks /delete`.

### 🔴 Security / Fixes
- **F-037: `_restrict_file_permissions()`** gewährt jetzt zusätzlich
  `BUILTIN\Administrators:(R)` auf `.db-credentials` (via SID
  `*S-1-5-32-544`, locale-unabhängig). Vorher konnte ein manueller
  Admin-Aufruf von `praxiszeit-server.py backup` mit
  `PermissionError: [Errno 13] '.db-credentials'` abbrechen, wenn der
  Service die Datei zuvor als `SYSTEM`+`MACHINE$` geschrieben hatte.
  Die scheduled task lief vorher schon korrekt (als `SYSTEM`), der Fix
  betrifft ausschließlich den interaktiven CLI-Workflow.

### 🟡 Build
- **`tools/build-release.sh`** kopiert `backup.bat` ins Windows-Paket.
  Default-Version auf `1.3.1` gebumpt.

### 📝 Bekannte Lücken (nicht geschlossen)
- **`core/updater.py`** hat noch keinen `apply`-Flow — die Admin-API
  bietet nur `/status` + `/check`, kein `/download` + `/apply`. Das
  pre-update-Backup (Spec §5) ist deshalb leer-konstruiert und wird
  erst mit der Umsetzung der Apply-Route relevant.

---

## [1.3.0] - 2026-04-11

**Großer Security-, Stability-, Performance- und UX-Review — 41 gezielte Fixes.**
362/362 Backend-Tests grün (inkl. 13 RLS-Integrationstests gegen echte
Postgres-DB), Frontend TypeScript + Vite-Build clean, ESLint 9 + flat
config installiert (0 Errors, 86 Legacy-Warnings für späteren Cleanup).

### 🔴 Security (CRITICAL + HIGH)
- **Access-Token raus aus `localStorage`** — Token lebt nur noch im
  Modul-Memory, Session-Recovery über HttpOnly-Refresh-Cookie beim
  App-Start. XSS-Steals-Session-Vektor geschlossen.
- **CSRF Double-Submit-Cookie** — neue `CSRFMiddleware`, nicht-HttpOnly
  `csrf_token` Cookie beim Login/Refresh, `X-CSRF-Token`-Header-Check
  auf allen unsafe Methods.
- **Hardcoded `PraxisZeit2025!` aus Installern entfernt** — PowerShell /
  `/dev/urandom` generiert zur Installationszeit ein Einmal-Passwort.
  `uninstall.bat` + neuer `restore-backup.template.bat` lesen
  `.db-credentials` statt Fallback zu verwenden.
- **`.env` Schutz** — neuer `pre-commit-hook.sh` blockiert `.env`-Commits
  (auch mit `-f`), `init-db-user.sh` lehnt schwache `APP_DB_PASSWORD` ab,
  Dev-`.env` auf zufällige Werte rotiert.
- **Multi-Tenant tenant_id-Filter** — `is_holiday()` + alle Bulk-Deletes
  + Admin-User-Lookups kriegen explizite `tenant_id`-Filter zusätzlich
  zu RLS. Neuer Helper `_get_user_in_tenant()` in `admin_users.py`.
- **Auth-Enumeration-Fix** — Dummy-bcrypt-Verify bei nicht-existenten
  Usern gleicht Timing aus, `_failed_logins` als OrderedDict-LRU mit
  O(1)-Eviction, `move_to_end()` hält legitime Opfer-Lockouts "heiß"
  gegen Attacker-Evict-Flood.
- **`bcrypt_sha256` statt bcrypt** — eliminiert die stillschweigende
  72-Byte-Trunkierung. Opportunistischer Re-Hash beim nächsten Login
  migriert Legacy-Hashes ohne User-Reset.
- **Ed25519-signierte Update-Manifeste** — `updater.py` verifiziert
  Manifest-Signatur vor Download-URL-Vertrauen + Host-Allowlist + HTTPS
  erzwungen. Trust-Root aus `license.py` wiederverwendet.
- **HSTS nur noch auf HTTPS** — verhindert Safari-Brick in Native-HTTP-
  Install.
- **GitHub-Issue-URL-Sanitizer** — `sanitizeGithubUrl()` blockt
  `javascript:`-URLs auf Admin-ErrorMonitoring-Seite.
- **`update_profile` Audit-Log** bei E-Mail-Änderungen.

### 🟠 Stability (HIGH)
- **`with_for_update()` auf CR/VR/Absence/TimeEntry Approval-Paths** —
  schließt Double-Click-Races bei `review_change_request`,
  `review_vacation_request`, `create_absence` (Duplicate-Probe) und
  `admin_update_time_entry`.
- **`create_year_closing` pg_advisory_xact_lock(42, hash(tenant,year))**
  + Pending-CR-Refusal.
- **`_close_stale_entry`** committet nicht mehr mitten im Request,
  schreibt `TimeEntryAuditLog(action="update", source="auto_close")` so
  dass §3 ArbZG-Verstöße vom Vortag nachverfolgbar sind.
- **clock-in §5 DST-Fix** — `datetime.combine(..., tzinfo=LOCAL_TZ)`
  statt naive, korrekte Wall-Clock-Rechnung auch bei Umschalttagen.
- **`get_weekly_hours_for_date` Bypass entfernt** — die zwei lokalen
  Shadow-Helpers in `calculation_service.py` gelöscht, authoritative
  Lookup mit optionalem `wh_changes=` Prefetch. Einziger Ort der
  `user.weekly_hours` direkt liest.
- **`company_closures.py:145`** reicht jetzt `weekly_hours` explizit durch.
- **`AbsenceType.OTHER` Semantik** dokumentiert + Pinning-Test
  `test_absence_type_other_reduces_target_and_ignores_actual`.
- **`vacation_requests.create` Validierung** auf Parität mit
  `create_absence` (Range, first/last_work_day, Dedup, Budget).
- **`get_vacation_account` Div-by-Zero-Fix** — früher Return mit
  `track_hours=False` Sentinel für Users ohne Zeiterfassung.
- **`xls_import_service.execute_import` try/except + rollback +
  Failure-Audit-Log** statt halbimportierter DB.

### 🟡 Performance
- **Migration 031 — Composite-Indexe** `(tenant_id, user_id, date)` auf
  `time_entries` und `absences`, `(user_id, effective_from)` auf
  `working_hours_changes`.
- **`net_hours` `@expression`** — `func.sum(TimeEntry.net_hours)` läuft
  jetzt auf SQL-Ebene (dialekt-portabel mit `CASE` statt `GREATEST`).
- **`date_in_year` / `date_in_month` / `date_in_year_up_to_month`** in
  neuer `services/date_filters.py`. **70+ non-sargable
  `extract('year'|'month', date)`-Sites** umgeschrieben in `reports`,
  `calculation_service`, `journal_service`, `export_service`,
  `ods_export_service`, `time_entries`, `admin_time_entries`,
  `absences`, `vacation_requests`, `rest_time_service`.
- **Reports `/yearly-absences` Bulk-Fetch** aller 5 Absence-Typen in
  einem Query statt N+1 per User per Typ.
- **Per-(tenant_id, year) Holiday-Cache** in `holiday_service` — 
  `is_holiday()` ist O(1) nach erstem Zugriff, Invalidierung auf
  `sync_holidays` / `delete_all_holidays`.
- **`db.close()` vor `StreamingResponse`** in allen 6 Export-Endpoints
  (Excel/ODS/PDF × monthly/yearly/yearly-classic) — keine Pool-
  Connection wird mehr während Download gehalten.
- **Audit-Log Cursor-Pagination** — neuer `before`-Query-Parameter
  (ISO-8601) als bevorzugter Modus, Legacy-Offset bleibt backward-compat.
- **`get_deletion_candidates` Single GROUP BY MAX(date)** statt N+1
  per-User-Lookup.

### 🎨 Frontend UX
- **Dashboard + TimeTracking Async-Cleanup** — `cancelled`-Flag-Pattern
  in allen useEffects, keine setState-after-unmount-Warnings mehr.
- **`formatHoursHM` NaN-Guard** + `parseHours()`-Helper. 5 Form-Sites
  (`UserForm`, `WorkingHoursModal`, `AbsenceCalendarPage`,
  `AdminAbsences`, `Reports`) migriert.
- **Toast-IDs via `crypto.randomUUID()`** — keine React-Key-Kollisionen
  bei Burst-Errors mehr.
- **Router-aware ErrorBoundary** (`key={location.pathname}`) — ein
  broken Page lähmt nicht mehr die ganze SPA.
- **PWA `registerType: 'prompt'`** + Confirm-Dialog statt silent reload
  beim Deploy.
- **`Layout.isActive`** highlighted Sub-Routes korrekt
  (`/admin/users/:id/journal` → "Benutzerverwaltung"-Nav-Entry).

### 🏗️ Infrastructure
- **`deploy.sh`** refuses dirty working tree, pre-migration `pg_dump` via
  `scripts/backup-db.sh`, automatischer `git reset --hard` + Rebuild bei
  Healthcheck-Failure, `PREVIOUS_COMMIT` als Rollback-Target gespeichert.
- **Backend multi-stage Dockerfile** — `gcc` und `postgresql-client` aus
  Runtime raus (nur Build-Stage hat sie). Python gepinnt auf
  `3.12.7-slim-bookworm`. Image ~200MB kleiner.
- **Prometheus + Grafana Image-Tags gepinnt** — `v2.54.1` / `11.2.0`.
- **Grafana provisioned Dashboards locked** — `editable: false`,
  `disableDeletion: true`.
- **`praxiszeit-server.py`** konfigurierbares `bind_address` (für
  127.0.0.1-only Deployments) + loud WARNING bei `0.0.0.0` ohne TLS.
- **ESLint 9 Flat Config** installiert (`eslint.config.js`) — 0 Errors,
  86 Legacy-Warnings. `scripts/local-ci.sh` wrappt Backend-Tests,
  TypeScript, ESLint, Vite-Build (und optional E2E) in eine Pipeline.
- **pre-commit Hook** (`scripts/pre-commit-hook.sh` +
  `scripts/install-git-hooks.sh`) blockt `.env`-Commits und
  `PraxisZeit2025!`-Referenzen.

### Breaking Changes / Migration Notes
- **Alembic-Migration 031** läuft automatisch beim nächsten
  `alembic upgrade head`. Erzeugt drei `CREATE INDEX` — keine Daten-
  migration.
- **APP_DB_PASSWORD**: Dev-`.env` auf zufälligen Wert rotiert. Bei
  bestehenden Docker-Volumes muss das DB-User-Passwort einmalig per
  `ALTER ROLE praxiszeit_app PASSWORD '<new>'` synchronisiert werden —
  oder Volume neu anlegen (neues `init-db-user.sh` setzt es dann
  automatisch).
- **SECRET_KEY**: Dev-`.env` rotiert. Existing-Sessions werden beim
  Restart ungültig — User müssen sich einmal neu einloggen.
- **Legacy bcrypt-Hashes** werden beim nächsten erfolgreichen Login
  automatisch auf `bcrypt_sha256` migriert — kein Passwort-Reset nötig.
- **CSRF-Token**: Frontend-Interceptor setzt den neuen Header
  automatisch. Dritt-Client-Integrationen (pure Bearer-API-Clients)
  sind nicht betroffen, die CSRF-Middleware prüft nur bei vorhandenem
  `csrf_token`-Cookie.
- **GitHub-Actions deaktiviert** (Repository-Level) während dieser PR.
  Vor Production-Release wieder aktivieren:
  `gh api repos/phash/praxiszeit/actions/permissions -X PUT --input - <<< '{"enabled":true}'`

### Documentation
- Ausführliche Sprint-Dokumentation in Commit-Message
- PR-Body mit gruppierten Fixes nach Priorität
- neue Migration-Notes für 1.3.0

## [1.2.1] - 2026-04-07

### Bug Fixes (Native Windows Installation)
- **psql -v Interpolation:** Variable-Substitution funktioniert nicht mit `-c` auf PostgreSQL 18.3/Windows — direkte SQL-Strings statt `-v`/`:'var'`
- **Python 3.13 Glob-Expansion:** `*` in subprocess-Argumenten wird auf Windows als Glob expanded — explizite Werte statt Wildcards
- **SYSTEM-Permissions:** `.db-credentials` war fuer NSSM-Service (SYSTEM-Account) nicht lesbar — `SYSTEM:(R,W)` hinzugefuegt
- **cp1252 UnicodeEncodeError:** Emoji-Output crasht im NSSM-Service — `PYTHONUTF8=1` fuer uvicorn-Subprozesse
- **Config-to-Env Bridge:** `SECRET_KEY`, `ADMIN_EMAIL` etc. fehlten als Env-Vars fuer Backend — TOML-Config-Werte werden in `cmd_start()` gesetzt
- **FRONTEND_DIR:** Relativer Pfad im Native-Modus falsch aufgeloest — absoluter Pfad via `APP_DIR / "frontend"`
- **LICENSE_KEY_PATH:** Relativer Pfad nicht auffindbar vom Backend-CWD — wird zu absolutem Pfad aufgeloest
- **SPA-Fallback 405:** Catch-All `@app.get("/{full_path:path}")` verursachte 405 fuer POST/PUT/DELETE API-Requests — ersetzt durch `SPAFallbackMiddleware`
- **Session-Verlust:** `SECRET_KEY` wurde bei jedem Restart neu generiert (alle JWTs ungueltig) — Key wird in `config/.secret-key` persistiert
- **cookie_secure ohne SSL:** Secure-Cookie bei HTTP-Verbindung vom Browser abgelehnt — `cookie_secure=false` fuer Nicht-SSL-Setups

### Documentation
- Neue Doku: `docs/NATIVE-WINDOWS-PITFALLS.md` — 10 Fallstricke mit Loesungen und Deployment-Checkliste
- CLAUDE.md um Native-Windows-Regeln erweitert

## [1.2.0] - 2026-04-03

### Features
- **Überstundenausgleich korrigiert:** Soll bleibt bestehen, Ist = 0h — Überstundenkonto sinkt korrekt um Tagessoll
- **Absences mit Start-/Endzeit:** Abwesenheiten können optional Start-/Endzeit haben ("ganzer Tag" wenn leer)
- **Änderungsanträge für Abwesenheiten:** Mitarbeiter können Krank, Fortbildung, Urlaub etc. per CR beantragen (entry_kind="absence")
- **Journal Multi-Entry:** Tage mit mehreren Einträgen zeigen jeden Eintrag auf eigener Zeile mit Typ
- **Gemischte Tage:** Arbeitszeit + Absence am selben Tag korrekt dargestellt und berechnet
- **Admin CR-Filter:** User-Dropdown + Zeitraum-Filter (1M/3M/Jahr/Vorjahr/freier Zeitraum)
- **Echtzeit-Ruhezeitwarnung:** Warnung beim Einstempeln wenn <11h seit letztem Arbeitsende (§5 ArbZG)
- **Pausen-Mindestdauer:** Warnung bei Pausenabschnitten <15 Minuten (§4 Satz 2 ArbZG)
- **DSGVO sick_hours opt-in:** JSON-Reports maskieren Krankheitsdaten ohne explizites opt-in

### Bug Fixes
- CR-Approval Race Condition: Status wird erst nach Precondition-Checks gesetzt
- CR-Approval: Unique-Constraint-Check bei Datumsänderung
- CR-Approval: Nutzt jetzt CR-Tenant-ID statt Admin-Tenant-ID
- Absence-CRs: Duplikat-Prüfung für pending Anträge
- TimeEntry-CRs: Duplikat-Check für CREATE-Anträge repariert
- UPDATE-CRs: Zukunftsdaten blockiert, start >= end Validierung
- DELETE-CRs: Entry-Existenzprüfung vor Status-Änderung
- Journal: SICK-Tag nutzt daily_target statt absence_sum
- Journal: Absence-Ordering deterministisch (.order_by type)
- Mixed-Day: VACATION/OTHER/OVERTIME reduzieren Soll korrekt
- Mixed-Day: Absence-Erstellung löscht nicht mehr alle TimeEntries (keep_time_entries)
- Mixed-Day: Delete löscht nur gezielten Eintrag, nicht Absence
- Sick Absence: Nutzt historische weekly_hours statt aktuelle
- Cross-Year Vacation: Budget-Check pro Jahr statt nur Startjahr
- Overlapping Absences: Verschiedene Typen am selben Tag blockiert
- net_hours: Floor bei 0 (kann nicht negativ werden)
- Export: Mehrere TimeEntries pro Tag werden korrekt exportiert
- Export: Historische daily_target pro Tag statt statisch
- Export: "Überstundenausgleich" Label in Absence-Type-Maps
- Export: Night-Work-Days zählt unique Dates statt Entries
- Export: PDF zeigt non-sick Absence-Notes unabhängig von health_data Flag
- ODS: Überstundenausgleich-Spalte in Jahresübersicht ergänzt
- Reports: monthly weekly_hours nutzt historischen Wert
- Dashboard: Missing-Bookings-Query mit Datum-Untergrenze (Performance)
- Vacation-Approval: Historische weekly_hours + Cross-Year-Budget-Check
- User-Purge: VacationRequest FK-Bereinigung verhindert IntegrityError
- DSGVO: Kalender maskiert "sick" → "absent" für nicht-Admins
- Absence-Löschung: Audit-Log vor delete
- Alembic: version_num_width=128 verhindert Spalten-Overflow
- formatHoursSimple: Negative Werte korrekt dargestellt
- Admin 8h-Warnung: DAILY_HOURS_WARNING in Admin-Pfaden ergänzt
- Holiday-Service: is_holiday() mit optionalem Tenant-Filter
- Anonymisierung: Grace-Period Null-Check für Legacy-User

### Tests
- 343 Backend-Tests (vorher 275, +68 neue)
- Absence-Typ-Matrix: Parametrisierte Tests für alle 5 Typen
- Überstundenausgleich: 8 Tests (Soll/Ist, Tagesplan, Journal, kumulativ)
- Jahresabschluss: 8 Tests (Übertrag, Resturlaub, Mid-Year-Hire, Idempotenz)
- Mixed-Day: 4 Tests (Work+Training, Work+Sick, Work+Vacation, Work+Overtime)
- Absence-CRs: 8 Tests (Model, Zeiten, Approval, Journal-Integration)
- Berechnungs-Units: 13 Tests (Target, Actual, Balance, Vacation, Carryover)

### Security & Compliance
- 4 Runden Bughunting-Review (31 Bugs gefunden und gefixt)
- ArbZG-Audit: KONFORM (§2-§18 vollständig geprüft)
- DSGVO-Audit: KONFORM (Art. 5/6/9/15/17/20/25/32 geprüft)
- Security-Review: 0 kritische Schwachstellen

### Migration
- `030` — Absence start_time/end_time + Change Request absence fields (entry_kind, absence_id, proposed/original_absence_type/hours)

---

## [1.1.0] - 2026-03-26

- Multi-Tenant Phase 1-3 (RLS, Tenant-Modell, Auth-Middleware)
- VacationRequest absence_type Erweiterung

## [1.0.0] - 2026-02-14

- Initiales Release
