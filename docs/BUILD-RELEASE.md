# Build & Release — PraxisZeit

Bauen, Verpacken und Ausliefern der Release-Artefakte (Native-Tarbälle, Windows-Installer, Docker-Bundle) + pzweb-Auslieferung. **Nicht** App-Entwicklung — die App-Regeln stehen in [CLAUDE.md](../CLAUDE.md).

> End-to-end-Release-Pipeline: Skill `/buildrelease` (`.claude/skills/buildrelease/SKILL.md`).

## Native Installer (Kundenserver, ohne Docker)

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

**Frontend-Dep-Bumps — vite/plugin-react im Gleichschritt (1.8.9):** Ein Dependabot-`vite`-Major-Bump (z. B. 7→8) ohne passenden `@vitejs/plugin-react`-Bump bricht `npm ci` mit `ERESOLVE` — plugin-react **5.1.4** kennt als Peer nur `vite ≤7`, **5.2.0+** ergänzt `vite 8` (6.0+ ist vite-8-only). Beim vite-Major immer plugin-react mitziehen + `npm ci` lokal verifizieren. Frontend-`Dockerfile` nutzt jetzt `npm ci` (scheitert hart bei Lock-Drift, statt still abweichend zu bauen). `npm update` kann auf Windows am optionalen `@tailwindcss/oxide-wasm32-wasi` (ENOENT-Cleanup) hängen → `rm -rf node_modules && npm install` oder `--package-lock-only`.

**Native-PG = `theseus-rs` 18.4.0** (ab 1.10.0; davor 16.13.0 — glibc-2.34-portabel: Ubuntu 22.04+/Debian 12+/RHEL·Rocky·Alma 9+/Fedora 35+; EDB-Quelle seit #125 raus, Build bricht bei glibc-Symbolen > 2.34 ab). **PG16→18-Major-Upgrade (nicht in-place):** `install.sh` dumpt vor dem Binary-Tausch mit den ALTEN Binaries, legt `data/db` als `data/db.pgXX-<ts>` zur Seite (nie gelöscht) + Marker `data/.pg-upgrade-restore`; `praxiszeit-server.py::_restore_pending_major_upgrade()` spielt den Dump in den frischen PG18-Cluster (`psql -f -v ON_ERROR_STOP=1`, streamend). Docker-Pendant: `tools/docker/update-pg-major.sh` (backup → nur `*_postgres_data`-Volume weg → frischer PG18 → restore). PG18-Docker-Image braucht `PGDATA=/var/lib/postgresql/data` (sonst Major-Unterordner). PG-Downloads SHA256-verifiziert, macOS zusätzlich per `file(1)` als Mach-O geprüft. ⚠️ `validate-macos.yml` läuft auf dem Privat-Repo **NIE** (Runs `queued`) → macOS-Release stützt sich auf die lokale Mach-O-Prüfung im Build, NICHT auf den GH-Workflow; echtes macOS-`initdb`-Smoke ggf. manuell auf einem Mac. `tools/validate-release.sh` (Linux) muss vor jedem Release grün sein. Hintergrund (EDB-403, 1.5.0-DMG-Pattern) → [docs/INSTALL-NATIVE.md](INSTALL-NATIVE.md).

Git Bash on Windows: `rsync`/`zip` fehlen → Script hat `tar`/PowerShell-`Compress-Archive`-Fallbacks.

PG Windows-Installer direkt: `https://get.enterprisedb.com/postgresql/postgresql-X.Y-Z-windows-x64.exe` (kein Webformular).

**Windows-Python-Deps werden beim BUILD vorinstalliert** (1.5.1, `build-release.sh` Phase 5): cp313-win_amd64-Wheels in `bin/python/Lib/site-packages` → Kunden-Install ohne PyPI-Download. `PYTHONNOUSERSITE=1` beim pip + Import-Verify (sonst sah pip ein System-Python-User-Site → leeres Bundle → `ERR_CONNECTION_REFUSED`). Postmortem → [docs/NATIVE-WINDOWS-PITFALLS.md](NATIVE-WINDOWS-PITFALLS.md) #12.

**Windows-PG ≠ theseus:** `.exe`/`.zip` bündeln den **EDB-Installer** (`postgresql-installer.exe`); die theseus-18-Binaries gelten nur für die Linux/macOS-Tarbälle. ⚠️ **Windows-PG-Installer ist SHA256-gepinnt (`PG_WINDOWS_SHA256` in build-release.sh) + wird per direktem EDB-Link auto-geladen + verifiziert** — KEIN ungeprüfter `~/Downloads`-Griff mehr. Hintergrund: der alte blinde Glob bundelte je nach Build-Maschine still eine ANDERE PG-Version (1.10.0-Windows war lokal **PG 16.13** statt 18, weil die gecachte `.exe` vom 19.06. stammte; die Büro-Build-Maschine hatte wieder eine andere) → 3 Maschinen, 3 Installer, keiner verifiziert. Beim PG-Bump `PG_WINDOWS_SHA256` an die zur `POSTGRESQL_VERSION` passende `postgresql-<maj.min>-<suffix>-windows-x64.exe` mitziehen. EDB-403 (Auto-Download blockiert) kam zeitweise vor → Build bricht dann mit Manual-Download-Hinweis + erwarteter SHA ab.

**Build-Staging-Race:** Phase 2 kopiert `praxiszeit-server.py`/`app/` früh ins Staging — Code-Edits NACH Build-Start landen NICHT im Artefakt. Nach jeder Server-Änderung komplett neu bauen + im ZIP verifizieren (`zipfile` → register-Call/Deps prüfen).

**Version-Bump:** 3 Stellen + Lock — `backend/app/core/updater.py`, `tools/build-release.sh` Default, `frontend/package.json` (+ `cd frontend && npm install` für Lock). Build-Script validiert Consistency und bricht sonst ab. `frontend/package.json.version` landet als `__APP_VERSION__` im Footer (`Layout.tsx:345`) — ohne Bump zeigt die UI die alte Version (war 1.3.0 → 1.3.5 lang gedriftet).

**APP_VERSION:** Backend-SoT in `app/core/updater.py`; Frontend-Footer liest `__APP_VERSION__` aus `frontend/package.json.version` (via vite `define`). Beide + `tools/build-release.sh` Default müssen synchron bleiben — Build-Script enforced das.

**Build-Exit-Code 1 am Ende ist kosmetisch** (letztes `$BUILD_LINUX && cat <<EOF` liefert 1 bei `false`). Erfolg = `dist/praxiszeit-X.Y.Z-windows-x64.zip` existiert.

**`dist/…-SHA256SUMS.txt`-Self-Reference (behoben):** Build-Schritt 7 (~Z. 1042) muss die alte SHA-Datei VOR dem `praxiszeit-<ver>-*`-Glob entfernen und über Temp-Datei + `mv` schreiben (sonst listet die SHA-Datei sich selbst → kosmetisches `sha256sum -c FAILED`). Bei Änderungen an Schritt 7 beibehalten.

**✅ #231 — `setup.exe` NICHT in den `windows-x64.zip`-Baum kopieren:** Sonst steckt das Paket doppelt im ZIP (loser `.bat`-Baum **+** die alles einbettende `setup.exe`) → ~985 statt ~490 MB. `setup.exe` ist nur Standalone-`dist/`-Artefakt; ein **Build-Abort-Guard** bricht ab, falls sie doch im ZIP landet (in `build-release.sh` beibehalten). Empfohlener Install-Weg verweist daher auf den **Standalone-`setup.exe`-Download** (ZIP-Nutzer → `.bat`-Fallback). Hintergrund: #231.

**Docker-Bundle (ab 1.8.0):** `build-release.sh --docker-only` baut `praxiszeit-<version>-docker.tar.gz` (Top-Level-Ordner!) mit compose-Dateien + `.env.example` + `generate-secrets.sh` + Build-Kontext (`backend/ frontend/ ssl/ prometheus/ grafana/`). Native-Tarbälle enthalten KEIN compose (Braumann-Feedback). Seit [pzweb #35](https://github.com/phash/pzweb/issues/35) akzeptiert das pzweb-Upload-Regex auch `-docker` (`os=docker`) + `-setup-windows-x64.exe` (`os=windows-setup`) → **alle 6 Artefakte gehören in den pzweb-Shop**; `setup.exe`/`docker.tar.gz` werden **zusätzlich** ans GitHub-Release gehängt (nicht mehr nur dort). `docker`/`windows-setup` sind download-only (kein `/v1/check`-Auto-Update-Kanal → `os=windows-setup` 204 ist korrekt). Doku: [docs/INSTALL-DOCKER.md](INSTALL-DOCKER.md). `ssl/`-Copy im Build excludet `cert.pem`/`key.pem` (kein Build-Host-Key im Bundle).

**Self-signed SSL-Cert generieren** (für lokale HTTPS-Tests): `python tools/generate-self-signed-cert.py` — Chrome ServiceWorker-Registrierung scheitert damit trotzdem (Issue #84).

→ Details: [docs/INSTALL-NATIVE.md](INSTALL-NATIVE.md)

## Cross-Platform Installer (1.4.0+, Avalonia/.NET 10)

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

## pzweb-Integration (ab 1.5.0)

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

**Release-Ablage lokal:** Artefakte nach `pzweb/releases/version_X.Y.Z/`. Prüfsummen **pro Datei** als `checksum_<dateiname>` (Inhalt: `sha256sum`-Zeile) — NICHT eine gemeinsame `…-SHA256SUMS.txt`, sonst überschreibt die Windows-Variante die Linux/Docker-Prüfsumme (alter Workaround `…-SHA256SUMS_win.txt`).

**Manifest-Signatur** (im Code in `app/core/updater.py:_verify_manifest_signature`):
JSON-Body über `sort_keys=True, separators=(",",":")` kanonisiert, mit Ed25519 signiert, base64-encoded ins `signature`-Feld. Veränderung beliebigen Feldes invalidiert die Signatur.

**Verwandte Issues:** #124 (Release-Prozess), #125 (Build-Bug postmortem, geschlossen), #84 (PWA-SW + self-signed cert).
