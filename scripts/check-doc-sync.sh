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
  # Heute anerkannter Eintrag: kein Bearbeiten/Löschen, nur Schloss mit Hinweis
  # (TimeTracking CREDITED_TODAY_HINT, PR2 T16). Einen Knopf „Änderung beantragen"
  # gibt es nicht; ab morgen gelten „Änderungsantrag stellen"/„Löschantrag stellen".
  # Die 409-Meldung oben erreicht die Oberfläche praktisch nicht mehr.
  need_code "Anerkannter Eintrag – Änderung ab morgen per Änderungsantrag oder über die Verwaltung"
  need_code "Änderungsantrag stellen"
  need_code "Löschantrag stellen"
  # Anrechnungsanträge (Gesamtreview PR2, Fund 1/4/5): zwei Knöpfe statt
  # „Genehmigen = Anerkennen", Nachfrage der Sammel-Genehmigung, Kennzeichen
  # unter Zeiterfassung → „Anträge", Anrechnung heute erst nach Arbeitsende.
  need_code "Ohne Anerkennen genehmigen"
  need_code "ohne Anerkennen genehmigt"
  need_code "Anrechnung beantragt"
  need_code "Genehmigen mit Anerkennen"
  need_code "Alle genehmigen"
  need_code " genehmigen, davon "
  need_code "Das Ende liegt in der Zukunft – die Anrechnung kann erst nach Arbeitsende beantragt werden."
  need_code "Antrag auf Anrechnung eingereicht"
  # Meldung für noch geöffnete alte Browser-Tabs (Release-Notes, Spec 11.4)
  # Im Code als zwei Python-Stringstücke umbrochen (admin_users.LEGACY_WINDOW_FIELDS_DETAIL).
  need_code "Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende)"
  need_code "wurden durch Arbeitszeit-Blöcke ersetzt."
  # Task 3 (Admin-Handbuch „Arbeitszeit ändern"): Bearbeiten-Formular, Dialog,
  # Auswirkungs-Box (WhImpactBox), Verkürzungs-Kasten (ShorteningChoice),
  # Lösch-Bereich (WhDeletePanel), Plan-Hinweise, Verlauf, Dashboard-Hinweis.
  # Teile aus Template-Strings nur als zusammenhängende Stücke.
  need_code "Arbeitszeit heute"
  need_code "Noch nichts zu speichern — die Eingabe entspricht dem Stand, der"
  need_code "geplanter Verstoß gegen § 3 ArbZG; ein Eintrag "
  need_code "nach diesem Plan wird beim Erfassen abgelehnt und beim Ausstempeln als Verstoß gemeldet."
  need_code "Automatisch erfasster Ausgangswert vor der ersten Stundenänderung"
  need_code "Rückwirkende Änderung"
  need_code "Betrifft bereits erfasste Zeiteinträge"
  need_code "Betrifft bereits gebuchte Abwesenheiten"
  need_code "Ändert Überstunden oder Urlaubsverbrauch"
  need_code "Auswirkung (Puffer "
  need_code "Tagessoll je Wochentag: "
  need_code "Zeiteinträge: "
  need_code "ohne Rohstempel – nicht erweiterbar"
  need_code "1 offener Eintrag eines vergangenen Tages wird vorher automatisch geschlossen."
  need_code "1 Abwesenheit an einem Misch-Tag angeglichen "
  need_code "(Arbeit und Gutschrift am selben Tag)"
  need_code "Tage > 10 h: angerechnet bisher "
  need_code "Einzelheiten"
  need_code "Das Überstundenkonto sinkt im Wirkungsbereich um "
  need_code " (höheres Soll), obwohl kein Eintrag angerechnete Zeit verliert"
  need_code "während die Person eingestempelt ist – das Überstundenkonto sinkt beim Ausstempeln."
  need_code "vergangene Tage bleiben unverändert"
  need_code "Eine einseitige rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO wirkt nur für die Zukunft); "
  need_code "Notiz und Begründung zusammen höchstens 500 Zeichen."
  need_code "Die Änderung liegt vollständig vor der Änderung ab "
  need_code "wirksam und im Verlauf stehen; ab "
  need_code " gilt wieder der vorherige Stand."
  need_code "Auswirkung des Löschens"
  need_code "Auswirkung der Rücksetzung"
  need_code "Zurücksetzen"
  need_code "Hinweis zu Ihrer Arbeitszeit"
  need_code "Arbeitszeit im Profil ansehen"
  need_code " neu berechnet, angerechnete Zeit "
  need_code " Überstundenkonto im Zeitraum "
  need_code " Rückwirkende Verkürzung – Grund: "
  need_code "wurde zurückgenommen."
  need_code "Stundenänderung"
  need_code "Arbeitszeit-Änderung ab "
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

group_admin_bloecke() {
  local f=docs/handbuch/HANDBUCH-ADMIN.md
  need "$f" '<a id="arbeitszeit-bloecke"></a>'
  need "$f" '### Arbeitszeit-Blöcke (Soll-Arbeitszeit je Wochentag)'
  need "$f" 'Tagessoll = Summe der Blockdauern − Pause innerhalb der Blöcke'
  need "$f" '08:00–12:15 und 14:45–18:00 = 7:30 h'
  need "$f" 'Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert.'
  need "$f" 'liegt vollständig zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet werden 0 Stunden.'
  need "$f" 'gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet'
  need "$f" 'gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken'
  need "$f" 'Arbeitszeit-Fenster (Altbestand, nur Kappung)'
  need "$f" '<a id="nicht-angerechnet-anerkennen"></a>'
  need "$f" 'Die gesamte gestempelte Zeit (08:00–18:00) wird angerechnet.'
  need "$f" 'Nichtanrechnung ersetzt keine Vergütungsentscheidung.'
  need "$f" 'Schichtzeit inklusive Lücke höchstens 10 h); PraxisZeit prüft diese nicht.'
  need "$f" '**Bekannte Grenze:**'
  # Review Task 2: der Antragssatz hängt nur an Lückentexten geschlossener
  # Einträge (Spec 6.2), nie am Einstempeln.
  need "$f" 'Mitarbeitende lesen an den Lückenhinweisen zu geschlossenen Einträgen (nicht beim Einstempeln) zusätzlich'
  forbid "$f" 'Mitarbeitende lesen an den Lückenhinweisen zusätzlich'
  # Review Task 2: Reparaturweg für Feiertagseinträge aus ≤ 1.19.2 (#484) bleibt.
  need "$f" 'Bis Version 1.19.2 wurde ein Feiertag auf einem Werktag wie ein normaler Arbeitstag gekappt.'
  need "$f" 'speichern ihn unverändert, wird er mit der tatsächlich gestempelten Zeit neu berechnet.'
  # Review Task 2: Formular kennt den Modus „Nach Tagen", keinen Haken mehr.
  need "$f" 'Im Modus **„Nach Tagen"** (ebenfalls Viertelstunden je Wochentag)'
  forbid "$f" 'Bei individuellen Tagesstunden (ebenfalls Viertelstunden je Wochentag)'
  # Review Task 2: Altfenster kappen seit 1.20 auch den Auto-Close (bis 1.19.3
  # blieb 23:59 ungekappt, Spec E36/E42) — „genau wie vorher" verschwieg das.
  need "$f" 'neu auch automatisch geschlossene Einträge'
  forbid "$f" 'Diese Fenster kappen weiter genau wie vorher'
  # Review Task 2: hh:45 gilt nur beim Standardpuffer, der Puffer ist einstellbar (§ 13).
  need "$f" 'Bei einem Blockbeginn zur vollen Stunde und dem Standardpuffer von 15 Minuten landet'
  forbid "$f" 'Bei einem Blockbeginn zur vollen Stunde landet'
  forbid "$f" 'Soll-Arbeitszeiten je Wochentag'
  forbid "$f" 'Soll-Arbeitszeit-Fenster, #201'
  forbid "$f" '#soll-arbeitszeiten-soll-arbeitszeit-fenster-201'
}

group_admin_aendern() {
  local f=docs/handbuch/HANDBUCH-ADMIN.md
  need "$f" '**Arbeitszeit ändern:**'
  need "$f" 'Arbeitszeit anpassen…'
  need "$f" 'Arbeitszeit & Wochenstunden'
  need "$f" 'Nach Arbeitsblöcken'
  need "$f" 'Gesamtzeit 9:00 h · Pause 1:00 h · Tagessoll 8:00 h'
  need "$f" 'Ich habe die Auswirkungen geprüft und möchte speichern'
  need "$f" '##### Rückwirkende Änderungen: Neuberechnung'
  need "$f" '##### Verlängerung und Verkürzung'
  need "$f" 'Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.'
  need "$f" 'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)'
  need "$f" 'Mit der beschäftigten Person vereinbart'
  need "$f" '[Erfassungsfehler korrigiert]'
  need "$f" '[Einvernehmlich vereinbart]'
  need "$f" 'Ich habe die Gründe geprüft.'
  need "$f" 'Rückwirkende Verkürzung in das abgeschlossene Jahr 2025 ist gesperrt.'
  need "$f" 'auf den vorherigen Stand zurücksetzen'
  need "$f" 'Rückwirkend löschen mit Neuberechnung'
  need "$f" 'Auch eine rückwirkende **Erhöhung**'
  need "$f" 'Ihre Arbeitszeit wurde ab 01.09.2026 geändert'
  need "$f" 'Neukappung (Arbeitszeit-Änderung)'
  need "$f" 'Krank 4,0 h — Arbeitszeit-Änderung ab 15.03.2026'
  need "$f" 'Ändert sich durch die Blöcke der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung'
  need "$f" 'mitbestimmungspflichtig; ohne Zustimmung ist die Maßnahme gegenüber den Beschäftigten unwirksam. PraxisZeit prüft das nicht.'
  forbid "$f" 'Wochenstunden anpassen…'
  forbid "$f" 'Wochenstunden & Tagesplan'
  forbid "$f" 'Wochenstunden-Änderung ab'
  # Nachträge aus PR3 samt Reviews (Code maßgeblich, Gate Task 0):
  # Verlauf beginnt mit „Ab" (WorkingHoursModal), Bestätigung auch bei reiner
  # Saldo-/Urlaubswirkung, Urlaub/ArbZG-Befunde stehen außerhalb „Einzelheiten"
  # (18a), Notizfeld begrenzt, Rücksetzung mit 409 bei Zwischenzeile
  # (Gesamtreview PR3), Dashboard-Hinweis ohne verschachtelte Klammern.
  need "$f" 'Ab 01.03.2026 bis heute: Mo 08:00–12:00 + 15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 = 15,0 h/Woche'
  need "$f" 'Automatisch erfasster Ausgangswert vor der ersten Stundenänderung'
  need "$f" 'oder ändern sich Überstundenkonto bzw. Urlaubsverbrauch'
  need "$f" 'Unter **„Einzelheiten"** stehen'
  need "$f" 'Notiz und Begründung zusammen höchstens 500 Zeichen.'
  need "$f" 'Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.'
  need "$f" 'weil inzwischen eine weitere Änderung dazwischen angelegt wurde'
  need "$f" 'Ihre Arbeitszeit ändert sich ab 01.11.2026 (neu: 25,0 h/Woche).'
  need "$f" '(neu: 40,0 h/Woche auf 4 Arbeitstage)'
  forbid "$f" '(gleichmäßig, 5 Tage))'
  forbid "$f" '**Stundenänderungen:**'
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
