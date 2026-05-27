# CLAUDE.md – PraxisZeit

**Repo:** https://github.com/phash/praxiszeit
**Stack:** React 18 + TypeScript + Tailwind / FastAPI (Python 3.12) + PostgreSQL 16
**Deployment:** Docker Compose (Entwicklung/Prod) ODER Native Installer (Kundenserver)
**Aktuelle Version:** 1.5.0 (Stand 2026-05-24)
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
bash tools/validate-release.sh                 # Linux-Tarball: Docker-Smoke gegen 4 Distros
# macOS-Validierung läuft als GitHub-Actions-Workflow (validate-macos.yml)
# auf macos-15-intel + macos-14 — manuell triggerbar via gh workflow run.
```
**PostgreSQL-Quelle (ab 1.5.0):** `theseus-rs/postgresql-binaries` 16.13.0. Manylinux-Build, forward-kompatibel bis **glibc 2.34** (Ubuntu 22.04+, Debian 12+, RHEL/Rocky/Alma 9+, Fedora 35+). EDB-Tarbälle sind seit 2026-05 nicht mehr verfügbar (HTTP 403), System-PG-Fallback wurde entfernt (#125). Build bricht hart ab, wenn die Quelle nicht erreichbar ist oder glibc-Symbole > 2.34 verlangt werden. Linux- UND macOS-PG-Downloads sind SHA256-verifiziert (`download_with_sha`); macOS-Binaries werden nach dem `tar xzf` per `file(1)` als Mach-O verifiziert (1.5.2 Härtung — verhindert das 1.5.0-Pattern, bei dem nur das EDB-DMG ohne Binaries im Paket landete und der Build trotzdem "erfolgreich" war). `tools/validate-release.sh` (Linux) + `.github/workflows/validate-macos.yml` (macOS) müssen vor jedem Release grün sein.
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
dotnet test                                    # 20 Tests (xunit + FluentAssertions)
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
- **Frontend `node_modules` ist root-owned** (im Image-Build erzeugt). Host-`npm install` failt mit EACCES. Pattern: `docker run --rm -v $(pwd)/frontend:/app -w /app node:20-alpine sh -c "npm install --silent && ..."`.
- **Test-Stratifizierung:** Unit-Tests laufen gegen SQLite (conftest.py). RLS + echte `SELECT FOR UPDATE`-Races brauchen Postgres → `test_tenant_rls.py` + `test_concurrency.py` aus normalem pytest ausschließen (`--ignore=`).

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
- **Absence-Typ-Matrix:** Siehe `docs/BACKEND-ARCHITEKTUR.md` → Berechnungsmodell
- **CR-Approval:** Precondition-Checks VOR Status-Änderung (Race-Condition-Fix)
- **Absence-CRs:** MA können Abwesenheiten per Änderungsantrag beantragen (entry_kind="absence")
- **Absences Start/End:** Absences haben optionale `start_time`/`end_time` (NULL = ganzer Tag)
- **DSGVO Art.9:** Kalender-Endpoints maskieren `sick` → `absent` für nicht-Admins
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
- **Lizenz-Public-Key niemals rotieren** — der Ed25519 `_PUBLIC_KEY_PEM` in `backend/app/core/license.py` ist mit dem privaten Key im pzweb-Repo gepaart. Eine Rotation entwertet alle bisher ausgestellten Kundenlizenzen. Privater Key liegt verschlüsselt offline bei Manuel. **REAL passiert (1.5.x):** der Key wurde `…B5ZiJro…` → `…t8zaDoRf…` rotiert → eine Produktiv-Lizenz wurde ungültig → `sys.exit(1)` → Login-Totalausfall. Recovery: neue Lizenz aus dem Shop ODER `license.key` temporär entfernen. Seit 1.5.2 crasht es nicht mehr (Read-Only-Fallback, s.o.). Falls je nötig: in `validate_license` mehrere Keys (alt+neu) akzeptieren statt hart rotieren.
- **`_ALLOWED_UPDATE_HOSTS` in `backend/app/core/updater.py`** enthält ab 1.5.0 sowohl `updates.mr-development.de` als auch `praxiszeit.mr-development.de`. Vor dem Entfernen eines Hosts MUSS mindestens eine Version durchgelaufen sein, die die ersetzende Domain bereits kennt (Henne-Ei). `updates.praxiszeit.de` ist Platzhalter, falls die eigene Domain irgendwann live geht.
- **Native-Build verlangt `pg_env()`-Helper** in `praxiszeit-server.py` — alle 7 PG-Subprocess-Aufrufe (initdb, postgres, pg_ctl, psql, pg_dump) bekommen `env=pg_env()`, das `LD_LIBRARY_PATH=$BIN_DIR/postgresql/lib` (Linux/macOS) bzw. `PATH`-Prepend (Windows) setzt. Plus `PGHOST` auf `DATA_DIR/run/`, damit psql den umgezogenen Socket findet.
- **`unix_socket_directories` in `pg_init()`** muss auf `DATA_DIR/run/` zeigen (nicht `/var/run/postgresql`), weil systemd `ProtectSystem=strict` das default Verzeichnis read-only macht. Detail-Postmortem in #125.
- **`installer/linux/install.sh` installiert Runtime-Libs automatisch** (`libxml2 libssl3 libgssapi-krb5-2 libzstd1 liblz4-1 libreadline8 libbrotli1` via apt-get/dnf/zypper). Auf Ubuntu-Minimal-Images sind die nicht alle da, theseus' postgres-Binary linkt aber dagegen.
- **Alembic Revision-IDs:** Max 32 Zeichen (`version_num varchar(32)` Limit)
- **clock_out `with_for_update`:** `_get_open_entry()` in `clock_out` MUSS mit Lock aufgerufen werden (Race Condition bei Doppelklick)
- **F-026 Tenant-Filter (belt-and-suspenders):** ALLE `db.query(Model).filter(...)` auf tenant-scoped Tabellen brauchen expliziten `Model.tenant_id == current_user.tenant_id` zusätzlich zu RLS — gilt für list, lookup-by-id UND `.delete()`. Helper für User-Lookup: `_get_user_in_tenant()` in `admin_users.py`. Tests in `test_cross_tenant_api.py`.
- **Absence Unique Constraint:** `(user_id, date)` muss eindeutig sein — DB-Constraint oder `with_for_update()` bei Duplikat-Check
- **is_holiday() tenant_id:** Immer `tenant_id=current_user.tenant_id` übergeben (Multi-Tenant-Pflicht)
- **`time_entry_audit_logs.source` ist `varchar(40)`** (Migration 037). Neue Source-Marker müssen <40 Zeichen sein, sonst 500 beim INSERT (`StringDataRightTruncation`). Bestehende Werte: `manual`, `import`, `change_request`, `vacation_request_cancel`.
- **`backend/create_handbuch_testdata.py`** ist multi-tenant-aware: ruft `set_superadmin_context(db)` auf + setzt `tenant_id=TENANT_ID` an User/TimeEntry/Absence/ChangeRequest. Wer das Script forkt für andere Seed-Daten muss beides mitnehmen, sonst RLS-Violation beim INSERT.
- **Container-File-Updates aus fremdem cwd:** `docker compose cp` resolved Host-Pfade **relativ zum cwd**. Aus `e2e/` heraus → `lstat e2e/backend/...: no such file`. Lösung: `docker cp <host-abs-path> praxiszeit-backend-1:/app/<path>`.

### pzweb-Integration (ab 1.5.0)

Lizenzen und Updates werden zentral über [pzweb](https://github.com/phash/pzweb) verkauft und ausgeliefert (`praxiszeit.mr-development.de` + `updates.mr-development.de`).

**Release-Workflow** (Detail-Checkliste in praxiszeit#124):
1. Version-Bump in `backend/app/core/updater.py`, `frontend/package.json`, `tools/build-release.sh` — alle drei synchron, Build-Script enforced das.
2. `bash tools/build-release.sh` — vier OS-Tarbälle in `dist/`.
3. `bash tools/validate-release.sh` — Docker-Smoke gegen Ubuntu 22.04/24.04, Debian 12, Rocky 9. Failt eine Distro = Tarball nicht freigabefähig.
3b. macOS-Validierung: `gh workflow run validate-macos.yml` (oder Push triggert automatisch bei `dist/praxiszeit-*-macos-*.tar.gz`-Änderung). Läuft auf `macos-15-intel` + `macos-14`, prüft Mach-O-Sanity (`file`/`otool`) + initdb-Smoketest. Beides muss grün sein vor Customer-Release.
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
- Mitarbeiter: `manuel@example.de`

### Claude-Code-Bash-Gotchas
- Das `cd` in einem Bash-Aufruf **persistiert** zwischen Tool-Calls. Nach `cd .claude/worktrees/...` ist `git status` ohne erneutes `cd` immer noch im Worktree. Bei git-Operationen lieber `git -C <pfad>` nutzen oder cwd explizit zurücksetzen.
- `docker compose cp <host-file> <svc>:<container-path>` resolved den Host-Pfad **relativ zum cwd**, nicht zum Repo-Root. Aus fremdem cwd → `docker cp` mit absoluten Pfaden + Container-Name (`praxiszeit-backend-1`).

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
| Native Installer Design | [docs/superpowers/specs/2026-04-07-native-single-instance-installer-design.md](docs/superpowers/specs/2026-04-07-native-single-instance-installer-design.md) |
| Specs & Design-Docs | `docs/specs/` (arbzg, dsgvo, features, security) |

---
*Entwickelt mit Claude Sonnet 4.5, Sonnet 4.6 & Opus 4.6*
