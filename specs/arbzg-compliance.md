# ArbZG-Compliance – Kritische Paragrafen für PraxisZeit

> Analyse des Arbeitszeitgesetzes (ArbZG) bezogen auf die Nutzung des Zeiterfassungssystems PraxisZeit.
> Stand: Februar 2026 | Gesetzesquelle: https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html

---

## 1. Hochkritische Paragrafen

### § 3 ArbZG – Tägliche Höchstarbeitszeit

**Gesetzliche Regel:**
- Maximale Arbeitszeit: **8 Stunden pro Tag**
- Verlängerung auf **10 Stunden** zulässig, wenn innerhalb von 6 Monaten oder 24 Wochen ein Ausgleich auf ≤ 8h im Durchschnitt erfolgt

**Relevanz für PraxisZeit:**
- Das System erfasst Arbeitszeiten, prüft aber **nicht automatisch**, ob die 8h/10h-Grenze überschritten wird
- Einträge von 11–12h werden ohne Warnsignal gespeichert
- Arbeitgeber haften für Verstöße – fehlende Systemunterstützung erhöht das Risiko
- **Empfehlung:** Warnhinweis bei Einträgen > 8h und Sperre/zweite Bestätigung bei > 10h implementieren

---

### § 4 ArbZG – Ruhepausen (Pflichtpausen)

**Gesetzliche Regel:**
- Arbeit > 6 Stunden → mind. **30 Minuten Pause** Pflicht
- Arbeit > 9 Stunden → mind. **45 Minuten Pause** Pflicht
- Maximale Arbeitszeit ohne jede Pause: **6 Stunden**

**Relevanz für PraxisZeit:**
- Das System kennt **keine Pausenerfassung** – Pausen sind keine eigene Eintragsart
- Bruttoarbeitszeit ≠ Nettoarbeitszeit → fehlerhafte Auswertungen und Exports
- Fehlende Pausen sind eine Ordnungswidrigkeit nach § 22 (bis **30.000 €** Bußgeld)
- **Empfehlung:** Pausenfeld bei Zeiteinträgen ergänzen; Pflichtvalidierung ab 6h Arbeitszeit

---

### § 5 ArbZG – Mindestruhezeit zwischen Schichten

**Gesetzliche Regel:**
- Mind. **11 Stunden ununterbrochene Ruhezeit** zwischen zwei Arbeitstagen

**Relevanz für PraxisZeit:**
- Beispiel: Arbeit bis 23:00 Uhr, Beginn nächsten Tag 07:00 Uhr = nur 8h Ruhe → **illegal**
- Das System prüft **keine Ruhezeiten** zwischen Einträgen verschiedener Tage
- Bei Schichtbetrieb in Arztpraxen (Notdienst, verlängerte Sprechzeiten) besonders kritisch
- **Empfehlung:** Warnung wenn letzte Buchung + 11h > nächste Buchungszeit

---

### § 9 ArbZG – Sonntagsruhe

**Gesetzliche Regel:**
- An Sonn- und gesetzlichen Feiertagen **Beschäftigungsverbot von 0–24 Uhr** (Grundsatz)
- Ausnahmen nach § 10 für Gesundheitsberufe und Notfalldienste möglich

**Relevanz für PraxisZeit:**
- Feiertagskalender ist vorhanden, aber Zeiteinträge an Sonn-/Feiertagen werden **nicht markiert oder geblockt**
- Arztpraxen können unter § 10 fallen – müssen aber dokumentieren **warum** Sonntagsarbeit stattfindet
- Fehlende Dokumentation ist bußgeldbewehrt
- **Empfehlung:** Kennzeichnung von Sonn-/Feiertagseinträgen mit optionalem Pflichtfeld „Ausnahmegrund"

---

### § 11 ArbZG – Ausgleich für Sonn- und Feiertagsarbeit

**Gesetzliche Regel:**
- Mindestens **15 beschäftigungsfreie Sonntage** pro Jahr pro Arbeitnehmer
- Ersatzruhetag nach Sonntagsarbeit: innerhalb **2 Wochen**
- Ersatzruhetag nach Feiertagsarbeit: innerhalb **8 Wochen**

**Relevanz für PraxisZeit:**
- Das System kann Sonntags-Einträge über den Excel-Export auswerten, zählt aber **nicht automatisch freie Sonntage**
- Kein automatischer Alarm, wenn ein Mitarbeiter die 15-Sonntage-Grenze erreicht
- **Empfehlung:** Reporting-Funktion: Anzahl gearbeiteter Sonntage pro Mitarbeiter pro Jahr

---

### § 16 ArbZG – Aufzeichnungs- und Aufbewahrungspflicht

**Gesetzliche Regel:**
- Arbeitgeber muss **Mehrarbeitszeiten** (über 8h werktäglich) aufzeichnen
- Aufzeichnungen müssen **mindestens 2 Jahre** aufbewahrt werden
- Arbeitgeber muss eine Kopie des ArbZG auslegen oder aushängen

**Relevanz für PraxisZeit:**
- System erfüllt Aufzeichnungspflicht grundsätzlich durch Zeiteinträge in der Datenbank
- **Unklar:** Gibt es ein Datenlöschkonzept? Einträge müssen 2 Jahre abrufbar bleiben
- Excel-Export reicht als Nachweis – wenn regelmäßig archiviert und unveränderlich gespeichert
- **Empfehlung:** Hinweis in der Dokumentation; Exportarchivierung als Prozess definieren

---

## 2. Mittlere Relevanz

| § | Thema | Details | Risiko |
|---|-------|---------|--------|
| **§ 6** | Nachtarbeit (23–6 Uhr) | Max. 8h/Nacht (verlängerbar auf 10h), Recht auf arbeitsmedizinische Untersuchung | System markiert keine Nacht-Einträge |
| **§ 7** | Tarifvertragliche Ausnahmen | Abweichende Arbeitszeiten, Ausgleichszeiträume per Tarifvertrag möglich | Wenn Tarifvertrag gilt → andere Grenzwerte konfigurieren |
| **§ 14** | Außergewöhnliche Fälle | Max. 48h/Woche im 6-Monats-Schnitt bei Notfällen | System erfasst Stunden, prüft Wochensumme nicht |

---

## 3. Straf- und Bußgeldvorschriften (§§ 22, 23)

| Verstoß | Sanktion |
|---------|----------|
| Überschreitung der zulässigen Arbeitszeit (§ 3) | Bußgeld bis **30.000 €** |
| Fehlende Ruhepausen (§ 4) | Bußgeld bis **30.000 €** |
| Verletzung der Ruhezeit (§ 5) | Bußgeld bis **30.000 €** |
| Unzulässige Sonn-/Feiertagsarbeit (§ 9) | Bußgeld bis **30.000 €** |
| Fehlende Aufzeichnung von Mehrarbeitszeiten (§ 16) | Bußgeld bis **30.000 €** |
| Fehlender Gesetzesaushang (§ 16) | Bußgeld bis **5.000 €** |
| Vorsätzliche Gesundheitsgefährdung (§ 23) | Freiheitsstrafe bis **1 Jahr** oder Geldstrafe |
| Fahrlässige Gesundheitsgefährdung (§ 23) | Freiheitsstrafe bis **6 Monate** oder Geldstrafe |

---

## 4. Zusammenfassung: Compliance-Lücken in PraxisZeit

| Gesetzliche Anforderung | § | Priorität | Status im System |
|------------------------|---|-----------|-----------------|
| Tagesarbeitszeit-Warnung bei > 8h / > 10h | § 3 | 🔴 Hoch | Nicht implementiert |
| Pausenerfassung bei > 6h Arbeit | § 4 | 🔴 Hoch | Pausenfeld fehlt komplett |
| 11h Mindestruhezeit zwischen Schichten | § 5 | 🔴 Hoch | Keine Prüfung |
| Sonn-/Feiertagskennzeichnung mit Ausnahmegrund | § 9/10 | 🟡 Mittel | Feiertagskalender vorhanden, keine Markierung |
| Zähler freier Sonntage (min. 15/Jahr) | § 11 | 🟡 Mittel | Kein automatischer Zähler |
| 2-jährige Aufbewahrungspflicht | § 16 | 🟡 Mittel | Depends on DB-Retention |
| Nachtarbeitskennzeichnung (23–6 Uhr) | § 6 | 🟢 Niedrig | Nicht implementiert |
| Wochenarbeitszeit-Tracking (48h-Grenze) | § 14 | 🟢 Niedrig | Nicht implementiert |

---

## 5. Empfohlene Maßnahmen (priorisiert)

1. **[Prio 1]** Pausenerfassung als Pflichtfeld bei Zeiteinträgen > 6h einführen (§ 4)
2. **[Prio 1]** Warnung/Bestätigungsdialog bei Tagesarbeitszeit > 8h und Ablehnung > 10h (§ 3)
3. **[Prio 1]** Ruhezeit-Prüfung: Warnung wenn < 11h zwischen zwei Buchungen (§ 5)
4. **[Prio 2]** Sonn-/Feiertagseinträge visuell markieren + optionaler Ausnahmegrund-Text (§ 9/10)
5. **[Prio 2]** Report: Gearbeitete Sonntage pro Mitarbeiter/Jahr für § 11-Compliance
6. **[Prio 2]** Datenbankretention-Richtlinie dokumentieren (min. 2 Jahre, § 16)
7. **[Prio 3]** Nachtarbeit-Kennzeichnung (Einträge, die Nachtzeit 23–6 Uhr schneiden)

---

> **Rechtlicher Hinweis:** Diese Analyse ersetzt keine Rechtsberatung. Arbeitgeber sind selbst
> verantwortlich für die Einhaltung des ArbZG. Bei Fragen zur Anwendung einzelner Vorschriften
> sollte ein Fachanwalt für Arbeitsrecht hinzugezogen werden.
