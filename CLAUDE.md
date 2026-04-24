# CLAUDE.md – PraxisZeit

**Repo:** https://github.com/phash/praxiszeit
**Stack:** React 18 + TypeScript + Tailwind / FastAPI (Python 3.12) + PostgreSQL 16
**Deployment:** Docker Compose (Entwicklung/Prod) ODER Native Installer (Kundenserver)

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
```
Git Bash on Windows: `rsync`/`zip` fehlen → Script hat `tar`/PowerShell-`Compress-Archive`-Fallbacks.
PG Windows-Installer direkt: `https://get.enterprisedb.com/postgresql/postgresql-X.Y-Z-windows-x64.exe` (kein Webformular).
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
docker compose exec backend pytest tests/test_concurrency.py     # Postgres-only Race-Tests
cd frontend && npm test                                          # Vitest Utils-Tests
```
All-in-one: `bash scripts/local-ci.sh` (backend pytest split SQLite/Postgres, vitest, tsc, eslint, vite build, e2e).
Nach nginx.conf / Frontend-Änderungen: `docker compose build frontend && docker compose up -d frontend`
**Version-Smoke-Test:** `/api/health` liefert nur `{status, database}` — **keine Version**. Version steht in `/openapi.json`, im Frontend-Footer (nach Hard-Refresh), oder unter `/` (nur wenn `SERVE_FRONTEND=False`).

### Dev-Workflow Fallstricke
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
- **Robocopy im Update-Wizard merged ohne Purge:** stale Files in `bin/python/Lib/site-packages/` kumulieren über Updates hinweg. `Step-PipInstall` bootstrappt pip deshalb via `get-pip.py --force-reinstall` VOR `pip install -r requirements.txt` (F-056). Gleiches Pattern wenn weitere `bin/`-Subdirs im Wizard behandelt werden.
- **Nach Native-Update:** im Browser Hard-Refresh (`Ctrl+F5`) oder Service-Worker unregister, sonst bleibt das alte Frontend-Bundle im Cache.
- **SPA-Fallback:** Middleware statt catch-all Route! `@app.get("/{full_path:path}")` verursacht 405 für POST/PUT/DELETE
- **SECRET_KEY persistieren:** Muss in `config/.secret-key` gespeichert werden, sonst Session-Verlust bei Restart
- **cookie_secure:** Muss `false` sein ohne SSL, sonst lehnt Browser das Refresh-Cookie ab
- **Subprocess `*` verboten:** Python 3.13/Windows expanded `*` als Glob in subprocess-Args → explizite Werte nutzen
- **PYTHONUTF8=1:** Immer für uvicorn-Subprozesse setzen (cp1252-Crashes bei Emojis)
- **APP_VERSION:** Backend-SoT in `app/core/updater.py`; Frontend-Footer liest `__APP_VERSION__` aus `frontend/package.json.version` (via vite `define`). Beide + `tools/build-release.sh` Default müssen synchron bleiben — Build-Script enforced das.
- **Alembic Revision-IDs:** Max 32 Zeichen (`version_num varchar(32)` Limit)
- **clock_out `with_for_update`:** `_get_open_entry()` in `clock_out` MUSS mit Lock aufgerufen werden (Race Condition bei Doppelklick)
- **Bulk-Deletes tenant_id:** Alle `.delete()` Aufrufe brauchen expliziten `tenant_id`-Filter (nicht nur auf RLS verlassen)
- **Absence Unique Constraint:** `(user_id, date)` muss eindeutig sein — DB-Constraint oder `with_for_update()` bei Duplikat-Check
- **is_holiday() tenant_id:** Immer `tenant_id=current_user.tenant_id` übergeben (Multi-Tenant-Pflicht)

### Multi-Tenant
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
