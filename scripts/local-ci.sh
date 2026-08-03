#!/usr/bin/env bash
#
# F-062: Local CI pipeline — the full-stack gate before a PR.
#
# GitHub Actions IS active: .github/workflows/cross-tenant-ci.yml runs on every
# pull request and on every push to master (path filter `backend/**`) against
# PostgreSQL 18, covering the SQLite suite plus the Postgres integration tests
# (steps 1+2 below). This script exists because that workflow deliberately stops
# at the backend — everything else is only ever checked here:
#
#   * step 3  native PostgreSQL lifecycle (praxiszeit-server.py, needs the repo
#             mounted — impossible in the backend-only workflow)
#   * steps 4-7  frontend: tsc, vitest, eslint, vite build
#   * step 8  E2E against a live docker compose stack
#
# So: a backend-only change is already gated by Actions; anything touching the
# frontend, the installer or the E2E surface needs this script.
#
# Steps:
#   1. Backend pytest             (unit + integration, SQLite-backed)
#   2. Backend RLS integration    (test_tenant_rls.py against real Postgres)
#   3. Native PG lifecycle        (praxiszeit-server.py, needs the repo mounted)
#   4. Frontend tsc --noEmit      (via node:20-alpine container, avoids
#                                  node_modules permission issues)
#   5. Frontend vitest            (unit tests for utils / pure logic)
#   6. Frontend eslint
#   7. Frontend vite build
#   8. E2E tests                  (docker compose stack must be healthy)
#
# Usage:   ./scripts/local-ci.sh [--skip-e2e]
#
set -euo pipefail

cd "$(dirname "$0")/.."

SKIP_E2E=0
for arg in "$@"; do
    case "$arg" in
        --skip-e2e) SKIP_E2E=1 ;;
    esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
step() { echo -e "\n${YELLOW}==>${NC} $*"; }

# -----------------------------------------------------------------------
# 1. Backend pytest (SQLite-backed unit + integration tests)
# -----------------------------------------------------------------------
# Excludes Postgres-only tests (RLS, concurrency) — run separately in step 2.
# TZ=Europe/Berlin: the container runs UTC, but the app computes "today" via
# now_local() (Europe/Berlin). Between ~22:00 and 24:00 UTC the two differ by a
# day and ~15 clock/create/break_waiver tests fail for that reason alone. Pinning
# the suite to the app's timezone removes that nightly false-red window.
step "Backend tests (pytest)"
if docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ -q --tb=short \
       --ignore=tests/test_tenant_rls.py \
       --ignore=tests/test_concurrency.py </dev/null 2>&1 | tail -5; then
    ok "Backend tests passed"
else
    fail "Backend tests failed"
fi

# -----------------------------------------------------------------------
# 2. Postgres-only integration (RLS + concurrency / row-lock races + Art.17 purge)
# -----------------------------------------------------------------------
# These tests hit the real Postgres instance so RLS policies, SELECT …
# FOR UPDATE and FOREIGN KEY rules actually enforce — SQLite unit tests cannot
# catch any of those regressions.
#
# test_purge_user_postgres.py is the Art.-17 erasure (DSGVO). It MUST run here:
# the SQLite suite has foreign keys switched OFF, so a missing cleanup in
# purge_user (precedent: shift_plans.created_by, #305) only ever shows up
# against real Postgres — as a 500 that BLOCKS the erasure request.
#
# test_cross_tenant_api.py is the third tenant-isolation suite named in
# CLAUDE.md. It is SQLite-backed (it exercises the explicit F-026
# `tenant_id == current_user.tenant_id` filters, not RLS) and therefore already
# runs inside step 1 — it is listed here only so the trio stays visible.
# Reference counts: step 2 runs 44 tests against real Postgres
# (20 RLS + 12 concurrency + 12 Art.-17 purge); the 18 cross-tenant tests run
# inside step 1. Same three files as the Actions step "Cross-tenant RLS +
# Art.17 purge + Race-Tests (real Postgres)".
step "Backend Postgres integration (RLS + concurrency + Art.17 purge)"
if docker compose exec -T -e TZ=Europe/Berlin backend pytest \
       tests/test_tenant_rls.py tests/test_concurrency.py \
       tests/test_purge_user_postgres.py -q --tb=short </dev/null 2>&1 | tail -5; then
    ok "Postgres integration verified"
else
    fail "Postgres integration tests failed"
fi

# -----------------------------------------------------------------------
# 3. Native PostgreSQL lifecycle (praxiszeit-server.py)
# -----------------------------------------------------------------------
# These 49 tests guard the native installer's PG decision logic — most
# importantly the Windows reinit bug where a foreign PG data directory (EDB
# leftover, scram auth) made the trust-based psql bootstrap hang forever on a
# password prompt.
#
# They skip themselves whenever praxiszeit-server.py is unreachable, and the
# backend image only contains the backend/ build context — so under
# `docker compose exec backend pytest` (steps 1+2) all 49 skip silently. They
# had therefore never run anywhere. Mounting the repo puts the orchestrator at
# ../praxiszeit-server.py relative to backend/, exactly as in a native install.
#
# --user: the mount is host-owned; the image's default user cannot create the
# logs/ directory the orchestrator opens at import time.
step "Native PG lifecycle (praxiszeit-server.py)"
if docker run --rm --user "$(id -u):$(id -g)" \
       -v "$(pwd)":/work -w /work/backend \
       -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp \
       -e SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
       -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X \
       -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci \
       -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost \
       -e DATABASE_URL=sqlite:////tmp/native-lifecycle.db \
       praxiszeit-backend \
       python -m pytest tests/test_native_pg_lifecycle.py -q --tb=short </dev/null 2>&1 | tail -5; then
    ok "Native PG lifecycle verified"
else
    fail "Native PG lifecycle tests failed"
fi

# -----------------------------------------------------------------------
# 4. Frontend TypeScript
# -----------------------------------------------------------------------
step "Frontend TypeScript (tsc --noEmit)"
if docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine \
       sh -c "npx tsc --noEmit" 2>&1 | tail -5; then
    ok "TypeScript clean"
else
    fail "TypeScript errors"
fi

# -----------------------------------------------------------------------
# 5. Frontend unit tests (vitest)
# -----------------------------------------------------------------------
step "Frontend unit tests (vitest)"
if docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine \
       sh -c "npm install --no-audit --no-fund --silent && npm test -- --run" 2>&1 | tail -20; then
    ok "Vitest passed"
else
    fail "Vitest failed"
fi

# -----------------------------------------------------------------------
# 6. Frontend ESLint
# -----------------------------------------------------------------------
step "Frontend ESLint"
if docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine \
       sh -c "npm run lint" 2>&1 | tail -5; then
    ok "ESLint: 0 errors"
else
    fail "ESLint errors"
fi

# -----------------------------------------------------------------------
# 7. Frontend production build
# -----------------------------------------------------------------------
step "Frontend production build (vite)"
if docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine \
       sh -c "npm run build" 2>&1 | tail -10; then
    ok "Frontend build successful"
else
    fail "Frontend build failed"
fi

# -----------------------------------------------------------------------
# 8. E2E tests (optional)
# -----------------------------------------------------------------------
if [ "$SKIP_E2E" -eq 1 ]; then
    warn "E2E tests skipped (--skip-e2e)"
else
    # -------------------------------------------------------------------
    # 8a. Preflight: auth rate limits must be raised for the E2E suite.
    #
    # Playwright logs in from several parallel workers. With the production
    # defaults (LOGIN_RATE_LIMIT=5/minute, REFRESH_RATE_LIMIT=10/minute) the
    # suite runs into an HTTP-429 storm and reports a large, confusing mix of
    # failed/flaky tests that has nothing to do with the code under test
    # (measured: 19 failed / 40 flaky / 208x 429). Fail fast with an
    # actionable message instead of burning a full E2E run.
    # -------------------------------------------------------------------
    # DATA_EXPORT_RATE_LIMIT defaults to 5/day and is per IP, so the whole
    # suite counts as one client: profile.spec.ts "DSGVO data export" burns one
    # unit per run and the sixth run of the day fails on a 429 the code did not
    # cause. Same treatment as the two auth limits.
    step "E2E preflight (auth rate limits)"
    limits_ok=1
    for var in LOGIN_RATE_LIMIT REFRESH_RATE_LIMIT DATA_EXPORT_RATE_LIMIT; do
        # Unset in the container => FastAPI falls back to the low prod default.
        value="$(docker compose exec -T backend printenv "$var" </dev/null 2>/dev/null | tr -d '\r')" || value=""
        number="${value%%/*}"
        if [ -z "$number" ] || ! [ "$number" -ge 100 ] 2>/dev/null; then
            warn "$var=${value:-<unset>} is too low for the E2E suite (need >= 100)"
            limits_ok=0
        fi
    done
    if [ "$limits_ok" -eq 0 ]; then
        fail "Raise the rate limits before running E2E, e.g. add to .env:
    LOGIN_RATE_LIMIT=10000/minute
    REFRESH_RATE_LIMIT=10000/minute
    DATA_EXPORT_RATE_LIMIT=10000/day
  then: docker compose up -d backend"
    fi
    ok "Rate limits raised for E2E"

    # -------------------------------------------------------------------
    # 8b. The frontend is served from a BUILT nginx image, not a host volume.
    # Without this rebuild the E2E suite silently exercises the previously
    # built bundle, so UI changes made in this working tree are not covered
    # and the run can be green for the wrong reason.
    # -------------------------------------------------------------------
    step "Rebuild frontend image (so E2E tests the current bundle)"
    if docker compose build frontend >/dev/null 2>&1 && docker compose up -d frontend >/dev/null 2>&1; then
        ok "Frontend image up to date"
    else
        fail "Frontend image rebuild failed"
    fi

    step "E2E tests (playwright)"
    if docker run --rm \
           -v "$(pwd)/e2e":/app -w /app \
           --network host \
           mcr.microsoft.com/playwright:v1.58.2-jammy \
           sh -c "npm install --silent && npx playwright test --reporter=line" 2>&1 | tail -15; then
        ok "E2E tests passed"
    else
        warn "E2E tests failed — check test output above"
        exit 1
    fi
fi

echo
ok "Local CI complete"
