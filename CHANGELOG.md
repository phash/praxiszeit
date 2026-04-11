# Changelog

## [1.3.0] - 2026-04-11

**Großer Security-, Stability-, Performance- und UX-Review — 41 gezielte Fixes.**
362/362 Backend-Tests grün (inkl. 13 RLS-Integrationstests gegen echte
Postgres-DB), Frontend TypeScript + Vite-Build clean, ESLint 9 + flat
config installiert (0 Errors, 86 Legacy-Warnings für späteren Cleanup).

### 🔴 Security (CRITICAL + HIGH)
- **Access-Token raus aus `localStorage`** — Token lebt nur noch im
  Modul-Memory, Session-Recovery über HttpOnly-Refresh-Cookie beim
  App-Start. XSS-Steals-Session-Vektor geschlossen.
- **CSRF Double-Submit-Cookie** — neue `CSRFMiddleware`, nicht-HttpOnly
  `csrf_token` Cookie beim Login/Refresh, `X-CSRF-Token`-Header-Check
  auf allen unsafe Methods.
- **Hardcoded `PraxisZeit2025!` aus Installern entfernt** — PowerShell /
  `/dev/urandom` generiert zur Installationszeit ein Einmal-Passwort.
  `uninstall.bat` + neuer `restore-backup.template.bat` lesen
  `.db-credentials` statt Fallback zu verwenden.
- **`.env` Schutz** — neuer `pre-commit-hook.sh` blockiert `.env`-Commits
  (auch mit `-f`), `init-db-user.sh` lehnt schwache `APP_DB_PASSWORD` ab,
  Dev-`.env` auf zufällige Werte rotiert.
- **Multi-Tenant tenant_id-Filter** — `is_holiday()` + alle Bulk-Deletes
  + Admin-User-Lookups kriegen explizite `tenant_id`-Filter zusätzlich
  zu RLS. Neuer Helper `_get_user_in_tenant()` in `admin_users.py`.
- **Auth-Enumeration-Fix** — Dummy-bcrypt-Verify bei nicht-existenten
  Usern gleicht Timing aus, `_failed_logins` als OrderedDict-LRU mit
  O(1)-Eviction, `move_to_end()` hält legitime Opfer-Lockouts "heiß"
  gegen Attacker-Evict-Flood.
- **`bcrypt_sha256` statt bcrypt** — eliminiert die stillschweigende
  72-Byte-Trunkierung. Opportunistischer Re-Hash beim nächsten Login
  migriert Legacy-Hashes ohne User-Reset.
- **Ed25519-signierte Update-Manifeste** — `updater.py` verifiziert
  Manifest-Signatur vor Download-URL-Vertrauen + Host-Allowlist + HTTPS
  erzwungen. Trust-Root aus `license.py` wiederverwendet.
- **HSTS nur noch auf HTTPS** — verhindert Safari-Brick in Native-HTTP-
  Install.
- **GitHub-Issue-URL-Sanitizer** — `sanitizeGithubUrl()` blockt
  `javascript:`-URLs auf Admin-ErrorMonitoring-Seite.
- **`update_profile` Audit-Log** bei E-Mail-Änderungen.

### 🟠 Stability (HIGH)
- **`with_for_update()` auf CR/VR/Absence/TimeEntry Approval-Paths** —
  schließt Double-Click-Races bei `review_change_request`,
  `review_vacation_request`, `create_absence` (Duplicate-Probe) und
  `admin_update_time_entry`.
- **`create_year_closing` pg_advisory_xact_lock(42, hash(tenant,year))**
  + Pending-CR-Refusal.
- **`_close_stale_entry`** committet nicht mehr mitten im Request,
  schreibt `TimeEntryAuditLog(action="update", source="auto_close")` so
  dass §3 ArbZG-Verstöße vom Vortag nachverfolgbar sind.
- **clock-in §5 DST-Fix** — `datetime.combine(..., tzinfo=LOCAL_TZ)`
  statt naive, korrekte Wall-Clock-Rechnung auch bei Umschalttagen.
- **`get_weekly_hours_for_date` Bypass entfernt** — die zwei lokalen
  Shadow-Helpers in `calculation_service.py` gelöscht, authoritative
  Lookup mit optionalem `wh_changes=` Prefetch. Einziger Ort der
  `user.weekly_hours` direkt liest.
- **`company_closures.py:145`** reicht jetzt `weekly_hours` explizit durch.
- **`AbsenceType.OTHER` Semantik** dokumentiert + Pinning-Test
  `test_absence_type_other_reduces_target_and_ignores_actual`.
- **`vacation_requests.create` Validierung** auf Parität mit
  `create_absence` (Range, first/last_work_day, Dedup, Budget).
- **`get_vacation_account` Div-by-Zero-Fix** — früher Return mit
  `track_hours=False` Sentinel für Users ohne Zeiterfassung.
- **`xls_import_service.execute_import` try/except + rollback +
  Failure-Audit-Log** statt halbimportierter DB.

### 🟡 Performance
- **Migration 031 — Composite-Indexe** `(tenant_id, user_id, date)` auf
  `time_entries` und `absences`, `(user_id, effective_from)` auf
  `working_hours_changes`.
- **`net_hours` `@expression`** — `func.sum(TimeEntry.net_hours)` läuft
  jetzt auf SQL-Ebene (dialekt-portabel mit `CASE` statt `GREATEST`).
- **`date_in_year` / `date_in_month` / `date_in_year_up_to_month`** in
  neuer `services/date_filters.py`. **70+ non-sargable
  `extract('year'|'month', date)`-Sites** umgeschrieben in `reports`,
  `calculation_service`, `journal_service`, `export_service`,
  `ods_export_service`, `time_entries`, `admin_time_entries`,
  `absences`, `vacation_requests`, `rest_time_service`.
- **Reports `/yearly-absences` Bulk-Fetch** aller 5 Absence-Typen in
  einem Query statt N+1 per User per Typ.
- **Per-(tenant_id, year) Holiday-Cache** in `holiday_service` — 
  `is_holiday()` ist O(1) nach erstem Zugriff, Invalidierung auf
  `sync_holidays` / `delete_all_holidays`.
- **`db.close()` vor `StreamingResponse`** in allen 6 Export-Endpoints
  (Excel/ODS/PDF × monthly/yearly/yearly-classic) — keine Pool-
  Connection wird mehr während Download gehalten.
- **Audit-Log Cursor-Pagination** — neuer `before`-Query-Parameter
  (ISO-8601) als bevorzugter Modus, Legacy-Offset bleibt backward-compat.
- **`get_deletion_candidates` Single GROUP BY MAX(date)** statt N+1
  per-User-Lookup.

### 🎨 Frontend UX
- **Dashboard + TimeTracking Async-Cleanup** — `cancelled`-Flag-Pattern
  in allen useEffects, keine setState-after-unmount-Warnings mehr.
- **`formatHoursHM` NaN-Guard** + `parseHours()`-Helper. 5 Form-Sites
  (`UserForm`, `WorkingHoursModal`, `AbsenceCalendarPage`,
  `AdminAbsences`, `Reports`) migriert.
- **Toast-IDs via `crypto.randomUUID()`** — keine React-Key-Kollisionen
  bei Burst-Errors mehr.
- **Router-aware ErrorBoundary** (`key={location.pathname}`) — ein
  broken Page lähmt nicht mehr die ganze SPA.
- **PWA `registerType: 'prompt'`** + Confirm-Dialog statt silent reload
  beim Deploy.
- **`Layout.isActive`** highlighted Sub-Routes korrekt
  (`/admin/users/:id/journal` → "Benutzerverwaltung"-Nav-Entry).

### 🏗️ Infrastructure
- **`deploy.sh`** refuses dirty working tree, pre-migration `pg_dump` via
  `scripts/backup-db.sh`, automatischer `git reset --hard` + Rebuild bei
  Healthcheck-Failure, `PREVIOUS_COMMIT` als Rollback-Target gespeichert.
- **Backend multi-stage Dockerfile** — `gcc` und `postgresql-client` aus
  Runtime raus (nur Build-Stage hat sie). Python gepinnt auf
  `3.12.7-slim-bookworm`. Image ~200MB kleiner.
- **Prometheus + Grafana Image-Tags gepinnt** — `v2.54.1` / `11.2.0`.
- **Grafana provisioned Dashboards locked** — `editable: false`,
  `disableDeletion: true`.
- **`praxiszeit-server.py`** konfigurierbares `bind_address` (für
  127.0.0.1-only Deployments) + loud WARNING bei `0.0.0.0` ohne TLS.
- **ESLint 9 Flat Config** installiert (`eslint.config.js`) — 0 Errors,
  86 Legacy-Warnings. `scripts/local-ci.sh` wrappt Backend-Tests,
  TypeScript, ESLint, Vite-Build (und optional E2E) in eine Pipeline.
- **pre-commit Hook** (`scripts/pre-commit-hook.sh` +
  `scripts/install-git-hooks.sh`) blockt `.env`-Commits und
  `PraxisZeit2025!`-Referenzen.

### Breaking Changes / Migration Notes
- **Alembic-Migration 031** läuft automatisch beim nächsten
  `alembic upgrade head`. Erzeugt drei `CREATE INDEX` — keine Daten-
  migration.
- **APP_DB_PASSWORD**: Dev-`.env` auf zufälligen Wert rotiert. Bei
  bestehenden Docker-Volumes muss das DB-User-Passwort einmalig per
  `ALTER ROLE praxiszeit_app PASSWORD '<new>'` synchronisiert werden —
  oder Volume neu anlegen (neues `init-db-user.sh` setzt es dann
  automatisch).
- **SECRET_KEY**: Dev-`.env` rotiert. Existing-Sessions werden beim
  Restart ungültig — User müssen sich einmal neu einloggen.
- **Legacy bcrypt-Hashes** werden beim nächsten erfolgreichen Login
  automatisch auf `bcrypt_sha256` migriert — kein Passwort-Reset nötig.
- **CSRF-Token**: Frontend-Interceptor setzt den neuen Header
  automatisch. Dritt-Client-Integrationen (pure Bearer-API-Clients)
  sind nicht betroffen, die CSRF-Middleware prüft nur bei vorhandenem
  `csrf_token`-Cookie.
- **GitHub-Actions deaktiviert** (Repository-Level) während dieser PR.
  Vor Production-Release wieder aktivieren:
  `gh api repos/phash/praxiszeit/actions/permissions -X PUT --input - <<< '{"enabled":true}'`

### Documentation
- Ausführliche Sprint-Dokumentation in Commit-Message
- PR-Body mit gruppierten Fixes nach Priorität
- neue Migration-Notes für 1.3.0

## [1.2.1] - 2026-04-07

### Bug Fixes (Native Windows Installation)
- **psql -v Interpolation:** Variable-Substitution funktioniert nicht mit `-c` auf PostgreSQL 18.3/Windows — direkte SQL-Strings statt `-v`/`:'var'`
- **Python 3.13 Glob-Expansion:** `*` in subprocess-Argumenten wird auf Windows als Glob expanded — explizite Werte statt Wildcards
- **SYSTEM-Permissions:** `.db-credentials` war fuer NSSM-Service (SYSTEM-Account) nicht lesbar — `SYSTEM:(R,W)` hinzugefuegt
- **cp1252 UnicodeEncodeError:** Emoji-Output crasht im NSSM-Service — `PYTHONUTF8=1` fuer uvicorn-Subprozesse
- **Config-to-Env Bridge:** `SECRET_KEY`, `ADMIN_EMAIL` etc. fehlten als Env-Vars fuer Backend — TOML-Config-Werte werden in `cmd_start()` gesetzt
- **FRONTEND_DIR:** Relativer Pfad im Native-Modus falsch aufgeloest — absoluter Pfad via `APP_DIR / "frontend"`
- **LICENSE_KEY_PATH:** Relativer Pfad nicht auffindbar vom Backend-CWD — wird zu absolutem Pfad aufgeloest
- **SPA-Fallback 405:** Catch-All `@app.get("/{full_path:path}")` verursachte 405 fuer POST/PUT/DELETE API-Requests — ersetzt durch `SPAFallbackMiddleware`
- **Session-Verlust:** `SECRET_KEY` wurde bei jedem Restart neu generiert (alle JWTs ungueltig) — Key wird in `config/.secret-key` persistiert
- **cookie_secure ohne SSL:** Secure-Cookie bei HTTP-Verbindung vom Browser abgelehnt — `cookie_secure=false` fuer Nicht-SSL-Setups

### Documentation
- Neue Doku: `docs/NATIVE-WINDOWS-PITFALLS.md` — 10 Fallstricke mit Loesungen und Deployment-Checkliste
- CLAUDE.md um Native-Windows-Regeln erweitert

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
