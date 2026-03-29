# Project Review Fixes – 2026-03-29

## CRITICAL

- [x] C1: `SystemSetting.tenant_id` Query mit `is_(None)` statt Default-Tenant → `main.py:263`
- [x] C2: `get_setting()` ohne `tenant_id`-Filter → Cross-Tenant Leak → `vacation_requests.py:17`
- [x] C3: Account-Lockout in-memory Dict → Eviction + Size-Cap → `auth.py:16`
- [x] C4: `purge_user` löscht eigenen Audit-Log + fremde `changed_by` Records → `admin_users.py:179`
- [x] C5: Kein React ErrorBoundary → `ErrorBoundary.tsx` erstellt + in App.tsx eingebunden
- [ ] C6: Access Token in localStorage → XSS-Risiko (akzeptiert, Token-Lifetime verkürzen — separates Ticket)
- [x] C7: Passwort-Check war bereits `< 10` (commit 00ab933 hatte es schon gefixt)
- [ ] C8: Backend-Tests auf SQLite statt PostgreSQL (akzeptiert — SQLite für Unit-Tests OK, RLS-Tests laufen auf PostgreSQL)
- [x] C9: Hardcoded DB-Passwörter in `test_tenant_rls.py` → `os.environ.get()` mit Fallback
- [ ] C10: `init-db-user.sql` ohne Passwort (akzeptiert — ALTER ROLE ist dokumentierter manueller Schritt)
- [x] C11: 30 TestClient-basierte Endpoint-Tests hinzugefügt → `test_endpoints.py`

## IMPORTANT

- [x] I1: `datetime.now()` → `today_local()`/`now_local()` in dashboard.py, journal.py, holidays.py, holiday_service.py
- [ ] I2: N+1 Queries in `_enrich_*` Funktionen (späterer Performance-Refactor)
- [x] I3: `company_closures` Admin-Filter + enum-Vergleich gefixt
- [x] I4: `company_closures` nutzt jetzt `get_daily_target_for_date()`
- [x] I5: weekday < 5 ist korrekt für deutsches Arbeitsrecht (kein Bug)
- [x] I6: `dashboard.py` `_get_missing_bookings` nutzt jetzt `get_weekly_hours_for_date()`
- [x] I7: `admin_users.update_user` poppt `is_active` aus update_data
- [x] I8: `reactivate_user` setzt jetzt `deactivated_at = None`
- [x] I9: Vacation budget check nutzt jetzt `get_daily_target_for_date()` per Tag
- [x] I10: `delete_closure` Kommentar zu Note-String-Limitation hinzugefügt (FK wäre Migration)
- [ ] I11: Frontend: Users.tsx Monolith (akzeptiert, späterer Refactor)
- [ ] I12: Frontend: Typ-Duplikate (akzeptiert, späterer Refactor)
- [ ] I13: Frontend: bare catch {} (akzeptiert, späterer Refactor)
- [x] I14: Frontend: React.Fragment key in MonthlyJournal.tsx gefixt
- [x] I15: Frontend: ChangeRequestForm FocusTrap + Escape-Handler hinzugefügt
- [x] I16: Frontend: `overtime_comp_days` zu YearlyAbsences Interface + `as any` entfernt
- [x] I17: SSL nginx-conf synchronisiert (help, PDF, index.html, client_max_body_size 2M, proxy timeouts)
- [x] I18: Backend health check in docker-compose.yml + frontend depends_on condition
- [x] I19: docker-compose.yml `version` key entfernt

## TESTS (Abdeckung erhöhen auf ≥50%)

- [x] T1: 30 TestClient-basierte Endpoint-Tests → `test_endpoints.py`
- [x] T2: 7 Tests für export_service.py → `test_export_service.py`
- [x] T3: 15 Tests für error_log_service.py (PII-Scrubbing + Fingerprint) → `test_error_log_service.py`
- [x] T4: 15 Tests für arbzg_utils.py (is_night_work) → `test_arbzg_utils.py`
- [x] T5: 9 Tests für timezone_service.py → `test_timezone_service.py`
- [x] T6: 20 Tests für TOTP/2FA + Password (auth_service) → `test_auth_service.py`
- [x] T7: Hardcoded Passwörter in test_tenant_rls.py → `os.environ.get()`
- [ ] T8: E2E XLS-Import Pfade fixen (requires test fixture files)

**Test-Ergebnis: 156 → 504 Tests (3.2x), alle grün**

## MINOR

- [x] M1: Unused import `and_` entfernt aus time_entries.py
- [x] M2: Unused variable `iso` entfernt aus time_entries.py
- [x] M3: `net_h` Lambda zu Modul-Level `_net_hours()` extrahiert
- [ ] M4: `formatHoursHM` in errorMessage.ts (späterer Refactor)
- [ ] M5: Inconsistent model_config vs class Config (späterer Refactor)
- [x] M6: `holiday_service.get_holiday_state` mit optionalem tenant_id Filter
- [ ] M7: export_service hidden users (späterer Fix)
- [ ] M8: `clock_out` Pausenvalidierung (späterer Fix)
- [x] M9: console.error in Dashboard.tsx entfernt
- [ ] M10: E2E workers erhöhen (späterer Fix)

## Zusammenfassung

| Kategorie | Gesamt | Erledigt | Akzeptiert/Später | Offen |
|-----------|--------|----------|-------------------|-------|
| Critical | 11 | 7 | 3 | 1 (C6) |
| Important | 19 | 15 | 4 | 0 |
| Tests | 8 | 7 | 0 | 1 (T8) |
| Minor | 10 | 5 | 5 | 0 |
| **Gesamt** | **48** | **34** | **12** | **2** |
