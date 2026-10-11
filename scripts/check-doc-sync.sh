#!/usr/bin/env bash
#
# Doku-Abgleich für die Arbeitszeit-Blöcke (Spec
# docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md, Abschnitt 16).
#
# Prüft die Nutzer- und Technik-Doku gegen den Code und gegeneinander:
#   code     – jeder Wortlaut, den die Doku zitiert, steht im App-Code (Gate)
#   mirror   – frontend/public/help/*.md ist byte-identisch zu docs/handbuch/*.md
#   links    – jeder In-Page-Link (#anker) der Handbücher hat ein Ziel
#   weitere  – je Doku-Fläche Pflicht- und Verbotsbegriffe (eine Gruppe je Fläche)
#
# Aufruf:  bash scripts/check-doc-sync.sh <gruppe> [<gruppe>…]
#          bash scripts/check-doc-sync.sh all
# Exit 0 = alles stimmt; 1 = Abweichungen (eine Zeile je Fund); 2 = Aufruffehler.
set -uo pipefail
cd "$(dirname "$0")/.."

FAIL=0
CODE_DIRS=(frontend/src backend/app)

# need DATEI TEXT — TEXT muss wörtlich in DATEI stehen.
need() {
  grep -qF -e "$2" "$1" || { echo "FEHLT     $1: $2"; FAIL=1; }
}

# forbid DATEI TEXT — TEXT darf in DATEI nicht (mehr) stehen.
forbid() {
  if grep -qF -e "$2" "$1"; then echo "VERALTET  $1: $2"; FAIL=1; fi
}

# need_code TEXT [VARIANTE…] — mindestens eine Variante steht im App-Code.
# Tests zählen nicht (einen Wortlaut, der nur in einem Test steht, sieht niemand),
# die In-App-Doku auch nicht (DocViewer/helpContent zitieren die Wortlaute selbst
# und würden das Gate sonst ab Task 8 immer erfüllen). Binärdateien ebenso wenig:
# ein veraltetes __pycache__/*.pyc enthält Texte, die im Quelltext längst anders
# lauten oder nur über einen Zeilenumbruch verteilt stehen (-I, --exclude-dir).
need_code() {
  local v
  for v in "$@"; do
    if grep -rqIF --exclude-dir='__pycache__' \
         --exclude='*.test.ts' --exclude='*.test.tsx' \
         --exclude='DocViewer.tsx' --exclude='helpContent.tsx' \
         -e "$v" "${CODE_DIRS[@]}"; then
      return 0
    fi
  done
  echo "NICHT IM CODE: $1"; FAIL=1
}

# Gate: Wortlaute, die die Doku dieses PRs zitiert (Spec 6.2, 8.3, 8.4, 11.4,
# 12.1, 12.3, 13.1, 13.3, 14). Weicht der Code ab, entscheidet Task 0 Step 3.
group_code() {
  # Dialog, Editor, Benutzerformular (PR3)
  need_code "Arbeitszeit anpassen…"
  need_code "Arbeitszeit & Wochenstunden" "Arbeitszeit &amp; Wochenstunden"
  need_code "Nach Arbeitsblöcken"
  need_code "Pause innerhalb der Blöcke"
  need_code "Keine Arbeitszeit-Blöcke hinterlegt"
  need_code "Ich habe die Auswirkungen geprüft und möchte speichern"
  need_code "vergangene Einträge bleiben unverändert"
  need_code "mit Neuberechnung"
  need_code "Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)"
  need_code "Mit der beschäftigten Person vereinbart"
  need_code "Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit."
  need_code "Ich habe geprüft, dass die hinterlegte Arbeitszeit falsch war (Fehlerkorrektur)."
  need_code "Ich habe geprüft, dass die rückwirkende Änderung mit der beschäftigten Person vereinbart ist."
  need_code "Ich habe die Gründe geprüft."
  need_code "Mir ist bewusst, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht nicht gedeckt ist."
  need_code "Auf den Mindestlohn für geleistete Stunden kann nicht verzichtet werden (§ 3 MiLoG)."
  need_code "Bei Minijob oder Vergütung in Mindestlohnhöhe kann die Kürzung"
  need_code "auf den vorherigen Stand zurücksetzen"
  need_code "Rückwirkend löschen mit Neuberechnung"
  need_code "Der vorherige Stand hat sich inzwischen geändert"
  need_code "Arbeitszeit-Fenster (Altbestand, nur Kappung)"
  need_code "In Arbeitszeit-Blöcke umwandeln"
  need_code "Fenster entfernen"
  need_code "Die Arbeitszeit-Blöcke enden mit dieser Änderung"
  need_code "ohne Wirkung (keine Stundenzählung)"
  need_code "ist nicht länger als der doppelte Puffer"
  need_code "Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG); PraxisZeit prüft diese nicht."
  need_code "Mit Betriebsrat ist die Änderung mitbestimmungspflichtig"
  need_code "Rückwirkende Verkürzung in das abgeschlossene Jahr"
  need_code "nur rückwirkend mit Begründung oder abbrechen"
  need_code "Zeiteinträge neu berechnet"
  # Kappung und Hinweise (PR1/PR2)
  need_code "Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster"
  need_code "Zwischen den Arbeitsblöcken ("
  need_code "liegt vollständig zwischen"
  need_code "Eingestempelt zwischen zwei Arbeitsblöcken"
  need_code "Zusätzlich werden zwischen den Arbeitsblöcken"
  need_code "beantragen Sie die Anrechnung"
  need_code "Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt"
  need_code "Pause in der Lücke wird zusätzlich abgezogen"
  need_code "Laut Stempel"
  need_code "Arbeitszeit-Änderung ab"
  # Sichtbarkeit, Anerkennen, Anträge (PR2)
  need_code "zwischen den Blöcken nicht angerechnet"
  need_code "nicht ausgestempelt"
  need_code "automatisch geschlossen"
  need_code "Anrechnung beantragen"
  need_code "Anerkennen"
  need_code "Die gesamte gestempelte Zeit"
  need_code "Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen."
  need_code "Anerkannter Eintrag – Änderung bitte per Änderungsantrag." "Anerkannter Eintrag — Änderung bitte per Änderungsantrag."
  need_code "Genehmigen und anerkennen"
  need_code "Eintrag ist anerkannt"
  need_code "Anwesenheit nicht angerechnet"
  need_code "Nicht angerechnet (Min)"
  need_code "Neukappung (Arbeitszeit-Änderung)"
  need_code "Anrechnung anerkannt"
  need_code "Anwesenheit laut Stempel"
  need_code "Eine Änderung des Puffers wirkt auf neue Einträge."
  need_code "Meine Arbeitszeit"
  need_code "Pause zwischen den Arbeitsblöcken"
  need_code "Ihre Arbeitszeit wurde ab"
  need_code "Ihre Arbeitszeit wird in Blöcken hinterlegt."
  # Einstellungen: Abschnitt und Feld, die das Handbuch nennt
  need_code "Soll-Arbeitszeit-Fenster"
  need_code "Puffer für Soll-Arbeitszeit-Fenster (Min.)"
  # Nachträge aus PR1–PR3 samt Reviews, die die Doku ebenfalls zitiert:
  # Datum beim Bearbeiten gesperrt (#502; im JSX umbrochen → zwei Stücke),
  # Rücksetzen mit 409, Notizlänge (Gesamtreview PR3), Dashboard-Hinweise (14).
  need_code "Das Datum bleibt beim Bearbeiten fest. Gehört die Zeit zu einem anderen Tag:"
  need_code "Eintrag löschen und oben über „Antrag“ einen Änderungsantrag für diesen Tag stellen."
  need_code "Einträge vergangener Tage können nur per Änderungsantrag geändert werden"
  need_code "Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."
  need_code "Notiz und Begründung zusammen höchstens 500 Zeichen."
  need_code "Ihre Arbeitszeit ändert sich ab"
  need_code "auf den vorherigen Stand zurückgesetzt (neu: "
  # Meldung für noch geöffnete alte Browser-Tabs (Release-Notes, Spec 11.4)
  # Im Code als zwei Python-Stringstücke umbrochen (admin_users.LEGACY_WINDOW_FIELDS_DETAIL).
  need_code "Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende)"
  need_code "wurden durch Arbeitszeit-Blöcke ersetzt."
}

group_mirror() {
  local f
  for f in HANDBUCH-ADMIN HANDBUCH-MITARBEITER CHEATSHEET-ADMIN CHEATSHEET-MITARBEITER SCHNELLSTART; do
    cmp -s "docs/handbuch/$f.md" "frontend/public/help/$f.md" \
      || { echo "SPIEGEL   frontend/public/help/$f.md weicht von docs/handbuch/$f.md ab"; FAIL=1; }
  done
}

group_links() {
  python3 - docs/handbuch/*.md docs/BERECHNUNGEN.md docs/GLOSSAR.md <<'PY' || FAIL=1
import re
import sys


def slug(heading):
    # GitHub-Anker: Kleinbuchstaben, Satzzeichen weg (Umlaute bleiben), Leerzeichen -> "-"
    text = re.sub(r"[`*]", "", heading).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


bad = 0
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as fh:
        body = re.sub(r"```.*?```", "", fh.read(), flags=re.S)
    anchors, seen = set(), {}
    for m in re.finditer(r"^#{1,6} (.+?)\s*$", body, re.M):
        s = slug(m.group(1))
        n = seen.get(s, 0)
        seen[s] = n + 1
        anchors.add(s if n == 0 else f"{s}-{n}")
    anchors |= set(re.findall(r'<a id="([^"]+)"', body))
    for m in re.finditer(r"\]\(#([^)\s]+)\)", body):
        if m.group(1) not in anchors:
            print(f"LINK      {path}: #{m.group(1)} hat kein Ziel")
            bad = 1
sys.exit(bad)
PY
}

# --- weitere Gruppen werden oberhalb dieser Zeile eingefügt ---

run_group() {
  if declare -F "group_$1" >/dev/null; then
    "group_$1"
  else
    echo "Unbekannte Gruppe: $1"; FAIL=1
  fi
}

if [ "$#" -eq 0 ]; then
  echo "Aufruf: bash scripts/check-doc-sync.sh <gruppe>…|all"
  exit 2
fi
if [ "$1" = "all" ]; then
  set -- $(declare -F | awk '{print $3}' | sed -n 's/^group_//p')
fi
for g in "$@"; do run_group "$g"; done
[ "$FAIL" -eq 0 ] && echo "OK: $*"
exit "$FAIL"
