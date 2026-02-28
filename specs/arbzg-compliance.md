# ArbZG-Compliance – Vollständiger Abgleich für PraxisZeit

> Ist-Analyse des Arbeitszeitgesetzes (ArbZG) gegenüber dem aktuellen Implementierungsstand von PraxisZeit.
> Stand: **28.02.2026** | Gesetz: https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html

---

## Übersicht: Compliance-Status

| § | Thema | Status | Hinweis |
|---|-------|--------|---------|
| **§ 2** | Begriffsbestimmungen (Nachtarbeit) | ✅ Korrekt | `_is_night_work()` prüft minutengenau >2h Nachtzeit (§2 Abs. 4); `is_night_worker`-Flag auf User |
| **§ 3** | Tages-Höchstarbeitszeit (8h/10h + 48h/Woche) | ✅ Vollständig | 6-Monats-Ausgleichszeitraum nicht getrackt |
| **§ 4** | Pflichtpausen | ✅ Weitgehend | Pausen-Timing (6h-Kontinuität) nicht prüfbar |
| **§ 5** | Mindestruhezeit (11h) | ✅ Vollständig | – |
| **§ 6** | Nacht- und Schichtarbeit | ⚠️ Teilweise | 3 Lücken (Untersuchung, Transferrecht, Zuschlag) – 8h-Limit jetzt ✅ |
| **§§ 9/10** | Sonn-/Feiertagsruhe | ✅ Vollständig | – |
| **§ 11** | Ausgleich Sonn-/Feiertagsarbeit | ✅ Vollständig | – |
| **§ 14** | Außergewöhnliche Fälle | ℹ️ Nicht anwendbar | Notfall-Ausnahme, kein Regelfall; 48h/Woche aus §3 |
| **§ 16** | Aufzeichnung & Aufbewahrung | ✅ Vollständig | – |
| **§ 18** | Ausnahmen leitende Angestellte | ✅ Vollständig | – |

---

## 1. § 2 – Begriffsbestimmungen (Referenz)

**Gesetzliche Definitionen (relevant für Implementierung):**
- **Nachtzeit** (§ 2 Abs. 3): 23:00–06:00 Uhr
- **Nachtarbeit** (§ 2 Abs. 4): jede Arbeit, die **mehr als zwei Stunden** der Nachtzeit umfasst
- **Nachtarbeitnehmer** (§ 2 Abs. 5): wer regelmäßig Nachtschicht leistet **oder** an mind. **48 Tagen/Jahr** Nachtarbeit leistet

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Nachtzeit-Fenster (23–6 Uhr) | ✅ | Korrekt in `_is_night_work()` und `_is_night_work()` in `time_entries.py` |
| Nachtarbeit-Schwellwert >2h | ✅ | `_is_night_work()` prüft minutengenau ob >2h (120 min) in Nachtzeit (23:00–06:00) fallen (§2 Abs. 4 ArbZG) |
| Nachtarbeitnehmer-Definition (≥48 Tage) | ✅ | Admin-Report `/api/admin/reports/night-work-summary` verwendet korrekt ≥48-Tage-Schwellwert |

**Bewertung:** Konservative Implementierung (mehr Warnungen als gesetzlich nötig), kein Compliance-Risiko.

---

## 2. § 3 – Tägliche Höchstarbeitszeit und 48h-Wochengrenze

**Gesetzliche Regel:**
- Maximale werktägliche Arbeitszeit: **8 Stunden**
- Verlängerung auf **10 Stunden** zulässig, wenn innerhalb von **6 Kalendermonaten oder 24 Wochen** ein Ausgleich auf ≤ 8h/Tag Durchschnitt erfolgt
- Implizierte Wochengrenze: 6 Werktage × 8h/Tag = **48h/Woche** im Durchschnitt

> **Hinweis §14:** Die 48h-Wochengrenze ist primär eine Ableitung aus §3 (Tagesdurchschnitt × 6 Werktage). §14 Abs. 3 wiederholt diese Grenze nur für Ausnahmefälle. Der `WEEKLY_HOURS_WARNING`-Check bei 48h implementiert die §3-Schutzintention.

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Warnung bei > 8h/Tag | ✅ | `DAILY_HOURS_WARNING` Flag + Frontend-Toast bei create / update / clock_out |
| Hard-Stop bei > 10h/Tag | ✅ | HTTP 422 bei allen Eingabepfaden (Mitarbeiter, Admin, Änderungsanträge) |
| §3-Check bei Admin-Direkteintrag | ✅ | `admin.py: admin_create_time_entry / admin_update_time_entry` – §3 nach §4-Prüfung |
| §3-Check bei Änderungsanträgen | ✅ | `change_requests.py` prüft §3 nach Genehmigung |
| Warnung bei > 48h/Woche | ✅ | `WEEKLY_HOURS_WARNING` + Frontend-Toast bei allen Eingabepfaden |
| §18-Ausnahme (exempt_from_arbzg) | ✅ | Alle Checks werden für leitende Angestellte übersprungen |
| 6-Monats-Ausgleichszeitraum | ❌ | Kein gleitender Durchschnitt; manuelle Dokumentationsaufgabe |

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

---

## 3. § 4 – Ruhepausen (Pflichtpausen)

**Gesetzliche Regel:**
- Arbeit > 6 Stunden → mind. **30 Minuten** Pause
- Arbeit > 9 Stunden → mind. **45 Minuten** Pause
- **Länger als 6 Stunden am Stück** dürfen Arbeitnehmer nicht ohne Ruhepause beschäftigt werden (§ 4 Satz 3)
- Pausen können aufgeteilt werden (mind. 15 min je Einheit)

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Pausenfeld im Zeiteintrag | ✅ | `break_minutes` bei allen Zeiteinträgen erfasst und gespeichert |
| >6h → mind. 30min Pause | ✅ | `break_validation_service.validate_daily_break()` – aktiv bei create / update / clock_out / admin / change_requests |
| >9h → mind. 45min Pause | ✅ | `break_validation_service.py` prüft 9h/45min vor 6h/30min |
| §18-Ausnahme (exempt_from_arbzg) | ✅ | Pausenpflicht-Checks werden für leitende Angestellte übersprungen |
| Pausen-Timing (max. 6h am Stück) | ⚠️ | Das System prüft die **Gesamtdauer** der Pause, nicht **wann** sie genommen wurde. Die 6h-Kontinuitätsregel (§ 4 Satz 3) ist nicht prüfbar, da Start/Ende der Pause nicht erfasst werden. |

**Bewertung:** Die kritische Mindestdauer ist vollständig konform. Das Pausen-Timing ist systemisch nicht prüfbar (kein Timestamp für Pausenbeginn/-ende), stellt aber für Arztpraxen mit geregelten Pausenzeiten kein praktisches Risiko dar.

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

---

## 4. § 5 – Mindestruhezeit zwischen Schichten

**Gesetzliche Regel:**
- Mind. **11 Stunden ununterbrochene Ruhezeit** nach dem Ende eines Arbeitstages
- Ausnahmen in bestimmten Bereichen (z.B. Krankenhäuser, Pflegeeinrichtungen) mit Ausgleich innerhalb 4 Wochen

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| 11h-Prüfung zwischen Schichten | ✅ | `rest_time_service.check_rest_time_violations()` vollständig |
| Admin-Report Ruhezeit-Verstöße | ✅ | `GET /api/admin/reports/rest-time-violations` mit Jahr, optionalem Monat, konfigurierbarem Schwellwert |
| Frontend-Anzeige | ✅ | Admin Reports-Seite zeigt betroffene Mitarbeiter, Datum und Stunden-Defizit |

**Status: Vollständig konform** ✅

---

## 5. § 6 – Nacht- und Schichtarbeit

**Gesetzliche Regel:**
- **Nachtzeit:** 23:00–06:00 Uhr (§ 2 Abs. 3)
- **Nachtarbeitnehmer:** mind. 48 Nächte/Jahr oder regelmäßige Nachtschicht (§ 2 Abs. 5)
- Max. **8 Stunden** für Nachtarbeitnehmer, verlängerbar auf 10h (Ausgleich innerhalb **1 Monat**, nicht 6 Monate wie bei §3) (Abs. 2)
- Anspruch auf **arbeitsmedizinische Untersuchung** (Abs. 3): vor Beschäftigungsbeginn, danach alle 3 Jahre (ab 50: jährlich)
- Recht auf **Wechsel zum Tagesarbeitsplatz** bei gesundheitlichen Gründen, Kind <12 Jahre oder pflegebedürftige Angehörige (Abs. 4)
- Anspruch auf **25% Lohnzuschlag oder gleichwertige Freizeit** bei Nachtarbeit (Abs. 5)
- **Gleicher Zugang zur Weiterbildung** wie Tagarbeitnehmer (Abs. 6)

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Erkennung Nachtarbeit (23–6 Uhr) | ✅ | `_is_night_work()` in `time_entries.py` |
| `is_night_work` Flag in API | ✅ | In allen `TimeEntryResponse`-Endpoints zurückgegeben |
| „Nacht"-Badge im Frontend | ✅ | Indigo-Badge in `TimeTracking.tsx` |
| Admin-Report: Nachtarbeit-Statistik | ✅ | `GET /api/admin/reports/night-work-summary` – Nachtschichten/MA, Nachtarbeitnehmer-Markierung (≥48 Tage/Jahr), Monatsaufschlüsselung |
| Strengere 8h-Grenze für Nachtarbeitnehmer (Abs. 2) | ✅ | `is_night_worker`-Flag auf User; Warnung bei >8h Nachtarbeit in allen 6 Validierungspfaden |
| Kürzerer 1-Monats-Ausgleichszeitraum für Nachtarbeitnehmer (Abs. 2) | ❌ | Nicht implementiert (§3 verwendet 6-Monats-Fenster; Nachtarbeitnehmer haben strengeren 1-Monat) |
| Tracking arbeitsmedizinischer Untersuchungen (Abs. 3) | ❌ | HR-Verwaltungsaufgabe – sinnvoller in separatem HR-System |
| Recht auf Wechsel Tagesarbeitsplatz (Abs. 4) | ❌ | Arbeitgeber-Pflicht, nicht im System abbildbar; Dokumentation manuell |
| Lohnzuschlag / Freizeitausgleich (Abs. 5) | ❌ | Lohnbuchhaltungsaufgabe – liegt außerhalb des Zeiterfassungssystems |
| Gleicher Zugang zur Weiterbildung (Abs. 6) | ❌ | HR-/Organisationspflicht; nicht im System prüfbar |

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

> **Praxishinweis:** Abs. 4–6 sind Arbeitgeber-Pflichten, die in keinem Zeiterfassungssystem vollständig abgebildet werden können. Der fehlende 8h-Grenzwert für Nachtarbeitnehmer (Abs. 2) ist für eine Arztpraxis mit seltener Nachtarbeit wenig relevant, sollte aber für Praxen mit regelmäßigem Nachtdienst beachtet werden.

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

> **Wichtige Klarstellung:** §14 ist eine **Notfall-Ausnahmeregel**, kein Regelfall. Die 48h-Wochenwarnung (`WEEKLY_HOURS_WARNING`) in PraxisZeit implementiert die Schutzintention aus **§3** (Tagesdurchschnitt ≤ 8h × 6 Werktage = 48h/Woche). Der Verweis auf "§14" in älteren Dokumenten war irreführend.

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Notfall-Ausnahmen nach §14 | ℹ️ Nicht anwendbar | §14-Ausnahmen erfordern behördliche Bewilligung; Zeiterfassungssystem nicht betroffen |
| 48h/Woche-Warnung (aus §3) | ✅ | `WEEKLY_HOURS_WARNING` – korrekt implementiert, auch wenn als „§14" bezeichnet |

---

## 9. § 16 – Aufzeichnungs- und Aufbewahrungspflicht

**Gesetzliche Regel:**
- Arbeitgeber muss Arbeitszeiten, die **8 Stunden werktäglich überschreiten**, aufzeichnen
- Aufzeichnungen mind. **2 Jahre** aufbewahren
- **Gesetzesaushang** (Kopie des ArbZG) am Arbeitsplatz oder über betriebliche IT zugänglich

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Vollständige Zeiterfassung in DB | ✅ | Start, Ende, Pausen, Datum, Mitarbeiter, Ausnahmegrund (`sunday_exception_reason`) |
| 2-Jahres-Aufbewahrung dokumentiert | ✅ | `INSTALLATION.md`: Backup-Anleitung + Retention-Prozess; Kommentar in `docker-compose.yml` |
| §16-Hinweis im Admin-Frontend | ✅ | Reports-Seite unter „Hinweise" mit 2-Jahres-Verweis |
| Excel-Export als Nachweis | ✅ | Monats- und Jahresexporte verfügbar |
| Gesetzesaushang / Link zum ArbZG | ✅ | Link zu gesetze-im-internet.de/arbzg in Admin-Reports unter „Hinweise" |

**Status: Vollständig konform** ✅

---

## 10. § 18 – Ausnahmen für leitende Angestellte (Nichtanwendung)

**Gesetzliche Regel:**
- Leitende Angestellte i.S. § 5 Abs. 3 BetrVG sowie **Chefärzte** sind vollständig vom ArbZG ausgenommen
- Praxisinhaber fallen ebenfalls unter §18

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Ausnahme-Flag auf Benutzerebene | ✅ | `User.exempt_from_arbzg` (Boolean) – DB-Spalte in Migration 016 |
| Admin-UI zur Verwaltung | ✅ | Checkbox „ArbZG-Prüfungen aussetzen (§18 ArbZG)" in Benutzerverwaltung |
| Vollständiger Bypass aller Checks | ✅ | §3/§4/§14-Checks und alle Warnungen (DAILY/WEEKLY/SUNDAY/HOLIDAY) übersprungen |

**Status: Vollständig konform** ✅

---

## 11. Weitere Paragrafen

| § | Thema | Relevanz für Arztpraxis | Status |
|---|-------|------------------------|--------|
| **§ 7** | Tarifvertragliche Abweichungen | Wenn Tarifvertrag gilt → andere Grenzwerte möglich | Nicht berücksichtigt – feste 8h/10h/48h-Werte |
| **§ 8** | Gefährliche Arbeiten | Bundesverordnung – nicht selbst konfigurierbar | Nicht anwendbar |
| **§ 12** | Abweichende Regelungen Sonn-/Feiertage per Tarifvertrag | Wenn Tarifvertrag gilt: min. Freisonntage abweichend | Nicht berücksichtigt |
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

## 13. Verbleibende Lücken (Gesamtüberblick)

| Anforderung | § | Priorität | Begründung |
|-------------|---|-----------|------------|
| 6-Monats-Ausgleichszeitraum | §3 | Niedrig | Rollierender Durchschnitt technisch komplex; bei typischen Praxiszeiten selten relevant |
| Pausen-Timing (max. 6h am Stück) | §4 Satz 3 | Niedrig | Start/Ende der Pause nicht erfasst; für geregelte Praxiszeiten kein Risiko |
| Kürzerer 1-Monat-Ausgleich für Nachtarbeitnehmer | §6 Abs. 2 | Niedrig | Gilt nur für Nachtarbeitnehmer mit >48 Nächten; selten in Arztpraxen (Warnung bereits integriert) |
| Arbeitsmedizinische Untersuchungen | §6 Abs. 3 | Mittel | HR-Pflicht; sollte in Personalakte dokumentiert werden |
| Recht auf Tagesarbeitsplatz | §6 Abs. 4 | Niedrig | Arbeitgeber-Pflicht bei Nachweis; nicht systemisch abbildbar |
| Lohnzuschlag / Freizeitausgleich Nachtarbeit | §6 Abs. 5 | Mittel | Lohnbuchhaltungsaufgabe; Nachweispflicht beim Arbeitgeber |
| Tarifvertragliche Abweichungen | §7 | Niedrig | PraxisZeit verwendet feste gesetzliche Grenzwerte |

---

> **Rechtlicher Hinweis:** Diese Analyse ersetzt keine Rechtsberatung. Arbeitgeber sind selbst
> verantwortlich für die Einhaltung des ArbZG. Bei Fragen zur Anwendung einzelner Vorschriften
> sollte ein Fachanwalt für Arbeitsrecht hinzugezogen werden.
