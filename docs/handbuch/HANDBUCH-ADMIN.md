# PraxisZeit – Handbuch für Administratoren

**Version 2.0 | Stand: März 2026**

---

## Inhaltsverzeichnis

1. [Einleitung](#1-einleitung)
2. [Login und Zugangsdaten](#2-login-und-zugangsdaten)
3. [Admin-Dashboard](#3-admin-dashboard)
4. [Benutzerverwaltung](#4-benutzerverwaltung)
5. [Abwesenheitskalender](#5-abwesenheitskalender)
6. [Berichte und Exporte](#6-berichte-und-exporte)
7. [Urlaubsanträge genehmigen](#7-urlaubsanträge-genehmigen)
8. [Korrekturanträge prüfen](#8-korrekturanträge-prüfen)
9. [Änderungsprotokoll (Audit-Log)](#9-änderungsprotokoll-audit-log)
10. [Fehler-Monitoring](#10-fehler-monitoring)
11. [Betriebsferien verwalten](#11-betriebsferien-verwalten)
12. [Import](#12-import)
13. [Einstellungen](#13-einstellungen)
14. [ArbZG-Compliance-Berichte](#14-arbzg-compliance-berichte)
15. [Rechtliche Grundlagen](#15-rechtliche-grundlagen)

---

## 1. Einleitung

Dieses Handbuch richtet sich an **Administratoren** von PraxisZeit. Als Admin haben Sie Zugriff auf alle Bereiche der Anwendung – von der Benutzerverwaltung über Berichte bis hin zu gesetzlichen Compliance-Auswertungen.

**Navigation:** In der linken Seitenleiste finden Sie zwei Bereiche:
- **Mitarbeiter-Bereich**: Dashboard, Zeiterfassung, Abwesenheiten, Profil (Ihre eigene Zeiterfassung)
- **Administration**: Admin-Dashboard, Benutzerverwaltung, Änderungsanträge, Berichte, Abwesenheiten, Änderungsprotokoll, Fehler-Monitoring, Urlaubsanträge, Import, Einstellungen

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
| **Urlaub** | Verbleibende Urlaubsstunden (Ampelfarbe) |
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
| **Wochenstunden** | Vertraglich vereinbarte Wochenstunden (Standard: 40) |
| **Arbeitstage pro Woche** | Anzahl der Arbeitstage 1–7 (Standard: 5) |
| **Urlaubstage** | Jährlicher Urlaubsanspruch (Standard: 30) |

**Optionale Felder:**
| Feld | Beschreibung |
|------|-------------|
| **E-Mail** | Für Kontaktzwecke (optional) |
| **Vorname / Nachname** | Anzeigename |
| **Stundenzählung aktiv** | Deaktivieren für Mitarbeiter ohne Zeiterfassungspflicht |
| **ArbZG-Prüfungen aussetzen** | Für leitende Angestellte nach § 18 ArbZG |
| **Nachtarbeitnehmer** | § 6 ArbZG – 8h-Tageslimit bei Nachtarbeit |
| **Erster / Letzter Arbeitstag** | Eintrittsdatum und ggf. geplantes Austrittsdatum |
| **Individuelle Tagesstunden** | Abweichende Stundenverteilung Mo–Fr statt einheitlich |

> **Rechtlicher Hinweis (§18 ArbZG):** Leitende Angestellte können von ArbZG-Beschränkungen ausgenommen werden. Aktivieren Sie dieses Flag nur für Personen, die tatsächlich unter § 18 ArbZG fallen.

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

Farbcodierte Balken pro Mitarbeiter:
- **Blau**: Urlaub
- **Rot**: Krankheit
- **Orange**: Fortbildung
- **Grau**: Sonstige Abwesenheit

Jeder Mitarbeiter hat zusätzlich eine individuelle **Kalenderfarbe** (konfigurierbar in der Benutzerverwaltung).

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

## 7. Urlaubsanträge genehmigen

Wenn die Genehmigungspflicht aktiviert ist, landen Urlaubsanträge von Mitarbeitern zur Prüfung beim Admin.

### Genehmigungspflicht konfigurieren

**Admin-Navigation → Urlaubsanträge**

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
- Alle aktiven Mitarbeiter erhalten für jeden Werktag Abwesenheitseinträge (Typ: Sonstiges)
- Urlaubstage werden **nicht** verbraucht
- Wochenenden und gesetzliche Feiertage werden übersprungen

### Betriebsferien löschen

Klicken Sie auf das Löschen-Symbol. Die Abwesenheitseinträge werden bei allen Mitarbeitern automatisch entfernt.

---

## 12. Import

Unter **Import** können Sie Zeiteinträge oder Abwesenheitsdaten aus externen Quellen (z. B. CSV-Dateien) in das System importieren.

Dieser Bereich ist für die initiale Datenübernahme oder die Massenbefüllung bei der Einführung von PraxisZeit vorgesehen.

**Vorgehensweise:** Laden Sie die Vorlagendatei herunter, befüllen Sie sie gemäß der Vorgaben und laden Sie die Datei wieder hoch.

---

## 13. Einstellungen

Unter **Einstellungen** konfigurieren Sie systemweite Parameter:

- **Genehmigungspflicht für Urlaubsanträge** (alternativ auch über den Urlaubsanträge-Bereich konfigurierbar)
- Weitere systemweite Konfigurationsoptionen

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

### Automatische Warnungen im Alltag

| Warnung | Auslöser | Rechtsgrundlage |
|---------|----------|----------------|
| **Tageshöchstgrenze** | > 10h Arbeitszeit | § 3 ArbZG |
| **8h-Warnung** | > 8h Arbeitszeit | § 3 ArbZG |
| **Pausenpflicht** | < 30 Min. bei > 6h / < 45 Min. bei > 9h | § 4 ArbZG |
| **Sonntagsarbeit** | Eintrag an Sonntag oder Feiertag | § 9 ArbZG |
| **Wochenhöchstgrenze** | > 48h/Woche | § 14 ArbZG |
| **8h-Warnung Nachtarbeit** | Nachtarbeitnehmer > 8h täglich | § 6 ArbZG |

---

## 15. Rechtliche Grundlagen

| Paragraph | Inhalt | Umsetzung in PraxisZeit |
|-----------|--------|------------------------|
| [§3](https://www.gesetze-im-internet.de/arbzg/__3.html) | Max. 8h/Tag (bis 10h mit Ausgleich) | Warnung > 8h, Sperrung > 10h |
| [§4](https://www.gesetze-im-internet.de/arbzg/__4.html) | Ruhepausen: 30 Min. ab 6h, 45 Min. ab 9h | Automatische Pausenvalidierung |
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
4. **Dokumentation von Ausnahmen** (Sonntagsarbeit, verlängerte Arbeitszeiten)
5. **Aktuelle Benutzerdaten** – bei Stundenänderungen immer Wirkungsdatum eintragen
6. **Abgleich Urlaubskonten** mit tatsächlichem Urlaubsanspruch

> **Haftungshinweis:** PraxisZeit unterstützt Sie bei der Einhaltung des ArbZG, ersetzt aber keine Rechtsberatung. Bei arbeitsrechtlichen Fragen wenden Sie sich an einen Fachanwalt für Arbeitsrecht.

---

*PraxisZeit – Zeiterfassungssystem für Arztpraxen und kleine Unternehmen*
*Stand: März 2026*
