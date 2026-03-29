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

## Wichtige Patterns

- **`get_weekly_hours_for_date(db, user, date)`** — Immer pro Tag aufrufen, nie `user.weekly_hours` direkt (historische Änderungen!)
- **Pydantic Response-Schemas:** `float` statt `Decimal` (JSON-Serialisierung)
- **RLS-Kontext:** Bei neuen Endpoints immer `set_tenant_context(db, tid)` aufrufen
- **Bulk-Deletes:** `synchronize_session=False` + expliziter `tenant_id`-Filter
