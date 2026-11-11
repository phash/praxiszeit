#!/usr/bin/env bash
#
# Kopiert den Handbuch-Code (frontend/src/handbuch, ohne Tests) und die
# Handbuch-Bilder (frontend/public/help/img/*.webp) in ein pzweb-Checkout.
#
# Aufruf:  bash scripts/sync-handbuch-to-pzweb.sh [<pzweb-pfad>]
# Standard-Pfad: ../pzweb (relativ zur Repo-Wurzel); sonst Argument 1 oder $PZWEB_DIR.
#
# Ziel: <pzweb>/frontend/src/handbuch/  und  <pzweb>/frontend/public/handbuch/img/
# Dateien, die es in der Quelle nicht mehr gibt, werden dort gelöscht (rsync --delete).
# Jede .ts/.tsx-Datei bekommt die GENERIERT-Kopfzeile, .css einen Kommentar
# gleichen Wortlauts; .json bleibt unverändert (JSON kennt keine Kommentare).
# Die Gruppe handbuch_pzweb in scripts/check-doc-sync.sh ruft dieses Skript mit
# einem Temp-Verzeichnis als Ziel auf und vergleicht per diff -r.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-${PZWEB_DIR:-$ROOT/../pzweb}}"
[ -d "$DEST" ] || { echo "pzweb-Pfad nicht gefunden: $DEST" >&2; exit 2; }
DEST="$(cd "$DEST" && pwd)"
# Schutz: rsync --delete darf nie auf Wurzel, das App-Repo selbst oder ein Nicht-pzweb zielen.
if [ "$DEST" = "/" ] || [ "$DEST" = "$ROOT" ] || [ ! -f "$DEST/frontend/package.json" ]; then
  echo "Ziel ist kein pzweb-Checkout (verweigert): $DEST — erwartet <pzweb>/frontend/package.json, nicht / und nicht das App-Repo" >&2
  exit 1
fi

SRC="$ROOT/frontend/src/handbuch"
IMG="$ROOT/frontend/public/help/img"
TEXT='GENERIERT aus phash/praxiszeit frontend/src/handbuch — nicht bearbeiten (scripts/sync-handbuch-to-pzweb.sh)'

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/src" "$STAGE/img"
rsync -a --exclude='*.test.*' "$SRC/" "$STAGE/src/"
rsync -a --include='*.webp' --exclude='*' "$IMG/" "$STAGE/img/"

while IFS= read -r -d '' f; do
  case "$f" in
    *.ts|*.tsx) { printf '// %s\n\n' "$TEXT"; cat "$f"; } > "$f.new" ;;
    *.css)      { printf '/* %s */\n\n' "$TEXT"; cat "$f"; } > "$f.new" ;;
    *) continue ;;
  esac
  mv "$f.new" "$f"
done < <(find "$STAGE/src" -type f -print0)

mkdir -p "$DEST/frontend/src/handbuch" "$DEST/frontend/public/handbuch/img"
rsync -a --delete --checksum "$STAGE/src/" "$DEST/frontend/src/handbuch/"
rsync -a --delete --checksum "$STAGE/img/" "$DEST/frontend/public/handbuch/img/"
echo "Handbuch nach $DEST synchronisiert."
