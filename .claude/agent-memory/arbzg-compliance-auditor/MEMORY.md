# ArbZG-Compliance-Auditor Memory

## Letzter Audit: 17.06.2026 (Vollaudit v1.8.10, master bac703e)

## Implementierungsstand (verifiziert 17.06.2026)

### Kernchecks und Dateien
- **§3 Hard-Stop (10h)**: `time_entries.py` create/update/clock_out + `admin_time_entries.py` admin_create/admin_update + `admin_change_requests.py` CR-Genehmigung — ALLE PFADE KONFORM
- **§3 Warnung (8h)**: Alle 6 Pfade korrekt (DAILY_HOURS_WARNING)
- **§3 Ausgleichszeitraum**: `reports.py` `/24-week-average`-Endpoint — korrekt implementiert
- **§4 Pausenpflicht**: `break_validation_service.py` validate_daily_break() — alle 6 Pfade korrekt, 15min-Mindestpause korrekt
- **§4 Break-Waiver**: audit-trail mit source='break_waiver' in allen Pfaden; approval-workflow konfigurierbar; clock-out nicht-blockierend (R2-b)
- **§5 Ruhezeit**: Echtzeit-Warnung clock_in() `time_entries.py` Zeilen 286-314 (TZ-aware, DST-korrekt) + `rest_time_service.py` retrospektiv — KONFORM
- **§6 is_night_work**: 23:00-06:00, `arbzg_utils.py` — korrekt per §2 Abs.4 ArbZG Normalfenster
- **§6 Nachtarbeiter-Warn**: alle 6 Pfade korrekt inkl. change-request-apply + XLS-Import (behoben Jun 2026)
- **§6 XLS-Import**: `xls_import_service.py:67-68,183-184` — exempt_from_arbzg UND is_night_worker jetzt korrekt
- **§6 Nachtarbeit-Report**: `reports.py` `/night-work-summary` — korrekt
- **§9/10**: weekday==6 korrekt, SUNDAY_WORK/HOLIDAY_WORK mit tenant_id — KONFORM
- **§11**: `/sunday-summary` + `/compensatory-rest` — korrekt mit tenant_id
- **§14 WEEKLY_HOURS_WARNING**: in allen 6 Pfaden korrekt
- **§16**: Excel/ODS/PDF-Export, 730-Tage-Purge-Schutz, Audit-Log alle Source-Marker <40 Zeichen; raw_start/raw_end bei geclampten Eintraegen
- **§18**: exempt_from_arbzg bool auf User, alle Pfade korrekt inkl. XLS-Import
- **§3 BUrlG Tagesprinzip**: beide Pfade (create_absence + review_vacation_request + CR-Genehmigung Absence) konsistent; OVERTIME-Ausnahme korrekt; track_hours=False korrekt
- **Feature #201**: work_window_service.clamp() in allen 6 Pfaden + CR-Genehmigung; §16 raw_* korrekt erhalten
- **Feature #191**: track_hours=False bucht Abwesenheiten tagebasiert mit hours=0; Vacation-Budget-Check korrekt
- **Feature #193/#195**: _within_employment_window() in get_monthly_target/get_overtime_account/get_ytd_summary (Soll+Ist)

### RLS-Architektur (wichtig fuer Compliance-Bewertung)
- users, public_holidays, time_entries etc. haben RLS-Policies (Migration 027)
- `set_tenant_context(db, tenant_id)` wird in auth.py Middleware IMMER gesetzt
- Daher: MITTEL-Findings ohne expliziten tenant_id-Filter sind durch RLS geschuetzt
- Aber: belt-and-suspenders-Filter fehlt — vor Phase 4 SaaS zwingend behoben

## Offene Findings (Stand 17.06.2026)

### MITTEL: §5 Rest-Time-Service ohne expliziten Tenant-Filter
- `rest_time_service.py:116`: `db.query(User).filter(User.is_active == True)` OHNE tenant_id
- Durch RLS geschuetzt; fehlt belt-and-suspenders

### MITTEL: count_workdays() tenant_id optional statt mandatory
- `calculation_service.py:851`: `def count_workdays(db, start, end, tenant_id=None)`
- Alle Aufrufer uebergeben tenant_id korrekt; Parameter sollte aber mandatory sein

### NIEDRIG: Kein Audit-Log bei Vacation-Request-Erstellung
- `vacation_requests.py:341-355`: create_vacation_request() schreibt keinen TimeEntryAuditLog
- Cancel (vacation_request_cancel) und Edit (vacation_request_edit) sind dokumentiert; CREATE fehlt
- Nicht §16-pflichtig; aber vollstaendiger Audit-Trail waere besser

### NIEDRIG: ChangeRequestForm zeigt keine ArbZG-Warnings aus API
- `frontend/src/components/ChangeRequestForm.tsx`: response.data.warnings nach await ignoriert
- Backend gibt warnings zurueck (§6 Nachtarbeiter etc.); `showArbzgWarnings(toast, ...)` fehlt

### NIEDRIG: Admin-Pfade kein SUNDAY_WORK/HOLIDAY_WORK
- `admin_time_entries.py`: admin_create/admin_update ohne Sonn-/Feiertagswarnungen
- Akzeptabel (Admins kennen Kalender)

## Behoben seit 23.05.2026
- XLS-Import: exempt_from_arbzg + is_night_worker korrekt in _check_arbzg()
- absences.py PublicHoliday tenant_id-Filter korrekt (war kein aktives Finding mehr)
- admin_vacations.py PublicHoliday tenant_id korrekt

## Report-Endpunkte (ArbZG) — vollstaendig
- `GET /api/admin/reports/rest-time-violations` - §5 retrospektiv
- `GET /api/admin/reports/sunday-summary` - §11 15-freie-Sonntage
- `GET /api/admin/reports/night-work-summary` - §6 Nachtarbeit
- `GET /api/admin/reports/compensatory-rest` - §11 Ersatzruhetag
- `GET /api/admin/reports/24-week-average` - §3 Ausgleichszeitraum
- `GET /api/admin/reports/monthly` - §16 Monatsreport
- `GET /api/admin/reports/export*` - §16 Excel/ODS/PDF Export

## Architektur-Details
- `break_minutes`: Single Integer je TimeEntry — keine Pause-Timing-Pruefung moeglich (§4 Satz 3)
- `arbzg_utils.is_night_work()`: 23:00-06:00 (korrekt per §2 Abs.4 ArbZG Normalfenster)
- `_calculate_daily_net_hours()`: summiert alle Eintraege des Tages + new entry, max(0,...)-Floor
- RLS via PostgreSQL-POLICY schuetzt alle Tabellen — auth.py Middleware setzt immer Kontext
- Source-Marker alle < 40 Zeichen (varchar(40) Limit Migration 037)
- work_window_service.clamp() IMMER VOR §3/§4-Checks aufrufen (geclamped = angerechnet = compliance-relevant)
- clock_out: §3 10h-Hard-Stop ist WARNUNG (nicht 422) — R2-b: offener Eintrag darf nicht eingesperrt werden
- XLS-Import: kein work_window_clamp (historische Daten, akzeptiertes Design)
- track_hours=False: clamp() gibt ungeaendert zurueck (Zeile 58-59 work_window_service.py)
