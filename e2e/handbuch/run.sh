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
  local cid out stichtag
  cid="$(dc ps -q backend)"
  [ -n "$cid" ] || { echo "Backend-Container laeuft nicht" >&2; exit 1; }
  docker cp backend/create_handbuch_testdata.py "$cid:/app/create_handbuch_testdata.py"
  # Bei Fehlschlag trotzdem die Ausgabe zeigen (set -e bricht sonst vor dem printf ab).
  if ! out="$(dc exec -T backend env -u LD_PRELOAD -u FAKETIME python create_handbuch_testdata.py </dev/null 2>&1)"; then
    printf '%s\n' "$out" >&2
    echo "Seed fehlgeschlagen" >&2
    exit 1
  fi
  printf '%s\n' "$out"
  # Letzte Zeile der Ausgabe: STICHTAG=YYYY-MM-DD
  stichtag="$(printf '%s\n' "$out" | tail -n 1)"
  [[ "$stichtag" == STICHTAG=* ]] || { echo "Letzte Seed-Zeile ist kein STICHTAG=: $stichtag" >&2; exit 1; }
  printf 'BASE_URL=%s\n%s\n' "$BASE_URL" "$stichtag" > "$STATE_FILE"
  enable_faketime "${stichtag#STICHTAG=}"
}

# R12: Serveruhr = Stichtag 10:30 (laufend). Nur das Backend wird neu erzeugt.
enable_faketime() {
  local day="$1"
  printf 'FAKETIME="@%s 10:30:00"\n' "$day" > "$FT_ENV"
  docker build -q -f e2e/handbuch/Dockerfile.backend-faketime \
    --build-arg BASE=pzhandbuch-backend -t pzhandbuch-backend-faketime e2e/handbuch >/dev/null
  dc up -d --no-build --no-deps --force-recreate backend
  wait_ready || exit 1
  echo "Serveruhr: ${day} 10:30 (libfaketime)"
}

cmd_down() {
  if [ -f "$ENV_FILE" ]; then
    dc down -v --remove-orphans
  else
    docker compose -p "$PROJECT" down -v --remove-orphans
  fi
  rm -f "$STATE_FILE"
}

case "${1:-}" in
  up) cmd_up ;;
  seed) cmd_seed ;;
  down) cmd_down ;;
  all)
    cmd_up
    cmd_seed
    # HOOK_CAPTURE: Aufnahme (Playwright capture.ts) wird spaeter hier eingehaengt.
    ;;
  *) echo "Aufruf: $0 up|seed|down|all" >&2; exit 2 ;;
esac
