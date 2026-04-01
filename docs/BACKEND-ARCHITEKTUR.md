# Backend-Architektur – PraxisZeit

## Router-Struktur

Der Admin-Router wurde aus einer 1244-Zeilen God-File in 7 Sub-Router aufgeteilt:

| Router | Datei | Zweck |
|--------|-------|-------|
| **Admin (Koordinator)** | `admin.py` | Inkludiert alle Sub-Router |
| Admin Users | `admin_users.py` | CRUD Benutzer, Stundenänderungen, Anonymisierung |
| Admin Time Entries | `admin_time_entries.py` | Zeit-Einträge verwalten, Audit-Log |
| Admin Change Requests | `admin_change_requests.py` | Korrekturanträge prüfen/genehmigen |
| Admin Vacations | `admin_vacations.py` | Urlaubsanträge genehmigen |
| Admin Carryovers | `admin_carryovers.py` | Jahresabschluss + Vorjahresübernahmen |
| Admin Settings | `admin_settings.py` | System-Einstellungen (Key-Value) |
| Admin Helpers | `admin_helpers.py` | Geteilte Hilfsfunktionen, Audit-Logging |

### User-facing Router

| Router | Datei | Zweck |
|--------|-------|-------|
| Auth | `auth.py` | Login, Logout, Refresh, Profil, TOTP 2FA |
| Dashboard | `dashboard.py` | Überstundenkonto, Urlaubskonto, fehlende Buchungen |
| Time Entries | `time_entries.py` | Stempeln, Zeiteinträge CRUD |
| Absences | `absences.py` | Abwesenheiten (Urlaub, Krank, Fortbildung) |
| Vacation Requests | `vacation_requests.py` | Urlaubsanträge stellen |
| Change Requests | `change_requests.py` | Korrekturanträge stellen |
| Journal | `journal.py` | Monatsjournal |
| Reports | `reports.py` | Berichte (Monats-/Jahresreport, ArbZG, PDF/ODS) |
| Holidays | `holidays.py` | Feiertage nach Bundesland |
| Company Closures | `company_closures.py` | Betriebsferien |
| Import XLS | `import_xls.py` | Bulk-Import aus Excel |
| Error Logs | `error_logs.py` | Fehler-Monitoring (Admin) |

## Services

| Service | Datei | Zweck |
|---------|-------|-------|
| `calculation_service.py` | Stunden-Berechnung | Soll/Ist, Überstundenkonto, Jahresabschluss, Urlaubskonto |
| `auth_service.py` | Authentifizierung | Passwort-Hashing, JWT, Token-Validierung |
| `journal_service.py` | Monatsjournal | Tages-Details mit Soll/Ist/Pausen |
| `holiday_service.py` | Feiertage | Feiertags-Berechnung nach Bundesland |
| `timezone_service.py` | Zeitzonen | `today_local()` für korrekte Datumsgrenzen |
| `xls_import_service.py` | Excel-Import | Parsing + ArbZG-Validierung |
| `break_validation_service.py` | Pausenvalidierung | ArbZG §4 Pausenregeln |

## Berechnungsmodell (calculation_service.py)

### Absence-Typ-Matrix

| Absence-Typ | Reduziert Soll? | Zählt als Ist? | Zweck |
|---|---|---|---|
| **VACATION** | Ja | Nein | Urlaub |
| **SICK** | Nein | Ja | Krankheit (§3 EntgFG) |
| **TRAINING** | Nein | Ja | Fortbildung (außer Haus) |
| **OVERTIME** | Nein | Nein | Überstundenausgleich |
| **OTHER** | Ja | Nein | Sonstiges |

**Überstundenausgleich-Logik:** An einem Ausgleichstag bleibt das Soll bestehen (z.B. 8h), die Ist-Stunden sind 0h. Dadurch sinkt das kumulative Überstundenkonto um das Tagessoll. Beispiel: 10 Arbeitstage à 9h mit 1 Tag Ausgleich → Soll 80h, Ist 81h, Bilanz +1h.

### Gemischte Tage (Mixed Days)

Wenn an einem Tag sowohl TimeEntries als auch Absences existieren:
- `day_type = "mixed"`
- `actual_hours = time_hours + credited_sum` (TRAINING/SICK werden gutgeschrieben)
- `target_hours = daily_target - target_reducing_sum` (VACATION/OTHER/OVERTIME reduzieren Soll)

### Jahresabschluss (create_year_closing)

1. Berechnet Überstundenkonto zum 31.12. via `get_overtime_account(year, 12)`
2. Berechnet Resturlaub via `get_vacation_account(year)['remaining_days']`
3. Erstellt/überschreibt `YearCarryover(year=year+1)` als Startbilanz fürs Folgejahr
4. Idempotent — mehrmaliges Ausführen liefert gleiche Ergebnisse

### Überstundenkonto (get_overtime_account)

1. Sucht neuesten `YearCarryover` ≤ Berechnungsjahr als Startbilanz
2. Iteriert alle Monate vom Start bis zum Zielmonat
3. Pro Monat: `cumulative += monthly_actual - monthly_target`
4. Carryover wird nur als Startpunkt verwendet, nicht doppelt addiert

### Urlaubskonto (get_vacation_account)

- Budget = `user.vacation_days` + Übertrag (YearCarryover)
- Pro-Rata bei Eintritt/Austritt im laufenden Jahr
- Verbrauch = Summe aller VACATION-Absences im Jahr
- Konvertierung Tage ↔ Stunden via aktuellem `daily_target`

## Wichtige Patterns

- **`get_weekly_hours_for_date(db, user, date)`** — Immer pro Tag aufrufen, nie `user.weekly_hours` direkt (historische Änderungen!)
- **Pydantic Response-Schemas:** `float` statt `Decimal` (JSON-Serialisierung)
- **RLS-Kontext:** Bei neuen Endpoints immer `set_tenant_context(db, tid)` aufrufen
- **Bulk-Deletes:** `synchronize_session=False` + expliziter `tenant_id`-Filter

## Änderungsanträge (Change Requests)

### Approval-Reihenfolge (admin_change_requests.py)

1. **Precondition-Checks** (VOR Status-Änderung):
   - CREATE: Duplikat-Prüfung (user + date + start_time)
   - UPDATE: Entry-Existenz + Unique-Constraint bei Datumsänderung
   - DELETE: Entry-Existenz
2. **Status auf APPROVED setzen** (nur wenn alle Checks bestanden)
3. **Änderung anwenden** (Entry erstellen/updaten/löschen + Audit-Log)
4. **db.commit()**

### Validierung (change_requests.py)

- CREATE/UPDATE: Nur vergangene Tage, Endzeit > Startzeit
- Arbeitszeitraum-Prüfung (first/last_work_day)
- ArbZG §4 Pausenvalidierung, §3 Tagesarbeitszeit-Limit
