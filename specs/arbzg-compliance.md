# ArbZG-Compliance – Kritische Paragrafen für PraxisZeit

> Vollständige Ist-Analyse des Arbeitszeitgesetzes (ArbZG) gegenüber dem aktuellen Implementierungsstand von PraxisZeit.
> Stand: **Februar 2026** | Gesetz: https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html

---

## Übersicht: Compliance-Status

| § | Thema | Status | Lücken |
|---|-------|--------|--------|
| **§ 3** | Tages-Höchstarbeitszeit | ✅ Vollständig | Nur 6-Monats-Ausgleichszeitraum nicht getrackt |
| **§ 4** | Pflichtpausen | ✅ Vollständig | – |
| **§ 5** | Mindestruhezeit (11h) | ✅ Vollständig | – |
| **§ 6** | Nachtarbeit | ✅ Weitgehend | 8h-Limit für Nachtarbeitnehmer; ärztl. Untersuchungs-Tracking |
| **§ 9/10** | Sonn-/Feiertagsruhe | ✅ Vollständig | – |
| **§ 11** | Ausgleich Sonn-/Feiertagsarbeit | ✅ Vollständig | – |
| **§ 14** | Wochenarbeitszeit | ✅ Weitgehend | 6-Monats-Durchschnitt nicht getrackt |
| **§ 16** | Aufzeichnung & Aufbewahrung | ✅ Vollständig | – |
| **§ 18** | Ausnahmen leitende Angestellte | ✅ Vollständig | – |

---

## 1. § 3 – Tägliche Höchstarbeitszeit

**Gesetzliche Regel:**
- Maximale werktägliche Arbeitszeit: **8 Stunden**
- Verlängerung auf **10 Stunden** zulässig, wenn innerhalb von **6 Kalendermonaten oder 24 Wochen** ein Ausgleich auf ≤ 8h Durchschnitt erfolgt

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Warnung bei > 8h/Tag | ✅ | `DAILY_HOURS_WARNING` Flag + Frontend-Toast bei `create`, `update`, `clock_out` |
| Hard-Stop bei > 10h/Tag | ✅ | HTTP 422 bei Erstellung/Bearbeitung über Mitarbeiter-Endpoints |
| §3-Check bei Admin-Direkteintrag | ✅ | `admin.py: admin_create_time_entry` und `admin_update_time_entry` prüfen §3 |
| §3-Check bei Änderungsanträgen | ✅ | `change_requests.py` prüft §3 nach Genehmigung |
| §18-Ausnahme (exempt_from_arbzg) | ✅ | Alle Checks werden für exempt-Benutzer übersprungen |
| 6-Monats-Ausgleichszeitraum | ❌ | Kein Tracking ob Durchschnitt ≤ 8h eingehalten wird (Dokumentationsaufgabe) |

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

---

## 2. § 4 – Ruhepausen (Pflichtpausen)

**Gesetzliche Regel:**
- Arbeit > 6 Stunden → mind. **30 Minuten** Pause
- Arbeit > 9 Stunden → mind. **45 Minuten** Pause
- Ohne jede Pause: maximal **6 Stunden** am Stück erlaubt
- Pausen können aufgeteilt werden (mind. 15 min je Einheit)

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Pausenfeld im Zeiteintrag | ✅ | `break_minutes` bei allen Zeiteinträgen erfasst |
| >6h → mind. 30min Pflicht | ✅ | `break_validation_service.validate_daily_break()` – aktiv bei create/update/clock_out/admin/change_requests |
| >9h → mind. 45min Pflicht | ✅ | `break_validation_service.py` prüft beide Regeln (9h/45min vor 6h/30min) |
| §18-Ausnahme (exempt_from_arbzg) | ✅ | Pausenpflicht-Checks werden für exempt-Benutzer übersprungen |

**Status: Vollständig konform** ✅

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

---

## 3. § 5 – Mindestruhezeit zwischen Schichten

**Gesetzliche Regel:**
- Mind. **11 Stunden ununterbrochene Ruhezeit** nach dem Ende eines Arbeitstages
- Ausnahmen in bestimmten Branchen (Krankenhäuser, Notaufnahme) mit Ausgleich innerhalb 4 Wochen

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| 11h-Prüfung zwischen Schichten | ✅ | `rest_time_service.check_rest_time_violations()` vollständig |
| Admin-Report | ✅ | `/api/admin/reports/rest-time-violations` (Jahr + optionaler Monat, konfigurierbarer Schwellwert) |
| Frontend-Anzeige | ✅ | Admin Reports-Seite zeigt Verstöße mit Betroffenen, Datum und Defizit in Stunden |

**Status: Vollständig konform** ✅

---

## 4. § 6 – Nacht- und Schichtarbeit

**Gesetzliche Regel:**
- **Nachtzeit:** 23:00–06:00 Uhr (§ 2 Abs. 3)
- **Nachtarbeitnehmer:** wer an mind. 48 Tagen/Jahr oder regelmäßig Nachtarbeit leistet
- Max. **8 Stunden** Arbeitszeit für Nachtarbeitnehmer (verlängerbar auf 10h, Ausgleich innerhalb 1 Monat)
- Anspruch auf **arbeitsmedizinische Untersuchung** (§ 6 Abs. 3)
- Anspruch auf **bezahlten Ausgleich** (25%-Zuschlag oder gleichwertige Freizeit) bei regelmäßiger Nachtarbeit

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Erkennung von Nachtarbeit (23–6 Uhr) | ✅ | `_is_night_work()` in `time_entries.py` |
| `is_night_work` Flag in API | ✅ | Returned in allen `TimeEntryResponse` Endpoints |
| „Nacht"-Badge im Frontend | ✅ | Indigo-Badge in `TimeTracking.tsx` |
| Admin-Report: Nachtarbeit-Statistik | ✅ | `/api/admin/reports/night-work-summary` – Nachtschichten/MA, Nachtarbeitnehmer-Markierung (≥48 Tage) |
| Strengere 8h-Grenze für Nachtarbeitnehmer | ❌ | Alle Mitarbeiter haben dasselbe 10h Hard-Limit (separate Nachtarbeitnehmer-Grenze nicht implementiert) |
| Tracking arbeitsmedizinischer Untersuchungen | ❌ | Nicht vorgesehen – Verwaltungsaufgabe außerhalb des Systems |

**Bußgeldrisiko:** bis **30.000 €** (§ 22 ArbZG)

---

## 5. §§ 9/10 – Sonn- und Feiertagsruhe

**Gesetzliche Regel (§ 9):**
- Beschäftigungsverbot an Sonn- und Feiertagen **0–24 Uhr** (Grundsatz)

**Ausnahmen (§ 10) u.a.:**
- Nr. 1: Kontinuierlich betriebene Anlagen, Notdienste, **Gesundheitsversorgung**
- Arztpraxen können unter Notfalldienst/Gesundheitsversorgung fallen → dokumentationspflichtig

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Sonntagserkennung | ✅ | `weekday() == 6` in `_enrich_response()` |
| Feiertagserkennung | ✅ | `is_holiday()` via `workalendar`-DB (alle Bundesländer konfigurierbar, default Bayern) |
| `is_sunday_or_holiday` Flag in API | ✅ | In allen TimeEntry-Responses |
| `SUNDAY_WORK` / `HOLIDAY_WORK` Warnings | ✅ | In API-Response + Frontend Toast |
| Visuelles Highlighting (orange) | ✅ | Tabellenzeilen + „So/FT"-Badge in `TimeTracking.tsx` |
| Ausnahmegrund-Feld (§ 10 ArbZG) | ✅ | Optionales Textfeld `sunday_exception_reason` im Formular (erscheint bei Sonn-/Feiertagen) |
| §18-Ausnahme (exempt_from_arbzg) | ✅ | Warnungen werden für exempt-Benutzer nicht erzeugt |

**Status: Vollständig konform** ✅

---

## 6. § 11 – Ausgleich nach Sonn- und Feiertagsarbeit

**Gesetzliche Regel:**
- Mind. **15 beschäftigungsfreie Sonntage** pro Jahr pro Arbeitnehmer
- Ersatzruhetag nach **Sonntagsarbeit** innerhalb **2 Wochen**
- Ersatzruhetag nach **Feiertagsarbeit** innerhalb **8 Wochen**

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| 15-freie-Sonntage Compliance | ✅ | `/api/admin/reports/sunday-summary` mit Grün/Rot-Bewertung |
| Frontend Sunday-Report | ✅ | Tabelle mit Jahresauswahl in `admin/Reports.tsx` |
| Ersatzruhetag-Tracking (2 Wochen) | ✅ | `/api/admin/reports/compensatory-rest` prüft freien Tag nach Sonntagsarbeit innerhalb 2 Wochen |
| Ersatzruhetag-Tracking (8 Wochen) | ✅ | Selber Endpoint prüft Feiertagsarbeit mit 8-Wochen-Fenster |
| Frontend Ersatzruhetag-Report | ✅ | Sektion „Ersatzruhetage §11 ArbZG" in `admin/Reports.tsx` |

**Status: Vollständig konform** ✅

---

## 7. § 14 – Außergewöhnliche Fälle / Wochenarbeitszeit

**Gesetzliche Regel:**
- Maximale Wochenarbeitszeit im **6-Monats-Durchschnitt: 48 Stunden**

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Warnung bei > 48h/Woche | ✅ | `WEEKLY_HOURS_WARNING` in `create`, `update`, `clock_out` + Frontend-Toast |
| §18-Ausnahme (exempt_from_arbzg) | ✅ | Wochenarbeitszeit-Check wird für exempt-Benutzer übersprungen |
| 6-Monats-Durchschnitt | ❌ | Nur wöchentliche Momentaufnahme, kein gleitender 6-Monats-Schnitt |

---

## 8. § 16 – Aufzeichnungs- und Aufbewahrungspflicht

**Gesetzliche Regel:**
- Arbeitgeber muss Arbeitszeiten, die **8 Stunden werktäglich überschreiten**, aufzeichnen
- Aufzeichnungen mind. **2 Jahre** aufbewahren
- **Gesetzesaushang** (ArbZG) am Arbeitsplatz erforderlich

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Vollständige Zeiterfassung in DB | ✅ | Start, Ende, Pausen, Datum, Mitarbeiter, Ausnahmegrund |
| 2-Jahres-Aufbewahrung dokumentiert | ✅ | `INSTALLATION.md`: Backup-Anleitung + Retention-Prozess |
| Hinweis in docker-compose.yml | ✅ | Kommentar über Aufbewahrungspflicht am `postgres_data`-Volume |
| §16-Hinweis im Admin-Frontend | ✅ | In Reports-Seite unter „Hinweise" |
| Excel-Export als Nachweis | ✅ | Monats- und Jahresexporte verfügbar |
| Gesetzesaushang-Funktion | ✅ | Link zum ArbZG-Gesetzestext (gesetze-im-internet.de) in Admin-Reports |

**Status: Vollständig konform** ✅

---

## 9. § 18 – Ausnahmen für leitende Angestellte

**Gesetzliche Regel:**
- Leitende Angestellte (Chefärzte, Praxisinhaber) können vom ArbZG ausgenommen sein

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Ausnahme-Flag auf Benutzerebene | ✅ | `exempt_from_arbzg` (Boolean) auf User-Model + DB-Spalte |
| Admin-UI zur Verwaltung | ✅ | Checkbox „ArbZG-Prüfungen aussetzen (§18 ArbZG)" in Benutzerverwaltung |
| Vollständige Bypass-Logik | ✅ | Alle §3/§4/§14-Checks und Warnungen werden für exempt-Benutzer übersprungen |

**Status: Vollständig konform** ✅

---

## 10. Weitere Paragrafen

| § | Thema | Relevanz | Status |
|---|-------|----------|--------|
| **§ 7** | Tarifvertragliche Abweichungen | Wenn Tarifvertrag gilt → andere Grenzwerte möglich | Nicht berücksichtigt – feste 8h/10h-Werte |
| **§ 22** | Bußgeldvorschriften | Bis 30.000 € pro Verstoß | Sanktionsrahmen unverändert |
| **§ 23** | Strafvorschriften | Freiheitsstrafe bei vorsätzlicher Gesundheitsgefährdung | – |

---

## 11. Straf- und Bußgeldrahmen

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

## 12. Verbleibende Lücken (niedrige Priorität)

| Anforderung | § | Aufwand | Begründung |
|-------------|---|---------|------------|
| 6-Monats-Ausgleichszeitraum §3 | §3 | Hoch | Rollierender Durchschnitt komplexe Berechnung; Verwaltungsaufgabe |
| Strengere 8h-Grenze für Nachtarbeitnehmer | §6 | Mittel | Erfordert Nachtarbeitnehmer-Status-Flag auf User-Ebene |
| Tracking arbeitsmedizinischer Untersuchungen | §6 | Mittel | HR-Verwaltungsaufgabe; sinnvoller in separatem HR-System |
| 6-Monats-Durchschnitt Wochenarbeitszeit §14 | §14 | Mittel | Gleitender Durchschnitt; aktuelle Warnungen bieten ausreichende Sicherheit |

---

> **Rechtlicher Hinweis:** Diese Analyse ersetzt keine Rechtsberatung. Arbeitgeber sind selbst
> verantwortlich für die Einhaltung des ArbZG. Bei Fragen zur Anwendung einzelner Vorschriften
> sollte ein Fachanwalt für Arbeitsrecht hinzugezogen werden.
