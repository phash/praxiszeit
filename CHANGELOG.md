# Changelog

## [1.2.0] - 2026-04-03

### Features
- **Überstundenausgleich korrigiert:** Soll bleibt bestehen, Ist = 0h — Überstundenkonto sinkt korrekt um Tagessoll
- **Absences mit Start-/Endzeit:** Abwesenheiten können optional Start-/Endzeit haben ("ganzer Tag" wenn leer)
- **Änderungsanträge für Abwesenheiten:** Mitarbeiter können Krank, Fortbildung, Urlaub etc. per CR beantragen (entry_kind="absence")
- **Journal Multi-Entry:** Tage mit mehreren Einträgen zeigen jeden Eintrag auf eigener Zeile mit Typ
- **Gemischte Tage:** Arbeitszeit + Absence am selben Tag korrekt dargestellt und berechnet
- **Admin CR-Filter:** User-Dropdown + Zeitraum-Filter (1M/3M/Jahr/Vorjahr/freier Zeitraum)
- **Echtzeit-Ruhezeitwarnung:** Warnung beim Einstempeln wenn <11h seit letztem Arbeitsende (§5 ArbZG)
- **Pausen-Mindestdauer:** Warnung bei Pausenabschnitten <15 Minuten (§4 Satz 2 ArbZG)
- **DSGVO sick_hours opt-in:** JSON-Reports maskieren Krankheitsdaten ohne explizites opt-in

### Bug Fixes
- CR-Approval Race Condition: Status wird erst nach Precondition-Checks gesetzt
- CR-Approval: Unique-Constraint-Check bei Datumsänderung
- CR-Approval: Nutzt jetzt CR-Tenant-ID statt Admin-Tenant-ID
- Absence-CRs: Duplikat-Prüfung für pending Anträge
- TimeEntry-CRs: Duplikat-Check für CREATE-Anträge repariert
- UPDATE-CRs: Zukunftsdaten blockiert, start >= end Validierung
- DELETE-CRs: Entry-Existenzprüfung vor Status-Änderung
- Journal: SICK-Tag nutzt daily_target statt absence_sum
- Journal: Absence-Ordering deterministisch (.order_by type)
- Mixed-Day: VACATION/OTHER/OVERTIME reduzieren Soll korrekt
- Mixed-Day: Absence-Erstellung löscht nicht mehr alle TimeEntries (keep_time_entries)
- Mixed-Day: Delete löscht nur gezielten Eintrag, nicht Absence
- Sick Absence: Nutzt historische weekly_hours statt aktuelle
- Cross-Year Vacation: Budget-Check pro Jahr statt nur Startjahr
- Overlapping Absences: Verschiedene Typen am selben Tag blockiert
- net_hours: Floor bei 0 (kann nicht negativ werden)
- Export: Mehrere TimeEntries pro Tag werden korrekt exportiert
- Export: Historische daily_target pro Tag statt statisch
- Export: "Überstundenausgleich" Label in Absence-Type-Maps
- Export: Night-Work-Days zählt unique Dates statt Entries
- Export: PDF zeigt non-sick Absence-Notes unabhängig von health_data Flag
- ODS: Überstundenausgleich-Spalte in Jahresübersicht ergänzt
- Reports: monthly weekly_hours nutzt historischen Wert
- Dashboard: Missing-Bookings-Query mit Datum-Untergrenze (Performance)
- Vacation-Approval: Historische weekly_hours + Cross-Year-Budget-Check
- User-Purge: VacationRequest FK-Bereinigung verhindert IntegrityError
- DSGVO: Kalender maskiert "sick" → "absent" für nicht-Admins
- Absence-Löschung: Audit-Log vor delete
- Alembic: version_num_width=128 verhindert Spalten-Overflow
- formatHoursSimple: Negative Werte korrekt dargestellt
- Admin 8h-Warnung: DAILY_HOURS_WARNING in Admin-Pfaden ergänzt
- Holiday-Service: is_holiday() mit optionalem Tenant-Filter
- Anonymisierung: Grace-Period Null-Check für Legacy-User

### Tests
- 343 Backend-Tests (vorher 275, +68 neue)
- Absence-Typ-Matrix: Parametrisierte Tests für alle 5 Typen
- Überstundenausgleich: 8 Tests (Soll/Ist, Tagesplan, Journal, kumulativ)
- Jahresabschluss: 8 Tests (Übertrag, Resturlaub, Mid-Year-Hire, Idempotenz)
- Mixed-Day: 4 Tests (Work+Training, Work+Sick, Work+Vacation, Work+Overtime)
- Absence-CRs: 8 Tests (Model, Zeiten, Approval, Journal-Integration)
- Berechnungs-Units: 13 Tests (Target, Actual, Balance, Vacation, Carryover)

### Security & Compliance
- 4 Runden Bughunting-Review (31 Bugs gefunden und gefixt)
- ArbZG-Audit: KONFORM (§2-§18 vollständig geprüft)
- DSGVO-Audit: KONFORM (Art. 5/6/9/15/17/20/25/32 geprüft)
- Security-Review: 0 kritische Schwachstellen

### Migration
- `030` — Absence start_time/end_time + Change Request absence fields (entry_kind, absence_id, proposed/original_absence_type/hours)

---

## [1.1.0] - 2026-03-26

- Multi-Tenant Phase 1-3 (RLS, Tenant-Modell, Auth-Middleware)
- VacationRequest absence_type Erweiterung

## [1.0.0] - 2026-02-14

- Initiales Release
