#!/bin/bash
# PraxisZeit Release Builder
# Baut Installer-Pakete fuer Linux, Windows und macOS mit gebuendelten Binaries.
#
# Usage:
#   bash tools/build-release.sh                    # Build alle Plattformen
#   bash tools/build-release.sh --linux-only       # Nur Linux
#   bash tools/build-release.sh --windows-only     # Nur Windows
#   bash tools/build-release.sh --macos-only       # Nur macOS (Intel + Apple Silicon)
#   bash tools/build-release.sh --skip-download    # Binaries nicht neu laden (cache)
#   bash tools/build-release.sh --version 1.3.0    # Versionsnummer setzen
set -euo pipefail

# =============================================================================
# Konfiguration — Versionen der gebuendelten Binaries
# =============================================================================

APP_VERSION="1.5.0"
PYTHON_VERSION="3.13.3"
# python-build-standalone Release-Tag (Format: YYYYMMDD)
PYTHON_STANDALONE_TAG="20250529"
POSTGRESQL_VERSION="16.8"
# EDB-spezifisches Versions-Suffix
POSTGRESQL_EDB_SUFFIX="1"
NSSM_VERSION="2.24"

# =============================================================================
# CLI-Argumente
# =============================================================================

BUILD_LINUX=true
BUILD_WINDOWS=true
BUILD_MACOS=true
SKIP_DOWNLOAD=false
SKIP_FRONTEND=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --linux-only)    BUILD_WINDOWS=false; BUILD_MACOS=false; shift ;;
        --windows-only)  BUILD_LINUX=false; BUILD_MACOS=false; shift ;;
        --macos-only)    BUILD_LINUX=false; BUILD_WINDOWS=false; shift ;;
        --skip-download) SKIP_DOWNLOAD=true; shift ;;
        --skip-frontend) SKIP_FRONTEND=true; shift ;;
        --version)       APP_VERSION="$2"; shift 2 ;;
        -h|--help)
            cat <<'USAGE'
Usage: build-release.sh [options] [VERSION]

Options:
  --linux-only       Build nur die Linux-Plattform
  --windows-only     Build nur die Windows-Plattform
  --macos-only       Build nur die macOS-Plattform
  --skip-download    Cache nutzen (PG/Python-Downloads nicht wiederholen)
  --skip-frontend    Frontend-Build überspringen (Dist muss schon existieren)
  --version VERSION  Explizit Versionsnummer setzen
  -h, --help         Diese Hilfe anzeigen

Wird VERSION ohne --version übergeben, wird sie als APP_VERSION genutzt.
Default ist die im Script-Header gesetzte APP_VERSION.

Ergebnis liegt in dist/.
USAGE
            exit 0
            ;;
        --*)
            echo "Unbekannte Option: $1" >&2
            echo "Hilfe: $0 --help" >&2
            exit 1
            ;;
        *)               APP_VERSION="$1"; shift ;;
    esac
done

# =============================================================================
# Pfade
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${REPO_DIR}/build/release-${APP_VERSION}"
DIST_DIR="${REPO_DIR}/dist"
CACHE_DIR="${REPO_DIR}/build/cache"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[BUILD]${NC} $*"; }
step()  { echo -e "${CYAN}[STEP]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Plattform-Liste fuer Zusammenfassung
PLATFORMS=""
$BUILD_LINUX   && PLATFORMS="${PLATFORMS} Linux"
$BUILD_WINDOWS && PLATFORMS="${PLATFORMS} Windows"
$BUILD_MACOS   && PLATFORMS="${PLATFORMS} macOS"

echo ""
echo "=============================================="
echo "  PraxisZeit Release Builder"
echo "  App: v${APP_VERSION}"
echo "  Python: ${PYTHON_VERSION}"
echo "  PostgreSQL: ${POSTGRESQL_VERSION}"
echo "  Plattformen:${PLATFORMS}"
echo "=============================================="
echo ""

# =============================================================================
# Version-Konsistenz-Check (F-055-Followup, 1.3.6)
# =============================================================================
# Backend-APP_VERSION (updater.py) ist Single Source of Truth. frontend/
# package.json hat eine eigene "version"-Eigenschaft die ins Bundle als
# __APP_VERSION__ eingebettet wird (Layout.tsx Footer). Wenn die beiden
# drueberlaufen, zeigt der Footer eine andere Version als /api/health —
# exakt was in 1.3.0..1.3.5 passiert ist. Build haerten: vor dem Frontend-
# Build abbrechen wenn frontend/package.json != APP_VERSION.

SCRIPT_DIR_PRE="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR_PRE="$(cd "${SCRIPT_DIR_PRE}/.." && pwd)"
_fe_ver=$(sed -n 's/^  "version": *"\([^"]*\)".*/\1/p' "${REPO_DIR_PRE}/frontend/package.json" | head -1)
if [ -z "$_fe_ver" ]; then
    echo -e "${RED}[ERROR]${NC} Konnte frontend/package.json version nicht lesen" >&2
    exit 1
fi
if [ "$_fe_ver" != "$APP_VERSION" ]; then
    echo -e "${RED}[ERROR]${NC} Version-Drift erkannt:" >&2
    echo -e "${RED}[ERROR]${NC}   APP_VERSION (build-release.sh) = ${APP_VERSION}" >&2
    echo -e "${RED}[ERROR]${NC}   frontend/package.json version  = ${_fe_ver}" >&2
    echo -e "${RED}[ERROR]${NC} Fix: frontend/package.json + package-lock.json auf ${APP_VERSION} bumpen" >&2
    echo -e "${RED}[ERROR]${NC}      (cd frontend && npm version ${APP_VERSION} --no-git-tag-version)" >&2
    exit 1
fi

# =============================================================================
# Download-URLs
# =============================================================================

# python-build-standalone (indygreg/astral-sh)
# Releases: https://github.com/indygreg/python-build-standalone/releases
_PBS="https://github.com/indygreg/python-build-standalone/releases/download/${PYTHON_STANDALONE_TAG}"
_CPY="cpython-${PYTHON_VERSION}+${PYTHON_STANDALONE_TAG}"

PYTHON_LINUX_URL="${_PBS}/${_CPY}-x86_64-unknown-linux-gnu-install_only.tar.gz"
PYTHON_WINDOWS_URL="${_PBS}/${_CPY}-x86_64-pc-windows-msvc-install_only.tar.gz"
PYTHON_MACOS_X64_URL="${_PBS}/${_CPY}-x86_64-apple-darwin-install_only.tar.gz"
PYTHON_MACOS_ARM64_URL="${_PBS}/${_CPY}-aarch64-apple-darwin-install_only.tar.gz"

# EnterpriseDB PostgreSQL Binaries
# Download-Seite: https://www.enterprisedb.com/download-postgresql-binaries
_EDB="https://get.enterprisedb.com/postgresql"
_PGV="postgresql-${POSTGRESQL_VERSION}-${POSTGRESQL_EDB_SUFFIX}"

PG_LINUX_URL="${_EDB}/${_PGV}-linux-x64-binaries.tar.gz"
# Windows: EDB Installer (.exe) — muss manuell heruntergeladen werden
# Download: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
# Datei in build/cache/postgresql-windows-x64.exe ablegen
PG_WINDOWS_INSTALLER="postgresql-windows-x64.exe"
# macOS: EDB Installer (.dmg) — muss manuell heruntergeladen werden
# Download: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
# Datei in build/cache/postgresql-macos.dmg ablegen
PG_MACOS_INSTALLER="postgresql-macos.dmg"

# nssm (Windows Service Manager) — web archive fallback, nssm.cc is unreliable
NSSM_URL="https://web.archive.org/web/2024/https://nssm.cc/release/nssm-${NSSM_VERSION}.zip"

# pip bootstrap
GET_PIP_URL="https://bootstrap.pypa.io/get-pip.py"

# =============================================================================
# Hilfsfunktionen
# =============================================================================

download() {
    local url="$1"
    local target="$2"
    local name="$(basename "$target")"

    if [ -f "$target" ] && [ "$SKIP_DOWNLOAD" = true ]; then
        info "Cache: ${name} (bereits vorhanden)"
        return 0
    fi

    info "Download: ${name}..."
    mkdir -p "$(dirname "$target")"
    if ! curl -fSL --progress-bar -o "$target" "$url"; then
        error "Download fehlgeschlagen: $url"
        rm -f "$target"
        return 1
    fi
    info "OK: ${name} ($(du -h "$target" | cut -f1))"
}

# Gemeinsame Funktion: Plattform-Verzeichnis mit App-Dateien + leeren Runtime-Dirs vorbereiten
prepare_platform_dir() {
    local dir="$1"
    mkdir -p "$dir"
    cp -r "${BUILD_DIR}/common/"* "$dir/"
    mkdir -p "$dir/data/db" "$dir/data/backups" "$dir/config/ssl" "$dir/logs"
}

# =============================================================================
# Phase 1: Cleanup + Frontend
# =============================================================================

step "1 — Cleanup + Frontend bauen"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}" "${DIST_DIR}" "${CACHE_DIR}"

# F-055 (1.3.4): Frontend IMMER neu bauen. Die alte "skip if dist/ exists"-
# Logik hat in der Session 2026-04-11 alle 1.3.x-ZIPs mit einem pre-1.3.0-
# Frontend ausgeliefert (ohne CSRF-Interceptor), weil eine alte dist/ im
# Repo lag. Ergebnis: Backend 1.3.x + Frontend pre-1.3.0 -> jede mutating
# Operation vom Browser haengt am CSRF-Check. Kosten: 5-10 Sek fuer einen
# vite build. Wer's wirklich ueberspringen will: --skip-frontend.
if [ "${SKIP_FRONTEND:-false}" = true ]; then
    info "Frontend-Build uebersprungen (SKIP_FRONTEND=true)"
    if [ ! -d "${REPO_DIR}/frontend/dist" ]; then
        error "SKIP_FRONTEND gesetzt, aber keine frontend/dist/ vorhanden"
        exit 1
    fi
else
    info "Baue Frontend (vite build)..."
    (cd "${REPO_DIR}/frontend" && npm ci --silent && npm run build)
fi

# =============================================================================
# Phase 2: Gemeinsame App-Dateien vorbereiten
# =============================================================================

step "2 — App-Dateien vorbereiten"

mkdir -p "${BUILD_DIR}/common/app/backend"
# Portable tar-based copy (replaces rsync for Git Bash/Windows compatibility)
if command -v rsync &>/dev/null; then
    rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='tests/' \
        "${REPO_DIR}/backend/app" "${BUILD_DIR}/common/app/backend/"
    rsync -a --exclude='__pycache__' --exclude='*.pyc' \
        "${REPO_DIR}/backend/alembic" "${BUILD_DIR}/common/app/backend/"
else
    (cd "${REPO_DIR}/backend" && \
        tar cf - --exclude='__pycache__' --exclude='*.pyc' --exclude='app/tests' app) | \
        tar xf - -C "${BUILD_DIR}/common/app/backend/"
    (cd "${REPO_DIR}/backend" && \
        tar cf - --exclude='__pycache__' --exclude='*.pyc' alembic) | \
        tar xf - -C "${BUILD_DIR}/common/app/backend/"
fi
cp "${REPO_DIR}/backend/alembic.ini" "${BUILD_DIR}/common/app/backend/"
cp "${REPO_DIR}/backend/init-db-user.sql" "${BUILD_DIR}/common/app/backend/"
cp "${REPO_DIR}/backend/requirements.txt" "${BUILD_DIR}/common/app/backend/"

mkdir -p "${BUILD_DIR}/common/app/frontend"
cp -r "${REPO_DIR}/frontend/dist/"* "${BUILD_DIR}/common/app/frontend/"

cp "${REPO_DIR}/praxiszeit-server.py" "${BUILD_DIR}/common/"
mkdir -p "${BUILD_DIR}/common/config"
cp "${REPO_DIR}/installer/praxiszeit.conf.example" "${BUILD_DIR}/common/config/"

info "App-Dateien: $(du -sh "${BUILD_DIR}/common" | cut -f1)"

# =============================================================================
# Phase 3: Binaries herunterladen
# =============================================================================

step "3 — Binaries herunterladen"

if [ "$BUILD_LINUX" = true ]; then
    download "$PYTHON_LINUX_URL"  "${CACHE_DIR}/python-linux-x64.tar.gz"
    if ! download "$PG_LINUX_URL" "${CACHE_DIR}/postgresql-linux-x64.tar.gz"; then
        warn "EDB-Download fehlgeschlagen. Versuche System-PostgreSQL zu bundlen..."
        _PG_FALLBACK_LINUX=true
    fi
fi

if [ "$BUILD_WINDOWS" = true ]; then
    download "$PYTHON_WINDOWS_URL" "${CACHE_DIR}/python-windows-x64.tar.gz"
    download "$NSSM_URL"           "${CACHE_DIR}/nssm.zip"
    download "$GET_PIP_URL"        "${CACHE_DIR}/get-pip.py"

    # PostgreSQL Windows: EDB Installer muss manuell heruntergeladen werden
    if [ ! -f "${CACHE_DIR}/${PG_WINDOWS_INSTALLER}" ]; then
        # Suche in ~/Downloads
        _found=""
        for f in ~/Downloads/postgresql-*-windows-x64.exe; do
            [ -f "$f" ] && _found="$f" && break
        done
        if [ -n "$_found" ]; then
            info "PostgreSQL-Installer gefunden: $(basename "$_found")"
            cp "$_found" "${CACHE_DIR}/${PG_WINDOWS_INSTALLER}"
        else
            warn "PostgreSQL-Installer nicht gefunden!"
            warn "Bitte herunterladen von:"
            warn "  https://www.enterprisedb.com/downloads/postgres-postgresql-downloads"
            warn "und ablegen als: ${CACHE_DIR}/${PG_WINDOWS_INSTALLER}"
            warn "oder in ~/Downloads/"
        fi
    fi
fi

if [ "$BUILD_MACOS" = true ]; then
    download "$PYTHON_MACOS_X64_URL"   "${CACHE_DIR}/python-macos-x64.tar.gz"
    download "$PYTHON_MACOS_ARM64_URL" "${CACHE_DIR}/python-macos-arm64.tar.gz"
    download "$GET_PIP_URL"            "${CACHE_DIR}/get-pip.py"

    # PostgreSQL macOS: EDB DMG muss manuell heruntergeladen werden
    if [ ! -f "${CACHE_DIR}/${PG_MACOS_INSTALLER}" ]; then
        _found=""
        for f in ~/Downloads/postgresql-*-osx.dmg; do
            [ -f "$f" ] && _found="$f" && break
        done
        if [ -n "$_found" ]; then
            info "PostgreSQL-DMG gefunden: $(basename "$_found")"
            cp "$_found" "${CACHE_DIR}/${PG_MACOS_INSTALLER}"
        else
            warn "PostgreSQL-DMG nicht gefunden!"
            warn "Bitte herunterladen von:"
            warn "  https://www.enterprisedb.com/downloads/postgres-postgresql-downloads"
            warn "und ablegen als: ${CACHE_DIR}/${PG_MACOS_INSTALLER}"
            warn "oder in ~/Downloads/"
        fi
    fi
fi

# =============================================================================
# Phase 4: Linux-Paket
# =============================================================================

if [ "$BUILD_LINUX" = true ]; then
    step "4 — Linux-Paket (x64)"

    LINUX_DIR="${BUILD_DIR}/linux"
    prepare_platform_dir "${LINUX_DIR}"

    cp "${REPO_DIR}/installer/linux/install.sh" "${LINUX_DIR}/"
    sed -i "s/@@VERSION@@/${APP_VERSION}/g" "${LINUX_DIR}/install.sh" 2>/dev/null || \
    sed -i'' "s/@@VERSION@@/${APP_VERSION}/g" "${LINUX_DIR}/install.sh"
    chmod +x "${LINUX_DIR}/install.sh"

    info "Entpacke Python ${PYTHON_VERSION} (Linux x64)..."
    mkdir -p "${LINUX_DIR}/bin/python"
    tar xzf "${CACHE_DIR}/python-linux-x64.tar.gz" \
        -C "${LINUX_DIR}/bin/python" --strip-components=1

    info "Installiere pip-Dependencies..."
    "${LINUX_DIR}/bin/python/bin/python3" -m pip install -q \
        --target="${LINUX_DIR}/bin/python/lib/python${PYTHON_VERSION%.*}/site-packages" \
        -r "${LINUX_DIR}/app/backend/requirements.txt" 2>&1 | tail -3

    info "PostgreSQL (Linux x64)..."
    mkdir -p "${LINUX_DIR}/bin/postgresql/bin" "${LINUX_DIR}/bin/postgresql/lib"
    if [ "${_PG_FALLBACK_LINUX:-false}" = true ] || [ ! -f "${CACHE_DIR}/postgresql-linux-x64.tar.gz" ]; then
        # Fallback: System-PostgreSQL-Binaries + Libs kopieren
        info "Kopiere System-PostgreSQL-Binaries..."
        PG_BINDIR="$(pg_config --bindir 2>/dev/null || echo /usr/bin)"
        PG_LIBDIR="$(pg_config --libdir 2>/dev/null || echo /usr/lib)"
        for bin in pg_ctl pg_isready psql initdb pg_dump pg_restore postgres pg_resetwal; do
            [ -f "${PG_BINDIR}/${bin}" ] && cp "${PG_BINDIR}/${bin}" "${LINUX_DIR}/bin/postgresql/bin/"
        done
        # Shared Libraries mitkopieren
        for bin in "${LINUX_DIR}/bin/postgresql/bin/"*; do
            ldd "$bin" 2>/dev/null | grep "=> /" | awk '{print $3}' | while read lib; do
                # Nur Nicht-Standard-Libs kopieren (nicht libc, ld-linux, etc.)
                # glibc-eigene Libs NICHT bundlen — sie sind ABI-gekoppelt
                # an die libc.so.6 des Build-Hosts. Wenn das Ziel eine ältere
                # glibc hat, schlägt der Loader mit "version GLIBC_X.Y not found"
                # fehl (libresolv 2.41 → Ubuntu-24-glibc-2.39 mismatch).
                case "$(basename "$lib")" in
                    libc.so*|libm.so*|libpthread*|libdl.so*|librt.so*|ld-linux*|linux-vdso*) ;;
                    libresolv.so*|libnsl.so*|libutil.so*|libcrypt.so*|libanl.so*|libthread_db.so*) ;;
                    *) cp -n "$lib" "${LINUX_DIR}/bin/postgresql/lib/" 2>/dev/null || true ;;
                esac
            done
        done
        # Share-Verzeichnis (Zeitzone, locale etc.)
        # initdb sucht unter <bindir>/../share/postgresql/, also share/postgresql/
        PG_SHAREDIR="$(pg_config --sharedir 2>/dev/null || echo /usr/share/postgresql)"
        if [ -d "$PG_SHAREDIR" ]; then
            mkdir -p "${LINUX_DIR}/bin/postgresql/share/postgresql"
            cp -r "$PG_SHAREDIR/"* "${LINUX_DIR}/bin/postgresql/share/postgresql/"
        fi
        # Extension-Libraries (dict_snowball etc., noetig fuer initdb)
        PG_PKGLIBDIR="$(pg_config --pkglibdir 2>/dev/null || echo /usr/lib/postgresql)"
        if [ -d "$PG_PKGLIBDIR" ]; then
            cp -r "$PG_PKGLIBDIR/"*.so "${LINUX_DIR}/bin/postgresql/lib/" 2>/dev/null || true
            # Bitcode-Verzeichnis (optional, fuer JIT)
            [ -d "$PG_PKGLIBDIR/bitcode" ] && cp -r "$PG_PKGLIBDIR/bitcode" "${LINUX_DIR}/bin/postgresql/lib/"
        fi
        # Symlink: postgres sucht $libdir unter lib/postgresql/ (pkglibdir)
        # Die .so-Dateien liegen direkt in lib/, also Symlink auf sich selbst
        ln -sfn . "${LINUX_DIR}/bin/postgresql/lib/postgresql"
        info "System-PostgreSQL $(pg_config --version) gebundelt"
    else
        tar xzf "${CACHE_DIR}/postgresql-linux-x64.tar.gz" \
            -C "${LINUX_DIR}/bin/postgresql" --strip-components=1
        info "EDB PostgreSQL ${POSTGRESQL_VERSION} entpackt"
    fi

    info "Erstelle Tarball..."
    tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-linux-x64.tar.gz" \
        -C "${LINUX_DIR}" .
    info "Linux-Paket: $(du -h "${DIST_DIR}/praxiszeit-${APP_VERSION}-linux-x64.tar.gz" | cut -f1)"
else
    step "4 — Linux: uebersprungen"
fi

# =============================================================================
# Phase 5: Windows-Paket
# =============================================================================

if [ "$BUILD_WINDOWS" = true ]; then
    step "5 — Windows-Paket (x64)"

    WIN_DIR="${BUILD_DIR}/windows"
    prepare_platform_dir "${WIN_DIR}"

    cp "${REPO_DIR}/installer/windows/install-service.bat" "${WIN_DIR}/"
    cp "${REPO_DIR}/installer/windows/uninstall-service.bat" "${WIN_DIR}/"
    cp "${REPO_DIR}/installer/windows/uninstall.bat" "${WIN_DIR}/"
    cp "${REPO_DIR}/installer/windows/backup.bat" "${WIN_DIR}/"
    cp "${REPO_DIR}/installer/windows/update-wizard.bat" "${WIN_DIR}/"
    cp "${REPO_DIR}/installer/windows/update-wizard.ps1" "${WIN_DIR}/"

    info "Entpacke Python ${PYTHON_VERSION} (Windows x64)..."
    mkdir -p "${WIN_DIR}/bin/python"
    tar xzf "${CACHE_DIR}/python-windows-x64.tar.gz" \
        -C "${WIN_DIR}/bin/python" --strip-components=1

    cp "${CACHE_DIR}/get-pip.py" "${WIN_DIR}/bin/python/"
    info "HINWEIS: Windows pip-Dependencies werden beim Install nachinstalliert"

    # ._pth Fix-Script
    cat > "${WIN_DIR}/bin/python/fix-pth.py" << 'PTHEOF'
"""Fix Python embeddable ._pth file to enable pip/site-packages."""
import glob, os, sys
pth_files = glob.glob(os.path.join(os.path.dirname(sys.executable), "python*._pth"))
for pth in pth_files:
    content = open(pth).read()
    if "#import site" in content:
        content = content.replace("#import site", "import site")
        open(pth, "w").write(content)
        print(f"Fixed: {pth}")
PTHEOF

    # PostgreSQL: EDB Installer (.exe) mitliefern — wird von setup.bat silent installiert
    if [ -f "${CACHE_DIR}/${PG_WINDOWS_INSTALLER}" ]; then
        info "Kopiere PostgreSQL-Installer ($(du -h "${CACHE_DIR}/${PG_WINDOWS_INSTALLER}" | cut -f1))..."
        cp "${CACHE_DIR}/${PG_WINDOWS_INSTALLER}" "${WIN_DIR}/bin/postgresql-installer.exe"
    else
        warn "Kein PostgreSQL-Installer im Paket — Kunde muss PostgreSQL manuell installieren"
    fi

    info "Entpacke nssm..."
    if command -v unzip &>/dev/null; then
        unzip -qo "${CACHE_DIR}/nssm.zip" -d "${BUILD_DIR}/tmp-nssm"
        # nssm ZIP kann verschiedene Verzeichnisnamen haben
        _nssm_exe=$(find "${BUILD_DIR}/tmp-nssm" -name "nssm.exe" -path "*/win64/*" 2>/dev/null | head -1)
        if [ -n "$_nssm_exe" ]; then
            cp "$_nssm_exe" "${WIN_DIR}/"
            info "nssm.exe kopiert"
        else
            warn "nssm.exe nicht im ZIP gefunden"
        fi
        rm -rf "${BUILD_DIR}/tmp-nssm"
    fi

    # Setup + Service Scripts aus dem Repo kopieren
    cp "${REPO_DIR}/installer/windows/setup.bat" "${WIN_DIR}/"

    # ========================================================================
    # Phase 5b: Avalonia GUI-Installer (setup.exe) mit eingebettetem Payload
    # ------------------------------------------------------------------------
    # Reihenfolge ist wichtig: erst das komplette Windows-Tree zusammenbauen,
    # dann als payload.zip packen, dann dotnet publish mit -p:PayloadZipPath
    # aufrufen — die EmbeddedResource im csproj zieht das ZIP rein, raus
    # kommt eine ~400 MB single-file setup.exe die zur Laufzeit nach %TEMP%
    # entpackt und setup.bat / update-wizard.ps1 -Headless aufruft.
    # ========================================================================
    _setup_exe_dist=""
    if command -v dotnet &>/dev/null; then
        info "Erzeuge Payload-ZIP fuer Embedding..."
        _payload_zip="${BUILD_DIR}/payload-${APP_VERSION}-windows-x64.zip"
        rm -f "${_payload_zip}"
        if command -v zip &>/dev/null; then
            (cd "${WIN_DIR}" && zip -qr "$_payload_zip" .)
        elif command -v powershell.exe &>/dev/null; then
            _payload_src_win="$(cygpath -w "${WIN_DIR}" 2>/dev/null || echo "${WIN_DIR}")"
            _payload_zip_win="$(cygpath -w "${_payload_zip}" 2>/dev/null || echo "${_payload_zip}")"
            powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \
                "Compress-Archive -Path '${_payload_src_win}\\*' -DestinationPath '${_payload_zip_win}' -Force -CompressionLevel Optimal"
        fi

        if [ -f "${_payload_zip}" ]; then
            info "Payload-ZIP: $(du -h "${_payload_zip}" | cut -f1) — baue setup.exe..."
            _setup_proj="${REPO_DIR}/installer/setup/src/PraxisZeit.Setup/PraxisZeit.Setup.csproj"
            _setup_publish="${BUILD_DIR}/tmp-setup-publish"
            rm -rf "${_setup_publish}"
            # Windows-Pfad fuer MSBuild-Property (sonst missparst Git-Bash den Pfad)
            _payload_zip_win="$(cygpath -w "${_payload_zip}" 2>/dev/null || echo "${_payload_zip}")"
            if dotnet publish "${_setup_proj}" \
                -c Release -r win-x64 \
                -p:PublishSingleFile=true \
                --self-contained true \
                -p:Version="${APP_VERSION}" \
                -p:PayloadZipPath="${_payload_zip_win}" \
                -o "${_setup_publish}" \
                > "${BUILD_DIR}/tmp-setup-publish.log" 2>&1; then
                # Naming-Pattern: praxiszeit-${VERSION}-* damit der sha256sum-Glob
                # in Phase 7 die EXE mit aufnimmt.
                _setup_exe_dist="${DIST_DIR}/praxiszeit-${APP_VERSION}-setup-windows-x64.exe"
                cp "${_setup_publish}/PraxisZeit.Setup.exe" "${_setup_exe_dist}"
                cp "${_setup_publish}/PraxisZeit.Setup.exe" "${WIN_DIR}/setup.exe"
                info "setup.exe: $(du -h "${_setup_exe_dist}" | cut -f1)"
                rm -rf "${_setup_publish}" "${BUILD_DIR}/tmp-setup-publish.log" "${_payload_zip}"
            else
                warn "dotnet publish setup.exe FEHLGESCHLAGEN — Log: ${BUILD_DIR}/tmp-setup-publish.log"
                warn "Paket wird ohne setup.exe gebaut (.bat-Fallback bleibt funktional)"
                rm -f "${_payload_zip}"
            fi
        else
            warn "Payload-ZIP konnte nicht erzeugt werden — setup.exe wird nicht gebaut"
        fi
    else
        warn "dotnet SDK nicht gefunden — setup.exe wird nicht gebaut (.bat-Fallback bleibt funktional)"
    fi

    info "Erstelle ZIP..."
    _win_zip="${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64.zip"
    if command -v zip &>/dev/null; then
        (cd "${WIN_DIR}" && zip -qr "$_win_zip" .)
    elif command -v powershell.exe &>/dev/null; then
        # Git Bash on Windows: use PowerShell Compress-Archive as fallback
        info "zip nicht verfuegbar — nutze PowerShell Compress-Archive"
        _win_src_win="$(cygpath -w "${WIN_DIR}" 2>/dev/null || echo "${WIN_DIR}")"
        _win_zip_win="$(cygpath -w "${_win_zip}" 2>/dev/null || echo "${_win_zip}")"
        powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \
            "Compress-Archive -Path '${_win_src_win}\\*' -DestinationPath '${_win_zip_win}' -Force -CompressionLevel Optimal"
    else
        tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64.tar.gz" -C "${WIN_DIR}" .
        warn "zip nicht verfuegbar — Windows-Paket als .tar.gz erstellt"
        _win_zip="${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64.tar.gz"
    fi
    info "Windows-Paket: $(du -h "$_win_zip" | cut -f1)"
    if [ -n "${_setup_exe_dist}" ] && [ -f "${_setup_exe_dist}" ]; then
        info "setup.exe (Standalone): $(du -h "${_setup_exe_dist}" | cut -f1)"
    fi
else
    step "5 — Windows: uebersprungen"
fi

# =============================================================================
# Phase 6: macOS-Pakete (Intel x64 + Apple Silicon arm64)
# =============================================================================

if [ "$BUILD_MACOS" = true ]; then
    step "6 — macOS-Pakete (Intel + Apple Silicon)"

    # Gemeinsamer macOS-Installer (install.sh) — wird in beide Pakete kopiert
    _write_macos_installer() {
        local target_dir="$1"
        cp "${REPO_DIR}/installer/macos/install.sh" "${target_dir}/install.sh"
        sed -i "s/@@VERSION@@/${APP_VERSION}/g" "${target_dir}/install.sh" 2>/dev/null || \
        sed -i'' "s/@@VERSION@@/${APP_VERSION}/g" "${target_dir}/install.sh"
        chmod +x "${target_dir}/install.sh"
    }

    # Funktion: Ein macOS-Paket bauen
    _build_macos_arch() {
        local arch="$1"       # x64 oder arm64
        local python_tar="$2" # Pfad zum Python-Tarball

        info "Baue macOS ${arch}..."
        local mac_dir="${BUILD_DIR}/macos-${arch}"
        prepare_platform_dir "${mac_dir}"

        # Python entpacken
        info "Entpacke Python ${PYTHON_VERSION} (macOS ${arch})..."
        mkdir -p "${mac_dir}/bin/python"
        tar xzf "${python_tar}" -C "${mac_dir}/bin/python" --strip-components=1

        # get-pip.py + requirements.txt mitliefern
        # pip install passiert beim Kunden (Cross-Platform von Linux nicht moeglich)
        cp "${CACHE_DIR}/get-pip.py" "${mac_dir}/bin/python/"

        # PostgreSQL: DMG-Installer mitliefern (silent install durch install.sh)
        if [ -f "${CACHE_DIR}/${PG_MACOS_INSTALLER}" ]; then
            info "Kopiere PostgreSQL-DMG ($(du -h "${CACHE_DIR}/${PG_MACOS_INSTALLER}" | cut -f1))..."
            cp "${CACHE_DIR}/${PG_MACOS_INSTALLER}" "${mac_dir}/bin/postgresql-installer.dmg"
        else
            warn "Kein PostgreSQL-DMG — Kunde muss PostgreSQL manuell installieren"
        fi

        _write_macos_installer "${mac_dir}"

        tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-${arch}.tar.gz" -C "${mac_dir}" .
        info "macOS ${arch}: $(du -h "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-${arch}.tar.gz" | cut -f1)"
    }

    _build_macos_arch "x64"   "${CACHE_DIR}/python-macos-x64.tar.gz"
    _build_macos_arch "arm64" "${CACHE_DIR}/python-macos-arm64.tar.gz"
else
    step "6 — macOS: uebersprungen"
fi

# =============================================================================
# Phase 7: Checksums + Zusammenfassung
# =============================================================================

step "7 — Pruefsummen + Zusammenfassung"

(cd "${DIST_DIR}" && sha256sum praxiszeit-${APP_VERSION}-* > "praxiszeit-${APP_VERSION}-SHA256SUMS.txt" 2>/dev/null || true)
if [ -f "${DIST_DIR}/praxiszeit-${APP_VERSION}-SHA256SUMS.txt" ]; then
    cat "${DIST_DIR}/praxiszeit-${APP_VERSION}-SHA256SUMS.txt"
fi

echo ""
echo "=============================================="
echo -e "  ${GREEN}Release v${APP_VERSION} gebaut!${NC}"
echo "=============================================="
echo ""
echo "  Pakete:"
ls -lh "${DIST_DIR}/praxiszeit-${APP_VERSION}-"* 2>/dev/null | while read line; do
    echo "    $line"
done
echo ""
echo "  Cache (wiederverwendbar mit --skip-download):"
echo "    ${CACHE_DIR}/ ($(du -sh "${CACHE_DIR}" | cut -f1))"
echo ""

$BUILD_LINUX && cat << EOF
  Linux-Installation:
    tar xzf praxiszeit-${APP_VERSION}-linux-x64.tar.gz
    sudo ./install.sh

EOF

$BUILD_WINDOWS && cat << EOF
  Windows-Installation/Update (empfohlen, ab 1.4.0):
    1. ZIP entpacken
    2. setup.exe (als Administrator) doppelklicken
       -> erkennt automatisch Erstinstallation, Update oder Reparatur

  Windows-Erstinstallation (.bat-Fallback):
    1. ZIP entpacken nach C:\\PraxisZeit\\
    2. setup.bat (als Administrator) ausfuehren
    3. install-service.bat ausfuehren (Dienst + Firewall + Backup-Task)
    4. net start PraxisZeit

  Windows-Update einer bestehenden Installation (.bat-Fallback):
    1. ZIP in einen TEMP-Ordner entpacken (NICHT ueber die Installation!)
    2. update-wizard.bat (als Administrator) ausfuehren
       -> GUI-Wizard: ACL-Fix, Backup, Stop, Copy, Start, Backup-Task

EOF

$BUILD_MACOS && cat << EOF
  macOS-Installation (Intel ODER Apple Silicon):
    tar xzf praxiszeit-${APP_VERSION}-macos-{x64|arm64}.tar.gz
    sudo ./install.sh

EOF
