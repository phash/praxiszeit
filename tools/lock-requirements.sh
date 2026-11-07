#!/usr/bin/env bash
# PraxisZeit — backend/requirements.lock neu erzeugen (Audit 2026-11-07 S3-05).
#
# Die nativen Pakete (Linux, Windows, macOS) installieren die Python-
# Abhaengigkeiten ausschliesslich aus requirements.lock mit
# `pip install --require-hashes --only-binary :all:` — exakte Versionen, jede
# Datei mit SHA256. Die Lock-Datei ist "universal": sie enthaelt die Wheels
# fuer alle drei Plattformen (inkl. plattformabhaengiger Pakete wie colorama
# unter Windows) fuer Python 3.13 (= gebuendelter Interpreter, PYTHON_VERSION in
# tools/build-release.sh). requirements-build.lock enthaelt setuptools, mit dem
# das einzige Paket ohne Wheel (odfpy) ohne Build-Isolation gebaut wird.
#
# Aufruf nach jeder Aenderung an backend/requirements.txt:
#   bash tools/lock-requirements.sh
# Danach den Diff pruefen (neue Versionen = Abhaengigkeits-Update: Changelog,
# pip-audit, echter Login wie in CLAUDE.md beschrieben) und mitcommitten.
# backend/tests/test_requirements_lock.py prueft, dass jede Zeile aus
# requirements.txt in der Lock-Datei erfuellt ist und alles Hashes hat.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY_IMAGE="${LOCK_PYTHON_IMAGE:-python:3.13-slim}"
UV_VERSION="${LOCK_UV_VERSION:-0.9.*}"

docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "${REPO_DIR}/backend":/w -w /w "${PY_IMAGE}" sh -euc "
        pip install -q --user 'uv==${UV_VERSION}'
        /tmp/.local/bin/uv pip compile --universal --python-version 3.13 \
            --generate-hashes \
            --custom-compile-command 'bash tools/lock-requirements.sh' \
            requirements.txt -o requirements.lock
        /tmp/.local/bin/uv pip compile --universal --python-version 3.13 \
            --generate-hashes \
            --custom-compile-command 'bash tools/lock-requirements.sh' \
            requirements-build.txt -o requirements-build.lock
    "
echo "backend/requirements.lock und backend/requirements-build.lock aktualisiert."
