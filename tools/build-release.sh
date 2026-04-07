#!/bin/bash
# PraxisZeit Release Builder
# Builds installer packages for Linux and Windows
set -euo pipefail

VERSION="${1:-1.2.0}"
BUILD_DIR="build/release-${VERSION}"
DIST_DIR="dist"

echo "Building PraxisZeit ${VERSION} release packages..."
echo ""

# --- Cleanup ---

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}" "${DIST_DIR}"

# --- Build frontend ---

echo "[1/5] Building frontend..."
(cd frontend && npm ci && npm run build)

# --- Prepare common files ---

echo "[2/5] Preparing application files..."

# Backend
mkdir -p "${BUILD_DIR}/app/backend"
cp -r backend/app "${BUILD_DIR}/app/backend/"
cp -r backend/alembic "${BUILD_DIR}/app/backend/"
cp backend/alembic.ini "${BUILD_DIR}/app/backend/"
cp backend/init-db-user.sql "${BUILD_DIR}/app/backend/"
cp backend/requirements.txt "${BUILD_DIR}/app/backend/"

# Frontend dist
mkdir -p "${BUILD_DIR}/app/frontend"
cp -r frontend/dist/* "${BUILD_DIR}/app/frontend/"

# Process manager
cp praxiszeit-server.py "${BUILD_DIR}/"

# Config template
mkdir -p "${BUILD_DIR}/config"
cp installer/praxiszeit.conf.example "${BUILD_DIR}/config/praxiszeit.conf.example"

# --- Build Linux package ---

echo "[3/5] Building Linux package..."
LINUX_DIR="${BUILD_DIR}/linux"
mkdir -p "${LINUX_DIR}"

# Copy app files
cp -r "${BUILD_DIR}/app" "${LINUX_DIR}/"
cp -r "${BUILD_DIR}/config" "${LINUX_DIR}/"
cp "${BUILD_DIR}/praxiszeit-server.py" "${LINUX_DIR}/"

# Copy installer
cp installer/linux/install.sh "${LINUX_DIR}/"
chmod +x "${LINUX_DIR}/install.sh"

# Python standalone (placeholder — download from python-build-standalone)
mkdir -p "${LINUX_DIR}/bin/python"
echo "PLACEHOLDER: Download python-build-standalone for Linux x86_64" > "${LINUX_DIR}/bin/python/README.txt"
echo "https://github.com/indygreg/python-build-standalone/releases" >> "${LINUX_DIR}/bin/python/README.txt"

# PostgreSQL portable (placeholder — download from EDB)
mkdir -p "${LINUX_DIR}/bin/postgresql"
echo "PLACEHOLDER: Download PostgreSQL 16 binaries for Linux x86_64" > "${LINUX_DIR}/bin/postgresql/README.txt"
echo "https://www.enterprisedb.com/download-postgresql-binaries" >> "${LINUX_DIR}/bin/postgresql/README.txt"

# Create tarball
tar -czf "${DIST_DIR}/praxiszeit-${VERSION}-linux-x64.tar.gz" -C "${LINUX_DIR}" .
echo "  -> ${DIST_DIR}/praxiszeit-${VERSION}-linux-x64.tar.gz"

# --- Build Windows package ---

echo "[4/5] Building Windows package..."
WINDOWS_DIR="${BUILD_DIR}/windows"
mkdir -p "${WINDOWS_DIR}"

# Copy app files
cp -r "${BUILD_DIR}/app" "${WINDOWS_DIR}/"
cp -r "${BUILD_DIR}/config" "${WINDOWS_DIR}/"
cp "${BUILD_DIR}/praxiszeit-server.py" "${WINDOWS_DIR}/"

# Copy Windows service scripts
cp installer/windows/install-service.bat "${WINDOWS_DIR}/"
cp installer/windows/uninstall-service.bat "${WINDOWS_DIR}/"

# Python embeddable (placeholder)
mkdir -p "${WINDOWS_DIR}/bin/python"
echo "PLACEHOLDER: Download Python 3.12 embeddable (Windows x64)" > "${WINDOWS_DIR}/bin/python/README.txt"
echo "https://www.python.org/downloads/windows/" >> "${WINDOWS_DIR}/bin/python/README.txt"

# PostgreSQL portable (placeholder)
mkdir -p "${WINDOWS_DIR}/bin/postgresql"
echo "PLACEHOLDER: Download PostgreSQL 16 ZIP (Windows x64)" > "${WINDOWS_DIR}/bin/postgresql/README.txt"
echo "https://www.enterprisedb.com/download-postgresql-binaries" >> "${WINDOWS_DIR}/bin/postgresql/README.txt"

# nssm placeholder
echo "PLACEHOLDER: Download nssm from https://nssm.cc/download" > "${WINDOWS_DIR}/nssm-README.txt"

# Create zip
(cd "${WINDOWS_DIR}" && zip -r "../../${DIST_DIR}/praxiszeit-${VERSION}-windows-x64.zip" .)
echo "  -> ${DIST_DIR}/praxiszeit-${VERSION}-windows-x64.zip"

# --- Generate checksums ---

echo "[5/5] Generating checksums..."
(cd "${DIST_DIR}" && sha256sum praxiszeit-${VERSION}-* > "praxiszeit-${VERSION}-SHA256SUMS.txt")
cat "${DIST_DIR}/praxiszeit-${VERSION}-SHA256SUMS.txt"

echo ""
echo "Release ${VERSION} built successfully!"
echo ""
echo "Packages in ${DIST_DIR}/:"
ls -lh "${DIST_DIR}/praxiszeit-${VERSION}-"*
echo ""
echo "NOTE: The bin/ directories contain PLACEHOLDERS."
echo "Before distribution, replace them with actual binaries:"
echo "  - Python: https://github.com/indygreg/python-build-standalone/releases"
echo "  - PostgreSQL: https://www.enterprisedb.com/download-postgresql-binaries"
echo "  - nssm (Windows): https://nssm.cc/download"
