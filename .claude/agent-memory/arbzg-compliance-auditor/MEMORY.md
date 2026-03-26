# ArbZG-Compliance-Auditor Memory

## Letzter Audit: 26.03.2026 (Vollaudit + Multi-Tenant Branch feat/multi-tenant-phase-1-3)

## Implementierungsstand

### Kernchecks und Dateien
- **§3 Hard-Stop (10h)**: `time_entries.py` create/update/clock_out + `admin.py` admin_create/admin_update + `change_requests.py` create
- **§3 Warnung (8h)**: Employee-Pfade ja; Admin-Pfade (admin_create/admin_update) kein DAILY_HOURS_WARNING (NIEDRIG)
- **§4 Pausenpflicht (Gesamtdauer)**: `break_validation_service.py` validate_daily_break() - alle 6 Pfade korrekt
- **§4 Lücken zählen als Pausen**: gap-Berechnung korrekt; ABER 15-Minuten-Mindestdauer je Lücke NICHT geprüft (HOCH)
- **§4 Satz 2 Fragmentierung**: `break_minutes`-Feld ist Summenwert, kein Segment-Check möglich (HOCH)
- **§5 Ruhezeit**: nur retrospektiv im Report; kein Echtzeit-Check beim Einstempeln (MITTEL)
- **§6 is_night_work**: `arbzg_utils.is_night_work()` importiert in ALLEN Reports/Routern korrekt (altes Finding "vereinfachte Logik in reports.py" ist überholt - reports.py nutzt arbzg_utils seit aktuellem Stand)
- **§6 Nachtarbeiter-Warn**: alle 6 Pfade korrekt inkl. change-request-apply
- **§9/10**: weekday==6 korrekt, SUNDAY_WORK/HOLIDAY_WORK, sunday_exception_reason
- **§14 WEEKLY_HOURS_WARNING**: in allen 6 Pfaden korrekt (inkl. change-request-apply in admin.py Zeile 691-702)
- **§16**: Excel/ODS/PDF-Export, 730-Tage-Purge-Schutz, DSGVO-Anonymisierung behaelt Zeiteintraege
- **§18**: exempt_from_arbzg bool auf User, alle Pfade korrekt

## Offene Findings (Stand 26.03.2026)

### HOCH: §4 Satz 2 - 15-Minuten-Mindestdauer je Pausenabschnitt nicht geprüft
- Lücken < 15min zwischen Zeiteinträgen werden als Pause gewertet (z.B. 10min-Gap wird für 30min-Gesamtpause gezählt)
- break_minutes=14 wird nicht abgelehnt (Feld ist Summenwert ohne Segment-Info)
- Fix: In break_validation_service.py gap-Schleife prüfen gap >= 15 min; deklarierte break_minutes: 0 oder >= 15
- Code: `break_validation_service.py` Zeile 65-69

### MITTEL: §5 - Kein Echtzeit-Check beim Einstempeln
- clock_in() und clock_out() prüfen keine 11h-Ruhezeit
- Nur Report-Pfad `rest_time_service.check_rest_time_violations()` prüft retrospektiv
- Empfehlung: Warnung (kein Hard-Stop) beim Einstempeln

### MITTEL: Frontend §4 - 9h-Fall fehlt in TimeTracking.tsx
- TimeTracking.tsx Zeile 255: nur >360min geprüft, nicht >540min (45min-Pflicht)
- Backend korrekt; nur UX-Mangel

### MITTEL: Feiertagskalender-Bugs (Multi-Tenant)
- `delete_all_holidays()` loescht ALLE Tenants Feiertage (kein tenant_id Filter)
- `sync_holidays()` prueft existing nur nach Datum, nicht tenant_id
- `sync_current_and_next_year()` aktualisiert h.name fuer ALLE Tenants

### MITTEL: §14/§3 - WEEKLY_HOURS_WARNING und DAILY_HOURS_WARNING fehlen in admin_create/admin_update
- admin.py admin_create_time_entry (Zeile 709ff) und admin_update_time_entry (Zeile 780ff) rufen _calculate_weekly_net_hours() nicht auf
- _calculate_weekly_net_hours() ist zwar importiert (admin.py Zeile 24), wird aber in diesen Pfaden nicht genutzt
- Hard-Stop 10h funktioniert; nur die Warn-Stufe fehlt

### MITTEL (systemisch): §16 - Tenant-Deaktivierung sperrt Zeitdaten-Zugriff
- tenant.is_active == False → HTTP 403 fuer ALLE User; Purge/Export unerreichbar
- Kein Notfall-Zugang fuer deaktivierte Tenants
- can_purge verwendet 730-Tage-Grenze korrekt (admin.py Zeile 169)

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

## Ueberholt / Korrigierte Findings
- §2/§6 Inkonsistenz reports.py: reports.py nutzt aktuell korrekt arbzg_utils.is_night_work() - altes Finding ungueltig
- §14 fehlt in change-request-apply: ist implementiert (admin.py Zeile 691-702) - altes Finding ungueltig
