#!/usr/bin/env bash
# Prüft, ob der gebaute Service Worker (frontend/dist/sw.js) die App vorlädt.
# Hintergrund (1.25.0): Ein npm-Override (minimatch 11 unter glob 11 von
# workbox-build) ließ die Glob-Muster ins Leere laufen — seit 1.22.0 enthielt
# sw.js nur noch 3 Einträge (Icons + Manifest), ohne index.html. Der Build lief
# trotzdem grün. Aufruf: bash scripts/check-sw-precache.sh [dist-Verzeichnis]
set -euo pipefail
DIST="${1:-$(dirname "$0")/../frontend/dist}"
SW="$DIST/sw.js"
[ -f "$SW" ] || { echo "FEHLER: $SW fehlt"; exit 1; }
COUNT=$(grep -o 'url:"[^"]*"' "$SW" | wc -l)
if ! grep -q 'url:"index.html"' "$SW"; then
  echo "FEHLER: sw.js lädt index.html nicht vor ($COUNT Einträge) — Workbox-Glob kaputt?"; exit 1
fi
if [ "$COUNT" -lt 10 ]; then
  echo "FEHLER: sw.js lädt nur $COUNT Dateien vor (erwartet >= 10)"; exit 1
fi
echo "OK: sw.js lädt $COUNT Dateien vor"
