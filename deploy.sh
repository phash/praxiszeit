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

log ">> Waiting for backend health..."
HEALTHY=0
for i in 1 2 3 4 5 6 7 8 9 10; do
    if $COMPOSE exec -T backend python -c "from urllib.request import urlopen; import json, sys; r=json.loads(urlopen('http://localhost:8000/api/health').read()); sys.exit(0 if r.get('status')=='healthy' else 1)" 2>/dev/null; then
        HEALTHY=1
        log ">> Backend OK (after ${i}s)"
        break
    fi
    sleep 1
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
