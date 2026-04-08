# ArbZG-Compliance-Auditor Memory

## Letzter Audit: 07.04.2026 (Vollaudit nach Native-Modus-Fixes)

## Implementierungsstand

### Kernchecks und Dateien
- **§3 Hard-Stop (10h)**: `time_entries.py` create/update/clock_out + `admin.py` admin_create/admin_update + `change_requests.py` create
- **§3 Warnung (8h)**: Employee-Pfade ja; Admin-Pfade DAILY_HOURS_WARNING jetzt implementiert; WEEKLY_HOURS_WARNING fehlt weiterhin in admin_create/admin_update (NIEDRIG)
- **§4 Pausenpflicht (Gesamtdauer)**: `break_validation_service.py` validate_daily_break() - alle 6 Pfade korrekt
- **§4 Satz 2**: 15min-Gap-Mindestdauer JETZT geprueft (break_validation_service.py Zeile 69: gap >= 15); deklarierte Pause < 15min ebenfalls abgelehnt (Zeile 95-99) -- BEHOBEN
- **§5 Ruhezeit**: Echtzeit-Warnung beim Einstempeln implementiert (time_entries.py clock_in() Zeilen 208-223) -- BEHOBEN
- **§6 is_night_work**: `arbzg_utils.is_night_work()` importiert in ALLEN Reports/Routern korrekt (altes Finding "vereinfachte Logik in reports.py" ist überholt - reports.py nutzt arbzg_utils seit aktuellem Stand)
- **§6 Nachtarbeiter-Warn**: alle 6 Pfade korrekt inkl. change-request-apply
- **§9/10**: weekday==6 korrekt, SUNDAY_WORK/HOLIDAY_WORK, sunday_exception_reason
- **§14 WEEKLY_HOURS_WARNING**: in allen 6 Pfaden korrekt (inkl. change-request-apply in admin.py Zeile 691-702)
- **§16**: Excel/ODS/PDF-Export, 730-Tage-Purge-Schutz, DSGVO-Anonymisierung behaelt Zeiteintraege
- **§18**: exempt_from_arbzg bool auf User, alle Pfade korrekt

## Offene Findings (Stand 07.04.2026)

### NIEDRIG: §14 - WEEKLY_HOURS_WARNING fehlt in admin_create/admin_update
- `admin_time_entries.py`: DAILY_HOURS_WARNING implementiert (Zeilen 60-62, 144-146)
- `_calculate_weekly_net_hours` importiert aber NICHT aufgerufen in diesen Pfaden
- Hard-Stop 10h und DAILY_HOURS_WARNING funktionieren; nur WEEKLY_HOURS_WARNING (48h) fehlt

### MITTEL: §9 - is_holiday() ohne tenant_id in time_entries.py
- Alle Aufrufe von `is_holiday(db, date)` ohne tenant_id-Parameter (time_entries.py Zeilen 101, 316, 482, 617)
- Im Single-Tenant-Betrieb kein Problem; bei Multi-Tenant koennte Feiertagscheck falsche Tenant-Daten nutzen

### MITTEL (systemisch): Feiertagskalender-Bug sync_current_and_next_year()
- `holiday_service.py` Zeile 165: `db.query(PublicHoliday).all()` – kein tenant_id-Filter beim h.name-Update
- Aktualisiert Feiertagsnamen fuer ALLE Tenants, nicht nur den aufgerufenen

### MITTEL (systemisch): §16 - Tenant-Deaktivierung sperrt Zeitdaten-Zugriff
- tenant.is_active == False → HTTP 403 fuer ALLE User; Purge/Export unerreichbar
- Kein Notfall-Zugang fuer deaktivierte Tenants

## Report-Endpunkte (ArbZG)
- `GET /api/admin/reports/rest-time-violations` - §5 retrospektiv, konfigurierbar min_rest_hours
- `GET /api/admin/reports/sunday-summary` - §11 15-freie-Sonntage
- `GET /api/admin/reports/night-work-summary` - §6 (nutzt arbzg_utils.is_night_work korrekt)
- `GET /api/admin/reports/compensatory-rest` - §11 Ersatzruhetag

## Architektur-Details
- `break_minutes`: Single Integer je TimeEntry (kein Pause-Start/Ende) - systemisch keine Timing-Pruefung möglich
- `arbzg_utils.is_night_work()`: einziger kanonischer Einstiegspunkt, von allen Routern importiert
- `_calculate_daily_net_hours()`: summiert alle Eintraege des Tages (korrekte Multi-Entry-Behandlung)
- XLS-Import: nur Warnings (kein Hard-Stop), exempt_from_arbzg korrekt, is_night_worker korrekt

## Neue Findings (Stand 01.04.2026) - Absence-CRs + Uberstundenausgleich

## Behobene Findings (Stand 07.04.2026)

### BEHOBEN: DSGVO Art. 9 - Sick-Typ in Team-Endpoints
- `absences.py` Zeilen 84-101 und 133-145: Maskierung sick→absent fuer Nicht-Admins korrekt

### BEHOBEN: §3 EntgFG - Sick-CR-Approval
- `admin_change_requests.py` Zeilen 225-232: SICK-Override mit get_daily_target_for_date() korrekt

### BEHOBEN: §16 - Kein Audit-Log fuer Absence-CR-Aktionen
- `admin_change_requests.py`: alle drei Aktionen (CREATE 249-263, UPDATE 267-298, DELETE 300-316) haben TimeEntryAuditLog-Eintraege

### BEHOBEN: DSGVO JSON-Monatsreport
- `reports.py` Zeile 36: include_health_data-Flag vorhanden; sick_hours conditional (Zeile 108)

### NOCH OFFEN: Negativer Uberstundenkonto-Schutz bei OVERTIME-Absence (MITTEL)
- `absences.py` und `admin_change_requests.py` pruefen Kontostand bei OVERTIME nicht
- Vergleich: Vacation-Budget in `absences.py` Zeile 289-301 korrekt geprueft

## Architektur: Overtime-Ausgleich (korrekt, Stand 01.04.2026)
- OVERTIME in `notin_([TRAINING, SICK, OVERTIME])` bei Soll-Berechnung → Soll bleibt erhalten
- OVERTIME nicht in `[TRAINING, SICK]` bei Ist-Berechnung → Ist = 0
- Netto-Effekt: Konto -= daily_target pro OVERTIME-Tag → rechtlich korrekt
- Konsistent in: get_monthly_target, get_monthly_actual, get_overtime_account, get_ytd_summary, journal_service.py

## Architektur: Absence-CR-Pfad (Stand 01.04.2026)
- `change_requests.py` Zeile 51: `entry_kind == "absence"` → eigener Branch → kein ArbZG-Check
- Pause- und Hard-Stop-Validierung korrekt nur im TimeEntry-Branch
- Absence-CR speichert Snapshot: original_absence_type, original_absence_hours, original_start_time

## Ueberholt / Korrigierte Findings
- §2/§6 Inkonsistenz reports.py: reports.py nutzt aktuell korrekt arbzg_utils.is_night_work() - altes Finding ungueltig
- §14 fehlt in change-request-apply: ist implementiert (admin_change_requests.py Zeilen 354-366) - altes Finding ungueltig
- §4 Satz 2 15min-Gap: behoben in break_validation_service.py (Audit 07.04.2026)
- §5 Echtzeit-Ruhezeit: behoben in time_entries.py clock_in() (Audit 07.04.2026)
- DSGVO Art.9 Team-Endpoints: behoben in absences.py (Audit 07.04.2026)
- §3 EntgFG Sick-CR: behoben in admin_change_requests.py (Audit 07.04.2026)
- §16 Absence-CR Audit-Log: behoben in admin_change_requests.py (Audit 07.04.2026)
- DSGVO JSON-Monatsreport include_health_data: behoben in reports.py (Audit 07.04.2026)
