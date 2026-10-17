#!/usr/bin/env bash
# PraxisZeit — Docker-DB-Restore (Plain-SQL aus gzip-Dump).
#
# Spielt ein mit backup.sh (oder der Datensicherung der App) erzeugtes
# praxiszeit_<ts>.sql.gz wieder ein.
# Erwartet, dass es NEBEN der docker-compose.yml + .env liegt (Docker-Bundle).
#
#   bash restore.sh backups/praxiszeit_<ts>.sql.gz
#
# Typischer Update-Ablauf:
#   1. In der ALTEN Version:  bash backup.sh
#   2. Neue Version entpacken, .env + backups/ uebernehmen, Stack starten
#   3. In der NEUEN Version:  bash restore.sh backups/praxiszeit_<ts>.sql.gz
#   4. Ausgabe der Migrationen lesen: docker compose logs backend
#
# Ablauf (wie restore-backup.bat unter Windows):
#   - Dump auf Vollstaendigkeit pruefen, BEVOR etwas veraendert wird.
#   - Laufendes Backend anhalten. Migrationen laufen bei Docker nur beim Start
#     des Backend-Containers (CMD: alembic upgrade head && uvicorn). Ein
#     `docker compose up -d backend` ist bei laufendem Backend ein No-op — der
#     Dump setzte das Schema auf den Stand der Vorversion zurueck, und das neue
#     Backend arbeitete dagegen (1.20: Login HTTP 500 fuer alle, Gesamtreview).
#   - Datenbank frisch anlegen: --clean --if-exists entfernt nur, was im Dump
#     vorkommt. Eine Tabelle, die erst eine neuere Version angelegt hat (z. B.
#     security_events mit Fremdschluessel auf users), bliebe stehen und braeche
#     das Einspielen eines aelteren Backups ab.
#   - Dump einspielen, Rechte der Erstinitialisierung erneut anwenden.
#   - Backend wieder starten (nur, wenn es vorher lief) und warten, bis es
#     gesund ist: erst dann sind die Migrationen durchgelaufen.
#
# Der db-Dienst muss laufen. Die bisherigen Daten der Datenbank werden ersetzt.
set -euo pipefail

# $FILE relativ zum AUFRUF-Verzeichnis absolut machen, BEVOR das cwd wechselt.
FILE="${1:-}"
case "$FILE" in /*|"") ;; *) FILE="$(pwd)/$FILE" ;; esac

# Bundle: docker-compose.yml + .env liegen NEBEN diesem Skript. Git-Checkout:
# das Skript liegt in tools/docker/, docker-compose.yml + .env im Repo-Root.
cd "$(dirname "$0")"
if [ ! -f docker-compose.yml ] && [ -f ../../docker-compose.yml ]; then cd ../../; fi

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
    echo "Aufruf: bash restore.sh <pfad/zu/praxiszeit_*.sql.gz>" >&2
    exit 1
fi
if ! gzip -t "$FILE" 2>/dev/null; then
    echo "FEHLER: '$FILE' ist kein gueltiges gzip-Archiv." >&2
    exit 1
fi
# Ein vollstaendiger Plain-SQL-Dump endet mit dem pg_dump-Trailer. Fehlt er, war
# der Dump abgebrochen — dann NICHTS anfassen (die Datenbank wird gleich ersetzt).
# Kein `... | grep -q` unter pipefail (SIGPIPE, siehe update-pg-major.sh);
# tail -15: pg_dump 18 haengt nach dem Trailer noch `\unrestrict <token>` an.
_dump_tail="$(gunzip -c "$FILE" | tail -15)"
if ! grep -q "PostgreSQL database dump complete" <<<"$_dump_tail"; then
    echo "FEHLER: '$FILE' ist unvollstaendig (pg_dump-Trailer fehlt). Datenbank unangetastet." >&2
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
WAIT_SECONDS="${RESTORE_WAIT_SECONDS:-300}"

# Laeuft das Backend (auch in einer Neustart-Schleife), wird es angehalten und
# nach dem Einspielen wieder gestartet. `start` statt `up -d`: derselbe Container
# mit derselben Konfiguration (auch mit -f docker-compose.ssl.yml gestartet).
BACKEND_WAS_RUNNING="$(docker compose ps -q backend 2>/dev/null </dev/null || true)"

# Schlaegt ab hier etwas fehl, bleibt das Backend bewusst angehalten: gegen eine
# halb eingespielte Datenbank liefen sonst die Migrationen, und der Start legte
# einen frischen Admin an.
trap '_rc=$?; if [ "$_rc" != 0 ]; then echo "" >&2; echo "ABBRUCH (Exit $_rc): Restore nicht abgeschlossen. Das Backend bleibt angehalten." >&2; echo "Ursache beheben, dann erneut: bash restore.sh \"${FILE}\"" >&2; fi' EXIT

if [ -n "$BACKEND_WAS_RUNNING" ]; then
    echo "Halte das Backend an ..."
    docker compose stop backend </dev/null
fi

echo "Lege die Datenbank '${PG_DB}' frisch an ..."
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS \"${PG_DB}\" WITH (FORCE)" \
    -c "CREATE DATABASE \"${PG_DB}\"" </dev/null

echo "Spiele '${FILE}' in Datenbank '${PG_DB}' (User '${PG_USER}') ein ..."
# ON_ERROR_STOP=1: psql bricht beim ersten echten SQL-Fehler ab + Exit != 0 (sonst
# meldet psql trotz Fehlern Exit 0 -> ein kaputter Restore sähe erfolgreich aus).
# Die DROP … IF EXISTS aus --clean --if-exists erzeugen keine Fehler.
# -q: ohne die hunderten Statuszeilen (SET, COPY, GRANT …) — Fehler erscheinen weiter.
gunzip -c "$FILE" | docker compose exec -T db psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB"

# GRANT CONNECT ON DATABASE steht nicht im Dump (gehoert zur Datenbank, nicht zu
# ihrem Inhalt) — dieselben Rechte wie bei der Erstinitialisierung erneut setzen.
INIT_SQL=/docker-entrypoint-initdb.d/01_init-db-user.sql
if docker compose exec -T db test -f "$INIT_SQL" </dev/null; then
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" -q -f "$INIT_SQL" </dev/null
fi
echo "Restore abgeschlossen."

if [ -z "$BACKEND_WAS_RUNNING" ]; then
    trap - EXIT
    echo "Das Backend lief nicht. Beim naechsten Start (docker compose up -d) heben die"
    echo "Migrationen das Schema auf den Stand dieser Version."
    echo "Danach die Ausgabe der Migrationen lesen: docker compose logs backend"
    exit 0
fi

echo "Starte das Backend — die Migrationen heben das Schema auf den Stand dieser Version ..."
docker compose start backend </dev/null
deadline=$(( $(date +%s) + WAIT_SECONDS ))
while :; do
    read -r state health <<<"$(docker compose ps -a backend --format '{{.State}} {{.Health}}' 2>/dev/null </dev/null | head -1)" || true
    if [ "${state:-}" = "running" ] && { [ "${health:-}" = "healthy" ] || [ -z "${health:-}" ]; }; then
        break
    fi
    if [ "${state:-}" != "running" ] && [ "${state:-}" != "created" ]; then
        echo "FEHLER: Backend nach dem Restore nicht gestartet (Zustand: ${state:-unbekannt})." >&2
        echo "Meist ist eine Migration gescheitert — Ausgabe: docker compose logs backend" >&2
        docker compose logs --tail=30 backend >&2 </dev/null || true
        trap - EXIT
        exit 1
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "FEHLER: Backend nach ${WAIT_SECONDS} s noch nicht bereit (Zustand: ${state} ${health:-})." >&2
        echo "Ausgabe der Migrationen pruefen: docker compose logs backend" >&2
        trap - EXIT
        exit 1
    fi
    sleep 2
done
trap - EXIT
echo "Backend laeuft wieder."
# Hinweise der Migrationen (z. B. „*** HINWEIS (Migration 073) ***“ … „*** ENDE
# HINWEIS ***“) gleich hier zeigen — sie nennen Datensaetze, die von Hand
# nachzuziehen sind. Nur die Ausgabe DIESES Starts: das Log des Containers
# enthaelt auch fruehere (im Update-Ablauf die Migration der frischen, leeren
# Datenbank). Startzeit vom Docker-Daemon, nicht von der Host-Uhr — unter
# Docker Desktop laeuft die Uhr der VM gern nach.
_cid="$(docker compose ps -q backend 2>/dev/null </dev/null | head -1 || true)"
START_TS="$(docker inspect --format '{{.State.StartedAt}}' "$_cid" 2>/dev/null </dev/null || true)"
[ -n "$START_TS" ] || START_TS="10m"
_notes="$(docker compose logs --no-log-prefix --since "$START_TS" backend 2>/dev/null </dev/null \
    | sed -n '/\*\*\* HINWEIS/,/\*\*\* ENDE HINWEIS \*\*\*/p' || true)"
if [ -n "$_notes" ]; then
    echo ""
    echo "Hinweise der Migrationen (bitte lesen):"
    printf '%s\n' "$_notes"
    echo ""
fi
echo "Vollstaendige Ausgabe der Migrationen: docker compose logs --since ${START_TS} backend"
echo "Danach die Seite im Browser neu laden (Strg+F5)."
