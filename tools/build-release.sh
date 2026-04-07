#!/bin/bash
# PraxisZeit Release Builder
# Baut Installer-Pakete fuer Linux und Windows mit gebuendelten Binaries.
#
# Usage:
#   bash tools/build-release.sh                    # Build beide Plattformen
#   bash tools/build-release.sh --linux-only       # Nur Linux
#   bash tools/build-release.sh --windows-only     # Nur Windows
#   bash tools/build-release.sh --skip-download    # Binaries nicht neu laden (cache)
#   bash tools/build-release.sh --version 1.3.0    # Versionsnummer setzen
set -euo pipefail

# =============================================================================
# Konfiguration — Versionen der gebuendelten Binaries
# =============================================================================

APP_VERSION="1.2.0"
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
SKIP_DOWNLOAD=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --linux-only)   BUILD_WINDOWS=false; shift ;;
        --windows-only) BUILD_LINUX=false; shift ;;
        --skip-download) SKIP_DOWNLOAD=true; shift ;;
        --version)      APP_VERSION="$2"; shift 2 ;;
        *)              APP_VERSION="$1"; shift ;;
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

echo ""
echo "=============================================="
echo "  PraxisZeit Release Builder"
echo "  App: v${APP_VERSION}"
echo "  Python: ${PYTHON_VERSION}"
echo "  PostgreSQL: ${POSTGRESQL_VERSION}"
echo "=============================================="
echo ""

# =============================================================================
# Download-URLs
# =============================================================================

# python-build-standalone (indygreg/astral-sh)
# Releases: https://github.com/indygreg/python-build-standalone/releases
PYTHON_LINUX_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PYTHON_STANDALONE_TAG}/cpython-${PYTHON_VERSION}+${PYTHON_STANDALONE_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"
PYTHON_WINDOWS_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PYTHON_STANDALONE_TAG}/cpython-${PYTHON_VERSION}+${PYTHON_STANDALONE_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz"

# EnterpriseDB PostgreSQL Binaries
# Download-Seite: https://www.enterprisedb.com/download-postgresql-binaries
PG_LINUX_URL="https://get.enterprisedb.com/postgresql/postgresql-${POSTGRESQL_VERSION}-${POSTGRESQL_EDB_SUFFIX}-linux-x64-binaries.tar.gz"
PG_WINDOWS_URL="https://get.enterprisedb.com/postgresql/postgresql-${POSTGRESQL_VERSION}-${POSTGRESQL_EDB_SUFFIX}-windows-x64-binaries.zip"

# nssm (Windows Service Manager)
NSSM_URL="https://nssm.cc/release/nssm-${NSSM_VERSION}.zip"

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

# =============================================================================
# Phase 1: Cleanup + Frontend
# =============================================================================

step "1/7 — Cleanup + Frontend bauen"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}" "${DIST_DIR}" "${CACHE_DIR}"

if [ -d "${REPO_DIR}/frontend/dist" ]; then
    info "Frontend-Build vorhanden, ueberspringe npm build"
else
    info "Baue Frontend..."
    (cd "${REPO_DIR}/frontend" && npm ci && npm run build)
fi

# =============================================================================
# Phase 2: Gemeinsame App-Dateien vorbereiten
# =============================================================================

step "2/7 — App-Dateien vorbereiten"

mkdir -p "${BUILD_DIR}/common/app/backend"
# Backend (ohne __pycache__, .pyc, tests)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='tests/' \
    "${REPO_DIR}/backend/app" "${BUILD_DIR}/common/app/backend/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' \
    "${REPO_DIR}/backend/alembic" "${BUILD_DIR}/common/app/backend/"
cp "${REPO_DIR}/backend/alembic.ini" "${BUILD_DIR}/common/app/backend/"
cp "${REPO_DIR}/backend/init-db-user.sql" "${BUILD_DIR}/common/app/backend/"
cp "${REPO_DIR}/backend/requirements.txt" "${BUILD_DIR}/common/app/backend/"

# Frontend dist
mkdir -p "${BUILD_DIR}/common/app/frontend"
cp -r "${REPO_DIR}/frontend/dist/"* "${BUILD_DIR}/common/app/frontend/"

# Process Manager + Config
cp "${REPO_DIR}/praxiszeit-server.py" "${BUILD_DIR}/common/"
mkdir -p "${BUILD_DIR}/common/config"
cp "${REPO_DIR}/installer/praxiszeit.conf.example" "${BUILD_DIR}/common/config/"

info "App-Dateien: $(du -sh "${BUILD_DIR}/common" | cut -f1)"

# =============================================================================
# Phase 3: Binaries herunterladen
# =============================================================================

step "3/7 — Binaries herunterladen"

if [ "$BUILD_LINUX" = true ]; then
    download "$PYTHON_LINUX_URL"  "${CACHE_DIR}/python-linux.tar.gz"
    download "$PG_LINUX_URL"      "${CACHE_DIR}/postgresql-linux.tar.gz"
fi

if [ "$BUILD_WINDOWS" = true ]; then
    download "$PYTHON_WINDOWS_URL" "${CACHE_DIR}/python-windows.tar.gz"
    download "$PG_WINDOWS_URL"     "${CACHE_DIR}/postgresql-windows.zip"
    download "$NSSM_URL"           "${CACHE_DIR}/nssm.zip"
    download "$GET_PIP_URL"        "${CACHE_DIR}/get-pip.py"
fi

# =============================================================================
# Phase 4: Linux-Paket
# =============================================================================

if [ "$BUILD_LINUX" = true ]; then
    step "4/7 — Linux-Paket bauen"

    LINUX_DIR="${BUILD_DIR}/linux"
    mkdir -p "${LINUX_DIR}"

    # App-Dateien
    cp -r "${BUILD_DIR}/common/"* "${LINUX_DIR}/"

    # Installer
    cp "${REPO_DIR}/installer/linux/install.sh" "${LINUX_DIR}/"
    chmod +x "${LINUX_DIR}/install.sh"

    # Python entpacken
    info "Entpacke Python ${PYTHON_VERSION} (Linux)..."
    mkdir -p "${LINUX_DIR}/bin/python"
    tar xzf "${CACHE_DIR}/python-linux.tar.gz" \
        -C "${LINUX_DIR}/bin/python" --strip-components=1

    # pip-Dependencies vorinstallieren
    info "Installiere pip-Dependencies..."
    "${LINUX_DIR}/bin/python/bin/python3" -m pip install -q \
        --target="${LINUX_DIR}/bin/python/lib/python${PYTHON_VERSION%.*}/site-packages" \
        -r "${LINUX_DIR}/app/backend/requirements.txt" 2>&1 | tail -3

    # PostgreSQL entpacken
    info "Entpacke PostgreSQL ${POSTGRESQL_VERSION} (Linux)..."
    mkdir -p "${LINUX_DIR}/bin/postgresql"
    tar xzf "${CACHE_DIR}/postgresql-linux.tar.gz" \
        -C "${LINUX_DIR}/bin/postgresql" --strip-components=1

    # Leere Verzeichnisse fuer Runtime-Daten
    mkdir -p "${LINUX_DIR}/data/db" "${LINUX_DIR}/data/backups"
    mkdir -p "${LINUX_DIR}/config/ssl" "${LINUX_DIR}/logs"

    # Paket schnueren
    info "Erstelle Tarball..."
    tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-linux-x64.tar.gz" \
        -C "${LINUX_DIR}" .
    info "Linux-Paket: $(du -h "${DIST_DIR}/praxiszeit-${APP_VERSION}-linux-x64.tar.gz" | cut -f1)"
else
    step "4/7 — Linux-Paket: uebersprungen"
fi

# =============================================================================
# Phase 5: Windows-Paket
# =============================================================================

if [ "$BUILD_WINDOWS" = true ]; then
    step "5/7 — Windows-Paket bauen"

    WIN_DIR="${BUILD_DIR}/windows"
    mkdir -p "${WIN_DIR}"

    # App-Dateien
    cp -r "${BUILD_DIR}/common/"* "${WIN_DIR}/"

    # Windows Service Scripts
    cp "${REPO_DIR}/installer/windows/install-service.bat" "${WIN_DIR}/"
    cp "${REPO_DIR}/installer/windows/uninstall-service.bat" "${WIN_DIR}/"

    # Python entpacken
    info "Entpacke Python ${PYTHON_VERSION} (Windows)..."
    mkdir -p "${WIN_DIR}/bin/python"
    tar xzf "${CACHE_DIR}/python-windows.tar.gz" \
        -C "${WIN_DIR}/bin/python" --strip-components=1

    # get-pip.py fuer spaetere pip-Bootstrap durch den Installer
    cp "${CACHE_DIR}/get-pip.py" "${WIN_DIR}/bin/python/"

    # pip-Dependencies koennen unter Linux NICHT fuer Windows vorinstalliert
    # werden (plattformspezifische Wheels). Stattdessen: requirements.txt +
    # get-pip.py mitliefern, der Windows-Installer fuehrt pip install aus.
    info "HINWEIS: Windows pip-Dependencies werden beim Install nachinstalliert"

    # ._pth Fix-Script fuer Python embeddable (muss beim Install laufen)
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

    # PostgreSQL entpacken
    info "Entpacke PostgreSQL ${POSTGRESQL_VERSION} (Windows)..."
    mkdir -p "${WIN_DIR}/bin/postgresql"
    # EDB Windows ZIP hat Struktur: pgsql/bin, pgsql/lib, etc.
    if command -v unzip &>/dev/null; then
        unzip -qo "${CACHE_DIR}/postgresql-windows.zip" -d "${BUILD_DIR}/tmp-pg-win"
        cp -r "${BUILD_DIR}/tmp-pg-win/pgsql/"* "${WIN_DIR}/bin/postgresql/"
        rm -rf "${BUILD_DIR}/tmp-pg-win"
    else
        warn "unzip nicht verfuegbar, PostgreSQL-ZIP muss manuell entpackt werden"
        cp "${CACHE_DIR}/postgresql-windows.zip" "${WIN_DIR}/bin/"
    fi

    # nssm entpacken
    info "Entpacke nssm ${NSSM_VERSION}..."
    if command -v unzip &>/dev/null; then
        unzip -qo "${CACHE_DIR}/nssm.zip" -d "${BUILD_DIR}/tmp-nssm"
        cp "${BUILD_DIR}/tmp-nssm/nssm-${NSSM_VERSION}/win64/nssm.exe" "${WIN_DIR}/"
        rm -rf "${BUILD_DIR}/tmp-nssm"
    else
        warn "unzip nicht verfuegbar, nssm muss manuell entpackt werden"
    fi

    # Leere Verzeichnisse
    mkdir -p "${WIN_DIR}/data/db" "${WIN_DIR}/data/backups"
    mkdir -p "${WIN_DIR}/config/ssl" "${WIN_DIR}/logs"

    # Windows-Install-Script das pip bootstrapped
    cat > "${WIN_DIR}/setup.bat" << 'SETUPEOF'
@echo off
echo PraxisZeit Setup - Installiere Abhaengigkeiten...
echo.

SET DIR=%~dp0
SET PYTHON=%DIR%bin\python\python.exe

REM Fix Python ._pth fuer pip/site-packages
"%PYTHON%" "%DIR%bin\python\fix-pth.py"

REM pip installieren
echo Installiere pip...
"%PYTHON%" "%DIR%bin\python\get-pip.py" --quiet

REM Dependencies installieren
echo Installiere Python-Abhaengigkeiten (kann einige Minuten dauern)...
"%PYTHON%" -m pip install --quiet -r "%DIR%app\backend\requirements.txt"

echo.
echo Abhaengigkeiten installiert.
echo Starten Sie jetzt install-service.bat um den Windows-Dienst einzurichten.
pause
SETUPEOF

    # Paket schnueren
    info "Erstelle ZIP..."
    if command -v zip &>/dev/null; then
        (cd "${WIN_DIR}" && zip -qr "../../${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64.zip" .)
    else
        # Fallback: tar.gz statt zip
        tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64.tar.gz" \
            -C "${WIN_DIR}" .
        warn "zip nicht verfuegbar, Windows-Paket als .tar.gz erstellt"
    fi
    info "Windows-Paket: $(ls -lh "${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64."* | awk '{print $5}')"
else
    step "5/7 — Windows-Paket: uebersprungen"
fi

# =============================================================================
# Phase 6: Checksums
# =============================================================================

step "6/7 — Pruefsummen"

(cd "${DIST_DIR}" && sha256sum praxiszeit-${APP_VERSION}-* > "praxiszeit-${APP_VERSION}-SHA256SUMS.txt" 2>/dev/null || true)
if [ -f "${DIST_DIR}/praxiszeit-${APP_VERSION}-SHA256SUMS.txt" ]; then
    cat "${DIST_DIR}/praxiszeit-${APP_VERSION}-SHA256SUMS.txt"
fi

# =============================================================================
# Phase 7: Zusammenfassung
# =============================================================================

step "7/7 — Fertig"

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

if [ "$BUILD_WINDOWS" = true ]; then
    echo "  Windows-Installation:"
    echo "    1. ZIP entpacken nach C:\\PraxisZeit\\"
    echo "    2. setup.bat ausfuehren (installiert Python-Dependencies)"
    echo "    3. install-service.bat ausfuehren (registriert Windows-Dienst)"
    echo "    4. net start PraxisZeit"
    echo ""
fi

if [ "$BUILD_LINUX" = true ]; then
    echo "  Linux-Installation:"
    echo "    1. tar xzf praxiszeit-${APP_VERSION}-linux-x64.tar.gz"
    echo "    2. sudo ./install.sh"
    echo ""
fi
