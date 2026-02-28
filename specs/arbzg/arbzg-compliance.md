# ArbZG-Compliance – Vollständiger Abgleich für PraxisZeit

> Ist-Analyse des Arbeitszeitgesetzes (ArbZG) gegenüber dem aktuellen Implementierungsstand von PraxisZeit.
> Stand: **28.02.2026** | Gesetz: https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html

---

## Übersicht: Compliance-Status

| § | Thema | Status | Hinweis |
|---|-------|--------|---------|
| **§ 2** | Begriffsbestimmungen (Nachtarbeit) | ✅ Korrekt | `_is_night_work()` prüft minutengenau >2h Nachtzeit; `is_night_worker`-Flag auf User |
| **§ 3** | Tages-Höchstarbeitszeit (8h/10h + 48h/Woche) | ✅ Vollständig | 6-Monats-Ausgleichszeitraum nicht getrackt; Code-Kommentar „§14" irreführend (korrekt: §3) |
| **§ 4** | Pflichtpausen | ✅ Weitgehend | Mindestdauer vollständig; Pausen-Timing (6h-Kontinuität) systemisch nicht prüfbar |
| **§ 5** | Mindestruhezeit (11h) | ✅ Korrekt | Split-Schicht-Bug behoben (Commit `a488985`): Datumsgruppierung statt Paarvergleich |
| **§ 6** | Nacht- und Schichtarbeit | ⚠️ Teilweise | 8h-Limit ✅; §18-Bypass jetzt in allen Pfaden korrekt; Abs. 3/5 UI-Hinweise in Reports ✅; Abs. 4/6 außerhalb System |
| **§§ 9/10** | Sonn-/Feiertagsruhe | ✅ Vollständig | – |
| **§ 11** | Ausgleich Sonn-/Feiertagsarbeit | ✅ Vollständig | – |
| **§ 14** | Außergewöhnliche Fälle | ℹ️ Nicht anwendbar | Notfall-Ausnahme; 48h-Wochenwarnung kommt aus §3, nicht §14 |
| **§ 16** | Aufzeichnung & Aufbewahrung | ✅ Vollständig | PraxisZeit zeichnet ALLE Stunden auf (übertrifft §16-Mindestanforderung); gut positioniert für EuGH-Reform |
| **§ 18** | Ausnahmen leitende Angestellte | ✅ Vollständig | Bypass in allen 3 Pfaden korrekt (Commit `a488985`); `exempt_from_arbzg` jetzt in admin.py + change_requests.py geprüft |

---

## 1. § 2 – Begriffsbestimmungen (Referenz)

**Gesetzliche Definitionen (relevant für Implementierung):**
- **Nachtzeit** (§ 2 Abs. 3): 23:00–06:00 Uhr
- **Nachtarbeit** (§ 2 Abs. 4): jede Arbeit, die **mehr als zwei Stunden** der Nachtzeit umfasst
- **Nachtarbeitnehmer** (§ 2 Abs. 5): wer regelmäßig Nachtschicht leistet **oder** an mind. **48 Tagen/Jahr** Nachtarbeit leistet

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Nachtzeit-Fenster (23–6 Uhr) | ✅ | Korrekt in `_is_night_work()` in `time_entries.py` |
| Nachtarbeit-Schwellwert >2h (Abs. 4) | ✅ | `_is_night_work()` prüft minutengenau >120 min in Nachtzeit |
| Nachtarbeitnehmer-Definition (≥48 Tage) | ✅ | Admin-Report `/api/admin/reports/night-work-summary` verwendet korrekt ≥48-Tage-Schwellwert |
| `is_night_worker`-Flag auf User-Ebene | ✅ | Migration 017, Admin-UI Checkbox; löst strengere §6-Abs.-2-Warnung aus |

**Bewertung:** Vollständig konform. ✅

---

## 2. § 3 – Tägliche Höchstarbeitszeit und 48h-Wochengrenze

**Gesetzliche Regel:**
- Maximale werktägliche Arbeitszeit: **8 Stunden**
- Verlängerung auf **10 Stunden** zulässig, wenn innerhalb von **6 Kalendermonaten oder 24 Wochen** ein Ausgleich auf ≤ 8h/Tag Durchschnitt erfolgt
- Implizierte Wochengrenze: 6 Werktage × 8h/Tag = **48h/Woche** im Durchschnitt

> **Code-Kommentar behoben (Commit `a488985`):** `MAX_WEEKLY_HOURS_WARN = 48.0` in `time_entries.py` trägt nun den korrekten Kommentar `# §3 ArbZG: 6 Werktage × 8h Durchschnitt = 48h/Woche` statt des früheren irreführenden `# §14 ArbZG`.

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Warnung bei > 8h/Tag | ✅ | `DAILY_HOURS_WARNING` Flag + Frontend-Toast bei create / update / clock_out |
| Hard-Stop bei > 10h/Tag | ✅ | HTTP 422 bei Mitarbeiter-Pfad (create/update/clock_out) |
| §3-Check bei Admin-Direkteintrag | ✅ | `admin.py: admin_create_time_entry / admin_update_time_entry` – §3 nach §4-Prüfung |
| §3-Check bei Änderungsanträgen | ✅ | `change_requests.py` prüft §3 nach Genehmigung |
| Warnung bei > 48h/Woche | ✅ | `WEEKLY_HOURS_WARNING` + Frontend-Toast bei allen Eingabepfaden |
| §18-Ausnahme im Mitarbeiter-Pfad | ✅ | `exempt_from_arbzg` korrekt geprüft in `time_entries.py` |
| §18-Ausnahme im Admin-Pfad | ✅ | `exempt_from_arbzg` jetzt korrekt geprüft in `admin.py` (`admin_create/update_time_entry`) – Commit `a488985` |
| §18-Ausnahme im Änderungsantrags-Pfad | ✅ | `exempt_from_arbzg` jetzt korrekt geprüft in `change_requests.py` – Commit `a488985` |
| 6-Monats-Ausgleichszeitraum | ❌ | Kein gleitender Durchschnitt; manuelle Dokumentationsaufgabe des Arbeitgebers |

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

---

## 3. § 4 – Ruhepausen (Pflichtpausen)

**Gesetzliche Regel:**
- Arbeit > 6 Stunden → mind. **30 Minuten** Pause
- Arbeit > 9 Stunden → mind. **45 Minuten** Pause
- **Länger als 6 Stunden am Stück** dürfen Arbeitnehmer nicht ohne Ruhepause beschäftigt werden (§ 4 Satz 3)
- Pausen müssen **im voraus feststehen** (nicht nachträglich erfasst werden)
- Pausen können aufgeteilt werden (mind. 15 min je Einheit)

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Pausenfeld im Zeiteintrag | ✅ | `break_minutes` bei allen Zeiteinträgen erfasst und gespeichert |
| >6h → mind. 30min Pause | ✅ | `break_validation_service.validate_daily_break()` – aktiv bei allen 6 Eingabepfaden |
| >9h → mind. 45min Pause | ✅ | Wird vor der 6h-Prüfung geprüft |
| §18-Ausnahme (Mitarbeiter-Pfad) | ✅ | Pausenpflicht-Checks werden für leitende Angestellte übersprungen (MA-Pfad) |
| §18-Ausnahme (Admin-Pfad + Änderungsanträge) | ✅ | Jetzt korrekt geprüft in `admin.py` und `change_requests.py` – Commit `a488985` |
| Pausen-Timing (max. 6h am Stück, Satz 3) | ⚠️ | Start/Ende der Pause nicht erfasst → 6h-Kontinuitätsregel systemisch nicht prüfbar |
| „Im voraus feststehend" (Satz 1) | ⚠️ | System erfasst tatsächlich genommene Pausen; Vorherig-Feststellung ist Prozessfrage |

**Bewertung:** Mindestdauer vollständig konform. Timing systemisch nicht prüfbar – gilt für alle Zeiterfassungssysteme ohne Pausen-Timestamp.

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

---

## 4. § 5 – Mindestruhezeit zwischen Schichten

**Gesetzliche Regel:**
- Mind. **11 Stunden ununterbrochene Ruhezeit** nach dem Ende eines Arbeitstages
- **Ausnahme (Abs. 2):** Krankenhäuser, Pflegeeinrichtungen, Gastronomie etc. können auf bis zu 10h kürzen, wenn innerhalb eines Kalendermonats oder 4 Wochen ein Ausgleich auf ≥ 12h erfolgt
- **Abs. 3 (Bereitschaftsdienst):** In Krankenhäusern/Pflegeeinrichtungen kann Kürzung durch Bereitschaftsdienst ausgeglichen werden

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| 11h-Prüfung zwischen Schichten | ✅ | `rest_time_service.check_rest_time_violations()` vollständig |
| Admin-Report Ruhezeit-Verstöße | ✅ | `GET /api/admin/reports/rest-time-violations` mit Jahr, optionalem Monat, konfigurierbarem Schwellwert |
| Frontend-Anzeige | ✅ | Admin Reports-Seite zeigt betroffene Mitarbeiter, Datum und Stunden-Defizit |
| Split-Schicht-Erkennung | ✅ | **Behoben (Commit `a488985`):** `rest_time_service.py` gruppiert Einträge jetzt nach Datum; nur noch `max(end_time)` des Vortages vs. `min(start_time)` des Folgetages wird verglichen – keine False Positives bei Splitschichten mehr. |
| §5 Abs. 2 Ausgleich (Reduzierung auf 10h) | ❌ | Ausgleichs-Tracking nicht implementiert; 11h-Grenze ist fest kodiert |

**Behoben in Commit `a488985`:** `check_rest_time_violations()` gruppiert Einträge jetzt nach Datum und vergleicht nur noch den letzten Eintrag (max end_time) des Vortages mit dem ersten Eintrag (min start_time) des Folgetages. Split-Schichten werden korrekt behandelt.

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

---

## 5. § 6 – Nacht- und Schichtarbeit

**Gesetzliche Regel:**
- **Nachtzeit:** 23:00–06:00 Uhr (§ 2 Abs. 3)
- **Nachtarbeitnehmer:** mind. 48 Nächte/Jahr oder regelmäßige Nachtschicht (§ 2 Abs. 5)
- Max. **8 Stunden** für Nachtarbeitnehmer, verlängerbar auf 10h (Ausgleich innerhalb **1 Monat**, nicht 6 Monate wie §3) (Abs. 2)
- Anspruch auf **arbeitsmedizinische Untersuchung** (Abs. 3): vor Beschäftigungsbeginn, alle 3 Jahre (ab 50: jährlich)
- Recht auf **Wechsel zum Tagesarbeitsplatz** bei gesundheitlichen Gründen, Kind <12 Jahre oder pflegebedürftigen Angehörigen (Abs. 4)
- Anspruch auf **25% Lohnzuschlag oder gleichwertige Freizeit** bei Nachtarbeit (Abs. 5)
- **Gleicher Zugang zur Weiterbildung** wie Tagarbeitnehmer (Abs. 6)

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Erkennung Nachtarbeit (23–6 Uhr) | ✅ | `_is_night_work()` in `time_entries.py` |
| `is_night_work` Flag in API | ✅ | In allen `TimeEntryResponse`-Endpoints zurückgegeben |
| „Nacht"-Badge im Frontend | ✅ | Indigo-Badge in `TimeTracking.tsx` |
| Admin-Report: Nachtarbeit-Statistik | ✅ | `GET /api/admin/reports/night-work-summary` – Nachtschichten/MA, Nachtarbeitnehmer-Markierung (≥48 Tage/Jahr) |
| 8h-Warnung für Nachtarbeitnehmer (Abs. 2) – MA-Pfad | ✅ | `is_night_worker`-Flag auf User; Warnung bei >8h Nachtarbeit in create/update/clock_out |
| 8h-Warnung für Nachtarbeitnehmer (Abs. 2) – Admin-Pfad | ✅ | In admin_create/admin_update und change_request-Genehmigung |
| §18-Ausnahme (exempt_from_arbzg) im MA-Pfad | ✅ | Checks werden für leitende Angestellte übersprungen |
| §18-Ausnahme (exempt_from_arbzg) – alle Pfade | ✅ | Behoben in Commit `a488985`; `exempt_from_arbzg` jetzt in MA-Pfad, Admin-Pfad und Änderungsantrags-Pfad korrekt geprüft |
| Kürzerer 1-Monat-Ausgleichszeitraum für Nachtarbeitnehmer (Abs. 2) | ❌ | Warnung enthält Hinweis; automatisches Tracking nicht implementiert |
| Tracking arbeitsmedizinischer Untersuchungen (Abs. 3) | ⚠️ | HR-Verwaltungsaufgabe; UI-Hinweis in Reports-Seite ergänzt (Commit `a488985`): Pflichtuntersuchung vor Beginn, alle 3 Jahre, ab 50 jährlich |
| Recht auf Wechsel Tagesarbeitsplatz (Abs. 4) | ❌ | Arbeitgeber-Pflicht, nicht im System abbildbar; Dokumentation manuell |
| Lohnzuschlag / Freizeitausgleich (Abs. 5) | ⚠️ | Lohnbuchhaltungsaufgabe; UI-Hinweis in Reports-Seite ergänzt (Commit `a488985`): 25% Zuschlag oder bezahlte Freizeit |
| Gleicher Zugang zur Weiterbildung (Abs. 6) | ❌ | HR-/Organisationspflicht; nicht im System prüfbar |

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

> **Praxishinweis:** Abs. 4–6 sind Arbeitgeber-Pflichten, die kein Zeiterfassungssystem vollständig abbilden kann. Der §18-Bypass-Bug im Admin-Pfad wurde in Commit `a488985` behoben; `exempt_from_arbzg` wird nun in allen Pfaden korrekt ausgewertet. Für Abs. 3 und Abs. 5 wurden UI-Hinweise in der Admin-Reports-Seite ergänzt.

---

## 6. §§ 9/10 – Sonn- und Feiertagsruhe

**Gesetzliche Regel (§ 9):**
- Beschäftigungsverbot an Sonn- und Feiertagen **0–24 Uhr**

**Ausnahmen (§ 10):**
- Nr. 3: Krankenhäuser und Einrichtungen zur Behandlung/Pflege von Personen (→ Arztpraxen bei Notdienst)
- Dokumentationspflicht für die Ausnahme

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Sonntagserkennung | ✅ | `weekday() == 6` in `_enrich_response()` |
| Feiertagserkennung | ✅ | `is_holiday()` via `workalendar`-DB (alle Bundesländer, default Bayern) |
| `is_sunday_or_holiday` Flag in API | ✅ | In allen TimeEntry-Responses |
| `SUNDAY_WORK` / `HOLIDAY_WORK` Warnings | ✅ | In API-Response + Frontend-Toast |
| Visuelles Highlighting (orange) | ✅ | Tabellenzeilen + „So/FT"-Badge in `TimeTracking.tsx` |
| Ausnahmegrund-Feld (§ 10 ArbZG) | ✅ | Optionales Textfeld `sunday_exception_reason` erscheint im Formular bei Sonn-/Feiertagen |
| `sunday_exception_reason` in Exports | ✅ | Seit `6894f56` in allen 6 Export-Varianten (xlsx + ods) als Bemerkung |
| §18-Ausnahme (exempt_from_arbzg) | ✅ | Warnungen für leitende Angestellte unterdrückt |

**Status: Vollständig konform** ✅

---

## 7. § 11 – Ausgleich nach Sonn- und Feiertagsarbeit

**Gesetzliche Regel:**
- Mind. **15 beschäftigungsfreie Sonntage** pro Jahr pro Arbeitnehmer
- Ersatzruhetag nach **Sonntagsarbeit** innerhalb **2 Wochen** (einschließlich des Beschäftigungstages)
- Ersatzruhetag nach **Feiertagsarbeit** innerhalb **8 Wochen**
- Ersatzruhetag unmittelbar in Verbindung mit einer Ruhezeit nach §5 (Abs. 4)

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| 15-freie-Sonntage Compliance | ✅ | `GET /api/admin/reports/sunday-summary` mit Grün/Rot-Bewertung + Frontend-Tabelle |
| Ersatzruhetag-Tracking (2 Wochen, Sonntag) | ✅ | `GET /api/admin/reports/compensatory-rest` – prüft freien Tag innerhalb 14 Tage nach Sonntagsarbeit |
| Ersatzruhetag-Tracking (8 Wochen, Feiertag) | ✅ | Selber Endpoint – 56-Tage-Fenster für Feiertagsarbeit |
| Frontend-Report | ✅ | Sektion „Ersatzruhetage §11 ArbZG" in Admin-Reports mit Verstoß-Tabelle |

**Status: Vollständig konform** ✅

---

## 8. § 14 – Außergewöhnliche Fälle

**Gesetzliche Regel:**
- §14 erlaubt **Abweichungen** von §§3–5, 6 Abs. 2, §§7, 9–11 in **Notfällen und außergewöhnlichen Situationen**, die unabhängig vom Willen der Betroffenen eintreten (z.B. drohender Verderb von Rohstoffen, Katastrophen)
- §14 Abs. 3: Auch bei Ausnahmefällen gilt eine Obergrenze von **48h/Woche im 6-Monats-Durchschnitt**

> **Wichtige Klarstellung:** §14 ist eine **Notfall-Ausnahmeregel**, kein Regelfall. Die 48h-Wochenwarnung (`WEEKLY_HOURS_WARNING`) in PraxisZeit implementiert die Schutzintention aus **§3** (Tagesdurchschnitt ≤ 8h × 6 Werktage = 48h/Woche). Der Code-Kommentar `# §14 ArbZG` im `time_entries.py` ist irreführend – die korrekte Referenz ist §3 (+ §7 Abs. 8 für Tarifvertragsfälle).

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Notfall-Ausnahmen nach §14 | ℹ️ Nicht anwendbar | §14-Ausnahmen erfordern außergewöhnliche Notfälle; Zeiterfassungssystem nicht betroffen |
| 48h/Woche-Warnung (aus §3) | ✅ | `WEEKLY_HOURS_WARNING` – korrekt implementiert |

---

## 9. § 16 – Aufzeichnungs- und Aufbewahrungspflicht

**Gesetzliche Regel:**
- Arbeitgeber muss Arbeitszeiten, die **8 Stunden werktäglich überschreiten**, aufzeichnen (Abs. 2)
- Aufzeichnungen mind. **2 Jahre** aufbewahren (Abs. 2)
- Liste der Arbeitnehmer führen, die nach §7 Abs. 7 in Überstunden eingewilligt haben (Abs. 2)
- **Gesetzesaushang** (Kopie des ArbZG) am Arbeitsplatz oder über betriebliche IT zugänglich (Abs. 1)

> **EuGH & BAG Kontext:** EuGH C-55/18 (Mai 2019) und BAG 1 ABR 22/21 (September 2022) etablieren eine weitergehende Pflicht zur Aufzeichnung **aller** Arbeitszeiten (nicht nur >8h). Deutschland bereitet eine entsprechende ArbZG-Reform vor (Stand: Aug. 2025 als Referentenentwurf). PraxisZeit zeichnet bereits **alle** Stunden lückenlos auf – übertrifft damit die aktuelle §16-Mindestanforderung und ist optimal für die Reform positioniert.

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Vollständige Zeiterfassung in DB | ✅ | Start, Ende, Pausen, Datum, Mitarbeiter, Ausnahmegrund (`sunday_exception_reason`) |
| Aufzeichnung >8h/Tag (§16 Abs. 2) | ✅ | System erfasst alle Stunden – übertrifft gesetzliche Mindestanforderung |
| 2-Jahres-Aufbewahrung dokumentiert | ✅ | `INSTALLATION.md`: Backup-Anleitung + Retention-Prozess |
| §16-Hinweis im Admin-Frontend | ✅ | Reports-Seite unter „Hinweise" mit 2-Jahres-Verweis |
| Excel-Export als Nachweis (xlsx) | ✅ | 3 Monats-/Jahres-Exportvarianten verfügbar |
| ODS-Export als Nachweis (ods) | ✅ | 3 ODS-Exportvarianten seit Commit `a503e4f` |
| ArbZG-Flags in Exports | ✅ | `sunday_exception_reason`, Nachtarbeit, `is_night_worker`, `exempt_from_arbzg` seit `6894f56` |
| Gesetzesaushang / Link zum ArbZG | ✅ | Link zu gesetze-im-internet.de/arbzg in Admin-Reports unter „Hinweise" |
| §7 Abs. 7 Opt-in-Register | ❌ | Nicht implementiert; bei Praxen ohne Tarifvertrag i.d.R. nicht relevant |

**Status: Vollständig konform** ✅ (übertrifft §16-Mindestanforderung)

---

## 10. § 18 – Ausnahmen für leitende Angestellte (Nichtanwendung)

**Gesetzliche Regel:**
- **§18 Abs. 1 Nr. 1:** Leitende Angestellte i.S. § 5 Abs. 3 BetrVG sowie **Chefärzte** sind vollständig vom ArbZG ausgenommen
- **§18 Abs. 1 Nr. 2:** Leiter von öffentlichen Behörden (für Arztpraxen nicht relevant)
- **§18 Abs. 1 Nr. 3:** Arbeitnehmer in häuslicher Gemeinschaft mit betreuten Personen (Pflegepersonen im Haushalt – selten in Praxen)
- Praxisinhaber fallen als „leitende Angestellte" unter Nr. 1

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Ausnahme-Flag auf Benutzerebene | ✅ | `User.exempt_from_arbzg` (Boolean) – DB-Spalte in Migration 016 |
| Admin-UI zur Verwaltung | ✅ | Checkbox „ArbZG-Prüfungen aussetzen (§18 ArbZG)" in Benutzerverwaltung |
| §3/§4 Bypass im MA-Selbstservice-Pfad | ✅ | Alle Checks und Warnungen in `time_entries.py` korrekt übersprungen |
| §3/§4 Bypass im Admin-Direkteintrag-Pfad | ✅ | **Behoben (Commit `a488985`):** `admin.py` prüft `exempt_from_arbzg` vor §3/§4-Checks in `admin_create_time_entry` und `admin_update_time_entry` |
| §3/§4 Bypass im Änderungsantrags-Pfad | ✅ | **Behoben (Commit `a488985`):** `change_requests.py` prüft `exempt_from_arbzg` in `create_change_request` vor §4-Break-Check, §3-Hard-Stop und §6-Nachtarbeiter-Warnung |

**Status: Vollständig konform** ✅ – alle drei Pfade (MA-Selbstservice, Admin-Direkteintrag, Änderungsantrag) berücksichtigen `exempt_from_arbzg` korrekt.

---

## 11. Weitere Paragrafen

| § | Thema | Relevanz für Arztpraxis | Status |
|---|-------|------------------------|--------|
| **§ 7** | Tarifvertragliche Abweichungen | Wenn Tarifvertrag gilt → andere Grenzwerte möglich (z.B. >10h/Tag, >11h Ruhezeit) | ⚠️ Nicht berücksichtigt – feste 8h/10h/48h-Werte |
| **§ 8** | Bundesverordnung für gefährliche Arbeiten | Nur für Sonderverordnungen | Nicht anwendbar |
| **§ 12** | Sonn-/Feiertagsausnahmen per Tarifvertrag | Wenn TV gilt: mind. Freisonntage abweichend möglich | Nicht berücksichtigt |
| **§ 13** | Bereichsausnahmen (Notfallverordnungen) | Bundesregierungs-Ermächtigung für Krisenzeiten | Nicht anwendbar |
| **§ 22** | Bußgeldvorschriften | Bis 30.000 € pro Verstoß | Sanktionsrahmen unverändert |
| **§ 23** | Strafvorschriften | Freiheitsstrafe bei vorsätzlicher Gesundheitsgefährdung | – |

---

## 12. Straf- und Bußgeldrahmen

| Verstoß | § | Sanktion |
|---------|---|----------|
| Überschreitung der Tages-Höchstarbeitszeit | § 3 | Bußgeld bis **30.000 €** |
| Fehlende oder unzureichende Ruhepause | § 4 | Bußgeld bis **30.000 €** |
| Verletzung der 11h-Mindestruhezeit | § 5 | Bußgeld bis **30.000 €** |
| Verstoß gegen Nachtarbeitsgrenzen | § 6 | Bußgeld bis **30.000 €** |
| Unzulässige Sonn-/Feiertagsbeschäftigung | § 9 | Bußgeld bis **30.000 €** |
| Fehlende Aufzeichnung von Überstunden | § 16 | Bußgeld bis **30.000 €** |
| Fehler beim Gesetzesaushang | § 16 | Bußgeld bis **5.000 €** |
| Vorsätzliche Gesundheitsgefährdung | § 23 | Freiheitsstrafe bis **1 Jahr** oder Geldstrafe |

---

## 13. Verbleibende Lücken und bekannte Bugs (Gesamtüberblick)

| Anforderung | § | Typ | Priorität | Begründung |
|-------------|---|-----|-----------|------------|
| ~~Split-Schicht False Positives~~ | ~~§5~~ | ~~Bug~~ | ~~Mittel~~ | **✅ Behoben** in Commit `a488985` |
| ~~§18-Bypass fehlt in admin.py/change_requests.py~~ | ~~§3/§4/§18~~ | ~~Bug~~ | ~~Mittel~~ | **✅ Behoben** in Commit `a488985` |
| ~~Code-Kommentar §14 statt §3~~ | ~~§3~~ | ~~Code~~ | ~~Niedrig~~ | **✅ Behoben** in Commit `a488985` |
| 6-Monats-Ausgleichszeitraum | §3 | Lücke | Niedrig | Rollierender Durchschnitt technisch komplex; Warnung bereits bei >8h/Tag aktiv |
| Pausen-Timing (max. 6h am Stück) | §4 Satz 3 | Systemlücke | Niedrig | Kein Pause-Timestamp; für geregelte Praxiszeiten kein Risiko |
| Kürzerer 1-Monat-Ausgleich für Nachtarbeitnehmer | §6 Abs. 2 | Lücke | Niedrig | Warnung mit Hinweis integriert; automatisches Tracking fehlt |
| Arbeitsmedizinische Untersuchungen | §6 Abs. 3 | HR-Aufgabe | Niedrig | UI-Hinweis in Reports-Seite ergänzt; Dokumentation in Personalakte bleibt Arbeitgeberpflicht |
| Recht auf Tagesarbeitsplatz | §6 Abs. 4 | Systemaußen | Niedrig | Arbeitgeber-Pflicht bei Nachweis; nicht systemisch abbildbar |
| Lohnzuschlag / Freizeitausgleich Nachtarbeit | §6 Abs. 5 | Lohnbuchhaltung | Niedrig | UI-Hinweis in Reports-Seite ergänzt; Abwicklung in Lohnbuchhaltung |
| Tarifvertragliche Abweichungen | §7 | Lücke | Niedrig | PraxisZeit verwendet feste gesetzliche Grenzwerte |
| §7 Abs. 7 Opt-in-Register | §16 Abs. 2 | Lücke | Niedrig | Nur relevant bei TV mit §7 Abs. 7-Vereinbarungen |

---

## 14. Handlungsempfehlungen (nach Priorität)

### ✅ Erledigt (Commit `a488985`, 28.02.2026)
1. **§5 Split-Schicht-Bug behoben** – `rest_time_service.py` verwendet jetzt Datumsgruppierung
2. **§18-Bypass vervollständigt** – `admin.py` und `change_requests.py` prüfen `exempt_from_arbzg` korrekt
3. **Code-Kommentar korrigiert** – `# §14 ArbZG` → `# §3 ArbZG` in `time_entries.py`
4. **§6 Abs. 3/5 UI-Hinweise** – Informations-Boxen in Admin-Reports-Seite ergänzt

### Niedrig – Verbleibende Dokumentationspflichten
5. **§6 Abs. 3** Arbeitsmedizinische Untersuchungen in Personalakte dokumentieren (UI-Hinweis vorhanden)
6. **§6 Abs. 5** Lohnzuschlag/Freizeitausgleich in Lohnbuchhaltung sicherstellen (UI-Hinweis vorhanden)

### Beobachtung – Externe Entwicklung
7. **EuGH/BAG Stechuhr-Reform**: Deutsche ArbZG-Novelle (erwartet ab 2025/2026) wird Pflicht zur Aufzeichnung aller Stunden kodifizieren. PraxisZeit ist bereits konform.

---

> **Rechtlicher Hinweis:** Diese Analyse ersetzt keine Rechtsberatung. Arbeitgeber sind selbst
> verantwortlich für die Einhaltung des ArbZG. Bei Fragen zur Anwendung einzelner Vorschriften
> sollte ein Fachanwalt für Arbeitsrecht hinzugezogen werden.
