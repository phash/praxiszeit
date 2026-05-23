# ArbZG-Compliance-Auditor Memory

## Letzter Audit: 23.05.2026 (Vollaudit nach vacation-request-edit Feature + 70 Commits seit 08.04.)

## Implementierungsstand (verifiziert 23.05.2026)

### Kernchecks und Dateien
- **§3 Hard-Stop (10h)**: `time_entries.py` create/update/clock_out + `admin_time_entries.py` admin_create/admin_update + `change_requests.py` create — ALLE PFADE KONFORM
- **§3 Warnung (8h)**: Alle 6 Pfade korrekt (DAILY_HOURS_WARNING)
- **§3 Ausgleichszeitraum**: `reports.py` `/24-week-average`-Endpoint — NEU seit letztem Audit, korrekt implementiert
- **§4 Pausenpflicht**: `break_validation_service.py` validate_daily_break() — alle 6 Pfade korrekt, 15min-Mindestpause korrekt
- **§5 Ruhezeit**: Echtzeit-Warnung clock_in() `time_entries.py` Zeilen 247-269 (TZ-aware, DST-korrekt) + `rest_time_service.py` retrospektiv — KONFORM
- **§6 is_night_work**: 23:00-06:00 (NICHT 22:00!), `arbzg_utils.py` — kanonisch korrekt per §2 Abs.4 ArbZG Normalfenster
- **§6 Nachtarbeiter-Warn**: alle 6 Pfade korrekt inkl. change-request-apply
- **§6 Nachtarbeit-Report**: `reports.py` `/night-work-summary` — korrekt, nutzt arbzg_utils.is_night_work
- **§9/10**: weekday==6 korrekt, SUNDAY_WORK/HOLIDAY_WORK mit tenant_id in time_entries.py allen Pfaden — KONFORM
- **§11**: `/sunday-summary` + `/compensatory-rest` — korrekt mit tenant_id
- **§14 WEEKLY_HOURS_WARNING**: in allen 6 Pfaden korrekt — KONFORM (altes Finding war bereits behoben)
- **§16**: Excel/ODS/PDF-Export, 730-Tage-Purge-Schutz, Audit-Log mit allen Source-Markern <40 Zeichen
- **§18**: exempt_from_arbzg bool auf User, alle Pfade korrekt

### RLS-Architektur (wichtig für Compliance-Bewertung)
- users, public_holidays, time_entries etc. haben RLS-Policies (Migration 027)
- `set_tenant_context(db, tenant_id)` wird in auth.py Middleware IMMER gesetzt
- Daher: `rest_time_service.check_all_users_violations()` OHNE expliziten tenant_id-Filter ist durch RLS geschuetzt
- `calculation_service.py` PublicHoliday-Queries OHNE tenant_id-Filter sind durch RLS geschuetzt
- Beide sind trotzdem MITTEL-Findings wegen Verteidigungstiefe (fehlt belt-and-suspenders-Filter)

## Offene Findings (Stand 23.05.2026)

### MITTEL: §9 Multi-Tenant - PublicHoliday ohne tenant_id in 4 Dateien
1. `absences.py` Zeile 250-252: `db.query(PublicHoliday).filter(PublicHoliday.year == year)` OHNE tenant_id
2. `admin_vacations.py` Zeile 159: `db.query(PublicHoliday).filter(PublicHoliday.year == year)` OHNE tenant_id
3. `calculation_service.py` Zeilen 201-203, 387-390, 463-465: PublicHoliday ohne tenant_id-Filter
4. `calculation_service.py` Zeile 633: `count_workdays()` ohne tenant_id-Filter
- Im Single-Tenant (on-prem) kein Problem (RLS schuetzt); vor Phase 4 SaaS zwingend beheben

### MITTEL: §5 Rest-Time-Service ohne expliziten Tenant-Filter
- `rest_time_service.py` Zeile 116: `db.query(User).filter(User.is_active == True)` OHNE tenant_id
- Durch RLS geschuetzt; mangelt aber an belt-and-suspenders

### MITTEL (systemisch): Feiertagskalender sync_current_and_next_year()
- `holiday_service.py` Zeile 221-225: `db.query(PublicHoliday)` ohne tenant_id beim Name-Update
- Tenant_id wird ab Zeile 215 als Parameter mitgegeben und ab Zeile 222 gefiltert — BEHOBEN (Zeile 222 hat den Filter)
- AKTION: Verifiziert — `sync_current_and_next_year` filtert korrekt per tenant_id (Zeile 222-225)

### NIEDRIG: §16 Audit-Log Luecke bei Vacation-Request-Create
- `vacation_requests.py`: Kein Audit-Log bei ERSTELLEN eines Urlaubsantrags (nur bei Cancel und Edit)
- Gesetzlich ist die Erstellung eines Antrags (nicht nur die Genehmigung) dokumentationswuerdig

### NIEDRIG: Change-Request-Formular zeigt keine ArbZG-Warnings aus API
- `ChangeRequestForm.tsx` Zeile 46-62: API-Response wird nach `await` komplett ignoriert
- Backend gibt warnings in Response zurueck (z.B. §6 Nachtarbeiter), Frontend zeigt sie nicht an
- `showArbzgWarnings(toast, response.data.warnings)` fehlt

### NIEDRIG: Admin-Pfade geben kein SUNDAY_WORK/HOLIDAY_WORK zurueck
- `admin_time_entries.py`: admin_create/admin_update senden keine SUNDAY/HOLIDAY-Warnungen
- Akzeptabel (Admins kennen Kalender), aber dokumentationswuerdig

## Behoben seit 08.04.2026 (via vacation-request-edit Feature)

### BEHOBEN: §16 Audit-Log fuer Vacation-Request-Edit
- `vacation_requests.py` Zeilen 349-361: source="vacation_request_edit" — korrekt
- `admin_vacations.py` Zeile 372: source="vacation_request_edit" — korrekt
- `vacation_requests.py` Zeile 218: source="vacation_request_cancel" — korrekt

### BEHOBEN: §16 - sync_current_and_next_year tenant_id
- `holiday_service.py` Zeile 220-225: query hat tenant_id-Filter — KONFORM (altes Finding war irrtuemllich)

## Report-Endpunkte (ArbZG) — vollstaendig
- `GET /api/admin/reports/rest-time-violations` - §5 retrospektiv
- `GET /api/admin/reports/sunday-summary` - §11 15-freie-Sonntage
- `GET /api/admin/reports/night-work-summary` - §6 Nachtarbeit
- `GET /api/admin/reports/compensatory-rest` - §11 Ersatzruhetag
- `GET /api/admin/reports/24-week-average` - §3 Ausgleichszeitraum NEU seit letztem Audit
- `GET /api/admin/reports/monthly` - §16 Monatsreport (DSGVO-konform)
- `GET /api/admin/reports/export*` - §16 Excel/ODS/PDF Export (DSGVO-konform)

## Architektur-Details
- `break_minutes`: Single Integer je TimeEntry — systemisch keine Pause-Timing-Pruefung moeglich
- `arbzg_utils.is_night_work()`: 23:00-06:00 (korrekt per §2 Abs.4 ArbZG Normalfenster)
- `_calculate_daily_net_hours()`: summiert alle Eintraege des Tages korrekt
- RLS via PostgreSQL-POLICY schuetzt alle Tabellen — auth.py Middleware setzt immer Kontext
- Source-Marker alle < 40 Zeichen (varchar(40) Limit Migration 037): laengster = "absence_request_approval" (24 Zeichen)
