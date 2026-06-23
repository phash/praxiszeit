# BUILD.md — Release-Artefakte bauen (alle OS)

Anleitung zum Bauen der PraxisZeit-Release-Pakete für **Linux (x64 + arm64)**,
**Windows (x64)**, **macOS (Intel + Apple Silicon)** und **Docker**. Mit allen
Footguns, die in der Praxis zugeschlagen haben.

> **Goldene Regel:** Ein Release ist erst dann fertig, wenn `tools/validate-release.sh`
> (Linux, 5 Distros) **grün** ist **und** mindestens ein **echter Login** auf einem
> realen Host geprüft wurde (Unit-Tests + validate-release reichen NICHT —
> mehrere 1.8.x-Bugs sind genau dadurch durchgerutscht).

---

## 1. Was gebaut wird

| Artefakt | Inhalt | DB |
|---|---|---|
| `praxiszeit-<v>-linux-x64.tar.gz` | Nativer Installer + Python + PostgreSQL (flach entpackt) | theseus-rs PG **18.4** |
| `praxiszeit-<v>-macos-x64/arm64.tar.gz` | Nativer Installer (Intel / Apple Silicon) | theseus-rs PG **18.4** |
| `praxiszeit-<v>-windows-x64.zip` | `.bat`-Installer-Baum (setup.bat-Fallback) | EDB-Installer PG **18.4** |
| `praxiszeit-<v>-setup-windows-x64.exe` | Avalonia-GUI-Single-File-Installer (#81) | (bettet das Paket ein) |
| `praxiszeit-<v>-docker.tar.gz` | compose + Build-Kontext + backup/restore/update-pg-major | `postgres:18-alpine` |

Alles entsteht aus **einem** Lauf von `tools/build-release.sh`.

---

## 2. Voraussetzungen

| Tool | Wofür | Hinweis |
|---|---|---|
| **Docker** | Frontend-Build, Backend-Image, validate-release | Pflicht. |
| **.NET 10 SDK** (`dotnet --version` → `10.x`) | Windows-`setup.exe` (Avalonia) | Fehlt es → `--skip-setup` (nur `.bat`-Fallback, kein GUI-Installer). |
| `curl`, `sha256sum`, `tar`, `unzip`, `objdump` | Download/Verify/Pack | objdump nur für den glibc-Check. |
| **KEIN Host-Node ≥ 26** | — | ⚠️ siehe §3. Host-Node 26 **bricht** den Frontend-Schritt. |

> ⚠️ **Mehrere Build-Maschinen (Büro):** Alle relevanten Binaries werden
> **versioniert + SHA256-verifiziert** geladen (theseus-PG, Python-Standalone,
> NSSM, VC++-Redist, **Windows-PG seit 1.10.1**). Dadurch bauen alle Maschinen
> **bit-identische** Bundles. Wenn eine Maschine abweicht → Cache-Datei mit
> falscher SHA (siehe §6 Windows).

---

## 3. Frontend vorbauen (Host-Node-26-Footgun)

`build-release.sh` ruft intern `npm run build`. **Host-Node ≥ 26 bricht das ab.**
Darum das Frontend **mit Docker node:20 vorbauen** und dann mit `--skip-frontend`
releasen (das `frontend/dist/` muss existieren):

```bash
docker run --rm -v "$(pwd)/frontend:/app" -w /app node:20-alpine sh -c "npm run build"
# danach immer mit --skip-frontend bauen
```

`__APP_VERSION__` (Footer) wird aus `frontend/package.json.version` ins Bundle
inlined — ohne korrekten Bump zeigt die UI die alte Version.

---

## 4. Version-Bump (3 Stellen + Lock)

Vor jedem Release synchron halten — `build-release.sh` **erzwingt** die Konsistenz
und bricht sonst ab:

```bash
# 1) backend/app/core/updater.py   -> APP_VERSION = "X.Y.Z"
# 2) frontend/package.json         -> "version": "X.Y.Z"
# 3) tools/build-release.sh        -> APP_VERSION="X.Y.Z"
# 4) Lock aktualisieren:
docker run --rm -v "$(pwd)/frontend:/app" -w /app node:20-alpine sh -c "npm install --package-lock-only"
```

`frontend/package.json.version` landet als `__APP_VERSION__` im Footer (`Layout.tsx`).

---

## 5. Bauen

### Alles (alle OS)
```bash
docker run --rm -v "$(pwd)/frontend:/app" -w /app node:20-alpine sh -c "npm run build"  # Frontend vorbauen
bash tools/build-release.sh --skip-frontend
bash tools/validate-release.sh          # Linux-Tarball: 5-Distro-Docker-Smoke (PG18 initdb/postgres)
```

### Einzelne OS (schnellere Iteration)
```bash
bash tools/build-release.sh --linux-only   --skip-frontend
bash tools/build-release.sh --windows-only --skip-frontend
bash tools/build-release.sh --docker-only                       # nur Docker-Bundle
bash tools/build-release.sh --windows-only --setup-only         # nur die setup.exe iterieren
bash tools/build-release.sh --windows-only --skip-setup         # Windows ohne setup.exe (.NET fehlt)
```

**Erfolg = `dist/praxiszeit-X.Y.Z-*.{tar.gz,zip,exe}` existieren.** Der Exit-Code 1
am Ende ist **kosmetisch** (letztes `$BUILD_LINUX && cat <<EOF` liefert 1 bei false).

---

## 6. Pro-OS-Details + Footguns

### Linux (x64 + arm64)
- **PostgreSQL = `theseus-rs` 18.4.0** (manylinux, glibc-2.34-portabel: Ubuntu 22.04+/
  Debian 12+/RHEL·Rocky·Alma 9+/Fedora 35+). Download SHA256-verifiziert. Der Build
  **bricht ab**, wenn die Binaries glibc-Symbole **> 2.34** brauchen.
- `libxml2.so.2` wird mitgebündelt (Rolling-Distros wie Arch liefern nur `.so.16`, #177).
- Tarball entpackt **flach** (`tar -C <ordner> .`, kein Top-Level-Ordner) — `install.sh`/
  `validate-release.sh` setzen das voraus.
- **`validate-release.sh` ist Pflicht** (5 Distros) — testet aber **NUR** initdb/postgres,
  **keinen echten Login**. Nach Dep-Bumps zusätzlich realen Login prüfen.

### Windows (x64) — der größte Footgun-Garten
- **PostgreSQL = EDB-Installer (`postgresql-installer.exe`, PG 18.4)** — NICHT theseus.
- ⚠️ **PG-Installer ist SHA256-gepinnt (`PG_WINDOWS_SHA256` in build-release.sh) +
  wird per direktem EDB-Link auto-geladen + verifiziert.** Früher griff der Build blind
  die erste `~/Downloads/postgresql-*-windows-x64.exe` → **jede Maschine bundelte still
  eine andere PG-Version** (1.10.0-Windows war versehentlich PG 16.13 statt 18). Beim
  PG-Bump `PG_WINDOWS_SHA256` an die zur `POSTGRESQL_VERSION` passende
  `postgresql-<maj.min>-<suffix>-windows-x64.exe` mitziehen.
- **EDB-403:** Der Auto-Download kann zeitweise mit HTTP 403 blocken. Dann bricht der
  Build mit Manual-Hinweis + erwarteter SHA ab → Datei manuell laden, nach
  `build/cache/postgresql-windows-x64.exe` legen, neu bauen.
- **`setup.exe` braucht .NET 10 SDK** (`dotnet test`-Gate läuft VOR dem Build; rote
  Tests → keine setup.exe). Cross-Build von Linux aus ist ok (echtes PE32+).
- **ZIP-Größe:** die `setup.exe` darf **NICHT** in den `.bat`-ZIP-Baum kopiert werden
  (sonst doppelt → ~985 MB statt ~490 MB, #231). Ein Build-Abort-Guard prüft das.
- **Windows-Python-Deps werden beim BUILD vorinstalliert** (cp313-Wheels in
  `bin/python/Lib/site-packages`, `PYTHONNOUSERSITE=1` beim pip), damit der Kunde
  ohne PyPI-Download installiert.
- **Build-Staging-Race:** Phase 2 kopiert `praxiszeit-server.py`/`app/` früh ins
  Staging — Code-Edits NACH Build-Start landen NICHT im Artefakt. Nach Server-Änderungen
  komplett neu bauen + im ZIP verifizieren.
- Git Bash on Windows: `rsync`/`zip` fehlen → `tar`/PowerShell-`Compress-Archive`-Fallbacks.

### macOS (Intel + Apple Silicon)
- **PostgreSQL = theseus-rs 18.4** (EDB-DMG seit #125 raus). Downloads SHA256- **und**
  per `file(1)` als **Mach-O** geprüft.
- ⚠️ **`validate-macos.yml` läuft auf dem Privat-Repo NIE** (Runs bleiben `queued`, kein
  Runner). macOS-Release stützt sich auf die lokale Mach-O-`file`-Prüfung im Build,
  **nicht** auf den GH-Workflow; echtes `initdb`-Smoke ggf. manuell auf einem Mac.

### Docker
- `--docker-only` baut `praxiszeit-<v>-docker.tar.gz` (**Top-Level-Ordner!**) mit
  compose-Dateien + `.env.example` + `generate-secrets.sh` + `backup.sh`/`restore.sh`/
  **`update-pg-major.sh`** + Build-Kontext (`backend/ frontend/ ssl/ prometheus/ grafana/`).
- DB = `postgres:18-alpine`; Backend-Image bringt `postgresql-client-18` (für #213-pg_dump).
  ⚠️ PG18-Image legt Daten per Default in einen Major-Unterordner → in der compose
  `PGDATA=/var/lib/postgresql/data` explizit gesetzt.
- Der `-docker`-Name passt NICHT ins strikte pzweb-Upload-Regex → gehört an ein
  **GitHub-Release**, nicht in den pzweb-Shop.

---

## 7. PostgreSQL-Major-Upgrade (16 → 18) — beim Bauen mitdenken

Ab 1.10.0 ist die DB **PG 18**. Ein Major-Upgrade ist **nicht in-place**:
- **Nativ:** `install.sh` dumpt vor dem Binary-Tausch mit den ALTEN Binaries, legt die
  Alt-Daten als `data/db.pgXX-<ts>` zur Seite (nie gelöscht) + Marker;
  `praxiszeit-server.py` spielt den Dump in den frischen Cluster.
- **Docker:** `tools/docker/update-pg-major.sh` (backup → nur `*_postgres_data`-Volume
  weg → frischer PG18 → restore).

Diese Pfade sind Teil der Artefakte — bei Änderungen am PG-Start/Connect immer
`pg_is_running()` + `_database_url()` + `pg_init`-`listen_addresses` zusammen pflegen.

---

## 8. Release-Ablage + Prüfsummen

```bash
# Artefakte nach pzweb/releases/version_X.Y.Z/
# Prüfsummen PRO DATEI als checksum_<dateiname> (Inhalt: eine sha256sum-Zeile) —
# NICHT eine gemeinsame SHA256SUMS.txt (sonst überschreibt Windows die Linux-Summe).
for f in praxiszeit-X.Y.Z-*.{tar.gz,zip,exe}; do sha256sum "$f" > "checksum_$f"; done
```

**Dateiname-Pattern (striktes pzweb-Regex):**
`praxiszeit-<version>-(linux-x64|macos-x64|macos-arm64|windows-x64).(tar.gz|zip)`
— Tippfehler ⇒ 422 beim Upload.

---

## 9. Footgun-Schnellliste

- Host-Node ≥ 26 → Frontend mit `docker node:20` vorbauen + `--skip-frontend`.
- Windows-PG-Installer **SHA-gepinnt** — bei abweichender Maschine: falsche Cache-Datei.
- `setup.exe` braucht .NET 10; darf nicht doppelt ins ZIP (#231-Guard).
- theseus-PG bricht bei glibc > 2.34 ab; libxml2.so.2 wird mitgebündelt.
- Build-Exit-Code 1 am Ende = kosmetisch; Erfolg = `dist/`-Dateien existieren.
- Nach Server-Code-Edits **komplett** neu bauen (Staging-Race) + im ZIP verifizieren.
- `validate-release` testet KEINEN Login → realen Host-Login nach Dep-Bumps prüfen.
- Prüfsummen **pro Datei** (`checksum_<datei>`), nicht gemeinsam.
- `validate-macos.yml` läuft nie (Privat-Repo) → lokale Mach-O-Prüfung ist der Gate.

---
*Stand: 1.10.1 (PostgreSQL 18.4 auf allen Plattformen).*
