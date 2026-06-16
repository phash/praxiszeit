# CLAUDE.md – PraxisZeit

**Repo:** https://github.com/phash/praxiszeit
**Stack:** React 18 + TypeScript + Tailwind / FastAPI (Python 3.12) + PostgreSQL 16
**Deployment:** Docker Compose (Entwicklung/Prod) ODER Native Installer (Kundenserver)
**Aktuelle Version:** 1.8.5 (Stand 2026-06-16)
**Lizenz/Updates:** ausgeliefert über [pzweb](https://github.com/phash/pzweb) — `praxiszeit.mr-development.de` (Shop) + `updates.mr-development.de` (Update-Server)

---

## Schnellreferenz

### Dev-Start
```bash
docker compose up -d          # Frontend :80, API-Docs :8000/docs
docker compose down
```

### Prod-Deployment (Docker)
```bash
ssh manuel@192.168.178.44 "cd /opt/praxiszeit/praxiszeit && sudo ./deploy.sh"
```
→ Details: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

### Native Installer (Kundenserver, ohne Docker)
```bash
bash tools/build-release.sh                    # Release-Pakete bauen (Linux/Windows/macOS)
bash tools/build-release.sh --linux-only       # Nur Linux
bash tools/build-release.sh --windows-only --skip-download   # Rebuild mit Cache
bash tools/build-release.sh --docker-only      # Nur Docker-Bundle (compose + Build-Kontext)
bash tools/validate-release.sh                 # Linux-Tarball: Docker-Smoke gegen 4 Distros
# macOS-Validierung läuft als GitHub-Actions-Workflow (validate-macos.yml)
# auf macos-15-intel + macos-14 — manuell triggerbar via gh workflow run.
```
**Build-Release-Frontend + Host-Node:** `build-release.sh` ruft intern `npm run build` (Schritt 3) — bricht mit Host-Node ≥26. Frontend vorher mit `docker run --rm -v $(pwd)/frontend:/app -w /app node:20-alpine sh -c "npm run build"` bauen und dann mit `--skip-frontend` releasen (`dist/` muss existieren).
**PostgreSQL-Quelle (ab 1.5.0):** `theseus-rs/postgresql-binaries` 16.13.0. Manylinux-Build, forward-kompatibel bis **glibc 2.34** (Ubuntu 22.04+, Debian 12+, RHEL/Rocky/Alma 9+, Fedora 35+). EDB-Tarbälle sind seit 2026-05 nicht mehr verfügbar (HTTP 403), System-PG-Fallback wurde entfernt (#125). Build bricht hart ab, wenn die Quelle nicht erreichbar ist oder glibc-Symbole > 2.34 verlangt werden. Linux- UND macOS-PG-Downloads sind SHA256-verifiziert (`download_with_sha`); macOS-Binaries werden nach dem `tar xzf` per `file(1)` als Mach-O verifiziert (1.5.2 Härtung — verhindert das 1.5.0-Pattern, bei dem nur das EDB-DMG ohne Binaries im Paket landete und der Build trotzdem "erfolgreich" war). `tools/validate-release.sh` (Linux) muss vor jedem Release grün sein. ⚠️ `validate-macos.yml` läuft auf dem PRIVATEN Repo NICHT (alle Runs hängen dauerhaft `queued` — keine macOS-Runner-Minuten; 1.8.1–1.8.4 wurden NUR auf Basis der lokalen `file(1)`-Mach-O-Prüfung ausgeliefert). NICHT auf den GH-Workflow warten; echtes macOS-initdb-Smoke ggf. manuell auf einem Mac.
Git Bash on Windows: `rsync`/`zip` fehlen → Script hat `tar`/PowerShell-`Compress-Archive`-Fallbacks.
PG Windows-Installer direkt: `https://get.enterprisedb.com/postgresql/postgresql-X.Y-Z-windows-x64.exe` (kein Webformular).
**Windows-Deps werden beim BUILD ins Bundle vorinstalliert** (1.5.1, `build-release.sh` Phase 5, analog Linux): `bin/python/Lib/site-packages` enthält die cp313-win_amd64-Wheels schon im Paket → Kunden-Install braucht KEINEN PyPI-Download. Früher install-zeitlich via `setup.bat`-pip — unzuverlässig (Netz/Timing) und sah auf Maschinen mit System-Python 3.13 deren User-Site → pip „bereits erfüllt" → NICHTS ins Bundle → Dienst (LocalSystem) findet alembic/uvicorn nicht → `ERR_CONNECTION_REFUSED`. Daher `PYTHONNOUSERSITE=1` beim pip + Import-Verify (Build & setup.bat).
**Windows-PG ≠ theseus:** `.exe`/`.zip` bündeln den **EDB-Installer** (`postgresql-installer.exe`, PG 18.x); die theseus-16-Binaries gelten nur für die Linux/macOS-Tarbälle.
**Build-Staging-Race:** Phase 2 kopiert `praxiszeit-server.py`/`app/` früh ins Staging — Code-Edits NACH Build-Start landen NICHT im Artefakt. Nach jeder Server-Änderung komplett neu bauen + im ZIP verifizieren (`zipfile` → register-Call/Deps prüfen).
**Version-Bump:** 3 Stellen + Lock — `backend/app/core/updater.py`, `tools/build-release.sh` Default, `frontend/package.json` (+ `cd frontend && npm install` für Lock). Build-Script validiert Consistency und bricht sonst ab. `frontend/package.json.version` landet als `__APP_VERSION__` im Footer (`Layout.tsx:345`) — ohne Bump zeigt die UI die alte Version (war 1.3.0 → 1.3.5 lang gedriftet).
**Build-Exit-Code 1 am Ende ist kosmetisch** (letztes `$BUILD_LINUX && cat <<EOF` liefert 1 bei `false`). Erfolg = `dist/praxiszeit-X.Y.Z-windows-x64.zip` existiert.
**Self-signed SSL-Cert generieren** (für lokale HTTPS-Tests): `python tools/generate-self-signed-cert.py` — Chrome ServiceWorker-Registrierung scheitert damit trotzdem (Issue #84).
→ Details: [docs/INSTALL-NATIVE.md](docs/INSTALL-NATIVE.md)

#### Cross-Platform Installer (1.4.0+, Avalonia/.NET 10)
Ab 1.4.0-alpha.1 (`7f10a4a`) gibt es zusätzlich einen GUI-Installer unter `installer/setup/`:
```bash
cd installer/setup
dotnet test                                    # 114 Tests (xunit + FluentAssertions)
dotnet build                                   # baut alle 3 Projekte (.NET 10)
dotnet publish src/PraxisZeit.Setup \
    -c Release -r win-x64 --self-contained \
    -p:PublishSingleFile=true                  # Single-File-Exe für eine Plattform
```
**Build-Dependency:** .NET 10 SDK (`dotnet --version` muss `10.x` zeigen).
**Solution-Struktur:**
- `src/PraxisZeit.Setup/` — Avalonia UI (WinExe, CommunityToolkit.Mvvm, Fluent-Theme)
- `src/PraxisZeit.Setup.Core/` — Plattform-Services (Orchestrator, Pip, Alembic, Config, Backup, DB)
- `tests/PraxisZeit.Setup.Core.Tests/` — Core-Unit-Tests
**Tracking-Issues:** [#79](https://github.com/phash/praxiszeit/issues/79) (Wizard-Pages) · [#80](https://github.com/phash/praxiszeit/issues/80) (Core Services) · [#81](https://github.com/phash/praxiszeit/issues/81) (Build Pipeline) · [#88](https://github.com/phash/praxiszeit/issues/88) (Meta)
**Config-Datei `C:\praxiszeit\config\praxiszeit.conf` NIEMALS mit Notepad editieren** — schreibt UTF-8 BOM, Python liest die erste Zeile als `﻿KEY=...` und bricht ab (F-053). VS Code oder `notepad++` mit UTF-8-ohne-BOM verwenden.

### Tests
```bash
cd e2e && npx playwright test                                    # E2E (114 Tests)
docker compose exec backend pytest tests/ -v                     # Backend Unit (343+ Tests)
docker compose exec backend pytest tests/test_tenant_rls.py -v   # RLS Integration (13 Tests)
docker compose exec backend pytest tests/test_cross_tenant_api.py -v  # App-Layer Tenant-Filter (F-026)
docker compose exec backend pytest tests/test_concurrency.py     # Postgres-only Race-Tests
cd frontend && npm test                                          # Vitest Utils-Tests
```
All-in-one: `bash scripts/local-ci.sh` (backend pytest split SQLite/Postgres, vitest, tsc, eslint, vite build, e2e).
Nach nginx.conf / Frontend-Änderungen: `docker compose build frontend && docker compose up -d frontend`
**Version-Smoke-Test:** `/api/health` liefert nur `{status, database}` — **keine Version**. Version steht in `/openapi.json`, im Frontend-Footer (nach Hard-Refresh), oder unter `/` (nur wenn `SERVE_FRONTEND=False`).

### E2E-Patterns (Playwright)
- **Locators in `<main>` scopen:** Hilfe-Sidebar dupliziert Handbuch-Tabellen + -Texte → strict-mode-Violations bei page-weiten Selektoren. `page.locator('main').getByText(...)`.
- **Werktag-Datum:** `weekdayFromNow(n)` aus `helpers/date.helper.ts` statt `daysFromNow(n)` für Absence/Vacation-Tests — `toISOString()` UTC-Rollover verschiebt sonst aufs Wochenende → "Keine gültigen Arbeitstage" 400.
- **`<select>`-Optionen:** `toBeAttached({ timeout: 10000 })` statt `toBeVisible()` — `<option>` in geschlossenem Select ist immer not-visible, der Wait greift sonst nie auf das fetch-populated-DOM.
- **DB-State-Tests (Vacation/Absence):** Unique-Note-Marker pro Test (`E2E-${Date.now()}-${random}`) im POST + `filter({ hasText: uniqueNote })` im Locator — sonst trifft `.first()` einen Leftover-Antrag bei seriellen Runs.
- **Cleanup-Fixtures:** `createTimeEntry`, `createAbsence`, `createChangeRequest`, `createVacationRequest` in `e2e/fixtures/test-data.fixture.ts` — alle tracken IDs + teardown-DELETE. NEUE state-erzeugende Tests sollen die Fixtures nutzen, nicht `employeeApi.post(...)` direkt.
- **XLS-Test-Fixtures:** `e2e/test-data/timerec_*.xls` (Januar + Februar 2026) wird im Repo committet, regenerierbar via xlwt im Backend-Container.

### Frontend-Component-Tests (Vitest + RTL)
- `vite.config.ts` test-block: `environment: 'jsdom'` + `setupFiles: ['./src/test/setup.ts']`.
- `src/test/setup.ts`: jest-dom matchers, afterEach-cleanup, **focus-trap-react Mock** (jsdom liefert 0×0 aus `getBoundingClientRect()` → `tabbable` rejected alle Nodes).
- Fake-Timer-Tests + click: `fireEvent.click()` statt `userEvent.click()` (userEvent's pointer-event-Delays racen mit `vi.advanceTimersByTime`).

### Dev-Workflow Fallstricke
- **`.env`-Drift:** Nach RLS-Umbau (Migration 027) braucht `.env` zusätzlich `APP_DB_USER`, `APP_DB_PASSWORD`, `ENVIRONMENT`, `CORS_ORIGINS` (siehe `.env.example`). Alte lokale `.env` ohne diese Vars → `docker compose up` failed mit `required variable APP_DB_PASSWORD is missing`.
- **Backend-Container ist gebaut**, kein Host-Volume: Nach Edits `docker compose cp <host-file> backend:/app/<path>` VOR `pytest`, sonst sieht der Container den alten Code. Für Prod-Änderungen: `docker compose build backend && docker compose up -d backend`.
- **Frontend `node_modules` ist root-owned** (im Image-Build erzeugt). Host-`npm install` failt mit EACCES. Pattern: `docker run --rm -v $(pwd)/frontend:/app -w /app node:20-alpine sh -c "npm install --silent && ..."`. `npx tsc --noEmit`, `npm run build` und `npm test -- --run` laufen damit OHNE `npm install` (Host-`node_modules` ist vorhanden); nur frische Container brauchen install.
- **Test-Stratifizierung:** Unit-Tests laufen gegen SQLite (conftest.py). RLS + echte `SELECT FOR UPDATE`-Races brauchen Postgres → `test_tenant_rls.py` + `test_concurrency.py` aus normalem pytest ausschließen (`--ignore=`). ⚠️ Ein nacktes `pytest tests/` OHNE diese `--ignore` cascaded ~26 Failures/Errors (`OperationalError`) — die Postgres-Files vergiften die geteilte SQLite-Engine für Folgetests. Immer beide `--ignore=` setzen oder `scripts/local-ci.sh` nutzen.

### Kritische Regeln
- `get_weekly_hours_for_date()` **immer** pro Tag – nie `user.weekly_hours` direkt
- Migrationen auf Host erstellen + committen **vor** Container-Rebuild
- Pydantic Response-Schemas: `float` statt `Decimal`
- nginx SPA vs. Static-Dir: `location = /route` VOR `location /` einfügen
- Stunden-Anzeige: `formatHoursHM()` aus `utils/errorMessage.ts` (H:MM, Overflow-safe)
- **ArbZG-Warnungen aus API-Responses:** immer über `showArbzgWarnings(toast, response.warnings)` aus `utils/arbzgWarnings.ts` (nicht einzelne `if includes(...)` Blöcke duplizieren)
- **Toast-Dauer:** Nicht hardcoden — `ToastContext` setzt severity-basierte Defaults (success 3s, error 8s, warning 6s, info 5s)
- **Tenant-Scope bei PublicHoliday:** Alle Queries mit `PublicHoliday.tenant_id == <tid>` filtern; User/Entry-Queries bereits durch RLS geschützt, Holidays werden aber oft standalone geladen
- **License-Enforcement ist Middleware:** `LicenseReadOnlyMiddleware` in `main.py` blockiert Schreib-Methoden bei abgelaufener Lizenz, plus `check_employee_limit()` in `create_user` (neue Writer-Endpoints automatisch mit abgedeckt — keine Per-Route-Dependency nötig)
- **Lizenz-Fehler dürfen den Dienst NICHT abschiessen** (ab 1.5.2): ein ungültiger/nicht verifizierbarer `license.key` (z.B. nach Key-Rotation) → **Read-Only** (Login + Export gehen, Stempeln/Anträge gesperrt), NICHT `sys.exit(1)`. Früher = Login-Totalausfall (niemand kam rein). Fehlermeldung sagt „Signatur passt nicht zum hinterlegten Schlüssel → neue Lizenz aus dem Shop", nicht das irreführende „corrupted/tampered".
- **Daily-Scheduler:** APScheduler in `main.py` startet täglich 03:00 die Lifecycle-Jobs (Vacation-Audit-Purge 730 Tage, Tenant-Suspend, Tenant-Deletion). Disabled im pytest-Mode via `PYTEST_CURRENT_TEST`.
- **Superadmin-Router:** `/api/superadmin/*` via `require_superadmin` (User ohne `tenant_id`) für §16-Notfall-Export deaktivierter Tenants
- Cross-Page Refresh nach Stempeln: `uiStore.notifyStampChange()` → `stampVersion` Effect
- Bulk-Deletes: `synchronize_session=False` + expliziter `tenant_id`-Filter
- **Überstundenausgleich:** Soll bleibt, Ist=0h (NICHT Soll reduzieren!)
- **Urlaub tagebasiert (Tagesprinzip §3 BUrlG, #156/#167):** 1 freier Arbeitstag = 1 Urlaubstag, Halbtag = 0,5 (`half_day` → 0,5 × Tagessoll). `get_vacation_account` zählt `Σ(Stunden ÷ Tagessoll-des-Tages)`, NICHT Stundensumme÷Ø-Tagessoll. Budget-Check tagebasiert. Anspruch anteilig `30 × Arbeitstage/5`.
- **⚠️ Abwesenheiten entstehen an ZWEI Stellen** — `create_absence` (Direkt-Buchung) UND `admin_vacations.review_vacation_request` (Antrags-Genehmigung). Voll-Tag-Typen buchen das **Tagessoll des Tages** (nicht Client-/`vr.hours`, die den 8h-Default tragen), nur `OVERTIME` behält explizite Stunden. Tagessoll-Buchung, Tagesprinzip und `half_day` müssen in **beiden** Pfaden gepflegt werden.
- **Betriebsferien-Teilnahme über `receives_company_closures` (Bool, Default True), NICHT über die Rolle (#189):** `company_closures.py` filtert die betroffenen MA an allen 3 Stellen (list/create/update) über `User.receives_company_closures == True`. Ein Admin, der zugleich als Mitarbeiter geführt wird, nimmt so teil; reine Verwaltungs-Accounts kann man per Flag abwählen. Checkbox im `UserForm`. NIE wieder auf `role != ADMIN` zurückbauen.
- **Leitende Angestellte = `track_hours=False` (#191):** keine Soll/Ist-Stundenzählung, sonst wie normale MA. `get_vacation_account` zählt Urlaub/Krank auch bei `daily_target==0` **tagebasiert** (1 VACATION-Tag = 1 Tag, Sondertage = 1 Tag), Stunden bleiben 0; Budget behält Pro-rata + Carryover. Halbtage zählen ohne Stundenzählung als voller Tag (Limitierung). Edit-Pfad-Budget-Check tagebasiert (#196 behoben). ⚠️ Jahresabschluss-Carryover (`admin_carryovers.py`) für untracked noch offen (#191).
- **Arbeitszeit-Fenster (#201):** Pro MA je Wochentag optionale `scheduled_start_<wd>`/`scheduled_end_<wd>`. Tenant-Setting `work_window_grace_minutes` (Default 15). `work_window_service.clamp(...)` kappt Start/Ende auf `[Soll-Beginn − Puffer, Soll-Ende + Puffer]`; Rohstempel in `raw_start_time`/`raw_end_time` erhalten (§16). `net_hours`/Salden rechnen mit der **gekappten** Zeit. Eingehängt an **allen** Schreibpfaden: `clock_in`, `clock_out`, `create/update_time_entry`, `admin_time_entries`, XLS-Import, CR-Genehmigung. Übersprungen bei `track_hours=False`; `§18/exempt_from_arbzg`-MA werden **trotzdem** gekappt (Anwesenheits-Policy). Opt-in: ohne gesetzte Soll-Zeiten kein Verhaltenswechsel.
- **Soll respektiert Eintritt/Austritt (#193):** `_within_employment_window(user, d)` in `calculation_service.py` schließt Tage vor `first_work_day` / nach `last_work_day` vom Soll aus — Guard in **drei** Per-Tag-Schleifen (`get_monthly_target`, `get_overtime_account` innere Schleife, `get_ytd_summary`). Bei weiteren Per-Tag-Regeln (vgl. #146) alle drei pflegen. **Ist-Seite ebenfalls gefenstert (#195 behoben):** `get_monthly_actual`/`get_overtime_account`/`get_ytd_summary` filtern auch `TimeEntry`+credited über `_within_employment_window` → keine Phantom-Überstunden bei Einträgen außerhalb des Fensters. Optionaler Tech-Debt: gemeinsamer Per-Tag-Helper statt der 6 Filterstellen.
- **`/api/settings` (public, no-auth) liefert `special_days` (#188)** für den Default-Tenant, damit der Kalender (auch MA) 24./31.12. als frei/Halbtag markieren kann (`getSpecialDayInfo` in `utils/specialDays.ts`). Admin-Pendant: `/admin/settings/special-days`. Hardcoded Default-Tenant → bei SaaS-Cutover (#100) mit-umbauen.
- **Admin-Benutzerübersicht: `GET /api/admin/users-overview` (#194)** liefert Urlaub + JTD-Überstunden je MA in EINEM Call (ersetzt Frontend-N+1), `require_admin` + F-026, gleiche `include_inactive/include_hidden`-Filter wie `list_users`.
- **In-App-Hilfe/Handbuch ist hardcoded** in `frontend/src/components/DocViewer.tsx` (`handbuchMitarbeiterSections`/`handbuchAdminSections`), NICHT aus `docs/handbuch/*.md` geladen → bei nutzersichtbaren Doku-Änderungen BEIDES pflegen.
- **Absence-Typ-Matrix:** Siehe `docs/BACKEND-ARCHITEKTUR.md` → Berechnungsmodell
- **CR-Approval:** Precondition-Checks VOR Status-Änderung (Race-Condition-Fix)
- **Absence-CRs:** MA können Abwesenheiten per Änderungsantrag beantragen (entry_kind="absence")
- **Absences Start/End:** Absences haben optionale `start_time`/`end_time` (NULL = ganzer Tag)
- **DSGVO Art.9:** Kollegen-Feeds (`/absences/calendar` UND `/absences/team/upcoming`) maskieren `_MASKED_ABSENCE_TYPES = {SICK, OTHER, PAID_LEAVE}` → `"absent"` für nicht-Admins (Fremd-Einträge). Nur-SICK-Masking ist ein Leak (`"absent"` wäre 1:1-Krankheits-Indikator) — beide Feeds müssen dieselbe Konstante nutzen.
- **§5 ArbZG:** Echtzeit-Ruhezeitwarnung beim Einstempeln (<11h seit letztem Arbeitsende)
- **net_hours Floor:** Kann nicht negativ werden (max(0, ...))
- **Export Multi-Entry:** Mehrere Einträge pro Tag werden korrekt exportiert
- **Native-Modus:** `SERVE_FRONTEND=True` → FastAPI liefert Frontend (nginx entfällt), `False` (Default) = Docker
- **Native Windows-Fallstricke:** Siehe `docs/NATIVE-WINDOWS-PITFALLS.md` (psql -v, Glob-Expansion, SYSTEM-Permissions, cp1252, SPA-Routing)
- **setup.bat `DisableDelayedExpansion`:** Absicht (PowerShell-Passwort mit `!`). `%VAR%` in `(...)`-Blöcken wird beim Block-Parse substituiert → leere Vars erzeugen Syntax-Fehler (`if  GEQ 16`). Defaults vor dem Block setzen.
- **setup.bat PG-Reuse:** Existierende PG-Installation (Registry `HKLM\SOFTWARE\PostgreSQL\Installations` + `%ProgramFiles%\PostgreSQL\{14..18}`) wird bei Major ≥ 16 per `mklink /J` verlinkt statt neu installiert. `rd /s /q` folgt Junctions nicht → `uninstall.bat` bleibt sicher.
- **setup.bat `--install_runtimes 1` (ab 1.5.3):** Der EDB-Installer MUSS die Microsoft Visual C++ Runtime mitinstallieren — die PG-18-Binaries sind MSVC-gebaut (`vcruntime140*.dll`). Stand früher auf `0` → auf frischem Windows OHNE vorhandenen VC++-Redist schlug `initdb.exe` sofort mit Exit `3221225781` = `0xC0000135` (`STATUS_DLL_NOT_FOUND`) fehl und der NSSM-Dienst loopte endlos (Feldreport 2026-05-26, GH-Pitfall #11). Server-seitig übersetzt `_check_pg_launchable()` in `praxiszeit-server.py` diese NTSTATUS-Codes jetzt in eine klare Meldung statt opakem Traceback. Sofort-Workaround für Bestands-Installs: `https://aka.ms/vs/17/release/vc_redist.x64.exe` als Admin + `net start PraxisZeit`. KEINE Klammern in den REM-Kommentaren im `()`-Block von setup.bat (unbalancierte Klammern beenden den Block vorzeitig).
- **Update-Pfad VC++-Härtung (ab 1.5.4):** `setup.bat --install_runtimes 1` deckt nur die Erstinstallation ab — ein In-Place-Update (`update-wizard.ps1`, auch der `setup.exe`-Update-Modus via `-Headless`) startet den EDB-Installer NICHT. Daher bündelt `build-release.sh` jetzt `bin/vc_redist.x64.exe` und `update-wizard.ps1` führt es in `Step-VcRedist` idempotent aus (`/install /quiet /norestart`, Exit 0/1638/3010/1641 = OK), best-effort/nicht-fatal vor dem Service-Start. Für Bestands-Installs unkritisch (die liefen schon = Runtime da), schützt aber Maschinen ohne Runtime.
- **Windows: PostgreSQL läuft als eigener NetworkService-Dienst** (`pg_start` → `pg_ctl register -U "NT AUTHORITY\NetworkService"`), NICHT als Kindprozess — `postgres.exe` verweigert den Start unter dem LocalSystem-Token des NSSM-Dienstes. Unix: `pg_ctl start` (Kind) ok. `pg_ctl register` akzeptiert NUR `-N -D -U -P -S -e -W -t -s -o` (kein `-l`, kein lowercase `-w`).
- **NetworkService braucht Schreibrecht auf `data\db` UND `logs\`** — `postgresql.log` (logging_collector) liegt in `logs\`. Ein Update kann diese ACL zurücksetzen → `FATAL: could not open log file … Permission denied` → PG startet nicht (hat eine Produktion lahmgelegt, 1.5.x). `pg_start` (Windows) grantet beides jetzt vor jedem Start idempotent (`icacls … *S-1-5-20 …`). Recovery bei Bestands-Installs: `icacls C:\PraxisZeit\logs /grant "*S-1-5-20:(OI)(CI)F" /T`. PG-Start-Timeout ist 60s (error-487/ASLR-Retries auf manchen Maschinen).
- **Cluster-Marker `.praxiszeit-cluster`:** `pg_init` schreibt ihn in PGDATA. Daten-Dir OHNE Marker + ohne `.db-credentials` = fremd (EDB-Leftover) → wird zur Seite verschoben (`db.foreign-<ts>`, NIE gelöscht) + neu initialisiert; Bestands-Cluster mit Creds bekommen den Marker per Backfill.
- **Recovery bei verlorener `.db-credentials` (Native):** Marker da + Creds weg = scram-Cluster ohne Passwort → `cmd_start` failt fast mit Verweis auf `docs/INSTALL-NATIVE.md` Abschnitt "Disaster Recovery" (NIEMALS einfach `pg_setup_database` darauf loslassen — hängt/scheitert opak). Drei Pfade dort: (A) `.db-credentials` aus Backup zurückspielen, (B) `pg_dumpall` solange Cluster noch antwortet + `rm -rf data/db` + neu starten + restore, (C) nur Marker `data/db/.praxiszeit-cluster` entfernen → Quarantäne-Branch greift, altes Verzeichnis bleibt als `data/db.foreign-<ts>` erhalten. Tests: `test_native_pg_lifecycle.py::TestLostCredentialsFailFast`.
- **Migrationen NICHT via `python -m alembic`:** in `app/backend` liegt ein `alembic/`-Verzeichnis → cwd-Shadowing (`No module named alembic.__main__`). Programmatisch: `python -c "from alembic.config import main; main([...])"` + Retry.
- **psql/pg_dump immer mit `-w`:** sonst Endlos-Hänger an der Passwort-Abfrage im Dienst-/Headless-Kontext statt sauberem Fehler.
- **Robocopy im Update-Wizard merged ohne Purge:** stale Files in `bin/python/Lib/site-packages/` kumulieren über Updates hinweg. `Step-PipInstall` bootstrappt pip deshalb via `get-pip.py --force-reinstall` VOR `pip install -r requirements.txt` (F-056). Gleiches Pattern wenn weitere `bin/`-Subdirs im Wizard behandelt werden.
- **Nach Native-Update:** im Browser Hard-Refresh (`Ctrl+F5`) oder Service-Worker unregister, sonst bleibt das alte Frontend-Bundle im Cache.
- **SPA-Fallback:** Middleware statt catch-all Route! `@app.get("/{full_path:path}")` verursacht 405 für POST/PUT/DELETE
- **SECRET_KEY persistieren:** Muss in `config/.secret-key` gespeichert werden, sonst Session-Verlust bei Restart
- **cookie_secure:** Muss `false` sein ohne SSL, sonst lehnt Browser das Refresh-Cookie ab
- **Subprocess `*` verboten:** Python 3.13/Windows expanded `*` als Glob in subprocess-Args → explizite Werte nutzen
- **PYTHONUTF8=1:** Immer für uvicorn-Subprozesse setzen (cp1252-Crashes bei Emojis)
- **APP_VERSION:** Backend-SoT in `app/core/updater.py`; Frontend-Footer liest `__APP_VERSION__` aus `frontend/package.json.version` (via vite `define`). Beide + `tools/build-release.sh` Default müssen synchron bleiben — Build-Script enforced das.
- **Lizenz-Public-Key: MEHRERE akzeptieren, NIE hart rotieren** — `backend/app/core/license.py` hält ab 1.8.0 eine **Liste** `_PUBLIC_KEYS_PEM` (NEU `…t8zaDoRf…` zuerst, dann ALT `…B5ZiJro…`); `validate_license`/`validate_license_quiet` probieren jeden Key, akzeptieren bei erster gültiger Signatur. So bleiben Bestandslizenzen (alt-signiert, z.B. „Praxis Klotz-Roedig") UND neue Shop-Lizenzen gültig. **REAL passiert (1.5.x):** harte Rotation `…B5ZiJro…`→`…t8zaDoRf…` entwertete eine Produktiv-Lizenz → Read-Only (früher `sys.exit(1)` → Login-Totalausfall). Neue Keys IMMER vorne ergänzen, alte NIE entfernen (sonst wieder ungültig). ⚠️ **Drei Stellen synchron halten:** `_PUBLIC_KEYS_PEM` (Python) + `PublicKeysPem[]` in `installer/setup/.../LicenseValidator.cs` (GUI-Installer, war bis 1.8.0 auf dem ALTEN Key allein → „beschädigt/manipuliert"-Fehlmeldung) + `_PUBLIC_KEY_PEM`-Alias (= `[0]`, von `updater.py` als Manifest-Trust-Root genutzt). Privater Key offline bei Manuel. license.key wird BOM-tolerant gelesen (`utf-8-sig`).
- **Beta-Phase: Lizenzprüfung AUS (`BETA_MODE`, ab 1.8.0)** — `backend/app/config.py:BETA_MODE` (Default **True**) gated den kompletten Lizenz-Block (`main.py` Schritt 7) → **keine Lizenz nötig, kein Read-Only, kein MA-Limit**. `/api/system/info` liefert `beta`; Frontend zeigt ein **BETA-Badge** (`BetaBadge.tsx`/`systemStore.isBeta()`). Installer fragen NICHT mehr nach Lizenz (Linux-Prompt entfernt, Windows-Wizard entkernt, macOS hatte keinen). `feedback.py` erlaubt Bug-Reports in der Beta (`license_id="beta"`). ⚠️ **Vor dem ersten kostenpflichtigen Release `BETA_MODE=False`** — `build-release.sh` warnt laut, solange True. Reversibel: Lizenz-Code bleibt erhalten.
- **`_ALLOWED_UPDATE_HOSTS` in `backend/app/core/updater.py`** enthält ab 1.5.0 sowohl `updates.mr-development.de` als auch `praxiszeit.mr-development.de`. Vor dem Entfernen eines Hosts MUSS mindestens eine Version durchgelaufen sein, die die ersetzende Domain bereits kennt (Henne-Ei). `updates.praxiszeit.de` ist Platzhalter, falls die eigene Domain irgendwann live geht.
- **Native-Build verlangt `pg_env()`-Helper** in `praxiszeit-server.py` — alle 7 PG-Subprocess-Aufrufe (initdb, postgres, pg_ctl, psql, pg_dump) bekommen `env=pg_env()`, das `LD_LIBRARY_PATH=$BIN_DIR/postgresql/lib` (Linux/macOS) bzw. `PATH`-Prepend (Windows) setzt. Plus `PGHOST` auf `DATA_DIR/run/`, damit psql den umgezogenen Socket findet.
- **`unix_socket_directories` in `pg_init()`** muss auf `DATA_DIR/run/` zeigen (nicht `/var/run/postgresql`), weil systemd `ProtectSystem=strict` das default Verzeichnis read-only macht. Detail-Postmortem in #125.
- **`installer/linux/install.sh` installiert Runtime-Libs automatisch** (`libxml2 libssl3 libgssapi-krb5-2 libzstd1 liblz4-1 libreadline8 libbrotli1` via apt-get/dnf/zypper). Auf Ubuntu-Minimal-Images sind die nicht alle da, theseus' postgres-Binary linkt aber dagegen.
- **`install.sh` / systemd-Unit (Debian-Cloud-Härtung, ab 1.8.0):** Native-Service läuft als **non-root** (`User=<svc>`, `NoNewPrivileges=yes`). Privilegierte Ports (<1024, z. B. 443) → `install.sh` vergibt für `PORT < 1024` automatisch `AmbientCapabilities=CAP_NET_BIND_SERVICE` + `CapabilityBoundingSet=…` (sonst `bind … permission denied`, Feldreport). Tägliches Backup läuft jetzt über einen **systemd-Timer** (`praxiszeit-backup.timer/.service`) statt `crontab` — cron fehlt auf Minimal-Images (Debian-13-Cloud: `crontab: command not found`). Zusätzliche Hardening-Direktiven in der Unit (`ProtectKernel*`, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `RestrictNamespaces` …) — `RestrictAddressFamilies` muss `AF_UNIX` enthalten (PG-Socket in `DATA_DIR/run/`). Linux-/macOS-Tarball entpackt **flach** (`build-release.sh`: `tar -czf … -C "$DIR" .`, kein Top-Level-Ordner) → `INSTALL-NATIVE.md` extrahiert deshalb mit `-C <ordner>`. ⚠️ `validate-release.sh` + `validate-macos.yml` setzen das flache Layout voraus (`cd /opt/pz && tar xzf …`) — Tarball-Struktur NICHT auf Top-Level-Ordner umstellen, ohne beide Validatoren anzupassen.
- **Docker-Bundle (ab 1.8.0):** `build-release.sh --docker-only` baut `praxiszeit-<version>-docker.tar.gz` (Top-Level-Ordner!) mit compose-Dateien + `.env.example` + `generate-secrets.sh` + Build-Kontext (`backend/ frontend/ ssl/ prometheus/ grafana/`). Native-Tarbälle enthalten KEIN compose (Braumann-Feedback). ⚠️ Der `-docker`-Name passt NICHT ins strikte pzweb-Upload-Regex (`linux-x64|macos-x64|macos-arm64|windows-x64`) → gehört an ein **GitHub-Release**, nicht in den pzweb-Shop. Doku: [docs/INSTALL-DOCKER.md](docs/INSTALL-DOCKER.md). `ssl/`-Copy im Build excludet `cert.pem`/`key.pem` (kein Build-Host-Key im Bundle).
- **Native-Install — Host-Grenzen (1.8.0):** (a) **Rolling-Distros** (Arch/CachyOS): theseus-PG braucht `libxml2.so.2`, Arch ab libxml2 2.14 liefert nur `libxml2.so.16` → PG lädt nicht. `install.sh` hat `pacman`-Support + klaren Fail-Fast statt Crash-Loop; echter Bundle-Fix offen (#177). (b) **Vorhandene System-PostgreSQL auf :5432** (#174, **behoben 1.8.5**): Der native Cluster ist auf Unix jetzt **socket-only** (`pg_init` schreibt `listen_addresses=''`), Verbindung über den eigenen Unix-Socket in `DATA_DIR/run` via `_database_url()`; `pg_is_running()` probt den **eigenen Socket** statt TCP `localhost:5432`. Dadurch kollidiert nichts mehr mit einer fremden System-PG auf :5432 (auf .131 e2e verifiziert, inkl. scram-Bestandsclustern → Update-sicher). **Windows unverändert** (kein Unix-Socket → bleibt TCP `localhost:5432`). ⚠️ Bei Änderungen am PG-Start/Connect immer **drei** Stellen zusammen pflegen: `pg_is_running()` + `_database_url()` + `pg_init`-`listen_addresses`.
- **Alembic Revision-IDs:** Max 32 Zeichen (`version_num varchar(32)` Limit)
- **clock_out `with_for_update`:** `_get_open_entry()` in `clock_out` MUSS mit Lock aufgerufen werden (Race Condition bei Doppelklick)
- **F-026 Tenant-Filter (belt-and-suspenders):** ALLE `db.query(Model).filter(...)` auf tenant-scoped Tabellen brauchen expliziten `Model.tenant_id == current_user.tenant_id` zusätzlich zu RLS — gilt für list, lookup-by-id UND `.delete()`. Helper für User-Lookup: `_get_user_in_tenant()` in `admin_users.py`. Tests in `test_cross_tenant_api.py`.
- **Absence Unique Constraint:** `(user_id, date)` muss eindeutig sein — DB-Constraint oder `with_for_update()` bei Duplikat-Check
- **is_holiday() tenant_id:** Immer `tenant_id=current_user.tenant_id` übergeben (Multi-Tenant-Pflicht)
- **`time_entry_audit_logs.source` UND `action` sind `varchar(40)`** (Migrationen 037 bzw. 044). Neue Marker müssen <40 Zeichen sein, sonst 500 beim INSERT (`StringDataRightTruncation`) — **SQLite-Tests fangen das NICHT** (ignorieren varchar-Länge), gegen Prod-DB-Kopie / Postgres prüfen. Source-Werte u. a.: `manual`, `import`, `change_request`, `vacation_request_cancel`, `break_waiver`, `dsgvo`, `license_startup`.
- **`backend/create_handbuch_testdata.py`** ist multi-tenant-aware: ruft `set_superadmin_context(db)` auf + setzt `tenant_id=TENANT_ID` an User/TimeEntry/Absence/ChangeRequest. Wer das Script forkt für andere Seed-Daten muss beides mitnehmen, sonst RLS-Violation beim INSERT.
- **Container-File-Updates aus fremdem cwd:** `docker compose cp` resolved Host-Pfade **relativ zum cwd**. Aus `e2e/` heraus → `lstat e2e/backend/...: no such file`. Lösung: `docker cp <host-abs-path> praxiszeit-backend-1:/app/<path>`.

### pzweb-Integration (ab 1.5.0)

Lizenzen und Updates werden zentral über [pzweb](https://github.com/phash/pzweb) verkauft und ausgeliefert (`praxiszeit.mr-development.de` + `updates.mr-development.de`).

**Release-Workflow** (Detail-Checkliste in praxiszeit#124):
1. Version-Bump in `backend/app/core/updater.py`, `frontend/package.json`, `tools/build-release.sh` — alle drei synchron, Build-Script enforced das.
2. `bash tools/build-release.sh` — vier OS-Tarbälle in `dist/`.
3. `bash tools/validate-release.sh` — Docker-Smoke gegen Ubuntu 22.04/24.04, Debian 12, Rocky 9. Failt eine Distro = Tarball nicht freigabefähig.
3b. macOS: ⚠️ `validate-macos.yml` läuft auf dem Private-Repo NIE (Runs bleiben `queued`, kein Runner springt an). Verlass dich auf die lokale Mach-O-`file`-Prüfung im Build (`build-release.sh` Schritt 6); optional manuelles initdb-Smoke auf echtem Mac. (Workflow erst nutzbar mit Self-hosted-Runner / macOS-Minuten / public Repo.)
4. Im pzweb-Admin (`https://praxiszeit.mr-development.de/admin/releases/neu`): Release anlegen, vier Artefakte hochladen, veröffentlichen.
5. Smoke: `curl 'https://updates.mr-development.de/v1/check?version=1.4.4&os=linux'` muss signed manifest mit `latest=<neue Version>` liefern.

**Filename-Pattern (strict regex im pzweb-Backend):**
`praxiszeit-<version>-(linux-x64|macos-x64|macos-arm64|windows-x64).(tar.gz|zip)` — Tippfehler ⇒ 422 beim Upload.

**Manifest-Signatur** (im Code in `app/core/updater.py:_verify_manifest_signature`):
JSON-Body über `sort_keys=True, separators=(",",":")` kanonisiert, mit Ed25519 signiert, base64-encoded ins `signature`-Feld. Veränderung beliebigen Feldes invalidiert die Signatur.

**Verwandte Issues:** #124 (Release-Prozess), #125 (Build-Bug postmortem, geschlossen), #84 (PWA-SW + self-signed cert).

### Multi-Tenant
- **SaaS-Roadmap:** Meta-Issue [#100](https://github.com/phash/praxiszeit/issues/100) trackt 8-Phasen-Umbau (Phase 0 fertig in PR #91). On-Prem bleibt single-tenant via geplantem `DEPLOYMENT_MODE`-Schalter (Issue #92).
- **Jede neue Tabelle** braucht `tenant_id` FK + RLS-Policy + Eintrag in Migration
- **Neue Endpoints:** `set_tenant_context(db, tid)` oder `set_superadmin_context(db)` aufrufen
- **Neue Sessions** (`SessionLocal()` direkt): RLS-Kontext setzen, sonst 0 Rows!
- **DB-User:** App = `praxiszeit_app` (RLS enforced), Migrations = `praxiszeit` (Superuser)
- **JWT:** `tid` Claim enthält tenant_id, Middleware validiert gegen DB
- Default-Tenant UUID: `00000000-0000-0000-0000-000000000001`
- **SaaS vs. On-Prem:** `DEPLOYMENT_MODE=onprem|saas` (Default `onprem`). `app/core/deployment.py` → `is_saas()/is_onprem()`. Startup-Bootstrap (Default-Tenant, Admin, Holidays) läuft nur im `onprem`-Modus; im `saas`-Modus werden Tenants via Phase-3-Signup erzeugt.
- **JSONB-Spalten:** Model-seitig `JSON().with_variant(JSONB(), "postgresql")` (z. B. `tenants.billing_address`), sonst crasht SQLite-Test-Suite mit `can't render element of type JSONB`.
- **Billing-Felder:** `tenants` hat `plan | subscription_status | trial_ends_at | seat_limit | stripe_customer_id | stripe_subscription_id | billing_email | company_name | vat_id | country | billing_address`. PATCH `/api/tenant/billing` erlaubt nur die Adresse-Sub­menge — `plan`/`stripe_*`/`seat_limit` sind webhook/superadmin-owned.

### Standard-Benutzer (Dev)
- Admin: `admin` / `Admin2025!`
- Mitarbeiter: `manuel@klotz-roedig.de`

### Claude-Code-Bash-Gotchas
- Das `cd` in einem Bash-Aufruf **persistiert** zwischen Tool-Calls. Nach `cd .claude/worktrees/...` ist `git status` ohne erneutes `cd` immer noch im Worktree. Bei git-Operationen lieber `git -C <pfad>` nutzen oder cwd explizit zurücksetzen.
- `docker compose cp <host-file> <svc>:<container-path>` resolved den Host-Pfad **relativ zum cwd**, nicht zum Repo-Root. Aus fremdem cwd → `docker cp` mit absoluten Pfaden + Container-Name (`praxiszeit-backend-1`).
- `docker compose cp` braucht den **Service-Namen** (`backend:`), NICHT den Container-Namen (`praxiszeit-backend-1:` → schlägt still fehl, kopiert nichts). Ganzes Verzeichnis geht: `docker compose cp backend/app backend:/app/` (→ `/app/app`).
- **Fish-Shell:** mehrzeilige `while`/`for … end`-Schleifen scheitern im Tool-Eval (`parse error near 'end'`) — Einzeiler nutzen oder auf `Monitor`/`run_in_background` ausweichen.
- **Commit-/PR-/Issue-Texte mit Sonderzeichen** (Klammern, `→`, Umlaute) brechen bei inline `-m`/`-c` (Shell-Splitting) → `git commit -F -` bzw. `gh pr/issue ... --body-file -` mit Heredoc (`<<'EOF'`) nutzen — Heredocs funktionieren zuverlässig.

## Weiterführende Docs

| Thema | Datei |
|-------|-------|
| Deployment & Prod | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Infrastruktur (Docker, nginx, Caddy, Mail, Monitoring) | [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) |
| Backend-Architektur (Router, Services, Patterns) | [docs/BACKEND-ARCHITEKTUR.md](docs/BACKEND-ARCHITEKTUR.md) |
| Architektur-Überblick (ARC42) | [docs/ARC42.md](docs/ARC42.md) |
| Installation | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| Security | [docs/SECURITY.md](docs/SECURITY.md) |
| Admin-Handbuch | [docs/handbuch/HANDBUCH-ADMIN.md](docs/handbuch/HANDBUCH-ADMIN.md) |
| Admin-Cheat-Sheet | [docs/handbuch/CHEATSHEET-ADMIN.md](docs/handbuch/CHEATSHEET-ADMIN.md) |
| Native Installation | [docs/INSTALL-NATIVE.md](docs/INSTALL-NATIVE.md) |
| Docker-Installation | [docs/INSTALL-DOCKER.md](docs/INSTALL-DOCKER.md) |
| Native Installer Design | [docs/superpowers/specs/2026-04-07-native-single-instance-installer-design.md](docs/superpowers/specs/2026-04-07-native-single-instance-installer-design.md) |
| Specs & Design-Docs | `docs/specs/` (arbzg, dsgvo, features, security) |

---
*Entwickelt mit Claude Sonnet 4.5, Sonnet 4.6 & Opus 4.6*
