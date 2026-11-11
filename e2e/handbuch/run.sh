#!/usr/bin/env bash
# Wegwerf-Instanz fuer Handbuch-Screenshots: run.sh up|seed|down|all
# Projektname IMMER pzhandbuch (nie praxiszeit: Dev-Volumes!).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

PROJECT=pzhandbuch
PORT=8099
BASE_URL="http://localhost:${PORT}"
ENV_FILE="e2e/handbuch/.env"
STATE_FILE="e2e/handbuch/.state"
FT_ENV="e2e/handbuch/.faketime.env"   # existiert nur nach `seed` (R12)

dc() {
  local extra=()
  if [ -f "$FT_ENV" ]; then
    extra=(--env-file "$FT_ENV")
  fi
  docker compose -p "$PROJECT" --env-file "$ENV_FILE" "${extra[@]}" \
    -f docker-compose.yml -f e2e/handbuch/compose.override.yml \
    $([ -f "$FT_ENV" ] && echo "-f e2e/handbuch/compose.faketime.yml") "$@"
}

wait_ready() {
  for _ in $(seq 1 90); do
    if curl -fsS "${BASE_URL}/api/system/info" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Instanz wurde nicht bereit" >&2
  return 1
}

make_env() {
  [ -f "$ENV_FILE" ] && return 0
  local out
  out="$(cat e2e/handbuch/env.template)"
  while [[ "$out" == *__SECRET__* ]]; do
    out="${out/__SECRET__/$(python3 -c 'import secrets;print(secrets.token_hex(32))')}"
  done
  printf '%s\n' "$out" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

cmd_up() {
  make_env
  rm -f "$FT_ENV"   # up startet immer mit echter Uhr; `seed` schaltet faketime zu
  dc up -d --build db backend frontend
  echo "Warte auf ${BASE_URL}/api/system/info ..."
  wait_ready || exit 1
  printf 'BASE_URL=%s\n' "$BASE_URL" > "$STATE_FILE"
  echo "Instanz bereit: $BASE_URL"
}

cmd_seed() {
  [ -f "$ENV_FILE" ] || { echo "Erst 'run.sh up' ausfuehren" >&2; exit 1; }
  local cid out stichtag day
  cid="$(dc ps -q backend)"
  [ -n "$cid" ] || { echo "Backend-Container laeuft nicht" >&2; exit 1; }
  # 1. Stichtag auf der ECHTEN Uhr berechnen (R14), noch ohne Datenbankfaelschung noetig
  docker cp backend/create_handbuch_testdata.py "$cid:/app/create_handbuch_testdata.py"
  if ! out="$(dc exec -T -e HANDBUCH_SEED=1 backend env -u LD_PRELOAD -u FAKETIME python create_handbuch_testdata.py --print-stichtag </dev/null 2>&1)"; then
    printf '%s\n' "$out" >&2
    echo "Stichtag-Berechnung fehlgeschlagen" >&2
    exit 1
  fi
  stichtag="$(printf '%s\n' "$out" | tail -n 1)"
  [[ "$stichtag" == STICHTAG=* ]] || { echo "Letzte Zeile ist kein STICHTAG=: $stichtag" >&2; exit 1; }
  day="${stichtag#STICHTAG=}"
  # 2. Uhr von Datenbank UND Backend auf den Stichtag stellen (beide neu erzeugt)
  enable_faketime "$day"
  # 3. Seed unter der gefaelschten Uhr, mit ausdruecklichem Stichtag
  cid="$(dc ps -q backend)"
  docker cp backend/create_handbuch_testdata.py "$cid:/app/create_handbuch_testdata.py"
  # Bei Fehlschlag trotzdem die Ausgabe zeigen (set -e bricht sonst vor dem printf ab).
  if ! out="$(dc exec -T -e HANDBUCH_SEED=1 backend python create_handbuch_testdata.py --stichtag "$day" </dev/null 2>&1)"; then
    printf '%s\n' "$out" >&2
    echo "Seed fehlgeschlagen" >&2
    exit 1
  fi
  printf '%s\n' "$out"
  printf 'BASE_URL=%s\nSTICHTAG=%s\n' "$BASE_URL" "$day" > "$STATE_FILE"
  smoke_check
}

# R14: Serveruhr = Stichtag 10:30 Europe/Berlin (laufend) fuer Backend UND Datenbank,
# mit derselben relativen Verschiebung (sonst lehnt der Audit-Waechter ab).
enable_faketime() {
  local day="$1" off
  off="$(python3 - "$day" <<'PY'
import sys, time
from datetime import datetime
from zoneinfo import ZoneInfo
t = datetime.fromisoformat(sys.argv[1] + "T10:30:00").replace(tzinfo=ZoneInfo("Europe/Berlin"))
print(int(t.timestamp() - time.time()))
PY
)"
  printf 'FAKETIME=%s\n' "$off" > "$FT_ENV"
  docker build -q -f e2e/handbuch/Dockerfile.backend-faketime \
    --build-arg BASE=pzhandbuch-backend -t pzhandbuch-backend-faketime e2e/handbuch >/dev/null
  docker build -q -f e2e/handbuch/Dockerfile.db-faketime -t pzhandbuch-db-faketime e2e/handbuch >/dev/null
  dc up -d --no-build --force-recreate db backend
  dc restart frontend   # nginx loest den Upstream backend:8000 nur beim Start auf
  wait_ready || exit 1
  echo "Serveruhr: ${day} 10:30 (libfaketime, Versatz ${off} s, Backend und Datenbank)"
}

# Admin-Login + PUT einer harmlosen Einstellung (Pufferzeit 15 -> 16 -> 15): jede
# Aenderung schreibt eine Audit-Zeile, die der Waechter aus Migration 076 nur
# annimmt, wenn Backend- und DB-Uhr zusammenpassen. Gleicher Wert schreibt keine
# Audit-Zeile und prueft deshalb nichts. Scheitert -> Exit 1 mit Antwortkoerper.
smoke_check() {
  local tok code body val
  tok="$(curl -fsS -X POST "${BASE_URL}/api/auth/login" -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"Handbuch2026!"}' \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')" \
    || { echo "Smoke: Admin-Login fehlgeschlagen" >&2; exit 1; }
  body="$(mktemp)"
  for val in 16 15; do
    code="$(curl -sS -o "$body" -w '%{http_code}' -X PUT "${BASE_URL}/api/admin/settings/work_window_grace_minutes" \
      -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' -d "{\"value\":\"$val\"}")"
    if [ "$code" != "200" ]; then
      echo "Smoke: PUT /api/admin/settings/work_window_grace_minutes=$val -> HTTP $code" >&2
      cat "$body" >&2; echo >&2
      rm -f "$body"
      exit 1
    fi
  done
  rm -f "$body"
  echo "Smoke: Admin-Login und Einstellungs-PUT (16, dann 15) ok: HTTP 200"
}

cmd_down() {
  if [ -f "$ENV_FILE" ]; then
    dc down -v --remove-orphans
  else
    docker compose -p "$PROJECT" down -v --remove-orphans
  fi
  rm -f "$STATE_FILE" "$FT_ENV"
}

case "${1:-}" in
  up) cmd_up ;;
  seed) cmd_seed ;;
  down) cmd_down ;;
  all)
    cmd_up
    cmd_seed
    ;;
  *) echo "Aufruf: $0 up|seed|down|all" >&2; exit 2 ;;
esac
