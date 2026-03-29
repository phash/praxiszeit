#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Use sudo if not root (prod server requires it for Docker)
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

COMPOSE="$SUDO docker compose -f docker-compose.yml -f docker-compose.ssl.yml"

echo "=== PraxisZeit Deploy ==="

# Pull latest code
echo ">> git pull"
git pull origin master

# Build updated containers
echo ">> Building frontend + backend"
$COMPOSE build frontend backend

# Run migrations + restart
echo ">> Starting services"
$COMPOSE up -d

echo ">> Waiting for backend health..."
sleep 3

# Quick health check
if $COMPOSE exec -T backend python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/api/health')" 2>/dev/null; then
    echo ">> Backend OK"
else
    echo ">> Backend health check failed, showing logs:"
    $COMPOSE logs --tail=20 backend
    exit 1
fi

echo "=== Deploy complete ==="
