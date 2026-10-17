# Arbeitszeit-Blöcke PR2 „Sichtbarkeit" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nicht angerechnete Zeit (Lücke **und** von der Hülle gekappte Anwesenheit) an jeder Anzeige-, Export- und Auskunftsfläche sichtbar machen, „Anerkennen" und „Anrechnung beantragen" bereitstellen und die weichen ArbZG-Warnungen auf der tatsächlichen Anwesenheit einführen — ohne Kappung, Soll oder Saldo zu verändern.

**Architecture:** Zwei neue Backend-Dienste: `presence_service` (Anwesenheit laut Stempel, `PRESENCE_*`, `BREAK_IN_GAP`) und `credit_override_service` („Anerkennen" — eine Quelle für die Admin-Aktion und die Antragsgenehmigung). „Nicht angerechnet" kommt ausschließlich aus `work_window_service.not_credited_minutes` (PR1) — im Backend als berechnetes Antwortfeld, im Frontend über den Zwilling `utils/workBlocks.ts::notCreditedMinutes`; `RawStampNote` ist die eine Textquelle der Eintragszeile. Exporte hängen eine Spalte an (XLSX/ODS Spalte 13, PDF Spalte 12), Auskunftsexporte führen die neuen Felder als `str`/`int`/`bool`/`None`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, openpyxl, odfpy, reportlab (SQLite in der Unit-Suite, PostgreSQL 18 in den PG-Suiten), React 18 + TypeScript + Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md` (verbindlich; Abschnitt 20 „PR2", Abschnitte 8, 13, 14, 15.1, 15.3, 2.10 inkl. „Entschieden 2026-10-08", 19.1). Schnittstellen aus PR1: `docs/superpowers/plans/2026-10-08-bloecke-pr1-fundament.md` (Abschnitt „Übergabe an PR2/PR3"). Wer einen Task umsetzt, liest die im Task genannten Spec-Abschnitte mit.

## Global Constraints

- PR2 setzt den **gemergten PR1** voraus. PR2 wird **nie allein released**; 1.20.0 erst nach PR1–PR4. PR3 nie ohne PR2 auf `master` (Spec 20).
- Verhalten nach dem Merge (Spec 20): wirkungslos, solange `uncredited_minutes` = 0; Hüllenminuten (Altfenster aus 073) werden bereits sichtbar. Kappung, Tagessoll, `net_hours` und Saldo ändern sich durch PR2 **nicht**.
- „Angerechnet" = `net_hours`; „nicht angerechnet" = `not_credited_minutes` = `uncredited_minutes` + Hüllenminuten (`eff_start − raw_start`, `raw_end − eff_end`; Endseite bei `auto_closed` ausgenommen, P18/P19). Keine Anzeige- oder Exportfläche nutzt `uncredited_minutes` allein für „nicht angerechnet".
- `uncredited_minutes`, `credit_override`, `auto_closed`, `clamp_grace_minutes`, `not_credited_minutes` sind **nie** Eingabefelder (E11, E79). Neue Eingaben in PR2 genau zwei: `ChangeRequestCreate.request_credit_override: bool = False` und `ChangeRequestReview.grant_credit_override: Optional[bool] = None`.
- Neue Warncodes, alle weich (nie 400/422), alle bei `exempt_from_arbzg` unterdrückt: `PRESENCE_DAILY_HOURS`, `PRESENCE_BREAK`, `PRESENCE_WEEKLY_HOURS`, `BREAK_IN_GAP` (Texte wörtlich aus Spec 8.3/8.4, siehe Task 3).
- Protokoll: `source="credit_override"` (15 Zeichen, < varchar(40)), `action="update"`; Oberflächen-Labels `credit_override: 'Anrechnung anerkannt'`, `wh_reclamp: 'Neukappung (Arbeitszeit-Änderung)'`. Protokollzeilen nur per `db.add` (Hook setzt `row_hash`, #121), kein Bulk-UPDATE.
- Exporte: Spaltenkopf **„Nicht angerechnet (Min)"**, angehängt — XLSX-Monatsblatt, XLSX-Jahres-Mitarbeiterblatt, ODS Monat und Jahr: **Spalte 13** (Köpfe 1–12 unverändert); PDF-Monat: **12. und letzte** Spalte, Kopf zweizeilig „Nicht angerechnet / (Min)", Spalte 6 bleibt „Unterbr. (Min)", Breiten neu auf 267 mm.
- Rohe JSON-Exporte (`lifecycle_service`, `auth /me/export`, `superadmin`): nur `str`/`int`/`bool`/`None` — jedes `time`/`Decimal` macht den Export für jede Person zu HTTP 500 (#383/#408).
- F-026: jede neue Abfrage auf mandantenbezogene Tabellen trägt `tenant_id == …` zusätzlich zu RLS (E74).
- Ankersperre (P5): „Anerkennen" sperrt **zuerst** `lock_user_row(db, tenant_id, owner_id)` und lädt **danach** den Eintrag mit `with_for_update`.
- Wörtliche Texte (Spec 11.4, 13.3, 14): „Ein offener Eintrag kann erst nach dem Ausstempeln anerkannt werden." · „Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen." · „Ein anderer Eintrag an diesem Tag beginnt bereits um {HH:MM}." · „Für diesen Eintrag kann keine Anrechnung beantragt werden." · „Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet." · „Pause zwischen den Arbeitsblöcken".
- Backend-Tests **nie** im geteilten Container. Vor jedem Lauf `rm -f backend/test.db backend/test.db-wal backend/test.db-shm`, nie zwei Läufe gleichzeitig (`pgrep -af pytest` prüfen). Befehl (aus dem Repo-Wurzelverzeichnis):
  `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/<datei> -q -p no:cacheprovider`
  Die volle SQLite-Suite: dieselbe Zeile mit `tests/ --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`.
- Frontend (aus `frontend/`): `npx vitest run <datei> --pool=threads`, `npx tsc --noEmit`, `npx eslint src`.
- Commits immer per `git commit -F - <<'EOF' … EOF`, letzte Zeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Issue-Lanes (#499 §4/Schreibpfade, #497/#498 Exporte, #493/#494/#500/#501 Mitarbeiter-Dashboard + `get_clock_status`, #496 `admin_helpers`, #491 F4 `ChangeRequestForm`/`TimeTracking`): Tasks mit **⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** vor Beginn gegen den Ausführungsstand neu lesen. Zeilennummern in diesem Plan beziehen sich auf `3d46c2f` **vor** PR1 und sind nur Orientierung; maßgeblich sind die zitierten Funktionsnamen und Codeanker.

## Review Focus

1. **Personen ohne Blöcke bzw. mit Altfenster (praktisch alle Bestandskunden direkt nach dem Merge):** reguläre Einträge (08:00–17:00 mit 45 Min Pause, zwei Einträge mit 30 Min Abstand) erzeugen **keine** `PRESENCE_*`/`BREAK_IN_GAP`-Warnung — Anwesenheit und Anrechnung weichen nur bei Kappung voneinander ab. Test in Task 3.
2. **Offener Eintrag mit Beginn vor der Hülle (K20 direkt nach dem Einstempeln):** die Zeile „gestempelt 07:00 · angerechnet ab 07:45" bleibt sichtbar (Bestandsverhalten), es erscheint keine „angerechnet x h"-Zeile. Test in Task 14.
3. **„Anrechnung beantragen" an einem automatisch geschlossenen Eintrag mit dem gekappten Ende (18:15) oder 23:59 als „tatsächlichem Ende":** die Genehmigung machte über `unclamp_input` wieder 23:59 daraus (16 h angerechnet) — der Antrag wird mit 400 abgelehnt, ein echtes Ende (17:30) geht durch. Test in Task 6.
4. **XLS-Re-Import eines bereits importierten Tages:** der überschriebene Bestandseintrag zählt in der Anwesenheit der Vorschau nicht doppelt (sonst falsches `PRESENCE_BREAK`). Test in Task 12.
5. **Dashboard-Status genau an den Blockgrenzen:** 12:00 (Ende Block 1) ist schon „Pause zwischen den Arbeitsblöcken", 15:00 (Beginn Block 2) wieder Arbeitszeit, vor dem ersten Block bleibt das bisherige Verhalten. Test in Tasks 13 und 17.

## Abgleich mit PR1 und Vorbedingung

Vor Task 1 prüfen, dass PR1 auf dem Ausführungsbranch liegt — sonst **STOP**:

```bash
grep -n "def not_credited_minutes\|def presence_minutes\|^EMPLOYEE_CREDIT_HINT\|def grace_for_entry\|def get_scheduled_blocks" backend/app/services/work_window_service.py
grep -n "uncredited_minutes\|credit_override\|auto_closed\|clamp_grace_minutes" backend/app/models/time_entry.py
grep -n "request_credit_override\|original_uncredited_minutes" backend/app/models/change_request.py
grep -n "def get_blocks_json_for_date\|def minutes_to_hhmm" backend/app/services/calculation_service.py backend/app/services/work_blocks_service.py
grep -n "export function formatWeekBlocks\|export function isLegacyWeek" frontend/src/utils/workBlocks.ts
```

Expected: jede Zeile liefert mindestens einen Treffer. Danach einmal die volle SQLite-Suite fahren und die Ausgangszahl notieren — „keine neuen Fehlschläge" in den Tasks bezieht sich auf diese Zahl.

Verwendete PR1-Schnittstellen (Namen und Signaturen exakt aus dem PR1-Plan):

| Schnittstelle | Ort (PR1-Task) |
|---|---|
| `TimeEntry.uncredited_minutes: int`, `.credit_override: bool`, `.auto_closed: bool`, `.clamp_grace_minutes: Optional[int]`; `ChangeRequest.request_credit_override: bool`, `.original_uncredited_minutes: Optional[int]`; `User.work_blocks`, `WorkingHoursChange.blocks` | Modelle (2) |
| `calculation_service.get_schedule_for_date(db, user, target_date, wh_changes=None) -> Schedule` (mit `blocks`, `block_pauses`), `get_blocks_json_for_date(db, user, target_date, wh_changes=None) -> Optional[list]`, `get_daily_target_for_date(user, target_date, schedule)` | `calculation_service` (2) |
| `work_blocks_service.minutes_to_hhmm(minutes) -> str`, `WEEKDAY_LABELS` | (1) |
| `ClampResult`, `get_grace_minutes(db, tenant_id)`, `grace_for_entry(db, entry)`, `get_scheduled_blocks(db, user, d, *, wh_changes=None, soll_free_dates=None) -> list[tuple[int,int]]`, `gap_segments(…)`, `clamp(…, *, credit_override)`, `clamp_warning(db, user, d, result, *, for_employee)`, `unclamp_input(…)`, `not_credited_minutes(entry) -> int`, `presence_minutes(entry) -> int`, Hilfsfunktion `_hm(minutes) -> str` | `work_window_service` (3) |
| `TimeEntry.net_hours` mit `uncredited_minutes`; `_calculate_daily_net_hours(…, *, uncredited_minutes, …)`, `_calculate_weekly_net_hours(…)`; `MAX_DAILY_HOURS_HARD`, `MAX_DAILY_HOURS_WARN`, `MAX_WEEKLY_HOURS_WARN` | `routers/time_entries.py` (4) |
| `validate_daily_break(db, user, entry_date, start_time, end_time, break_minutes, *, uncredited_segments, tenant_id, exclude_entry_id=None) -> Optional[str]` | `break_validation_service` (5) |
| `lock_user_row` vor jeder Zeilensperre; `_close_stale_entry(db, entry, *, changed_by_id=None)` setzt `auto_closed` | (7, 8) |
| P3: MA-`PUT` auf anerkannten Eintrag → 409; P28: `original_uncredited_minutes` im Antrags-Snapshot; E40: Antragsprüfung mit `clamp` | (9) |
| `ImportedEntry.uncredited_minutes`, `parse_xls(file_bytes, user_id, db, *, tenant_id=None)`, `_check_arbzg(…)` mit Texten „§4 ArbZG: …"/„§3 ArbZG: …" | `xls_import_service` (10) |
| `tests/test_no_live_work_blocks_read.py` mit Erlaubnisliste `ALLOWED` | (13) |
| Test-Helfer `tests.work_blocks_fixtures` (`legacy_week`, `block_week`, `MON`, `K_BLOCKS`), `tests.work_blocks_cases` (`KCase`, `K_CASES`, `k_user`, `EASTER_MONDAY`, `SUNDAY`, `DEC24_THU`), `tests.test_xls_blocks` (`HEADER`, `_xls`) | (1, 3, 10) |
| Frontend `types/workBlocks.ts` (`TimeBlock`, `DayBlocks`, `WeekBlocks`), `utils/workBlocks.ts` (`WEEKDAY_LABELS`, `isLegacyWeek`, `formatWeekBlocks`) | (15) |

## Dateistruktur

| Datei | Verantwortung | Task |
|---|---|---|
| `backend/app/services/work_window_service.py` | + `credit_summary_text` | 1 |
| `backend/app/schemas/time_entry.py` | lesende Antwortfelder, `ClockBlock`, `ClockStatusResponse.blocks_today/grace_minutes` | 1, 2 |
| `backend/app/routers/time_entries.py` | Clock-Status-Blöcke, Anwesenheits-Warnungen in `clock_out`/`create`/`update` | 2, 4 |
| `backend/app/services/presence_service.py` (neu) | Anwesenheit laut Stempel, `PRESENCE_*`, `BREAK_IN_GAP` | 3 |
| `backend/tests/work_blocks_cases.py` | + Spalte „Meldung" (`K_CODES`) | 4 |
| `backend/app/routers/admin_time_entries.py` | Anwesenheits-Warnungen Admin-Pfade; Endpunkt „Anerkennen" | 4, 5 |
| `backend/app/services/credit_override_service.py` (neu) | „Anerkennen" (Prüfungen, Felder, Protokoll, weiche Warnungen) | 5 |
| `backend/app/schemas/change_request.py`, `routers/change_requests.py`, `routers/admin_change_requests.py`, `routers/admin_helpers.py` | „Anrechnung beantragen", „genehmigen und anerkennen", Antwortfelder | 6 |
| `backend/app/services/journal_service.py`, `schemas/journal.py` | Journal-Felder + Monatssumme | 7 |
| `backend/app/services/export_service.py`, `ods_export_service.py` | Spalte „Nicht angerechnet (Min)" | 8 |
| `backend/app/routers/reports.py`, `frontend/src/pages/admin/Reports.tsx` | 24-Wochen-Auswertung mit Anwesenheit laut Stempel | 9 |
| `backend/app/services/work_schedule_service.py`, `schemas/work_schedule.py` (neu), `routers/auth.py`, `frontend/src/components/MyWorkScheduleCard.tsx` (neu), `pages/Profile.tsx` | Profil „Meine Arbeitszeit" | 10 |
| `backend/app/services/lifecycle_service.py`, `routers/auth.py`, `routers/superadmin.py`, `tests/test_no_live_work_blocks_read.py` | Art.-15/20- und §16-Notfallexport | 11 |
| `backend/app/services/xls_import_service.py`, `frontend/src/pages/admin/ImportXls.tsx` | XLS-Vorschau: Netto vom Server, Anwesenheits-Hinweise | 12 |
| `frontend/src/utils/workBlocks.ts`, `utils/workBlocksCases.ts` (neu), `utils/arbzgWarnings.ts`, `utils/breakValidation.ts` | Frontend-Zwillinge, neue Codes, §4 mit Lückensegmenten | 13 |
| `frontend/src/components/RawStampNote.tsx`, `pages/admin/EmployeeTimeEntryTable.tsx` (neu), `pages/TimeTracking.tsx`, `components/MonthlyJournal.tsx`, `pages/admin/AdminDashboard.tsx` | Eintragszeile „nicht angerechnet" | 14 |
| `frontend/src/components/CreditOverrideButton.tsx` (neu), `EmployeeTimeEntryTable.tsx`, `MonthlyJournal.tsx`, `AdminDashboard.tsx` | „Anerkennen", Journal-Summe | 15 |
| `frontend/src/components/ChangeRequestForm.tsx`, `pages/TimeTracking.tsx`, `components/MonthlyJournal.tsx`, `pages/admin/ChangeRequests.tsx` | „Anrechnung beantragen", Antragsprüfung | 16 |
| `frontend/src/components/StampWidget.tsx`, `pages/TimeTracking.tsx`, `pages/Dashboard.tsx` | §4-Vorprüfung mit Lücke, Vorbelegung, Status in der Lücke | 17 |
| `frontend/src/constants/auditSources.ts` (neu), `pages/admin/AuditLog.tsx`, `pages/Privacy.tsx`, `pages/admin/Settings.tsx` | Audit-Labels, Datenschutz-Text, Puffer-Text | 18 |

**Außerhalb von PR2 (nicht anfassen):** Schreibschemas mit Blöcken (`DayBlocksIn`, `validate_week_blocks`), `derive_targets`, Dialog/Editor, POST-Vorschau, Neukappung (`reclamp_time_entries`), Schutzpaket, Sammelzeile `wh_reclamp` und `reclamp_audit.py`, Dashboard-Hinweise `schedule_change_notices`, F1-Klemmung, Plan-Hinweise (alles PR3); E2E `work-blocks.spec.ts` mit allen Szenarien 1–8 aus 17.8, **auch** 5 (Anerkennen im Admin-Dashboard) und 7 („Anrechnung beantragen" + „Genehmigen und anerkennen") — PR3 Task 22, weil Blöcke mit Lücke erst dort anlegbar sind. Die Oberflächentexte, auf die diese beiden Tests zielen („Anerkennen", „Zeit anerkennen", Toast „Zeit anerkannt", Kennzeichen „anerkannt", „Anrechnung beantragen", „Änderungsantrag: Anrechnung beantragen", „Antrag auf Anrechnung eingereicht", „Anrechnung beantragt", „Genehmigen und anerkennen"), liefert PR2 (Task 14–16); sie sind ab dort eingefroren; Doku, `CLAUDE.md`, Release-Notes (PR4). **Hinweis für den PR3-Plan:** Spec 15.2 (Berichtstext der Vertragsänderungen mit Blöcken, `blocks_changed`, `format_weekly_hours_history`/`formatWeeklyHoursChanges`) ist in Abschnitt 20 keinem PR zugeordnet; er hängt an editierbaren Blöcken und gehört damit zu PR3.

---

### Task 1: Antwortfelder der Zeiteinträge und `credit_summary_text`

**Files:**
- Modify: `backend/app/services/work_window_service.py` (am Dateiende, nach `presence_minutes`)
- Modify: `backend/app/schemas/time_entry.py` (Import `computed_field`; `TimeEntryResponse` nach `raw_end_time`)
- Test (neu): `backend/tests/test_time_entry_response_fields.py`

**Interfaces:**
- Consumes: `work_window_service.not_credited_minutes(entry) -> int`, `work_window_service._hm(minutes) -> str` (PR1 Task 3); `TimeEntry.net_hours` mit `uncredited_minutes` (PR1 Task 4); Fixtures `tests.test_endpoints`; `tests.work_blocks_fixtures.K_BLOCKS`, `MON`
- Produces:
  - `work_window_service.credit_summary_text(entry) -> str` — „angerechnet H:MM h[, nicht angerechnet H:MM h[, davon H:MM h zwischen den Blöcken]][, Pause H:MM h]"
  - `TimeEntryResponse.uncredited_minutes: int = 0`, `.credit_override: bool = False`, `.auto_closed: bool = False`, `.clamp_grace_minutes: Optional[int] = None` und das berechnete Feld `.not_credited_minutes: int` (gilt damit auch für `ClockStatusResponse.current_entry` und jede Route, die `TimeEntryResponse.model_validate(entry)` nutzt)

**Auslegung (Widerspruch in Spec 10.1):** Die Kurzregel sagt, „davon … zwischen den Blöcken" entfalle, wenn es gleich der Gesamtzahl ist; beide wörtlichen Beispiele (10.1 `old_note`, 13.3 Schritt 5) zeigen für K1 (Lücke = Gesamt) den Zusatz aber. Dieser Plan folgt den Beispielen, weil der Zusatz die Ursache nennt; er entfällt nur bei `uncredited_minutes` = 0. Ändert der Betreiber das, ist es eine Zeile plus eine Testerwartung.

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_time_entry_response_fields.py`:

```python
"""Spec 2026-10-08 (PR2): lesende Antwortfelder der Zeiteinträge (7.1, E79,
P18, P19) und der Notiztext der Anrechnung (10.1, 13.3)."""
from datetime import time

import pytest

from app.models import TimeEntry
from app.schemas.change_request import ChangeRequestCreate
from app.schemas.time_entry import ClockOutRequest, TimeEntryCreate, TimeEntryUpdate
from app.services import work_window_service as wws
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON

SERVER_ONLY = {
    "uncredited_minutes", "credit_override", "auto_closed",
    "clamp_grace_minutes", "not_credited_minutes",
}


def _te(start, end, brk=0, unc=0, **kw):
    return TimeEntry(start_time=start, end_time=end, break_minutes=brk,
                     uncredited_minutes=unc, **kw)


@pytest.mark.parametrize("entry, text", [
    # K1: nur Lücke — die Beispiele aus 10.1/13.3 nennen „davon …" auch hier.
    (_te(time(8), time(18), unc=150),
     "angerechnet 7:30 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken"),
    # K7: Hülle und Lücke
    (_te(time(7, 45), time(18, 15), unc=150, raw_start_time=time(7), raw_end_time=time(19)),
     "angerechnet 8:00 h, nicht angerechnet 4:00 h, davon 2:30 h zwischen den Blöcken"),
    # K9: Pause folgt am Ende
    (_te(time(8), time(18), brk=30, unc=150),
     "angerechnet 7:00 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken, Pause 0:30 h"),
    # nur Hülle: kein „davon"
    (_te(time(7, 45), time(16), brk=30, raw_start_time=time(7, 30)),
     "angerechnet 7:45 h, nicht angerechnet 0:15 h, Pause 0:30 h"),
    # nichts gekappt
    (_te(time(8), time(18)), "angerechnet 10:00 h"),
    # K15 Auto-Close: die synthetische Endseite (23:59) zählt nicht (P18)
    (_te(time(8), time(18, 15), unc=150, raw_end_time=time(23, 59), auto_closed=True),
     "angerechnet 7:45 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken"),
], ids=["K1", "K7", "K9", "hull", "plain", "K15"])
def test_credit_summary_text(entry, text):
    assert wws.credit_summary_text(entry) == text


def test_response_carries_the_read_only_fields(_db_session, employee_user, employee_client):
    employee_user.work_blocks = K_BLOCKS
    e = _te(time(7, 45), time(18, 15), unc=150, raw_start_time=time(7), raw_end_time=time(19),
            tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON, clamp_grace_minutes=15)
    _db_session.add(e)
    _db_session.commit()
    r = employee_client.get(f"/api/time-entries/{e.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uncredited_minutes"] == 150
    assert body["not_credited_minutes"] == 240   # P19: Lücke + Hülle (K7)
    assert body["credit_override"] is False
    assert body["auto_closed"] is False
    assert body["clamp_grace_minutes"] == 15
    assert body["net_hours"] == 8.0


def test_list_and_auto_closed_entry(_db_session, employee_user, employee_client):
    e = _te(time(8), time(18, 15), unc=150, raw_end_time=time(23, 59), auto_closed=True,
            tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON)
    _db_session.add(e)
    _db_session.commit()
    rows = employee_client.get("/api/time-entries/?month=2026-06").json()
    row = next(r for r in rows if r["id"] == str(e.id))
    assert (row["auto_closed"], row["not_credited_minutes"]) == (True, 150)


@pytest.mark.parametrize(
    "schema", [TimeEntryCreate, TimeEntryUpdate, ClockOutRequest, ChangeRequestCreate],
)
def test_server_side_fields_are_never_inputs(schema):
    assert SERVER_ONLY.isdisjoint(schema.model_fields), schema.__name__
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_time_entry_response_fields.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'app.services.work_window_service' has no attribute 'credit_summary_text'` und `KeyError: 'uncredited_minutes'` in den Antworttests; `test_server_side_fields_are_never_inputs` ist bereits grün (Regressionsschutz).

- [ ] **Step 3: `credit_summary_text` anlegen**

Am Ende von `backend/app/services/work_window_service.py`:

```python
def credit_summary_text(entry) -> str:
    """Spec 10.1 / 13.3: Klartext für Protokollnotizen — EINE Quelle
    („Anerkennen" in PR2, Neukappung in PR3).

    „angerechnet" = ``net_hours`` (nach Pause und Lücke), „nicht angerechnet" =
    ``not_credited_minutes`` (Lücke + Hülle, P19), „davon … zwischen den
    Blöcken" = ``uncredited_minutes`` (entfällt bei 0), bei Pause > 0 folgt
    „, Pause H:MM h". Bewusst ohne Typlabels („Krank " …) — sonst schlüge
    ``admin_time_entries._audit_note_is_health_sensitive`` an (Spec 10.1)."""
    credited = int(round(float(entry.net_hours or 0) * 60))
    parts = [f"angerechnet {_hm(credited)} h"]
    total = not_credited_minutes(entry)
    gap = int(getattr(entry, "uncredited_minutes", 0) or 0)
    if total > 0:
        text = f"nicht angerechnet {_hm(total)} h"
        if gap > 0:
            text += f", davon {_hm(gap)} h zwischen den Blöcken"
        parts.append(text)
    brk = int(entry.break_minutes or 0)
    if brk > 0:
        parts.append(f"Pause {_hm(brk)} h")
    return ", ".join(parts)
```

- [ ] **Step 4: Antwortfelder in `TimeEntryResponse`**

In `backend/app/schemas/time_entry.py` die erste Importzeile ersetzen durch:

```python
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, field_serializer
```

In `TimeEntryResponse` direkt nach `raw_end_time: Optional[time] = None  # #201: unklammerter Stempelzeitpunkt`:

```python
    # Spec 2026-10-08 (7.1, E79, P18): nur lesend — kein Eingabeschema kennt
    # diese Felder (E11), der Server leitet sie ab.
    uncredited_minutes: int = 0
    credit_override: bool = False
    auto_closed: bool = False
    clamp_grace_minutes: Optional[int] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def not_credited_minutes(self) -> int:
        """P19: Lücke + von der Hülle gekappte Anwesenheit — DIE eine Quelle
        ``work_window_service.not_credited_minutes`` (lokal importiert: ein
        Schema zieht beim Modulimport keine Services)."""
        from app.services.work_window_service import not_credited_minutes
        return not_credited_minutes(self)
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_time_entry_response_fields.py tests/test_endpoints.py tests/test_494_clock_status_today.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/work_window_service.py backend/app/schemas/time_entry.py backend/tests/test_time_entry_response_fields.py
git commit -F - <<'EOF'
feat(bloecke): Antwortfelder nicht angerechnete Zeit + credit_summary_text (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Clock-Status liefert die Blöcke von heute und den Puffer des Ausstempelns

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#494 hat `get_clock_status` umgebaut — der Stale-Zweig setzt `open_entry = None` statt früh zurückzukehren; PR1 Task 7 hat dort die Ankersperre ergänzt. Vor Beginn `get_clock_status` lesen: es gibt genau zwei `return ClockStatusResponse(...)`.)

**Files:**
- Modify: `backend/app/schemas/time_entry.py` (`ClockBlock` neu vor `ClockStatusResponse`; zwei Felder in `ClockStatusResponse`)
- Modify: `backend/app/routers/time_entries.py` (Helfer `_clock_blocks_and_grace` vor `get_clock_status`; beide Rückgaben in `get_clock_status`)
- Test (neu): `backend/tests/test_clock_status_blocks.py`

**Interfaces:**
- Consumes: `work_window_service.get_scheduled_blocks`, `grace_for_entry`, `get_grace_minutes` (PR1 Task 3); `work_blocks_service.minutes_to_hhmm` (PR1 Task 1)
- Produces:
  - `schemas.time_entry.ClockBlock(BaseModel)`: `start: str`, `end: str` (`"HH:MM"`)
  - `ClockStatusResponse.blocks_today: List[ClockBlock] = []`, `ClockStatusResponse.grace_minutes: int = 15` — in **jedem** Zweig (nicht eingestempelt, Stale-Auto-Close, eingestempelt); `grace_minutes` = `clamp_grace_minutes` des offenen Eintrags, sonst aktueller Mandanten-Puffer (E80); `blocks_today` = `[]` an Tagen ohne Blöcke, an Feiertagen/freien Sondertagen und bei `track_hours=false`
  - `time_entries._clock_blocks_and_grace(db, user, today, open_entry) -> tuple[list[dict], int]`

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_clock_status_blocks.py`:

```python
"""Spec 2026-10-08, 8.4 / 11.1 / 14 (PR2): /clock-status liefert die Blöcke von
heute und den Puffer, mit dem das Ausstempeln kappen wird — in jedem Zweig."""
import datetime as dt
from datetime import date, time

import app.routers.time_entries as te
from app.models import TimeEntry
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON, block_week

TUE = date(2026, 6, 2)
SAT = date(2026, 6, 6)
WEEK = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "13:00")])
MON_BLOCKS = [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}]


def _at(monkeypatch, d, hh=10):
    monkeypatch.setattr(te, "_today_local", lambda: d)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(d.year, d.month, d.day, hh, 0))


def _grace(db, minutes):
    db.add(SystemSetting(key="work_window_grace_minutes", value=str(minutes), tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def _status(client):
    r = client.get("/api/time-entries/clock-status")
    assert r.status_code == 200, r.text
    return r.json()


def test_not_clocked_in_returns_blocks_and_tenant_grace(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = WEEK
    _db_session.commit()
    _grace(_db_session, 10)
    _at(monkeypatch, MON)
    body = _status(employee_client)
    assert body["is_clocked_in"] is False
    assert body["blocks_today"] == MON_BLOCKS
    assert body["grace_minutes"] == 10


def test_clocked_in_uses_the_stored_grace_of_the_open_entry(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = WEEK
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=None, break_minutes=0, clamp_grace_minutes=15))
    _db_session.commit()
    _grace(_db_session, 0)
    _at(monkeypatch, MON, 13)
    body = _status(employee_client)
    assert body["is_clocked_in"] is True
    assert body["grace_minutes"] == 15        # E80: der Puffer, mit dem clock_out kappen wird
    assert body["blocks_today"] == MON_BLOCKS
    assert body["current_entry"]["uncredited_minutes"] == 0
    assert body["current_entry"]["clamp_grace_minutes"] == 15


def test_stale_branch_closes_and_still_reports_today(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = WEEK
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=None, break_minutes=0, clamp_grace_minutes=15))
    _db_session.commit()
    _at(monkeypatch, TUE)
    body = _status(employee_client)
    assert body["is_clocked_in"] is False
    assert body["blocks_today"] == [{"start": "08:00", "end": "13:00"}]
    assert body["grace_minutes"] == 15        # kein offener Eintrag mehr → Mandanten-Puffer (Default)


def test_no_blocks_on_saturday_and_without_hour_tracking(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = WEEK
    _db_session.commit()
    _at(monkeypatch, SAT)
    assert _status(employee_client)["blocks_today"] == []
    employee_user.track_hours = False
    _db_session.commit()
    _at(monkeypatch, MON)
    assert _status(employee_client)["blocks_today"] == []
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_clock_status_blocks.py -q -p no:cacheprovider`
Expected: FAIL — `KeyError: 'blocks_today'`

- [ ] **Step 3: Schema erweitern**

In `backend/app/schemas/time_entry.py` direkt vor `class ClockStatusResponse(BaseModel):`:

```python
class ClockBlock(BaseModel):
    """Spec 2026-10-08, 8.4/14: ein Arbeitszeit-Block des heutigen Tages."""
    start: str  # "HH:MM"
    end: str    # "HH:MM"
```

Am Ende von `ClockStatusResponse` (nach `today_target_hours: float = 0.0`):

```python
    # Spec 2026-10-08 (8.4, 11.1, 14): die Blöcke von heute — für die §4-Vorprüfung
    # im StampWidget und den Dashboard-Status in der Lücke (E69) — und der
    # Puffer, mit dem das Ausstempeln kappen wird (E80). In JEDEM Zweig.
    blocks_today: List[ClockBlock] = []
    grace_minutes: int = 15
```

- [ ] **Step 4: Helfer und Rückgaben in `get_clock_status`**

In `backend/app/routers/time_entries.py` direkt vor `@router.get("/clock-status", response_model=ClockStatusResponse)`:

```python
def _clock_blocks_and_grace(db: Session, user: User, today: date, open_entry) -> tuple:
    """Spec 2026-10-08, 8.4/11.1/14 (PR2): Blöcke von heute als ``{"start",
    "end"}`` und der Puffer, mit dem ``clock_out`` kappen wird — der
    gespeicherte des offenen Eintrags (E80), sonst der aktuelle
    Mandanten-Puffer. Ohne Stundenzählung kappt nichts → keine Blöcke."""
    from app.services import work_blocks_service, work_window_service

    grace = (
        work_window_service.grace_for_entry(db, open_entry)
        if open_entry is not None
        else work_window_service.get_grace_minutes(db, user.tenant_id)
    )
    if not getattr(user, "track_hours", True):
        return [], grace
    blocks = [
        {
            "start": work_blocks_service.minutes_to_hhmm(start),
            "end": work_blocks_service.minutes_to_hhmm(end),
        }
        for start, end in work_window_service.get_scheduled_blocks(db, user, today)
    ]
    return blocks, grace
```

In `get_clock_status` direkt nach `target_hours = _today_target_hours(db, current_user, today)`:

```python
    blocks_today, grace_minutes = _clock_blocks_and_grace(db, current_user, today, open_entry)
```

Beide Rückgaben bekommen die zwei Felder — die frühe Rückgabe ohne offenen Eintrag:

```python
    if not open_entry:
        return ClockStatusResponse(
            is_clocked_in=False,
            today_net_minutes=closed_minutes,
            today_target_hours=target_hours,
            blocks_today=blocks_today,
            grace_minutes=grace_minutes,
        )
```

und die Rückgabe am Ende:

```python
    return ClockStatusResponse(
        is_clocked_in=True,
        current_entry=response_entry,
        elapsed_minutes=elapsed,
        today_net_minutes=closed_minutes + running_net,
        today_target_hours=target_hours,
        blocks_today=blocks_today,
        grace_minutes=grace_minutes,
    )
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_clock_status_blocks.py tests/test_494_clock_status_today.py tests/test_write_path_locks.py tests/test_auto_close_blocks.py -q -p no:cacheprovider`
Expected: PASS (die PR1-Spione in `test_write_path_locks.py` sehen die neuen Aufrufe erst nach der Ankersperre bzw. ohne Sperrpflicht im lesenden Zweig)

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/time_entry.py backend/app/routers/time_entries.py backend/tests/test_clock_status_blocks.py
git commit -F - <<'EOF'
feat(bloecke): clock-status liefert blocks_today und grace_minutes (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: `presence_service` — Anwesenheit laut Stempel und `BREAK_IN_GAP`

**Files:**
- Create: `backend/app/services/presence_service.py`
- Test (neu): `backend/tests/test_arbzg_blocks.py`

**Interfaces:**
- Consumes: `work_window_service.presence_minutes(entry) -> int` (PR1 Task 3); `TimeEntry.net_hours`, `.uncredited_minutes`, `.auto_closed` (PR1)
- Produces (in `app.services.presence_service`):
  - Konstanten `PRESENCE_DAILY_CODE = "PRESENCE_DAILY_HOURS"`, `PRESENCE_BREAK_CODE = "PRESENCE_BREAK"`, `PRESENCE_WEEKLY_CODE = "PRESENCE_WEEKLY_HOURS"`, `BREAK_IN_GAP_CODE = "BREAK_IN_GAP"`, `DAILY_LIMIT_MINUTES = 600`, `WEEKLY_LIMIT_MINUTES = 2880`
  - `class DayPresence(NamedTuple): presence_minutes: int; credited_minutes: int; recorded_break_minutes: int; has_gap: bool`
  - `credited_minutes(entries: Sequence) -> int` (Σ `net_hours` geschlossener Einträge in Minuten)
  - `closed_entries(db: Session, user, start: date, end: date) -> list[TimeEntry]` (F-026)
  - `day_presence(entries: Sequence) -> DayPresence` (rein; nimmt ORM-Objekte oder Gleichartige mit `start_time`, `end_time`, `raw_start_time`, `raw_end_time`, `break_minutes`, `auto_closed`, `uncredited_minutes`, `net_hours`)
  - `daily_presence_warnings(day: DayPresence, *, break_check_passed: bool) -> list[str]`
  - `weekly_presence_warning(entries: Sequence) -> Optional[str]`
  - `break_in_gap_warning(entry) -> Optional[str]`
  - `presence_warnings(db: Session, user, d: date, *, break_check_passed: bool, entry=None) -> list[str]` — nach dem Schreiben aufrufen; Reihenfolge `BREAK_IN_GAP`, `PRESENCE_DAILY_HOURS`, `PRESENCE_BREAK`, `PRESENCE_WEEKLY_HOURS`; `[]` bei `exempt_from_arbzg`
  - Format jeder Warnung: `"CODE: Text"` (Text wörtlich Spec 8.3/8.4, Stunden als `H:MM`)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_arbzg_blocks.py`:

```python
"""Spec 2026-10-08, 8.3 / 8.4 (P14, P22): weiche Warnungen auf der Anwesenheit
laut Stempel und der Pausen-Doppelabzug (PR2)."""
import uuid
from datetime import time, timedelta

from app.models import TimeEntry
from app.models.tenant import Tenant
from app.services import presence_service as ps
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import MON


def _e(start, end, brk=0, unc=0, raw_start=None, raw_end=None, auto=False):
    return TimeEntry(start_time=start, end_time=end, break_minutes=brk, uncredited_minutes=unc,
                     raw_start_time=raw_start, raw_end_time=raw_end, auto_closed=auto)


def _codes(warnings):
    return [w.split(":", 1)[0] for w in warnings]


def test_k1_break_with_gap_text():
    day = ps.day_presence([_e(time(8), time(18), unc=150)])
    assert day == ps.DayPresence(600, 450, 0, True)
    assert ps.daily_presence_warnings(day, break_check_passed=True) == [
        "PRESENCE_BREAK: §4 ArbZG: Durchgehend über die Lücke zwischen den Arbeitsblöcken "
        "gestempelt – eine Ruhepause ist nicht erfasst (10:00 h Anwesenheit). Die Lücke gilt "
        "nur dann als Pause, wenn sie tatsächlich frei war."
    ]


def test_k7_daily_and_break():
    day = ps.day_presence([_e(time(7, 45), time(18, 15), unc=150, raw_start=time(7), raw_end=time(19))])
    warnings = ps.daily_presence_warnings(day, break_check_passed=True)
    assert _codes(warnings) == ["PRESENCE_DAILY_HOURS", "PRESENCE_BREAK"]
    assert warnings[0] == (
        "PRESENCE_DAILY_HOURS: §3 ArbZG: Laut Stempel 12:00 h anwesend (abzüglich erfasster "
        "Pausen) – mehr als 10 Stunden. Angerechnet werden 8:00 h; die Höchstgrenze gilt für "
        "die tatsächliche Arbeitszeit."
    )


def test_k9_recorded_pause_too_short_k21_enough():
    k9 = ps.day_presence([_e(time(8), time(18), brk=30, unc=150)])
    assert k9.presence_minutes == 570 and k9.recorded_break_minutes == 30
    assert _codes(ps.daily_presence_warnings(k9, break_check_passed=True)) == ["PRESENCE_BREAK"]
    k21 = ps.day_presence([_e(time(8), time(18), brk=45, unc=150)])
    assert ps.daily_presence_warnings(k21, break_check_passed=True) == []


def test_k19_warns_although_credited_time_needs_no_break():
    day = ps.day_presence([_e(time(8), time(18), unc=270)])
    assert _codes(ps.daily_presence_warnings(day, break_check_passed=True)) == ["PRESENCE_BREAK"]


def test_hull_only_text():
    day = ps.day_presence([_e(time(8), time(13, 45), raw_start=time(6))])
    assert ps.daily_presence_warnings(day, break_check_passed=True) == [
        "PRESENCE_BREAK: §4 ArbZG: Laut Stempel 7:45 h anwesend ohne ausreichende erfasste "
        "Ruhepause; angerechnet werden nur 5:45 h. Die Pausenpflicht gilt für die tatsächliche "
        "Arbeitszeit."
    ]


def test_failed_or_waived_break_check_suppresses_presence_break():
    day = ps.day_presence([_e(time(8), time(18), unc=150)])
    assert ps.daily_presence_warnings(day, break_check_passed=False) == []


def test_hard_daily_limit_on_credited_time_suppresses_presence_daily():
    day = ps.day_presence([_e(time(7), time(18, 30))])     # angerechnet 11:30 h → harte §3 griff
    assert "PRESENCE_DAILY_HOURS" not in _codes(ps.daily_presence_warnings(day, break_check_passed=True))


def test_auto_closed_presence_ends_at_the_effective_end():
    """P18: 23:59 ist kein Stempel — mit 23:59 wären es 14:59 h + 1 h Anwesenheit."""
    auto = _e(time(10), time(18, 15), raw_end=time(23, 59), auto=True)
    later = _e(time(19), time(20))
    day = ps.day_presence([auto, later])
    assert day.presence_minutes == 495 + 60
    assert "PRESENCE_DAILY_HOURS" not in _codes(ps.daily_presence_warnings(day, break_check_passed=True))


# Review Focus 1: ohne Kappung ist Anwesenheit = Anrechnung — keine Zusatzwarnung.
def test_regular_days_without_blocks_never_warn():
    for entries in (
        [_e(time(8), time(17), brk=45)],
        [_e(time(8), time(12)), _e(time(12, 30), time(17))],
        [_e(time(8), time(14, 30), brk=30)],
    ):
        day = ps.day_presence(entries)
        assert ps.daily_presence_warnings(day, break_check_passed=True) == [], entries


def test_gap_between_entries_counts_as_recorded_break_overlap_does_not():
    assert ps.day_presence([_e(time(8), time(12)), _e(time(12, 30), time(17))]).recorded_break_minutes == 30
    overlap = ps.day_presence([_e(time(8), time(12)), _e(time(11), time(13))])
    assert overlap.recorded_break_minutes == 0


def test_weekly_presence():
    clamped = [_e(time(8), time(18), unc=150) for _ in range(5)]
    assert ps.weekly_presence_warning(clamped) == (
        "PRESENCE_WEEKLY_HOURS: §3 ArbZG: Laut Stempel 50:00 h in dieser Woche anwesend "
        "(abzüglich erfasster Pausen) – mehr als 48 Stunden. Angerechnet werden 37:30 h; "
        "die Grenze gilt für die tatsächliche Arbeitszeit."
    )
    # angerechnet selbst > 48 h → WEEKLY_HOURS_WARNING kam schon (P22)
    assert ps.weekly_presence_warning([_e(time(8), time(18)) for _ in range(5)]) is None


def test_break_in_gap():
    assert ps.break_in_gap_warning(_e(time(8), time(18), brk=30, unc=150)) == (
        "BREAK_IN_GAP: Pause in der Lücke wird zusätzlich abgezogen: 30 Min Pause und 2:30 h "
        "nicht angerechnet zwischen den Arbeitsblöcken. Lag die Pause in der Lücke, bitte die "
        "Pause auf 0 setzen."
    )
    assert ps.break_in_gap_warning(_e(time(8), time(18), unc=150)) is None
    assert ps.break_in_gap_warning(_e(time(7, 45), time(16), brk=30, raw_start=time(7))) is None


def test_presence_warnings_reads_the_day_and_week_from_the_db(db, test_user):
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    db.add(other)
    k9 = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                   start_time=time(8), end_time=time(18), break_minutes=30, uncredited_minutes=150)
    db.add(k9)
    # F-026: fremder Mandant — gezählt ergäbe das 11:00 h Anwesenheit (PRESENCE_DAILY).
    db.add(TimeEntry(tenant_id=other.id, user_id=test_user.id, date=MON,
                     start_time=time(19), end_time=time(20, 30), break_minutes=0))
    db.commit()
    warnings = ps.presence_warnings(db, test_user, MON, break_check_passed=True, entry=k9)
    assert _codes(warnings) == ["BREAK_IN_GAP", "PRESENCE_BREAK"]
    test_user.exempt_from_arbzg = True
    assert ps.presence_warnings(db, test_user, MON, break_check_passed=True, entry=k9) == []


def test_presence_warnings_week(db, test_user):
    for i in range(5):
        db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON + timedelta(days=i),
                         start_time=time(8), end_time=time(18), break_minutes=0, uncredited_minutes=150))
    db.commit()
    codes = _codes(ps.presence_warnings(db, test_user, MON + timedelta(days=4), break_check_passed=True))
    assert codes == ["PRESENCE_BREAK", "PRESENCE_WEEKLY_HOURS"]
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_arbzg_blocks.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'presence_service'`

- [ ] **Step 3: `presence_service.py` anlegen**

`backend/app/services/presence_service.py`:

```python
"""Spec 2026-10-08, 8.3 / 8.4 (P14, P22): weiche ArbZG-Warnungen auf der
TATSÄCHLICHEN Anwesenheit laut Stempel — und der Hinweis auf den
Pausen-Doppelabzug (``BREAK_IN_GAP``).

Die harten Prüfungen (§3 10 h, §4) rechnen weiter auf der ANGERECHNETEN Zeit
(E43). Eine Lücke zwischen Arbeitsblöcken oder eine Neukappung darf einen
echten Verstoß aber nicht verschwinden lassen (Rechtsbewertung Pflicht 4):
diese Warnungen sehen die Rohstempel. Sie blockieren nie.

Anwesenheit eines Eintrags = ``work_window_service.presence_minutes`` —
Rohstempel abzüglich erfasster Pause, bei ``auto_closed`` bis zum wirksamen
Ende (P18), offene Einträge zählen nicht. Lücken werden NICHT abgezogen.

Ohne Kappung ist Anwesenheit = angerechnete Zeit; dann greift bereits die
harte Prüfung, und hier kommt nichts dazu.
"""
from datetime import date, timedelta
from typing import NamedTuple, Optional, Sequence

from sqlalchemy.orm import Session

from app.models import TimeEntry
from app.services import work_window_service

PRESENCE_DAILY_CODE = "PRESENCE_DAILY_HOURS"
PRESENCE_BREAK_CODE = "PRESENCE_BREAK"
PRESENCE_WEEKLY_CODE = "PRESENCE_WEEKLY_HOURS"
BREAK_IN_GAP_CODE = "BREAK_IN_GAP"

DAILY_LIMIT_MINUTES = 10 * 60
WEEKLY_LIMIT_MINUTES = 48 * 60
# §4 Satz 1 ArbZG: > 9 h → 45 Min, > 6 h → 30 Min (von oben nach unten).
_BREAK_RULES = ((9 * 60, 45), (6 * 60, 30))


class DayPresence(NamedTuple):
    presence_minutes: int        # Σ presence_minutes der geschlossenen Einträge
    credited_minutes: int        # Σ net_hours (angerechnet), in Minuten
    recorded_break_minutes: int  # erfasste Pausen ≥ 15 + Abstände zwischen Einträgen ≥ 15
    has_gap: bool                # mindestens ein Eintrag mit uncredited_minutes > 0


def _hm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _min(t) -> int:
    return t.hour * 60 + t.minute


def credited_minutes(entries: Sequence) -> int:
    """Σ angerechnete Zeit (``net_hours``) der geschlossenen Einträge in Minuten."""
    total = sum(float(e.net_hours or 0) for e in entries if e.end_time is not None)
    return int(round(total * 60))


def closed_entries(db: Session, user, start: date, end: date) -> list:
    """Geschlossene Einträge der Person im Zeitraum (F-026: Mandantenfilter)."""
    return (
        db.query(TimeEntry)
        .filter(
            TimeEntry.user_id == user.id,
            TimeEntry.tenant_id == user.tenant_id,
            TimeEntry.date >= start,
            TimeEntry.date <= end,
            TimeEntry.end_time.isnot(None),
        )
        .all()
    )


def _presence_span(entry) -> tuple:
    start = entry.raw_start_time or entry.start_time
    if getattr(entry, "auto_closed", False):
        end = entry.end_time            # P18: 23:59 ist kein Stempel
    else:
        end = entry.raw_end_time or entry.end_time
    return _min(start), _min(end)


def day_presence(entries: Sequence) -> DayPresence:
    """Anwesenheit des Tages über die GESCHLOSSENEN Einträge. Abstände zwischen
    Einträgen über die Vereinigung der Anwesenheits-Intervalle (eine
    Überlappung ergibt keinen erfundenen Abstand)."""
    closed = [e for e in entries if e.end_time is not None]
    gaps, reach = 0, None
    for start, end in sorted(_presence_span(e) for e in closed):
        if reach is not None and start - reach >= 15:
            gaps += start - reach
        reach = end if reach is None else max(reach, end)
    declared = sum(int(e.break_minutes or 0) for e in closed if int(e.break_minutes or 0) >= 15)
    return DayPresence(
        presence_minutes=sum(work_window_service.presence_minutes(e) for e in closed),
        credited_minutes=credited_minutes(closed),
        recorded_break_minutes=declared + gaps,
        has_gap=any(int(getattr(e, "uncredited_minutes", 0) or 0) > 0 for e in closed),
    )


def _required_break(presence: int) -> int:
    for limit, need in _BREAK_RULES:
        if presence > limit:
            return need
    return 0


def daily_presence_warnings(day: DayPresence, *, break_check_passed: bool) -> list:
    """``PRESENCE_DAILY_HOURS`` nur, wenn die harte §3-Prüfung auf angerechneter
    Zeit nicht gegriffen hat (angerechnet ≤ 10 h). ``PRESENCE_BREAK`` nur, wenn
    die §4-Prüfung auf angerechneter Zeit BESTANDEN hat — weder 400 noch
    Ausnahme (``BREAK_WAIVER``/202); seit #499 gibt es kein ``BREAK_WARNING``
    mehr, deshalb entscheidet der Aufrufer am Ergebnis von
    ``validate_daily_break`` (P14). Keine Bedingung „nur dank Lückensegmenten"."""
    out = []
    if day.presence_minutes > DAILY_LIMIT_MINUTES and day.credited_minutes <= DAILY_LIMIT_MINUTES:
        out.append(
            f"{PRESENCE_DAILY_CODE}: §3 ArbZG: Laut Stempel {_hm(day.presence_minutes)} h anwesend "
            f"(abzüglich erfasster Pausen) – mehr als 10 Stunden. Angerechnet werden "
            f"{_hm(day.credited_minutes)} h; die Höchstgrenze gilt für die tatsächliche Arbeitszeit."
        )
    need = _required_break(day.presence_minutes)
    if break_check_passed and need and day.recorded_break_minutes < need:
        if day.has_gap:
            text = (
                f"§4 ArbZG: Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – "
                f"eine Ruhepause ist nicht erfasst ({_hm(day.presence_minutes)} h Anwesenheit). "
                f"Die Lücke gilt nur dann als Pause, wenn sie tatsächlich frei war."
            )
        else:
            text = (
                f"§4 ArbZG: Laut Stempel {_hm(day.presence_minutes)} h anwesend ohne ausreichende "
                f"erfasste Ruhepause; angerechnet werden nur {_hm(day.credited_minutes)} h. "
                f"Die Pausenpflicht gilt für die tatsächliche Arbeitszeit."
            )
        out.append(f"{PRESENCE_BREAK_CODE}: {text}")
    return out


def weekly_presence_warning(entries: Sequence) -> Optional[str]:
    """P22: Anwesenheit der Kalenderwoche (Mo–So) > 48 h, solange die
    angerechnete Zeit ≤ 48 h ist (sonst kam ``WEEKLY_HOURS_WARNING`` schon)."""
    closed = [e for e in entries if e.end_time is not None]
    presence = sum(work_window_service.presence_minutes(e) for e in closed)
    credited = credited_minutes(closed)
    if presence > WEEKLY_LIMIT_MINUTES and credited <= WEEKLY_LIMIT_MINUTES:
        return (
            f"{PRESENCE_WEEKLY_CODE}: §3 ArbZG: Laut Stempel {_hm(presence)} h in dieser Woche "
            f"anwesend (abzüglich erfasster Pausen) – mehr als 48 Stunden. Angerechnet werden "
            f"{_hm(credited)} h; die Grenze gilt für die tatsächliche Arbeitszeit."
        )
    return None


def break_in_gap_warning(entry) -> Optional[str]:
    """Spec 8.4 (E45): Pause > 0 UND nicht angerechnete Lücke am selben Eintrag —
    der Doppelabzug wird sichtbar statt still."""
    brk = int(entry.break_minutes or 0)
    gap = int(getattr(entry, "uncredited_minutes", 0) or 0)
    if brk > 0 and gap > 0:
        return (
            f"{BREAK_IN_GAP_CODE}: Pause in der Lücke wird zusätzlich abgezogen: {brk} Min Pause "
            f"und {_hm(gap)} h nicht angerechnet zwischen den Arbeitsblöcken. Lag die Pause in der "
            f"Lücke, bitte die Pause auf 0 setzen."
        )
    return None


def presence_warnings(db: Session, user, d: date, *, break_check_passed: bool, entry=None) -> list:
    """Alle weichen Warnungen aus 8.3/8.4 für den Tag ``d`` — NACH dem Schreiben
    aufrufen (die DB enthält den Eintrag). ``entry`` = der eben geschriebene
    Eintrag (für ``BREAK_IN_GAP``). §18 (``exempt_from_arbzg``) → keine."""
    if user is None or getattr(user, "exempt_from_arbzg", False):
        return []
    out = []
    if entry is not None:
        gap = break_in_gap_warning(entry)
        if gap:
            out.append(gap)
    out.extend(daily_presence_warnings(
        day_presence(closed_entries(db, user, d, d)), break_check_passed=break_check_passed,
    ))
    monday = d - timedelta(days=d.weekday())
    weekly = weekly_presence_warning(closed_entries(db, user, monday, monday + timedelta(days=6)))
    if weekly:
        out.append(weekly)
    return out
```

- [ ] **Step 4: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_arbzg_blocks.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/presence_service.py backend/tests/test_arbzg_blocks.py
git commit -F - <<'EOF'
feat(bloecke): presence_service — weiche Warnungen auf Anwesenheit laut Stempel (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 4: Anwesenheits-Warnungen in den Schreibpfaden und Spalte „Meldung" der Falltabelle

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499: §4 in `clock_out` steht vor dem Schreiben und blockiert über `break_waiver_rejection`; in `create_time_entry`/`update_time_entry` kehren 400 und der 202-Antrag vor dem Commit zurück. Vor Beginn die fünf Funktionen lesen und die Variablen `break_error` (clock_out) bzw. `break_waiver_active` (übrige) bestätigen.)

**Files:**
- Modify: `backend/tests/work_blocks_cases.py` (nach `K_CASES`)
- Modify: `backend/app/routers/time_entries.py` (Import; `clock_out`, `create_time_entry`, `update_time_entry`)
- Modify: `backend/app/routers/admin_time_entries.py` (Import; `admin_create_time_entry`, `admin_update_time_entry`)
- Test: `backend/tests/test_arbzg_blocks.py` (anhängen)

**Interfaces:**
- Consumes: `presence_service.presence_warnings(db, user, d, *, break_check_passed, entry=None)` (Task 3); `tests.work_blocks_cases.K_CASES`, `EASTER_MONDAY` (PR1 Task 3)
- Produces:
  - `tests.work_blocks_cases.K_HTTP_400 = "HTTP_400"`, `tests.work_blocks_cases.K_CODES: dict[str, Optional[frozenset[str]]]` — Spec 6.3 Spalte „Meldung" für `POST /api/time-entries/` (Person selbst, Falltag = heute); `None` = über diesen Pfad nicht erzeugbar (K2, K10, K14, K15)
  - Ausgabe der Warnungen aus Spec 8.3/8.4 an `clock_out`, `create_time_entry`, `update_time_entry`, `admin_create_time_entry`, `admin_update_time_entry` (Anerkennen: Task 5, CR-Genehmigung inkl. Bulk: Task 6, XLS-Vorschau: Task 12)

- [ ] **Step 1: Spalte „Meldung" in die Falltabelle**

In `backend/tests/work_blocks_cases.py` direkt nach der Liste `K_CASES` (vor `def k_user`):

```python
# Spec 6.3, Spalte „Meldung" (PR2): Warncodes, die POST /api/time-entries/ —
# manuelles Anlegen durch die Person selbst, Falltag = heute — für den
# GESCHLOSSENEN Eintrag liefert. None = über diesen Pfad nicht erzeugbar
# (offen K2/K14, anerkannt K10 → Task 5, Auto-Close K15). K20 hier als ein
# Eintrag 07:00–18:00 (EARLY_START gibt es nur beim Einstempeln). K_HTTP_400 =
# harte §4-Sperre (K6). Der Frontend-Zwilling utils/workBlocksCases.ts führt
# dieselben IDs.
K_HTTP_400 = "HTTP_400"
_CLAMPED = "WORK_WINDOW_CLAMPED"
K_CODES: dict = {
    "K1": frozenset({_CLAMPED, "PRESENCE_BREAK"}),
    "K2": None,
    "K2b": frozenset({_CLAMPED}),
    "K3": frozenset({_CLAMPED}),
    "K4": frozenset(),
    "K5": frozenset({_CLAMPED}),
    "K6": frozenset({K_HTTP_400}),
    "K7": frozenset({_CLAMPED, "PRESENCE_DAILY_HOURS", "PRESENCE_BREAK"}),
    "K8": frozenset({_CLAMPED}),
    "K9": frozenset({_CLAMPED, "BREAK_IN_GAP", "PRESENCE_BREAK"}),
    "K10": None,
    "K11": frozenset({"HOLIDAY_WORK", "DAILY_HOURS_WARNING"}),
    "K12": frozenset({"SUNDAY_WORK", "DAILY_HOURS_WARNING"}),
    "K13": frozenset({"DAILY_HOURS_WARNING"}),
    "K14": None,
    "K15": None,
    "K16": frozenset({_CLAMPED}),
    "K17": frozenset({_CLAMPED, "DAILY_HOURS_WARNING", "PRESENCE_DAILY_HOURS", "PRESENCE_BREAK"}),
    "K18": frozenset({_CLAMPED, "PRESENCE_BREAK"}),
    "K19": frozenset({_CLAMPED, "PRESENCE_BREAK"}),
    "K20": frozenset({_CLAMPED, "PRESENCE_DAILY_HOURS", "PRESENCE_BREAK"}),
    "K21": frozenset({_CLAMPED, "BREAK_IN_GAP"}),
}
assert set(K_CODES) == {c.id for c in K_CASES}
```

- [ ] **Step 2: Failing tests anhängen**

An `backend/tests/test_arbzg_blocks.py` anhängen:

```python
# ── Schreibpfade (Spec 8.3 „Ausgegeben an") und Falltabelle (6.3) ─────────────
import datetime as dt  # noqa: E402

import pytest  # noqa: E402

import app.routers.time_entries as te  # noqa: E402
import app.schemas.time_entry as te_schema  # noqa: E402
from app.models.public_holiday import PublicHoliday  # noqa: E402
from app.models.system_setting import SystemSetting  # noqa: E402
from app.services.holiday_service import invalidate_holiday_cache  # noqa: E402
from tests.test_endpoints import (  # noqa: F401,E402 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_cases import EASTER_MONDAY, K_CASES, K_CODES, K_HTTP_400  # noqa: E402
from tests.work_blocks_fixtures import K_BLOCKS, block_week  # noqa: E402

HTTP_CASES = [c for c in K_CASES if K_CODES[c.id] is not None]


@pytest.fixture
def k_http(_db_session, employee_user):
    _db_session.add(PublicHoliday(date=EASTER_MONDAY, name="Ostermontag", year=2026,
                                  tenant_id=DEFAULT_TENANT_ID))
    _db_session.add(SystemSetting(key="special_day_dec24_mode", value="half_day",
                                  tenant_id=DEFAULT_TENANT_ID))
    _db_session.commit()
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


def _today(monkeypatch, d, hh=10):
    monkeypatch.setattr(te, "_today_local", lambda: d)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(d.year, d.month, d.day, hh, 0))
    monkeypatch.setattr(te_schema, "today_local", lambda: d)


def _resp_codes(r):
    return {w.split(":", 1)[0] for w in r.json()["warnings"]}


@pytest.mark.parametrize("case", HTTP_CASES, ids=[c.id for c in HTTP_CASES])
def test_k_table_codes_on_manual_create(_db_session, employee_user, employee_client, k_http,
                                        monkeypatch, case):
    """Spec 6.3, Spalte „Meldung": POST /api/time-entries/ durch die Person selbst."""
    employee_user.work_blocks = case.blocks
    employee_user.track_hours = case.track_hours
    _db_session.commit()
    _today(monkeypatch, case.day)
    r = employee_client.post("/api/time-entries/", json={
        "date": case.day.isoformat(),
        "start_time": case.start.strftime("%H:%M"),
        "end_time": case.end.strftime("%H:%M"),
        "break_minutes": case.break_minutes,
    })
    if K_CODES[case.id] == frozenset({K_HTTP_400}):
        assert r.status_code == 400, r.text   # K6: harte §4-Sperre wie heute
        return
    assert r.status_code == 201, r.text
    assert _resp_codes(r) == K_CODES[case.id]


def test_clock_out_reports_presence_break(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=None, break_minutes=0,
                              clamp_grace_minutes=15))
    _db_session.commit()
    _today(monkeypatch, MON, 18)
    r = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0})
    assert r.status_code == 200, r.text
    assert {"WORK_WINDOW_CLAMPED", "PRESENCE_BREAK"} <= _resp_codes(r)


def test_employee_update_reports_presence(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                  start_time=time(8), end_time=time(12), break_minutes=0)
    _db_session.add(e)
    _db_session.commit()
    _today(monkeypatch, MON, 19)
    r = employee_client.put(f"/api/time-entries/{e.id}", json={"end_time": "18:00"})
    assert r.status_code == 200, r.text
    assert "PRESENCE_BREAK" in _resp_codes(r)


def test_exempt_person_gets_no_presence_warnings(_db_session, employee_user, employee_client,
                                                 monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    employee_user.exempt_from_arbzg = True
    _db_session.commit()
    _today(monkeypatch, MON)
    r = employee_client.post("/api/time-entries/", json={
        "date": MON.isoformat(), "start_time": "07:00", "end_time": "19:00", "break_minutes": 30,
    })
    assert r.status_code == 201, r.text
    assert _resp_codes(r) == {"WORK_WINDOW_CLAMPED"}


def test_weekly_presence_on_create(_db_session, employee_user, employee_client, monkeypatch):
    week = [("08:00", "12:00"), ("15:00", "18:00")]
    employee_user.work_blocks = block_week(mon=week, tue=week, wed=week, thu=week, fri=week)
    for i in range(4):
        _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id,
                                  date=MON + timedelta(days=i), start_time=time(8),
                                  end_time=time(18), break_minutes=0, uncredited_minutes=150,
                                  clamp_grace_minutes=15))
    _db_session.commit()
    friday = MON + timedelta(days=4)
    _today(monkeypatch, friday)
    r = employee_client.post("/api/time-entries/", json={
        "date": friday.isoformat(), "start_time": "08:00", "end_time": "18:00", "break_minutes": 0,
    })
    assert r.status_code == 201, r.text
    codes = _resp_codes(r)
    assert "PRESENCE_WEEKLY_HOURS" in codes
    assert "WEEKLY_HOURS_WARNING" not in codes   # angerechnet 37:30 h


def test_admin_create_and_update_report_presence(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    r = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "18:00", "break_minutes": 30,
    })
    assert r.status_code == 201, r.text
    assert {"WORK_WINDOW_CLAMPED", "BREAK_IN_GAP", "PRESENCE_BREAK"} <= _resp_codes(r)

    other = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id,
                      date=MON + timedelta(days=7), start_time=time(8), end_time=time(12),
                      break_minutes=0)
    _db_session.add(other)
    _db_session.commit()
    r = admin_client.put(f"/api/admin/time-entries/{other.id}", json={"end_time": "18:00"})
    assert r.status_code == 200, r.text
    assert "PRESENCE_BREAK" in _resp_codes(r)
```

- [ ] **Step 3: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_arbzg_blocks.py -q -p no:cacheprovider`
Expected: FAIL — u. a. `K1`, `K7`, `K9`, `K17`–`K21`: die `PRESENCE_*`/`BREAK_IN_GAP`-Codes fehlen; `K4`, `K11`–`K13`, `K2b`, `K3`, `K5`, `K6`, `K8`, `K16` und `test_exempt_person_gets_no_presence_warnings` sind schon grün.

- [ ] **Step 4: `time_entries.py` verdrahten**

Bei den übrigen `app.services`-Importen oben in `backend/app/routers/time_entries.py`:

```python
from app.services import presence_service
```

`clock_out` — direkt vor `response = TimeEntryResponse.model_validate(open_entry)`:

```python
    # Spec 8.3/8.4 (P14, P22): weiche Warnungen auf der Anwesenheit laut Stempel
    # und der Pausen-Doppelabzug — nach dem Commit, die Tagessumme enthält den
    # eben geschlossenen Eintrag. §4 „bestanden" = weder 400 (oben) noch Ausnahme.
    clock_out_warnings.extend(presence_service.presence_warnings(
        db, current_user, open_entry.date,
        break_check_passed=break_error is None, entry=open_entry,
    ))
```

`create_time_entry` — direkt nach `db.commit()` / `db.refresh(entry)` (vor dem MiLoG-Block):

```python
    # Spec 8.3/8.4 (P14, P22): §4 „bestanden" = keine Ausnahme nötig (400 und
    # der 202-Antrag sind oben schon zurückgekehrt).
    warnings.extend(presence_service.presence_warnings(
        db, current_user, entry.date,
        break_check_passed=not break_waiver_active, entry=entry,
    ))
```

`update_time_entry` — nach dem Block `if not exempt:` mit `SUNDAY_WORK`/`HOLIDAY_WORK`/§6, vor dem Kommentar „# #377 § 2 Abs. 2 MiLoG: auch beim Bearbeiten":

```python
    # Spec 8.3/8.4 (P14, P22): wie beim Anlegen; nur für geschlossene Einträge.
    if entry.end_time is not None:
        update_warnings.extend(presence_service.presence_warnings(
            db, _entry_owner, entry.date,
            break_check_passed=not break_waiver_active, entry=entry,
        ))
```

- [ ] **Step 5: `admin_time_entries.py` verdrahten**

Import `from app.services import work_window_service` ersetzen durch:

```python
from app.services import presence_service, work_window_service
```

`admin_create_time_entry` — nach `db.commit()` / `db.refresh(entry)`, vor `response = TimeEntryResponse.model_validate(entry)`:

```python
    # Spec 8.3/8.4 (P14, P22): weiche Anwesenheits-Warnungen für die Person.
    admin_create_warnings.extend(presence_service.presence_warnings(
        db, user, entry.date, break_check_passed=not break_waiver_active, entry=entry,
    ))
```

`admin_update_time_entry` — nach `db.commit()` / `db.refresh(entry)`, vor `response = TimeEntryResponse.model_validate(entry)`:

```python
    # Spec 8.3/8.4 (P14, P22): weiche Anwesenheits-Warnungen für die Person.
    if entry.end_time is not None and affected_user is not None:
        admin_update_warnings.extend(presence_service.presence_warnings(
            db, affected_user, entry.date,
            break_check_passed=not break_waiver_active, entry=entry,
        ))
```

- [ ] **Step 6: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (keine neuen Fehlschläge gegenüber der Ausgangszahl). Fällt ein Bestandstest, der eine **exakte** Warnliste erwartet, an einem gekappten Eintrag mit neuem `PRESENCE_*`-Code: den Code in die Erwartung aufnehmen (das ist die beabsichtigte Wirkung) und den Test im Commit nennen.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/work_blocks_cases.py backend/tests/test_arbzg_blocks.py backend/app/routers/time_entries.py backend/app/routers/admin_time_entries.py
git commit -F - <<'EOF'
feat(bloecke): PRESENCE_*/BREAK_IN_GAP an Stempel-, Erfassungs- und Admin-Pfaden (PR2)

Falltabelle K1–K21 um die Spalte „Meldung" (K_CODES) ergänzt.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: „Anerkennen" — `credit_override_service` und Endpunkt

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499 ändert `validate_daily_break`-Aufrufer; `override_warnings` nutzt die PR1-Signatur `validate_daily_break(db, user, …, *, uncredited_segments, tenant_id, exclude_entry_id=None)`.)

**Files:**
- Create: `backend/app/services/credit_override_service.py`
- Modify: `backend/app/routers/admin_time_entries.py` (Importe; neuer Endpunkt nach `admin_update_time_entry`)
- Test (neu): `backend/tests/test_credit_override.py`
- Test: `backend/tests/test_write_path_locks.py` (anhängen)

**Interfaces:**
- Consumes: `work_window_service.credit_summary_text` (Task 1); `presence_service.presence_warnings`, `closed_entries`, `credited_minutes` (Task 3); `admin_helpers.lock_user_row` (PR1 Task 7); `validate_daily_break` (PR1 Task 5); `MAX_DAILY_HOURS_HARD`, `MAX_DAILY_HOURS_WARN`, `MAX_WEEKLY_HOURS_WARN` aus `routers/time_entries.py`
- Produces (in `app.services.credit_override_service`):
  - `CREDIT_OVERRIDE_SOURCE = "credit_override"`, `OPEN_ENTRY_DETAIL`, `AUTO_CLOSED_DETAIL` (Wortlaute Spec 11.4)
  - `start_taken_detail(t: time) -> str` — „Ein anderer Eintrag an diesem Tag beginnt bereits um HH:MM."
  - `load_entry_locked(db: Session, tenant_id, entry_id) -> Optional[TimeEntry]` (`with_for_update`, F-026)
  - `apply_credit_override(db: Session, entry: TimeEntry, *, changed_by_id, on_request: bool, change_request_id=None) -> bool` — Spec 13.3 Schritte 2–5 (ohne Sperren; der Aufrufer hält Anker vor Zeile); `False` = war schon anerkannt (idempotent, kein Protokoll); wirft `HTTPException` 400/409
  - `override_warnings(db: Session, user, entry: TimeEntry, *, include_weekly: bool = True) -> list[str]` — Schritt 6 (P4): `DAILY_HOURS_HARD: …`/`DAILY_HOURS_WARNING`, `BREAK_WARNING: …`, `WEEKLY_HOURS_WARNING`, plus `presence_warnings`
  - Endpunkt `POST /api/admin/time-entries/{entry_id}/credit-override` → `TimeEntryResponse` (200), 404 fremd/unbekannt, 400 offen/`auto_closed`, 409 Kollision

Abgrenzung der Tests aus Spec 17.3 `test_credit_override.py`: „überlebt Neukappung" gehört in den PR3-Plan (`reclamp_time_entries` überspringt `credit_override`, `test_reclamp.py`); MA-`PUT` → 409, Antragsgenehmigung (UPDATE) und XLS-Überschreiben behalten das Flag sind PR1-Tests (Task 9/10). Die Kollision (409) prüft hier die Anwendungsebene und läuft deshalb auch auf SQLite.

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_credit_override.py`:

```python
"""Spec 2026-10-08, 13.3 / P3 / P4 (PR2): „Anerkennen" — Felder, Protokoll,
weiche Warnungen, Dauerhaftigkeit."""
import uuid
from datetime import time

from app.models import TimeEntry, TimeEntryAuditLog
from app.models.tenant import Tenant
from app.services import credit_override_service as cos
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON


def _entry(db, user, start, end, **kw):
    e = TimeEntry(tenant_id=kw.pop("tenant_id", DEFAULT_TENANT_ID), user_id=user.id,
                  date=kw.pop("day", MON), start_time=start, end_time=end,
                  break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def _k7(db, user):
    """K7 wie nach PR1 gespeichert: 07:00–19:00 gestempelt, 07:45–18:15 angerechnet."""
    user.work_blocks = K_BLOCKS
    return _entry(db, user, time(7, 45), time(18, 15), raw_start_time=time(7),
                  raw_end_time=time(19), uncredited_minutes=150, clamp_grace_minutes=15)


def _post(client, entry):
    return client.post(f"/api/admin/time-entries/{entry.id}/credit-override")


def _override_logs(db):
    return db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.source == cos.CREDIT_OVERRIDE_SOURCE).all()


def _codes(r):
    return [w.split(":", 1)[0] for w in r.json()["warnings"]]


def test_sets_fields_and_writes_one_audit_row(_db_session, employee_user, admin_user, admin_client):
    e = _k7(_db_session, employee_user)
    r = _post(admin_client, e)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["start_time"], body["end_time"]) == ("07:00:00", "19:00:00")
    assert (body["raw_start_time"], body["raw_end_time"]) == (None, None)
    assert (body["uncredited_minutes"], body["not_credited_minutes"]) == (0, 0)
    assert body["credit_override"] is True
    assert body["clamp_grace_minutes"] == 15     # 13.3 Schritt 4: bleibt unverändert
    assert body["net_hours"] == 12.0
    [log] = _override_logs(_db_session)
    assert (log.action, log.user_id, log.changed_by) == ("update", employee_user.id, admin_user.id)
    assert (log.old_start_time, log.old_end_time) == (time(7, 45), time(18, 15))
    assert (log.new_start_time, log.new_end_time) == (time(7), time(19))
    assert log.old_note == (
        "angerechnet 8:00 h, nicht angerechnet 4:00 h, davon 2:30 h zwischen den Blöcken")
    assert log.new_note == "angerechnet 12:00 h — von der Verwaltung anerkannt"
    assert log.row_hash   # #121: über die Objektschicht geschrieben


def test_is_idempotent(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    assert _post(admin_client, e).status_code == 200
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["warnings"]) == (200, [])
    assert len(_override_logs(_db_session)) == 1


def test_open_entry_is_400(_db_session, employee_user, admin_client):
    e = _entry(_db_session, employee_user, time(8), None)
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["detail"]) == (400, cos.OPEN_ENTRY_DETAIL)


def test_auto_closed_entry_is_400(_db_session, employee_user, admin_client):
    """P18: 23:59 ist kein Stempel — Anerkennen öffnete sonst das Schlupfloch."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18, 15), raw_end_time=time(23, 59),
               uncredited_minutes=150, auto_closed=True)
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["detail"]) == (400, cos.AUTO_CLOSED_DETAIL)


def test_collision_at_the_raw_start_is_409(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    _entry(_db_session, employee_user, time(7), time(7, 30))
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["detail"]) == (
        409, "Ein anderer Eintrag an diesem Tag beginnt bereits um 07:00.")
    _db_session.refresh(e)
    assert e.credit_override is False


def test_hard_limits_are_only_soft_warnings(_db_session, employee_user, admin_client):
    """P4: 12 h ohne Pause — Anerkennen blockiert nie an §3/§4."""
    r = _post(admin_client, _k7(_db_session, employee_user))
    assert r.status_code == 200
    assert _codes(r) == ["DAILY_HOURS_HARD", "BREAK_WARNING"]


def test_k10_gives_only_the_8h_warning(_db_session, employee_user, admin_client):
    """Spec 6.3 K10: 08:00–18:00, Pause 45, anerkannt → 9,25 h, DAILY_HOURS_WARNING."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18), break_minutes=45,
               uncredited_minutes=150, clamp_grace_minutes=15)
    r = _post(admin_client, e)
    assert r.json()["net_hours"] == 9.25
    assert r.json()["warnings"] == ["DAILY_HOURS_WARNING"]


def test_entry_of_another_tenant_is_404(_db_session, employee_user, admin_client):
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    _db_session.add(other)
    _db_session.commit()
    e = _entry(_db_session, employee_user, time(7, 45), time(18, 15), tenant_id=other.id,
               raw_start_time=time(7), uncredited_minutes=150)
    assert _post(admin_client, e).status_code == 404


def test_admin_edit_keeps_the_recognition(_db_session, employee_user, admin_client):
    """P3: die Verwaltung bestätigt bei der Direktbearbeitung — das Flag bleibt."""
    e = _k7(_db_session, employee_user)
    assert _post(admin_client, e).status_code == 200
    r = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"note": "geprüft"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.credit_override, e.start_time, e.end_time, e.uncredited_minutes) == (
        True, time(7), time(19), 0)
```

An `backend/tests/test_write_path_locks.py` anhängen:

```python
def test_credit_override_locks_anchor_before_entry(_db_session, employee_user, admin_client, monkeypatch):
    """Spec 13.3 Schritt 1 / P5: Anker VOR der Eintragszeile — umgekehrt verklemmen
    sich Anerkennen und eine parallele Neukappung (40P01 → 500)."""
    from app.services import credit_override_service as cos

    _setup(_db_session, employee_user)
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                  start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                  raw_end_time=time(19), break_minutes=0, uncredited_minutes=150)
    _db_session.add(e)
    _db_session.commit()
    log = []
    real_lock, real_load = ate.lock_user_row, cos.load_entry_locked

    def spy_lock(db, tenant_id, user_id):
        log.append(("lock", str(user_id)))
        return real_lock(db, tenant_id, user_id)

    def spy_load(*a, **kw):
        log.append(("entry",))
        return real_load(*a, **kw)

    monkeypatch.setattr(ate, "lock_user_row", spy_lock)
    monkeypatch.setattr(cos, "load_entry_locked", spy_load)
    assert admin_client.post(f"/api/admin/time-entries/{e.id}/credit-override").status_code == 200
    assert log == [("lock", str(employee_user.id)), ("entry",)]
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_credit_override.py tests/test_write_path_locks.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'credit_override_service'`

- [ ] **Step 3: `credit_override_service.py` anlegen**

`backend/app/services/credit_override_service.py`:

```python
"""Spec 2026-10-08, 13.3 / P3 / P4 / P21: „Anerkennen" — die gesamte
gestempelte Zeit eines Eintrags wird angerechnet, dauerhaft.

EINE Quelle für beide Wege: die Admin-Aktion (``POST /admin/time-entries/{id}/
credit-override``) und die Genehmigung eines Antrags „Anrechnung beantragen"
bzw. „genehmigen und anerkennen" (``admin_change_requests``). Die Sperren
(Anker VOR Zeile, P5) nimmt der Aufrufer. Kein Pfad setzt das Flag zurück (P3),
eine Rücknahme gibt es nicht (P11).
"""
from datetime import time, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import TimeEntry, TimeEntryAuditLog
from app.services import presence_service, work_window_service

CREDIT_OVERRIDE_SOURCE = "credit_override"  # 15 Zeichen < varchar(40)
OPEN_ENTRY_DETAIL = "Ein offener Eintrag kann erst nach dem Ausstempeln anerkannt werden."
AUTO_CLOSED_DETAIL = (
    "Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen."
)
_BY_ADMIN = "von der Verwaltung anerkannt"
_ON_REQUEST = "auf Antrag der beschäftigten Person von der Verwaltung anerkannt"


def start_taken_detail(t: time) -> str:
    return f"Ein anderer Eintrag an diesem Tag beginnt bereits um {t.strftime('%H:%M')}."


def load_entry_locked(db: Session, tenant_id, entry_id) -> Optional[TimeEntry]:
    """Den Eintrag mit Zeilensperre laden — NACH der Ankersperre (P5)."""
    return (
        db.query(TimeEntry)
        .filter(TimeEntry.id == entry_id, TimeEntry.tenant_id == tenant_id)  # F-026
        .with_for_update()
        .first()
    )


def apply_credit_override(
    db: Session, entry: TimeEntry, *, changed_by_id, on_request: bool, change_request_id=None,
) -> bool:
    """Spec 13.3 Schritte 2–5. ``False`` = war schon anerkannt (idempotent,
    kein Protokoll). Wirft 400 (offen, ``auto_closed``) bzw. 409 (Kollision)."""
    if entry.end_time is None:
        raise HTTPException(status_code=400, detail=OPEN_ENTRY_DETAIL)
    if entry.auto_closed:
        raise HTTPException(status_code=400, detail=AUTO_CLOSED_DETAIL)
    if entry.credit_override:
        return False

    new_start = entry.raw_start_time or entry.start_time
    new_end = entry.raw_end_time or entry.end_time
    if new_start != entry.start_time:
        clash = db.query(TimeEntry.id).filter(
            TimeEntry.user_id == entry.user_id,
            TimeEntry.tenant_id == entry.tenant_id,  # F-026
            TimeEntry.date == entry.date,
            TimeEntry.start_time == new_start,
            TimeEntry.id != entry.id,
        ).first()
        if clash is not None:
            raise HTTPException(status_code=409, detail=start_taken_detail(new_start))

    old_start, old_end = entry.start_time, entry.end_time
    old_note = work_window_service.credit_summary_text(entry)
    entry.start_time, entry.end_time = new_start, new_end
    entry.raw_start_time = None
    entry.raw_end_time = None
    entry.uncredited_minutes = 0
    entry.credit_override = True
    # clamp_grace_minutes bleibt (13.3 Schritt 4) — ohne Wirkung, solange das Flag gilt.
    suffix = _ON_REQUEST if on_request else _BY_ADMIN
    db.add(TimeEntryAuditLog(
        time_entry_id=entry.id,
        user_id=entry.user_id,
        changed_by=changed_by_id,
        action="update",
        source=CREDIT_OVERRIDE_SOURCE,
        change_request_id=change_request_id,
        tenant_id=entry.tenant_id,
        old_date=entry.date,
        old_start_time=old_start,
        old_end_time=old_end,
        old_break_minutes=entry.break_minutes,
        old_note=old_note,
        new_date=entry.date,
        new_start_time=new_start,
        new_end_time=new_end,
        new_break_minutes=entry.break_minutes,
        new_note=f"{work_window_service.credit_summary_text(entry)} — {suffix}",
    ))
    db.flush()
    return True


def override_warnings(db: Session, user, entry: TimeEntry, *, include_weekly: bool = True) -> list:
    """Spec 13.3 Schritt 6 / P4: nach dem Anerkennen nur WEICHE Warnungen —
    §3 (Tag), §4, 48 h und die Anwesenheits-Warnungen. Nach dem Commit
    aufrufen. ``include_weekly=False`` für die CR-Genehmigung, deren
    Nachprüfung die 48-h-Warnung schon selbst ausgibt."""
    # Lokal: die Grenzwerte leben im Router-Modul; ein Modulimport hier zöge
    # den Router beim Laden des Dienstes mit.
    from app.routers.time_entries import (
        MAX_DAILY_HOURS_HARD, MAX_DAILY_HOURS_WARN, MAX_WEEKLY_HOURS_WARN,
    )
    from app.services.break_validation_service import validate_daily_break

    if user is None or getattr(user, "exempt_from_arbzg", False):
        return []
    out = []
    day_hours = presence_service.credited_minutes(
        presence_service.closed_entries(db, user, entry.date, entry.date)) / 60
    if day_hours > MAX_DAILY_HOURS_HARD:
        out.append(
            f"DAILY_HOURS_HARD: Tagesarbeitszeit beträgt {day_hours:.1f}h und überschreitet "
            f"die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG)."
        )
    elif day_hours > MAX_DAILY_HOURS_WARN:
        out.append("DAILY_HOURS_WARNING")
    break_error = validate_daily_break(
        db, user, entry.date, entry.start_time, entry.end_time, entry.break_minutes,
        uncredited_segments=[], tenant_id=entry.tenant_id, exclude_entry_id=entry.id,
    )
    if break_error:
        out.append(f"BREAK_WARNING: {break_error}")
    if include_weekly:
        monday = entry.date - timedelta(days=entry.date.weekday())
        week_hours = presence_service.credited_minutes(presence_service.closed_entries(
            db, user, monday, monday + timedelta(days=6))) / 60
        if week_hours > MAX_WEEKLY_HOURS_WARN:
            out.append("WEEKLY_HOURS_WARNING")
    out.extend(presence_service.presence_warnings(
        db, user, entry.date, break_check_passed=break_error is None, entry=entry,
    ))
    return out
```

- [ ] **Step 4: Endpunkt in `admin_time_entries.py`**

Importe oben ergänzen (falls PR1 `lock_user_row` schon importiert, nur `credit_override_service` ergänzen):

```python
from app.routers.admin_helpers import lock_user_row
from app.services import credit_override_service
```

Direkt nach `admin_update_time_entry` (vor `@router.delete("/time-entries/{entry_id}"…)`):

```python
@router.post("/time-entries/{entry_id}/credit-override", response_model=TimeEntryResponse)
def admin_credit_override(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Spec 2026-10-08, 13.3 „Anerkennen": die gesamte gestempelte Zeit des
    Eintrags wird angerechnet — dauerhaft, auch über spätere Neukappungen.
    §3/§4/48 h und Anwesenheit nur als weiche Warnung (P4)."""
    owner_id = db.query(TimeEntry.user_id).filter(
        TimeEntry.id == entry_id,
        TimeEntry.tenant_id == current_user.tenant_id,  # F-026
    ).scalar()
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")
    # P5: Anker VOR der Eintragszeile — dieselbe Reihenfolge wie jede Neukappung.
    lock_user_row(db, current_user.tenant_id, owner_id)
    entry = credit_override_service.load_entry_locked(db, current_user.tenant_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")
    owner = db.query(User).filter(
        User.id == owner_id, User.tenant_id == current_user.tenant_id,  # F-026
    ).first()
    changed = credit_override_service.apply_credit_override(
        db, entry, changed_by_id=current_user.id, on_request=False,
    )
    db.commit()
    db.refresh(entry)
    response = TimeEntryResponse.model_validate(entry)
    response.warnings = (
        credit_override_service.override_warnings(db, owner, entry) if changed else []
    )
    return response
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_credit_override.py tests/test_write_path_locks.py tests/test_audit_integrity.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/credit_override_service.py backend/app/routers/admin_time_entries.py backend/tests/test_credit_override.py backend/tests/test_write_path_locks.py
git commit -F - <<'EOF'
feat(bloecke): „Anerkennen" — credit_override_service und Admin-Endpunkt (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 6: „Anrechnung beantragen" und „genehmigen und anerkennen"

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#496 ändert `admin_helpers.py` — `_enrich_vr_responses`; hier wird nur `_enrich_cr_responses` erweitert, Importe am Dateikopf abgleichen. #499 ändert die Vorprüfung in `review_change_request`; PR1 Task 9 hat `change_requests.create_change_request` umgebaut (E40, P28) — die Anker unten sind die nach PR1.)

**Files:**
- Modify: `backend/app/schemas/change_request.py` (`ChangeRequestCreate`, `ChangeRequestReview`, `ChangeRequestResponse`)
- Modify: `backend/app/routers/change_requests.py` (Konstante, Importe, Prüfung, Konstruktor)
- Modify: `backend/app/routers/admin_change_requests.py` (Konstante, Importe, `review_change_request`)
- Modify: `backend/app/routers/admin_helpers.py` (`_enrich_cr_responses`)
- Test: `backend/tests/test_credit_override.py` (anhängen)

**Interfaces:**
- Consumes: `credit_override_service.apply_credit_override`, `override_warnings`, `AUTO_CLOSED_DETAIL` (Task 5); `presence_service.presence_warnings` (Task 3); `work_window_service.not_credited_minutes` (PR1)
- Produces:
  - `ChangeRequestCreate.request_credit_override: bool = False` (einzige neue MA-Eingabe, P21)
  - `ChangeRequestReview.grant_credit_override: Optional[bool] = None` — `None` = Wert des Antrags (auch in der Sammel-Genehmigung)
  - `ChangeRequestResponse.request_credit_override: bool = False`, `.original_uncredited_minutes: Optional[int] = None`, `.entry_credit_override: bool = False`, `.entry_not_credited_minutes: int = 0`, `.entry_auto_closed: bool = False` (aktueller Zustand des Zieleintrags, batch-geladen)
  - `routers.change_requests.CREDIT_REQUEST_REJECTED_DETAIL = "Für diesen Eintrag kann keine Anrechnung beantragt werden."`
  - `routers.admin_change_requests.GRANT_ONLY_UPDATE_DETAIL = "Anerkennen ist nur bei einem Änderungsantrag zu einem bestehenden Zeiteintrag möglich."`
  - Verhalten: MA-Antrag mit Flag nur als UPDATE auf eigenen, geschlossenen, nicht anerkannten Eintrag mit `not_credited_minutes > 0`; bei `auto_closed` muss `proposed_end_time` ∉ {gespeichertes Ende, `raw_end_time`, 23:59} sein (sonst 400 `AUTO_CLOSED_DETAIL`). Genehmigung mit wirksamem `grant` führt nach dem UPDATE-Zweig `apply_credit_override` aus; die Nachprüfung gibt Anwesenheits-Warnungen bzw. nach Anerkennen die Warnungen aus 13.3 Schritt 6 aus.

- [ ] **Step 1: Failing tests anhängen**

An `backend/tests/test_credit_override.py` anhängen:

```python
# ── „Anrechnung beantragen" (P21) und „genehmigen und anerkennen" ──────────────
import pytest  # noqa: E402

from app.models import ChangeRequest  # noqa: E402
from app.models.change_request import ChangeRequestStatus, ChangeRequestType  # noqa: E402
from app.routers.admin_change_requests import GRANT_ONLY_UPDATE_DETAIL  # noqa: E402
from app.routers.change_requests import CREDIT_REQUEST_REJECTED_DETAIL  # noqa: E402


def _request(client, entry, **kw):
    body = {
        "request_type": kw.pop("request_type", "update"),
        "time_entry_id": str(entry.id) if entry is not None else None,
        "proposed_date": MON.isoformat(),
        "proposed_start_time": kw.pop("start", "07:00"),
        "proposed_end_time": kw.pop("end", "19:00"),
        "proposed_break_minutes": 0,
        "reason": "Habe in der Lücke Patienten versorgt",
        "request_credit_override": True,
    }
    body.update(kw)
    return client.post("/api/change-requests/", json=body)


def test_employee_can_request_credit(_db_session, employee_user, employee_client):
    e = _k7(_db_session, employee_user)
    r = _request(employee_client, e)
    assert r.status_code == 201, r.text
    assert r.json()["request_credit_override"] is True
    cr = _db_session.query(ChangeRequest).one()
    assert (cr.request_credit_override, cr.original_uncredited_minutes) == (True, 150)


def test_request_rejected_without_not_credited_time(_db_session, employee_user, employee_client):
    e = _entry(_db_session, employee_user, time(8), time(16), break_minutes=30)
    r = _request(employee_client, e, start="08:00", end="16:00")
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)


def test_request_rejected_for_recognized_entry_create_and_absence(_db_session, employee_user,
                                                                   employee_client):
    e = _k7(_db_session, employee_user)
    e.credit_override = True
    _db_session.commit()
    assert _request(employee_client, e).json()["detail"] == CREDIT_REQUEST_REJECTED_DETAIL
    r = _request(employee_client, None, request_type="create", start="08:00", end="12:00")
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "entry_kind": "absence", "proposed_date": MON.isoformat(),
        "proposed_absence_type": "sick", "proposed_absence_hours": 8, "reason": "krank",
        "request_credit_override": True,
    })
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)


# Review Focus 3: 18:15 (gekapptes Ende) und 23:59 liefen über unclamp_input wieder auf 23:59.
@pytest.mark.parametrize("end, status", [("18:15", 400), ("23:59", 400), ("17:30", 201)])
def test_auto_closed_needs_the_actual_end(_db_session, employee_user, employee_client, end, status):
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18, 15), raw_end_time=time(23, 59),
               uncredited_minutes=150, auto_closed=True, clamp_grace_minutes=15)
    r = _request(employee_client, e, start="08:00", end=end)
    assert r.status_code == status, r.text
    if status == 400:
        assert r.json()["detail"] == cos.AUTO_CLOSED_DETAIL


def _cr(db, user, entry, **kw):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
        request_type=kw.pop("request_type", ChangeRequestType.UPDATE),
        status=ChangeRequestStatus.PENDING,
        time_entry_id=entry.id if entry is not None else None,
        proposed_date=MON, proposed_start_time=kw.pop("start", time(7)),
        proposed_end_time=kw.pop("end", time(19)), proposed_break_minutes=0,
        reason="Habe in der Lücke Patienten versorgt", **kw)
    db.add(cr)
    db.commit()
    return cr


def _review(client, cr, **body):
    return client.post(f"/api/admin/change-requests/{cr.id}/review",
                       json={"action": "approve", **body})


def test_approving_a_credit_request_recognizes_the_entry(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, request_credit_override=True,
             original_uncredited_minutes=150)
    r = _review(admin_client, cr)
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.credit_override, e.start_time, e.end_time, e.uncredited_minutes) == (
        True, time(7), time(19), 0)
    [log] = _override_logs(_db_session)
    assert log.new_note == (
        "angerechnet 12:00 h — auf Antrag der beschäftigten Person von der Verwaltung anerkannt")
    assert log.change_request_id == cr.id
    codes = _codes(r)
    assert "WORK_WINDOW_CLAMPED" not in codes   # jetzt ungekappt angerechnet
    assert "DAILY_HOURS_HARD" in codes          # P4: nur weich


def test_admin_can_decline_the_recognition(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, request_credit_override=True)
    assert _review(admin_client, cr, grant_credit_override=False).status_code == 200
    _db_session.refresh(e)
    assert e.credit_override is False
    assert _override_logs(_db_session) == []


def test_approve_and_recognize_an_ordinary_update(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e)
    assert _review(admin_client, cr, grant_credit_override=True).status_code == 200
    [log] = _override_logs(_db_session)
    assert log.new_note == "angerechnet 12:00 h — von der Verwaltung anerkannt"


def test_grant_only_for_updates_and_cr_stays_pending(_db_session, employee_user, admin_client):
    cr = _cr(_db_session, employee_user, None, request_type=ChangeRequestType.CREATE,
             start=time(8), end=time(12))
    r = _review(admin_client, cr, grant_credit_override=True)
    assert (r.status_code, r.json()["detail"]) == (400, GRANT_ONLY_UPDATE_DETAIL)
    _db_session.refresh(cr)
    assert cr.status == ChangeRequestStatus.PENDING


def test_bulk_approval_takes_the_request_value(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, request_credit_override=True)
    r = admin_client.post("/api/admin/change-requests/bulk-review",
                          json={"request_ids": [str(cr.id)], "action": "approve"})
    assert r.status_code == 200 and r.json()["succeeded"] == 1, r.text
    _db_session.refresh(e)
    assert e.credit_override is True


def test_response_carries_entry_state_and_snapshot(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, request_credit_override=True,
             original_uncredited_minutes=150)
    body = admin_client.get(f"/api/admin/change-requests/{cr.id}").json()
    assert body["request_credit_override"] is True
    assert body["original_uncredited_minutes"] == 150
    assert (body["entry_credit_override"], body["entry_not_credited_minutes"],
            body["entry_auto_closed"]) == (False, 240, False)


def test_approval_reports_presence_warnings(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(12))
    cr = _cr(_db_session, employee_user, e, start=time(8), end=time(18))
    r = _review(admin_client, cr)
    assert r.status_code == 200, r.text
    assert {"WORK_WINDOW_CLAMPED", "PRESENCE_BREAK"} <= set(_codes(r))
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_credit_override.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'GRANT_ONLY_UPDATE_DETAIL'`

- [ ] **Step 3: Schemas**

In `backend/app/schemas/change_request.py`:

`ChangeRequestCreate` — nach `proposed_sunday_exception_reason`:

```python
    # Spec 2026-10-08 P21: „Anrechnung beantragen" — Genehmigung = Anerkennen.
    request_credit_override: bool = False
```

`ChangeRequestReview` — nach `rejection_reason`:

```python
    # Spec 2026-10-08 P21 / 13.3: None = Wert des Antrags (request_credit_override);
    # True auch für „genehmigen und anerkennen" eines gewöhnlichen UPDATE-Antrags.
    grant_credit_override: Optional[bool] = None
```

`ChangeRequestResponse` — nach `original_absence_hours`:

```python
    # Spec 2026-10-08 P21/P28: Antragskennzeichen und Vorher-Snapshot der Lücke.
    request_credit_override: bool = False
    original_uncredited_minutes: Optional[int] = None
    # Spec P3/P21: AKTUELLER Zustand des Zieleintrags (batch-geladen in
    # admin_helpers._enrich_cr_responses) — Hinweis „Eintrag ist anerkannt …"
    # und die Option „genehmigen und anerkennen".
    entry_credit_override: bool = False
    entry_not_credited_minutes: int = 0
    entry_auto_closed: bool = False
```

- [ ] **Step 4: MA-Antrag (`change_requests.py`)**

Importe ergänzen (unter `from datetime import date`):

```python
from datetime import time
from app.services import credit_override_service, work_window_service
```

Konstante direkt unter `router = APIRouter(...)`:

```python
# Spec 2026-10-08, 11.4 / P21 (wörtlich).
CREDIT_REQUEST_REJECTED_DETAIL = "Für diesen Eintrag kann keine Anrechnung beantragt werden."
```

Direkt nach der Prüfung `if data.entry_kind not in ("time_entry", "absence"): …`:

```python
    # Spec 2026-10-08 P21: „Anrechnung beantragen" gibt es nur für Zeiteinträge.
    if data.request_credit_override and data.entry_kind != "time_entry":
        raise HTTPException(status_code=400, detail=CREDIT_REQUEST_REJECTED_DETAIL)
```

Direkt vor dem Kommentar `# Time range validation for CREATE and UPDATE`:

```python
    # Spec 2026-10-08 P21: nur als Änderung (UPDATE) an einem eigenen,
    # geschlossenen, noch nicht anerkannten Eintrag mit nicht angerechneter Zeit.
    # Ein automatisch geschlossener Eintrag braucht das TATSÄCHLICHE Ende (P18):
    # 23:59 ist kein Stempel, und das gekappte Ende liefe bei der Genehmigung
    # über unclamp_input wieder auf 23:59 hinaus.
    if data.request_credit_override:
        if (
            data.request_type != "update"
            or entry is None
            or entry.end_time is None
            or entry.credit_override
            or work_window_service.not_credited_minutes(entry) <= 0
        ):
            raise HTTPException(status_code=400, detail=CREDIT_REQUEST_REJECTED_DETAIL)
        if entry.auto_closed and data.proposed_end_time in (
            entry.end_time, entry.raw_end_time, time(23, 59),
        ):
            raise HTTPException(status_code=400, detail=credit_override_service.AUTO_CLOSED_DETAIL)
```

Im Konstruktor `cr = ChangeRequest(...)` (Zeiteintrags-Zweig) nach `proposed_sunday_exception_reason=(...)`:

```python
        request_credit_override=bool(data.request_credit_override),  # P21
```

(Ein lokales `from app.services import work_window_service` aus PR1 im E40-Block bleibt unschädlich stehen.)

- [ ] **Step 5: Genehmigung (`admin_change_requests.py`)**

Importe ergänzen:

```python
from app.services import credit_override_service, presence_service
```

Konstante unter `router = APIRouter(...)`:

```python
# Spec 2026-10-08 P21 / 13.3: „Genehmigen = Anerkennen" nur an Zeiteinträgen.
GRANT_ONLY_UPDATE_DETAIL = (
    "Anerkennen ist nur bei einem Änderungsantrag zu einem bestehenden Zeiteintrag möglich."
)
```

In `review_change_request` direkt vor dem Kommentar `# Approve: validate preconditions BEFORE changing status` (nach den beiden 4-Augen-Prüfungen):

```python
    # Spec 2026-10-08 P21 / 13.3: „Genehmigen = Anerkennen". Ohne Angabe gilt der
    # Wert des Antrags — auch in der Sammel-Genehmigung (ChangeRequestReview ohne
    # grant_credit_override). Precondition VOR der Statusänderung.
    grant_override = (
        review.grant_credit_override
        if review.grant_credit_override is not None
        else bool(cr.request_credit_override)
    )
    if grant_override and (
        cr.entry_kind == "absence" or cr.request_type != ChangeRequestType.UPDATE
    ):
        raise HTTPException(status_code=400, detail=GRANT_ONLY_UPDATE_DETAIL)
```

Im UPDATE-Zweig der Zeiteinträge, direkt nach dem Block `# #485 §10 ArbZG: ein mitgebrachter Ausnahmegrund ersetzt den alten …` (also nachdem `entry.date/start_time/end_time/raw_*` und PR1s `uncredited_minutes`/`clamp_grace_minutes`/`auto_closed` gesetzt sind):

```python
            # Spec 13.3 Schritte 2–6 im Genehmigungspfad (P21) — die Ankersperre
            # hält dieser Pfad schon (Anker vor Antrag vor Eintrag).
            if grant_override:
                credit_override_service.apply_credit_override(
                    db, entry,
                    changed_by_id=current_user.id,
                    on_request=bool(cr.request_credit_override),
                    change_request_id=cr.id,
                )
                # Die Kappungswarnung dieser Genehmigung gilt nicht mehr.
                _clamp_warn = None
```

In der Nachprüfung (Block `if cr_user and not cr_user.exempt_from_arbzg:` unter „§6 Abs. 2 / §3 ArbZG: Warnungen bei CREATE/UPDATE-Genehmigung"), am Ende des Blocks direkt nach der 48-h-Warnung:

```python
            # Spec 8.3/8.4: weiche Anwesenheits-Warnungen und Pausen-Doppelabzug —
            # nach „Anerkennen" stattdessen die weichen Warnungen aus 13.3 Schritt 6
            # (P4; die 48-h-Warnung steht schon oben). `entry` ist der eben
            # geschriebene Eintrag (CREATE- bzw. UPDATE-Zweig).
            if entry is not None:
                if grant_override:
                    cr_response.warnings.extend(credit_override_service.override_warnings(
                        db, cr_user, entry, include_weekly=False,
                    ))
                else:
                    cr_response.warnings.extend(presence_service.presence_warnings(
                        db, cr_user, cr.proposed_date,
                        break_check_passed=waiver_reason is None, entry=entry,
                    ))
```

- [ ] **Step 6: Antwort anreichern (`admin_helpers.py`)**

Importe ergänzen:

```python
from app.models import TimeEntry
from app.services import work_window_service
```

In `_enrich_cr_responses` direkt nach `user_map = {u.id: u for u in users}`:

```python
    # Spec 2026-10-08 P3/P21: aktueller Zustand der Zieleinträge — EIN Query, F-026.
    entry_ids = {cr.time_entry_id for cr in crs if cr.time_entry_id}
    entries = {
        e.id: e for e in db.query(TimeEntry).filter(
            TimeEntry.id.in_(entry_ids), TimeEntry.tenant_id.in_(tenant_ids),
        ).all()
    } if entry_ids else {}
```

In der Schleife direkt nach `response = ChangeRequestResponse.model_validate(cr)`:

```python
        target = entries.get(cr.time_entry_id)
        if target is not None:
            response.entry_credit_override = bool(target.credit_override)
            response.entry_auto_closed = bool(target.auto_closed)
            response.entry_not_credited_minutes = work_window_service.not_credited_minutes(target)
```

- [ ] **Step 7: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS (keine neuen Fehlschläge)

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/change_request.py backend/app/routers/change_requests.py backend/app/routers/admin_change_requests.py backend/app/routers/admin_helpers.py backend/tests/test_credit_override.py
git commit -F - <<'EOF'
feat(bloecke): „Anrechnung beantragen" und „genehmigen und anerkennen" (P21, PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 7: Monatsjournal — Felder je Eintrag und Monatssumme

**Files:**
- Modify: `backend/app/services/journal_service.py` (Import; Initialisierung vor `days = []`; Tagesschleife; Eintrags-Dict; `monthly_summary`)
- Modify: `backend/app/schemas/journal.py` (`JournalTimeEntry`, `JournalMonthlySummary`)
- Test (neu): `backend/tests/test_journal_uncredited.py`

**Interfaces:**
- Consumes: `work_window_service.not_credited_minutes(entry)` (PR1)
- Produces:
  - `JournalTimeEntry.uncredited_minutes: int = 0`, `.not_credited_minutes: int = 0`, `.credit_override: bool = False`, `.auto_closed: bool = False`
  - `JournalMonthlySummary.not_credited_minutes_total: int = 0` — Σ `not_credited_minutes` aller Einträge des Monats (Lücke **und** Hülle, P19)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_journal_uncredited.py`:

```python
"""Spec 2026-10-08, 13.2 (PR2): das Monatsjournal führt je Eintrag die nicht
angerechnete Zeit und im Summary die Monatssumme (Lücke + Hülle, P19)."""
from datetime import time, timedelta

from app.models import TimeEntry
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON

TUE = MON + timedelta(days=1)


def _seed(db, user):
    # K7: Lücke 150 + Hülle 90 = 240
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                     start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                     raw_end_time=time(19), break_minutes=0, uncredited_minutes=150,
                     clamp_grace_minutes=15))
    # K15: automatisch geschlossen — die Endseite 23:59 zählt nicht (P18)
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=TUE,
                     start_time=time(8), end_time=time(18, 15), raw_end_time=time(23, 59),
                     break_minutes=0, uncredited_minutes=150, auto_closed=True))
    db.commit()


def _day(body, d):
    return next(x for x in body["days"] if x["date"] == d.isoformat())


def _check(body):
    k7 = _day(body, MON)["time_entries"][0]
    assert (k7["uncredited_minutes"], k7["not_credited_minutes"],
            k7["credit_override"], k7["auto_closed"]) == (150, 240, False, False)
    k15 = _day(body, TUE)["time_entries"][0]
    assert (k15["not_credited_minutes"], k15["auto_closed"]) == (150, True)
    assert body["monthly_summary"]["not_credited_minutes_total"] == 390


def test_own_journal(_db_session, employee_user, employee_client):
    _seed(_db_session, employee_user)
    r = employee_client.get("/api/journal/me?year=2026&month=6")
    assert r.status_code == 200, r.text
    _check(r.json())


def test_admin_journal(_db_session, employee_user, admin_client):
    _seed(_db_session, employee_user)
    r = admin_client.get(f"/api/admin/users/{employee_user.id}/journal?year=2026&month=6")
    assert r.status_code == 200, r.text
    _check(r.json())


def test_month_without_clamping_reports_zero(_db_session, employee_user, employee_client):
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=time(16, 30), break_minutes=30))
    _db_session.commit()
    body = employee_client.get("/api/journal/me?year=2026&month=6").json()
    assert body["monthly_summary"]["not_credited_minutes_total"] == 0
    assert _day(body, MON)["time_entries"][0]["not_credited_minutes"] == 0
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_journal_uncredited.py -q -p no:cacheprovider`
Expected: FAIL — `KeyError: 'uncredited_minutes'` (das `response_model` filtert unbekannte Felder still weg, CLAUDE.md #485)

- [ ] **Step 3: Schema**

In `backend/app/schemas/journal.py`, `JournalTimeEntry` nach `sunday_exception_reason`:

```python
    # Spec 2026-10-08 (13.2, P18, P19): ohne diese Felder filterte das
    # response_model sie still weg (CLAUDE.md #485).
    uncredited_minutes: int = 0
    not_credited_minutes: int = 0
    credit_override: bool = False
    auto_closed: bool = False
```

`JournalMonthlySummary` nach `balance: float`:

```python
    # Spec 13.2: Σ not_credited_minutes (Lücke + Hülle) — Zeile
    # „Anwesenheit nicht angerechnet" im Journal.
    not_credited_minutes_total: int = 0
```

- [ ] **Step 4: `journal_service.py`**

Import ersetzen:

```python
from app.services import calculation_service, special_days_service, work_window_service
```

Direkt vor `days = []`:

```python
    # Spec 13.2 (P19): Monatssumme der nicht angerechneten Anwesenheit.
    not_credited_total = 0
```

In der Tagesschleife direkt nach `time_hours = Decimal(str(sum(e.net_hours for e in day_entries)))`:

```python
        not_credited_total += sum(work_window_service.not_credited_minutes(e) for e in day_entries)
```

Im Eintrags-Dict (Liste `"time_entries": [...]`) nach `"sunday_exception_reason": e.sunday_exception_reason,`:

```python
                    "uncredited_minutes": int(e.uncredited_minutes or 0),
                    "not_credited_minutes": work_window_service.not_credited_minutes(e),
                    "credit_override": bool(e.credit_override),
                    "auto_closed": bool(e.auto_closed),
```

In `"monthly_summary": {...}` nach `"balance": …`:

```python
            "not_credited_minutes_total": not_credited_total,
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_journal_uncredited.py tests/test_journal_service.py tests/test_audit_20260731_journal_zeit.py tests/test_fix6_journal_health_audit.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/journal_service.py backend/app/schemas/journal.py backend/tests/test_journal_uncredited.py
git commit -F - <<'EOF'
feat(bloecke): Monatsjournal mit nicht angerechneter Zeit je Eintrag und Monatssumme (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 8: Export-Spalte „Nicht angerechnet (Min)" in XLSX, ODS und PDF

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#497/#498 haben die Tagesschleifen aller Exporter umgebaut — Spalten 11/12 „Unterbrechung (Min)"/„Arbeitsblöcke" in XLSX/ODS, PDF-Spalte 6 „Unterbr. (Min)", `day_work_blocks`. Anker unten sind die Stellen, an denen `day_work_blocks(day_entries)` aufgerufen wird, und die Zeilen `night_work_count = 0`.)

**Planentscheidung zum offenen Punkt aus Spec 15.1 (vom Betreiber vor dem Merge zu bestätigen):** Die Datei bekommt **keine** zusätzliche Spalte für den Lückenanteil — „Nicht angerechnet (Min)" bleibt die letzte Spalte (Spec 15.1/17.6). Der Lückenanteil je Tag wird an **einer** Stelle gerechnet (`export_service.day_credit_minutes`, Feld `gap_uncredited`), die Zeilenregel lautet dort im Docstring `Bis − Von − Pause − Unterbrechung − gap_uncredited = Netto`; das Handbuch (PR4) schränkt die Regel auf „ohne an der Hülle gekappte Anwesenheit" ein. Die #498-Spalte „Arbeitsblöcke" behält in PR2 ihren Namen (Köpfe 1–12 unverändert, 17.6); die Umbenennung entscheidet der Betreiber vor dem Release (PR4).

**Files:**
- Modify: `backend/app/services/export_service.py` (Importe; Konstanten + `DayCredit` + `day_credit_minutes` nach `day_work_blocks`; `_create_employee_sheet`; `_create_employee_yearly_sheet`; `generate_monthly_report_pdf`)
- Modify: `backend/app/services/ods_export_service.py` (Import; `_monthly_sheet`; `_yearly_employee_sheet`)
- Test (neu): `backend/tests/test_export_uncredited_column.py`

**Interfaces:**
- Consumes: `work_window_service.not_credited_minutes` (PR1); Lese-Helfer aus `tests/test_497_498_export_day_rows.py` (`XLSX_HEADERS_1_TO_10`, `YEAR`, `MONTH`, `_as_date`, `_minutes`, `_xlsx_employee_sheet`, `_ods_table`, `_ods_rows`, `_ods_day_rows`, `_ods_header`, `_pdf_main_table`)
- Produces (in `app.services.export_service`):
  - `NOT_CREDITED_HEADER = "Nicht angerechnet (Min)"`, `PDF_NOT_CREDITED_HEADER = "Nicht angerechnet\n(Min)"`
  - `class DayCredit(NamedTuple): not_credited: Optional[int]; gap_uncredited: int`
  - `day_credit_minutes(day_entries) -> DayCredit` — `not_credited` = Σ `not_credited_minutes` (None ohne Eintrag), `gap_uncredited` = Σ `uncredited_minutes`
  - Summenzeilen „Nicht angerechnet (Min) Monat:" (XLSX/ODS-Monat), „Nicht angerechnet (Min) Jahr:" (XLSX-Jahres-Mitarbeiterblatt), „Nicht angerechnet (Min):" (PDF)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_export_uncredited_column.py`:

```python
"""Spec 2026-10-08, 15.1 / 17.6 (PR2): Spalte „Nicht angerechnet (Min)" —
angehängt (XLSX/ODS Spalte 13, PDF Spalte 12), Wert je Tag = Σ
not_credited_minutes (Lücke + Hülle, P19), Summenzeile = Σ Zeitraum."""
from datetime import date, time

import pytest

from app.models import TimeEntry
from app.services import export_service, ods_export_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_497_498_export_day_rows import (
    MONTH, XLSX_HEADERS_1_TO_10, YEAR, _as_date, _minutes, _ods_day_rows, _ods_header,
    _ods_rows, _ods_table, _pdf_main_table, _xlsx_employee_sheet,
)

K7_DAY = date(2026, 9, 7)       # Mo
PLAIN_DAY = date(2026, 9, 8)    # Di — ohne Kappung
EMPTY_DAY = date(2026, 9, 9)    # Mi — nichts erfasst
K15_DAY = date(2026, 9, 14)     # Mo — automatisch geschlossen
HEADER = "Nicht angerechnet (Min)"


@pytest.fixture
def month(db, test_user):
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=K7_DAY,
                     start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                     raw_end_time=time(19), break_minutes=0, uncredited_minutes=150,
                     clamp_grace_minutes=15))
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=PLAIN_DAY,
                     start_time=time(8), end_time=time(16, 30), break_minutes=30))
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=K15_DAY,
                     start_time=time(8), end_time=time(18, 15), raw_end_time=time(23, 59),
                     break_minutes=0, uncredited_minutes=150, auto_closed=True))
    db.commit()
    return test_user


def _xlsx_rows(sheet):
    rows = {}
    for r in sheet.iter_rows(min_col=1, max_col=13, values_only=True):
        d = _as_date(r[0])
        if isinstance(d, date):
            rows[d] = list(r)
    return rows


def _label_value(sheet, label):
    for r in sheet.iter_rows(min_col=1, max_col=2, values_only=True):
        if r[0] == label:
            return r[1]
    raise AssertionError(f"Zeile {label!r} fehlt")


@pytest.mark.parametrize("yearly", [False, True])
def test_xlsx_column_13_values_and_sum(db, month, yearly):
    if yearly:
        bio = export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID)
        header_row, label = 3, "Nicht angerechnet (Min) Jahr:"
    else:
        bio = export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
        header_row, label = 4, "Nicht angerechnet (Min) Monat:"
    sheet = _xlsx_employee_sheet(bio, month, yearly=yearly)
    headers = [sheet.cell(row=header_row, column=c).value for c in range(1, 14)]
    assert headers[:10] == XLSX_HEADERS_1_TO_10, "Spalten 1–10 bleiben, wo sie sind"
    assert headers[10:] == ["Unterbrechung (Min)", "Arbeitsblöcke", HEADER]
    rows = _xlsx_rows(sheet)
    assert rows[K7_DAY][12] == 240      # K7: Lücke 150 + Hülle 90
    assert rows[K15_DAY][12] == 150     # K15: Endseite 23:59 zählt nicht (P18)
    assert rows[PLAIN_DAY][12] == 0
    assert rows[EMPTY_DAY][12] is None
    assert _label_value(sheet, label) == 390


def test_xlsx_row_rule_subtracts_the_gap_share_only(db, month):
    """15.1: Bis − Von − Pause − Unterbrechung − Σ uncredited = Netto. Mit der
    Spalte 13 (240, enthält die Hülle) ginge die Zeile NICHT auf."""
    sheet = _xlsx_employee_sheet(export_service.generate_monthly_report(
        db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID), month)
    r = _xlsx_rows(sheet)[K7_DAY]
    von, bis, pause, netto, gap = r[2], r[3], r[4], r[5], r[10]
    assert (_minutes(bis) - _minutes(von) - pause - gap - 150) / 60 == pytest.approx(netto, abs=0.01)
    assert (_minutes(bis) - _minutes(von) - pause - gap - r[12]) / 60 != pytest.approx(netto, abs=0.01)


@pytest.mark.parametrize("yearly", [False, True])
def test_ods_column_13(db, month, yearly):
    if yearly:
        bio = ods_export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID)
    else:
        bio = ods_export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    table = _ods_table(bio, f"{month.last_name} {month.first_name}"[:31])
    header = _ods_header(table)
    assert header[:10] == XLSX_HEADERS_1_TO_10
    assert header[10:13] == ["Unterbrechung (Min)", "Arbeitsblöcke", HEADER]
    rows = _ods_day_rows(table)
    assert rows[K7_DAY][12][1] == "240"
    assert rows[K15_DAY][12][1] == "150"
    assert rows[PLAIN_DAY][12][1] == "0"


def test_ods_monthly_sum_row(db, month):
    table = _ods_table(ods_export_service.generate_monthly_report(
        db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID), f"{month.last_name} {month.first_name}"[:31])
    row = next(r for r in _ods_rows(table) if r and r[0][0] == "Nicht angerechnet (Min) Monat:")
    assert row[1][1] == "390"


def test_pdf_last_column(db, month, monkeypatch):
    header, rows = _pdf_main_table(db, monkeypatch)
    assert len(header) == 12
    assert header[-1] == "Nicht angerechnet (Min)"
    assert header.index("Unterbr. (Min)") == 5, "Spalte 6 bleibt die Unterbrechung"
    assert rows[K7_DAY][-1] == "240"
    assert rows[K15_DAY][-1] == "150"
    assert rows[EMPTY_DAY][-1] == ""


def test_day_credit_minutes_helper():
    k7 = TimeEntry(start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                   raw_end_time=time(19), break_minutes=0, uncredited_minutes=150)
    plain = TimeEntry(start_time=time(8), end_time=time(12), break_minutes=0, uncredited_minutes=0)
    assert export_service.day_credit_minutes([k7, plain]) == export_service.DayCredit(240, 150)
    assert export_service.day_credit_minutes([]) == export_service.DayCredit(None, 0)
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_export_uncredited_column.py -q -p no:cacheprovider`
Expected: FAIL — Kopf 13 ist `None`; `AttributeError: … has no attribute 'day_credit_minutes'`

- [ ] **Step 3: Helfer in `export_service.py`**

Importe ersetzen: `from typing import List` → `from typing import List, NamedTuple, Optional` und `from app.services import calculation_service, practice_name_service, special_days_service` → `from app.services import calculation_service, practice_name_service, special_days_service, work_window_service`.

Im Docstring von `day_work_blocks` den Satz „Kommt eine weitere Abzugsgroesse innerhalb von Von/Bis hinzu (z. B. nicht angerechnete Luecke eines Eintrags), gehoert sie hierher, damit die Zeilenregel an EINER Stelle gerechnet wird." ersetzen durch „Die nicht angerechnete Luecke eines Eintrags (Arbeitszeit-Bloecke) rechnet ``day_credit_minutes`` — die vollstaendige Zeilenregel steht dort."

Direkt nach `day_work_blocks`:

```python
# Spec 2026-10-08, 15.1: angehängte Spalte (XLSX/ODS 13, PDF 12) — Name bleibt.
NOT_CREDITED_HEADER = "Nicht angerechnet (Min)"
PDF_NOT_CREDITED_HEADER = "Nicht angerechnet\n(Min)"


class DayCredit(NamedTuple):
    not_credited: Optional[int]   # Σ not_credited_minutes (Lücke + Hülle, P19); None ohne Eintrag
    gap_uncredited: int           # Σ uncredited_minutes (nur die Lücke zwischen den Blöcken)


def day_credit_minutes(day_entries) -> DayCredit:
    """Spec 15.1: nicht angerechnete Anwesenheit eines Tages.

    ``not_credited`` speist die Spalte „Nicht angerechnet (Min)" — Lücke UND
    von der Hülle gekappte Anwesenheit, ohne die synthetische Auto-Close-Endseite
    (``work_window_service.not_credited_minutes``, DIE eine Quelle).

    Zeilenregel der Tageszeile (#498 + E13):
    ``Bis − Von − Pause − Unterbrechung − gap_uncredited = Netto``.
    NICHT „− Nicht angerechnet": die Spalte enthält zusätzlich die Hüllenminuten,
    und die liegen AUSSERHALB der (gekappten) Von/Bis, die die Datei zeigt
    (K7: 240 in der Spalte, 150 in der Zeilenregel)."""
    if not day_entries:
        return DayCredit(None, 0)
    return DayCredit(
        sum(work_window_service.not_credited_minutes(e) for e in day_entries),
        sum(int(e.uncredited_minutes or 0) for e in day_entries),
    )
```

- [ ] **Step 4: XLSX-Monatsblatt (`_create_employee_sheet`)**

Docstring-Spaltenliste um `- Nicht angerechnet (Min) (Spec 2026-10-08, angehängt)` ergänzen. Kopfzeile:

```python
    headers = ["Datum", "Wochentag", "Von", "Bis", "Pause (Min)", "Netto (Std)", "Soll (Std)", "Differenz", "Abwesenheit", "Bemerkung",
               "Unterbrechung (Min)", "Arbeitsblöcke", NOT_CREDITED_HEADER]
```

Nach `night_work_count = 0`:

```python
    month_not_credited = 0  # Spec 15.1: Summenzeile
```

Im Zweig `if day_entries:` direkt nach den Zeilen für Spalte 11/12 (`if _blocks: sheet.cell(row=row, column=12).value = _blocks`):

```python
            # Spec 15.1: Spalte 13 — Lücke + Hülle (P19), angehängt.
            _credit = day_credit_minutes(day_entries)
            sheet.cell(row=row, column=13).value = _credit.not_credited
            month_not_credited += _credit.not_credited
```

Beide Füllschleifen `for col in range(1, 13):` (Wochenende, Feiertag) → `for col in range(1, 14):`.

Nach der Summenzeile „Nachtarbeitstage (§6 ArbZG):" (vor „# Adjust column widths"):

```python
    row += 1
    sheet.cell(row=row, column=1).value = "Nicht angerechnet (Min) Monat:"
    sheet.cell(row=row, column=2).value = month_not_credited
    sheet.cell(row=row, column=1).font = Font(bold=True)
```

Nach `sheet.column_dimensions['L'].width = 26`:

```python
    sheet.column_dimensions['M'].width = 16
```

- [ ] **Step 5: XLSX-Jahres-Mitarbeiterblatt (`_create_employee_yearly_sheet`)**

Dieselben Änderungen: Kopfzeile mit `NOT_CREDITED_HEADER` am Ende; nach `night_work_count = 0` die Zeile `year_not_credited = 0  # Spec 15.1: Summenzeile`; nach dem Spalte-11/12-Block

```python
            # Spec 15.1: Spalte 13 — Lücke + Hülle (P19), angehängt.
            _credit = day_credit_minutes(day_entries)
            sheet.cell(row=row, column=13).value = _credit.not_credited
            year_not_credited += _credit.not_credited
```

beide Füllschleifen auf `range(1, 14)`; nach „Nachtarbeitstage (§6 ArbZG):"

```python
    row += 1
    sheet.cell(row=row, column=1).value = "Nicht angerechnet (Min) Jahr:"
    sheet.cell(row=row, column=2).value = year_not_credited
    sheet.cell(row=row, column=1).font = Font(bold=True)
```

und `sheet.column_dimensions['M'].width = 16`.

- [ ] **Step 6: PDF (`generate_monthly_report_pdf`)**

Spaltenbreiten (Σ 267 mm):

```python
    # Spec 2026-10-08, 15.1: „Nicht angerechnet (Min)" als 12. und letzte Spalte
    # (18 mm, je 9 mm aus Abwesenheit/Bemerkung) — Spalte 6 bleibt die Unterbrechung.
    col_widths = [22*mm, 10*mm, 13*mm, 13*mm, 15*mm, 15*mm, 16*mm, 14*mm, 16*mm, 58*mm, 57*mm, 18*mm]
```

Kopfzeile:

```python
        headers = ['Datum', 'WT', 'Von', 'Bis', 'Pause\n(Min)', 'Unterbr.\n(Min)', 'Netto\n(Std)', 'Soll\n(Std)', 'Diff.', 'Abwesenheit', 'Bemerkung', PDF_NOT_CREDITED_HEADER]
```

Nach `night_work_count = 0` (innerhalb der Personenschleife):

```python
        month_not_credited = 0  # Spec 15.1: Summenzeile
```

Im Zweig `if day_entries:` direkt nach `gap_str = str(_gap)`:

```python
                _credit = day_credit_minutes(day_entries)
                nc_str = str(_credit.not_credited)
                month_not_credited += _credit.not_credited
```

Im `else`-Zweig die Zeile `von = bis = pause_str = gap_str = bem = ''` ersetzen durch:

```python
                von = bis = pause_str = gap_str = bem = nc_str = ''
```

In der Zeilenliste `row = [...]` als letztes Element nach `Paragraph(escape_pdf_text(bem), s_normal),`:

```python
                Paragraph(nc_str, s_center),
```

In `summary_rows` als letzte Zeile nach „Nachtarbeitstage (§6 ArbZG):":

```python
            [Paragraph('Nicht angerechnet (Min):', s_sum_lbl),
             Paragraph(str(month_not_credited), s_sum_val)],
```

- [ ] **Step 7: ODS (`ods_export_service.py`)**

Import-Block aus `export_service` ergänzen:

```python
    day_work_blocks,  # #498
    day_credit_minutes, NOT_CREDITED_HEADER,  # Spec 2026-10-08, 15.1
```

`_monthly_sheet` und `_yearly_employee_sheet` — Kopfzeilen:

```python
        # #498: angehängt, nie eingeschoben (Parität zu XLSX).
        "Unterbrechung (Min)", "Arbeitsblöcke",
        NOT_CREDITED_HEADER,  # Spec 2026-10-08, 15.1: Spalte 13
```

`_monthly_sheet` — nach `night_work_count = 0`: `month_not_credited = 0`; am Zeilenende direkt nach `tr.addElement(_str_cell(_blocks))`:

```python
        # Spec 15.1: Spalte 13 — Lücke + Hülle (P19).
        _credit = day_credit_minutes(day_entries)
        tr.addElement(_int_cell(_credit.not_credited) if _credit.not_credited is not None else _empty_cell())
        month_not_credited += _credit.not_credited or 0
```

Summenzeilen nach `summary_int_row("Nachtarbeitstage (§6 ArbZG):", night_work_count)`:

```python
    table.addElement(summary_int_row("Nicht angerechnet (Min) Monat:", month_not_credited))
```

`_yearly_employee_sheet` — am Zeilenende direkt nach `tr.addElement(_str_cell(_blocks))`:

```python
        # Spec 15.1: Spalte 13 (s. Monatsblatt).
        _credit = day_credit_minutes(day_entries)
        tr.addElement(_int_cell(_credit.not_credited) if _credit.not_credited is not None else _empty_cell())
```

- [ ] **Step 8: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_export_uncredited_column.py tests/test_497_498_export_day_rows.py tests/test_export_service.py tests/test_ods_export_service.py tests/test_export_endpoints.py tests/test_audit_20260731_export_ist.py tests/test_export_employment_window.py tests/test_release_review_116_exports.py -q -p no:cacheprovider`
Expected: PASS — insbesondere `TestIssue497*` (Σ „Differenz" = „Saldo Monat") und `TestIssue498*` (Köpfe 1–12) unverändert grün

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/export_service.py backend/app/services/ods_export_service.py backend/tests/test_export_uncredited_column.py
git commit -F - <<'EOF'
feat(bloecke): Export-Spalte „Nicht angerechnet (Min)" in XLSX, ODS und PDF (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 9: 24-Wochen-Auswertung mit „Anwesenheit laut Stempel"

**Files:**
- Modify: `backend/app/routers/reports.py` (Import; `get_24_week_averaging_period`)
- Modify: `frontend/src/pages/admin/Reports.tsx` (Import, Typen, State, Abschnitt vor „Additional Info")
- Test (neu): `backend/tests/test_24_week_presence.py`, `frontend/src/pages/admin/Reports.test.tsx`

**Interfaces:**
- Consumes: `work_window_service.presence_minutes(entry)` (PR1)
- Produces:
  - `GET /api/admin/reports/24-week-average`: je Person zusätzlich `presence_hours: float` (Σ Anwesenheit laut Stempel im 24-Wochen-Fenster), `presence_average: float` (je eingeplantem Arbeitstag, derselbe Nenner wie `average_daily_hours`) und `presence_weeks: List[{"iso_week": str, "presence_hours": float}]` (Spec 8.1/11.1 „je Woche": Σ `presence_minutes` je ISO-Kalenderwoche Mo–So, Schlüssel `"YYYY-Www"`, nur Wochen mit mindestens einem geschlossenen Eintrag, aufsteigend; Randwochen des Fensters nur mit ihren Tagen im Fenster). Damit bleibt eine Woche mit mehr als 48 h laut Stempel im Bericht erkennbar, auch wenn die angerechnete Zeit darunter liegt (P22, Pflicht 4).
  - Admin-Berichte: Abschnitt „24-Wochen-Durchschnitt §3 ArbZG" (`aria-label`-Button „24-Wochen-Durchschnitt prüfen", Tabelle `aria-label="24-Wochen-Durchschnitt"`) mit Spalten „Anwesenheit laut Stempel (Ø / Tag)" und „Wochen > 48 h laut Stempel" (Anzahl und die Wochen mit ihrem Wert, sonst „–")

- [ ] **Step 1: Failing Backend-Tests schreiben**

`backend/tests/test_24_week_presence.py`:

```python
"""Spec 2026-10-08, 8.1 / P22 (PR2): die 24-Wochen-Auswertung führt neben der
angerechneten Zeit die Anwesenheit laut Stempel — die keine Neuberechnung senkt."""
import uuid
from datetime import time, timedelta

from app.models import TimeEntry
from app.models.tenant import Tenant
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON

URL = "/api/admin/reports/24-week-average?end_date=2026-06-05"


def _row(client, user):
    r = client.get(URL)
    assert r.status_code == 200, r.text
    return next(e for e in r.json()["employees"] if e["user_id"] == str(user.id))


def _add(db, user, d, start, end, **kw):
    e = TimeEntry(tenant_id=kw.pop("tenant_id", DEFAULT_TENANT_ID), user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def test_presence_next_to_credited_time(_db_session, employee_user, admin_client):
    _add(_db_session, employee_user, MON, time(8), time(18), uncredited_minutes=150)          # K1
    _add(_db_session, employee_user, MON + timedelta(days=1), time(7, 45), time(18, 15),
         raw_start_time=time(7), raw_end_time=time(19), uncredited_minutes=150)               # K7
    row = _row(admin_client, employee_user)
    assert row["total_hours"] == 15.5
    assert row["presence_hours"] == 22.0
    assert row["presence_average"] == round(22.0 / row["scheduled_work_days"], 2)


def test_retroactive_shortening_lowers_credited_not_presence(_db_session, employee_user, admin_client):
    e = _add(_db_session, employee_user, MON, time(8), time(18))
    before = _row(admin_client, employee_user)
    e.uncredited_minutes = 150   # wie eine spätere Neukappung (PR3)
    _db_session.commit()
    after = _row(admin_client, employee_user)
    assert after["total_hours"] == before["total_hours"] - 2.5
    assert after["presence_hours"] == before["presence_hours"] == 10.0


def test_weekly_presence_shows_a_week_over_48_hours(_db_session, employee_user, admin_client):
    """Spec 8.1/11.1 „je Woche" (P22, Pflicht 4): eine Woche mit 50 h laut Stempel
    bleibt im Bericht erkennbar, obwohl nur 37,5 h angerechnet sind (5 × K1)."""
    for i in range(5):
        _add(_db_session, employee_user, MON + timedelta(days=i), time(8), time(18), uncredited_minutes=150)
    row = _row(admin_client, employee_user)
    assert row["total_hours"] == 37.5
    assert row["presence_hours"] == 50.0
    assert row["presence_weeks"] == [{"iso_week": "2026-W23", "presence_hours": 50.0}]


def test_other_tenant_entries_do_not_count(_db_session, employee_user, admin_client):
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    _db_session.add(other)
    _db_session.commit()
    _add(_db_session, employee_user, MON, time(8), time(18), uncredited_minutes=150)
    _add(_db_session, employee_user, MON, time(19), time(21), tenant_id=other.id)
    row = _row(admin_client, employee_user)
    assert (row["total_hours"], row["presence_hours"]) == (7.5, 10.0)
```

- [ ] **Step 2: Backend-Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_24_week_presence.py -q -p no:cacheprovider`
Expected: FAIL — `KeyError: 'presence_hours'` bzw. `KeyError: 'presence_weeks'`; `test_other_tenant_entries_do_not_count` zusätzlich mit `total_hours == 9.5` (fehlender F-026-Filter)

- [ ] **Step 3: Endpunkt erweitern**

In `backend/app/routers/reports.py` den Import ersetzen:

```python
from app.services import calculation_service, export_service, ods_export_service, rest_time_service, work_window_service
```

In `get_24_week_averaging_period` die Abfrage der Einträge ersetzen durch:

```python
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                TimeEntry.tenant_id == current_user.tenant_id,  # F-026 (E74)
                TimeEntry.date >= start_date,
                TimeEntry.date <= end_date,
                TimeEntry.end_time.isnot(None),
            )
            .all()
        )
        total_hours = sum(float(e.net_hours or 0) for e in entries)
        # Spec 8.1 / P22: zweiter, eigens gekennzeichneter Wert — Anwesenheit laut
        # Stempel (Rohstempel abzüglich erfasster Pausen, bei Auto-Close bis zum
        # wirksamen Ende). Eine Neukappung senkt total_hours, nie diesen Wert.
        presence_hours = sum(work_window_service.presence_minutes(e) for e in entries) / 60.0
        # Spec 8.1/11.1 „je Woche": dieselbe Größe je ISO-Kalenderwoche (Mo–So) —
        # eine Woche > 48 h laut Stempel darf nicht im Fensterdurchschnitt verschwinden.
        presence_by_week: dict[str, int] = {}
        for e in entries:
            iso_year, iso_week, _ = e.date.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            presence_by_week[key] = presence_by_week.get(key, 0) + work_window_service.presence_minutes(e)
        presence_weeks = [
            {"iso_week": key, "presence_hours": round(minutes / 60.0, 2)}
            for key, minutes in sorted(presence_by_week.items())
        ]
```

Direkt nach `average = (total_hours / scheduled_days) if scheduled_days else 0.0`:

```python
        presence_average = (presence_hours / scheduled_days) if scheduled_days else 0.0
```

Im `result.append({...})` nach `"compliant": average <= 8.0,`:

```python
            "presence_hours": round(presence_hours, 2),
            "presence_average": round(presence_average, 2),
            "presence_weeks": presence_weeks,
```

- [ ] **Step 4: Backend-Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_24_week_presence.py tests/test_weekly_report.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Failing Frontend-Test schreiben**

`frontend/src/pages/admin/Reports.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import Reports from './Reports';

// Spec 2026-10-08, 8.1 / P22: neben dem angerechneten 24-Wochen-Durchschnitt
// steht die Anwesenheit laut Stempel — die senkt keine spätere Neuberechnung.

const getMock = vi.fn();
vi.mock('../../api/client', () => ({ default: { get: (...a: unknown[]) => getMock(...a) } }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

beforeEach(() => {
  getMock.mockReset();
});

describe('<Reports /> 24-Wochen-Durchschnitt (Spec 8.1, P22)', () => {
  it('zeigt angerechnete Zeit und Anwesenheit laut Stempel nebeneinander', async () => {
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-12-19', window_end: '2026-06-05', non_compliant_count: 0,
        employees: [{
          user_id: 'u1', first_name: 'Anna', last_name: 'Meier', total_hours: 15.5,
          scheduled_work_days: 2, average_daily_hours: 7.75, days_over_8h: 0, compliant: true,
          presence_hours: 22, presence_average: 11,
          presence_weeks: [{ iso_week: '2026-W23', presence_hours: 22 }],
        }],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    const table = await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    expect(within(table).getByText('Anwesenheit laut Stempel (Ø / Tag)')).toBeInTheDocument();
    expect(within(table).getByText('7:45')).toBeInTheDocument();
    expect(within(table).getByText('11:00')).toBeInTheDocument();
    expect(within(table).getByText('22:00')).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/admin\/reports\/24-week-average\?end_date=\d{4}-\d{2}-\d{2}$/),
    );
    expect(within(table).getByText('Wochen > 48 h laut Stempel')).toBeInTheDocument();
    expect(within(table).getByText('–')).toBeInTheDocument();
  });

  it('nennt Wochen mit mehr als 48 h laut Stempel (Spec 8.1/11.1 „je Woche")', async () => {
    getMock.mockResolvedValue({
      data: {
        window_start: '2025-12-19', window_end: '2026-06-12', non_compliant_count: 0,
        employees: [{
          user_id: 'u2', first_name: 'Bea', last_name: 'Kurz', total_hours: 67.5,
          scheduled_work_days: 10, average_daily_hours: 6.75, days_over_8h: 0, compliant: true,
          presence_hours: 90, presence_average: 9,
          presence_weeks: [{ iso_week: '2026-W23', presence_hours: 50 }, { iso_week: '2026-W24', presence_hours: 40 }],
        }],
      },
    });
    render(<Reports />);
    fireEvent.click(screen.getByRole('button', { name: '24-Wochen-Durchschnitt prüfen' }));
    const table = await screen.findByRole('table', { name: '24-Wochen-Durchschnitt' });
    expect(within(table).getByText('1 (2026-W23: 50:00 h)')).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Frontend-Test laufen lassen — muss scheitern**

Run (aus `frontend/`): `npx vitest run src/pages/admin/Reports.test.tsx --pool=threads`
Expected: FAIL — „Unable to find an accessible element with the role "button" and name "24-Wochen-Durchschnitt prüfen""

- [ ] **Step 7: Abschnitt in `Reports.tsx`**

Import ersetzen: `import { parseHours } from '../../utils/formatters';` → `import { formatHoursHM, parseHours } from '../../utils/formatters';`

Nach `interface CompensatoryRest {…}`:

```tsx
// Spec 2026-10-08, 8.1 / P22: 24-Wochen-Durchschnitt (§3 ArbZG) mit einem
// zweiten, eigens gekennzeichneten Wert „Anwesenheit laut Stempel".
interface AverageEmployee {
  user_id: string;
  first_name: string;
  last_name: string;
  total_hours: number;
  scheduled_work_days: number;
  average_daily_hours: number;
  days_over_8h: number;
  compliant: boolean;
  presence_hours: number;
  presence_average: number;
  /** Spec 8.1/11.1 „je Woche": Σ Anwesenheit laut Stempel je ISO-Kalenderwoche. */
  presence_weeks?: { iso_week: string; presence_hours: number }[];
}

// P22: Wochen über der 48-h-Grenze laut Stempel — Text der Spalte, sonst „–".
function weeksOver48Text(weeks: AverageEmployee['presence_weeks']): string {
  const over = (weeks ?? []).filter((w) => w.presence_hours > 48);
  if (over.length === 0) return '–';
  return `${over.length} (${over.map((w) => `${w.iso_week}: ${formatHoursHM(w.presence_hours)} h`).join(', ')})`;
}

interface AverageReport {
  window_start: string;
  window_end: string;
  employees: AverageEmployee[];
  non_compliant_count: number;
}
```

Im Komponentenrumpf nach den `compRest…`-States:

```tsx
  // 24-Wochen-Durchschnitt §3 ArbZG (Spec 8.1, P22)
  const [avgEndDate, setAvgEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [avgReport, setAvgReport] = useState<AverageReport | null>(null);
  const [avgLoading, setAvgLoading] = useState(false);
```

Nach `checkCompensatoryRest`:

```tsx
  const checkAverage = async () => {
    setAvgLoading(true);
    try {
      const res = await apiClient.get(`/admin/reports/24-week-average?end_date=${avgEndDate}`);
      setAvgReport(res.data);
    } catch {
      toast.error('Fehler beim Laden des 24-Wochen-Durchschnitts');
    } finally {
      setAvgLoading(false);
    }
  };
```

Direkt vor `{/* Additional Info */}`:

```tsx
      {/* 24-Wochen-Durchschnitt §3 ArbZG (Spec 2026-10-08, 8.1 / P22) */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6 mb-6">
        <div className="flex items-center space-x-3 mb-2">
          <Clock className="text-primary" size={24} />
          <h2 className="text-xl font-semibold">24-Wochen-Durchschnitt §3 ArbZG</h2>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Über 24 Wochen darf die angerechnete Arbeitszeit im Durchschnitt <strong>8 Stunden je Arbeitstag</strong> nicht
          überschreiten. Daneben steht die <strong>Anwesenheit laut Stempel</strong> (abzüglich erfasster Pausen) — sie
          ändert sich nicht, wenn die Anrechnung später neu berechnet wird.
        </p>
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label htmlFor="avg-end-date" className="block text-sm font-medium text-gray-700 mb-1">Stichtag</label>
            <input
              id="avg-end-date"
              type="date"
              value={avgEndDate}
              onChange={(e) => setAvgEndDate(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg"
            />
          </div>
          <button
            onClick={checkAverage}
            disabled={avgLoading}
            aria-label="24-Wochen-Durchschnitt prüfen"
            className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition disabled:opacity-50"
          >
            <Clock size={18} />
            <span>{avgLoading ? 'Prüfe...' : 'Prüfen'}</span>
          </button>
        </div>

        {avgReport !== null && (
          <table aria-label="24-Wochen-Durchschnitt" className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs text-gray-500 uppercase">Mitarbeiter:in</th>
                <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Ø angerechnet / Tag</th>
                <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Anwesenheit laut Stempel (Ø / Tag)</th>
                <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Angerechnet gesamt</th>
                <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Anwesenheit laut Stempel gesamt</th>
                <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Wochen &gt; 48 h laut Stempel</th>
                <th className="px-4 py-2 text-right text-xs text-gray-500 uppercase">Tage &gt; 8 h</th>
                <th className="px-4 py-2 text-center text-xs text-gray-500 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {avgReport.employees.map((emp) => (
                <tr key={emp.user_id} className={`hover:bg-gray-50 ${!emp.compliant ? 'bg-red-50' : ''}`}>
                  <td className="px-4 py-2 font-medium text-gray-900">{emp.first_name} {emp.last_name}</td>
                  <td className="px-4 py-2 text-right text-gray-700">{formatHoursHM(emp.average_daily_hours)}</td>
                  <td className="px-4 py-2 text-right text-gray-700">{formatHoursHM(emp.presence_average)}</td>
                  <td className="px-4 py-2 text-right text-gray-700">{formatHoursHM(emp.total_hours)}</td>
                  <td className="px-4 py-2 text-right text-gray-700">{formatHoursHM(emp.presence_hours)}</td>
                  <td className={`px-4 py-2 text-right ${weeksOver48Text(emp.presence_weeks) === '–' ? 'text-gray-700' : 'text-red-700 font-medium'}`}>
                    {weeksOver48Text(emp.presence_weeks)}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-700">{emp.days_over_8h}</td>
                  <td className="px-4 py-2 text-center">
                    {emp.compliant
                      ? <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-green-100 text-green-800">✓ Konform</span>
                      : <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-red-100 text-red-800">✗ Verstoß</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
```

- [ ] **Step 8: Frontend-Test und Typprüfung — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/pages/admin/Reports.test.tsx --pool=threads && npx tsc --noEmit`
Expected: PASS, keine TypeScript-Fehler

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/reports.py backend/tests/test_24_week_presence.py frontend/src/pages/admin/Reports.tsx frontend/src/pages/admin/Reports.test.tsx
git commit -F - <<'EOF'
feat(bloecke): 24-Wochen-Auswertung mit Anwesenheit laut Stempel (P22, PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 10: Profil „Meine Arbeitszeit" — `GET /api/auth/me/work-schedule`

**Files:**
- Create: `backend/app/services/work_schedule_service.py`, `backend/app/schemas/work_schedule.py`
- Modify: `backend/app/routers/auth.py` (Importe; neuer Endpunkt nach `get_me`)
- Create: `frontend/src/components/MyWorkScheduleCard.tsx`, `frontend/src/components/MyWorkScheduleCard.test.tsx`
- Modify: `frontend/src/pages/Profile.tsx` (Import; Karte vor `<MyQualificationsCard />`)
- Test (neu): `backend/tests/test_me_work_schedule.py`

**Interfaces:**
- Consumes: `calculation_service.get_schedule_for_date`, `get_blocks_json_for_date`, `get_daily_target_for_date` (PR1 Task 2); Frontend `WEEKDAY_LABELS`, `formatWeekBlocks`, `isLegacyWeek` (PR1 Task 15), `formatHoursHM`
- Produces:
  - `work_schedule_service.build_my_work_schedule(db: Session, user: User, on_date: date) -> dict` — `{"today": {"date", "blocks", "day_targets", "weekly_hours"}, "history": [{"effective_from", "effective_until", "blocks", "day_targets", "weekly_hours"}, …]}`; datumsaufgelöst über `get_schedule_for_date`, nie aus `users.work_blocks` direkt; kein `note` (P12); F-026
  - Schemas `WorkScheduleSnapshot`, `WorkScheduleToday`, `WorkScheduleHistoryRow`, `MyWorkScheduleResponse`
  - Endpunkt `GET /api/auth/me/work-schedule` (angemeldet, nur eigene Daten)
  - Komponente `MyWorkScheduleCard` (default export), Liste `aria-label="Arbeitszeit heute"`, Verlauf `aria-label="Verlauf der Arbeitszeit"`

- [ ] **Step 1: Failing Backend-Tests schreiben**

`backend/tests/test_me_work_schedule.py`:

```python
"""Spec 2026-10-08, Abschnitt 14 / E67 / P12 (PR2): GET /api/auth/me/work-schedule —
heute gültige Blöcke und Verlauf, datumsaufgelöst, ohne Freitext."""
import datetime as dt
import uuid
from datetime import date

import app.routers.auth as auth_router
from app.models import WorkingHoursChange
from app.models.tenant import Tenant
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, legacy_week

TODAY = date(2026, 10, 8)
LEGACY = legacy_week(mon=("07:30", "16:30"))


def _row(db, user, effective_from, blocks, **kw):
    row = WorkingHoursChange(
        user_id=user.id, tenant_id=kw.pop("tenant_id", DEFAULT_TENANT_ID),
        effective_from=effective_from, weekly_hours=kw.pop("weekly_hours", 40.0),
        use_daily_schedule=False, work_days_per_week=5, blocks=blocks,
        note=kw.pop("note", None), **kw)
    db.add(row)
    db.commit()
    return row


def _get(client, monkeypatch, d=TODAY):
    monkeypatch.setattr(auth_router, "now_local", lambda: dt.datetime(d.year, d.month, d.day, 10, 0))
    r = client.get("/api/auth/me/work-schedule")
    assert r.status_code == 200, r.text
    return r


def test_without_history_resolves_the_fallback(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    body = _get(employee_client, monkeypatch).json()
    assert body["today"]["date"] == "2026-10-08"
    assert body["today"]["blocks"] == K_BLOCKS
    assert body["today"]["day_targets"] == [8.0, 8.0, 8.0, 8.0, 8.0]
    assert body["today"]["weekly_hours"] == 40.0
    assert body["history"] == []


def test_history_with_until_future_row_and_no_note(_db_session, employee_user, employee_client, monkeypatch):
    _row(_db_session, employee_user, date(2026, 1, 1), LEGACY, note="Grund mit Klarnamen")
    _row(_db_session, employee_user, date(2026, 9, 1), K_BLOCKS, weekly_hours=20.0)
    _row(_db_session, employee_user, date(2026, 11, 1), None, weekly_hours=25.0)   # zukunftsdatiert
    r = _get(employee_client, monkeypatch)
    body = r.json()
    assert [h["effective_from"] for h in body["history"]] == ["2026-01-01", "2026-09-01", "2026-11-01"]
    assert [h["effective_until"] for h in body["history"]] == ["2026-08-31", "2026-10-31", None]
    assert body["history"][0]["blocks"] == LEGACY
    assert body["history"][1]["day_targets"] == [4.0, 4.0, 4.0, 4.0, 4.0]
    assert body["history"][2]["blocks"] is None
    assert body["today"]["blocks"] == K_BLOCKS        # die Novemberzeile wirkt heute nicht
    assert body["today"]["weekly_hours"] == 20.0
    assert "Klarnamen" not in r.text                  # P12: kein Freitext


def test_rows_of_another_tenant_are_ignored(_db_session, employee_user, employee_client, monkeypatch):
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    _db_session.add(other)
    _db_session.commit()
    _row(_db_session, employee_user, date(2026, 9, 1), K_BLOCKS, tenant_id=other.id)
    assert _get(employee_client, monkeypatch).json()["history"] == []
```

- [ ] **Step 2: Backend-Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_me_work_schedule.py -q -p no:cacheprovider`
Expected: FAIL — HTTP 404 bzw. 405 für `/api/auth/me/work-schedule`

- [ ] **Step 3: Schema und Dienst**

`backend/app/schemas/work_schedule.py`:

```python
"""Spec 2026-10-08, Abschnitt 14 / E67: die eigene Arbeitszeit im Profil."""
# #225: ``date`` aliasieren, damit das Feld namens ``date`` den Typ nicht verdeckt.
from datetime import date as date_type
from typing import Any, List, Optional

from pydantic import BaseModel


class WorkScheduleSnapshot(BaseModel):
    blocks: Optional[Any] = None   # kanonische JSON-Woche, locker gelesen (E29)
    day_targets: List[float]       # Mo–Fr
    weekly_hours: float


class WorkScheduleToday(WorkScheduleSnapshot):
    date: date_type


class WorkScheduleHistoryRow(WorkScheduleSnapshot):
    effective_from: date_type
    effective_until: Optional[date_type] = None


class MyWorkScheduleResponse(BaseModel):
    today: WorkScheduleToday
    history: List[WorkScheduleHistoryRow]
```

`backend/app/services/work_schedule_service.py`:

```python
"""Spec 2026-10-08, Abschnitt 14 / E67 / P12: die eigene Arbeitszeit — heute
gültige Blöcke und Verlauf. Datumsaufgelöst über den Vertrags-Snapshot
(``calculation_service.get_schedule_for_date``), nie aus ``users.work_blocks``
direkt; ohne den Verwaltungsfreitext ``note`` (der steht im Art.-15-Export)."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import User, WorkingHoursChange
from app.services import calculation_service


def _snapshot(db: Session, user: User, d: date, wh_changes) -> dict:
    schedule = calculation_service.get_schedule_for_date(db, user, d, wh_changes)
    monday = d - timedelta(days=d.weekday())
    return {
        "blocks": calculation_service.get_blocks_json_for_date(db, user, d, wh_changes),
        "day_targets": [
            float(calculation_service.get_daily_target_for_date(user, monday + timedelta(days=i), schedule))
            for i in range(5)
        ],
        "weekly_hours": float(schedule.weekly_hours),
    }


def build_my_work_schedule(db: Session, user: User, on_date: date) -> dict:
    rows = (
        db.query(WorkingHoursChange)
        .filter(
            WorkingHoursChange.user_id == user.id,
            WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
        )
        .order_by(WorkingHoursChange.effective_from)
        .all()
    )
    history = []
    for i, row in enumerate(rows):
        following = rows[i + 1].effective_from if i + 1 < len(rows) else None
        history.append({
            "effective_from": row.effective_from,
            "effective_until": following - timedelta(days=1) if following else None,
            **_snapshot(db, user, row.effective_from, rows),
        })
    return {"today": {"date": on_date, **_snapshot(db, user, on_date, rows)}, "history": history}
```

- [ ] **Step 4: Endpunkt in `auth.py`**

Importe ergänzen:

```python
from app.schemas.work_schedule import MyWorkScheduleResponse
from app.services import work_schedule_service
```

Direkt nach der Funktion zu `@router.get("/me", response_model=UserResponse)`:

```python
@router.get("/me/work-schedule", response_model=MyWorkScheduleResponse)
def get_my_work_schedule(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spec 2026-10-08, 14 / E67: die heute gültigen Arbeitszeit-Blöcke und ihr
    Verlauf — nur eigene Daten, ohne Freitext (P12)."""
    return work_schedule_service.build_my_work_schedule(db, current_user, now_local().date())
```

- [ ] **Step 5: Backend-Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_me_work_schedule.py tests/test_no_live_work_blocks_read.py -q -p no:cacheprovider`
Expected: PASS (der Guard bleibt grün — der neue Dienst liest `users.work_blocks` nicht selbst)

- [ ] **Step 6: Failing Frontend-Test schreiben**

`frontend/src/components/MyWorkScheduleCard.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import MyWorkScheduleCard from './MyWorkScheduleCard';

// Spec 2026-10-08, Abschnitt 14 / E67: Profilkarte „Meine Arbeitszeit".

const getMock = vi.fn();
vi.mock('../api/client', () => ({ default: { get: (...a: unknown[]) => getMock(...a) } }));

const NONE = { blocks: [], pause_minutes: 0 };
const WEEK = [
  { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
  { blocks: [{ start: '08:00', end: '13:00' }], pause_minutes: 0 },
  NONE,
  { blocks: [{ start: '08:00', end: '12:00' }], pause_minutes: 0 },
  NONE,
];

beforeEach(() => {
  getMock.mockReset();
});

describe('<MyWorkScheduleCard />', () => {
  it('zeigt je Wochentag die heutigen Blöcke mit Tagessoll und den Verlauf', async () => {
    getMock.mockResolvedValue({
      data: {
        today: { date: '2026-10-08', blocks: WEEK, day_targets: [6.5, 5, 0, 4, 0], weekly_hours: 15.5 },
        history: [
          { effective_from: '2026-01-01', effective_until: '2026-08-31', blocks: null,
            day_targets: [8, 8, 8, 8, 8], weekly_hours: 40 },
          { effective_from: '2026-09-01', effective_until: null, blocks: WEEK,
            day_targets: [6.5, 5, 0, 4, 0], weekly_hours: 15.5 },
        ],
      },
    });
    render(<MyWorkScheduleCard />);
    const today = await screen.findByRole('list', { name: 'Arbeitszeit heute' });
    expect(within(today).getByText('Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Tagessoll 6:30 h')).toBeInTheDocument();
    expect(within(today).getByText('Mi – · Tagessoll 0:00 h')).toBeInTheDocument();
    expect(screen.getByText('Wochenstunden: 15:30 h')).toBeInTheDocument();
    const history = screen.getByRole('list', { name: 'Verlauf der Arbeitszeit' });
    expect(within(history).getByText('ab 01.01.2026 bis 31.08.2026: keine Arbeitszeit-Blöcke · 40:00 h/Woche')).toBeInTheDocument();
    expect(within(history).getByText(
      'ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00 · Do 08:00–12:00 · 15:30 h/Woche',
    )).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith('/auth/me/work-schedule');
  });

  it('kennzeichnet ein Altfenster (nur Anrechnung, kein Tagessoll)', async () => {
    const legacy = [
      { blocks: [{ start: '07:30', end: '16:30' }], pause_minutes: null },
      { blocks: [], pause_minutes: null }, { blocks: [], pause_minutes: null },
      { blocks: [], pause_minutes: null }, { blocks: [], pause_minutes: null },
    ];
    getMock.mockResolvedValue({
      data: { today: { date: '2026-10-08', blocks: legacy, day_targets: [8, 8, 8, 8, 8], weekly_hours: 40 }, history: [] },
    });
    render(<MyWorkScheduleCard />);
    expect(await screen.findByText(/begrenzen nur die Anrechnung/)).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Verlauf der Arbeitszeit' })).not.toBeInTheDocument();
  });

  it('rendert nichts, wenn der Abruf scheitert', async () => {
    getMock.mockRejectedValue(new Error('offline'));
    const { container } = render(<MyWorkScheduleCard />);
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 7: Frontend-Test laufen lassen — muss scheitern**

Run (aus `frontend/`): `npx vitest run src/components/MyWorkScheduleCard.test.tsx --pool=threads`
Expected: FAIL — „Failed to resolve import ./MyWorkScheduleCard"

- [ ] **Step 8: Karte anlegen und im Profil einbinden**

`frontend/src/components/MyWorkScheduleCard.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { Clock } from 'lucide-react';
import apiClient from '../api/client';
import { formatHoursHM } from '../utils/formatters';
import { WEEKDAY_LABELS, formatWeekBlocks, isLegacyWeek } from '../utils/workBlocks';
import type { WeekBlocks } from '../types/workBlocks';

/**
 * Spec 2026-10-08, Abschnitt 14 / E67: „Meine Arbeitszeit" — die heute gültigen
 * Arbeitszeit-Blöcke je Wochentag mit Tagessoll und der Verlauf mit
 * Wirkungsdaten. Datumsaufgelöst vom Server (`GET /auth/me/work-schedule`);
 * der Verwaltungsfreitext steht bewusst nicht hier (P12, Art.-15-Export).
 */
interface Snapshot {
  blocks: WeekBlocks | null;
  day_targets: number[];
  weekly_hours: number;
}

interface WorkSchedule {
  today: Snapshot & { date: string };
  history: (Snapshot & { effective_from: string; effective_until: string | null })[];
}

function deDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

export default function MyWorkScheduleCard() {
  const [data, setData] = useState<WorkSchedule | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get('/auth/me/work-schedule')
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch(() => { /* Karte entfällt — nicht kritisch */ });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) return null;
  const today = data.today;

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <div className="flex items-center gap-2 mb-3">
        <Clock size={18} className="text-primary" />
        <h2 className="text-lg font-semibold text-gray-900">Meine Arbeitszeit</h2>
      </div>
      <ul className="text-sm text-gray-700 space-y-1" aria-label="Arbeitszeit heute">
        {WEEKDAY_LABELS.map((label, i) => {
          const day = today.blocks?.[i];
          const spans = day && day.blocks.length > 0
            ? day.blocks.map((b) => `${b.start}–${b.end}`).join(' + ')
            : '–';
          const pause = day?.pause_minutes ? ` (Pause ${day.pause_minutes} Min)` : '';
          return (
            <li key={label}>
              {`${label} ${spans}${pause} · Tagessoll ${formatHoursHM(today.day_targets[i] ?? 0)} h`}
            </li>
          );
        })}
      </ul>
      <p className="text-sm text-gray-500 mt-2">{`Wochenstunden: ${formatHoursHM(today.weekly_hours)} h`}</p>
      {isLegacyWeek(today.blocks) && (
        <p className="text-xs text-gray-500 mt-1">
          Diese Zeiten begrenzen nur die Anrechnung der erfassten Zeit; das Tagessoll ergibt sich aus den Wochenstunden.
        </p>
      )}
      {data.history.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Verlauf</h3>
          <ul className="text-sm text-gray-600 space-y-1" aria-label="Verlauf der Arbeitszeit">
            {data.history.map((h) => (
              <li key={h.effective_from}>
                {`ab ${deDate(h.effective_from)}${h.effective_until ? ` bis ${deDate(h.effective_until)}` : ''}: `
                  + `${formatWeekBlocks(h.blocks) ?? 'keine Arbeitszeit-Blöcke'} · ${formatHoursHM(h.weekly_hours)} h/Woche`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

In `frontend/src/pages/Profile.tsx` nach `import MyQualificationsCard from '../components/MyQualificationsCard';`:

```tsx
import MyWorkScheduleCard from '../components/MyWorkScheduleCard';
```

und direkt vor `<MyQualificationsCard />`:

```tsx
        <MyWorkScheduleCard />
```

- [ ] **Step 9: Frontend-Tests und Typprüfung — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/components/MyWorkScheduleCard.test.tsx --pool=threads && npx tsc --noEmit`
Expected: PASS, keine TypeScript-Fehler

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/work_schedule.py backend/app/services/work_schedule_service.py backend/app/routers/auth.py backend/tests/test_me_work_schedule.py frontend/src/components/MyWorkScheduleCard.tsx frontend/src/components/MyWorkScheduleCard.test.tsx frontend/src/pages/Profile.tsx
git commit -F - <<'EOF'
feat(bloecke): Profil „Meine Arbeitszeit" mit heute gültigen Blöcken und Verlauf (E67, PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 11: Art.-15/20- und §16-Notfallexport (15.3)

**Files:**
- Modify: `backend/app/services/lifecycle_service.py` (`_user_dict`, `_time_entry_dict`, `_change_request_dict`, `_build_art15_meta`)
- Modify: `backend/app/routers/auth.py` (`export_my_data`)
- Modify: `backend/app/routers/superadmin.py` (`_user_dict`, `_time_entry_dict`)
- Modify: `backend/tests/test_no_live_work_blocks_read.py` (`ALLOWED` um drei Exportstellen)
- Test (neu): `backend/tests/test_dsgvo_work_blocks.py`

**Interfaces:**
- Consumes: `User.work_blocks`, `WorkingHoursChange.blocks`, `TimeEntry.uncredited_minutes/credit_override/auto_closed/clamp_grace_minutes`, `ChangeRequest.request_credit_override/original_uncredited_minutes` (PR1)
- Produces:
  - Art. 15 (`_user_dict`): `work_blocks` (wie gespeichert) und je Verlaufszeile `blocks`; `_time_entry_dict`: `uncredited_minutes` (int), `credit_override` (bool), `auto_closed` (bool), `clamp_grace_minutes` (int|None); `_change_request_dict`: `request_credit_override` (bool), `original_uncredited_minutes` (int|None); Kategorien „Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause, Verlauf)", „nicht angerechnete Zeit und Anerkennungen"; Logik-Satz in `h_automatisierte_entscheidung` (Konsistenz zu Spec 14, Art. 15 Abs. 1 lit. h)
  - Art. 20 (`/api/auth/me/export`): `stammdaten.work_blocks`, `zeiteintraege[*]` mit den vier Feldern, `stundenhistorie[*].blocks`
  - §16-Notfallexport (`superadmin`): je Eintrag die vier Felder; **zusätzlich über 15.3 hinaus** `work_blocks` und Verlaufs-`blocks` im Personen-Dict — Begründung wie der #431-Kommentar dort: ohne den Vertragszustand ist die Kappung im §16-Dokument nicht herleitbar (Betreiber vor dem Merge informieren)
  - Guard-Erlaubnisliste um `("app/services/lifecycle_service.py", "_user_dict")`, `("app/routers/auth.py", "export_my_data")`, `("app/routers/superadmin.py", "_user_dict")`

Spec 15.4 (Anonymisierung leert `working_hours_changes.note`, beide Pfade) ist bereits Bestand und durch `tests/test_anonymize_scrubs_wh_note.py` und `tests/test_tenant_anonymization.py` abgedeckt — im Gesamtlauf (Task 19) mitlaufen lassen, nichts ändern.

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_dsgvo_work_blocks.py`:

```python
"""Spec 2026-10-08, 15.3 / E72 (PR2): Auskunfts- und §16-Notfallexporte führen
Blöcke, Verlauf und die neuen Eintrags-/Antragsfelder — nur str/int/bool/None."""
import json
from datetime import date, time

from app.models import ChangeRequest, TimeEntry, WorkingHoursChange
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.routers import superadmin
from app.services import lifecycle_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

LEGACY = legacy_week(mon=("07:37", None))   # Altwert + Platzhalter 23:59
ENTRY_FIELDS = {"uncredited_minutes": 150, "credit_override": False, "auto_closed": False,
                "clamp_grace_minutes": 15}


def _seed(db, user):
    user.work_blocks = LEGACY
    db.add(WorkingHoursChange(user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
                              effective_from=date(2026, 9, 1), weekly_hours=40.0,
                              use_daily_schedule=False, work_days_per_week=5, blocks=K_BLOCKS,
                              note="Grund"))
    te = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                   start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                   raw_end_time=time(19), break_minutes=0, uncredited_minutes=150,
                   clamp_grace_minutes=15)
    db.add(te)
    db.commit()
    db.add(ChangeRequest(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
                         request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                         time_entry_id=te.id, proposed_date=MON, proposed_start_time=time(7),
                         proposed_end_time=time(19), proposed_break_minutes=0,
                         reason="Durchgearbeitet", request_credit_override=True,
                         original_uncredited_minutes=150))
    db.commit()
    return te


def _pick(d):
    return {k: d[k] for k in ENTRY_FIELDS}


def test_art15_self_export(_db_session, employee_user):
    _seed(_db_session, employee_user)
    payload = lifecycle_service.build_self_export_payload(_db_session, employee_user)
    json.dumps(payload)   # #383/#408: nur JSON-fähige Werte
    assert payload["subject"]["work_blocks"] == LEGACY
    assert payload["subject"]["working_hours_changes"][0]["blocks"] == K_BLOCKS
    assert _pick(payload["time_entries"][0]) == ENTRY_FIELDS
    cr = payload["change_requests"][0]
    assert (cr["request_credit_override"], cr["original_uncredited_minutes"]) == (True, 150)


def test_art15_categories_and_logic():
    meta = lifecycle_service._build_art15_meta()
    assert "Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause, Verlauf)" in meta["b_datenkategorien"]
    assert "nicht angerechnete Zeit und Anerkennungen" in meta["b_datenkategorien"]
    assert "zwischen den Blöcken" in meta["h_automatisierte_entscheidung"]


def test_art20_me_export(_db_session, employee_user, employee_client):
    _seed(_db_session, employee_user)
    r = employee_client.get("/api/auth/me/export")
    assert r.status_code == 200, r.text
    data = json.loads(r.content)
    assert data["stammdaten"]["work_blocks"] == LEGACY
    assert data["stundenhistorie"][0]["blocks"] == K_BLOCKS
    assert _pick(data["zeiteintraege"][0]) == ENTRY_FIELDS


def test_superadmin_emergency_export_dicts(_db_session, employee_user):
    te = _seed(_db_session, employee_user)
    history = _db_session.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == employee_user.id).all()
    user = superadmin._user_dict(employee_user, history)
    entry = superadmin._time_entry_dict(te)
    json.dumps(user)
    json.dumps(entry)
    assert user["work_blocks"] == LEGACY
    assert user["working_hours_changes"][0]["blocks"] == K_BLOCKS
    assert _pick(entry) == ENTRY_FIELDS
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_dsgvo_work_blocks.py -q -p no:cacheprovider`
Expected: FAIL — `KeyError: 'work_blocks'`

- [ ] **Step 3: `lifecycle_service.py`**

In `_user_dict` nach `"hours_friday": …,` (User-Ebene):

```python
        # Spec 2026-10-08 (15.3, E72): Arbeitszeit-Blöcke wie gespeichert — Liste
        # aus Dicts mit "HH:MM"-Strings, JSON-fähig. Rückfallwert vor der ersten
        # Verlaufszeile; Ausgabe, keine Berechnung (Guard-Erlaubnisliste).
        "work_blocks": u.work_blocks,
```

In der Verlaufszeile (`"working_hours_changes": [ {...} for h in history ]`) nach `"work_days_per_week": h.work_days_per_week,`:

```python
                "blocks": h.blocks,
```

In `_time_entry_dict` nach `"sunday_exception_reason": …,`:

```python
        # Spec 2026-10-08 (15.3): nicht angerechnete Lückenminuten, Anerkennung,
        # Auto-Close-Kennzeichen (P18: sonst läse sich raw_end 23:59 als Stempel)
        # und der Puffer der letzten Kappung (E79). Nur int/bool/None.
        "uncredited_minutes": int(getattr(te, "uncredited_minutes", 0) or 0),
        "credit_override": bool(getattr(te, "credit_override", False)),
        "auto_closed": bool(getattr(te, "auto_closed", False)),
        "clamp_grace_minutes": getattr(te, "clamp_grace_minutes", None),
```

In `_change_request_dict` nach `"original_note": c.original_note,`:

```python
        # Spec 2026-10-08 (P21, P28): „Anrechnung beantragen" und Vorher-Snapshot.
        "request_credit_override": bool(getattr(c, "request_credit_override", False)),
        "original_uncredited_minutes": getattr(c, "original_uncredited_minutes", None),
```

In `_build_art15_meta`, Liste `"b_datenkategorien"` nach `"Zeiteintraege (Datum, Beginn, Ende, Pausen, Notiz)",`:

```python
            "Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause, Verlauf)",
            "nicht angerechnete Zeit und Anerkennungen",
```

und `"h_automatisierte_entscheidung"` ersetzen durch:

```python
        "h_automatisierte_entscheidung": (
            "Es findet KEINE automatisierte Entscheidung im Sinne von Art. 22 "
            "DSGVO statt. Genehmigungen von Antraegen erfolgen ausschliesslich "
            "durch einen menschlichen Admin. Hinterlegte Arbeitszeit-Blöcke wirken "
            "automatisch auf die Anrechnung: gestempelte Zeit vor dem ersten Block, "
            "nach dem letzten Block und zwischen den Blöcken wird – abzüglich eines "
            "Puffers – nicht angerechnet; die Stempelzeiten bleiben gespeichert. Die "
            "Verwaltung kann nicht angerechnete Zeit anerkennen; die Anrechnung kann "
            "per Änderungsantrag beantragt werden."
        ),
```

- [ ] **Step 4: `auth.py` (`export_my_data`)**

In `"stammdaten": {...}` nach `"vacation_days": …,`:

```python
            "work_blocks": current_user.work_blocks,  # Spec 15.3 / E72: wie gespeichert
```

In `"zeiteintraege": [ {...} ]` nach `"note": e.note,`:

```python
                # Spec 2026-10-08 (15.3): nur int/bool/None — rohes JSONResponse.
                "uncredited_minutes": int(e.uncredited_minutes or 0),
                "credit_override": bool(e.credit_override),
                "auto_closed": bool(e.auto_closed),
                "clamp_grace_minutes": e.clamp_grace_minutes,
```

In `"stundenhistorie": [ {...} ]` nach `"work_days_per_week": h.work_days_per_week,`:

```python
                "blocks": h.blocks,
```

- [ ] **Step 5: `superadmin.py`**

In `_user_dict` nach `"hours_friday": _num(u.hours_friday),`:

```python
        # Spec 2026-10-08 (über 15.3 hinaus, Begründung wie #431 oben): ohne den
        # Rückfallwert der Arbeitszeit-Blöcke ist die Kappung vor der ersten
        # Verlaufszeile im §16-Dokument nicht herleitbar.
        "work_blocks": u.work_blocks,
```

In der Verlaufszeile nach `"work_days_per_week": h.work_days_per_week,`:

```python
                "blocks": h.blocks,
```

In `_time_entry_dict` nach `"sunday_exception_reason": te.sunday_exception_reason,`:

```python
        # Spec 2026-10-08 (15.3): ohne auto_closed läse sich raw_end_time 23:59 als
        # echter Stempel (P18). Nur int/bool/None — rohes json.dumps.
        "uncredited_minutes": int(te.uncredited_minutes or 0),
        "credit_override": bool(te.credit_override),
        "auto_closed": bool(te.auto_closed),
        "clamp_grace_minutes": te.clamp_grace_minutes,
```

- [ ] **Step 6: Guard-Erlaubnisliste ergänzen**

In `backend/tests/test_no_live_work_blocks_read.py` die Menge `ALLOWED` um drei Einträge ergänzen (bestehende Einträge stehen lassen):

```python
    # PR2 (Spec 15.3 / E72): Auskunfts- und §16-Notfallexporte geben den
    # gespeicherten Rückfallwert unverändert aus — keine Berechnung.
    ("app/services/lifecycle_service.py", "_user_dict"),
    ("app/routers/auth.py", "export_my_data"),
    ("app/routers/superadmin.py", "_user_dict"),
```

- [ ] **Step 7: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_dsgvo_work_blocks.py tests/test_no_live_work_blocks_read.py tests/test_self_data_export.py tests/test_superadmin_arbzg_export.py tests/test_superadmin_export_schedule_history.py tests/test_dsgvo_export_schedule.py tests/test_anonymize_scrubs_wh_note.py tests/test_tenant_anonymization.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/lifecycle_service.py backend/app/routers/auth.py backend/app/routers/superadmin.py backend/tests/test_no_live_work_blocks_read.py backend/tests/test_dsgvo_work_blocks.py
git commit -F - <<'EOF'
feat(bloecke): Art.-15/20- und §16-Notfallexport mit Blöcken und Anrechnungsfeldern (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 12: XLS-Vorschau — Netto vom Server und Anwesenheits-Hinweise

**Files:**
- Modify: `backend/app/services/xls_import_service.py` (Importe; `ImportedEntry`; `parse_xls`)
- Modify: `frontend/src/pages/admin/ImportXls.tsx` (Typ `ImportedEntry`, Netto-Zelle, `calcNetHours` entfernen)
- Test: `backend/tests/test_xls_blocks.py` (anhängen), `frontend/src/pages/admin/ImportXls.test.tsx` (neu)

**Interfaces:**
- Consumes: `presence_service.closed_entries`, `day_presence`, `daily_presence_warnings`, `break_in_gap_warning` (Task 3); PR1-`parse_xls` mit den Variablen `existing`, `r`, `start_t`, `end_t`, `raw_start_t`, `raw_end_t`, `break_min`, `arbzg_warnings`, `exempt`, `user`; Test-Helfer `tests.test_xls_blocks._xls`, `_entry` (PR1 Task 10)
- Produces:
  - `ImportedEntry.net_hours: float = 0.0` — nur Anzeige; `/confirm` rechnet neu (wie `uncredited_minutes`)
  - Zeilenhinweise der Vorschau als Klartext ohne Code (Spec 8.3): `PRESENCE_DAILY_HOURS`/`PRESENCE_BREAK`-Text und `BREAK_IN_GAP`-Text; der von der Zeile überschriebene Bestandseintrag zählt nicht mit
  - `ImportXls.tsx` zeigt `net_hours` (H:MM) und darunter „H:MM h nicht angerechnet", wenn `uncredited_minutes > 0`

- [ ] **Step 1: Failing Backend-Tests anhängen**

An `backend/tests/test_xls_blocks.py` anhängen:

```python
# ── PR2: Netto vom Server und Anwesenheits-Hinweise in der Vorschau (7.4, 8.3) ──
def _k1_row():
    return _xls((datetime(2026, 6, 1, 8, 0), datetime(2026, 6, 1, 18, 0)))


def test_preview_net_hours_from_the_server(db, test_user):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    [e] = parse_xls(_k1_row(), test_user.id, db)
    assert (e.uncredited_minutes, e.break_minutes, e.net_hours) == (150, 0, 7.5)


def test_preview_lists_the_presence_hint_as_plain_text(db, test_user):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    [e] = parse_xls(_k1_row(), test_user.id, db)
    assert any(w.startswith("§4 ArbZG: Durchgehend über die Lücke") for w in e.arbzg_warnings)
    assert not any(w.startswith(("PRESENCE_", "BREAK_IN_GAP")) for w in e.arbzg_warnings)


# Review Focus 4: der überschriebene Bestandseintrag zählt in der Anwesenheit nicht doppelt.
def test_reimport_does_not_double_count_presence(db, test_user):
    test_user.work_blocks = K_BLOCKS
    _entry(db, test_user, time(8), time(12, 30), uncredited_minutes=15, clamp_grace_minutes=15)
    [e] = parse_xls(_xls((datetime(2026, 6, 1, 8, 0), datetime(2026, 6, 1, 12, 30))), test_user.id, db)
    assert e.has_conflict is True
    assert not any("Laut Stempel" in w or "Durchgehend" in w for w in e.arbzg_warnings), e.arbzg_warnings


def test_exempt_person_gets_no_presence_hint(db, test_user):
    test_user.work_blocks = K_BLOCKS
    test_user.exempt_from_arbzg = True
    db.commit()
    [e] = parse_xls(_k1_row(), test_user.id, db)
    assert not any("Laut Stempel" in w or "Durchgehend" in w for w in e.arbzg_warnings)
```

- [ ] **Step 2: Backend-Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_xls_blocks.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: 'ImportedEntry' object has no attribute 'net_hours'`; der Hinweistest findet keinen „Durchgehend"-Text

- [ ] **Step 3: `xls_import_service.py`**

Importe ergänzen:

```python
from types import SimpleNamespace

from app.services import presence_service
```

`ImportedEntry` nach `uncredited_minutes: int = 0`:

```python
    # Spec 7.4 (PR2): Netto der Vorschau vom Server — ImportXls.tsx rechnet nicht
    # mehr selbst. Nur Anzeige; /confirm rechnet neu.
    net_hours: float = 0.0
```

In `parse_xls` direkt nach `batch_blocks_by_date: dict[date, list[BreakBlock]] = {}` / `db_blocks_by_date: …`:

```python
    # Spec 8.3 (PR2): Anwesenheit laut Stempel je Tag — Bestand + bisheriger Batch;
    # von einer Importzeile überschriebene Bestandseinträge zählen nicht mit.
    db_presence_by_date: dict = {}
    batch_presence_by_date: dict = {}
    replaced_by_date: dict = {}
```

In der Zeilenschleife direkt nach dem Block `if override: arbzg_warnings = arbzg_warnings + [CREDIT_OVERRIDE_IMPORT_NOTE]` (vor „# Diesen Block für nachfolgende Zeilen am selben Tag merken"):

```python
        # Spec 7.4: Netto wie TimeEntry.net_hours (E13) — dieselbe Formel, die
        # beim Import gespeichert wird.
        net = float(TimeEntry(
            start_time=start_t, end_time=end_t, break_minutes=break_min,
            uncredited_minutes=r.uncredited_minutes,
        ).net_hours)

        # Spec 8.3 (XLS-Vorschau): Anwesenheit laut Stempel als Klartext-Hinweis
        # ohne Code. §4 „bestanden" = _check_arbzg meldete keinen §4-Verstoß (P14).
        if not exempt:
            row_view = SimpleNamespace(
                start_time=start_t, end_time=end_t, raw_start_time=raw_start_t,
                raw_end_time=raw_end_t, break_minutes=break_min, auto_closed=False,
                uncredited_minutes=r.uncredited_minutes, net_hours=net,
            )
            if existing is not None:
                replaced_by_date.setdefault(entry_date, set()).add(existing.id)
            if entry_date not in db_presence_by_date:
                db_presence_by_date[entry_date] = presence_service.closed_entries(
                    db, user, entry_date, entry_date,
                )
            replaced = replaced_by_date.get(entry_date, set())
            day_rows = (
                [e for e in db_presence_by_date[entry_date] if e.id not in replaced]
                + batch_presence_by_date.get(entry_date, [])
                + [row_view]
            )
            break_passed = not any(w.startswith("§4 ArbZG") for w in arbzg_warnings)
            hints = presence_service.daily_presence_warnings(
                presence_service.day_presence(day_rows), break_check_passed=break_passed,
            )
            gap_hint = presence_service.break_in_gap_warning(row_view)
            if gap_hint:
                hints.insert(0, gap_hint)
            arbzg_warnings = arbzg_warnings + [h.split(": ", 1)[1] for h in hints]
            batch_presence_by_date.setdefault(entry_date, []).append(row_view)
```

Im Konstruktor `entries.append(ImportedEntry(...))` nach `uncredited_minutes=r.uncredited_minutes,`:

```python
            net_hours=net,
```

- [ ] **Step 4: Backend-Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_xls_blocks.py tests/test_xls_import_service.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Failing Frontend-Test schreiben**

`frontend/src/pages/admin/ImportXls.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ImportXls from './ImportXls';

// Spec 2026-10-08, 7.4: die Vorschau zeigt das Netto des Servers (nach nicht
// angerechneter Lücke und Auto-Pause) statt es im Browser nachzurechnen.

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
  },
}));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
});

describe('<ImportXls /> Vorschau-Netto (Spec 7.4)', () => {
  it('zeigt net_hours vom Server und die nicht angerechnete Lücke', async () => {
    getMock.mockResolvedValue({
      data: [{ id: 'u1', first_name: 'Jane', last_name: 'Doe', username: 'jd', is_active: true }],
    });
    postMock.mockResolvedValue({
      data: {
        total: 1, conflicts: 0, arbzg_warnings: 0,
        entries: [{
          date: '2026-06-01', start_time: '08:00:00', end_time: '18:00:00', break_minutes: 0,
          note: null, has_conflict: false, arbzg_warnings: [], uncredited_minutes: 150, net_hours: 7.5,
        }],
      },
    });
    const { container } = render(<ImportXls />);
    const select = screen.getByRole('combobox');
    fireEvent.focus(select);
    await screen.findByRole('option', { name: 'Jane Doe (jd)' });
    fireEvent.change(select, { target: { value: 'u1' } });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'zeit.xls')] } });
    fireEvent.click(screen.getByRole('button', { name: 'Datei analysieren →' }));
    expect(await screen.findByText('7:30')).toBeInTheDocument();
    expect(screen.getByText('2:30 h nicht angerechnet')).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Frontend-Test laufen lassen — muss scheitern**

Run (aus `frontend/`): `npx vitest run src/pages/admin/ImportXls.test.tsx --pool=threads`
Expected: FAIL — „Unable to find an element with the text: 7:30" (der Browser rechnet 10:00)

- [ ] **Step 7: `ImportXls.tsx`**

Import ergänzen:

```tsx
import { formatHoursHM } from '../../utils/formatters';
```

`interface ImportedEntry` nach `arbzg_warnings: string[];`:

```tsx
  raw_start_time?: string | null;
  raw_end_time?: string | null;
  // Spec 2026-10-08 (7.4): Netto und nicht angerechnete Lücke rechnet der Server.
  uncredited_minutes?: number;
  net_hours?: number;
```

Die Funktion `calcNetHours` vollständig löschen und die Netto-Zelle ersetzen durch:

```tsx
                    <td className="px-3 py-2">
                      {formatHoursHM(e.net_hours ?? 0)}
                      {(e.uncredited_minutes ?? 0) > 0 && (
                        <div className="text-xs text-gray-500">
                          {`${formatHoursHM((e.uncredited_minutes ?? 0) / 60)} h nicht angerechnet`}
                        </div>
                      )}
                    </td>
```

- [ ] **Step 8: Frontend-Test, Typprüfung, Lint — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/pages/admin/ImportXls.test.tsx --pool=threads && npx tsc --noEmit && npx eslint src/pages/admin/ImportXls.tsx`
Expected: PASS, keine Fehler

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/xls_import_service.py backend/tests/test_xls_blocks.py frontend/src/pages/admin/ImportXls.tsx frontend/src/pages/admin/ImportXls.test.tsx
git commit -F - <<'EOF'
feat(bloecke): XLS-Vorschau mit Server-Netto und Anwesenheits-Hinweisen (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 13: Frontend-Zwillinge, neue Warncodes, §4-Vorprüfung mit Lückensegmenten

**Files:**
- Modify: `frontend/src/utils/workBlocks.ts` (Import um `TimeBlock`; Funktionen anhängen)
- Create: `frontend/src/utils/workBlocksCases.ts`
- Modify: `frontend/src/utils/arbzgWarnings.ts` (vier `case`, Kommentar `BREAK_WARNING`)
- Modify: `frontend/src/utils/breakValidation.ts` (`BreakBlock`, `computeBreakError`)
- Test: `frontend/src/utils/workBlocks.test.ts`, `arbzgWarnings.test.ts`, `breakValidation.test.ts` (anhängen)

**Interfaces:**
- Consumes: `types/workBlocks.ts` (`TimeBlock`, `WeekBlocks`), `utils/workBlocks.ts` (PR1 Task 15); Werte der Backend-Falltabelle `backend/tests/work_blocks_cases.py`
- Produces (in `utils/workBlocks.ts`):
  - `hhmmToMinutes(value: string): number`
  - `gapSegments(blocks: TimeBlock[] | null | undefined, grace: number, start: string, end: string): number[]` — Zwilling von `work_window_service.gap_segments`
  - `isInBlockGap(blocks: TimeBlock[] | null | undefined, minutes: number): boolean` — ungeschrumpfte Lücke `[Ende Block i, Beginn Block i+1)`
  - `blocksSpan(blocks: TimeBlock[] | null | undefined): { start: string; end: string } | null`
  - `interface CreditEntry`, `notCreditedMinutes(e: CreditEntry): number` — Zwilling von `not_credited_minutes`
  - `interface StampEntry extends CreditEntry`, `interface StampNoteData`, `stampNoteProps(e: StampEntry): StampNoteData`
- Produces (in `utils/workBlocksCases.ts`): `interface KCaseFE`, `K_CASES_FE: KCaseFE[]` (IDs K1–K21 wie im Backend)
- Produces (in `utils/breakValidation.ts`): `BreakBlock.deduct?: number`, `BreakBlock.pauseSegments?: number[]`; `computeBreakError(existingBlocks, startTime, endTime, breakMinutes, exempt, uncreditedSegments: number[] = [])`
- Produces (in `utils/arbzgWarnings.ts`): `case`s `PRESENCE_DAILY_HOURS`, `PRESENCE_BREAK`, `PRESENCE_WEEKLY_HOURS`, `BREAK_IN_GAP` (Servertext, sonst Rückfalltext)

- [ ] **Step 1: Falltabelle als Zwilling anlegen**

`frontend/src/utils/workBlocksCases.ts`:

```ts
// Spec 2026-10-08, 6.3: Falltabelle K1–K21 — Zwilling von
// backend/tests/work_blocks_cases.py (gleiche IDs, gleiche Werte, Puffer 15).
// `dayBlocks` = was GET /time-entries/clock-status als `blocks_today` für den
// Falltag liefert (Feiertag/Sonntag/track_hours=false → []); `stored` = der
// Eintrag, wie das Backend ihn speichert.
import type { TimeBlock } from '../types/workBlocks';

export interface KCaseFE {
  id: string;
  dayBlocks: TimeBlock[];
  start: string;
  end: string | null;
  creditOverride: boolean;
  stored: {
    start_time: string;
    end_time: string | null;
    raw_start_time: string | null;
    raw_end_time: string | null;
    break_minutes: number;
    uncredited_minutes: number;
    auto_closed: boolean;
    net_hours: number;
  };
  notCredited: number;
}

type Stored = Partial<KCaseFE['stored']> & { start_time: string; end_time: string | null };

const K: TimeBlock[] = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];
const K6: TimeBlock[] = [{ start: '08:00', end: '12:00' }, { start: '12:30', end: '16:00' }];
const K17: TimeBlock[] = [
  { start: '07:00', end: '10:00' }, { start: '11:00', end: '13:00' }, { start: '16:00', end: '19:00' },
];
const K19: TimeBlock[] = [{ start: '08:00', end: '10:00' }, { start: '15:00', end: '18:00' }];

function c(
  id: string, dayBlocks: TimeBlock[], start: string, end: string | null,
  stored: Stored, notCredited: number, creditOverride = false,
): KCaseFE {
  return {
    id, dayBlocks, start, end, creditOverride, notCredited,
    stored: {
      raw_start_time: null, raw_end_time: null, break_minutes: 0, uncredited_minutes: 0,
      auto_closed: false, net_hours: 0, ...stored,
    },
  };
}

const DAY_10H_P45: Stored = { start_time: '08:00', end_time: '18:00', break_minutes: 45, net_hours: 9.25 };

export const K_CASES_FE: KCaseFE[] = [
  c('K1', K, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', uncredited_minutes: 150, net_hours: 7.5 }, 150),
  c('K2', K, '13:00', null, { start_time: '13:00', end_time: null }, 0),
  c('K2b', K, '13:00', '18:00', { start_time: '13:00', end_time: '18:00', uncredited_minutes: 105, net_hours: 3.25 }, 105),
  c('K3', K, '12:30', '14:30', { start_time: '12:30', end_time: '14:30', uncredited_minutes: 120 }, 120),
  c('K4', K, '08:00', '12:05', { start_time: '08:00', end_time: '12:05', net_hours: 4.08 }, 0),
  c('K5', K, '08:00', '12:30', { start_time: '08:00', end_time: '12:30', uncredited_minutes: 15, net_hours: 4.25 }, 15),
  c('K6', K6, '08:00', '16:00', { start_time: '08:00', end_time: '16:00', net_hours: 8 }, 0),
  c('K7', K, '07:00', '19:00', {
    start_time: '07:45', end_time: '18:15', raw_start_time: '07:00', raw_end_time: '19:00',
    uncredited_minutes: 150, net_hours: 8,
  }, 240),
  c('K8', K, '05:00', '07:00', {
    start_time: '05:00', end_time: '05:00', raw_start_time: '05:00', raw_end_time: '07:00',
  }, 120),
  c('K9', K, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', break_minutes: 30, uncredited_minutes: 150, net_hours: 7 }, 150),
  c('K10', K, '08:00', '18:00', DAY_10H_P45, 0, true),
  c('K11', [], '08:00', '18:00', DAY_10H_P45, 0),
  c('K12', [], '08:00', '18:00', DAY_10H_P45, 0),
  c('K13', [], '08:00', '18:00', DAY_10H_P45, 0),
  c('K14', K, '08:00', null, { start_time: '08:00', end_time: null }, 0),
  c('K15', K, '08:00', '23:59', {
    start_time: '08:00', end_time: '18:15', raw_end_time: '23:59', uncredited_minutes: 150,
    auto_closed: true, net_hours: 7.75,
  }, 150),
  c('K16', K, '14:30', '18:00', { start_time: '14:30', end_time: '18:00', uncredited_minutes: 15, net_hours: 3.25 }, 15),
  c('K17', K17, '07:00', '19:00', { start_time: '07:00', end_time: '19:00', uncredited_minutes: 180, net_hours: 9 }, 180),
  c('K18', K, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', uncredited_minutes: 150, net_hours: 7.5 }, 150),
  c('K19', K19, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', uncredited_minutes: 270, net_hours: 5.5 }, 270),
  c('K20', K, '07:00', '18:00', {
    start_time: '07:45', end_time: '18:00', raw_start_time: '07:00', uncredited_minutes: 150, net_hours: 7.75,
  }, 195),
  c('K21', K, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', break_minutes: 45, uncredited_minutes: 150, net_hours: 6.75 }, 150),
];
```

- [ ] **Step 2: Failing tests anhängen**

An `frontend/src/utils/workBlocks.test.ts` anhängen:

```ts
import {
  blocksSpan, gapSegments, hhmmToMinutes, isInBlockGap, notCreditedMinutes, stampNoteProps,
} from './workBlocks';
import { K_CASES_FE } from './workBlocksCases';

describe('notCreditedMinutes — Zwilling von not_credited_minutes (Spec 6.3, P19)', () => {
  it.each(K_CASES_FE.map((k) => [k.id, k] as const))('%s', (_id, k) => {
    expect(notCreditedMinutes(k.stored)).toBe(k.notCredited);
  });
});

describe('gapSegments — Zwilling von gap_segments (Σ = uncredited_minutes)', () => {
  const closed = K_CASES_FE.filter((k) => k.end !== null && !k.creditOverride);
  it.each(closed.map((k) => [k.id, k] as const))('%s', (_id, k) => {
    const sum = gapSegments(k.dayBlocks, 15, k.start, k.end!).reduce((a, b) => a + b, 0);
    expect(sum).toBe(k.stored.uncredited_minutes);
  });

  it('liefert die Segmente je Lücke (K17)', () => {
    const k17 = K_CASES_FE.find((k) => k.id === 'K17')!;
    expect(gapSegments(k17.dayBlocks, 15, '07:00', '19:00')).toEqual([30, 150]);
  });

  it('eine Lücke ≤ 2 × Puffer verschwindet (K6)', () => {
    const k6 = K_CASES_FE.find((k) => k.id === 'K6')!;
    expect(gapSegments(k6.dayBlocks, 15, '08:00', '16:00')).toEqual([]);
  });

  it('akzeptiert Zeiten mit Sekunden aus der API', () => {
    const k1 = K_CASES_FE.find((k) => k.id === 'K1')!;
    expect(gapSegments(k1.dayBlocks, 15, '08:00:00', '18:00:00')).toEqual([150]);
  });
});

describe('isInBlockGap — ungeschrumpfte Lücke (Spec 14, E69)', () => {
  const B = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];
  it.each([
    ['07:30', false], ['11:59', false], ['12:00', true], ['12:05', true],
    ['13:00', true], ['14:59', true], ['15:00', false], ['18:30', false],
  ] as const)('%s → %s', (t, expected) => {
    expect(isInBlockGap(B, hhmmToMinutes(t))).toBe(expected);
  });

  it('ohne zweiten Block gibt es keine Lücke', () => {
    expect(isInBlockGap([{ start: '08:00', end: '16:00' }], hhmmToMinutes('12:00'))).toBe(false);
    expect(isInBlockGap(undefined, 600)).toBe(false);
  });
});

describe('blocksSpan', () => {
  it('erster Beginn bis letztes Ende', () => {
    expect(blocksSpan([{ start: '15:00', end: '18:00' }, { start: '08:00', end: '12:00' }]))
      .toEqual({ start: '08:00', end: '18:00' });
    expect(blocksSpan([])).toBeNull();
  });
});

describe('stampNoteProps', () => {
  it('baut Roh- und angerechnete Spanne (K7) und nimmt den Serverwert, wenn vorhanden', () => {
    const k7 = K_CASES_FE.find((k) => k.id === 'K7')!;
    const props = stampNoteProps(k7.stored);
    expect(props).toMatchObject({
      rawSpan: '07:00–19:00', effSpan: '07:45–18:15', uncreditedMinutes: 150,
      notCreditedMinutes: 240, creditedHours: 8, breakMinutes: 0, autoClosed: false, creditOverride: false,
    });
    expect(stampNoteProps({ ...k7.stored, not_credited_minutes: 241 }).notCreditedMinutes).toBe(241);
  });
});
```

An `frontend/src/utils/arbzgWarnings.test.ts` anhängen:

```ts
describe('Spec 2026-10-08, 8.3/8.4: weiche Anwesenheits-Codes', () => {
  it.each([
    'PRESENCE_DAILY_HOURS: §3 ArbZG: Laut Stempel 12:00 h anwesend (abzüglich erfasster Pausen) – mehr als 10 Stunden.',
    'PRESENCE_BREAK: §4 ArbZG: Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – eine Ruhepause ist nicht erfasst (10:00 h Anwesenheit).',
    'PRESENCE_WEEKLY_HOURS: §3 ArbZG: Laut Stempel 50:00 h in dieser Woche anwesend (abzüglich erfasster Pausen) – mehr als 48 Stunden.',
    'BREAK_IN_GAP: Pause in der Lücke wird zusätzlich abgezogen: 30 Min Pause und 2:30 h nicht angerechnet zwischen den Arbeitsblöcken.',
  ])('reicht den Servertext durch: %s', (raw) => {
    const toast = mockToast();
    showArbzgWarnings(toast, [raw]);
    expect(toast.warning).toHaveBeenCalledWith(raw.slice(raw.indexOf(':') + 1).trim());
  });

  it.each(['PRESENCE_DAILY_HOURS', 'PRESENCE_BREAK', 'PRESENCE_WEEKLY_HOURS', 'BREAK_IN_GAP'])(
    'hat einen Rückfalltext ohne Servertext: %s', (code) => {
      const toast = mockToast();
      showArbzgWarnings(toast, [code]);
      const text = (toast.warning as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(text).not.toBe(code);
      expect(text.length).toBeGreaterThan(20);
    },
  );
});
```

An `frontend/src/utils/breakValidation.test.ts` anhängen:

```ts
describe('computeBreakError mit Lückensegmenten (Spec 8.2/8.4)', () => {
  it('eine Lücke ≥ 15 Min zählt als Pause (K1: 08–18 ohne Pause)', () => {
    expect(computeBreakError([], '08:00', '18:00', 0, false, [150])).toBeNull();
    expect(computeBreakError([], '08:00', '18:00', 0, false)).toMatch(/45 Min/);
  });

  it('ein Segment < 15 Min wird abgezogen, zählt aber nicht als Pause', () => {
    expect(computeBreakError([], '08:00', '17:00', 0, false, [10])).toMatch(/30 Min/);
  });

  it('Abzug und Pausenabschnitte bestehender Einträge zählen mit', () => {
    const existing = [{ start: 8 * 60, end: 18 * 60, brk: 0, deduct: 150, pauseSegments: [150] }];
    expect(computeBreakError(existing, '18:00', '18:30', 0, false)).toBeNull();
    const strict = [{ start: 8 * 60, end: 18 * 60, brk: 0, deduct: 100, pauseSegments: [] }];
    expect(computeBreakError(strict, '18:00', '18:30', 0, false)).toMatch(/30 Min/);
  });
});
```

- [ ] **Step 3: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/utils/workBlocks.test.ts src/utils/arbzgWarnings.test.ts src/utils/breakValidation.test.ts --pool=threads`
Expected: FAIL — `gapSegments`/`notCreditedMinutes` nicht exportiert; die vier Codes erscheinen roh; `computeBreakError` ignoriert die Segmente

- [ ] **Step 4: `utils/workBlocks.ts` erweitern**

Import ersetzen: `import type { WeekBlocks } from '../types/workBlocks';` → `import type { TimeBlock, WeekBlocks } from '../types/workBlocks';`. Am Dateiende:

```ts
const LAST_MINUTE = 23 * 60 + 59;

/** "HH:MM" bzw. "HH:MM:SS" → Minuten seit Mitternacht (Sekunden ignoriert, wie im Backend). */
export function hhmmToMinutes(value: string): number {
  const [h, m] = value.substring(0, 5).split(':').map(Number);
  return h * 60 + m;
}

function sortedMinutes(blocks: TimeBlock[]): [number, number][] {
  return blocks
    .map((b) => [hhmmToMinutes(b.start), hhmmToMinutes(b.end)] as [number, number])
    .sort((a, b) => a[0] - b[0]);
}

/**
 * Zwilling von `work_window_service.gap_segments` (Spec 6.1/8.4): die nicht
 * angerechneten Minuten je Lücke für einen Eintrag `start`–`end` an einem Tag
 * mit `blocks`. Beginn/Ende werden auf die Hülle (erster Block − Puffer, letzter
 * Block + Puffer) begrenzt; die Lücken schrumpfen an beiden Rändern um den
 * Puffer, eine Lücke ≤ 2 × Puffer verschwindet. Kollaps außerhalb der Hülle → [].
 */
export function gapSegments(
  blocks: TimeBlock[] | null | undefined, grace: number, start: string, end: string,
): number[] {
  if (!blocks || blocks.length === 0) return [];
  const mins = sortedMinutes(blocks);
  const floor = Math.max(0, Math.min(mins[0][0] - grace, LAST_MINUTE));
  const ceil = Math.max(0, Math.min(mins[mins.length - 1][1] + grace, LAST_MINUTE));
  const s = Math.max(hhmmToMinutes(start), floor);
  const e = Math.min(hhmmToMinutes(end), ceil);
  if (s >= e) return [];
  const out: number[] = [];
  for (let i = 0; i + 1 < mins.length; i++) {
    const gs = mins[i][1] + grace;
    const ge = mins[i + 1][0] - grace;
    if (ge <= gs) continue;
    const overlap = Math.min(e, ge) - Math.max(s, gs);
    if (overlap > 0) out.push(overlap);
  }
  return out;
}

/** Spec 14 / E69: liegt `minutes` in einer UNGESCHRUMPFTEN Lücke (Ende Block i
 * bis Beginn Block i+1)? Laut Plan beginnt die Pause am Blockende, nicht erst
 * nach dem Puffer — der geschrumpfte Wert gilt nur für die Anrechnung. */
export function isInBlockGap(blocks: TimeBlock[] | null | undefined, minutes: number): boolean {
  if (!blocks || blocks.length < 2) return false;
  const mins = sortedMinutes(blocks);
  for (let i = 0; i + 1 < mins.length; i++) {
    if (mins[i][1] <= minutes && minutes < mins[i + 1][0]) return true;
  }
  return false;
}

/** Erster Beginn bis letztes Ende (Vorbelegung neuer Einträge, Spec 14). */
export function blocksSpan(blocks: TimeBlock[] | null | undefined): { start: string; end: string } | null {
  if (!blocks || blocks.length === 0) return null;
  const mins = sortedMinutes(blocks);
  const toHHMM = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  return { start: toHHMM(mins[0][0]), end: toHHMM(Math.max(...mins.map(([, e]) => e))) };
}

export interface CreditEntry {
  start_time: string | null;
  end_time: string | null;
  raw_start_time?: string | null;
  raw_end_time?: string | null;
  uncredited_minutes?: number | null;
  auto_closed?: boolean | null;
}

/** Zwilling von `work_window_service.not_credited_minutes` (P19): Lücke +
 * von der Hülle gekappte Minuten; die Endseite eines automatisch geschlossenen
 * Eintrags zählt nicht (23:59 ist kein Stempel, P18). */
export function notCreditedMinutes(e: CreditEntry): number {
  let total = e.uncredited_minutes ?? 0;
  if (e.start_time && e.raw_start_time) {
    total += Math.max(0, hhmmToMinutes(e.start_time) - hhmmToMinutes(e.raw_start_time));
  }
  if (e.end_time && e.raw_end_time && !e.auto_closed) {
    total += Math.max(0, hhmmToMinutes(e.raw_end_time) - hhmmToMinutes(e.end_time));
  }
  return total;
}

export interface StampEntry extends CreditEntry {
  break_minutes?: number | null;
  net_hours?: number | null;
  not_credited_minutes?: number | null;
  credit_override?: boolean | null;
}

/** Spec 13.1: die Eingaben der Komponente `RawStampNote`. */
export interface StampNoteData {
  uncreditedMinutes: number;
  notCreditedMinutes: number;
  rawSpan: string;       // "08:00–18:00" aus raw_* oder start/end; offen: "07:00–"
  effSpan: string;       // gespeicherte start/end
  creditedHours: number; // net_hours (nach Pause und Lücke)
  breakMinutes: number;
  autoClosed: boolean;
  creditOverride: boolean;
}

export function stampNoteProps(e: StampEntry): StampNoteData {
  const hhmm = (t?: string | null) => (t ? t.substring(0, 5) : '');
  return {
    uncreditedMinutes: e.uncredited_minutes ?? 0,
    notCreditedMinutes: e.not_credited_minutes ?? notCreditedMinutes(e),
    rawSpan: `${hhmm(e.raw_start_time ?? e.start_time)}–${hhmm(e.raw_end_time ?? e.end_time)}`,
    effSpan: `${hhmm(e.start_time)}–${hhmm(e.end_time)}`,
    creditedHours: e.net_hours ?? 0,
    breakMinutes: e.break_minutes ?? 0,
    autoClosed: !!e.auto_closed,
    creditOverride: !!e.credit_override,
  };
}
```

- [ ] **Step 5: `arbzgWarnings.ts`**

Im `switch` vor `default:`:

```ts
      case 'PRESENCE_DAILY_HOURS':
        // Spec 2026-10-08, 8.3: weiche Warnung auf der Anwesenheit laut Stempel.
        toast.warning(detail ?? 'Laut Stempel mehr als 10 Stunden anwesend (§3 ArbZG) – angerechnet wird weniger.');
        break;
      case 'PRESENCE_BREAK':
        toast.warning(detail ?? 'Laut Stempel ohne ausreichende erfasste Ruhepause anwesend (§4 ArbZG).');
        break;
      case 'PRESENCE_WEEKLY_HOURS':
        toast.warning(detail ?? 'Laut Stempel mehr als 48 Stunden in dieser Woche anwesend (§3 ArbZG).');
        break;
      case 'BREAK_IN_GAP':
        // Spec 8.4: Pause und nicht angerechnete Lücke am selben Eintrag.
        toast.warning(detail ?? 'Pause in der Lücke wird zusätzlich abgezogen – lag die Pause in der Lücke, bitte die Pause auf 0 setzen.');
        break;
```

Den Kommentar am `case 'BREAK_WARNING':` ersetzen durch:

```ts
        // Seit #499 an allen Schreibwegen eine Sperre (mit Begründung kommt
        // BREAK_WAIVER). Einzige Quelle seither: „Anerkennen" (Spec 13.3, P4) —
        // dort ist §4 bewusst nur eine weiche Warnung.
```

- [ ] **Step 6: `breakValidation.ts`**

`BreakBlock` ersetzen durch:

```ts
/** A closed (start+end) working block on a single day, in minutes-since-midnight. */
export interface BreakBlock {
  start: number;
  end: number;
  /** Declared break minutes for this block. */
  brk: number;
  /** Spec 2026-10-08, 8.2: nicht angerechnete Lückenminuten — Abzug von der Bruttozeit. */
  deduct?: number;
  /** Spec 8.2: Lückensegmente; nur Segmente ≥ 15 Min zählen als Pausenabschnitt. */
  pauseSegments?: number[];
}
```

Signatur von `computeBreakError` um den sechsten Parameter erweitern (JSDoc ergänzen: `@param uncreditedSegments  gapSegments(...) des vorgeschlagenen Eintrags (Spec 8.4)`):

```ts
export function computeBreakError(
  existingBlocks: BreakBlock[],
  startTime: string,
  endTime: string,
  breakMinutes: number,
  exempt: boolean,
  uncreditedSegments: number[] = [],
): string | null {
```

Die Zeilen ab `const allBlocks: BreakBlock[] = [` bis einschließlich `const totalEffBreak = totalDeclared + totalGap;` ersetzen durch:

```ts
  const allBlocks: BreakBlock[] = [
    ...existingBlocks,
    {
      start, end, brk: breakMinutes,
      deduct: uncreditedSegments.reduce((s, x) => s + x, 0),
      pauseSegments: uncreditedSegments,
    },
  ];
  allBlocks.sort((a, b) => a.start - b.start);

  // §4 Satz 2: only break SEGMENTS of at least 15 min count toward the
  // mandatory break — declared breaks, gaps between entries and (Spec 8.2)
  // gap segments between work blocks alike.
  const totalDeclared = allBlocks.reduce((s, b) => s + (b.brk >= 15 ? b.brk : 0), 0);
  let totalGap = 0;
  for (let i = 1; i < allBlocks.length; i++) {
    const gap = allBlocks[i].start - allBlocks[i - 1].end;
    if (gap >= 15) totalGap += gap;
  }
  const totalSegments = allBlocks.reduce(
    (s, b) => s + (b.pauseSegments ?? []).filter((x) => x >= 15).reduce((a, x) => a + x, 0), 0,
  );
  // Nicht angerechnete Lückenminuten sind keine Arbeitszeit (Spec 8.2).
  const totalGross = allBlocks.reduce((s, b) => s + (b.end - b.start) - (b.deduct ?? 0), 0);
  const totalNet = totalGross - totalDeclared;
  const totalEffBreak = totalDeclared + totalGap + totalSegments;
```

- [ ] **Step 7: Tests, Typprüfung — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/utils/workBlocks.test.ts src/utils/arbzgWarnings.test.ts src/utils/breakValidation.test.ts --pool=threads && npx tsc --noEmit`
Expected: PASS, keine TypeScript-Fehler

- [ ] **Step 8: Commit**

```bash
git add frontend/src/utils/workBlocks.ts frontend/src/utils/workBlocksCases.ts frontend/src/utils/workBlocks.test.ts frontend/src/utils/arbzgWarnings.ts frontend/src/utils/arbzgWarnings.test.ts frontend/src/utils/breakValidation.ts frontend/src/utils/breakValidation.test.ts
git commit -F - <<'EOF'
feat(bloecke): Frontend-Zwillinge notCreditedMinutes/gapSegments, neue Warncodes, §4 mit Lücke (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 14: `RawStampNote` — eine Zeile „nicht angerechnet" je Eintrag

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#491 F4 hat `TimeTracking.tsx` angefasst; die Zeilen mit `<RawStampNote … side=…/>` und der Inline-Block der Mobilkarte sind die Anker.)

**Files:**
- Modify (komplett ersetzen): `frontend/src/components/RawStampNote.tsx`, `frontend/src/components/RawStampNote.test.tsx`
- Create: `frontend/src/pages/admin/EmployeeTimeEntryTable.tsx`, `frontend/src/pages/admin/EmployeeTimeEntryTable.test.tsx`
- Modify: `frontend/src/pages/TimeTracking.tsx` (Typ `TimeEntry`, Tabelle „Von"/„Bis", Mobilkarte)
- Modify: `frontend/src/components/MonthlyJournal.tsx` (Typ `TimeEntryItem`, Zeitspalte)
- Modify: `frontend/src/pages/admin/AdminDashboard.tsx` (Typ `TimeEntry`, Detailtabelle)
- Test: `frontend/src/pages/TimeTracking.test.tsx`, `frontend/src/components/MonthlyJournal.test.tsx` (anhängen)

**Interfaces:**
- Consumes: `stampNoteProps`, `StampEntry`, `StampNoteData` (Task 13); `formatHoursHM`, `formatClockTime` (`utils/formatters`); Antwortfelder aus Task 1/7
- Produces:
  - `RawStampNote(props: StampNoteData & { onRequestCredit?: () => void; className?: string })` — Wortlaute Spec 13.1; bei `creditOverride` das Kennzeichen „anerkannt"; Button „Anrechnung beantragen" nur mit `onRequestCredit` und `notCreditedMinutes > 0`
  - `EmployeeTimeEntryTable` (default export) mit `interface EmployeeTimeEntry extends StampEntry` und Props `{ entries, onEdit, onDelete }` (Task 15 ergänzt `onCredited`) — Spalten Datum · Von · Bis · Pause · **Netto** · Notiz · Aktionen

- [ ] **Step 1: Failing tests schreiben**

`frontend/src/components/RawStampNote.test.tsx` (komplett ersetzen):

```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RawStampNote } from './RawStampNote';
import { stampNoteProps } from '../utils/workBlocks';
import { K_CASES_FE } from '../utils/workBlocksCases';

function kNote(id: string, extra: { onRequestCredit?: () => void } = {}) {
  const k = K_CASES_FE.find((c) => c.id === id)!;
  return render(
    <RawStampNote {...stampNoteProps({ ...k.stored, credit_override: k.creditOverride })} {...extra} />,
  );
}

describe('RawStampNote — Spec 13.1 (PR2)', () => {
  it.each([
    ['K1', 'gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet'],
    ['K7', 'gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken'],
    ['K9', 'gestempelt 08:00–18:00 · angerechnet 7:00 h nach 0:30 h Pause · 2:30 h zwischen den Blöcken nicht angerechnet'],
    ['K15', 'eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 7:45 h (08:00–18:15) · 2:30 h zwischen den Blöcken nicht angerechnet'],
    ['K20', 'gestempelt 07:00–18:00 · angerechnet 7:45 h (07:45–18:00) · 3:15 h nicht angerechnet, davon 2:30 h zwischen den Blöcken'],
  ])('%s', (id, text) => {
    kNote(id);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('nur Hülle: Wortlaut je Seite unverändert (Handbuch und Cheat-Sheet zitieren ihn)', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '07:45:00', end_time: '17:15:00', raw_start_time: '07:37:00', raw_end_time: '18:20:00',
      break_minutes: 30, net_hours: 9, uncredited_minutes: 0,
    })} />);
    expect(screen.getByText('gestempelt 07:37 · angerechnet ab 07:45')).toBeInTheDocument();
    expect(screen.getByText('gestempelt 18:20 · angerechnet bis 17:15')).toBeInTheDocument();
  });

  it('Kollaps vor der Hülle (K8): nur die Endseite, wie bisher', () => {
    kNote('K8');
    expect(screen.getByText('gestempelt 07:00 · angerechnet bis 05:00')).toBeInTheDocument();
  });

  it('nichts gekappt (K4): keine Zeile', () => {
    const { container } = kNote('K4');
    expect(container).toBeEmptyDOMElement();
  });

  // Review Focus 2
  it('offener Eintrag mit Beginn vor der Hülle (K20 nach dem Einstempeln)', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '07:45:00', end_time: null, raw_start_time: '07:00:00',
      break_minutes: 0, net_hours: 0, uncredited_minutes: 0,
    })} />);
    expect(screen.getByText('gestempelt 07:00 · angerechnet ab 07:45')).toBeInTheDocument();
    expect(screen.queryByText(/angerechnet \d+:\d\d h/)).not.toBeInTheDocument();
  });

  it('automatisch geschlossen ohne Blöcke: „… um 23:59"', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '08:00:00', end_time: '23:59:00', break_minutes: 0, net_hours: 15.98,
      uncredited_minutes: 0, auto_closed: true,
    })} />);
    expect(screen.getByText('eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen um 23:59')).toBeInTheDocument();
  });

  it('anerkannt: Kennzeichen statt Kappungszeile', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '07:00:00', end_time: '19:00:00', break_minutes: 0, net_hours: 12,
      uncredited_minutes: 0, credit_override: true,
    })} />);
    expect(screen.getByText('anerkannt')).toBeInTheDocument();
    expect(screen.queryByText(/gestempelt/)).not.toBeInTheDocument();
  });

  it('„Anrechnung beantragen" nur mit onRequestCredit (Mitarbeiter-Ansicht, P21)', () => {
    const { unmount } = kNote('K1');
    expect(screen.queryByRole('button', { name: 'Anrechnung beantragen' })).not.toBeInTheDocument();
    unmount();
    const onRequestCredit = vi.fn();
    kNote('K1', { onRequestCredit });
    fireEvent.click(screen.getByRole('button', { name: 'Anrechnung beantragen' }));
    expect(onRequestCredit).toHaveBeenCalled();
  });
});
```

`frontend/src/pages/admin/EmployeeTimeEntryTable.test.tsx`:

```tsx
import { render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import EmployeeTimeEntryTable from './EmployeeTimeEntryTable';

vi.mock('../../api/client', () => ({ default: { post: vi.fn() } }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

const K7_ENTRY = {
  id: 'e1', date: '2026-06-01', start_time: '07:45:00', end_time: '18:15:00',
  raw_start_time: '07:00:00', raw_end_time: '19:00:00', break_minutes: 0, net_hours: 8, note: '',
  uncredited_minutes: 150, not_credited_minutes: 240, credit_override: false, auto_closed: false,
};

describe('<EmployeeTimeEntryTable /> (Spec 12.3: Netto-Spalte und RawStampNote)', () => {
  it('zeigt Netto und die Zeile „nicht angerechnet"', () => {
    render(<EmployeeTimeEntryTable entries={[K7_ENTRY]} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByRole('columnheader', { name: 'Netto' })).toBeInTheDocument();
    const row = screen.getAllByRole('row')[1];
    expect(within(row).getByText('8:00 h')).toBeInTheDocument();
    expect(within(row).getByText(/4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken/)).toBeInTheDocument();
  });
});
```

An `frontend/src/pages/TimeTracking.test.tsx` anhängen:

```tsx
describe('<TimeTracking /> RawStampNote (Spec 13.1)', () => {
  it('Tabelle und Mobilkarte nutzen dieselbe Komponente', async () => {
    mockEntries([{
      ...closedEntry, start_time: '07:45:00', raw_start_time: '07:37:00', not_credited_minutes: 8,
    }]);
    renderPage();
    expect(await screen.findAllByText('gestempelt 07:37 · angerechnet ab 07:45')).toHaveLength(2);
  });
});
```

An `frontend/src/components/MonthlyJournal.test.tsx` anhängen:

```tsx
const k7Entry = {
  id: 'te1', start_time: '07:45', end_time: '18:15', break_minutes: 0, net_hours: 8,
  raw_start_time: '07:00', raw_end_time: '19:00', uncredited_minutes: 150,
  not_credited_minutes: 240, credit_override: false, auto_closed: false,
};
const creditJournal = { ...validJournal, days: [{ ...validDay, time_entries: [k7Entry] }] };

describe('<MonthlyJournal /> nicht angerechnete Zeit (Spec 13.1, PR2)', () => {
  it('zeigt die Zeile „nicht angerechnet" am Eintrag', async () => {
    getMock.mockResolvedValue({ data: creditJournal });
    render(<MonthlyJournal userId="u1" isAdminView={false} />);
    expect(await screen.findByText(
      'gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken',
    )).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/components/RawStampNote.test.tsx src/pages/admin/EmployeeTimeEntryTable.test.tsx src/pages/TimeTracking.test.tsx src/components/MonthlyJournal.test.tsx --pool=threads`
Expected: FAIL — neue Props unbekannt (Texte fehlen), „Failed to resolve import ./EmployeeTimeEntryTable", Mobilkarte zeigt den Inline-Text nur einmal in anderer Form

- [ ] **Step 3: `RawStampNote.tsx` ersetzen**

```tsx
/**
 * Hinweiszeile zu einem gekappten bzw. nicht vollständig angerechneten
 * Zeiteintrag (#201/#462, Spec 2026-10-08 Abschnitt 13.1).
 *
 * DIE eine Quelle des Textes für Admin-Dashboard, Monatsjournal und
 * Zeiterfassung (Tabelle UND Mobilkarte). „angerechnet" ist immer `net_hours`
 * (nach Pause und Lücke), „nicht angerechnet" = Lücke + Hülle
 * (`not_credited_minutes`, P19). Der Hülle-Wortlaut „gestempelt 07:30 ·
 * angerechnet ab 07:45" wird in Handbuch und Cheat-Sheet wörtlich zitiert und
 * bleibt deshalb unverändert.
 */
import { formatHoursHM } from '../utils/formatters';
import type { StampNoteData } from '../utils/workBlocks';

interface RawStampNoteProps extends StampNoteData {
  /** P21: nur die Mitarbeiter-Ansicht übergibt das — Aktion „Anrechnung beantragen". */
  onRequestCredit?: () => void;
  className?: string;
}

function hm(minutes: number): string {
  return formatHoursHM(minutes / 60);
}

export function RawStampNote({
  uncreditedMinutes, notCreditedMinutes, rawSpan, effSpan, creditedHours, breakMinutes,
  autoClosed, creditOverride, onRequestCredit, className,
}: RawStampNoteProps) {
  const cls = className ?? 'text-xs text-gray-500 mt-0.5';
  if (creditOverride) {
    return (
      <div className={cls}>
        <span
          className="inline-flex items-center px-1.5 py-0.5 rounded-sm text-xs font-medium bg-gray-100 text-gray-600"
          title="Von der Verwaltung anerkannt – die gesamte gestempelte Zeit wird angerechnet"
        >
          anerkannt
        </span>
      </div>
    );
  }

  const [rawStart, rawEnd] = rawSpan.split('–');
  const [effStart, effEnd] = effSpan.split('–');
  const credited = `angerechnet ${formatHoursHM(creditedHours)} h${breakMinutes > 0 ? ` nach ${hm(breakMinutes)} h Pause` : ''}`;
  const lines: string[] = [];

  if (autoClosed) {
    const base = `eingestempelt ${rawStart}, nicht ausgestempelt – automatisch geschlossen`;
    if (rawEnd === effEnd) {
      lines.push(`${base} um ${effEnd}`);   // ohne Blöcke: 23:59 ungekappt
    } else {
      lines.push(
        `${base} · ${credited} (${effSpan})`
        + (uncreditedMinutes > 0 ? ` · ${hm(uncreditedMinutes)} h zwischen den Blöcken nicht angerechnet` : ''),
      );
    }
  } else if (!effEnd) {
    // offener Eintrag: nur die Hülle des Beginns (P17, K20 nach dem Einstempeln)
    if (rawStart && rawStart !== effStart) lines.push(`gestempelt ${rawStart} · angerechnet ab ${effStart}`);
  } else if (notCreditedMinutes > 0) {
    if (uncreditedMinutes === 0) {
      if (rawStart !== effStart) lines.push(`gestempelt ${rawStart} · angerechnet ab ${effStart}`);
      if (rawEnd !== effEnd) lines.push(`gestempelt ${rawEnd} · angerechnet bis ${effEnd}`);
    } else if (uncreditedMinutes === notCreditedMinutes) {
      lines.push(`gestempelt ${rawSpan} · ${credited} · ${hm(uncreditedMinutes)} h zwischen den Blöcken nicht angerechnet`);
    } else {
      lines.push(
        `gestempelt ${rawSpan} · ${credited} (${effSpan}) · ${hm(notCreditedMinutes)} h nicht angerechnet, `
        + `davon ${hm(uncreditedMinutes)} h zwischen den Blöcken`,
      );
    }
  }

  const offer = !!onRequestCredit && notCreditedMinutes > 0;
  if (lines.length === 0 && !offer) return null;
  return (
    <div className={cls}>
      {lines.map((line) => <div key={line}>{line}</div>)}
      {offer && (
        <button
          type="button"
          onClick={onRequestCredit}
          className="mt-0.5 text-amber-700 underline hover:text-amber-900"
        >
          Anrechnung beantragen
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: `EmployeeTimeEntryTable.tsx` anlegen**

```tsx
import { format } from 'date-fns';
import { Edit2, Trash2 } from 'lucide-react';
import { RawStampNote } from '../../components/RawStampNote';
import { formatClockTime, formatHoursHM } from '../../utils/formatters';
import { stampNoteProps, type StampEntry } from '../../utils/workBlocks';

/**
 * Detailtabelle der Zeiteinträge im Admin-Dashboard (Spec 2026-10-08, 12.3):
 * Netto-Spalte und die Zeile „nicht angerechnet" (RawStampNote). Aus
 * AdminDashboard.tsx herausgelöst, damit sie für sich testbar ist.
 */
export interface EmployeeTimeEntry extends StampEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string | null; // #382: null bei offenem Eintrag — Deref nur über formatClockTime
  break_minutes: number;
  net_hours: number;
  note?: string;
}

interface EmployeeTimeEntryTableProps {
  entries: EmployeeTimeEntry[];
  onEdit: (entry: EmployeeTimeEntry) => void;
  onDelete: (entryId: string) => void;
}

export default function EmployeeTimeEntryTable({ entries, onEdit, onDelete }: EmployeeTimeEntryTableProps) {
  return (
    <table className="w-full">
      <thead className="bg-gray-50 sticky top-0">
        <tr>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Datum</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Von</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Bis</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Pause</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Netto</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Notiz</th>
          <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">Aktionen</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-200">
        {entries.map((entry) => (
          <tr key={entry.id} className="hover:bg-gray-50 align-top">
            <td className="px-4 py-2 text-sm">{format(new Date(entry.date), 'dd.MM.yyyy')}</td>
            <td className="px-4 py-2 text-sm">
              {formatClockTime(entry.start_time)}
              <RawStampNote {...stampNoteProps(entry)} />
            </td>
            <td className="px-4 py-2 text-sm">{formatClockTime(entry.end_time, 'offen')}</td>
            <td className="px-4 py-2 text-sm">{entry.break_minutes} min</td>
            <td className="px-4 py-2 text-sm">{formatHoursHM(entry.net_hours)} h</td>
            <td className="px-4 py-2 text-sm text-gray-500">{entry.note || '-'}</td>
            <td className="px-4 py-2 text-right text-sm space-x-1">
              <button
                onClick={() => onEdit(entry)}
                className="text-primary hover:text-primary-dark p-1 rounded-sm"
                aria-label={`Eintrag vom ${format(new Date(entry.date), 'dd.MM.yyyy')} bearbeiten`}
              >
                <Edit2 size={14} aria-hidden="true" />
              </button>
              <button
                onClick={() => onDelete(entry.id)}
                className="text-red-600 hover:text-red-800 p-1 rounded-sm"
                aria-label={`Eintrag vom ${format(new Date(entry.date), 'dd.MM.yyyy')} löschen`}
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 5: `AdminDashboard.tsx` umstellen**

Import `import { RawStampNote } from '../../components/RawStampNote';` ersetzen durch:

```tsx
import EmployeeTimeEntryTable, { type EmployeeTimeEntry } from './EmployeeTimeEntryTable';
```

Das lokale `interface TimeEntry { … }` (mit `raw_start_time`/`raw_end_time`) ersetzen durch:

```tsx
// Spec 2026-10-08 (12.3): Felder inkl. nicht angerechneter Zeit — eine Quelle
// mit der herausgelösten Detailtabelle.
type TimeEntry = EmployeeTimeEntry;
```

Im Detail-Modal den gesamten Block `<table className="w-full"> … </table>` im Zweig `employeeTimeEntries.length === 0 ? (…) : (…)` ersetzen durch:

```tsx
                        <EmployeeTimeEntryTable
                          entries={employeeTimeEntries}
                          onEdit={handleAdminEditEntry}
                          onDelete={handleAdminDeleteEntry}
                        />
```

Danach unbenutzte Importe entfernen, die `npx tsc --noEmit` meldet (z. B. Icons, die nur in der alten Tabelle vorkamen — `Edit2`/`Trash2` nur dann, wenn sie sonst nirgends verwendet werden).

- [ ] **Step 6: `TimeTracking.tsx` umstellen**

Import ergänzen:

```tsx
import { stampNoteProps, type StampEntry } from '../utils/workBlocks';
```

`interface TimeEntry {` ersetzen durch `interface TimeEntry extends StampEntry {` und nach `raw_end_time?: string | null;` ergänzen:

```tsx
  // Spec 2026-10-08 (7.1, P19): nur lesend, vom Server abgeleitet.
  uncredited_minutes?: number;
  not_credited_minutes?: number;
  credit_override?: boolean;
  auto_closed?: boolean;
  clamp_grace_minutes?: number | null;
```

Tabelle — in der „Von"-Zelle die Zeile `<RawStampNote raw={entry.raw_start_time} effective={entry.start_time} side="start" />` ersetzen durch:

```tsx
                        <RawStampNote {...stampNoteProps(entry)} />
```

und in der „Bis"-Zelle die Zeile `<RawStampNote raw={entry.raw_end_time} effective={entry.end_time} side="end" />` ersatzlos löschen.

Mobilkarte — den Block `{(entry.raw_start_time || entry.raw_end_time) && ( <div className="text-xs text-gray-500 mb-2 space-y-0.5"> … </div> )}` ersetzen durch:

```tsx
                      <RawStampNote {...stampNoteProps(entry)} className="text-xs text-gray-500 mb-2 space-y-0.5" />
```

- [ ] **Step 7: `MonthlyJournal.tsx` umstellen**

Import ergänzen:

```tsx
import { stampNoteProps } from '../utils/workBlocks';
```

`interface TimeEntryItem` nach `sunday_exception_reason?: string | null; // #485 §10 ArbZG`:

```tsx
  // Spec 2026-10-08 (13.2): nicht angerechnete Zeit, Anerkennung, Auto-Close.
  uncredited_minutes?: number;
  not_credited_minutes?: number;
  credit_override?: boolean;
  auto_closed?: boolean;
```

In der Zeitspalte die beiden Zeilen

```tsx
                                  <RawStampNote raw={e.raw_start_time} effective={e.start_time} side="start" className="text-xs text-gray-500" />
                                  <RawStampNote raw={e.raw_end_time} effective={e.end_time} side="end" className="text-xs text-gray-500" />
```

ersetzen durch:

```tsx
                                  <RawStampNote {...stampNoteProps(e)} className="text-xs text-gray-500" />
```

- [ ] **Step 8: Tests, Typprüfung, Lint — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/components/RawStampNote.test.tsx src/pages/admin/EmployeeTimeEntryTable.test.tsx src/pages/TimeTracking.test.tsx src/components/MonthlyJournal.test.tsx src/pages/admin/AdminDashboard.test.tsx --pool=threads && npx tsc --noEmit && npx eslint src/components/RawStampNote.tsx src/pages/admin/EmployeeTimeEntryTable.tsx src/pages/admin/AdminDashboard.tsx src/pages/TimeTracking.tsx src/components/MonthlyJournal.tsx`
Expected: PASS, keine Fehler

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/RawStampNote.tsx frontend/src/components/RawStampNote.test.tsx frontend/src/pages/admin/EmployeeTimeEntryTable.tsx frontend/src/pages/admin/EmployeeTimeEntryTable.test.tsx frontend/src/pages/admin/AdminDashboard.tsx frontend/src/pages/TimeTracking.tsx frontend/src/pages/TimeTracking.test.tsx frontend/src/components/MonthlyJournal.tsx frontend/src/components/MonthlyJournal.test.tsx
git commit -F - <<'EOF'
feat(bloecke): RawStampNote mit Lücken-/Hüllenzeile, Netto-Spalte im Admin-Detail (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 15: „Anerkennen" in der Oberfläche und Journal-Summe

**Files:**
- Create: `frontend/src/components/CreditOverrideButton.tsx`, `frontend/src/components/CreditOverrideButton.test.tsx`
- Modify: `frontend/src/pages/admin/EmployeeTimeEntryTable.tsx` (Prop `onCredited`, Aktionszelle)
- Modify: `frontend/src/pages/admin/AdminDashboard.tsx` (`reloadEmployeeEntries`, Prop)
- Modify: `frontend/src/components/MonthlyJournal.tsx` (Import, Button in der Admin-Ansicht, Summenzeile)
- Test: `frontend/src/pages/admin/EmployeeTimeEntryTable.test.tsx`, `frontend/src/components/MonthlyJournal.test.tsx` (anhängen)

**Interfaces:**
- Consumes: `POST /api/admin/time-entries/{id}/credit-override` (Task 5); `notCreditedMinutes` (Task 13); `showArbzgWarnings`, `useConfirm`, `ConfirmDialog`
- Produces:
  - `CreditOverrideButton` (default export), Props `{ entry: CreditButtonEntry; onDone: () => void; className?: string }`; exportiert `AUTO_CLOSED_HINT` und `creditConfirmText(rawSpan: string): string` (Wortlaut Spec 13.3 UI); rendert nichts bei `credit_override`, offenem Eintrag oder `not_credited_minutes ≤ 0`; bei `auto_closed` deaktiviert mit Text
  - `EmployeeTimeEntryTable`-Prop `onCredited?: () => void`
  - Journal: Admin-Ansicht „Anerkennen" je Eintrag; Zusammenfassung „Anwesenheit nicht angerechnet: H:MM h" (nur > 0)

- [ ] **Step 1: Failing tests schreiben**

`frontend/src/components/CreditOverrideButton.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CreditOverrideButton, { AUTO_CLOSED_HINT } from './CreditOverrideButton';

const postMock = vi.fn();
vi.mock('../api/client', () => ({ default: { post: (...a: unknown[]) => postMock(...a) } }));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toast }));

const K7 = {
  id: 'e1', start_time: '07:45:00', end_time: '18:15:00', raw_start_time: '07:00:00',
  raw_end_time: '19:00:00', uncredited_minutes: 150, not_credited_minutes: 240,
  credit_override: false, auto_closed: false,
};

beforeEach(() => {
  postMock.mockReset();
  Object.values(toast).forEach((f) => f.mockReset());
});

describe('<CreditOverrideButton /> (Spec 13.3)', () => {
  it('bestätigt mit dem Wortlaut aus 13.3, ruft den Endpunkt und zeigt die weichen Warnungen', async () => {
    postMock.mockResolvedValue({ data: { warnings: ['DAILY_HOURS_HARD: Tagesarbeitszeit beträgt 12.0h …'] } });
    const onDone = vi.fn();
    render(<CreditOverrideButton entry={K7} onDone={onDone} />);
    fireEvent.click(screen.getByRole('button', { name: 'Anerkennen' }));
    expect(screen.getByText(/^Die gesamte gestempelte Zeit \(07:00–19:00\) wird angerechnet\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Zeit anerkennen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/admin/time-entries/e1/credit-override'));
    expect(onDone).toHaveBeenCalled();
    expect(toast.warning).toHaveBeenCalled();
  });

  it('ist bei automatisch geschlossenen Einträgen deaktiviert und nennt den Grund (P18)', () => {
    render(<CreditOverrideButton entry={{ ...K7, auto_closed: true }} onDone={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Anerkennen' })).toBeDisabled();
    expect(screen.getByText(AUTO_CLOSED_HINT)).toBeInTheDocument();
  });

  it('fehlt ohne nicht angerechnete Zeit, bei anerkannten und bei offenen Einträgen', () => {
    const { container, rerender } = render(
      <CreditOverrideButton entry={{ ...K7, not_credited_minutes: 0, uncredited_minutes: 0, raw_start_time: null, raw_end_time: null }} onDone={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(<CreditOverrideButton entry={{ ...K7, credit_override: true }} onDone={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<CreditOverrideButton entry={{ ...K7, end_time: null }} onDone={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

An `frontend/src/pages/admin/EmployeeTimeEntryTable.test.tsx` anhängen:

```tsx
describe('<EmployeeTimeEntryTable /> Anerkennen', () => {
  it('zeigt „Anerkennen" nur mit onCredited', () => {
    const { unmount } = render(<EmployeeTimeEntryTable entries={[K7_ENTRY]} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Anerkennen' })).not.toBeInTheDocument();
    unmount();
    render(<EmployeeTimeEntryTable entries={[K7_ENTRY]} onEdit={vi.fn()} onDelete={vi.fn()} onCredited={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Anerkennen' })).toBeInTheDocument();
  });
});
```

An `frontend/src/components/MonthlyJournal.test.tsx` anhängen:

```tsx
describe('<MonthlyJournal /> Anerkennen und Monatssumme (Spec 13.2/13.3)', () => {
  const withTotal = (total: number) => ({
    ...creditJournal,
    monthly_summary: { ...creditJournal.monthly_summary, not_credited_minutes_total: total },
  });

  it('Admin-Ansicht: „Anerkennen" am Eintrag und die Summenzeile', async () => {
    getMock.mockResolvedValue({ data: withTotal(450) });
    render(<MonthlyJournal userId="u1" isAdminView />);
    expect(await screen.findByRole('button', { name: 'Anerkennen' })).toBeInTheDocument();
    expect(screen.getByText('Anwesenheit nicht angerechnet: 7:30 h')).toBeInTheDocument();
  });

  it('Mitarbeiter-Ansicht: kein „Anerkennen"; ohne nicht angerechnete Zeit keine Summenzeile', async () => {
    getMock.mockResolvedValue({ data: withTotal(0) });
    render(<MonthlyJournal userId="u1" isAdminView={false} />);
    await screen.findByText(/gestempelt 07:00–19:00/);
    expect(screen.queryByRole('button', { name: 'Anerkennen' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Anwesenheit nicht angerechnet/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/components/CreditOverrideButton.test.tsx src/pages/admin/EmployeeTimeEntryTable.test.tsx src/components/MonthlyJournal.test.tsx --pool=threads`
Expected: FAIL — „Failed to resolve import ./CreditOverrideButton"

- [ ] **Step 3: `CreditOverrideButton.tsx` anlegen**

```tsx
import { useState } from 'react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../hooks/useConfirm';
import ConfirmDialog from './ConfirmDialog';
import { getErrorMessage } from '../utils/errorMessage';
import { showArbzgWarnings } from '../utils/arbzgWarnings';
import { notCreditedMinutes, type CreditEntry } from '../utils/workBlocks';

/**
 * Spec 2026-10-08, 13.3 „Anerkennen": die gesamte gestempelte Zeit eines
 * Eintrags anrechnen — dauerhaft, protokolliert. Eine Komponente für
 * Admin-Dashboard und Monatsjournal (Admin-Ansicht).
 */
export const AUTO_CLOSED_HINT = 'Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen.';

export function creditConfirmText(rawSpan: string): string {
  return (
    `Die gesamte gestempelte Zeit (${rawSpan}) wird angerechnet. Sie bleibt angerechnet — auch bei `
    + 'späteren Neuberechnungen und wenn die Verwaltung die Zeiten ändert; Mitarbeitende können den '
    + 'Eintrag danach nur noch per Änderungsantrag ändern. Wurde nur ein Teil der Zeit gearbeitet, den '
    + 'Eintrag besser aufteilen oder korrigieren. Der Vorgang wird protokolliert.'
  );
}

interface CreditButtonEntry extends CreditEntry {
  id: string;
  not_credited_minutes?: number | null;
  credit_override?: boolean | null;
}

interface CreditOverrideButtonProps {
  entry: CreditButtonEntry;
  onDone: () => void;
  className?: string;
}

export default function CreditOverrideButton({ entry, onDone, className }: CreditOverrideButtonProps) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [busy, setBusy] = useState(false);

  const notCredited = entry.not_credited_minutes ?? notCreditedMinutes(entry);
  if (entry.credit_override || !entry.end_time || notCredited <= 0) return null;

  const hhmm = (t?: string | null) => (t ? t.substring(0, 5) : '');
  const rawSpan = `${hhmm(entry.raw_start_time ?? entry.start_time)}–${hhmm(entry.raw_end_time ?? entry.end_time)}`;

  const run = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await apiClient.post(`/admin/time-entries/${entry.id}/credit-override`);
      toast.success('Zeit anerkannt');
      // P4: §3/§4/48 h und Anwesenheit kommen nur als weiche Warnung zurück.
      showArbzgWarnings(toast, res.data?.warnings);
      onDone();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Anerkennen fehlgeschlagen'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <button
        type="button"
        disabled={!!entry.auto_closed || busy}
        title={entry.auto_closed ? AUTO_CLOSED_HINT : 'Nicht angerechnete Zeit anerkennen'}
        onClick={() => confirm({
          title: 'Nicht angerechnete Zeit anerkennen',
          message: creditConfirmText(rawSpan),
          confirmLabel: 'Zeit anerkennen',
          variant: 'warning',
          onConfirm: () => { void run(); },
        })}
        className={className ?? 'text-xs px-2 py-0.5 rounded-sm border border-amber-300 text-amber-800 hover:bg-amber-50 disabled:opacity-50 disabled:cursor-not-allowed'}
      >
        Anerkennen
      </button>
      {entry.auto_closed && <span className="block text-xs text-gray-500">{AUTO_CLOSED_HINT}</span>}
    </>
  );
}
```

- [ ] **Step 4: Detailtabelle und Admin-Dashboard**

In `EmployeeTimeEntryTable.tsx` Import ergänzen:

```tsx
import CreditOverrideButton from '../../components/CreditOverrideButton';
```

Props erweitern:

```tsx
interface EmployeeTimeEntryTableProps {
  entries: EmployeeTimeEntry[];
  onEdit: (entry: EmployeeTimeEntry) => void;
  onDelete: (entryId: string) => void;
  /** Spec 13.3: „Anerkennen" — nach Erfolg lädt der Aufrufer neu. */
  onCredited?: () => void;
}

export default function EmployeeTimeEntryTable({ entries, onEdit, onDelete, onCredited }: EmployeeTimeEntryTableProps) {
```

In der Aktionszelle vor dem Bearbeiten-Button:

```tsx
              {onCredited && <CreditOverrideButton entry={entry} onDone={onCredited} />}
```

In `AdminDashboard.tsx` direkt vor `const handleAdminDeleteEntry`:

```tsx
  // Spec 13.3: nach „Anerkennen" Einträge, Protokoll und Monatsbericht neu laden.
  const reloadEmployeeEntries = async () => {
    if (!selectedEmployee) return;
    const entriesResponse = await apiClient.get('/time-entries', {
      params: { user_id: selectedEmployee.user_id, month: currentMonth },
    });
    setEmployeeTimeEntries(Array.isArray(entriesResponse.data) ? entriesResponse.data : []); // #382
    fetchAuditForUser(selectedEmployee.user_id);
    fetchReport();
  };
```

und am `<EmployeeTimeEntryTable …/>` aus Task 14 die Prop ergänzen:

```tsx
                          onCredited={() => { void reloadEmployeeEntries(); }}
```

- [ ] **Step 5: Monatsjournal**

In `MonthlyJournal.tsx` Importe ergänzen bzw. ersetzen:

```tsx
import { formatHoursHM, formatHoursHMText, parseHours } from '../utils/formatters';
import CreditOverrideButton from './CreditOverrideButton';
```

`interface JournalData` — `monthly_summary` ersetzen durch:

```tsx
  monthly_summary: { actual_hours: number; target_hours: number; balance: number; not_credited_minutes_total?: number };
```

In der Zeitspalte direkt nach `<RawStampNote {...stampNoteProps(e)} className="text-xs text-gray-500" />`:

```tsx
                                  {isAdminView && (
                                    <CreditOverrideButton entry={e} onDone={() => setReloadKey((k) => k + 1)} />
                                  )}
```

Direkt nach dem schließenden `</div>` des Kachel-Rasters `{/* Aggregates */}` (nach der Kachel „Überstunden (kumuliert)"):

```tsx
          {(data.monthly_summary.not_credited_minutes_total ?? 0) > 0 && (
            <p className="text-sm text-gray-600 mt-3">
              {`Anwesenheit nicht angerechnet: ${formatHoursHM((data.monthly_summary.not_credited_minutes_total ?? 0) / 60)} h`}
            </p>
          )}
```

- [ ] **Step 6: Tests, Typprüfung, Lint — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/components/CreditOverrideButton.test.tsx src/pages/admin/EmployeeTimeEntryTable.test.tsx src/components/MonthlyJournal.test.tsx src/pages/admin/AdminDashboard.test.tsx --pool=threads && npx tsc --noEmit && npx eslint src/components/CreditOverrideButton.tsx src/components/MonthlyJournal.tsx src/pages/admin/AdminDashboard.tsx src/pages/admin/EmployeeTimeEntryTable.tsx`
Expected: PASS, keine Fehler

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/CreditOverrideButton.tsx frontend/src/components/CreditOverrideButton.test.tsx frontend/src/pages/admin/EmployeeTimeEntryTable.tsx frontend/src/pages/admin/EmployeeTimeEntryTable.test.tsx frontend/src/pages/admin/AdminDashboard.tsx frontend/src/components/MonthlyJournal.tsx frontend/src/components/MonthlyJournal.test.tsx
git commit -F - <<'EOF'
feat(bloecke): „Anerkennen" im Admin-Dashboard und Journal, Journal-Summe nicht angerechnet (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 16: „Anrechnung beantragen" in der Oberfläche und Antragsprüfung

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#491 F4 hat `ChangeRequestForm.tsx` und `TimeTracking.tsx` um den §10-Grund erweitert — `useSundayOrHoliday`, `sundayReason`. Die Anker unten liegen außerhalb dieser Blöcke.)

**Files:**
- Modify: `frontend/src/components/ChangeRequestForm.tsx` (Typ, Props, Vorbelegung, Prüfung, Payload, Titel, Hinweis)
- Modify: `frontend/src/pages/TimeTracking.tsx` (State, `openChangeRequest`, `creditRequestFor`, Aufrufe, P3-Bedingung)
- Modify: `frontend/src/components/MonthlyJournal.tsx` (Import, State, Aufruf, Modal)
- Modify: `frontend/src/pages/admin/ChangeRequests.tsx` (Typ, `handleApprove`, Kennzeichen, Hinweis, Knöpfe)
- Test: `frontend/src/components/ChangeRequestForm.test.tsx`, `frontend/src/pages/TimeTracking.test.tsx`, `frontend/src/components/MonthlyJournal.test.tsx`, `frontend/src/pages/admin/ChangeRequests.test.tsx` (anhängen)

**Interfaces:**
- Consumes: `ChangeRequestCreate.request_credit_override`, `ChangeRequestReview.grant_credit_override`, Antwortfelder `request_credit_override`, `original_uncredited_minutes`, `entry_credit_override`, `entry_not_credited_minutes` (Task 6); `RawStampNote`-Prop `onRequestCredit` (Task 14)
- Produces:
  - `ChangeRequestForm`-Prop `requestCredit?: boolean` — Titel „Änderungsantrag: Anrechnung beantragen", Vorbelegung mit den Rohstempeln, bei `auto_closed` leeres „Bis" (Pflicht, nicht 23:59), Payload `request_credit_override: true`
  - Zeiterfassung und Monatsjournal (Mitarbeiter-Ansicht): Aktion „Anrechnung beantragen" an eigenen, geschlossenen, nicht anerkannten Einträgen **vergangener** Tage mit nicht angerechneter Zeit; anerkannte Einträge: kein direktes Bearbeiten für Mitarbeitende, stattdessen Antrag (P3)
  - Antragsprüfung: Kennzeichen „Anrechnung beantragt"; Knopf „Genehmigen und anerkennen" (Antragswert) bzw. „Ohne Anerkennen genehmigen" (`grant_credit_override: false`); bei gewöhnlichen UPDATE-Anträgen auf Einträge mit nicht angerechneter Zeit zusätzlich „Genehmigen und anerkennen" (`grant_credit_override: true`); Hinweis P3 bei anerkanntem Zieleintrag; Zeile „Nicht angerechnet (Lücke): H:MM h" aus `original_uncredited_minutes`

- [ ] **Step 1: Failing tests anhängen**

An `frontend/src/components/ChangeRequestForm.test.tsx`:

```tsx
describe('ChangeRequestForm — Anrechnung beantragen (Spec P21)', () => {
  const K7 = {
    id: 'te1', date: '2026-06-01', start_time: '07:45:00', end_time: '18:15:00',
    raw_start_time: '07:00:00', raw_end_time: '19:00:00', break_minutes: 0,
  };

  it('belegt die Rohstempel vor und sendet das Kennzeichen', async () => {
    const onSuccess = vi.fn();
    render(<ChangeRequestForm entry={K7} requestType="update" requestCredit onClose={vi.fn()} onSuccess={onSuccess} />);
    expect(screen.getByRole('heading', { name: 'Änderungsantrag: Anrechnung beantragen' })).toBeInTheDocument();
    expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('07:00');
    expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('19:00');
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith('/change-requests', expect.objectContaining({
      request_type: 'update', time_entry_id: 'te1', proposed_start_time: '07:00',
      proposed_end_time: '19:00', request_credit_override: true,
    }));
  });

  it('verlangt bei einem automatisch geschlossenen Eintrag das tatsächliche Ende (P18)', async () => {
    render(<ChangeRequestForm
      entry={{ ...K7, start_time: '08:00:00', raw_start_time: null, raw_end_time: '23:59:00', auto_closed: true }}
      requestType="update" requestCredit onClose={vi.fn()} onSuccess={vi.fn()} />);
    expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('');
    submitWithReason();
    expect(await screen.findByText('Der Eintrag wurde automatisch geschlossen – bitte das tatsächliche Ende angeben.')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('ein gewöhnlicher Änderungsantrag sendet kein Kennzeichen', async () => {
    const onSuccess = vi.fn();
    render(<ChangeRequestForm entry={K7} requestType="update" onClose={vi.fn()} onSuccess={onSuccess} />);
    expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('07:45');
    submitWithReason();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).not.toHaveProperty('request_credit_override');
  });
});
```

An `frontend/src/pages/TimeTracking.test.tsx`:

```tsx
describe('<TimeTracking /> Anrechnung beantragen und anerkannte Einträge (Spec P21, P3)', () => {
  const past = {
    ...closedEntry, id: 'te-past', date: '2026-06-01', is_editable: false,
    start_time: '07:45:00', end_time: '18:15:00', raw_start_time: '07:00:00', raw_end_time: '19:00:00',
    break_minutes: 0, net_hours: 8, uncredited_minutes: 150, not_credited_minutes: 240,
    credit_override: false, auto_closed: false,
  };

  it('öffnet an einem vergangenen Eintrag den Antrag mit den Rohstempeln', async () => {
    mockEntries([past]);
    renderPage();
    const [button] = await screen.findAllByRole('button', { name: 'Anrechnung beantragen' });
    fireEvent.click(button);
    expect(await screen.findByRole('heading', { name: 'Änderungsantrag: Anrechnung beantragen' })).toBeInTheDocument();
    expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('07:00');
  });

  it('heutige Einträge bieten die Aktion nicht an (Anträge nur für vergangene Tage)', async () => {
    mockEntries([{ ...past, date: today, is_editable: true }]);
    renderPage();
    await screen.findAllByText(/4:00 h nicht angerechnet/);
    expect(screen.queryByRole('button', { name: 'Anrechnung beantragen' })).not.toBeInTheDocument();
  });

  it('anerkannter Eintrag: kein direktes Bearbeiten, nur Antrag', async () => {
    mockEntries([{ ...closedEntry, credit_override: true }]);
    renderPage();
    await screen.findAllByLabelText(/Änderungsantrag für/);
    expect(screen.queryByLabelText(/bearbeiten/i)).not.toBeInTheDocument();
  });
});
```

An `frontend/src/components/MonthlyJournal.test.tsx`:

```tsx
describe('<MonthlyJournal /> Anrechnung beantragen (Spec P21)', () => {
  it('Mitarbeiter-Ansicht: öffnet den Antrag mit den Rohstempeln', async () => {
    getMock.mockImplementation((url: string) =>
      String(url).startsWith('/journal/me')
        ? Promise.resolve({ data: creditJournal })
        : Promise.resolve({ data: [] }));
    render(<MonthlyJournal userId="u1" isAdminView={false} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Anrechnung beantragen' }));
    expect(await screen.findByRole('heading', { name: 'Änderungsantrag: Anrechnung beantragen' })).toBeInTheDocument();
    expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('07:00');
  });
});
```

An `frontend/src/pages/admin/ChangeRequests.test.tsx`:

```tsx
describe('<AdminChangeRequests /> Anrechnung beantragen (Spec P21, P3)', () => {
  const creditCr = {
    ...pendingCr, id: 'cr2', request_type: 'update', time_entry_id: 'te1',
    original_date: '2026-06-01', original_start_time: '07:45:00', original_end_time: '18:15:00',
    original_break_minutes: 0, proposed_date: '2026-06-01', proposed_start_time: '07:00:00',
    proposed_end_time: '19:00:00', request_credit_override: true, original_uncredited_minutes: 150,
    entry_credit_override: false, entry_not_credited_minutes: 240,
  };

  it('kennzeichnet den Antrag und genehmigt mit Anerkennen (Antragswert)', async () => {
    mockApi([creditCr]);
    postMock.mockResolvedValue({ data: { warnings: [] } });
    render(<AdminChangeRequests />);
    expect(await screen.findByText('Anrechnung beantragt')).toBeInTheDocument();
    expect(screen.getByText('Nicht angerechnet (Lücke): 2:30 h')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Genehmigen und anerkennen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/admin/change-requests/cr2/review', { action: 'approve' }));
  });

  it('erlaubt, ohne Anerkennen zu genehmigen', async () => {
    mockApi([creditCr]);
    postMock.mockResolvedValue({ data: { warnings: [] } });
    render(<AdminChangeRequests />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ohne Anerkennen genehmigen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/admin/change-requests/cr2/review', { action: 'approve', grant_credit_override: false }));
  });

  it('bietet „Genehmigen und anerkennen" auch für gewöhnliche Änderungen mit nicht angerechneter Zeit', async () => {
    mockApi([{ ...creditCr, request_credit_override: false }]);
    postMock.mockResolvedValue({ data: { warnings: [] } });
    render(<AdminChangeRequests />);
    expect(await screen.findByRole('button', { name: 'Genehmigen' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Genehmigen und anerkennen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/admin/change-requests/cr2/review', { action: 'approve', grant_credit_override: true }));
  });

  it('zeigt bei einem anerkannten Zieleintrag den Hinweis aus P3', async () => {
    mockApi([{ ...creditCr, request_credit_override: false, entry_credit_override: true, entry_not_credited_minutes: 0 }]);
    render(<AdminChangeRequests />);
    expect(await screen.findByText('Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Genehmigen und anerkennen' })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/components/ChangeRequestForm.test.tsx src/pages/TimeTracking.test.tsx src/components/MonthlyJournal.test.tsx src/pages/admin/ChangeRequests.test.tsx --pool=threads`
Expected: FAIL — Titel „Anrechnung beantragen" fehlt, Knöpfe fehlen, „Anrechnung beantragen" wird in Zeiterfassung/Journal nicht angeboten

- [ ] **Step 3: `ChangeRequestForm.tsx`**

`interface TimeEntry` nach `sunday_exception_reason?: string | null;`:

```tsx
  // Spec 2026-10-08 P21: „Anrechnung beantragen" belegt die Rohstempel vor.
  raw_start_time?: string | null;
  raw_end_time?: string | null;
  auto_closed?: boolean | null;
```

`interface Props` nach `requestType: …;`:

```tsx
  /** Spec P21: „Anrechnung beantragen" — Zeiten = Rohstempel, Genehmigung = Anerkennen. */
  requestCredit?: boolean;
```

Signatur und Vorbelegung (die ersten Zeilen der Komponente) ersetzen durch:

```tsx
export default function ChangeRequestForm({ entry, requestType, requestCredit = false, onClose, onSuccess }: Props) {
  // P21: die gestempelten (Roh-)Zeiten vorbelegen. Ein automatisch geschlossener
  // Eintrag hat kein echtes Ende (P18) — das Feld bleibt leer und ist Pflicht.
  const creditStart = entry?.raw_start_time ?? entry?.start_time ?? null;
  const creditEnd = entry?.auto_closed ? '' : (entry?.raw_end_time ?? entry?.end_time ?? '');
  const [formData, setFormData] = useState({
    proposed_date: entry?.date || '',
    proposed_start_time: (requestCredit ? creditStart : entry?.start_time)?.substring(0, 5) || '08:00',
    proposed_end_time: requestCredit
      ? creditEnd.substring(0, 5)
      : entry?.end_time?.substring(0, 5) || '17:00',
    proposed_break_minutes: entry?.break_minutes ?? 0,
    proposed_note: entry?.note || '',
    reason: '',
  });
```

In `handleSubmit` direkt nach der Begründungsprüfung (`if (!formData.reason.trim()) { … }`):

```tsx
    if (requestCredit && entry?.auto_closed
        && (!formData.proposed_end_time || formData.proposed_end_time === '23:59')) {
      setError('Der Eintrag wurde automatisch geschlossen – bitte das tatsächliche Ende angeben.');
      return;
    }
```

Im Payload von `apiClient.post('/change-requests', {…})` nach `proposed_sunday_exception_reason: …,`:

```tsx
        ...(requestCredit ? { request_credit_override: true } : {}),
```

Titel `<h2 className="text-lg font-bold">Änderungsantrag: {typeLabels[requestType]}</h2>` ersetzen durch:

```tsx
          <h2 className="text-lg font-bold">Änderungsantrag: {requestCredit ? 'Anrechnung beantragen' : typeLabels[requestType]}</h2>
```

Direkt vor `{/* Proposed values form (for CREATE and UPDATE) */}`:

```tsx
          {requestCredit && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-900">
              Die gesamte gestempelte Zeit soll angerechnet werden. Bitte begründen Sie, warum Sie in dieser Zeit gearbeitet haben.
              {entry?.auto_closed && ' Der Eintrag wurde automatisch geschlossen – bitte das tatsächliche Ende angeben.'}
            </div>
          )}
```

- [ ] **Step 4: `TimeTracking.tsx`**

Nach `const [crType, setCrType] = useState<'create' | 'update' | 'delete'>('update');`:

```tsx
  const [crRequestCredit, setCrRequestCredit] = useState(false);  // Spec P21
```

`openChangeRequest` und `openCreateChangeRequest` ersetzen durch:

```tsx
  const openChangeRequest = (entry: TimeEntry, type: 'update' | 'delete', requestCredit = false) => {
    setCrEntry(entry);
    setCrType(type);
    setCrRequestCredit(requestCredit);
    setCrModalOpen(true);
  };

  const openCreateChangeRequest = () => {
    setCrEntry(null);
    setCrType('create');
    setCrRequestCredit(false);
    setCrModalOpen(true);
  };
```

Direkt nach `const isAdmin = user?.role === 'admin';`:

```tsx
  // Spec P21: Mitarbeitende beantragen die Anrechnung an eigenen, geschlossenen,
  // nicht anerkannten Einträgen vergangener Tage (Anträge gibt es nur dort).
  const creditRequestFor = (entry: TimeEntry) => (
    !isAdmin && !!entry.end_time && !entry.credit_override
      && entry.date < format(new Date(), 'yyyy-MM-dd')
      ? () => openChangeRequest(entry, 'update', true)
      : undefined
  );
  // P3: ein anerkannter Eintrag ist für Mitarbeitende nur per Antrag änderbar.
  const directlyEditable = (entry: TimeEntry) => entry.is_editable && !(entry.credit_override && !isAdmin);
```

Das Modal `<ChangeRequestForm entry={crEntry} requestType={crType} … />` ersetzen durch:

```tsx
        <ChangeRequestForm
          entry={crEntry}
          requestType={crType}
          requestCredit={crRequestCredit}
          onClose={() => setCrModalOpen(false)}
          onSuccess={() => {
            setCrModalOpen(false);
            toast.success(crRequestCredit ? 'Antrag auf Anrechnung eingereicht' : 'Änderungsantrag erfolgreich erstellt');
          }}
        />
```

Beide `RawStampNote`-Aufrufe aus Task 14 bekommen die Aktion — Tabelle:

```tsx
                        <RawStampNote {...stampNoteProps(entry)} onRequestCredit={creditRequestFor(entry)} />
```

Mobilkarte:

```tsx
                      <RawStampNote {...stampNoteProps(entry)} className="text-xs text-gray-500 mb-2 space-y-0.5" onRequestCredit={creditRequestFor(entry)} />
```

In der Tabelle `{entry.is_editable ? (` (Aktionszelle) und in der Mobilkarte `{entry.is_editable ? (` jeweils ersetzen durch:

```tsx
                        {directlyEditable(entry) ? (
```

- [ ] **Step 5: `MonthlyJournal.tsx`**

Import ergänzen:

```tsx
import ChangeRequestForm from './ChangeRequestForm';
```

Nach `const [reloadKey, setReloadKey] = useState(0);`:

```tsx
  // Spec P21: „Anrechnung beantragen" aus der Mitarbeiter-Ansicht.
  const [creditRequest, setCreditRequest] = useState<{ day: JournalDay; entry: TimeEntryItem } | null>(null);
```

Den `RawStampNote`-Aufruf in der Zeitspalte (Task 14) ersetzen durch:

```tsx
                                  <RawStampNote
                                    {...stampNoteProps(e)}
                                    className="text-xs text-gray-500"
                                    onRequestCredit={
                                      !isAdminView && isPastDay(day.date) && e.end_time && !e.credit_override
                                        ? () => setCreditRequest({ day, entry: e })
                                        : undefined
                                    }
                                  />
```

Im Rückgabe-JSX direkt nach dem schließenden `/>` von `<ConfirmDialog … />`:

```tsx
      {creditRequest && (
        <ChangeRequestForm
          entry={{
            id: creditRequest.entry.id,
            date: creditRequest.day.date,
            start_time: creditRequest.entry.start_time ?? '',
            end_time: creditRequest.entry.end_time,
            break_minutes: creditRequest.entry.break_minutes,
            raw_start_time: creditRequest.entry.raw_start_time,
            raw_end_time: creditRequest.entry.raw_end_time,
            auto_closed: creditRequest.entry.auto_closed,
            sunday_exception_reason: creditRequest.entry.sunday_exception_reason,
          }}
          requestType="update"
          requestCredit
          onClose={() => setCreditRequest(null)}
          onSuccess={() => {
            setCreditRequest(null);
            toast.success('Antrag auf Anrechnung eingereicht');
            setReloadKey((k) => k + 1);
          }}
        />
      )}
```

- [ ] **Step 6: Antragsprüfung (`pages/admin/ChangeRequests.tsx`)**

`interface ChangeRequest` nach `original_absence_hours?: number;`:

```tsx
  // Spec 2026-10-08 P21/P28/P3
  request_credit_override?: boolean;
  original_uncredited_minutes?: number | null;
  entry_credit_override?: boolean;
  entry_not_credited_minutes?: number;
```

Import ergänzen:

```tsx
import { formatHoursHM } from '../../utils/formatters';
```

`handleApprove` — Signatur und POST ersetzen durch:

```tsx
  const handleApprove = async (id: string, grant?: boolean) => {
    if (actionLock.current) return;
    actionLock.current = true;
    try {
      // Spec P21: ohne `grant` gilt der Antragswert (request_credit_override).
      const response = await apiClient.post(`/admin/change-requests/${id}/review`, {
        action: 'approve',
        ...(grant === undefined ? {} : { grant_credit_override: grant }),
      });
```

(der Rest der Funktion bleibt).

Im Kartenkopf direkt nach `<span className="text-sm text-gray-600">{typeLabels[cr.request_type]}</span>`:

```tsx
                      {cr.request_credit_override && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium bg-amber-100 text-amber-800">
                          Anrechnung beantragt
                        </span>
                      )}
```

Im Kasten „Aktuell" (Zeiteintrag) nach `<p>Pause: <span className="font-medium">{cr.original_break_minutes} min</span></p>`:

```tsx
                            {(cr.original_uncredited_minutes ?? 0) > 0 && (
                              <p>{`Nicht angerechnet (Lücke): ${formatHoursHM((cr.original_uncredited_minutes ?? 0) / 60)} h`}</p>
                            )}
```

Direkt vor `{/* Reason */}`:

```tsx
                {cr.entry_kind !== 'absence' && cr.request_type === 'update' && cr.entry_credit_override && (
                  <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-700">
                    Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.
                  </div>
                )}
```

Den Knopfblock im Zweig ohne Ablehnung (`<div className="flex space-x-3"> … </div>`) ersetzen durch:

```tsx
                      <div className="flex flex-wrap gap-3">
                        {cr.request_credit_override ? (
                          <>
                            <button
                              onClick={() => handleApprove(cr.id)}
                              className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg transition"
                            >
                              <Check size={16} />
                              <span>Genehmigen und anerkennen</span>
                            </button>
                            <button
                              onClick={() => handleApprove(cr.id, false)}
                              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-lg transition"
                            >
                              Ohne Anerkennen genehmigen
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              onClick={() => handleApprove(cr.id)}
                              className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg transition"
                            >
                              <Check size={16} />
                              <span>Genehmigen</span>
                            </button>
                            {cr.entry_kind !== 'absence' && cr.request_type === 'update'
                              && !cr.entry_credit_override && (cr.entry_not_credited_minutes ?? 0) > 0 && (
                              <button
                                onClick={() => handleApprove(cr.id, true)}
                                className="px-4 py-2 bg-amber-100 hover:bg-amber-200 text-amber-800 text-sm rounded-lg transition"
                              >
                                Genehmigen und anerkennen
                              </button>
                            )}
                          </>
                        )}
                        <button
                          onClick={() => setRejectingId(cr.id)}
                          className="flex items-center space-x-2 px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 text-sm rounded-lg transition"
                        >
                          <X size={16} />
                          <span>Ablehnen</span>
                        </button>
                      </div>
```

- [ ] **Step 7: Tests, Typprüfung, Lint — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/components/ChangeRequestForm.test.tsx src/components/ChangeRequestForm.breakWaiver.test.tsx src/pages/TimeTracking.test.tsx src/components/MonthlyJournal.test.tsx src/pages/admin/ChangeRequests.test.tsx --pool=threads && npx tsc --noEmit && npx eslint src/components/ChangeRequestForm.tsx src/pages/TimeTracking.tsx src/components/MonthlyJournal.tsx src/pages/admin/ChangeRequests.tsx`
Expected: PASS, keine Fehler

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/ChangeRequestForm.tsx frontend/src/components/ChangeRequestForm.test.tsx frontend/src/pages/TimeTracking.tsx frontend/src/pages/TimeTracking.test.tsx frontend/src/components/MonthlyJournal.tsx frontend/src/components/MonthlyJournal.test.tsx frontend/src/pages/admin/ChangeRequests.tsx frontend/src/pages/admin/ChangeRequests.test.tsx
git commit -F - <<'EOF'
feat(bloecke): „Anrechnung beantragen" in Zeiterfassung/Journal, Antragsprüfung mit Anerkennen (P21, P3, PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 17: StampWidget, Zeiterfassung und Dashboard-Status mit den Blöcken von heute

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#493/#494/#500/#501 haben `Dashboard.tsx` umgebaut — Stempelkarte mit `today_net_minutes`/`today_target_hours`, `workedToday`; #499 hat den Ausstempel-Dialog im `StampWidget` umgebaut. Anker: `computeBreakError([], startHHMM, endHHMM, breakMinutes, false)` im StampWidget, `const shouldBeClockedIn = …` im Dashboard.)

**Files:**
- Modify: `frontend/src/components/StampWidget.tsx` (Typ `ClockStatus`, Vorprüfung)
- Modify: `frontend/src/pages/TimeTracking.tsx` (Clock-Status laden, Vorbelegung, §4-Vorprüfung, Pausen-Automatik)
- Modify: `frontend/src/pages/Dashboard.tsx` (Typ, Status in der Lücke)
- Test: `frontend/src/components/StampWidget.test.tsx`, `frontend/src/pages/TimeTracking.test.tsx`, `frontend/src/pages/Dashboard.test.tsx` (anhängen)

**Interfaces:**
- Consumes: `ClockStatusResponse.blocks_today`, `.grace_minutes` (Task 2); `gapSegments`, `isInBlockGap`, `blocksSpan`, `hhmmToMinutes` (Task 13); `computeBreakError(…, uncreditedSegments)` (Task 13)
- Produces:
  - StampWidget: keine Pausenabfrage, wenn eine Lücke zwischen den Blöcken §4 deckt (Spec 8.4)
  - Zeiterfassung: Von/Bis neuer Einträge aus den heutigen Blöcken vorbelegt (erster Beginn, letztes Ende); §4-Vorprüfung mit Lückensegmenten (bestehende Einträge mit ihrem Puffer, 8.2); die automatische 30-Minuten-Pause entfällt, wenn die Lücke §4 deckt (E45 — sonst Doppelabzug)
  - Dashboard: in einer ungeschrumpften Lücke statt Rot neutral „Pause zwischen den Arbeitsblöcken" (E69)

- [ ] **Step 1: Failing tests anhängen**

An `frontend/src/components/StampWidget.test.tsx`:

```tsx
describe('<StampWidget /> §4-Vorprüfung mit Lückensegmenten (Spec 8.4)', () => {
  const BLOCKS = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];

  function clockedInWithBlocks(blocks: unknown[]) {
    getMock.mockImplementation((url: string) =>
      url === '/time-entries/clock-status'
        ? Promise.resolve({ data: {
          is_clocked_in: true, current_entry: { id: 'te-open', start_time: '08:00:00' },
          elapsed_minutes: 600, blocks_today: blocks, grace_minutes: 15,
        } })
        : Promise.resolve({ data: {} }));
  }

  afterEach(() => {
    vi.useRealTimers();
  });

  it('verlangt keine Pause, wenn die Lücke zwischen den Blöcken §4 deckt', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-06-01T18:00:00'));
    clockedInWithBlocks(BLOCKS);
    postMock.mockResolvedValueOnce({ data: { warnings: [] } });
    await openBreakDialog();
    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/time-entries/clock-out', expect.objectContaining({ break_minutes: 0 })));
  });

  it('Kontrolle: ohne Blöcke greift die Vorprüfung wie bisher (10 h ohne Pause)', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-06-01T18:00:00'));
    clockedInWithBlocks([]);
    await openBreakDialog();
    fireEvent.click(screen.getByRole('button', { name: /Jetzt ausstempeln/ }));
    expect(await screen.findByText('Bei >9h Arbeitszeit sind mind. 45 Min. Pause erforderlich (ArbZG §4)')).toBeInTheDocument();
    expect(postMock).not.toHaveBeenCalled();
  });
});
```

(Fehlt `afterEach` im Import der Datei, die erste Zeile auf `import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';` erweitern.)

An `frontend/src/pages/TimeTracking.test.tsx`:

```tsx
describe('<TimeTracking /> Blöcke von heute (Spec 8.4, 14)', () => {
  const BLOCKS = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];

  function mockWithBlocks(entries: unknown[]) {
    getMock.mockImplementation((url: string) => {
      if (url === '/time-entries/clock-status') {
        return Promise.resolve({ data: { is_clocked_in: false, blocks_today: BLOCKS, grace_minutes: 15 } });
      }
      if (url.includes('/settings')) return Promise.resolve({ data: {} });
      if (url.includes('/time-entries')) return Promise.resolve({ data: entries });
      return Promise.resolve({ data: [] });
    });
  }

  it('belegt Von/Bis neuer Einträge aus den heutigen Blöcken vor', async () => {
    mockWithBlocks([]);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Neuer Eintrag/ }));
    await waitFor(() => expect((screen.getByLabelText('Von') as HTMLInputElement).value).toBe('08:00'));
    expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('18:00');
  });

  it('verlangt keine Pause und setzt keine automatische Pause, wenn die Lücke §4 deckt (E45)', async () => {
    mockWithBlocks([]);
    postMock.mockResolvedValue({ status: 201, data: { ...closedEntry, warnings: [] } });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Neuer Eintrag/ }));
    await waitFor(() => expect((screen.getByLabelText('Bis') as HTMLInputElement).value).toBe('18:00'));
    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).toMatchObject({ start_time: '08:00', end_time: '18:00', break_minutes: 0 });
  });
});
```

An `frontend/src/pages/Dashboard.test.tsx` (falls `afterEach` nicht importiert ist, im `vitest`-Import ergänzen):

```tsx
// Spec 2026-10-08, 14 / E69: eine geplante Pause zwischen zwei Arbeitsblöcken
// ist kein Fehlverhalten — die Stempelkarte wird dort nicht rot.
describe('Dashboard Stempelkarte in der Lücke zwischen den Arbeitsblöcken (Spec 14, E69)', () => {
  const BLOCKS = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];

  function at(iso: string) {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(iso));
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) =>
      url === '/time-entries/clock-status'
        ? Promise.resolve({ data: {
          is_clocked_in: false, elapsed_minutes: null, today_net_minutes: 0,
          today_target_hours: 7, blocks_today: BLOCKS, grace_minutes: 15,
        } })
        : base(url));
  }

  afterEach(() => {
    vi.useRealTimers();
  });

  it.each(['2026-06-01T12:00:00', '2026-06-01T12:05:00', '2026-06-01T13:00:00'])(
    'zeigt um %s neutral „Pause zwischen den Arbeitsblöcken"', async (iso) => {
      at(iso);
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      const card = await screen.findByRole('button', { name: 'Stempeluhr öffnen' });
      await waitFor(() => expect(within(card).getByText('Pause zwischen den Arbeitsblöcken')).toBeInTheDocument());
      expect(within(card).queryByText('Noch nicht eingestempelt')).not.toBeInTheDocument();
      expect(card.className).not.toMatch(/bg-danger/);
    },
  );

  it.each(['2026-06-01T15:00:00', '2026-06-01T07:30:00'])(
    'um %s (Blockbeginn bzw. vor dem ersten Block) bleibt das bisherige Verhalten', async (iso) => {
      at(iso);
      render(<MemoryRouter><Dashboard /></MemoryRouter>);
      const card = await screen.findByRole('button', { name: 'Stempeluhr öffnen' });
      await waitFor(() => expect(within(card).getByText('Noch nicht eingestempelt')).toBeInTheDocument());
    },
  );
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/components/StampWidget.test.tsx src/pages/TimeTracking.test.tsx src/pages/Dashboard.test.tsx --pool=threads`
Expected: FAIL — StampWidget zeigt die 45-Min-Meldung trotz Blöcken; Von/Bis bleiben 08:00/17:00 bzw. Zielstunden; Dashboard zeigt „Noch nicht eingestempelt"

- [ ] **Step 3: `StampWidget.tsx`**

Importe ergänzen:

```tsx
import { gapSegments } from '../utils/workBlocks';
import type { TimeBlock } from '../types/workBlocks';
```

`interface ClockStatus` nach `elapsed_minutes?: number | null;`:

```tsx
  // Spec 2026-10-08 (8.4): Blöcke von heute und der Puffer des Ausstempelns (E80).
  blocks_today?: TimeBlock[];
  grace_minutes?: number;
```

Die Zeile `const breakErr = computeBreakError([], startHHMM, endHHMM, breakMinutes, false);` ersetzen durch:

```tsx
      // Spec 8.4: eine Lücke zwischen den Arbeitsblöcken (Segment ≥ 15 Min) deckt
      // §4 — dann keine Pausenabfrage; der Server rechnet genauso (E43).
      const segs = gapSegments(status?.blocks_today ?? [], status?.grace_minutes ?? 15, startHHMM, endHHMM);
      const breakErr = computeBreakError([], startHHMM, endHHMM, breakMinutes, false, segs);
```

- [ ] **Step 4: `TimeTracking.tsx`**

Den Import aus Task 14 ersetzen durch:

```tsx
import { blocksSpan, gapSegments, hhmmToMinutes, stampNoteProps, type StampEntry } from '../utils/workBlocks';
import type { TimeBlock } from '../types/workBlocks';
```

Nach `const breakExceptionAllowed = useSystemStore((s) => s.isBreakExceptionAllowed());`:

```tsx
  // Spec 2026-10-08 (8.4, 14): Blöcke von heute und Puffer aus /clock-status —
  // für die §4-Vorprüfung (Lückensegmente) und die Vorbelegung neuer Einträge.
  // Ohne Antwort (oder fremde Form) bleibt alles wie bisher; der Server prüft ohnehin.
  const [clockInfo, setClockInfo] = useState<{ blocks: TimeBlock[]; grace: number }>({ blocks: [], grace: 15 });
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get('/time-entries/clock-status')
      .then((res) => {
        if (cancelled) return;
        const d = res.data;
        setClockInfo({
          blocks: Array.isArray(d?.blocks_today) ? d.blocks_today : [],
          grace: typeof d?.grace_minutes === 'number' ? d.grace_minutes : 15,
        });
      })
      .catch(() => { /* Vorprüfung ohne Blöcke */ });
    return () => { cancelled = true; };
  }, [stampVersion]);

  // Spec 14: Von/Bis neuer Einträge aus den heutigen Blöcken vorbelegen.
  useEffect(() => {
    const span = blocksSpan(clockInfo.blocks);
    if (!span || editingId) return;
    setFormData((f) => (f.date === format(new Date(), 'yyyy-MM-dd')
      ? { ...f, start_time: span.start, end_time: span.end }
      : f));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clockInfo.blocks]);
```

In `validateTimeEntry` den Block ab `const existingBlocks = sameDay.map((e) => ({` bis einschließlich des Aufrufs `const breakError = computeBreakError( … );` ersetzen durch:

```tsx
    // Spec 8.2/8.4: an heutigen Einträgen zählen Lückensegmente ≥ 15 Min als Pause
    // und nicht angerechnete Minuten nicht als Arbeitszeit — wie der Server.
    // Bestehende Einträge mit IHREM Puffer (E80); weicht Σ Segmente vom
    // gespeicherten Wert ab, zählt der gespeicherte als Abzug, nicht als Pause.
    const dayBlocks = formData.date === format(new Date(), 'yyyy-MM-dd') ? clockInfo.blocks : [];
    const existingBlocks = sameDay.map((e) => {
      const stored = e.uncredited_minutes ?? 0;
      const segs = e.credit_override
        ? []
        : gapSegments(dayBlocks, e.clamp_grace_minutes ?? clockInfo.grace, e.start_time, e.end_time!);
      const matches = segs.reduce((a, b) => a + b, 0) === stored;
      return {
        start: hhmmToMinutes(e.start_time),
        end: hhmmToMinutes(e.end_time!),
        brk: e.break_minutes,
        deduct: stored,
        pauseSegments: matches ? segs : [],
      };
    });
    const editing = editingId ? entries.find((x) => x.id === editingId) : undefined;
    const newSegs = editing?.credit_override
      ? []
      : gapSegments(dayBlocks, editing?.clamp_grace_minutes ?? clockInfo.grace, formData.start_time, formData.end_time);
    const breakError = computeBreakError(
      existingBlocks,
      formData.start_time,
      formData.end_time,
      formData.break_minutes,
      !!user?.exempt_from_arbzg,
      newSegs,
    );
```

In `handleSubmit` den Block „Smart break default" (`if (!editingId && submitData.break_minutes === 0) { … }`) ersetzen durch:

```tsx
    // Smart break default: auto-set 30 min when creating entry >6h with no break —
    // Spec 8.4 (E45): nicht, wenn eine Lücke zwischen den Arbeitsblöcken §4 schon
    // deckt (sonst würde die Pause zusätzlich zur Lücke abgezogen).
    if (!editingId && submitData.break_minutes === 0) {
      const gross = hhmmToMinutes(submitData.end_time) - hhmmToMinutes(submitData.start_time);
      const segs = submitData.date === format(new Date(), 'yyyy-MM-dd')
        ? gapSegments(clockInfo.blocks, clockInfo.grace, submitData.start_time, submitData.end_time)
        : [];
      const credited = gross - segs.reduce((a, b) => a + b, 0);
      const covered = segs.filter((s) => s >= 15).reduce((a, b) => a + b, 0);
      if (credited > 360 && covered < 30) {
        submitData = { ...submitData, break_minutes: 30 };
      }
    }
```

In `resetForm` die Vorbelegung ersetzen durch:

```tsx
    const today = format(new Date(), 'yyyy-MM-dd');
    const targetHours = getDailyTargetHours(user, today);
    const defaultEnd = targetHours > 0 ? addHoursToTime('08:00', targetHours) : '17:00';
    const span = blocksSpan(clockInfo.blocks);  // Spec 14
    setFormData({
      date: today,
      start_time: span?.start ?? '08:00',
      end_time: span?.end ?? defaultEnd,
      break_minutes: 0,
      note: '',
      sunday_exception_reason: '',
    });
```

- [ ] **Step 5: `Dashboard.tsx`**

Importe ergänzen:

```tsx
import { isInBlockGap } from '../utils/workBlocks';
import type { TimeBlock } from '../types/workBlocks';
```

Im `useState`-Typ von `clockStatus` nach `today_target_hours?: number; …`:

```tsx
    blocks_today?: TimeBlock[]; // Spec 2026-10-08 (14, E69)
```

In der Stempelkarte die Zeile `const shouldBeClockedIn = isWorkday && !isClockedIn && !workedToday;` ersetzen durch:

```tsx
        // Spec 14 / E69: in einer UNGESCHRUMPFTEN Lücke (Blockende bis nächster
        // Blockbeginn) ist eine Pause geplant — neutral statt rot.
        const nowDate = new Date();
        const inGap = !isClockedIn
          && isInBlockGap(clockStatus?.blocks_today, nowDate.getHours() * 60 + nowDate.getMinutes());
        const shouldBeClockedIn = isWorkday && !isClockedIn && !workedToday && !inGap;
```

und im Statustext die Kette

```tsx
                {isClockedIn && startDisplay
                  ? `Eingestempelt seit ${startDisplay}`
                  : shouldBeClockedIn
```

ersetzen durch:

```tsx
                {isClockedIn && startDisplay
                  ? `Eingestempelt seit ${startDisplay}`
                  : inGap
                  ? 'Pause zwischen den Arbeitsblöcken'
                  : shouldBeClockedIn
```

- [ ] **Step 6: Tests, Typprüfung, Lint — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/components/StampWidget.test.tsx src/pages/TimeTracking.test.tsx src/pages/Dashboard.test.tsx src/utils/breakValidation.test.ts --pool=threads && npx tsc --noEmit && npx eslint src/components/StampWidget.tsx src/pages/TimeTracking.tsx src/pages/Dashboard.tsx`
Expected: PASS, keine Fehler

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/StampWidget.tsx frontend/src/components/StampWidget.test.tsx frontend/src/pages/TimeTracking.tsx frontend/src/pages/TimeTracking.test.tsx frontend/src/pages/Dashboard.tsx frontend/src/pages/Dashboard.test.tsx
git commit -F - <<'EOF'
feat(bloecke): §4-Vorprüfung mit Lücke, Vorbelegung aus Blöcken, Dashboard neutral in der Lücke (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 18: Audit-Labels, Datenschutzseite, Puffer-Hinweis

**Files:**
- Create: `frontend/src/constants/auditSources.ts`, `frontend/src/constants/auditSources.test.ts`
- Modify: `frontend/src/pages/admin/AuditLog.tsx` (lokale `sourceLabels` durch Import ersetzen)
- Modify: `frontend/src/pages/Privacy.tsx` (Abschnitt 3 „Verarbeitete Datenkategorien")
- Modify: `frontend/src/pages/admin/Settings.tsx` (Abschnitt „Soll-Arbeitszeit-Fenster", Text)
- Test: `frontend/src/components/AuditValues.test.tsx`, `frontend/src/pages/admin/Settings.test.tsx` (anhängen), `frontend/src/pages/Privacy.test.tsx` (neu)

**Interfaces:**
- Consumes: —
- Produces:
  - `constants/auditSources.ts`: `AUDIT_SOURCE_LABELS: Record<string, string>` (bisherige acht Labels + `wh_reclamp: 'Neukappung (Arbeitszeit-Änderung)'`, `credit_override: 'Anrechnung anerkannt'`)
  - Datenschutzseite: Kategorie „Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause) und nicht angerechnete Zeit" mit dem Logik-Text aus Spec 14 (Art. 13 Abs. 2 lit. f DSGVO)
  - Einstellungen: Puffer-Text aus Spec 12.3 (Blockränder, Puffer je Eintrag, E79/E80)

- [ ] **Step 1: Failing tests schreiben**

`frontend/src/constants/auditSources.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { AUDIT_SOURCE_LABELS } from './auditSources';

describe('AUDIT_SOURCE_LABELS (Spec 2026-10-08, 10.3)', () => {
  it('kennt Neukappung und Anerkennen', () => {
    expect(AUDIT_SOURCE_LABELS.wh_reclamp).toBe('Neukappung (Arbeitszeit-Änderung)');
    expect(AUDIT_SOURCE_LABELS.credit_override).toBe('Anrechnung anerkannt');
  });

  it('behält die bisherigen Labels', () => {
    expect(AUDIT_SOURCE_LABELS.wh_change).toBe('Stundenänderung');
    expect(AUDIT_SOURCE_LABELS.manual).toBe('Admin');
    expect(AUDIT_SOURCE_LABELS.break_waiver).toBe('Pausen-Verzicht');
  });
});
```

An `frontend/src/components/AuditValues.test.tsx` anhängen:

```tsx
describe('AuditValues — Protokollzeilen der Anerkennung (Spec 10.3)', () => {
  it('zeigt die Notiz auch bei vorhandenem Von–Bis', () => {
    render(<AuditValues date="2026-06-01" start="07:00:00" end="19:00:00" breakMinutes={0}
      note="angerechnet 12:00 h — von der Verwaltung anerkannt" />);
    expect(screen.getByText('angerechnet 12:00 h — von der Verwaltung anerkannt')).toBeInTheDocument();
    expect(screen.getByText('07:00 - 19:00')).toBeInTheDocument();
  });
});
```

(Fehlt `render`/`screen` im Import der Datei, ergänzen.)

`frontend/src/pages/Privacy.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import Privacy from './Privacy';

describe('<Privacy /> Arbeitszeit-Blöcke (Spec 14, Art. 13 Abs. 2 lit. f DSGVO)', () => {
  it('nennt die Kategorie und beschreibt die Logik der Nichtanrechnung', () => {
    render(<MemoryRouter><Privacy /></MemoryRouter>);
    expect(screen.getByText('Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause) und nicht angerechnete Zeit:')).toBeInTheDocument();
    expect(screen.getByText(new RegExp(
      'Ihre Arbeitszeit wird in Blöcken hinterlegt\\. Gestempelte Zeit vor dem ersten Block, nach dem letzten Block '
      + 'und zwischen den Blöcken wird – abzüglich eines Puffers – automatisch nicht angerechnet; die Stempelzeiten '
      + 'bleiben gespeichert\\. Die Verwaltung kann nicht angerechnete Zeit anerkennen; Sie können die Anrechnung per '
      + 'Änderungsantrag beantragen\\.',
    ))).toBeInTheDocument();
  });
});
```

An `frontend/src/pages/admin/Settings.test.tsx` anhängen:

```tsx
describe('<Settings /> Puffer-Hinweis (Spec 2026-10-08, 12.3)', () => {
  it('nennt die Blockränder und dass Einträge ihren Puffer behalten', async () => {
    mockSettings([]);
    render(<Settings />);
    expect(await screen.findByText(
      /gilt an jedem Blockrand, auch zwischen zwei Blöcken; eine Lücke bis zum doppelten Puffer wird angerechnet/,
    )).toBeInTheDocument();
    expect(screen.getByText(/^Eine Änderung des Puffers wirkt auf neue Einträge\./)).toBeInTheDocument();
    expect(screen.getByText(
      /Bereits gespeicherte Einträge ändern sich durch das Speichern dieser Einstellung allein nicht\.$/,
    )).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/constants/auditSources.test.ts src/components/AuditValues.test.tsx src/pages/Privacy.test.tsx src/pages/admin/Settings.test.tsx --pool=threads`
Expected: FAIL — `auditSources` fehlt, Datenschutz- und Puffertexte fehlen (der AuditValues-Test ist bereits grün: Regressionsschutz für die Protokollzeile)

- [ ] **Step 3: Konstanten und Protokollseite**

`frontend/src/constants/auditSources.ts`:

```ts
// Oberflächen-Labels der Protokollquellen (`time_entry_audit_logs.source`).
// Spec 2026-10-08 (10.3): `wh_reclamp` (Neukappung einer Arbeitszeit-Änderung,
// ab PR3) und `credit_override` („Anerkennen") ergänzt. Unbekannte Quellen
// zeigt die Seite roh an.
export const AUDIT_SOURCE_LABELS: Record<string, string> = {
  manual: 'Admin',
  change_request: 'Antrag',
  import: 'Import',
  dsgvo: 'DSGVO',
  break_waiver: 'Pausen-Verzicht',
  vacation_request_cancel: 'Urlaub storniert',
  license_startup: 'Lizenz',
  wh_change: 'Stundenänderung',
  wh_reclamp: 'Neukappung (Arbeitszeit-Änderung)',
  credit_override: 'Anrechnung anerkannt',
};
```

In `frontend/src/pages/admin/AuditLog.tsx` den Block `const sourceLabels: Record<string, string> = { … };` vollständig löschen und bei den Importen ergänzen:

```tsx
import { AUDIT_SOURCE_LABELS as sourceLabels } from '../../constants/auditSources';
```

- [ ] **Step 4: Datenschutzseite**

In `frontend/src/pages/Privacy.tsx`, Abschnitt „3. Verarbeitete Datenkategorien", direkt nach dem Listenpunkt „Zeiterfassungsdaten":

```tsx
              <li className="flex gap-2">
                <span className="text-primary mt-1">•</span>
                <span>
                  <strong>Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause) und nicht angerechnete Zeit:</strong>{' '}
                  Ihre Arbeitszeit wird in Blöcken hinterlegt. Gestempelte Zeit vor dem ersten Block, nach dem letzten
                  Block und zwischen den Blöcken wird – abzüglich eines Puffers – automatisch nicht angerechnet; die
                  Stempelzeiten bleiben gespeichert. Die Verwaltung kann nicht angerechnete Zeit anerkennen; Sie können
                  die Anrechnung per Änderungsantrag beantragen.
                </span>
              </li>
```

- [ ] **Step 5: Puffer-Hinweis in den Einstellungen**

In `frontend/src/pages/admin/Settings.tsx`, Abschnitt `{/* Soll-Fenster-Puffer (#201) */}`, den Absatz

```tsx
        <p className="text-sm text-gray-500 mb-4">
          Anwesenheit vor oder nach dem Soll-Fenster zählt nur bis zu diesem Puffer zur Arbeitszeit.
          Stempel außerhalb des Puffers werden auf die Fenstergrenze gekürzt.
        </p>
```

ersetzen durch:

```tsx
        <p className="text-sm text-gray-500 mb-2">
          Anwesenheit vor dem ersten und nach dem letzten Arbeitszeit-Block zählt nur bis zu diesem Puffer zur
          Arbeitszeit; Stempel außerhalb werden auf diese Grenze gekürzt. Der Puffer gilt an jedem Blockrand, auch
          zwischen zwei Blöcken; eine Lücke bis zum doppelten Puffer wird angerechnet.
        </p>
        <p className="text-sm text-gray-500 mb-4">
          Eine Änderung des Puffers wirkt auf neue Einträge. Jeder gekappte Eintrag merkt sich seinen Puffer und behält
          ihn, auch wenn er später bearbeitet wird. Nur eine Arbeitszeit-Änderung mit Neuberechnung kappt die
          betroffenen Einträge mit dem dann gültigen Puffer neu; die Vorschau nennt ihn, und verliert dabei ein Eintrag
          angerechnete Zeit, gilt der Verkürzungsschutz. Einträge aus der Zeit vor Version 1.20.0 tragen keinen
          gespeicherten Puffer und werden bei einer Bearbeitung mit dem aktuellen Puffer gekappt. Bereits gespeicherte
          Einträge ändern sich durch das Speichern dieser Einstellung allein nicht.
        </p>
```

(Das Wort „Neuberechnung" bezieht sich auf PR3; PR2 wird nie allein released.)

- [ ] **Step 6: Tests, Typprüfung, Lint — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/constants/auditSources.test.ts src/components/AuditValues.test.tsx src/pages/Privacy.test.tsx src/pages/admin/Settings.test.tsx --pool=threads && npx tsc --noEmit && npx eslint src/constants/auditSources.ts src/pages/admin/AuditLog.tsx src/pages/Privacy.tsx src/pages/admin/Settings.tsx`
Expected: PASS, keine Fehler

- [ ] **Step 7: Commit**

```bash
git add frontend/src/constants/auditSources.ts frontend/src/constants/auditSources.test.ts frontend/src/pages/admin/AuditLog.tsx frontend/src/components/AuditValues.test.tsx frontend/src/pages/Privacy.tsx frontend/src/pages/Privacy.test.tsx frontend/src/pages/admin/Settings.tsx frontend/src/pages/admin/Settings.test.tsx
git commit -F - <<'EOF'
feat(bloecke): Audit-Labels Anerkennen/Neukappung, Datenschutz- und Puffer-Text (PR2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 19: Gesamtlauf

**Files:** keine (nur Prüfung; Funde werden im verursachenden Task-Bereich behoben und separat committet)

**Interfaces:**
- Consumes: alle Tasks 1–18
- Produces: Nachweis „PR2 grün" — SQLite-Vollsuite, PG-Suiten, Vitest-Vollsuite, `tsc`, ESLint, Vite-Build

- [ ] **Step 1: Backend-Vollsuite (SQLite)**

Run: `pgrep -af pytest; rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py`
Expected: PASS — keine neuen Fehlschläge gegenüber der Ausgangszahl vor Task 1

- [ ] **Step 2: Postgres-Suiten und Gesamt-CI**

Run: `bash scripts/local-ci.sh`
Expected: alle Stufen grün (Backend SQLite/Postgres inkl. `test_tenant_rls.py`, `test_concurrency.py`, `test_net_hours_parity_pg.py`, `test_073_migration_pg.py`, Vitest, `tsc`, ESLint, Vite-Build). Läuft die E2E-Stufe mit, vorher die Auth-Rate-Limits nach CLAUDE.md anheben (`LOGIN_RATE_LIMIT=10000/minute REFRESH_RATE_LIMIT=10000/minute`); hängt Vitest mit dem Fork-Pool, die Stufe mit `--pool=threads` fahren.

- [ ] **Step 3: Frontend separat (falls `local-ci.sh` die Stufe übersprungen hat)**

Run (aus `frontend/`): `npx vitest run --pool=threads && npx tsc --noEmit && npx eslint src && npm run build`
Expected: PASS

- [ ] **Step 4: Rückstände ausschließen**

```bash
grep -rn "calcNetHours\|side=\"start\"\|side=\"end\"" frontend/src
grep -rn "work_window_service.clamp_warning(None\|clamp_warning(raw_start" backend/app
```

Expected: keine Treffer (alte `RawStampNote`-Props und Client-Netto entfernt; PR1-Altaufrufe von `clamp_warning` kommen nicht zurück).

---

## Übergabe an PR3/PR4 — was PR2 bereitstellt

Die verbindlichen Signaturen stehen in den **Interfaces**-Blöcken der Tasks; diese Liste ist das Inhaltsverzeichnis dafür.

| Schnittstelle | Ort | Task |
|---|---|---|
| `credit_summary_text(entry) -> str` (Notiztext für `wh_reclamp`-Einzelzeilen in PR3) | `app/services/work_window_service.py` | 1 |
| `TimeEntryResponse.uncredited_minutes/credit_override/auto_closed/clamp_grace_minutes` + berechnet `not_credited_minutes` | `app/schemas/time_entry.py` | 1 |
| `ClockBlock`, `ClockStatusResponse.blocks_today/grace_minutes`, `_clock_blocks_and_grace(db, user, today, open_entry)` | Schema, `routers/time_entries.py` | 2 |
| `presence_service`: Codes, `DayPresence`, `credited_minutes`, `closed_entries`, `day_presence`, `daily_presence_warnings`, `weekly_presence_warning`, `break_in_gap_warning`, `presence_warnings` (PR3: `arbzg_findings` der Vorschau nutzt `day_presence`/`credited_minutes`) | `app/services/presence_service.py` | 3 |
| `K_CODES`, `K_HTTP_400` (Spalte „Meldung" der Falltabelle) | `tests/work_blocks_cases.py` | 4 |
| `credit_override_service`: `CREDIT_OVERRIDE_SOURCE`, `OPEN_ENTRY_DETAIL`, `AUTO_CLOSED_DETAIL`, `start_taken_detail`, `load_entry_locked`, `apply_credit_override`, `override_warnings`; Endpunkt `POST /api/admin/time-entries/{id}/credit-override` | Dienst, `routers/admin_time_entries.py` | 5 |
| `ChangeRequestCreate.request_credit_override`, `ChangeRequestReview.grant_credit_override`, `ChangeRequestResponse.request_credit_override/original_uncredited_minutes/entry_credit_override/entry_not_credited_minutes/entry_auto_closed`; `CREDIT_REQUEST_REJECTED_DETAIL`, `GRANT_ONLY_UPDATE_DETAIL` | Schemas, Router | 6 |
| `JournalTimeEntry.uncredited_minutes/not_credited_minutes/credit_override/auto_closed`, `JournalMonthlySummary.not_credited_minutes_total` | `schemas/journal.py`, `journal_service` | 7 |
| `NOT_CREDITED_HEADER`, `PDF_NOT_CREDITED_HEADER`, `DayCredit`, `day_credit_minutes(day_entries)` | `app/services/export_service.py` | 8 |
| `24-week-average`: `presence_hours`, `presence_average`, `presence_weeks` (je ISO-Kalenderwoche) | `routers/reports.py` | 9 |
| `GET /api/auth/me/work-schedule`, `work_schedule_service.build_my_work_schedule`, Schemas `MyWorkScheduleResponse` …; `MyWorkScheduleCard` | Backend, Frontend | 10 |
| Auskunftsfelder Art. 15/20 und §16-Notfallexport; Guard-Erlaubnisliste um drei Exportstellen erweitert | `lifecycle_service`, `auth`, `superadmin`, `tests/test_no_live_work_blocks_read.py` | 11 |
| `ImportedEntry.net_hours`; Anwesenheits-Hinweise in der XLS-Vorschau | `xls_import_service` | 12 |
| `hhmmToMinutes`, `gapSegments`, `isInBlockGap`, `blocksSpan`, `CreditEntry`, `notCreditedMinutes`, `StampEntry`, `StampNoteData`, `stampNoteProps`; `K_CASES_FE`; `computeBreakError(…, uncreditedSegments)`; vier neue `arbzgWarnings`-Codes | `frontend/src/utils/*` | 13 |
| `RawStampNote` (Spec-13.1-Props + `onRequestCredit`), `EmployeeTimeEntryTable` | `components/`, `pages/admin/` | 14 |
| `CreditOverrideButton`, `AUTO_CLOSED_HINT`, `creditConfirmText` | `components/` | 15 |
| `ChangeRequestForm`-Prop `requestCredit`; Antragsprüfung „Genehmigen und anerkennen" | Frontend | 16 |
| StampWidget/TimeTracking §4 mit Lücke, Vorbelegung, Dashboard „Pause zwischen den Arbeitsblöcken" | Frontend | 17 |
| `AUDIT_SOURCE_LABELS` (inkl. `wh_reclamp` für PR3) | `frontend/src/constants/auditSources.ts` | 18 |

**Offen für den Betreiber vor dem Merge (in den Tasks begründet):** (1) „davon … zwischen den Blöcken" auch bei Lücke = Gesamt (Task 1, folgt den Spec-Beispielen statt der Kurzregel); (2) keine zusätzliche Export-Spalte für den Lückenanteil, Zeilenregel im Handbuch einschränken (Task 8, Spec 15.1 „offen"); (3) §16-Notfallexport führt zusätzlich `work_blocks`/Verlaufs-`blocks` (Task 11, über 15.3 hinaus).
