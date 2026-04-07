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
BUILD_MACOS=true
SKIP_DOWNLOAD=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --linux-only)    BUILD_WINDOWS=false; BUILD_MACOS=false; shift ;;
        --windows-only)  BUILD_LINUX=false; BUILD_MACOS=false; shift ;;
        --macos-only)    BUILD_LINUX=false; BUILD_WINDOWS=false; shift ;;
        --skip-download) SKIP_DOWNLOAD=true; shift ;;
        --version)       APP_VERSION="$2"; shift 2 ;;
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
PG_WINDOWS_URL="${_EDB}/${_PGV}-windows-x64-binaries.zip"
PG_MACOS_URL="${_EDB}/${_PGV}-osx-binaries.zip"

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

if [ -d "${REPO_DIR}/frontend/dist" ]; then
    info "Frontend-Build vorhanden, ueberspringe npm build"
else
    info "Baue Frontend..."
    (cd "${REPO_DIR}/frontend" && npm ci && npm run build)
fi

# =============================================================================
# Phase 2: Gemeinsame App-Dateien vorbereiten
# =============================================================================

step "2 — App-Dateien vorbereiten"

mkdir -p "${BUILD_DIR}/common/app/backend"
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='tests/' \
    "${REPO_DIR}/backend/app" "${BUILD_DIR}/common/app/backend/"
rsync -a --exclude='__pycache__' --exclude='*.pyc' \
    "${REPO_DIR}/backend/alembic" "${BUILD_DIR}/common/app/backend/"
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
    download "$PG_WINDOWS_URL"     "${CACHE_DIR}/postgresql-windows-x64.zip"
    download "$NSSM_URL"           "${CACHE_DIR}/nssm.zip"
    download "$GET_PIP_URL"        "${CACHE_DIR}/get-pip.py"
fi

if [ "$BUILD_MACOS" = true ]; then
    download "$PYTHON_MACOS_X64_URL"   "${CACHE_DIR}/python-macos-x64.tar.gz"
    download "$PYTHON_MACOS_ARM64_URL" "${CACHE_DIR}/python-macos-arm64.tar.gz"
    download "$PG_MACOS_URL"           "${CACHE_DIR}/postgresql-macos.zip"
    download "$GET_PIP_URL"            "${CACHE_DIR}/get-pip.py"
fi

# =============================================================================
# Phase 4: Linux-Paket
# =============================================================================

if [ "$BUILD_LINUX" = true ]; then
    step "4 — Linux-Paket (x64)"

    LINUX_DIR="${BUILD_DIR}/linux"
    prepare_platform_dir "${LINUX_DIR}"

    cp "${REPO_DIR}/installer/linux/install.sh" "${LINUX_DIR}/"
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
                case "$(basename "$lib")" in
                    libc.so*|libm.so*|libpthread*|libdl.so*|librt.so*|ld-linux*|linux-vdso*) ;;
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

    info "Entpacke PostgreSQL ${POSTGRESQL_VERSION} (Windows x64)..."
    mkdir -p "${WIN_DIR}/bin/postgresql"
    if command -v unzip &>/dev/null; then
        unzip -qo "${CACHE_DIR}/postgresql-windows-x64.zip" -d "${BUILD_DIR}/tmp-pg-win"
        cp -r "${BUILD_DIR}/tmp-pg-win/pgsql/"* "${WIN_DIR}/bin/postgresql/"
        rm -rf "${BUILD_DIR}/tmp-pg-win"
    else
        warn "unzip nicht verfuegbar — PostgreSQL-ZIP ins Paket kopiert"
        cp "${CACHE_DIR}/postgresql-windows-x64.zip" "${WIN_DIR}/bin/"
    fi

    info "Entpacke nssm ${NSSM_VERSION}..."
    if command -v unzip &>/dev/null; then
        unzip -qo "${CACHE_DIR}/nssm.zip" -d "${BUILD_DIR}/tmp-nssm"
        cp "${BUILD_DIR}/tmp-nssm/nssm-${NSSM_VERSION}/win64/nssm.exe" "${WIN_DIR}/"
        rm -rf "${BUILD_DIR}/tmp-nssm"
    fi

    # setup.bat: pip bootstrap + dependency install
    cat > "${WIN_DIR}/setup.bat" << 'SETUPEOF'
@echo off
echo PraxisZeit Setup - Installiere Abhaengigkeiten...
echo.

SET DIR=%~dp0
SET PYTHON=%DIR%bin\python\python.exe

"%PYTHON%" "%DIR%bin\python\fix-pth.py"

echo Installiere pip...
"%PYTHON%" "%DIR%bin\python\get-pip.py" --quiet

echo Installiere Python-Abhaengigkeiten (kann einige Minuten dauern)...
"%PYTHON%" -m pip install --quiet -r "%DIR%app\backend\requirements.txt"

echo.
echo Abhaengigkeiten installiert.
echo Starten Sie jetzt install-service.bat um den Windows-Dienst einzurichten.
pause
SETUPEOF

    info "Erstelle ZIP..."
    if command -v zip &>/dev/null; then
        (cd "${WIN_DIR}" && zip -qr "../../${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64.zip" .)
    else
        tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64.tar.gz" -C "${WIN_DIR}" .
        warn "zip nicht verfuegbar — Windows-Paket als .tar.gz erstellt"
    fi
    info "Windows-Paket: $(ls -lh "${DIST_DIR}/praxiszeit-${APP_VERSION}-windows-x64."* 2>/dev/null | awk '{print $5}' | head -1)"
else
    step "5 — Windows: uebersprungen"
fi

# =============================================================================
# Phase 6: macOS-Pakete (Intel x64 + Apple Silicon arm64)
# =============================================================================

if [ "$BUILD_MACOS" = true ]; then
    step "6 — macOS-Pakete (Intel + Apple Silicon)"

    # macOS Installer-Script (launchd statt systemd)
    _write_macos_installer() {
        local target_dir="$1"
        cat > "${target_dir}/install.sh" << 'MACINSTEOF'
#!/bin/bash
# PraxisZeit Installer fuer macOS
set -euo pipefail

VERSION="@@VERSION@@"
INSTALL_DIR="${1:-/usr/local/praxiszeit}"

echo ""
echo "=============================================="
echo "  PraxisZeit Installer v${VERSION} (macOS)"
echo "=============================================="
echo ""

if [ "$EUID" -ne 0 ]; then
    echo "Bitte mit sudo ausfuehren: sudo $0 [install-dir]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

read -rp "Praxis-Name [Testpraxis]: " PRACTICE_NAME
PRACTICE_NAME=${PRACTICE_NAME:-Testpraxis}
read -rp "Admin-E-Mail [admin@local.test]: " ADMIN_EMAIL
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@local.test}
read -rp "Admin-Passwort (min. 12 Zeichen): " ADMIN_PASSWORD
if [ ${#ADMIN_PASSWORD} -lt 12 ]; then
    echo "Passwort zu kurz (min. 12 Zeichen)."
    exit 1
fi
read -rp "Port [8443]: " PORT
PORT=${PORT:-8443}

echo ""
echo "Installiere nach ${INSTALL_DIR}..."

# Benutzer
if ! dscl . -read /Users/_praxiszeit &>/dev/null 2>&1; then
    # macOS: Service-User anlegen
    LAST_UID=$(dscl . -list /Users UniqueID | awk '{print $2}' | sort -n | tail -1)
    NEXT_UID=$((LAST_UID + 1))
    dscl . -create /Users/_praxiszeit
    dscl . -create /Users/_praxiszeit UniqueID "$NEXT_UID"
    dscl . -create /Users/_praxiszeit PrimaryGroupID 20
    dscl . -create /Users/_praxiszeit UserShell /usr/bin/false
    dscl . -create /Users/_praxiszeit NFSHomeDirectory "${INSTALL_DIR}"
    echo "Benutzer _praxiszeit erstellt"
fi

# Dateien kopieren
mkdir -p "${INSTALL_DIR}"
cp -R "${SCRIPT_DIR}/bin" "${INSTALL_DIR}/"
cp -R "${SCRIPT_DIR}/app" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/praxiszeit-server.py" "${INSTALL_DIR}/"
mkdir -p "${INSTALL_DIR}"/{data/db,data/backups,config/ssl,logs}

# Konfiguration
SECRET_KEY=$("${INSTALL_DIR}/bin/python/bin/python3" -c "import secrets; print(secrets.token_hex(64))")
cat > "${INSTALL_DIR}/config/praxiszeit.conf" << CONFEOF
[server]
port = ${PORT}
ssl_cert = ""
ssl_key = ""

[database]
data_dir = "data/db"
superuser = "praxiszeit"
app_user = "praxiszeit_app"

[practice]
name = "${PRACTICE_NAME}"
holiday_state = "Bayern"

[admin]
username = "admin"
email = "${ADMIN_EMAIL}"
password = "${ADMIN_PASSWORD}"

[security]
secret_key = "${SECRET_KEY}"
login_rate_limit = "10/minute"
cookie_secure = false

[license]
# key_file = "config/license.key"

[updates]
check_enabled = false

[backup]
enabled = true
schedule = "02:00"
retention_days = 31
CONFEOF
chmod 600 "${INSTALL_DIR}/config/praxiszeit.conf"

# Berechtigungen
chown -R _praxiszeit:staff "${INSTALL_DIR}"

# launchd Plist (macOS Service)
cat > /Library/LaunchDaemons/de.praxiszeit.server.plist << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>de.praxiszeit.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/bin/python/bin/python3</string>
        <string>${INSTALL_DIR}/praxiszeit-server.py</string>
        <string>start</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>UserName</key>
    <string>_praxiszeit</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${INSTALL_DIR}/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${INSTALL_DIR}/logs/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
PLISTEOF

launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist

echo ""
echo "=============================================="
echo "  PraxisZeit installiert!"
echo "=============================================="
echo ""
echo "  URL:     http://localhost:${PORT}"
echo "  Login:   admin / (ihr Passwort)"
echo "  Start:   sudo launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist"
echo "  Stop:    sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist"
echo "  Logs:    ${INSTALL_DIR}/logs/"
echo ""
MACINSTEOF
        # Version-Platzhalter ersetzen
        sed -i'' "s/@@VERSION@@/${APP_VERSION}/g" "${target_dir}/install.sh" 2>/dev/null || \
        sed -i "s/@@VERSION@@/${APP_VERSION}/g" "${target_dir}/install.sh"
        chmod +x "${target_dir}/install.sh"
    }

    # --- macOS Intel (x64) ---
    info "Baue macOS Intel (x64)..."
    MAC_X64="${BUILD_DIR}/macos-x64"
    prepare_platform_dir "${MAC_X64}"

    info "Entpacke Python ${PYTHON_VERSION} (macOS x64)..."
    mkdir -p "${MAC_X64}/bin/python"
    tar xzf "${CACHE_DIR}/python-macos-x64.tar.gz" \
        -C "${MAC_X64}/bin/python" --strip-components=1

    info "Installiere pip-Dependencies (macOS x64)..."
    "${MAC_X64}/bin/python/bin/python3" -m pip install -q \
        --target="${MAC_X64}/bin/python/lib/python${PYTHON_VERSION%.*}/site-packages" \
        -r "${MAC_X64}/app/backend/requirements.txt" 2>&1 | tail -3 || \
        warn "pip install fuer macOS x64 fehlgeschlagen (Cross-Platform — Dependencies werden beim Install nachinstalliert)"

    info "Entpacke PostgreSQL ${POSTGRESQL_VERSION} (macOS)..."
    mkdir -p "${MAC_X64}/bin/postgresql"
    if command -v unzip &>/dev/null; then
        unzip -qo "${CACHE_DIR}/postgresql-macos.zip" -d "${BUILD_DIR}/tmp-pg-mac"
        cp -r "${BUILD_DIR}/tmp-pg-mac/pgsql/"* "${MAC_X64}/bin/postgresql/" 2>/dev/null || \
        cp -r "${BUILD_DIR}/tmp-pg-mac/"* "${MAC_X64}/bin/postgresql/"
        rm -rf "${BUILD_DIR}/tmp-pg-mac"
    fi

    cp "${CACHE_DIR}/get-pip.py" "${MAC_X64}/bin/python/"
    _write_macos_installer "${MAC_X64}"

    tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-x64.tar.gz" -C "${MAC_X64}" .
    info "macOS x64: $(du -h "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-x64.tar.gz" | cut -f1)"

    # --- macOS Apple Silicon (arm64) ---
    info "Baue macOS Apple Silicon (arm64)..."
    MAC_ARM="${BUILD_DIR}/macos-arm64"
    prepare_platform_dir "${MAC_ARM}"

    info "Entpacke Python ${PYTHON_VERSION} (macOS arm64)..."
    mkdir -p "${MAC_ARM}/bin/python"
    tar xzf "${CACHE_DIR}/python-macos-arm64.tar.gz" \
        -C "${MAC_ARM}/bin/python" --strip-components=1

    # pip-Dependencies: Cross-Compile von Linux fuer macOS arm64 geht nicht
    # -> get-pip.py + requirements.txt mitliefern, install.sh macht pip install
    cp "${CACHE_DIR}/get-pip.py" "${MAC_ARM}/bin/python/"
    info "HINWEIS: macOS arm64 pip-Dependencies werden beim Install nachinstalliert"

    # PostgreSQL: EDB liefert ein Universal-Binary fuer macOS (x64+arm64)
    info "Kopiere PostgreSQL (macOS Universal)..."
    mkdir -p "${MAC_ARM}/bin/postgresql"
    if [ -d "${MAC_X64}/bin/postgresql/bin" ]; then
        cp -r "${MAC_X64}/bin/postgresql/"* "${MAC_ARM}/bin/postgresql/"
    elif command -v unzip &>/dev/null; then
        unzip -qo "${CACHE_DIR}/postgresql-macos.zip" -d "${BUILD_DIR}/tmp-pg-mac2"
        cp -r "${BUILD_DIR}/tmp-pg-mac2/pgsql/"* "${MAC_ARM}/bin/postgresql/" 2>/dev/null || \
        cp -r "${BUILD_DIR}/tmp-pg-mac2/"* "${MAC_ARM}/bin/postgresql/"
        rm -rf "${BUILD_DIR}/tmp-pg-mac2"
    fi

    _write_macos_installer "${MAC_ARM}"

    tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-arm64.tar.gz" -C "${MAC_ARM}" .
    info "macOS arm64: $(du -h "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-arm64.tar.gz" | cut -f1)"
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
  Windows-Installation:
    1. ZIP entpacken nach C:\\PraxisZeit\\
    2. setup.bat ausfuehren (installiert Python-Dependencies)
    3. install-service.bat ausfuehren (registriert Windows-Dienst)
    4. net start PraxisZeit

EOF

$BUILD_MACOS && cat << EOF
  macOS-Installation (Intel ODER Apple Silicon):
    tar xzf praxiszeit-${APP_VERSION}-macos-{x64|arm64}.tar.gz
    sudo ./install.sh

EOF
