# Arbeitszeit-Blöcke PR4 „Doku" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alle fünf Doku-Sync-Flächen, die Technik-Doku, `CLAUDE.md`, die Handbuch-Screenshots und den CHANGELOG-Entwurf für 1.20.0 auf die Arbeitszeit-Blöcke aus PR1–PR3 bringen – einschließlich Vergütungs- und Mitbestimmungshinweis – und die pzweb-Web-Anleitungen in einem eigenen PR nachziehen.

**Architecture:** Der Test dieses PRs ist ein Prüfskript `scripts/check-doc-sync.sh`. Es prüft zuerst als Gate, dass jeder Wortlaut, den die Doku zitiert, im gemergten Code von PR1–PR3 steht; danach je Doku-Fläche Pflicht- und Verbotsbegriffe, die Byte-Gleichheit des Hilfe-Spiegels `frontend/public/help` und die In-Page-Anker der Handbücher. Die In-App-Flächen (DocViewer, Schnellstart, Kontexthilfe) sichert ein Vitest ab, die pzweb-Seiten deren eigene Vitests. Die Doku folgt dem Code; wo der Code vom Spec-Wortlaut abweicht, entscheidet das Gate in Task 0, nicht der Schreibende.

**Tech Stack:** Markdown, React 18 + TypeScript (Vitest + Testing Library), Bash + Python 3 (Prüfskript), Playwright (Screenshots), Python 3.12/SQLAlchemy (Seed-Skript), pzweb: React + Vitest im Container `node:20`.

**Spec:** `docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md` (verbindlich; Abschnitt 20 „PR4", Abschnitt 16 „Doku-Flächen + CLAUDE.md", Abschnitt 2 inkl. „Entschieden 2026-10-08", 19.1). Die zitierten Wortlaute stammen aus 6.2, 8.3, 8.4, 9.5, 10.2, 11.4, 12.1, 12.3, 13.1, 13.3, 14, 15.1, 15.2, 16.1. Wer einen Task umsetzt, liest die im Task genannten Spec-Abschnitte mit.

## Global Constraints

- **Reihenfolge (Spec 20):** PR4 beginnt erst, wenn PR1, PR2 und PR3 im Integrationszweig gemergt sind (Gate Task 0 Step 1). 1.20.0 wird erst nach PR1–PR4 released. Die pzweb-PR (Tasks 14–15) wird erst mit dem Release gemergt – wie pzweb #67.
- **Arbeitsort:** `/home/manuel/claude/praxiszeit`, neuer Zweig `docs/bloecke-pr4` vom Integrationszweig. Der Name des Integrationszweigs wird in Task 0 nach `.git/pr4-base` geschrieben und in Task 13 als PR-Basis gelesen. pzweb: `/home/manuel/claude/pzweb`, Zweig `docs/web-anleitungen-1.20.0` von `main`.
- **Zeilennummern** beziehen sich auf `3d46c2f` (Lane-Merge). PR1–PR3 ändern laut ihren Plänen keine Nutzer-Doku (Spec 20: „Doku" = PR4); die Ersetzungen sind trotzdem über **wörtliche Anker** formuliert („ersetze den Absatz, der mit … beginnt"), nie über Zeilennummern allein. Vor jedem Edit die Datei lesen.
- **Begriffe (verbindlich in allen Flächen):** „Arbeitszeit-Block"/„Blöcke" = die vertraglich hinterlegte Soll-Arbeitszeit; „Zeiteintrag"/„Eintrag" = gestempelte Zeit. Gestempelte Einträge heißen nie „Blöcke" (die Issue-Lanes #494/#500 schrieben „alle heute erfassten Blöcke", „vergessener Nachmittagsblock" – das wird in diesem PR auf „Einträge" umgestellt). „Lücke" = Zeit zwischen zwei Blöcken. „angerechnet" = `net_hours`; „nicht angerechnet" = Lücke **plus** an der Hülle abgeschnittene Zeit (P19). „Anerkennen", „Anrechnung beantragen", „Neukappung" wie in der Oberfläche.
- **Bedienelemente (Spec E58/E59/12.1):** Knopf „Arbeitszeit anpassen…" (mit U+2026), Dialog „Arbeitszeit & Wochenstunden", Modi „Gleichmäßig" / „Nach Tagen" / „Nach Arbeitsblöcken", Feld „Pause innerhalb der Blöcke". Die Begriffe „Wochenstunden anpassen…", „Wochenstunden & Tagesplan" und die Formularfelder „Soll-Beginn/Soll-Ende je Wochentag" kommen als aktuelle Bedienung in keiner Fläche mehr vor.
- **Zitate:** Oberflächen- und Meldungstexte stehen in der Doku wortgleich wie im Code. Der Hülle-Text („Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt (Beginn 07:37 → 07:45; Puffer 15 Minuten).") wird nur mit seinem ersten Satz zitiert – der zweite Satz steht im Code in ASCII-Umschrift („urspruengliche") und bleibt byte-identisch (PR1).
- **Zeichen:** Zeitspannen mit Halbgeviertstrich `–` (U+2013, „08:00–12:00"); Formeln und negative Werte mit Minuszeichen `−` (U+2212); Geviertstrich `—` (U+2014) nur, wo der zitierte Code-Text ihn hat. Doku-Anführungszeichen wie im Bestand: „…" (U+201E öffnend, ASCII `"` schließend); der Mitarbeiter-Hinweis aus dem Code endet mit „Anrechnung beantragen“ (U+201C) und wird so zitiert.
- **Rechtskästen (Spec 16.1/E61/E76), wortgleich:** Vergütungs-Kasten und Mitbestimmungs-Kasten (volle Fassung) sowie der JArbSchG-Satz stehen in HANDBUCH-ADMIN.md, im Admin-Handbuch des DocViewer und auf der pzweb-Seite HandbuchAdmin. Die Kurzfassung des Mitbestimmungs-Hinweises steht nur im Dialog (PR3).
- **Fünf Sync-Flächen (CLAUDE.md):** (1) `docs/handbuch/*.md` + `docs/BERECHNUNGEN.md` + `docs/GLOSSAR.md`; (2) `frontend/src/components/DocViewer.tsx` + `frontend/src/constants/helpContent.tsx`; (3) `frontend/public/help/*.md` byte-identisch zu `docs/handbuch/*.md` (BERECHNUNGEN/GLOSSAR werden nicht gespiegelt); (4) pzweb `frontend/src/pages/marketing/anleitung/*`; (5) `SchnellstartAdmin` in DocViewer.tsx.
- **Spiegel:** Wer `docs/handbuch/<X>.md` ändert, kopiert im selben Commit `cp docs/handbuch/<X>.md frontend/public/help/<X>.md`.
- **#498-Spalte:** Endgültiger Name „Zeiteinträge" (Spec 15.1 „vor dem Release eine der beiden Bezeichnungen ändern"); Task 1 setzt das um, falls PR2 es nicht getan hat. Alle Texte dieses Plans verwenden „Zeiteinträge".
- **Prüfskript:** `bash scripts/check-doc-sync.sh <gruppe>…` bzw. `… all` (aus dem Repo-Wurzelverzeichnis). Exit 0 = OK, 1 = Abweichung (je Fund eine Zeile `FEHLT`/`VERALTET`/`NICHT IM CODE`/`SPIEGEL`/`LINK`).
- **Frontend-Tests** (aus `frontend/`): `npx vitest run <datei> --pool=threads`, `npx tsc --noEmit`. Der Standard-`forks`-Pool hängt auf dieser Maschine.
- **Backend-Tests (nur Task 1)** nie im geteilten Container. Aus dem Repo-Wurzelverzeichnis, vorher `rm -f backend/test.db backend/test.db-wal backend/test.db-shm` (Dateien einzeln nennen – zsh bricht bei Glob ohne Treffer ab), nie zwei Läufe gleichzeitig:
  `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/<datei> -q -p no:cacheprovider`
- **pzweb-Tests** (aus `/home/manuel/claude/pzweb`; glibc-Image `node:20`, **nicht** alpine): `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx vitest run src/pages/marketing/anleitung --pool=threads` und `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx tsc -b` (pzweb baut strikt mit `noUnusedLocals`).
- **Commits** immer `git commit -F - <<'EOF' … EOF` (Umlaute, Klammern, Pfeile), letzte Zeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Kein `--no-verify` (Pre-Commit-Secret-Scanner).
- **Issue-Lanes:** #497/#498 (Export-Doku: Differenz, geteilte Dienste), #499 (§4-Tagesprüfung, Schalter Pflicht-Pause-Ausnahme), #493/#494/#500/#501 (Mitarbeiter-Dashboard, Stempelkarte, Monat/Woche, Jahresend-Warnung), #496 (Antrags-Arbeitstage), #495 (Praxisname im Aushang) und #491 F4 (§10-Feld im Antragsformular) sind bei `3d46c2f` in den Doku-Dateien bereits beschrieben. Tasks, die genau diese Absätze anfassen, tragen **⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen**: vor dem Edit den zitierten Anker per `grep -n` suchen; fehlt er, den Absatz im aktuellen Stand suchen und die Ersetzung sinngemäß an derselben Stelle vornehmen.
- **Shell:** Das Tool-Shell ist zsh. `grep`-Muster immer mit `-F -e`; Globs mit möglicherweise null Treffern nicht an `rm` geben.
- **Umbrüche:** `docs/BERECHNUNGEN.md`, `docs/GLOSSAR.md` und die pzweb-JSX-Dateien sind hart umbrochen – eine zitierte Altstelle („… ersetzen durch …") kann über einen Zeilenumbruch laufen. Beim Ersetzen den Umbruch mitnehmen (Edit-Werkzeug mit dem gelesenen Original). Die Handbücher unter `docs/handbuch/` und die `<p>`-Zeilen in `DocViewer.tsx` sind nicht umbrochen (ein Absatz = eine Zeile).

## Review Focus

1. **Doku nennt eine Bedienung oder Meldung, die es nicht gibt** (PR2/PR3 haben einen Wortlaut anders umgesetzt, Prettier hat JSX-Text umbrochen, ein Gedankenstrich ist ein anderer): Die Person sucht den Knopf oder die Meldung vergeblich – `code`-Gruppe in Task 0, Abweichungsverfahren in Task 0 Step 3.
2. **Eine der fünf Flächen beschreibt noch die alte Bedienung** („Wochenstunden anpassen…", Soll-Beginn/-Ende-Felder): Wer die In-App-Hilfe statt des Markdown-Handbuchs liest, findet den Knopf nicht – Verbotsbegriffe je Gruppe (Tasks 2–7) und der DocViewer-Vitest (Task 8).
3. **„Blöcke" ist doppeldeutig** (gestempelte Einträge vs. Arbeitszeit-Blöcke; die #498-Exportspalte „Arbeitsblöcke" listet Einträge): Eine Lohnbuchhaltung liest „Arbeitsblöcke" neben „Nicht angerechnet (Min)" falsch – Task 1 (Spalte „Zeiteinträge") und die Verbotsbegriffe „erfassten Blöcke", „aller Blöcke des Tages", „vergessener Nachmittagsblock", „Fehlende Blöcke" (Tasks 5, 6, 8).
4. **Download-Spiegel driftet**: Die In-App-Download-Fassung (`frontend/public/help`) zeigt den alten Stand, obwohl `docs/handbuch` neu ist – `mirror`-Gruppe, in jedem Markdown-Task mitgeprüft.
5. **In-Page-Links ins Leere** nach den umbenannten Überschriften (Mitarbeiter-FAQ → 3.3, §6/§13 → Arbeitszeit-Blöcke) und der Altfehler `#6-benutzer-verwalten` – `links`-Gruppe (Task 0 legt sie an, Tasks 2, 4, 5, 7 machen sie grün).

## Dateistruktur

| Datei | Verantwortung | Task |
|---|---|---|
| `scripts/check-doc-sync.sh` (neu) | Prüfskript: Gate gegen den Code, Spiegel, Anker, Pflicht-/Verbotsbegriffe je Fläche | 0 (Gerüst), 2–7, 10–12 (Gruppen) |
| `backend/app/services/export_service.py`, `ods_export_service.py`, `backend/tests/test_497_498_export_day_rows.py` | #498-Spaltenname „Zeiteinträge" (bedingt) | 1 |
| `docs/handbuch/HANDBUCH-ADMIN.md` + Spiegel | Admin-Handbuch | 2, 3, 4 |
| `docs/handbuch/HANDBUCH-MITARBEITER.md` + Spiegel | Mitarbeiter-Handbuch | 5 |
| `docs/handbuch/CHEATSHEET-ADMIN.md`, `CHEATSHEET-MITARBEITER.md`, `SCHNELLSTART.md` + Spiegel | Kurzanleitungen, Schnellstart (Markdown) | 6 |
| `docs/BERECHNUNGEN.md`, `docs/GLOSSAR.md` | Rechenregeln, Begriffe | 7 |
| `frontend/src/components/DocViewer.tsx`, `frontend/src/constants/helpContent.tsx`, `frontend/src/pages/admin/Reports.tsx` | In-App-Handbuch, Kurzanleitungen, Schnellstart, Kontexthilfe, Export-Hinweis | 8 |
| `frontend/src/components/DocViewer.test.tsx` (neu) | Vitest der In-App-Flächen | 8 |
| `backend/create_handbuch_testdata.py`, `e2e/capture-handbook-screenshots.ts`, `tools/handbook/handbuch-screenshots.js`, `docs/handbuch/HANDBUCH-ERSTELLEN.md`, `docs/handbuch/screenshots/16-admin-benutzer-formular.png`, `17-admin-benutzer-bearbeiten.png` | Demo-Person mit Blöcken, Screenshots 16/17 | 9 |
| `docs/BACKEND-ARCHITEKTUR.md`, `docs/ARC42.md`, `README.md`, `docs/specs/dsgvo/verarbeitungsverzeichnis.md`, `docs/UPDATE.md` | Technik-Doku | 10 |
| `CLAUDE.md` | Projektregeln | 11 |
| `CHANGELOG.md` | Entwurf 1.20.0 | 12 |
| `scripts/local-ci.sh` | Doku-Abgleich als Schritt 0 | 13 |
| pzweb `frontend/src/pages/marketing/anleitung/HandbuchAdmin.tsx`, `HandbuchMitarbeiter.tsx`, `AnleitungBerechnungen.tsx`, `HandbuchAdmin.test.tsx`, `HandbuchMitarbeiter.test.tsx`, `AnleitungBerechnungen.test.tsx` (neu) | Web-Anleitungen | 14, 15 |

**Außerhalb von PR4 (nicht anfassen):** jede Logik, jedes Schema und jeder Oberflächentext aus PR1–PR3 (Ausnahme: der #498-Spaltenkopf in Task 1 und die Exportliste in `Reports.tsx` in Task 8, beides reine Beschriftung); E2E-Specs (`user-management.spec.ts` u. a. gehören zu PR3, Spec 17.8); die App-Version (`CLAUDE.md` „Aktuelle Version", `package.json`, Backend-Version) – die setzt der Release (`/buildrelease`).

---

### Task 0: Gate und Prüfskript

**Files:**
- Create: `scripts/check-doc-sync.sh`

**Interfaces:**
- Consumes: den gemergten Stand von PR1–PR3 (u. a. `work_window_service.reclamp_time_entries`, `work_blocks_service.derive_targets`, Endpunkt `POST /admin/time-entries/{id}/credit-override`, Oberflächentexte aus Spec 12–14).
- Produces:
  - Aufruf `bash scripts/check-doc-sync.sh <gruppe> [<gruppe>…]` bzw. `… all`; Exit 0/1/2.
  - Hilfsfunktionen im Skript: `need DATEI TEXT`, `forbid DATEI TEXT`, `need_code TEXT [VARIANTE…]`.
  - Gruppen `group_code`, `group_mirror`, `group_links`; weitere Gruppen werden als Funktion `group_<name>` **oberhalb** der Markerzeile `# --- weitere Gruppen werden oberhalb dieser Zeile eingefügt ---` eingefügt (Tasks 2–7, 10–12).
  - Datei `.git/pr4-base` mit dem Namen des Integrationszweigs (Task 13 liest sie).

- [ ] **Step 1: Prüfen, dass PR1–PR3 gemergt sind, und Zweig anlegen**

```bash
cd /home/manuel/claude/praxiszeit
git status --short
grep -qF -e "def reclamp_time_entries" backend/app/services/work_window_service.py \
  && grep -qF -e "def derive_targets" backend/app/services/work_blocks_service.py \
  && grep -qF -e "credit-override" backend/app/routers/admin_time_entries.py \
  && grep -qF -e "def not_credited_minutes" backend/app/services/work_window_service.py \
  && echo "PR1-3 da"
```

Expected: `git status --short` ohne geänderte Dateien (nur ggf. untracked Pläne), danach `PR1-3 da`. Fehlt die Zeile `PR1-3 da`: **STOP** – PR4 darf erst nach PR3 laufen (Spec 20); an den Auftraggeber melden.

```bash
git branch --show-current > .git/pr4-base
cat .git/pr4-base
git switch -c docs/bloecke-pr4
```

Expected: der Name des Integrationszweigs, danach `Switched to a new branch 'docs/bloecke-pr4'`.

- [ ] **Step 2: Prüfskript schreiben**

Datei `scripts/check-doc-sync.sh` mit genau diesem Inhalt anlegen:

````bash
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
# und würden das Gate sonst ab Task 8 immer erfüllen).
need_code() {
  local v
  for v in "$@"; do
    if grep -rqF --exclude='*.test.ts' --exclude='*.test.tsx' \
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
  need_code "genehmigen und anerkennen"
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
  # Meldung für noch geöffnete alte Browser-Tabs (Release-Notes, Spec 11.4)
  need_code "Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) wurden durch Arbeitszeit-Blöcke ersetzt."
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
````

```bash
chmod +x scripts/check-doc-sync.sh
```

- [ ] **Step 3: Gate laufen lassen**

Run: `bash scripts/check-doc-sync.sh code`
Expected: `OK: code`, Exit 0.

Für **jede** Zeile `NICHT IM CODE: <Text>` gilt dieses Verfahren (nicht überspringen):

1. Ein kurzes, zusammenhängendes Stück des Textes suchen, z. B. die ersten drei Wörter:
   `grep -rnF --exclude='*.test.ts' --exclude='*.test.tsx' --exclude='DocViewer.tsx' --exclude='helpContent.tsx' -e '<die ersten drei Wörter der gemeldeten Zeile>' frontend/src backend/app`
2. Steht der Text im Code nur durch einen Zeilenumbruch (JSX/Prettier) getrennt oder mit anderem Gedanken-/Anführungszeichen, die Zeile im Skript auf das längste zusammenhängende Stück kürzen bzw. die Code-Variante als weiteres Argument von `need_code` ergänzen. Der Doku-Text dieses Plans bleibt dann, wie er ist – außer bei einem anderen Gedankenstrich: dann in **allen** Tasks dieses Plans das Zitat auf das Zeichen des Codes umstellen.
3. Fehlt die Funktion oder lautet der Text inhaltlich anders (anderer Knopfname, andere Meldung, anderer Abschnittsname in den Einstellungen): **STOP**. Nicht die Doku still an einen abweichenden Code anpassen, sondern mit `Datei:Zeile` an den Auftraggeber melden – entweder ist PR2/PR3 nachzubessern oder die Abweichung ist eine Entscheidung, die in die Spec gehört. Erst nach der Antwort weiter.

Run danach erneut: `bash scripts/check-doc-sync.sh code` → `OK: code`.

- [ ] **Step 4: Spiegel und Anker prüfen (Ausgangslage)**

Run: `bash scripts/check-doc-sync.sh mirror links`
Expected: genau eine Zeile `LINK      docs/handbuch/HANDBUCH-ADMIN.md: #6-benutzer-verwalten hat kein Ziel` und Exit 1 (Altfehler aus §18.8, Task 4 behebt ihn). Keine `SPIEGEL`-Zeile – der Spiegel ist bei `3d46c2f` byte-identisch. Erscheinen weitere `LINK`-Zeilen, sie notieren: sie gehören zu der Datei, deren Task sie behebt (die `links`-Gruppe muss am Ende von Task 7 grün sein).

- [ ] **Step 5: Stand der #498-Spalte festhalten (entscheidet Task 1)**

Run: `grep -rnF -e '"Arbeitsblöcke"' backend/app/services/export_service.py backend/app/services/ods_export_service.py`
Expected: entweder Treffer (PR2 hat die Spalte nicht umbenannt → Task 1 ausführen) oder keine Ausgabe (→ Task 1 Step 1 bestätigt nur den neuen Namen).

- [ ] **Step 6: Commit**

```bash
git add scripts/check-doc-sync.sh
git commit -F - <<'EOF'
chore(doku): Prüfskript für den Doku-Abgleich der Arbeitszeit-Blöcke

scripts/check-doc-sync.sh prüft als Gate, dass jeder in der Doku zitierte
Wortlaut im Code von PR1–PR3 steht, dazu Byte-Gleichheit des Hilfe-Spiegels
und die In-Page-Anker der Handbücher. Je Doku-Fläche folgen eigene Gruppen
mit Pflicht- und Verbotsbegriffen (Spec 16).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 1: #498-Exportspalte „Zeiteinträge" (bedingt) ⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen

Spec 15.1 „Begriffe": Die #498-Spalte „Arbeitsblöcke" listet die **Zeiteinträge** des Tages, während „Arbeitsblöcke" seit diesem Feature die **Vertrags**-Blöcke meint; vor dem Release ist eine der beiden Bezeichnungen zu ändern. Die Spalte ist neu in 1.20.0 (es gab sie in keinem Release), eine Umbenennung bricht also keine Kundenauswertung.

**Files:**
- Modify: `backend/app/services/export_service.py` (Kopfzeilen bei `3d46c2f` Zeilen 563 und 1177, Docstring Zeile 514)
- Modify: `backend/app/services/ods_export_service.py` (Kopfzeilen bei `3d46c2f` Zeilen 227 und 622)
- Test: `backend/tests/test_497_498_export_day_rows.py` (Zusicherungen bei `3d46c2f` Zeilen 435 und 467) und jede weitere Testdatei, die `"Arbeitsblöcke"` als Spaltenkopf erwartet (z. B. PR2s `test_export_uncredited_column.py`)

**Interfaces:**
- Consumes: Kopfzeilen-Listen der Exporter aus #498 und PR2 (`[…, "Unterbrechung (Min)", "Arbeitsblöcke", "Nicht angerechnet (Min)"]`).
- Produces: Spaltenkopf 12 in XLSX-Monatsblatt, XLSX-Jahres-Mitarbeiterblatt und ODS (Monat, Jahr) lautet `"Zeiteinträge"`; alle Doku-Texte der Tasks 4, 7, 8, 12, 14 setzen das voraus.

- [ ] **Step 1: Prüfen, ob die Umbenennung nötig ist**

Run: `grep -rnF -e '"Arbeitsblöcke"' backend/app backend/tests`
Expected: Treffer in `export_service.py`, `ods_export_service.py` und Tests → weiter mit Step 2.
Keine Ausgabe → `grep -rnF -e '"Zeiteinträge"' backend/app/services/export_service.py backend/app/services/ods_export_service.py` muss die vier Kopfzeilen zeigen; dann ist der Task erledigt (kein Commit), weiter mit Task 2.

- [ ] **Step 2: Tests auf den neuen Namen umstellen (rot)**

```bash
grep -rlF -e '"Arbeitsblöcke"' backend/tests | xargs sed -i 's/"Arbeitsblöcke"/"Zeiteinträge"/g'
grep -rnF -e '"Zeiteinträge"' backend/tests
```

Expected: die geänderten Zusicherungen, mindestens `test_497_498_export_day_rows.py` mit `assert headers[10:…] == ["Unterbrechung (Min)", "Zeiteinträge", …]` und `assert header[10:12] == ["Unterbrechung (Min)", "Zeiteinträge"]`. Den Modul-Docstring der Datei (bei `3d46c2f` Zeile 22, `„Arbeitsblöcke"`) ebenfalls auf `„Zeiteinträge"` ändern.

- [ ] **Step 3: Tests laufen lassen – müssen scheitern**

Run (Repo-Wurzel): `rm -f backend/test.db backend/test.db-wal backend/test.db-shm` und dann
`docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_497_498_export_day_rows.py -q -p no:cacheprovider`
Expected: FAIL in `TestIssue498Xlsx::test_columns_are_appended_not_inserted` und `TestIssue498Ods` (`'Arbeitsblöcke' != 'Zeiteinträge'`).

- [ ] **Step 4: Spaltenköpfe umbenennen**

```bash
sed -i 's/"Arbeitsblöcke"/"Zeiteinträge"/g' backend/app/services/export_service.py backend/app/services/ods_export_service.py
sed -i 's/^    - Arbeitsblöcke         (#498, angehängt)$/    - Zeiteinträge          (#498, angehängt)/' backend/app/services/export_service.py
grep -rnF -e 'Arbeitsblöcke' backend/app/services/export_service.py backend/app/services/ods_export_service.py
```

Expected: keine Ausgabe der letzten Zeile mehr, außer dem Docstring von `day_work_blocks` („#498: Arbeitsbloecke eines Tages …", ASCII-Umschrift, bleibt – er beschreibt die Funktion, nicht die Spalte).

- [ ] **Step 5: Tests laufen lassen – grün**

Run: derselbe `docker run …` wie in Step 3, einmal mit `tests/test_497_498_export_day_rows.py`, danach mit jeder in Step 2 geänderten Datei (z. B. `tests/test_export_uncredited_column.py`).
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/export_service.py backend/app/services/ods_export_service.py backend/tests
git commit -F - <<'EOF'
fix(export): Spalte 12 heißt „Zeiteinträge" statt „Arbeitsblöcke" (#498, Spec 15.1)

„Arbeitsblöcke" meint seit 1.20.0 die vertraglich hinterlegten
Arbeitszeit-Blöcke; die #498-Spalte listet dagegen die gestempelten
Zeiteinträge des Tages. Neben der neuen Spalte „Nicht angerechnet (Min)"
wäre der alte Name missverständlich. Die Spalte ist neu in 1.20.0, keine
Kundenauswertung hängt an ihrem Namen.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 2: Admin-Handbuch – Abschnitt „Arbeitszeit-Blöcke", Anerkennen, Rechtshinweise

Ersetzt den #201-Abschnitt in §4 durch die Beschreibung der Blöcke (Spec 3, 4.1, 6.1–6.3, 13, 16.1 Pflichtinhalte, E76).

**Files:**
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md` (bei `3d46c2f`: Tabelle „Neuen Mitarbeiter anlegen" Zeilen 172 und 189–190, Abschnitt Zeilen 219–236, Links Zeilen 339 und 663)
- Modify: `frontend/public/help/HANDBUCH-ADMIN.md` (Spiegel)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `admin_bloecke`)

**Interfaces:**
- Consumes: Prüfskript aus Task 0 (`need`, `forbid`, Markerzeile).
- Produces: Anker `#arbeitszeit-bloecke` (Abschnitt „Arbeitszeit-Blöcke (Soll-Arbeitszeit je Wochentag)") und `#nicht-angerechnet-anerkennen` (Unterabschnitt „Nicht angerechnete Zeit erkennen und anerkennen") in HANDBUCH-ADMIN.md – Tasks 3, 4, 6 verlinken darauf. Gruppe `admin_bloecke`.

- [ ] **Step 1: Prüfgruppe ergänzen (Test zuerst)**

In `scripts/check-doc-sync.sh` unmittelbar **oberhalb** der Zeile `# --- weitere Gruppen werden oberhalb dieser Zeile eingefügt ---` einfügen:

```bash
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
  forbid "$f" 'Soll-Arbeitszeiten je Wochentag'
  forbid "$f" 'Soll-Arbeitszeit-Fenster, #201'
  forbid "$f" '#soll-arbeitszeiten-soll-arbeitszeit-fenster-201'
}
```

- [ ] **Step 2: Gruppe laufen lassen – muss scheitern**

Run: `bash scripts/check-doc-sync.sh admin_bloecke`
Expected: Exit 1, u. a. `FEHLT     docs/handbuch/HANDBUCH-ADMIN.md: <a id="arbeitszeit-bloecke"></a>` und `VERALTET  docs/handbuch/HANDBUCH-ADMIN.md: Soll-Arbeitszeiten je Wochentag`.

- [ ] **Step 3: Tabelle „Neuen Mitarbeiter anlegen" anpassen**

In `docs/handbuch/HANDBUCH-ADMIN.md` (Datei vorher lesen):

Die Zeile, die mit `| **Wochenstunden** | Vertraglich vereinbarte Wochenstunden (Standard: 40)` beginnt, endet mit `– der Eingabewert im Feld selbst spielt dann keine Rolle. |`. Dieses Ende ersetzen durch:

```markdown
– der Eingabewert im Feld selbst spielt dann keine Rolle. Im Modus **„Nach Arbeitsblöcken"** leitet das System Wochenstunden, Tagesstunden und Arbeitstage aus den Blöcken ab (→ [Arbeitszeit-Blöcke](#arbeitszeit-bloecke)). |
```

Die Zeile `| **Individuelle Tagesstunden** | Abweichende Stundenverteilung Mo–Fr statt einheitlich (nur bei aktiver Stundenzählung) |` ersetzen durch:

```markdown
| **Modus der Arbeitszeit** | **„Gleichmäßig"** (Wochenstunden + Arbeitstage pro Woche), **„Nach Tagen"** (abweichende Stunden je Wochentag Mo–Fr) oder **„Nach Arbeitsblöcken"** (Zeitblöcke je Wochentag, siehe unten). Tagesplan und Blöcke nur bei aktiver Stundenzählung. |
```

Die Zeile `| **Soll-Arbeitszeiten je Wochentag** | Optionaler Soll-Beginn / Soll-Ende pro Wochentag (Mo–Fr) – siehe eigener Abschnitt „Soll-Arbeitszeiten" unten. |` ersetzen durch:

```markdown
| **Arbeitszeit-Blöcke** | Im Modus **„Nach Arbeitsblöcken"**: je Wochentag (Mo–Fr) bis zu drei Blöcke „von–bis" plus **„Pause innerhalb der Blöcke"** – daraus folgen Tagessoll und Anrechnung, siehe [„Arbeitszeit-Blöcke"](#arbeitszeit-bloecke) unten. |
```

- [ ] **Step 4: #201-Abschnitt durch „Arbeitszeit-Blöcke" ersetzen**

Alles von der Zeile `### Soll-Arbeitszeiten (Soll-Arbeitszeit-Fenster, #201)` bis **ausschließlich** der Zeile `### Mitarbeiter bearbeiten` (also einschließlich des Kastens „> **Rechtlicher Hinweis:** Die Nicht-Anrechnung von Zeiten außerhalb des Soll-Fensters …" und der Leerzeile danach) mit dem Edit-Werkzeug ersetzen durch:

````markdown
<a id="arbeitszeit-bloecke"></a>
### Arbeitszeit-Blöcke (Soll-Arbeitszeit je Wochentag)

Seit Version 1.20.0 hinterlegen Sie die Soll-Arbeitszeit einer Person je Wochentag (Montag bis Freitag) als **bis zu drei Arbeitszeit-Blöcke**, z. B. Montag 08:00–12:00 und 15:00–18:00, und dazu eine **„Pause innerhalb der Blöcke"** in Minuten. Aus den Blöcken folgt zweierlei:

- **Das Tagessoll:** Tagessoll = Summe der Blockdauern − Pause innerhalb der Blöcke. Beispiel: 08:00–12:00 und 15:00–18:00 mit 30 Minuten Pause ergeben 7:00 h − 0:30 h = **6:30 h**. Wochenstunden, Tagesstunden und Arbeitstage pro Woche leitet PraxisZeit daraus ab; ein Wochentag ohne Block ist kein Arbeitstag (Tagessoll 0). Eine zweite Pflegestelle für das Soll gibt es nicht.
- **Die Anrechnung:** Gestempelte Zeit **vor dem ersten Block, nach dem letzten Block und zwischen den Blöcken** wird nicht angerechnet. An **jedem** Blockrand – auch an den inneren – gilt der Puffer aus den Einstellungen (Standard 15 Minuten, → [Abschnitt 13](#soll-arbeitszeit-fenster-puffer)).

Blöcke werden im 5-Minuten-Raster erfasst (z. B. 08:05), dürfen sich nicht überschneiden und nicht direkt aneinanderstoßen – zwei Blöcke 08:00–12:00 und 12:00–16:00 erfassen Sie als einen Block 08:00–16:00. Blöcke gibt es nur Montag bis Freitag und nicht über Mitternacht. Gepflegt werden sie ausschließlich mit Wirkungsdatum über **„Arbeitszeit anpassen…"** (→ [Mitarbeiter bearbeiten](#mitarbeiter-bearbeiten)); beim **Anlegen** wählen Sie im Formular den Modus **„Nach Arbeitsblöcken"**.

**Beispiel – durchgestempelt über die Mittagslücke:** Blöcke Mo 08:00–12:00 und 15:00–18:00, Pause 0, Puffer 15 Minuten. Wer von 08:00 bis 18:00 durchstempelt, bekommt **08:00–12:15 und 14:45–18:00 = 7:30 h** angerechnet. Die Lücke zwischen den Blöcken schrumpft um den Puffer an beiden Rändern auf 12:15–14:45; diese **2:30 h werden nicht angerechnet**. Die gestempelten Zeiten 08:00 und 18:00 bleiben unverändert gespeichert (§ 16 ArbZG). Wer um 12:05 ausstempelt, verliert keine Minute – der Puffer deckt es. Eine Lücke, die nicht länger ist als der doppelte Puffer (z. B. 12:00–12:30 bei 15 Minuten Puffer), verschwindet ganz und wird voll angerechnet; eine geplante Pause erfassen Sie deshalb als „Pause innerhalb der Blöcke", nicht als kurze Lücke.

**Was wo gilt:**
- **Beginn und Ende außerhalb der Blöcke** werden wie bisher auf den ersten Block minus Puffer bzw. den letzten Block plus Puffer gekürzt; der gestempelte Wert bleibt als Rohstempel erhalten. Liegt ein Eintrag ganz vor dem ersten oder ganz nach dem letzten Block, werden 0 Stunden angerechnet.
- **Zeit in der Lücke** wird nicht verschoben, sondern als „nicht angerechnet" vom Eintrag abgezogen. Die gestempelten Zeiten bleiben stehen.
- **Kein Block, keine Kappung:** An Wochentagen ohne Block, an Wochenenden, gesetzlichen Feiertagen und an Sondertagen (24./31.12.), die als **„frei"** eingestellt sind, wird nichts gekappt – Arbeit dort (z. B. ein Notdienst am Ostermontag) wird voll angerechnet. Ein Sondertag als **„halber Feiertag"** behält die Blöcke seines Wochentags.
- **Ausgenommen** sind Mitarbeitende ohne Stundenzählung und Einträge, die die Verwaltung **anerkannt** hat (siehe unten). Bei **§ 18-befreiten** Mitarbeitenden (ArbZG-Prüfungen ausgesetzt) wird trotzdem gekappt – die Kappung ist eine Anrechnungsregel, keine ArbZG-Prüfung.
- **Vergessen auszustempeln:** Schließt PraxisZeit einen offenen Eintrag eines vergangenen Tages automatisch (um 23:59), wird er jetzt ebenfalls gekappt – angerechnet wird bis zum Ende des letzten Blocks plus Puffer, nicht mehr der ganze Abend. Ein solcher Eintrag ist als „automatisch geschlossen" gekennzeichnet; 23:59 gilt nicht als echter Stempel.
- Die Kappung greift an **allen** Wegen: Ein- und Ausstempeln, eigene Einträge, Korrekturen der Verwaltung, genehmigte Änderungsanträge, XLS-Import.

**Was beim Speichern erscheint** (Hinweise blockieren nie, der Eintrag wird gespeichert):
- Beginn oder Ende gekürzt (wie bisher): *„Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt (Beginn 07:37 → 07:45; Puffer 15 Minuten)."* Kommt eine Lücke dazu, folgt *„Zusätzlich werden zwischen den Arbeitsblöcken (12:15–14:45) 2:30 h nicht angerechnet."*
- nur Lücke: *„Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."*
- Eintrag ganz in der Lücke: *„Die eingetragene Zeit (12:30–14:30) liegt vollständig zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet werden 0 Stunden. Die gestempelte Zeit bleibt gespeichert."*
- Einstempeln in der Lücke: *„Eingestempelt zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet wird erst ab 14:45."*

Mitarbeitende lesen an den Lückenhinweisen zusätzlich *„Haben Sie in dieser Zeit gearbeitet, beantragen Sie die Anrechnung (Zeiterfassung → Eintrag → „Anrechnung beantragen“)."* Bei einem Blockbeginn zur vollen Stunde landet eine zu frühe Eingabe auf `hh:45` – das ist die Grenze aus Block und Puffer, keine Rundung; Eingaben sind immer minutengenau möglich.

**Pausen und Lücke:** Bleiben von der Lücke nach Abzug des Puffers an beiden Rändern mindestens 15 Minuten, zählen sie für die Pausenpflicht (§ 4 ArbZG) als Pause – die Lücke ist eine im Voraus feststehende Ruhepause. Wird zusätzlich eine Pause eingetragen, obwohl über die Lücke durchgestempelt wurde, wird beides abgezogen; dann erscheint *„Pause in der Lücke wird zusätzlich abgezogen: 30 Min Pause und 2:30 h nicht angerechnet zwischen den Arbeitsblöcken. Lag die Pause in der Lücke, bitte die Pause auf 0 setzen."* Hinweise zur tatsächlichen Anwesenheit laut Stempel stehen in [Abschnitt 14](#automatische-warnungen-im-alltag).

**Bisherige Arbeitszeit-Fenster:** Das Update auf 1.20.0 übernimmt jedes bisher hinterlegte Soll-Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) als einen Block je Tag. Diese Fenster kappen weiter genau wie vorher, ändern das Soll aber nicht. Im Dialog erscheinen sie als **„Arbeitszeit-Fenster (Altbestand, nur Kappung)"** mit den Aktionen **„In Arbeitszeit-Blöcke umwandeln"** (öffnet den Block-Modus vorbefüllt; die Pause geben Sie an, danach folgt das Soll aus den Blöcken) und **„Fenster entfernen"**. Eine Änderung im Modus „Gleichmäßig" oder „Nach Tagen" übernimmt ein Altfenster, solange Sie es nicht entfernen.

<a id="nicht-angerechnet-anerkennen"></a>
#### Nicht angerechnete Zeit erkennen und anerkennen

Nicht angerechnete Zeit ist nie still. Unter der Uhrzeit eines Eintrags steht im **Admin-Dashboard** (Detailansicht), im **Monatsjournal** und in der **Zeiterfassung** eine Zusatzzeile:

| Lage | Zusatzzeile |
|------|-------------|
| nur Beginn oder Ende gekürzt | *„gestempelt 07:30 · angerechnet ab 07:45"* (bzw. „… angerechnet bis …") |
| durchgestempelt über die Lücke | *„gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet"* |
| zusätzlich Beginn/Ende gekürzt | *„gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken"* |
| mit eingetragener Pause | „angerechnet 7:00 h" erhält den Zusatz *„nach 0:30 h Pause"* |
| automatisch geschlossen | *„eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 7:45 h (08:00–18:15) · 2:30 h zwischen den Blöcken nicht angerechnet"*; ohne Blöcke *„… automatisch geschlossen um 23:59"* |
| anerkannt | Kennzeichen *„anerkannt"*, keine Zusatzzeile |

„Angerechnet" ist immer die Zeit, die ins Ist und in den Saldo eingeht (nach Pause und Lücke). „Nicht angerechnet" ist die Lücke **plus** die vor dem ersten bzw. nach dem letzten Block abgeschnittene Zeit. Das **Monatsjournal** zeigt die Monatssumme als Zeile *„Anwesenheit nicht angerechnet: 7:30 h"* (nur wenn etwas anfällt); die Datei-Exporte führen sie in der letzten Spalte **„Nicht angerechnet (Min)"** (→ [Abschnitt 6](#6-berichte-und-exporte)).

**Anerkennen:** Wurde vor, nach oder zwischen den Blöcken tatsächlich gearbeitet, klicken Sie am Eintrag (Admin-Dashboard, Detailansicht, oder Monatsjournal) auf **„Anerkennen"**. Die Bestätigung lautet: *„Die gesamte gestempelte Zeit (08:00–18:00) wird angerechnet. Sie bleibt angerechnet — auch bei späteren Neuberechnungen und wenn die Verwaltung die Zeiten ändert; Mitarbeitende können den Eintrag danach nur noch per Änderungsantrag ändern. Wurde nur ein Teil der Zeit gearbeitet, den Eintrag besser aufteilen oder korrigieren. Der Vorgang wird protokolliert."* Ein anerkannter Eintrag wird nie wieder gekappt, auch nicht bei späteren Arbeitszeit-Änderungen; ändern Sie seine Zeiten (Bearbeiten, Antrag, XLS-Import), werden auch die neuen Zeiten ungekappt angerechnet. Eine Rücknahme der Anerkennung gibt es nicht. Ein offener Eintrag lässt sich erst nach dem Ausstempeln anerkennen, ein **automatisch geschlossener** erst, wenn das tatsächliche Ende eingetragen ist (*„Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen."*). Anerkennen blockiert nie an § 3 oder § 4 ArbZG; Verstöße erscheinen als Hinweis. Im Änderungsprotokoll steht der Vorgang als **„Anrechnung anerkannt"**.

**Anrechnung beantragen:** Mitarbeitende können an einem eigenen Eintrag mit nicht angerechneter Zeit über **„Anrechnung beantragen"** einen Änderungsantrag mit Begründung stellen. In der Antragsprüfung (→ [Abschnitt 8](#8-korrekturanträge-prüfen)) bedeutet „Genehmigen" dann „Anerkennen".

> **Vergütung:** Nichtanrechnung ersetzt keine Vergütungsentscheidung. Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde oder zur Erledigung der Arbeit notwendig war, ist zu vergüten (§ 611a Abs. 2, § 612 Abs. 1 BGB; MiLoG). Wurde vor, nach oder zwischen den Blöcken gearbeitet, nutzen Sie „Anerkennen"; wurde nur ein Teil gearbeitet, den Eintrag aufteilen oder korrigieren statt die ganze Zeit anzuerkennen.

> **Jugendliche:** Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG: 30 Min Pause ab 4,5 h, 60 Min ab 6 h, höchstens 4,5 h ohne Pause, Schichtzeit inklusive Lücke höchstens 10 h); PraxisZeit prüft diese nicht.

**Bekannte Grenze:** Arbeit in der Lücke bleibt in der angerechneten Zeit unsichtbar, bis sie anerkannt wird. Die Nachtarbeits-Erkennung (§ 6 ArbZG) rechnet weiter mit den gespeicherten (gekappten) Zeiten; eine Erkennung auf den Rohstempeln folgt separat. Rohstempel stehen weiterhin nicht in den Exportdateien.

> **Rechtlicher Hinweis:** Die Nichtanrechnung von Zeit vor, nach und zwischen den Blöcken ist eine **Anrechnungsregel des Betriebs**, keine gesetzliche Vorgabe. Der erhaltene Rohstempel dokumentiert gemäß § 16 ArbZG die tatsächliche Anwesenheit.

````

- [ ] **Step 5: Die zwei Links auf den alten Anker umstellen**

```bash
sed -i 's/(#soll-arbeitszeiten-soll-arbeitszeit-fenster-201)/(#arbeitszeit-bloecke)/g' docs/handbuch/HANDBUCH-ADMIN.md
grep -nF -e '#soll-arbeitszeiten-soll-arbeitszeit-fenster-201' docs/handbuch/HANDBUCH-ADMIN.md
```

Expected: keine Ausgabe der zweiten Zeile (bei `3d46c2f` betraf es §6 „Netto (Std)" und §13 „Soll-Arbeitszeit-Fenster (Puffer)"; den Wortlaut dieser Absätze passt Task 4 an).

- [ ] **Step 6: Spiegel aktualisieren und prüfen**

```bash
cp docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
bash scripts/check-doc-sync.sh admin_bloecke mirror
```

Expected: `OK: admin_bloecke mirror`.

- [ ] **Step 7: Commit**

```bash
git add scripts/check-doc-sync.sh docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
git commit -F - <<'EOF'
docs(handbuch): Admin-Handbuch beschreibt Arbeitszeit-Blöcke statt #201-Fenster

Neuer Abschnitt „Arbeitszeit-Blöcke": Tagessoll aus Blöcken minus Pause,
Puffer an jedem Blockrand (Beispiel 08–18 → 7:30 h), Meldungstexte,
Altfenster aus 1.19.x, Zusatzzeilen „nicht angerechnet", Anerkennen,
Anrechnung beantragen, Vergütungs- und JArbSchG-Hinweis, bekannte Grenze
(Spec 16.1).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Admin-Handbuch – Arbeitszeit ändern, Rückwirkung, Schutzpaket, Mitbestimmung

Schreibt den Unterabschnitt „Mitarbeiter bearbeiten" für den Dialog „Arbeitszeit & Wochenstunden" neu (Spec 9.1–9.7, 10, 12.1, 14, 16.1, 19.1 Nr. 1–7).

**Files:**
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md` (bei `3d46c2f` Zeilen 243–272: vom Absatz `**Stundenänderungen:**` bis vor `**Mitarbeiter deaktivieren:**`)
- Modify: `frontend/public/help/HANDBUCH-ADMIN.md` (Spiegel)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `admin_aendern`)

**Interfaces:**
- Consumes: Anker `#arbeitszeit-bloecke`, `#nicht-angerechnet-anerkennen` (Task 2); Prüfskript (Task 0).
- Produces: Unterüberschriften „Auswirkung prüfen", „Rückwirkende Änderungen: Neuberechnung", „Verlängerung und Verkürzung", „Änderung löschen", „Wer davon erfährt" unter „Mitarbeiter bearbeiten" (Anker per GitHub-Slug, z. B. `#verlängerung-und-verkürzung`); Gruppe `admin_aendern`.

- [ ] **Step 1: Prüfgruppe ergänzen**

Oberhalb der Markerzeile in `scripts/check-doc-sync.sh` einfügen:

```bash
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
}
```

- [ ] **Step 2: Gruppe laufen lassen – muss scheitern**

Run: `bash scripts/check-doc-sync.sh admin_aendern`
Expected: Exit 1, u. a. `FEHLT     docs/handbuch/HANDBUCH-ADMIN.md: **Arbeitszeit ändern:**` und `VERALTET  docs/handbuch/HANDBUCH-ADMIN.md: Wochenstunden anpassen…`.

- [ ] **Step 3: Unterabschnitt neu schreiben**

In `docs/handbuch/HANDBUCH-ADMIN.md` unter `### Mitarbeiter bearbeiten` alles vom Absatz `**Stundenänderungen:**` bis **ausschließlich** zum Absatz `**Mitarbeiter deaktivieren:**` (Bildzeile, Überschrift und den Satz „Klicken Sie in der Benutzerliste auf den Namen des Mitarbeiters." davor stehen lassen) ersetzen durch:

````markdown
**Arbeitszeit ändern:**
Wochenstunden, Tagesstunden, der Modus, die Arbeitstage pro Woche und die Arbeitszeit-Blöcke werden im Bearbeiten-Formular nur **angezeigt** – für **alle** Mitarbeitenden. Oben steht die heute gültige Arbeitszeit, z. B. *„Arbeitszeit heute: Mo 08:00–12:00 + 15:00–18:00 · Di 08:00–12:00 …"* (ohne Blöcke: *„Keine Arbeitszeit-Blöcke hinterlegt"*). Daneben steht der Button **„Arbeitszeit anpassen…"**. Er öffnet denselben Dialog **„Arbeitszeit & Wochenstunden"** wie das Uhr-Symbol in der Benutzerliste.

So ändern Sie die Arbeitszeit (Teilzeitumstellung, neuer Tagesplan, neue Blöcke):

1. Name/Kürzel des Mitarbeiters öffnen
2. Button **„Arbeitszeit anpassen…"** klicken (alternativ: Uhr-Symbol in der Benutzerliste)
3. **„Gültig ab"**-Datum angeben (ab wann gilt die neue Regelung)
4. Modus wählen:
   - **„Gleichmäßig"** – Wochenstunden und Arbeitstage pro Woche
   - **„Nach Tagen"** – Stunden je Wochentag (Mo–Fr); Wochensumme und Arbeitstage errechnet der Dialog (Arbeitstage = Wochentage mit eingetragenen Stunden)
   - **„Nach Arbeitsblöcken"** – je Wochentag bis zu drei Zeilen „von–bis" (weitere Zeile über **„+ Block"**) und **„Pause innerhalb der Blöcke"** in Minuten. Der Dialog zeigt je Tag live *„Gesamtzeit 9:00 h · Pause 1:00 h · Tagessoll 8:00 h"* und darunter die Wochensumme. Tagessoll, Wochenstunden und Arbeitstage folgen aus den Blöcken (→ [Arbeitszeit-Blöcke](#arbeitszeit-bloecke)).
5. Die **Auswirkung** unter dem Formular prüfen (siehe unten) und, wenn verlangt, bestätigen
6. Speichern

Nach dem Speichern meldet PraxisZeit z. B. *„Gespeichert. 3 Zeiteinträge neu berechnet, 1 übersprungen, 1 Abwesenheit angepasst."*

**Hinweise im Dialog** (blockieren nicht): Reichen die geplanten Pausen eines Tages für § 4 ArbZG nicht, ist eine Lücke so kurz, dass sie im Puffer verschwindet (*„Mo: Die Lücke 12:00–12:30 ist nicht länger als der doppelte Puffer (15 Min) und wird vollständig angerechnet. Eine geplante Pause bitte als „Pause innerhalb der Blöcke" erfassen."*), oder liegt das Tagessoll über 10 bzw. 8 Stunden oder das Wochensoll über 48 Stunden, weist der Dialog darauf hin. Ein Tagessoll über 10 Stunden ist ein geplanter Verstoß gegen § 3 ArbZG – eine Erfassung nach diesem Plan lehnt die Zeiterfassung ab. Wechseln Sie von Blöcken zu „Gleichmäßig" oder „Nach Tagen", nennt der Dialog vor dem Speichern: *„Die Arbeitszeit-Blöcke enden mit dieser Änderung; ab ‹Datum› wird nicht mehr gekappt."* Für Mitarbeitende **ohne Stundenzählung** bietet der Dialog den Block-Modus nicht an; gespeicherte Blöcke stehen dort als *„Arbeitszeit-Blöcke gespeichert, ohne Wirkung (keine Stundenzählung)"* und enden mit der nächsten Arbeitszeit-Änderung.

**Verlauf:** Der Dialog zeigt jeden Eintrag als **„ab … bis …"**; die vorherige Regelung endet am Vortag des neuen Gültigkeitsdatums, der aktuellste Eintrag läuft „bis heute" – z. B. „ab 01.03.2026 bis heute: Mo 08:00–12:00 + 15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 = 15,0 h/Woche" oder bei Tagesplan „ab 01.03.2026 bis heute: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 Std/Woche · 3 Tage/Woche".

##### Auswirkung prüfen

Unter dem Formular zeigt der Kasten **„Auswirkung (Puffer 15 Min)"** vor dem Speichern:
- den **Wirkungsbereich** – vom Gültig-ab-Datum bis zum Tag vor der nächsten Änderung; gibt es keine spätere Änderung, bis zum letzten erfassten Eintrag bzw. zur letzten gebuchten Abwesenheit, mindestens bis heute – und die geänderten Wochentage,
- die **Zeiteinträge**, die neu berechnet werden, je Monat mit angerechneter Zeit vorher → nachher, und jeden übersprungenen Eintrag mit Grund,
- die **Abwesenheiten**, deren Stunden auf das neue Tagessoll umgestellt werden,
- getrennt die Veränderung des **Solls** im Zeitraum, der **angerechneten Zeit** und des **Überstundenkontos** (bisher, neu, Differenz); unter „Einzelheiten" zusätzlich Urlaub vorher/nachher und geänderte ArbZG-Befunde.

Sobald Zeiteinträge oder Abwesenheiten betroffen sind, ist der Haken **„Ich habe die Auswirkungen geprüft und möchte speichern"** Pflicht – auch bei Wirkungsdatum heute. Berührt der Zeitraum ein bereits **abgeschlossenes Jahr**, weist der Dialog darauf hin; der eingefrorene Jahresabschluss wird nicht automatisch neu berechnet, den Übertrag prüfen Sie von Hand (→ [Jahresabschluss](#jahresabschluss)).

##### Rückwirkende Änderungen: Neuberechnung

Liegt das Gültig-ab-Datum in der Vergangenheit, rechnet PraxisZeit die bereits erfassten Zeiteinträge im Wirkungsbereich neu:
- **Nur geänderte Wochentage:** Neu gekappt werden Einträge an Wochentagen, deren Blöcke sich geändert haben. Eine reine Pausenänderung kappt nichts neu – sie ändert nur das Tagessoll.
- **Grundlage ist der Stempel:** Neu gekappt wird immer vom ursprünglich gestempelten Wert aus, nie von einer schon gekappten Zeit. Eine Verlängerung gibt so vorher abgeschnittene Zeit wieder frei. Einträge, deren Rohstempel aus der Zeit vor Version 1.19.1 nicht mehr vorhanden ist, nennt die Auswirkung als „nicht erweiterbar" – sie bleiben, wie sie sind.
- **Aktueller Puffer:** Die Neuberechnung nimmt den heute eingestellten Puffer (die Auswirkung nennt ihn) und merkt ihn sich an jedem geprüften Eintrag.
- **Übersprungen und einzeln genannt:** der offene Eintrag von heute, Sonn- und Feiertage sowie „freie" Sondertage, Mitarbeitende ohne Stundenzählung, Tage außerhalb des Beschäftigungszeitraums, anerkannte Einträge und Einträge, die nach der Kappung mit einem anderen Eintrag desselben Tages kollidieren würden. Offene Einträge **vergangener** Tage (vergessenes Ausstempeln) schließt PraxisZeit vorher automatisch und rechnet sie danach regulär neu.
- **Danach die Abwesenheiten:** Erst nach den Zeiteinträgen werden die Stunden bereits gebuchter Abwesenheiten im Wirkungsbereich auf das neue Tagessoll umgestellt (ein Halbtag zur Hälfte) – bei rückwirkendem **und** bei zukunftsdatiertem Wirkungsdatum, denn Urlaub, Betriebsferien und Fortbildungen sind oft im Voraus gebucht. Ausgenommen sind Überstundenausgleich und Mitarbeitende ohne Stundenzählung; die **Urlaubstage selbst ändern sich nie** (Tagesprinzip). An einem Tag mit Abwesenheit **und** Arbeit (z. B. halber Tag krank, halber Tag gearbeitet) wird die Gutschrift so angeglichen, dass Arbeit und Gutschrift zusammen das Tagessoll nicht überschreiten.

##### Verlängerung und Verkürzung

**Verlängerung** heißt: Weder die angerechnete Zeit eines Eintrags noch das Überstundenkonto sinken (z. B. längere Blöcke bei gleichem Tagessoll, oder ein niedrigeres Soll). Dann genügt der Bestätigungshaken.

**Verkürzung** liegt vor, sobald mindestens eines zutrifft:
1. ein erfasster Eintrag verliert angerechnete Zeit;
2. das Überstundenkonto sinkt im Wirkungsbereich – auch durch ein rückwirkend **höheres** Soll (längere Blöcke, kleinere Pause, mehr Wochenstunden) oder durch ein höheres Soll für den heutigen Tag, während die Person eingestempelt ist;
3. eine Abwesenheits-Gutschrift an einem Tag mit Arbeit und Abwesenheit sinkt stärker als das Tagessoll des Tages.

Das gilt für jede Änderung in diesem Dialog – auch für eine reine Wochenstunden- oder Tagesplan-Änderung ohne Blöcke –, beim Anlegen wie beim Löschen. Der Dialog zeigt dann einen Kasten **„⚠ Verkürzung"** mit den zutreffenden Gründen (z. B. „3 Einträge verlieren angerechnete Zeit (zusammen 2:15 h)" oder „Das Überstundenkonto sinkt im Wirkungsbereich um 3:45 h (höheres Soll), obwohl kein Eintrag angerechnete Zeit verliert") und zwei Möglichkeiten:

- **„Ab heute (TT.MM.JJJJ) wirksam – vergangene Einträge bleiben unverändert"** (Standard). Die Änderung gilt ab dem frühesten Datum, ab dem nichts verloren geht – meist heute; morgen, wenn heute schon ein Eintrag verliert, der heutige Tag bereits Saldo oder Gutschrift verliert oder das Soll von heute steigt, während die Person eingestempelt ist. Vergangene Einträge werden nicht neu berechnet, und auch spätere Bearbeitungen alter Einträge rechnen mit der damals gültigen Arbeitszeit. Dafür ist kein Grund nötig.
- **„Rückwirkend ab ‹Datum› mit Neuberechnung"** – nur mit **Grund**, **Begründung** (10 bis 400 Zeichen) und **Bestätigung**:
  - Grund **„Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)"**, **„Mit der beschäftigten Person vereinbart"** oder **„Sonstiges"**. Unter der Auswahl steht immer: *„Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit."* Das heißt: Falsch gestempelte Zeiten korrigieren Sie am Zeiteintrag selbst (Bearbeiten im Admin-Dashboard oder im Monatsjournal), Mitarbeitende per Änderungsantrag. Eine rückwirkende Arbeitszeit-Änderung berichtigt nur eine falsch **hinterlegte** Arbeitszeit.
  - Bestätigung je Grund: *„Ich habe geprüft, dass die hinterlegte Arbeitszeit falsch war (Fehlerkorrektur)."* bzw. *„Ich habe geprüft, dass die rückwirkende Änderung mit der beschäftigten Person vereinbart ist."* bzw. *„Ich habe die Gründe geprüft."* Jeder Text endet mit *„Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist unabhängig von der Anrechnung zu vergüten (§ 611a, § 612 BGB). Auf den Mindestlohn für geleistete Stunden kann nicht verzichtet werden (§ 3 MiLoG)."*
  - Bei **„Sonstiges"** zusätzlich die rote Warnung *„Eine einseitige rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO wirkt nur für die Zukunft); geleistete Arbeit bleibt zu vergüten."* und ein zweiter Haken *„Mir ist bewusst, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht nicht gedeckt ist."*
  - Bei jeder rückwirkenden Verkürzung der Hinweis *„Bei Minijob oder Vergütung in Mindestlohnhöhe kann die Kürzung Mindestlohnansprüche (§§ 1, 3 MiLoG) und die Aufzeichnung nach § 17 MiLoG berühren."* – bei Personen mit Minijob-Arbeitszeitkonto oder vereinbarter Monatsarbeitszeit zusätzlich ein Hinweis zum Kontostand und zur 12-Monats-Ausgleichsfrist.
  - Im Änderungsprotokoll steht der Grund als Kürzel **„[Erfassungsfehler korrigiert]"**, **„[Einvernehmlich vereinbart]"** bzw. **„[Sonstiges]"**, gefolgt von Ihrer Begründung.
- In ein **abgeschlossenes Jahr** hinein ist eine rückwirkende Verkürzung **gesperrt**: *„Rückwirkende Verkürzung in das abgeschlossene Jahr 2025 ist gesperrt. Bitte die Änderung frühestens ab 01.01.2026 wirksam werden lassen."*
- Liegt die Änderung vollständig vor einer späteren Änderung, entfällt der Standard: *„Die Änderung liegt vollständig vor der Änderung ab ‹Datum›; nur rückwirkend mit Begründung oder abbrechen."*

> ⚠️ **Neu in 1.20.0:** Auch eine rückwirkende **Erhöhung** der Wochenstunden oder des Tagesplans braucht jetzt Grund und Bestätigung, wenn das Überstundenkonto dadurch sinkt – bisher genügte der Bestätigungshaken. „Ab heute" bleibt ohne Grund möglich.

##### Änderung löschen

**„Löschen"** steht nur an der jüngsten Zeile des Verlaufs; die **früheste** Änderung lässt sich nicht löschen, solange spätere bestehen – sie hält die davor gültige Regelung fest. Das Löschen rechnet Zeiteinträge und Abwesenheiten symmetrisch zurück und zeigt vorher dieselbe Auswirkung. Verkürzt das Löschen, gelten dieselben Regeln wie beim Anlegen:
- **„Ab ‹Datum› auf den vorherigen Stand zurücksetzen"** (Standard): Statt zu löschen entsteht eine neue Verlaufszeile mit dem vorherigen Stand – *„Die Änderung ab ‹Gültig ab› bleibt bis ‹Vortag› wirksam und im Verlauf stehen; ab ‹Datum› gilt wieder der vorherige Stand."*
- **„Rückwirkend löschen mit Neuberechnung"** – nur mit Grund, Begründung und Bestätigung wie oben; in ein abgeschlossenes Jahr gesperrt.

Hat sich der Verlauf inzwischen geändert, meldet der Dialog *„Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."*

##### Wer davon erfährt

- **Mitarbeitende:** Nach **jeder** Arbeitszeit-Änderung, die sie betrifft – auch „ab heute", zukunftsdatiert, gelöscht oder zurückgesetzt –, steht 30 Tage lang ein Hinweis auf ihrem Dashboard, z. B. *„Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00). 3 Einträge neu berechnet, angerechnete Zeit −2:15 h."* Bei einer rückwirkenden Verkürzung steht der Grundtyp dabei, nie Ihre Begründung. Unter **Profil → „Meine Arbeitszeit"** sehen sie die heute gültigen Blöcke und den Verlauf.
- **Änderungsprotokoll:** je neu berechnetem Eintrag eine Zeile **„Neukappung (Arbeitszeit-Änderung)"** mit alten und neuen Zeiten; je Änderung und je Löschung eine Sammelzeile mit Wirkungsdatum, Anzahl, Differenz der angerechneten Zeit, Saldo-Differenz, Puffer, Grund und Vertrag alt → neu – auch ohne betroffene Einträge; je nachgezogener Abwesenheit eine Zeile mit altem und neuem Stundenwert (z. B. „Krank 8,0 h" → „Krank 4,0 h — Arbeitszeit-Änderung ab 15.03.2026"). Der beim Buchen erfasste Stundenwert bleibt daneben intern unverändert gespeichert – eine Rückversicherung, falls sich eine Berechnung nachträglich als falsch herausstellt.
- **Berichte:** Monats- und Jahresbericht zeigen als Wochenstunden den **zu Zeitraumsbeginn** gültigen Wert und daneben die Änderung, z. B. „ab 15.03.2026: 20,0 Std/Woche", bei Tagesplan „ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche", bei Blöcken „ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche" (ein Altfenster mit dem Zusatz „(nur Kappung)", entfernte Blöcke mit „· ohne Arbeitszeit-Blöcke"). Das gilt für das Admin-Dashboard und die Excel-, ODS- und PDF-Exporte (Jahresübersicht: Spalte **Stundenänderungen**).

> ⚠️ **Fallstrick – die Wochenstundenzahl allein verrät nicht jede Änderung.** Ändern Sie im Modus „Gleichmäßig" nur die Arbeitstage pro Woche bei gleichbleibenden Wochenstunden (z. B. 40 h auf 5 Tage → 40 h auf 4 Tage), nennt der Verlauf bzw. Bericht die neue Arbeitstage-Zahl zwar zusätzlich (z. B. „ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage") – die **Wochenstundenzahl selbst bleibt unverändert**, das **Tagessoll** verschiebt sich aber still (8 h/Tag → 10 h/Tag). Verschieben Sie im Modus „Nach Tagen" oder „Nach Arbeitsblöcken" Stunden von einem Wochentag auf einen anderen, ohne die Wochensumme zu ändern, bleibt das Tagessoll der übrigen Tage gleich – dafür ändert sich der **Urlaubsverbrauch**: War am wegfallenden Wochentag bereits ein Urlaubstag gebucht, zählt er rückwirkend nicht mehr, weil dort kein Tagessoll mehr anfällt. Prüfen Sie deshalb immer die Auswirkung, nicht nur die Wochenstundenzahl.

> **Arbeitsrecht und Mitbestimmung:** Ändert sich durch die Blöcke der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und braucht das Einverständnis der beschäftigten Person (sonst Änderungskündigung, § 2 KSchG; bei Teilzeit §§ 8, 9 TzBfG). Die Lage kann, soweit der Vertrag sie nicht festlegt, im Rahmen des Direktionsrechts (§ 106 GewO) nach billigem Ermessen und mit angemessener Ankündigung nur für die Zukunft geändert werden (Arbeit auf Abruf: mindestens 4 Tage vorher, § 12 Abs. 3 TzBfG). Vereinbarte Arbeitszeiten und Ruhepausen sind wesentliche Vertragsbedingungen (§ 2 Abs. 1 Satz 2 Nr. 7 NachwG); eine Änderung ist spätestens am Tag des Wirksamwerdens schriftlich mitzuteilen (§ 3 NachwG). Mit Betriebsrat sind Lage, Verteilung und Pausen (§ 87 Abs. 1 Nr. 2 BetrVG), vorübergehende Änderungen der betriebsüblichen Arbeitszeit (Nr. 3) und die Kappung als technische Einrichtung (Nr. 6) mitbestimmungspflichtig; ohne Zustimmung ist die Maßnahme gegenüber den Beschäftigten unwirksam. PraxisZeit prüft das nicht.
>
> Der Dialog zeigt dazu eine Kurzfassung unter dem Editor.

````

- [ ] **Step 4: Zweite Fundstelle des alten Knopfnamens (§13 Minijob)**

In §13 unter `### Minijob / Arbeitszeitkonto (§ 2 Abs. 2 MiLoG) (#377)`, Punkt `- **Individuelle Tagesstunden werden zur geplanten Anwesenheit:**`: `ausschließlich über den Dialog „Wochenstunden anpassen…" (Modus „Nach Tagen")` → `ausschließlich über „Arbeitszeit anpassen…" (Modus „Nach Tagen")`.

Run: `grep -nF -e 'Wochenstunden anpassen' docs/handbuch/HANDBUCH-ADMIN.md`
Expected: keine Ausgabe.

- [ ] **Step 5: Spiegel aktualisieren und prüfen**

```bash
cp docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
bash scripts/check-doc-sync.sh admin_aendern admin_bloecke mirror
```

Expected: `OK: admin_aendern admin_bloecke mirror`.

- [ ] **Step 6: Commit**

```bash
git add scripts/check-doc-sync.sh docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
git commit -F - <<'EOF'
docs(handbuch): Arbeitszeit ändern – Dialog, Neuberechnung, Schutzpaket, Löschen

„Mitarbeiter bearbeiten" beschreibt den Dialog „Arbeitszeit & Wochenstunden"
mit drei Modi, die Auswirkungs-Vorschau, die Neukappung vergangener Einträge,
Verlängerung vs. Verkürzung mit allen drei Kriterien, das Schutzpaket je
Grundtyp, Löschen mit „auf den vorherigen Stand zurücksetzen", den
Mitarbeiter-Hinweis und den Kasten Arbeitsrecht/Mitbestimmung (Spec 16.1).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 4: Admin-Handbuch – übrige Abschnitte ⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen

Zieht §1-Kopf, §3, §6 (Exporte, #497/#498), §8, §9, §12, §13, §14 (#499), §17 und §18 nach (Spec 8.1–8.4, 10.3, 12.3, 13.2, 15.1, 15.2, 16.1, A.2) und behebt den Altfehler `#6-benutzer-verwalten`.

**Files:**
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md` (bei `3d46c2f`: Zeile 3; §3 Zeile 97; §6 Zeilen 334, 339, 341, 356; §8 Zeile 443; §9 Zeile 463; §12 Zeile 581; §13 Zeilen 661–663; §14 Zeilen 820–830; §17 Zeilen 877–900; §18 Zeilen 907, 935, 939–941, 1012)
- Modify: `frontend/public/help/HANDBUCH-ADMIN.md` (Spiegel)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `admin_rest`)

**Interfaces:**
- Consumes: Anker `#arbeitszeit-bloecke`, `#nicht-angerechnet-anerkennen` (Task 2), `#mitarbeiter-bearbeiten` (Bestand); Spaltenname „Zeiteinträge" (Task 1).
- Produces: Gruppe `admin_rest`; HANDBUCH-ADMIN.md auf Stand 1.20.0 (Kopf „Version 2.9"); die `links`-Gruppe ist ab hier für das Admin-Handbuch grün.

- [ ] **Step 1: Prüfgruppe ergänzen**

Oberhalb der Markerzeile in `scripts/check-doc-sync.sh` einfügen:

```bash
group_admin_rest() {
  local f=docs/handbuch/HANDBUCH-ADMIN.md
  need "$f" '**Version 2.9 | Stand: Oktober 2026 (für PraxisZeit 1.20.0)**'
  need "$f" 'Rechenstand der Software (Version 1.20.0)'
  need "$f" 'Netto-Spalte; unter der Uhrzeit steht bei gekappten Einträgen'
  need "$f" 'Unterbrechung (Min)** und **Zeiteinträge**'
  need "$f" 'Nicht angerechnet (Min)** (letzte Spalte, ab 1.20.0)'
  need "$f" 'Von 07:45, Bis 18:15, Netto 8,00, Nicht angerechnet 240'
  need "$f" 'inkl. Unterbrechung, Zeiteinträge und Nicht angerechnet'
  need "$f" 'genehmigen und anerkennen'
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
}

```

- [ ] **Step 2: Gruppe laufen lassen – muss scheitern**

Run: `bash scripts/check-doc-sync.sh admin_rest`
Expected: Exit 1, u. a. `FEHLT     … **Version 2.9 | Stand …` und `VERALTET  … #6-benutzer-verwalten`.

- [ ] **Step 3: Kopf, §3 und §6 (⚠ #497/#498)**

In `docs/handbuch/HANDBUCH-ADMIN.md`:

1. `**Version 2.8 | Stand: Oktober 2026 (für PraxisZeit 1.19.3)**` → `**Version 2.9 | Stand: Oktober 2026 (für PraxisZeit 1.20.0)**`
2. Den Satz `**Detailansicht:** Klicken Sie auf den Pfeil am Ende einer Zeile, um die Detailansicht des Mitarbeiters zu öffnen.` ergänzen zu:

```markdown
**Detailansicht:** Klicken Sie auf den Pfeil am Ende einer Zeile, um die Detailansicht des Mitarbeiters zu öffnen. Sie listet die Einträge mit Netto-Spalte; unter der Uhrzeit steht bei gekappten Einträgen die Zusatzzeile zur nicht angerechneten Zeit, daneben der Knopf **„Anerkennen"** (→ [Nicht angerechnete Zeit erkennen und anerkennen](#nicht-angerechnet-anerkennen)).
```

3. Die Zeile, die mit `- **Spalten je Tag:** Datum, Wochentag, Von, Bis, Pause (Min)` beginnt, ganz ersetzen durch:

```markdown
- **Spalten je Tag:** Datum, Wochentag, Von, Bis, Pause (Min), Netto (Std), Soll (Std), Differenz, Abwesenheit, Bemerkung – in Excel und ODS zusätzlich **Unterbrechung (Min)** und **Zeiteinträge**, als letzte Spalte in Excel, ODS und PDF **Nicht angerechnet (Min)** (alle hinten angehängt; die übrigen Spalten stehen unverändert an ihrem Platz, damit bestehende Auswertungen weiter funktionieren)
```

4. Im Punkt `- **Netto (Std)** ist die **angerechnete Arbeitszeit** …` den Teilsatz `Ist für die Person ein [Soll-Arbeitszeit-Fenster](#arbeitszeit-bloecke) hinterlegt, ist das die auf das Fenster gekappte Zeit – auch „Von"/„Bis" zeigen dann die gekappten Zeiten;` ersetzen durch:

```markdown
Hat die Person [Arbeitszeit-Blöcke](#arbeitszeit-bloecke), ist das die Zeit nach der Kappung: „Von"/„Bis" zeigen die vor dem ersten bzw. nach dem letzten Block gekürzten Zeiten, und Zeit zwischen den Blöcken ist von Netto abgezogen;
```

5. Im Punkt `- **Geteilte Dienste** …` drei Stellen ersetzen:
   - `**Unterbrechung (Min)** die Zeit zwischen den Blöcken und **Arbeitsblöcke** die einzelnen Blöcke („07:45–12:00, 14:15–17:00")` → `**Unterbrechung (Min)** die Zeit zwischen den Einträgen und **Zeiteinträge** die einzelnen Einträge („07:45–12:00, 14:15–17:00")`
   - `Damit geht die Zeile auf: Bis − Von − Pause − Unterbrechung = Netto.` → `Damit geht die Zeile auf: Bis − Von − Pause − Unterbrechung = Netto – solange nichts zwischen zwei Arbeitszeit-Blöcken gestempelt wurde; sonst ist Netto zusätzlich um diese nicht angerechnete Lückenzeit kleiner.`
   - `– die Spalte „Arbeitsblöcke" zeigt sie` → `– die Spalte „Zeiteinträge" zeigt sie`
6. Direkt nach dem Punkt „Geteilte Dienste" (vor der Leerzeile und `**Verwendung:** Gehaltsabrechnung, …`) einen Punkt einfügen:

```markdown
- **Nicht angerechnet (Min)** (letzte Spalte, ab 1.20.0) nennt je Tag die gestempelte, aber nicht angerechnete Zeit in Minuten: die Zeit zwischen den Arbeitszeit-Blöcken **und** die vor dem ersten bzw. nach dem letzten Block abgeschnittene Zeit, die in „Von"/„Bis" schon fehlt. Beispiel: gestempelt 07:00–19:00 bei Blöcken 08:00–12:00 + 15:00–18:00 und 15 Minuten Puffer → Von 07:45, Bis 18:15, Netto 8,00, Nicht angerechnet 240 (davon 150 zwischen den Blöcken). Die Abendzeit eines automatisch auf 23:59 geschlossenen Eintrags zählt nicht mit (23:59 ist kein echter Stempel). Die Summenzeile nennt den Monat.
```

7. Unter `### Jahresreport Detailliert`: `(inkl. Unterbrechung und Arbeitsblöcke; die Differenz enthält die Gutschrift für Krankheit/Fortbildung)` → `(inkl. Unterbrechung, Zeiteinträge und Nicht angerechnet; die Differenz enthält die Gutschrift für Krankheit/Fortbildung)`

- [ ] **Step 4: §8, §9, §12, §13**

1. §8: `(Kappung auf das Arbeitszeit-Fenster, Wochen- oder Nachtarbeitszeit, Kind-krank-Kontingent)` → `(Kappung durch die Arbeitszeit-Blöcke, Wochen- oder Nachtarbeitszeit, Kind-krank-Kontingent)`. Danach, vor dem Kasten `> **Empfehlung:** Prüfen Sie Korrekturanträge zeitnah …`, einfügen:

```markdown
**Anrechnung beantragt (ab 1.20.0):** Stellt eine Mitarbeiterin bzw. ein Mitarbeiter einen Antrag über **„Anrechnung beantragen"**, bedeutet **„Genehmigen"** hier **„Anerkennen"**: Die gesamte gestempelte Zeit des Eintrags wird angerechnet und bleibt es (→ [Anerkennen](#nicht-angerechnet-anerkennen)). Bei einem automatisch geschlossenen Eintrag enthält der Antrag das tatsächliche Ende. Bei jedem anderen Änderungsantrag zu einem Eintrag mit nicht angerechneter Zeit bietet die Prüfung zusätzlich **„genehmigen und anerkennen"** an. Ist der Eintrag bereits anerkannt, steht in der Prüfung *„Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet."*

```

2. §9: Die Tabellenzeile, die mit `| **Stundenänderungen** |` beginnt, ersetzen durch:

```markdown
| **Arbeitszeit-Änderungen** | Je Änderung und je Löschung eine Sammelzeile im Monat der Änderung (Wirkungsdatum, neu berechnete Einträge, Differenz der angerechneten Zeit, Saldo-Differenz, Puffer, Grund, Vertrag alt → neu) und je neu berechnetem Eintrag eine Zeile mit alten und neuen Zeiten (Quelle „wh_reclamp", Anzeige „Neukappung (Arbeitszeit-Änderung)"); je nachgezogener Abwesenheit eine Zeile mit altem/neuem Stundenwert (Quelle „wh_change", Anzeige „Stundenänderung") |
| **Anerkennungen** | Anerkannte Einträge mit vorher und nachher angerechneter Zeit (Quelle „credit_override", Anzeige „Anrechnung anerkannt") |
```

3. §12, Schritt 2 „Vorschau": `und, wenn ein Arbeitszeit-Fenster hinterlegt ist, die Kappung der importierten Zeit auf dieses Fenster.` → `und, wenn Arbeitszeit-Blöcke hinterlegt sind, die Kappung der importierten Zeit (auch die nicht angerechnete Zeit zwischen den Blöcken).` Im selben Schritt nach `Klicken Sie auf **„Import bestätigen"**.` anfügen: ` Die Netto-Stunden der Vorschau rechnet der Server so, wie er sie anschließend speichert; eine automatische Pause zieht der Import nur ab, soweit die Lücke zwischen den Blöcken die Pausenpflicht nicht schon abdeckt. Überschreibt der Import einen anerkannten Eintrag, steht dort *„Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet."*`
4. §13: Unter `### Soll-Arbeitszeit-Fenster (Puffer)` den Absatz, der mit `Im Bereich **„Soll-Arbeitszeit-Fenster"** legen Sie im Feld` beginnt, ersetzen durch:

```markdown
Im Bereich **„Soll-Arbeitszeit-Fenster"** legen Sie im Feld **„Puffer für Soll-Arbeitszeit-Fenster (Min.)"** den systemweiten Puffer für die Arbeitszeit-Blöcke fest (Standard: **15** Minuten). Er gilt an jedem Blockrand, auch zwischen zwei Blöcken; eine Lücke bis zum doppelten Puffer wird angerechnet. Gestempelte Zeit weiter außerhalb wird nicht angerechnet – Details und Beispiel: [Abschnitt 4 → „Arbeitszeit-Blöcke"](#arbeitszeit-bloecke).

Eine Änderung des Puffers wirkt auf neue Einträge. Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn, auch wenn er später bearbeitet wird. Nur eine Arbeitszeit-Änderung mit Neuberechnung kappt die betroffenen Einträge mit dem dann gültigen Puffer neu; die Vorschau nennt ihn, und verliert dabei ein Eintrag angerechnete Zeit, gilt der Verkürzungsschutz. Einträge aus der Zeit vor Version 1.20.0 tragen keinen gespeicherten Puffer und werden bei einer Bearbeitung mit dem aktuellen Puffer gekappt. Bereits gespeicherte Einträge ändern sich durch das Speichern dieser Einstellung allein nicht.
```

- [ ] **Step 5: §14 (⚠ #499), §17, §18**

1. §14, Tabelle unter `### Automatische Warnungen im Alltag`: nach der Zeile, die mit `| **Ruhezeitwarnung** |` beginnt, vier Zeilen anfügen:

```markdown
| **Anwesenheit über 10 h (laut Stempel)** | gestempelte Anwesenheit des Tages abzüglich erfasster Pausen > 10 h, angerechnet ≤ 10 h | Hinweis | § 3 ArbZG |
| **Durchgestempelt ohne Pause (laut Stempel)** | > 6 h Anwesenheit ohne ausreichende erfasste Pause, obwohl die Pausenprüfung auf der angerechneten Zeit bestanden hat | Hinweis | § 4 ArbZG |
| **Anwesenheit über 48 h/Woche (laut Stempel)** | gestempelte Anwesenheit der Kalenderwoche > 48 h, angerechnet ≤ 48 h | Hinweis | § 3 ArbZG |
| **Pause in der Lücke** | Pause eingetragen **und** über die Lücke zwischen zwei Arbeitszeit-Blöcken durchgestempelt (beides wird abgezogen) | Hinweis | – |
```

   Direkt unter der Tabelle (vor `---` und `## 15. Überstundenausgleich`) einfügen:

```markdown

**Angerechnete Zeit und tatsächliche Anwesenheit (ab 1.20.0):** Die Sperren nach § 3 (10 Stunden) und § 4 (Pausen) rechnen mit der **angerechneten** Zeit; ein Lückenabschnitt ab 15 Minuten zwischen zwei Arbeitszeit-Blöcken zählt dabei als Pause. Damit eine Kappung keinen Verstoß verdeckt, prüft PraxisZeit zusätzlich die **Anwesenheit laut Stempel** und meldet sie als Hinweis (nie blockierend), z. B. *„§4 ArbZG: Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – eine Ruhepause ist nicht erfasst (‹x› h Anwesenheit). Die Lücke gilt nur dann als Pause, wenn sie tatsächlich frei war."* oder *„§3 ArbZG: Laut Stempel ‹x› h anwesend (abzüglich erfasster Pausen) – mehr als 10 Stunden. Angerechnet werden ‹y› h; die Höchstgrenze gilt für die tatsächliche Arbeitszeit."* Die 24-Wochen-Auswertung (§ 3 ArbZG) zeigt neben dem Durchschnitt der angerechneten Zeit einen zweiten Wert **„Anwesenheit laut Stempel"**, den keine Neuberechnung verändert. Für Jugendliche (JArbSchG) prüft PraxisZeit keine dieser Grenzen.
```

2. §17: Nach der Tabelle „Paragraph | Inhalt | Umsetzung" (vor `### Admin-Pflichten im Überblick`) einfügen:

```markdown

**Arbeitszeit-Blöcke – weitere Rechtsgrundlagen:** Vergütung tatsächlich geleisteter, nicht angerechneter Arbeit (§ 611a Abs. 2, § 612 Abs. 1 BGB; §§ 1, 3, 17 MiLoG), Lage und Umfang der Arbeitszeit (§ 106 GewO; § 2 KSchG; §§ 8, 9, 12 Abs. 3 TzBfG; § 2 Abs. 1 Satz 2 Nr. 7 und § 3 NachwG), Mitbestimmung (§ 87 Abs. 1 Nr. 2, 3 und 6 BetrVG) und Jugendliche (§§ 11, 12 JArbSchG). Die Hinweise dazu stehen unter [„Arbeitszeit-Blöcke"](#arbeitszeit-bloecke) und [„Mitarbeiter bearbeiten"](#mitarbeiter-bearbeiten); PraxisZeit prüft diese Punkte nicht.
```

   In der Liste „Admin-Pflichten im Überblick": `5. **Aktuelle Benutzerdaten** – bei Stundenänderungen immer Wirkungsdatum eintragen` → `5. **Aktuelle Benutzerdaten** – bei Arbeitszeit-Änderungen immer Wirkungsdatum eintragen; rückwirkende Verkürzungen nur mit Grund (Fehlerkorrektur oder Vereinbarung)`. Nach Punkt 6 anfügen: `7. **Nicht angerechnete Zeit prüfen** – Monatsjournal („Anwesenheit nicht angerechnet") bzw. Export-Spalte „Nicht angerechnet (Min)"; tatsächlich geleistete, geduldete Arbeit anerkennen`

3. §18-Einleitung: `auf dem tatsächlichen Rechenstand der Software (Version 1.19.3)` → `auf dem tatsächlichen Rechenstand der Software (Version 1.20.0)`
4. §18.2: Nach dem Absatz, der mit `Bei **individuellen Tagesstunden** (z. B. Mo 10 h / Di 10 h / Mi 4 h)` beginnt, einen Absatz einfügen:

```markdown

Bei **Arbeitszeit-Blöcken** ist das Tagessoll die Summe der Blockdauern minus „Pause innerhalb der Blöcke", auf zwei Nachkommastellen gerundet (08:00–12:00 + 15:00–18:00, Pause 30 Min. → 6,50 h; 08:00–12:05 ohne Pause → 4,08 h).
```

5. §18.3: `Pro Zeiteintrag: **Ist = (Ende − Beginn) − Pause**, auf 2 Nachkommastellen gerundet und **nie negativ**.` → `Pro Zeiteintrag: **Ist = (Ende − Beginn) − Pause − nicht angerechnete Zeit zwischen den Arbeitszeit-Blöcken**, auf 2 Nachkommastellen gerundet und **nie negativ**.` Im folgenden Absatz `Ist ein **Soll-Arbeitszeit-Fenster** hinterlegt (→ [Abschnitt 4, Soll-Arbeitszeiten](#4-benutzerverwaltung)), wird die angerechnete Zeit auf das Fenster (± Puffer) gekürzt; der Rohstempel bleibt erhalten (§ 16 ArbZG).` ersetzen durch `Sind **Arbeitszeit-Blöcke** hinterlegt (→ [Abschnitt 4, Arbeitszeit-Blöcke](#arbeitszeit-bloecke)), werden Beginn und Ende auf den ersten Block minus Puffer bzw. den letzten Block plus Puffer gekürzt und die Zeit zwischen den Blöcken (abzüglich Puffer) nicht angerechnet; der Rohstempel bleibt erhalten (§ 16 ArbZG), anerkannte Einträge zählen voll.`
6. §18.8: Den Punkt, der mit `- **Stundenänderung (rückwirkend oder zukunftsdatiert):**` beginnt, ganz ersetzen durch:

```markdown
- **Arbeitszeit-Änderung (rückwirkend oder zukunftsdatiert):** alte Monate rechnen mit der damals gültigen Arbeitszeit (Verlauf / Gültig-ab-Datum). Rückwirkend werden erfasste Zeiteinträge an geänderten Wochentagen neu gekappt und danach die Stunden bereits gebuchter Abwesenheiten auf das neue Tagessoll umgestellt – Abwesenheiten auch bei einem Datum in der Zukunft (Ausnahme: Überstundenausgleich, MA ohne Stundenzählung); Urlaubs**tage** bleiben unberührt. Senkt eine rückwirkende Änderung angerechnete Zeit oder das Überstundenkonto, gilt der Verkürzungsschutz. Details in [Abschnitt 4 → „Mitarbeiter bearbeiten"](#mitarbeiter-bearbeiten).
```

- [ ] **Step 6: Spiegel aktualisieren und alle Admin-Gruppen prüfen**

```bash
cp docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
bash scripts/check-doc-sync.sh admin_bloecke admin_aendern admin_rest mirror links
```

Expected: `OK: admin_bloecke admin_aendern admin_rest mirror links`.

- [ ] **Step 7: Commit**

```bash
git add scripts/check-doc-sync.sh docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
git commit -F - <<'EOF'
docs(handbuch): Admin-Handbuch – Exporte, Anträge, Protokoll, Puffer, ArbZG auf 1.20.0

Export-Spalten „Zeiteinträge" und „Nicht angerechnet (Min)" mit Zeilenregel,
„Anrechnung beantragt" / „genehmigen und anerkennen", Protokollzeilen
Neukappung und Anerkennung, XLS-Import, Puffertext (Spec 12.3),
Anwesenheits-Hinweise und 24-Wochen-Wert, weitere Rechtsgrundlagen,
Berechnungsanhang. Behebt den toten Link #6-benutzer-verwalten.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 5: Mitarbeiter-Handbuch ⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen

Nicht angerechnete Zeit erkennen, „Anrechnung beantragen", anerkannte Einträge, Dashboard-Hinweis, Profilkarte (Spec 13.1, 14, 16.1 „Mitarbeiter-Handbuch"); Begriffsbereinigung der Lane-Texte #494/#500.

**Files:**
- Modify: `docs/handbuch/HANDBUCH-MITARBEITER.md` (bei `3d46c2f`: Zeile 3, Inhaltsverzeichnis Zeile 16, §2 Zeilen 63, 81–87, §3.2 Zeilen 176–184, §3.3 Zeilen 197–211, §3.4 Zeilen 217–222, §5 Zeilen 410–420, §7 Zeilen 480–483, FAQ Zeilen 585–586, Rechtliche Grundlagen Zeilen 620–636)
- Modify: `frontend/public/help/HANDBUCH-MITARBEITER.md` (Spiegel)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `mitarbeiter`)

**Interfaces:**
- Consumes: Prüfskript (Task 0).
- Produces: Anker `#33-arbeitszeit-blöcke-und-anrechnung` (Überschrift „3.3 Arbeitszeit-Blöcke und Anrechnung"); Gruppe `mitarbeiter`.

- [ ] **Step 1: Prüfgruppe ergänzen**

Oberhalb der Markerzeile einfügen:

```bash
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
  need "$f" 'Anerkannter Eintrag – Änderung bitte per Änderungsantrag.'
  need "$f" 'Pause zwischen den Arbeitsblöcken'
  need "$f" 'Meine Arbeitszeit'
  need "$f" 'Ihre Arbeitszeit wurde ab 01.09.2026 geändert'
  need "$f" 'Nicht angerechnet heißt nicht unbezahlt'
  forbid "$f" 'erfassten Blöcke'
  forbid "$f" 'vergessener Nachmittagsblock'
  forbid "$f" '#33-soll-arbeitszeiten-und-anrechnung'
  forbid "$f" 'Soll-Arbeitszeit hinterlegt'
  forbid "$f" 'Soll-Zeiten für Sie hinterlegt'
}

```

- [ ] **Step 2: Gruppe laufen lassen – muss scheitern**

Run: `bash scripts/check-doc-sync.sh mitarbeiter`
Expected: Exit 1, u. a. `FEHLT     … ### 3.3 Arbeitszeit-Blöcke und Anrechnung` und `VERALTET  … erfassten Blöcke`.

- [ ] **Step 3: Kopf, Inhaltsverzeichnis, §2 Dashboard (⚠ #494/#500)**

In `docs/handbuch/HANDBUCH-MITARBEITER.md`:

1. `**Version:** 2.8 · **Stand:** Oktober 2026 (PraxisZeit 1.19.3)` → `**Version:** 2.9 · **Stand:** Oktober 2026 (PraxisZeit 1.20.0)`
2. `   - 3.3 [Soll-Arbeitszeiten und Anrechnung](#33-soll-arbeitszeiten-und-anrechnung)` → `   - 3.3 [Arbeitszeit-Blöcke und Anrechnung](#33-arbeitszeit-blöcke-und-anrechnung)`
3. Tabellenzeile **Tagessaldo**: `Gezählt werden **alle** heute erfassten Blöcke – bei geteiltem Dienst also Vormittag **und** Nachmittag` → `Gezählt werden **alle** heute erfassten Einträge – bei geteiltem Dienst also Vormittag **und** Nachmittag`; am Ende derselben Zeile `Ein halber Urlaubstag oder ein halber 24./31.12. halbiert das Tagessoll |` → `Ein halber Urlaubstag oder ein halber 24./31.12. halbiert das Tagessoll. Sind Arbeitszeit-Blöcke für Sie hinterlegt und Sie sind in der geplanten Pause zwischen zwei Blöcken nicht eingestempelt, zeigt die Karte neutral „Pause zwischen den Arbeitsblöcken" statt Rot |`
4. Nach dem Kasten, der mit `> **Minijob mit festem Monats-Soll:**` beginnt (vor `### Monats-/Wochenübersicht (Tabelle)`), einfügen:

```markdown

> **Hinweis bei Änderungen Ihrer Arbeitszeit:** Ändert die Verwaltung Ihre Arbeitszeit (Wochenstunden, Tagesplan oder Arbeitszeit-Blöcke), sehen Sie 30 Tage lang einen Hinweis auf dem Dashboard – auch wenn die Änderung erst in der Zukunft gilt, z. B. *„Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00). 3 Einträge neu berechnet, angerechnete Zeit −2:15 h."* Wurde rückwirkend verkürzt, steht der Grund dabei (z. B. *„Rückwirkende Verkürzung – Grund: Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)."*). Über den Link gelangen Sie zu Profil → „Meine Arbeitszeit".
```

5. Unter `### Monats-/Wochenübersicht (Tabelle)`: `etwa ein vergessener Nachmittagsblock oder ein Eintrag` → `etwa ein vergessener Nachmittags-Eintrag oder ein Eintrag`

- [ ] **Step 4: §3.2 Vorbelegung und §3.3 neu**

1. In §3.2 nach dem Satz `Klicken Sie auf **Speichern**. Mit **Abbrechen** (oben rechts) verwerfen Sie das Formular.` einfügen:

```markdown

> **Vorbelegung:** Sind Arbeitszeit-Blöcke für Sie hinterlegt, sind **Von** und **Bis** mit dem Beginn des ersten und dem Ende des letzten Blocks von heute vorbelegt.
```

2. Alles von der Zeile `### 3.3 Soll-Arbeitszeiten und Anrechnung` bis **ausschließlich** der Trennlinie `---` vor `### 3.4 Eintrag bearbeiten oder löschen` ersetzen durch:

````markdown
### 3.3 Arbeitszeit-Blöcke und Anrechnung

Ihre Praxis kann Ihre Arbeitszeit je Wochentag (Mo–Fr) als **Arbeitszeit-Blöcke** hinterlegen, z. B. „Montag 08:00–12:00 und 15:00–18:00". Ihr Tagessoll ergibt sich dann aus den Blöcken (→ [Abschnitt 5](#ihr-tagessoll)). Ihre heute gültigen Blöcke und alle Änderungen sehen Sie unter **Profil → „Meine Arbeitszeit"**.

Angerechnet wird Ihre gestempelte Zeit **innerhalb** der Blöcke – mit einem kleinen **Puffer** (Standard 15 Minuten) an jedem Blockrand:

- **Zu früh eingestempelt:** Stempeln Sie deutlich **vor Ihrem ersten Block** ein, wird die Zeit davor nicht angerechnet. Sie sehen dann den Hinweis: *„Du hast vor deinem Soll-Beginn eingestempelt – die Anrechnung beginnt ab dem frühestmöglichen Zeitpunkt."* In der Eintragsliste steht z. B. *„gestempelt 07:30 · angerechnet ab 07:45"*.
- **Zu spät ausgestempelt:** Zeit deutlich **nach dem letzten Block** (über den Puffer hinaus) wird ebenfalls nicht angerechnet.
- **Durchgestempelt über die Pause zwischen zwei Blöcken:** Die Zeit zwischen den Blöcken wird nicht angerechnet – abzüglich des Puffers an beiden Rändern. Beispiel: Blöcke 08:00–12:00 und 15:00–18:00, gestempelt 08:00–18:00 → angerechnet werden **7:30 h**, die 2:30 h von 12:15 bis 14:45 nicht. In der Eintragsliste steht dann *„gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet"*. Wer um 12:05 ausstempelt, verliert keine Minute.
- **Einstempeln in der Pause zwischen zwei Blöcken:** *„Eingestempelt zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet wird erst ab 14:45."* In dieser Zeit zeigt Ihr Dashboard neutral „Pause zwischen den Arbeitsblöcken" statt Rot.
- **Wochenende und Feiertage:** Dort gelten keine Blöcke. Arbeiten Sie an einem Samstag, Sonntag oder Feiertag (z. B. Notdienst), wird die ganze Zeit angerechnet.
- **Beim Ausstempeln und beim Speichern eines eigenen Eintrags** erscheint ein Hinweis, sobald etwas nicht angerechnet wird, z. B. *„Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert. Haben Sie in dieser Zeit gearbeitet, beantragen Sie die Anrechnung (Zeiterfassung → Eintrag → „Anrechnung beantragen“)."* Bei zu frühem Beginn oder zu spätem Ende lautet er z. B. *„… gekappt (Beginn 07:00 → 07:45; Puffer 15 Minuten)"*. Der Eintrag wird **trotzdem gespeichert** — der Hinweis blockiert nichts.
- **Pause und Lücke:** Die Zeit zwischen zwei Blöcken zählt für die Pausenpflicht mit, sobald nach Abzug des Puffers an beiden Rändern mindestens 15 Minuten übrig bleiben – dann verlangt das Ausstempeln dafür keine zusätzliche Pause. Tragen Sie trotzdem eine Pause ein, obwohl Sie über die Lücke durchgestempelt haben, wird beides abgezogen; Sie sehen dann *„Pause in der Lücke wird zusätzlich abgezogen: 30 Min Pause und 2:30 h nicht angerechnet zwischen den Arbeitsblöcken. Lag die Pause in der Lücke, bitte die Pause auf 0 setzen."*
- **Vergessen auszustempeln?** Ein offener Eintrag wird über Nacht automatisch geschlossen und nur bis zum Ende Ihres letzten Blocks (plus Puffer) angerechnet: *„eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 7:45 h (08:00–18:15)"*. Tragen Sie das tatsächliche Ende per Änderungsantrag nach.

**Haben Sie außerhalb oder zwischen den Blöcken gearbeitet?** Dann beantragen Sie die Anrechnung: In der Zeiterfassung oder im Journal am Eintrag **„Anrechnung beantragen"** wählen, kurz begründen (z. B. „Patientin nach Sprechstundenende versorgt") und absenden. Bei einem automatisch geschlossenen Eintrag geben Sie im selben Antrag das tatsächliche Ende an. Genehmigt die Verwaltung den Antrag, wird die ganze gestempelte Zeit angerechnet und der Eintrag ist **„anerkannt"**. Anerkannte Einträge können Sie nicht mehr direkt bearbeiten (*„Anerkannter Eintrag – Änderung bitte per Änderungsantrag."*) – nutzen Sie **„Änderung beantragen"**.

> **Ihre echte Stempelzeit geht nicht verloren:** Der Zeitpunkt, zu dem Sie tatsächlich gestempelt haben, bleibt immer gespeichert (gesetzlich vorgeschrieben, § 16 ArbZG). Für Ihr Stundenkonto wird nur die **angerechnete** Zeit verwendet.

> **Nicht angerechnet heißt nicht unbezahlt:** Ob gearbeitete Zeit vergütet wird, entscheidet nicht diese Anrechnung. Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist zu vergüten (§ 611a, § 612 BGB; Mindestlohngesetz). Sprechen Sie Ihre Verwaltung an oder beantragen Sie die Anrechnung.

> **Hinweis:** Diese Begrenzung ist **nur aktiv, wenn Ihre Praxis Arbeitszeit-Blöcke für Sie hinterlegt hat**. Ist nichts hinterlegt, zählt Ihre gestempelte Zeit ganz normal. Ändert die Praxis Ihre Arbeitszeit, sehen Sie 30 Tage lang einen Hinweis auf Ihrem Dashboard (→ [Abschnitt 2](#2-dashboard--die-übersicht)).

````

- [ ] **Step 5: §3.4, §5, §7, FAQ, Rechtliche Grundlagen**

1. §3.4, Tabelle „Button | Funktion": nach der Zeile `| **Löschantrag** | … |` anfügen:

```markdown
| **Anrechnung beantragen** | Bei eigenen Einträgen mit nicht angerechneter Zeit: Antrag, die ganze gestempelte Zeit anzurechnen (→ [Abschnitt 3.3](#33-arbeitszeit-blöcke-und-anrechnung)) |
| **Änderung beantragen** | Bei **anerkannten** Einträgen anstelle von „Bearbeiten" – anerkannte Einträge ändern Sie nur per Antrag |
```

2. §5 „Ihr Tagessoll": an den Absatz, der mit `Beispiele: 40 h auf 5 Tage = **8 h/Tag**` beginnt, anfügen: ` Hat Ihre Praxis **Arbeitszeit-Blöcke** für Sie hinterlegt, ist Ihr Tagessoll die Summe der Blöcke minus der geplanten Pause innerhalb der Blöcke – z. B. 08:00–12:00 und 15:00–18:00 mit 30 Minuten Pause = **6:30 h**.`
3. §5 „Ihre Ist-Stunden": `Ihr **Ist** ist Ihre tatsächlich erfasste Arbeitszeit: **(Ende − Beginn) − Pause** je Eintrag.` → `Ihr **Ist** ist Ihre tatsächlich erfasste Arbeitszeit: **(Ende − Beginn) − Pause** je Eintrag – abzüglich nicht angerechneter Zeit vor, nach oder zwischen Ihren Arbeitszeit-Blöcken (→ [Abschnitt 3.3](#33-arbeitszeit-blöcke-und-anrechnung)).`
4. §7: nach der Liste, die mit `- Rolle, Urlaubstage, Status` endet, einfügen (PR2-Gesamtreview Fund 10: die Wochenstunden stehen seit PR2 nicht mehr in den persönlichen Daten, sondern datumsaufgelöst in der Karte „Meine Arbeitszeit"; die Liste ist in PR2 schon angepasst):

```markdown

**Meine Arbeitszeit:** Die Karte zeigt Ihre heute gültigen Arbeitszeit-Blöcke je Wochentag mit Tagessoll, Ihre Wochenstunden und den Verlauf mit Wirkungsdaten (z. B. „ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) … · 15,5 Std/Woche"). Sind keine Blöcke hinterlegt, sehen Sie Tagessoll und Wochenstunden. Ändern kann Ihre Arbeitszeit nur die Verwaltung; jede Änderung kündigt Ihr Dashboard 30 Tage lang an.
```

5. FAQ: Die Antwort unter `**F: Warum steht bei meinem Eintrag „gestempelt 07:30 · angerechnet ab 07:45"?**` ersetzen durch:

```markdown
A: Ihre Praxis hat für diesen Wochentag Arbeitszeit-Blöcke hinterlegt. Wenn Sie deutlich vor dem ersten Block ein- oder nach dem letzten Block ausstempeln, wird nur bis zu einem kleinen Puffer (Standard 15 Min.) angerechnet. Ihre tatsächliche Stempelzeit bleibt gespeichert. Siehe [Abschnitt 3.3](#33-arbeitszeit-blöcke-und-anrechnung).

**F: Warum steht bei meinem Eintrag „2:30 h zwischen den Blöcken nicht angerechnet"?**
A: Sie haben über die geplante Pause zwischen zwei Arbeitszeit-Blöcken durchgestempelt. Diese Zeit (abzüglich Puffer) wird nicht angerechnet; Ihre Stempelzeit bleibt gespeichert. Haben Sie in dieser Zeit gearbeitet, beantragen Sie am Eintrag die Anrechnung über **„Anrechnung beantragen"** (→ [Abschnitt 3.3](#33-arbeitszeit-blöcke-und-anrechnung)).

**F: Ich kann einen Eintrag nicht mehr bearbeiten – „Anerkannter Eintrag – Änderung bitte per Änderungsantrag."**
A: Die Verwaltung hat für diesen Eintrag die ganze gestempelte Zeit anerkannt. Solche Einträge ändern Sie nur noch per Antrag (**„Änderung beantragen"**).

**F: Auf meinem Dashboard steht „Ihre Arbeitszeit wurde ab … geändert". Was bedeutet das?**
A: Ihre Verwaltung hat Ihre Arbeitszeit geändert – Wochenstunden, Tagesplan oder Arbeitszeit-Blöcke. Der Hinweis nennt das Datum, die neue Arbeitszeit und, falls bereits erfasste Einträge neu berechnet wurden, deren Anzahl und die Änderung der angerechneten Zeit. Er verschwindet nach 30 Tagen; die Einzelheiten stehen unter Profil → „Meine Arbeitszeit". Bei Fragen wenden Sie sich an Ihre Verwaltung.
```

6. „Rechtliche Grundlagen": unter dem Kasten `> **Minijob-Arbeitszeitkonto:** …` einfügen:

```markdown

> **Arbeitszeit-Blöcke und Vergütung:** Nicht angerechnet heißt nicht unbezahlt – Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist zu vergüten (§ 611a, § 612 BGB; Mindestlohngesetz). Haben Sie außerhalb oder zwischen Ihren Arbeitszeit-Blöcken gearbeitet, beantragen Sie die Anrechnung (→ [Abschnitt 3.3](#33-arbeitszeit-blöcke-und-anrechnung)).
```

- [ ] **Step 6: Spiegel aktualisieren und prüfen**

```bash
cp docs/handbuch/HANDBUCH-MITARBEITER.md frontend/public/help/HANDBUCH-MITARBEITER.md
bash scripts/check-doc-sync.sh mitarbeiter mirror links
```

Expected: `OK: mitarbeiter mirror links`.

- [ ] **Step 7: Commit**

```bash
git add scripts/check-doc-sync.sh docs/handbuch/HANDBUCH-MITARBEITER.md frontend/public/help/HANDBUCH-MITARBEITER.md
git commit -F - <<'EOF'
docs(handbuch): Mitarbeiter-Handbuch – Arbeitszeit-Blöcke und Anrechnung beantragen

3.3 erklärt Blöcke, Puffer, Lücke (08–18 → 7:30 h), Hinweistexte, Pause in
der Lücke, Auto-Close, „Anrechnung beantragen" und anerkannte Einträge;
Dashboard-Hinweis bei Arbeitszeit-Änderungen, Profilkarte „Meine
Arbeitszeit", FAQ, Vergütungshinweis. Gestempelte Einträge heißen nicht
mehr „Blöcke" (Abgrenzung zu den Arbeitszeit-Blöcken).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 6: Kurzanleitungen und Schnellstart (Markdown) ⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen

**Files:**
- Modify: `docs/handbuch/CHEATSHEET-ADMIN.md` (bei `3d46c2f`: Zeilen 43–59, 120–125, 157, 262–265)
- Modify: `docs/handbuch/CHEATSHEET-MITARBEITER.md` (bei `3d46c2f`: Zeilen 58–62, 134, 143, 176–185)
- Modify: `docs/handbuch/SCHNELLSTART.md` (bei `3d46c2f`: Zeilen 33, 39–40)
- Modify: `frontend/public/help/CHEATSHEET-ADMIN.md`, `CHEATSHEET-MITARBEITER.md`, `SCHNELLSTART.md` (Spiegel)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `kurz`)

**Interfaces:**
- Consumes: Begriffe und Wortlaute aus Tasks 2–5; Prüfskript (Task 0).
- Produces: Gruppe `kurz`.

- [ ] **Step 1: Prüfgruppe ergänzen**

Oberhalb der Markerzeile einfügen:

```bash
group_kurz() {
  local a=docs/handbuch/CHEATSHEET-ADMIN.md
  local m=docs/handbuch/CHEATSHEET-MITARBEITER.md
  local s=docs/handbuch/SCHNELLSTART.md
  need "$a" '### Arbeitszeit-Blöcke (ab 1.20.0)'
  need "$a" '### Arbeitszeit ändern (Wochenstunden, Tagesplan, Blöcke)'
  need "$a" 'Arbeitszeit anpassen…'
  need "$a" 'Nach Arbeitsblöcken'
  need "$a" 'Nicht angerechnet (Min)'
  need "$a" 'genehmigen und anerkennen'
  need "$a" 'auf den vorherigen Stand zurücksetzen'
  need "$a" '[Erfassungsfehler korrigiert]'
  need "$a" 'Nichtanrechnung ersetzt keine Vergütungsentscheidung'
  forbid "$a" 'Wochenstunden anpassen…'
  forbid "$a" 'Wochenstunden & Tagesplan'
  forbid "$a" '### Soll-Arbeitszeit-Fenster (#201)'
  need "$m" '### Arbeitszeit-Blöcke'
  need "$m" 'zwischen den Blöcken nicht angerechnet'
  need "$m" 'Anrechnung beantragen'
  need "$m" 'Meine Arbeitszeit'
  forbid "$m" 'aller Blöcke des Tages'
  forbid "$m" 'Fehlende Blöcke'
  forbid "$m" 'für Sie Soll-Zeiten hinterlegt'
  need "$s" 'Arbeitszeit anpassen…'
  need "$s" 'Nach Arbeitsblöcken'
  forbid "$s" 'Wochenstunden anpassen…'
  forbid "$s" 'Soll-Beginn/-Ende je Wochentag'
}

```

- [ ] **Step 2: Gruppe laufen lassen – muss scheitern**

Run: `bash scripts/check-doc-sync.sh kurz`
Expected: Exit 1, u. a. `VERALTET  docs/handbuch/CHEATSHEET-ADMIN.md: Wochenstunden anpassen…`.

- [ ] **Step 3: CHEATSHEET-ADMIN.md**

1. Alles von `### Soll-Arbeitszeit-Fenster (#201)` bis **ausschließlich** `### Mitarbeiter deaktivieren (niemals löschen!)` (also beide Abschnitte „Soll-Arbeitszeit-Fenster" und „Stundenänderung") ersetzen durch:

````markdown
### Arbeitszeit-Blöcke (ab 1.20.0)

Je MA und Wochentag (Mo–Fr) bis zu **3 Blöcke** „von–bis" + **„Pause innerhalb der Blöcke"** (Raster 5 Min.).
- **Tagessoll = Σ Blöcke − Pause** (z. B. 08–12 + 15–18, Pause 30 → 6:30 h); Wochenstunden und Arbeitstage werden abgeleitet.
- **Kappung:** vor dem ersten, nach dem letzten und **zwischen** den Blöcken nicht angerechnet; **Puffer an jedem Blockrand** (Einstellungen → „Soll-Arbeitszeit-Fenster", Default **15**). Lücke ≤ 2 × Puffer wird voll angerechnet.
- Beispiel: Blöcke 08–12 + 15–18, gestempelt 08:00–18:00 → **7:30 h** angerechnet, 2:30 h nicht; die Stempel bleiben gespeichert (§16).
- **Kein Block → keine Kappung:** blockfreie Wochentage, Wochenende, Feiertage, „freie" Sondertage; MA ohne Stundenzählung; **anerkannte** Einträge. §18-MA werden trotzdem gekappt.
- **Auto-Close** (vergessenes Ausstempeln) rechnet nur bis zum letzten Block + Puffer an.
- **Sichtbar:** Zusatzzeile am Eintrag („… 2:30 h zwischen den Blöcken nicht angerechnet"), Journal-Summe „Anwesenheit nicht angerechnet", Export-Spalte „Nicht angerechnet (Min)" (letzte Spalte).
- **Anerkennen** (Admin-Dashboard-Detail, Monatsjournal): ganze gestempelte Zeit zählt, dauerhaft, protokolliert („Anrechnung anerkannt"). MA beantragen das per **„Anrechnung beantragen"**.
- **Altbestand:** frühere Soll-Fenster = „Arbeitszeit-Fenster (Altbestand, nur Kappung)" → im Dialog umwandeln oder entfernen.
- ⚖️ Nichtanrechnung ersetzt keine Vergütungsentscheidung (§ 611a, § 612 BGB; MiLoG) – geduldete Arbeit anerkennen. Mitbestimmung § 87 Abs. 1 Nr. 2, 3, 6 BetrVG; Jugendliche §§ 11, 12 JArbSchG – PraxisZeit prüft das nicht.

### Arbeitszeit ändern (Wochenstunden, Tagesplan, Blöcke)
**Benutzer öffnen** → Button **„Arbeitszeit anpassen…"** (oder Uhr-Symbol in der Benutzerliste) → Dialog **„Arbeitszeit & Wochenstunden"** → **„Gültig ab"** → Modus **„Gleichmäßig"** / **„Nach Tagen"** / **„Nach Arbeitsblöcken"** (live: Gesamtzeit · Pause · Tagessoll + Wochensumme)
→ Im Bearbeiten-Formular sind Wochenstunden, Tagesstunden, Modus, Arbeitstage und Blöcke nur Anzeige („Arbeitszeit heute: …"); beim **Anlegen** normale Felder bzw. Block-Editor
→ **Auswirkung** vor dem Speichern: Einträge je Monat alt → neu, übersprungene (mit Grund), Abwesenheiten, Δ Soll / Δ angerechnet / Δ Überstunden; Haken „Ich habe die Auswirkungen geprüft und möchte speichern" Pflicht, sobald etwas betroffen ist
→ **Rückwirkend:** Einträge an geänderten Wochentagen werden ab Rohstempel mit dem aktuellen Puffer **neu gekappt**, danach Abwesenheits-Stunden aufs neue Tagessoll (Urlaubs**tage** bleiben); offene Einträge vergangener Tage werden vorher geschlossen; abgeschlossenes Jahr wird nur gemeldet
→ **Verkürzung** (Eintrag verliert Zeit **oder** Überstundenkonto sinkt – auch durch höheres Soll – **oder** Misch-Tag-Gutschrift sinkt stärker als das Tagessoll): Standard **„Ab heute (…) wirksam"**; **rückwirkend** nur mit Grund („Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)" / „Mit der beschäftigten Person vereinbart" / „Sonstiges"), Begründung (10–400 Zeichen) + Haken; Protokoll-Kürzel „[Erfassungsfehler korrigiert]" / „[Einvernehmlich vereinbart]" / „[Sonstiges]". Falsche **Stempel** am Zeiteintrag korrigieren, nicht über die Arbeitszeit. In **abgeschlossene Jahre** gesperrt
→ ⚠️ Seit 1.20.0 braucht auch eine rückwirkende **Erhöhung** der Wochenstunden Grund + Haken, wenn das Konto sinkt
→ **Löschen** (nur jüngste Zeile; früheste gesperrt, solange spätere bestehen) rechnet zurück; bei Verkürzung Standard **„auf den vorherigen Stand zurücksetzen"**
→ MA sehen 30 Tage einen Dashboard-Hinweis + Profil „Meine Arbeitszeit"; Protokoll: „Neukappung (Arbeitszeit-Änderung)" je Eintrag + Sammelzeile je Änderung
→ Berichte: Wert zu Zeitraumsbeginn + „ab TT.MM.JJJJ: …" (bei Blöcken „Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / …")
→ ⚠️ Arbeitstage-only-Änderung (gleiche Wochenstunden, andere Arbeitstage): Berichtstext nennt bei „Gleichmäßig" zwar die neue Arbeitstage-Zahl, die Wochenstundenzahl selbst bleibt aber gleich – das Tagessoll verschiebt sich trotzdem still; bei „Nach Tagen"/„Nach Arbeitsblöcken" ändert sich stattdessen der Urlaubsverbrauch – immer die Auswirkung prüfen, nicht nur die Wochenstundenzahl

````

2. Unter `## Korrekturanträge prüfen` nach der Zeile `- **Ablehnen** → optional Ablehnungsgrund eintragen` anfügen:

```markdown
- **„Anrechnung beantragen"** (MA): Genehmigen = **Anerkennen** (ganze gestempelte Zeit zählt); bei anderen Anträgen zu Einträgen mit nicht angerechneter Zeit zusätzlich **„genehmigen und anerkennen"**
```

3. Einstellungen-Tabelle: `| **Soll-Arbeitszeit-Fenster** | Puffer (Min.) für Soll-Zeiten, Default 15 (s. o.) |` → `| **Soll-Arbeitszeit-Fenster** | Puffer (Min.) an jedem Rand der Arbeitszeit-Blöcke, Default 15; wirkt auf neue Einträge, jeder Eintrag behält seinen Puffer (s. o.) |`
4. Unter `## Audit-Log & Monitoring`: `**Änderungsprotokoll:** Alle Aktionen lückenlos protokolliert → Betriebsprüfungsnachweis` → `**Änderungsprotokoll:** Alle Aktionen lückenlos protokolliert → Betriebsprüfungsnachweis · Arbeitszeit-Änderungen: „Neukappung (Arbeitszeit-Änderung)" je Eintrag + Sammelzeile · Anerkennungen: „Anrechnung anerkannt"`
5. Unter `## Berichte & Exporte` nach `**Aufbewahrungspflicht: 2 Jahre** (§16 ArbZG)` anfügen: `**Spalten (Excel/ODS):** hinten angehängt „Unterbrechung (Min)", „Zeiteinträge" und – auch im PDF – als letzte Spalte „Nicht angerechnet (Min)" (Lücke + vor/nach den Blöcken abgeschnittene Zeit)`

- [ ] **Step 4: CHEATSHEET-MITARBEITER.md und SCHNELLSTART.md**

1. CHEATSHEET-MITARBEITER: Alles von `### Soll-Arbeitszeit-Fenster` bis **ausschließlich** der folgenden Trennlinie `---` ersetzen durch:

````markdown
### Arbeitszeit-Blöcke
*Nur aktiv, wenn die Praxis für Sie Arbeitszeit-Blöcke hinterlegt hat (Profil → „Meine Arbeitszeit") – sonst zählt alles wie gewohnt.*
- Angerechnet wird innerhalb der Blöcke, mit **Puffer** (Std. 15 Min.) an jedem Blockrand.
- Zu früh / zu spät → *„gestempelt 07:30 · angerechnet ab 07:45"*.
- Über die Pause zwischen zwei Blöcken durchgestempelt → *„gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet"*.
- In der Pause zwischen den Blöcken zeigt das Dashboard neutral „Pause zwischen den Arbeitsblöcken".
- Dort gearbeitet? Am Eintrag **„Anrechnung beantragen"** (mit Begründung). Anerkannte Einträge nur noch per **„Änderung beantragen"**.
- Ihre **echte Stempelzeit bleibt gespeichert** (§16 ArbZG); fürs Stundenkonto zählt die angerechnete Zeit. Nicht angerechnet heißt nicht unbezahlt.

````

2. CHEATSHEET-MITARBEITER, Tabelle „Dashboard verstehen": `Heute: Ist-Zeit aller Blöcke des Tages (z. B. Vormittag + Nachmittag)` → `Heute: Ist-Zeit aller Einträge des Tages (z. B. Vormittag + Nachmittag)`
3. CHEATSHEET-MITARBEITER: `Fehlende Blöcke fallen pro Woche sofort auf.` → `Fehlende Einträge fallen pro Woche sofort auf.`
4. CHEATSHEET-MITARBEITER, Tabelle „Häufige Probleme": die Zeile `| „angerechnet ab HH:MM" beim Eintrag | Soll-Zeit-Fenster: nur bis Puffer angerechnet (echte Zeit bleibt) |` ersetzen durch:

```markdown
| „angerechnet ab HH:MM" beim Eintrag | Arbeitszeit-Blöcke: nur bis Puffer angerechnet (echte Zeit bleibt) |
| „… zwischen den Blöcken nicht angerechnet" | Über die Pause zwischen zwei Blöcken gestempelt; gearbeitet? → **„Anrechnung beantragen"** |
| „Anerkannter Eintrag – Änderung bitte per Änderungsantrag." | Eintrag wurde anerkannt → **„Änderung beantragen"** |
| Hinweis „Ihre Arbeitszeit wurde ab … geändert" | Verwaltung hat Ihre Arbeitszeit geändert → Profil → „Meine Arbeitszeit" |
```

5. SCHNELLSTART, §2 Punkt 4: `4. **Arbeitstage** bzw. – bei ungleichmäßiger Verteilung – **Tagesplan** (Stunden je Wochentag)` → `4. **Arbeitstage** bzw. – bei ungleichmäßiger Verteilung – **Tagesplan** (Stunden je Wochentag) oder **Arbeitszeit-Blöcke** (Modus „Nach Arbeitsblöcken")`
6. SCHNELLSTART, Sonderfälle: `- **Soll-Arbeitszeit-Fenster (optional):** Soll-Beginn/-Ende je Wochentag, wenn früh-/spät-Stempel auf das Soll begrenzt werden sollen.` → `- **Arbeitszeit-Blöcke (optional):** Modus „Nach Arbeitsblöcken" – je Wochentag bis zu drei Blöcke „von–bis" plus „Pause innerhalb der Blöcke"; daraus folgen Tagessoll und Anrechnung (Zeit vor, nach und zwischen den Blöcken zählt nur bis zum Puffer).`
7. SCHNELLSTART: den Punkt, der mit `- **Spätere Änderungen:**` beginnt, ersetzen durch: `- **Spätere Änderungen:** Wochenstunden, Tagesplan, Blöcke, Modus und Arbeitstage lassen sich nach dem Anlegen nur noch über den Button „Arbeitszeit anpassen…" mit Wirkungsdatum ändern – direkt im Formular sind diese Felder dann nur noch Anzeige (siehe [Admin-Handbuch](HANDBUCH-ADMIN.md#mitarbeiter-bearbeiten)).`
8. SCHNELLSTART, §3: nach `- Das **Admin-Dashboard** zeigt Team-Stunden, Salden und fehlende Buchungen.` anfügen: `- Gestempelte Zeit vor, nach oder zwischen den Arbeitszeit-Blöcken zeigt PraxisZeit als „nicht angerechnet"; tatsächlich geleistete Arbeit dort **„Anerkennen"** (Admin-Dashboard → Detailansicht).`

- [ ] **Step 5: Spiegel aktualisieren und prüfen**

```bash
cp docs/handbuch/CHEATSHEET-ADMIN.md frontend/public/help/CHEATSHEET-ADMIN.md
cp docs/handbuch/CHEATSHEET-MITARBEITER.md frontend/public/help/CHEATSHEET-MITARBEITER.md
cp docs/handbuch/SCHNELLSTART.md frontend/public/help/SCHNELLSTART.md
bash scripts/check-doc-sync.sh kurz mirror links
```

Expected: `OK: kurz mirror links`.

- [ ] **Step 6: Commit**

```bash
git add scripts/check-doc-sync.sh docs/handbuch/CHEATSHEET-ADMIN.md docs/handbuch/CHEATSHEET-MITARBEITER.md docs/handbuch/SCHNELLSTART.md frontend/public/help/CHEATSHEET-ADMIN.md frontend/public/help/CHEATSHEET-MITARBEITER.md frontend/public/help/SCHNELLSTART.md
git commit -F - <<'EOF'
docs(handbuch): Kurzanleitungen und Schnellstart auf Arbeitszeit-Blöcke

Admin-Kurzanleitung: Blöcke, Kappung, Anerkennen, Arbeitszeit ändern mit
Verkürzungsschutz und Rücksetzen; Mitarbeiter-Kurzanleitung: Blöcke,
„Anrechnung beantragen", neue Fehlerbilder; Schnellstart: Modus „Nach
Arbeitsblöcken" und Knopf „Arbeitszeit anpassen…".

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 7: BERECHNUNGEN.md und GLOSSAR.md ⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen

Rechenregeln der Blöcke (Spec 3, 4.1, 6.1, 6.3, 8, 9.5, 10.2, 15.1, 15.2) und die neuen Begriffe (Spec 16.1: GLOSSAR „Arbeitszeit-Block", „Lücke", „nicht angerechnet", „Anerkennen", „Neukappung").

**Files:**
- Modify: `docs/BERECHNUNGEN.md` (bei `3d46c2f`: Zeile 3; §2 Zeilen 64, 71–79; §3.2 Zeilen 112–115; §3.3 Zeile 117; §4 Zeilen 125–154; Export-Absätze Zeilen 237–268 (#497/#498); TZ-E Zeilen 1058–1071 und 1191; nach TZ-F vor `## 15.` (Zeile 1236); „Quellen im Code" Zeilen 1287–1307)
- Modify: `docs/GLOSSAR.md` (Einleitungskasten Zeilen 11–14, Tabelle §1 Zeile 30, §6 Zeilen 112–124, neuer §7 am Ende)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `berechnungen`)

**Interfaces:**
- Consumes: Funktionsnamen aus PR1–PR3 (`work_blocks_service.derive_targets`, `work_window_service.clamp`, `ClampResult`, `grace_for_entry`, `get_scheduled_blocks`, `credit_gaps`, `gap_segments`, `not_credited_minutes`, `presence_minutes`, `reclamp_time_entries`, `reclamp_audit.summary_note`/`parse_summary_note`/`REASON_TYPES`, `calculation_service.blocks_changed`, `retarget_absence_hours`).
- Produces: BERECHNUNGEN §3.3 „Tagesplan aus Arbeitszeit-Blöcken", §4.1 „Arbeitszeit-Blöcke und Kappung", Worked Example „TZ-G"; GLOSSAR §7; Gruppe `berechnungen`.

- [ ] **Step 1: Namen aus dem Code bestätigen**

```bash
grep -nE "^def (derive_targets|clamp|grace_for_entry|get_scheduled_blocks|credit_gaps|gap_segments|not_credited_minutes|presence_minutes|reclamp_time_entries)\b" backend/app/services/work_window_service.py backend/app/services/work_blocks_service.py
grep -nE "^(def summary_note|def parse_summary_note|REASON_TYPES)" backend/app/services/reclamp_audit.py
grep -nE "^def (blocks_changed|retarget_absence_hours)\b" backend/app/services/calculation_service.py
```

Expected: je Name eine Fundstelle (9 + 3 + 2). Fehlt ein Name oder heißt er anders: den Code-Namen in **allen** Texten dieses Tasks verwenden (und in Task 10/11) – die Rechenregel selbst bleibt.

- [ ] **Step 2: Prüfgruppe ergänzen**

Oberhalb der Markerzeile einfügen:

```bash
group_berechnungen() {
  local b=docs/BERECHNUNGEN.md
  local g=docs/GLOSSAR.md
  need "$b" 'App-Version 1.20.0'
  need "$b" '| `work_blocks` |'
  need "$b" '### 3.3 Tagesplan aus Arbeitszeit-Blöcken (ab 1.20.0)'
  need "$b" '### 3.4 Allgemeine Regeln'
  need "$b" 'net_hours = max( 0 , (end_time − start_time) − break_minutes − uncredited_minutes )'
  need "$b" '### 4.1 Arbeitszeit-Blöcke und Kappung'
  need "$b" 'grace_for_entry'
  need "$b" 'not_credited_minutes'
  need "$b" 'Bis − Von − Pause − Unterbrechung − Σ uncredited_minutes = Netto'
  need "$b" '### TZ-G: Rückwirkende Änderung der Arbeitszeit-Blöcke (ab 1.20.0)'
  need "$b" 'Arbeitszeit-Änderung ab 01.09.2026: 3 Einträge neu berechnet, Δ -135 Min, Saldo Δ +105 Min'
  need "$b" 'services/reclamp_audit.py'
  forbid "$b" 'scheduled_start_<wd>'
  forbid "$b" 'Wochenstunden anpassen…'
  forbid "$b" '### 4.1 Arbeitszeit-Fenster (#201)'
  forbid "$b" 'Arbeitsblöcke" als Spalten 11/12'
  need "$g" '## 7. Arbeitszeit-Blöcke und Anrechnung (ab 1.20.0)'
  need "$g" '| **Arbeitszeit-Block** |'
  need "$g" '| **Lücke** |'
  need "$g" '| **nicht angerechnet** |'
  need "$g" '| **Anerkennen** |'
  need "$g" '| **Neukappung** |'
  need "$g" '(Ende − Beginn) − Pause − `uncredited_minutes`'
}

```

- [ ] **Step 3: Gruppe laufen lassen – muss scheitern**

Run: `bash scripts/check-doc-sync.sh berechnungen`
Expected: Exit 1, u. a. `VERALTET  docs/BERECHNUNGEN.md: scheduled_start_<wd>`.

- [ ] **Step 4: BERECHNUNGEN.md – Kopf, §2, §3**

1. `> **Stand: Oktober 2026 · App-Version 1.19.3**` → `> **Stand: Oktober 2026 · App-Version 1.20.0**`
2. §2-Tabelle: die Zeile `| `scheduled_start_<wd>` / `scheduled_end_<wd>` | Arbeitszeit-Fenster je Wochentag (#201) | optional | optional |` ersetzen durch:

```markdown
| `work_blocks` | Arbeitszeit-Blöcke Mo–Fr: je Tag bis zu 3 Blöcke `"HH:MM"` + `pause_minutes` (historisiert, s. u.; Rückfall nur vor der ersten Verlaufszeile, §3.3/§4.1) | – | `Mo 08:00–12:00 + 15:00–18:00, Pause 30` |
```

3. Am Ende des Kastens `> **Historie (#415/#431):** …` (nach `… gleichmäßige Verteilung **und** individuellen Tagesplan.`) eine Zeile anfügen:

```markdown
> Seit 1.20.0 trägt dieselbe Zeile auch die **Arbeitszeit-Blöcke** (`working_hours_changes.blocks`); NULL heißt dort „keine Blöcke", **nie** Rückfall auf `users.work_blocks`.
```

4. §3.2: `> „Wochenstunden anpassen…" mit Wirkungsdatum historisch ändern — inkl. Rückrechnung` → `> „Arbeitszeit anpassen…" mit Wirkungsdatum historisch ändern — inkl. Rückrechnung`
5. `### 3.3 Allgemeine Regeln` → `### 3.4 Allgemeine Regeln` und **davor** einfügen:

````markdown
### 3.3 Tagesplan aus Arbeitszeit-Blöcken (ab 1.20.0)

Im Modus „Nach Arbeitsblöcken" pflegt die Verwaltung je Wochentag bis zu drei Blöcke und eine
„Pause innerhalb der Blöcke". Beim Speichern leitet `work_blocks_service.derive_targets` daraus den
Tagesplan ab und schreibt ihn in die Verlaufszeile (materialisiert):

```
hours_<tag>        = (Σ Blockdauer − pause_minutes) / 60   → quantize(0,01, ROUND_HALF_EVEN)
weekly_hours       = Σ hours_<tag>
work_days_per_week = Anzahl Tage mit Blöcken
use_daily_schedule = true
```

Danach rechnet alles wie §3.2 — `calculation_service` liest für das Soll **nie** Blöcke. Beispiele:

| Blöcke | Pause | Σ | Tagessoll |
|---|---|---|---|
| 08:00–12:00 + 15:00–18:00 | 30 | 7:00 h | **6,50 h** |
| 08:00–12:05 | 0 | 4:05 h | **4,08 h** (4,0833…) |
| 07:30–12:00 + 13:00–16:25 | 0 | 7:55 h | **7,92 h** (7,9166…) |
| — | 0 | 0 | **0,00 h** |

Rundung: höchstens 0,005 h (18 s) je Tag zwischen Blocksumme und gespeichertem Tagessoll; dazu
rundet `net_hours` je Eintrag auf 2 Stellen. Ein exakt nach Blöcken gestempelter Tag ergibt Saldo 0
bis auf höchstens 0,005 h × (Anzahl Einträge + 1) — drei Blöcke zu 55 Min mit je einem Eintrag:
3 × 0,92 h = 2,76 h gegen 2,75 h Soll.

**Altfenster** aus Migration 073 (`pause_minutes` = NULL; ein Block je Tag aus dem früheren
Soll-Fenster #201) kappen nur; ihr Soll kommt weiter aus `weekly_hours`/`hours_*` der Zeile.
Eine Liste mit fünf leeren Tagen gilt wie NULL (keine Blöcke).

````

- [ ] **Step 5: BERECHNUNGEN.md – §4 (⚠ #497/#498)**

1. Den Codeblock unter `## 4. Ist-Stunden (`net_hours`)` und die drei Punkte darunter ersetzen durch:

````markdown
```
net_hours = max( 0 , (end_time − start_time) − break_minutes − uncredited_minutes )
```

- Auf **2 Nachkommastellen** gerundet.
- **Floor bei 0**: kann nie negativ werden (offene Einträge ohne `end_time` → 0).
- **Pause** wird in Minuten geführt und abgezogen.
- **`uncredited_minutes`** = gestempelte Minuten in der Lücke zwischen zwei Arbeitszeit-Blöcken (§4.1); immer serverseitig berechnet, nie Eingabe. Ohne Blöcke 0.
- Der SQL-Ausdruck (Summen in der Datenbank) rechnet dasselbe, rundet aber nicht je Zeile; Python- und SQL-Summe liegen höchstens n × 0,005 h auseinander.
````

2. Den ganzen Unterabschnitt `### 4.1 Arbeitszeit-Fenster (#201)` (bis ausschließlich `### 4.2 Gutgeschriebene Abwesenheiten`) ersetzen durch:

````markdown
### 4.1 Arbeitszeit-Blöcke und Kappung

Sind für den Tag Blöcke hinterlegt (`work_window_service.get_scheduled_blocks`, datumsaufgelöst über
`get_schedule_for_date`), kappt `work_window_service.clamp()` mit dem Puffer `g`
(`work_window_grace_minutes`, Default 15) und liefert `ClampResult(eff_start, eff_end, raw_start,
raw_end, uncredited_minutes, grace_minutes)`:

1. **Hülle:** Beginn vor `erster Block − g` wird auf diese Grenze verschoben, Ende nach
   `letzter Block + g` ebenso; die Rohstempel stehen in `raw_start_time`/`raw_end_time` (§16 ArbZG).
   Liegt der Eintrag ganz außerhalb der Hülle, wird er auf 0 h zusammengezogen (Beginn = Ende), die
   Rohstempel bleiben.
2. **Lücken:** Jede Lücke zwischen zwei Blöcken schrumpft um `g` an beiden Rändern (`credit_gaps`);
   eine Lücke ≤ 2 × g verschwindet. Die Überlappung des (an der Hülle gekappten) Eintrags mit den
   geschrumpften Lücken ist `uncredited_minutes` (je Lücke einzeln: `gap_segments`). Ein Beginn in
   der Lücke wird **nicht** verschoben (UNIQUE auf Beginn je Tag).
3. **Keine Kappung** (`uncredited_minutes` = 0, keine Rohstempel): Tag ohne Blöcke, Wochenende,
   Feiertag des Mandanten, Sondertag `free` (#484), `track_hours = false`, `credit_override`
   (anerkannt). Ein offener Eintrag (`end = None`) wird nur an der Hülle gekappt.
4. **Puffer je Eintrag:** Der angewandte Puffer steht in `clamp_grace_minutes`. Neuanlagen nehmen
   den aktuellen Mandanten-Puffer; jede Einzel-Neukappung eines gespeicherten Eintrags (Ausstempeln,
   Bearbeiten, Datumswechsel, Antragsgenehmigung, XLS-Überschreiben, Auto-Close) nimmt dessen
   gespeicherten Puffer (`grace_for_entry`; NULL bei Bestand vor 1.20.0 → aktueller Puffer). Nur die
   Massen-Neukappung einer Arbeitszeit-Änderung (TZ-G) nimmt den aktuellen Puffer und schreibt ihn neu.
5. **Auto-Close:** Ein offener Eintrag eines vergangenen Tages wird mit Ende 23:59 über `clamp`
   geschlossen (`auto_closed = true`); angerechnet wird bis `letzter Block + g`, 23:59 bleibt als
   `raw_end_time` stehen, gilt aber nicht als Stempel.

**Beispiele** (Blöcke Mo 08:00–12:00 + 15:00–18:00, Pause im Plan 0, g = 15 → Hülle 07:45–18:15,
Lücke 12:15–14:45):

| Fall | gestempelt | gespeichert | Rohstempel | `uncredited` | `net_hours` | nicht angerechnet |
|---|---|---|---|---|---|---|
| durchgestempelt | 08:00–18:00 | 08:00–18:00 | – | 150 | **7,50 h** | 150 |
| Ausstempeln 12:05 | 08:00–12:05 | 08:00–12:05 | – | 0 | 4,08 h | 0 |
| ganz in der Lücke | 12:30–14:30 | 12:30–14:30 | – | 120 | 0,00 h | 120 |
| Hülle und Lücke | 07:00–19:00 | 07:45–18:15 | 07:00 / 19:00 | 150 | 8,00 h | 240 |
| Pause 30 und Lücke | 08:00–18:00 | 08:00–18:00 | – | 150 | 7,00 h | 150 |
| vergessen auszustempeln (Auto-Close) | 08:00–offen | 08:00–18:15 | – / 23:59 | 150 | 7,75 h | 150 |
| anerkannt, Pause 45 | 08:00–18:00 | 08:00–18:00 | – | 0 | 9,25 h | 0 |

**„Nicht angerechnet"** (`work_window_service.not_credited_minutes`, Frontend-Zwilling
`utils/workBlocks.ts::notCreditedMinutes`) = `uncredited_minutes` + die an der Hülle abgeschnittenen
Minuten (`eff_start − raw_start`, `raw_end − eff_end`); beim Auto-Close zählt die Endseite nicht.
Diese Zahl steht unter dem Eintrag, im Monatsjournal („Anwesenheit nicht angerechnet") und in der
letzten Exportspalte „Nicht angerechnet (Min)".

**Anerkennen** (`credit_override = true`, `POST /admin/time-entries/{id}/credit-override`): Der
Eintrag bekommt seine Rohstempel als wirksame Zeiten, `uncredited_minutes` = 0, und wird von keiner
späteren Kappung mehr erfasst.

**ArbZG:** §3 und §4 rechnen hart auf der angerechneten Zeit; ein Lückensegment ≥ 15 Min zählt für
§4 als Pausenabschnitt (`validate_daily_break(…, uncredited_segments=…)`). Zusätzlich weiche
Hinweise auf der Anwesenheit laut Stempel (`presence_minutes` = `(raw_end or end) −
(raw_start or start) − Pause`, beim Auto-Close bis zum wirksamen Ende): `PRESENCE_DAILY_HOURS`
(> 10 h), `PRESENCE_BREAK` (> 6 h ohne ausreichende erfasste Pause), `PRESENCE_WEEKLY_HOURS`
(> 48 h je Kalenderwoche); `BREAK_IN_GAP`, wenn Pause **und** Lücke am selben Eintrag abgezogen
werden. §5 rechnet unverändert gegen die Rohstempel.

````

3. Im Absatz über die Per-Tag-Spalte „Netto (Std)" (beginnt mit `Die Regel gilt an **allen** Flächen, die die Gutschrift kennen:`) den Satz `„Angerechnet" heißt: bei Soll-Arbeitszeit-Fenster (#201) die **gekappte** Zeit — Von/Bis/Netto kommen aus `start_time`/`end_time`, die Rohstempel `raw_*` stehen bis heute in keiner Datei.` ersetzen durch:

```markdown
„Angerechnet" heißt: bei Arbeitszeit-Blöcken (§4.1) die gekappte Zeit nach Abzug der Lücke — Von/Bis kommen aus `start_time`/`end_time`, Netto aus `net_hours` (mit `uncredited_minutes`), die Rohstempel `raw_*` stehen in keiner Datei.
```

4. Im Absatz, der mit `Geteilte Dienste (#498):` beginnt, `und „Arbeitsblöcke" als Spalten 11/12 an,` → `und „Zeiteinträge" als Spalten 11/12 an,` und `Damit gilt je Zeile `Bis − Von − Pause − Unterbrechung = Netto` — **außer**` → `Damit gilt je Zeile `Bis − Von − Pause − Unterbrechung − Σ uncredited_minutes = Netto` — **außer**` (im Original steht `Damit gilt je Zeile` am Ende einer Zeile und die Formel am Anfang der nächsten; die neue Formel bleibt in einem Stück auf einer Zeile). Hinter das Absatzende (`… (Netto 0, Stempel sichtbar).`) einen neuen Absatz setzen:

```markdown

Seit 1.20.0 hängt jede Datei als letzte Spalte **„Nicht angerechnet (Min)"** an (XLSX/ODS Spalte 13,
PDF 12. Spalte mit Kopf „Nicht angerechnet / (Min)"): Σ `not_credited_minutes` der Einträge des
Tages in ganzen Minuten, Summenzeile = Σ Monat. In der Zeilenregel steht bewusst **nicht**
„− Nicht angerechnet": die Spalte enthält zusätzlich die an der Hülle abgeschnittenen Minuten, die in
Von/Bis schon fehlen. Beispiel Hülle und Lücke (§4.1): 18:15 − 07:45 = 10:30 h; − 150 Min = 8:00 h =
Netto; die Spalte zeigt 240.
```

- [ ] **Step 6: BERECHNUNGEN.md – TZ-E, TZ-G, Quellen**

1. TZ-E: nach dem Absatz, der mit `Die Segmente liefert `calculation_service.weekly_hours_segments(db, user, von, bis)`` beginnt und mit `ausgewiesen.` endet, einfügen:

```markdown

Seit 1.20.0 nennt der Text bei Arbeitszeit-Blöcken die Blöcke, sobald sie sich geändert haben
(`calculation_service.blocks_changed` neben `work_days_changed`, Frontend-Zwilling
`formatWeeklyHoursChanges` wortgleich): `ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) /
Di 08:00–13:00 = 11,5 h/Woche` (nur Tage mit Blöcken; „(Pause … Min)" nur bei Pause > 0). Ein
Altfenster steht als `… / Fr 07:30–23:59 (nur Kappung)`, ein Segment, das Blöcke entfernt, als
bisheriger Wortlaut plus „ · ohne Arbeitszeit-Blöcke"; PDF-Kurzform
`Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00`. Ohne Blockänderung bleibt der Text byte-identisch.
```

2. TZ-E: `„Wochenstunden anpassen…" mit Wirkungsdatum wie alle anderen.` → `„Arbeitszeit anpassen…" mit Wirkungsdatum wie alle anderen. Seit 1.20.0 läuft vor dieser Abwesenheits-Rückrechnung die Neukappung der Zeiteinträge (TZ-G), und eine rückwirkende Änderung, die das Überstundenkonto senkt, braucht Grund und Bestätigung.`
3. Nach dem Ende von `### TZ-F: Rückwirkende Tagesplan-Änderung (#431)` (vor der Trennlinie `---` und `## 15. Worked Example – Minijob (MiLoG-Fixmodus)`) einfügen:

````markdown

### TZ-G: Rückwirkende Änderung der Arbeitszeit-Blöcke (ab 1.20.0)

Heute ist Do 08.10.2026. Anna arbeitet seit 01.03.2026 mit Blöcken Mo 08:00–12:00 + 15:00–18:00,
Di 08:00–12:00, Do 08:00–12:00 (Pausen 0, Wochensoll 15,0 h); Puffer 15 Min. Im Wirkungsbereich ab
01.09. liegen fünf Montage: 07.09. (Urlaub), 14.09., 21.09., 28.09. (Nachmittag anerkannt), 05.10.;
gestempelt jeweils 08:00–12:00 und 15:00–18:00.

**Fall 1 — Verkürzung:** Mo 15:00–18:00 wird rückwirkend ab 01.09. auf 15:00–17:00 gekürzt
(Tagessoll Mo 7:00 → 6:00 h).

```
Nachmittag je Montag: 15:00–18:00 gegen Hülle bis 17:15 → 15:00–17:15, −0:45 h
3 Montage (14.09., 21.09., 05.10.)  → angerechnet −2:15 h   (28.09. anerkannt → übersprungen)
4 Montage × Tagessoll −1:00 h       → Soll −4:00 h          (07.09.: Urlaub zieht mit, saldo-neutral)
Überstunden +12:30 h → +14:15 h     → Δ +1:45 h
```

Drei Einträge verlieren angerechnete Zeit → **Verkürzung** (Kriterium a), obwohl der Saldo steigt.
`earliest_lossless_date` ist heute (kein Montag zwischen heute und dem Saldo-Stichtag), Standard also
„Ab heute (08.10.2026) wirksam"; rückwirkend nur mit Grund, Begründung und Bestätigung.

**Fall 2 — Verlängerung:** Mo 15:00–18:00 → 15:00–19:00 **und** Pause Mo 0 → 60 Min (Tagessoll
bleibt 7:00 h). Am 21.09. bis 18:30 gestempelt: 18:15 → 18:30, +0:15 h; der 14.09. (Ende 18:15 ohne
Rohstempel aus der Zeit vor 1.19.1) ist „nicht erweiterbar". Soll ±0, angerechnet +0:15 h,
Überstunden +0:15 h → keine Verkürzung, der Bestätigungshaken genügt.

**Fall 3 — rückwirkende Soll-Erhöhung:** wie Fall 2, aber Pause bleibt 0 (Tagessoll Mo 7:00 → 8:00 h):
angerechnet +0:15 h, Soll +4:00 h, Überstunden −3:45 h. Kein Eintrag verliert, aber das
Überstundenkonto sinkt → **Verkürzung** (Kriterium b); ohne Grund lehnt der Server die rückwirkende
Variante mit 400 ab.

**Klassifikation** (nach Neukappung **und** `retarget_absence_hours`):
- (a) ein Eintrag verliert angerechnete Zeit (beim heute offenen Eintrag: für irgendein mögliches Ende);
- (b) `saldo_delta_hours` < 0 — Σ (Ist − Soll) nachher minus vorher über die Monate des
  Wirkungsbereichs bis zum Saldo-Stichtag (#313, §7.4), ohne Jahresüberträge, über
  `get_monthly_target`/`get_monthly_actual`; zusätzlich `open_day_saldo_delta_hours` < 0 für den
  heute offenen Tag;
- (c) die F1-Klemmung in `retarget_absence_hours` senkt eine Abwesenheits-Gutschrift stärker als
  das Tagessoll des Tages.

`earliest_lossless_date = max(heute, letzter verlierender Eintrag + 1, letzte gesenkte Gutschrift + 1, H)`
mit H = morgen, wenn der heutige Tag schon Saldo verliert; liegt es am oder nach der nächsten Änderung,
gibt es keinen verlustfreien Standard. Eine rückwirkende Verkürzung in ein abgeschlossenes Jahr
(`YearCarryover` für das Folgejahr) ist gesperrt.

**Protokoll** (`reclamp_audit.summary_note`, Fall 1 rückwirkend gespeichert):

```
Arbeitszeit-Änderung ab 01.09.2026: 3 Einträge neu berechnet, Δ -135 Min, Saldo Δ +105 Min, 1 übersprungen (1 anerkannt) · Puffer 15 Min · Verkürzung · Grund: [Erfassungsfehler korrigiert] Mo-Nachmittagsblock war seit 01.09. mit 18:00 statt 17:00 hinterlegt · Vertrag: Mo 08:00–12:00+15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 → Mo 08:00–12:00+15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00
```

Dazu je neu gekapptem Eintrag eine Zeile `source = "wh_reclamp"` mit alten und neuen Zeiten und je
nachgezogener Abwesenheit eine `wh_change`-Zeile (Präfix „Arbeitszeit-Änderung ab …").
````

4. „Quellen im Code": die Zeile `| Arbeitszeit-Fenster | `services/work_window_service.py` |` ersetzen durch:

```markdown
| Arbeitszeit-Blöcke: `clamp`/`ClampResult`, `grace_for_entry`, `get_scheduled_blocks`, `credit_gaps`, `gap_segments`, `not_credited_minutes`, `presence_minutes`, Neukappung `reclamp_time_entries` | `services/work_window_service.py` |
| JSON-Form der Blöcke, `derive_targets` | `services/work_blocks_service.py` |
| Sammelzeile `summary_note`/`parse_summary_note`, Grundtypen `REASON_TYPES` | `services/reclamp_audit.py` |
```

- [ ] **Step 7: GLOSSAR.md**

1. Am Ende des Einleitungskastens (nach `… gilt jetzt für alle vier Größen gemeinsam.`) anfügen:

```markdown
>
> Seit 1.20.0 gehören auch die **Arbeitszeit-Blöcke** zu diesem Snapshot (§7).
```

2. Tabelle §1, Zeile **net_hours**: `| **net_hours** | Stunden | Brutto (Ende − Beginn) − Pause; `max(0, …)`. | `TimeEntry.net_hours` |` → `| **net_hours** | Stunden | (Ende − Beginn) − Pause − `uncredited_minutes` (nicht angerechnete Lückenzeit, §7); `max(0, …)`. | `TimeEntry.net_hours` |`
3. §6-Tabelle: nach der Zeile `| Stichtag „bis heute"? | `get_soll_cutoff_date()` |` anfügen:

```markdown
| Arbeitszeit-Blöcke an Datum X? | `work_window_service.get_scheduled_blocks()` (über `get_schedule_for_date()`, nie `users.work_blocks` direkt) |
| Wird an Datum X gekappt? | `work_window_service.clamp_applies()` |
| Nicht angerechnete Minuten eines Eintrags? | `work_window_service.not_credited_minutes()` |
```

4. Am Dateiende anfügen:

```markdown

---

## 7. Arbeitszeit-Blöcke und Anrechnung (ab 1.20.0)

| Begriff | Bedeutung | Maßgebliche Quelle |
|---------|-----------|--------------------|
| **Arbeitszeit-Block** | Vertraglich hinterlegter Zeitraum „von–bis" an einem Wochentag (Mo–Fr, höchstens 3 je Tag, Raster 5 Min). Teil des Vertrags-Snapshots `working_hours_changes.blocks`; `users.work_blocks` nur Rückfall vor der ersten Verlaufszeile. **Nicht** verwechseln mit einem **Zeiteintrag** (gestempelte Zeit). | `get_schedule_for_date().blocks` → `get_scheduled_blocks()` |
| **Pause innerhalb der Blöcke** | Geplante Pause (`pause_minutes`); Tagessoll = Σ Blöcke − Pause. NULL = Altfenster aus Migration 073 (nur Kappung, kein Soll). | `work_blocks_service.derive_targets()` |
| **Hülle** | Erster Block − Puffer bis letzter Block + Puffer; Beginn/Ende außerhalb werden verschoben, der Rohstempel bleibt. | `clamp()` |
| **Lücke** | Zeit zwischen zwei Blöcken, an beiden Rändern um den Puffer geschrumpft; eine Lücke ≤ 2 × Puffer verschwindet. Gestempelte Zeit darin ist `uncredited_minutes`. | `credit_gaps()` |
| **Puffer** | Toleranz an jedem Blockrand (Mandanten-Setting `work_window_grace_minutes`, Default 15); je Eintrag gespeichert (`clamp_grace_minutes`). | `get_grace_minutes()`, `grace_for_entry()` |
| **angerechnet** | Zeit, die ins Ist eingeht = `net_hours` (nach Pause und Lücke). | `TimeEntry.net_hours` |
| **nicht angerechnet** | Lücke **plus** an der Hülle abgeschnittene Zeit; ohne die synthetische 23:59 des Auto-Close. | `not_credited_minutes()` |
| **Anwesenheit laut Stempel** | `(raw_end or end) − (raw_start or start) − Pause`; Basis der weichen Hinweise `PRESENCE_*`. | `presence_minutes()` |
| **Anerkennen** | Verwaltung rechnet einen Eintrag ungekappt an (`credit_override`), dauerhaft, protokolliert (`source = "credit_override"`). | `POST /admin/time-entries/{id}/credit-override` |
| **Neukappung** | Neuberechnung erfasster Einträge nach einer rückwirkenden Arbeitszeit-Änderung – ab Rohstempel, nur geänderte Wochentage, aktueller Puffer; protokolliert als `wh_reclamp`. | `reclamp_time_entries()` |
| **Verkürzung** | Arbeitszeit-Änderung, bei der ein Eintrag angerechnete Zeit verliert, das Überstundenkonto sinkt oder eine Misch-Tag-Gutschrift stärker als das Tagessoll sinkt; rückwirkend nur mit Grund (Schutzpaket). | Vorschau `is_shortening` |

> **Stunden, nicht Tage:** Blöcke, Lücke und „nicht angerechnet" sind Stunden- bzw.
> Minutengrößen. Am Urlaub ändert sich dadurch nichts – er bleibt tagebasiert (§2); ein Wochentag
> ohne Block hat Tagessoll 0 und kostet keinen Urlaubstag.
```

- [ ] **Step 8: Prüfen**

Run: `bash scripts/check-doc-sync.sh berechnungen links`
Expected: `OK: berechnungen links`.

- [ ] **Step 9: Commit**

```bash
git add scripts/check-doc-sync.sh docs/BERECHNUNGEN.md docs/GLOSSAR.md
git commit -F - <<'EOF'
docs(berechnungen): Arbeitszeit-Blöcke, Kappung, Neukappung und Begriffe

BERECHNUNGEN: Tagesplan aus Blöcken (derive_targets, Rundung), net_hours
mit uncredited_minutes, Kappungsalgorithmus mit Beispieltabelle, Puffer je
Eintrag, Export-Zeilenregel mit Lücke, Berichtstext mit Blöcken, Worked
Example TZ-G (Verkürzung, Verlängerung, Soll-Erhöhung, Protokoll).
GLOSSAR: Abschnitt 7 mit Block, Lücke, Hülle, Puffer, angerechnet,
nicht angerechnet, Anerkennen, Neukappung, Verkürzung.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 8: In-App-Hilfe – DocViewer, Schnellstart, Kontexthilfe, Export-Hinweis ⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen

Sync-Flächen (2) und (5) (Spec 16.1). Jeder `<p>` im DocViewer steht auf **einer** Zeile; die Ersetzungen sind über den Zeilenanfang benannt.

**Files:**
- Create: `frontend/src/components/DocViewer.test.tsx`
- Modify: `frontend/src/components/DocViewer.tsx` (bei `3d46c2f`: MA-Kurzanleitung Zeilen 52–96, 144, 151; Admin-Kurzanleitung Zeilen 197–202, 233–236, 225–228; MA-Handbuch Zeilen 289–290, 324–333, 336–340, 360–364, 384–390; Admin-Handbuch Zeilen 421–437, 439–448, 450–458, 515–522, 525–531, 534–549, alle Titel ab Zeile 439; Schnellstart Zeilen 620–632)
- Modify: `frontend/src/constants/helpContent.tsx` (bei `3d46c2f`: `/time-tracking` Zeilen 33–75, `/profile` Zeilen 161–164, `/admin/users` Zeilen 198–216, `/admin/change-requests` Zeilen 260–283)
- Modify: `frontend/src/pages/admin/Reports.tsx` (bei `3d46c2f`: Liste „Was enthält der Export?" Zeilen 359–366)

**Interfaces:**
- Consumes: Exporte von `DocViewer.tsx`: `CheatsheetAdmin`, `CheatsheetMitarbeiter`, `SchnellstartAdmin`, `handbuchAdminSections`, `handbuchMitarbeiterSections`, Typ `AccordionItem`; `helpContent: Record<string, { title: string; content: ReactNode }>` aus `constants/helpContent.tsx`.
- Produces: Admin-Handbuch-Abschnitt „3. Arbeitszeit-Blöcke, Rückwirkung & Anerkennen" (Folgeabschnitte um eins hochgezählt, bis „15. Admin-Passwort verloren"); MA-Abschnitt „5. Arbeitszeit-Blöcke & Anrechnung"; Vitest `DocViewer.test.tsx`.

- [ ] **Step 1: Vitest schreiben**

`frontend/src/components/DocViewer.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  CheatsheetAdmin,
  CheatsheetMitarbeiter,
  SchnellstartAdmin,
  handbuchAdminSections,
  handbuchMitarbeiterSections,
  type AccordionItem,
} from './DocViewer';
import { helpContent } from '../constants/helpContent';

// Sichtbarer Text einer Doku-Fläche, Leerraum zusammengefasst.
function textOf(node: ReactNode): string {
  const { container, unmount } = render(<div>{node}</div>);
  const text = (container.textContent ?? '').replace(/\s+/g, ' ');
  unmount();
  return text;
}

function sectionsText(items: AccordionItem[]): string {
  return textOf(
    items.map((item) => (
      <section key={item.title}>
        <h2>{item.title}</h2>
        {item.content}
      </section>
    )),
  );
}

// Bedienung und Begriffe, die es seit 1.20.0 nicht mehr gibt (Spec E58, 12.2, 15.1).
const VERALTET = [
  'Wochenstunden anpassen…',
  'Wochenstunden & Tagesplan',
  'Soll-Beginn und Soll-Ende hinterlegen',
  'Soll-Beginn/-Ende je Wochentag',
  'erfassten Blöcke',
  'aller Blöcke des Tages',
  'vergessener Nachmittagsblock',
  'Fehlende Blöcke',
  'Spalte „Arbeitsblöcke"',
];

function expectNoStaleTerms(text: string) {
  for (const stale of VERALTET) expect(text).not.toContain(stale);
}

describe('In-App-Doku: Arbeitszeit-Blöcke (1.20.0)', () => {
  it('Admin-Handbuch beschreibt Dialog, Blöcke, Schutzpaket und Rechtshinweise', () => {
    const text = sectionsText(handbuchAdminSections);
    for (const expected of [
      '3. Arbeitszeit-Blöcke, Rückwirkung & Anerkennen',
      '15. Admin-Passwort verloren',
      'Arbeitszeit anpassen…',
      'Arbeitszeit & Wochenstunden',
      'Nach Arbeitsblöcken',
      'Pause innerhalb der Blöcke',
      'Tagessoll = Summe der Blockdauern − Pause innerhalb der Blöcke',
      '08:00–12:15 und 14:45–18:00 = 7:30 h',
      'Anerkennen',
      'Anrechnung anerkannt',
      'Neukappung (Arbeitszeit-Änderung)',
      'Nicht angerechnet (Min)',
      'genehmigen und anerkennen',
      'Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.',
      'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)',
      'Mit der beschäftigten Person vereinbart',
      '[Erfassungsfehler korrigiert]',
      'auf den vorherigen Stand zurücksetzen',
      'Eine Änderung des Puffers wirkt auf neue Einträge.',
      'Nichtanrechnung ersetzt keine Vergütungsentscheidung.',
      '§ 87 Abs. 1 Nr. 2 BetrVG',
      'PraxisZeit prüft das nicht.',
      'Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln',
      'Details in Abschnitt 9',
    ]) {
      expect(text).toContain(expected);
    }
    expectNoStaleTerms(text);
  });

  it('Mitarbeiter-Handbuch erklärt nicht angerechnete Zeit, Antrag und Profilkarte', () => {
    const text = sectionsText(handbuchMitarbeiterSections);
    for (const expected of [
      '5. Arbeitszeit-Blöcke & Anrechnung',
      '2:30 h zwischen den Blöcken nicht angerechnet',
      'Anrechnung beantragen',
      'Anerkannter Eintrag – Änderung bitte per Änderungsantrag.',
      'Pause zwischen den Arbeitsblöcken',
      'Meine Arbeitszeit',
      'Ihre Arbeitszeit wurde ab 01.09.2026 geändert',
      'Nicht angerechnet heißt nicht unbezahlt',
    ]) {
      expect(text).toContain(expected);
    }
    expectNoStaleTerms(text);
  });

  it('Kurzanleitungen und Schnellstart nennen Knopf, Modus und Anrechnung', () => {
    const admin = textOf(<CheatsheetAdmin />);
    for (const expected of ['Arbeitszeit anpassen…', 'Nach Arbeitsblöcken', 'Anerkennen', 'Nicht angerechnet (Min)']) {
      expect(admin).toContain(expected);
    }
    expectNoStaleTerms(admin);

    const ma = textOf(<CheatsheetMitarbeiter />);
    for (const expected of ['zwischen den Blöcken nicht angerechnet', 'Anrechnung beantragen', 'Meine Arbeitszeit']) {
      expect(ma).toContain(expected);
    }
    expectNoStaleTerms(ma);

    const start = textOf(<SchnellstartAdmin />);
    expect(start).toContain('Arbeitszeit anpassen…');
    expect(start).toContain('Nach Arbeitsblöcken');
    expectNoStaleTerms(start);
  });

  it('Kontexthilfe zu Benutzerverwaltung, Zeiterfassung, Profil und Anträgen ist nachgezogen', () => {
    const users = textOf(helpContent['/admin/users'].content);
    expect(users).toContain('Arbeitszeit anpassen…');
    expectNoStaleTerms(users);
    expect(textOf(helpContent['/time-tracking'].content)).toContain('Anrechnung beantragen');
    expect(textOf(helpContent['/profile'].content)).toContain('Meine Arbeitszeit');
    expect(textOf(helpContent['/admin/change-requests'].content)).toContain('genehmigen und anerkennen');
  });
});
```

- [ ] **Step 2: Test laufen lassen – muss scheitern**

Run (aus `frontend/`): `npx vitest run src/components/DocViewer.test.tsx --pool=threads`
Expected: 4 failed, u. a. `expected '…' to contain '3. Arbeitszeit-Blöcke, Rückwirkung & Anerkennen'` und `expected '…' not to contain 'Wochenstunden anpassen…'`.

- [ ] **Step 3: Mitarbeiter-Handbuch (`handbuchMitarbeiterSections`)**

1. Abschnitt „2. Dashboard & Saldo verstehen", Zeile `<p>Der <strong>Tagessaldo</strong> („x von y h heute") zählt …`: `heute erfassten Blöcke` → `heute erfassten Einträge`; vor `Auf dem Smartphone listet` einfügen: `In der geplanten Pause zwischen zwei Arbeitszeit-Blöcken zeigt die Karte neutral „Pause zwischen den Arbeitsblöcken". `
2. Gleicher Abschnitt, Zeile `<p><strong>Monats-/Wochenübersicht:</strong>`: `ein vergessener Nachmittagsblock` → `ein vergessener Nachmittags-Eintrag`. Danach eine Zeile einfügen:

```tsx
        <p><strong>Hinweis bei Änderungen Ihrer Arbeitszeit:</strong> Ändert die Verwaltung Ihre Arbeitszeit (Wochenstunden, Tagesplan oder Arbeitszeit-Blöcke), steht 30 Tage lang ein Hinweis auf dem Dashboard – auch bei einer erst künftig geltenden Änderung, z. B. <em>„Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00). 3 Einträge neu berechnet, angerechnete Zeit −2:15 h."</em> Einzelheiten unter Profil → „Meine Arbeitszeit".</p>
```

3. Den ganzen Eintrag mit `title: '5. Soll-Arbeitszeiten & Anrechnung',` (von `{` bis `},`) ersetzen durch:

```tsx
  {
    title: '5. Arbeitszeit-Blöcke & Anrechnung',
    content: (
      <div className="space-y-2">
        <p>Ihre Praxis kann Ihre Arbeitszeit je Wochentag als <strong>Arbeitszeit-Blöcke</strong> hinterlegen (z. B. Mo 08:00–12:00 und 15:00–18:00). Ihr Tagessoll ergibt sich dann aus den Blöcken; Ihre Blöcke und deren Verlauf zeigt <strong>Profil → „Meine Arbeitszeit"</strong>.</p>
        <p>Angerechnet wird Ihre gestempelte Zeit <strong>innerhalb</strong> der Blöcke, mit einem Puffer (Standard 15 Min.) an jedem Blockrand. Zu früh eingestempelt? Hinweis <em>„Du hast vor deinem Soll-Beginn eingestempelt – die Anrechnung beginnt ab dem frühestmöglichen Zeitpunkt."</em>, in der Eintragsliste <em>„gestempelt 07:30 · angerechnet ab 07:45"</em>. Über die Pause zwischen zwei Blöcken durchgestempelt (08:00–18:00 bei 08–12 und 15–18)? Dann steht dort <em>„gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet"</em>. In der Pause zwischen den Blöcken zeigt das Dashboard neutral „Pause zwischen den Arbeitsblöcken". An Wochenenden und Feiertagen gelten keine Blöcke – Arbeit dort (z. B. Notdienst) wird voll angerechnet.</p>
        <p>Beim <strong>Ausstempeln</strong> und beim Speichern eines eigenen Eintrags erscheint ein Hinweis, sobald etwas nicht angerechnet wird, z. B. <em>„Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."</em> Der Eintrag wird trotzdem gespeichert. Tragen Sie eine Pause ein, obwohl Sie über die Lücke durchgestempelt haben, wird beides abgezogen („Pause in der Lücke wird zusätzlich abgezogen …"). Ein vergessenes Ausstempeln wird über Nacht geschlossen und nur bis zum letzten Block plus Puffer angerechnet.</p>
        <p><strong>Dort gearbeitet?</strong> Am Eintrag <strong>„Anrechnung beantragen"</strong> wählen und kurz begründen. Genehmigt die Verwaltung, zählt die ganze gestempelte Zeit und der Eintrag ist „anerkannt". Anerkannte Einträge ändern Sie nur noch per Antrag („Anerkannter Eintrag – Änderung bitte per Änderungsantrag.").</p>
        <p className="text-gray-700">Ihre <strong>echte Stempelzeit geht nicht verloren</strong> (§16 ArbZG) – fürs Stundenkonto zählt die angerechnete Zeit. <strong>Nicht angerechnet heißt nicht unbezahlt:</strong> Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist zu vergüten (§ 611a, § 612 BGB; Mindestlohngesetz).</p>
      </div>
    ),
  },
```

4. Abschnitt „6. Korrekturanträge stellen & verwalten": nach der Zeile, die mit `<p>Den Status aller Anträge sehen Sie unter` beginnt, einfügen:

```tsx
        <p><strong>Anrechnung beantragen:</strong> Bei einem eigenen Eintrag mit nicht angerechneter Zeit (z. B. „2:30 h zwischen den Blöcken nicht angerechnet") stellen Sie über <strong>„Anrechnung beantragen"</strong> einen Antrag mit Begründung; bei einem automatisch geschlossenen Eintrag geben Sie dabei das tatsächliche Ende an. Für <strong>anerkannte</strong> Einträge gibt es statt „Bearbeiten" nur noch <strong>„Änderung beantragen"</strong>.</p>
```

5. Abschnitt „8. So werden Ihre Stunden & Ihr Urlaub berechnet": in der Zeile `<p><strong>Tagessoll</strong> = Wochenstunden ÷ Arbeitstage pro Woche …` vor `</p>` einfügen: ` Bei Arbeitszeit-Blöcken: Summe der Blöcke minus Pause innerhalb der Blöcke.`; in der Zeile `<p><strong>Ist</strong> = (Ende − Beginn) − Pause je Eintrag.` → `<p><strong>Ist</strong> = (Ende − Beginn) − Pause je Eintrag, abzüglich nicht angerechneter Zeit vor, nach oder zwischen Ihren Arbeitszeit-Blöcken.` (Rest der Zeile unverändert).
6. Abschnitt „10. Profil & Passwort": vor der Zeile, die mit `<p>Persönliche Daten wie Name und Wochenstunden` beginnt, einfügen:

```tsx
        <p><strong>Meine Arbeitszeit:</strong> Die Karte zeigt Ihre heute gültigen Arbeitszeit-Blöcke je Wochentag mit Tagessoll und den Verlauf mit Wirkungsdaten. Ohne Blöcke sehen Sie Tagessoll und Wochenstunden.</p>
```

- [ ] **Step 4: Admin-Handbuch (`handbuchAdminSections`)**

1. Titel hochzählen (je Zeile `title: '…'`): `'3. Berichte & Exporte'` → `'4. Berichte & Exporte'`, `'4. Korrekturanträge genehmigen'` → `'5. …'`, `'5. Urlaubsanträge & Betriebsferien'` → `'6. …'`, `'6. Sondertage 24./31.12.'` → `'7. …'`, `'7. Pflicht-Pause-Ausnahme (§4 ArbZG)'` → `'8. …'`, `'8. Eigene Abwesenheitsgründe, Kind krank & Minijob'` → `'9. …'`, `'9. ArbZG-Berichte & Compliance'` → `'10. …'`, `'10. Audit-Log & Fehler-Monitoring'` → `'11. …'`, `'11. Berechnungsgrundlagen (Soll, Ist, Überstunden, Urlaub)'` → `'12. …'`, `'12. Datensicherung (Backup & Restore)'` → `'13. …'`, `'13. Schichtplanung (optional)'` → `'14. …'`, `'14. Admin-Passwort verloren'` → `'15. Admin-Passwort verloren'`. Im (neu) Abschnitt 12 `Details in Abschnitt 8 „Eigene Abwesenheitsgründe, Kind krank & Minijob"` → `Details in Abschnitt 9 „Eigene Abwesenheitsgründe, Kind krank & Minijob"`.
2. Abschnitt „2. Benutzerverwaltung": die Zeile, die mit `<p>Für Teilzeit- und Tagesplan-Anpassungen: Benutzer öffnen` beginnt, ganz ersetzen durch:

```tsx
        <p>Arbeitszeit ändern (Teilzeit, Tagesplan, Blöcke): Benutzer öffnen → Button „<strong>Arbeitszeit anpassen…</strong>" (oder Uhr-Symbol in der Benutzerliste) → Dialog „<strong>Arbeitszeit &amp; Wochenstunden</strong>": <strong>„Gleichmäßig"</strong> (Wochenstunden + Arbeitstage pro Woche), <strong>„Nach Tagen"</strong> (Stunden je Wochentag Mo–Fr; Wochensumme und Arbeitstage werden abgeleitet) oder <strong>„Nach Arbeitsblöcken"</strong> (bis zu drei Blöcke je Wochentag + Pause innerhalb der Blöcke, siehe Abschnitt 3) + <strong>„Gültig ab"</strong>-Datum. Im Bearbeiten-Formular sind diese Angaben für <strong>alle</strong> Mitarbeitenden nur Anzeige („Arbeitszeit heute: …"); beim <strong>Anlegen</strong> sind es normale Felder bzw. der Block-Editor. Der Verlauf zeigt „ab … bis …" (z. B. „Mo 08:00–12:00 + 15:00–18:00 / Di 08:00–12:00 = 11,0 h/Woche" oder „Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 Std/Woche · 3 Tage/Woche"). Vor dem Speichern zeigt der Dialog die Auswirkung (neu berechnete Einträge, Abwesenheiten, Soll, angerechnete Zeit, Überstunden; Urlaubs<strong>tage</strong> bleiben unverändert); Rückwirkung, Verkürzungsschutz und Löschen beschreibt Abschnitt 3. Checkboxen: „ArbZG-Prüfungen aussetzen" für §18, „Nachtarbeitnehmer" für §6, „<strong>Nimmt an Betriebsferien teil</strong>" (Standard an, rollenunabhängig – für reine Verwaltungs-Accounts abwählbar), „Stundenzählung" aus für MA ohne Zeiterfassung (Urlaub/Krank zählen trotzdem tagebasiert).</p>
```

3. Gleicher Abschnitt: die Zeile, die mit `<p><strong>Soll-Arbeitszeiten (Arbeitszeit-Fenster):</strong>` beginnt, ganz ersetzen durch:

```tsx
        <p><strong>Arbeitszeit-Blöcke:</strong> Tagessoll, Kappung (auch zwischen den Blöcken), Anerkennen und Rückwirkung beschreibt Abschnitt 3. Frühere Soll-Fenster laufen als „Arbeitszeit-Fenster (Altbestand, nur Kappung)" weiter.</p>
```

4. Direkt nach dem Eintrag „2. Benutzerverwaltung" (nach dessen `},`) einen neuen Eintrag einfügen:

```tsx
  {
    title: '3. Arbeitszeit-Blöcke, Rückwirkung & Anerkennen',
    content: (
      <div className="space-y-2">
        <p><strong>Arbeitszeit-Blöcke (ab 1.20.0):</strong> Je Mitarbeiter:in und Wochentag (Mo–Fr) bis zu drei Blöcke „von–bis" (5-Minuten-Raster, nicht überlappend, nicht aneinanderstoßend) plus <strong>„Pause innerhalb der Blöcke"</strong>. <strong>Tagessoll = Summe der Blockdauern − Pause innerhalb der Blöcke</strong> (08:00–12:00 + 15:00–18:00 mit 30 Min. Pause = 6:30 h); Wochenstunden, Tagesstunden und Arbeitstage werden abgeleitet. Gepflegt nur mit Wirkungsdatum über <strong>„Arbeitszeit anpassen…"</strong> (Dialog <strong>„Arbeitszeit &amp; Wochenstunden"</strong>, Modus <strong>„Nach Arbeitsblöcken"</strong>); beim Anlegen steht derselbe Modus im Formular.</p>
        <p><strong>Anrechnung:</strong> Gestempelte Zeit vor dem ersten, nach dem letzten und zwischen den Blöcken wird nicht angerechnet – mit dem Puffer (Standard 15 Min.) an <strong>jedem</strong> Blockrand. Beispiel: Blöcke 08:00–12:00 + 15:00–18:00, durchgestempelt 08:00–18:00 → angerechnet <strong>08:00–12:15 und 14:45–18:00 = 7:30 h</strong>, die Lücke 12:15–14:45 (2:30 h) nicht; die Stempel bleiben gespeichert (§16 ArbZG). Eine Lücke bis zum doppelten Puffer wird voll angerechnet. Keine Kappung an Tagen ohne Block, an Wochenenden, Feiertagen, „freien" Sondertagen, bei Mitarbeitenden ohne Stundenzählung und bei anerkannten Einträgen; §18-befreite werden trotzdem gekappt. Ein vergessenes Ausstempeln (automatisch um 23:59 geschlossen) wird nur bis zum letzten Block plus Puffer angerechnet. Hinweis beim Speichern z. B. <em>„Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."</em> Frühere Soll-Fenster laufen als „Arbeitszeit-Fenster (Altbestand, nur Kappung)" weiter und lassen sich im Dialog umwandeln oder entfernen.</p>
        <p><strong>Sichtbar und anerkennbar:</strong> Unter jedem gekappten Eintrag (Admin-Dashboard, Monatsjournal, Zeiterfassung) steht z. B. <em>„gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet"</em>; das Journal summiert „Anwesenheit nicht angerechnet", die Exporte haben die letzte Spalte <strong>„Nicht angerechnet (Min)"</strong>. Mit <strong>„Anerkennen"</strong> (Admin-Dashboard-Detail, Monatsjournal) zählt die ganze gestempelte Zeit – dauerhaft, auch nach späteren Neuberechnungen, protokolliert als „Anrechnung anerkannt". Mitarbeitende beantragen das über „Anrechnung beantragen"; in der Antragsprüfung heißt Genehmigen dann Anerkennen, bei anderen Anträgen gibt es „genehmigen und anerkennen".</p>
        <p><strong>Rückwirkend ändern:</strong> Die Auswirkung zeigt vorab die neu berechneten Einträge je Monat (alt → neu), übersprungene Einträge mit Grund, angepasste Abwesenheiten und getrennt Δ Soll, Δ angerechnete Zeit und Δ Überstunden; der Haken „Ich habe die Auswirkungen geprüft und möchte speichern" ist Pflicht, sobald etwas betroffen ist. Neu gekappt wird ab dem Rohstempel, nur an geänderten Wochentagen und mit dem aktuellen Puffer; je Eintrag entsteht eine Protokollzeile „Neukappung (Arbeitszeit-Änderung)", je Änderung eine Sammelzeile. Mitarbeitende sehen 30 Tage lang einen Hinweis auf ihrem Dashboard.</p>
        <p className="text-amber-700"><strong>Verkürzung</strong> = ein Eintrag verliert angerechnete Zeit, <strong>oder</strong> das Überstundenkonto sinkt (auch durch ein rückwirkend höheres Soll), <strong>oder</strong> eine Misch-Tag-Gutschrift sinkt stärker als das Tagessoll. Standard ist dann „Ab heute (…) wirksam – vergangene Einträge bleiben unverändert". Rückwirkend nur mit Grund („Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)" / „Mit der beschäftigten Person vereinbart" / „Sonstiges"), Begründung und Bestätigung; im Protokoll als [Erfassungsfehler korrigiert] / [Einvernehmlich vereinbart] / [Sonstiges]. Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit. In abgeschlossene Jahre gesperrt. Seit 1.20.0 gilt das auch für eine rückwirkende Erhöhung der Wochenstunden, die das Konto senkt. Löschen einer verkürzenden Änderung: Standard „Ab … auf den vorherigen Stand zurücksetzen".</p>
        <p><strong>Puffer:</strong> Eine Änderung des Puffers wirkt auf neue Einträge. Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn, auch wenn er später bearbeitet wird; nur eine Arbeitszeit-Änderung mit Neuberechnung nimmt den dann gültigen Puffer.</p>
        <p className="text-gray-700"><strong>Vergütung:</strong> Nichtanrechnung ersetzt keine Vergütungsentscheidung. Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde oder zur Erledigung der Arbeit notwendig war, ist zu vergüten (§ 611a Abs. 2, § 612 Abs. 1 BGB; MiLoG). Wurde vor, nach oder zwischen den Blöcken gearbeitet, nutzen Sie „Anerkennen"; wurde nur ein Teil gearbeitet, den Eintrag aufteilen oder korrigieren statt die ganze Zeit anzuerkennen.</p>
        <p className="text-gray-700"><strong>Arbeitsrecht und Mitbestimmung:</strong> Ändert sich durch die Blöcke der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und braucht das Einverständnis der beschäftigten Person (sonst Änderungskündigung, § 2 KSchG; bei Teilzeit §§ 8, 9 TzBfG). Die Lage kann, soweit der Vertrag sie nicht festlegt, im Rahmen des Direktionsrechts (§ 106 GewO) nach billigem Ermessen und mit angemessener Ankündigung nur für die Zukunft geändert werden (Arbeit auf Abruf: mindestens 4 Tage vorher, § 12 Abs. 3 TzBfG). Vereinbarte Arbeitszeiten und Ruhepausen sind wesentliche Vertragsbedingungen (§ 2 Abs. 1 Satz 2 Nr. 7 NachwG); eine Änderung ist spätestens am Tag des Wirksamwerdens schriftlich mitzuteilen (§ 3 NachwG). Mit Betriebsrat sind Lage, Verteilung und Pausen (§ 87 Abs. 1 Nr. 2 BetrVG), vorübergehende Änderungen der betriebsüblichen Arbeitszeit (Nr. 3) und die Kappung als technische Einrichtung (Nr. 6) mitbestimmungspflichtig; ohne Zustimmung ist die Maßnahme gegenüber den Beschäftigten unwirksam. PraxisZeit prüft das nicht.</p>
        <p className="text-gray-500">Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG: 30 Min Pause ab 4,5 h, 60 Min ab 6 h, höchstens 4,5 h ohne Pause, Schichtzeit inklusive Lücke höchstens 10 h); PraxisZeit prüft diese nicht.</p>
      </div>
    ),
  },
```

5. Abschnitt „4. Berichte & Exporte": die Zeile, die mit `<p><strong>Tageszeilen lesen:</strong>` beginnt, ganz ersetzen durch:

```tsx
        <p><strong>Tageszeilen lesen:</strong> <strong>Netto</strong> ist die angerechnete Arbeitszeit der Zeiteinträge – bei Arbeitszeit-Blöcken die Zeit nach der Kappung („Von"/„Bis" zeigen die gekürzten Zeiten, Zeit zwischen den Blöcken ist abgezogen; der ursprüngliche Stempel bleibt in PraxisZeit gespeichert, steht aber nicht in der Datei). <strong>Differenz</strong> ist der Saldo des Tages – Netto plus Gutschrift für Krankheit/Fortbildung minus Soll; ein Krank- oder Fortbildungstag steht deshalb bei ±0, und die Summe der Spalte ergibt den „Saldo Monat". Ausnahme: Mitarbeitende mit fester Monatsarbeitszeit (Minijob-Modus) – dort ist nur die Zusammenfassung verbindlich. Bei <strong>geteilten Diensten</strong> (mehrere Einträge an einem Tag) zeigen Excel/ODS in „Von"/„Bis" den Rahmen des Tages und in den hinten angehängten Spalten <strong>Unterbrechung (Min)</strong> und <strong>Zeiteinträge</strong> die Zeit zwischen den Einträgen bzw. die einzelnen Einträge; damit gilt Bis − Von − Pause − Unterbrechung = Netto, solange nichts zwischen zwei Arbeitszeit-Blöcken gestempelt wurde (sonst ist Netto um diese Lückenzeit kleiner). Ausnahmen: Überschneiden sich zwei Einträge, zählt Netto die Überschneidung doppelt (die Spalte „Zeiteinträge" zeigt sie); läuft ein Eintrag noch, fehlt seine Zeit in Netto und in „Bis"; außerhalb des Beschäftigungszeitraums ist Netto 0. Im PDF stehen die Einträge in „Von"/„Bis" untereinander, die Unterbrechung direkt neben der Pause. Letzte Spalte in allen Formaten: <strong>Nicht angerechnet (Min)</strong> – Lücke plus vor dem ersten bzw. nach dem letzten Block abgeschnittene Zeit (Beispiel 07:00–19:00 bei Blöcken 08–12 + 15–18: Netto 8,00, Nicht angerechnet 240).</p>
```

6. Abschnitt „5. Korrekturanträge genehmigen": nach der Zeile, die mit `<p><strong>Mehrere Anträge auf einmal:</strong>` beginnt, einfügen:

```tsx
        <p><strong>Anrechnung beantragt (ab 1.20.0):</strong> Bei einem Antrag „Anrechnung beantragen" bedeutet Genehmigen <strong>Anerkennen</strong> – die ganze gestempelte Zeit des Eintrags zählt, dauerhaft. Bei anderen Anträgen zu Einträgen mit nicht angerechneter Zeit gibt es zusätzlich <strong>„genehmigen und anerkennen"</strong>. Ist der Eintrag schon anerkannt, zeigt die Prüfung „Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet."</p>
```

7. Abschnitt „10. ArbZG-Berichte & Compliance": nach der Zeile, die mit `<p className="text-amber-700"><strong>§3 Tageshöchstgrenze (10h):</strong>` beginnt, einfügen:

```tsx
        <p><strong>Angerechnet vs. laut Stempel (ab 1.20.0):</strong> Die §3- und §4-Sperren rechnen mit der angerechneten Zeit; eine Lücke ab 15 Min. zwischen zwei Arbeitszeit-Blöcken zählt als Pause. Zusätzlich weisen Hinweise auf die <strong>Anwesenheit laut Stempel</strong> hin (über 10 h am Tag, durchgestempelt ohne Pause, über 48 h in der Woche) sowie auf „Pause in der Lücke wird zusätzlich abgezogen". Die 24-Wochen-Auswertung zeigt neben dem Durchschnitt einen zweiten Wert „Anwesenheit laut Stempel". Für Jugendliche (JArbSchG) prüft PraxisZeit nichts davon.</p>
```

8. Abschnitt „11. Audit-Log & Fehler-Monitoring": `(Zeiteinträge, Abwesenheiten, Korrekturanträge, Stundenänderungen, DSGVO-Vorgänge)` → `(Zeiteinträge, Abwesenheiten, Korrekturanträge, Arbeitszeit-Änderungen mit „Neukappung (Arbeitszeit-Änderung)" je neu berechnetem Eintrag und einer Sammelzeile je Änderung, Anerkennungen als „Anrechnung anerkannt", Stundenänderungen, DSGVO-Vorgänge)`
9. Abschnitt „12. Berechnungsgrundlagen …": In der Zeile `<p><strong>Tagessoll</strong> = Wochenstunden ÷ Arbeitstage pro Woche – der Divisor …` vor `</p>` einfügen: ` Bei <strong>Arbeitszeit-Blöcken</strong>: Summe der Blöcke − Pause innerhalb der Blöcke (08–12 + 15–18, Pause 30 Min. = 6,50 h).`; in der Zeile `<p><strong>Ist</strong> = (Ende − Beginn) − Pause, nie negativ.` den Satz `Ein Soll-Arbeitszeit-Fenster kürzt die Anrechnung auf das Fenster (± Puffer); der Rohstempel bleibt erhalten (§16 ArbZG).` ersetzen durch `Arbeitszeit-Blöcke kürzen die Anrechnung: vor dem ersten, nach dem letzten und zwischen den Blöcken zählt Zeit nur bis zum Puffer; nicht angerechnete Lückenzeit wird abgezogen, der Rohstempel bleibt erhalten (§16 ArbZG), anerkannte Einträge zählen voll.`

- [ ] **Step 5: Kurzanleitungen und Schnellstart**

1. `CheatsheetMitarbeiter`, Abschnitt „⏱️ Zeiterfassung": nach dem `<div>`-Block mit `<p className="text-sm font-medium text-gray-700 mb-1">Tagesgrenze (§3 ArbZG)</p>` (er endet mit `</ul>` und `</div>`) einfügen:

```tsx
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Arbeitszeit-Blöcke</p>
            <ul className="text-sm text-gray-600 space-y-0.5">
              <li>Nur wenn die Praxis Blöcke hinterlegt hat (Profil → „Meine Arbeitszeit").</li>
              <li>Angerechnet wird innerhalb der Blöcke, mit Puffer (Std. 15 Min.) an jedem Blockrand.</li>
              <li>Über die Pause zwischen zwei Blöcken gestempelt → „gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet".</li>
              <li>Dort gearbeitet? Am Eintrag <strong>„Anrechnung beantragen"</strong>. Anerkannte Einträge nur per „Änderung beantragen".</li>
            </ul>
          </div>
```

2. `CheatsheetMitarbeiter`, Tabelle „📊 Dashboard verstehen": `Heute: Ist aller Blöcke des Tages (z. B. Vormittag + Nachmittag) vs. Tagessoll (grün = eingestempelt)` → `Heute: Ist aller Einträge des Tages (z. B. Vormittag + Nachmittag) vs. Tagessoll (grün = eingestempelt)`; in der Zeile `<strong>Monat ↔ Woche:</strong> …` `Fehlende Blöcke fallen pro Woche sofort auf.` → `Fehlende Einträge fallen pro Woche sofort auf.`
3. `CheatsheetAdmin`, Abschnitt „👤 Benutzerverwaltung": den `<div>`-Block, der mit `<p className="text-sm font-medium text-gray-700 mb-1">Stundenänderung</p>` beginnt (bis einschließlich seiner Zeile `⚠️ Arbeitstage-only-Änderung …` und `</div>`), ersetzen durch:

```tsx
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Arbeitszeit ändern</p>
            <p className="text-sm text-gray-600">Benutzer bearbeiten → Button „Arbeitszeit anpassen…" (oder Uhr-Symbol in der Liste) → Dialog „Arbeitszeit &amp; Wochenstunden": „Gleichmäßig", „Nach Tagen" oder „Nach Arbeitsblöcken" (bis zu 3 Blöcke je Wochentag + Pause innerhalb der Blöcke; Tagessoll = Σ Blöcke − Pause) + „Gültig ab". Im Formular nur Anzeige („Arbeitszeit heute: …"), beim Anlegen normale Felder bzw. Block-Editor.</p>
            <p className="text-sm text-gray-600">Vorab die Auswirkung prüfen (Einträge je Monat alt → neu, Abwesenheiten, Δ Soll / Δ angerechnet / Δ Überstunden). Rückwirkend werden Einträge an geänderten Wochentagen ab Rohstempel neu gekappt, danach Abwesenheits-Stunden aufs neue Tagessoll (Urlaubstage bleiben).</p>
            <p className="text-sm text-amber-700">⚠️ Verkürzung (Eintrag verliert Zeit, Konto sinkt – auch durch höheres Soll – oder Misch-Tag-Gutschrift sinkt stärker als das Tagessoll): Standard „Ab heute"; rückwirkend nur mit Grund, Begründung und Haken; in abgeschlossene Jahre gesperrt. Löschen: Standard „auf den vorherigen Stand zurücksetzen". Falsche Stempel am Zeiteintrag korrigieren, nicht über die Arbeitszeit.</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">Nicht angerechnete Zeit</p>
            <p className="text-sm text-gray-600">Zeit vor, nach und zwischen den Blöcken zählt nur bis zum Puffer (an jedem Blockrand). Sichtbar am Eintrag, im Journal („Anwesenheit nicht angerechnet") und in der Export-Spalte „Nicht angerechnet (Min)". Geleistete Arbeit: <strong>„Anerkennen"</strong> (Admin-Dashboard-Detail, Monatsjournal) – dauerhaft, protokolliert. Nichtanrechnung ersetzt keine Vergütungsentscheidung.</p>
          </div>
```

4. `CheatsheetAdmin`, Abschnitt „✅ Korrekturanträge prüfen": nach `<li>Genehmigen oder Ablehnen (mit optionalem Grund)</li>` einfügen: `<li>„Anrechnung beantragen": Genehmigen = Anerkennen; sonst ggf. „genehmigen und anerkennen"</li>`
5. `CheatsheetAdmin`, Abschnitt „📊 Berichte & Exporte": vor `<p className="text-sm text-gray-500 mt-2">Aufbewahrungspflicht: 2 Jahre (§16 ArbZG)</p>` einfügen: `<p className="text-sm text-gray-500 mt-2">Letzte Spalte aller Formate: „Nicht angerechnet (Min)" (Lücke + vor/nach den Blöcken abgeschnittene Zeit).</p>`
6. `SchnellstartAdmin`, Abschnitt „2. Mitarbeiter anlegen": `<li>Optional: Soll-Arbeitszeit-Fenster (Soll-Beginn/-Ende je Wochentag).</li>` → `<li>Optional: Arbeitszeit-Blöcke – Modus „Nach Arbeitsblöcken" (je Wochentag bis zu drei Blöcke + Pause innerhalb der Blöcke; daraus Tagessoll und Anrechnung).</li>`; `<li>Spätere Änderungen an Wochenstunden, Tagesplan, Modus oder Arbeitstagen: nur noch über „Wochenstunden anpassen…" mit Wirkungsdatum.</li>` → `<li>Spätere Änderungen an Wochenstunden, Tagesplan, Blöcken, Modus oder Arbeitstagen: nur noch über „Arbeitszeit anpassen…" mit Wirkungsdatum.</li>`
7. `SchnellstartAdmin`, Abschnitt „3. Betrieb": vor `</p>` der Zeile `Mitarbeiter stempeln/erfassen; …` einfügen: ` Nicht angerechnete Zeit (vor, nach oder zwischen den Arbeitszeit-Blöcken) steht am Eintrag; geleistete Arbeit dort „Anerkennen".`
8. `SchnellstartAdmin`, Abschnitt „1. Praxis konfigurieren", Zeile `<p …><strong>Feste Monatsarbeitszeit (Minijob-Modus, #377 Baustein 2b):</strong> …`: `ausschließlich über „Wochenstunden anpassen…" (Modus „Nach Tagen")` → `ausschließlich über „Arbeitszeit anpassen…" (Modus „Nach Tagen")`.

Run (Repo-Wurzel): `grep -nF -e 'Wochenstunden anpassen' -e 'Wochenstunden &amp; Tagesplan' frontend/src/components/DocViewer.tsx frontend/src/constants/helpContent.tsx`
Expected: keine Ausgabe.

- [ ] **Step 6: Kontexthilfe und Export-Hinweis**

1. `frontend/src/constants/helpContent.tsx`, Eintrag `'/admin/users'`: `<li>Wochenstunden, Arbeitstage, Urlaubstage festlegen</li>` → `<li>Wochenstunden/Arbeitstage, Tagesplan oder Arbeitszeit-Blöcke sowie Urlaubstage festlegen</li>`; den `<section>`-Block mit `<h3 …>Stundenänderung (Teilzeit)</h3>` ersetzen durch:

```tsx
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Arbeitszeit ändern</h3>
          <p className="text-sm text-gray-600">Benutzer bearbeiten → <span className="font-medium">„Arbeitszeit anpassen…"</span> → Gültig ab + Modus (Gleichmäßig / Nach Tagen / Nach Arbeitsblöcken) → Auswirkung prüfen → Speichern. Rückwirkende Verkürzungen nur mit Grund und Bestätigung; historische Salden bleiben korrekt.</p>
        </section>
```

2. Eintrag `'/time-tracking'`: vor dem `<section>`-Block mit `<h3 …>Wochenansicht</h3>` einfügen:

```tsx
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Nicht angerechnete Zeit</h3>
          <p className="text-sm text-gray-600">Zeit vor, nach oder zwischen Ihren Arbeitszeit-Blöcken steht unter dem Eintrag als „nicht angerechnet". Haben Sie dort gearbeitet: am Eintrag <span className="font-medium">„Anrechnung beantragen"</span>.</p>
        </section>
```

3. Eintrag `'/profile'`: `Persönliche Daten (Name, Wochenstunden) können nur vom Admin geändert werden.` → `Persönliche Daten (Name, Wochenstunden) können nur vom Admin geändert werden. Ihre Arbeitszeit-Blöcke und deren Verlauf zeigt die Karte „Meine Arbeitszeit".`
4. Eintrag `'/admin/change-requests'`: vor dem `<section>`-Block mit `<h3 …>Bei Ablehnung</h3>` einfügen:

```tsx
        <section>
          <h3 className="font-semibold text-gray-800 mb-2">Anrechnung beantragt</h3>
          <p className="text-sm text-gray-600">Bei „Anrechnung beantragen" heißt Genehmigen Anerkennen (die ganze gestempelte Zeit zählt). Für andere Anträge zu Einträgen mit nicht angerechneter Zeit gibt es zusätzlich „genehmigen und anerkennen".</p>
        </section>
```

5. `frontend/src/pages/admin/Reports.tsx`, Liste unter `Was enthält der Export?`: zuerst prüfen `grep -nF -e 'Nicht angerechnet (Min)' frontend/src/pages/admin/Reports.tsx`. Ohne Treffer nach `<li>Tägliche Zeiteinträge (Datum, Von, Bis, Pause, Netto)</li>` einfügen: `<li>Letzte Spalte „Nicht angerechnet (Min)": gestempelte, nicht angerechnete Zeit (vor, nach und zwischen den Arbeitszeit-Blöcken)</li>`.

- [ ] **Step 7: Tests, Typen, Lint**

Run (aus `frontend/`):
- `npx vitest run src/components/DocViewer.test.tsx --pool=threads` → Expected: `4 passed`
- `npx tsc --noEmit` → Expected: keine Ausgabe, Exit 0
- `npx eslint src/components/DocViewer.tsx src/components/DocViewer.test.tsx src/constants/helpContent.tsx src/pages/admin/Reports.tsx` → Expected: keine Fehler

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/DocViewer.tsx frontend/src/components/DocViewer.test.tsx frontend/src/constants/helpContent.tsx frontend/src/pages/admin/Reports.tsx
git commit -F - <<'EOF'
docs(in-app): Hilfe, Kurzanleitungen und Schnellstart beschreiben Arbeitszeit-Blöcke

DocViewer: neuer Admin-Abschnitt 3 „Arbeitszeit-Blöcke, Rückwirkung &
Anerkennen" (Folgeabschnitte hochgezählt) mit Vergütungs-, Mitbestimmungs-
und JArbSchG-Hinweis; MA-Abschnitt 5 „Arbeitszeit-Blöcke & Anrechnung",
Dashboard-Hinweis, Profilkarte, „Anrechnung beantragen"; Kurzanleitungen,
Schnellstart, Kontexthilfe und Export-Hinweis nachgezogen. Vitest sichert
Pflichtbegriffe und verbietet die alte Bedienung („Wochenstunden anpassen…").

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 9: Demo-Person mit Blöcken und Screenshots 16/17

Spec 16.1 „Screenshots": `docs/handbuch/screenshots/16-*.png`, `17-*.png` neu, Demo-Person mit Blöcken in `create_handbuch_testdata.py` (`set_superadmin_context`, `TENANT_ID`). Das Seed-Skript läuft nur gegen PostgreSQL (rohe `::changerequesttype`-Casts); geprüft wird deshalb am laufenden Dev-Stack.

**Files:**
- Modify: `backend/create_handbuch_testdata.py` (bei `3d46c2f`: Imports Zeilen 13–20, Mitarbeiterin `sarah.klein` Zeilen 55–67, `create_employees` Zeilen 109–143, `create_time_entries_for_user` Zeilen 192–212)
- Modify: `e2e/capture-handbook-screenshots.ts` (Screenshots 16 und 17, bei `3d46c2f` Zeilen 163–187)
- Modify: `tools/handbook/handbuch-screenshots.js` (Screenshots 16 und 17, bei `3d46c2f` Zeilen 174–196)
- Modify: `docs/handbuch/HANDBUCH-ERSTELLEN.md` (Tabellenzeilen 16 und 17, bei `3d46c2f` Zeilen 78–79)
- Modify: `docs/handbuch/screenshots/16-admin-benutzer-formular.png`, `docs/handbuch/screenshots/17-admin-benutzer-bearbeiten.png`
- Modify: `docs/handbuch/screenshots/10-ma-profil.png` (PR2-Gesamtreview Fund 10: seit PR2 ohne „Wochenstunden" in den persönlichen Daten, dafür mit der Karte „Meine Arbeitszeit"; das Aufnahmeskript nimmt das Bild ohnehin neu auf — nur behalten statt verwerfen)

**Interfaces:**
- Consumes: `app.services.work_blocks_service.derive_targets(week_blocks: list[dict]) -> dict` (Schlüssel `hours_monday` … `hours_friday`, `weekly_hours`, `work_days_per_week`, `use_daily_schedule`; PR3); `app.services.work_window_service.get_grace_minutes(db, tenant_id) -> int` und `clamp(db, user, d, start, end, grace, *, credit_override: bool) -> ClampResult` (PR1); Spalten `users.work_blocks`, `time_entries.uncredited_minutes`, `time_entries.clamp_grace_minutes` (PR1).
- Produces: Demo-Mitarbeiterin `sarah.klein` mit Blöcken Mo–Fr 08:00–12:00 + 15:00–16:00 (Pause 0, Tagessoll 5,00 h, 25,00 h/Woche) und zwei über die Lücke durchgestempelten Montagen (09.02.2026, 23.02.2026, je `uncredited_minutes = 150`); Screenshots 16 (Anlegen im Modus „Nach Arbeitsblöcken") und 17 (Bearbeiten mit „Arbeitszeit heute: …").

- [ ] **Step 1: Seed – Blöcke für die Demo-Person**

In `backend/create_handbuch_testdata.py`:

1. Nach `from app.services import auth_service` ergänzen:

```python
from app.services import work_window_service
from app.services.work_blocks_service import derive_targets
```

2. Im Dict von `sarah.klein` nach `"exempt_from_arbzg": False,` einfügen:

```python
        # 1.20.0: Demo für Handbuch-Screenshots 16/17 — Vormittag + Nachmittag mit
        # Mittagslücke; Tagessoll 4 h + 1 h = 5 h, also unverändert 25 h/Woche.
        "work_blocks": [
            {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "16:00"}],
             "pause_minutes": 0}
            for _ in range(5)
        ],
```

3. Vor `def create_employees` (bzw. direkt nach den Konstanten `START_DATE`/`END_DATE`) einfügen:

```python
# Tage, an denen die Demo-Person über die Mittagslücke durchstempelt — erzeugt die
# Zusatzzeile „… zwischen den Blöcken nicht angerechnet" im Handbuch.
BLOCK_DEMO_THROUGH_DAYS = {date(2026, 2, 9), date(2026, 2, 23)}


def _apply_work_blocks(db, user: User, emp: dict) -> None:
    """Setzt Arbeitszeit-Blöcke samt abgeleitetem Soll (Spec 4.1, E9).

    ``users.work_blocks`` ist der Rückfall vor der ersten Verlaufszeile — die
    Demo-Person hat keine Verlaufszeile, also gelten diese Blöcke für den ganzen
    Demo-Zeitraum. Soll-Felder über ``derive_targets`` wie im Anlege-Pfad, damit
    Blöcke und Tagessoll zusammenpassen."""
    blocks = emp.get("work_blocks")
    if not blocks:
        return
    user.work_blocks = blocks
    for field, value in derive_targets(blocks).items():
        setattr(user, field, value)
    db.commit()


def create_block_entries_for_user(db, user: User, work_days: list) -> int:
    """Je Arbeitstag ein Eintrag je Block; an BLOCK_DEMO_THROUGH_DAYS ein Eintrag
    vom ersten Blockbeginn bis zum letzten Blockende. Gekappt über den echten
    ``clamp`` (Puffer aus den Einstellungen), wie jeder Schreibpfad es tut."""
    grace = work_window_service.get_grace_minutes(db, TENANT_ID)
    count = 0
    for d in work_days:
        day_blocks = user.work_blocks[d.weekday()]["blocks"]
        if not day_blocks:
            continue
        if d in BLOCK_DEMO_THROUGH_DAYS:
            spans = [(day_blocks[0]["start"], day_blocks[-1]["end"])]
        else:
            spans = [(b["start"], b["end"]) for b in day_blocks]
        for start_s, end_s in spans:
            r = work_window_service.clamp(
                db, user, d, dt_time.fromisoformat(start_s), dt_time.fromisoformat(end_s),
                grace, credit_override=False,
            )
            db.add(TimeEntry(
                tenant_id=TENANT_ID, user_id=user.id, date=d,
                start_time=r.eff_start, end_time=r.eff_end,
                raw_start_time=r.raw_start, raw_end_time=r.raw_end,
                uncredited_minutes=r.uncredited_minutes,
                clamp_grace_minutes=r.grace_minutes,
                break_minutes=0, note="",
            ))
            count += 1
    db.commit()
    return count
```

4. In `create_employees`: im Zweig `if existing:` vor `created.append(existing)` die Zeile `_apply_work_blocks(db, existing, emp)` einfügen; nach `db.refresh(u)` die Zeile `_apply_work_blocks(db, u, emp)` einfügen.
5. In `create_time_entries_for_user` direkt nach der Zuweisung `work_days = working_days_in_range(START_DATE, END_DATE, holiday_dates, user.work_days_per_week)` einfügen:

```python
    if getattr(user, "work_blocks", None):
        count = create_block_entries_for_user(
            db, user, [d for d in work_days if d not in absence_dates])
        print(f"    ✓ {count} Zeiteinträge nach Arbeitszeit-Blöcken erstellt")
        return
```

Run: `python3 -m py_compile backend/create_handbuch_testdata.py && echo kompiliert`
Expected: `kompiliert`.

- [ ] **Step 2: Dev-Stack mit PR1–PR3 bauen und Seed laufen lassen**

```bash
docker compose build backend frontend
docker compose up -d
docker compose exec -T backend python -c "from alembic.config import main; main(['current'])" </dev/null
```

Expected: letzte Zeile enthält `073_work_blocks (head)`.

```bash
docker compose cp backend/create_handbuch_testdata.py backend:/app/create_handbuch_testdata.py
docker compose exec -T backend python create_handbuch_testdata.py </dev/null
docker compose exec -T db psql -U praxiszeit -d praxiszeit -c "SELECT te.date, te.start_time, te.end_time, te.uncredited_minutes, te.clamp_grace_minutes FROM time_entries te JOIN users u ON u.id = te.user_id WHERE u.username = 'sarah.klein' AND te.uncredited_minutes > 0 ORDER BY te.date;" </dev/null
docker compose exec -T db psql -U praxiszeit -d praxiszeit -c "SELECT username, weekly_hours, work_days_per_week, use_daily_schedule, hours_monday FROM users WHERE username = 'sarah.klein';" </dev/null
```

Expected: Seed endet mit `✅ Testdaten erfolgreich erstellt!` und der Zeile `✓ … Zeiteinträge nach Arbeitszeit-Blöcken erstellt` bei Sarah Klein; die erste Abfrage liefert genau zwei Zeilen (`2026-02-09` und `2026-02-23`, je `08:00:00 | 16:00:00 | 150 | 15`); die zweite `sarah.klein | 25.00 | 5 | t | 5.00`. Hinweis: Das Seed-Skript setzt das Dev-Admin-Passwort auf `Admin2026!`.

- [ ] **Step 3: Aufnahmeskripte auf die Demo-Person ausrichten**

1. `e2e/capture-handbook-screenshots.ts`, Block `// 16 Neuer-Benutzer-Formular`: nach `await page.waitForTimeout(500);` (vor `await shot(page, '16-admin-benutzer-formular');`) einfügen:

```ts
    // 1.20.0: Block-Editor zeigen (Modus „Nach Arbeitsblöcken").
    const blockMode = page.getByText('Nach Arbeitsblöcken', { exact: true }).first();
    if (await blockMode.isVisible().catch(() => false)) {
      await blockMode.click();
      await page.waitForTimeout(300);
    }
```

2. Gleiche Datei, Block `// 17 Benutzer bearbeiten (click erster User-Row)`: Kommentar → `// 17 Benutzer bearbeiten — Demo-Person mit Arbeitszeit-Blöcken (Sarah Klein)`; die Zeile `const editBtn = page.getByRole('button', { name: /bearbeiten/i }).first();` ersetzen durch:

```ts
    const kleinRow = page.getByRole('row', { name: /Klein/ }).first();
    const editBtn = (await kleinRow.isVisible().catch(() => false))
      ? kleinRow.getByRole('button', { name: /bearbeiten/i }).first()
      : page.getByRole('button', { name: /bearbeiten/i }).first();
```

3. `tools/handbook/handbuch-screenshots.js`, Block `// 16 Neuen Benutzer anlegen`: nach `await sleep(1000);` (vor `await shot(ap, '16-admin-benutzer-formular.png', true);`) einfügen:

```js
    await ap.evaluate(() => {
      const el = [...document.querySelectorAll('label, button')]
        .find(e => e.textContent.trim() === 'Nach Arbeitsblöcken');
      if (el) el.click();
    });
    await sleep(500);
```

4. Gleiche Datei, Block `// 17 Einen Benutzer bearbeiten`: den `try { … } catch(e) { … }`-Block (Schleife über alle Buttons) ersetzen durch:

```js
    try {
      const clicked = await ap.evaluate(() => {
        const row = [...document.querySelectorAll('tr')].find(tr => tr.textContent.includes('Klein'));
        const btn = row && [...row.querySelectorAll('button')].find(b =>
          (b.getAttribute('aria-label') || b.title || b.textContent || '').includes('Bearbeiten'));
        if (btn) { btn.click(); return true; }
        return false;
      });
      if (!clicked) console.log('  ~ Zeile „Klein" mit Bearbeiten-Button nicht gefunden');
      await sleep(1000);
    } catch(e) { console.log('  ~ Kein Bearbeiten-Button gefunden'); }
```

5. `docs/handbuch/HANDBUCH-ERSTELLEN.md`: `| `16-admin-benutzer-formular.png` | `/admin/users` | Formular „Neuer Mitarbeiter:in" |` → `| `16-admin-benutzer-formular.png` | `/admin/users` | Formular „Neuer Mitarbeiter:in", Modus „Nach Arbeitsblöcken" (Block-Editor) |`; `| `17-admin-benutzer-bearbeiten.png` | `/admin/users` | Bearbeiten-Formular eines Benutzers |` → `| `17-admin-benutzer-bearbeiten.png` | `/admin/users` | Bearbeiten-Formular der Demo-Person mit Arbeitszeit-Blöcken (Sarah Klein, „Arbeitszeit heute: …") |`

- [ ] **Step 4: Screenshots aufnehmen und prüfen**

```bash
cd e2e && npx --yes tsx capture-handbook-screenshots.ts; cd ..
git status --short docs/handbuch/screenshots
```

Expected: `✓ 10-ma-profil.png`, `✓ 16-admin-benutzer-formular.png` und `✓ 17-admin-benutzer-bearbeiten.png` in der Ausgabe; `git status` zeigt geänderte PNGs.

Alle drei Bilder mit dem Read-Werkzeug ansehen:
- `docs/handbuch/screenshots/10-ma-profil.png` zeigt das Profil mit den persönlichen Daten ohne „Wochenstunden" (Rolle, Urlaubstage, Status) und darunter die Karte „Meine Arbeitszeit" (Wochenstunden mit Dezimalkomma, z. B. „Wochenstunden: 38,5").
- `docs/handbuch/screenshots/16-admin-benutzer-formular.png` zeigt das Anlegeformular mit den Modi „Gleichmäßig / Nach Tagen / Nach Arbeitsblöcken" und dem Block-Editor („von–bis", „+ Block", „Pause innerhalb der Blöcke").
- `docs/handbuch/screenshots/17-admin-benutzer-bearbeiten.png` zeigt das Bearbeiten-Formular von Sarah Klein mit „Arbeitszeit heute: Mo 08:00–12:00 + 15:00–16:00 …" und dem Knopf „Arbeitszeit anpassen…".

Zeigt eines der Bilder etwas anderes (z. B. andere Modusbeschriftung im Anlegeformular): Selektor in Step 3 an die echte Beschriftung anpassen und Step 4 wiederholen; weicht die Beschriftung von „Nach Arbeitsblöcken" ab, gilt das Abweichungsverfahren aus Task 0 Step 3.

Nur 10, 16 und 17 gehören in diesen PR; die übrigen neu aufgenommenen Bilder verwerfen:

```bash
git add docs/handbuch/screenshots/10-ma-profil.png docs/handbuch/screenshots/16-admin-benutzer-formular.png docs/handbuch/screenshots/17-admin-benutzer-bearbeiten.png
git restore docs/handbuch/screenshots/
git status --short docs/handbuch/screenshots
```

Expected: nur die drei gestagten PNGs (`M  …10-…`, `M  …16-…`, `M  …17-…`).

- [ ] **Step 5: Commit**

```bash
git add backend/create_handbuch_testdata.py e2e/capture-handbook-screenshots.ts tools/handbook/handbuch-screenshots.js docs/handbuch/HANDBUCH-ERSTELLEN.md
git commit -F - <<'EOF'
docs(screenshots): Demo-Person mit Arbeitszeit-Blöcken, Handbuch-Bilder 10/16/17 neu

Seed: Sarah Klein bekommt Blöcke 08–12 + 15–16 (Soll unverändert 25 h)
und zwei über die Mittagslücke durchgestempelte Montage, gekappt über den
echten clamp. Aufnahmeskripte öffnen den Block-Editor beim Anlegen und das
Bearbeiten-Formular der Demo-Person. Bild 10 (Profil) zeigt die Karte
„Meine Arbeitszeit" statt der Wochenstunden in den persönlichen Daten.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 10: Technik-Doku – Backend-Architektur, ARC42, README, Verarbeitungsverzeichnis, Update-Anleitung

Spec 16.1 „Technik-Doku" (`docs/BACKEND-ARCHITEKTUR.md`, `docs/specs/dsgvo` mit Rechtsgrundlage nach A.2), Spec 19 Nr. 6 (natives Update), E24 (Downgrade aus der Hülle).

**Files:**
- Modify: `docs/BACKEND-ARCHITEKTUR.md` (bei `3d46c2f`: Abschnitt `### Arbeitszeit-Fenster (#201, work_window_service.py)` Zeilen 118–150, „Wichtige Patterns" Zeilen 152–158)
- Modify: `docs/ARC42.md` (bei `3d46c2f`: Zeilen 344–346, 482–483, 487, 528, 586)
- Modify: `README.md` (Migrationsliste, nach Zeile 247 `065`)
- Modify: `docs/specs/dsgvo/verarbeitungsverzeichnis.md` (Zeilen 4, 15, 51, 57–60, 78–83)
- Modify: `docs/UPDATE.md` (Kasten nach Zeile 12, Abschnitt „Rollback" Zeilen 231–232)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `technik`)

**Interfaces:**
- Consumes: Funktions- und Spaltennamen aus Task 7 Step 1; Endpunkte aus Spec 11.1.
- Produces: Gruppe `technik`.

- [ ] **Step 1: Prüfgruppe ergänzen**

Oberhalb der Markerzeile einfügen:

```bash
group_technik() {
  local f
  f=docs/BACKEND-ARCHITEKTUR.md
  need "$f" '### Arbeitszeit-Blöcke und Kappung (work_window_service.py, ab 1.20.0)'
  need "$f" 'reclamp_time_entries'
  need "$f" 'clamp_grace_minutes'
  need "$f" 'lock_user_row'
  forbid "$f" '### Arbeitszeit-Fenster (#201, work_window_service.py)'
  forbid "$f" 'scheduled_start_<wd>'
  f=docs/ARC42.md
  need "$f" '| 013 |'
  need "$f" '**Arbeitszeit-Block**'
  need "$f" 'work_blocks_service'
  forbid "$f" '# #201 Arbeitszeit-Fenster-Kappung mit Rohstempel-Erhalt'
  forbid "$f" 'aktuell **48 Migrationen**'
  f=README.md
  need "$f" '- `066` -'
  need "$f" '- `073` - Arbeitszeit-Blöcke'
  f=docs/specs/dsgvo/verarbeitungsverzeichnis.md
  need "$f" 'Arbeitszeit-Blöcke'
  need "$f" 'uncredited_minutes'
  need "$f" 'EuGH C-34/21'
  need "$f" 'Art. 13 Abs. 2 lit. f'
  f=docs/UPDATE.md
  need "$f" '### ⚠️ Update auf 1.20.0'
  need "$f" '`073_work_blocks`'
  need "$f" 'Hülle der Blöcke'
}

```

Run: `bash scripts/check-doc-sync.sh technik`
Expected: Exit 1 (u. a. `FEHLT     docs/UPDATE.md: ### ⚠️ Update auf 1.20.0`).

- [ ] **Step 2: BACKEND-ARCHITEKTUR.md**

Den Abschnitt von `### Arbeitszeit-Fenster (#201, work_window_service.py)` bis **ausschließlich** `## Wichtige Patterns` ersetzen durch:

````markdown
### Arbeitszeit-Blöcke und Kappung (work_window_service.py, ab 1.20.0)

**Datenmodell (Migration 073, ersetzt #201):** Blöcke sind Teil des datierten Vertrags-Snapshots: `working_hours_changes.blocks` (JSON/JSONB, nullable) und `users.work_blocks` (Rückfall nur vor der ersten Verlaufszeile, sonst Spiegel der jüngsten Zeile ≤ heute). Form: Liste aus genau 5 Tagen (Mo–Fr), je `{"blocks": [{"start": "HH:MM", "end": "HH:MM"}, …], "pause_minutes": int|null}`, höchstens 3 Blöcke, Raster 5 Min. NULL in einer Verlaufszeile = keine Blöcke (nie Rückfall); fünf leere Tage ≡ NULL; `pause_minutes` NULL = Altfenster aus 073 (nur Kappung). `time_entries` trägt `uncredited_minutes` (INT, Default 0), `credit_override` (BOOL), `auto_closed` (BOOL) und `clamp_grace_minutes` (INT NULL); `change_requests` trägt `request_credit_override` und `original_uncredited_minutes`. Die Spalten `users.scheduled_*` sind entfallen (Guard-Test `test_no_scheduled_columns.py`).

**Soll:** Neue Blöcke materialisieren beim Speichern `hours_*`, `weekly_hours`, `work_days_per_week`, `use_daily_schedule=True` (`work_blocks_service.derive_targets`); `calculation_service` liest für das Soll nie Blöcke. Blöcke liest ausschließlich `calculation_service.get_schedule_for_date` (`Schedule.blocks`, `Schedule.block_pauses`) → `work_window_service.get_scheduled_blocks(db, user, d)` (`[]` an Wochenende, Feiertag, `free`-Sondertag; Guard-Test `test_no_live_work_blocks_read.py`).

**Clamp (`clamp(db, user, d, start, end, grace, *, credit_override)` → `ClampResult(eff_start, eff_end, raw_start, raw_end, uncredited_minutes, grace_minutes)`):**
1. Keine Blöcke, `track_hours=False` oder `credit_override` → unverändert, `uncredited_minutes` 0, `grace_minutes` None.
2. Hülle `[erster Block − g, letzter Block + g]`: Beginn/Ende außerhalb werden verschoben, die Rohwerte stehen in `raw_start_time`/`raw_end_time` (§16); ganz außerhalb → Kollaps auf 0 h.
3. Lücken zwischen den Blöcken, um g an beiden Rändern geschrumpft (`credit_gaps`); ihre Überlappung mit dem Eintrag ist `uncredited_minutes` (je Lücke: `gap_segments`). Ein Beginn in der Lücke wird nie verschoben.
4. `net_hours` = Ende − Beginn − Pause − `uncredited_minutes` (Hybrid-Property, Python und SQL).

**Puffer-Herkunft:** Neuanlage → `get_grace_minutes(db, tenant_id)`; Einzel-Neukappung eines gespeicherten Eintrags → `grace_for_entry(db, entry)` (gespeicherter `clamp_grace_minutes`, sonst aktueller Puffer); Massen-Neukappung → aktueller Puffer, neu geschrieben. Jede schreibende Stelle setzt `clamp_grace_minutes = r.grace_minutes`, wenn nicht None.

**Schreibpfade (vollständig, je mit `lock_user_row` als erster Sperre):**

| Pfad | Wo gekappt |
|------|-----------|
| `clock_in` | Beginn (Hülle); Hinweis bei Einstempeln in der Lücke |
| `clock_out` | Ende, `uncredited_minutes`, Puffer des offenen Eintrags |
| `_close_stale_entry` (Auto-Close) | Ende 23:59 über `clamp`, `auto_closed=True` |
| `create_time_entry` / `update_time_entry` | MA-CRUD; `update` kappt auch bei Datumswechsel neu, anerkannter Eintrag → 409 |
| `admin_time_entries` create + update | Admin-CRUD; `credit_override` bleibt |
| `xls_import_service` | Vorschau + Ausführung (`clamp_applies`; Auto-Pause nur für den von Lücken ungedeckten §4-Rest) |
| `admin_change_requests.review_change_request` | CR-Genehmigung (CREATE/UPDATE, auch Bulk), „genehmigen und anerkennen" |
| `change_requests.create_change_request` | prüft mit `clamp`, speichert roh; `request_credit_override` |
| `work_window_service.reclamp_time_entries` | Massen-Neukappung einer Arbeitszeit-Änderung (Router `admin_users`) |
| `POST /admin/time-entries/{id}/credit-override` | Anerkennen: Rohzeiten werden wirksam, keine Kappung mehr |

**Ausnahmen:** `track_hours=False` → kein Clamp; `exempt_from_arbzg` (§18) → Clamp greift trotzdem; `credit_override` → nie gekappt, überlebt jede Neuberechnung.

**ArbZG:** §3/§4 hart auf angerechneter Zeit (`validate_daily_break(…, uncredited_segments=…)`, Lückensegmente ≥ 15 Min zählen als Pausenabschnitt); weiche `PRESENCE_DAILY_HOURS`/`PRESENCE_BREAK`/`PRESENCE_WEEKLY_HOURS` auf `presence_minutes`, dazu `BREAK_IN_GAP`; §5 auf den Rohstempeln.

**Rückwirkung:** `POST /admin/users/{id}/working-hours-changes` (dazu `…/preview`, `…/{change_id}/delete-preview`, `DELETE …/{change_id}`) läuft in einer Transaktion unter `lock_user_row`: offene Alteinträge schließen, `reclamp_time_entries` (nur geänderte Wochentage, ab Rohstempel), `retarget_absence_hours` (mit F1-Klemmung), Klassifikation Verlängerung/Verkürzung (Eintrag, Saldo, Gutschrift), Schutzpaket (Grundtyp, Begründung, Haken; in abgeschlossene Jahre gesperrt), Protokoll `wh_reclamp` je Eintrag plus Sammelzeile (`reclamp_audit.summary_note`/`parse_summary_note`). Die Vorschau rollt zurück und protokolliert nie.

**Services-Einträge:**

| Service | Datei | Zweck |
|---------|-------|-------|
| `work_window_service.py` | Arbeitszeit-Blöcke | `clamp()`, Lücken, Puffer je Eintrag, „nicht angerechnet", Anwesenheit, Neukappung |
| `work_blocks_service.py` | Arbeitszeit-Blöcke | JSON-Form parsen/serialisieren, `derive_targets` |
| `reclamp_audit.py` | Protokoll | Sammelzeile schreiben/lesen, Grundtypen `REASON_TYPES` |

````

Unter `## Wichtige Patterns` nach dem Punkt, der mit `- **`get_schedule_for_date(db, user, date)`** (#431)` beginnt, einfügen:

```markdown
- **Zeiteintrag schreiben (ab 1.20.0):** `lock_user_row` zuerst, dann `clamp(…, credit_override=…)` mit dem richtigen Puffer (`get_grace_minutes` bei Neuanlage, `grace_for_entry` bei gespeicherten Einträgen), `uncredited_minutes`/`clamp_grace_minutes` übernehmen, Netto-Helfer und `validate_daily_break` mit den Lückenwerten. Nie `users.work_blocks` oder Altfelder `scheduled_*` lesen.
```

- [ ] **Step 3: ARC42.md**

1. `services/  (26 Domain-Services)`: Zahl ersetzen durch die Ausgabe von `ls backend/app/services/*.py | grep -v __init__ | wc -l`.
2. `  work_window_service       # #201 Arbeitszeit-Fenster-Kappung mit Rohstempel-Erhalt` ersetzen durch:

```text
  work_window_service       # Arbeitszeit-Blöcke: Kappung (Hülle + Lücken), Neukappung, Rohstempel-Erhalt
  work_blocks_service       # JSON-Form der Blöcke, derive_targets (Tagessoll aus Blöcken)
  reclamp_audit             # Sammelzeile der Arbeitszeit-Änderung, Grundtypen
```

3. §8.4: `- **Alembic**, aktuell **48 Migrationen** (`001`…`048`, `version_num varchar(32)`-Limit beachten).` → `- **Alembic**, aktuell **<N> Migrationen** (`001`…`073`, `version_num varchar(32)`-Limit beachten).` mit `<N>` = Ausgabe von `ls backend/alembic/versions/*.py | wc -l`; in der Folgezeile hinter `` `048` Arbeitszeit-Fenster`` anfügen: `` · `067` Vertrags-Snapshot (#431) · `073` Arbeitszeit-Blöcke (Fenster-Spalten entfallen)``.
4. §8.5: `**#201 Arbeitszeit-Fenster** (Rohstempel `raw_start/end_time` erhalten).` → `**Arbeitszeit-Blöcke** (Kappung vor, nach und zwischen den Blöcken; Rohstempel `raw_start/end_time` erhalten; weiche Anwesenheits-Hinweise `PRESENCE_*`).`
5. ADR-Tabelle: nach der Zeile `| 012 | **Arbeitszeit-Fenster mit Rohstempel-Erhalt** (#201) | … |` anfügen:

```markdown
| 013 | **Arbeitszeit-Blöcke im Vertrags-Snapshot**, Soll beim Schreiben materialisiert, Neukappung mit Schutzpaket (1.20.0) | Eine Pflegestelle für Soll und Kappung; `calculation_service` bleibt unverändert; rückwirkende Verkürzung nur mit Grund (§ 106 GewO), nicht angerechnete Zeit sichtbar und anerkennbar |
```

6. Glossar: nach der Zeile `| **Arbeitszeit-Fenster** | … |` anfügen: `| **Arbeitszeit-Block** | Vertraglicher Zeitraum „von–bis" je Wochentag (bis zu 3, ab 1.20.0); Tagessoll = Σ Blöcke − Pause; Zeit vor, nach und zwischen den Blöcken wird bis auf den Puffer nicht angerechnet (`uncredited_minutes`) |`

- [ ] **Step 4: README.md**

Nach der Zeile `- `065` - use_fixed_monthly_target (fester Monats-Soll für Minijobs, #377 Baustein 2b)` einfügen:

```markdown
- `066` - users.vacation_days dezimal (Numeric(4,1), #408)
- `067` - working_hours_changes als vollständiger Vertrags-Snapshot (#431)
- `068` - absences.raw_hours (beim Buchen festgeschriebener Stundenwert)
- `069` - users.weekly_hours Numeric(4,2) (#431)
- `070` - Schichtplan-Freigabe für Mitarbeitende + Hinweis je Einteilung (#443)
- `071` - security_events (Konto-Vorgänge, #425)
- `072` - change_requests.proposed_sunday_exception_reason (§10-Grund im Antrag, #485)
- `073` - Arbeitszeit-Blöcke: users.work_blocks + working_hours_changes.blocks, time_entries.uncredited_minutes/credit_override/auto_closed/clamp_grace_minutes, change_requests.request_credit_override/original_uncredited_minutes; users.scheduled_start/end_<wochentag> entfallen
```

- [ ] **Step 5: Verarbeitungsverzeichnis**

In `docs/specs/dsgvo/verarbeitungsverzeichnis.md`:

1. `**Stand:** 2026-06-06` → `**Stand:** 2026-10 (PraxisZeit 1.20.0)`
2. Zeile `| **Rechtsgrundlage** | … |` in §1 ersetzen durch:

```markdown
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. c DSGVO (rechtliche Verpflichtung: § 16 Abs. 2 ArbZG, § 3 Abs. 2 Nr. 1 ArbSchG i. V. m. BAG 1 ABR 22/21, § 17 MiLoG), Art. 6 Abs. 1 lit. b DSGVO (Durchführung des Beschäftigungsverhältnisses, u. a. Anrechnung der Arbeitszeit); § 26 BDSG nach EuGH C-34/21 nur ergänzend |
```

3. §4.1: die Zeile, die mit `| Vertrags` beginnt (das Wort enthält einen weichen Trennstrich U+00AD – Zeile vorher lesen), in der zweiten Spalte von `Wochenstunden, Arbeitstage, Urlaubstage, Kalenderfarbe` auf `Wochenstunden, Arbeitstage, Tagesplan, Soll-Arbeitszeiten (Arbeitszeit-Blöcke je Wochentag mit Pause innerhalb der Blöcke), Urlaubstage, Kalenderfarbe` ändern.
4. §4.2: nach der Zeile `| Sonn-/Feiertagsarbeit | Ausnahmegrund-Dokumentation (§10 ArbZG) | Art. 6 Abs. 1 lit. c DSGVO |` anfügen:

```markdown
| Anrechnung der Arbeitszeit | nicht angerechnete Minuten (`uncredited_minutes`), Anerkennung (`credit_override`), automatisch geschlossen (`auto_closed`), angewandter Puffer (`clamp_grace_minutes`), Rohstempel (`raw_start_time`/`raw_end_time`) | Art. 6 Abs. 1 lit. b DSGVO (Anrechnung), lit. c (§ 16 Abs. 2 ArbZG, § 17 MiLoG) |
```

5. §4.4: `| Arbeitszeitenhistorie | Wochenstunden, Gültigkeitsdatum | Korrekte historische Berechnung von Soll-Stunden |` → `| Arbeitszeitenhistorie | Wochenstunden, Tagesplan, Arbeitszeit-Blöcke, Gültigkeitsdatum, Begründung rückwirkender Änderungen (Freitext, bei Anonymisierung geleert) | Korrekte historische Berechnung von Soll und Anrechnung; Nachweis rückwirkender Änderungen |`; `| Änderungsanträge | Zeiteintrags-Korrekturen mit Begründung | Transparenz, Nachvollziehbarkeit |` → `| Änderungsanträge | Zeiteintrags-Korrekturen mit Begründung, inkl. Antrag auf Anrechnung nicht angerechneter Zeit | Transparenz, Nachvollziehbarkeit, Anfechtung der automatischen Anrechnung |`; `| Audit-Log | Benutzer, Aktion, Zeitstempel, Details | Nachvollziehbarkeit von Admin-Aktionen, DSGVO-Compliance |` → `| Audit-Log | Benutzer, Aktion, Zeitstempel, Details, inkl. Neukappungen und Anerkennungen | Nachvollziehbarkeit von Admin-Aktionen, DSGVO-Compliance |`. Danach (vor `### 4.5`) einfügen:

```markdown

> **Automatisierte Anrechnung (Art. 22, Art. 13 Abs. 2 lit. f DSGVO):** Die Kappung gegen die Arbeitszeit-Blöcke läuft beim Stempeln automatisch und wirkt auf das Überstundenkonto (Risiko gering bis mittel). Schutzmaßnahmen: jede nicht angerechnete Zeit ist sichtbar (Eintrag, Monatsjournal, Exportspalte), die Verwaltung kann sie anerkennen, Beschäftigte können die Anrechnung mit Begründung beantragen; Arbeitszeit-Änderungen laufen mit Vorschau, Bestätigung, Protokoll und Dashboard-Hinweis an die Betroffenen. Die Logik ist auf der Datenschutzseite der Anwendung beschrieben.
```

- [ ] **Step 6: UPDATE.md**

1. Nach dem Kasten, der mit `> **Nach jedem Update: Browser-Hard-Refresh**` beginnt (vor `---` und `## Docker`), einfügen:

```markdown

> ### ⚠️ Update auf 1.20.0 = Arbeitszeit-Fenster werden zu Arbeitszeit-Blöcken
>
> Die Migration `073_work_blocks` läuft beim ersten Start automatisch. Sie übernimmt
> jedes hinterlegte Soll-Arbeitszeit-Fenster als einen Block je Tag
> („Arbeitszeit-Fenster (Altbestand, nur Kappung)") und **entfernt die alten
> Fenster-Spalten**. Tagessoll, angerechnete Zeit und Überstundensaldo bestehender
> Einträge bleiben unverändert. Danach:
> - Seite neu laden (siehe oben) – ein noch geöffnetes altes Benutzerformular meldet
>   beim Speichern „Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende)
>   wurden durch Arbeitszeit-Blöcke ersetzt."
> - **Zurück auf 1.19.x nur über das Backup** von vor dem Update. Ein Schema-Downgrade
>   stellt je Tag nur die Hülle der Blöcke (Beginn des ersten bis Ende des letzten
>   Blocks) als Fenster her – Zeit zwischen den Blöcken würde dann wieder angerechnet.
```

2. Abschnitt „Rollback": nach `**nicht** unterstützt — daher das Backup.` anfügen: ` Ab 1.20.0 gilt das besonders: Migration `073` entfernt die Spalten der alten Arbeitszeit-Fenster (siehe Kasten oben).`

- [ ] **Step 7: Prüfen und Commit**

Run: `bash scripts/check-doc-sync.sh technik`
Expected: `OK: technik`.

```bash
git add scripts/check-doc-sync.sh docs/BACKEND-ARCHITEKTUR.md docs/ARC42.md README.md docs/specs/dsgvo/verarbeitungsverzeichnis.md docs/UPDATE.md
git commit -F - <<'EOF'
docs(technik): Arbeitszeit-Blöcke in Architektur, ARC42, README, VVT und Update-Anleitung

BACKEND-ARCHITEKTUR: Datenmodell, Soll-Materialisierung, clamp/ClampResult,
Puffer-Herkunft, alle Schreibpfade mit Ankersperre, Rückwirkung. ARC42: ADR
013, Services, Migrationen, Glossar. README: Migrationen 066–073.
Verarbeitungsverzeichnis: neue Kategorien, Rechtsgrundlage nach EuGH
C-34/21, Art.-22-Hinweis. UPDATE.md: Kasten zu 073 und zum Rückweg.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 11: CLAUDE.md – Regeln zu Blöcken, Kappung, Neukappung, Doku-Abgleich

Spec 16.2 (zwölf Regeln) plus die Doku-Regeln dieses PRs.

**Files:**
- Modify: `CLAUDE.md` (bei `3d46c2f`: Zeile 105 `#201`-Regel, Zeile 122 #498-Regel, Zeile 131 #431-Regel, Zeile 138 `wh_change`-Regel, Zeile 139 Doku-Sync-Regel, Zeile 173 `source`-Liste)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `claude`)

**Interfaces:**
- Consumes: Namen aus Task 7 Step 1; `scripts/check-doc-sync.sh` (Task 0); `DocViewer.test.tsx` (Task 8).
- Produces: Gruppe `claude`.

- [ ] **Step 1: Prüfgruppe ergänzen**

Oberhalb der Markerzeile einfügen:

```bash
group_claude() {
  local f=CLAUDE.md
  need "$f" '**Arbeitszeit-Blöcke (1.20.0, ersetzt das #201-Fenster):**'
  need "$f" '**`clamp` liefert `ClampResult(eff_start, eff_end, raw_start, raw_end, uncredited_minutes, grace_minutes)`'
  need "$f" '**`net_hours` = Ende − Beginn − Pause − `uncredited_minutes`**'
  need "$f" '**Puffer je Eintrag (`clamp_grace_minutes`'
  need "$f" '**Ankersperre zuerst (P5):**'
  need "$f" '**`auto_closed`:**'
  need "$f" '= Lücke + Hülle**'
  need "$f" '**Neukappung (`work_window_service.reclamp_time_entries`):**'
  need "$f" '**`credit_override` (Anerkennen)**'
  need "$f" '**Sammelzeile und Grundtypen'
  need "$f" 'Das gilt auch für Kappungsregeln'
  need "$f" '`wh_reclamp` (Neukappung + Sammelzeile, 1.20.0)'
  need "$f" 'Krank 4,0 h — Arbeitszeit-Änderung ab 15.03.2026'
  need "$f" 'bash scripts/check-doc-sync.sh all'
  need "$f" '**Release-Gate 1.20.0 (Migration 073, Spec 17.8, Risiko 6):**'
  need "$f" 'GET /api/admin/users` mit einer Altfenster-Person (07:37/23:59)'
  forbid "$f" 'Pro MA je Wochentag optionale `scheduled_start_<wd>`'
  forbid "$f" '`get_scheduled_window(db, user, d)` liefert'
}

```

Run: `bash scripts/check-doc-sync.sh claude` → Expected: Exit 1.

- [ ] **Step 2: #201-Regel ersetzen**

Die ganze Zeile, die mit `- **Arbeitszeit-Fenster (#201):** Pro MA je Wochentag optionale` beginnt, durch diese Punkte ersetzen:

```markdown
- **Arbeitszeit-Blöcke (1.20.0, ersetzt das #201-Fenster):** `working_hours_changes.blocks` / `users.work_blocks` = Liste[5] Mo–Fr, je `{"blocks": [{"start": "HH:MM", "end": "HH:MM"}, …], "pause_minutes": int|null}`, max. 3 Blöcke, Raster 5, Zeiten immer als String; Änderung nur per Neuzuweisung des ganzen Werts (eine In-place-Mutation speichert SQLAlchemy nicht). **NULL in einer Verlaufszeile = keine Blöcke, NIE Rückfall**; `users.work_blocks` ist Rückfall nur vor der ersten Verlaufszeile; fünf leere Tage ≡ NULL. `pause_minutes` NULL = Altfenster aus Migration 073 (nur Kappung, keine Soll-Wirkung). Neue Blöcke materialisieren beim Schreiben `hours_*`, `weekly_hours`, `work_days_per_week`, `use_daily_schedule=True` über **`work_blocks_service.derive_targets`** (Decimal, HALF_EVEN) — `calculation_service` liest für das Soll **nie** Blöcke. Einzige Leseschnittstelle: `get_schedule_for_date` → `work_window_service.get_scheduled_blocks` (Wochenende, Feiertag des Mandanten, `free`-Sondertag → `[]`, #484; `db` ist Pflicht). Guard-Tests: kein Code in `app/` enthält `scheduled_start_`/`scheduled_end_` (`test_no_scheduled_columns.py`), `.work_blocks` nur an den Stellen aus `test_no_live_work_blocks_read.py`. Leseschemas (auch Login/Impersonation) typisieren Blöcke **locker** (`Optional[Any]`) — ein strenger Validator machte den Login einer Person mit Altfenster (07:37, 23:59) zu HTTP 500; streng prüfen nur `UserCreate`/`WorkingHoursChangeCreate` (`validators.validate_week_blocks`). `PUT /admin/users` lehnt `work_blocks` (historisiert) und Altfelder mit Präfix `scheduled_` (400 „Bitte Seite neu laden …") ab.
- **`clamp` liefert `ClampResult(eff_start, eff_end, raw_start, raw_end, uncredited_minutes, grace_minutes)`, `credit_override` ist Pflicht-Schlüsselwort.** Hülle wie #201 (Beginn vor erstem Block − g / Ende nach letztem Block + g verschoben, Rohstempel in `raw_*`, Kollaps außerhalb der Hülle wie bisher); **Beginn in der Lücke wird NIE verschoben** (UNIQUE `uq_tenant_user_date_start`), die Lücke läuft über `uncredited_minutes`. Puffer an jedem Blockrand, die Lücke schrumpft um 2g, eine Lücke ≤ 2g verschwindet. Jede neue Schreibfläche für Zeiteinträge: `clamp` + `uncredited_minutes` + `clamp_warning(…, for_employee=…)`, die Netto-Helfer `_calculate_daily/weekly_net_hours` mit `uncredited_minutes` (Pflichtparameter) und `validate_daily_break` mit `uncredited_segments`. Übersprungen bei `track_hours=False` und `credit_override`; `§18/exempt_from_arbzg`-MA werden **trotzdem** gekappt (Anwesenheits-Policy). **§5-Ruhezeit rechnet gegen die ROHSTEMPEL, nicht die gekappte Zeit** (UC-Review R3): `rest_time_service.check_rest_time_violations` + die Echtzeit-Warnung in `clock_in` nutzen `raw_end_time/raw_start_time or end_time/start_time`; die Neukappung setzt `raw_*` nie aus gekappten Werten.
- **`net_hours` = Ende − Beginn − Pause − `uncredited_minutes`** (Python-Hybrid **und** SQL-Ausdruck; Paritätstest auf PG mit Toleranz n × 0,005 h — Python rundet je Zeile, SQL nicht, und das bleibt so wegen der Byte-Identität bestehender Summen). Keine Inline-Netto-Rechnung ohne `uncredited`.
- **Puffer je Eintrag (`clamp_grace_minutes`, E79/E80):** Jede Kappung gegen Blöcke schreibt den angewandten Puffer (`r.grace_minutes`; `None` lässt den gespeicherten Wert stehen). Wer einen **gespeicherten** Eintrag neu kappt (Ausstempeln, Bearbeiten, Datumswechsel, CR-Genehmigung, XLS-Überschreiben, Auto-Close), nimmt `grace_for_entry(db, entry)` — nie `get_grace_minutes` direkt; NULL (Bestand vor 1.20.0) = aktueller Puffer. Nur die Massen-Neukappung nimmt den aktuellen Puffer und schreibt ihn in **jeden** geprüften Eintrag an einem geänderten Wochentag, auch ohne Zeitänderung.
- **Ankersperre zuerst (P5):** Jeder Schreibpfad für Zeiteinträge nimmt `lock_user_row(db, tenant_id, owner_id)` als erste Sperre — vor Puffer, Snapshot-Auflösung und `clamp` und **immer vor** einer Zeilensperre auf `time_entries` —, sonst kappt ein paralleler Schreiber unter dem alten Snapshot (READ COMMITTED) bzw. verklemmen sich Anerkennen und Neukappung (40P01 → 500).
- **`auto_closed`:** `raw_end_time = 23:59` eines automatisch geschlossenen Eintrags ist **kein** Stempel — nie anerkennen (400), nie als Anwesenheit oder „nicht angerechnet" zählen. Aufgehoben wird es nur von einem **tatsächlich neuen** Ende: Ausstempeln und XLS-Überschreiben immer, MA-/Admin-Bearbeitung und CR-UPDATE nur, wenn `work_window_service.end_is_correction(…)` zutrifft. Ein unverändert zurückgeschicktes wirksames Ende, das zurückgeschickte Rohende 23:59 und die Neukappung lassen `auto_closed` stehen — NIE bei jedem `end_time`-Schreiben auf False setzen, sonst hebt schon das Formular-Speichern (Pause ergänzt, Ende unverändert) das Kennzeichen auf und Anerkennen rechnet wieder bis 23:59 an. Der Auto-Close (`_close_stale_entry`) kappt über `clamp` (der Abend wird nicht mehr voll angerechnet).
- **„Nicht angerechnet" = Lücke + Hülle** (`work_window_service.not_credited_minutes`, Frontend-Zwilling `utils/workBlocks.ts::notCreditedMinutes` mit wortgleichen Testfällen); „angerechnet" = `net_hours`; Anwesenheit = `presence_minutes`. Neue Anzeige- und Exportflächen nutzen die Helfer, nie `uncredited_minutes` allein. Die Export-Spalte „Nicht angerechnet (Min)" wird **angehängt** (XLSX/ODS Spalte 13, PDF 12.), nie eingeschoben. Begriffe: „Arbeitszeit-Block" = Vertrag, „Zeiteintrag" = Stempel — deshalb heißt die #498-Spalte „Zeiteinträge".
- **Neukappung (`work_window_service.reclamp_time_entries`):** Quelle Rohstempel (sonst die gespeicherte Zeit), nur geänderte Wochentage, aktueller Puffer; offene Einträge vergangener Tage vorher per `_close_stale_entry` schließen; erst Zeiteinträge, dann `retarget_absence_hours` (mit F1-Klemmung `kept_net_by_date`); eine Transaktion unter `lock_user_row`; Protokoll `wh_reclamp` je Eintrag plus Sammelzeile **im Router**; die Vorschau rollt zurück und protokolliert nie. **Verkürzung** = Eintrag verliert angerechnete Zeit **oder** Saldo sinkt (ohne Jahresüberträge, bis zum Stichtag #313, plus steigendes Soll am heute offenen Tag) **oder** F1 senkt eine Abwesenheits-Gutschrift stärker als das Tagessoll des Tages (eine nur mit dem Soll sinkende Gutschrift ist saldo-neutral, keine Verkürzung) — beim Anlegen **und** Löschen, auch bei reinen Wochenstunden-Änderungen; rückwirkend nur mit Grund/Haken, in abgeschlossene Jahre gesperrt (400), Standard = `earliest_lossless_date`. Klassifikation erst **nach** `retarget_absence_hours`. Löschen mit Verkürzung: Standard Rücksetzung (`reset_body`/`reset_of_change_id`).
- **`credit_override` (Anerkennen)** überlebt jede Neuberechnung und jede Zeitänderung durch die Verwaltung (Direktbearbeitung, Antragsgenehmigung, XLS-Überschreiben); kein Pfad setzt es still zurück, eine Rücknahme gibt es nicht. MA-`PUT` auf einen anerkannten Eintrag → 409 (nur per Antrag). `POST /admin/time-entries/{id}/credit-override`: Ankersperre, dann Zeilensperre; Protokoll `source="credit_override"`.
- **Sammelzeile und Grundtypen (`app/services/reclamp_audit.py`):** genau eine Sammelzeile bei **jedem** Anlegen und Löschen einer Arbeitszeit-Änderung (auch 0 Einträge, auch reine Wochenstunden-Änderung), erkennbar an `source='wh_reclamp' AND time_entry_id IS NULL AND old_date IS NULL AND new_date IS NULL`; Schreiben (`summary_note`) und Lesen (`parse_summary_note`) nur dort (Round-Trip-Test) — der 30-Tage-Hinweis im MA-Dashboard hängt daran. Grundtyp-Schlüssel (`erfassungsfehler`/`einvernehmlich`/`sonstiges`) und Notiz-Präfixe (`[Erfassungsfehler korrigiert]` …) sind **eingefroren**; Beschriftungen nur über `REASON_TYPES`. Keine neue gehashte Spalte (sonst meldet `verify-integrity` alle Altzeilen).
- **Release-Gate 1.20.0 (Migration 073, Spec 17.8, Risiko 6):** 073 löscht die Spalten `users.scheduled_*` und ändert Login-, Benutzer- und Stempelpfade. `/buildrelease` prüft nach dem Update auf 073 auf .131 **nativ** (`install.sh`-Update) **und** mit dem **Docker-Bundle** jeweils einen echten Login, clock-in und clock-out sowie `GET /api/admin/users` mit einer Altfenster-Person (07:37/23:59) — die lockeren Leseschemas dürfen dort kein HTTP 500 werfen. Unit-Tests, `validate-release.sh` (prüft nur `postgres`/`initdb`) und die Byte-Identitäts-Probe (PR1 Task 17) ersetzen diesen Schritt nicht.
```

- [ ] **Step 3: Übrige Regeln anpassen**

1. Regel `- **Geteilte Dienste in §16-Exporten (#498):**`: `12 „Arbeitsblöcke“` → `12 „Zeiteinträge“`; am Ende dieses Punkts (vor dem Zeilenende) anfügen: ` Spalte 12 hieß bis kurz vor 1.20.0 „Arbeitsblöcke“ – umbenannt, weil „Arbeitszeit-Block“ seit 1.20.0 den Vertrag meint; Spalte 13 „Nicht angerechnet (Min)“ ist die letzte.`
2. #431-Regel: nach `… sonst wiederholt sich exakt die #431-Lücke (Live-Feld ohne Historie, ohne Rückrechnung, ohne Jahresabschluss-Warnung).` anfügen: ` Das gilt auch für Kappungsregeln: Arbeitszeit-Blöcke und `pause_minutes` stehen deshalb in derselben Zeile (`working_hours_changes.blocks`); `users.work_blocks` ist nur Rückfall und Spiegel.`
3. `wh_change`-Regel: `„Krank 8,0 h" → „Krank 4,0 h — Wochenstunden-Änderung ab 15.03.2026")` → `„Krank 8,0 h" → „Krank 4,0 h — Arbeitszeit-Änderung ab 15.03.2026"; Präfix seit 1.20.0 „Arbeitszeit-Änderung")`
4. Doku-Regel `- **In-App-Hilfe/Handbuch ist hardcoded**`: am Ende anfügen: ` Seit 1.20.0 prüft `bash scripts/check-doc-sync.sh all` den Spiegel, die Anker, Pflicht- und Verbotsbegriffe je Fläche und – als Gate – dass jeder zitierte Wortlaut im Code steht; die In-App-Flächen sichert `frontend/src/components/DocViewer.test.tsx`. Läuft als Schritt 0 von `scripts/local-ci.sh`. Neue Doku-Fläche oder neuer zitierter Wortlaut → Gruppe im Skript ergänzen. Gestempelte Einträge nie „Blöcke" nennen (Abgrenzung zu den Arbeitszeit-Blöcken).`
5. `source`-Regel: `Source-Werte u. a.: `manual`, `import`, `change_request`, `vacation_request_cancel`, `break_waiver`, `dsgvo`, `license_startup`.` → `Source-Werte u. a.: `manual`, `import`, `change_request`, `vacation_request_cancel`, `break_waiver`, `dsgvo`, `license_startup`, `auto_close`, `wh_change`, `wh_reclamp` (Neukappung + Sammelzeile, 1.20.0), `credit_override` (Anerkennen, 1.20.0).`

- [ ] **Step 4: Prüfen und Commit**

Run: `bash scripts/check-doc-sync.sh claude`
Expected: `OK: claude`.

```bash
git add scripts/check-doc-sync.sh CLAUDE.md
git commit -F - <<'EOF'
docs(claude): Regeln zu Arbeitszeit-Blöcken, Kappung, Neukappung, Doku-Abgleich

Ersetzt die #201-Regel durch die Block-Regeln aus Spec 16.2 (Datenmodell,
ClampResult, net_hours, Puffer je Eintrag, Ankersperre, auto_closed,
„nicht angerechnet", Neukappung/Verkürzung, credit_override, Sammelzeile
und Grundtypen) plus Release-Gate für Migration 073 (Spec 17.8, Risiko 6);
#431-, #498-, wh_change- und source-Regel nachgezogen; Doku-Abgleich per
scripts/check-doc-sync.sh.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 12: CHANGELOG-Entwurf für 1.20.0 ⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen

Release-Notes laut Spec 16.1 („Auto-Close kappt jetzt; rückwirkende Erhöhungen brauchen Grund und Bestätigung; Puffer je Eintrag; Downgrade aus der Hülle") plus die Issue-Lanes, die im selben Release ausgeliefert werden. Der Abschnitt bleibt `[Unreleased]`; `/buildrelease` setzt Versionsnummer und Datum.

**Files:**
- Modify: `CHANGELOG.md` (Abschnitt `## [Unreleased]`, Zeile 3)
- Modify: `scripts/check-doc-sync.sh` (Gruppe `changelog`)

**Interfaces:**
- Consumes: Commits der Issue-Lanes zwischen `master` und dem Integrationszweig.
- Produces: Gruppe `changelog`; Release-Text, den `/buildrelease` (Phase „Stage pzweb", `DEPLOYMENT-ORDER.md`) übernimmt.

- [ ] **Step 1: Prüfgruppe ergänzen**

Oberhalb der Markerzeile einfügen:

```bash
group_changelog() {
  local f=CHANGELOG.md
  need "$f" 'Geplant als **1.20.0**'
  need "$f" '`073_work_blocks`'
  need "$f" '### ✨ Arbeitszeit als Blöcke je Tag'
  need "$f" '### ⚠️ Geändertes Verhalten'
  need "$f" '**Vergessenes Ausstempeln:**'
  need "$f" 'Bitte Seite neu laden'
  need "$f" '**Downgrade auf 1.19.x:**'
  local n
  for n in '(#482)' '(#491)' '(#493)' '(#494)' '(#495)' '(#496)' '(#497, #498)' '(#499)' '(#500)' '(#501)'; do
    need "$f" "$n"
  done
}

```

Run: `bash scripts/check-doc-sync.sh changelog` → Expected: Exit 1.

- [ ] **Step 2: Lane-Inhalte gegenprüfen**

Run: `git log --format='%h %s' "$(git merge-base master HEAD)"..HEAD | grep -E '#(482|491|493|494|495|496|497|498|499|500|501)'`
Expected: Commits zu jeder der elf Nummern. Für jeden Punkt unter „Weitere Verbesserungen", „Weitere Korrekturen" und „Technik" in Step 3 die zugehörige Commit-Nachricht lesen (`git show --stat <hash>`) und den Punkt nur dann unverändert übernehmen, wenn er den Commit richtig beschreibt; sonst den Punkt an die Commit-Nachricht anpassen (Wortlaut für Praxen, ohne Code-Namen).

- [ ] **Step 3: Abschnitt schreiben**

In `CHANGELOG.md` die Zeile `## [Unreleased]` (und die leere Zeile danach) ersetzen durch:

````markdown
## [Unreleased]

Geplant als **1.20.0** (Minor-Release). Update aus jeder 1.19.x ohne
Zwischenschritte. **Enthält eine Datenbank-Migration** (`073_work_blocks`): Sie
übernimmt die bisherigen Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende je Wochentag)
als Arbeitszeit-Blöcke und entfernt die alten Spalten. Tagessoll, angerechnete
Zeit und Überstundensaldo aller bestehenden Einträge bleiben dabei unverändert.
**Vor dem Update ein Backup ziehen** – der Rückweg auf 1.19.x ist nur über dieses
Backup verlustfrei (`UPDATE.md`).

### ✨ Arbeitszeit als Blöcke je Tag
- **Bis zu drei Arbeitszeit-Blöcke je Wochentag** mit „Pause innerhalb der
  Blöcke", z. B. Mo 08:00–12:00 und 15:00–18:00. Daraus folgt das Tagessoll
  (Summe der Blöcke minus Pause); Wochenstunden und Arbeitstage werden
  abgeleitet – eine zweite Pflegestelle entfällt. Gepflegt mit Wirkungsdatum im
  Dialog „Arbeitszeit & Wochenstunden" (Knopf „Arbeitszeit anpassen…", Modus
  „Nach Arbeitsblöcken"), beim Anlegen direkt im Formular.
- **Zeit zwischen den Blöcken wird nicht angerechnet** – mit Puffer an jedem
  Blockrand. Wer bei obigen Blöcken und 15 Minuten Puffer 08:00–18:00
  durchstempelt, bekommt 7:30 h angerechnet; die gestempelten Zeiten bleiben
  gespeichert (§ 16 ArbZG).
- **Nicht angerechnete Zeit ist überall sichtbar:** unter jedem Eintrag
  (Admin-Dashboard, Monatsjournal, Zeiterfassung), als Monatssumme im Journal und
  als neue letzte Spalte „Nicht angerechnet (Min)" in Excel, ODS und PDF.
- **Anerkennen und „Anrechnung beantragen":** Die Verwaltung kann nicht
  angerechnete Zeit je Eintrag anerkennen (dauerhaft, protokolliert);
  Mitarbeitende können die Anrechnung per Änderungsantrag beantragen.
- **Rückwirkende Änderungen rechnen neu** – mit Vorschau (Einträge je Monat
  alt → neu, Differenz von Soll, angerechneter Zeit und Überstundenkonto,
  übersprungene Einträge mit Grund), Protokoll je Eintrag und einer Sammelzeile
  je Änderung.
- **Schutz gegen rückwirkende Verkürzung:** Verliert ein Eintrag angerechnete
  Zeit, sinkt das Überstundenkonto oder sinkt eine Abwesenheits-Gutschrift
  stärker als das Tagessoll, gilt die Änderung standardmäßig erst ab heute.
  Rückwirkend nur mit Grund („Arbeitszeit war falsch hinterlegt
  (Fehlerkorrektur)", „Mit der beschäftigten Person vereinbart", „Sonstiges"),
  Begründung und Bestätigung; in abgeschlossene Jahre gesperrt. Das Löschen einer
  verkürzenden Änderung setzt standardmäßig ab heute auf den vorherigen Stand
  zurück.
- **Mitarbeitende werden informiert:** 30 Tage lang ein Hinweis auf dem
  Dashboard nach jeder Änderung ihrer Arbeitszeit, im Profil die Karte „Meine
  Arbeitszeit" mit Blöcken und Verlauf; in der geplanten Pause zwischen zwei
  Blöcken zeigt das Dashboard neutral „Pause zwischen den Arbeitsblöcken" statt rot.
- **ArbZG auch auf der tatsächlichen Anwesenheit:** Zusätzlich zu den
  Prüfungen auf der angerechneten Zeit weisen Hinweise auf eine Anwesenheit laut
  Stempel über 10 Stunden am Tag, auf durchgestempelte Tage ohne Pause und auf
  über 48 Stunden je Woche hin; die 24-Wochen-Auswertung zeigt einen zweiten
  Wert „Anwesenheit laut Stempel". Ein Hinweis meldet, wenn eine Pause
  zusätzlich zur Lücke abgezogen wird.

### ⚠️ Geändertes Verhalten
- **Vergessenes Ausstempeln:** Ein automatisch um 23:59 geschlossener Eintrag
  wird jetzt gegen die Arbeitszeit gekappt – der Abend wird nicht mehr voll
  angerechnet. 23:59 bleibt gespeichert, gilt aber nicht als Stempel.
- **Rückwirkende Erhöhung der Wochenstunden oder des Tagesplans** braucht jetzt
  Grund und Bestätigung, wenn das Überstundenkonto dadurch sinkt (bisher genügte
  der Bestätigungshaken). „Ab heute" bleibt ohne Grund möglich.
- **Der Puffer wird je Eintrag gespeichert.** Eine Änderung des Puffers in den
  Einstellungen wirkt nur auf neue Einträge; Einträge aus der Zeit vor 1.20.0
  werden bei einer Bearbeitung mit dem aktuellen Puffer gekappt.
- **Bisherige Arbeitszeit-Fenster** wirken als „Arbeitszeit-Fenster
  (Altbestand, nur Kappung)" unverändert weiter und lassen sich im Dialog in
  Blöcke umwandeln oder entfernen.
- **Nach dem Update die Seite neu laden:** Ein noch geöffnetes altes
  Benutzerformular meldet beim Speichern „Bitte Seite neu laden: Die
  Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) wurden durch Arbeitszeit-Blöcke
  ersetzt."
- **Downgrade auf 1.19.x:** Ein Schema-Downgrade stellt je Tag die Hülle der
  Blöcke (Beginn des ersten bis Ende des letzten Blocks) als Fenster her; Zeit
  zwischen den Blöcken würde dann wieder angerechnet. Empfohlen ist der Rückweg
  über das Backup.

### 🐞 Korrekturen (mit den Blöcken behoben)
- **Datumswechsel eines eigenen Eintrags** auf einen anderen Wochentag kappt
  jetzt gegen die Arbeitszeit des neuen Tags.
- **Änderungsanträge mit geteiltem Dienst** (z. B. „08–18, Pause 0" bei einer
  Mittagslücke) ließen sich nicht stellen, weil der Antrag die gestempelte Zeit
  prüfte, die Genehmigung aber die angerechnete; beide prüfen jetzt dasselbe.
- **Nachprüfung nach einer Antrags-Genehmigung** zählte den geänderten Eintrag
  doppelt (zu hohe Wochen- und Nachtarbeits-Hinweise).
- **XLS-Import:** zieht keine automatische Pause mehr doppelt ab, wenn die
  Lücke zwischen den Blöcken die Pausenpflicht deckt; die Ruhezeitprüfung nutzt
  die tatsächlich gestempelte Endzeit.

### ✨ Weitere Verbesserungen
- **Mitarbeiter-Dashboard: Umschalter Monat/Woche** (#500) – die letzten
  8 Kalenderwochen mit Soll, Ist, Saldo und Überstundenkonto; vergessene
  Einträge fallen pro Woche sofort auf.
- **Stempelkarte „x von y h heute"** (#494) zählt alle Einträge des Tages (bei
  geteiltem Dienst Vormittag und Nachmittag, auch nach dem Ausstempeln); das
  Tagessoll folgt Feiertag, ganztägiger Abwesenheit und Sondertag – kein rotes
  „Noch nicht eingestempelt" mehr an freien Tagen.
- **„Arbeitstage" am Abwesenheitsantrag** (#496) zählt nach derselben Regel wie
  die Buchung (Tagesplan, Halbtage, freie Sondertage).
- **Exporte: Tages-Differenz mit Gutschrift, geteilte Dienste sichtbar**
  (#497, #498) – ein Krank- oder Fortbildungstag steht bei ±0, die Summe der
  Spalte ergibt den „Saldo Monat"; neue Spalten „Unterbrechung (Min)" und
  „Zeiteinträge".
- **Pausenpflicht beim Ausstempeln über den ganzen Tag** (#499) – auch zwei
  aneinandergereihte Einträge zählen zusammen; ein neuer Schalter in den
  Einstellungen schaltet die Ausnahme „Pflicht-Pause war nicht möglich" ab.
- **Jahresend-Warnung zu offenem Urlaub** (#501) erst ab einem ganzen offenen Tag.
- **§10-Ausnahmegrund** auch im Antragsformular der Zeiterfassung und bei der
  Direkteingabe an Feiertagen (#491).

### 🐞 Weitere Korrekturen
- **„Letzte Einträge"** auf dem Smartphone zeigt die neuesten statt der ältesten
  Einträge (#493).
- **Schichtplan-Aushang** zeigt on-prem den Praxisnamen statt „Default" (#495).
- **Konto deaktivieren/reaktivieren** gleichzeitig durch zwei Admins führte zu
  doppelten oder fehlenden Protokollzeilen (#491).

### 🔧 Technik
- `deploy.sh` und die Update-Anleitung im Docker-Paket ziehen die Basis-Images
  beim Bauen neu (Debian/Alpine-Sicherheitsupdates); der Rollback startet die
  vorherigen Images, statt neu zu bauen (#491).
- Prometheus 3.12.0 → 3.13.4 (LTS) (#491).
- macOS-Build prüft die Mach-O-Abhängigkeiten aller ausgelieferten Bibliotheken
  (#482).
- Ungültige Kennungen in Anfragen werden zusätzlich als Warnung protokolliert
  (#491).

### 📖 Dokumentation
- Handbücher, Kurzanleitungen, In-App-Hilfe, Schnellstart, Berechnungs-Doku und
  Glossar beschreiben Arbeitszeit-Blöcke, Kappung, Rückwirkung, Schutzpaket,
  Anerkennen und „Anrechnung beantragen" – mit Hinweisen zur Vergütung
  (§ 611a, § 612 BGB; MiLoG) und zur Mitbestimmung (§ 87 BetrVG).
- Neues Prüfskript `scripts/check-doc-sync.sh` hält die fünf Doku-Flächen
  zusammen (Teil von `scripts/local-ci.sh`).

````

- [ ] **Step 4: Prüfen und Commit**

Run: `bash scripts/check-doc-sync.sh changelog`
Expected: `OK: changelog`.

```bash
git add scripts/check-doc-sync.sh CHANGELOG.md
git commit -F - <<'EOF'
docs(changelog): Entwurf 1.20.0 – Arbeitszeit-Blöcke und Issue-Lanes

Neue Funktion, geändertes Verhalten (Auto-Close kappt, rückwirkende
Erhöhung braucht Grund, Puffer je Eintrag, Seite neu laden, Downgrade aus
der Hülle), mitbehobene Fehler und die Lanes #482, #491, #493–#501.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 13: Gesamtprüfung, local-ci-Schritt und PR

**Files:**
- Modify: `scripts/local-ci.sh` (Kopfkommentar Zeilen 19–28, neuer Schritt vor `# 1. Backend pytest`)

**Interfaces:**
- Consumes: alle Gruppen aus Tasks 0–12, `DocViewer.test.tsx` (Task 8), `.git/pr4-base` (Task 0).
- Produces: Schritt „0. Doku-Abgleich" in `scripts/local-ci.sh`; PR `docs/bloecke-pr4` gegen den Integrationszweig.

- [ ] **Step 1: Schritt 0 in local-ci.sh**

Im Kopfkommentar unter `# Steps:` vor `#   1. Backend pytest             (unit + integration, SQLite-backed)` einfügen:

```bash
#   0. Doku-Abgleich              (scripts/check-doc-sync.sh all — Spiegel,
#                                  Anker, Pflichtbegriffe, zitierte Wortlaute;
#                                  braucht kein Docker)
```

Direkt vor dem Block, der mit `# 1. Backend pytest (SQLite-backed unit + integration tests)` beginnt (also vor dessen Trennkommentarzeile `# ---…`), einfügen:

```bash
# -----------------------------------------------------------------------
# 0. Doku-Abgleich (fünf Sync-Flächen, Spiegel, Anker, zitierte Wortlaute)
# -----------------------------------------------------------------------
step "Doku-Abgleich (scripts/check-doc-sync.sh all)"
if bash scripts/check-doc-sync.sh all; then
    ok "Doku-Abgleich OK"
else
    fail "Doku-Abgleich: Abweichungen siehe oben"
fi

```

Run: `bash -n scripts/local-ci.sh && echo syntax-ok`
Expected: `syntax-ok`.

- [ ] **Step 2: Alle Doku-Gruppen**

Run: `bash scripts/check-doc-sync.sh all`
Expected: eine Zeile `OK: admin_aendern admin_bloecke admin_rest berechnungen changelog claude code kurz links mirror mitarbeiter technik` (Reihenfolge wie `declare -F`), Exit 0.

- [ ] **Step 3: Frontend komplett**

Run (aus `frontend/`):
- `npx vitest run --pool=threads` → Expected: alle Testdateien grün, darunter `src/components/DocViewer.test.tsx (4 tests)`.
- `npx tsc --noEmit` → Expected: Exit 0.
- `npm run lint` → Expected: keine Fehler.

- [ ] **Step 4: Backend-Stichprobe (nur wenn Task 1 Code geändert hat)**

Run (Repo-Wurzel, vorher `rm -f backend/test.db backend/test.db-wal backend/test.db-shm`): der `docker run …`-Befehl aus den Global Constraints mit `tests/test_497_498_export_day_rows.py` und jeder weiteren Testdatei, die Task 1 Step 2 geändert hat (z. B. `tests/test_export_uncredited_column.py`, falls vorhanden).
Expected: PASS. (Wurde Task 1 übersprungen: entfällt.)

- [ ] **Step 5: Ergebnis kontrollieren**

```bash
git log --oneline "$(cat .git/pr4-base)"..HEAD
git diff --stat "$(cat .git/pr4-base)"...HEAD
git status --short
```

Expected: die Commits der Tasks 0–12 plus dieser; im Diff nur die Dateien aus der Dateistruktur; `git status` sauber.

- [ ] **Step 6: Commit, Push, PR**

```bash
git add scripts/local-ci.sh
git commit -F - <<'EOF'
ci: Doku-Abgleich als Schritt 0 von local-ci.sh

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git push -u origin docs/bloecke-pr4
gh pr create --base "$(cat .git/pr4-base)" --head docs/bloecke-pr4 \
  --title "Arbeitszeit-Blöcke PR4: Doku, CLAUDE.md, Screenshots, Release-Notes" \
  --body-file - <<'EOF'
## Inhalt
PR4 der Arbeitszeit-Blöcke (Spec `docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md`, Abschnitt 16 und 20):

- Admin- und Mitarbeiter-Handbuch, Kurzanleitungen, Schnellstart, BERECHNUNGEN, GLOSSAR (Sync-Fläche 1) inkl. Vergütungs-, Mitbestimmungs- und JArbSchG-Hinweis
- In-App-Hilfe (DocViewer, Kontexthilfe, Schnellstart; Flächen 2 und 5) mit Vitest
- Download-Spiegel `frontend/public/help` byte-identisch (Fläche 3)
- Technik-Doku (Backend-Architektur, ARC42, README, Verarbeitungsverzeichnis, UPDATE.md), CLAUDE.md-Regeln
- Screenshots 16/17 mit Demo-Person (Seed), CHANGELOG-Entwurf 1.20.0
- #498-Spalte heißt „Zeiteinträge" (falls nicht schon in PR2)
- `scripts/check-doc-sync.sh` (Gate gegen den Code, Spiegel, Anker, Begriffe) als Schritt 0 von `local-ci.sh`

Die pzweb-Web-Anleitungen kommen als eigener PR in phash/pzweb (Merge erst mit dem Release).

## Prüfung
- `bash scripts/check-doc-sync.sh all` grün
- `cd frontend && npx vitest run --pool=threads`, `npx tsc --noEmit`, `npm run lint` grün

## Release-Gate (Spec 17.8, Risiko 6)
Migration `073_work_blocks` löscht Spalten. Vor dem Release 1.20.0 muss `/buildrelease` nach dem Update auf 073 auf .131 **nativ** (`install.sh`-Update) **und** mit dem **Docker-Bundle** einen echten Login, clock-in und clock-out sowie `GET /api/admin/users` mit einer Altfenster-Person (07:37/23:59) prüfen. Unit-Tests, `validate-release.sh` und die Byte-Identitäts-Probe (PR1 Task 17) ersetzen das nicht. Als Pflichtbegriff in `CLAUDE.md` abgesichert (`check-doc-sync.sh`, Gruppe `claude`).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

Expected: PR-URL in der Ausgabe.

---
### Task 14: pzweb – Web-Anleitungen zu den Arbeitszeit-Blöcken (eigener PR, Teil 1)

Sync-Fläche (4). Repo `/home/manuel/claude/pzweb`, eigene Tests, eigene Zweig-/PR-Regeln (`main`). Die drei Seiten spiegeln `HANDBUCH-ADMIN.md`, `HANDBUCH-MITARBEITER.md` und `BERECHNUNGEN.md` (Tasks 2–7) in kuratierter Form.

**Files:**
- Modify: `/home/manuel/claude/pzweb/frontend/src/pages/marketing/anleitung/HandbuchAdmin.tsx` (bei `3d1f87d`: §2 Zeilen 173–178, 223–297, 299–352; §3 Zeilen 432–477; §4 Zeilen 479–511; §7 Zeilen 601–642)
- Modify: `…/anleitung/HandbuchMitarbeiter.tsx` (§2 Zeilen 105–169, §3 Zeilen 198–219, §8 Zeilen 432–436)
- Modify: `…/anleitung/AnleitungBerechnungen.tsx` (§2 Zeilen 134–256, §3 Zeilen 258–272)
- Modify: `…/anleitung/HandbuchAdmin.test.tsx`, `…/anleitung/HandbuchMitarbeiter.test.tsx`
- Create: `…/anleitung/AnleitungBerechnungen.test.tsx`

**Interfaces:**
- Consumes: Wortlaute aus Tasks 2–8; Komponenten der Seiten (`SectionCard`, `SubHeading`, `Bullet`, `Table`/`Th`/`Td`, `Formula`) – jeweils lokal in der Datei definiert.
- Produces: pzweb-Zweig `docs/web-anleitungen-1.20.0` mit den Block-Inhalten; Task 15 setzt darauf auf.

- [ ] **Step 1: Zweig anlegen**

```bash
cd /home/manuel/claude/pzweb
git status --short
git switch main && git pull --ff-only
git switch -c docs/web-anleitungen-1.20.0
```

Expected: sauberer Stand, neuer Zweig.

- [ ] **Step 2: Tests schreiben (rot)**

1. `HandbuchAdmin.test.tsx`: den Test `it('covers the #431 daily-plan hours history (dialog, two modes, per-absence audit)', …)` ersetzen durch:

```tsx
  it('covers the hours history dialog (three modes, per-absence audit)', () => {
    renderPage();
    expect(screen.getAllByText(/Arbeitszeit & Wochenstunden/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Nach Tagen/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/je nachgezogener Abwesenheit/).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/Wochenstunden & Tagesplan/)).toHaveLength(0);
    expect(screen.queryAllByText(/Wochenstunden anpassen…/)).toHaveLength(0);
  });

  it('covers the 1.20.0 work blocks (gap rule, credit, protection, legal notes)', () => {
    renderPage();
    expect(screen.getByText('Arbeitszeit-Blöcke (ab Version 1.20.0)')).toBeInTheDocument();
    expect(screen.getAllByText(/Nach Arbeitsblöcken/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Nicht angerechnet \(Min\)/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Anerkennen/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Falsche Stempelzeiten bitte am Zeiteintrag korrigieren/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Nichtanrechnung ersetzt keine Vergütungsentscheidung/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/§ 87 Abs\. 1 Nr\. 2 BetrVG/).length).toBeGreaterThan(0);
  });
```

2. `HandbuchMitarbeiter.test.tsx`: vor `it('renders an external link to HANDBUCH-MITARBEITER.md', …)` einfügen:

```tsx
  it('covers the 1.20.0 work blocks (gap, credit request, profile card)', () => {
    renderPage();
    expect(screen.getByText('Arbeitszeit-Blöcke und Anrechnung')).toBeInTheDocument();
    expect(screen.getAllByText(/zwischen den Blöcken nicht angerechnet/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Anrechnung beantragen/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Meine Arbeitszeit/).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/Soll-Arbeitszeit-Fenster/)).toHaveLength(0);
  });

```

3. Neue Datei `AnleitungBerechnungen.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AnleitungBerechnungen } from './AnleitungBerechnungen';

function renderPage() {
  return render(
    <MemoryRouter>
      <AnleitungBerechnungen />
    </MemoryRouter>,
  );
}

describe('AnleitungBerechnungen', () => {
  it('covers the 1.20.0 work blocks (daily target, gap deduction, dialog name)', () => {
    renderPage();
    expect(screen.getByText('Tagesplan aus Arbeitszeit-Blöcken (ab Version 1.20.0)')).toBeInTheDocument();
    expect(screen.getByText('Ist = (Ende − Beginn) − Pause − nicht angerechnete Lückenzeit')).toBeInTheDocument();
    expect(screen.getAllByText(/Arbeitszeit & Wochenstunden/).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/Wochenstunden & Tagesplan/)).toHaveLength(0);
  });
});
```

Run: `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx vitest run src/pages/marketing/anleitung --pool=threads`
Expected: FAIL in den drei neuen/geänderten Tests (z. B. `Unable to find an element with the text: Arbeitszeit-Blöcke (ab Version 1.20.0)`), die übrigen Tests grün.

- [ ] **Step 3: HandbuchAdmin.tsx**

1. §2, Absatz „Diese Angaben lassen sich nur **beim Anlegen** direkt eintragen …": `Später ändern Sie Wochenstunden, Tagesstunden, Modus und` / `Arbeitstage ausschließlich über den Dialog „Wochenstunden anpassen…"` (über zwei Zeilen umbrochen) → `Später ändern Sie Wochenstunden, Tagesstunden, Arbeitszeit-Blöcke, Modus und Arbeitstage ausschließlich über den Knopf „Arbeitszeit anpassen…"`.
2. `Arbeitszeit ändern (Dialog „Wochenstunden &amp; Tagesplan" mit „Gültig ab")` → `Arbeitszeit ändern (Dialog „Arbeitszeit &amp; Wochenstunden" mit „Gültig ab")`; im Absatz darunter `<strong>„Wochenstunden anpassen…"</strong>` → `<strong>„Arbeitszeit anpassen…"</strong>`. Außerdem im Absatz unter `<SubHeading>Feste Monatsarbeitszeit (Minijob-Modus)</SubHeading>`: `über den Dialog „Wochenstunden anpassen…" (Modus „Nach Tagen") mit` → `über den Knopf „Arbeitszeit anpassen…" (Modus „Nach Tagen") mit`. Danach darf `grep -nF -e 'Wochenstunden anpassen' frontend/src/pages/marketing/anleitung/*.tsx` nur noch Treffer in Testdateien zeigen.
3. Den ersten `<Bullet>` der Liste darunter (beginnt mit `<strong>Zwei Modi:</strong>`) ersetzen durch:

```tsx
          <Bullet>
            <strong>Drei Modi:</strong> „Gleichmäßig" (Wochenstunden + Arbeitstage pro Woche), „Nach Tagen" (Stunden je Wochentag Mo–Fr) oder „Nach Arbeitsblöcken" (bis zu drei Blöcke je Wochentag plus Pause innerhalb der Blöcke; der Dialog zeigt je Tag „Gesamtzeit · Pause · Tagessoll" und die Wochensumme). Wochensumme und Arbeitstage leitet der Dialog ab; auch der Wechsel zwischen den Modi läuft über diesen Dialog.
          </Bullet>
```

4. Nach dem `<Bullet>`, der mit `<strong>Bereits gebuchte Abwesenheiten</strong>` beginnt, einfügen:

```tsx
          <Bullet>
            <strong>Erfasste Einträge rechnen rückwirkend neu (ab 1.20.0):</strong> Liegt das Gültig-ab-Datum in der Vergangenheit, werden Einträge an Wochentagen mit geänderten Blöcken vom ursprünglichen Stempel aus neu gekappt – mit dem aktuellen Puffer; danach folgen die Abwesenheiten. Übersprungen (und einzeln genannt) werden u. a. der offene Eintrag von heute, Sonn- und Feiertage und anerkannte Einträge. Die Vorschau zeigt die Einträge je Monat alt → neu und getrennt die Änderung von Soll, angerechneter Zeit und Überstundenkonto.
          </Bullet>
          <Bullet>
            <strong>Schutz gegen rückwirkende Verkürzung:</strong> Verliert ein Eintrag angerechnete Zeit, sinkt das Überstundenkonto (auch durch ein höheres Soll) oder sinkt eine Abwesenheits-Gutschrift stärker als das Tagessoll, gilt die Änderung standardmäßig „ab heute". Rückwirkend nur mit Grund („Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)", „Mit der beschäftigten Person vereinbart" oder „Sonstiges"), Begründung und Bestätigung zum Vergütungsrisiko; in abgeschlossene Jahre gesperrt. Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit. Seit 1.20.0 gilt das auch für eine rückwirkende Erhöhung der Wochenstunden, die das Konto senkt.
          </Bullet>
```

5. Den `<Bullet>`, der mit `Das <strong>Löschen</strong> einer Änderung rechnet denselben` beginnt, ersetzen durch:

```tsx
          <Bullet>
            Das <strong>Löschen</strong> einer Änderung rechnet denselben Zeitraum wieder zurück. Würde das Löschen rückwirkend verkürzen, setzt PraxisZeit standardmäßig ab heute auf den vorherigen Stand zurück (neue Verlaufszeile); rückwirkendes Löschen nur mit Grund und Bestätigung. Die früheste Änderung lässt sich nicht löschen, solange spätere bestehen – sie hält die davor gültige Regelung fest.
          </Bullet>
```

6. Im `<Bullet>`, der mit `<strong>Im Änderungsprotokoll</strong> erscheint neben der` beginnt, vor dem schließenden `</Bullet>` anfügen: ` Je neu berechnetem Eintrag steht dort außerdem eine Zeile „Neukappung (Arbeitszeit-Änderung)"; Mitarbeitende sehen nach jeder Änderung 30 Tage lang einen Hinweis auf ihrem Dashboard.`
7. Im Fallstrick-`<Bullet>` (beginnt mit `⚠️ <strong>Fallstrick:</strong>`) `Verschieben Sie im Modus „Nach Tagen" Stunden` → `Verschieben Sie im Modus „Nach Tagen" oder „Nach Arbeitsblöcken" Stunden`.
8. Den Block von `<SubHeading>Soll-Arbeitszeit-Fenster</SubHeading>` bis **ausschließlich** `<SubHeading>Minijob-Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)</SubHeading>` ersetzen durch:

```tsx
        <SubHeading>Arbeitszeit-Blöcke (ab Version 1.20.0)</SubHeading>
        <p>
          Seit Version 1.20.0 hinterlegen Sie die Soll-Arbeitszeit je Wochentag (Mo–Fr) als <strong>bis zu drei Arbeitszeit-Blöcke</strong> – z. B. Montag 08:00–12:00 und 15:00–18:00 – plus eine <strong>„Pause innerhalb der Blöcke"</strong>. Daraus folgt das <strong>Tagessoll</strong> (Summe der Blöcke minus Pause: 08–12 + 15–18 mit 30 Minuten Pause = 6:30 h); Wochenstunden und Arbeitstage werden abgeleitet. Gepflegt wird mit Wirkungsdatum im Dialog „Arbeitszeit &amp; Wochenstunden" (Modus <strong>„Nach Arbeitsblöcken"</strong>), beim Anlegen direkt im Formular.
        </p>
        <p>
          Gestempelte Zeit <strong>vor dem ersten, nach dem letzten und zwischen den Blöcken</strong> wird nicht angerechnet – mit dem Puffer aus den Einstellungen (Standard 15 Minuten) an <strong>jedem</strong> Blockrand. Beispiel: Blöcke 08:00–12:00 und 15:00–18:00, durchgestempelt 08:00–18:00 → angerechnet werden 08:00–12:15 und 14:45–18:00 = <strong>7:30 h</strong>, die 2:30 h dazwischen nicht. Die Stempel bleiben gespeichert (§ 16 ArbZG). Wer um 12:05 ausstempelt, verliert nichts; eine Lücke bis zum doppelten Puffer wird voll angerechnet. Keine Kappung an Tagen ohne Block, an Wochenenden, Feiertagen und „freien" Sondertagen, bei Mitarbeitenden ohne Stundenzählung und bei anerkannten Einträgen; §18-befreite werden trotzdem gekappt. Ein vergessenes Ausstempeln (automatisch um 23:59 geschlossen) wird nur bis zum letzten Block plus Puffer angerechnet.
        </p>
        <p>
          Beim Speichern meldet PraxisZeit, was nicht angerechnet wird – etwa „Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert." Der Eintrag wird trotzdem gespeichert. Ein Lückenabschnitt ab 15 Minuten zählt für die Pausenpflicht als Pause; wer zusätzlich eine Pause einträgt, bekommt den Hinweis „Pause in der Lücke wird zusätzlich abgezogen".
        </p>
        <p>
          <strong>Bisherige Arbeitszeit-Fenster:</strong> Das Update übernimmt jedes frühere Soll-Fenster als einen Block je Tag. Es kappt weiter wie vorher, ändert aber das Soll nicht („Arbeitszeit-Fenster (Altbestand, nur Kappung)") und lässt sich im Dialog in Blöcke umwandeln oder entfernen.
        </p>

        <SubHeading>Nicht angerechnete Zeit: sichtbar und anerkennbar</SubHeading>
        <p>
          Unter jedem gekappten Eintrag steht eine Zusatzzeile, z. B. „gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet" – im Admin-Dashboard, im Monatsjournal und in der Zeiterfassung. Das Monatsjournal summiert die Zeile „Anwesenheit nicht angerechnet", die Exporte haben die letzte Spalte „Nicht angerechnet (Min)". Wurde tatsächlich gearbeitet, klicken Sie am Eintrag auf <strong>„Anerkennen"</strong>: Die ganze gestempelte Zeit zählt dann dauerhaft, auch nach späteren Neuberechnungen; der Vorgang steht als „Anrechnung anerkannt" im Änderungsprotokoll. Mitarbeitende können die Anrechnung über <strong>„Anrechnung beantragen"</strong> selbst beantragen.
        </p>
        <p>
          <strong>Vergütung:</strong> Nichtanrechnung ersetzt keine Vergütungsentscheidung. Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde oder zur Erledigung der Arbeit notwendig war, ist zu vergüten (§ 611a Abs. 2, § 612 Abs. 1 BGB; MiLoG). Wurde vor, nach oder zwischen den Blöcken gearbeitet, nutzen Sie „Anerkennen"; wurde nur ein Teil gearbeitet, den Eintrag aufteilen oder korrigieren statt die ganze Zeit anzuerkennen.
        </p>
        <p>
          <strong>Arbeitsrecht und Mitbestimmung:</strong> Ändert sich durch die Blöcke der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und braucht das Einverständnis der beschäftigten Person (sonst Änderungskündigung, § 2 KSchG; bei Teilzeit §§ 8, 9 TzBfG). Die Lage kann, soweit der Vertrag sie nicht festlegt, im Rahmen des Direktionsrechts (§ 106 GewO) nach billigem Ermessen und mit angemessener Ankündigung nur für die Zukunft geändert werden (Arbeit auf Abruf: mindestens 4 Tage vorher, § 12 Abs. 3 TzBfG). Vereinbarte Arbeitszeiten und Ruhepausen sind wesentliche Vertragsbedingungen (§ 2 Abs. 1 Satz 2 Nr. 7 NachwG); eine Änderung ist spätestens am Tag des Wirksamwerdens schriftlich mitzuteilen (§ 3 NachwG). Mit Betriebsrat sind Lage, Verteilung und Pausen (§ 87 Abs. 1 Nr. 2 BetrVG), vorübergehende Änderungen der betriebsüblichen Arbeitszeit (Nr. 3) und die Kappung als technische Einrichtung (Nr. 6) mitbestimmungspflichtig; ohne Zustimmung ist die Maßnahme gegenüber den Beschäftigten unwirksam. PraxisZeit prüft das nicht.
        </p>
        <p>
          Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG: 30 Min Pause ab 4,5 h, 60 Min ab 6 h, höchstens 4,5 h ohne Pause, Schichtzeit inklusive Lücke höchstens 10 h); PraxisZeit prüft diese nicht.
        </p>

```

9. §3 „Berichte & Exporte": vor dem Absatz, der mit `<strong>Stundenänderungen im Berichtszeitraum:</strong>` beginnt, einfügen:

```tsx
        <p>
          <strong>Nicht angerechnete Zeit (ab 1.20.0):</strong> Excel, ODS und PDF haben als letzte Spalte „Nicht angerechnet (Min)" – je Tag die gestempelte, aber nicht angerechnete Zeit: die Lücke zwischen den Arbeitszeit-Blöcken und die vor dem ersten bzw. nach dem letzten Block abgeschnittene Zeit. Netto ist die angerechnete Zeit; „Von"/„Bis" zeigen die gekürzten Zeiten. Beispiel: gestempelt 07:00–19:00 bei Blöcken 08–12 + 15–18 → Von 07:45, Bis 18:15, Netto 8,00, Nicht angerechnet 240.
        </p>
```

   Im Absatz `<strong>Stundenänderungen im Berichtszeitraum:</strong>` nach `Std/Woche auf 4 Arbeitstage")` einfügen: `, bei Arbeitszeit-Blöcken „ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche"`.
10. §4 „Urlaubs- und Änderungsanträge": `Kappung auf das Arbeitszeit-Fenster` → `Kappung durch die Arbeitszeit-Blöcke`; vor dem schließenden `</SectionCard>` des Abschnitts einfügen:

```tsx
        <p>
          <strong>Anrechnung beantragt (ab 1.20.0):</strong> Bei einem Antrag „Anrechnung beantragen" bedeutet Genehmigen <strong>Anerkennen</strong> – die ganze gestempelte Zeit des Eintrags zählt, dauerhaft. Bei anderen Anträgen zu Einträgen mit nicht angerechneter Zeit gibt es zusätzlich „genehmigen und anerkennen".
        </p>
```

11. §7 „ArbZG-Berichte & Compliance": vor dem Absatz, der mit `<strong>Konto-Vorgänge (seit 1.19.3):</strong>` beginnt, einfügen:

```tsx
        <p>
          <strong>Angerechnet und laut Stempel (ab 1.20.0):</strong> Die Sperren nach § 3 und § 4 rechnen mit der angerechneten Zeit; eine Lücke ab 15 Minuten zwischen zwei Arbeitszeit-Blöcken zählt als Pause. Damit eine Kappung keinen Verstoß verdeckt, weisen zusätzliche Hinweise auf die Anwesenheit laut Stempel hin (über 10 Stunden am Tag, durchgestempelt ohne Pause, über 48 Stunden in der Woche); die 24-Wochen-Auswertung zeigt einen zweiten Wert „Anwesenheit laut Stempel". Das Änderungsprotokoll führt Arbeitszeit-Änderungen mit einer Zeile „Neukappung (Arbeitszeit-Änderung)" je neu berechnetem Eintrag und Anerkennungen als „Anrechnung anerkannt".
        </p>
```

- [ ] **Step 4: HandbuchMitarbeiter.tsx**

1. §2: In der `<ul>` am Abschnittsende vor dem schließenden `</ul>` einen `<Bullet>` einfügen:

```tsx
          <Bullet>
            <strong>Hinweis bei Änderungen Ihrer Arbeitszeit:</strong> Ändert die Verwaltung Ihre Arbeitszeit, steht 30 Tage lang ein Hinweis auf dem Dashboard, z. B. „Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: …)". Die heute gültigen Blöcke und den Verlauf zeigt Profil → „Meine Arbeitszeit".
          </Bullet>
```

2. §3: Den Block von `<SubHeading>Soll-Arbeitszeit-Fenster</SubHeading>` bis vor das schließende `</SectionCard>` des Abschnitts (beide Absätze) ersetzen durch:

```tsx
        <SubHeading>Arbeitszeit-Blöcke und Anrechnung</SubHeading>
        <p>
          Hat Ihre Praxis Ihre Arbeitszeit als <strong>Arbeitszeit-Blöcke</strong> hinterlegt (z. B. Montag 08:00–12:00 und 15:00–18:00), ergibt sich Ihr Tagessoll aus den Blöcken. Angerechnet wird Ihre gestempelte Zeit innerhalb der Blöcke, mit einem Puffer (Standard 15 Minuten) an jedem Blockrand. Zu früh oder zu spät gestempelte Zeit zählt nicht – Sie sehen dann z. B. „gestempelt 07:30 · angerechnet ab 07:45". Stempeln Sie über die Pause zwischen zwei Blöcken durch, wird diese Lücke nicht angerechnet: „gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet". In der Pause zwischen den Blöcken zeigt Ihr Dashboard neutral „Pause zwischen den Arbeitsblöcken". An Wochenenden und Feiertagen gelten keine Blöcke – Arbeit dort (z. B. Notdienst) wird voll angerechnet.
        </p>
        <p>
          Beim <strong>Ausstempeln</strong> und beim Speichern eines eigenen Eintrags erscheint ein Hinweis, sobald etwas nicht angerechnet wird; Ihr Eintrag wird trotzdem gespeichert. Ihre tatsächliche Stempelzeit bleibt immer erhalten (§ 16 ArbZG). Haben Sie außerhalb oder zwischen den Blöcken gearbeitet, wählen Sie am Eintrag <strong>„Anrechnung beantragen"</strong> und begründen kurz; genehmigt die Verwaltung, zählt die ganze gestempelte Zeit, und der Eintrag ist „anerkannt" – ändern lässt er sich danach nur noch per Antrag. Nicht angerechnet heißt nicht unbezahlt: Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist zu vergüten (§ 611a, § 612 BGB; Mindestlohngesetz).
        </p>
```

3. §8: `hinterlegten Stammdaten (Name, Rolle, Wochenstunden, Urlaubstage).` → `hinterlegten Stammdaten (Name, Rolle, Urlaubstage). Die Karte <strong>„Meine Arbeitszeit"</strong> zeigt Ihre heute gültigen Arbeitszeit-Blöcke mit Tagessoll, Ihre Wochenstunden und den Verlauf mit Wirkungsdaten.` (PR2-Gesamtreview Fund 10: die Wochenstunden stehen seit PR2 nicht mehr in den Stammdaten des Profils, sondern in der Karte.)

- [ ] **Step 5: AnleitungBerechnungen.tsx**

1. §2: vor `<SubHeading>` „Arbeitszeit ändern (Stundenhistorie – ab Version 1.18.0 auch für Tagespläne)" einfügen:

```tsx
        <SubHeading>Tagesplan aus Arbeitszeit-Blöcken (ab Version 1.20.0)</SubHeading>
        <Formula>Tagessoll = Σ Blockdauer − Pause innerhalb der Blöcke</Formula>
        <p>
          Im Modus „Nach Arbeitsblöcken" pflegt die Verwaltung je Wochentag bis zu drei Blöcke und eine Pause innerhalb der Blöcke. Beim Speichern wird daraus der Tagesplan abgeleitet und gespeichert (auf zwei Nachkommastellen gerundet): 08:00–12:00 + 15:00–18:00 mit 30 Minuten Pause ergibt 6,50 h, 08:00–12:05 ohne Pause 4,08 h. Wochenstunden = Summe der Tage, Arbeitstage = Tage mit Blöcken. Danach rechnet alles wie beim individuellen Tagesplan.
        </p>

```

2. Im Absatz unter „Arbeitszeit ändern …": `Dialog <strong>„Wochenstunden &amp; Tagesplan"</strong> mit einem` → `Dialog <strong>„Arbeitszeit &amp; Wochenstunden"</strong> (Knopf „Arbeitszeit anpassen…") mit einem`.
3. Den `<Bullet>`, der mit `<strong>Zwei Modi im selben Dialog:</strong>` beginnt, ersetzen durch:

```tsx
          <Bullet>
            <strong>Drei Modi im selben Dialog:</strong> „Gleichmäßig" (Wochenstunden + Arbeitstage pro Woche), „Nach Tagen" (Stunden je Wochentag Mo–Fr, in Viertelstunden) oder „Nach Arbeitsblöcken" (Blöcke + Pause, siehe oben). Wochensumme und Arbeitstage leitet der Dialog ab; auch der Wechsel zwischen den Modi läuft über diesen Dialog und trägt ein Wirkungsdatum.
          </Bullet>
          <Bullet>
            <strong>Rückwirkend werden auch erfasste Einträge neu gekappt (ab 1.20.0)</strong> – vom ursprünglichen Stempel aus, nur an Wochentagen mit geänderten Blöcken, mit dem aktuellen Puffer; danach folgen die Abwesenheiten. Sinkt dabei angerechnete Zeit oder das Überstundenkonto (auch durch ein höheres Soll), ist die Änderung eine Verkürzung: Standard „ab heute", rückwirkend nur mit Grund und Bestätigung, in abgeschlossene Jahre gesperrt.
          </Bullet>
```

4. §3: `<Formula>Ist = (Ende − Beginn) − Pause</Formula>` → `<Formula>Ist = (Ende − Beginn) − Pause − nicht angerechnete Lückenzeit</Formula>`; den Absatz darunter (beginnt mit `Pro Zeiteintrag, auf 2 Nachkommastellen gerundet`) bis zu `<strong>Fortbildung</strong> mit ihren gebuchten Stunden als Ist (§ 3 EntgFG).` ersetzen durch:

```tsx
        <p>
          Pro Zeiteintrag, auf 2 Nachkommastellen gerundet und <strong>nie negativ</strong>. Sind Arbeitszeit-Blöcke hinterlegt, werden Beginn und Ende auf den ersten Block minus Puffer bzw. den letzten Block plus Puffer gekürzt, und Zeit zwischen den Blöcken (an beiden Rändern um den Puffer geschrumpft) wird abgezogen – Beispiel: Blöcke 08–12 + 15–18, Puffer 15 Minuten, gestempelt 08:00–18:00 → 7,50 h. Der tatsächlich gestempelte Rohwert bleibt erhalten (§ 16 ArbZG); PraxisZeit meldet die Kürzung beim Speichern. Keine Kappung an Wochenenden, Feiertagen und als „frei" eingestellten Sondertagen (ein „halber Feiertag" behält die Blöcke) und bei anerkannten Einträgen. Zusätzlich zählen <strong>Krankheit</strong> und <strong>Fortbildung</strong> mit ihren gebuchten Stunden als Ist (§ 3 EntgFG).
        </p>
```

- [ ] **Step 6: Tests und Typen grün**

Run (aus `/home/manuel/claude/pzweb`):
- `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx vitest run src/pages/marketing/anleitung --pool=threads` → Expected: alle Tests grün.
- `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx tsc -b` → Expected: Exit 0.

- [ ] **Step 7: Commit**

```bash
cd /home/manuel/claude/pzweb
git add frontend/src/pages/marketing/anleitung
git commit -F - <<'EOF'
docs(fe): Web-Anleitungen beschreiben Arbeitszeit-Blöcke (PraxisZeit 1.20.0)

Admin-Handbuch: Dialog „Arbeitszeit & Wochenstunden" mit drei Modi,
Blöcke und Lückenregel, Neuberechnung, Verkürzungsschutz, Anerkennen,
Vergütungs-, Mitbestimmungs- und JArbSchG-Hinweis, Export-Spalte „Nicht
angerechnet (Min)". Mitarbeiter-Handbuch: Blöcke, „Anrechnung
beantragen", Profilkarte. So rechnet PraxisZeit: Tagessoll aus Blöcken,
Ist mit Lückenabzug.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 15: pzweb – Issue-Lanes nachziehen, Stand 1.20.0, PR (Teil 2) ⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen

Die Web-Anleitungen stehen bei `3d1f87d` auf 1.19.3 und kennen die Lane-Änderungen aus 1.20.0 noch nicht (#493, #494, #495, #496, #497/#498, #499, #500, #501, #491 F4). Quelle sind die bei `3d46c2f` bereits nachgezogenen Handbücher.

**Files:**
- Modify: `/home/manuel/claude/pzweb/frontend/src/pages/marketing/anleitung/HandbuchAdmin.tsx`, `HandbuchMitarbeiter.tsx`, `AnleitungBerechnungen.tsx`, `HandbuchAdmin.test.tsx`, `HandbuchMitarbeiter.test.tsx`

**Interfaces:**
- Consumes: Zweig `docs/web-anleitungen-1.20.0` aus Task 14.
- Produces: pzweb-PR „Web-Anleitungen auf 1.20.0" (Merge erst mit dem Release).

- [ ] **Step 1: Tests ergänzen (rot)**

1. `HandbuchAdmin.test.tsx`, vor `it('renders an external link to HANDBUCH-ADMIN.md', …)`:

```tsx
  it('covers the 1.20.0 lane changes (export rows, request days, practice name, version)', () => {
    renderPage();
    expect(screen.getAllByText(/Unterbrechung \(Min\)/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Arbeitstage" auf der Antragskarte/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Praxisname/).length).toBeGreaterThan(0);
    expect(screen.getByText('Jahresend-Warnung zu offenem Urlaub')).toBeInTheDocument();
    expect(screen.getAllByText(/Version 1\.20\.0/).length).toBeGreaterThan(0);
  });

```

2. `HandbuchMitarbeiter.test.tsx`, vor `it('renders an external link to HANDBUCH-MITARBEITER.md', …)`:

```tsx
  it('covers the 1.20.0 dashboard and pause changes (week view, whole day)', () => {
    renderPage();
    expect(screen.getByText('Monats- und Wochenübersicht')).toBeInTheDocument();
    expect(screen.getAllByText(/Letzte Einträge/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Der ganze Tag zählt/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Version 1\.20\.0/).length).toBeGreaterThan(0);
  });

```

Run (aus `/home/manuel/claude/pzweb`): `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx vitest run src/pages/marketing/anleitung --pool=threads`
Expected: FAIL in den zwei neuen Tests, Rest grün.

- [ ] **Step 2: Stand 1.20.0**

```bash
cd /home/manuel/claude/pzweb/frontend/src/pages/marketing/anleitung
sed -i 's/Stand 1\.19\.3)/Stand 1.20.0)/' HandbuchAdmin.tsx HandbuchMitarbeiter.tsx AnleitungBerechnungen.tsx
sed -i '/^        lead=/s/Version 1\.19\.3/Version 1.20.0/' HandbuchAdmin.tsx HandbuchMitarbeiter.tsx AnleitungBerechnungen.tsx
grep -nF -e '1.19.3' HandbuchAdmin.tsx HandbuchMitarbeiter.tsx AnleitungBerechnungen.tsx
cd /home/manuel/claude/pzweb
```

Expected: verbleibende Treffer nur in Sätzen der Art „seit Version 1.19.3 …" (historische Angaben), keiner mehr in Kopfkommentar oder `lead=`.

- [ ] **Step 3: HandbuchAdmin.tsx – Lanes**

1. Vor dem schließenden `</SectionCard>` von `<SectionCard title="1. Admin-Dashboard">` einfügen (#501):

```tsx
        <SubHeading>Jahresend-Warnung zu offenem Urlaub</SubHeading>
        <p>
          Im letzten Quartal listet ein gelber Hinweis über der Jahresübersicht alle Mitarbeitenden, die noch <strong>mindestens einen ganzen Urlaubstag</strong> offen haben. Kleinere Reste (z. B. 0,3 oder 0,5 Tage bei Teilzeit) lösen bewusst keine Warnung aus – sie lassen sich nicht als ganzer Tag nehmen und werden üblicherweise im Folgejahr zusammengelegt; im Urlaubskonto und beim Jahresabschluss zählen sie unverändert mit.
        </p>
```

2. §3 „Berichte & Exporte": direkt nach `</Table>` einfügen (#497/#498):

```tsx
        <p>
          <strong>Tageszeilen lesen:</strong> „Netto" ist die angerechnete Arbeitszeit der Zeiteinträge; „Differenz" ist der Saldo des Tages – Netto plus Gutschrift für Krankheit/Fortbildung minus Soll. Ein Krank- oder Fortbildungstag steht damit bei ±0, und die Summe der Spalte ergibt den „Saldo Monat". Bei <strong>geteilten Diensten</strong> zeigen Excel/ODS in „Von"/„Bis" den Rahmen des Tages und in den angehängten Spalten „Unterbrechung (Min)" und „Zeiteinträge" die Zeit zwischen den Einträgen bzw. die einzelnen Einträge; im PDF stehen die Einträge untereinander, die Unterbrechung neben der Pause. Bestehende Spalten bleiben an ihrem Platz.
        </p>
```

3. §4 „Urlaubs- und Änderungsanträge": nach dem ersten Absatz (endet mit `automatisch entfernt.`) einfügen (#496):

```tsx
        <p>
          <strong>„Arbeitstage" auf der Antragskarte</strong> zeigt, wie viele Tage der Antrag nach der Genehmigung tatsächlich kostet – nach denselben Regeln wie die Buchung: nur Tage, an denen die Person laut ihrem zum Datum gültigen Plan arbeitet; Wochenenden, Feiertage und „freie" Sondertage zählen nicht; ein halber Tag und ein „halber Feiertag" zählen 0,5. Mitarbeitende sehen dieselbe Zahl unter „Meine Anträge".
        </p>
```

4. §7 „ArbZG-Berichte & Compliance" (#499): die Tabellenzeile `<tr><Td><strong>§ 4 – Pausenpflicht</strong></Td><Td>30 Min. ab 6h, 45 Min. ab 9h — dokumentierte Ausnahme statt Blockade möglich</Td></tr>` ersetzen durch `<tr><Td><strong>§ 4 – Pausenpflicht</strong></Td><Td>30 Min. ab 6h, 45 Min. ab 9h über den ganzen Tag (Unterbrechungen unter 15 Min. zählen nicht) – Sperre auch beim Ausstempeln; dokumentierte Ausnahme möglich, sofern erlaubt</Td></tr>`. Im Absatz darunter den Satz `Die <strong>Pflicht-Pause-Ausnahme</strong> lässt sich unter … genehmigen).` (über vier Zeilen umbrochen) ersetzen durch: `Die <strong>Pflicht-Pause-Ausnahme</strong> lässt sich unter Einstellungen ganz abschalten (dann lassen sich Tage über 6 bzw. 9 Stunden nur noch mit eingetragener Pause speichern oder ausstempeln, auch für Admins) oder für Einträge in der Zeiterfassung genehmigungspflichtig schalten (4-Augen-Prinzip: ein Admin darf seine eigene Ausnahme nicht selbst genehmigen); beim Ausstempeln wird eine Begründung immer sofort wirksam.`
5. Vor dem schließenden `</SectionCard>` von `<SectionCard title="11. Schichtplanung (optional)">` einfügen (#495):

```tsx
        <p>
          Der <strong>Praxisname</strong> in der Kopfzeile des Aushangs ist der bei der Installation angegebene – nativ der Eintrag <code>name</code> im Abschnitt <code>[practice]</code> der Datei <code>config/praxiszeit.conf</code>, bei Docker <code>PRACTICE_NAME</code> in der <code>.env</code>; er gilt nach einem Neustart des Dienstes. Bis Version 1.19.3 stand dort bei vielen Installationen „Default".
        </p>
```

- [ ] **Step 4: HandbuchMitarbeiter.tsx – Lanes**

1. §2-Tabelle (#494): `<tr><Td><strong>Tagessaldo</strong></Td><Td>Heutige Ist-Zeit vs. Tagessoll</Td></tr>` → `<tr><Td><strong>Tagessaldo</strong></Td><Td>Heutige Ist-Zeit aller Einträge des Tages (bei geteiltem Dienst Vormittag und Nachmittag, auch nach dem Ausstempeln) vs. Tagessoll. An Feiertagen, bei ganztägiger Abwesenheit und an freien Sondertagen gibt es heute kein Tagessoll – dann erscheint kein rotes „Noch nicht eingestempelt"</Td></tr>`
2. §2: nach dem Absatz unter `<SubHeading>Monatssaldo nur bis zum letzten Arbeitstag</SubHeading>` einfügen (#500, #493):

```tsx
        <SubHeading>Monats- und Wochenübersicht</SubHeading>
        <p>
          Über den Umschalter <strong>„Monat / Woche"</strong> über der Übersichtstabelle sehen Sie statt der Monate die <strong>letzten 8 Kalenderwochen</strong> mit Soll, Ist, Saldo und dem Stand Ihres Überstundenkontos am Wochenende. Pro Woche fällt sofort auf, wenn ein Eintrag fehlt oder ein vergessenes Ausstempeln automatisch geschlossen wurde. Die laufende Woche zählt wie der Monatssaldo nur bis heute; Ihre Auswahl bleibt auf dem Gerät gespeichert. Auf dem Smartphone zeigt die Karte „Letzte Einträge" Ihre fünf neuesten Einträge des Monats, der jüngste zuerst.
        </p>

```

3. §2: in der `<ul>` am Abschnittsende vor dem in Task 14 eingefügten Hinweis-`<Bullet>` einfügen (#501):

```tsx
          <Bullet>
            <strong>Hinweis auf offenen Urlaub (ab Oktober):</strong> Das Urlaubskonto weist im letzten Quartal gelb auf noch offene Urlaubstage hin – erst ab einem ganzen offenen Tag; kleinere Reste (z. B. 0,5 Tage bei Teilzeit) lösen keinen Hinweis aus.
          </Bullet>
```

4. §4 „Pausen (§ 4 ArbZG)": vor dem Absatz, der mit `Dieselbe Logik gilt bei einem <strong>Korrekturantrag</strong>` beginnt, einfügen (#499):

```tsx
        <p>
          <strong>Der ganze Tag zählt:</strong> Geprüft werden alle Einträge des Tages zusammen, nicht nur der laufende Abschnitt. Aus- und sofort wieder einstempeln ist keine Pause – eine Unterbrechung zählt erst ab 15 Minuten. Fehlt das Begründungsfeld, hat Ihre Praxis die Ausnahme „Pflicht-Pause war nicht möglich" abgeschaltet; dann klappt das Ausstempeln nur mit eingetragener Pause.
        </p>
```

5. §5 „Abwesenheiten beantragen": nach dem Absatz zur Option „Halber Tag" (endet mit `<strong> 0,5 statt 1,0 Tage</strong>.`) einfügen (#496):

```tsx
        <p>
          Bei einem <strong>Urlaubsantrag</strong> steht neben dem Zeitraum, wie viele Tage er kostet: nur Ihre Arbeitstage (arbeiten Sie mittwochs nicht, kostet eine Woche Montag bis Freitag 4 Tage), ohne Wochenenden, Feiertage und „freie" Sondertage; ein halber Tag und ein „halber Feiertag" zählen je 0,5. Genau so viele Urlaubstage werden nach der Genehmigung gebucht.
        </p>
```

6. §7, Absatz unter `<SubHeading>Arbeit am Wochenende oder Feiertag (z. B. KV-Dienst)</SubHeading>` (#491 F4): `fragt PraxisZeit dabei nach dem{' '}` → `fragt PraxisZeit – beim neuen Eintrag ebenso wie im Antragsformular und im Journal – nach dem{' '}`

- [ ] **Step 5: AnleitungBerechnungen.tsx – Lanes**

1. §7 „Verbrauch" (#496): im `<Bullet>`, der mit `Der <strong>Budget-Check</strong> beim Antrag zählt nur buchbare Arbeitstage` beginnt, vor `</Bullet>` anfügen: ` Dieselbe Zahl steht seit 1.20.0 als „Arbeitstage" am Antrag – nach dem zum jeweiligen Datum gültigen Arbeitsplan, Halbtag und „halber Feiertag" je 0,5, „freie" Sondertage 0.`
2. Vor dem schließenden `</SectionCard>` von `<SectionCard title="6. Saldo und Überstundenkonto">` einfügen (#497):

```tsx
        <p>
          In den Datei-Exporten ist die Tagesspalte <strong>„Differenz"</strong> seit 1.20.0 Netto plus Gutschrift für Krankheit/Fortbildung minus Soll – ein Krank- oder Fortbildungstag steht bei ±0, und die Summe der Spalte ergibt den „Saldo Monat" derselben Datei. Ausnahme: feste Monatsarbeitszeit (Minijob-Modus) – dort ist nur die Zusammenfassung verbindlich.
        </p>
```

- [ ] **Step 6: Tests und Typen grün**

Run (aus `/home/manuel/claude/pzweb`):
- `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx vitest run src/pages/marketing/anleitung --pool=threads` → Expected: alle grün.
- `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx vitest run --pool=threads` → Expected: ganze pzweb-Frontend-Suite grün (u. a. `src/seo/routes.test.ts`, `src/csp.test.ts` unverändert).
- `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx tsc -b` → Expected: Exit 0.

- [ ] **Step 7: Commit, Push, PR**

```bash
cd /home/manuel/claude/pzweb
git add frontend/src/pages/marketing/anleitung
git commit -F - <<'EOF'
docs(fe): Web-Anleitungen auf 1.20.0 – Dashboard, Exporte, Pausen, Anträge

Wochenübersicht und Stempelkarte im Mitarbeiter-Dashboard, „Letzte
Einträge", Jahresend-Hinweis ab einem ganzen Tag, Tages-Differenz mit
Gutschrift und geteilte Dienste in den Exporten, §4 über den ganzen Tag
mit abschaltbarer Ausnahme, „Arbeitstage" am Antrag, Praxisname im
Aushang, §10-Grund im Antragsformular. Stand der Seiten: 1.20.0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git push -u origin docs/web-anleitungen-1.20.0
gh pr create --repo phash/pzweb --base main --head docs/web-anleitungen-1.20.0 \
  --title "docs(fe): Web-Anleitungen auf PraxisZeit 1.20.0 (Arbeitszeit-Blöcke)" \
  --body-file - <<'EOF'
Spiegelt die praxiszeit-Doku für 1.20.0 (HANDBUCH-ADMIN.md, HANDBUCH-MITARBEITER.md, BERECHNUNGEN.md):

- Arbeitszeit-Blöcke: Dialog „Arbeitszeit & Wochenstunden", Lückenregel, Neuberechnung, Verkürzungsschutz, Anerkennen / „Anrechnung beantragen", Export-Spalte „Nicht angerechnet (Min)", Vergütungs-, Mitbestimmungs- und JArbSchG-Hinweis
- Issue-Lanes aus 1.20.0: Wochenübersicht und Stempelkarte, „Letzte Einträge", Jahresend-Hinweis, Exporte (Differenz mit Gutschrift, geteilte Dienste), §4 über den ganzen Tag, „Arbeitstage" am Antrag, Praxisname im Aushang, §10-Grund im Antragsformular

**Erst mit dem Release 1.20.0 mergen.** Vitest (`node:20`) und `tsc -b` grün.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

Expected: PR-URL in der Ausgabe.

---

## Selbstprüfung des Plans (erledigt beim Schreiben)

- **Spec-Abdeckung (16.1/16.2/20 PR4):** Fläche (1) Tasks 2–7, (2)+(5) Task 8, (3) Spiegel in Tasks 2–6, (4) Tasks 14–15; Pflichtinhalte 16.1: Blöcke/Pause/Tagessoll/Puffer mit K1 (Task 2), Wortlaute 6.2 und 13.1 (Tasks 2, 5), Rückwirkung mit Vorschau, Verlängerung, Verkürzung (a)–(c), Standard „frühestes verlustfreies Datum", Schutzpaket mit Beschriftungen, Kürzeln und Hilfetext, Sperre abgeschlossener Jahre, Löschen mit Rücksetzen, Dashboard-Hinweis (Task 3), Puffer je Eintrag (Task 4), offene Alteinträge + Moduswechsel (Task 3), Vergütungs- und Mitbestimmungs-Kasten, JArbSchG, bekannte Grenze (Tasks 2, 3, 8, 14), Mitarbeiter-Handbuch (Task 5), Release-Notes (Task 12), weitere Texte `Reports.tsx`/Kontexthilfe (Task 8; `Profile.tsx` und `Privacy.tsx` sind PR2-Oberfläche und werden in Task 0 über `Meine Arbeitszeit`/Datenschutztext als vorhanden geprüft), Screenshots + Demo-Person (Task 9), Technik-Doku inkl. Verarbeitungsverzeichnis (Task 10), CLAUDE.md-Regeln 1–12 (Task 11), #498-Begriffsfrage aus 15.1 (Task 1).
- **Typen/Namen:** Funktionsnamen werden in Task 7 Step 1 gegen den Code bestätigt und gelten für Tasks 7, 10, 11; Prüfgruppen-Namen (`admin_bloecke`, `admin_aendern`, `admin_rest`, `mitarbeiter`, `kurz`, `berechnungen`, `technik`, `claude`, `changelog`, `code`, `mirror`, `links`) sind in Task 13 Step 2 vollständig aufgezählt.
