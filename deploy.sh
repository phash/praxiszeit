#!/usr/bin/env bash
#
# F-035: Deploy with pre-migration backup and automatic rollback.
#
# Steps:
#   1. refuse to deploy with a dirty working tree
#   2. record the currently-deployed commit so we can roll back
#   3. pre-migration pg_dump via scripts/backup-db.sh (fails-closed)
#   4. git pull + docker build + docker compose up -d
#   5. wait for /api/health, on failure: rewind to the previous commit,
#      rebuild, and surface logs
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

# --- 3. build ---

log ">> Building frontend + backend"
if ! $COMPOSE build frontend backend; then
    log "ERROR: build failed. Rolling back to ${PREVIOUS_COMMIT}."
    git reset --hard "${PREVIOUS_COMMIT}"
    exit 1
fi

# --- 4. start / run migrations ---

log ">> Starting services"
if ! $COMPOSE up -d; then
    log "ERROR: compose up failed. Rolling back to ${PREVIOUS_COMMIT}."
    git reset --hard "${PREVIOUS_COMMIT}"
    $COMPOSE build frontend backend || true
    $COMPOSE up -d || true
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
    $COMPOSE build frontend backend
    $COMPOSE up -d
    log "Rollback complete. Failing the deploy."
    exit 1
fi

log "=== Deploy complete: ${PREVIOUS_COMMIT} → ${NEW_COMMIT} ==="
