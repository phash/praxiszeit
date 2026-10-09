# Arbeitszeit-Blöcke PR1 „Fundament, verhaltensneutral" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Datenmodell, Migration 073, Resolver und Kappungskern auf Arbeitszeit-Blöcke umstellen und alle 13 Schreibpfade (inkl. Ankersperren und Puffer-Herkunft) darauf ausrichten — ohne dass sich für Bestandsdaten Soll, `net_hours` oder Saldo ändern.

**Architecture:** Blöcke leben als JSON im datierten Vertrags-Snapshot (`working_hours_changes.blocks`, Rückfall `users.work_blocks`) und werden ausschließlich über `calculation_service.get_schedule_for_date` aufgelöst. `work_window_service.clamp` liefert ein `ClampResult` (Hülle wie #201, Lücken als `uncredited_minutes`, angewandter Puffer); jede Schreibstelle nimmt zuerst die Ankersperre, speichert `uncredited_minutes`/`clamp_grace_minutes`/`auto_closed` und rechnet §3/§4 auf der angerechneten Zeit. Migration 073 überführt die #201-Fenster in Einblock-Altzeilen (`pause_minutes` NULL) und löscht `users.scheduled_*`; die Benutzer-API lehnt Altfelder mit 400 ab, das UserForm zeigt statt des Fenster-Abschnitts die heute gültigen Blöcke.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, Alembic, PostgreSQL 18 (SQLite in der Unit-Suite), React 18 + TypeScript + Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md` (verbindlich; Abschnitt 20 „PR1", Abschnitt 2 inkl. „Entschieden 2026-10-08", 19.1). Wer einen Task umsetzt, liest die im Task genannten Spec-Abschnitte mit.

## Global Constraints

- PR1 wird **nie allein released**; zwischen PR1 und PR3 **kein Release** (Altfenster sind bis PR3 nicht editierbar). Version 1.20.0 erst nach PR1–PR4 (Spec 20).
- Verhalten nach dem Merge (Spec 20): Altfenster wirken als Einzelblock unverändert (`uncredited_minutes` immer 0, weil Einzelblöcke keine Lücke haben); der Auto-Close kappt jetzt (E42); jeder neu gekappte Eintrag speichert seinen Puffer, eine spätere Puffer-Änderung wirkt bei Bearbeitungen nur noch auf Einträge ohne gespeicherten Wert.
- Migration: Datei `backend/alembic/versions/2026_10_08_1200-073_work_blocks.py`, `revision = "073_work_blocks"`, `down_revision = "072_cr_sunday_reason"`.
- JSON-Form (Spec 3.1) für `working_hours_changes.blocks` **und** `users.work_blocks`: Liste aus genau 5 Einträgen (Index 0 = Mo … 4 = Fr), je `{"blocks": [{"start": "HH:MM", "end": "HH:MM"}, …], "pause_minutes": int | null}`; Zeiten immer als String `"HH:MM"`; Änderung nur per Neuzuweisung des ganzen Werts; fünf leere Tage ≡ NULL (3.3).
- Spalten (Spec 3.2): `users.work_blocks` / `working_hours_changes.blocks` = `JSON().with_variant(JSONB(), "postgresql")`, nullable; `time_entries.uncredited_minutes` INT NOT NULL server_default `'0'`; `time_entries.credit_override` und `time_entries.auto_closed` BOOL NOT NULL server_default `'false'`; `time_entries.clamp_grace_minutes` INT NULL ohne Default; `change_requests.request_credit_override` BOOL NOT NULL server_default `'false'`; `change_requests.original_uncredited_minutes` INT NULL.
- NULL in einer Verlaufszeile heißt „keine Blöcke", **nie** Rückfall auf `users.work_blocks` (E8). `users.work_blocks` ist Rückfall nur vor der ersten Verlaufszeile und Spiegel der jüngsten Zeile ≤ heute (E9).
- `Schedule` bekommt `blocks` und `block_pauses` **ohne** Vorgabewert; `clamp` nimmt `credit_override` als **pflichtiges** Schlüsselwort; `ClampResult` hat genau 6 Felder (altes Entpacken in 4 Variablen scheitert laut, E31).
- `net_hours` = Ende − Beginn − Pause − `uncredited_minutes` (Python-Hybrid **und** SQL-Ausdruck; SQL rundet **nicht** je Zeile, E13/6.1).
- `uncredited_minutes`, `credit_override`, `auto_closed`, `clamp_grace_minutes` sind **nie** Eingabefelder eines Schemas (E11, E79).
- Puffer-Herkunft (E80): Neuanlagen → `get_grace_minutes`; Einzel-Neukappung gespeicherter Einträge → `grace_for_entry`; jede schreibende Stelle setzt `clamp_grace_minutes = r.grace_minutes`, wenn `r.grace_minutes is not None`.
- Ankersperre (P5): in jedem Schreibpfad für Zeiteinträge ist `lock_user_row(db, tenant_id, owner_id)` die erste Sperre — vor `get_grace_minutes`/`grace_for_entry`/Snapshot/`clamp` und vor jedem `with_for_update` auf `time_entries`.
- Kein Code in `backend/app/` enthält das Token `scheduled_start_` oder `scheduled_end_` (Guard-Test, 17.6); `.work_blocks` wird in `app/` nur dort gelesen, wo `tests/test_no_live_work_blocks_read.py` es zulässt (9.8).
- 400-Text für Altfelder (Spec 11.4), wörtlich: „Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) wurden durch Arbeitszeit-Blöcke ersetzt."
- Warntexte: der bisherige Hülle-Text und der Kollaps-Text bleiben **byte-identisch** (ASCII-Umschrift „urspruengliche", „vollstaendig ausserhalb"); neue Lückentexte exakt nach Spec 6.2.
- F-026: jede neue Abfrage auf mandantenbezogene Tabellen trägt `tenant_id == …` zusätzlich zu RLS (E74).
- Backend-Tests **nie** im geteilten Container. Befehl (aus dem Repo-Wurzelverzeichnis, vorher `rm -f backend/test.db backend/test.db-wal backend/test.db-shm`, nie zwei Läufe gleichzeitig — die Suite nutzt `./test.db` im gemounteten `backend/`):
  `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/<datei> -q -p no:cacheprovider`
  In den Schritten steht jeweils der volle Befehl mit konkreter Datei. Die volle SQLite-Suite: dieselbe Zeile mit `tests/ --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py` (dauert ~12 min; vorher `pgrep -af pytest` prüfen).
- Postgres-Läufe (Task 13, 14, 17) gegen eine **Wegwerf-PG18** auf eigenem Docker-Netz, nie gegen den Dev-Stack (Muster CLAUDE.md „Migration Testing"); Verbindungs-URLs aus Teilen bauen (`S="postgres"; S="${S}ql://"`), damit der Pre-Commit-Scanner kein `schema://user:pass@host`-Literal sieht.
- Frontend (aus `frontend/`): `npx vitest run <datei> --pool=threads`, `npx tsc --noEmit`.
- Commit-Nachrichten immer per `git commit -F - <<'EOF' … EOF` (Umlaute/Klammern), letzte Zeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Issue-Lanes: #499 (§4 über aneinandergereihte Einträge + Mandanten-Schalter `break_exception_allowed` → `validate_daily_break`, Schreibpfade), #497/#498 (Exporte, nicht berührt), #493/#494/#500/#501 (Mitarbeiter-Dashboard; #494 baut `get_clock_status` um), #496 (`admin_helpers._enrich_vr_responses`, nicht berührt), #495 (Schichtplan-PDF, nicht berührt), #491 F4 (ChangeRequestForm §10-Feld) und #491 API-2 (Sperren in `admin_users`). Der Plan wurde gegen `b635679` validiert (SQLite-Suite, PG-Suiten, Migration auf PG18, Frontend); die Lanes sind danach in `feat/1.20-issues-bloecke-review` gemergt worden (`3d46c2f`). Zeilennummern beziehen sich auf `b635679`, wo nicht ausdrücklich `3d46c2f` steht. Tasks mit **⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** vor Beginn gegen den Ausführungsstand neu lesen; die bereits gefundenen Abweichungen stehen im Abschnitt „Abgleich mit dem Lane-Merge" und sind in die betroffenen Tasks eingearbeitet.

## Abgleich mit dem Lane-Merge (`b635679` → `3d46c2f`)

Geprüft: jeder Inline-Anker und jeder wörtlich zitierte Altcode-Block dieses Plans existiert bei `3d46c2f` unverändert; Migrationskopf weiter `072_cr_sunday_reason`; dieselben 16 Dateien lesen/schreiben `scheduled_*`; `xls_import_service.py`, `import_xls.py`, `work_window_service.py`, Frontend-Benutzerformular und die beiden E2E-Specs sind unberührt. Eingearbeitet:

| Task | Abweichung bei `3d46c2f` | Folge im Plan |
|---|---|---|
| 2 | `calculation_service.py` +345 Zeilen (#493/#494/#496/#500/#501), neuer Aufrufer `vacation_day_cost_by_year`; Vorschau-`Schedule(...)` in `admin_users.py` jetzt Zeile 1865 | nur Zeilen; Marker mit `grep`-Kontrolle |
| 3–9 | `time_entries.py`: §4 in `clock_out` steht vor dem Schreiben und blockiert über `break_waiver_rejection` (#499); `get_clock_status` liefert `today_net_minutes`/`today_target_hours` (#494) und liest dafür `net_hours` | `net_hours`-Leser folgen dem Hybrid automatisch (in PR1 ist `uncredited_minutes` 0) |
| 5 | `break_validation_service.py` trägt die #499-Helfer `BREAK_EXCEPTION_ALLOWED`, `BREAK_EXCEPTION_DISABLED_HINT`, `is_break_exception_allowed`, `break_waiver_rejection`; `test_issue_499_break_chain.py:304` ruft `validate_daily_break` direkt | Step 3 übernimmt die Helfer wörtlich; Step 1 stellt den Testaufruf um |
| 7 | Stale-Zweig von `get_clock_status` gibt nicht mehr früh zurück (#494) | Step 3 auf den neuen Zweig umgeschrieben; Rückschritt hält `test_494_clock_status_today.py` fest |
| 11, 12 | `admin_users.py`: `lock_active_admins_and_user`/`_lock_and_reload` (#491 API-2) | nur Zeilen |
| 14 | `test_concurrency.py` 15 statt 12 Tests, `test_invalid_uuid_postgres.py` 3 statt 2; `local-ci.sh`-Zählkommentar noch auf 46 | Erwartung `52 passed`, Kommentar auf 52 |

Die Planungsläufe (SQLite-Vollsuite, PG-Suiten, Prod-Probe-Prüfung auf Wegwerf-Daten) liefen bei `b635679`. Bei `3d46c2f` vor Task 1 einmal die Vollsuite fahren und die Ausgangszahl notieren — „keine neuen Fehlschläge" in den Tasks bezieht sich auf diese Zahl.

## Review Focus

1. **Halboffene Altfenster** (Platzhalter `23:59`/`00:00` aus 073) beim späten Ausstempeln und beim Auto-Close: eine Person mit Fenster „Mo ab 08:00" bleibt wie unter 072 ohne Ende-Kappung (kein `raw_end_time`, `uncredited` 0) — Tests in Task 8.
2. **Notiz- oder Pausenkorrektur an einem lückengekappten Eintrag** (Admin-Bearbeitung nach einer Puffer-Senkung): `raw_*`, `uncredited_minutes` und `clamp_grace_minutes` bleiben stehen, nichts wird doppelt gekappt — Test in Task 6.
3. **XLS-Re-Import desselben Tages nach einer Puffer-Senkung**: der bestehende Eintrag wird über seinen Rohstempel gefunden (kein zweiter Eintrag) und mit seinem gespeicherten Puffer neu gekappt — Test in Task 10.
4. **Neue Wochenstunden-Änderung für eine Person mit Altfenster**: die Kappung läuft ab dem Wirkungsdatum unverändert weiter (P2), die Basis-Zeile friert das Fenster der Vergangenheit ein — Test in Task 12.
5. **Uhrzeiten mit Sekunden an der Hüllkante** (API-Clients): Ende `18:15:30` bei Hülle `18:15` wird wie unter 072 gekappt, Beginn `07:44:30` bei `07:45` ebenso — Test in Task 3; die vollständige Parität 072 ↔ 073 prüft ein Raster in Task 13.

## Dateistruktur

| Datei | Verantwortung | Task |
|---|---|---|
| `tools/migration-073/diagnose-073.sql` (neu) | Diagnose-SQL der Spec 5.1, rein lesend | 0 |
| `backend/app/services/work_blocks_service.py` (neu) | JSON-Form parsen/serialisieren, keine DB | 1 |
| `backend/tests/work_blocks_fixtures.py` (neu) | Test-Helfer `legacy_week`, `block_week`, `K_BLOCKS`, `MON` | 1 |
| `backend/app/models/{user,working_hours_change,time_entry,change_request}.py` | neue Spalten (Task 2), `net_hours` (Task 4), Drop `users.scheduled_*` (Task 13) | 2, 4, 13 |
| `backend/app/services/calculation_service.py` | `Schedule.blocks/block_pauses`, Resolver, `get_blocks_json_for_date`, `attach_work_blocks_today` | 2, 11 |
| `backend/app/services/work_window_service.py` | Kappungskern (komplett ersetzt) | 3 |
| `backend/tests/work_blocks_cases.py` (neu) | Falltabelle K1–K21 (PR2 ergänzt die ArbZG-Codes) | 3 |
| `backend/app/routers/time_entries.py` | Netto-Helfer, `clock_in/out`, Anlegen/Bearbeiten, Auto-Close, Stale-Zweig | 3–9 |
| `backend/app/routers/admin_time_entries.py`, `admin_change_requests.py`, `change_requests.py` | übrige Schreibpfade, Antragsprüfung | 3–9 |
| `backend/app/services/break_validation_service.py` | §4 mit Lückensegmenten, `BreakBlock`, `daily_break_figures` | 5 |
| `backend/app/services/xls_import_service.py`, `routers/import_xls.py` | Import (Vorschau + Ausführung) | 3, 10 |
| `backend/app/schemas/{user,validators,working_hours_change}.py`, `routers/{admin_users,auth,impersonation}.py` | Benutzer-API, Verlauf | 11, 12 |
| `backend/alembic/versions/2026_10_08_1200-073_work_blocks.py` (neu) | Migration inkl. Diagnose, Downgrade aus der Hülle | 13 |
| `backend/tests/test_no_scheduled_columns.py`, `test_no_live_work_blocks_read.py` (neu) | Guard-Tests | 13 |
| `backend/tests/test_073_migration_pg.py`, `test_net_hours_parity_pg.py` (neu) | Postgres-only | 14 |
| `.github/workflows/cross-tenant-ci.yml`, `scripts/local-ci.sh` | PG-Tests einhängen | 14 |
| `frontend/src/types/workBlocks.ts`, `frontend/src/utils/workBlocks.ts` (neu) | JSON-Typen, Anzeige-Helfer | 15 |
| `frontend/src/types/user.ts`, `pages/admin/users/UserForm.tsx`, `pages/admin/Users.tsx` | Fenster-Abschnitt raus, Blöcke-Anzeige rein | 15 |
| `e2e/tests/admin/prod-release-features.spec.ts`, `e2e/tests/shared/visual-prod-release.spec.ts` | E2E-Anpassung | 16 |
| `tools/migration-073/probe_073.py` (neu) | Byte-Identität auf der Prod-Kopie | 17 |

**Außerhalb von PR1 (nicht anfassen):** `RawStampNote`, Journal-Summe, Export-Spalte, Anerkennen-Endpunkt, „Anrechnung beantragen" (`ChangeRequestCreate.request_credit_override`), `PRESENCE_*`/`BREAK_IN_GAP`, Antwortfelder `uncredited_minutes`/`clamp_grace_minutes` in `TimeEntryResponse`/`ClockStatusResponse`, `blocks_today` im Clock-Status, `ImportXls.tsx` (Netto vom Server), Art.-15/20-Export, `Settings.tsx`-Puffertext (PR2); Schreibschemas mit Blöcken (`DayBlocksIn`, `validate_week_blocks`), `derive_targets`, Dialog/Editor, POST-Vorschau, Neukappung, Schutzpaket, `remove_legacy_window`, Umbenennung „Arbeitszeit anpassen…" (PR3); Doku, CLAUDE.md, Release-Notes (PR4).

---

### Task 0: Vorbedingung — Diagnose der Produktions-Kopie (Gate)

**Files:**
- Create: `tools/migration-073/diagnose-073.sql`
- Modify: `docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md` (Abschnitt 19, Punkt 1 — nur mit den Zahlen des Betreibers)

**Interfaces:**
- Consumes: —
- Produces: `tools/migration-073/diagnose-073.sql` (Q1–Q6 aus Spec 5.1, wörtlich); der Container `pz073-prod` (PG18 mit der Prod-Kopie, Netz `pz073`), den Task 17 weiterverwendet; ein dokumentiertes Diagnose-Ergebnis in Spec §19 Nr. 1, das Task 13 (Diagnose-Texte) und Task 17 (Prod-Probe) heranziehen; die Datei `.git/pr1-base` (genauer: `$(git rev-parse --git-dir)/pr1-base`) mit dem Commit des Ausgangsstands vor PR1 — Task 17 vergleicht gegen genau diesen Stand.

**STOP-Regel:** Kein weiterer Task beginnt, bevor das Ergebnis in Spec §19 Nr. 1 steht (E25: „bevor implementiert wird"). Der ausführende Agent hat keinen Zugriff auf Produktionsdaten und erfindet keine Zahlen.

- [ ] **Step 1: Diagnose-Skript aus der Spec extrahieren**

```bash
mkdir -p tools/migration-073
awk '/^-- diagnose-073.sql/{f=1} f{print} /^FROM tenants t ORDER BY t.name;/{exit}' \
  docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md > tools/migration-073/diagnose-073.sql
head -1 tools/migration-073/diagnose-073.sql
tail -1 tools/migration-073/diagnose-073.sql
```

Expected: erste Zeile `-- diagnose-073.sql — rein lesend`, letzte Zeile `FROM tenants t ORDER BY t.name;`.

- [ ] **Step 2: Syntax gegen eine leere 072-Datenbank prüfen**

```bash
PGPW=$(python3 -c 'import secrets;print(secrets.token_hex(16))')
S="postgres"; S="${S}ql://"; URL="${S}praxiszeit:${PGPW}@pz073-syntax:5432/praxiszeit"
docker network create pz073 2>/dev/null || true
docker run -d --rm --name pz073-syntax --network pz073 -e POSTGRES_USER=praxiszeit -e POSTGRES_PASSWORD="$PGPW" -e POSTGRES_DB=praxiszeit postgres:18-alpine
timeout 60 sh -c 'until docker exec pz073-syntax pg_isready -U praxiszeit >/dev/null 2>&1; do sleep 1; done'
docker run --rm --network pz073 -v "$PWD/backend":/app:ro -w /app --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X \
  -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost \
  -e DATABASE_URL="$URL" -e DATABASE_URL_MIGRATIONS="$URL" \
  praxiszeit-backend python -c "from alembic.config import main; main(['upgrade','072_cr_sunday_reason'])"
docker exec -i pz073-syntax psql -v ON_ERROR_STOP=1 -U praxiszeit -d praxiszeit < tools/migration-073/diagnose-073.sql
docker stop pz073-syntax
```

Expected: sechs Ergebnisblöcke ohne Fehler (auf der leeren DB je 0 Zeilen, Q6 eine Zeile `Default | 15 (Default)`).

- [ ] **Step 3: Betreiber führt das Skript auf der Prod-Kopie aus**

An den Betreiber (Manuel) übergeben — wörtlich so (die Sicherungen sind Plain-SQL + gzip, `backup_service.py`):

```text
Bitte die jüngste Produktions-Sicherung (praxiszeit_<Zeitstempel>.sql.gz) in eine Wegwerf-PG18 einspielen und tools/migration-073/diagnose-073.sql als Superuser ausführen:

  docker network create pz073 2>/dev/null || true
  docker run -d --name pz073-prod --network pz073 -e POSTGRES_USER=praxiszeit -e POSTGRES_PASSWORD="$(python3 -c 'import secrets;print(secrets.token_hex(16))')" -e POSTGRES_DB=praxiszeit postgres:18-alpine
  timeout 60 sh -c 'until docker exec pz073-prod pg_isready -U praxiszeit >/dev/null 2>&1; do sleep 1; done'
  docker exec pz073-prod psql -U praxiszeit -d praxiszeit -c "CREATE ROLE praxiszeit_app LOGIN NOINHERIT"
  gunzip -c praxiszeit_<Zeitstempel>.sql.gz | docker exec -i pz073-prod psql -q -U praxiszeit -d praxiszeit
  docker exec pz073-prod psql -U praxiszeit -d praxiszeit -Atc "SELECT version_num FROM alembic_version"
  docker exec -i pz073-prod psql -U praxiszeit -d praxiszeit < tools/migration-073/diagnose-073.sql > diagnose-073.out

Erwartet: version_num = 072_cr_sunday_reason. Die Ausgabe (Zahlen je Befund aus Q2, Konten aus Q3, Q5-Zählungen, Q6-Puffer) bitte zurückgeben — ohne Namen, wenn gewünscht. Der Container pz073-prod bleibt für Task 17 stehen (kein --rm).
```

- [ ] **Step 4: Ergebnis in Spec §19 Nr. 1 nachtragen**

Unter Punkt 1 („Ergebnis der Prod-Diagnose fehlt") einen Absatz „**Ergebnis (Datum, Sicherung vom …):**" mit den Zahlen aus Q2 (je Befund), der Zahl der Konten aus Q3, den Summen aus Q5 und den Puffern aus Q6 einfügen — ausschließlich mit den vom Betreiber gelieferten Werten. Enthält Q2 einen Befund `Beginn>=Ende`, die Anzahl betroffener Wochentage nennen (Verhaltensänderung nach 073: dort wird nicht mehr gekappt, Spec 5.3).

- [ ] **Step 5: Ausgangsstand vor PR1 festhalten (vor dem ersten PR1-Commit, vor Task 1)**

PR1 läuft auf dem Integrationszweig mit den Lane-Merges (#491–#501, Kopf `3d46c2f`). `git merge-base HEAD master` zeigt dort auf 1.19.3 (`616b43c`, 40 Commits zurück, darunter Änderungen an `calculation_service` aus #494/#496/#501) — ein Vergleich dagegen schriebe Lane-Änderungen PR1 zu. Deshalb den Kopf des Integrationszweigs **jetzt** festhalten:

```bash
git rev-parse HEAD > "$(git rev-parse --git-dir)/pr1-base"
git log -1 --oneline "$(cat "$(git rev-parse --git-dir)/pr1-base")"
git status --porcelain -- backend
```

Expected: `3d46c2f docs: Hilfe-Spiegel und CLAUDE.md-Regeln aus den Issue-Lanes …` bzw. der aktuelle Kopf des Integrationszweigs, **nicht** `616b43c`; `git status` für `backend/` leer (der festgehaltene Commit ist der Code-Stand, der in Task 17 als „vor PR1" läuft). `--git-dir` statt eines festen `.git/` hält den Befehl auch in einem Worktree gültig (dort ist `.git` eine Datei); Task 17 liest die Datei im selben Worktree.

- [ ] **Step 6: Commit**

```bash
git add tools/migration-073/diagnose-073.sql docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md
git commit -F - <<'EOF'
chore(073): Diagnose-SQL ins Repo, Ergebnis der Prod-Kopie in der Spec

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 1: `work_blocks_service` — kanonische JSON-Form

**Files:**
- Create: `backend/app/services/work_blocks_service.py`
- Create: `backend/tests/work_blocks_fixtures.py`
- Test: `backend/tests/test_work_blocks_service.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `WEEKDAY_LABELS: tuple[str, ...] = ("Mo", "Di", "Mi", "Do", "Fr")`
  - `class ParsedWeek(NamedTuple): blocks: tuple; pauses: tuple` — `blocks` = 5 × `tuple[tuple[int, int], ...]` (Minuten seit Mitternacht, je Tag sortiert), `pauses` = 5 × `Optional[int]`
  - `hhmm_to_minutes(value: str) -> int` (ValueError bei Formatfehler)
  - `minutes_to_hhmm(minutes: int) -> str`
  - `parse_week_blocks(raw: Any) -> Optional[ParsedWeek]` — `None` bei `None` **und** bei fünf leeren Tagen; `ValueError` bei Strukturfehlern; akzeptiert Altwerte (`07:37`, `00:00`, `23:59`), prüft **kein** Raster
  - `week_blocks_to_json(blocks: Optional[tuple], pauses: Optional[tuple]) -> Optional[list[dict]]`
  - `is_legacy_week(parsed: Optional[ParsedWeek]) -> bool` — True, wenn mindestens ein `pause_minutes` None ist (Spec 3.3)
  - Test-Helfer (`tests/work_blocks_fixtures.py`): `legacy_week(**days) -> list[dict]` (Schlüssel `mon,tue,wed,thu,fri`, Wert `(start|None, end|None)` als `"HH:MM"`; halboffen → Platzhalter `00:00`/`23:59`), `block_week(pause: int = 0, **days) -> list[dict]` (Wert = Liste von `(start, end)`), `MON = date(2026, 6, 1)` (Montag), `K_BLOCKS = block_week(mon=[("08:00","12:00"), ("15:00","18:00")])`

- [ ] **Step 1: Test-Helfer anlegen**

`backend/tests/work_blocks_fixtures.py`:

```python
"""Test-Helfer: kanonische JSON-Form der Arbeitszeit-Blöcke (Spec 3.1)."""
from datetime import date

_DAYS = ("mon", "tue", "wed", "thu", "fri")

# 2026-06-01 ist ein Montag; die Falltabelle K1–K21 (Spec 6.3) rechnet darauf.
MON = date(2026, 6, 1)


def legacy_week(**days):
    """Altfenster wie nach Migration 073: je Tag höchstens EIN Block,
    ``pause_minutes`` None. ``mon=("08:00", "17:00")``; halboffen
    ``("08:00", None)`` → Ende ``23:59``, ``(None, "17:00")`` → Beginn
    ``00:00`` (Platzhalter wie Spec 5.3)."""
    unknown = set(days) - set(_DAYS)
    if unknown:
        raise TypeError(f"unbekannte Wochentage: {sorted(unknown)}")
    week = []
    for key in _DAYS:
        window = days.get(key)
        if window is None:
            week.append({"blocks": [], "pause_minutes": None})
            continue
        start, end = window
        week.append({
            "blocks": [{"start": start or "00:00", "end": end or "23:59"}],
            "pause_minutes": None,
        })
    return week


def block_week(pause: int = 0, **days):
    """Neue Blöcke (``pause_minutes`` int): ``mon=[("08:00", "12:00"), ("15:00", "18:00")]``.
    Tage ohne Blöcke tragen ``pause_minutes`` 0 (Spec 3.4)."""
    unknown = set(days) - set(_DAYS)
    if unknown:
        raise TypeError(f"unbekannte Wochentage: {sorted(unknown)}")
    week = []
    for key in _DAYS:
        blocks = days.get(key) or []
        week.append({
            "blocks": [{"start": s, "end": e} for s, e in blocks],
            "pause_minutes": pause if blocks else 0,
        })
    return week


# Spec 6.3: Mo 08:00–12:00 + 15:00–18:00, Pause 0 → Hülle 07:45–18:15, Lücke 12:15–14:45.
K_BLOCKS = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")])
```

- [ ] **Step 2: Failing tests schreiben**

`backend/tests/test_work_blocks_service.py`:

```python
"""Spec 2026-10-08, Abschnitt 3: JSON-Form der Arbeitszeit-Blöcke."""
import pytest

from app.services import work_blocks_service as wbs
from tests.work_blocks_fixtures import K_BLOCKS, block_week, legacy_week

CANONICAL = [
    {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], "pause_minutes": 30},
    {"blocks": [{"start": "08:00", "end": "13:00"}], "pause_minutes": 0},
    {"blocks": [], "pause_minutes": 0},
    {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], "pause_minutes": 30},
    {"blocks": [], "pause_minutes": 0},
]


def test_parse_canonical_example():
    parsed = wbs.parse_week_blocks(CANONICAL)
    assert parsed.blocks[0] == ((480, 720), (900, 1080))
    assert parsed.blocks[2] == ()
    assert parsed.pauses == (30, 0, 0, 30, 0)
    assert wbs.is_legacy_week(parsed) is False


def test_parse_legacy_row_with_placeholders_and_odd_minutes():
    week = legacy_week(mon=("07:37", "16:30"), fri=("07:30", None), tue=(None, "16:00"))
    parsed = wbs.parse_week_blocks(week)
    assert parsed.blocks[0] == ((457, 990),)
    assert parsed.blocks[1] == ((0, 960),)
    assert parsed.blocks[4] == ((450, 1439),)
    assert parsed.pauses == (None,) * 5
    assert wbs.is_legacy_week(parsed) is True


@pytest.mark.parametrize("raw", [None, block_week(), legacy_week()])
def test_none_and_five_empty_days_are_the_same(raw):
    assert wbs.parse_week_blocks(raw) is None


def test_round_trip_keeps_canonical_form():
    for raw in (CANONICAL, legacy_week(mon=("07:30", None)), K_BLOCKS):
        parsed = wbs.parse_week_blocks(raw)
        assert wbs.week_blocks_to_json(parsed.blocks, parsed.pauses) == raw


def test_unsorted_blocks_are_sorted():
    raw = block_week(mon=[("15:00", "18:00"), ("08:00", "12:00")])
    assert wbs.parse_week_blocks(raw).blocks[0] == ((480, 720), (900, 1080))


def test_week_blocks_to_json_none():
    assert wbs.week_blocks_to_json(None, None) is None


@pytest.mark.parametrize("raw", [
    CANONICAL[:4],                                                      # vier Tage
    block_week(mon=[("7:30", "12:00")]),                                # kein HH:MM
    block_week(mon=[("24:00", "23:00")]),                               # Stunde 24
    block_week(mon=[("12:00", "08:00")]),                               # Beginn >= Ende
    block_week(mon=[("08:00", "12:00"), ("11:00", "14:00")]),           # Überlappung
    [{"blocks": "x", "pause_minutes": 0}] * 5,                          # kein Block-Array
    [{"blocks": [], "pause_minutes": -5}] + block_week()[1:],           # negative Pause
])
def test_structural_errors_raise(raw):
    with pytest.raises(ValueError):
        wbs.parse_week_blocks(raw)


def test_minutes_helpers():
    assert wbs.hhmm_to_minutes("07:37") == 457
    assert wbs.minutes_to_hhmm(1439) == "23:59"
    with pytest.raises(ValueError):
        wbs.hhmm_to_minutes("7:37")
```

- [ ] **Step 3: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_work_blocks_service.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.work_blocks_service'`

- [ ] **Step 4: Modul implementieren**

`backend/app/services/work_blocks_service.py`:

```python
"""Arbeitszeit-Blöcke (Spec 2026-10-08, Abschnitt 3): kanonische JSON-Form.

Kanonisch für ``working_hours_changes.blocks`` und ``users.work_blocks``: eine
Liste aus genau fünf Einträgen (Index 0 = Montag … 4 = Freitag), je
``{"blocks": [{"start": "HH:MM", "end": "HH:MM"}, …], "pause_minutes": int | None}``.

Reine Funktionen ohne Datenbank. Gelesen werden auch Altzeilen aus Migration 073
(``07:37``, Platzhalter ``00:00``/``23:59``, ``pause_minutes`` None) — die
STRENGE Prüfung (5-Minuten-Raster, höchstens drei Blöcke, Pause < Σ) gehört in
die Schreibschemas (PR3), nie hierher: ein Lesepfad, der Altwerte ablehnt,
machte den Login einer Person mit Altfenster zu HTTP 500 (E29).
"""
from typing import Any, NamedTuple, Optional

WEEKDAY_LABELS = ("Mo", "Di", "Mi", "Do", "Fr")
_LAST_MINUTE = 23 * 60 + 59


class ParsedWeek(NamedTuple):
    blocks: tuple   # 5 × tuple[(start_min, end_min), …], je Tag sortiert
    pauses: tuple   # 5 × Optional[int]; None = Altzeile (Soll nicht aus Blöcken)


def hhmm_to_minutes(value: str) -> int:
    """``"HH:MM"`` → Minuten seit Mitternacht (00:00–23:59)."""
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError(f"Uhrzeit {value!r} nicht im Format HH:MM")
    hh, mm = value[:2], value[3:]
    if not (hh.isdigit() and mm.isdigit()):
        raise ValueError(f"Uhrzeit {value!r} nicht im Format HH:MM")
    hours, minutes = int(hh), int(mm)
    if hours > 23 or minutes > 59:
        raise ValueError(f"Uhrzeit {value!r} außerhalb 00:00–23:59")
    return hours * 60 + minutes


def minutes_to_hhmm(minutes: int) -> str:
    if not 0 <= minutes <= _LAST_MINUTE:
        raise ValueError(f"Minutenwert {minutes} außerhalb des Tages")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_week_blocks(raw: Any) -> Optional[ParsedWeek]:
    """Kanonische JSON-Woche → :class:`ParsedWeek`.

    ``None`` und eine Woche mit fünf leeren Tagen ergeben ``None`` (Spec 3.3:
    beides heißt „keine Blöcke" — sonst entstünden Scheinänderungen)."""
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != 5:
        raise ValueError("Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet.")
    all_blocks, pauses = [], []
    for idx, day in enumerate(raw):
        label = WEEKDAY_LABELS[idx]
        if not isinstance(day, dict) or not isinstance(day.get("blocks", []), list):
            raise ValueError(f"{label}: Tag nicht in der Form {{blocks, pause_minutes}}.")
        day_blocks = []
        for block in day.get("blocks") or []:
            try:
                start = hhmm_to_minutes(block["start"])
                end = hhmm_to_minutes(block["end"])
            except (KeyError, TypeError) as exc:
                raise ValueError(f"{label}: Block ohne start/end.") from exc
            if start >= end:
                raise ValueError(f"{label}: Beginn muss vor dem Ende liegen.")
            day_blocks.append((start, end))
        day_blocks.sort()
        for (_, end_a), (start_b, _) in zip(day_blocks, day_blocks[1:]):
            if start_b < end_a:
                raise ValueError(f"{label}: Blöcke überlappen.")
        pause = day.get("pause_minutes")
        if pause is not None and (isinstance(pause, bool) or not isinstance(pause, int) or pause < 0):
            raise ValueError(f"{label}: Pause muss eine ganze Zahl ≥ 0 sein.")
        all_blocks.append(tuple(day_blocks))
        pauses.append(pause)
    if not any(all_blocks):
        return None
    return ParsedWeek(tuple(all_blocks), tuple(pauses))


def week_blocks_to_json(blocks: Optional[tuple], pauses: Optional[tuple]) -> Optional[list]:
    """Umkehrung von :func:`parse_week_blocks` — ``None`` bleibt ``None``."""
    if blocks is None:
        return None
    return [
        {
            "blocks": [{"start": minutes_to_hhmm(s), "end": minutes_to_hhmm(e)} for s, e in day],
            "pause_minutes": pause,
        }
        for day, pause in zip(blocks, pauses)
    ]


def is_legacy_week(parsed: Optional[ParsedWeek]) -> bool:
    """Spec 3.3: eine Zeile mit mindestens einem ``pause_minutes`` None ist eine
    Altzeile (Fenster aus Migration 073 — kappt, treibt kein Soll)."""
    return parsed is not None and any(p is None for p in parsed.pauses)
```

- [ ] **Step 5: Test laufen lassen — muss grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_work_blocks_service.py -q -p no:cacheprovider`
Expected: PASS (alle Tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/work_blocks_service.py backend/tests/work_blocks_fixtures.py backend/tests/test_work_blocks_service.py
git commit -F - <<'EOF'
feat(bloecke): kanonische JSON-Form der Arbeitszeit-Blöcke (Spec 3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Modellspalten und Resolver

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#493/#494/#496/#500/#501, gemergt in `3d46c2f`: `calculation_service.py` +345 Zeilen — neuer direkter Aufrufer von `get_schedule_for_date` ist `vacation_day_cost_by_year`, `get_day_presence_target`/`get_week_summary` lesen das Soll über die bestehenden Helfer; keine neue `Schedule(...)`-Konstruktion. Der Vorschau-Konstruktor aus Step 5 steht bei `3d46c2f` in `admin_users.py` Zeile 1865 (statt 1819). Vor Step 5 `grep -n "Schedule(" backend/app backend/tests` laufen lassen: jede Konstruktion außerhalb von `calculation_service.py` braucht die zwei neuen Pflichtfelder.)

**Files:**
- Modify: `backend/app/models/user.py` (nach `hours_friday`, vor den `scheduled_*`-Spalten — die bleiben bis Task 13)
- Modify: `backend/app/models/working_hours_change.py:41` (nach `work_days_per_week`)
- Modify: `backend/app/models/time_entry.py:24-25` (nach `raw_end_time`)
- Modify: `backend/app/models/change_request.py:69` (nach `original_note`)
- Modify: `backend/app/services/calculation_service.py:13-102`
- Modify: `backend/app/routers/admin_users.py:1819-1826` (Vorschau-Konstruktor `calculation_service.Schedule(...)`)
- Test: `backend/tests/test_schedule_blocks_resolver.py`

**Interfaces:**
- Consumes: `work_blocks_service.parse_week_blocks`, `week_blocks_to_json`, `ParsedWeek` (Task 1); `tests.work_blocks_fixtures.*`
- Produces:
  - Modellattribute: `User.work_blocks` (JSON|None), `WorkingHoursChange.blocks` (JSON|None), `TimeEntry.uncredited_minutes: int` (Default 0), `TimeEntry.credit_override: bool` (Default False), `TimeEntry.auto_closed: bool` (Default False), `TimeEntry.clamp_grace_minutes: Optional[int]`, `ChangeRequest.request_credit_override: bool` (Default False), `ChangeRequest.original_uncredited_minutes: Optional[int]`
  - `calculation_service.Schedule` mit zusätzlichen Pflichtfeldern `blocks: Optional[tuple]` (5 × `tuple[(start_min, end_min), …]` oder None) und `block_pauses: Optional[tuple]` (5 × `Optional[int]` oder None)
  - `calculation_service.get_schedule_for_date(db, user, target_date, wh_changes=None) -> Schedule` — Blöcke aus der Verlaufszeile (NULL → None, **kein** Rückfall), ohne Zeile aus `users.work_blocks`; Parse-Cache am ORM-Objekt (`_parsed_blocks`)
  - `calculation_service.get_blocks_json_for_date(db, user, target_date, wh_changes=None) -> Optional[list[dict]]`

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_schedule_blocks_resolver.py`:

```python
"""Spec 3.3/3.6: Blöcke kommen datumsaufgelöst aus dem Vertrags-Snapshot."""
from datetime import date, time

from app.models import ChangeRequest, TimeEntry, WorkingHoursChange
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week, legacy_week


def _row(db, user, effective_from, blocks):
    row = WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=effective_from,
        weekly_hours=40.0, use_daily_schedule=False, work_days_per_week=5, blocks=blocks,
    )
    db.add(row)
    db.commit()
    return row


def test_fallback_to_user_work_blocks_without_history(db, test_user):
    test_user.work_blocks = legacy_week(mon=("07:30", "16:30"))
    db.commit()
    s = cs.get_schedule_for_date(db, test_user, MON)
    assert s.blocks[0] == ((450, 990),)
    assert s.block_pauses == (None,) * 5


def test_null_in_history_row_means_no_blocks_never_fallback(db, test_user):
    test_user.work_blocks = legacy_week(mon=("07:30", "16:30"))
    _row(db, test_user, date(2026, 1, 1), None)
    s = cs.get_schedule_for_date(db, test_user, MON)
    assert s.blocks is None and s.block_pauses is None


def test_history_row_wins_and_date_before_falls_back(db, test_user):
    test_user.work_blocks = legacy_week(mon=("07:30", "16:30"))
    _row(db, test_user, date(2026, 5, 1), K_BLOCKS)
    assert cs.get_schedule_for_date(db, test_user, MON).blocks[0] == ((480, 720), (900, 1080))
    assert cs.get_schedule_for_date(db, test_user, date(2026, 4, 27)).blocks[0] == ((450, 990),)


def test_five_empty_days_normalise_to_none(db, test_user):
    _row(db, test_user, date(2026, 1, 1), block_week())
    assert cs.get_schedule_for_date(db, test_user, MON).blocks is None


def test_preload_path_matches_query_path(db, test_user):
    _row(db, test_user, date(2026, 5, 1), K_BLOCKS)
    rows = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).all()
    assert cs.get_schedule_for_date(db, test_user, MON, rows) == cs.get_schedule_for_date(db, test_user, MON)


def test_parse_cache_is_invalidated_by_reassignment(db, test_user):
    row = _row(db, test_user, date(2026, 5, 1), K_BLOCKS)
    first = cs.get_schedule_for_date(db, test_user, MON, [row]).blocks
    assert cs.get_schedule_for_date(db, test_user, MON, [row]).blocks is first   # Cache
    row.blocks = legacy_week(mon=("09:00", "17:00"))                            # Neuzuweisung
    assert cs.get_schedule_for_date(db, test_user, MON, [row]).blocks[0] == ((540, 1020),)


def test_get_blocks_json_for_date_round_trip(db, test_user):
    _row(db, test_user, date(2026, 5, 1), K_BLOCKS)
    assert cs.get_blocks_json_for_date(db, test_user, MON) == K_BLOCKS
    assert cs.get_blocks_json_for_date(db, test_user, date(2026, 4, 27)) is None


def test_new_time_entry_and_cr_columns_have_defaults(db, test_user):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                  start_time=time(8, 0), end_time=time(9, 0), break_minutes=0)
    cr = ChangeRequest(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id,
                       request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
                       reason="x")
    db.add_all([e, cr])
    db.commit()
    db.refresh(e)
    db.refresh(cr)
    assert (e.uncredited_minutes, e.credit_override, e.auto_closed, e.clamp_grace_minutes) == (0, False, False, None)
    assert (cr.request_credit_override, cr.original_uncredited_minutes) == (False, None)
```

- [ ] **Step 2: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_schedule_blocks_resolver.py -q -p no:cacheprovider`
Expected: FAIL — `TypeError: 'work_blocks' is an invalid keyword argument` bzw. `AttributeError: 'Schedule' object has no attribute 'blocks'`

- [ ] **Step 3: Modelle ergänzen**

`backend/app/models/user.py` — Importzeile 1–2 ergänzen und Spalte nach `hours_friday` einfügen:

```python
from sqlalchemy import Column, String, Boolean, Numeric, Integer, BigInteger, Enum, DateTime, Date, Text, Time, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
```

```python
    # Spec 2026-10-08 (E9): Arbeitszeit-Blöcke als Rückfall NUR für Tage vor der
    # ersten Verlaufszeile (wie weekly_hours seit #415) und Spiegel der jüngsten
    # Zeile ≤ heute. Gelesen wird sie AUSSCHLIESSLICH vom Resolver
    # (calculation_service.get_schedule_for_date) — Guard-Test
    # test_no_live_work_blocks_read.py. JSON-Form: Spec 3.1.
    work_blocks = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
```

`backend/app/models/working_hours_change.py` — Importe und Spalte nach `work_days_per_week`:

```python
from sqlalchemy import Column, String, Numeric, Date, DateTime, ForeignKey, Boolean, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
```

```python
    # Spec 2026-10-08 (E8): Blöcke ab effective_from. NULL heißt „keine Blöcke"
    # — NIE Rückfall auf users.work_blocks (sonst schlüge jede Sync der
    # User-Zeile rückwirkend in alle Altzeilen durch, #431-Fehlerklasse).
    # Änderung nur per Neuzuweisung des ganzen Werts (keine In-place-Mutation).
    blocks = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
```

`backend/app/models/time_entry.py` — Import `Boolean` ergänzen, Spalten nach `raw_end_time`:

```python
from sqlalchemy import Boolean, Column, Date, Time, Integer, Text, DateTime, Numeric, ForeignKey, UniqueConstraint, case
```

```python
    # Spec 2026-10-08: nicht angerechnete Minuten in der Lücke zwischen zwei
    # Arbeitsblöcken (E11). NIE Eingabefeld, immer serverseitig aus clamp().
    uncredited_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    # „Anerkennen" (E12, Endpunkt in PR2): Eintrag wird nie gekappt.
    credit_override = Column(Boolean, nullable=False, default=False, server_default="false")
    # P18: vom Auto-Close geschlossen — raw_end_time 23:59 ist dann kein Stempel.
    auto_closed = Column(Boolean, nullable=False, default=False, server_default="false")
    # E79: Puffer der letzten Kappung gegen Blöcke; NULL = nie gegen Blöcke
    # gekappt bzw. Bestand vor 073 („unbekannt → aktueller Puffer").
    clamp_grace_minutes = Column(Integer, nullable=True)
```

`backend/app/models/change_request.py` — Import `Boolean`, Spalten nach `original_note`:

```python
from sqlalchemy import Boolean, Column, Date, Time, Integer, String, Text, DateTime, Numeric, Enum, ForeignKey
```

```python
    # P28: Vorher-Snapshot der nicht angerechneten Lückenminuten des Eintrags.
    original_uncredited_minutes = Column(Integer, nullable=True)
    # P21 (Antrag „Anrechnung beantragen", Logik in PR2).
    request_credit_override = Column(Boolean, nullable=False, default=False, server_default="false")
```

- [ ] **Step 4: Resolver erweitern**

`backend/app/services/calculation_service.py` — Import nach Zeile 10:

```python
from app.services import special_days_service, settings_service, work_blocks_service
```

`Schedule` (Zeilen 13–25) ersetzen:

```python
class Schedule(NamedTuple):
    """#431: der vollstaendige Vertrags-Snapshot fuer EIN Datum.

    Aufgeloest aus der jeweils juengsten ``WorkingHoursChange`` mit
    ``effective_from <= target_date``; gibt es keine, aus den aktuellen
    User-Feldern (der Rueckfallwert fuer die Zeit vor der ersten erfassten
    Aenderung — dieselbe Semantik wie ``user.weekly_hours`` seit #415).

    Spec 2026-10-08 (P6): ``blocks``/``block_pauses`` OHNE Vorgabewert — eine
    uebersehene Konstruktor-Stelle soll laut scheitern.
    """

    weekly_hours: Decimal
    use_daily_schedule: bool
    day_hours: tuple          # (Mo, Di, Mi, Do, Fr), je Optional[Decimal]
    work_days_per_week: int
    blocks: Optional[tuple]        # 5 × tuple[(start_min, end_min), …] oder None
    block_pauses: Optional[tuple]  # 5 × Optional[int]; None-Einträge = Altzeile
```

Vor `get_schedule_for_date` einfügen:

```python
def _parsed_blocks(holder, raw) -> Optional[work_blocks_service.ParsedWeek]:
    """Parse-Cache am ORM-Objekt (Spec 3.6): der Preload-Pfad (#449) löst
    hunderte Tage gegen dieselbe Zeile auf. Geprüft wird die IDENTITÄT des
    JSON-Werts — eine Neuzuweisung (einziger erlaubter Änderungsweg) macht den
    Cache ungültig."""
    cache = getattr(holder, "_parsed_blocks", None)
    if cache is not None and cache[0] is raw:
        return cache[1]
    parsed = work_blocks_service.parse_week_blocks(raw)
    holder._parsed_blocks = (raw, parsed)
    return parsed
```

In `get_schedule_for_date` den Zweig mit Verlaufszeile ergänzen (vor `return Schedule(` der Zeile):

```python
    change = _latest_change(db, user, target_date, wh_changes)
    if change is not None:
        # E8: NULL in der Verlaufszeile = keine Blöcke, KEIN Rückfall.
        parsed = _parsed_blocks(change, change.blocks)
        return Schedule(
            weekly_hours=Decimal(str(change.weekly_hours)),
            use_daily_schedule=bool(change.use_daily_schedule),
            day_hours=(
                _dec_or_none(change.hours_monday),
                _dec_or_none(change.hours_tuesday),
                _dec_or_none(change.hours_wednesday),
                _dec_or_none(change.hours_thursday),
                _dec_or_none(change.hours_friday),
            ),
            work_days_per_week=int(
                change.work_days_per_week
                if change.work_days_per_week is not None
                else user.work_days_per_week
            ),
            blocks=parsed.blocks if parsed else None,
            block_pauses=parsed.pauses if parsed else None,
        )
    # Kein Eintrag → aktuelle User-Felder. Dies ist die EINZIGE Stelle im Code,
    # die user.weekly_hours / user.hours_* / user.work_days_per_week /
    # user.work_blocks direkt lesen darf.
    parsed = _parsed_blocks(user, getattr(user, "work_blocks", None))
    return Schedule(
        weekly_hours=Decimal(str(user.weekly_hours)),
        use_daily_schedule=bool(getattr(user, 'use_daily_schedule', False)),
        day_hours=(
            _dec_or_none(user.hours_monday),
            _dec_or_none(user.hours_tuesday),
            _dec_or_none(user.hours_wednesday),
            _dec_or_none(user.hours_thursday),
            _dec_or_none(user.hours_friday),
        ),
        work_days_per_week=int(user.work_days_per_week),
        blocks=parsed.blocks if parsed else None,
        block_pauses=parsed.pauses if parsed else None,
    )
```

Hinweis zum Guard (Task 13): `getattr(user, "work_blocks", None)` ist kein `.work_blocks`-Token — der Guard prüft per `ast` sowohl `ast.Attribute` als auch `getattr(…, "work_blocks", …)`; die Funktion `get_schedule_for_date` steht auf seiner Erlaubnisliste.

Nach `get_weekly_hours_for_date` einfügen:

```python
def get_blocks_json_for_date(
    db: Session,
    user: User,
    target_date: date,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Optional[list]:
    """Spec 11.1 ``work_blocks_today``: die datumsaufgelösten Blöcke als
    kanonische JSON-Woche (Strings, nie ``time``) oder None."""
    schedule = get_schedule_for_date(db, user, target_date, wh_changes)
    return work_blocks_service.week_blocks_to_json(schedule.blocks, schedule.block_pauses)
```

- [ ] **Step 5: Vorschau-Konstruktor in `admin_users.py` (Zeilen 1819–1826) ergänzen**

```python
        new_schedule = calculation_service.Schedule(
            weekly_hours=Decimal(str(norm.weekly_hours)),
            use_daily_schedule=norm.use_daily_schedule,
            day_hours=tuple(
                None if v is None else Decimal(str(v)) for v in norm.day_hours
            ),
            work_days_per_week=norm.work_days_per_week,
            # PR1: der Dialog kennt noch keine Blöcke — die neue Zeile übernimmt
            # die des aktuell gültigen Snapshots (Task 12 verfeinert das nach P2).
            blocks=current_schedule.blocks,
            block_pauses=current_schedule.block_pauses,
        )
```

- [ ] **Step 6: Test laufen lassen — muss grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_schedule_blocks_resolver.py tests/test_449_schedule_preload.py tests/test_wh_change_preview.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models backend/app/services/calculation_service.py backend/app/routers/admin_users.py backend/tests/test_schedule_blocks_resolver.py
git commit -F - <<'EOF'
feat(bloecke): neue Spalten und datumsaufgelöste Blöcke im Schedule-Resolver

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Kappungskern `ClampResult` und mechanische Umstellung aller Aufrufer

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499 ändert Schreibpfade in `routers/time_entries.py`).

**Files:**
- Modify (komplett ersetzen): `backend/app/services/work_window_service.py`
- Create: `backend/tests/work_blocks_cases.py`
- Test (neu): `backend/tests/test_clamp_blocks.py`
- Test (komplett ersetzen): `backend/tests/test_work_window_service.py`
- Modify: `backend/app/routers/time_entries.py` (clamp-Aufrufe ~300, ~403, ~655, ~990; Warnungen ~319, ~457, ~768, ~1126)
- Modify: `backend/app/routers/admin_time_entries.py` (~88, ~114, ~293, ~335)
- Modify: `backend/app/routers/admin_change_requests.py` (~387, ~488/494, ~535/541, ~1019)
- Modify: `backend/app/services/xls_import_service.py` (~220, ~269, ~412-424)
- Modify (Testumstellung `scheduled_*` → `work_blocks`): `backend/tests/test_work_window_integration.py`, `test_xls_import_service.py`, `test_486_bulk_warnings.py`, `test_break_waiver.py`, `test_admin_entry_date_change_keeps_raw.py`, `test_release_1_19_1_review.py`

**Interfaces:**
- Consumes: `calculation_service.get_schedule_for_date` mit `Schedule.blocks` (Task 2); `tests.work_blocks_fixtures` (Task 1)
- Produces (alle in `app.services.work_window_service`):
  - `class ClampResult(NamedTuple): eff_start: Optional[time]; eff_end: Optional[time]; raw_start: Optional[time]; raw_end: Optional[time]; uncredited_minutes: int; grace_minutes: Optional[int]`
  - `DEFAULT_GRACE_MINUTES = 15`, `CLAMP_WARNING_CODE = "WORK_WINDOW_CLAMPED"`, `EMPLOYEE_CREDIT_HINT: str`
  - `get_grace_minutes(db: Session, tenant_id) -> int` (unverändert)
  - `grace_for_entry(db: Session, entry) -> int`
  - `get_scheduled_blocks(db: Session, user, d: date, *, wh_changes=None, soll_free_dates: Optional[set] = None) -> list[tuple[int, int]]`
  - `has_blocks(db: Session, user, d: date, **preload) -> bool`
  - `clamp_applies(db: Session, user, d: date, *, credit_override: bool, **preload) -> bool`
  - `credit_gaps(blocks: list[tuple[int, int]], grace: int) -> list[tuple[int, int]]`
  - `clamp(db: Session, user, d: date, start: Optional[time], end: Optional[time], grace: int, *, credit_override: bool, wh_changes=None, soll_free_dates=None) -> ClampResult`
  - `gap_segments(db: Session, user, d: date, start: Optional[time], end: Optional[time], grace: int, *, credit_override: bool, wh_changes=None, soll_free_dates=None) -> list[int]` — Invariante `sum(gap_segments(...)) == clamp(...).uncredited_minutes`
  - `clamp_warning_text(db: Session, user, d: date, result: ClampResult, *, for_employee: bool) -> Optional[str]` (ohne Code-Präfix; `db`/`user`/`d` werden nur gelesen, wenn eine Lücke aufzulösen ist)
  - `clamp_warning(db: Session, user, d: date, result: ClampResult, *, for_employee: bool) -> Optional[str]` (mit Präfix `WORK_WINDOW_CLAMPED: `)
  - `unclamp_input(incoming, prev_eff, prev_raw) -> Optional[time]` (unverändert)
  - `not_credited_minutes(entry) -> int` (P19)
  - `presence_minutes(entry) -> int` (8.3)
  - entfallen: `get_scheduled_window`, `_shift`, `_WEEKDAY_ATTR`
  - Test-Daten `tests.work_blocks_cases`: `class KCase(NamedTuple)`, `K_CASES: list[KCase]`, `EASTER_MONDAY`, `SUNDAY`, `DEC24_THU`, `k_user(case) -> User`

- [ ] **Step 1: Falltabelle anlegen**

`backend/tests/work_blocks_cases.py`:

```python
"""Spec 6.3: Falltabelle K1–K21 (Puffer 15 Min). Eine Quelle für Backend-Tests;
PR2 ergänzt die Spalte der ArbZG-Codes und spiegelt die IDs im Frontend-Test.

``clamp_text`` beschreibt, was ``clamp_warning_text`` für das Ergebnis EINES
clamp-Aufrufs liefert: None | "hull" | "collapse" | "gap" | "hull+gap" |
"in_gap" | "clock_in_gap". (K15 liefert beim Auto-Close keine Warnung — der
Auto-Close ruft clamp_warning nicht auf; K20 ist hier ein einziger Aufruf
07:00–18:00, beim echten Ausstempeln greift nur noch der Lückenteil.)
"""
from datetime import date, time
from typing import NamedTuple, Optional

from app.models import User, UserRole
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

EASTER_MONDAY = date(2026, 4, 6)   # Montag, Feiertag (Fixture legt ihn an)
SUNDAY = date(2026, 6, 7)
DEC24_THU = date(2026, 12, 24)     # Donnerstag; Fixture setzt dec24 = half_day

K6_BLOCKS = block_week(mon=[("08:00", "12:00"), ("12:30", "16:00")])
K17_BLOCKS = block_week(mon=[("07:00", "10:00"), ("11:00", "13:00"), ("16:00", "19:00")])
K18_BLOCKS = block_week(thu=[("08:00", "12:00"), ("15:00", "18:00")])
K19_BLOCKS = block_week(mon=[("08:00", "10:00"), ("15:00", "18:00")])


class KCase(NamedTuple):
    id: str
    blocks: list
    day: date
    start: time
    end: Optional[time]
    break_minutes: int
    track_hours: bool
    credit_override: bool
    auto_closed: bool
    exp_start: time
    exp_end: Optional[time]
    exp_raw_start: Optional[time]
    exp_raw_end: Optional[time]
    exp_uncredited: int
    exp_grace: Optional[int]
    exp_net: str
    exp_not_credited: int
    clamp_text: Optional[str]


def _t(h, m=0):
    return time(h, m)


K_CASES = [
    KCase("K1", K_BLOCKS, MON, _t(8), _t(18), 0, True, False, False, _t(8), _t(18), None, None, 150, 15, "7.50", 150, "gap"),
    KCase("K2", K_BLOCKS, MON, _t(13), None, 0, True, False, False, _t(13), None, None, None, 0, 15, "0.00", 0, "clock_in_gap"),
    KCase("K2b", K_BLOCKS, MON, _t(13), _t(18), 0, True, False, False, _t(13), _t(18), None, None, 105, 15, "3.25", 105, "gap"),
    KCase("K3", K_BLOCKS, MON, _t(12, 30), _t(14, 30), 0, True, False, False, _t(12, 30), _t(14, 30), None, None, 120, 15, "0.00", 120, "in_gap"),
    KCase("K4", K_BLOCKS, MON, _t(8), _t(12, 5), 0, True, False, False, _t(8), _t(12, 5), None, None, 0, 15, "4.08", 0, None),
    KCase("K5", K_BLOCKS, MON, _t(8), _t(12, 30), 0, True, False, False, _t(8), _t(12, 30), None, None, 15, 15, "4.25", 15, "gap"),
    KCase("K6", K6_BLOCKS, MON, _t(8), _t(16), 0, True, False, False, _t(8), _t(16), None, None, 0, 15, "8.00", 0, None),
    KCase("K7", K_BLOCKS, MON, _t(7), _t(19), 0, True, False, False, _t(7, 45), _t(18, 15), _t(7), _t(19), 150, 15, "8.00", 240, "hull+gap"),
    KCase("K8", K_BLOCKS, MON, _t(5), _t(7), 0, True, False, False, _t(5), _t(5), _t(5), _t(7), 0, 15, "0.00", 120, "collapse"),
    KCase("K9", K_BLOCKS, MON, _t(8), _t(18), 30, True, False, False, _t(8), _t(18), None, None, 150, 15, "7.00", 150, "gap"),
    KCase("K10", K_BLOCKS, MON, _t(8), _t(18), 45, True, True, False, _t(8), _t(18), None, None, 0, None, "9.25", 0, None),
    KCase("K11", K_BLOCKS, EASTER_MONDAY, _t(8), _t(18), 45, True, False, False, _t(8), _t(18), None, None, 0, None, "9.25", 0, None),
    KCase("K12", K_BLOCKS, SUNDAY, _t(8), _t(18), 45, True, False, False, _t(8), _t(18), None, None, 0, None, "9.25", 0, None),
    KCase("K13", K_BLOCKS, MON, _t(8), _t(18), 45, False, False, False, _t(8), _t(18), None, None, 0, None, "9.25", 0, None),
    KCase("K14", K_BLOCKS, MON, _t(8), None, 0, True, False, False, _t(8), None, None, None, 0, 15, "0.00", 0, None),
    KCase("K15", K_BLOCKS, MON, _t(8), _t(23, 59), 0, True, False, True, _t(8), _t(18, 15), None, _t(23, 59), 150, 15, "7.75", 150, "hull+gap"),
    KCase("K16", K_BLOCKS, MON, _t(14, 30), _t(18), 0, True, False, False, _t(14, 30), _t(18), None, None, 15, 15, "3.25", 15, "gap"),
    KCase("K17", K17_BLOCKS, MON, _t(7), _t(19), 0, True, False, False, _t(7), _t(19), None, None, 180, 15, "9.00", 180, "gap"),
    KCase("K18", K18_BLOCKS, DEC24_THU, _t(8), _t(18), 0, True, False, False, _t(8), _t(18), None, None, 150, 15, "7.50", 150, "gap"),
    KCase("K19", K19_BLOCKS, MON, _t(8), _t(18), 0, True, False, False, _t(8), _t(18), None, None, 270, 15, "5.50", 270, "gap"),
    KCase("K20", K_BLOCKS, MON, _t(7), _t(18), 0, True, False, False, _t(7, 45), _t(18), _t(7), None, 150, 15, "7.75", 195, "hull+gap"),
    KCase("K21", K_BLOCKS, MON, _t(8), _t(18), 45, True, False, False, _t(8), _t(18), None, None, 150, 15, "6.75", 150, "gap"),
]


def k_user(case: KCase) -> User:
    """Transiente Person ohne Verlauf → der Resolver nimmt ``work_blocks``."""
    return User(
        username=f"k_{case.id.lower()}", email=f"{case.id.lower()}@x.de", password_hash="h",
        first_name="K", last_name=case.id, role=UserRole.EMPLOYEE, weekly_hours=40.0,
        work_days_per_week=5, vacation_days=30, track_hours=case.track_hours,
        tenant_id=DEFAULT_TENANT_ID, work_blocks=case.blocks,
    )
```

- [ ] **Step 2: Failing tests schreiben**

`backend/tests/test_clamp_blocks.py`:

```python
"""Spec 6.1–6.3: Kappung gegen Arbeitszeit-Blöcke (Falltabelle K1–K21)."""
from datetime import time

import pytest

from app.models import TimeEntry, User, UserRole
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.services import work_window_service as wws
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_cases import EASTER_MONDAY, K_CASES, k_user
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

_TEXT_KIND = {
    None: lambda t: t is None,
    "hull": lambda t: t.startswith("Die eingetragene Zeit wurde auf das hinterlegte") and "Zusätzlich" not in t,
    "collapse": lambda t: "vollstaendig ausserhalb" in t,
    "gap": lambda t: t.startswith("Zwischen den Arbeitsblöcken ("),
    "hull+gap": lambda t: t.startswith("Die eingetragene Zeit wurde") and "Zusätzlich werden zwischen den Arbeitsblöcken" in t,
    "in_gap": lambda t: "vollständig zwischen zwei Arbeitsblöcken" in t,
    "clock_in_gap": lambda t: t.startswith("Eingestempelt zwischen zwei Arbeitsblöcken"),
}


@pytest.fixture
def k_setup(db, default_tenant):
    db.add(PublicHoliday(date=EASTER_MONDAY, name="Ostermontag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.add(SystemSetting(key="special_day_dec24_mode", value="half_day", tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


def _entry(case, r):
    return TimeEntry(
        start_time=r.eff_start, end_time=r.eff_end, raw_start_time=r.raw_start,
        raw_end_time=r.raw_end, break_minutes=case.break_minutes,
        uncredited_minutes=r.uncredited_minutes, auto_closed=case.auto_closed,
    )


@pytest.mark.parametrize("case", K_CASES, ids=[c.id for c in K_CASES])
def test_k_table(db, k_setup, case):
    user = k_user(case)
    r = wws.clamp(db, user, case.day, case.start, case.end, 15, credit_override=case.credit_override)
    assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == (
        case.exp_start, case.exp_end, case.exp_raw_start, case.exp_raw_end)
    assert r.uncredited_minutes == case.exp_uncredited
    assert r.grace_minutes == case.exp_grace
    segs = wws.gap_segments(db, user, case.day, case.start, case.end, 15, credit_override=case.credit_override)
    assert sum(segs) == r.uncredited_minutes
    assert wws.not_credited_minutes(_entry(case, r)) == case.exp_not_credited
    text = wws.clamp_warning_text(db, user, case.day, r, for_employee=False)
    assert _TEXT_KIND[case.clamp_text](text), text


def test_result_has_six_fields_and_four_unpack_fails(db, default_tenant):
    r = wws.clamp(db, k_user(K_CASES[0]), MON, time(8), time(18), 15, credit_override=False)
    assert len(r) == 6
    with pytest.raises(ValueError):
        a, b, c, d = r  # noqa: F841 — E31: altes Entpacken scheitert laut


def test_credit_override_is_mandatory(db, default_tenant):
    with pytest.raises(TypeError):
        wws.clamp(db, k_user(K_CASES[0]), MON, time(8), time(18), 15)


def test_start_none_with_end_does_not_crash(db, default_tenant):
    r = wws.clamp(db, k_user(K_CASES[0]), MON, None, time(19), 15, credit_override=False)
    assert r == wws.ClampResult(None, time(18, 15), None, time(19), 0, 15)


def test_preload_parameters_give_same_result(db, default_tenant):
    user = k_user(K_CASES[0])
    plain = wws.clamp(db, user, MON, time(7), time(19), 15, credit_override=False)
    pre = wws.clamp(db, user, MON, time(7), time(19), 15, credit_override=False,
                    wh_changes=[], soll_free_dates=set())
    assert pre == plain
    free = wws.clamp(db, user, MON, time(7), time(19), 15, credit_override=False,
                     wh_changes=[], soll_free_dates={MON})
    assert free == wws.ClampResult(time(7), time(19), None, None, 0, None)


@pytest.mark.parametrize("cid, minutes", [("K7", 720), ("K8", 120), ("K15", 615), ("K20", 660)])
def test_presence_minutes(db, k_setup, cid, minutes):
    case = next(c for c in K_CASES if c.id == cid)
    r = wws.clamp(db, k_user(case), case.day, case.start, case.end, 15, credit_override=False)
    assert wws.presence_minutes(_entry(case, r)) == minutes


def test_hull_text_is_byte_identical_to_1_19():
    r = wws.ClampResult(time(7, 45), time(16, 0), time(7, 37), None, 0, 15)
    assert wws.clamp_warning_text(None, None, None, r, for_employee=True) == (
        "Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt "
        "(Beginn 07:37 → 07:45; Puffer 15 Minuten). Angerechnet wird die gekappte Zeit; "
        "die urspruengliche Eingabe bleibt als Rohstempel gespeichert."
    )


def test_gap_text_and_employee_hint(db, default_tenant):
    user = k_user(K_CASES[0])
    r = wws.clamp(db, user, MON, time(8), time(18), 15, credit_override=False)
    assert wws.clamp_warning_text(db, user, MON, r, for_employee=False) == (
        "Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden "
        "2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."
    )
    with_hint = wws.clamp_warning_text(db, user, MON, r, for_employee=True)
    assert with_hint.endswith(wws.EMPLOYEE_CREDIT_HINT)
    assert wws.clamp_warning(db, user, MON, r, for_employee=False).startswith("WORK_WINDOW_CLAMPED: Zwischen")


def test_clock_in_gap_text(db, default_tenant):
    user = k_user(K_CASES[0])
    r = wws.clamp(db, user, MON, time(13), None, 15, credit_override=False)
    assert wws.clamp_warning_text(db, user, MON, r, for_employee=True) == (
        "Eingestempelt zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) "
        "— angerechnet wird erst ab 14:45."
    )


def test_clamp_applies(db, default_tenant):
    user = k_user(K_CASES[0])
    assert wws.clamp_applies(db, user, MON, credit_override=False) is True
    assert wws.clamp_applies(db, user, MON, credit_override=True) is False
    user.track_hours = False
    assert wws.clamp_applies(db, user, MON, credit_override=False) is False
    user.track_hours = True
    user.work_blocks = None
    assert wws.clamp_applies(db, user, MON, credit_override=False) is False


def test_grace_for_entry_prefers_stored_value(db, default_tenant):
    db.add(SystemSetting(key="work_window_grace_minutes", value="0", tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    stored = TimeEntry(tenant_id=DEFAULT_TENANT_ID, clamp_grace_minutes=15)
    legacy = TimeEntry(tenant_id=DEFAULT_TENANT_ID, clamp_grace_minutes=None)
    assert wws.grace_for_entry(db, stored) == 15
    assert wws.grace_for_entry(db, legacy) == 0


# Review Focus 5: Uhrzeiten mit Sekunden an der Hüllkante — wie 072.
def test_seconds_at_the_hull_edge_behave_like_072(db, default_tenant):
    user = User(username="s", email="s@x.de", password_hash="h", first_name="S", last_name="S",
                role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
                track_hours=True, tenant_id=DEFAULT_TENANT_ID,
                work_blocks=legacy_week(mon=("08:00", "18:00")))
    late = wws.clamp(db, user, MON, time(9), time(18, 15, 30), 15, credit_override=False)
    assert (late.eff_end, late.raw_end) == (time(18, 15), time(18, 15, 30))
    early = wws.clamp(db, user, MON, time(7, 44, 30), time(17), 15, credit_override=False)
    assert (early.eff_start, early.raw_start) == (time(7, 45), time(7, 44, 30))
    edge = wws.clamp(db, user, MON, time(9), time(18, 15), 15, credit_override=False)
    assert edge.raw_end is None
```

- [ ] **Step 3: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_clamp_blocks.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'app.services.work_window_service' has no attribute 'ClampResult'`

- [ ] **Step 4: `work_window_service.py` komplett ersetzen**

```python
"""Arbeitszeit-Blöcke (Spec 2026-10-08, Abschnitt 6) — kappt das Ist beim Schreiben.

Quelle sind die Blöcke des DATUMSAUFGELÖSTEN Vertrags-Snapshots
(``calculation_service.get_schedule_for_date``), nie ein Live-Feld der
User-Zeile. Altfenster aus Migration 073 sind Einblock-Tage und kappen exakt wie
die früheren #201-Fenster (Hülle). Zeit zwischen zwei Blöcken wird nicht
angerechnet (``uncredited_minutes``); der Beginn wird nie in eine Lücke
verschoben (E33), nur die Hülle verschiebt Beginn/Ende und bewahrt den
Rohstempel (§16, §5).

Keine Kappung an Wochenenden, Feiertagen und freien Sondertagen (#484), bei
``track_hours=False`` und für anerkannte Einträge (``credit_override``).
"""
from datetime import date, time
from typing import NamedTuple, Optional

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting
from app.services import calculation_service

DEFAULT_GRACE_MINUTES = 15
# #462: Kennung der weichen Warnung ("CODE: Text", läuft durch showArbzgWarnings).
CLAMP_WARNING_CODE = "WORK_WINDOW_CLAMPED"
_LAST_MINUTE = 23 * 60 + 59
# Spec 6.2 / P21: nur Mitarbeiterpfade, nur an Lückentexten geschlossener Einträge.
EMPLOYEE_CREDIT_HINT = (
    " Haben Sie in dieser Zeit gearbeitet, beantragen Sie die Anrechnung "
    "(Zeiterfassung → Eintrag → „Anrechnung beantragen“)."
)


class ClampResult(NamedTuple):
    eff_start: Optional[time]
    eff_end: Optional[time]
    raw_start: Optional[time]
    raw_end: Optional[time]
    uncredited_minutes: int
    grace_minutes: Optional[int]   # angewandter Puffer; None = nicht gegen Blöcke gekappt (E79)


def get_grace_minutes(db: Session, tenant_id) -> int:
    """work_window_grace_minutes aus system_settings (Default 15, >= 0)."""
    s = db.query(SystemSetting).filter(
        SystemSetting.key == "work_window_grace_minutes",
        SystemSetting.tenant_id == tenant_id,
    ).first()
    if not s:
        return DEFAULT_GRACE_MINUTES
    try:
        return max(0, int(s.value))
    except (TypeError, ValueError):
        return DEFAULT_GRACE_MINUTES


def grace_for_entry(db: Session, entry) -> int:
    """Puffer für die Einzel-Neukappung eines GESPEICHERTEN Eintrags (E80): der
    bei der letzten Kappung gespeicherte Wert, sonst (Bestand vor 073 / nie
    gegen Blöcke gekappt) der aktuelle Mandanten-Puffer."""
    if entry.clamp_grace_minutes is not None:
        return entry.clamp_grace_minutes
    return get_grace_minutes(db, entry.tenant_id)


def _is_soll_free_weekday(db: Session, user, d: date) -> bool:
    """#484: Feiertag des Mandanten oder als ``free`` konfigurierter Sondertag."""
    from app.services.holiday_service import is_holiday
    from app.services.special_days_service import free_special_days_in_range

    tenant_id = getattr(user, "tenant_id", None)
    if is_holiday(db, d, tenant_id=tenant_id):
        return True
    return d in free_special_days_in_range(db, tenant_id, d, d)


def _min(t: time) -> int:
    return t.hour * 60 + t.minute


def _t(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _shift_min(minutes: int, delta: int) -> int:
    """Auf [00:00, 23:59] des Tages begrenzt (wie das frühere ``_shift``)."""
    return max(0, min(minutes + delta, _LAST_MINUTE))


def _hhmm(t: Optional[time]) -> str:
    return t.strftime("%H:%M") if t else "?"


def _mm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def get_scheduled_blocks(db: Session, user, d: date, *, wh_changes=None,
                         soll_free_dates=None) -> list:
    """Blöcke des Datums in Minuten seit Mitternacht, sortiert.

    ``[]`` am Wochenende, ohne Blöcke im datumsaufgelösten Snapshot, an
    Feiertagen und an freien Sondertagen (#484). ``wh_changes`` /
    ``soll_free_dates``: optional vorgeladen (Muster #449); ohne sie fragt die
    Funktion je Aufruf den Resolver bzw. die Feiertage ab."""
    if d.weekday() > 4:
        return []
    sched = calculation_service.get_schedule_for_date(db, user, d, wh_changes)
    if sched.blocks is None or not sched.blocks[d.weekday()]:
        return []
    if soll_free_dates is not None:
        if d in soll_free_dates:
            return []
    elif _is_soll_free_weekday(db, user, d):
        return []
    return list(sched.blocks[d.weekday()])


def has_blocks(db: Session, user, d: date, **preload) -> bool:
    return bool(get_scheduled_blocks(db, user, d, **preload))


def clamp_applies(db: Session, user, d: date, *, credit_override: bool, **preload) -> bool:
    """Kappt ``clamp`` an diesem Tag überhaupt? (XLS-Gate, E38 — statt
    ``has_blocks`` allein, sonst löschte ``track_hours=False`` + Blöcke ein
    mitgeliefertes ``raw_*``.)"""
    return (
        user is not None
        and bool(getattr(user, "track_hours", True))
        and not credit_override
        and has_blocks(db, user, d, **preload)
    )


def credit_gaps(blocks, grace: int) -> list:
    """Innere Lücken, um den Puffer an BEIDEN Rändern geschrumpft (E5).
    Eine Lücke ≤ 2 × Puffer verschwindet."""
    gaps = []
    for (_, end_a), (start_b, _) in zip(blocks, blocks[1:]):
        gs, ge = end_a + grace, start_b - grace
        if ge > gs:
            gaps.append((gs, ge))
    return gaps


def _clamp_core(db, user, d, start, end, grace, *, credit_override, wh_changes, soll_free_dates):
    if credit_override or user is None or not getattr(user, "track_hours", True):
        return ClampResult(start, end, None, None, 0, None), []
    blocks = get_scheduled_blocks(db, user, d, wh_changes=wh_changes, soll_free_dates=soll_free_dates)
    if not blocks:
        return ClampResult(start, end, None, None, 0, None), []

    floor = _t(_shift_min(blocks[0][0], -grace))
    ceil = _t(_shift_min(blocks[-1][1], grace))
    eff_start, eff_end, raw_start, raw_end = start, end, None, None
    # Vergleich als Uhrzeit (nicht in Minuten): exakt das Verhalten von 072
    # auch für Eingaben mit Sekunden (Kappungsparität, Spec 17.1).
    if start is not None and start < floor:
        eff_start, raw_start = floor, start
    if end is not None and end > ceil:
        eff_end, raw_end = ceil, end

    # Kollaps außerhalb der Hülle — unverändert seit #201 (0 h, Stempel bleiben).
    if eff_start is not None and eff_end is not None and eff_start >= eff_end:
        return ClampResult(start, start, start, end, 0, grace), []
    # Offener Eintrag (P17: Hülle gilt) bzw. Teil-Update ohne Beginn: keine Lücke.
    if eff_start is None or eff_end is None:
        return ClampResult(eff_start, eff_end, raw_start, raw_end, 0, grace), []

    s, e = _min(eff_start), _min(eff_end)
    segments = [o for o in (_overlap(s, e, gs, ge) for gs, ge in credit_gaps(blocks, grace)) if o > 0]
    return ClampResult(eff_start, eff_end, raw_start, raw_end, sum(segments), grace), segments


def clamp(db: Session, user, d: date, start: Optional[time], end: Optional[time], grace: int,
          *, credit_override: bool, wh_changes=None, soll_free_dates=None) -> ClampResult:
    """Spec 6.1. ``credit_override`` ist pflichtiges Schlüsselwort (P6): jede
    Aufrufstelle entscheidet ausdrücklich. Der Aufrufer bestimmt ``grace``
    (E80): aktueller Mandanten-Puffer bei Neuanlage, ``grace_for_entry`` bei
    Einzel-Neukappung eines gespeicherten Eintrags."""
    return _clamp_core(db, user, d, start, end, grace, credit_override=credit_override,
                       wh_changes=wh_changes, soll_free_dates=soll_free_dates)[0]


def gap_segments(db: Session, user, d: date, start: Optional[time], end: Optional[time], grace: int,
                 *, credit_override: bool, wh_changes=None, soll_free_dates=None) -> list:
    """Die Überlappungen mit den Lücken je Lücke (für §4, XLS-Auto-Pause).
    Invariante: ``sum(gap_segments(...)) == clamp(...).uncredited_minutes``."""
    return _clamp_core(db, user, d, start, end, grace, credit_override=credit_override,
                       wh_changes=wh_changes, soll_free_dates=soll_free_dates)[1]


def _hull_sentence(teile, grace) -> str:
    # Byte-identisch zu 1.19 (in der Doku zitiert) — ASCII-Umschrift bleibt.
    return (
        f"Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster "
        f"gekappt ({', '.join(teile)}; Puffer {grace} Minuten). "
        f"Angerechnet wird die gekappte Zeit; die urspruengliche Eingabe bleibt "
        f"als Rohstempel gespeichert."
    )


def clamp_warning_text(db: Session, user, d: date, result: ClampResult, *,
                       for_employee: bool) -> Optional[str]:
    """Klartext der Kappungs-Warnung (Spec 6.2) — oder None.

    DIE eine Quelle des Textes (#462). Der genannte Puffer ist der tatsächlich
    angewandte (``result.grace_minutes``, E80). ``db``/``user``/``d`` werden nur
    gelesen, wenn eine Lücke aufzulösen ist. Ohne Code-Präfix (XLS-Vorschau)."""
    if result.grace_minutes is None:
        return None
    g = result.grace_minutes
    es, ee, rs, re_ = result.eff_start, result.eff_end, result.raw_start, result.raw_end

    teile = []
    if rs is not None and es is not None and rs != es:
        teile.append(f"Beginn {_hhmm(rs)} → {_hhmm(es)}")
    if re_ is not None and ee is not None and re_ != ee:
        teile.append(f"Ende {_hhmm(re_)} → {_hhmm(ee)}")

    if es is not None and ee is not None and es == ee:
        roh_start, roh_end = rs or es, re_ or ee
        return (
            f"Die eingetragene Zeit ({_hhmm(roh_start)}–{_hhmm(roh_end)}) liegt "
            f"vollstaendig ausserhalb des hinterlegten Arbeitszeit-Fensters "
            f"(Puffer {g} Minuten) — angerechnet werden 0 Stunden. "
            f"Die urspruengliche Eingabe bleibt als Rohstempel gespeichert."
        )

    if ee is None:  # offener Eintrag
        if teile:
            return _hull_sentence(teile, g)
        if es is None:
            return None
        s = _min(es)
        for gs, ge in credit_gaps(get_scheduled_blocks(db, user, d), g):
            if gs <= s < ge:
                return (
                    f"Eingestempelt zwischen zwei Arbeitsblöcken (Lücke {_mm(gs)}–{_mm(ge)}, "
                    f"Puffer {g} Minuten) — angerechnet wird erst ab {_mm(ge)}."
                )
        return None

    hull = _hull_sentence(teile, g) if teile else None
    if result.uncredited_minutes <= 0:
        return hull

    s, e = _min(es), _min(ee)
    hit = [(gs, ge) for gs, ge in credit_gaps(get_scheduled_blocks(db, user, d), g)
           if _overlap(s, e, gs, ge) > 0]
    spans = ", ".join(f"{_mm(gs)}–{_mm(ge)}" for gs, ge in hit)
    u = _hm(result.uncredited_minutes)
    if hit and result.uncredited_minutes >= e - s:
        gs, ge = hit[0]
        text = (
            f"Die eingetragene Zeit ({_hhmm(es)}–{_hhmm(ee)}) liegt vollständig zwischen "
            f"zwei Arbeitsblöcken (Lücke {_mm(gs)}–{_mm(ge)}, Puffer {g} Minuten) — "
            f"angerechnet werden 0 Stunden. Die gestempelte Zeit bleibt gespeichert."
        )
    elif hull:
        text = hull + f" Zusätzlich werden zwischen den Arbeitsblöcken ({spans}) {u} h nicht angerechnet."
    else:
        text = (
            f"Zwischen den Arbeitsblöcken ({spans}, Puffer {g} Minuten eingerechnet) werden "
            f"{u} h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."
        )
    if for_employee:
        text += EMPLOYEE_CREDIT_HINT
    return text


def clamp_warning(db: Session, user, d: date, result: ClampResult, *,
                  for_employee: bool) -> Optional[str]:
    """Wie ``clamp_warning_text``, mit Code-Präfix für die ``warnings``-Fläche."""
    text = clamp_warning_text(db, user, d, result, for_employee=for_employee)
    return f"{CLAMP_WARNING_CODE}: {text}" if text else None


def unclamp_input(
    incoming: Optional[time], prev_eff: Optional[time], prev_raw: Optional[time],
) -> Optional[time]:
    """Schickt ein Formular die zuvor GEKAPPTE Zeit unveraendert zurueck, ist das
    keine Eingabe — sondern derselbe Eintrag. Dann mit dem Rohwert weiterrechnen
    (Release-Review 1.19.1). Ein echter Wechsel läuft unverändert durch."""
    if incoming is not None and prev_raw is not None and incoming == prev_eff:
        return prev_raw
    return incoming


def not_credited_minutes(entry) -> int:
    """P19: nicht angerechnete Anwesenheit eines Eintrags = ``uncredited_minutes``
    + von der Hülle gekappte Minuten (``eff_start − raw_start``,
    ``raw_end − eff_end``; 0 ohne ``raw_*``; Endseite bei ``auto_closed``
    ausgenommen, dort ist 23:59 kein Stempel, P18). Frontend-Zwilling (PR2):
    ``utils/workBlocks.ts::notCreditedMinutes``."""
    total = int(getattr(entry, "uncredited_minutes", 0) or 0)
    if entry.start_time is not None and entry.raw_start_time is not None:
        total += max(0, _min(entry.start_time) - _min(entry.raw_start_time))
    if (entry.end_time is not None and entry.raw_end_time is not None
            and not getattr(entry, "auto_closed", False)):
        total += max(0, _min(entry.raw_end_time) - _min(entry.end_time))
    return total


def presence_minutes(entry) -> int:
    """Spec 8.3: Anwesenheit laut Stempel = (raw_end oder end) − (raw_start oder
    start) − erfasste Pause; bei ``auto_closed`` bis zum wirksamen Ende; offene
    Einträge zählen nicht."""
    if entry.end_time is None:
        return 0
    start = entry.raw_start_time or entry.start_time
    end = entry.end_time if getattr(entry, "auto_closed", False) else (entry.raw_end_time or entry.end_time)
    return max(0, _min(end) - _min(start) - int(entry.break_minutes or 0))
```

Falls beim Import ein Zirkelimport `calculation_service` ↔ `work_window_service` auftritt, den Modulimport `from app.services import calculation_service` in `get_scheduled_blocks` verlegen (lokaler Import) — sonst nichts ändern.

- [ ] **Step 5: `test_work_window_service.py` komplett ersetzen**

```python
"""#201 → Spec 2026-10-08: Kappung gegen Altfenster (Einblock-Tage aus 073).

Kappungsparität: dieselben Fälle wie bis 1.19.3, jetzt über ``work_blocks``
(``legacy_week``) statt ``scheduled_*`` und mit ``ClampResult``."""
from datetime import date, time

import pytest

from app.models import TimeEntry, User, UserRole
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.services import work_window_service as wws
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import legacy_week

MON = date(2026, 6, 1)
EASTER_MONDAY = date(2026, 4, 6)
DEC24 = date(2026, 12, 24)


def _user(**kw):
    defaults = dict(
        username="w", email="w@x.de", password_hash="h", first_name="W", last_name="W",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
        track_hours=True,
    )
    defaults.update(kw)
    return User(**defaults)


def _c(db, user, d, start, end, grace=15):
    return wws.clamp(db, user, d, start, end, grace, credit_override=False)


def test_no_window_no_clamp(db):
    assert _c(db, _user(), MON, time(7, 0), time(17, 0)) == wws.ClampResult(
        time(7, 0), time(17, 0), None, None, 0, None)


def test_early_start_capped(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", None))), MON, time(7, 0), time(16, 0))
    assert (r.eff_start, r.raw_start, r.eff_end, r.raw_end) == (time(7, 45), time(7, 0), time(16, 0), None)
    assert (r.uncredited_minutes, r.grace_minutes) == (0, 15)


def test_within_grace_not_capped(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", None))), MON, time(7, 50), time(16, 0))
    assert r.eff_start == time(7, 50) and r.raw_start is None


def test_late_end_capped(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=(None, "17:00"))), MON, time(8, 0), time(18, 30))
    assert r.eff_end == time(17, 15) and r.raw_end == time(18, 30)


def test_track_hours_false_skips(db):
    r = _c(db, _user(track_hours=False, work_blocks=legacy_week(mon=("08:00", None))), MON, time(6, 0), time(16, 0))
    assert r.eff_start == time(6, 0) and r.raw_start is None and r.grace_minutes is None


def test_open_end_none_passthrough(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", "17:00"))), MON, time(6, 0), None)
    assert r.eff_end is None and r.raw_end is None


def test_grace_shift_clamps_to_day_bounds(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=(None, "23:50"))), MON, time(8, 0), time(23, 59))
    assert r.eff_end == time(23, 59)


def test_entry_entirely_before_window_zero_credit(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("14:00", "18:00"))), MON, time(8, 0), time(9, 0))
    assert r.eff_start == r.eff_end
    assert (r.raw_start, r.raw_end) == (time(8, 0), time(9, 0))


def test_entry_entirely_after_window_zero_credit(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", "10:00"))), MON, time(14, 0), time(15, 0))
    assert r.eff_start == r.eff_end
    assert (r.raw_start, r.raw_end) == (time(14, 0), time(15, 0))


def test_entirely_outside_entry_has_zero_net_hours(db):
    r = _c(db, _user(work_blocks=legacy_week(mon=("08:00", "10:00"))), MON, time(14, 0), time(15, 0))
    te = TimeEntry(start_time=r.eff_start, end_time=r.eff_end, break_minutes=0,
                   raw_start_time=r.raw_start, raw_end_time=r.raw_end)
    assert te.net_hours == 0
    assert te.raw_start_time == time(14, 0) and te.raw_end_time == time(15, 0)


def test_half_open_placeholders_behave_like_072(db):
    """Spec 5.3: Platzhalter 00:00/23:59 verhalten sich wie das fehlende Ende."""
    start_only = _user(work_blocks=legacy_week(mon=("08:00", None)))
    r = _c(db, start_only, MON, time(9, 0), time(23, 59))
    assert (r.eff_end, r.raw_end) == (time(23, 59), None)
    end_only = _user(work_blocks=legacy_week(mon=(None, "17:00")))
    r = _c(db, end_only, MON, time(0, 0), time(16, 0))
    assert (r.eff_start, r.raw_start) == (time(0, 0), None)


# ── #484: keine Kappung an soll-freien Werktagen ──────────────────────────────

def _windowed_user():
    return _user(
        tenant_id=DEFAULT_TENANT_ID,
        work_blocks=legacy_week(mon=("08:00", "17:00"), thu=("08:00", "17:00")),
    )


def _holiday(db, d, tenant_id=DEFAULT_TENANT_ID):
    db.add(PublicHoliday(date=d, name="Feiertag", year=d.year, tenant_id=tenant_id))
    db.commit()
    invalidate_holiday_cache()


def _dec24_mode(db, mode):
    db.add(SystemSetting(key="special_day_dec24_mode", value=mode, tenant_id=DEFAULT_TENANT_ID))
    db.commit()


@pytest.fixture
def fresh_holiday_cache():
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


def test_window_still_applies_on_ordinary_monday(db, default_tenant, fresh_holiday_cache):
    r = _c(db, _windowed_user(), MON, time(7, 0), time(18, 0))
    assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == (time(7, 45), time(17, 15), time(7, 0), time(18, 0))


def test_holiday_on_weekday_has_no_window(db, default_tenant, fresh_holiday_cache):
    _holiday(db, EASTER_MONDAY)
    r = _c(db, _windowed_user(), EASTER_MONDAY, time(7, 0), time(18, 0))
    assert r == wws.ClampResult(time(7, 0), time(18, 0), None, None, 0, None)
    assert wws.get_scheduled_blocks(db, _windowed_user(), EASTER_MONDAY) == []


def test_holiday_of_another_tenant_does_not_lift_the_window(db, default_tenant, fresh_holiday_cache):
    import uuid
    other = Tenant(id=uuid.uuid4(), name="Andere Praxis", slug="andere-praxis")
    db.add(other)
    db.commit()
    _holiday(db, EASTER_MONDAY, tenant_id=other.id)
    r = _c(db, _windowed_user(), EASTER_MONDAY, time(7, 0), time(18, 0))
    assert (r.raw_start, r.raw_end) == (time(7, 0), time(18, 0))


def test_free_special_day_has_no_window(db, default_tenant, fresh_holiday_cache):
    _dec24_mode(db, "free")
    r = _c(db, _windowed_user(), DEC24, time(7, 0), time(18, 0))
    assert r == wws.ClampResult(time(7, 0), time(18, 0), None, None, 0, None)


def test_half_special_day_keeps_the_window(db, default_tenant, fresh_holiday_cache):
    _dec24_mode(db, "half_day")
    r = _c(db, _windowed_user(), DEC24, time(7, 0), time(18, 0))
    assert (r.raw_start, r.raw_end) == (time(7, 0), time(18, 0))
```

Die neue Datei enthält alle 15 bisherigen Fälle (über `work_blocks=legacy_week(...)` und die Felder von `ClampResult`) plus `test_half_open_placeholders_behave_like_072`. Kontrolle: `git show HEAD:backend/tests/test_work_window_service.py | grep -c '^def test_'` ergibt 15, `grep -c '^def test_' backend/tests/test_work_window_service.py` ergibt 16.

- [ ] **Step 6: Aufrufer mechanisch umstellen (Verhalten unverändert)**

`backend/app/routers/time_entries.py`, `clock_in`:

```python
    _r = work_window_service.clamp(
        db, current_user, now.date(), start_t, None, grace, credit_override=False,
    )
    eff_start, raw_start = _r.eff_start, _r.raw_start
```

und den Warnblock ersetzen — den Kommentar „#462: Hier KEINE zusaetzliche WORK_WINDOW_CLAMPED-Meldung …" samt `if raw_start is not None:`-Block (Spec 7.1 Nr. 1: vor der Hülle unverändert `EARLY_START`, in der Lücke derselbe Text wie überall):

```python
    # #462: Vor der Hülle meldet EARLY_START die Kappung (zielgruppengerecht,
    # keine zweite WORK_WINDOW_CLAMPED-Meldung). Spec 6.2/7.1 Nr. 1: wer
    # ZWISCHEN zwei Blöcken einstempelt, bekommt den gemeinsamen Lückentext
    # („angerechnet wird erst ab …").
    if raw_start is not None:
        clock_in_warnings.append(
            f"EARLY_START: Du hast vor deinem Soll-Beginn eingestempelt — angerechnet ab {eff_start.strftime('%H:%M')}."
        )
    else:
        # Spec 6.2: Einstempeln zwischen zwei Blöcken (K2) — derselbe Text wie
        # überall, angerechnet wird erst ab dem Ende der Lücke.
        _gap_warn = work_window_service.clamp_warning(
            db, current_user, now.date(), _r, for_employee=True,
        )
        if _gap_warn:
            clock_in_warnings.append(_gap_warn)
```

`clock_out`:

```python
    _r = work_window_service.clamp(
        db, current_user, open_entry.date, open_entry.start_time, new_end_time, grace,
        credit_override=open_entry.credit_override,
    )
    eff_end, raw_end = _r.eff_end, _r.raw_end
```

und die Warnung:

```python
    _clamp_warn = work_window_service.clamp_warning(
        db, current_user, open_entry.date, _r, for_employee=True,
    )
```

`create_time_entry`:

```python
    _r = work_window_service.clamp(
        db, current_user, entry_data.date, entry_data.start_time, entry_data.end_time, _grace,
        credit_override=False,
    )
    eff_start, eff_end, raw_start, raw_end = _r.eff_start, _r.eff_end, _r.raw_start, _r.raw_end
```

und `_clamp_warn = work_window_service.clamp_warning(db, current_user, entry_data.date, _r, for_employee=True)`.

`update_time_entry`:

```python
    _r = work_window_service.clamp(
        db, _entry_owner, entry.date, _clamp_start, _clamp_end, _grace,
        credit_override=entry.credit_override,
    )
    _eff_start, _eff_end, _raw_start, _raw_end = _r.eff_start, _r.eff_end, _r.raw_start, _r.raw_end
```

und im Warnblock `_clamp_warn = work_window_service.clamp_warning(db, _entry_owner, entry.date, _r, for_employee=True)`.

`backend/app/routers/admin_time_entries.py`, `admin_create_time_entry`:

```python
    _r = work_window_service.clamp(
        db, user, entry_data.date, entry_data.start_time, entry_data.end_time, _grace,
        credit_override=False,
    )
    eff_start, eff_end, raw_start, raw_end = _r.eff_start, _r.eff_end, _r.raw_start, _r.raw_end
```

und `_clamp_warn = work_window_service.clamp_warning(db, user, entry_data.date, _r, for_employee=False)`.

`admin_update_time_entry` — der `if affected_user is not None … else`-Block wird (clamp ist None-sicher):

```python
    _r = work_window_service.clamp(
        db, affected_user, update_date, update_start_time, update_end_time, _grace,
        credit_override=entry.credit_override,
    )
    eff_start, eff_end, raw_start, raw_end = _r.eff_start, _r.eff_end, _r.raw_start, _r.raw_end
```

und `_clamp_warn = work_window_service.clamp_warning(db, affected_user, update_date, _r, for_employee=False)`.

`backend/app/routers/admin_change_requests.py` — Vorprüfung:

```python
                _r_pre = work_window_service.clamp(
                    db, cr_user, cr.proposed_date, _in_start, _in_end, _grace,
                    credit_override=bool(entry is not None and entry.credit_override),
                )
                _eff_start, _eff_end = _r_pre.eff_start, _r_pre.eff_end
```

CREATE-Zweig:

```python
            _r = work_window_service.clamp(
                db, _cr_user_te, cr.proposed_date, _in_start, _in_end, _grace,
                credit_override=False,
            )
            eff_start, eff_end, raw_start, raw_end = _r.eff_start, _r.eff_end, _r.raw_start, _r.raw_end
            _clamp_warn = work_window_service.clamp_warning(
                db, _cr_user_te, cr.proposed_date, _r, for_employee=False,
            )
```

UPDATE-Zweig identisch mit `credit_override=entry.credit_override`. Nachprüfung nach dem Commit:

```python
            _rw = work_window_service.clamp(
                db, cr_user, cr.proposed_date, _in_start, _in_end, _wgrace,
                credit_override=bool(getattr(entry, "credit_override", False)),
            )
            _w_start, _w_end = _rw.eff_start, _rw.eff_end
```

`backend/app/services/xls_import_service.py`, `parse_xls`:

```python
        if user is not None:
            _r = work_window_service.clamp(
                db, user, entry_date, start_t, end_t, grace, credit_override=False,
            )
            start_t, end_t, raw_start_t, raw_end_t = _r.eff_start, _r.eff_end, _r.raw_start, _r.raw_end
        else:
            _r = work_window_service.ClampResult(start_t, end_t, None, None, 0, None)
            raw_start_t = raw_end_t = None
```

und die Kappungsnotiz:

```python
        if raw_start_t is not None or raw_end_t is not None:
            clamp_note = work_window_service.clamp_warning_text(
                db, user, entry_date, _r, for_employee=False,
            )
```

`_execute_import_inner`:

```python
        _hat_fenster = target_user is not None and work_window_service.has_blocks(
            db, target_user, entry.date,
        )
        if _hat_fenster:
            _r = work_window_service.clamp(
                db, target_user,
                entry.date,
                entry.raw_start_time or entry.start_time,
                entry.raw_end_time or entry.end_time,
                grace,
                credit_override=False,
            )
            entry = entry.model_copy(update={
                "start_time": _r.eff_start,
                "end_time": _r.eff_end,
                "raw_start_time": _r.raw_start,
                "raw_end_time": _r.raw_end,
            })
```

Danach: `grep -n "work_window_service.clamp(\|clamp_warning(\|get_scheduled_window" backend/app -r` — jede Fundstelle trägt `credit_override=` bzw. die neue Signatur; `get_scheduled_window` kommt nicht mehr vor.

- [ ] **Step 7: Bestandstests auf `work_blocks` umstellen**

Einmal-Umschreibung der `scheduled_*`-Zuweisungen in den fünf betroffenen Testdateien: alle Zuweisungen **eines Objekts** in aufeinanderfolgenden Zeilen werden zu **einer** Zuweisung `<obj>.work_blocks = legacy_week(...)` (nur Beginn → `("08:00", None)`, nur Ende → `(None, "17:00")`, nur `None`-Zuweisungen → `work_blocks = None`), Konstruktor-Kwargs zu `work_blocks=legacy_week(...)`, und `from tests.work_blocks_fixtures import legacy_week` wird ergänzt. Das Skript wird nur ausgeführt, nicht eingecheckt:

```bash
python3 - backend/tests/test_work_window_integration.py backend/tests/test_xls_import_service.py \
  backend/tests/test_486_bulk_warnings.py backend/tests/test_break_waiver.py \
  backend/tests/test_admin_entry_date_change_keeps_raw.py <<'PYEOF'
import re
import sys
from pathlib import Path

DAY = {"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu", "friday": "fri"}
ASSIGN = re.compile(
    r"^(?P<ind>\s*)(?P<obj>[\w.]+)\.scheduled_(?P<kind>start|end)_(?P<day>\w+day)\s*=\s*"
    r"(?:(?:dt\.)?time\((?P<h>\d+),\s*(?P<m>\d+)\)|None)\s*(?P<comment>#.*)?$"
)
KWARG = re.compile(
    r"scheduled_(?P<kind>start|end)_(?P<day>\w+day)=(?:dt\.)?time\((?P<h>\d+),\s*(?P<m>\d+)\),?\s*"
)


def _fmt(h, m):
    return f'"{int(h):02d}:{int(m):02d}"'


def _week(days):
    parts = [f"{DAY[d]}=({days[d].get('start') or 'None'}, {days[d].get('end') or 'None'})"
             for d in DAY if d in days]
    return f"legacy_week({', '.join(parts)})" if parts else "None"


def convert(text):
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        m = ASSIGN.match(lines[i])
        if m is None and KWARG.search(lines[i]):
            days, j = {}, i
            ind = re.match(r"^\s*", lines[i]).group(0)
            rest = KWARG.sub("", lines[i]).strip()
            while j < len(lines) and KWARG.search(lines[j]) and (j == i or not KWARG.sub("", lines[j]).strip()):
                for k in KWARG.finditer(lines[j]):
                    days.setdefault(k["day"], {})[k["kind"]] = _fmt(k["h"], k["m"])
                j += 1
            if rest:
                out.append(ind + rest)
            out.append(f"{ind}work_blocks={_week(days)},")
            i = j
            continue
        if m is None:
            out.append(lines[i])
            i += 1
            continue
        days, comment, j = {}, m["comment"], i
        while j < len(lines) and (mm := ASSIGN.match(lines[j])) and mm["obj"] == m["obj"]:
            if mm["h"] is not None:
                days.setdefault(mm["day"], {})[mm["kind"]] = _fmt(mm["h"], mm["m"])
            comment = comment or mm["comment"]
            j += 1
        out.append(f"{m['ind']}{m['obj']}.work_blocks = {_week(days)}" + (f"  {comment}" if comment else ""))
        i = j
    result = "\n".join(out)
    if "legacy_week(" in result and "import legacy_week" not in result:
        anchor = result.find("from tests.conftest import")
        insert_at = result.find("\n\n", anchor if anchor != -1 else 0)
        result = result[:insert_at] + "\nfrom tests.work_blocks_fixtures import legacy_week" + result[insert_at:]
    return result


for name in sys.argv[1:]:
    path = Path(name)
    path.write_text(convert(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("umgeschrieben:", name)
PYEOF
grep -n "scheduled_start_\|scheduled_end_" backend/tests/test_work_window_integration.py backend/tests/test_xls_import_service.py backend/tests/test_486_bulk_warnings.py backend/tests/test_break_waiver.py backend/tests/test_admin_entry_date_change_keeps_raw.py
```

Expected: fünf Zeilen „umgeschrieben: …"; das `grep` findet nur noch zwei Kommentar-/Docstring-Zeilen in `test_work_window_integration.py` („# scheduled_start_monday bleibt NULL …" und „Soll Mo 08:00 (scheduled_start_monday), grace=15 min → floor=07:45."). Beide von Hand umformulieren zu `# Kein Fenster hinterlegt (work_blocks bleibt NULL).` bzw. `Soll Mo 08:00 (work_blocks), grace=15 min → floor=07:45.` Stichprobe gegen diese Ergebnisse:

```python
# test_work_window_integration.py (vorher: employee.scheduled_start_monday = dt.time(8, 0))
employee.work_blocks = legacy_week(mon=("08:00", None))
# test_xls_import_service.py (vorher: Beginn 08:00 und Ende 17:00 in zwei Zeilen)
test_user.work_blocks = legacy_week(mon=("08:00", "17:00"))
# test_xls_import_service.py::test_parse_xls_without_soll_window_has_no_clamp_warning
test_user.work_blocks = None
# test_admin_entry_date_change_keeps_raw.py (Konstruktor-Kwargs)
        work_blocks=legacy_week(mon=("08:00", "16:00"), tue=("10:00", "18:00")),
# test_break_waiver.py
        employee.work_blocks = legacy_week(mon=("08:00", "16:00"))  # grace=15 → Fenster [07:45, 16:15]
```

In `backend/tests/test_break_waiver.py` den Kommentar „Soll-Fenster gibt es nur Mo–Fr (work_window_service._WEEKDAY_ATTR)" auf „(work_window_service.get_scheduled_blocks)" ändern — `_WEEKDAY_ATTR` gibt es nicht mehr.

`test_release_1_19_1_review.py`, Klasse `TestClampWarningCollapse` — die drei Aufrufe werden zu:

```python
from app.services.work_window_service import ClampResult

        text = work_window_service.clamp_warning_text(
            None, None, None,
            ClampResult(time(5, 0), time(5, 0), time(5, 0), time(6, 0), 0, 15),
            for_employee=False,
        )
```

(zweiter Test identisch) und

```python
        text = work_window_service.clamp_warning_text(
            None, None, None,
            ClampResult(time(7, 45), time(16, 0), time(7, 0), None, 0, 15),
            for_employee=False,
        )
```

- [ ] **Step 8: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_clamp_blocks.py tests/test_work_window_service.py tests/test_work_window_integration.py tests/test_xls_import_service.py tests/test_486_bulk_warnings.py tests/test_break_waiver.py tests/test_admin_entry_date_change_keeps_raw.py tests/test_release_1_19_1_review.py tests/test_fix2_update_keeps_raw.py -q -p no:cacheprovider`
Expected: PASS

Danach die volle SQLite-Suite: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (dieselbe Zahl Fehlschläge wie auf `master` vor PR1; neue Fehlschläge = 0)

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/work_window_service.py backend/app/routers backend/app/services/xls_import_service.py backend/tests
git commit -F - <<'EOF'
feat(bloecke): Kappungskern ClampResult (Hülle, Lücken, Puffer) und Umstellung aller Aufrufer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: `uncredited_minutes` durchgängig — `net_hours`, Netto-Helfer, Schreibstellen

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499: Schreibpfade in `time_entries.py`, `admin_time_entries.py`).

**Files:**
- Modify: `backend/app/models/time_entry.py:36-80` (`net_hours` Python + SQL)
- Modify: `backend/app/routers/time_entries.py:46-119` (`_net_hours`, `_calculate_daily_net_hours`, `_calculate_weekly_net_hours`) und Aufrufer 408, 505, 685, 785, 1014, 1149, 1161; Schreibstellen `clock_in`, `clock_out`, `create_time_entry`, `update_time_entry`
- Modify: `backend/app/routers/admin_time_entries.py` (Aufrufer 139, 156, 359, 376; Schreibstellen create/update)
- Modify: `backend/app/routers/admin_change_requests.py` (Aufrufer 391, 1022, 1044; Schreibstellen CREATE/UPDATE)
- Modify: `backend/app/routers/change_requests.py` (Aufrufer 218, 297, 321)
- Test: `backend/tests/test_clamp_blocks.py` (Netto-Spalte der Falltabelle), `backend/tests/test_net_hours_uncredited.py` (neu), `backend/tests/test_write_paths_uncredited.py` (neu); die SQL-Parität prüft `test_net_hours_parity_pg.py` in Task 14 (braucht Migration 073)

**Interfaces:**
- Consumes: `ClampResult`, `clamp` (Task 3); `TimeEntry.uncredited_minutes` (Task 2); `tests.work_blocks_cases.K_CASES`, `k_user`
- Produces:
  - `TimeEntry.net_hours` (Hybrid): Python `Decimal(str(max(round(dauer − pause/60 − (uncredited_minutes or 0)/60, 2), 0)))`; SQL `… − coalesce(uncredited_minutes, 0) / 60.0`, ohne Rundung je Zeile
  - `time_entries._net_hours(st: time, et: time, brk: int, uncredited: int) -> float` (4. Parameter Pflicht)
  - `time_entries._calculate_daily_net_hours(db, user_id, entry_date, start_time, end_time, break_minutes, *, uncredited_minutes: int, exclude_entry_id=None, tenant_id=None) -> float`
  - `time_entries._calculate_weekly_net_hours(db, user_id, entry_date, start_time, end_time, break_minutes, *, uncredited_minutes: int, exclude_entry_id=None, tenant_id=None) -> float`
  - Schreibregel: Pfade 1–6, 8, 9 speichern `uncredited_minutes = _r.uncredited_minutes`, sobald sie das Zeitpaar schreiben

- [ ] **Step 1: Failing tests schreiben**

An `backend/tests/test_clamp_blocks.py` anhängen:

```python
from decimal import Decimal


@pytest.mark.parametrize("case", K_CASES, ids=[c.id for c in K_CASES])
def test_k_table_net_hours(db, k_setup, case):
    r = wws.clamp(db, k_user(case), case.day, case.start, case.end, 15, credit_override=case.credit_override)
    assert _entry(case, r).net_hours == Decimal(case.exp_net)
```

`backend/tests/test_net_hours_uncredited.py`:

```python
"""Spec E13 / 7.1: nicht angerechnete Minuten in net_hours und den Netto-Helfern."""
from datetime import time

import pytest

from app.models import TimeEntry
from app.routers.time_entries import (
    _calculate_daily_net_hours, _calculate_weekly_net_hours, _net_hours,
)
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import MON


def test_net_hours_helper_subtracts_uncredited():
    assert _net_hours(time(8, 0), time(18, 0), 0, 150) == 7.5
    assert _net_hours(time(12, 30), time(14, 30), 0, 120) == 0.0


def test_net_hours_helper_requires_uncredited():
    with pytest.raises(TypeError):
        _net_hours(time(8, 0), time(18, 0), 0)


def test_daily_and_weekly_sum_use_stored_uncredited(db, test_user):
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                     start_time=time(8, 0), end_time=time(18, 0), break_minutes=0,
                     uncredited_minutes=150))
    db.commit()
    kwargs = dict(db=db, user_id=test_user.id, entry_date=MON, start_time=time(19, 0),
                  end_time=time(20, 0), break_minutes=0, uncredited_minutes=0,
                  tenant_id=DEFAULT_TENANT_ID)
    assert _calculate_daily_net_hours(**kwargs) == 8.5
    assert _calculate_weekly_net_hours(**kwargs) == 8.5


def test_helpers_require_uncredited_keyword(db, test_user):
    with pytest.raises(TypeError):
        _calculate_daily_net_hours(db=db, user_id=test_user.id, entry_date=MON,
                                   start_time=time(8), end_time=time(9), break_minutes=0)


def test_transient_entry_without_flush_counts_zero():
    """``or 0``: vor dem flush greift der Spalten-Default noch nicht."""
    e = TimeEntry(start_time=time(8, 0), end_time=time(9, 0), break_minutes=0)
    e.uncredited_minutes = None
    assert str(e.net_hours) == "1.0"
```

`backend/tests/test_write_paths_uncredited.py`:

```python
"""Spec 7.1 Nr. 1–6, 8, 9: jede schreibende Stelle speichert uncredited_minutes."""
import datetime as dt
from datetime import time
from decimal import Decimal

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

import app.routers.time_entries as te


def _blocks(db, user, blocks=K_BLOCKS):
    user.work_blocks = blocks
    db.commit()


def _entry(db, user, start, end, brk=0):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                  start_time=start, end_time=end, break_minutes=brk)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _today(monkeypatch, hh=12, mm=0):
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, hh, mm))


def test_clock_in_in_gap(_db_session, employee_user, employee_client, monkeypatch):
    _blocks(_db_session, employee_user)
    _today(monkeypatch, 13, 0)
    resp = employee_client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text
    assert any(w.startswith("WORK_WINDOW_CLAMPED: Eingestempelt zwischen") for w in resp.json()["warnings"])
    entry = _db_session.query(TimeEntry).one()
    assert entry.uncredited_minutes == 0


def test_clock_out_k2b(_db_session, employee_user, employee_client, monkeypatch):
    _blocks(_db_session, employee_user)
    _entry(_db_session, employee_user, time(13, 0), None)
    _today(monkeypatch, 18, 0)
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0})
    assert resp.status_code == 200, resp.text
    entry = _db_session.query(TimeEntry).one()
    assert entry.uncredited_minutes == 105
    assert entry.net_hours == Decimal("3.25")


def test_employee_create_k21(_db_session, employee_user, employee_client, monkeypatch):
    _blocks(_db_session, employee_user)
    _today(monkeypatch)
    resp = employee_client.post("/api/time-entries/", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "18:00", "break_minutes": 45})
    assert resp.status_code == 201, resp.text
    entry = _db_session.query(TimeEntry).one()
    assert (entry.uncredited_minutes, entry.net_hours) == (150, Decimal("6.75"))


def test_employee_update_writes_uncredited(_db_session, employee_user, employee_client, monkeypatch):
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8, 0), time(12, 0))
    _today(monkeypatch, 19, 0)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"end_time": "18:00", "break_minutes": 45})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.uncredited_minutes == 150


def test_admin_create_counts_daily_hours_on_credited_time(_db_session, employee_user, admin_client):
    """Spec 7.1 (Netto-Helfer): 06:00–19:00, Pause 45, Lücke 10:15–13:45 →
    angerechnet 8,75 h; ohne uncredited wären es 12,25 h und HTTP 422."""
    _blocks(_db_session, employee_user, block_week(mon=[("06:00", "10:00"), ("14:00", "19:00")]))
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "06:00", "end_time": "19:00", "break_minutes": 45})
    assert resp.status_code == 201, resp.text
    entry = _db_session.query(TimeEntry).one()
    assert (entry.uncredited_minutes, entry.net_hours) == (210, Decimal("8.75"))


def test_admin_update_writes_uncredited(_db_session, employee_user, admin_client):
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8, 0), time(12, 0))
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "18:00", "break_minutes": 45})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.uncredited_minutes == 150


def _cr(db, user, **kw):
    cr = ChangeRequest(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       status=ChangeRequestStatus.PENDING, proposed_date=MON,
                       proposed_start_time=time(8, 0), proposed_end_time=time(18, 0),
                       proposed_break_minutes=45, reason="Nachtrag", **kw)
    db.add(cr)
    db.commit()
    return cr


def test_cr_create_approval_writes_uncredited(_db_session, employee_user, admin_client):
    _blocks(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, request_type=ChangeRequestType.CREATE)
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    assert _db_session.query(TimeEntry).one().uncredited_minutes == 150


def test_cr_update_approval_writes_uncredited(_db_session, employee_user, admin_client):
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8, 0), time(12, 0))
    cr = _cr(_db_session, employee_user, request_type=ChangeRequestType.UPDATE, time_entry_id=e.id)
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.uncredited_minutes == 150
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_clamp_blocks.py tests/test_net_hours_uncredited.py tests/test_write_paths_uncredited.py -q -p no:cacheprovider`
Expected: FAIL — u. a. `test_k_table_net_hours[K1]` (`7.50 != 10.0`), `TypeError` fehlt in `test_net_hours_helper_requires_uncredited`, `uncredited_minutes == 0` statt 150.

- [ ] **Step 3: `net_hours` erweitern (`models/time_entry.py`)**

```python
    @hybrid_property
    def net_hours(self) -> Decimal:
        """
        Calculate net hours worked (end - start - break - uncredited).
        Returns hours as Decimal with 2 decimal places.

        Spec 2026-10-08 (E13): ``uncredited_minutes`` = Zeit zwischen zwei
        Arbeitsblöcken, die nicht angerechnet wird. ``or 0`` deckt transiente
        Einträge vor dem flush ab (der Spalten-Default greift erst dort).
        """
        if not self.start_time or not self.end_time:
            return Decimal('0.00')

        start_seconds = self.start_time.hour * 3600 + self.start_time.minute * 60 + self.start_time.second
        end_seconds = self.end_time.hour * 3600 + self.end_time.minute * 60 + self.end_time.second
        duration_hours = (end_seconds - start_seconds) / 3600.0
        break_hours = self.break_minutes / 60.0
        uncredited_hours = (self.uncredited_minutes or 0) / 60.0

        net = duration_hours - break_hours - uncredited_hours

        return Decimal(str(max(round(net, 2), 0)))

    @net_hours.expression
    def net_hours(cls):
        """
        F-032: SQL-level expression for net_hours (``func.sum`` in Postgres).
        Rundet bewusst NICHT je Zeile — sonst änderten sich bestehende
        SQL-Summen (Spec 6.1, Byte-Identität E22). Parität zum Python-Pfad bis
        auf n × 0,005 h (Test ``test_net_hours_parity_pg.py``).
        """
        duration = (
            func.extract("epoch", cls.end_time - cls.start_time) / 3600.0
            - cls.break_minutes / 60.0
            - func.coalesce(cls.uncredited_minutes, 0) / 60.0
        )
        return case(
            (cls.end_time.is_(None), 0),
            (duration < 0, 0),
            else_=duration,
        )
```

- [ ] **Step 4: Netto-Helfer in `routers/time_entries.py` (Zeilen 46–119)**

```python
def _net_hours(st: time, et: time, brk: int, uncredited: int) -> float:
    """Calculate net working hours from start/end time, break and the
    uncredited minutes between work blocks (Spec 2026-10-08, E13).

    Invariant: et > st. This is NOT over-midnight aware on purpose — see the
    history of this helper; the max(0, …) floor stays the last-resort guard.
    ``uncredited`` ist Pflicht: ohne ihn ergäbe „gestempelt 08:00–18:30,
    gekappt auf 18:15" 10,25 h und HTTP 422, obwohl nur 7,75 h angerechnet sind.
    """
    mins = (et.hour * 60 + et.minute) - (st.hour * 60 + st.minute)
    return max(0.0, (mins - brk - uncredited) / 60.0)


def _calculate_daily_net_hours(
    db: Session,
    user_id: UUIDType,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    *,
    uncredited_minutes: int,
    exclude_entry_id=None,
    tenant_id=None,
) -> float:
    """Sum up all net hours for a user on a given date, including the
    new/updated entry. Bestehende Einträge tragen ihr gespeichertes
    ``uncredited_minutes`` bei; ``uncredited_minutes`` des neuen Eintrags ist
    Pflicht (Spec 7.1)."""
    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.date == entry_date,
        TimeEntry.end_time.isnot(None),
    )
    if tenant_id is not None:
        query = query.filter(TimeEntry.tenant_id == tenant_id)
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    existing = query.all()

    total = sum(
        _net_hours(e.start_time, e.end_time, e.break_minutes, e.uncredited_minutes or 0)
        for e in existing
    )
    total += _net_hours(start_time, end_time, break_minutes, uncredited_minutes)
    return total


def _calculate_weekly_net_hours(
    db: Session,
    user_id: UUIDType,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    *,
    uncredited_minutes: int,
    exclude_entry_id=None,
    tenant_id=None,
) -> float:
    """Sum all net hours for the ISO calendar week containing entry_date,
    including the new/updated entry (uncredited wie im Tageshelfer)."""
    from datetime import timedelta
    monday = entry_date - timedelta(days=entry_date.weekday())
    sunday = monday + timedelta(days=6)

    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.date >= monday,
        TimeEntry.date <= sunday,
        TimeEntry.end_time.isnot(None),
    )
    if tenant_id is not None:
        query = query.filter(TimeEntry.tenant_id == tenant_id)
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    existing = query.all()

    total = sum(
        _net_hours(e.start_time, e.end_time, e.break_minutes, e.uncredited_minutes or 0)
        for e in existing
    )
    total += _net_hours(start_time, end_time, break_minutes, uncredited_minutes)
    return total
```

- [ ] **Step 5: Alle 17 Aufrufer ergänzen**

Jeder Aufruf bekommt genau eine zusätzliche Schlüsselwort-Zeile `uncredited_minutes=<Wert>` direkt nach `break_minutes=…`. Beispiel `clock_out` (Tag):

```python
    daily_hours = _calculate_daily_net_hours(
        db=db,
        user_id=current_user.id,
        entry_date=open_entry.date,
        start_time=open_entry.start_time,
        end_time=eff_end,
        break_minutes=body.break_minutes,
        uncredited_minutes=_r.uncredited_minutes,
        exclude_entry_id=open_entry.id,
        tenant_id=current_user.tenant_id,
    )
```

| Datei:Zeile (vor der Änderung) | Funktion | Wert |
|---|---|---|
| `time_entries.py:408`, `:505` | `clock_out` Tag/Woche | `_r.uncredited_minutes` |
| `time_entries.py:685`, `:785` | `create_time_entry` Tag/Woche | `_r.uncredited_minutes` |
| `time_entries.py:1014`, `:1149`, `:1161` | `update_time_entry` §3 / Tag / Woche | `entry.uncredited_minutes` (nach Step 6 bereits geschrieben) |
| `admin_time_entries.py:139`, `:156` | `admin_create_time_entry` | `_r.uncredited_minutes` |
| `admin_time_entries.py:359`, `:376` | `admin_update_time_entry` | `_r.uncredited_minutes` (die geprüften `eff_*` stammen aus demselben `_r`) |
| `admin_change_requests.py:391` | Vorprüfung | `_r_pre.uncredited_minutes` |
| `admin_change_requests.py:1022`, `:1044` | Nachprüfung | `_rw.uncredited_minutes` (Task 9 ersetzt den Block) |
| `change_requests.py:218`, `:297`, `:321` | MA-Antrag | `0` — der Antrag prüft bis Task 9 roh (E40 folgt dort) |

Kontrolle: `grep -n "_calculate_daily_net_hours(\|_calculate_weekly_net_hours(" -A10 backend/app/routers/*.py | grep -c "uncredited_minutes="` ergibt 17.

Nicht anfassen, aber wissen: `absences.create_absence` (F1-Klemmung, `kept_net_by_date`) und alle Ist-Summen im `calculation_service` lesen `TimeEntry.net_hours` — sie folgen dem Hybrid automatisch (Spec Anhang B, Gruppe 3: „folgen dem Hybrid, nicht umbauen“).

- [ ] **Step 6: Schreibstellen speichern `uncredited_minutes`**

`clock_in` — im Konstruktor `TimeEntry(...)` nach `raw_start_time=raw_start,`:

```python
        uncredited_minutes=_r.uncredited_minutes,
```

`clock_out` — nach `open_entry.raw_end_time = raw_end`:

```python
    open_entry.uncredited_minutes = _r.uncredited_minutes
```

`create_time_entry` — im Konstruktor nach `raw_end_time=raw_end,`:

```python
        uncredited_minutes=_r.uncredited_minutes,
```

`update_time_entry` — nach den beiden bestehenden Gates `if "start_time" in update_data:` / `if "end_time" in update_data:`:

```python
    if "start_time" in update_data or "end_time" in update_data:
        # Spec E11: die Lückenminuten folgen dem geschriebenen Zeitpaar.
        entry.uncredited_minutes = _r.uncredited_minutes
```

`admin_create_time_entry` — im Konstruktor nach `raw_end_time=raw_end,`:

```python
        uncredited_minutes=_r.uncredited_minutes,
```

`admin_update_time_entry` — nach den `raw_*`-Zuweisungen:

```python
    if entry_data.start_time is not None or entry_data.end_time is not None or _times_affected:
        entry.uncredited_minutes = _r.uncredited_minutes
```

`review_change_request`, CREATE-Zweig — im Konstruktor nach `raw_end_time=raw_end,`:

```python
                uncredited_minutes=_r.uncredited_minutes,
```

UPDATE-Zweig — nach `entry.raw_end_time = raw_end`:

```python
            entry.uncredited_minutes = _r.uncredited_minutes
```

- [ ] **Step 7: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (keine neuen Fehlschläge gegenüber `master`; die neuen Tests grün)

- [ ] **Step 8: Commit**

```bash
git add backend/app backend/tests
git commit -F - <<'EOF'
feat(bloecke): nicht angerechnete Minuten in net_hours, Netto-Helfern und allen Schreibstellen

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: §4 ArbZG mit Lückensegmenten (`validate_daily_break`)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499, gemergt in `3d46c2f`: `validate_daily_break` hat dort einen optionalen `tenant_id`-Filter und unveränderte Rechenregel; neu sind `BREAK_EXCEPTION_ALLOWED`, `BREAK_EXCEPTION_DISABLED_HINT`, `is_break_exception_allowed`, `break_waiver_rejection` — Step 3 übernimmt sie wörtlich, vier Router importieren sie. `tests/test_issue_499_break_chain.py:304` ruft `validate_daily_break` direkt auf und wird in Step 1 mit umgestellt.)

**Files:**
- Modify (komplett ersetzen): `backend/app/services/break_validation_service.py`
- Modify: Aufrufer `time_entries.py` 462, 707, 773, 1036, 1132; `admin_time_entries.py` 123, 344; `admin_change_requests.py` 410; `change_requests.py` 201 (Zeilen bei `b635679`; bei `3d46c2f`: `time_entries.py` 492, 771, 843, 1107, 1209; `admin_time_entries.py` 123, 349; `admin_change_requests.py` 427; `change_requests.py` 208 — maßgeblich sind die Funktionsnamen in Step 4)
- Test: `backend/tests/test_break_validation.py` und `backend/tests/test_issue_499_break_chain.py` (Aufrufe umstellen), `backend/tests/test_break_gaps.py` (neu)

**Interfaces:**
- Consumes: `work_window_service.gap_segments`, `grace_for_entry` (Task 3); `TimeEntry.uncredited_minutes`, `credit_override` (Task 2)
- Produces (in `app.services.break_validation_service`):
  - `class BreakBlock(NamedTuple): start: int; end: int; break_minutes: int; deduct_minutes: int; pause_segments: tuple`
  - `break_block_for_new(start_time: time, end_time: time, break_minutes: int, uncredited_segments: Sequence[int]) -> BreakBlock`
  - `break_block_for_entry(db: Session, user, entry, *, wh_changes=None, soll_free_dates=None) -> BreakBlock` — Segmente aus gespeicherten wirksamen Zeiten mit `grace_for_entry`; Σ ≠ gespeichertes `uncredited_minutes` → gespeicherter Wert als Abzug, keine Pausenabschnitte (8.2)
  - `daily_break_figures(blocks: Sequence[BreakBlock]) -> tuple[int, int]` = `(net_work_minutes, effective_break_minutes)`
  - `validate_daily_break(db: Session, user, entry_date: date, start_time: time, end_time: time, break_minutes: int, *, uncredited_segments: Sequence[int], tenant_id, exclude_entry_id=None) -> Optional[str]` (Parameter `user` statt `user_id`; `tenant_id` Pflicht, P10/7.3)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_break_gaps.py`:

```python
"""Spec 8.2: §4 mit Lückensegmenten; 7.3: Mandantenfilter."""
import uuid
from datetime import time

from app.models import TimeEntry
from app.models.tenant import Tenant
from app.services.break_validation_service import (
    BreakBlock, break_block_for_new, daily_break_figures, validate_daily_break,
)
from app.services import work_window_service as wws
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week


def _validate(db, user, start, end, brk=0, segs=(), **kw):
    return validate_daily_break(db, user, MON, start, end, brk, uncredited_segments=list(segs),
                                tenant_id=DEFAULT_TENANT_ID, **kw)


def test_gap_segment_counts_as_break_k1(db, test_user):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    segs = wws.gap_segments(db, test_user, MON, time(8), time(18), 15, credit_override=False)
    assert segs == [150]
    assert _validate(db, test_user, time(8), time(18), 0, segs) is None


def test_segment_below_15_is_deducted_but_no_break(db, test_user):
    test_user.work_blocks = block_week(mon=[("08:00", "12:00"), ("12:40", "17:00")])  # Lücke 12:15–12:25
    db.commit()
    segs = wws.gap_segments(db, test_user, MON, time(8), time(17), 15, credit_override=False)
    assert segs == [10]
    error = _validate(db, test_user, time(8), time(17), 0, segs)
    assert error is not None and "30 Minuten" in error


def test_existing_entry_segments_use_its_own_grace(db, test_user):
    """8.2/E80: Segmente bestehender Einträge mit deren GESPEICHERTEM Puffer —
    mit dem aktuellen Puffer 0 wäre die Lücke 180 ≠ 150 und zählte nicht."""
    from app.models.system_setting import SystemSetting
    db.add(SystemSetting(key="work_window_grace_minutes", value="0", tenant_id=DEFAULT_TENANT_ID))
    test_user.work_blocks = K_BLOCKS
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                     start_time=time(8), end_time=time(18), break_minutes=0,
                     uncredited_minutes=150, clamp_grace_minutes=15))
    db.commit()
    # direkt anschließend: kein Abstand zwischen den Einträgen, Pause nur aus der Lücke
    assert _validate(db, test_user, time(18, 0), time(18, 30), 0, ()) is None


def test_stored_uncredited_differs_from_segments_counts_strictly(db, test_user):
    """8.2: gespeichertes uncredited ≠ Σ Segmente → Abzug, aber kein Pausenabschnitt."""
    test_user.work_blocks = K_BLOCKS
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                     start_time=time(8), end_time=time(18), break_minutes=0,
                     uncredited_minutes=100, clamp_grace_minutes=15))
    db.commit()
    error = _validate(db, test_user, time(18, 0), time(18, 30), 0, ())
    assert error is not None and "30 Minuten" in error  # 530 Min Arbeit, keine Pause gezählt


def test_other_tenant_rows_are_ignored(db, test_user):
    """Fremde Zeile 08:00–14:00 + neuer Eintrag 14:00–15:00 ergäbe 7 h ohne
    Pause — ignoriert bleibt 1 h."""
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    db.add(other)
    db.add(TimeEntry(tenant_id=other.id, user_id=test_user.id, date=MON,
                     start_time=time(8), end_time=time(14), break_minutes=0))
    db.commit()
    assert _validate(db, test_user, time(14), time(15), 0, ()) is None


def test_daily_break_figures_without_blocks_is_byte_identical():
    blocks = [BreakBlock(480, 720, 0, 0, ()), break_block_for_new(time(12, 30), time(17), 15, [])]
    assert daily_break_figures(blocks) == ((240 + 270) - 15, 15 + 30)
```

`backend/tests/test_break_validation.py` — jeden Aufruf `validate_daily_break(db, test_user.id, …, break_minutes=X[, exclude_entry_id=…])` umschreiben zu `validate_daily_break(db, test_user, …, break_minutes=X, uncredited_segments=[], tenant_id=DEFAULT_TENANT_ID[, exclude_entry_id=…])`; Import `from tests.conftest import DEFAULT_TENANT_ID` ergänzen. Beispiel:

```python
    result = validate_daily_break(db, test_user, date(2026, 3, 10), time(8, 0), time(13, 59),
                                  break_minutes=0, uncredited_segments=[], tenant_id=DEFAULT_TENANT_ID)
```

Die in dieser Datei angelegten `TimeEntry`-Zeilen tragen `tenant_id=DEFAULT_TENANT_ID` (prüfen: `grep -n "TimeEntry(" backend/tests/test_break_validation.py`; fehlt es, ergänzen — sonst filtert der neue Mandantenfilter sie weg).

`backend/tests/test_issue_499_break_chain.py` (#499, `test_fremder_mandant_zaehlt_nicht`) — der direkte Aufruf

```python
        result = validate_daily_break(
            db, employee.id, d, time(14, 0), time(15, 0), 0, tenant_id=DEFAULT_TENANT_ID,
        )
```

wird zu

```python
        result = validate_daily_break(
            db, employee, d, time(14, 0), time(15, 0), 0,
            uncredited_segments=[], tenant_id=DEFAULT_TENANT_ID,
        )
```

(Kontrolle: `grep -rn "validate_daily_break(" backend/tests | grep -v "uncredited_segments"` listet nur noch mehrzeilige Aufrufe, deren Folgezeile `uncredited_segments=` trägt.)

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_break_gaps.py tests/test_break_validation.py tests/test_issue_499_break_chain.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'BreakBlock'` bzw. `TypeError: validate_daily_break() got an unexpected keyword argument 'uncredited_segments'`

- [ ] **Step 3: `break_validation_service.py` ersetzen**

```python
"""§4 ArbZG — Pausenprüfung über den Tag (Spec 2026-10-08, Abschnitt 8.2).

Basis ist die ANGERECHNETE Zeit: nicht angerechnete Lückenminuten sind keine
Arbeitszeit (Abzug von der Bruttozeit); ein Lückensegment ≥ 15 Min zählt als
Pausenabschnitt (geplante Ruhepause, E43). ``daily_break_figures`` ist die eine
Rechenregel — ``xls_import_service._check_arbzg`` nutzt sie mit.
"""
from datetime import date, time
from typing import NamedTuple, Optional, Sequence

from sqlalchemy.orm import Session

from app.models import TimeEntry
from app.services import settings_service


# #499: Mandanten-Schalter für die Ausnahme „Pflicht-Pause war nicht möglich"
# (#144). Default AN = bisheriges Verhalten. AUS → keine Ausnahme mehr, an
# keinem Schreibpfad: der §4-Verstoß bleibt eine harte Sperre.
BREAK_EXCEPTION_ALLOWED = "break_exception_allowed"

BREAK_EXCEPTION_DISABLED_HINT = (
    "Die Ausnahme „Pflicht-Pause war nicht möglich“ ist in dieser Praxis "
    "abgeschaltet – bitte die Pause erfassen."
)


def is_break_exception_allowed(db: Session, tenant_id) -> bool:
    """#499: darf ein §4-Verstoß per dokumentierter Begründung erfasst werden?"""
    return settings_service.get_bool_setting(
        db, BREAK_EXCEPTION_ALLOWED, tenant_id=tenant_id, default=True,
    )


def break_waiver_rejection(
    db: Session, tenant_id, break_error: str, waiver_reason: Optional[str],
) -> Optional[str]:
    """#499: entscheidet einheitlich für ALLE Schreibpfade, ob ein §4-Verstoß
    (``break_error``) per Ausnahme durchgelassen wird.

    Liefert ``None``, wenn die Ausnahme greift (Begründung vorhanden UND der
    Mandant erlaubt Ausnahmen) — sonst den Text für die 400-Antwort. Ist die
    Ausnahme abgeschaltet, nennt der Text das ausdrücklich, damit die
    Oberfläche nicht erneut nach einer Begründung fragt.
    """
    if not is_break_exception_allowed(db, tenant_id):
        return f"{break_error} {BREAK_EXCEPTION_DISABLED_HINT}"
    if not (waiver_reason or "").strip():
        return break_error
    return None


def _time_to_minutes(t: time) -> int:
    """Convert a time object to total minutes since midnight."""
    return t.hour * 60 + t.minute


class BreakBlock(NamedTuple):
    start: int             # wirksamer Beginn, Minuten seit Mitternacht
    end: int               # wirksames Ende
    break_minutes: int     # erfasste Pause
    deduct_minutes: int    # nicht angerechnete Minuten (Abzug von der Bruttozeit)
    pause_segments: tuple  # Lückensegmente ≥ 15 Min, die als Pausenabschnitt zählen


def break_block_for_new(start_time: time, end_time: time, break_minutes: int,
                        uncredited_segments: Sequence[int]) -> BreakBlock:
    segs = [int(s) for s in uncredited_segments]
    return BreakBlock(
        _time_to_minutes(start_time), _time_to_minutes(end_time), int(break_minutes or 0),
        sum(segs), tuple(s for s in segs if s >= 15),
    )


def break_block_for_entry(db: Session, user, entry, *, wh_changes=None,
                          soll_free_dates=None) -> BreakBlock:
    """Bestehender Eintrag: Segmente aus seinen GESPEICHERTEN wirksamen Zeiten,
    den Blöcken des Datums und SEINEM Puffer (E80). Weicht Σ Segmente vom
    gespeicherten ``uncredited_minutes`` ab (Bestand ohne gespeicherten Puffer
    nach einer Puffer-Änderung), zählt der gespeicherte Wert als Abzug und NICHT
    als Pausenabschnitt (strenge Richtung, 8.2)."""
    from app.services import work_window_service

    stored = int(entry.uncredited_minutes or 0)
    segs = [] if entry.credit_override else work_window_service.gap_segments(
        db, user, entry.date, entry.start_time, entry.end_time,
        work_window_service.grace_for_entry(db, entry), credit_override=False,
        wh_changes=wh_changes, soll_free_dates=soll_free_dates,
    )
    start, end = _time_to_minutes(entry.start_time), _time_to_minutes(entry.end_time)
    brk = int(entry.break_minutes or 0)
    if sum(segs) != stored:
        return BreakBlock(start, end, brk, stored, ())
    return BreakBlock(start, end, brk, stored, tuple(s for s in segs if s >= 15))


def daily_break_figures(blocks: Sequence[BreakBlock]) -> tuple:
    """(Netto-Arbeitsminuten, wirksame Pause) über alle Blöcke des Tages.

    Netto = Σ (Ende − Beginn − Abzug) − erfasste Pausen ≥ 15 (§4 Satz 2).
    Wirksame Pause = erfasste Pausen ≥ 15 + Abstände zwischen Einträgen ≥ 15 +
    Lückensegmente ≥ 15."""
    ordered = sorted(blocks, key=lambda b: b.start)
    gross = sum(b.end - b.start - b.deduct_minutes for b in ordered)
    declared = sum(b.break_minutes for b in ordered if b.break_minutes >= 15)
    gaps = 0
    for prev, cur in zip(ordered, ordered[1:]):
        gap = cur.start - prev.end
        if gap >= 15:
            gaps += gap
    segments = sum(sum(b.pause_segments) for b in ordered)
    return gross - declared, declared + gaps + segments


def validate_daily_break(
    db: Session,
    user,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    *,
    uncredited_segments: Sequence[int],
    tenant_id,
    exclude_entry_id=None,
) -> Optional[str]:
    """§4 ArbZG: > 6 h → 30 Min, > 9 h → 45 Min, Abschnitte ≥ 15 Min.

    ``uncredited_segments`` = ``work_window_service.gap_segments`` des neuen
    bzw. geänderten Eintrags (Pflicht, Spec 8.2). ``tenant_id`` Pflicht (7.3).
    Returns an error message string if invalid, None if valid."""
    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == tenant_id,  # F-026 (Spec 7.3)
        TimeEntry.date == entry_date,
    )
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    blocks = [
        break_block_for_entry(db, user, e)
        for e in query.order_by(TimeEntry.start_time).all()
        if e.end_time is not None
    ]
    blocks.append(break_block_for_new(start_time, end_time, break_minutes, uncredited_segments))

    net_work_minutes, total_effective_break = daily_break_figures(blocks)

    if net_work_minutes > 540 and total_effective_break < 45:
        return (
            f"Bei mehr als 9 Stunden Arbeitszeit ist eine Pause von mindestens 45 Minuten erforderlich (ArbZG §4). "
            f"Aktuelle Netto-Arbeitszeit: {net_work_minutes // 60}h {net_work_minutes % 60}min, "
            f"Gesamtpause: {total_effective_break} Minuten."
        )
    if net_work_minutes > 360 and total_effective_break < 30:
        return (
            f"Bei mehr als 6 Stunden Arbeitszeit ist eine Pause von mindestens 30 Minuten erforderlich (ArbZG §4). "
            f"Aktuelle Netto-Arbeitszeit: {net_work_minutes // 60}h {net_work_minutes % 60}min, "
            f"Gesamtpause: {total_effective_break} Minuten."
        )
    if break_minutes is not None and 0 < break_minutes < 15:
        return (
            f"Pausenabschnitte müssen mindestens 15 Minuten betragen (§4 Satz 2 ArbZG). "
            f"Eingegebene Pause: {break_minutes} Minuten."
        )
    return None
```

- [ ] **Step 4: Die 9 Aufrufer umstellen**

Je Pfad direkt nach dem `clamp`-Aufruf die Segmente aus **denselben** Eingaben bestimmen und an `validate_daily_break` übergeben:

`time_entries.clock_out` (nach `_r = …clamp(...)`):

```python
    _segs = work_window_service.gap_segments(
        db, current_user, open_entry.date, open_entry.start_time, new_end_time, grace,
        credit_override=open_entry.credit_override,
    )
```

```python
        break_error = validate_daily_break(
            db=db,
            user=current_user,
            entry_date=open_entry.date,
            start_time=open_entry.start_time,
            end_time=eff_end,
            break_minutes=body.break_minutes,
            uncredited_segments=_segs,
            exclude_entry_id=open_entry.id,
            tenant_id=current_user.tenant_id,
        )
```

`create_time_entry` (707 und 773): `_segs = work_window_service.gap_segments(db, current_user, entry_data.date, entry_data.start_time, entry_data.end_time, _grace, credit_override=False)`; Aufrufe mit `user=current_user, …, uncredited_segments=_segs, tenant_id=current_user.tenant_id`.

`update_time_entry` (1036 und 1132): `_segs = work_window_service.gap_segments(db, _entry_owner, entry.date, _clamp_start, _clamp_end, _grace, credit_override=entry.credit_override)`; Aufrufe mit `user=_entry_owner, …, uncredited_segments=_segs, tenant_id=entry.tenant_id`.

`admin_create_time_entry` (123): `_segs = work_window_service.gap_segments(db, user, entry_data.date, entry_data.start_time, entry_data.end_time, _grace, credit_override=False)`; Aufruf `validate_daily_break(db=db, user=user, entry_date=entry_data.date, start_time=eff_start, end_time=eff_end, break_minutes=entry_data.break_minutes, uncredited_segments=_segs, tenant_id=current_user.tenant_id)`.

`admin_update_time_entry` (344): direkt nach dem Laden von `affected_user`

```python
    if affected_user is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
```

dann `_segs = work_window_service.gap_segments(db, affected_user, update_date, update_start_time, update_end_time, _grace, credit_override=entry.credit_override)` und `validate_daily_break(db=db, user=affected_user, …, uncredited_segments=_segs, exclude_entry_id=entry.id, tenant_id=current_user.tenant_id)`; die Bedingung `if not affected_user or not affected_user.exempt_from_arbzg:` wird zu `if not affected_user.exempt_from_arbzg:`.

`admin_change_requests` Vorprüfung (410): `_segs_pre = work_window_service.gap_segments(db, cr_user, cr.proposed_date, _in_start, _in_end, _grace, credit_override=bool(entry is not None and entry.credit_override))`; `validate_daily_break(db=db, user=cr_user, …, uncredited_segments=_segs_pre, exclude_entry_id=exclude_id, tenant_id=cr.tenant_id)`.

`change_requests.create_change_request` (201): bis Task 9 roh — `validate_daily_break(db=db, user=current_user, entry_date=data.proposed_date, start_time=data.proposed_start_time, end_time=data.proposed_end_time, break_minutes=data.proposed_break_minutes or 0, uncredited_segments=[], exclude_entry_id=entry.id if entry else None, tenant_id=current_user.tenant_id)`.

Seit #499 (`3d46c2f`) steht die §4-Prüfung in `clock_out` **vor** dem Schreiben und blockiert (400 über `break_waiver_rejection`); die übrigen Aufrufer reichen bereits `tenant_id=` durch. An der Umstellung ändert das nichts: `_segs` entsteht direkt nach `clamp`, also vor der vorgezogenen Prüfung; `break_waiver_rejection` und die Begründungslogik bleiben unangetastet.

Kontrolle: `grep -n "validate_daily_break(" -A12 backend/app/routers/*.py | grep -c "uncredited_segments="` ergibt 9; `grep -rn "user_id=" … validate_daily_break` liefert nichts mehr.

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (keine neuen Fehlschläge)

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -F - <<'EOF'
feat(bloecke): §4 ArbZG auf angerechneter Zeit mit Lückensegmenten, Mandantenfilter in validate_daily_break

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 6: Puffer-Herkunft und `clamp_grace_minutes` (E79/E80)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499: Schreibpfade).

**Files:**
- Modify: `backend/app/routers/time_entries.py` (`clock_in`, `clock_out`, `create_time_entry`, `update_time_entry`)
- Modify: `backend/app/routers/admin_time_entries.py` (`admin_create_time_entry`, `admin_update_time_entry`)
- Modify: `backend/app/routers/admin_change_requests.py` (Vorprüfung, CREATE, UPDATE)
- Test: `backend/tests/test_clamp_grace.py` (neu)

**Interfaces:**
- Consumes: `work_window_service.grace_for_entry`, `get_grace_minutes`, `ClampResult.grace_minutes` (Task 3)
- Produces: Schreibregel „jede schreibende Stelle setzt `clamp_grace_minutes = r.grace_minutes`, wenn nicht `None`"; Puffer je Pfad: Neuanlage (`clock_in`, `create_time_entry`, Admin-Anlage, CR-CREATE) → `get_grace_minutes`; Einzel-Neukappung (`clock_out`, MA-/Admin-Bearbeitung, CR-UPDATE inkl. Vorprüfung) → `grace_for_entry(db, entry)`. Auto-Close folgt in Task 8, XLS in Task 10.

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_clamp_grace.py`:

```python
"""Spec E79/E80 (19.1 Nr. 8): jeder gekappte Eintrag merkt sich seinen Puffer;
Einzel-Neukappungen kappen mit dem gespeicherten Wert weiter."""
import datetime as dt
from datetime import date, time

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

import app.routers.time_entries as te

NEXT_MON = date(2026, 6, 8)
SATURDAY = date(2026, 6, 6)


def _grace(db, minutes):
    row = db.query(SystemSetting).filter(SystemSetting.key == "work_window_grace_minutes").first()
    if row is None:
        db.add(SystemSetting(key="work_window_grace_minutes", value=str(minutes), tenant_id=DEFAULT_TENANT_ID))
    else:
        row.value = str(minutes)
    db.commit()


def _window(db, user):
    user.work_blocks = legacy_week(mon=("08:00", "17:00"))
    db.commit()


def _admin_create(client, user, start="07:00", end="16:00", brk=30):
    resp = client.post(f"/api/admin/users/{user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": start, "end_time": end, "break_minutes": brk})
    assert resp.status_code == 201, resp.text
    return resp


def _only(db):
    entry = db.query(TimeEntry).one()
    db.refresh(entry)
    return entry


def test_new_entries_store_current_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7, 0), 15)


def test_employee_create_and_clock_in_store_current_grace(_db_session, employee_user, employee_client, monkeypatch):
    _window(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 7, 0))
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    assert _only(_db_session).clamp_grace_minutes == 15


def test_admin_full_form_resave_keeps_stored_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 0)
    e = _only(_db_session)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={
        "start_time": "07:45", "end_time": "16:00", "break_minutes": 30, "note": "Korrektur"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7, 0), 15)


def test_employee_edit_keeps_stored_grace(_db_session, employee_user, employee_client, monkeypatch):
    _window(_db_session, employee_user)
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(7, 45), raw_start_time=time(7, 0), end_time=time(16, 0),
                              break_minutes=30, clamp_grace_minutes=15))
    _db_session.commit()
    _grace(_db_session, 0)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    e = _only(_db_session)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"start_time": "07:00", "end_time": "16:00"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.clamp_grace_minutes) == (time(7, 45), 15)


def test_admin_date_change_keeps_stored_grace_and_names_it(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 0)
    e = _only(_db_session)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"date": NEXT_MON.isoformat()})
    assert resp.status_code == 200, resp.text
    assert any("Puffer 15 Minuten" in w for w in resp.json()["warnings"])
    e = _only(_db_session)
    assert (e.date, e.start_time, e.clamp_grace_minutes) == (NEXT_MON, time(7, 45), 15)


def test_cr_update_keeps_stored_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 0)
    e = _only(_db_session)
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=e.id, proposed_date=MON, proposed_start_time=time(7, 45),
                       proposed_end_time=time(16, 0), proposed_break_minutes=30, reason="Notiz")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7, 0), 15)


def test_clock_out_uses_grace_of_open_entry(_db_session, employee_user, employee_client, monkeypatch):
    _window(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 7, 0))
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    _grace(_db_session, 0)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 30))
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 30})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.end_time, e.raw_end_time, e.clamp_grace_minutes) == (time(17, 15), time(17, 30), 15)


def test_null_grace_uses_current_and_stores_it(_db_session, employee_user, admin_client):
    """Restfall (Spec 19 Nr. 2a): Bestand ohne gespeicherten Puffer kappt bei der
    Bearbeitung mit dem aktuellen Puffer — und merkt ihn sich danach."""
    _window(_db_session, employee_user)
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(7, 45), raw_start_time=time(7, 0), end_time=time(16, 0),
                              break_minutes=30, clamp_grace_minutes=None))
    _db_session.commit()
    _grace(_db_session, 10)
    e = _only(_db_session)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"start_time": "07:45", "end_time": "16:00"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.clamp_grace_minutes) == (time(7, 50), 10)


def test_day_without_blocks_keeps_stored_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 0)
    e = _only(_db_session)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"date": SATURDAY.isoformat()}).status_code == 200
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 0), None, 15)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"date": MON.isoformat()}).status_code == 200
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7, 0), 15)


def test_credit_override_sets_no_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(7, 0), end_time=time(16, 0), break_minutes=30,
                              credit_override=True))
    _db_session.commit()
    e = _only(_db_session)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"start_time": "06:30"}).status_code == 200
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes, e.credit_override) == (time(6, 30), None, None, True)


def test_schemas_never_accept_server_side_fields(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "07:00", "end_time": "16:00", "break_minutes": 30,
        "clamp_grace_minutes": 99, "uncredited_minutes": 999, "credit_override": True, "auto_closed": True})
    assert resp.status_code == 201, resp.text
    e = _only(_db_session)
    assert (e.clamp_grace_minutes, e.uncredited_minutes, e.credit_override, e.auto_closed) == (15, 0, False, False)


# Review Focus 2: Formular-Re-Save (Notiz/Pause) an einem lückengekappten Eintrag.
def test_admin_full_form_resave_keeps_gap_state(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    _admin_create(admin_client, employee_user, "07:00", "19:00", 0)          # K7
    _grace(_db_session, 0)
    e = _only(_db_session)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={
        "start_time": "07:45", "end_time": "18:15", "break_minutes": 30, "note": "Korrektur"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time) == (
        time(7, 45), time(18, 15), time(7, 0), time(19, 0))
    assert (e.uncredited_minutes, e.clamp_grace_minutes, e.break_minutes) == (150, 15, 30)
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_clamp_grace.py -q -p no:cacheprovider`
Expected: FAIL — `clamp_grace_minutes` ist `None` statt 15; gekappte Zeiten nach Puffer-Senkung `08:00` statt `07:45`.

- [ ] **Step 3: Puffer-Herkunft und Schreibregel umsetzen**

`time_entries.clock_in` — im Konstruktor `TimeEntry(...)`:

```python
        clamp_grace_minutes=_r.grace_minutes,
```

`clock_out` — `grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)` ersetzen durch

```python
    # E80: Einzel-Neukappung des offenen Eintrags mit SEINEM Puffer aus clock_in.
    grace = work_window_service.grace_for_entry(db, open_entry)
```

und nach `open_entry.uncredited_minutes = _r.uncredited_minutes`:

```python
    if _r.grace_minutes is not None:
        open_entry.clamp_grace_minutes = _r.grace_minutes
```

`create_time_entry` — Konstruktor: `clamp_grace_minutes=_r.grace_minutes,`.

`update_time_entry` — `_grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)` ersetzen durch `_grace = work_window_service.grace_for_entry(db, entry)` und den Uncredited-Block aus Task 4 erweitern:

```python
    if "start_time" in update_data or "end_time" in update_data:
        # Spec E11/E79: Lückenminuten und angewandter Puffer folgen dem
        # geschriebenen Zeitpaar; ein None-Puffer (Tag ohne Blöcke) lässt den
        # gespeicherten Wert stehen.
        entry.uncredited_minutes = _r.uncredited_minutes
        if _r.grace_minutes is not None:
            entry.clamp_grace_minutes = _r.grace_minutes
```

`admin_create_time_entry` — Konstruktor: `clamp_grace_minutes=_r.grace_minutes,`.

`admin_update_time_entry` — `_grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)` ersetzen durch `_grace = work_window_service.grace_for_entry(db, entry)`; Block aus Task 4 erweitern:

```python
    if entry_data.start_time is not None or entry_data.end_time is not None or _times_affected:
        entry.uncredited_minutes = _r.uncredited_minutes
        if _r.grace_minutes is not None:
            entry.clamp_grace_minutes = _r.grace_minutes
```

`admin_change_requests` Vorprüfung — die Zeile `_grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)` wird zu:

```python
                _grace = (
                    work_window_service.grace_for_entry(db, entry)
                    if cr.request_type == ChangeRequestType.UPDATE and entry is not None
                    else work_window_service.get_grace_minutes(db, current_user.tenant_id)
                )
```

CREATE-Zweig: Konstruktor `clamp_grace_minutes=_r.grace_minutes,`. UPDATE-Zweig: `_grace = work_window_service.grace_for_entry(db, entry)` und nach `entry.uncredited_minutes = _r.uncredited_minutes`:

```python
            if _r.grace_minutes is not None:
                entry.clamp_grace_minutes = _r.grace_minutes
```

- [ ] **Step 4: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (keine neuen Fehlschläge)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers backend/tests/test_clamp_grace.py
git commit -F - <<'EOF'
feat(bloecke): Puffer je Eintrag speichern, Einzel-Neukappungen mit gespeichertem Puffer (E79/E80)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 7: Ankersperren in allen Schreibpfaden (P5)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499: Schreibpfade; #494 hat `get_clock_status` umgebaut — Step 3 ist auf den Stand `3d46c2f` geschrieben; `test_concurrency.py` hat seit #491 API-2 drei neue Tests, der in Step 4 angepasste Test steht dort bei Zeile 1221, seine Startzeile `t_edit.start(); t_closure.start()` bei 1266).

**Files:**
- Modify: `backend/app/routers/time_entries.py` (`get_clock_status` Stale-Zweig, `clock_out`, `create_time_entry`, `update_time_entry`)
- Modify: `backend/app/routers/admin_time_entries.py` (Import, `admin_create_time_entry`, `admin_update_time_entry`)
- Test: `backend/tests/test_write_path_locks.py` (neu; Task 10 ergänzt den XLS-Fall)
- Modify: `backend/tests/test_concurrency.py` (`test_admin_time_entry_edit_does_not_deadlock_with_a_parallel_closure`: Docstring + deterministischer Start; läuft in Task 14 gegen Postgres)

**Interfaces:**
- Consumes: `admin_helpers.lock_user_row(db, tenant_id, user_id)` (unverändert)
- Produces: Reihenfolge-Invariante „Ankersperre auf die Eigentümer-Zeile vor jedem `get_grace_minutes`/`grace_for_entry`/`get_scheduled_blocks`/`clamp` und vor jeder `with_for_update`-Sperre auf `time_entries`"; Test-Fixture `calls` in `tests/test_write_path_locks.py` (Spy-Liste, von Task 10 mitbenutzt)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_write_path_locks.py`:

```python
"""Spec P5: jeder Schreibpfad für Zeiteinträge nimmt ZUERST die Ankersperre der
Eigentümer-Zeile — vor Puffer, Snapshot-Auflösung, clamp und Zeilensperren."""
import datetime as dt
from datetime import date, time

import pytest

import app.routers.admin_change_requests as acr
import app.routers.admin_time_entries as ate
import app.routers.time_entries as te
from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.routers import admin_helpers
from app.services import work_window_service as wws
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON


@pytest.fixture
def calls(monkeypatch):
    log = []
    real_lock = admin_helpers.lock_user_row

    def spy_lock(db, tenant_id, user_id):
        log.append(("lock", str(user_id)))
        return real_lock(db, tenant_id, user_id)

    for mod in (te, ate, acr, admin_helpers):
        monkeypatch.setattr(mod, "lock_user_row", spy_lock, raising=False)
    for name in ("clamp", "get_grace_minutes", "grace_for_entry", "get_scheduled_blocks"):
        real = getattr(wws, name)

        def make(real, name):
            def spy(*a, **kw):
                log.append((name,))
                return real(*a, **kw)
            return spy

        monkeypatch.setattr(wws, name, make(real, name))
    real_close = te._close_stale_entry

    def spy_close(*a, **kw):
        log.append(("close",))
        return real_close(*a, **kw)

    monkeypatch.setattr(te, "_close_stale_entry", spy_close)
    return log


def assert_lock_first(log, owner_id):
    locks = [i for i, c in enumerate(log) if c == ("lock", str(owner_id))]
    others = [i for i, c in enumerate(log) if c[0] != "lock"]
    assert locks, f"keine Ankersperre auf {owner_id}: {log}"
    assert not others or locks[0] < others[0], log


def _setup(db, user):
    user.work_blocks = K_BLOCKS
    db.commit()


def _entry(db, user, start, end, d=MON):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=0)
    db.add(e)
    db.commit()
    return e


def _clock(monkeypatch, d, hh):
    monkeypatch.setattr(te, "_today_local", lambda: d)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(d.year, d.month, d.day, hh, 0))


def test_clock_in(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    _clock(monkeypatch, MON, 8)
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    assert_lock_first(calls, employee_user.id)


def test_clock_out(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    _entry(_db_session, employee_user, time(8), None)
    _clock(monkeypatch, MON, 12)
    assert employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0}).status_code == 200
    assert_lock_first(calls, employee_user.id)


def test_clock_status_stale_branch(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    _entry(_db_session, employee_user, time(8), None)
    _clock(monkeypatch, date(2026, 6, 2), 8)
    assert employee_client.get("/api/time-entries/clock-status").status_code == 200
    assert ("close",) in calls
    assert_lock_first(calls, employee_user.id)


def test_create(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    _clock(monkeypatch, MON, 13)
    resp = employee_client.post("/api/time-entries/", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "12:00", "break_minutes": 0})
    assert resp.status_code == 201, resp.text
    assert_lock_first(calls, employee_user.id)


def test_update(_db_session, employee_user, employee_client, calls, monkeypatch):
    _setup(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8), time(11))
    _clock(monkeypatch, MON, 13)
    assert employee_client.put(f"/api/time-entries/{e.id}", json={"end_time": "12:00"}).status_code == 200
    assert_lock_first(calls, employee_user.id)


def test_admin_create(_db_session, employee_user, admin_client, calls):
    _setup(_db_session, employee_user)
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "12:00", "break_minutes": 0})
    assert resp.status_code == 201, resp.text
    assert_lock_first(calls, employee_user.id)


def test_admin_update(_db_session, employee_user, admin_client, calls):
    _setup(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8), time(11))
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "12:00"}).status_code == 200
    assert_lock_first(calls, employee_user.id)


def test_cr_review(_db_session, employee_user, admin_client, calls):
    _setup(_db_session, employee_user)
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
                       proposed_date=MON, proposed_start_time=time(8), proposed_end_time=time(12),
                       proposed_break_minutes=0, reason="Nachtrag")
    _db_session.add(cr)
    _db_session.commit()
    assert admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"}).status_code == 200
    assert_lock_first(calls, employee_user.id)
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_write_path_locks.py -q -p no:cacheprovider`
Expected: FAIL in `test_clock_out`, `test_clock_status_stale_branch`, `test_create`, `test_update`, `test_admin_create`, `test_admin_update` („keine Ankersperre"); `test_clock_in`, `test_cr_review` PASS (Sperre existiert schon).

- [ ] **Step 3: Ankersperren einbauen**

`admin_time_entries.py` — Import erweitern:

```python
from app.routers.admin_helpers import _create_audit_log, _enrich_audit_response, _enrich_audit_responses, lock_user_row
```

`time_entries.clock_out` — erste Anweisung im Funktionsrumpf:

```python
    # P5 (Spec 2.10): Ankersperre als ERSTE Datenbankaktion — vor Puffer,
    # Snapshot und clamp, vor der Zeilensperre auf den offenen Eintrag. Sonst
    # kappt ein Ausstempeln während einer laufenden Arbeitszeit-Änderung noch
    # gegen den alten Snapshot und entgeht deren Neuberechnung.
    lock_user_row(db, current_user.tenant_id, current_user.id)
```

`create_time_entry` — erste Anweisung (identischer Kommentar, `lock_user_row(db, current_user.tenant_id, current_user.id)`).

`update_time_entry` — das Laden des Eintrags ersetzen:

```python
    # P5: Ankersperre auf den EIGENTÜMER vor jeder Zeilensperre. Der Eigentümer
    # eines Eintrags ist unveränderlich — ein ungesperrter Lesezugriff genügt.
    _owner_id = db.query(TimeEntry.user_id).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
    ).scalar()
    if _owner_id is not None:
        lock_user_row(db, current_user.tenant_id, _owner_id)
    entry = db.query(TimeEntry).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
    ).with_for_update().first()
```

`admin_create_time_entry` — direkt nach `if not user: raise HTTPException(404, …)`:

```python
    # P5: Ankersperre auf die Zielperson vor Puffer, Snapshot und clamp.
    lock_user_row(db, current_user.tenant_id, user.id)
```

`admin_update_time_entry` — vor dem bestehenden `entry = (db.query(TimeEntry)…with_for_update()…first())`:

```python
    # P5: Ankersperre (Eigentümer) VOR der Zeilensperre F-028 — feste
    # Reihenfolge gegen Deadlocks (40P01 → 500).
    _owner_id = db.query(TimeEntry.user_id).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,
    ).scalar()
    if _owner_id is not None:
        lock_user_row(db, current_user.tenant_id, _owner_id)
```

`get_clock_status` — den Stale-Zweig (Stand `3d46c2f`, #494: `today = _today_local()` steht schon am Funktionsanfang, der Zweig setzt `open_entry = None` statt früh zurückzukehren)

```python
    # If the open entry is from a previous day, auto-close it
    if open_entry and open_entry.date != today:
        _close_stale_entry(db, open_entry, changed_by_id=current_user.id)
        db.commit()  # F-043: /clock-status now owns the commit
        open_entry = None
```

ersetzen durch:

```python
    # If the open entry is from a previous day, auto-close it.
    # P5: Ankersperre, danach den offenen Eintrag NEU lesen (ein paralleler
    # Schreiber kann ihn inzwischen geschlossen oder ersetzt haben).
    if open_entry is not None and open_entry.date != today:
        lock_user_row(db, current_user.tenant_id, current_user.id)
        open_entry = _get_open_entry(
            db, current_user.id, with_lock=True, tenant_id=current_user.tenant_id,
        )
        if open_entry is not None and open_entry.date != today:
            _close_stale_entry(db, open_entry, changed_by_id=current_user.id)
            db.commit()  # F-043: /clock-status owns the commit
            open_entry = None
```

Der Rest der Funktion bleibt: `closed_minutes`/`target_hours` (#494), die frühe Rückgabe ohne offenen Eintrag (mit `today_net_minutes`/`today_target_hours`), `elapsed` und die Rückgabe. Ein früher `return ClockStatusResponse(is_clocked_in=False)` im Stale-Zweig wäre ein Rückschritt hinter #494 — `tests/test_494_clock_status_today.py` hält das fest.

- [ ] **Step 4: Postgres-Wettlauftest an die neue Sperrreihenfolge anpassen**

`backend/tests/test_concurrency.py::test_admin_time_entry_edit_does_not_deadlock_with_a_parallel_closure` begründet im Docstring, `admin_time_entries` brauche keinen Anker — mit P5 nimmt `admin_update_time_entry` jetzt die Ankersperre der **Mitarbeiterin** (nicht der Admin-Zeile). Beide Vorgänge serialisieren damit auf derselben Zeile; startet die Betriebsferien-Buchung zuerst, löscht sie den Zeiteintrag, und die Korrektur endet sauber mit 404 statt mit „updated". Der Test bleibt ein Deadlock-Test, startet aber deterministisch:

Im Docstring den Absatz ab „Auch hier reicht ``FOR NO KEY UPDATE`` am Anker" bis zum Ende ersetzen durch:

```text
    Seit Spec 2026-10-08 (P5) nimmt ``admin_update_time_entry`` ZUERST die
    Ankersperre der Mitarbeiterin (``FOR NO KEY UPDATE``) und erst danach die
    Zeiteintrags-Zeile — dieselbe Reihenfolge wie die Betriebsferien. Damit gibt
    es keinen Zyklus mehr; die beiden Vorgänge serialisieren auf der
    Benutzerzeile. Die Korrektur startet hier zuerst (sonst löschte die
    Buchung den Eintrag, und die Korrektur endete regulär mit 404).
```

und die Startzeile

```python
    t_edit.start(); t_closure.start()
```

ersetzen durch

```python
    t_edit.start()
    time_module.sleep(0.5)  # P5: die Korrektur hält den Anker, bevor die Buchung ihn anfragt
    t_closure.start()
```

Der Lauf gegen Postgres folgt in Task 14 Step 3 (vor Migration 073 passt das Modell nicht zur Datenbank).

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (keine neuen Fehlschläge)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers backend/tests/test_write_path_locks.py backend/tests/test_concurrency.py
git commit -F - <<'EOF'
feat(bloecke): Ankersperre vor Puffer, Snapshot und clamp in allen Schreibpfaden (P5)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 8: Auto-Close über `clamp` und Kennzeichen `auto_closed` (E36/E42, P18)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499: Schreibpfade).

**Files:**
- Modify: `backend/app/routers/time_entries.py:165-205` (`_close_stale_entry`), `clock_out`, `update_time_entry`
- Modify: `backend/app/routers/admin_time_entries.py` (`admin_update_time_entry`)
- Modify: `backend/app/routers/admin_change_requests.py` (UPDATE-Zweig)
- Test: `backend/tests/test_auto_close_blocks.py` (neu)

**Interfaces:**
- Consumes: `clamp`, `grace_for_entry` (Task 3); Ankersperren der Aufrufer (Task 7)
- Produces:
  - `time_entries._close_stale_entry(db: Session, entry: TimeEntry, *, changed_by_id=None) -> None` — Ende über `clamp(…, time(23, 59), grace_for_entry(db, entry), credit_override=entry.credit_override)`, schreibt `end_time`, `raw_end_time`, `uncredited_minutes`, `clamp_grace_minutes` (wenn nicht None), `auto_closed = True`; Audit `source="auto_close"` unverändert; kein Commit (F-043). PR3 (P23) ruft sie mit der handelnden Admin als `changed_by_id` auf.
  - Regel „`auto_closed = False`, sobald eine Eingabe ein anderes Ende liefert als das gespeicherte wirksame Ende" (Ausstempeln, MA-/Admin-Bearbeitung, CR-UPDATE; XLS in Task 10)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_auto_close_blocks.py`:

```python
"""Spec K15, P18, E42: der Auto-Close kappt jetzt und kennzeichnet sich."""
import datetime as dt
from datetime import date, time
from decimal import Decimal

from app.models import TimeEntry, TimeEntryAuditLog
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

import app.routers.time_entries as te

TUE = date(2026, 6, 2)


def _open(db, user, start=time(8, 0), **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                  start_time=start, end_time=None, break_minutes=0, **kw)
    db.add(e)
    db.commit()
    return e


def _next_day_clock_in(client, monkeypatch):
    monkeypatch.setattr(te, "_today_local", lambda: TUE)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 2, 7, 30))
    resp = client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text


def test_k15_auto_close_clamps_and_flags(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes) == (time(18, 15), time(23, 59), 150)
    assert (e.auto_closed, e.clamp_grace_minutes, e.net_hours) == (True, 15, Decimal("7.75"))
    audit = _db_session.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.time_entry_id == e.id, TimeEntryAuditLog.source == "auto_close").one()
    assert audit.new_end_time == time(18, 15)


def test_without_blocks_end_stays_2359(_db_session, employee_user, employee_client, monkeypatch):
    e = _open(_db_session, employee_user)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)


def test_auto_close_uses_stored_grace(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.add(SystemSetting(key="work_window_grace_minutes", value="0", tenant_id=DEFAULT_TENANT_ID))
    _db_session.commit()
    e = _open(_db_session, employee_user, clamp_grace_minutes=15)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert e.end_time == time(18, 15)


def test_clock_status_stale_branch_closes_with_clamp(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: TUE)
    assert employee_client.get("/api/time-entries/clock-status").json()["is_clocked_in"] is False
    _db_session.refresh(e)
    assert (e.end_time, e.auto_closed) == (time(18, 15), True)


def _auto_close_directly(db, entry):
    """Ein Test mit ``admin_client`` UND ``employee_client`` sähe beide als
    dieselbe Person — beide Fixtures überschreiben ``get_current_user``, die
    zuletzt gebaute gewinnt. Deshalb den Auto-Close hier direkt aufrufen."""
    te._close_stale_entry(db, entry)
    db.commit()


def test_admin_end_correction_resets_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    assert e.auto_closed is True
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "17:00"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 0), None, False)


def test_admin_form_resave_keeps_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={
        "start_time": "08:00", "end_time": "18:15", "note": "geprüft"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)


# Review Focus 1: halboffenes Altfenster (Platzhalter 23:59) — wie 072.
def test_half_open_legacy_window_unchanged(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = legacy_week(mon=("08:00", None))
    _db_session.commit()
    e = _open(_db_session, employee_user, start=time(9, 0))
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes, e.auto_closed) == (time(23, 59), None, 0, True)


def test_half_open_legacy_window_late_clock_out(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = legacy_week(mon=("08:00", None))
    _db_session.commit()
    e = _open(_db_session, employee_user, start=time(9, 0))
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 22, 30))
    assert employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 45}).status_code == 200
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(22, 30), None, False)
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_auto_close_blocks.py -q -p no:cacheprovider`
Expected: FAIL — `end_time == 23:59` statt `18:15`, `auto_closed` False.

- [ ] **Step 3: `_close_stale_entry` umbauen**

```python
def _close_stale_entry(
    db: Session,
    entry: TimeEntry,
    *,
    changed_by_id=None,
) -> None:
    """Close a stale open entry of a previous day.

    Spec E36/E42: läuft über ``clamp`` — Ende 23:59 wird auf die Hülle
    (letzter Block + Puffer) gekappt, ``raw_end_time`` = 23:59. Puffer = der
    gespeicherte des Eintrags aus ``clock_in`` (E80). P18: ``auto_closed`` =
    True — 23:59 ist dann ein synthetischer Wert, kein Stempel. Ohne Blöcke
    bleibt 23:59 ungekappt (wie bisher).

    F-043: Does NOT commit — the caller's transaction owns the commit (und hat
    die Ankersperre, P5). Writes a TimeEntryAuditLog row with action=update /
    source=auto_close.
    """
    from app.services import work_window_service

    owner = db.query(User).filter(
        User.id == entry.user_id,
        User.tenant_id == entry.tenant_id,  # F-026
    ).first()
    old_end_time = entry.end_time
    old_note = entry.note

    r = work_window_service.clamp(
        db, owner, entry.date, entry.start_time, time(23, 59),
        work_window_service.grace_for_entry(db, entry),
        credit_override=entry.credit_override,
    )
    entry.end_time = r.eff_end
    entry.raw_end_time = r.raw_end
    entry.uncredited_minutes = r.uncredited_minutes
    if r.grace_minutes is not None:
        entry.clamp_grace_minutes = r.grace_minutes
    entry.auto_closed = True
    entry.note = (entry.note or '') + ' [auto-closed]'
    if entry.note.startswith(' '):
        entry.note = entry.note.strip()

    audit = TimeEntryAuditLog(
        time_entry_id=entry.id,
        user_id=entry.user_id,
        changed_by=changed_by_id or entry.user_id,
        action="update",
        source="auto_close",
        old_date=entry.date,
        old_start_time=entry.start_time,
        old_end_time=old_end_time,
        old_break_minutes=entry.break_minutes,
        old_note=old_note,
        new_date=entry.date,
        new_start_time=entry.start_time,
        new_end_time=entry.end_time,
        new_break_minutes=entry.break_minutes,
        new_note=entry.note,
        tenant_id=entry.tenant_id,
    )
    db.add(audit)
    db.flush()
```

- [ ] **Step 4: `auto_closed` an den übrigen Ende-Schreibern zurücksetzen**

`clock_out` — nach `open_entry.raw_end_time = raw_end`:

```python
    open_entry.auto_closed = False  # P18: echtes Ende gestempelt
```

`update_time_entry` — nach dem Uncredited-/Puffer-Block:

```python
    # P18: nur ein ANDERES Ende als das gespeicherte wirksame ist eine echte
    # Korrektur; das Formular schickt das wirksame Ende sonst unverändert mit.
    if "end_time" in update_data and update_data["end_time"] != orig_snapshot["end_time"]:
        entry.auto_closed = False
```

`admin_update_time_entry` — vor dem Block „Apply only provided updates" festhalten und danach anwenden:

```python
    _end_corrected = entry_data.end_time is not None and entry_data.end_time != entry.end_time
```

```python
    if _end_corrected:
        entry.auto_closed = False  # P18
```

`review_change_request`, UPDATE-Zweig — vor `entry.end_time = eff_end`:

```python
            _end_corrected = cr.proposed_end_time is not None and cr.proposed_end_time != entry.end_time
```

und nach den Zuweisungen:

```python
            if _end_corrected:
                entry.auto_closed = False  # P18
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (keine neuen Fehlschläge; bestehende Auto-Close-Tests ohne Fenster sehen weiter 23:59)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers backend/tests/test_auto_close_blocks.py
git commit -F - <<'EOF'
feat(bloecke): Auto-Close kappt über clamp und setzt auto_closed (E42, P18)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 9: Mitbehobene Bestandsfehler E39–E41, P3 (409), P28

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499: Schreibpfade; #491 F4 berührt das Antragsformular — Backend `change_requests.py` vor Beginn auf Änderungen prüfen).

**Files:**
- Modify: `backend/app/routers/time_entries.py` (`update_time_entry`: Gates, Warn-Gate, 409, Waiver-Antrag)
- Modify: `backend/app/routers/change_requests.py:194-331` (`create_change_request`)
- Modify: `backend/app/routers/admin_change_requests.py:1005-1056` (Nachprüfung nach dem Commit)
- Test: `backend/tests/test_legacy_fixes_blocks.py` (neu)

**Interfaces:**
- Consumes: `clamp`, `gap_segments`, `grace_for_entry`, `get_grace_minutes`, `unclamp_input` (Task 3); Netto-Helfer (Task 4); `validate_daily_break` (Task 5)
- Produces:
  - MA-`PUT /api/time-entries/{id}`: `date` im Neukappungs- und Warn-Gate (E39); 409 „Anerkannter Eintrag – Änderung bitte per Änderungsantrag." bei `credit_override`, wenn der Aufrufer kein Admin ist (P3)
  - `POST /api/change-requests`: §3/§4/§6/48 h auf `clamp` + `uncredited` (E40), Vorschläge weiter roh gespeichert; Snapshot `original_uncredited_minutes` (P28)
  - CR-Nachprüfung zählt den Eintrag nicht doppelt (E41)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_legacy_fixes_blocks.py`:

```python
"""Spec 7.2 / 2.7: E39, E40, E41 — und P3 (409), P28."""
import datetime as dt
from datetime import date, time

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

import app.routers.time_entries as te

FRI_BEFORE = date(2026, 5, 29)


def _entry(db, user, d, start, end, brk=0, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=brk, **kw)
    db.add(e)
    db.commit()
    return e


def test_e39_employee_date_change_reclamps_and_warns(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = legacy_week(fri=("08:00", "17:00"))
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(7, 0), time(16, 0), 30)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"date": FRI_BEFORE.isoformat()})
    assert resp.status_code == 200, resp.text
    assert any(w.startswith("WORK_WINDOW_CLAMPED") for w in resp.json()["warnings"])
    _db_session.refresh(e)
    assert (e.date, e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (FRI_BEFORE, time(7, 45), time(7, 0), 15)


def test_e40_request_validates_on_credited_time_and_stores_raw(_db_session, employee_user, employee_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "18:00",
        "proposed_break_minutes": 0, "reason": "Nachtrag Teilschicht"})
    assert resp.status_code == 201, resp.text
    cr = _db_session.query(ChangeRequest).one()
    assert (cr.proposed_start_time, cr.proposed_end_time) == (time(8, 0), time(18, 0))


def test_p28_request_snapshots_uncredited(_db_session, employee_user, employee_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(8), time(18), 45,
               uncredited_minutes=150, clamp_grace_minutes=15)
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id), "proposed_date": MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "18:00",
        "proposed_break_minutes": 45, "reason": "Notiz"})
    assert resp.status_code == 201, resp.text
    assert _db_session.query(ChangeRequest).one().original_uncredited_minutes == 150


def test_e41_post_commit_check_counts_entry_once(_db_session, employee_user, admin_client):
    for day in range(1, 5):                                  # Mo–Do je 9,5 h = 38 h
        _entry(_db_session, employee_user, date(2026, 6, day), time(7), time(17, 15), 45)
    fri = _entry(_db_session, employee_user, date(2026, 6, 5), time(8), time(14))   # 6 h → 44 h
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=fri.id, proposed_date=date(2026, 6, 5),
                       proposed_start_time=time(8), proposed_end_time=time(14),
                       proposed_break_minutes=0, proposed_note="Nachtrag", reason="Notiz")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    assert not [w for w in resp.json()["warnings"] if "Wochenarbeitszeit" in w], resp.json()["warnings"]


def test_p3_employee_put_on_acknowledged_entry_is_409(_db_session, employee_user, employee_client, monkeypatch):
    e = _entry(_db_session, employee_user, MON, time(8), time(12), credit_override=True)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"note": "x"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Anerkannter Eintrag – Änderung bitte per Änderungsantrag."


def test_p3_admin_on_the_employee_route_keeps_the_flag(_db_session, employee_user, admin_client):
    """P3 nennt „MA-PUT": die Verwaltung bestätigt neue Zeiten ausdrücklich —
    auch wenn sie den Mitarbeiter-Endpunkt benutzt (TimeTracking-Seite)."""
    employee_user.work_blocks = legacy_week(mon=("08:00", "12:00"))  # ohne Anerkennung: Ende → 12:15
    e = _entry(_db_session, employee_user, MON, time(7), time(12), credit_override=True)
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={"end_time": "12:30"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.credit_override) == (time(12, 30), None, True)


def test_employee_put_ignores_server_side_fields(_db_session, employee_user, employee_client, monkeypatch):
    """Spec 7.1 Nr. 4/E11: uncredited_minutes, credit_override, auto_closed,
    clamp_grace_minutes nie über die generische setattr-Schleife."""
    e = _entry(_db_session, employee_user, MON, time(8), time(12))
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={
        "note": "x", "uncredited_minutes": 999, "credit_override": True,
        "auto_closed": True, "clamp_grace_minutes": 99})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.uncredited_minutes, e.credit_override, e.auto_closed, e.clamp_grace_minutes) == (0, False, False, None)


def test_p3_admin_edit_and_cr_update_keep_flag(_db_session, employee_user, admin_client):
    e = _entry(_db_session, employee_user, MON, time(8), time(12), credit_override=True)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "12:30"}).status_code == 200
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=e.id, proposed_date=MON, proposed_start_time=time(8),
                       proposed_end_time=time(13), proposed_break_minutes=0, reason="Notiz")
    _db_session.add(cr)
    _db_session.commit()
    assert admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"}).status_code == 200
    _db_session.refresh(e)
    assert (e.end_time, e.credit_override) == (time(13), True)
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_legacy_fixes_blocks.py -q -p no:cacheprovider`
Expected: FAIL — E39 `start_time == 07:00` (keine Neukappung), E40 HTTP 400 (§4 auf Rohzeit), P28 `None`, E41 Warnung „Wochenarbeitszeit 50.0h", P3 (Mitarbeiter) HTTP 200. `test_p3_admin_on_the_employee_route_keeps_the_flag` und `test_employee_put_ignores_server_side_fields` sind schon grün (Regressionsschutz).

- [ ] **Step 3: `update_time_entry` (E39, P3, P28)**

Direkt nach der Edit-Schutz-Prüfung (403 für vergangene Tage):

```python
    # P3: ein anerkannter Eintrag wird nicht still per MA-PUT neu gekappt —
    # die Änderung läuft über einen Antrag (die Verwaltung bestätigt dort).
    # Admins auf dieser Route SIND die Verwaltung: Flag bleibt, keine Kappung.
    if entry.credit_override and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=409,
            detail="Anerkannter Eintrag – Änderung bitte per Änderungsantrag.",
        )
```

`orig_snapshot` um `"uncredited_minutes": entry.uncredited_minutes,` ergänzen; im Waiver-Antrag (`cr = ChangeRequest(...)` im Genehmigungsfall) nach `original_note=…`:

```python
                    original_uncredited_minutes=orig_snapshot["uncredited_minutes"],  # P28
```

Die beiden Schreib-Gates samt Uncredited-/Puffer-Block ersetzen:

```python
    # E39: ein reiner Datumswechsel auf einen anderen Wochentag kappt neu.
    _times_written = any(k in update_data for k in ("start_time", "end_time", "date"))
    if "start_time" in update_data or "date" in update_data:
        entry.start_time = _eff_start
        entry.raw_start_time = _raw_start
    if "end_time" in update_data or "date" in update_data:
        entry.end_time = _eff_end
        entry.raw_end_time = _raw_end
    if _times_written:
        entry.uncredited_minutes = _r.uncredited_minutes
        if _r.grace_minutes is not None:
            entry.clamp_grace_minutes = _r.grace_minutes
```

Warn-Gate ersetzen:

```python
    _resubmitted_unchanged = (
        entry.date == orig_snapshot["date"]
        and _clamp_start == (orig_snapshot["raw_start_time"] or orig_snapshot["start_time"])
        and _clamp_end == (orig_snapshot["raw_end_time"] or orig_snapshot["end_time"])
    )
    if _times_written and not _resubmitted_unchanged:
        _clamp_warn = work_window_service.clamp_warning(
            db, _entry_owner, entry.date, _r, for_employee=True,
        )
        if _clamp_warn:
            update_warnings.append(_clamp_warn)
```

- [ ] **Step 4: `create_change_request` (E40, P28)**

In `backend/app/routers/change_requests.py` direkt vor dem Kommentar „# Break validation for CREATE and UPDATE (§18-Ausnahme …)" einfügen:

```python
    # E40 (Spec 2026-10-08): der Antrag prüft §3/§4/§6/48 h auf der
    # ANGERECHNETEN Zeit — wie die Genehmigung. Gespeichert werden weiter die
    # ROHEN Vorschläge (die Genehmigung kappt genau einmal, admin_change_requests).
    from app.services import work_window_service
    _cr_clamp = None
    _cr_segs: list = []
    if (data.request_type in ("create", "update")
            and data.proposed_date and data.proposed_start_time and data.proposed_end_time):
        _in_start, _in_end = data.proposed_start_time, data.proposed_end_time
        _override = bool(entry is not None and entry.credit_override)
        if entry is not None:
            # Das Antragsformular belegt die Zeiten mit der angerechneten Zeit vor
            # (Release-Review 1.19.3 F1) — derselbe Rohwert-Rückgriff wie bei der
            # Genehmigung, sonst zählte eine reine Pausen-Korrektur gekappt.
            _in_start = work_window_service.unclamp_input(_in_start, entry.start_time, entry.raw_start_time)
            _in_end = work_window_service.unclamp_input(_in_end, entry.end_time, entry.raw_end_time)
            _cr_grace = work_window_service.grace_for_entry(db, entry)
        else:
            _cr_grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
        _cr_clamp = work_window_service.clamp(
            db, current_user, data.proposed_date, _in_start, _in_end, _cr_grace,
            credit_override=_override,
        )
        _cr_segs = work_window_service.gap_segments(
            db, current_user, data.proposed_date, _in_start, _in_end, _cr_grace,
            credit_override=_override,
        )
    _chk_start = _cr_clamp.eff_start if _cr_clamp else data.proposed_start_time
    _chk_end = _cr_clamp.eff_end if _cr_clamp else data.proposed_end_time
    _chk_unc = _cr_clamp.uncredited_minutes if _cr_clamp else 0
```

(Der Absence-Zweig ist an dieser Stelle schon zurückgekehrt — hier geht es nur um Zeiteintrags-Anträge.) Die beiden Prüfaufrufe vor dem Speichern werden zu:

```python
        break_error = validate_daily_break(
            db=db,
            user=current_user,
            entry_date=data.proposed_date,
            start_time=_chk_start,
            end_time=_chk_end,
            break_minutes=data.proposed_break_minutes or 0,
            uncredited_segments=_cr_segs,
            exclude_entry_id=entry.id if entry else None,
            tenant_id=current_user.tenant_id,
        )
```

```python
        daily_hours = _calculate_daily_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=_chk_start,
            end_time=_chk_end,
            break_minutes=data.proposed_break_minutes or 0,
            uncredited_minutes=_chk_unc,
            exclude_entry_id=entry.id if entry else None,
            tenant_id=current_user.tenant_id,
        )
```

Im Snapshot nach `cr.original_note = entry.note`:

```python
        cr.original_uncredited_minutes = entry.uncredited_minutes  # P28
```

Die Warnungen nach dem Commit (§6 Nacht, 48 h) rechnen auf derselben Grundlage:

```python
        daily_hours_check = _calculate_daily_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=_chk_start,
            end_time=_chk_end,
            break_minutes=data.proposed_break_minutes or 0,
            uncredited_minutes=_chk_unc,
            exclude_entry_id=entry.id if entry else None,
            tenant_id=current_user.tenant_id,
        )
        if (
            current_user.is_night_worker
            and is_night_work(_chk_start, _chk_end)
            and daily_hours_check > MAX_NIGHT_WORKER_DAILY_WARN
        ):
```

```python
        weekly_hours_check = _calculate_weekly_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=_chk_start,
            end_time=_chk_end,
            break_minutes=data.proposed_break_minutes or 0,
            uncredited_minutes=_chk_unc,
            exclude_entry_id=entry.id if entry else None,
            tenant_id=current_user.tenant_id,
        )
```

Kontrolle: `grep -n "data.proposed_start_time\|data.proposed_end_time" backend/app/routers/change_requests.py` zeigt nur noch die Pflichtfeld-/Reihenfolge-Prüfungen, `_in_start/_in_end` und den `ChangeRequest(...)`-Konstruktor (dort bleiben die ROHEN Werte).

- [ ] **Step 5: Nachprüfung nach dem Commit in `review_change_request` (E41)**

Den Block ab `cr_user = db.query(User)…` innerhalb von `if review.action == "approve" and cr.request_type in (CREATE, UPDATE) …` ersetzen:

```python
        cr_user = db.query(User).filter(User.id == cr.user_id, User.tenant_id == cr.tenant_id).first()
        # E41: der eben geschriebene Eintrag steht schon in der Tabelle — er wird
        # ausgeschlossen und mit seinen GESPEICHERTEN Werten (gekappt, uncredited,
        # Pause) einmal addiert, statt doppelt gezählt zu werden.
        _w_entry = (
            db.query(TimeEntry).filter(
                TimeEntry.id == cr.time_entry_id,
                TimeEntry.tenant_id == cr.tenant_id,  # F-026
            ).first()
            if cr.time_entry_id else None
        )
        if cr_user and not cr_user.exempt_from_arbzg and _w_entry is not None and _w_entry.end_time is not None:
            _w_kwargs = dict(
                db=db,
                user_id=cr.user_id,
                entry_date=_w_entry.date,
                start_time=_w_entry.start_time,
                end_time=_w_entry.end_time,
                break_minutes=_w_entry.break_minutes,
                uncredited_minutes=_w_entry.uncredited_minutes,
                exclude_entry_id=_w_entry.id,
                tenant_id=cr.tenant_id,
            )
            daily_hours_cr = _calculate_daily_net_hours(**_w_kwargs)
            if (
                cr_user.is_night_worker
                and is_night_work(_w_entry.start_time, _w_entry.end_time)
                and daily_hours_cr > MAX_NIGHT_WORKER_DAILY_WARN
            ):
                cr_response.warnings.append(
                    f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours_cr:.1f}h). "
                    "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
                )
            weekly = _calculate_weekly_net_hours(**_w_kwargs)
            if weekly > MAX_WEEKLY_HOURS_WARN:
                cr_response.warnings.append(
                    f"§3 ArbZG: Wochenarbeitszeit {weekly:.1f}h überschreitet 48h-Grenze."
                )
```

(Die bisherigen Variablen `_wgrace`, `_rw`, `_w_start`, `_w_end` entfallen.)

- [ ] **Step 6: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (keine neuen Fehlschläge; ein Bestandstest, der die doppelte Zählung der Nachprüfung als erwartet kodiert, wird auf die korrekte einfache Zählung umgestellt, nicht gelöscht)

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers backend/tests/test_legacy_fixes_blocks.py
git commit -F - <<'EOF'
fix(bloecke): Datumswechsel kappt neu (E39), Antrag prüft angerechnete Zeit (E40), keine Doppelzählung (E41), 409 für anerkannte Einträge (P3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 10: XLS-Import — `clamp_applies`, Auto-Pause-Rest, Puffer-Herkunft, Mandantenfilter (7.1 Nr. 11/12, 7.3, 7.4)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499 ist in `3d46c2f` gemergt und hat `xls_import_service.py`/`import_xls.py` nicht angefasst; die Rechenregel von `validate_daily_break` blieb dort unverändert — die Vollersetzung unten gilt wörtlich. Kommt später eine §4-Regeländerung hinzu, gehört sie in `daily_break_figures`, nicht als vierter Nachbau in `_check_arbzg`.)

**Files:**
- Modify (komplett ersetzen): `backend/app/services/xls_import_service.py`
- Modify: `backend/app/routers/import_xls.py:77` (`parse_xls(..., tenant_id=…)`)
- Modify: `backend/tests/test_xls_import_service.py` (Aufrufe von `_calc_break_minutes`/`_check_arbzg` auf die neuen Pflichtparameter)
- Modify: `backend/tests/test_write_path_locks.py` (XLS-Fall anhängen)
- Test (neu): `backend/tests/test_xls_blocks.py`

**Interfaces:**
- Consumes: `work_window_service.clamp`, `gap_segments`, `clamp_applies`, `grace_for_entry`, `get_grace_minutes`, `clamp_warning_text(db, user, d, result, *, for_employee)` (Task 3); `break_validation_service.BreakBlock`, `break_block_for_new`, `break_block_for_entry`, `daily_break_figures` (Task 5); `admin_helpers.lock_user_row` (lokal importiert); Fixture `calls`/`assert_lock_first` aus `tests/test_write_path_locks.py` (Task 7)
- Produces (in `app.services.xls_import_service`):
  - `CREDIT_OVERRIDE_IMPORT_NOTE: str` = „Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet." (P3)
  - `ImportedEntry.uncredited_minutes: int = 0` — nur Anzeige der Vorschau; `/confirm` übernimmt ihn nie
  - `_calc_break_minutes(eff_start: time, eff_end: time, segments: Sequence[int]) -> int` (7.4; `segments` Pflicht)
  - `_check_arbzg(entry_date: date, start: time, end: time, break_min: int, prev_end_dt: Optional[datetime], exempt: bool = False, is_night_worker: bool = False, same_day_blocks: Optional[list[BreakBlock]] = None, *, uncredited_segments: Sequence[int], rest_start: Optional[time] = None) -> list[str]`
  - `_find_existing_entry(db, user_id, tenant_id, d: date, *, starts: Sequence[time], raw_start: time) -> Optional[TimeEntry]`
  - `_start_taken(db, user_id, tenant_id, d: date, start: time, exclude_id) -> bool`
  - `parse_xls(file_bytes: bytes, user_id: uuid.UUID, db: Session, *, tenant_id: Optional[uuid.UUID] = None) -> list[ImportedEntry]` (unbekannte Person → `ValueError("Benutzer nicht gefunden")`)
  - `_execute_import_inner(...)`: Ankersperre einmal am Anfang (P5); Gate `clamp_applies(…, credit_override=<Zieleintrag>)` (E38); Zeiten, `raw_*`, `uncredited_minutes` und Auto-Pause serverseitig neu; Überschreiben schreibt `start_time`, `uncredited_minutes`, `clamp_grace_minutes` (Puffer des Zieleintrags, E80), `auto_closed = False` (P18) und lässt `credit_override` stehen (P3)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_xls_blocks.py`:

```python
"""Spec 2026-10-08, 7.1 Nr. 11/12, 7.3, 7.4, E38, E80, P3: XLS-Import und Blöcke."""
import uuid
from datetime import date, datetime, time

import pytest

from app.models import TimeEntry
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.services.xls_import_service import (
    CREDIT_OVERRIDE_IMPORT_NOTE, ImportedEntry, _calc_break_minutes, execute_import, parse_xls,
)
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]
LEGACY = legacy_week(mon=("08:00", "17:00"))


def _xls(*rows):
    return _make_xls_bytes([HEADER, *[_make_data_row(a, b) for a, b in rows]])


def _row(start, end, **kw):
    return ImportedEntry(date=MON, start_time=start, end_time=end, break_minutes=kw.pop("break_minutes", 0),
                         note=None, has_conflict=False, arbzg_warnings=[], **kw)


def _entry(db, user, start, end, **kw):
    e = TimeEntry(tenant_id=kw.pop("tenant_id", DEFAULT_TENANT_ID), user_id=user.id,
                  date=kw.pop("day", MON), start_time=start, end_time=end,
                  break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def _grace(db, minutes):
    db.add(SystemSetting(key="work_window_grace_minutes", value=str(minutes), tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def _run(db, user, admin, entries, overwrite=False):
    return execute_import(user.id, entries, overwrite=overwrite, db=db, changed_by_id=admin.id,
                          filename="t.xls", tenant_id=DEFAULT_TENANT_ID)


@pytest.mark.parametrize("start, end, segments, expected", [
    (time(8), time(18), [150], 0),        # K1: Lücke deckt §4 (heute 45 → Doppelabzug)
    (time(8), time(17, 30), [10], 45),    # Segment < 15 deckt nichts
    (time(8), time(17), [20], 15),        # Rest 10 Min → auf 15 aufgerundet (§4 Satz 2)
    (time(8), time(16, 1), [], 30),       # ohne Blöcke wie bisher
])
def test_auto_pause_rest(start, end, segments, expected):
    assert _calc_break_minutes(start, end, segments) == expected


def test_k1_preview_gap_note_without_raw_and_no_s3_s4_warning(db, test_user):
    """8.2: K1 als Import ergibt keine §3/§4-Warnung (angerechnet 7:30 h, Lücke
    deckt §4) — auch nicht in der Tagesaggregation mit einem DB-Eintrag direkt
    danach; der reine Lückenfall bekommt trotzdem den Kappungshinweis."""
    test_user.work_blocks = K_BLOCKS
    db.commit()
    _entry(db, test_user, time(18), time(18, 30))
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 18, 0))), test_user.id, db)
    assert (row.start_time, row.end_time, row.raw_start_time, row.raw_end_time) == (time(8), time(18), None, None)
    assert (row.uncredited_minutes, row.break_minutes) == (150, 0)
    assert not [w for w in row.arbzg_warnings if w.startswith(("§3", "§4"))], row.arbzg_warnings
    assert any(w.startswith("Zwischen den Arbeitsblöcken (12:15–14:45") for w in row.arbzg_warnings)


def test_confirm_ignores_client_uncredited_and_break(db, test_user, test_admin):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    _run(db, test_user, test_admin, [_row(time(8), time(18), break_minutes=45, uncredited_minutes=999)])
    e = db.query(TimeEntry).one()
    assert (e.uncredited_minutes, e.break_minutes, e.clamp_grace_minutes) == (150, 0, 15)


def test_day_without_blocks_keeps_client_raw_on_new_entry(db, test_user, test_admin):
    _run(db, test_user, test_admin, [_row(time(7, 15), time(16), raw_start_time=time(6, 30))])
    e = db.query(TimeEntry).one()
    assert (e.start_time, e.raw_start_time, e.uncredited_minutes, e.clamp_grace_minutes) == (
        time(7, 15), time(6, 30), 0, None)


def test_track_hours_false_with_blocks_keeps_client_raw(db, test_user, test_admin):
    """E38/F27: clamp_applies prüft track_hours — sonst löschte die Kappung, die
    gar nicht stattfindet, einen mitgelieferten Rohstempel."""
    test_user.work_blocks = LEGACY
    test_user.track_hours = False
    db.commit()
    _run(db, test_user, test_admin, [_row(time(7, 15), time(16), raw_start_time=time(6, 30))])
    e = db.query(TimeEntry).one()
    assert (e.start_time, e.raw_start_time) == (time(7, 15), time(6, 30))


def test_foreign_tenant_rows_are_invisible(db, test_user, test_admin):
    """7.3/F-026: Konfliktsuche und Überschreiben nur im eigenen Mandanten."""
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd-xls")
    db.add(other)
    db.commit()
    foreign = _entry(db, test_user, time(8), time(12), tenant_id=other.id, note="fremd")
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 13, 0))), test_user.id, db)
    assert row.has_conflict is False
    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert (result.imported, result.overwritten) == (1, 0)
    db.refresh(foreign)
    assert (foreign.end_time, foreign.note) == (time(12), "fremd")


def test_rest_time_uses_the_raw_end(db, test_user):
    """7.3: §5 gegen den Rohstempel (raw_end or end) wie rest_time_service."""
    _entry(db, test_user, time(12), time(20), day=date(2026, 5, 31), raw_end_time=time(23, 0))
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 12, 0))), test_user.id, db)
    assert any(w.startswith("§5 ArbZG: Ruhezeit 9.0h") for w in row.arbzg_warnings), row.arbzg_warnings


def test_overwriting_an_acknowledged_entry_keeps_the_flag_and_warns(db, test_user, test_admin):
    test_user.work_blocks = LEGACY
    db.commit()
    e = _entry(db, test_user, time(8), time(17), credit_override=True)
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 18, 30))), test_user.id, db)
    assert row.has_conflict is True
    assert (row.end_time, row.raw_end_time) == (time(18, 30), None)
    assert CREDIT_OVERRIDE_IMPORT_NOTE in row.arbzg_warnings
    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert result.overwritten == 1
    db.refresh(e)
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes, e.credit_override) == (time(18, 30), None, 0, True)


# Review Focus 3: Re-Import desselben Tages nach einer Puffer-Senkung.
def test_reimport_after_grace_reduction_finds_the_entry_and_keeps_its_grace(db, test_user, test_admin):
    test_user.work_blocks = LEGACY
    db.commit()
    e = _entry(db, test_user, time(7, 45), time(16), raw_start_time=time(7, 0), clamp_grace_minutes=15)
    _grace(db, 10)
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 7, 0), _dt(2026, 6, 1, 16, 0))), test_user.id, db)
    assert (row.has_conflict, row.start_time, row.raw_start_time) == (True, time(7, 45), time(7, 0))
    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert (result.imported, result.overwritten) == (0, 1)
    assert db.query(TimeEntry).count() == 1
    db.refresh(e)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes, e.auto_closed) == (time(7, 45), time(7, 0), 15, False)


def test_overwrite_skips_when_the_new_start_is_taken(db, test_user, test_admin):
    """Der Beginn eines überschriebenen Eintrags kann sich durch dessen
    gespeicherten Puffer ändern — trifft er einen anderen Eintrag, wird die
    Zeile übersprungen statt an ``uq_tenant_user_date_start`` zu scheitern."""
    test_user.work_blocks = LEGACY
    db.commit()
    x = _entry(db, test_user, time(7), time(12), clamp_grace_minutes=30)
    _entry(db, test_user, time(7, 30), time(7, 40))
    result = _run(db, test_user, test_admin, [_row(time(7), time(12))], overwrite=True)
    assert (result.overwritten, result.skipped) == (0, 1)
    assert any("beginnt bereits um 07:30" in w for w in result.warnings)
    db.refresh(x)
    assert x.start_time == time(7)
```

An `backend/tests/test_write_path_locks.py` anhängen:

```python
def test_xls_import(_db_session, employee_user, admin_user, calls):
    """P5: ``_execute_import_inner`` sperrt die Zielperson EINMAL am Anfang —
    vor Puffer, Snapshot und clamp (lokaler Import → Spy über admin_helpers)."""
    from app.services.xls_import_service import ImportedEntry, execute_import

    _setup(_db_session, employee_user)
    row = ImportedEntry(date=MON, start_time=time(8), end_time=time(12), break_minutes=0,
                        note=None, has_conflict=False, arbzg_warnings=[])
    result = execute_import(employee_user.id, [row], overwrite=False, db=_db_session,
                            changed_by_id=admin_user.id, filename="t.xls", tenant_id=DEFAULT_TENANT_ID)
    assert result.imported == 1
    assert_lock_first(calls, employee_user.id)
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_xls_blocks.py tests/test_write_path_locks.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'CREDIT_OVERRIDE_IMPORT_NOTE'` (Sammlung von `test_xls_blocks.py`) und `test_xls_import` („keine Ankersperre").

- [ ] **Step 3: `xls_import_service.py` komplett ersetzen**

`execute_import` und `_excel_serial_to_datetime` bleiben inhaltlich gleich; neu sind die Puffer-Herkunft je Zieleintrag (E80), der Rohstempel-Abgleich bei der Konfliktsuche (sonst entstünde nach einer Puffer-Senkung ein zweiter Eintrag), `clamp_applies` als Gate, die Lücken in Auto-Pause und §3/§4 und die Mandantenfilter:

```python
"""
Service für den Import historischer Zeiterfassungsdaten aus TimeRec-XLS-Dateien.
Dateiformat: Sheet "Zeiterfassung", Spalten: Datum, Tag, Total, Ein, Aus, Tagesnotiz
"""
import uuid
import xlrd
from datetime import datetime, timedelta, date, time
from typing import Optional, Sequence
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models import TimeEntry, TimeEntryAuditLog, User
from app.services.arbzg_utils import is_night_work
from app.services import work_window_service
from app.services.break_validation_service import (
    BreakBlock, break_block_for_entry, break_block_for_new, daily_break_figures,
)

EXCEL_EPOCH = datetime(1899, 12, 30)
MAX_DAILY_NET_HOURS = 10.0   # §3 ArbZG
MIN_REST_HOURS = 11.0        # §5 ArbZG
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# Spec 2026-10-08 P3: Hinweis in der Vorschau, wenn die Zeile einen anerkannten
# Eintrag überschreibt — die neuen Zeiten werden dann ungekappt angerechnet.
CREDIT_OVERRIDE_IMPORT_NOTE = (
    "Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet."
)


class ImportedEntry(BaseModel):
    date: date
    start_time: time
    end_time: time
    break_minutes: int
    note: Optional[str]
    has_conflict: bool
    arbzg_warnings: list[str]
    raw_start_time: Optional[time] = None
    raw_end_time: Optional[time] = None
    # Spec 2026-10-08 (7.1 Nr. 11): nur ANZEIGE der Vorschau. ``/confirm``
    # übernimmt den Wert nie (E11) — ``_execute_import_inner`` rechnet neu.
    uncredited_minutes: int = 0


class ImportResult(BaseModel):
    imported: int
    skipped: int
    overwritten: int
    warnings: list[str]


def _excel_serial_to_datetime(serial: float) -> datetime:
    """Konvertiert Excel-Serial-Datetime zu Python-datetime. Basis: 1899-12-30."""
    return EXCEL_EPOCH + timedelta(days=serial)


def _min(t: time) -> int:
    return t.hour * 60 + t.minute


def _calc_break_minutes(eff_start: time, eff_end: time, segments: Sequence[int]) -> int:
    """ArbZG §4: Auto-Pause aus der ANGERECHNETEN Bruttozeit (Spec 7.4).

    ``segments`` = ``work_window_service.gap_segments`` der Zeile. Lückensegmente
    >= 15 Min decken den Bedarf als Pausenabschnitt; nachgetragen wird nur, was
    fehlt — sonst zöge der Import eine Pause in der Lücke ein zweites Mal ab
    (Doppelabzug, E45). Ein Rest unter 15 Min wird auf 15 aufgerundet (§4 Satz 2).
    Ohne Blöcke (``segments == []``) byte-identisch zur bisherigen Regel.
    Note: assumes end > start (no overnight shifts) — TimeRec liefert keine."""
    credited_gross = (_min(eff_end) - _min(eff_start)) - sum(segments)
    required = 45 if credited_gross > 9 * 60 else 30 if credited_gross > 6 * 60 else 0
    covered = sum(s for s in segments if s >= 15)
    rest = max(0, required - covered)
    return 15 if 0 < rest < 15 else rest


NIGHT_WORKER_MAX_NET_HOURS = 8.0  # §6 Abs. 2 ArbZG: Nachtarbeitnehmer


def _check_arbzg(
    entry_date: date,
    start: time,
    end: time,
    break_min: int,
    prev_end_dt: Optional[datetime],
    exempt: bool = False,
    is_night_worker: bool = False,
    same_day_blocks: Optional[list[BreakBlock]] = None,
    *,
    uncredited_segments: Sequence[int],
    rest_start: Optional[time] = None,
) -> list[str]:
    """ArbZG-Warnungen ermitteln (§3 Tageslimit, §4 Pause, §5 Ruhezeit, §6 Nachtarbeit).

    exempt=True (§18 ArbZG): alle Prüfungen werden übersprungen.
    is_night_worker=True (§6 Abs. 2 ArbZG): 8h-Limit statt 10h.
    same_day_blocks: ``BreakBlock`` der anderen Einträge desselben Tages (Import-
        Batch + vorhandene DB). Wenn übergeben, werden §3 und §4 auf Basis der
        Tages-Aggregation bewertet — mit derselben Regel wie
        ``validate_daily_break`` (``daily_break_figures``), kein vierter Nachbau.
    uncredited_segments: Lückensegmente dieses Eintrags (Spec 8.2) — nicht
        angerechnete Zeit ist keine Arbeitszeit, Segmente >= 15 Min zählen als Pause.
    rest_start: Beginn für §5, der ROHSTEMPEL (``raw_start or start``) wie in
        ``rest_time_service`` (Spec 7.3); ohne Angabe ``start``.
    """
    if exempt:
        return []

    warnings = []
    own = break_block_for_new(start, end, break_min, uncredited_segments)
    net_hours = (own.end - own.start - own.deduct_minutes) / 60.0 - break_min / 60.0

    if same_day_blocks:
        # §3 / §4 Aggregation: alle Blöcke des Tages zusammenfassen (inkl. diesem Eintrag)
        total_net_min, total_effective_break = daily_break_figures(list(same_day_blocks) + [own])
        total_net_hours = total_net_min / 60.0

        # §3 / §6 Abs. 2 auf Tagesbasis
        if is_night_worker and total_net_hours > NIGHT_WORKER_MAX_NET_HOURS:
            warnings.append(
                f"§6 Abs. 2 ArbZG: Nachtarbeitnehmer — Tages-Netto-Arbeitszeit {total_net_hours:.1f}h überschreitet 8h-Limit"
            )
        elif total_net_hours > MAX_DAILY_NET_HOURS:
            warnings.append(
                f"§3 ArbZG: Tages-Netto-Arbeitszeit {total_net_hours:.1f}h überschreitet das 10h-Tageslimit"
            )

        # §4 Pausenpflicht auf Tagesbasis
        if total_net_min > 540 and total_effective_break < 45:
            warnings.append(
                f"§4 ArbZG: Tages-Netto-Arbeitszeit {total_net_hours:.1f}h erfordert mindestens 45 Minuten Pause "
                f"(Gesamtpause: {total_effective_break} Minuten)"
            )
        elif total_net_min > 360 and total_effective_break < 30:
            warnings.append(
                f"§4 ArbZG: Tages-Netto-Arbeitszeit {total_net_hours:.1f}h erfordert mindestens 30 Minuten Pause "
                f"(Gesamtpause: {total_effective_break} Minuten)"
            )
    else:
        # Einzeleintrag: §3 / §6 Abs. 2 nur anhand dieses Eintrags
        if is_night_worker and net_hours > NIGHT_WORKER_MAX_NET_HOURS:
            warnings.append(
                f"§6 Abs. 2 ArbZG: Nachtarbeitnehmer — Netto-Arbeitszeit {net_hours:.1f}h überschreitet 8h-Limit"
            )
        elif net_hours > MAX_DAILY_NET_HOURS:
            # §3: allgemeines 10h-Tageslimit
            warnings.append(
                f"§3 ArbZG: Netto-Arbeitszeit {net_hours:.1f}h überschreitet das 10h-Tageslimit"
            )

    if is_night_work(start, end):
        # §6 Abs. 1: Nachtarbeit-Erkennung (>2h zwischen 23:00–06:00)
        warnings.append("§6 ArbZG: Nachtarbeit (>2h in der Nachtzeit 23:00–06:00)")

    if prev_end_dt is not None:
        curr_start_dt = datetime.combine(entry_date, rest_start or start)
        rest_hours = (curr_start_dt - prev_end_dt).total_seconds() / 3600.0
        if rest_hours < MIN_REST_HOURS:
            warnings.append(
                f"§5 ArbZG: Ruhezeit {rest_hours:.1f}h unterschreitet das 11h-Minimum "
                f"(vorheriger Eintrag endete {prev_end_dt.strftime('%d.%m.%Y %H:%M')})"
            )

    return warnings


def _find_existing_entry(
    db: Session,
    user_id: uuid.UUID,
    tenant_id,
    d: date,
    *,
    starts: Sequence[time],
    raw_start: time,
) -> Optional[TimeEntry]:
    """Der Eintrag, den eine Importzeile überschreiben würde.

    Reihenfolge:
    1. ``start_time`` == einer der ``starts`` (angerechneter Beginn der Zeile,
       bei ``/confirm`` zusätzlich der vom Client gelieferte) — Verhalten bis 1.19.3;
    2. ``raw_start_time`` == Dateibeginn — ein gekappter Eintrag, der mit dem
       AKTUELLEN Puffer einen anderen Beginn bekäme (Puffer seither geändert).
       Ohne diesen Schritt entstünde ein zweiter Eintrag neben dem alten;
    3. ``start_time`` == Dateibeginn — ein ungekappt gespeicherter Eintrag
       (anerkannt, oder erfasst, als der Tag noch keine Blöcke hatte).

    F-026: ``tenant_id``-Filter zusätzlich zu RLS (Spec 7.3)."""
    base = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.tenant_id == tenant_id,
        TimeEntry.date == d,
    )
    for start in dict.fromkeys(s for s in starts if s is not None):
        hit = base.filter(TimeEntry.start_time == start).first()
        if hit is not None:
            return hit
    hit = base.filter(TimeEntry.raw_start_time == raw_start).first()
    if hit is not None:
        return hit
    return base.filter(TimeEntry.start_time == raw_start).first()


def _start_taken(db: Session, user_id, tenant_id, d: date, start: time, exclude_id) -> bool:
    """Belegt ein ANDERER Eintrag des Tages schon diesen Beginn?
    (``uq_tenant_user_date_start`` — SQLite prüft den Index nicht.)"""
    return db.query(TimeEntry.id).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.tenant_id == tenant_id,  # F-026
        TimeEntry.date == d,
        TimeEntry.start_time == start,
        TimeEntry.id != exclude_id,
    ).first() is not None


def parse_xls(
    file_bytes: bytes,
    user_id: uuid.UUID,
    db: Session,
    *,
    tenant_id: Optional[uuid.UUID] = None,
) -> list[ImportedEntry]:
    """
    Parst eine TimeRec-XLS-Datei und gibt ImportedEntry-Liste zurück.
    Ermittelt Konflikte (user_id+date+start_time) und ArbZG-Warnungen.

    ``tenant_id``: F-026 — der Router übergibt den Mandanten der Verwaltung.

    Raises ValueError bei ungültigem Format oder fehlenden Daten.
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError("Datei zu groß (max. 5 MB)")

    try:
        wb = xlrd.open_workbook(file_contents=file_bytes)
    except xlrd.XLRDError as e:
        raise ValueError(f"Datei konnte nicht geöffnet werden: {e}")

    if "Zeiterfassung" not in wb.sheet_names():
        raise ValueError(
            f"Sheet 'Zeiterfassung' nicht gefunden. "
            f"Vorhandene Sheets: {', '.join(wb.sheet_names())}"
        )

    # §18-Bypass und §6 Abs. 2: User-Flags einmalig laden
    user_query = db.query(User).filter(User.id == user_id)
    if tenant_id is not None:
        user_query = user_query.filter(User.tenant_id == tenant_id)  # F-026
    user = user_query.first()
    if user is None:
        raise ValueError("Benutzer nicht gefunden")
    exempt = bool(getattr(user, "exempt_from_arbzg", False))
    is_night_worker = bool(getattr(user, "is_night_worker", False))
    user_tenant = user.tenant_id

    # Puffer des Mandanten (Default 15 min) — für NEUE Einträge (E80).
    grace = work_window_service.get_grace_minutes(db, user_tenant)

    ws = wb.sheet_by_name("Zeiterfassung")
    entries: list[ImportedEntry] = []
    prev_end_dt: Optional[datetime] = None
    first_import_date: Optional[date] = None

    # §3/§4 Tagesaggregation: BreakBlocks pro Datum (Import-Batch + DB-Einträge)
    batch_blocks_by_date: dict[date, list[BreakBlock]] = {}
    db_blocks_by_date: dict[date, list[BreakBlock]] = {}

    for row_idx in range(ws.nrows):
        # Datenzeile erkennbar durch numerischen ctype (3) in Ein-Spalte (D)
        if ws.cell(row_idx, 3).ctype != 3:
            continue

        ein_serial = ws.cell_value(row_idx, 3)
        aus_serial = ws.cell_value(row_idx, 4)
        notiz_raw = ws.cell_value(row_idx, 5)

        ein_dt = _excel_serial_to_datetime(ein_serial)
        aus_dt = _excel_serial_to_datetime(aus_serial)
        note = str(notiz_raw).strip() if notiz_raw is not None and str(notiz_raw).strip() else None

        entry_date = ein_dt.date()
        # Sekunden auf 0 setzen (XLS hat keine Sekunden)
        file_start = ein_dt.time().replace(second=0, microsecond=0)
        file_end = aus_dt.time().replace(second=0, microsecond=0)

        # Spec 6.1/E80: neue Zeilen kappen mit dem aktuellen Puffer; trifft die
        # Zeile einen GESPEICHERTEN Eintrag, gelten dessen Puffer und dessen
        # Anerkennung (P3) — die Vorschau zeigt, was /confirm schreiben wird.
        r = work_window_service.clamp(
            db, user, entry_date, file_start, file_end, grace, credit_override=False,
        )
        existing = _find_existing_entry(
            db, user_id, user_tenant, entry_date, starts=(r.eff_start,), raw_start=file_start,
        )
        override = bool(existing is not None and existing.credit_override)
        row_grace = (
            work_window_service.grace_for_entry(db, existing) if existing is not None else grace
        )
        if override or row_grace != grace:
            r = work_window_service.clamp(
                db, user, entry_date, file_start, file_end, row_grace, credit_override=override,
            )
        segs = work_window_service.gap_segments(
            db, user, entry_date, file_start, file_end, row_grace, credit_override=override,
        )
        start_t, end_t = r.eff_start, r.eff_end
        raw_start_t, raw_end_t = r.raw_start, r.raw_end

        break_min = _calc_break_minutes(start_t, end_t, segs)

        # §5-Check: Für den ersten Eintrag im Import letzten DB-Eintrag vor Import-Zeitraum holen.
        # Spec 7.3: gegen den ROHSTEMPEL (raw_end or end) wie rest_time_service.
        check_prev = prev_end_dt
        if first_import_date is None:
            first_import_date = entry_date
            last_db_entry = (
                db.query(TimeEntry)
                .filter(
                    TimeEntry.user_id == user_id,
                    TimeEntry.tenant_id == user_tenant,  # F-026
                    TimeEntry.date < entry_date,
                )
                .order_by(TimeEntry.date.desc(), TimeEntry.start_time.desc())
                .first()
            )
            if last_db_entry and last_db_entry.end_time:
                check_prev = datetime.combine(
                    last_db_entry.date, last_db_entry.raw_end_time or last_db_entry.end_time,
                )

        # §3/§4 Tagesaggregation: bestehende DB-Einträge für diesen Tag einmalig laden
        if entry_date not in db_blocks_by_date:
            db_blocks_by_date[entry_date] = [
                break_block_for_entry(db, user, e)
                for e in db.query(TimeEntry).filter(
                    TimeEntry.user_id == user_id,
                    TimeEntry.tenant_id == user_tenant,  # F-026
                    TimeEntry.date == entry_date,
                ).all()
                if e.end_time is not None
            ]

        # Alle anderen Blöcke am selben Tag = DB-Blöcke + bisher im Batch gesammelte Blöcke
        other_blocks = db_blocks_by_date[entry_date] + batch_blocks_by_date.get(entry_date, [])

        arbzg_warnings = _check_arbzg(
            entry_date, start_t, end_t, break_min, check_prev,
            exempt=exempt, is_night_worker=is_night_worker,
            same_day_blocks=other_blocks if other_blocks else None,
            uncredited_segments=segs,
            rest_start=raw_start_t or start_t,
        )

        # #462: Die Kappung darf auch hier nicht stumm passieren. Spec 7.1 Nr. 11:
        # auch ein reiner Lückenfall (K1, ohne raw_*) bekommt den Hinweis.
        # Klartext ohne Code-Präfix (Tooltip der Vorschau).
        if raw_start_t is not None or raw_end_t is not None or r.uncredited_minutes > 0:
            clamp_note = work_window_service.clamp_warning_text(
                db, user, entry_date, r, for_employee=False,
            )
            if clamp_note:
                arbzg_warnings = arbzg_warnings + [clamp_note]
        if override:
            arbzg_warnings = arbzg_warnings + [CREDIT_OVERRIDE_IMPORT_NOTE]

        # Diesen Block für nachfolgende Zeilen am selben Tag merken
        batch_blocks_by_date.setdefault(entry_date, []).append(
            break_block_for_new(start_t, end_t, break_min, segs)
        )

        entries.append(ImportedEntry(
            date=entry_date,
            start_time=start_t,
            end_time=end_t,
            break_minutes=break_min,
            note=note,
            has_conflict=existing is not None,
            arbzg_warnings=arbzg_warnings,
            raw_start_time=raw_start_t,
            raw_end_time=raw_end_t,
            uncredited_minutes=r.uncredited_minutes,
        ))

        prev_end_dt = datetime.combine(entry_date, raw_end_t or end_t)

    if not entries:
        raise ValueError("Keine Datenzeilen im Sheet 'Zeiterfassung' gefunden")

    return entries


def execute_import(
    user_id: uuid.UUID,
    entries: list[ImportedEntry],
    overwrite: bool,
    db: Session,
    changed_by_id: uuid.UUID,
    filename: str,
    tenant_id: uuid.UUID | None = None,
) -> ImportResult:
    """
    Führt den Import durch. Bei overwrite=True werden Konflikte überschrieben,
    sonst übersprungen. Schreibt Audit-Log-Einträge.

    F-042: Fully wrapped in try/except. On any failure the whole batch
    rolls back (so the DB can't end up with half-imported rows) and a
    separate audit-log transaction is written to record the failure.
    """
    try:
        return _execute_import_inner(
            user_id=user_id,
            entries=entries,
            overwrite=overwrite,
            db=db,
            changed_by_id=changed_by_id,
            filename=filename,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        db.rollback()
        # Write a standalone failure audit log in a fresh transaction.
        try:
            failure_log = TimeEntryAuditLog(
                time_entry_id=None,
                user_id=user_id,
                changed_by=changed_by_id,
                action="import",
                source="import",
                new_note=(
                    f"XLS-Import FEHLGESCHLAGEN | Benutzer: {user_id} "
                    f"| Datei: {filename} | Fehler: {type(exc).__name__}: {exc}"[:1000]
                ),
                tenant_id=tenant_id,
            )
            db.add(failure_log)
            db.commit()
        except Exception:
            db.rollback()
        # Re-raise as ValueError so the router translates to HTTP 400 cleanly
        raise ValueError(f"Import fehlgeschlagen: {exc}") from exc


def _execute_import_inner(
    user_id: uuid.UUID,
    entries: list[ImportedEntry],
    overwrite: bool,
    db: Session,
    changed_by_id: uuid.UUID,
    filename: str,
    tenant_id: uuid.UUID | None = None,
) -> ImportResult:
    """Actual import body. Callers should use execute_import() which wraps it."""
    # Lokaler Import: ein Service greift auf den Router-Helfer zu (kein Zirkel
    # beim Laden von app.routers).
    from app.routers.admin_helpers import lock_user_row

    imported = 0
    skipped = 0
    overwritten = 0
    all_warnings: list[str] = []

    # Spec P5: Ankersperre der Zielperson EINMAL am Anfang — vor Puffer,
    # Snapshot-Auflösung und clamp, vor jeder Zeilensperre.
    lock_user_row(db, tenant_id, user_id)

    # Einmal fuer die Schleife: Ziel-Person (fuer die Kappung unten und die
    # Zusammenfassung am Ende) und der Tenant-Puffer.
    target_query = db.query(User).filter(User.id == user_id)
    if tenant_id is not None:
        target_query = target_query.filter(User.tenant_id == tenant_id)  # F-026
    target_user = target_query.first()
    grace = work_window_service.get_grace_minutes(db, tenant_id)

    for entry in entries:
        # Invariant end_time > start_time. net_hours floors a negative duration
        # to 0, so an end<=start row (over-midnight shift, or corrupt/forged
        # source — /confirm trusts client-supplied entries) would otherwise be
        # stored as a phantom 0h entry: wrong pay + it bypasses the §3 daily cap.
        # The interactive write paths reject this; the importer must too. Skip it
        # with a visible warning (over-midnight shifts are entered as two entries).
        if entry.end_time is None or entry.end_time <= entry.start_time:
            skipped += 1
            all_warnings.append(
                f"{entry.date.strftime('%d.%m.%Y')}: übersprungen — Endzeit "
                f"({entry.end_time.strftime('%H:%M') if entry.end_time else '—'}) "
                f"liegt nicht nach Startzeit ({entry.start_time.strftime('%H:%M')}). "
                f"Über-Mitternacht-Schichten als zwei Einträge erfassen."
            )
            continue

        # Release-Review 1.19.1 + Spec 7.4: NICHT den Client-Werten vertrauen.
        # /confirm nimmt die Einträge aus dem Request-Body entgegen; wo gekappt
        # wird, rechnet der Server Zeiten, raw_*, uncredited UND Auto-Pause neu,
        # und zwar aus dem Rohwert (für eine unveränderte Vorschau identisch).
        file_start = entry.raw_start_time or entry.start_time
        file_end = entry.raw_end_time or entry.end_time
        first = work_window_service.clamp(
            db, target_user, entry.date, file_start, file_end, grace, credit_override=False,
        )
        existing = _find_existing_entry(
            db, user_id, tenant_id, entry.date,
            starts=(first.eff_start, entry.start_time), raw_start=file_start,
        )
        override = bool(existing is not None and existing.credit_override)
        row_grace = (
            work_window_service.grace_for_entry(db, existing) if existing is not None else grace
        )
        # E38: ``clamp_applies`` statt „hat Blöcke" — prüft zusätzlich
        # track_hours und credit_override. Ohne Kappung bleibt ein mitgeliefertes
        # raw_* als §16-Nachweis stehen, statt von einer Kappung gelöscht zu
        # werden, die gar nicht stattfindet.
        if target_user is not None and work_window_service.clamp_applies(
            db, target_user, entry.date, credit_override=override,
        ):
            r = work_window_service.clamp(
                db, target_user, entry.date, file_start, file_end, row_grace,
                credit_override=False,
            )
            segs = work_window_service.gap_segments(
                db, target_user, entry.date, file_start, file_end, row_grace,
                credit_override=False,
            )
            eff_start, eff_end, raw_start, raw_end = r.eff_start, r.eff_end, r.raw_start, r.raw_end
            uncredited, applied_grace = r.uncredited_minutes, r.grace_minutes
            break_minutes = _calc_break_minutes(eff_start, eff_end, segs)
        else:
            eff_start, eff_end = entry.start_time, entry.end_time
            raw_start, raw_end = entry.raw_start_time, entry.raw_end_time
            uncredited, applied_grace = 0, None
            break_minutes = entry.break_minutes

        for w in entry.arbzg_warnings:
            all_warnings.append(f"{entry.date.strftime('%d.%m.%Y')}: {w}")

        if existing:
            if not overwrite:
                skipped += 1
                continue
            if eff_start != existing.start_time and _start_taken(
                db, user_id, tenant_id, entry.date, eff_start, existing.id,
            ):
                skipped += 1
                all_warnings.append(
                    f"{entry.date.strftime('%d.%m.%Y')}: übersprungen — ein anderer "
                    f"Eintrag beginnt bereits um {eff_start.strftime('%H:%M')}."
                )
                continue

            # Audit-Log: alter Zustand
            log = TimeEntryAuditLog(
                time_entry_id=existing.id,
                user_id=user_id,
                changed_by=changed_by_id,
                action="update",
                source="import",
                old_date=existing.date,
                old_start_time=existing.start_time,
                old_end_time=existing.end_time,
                old_break_minutes=existing.break_minutes,
                old_note=existing.note,
                new_date=entry.date,
                new_start_time=eff_start,
                new_end_time=eff_end,
                new_break_minutes=break_minutes,
                new_note=entry.note,
                tenant_id=tenant_id,
            )
            existing.start_time = eff_start
            existing.end_time = eff_end
            existing.break_minutes = break_minutes
            existing.note = entry.note
            # Audit R3/§16: Roh-Stempel des Import-Eintrags übernehmen, sonst
            # geht der Nachweis der tatsächlichen Anwesenheit beim Overwrite
            # verloren (gekappter Wert bliebe, Rohwert verschwände).
            existing.raw_start_time = raw_start
            existing.raw_end_time = raw_end
            existing.uncredited_minutes = uncredited
            if applied_grace is not None:
                existing.clamp_grace_minutes = applied_grace
            # P18: der Import liefert ein echtes Ende; credit_override bleibt (P3).
            existing.auto_closed = False
            db.add(log)
            overwritten += 1
        else:
            new_entry = TimeEntry(
                user_id=user_id,
                tenant_id=tenant_id,
                date=entry.date,
                start_time=eff_start,
                end_time=eff_end,
                break_minutes=break_minutes,
                note=entry.note,
                raw_start_time=raw_start,
                raw_end_time=raw_end,
                uncredited_minutes=uncredited,
                clamp_grace_minutes=applied_grace,
            )
            db.add(new_entry)
            db.flush()  # ID für Audit-Log

            log = TimeEntryAuditLog(
                time_entry_id=new_entry.id,
                user_id=user_id,
                changed_by=changed_by_id,
                action="create",
                source="import",
                new_date=entry.date,
                new_start_time=eff_start,
                new_end_time=eff_end,
                new_break_minutes=break_minutes,
                new_note=entry.note,
                tenant_id=tenant_id,
            )
            db.add(log)
            imported += 1

    # Zusammenfassungs-Eintrag im Audit-Log (action="import", time_entry_id=None)
    username = f"{target_user.first_name} {target_user.last_name}" if target_user else str(user_id)
    summary = (
        f"XLS-Import: {imported} neu, {overwritten} überschrieben, {skipped} übersprungen "
        f"| Benutzer: {username} | Datei: {filename}"
    )
    summary_log = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=user_id,
        changed_by=changed_by_id,
        action="import",
        source="import",
        new_note=summary,
        tenant_id=tenant_id,
    )
    db.add(summary_log)
    db.commit()

    return ImportResult(
        imported=imported,
        skipped=skipped,
        overwritten=overwritten,
        warnings=all_warnings,
    )
```

- [ ] **Step 4: Router `import_xls.py` — Mandant durchreichen (F-026)**

In `preview_import` die Zeile `entries = parse_xls(content, user_id, db)` ersetzen durch:

```python
        entries = parse_xls(content, user_id, db, tenant_id=current_admin.tenant_id)
```

- [ ] **Step 5: Bestandstests auf die neuen Pflichtparameter umstellen**

```bash
python3 - backend/tests/test_xls_import_service.py <<'PYEOF'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = re.sub(r"_calc_break_minutes\((time\(\d+, \d+\)), (time\(\d+, \d+\))\)",
              r"_calc_break_minutes(\1, \2, [])", path.read_text(encoding="utf-8"))
lines, out, i = text.split("\n"), [], 0
while i < len(lines):
    line = lines[i]
    if "_check_arbzg(" in line and "import" not in line and not line.strip().startswith("_check_arbzg,"):
        call, depth, j = [line], line.count("(") - line.count(")"), i
        while depth > 0:
            j += 1
            call.append(lines[j])
            depth += lines[j].count("(") - lines[j].count(")")
        joined = "\n".join(call)
        k = joined.rfind(")")
        head = joined[:k].rstrip()
        joined = head + ("" if head.endswith(",") else ",") + " uncredited_segments=[]" + joined[k:]
        out.extend(joined.split("\n"))
        i = j + 1
        continue
    out.append(line)
    i += 1
path.write_text("\n".join(out), encoding="utf-8")
PYEOF
grep -c "uncredited_segments=\[\]" backend/tests/test_xls_import_service.py
grep -c ", \[\]) ==" backend/tests/test_xls_import_service.py
```

Expected: `9` und `5`.

- [ ] **Step 6: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_xls_blocks.py tests/test_write_path_locks.py tests/test_xls_import_service.py -q -p no:cacheprovider`
Expected: PASS (64 Tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/xls_import_service.py backend/app/routers/import_xls.py backend/tests/test_xls_blocks.py backend/tests/test_xls_import_service.py backend/tests/test_write_path_locks.py
git commit -F - <<'EOF'
feat(bloecke): XLS-Import mit clamp_applies, Auto-Pause-Rest, gespeichertem Puffer und Mandantenfilter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 11: Benutzer-API — Altfelder 400, `work_blocks` gesperrt, lockere Leseschemas, `work_blocks_today` (E26–E29, 11.1, 11.4, 11.5)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#491 API-2, gemergt in `3d46c2f`: `admin_users.update_user` sperrt bei Rollenwechsel über `lock_active_admins_and_user`, `deactivate_user`/`reactivate_user` über `_lock_and_reload` — die Eingriffe dieses Tasks liegen außerhalb dieser Blöcke, aber die Zeilennummern sind verschoben; maßgeblich sind die zitierten Anker.)

**Files:**
- Modify: `backend/app/schemas/validators.py:14-21, 48-58`
- Modify: `backend/app/schemas/user.py` (Importe, `UserBase` 58-72, `UserCreate` 89-96, `UserUpdate` 175-189, `UserResponse` 222-223, `UserListResponse` 263-273)
- Modify: `backend/app/services/calculation_service.py` (Logger, `attach_work_blocks_today`)
- Modify: `backend/app/routers/admin_users.py` (`LEGACY_WINDOW_FIELDS_DETAIL`, `list_users`, `get_user`, `create_user`, `update_user`)
- Modify: `backend/app/routers/auth.py:298-303` (Login), `backend/app/routers/impersonation.py:89-93`
- Modify: `backend/tests/test_endpoints.py` (Klasse `TestScheduledWindowRoundtrip`, `test_inverted_scheduled_window_rejected`)
- Test (neu): `backend/tests/test_users_api_work_blocks.py`

**Interfaces:**
- Consumes: `calculation_service.get_blocks_json_for_date(db, user, target_date, wh_changes=None) -> Optional[list]` (Task 2); `tests.work_blocks_fixtures.legacy_week` (Task 1)
- Produces:
  - `app.schemas.validators.LEGACY_WINDOW_FIELD_PREFIX = "scheduled_"`
  - `app.schemas.validators.strip_legacy_window_fields(data: Any) -> Any` (Kern des `before`-Validators)
  - `app.schemas.validators.validate_employment_order(model: Any) -> Any` (ersetzt `validate_employment_and_window_order`; `SCHEDULED_WINDOW_PAIRS` entfällt)
  - `UserCreate.legacy_window_fields_sent: bool = Field(False, exclude=True)`, `UserUpdate.legacy_window_fields_sent` (dito), `UserUpdate.work_blocks: Optional[Any] = None` (nur deklariert, damit die Sperre greift)
  - `UserResponse.work_blocks: Optional[Any] = None`, `UserResponse.work_blocks_today: Optional[Any] = None`, dieselben zwei Felder auf `UserListResponse`; `UserBase`/`UserUpdate`/`UserListResponse` ohne `scheduled_*`
  - `app.routers.admin_users.LEGACY_WINDOW_FIELDS_DETAIL: str` (Wortlaut Spec 11.4)
  - `calculation_service.attach_work_blocks_today(db: Session, users: Sequence[User], on_date: date) -> None` — setzt das transiente Attribut `work_blocks_today` (EIN Preload der Verlaufszeilen, F-026-gefiltert; strukturell kaputtes JSON → `None` + Log, nie 500)
  - `PUT /api/admin/users/{id}`: 400 bei `work_blocks` (in `_HISTORISED_FIELDS`) und bei jedem Schlüssel mit Präfix `scheduled_`; `POST /api/admin/users`: 400 bei Präfix `scheduled_`
  - `GET /api/admin/users`, `GET /api/admin/users/{id}`, Anlege-/Bearbeiten-Antwort, Login, Impersonation: `work_blocks` + `work_blocks_today`

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_users_api_work_blocks.py`:

```python
"""Spec 2026-10-08, 11.1/11.4/11.5 (PR1): Benutzer-API und Arbeitszeit-Blöcke.

* Altfelder ``scheduled_*`` → 400 „Bitte Seite neu laden" (E26), erkannt am Präfix.
* ``work_blocks`` per PUT → 400 (E27, genau ein Schreibweg).
* Leseschemas LOCKER (E29): Altwerte wie 07:37 oder der Platzhalter 23:59
  dürfen weder Login noch Benutzerliste in einen HTTP 500 verwandeln.
* ``work_blocks_today`` ist datumsaufgelöst (11.1) — eine zukunftsdatierte
  Verlaufszeile wirkt heute noch nicht.
"""
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_db
from app.models import WorkingHoursChange
from app.routers.admin_users import LEGACY_WINDOW_FIELDS_DETAIL
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_user, endpoints_app, tenant,
)
from tests.work_blocks_fixtures import legacy_week

# 07:37 (kein 5-Minuten-Raster) und der Platzhalter 23:59 aus Migration 073.
ODD = legacy_week(mon=("07:37", "16:30"), fri=("07:30", None))
LATER = legacy_week(mon=("09:00", "17:00"))
NEW_USER = {
    "username": "neu", "first_name": "Neu", "last_name": "Person", "weekly_hours": 40.0,
    "vacation_days": 30, "work_days_per_week": 5, "password": "NeuPerson2025!",
}


def test_legacy_detail_text_is_the_spec_text():
    assert LEGACY_WINDOW_FIELDS_DETAIL == (
        "Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) "
        "wurden durch Arbeitszeit-Blöcke ersetzt."
    )


def test_put_with_work_blocks_is_400(admin_client, employee_user):
    resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={"work_blocks": ODD})
    assert resp.status_code == 400, resp.text
    assert "Arbeitszeit-Blöcke" in resp.json()["detail"]


def test_put_with_legacy_prefix_is_400_and_changes_nothing(admin_client, employee_user, _db_session):
    resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={
        "first_name": "Neu", "scheduled_start_monday": "08:00"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == LEGACY_WINDOW_FIELDS_DETAIL
    _db_session.refresh(employee_user)
    assert employee_user.first_name == "Max"


def test_post_with_legacy_prefix_is_400(admin_client):
    resp = admin_client.post("/api/admin/users", json={**NEW_USER, "scheduled_end_friday": "15:00"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == LEGACY_WINDOW_FIELDS_DETAIL


def test_post_without_legacy_fields_has_no_window_keys(admin_client):
    resp = admin_client.post("/api/admin/users", json=NEW_USER)
    assert resp.status_code == 201, resp.text
    body = resp.json()["user"]
    assert [k for k in body if k.startswith("scheduled_")] == []
    assert body["work_blocks"] is None
    assert body["work_blocks_today"] is None


def test_list_and_get_resolve_work_blocks_today(admin_client, employee_user, _db_session):
    employee_user.work_blocks = ODD
    _db_session.add(WorkingHoursChange(
        user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=today_local() + timedelta(days=1), weekly_hours=40,
        use_daily_schedule=False, work_days_per_week=5, blocks=LATER,
    ))
    _db_session.commit()
    listed = next(u for u in admin_client.get("/api/admin/users").json()
                  if u["id"] == str(employee_user.id))
    assert listed["work_blocks"] == ODD
    assert listed["work_blocks_today"] == ODD  # die Zeile ab morgen wirkt heute nicht
    single = admin_client.get(f"/api/admin/users/{employee_user.id}")
    assert single.status_code == 200, single.text
    assert single.json()["work_blocks_today"] == ODD


def test_structurally_broken_blocks_do_not_break_the_list(admin_client, employee_user, _db_session):
    employee_user.work_blocks = [{"blocks": "kaputt", "pause_minutes": None}] * 5
    _db_session.commit()
    resp = admin_client.get("/api/admin/users")
    assert resp.status_code == 200, resp.text
    listed = next(u for u in resp.json() if u["id"] == str(employee_user.id))
    assert listed["work_blocks_today"] is None


def test_login_with_legacy_blocks_is_200(_db_session, employee_user):
    employee_user.work_blocks = ODD
    _db_session.commit()

    def _override_db():
        yield _db_session

    endpoints_app.dependency_overrides[get_db] = _override_db
    try:
        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(endpoints_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "employee", "password": "Employee2025!"})
    finally:
        endpoints_app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["work_blocks"] == ODD
    assert resp.json()["user"]["work_blocks_today"] == ODD
```

In `backend/tests/test_endpoints.py` die Klasse `TestScheduledWindowRoundtrip` (beide Tests) vollständig ersetzen durch:

```python
class TestLegacyWindowFieldsRejected:
    """Spec 2026-10-08, 11.4 (E26): die mit Migration 073 entfallenen #201-Felder
    lehnt die Benutzer-API mit 400 ab — ein gecachtes altes Frontend darf nicht
    „gespeichert" melden, ohne zu speichern."""

    def test_post_with_legacy_window_fields_is_400(self, admin_client, _db_session):
        resp = admin_client.post("/api/admin/users", json={
            "username": "win",
            "first_name": "Win",
            "last_name": "Dow",
            "weekly_hours": 40.0,
            "vacation_days": 30,
            "work_days_per_week": 5,
            "password": "WindowPass2025!",
            "scheduled_start_monday": "08:00",
            "scheduled_end_monday": "17:00",
        })
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Bitte Seite neu laden")
        assert _db_session.query(User).filter(User.username == "win").first() is None

    def test_put_with_legacy_window_fields_is_400(self, admin_client, employee_user, _db_session):
        resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={
            "scheduled_start_friday": "09:00",
            "scheduled_end_friday": "15:00",
        })
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Bitte Seite neu laden")
```

und in `TestAdminSettings` den Test `test_inverted_scheduled_window_rejected` ersetzen durch:

```python
    def test_inverted_legacy_window_is_rejected_as_legacy_field(self, admin_client):
        """#201 → Spec 11.4: auch ein (invertiertes) Altfenster ist ein Altfeld → 400."""
        resp = admin_client.post("/api/admin/users", json={
            "username": "inv", "first_name": "In", "last_name": "V", "weekly_hours": 40.0,
            "vacation_days": 30, "work_days_per_week": 5, "password": "InvWindow2025!",
            "scheduled_start_monday": "18:00", "scheduled_end_monday": "08:00"})
        assert resp.status_code == 400, resp.text
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_users_api_work_blocks.py tests/test_endpoints.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'LEGACY_WINDOW_FIELDS_DETAIL'`; in `test_endpoints.py` die drei umgestellten Tests (201/200/422 statt 400).

- [ ] **Step 3: `schemas/validators.py`**

`SCHEDULED_WINDOW_PAIRS` samt Kommentar ersetzen durch:

```python
# Spec 2026-10-08 (11.4/E26): Präfix der mit Migration 073 entfallenen
# Fensterfelder. Erkannt wird NUR das Präfix — die vollen Feldnamen dürfen in
# app/ nicht mehr vorkommen (Guard-Test test_no_scheduled_columns.py).
LEGACY_WINDOW_FIELD_PREFIX = "scheduled_"
```

`validate_employment_and_window_order` ersetzen durch:

```python
def validate_employment_order(model: Any) -> Any:
    """Erster < letzter Arbeitstag (#193). Die Soll-Fenster-Prüfung (#201)
    entfällt mit Migration 073 — Blöcke werden im Verlauf validiert (PR3)."""
    if model.first_work_day and model.last_work_day:
        if model.first_work_day >= model.last_work_day:
            raise ValueError("Erster Arbeitstag muss vor dem letzten Arbeitstag liegen")
    return model


def strip_legacy_window_fields(data: Any) -> Any:
    """``model_validator(mode="before")``-Kern für UserCreate/UserUpdate (E26).

    Ein gecachtes altes Frontend schickt die entfallenen Fensterfelder bei
    jedem Speichern. Pydantic verwürfe sie still — der Router meldete dann
    „gespeichert", ohne zu speichern. Stattdessen werden sie entfernt und das
    nie serialisierte Feld ``legacy_window_fields_sent`` gesetzt; der Router
    antwortet daraufhin mit 400 „Bitte Seite neu laden"."""
    if isinstance(data, dict) and any(
        isinstance(key, str) and key.startswith(LEGACY_WINDOW_FIELD_PREFIX) for key in data
    ):
        data = {
            key: value for key, value in data.items()
            if not (isinstance(key, str) and key.startswith(LEGACY_WINDOW_FIELD_PREFIX))
        }
        data["legacy_window_fields_sent"] = True
    return data
```

- [ ] **Step 4: `schemas/user.py`**

Importe:

```python
from typing import Any, Optional
from datetime import datetime, date
```

```python
from app.schemas.validators import strip_legacy_window_fields, validate_employment_order
```

In `UserBase` den Block „# #201: Soll-Zeitfenster pro Wochentag" (zehn `scheduled_*`-Felder) löschen und den Validator auf den neuen Namen stellen:

```python
    @model_validator(mode='after')
    def check_work_day_order(self):
        return validate_employment_order(self)  # #219: shared
```

`UserCreate` — direkt nach `role: UserRole = UserRole.EMPLOYEE` einfügen (der bestehende `check_daily_schedule_matches_weekly_hours` bleibt):

```python
    # Spec 11.4 (E26): gesetzt vom before-Validator, nie serialisiert.
    legacy_window_fields_sent: bool = Field(False, exclude=True)

    @model_validator(mode='before')
    @classmethod
    def reject_legacy_window_fields(cls, data):
        return strip_legacy_window_fields(data)
```

`UserUpdate` — den Block „# #201: Soll-Zeitfenster pro Wochentag" (zehn Felder) und den alten `check_work_day_order` ersetzen durch:

```python
    # E27: nur deklariert, damit die Sperre in update_user greift (400) —
    # Blöcke haben genau EINEN Schreibweg, den Verlauf mit Wirkungsdatum.
    work_blocks: Optional[Any] = None
    # Spec 11.4 (E26): gesetzt vom before-Validator, nie serialisiert.
    legacy_window_fields_sent: bool = Field(False, exclude=True)

    @model_validator(mode='before')
    @classmethod
    def reject_legacy_window_fields(cls, data):
        return strip_legacy_window_fields(data)

    @model_validator(mode='after')
    def check_work_day_order(self):
        return validate_employment_order(self)  # #219: shared
```

`UserResponse` — nach `vacation_carryover_deadline: Optional[date] = None`:

```python
    # Spec E29/11.5: Leseschema LOCKER (kein Validator) — Altwerte wie 07:37 oder
    # 23:59 dürfen Login und Listen nie in einen HTTP 500 verwandeln.
    work_blocks: Optional[Any] = None
    # Spec 11.1: datumsaufgelöst für heute (calculation_service.attach_work_blocks_today);
    # ohne Aufruf None.
    work_blocks_today: Optional[Any] = None
```

`UserListResponse` — den Block „# #201: Soll-Zeitfenster pro Wochentag" (zehn Felder) ersetzen durch:

```python
    # Spec E29/11.5: locker, siehe UserResponse.
    work_blocks: Optional[Any] = None
    work_blocks_today: Optional[Any] = None
```

- [ ] **Step 5: `calculation_service.attach_work_blocks_today`**

Ganz oben `import logging` ergänzen, nach den Importen:

```python
logger = logging.getLogger(__name__)
```

Nach `get_blocks_json_for_date` einfügen:

```python
def attach_work_blocks_today(db: Session, users, on_date: date) -> None:
    """Spec 11.1 ``work_blocks_today``: hängt die für ``on_date`` aufgelösten
    Blöcke als transientes Attribut an jede User-Instanz — die Leseschemas
    lesen es per ``from_attributes``. EIN Preload der Verlaufszeilen für alle
    übergebenen Personen (Muster #449/#204).

    Locker wie ein Leseschema (E29): strukturell kaputtes JSON (nur per Hand in
    der Datenbank erzeugbar) wird als ``None`` angezeigt und geloggt, statt
    Login oder Benutzerliste mit HTTP 500 zu sperren."""
    users = [u for u in users if u is not None]
    if not users:
        return
    tenant_ids = sorted({u.tenant_id for u in users if u.tenant_id is not None}, key=str)
    by_user: dict = {}
    for row in db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id.in_([u.id for u in users]),
        WorkingHoursChange.tenant_id.in_(tenant_ids),  # F-026
    ).all():
        by_user.setdefault(row.user_id, []).append(row)
    for user in users:
        try:
            user.work_blocks_today = get_blocks_json_for_date(
                db, user, on_date, by_user.get(user.id, []))
        except ValueError:
            logger.warning("work_blocks_today: Blöcke von Benutzer %s nicht lesbar", user.id)
            user.work_blocks_today = None
```

- [ ] **Step 6: `admin_users.py`**

Direkt vor `LAST_ADMIN_DETAIL = (`:

```python
# Spec 11.4 (E26): ein gecachtes altes Frontend schickt die entfallenen
# Fensterfelder bei jedem Speichern mit.
LEGACY_WINDOW_FIELDS_DETAIL = (
    "Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) "
    "wurden durch Arbeitszeit-Blöcke ersetzt."
)
```

`list_users` — vor `return users`:

```python
    # Spec 11.1: EIN Preload der Verlaufszeilen für alle gelisteten Personen.
    calculation_service.attach_work_blocks_today(db, users, today_local())
```

`get_user` — der Rumpf wird:

```python
    user = _get_user_in_tenant(db, user_id, current_user)
    calculation_service.attach_work_blocks_today(db, [user], today_local())
    return user
```

`create_user` — erste Anweisung im Rumpf:

```python
    if user_data.legacy_window_fields_sent:
        raise HTTPException(status_code=400, detail=LEGACY_WINDOW_FIELDS_DETAIL)
```

im `User(...)`-Konstruktor die zehn Zeilen `scheduled_start_monday=user_data.scheduled_start_monday,` … `scheduled_end_friday=user_data.scheduled_end_friday,` löschen und vor dem `return UserCreateResponse(` einfügen:

```python
    calculation_service.attach_work_blocks_today(db, [new_user], today_local())
```

`update_user` — erste Anweisung im Rumpf (vor `_get_user_in_tenant`):

```python
    if user_data.legacy_window_fields_sent:
        raise HTTPException(status_code=400, detail=LEGACY_WINDOW_FIELDS_DETAIL)
```

`_HISTORISED_FIELDS` samt Meldung ersetzen (der Knopf heißt bis PR3 noch „Wochenstunden anpassen"):

```python
    _HISTORISED_FIELDS = (
        'weekly_hours', 'use_daily_schedule', 'work_days_per_week',
        'hours_monday', 'hours_tuesday', 'hours_wednesday',
        'hours_thursday', 'hours_friday',
        # Spec E27: Blöcke gehören zum Vertrags-Snapshot.
        'work_blocks',
    )
    if any(f in update_data for f in _HISTORISED_FIELDS):
        raise HTTPException(
            status_code=400,
            detail=(
                "Wochenstunden, Tagesstunden, Arbeitstage und Arbeitszeit-Blöcke "
                "werden über „Wochenstunden anpassen“ mit Wirkungsdatum geändert, "
                "damit Historie und Soll vergangener Monate korrekt bleiben."
            ),
        )
```

die Schleife `for _wd, _label in (('monday', 'Montag'), …): _s, _e = _eff(f'scheduled_start_{_wd}'), …` (sieben Zeilen bis einschließlich `detail=f"{_label}: Soll-Beginn muss vor dem Soll-Ende liegen.",` und den schließenden Klammern) löschen; im Kommentar darüber „Beschäftigungsfenster und Soll-Zeit-Fenster ebenfalls" → „Beschäftigungsfenster ebenfalls" und „`validate_employment_and_window_order` im Schema" → „`validate_employment_order` im Schema". Vor dem abschließenden `return user`:

```python
    calculation_service.attach_work_blocks_today(db, [user], today_local())
```

- [ ] **Step 7: Login und Impersonation**

`backend/app/routers/auth.py`, nach `security_logger.info("AUTH login_success user=%s", username_lower)`:

```python
    # Spec 11.1: heute gültige Blöcke (locker, E29 — nie ein 500 im Login).
    from app.services import calculation_service
    from app.services.timezone_service import today_local
    calculation_service.attach_work_blocks_today(db, [user], today_local())
```

`backend/app/routers/impersonation.py`, direkt vor `return {"access_token": token, …}` in `start_impersonation`:

```python
    # Spec 11.1: wie der Login.
    from app.services import calculation_service
    from app.services.timezone_service import today_local
    calculation_service.attach_work_blocks_today(db, [target], today_local())
```

- [ ] **Step 8: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_users_api_work_blocks.py tests/test_endpoints.py tests/test_impersonation.py tests/test_user_create_daily_schedule_validation.py tests/test_user_fixed_mode_validation.py -q -p no:cacheprovider`
Expected: PASS

Kontrolle: `grep -rn "scheduled_start_\|scheduled_end_" backend/app` zeigt nur noch `backend/app/models/user.py` (die Spalten fallen in Task 13).

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas backend/app/services/calculation_service.py backend/app/routers/admin_users.py backend/app/routers/auth.py backend/app/routers/impersonation.py backend/tests/test_users_api_work_blocks.py backend/tests/test_endpoints.py
git commit -F - <<'EOF'
feat(bloecke): Benutzer-API lehnt Altfenster-Felder mit 400 ab, liefert work_blocks und work_blocks_today

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 12: Verlauf — Altfenster laufen in neuen Zeilen weiter, Basis-Zeile friert sie ein, User-Spiegel (P2, P24, E8, E9, 3.3)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (`admin_users.py` durch #491 API-2 verschoben, siehe Task 11; `_sync_user_from_change`, `create_working_hours_change` und die Vorschau sind unverändert.)

**Files:**
- Modify: `backend/app/routers/admin_users.py` (Import, `_comparable_snapshot` 155-177, neu `_carried_blocks`, `_sync_user_from_change` 228-261, `create_working_hours_change` 1475-1597, `preview_working_hours_change` 1802-1950)
- Modify: `backend/app/schemas/working_hours_change.py:59-69` (`WorkingHoursChangeResponse.blocks`)
- Test (neu): `backend/tests/test_wh_change_legacy_blocks.py`

**Interfaces:**
- Consumes: `calculation_service.Schedule` mit `blocks`/`block_pauses`, `get_schedule_for_date` (Task 2); `work_blocks_service.ParsedWeek`, `is_legacy_week`, `week_blocks_to_json`, `parse_week_blocks` (Task 1); `work_window_service.clamp` (Task 3)
- Produces (in `app.routers.admin_users`):
  - `_comparable_snapshot(weekly_hours, use_daily_schedule, day_hours, work_days_per_week, blocks: Optional[tuple], block_pauses: Optional[tuple]) -> tuple` — Blöcke/Pausen im Schedule-Format sind Teil des Vergleichs (PR3 nutzt ihn für reine Blockänderungen)
  - `_carried_blocks(predecessor: calculation_service.Schedule) -> tuple[Optional[tuple], Optional[tuple]]` — P2/P24: Altfenster des Vorgänger-Snapshots wird übernommen, neue Blöcke (Pause gesetzt) nicht
  - `_sync_user_from_change(user, most_recent)` spiegelt zusätzlich `user.work_blocks = copy.deepcopy(most_recent.blocks)` (E9)
  - Basis-Zeile (`create_working_hours_change`) trägt `blocks` des eingefrorenen Snapshots; neue Zeile und Vorschau-Zeile tragen `_carried_blocks(...)` als JSON
  - `WorkingHoursChangeResponse.blocks: Optional[Any] = None` (locker, nur Leseschema — **nicht** auf `WorkingHoursChangeBase`, sonst erbte das Create-Schema ein ungeprüftes Eingabefeld)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_wh_change_legacy_blocks.py`:

```python
"""Spec 2026-10-08 (PR1): Verlauf und Altfenster — P2, E8, E9, 3.3.

Bis PR3 kennt der Dialog keine Blöcke. Eine Wochenstunden-Änderung für eine
Person mit Altfenster muss die Kappung ab dem Wirkungsdatum deshalb
UNVERÄNDERT weiterlaufen lassen (P2: Übernahme aus dem Vorgänger-Snapshot),
die Basis-Zeile friert das Fenster der Vergangenheit ein (E8), und die
User-Zeile spiegelt die jüngste Zeile ≤ heute (E9).
"""
from datetime import date, time
from decimal import Decimal

from app.models import WorkingHoursChange
from app.routers.admin_users import _carried_blocks, _comparable_snapshot
from app.services import calculation_service, work_blocks_service
from app.services import work_window_service as wws
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, legacy_week

LEGACY = legacy_week(mon=("08:00", "17:00"))
LEGACY_LATER = legacy_week(mon=("09:00", "17:00"))
EFFECTIVE = date(2026, 6, 1)   # Montag, in der Vergangenheit
EARLIER_MON = date(2026, 5, 25)
LATER_MON = date(2026, 6, 8)


def _row(db, user, effective_from, blocks, weekly_hours=40):
    row = WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=effective_from,
        weekly_hours=weekly_hours, use_daily_schedule=False, work_days_per_week=5,
        blocks=blocks,
    )
    db.add(row)
    db.commit()
    return row


def _rows(db, user):
    return (
        db.query(WorkingHoursChange)
        .filter(WorkingHoursChange.user_id == user.id,
                WorkingHoursChange.tenant_id == DEFAULT_TENANT_ID)
        .order_by(WorkingHoursChange.effective_from)
        .all()
    )


def _post(client, user, effective_from, weekly_hours):
    return client.post(f"/api/admin/users/{user.id}/working-hours-changes", json={
        "effective_from": effective_from.isoformat(), "weekly_hours": weekly_hours})


# Review Focus 4: neue Wochenstunden-Änderung für eine Person mit Altfenster.
def test_change_carries_legacy_window_and_freezes_the_past(_db_session, employee_user, admin_client):
    employee_user.work_blocks = LEGACY
    _db_session.commit()
    resp = _post(admin_client, employee_user, EFFECTIVE, 30)
    assert resp.status_code == 201, resp.text
    assert resp.json()["blocks"] == LEGACY
    rows = _rows(_db_session, employee_user)
    assert [r.effective_from for r in rows] == [date(2026, 5, 31), EFFECTIVE]  # Basis-Zeile + neue
    assert [r.blocks for r in rows] == [LEGACY, LEGACY]
    _db_session.refresh(employee_user)
    assert employee_user.work_blocks == LEGACY
    for d in (EARLIER_MON, LATER_MON):
        r = wws.clamp(_db_session, employee_user, d, time(7, 0), time(18, 0), 15,
                      credit_override=False)
        assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == (
            time(7, 45), time(17, 15), time(7, 0), time(18, 0)), d


def test_inserted_row_takes_window_of_its_predecessor(_db_session, employee_user, admin_client):
    """Spec 4.3: eine Zeile zwischen eine mit und eine ohne Fenster eingefügt
    übernimmt das Fenster; die Folgezeile bleibt ohne."""
    employee_user.work_blocks = None
    _row(_db_session, employee_user, date(2026, 1, 1), LEGACY)
    _row(_db_session, employee_user, date(2026, 9, 1), None)
    resp = _post(admin_client, employee_user, date(2026, 5, 4), 30)
    assert resp.status_code == 201, resp.text
    assert [(r.effective_from, r.blocks) for r in _rows(_db_session, employee_user)] == [
        (date(2026, 1, 1), LEGACY), (date(2026, 5, 4), LEGACY), (date(2026, 9, 1), None)]


def test_new_blocks_end_with_a_change_without_blocks(_db_session, employee_user, admin_client):
    """P24: neue Blöcke (Pause gesetzt) laufen NICHT in eine Zeile des Modus
    „Gleichmäßig" hinein; die Vorgängerzeile behält ihre Blöcke."""
    _row(_db_session, employee_user, date(2026, 1, 1), K_BLOCKS)
    resp = _post(admin_client, employee_user, date(2026, 5, 4), 30)
    assert resp.status_code == 201, resp.text
    assert [r.blocks for r in _rows(_db_session, employee_user)] == [K_BLOCKS, None]


def test_delete_resyncs_the_user_mirror(_db_session, employee_user, admin_client):
    _row(_db_session, employee_user, date(2026, 1, 1), LEGACY)
    later = _row(_db_session, employee_user, date(2026, 6, 1), LEGACY_LATER, weekly_hours=30)
    employee_user.work_blocks = LEGACY_LATER
    _db_session.commit()
    resp = admin_client.delete(f"/api/admin/users/{employee_user.id}/working-hours-changes/{later.id}")
    assert resp.status_code in (200, 204), resp.text
    _db_session.refresh(employee_user)
    assert employee_user.work_blocks == LEGACY


def test_list_returns_blocks(_db_session, employee_user, admin_client):
    _row(_db_session, employee_user, date(2026, 1, 1), LEGACY)
    listed = admin_client.get(f"/api/admin/users/{employee_user.id}/working-hours-changes").json()
    assert [r["blocks"] for r in listed] == [LEGACY]


def test_carried_blocks_rule():
    legacy = work_blocks_service.parse_week_blocks(LEGACY)
    new = work_blocks_service.parse_week_blocks(K_BLOCKS)

    def schedule(parsed):
        return calculation_service.Schedule(
            weekly_hours=Decimal("40"), use_daily_schedule=False, day_hours=(None,) * 5,
            work_days_per_week=5,
            blocks=parsed.blocks if parsed else None,
            block_pauses=parsed.pauses if parsed else None,
        )

    assert _carried_blocks(schedule(legacy)) == (legacy.blocks, legacy.pauses)
    assert _carried_blocks(schedule(new)) == (None, None)
    assert _carried_blocks(schedule(None)) == (None, None)


def test_comparable_snapshot_sees_blocks():
    legacy = work_blocks_service.parse_week_blocks(LEGACY)
    plain = _comparable_snapshot(40, False, (None,) * 5, 5, None, None)
    assert plain == _comparable_snapshot(40.0, False, (None,) * 5, 5, None, None)
    assert plain != _comparable_snapshot(40, False, (None,) * 5, 5, legacy.blocks, legacy.pauses)
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_legacy_blocks.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name '_carried_blocks'`.

- [ ] **Step 3: Vergleich und Übernahmeregel (`admin_users.py`)**

Importe: `import copy` zu den Modul-Importen; die Zeile `from app.services import auth_service, calculation_service, lifecycle_service, milog_service, settings_service` um `, work_blocks_service` erweitern.

`_comparable_snapshot` — Signatur und Rückgabe:

```python
def _comparable_snapshot(weekly_hours, use_daily_schedule, day_hours, work_days_per_week,
                         blocks, block_pauses):
```

```python
    use_daily_schedule = bool(use_daily_schedule)
    return (
        Decimal(str(weekly_hours)),
        use_daily_schedule,
        tuple(
            None if v is None else Decimal(str(v)) for v in day_hours
        ) if use_daily_schedule else (None,) * 5,
        int(work_days_per_week),
        # Spec 2026-10-08 (3.3/11.3): Blöcke und Pausen gehören zum Snapshot.
        # Beide kommen im Schedule-Format (bereits normalisiert: None == fünf
        # leere Tage), Pausen nur, wenn es Blöcke gibt.
        blocks,
        block_pauses if blocks is not None else None,
    )
```

Direkt danach einfügen:

```python
def _carried_blocks(predecessor: "calculation_service.Schedule") -> tuple:
    """P2/P24: welche Blöcke eine NEUE Verlaufszeile erbt, solange der Dialog
    keine Blöcke kennt — aus dem VOR der Änderung für ``effective_from``
    gültigen Snapshot (Vorgängerzeile bzw. Rückfall ``users.work_blocks``).

    Ein Altfenster (``pause_minutes`` NULL) läuft weiter; ohne diese Übernahme
    schaltete jede Wochenstunden-Änderung die Kappung still ab. Neue Blöcke
    (Pause gesetzt) enden mit einem Wechsel nach „Gleichmäßig"/„Nach Tagen".
    Rückgabe ``(blocks, block_pauses)`` im Schedule-Format."""
    parsed = (
        None if predecessor.blocks is None
        else work_blocks_service.ParsedWeek(predecessor.blocks, predecessor.block_pauses)
    )
    if work_blocks_service.is_legacy_week(parsed):
        return predecessor.blocks, predecessor.block_pauses
    return None, None
```

`_sync_user_from_change` — am Ende:

```python
    # Spec E9: Spiegel der jüngsten Zeile ≤ heute — als KOPIE (eine geteilte
    # Liste würde eine spätere In-place-Änderung in beide Zeilen tragen).
    user.work_blocks = copy.deepcopy(most_recent.blocks)
```

- [ ] **Step 4: `create_working_hours_change`**

Direkt nach `norm = _normalise_schedule_input(change_data, user)`:

```python
    # P2 (Spec 2.10): Blöcke aus dem VOR der Änderung für effective_from
    # gültigen Snapshot — vor dem Anlegen der neuen Zeile aufgelöst.
    _new_blocks, _new_pauses = _carried_blocks(
        calculation_service.get_schedule_for_date(db, user, change_data.effective_from)
    )
```

Den Vergleich für die Basis-Zeile ersetzen:

```python
    if _current is not None and _comparable_snapshot(
        _current.weekly_hours, _current.use_daily_schedule,
        _current.day_hours, _current.work_days_per_week,
        _current.blocks, _current.block_pauses,
    ) != _comparable_snapshot(
        norm.weekly_hours, norm.use_daily_schedule,
        norm.day_hours, norm.work_days_per_week,
        _new_blocks, _new_pauses,
    ):
```

In der Basis-Zeile (`db.add(WorkingHoursChange(... note="Automatisch erfasster Ausgangswert …"))`) nach `work_days_per_week=_current.work_days_per_week,`:

```python
            # E8: die Basis-Zeile friert auch die Blöcke der Vergangenheit ein.
            blocks=work_blocks_service.week_blocks_to_json(_current.blocks, _current.block_pauses),
```

In der neuen Zeile (`change = WorkingHoursChange(...)`) nach `work_days_per_week=norm.work_days_per_week,`:

```python
        blocks=work_blocks_service.week_blocks_to_json(_new_blocks, _new_pauses),
```

- [ ] **Step 5: `preview_working_hours_change`**

Nach `current_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)`:

```python
    _new_blocks, _new_pauses = _carried_blocks(current_schedule)  # P2, wie der Schreibpfad
```

Im `calculation_service.Schedule(...)` (Task 2 setzte dort vorläufig `blocks=current_schedule.blocks, block_pauses=current_schedule.block_pauses`) diese beiden Zeilen ersetzen durch:

```python
            blocks=_new_blocks,
            block_pauses=_new_pauses,
```

`snapshot_unchanged` ersetzen:

```python
    snapshot_unchanged = norm is not None and _comparable_snapshot(
        current_schedule.weekly_hours, current_schedule.use_daily_schedule,
        current_schedule.day_hours, current_schedule.work_days_per_week,
        current_schedule.blocks, current_schedule.block_pauses,
    ) == _comparable_snapshot(
        norm.weekly_hours, norm.use_daily_schedule,
        norm.day_hours, norm.work_days_per_week,
        _new_blocks, _new_pauses,
    )
```

In `temp_change = WorkingHoursChange(...)` nach `work_days_per_week=norm.work_days_per_week,`:

```python
                blocks=work_blocks_service.week_blocks_to_json(_new_blocks, _new_pauses),
```

- [ ] **Step 6: `WorkingHoursChangeResponse.blocks`**

`backend/app/schemas/working_hours_change.py` — `from typing import Any, List, Optional`; in `WorkingHoursChangeResponse` nach `warning: Optional[str] = None`:

```python
    # Spec 11.1/11.5: Blöcke der Zeile, LOCKER (kein Validator — Altzeilen aus
    # Migration 073 tragen 07:37/23:59). Bewusst nicht auf WorkingHoursChangeBase:
    # das Create-Schema erbte sonst ein ungeprüftes Eingabefeld (PR3 typisiert es).
    blocks: Optional[Any] = None
```

- [ ] **Step 7: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_legacy_blocks.py tests/test_wh_change_preview.py tests/test_absence_raw_hours.py tests/test_449_schedule_preload.py -q -p no:cacheprovider`
Expected: PASS

Danach die volle SQLite-Suite (Global Constraints); Expected: keine neuen Fehlschläge — insbesondere die #415-/#431-Suiten (`test_415_*`, `test_wh_change_*`, `test_retarget_absence_hours.py`) unverändert grün, weil Personen ohne Fenster `blocks = None` tragen und der Vergleich für sie unverändert bleibt.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/admin_users.py backend/app/schemas/working_hours_change.py backend/tests/test_wh_change_legacy_blocks.py
git commit -F - <<'EOF'
feat(bloecke): Altfenster laufen in neuen Verlaufszeilen weiter, Basis-Zeile und User-Spiegel tragen Blöcke

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 13: Migration 073, Spalten-Drop im Modell, Guard-Tests (Spec 5, E19–E24, 17.1, 17.6)

**Files:**
- Create: `backend/alembic/versions/2026_10_08_1200-073_work_blocks.py`
- Modify: `backend/app/models/user.py:1, 44-55` (die zehn `scheduled_*`-Spalten samt Kommentar löschen; `Time` aus dem Import)
- Test (neu): `backend/tests/test_073_work_blocks_migration.py`, `backend/tests/test_no_scheduled_columns.py`, `backend/tests/test_no_live_work_blocks_read.py`

**Interfaces:**
- Consumes: Diagnose-Ergebnis aus Task 0 (Spec §19 Nr. 1 — zeigt, welche Fallen real vorkommen; die Migration behandelt alle drei ohne Abbruch); `work_window_service.clamp` (Task 3); `calculation_service.get_schedule_for_date`, `get_daily_target_for_date` (Task 2); Lesestellen von `.work_blocks` nach Task 2/12
- Produces:
  - Alembic-Revision `073_work_blocks` (down `072_cr_sunday_reason`) mit den reinen Helfern `DAYS`, `LABELS`, `WINDOW_COLUMNS`, `PLACEHOLDER_START = "00:00"`, `PLACEHOLDER_END = "23:59"`, `tenant_label(tenant_id) -> str`, `build_week(window: Mapping) -> tuple[Optional[list], list[str]]`, `window_from_week(week) -> tuple[dict, list[str]]`, `upgrade_report(accounts: int, history_rows: int, notes) -> str`, `downgrade_report(multi_block, uncredited, overrides, open_requests: int) -> str`
  - Upgrade: alle neuen Spalten (3.2), Backfill in Python unter `SET LOCAL app.is_superadmin`, `auto_closed`-Backfill, Diagnose per `print`, Drop der zehn `users.scheduled_*`
  - Downgrade: Fenster aus der **Hülle**, Platzhalter → NULL, namentliche Diagnose, Drop aller neuen Spalten
  - Guard `tests/test_no_scheduled_columns.py` (Token in `app/`, Lesezugriffe in `tests/`), Guard `tests/test_no_live_work_blocks_read.py` (Erlaubnisliste `{("app/services/calculation_service.py", "get_schedule_for_date"), ("app/routers/admin_users.py", "_sync_user_from_change")}` — PR2 ergänzt den Art.-15/20-Export)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_073_work_blocks_migration.py`:

```python
"""Spec 2026-10-08, 17.1 (SQLite-Teil): die reinen Helfer der Migration 073.

Der Lauf gegen echtes PostgreSQL (Backfill unter RLS, Downgrade, Round-Trip)
steht in ``test_073_migration_pg.py``. Hier: die Backfill-Regeln je
Bestandsfalle (5.3), die Hülle beim Downgrade (5.5), die Diagnose-Texte (5.4)
und die Kappungsparität — ``clamp`` nach 073 liefert für Altfenster dieselben
Zeiten wie der 072-Code (eingefrorene Kopie unten).
"""
import importlib.util
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pytest

from app.models import User, UserRole
from app.services import calculation_service
from app.services import work_window_service as wws

MIGRATION = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
             / "2026_10_08_1200-073_work_blocks.py")


def _load():
    spec = importlib.util.spec_from_file_location("mig073", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()
EMPTY = {"blocks": [], "pause_minutes": None}


def _win(**kw):
    """``mon=(time|None, time|None)`` → 072-Spaltenwerte."""
    names = {"mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday", "fri": "friday"}
    out = {}
    for key, (start, end) in kw.items():
        out[f"scheduled_start_{names[key]}"] = start
        out[f"scheduled_end_{names[key]}"] = end
    return out


def test_revision_ids():
    assert M.revision == "073_work_blocks" and len(M.revision) <= 32
    assert M.down_revision == "072_cr_sunday_reason"


def test_two_sided_window_becomes_one_legacy_block():
    week, notes = M.build_week(_win(mon=(time(7, 30), time(16, 30))))
    assert week == [{"blocks": [{"start": "07:30", "end": "16:30"}], "pause_minutes": None}] + [EMPTY] * 4
    assert notes == []


def test_half_open_windows_get_placeholders_and_a_note():
    week, notes = M.build_week(_win(mon=(time(7, 30), None), tue=(None, time(16, 30))))
    assert week[0]["blocks"] == [{"start": "07:30", "end": "23:59"}]
    assert week[1]["blocks"] == [{"start": "00:00", "end": "16:30"}]
    assert notes == [
        "halboffen: Mo ab 07:30 → Ende 23:59 (Kappung unverändert)",
        "halboffen: Di bis 16:30 → Beginn 00:00 (Kappung unverändert)",
    ]


def test_seconds_are_truncated_with_a_note():
    week, notes = M.build_week(_win(mon=(time(7, 30, 45), time(16, 30))))
    assert week[0]["blocks"] == [{"start": "07:30", "end": "16:30"}]
    assert notes == ["Sekunden abgeschnitten: Mo 07:30:45 → 07:30"]


def test_inverted_window_is_dropped_with_a_note():
    week, notes = M.build_week(_win(mon=(time(17, 0), time(8, 0)), tue=(time(8, 0), time(16, 0))))
    assert week[0] == EMPTY
    assert week[1]["blocks"] == [{"start": "08:00", "end": "16:00"}]
    assert notes == [
        "nicht übernommen: Mo 17:00–08:00 (Beginn nicht vor Ende); "
        "Einträge an diesem Wochentag werden künftig nicht mehr gekappt"
    ]


def test_only_inverted_windows_give_none():
    """Spec 3.3/5.2: fünf leere Tage == NULL — es wird nichts geschrieben."""
    week, notes = M.build_week(_win(wed=(time(17, 0), time(8, 0))))
    assert week is None and len(notes) == 1


def test_no_window_gives_none():
    assert M.build_week(_win()) == (None, [])


def test_hull_for_multi_block_days_and_placeholders():
    week = [
        {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], "pause_minutes": 0},
        {"blocks": [{"start": "07:00", "end": "10:00"}, {"start": "11:00", "end": "13:00"},
                    {"start": "16:00", "end": "19:00"}], "pause_minutes": 0},
        {"blocks": [{"start": "07:30", "end": "16:30"}], "pause_minutes": None},
        {"blocks": [{"start": "00:00", "end": "16:30"}], "pause_minutes": None},
        {"blocks": [], "pause_minutes": 0},
    ]
    values, notes = M.window_from_week(week)
    assert (values["scheduled_start_monday"], values["scheduled_end_monday"]) == (time(8, 0), time(18, 0))
    assert (values["scheduled_start_tuesday"], values["scheduled_end_tuesday"]) == (time(7, 0), time(19, 0))
    assert (values["scheduled_start_wednesday"], values["scheduled_end_wednesday"]) == (time(7, 30), time(16, 30))
    assert (values["scheduled_start_thursday"], values["scheduled_end_thursday"]) == (None, time(16, 30))
    assert (values["scheduled_start_friday"], values["scheduled_end_friday"]) == (None, None)
    assert notes == [
        "Mo 08:00–12:00 + 15:00–18:00 → Fenster 08:00–18:00 (wieder angerechnete Lücken: 12:00–15:00)",
        "Di 07:00–10:00 + 11:00–13:00 + 16:00–19:00 → Fenster 07:00–19:00 "
        "(wieder angerechnete Lücken: 10:00–11:00, 13:00–16:00)",
    ]


@pytest.mark.parametrize("window", [
    _win(mon=(time(7, 30), time(16, 30))),
    _win(mon=(time(7, 30), None), fri=(None, time(13, 0))),
    _win(tue=(time(7, 37), time(16, 22)), thu=(time(6, 0), time(14, 0))),
])
def test_round_trip_073_072_073_is_identical_for_single_blocks(window):
    week, _ = M.build_week(window)
    values, notes = M.window_from_week(week)
    assert notes == []
    assert {k: v for k, v in values.items() if v is not None} == {
        k: v for k, v in window.items() if v is not None}
    assert M.build_week(values)[0] == week


def test_upgrade_report_format():
    text = M.upgrade_report(7, 23, ["mfa.mueller (Mandant 0000…0001): halboffen: Fr ab 07:30 → Ende 23:59 (Kappung unverändert)"])
    assert "*** HINWEIS (Migration 073) ***" in text
    assert "Arbeitszeit-Fenster wurden in Arbeitszeit-Blöcke übernommen: 7 Konten, 23 Verlaufszeilen." in text
    assert "  - mfa.mueller (Mandant 0000…0001): halboffen" in text
    assert text.rstrip().endswith("*** ENDE HINWEIS ***")
    assert "Besonderheiten" not in M.upgrade_report(0, 0, [])


def test_downgrade_report_names_everyone():
    text = M.downgrade_report(
        ["sek (Mandant 0000…0001): Mo 08:00–12:00 + 15:00–18:00 → Fenster 08:00–18:00 (wieder angerechnete Lücken: 12:00–15:00)"],
        [("zwei (Mandant 0000…0001)", 3, 450)],
        [("zwei (Mandant 0000…0001)", 1)],
        2,
    )
    assert "sek (Mandant 0000…0001): Mo 08:00–12:00 + 15:00–18:00" in text
    assert "zwei (Mandant 0000…0001): 3 Einträge, zusammen 7,50 h" in text
    assert "Anerkannte Einträge" in text
    assert "2 offene Anträge" in text


def test_tenant_label():
    assert M.tenant_label("00000000-0000-0000-0000-000000000001") == "0000…0001"


# ── Kappungsparität (Spec 17.1) ──────────────────────────────────────────────

def _shift_072(t, minutes):
    total = max(0, min(t.hour * 60 + t.minute + minutes, 23 * 60 + 59))
    return time(total // 60, total % 60)


def _clamp_072(soll_start, soll_end, start, end, grace):
    """Eingefrorene Kopie von work_window_service.clamp aus 1.19.3 (ohne die
    Feiertags-/track_hours-Zweige, die hier nicht variieren)."""
    eff_start, eff_end, raw_start, raw_end = start, end, None, None
    if soll_start is not None and start is not None:
        floor = _shift_072(soll_start, -grace)
        if start < floor:
            eff_start, raw_start = floor, start
    if soll_end is not None and end is not None:
        ceil = _shift_072(soll_end, grace)
        if end > ceil:
            eff_end, raw_end = ceil, end
    if eff_start is not None and eff_end is not None and eff_start >= eff_end:
        return (start, start, start, end)
    return (eff_start, eff_end, raw_start, raw_end)


WINDOWS = [
    (time(8, 0), time(17, 0)), (time(8, 0), None), (None, time(17, 0)),
    (time(7, 37), time(16, 22)), (None, time(23, 50)), (time(0, 10), time(23, 50)),
]
STAMPS = [time(h, m) for h, m in (
    (0, 0), (5, 0), (7, 0), (7, 22), (7, 44), (7, 45), (7, 50), (8, 0), (12, 0),
    (16, 0), (16, 37), (17, 14), (17, 15), (17, 16), (18, 30), (23, 59))]
MON = date(2026, 6, 1)


def _user(window):
    week, _ = M.build_week({"scheduled_start_monday": window[0], "scheduled_end_monday": window[1]})
    return User(username="p", email="p@x.de", password_hash="h", first_name="P", last_name="P",
                role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5,
                vacation_days=30, track_hours=True, work_blocks=week)


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("grace", [0, 15, 30])
def test_clamp_parity_with_072(db, window, grace):
    user = _user(window)
    for start in STAMPS:
        for end in [None] + [s for s in STAMPS if s > start]:
            r = wws.clamp(db, user, MON, start, end, grace, credit_override=False)
            assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == _clamp_072(
                window[0], window[1], start, end, grace), (window, grace, start, end)
            assert r.uncredited_minutes == 0


def test_blocks_do_not_feed_the_target(db):
    """E10/E18: Altfenster treiben kein Soll — das Tagessoll ist mit und ohne
    übernommenes Fenster identisch (Saldo-Identität auf echten Daten: Task 17)."""
    user = _user((time(7, 30), time(12, 0)))
    with_window = calculation_service.get_daily_target_for_date(
        user, MON, calculation_service.get_schedule_for_date(db, user, MON))
    user.work_blocks = None
    without = calculation_service.get_daily_target_for_date(
        user, MON, calculation_service.get_schedule_for_date(db, user, MON))
    assert with_window == without == Decimal("8")
```

`backend/tests/test_no_scheduled_columns.py`:

```python
"""Spec E23 / 17.6: nach Migration 073 liest kein Code mehr ``users.scheduled_*``.

Ein ``getattr(user, "scheduled_…", None)`` lieferte nach dem Spalten-Drop still
``None`` und schaltete die Kappung ab — deshalb ein Token-Guard statt
Vertrauen. In ``app/`` ist das Token verboten (die Altfeld-Erkennung nutzt nur
das Präfix ``scheduled_``, 11.4; die Migration liegt in ``alembic/``). In
``tests/`` sind nur LESEZUGRIFFE verboten — Tests dürfen die Altfelder als
JSON-Schlüssel senden (400-Tests). Ausgenommen: ``tests/test_073_*.py``
(Backfill/Downgrade lesen die Spalten per SQL) und dieser Guard.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP_TOKEN = re.compile(r"scheduled_(start|end)_")
TEST_READ = re.compile(r"\.scheduled_(start|end)_|getattr\([^)]*[\"']scheduled_")


def _py_files(root: Path):
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _hits(files, pattern):
    hits = []
    for path in files:
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(BACKEND)}:{no}: {line.strip()}")
    return hits


def test_app_has_no_scheduled_window_token():
    assert _hits(_py_files(BACKEND / "app"), APP_TOKEN) == []


def test_tests_do_not_read_scheduled_window_attributes():
    me = Path(__file__).name
    files = [p for p in _py_files(BACKEND / "tests")
             if p.name != me and not p.name.startswith("test_073_")]
    assert _hits(files, TEST_READ) == []
```

`backend/tests/test_no_live_work_blocks_read.py`:

```python
"""Spec E9/E56/9.8: ``users.work_blocks`` ist Rückfall NUR für Tage vor der
ersten Verlaufszeile und Spiegel der jüngsten Zeile ≤ heute. Wer es live für
eine Berechnung läse, hebelte zukunftsdatierte Änderungen aus (kein Scheduler).

Der Guard prüft per ``ast`` jeden Attributzugriff ``.work_blocks`` und jedes
``getattr/setattr/hasattr(…, "work_blocks", …)`` in ``app/`` und vergleicht die
Fundstellen (Datei, umschließende Funktion) mit der Erlaubnisliste. PR2 ergänzt
den Art.-15/20-Export (``lifecycle_service._user_dict``, ``auth`` ``/me/export``).
``work_blocks_today`` ist ein anderer Name und entsteht über den Resolver.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ALLOWED = {
    ("app/services/calculation_service.py", "get_schedule_for_date"),
    ("app/routers/admin_users.py", "_sync_user_from_change"),
}


class _Finder(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel, self.stack, self.found = rel, [], set()

    def _scope(self):
        return self.stack[-1] if self.stack else "<modul>"

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Attribute(self, node):
        if node.attr == "work_blocks":
            self.found.add((self.rel, self._scope()))
        self.generic_visit(node)

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr", "hasattr")
                and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "work_blocks"):
            self.found.add((self.rel, self._scope()))
        self.generic_visit(node)


def test_work_blocks_is_read_only_where_allowed():
    found = set()
    for path in sorted((BACKEND / "app").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        finder = _Finder(path.relative_to(BACKEND).as_posix())
        finder.visit(ast.parse(path.read_text(encoding="utf-8")))
        found |= finder.found
    assert found == ALLOWED
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_073_work_blocks_migration.py tests/test_no_scheduled_columns.py tests/test_no_live_work_blocks_read.py -q -p no:cacheprovider`
Expected: FAIL — `test_073_work_blocks_migration.py` bei der Sammlung (`FileNotFoundError` für die Migrationsdatei); `test_app_has_no_scheduled_window_token` listet die zehn Spalten in `app/models/user.py`; `test_work_blocks_is_read_only_where_allowed` PASS.

- [ ] **Step 3: Migration anlegen**

`backend/alembic/versions/2026_10_08_1200-073_work_blocks.py`:

```python
"""Arbeitszeit-Bloecke (Spec 2026-10-08, Abschnitt 5): Fenster -> Bloecke.

#201 hatte je Wochentag EIN Soll-Fenster direkt auf der User-Zeile
(``users.scheduled_*``): nicht historisiert, einteilig, ohne Soll-Wirkung. Ab
hier leben die Bloecke im datierten Vertrags-Snapshot
(``working_hours_changes.blocks``, Rueckfall ``users.work_blocks``).

Upgrade (Spec 5.2):

* neue Spalten (Bloecke, ``uncredited_minutes``, ``credit_override``,
  ``auto_closed``, ``clamp_grace_minutes``, Antragsfelder);
* Backfill IN PYTHON: jedes Fenster wird ein Einblock-Tag mit
  ``pause_minutes`` NULL ("Altfenster": kappt, treibt kein Soll), auf
  ``users.work_blocks`` UND auf JEDE Verlaufszeile der Person - die Fenster
  wirkten live, also bleibt das Verhalten byte-identisch (Prinzip wie 067);
* Bestandsfallen (halboffen, Beginn >= Ende, Sekunden) brechen NICHT ab,
  sondern stehen namentlich in der Diagnose (Spec 5.3/5.4) - ein Update eines
  Kundensystems darf nicht haengen;
* ``auto_closed`` fuer Eintraege, die der Auto-Close auf 23:59 geschlossen hat
  (Ende ODER Rohende 23:59, siehe ``backfill_auto_closed``);
* die zehn ``scheduled_*``-Spalten werden geloescht (E23, kein Expand/Contract).

KEINE Neukappung: ``uncredited_minutes`` bleibt 0, ``clamp_grace_minutes``
NULL ("unbekannt -> aktueller Puffer"), ``hours_*``/``weekly_hours`` unberuehrt
- ``net_hours``, Soll und Saldo bleiben byte-identisch (E22).

Downgrade (Spec 5.5, entschieden 2026-10-08): das 072-Fenster entsteht aus der
HUELLE der Bloecke (Beginn des ersten bis Ende des letzten Blocks), nicht aus
dem ersten Block. Verlustbehaftet; die Diagnose nennt die Betroffenen.

Die reinen Helfer (``build_week``, ``window_from_week``, ``upgrade_report``,
``downgrade_report``) sind ohne Datenbank testbar, ``backfill_auto_closed``
gegen die SQLite-Test-DB (``tests/test_073_work_blocks_migration.py``); der
Lauf gegen echtes PostgreSQL steht in ``tests/test_073_migration_pg.py``.
"""
import json
import sys
from datetime import time

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "073_work_blocks"
down_revision = "072_cr_sunday_reason"
branch_labels = None
depends_on = None

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
LABELS = ("Mo", "Di", "Mi", "Do", "Fr")
WINDOW_COLUMNS = tuple(
    f"scheduled_{kind}_{day}" for day in DAYS for kind in ("start", "end")
)
PLACEHOLDER_START = "00:00"
PLACEHOLDER_END = "23:59"


def _hhmm(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def _hms(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}:{t.second:02d}"


def _parse_hhmm(value: str) -> time:
    return time(int(value[:2]), int(value[3:5]))


def _n(count: int, singular: str, plural: str) -> str:
    """Zahl mit passender Form: ``1 Konto``, ``0 Konten``, ``2 Konten``."""
    return f"{count} {singular if count == 1 else plural}"


def _emit(text: str) -> None:
    """Diagnose ausgeben, ohne an der Kodierung der Ausgabe zu scheitern.

    Die Texte enthalten "→" (U+2192), das cp1252 nicht kennt. Nativ unter
    Windows ist stdout dieser Migration eine Pipe in der ANSI-Codepage, sobald
    PYTHONUTF8 nicht gesetzt ist (etwa beim Konsolenstart des Prozessmanagers);
    ein nacktes ``print`` wuerfe dann UnicodeEncodeError, alembic rollte die
    Migration zurueck und der Dienst startete nicht - genau das, was E21
    ausschliesst. Rueckfall: "→" als "->", alles Uebrige, was die Kodierung
    nicht kennt (etwa ein Benutzername mit "ł"), als "?". Mit UTF-8 bleibt der
    Wortlaut der Spec unveraendert."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.replace("→", "->").encode(enc, "replace").decode(enc))


def tenant_label(tenant_id) -> str:
    """Kurzform wie in der Spec (``0000…0001``)."""
    text = str(tenant_id)
    return f"{text[:4]}…{text[-4:]}" if len(text) > 8 else text


def build_week(window) -> tuple:
    """072-Fenster (Mapping mit ``scheduled_start_monday`` …) -> kanonische
    Altzeilen-Woche (Spec 3.1/5.3).

    Rueckgabe ``(woche, hinweise)``. ``woche`` ist ``None``, wenn kein Tag
    einen Block bekommt (Spec 3.3: fuenf leere Tage == NULL, geschrieben wird
    dann nichts)."""
    week, notes = [], []
    for day, label in zip(DAYS, LABELS):
        start = window.get(f"scheduled_start_{day}")
        end = window.get(f"scheduled_end_{day}")
        if start is None and end is None:
            week.append({"blocks": [], "pause_minutes": None})
            continue
        for value in (start, end):
            if value is not None and (value.second or value.microsecond):
                notes.append(
                    f"Sekunden abgeschnitten: {label} {_hms(value)} → {_hhmm(value)}"
                )
        s = _hhmm(start) if start is not None else None
        e = _hhmm(end) if end is not None else None
        if e is None:
            notes.append(
                f"halboffen: {label} ab {s} → Ende {PLACEHOLDER_END} (Kappung unverändert)"
            )
            e = PLACEHOLDER_END
        elif s is None:
            notes.append(
                f"halboffen: {label} bis {e} → Beginn {PLACEHOLDER_START} (Kappung unverändert)"
            )
            s = PLACEHOLDER_START
        if s >= e:  # "HH:MM" ist nullgepolstert -> Stringvergleich == Zeitvergleich
            notes.append(
                f"nicht übernommen: {label} {s}–{e} (Beginn nicht vor Ende); "
                "Einträge an diesem Wochentag werden künftig nicht mehr gekappt"
            )
            week.append({"blocks": [], "pause_minutes": None})
            continue
        week.append({"blocks": [{"start": s, "end": e}], "pause_minutes": None})
    if not any(day["blocks"] for day in week):
        return None, notes
    return week, notes


def window_from_week(week) -> tuple:
    """Downgrade (Spec 5.5): 072-Fenster je Tag aus der HUELLE der Bloecke.

    Rueckgabe ``(spalten, mehrblock_hinweise)``. Platzhalter ``00:00`` als
    Beginn und ``23:59`` als Ende werden wieder NULL (Round-Trip der
    halboffenen Fenster)."""
    values = {column: None for column in WINDOW_COLUMNS}
    notes = []
    for idx, (day, label) in enumerate(zip(DAYS, LABELS)):
        if not week or idx >= len(week):
            continue
        blocks = sorted((week[idx] or {}).get("blocks") or [], key=lambda b: b["start"])
        if not blocks:
            continue
        start = blocks[0]["start"]
        end = max(block["end"] for block in blocks)
        if len(blocks) > 1:
            spans = " + ".join(f"{b['start']}–{b['end']}" for b in blocks)
            gaps = ", ".join(f"{a['end']}–{b['start']}" for a, b in zip(blocks, blocks[1:]))
            notes.append(
                f"{label} {spans} → Fenster {start}–{end} "
                f"(wieder angerechnete Lücken: {gaps})"
            )
        values[f"scheduled_start_{day}"] = None if start == PLACEHOLDER_START else _parse_hhmm(start)
        values[f"scheduled_end_{day}"] = None if end == PLACEHOLDER_END else _parse_hhmm(end)
    return values, notes


def upgrade_report(accounts: int, history_rows: int, notes) -> str:
    """Diagnose-Ausgabe (Spec 5.4) - ausgegeben ueber ``_emit`` (``print`` wie
    067, mit Rueckfall fuer Nicht-UTF-8-Ausgaben), landet im Update-Log (nativ)
    bzw. im Container-Log (Docker)."""
    lines = [
        "",
        "*** HINWEIS (Migration 073) ***",
        "Arbeitszeit-Fenster wurden in Arbeitszeit-Blöcke übernommen: "
        f"{_n(accounts, 'Konto', 'Konten')}, "
        f"{_n(history_rows, 'Verlaufszeile', 'Verlaufszeilen')}.",
    ]
    if notes:
        lines.append("Besonderheiten (bitte im Dialog „Arbeitszeit anpassen…“ prüfen):")
        lines.extend(f"  - {note}" for note in notes)
    lines.append("*** ENDE HINWEIS ***")
    return "\n".join(lines) + "\n"


def _hours_de(minutes: int) -> str:
    return f"{minutes / 60:.2f}".replace(".", ",")


def downgrade_report(multi_block, uncredited, overrides, open_requests: int) -> str:
    """Diagnose des Downgrades (Spec 5.5 Schritt 3).

    ``multi_block``: fertige Zeilen ``"<wer>: <Tag> …"``; ``uncredited``:
    ``(wer, anzahl, minuten)``; ``overrides``: ``(wer, anzahl)``."""
    lines = [
        "",
        "*** HINWEIS (Migration 073, Downgrade) ***",
        "Arbeitszeit-Blöcke wurden auf ein Fenster je Wochentag zurückgeführt "
        "(Hülle: Beginn des ersten bis Ende des letzten Blocks).",
    ]
    if multi_block:
        lines.append(
            "Mehrere Blöcke an einem Tag – das Fenster kappt nur noch an der Hülle, "
            "Zeit zwischen den Blöcken wird bei künftigen Schreibvorgängen wieder angerechnet:"
        )
        lines.extend(f"  - {note}" for note in multi_block)
    if uncredited:
        lines.append(
            "Einträge mit nicht angerechneter Zeit – ihre angerechnete Zeit steigt "
            "mit dem Downgrade sofort um diese Summe:"
        )
        lines.extend(
            f"  - {who}: {_n(count, 'Eintrag', 'Einträge')}, zusammen {_hours_de(minutes)} h"
            for who, count, minutes in uncredited
        )
    if overrides:
        lines.append("Anerkannte Einträge (das Kennzeichen entfällt):")
        lines.extend(f"  - {who}: {_n(count, 'Eintrag', 'Einträge')}" for who, count in overrides)
    if open_requests:
        one = open_requests == 1
        lines.append(
            f"{_n(open_requests, 'offener Antrag', 'offene Anträge')} „Anrechnung beantragen“ "
            f"{'wird' if one else 'werden'} nach dem Downgrade wie "
            f"{'ein gewöhnlicher Änderungsantrag' if one else 'gewöhnliche Änderungsanträge'} "
            "genehmigt, also wieder gekappt."
        )
    lines.append("*** ENDE HINWEIS ***")
    return "\n".join(lines) + "\n"


def _json_type():
    # JSONB auf PostgreSQL, JSON sonst - wie das Modell (Spec E8).
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _superadmin(conn) -> bool:
    """FORCE RLS (Spec 5.2 Schritt 2): ist die Migrationsrolle Eigentuemerin,
    aber kein Superuser, traefe der Backfill sonst still 0 Zeilen."""
    if conn.dialect.name != "postgresql":
        return False
    conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))
    return True


def backfill_auto_closed(conn) -> int:
    """P18: vor 073 kappte der Auto-Close nie - ein Eintrag mit Ende 23:59 UND
    Protokollzeile auto_close ist der Auto-Close. Reines Kennzeichen, net_hours
    unveraendert. Rueckgabe: Anzahl gekennzeichneter Eintraege.

    ``raw_end_time = 23:59`` gehoert dazu: unter 072 kappte ein spaeteres
    Speichern des ganzen Formulars (etwa nur die Pause ergaenzt, Ende 23:59
    unveraendert - ``unclamp_input`` reicht es mangels Rohwert durch) die
    synthetischen 23:59 auf das Fensterende und hielt 23:59 als ``raw_end_time``
    fest. Das ist genau die Form, die der neue Auto-Close mit
    ``auto_closed = true`` schreibt; ohne Kennzeichen zaehlte P19 die Strecke bis
    23:59 als "nicht angerechnet", und Anerkennen rechnete bis 23:59 an.

    Kein Fehltreffer: ein echt korrigiertes Ende laesst ``raw_end_time`` NULL
    (im Fenster) oder traegt den echten Wert (ausserhalb), nie 23:59. Offen
    bleibt nur ein echtes Ende um genau 23:59 - dieselbe Mehrdeutigkeit, die die
    Spec fuer ``end_time = 23:59`` schon hinnimmt."""
    return conn.execute(sa.text(
        "UPDATE time_entries SET auto_closed = true "
        "WHERE (end_time = :t OR raw_end_time = :t) AND EXISTS ("
        "  SELECT 1 FROM time_entry_audit_logs a "
        "  WHERE a.time_entry_id = time_entries.id AND a.source = 'auto_close')"
    ).bindparams(sa.bindparam("t", time(23, 59), type_=sa.Time()))).rowcount


def upgrade():
    op.add_column("users", sa.Column("work_blocks", _json_type(), nullable=True))
    op.add_column("working_hours_changes", sa.Column("blocks", _json_type(), nullable=True))
    op.add_column("time_entries", sa.Column(
        "uncredited_minutes", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("time_entries", sa.Column(
        "credit_override", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("time_entries", sa.Column(
        "auto_closed", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("time_entries", sa.Column("clamp_grace_minutes", sa.Integer(), nullable=True))
    op.add_column("change_requests", sa.Column(
        "request_credit_override", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("change_requests", sa.Column(
        "original_uncredited_minutes", sa.Integer(), nullable=True))

    conn = op.get_bind()
    pg = _superadmin(conn)
    as_json = "CAST(:j AS JSONB)" if pg else ":j"

    columns = ", ".join(WINDOW_COLUMNS)
    any_window = " OR ".join(f"{c} IS NOT NULL" for c in WINDOW_COLUMNS)
    rows = conn.execute(sa.text(
        f"SELECT id, tenant_id, username, {columns} FROM users "
        f"WHERE {any_window} ORDER BY tenant_id, username"
    )).mappings().all()

    notes, expected, accounts, history_rows = [], 0, 0, 0
    for row in rows:
        week, day_notes = build_week(row)
        who = f"{row['username']} (Mandant {tenant_label(row['tenant_id'])})"
        notes.extend(f"{who}: {note}" for note in day_notes)
        if week is None:
            continue
        expected += 1
        payload = json.dumps(week)
        accounts += conn.execute(
            sa.text(f"UPDATE users SET work_blocks = {as_json} WHERE id = :id"),
            {"j": payload, "id": row["id"]},
        ).rowcount
        history_rows += conn.execute(
            sa.text(f"UPDATE working_hours_changes SET blocks = {as_json} WHERE user_id = :id"),
            {"j": payload, "id": row["id"]},
        ).rowcount
    if accounts != expected:
        notes.append(
            f"Abweichung: {_n(expected, 'Konto', 'Konten')} erwartet, "
            f"{accounts} aktualisiert (RLS?)"
        )

    backfill_auto_closed(conn)

    _emit(upgrade_report(accounts, history_rows, notes))

    for column in WINDOW_COLUMNS:
        op.drop_column("users", column)


def downgrade():
    for column in WINDOW_COLUMNS:
        op.add_column("users", sa.Column(column, sa.Time(), nullable=True))

    conn = op.get_bind()
    _superadmin(conn)

    multi_block = []
    rows = conn.execute(sa.text(
        "SELECT id, tenant_id, username, work_blocks FROM users "
        "WHERE work_blocks IS NOT NULL ORDER BY tenant_id, username"
    )).mappings().all()
    assignments = ", ".join(f"{c} = :{c}" for c in WINDOW_COLUMNS)
    for row in rows:
        week = row["work_blocks"]
        if isinstance(week, str):  # SQLite liefert JSON als Text
            week = json.loads(week)
        values, notes = window_from_week(week)
        who = f"{row['username']} (Mandant {tenant_label(row['tenant_id'])})"
        multi_block.extend(f"{who}: {note}" for note in notes)
        conn.execute(
            sa.text(f"UPDATE users SET {assignments} WHERE id = :id"),
            {**values, "id": row["id"]},
        )

    uncredited = [
        (f"{r['username']} (Mandant {tenant_label(r['tenant_id'])})", int(r["n"]), int(r["m"]))
        for r in conn.execute(sa.text(
            "SELECT u.username, u.tenant_id, COUNT(*) AS n, SUM(e.uncredited_minutes) AS m "
            "FROM time_entries e JOIN users u ON u.id = e.user_id "
            "WHERE e.uncredited_minutes > 0 "
            "GROUP BY u.username, u.tenant_id ORDER BY u.tenant_id, u.username"
        )).mappings().all()
    ]
    overrides = [
        (f"{r['username']} (Mandant {tenant_label(r['tenant_id'])})", int(r["n"]))
        for r in conn.execute(sa.text(
            "SELECT u.username, u.tenant_id, COUNT(*) AS n "
            "FROM time_entries e JOIN users u ON u.id = e.user_id "
            "WHERE e.credit_override "
            "GROUP BY u.username, u.tenant_id ORDER BY u.tenant_id, u.username"
        )).mappings().all()
    ]
    open_requests = conn.execute(sa.text(
        "SELECT COUNT(*) FROM change_requests "
        "WHERE request_credit_override AND status = 'pending'"
    )).scalar() or 0

    _emit(downgrade_report(multi_block, uncredited, overrides, int(open_requests)))

    op.drop_column("change_requests", "original_uncredited_minutes")
    op.drop_column("change_requests", "request_credit_override")
    op.drop_column("time_entries", "clamp_grace_minutes")
    op.drop_column("time_entries", "auto_closed")
    op.drop_column("time_entries", "credit_override")
    op.drop_column("time_entries", "uncredited_minutes")
    op.drop_column("working_hours_changes", "blocks")
    op.drop_column("users", "work_blocks")
```

- [ ] **Step 4: Spalten aus dem Modell entfernen**

`backend/app/models/user.py` — Importzeile:

```python
from sqlalchemy import Column, String, Boolean, Numeric, Integer, BigInteger, Enum, DateTime, Date, Text, ForeignKey, JSON
```

und den Block

```python
    # #201: optionales Soll-Arbeitszeit-Fenster je Wochentag (Mo–Fr). NULL =
    # kein Fenster an dem Tag → keine Kappung. Kappt nur das Ist, nicht das Soll.
    scheduled_start_monday = Column(Time, nullable=True)
```

bis einschließlich `scheduled_end_friday = Column(Time, nullable=True)` löschen.

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_073_work_blocks_migration.py tests/test_no_scheduled_columns.py tests/test_no_live_work_blocks_read.py tests/test_migration_067_weekly_hours_guard.py -q -p no:cacheprovider`
Expected: PASS (36 Tests in den drei neuen Dateien + 3 in 067).

Danach die volle SQLite-Suite (Global Constraints). Expected: keine neuen Fehlschläge.

Nachgezogen nach dem Review von Task 13: Einzahl in den Diagnosen (`_n`: „1 Konto, 1 Verlaufszeile.", „1 Eintrag", „1 offener Antrag … wird … wie ein gewöhnlicher Änderungsantrag genehmigt") und `_emit` statt `print` (cp1252-Rückfall „→" → „->", Kodierungsfremdes → „?"; nativ unter Windows sonst UnicodeEncodeError → Rollback → Dienst startet nicht, E21). Tests dazu in `test_073_work_blocks_migration.py` (`test_upgrade_report_singular`, `test_downgrade_report_singular`, `test_emit_*`, `test_upgrade_and_downgrade_print_only_through_emit`); außerdem setzt `praxiszeit-server.py::run_migrations` `PYTHONUTF8=1` und liest die Ausgabe als UTF-8 mit `errors="replace"` (`test_native_pg_lifecycle.py::TestMigrationenLaufenInUtf8`, läuft nur mit gemountetem Repo wie in `scripts/local-ci.sh` Schritt 3).

Kontrolle der Revisionskette: `grep -n "^revision\|^down_revision" backend/alembic/versions/*073*.py` → `073_work_blocks` / `072_cr_sunday_reason`; `grep -l "down_revision = \"073_work_blocks\"" backend/alembic/versions/*.py` → keine Ausgabe (073 ist Kopf). Der Lauf gegen echtes PostgreSQL folgt in Task 14.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/2026_10_08_1200-073_work_blocks.py backend/app/models/user.py backend/tests/test_073_work_blocks_migration.py backend/tests/test_no_scheduled_columns.py backend/tests/test_no_live_work_blocks_read.py
git commit -F - <<'EOF'
feat(bloecke): Migration 073 — Fenster werden Altblöcke, neue Spalten, Downgrade aus der Hülle, Guard-Tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 14: Postgres — Migration-Round-Trip, `net_hours`-Parität, Bestands-PG-Suiten, CI-Verdrahtung (17.1, 17.3)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#491/#482 haben in `scripts/local-ci.sh` den Schritt „Native PG lifecycle" erweitert; Schritt 1 und 2, die dieser Task ändert, sind unverändert. `test_concurrency.py` und `test_invalid_uuid_postgres.py` haben neue Tests — die Erwartung in Step 3 nennt den Stand `3d46c2f`.)

**Files:**
- Create: `backend/tests/test_073_migration_pg.py`, `backend/tests/test_net_hours_parity_pg.py`
- Modify: `.github/workflows/cross-tenant-ci.yml` (SQLite-Schritt: zwei `--ignore`; PostgreSQL-Schritt: zwei Dateien)
- Modify: `scripts/local-ci.sh` (Schritt 1: zwei `--ignore`; Schritt 2: zwei Dateien, Zählkommentar)

**Interfaces:**
- Consumes: Migration `073_work_blocks` mit `print`-Diagnose (Task 13); `TimeEntry.net_hours`-SQL-Ausdruck (Task 4); `test_concurrency.py` mit deterministischem Start (Task 7)
- Produces: zwei PG-only-Testdateien mit modulweitem Skip ohne PostgreSQL-URL (Muster `test_invalid_uuid_postgres.py`); `test_073_migration_pg.py` arbeitet in einer **eigenen** Wegwerf-Datenbank (`CREATE DATABASE` als Superuser), nie in der geteilten Test-DB; beide in Actions und `local-ci.sh` eingehängt

- [ ] **Step 1: Tests schreiben**

`backend/tests/test_073_migration_pg.py`:

```python
"""Spec 2026-10-08, 17.1 (Postgres-only): Migration 073 auf echtem PostgreSQL.

Läuft in einer EIGENEN Wegwerf-Datenbank auf demselben Server (``CREATE
DATABASE`` als Superuser) — die geteilte Test-DB wird nie herabgestuft.
Alembic läuft als Unterprozess über ``from alembic.config import main``
(CLAUDE.md: kein ``python -m alembic`` wegen cwd-Shadowing).

Geprüft: Backfill (zweiseitig, halboffen, invertiert, Sekunden, nur invertiert),
Verlaufszeilen, ``auto_closed``-Backfill, ``clamp_grace_minutes`` NULL,
Spaltentypen, Diagnose-Ausgabe, Byte-Identität der Bestandsspalten,
Downgrade aus der HÜLLE inkl. Diagnose, Round-Trip 073 → 072 → 073.

Eingehängt in ``scripts/local-ci.sh`` Schritt 2 und den PostgreSQL-Schritt von
``.github/workflows/cross-tenant-ci.yml`` (im SQLite-Schritt per ``--ignore``).
"""
import json
import os
import subprocess
import sys
import uuid
from datetime import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_URL or not ADMIN_URL.startswith("postgresql"):
    pytest.skip(
        "test_073_migration_pg.py braucht PostgreSQL (ADMIN_DB_URL / DATABASE_URL_MIGRATIONS)",
        allow_module_level=True,
    )

BACKEND = Path(__file__).resolve().parents[1]
TENANT = "00000000-0000-0000-0000-000000000001"  # legt Migration 027 an
U = {name: str(uuid.UUID(int=0x1111_0000_0000_4000_8000_0000_0000_0000 + i))
     for i, name in enumerate(("zwei", "halbende", "invers", "sek", "nurinvers", "ohne", "mehr"), 1)}
E = {name: str(uuid.UUID(int=0x3333_0000_0000_4000_8000_0000_0000_0000 + i))
     for i, name in enumerate(("autoclose", "korrigiert", "ohne_protokoll", "mehr",
                               "nachgekappt", "nachgekappt_echt"), 1)}
WINDOW_COLUMNS = [f"scheduled_{k}_{d}" for d in ("monday", "tuesday", "wednesday", "thursday", "friday")
                  for k in ("start", "end")]
OLD_TE = "id, user_id, date, start_time, end_time, break_minutes, raw_start_time, raw_end_time, note"
OLD_WH = "id, user_id, effective_from, weekly_hours, use_daily_schedule, work_days_per_week"


def _alembic(url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL_MIGRATIONS": url}
    proc = subprocess.run(
        [sys.executable, "-c", f"from alembic.config import main; main({list(args)!r})"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout + proc.stderr


def _md5(conn, sql: str) -> tuple:
    return tuple(conn.execute(text(
        f"SELECT count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM ({sql}) t"
    )).one())


@pytest.fixture(scope="module")
def scratch():
    name = f"pz073_{uuid.uuid4().hex[:10]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _user(conn, key, **window):
    cols = ["id", "tenant_id", "username", "email", "password_hash", "first_name",
            "last_name", "role", "weekly_hours", "vacation_days", "is_active", *window]
    params = {"id": U[key], "tenant_id": TENANT, "username": key, "email": f"{key}@x.de",
              "password_hash": "h", "first_name": key, "last_name": "T", "role": "EMPLOYEE",
              "weekly_hours": 40, "vacation_days": 30, "is_active": True, **window}
    conn.execute(text(
        f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"
    ), params)


def _seed_072(conn):
    _user(conn, "zwei", **{f"scheduled_{k}_{d}": (time(7, 30) if k == "start" else time(16, 30))
                           for d in ("monday", "tuesday", "wednesday", "thursday") for k in ("start", "end")},
          scheduled_start_friday=time(7, 30))
    _user(conn, "halbende", scheduled_end_monday=time(16, 30))
    _user(conn, "invers", scheduled_start_monday=time(17, 0), scheduled_end_monday=time(8, 0),
          scheduled_start_tuesday=time(8, 0), scheduled_end_tuesday=time(16, 0))
    _user(conn, "sek", scheduled_start_monday=time(7, 30, 45), scheduled_end_monday=time(16, 30))
    _user(conn, "nurinvers", scheduled_start_wednesday=time(17, 0), scheduled_end_wednesday=time(8, 0))
    _user(conn, "ohne")
    _user(conn, "mehr", scheduled_start_monday=time(8, 0), scheduled_end_monday=time(18, 0))
    for i, (who, day) in enumerate((("zwei", "2026-01-01"), ("zwei", "2026-06-01"), ("nurinvers", "2026-01-01")), 1):
        conn.execute(text(
            "INSERT INTO working_hours_changes (id, tenant_id, user_id, effective_from, weekly_hours) "
            "VALUES (:id, :t, :u, :d, 40)"
        ), {"id": str(uuid.UUID(int=0x2222_0000_0000_4000_8000_0000_0000_0000 + i)),
            "t": TENANT, "u": U[who], "d": day})
    # "nachgekappt": 072-Auto-Close (23:59), danach das ganze Formular gespeichert →
    # 072 kappte die 23:59 auf das Fensterende und hielt sie als Rohende fest
    # (dieselbe Form wie der neue Auto-Close). "nachgekappt_echt": Kontrolle, echtes
    # Ende 19:00 außerhalb des Fensters.
    for key, who, day, end, raw_end in (("autoclose", "zwei", "2026-06-01", time(23, 59), None),
                                        ("korrigiert", "zwei", "2026-06-02", time(17, 0), None),
                                        ("ohne_protokoll", "zwei", "2026-06-03", time(23, 59), None),
                                        ("mehr", "mehr", "2026-06-01", time(18, 0), None),
                                        ("nachgekappt", "zwei", "2026-06-08", time(16, 45), time(23, 59)),
                                        ("nachgekappt_echt", "zwei", "2026-06-09", time(16, 45), time(19, 0))):
        conn.execute(text(
            "INSERT INTO time_entries (id, tenant_id, user_id, date, start_time, end_time, raw_end_time, break_minutes) "
            "VALUES (:id, :t, :u, :d, :s, :e, :re, 0)"
        ), {"id": E[key], "t": TENANT, "u": U[who], "d": day, "s": time(8, 0), "e": end, "re": raw_end})
    for key in ("autoclose", "korrigiert", "nachgekappt", "nachgekappt_echt"):
        conn.execute(text(
            "INSERT INTO time_entry_audit_logs (tenant_id, time_entry_id, user_id, changed_by, action, source, new_end_time) "
            "VALUES (:t, :e, :u, :u, 'update', 'auto_close', :end)"
        ), {"t": TENANT, "e": E[key], "u": U["zwei"], "end": time(23, 59)})


def _blocks(conn, key):
    return conn.execute(text("SELECT work_blocks FROM users WHERE id = :id"), {"id": U[key]}).scalar()


def _one(start, end):
    return {"blocks": [{"start": start, "end": end}], "pause_minutes": None}


EMPTY = {"blocks": [], "pause_minutes": None}


def test_073_upgrade_downgrade_round_trip(scratch):
    url, engine = scratch
    _alembic(url, "upgrade", "072_cr_sunday_reason")
    with engine.begin() as conn:
        _seed_072(conn)
    with engine.connect() as conn:
        te_before = _md5(conn, f"SELECT {OLD_TE} FROM time_entries")
        wh_before = _md5(conn, f"SELECT {OLD_WH} FROM working_hours_changes")

    out = _alembic(url, "upgrade", "073_work_blocks")
    assert "*** HINWEIS (Migration 073) ***" in out
    assert "übernommen: 5 Konten, 2 Verlaufszeilen." in out
    assert "halboffen: Fr ab 07:30 → Ende 23:59 (Kappung unverändert)" in out
    assert "halboffen: Mo bis 16:30 → Beginn 00:00 (Kappung unverändert)" in out
    assert "Sekunden abgeschnitten: Mo 07:30:45 → 07:30" in out
    assert "nicht übernommen: Mo 17:00–08:00" in out
    assert "nicht übernommen: Mi 17:00–08:00" in out
    # Spec 17.1: "nurinvers" (nur invertierte Fenster) zählt nicht als erwartetes
    # Konto. Der einzige Lauf, in dem die Zählprobe überhaupt rechnet — die
    # SQLite-Tests prüfen nur die Helfer und rufen ``upgrade()`` nie auf.
    assert "Abweichung" not in out

    with engine.connect() as conn:
        assert _blocks(conn, "zwei") == [_one("07:30", "16:30")] * 4 + [_one("07:30", "23:59")]
        assert _blocks(conn, "halbende") == [_one("00:00", "16:30")] + [EMPTY] * 4
        assert _blocks(conn, "invers") == [EMPTY, _one("08:00", "16:00")] + [EMPTY] * 3
        assert _blocks(conn, "sek") == [_one("07:30", "16:30")] + [EMPTY] * 4
        assert _blocks(conn, "nurinvers") is None
        assert _blocks(conn, "ohne") is None
        wh = conn.execute(text(
            "SELECT user_id::text, blocks FROM working_hours_changes ORDER BY user_id, effective_from"
        )).all()
        assert [(u, b is None) for u, b in wh] == [(U["zwei"], False), (U["zwei"], False), (U["nurinvers"], True)]
        assert all(b == _blocks(conn, "zwei") for u, b in wh if u == U["zwei"])
        flags = dict(conn.execute(text("SELECT id::text, auto_closed FROM time_entries")).all())
        assert flags == {E["autoclose"]: True, E["korrigiert"]: False,
                         E["ohne_protokoll"]: False, E["mehr"]: False,
                         E["nachgekappt"]: True, E["nachgekappt_echt"]: False}
        assert conn.execute(text(
            "SELECT count(*) FROM time_entries WHERE clamp_grace_minutes IS NOT NULL "
            "OR uncredited_minutes <> 0 OR credit_override"
        )).scalar() == 0
        columns = {(t, c): (d, n, dflt) for t, c, d, n, dflt in conn.execute(text(
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema = 'public'"
        )).all()}
        assert not [c for (t, c) in columns if t == "users" and c.startswith("scheduled_")]
        assert columns[("users", "work_blocks")][:2] == ("jsonb", "YES")
        assert columns[("working_hours_changes", "blocks")][:2] == ("jsonb", "YES")
        assert columns[("time_entries", "uncredited_minutes")] == ("integer", "NO", "0")
        assert columns[("time_entries", "credit_override")] == ("boolean", "NO", "false")
        assert columns[("time_entries", "auto_closed")] == ("boolean", "NO", "false")
        assert columns[("time_entries", "clamp_grace_minutes")][:2] == ("integer", "YES")
        assert columns[("change_requests", "request_credit_override")] == ("boolean", "NO", "false")
        assert columns[("change_requests", "original_uncredited_minutes")][:2] == ("integer", "YES")
        assert _md5(conn, f"SELECT {OLD_TE} FROM time_entries") == te_before
        assert _md5(conn, f"SELECT {OLD_WH} FROM working_hours_changes") == wh_before
    with engine.connect() as conn:
        first_upgrade = {k: _blocks(conn, k) for k in U}

    # Mehrblock-Stand wie nach PR3 simulieren, dazu Lücken-, Anerkennungs- und Antragsdaten.
    multi = [{"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}],
              "pause_minutes": 0}] + [{"blocks": [], "pause_minutes": 0}] * 4
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET work_blocks = CAST(:j AS JSONB) WHERE id = :id"),
                     {"j": json.dumps(multi), "id": U["mehr"]})
        conn.execute(text("UPDATE time_entries SET uncredited_minutes = 150, credit_override = true "
                          "WHERE id = :id"), {"id": E["mehr"]})
        conn.execute(text(
            "INSERT INTO change_requests (tenant_id, user_id, request_type, status, reason, request_credit_override) "
            "VALUES (:t, :u, 'update', 'pending', 'x', true)"
        ), {"t": TENANT, "u": U["mehr"]})

    out = _alembic(url, "downgrade", "072_cr_sunday_reason")
    assert "*** HINWEIS (Migration 073, Downgrade) ***" in out
    assert ("mehr (Mandant 0000…0001): Mo 08:00–12:00 + 15:00–18:00 → Fenster 08:00–18:00 "
            "(wieder angerechnete Lücken: 12:00–15:00)") in out
    assert "mehr (Mandant 0000…0001): 1 Eintrag, zusammen 2,50 h" in out
    assert "1 offener Antrag „Anrechnung beantragen“ wird" in out
    with engine.connect() as conn:
        windows = {row[0]: row[1:] for row in conn.execute(text(
            f"SELECT username, {', '.join(WINDOW_COLUMNS)} FROM users ORDER BY username"
        )).all()}
        assert windows["mehr"][:2] == (time(8, 0), time(18, 0))           # Hülle, nicht 12:00
        assert windows["zwei"][8:10] == (time(7, 30), None)                 # Platzhalter 23:59 → NULL
        assert windows["halbende"][:2] == (None, time(16, 30))              # Platzhalter 00:00 → NULL
        assert windows["sek"][:2] == (time(7, 30), time(16, 30))            # Sekunden bleiben weg
        assert windows["invers"][:4] == (None, None, time(8, 0), time(16, 0))
        remaining = {c for (c,) in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name IN "
            "('work_blocks', 'blocks', 'uncredited_minutes', 'credit_override', 'auto_closed', "
            "'clamp_grace_minutes', 'request_credit_override', 'original_uncredited_minutes')"
        )).all()}
        assert remaining == set()
        assert _md5(conn, f"SELECT {OLD_TE} FROM time_entries") == te_before

    _alembic(url, "upgrade", "073_work_blocks")
    with engine.connect() as conn:
        for key in ("zwei", "halbende", "sek", "ohne", "nurinvers"):
            assert _blocks(conn, key) == first_upgrade[key], key
        assert _blocks(conn, "mehr") == [_one("08:00", "18:00")] + [EMPTY] * 4
        assert _md5(conn, f"SELECT {OLD_TE} FROM time_entries") == te_before
```

`backend/tests/test_net_hours_parity_pg.py`:

```python
"""Spec 6.1 / 17.3 (Postgres-only): SQL-Ausdruck von net_hours folgt dem
Python-Hybrid inkl. uncredited_minutes — bis auf n × 0,005 h (keine Rundung je
Zeile in SQL, sonst bräche die Byte-Identität bestehender Summen)."""
import os
import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

ADMIN_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_URL or not ADMIN_URL.startswith("postgresql"):
    pytest.skip("braucht Postgres (ADMIN_DB_URL / DATABASE_URL_MIGRATIONS)", allow_module_level=True)

from app.models import TimeEntry, User, UserRole  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402

TENANT_ID = uuid.UUID("07300000-0000-4000-8000-0000000000aa")


@pytest.fixture
def session():
    engine = create_engine(ADMIN_URL)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.rollback()
        s.execute(text("DELETE FROM time_entries WHERE tenant_id = :t"), {"t": TENANT_ID})
        s.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": TENANT_ID})
        s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": TENANT_ID})
        s.commit()
        s.close()
        engine.dispose()


def test_sql_sum_matches_python_sum(session):
    session.add(Tenant(id=TENANT_ID, name="Parität 073", slug=f"paritaet-{uuid.uuid4().hex[:8]}",
                       is_active=True, mode="multi"))
    user = User(id=uuid.uuid4(), tenant_id=TENANT_ID, username="paritaet", password_hash="x",
                first_name="P", last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40,
                vacation_days=30, work_days_per_week=5)
    session.add(user)
    session.flush()
    rows = [  # (start, end, pause, uncredited) — K1, K4, K3, K7 (gespeichert), K9, offen
        (time(8, 0), time(18, 0), 0, 150),
        (time(8, 0), time(12, 5), 0, 0),
        (time(12, 30), time(14, 30), 0, 120),
        (time(7, 45), time(18, 15), 0, 150),
        (time(8, 0), time(18, 0), 30, 150),
        (time(9, 0), None, 0, 0),
    ]
    for i, (start, end, brk, unc) in enumerate(rows):
        session.add(TimeEntry(tenant_id=TENANT_ID, user_id=user.id, date=date(2026, 6, 1 + i),
                              start_time=start, end_time=end, break_minutes=brk,
                              uncredited_minutes=unc))
    session.flush()
    entries = session.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID).all()
    py_sum = sum((e.net_hours for e in entries), Decimal("0"))
    sql_sum = session.query(func.sum(TimeEntry.net_hours)).filter(TimeEntry.tenant_id == TENANT_ID).scalar()
    closed = sum(1 for e in entries if e.end_time is not None)
    assert abs(Decimal(str(sql_sum)) - py_sum) <= Decimal("0.005") * closed
```

- [ ] **Step 2: Ohne PostgreSQL überspringen sie sich**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_073_migration_pg.py tests/test_net_hours_parity_pg.py -q -p no:cacheprovider`
Expected: `2 skipped`.

- [ ] **Step 3: Alle PostgreSQL-Suiten gegen eine Wegwerf-PG18 auf 073 (ein Shell-Aufruf, App-Rolle wie in Actions)**

Aus der Repo-Wurzel:

```bash
bash <<'BASHEOF'
set -e
PGPW=$(python3 -c 'import secrets;print(secrets.token_hex(16))'); APPPW=$(python3 -c 'import secrets;print(secrets.token_hex(16))')
S="postgres"; S="${S}ql://"
URL="${S}praxiszeit:${PGPW}@pz073-pg:5432/praxiszeit"; APPURL="${S}praxiszeit_app:${APPPW}@pz073-pg:5432/praxiszeit"
docker network create pz073 2>/dev/null || true
docker run -d --rm --name pz073-pg --network pz073 -e POSTGRES_USER=praxiszeit -e POSTGRES_PASSWORD="$PGPW" -e POSTGRES_DB=praxiszeit postgres:18-alpine > /dev/null
trap 'docker stop pz073-pg > /dev/null' EXIT
timeout 60 sh -c 'until docker exec pz073-pg pg_isready -U praxiszeit >/dev/null 2>&1; do sleep 1; done'
docker exec -i pz073-pg psql -q -U praxiszeit -d praxiszeit < backend/init-db-user.sql
docker run --rm --network pz073 -v "$PWD/backend":/app:ro -w /app --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X \
  -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost \
  -e DATABASE_URL="$URL" -e DATABASE_URL_MIGRATIONS="$URL" \
  praxiszeit-backend python -c "from alembic.config import main; main(['upgrade','head'])" 2>&1 | sed -n '/HINWEIS (Migration 073)/,/ENDE HINWEIS/p'
docker exec -i pz073-pg psql -q -U praxiszeit -d praxiszeit < backend/init-db-user.sql
docker exec pz073-pg psql -q -U praxiszeit -d praxiszeit -c "ALTER ROLE praxiszeit_app PASSWORD '${APPPW}'"
echo "Stand: $(docker exec pz073-pg psql -U praxiszeit -d praxiszeit -Atc 'SELECT version_num FROM alembic_version')"
docker run --rm --network pz073 -v "$PWD/backend":/app:ro -w /app --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X \
  -e APP_DB_USER=praxiszeit_app -e APP_DB_PASSWORD="$APPPW" -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e TZ=Europe/Berlin \
  -e DATABASE_URL="$APPURL" -e APP_DB_URL="$APPURL" -e DATABASE_URL_MIGRATIONS="$URL" -e ADMIN_DB_URL="$URL" \
  praxiszeit-backend python -m pytest tests/test_tenant_rls.py tests/test_concurrency.py tests/test_purge_user_postgres.py \
    tests/test_invalid_uuid_postgres.py tests/test_073_migration_pg.py tests/test_net_hours_parity_pg.py -q -p no:cacheprovider
BASHEOF
```

Expected: der 073-Block „*** HINWEIS (Migration 073) *** … übernommen: 0 Konten, 0 Verlaufszeilen. *** ENDE HINWEIS ***", `Stand: 073_work_blocks`, dann `52 passed` (Stand `3d46c2f`: 20 RLS + 15 Wettlauf — darunter der in Task 7 angepasste Admin-Korrektur-gegen-Betriebsferien-Test und die drei #491-API-2-Tests — + 12 Art.-17 + 3 #483 + 1 Round-Trip + 1 Parität; validiert wurde der Plan bei `b635679` mit 48 = 12 Wettlauf + 2 #483). Weicht die Zahl ab, zuerst `grep -c "^def test_" backend/tests/test_concurrency.py` und `backend/tests/test_invalid_uuid_postgres.py` zählen — die Summe muss stimmen, `failed` darf es nicht geben. Scheitert `test_admin_time_entry_edit_does_not_deadlock_with_a_parallel_closure` mit `("deadlock",)`, ist die Ankersperre in `admin_update_time_entry` nicht die erste Sperre (Task 7) — den Test nicht lockern.

Nachtrag aus dem Review zu Task 14: `test_073_migration_pg.py` hat einen zweiten Test, `test_073_backfill_as_owner_under_force_rls`. Er hebt eine eigene Wegwerf-Datenbank als Superuser auf 072, überträgt alle `public`-Tabellen an eine Rolle `pz073_owner_<hex>` (LOGIN NOSUPERUSER NOBYPASSRLS) und lässt 073 als diese Rolle laufen. Geprüft wird „übernommen: 1 Konto, 1 Verlaufszeile.", nicht das Fehlen der „(RLS?)"-Zeile. Nur so greift FORCE RLS: `praxiszeit` ist in Docker, Actions und auf der Prod-Kopie Superuser und umgeht RLS. Außerdem vergleicht der Round-Trip-Test jetzt `time_entries` und `working_hours_changes` vollständig und `users` ohne die zehn Fensterspalten. Die Spaltenlisten kommen im Stand 072 aus `information_schema`. Verglichen wird nach dem Upgrade, nach dem Downgrade und nach dem erneuten Upgrade. Die Downgrade-Diagnose für `credit_override` wird wörtlich zugesichert. Nach dem ersten Upgrade sichert der Round-Trip-Test außerdem zu, dass keine Zeile „Abweichung“ erscheint (Spec 17.1, Konto `nurinvers`): Er ist der einzige Lauf, in dem die Zählprobe rechnet, und die Mutation `expected += 1` vor `if week is None` lief ohne diese Zeile grün. Im Eigentümer-Test steht sie bewusst nicht, dort gibt es kein nur invertiertes Konto, und sein Docstring erklärt, warum ihr Fehlen unter RLS nichts belegt. Die Zahl in Step 3 steigt damit um eins (Lauf nach dem Review: `57 passed` = 20 RLS + 19 Wettlauf + 12 Art. 17 + 3 #483 + 2 Migration 073 + 1 Parität).

- [ ] **Step 4: In Actions einhängen**

`.github/workflows/cross-tenant-ci.yml`, Schritt „Unit + cross-tenant suite (SQLite)" — nach `--ignore=tests/test_invalid_uuid_postgres.py \` zwei Zeilen:

```yaml
            --ignore=tests/test_073_migration_pg.py \
            --ignore=tests/test_net_hours_parity_pg.py \
```

Schritt „Cross-tenant RLS + Art.17 purge + Race-Tests (real Postgres)" — die `pytest`-Zeilen werden:

```yaml
          pytest tests/test_tenant_rls.py tests/test_purge_user_postgres.py \
            tests/test_concurrency.py tests/test_invalid_uuid_postgres.py \
            tests/test_073_migration_pg.py tests/test_net_hours_parity_pg.py \
            -p no:asyncio -v
```

(Im SQLite-Schritt ist `ADMIN_DB_URL` bereits gesetzt, die Datenbank aber noch nicht migriert — ohne `--ignore` liefen beide Dateien dort gegen ein leeres Schema.)

- [ ] **Step 5: In `scripts/local-ci.sh` einhängen**

Schritt 1 — nach `--ignore=tests/test_tenant_rls.py \`:

```bash
       --ignore=tests/test_073_migration_pg.py \
       --ignore=tests/test_net_hours_parity_pg.py \
```

Schritt 2 — die Dateiliste wird

```bash
       tests/test_tenant_rls.py tests/test_concurrency.py \
       tests/test_purge_user_postgres.py tests/test_invalid_uuid_postgres.py \
       tests/test_073_migration_pg.py tests/test_net_hours_parity_pg.py \
```

und die beiden Kommentarzeilen darüber

```bash
# Reference counts: step 2 runs 46 tests against real Postgres
# (20 RLS + 12 concurrency + 12 Art.-17 purge + 2 invalid-UUID #483); the 18 cross-tenant tests run
```

werden zu

```bash
# Reference counts: step 2 runs 52 tests against real Postgres
# (20 RLS + 15 concurrency + 12 Art.-17 purge + 3 invalid-UUID #483 + 1 migration-073
# round trip + 1 net_hours parity); the 18 cross-tenant tests run
```

(Der alte Kommentar nannte bei `3d46c2f` noch 46 — die Lanes haben drei Wettlauf- und einen #483-Test ergänzt, ohne ihn nachzuziehen.)

Kontrolle: `bash -n scripts/local-ci.sh` ohne Ausgabe.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_073_migration_pg.py backend/tests/test_net_hours_parity_pg.py .github/workflows/cross-tenant-ci.yml scripts/local-ci.sh
git commit -F - <<'EOF'
test(bloecke): Migration 073 und net_hours-Parität gegen echtes PostgreSQL, in Actions und local-ci

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 15: Frontend — UserForm ohne Fenster-Abschnitt, Anzeige der heute gültigen Blöcke (E62, 12.2)

**Files:**
- Create: `frontend/src/types/workBlocks.ts`, `frontend/src/utils/workBlocks.ts`, `frontend/src/utils/workBlocks.test.ts`
- Modify: `frontend/src/types/user.ts:1-54`
- Modify: `frontend/src/pages/admin/users/UserForm.tsx` (Props 14-50, `formData` 90-99, Edit-Vorbelegung 142-151, Payload 227-236, Anzeige ~347, Fenster-Abschnitt 942-977)
- Modify: `frontend/src/pages/admin/Users.tsx:183-184, 390-398`
- Modify: `frontend/src/pages/admin/Users.test.tsx` (Import, `FakeUserForm`-Props/Anzeige, Fixture 142-151, neuer `describe`-Block)
- Test: `frontend/src/pages/admin/users/UserForm.test.tsx` (neuer `describe`-Block)

**Interfaces:**
- Consumes: Antwortfelder `work_blocks`, `work_blocks_today` aus `GET /api/admin/users` (Task 11); JSON-Form Spec 3.1
- Produces:
  - `types/workBlocks.ts`: `interface TimeBlock { start: string; end: string }`, `interface DayBlocks { blocks: TimeBlock[]; pause_minutes: number | null }`, `type WeekBlocks = DayBlocks[]`
  - `utils/workBlocks.ts`: `WEEKDAY_LABELS = ['Mo','Di','Mi','Do','Fr'] as const`, `isLegacyWeek(week: WeekBlocks | null | undefined): boolean`, `formatWeekBlocks(week: WeekBlocks | null | undefined): string | null` — PR2/PR3 ergänzen hier `notCreditedMinutes`, `gapSegments`, `deriveTargets`
  - `User.work_blocks?: WeekBlocks | null`, `User.work_blocks_today?: WeekBlocks | null`; `scheduled_*` entfällt aus `User`
  - `UserForm`-Prop `displayBlocks?: WeekBlocks | null`; Anzeige „Arbeitszeit heute" (`aria-labelledby="f-work-blocks-label"`) nur beim Bearbeiten; weder POST- noch PUT-Payload tragen `scheduled_*`, `work_blocks` oder `work_blocks_today`

- [ ] **Step 1: Failing tests schreiben**

`frontend/src/utils/workBlocks.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { formatWeekBlocks, isLegacyWeek } from './workBlocks';
import type { WeekBlocks } from '../types/workBlocks';

const EMPTY_NEW = { blocks: [], pause_minutes: 0 };
const EMPTY_LEGACY = { blocks: [], pause_minutes: null };

const NEW_WEEK: WeekBlocks = [
  { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
  { blocks: [{ start: '08:00', end: '13:00' }], pause_minutes: 0 },
  EMPTY_NEW, EMPTY_NEW, EMPTY_NEW,
];

const LEGACY_WEEK: WeekBlocks = [
  { blocks: [{ start: '07:37', end: '16:30' }], pause_minutes: null },
  EMPTY_LEGACY, EMPTY_LEGACY, EMPTY_LEGACY,
  { blocks: [{ start: '07:30', end: '23:59' }], pause_minutes: null },
];

describe('formatWeekBlocks (Spec 12.2)', () => {
  it('nennt nur Tage mit Blöcken, Pause nur wenn > 0', () => {
    expect(formatWeekBlocks(NEW_WEEK)).toBe('Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00');
  });

  it('zeigt Altwerte und Platzhalter unverändert', () => {
    expect(formatWeekBlocks(LEGACY_WEEK)).toBe('Mo 07:37–16:30 · Fr 07:30–23:59');
  });

  it('liefert null ohne Blöcke', () => {
    expect(formatWeekBlocks(null)).toBeNull();
    expect(formatWeekBlocks(undefined)).toBeNull();
    expect(formatWeekBlocks([EMPTY_NEW, EMPTY_NEW, EMPTY_NEW, EMPTY_NEW, EMPTY_NEW])).toBeNull();
  });
});

describe('isLegacyWeek (Spec 3.3)', () => {
  it('erkennt Altzeilen an pause_minutes null', () => {
    expect(isLegacyWeek(LEGACY_WEEK)).toBe(true);
    expect(isLegacyWeek(NEW_WEEK)).toBe(false);
    expect(isLegacyWeek(null)).toBe(false);
  });
});
```

An `frontend/src/pages/admin/users/UserForm.test.tsx` anhängen:

```tsx
describe('Spec 2026-10-08 (PR1): Arbeitszeit-Blöcke statt Soll-Fenster', () => {
  const baseEditUser = {
    id: 'u1', username: 'jd', first_name: 'Jane', last_name: 'Doe', role: 'employee',
    weekly_hours: 40, vacation_days: 30, work_days_per_week: 5, track_hours: true,
    is_active: true, use_daily_schedule: false,
  };
  const empty = { blocks: [], pause_minutes: 0 };
  const TWO_BLOCKS = [
    { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
    empty, empty, empty, empty,
  ];
  const legacyEmpty = { blocks: [], pause_minutes: null };
  const LEGACY = [
    { blocks: [{ start: '07:37', end: '16:30' }], pause_minutes: null },
    legacyEmpty, legacyEmpty, legacyEmpty,
    { blocks: [{ start: '07:30', end: '23:59' }], pause_minutes: null },
  ];

  async function fillAndSave() {
    fireEvent.change(screen.getByLabelText(/Benutzername/i), { target: { value: 'newemployee' } });
    fireEvent.change(screen.getByLabelText('Passwort *'), { target: { value: 'TestPass123!' } });
    fireEvent.change(screen.getByLabelText('Vorname'), { target: { value: 'New' } });
    fireEvent.change(screen.getByLabelText('Nachname'), { target: { value: 'User' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
  }

  it('zeigt keine Soll-Fenster-Felder mehr (Anlegen und Bearbeiten)', () => {
    const { unmount } = renderForm();
    expect(screen.queryByLabelText(/Soll-Beginn/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Soll-Arbeitszeiten je Wochentag/)).not.toBeInTheDocument();
    unmount();
    renderForm({ editUser: baseEditUser });
    expect(screen.queryByLabelText(/Soll-Ende/)).not.toBeInTheDocument();
  });

  it('POST-Payload trägt keinen Schlüssel mit Präfix scheduled_ (sonst 400)', async () => {
    renderForm();
    await fillAndSave();
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const keys = Object.keys(postMock.mock.calls[0][1] as object);
    expect(keys.filter((k) => k.startsWith('scheduled_'))).toEqual([]);
    expect(keys).not.toContain('work_blocks');
  });

  it('PUT-Payload trägt weder scheduled_* noch work_blocks/work_blocks_today (sonst 400)', async () => {
    renderForm({ editUser: { ...baseEditUser, work_blocks: LEGACY, work_blocks_today: LEGACY } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => /\/admin\/users\/u1$/.test(String(c[0])));
      expect(call).toBeTruthy();
      const keys = Object.keys(call![1] as object);
      expect(keys.filter((k) => k.startsWith('scheduled_'))).toEqual([]);
      expect(keys).not.toContain('work_blocks');
      expect(keys).not.toContain('work_blocks_today');
    });
  });

  it('zeigt beim Bearbeiten die heute gültigen Blöcke (displayBlocks)', () => {
    renderForm({ editUser: baseEditUser, displayBlocks: TWO_BLOCKS });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent(
      'Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min)',
    );
    expect(screen.queryByText(/Altbestand/)).not.toBeInTheDocument();
  });

  it('kennzeichnet ein Altfenster aus Migration 073 und zeigt Altwerte unverändert', () => {
    renderForm({ editUser: { ...baseEditUser, work_blocks_today: LEGACY } });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Mo 07:37–16:30 · Fr 07:30–23:59');
    expect(screen.getByText(/Altbestand: kappt die erfasste Zeit/)).toBeInTheDocument();
  });

  // E63/P2: ohne Stundenzählung kappt das Backend nie (`_clamp_core`/`clamp_applies`
  // brechen bei track_hours=False ab), 073 übernimmt Altfenster aber unabhängig davon.
  // Der Kappungs-Hinweis wäre dort eine falsche Aussage.
  it('Altfenster bei track_hours=false: kein Kappungs-Hinweis, sondern „ohne Wirkung"', () => {
    renderForm({ editUser: { ...baseEditUser, track_hours: false, work_blocks_today: LEGACY } });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Mo 07:37–16:30 · Fr 07:30–23:59');
    expect(screen.queryByText(/kappt die erfasste Zeit/)).not.toBeInTheDocument();
    expect(screen.getByText(/Altbestand gespeichert, ohne Wirkung \(keine Stundenzählung\)/)).toBeInTheDocument();
  });

  it('Blöcke bei track_hours=false: „gespeichert, ohne Wirkung" (Wortlaut wie im Dialog, Spec 12.1)', () => {
    renderForm({ editUser: { ...baseEditUser, track_hours: false }, displayBlocks: TWO_BLOCKS });
    expect(screen.getByText('Arbeitszeit-Blöcke gespeichert, ohne Wirkung (keine Stundenzählung).')).toBeInTheDocument();
    expect(screen.queryByText(/Altbestand/)).not.toBeInTheDocument();
  });

  it('Hinweis folgt dem Haken „Stundenzählung aktiv" im Formular', () => {
    renderForm({ editUser: { ...baseEditUser, work_blocks_today: LEGACY } });
    expect(screen.getByText(/Altbestand: kappt die erfasste Zeit/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Stundenzählung aktiv/));
    expect(screen.queryByText(/kappt die erfasste Zeit/)).not.toBeInTheDocument();
    expect(screen.getByText(/Altbestand gespeichert, ohne Wirkung/)).toBeInTheDocument();
  });

  it('ohne Blöcke bei track_hours=false: kein „ohne Wirkung"-Hinweis', () => {
    renderForm({ editUser: { ...baseEditUser, track_hours: false }, displayBlocks: null });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Keine Arbeitszeit-Blöcke hinterlegt');
    expect(screen.queryByText(/ohne Wirkung/)).not.toBeInTheDocument();
  });

  it('ohne Blöcke: „Keine Arbeitszeit-Blöcke hinterlegt"', () => {
    renderForm({ editUser: baseEditUser, displayBlocks: null });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Keine Arbeitszeit-Blöcke hinterlegt');
  });

  // Vorrangregel nach dem Muster `displayDayHours` (Spec 12.2, vgl. #431 Fund 3):
  // ein frisch nachgeführtes `displayBlocks = null` (Fenster entfernt, Verlaufszeile
  // gelöscht) schlägt den beim Öffnen übergebenen Stand. Ein `??` an dieser Stelle
  // fiele auf das alte Altfenster samt Altbestand-Hinweis zurück.
  it('frisches displayBlocks=null schlägt veraltete editUser.work_blocks_today', () => {
    renderForm({ editUser: { ...baseEditUser, work_blocks_today: LEGACY }, displayBlocks: null });
    expect(screen.getByLabelText('Arbeitszeit heute')).toHaveTextContent('Keine Arbeitszeit-Blöcke hinterlegt');
    expect(screen.queryByText(/Altbestand/)).not.toBeInTheDocument();
  });

  it('beim Anlegen keine Blöcke-Anzeige (der Editor folgt mit PR3)', () => {
    renderForm();
    expect(screen.queryByLabelText('Arbeitszeit heute')).not.toBeInTheDocument();
  });
});
```

`frontend/src/pages/admin/Users.test.tsx` — nach `import type { User } from '../../types/user';`:

```tsx
import type { WeekBlocks } from '../../types/workBlocks';
```

in den Props von `FakeUserForm` nach `displayUseDailySchedule?: boolean;`:

```tsx
  // Spec 2026-10-08 (E62/12.2): heute gültige Blöcke, gleiche Bauart.
  displayBlocks?: WeekBlocks | null;
```

im JSX von `FakeUserForm` direkt vor `<span data-testid="display-use-daily-schedule">`:

```tsx
      <span data-testid="display-blocks">
        {props.displayBlocks === undefined ? 'undefined' : JSON.stringify(props.displayBlocks)}
      </span>
```

und am Dateiende:

```tsx
describe('Spec 2026-10-08 (PR1): heute gültige Blöcke werden mit nachgezogen', () => {
  it('reicht work_blocks_today als displayBlocks durch und zieht es nach einer Dialog-Speicherung nach', async () => {
    const before: WeekBlocks = [
      { blocks: [{ start: '08:00', end: '17:00' }], pause_minutes: null },
      { blocks: [], pause_minutes: null }, { blocks: [], pause_minutes: null },
      { blocks: [], pause_minutes: null }, { blocks: [], pause_minutes: null },
    ];
    let today: WeekBlocks | null = before;
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/admin/users-overview')) return Promise.resolve({ data: [] });
      if (String(url) === '/admin/users') {
        return Promise.resolve({ data: [makeUser({ work_blocks_today: today })] });
      }
      return Promise.resolve({ data: [] });
    });

    renderPage();
    await screen.findAllByText('Doe, Jane');
    fireEvent.click(screen.getAllByTitle('Bearbeiten')[0]);
    await screen.findByTestId('fake-user-form');
    expect(screen.getByTestId('display-blocks')).toHaveTextContent('"start":"08:00","end":"17:00"');

    fireEvent.click(screen.getByText('Wochenstunden anpassen…'));
    today = null;
    fireEvent.click(screen.getByText('Stundenänderung speichern (simuliert)'));

    await waitFor(() => expect(screen.getByTestId('display-blocks')).toHaveTextContent('null'));
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/utils/workBlocks.test.ts src/pages/admin/users/UserForm.test.tsx src/pages/admin/Users.test.tsx --pool=threads`
Expected: FAIL — `workBlocks.test.ts`: „Failed to resolve import ./workBlocks" (bzw. `../types/workBlocks`); `UserForm.test.tsx`: „zeigt keine Soll-Fenster-Felder mehr", die beiden Payload-Tests (`scheduled_start_monday` u. a. im Payload) und die acht Anzeige-Tests (u. a. „Unable to find a label with the text of: Arbeitszeit heute"; nur „beim Anlegen keine Blöcke-Anzeige" ist schon grün); `Users.test.tsx`: der neue Test (`display-blocks` zeigt „undefined").

- [ ] **Step 3: Typen und Helfer anlegen**

`frontend/src/types/workBlocks.ts`:

```ts
// Spec 2026-10-08, Abschnitt 3.1: kanonische JSON-Form der Arbeitszeit-Blöcke
// (users.work_blocks / working_hours_changes.blocks). Genau fünf Einträge,
// Index 0 = Montag … 4 = Freitag; Zeiten als "HH:MM".
export interface TimeBlock {
  start: string;
  end: string;
}

export interface DayBlocks {
  blocks: TimeBlock[];
  // null = Altfenster aus Migration 073: kappt nur, treibt kein Tagessoll.
  pause_minutes: number | null;
}

export type WeekBlocks = DayBlocks[];
```

`frontend/src/utils/workBlocks.ts`:

```ts
// Spec 2026-10-08: Anzeige-Helfer für Arbeitszeit-Blöcke. PR2/PR3 ergänzen hier
// die Zwillinge der Backend-Rechenhelfer (notCreditedMinutes, gapSegments,
// deriveTargets) — jeweils mit wortgleichen Testfällen.
import type { WeekBlocks } from '../types/workBlocks';

export const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr'] as const;

/** Spec 3.3: eine Altzeile (aus Migration 073) trägt an mindestens einem Tag
 * keine Pausenangabe (`pause_minutes === null`). */
export function isLegacyWeek(week: WeekBlocks | null | undefined): boolean {
  return Array.isArray(week) && week.some((day) => day?.pause_minutes === null);
}

/** „Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00" — nur Tage
 * mit Blöcken, „(Pause …)" nur bei Pause > 0; `null`, wenn kein Tag Blöcke hat.
 * Altwerte (07:37, Platzhalter 23:59) werden unverändert angezeigt (Spec 4.4). */
export function formatWeekBlocks(week: WeekBlocks | null | undefined): string | null {
  if (!Array.isArray(week)) return null;
  const parts = week.flatMap((day, index) => {
    const blocks = day?.blocks ?? [];
    if (blocks.length === 0 || index >= WEEKDAY_LABELS.length) return [];
    const spans = blocks.map((block) => `${block.start}–${block.end}`).join(' + ');
    const pause = day.pause_minutes ? ` (Pause ${day.pause_minutes} Min)` : '';
    return [`${WEEKDAY_LABELS[index]} ${spans}${pause}`];
  });
  return parts.length > 0 ? parts.join(' · ') : null;
}
```

`frontend/src/types/user.ts` — nach dem Kopfkommentar (vor `export interface User {`):

```ts
import type { WeekBlocks } from './workBlocks';

```

die zehn Felder `scheduled_start_monday: string | null;` … `scheduled_end_friday: string | null;` löschen und am Ende des Interfaces nach `vacation_carryover_deadline?: string | null;`:

```ts
  // Spec 2026-10-08 (11.1/11.5): Rohwert der User-Zeile und die für HEUTE
  // datumsaufgelösten Blöcke (Admin-Liste/-Detail, Login). Nur Anzeige — die
  // Blöcke ändern sich ausschließlich über den Verlauf mit Wirkungsdatum.
  work_blocks?: WeekBlocks | null;
  work_blocks_today?: WeekBlocks | null;
```

- [ ] **Step 4: `UserForm.tsx`**

Importe nach `import { PASTEL_COLORS, DEFAULT_CALENDAR_COLOR } from '../../../utils/calendarColors';`:

```ts
import { formatWeekBlocks, isLegacyWeek } from '../../../utils/workBlocks';
```

und nach `import type { User } from '../../../types/user';`:

```ts
import type { WeekBlocks } from '../../../types/workBlocks';
```

In `UserFormProps` nach `displayUseDailySchedule?: boolean;`:

```ts
  // Spec 2026-10-08 (E62/12.2): die heute gültigen Arbeitszeit-Blöcke des
  // bearbeiteten Nutzers (serverseitig datumsaufgelöst, `work_blocks_today`),
  // wie `displayDayHours` frisch aus Users.tsx nachgeführt. Nur Anzeige.
  displayBlocks?: WeekBlocks | null;
```

Destrukturierung der Props: `displayWorkDays, displayUseDailySchedule, displayBlocks,`.

Die zehn `scheduled_*`-Schlüssel löschen — in `useState({...})` (`scheduled_start_monday: '',` … `scheduled_end_friday: '',`), in der Edit-Vorbelegung (`scheduled_start_monday: editUser.scheduled_start_monday?.substring(0, 5) || '',` … ) und im `payload` (`scheduled_start_monday: formData.scheduled_start_monday || null,` …). Ohne das endet mit Task 11 jedes Anlegen und Bearbeiten mit 400 „Bitte Seite neu laden".

Nach `const weeklyHoursDisplay = …;`:

```ts
  // Spec 2026-10-08 (E62/12.2): heute gültige Blöcke — frisch aus Users.tsx
  // (`displayBlocks`), sonst aus dem beim Öffnen übergebenen Nutzer.
  const shownBlocks = displayBlocks !== undefined ? displayBlocks : (editUser?.work_blocks_today ?? null);
  const workBlocksText = formatWeekBlocks(shownBlocks);
```

Den kompletten Abschnitt ab `{/* Soll-Arbeitszeiten (Arbeitszeit-Fenster) */}` bis einschließlich des `<p className="text-xs text-gray-500 mt-2">Oben: Soll-Beginn · Unten: Soll-Ende</p>` und des schließenden `</div>` ersetzen durch:

```tsx
          {/* Spec 2026-10-08 (E62): heute gültige Arbeitszeit-Blöcke — nur Anzeige.
              Geändert werden sie ausschließlich über den Verlauf mit Wirkungsdatum. */}
          {editUser && (
            <div className="md:col-span-2 border border-gray-200 rounded-lg p-4">
              <p id="f-work-blocks-label" className="text-sm font-medium text-gray-700 mb-1">
                Arbeitszeit heute
              </p>
              <div aria-labelledby="f-work-blocks-label" className="text-sm text-gray-800">
                {workBlocksText ?? 'Keine Arbeitszeit-Blöcke hinterlegt'}
              </div>
              {/* E63: ohne Stundenzählung wirken weder Soll noch Kappung — das
                  Backend kappt dann nie (`clamp_applies`/`_clamp_core`), 073
                  übernimmt Altfenster aber unabhängig von track_hours (P2).
                  Wortlaut wie im Dialog (Spec 12.1). */}
              {workBlocksText && !formData.track_hours && (
                <p className="text-xs text-gray-500 mt-1">
                  {isLegacyWeek(shownBlocks)
                    ? 'Arbeitszeit-Fenster aus dem Altbestand gespeichert, ohne Wirkung (keine Stundenzählung).'
                    : 'Arbeitszeit-Blöcke gespeichert, ohne Wirkung (keine Stundenzählung).'}
                </p>
              )}
              {workBlocksText && formData.track_hours && isLegacyWeek(shownBlocks) && (
                <p className="text-xs text-gray-500 mt-1">
                  Arbeitszeit-Fenster aus dem Altbestand: kappt die erfasste Zeit, ändert das Tagessoll nicht.
                </p>
              )}
            </div>
          )}
```

Die Edit-`PUT`-Destrukturierung (`const { password, weekly_hours, … } = payload;`) bleibt: `payload` wird aus `formData` gebaut, das weder `work_blocks` noch `work_blocks_today` enthält — der PUT-Test aus Step 1 hält das fest.

- [ ] **Step 5: `Users.tsx` und `Users.test.tsx`**

`frontend/src/pages/admin/Users.tsx` — nach `const displayUseDailySchedule = freshEditingUser?.use_daily_schedule;`:

```ts
  // Spec 2026-10-08 (E62/12.2): dieselbe Bauart für die heute gültigen Blöcke.
  const displayBlocks = freshEditingUser ? (freshEditingUser.work_blocks_today ?? null) : undefined;
```

und im `<UserForm …>` nach `displayUseDailySchedule={displayUseDailySchedule}`:

```tsx
          displayBlocks={displayBlocks}
```

`frontend/src/pages/admin/Users.test.tsx` — in der Fixture die zehn Zeilen `scheduled_start_monday: null,` … `scheduled_end_friday: null,` löschen (sonst meldet `tsc` unbekannte Eigenschaften am Typ `User`).

- [ ] **Step 6: Tests, Typen, Lint**

Run (aus `frontend/`):
- `npx vitest run src/utils/workBlocks.test.ts src/pages/admin/users/UserForm.test.tsx src/pages/admin/Users.test.tsx --pool=threads` → PASS
- `npx vitest run --pool=threads` → alle Dateien grün (bei der Planung: 41 Dateien, 418 Tests; gemergte Issue-Lanes erhöhen die Zahl)
- `npx tsc --noEmit` → keine Ausgabe
- `npx eslint src/pages/admin/users/UserForm.tsx src/pages/admin/Users.tsx src/utils/workBlocks.ts src/utils/workBlocks.test.ts src/types/workBlocks.ts src/types/user.ts` → `0 errors` (die vorhandenen Warnungen zu ungenutzten Destrukturierungs-Variablen bleiben)
- `grep -rn "scheduled_" src/` → keine Ausgabe

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/workBlocks.ts frontend/src/utils/workBlocks.ts frontend/src/utils/workBlocks.test.ts frontend/src/types/user.ts frontend/src/pages/admin/users/UserForm.tsx frontend/src/pages/admin/users/UserForm.test.tsx frontend/src/pages/admin/Users.tsx frontend/src/pages/admin/Users.test.tsx
git commit -F - <<'EOF'
feat(bloecke): UserForm ohne Soll-Fenster, zeigt die heute gültigen Arbeitszeit-Blöcke

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 16: E2E — Prod-Release-Spec und visueller Beleg auf Blöcke umstellen (17.8)

**Files:**
- Modify: `e2e/tests/admin/prod-release-features.spec.ts:1-10` (Kopfkommentar), `:40-67` (Test „#201 + #189")
- Modify: `e2e/tests/shared/visual-prod-release.spec.ts:19-25`

Die Fixtures (`e2e/fixtures/test-data.fixture.ts`: `testEmployee`, `createUser`, `createTimeEntry`) senden keine `scheduled_*`-Felder und lesen keine — sie brauchen in PR1 keine Änderung (Kontrolle: `grep -rn "scheduled_" e2e/fixtures` ohne Ausgabe). `user-management.spec.ts` (Knopf „Wochenstunden anpassen…") bleibt bis PR3.

**Interfaces:**
- Consumes: 400-Text für Altfelder (Task 11), UserForm ohne Fenster-Abschnitt (Task 15), Antwortfelder `work_blocks`/`work_blocks_today` (Task 11)
- Produces: E2E-Absicherung „kein Soll-Fenster-Feld im Formular, Altfelder per API → 400, Betriebsferien-Flag weiter gespeichert"

- [ ] **Step 1: Test umschreiben**

`e2e/tests/admin/prod-release-features.spec.ts` — im Kopfkommentar „#201 Soll-Arbeitszeit-Fenster + Puffer" → „#201 → Arbeitszeit-Blöcke (Spec 2026-10-08)". Den Test `'#201 + #189: Soll-Arbeitszeit-Fenster und Betriebsferien-Flag werden gespeichert'` vollständig ersetzen durch:

```ts
  test('#201 → Blöcke + #189: kein Soll-Fenster im Formular, Altfelder per API abgelehnt, Betriebsferien-Flag gespeichert', async ({ adminPage, adminApi }) => {
    const username = `e2e_ww_${Date.now()}`;
    try {
      await openNewUserForm(adminPage);
      await fillRequired(adminPage, username);

      // Spec 2026-10-08 (E62/12.2): die #201-Fenster sind mit Migration 073 in
      // Arbeitszeit-Blöcke übergegangen — das Formular hat keine Fensterfelder mehr.
      await expect(adminPage.getByLabel('Soll-Beginn Mo')).toHaveCount(0);
      await expect(adminPage.getByLabel('Soll-Ende Mo')).toHaveCount(0);

      // #189: Teilnahme an Betriebsferien abwählen
      await adminPage.locator('#receives_company_closures').uncheck();

      await adminPage.getByRole('button', { name: 'Speichern' }).click();
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: 'erstellt' })
      ).toBeVisible({ timeout: 10000 });

      // Persistenz über die API verifizieren
      const users = await adminApi.get('/admin/users?include_inactive=true');
      const created = users.find((u: any) => u.username === username);
      expect(created, 'created user should exist').toBeTruthy();
      expect(Object.keys(created).filter((k) => k.startsWith('scheduled_'))).toEqual([]);
      expect(created.work_blocks ?? null).toBeNull();
      expect(created.work_blocks_today ?? null).toBeNull();
      expect(created.receives_company_closures).toBe(false);

      // E26: ein gecachtes altes Frontend schickt die Altfelder mit → 400, nichts gespeichert.
      await expect(
        adminApi.put(`/admin/users/${created.id}`, { first_name: 'Alt', scheduled_start_monday: '09:00' })
      ).rejects.toThrow(/failed: 400 .*Bitte Seite neu laden/);
      const again = (await adminApi.get('/admin/users?include_inactive=true'))
        .find((u: any) => u.id === created.id);
      expect(again.first_name).toBe('E2E');
    } finally {
      await cleanup(adminApi, username);
    }
  });
```

`e2e/tests/shared/visual-prod-release.spec.ts` — der Test `'Benutzerformular: Flags + Soll-Arbeitszeit-Fenster (#189/#191/#201)'` heißt künftig `'Benutzerformular: Flags ohne Soll-Fenster (#189/#191, Spec 2026-10-08)'` und speichert nach `${SHOTS}/02-userform-flags.png` statt `02-userform-flags-workwindow.png`; der Settings-Test bleibt (der Puffer ist weiter eine Einstellung).

- [ ] **Step 2: Specs übersetzen lassen (ohne Server)**

Run (aus `e2e/`): `npx --no-install playwright test --list tests/admin/prod-release-features.spec.ts tests/shared/visual-prod-release.spec.ts`
Expected: „Total: 8 tests in 2 files", darunter „#201 → Blöcke + #189: kein Soll-Fenster im Formular, …" und „Benutzerformular: Flags ohne Soll-Fenster (#189/#191, Spec 2026-10-08)" — kein Übersetzungsfehler (`e2e/` hat kein eigenes `tsc`; Playwright übersetzt die Specs selbst).

- [ ] **Step 3: E2E-Lauf gegen den lokalen Stack (nur nach Absprache)**

⚠ Der Docker-Stack (`:80`) ist geteilt; `docker compose up -d backend` führt beim Start `alembic upgrade head` aus und löscht damit `users.scheduled_*` in der Dev-Datenbank. Nur starten, wenn keine andere Lane den Stack nutzt; danach zurück auf `072_cr_sunday_reason`, bevor `master`-Code wieder läuft.

```bash
grep -q '^LOGIN_RATE_LIMIT=' .env || echo 'LOGIN_RATE_LIMIT=10000/minute' >> .env
grep -q '^REFRESH_RATE_LIMIT=' .env || echo 'REFRESH_RATE_LIMIT=10000/minute' >> .env
docker compose build backend frontend && docker compose up -d
cd e2e && npx playwright test tests/admin/prod-release-features.spec.ts tests/shared/visual-prod-release.spec.ts --output=/tmp/pz-e2e-pr1
```

Expected: alle Tests der beiden Dateien grün. Zurücksetzen nach dem Lauf (gleiche Shell, Repo-Wurzel):

```bash
docker compose exec -T backend python -c "from alembic.config import main; main(['downgrade','072_cr_sunday_reason'])" </dev/null
```

Die `.env`-Zeilen nur entfernen, wenn sie in diesem Schritt angelegt wurden.

- [ ] **Step 4: Commit**

```bash
git add e2e/tests/admin/prod-release-features.spec.ts e2e/tests/shared/visual-prod-release.spec.ts
git commit -F - <<'EOF'
test(e2e): Prod-Release-Spec auf Arbeitszeit-Blöcke umgestellt (kein Soll-Fenster, Altfelder 400)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 17: Byte-Identität auf der Prod-Kopie (Erfolgskriterium 4, 17.1 „Postgres-Round-Trip mit der Prod-Kopie")

**Voraussetzung:** Container `pz073-prod` aus Task 0 Step 3 (Netz `pz073`, Prod-Kopie auf `072_cr_sunday_reason`). Ist er weg, Task 0 Step 3 wiederholen lassen. Die Ausgaben dieses Tasks enthalten personenbezogene Daten — sie bleiben in einem Arbeitsverzeichnis **außerhalb** des Repos und werden nie eingecheckt; in den PR wandert nur das Ergebnis („identisch", Anzahl Personen/Einträge, die Diagnose-Zählzeile).

**Files:**
- Create: `tools/migration-073/probe_073.py`

**Interfaces:**
- Consumes: Migration `073_work_blocks` (Task 13); Code-Stand vor PR1 (`.git/pr1-base` aus Task 0 Step 5, d. h. `$(git rev-parse --git-dir)/pr1-base` — Kopf des Integrationszweigs mit den Lane-Merges, **nicht** `git merge-base HEAD master`) und PR1-Stand; nur Funktionen, die in beiden gleich heißen: `calculation_service.get_schedule_for_date`, `get_daily_target_for_date`, `get_monthly_target`, `get_monthly_actual`, `get_overtime_account`, `TimeEntry.net_hours`
- Produces: `tools/migration-073/probe_073.py` (sortiertes JSON je Person: `net_hours` je Eintrag, Tagessoll je Kalendertag, Monats-Soll/-Ist, Überstundensaldo); Nachweis „vorher == nachher" und „073 → 072 → 073 ändert keine Bestandsspalte außer den diagnostizierten Fenstern"

- [ ] **Step 1: Probe-Skript anlegen**

`tools/migration-073/probe_073.py`:

```python
"""Spec 2026-10-08, Erfolgskriterium 4 / 17.1: Byte-Identität über Migration 073.

Schreibt je Person (sortiertes JSON nach stdout): ``net_hours`` je Eintrag,
Tagessoll je Kalendertag, Monats-Soll/-Ist je Monat und den Überstundensaldo —
vom ersten Eintrag bis heute. Läuft einmal mit dem Code VOR PR1 (.git/pr1-base) gegen
die Prod-Kopie auf 072 und einmal mit dem PR1-Code gegen dieselbe Kopie auf
073; ``diff`` der beiden Ausgaben muss leer sein.

Nutzt nur Funktionen, die es in 1.19.3 und nach PR1 gleichlautend gibt.
Aufruf im Backend-Image, Arbeitsverzeichnis = Backend der jeweiligen Version:
    python /probe/probe_073.py > /out/<name>.json
"""
import json
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from app.database import SessionLocal, set_superadmin_context  # noqa: E402
from app.models import TimeEntry, User  # noqa: E402
from app.services import calculation_service as cs  # noqa: E402
from app.services.timezone_service import today_local  # noqa: E402


def _months(first: date, last: date):
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def main() -> None:
    db = SessionLocal()
    set_superadmin_context(db)
    today = today_local()
    result = {}
    for user in db.query(User).filter(User.tenant_id.isnot(None)).order_by(User.id).all():
        entries = (
            db.query(TimeEntry)
            .filter(TimeEntry.user_id == user.id, TimeEntry.tenant_id == user.tenant_id)
            .order_by(TimeEntry.id)
            .all()
        )
        first = min((e.date for e in entries), default=today)
        daily, day = {}, first
        while day <= today:
            schedule = cs.get_schedule_for_date(db, user, day)
            daily[day.isoformat()] = str(cs.get_daily_target_for_date(user, day, schedule))
            day += timedelta(days=1)
        result[str(user.id)] = {
            "net_hours": {str(e.id): str(e.net_hours) for e in entries},
            "daily_target": daily,
            "months": {
                f"{y}-{m:02d}": [str(cs.get_monthly_target(db, user, y, m)),
                                 str(cs.get_monthly_actual(db, user, y, m))]
                for y, m in _months(first, today)
            },
            "overtime": str(cs.get_overtime_account(db, user, today.year, today.month)),
        }
    json.dump(result, sys.stdout, sort_keys=True, indent=1)
    db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Prüflauf (ein Shell-Aufruf — Variablen und Funktionen überleben keinen Tool-Aufruf)**

Aus der Repo-Wurzel:

```bash
bash <<'BASHEOF'
set -e
WORK=$(mktemp -d); echo "Arbeitsverzeichnis: $WORK"
CT=pz073-prod; NET=pz073
PGPW=$(python3 -c 'import secrets;print(secrets.token_hex(16))')
docker exec $CT psql -q -U praxiszeit -d praxiszeit -c "ALTER ROLE praxiszeit PASSWORD '${PGPW}'"
S="postgres"; S="${S}ql://"; URL="${S}praxiszeit:${PGPW}@$CT:5432/praxiszeit"
COLS_TE="id, tenant_id, user_id, date, start_time, end_time, break_minutes, raw_start_time, raw_end_time, note, sunday_exception_reason, break_waiver_reason, created_at, updated_at"
COLS_WH="id, tenant_id, user_id, effective_from, weekly_hours, use_daily_schedule, hours_monday, hours_tuesday, hours_wednesday, hours_thursday, hours_friday, work_days_per_week, note, created_at"
WIN="scheduled_start_monday, scheduled_end_monday, scheduled_start_tuesday, scheduled_end_tuesday, scheduled_start_wednesday, scheduled_end_wednesday, scheduled_start_thursday, scheduled_end_thursday, scheduled_start_friday, scheduled_end_friday"
sql() { docker exec $CT psql -U praxiszeit -d praxiszeit -Atc "$1"; }
md5s() {
  sql "SELECT 'time_entries', count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM (SELECT $COLS_TE FROM time_entries) t"
  sql "SELECT 'working_hours_changes', count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM (SELECT $COLS_WH FROM working_hours_changes) t"
}
run() {  # $1 = Backend-Verzeichnis, Rest = Befehl
  local dir=$1; shift
  docker run --rm --network $NET -v "$dir":/app:ro -v "$PWD/tools/migration-073":/probe:ro -w /app \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
    -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid \
    -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development \
    -e CORS_ORIGINS=http://localhost -e TZ=Europe/Berlin -e DATABASE_URL="$URL" -e DATABASE_URL_MIGRATIONS="$URL" \
    praxiszeit-backend "$@"
}
migrate() { run "$PWD/backend" python -c "from alembic.config import main; main(['$1','$2'])"; }

echo "== Stand: $(sql 'SELECT version_num FROM alembic_version')"
sql "DROP TABLE IF EXISTS _probe_users_072; CREATE TABLE _probe_users_072 AS SELECT id, username, $WIN FROM users" > /dev/null
md5s | tee "$WORK/md5-072.txt"
echo "-- Auto-Close-Formen (P18): Ende 23:59 | nachgekappt (Ende <> 23:59, Rohende 23:59)"
sql "SELECT count(*) FILTER (WHERE end_time = '23:59'), count(*) FILTER (WHERE end_time <> '23:59' AND raw_end_time = '23:59') FROM time_entries t WHERE EXISTS (SELECT 1 FROM time_entry_audit_logs a WHERE a.time_entry_id = t.id AND a.source = 'auto_close')"
BASE=$(cat "$(git rev-parse --git-dir)/pr1-base")  # Task 0 Step 5 — Kopf des Integrationszweigs vor PR1
git cat-file -e "${BASE}^{commit}"; echo "== Code vor PR1: $(git log -1 --oneline "$BASE")"
mkdir -p "$WORK/old"; git archive "$BASE" backend | tar -x -C "$WORK/old"

echo "== Probe mit dem Code vor PR1"
run "$WORK/old/backend" python /probe/probe_073.py > "$WORK/072.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d), 'Personen,', sum(len(v['net_hours']) for v in d.values()), 'Einträge')" "$WORK/072.json"

echo "== Upgrade auf 073 mit dem PR1-Code"
migrate upgrade 073_work_blocks 2>&1 | tee "$WORK/upgrade.log" | sed -n '/HINWEIS (Migration 073)/,/ENDE HINWEIS/p'
run "$PWD/backend" python /probe/probe_073.py > "$WORK/073.json"
echo "-- auto_closed = true: $(sql 'SELECT count(*) FROM time_entries WHERE auto_closed')"
diff -q "$WORK/072.json" "$WORK/073.json" && echo "BYTE-IDENTISCH"

echo "== Round-Trip 073 -> 072 -> 073"
migrate downgrade 072_cr_sunday_reason 2>&1 | sed -n '/HINWEIS (Migration 073, Downgrade)/,/ENDE HINWEIS/p'
md5s > "$WORK/md5-roundtrip.txt"
diff "$WORK/md5-072.txt" "$WORK/md5-roundtrip.txt" && echo "TABELLEN IDENTISCH"
echo "-- Personen mit geändertem 072-Fenster nach dem Round-Trip:"
sql "SELECT b.username FROM _probe_users_072 b JOIN users u USING (id) WHERE ($(echo "$WIN" | sed 's/\([a-z_]*day\)/b.\1/g')) IS DISTINCT FROM ($(echo "$WIN" | sed 's/\([a-z_]*day\)/u.\1/g')) ORDER BY 1"
migrate upgrade 073_work_blocks > /dev/null 2>&1
run "$PWD/backend" python /probe/probe_073.py > "$WORK/073b.json"
diff -q "$WORK/072.json" "$WORK/073b.json" && echo "NACH ROUND-TRIP BYTE-IDENTISCH"
sql "DROP TABLE _probe_users_072" > /dev/null
echo "== Stand: $(sql 'SELECT version_num FROM alembic_version')"
BASHEOF
```

Expected, in dieser Reihenfolge:
1. `== Stand: 072_cr_sunday_reason`, zwei Zeilen `time_entries|<n>|<md5>` / `working_hours_changes|<n>|<md5>`, die Zeile „Auto-Close-Formen" mit zwei Zahlen `<a>|<b>`, `== Code vor PR1: 3d46c2f …` (bzw. der in Task 0 Step 5 festgehaltene Kopf; fehlt die Datei `pr1-base`, bricht `set -e` hier ab — dann nicht auf `merge-base` ausweichen, sondern den Commit unmittelbar vor dem ersten PR1-Commit per `git log --oneline` bestimmen und in die Datei schreiben), „<p> Personen, <e> Einträge" mit e > 0.
2. Der 073-Diagnoseblock nennt dieselben Fallen wie Task 0 (Q2: halboffen → „halboffen: …", `Beginn>=Ende` → „nicht übernommen: …", Sekunden → „Sekunden abgeschnitten: …"; Kontenzahl = Q3-Zeilen mit mindestens einem gültigen Tag) und **keine** Zeile „Abweichung: … (RLS?)" (das belegt hier nur, dass die Zählprobe stimmt: `praxiszeit` ist auch auf der Prod-Kopie Superuser, RLS greift also gar nicht, und unter RLS würde auch das Lesen gefiltert, sodass die Zählprobe nie anschlägt. Ob der Backfill unter FORCE RLS alle Zeilen trifft, prüft `test_073_migration_pg.py::test_073_backfill_as_owner_under_force_rls`, Task 14); `auto_closed = true: <a + b>` (Summe der beiden Auto-Close-Formen aus 1.); danach `BYTE-IDENTISCH`.
3. Der Downgrade-Block nennt keine Mehrblock-Personen und keine Einträge mit nicht angerechneter Zeit (PR1 erzeugt keine); `TABELLEN IDENTISCH`; unter „Personen mit geändertem 072-Fenster" stehen nur Personen, die die 073-Diagnose mit „Sekunden abgeschnitten" oder „nicht übernommen" nennt (halboffene Fenster kommen über die Platzhalter identisch zurück).
4. `NACH ROUND-TRIP BYTE-IDENTISCH`, `== Stand: 073_work_blocks`.

Fehlt `BYTE-IDENTISCH`: `diff "$WORK/072.json" "$WORK/073.json" | head -40` (Pfad aus der ersten Ausgabezeile) — jede Abweichung ist ein Fehler in PR1 (Spec E22), nicht in der Probe; Task stoppen und melden.

- [ ] **Step 3: Ergebnis festhalten, aufräumen, Commit**

Für den PR-Text notieren: Datum der Sicherung, „<p> Personen, <e> Einträge", die Zählzeile der 073-Diagnose, die beiden Auto-Close-Formen und `auto_closed = true`, „BYTE-IDENTISCH", „TABELLEN IDENTISCH", die Zahl der Personen mit geändertem Fenster. Dann das Arbeitsverzeichnis aus der ersten Ausgabezeile löschen (`rm -rf <Pfad>` — es enthält Prod-Daten) und:

```bash
git add tools/migration-073/probe_073.py
git commit -F - <<'EOF'
chore(073): Probe für die Byte-Identität auf einer Prod-Kopie (Erfolgskriterium 4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

Den Container `pz073-prod` entfernt der Betreiber (`docker rm -f pz073-prod`), sobald PR1 gemergt ist — bis dahin bleibt er für einen erneuten Lauf nach Review-Korrekturen stehen.

---

## Übergabe an PR2/PR3 — was PR1 bereitstellt

Die verbindlichen Signaturen stehen in den **Interfaces**-Blöcken der Tasks; diese Liste ist das Inhaltsverzeichnis dafür. PR2/PR3 ändern keine dieser Signaturen, sie ergänzen.

| Schnittstelle | Ort | Task |
|---|---|---|
| `WEEKDAY_LABELS`, `ParsedWeek`, `hhmm_to_minutes`, `minutes_to_hhmm`, `parse_week_blocks`, `week_blocks_to_json`, `is_legacy_week` | `app/services/work_blocks_service.py` | 1 |
| Test-Helfer `legacy_week`, `block_week`, `MON`, `K_BLOCKS` | `tests/work_blocks_fixtures.py` | 1 |
| `User.work_blocks`, `WorkingHoursChange.blocks`, `TimeEntry.uncredited_minutes` / `credit_override` / `auto_closed` / `clamp_grace_minutes`, `ChangeRequest.request_credit_override` / `original_uncredited_minutes` | Modelle | 2 |
| `Schedule.blocks`, `Schedule.block_pauses`; `get_schedule_for_date(db, user, target_date, wh_changes=None)`; `get_blocks_json_for_date(db, user, target_date, wh_changes=None)` | `calculation_service` | 2 |
| `ClampResult`, `DEFAULT_GRACE_MINUTES`, `CLAMP_WARNING_CODE`, `EMPLOYEE_CREDIT_HINT`, `get_grace_minutes`, `grace_for_entry`, `get_scheduled_blocks`, `has_blocks`, `clamp_applies`, `credit_gaps`, `clamp`, `gap_segments`, `clamp_warning_text`, `clamp_warning`, `unclamp_input`, `not_credited_minutes`, `presence_minutes` | `app/services/work_window_service.py` | 3 |
| Falltabelle `KCase`, `K_CASES`, `k_user`, `EASTER_MONDAY`, `SUNDAY`, `DEC24_THU` | `tests/work_blocks_cases.py` | 3 |
| `TimeEntry.net_hours` (Hybrid mit `uncredited_minutes`); `_net_hours(st, et, brk, uncredited)`, `_calculate_daily_net_hours(…, *, uncredited_minutes, …)`, `_calculate_weekly_net_hours(…, *, uncredited_minutes, …)` | Modell, `routers/time_entries.py` | 4 |
| `BreakBlock`, `break_block_for_new`, `break_block_for_entry`, `daily_break_figures`, `validate_daily_break(db, user, …, *, uncredited_segments, tenant_id, exclude_entry_id=None)` (+ unveränderte #499-Helfer) | `app/services/break_validation_service.py` | 5 |
| Schreibregel `clamp_grace_minutes = r.grace_minutes` (wenn nicht None); Puffer-Herkunft Neuanlage vs. Einzel-Neukappung | alle Schreibpfade | 6 |
| Ankersperre `lock_user_row` als erste Sperre jedes Schreibpfads; Spy-Fixture `calls` / `assert_lock_first` | Schreibpfade, `tests/test_write_path_locks.py` | 7 |
| `_close_stale_entry(db, entry, *, changed_by_id=None)` (Auto-Close über `clamp`, setzt `auto_closed`); Regel „`auto_closed = False` bei neuem Ende" | `routers/time_entries.py` | 8 |
| E39 (Datum im Gate), E40 (Antragsprüfung auf `clamp`), E41 (keine Doppelzählung), P3-409 nur für Nicht-Admins, P28-Snapshot `original_uncredited_minutes` | `time_entries.py`, `change_requests.py`, `admin_change_requests.py` | 9 |
| `CREDIT_OVERRIDE_IMPORT_NOTE`, `ImportedEntry.uncredited_minutes`, `_calc_break_minutes(eff_start, eff_end, segments)`, `_check_arbzg(…, *, uncredited_segments, rest_start=None)`, `_find_existing_entry`, `_start_taken`, `parse_xls(file_bytes, user_id, db, *, tenant_id=None)` | `app/services/xls_import_service.py` | 10 |
| `LEGACY_WINDOW_FIELD_PREFIX`, `strip_legacy_window_fields`, `validate_employment_order`; `legacy_window_fields_sent` (exclude), `UserUpdate.work_blocks` (gesperrt), `work_blocks`/`work_blocks_today` auf `UserResponse`/`UserListResponse`; `LEGACY_WINDOW_FIELDS_DETAIL`; `attach_work_blocks_today(db, users, on_date)` | Schemas, `admin_users.py`, `calculation_service` | 11 |
| `_comparable_snapshot(…, blocks, block_pauses)`, `_carried_blocks(predecessor)`, User-Spiegel in `_sync_user_from_change`, `WorkingHoursChangeResponse.blocks` | `admin_users.py`, Schema | 12 |
| Migration `073_work_blocks` (Helfer `build_week`, `window_from_week`, `upgrade_report`, `downgrade_report`, `tenant_label`); Guards `test_no_scheduled_columns.py`, `test_no_live_work_blocks_read.py` (Erlaubnisliste, PR2 ergänzt den Art.-15/20-Export) | `alembic/versions`, `tests/` | 13 |
| PG-only `test_073_migration_pg.py`, `test_net_hours_parity_pg.py`, eingehängt in Actions und `local-ci.sh` | `tests/`, CI | 14 |
| `TimeBlock`, `DayBlocks`, `WeekBlocks`; `WEEKDAY_LABELS`, `isLegacyWeek`, `formatWeekBlocks`; `User.work_blocks(_today)`; `UserForm`-Prop `displayBlocks` | `frontend/src/types/workBlocks.ts`, `frontend/src/utils/workBlocks.ts`, `types/user.ts`, `UserForm.tsx` | 15 |
| E2E „kein Soll-Fenster, Altfelder 400" | `e2e/tests/admin/prod-release-features.spec.ts` | 16 |
| `tools/migration-073/probe_073.py` (Byte-Identität auf der Prod-Kopie) | `tools/` | 17 |

**Release-Gate (Spec 17.8, Risiko 6):** Migration 073 löscht die Spalten `users.scheduled_*`; die Byte-Identitäts-Probe (Task 17), Unit-Tests und `validate-release.sh` decken einen echten Betrieb nicht ab. Vor dem Release 1.20.0 (erst nach PR1–PR4) muss `/buildrelease` nach dem Update auf 073 auf .131 **nativ** (`install.sh`-Update) **und** mit dem **Docker-Bundle** einen echten Login, clock-in und clock-out sowie `GET /api/admin/users` mit einer Altfenster-Person (07:37/23:59) prüfen. PR4 Task 11 verankert das als Regel in `CLAUDE.md` (Pflichtbegriff in `check-doc-sync.sh`, Gruppe `claude`), PR4 Task 13 nennt es im PR-Text.
