# ArbZG-Compliance-Auditor Memory

## Letzter Audit: 01.03.2026 (Migration 001-020)

## Implementierungsstand (vollstandig)

### Kernchecks und Dateien
- **§3 Hard-Stop (10h)**: `time_entries.py` create/update/clock_out + `admin.py` admin_create/admin_update + `change_requests.py` create
- **§3 Warnung (8h)**: alle o.g. Pfade ausser change-request-apply
- **§4 Pausenpflicht**: `break_validation_service.py` validate_daily_break() - alle Pfade ausser clock-out (N/A)
- **§5 Ruhezeit**: `rest_time_service.check_rest_time_violations()` - nur Report (retrospektiv), kein Echtzeit-Check
- **§6 is_night_work**: `_is_night_work()` in `time_entries.py` - minutengenau, NIGHT_THRESHOLD_MINUTES=120, Mitternachtsuebergang korrekt
- **§6 Nachtarbeiter-Warn**: alle 6 Pfade (inkl. change-request-apply seit Migration 018)
- **§9/10**: is_sunday_or_holiday, SUNDAY_WORK/HOLIDAY_WORK, sunday_exception_reason - Samstag-Bug behoben (weekday==6)
- **§14 Wochenwarnung**: WEEKLY_HOURS_WARNING in 5 von 6 Pfaden (fehlt in change-request-apply)
- **§16**: Excel/ODS-Export, 2-Jahres-Purge-Schutz (730 Tage), DSGVO-Anonymisierung behaelt Zeiteintraege
- **§18**: exempt_from_arbzg bool auf User, alle Pfade korrekt

## Bekannte Luecken / Offene Findings

### MITTEL: §2/§6 - Inkonsistente Nachtzeit-Logik in reports.py
- `_is_night_work()` in `time_entries.py`: prazise, >120min Schwellwert, Mitternacht korrekt
- Lokale `is_night_work()` in `reports.py get_night_work_summary()`: vereinfacht `start < 06:00 OR end > 23:00` ohne 2h-Schwellwert
- Auswirkung: Fruhdienst 05:45 Uhr wird im Report als Nachtarbeit gezahlt, obwohl Validierung es nicht tut
- Fix: Import von `_is_night_work` aus `time_entries.py` in reports.py

### NIEDRIG: §14 - WEEKLY_HOURS_WARNING fehlt bei change-request-apply
- `admin.py review_change_request()` pruft §6-Nachtarbeiter, aber keine Wochenarbeitszeit
- §3-Hard-Stop (10h) ist korrekt implementiert
- Risiko gering, da §3 bei Antragserstellung bereits gepruft

### NIEDRIG: §3 Hard-Stop fehlt bei change-request-apply
- Bei Genehmigung eines Anderungsantrags wird kein erneuter §3-Hard-Stop gepruft
- Bereits bei Antragserstellung gepruft, aber Admin kann Werte andern

### UNVERAENDERLICH (systemisch): §4 Pausen-Timing (6h-Kontinuitaet)
- Start/Ende der Pause nicht gespeichert - nicht prufbar

## Report-Endpunkte (ArbZG)
- `GET /api/admin/reports/rest-time-violations` - §5 (konfigurierbares min_rest_hours)
- `GET /api/admin/reports/sunday-summary` - §11 15-freie-Sonntage
- `GET /api/admin/reports/night-work-summary` - §6 (vereinfachte Logik im Report!)
- `GET /api/admin/reports/compensatory-rest` - §11 Ersatzruhetag

## Migrationen ArbZG-relevant
- 016: sunday_exception_reason auf time_entries + exempt_from_arbzg auf users
- 017: is_night_worker auf users
- 018: (gleich wie 017 in Memory erwahnt, Migration 018 = is_night_worker)
- 020: deactivated_at auf users (DSGVO Grace-Period, indirekt §16)

## Arztpraxis-Kontext (Bayern)
- Feiertage: workalendar Germany Bavaria, automatisch synchronisiert
- §10-Ausnahme (Gesundheitswesen): sunday_exception_reason dokumentiert Ausnahmetatbestand
- §5 Abs. 2: MIN_REST_HOURS konfigurierbar (Kliniken/Pflegeeinrichtungen)
- is_night_worker: relevant fur Nacht-/Bereitschaftsdienste

## HTML-Report
- Pfad: `docs/specs/arbzg/arbzg-compliance.html`
- Letztes Update: 01.03.2026
- Struktur: Executive Summary + §2/3/4/5/6/9/11/14/16/18 + §7 + Praxis-Kontext + Matrix + Tests
