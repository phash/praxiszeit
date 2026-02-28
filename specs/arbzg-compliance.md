# ArbZG-Compliance – Kritische Paragrafen für PraxisZeit

> Vollständige Ist-Analyse des Arbeitszeitgesetzes (ArbZG) gegenüber dem aktuellen Implementierungsstand von PraxisZeit.
> Stand: **Februar 2026** | Gesetz: https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html

---

## Übersicht: Compliance-Status

| § | Thema | Status | Lücken |
|---|-------|--------|--------|
| **§ 3** | Tages-Höchstarbeitszeit | ⚠️ Teilweise | Admin-Endpoints ohne Prüfung; kein Ausgleichszeitraum |
| **§ 4** | Pflichtpausen | ⚠️ Teilweise | 9h→45min-Regel fehlt; nur 6h→30min implementiert |
| **§ 5** | Mindestruhezeit (11h) | ✅ Vollständig | – |
| **§ 6** | Nachtarbeit | ⚠️ Teilweise | Kein Report; 8h-Limit für Nachtarbeitnehmer fehlt |
| **§ 9/10** | Sonn-/Feiertagsruhe | ⚠️ Teilweise | Kein Ausnahmegrund-Feld; kein Feiertags-Report |
| **§ 11** | Ausgleich Sonn-/Feiertagsarbeit | ⚠️ Teilweise | Kein Ersatzruhetag-Tracking (2/8 Wochen) |
| **§ 16** | Aufzeichnung & Aufbewahrung | ✅ Weitgehend | Admin-Direkteinträge ohne §3-Prüfung |

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
| §3-Check bei Admin-Direkteintrag | ❌ | `admin.py: admin_create_time_entry` und `admin_update_time_entry` fehlt §3-Prüfung |
| §3-Check bei Änderungsanträgen | ❌ | `change_requests.py` prüft §4, aber nicht §3 |
| 6-Monats-Ausgleichszeitraum | ❌ | Kein Tracking ob Durchschnitt ≤ 8h eingehalten wird |

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
| >9h → mind. 45min Pflicht | ❌ | `break_validation_service.py` prüft **nur** die 6h/30min-Regel; die 9h/45min-Regel fehlt vollständig |

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
| Admin-Report: Nachtarbeit-Statistik | ❌ | Kein Report über Häufigkeit/Mitarbeiter |
| Strengere 8h-Grenze für Nachtarbeitnehmer | ❌ | Alle Mitarbeiter haben dieselbe 10h Hard-Limit |
| Tracking arbeitsmedizinischer Untersuchungen | ❌ | Nicht vorgesehen |

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
| Ausnahmegrund-Feld bei Sonn-/Feiertagsarbeit | ❌ | Kein Pflichtfeld oder optionales Feld für § 10-Ausnahme-Dokumentation |
| Admin-Report: Feiertage gearbeitet | ❌ | `sunday-summary` zählt nur Sonntage, keine Feiertage |

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
| Ersatzruhetag-Tracking (2 Wochen) | ❌ | Keine Verfolgung ob nach Sonntagsarbeit ein Ersatzruhetag gewährt wurde |
| Ersatzruhetag-Tracking (8 Wochen) | ❌ | Keine Verfolgung für Feiertagsarbeit |

---

## 7. § 16 – Aufzeichnungs- und Aufbewahrungspflicht

**Gesetzliche Regel:**
- Arbeitgeber muss Arbeitszeiten, die **8 Stunden werktäglich überschreiten**, aufzeichnen
- Aufzeichnungen mind. **2 Jahre** aufbewahren
- **Gesetzesaushang** (ArbZG) am Arbeitsplatz erforderlich

### Implementierungsstand

| Anforderung | Status | Details |
|-------------|--------|---------|
| Vollständige Zeiterfassung in DB | ✅ | Start, Ende, Pausen, Datum, Mitarbeiter |
| 2-Jahres-Aufbewahrung dokumentiert | ✅ | `INSTALLATION.md`: Backup-Anleitung + Retention-Prozess |
| Hinweis in docker-compose.yml | ✅ | Kommentar über Aufbewahrungspflicht am `postgres_data`-Volume |
| §16-Hinweis im Admin-Frontend | ✅ | In Reports-Seite unter „Hinweise" |
| Excel-Export als Nachweis | ✅ | Monats- und Jahresexporte verfügbar |
| Gesetzesaushang-Funktion | ❌ | Kein digitaler Hinweis/Link zum ArbZG im System |

---

## 8. Weitere Paragrafen

| § | Thema | Relevanz | Status |
|---|-------|----------|--------|
| **§ 7** | Tarifvertragliche Abweichungen | Wenn Tarifvertrag gilt → andere Grenzwerte möglich | Nicht berücksichtigt – feste 8h/10h-Werte |
| **§ 14** | Außergewöhnliche Fälle | Max. 48h/Woche im 6-Monats-Schnitt | Wöchentliche Stundensumme nicht getrackt |
| **§ 18** | Ausnahmen (leitende Angestellte) | Chefärzte/Praxisinhaber ggf. ausgenommen | Kein Ausnahme-Flag auf Benutzerebene |
| **§ 22** | Bußgeldvorschriften | Bis 30.000 € pro Verstoß | Sanktionsrahmen unverändert |
| **§ 23** | Strafvorschriften | Freiheitsstrafe bei vorsätzlicher Gesundheitsgefährdung | – |

---

## 9. Straf- und Bußgeldrahmen

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

## 10. Verbleibende Maßnahmen (priorisiert)

### Prio 1 – Gesetzlich direkt gefordert

1. **§ 4: 9h/45min-Pausenregel** – `break_validation_service.py` um zweite Bedingung erweitern
2. **§ 3: Admin-Endpoints absichern** – `admin.py` `admin_create_time_entry` / `admin_update_time_entry` + `change_requests.py` mit §3-Check nachrüsten

### Prio 2 – Compliance-Dokumentation

3. **§ 10: Ausnahmegrund-Feld** – Optionales Textfeld „Ausnahmegrund (§ 10 ArbZG)" bei Sonn-/Feiertagseinträgen
4. **§ 6: Nachtarbeit-Report** – Admin-Report: wie oft hat welcher Mitarbeiter Nachtarbeit geleistet (für 48-Tage-Schwellwert)
5. **§ 11: Ersatzruhetag-Tracking** – Prüfung ob nach Sonntagsarbeit ein freier Tag innerhalb 2 Wochen folgt

### Prio 3 – Nice-to-have

6. **§ 14: Wochenarbeitszeit** – Warnung bei > 48h/Woche
7. **§ 18: Ausnahme-Flag** – Benutzerfeld „leitender Angestellter" (§ 18 ArbZG) → von Prüfungen ausschließen

---

> **Rechtlicher Hinweis:** Diese Analyse ersetzt keine Rechtsberatung. Arbeitgeber sind selbst
> verantwortlich für die Einhaltung des ArbZG. Bei Fragen zur Anwendung einzelner Vorschriften
> sollte ein Fachanwalt für Arbeitsrecht hinzugezogen werden.
