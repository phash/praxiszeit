# PraxisZeit – Handbuch für Administratoren

**Version 2.4 | Stand: Juni 2026 (für PraxisZeit 1.9.0)**

---

## Inhaltsverzeichnis

1. [Einleitung](#1-einleitung)
2. [Login und Zugangsdaten](#2-login-und-zugangsdaten)
3. [Admin-Dashboard](#3-admin-dashboard)
4. [Benutzerverwaltung](#4-benutzerverwaltung)
5. [Abwesenheitskalender](#5-abwesenheitskalender)
6. [Berichte und Exporte](#6-berichte-und-exporte)
7. [Abwesenheitsanträge genehmigen](#7-abwesenheitsanträge-genehmigen)
8. [Korrekturanträge prüfen](#8-korrekturanträge-prüfen)
9. [Änderungsprotokoll (Audit-Log)](#9-änderungsprotokoll-audit-log)
10. [Fehler-Monitoring](#10-fehler-monitoring)
11. [Betriebsferien verwalten](#11-betriebsferien-verwalten)
12. [Import](#12-import)
13. [Einstellungen](#13-einstellungen)
    - [Feiertage / Eigene Feiertage](#feiertage)
    - [Sondertage 24./31.12.](#sondertage-2431-12)
    - [Urlaubsgenehmigung](#urlaubsgenehmigung)
    - [Pflicht-Pause-Ausnahme](#pflicht-pause-ausnahme)
    - [Soll-Arbeitszeit-Fenster (Puffer)](#soll-arbeitszeit-fenster-puffer)
    - [Farben](#farben)
14. [ArbZG-Compliance-Berichte](#14-arbzg-compliance-berichte)
15. [Überstundenausgleich](#15-überstundenausgleich)
16. [Änderungsanträge für Abwesenheiten](#16-änderungsanträge-für-abwesenheiten)
17. [Rechtliche Grundlagen](#17-rechtliche-grundlagen)
18. [Berechnungsgrundlagen (Anhang)](#18-berechnungsgrundlagen-anhang)
19. [Datensicherung (Backup & Restore)](#19-datensicherung-backup--restore)

---

## 1. Einleitung

Dieses Handbuch richtet sich an **Administratoren** von PraxisZeit. Als Admin haben Sie Zugriff auf alle Bereiche der Anwendung – von der Benutzerverwaltung über Berichte bis hin zu gesetzlichen Compliance-Auswertungen.

**Navigation:** In der linken Seitenleiste finden Sie zwei Bereiche:
- **Mitarbeiter-Bereich**: Dashboard, Zeiterfassung, Abwesenheiten, Profil (Ihre eigene Zeiterfassung)
- **Administration**: Admin-Dashboard, Benutzerverwaltung, Änderungsanträge, Berichte, Abwesenheiten, Änderungsprotokoll, Fehler-Monitoring, Anträge, Import, Einstellungen

**Rechtliche Verantwortung:** Als Admin sind Sie für die gesetzeskonforme Dokumentation der Arbeitszeiten gemäß dem **Arbeitszeitgesetz (ArbZG)** verantwortlich. PraxisZeit unterstützt Sie mit automatischen Prüfungen und Berichten.

---

## 2. Login und Zugangsdaten

![Login-Seite](screenshots/01-ma-login.png)

**Zugang:**
- **URL:** `http://[Ihre-Server-Adresse]/login`
- **Benutzername:** Ihr Administrator-Benutzername
- **Passwort:** Ihr Passwort (mind. 10 Zeichen, Groß-/Kleinbuchstabe, Ziffer)

Nach erfolgreichem Login werden Sie automatisch zum Dashboard weitergeleitet. Die Admin-Navigation erscheint unter dem Abschnitt **„Administration"** in der linken Seitenleiste.

---

## 3. Admin-Dashboard

Das Admin-Dashboard gibt Ihnen eine sofortige **Gesamtübersicht über Ihr gesamtes Team**.

![Admin-Dashboard](screenshots/14-admin-dashboard.png)

### Teamübersicht

Das Admin-Dashboard zeigt alle aktiven Mitarbeiter mit ihren aktuellen Monatsdaten:

| Spalte | Bedeutung |
|--------|-----------|
| **Name** | Vor- und Nachname des Mitarbeiters |
| **Wochenstd.** | Aktuell gültige Wochenstunden |
| **Soll** | Zu leistende Stunden im aktuellen Monat |
| **Ist** | Tatsächlich geleistete Stunden |
| **Saldo** | Differenz Ist – Soll (H:MM, + = Überstunden, – = Fehlstunden) |
| **Übersto. Kum.** | Kumulierter Jahressaldo |
| **Urlaub** | Verbleibende Urlaubstage (Ampelfarbe) |
| **Krank** | Kranktage im aktuellen Monat |

### Statistiken (oben)

- **Mitarbeitende:** Anzahl aktiver Mitarbeiter
- **Ø Saldo (Monat):** Durchschnittlicher Monatssaldo aller Mitarbeiter
- **Monat:** Aktuell angezeigter Monat

**Monat wechseln:** Mit den Pfeilen `<` und `>` wechseln Sie den angezeigten Monat.

**Suche:** Nutzen Sie das Suchfeld, um nach einem bestimmten Mitarbeiter zu filtern.

**Detailansicht:** Klicken Sie auf den Pfeil am Ende einer Zeile, um die Detailansicht des Mitarbeiters zu öffnen.

> **Tipp:** Der Ampelindikator beim Urlaub zeigt auf einen Blick, wer dringend Urlaub nehmen sollte.

### Jahresabschluss

Unterhalb der Monatsübersicht finden Sie die **Jahresübersicht** mit Urlaubs- und Krankheitstagen aller Mitarbeiter. Hier können Sie den Jahresabschluss durchführen.

#### Jahresabschluss erstellen

1. Wählen Sie das gewünschte **Jahr** im Zahlenfeld aus
2. Klicken Sie auf den orangefarbenen Button **Jahresabschluss**
3. Im Bestätigungsdialog werden Sie informiert, dass Überstunden-Saldo und Resturlaub aller aktiven Mitarbeiter berechnet und als Übernahme ins Folgejahr gespeichert werden
4. Bestätigen Sie mit **Jahresabschluss erstellen**

Der Jahresabschluss berechnet für jeden aktiven Mitarbeiter:
- **Überstunden-Saldo** zum 31.12. des gewählten Jahres
- **Resturlaub** (nicht genommene Urlaubstage)

Diese Werte werden als Vorjahresübernahme für das Folgejahr gespeichert und fließen dort in die Stunden- und Urlaubsberechnung ein.

#### Jahresabschluss löschen

Falls ein Jahresabschluss versehentlich erstellt wurde, können Sie ihn wieder löschen:

1. Wählen Sie das Jahr, dessen Abschluss Sie löschen möchten
2. Klicken Sie auf den roten Button **Abschluss löschen**
3. Lesen Sie den Bestätigungsdialog sorgfältig — die Löschung ist **unwiderruflich**
4. Bestätigen Sie mit **Jahresabschluss löschen**

> **Wichtig:** Das Löschen entfernt **alle** Übernahmen für das Folgejahr — auch manuell eingetragene Vorjahresübernahmen einzelner Mitarbeiter. Prüfen Sie daher vor dem Löschen, ob manuelle Übernahmen existieren, die Sie anschließend neu eintragen müssen.

---

## 4. Benutzerverwaltung

Die Benutzerverwaltung ist das Herzstück der Admin-Funktion.

![Benutzerverwaltung](screenshots/15-admin-benutzer.png)

### Übersicht aller Mitarbeiter

Die Liste zeigt alle aktiven Mitarbeiter mit:
- **Name** und **Benutzername** (Kürzel)
- **Rolle** (Mitarbeiter:in / Admin)
- **Wochenstd.** und **Arbeitstage**
- **Urlaubskonto** (Budget, Genommen, Übrig – mit Ampelfarbe)

**Filter:** Aktivieren Sie **„Inaktive anzeigen"** oder **„Ausgeblendete anzeigen"** um deaktivierte Mitarbeiter einzublenden.

### Neuen Mitarbeiter anlegen

![Neuen Benutzer anlegen](screenshots/16-admin-benutzer-formular.png)

Klicken Sie auf **„Neuer Mitarbeiter:in"** und füllen Sie das Formular aus:

**Pflichtfelder:**
| Feld | Beschreibung |
|------|-------------|
| **Benutzername** | Eindeutiger Login-Name (z. B. `m.hoffmann`) |
| **Passwort** | Initiales Passwort (mind. 10 Zeichen, Groß-/Kleinbuchstabe, Ziffer) |
| **Rolle** | Mitarbeiter:in oder Admin |
| **Wochenstunden** | Vertraglich vereinbarte Wochenstunden (Standard: 40). Viertelstunden (0,25/0,75) bei individuellen Tagesstunden möglich. |
| **Arbeitstage pro Woche** | Anzahl der Arbeitstage 1–7 (Standard: 5). Bestimmt den anteiligen Urlaubsvorschlag. |
| **Urlaubstage** | Jährlicher Urlaubsanspruch in **Tagen**. Vorschlag anteilig nach Arbeitstagen: `30 × Arbeitstage ÷ 5` (5 Tage → 30, 3 Tage → 18). Überschreibbar. |

**Optionale Felder:**
| Feld | Beschreibung |
|------|-------------|
| **E-Mail** | Für Kontaktzwecke (optional) |
| **Vorname / Nachname** | Anzeigename |
| **Stundenzählung aktiv (Soll-Stunden werden berechnet)** | Standardmäßig aktiv. Deaktivieren Sie diese Option für **Mitarbeiter ohne Stundenzählung** – siehe eigener Abschnitt unten. |
| **ArbZG-Prüfungen aussetzen (§18 ArbZG – leitende Angestellte)** | Setzt die ArbZG-Prüfungen für diese Person aus. **Eigenständige, von der Stundenzählung unabhängige Einstellung** – siehe Hinweis unten. |
| **Nachtarbeitnehmer** | § 6 ArbZG – 8h-Tageslimit bei Nachtarbeit |
| **Nimmt an Betriebsferien teil** | Standardmäßig aktiv. Bestimmt, ob der/die Mitarbeitende bei angelegten Betriebsferien automatisch Abwesenheitseinträge erhält – **unabhängig von der Rolle**. Für reine Verwaltungs-Accounts (Admin ohne eigene Zeiterfassung) abwählbar. Siehe eigener Abschnitt unten. |
| **Erster / Letzter Arbeitstag** | Eintrittsdatum und ggf. geplantes Austrittsdatum. Das **Soll wird nur innerhalb dieses Zeitraums** berechnet – vor dem Eintritt bzw. nach dem Austritt entsteht kein Stundensoll, und auch tatsächlich erfasste Zeiten außerhalb des Beschäftigungszeitraums erzeugen keine Überstunden. Der **Urlaubsanspruch wird anteilig** berechnet (für ein unterjähriges Eintritts-/Austrittsjahr). |
| **Individuelle Tagesstunden** | Abweichende Stundenverteilung Mo–Fr statt einheitlich (nur bei aktiver Stundenzählung) |
| **Abteilung/Bereich** | Optionale Zuordnung (Freitext); ermöglicht Filterung im Abwesenheitskalender |
| **Anfangssaldo Überstunden** | Übernommener Überstundensaldo zum Startjahr (kann +/- sein; nur bei aktiver Stundenzählung) |
| **Soll-Arbeitszeiten je Wochentag** | Optionaler Soll-Beginn / Soll-Ende pro Wochentag (Mo–Fr) – siehe eigener Abschnitt „Soll-Arbeitszeiten" unten. |

> **Wichtig – zwei getrennte Einstellungen, bitte nicht verwechseln:**
> - **„Stundenzählung aktiv"** steuert nur, **ob** für diese Person Soll-/Ist-Stunden und Überstunden geführt werden. Sie hat **nichts** mit dem § 18 ArbZG zu tun.
> - **„ArbZG-Prüfungen aussetzen (§ 18 ArbZG)"** ist eine eigene Checkbox und setzt die arbeitszeitrechtlichen Prüfungen aus. Diese betrifft ausschließlich leitende Angestellte im Sinne des § 18 ArbZG.
>
> Beide Optionen lassen sich frei und unabhängig kombinieren. Aktivieren Sie das § 18-Flag nur für Personen, die tatsächlich unter § 18 ArbZG fallen.

> **Überstunden-Übersicht:** Die Benutzerübersicht zeigt pro Mitarbeiter:in zusätzlich zum Urlaubskonto den **aktuellen Überstundensaldo (Jahr bis heute)** in der Spalte **„Überstunden (JTD)"**. Bei Mitarbeitern ohne Stundenzählung erscheint hier „—" (→ [Abschnitt „Mitarbeiter ohne Stundenzählung"](#mitarbeiter-ohne-stundenzählung)).

> ⚠️ **Wichtig bei unterjährigem Eintritt:** Tragen Sie für Mitarbeitende, die **nicht seit dem 1. Januar** im System sind, unbedingt den **„Ersten Arbeitstag"** ein. Ohne dieses Datum zählt das System das Stundensoll für den Eintrittsmonat (bzw. die JTD-Überstunden ab dem 1. Januar) auch für Tage **vor** dem tatsächlichen Eintritt mit – es entstehen **Phantom-Minusstunden**. Mit gesetztem Eintrittsdatum bleibt das Überstundenkonto korrekt.

> **So wird Urlaub berechnet (Tagesprinzip, § 3 BUrlG / BAG):** Der Urlaub wird **nach Arbeitstagen** geführt, nicht nach Stunden. Ein freier Arbeitstag verbraucht **genau 1 Urlaubstag**, unabhängig von der Tagesstundenzahl – ein langer Tag (z. B. 9 h) kostet so viel wie ein kurzer (z. B. 4 h): einen Tag. Ein **halber freier Tag** (Halbtags-Abwesenheit) kostet **0,5 Urlaubstage**. Auch bei **individuellen Tagesstunden** kostet jeder Arbeitstag gleich viel (Montag = Dienstag). Der Jahresanspruch wird anteilig nach Arbeitstagen vorgeschlagen (`30 × Arbeitstage ÷ 5`) und bei unterjährigem Eintritt/Austritt zeitanteilig berechnet. Intern speichert das System Stunden (für die Soll-/Ist-Berechnung); der **Verbrauch wird tagebasiert** gezählt und im Urlaubskonto in Tagen angezeigt.

### Mitarbeiter ohne Stundenzählung

Über die Checkbox **„Stundenzählung aktiv (Soll-Stunden werden berechnet)"** (standardmäßig aktiv) legen Sie fest, ob für eine Person die Arbeitszeit ausgewertet wird. Deaktivieren Sie die Checkbox, wird der/die Mitarbeitende zu einem **Mitarbeiter ohne Stundenzählung**.

**Was sich ändert, wenn die Stundenzählung deaktiviert ist:**
- **Keine Soll-/Ist-Stundenberechnung** und **keine Überstundenberechnung.** In der Benutzerübersicht erscheint in der Spalte „Überstunden (JTD)" ein „—".
- Die Felder „Anfangssaldo Überstunden", „Individuelle Tagesstunden" und das Soll-/Ist-Dashboard entfallen für diese Person.
- **Urlaub und Krankheit werden trotzdem geführt** – und zwar **tagebasiert**: 1 genommener freier Arbeitstag = 1 Urlaubstag (Sondertage wie Heiligabend zählen ebenfalls als 1 Tag). Der Urlaubsanspruch bleibt anteilig nach Arbeitstagen und behält die Vorjahresübernahme.

**Wofür gedacht:** z. B. Personen, deren Arbeitszeit nicht erfasst, deren Urlaub aber dennoch verwaltet werden soll.

> **Abgrenzung (bitte nicht verwechseln):** „Mitarbeiter ohne Stundenzählung" hat **nichts** mit § 18 ArbZG zu tun. Die § 18-Ausnahme („ArbZG-Prüfungen aussetzen") ist eine **separate, unabhängige Checkbox** und betrifft ausschließlich leitende Angestellte. Eine Person kann z. B. Stundenzählung haben **und** § 18-befreit sein – oder umgekehrt.
>
> **Hinweis zu Halbtagen:** Bei Mitarbeitern ohne Stundenzählung zählt ein halber Tag derzeit als voller Tag (es findet keine Stunden-/Halbtagsverrechnung statt).

### Soll-Arbeitszeiten (Soll-Arbeitszeit-Fenster, #201)

Im Benutzerformular finden Sie den Bereich **„Soll-Arbeitszeiten je Wochentag"**. Dort können Sie pro Wochentag (Mo–Fr) einen **Soll-Beginn** (oberes Feld) und ein **Soll-Ende** (unteres Feld) hinterlegen. Beide Felder sind **optional** – leer lassen bedeutet „kein Fenster". Das System rechnet dann erfasste Zeiten außerhalb dieses Fensters **nicht** auf die Arbeitszeit an, sondern kürzt sie auf den jeweils erlaubten Rand (zuzüglich eines konfigurierbaren Puffers).

**Funktionsweise:**
- Zeiten außerhalb des Fensters werden **nicht angerechnet**: Die angerechnete Zeit beginnt frühestens beim Soll-Beginn (minus Puffer) und endet spätestens beim Soll-Ende (plus Puffer).
- Der **tatsächlich gestempelte Zeitpunkt** bleibt als Rohstempel erhalten und ist im Eintrag nachvollziehbar (§ 16 ArbZG – Dokumentationspflicht). Salden und Überstundenkonto rechnen ausschließlich mit der angerechneten (gekürzten) Zeit.
- **Puffer:** Der systemweite Toleranzbereich (Standard: **15 Minuten**) ist unter **Einstellungen → „Soll-Arbeitszeit-Fenster"** im Feld **„Puffer für Soll-Arbeitszeit-Fenster (Min.)"** konfigurierbar (→ [Abschnitt 13](#soll-arbeitszeit-fenster-puffer)). Innerhalb des Puffers wird die Differenz angerechnet; außerhalb wird auf den Fensterrand gekürzt.

**Opt-in:** Sind für einen Mitarbeiter **keine** Soll-Zeiten hinterlegt, ändert sich nichts am bisherigen Verhalten. Die Kappung wird außerdem **übersprungen** bei Mitarbeitern ohne Stundenzählung. Bei **§ 18-befreiten** Mitarbeitern (ArbZG-Prüfungen ausgesetzt) wird **trotzdem gekappt** – es handelt sich um eine reine Anwesenheits-Policy, nicht um eine ArbZG-Prüfung.

Eingehängt ist die Kappung an **allen** Schreibpfaden: Ein-/Ausstempeln, manuelles Anlegen/Bearbeiten von Zeiteinträgen, Admin-Korrekturen, XLS-Import und genehmigte Korrekturanträge.

> **Rechtlicher Hinweis:** Die Nicht-Anrechnung von Zeiten außerhalb des Soll-Fensters ist eine **Arbeitgeber-seitige Policy-Entscheidung** (keine gesetzliche Vorgabe). Die arbeitsrechtliche Zulässigkeit (z. B. Umgang mit angeordneter Mehrarbeit) verantwortet der Betrieb. Der erhaltene Rohstempel dokumentiert gemäß § 16 ArbZG die tatsächliche Anwesenheit.

### Mitarbeiter bearbeiten

![Mitarbeiter bearbeiten](screenshots/17-admin-benutzer-bearbeiten.png)

Klicken Sie in der Benutzerliste auf den Namen des Mitarbeiters.

**Stundenänderungen:**
Wenn Sie die Wochenstunden ändern (z. B. bei Teilzeitumstellung), wird ein Eintrag in der **Stundenhistorie** erstellt. Frühere Monate werden weiterhin mit den damals gültigen Stunden berechnet.

1. Name/Kürzel des Mitarbeiters öffnen
2. Neue Wochenstunden eintragen
3. **Wirkungsdatum** angeben (ab wann gelten die neuen Stunden)
4. Speichern

**Mitarbeiter deaktivieren:**
Setzen Sie den Status auf **„Inaktiv"**. Deaktivierte Mitarbeiter können sich nicht mehr einloggen, historische Daten bleiben erhalten.

> **Rechtlicher Hinweis (§16 ArbZG):** Arbeitszeitaufzeichnungen müssen **mindestens 2 Jahre** aufbewahrt werden. Löschen Sie daher niemals Mitarbeiterdaten – deaktivieren Sie die Konten.

---

## 5. Abwesenheitskalender

![Abwesenheitskalender Admin](screenshots/18-admin-abwesenheitskalender.png)

### Kalenderansicht

Abwesenheiten werden farbcodiert nach Typ dargestellt (z. B. Urlaub, Krankheit, Fortbildung, Überstundenausgleich, Sonstiges). Die genauen Farben sind unter **Einstellungen → „Farben"** je Typ frei konfigurierbar (→ [Abschnitt 13](#farben)). Jeder Mitarbeitende hat zusätzlich eine **eigene Kalenderfarbe** im Teamkalender. Diese kann der Mitarbeiter selbst unter **Profil → Kalenderfarbe** wählen oder der Administrator im **Benutzerformular** (Feld **Kalenderfarbe**) für ihn vorgeben.

**Sondertage und Feiertage im Kalender:**
- **Gesetzliche Feiertage** und arbeitsfreie **Sondertage** (24./31.12. im Modus „Frei") werden **grau** hinterlegt und sind nicht buchbar.
- **Halbe Sondertage** (24./31.12. im Modus „Halbtag") werden **amber/gelb** hinterlegt.

Die Anzeige folgt der Konfiguration unter **Einstellungen → „Sondertage (24./31.12.)"** (→ [Abschnitt 13](#sondertage-2431-12)).

### Als Admin Abwesenheit eintragen

1. Klicken Sie auf **„Abwesenheit eintragen"**
2. Wählen Sie den **Mitarbeiter** aus dem Dropdown
3. Wählen Sie Datum, Typ und ggf. Zeitraum
4. Speichern

### Betriebsferien im Kalender

Betriebsferien werden als gesonderte Einträge angezeigt und betreffen alle aktiven Mitarbeiter gleichzeitig (→ [Abschnitt 11](#11-betriebsferien-verwalten)).

---

## 6. Berichte und Exporte

![Berichte](screenshots/19-admin-berichte.png)

### Monatsreport

- **Inhalt:** Tägliche Zeiteinträge aller Mitarbeiter im gewählten Monat
- **Format:** Excel (.xlsx) oder CSV
- **Details pro Mitarbeiter:** Datum, Wochentag, Start, Ende, Pause, Ist-Stunden, Soll-Stunden, Abwesenheitstyp, Monatssaldo

**Verwendung:** Gehaltsabrechnung, monatliche Kontrolle, Dokumentation

### Jahresreport Classic

- **Format:** Excel (.xlsx) oder CSV, ca. 17 KB
- **Inhalt:** Pro Mitarbeiter eine Zeile pro Monat
- **Details:** Soll, Ist, Saldo, Urlaubstage, Krankheitstage, Fortbildungstage

**Verwendung:** Jahresüberblick, schnelle Kontrolle

### Jahresreport Detailliert

- **Format:** Excel (.xlsx) oder CSV, ca. 108 KB
- **Inhalt:** Jeden Tag des Jahres pro Mitarbeiter
- **Hinweis:** Generierungszeit 3–5 Sekunden

**Verwendung:** Detaillierte Jahresauswertung, Steuerberater, Betriebsprüfung

### Bericht erstellen

1. Wählen Sie den **Berichtstyp**
2. Wählen Sie **Monat** oder **Jahr**
3. Optional: **„Krankheiten einstellen"** – legt fest, ab welchem Datum § 3 EntgFG (Kranktage als gearbeitete Zeit) gilt
4. Klicken Sie auf **Excel** oder **CSV**
5. Die Datei wird automatisch heruntergeladen

> **Rechtlicher Hinweis (§16 ArbZG):** Exportieren Sie regelmäßig (mindestens jährlich) und sichern Sie die Dateien sicher für **2 Jahre**.

---

## 7. Abwesenheitsanträge genehmigen

Wenn die Genehmigungspflicht aktiviert ist, landen Urlaubsanträge von Mitarbeitern zur Prüfung beim Admin.

### Genehmigungspflicht konfigurieren

**Admin-Navigation → Anträge** (Seitentitel: „Abwesenheitsanträge")

Oben auf der Seite befindet sich ein Toggle **„Urlaubsanträge genehmigungspflichtig"**:

| Toggle | Verhalten |
|--------|-----------|
| **Aus** (Standard) | Mitarbeiter buchen Urlaub direkt |
| **Ein** | Urlaubsanträge landen als „Offen" beim Admin |

### Antrag genehmigen

1. Antragskarte aufrufen – zeigt Mitarbeitername, Zeitraum, Notiz
2. Klicken Sie auf **„Genehmigen"** (grüner Button)
3. Das System trägt automatisch Abwesenheiten für alle Werktage ein (Wochenenden und Feiertage ausgeschlossen)

> **Achtung:** Eine Genehmigung ist unwiderruflich. Zum Stornieren müssen die erstellten Abwesenheitseinträge manuell gelöscht werden.

### Antrag ablehnen

1. Klicken Sie auf **„Ablehnen"** (roter Button)
2. Optional: Ablehnungsgrund eingeben
3. Bestätigen

Der Mitarbeiter sieht den Ablehnungsgrund im Tab „Meine Anträge".

---

## 8. Korrekturanträge prüfen

Mitarbeiter können Korrekturanträge stellen, wenn Zeiteinträge nachträglich geändert werden müssen.

![Korrekturanträge Admin](screenshots/20-admin-korrekturantraege.png)

### Antrag prüfen und entscheiden

![Korrekturantrag Details](screenshots/21-admin-korrekturantrag-details.png)

1. Klicken Sie auf den Antrag oder **„Prüfen"**
2. Das Formular zeigt den aktuellen und den gewünschten Eintrag im Vergleich
3. Lesen Sie die Begründung des Mitarbeiters
4. Entscheiden Sie:
   - **„Genehmigen"**: Zeiteintrag wird automatisch geändert
   - **„Ablehnen"**: Optionalen Ablehnungsgrund eingeben

**Filter-Tabs:** Alle / Offen / Genehmigt / Abgelehnt

> **Empfehlung:** Prüfen Sie Korrekturanträge zeitnah, damit der Monatssaldo der Mitarbeiter aktuell bleibt.

---

## 9. Änderungsprotokoll (Audit-Log)

Das Audit-Log protokolliert alle Aktionen im System vollständig und unveränderlich.

![Audit-Log](screenshots/22-admin-auditlog.png)

### Was wird protokolliert?

| Aktion | Beispiel |
|--------|---------|
| **Login/Logout** | Wer hat sich wann eingeloggt? |
| **Zeiteinträge** | Erstellen, Ändern, Löschen |
| **Abwesenheiten** | Neue Abwesenheiten, Stornierungen |
| **Benutzerverwaltung** | Neue Benutzer, Passwortänderungen, Deaktivierungen |
| **Korrekturanträge** | Stellen, Genehmigen, Ablehnen |
| **Betriebsferien** | Anlegen und Löschen |
| **Pflicht-Pause-Ausnahmen** | Erfasste § 4-Ausnahmen samt Begründung (Quelle „break_waiver") |

### Filter und Suche

- **Zeitraum**: Von–Bis-Datum wählen
- **Benutzer**: Nur Aktionen eines bestimmten Mitarbeiters
- **Aktion**: Nur bestimmte Aktionstypen

> **Rechtlicher Hinweis:** Das Audit-Log erfüllt die Anforderungen einer unveränderlichen Aufzeichnung gem. § 16 ArbZG und kann bei Betriebsprüfungen als Nachweis dienen.

---

## 10. Fehler-Monitoring

Das Fehler-Monitoring zeigt technische Fehler, die im Betrieb aufgetreten sind.

![Fehler-Monitoring](screenshots/23-admin-fehlermonitoring.png)

### Fehler-Liste

Jeder Eintrag zeigt:
- **Zeitstempel** des Fehlers
- **Fehlertyp** und Beschreibung
- **Häufigkeit** (wie oft ist dieser Fehler aufgetreten?)
- **Benutzerkontext** (welcher Benutzer war betroffen?)

### Was tun bei Fehlern?

1. **Lesen Sie die Fehlermeldung** – oft gibt es eine verständliche Beschreibung
2. **Prüfen Sie die Häufigkeit** – einmalige Fehler sind meist unkritisch
3. **Bei wiederkehrenden Fehlern**: Zeitstempel und Fehlermeldung notieren, IT-Support kontaktieren oder direkt als GitHub Issue melden (Button in der Detailansicht)

---

## 11. Betriebsferien verwalten

Betriebsferien sind betriebsweite Schließzeiten, die für alle Mitarbeiter automatisch als Abwesenheit eingetragen werden.

![Betriebsferien](screenshots/24-admin-betriebsferien.png)

### Wofür werden Betriebsferien verwendet?

- Weihnachtsschließzeiten
- Sommerferien-Schließzeiten
- Brückentage (wenn die gesamte Praxis geschlossen ist)

### Betriebsferien anlegen

Navigieren Sie zu **Abwesenheiten → Tab „Betriebsferien"** und klicken Sie auf **„Neue Betriebsferien"**:

1. **Bezeichnung** (z. B. „Weihnachtsschließzeit 2026")
2. **Von** (Startdatum) und **Bis** (Enddatum)
3. Speichern

**Was passiert automatisch:**
- Alle aktiven Mitarbeiter **mit der Option „Nimmt an Betriebsferien teil"** (Standard) erhalten für jeden Werktag Abwesenheitseinträge – unabhängig von der Rolle, also auch Admins, die zugleich als Mitarbeiter geführt werden. Reine Verwaltungs-Accounts können die Option in der Benutzerverwaltung abwählen.
- Urlaubstage werden **nicht** verbraucht
- Wochenenden und gesetzliche Feiertage werden übersprungen
- Mitarbeiter erhalten Einträge **nur für Tage innerhalb ihres Beschäftigungszeitraums**: noch nicht eingetretene (Eintrittsdatum in der Zukunft) oder bereits ausgetretene Mitarbeiter bekommen für die betreffenden Tage **keine** Betriebsferien-Einträge

> **Tipp – nachträglich Berechtigte ergänzen:** Aktivieren Sie die Option „Nimmt an Betriebsferien teil" bei einem Mitarbeiter und speichern Sie die Benutzer-Änderung. Die Abwesenheiten werden **automatisch** für alle laufenden und künftigen Betriebsferien nachgetragen – ein erneutes Speichern der Betriebsferien ist nicht mehr nötig, und bereits erfasste Arbeitszeiten bleiben erhalten. (Bereits abgelaufene Betriebsferien werden bewusst nicht rückwirkend ergänzt.)

### Betriebsferien löschen

Klicken Sie auf das Löschen-Symbol. Die Abwesenheitseinträge werden bei allen Mitarbeitern automatisch entfernt.

---

## 12. Import

Unter **Import** können Sie Zeiteinträge oder Abwesenheitsdaten aus externen Quellen (z. B. CSV-Dateien) in das System importieren.

Dieser Bereich ist für die initiale Datenübernahme oder die Massenbefüllung bei der Einführung von PraxisZeit vorgesehen.

**Vorgehensweise:** Laden Sie die Vorlagendatei herunter, befüllen Sie sie gemäß der Vorgaben und laden Sie die Datei wieder hoch.

---

## 13. Einstellungen

Unter **Einstellungen** konfigurieren Sie alle systemweiten Parameter. Jeder Bereich hat einen eigenen **Speichern**-Button – Änderungen werden erst durch Klick darauf wirksam.

<a id="onboarding"></a>
### Onboarding / Willkommens-Tour

Beim **ersten Login** sehen neue Mitarbeitende und Admins eine kurze, rollenspezifische **Willkommens-Tour** mit den wichtigsten Bereichen. Im Bereich **„Onboarding / Willkommens-Tour"** schalten Sie diese mit dem Schalter **„Willkommens-Tour anzeigen"** praxisweit ein oder aus (Standard: **an**). Bereits gesehene Touren erscheinen ohnehin nicht erneut. Eine eigene **Schnellstart**-Anleitung für die Ersteinrichtung erreichen Sie jederzeit über den Button **„Schnellstart"** unten links in der Seitenleiste.

<a id="feiertage"></a>
### Feiertage / Eigene Feiertage

**Feiertage:** Wählen Sie das **Bundesland**, dessen gesetzliche Feiertage gelten sollen. Nach dem Speichern werden alle gesetzlichen Feiertage automatisch neu berechnet. Feiertage reduzieren das Stundensoll und werden im Kalender grau dargestellt.

**Eigene Feiertage:** Legen Sie zusätzlich lokale/regionale Feiertage an (z. B. Schützenfest, Karneval) – mit **Name** und **Datum**. Eigene Feiertage reduzieren die Soll-Zeit wie gesetzliche Feiertage und können bearbeitet oder gelöscht werden. Gesetzliche Feiertage werden nur zur Information angezeigt und lassen sich nicht ändern. Über das Jahr-Auswahlfeld blättern Sie zwischen den Jahren. Eigene Feiertage bleiben erhalten, wenn Sie das Bundesland wechseln.

<a id="sondertage-2431-12"></a>
### Sondertage 24./31.12.

Heiligabend (24.12.) und Silvester (31.12.) sind keine gesetzlichen Feiertage. Im Bereich **„Sondertage (24./31.12.)"** legen Sie für **jeden** der beiden Tage getrennt fest, wie er behandelt wird.

**Modus** (Auswahlfeld pro Tag):
| Modus | Bedeutung |
|-------|-----------|
| **Arbeitstag** (Standard) | Voller Arbeitstag, normales Tagessoll |
| **Halbtag** | Halbes Tagessoll; im Kalender amber/gelb hinterlegt |
| **Frei** | Arbeitsfrei (wie ein Feiertag), Tagessoll 0; im Kalender grau hinterlegt |

**Anrechnung** (zusätzliches Auswahlfeld, erscheint nur bei Modus „Frei"):
| Auswahl | Bedeutung |
|---------|-----------|
| **Urlaub** | Der freie Tag wird vom Urlaubskonto abgezogen |
| **Bezahlte Freistellung** | Kein Abzug vom Urlaubskonto (wie ein Feiertag) |

Die Einstellung wirkt sich automatisch auf **Stundensoll**, **Urlaubskonto** und die **Kalenderdarstellung** aus. Klicken Sie nach Änderungen auf **Speichern**.

<a id="urlaubsgenehmigung"></a>
### Urlaubsgenehmigung

Der Schalter **„Genehmigung erforderlich"** steuert, ob Urlaubsanträge von einem Admin genehmigt werden müssen, bevor sie wirksam werden:
- **Aus** (Standard): Mitarbeiter buchen Urlaub direkt.
- **Ein**: Urlaubsanträge landen als „Offen" im Bereich **Anträge** beim Admin (→ [Abschnitt 7](#7-abwesenheitsanträge-genehmigen)).

Diese Einstellung lässt sich alternativ auch direkt im Bereich „Abwesenheitsanträge" umschalten.

<a id="pflicht-pause-ausnahme"></a>
### Pflicht-Pause-Ausnahme

> **Hinweis:** Hintergrund zur Pausenpflicht selbst (§ 4 ArbZG) siehe [Abschnitt 14 → „Pflicht-Pause-Ausnahme"](#pflicht-pause-ausnahme-§4-arbzg).

Konnte eine gesetzlich vorgeschriebene Pause (§ 4 ArbZG) nicht eingelegt werden, kann ein Eintrag mit einer **Pflicht-Begründung** trotzdem erfasst werden, statt ihn zu blockieren. Der Schalter **„Genehmigung erforderlich"** steuert das Verhalten:
- **Aus** (Standard): Der Eintrag wird sofort gespeichert; die Abweichung wird als Warnung gemeldet und im Änderungsprotokoll dokumentiert.
- **Ein**: Der Eintrag wird erst nach **Admin-Genehmigung** wirksam (**4-Augen-Prinzip**).

> **4-Augen-Prinzip:** Ein Admin darf seine **eigene** Pflicht-Pause-Ausnahme **nicht selbst genehmigen** – sie muss von einem anderen Admin geprüft werden.

<a id="soll-arbeitszeit-fenster-puffer"></a>
### Soll-Arbeitszeit-Fenster (Puffer)

Im Bereich **„Soll-Arbeitszeit-Fenster"** legen Sie im Feld **„Puffer für Soll-Arbeitszeit-Fenster (Min.)"** den systemweiten Toleranzbereich für die in der Benutzerverwaltung hinterlegten Soll-Arbeitszeiten fest (Standard: **15** Minuten). Anwesenheit vor oder nach dem Soll-Fenster zählt nur bis zu diesem Puffer zur Arbeitszeit; Stempel außerhalb des Puffers werden auf die Fenstergrenze gekürzt. Details und rechtlicher Hinweis: [Abschnitt 4 → „Soll-Arbeitszeiten"](#soll-arbeitszeiten-soll-arbeitszeit-fenster-201).

<a id="farben"></a>
### Farben

Im Bereich **„Farben"** legen Sie für jeden Anwesenheits- und Abwesenheitstyp eine eigene Farbe fest (Arbeit/Anwesenheit, Fortbildung, Urlaub, Krank, Überstundenausgleich, Sonstiges, Bezahlte Freistellung). Die Farben werden im Kalender, in den Übersichten und bei der Zeiterfassung verwendet. Eine kleine „Aa"-Vorschau zeigt, ob die Schrift auf der gewählten Farbe lesbar bleibt.

---

## 14. ArbZG-Compliance-Berichte

PraxisZeit überwacht automatisch die Einhaltung des Arbeitszeitgesetzes.

![ArbZG-Berichte](screenshots/25-admin-arbzg-berichte.png)

Die ArbZG-spezifischen Auswertungen finden Sie auf der **Berichte-Seite** weiter unten.

---

### §5 ArbZG – Ruhezeitverstöße

**Gesetzliche Anforderung:**
Nach § 5 ArbZG müssen Arbeitnehmer nach Beendigung der täglichen Arbeitszeit eine ununterbrochene Ruhezeit von **mindestens 11 Stunden** haben.

[§5 ArbZG](https://www.gesetze-im-internet.de/arbzg/__5.html)

**Was der Bericht zeigt:**
- Alle Fälle, bei denen die 11-Stunden-Ruhezeit unterschritten wurde
- Mitarbeitername, betroffene Daten, tatsächliche Ruhezeit

**Handlungsbedarf:**
- Ruhezeitverstöße dokumentieren und Ursachen beseitigen
- In Ausnahmefällen (§ 7 ArbZG) kann die Ruhezeit auf 9 Stunden verkürzt werden (Ausgleich innerhalb von 4 Wochen)

---

### §6 ArbZG – Nachtarbeit-Auswertung

**Gesetzliche Anforderung:**
Nachtarbeitnehmer (> 48 Nachtarbeitstage/Jahr, 23–6 Uhr) haben eine reduzierte Tageshöchstarbeitszeit von **8 Stunden**.

[§6 ArbZG](https://www.gesetze-im-internet.de/arbzg/__6.html)

**Was der Bericht zeigt:**
- Mitarbeiter mit 48+ Nachtarbeitstagen im gewählten Jahr
- Anzahl der Nachtarbeitstage und 8h-Warnungen

**Handlungsbedarf:**
- Regelmäßige arbeitsmedizinische Untersuchung anbieten (§ 6 Abs. 3 ArbZG)

---

### §11 ArbZG – Sonntagsarbeit (15-freie-Sonntage-Regel)

**Gesetzliche Anforderung:**
Arbeitnehmer müssen mindestens **15 Sonntage pro Jahr** beschäftigungsfrei haben.

[§11 ArbZG](https://www.gesetze-im-internet.de/arbzg/__11.html)

**Was der Bericht zeigt:**
- Anzahl der gearbeiteten Sonntage pro Mitarbeiter im gewählten Jahr
- Warnung bei Annäherung an oder Überschreitung der 37 Arbeitsonntage (52 − 15)

---

### §11 ArbZG – Ersatzruhetag-Tracking

**Gesetzliche Anforderung:**
Bei Sonntagsarbeit: Ersatzruhetag innerhalb von **2 Wochen**.
Bei Feiertagsarbeit: Ersatzruhetag innerhalb von **8 Wochen**.

**Was der Bericht zeigt:**
- Alle Sonntagseinsätze ohne dokumentierten Ersatzruhetag
- Frist und Status (innerhalb Frist / Frist abgelaufen)

**Handlungsbedarf:**
- Gewährte Ersatzruhetage als Abwesenheit (Typ: Sonstiges) eintragen

---

### §3 ArbZG – Tageshöchstgrenze (10 Stunden)

Nach § 3 ArbZG darf die werktägliche Arbeitszeit 8 Stunden nicht überschreiten; sie darf auf bis zu **10 Stunden** verlängert werden, wenn innerhalb von 6 Kalendermonaten / 24 Wochen im Schnitt 8 Stunden eingehalten werden. PraxisZeit behandelt die 10-Stunden-Grenze je nach Erfassungsweg unterschiedlich:

- **Beim Live-Ausstempeln** wird ein Tag über 10 Stunden **nicht mehr blockiert** – die Arbeitszeit ist bereits tatsächlich geleistet und muss gemäß § 16 ArbZG dokumentiert werden. Der Eintrag wird gespeichert, und der § 3-Verstoß wird als **deutliche Warnung** gemeldet (und steht für die Compliance-Berichte zur Verfügung).
- **Bei manueller Eingabe oder einem Antrag** (frei wählbare Start-/Endzeit) bleibt die 10-Stunden-Grenze eine **harte Sperre**: Ein solcher Eintrag kann nicht über 10 Stunden hinaus gespeichert werden.

Eine **8-Stunden-Warnung** weist bereits ab Überschreiten der Regelgrenze auf den nötigen Ausgleich hin. § 18-befreite Mitarbeitende sind von diesen Prüfungen ausgenommen.

---

<a id="pflicht-pause-ausnahme-§4-arbzg"></a>
### §4 ArbZG – Pausenpflicht und Pflicht-Pause-Ausnahme

Nach § 4 ArbZG ist die Arbeit durch im Voraus feststehende Ruhepausen zu unterbrechen: **mindestens 30 Minuten** bei mehr als 6 Stunden, **mindestens 45 Minuten** bei mehr als 9 Stunden Arbeitszeit.

Wird beim Erfassen, Korrigieren oder Genehmigen eines Eintrags die Pausenpflicht verletzt, blockiert PraxisZeit den Vorgang nicht zwingend. Stattdessen kann eine **dokumentierte Ausnahme mit Pflicht-Begründung** erfasst werden, falls die Pause im konkreten Fall nicht eingelegt werden konnte. Die Begründung wird im Änderungsprotokoll festgehalten.

Ob solche Ausnahmen sofort wirksam werden oder zuerst genehmigt werden müssen, steuern Sie unter **Einstellungen → „Pflicht-Pause-Ausnahme"** (→ [Abschnitt 13](#pflicht-pause-ausnahme)).

> **4-Augen-Prinzip:** Ist die Genehmigungspflicht aktiv, darf ein Admin seine **eigene** Pflicht-Pause-Ausnahme **nicht selbst genehmigen**. Sie muss von einer zweiten Person geprüft werden.

---

### Automatische Warnungen im Alltag

| Warnung | Auslöser | Verhalten | Rechtsgrundlage |
|---------|----------|-----------|----------------|
| **Tageshöchstgrenze** | > 10h Arbeitszeit | Warnung beim Live-Ausstempeln; harte Sperre bei manueller Eingabe/Antrag | § 3 ArbZG |
| **8h-Warnung** | > 8h Arbeitszeit | Warnung | § 3 ArbZG |
| **Pausenpflicht** | < 30 Min. bei > 6h / < 45 Min. bei > 9h | Warnung; dokumentierte Ausnahme mit Begründung möglich | § 4 ArbZG |
| **Sonntagsarbeit** | Eintrag an Sonntag oder Feiertag | Warnung | § 9 ArbZG |
| **Wochenhöchstgrenze** | > 48h/Woche | Warnung | § 14 ArbZG |
| **8h-Warnung Nachtarbeit** | Nachtarbeitnehmer > 8h täglich | Warnung | § 6 ArbZG |
| **Ruhezeitwarnung** | < 11h seit letztem Arbeitsende beim Einstempeln | Warnung | § 5 ArbZG |

---

## 15. Überstundenausgleich

Mitarbeiter können angesammelte Überstunden durch **Überstundenausgleich-Tage** abbauen.

### Funktionsweise

Wenn ein Überstundenausgleich-Tag eingetragen wird:
- **Soll-Stunden** bleiben für den Tag erhalten (z. B. 8h)
- **Ist-Stunden** werden auf 0h gesetzt
- Das Überstundenkonto **sinkt** um die Tagessollzeit

**Beispiel:** Ein Mitarbeiter mit 40h/Woche (8h/Tag) nimmt einen Überstundenausgleich-Tag.
→ Konto: -8h an diesem Tag → Überstunden werden effektiv abgebaut.

### Eintragen

1. **Abwesenheiten** → **Abwesenheit eintragen**
2. **Typ:** „Überstundenausgleich" auswählen
3. Datum(e) auswählen → Speichern

> **Hinweis:** Es gibt keine automatische Prüfung, ob das Überstundenkonto ausreichend gedeckt ist. Prüfen Sie den Kontostand im Admin-Dashboard.

---

## 16. Änderungsanträge für Abwesenheiten

Mitarbeiter können nicht nur Zeiteinträge korrigieren, sondern auch **Abwesenheiten per Änderungsantrag beantragen** (z. B. Fortbildung, Urlaub).

### Ablauf

1. Mitarbeiter erstellt einen Änderungsantrag mit **Typ „Abwesenheit"**
2. Der Antrag enthält: Datum, Abwesenheitstyp, optionale Start-/Endzeit, Begründung
3. Admin prüft und genehmigt/lehnt ab
4. Bei Genehmigung wird die Abwesenheit automatisch erstellt

### Besonderheiten

- **Krankmeldung per Antrag ist gesperrt** — Krankschreibungen müssen vom Admin eingetragen werden
- **Halbe Tage:** Abwesenheiten können optionale Start-/Endzeiten haben (z. B. „Fortbildung nachmittags 13:00–17:00")
- **DSGVO:** Im Kalender sehen Nicht-Admins fremde Kranktage nur als „abwesend" (nicht als „krank")

---

## 17. Rechtliche Grundlagen

| Paragraph | Inhalt | Umsetzung in PraxisZeit |
|-----------|--------|------------------------|
| [§3](https://www.gesetze-im-internet.de/arbzg/__3.html) | Max. 8h/Tag (bis 10h mit Ausgleich) | Warnung > 8h; > 10h: Warnung beim Live-Ausstempeln, harte Sperre bei manueller Eingabe/Antrag |
| [§4](https://www.gesetze-im-internet.de/arbzg/__4.html) | Ruhepausen: 30 Min. ab 6h, 45 Min. ab 9h | Automatische Pausenvalidierung; dokumentierte Ausnahme mit Begründung möglich (optional genehmigungspflichtig, 4-Augen-Prinzip) |
| [§5](https://www.gesetze-im-internet.de/arbzg/__5.html) | Ruhezeit mind. 11h | Ruhezeitbericht im Admin-Bereich |
| [§6](https://www.gesetze-im-internet.de/arbzg/__6.html) | Nachtarbeit 23–6 Uhr: max. 8h für Nachtarbeitnehmer | Nachtarbeit-Flag, 8h-Warnung, Nachtarbeit-Report |
| [§9](https://www.gesetze-im-internet.de/arbzg/__9.html) | Sonn- und Feiertagsruhe | Warnung bei Eintrag an Sonntag/Feiertag |
| [§10](https://www.gesetze-im-internet.de/arbzg/__10.html) | Ausnahmen Sonn-/Feiertagsarbeit | Pflichtfeld „Ausnahmegrund" |
| [§11](https://www.gesetze-im-internet.de/arbzg/__11.html) | Min. 15 freie Sonntage/Jahr; Ersatzruhetag | 15-freie-Sonntage-Report; Ersatzruhetag-Tracking |
| [§14](https://www.gesetze-im-internet.de/arbzg/__14.html) | Außergewöhnliche Fälle: 48h/Woche Warnschwelle | Wochenwarnung > 48h |
| [§16](https://www.gesetze-im-internet.de/arbzg/__16.html) | Aufzeichnungspflicht: 2 Jahre Aufbewahrung | Excel-Exporte; Audit-Log |
| [§18](https://www.gesetze-im-internet.de/arbzg/__18.html) | Ausnahmen für leitende Angestellte | `ArbZG-Prüfungen aussetzen`-Flag |

### Admin-Pflichten im Überblick

1. **Regelmäßige Datenexporte** (mindestens monatlich) und sichere Aufbewahrung für 2 Jahre
2. **Zeitnahe Prüfung** von Korrekturanträgen
3. **Überwachung der ArbZG-Berichte** – besonders §5 (Ruhezeit) und §11 (Sonntage)
4. **Dokumentation von Ausnahmen** (Sonntagsarbeit, verlängerte Arbeitszeiten, Pflicht-Pause-Ausnahmen)
5. **Aktuelle Benutzerdaten** – bei Stundenänderungen immer Wirkungsdatum eintragen
6. **Abgleich Urlaubskonten** mit tatsächlichem Urlaubsanspruch

> **Haftungshinweis:** PraxisZeit unterstützt Sie bei der Einhaltung des ArbZG, ersetzt aber keine Rechtsberatung. Bei arbeitsrechtlichen Fragen wenden Sie sich an einen Fachanwalt für Arbeitsrecht.

---

## 18. Berechnungsgrundlagen (Anhang)

> Dieser Anhang erklärt **vollständig und exakt**, wie PraxisZeit Soll-, Ist-, Überstunden- und Urlaubswerte ermittelt – auf dem tatsächlichen Rechenstand der Software (Version 1.9.0). Die ausführliche, code-nahe Referenz mit allen durchgerechneten Beispielen (Teilzeit, individueller Tagesplan, Pro-rata, Historie) steht in [`docs/BERECHNUNGEN.md`](../BERECHNUNGEN.md).

### 18.1 Grundbegriffe

| Begriff | Bedeutung |
|---------|-----------|
| **Soll** | Stunden, die ein Mitarbeiter an einem Tag/Monat vertraglich arbeiten müsste |
| **Ist** | Tatsächlich erfasste Arbeitszeit + gutgeschriebene Abwesenheiten (Krank/Fortbildung) |
| **Saldo / Überstunden** | Ist − Soll (positiv = Mehrarbeit, negativ = Minusstunden) |
| **Tagessoll** | Soll-Stunden für einen einzelnen Arbeitstag |
| **Tagesprinzip** | Urlaub wird in **Tagen** gezählt (§ 3 BUrlG): 1 freier Arbeitstag = 1 Urlaubstag |
| **Carryover** | Jahresübertrag von Überstunden und Resturlaub ins Folgejahr |

### 18.2 Tagessoll

Bei gleichmäßiger Verteilung gilt:

> **Tagessoll = Wochenstunden ÷ Arbeitstage pro Woche**

⚠️ Der Divisor ist die **Arbeitstage pro Woche**, **nicht** fix 5. Ein Mitarbeiter mit 24 h auf 3 Tage hat **8 h/Tag**, nicht 4,8 h.

| Wochenstunden | Arbeitstage/Woche | Tagessoll |
|---|---|---|
| 40 | 5 | 8,00 h |
| 20 | 5 | 4,00 h |
| 24 | 3 | 8,00 h |
| 20 | 2 | 10,00 h |

Bei **individuellen Tagesstunden** (z. B. Mo 10 h / Di 10 h / Mi 4 h) zählt der konkrete Wert des jeweiligen Wochentags. Wochenenden, Tage vor Eintritt / nach Austritt sowie Mitarbeiter ohne Stundenzählung haben Tagessoll 0.

### 18.3 Ist-Stunden

Pro Zeiteintrag: **Ist = (Ende − Beginn) − Pause**, auf 2 Nachkommastellen gerundet und **nie negativ**.

Ist ein **Soll-Arbeitszeit-Fenster** hinterlegt (→ [Abschnitt 4, Soll-Arbeitszeiten](#4-benutzerverwaltung)), wird die angerechnete Zeit auf das Fenster (± Puffer) gekürzt; der Rohstempel bleibt erhalten (§ 16 ArbZG). Zusätzlich zählen **Krankheit** und **Fortbildung** mit ihren gebuchten Stunden als Ist (siehe Matrix).

### 18.4 Monats-Soll

PraxisZeit geht jeden Kalendertag des Monats durch und addiert das Tagessoll – **außer** an: Wochenenden, Feiertagen, Tagen außerhalb des Beschäftigungszeitraums und Abwesenheitstagen, die das Soll reduzieren (siehe Matrix). Sondertage 24./31.12. wirken mit Faktor 0,5 (Halbtag) bzw. 0 (frei).

### 18.5 Abwesenheits-Typen-Matrix

| Typ | reduziert Soll? | zählt als Ist? | belastet Urlaub? | Effekt aufs Konto |
|-----|:---:|:---:|:---:|---|
| **Urlaub** | ✅ | ❌ | ✅ | saldo-neutral; zieht 1 Urlaubstag |
| **Krank** | ❌ | ✅ | ❌ | saldo-neutral (Soll bleibt, Ist gutgeschrieben, § 3 EntgFG) |
| **Fortbildung** | ❌ | ✅ | ❌ | saldo-neutral (zählt als gearbeitet) |
| **Bezahlte Freistellung** | ✅ | ❌ | ❌ | saldo-neutral, aber **kein** Urlaubsverbrauch |
| **Sonstige** | ✅ | ❌ | ❌ | saldo-neutral |
| **Überstundenausgleich** | ❌ | ❌ (Ist = 0) | ❌ | Soll bleibt, Ist = 0 h → **Überstundenkonto sinkt** |

> **Merksatz:** Krankheit & Fortbildung **füllen das Ist auf** (kein Saldo-Effekt). Urlaub, bezahlte Freistellung & Sonstige **senken das Soll**. Nur der Überstundenausgleich lässt das Soll stehen und baut so Überstunden ab.

### 18.6 Saldo & Überstundenkonto

**Monatssaldo = Monats-Ist − Monats-Soll.** Das kumulierte Überstundenkonto summiert die Monatssalden fortlaufend und startet beim **Jahresübertrag** (Carryover) des Jahres. Die Spalte „Überstunden (JTD)" in der Benutzerübersicht zeigt den Saldo vom 1. Januar bis heute zzgl. Carryover.

### 18.7 Urlaubskonto (Tagesprinzip)

- **Budget** = Jahresanspruch in Tagen (anteilig bei unterjährigem Eintritt/Austritt) + Resturlaub-Carryover.
- **Verbrauch:** Nur Urlaub belastet das Budget. Jeder freie Arbeitstag kostet **1 Tag** (Halbtag 0,5) – unabhängig von der Stundenzahl des Tages.
- **Budget-Check** beim Antrag zählt **buchbare Arbeitstage** (Tagessoll > 0). Eine ganze Urlaubswoche kostet einen 3-Tage-Mitarbeiter nur 3 Tage.
- Jahresanspruch-Vorschlag: `30 × Arbeitstage ÷ 5` (5 Tage → 30; 3 Tage → 18), überschreibbar.

### 18.8 Sonderfälle

- **Mitarbeiter ohne Stundenzählung (leitende Angestellte):** kein Soll/Ist/Überstunden; Urlaub trotzdem tagebasiert (jeder Urlaubs-/Sondertag = 1 Tag).
- **Sondertage 24./31.12.:** je Tag Arbeitstag / Halbtag (Faktor 0,5) / Frei (Faktor 0). „Frei + zählt als Urlaub" zieht 1 Urlaubstag.
- **Eintritt/Austritt:** vor dem ersten / nach dem letzten Arbeitstag entstehen weder Soll noch Ist; der Urlaubsanspruch wird anteilig berechnet.
- **Rückwirkende Stundenänderung:** alte Monate rechnen mit dem damals gültigen Wochensoll (Stundenhistorie / Wirkungsdatum).

### 18.9 Durchgerechnetes Beispiel (Vollzeit)

Profil: 40 h / 5 Tage → Tagessoll 8,00 h, 30 Urlaubstage. Beispielmonat mit 22 Werktagen, davon 1 Feiertag.

```
Werktage 22 − 1 Feiertag − 4 Urlaubstage = 17 Soll-Tage
Monats-Soll  = 17 × 8,00 h               = 136,00 h
Ist (14 Tage à 8,0 h + 3 Tage à 8,5 h)   = 137,50 h
Monatssaldo  = 137,50 − 136,00           = +1,50 h
Urlaubskonto = 30 − 4                     = 26 Tage übrig
```

> Vollständige Beispiele für Teilzeit, individuellen Tagesplan, Pro-rata-Eintritt und rückwirkende Stundenänderung stehen in [`docs/BERECHNUNGEN.md`](../BERECHNUNGEN.md).

---

## 19. Datensicherung (Backup & Restore)

Unter **Admin → Datensicherung** (ab Version 1.9.0) verwalten Sie Backups ohne Kommandozeile — in der Docker- **und** der nativen Installation:

- **Jetzt sichern** — erstellt umgehend ein vollständiges, komprimiertes Backup (`praxiszeit_<Zeitstempel>.sql.gz`, Plain-SQL mit `--clean --if-exists`).
- **Geplante Sicherung** — tägliche automatische Sicherung zur eingestellten Stunde aktivieren, mit Aufbewahrungsdauer (Tage) und optionalem Speicherort.
- **Liste** — vorhandene Sicherungen **herunterladen** (für eine externe Kopie) oder löschen.

**Wo:** Docker im Volume `praxiszeit_backups`, native im `data/backups/`-Verzeichnis.

**§16 ArbZG:** Zeitaufzeichnungen mindestens **2 Jahre** aufbewahren — Aufbewahrungsdauer entsprechend setzen, eine Kopie **außerhalb** des Servers vorhalten und vor jedem Update zusätzlich sichern.

> **Native:** Die *geplante* Sicherung läuft weiterhin über den OS-Timer (systemd/launchd/Task); der *manuelle* Trigger und die Liste funktionieren überall.

**Wiederherstellung** (idempotent dank `--clean --if-exists`, kein manuelles Leeren der DB nötig) und alle Kommandozeilen-Varianten: siehe [`docs/BACKUP.md`](../BACKUP.md).

---

## Schichtplanung (optional, standardmäßig deaktiviert)

Mit der **Schichtplanung** erstellen Sie wöchentliche Einsatzpläne (wer steht
wann an welchem Arbeitsplatz). Sie ist ein **reines Planungswerkzeug** und
verändert **nicht** Zeiterfassung, Soll/Ist-Stunden, ArbZG-Prüfungen, Urlaub
oder Überstunden.

**Aktivieren:** **Einstellungen → Schichtplanung → „Schichtplanung aktivieren"
→ Speichern.** Das Modul ist nach der Installation **aus**; nur Admins können es
einschalten. Erst danach erscheinen die Menüpunkte und das Dashboard-Widget.

**Stammdaten:** **Standorte** (optional) und **Arbeitsplätze** (Tresen, Labor,
Springer … mit Farbe) anlegen. **Schichtpläne:** beliebig viele benannte
Wochenpläne („Normalzustand", „Azubis Schulferien" …). Im **Wochen-Editor**
Zeitslots per **Drag & Drop** oder Klick-Dialog über die Woche verteilen,
**Mitarbeitende** per Drag auf einen Slot ziehen, optional eine
**Mindestbesetzung** setzen (unterbesetzte Slots werden markiert – weiche
Warnung, blockiert nicht).

**Aktiv schalten** macht einen Plan für alle sichtbar; **mehrere Pläne können
gleichzeitig aktiv** sein. Mitarbeitende sehen ihre heutige Einteilung im
Dashboard. Details: [`docs/SCHICHTPLANUNG.md`](../SCHICHTPLANUNG.md).

---

*PraxisZeit – Zeiterfassungssystem für Arztpraxen und kleine Unternehmen*
*Stand: Juni 2026 (für PraxisZeit 1.9.0)*
