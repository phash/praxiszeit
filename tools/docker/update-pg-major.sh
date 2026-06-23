#!/usr/bin/env bash
# PraxisZeit — Docker-Update MIT PostgreSQL-Major-Upgrade (z. B. PG16 -> PG18).
#
# Hintergrund: Ein PostgreSQL-Major-Upgrade ist NICHT in-place — postgres:18 kann
# ein von postgres:16 angelegtes Daten-Volume nicht starten (es bricht mit einer
# ausfuehrlichen "incompatible"-Meldung ab). Dieser Helfer macht den Umstieg
# sicher: er sichert die laufende DB, entfernt NUR das DB-Volume (die #213-Backups
# im praxiszeit_backups-Volume bleiben erhalten), startet einen frischen
# PG18-Stack und spielt den Dump wieder ein.
#
# Aufruf NEBEN der docker-compose.yml (im Docker-Bundle):  bash update-pg-major.sh
# (Der ALTE Stack muss noch laufen, damit gesichert werden kann.)
set -euo pipefail
cd "$(dirname "$0")"   # Bundle-Root (hier liegen docker-compose.yml + backup.sh/restore.sh)

[ -f docker-compose.yml ] || { echo "FEHLER: keine docker-compose.yml neben diesem Skript (bitte im Docker-Bundle ausfuehren)." >&2; exit 1; }

echo "==> 1/5  Backup der laufenden Datenbank (alte PostgreSQL-Version)..."
bash backup.sh
BK="$(ls -1t backups/praxiszeit_*.sql.gz 2>/dev/null | head -1)"
[ -n "$BK" ] && [ -f "$BK" ] || { echo "FEHLER: kein Backup erzeugt — Abbruch (Daten unangetastet)." >&2; exit 1; }
echo "    Backup: $BK"

echo "==> 2/5  Exaktes DB-Volume ermitteln (vor dem Stop)..."
VOL="$(docker compose ps -q db | xargs -r docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')"
[ -n "$VOL" ] || { echo "FEHLER: DB-Volume nicht gefunden — laeuft der alte Stack noch?" >&2; exit 1; }
echo "    Volume: $VOL"

echo "==> 3/5  Stack stoppen + altes DB-Volume entfernen (Backups bleiben erhalten)..."
docker compose down
docker volume rm "$VOL"

echo "==> 4/5  Frischen PG18-Stack bauen + starten..."
docker compose up -d --build
for _ in $(seq 1 40); do
    [ "$(docker compose ps db --format '{{.Health}}' 2>/dev/null)" = "healthy" ] && break
    sleep 3
done
[ "$(docker compose ps db --format '{{.Health}}' 2>/dev/null)" = "healthy" ] \
    || { echo "FEHLER: neue Datenbank wurde nicht 'healthy'. Backup liegt unter ${BK}." >&2; exit 1; }

echo "==> 5/5  Restore in den frischen Cluster..."
bash restore.sh "$BK"
docker compose up -d backend

echo ""
echo "Fertig. Das alte DB-Volume wurde durch einen frischen PG18-Cluster ersetzt."
echo "Das Backup bleibt erhalten: ${BK} — erst loeschen, wenn alles geprueft ist."
