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

# need_code_label DATEI TEXT — TEXT ist in DATEI eine eigene Beschriftung: ein
# JSX-Textknoten, der allein auf seiner Zeile steht, direkt vor einem Tag
# (TEXT<span…) oder zwischen zwei Tags (>TEXT<). Für kurze Knopf- und
# Feldtexte („Zurücksetzen", „Einzelheiten"): als bloßes Wort finden sie sich
# auch in Kommentaren, Fehlermeldungen und fremden Komponenten, und need_code
# bliebe grün, obwohl der zitierte Knopf längst anders heißt.
need_code_label() {
  if [[ -f "$1" ]] && awk -v t="$2" '
      { s = $0; sub(/^[ \t]+/, "", s); sub(/[ \t\r]+$/, "", s)
        if (s == t || index(s, t "<") == 1 || index($0, ">" t "<")) { f = 1; exit } }
      END { exit !f }' "$1"; then
    return 0
  fi
  echo "NICHT IM CODE: $2 ($1)"; FAIL=1
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
  # Kurze Beschriftungen an ihre Komponente gebunden: „Arbeitszeit heute" steht
  # auch über dem Stempel-Timer, „Einzelheiten" in einem Python-Kommentar,
  # „Zurücksetzen" in einem Kommentar von ImportXls und in der Fehlermeldung
  # „Fehler beim Zurücksetzen", „Stundenänderung" in rund zehn Dateien.
  need_code_label frontend/src/pages/admin/users/UserForm.tsx "Arbeitszeit heute"
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
  need_code_label frontend/src/pages/admin/users/WhImpactBox.tsx "Einzelheiten"
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
  need_code_label frontend/src/pages/admin/users/WhDeletePanel.tsx "Zurücksetzen"
  need_code "Hinweis zu Ihrer Arbeitszeit"
  need_code "Arbeitszeit im Profil ansehen"
  need_code " neu berechnet, angerechnete Zeit "
  need_code " Überstundenkonto im Zeitraum "
  need_code " Rückwirkende Verkürzung – Grund: "
  need_code "wurde zurückgenommen."
  need_code "wh_change: 'Stundenänderung'"
  # Spaltenkopf der Jahresübersicht (XLSX/ODS), den „Berichte" nennt.
  need_code '"Stundenänderungen",'
  need_code "Arbeitszeit-Änderung ab "
  # Task 4 (Admin-Handbuch übrige Abschnitte): Exportspalten (#498 → „Zeiteinträge"),
  # Antragsprüfung (Stempelzeile, Abweichung, Aktuell-Kasten), Quellen des
  # Protokolls, Puffertext (Settings), Anwesenheits-Hinweise (presence_service,
  # f-Strings nur als zusammenhängende Stücke), 24-Wochen-Auswertung (Reports).
  need_code '"Unterbrechung (Min)", "Zeiteinträge"'
  need_code "Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet."
  need_code "Zeiten weichen von den Stempeln ab (gestempelt "
  need_code " · nicht angerechnet aktuell "
  need_code "Nicht angerechnet (Lücke): "
  need_code 'AUDIT_SOURCE = "wh_reclamp"'
  need_code 'CREDIT_OVERRIDE_SOURCE = "credit_override"'
  need_code "zwischen zwei Blöcken; eine Lücke bis zum doppelten Puffer wird angerechnet."
  need_code "Einträge ändern sich durch das Speichern dieser Einstellung allein nicht."
  need_code "eine Ruhepause ist nicht erfasst ("
  need_code "Die Lücke gilt nur dann als Pause, wenn sie tatsächlich frei war."
  need_code "(abzüglich erfasster Pausen) – mehr als 10 Stunden. Angerechnet werden "
  need_code " h; die Höchstgrenze gilt für die tatsächliche Arbeitszeit."
  need_code "24-Wochen-Durchschnitt §3 ArbZG"
  need_code "Ø angerechnet / Tag"
  need_code "Anwesenheit laut Stempel (Ø / Tag)"
  need_code "Anwesenheit laut Stempel gesamt"
  need_code "Wochen &gt; 48 h laut Stempel"
  need_code "laut Stempel Ø &gt; 8 h"
  need_code "keine Soll-Arbeitstage"
  need_code "Anrechnung später neu berechnet wird, und die Grenze gilt für die tatsächliche Arbeitszeit."
  # Sammelzeile der Abwesenheits-Rückrechnung (admin_users._log_wh_change_retarget,
  # Review Task 4): Quelle „wh_change", Anlegen und Löschen.
  need_code "Abwesenheit(en) im Zeitraum "
  need_code "auf neues Tagessoll nachgezogen"
  need_code "auf den davor gültigen Wert zurückgerechnet"
  # Task 5 (Mitarbeiter-Handbuch): Frühstart-Meldung, wie sie der Server schickt
  # (clock_in, Geviertstrich; der Rückfalltext in arbzgWarnings erscheint nie),
  # Zusatzzeile „angerechnet bis", Antragsformular „Anrechnung beantragen",
  # Profilkarte „Meine Arbeitszeit".
  need_code "Du hast vor deinem Soll-Beginn eingestempelt — angerechnet ab "
  need_code 'gestempelt ${rawEnd} · angerechnet bis ${effEnd}'
  need_code 'nach ${hm(breakMinutes)} h Pause'
  need_code "Die gesamte gestempelte Zeit soll angerechnet werden. Bitte begründen Sie, warum Sie in dieser Zeit gearbeitet haben."
  need_code "Der Eintrag wurde automatisch geschlossen – bitte das tatsächliche Ende angeben."
  need_code 'Wochenstunden: ${deHoursExact(today.weekly_hours)}'
  need_code ' Std/Woche`}'
  need_code "Feste Monatsarbeitszeit: "
  need_code "Ohne Stundenzählung: kein Tagessoll; die Arbeitszeit-Blöcke begrenzen die Anrechnung nicht."
  need_code "Anwesenheit nicht angerechnet: "
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
  # Review Task 3: Löschen gibt es nur an der jüngsten Zeile (kein P25). Ab heute
  # → Rücksetzung ab morgen; nach heute → Löschen verkürzt nie. Eine Verkürzung
  # ohne Rücksetzung tritt in der Oberfläche praktisch nicht auf.
  forbid "$f" 'Ist keine Rücksetzung möglich'
  need "$f" 'Eine Änderung, die erst nach heute beginnt, verkürzt beim Löschen nichts'
  # Review Task 4: die wh_change-Sammelzeile (nur wenn Abwesenheiten nachgezogen werden).
  need "$f" 'sind Abwesenheiten betroffen, zusätzlich eine Sammelzeile **„Stundenänderung"** ohne Datum'
}

group_admin_rest() {
  local f=docs/handbuch/HANDBUCH-ADMIN.md
  need "$f" '**Version 2.9 | Stand: Oktober 2026 (für PraxisZeit 1.20.0)**'
  need "$f" 'Rechenstand der Software (Version 1.20.0)'
  need "$f" 'Netto-Spalte; unter der Uhrzeit steht bei gekappten Einträgen'
  need "$f" 'Unterbrechung (Min)** und **Zeiteinträge**'
  need "$f" 'Nicht angerechnet (Min)** (letzte Spalte, ab 1.20.0)'
  need "$f" 'Von 07:45, Bis 18:15, Netto 8,00, Nicht angerechnet 240'
  need "$f" 'inkl. Unterbrechung, Zeiteinträge und Nicht angerechnet'
  need "$f" 'Genehmigen und anerkennen'
  need "$f" 'Ohne Anerkennen genehmigen'
  need "$f" 'Alle genehmigen'
  need "$f" 'Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.'
  need "$f" '| **Anerkennungen** |'
  need "$f" 'Neukappung (Arbeitszeit-Änderung)'
  need "$f" 'Eine Änderung des Puffers wirkt auf neue Einträge. Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn, auch wenn er später bearbeitet wird.'
  need "$f" 'Bereits gespeicherte Einträge ändern sich durch das Speichern dieser Einstellung allein nicht.'
  need "$f" 'Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt'
  need "$f" 'Anwesenheit laut Stempel'
  need "$f" '| **Pause in der Lücke** |'
  need "$f" '**Arbeitszeit-Blöcke – weitere Rechtsgrundlagen:**'
  need "$f" '**Nicht angerechnete Zeit prüfen**'
  need "$f" 'Ist = (Ende − Beginn) − Pause − nicht angerechnete Zeit zwischen den Arbeitszeit-Blöcken'
  need "$f" 'Pause 30 Min. → 6,50 h'
  forbid "$f" '#6-benutzer-verwalten'
  forbid "$f" 'Version 2.8 | Stand'
  forbid "$f" 'Ist ein **Soll-Arbeitszeit-Fenster** hinterlegt'
  forbid "$f" 'auf das Fenster gekappte Zeit'
  forbid "$f" 'Kappung auf das Arbeitszeit-Fenster'
  forbid "$f" '**Arbeitsblöcke** die einzelnen Blöcke'
  forbid "$f" 'inkl. Unterbrechung und Arbeitsblöcke'
  # Über den Plan hinaus (Review Focus 3, Code maßgeblich): auch die PDF-Zeile
  # nennt gestempelte Einträge nicht „Blöcke"; Spalte „Arbeitsblöcke" gibt es nicht mehr.
  need "$f" 'Im **PDF** stehen die Einträge in „Von"/„Bis" untereinander'
  forbid "$f" 'Im **PDF** stehen die Blöcke'
  forbid "$f" 'die Spalte „Arbeitsblöcke"'
  forbid "$f" 'wenn ein Arbeitszeit-Fenster hinterlegt ist'
  # Antragsprüfung (Gesamtreview PR2, Fund 2): „Genehmigen und anerkennen"
  # rechnet die BEANTRAGTEN Zeiten ungekappt an; die Prüfung zeigt die Stempel.
  need "$f" 'Zeiten weichen von den Stempeln ab (gestempelt 08:00–18:00)'
  need "$f" 'nicht angerechnet aktuell 2:30 h'
  # XLS-Vorschau (PR2 Task 12 + Review): Netto vom Server, Anwesenheitshinweise,
  # Konfliktzeile kann beide Kennzeichen tragen.
  need "$f" 'Eine Konfliktzeile kann beide Kennzeichen tragen'
  # 24-Wochen-Auswertung (PR2 Task 9 + Reviews): bis 1.19.3 nicht dokumentiert.
  need "$f" '### §3 ArbZG – 24-Wochen-Durchschnitt'
  need "$f" '„laut Stempel Ø > 8 h"'
  need "$f" '„keine Soll-Arbeitstage"'
  need "$f" 'die Grenze gilt für die tatsächliche Arbeitszeit'
  # Review Task 4: §9 erklärt auch die wh_change-Sammelzeile (Code:
  # admin_users._log_wh_change_retarget, Spec 10.3).
  need "$f" 'sind Abwesenheiten betroffen, zusätzlich eine Sammelzeile ohne Datum (z. B. „Arbeitszeit-Änderung zum'
  need "$f" '(beide Quelle „wh_change", Anzeige „Stundenänderung")'
  need "$f" 'Abwesenheit(en) im Zeitraum 2026-09-01–2026-10-09 auf neues Tagessoll nachgezogen'
  # Review Task 4 (2. Runde): Die Anwesenheitsprüfungen gelten für alle
  # (Erwachsenenschwellen, kein Kennzeichen „jugendlich" im Code); nur die
  # strengeren JArbSchG-Regeln prüft PraxisZeit nicht (Spec 8.3).
  need "$f" 'Es gelten die Grenzen für Erwachsene; die strengeren Regeln für Jugendliche (§§ 11, 12 JArbSchG) prüft PraxisZeit nicht'
  forbid "$f" 'prüft PraxisZeit keine dieser Grenzen'
  # „Ist" ist die angerechnete Zeit (net_hours, nach der Kappung, 18.3),
  # nicht die tatsächlich erfasste bzw. geleistete (Begriffsregel des Plans).
  need "$f" '| **Ist** | Angerechnete Arbeitszeit der Zeiteinträge (bei Arbeitszeit-Blöcken nach der Kappung, → 18.3) + gutgeschriebene Abwesenheiten (Krank/Fortbildung) |'
  forbid "$f" '| **Ist** | Tatsächlich erfasste Arbeitszeit'
  forbid "$f" '| **Ist** | Tatsächlich geleistete Stunden'
}

# Review Task 4: Die 48-h-Wochengrenze nennt der Code als § 3 ArbZG
# (WEEKLY_HOURS_WARNING, PRESENCE_WEEKLY_HOURS); § 14 regelt außergewöhnliche
# Fälle. Alle Flächen, die die Wochenwarnung einem Paragraphen zuordnen.
group_arbzg_48h() {
  local f=docs/handbuch/HANDBUCH-ADMIN.md
  need "$f" '| **Wochenhöchstgrenze** | > 48h/Woche | Warnung | § 3 ArbZG |'
  need "$f" 'Wochenwarnung > 48h |'
  forbid "$f" 'Warnung | § 14 ArbZG'
  forbid "$f" 'Außergewöhnliche Fälle: 48h/Woche Warnschwelle'
  need docs/handbuch/CHEATSHEET-ADMIN.md '| Wochenstunden | > 48h | Warnung | §3 |'
  forbid docs/handbuch/CHEATSHEET-ADMIN.md '| Wochenstunden | > 48h | Warnung | §14 |'
  forbid frontend/src/components/DocViewer.tsx '§14 (48h-Wochenwarnung)'
  forbid frontend/src/components/DocViewer.tsx '>§14</td><td className="px-3 py-2 border border-gray-200 text-gray-600">48h-Wochenwarnung'
}

group_mitarbeiter() {
  local f=docs/handbuch/HANDBUCH-MITARBEITER.md
  need "$f" '**Version:** 2.9 · **Stand:** Oktober 2026 (PraxisZeit 1.20.0)'
  need "$f" '### 3.3 Arbeitszeit-Blöcke und Anrechnung'
  need "$f" '(#33-arbeitszeit-blöcke-und-anrechnung)'
  need "$f" 'gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet'
  need "$f" 'Eingestempelt zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet wird erst ab 14:45.'
  need "$f" 'Pause in der Lücke wird zusätzlich abgezogen'
  need "$f" 'nicht ausgestempelt – automatisch geschlossen'
  need "$f" 'Anrechnung beantragen'
  need "$f" 'Anerkannter Eintrag – Änderung ab morgen per Änderungsantrag oder über die Verwaltung'
  need "$f" 'Das Ende liegt in der Zukunft – die Anrechnung kann erst nach Arbeitsende beantragt werden.'
  need "$f" 'ohne Anerkennen genehmigt'
  need "$f" 'Pause zwischen den Arbeitsblöcken'
  need "$f" 'Meine Arbeitszeit'
  need "$f" 'Ihre Arbeitszeit wurde ab 01.09.2026 geändert'
  need "$f" 'Nicht angerechnet heißt nicht unbezahlt'
  forbid "$f" 'erfassten Blöcke'
  forbid "$f" 'vergessener Nachmittagsblock'
  forbid "$f" '#33-soll-arbeitszeiten-und-anrechnung'
  forbid "$f" 'Soll-Arbeitszeit hinterlegt'
  forbid "$f" 'Soll-Zeiten für Sie hinterlegt'
  forbid "$f" 'Änderung beantragen'
  # Über den Plan hinaus (Code maßgeblich, Gate Task 0):
  # Fußzeile wie der Kopf auf 1.20.0.
  need "$f" '*PraxisZeit – Zeiterfassungssystem | Mitarbeiter-Handbuch v2.9 | Oktober 2026 (PraxisZeit 1.20.0)*'
  forbid "$f" 'Mitarbeiter-Handbuch v2.8'
  # Frühstart-Meldung so, wie der Server sie schickt (clock_in): Geviertstrich
  # und konkrete Uhrzeit; den Rückfalltext mit Halbgeviertstrich gibt es nicht.
  need "$f" 'Du hast vor deinem Soll-Beginn eingestempelt — angerechnet ab 07:45.'
  forbid "$f" 'eingestempelt – die Anrechnung beginnt ab dem frühestmöglichen Zeitpunkt'
  # Alle Zusatzzeilen aus Spec 13.1, auch Ende gekürzt, Hülle + Lücke, Pause,
  # dazu die Monatssumme im Journal (13.2).
  need "$f" 'gestempelt 19:00 · angerechnet bis 18:15'
  need "$f" 'gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken'
  need "$f" 'nach 0:30 h Pause'
  need "$f" 'Anwesenheit nicht angerechnet: 7:30 h'
  need "$f" 'eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 7:45 h (08:00–18:15) · 2:30 h zwischen den Blöcken nicht angerechnet'
  # Anwesenheits-Hinweis bei durchgestempelter Lücke (presence_service, 8.3).
  need "$f" 'Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – eine Ruhepause ist nicht erfasst'
  # Antragsformular „Anrechnung beantragen" (ChangeRequestForm): Hinweis, festes
  # Datum, tatsächliches Ende beim automatisch geschlossenen Eintrag.
  need "$f" 'Die gesamte gestempelte Zeit soll angerechnet werden. Bitte begründen Sie, warum Sie in dieser Zeit gearbeitet haben.'
  need "$f" 'Der Eintrag wurde automatisch geschlossen – bitte das tatsächliche Ende angeben.'
  # V1 (Spec P18, Entschieden 2026-10-11): ein echtes Ende 23:59 ist eintragbar.
  need "$f" 'Auch ein tatsächliches Ende um **23:59**'
  # #502: Datum beim Bearbeiten gesperrt, ein anderes Datum nur per Antrag
  # (TimeTracking, im JSX über zwei Zeilen umbrochen).
  need "$f" 'Das Datum bleibt beim Bearbeiten fest. Gehört die Zeit zu einem anderen Tag: Eintrag löschen und oben über „Antrag“ einen Änderungsantrag für diesen Tag stellen.'
  # Dashboard-Hinweis laut Code (reclamp_audit.notice_text): ohne verschachtelte
  # Klammern, Arbeitstage nur bei Änderung, Rücksetzung und Rücknahme.
  need "$f" 'Hinweis zu Ihrer Arbeitszeit'
  need "$f" 'Arbeitszeit im Profil ansehen'
  need "$f" 'Ihre Arbeitszeit ändert sich ab 01.11.2026 (neu: 25,0 h/Woche).'
  need "$f" '(neu: 40,0 h/Woche auf 4 Arbeitstage)'
  need "$f" 'auf den vorherigen Stand zurückgesetzt (neu: '
  need "$f" 'Die Arbeitszeit-Änderung ab 01.09.2026 wurde zurückgenommen.'
  need "$f" 'Überstundenkonto im Zeitraum +1:45 h.'
  forbid "$f" '(gleichmäßig, 5 Tage))'
  # Profilkarte (MyWorkScheduleCard): Tage mit „ · ", Wochenstunden mit Komma.
  need "$f" 'ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00 · Do 08:00–12:00 · 15,5 Std/Woche'
  need "$f" 'Wochenstunden: 15,5'
  # „Ist" ist die angerechnete Zeit (net_hours), Begriffsregel des Plans wie
  # im Admin-Handbuch (Review Task 4).
  need "$f" 'Ihr **Ist** ist Ihre angerechnete Arbeitszeit'
  forbid "$f" 'Ihr **Ist** ist Ihre tatsächlich erfasste Arbeitszeit'
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
