#!/usr/bin/env bash
#
# F-062: Local CI pipeline — runs the equivalent of what the disabled
# GitHub Actions would run.
#
# Steps:
#   1. Backend pytest         (docker compose exec)
#   2. Frontend tsc --noEmit  (via node:20-alpine container, avoids
#                              node_modules permission issues)
#   3. Frontend eslint
#   4. Frontend vite build
#   5. E2E tests              (docker compose stack must be healthy)
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
# 1. Backend pytest
# -----------------------------------------------------------------------
step "Backend tests (pytest)"
if docker compose exec -T backend pytest tests/ -q --tb=short 2>&1 | tail -5; then
    ok "Backend tests passed"
else
    fail "Backend tests failed"
fi

# -----------------------------------------------------------------------
# 2. Frontend TypeScript
# -----------------------------------------------------------------------
step "Frontend TypeScript (tsc --noEmit)"
if docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine \
       sh -c "npx tsc --noEmit" 2>&1 | tail -5; then
    ok "TypeScript clean"
else
    fail "TypeScript errors"
fi

# -----------------------------------------------------------------------
# 3. Frontend ESLint
# -----------------------------------------------------------------------
step "Frontend ESLint"
if docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine \
       sh -c "npm run lint" 2>&1 | tail -5; then
    ok "ESLint: 0 errors"
else
    fail "ESLint errors"
fi

# -----------------------------------------------------------------------
# 4. Frontend production build
# -----------------------------------------------------------------------
step "Frontend production build (vite)"
if docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine \
       sh -c "npm run build" 2>&1 | tail -10; then
    ok "Frontend build successful"
else
    fail "Frontend build failed"
fi

# -----------------------------------------------------------------------
# 5. E2E tests (optional)
# -----------------------------------------------------------------------
if [ "$SKIP_E2E" -eq 1 ]; then
    warn "E2E tests skipped (--skip-e2e)"
else
    step "E2E tests (playwright)"
    if docker run --rm \
           -v "$(pwd)/e2e":/app -w /app \
           --network host \
           mcr.microsoft.com/playwright:v1.50.0-jammy \
           sh -c "npm install --silent && npx playwright test --reporter=line" 2>&1 | tail -15; then
        ok "E2E tests passed"
    else
        warn "E2E tests failed — check test output above"
        exit 1
    fi
fi

echo
ok "Local CI complete"
