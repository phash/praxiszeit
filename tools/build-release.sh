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

APP_VERSION="1.8.15"
PYTHON_VERSION="3.13.13"
# python-build-standalone Release-Tag (Format: YYYYMMDD)
# 20260510 buendelt CPython 3.13.13 — enthaelt die tarfile-Fixes
# (CVE-2025-4517 u.a.) gegenueber dem alten 3.13.3 (Tag 20250529).
PYTHON_STANDALONE_TAG="20260510"
# theseus-rs/postgresql-binaries — manylinux-Build, portable bis glibc 2.34
# (Ubuntu 22.04, Debian 12, RHEL 9 und neuer). Releases:
#   https://github.com/theseus-rs/postgresql-binaries/releases
POSTGRESQL_VERSION="16.13.0"
# EDB-Format (für Legacy-Fallback, falls jemals wieder verfügbar)
POSTGRESQL_EDB_SUFFIX="1"
NSSM_VERSION="2.24"

# =============================================================================
# CLI-Argumente
# =============================================================================

BUILD_LINUX=true
BUILD_WINDOWS=true
BUILD_MACOS=true
BUILD_DOCKER=true
SKIP_DOWNLOAD=false
SKIP_FRONTEND=false
# #81: GUI-Installer (Avalonia setup.exe) steuern.
SKIP_SETUP=false     # Payload bauen, aber KEINE setup.exe (dotnet fehlt/kaputt)
SETUP_ONLY=false     # nur die Windows-setup.exe iterieren (kein separates payload-ZIP)

while [[ $# -gt 0 ]]; do
    case "$1" in
        --linux-only)    BUILD_WINDOWS=false; BUILD_MACOS=false; BUILD_DOCKER=false; shift ;;
        --windows-only)  BUILD_LINUX=false; BUILD_MACOS=false; BUILD_DOCKER=false; shift ;;
        --macos-only)    BUILD_LINUX=false; BUILD_WINDOWS=false; BUILD_DOCKER=false; shift ;;
        --docker-only)   BUILD_LINUX=false; BUILD_WINDOWS=false; BUILD_MACOS=false; shift ;;
        # #81: nur die Windows-setup.exe (fuer schnelle Installer-Iteration) —
        # baut den Windows-Payload-Tree + setup.exe, ueberspringt Linux/macOS/Docker
        # UND das separate windows-x64.zip (Payload steckt bereits in der setup.exe).
        --setup-only)    SETUP_ONLY=true; BUILD_LINUX=false; BUILD_MACOS=false; BUILD_DOCKER=false; BUILD_WINDOWS=true; shift ;;
        --skip-setup)    SKIP_SETUP=true; shift ;;
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
  --docker-only      Build nur das Docker-Bundle (compose + Build-Kontext)
  --setup-only       Nur die Windows-GUI-setup.exe iterieren (Windows-Payload +
                     setup.exe; ohne Linux/macOS/Docker UND ohne windows-x64.zip)
  --skip-setup       Payload bauen, aber KEINE setup.exe (z. B. wenn .NET fehlt
                     oder der Installer-Build kaputt ist; .bat-Fallback bleibt)
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

# BETA_MODE-Hinweis: solange Default True, ist die Lizenzpruefung in JEDEM
# gebauten Paket deaktiviert (keine Lizenz noetig). Das ist in der Beta gewollt,
# aber vor dem ersten KOSTENPFLICHTIGEN Release MUSS BETA_MODE auf False —
# sonst laeuft jede Installation dauerhaft ohne Lizenzdurchsetzung. Laut warnen,
# damit es beim GA-Build nicht uebersehen wird (nicht abbrechen — Beta-Builds
# sind legitim).
if grep -qE '^\s*BETA_MODE:\s*bool\s*=\s*True' "${REPO_DIR_PRE}/backend/app/config.py" 2>/dev/null; then
    echo -e "${YELLOW}[WARN]${NC} BETA_MODE=True -> Lizenzpruefung in diesem Build DEAKTIVIERT (keine Lizenz noetig)." >&2
    echo -e "${YELLOW}[WARN]${NC} Fuer ein kostenpflichtiges Release vorher backend/app/config.py BETA_MODE=False setzen." >&2
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

# PostgreSQL Binaries — theseus-rs/postgresql-binaries (manylinux-Builds)
# Primärquelle. Forward-kompatibel bis glibc 2.34 (Ubuntu 22.04+, Debian 12+, RHEL 9+).
# Tarball-Layout: postgresql-<ver>-<triple>/{bin,lib,share,include}/
# SHA256 wird vom Repo mit .sha256-Suffix bereitgestellt.
_THESEUS="https://github.com/theseus-rs/postgresql-binaries/releases/download/${POSTGRESQL_VERSION}"

PG_LINUX_URL="${_THESEUS}/postgresql-${POSTGRESQL_VERSION}-x86_64-unknown-linux-gnu.tar.gz"
PG_LINUX_SHA_URL="${_THESEUS}/postgresql-${POSTGRESQL_VERSION}-x86_64-unknown-linux-gnu.tar.gz.sha256"
PG_LINUX_ARM64_URL="${_THESEUS}/postgresql-${POSTGRESQL_VERSION}-aarch64-unknown-linux-gnu.tar.gz"
PG_LINUX_ARM64_SHA_URL="${_THESEUS}/postgresql-${POSTGRESQL_VERSION}-aarch64-unknown-linux-gnu.tar.gz.sha256"
PG_MACOS_X64_URL="${_THESEUS}/postgresql-${POSTGRESQL_VERSION}-x86_64-apple-darwin.tar.gz"
PG_MACOS_X64_SHA_URL="${_THESEUS}/postgresql-${POSTGRESQL_VERSION}-x86_64-apple-darwin.tar.gz.sha256"
PG_MACOS_ARM64_URL="${_THESEUS}/postgresql-${POSTGRESQL_VERSION}-aarch64-apple-darwin.tar.gz"
PG_MACOS_ARM64_SHA_URL="${_THESEUS}/postgresql-${POSTGRESQL_VERSION}-aarch64-apple-darwin.tar.gz.sha256"
# EDB-Legacy URL (nur noch als Last-Resort-Fallback dokumentiert; aktuell HTTP 403)
_EDB="https://get.enterprisedb.com/postgresql"
_PGV_EDB="postgresql-${POSTGRESQL_VERSION%.*}-${POSTGRESQL_EDB_SUFFIX}"
PG_LINUX_EDB_URL="${_EDB}/${_PGV_EDB}-linux-x64-binaries.tar.gz"
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
# SHA256 der offiziellen nssm-2.24.zip. web.archive.org ist KEINE content-
# addressierte Quelle (gleiche URL kann ueber die Zeit anderen Inhalt liefern)
# und nssm.exe landet 1:1 als Windows-Dienstmanager beim Kunden — daher den
# Hash pinnen und nach dem Download (auch bei Cache-Hit) verifizieren.
NSSM_SHA256="727d1e42275c605e0f04aba98095c38a8e1e46def453cdffce42869428aa6743"

# pip bootstrap
GET_PIP_URL="https://bootstrap.pypa.io/get-pip.py"

# Microsoft Visual C++ Redistributable (x64). Die EDB-PG-18-Binaries sind
# MSVC-gebaut und linken vcruntime140*.dll. Wird ins Windows-Paket gebuendelt,
# damit der Update-Pfad (update-wizard.ps1 -> Step-VcRedist) die Runtime
# idempotent sicherstellen kann — der EDB-Installer (--install_runtimes 1) deckt
# nur die Erstinstallation ab, nicht das In-Place-Update (1.5.4, Pitfall #11).
VC_REDIST_URL="https://aka.ms/vs/17/release/vc_redist.x64.exe"

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

# Download + SHA256-Verify. Wenn die .sha256-Datei verfügbar ist, wird der
# heruntergeladene Tarball gegen sie geprüft. Cache wird invalidiert wenn
# der Hash nicht stimmt.
download_with_sha() {
    local url="$1"
    local sha_url="$2"
    local target="$3"
    local name="$(basename "$target")"

    download "$url" "$target" || return 1

    if [ -n "$sha_url" ]; then
        local sha_target="${target}.sha256"
        if curl -fsSL -o "${sha_target}" "$sha_url" 2>/dev/null; then
            local expected
            expected=$(awk '{print $1}' "${sha_target}")
            local actual
            actual=$(sha256sum "$target" | awk '{print $1}')
            if [ "$expected" != "$actual" ]; then
                error "SHA256 mismatch fuer ${name}:"
                error "  expected: ${expected}"
                error "  actual:   ${actual}"
                rm -f "$target" "$sha_target"
                return 1
            fi
            info "SHA256 verifiziert: ${name}"
        else
            warn "Keine .sha256-Datei fuer ${name} (Quelle: ${sha_url})"
        fi
    fi
}

# Glibc-Symbol-Check: verifiziert dass kein Binary Symbole verlangt, die
# über GLIBC_MAX_VERSION hinausgehen. Vorhanden in objdump-Output als
# Versioned Symbols (z.B. GLIBC_2.43).
GLIBC_MAX_VERSION="2.34"
check_glibc_compat() {
    local binary="$1"
    if ! command -v objdump &>/dev/null; then
        warn "objdump nicht gefunden — glibc-Compat-Check uebersprungen"
        return 0
    fi
    local max_needed
    max_needed=$(objdump -T "$binary" 2>/dev/null \
        | grep -oE 'GLIBC_[0-9]+\.[0-9]+' \
        | sort -V -u \
        | tail -1)
    if [ -z "$max_needed" ]; then
        return 0
    fi
    local needed_ver="${max_needed#GLIBC_}"
    # Vergleich per sort -V
    local higher
    higher=$(printf '%s\n%s\n' "$needed_ver" "$GLIBC_MAX_VERSION" | sort -V | tail -1)
    if [ "$higher" != "$GLIBC_MAX_VERSION" ]; then
        error "Glibc-Forward-Compat verletzt:"
        error "  Binary: $binary"
        error "  Verlangt: GLIBC_${needed_ver}"
        error "  Erlaubt:  GLIBC_${GLIBC_MAX_VERSION}"
        error "  Auswirkung: Binary laeuft nicht auf Ubuntu 22.04 / RHEL 9 / Debian 12."
        error "  Aktion: PostgreSQL aus einer manylinux-portablen Quelle beziehen"
        error "          (theseus-rs/postgresql-binaries) statt System-Build."
        return 1
    fi
    return 0
}

# macOS-Binary-Sanity-Check: stellt sicher dass das entpackte postgres-Binary
# tatsaechlich ein Mach-O ist (nicht z.B. ein Shell-Skript oder leeres File aus
# einem kaputten Tarball — Hintergrund: 1.5.0-Bug, wo nur das EDB-DMG mit kam
# und Binary-Files unter bin/ fehlten). otool-Check ist optional: er laeuft nur
# wenn wir auf macOS bauen; auf Linux-Build-Hosts wird er als Skip behandelt.
check_macos_binary_sanity() {
    local binary="$1"
    if [ ! -e "$binary" ]; then
        error "macOS-Binary fehlt: $binary"
        return 1
    fi
    if ! command -v file &>/dev/null; then
        warn "file(1) nicht gefunden — macOS-Binary-Sanity-Check uebersprungen"
        return 0
    fi
    local ftype
    ftype=$(file -b "$binary")
    case "$ftype" in
        *Mach-O*executable*|*Mach-O*universal*)
            info "Binary OK ($(basename "$binary")): ${ftype%%,*}"
            ;;
        *)
            error "macOS-Binary ist kein Mach-O:"
            error "  Pfad:  $binary"
            error "  Typ:   $ftype"
            error "  Auswirkung: Tarball ist kaputt oder unvollstaendig entpackt."
            return 1
            ;;
    esac
    # otool nur auf macOS-Build-Hosts verfuegbar — auf Linux nicht-fatal skippen
    if command -v otool &>/dev/null; then
        local missing
        missing=$(otool -L "$binary" 2>/dev/null | awk '/not found/ {print}')
        if [ -n "$missing" ]; then
            error "otool zeigt fehlende Dylibs fuer $binary:"
            error "$missing"
            return 1
        fi
    fi
    return 0
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
    if ! download_with_sha "$PG_LINUX_URL" "$PG_LINUX_SHA_URL" \
                           "${CACHE_DIR}/postgresql-linux-x64.tar.gz"; then
        error "PostgreSQL-Tarball konnte nicht heruntergeladen werden."
        error "Primärquelle (theseus-rs): $PG_LINUX_URL"
        error ""
        error "Optionen:"
        error "  1) Internet-Verbindung pruefen"
        error "  2) Cache wiederverwenden: --skip-download"
        error "     (wenn vorheriger Build erfolgreich war)"
        error "  3) Andere PG-Version setzen via POSTGRESQL_VERSION im Script"
        error ""
        error "Kein System-PG-Fallback mehr — die produzieren ABI-incompatible"
        error "Binaries (Issue #125). Build bricht ab."
        exit 1
    fi
fi

if [ "$BUILD_WINDOWS" = true ]; then
    download "$PYTHON_WINDOWS_URL" "${CACHE_DIR}/python-windows-x64.tar.gz"
    download "$NSSM_URL"           "${CACHE_DIR}/nssm.zip"
    # nssm.zip gegen den gepinnten Hash pruefen — auch bei --skip-download/Cache-
    # Hit, da das eingebettete nssm.exe direkt aus dieser Datei stammt.
    _nssm_actual=$(sha256sum "${CACHE_DIR}/nssm.zip" | awk '{print $1}')
    if [ "$_nssm_actual" != "$NSSM_SHA256" ]; then
        error "nssm.zip SHA256 stimmt nicht: erwartet ${NSSM_SHA256}, ist ${_nssm_actual}"
        error "  (web.archive.org-Quelle moeglicherweise veraendert — Build abgebrochen)"
        rm -f "${CACHE_DIR}/nssm.zip"
        exit 1
    fi
    info "nssm.zip SHA256 verifiziert"
    download "$GET_PIP_URL"        "${CACHE_DIR}/get-pip.py"
    download "$VC_REDIST_URL"      "${CACHE_DIR}/vc_redist.x64.exe"

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
            # Frueher: nur warn() — silent-fail produzierte unbenutzbare ZIPs
            # ohne PG-Installer (Kunde bekam beim setup.bat sofort einen Fehler).
            # Jetzt: hart abbrechen, analog zur Linux-Logik fuer fehlende PG-Tarballs.
            error "PostgreSQL Windows-Installer FEHLT!"
            error "  Erwartet: ${CACHE_DIR}/${PG_WINDOWS_INSTALLER}"
            error "  (oder in ~/Downloads/postgresql-*-windows-x64.exe)"
            error ""
            error "Download via direkter EDB-Link (kein Webformular noetig):"
            error "  https://get.enterprisedb.com/postgresql/postgresql-${POSTGRESQL_VERSION%.*}-${POSTGRESQL_EDB_SUFFIX}-windows-x64.exe"
            error ""
            error "Datei nach ${CACHE_DIR}/${PG_WINDOWS_INSTALLER} kopieren und Build wiederholen."
            error "Ohne Installer waere das Windows-ZIP unbrauchbar (setup.bat schlaegt fehl)."
            exit 1
        fi
    fi
fi

if [ "$BUILD_MACOS" = true ]; then
    download "$PYTHON_MACOS_X64_URL"   "${CACHE_DIR}/python-macos-x64.tar.gz"
    download "$PYTHON_MACOS_ARM64_URL" "${CACHE_DIR}/python-macos-arm64.tar.gz"
    download "$GET_PIP_URL"            "${CACHE_DIR}/get-pip.py"

    # PG Tarballs (theseus-rs) — analog zum Linux-Pfad mit SHA256-Verify.
    # Frueher: einfaches download(), Hash wurde nicht geprueft → ein gescheiterter
    # Download oder ein MITM haetten kommentarlos ein kaputtes Archiv in den
    # Build geschoben (1.5.0-Bug-Kontext). Jetzt: SHA256 enforced.
    if ! download_with_sha "$PG_MACOS_X64_URL" "$PG_MACOS_X64_SHA_URL" \
                           "${CACHE_DIR}/postgresql-macos-x64.tar.gz"; then
        error "PostgreSQL-Tarball (macOS x64) konnte nicht heruntergeladen werden."
        error "Quelle (theseus-rs): $PG_MACOS_X64_URL"
        exit 1
    fi
    if ! download_with_sha "$PG_MACOS_ARM64_URL" "$PG_MACOS_ARM64_SHA_URL" \
                           "${CACHE_DIR}/postgresql-macos-arm64.tar.gz"; then
        error "PostgreSQL-Tarball (macOS arm64) konnte nicht heruntergeladen werden."
        error "Quelle (theseus-rs): $PG_MACOS_ARM64_URL"
        exit 1
    fi

    # Legacy EDB-DMG: nur noch Cache-Lookup, KEIN Fallback in den Build —
    # die DMG wird in Phase 6 nicht mehr ins Paket kopiert (1.5.0-Bug).
    # Wenn jemand sie trotzdem im Cache hat, ignorieren wir das stillschweigend.
    if [ ! -f "${CACHE_DIR}/${PG_MACOS_INSTALLER}" ]; then
        info "(EDB macOS-DMG nicht benoetigt — Build nutzt theseus-rs Tarballs)"
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

    info "PostgreSQL (Linux x64) — theseus-rs ${POSTGRESQL_VERSION}..."
    mkdir -p "${LINUX_DIR}/bin/postgresql"
    # theseus-Tarball-Layout: top-level postgresql-<ver>-<triple>/{bin,lib,share,include}
    tar xzf "${CACHE_DIR}/postgresql-linux-x64.tar.gz" \
        -C "${LINUX_DIR}/bin/postgresql" --strip-components=1
    # Sanity: erwartete Pfade existieren
    for f in bin/postgres bin/initdb bin/psql lib/libpq.so.5 share/postgres.bki; do
        if [ ! -e "${LINUX_DIR}/bin/postgresql/${f}" ]; then
            error "Theseus-Tarball unvollstaendig: ${f} fehlt"
            exit 1
        fi
    done
    # Glibc-Compat-Check auf das postgres-Binary
    if ! check_glibc_compat "${LINUX_DIR}/bin/postgresql/bin/postgres"; then
        exit 1
    fi
    info "PostgreSQL ${POSTGRESQL_VERSION} entpackt (glibc-2.34-portabel)"

    # #177: theseus-PG linkt libxml2.so.2; Rolling-Distros (Arch/CachyOS) liefern
    # nur noch libxml2.so.16 -> PG laedt nicht (Crash-Loop). libxml2.so.2 aus
    # rockylinux:9 buendeln (glibc-2.34, gebaut OHNE ICU -> nur base libs
    # libz/liblzma/libm/libc), abgelegt in bin/postgresql/lib/, das pg_env() per
    # LD_LIBRARY_PATH-Prepend findet -> Native-Install wird distro-unabhaengig.
    if command -v docker &>/dev/null; then
        info "Buendle libxml2.so.2 (Rolling-Distro-Support, #177)..."
        if docker run --rm rockylinux:9 sh -c \
                'dnf install -y -q libxml2 >/dev/null 2>&1 && cat "$(readlink -f /usr/lib64/libxml2.so.2)"' \
                > "${LINUX_DIR}/bin/postgresql/lib/libxml2.so.2" 2>/dev/null \
           && [ -s "${LINUX_DIR}/bin/postgresql/lib/libxml2.so.2" ]; then
            # Sanity: glibc <= Baseline (sonst wuerde es die unterstuetzten Distros
            # brechen) — derselbe Check wie fuer das postgres-Binary.
            if ! check_glibc_compat "${LINUX_DIR}/bin/postgresql/lib/libxml2.so.2"; then
                error "Gebuendeltes libxml2.so.2 ueberschreitet die glibc-Baseline — Abbruch."
                exit 1
            fi
            # Defensive: keine ICU-Abhaengigkeit (sonst kaskadiert das Soname-Problem)
            if command -v objdump &>/dev/null && objdump -p "${LINUX_DIR}/bin/postgresql/lib/libxml2.so.2" 2>/dev/null | grep -qi 'libicu'; then
                error "Gebuendeltes libxml2.so.2 haengt an ICU — falsche Quelle, Abbruch."
                exit 1
            fi
            info "libxml2.so.2 gebuendelt ($(du -h "${LINUX_DIR}/bin/postgresql/lib/libxml2.so.2" | cut -f1), glibc-2.34, ohne ICU)"
        else
            rm -f "${LINUX_DIR}/bin/postgresql/lib/libxml2.so.2"
            warn "libxml2.so.2 konnte nicht gebuendelt werden — Rolling-Distros bleiben unsupported (install.sh-Fail-Fast greift)."
        fi
    else
        warn "docker fehlt -> libxml2.so.2 NICHT gebuendelt (#177); Rolling-Distros bleiben unsupported."
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

    # pip-Dependencies VORAB ins Windows-Bundle installieren (wie beim Linux-Paket).
    # Frueher wurden sie erst beim Kunden-Install via setup.bat nachgeladen — das
    # ist netz-/timing-abhaengig und schlug fehl (Dienst fand alembic/uvicorn nicht
    # -> ERR_CONNECTION_REFUSED). Jetzt sind die cp313-win_amd64-Wheels bereits im
    # Paket -> der Install braucht KEINEN PyPI-Download mehr.
    # PYTHONNOUSERSITE: das gebuendelte Python nicht das User-Site eines evtl. auf
    # der Build-Maschine installierten System-Python 3.13 sehen lassen.
    info "Installiere pip-Dependencies ins Windows-Bundle (vorab, kein Kunden-Download)..."
    PYTHONNOUSERSITE=1 PYTHONUTF8=1 "${WIN_DIR}/bin/python/python.exe" -m pip install -q \
        --no-warn-script-location \
        -r "${WIN_DIR}/app/backend/requirements.txt" 2>&1 | tail -3
    if ! PYTHONNOUSERSITE=1 "${WIN_DIR}/bin/python/python.exe" -s -c \
        "import alembic, uvicorn, fastapi, sqlalchemy, psycopg2, cryptography" 2>/dev/null; then
        error "Windows-Bundle: pip-Dependencies fehlen nach der Installation (Import-Check fehlgeschlagen)"
        exit 1
    fi
    info "Windows pip-Dependencies ins Bundle installiert + verifiziert"

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

    # VC++ Redistributable buendeln — update-wizard.ps1 (Step-VcRedist) fuehrt es
    # idempotent aus, damit auch ein In-Place-Update die Runtime sicherstellt.
    if [ -f "${CACHE_DIR}/vc_redist.x64.exe" ]; then
        info "Kopiere VC++ Redistributable ($(du -h "${CACHE_DIR}/vc_redist.x64.exe" | cut -f1))..."
        cp "${CACHE_DIR}/vc_redist.x64.exe" "${WIN_DIR}/bin/vc_redist.x64.exe"
    else
        warn "Kein vc_redist.x64.exe im Cache — Update-Pfad kann die VC++-Runtime nicht sicherstellen"
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
    if [ "$SKIP_SETUP" = true ]; then
        info "setup.exe-Build uebersprungen (--skip-setup) — .bat-Fallback bleibt funktional."
    elif command -v dotnet &>/dev/null; then
        # #81: Pre-Build-Gate — die Installer-Unit-Tests muessen gruen sein, sonst
        # wird KEINE setup.exe gebaut (verhindert die Auslieferung eines kaputten
        # GUI-Installers). Failt das, bricht der Build hart ab.
        info "Installer-Tests (dotnet test)..."
        if ! dotnet test "${REPO_DIR}/installer/setup/PraxisZeit.Setup.slnx" \
                -c Release --nologo -v quiet \
                > "${BUILD_DIR}/setup-tests.log" 2>&1; then
            error "Installer-Tests FEHLGESCHLAGEN — setup.exe wird NICHT gebaut."
            error "Log: ${BUILD_DIR}/setup-tests.log"
            exit 1
        fi
        info "Installer-Tests gruen."
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
                # setup.exe wird NICHT in WIN_DIR kopiert: sonst landet die ~500 MB
                # single-file-EXE (die denselben Payload bereits eingebettet hat) auch
                # noch in der windows-x64.zip -> Payload doppelt, ZIP ~1 GB statt ~490 MB.
                # Die setup.exe wird ausschliesslich als eigenes Artefakt
                # praxiszeit-*-setup-windows-x64.exe ausgeliefert (oben nach DIST kopiert).
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

    if [ "$SETUP_ONLY" = true ]; then
        info "windows-x64.zip uebersprungen (--setup-only) — Payload steckt bereits in der setup.exe."
    else
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
    # Regression-Guard: die portable/Updater-ZIP darf KEINE setup.exe enthalten
    # (sonst ist der Payload doppelt drin — siehe Phase 5b). setup.exe wird separat
    # als praxiszeit-*-setup-windows-x64.exe ausgeliefert.
    if command -v unzip &>/dev/null && [[ "$_win_zip" == *.zip ]]; then
        if unzip -Z1 "$_win_zip" 2>/dev/null | grep -qiE '(^|[/\\])setup\.exe$'; then
            error "windows-x64.zip enthaelt setup.exe — Payload doppelt (~1 GB statt ~490 MB). Build abgebrochen."
            exit 1
        fi
    fi
    fi  # Ende --setup-only-Guard um die windows-x64.zip-Emission
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
        local pg_tar="$3"     # Pfad zum theseus PG-Tarball

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

        info "PostgreSQL (macOS ${arch}) — theseus-rs ${POSTGRESQL_VERSION}..."
        mkdir -p "${mac_dir}/bin/postgresql"
        tar xzf "${pg_tar}" -C "${mac_dir}/bin/postgresql" --strip-components=1
        for f in bin/postgres bin/initdb bin/psql; do
            if [ ! -e "${mac_dir}/bin/postgresql/${f}" ]; then
                error "Theseus macOS-${arch}-Tarball unvollstaendig: ${f} fehlt"
                exit 1
            fi
        done

        # Mach-O-Sanity (file-basiert, ohne otool-Pflicht — laeuft auch auf Linux-
        # Build-Hosts). Schuetzt vor dem 1.5.0-Pattern, wo nur ein DMG ohne
        # Binaries im Paket landete und der Build trotzdem "erfolgreich" war.
        if ! check_macos_binary_sanity "${mac_dir}/bin/postgresql/bin/postgres"; then
            exit 1
        fi
        if ! check_macos_binary_sanity "${mac_dir}/bin/postgresql/bin/initdb"; then
            exit 1
        fi

        _write_macos_installer "${mac_dir}"

        tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-${arch}.tar.gz" -C "${mac_dir}" .
        info "macOS ${arch}: $(du -h "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-${arch}.tar.gz" | cut -f1)"
    }

    _build_macos_arch "x64"   "${CACHE_DIR}/python-macos-x64.tar.gz"   "${CACHE_DIR}/postgresql-macos-x64.tar.gz"
    _build_macos_arch "arm64" "${CACHE_DIR}/python-macos-arm64.tar.gz" "${CACHE_DIR}/postgresql-macos-arm64.tar.gz"
else
    step "6 — macOS: uebersprungen"
fi

# =============================================================================
# Phase 6b: Docker-Bundle (self-contained: compose + Quellcode-Build-Kontext)
# -----------------------------------------------------------------------------
# Feedback Braumann (2026-05): Wer Docker bevorzugt, fand kein docker-compose.yml
# im Download. Dieses Bundle enthaelt compose-Dateien, .env.example, einen
# Secrets-Generator und den kompletten Build-Kontext (backend/ + frontend/ +
# ssl/ + prometheus/ + grafana/), sodass `docker compose up -d --build` direkt
# laeuft. Top-Level-Ordner praxiszeit-<version>/ -> `tar xzf … && cd …` klappt.
# =============================================================================

if [ "$BUILD_DOCKER" = true ]; then
    step "6b — Docker-Bundle"

    DOCKER_STAGE="${BUILD_DIR}/docker/praxiszeit-${APP_VERSION}"
    rm -rf "${BUILD_DIR}/docker"
    mkdir -p "${DOCKER_STAGE}"

    cp "${REPO_DIR}/docker-compose.yml"               "${DOCKER_STAGE}/"
    cp "${REPO_DIR}/docker-compose.ssl.yml"           "${DOCKER_STAGE}/"
    cp "${REPO_DIR}/.env.example"                     "${DOCKER_STAGE}/"
    cp "${REPO_DIR}/tools/docker/generate-secrets.sh" "${DOCKER_STAGE}/generate-secrets.sh"
    cp "${REPO_DIR}/tools/docker/backup.sh"           "${DOCKER_STAGE}/backup.sh"
    cp "${REPO_DIR}/tools/docker/restore.sh"          "${DOCKER_STAGE}/restore.sh"
    chmod +x "${DOCKER_STAGE}/generate-secrets.sh" "${DOCKER_STAGE}/backup.sh" "${DOCKER_STAGE}/restore.sh"

    # Build-Kontext kopieren (ohne Ballast / ohne evtl. lokale Secrets+Certs).
    # cd ins REPO_DIR -> Pfade in den tar-Excludes sind relativ ("backend/...").
    _copy_tree() {  # $1 = Unterverzeichnis, $2.. = zusaetzliche tar-Excludes
        local sub="$1"; shift
        (cd "${REPO_DIR}" && tar cf - "$@" "${sub}") | tar xf - -C "${DOCKER_STAGE}/"
    }
    # Belt-and-suspenders: nie lokale Secrets/Keys ins Bundle, auch wenn jemand
    # mal welche unter backend/ oder frontend/ ablegt.
    _copy_tree backend \
        --exclude='backend/__pycache__' --exclude='*.pyc' --exclude='backend/tests' \
        --exclude='backend/.pytest_cache' --exclude='backend/htmlcov' \
        --exclude='backend/test.db' --exclude='backend/.venv' \
        --exclude='*.pem' --exclude='*.key' --exclude='.env'
    _copy_tree frontend \
        --exclude='frontend/node_modules' --exclude='frontend/dist' \
        --exclude='*.pem' --exclude='*.key' --exclude='.env'
    # ssl/: Skript + nginx-Config, aber NIE einen evtl. lokal erzeugten Key/Cert
    _copy_tree ssl --exclude='ssl/cert.pem' --exclude='ssl/key.pem'
    _copy_tree prometheus
    _copy_tree grafana

    cat > "${DOCKER_STAGE}/DOCKER-README.md" << DOCKEREOF
# PraxisZeit ${APP_VERSION} — Docker

1. Secrets erzeugen:        bash generate-secrets.sh
2. (HTTPS) Zertifikat:      bash ssl/generate-cert.sh
3. Starten (HTTPS):         docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
   ODER (nur intern, HTTP): in .env ENVIRONMENT=development + COOKIE_SECURE=false setzen, dann
                            docker compose up -d --build

## Datensicherung / Update

Vor jedem Versions-Update die DB der laufenden (alten) Version sichern und nach
dem Hochziehen der neuen Version wieder einspielen:

    bash backup.sh                                  # -> backups/praxiszeit_<ts>.sql.gz
    # ... neue Version entpacken, .env + backups/ uebernehmen, Stack starten ...
    bash restore.sh backups/praxiszeit_<ts>.sql.gz  # DB einspielen
    docker compose up -d backend                    # Alembic-Migrationen -> Schema auf head

Die Backups sind gzip-komprimierte Plain-SQL-Dumps und lassen sich auch per
\`gunzip -c <datei>.sql.gz | docker compose exec -T db psql -U praxiszeit praxiszeit\` einspielen.

Volle Anleitung: https://github.com/phash/praxiszeit/blob/master/docs/INSTALL-DOCKER.md
DOCKEREOF

    tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-docker.tar.gz" \
        -C "${BUILD_DIR}/docker" "praxiszeit-${APP_VERSION}"
    info "Docker-Bundle: $(du -h "${DIST_DIR}/praxiszeit-${APP_VERSION}-docker.tar.gz" | cut -f1)"
    info "Docker-Bundle: das pzweb-Upload-Regex akzeptiert seit 2026-06 auch '-docker'"
    info "(neben linux/macos/windows) — kann also in den Shop ODER an ein GitHub-Release."
else
    step "6b — Docker: uebersprungen"
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
  Linux-Installation (Tarball entpackt FLACH -> in Zielordner entpacken):
    mkdir -p praxiszeit-${APP_VERSION} && tar xzf praxiszeit-${APP_VERSION}-linux-x64.tar.gz -C praxiszeit-${APP_VERSION}
    sudo praxiszeit-${APP_VERSION}/install.sh

EOF

$BUILD_WINDOWS && cat << EOF
  Windows-Installation/Update (empfohlen, ab 1.4.0):
    1. praxiszeit-${APP_VERSION}-setup-windows-x64.exe herunterladen
       (eigenes Artefakt — NICHT in der ZIP enthalten)
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
  macOS-Installation (Intel ODER Apple Silicon; Tarball entpackt FLACH):
    mkdir -p praxiszeit-${APP_VERSION} && tar xzf praxiszeit-${APP_VERSION}-macos-{x64|arm64}.tar.gz -C praxiszeit-${APP_VERSION}
    sudo praxiszeit-${APP_VERSION}/install.sh

EOF

$BUILD_DOCKER && cat << EOF
  Docker-Installation (Bundle -> GitHub-Release, NICHT pzweb):
    tar xzf praxiszeit-${APP_VERSION}-docker.tar.gz
    cd praxiszeit-${APP_VERSION}
    bash generate-secrets.sh && bash ssl/generate-cert.sh
    docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build

EOF
