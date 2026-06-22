#!/usr/bin/env bash
# PraxisZeit — Docker-DB-Restore (Plain-SQL aus gzip-Dump).
#
# Spielt ein mit backup.sh erzeugtes praxiszeit_<ts>.sql.gz wieder ein.
# Erwartet, dass es NEBEN der docker-compose.yml + .env liegt (Docker-Bundle).
#
#   bash restore.sh backups/praxiszeit_<ts>.sql.gz
#
# Typischer Update-Ablauf:
#   1. In der ALTEN Version:  bash backup.sh
#   2. Neue Version entpacken, .env + backups/ uebernehmen, Stack starten
#   3. In der NEUEN Version:  bash restore.sh backups/praxiszeit_<ts>.sql.gz
#   4. docker compose up -d backend   (Alembic-Migrationen heben das Schema auf head)
#
# Der Stack muss laufen. Der Dump ist mit --clean --if-exists erzeugt, ueberschreibt
# also die vorhandenen Tabellen.
set -euo pipefail

cd "$(dirname "$0")"

FILE="${1:-}"
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
    echo "Aufruf: bash restore.sh <pfad/zu/praxiszeit_*.sql.gz>" >&2
    exit 1
fi
if ! gzip -t "$FILE" 2>/dev/null; then
    echo "FEHLER: '$FILE' ist kein gueltiges gzip-Archiv." >&2
    exit 1
fi
if [ ! -f .env ]; then
    echo "FEHLER: .env nicht gefunden — zuerst 'bash generate-secrets.sh' ausfuehren." >&2
    exit 1
fi

PG_USER="$(grep -E '^POSTGRES_USER=' .env | head -1 | cut -d= -f2-)"
PG_DB="$(grep -E '^POSTGRES_DB=' .env | head -1 | cut -d= -f2-)"
PG_USER="${PG_USER:-praxiszeit}"
PG_DB="${PG_DB:-praxiszeit}"

echo "Spiele '${FILE}' in Datenbank '${PG_DB}' (User '${PG_USER}') ein ..."
gunzip -c "$FILE" | docker compose exec -T db psql -U "$PG_USER" -d "$PG_DB"
echo "Restore abgeschlossen."
echo "Backend neu starten, damit Migrationen laufen: docker compose up -d backend"
