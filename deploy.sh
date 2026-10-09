#!/usr/bin/env bash
#
# F-035: Deploy with pre-migration backup and automatic rollback.
#
# Steps:
#   1. refuse to deploy with a dirty working tree
#   2. record the currently-deployed commit so we can roll back
#   3. pre-migration pg_dump via scripts/backup-db.sh (fails-closed)
#   4. git pull + docker build --pull (frische Basis-Images, #491) +
#      compose pull db + docker compose up -d
#   5. wait for /api/health, on failure: rewind to the previous commit,
#      re-tag + start the previously running images (rebuild only if none
#      were recorded), and surface logs
#
# Requires: git, docker compose, scripts/backup-db.sh
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.ssl.yml"
LOGF="/var/log/praxiszeit-deploy.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# --- 0. pre-flight ---

log "=== PraxisZeit Deploy ==="

# Refuse to deploy with uncommitted changes — overwriting or losing
# accidentally-tracked files in a rebuild would be silent.
if ! git diff --quiet || ! git diff --cached --quiet; then
    log "ERROR: working tree has uncommitted changes. Commit or stash first."
    git status --short
    exit 1
fi

# This script uses the SSL overlay → production deploy. Refuse to run with
# ENVIRONMENT != production so that /docs, /redoc and /openapi.json stay
# disabled and the weak-admin-password check hard-fails on boot.
if [ -f .env ]; then
    ENV_VALUE=$(grep -E '^ENVIRONMENT=' .env | head -n 1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
else
    ENV_VALUE=""
fi
if [ "${ENV_VALUE}" != "production" ]; then
    log "ERROR: .env must contain ENVIRONMENT=production for this deploy."
    log "       Current value: '${ENV_VALUE:-<unset>}'"
    exit 1
fi

# Record the currently-deployed commit BEFORE pulling.
PREVIOUS_COMMIT=$(git rev-parse HEAD)
log "Current deployed commit: ${PREVIOUS_COMMIT}"

# --- 1. pre-migration backup ---

log ">> pre-migration pg_dump"
if [ -x "./scripts/backup-db.sh" ]; then
    if ./scripts/backup-db.sh; then
        log "Backup ok"
    else
        log "ERROR: pre-migration backup failed, aborting deploy."
        exit 1
    fi
else
    log "WARN: scripts/backup-db.sh not found or not executable — skipping backup."
    log "      Refuse to deploy without a backup. Fix permissions and retry."
    exit 1
fi

# --- 2. git pull ---

log ">> git pull"
git pull origin master

NEW_COMMIT=$(git rev-parse HEAD)
if [ "${NEW_COMMIT}" = "${PREVIOUS_COMMIT}" ]; then
    log "No new commits. Nothing to deploy."
    exit 0
fi
log "New commit: ${NEW_COMMIT}"

# --- 2b. keep the running app images for a rollback (#491 DEP-4, Review-Nachzug) ---
# Nach `build --pull` zeigen die lokalen Basis-Tags (python:3.12-slim,
# node:20-alpine, nginx:alpine) auf die FRISCHEN Images. Ein Rollback per
# Neubau entstuende auf genau diesen — kommt der Fehler vom neuen Basis-Image
# (z. B. Debian-Release-Wechsel), stellte er nichts wieder her.
# Deshalb bekommen die laufenden App-Images JETZT eine zweite Referenz
# `<name>:pre-deploy`. Die Image-ID allein reicht nicht: im containerd-Image-
# Store (Docker 29) verschwindet ein Image, sobald `build` seinen Namen
# umhaengt — auch wenn ein Container es noch nutzt (nachgeprueft). Der Rollback
# haengt den Namen zurueck und startet ohne Bau; nur ohne Referenz (nichts lief,
# Taggen gescheitert) wird neu gebaut. Nach Erfolg fallen die Referenzen weg.
_running_image() {  # $1 = Dienst -> "<image-id> <image-name>" oder leer
    local cid
    cid=$($COMPOSE ps -q "$1" 2>/dev/null | head -n 1) || true
    [ -n "${cid}" ] || return 0
    docker inspect -f '{{.Image}} {{.Config.Image}}' "${cid}" 2>/dev/null || true
}
_repo_of() {  # "name[:tag]" -> "name" (ein Registry-Port mit "/" bleibt stehen)
    local last="${1##*:}"
    if [ "${last}" != "$1" ] && [[ "${last}" != */* ]]; then echo "${1%:*}"; else echo "$1"; fi
}
_keep_running_image() {  # $1 = Dienst -> "<name> <name>:pre-deploy" oder leer
    local id name ref
    read -r id name <<<"$(_running_image "$1")" || true
    [ -n "${id}" ] && [ -n "${name}" ] || return 0
    ref="$(_repo_of "${name}"):pre-deploy"
    docker tag "${id}" "${ref}" >/dev/null 2>&1 || return 0
    echo "${name} ${ref}"
}
PREV_BACKEND_NAME=""; PREV_BACKEND_REF=""; PREV_FRONTEND_NAME=""; PREV_FRONTEND_REF=""
read -r PREV_BACKEND_NAME PREV_BACKEND_REF <<<"$(_keep_running_image backend)" || true
read -r PREV_FRONTEND_NAME PREV_FRONTEND_REF <<<"$(_keep_running_image frontend)" || true
if [ -n "${PREV_BACKEND_REF}" ] && [ -n "${PREV_FRONTEND_REF}" ]; then
    log "Running images kept for rollback: ${PREV_BACKEND_REF} ${PREV_FRONTEND_REF}"
else
    log "WARN: running backend/frontend image could not be kept — a rollback would rebuild"
fi

# 0 = vorherige Images wieder unter ihren Namen; 1 = keine Referenz / Taggen
# gescheitert (Aufrufer baut dann neu).
_retag_previous_images() {
    [ -n "${PREV_BACKEND_REF}" ] && [ -n "${PREV_FRONTEND_REF}" ] || return 1
    docker tag "${PREV_BACKEND_REF}" "${PREV_BACKEND_NAME}" || return 1
    docker tag "${PREV_FRONTEND_REF}" "${PREV_FRONTEND_NAME}" || return 1
}

# Rollback der Container: vorherige Images zuruecktaggen und ohne Bau starten,
# sonst (keine Referenz / Taggen gescheitert) Neubau wie frueher.
_rollback_containers() {
    if _retag_previous_images; then
        log "Rollback: previous images re-tagged, starting them without a rebuild"
        $COMPOSE up -d --no-build && return 0
        log "WARN: starting the previous images failed, rebuilding ${PREVIOUS_COMMIT}"
    else
        log "Rollback: previous images not available, rebuilding ${PREVIOUS_COMMIT}"
    fi
    $COMPOSE build frontend backend && $COMPOSE up -d
}

# Nach Erfolg: nur die Zusatz-Referenzen entfernen (das Image selbst faellt
# weg, sobald nichts mehr darauf zeigt — wie vor diesem Mechanismus).
_drop_rollback_refs() {
    local ref
    for ref in "${PREV_BACKEND_REF}" "${PREV_FRONTEND_REF}"; do
        [ -n "${ref}" ] && docker rmi "${ref}" >/dev/null 2>&1 || true
    done
}

# --- 3. build ---

log ">> Building frontend + backend"
# #491 DEP-4: --pull zieht die Basis-Images (python:3.12-slim, node:20-alpine,
# nginx:alpine) neu — sonst kommen Debian/Alpine-Sicherheitsupdates unter
# demselben Tag nie an. Wie beim `pull db` unten darf ein nicht erreichbares
# Registry das Deployment nicht verhindern: scheitert der Bau mit --pull, folgt
# ein Bau mit den lokalen Images. Erst wenn auch der scheitert -> Rollback.
# (Ein Rollback startet die oben festgehaltenen Images, siehe 2b.)
if ! $COMPOSE build --pull frontend backend; then
    log "WARN: build --pull failed (registry unreachable?), retrying with local base images"
    if ! $COMPOSE build frontend backend; then
        log "ERROR: build failed. Rolling back to ${PREVIOUS_COMMIT}."
        git reset --hard "${PREVIOUS_COMMIT}"
        # Die alten Container laufen weiter; ein teilweise geglueckter Bau hat
        # aber evtl. schon einen Namen umgehaengt -> zuruecktaggen, damit ein
        # spaeteres `up` nicht den Stand des gescheiterten Deploys startet.
        _retag_previous_images || true
        exit 1
    fi
fi

# --- 4. start / run migrations ---

# PostgreSQL-18-Patchstand nachziehen: `up` allein nimmt das bereits vorhandene
# Image (floatendes postgres:18-alpine). Ein Pull-Fehler bricht nicht ab.
$COMPOSE pull db || log "WARN: docker compose pull db failed, continuing with local image"

log ">> Starting services"
if ! $COMPOSE up -d; then
    log "ERROR: compose up failed. Rolling back to ${PREVIOUS_COMMIT}."
    git reset --hard "${PREVIOUS_COMMIT}"
    _rollback_containers || true
    exit 1
fi

# --- 5. health check with retry window ---
# #337: HEALTH_TIMEOUT (Sekunden, Default 120) — großzügig, weil auf schwachen
# 1-Core-VMs (z. B. Proxmox) der Image-Build + Backend-Start (inkl. Alembic-
# Migration) deutlich länger als die früheren 10 s dauern kann. Überschreibbar:
#   HEALTH_TIMEOUT=180 ./deploy.sh
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"
log ">> Waiting for backend health (timeout ${HEALTH_TIMEOUT}s)..."
HEALTHY=0
WAITED=0
while [ "${WAITED}" -lt "${HEALTH_TIMEOUT}" ]; do
    if $COMPOSE exec -T backend python -c "from urllib.request import urlopen; import json, sys; r=json.loads(urlopen('http://localhost:8000/api/health').read()); sys.exit(0 if r.get('status')=='healthy' else 1)" 2>/dev/null; then
        HEALTHY=1
        log ">> Backend OK (after ${WAITED}s)"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

if [ "${HEALTHY}" -ne 1 ]; then
    log "ERROR: backend health check failed. Rolling back to ${PREVIOUS_COMMIT}."
    log "=== Recent backend logs ==="
    $COMPOSE logs --tail=50 backend || true
    log "=== Rolling back ==="
    git reset --hard "${PREVIOUS_COMMIT}"
    if _rollback_containers; then
        log "Rollback complete. Failing the deploy."
    else
        log "ERROR: rollback could not restart the previous version — check 'docker compose ps'."
    fi
    exit 1
fi

_drop_rollback_refs
log "=== Deploy complete: ${PREVIOUS_COMMIT} → ${NEW_COMMIT} ==="
