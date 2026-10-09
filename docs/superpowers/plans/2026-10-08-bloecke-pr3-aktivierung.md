# Arbeitszeit-Blöcke PR3 „Aktivierung" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Arbeitszeit-Blöcke werden über den Dialog „Arbeitszeit & Wochenstunden" und das Anlegeformular erfassbar; eine Arbeitszeit-Änderung kappt bereits erfasste Einträge neu, zieht Abwesenheiten mit F1-Klemmung nach, protokolliert jede Neukappung und jede Änderung und verlangt bei einer rückwirkenden Verkürzung (Eintrag, Saldo oder Gutschrift) das Schutzpaket.

**Architecture:** Ein einziger Rechenpfad `wh_change_service.run_change` führt die Schritte 2–7 aus Spec 9.3 (offene Alteinträge schließen, Saldo/Tagessoll vorher, Änderung anwenden, `reclamp_time_entries`, `retarget_absence_hours` mit F1, Saldo nachher, Klassifikation nach 9.4/9.5) für Anlegen, Löschen und beide Vorschauen aus; der Router entscheidet nur noch über Sperre, Schutzpaket, Protokoll (`reclamp_audit`), Commit oder Rollback. Neue Blöcke werden im Schreibschema streng geprüft und beim Speichern in `hours_*`/`weekly_hours`/`work_days_per_week` materialisiert (`work_blocks_service.derive_targets`) — `calculation_service` liest Blöcke nie fürs Soll. Das Frontend bekommt einen Block-Editor, eine POST-Vorschau mit Auswirkungs-Box, den Verkürzungs-Kasten (Grundtypen, Haken, MiLoG) und einen Lösch-Dialog mit „auf vorherigen Stand zurücksetzen".

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, PostgreSQL 18 (SQLite in der Unit-Suite), React 18 + TypeScript + Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-08-arbeitszeit-bloecke-design.md` (verbindlich; Abschnitt 20 „PR3", Abschnitte 4, 9, 10, 11, 12, 14 (Dashboard-Hinweise), 15.2, 17.2/17.5–17.8 und alle „Entschieden 2026-10-08"-Punkte aus 19.1). Die Schnittstellen aus PR1 stehen in `docs/superpowers/plans/2026-10-08-bloecke-pr1-fundament.md` (Abschnitt „Übergabe an PR2/PR3") und werden hier mit exakt diesen Namen und Signaturen konsumiert.

## Global Constraints

- Voraussetzungen: PR1 und PR2 sind auf dem Ausführungsbranch gemergt (Spec 20: „PR3 nie ohne PR2 auf `master`"). Vor Task 1 einmal die volle SQLite-Suite, `npx vitest run --pool=threads` und die volle Playwright-Suite (mit erhöhten Auth-Rate-Limits, siehe Task 23 Step 4) fahren und die Ausgangszahlen notieren — „keine neuen Fehlschläge" bezieht sich auf diese Zahlen (die E2E-Zahl braucht erst der Gesamtlauf in Task 23).
- Release-Regel (Spec 20): 1.20.0 erst nach PR1–PR4; PR3 wird nicht allein released.
- Verhalten nach dem Merge (Spec 20): „Blöcke und Lückenkappung aktiv; rückwirkende Soll-Erhöhungen (auch reine Wochenstunden-Änderungen) nur noch mit Schutzpaket".
- **Verkürzung** (Spec 9.5, 19.1 Nr. 1) = mindestens eines von (a) ein Eintrag verliert angerechnete Zeit (inkl. offener Eintrag von heute nach der Knickstellen-Prüfung P1); (b) `saldo_delta_hours < 0` **oder** der Anteil eines abgeschlossenen Jahres < 0 **oder** `open_day_saldo_delta_hours < 0`; (c) die F1-Klemmung senkt eine Abwesenheits-Gutschrift stärker als das Tagessoll des Tages. Keine Toleranz: jede Senkung ab 0,01 h zählt. Gilt beim Anlegen **und** Löschen, auch für reine Wochenstunden-/Tagesplan-Änderungen.
- `earliest_lossless_date = max(heute, A + 1 Tag, C + 1 Tag, H)`; `null` + Text „Die Änderung liegt vollständig vor der Änderung ab ‹Datum›; nur rückwirkend mit Begründung oder abbrechen.", wenn der Wert die nächste Änderung erreicht (P25).
- Grundtypen (19.1 Nr. 7) — **eine** Konstante `REASON_TYPES` in `app/services/reclamp_audit.py`; Schlüssel und Notiz-Präfixe eingefroren:
  - `erfassungsfehler` → `[Erfassungsfehler korrigiert]` → „Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)"
  - `einvernehmlich` → `[Einvernehmlich vereinbart]` → „Mit der beschäftigten Person vereinbart"
  - `sonstiges` → `[Sonstiges]` → „Sonstiges"
- Hilfetext unter der Grund-Auswahl, wörtlich: „Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit."
- `retroactive_reason_text` 10–400 Zeichen (P15); Notiz + Begründung > 500 → 422 „Notiz und Begründung zusammen höchstens 500 Zeichen." (keine stille Kürzung).
- Fehlertexte 11.4 wörtlich (Klammern, Gedankenstrich „–", Datumsformat `TT.MM.JJJJ`); der Minus-Strich in Anzeigetexten ist U+2212 „−", in der Sammelzeile ASCII `+`/`-`.
- Protokoll: `source="wh_reclamp"` (10 Zeichen), Einzelzeile je **geändertem** Eintrag, **immer genau eine** Sammelzeile je Anlegen/Löschen (P20, auch ohne Einträge, auch zukunftsdatiert), `time_entry_id`/`old_date`/`new_date` der Sammelzeile NULL; alles per `db.add` (row_hash, #121), kein Bulk-UPDATE, keine neue gehashte Spalte. Abwesenheits-Rückrechnung weiter über `_log_wh_change_retarget` (`source="wh_change"`), Präfix „Arbeitszeit-Änderung" bzw. „Löschung der Arbeitszeit-Änderung".
- Vorschauen (`…/preview`, `…/delete-preview`) protokollieren nie, nehmen keine Ankersperre und rollen **immer** zurück; Body untypisiert, Eingabefehler als `blocked_reason`, nie 422.
- Ankersperre (E52/P5): `lock_user_row(db, tenant_id, user.id)` ist im Anlege- und Lösch-Endpunkt die erste Sperre, vor jedem Snapshot, `clamp` und jeder Zeilensperre.
- Massen-Neukappung: aktueller Mandanten-Puffer (`get_grace_minutes`), geschrieben in `clamp_grace_minutes` **jedes** geprüften Eintrags an einem geänderten Wochentag, auch ohne Zeitänderung (E47/E79/E80).
- Keine stille Obergrenze (E52): Vorschau, Antwort und Protokoll nennen alle Einträge.
- F-026: jede neue Abfrage auf mandantenbezogene Tabellen trägt `tenant_id == …` zusätzlich zu RLS.
- `uncredited_minutes`, `credit_override`, `auto_closed`, `clamp_grace_minutes` bleiben Nicht-Eingabefelder (E11/E79).
- Knopf „Arbeitszeit anpassen…", Dialogtitel „Arbeitszeit & Wochenstunden" (E58); die E2E-Regex `/Wochenstunden/i` muss weiter passen.
- Backend-Tests **nie** im geteilten Container. Befehl aus der Repo-Wurzel (vorher `rm -f backend/test.db backend/test.db-wal backend/test.db-shm`, nie zwei Läufe gleichzeitig):
  `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/<datei> -q -p no:cacheprovider`
  Volle SQLite-Suite: dieselbe Zeile mit `tests/ --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py --ignore=tests/test_073_migration_pg.py --ignore=tests/test_net_hours_parity_pg.py --ignore=tests/test_reclamp_concurrency.py` (vorher `pgrep -af pytest`).
- Postgres-Läufe gegen eine Wegwerf-PG18 auf eigenem Docker-Netz (Muster PR1 Task 14 Step 3); Verbindungs-URLs aus Teilen bauen (`S="postgres"; S="${S}ql://"`).
- Frontend (aus `frontend/`): `npx vitest run <datei> --pool=threads`, `npx tsc --noEmit`.
- Commits per `git commit -F - <<'EOF' … EOF`, letzte Zeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Issue-Lanes (#493/#494/#500/#501 Dashboard, #497/#498 Exporte, #499 Schreibpfade/§4, #496, #495, #491 F4): Tasks, die diese Stellen berühren, tragen **⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** — vor Beginn die genannten Anker per `grep` gegen den Ausführungsstand prüfen; maßgeblich sind die zitierten Anker, nicht Zeilennummern.

## Review Focus

1. **Unfertige Eingabe im Block-Editor** (leeres `<input type="time">`, Pause leer, `08:07`, Pause ≥ Σ): die Vorschau antwortet 200 mit `blocked_reason` im Wortlaut von 3.4, Speichern bleibt gesperrt — nie 422/500 beim Tippen. Tests: Task 10 (Backend), Task 17/18b (Frontend).
2. **Geteilte Stempel um die geplante Lücke** (08:00–12:40 und 14:20–18:00 an einem Tag mit Blöcken 08–12 + 15–18): beide Beginnzeiten bleiben, jeder Eintrag bekommt seine eigenen nicht angerechneten Minuten, keine Kollision. Test: Task 7.
3. **Wirkungsdatum an einem Samstag** (z. B. 01.08.2026): Wirkungsbereich beginnt dort, die folgenden Montage werden neu gekappt, `earliest_lossless_date` ist heute — kein Sonderfall bricht. Tests: Task 9 (Anlegen), Task 10 (Vorschau).
4. **„In Arbeitszeit-Blöcke umwandeln" mit Altwerten** (`07:37`, Platzhalter `23:59`): der Editor zeigt die Werte unverändert, meldet das 5-Minuten-Raster je Block und verlangt die Pause; Speichern bleibt gesperrt, bis korrigiert. Test: Task 18b.
5. **Tagessoll mit Rundung** (07:30–12:00 + 13:00–16:25 = 7:55 h → gespeichert 7,92 h): der Editor zeigt Minuten-genau „Tagessoll 7:55 h", der Server speichert 7,92, und der Dialog meldet danach keinen Scheinunterschied („Noch nichts zu speichern"). Tests: Task 16/17/18b.

## Dateistruktur

| Datei | Verantwortung | Task |
|---|---|---|
| `backend/app/services/work_blocks_service.py` | + `derive_targets`, `changed_weekdays`, `blocks_text`, `block_break_notices` | 1, 5 |
| `backend/app/schemas/validators.py` | + `validate_week_blocks` (strenge Regeln 3.4) | 1 |
| `backend/app/services/reclamp_audit.py` (neu) | `REASON_TYPES`, Notizen, Sammelzeile schreiben/lesen, Vertrags-Kurztext, Dashboard-Hinweise | 2, 15 |
| `backend/app/schemas/working_hours_change.py` | `TimeBlockIn`, `DayBlocksIn`, `WorkingHoursChangeCreate` (Blöcke, Schutzpaket, Rücksetzung), `WorkingHoursChangeDelete`, Vorschau-Felder 11.3 | 3 |
| `backend/app/schemas/user.py` | `UserCreate.work_blocks` + Ableitung | 4 |
| `backend/app/services/calculation_service.py` | `RetargetWindow.last_time_entry`, F1 in `retarget_absence_hours`, `absence_full_targets`, `ScheduleSegment.blocks`, `blocks_changed` | 6, 14 |
| `backend/app/services/work_window_service.py` | `ReclampChange/Skip/Result`, `reclamp_time_entries`, `credited_minutes_for`, `open_entry_loses` | 7 |
| `backend/app/services/wh_change_service.py` (neu) | Rechenpfad 9.3, Klassifikation 9.4/9.5, Fehlertexte, `reset_body` | 8 |
| `backend/app/routers/admin_users.py` | Anlegen/Vorschau/Löschen/delete-preview, Protokoll, PUT-Text | 9–11 |
| `backend/app/services/export_service.py`, `schemas/reports.py` | Berichtstext mit Blöcken (15.2) | 14 |
| `backend/app/routers/dashboard.py`, `schemas/reports.py` | `schedule_change_notices` | 15 |
| `backend/tests/wh_change_helpers.py` (neu) | gemeinsame Test-Bausteine (eingefrorenes „heute", Verlaufszeilen, Einträge) | 6 |
| `frontend/src/utils/workBlocks.ts` | + `parseHhmm`, `minutesToHm`, `sumBlocks`, `deriveTargets`, `validateWeekBlocks`, `formatBlocksText`, `emptyWeek` | 16 |
| `frontend/src/components/WorkBlocksEditor.tsx` (neu) | Block-Editor (Dialog + Anlegen) | 17 |
| `frontend/src/pages/admin/users/workingHoursTypes.ts`, `workingHoursTexts.ts` (neu) | Antworttypen, feste Texte | 16 |
| `frontend/src/pages/admin/users/WhImpactBox.tsx` (neu) | Auswirkungs-Box | 18a |
| `frontend/src/pages/admin/users/ShorteningChoice.tsx` (neu) | Verkürzungs-Kasten | 19 |
| `frontend/src/pages/admin/users/WhDeletePanel.tsx` (neu) | Löschen mit delete-preview/Rücksetzung | 20 |
| `frontend/src/pages/admin/users/WorkingHoursModal.tsx` | Dialog „Arbeitszeit & Wochenstunden" | 18b–20 |
| `frontend/src/pages/admin/users/UserForm.tsx`, `pages/admin/Users.tsx` | Anlegen mit Blöcken, Knopftexte | 21 |
| `frontend/src/components/ScheduleChangeNotices.tsx` (neu), `pages/Dashboard.tsx` | Dashboard-Hinweise | 15 |
| `frontend/src/utils/formatters.ts` | `formatWeeklyHoursChanges` mit Blöcken | 14 |
| `e2e/tests/admin/work-blocks.spec.ts` (neu), `e2e/tests/admin/user-management.spec.ts` | E2E | 22 |

**Außerhalb von PR3 (nicht anfassen):** `RawStampNote`, Journal-Summe, Export-Spalte „Nicht angerechnet", Anerkennen-Endpunkt, „Anrechnung beantragen", `PRESENCE_*`, Profilkarte „Meine Arbeitszeit" (`GET /api/auth/me/work-schedule`), Audit-Labels in `AuditLog.tsx`, Art.-15/20-Felder, `Settings.tsx`-Puffertext (alle PR2); Doku-Flächen, `DocViewer.tsx`, Handbücher, `CLAUDE.md`, Release-Notes (PR4).

**Von PR2 konsumiert:** `work_window_service.credit_summary_text(entry) -> str` (Spec 10.1/13.3, PR2 Task 1). PR2 ist Voraussetzung (Global Constraints); PR3 legt die Funktion nicht an und ändert ihren Wortlaut nicht — Task 2 prüft ihn nur in `TestCreditSummaryText` mit den PR2-Erwartungen.

---

### Task 1: Soll-Ableitung und strenge Blockvalidierung (Spec 3.4, 4.1, 9.1)

**Files:**
- Modify: `backend/app/services/work_blocks_service.py` (am Dateiende anhängen)
- Modify: `backend/app/schemas/validators.py` (Importe, neue Funktion am Dateiende)
- Test (neu): `backend/tests/test_derive_targets.py`, `backend/tests/test_work_blocks_validation.py`
- Test (erweitern): `backend/tests/test_work_blocks_service.py`

**Interfaces:**
- Consumes: `work_blocks_service.WEEKDAY_LABELS`, `hhmm_to_minutes`, `minutes_to_hhmm`, `ParsedWeek`, `is_legacy_week` (PR1 Task 1); `tests.work_blocks_fixtures.block_week`, `legacy_week`, `K_BLOCKS` (PR1 Task 1)
- Produces:
  - `work_blocks_service.HOURS_FIELDS: tuple[str, ...]` = `("hours_monday", …, "hours_friday")`
  - `work_blocks_service.derive_targets(week_blocks: list[dict]) -> dict` — Schlüssel `hours_monday…hours_friday` (Decimal, 0,01 HALF_EVEN), `weekly_hours` (Decimal), `work_days_per_week` (int), `use_daily_schedule` (`True`)
  - `work_blocks_service.changed_weekdays(old_blocks: Optional[tuple], new_blocks: Optional[tuple]) -> list[int]` (Schedule-Format, ohne Pause verglichen)
  - `work_blocks_service.blocks_text(blocks: tuple, pauses: Optional[tuple], *, compact: bool) -> str` — lang `Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00`, kurz `Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00`
  - `app.schemas.validators.validate_week_blocks(value) -> list[dict]` — wirft `ValueError` mit dem deutschen Text der ersten verletzten Regel; nimmt Dicts oder Pydantic-Modelle (`model_dump`), liefert die kanonische JSON-Woche

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_derive_targets.py`:

```python
"""Spec 4.1: Tagessoll aus NEUEN Blöcken — DIE eine Ableitung (derive_targets)."""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import TimeEntry, WorkingHoursChange
from app.services import calculation_service, work_blocks_service as wbs
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import block_week


@pytest.mark.parametrize("day, pause, expected", [
    ([("08:00", "12:00"), ("15:00", "18:00")], 30, Decimal("6.50")),
    ([("08:00", "12:05")], 0, Decimal("4.08")),                       # 4,0833…
    ([("07:30", "12:00"), ("13:00", "16:25")], 0, Decimal("7.92")),   # 7,9166…
])
def test_table_4_1(day, pause, expected):
    derived = wbs.derive_targets(block_week(pause=pause, mon=day))
    assert derived["hours_monday"] == expected
    assert derived["hours_tuesday"] == Decimal("0.00")
    assert derived["weekly_hours"] == expected
    assert derived["work_days_per_week"] == 1
    assert derived["use_daily_schedule"] is True


def test_week_sum_and_work_days():
    week = block_week(mon=[("08:00", "12:00")], tue=[("08:00", "13:00")], thu=[("08:00", "12:00")])
    derived = wbs.derive_targets(week)
    assert derived["weekly_hours"] == Decimal("13.00")
    assert derived["work_days_per_week"] == 3
    assert derived["hours_wednesday"] == Decimal("0.00")


def test_three_55_minute_blocks_stay_within_the_rounding_bound():
    """Spec 4.1: Abweichung ≤ 0,005 h × (Einträge + 1) — hier 2,76 gegen 2,75."""
    week = block_week(mon=[("08:00", "08:55"), ("09:00", "09:55"), ("10:00", "10:55")])
    assert wbs.derive_targets(week)["hours_monday"] == Decimal("2.75")
    nets = [
        TimeEntry(start_time=time(h, 0), end_time=time(h, 55), break_minutes=0, uncredited_minutes=0).net_hours
        for h in (8, 9, 10)
    ]
    assert sum(nets) == Decimal("2.76")
    assert sum(nets) - Decimal("2.75") <= Decimal("0.005") * (len(nets) + 1)


def test_coupled_to_get_daily_target_for_date(db, test_user):
    week = block_week(pause=30, mon=[("08:00", "12:00"), ("15:00", "18:00")])
    d = wbs.derive_targets(week)
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=date(2026, 1, 1),
        blocks=week, weekly_hours=d["weekly_hours"], use_daily_schedule=True,
        hours_monday=d["hours_monday"], hours_tuesday=d["hours_tuesday"],
        hours_wednesday=d["hours_wednesday"], hours_thursday=d["hours_thursday"],
        hours_friday=d["hours_friday"], work_days_per_week=d["work_days_per_week"],
    ))
    db.commit()
    mon, tue = date(2026, 6, 1), date(2026, 6, 2)
    sched = calculation_service.get_schedule_for_date(db, test_user, mon)
    assert calculation_service.get_daily_target_for_date(test_user, mon, sched) == Decimal("6.50")
    assert calculation_service.get_daily_target_for_date(test_user, tue, sched) == Decimal("0")
```

`backend/tests/test_work_blocks_validation.py`:

```python
"""Spec 3.4: strenge Prüfung der Blöcke — nur in Schreibschemas."""
import pytest

from app.schemas.validators import validate_week_blocks
from tests.work_blocks_fixtures import K_BLOCKS, block_week

ADJACENT = "Mo: Block 2 muss nach dem Ende von Block 1 beginnen; aneinandergrenzende Blöcke bitte als einen Block erfassen."


def _days(*days):
    return list(days)


EMPTY = {"blocks": [], "pause_minutes": 0}
MON_8_12 = {"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": 0}


@pytest.mark.parametrize("week, message", [
    (block_week()[:4], "Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet."),
    ("kaputt", "Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet."),
    (block_week(mon=[("06:00", "07:00"), ("08:00", "09:00"), ("10:00", "11:00"), ("12:00", "13:00")]),
     "Mo: höchstens drei Blöcke je Tag."),
    (block_week(mon=[("8:00", "12:00")]), "Mo, Block 1: Uhrzeit im Format HH:MM angeben."),
    (block_week(mon=[("", "12:00")]), "Mo, Block 1: Uhrzeit im Format HH:MM angeben."),
    (block_week(mon=[("08:07", "12:00")]), "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."),
    (block_week(mon=[("08:00", "23:59")]), "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."),
    (block_week(tue=[("08:00", "12:00"), ("13:00", "12:30")]), "Di, Block 2: Beginn muss vor dem Ende liegen."),
    (block_week(mon=[("08:00", "12:00"), ("12:00", "13:00")]), ADJACENT),
    (block_week(mon=[("13:00", "14:00"), ("08:00", "12:00")]), ADJACENT),
    (block_week(mon=[("08:00", "12:00"), ("11:00", "14:00")]), ADJACENT),
    (block_week(pause=240, mon=[("08:00", "12:00")]), "Mo: Pause muss kürzer sein als die Gesamtzeit der Blöcke."),
    (_days(MON_8_12, EMPTY, {"blocks": [], "pause_minutes": 15}, EMPTY, EMPTY), "Mi: Pause nur an Tagen mit Blöcken."),
    (_days({"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": None}, EMPTY, EMPTY, EMPTY, EMPTY),
     "Mo: Pause angeben (0, wenn keine)."),
    (block_week(pause=7, mon=[("08:00", "12:00")]), "Mo: Pause in Minuten im 5-Minuten-Raster angeben."),
    (block_week(pause=-5, mon=[("08:00", "12:00")]), "Mo: Pause in Minuten im 5-Minuten-Raster angeben."),
    (block_week(), "Mindestens ein Wochentag braucht einen Block."),
    (block_week(mon=[("00:00", "12:05")], tue=[("00:00", "12:05")], wed=[("00:00", "12:05")],
                thu=[("00:00", "12:05")], fri=[("00:00", "12:05")]),
     "Die Wochensumme darf 60 Stunden nicht überschreiten."),
])
def test_each_rule_has_its_german_message(week, message):
    with pytest.raises(ValueError) as exc:
        validate_week_blocks(week)
    assert str(exc.value) == message


@pytest.mark.parametrize("week", [
    block_week(mon=[("06:00", "07:00"), ("08:00", "09:00"), ("10:00", "11:00")]),   # genau 3 Blöcke
    block_week(mon=[("08:05", "12:00")]),                                            # Raster 08:05
    block_week(pause=235, mon=[("08:00", "12:00")]),                                 # Pause = Σ − 5
    block_week(mon=[("00:00", "12:00")], tue=[("00:00", "12:00")], wed=[("00:00", "12:00")],
               thu=[("00:00", "12:00")], fri=[("00:00", "12:00")]),                  # genau 60 h
    block_week(mon=[("08:00", "23:55")]),                                            # größte Endzeit
])
def test_boundaries_are_valid(week):
    assert validate_week_blocks(week) == week


def test_returns_the_canonical_week_and_accepts_models():
    from pydantic import BaseModel

    class _Day(BaseModel):
        blocks: list
        pause_minutes: int | None

    assert validate_week_blocks(K_BLOCKS) == K_BLOCKS
    assert validate_week_blocks([_Day(**d) for d in K_BLOCKS]) == K_BLOCKS
```

An `backend/tests/test_work_blocks_service.py` anhängen:

```python
def test_changed_weekdays_compares_blocks_without_pause():
    old = wbs.parse_week_blocks(block_week(pause=30, mon=[("08:00", "12:00"), ("15:00", "18:00")],
                                           tue=[("08:00", "12:00")]))
    pause_only = wbs.parse_week_blocks(block_week(pause=60, mon=[("08:00", "12:00"), ("15:00", "18:00")],
                                                  tue=[("08:00", "12:00")]))
    shorter_mon = wbs.parse_week_blocks(block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")],
                                                   tue=[("08:00", "12:00")]))
    assert wbs.changed_weekdays(old.blocks, pause_only.blocks) == []
    assert wbs.changed_weekdays(old.blocks, shorter_mon.blocks) == [0]
    assert wbs.changed_weekdays(None, old.blocks) == [0, 1]
    assert wbs.changed_weekdays(old.blocks, None) == [0, 1]
    assert wbs.changed_weekdays(None, None) == []


def test_blocks_text_long_and_compact():
    parsed = wbs.parse_week_blocks(block_week(pause=30, mon=[("08:00", "12:00"), ("15:00", "18:00")],
                                              tue=[("08:00", "13:00")]))
    pauses = (30, 30, 0, 0, 0)
    assert wbs.blocks_text(parsed.blocks, pauses, compact=False) == (
        "Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 (Pause 30 Min)")
    assert wbs.blocks_text(parsed.blocks, (30, 0, 0, 0, 0), compact=True) == (
        "Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00")
    legacy = wbs.parse_week_blocks(legacy_week(mon=("07:37", "16:30"), fri=("07:30", None)))
    assert wbs.blocks_text(legacy.blocks, legacy.pauses, compact=False) == "Mo 07:37–16:30 / Fr 07:30–23:59"
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_derive_targets.py tests/test_work_blocks_validation.py tests/test_work_blocks_service.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'app.services.work_blocks_service' has no attribute 'derive_targets'` bzw. `ImportError: cannot import name 'validate_week_blocks'`.

- [ ] **Step 3: `work_blocks_service.py` ergänzen**

Import am Dateikopf ergänzen:

```python
from decimal import Decimal, ROUND_HALF_EVEN
```

Am Dateiende anhängen:

```python
HOURS_FIELDS = ("hours_monday", "hours_tuesday", "hours_wednesday", "hours_thursday", "hours_friday")


def derive_targets(week_blocks: list) -> dict:
    """Spec 4.1 — DIE eine Soll-Ableitung aus NEUEN Blöcken (``pause_minutes`` int).

    Erwartet die bereits validierte kanonische JSON-Woche (``validate_week_blocks``).
    Tagessoll = (Σ Blockdauer − Pause) / 60, ``quantize(0.01, ROUND_HALF_EVEN)``;
    ``weekly_hours`` = Σ der gerundeten Tageswerte. Genutzt von
    ``WorkingHoursChangeCreate`` und ``UserCreate``; Frontend-Zwilling
    ``utils/workBlocks.ts::deriveTargets`` (wortgleiche Testfälle)."""
    hours = []
    for day in week_blocks:
        blocks = day.get("blocks") or []
        total = sum(hhmm_to_minutes(b["end"]) - hhmm_to_minutes(b["start"]) for b in blocks)
        net = total - int(day.get("pause_minutes") or 0) if blocks else 0
        hours.append((Decimal(net) / Decimal(60)).quantize(Decimal("0.01"), ROUND_HALF_EVEN))
    derived = dict(zip(HOURS_FIELDS, hours))
    derived.update(
        weekly_hours=sum(hours, Decimal("0")),
        work_days_per_week=sum(1 for d in week_blocks if d.get("blocks")),
        use_daily_schedule=True,
    )
    return derived


def changed_weekdays(old_blocks: Optional[tuple], new_blocks: Optional[tuple]) -> list:
    """Spec 9.1: Wochentage (0 = Mo … 4 = Fr), deren Blocklisten sich zwischen dem
    alten und dem neuen Snapshot unterscheiden — OHNE Pause (eine reine
    Pausenänderung kappt nichts neu). Schedule-Format: ``None`` == fünf leere Tage
    (3.3, der Resolver normalisiert bereits)."""
    old = old_blocks or ((),) * 5
    new = new_blocks or ((),) * 5
    return [i for i in range(5) if tuple(old[i]) != tuple(new[i])]


def blocks_text(blocks: tuple, pauses: Optional[tuple], *, compact: bool) -> str:
    """Blöcke als Klartext, nur Tage mit Blöcken.

    lang (Dashboard-Hinweis, Berichtstext 15.2):
    ``Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00``;
    kurz (Sammelzeile „Vertrag:", PDF-Kurzform 15.2):
    ``Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00``.
    „Pause" nur bei Pause > 0; Altzeilen (Pause ``None``) ohne Pausenangabe."""
    parts = []
    for idx, day in enumerate(blocks or ()):
        if not day:
            continue
        spans = [f"{minutes_to_hhmm(s)}–{minutes_to_hhmm(e)}" for s, e in day]
        pause = pauses[idx] if pauses else None
        if compact:
            text = "+".join(spans) + (f" P{pause}" if pause else "")
        else:
            text = " + ".join(spans) + (f" (Pause {pause} Min)" if pause else "")
        parts.append(f"{WEEKDAY_LABELS[idx]} {text}")
    return " / ".join(parts)
```

- [ ] **Step 4: `validators.py` ergänzen**

Import nach `from typing import Any`:

```python
from app.services.work_blocks_service import WEEKDAY_LABELS, hhmm_to_minutes
```

Am Dateiende anhängen:

```python
# Spec 3.4: Obergrenze der Wochensumme (bestehende Grenze der Wochenstunden).
WEEK_LIMIT_MINUTES = 60 * 60


def _as_dict(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


def validate_week_blocks(value: Any) -> list:
    """Spec 2026-10-08, 3.4 — strenge Prüfung NUR für Schreibschemas
    (``UserCreate``, ``WorkingHoursChangeCreate``), nie für Leseschemas (E29).

    Wirft ``ValueError`` mit dem deutschen Text der ERSTEN verletzten Regel und
    liefert sonst die kanonische JSON-Woche. Frontend-Zwilling:
    ``utils/workBlocks.ts::validateWeekBlocks`` (wortgleiche Texte und Fälle).
    Die ArbZG-Plausibilität des Plans ist KEINE Regel hier (P9: Hinweise)."""
    if not isinstance(value, list) or len(value) != 5:
        raise ValueError("Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet.")
    week = []
    total_net = 0
    for idx, raw_day in enumerate(value):
        day = _as_dict(raw_day)
        if not isinstance(day, dict):
            raise ValueError("Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet.")
        label = WEEKDAY_LABELS[idx]
        blocks = [_as_dict(b) for b in (day.get("blocks") or [])]
        if len(blocks) > 3:
            raise ValueError(f"{label}: höchstens drei Blöcke je Tag.")
        spans = []
        for n, block in enumerate(blocks, start=1):
            try:
                start = hhmm_to_minutes(block.get("start"))
                end = hhmm_to_minutes(block.get("end"))
            except (ValueError, TypeError, AttributeError):
                raise ValueError(f"{label}, Block {n}: Uhrzeit im Format HH:MM angeben.") from None
            if start % 5 or end % 5:
                raise ValueError(f"{label}, Block {n}: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).")
            if start >= end:
                raise ValueError(f"{label}, Block {n}: Beginn muss vor dem Ende liegen.")
            spans.append((start, end))
        for n in range(1, len(spans)):
            if spans[n][0] <= spans[n - 1][1]:
                raise ValueError(
                    f"{label}: Block {n + 1} muss nach dem Ende von Block {n} beginnen; "
                    "aneinandergrenzende Blöcke bitte als einen Block erfassen."
                )
        pause = day.get("pause_minutes")
        if pause is None:
            raise ValueError(f"{label}: Pause angeben (0, wenn keine).")
        if isinstance(pause, bool) or not isinstance(pause, int) or pause < 0 or pause % 5:
            raise ValueError(f"{label}: Pause in Minuten im 5-Minuten-Raster angeben.")
        if not spans and pause != 0:
            raise ValueError(f"{label}: Pause nur an Tagen mit Blöcken.")
        gross = sum(e - s for s, e in spans)
        if spans and pause >= gross:
            raise ValueError(f"{label}: Pause muss kürzer sein als die Gesamtzeit der Blöcke.")
        total_net += gross - pause if spans else 0
        week.append({
            "blocks": [{"start": b["start"], "end": b["end"]} for b in blocks],
            "pause_minutes": pause,
        })
    if not any(d["blocks"] for d in week):
        raise ValueError("Mindestens ein Wochentag braucht einen Block.")
    if total_net > WEEK_LIMIT_MINUTES:
        raise ValueError("Die Wochensumme darf 60 Stunden nicht überschreiten.")
    return week
```

Hinweis zu „Pause im 5-Minuten-Raster": 3.4 nennt für Raster/Vorzeichen der Pause keinen eigenen Wortlaut; der Text „Pause in Minuten im 5-Minuten-Raster angeben." ist hier festgelegt und im Frontend-Zwilling wortgleich (Task 16).

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_derive_targets.py tests/test_work_blocks_validation.py tests/test_work_blocks_service.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/work_blocks_service.py backend/app/schemas/validators.py backend/tests/test_derive_targets.py backend/tests/test_work_blocks_validation.py backend/tests/test_work_blocks_service.py
git commit -F - <<'EOF'
feat(bloecke): Soll-Ableitung aus Blöcken und strenge Blockvalidierung (Spec 3.4, 4.1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Protokoll-Modul `reclamp_audit` (Spec 9.5, 10.1, 10.2, P7, P12)

**Files:**
- Create: `backend/app/services/reclamp_audit.py`
- Test (neu): `backend/tests/test_reclamp_audit.py`

**Interfaces:**
- Consumes: `work_blocks_service.ParsedWeek`, `is_legacy_week`, `blocks_text` (Task 1); `export_service.format_day_plan`, `format_hours_de` (Bestand); `work_window_service.not_credited_minutes`, `_hm` (PR1 Task 3); `work_window_service.credit_summary_text(entry) -> str` (PR2 Task 1 — PR2 ist nach den Global Constraints gemergt; der Wortlaut dort ist verbindlich, „davon … zwischen den Blöcken" steht bei jeder Lücke > 0, auch wenn sie der Gesamtzahl entspricht); `calculation_service.Schedule` (PR1 Task 2, nur gelesen)
- Produces (alle in `app.services.reclamp_audit`):
  - `AUDIT_SOURCE = "wh_reclamp"`
  - `class ReasonType(NamedTuple): key: str; prefix: str; label: str`; `REASON_TYPES: dict[str, ReasonType]`
  - `NOTE_MAX_LENGTH = 500`, `NOTE_TOO_LONG_DETAIL = "Notiz und Begründung zusammen höchstens 500 Zeichen."`
  - `SKIP_LABELS: dict[str, str]` (Gründe aus `ReclampSkip.reason` → Protokoll-/Anzeigewort)
  - `reason_text(reason_type: str, text: Optional[str]) -> str` — `"[Präfix] <Begründung>"`
  - `compose_change_note(note: Optional[str], reason_type: Optional[str], text: Optional[str]) -> Optional[str]`
  - `contract_text(schedule, *, compact: bool) -> str`
  - `summary_note(*, effective_from: date, deleted: bool, count: int, delta_minutes: int, saldo_delta_minutes: int, skipped: dict[str, int], grace: int, credit_reductions: int, reset_of: Optional[date], shortening: bool, reason_type: Optional[str], reason_text_value: Optional[str], contract_before: str, contract_after: str) -> str`
  - `class SummaryNote(NamedTuple): effective_from: date; deleted: bool; count: int; delta_minutes: int; saldo_delta_minutes: int; shortening: bool; reason_type: Optional[str]; reset_of: Optional[date]`
  - `parse_summary_note(note: Optional[str]) -> Optional[SummaryNote]`
  - `entry_new_note(after_text: str, *, effective_from: date, deleted: bool, old_grace: Optional[int], grace: int, shortening: bool, reason_type: Optional[str], reason_text_value: Optional[str]) -> str`

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_reclamp_audit.py`:

```python
"""Spec 10.1/10.2: Notizen der Neukappung, Sammelzeile schreiben UND lesen (P7).

Round-Trip für n = 0, 1, 2, 14, Saldo Δ negativ/0/positiv, mit/ohne Verkürzung,
mit Löschkennzeichen, mit Rücksetzung. Die Grundtyp-Präfixe sind eingefroren
(19.1 Nr. 7) — die Sammelzeile trägt nie eine Beschriftung, nur das Präfix.
"""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import TimeEntry, TimeEntryAuditLog
from app.routers.admin_time_entries import _audit_note_is_health_sensitive
from app.services import calculation_service, reclamp_audit as ra, work_blocks_service
from app.services.work_window_service import credit_summary_text
from tests.work_blocks_fixtures import block_week, legacy_week

EFF = date(2026, 9, 1)


def _schedule(*, week=None, weekly=Decimal("40"), daily=None, work_days=5):
    parsed = work_blocks_service.parse_week_blocks(week) if week else None
    return calculation_service.Schedule(
        weekly_hours=weekly,
        use_daily_schedule=daily is not None,
        day_hours=tuple(Decimal(str(v)) if v else None for v in (daily or (None,) * 5)),
        work_days_per_week=work_days,
        blocks=parsed.blocks if parsed else None,
        block_pauses=parsed.pauses if parsed else None,
    )


def _summary(**overrides):
    kwargs = dict(
        effective_from=EFF, deleted=False, count=3, delta_minutes=-135, saldo_delta_minutes=105,
        skipped={"credit_override": 1}, grace=15, credit_reductions=0, reset_of=None,
        shortening=True, reason_type="erfassungsfehler",
        reason_text_value="Mo-Nachmittagsblock war seit 01.09. mit 18:00 statt 17:00 hinterlegt",
        contract_before="Mo 08:00–12:00+15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00",
        contract_after="Mo 08:00–12:00+15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00",
    )
    kwargs.update(overrides)
    return ra.summary_note(**kwargs)


class TestReasonTypes:
    def test_keys_prefixes_and_labels_are_the_decided_ones(self):
        assert {k: (v.prefix, v.label) for k, v in ra.REASON_TYPES.items()} == {
            "erfassungsfehler": ("[Erfassungsfehler korrigiert]", "Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)"),
            "einvernehmlich": ("[Einvernehmlich vereinbart]", "Mit der beschäftigten Person vereinbart"),
            "sonstiges": ("[Sonstiges]", "Sonstiges"),
        }

    def test_compose_change_note(self):
        assert ra.compose_change_note("Teilzeit", None, None) == "Teilzeit"
        assert ra.compose_change_note(None, "einvernehmlich", "Montags bis 19 Uhr vereinbart") == (
            "[Einvernehmlich vereinbart] Montags bis 19 Uhr vereinbart")
        assert ra.compose_change_note("Vertrag v. 01.09.", "sonstiges", "  Ganz anderer Grund  ") == (
            "[Sonstiges] Ganz anderer Grund · Vertrag v. 01.09.")

    @pytest.mark.parametrize("key", ["erfassungsfehler", "einvernehmlich", "sonstiges"])
    def test_prefix_without_free_text_is_not_health_sensitive(self, key):
        """Spec 9.5: „[Sonstiges]" enthält das Label des maskierten Typs OTHER und
        entgeht dem Token „Sonstiges " nur durch die schließende Klammer."""
        summary = _summary(reason_type=key, reason_text_value="")
        entry_note = ra.entry_new_note("angerechnet 7:30 h", effective_from=EFF, deleted=False, old_grace=15,
                                       grace=15, shortening=True, reason_type=key, reason_text_value="")
        for note in (summary, entry_note):
            assert not _audit_note_is_health_sensitive(TimeEntryAuditLog(old_note=None, new_note=note)), note


class TestContractText:
    def test_new_blocks_compact_and_long(self):
        sched = _schedule(week=block_week(pause=30, mon=[("08:00", "12:00"), ("15:00", "18:00")]))
        assert ra.contract_text(sched, compact=True) == "Mo 08:00–12:00+15:00–18:00 P30"
        assert ra.contract_text(sched, compact=False) == "Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min)"

    def test_without_blocks(self):
        assert ra.contract_text(_schedule(weekly=Decimal("20")), compact=True) == "20,0 h/Woche (gleichmäßig, 5 Tage)"
        assert ra.contract_text(_schedule(weekly=Decimal("8"), work_days=1), compact=True) == "8,0 h/Woche (gleichmäßig, 1 Tag)"
        assert ra.contract_text(_schedule(weekly=Decimal("17"), daily=(8, 5, 4, 0, 0), work_days=3),
                                compact=False) == "Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche"

    def test_legacy_window_names_hours_and_window(self):
        sched = _schedule(weekly=Decimal("40"), week=legacy_week(mon=("07:30", "16:30"), fri=("07:30", None)))
        assert ra.contract_text(sched, compact=True) == (
            "40,0 h/Woche (gleichmäßig, 5 Tage) · Mo 07:30–16:30 / Fr 07:30–23:59 (nur Kappung)")


class TestSummaryNote:
    def test_spec_example_one(self):
        assert _summary() == (
            "Arbeitszeit-Änderung ab 01.09.2026: 3 Einträge neu berechnet, Δ -135 Min, Saldo Δ +105 Min, "
            "1 übersprungen (1 anerkannt) · Puffer 15 Min · Verkürzung · Grund: [Erfassungsfehler korrigiert] "
            "Mo-Nachmittagsblock war seit 01.09. mit 18:00 statt 17:00 hinterlegt · Vertrag: "
            "Mo 08:00–12:00+15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 → "
            "Mo 08:00–12:00+15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00"
        )

    def test_spec_example_without_entries(self):
        assert _summary(effective_from=date(2026, 11, 1), count=0, delta_minutes=0, saldo_delta_minutes=0,
                        skipped={}, shortening=False, reason_type=None, reason_text_value=None,
                        contract_before="20,0 h/Woche (gleichmäßig, 5 Tage)",
                        contract_after="25,0 h/Woche (gleichmäßig, 5 Tage)") == (
            "Arbeitszeit-Änderung ab 01.11.2026: 0 Einträge neu berechnet, Δ +0 Min, Saldo Δ +0 Min "
            "· Puffer 15 Min · Vertrag: 20,0 h/Woche (gleichmäßig, 5 Tage) → 25,0 h/Woche (gleichmäßig, 5 Tage)"
        )

    def test_credit_reductions_reset_and_deleted(self):
        assert " · 1 Abwesenheits-Gutschrift gesenkt · " in _summary(credit_reductions=1)
        assert " · 2 Abwesenheits-Gutschriften gesenkt · " in _summary(credit_reductions=2)
        reset = _summary(reset_of=EFF, effective_from=date(2026, 10, 9), shortening=False, reason_type=None)
        assert " · Rücksetzung der Änderung ab 01.09.2026 · " in reset
        assert _summary(deleted=True).startswith("Arbeitszeit-Änderung ab 01.09.2026 gelöscht: ")

    def test_skipped_breakdown_lists_every_reason(self):
        note = _summary(skipped={"credit_override": 1, "open": 1, "unique_collision": 2})
        assert ", 4 übersprungen (1 anerkannt, 1 offen, 2 Überschneidung) · " in note

    @pytest.mark.parametrize("count", [0, 1, 2, 14])
    @pytest.mark.parametrize("saldo", [-225, 0, 15])
    @pytest.mark.parametrize("shortening, reason", [(False, None), (True, "erfassungsfehler"),
                                                    (True, "einvernehmlich"), (True, "sonstiges")])
    @pytest.mark.parametrize("deleted", [False, True])
    @pytest.mark.parametrize("reset_of", [None, date(2026, 3, 1)])
    def test_round_trip(self, count, saldo, shortening, reason, deleted, reset_of):
        note = _summary(count=count, delta_minutes=-count * 45, saldo_delta_minutes=saldo,
                        shortening=shortening, reason_type=reason, deleted=deleted, reset_of=reset_of,
                        reason_text_value="Freitext · Verkürzung · Rücksetzung der Änderung ab 01.01.2020 · ")
        parsed = ra.parse_summary_note(note)
        assert parsed == ra.SummaryNote(EFF, deleted, count, -count * 45, saldo, shortening, reason, reset_of)
        assert ("1 Eintrag neu" in note) == (count == 1)

    def test_free_text_never_fakes_flags(self):
        """P12: der Freitext nach „Grund:" wird nie gelesen."""
        note = _summary(shortening=True, reason_type="sonstiges",
                        reason_text_value="x · Rücksetzung der Änderung ab 01.01.2020 · y")
        assert ra.parse_summary_note(note).reset_of is None

    @pytest.mark.parametrize("note", [None, "", "Krank 4,0 h — Arbeitszeit-Änderung ab 01.09.2026",
                                      "angerechnet 7:30 h — Arbeitszeit-Änderung ab 01.09.2026"])
    def test_foreign_notes_are_not_summaries(self, note):
        assert ra.parse_summary_note(note) is None


class TestEntryNote:
    def test_trigger_grace_and_reason(self):
        assert ra.entry_new_note("angerechnet 2:15 h, nicht angerechnet 0:45 h", effective_from=EFF,
                                 deleted=False, old_grace=15, grace=10, shortening=True,
                                 reason_type="erfassungsfehler", reason_text_value="Falsch hinterlegt seit 09") == (
            "angerechnet 2:15 h, nicht angerechnet 0:45 h — Arbeitszeit-Änderung ab 01.09.2026 · Puffer 15 → 10 Min "
            "· Grund: [Erfassungsfehler korrigiert] Falsch hinterlegt seit 09")

    def test_delete_trigger_and_no_grace_note_for_null_or_equal(self):
        assert ra.entry_new_note("angerechnet 3:00 h", effective_from=EFF, deleted=True, old_grace=None, grace=15,
                                 shortening=False, reason_type=None, reason_text_value=None) == (
            "angerechnet 3:00 h — Löschung der Arbeitszeit-Änderung ab 01.09.2026")
        assert " · Puffer" not in ra.entry_new_note("x", effective_from=EFF, deleted=False, old_grace=15, grace=15,
                                                     shortening=False, reason_type=None, reason_text_value=None)


class TestCreditSummaryText:
    def _e(self, start, end, unc=0, brk=0, raw_start=None, raw_end=None):
        return TimeEntry(start_time=start, end_time=end, raw_start_time=raw_start, raw_end_time=raw_end,
                         break_minutes=brk, uncredited_minutes=unc, auto_closed=False)

    def test_k1_gap_only(self):
        # PR2 Task 1: „davon …" auch, wenn die Lücke die Gesamtzahl ist (Beispiele 10.1/13.3).
        assert credit_summary_text(self._e(time(8), time(18), unc=150)) == (
            "angerechnet 7:30 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken")

    def test_k7_hull_and_gap(self):
        assert credit_summary_text(self._e(time(7, 45), time(18, 15), unc=150, raw_start=time(7), raw_end=time(19))) == (
            "angerechnet 8:00 h, nicht angerechnet 4:00 h, davon 2:30 h zwischen den Blöcken")

    def test_k9_with_pause(self):
        assert credit_summary_text(self._e(time(8), time(18), unc=150, brk=30)) == (
            "angerechnet 7:00 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken, Pause 0:30 h")

    def test_nothing_withheld(self):
        assert credit_summary_text(self._e(time(8), time(12))) == "angerechnet 4:00 h"
```

- [ ] **Step 2: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_reclamp_audit.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.reclamp_audit'`.

- [ ] **Step 3: `reclamp_audit.py` anlegen**

`backend/app/services/reclamp_audit.py`:

```python
"""Spec 2026-10-08, Abschnitt 10: Protokoll der Arbeitszeit-Änderungen.

Schreiben UND Lesen der Sammelzeile leben hier (P7) — ein Format, ein Parser,
Round-Trip-Test in ``tests/test_reclamp_audit.py``. Keine neue gehashte Spalte:
alles steht in festen Notiz-Bausteinen von ``new_note`` (10.3).

Die Notiz-Präfixe der Grundtypen sind EINGEFROREN (19.1 Nr. 7) — Protokoll und
Parser lesen sie. Die Oberfläche und der Dashboard-Hinweis zeigen ausschließlich
die Beschriftung aus :data:`REASON_TYPES`, nie das Präfix und nie den Freitext (P12).
"""
import re
from datetime import date, datetime
from typing import NamedTuple, Optional

from app.services import work_blocks_service
from app.services.export_service import format_day_plan, format_hours_de

AUDIT_SOURCE = "wh_reclamp"  # 10 Zeichen, varchar(40)
NOTE_MAX_LENGTH = 500
NOTE_TOO_LONG_DETAIL = "Notiz und Begründung zusammen höchstens 500 Zeichen."


class ReasonType(NamedTuple):
    key: str
    prefix: str
    label: str


REASON_TYPES = {
    "erfassungsfehler": ReasonType(
        "erfassungsfehler", "[Erfassungsfehler korrigiert]",
        "Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)"),
    "einvernehmlich": ReasonType(
        "einvernehmlich", "[Einvernehmlich vereinbart]",
        "Mit der beschäftigten Person vereinbart"),
    "sonstiges": ReasonType("sonstiges", "[Sonstiges]", "Sonstiges"),
}

# ReclampSkip.reason → Wort in Sammelzeile und Vorschau (keine Typlabels, 10.1).
SKIP_LABELS = {
    "credit_override": "anerkannt",
    "open": "offen",
    "soll_free_day": "Sonn-/Feiertag",
    "track_hours_off": "ohne Stundenzählung",
    "outside_employment": "außerhalb der Beschäftigung",
    "unique_collision": "Überschneidung",
}

_HEAD = re.compile(
    r"^Arbeitszeit-Änderung ab (\d{2}\.\d{2}\.\d{4})( gelöscht)?: (\d+) Eintr(?:ag|äge) neu berechnet, "
    r"Δ ([+-]\d+) Min, Saldo Δ ([+-]\d+) Min"
)
_RESET = re.compile(r" · Rücksetzung der Änderung ab (\d{2}\.\d{2}\.\d{4}) · ")
_GRUND = " · Grund: "
_VERTRAG = " · Vertrag: "


class SummaryNote(NamedTuple):
    effective_from: date
    deleted: bool
    count: int
    delta_minutes: int
    saldo_delta_minutes: int
    shortening: bool
    reason_type: Optional[str]
    reset_of: Optional[date]


def reason_text(reason_type: str, text: Optional[str]) -> str:
    """„[Erfassungsfehler korrigiert] <Begründung>" — Präfix unverändert (9.5)."""
    prefix = REASON_TYPES[reason_type].prefix
    text = (text or "").strip()
    return f"{prefix} {text}" if text else prefix


def compose_change_note(note: Optional[str], reason_type: Optional[str],
                        text: Optional[str]) -> Optional[str]:
    """Spec 9.5: ``working_hours_changes.note`` = Grund mit Präfix, eine zusätzliche
    Notiz mit „ · " angehängt. Ohne Grund bleibt die Notiz wie eingegeben."""
    if not reason_type:
        return note
    base = reason_text(reason_type, text)
    extra = (note or "").strip()
    return f"{base} · {extra}" if extra else base


def _days_text(n: int) -> str:
    return "1 Tag" if n == 1 else f"{n} Tage"


def contract_text(schedule, *, compact: bool) -> str:
    """Kurztext eines Vertrags-Snapshots (Sammelzeile „Vertrag:", ``compact``;
    Dashboard-Hinweis „neu: …", lang).

    * neue Blöcke: nur die Blöcke (Soll ist daraus abgeleitet)
    * Tagesplan: „Mo 8,0 / Di 5,0 = 13,0 h/Woche"
    * gleichmäßig: „20,0 h/Woche (gleichmäßig, 5 Tage)"
    * Altfenster: Soll-Text + „ · <Fenster> (nur Kappung)"."""
    parsed = None
    if schedule.blocks is not None:
        parsed = work_blocks_service.ParsedWeek(schedule.blocks, schedule.block_pauses)
    if parsed is not None and not work_blocks_service.is_legacy_week(parsed):
        return work_blocks_service.blocks_text(parsed.blocks, parsed.pauses, compact=compact)
    plan = format_day_plan(schedule.day_hours) if schedule.use_daily_schedule else ""
    if plan:
        base = f"{plan} = {format_hours_de(schedule.weekly_hours)} h/Woche"
    else:
        base = (f"{format_hours_de(schedule.weekly_hours)} h/Woche "
                f"(gleichmäßig, {_days_text(int(schedule.work_days_per_week))})")
    if parsed is None:
        return base
    window = work_blocks_service.blocks_text(parsed.blocks, parsed.pauses, compact=compact)
    return f"{base} · {window} (nur Kappung)"


def _sign(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


def summary_note(*, effective_from: date, deleted: bool, count: int, delta_minutes: int,
                 saldo_delta_minutes: int, skipped: dict, grace: int, credit_reductions: int,
                 reset_of: Optional[date], shortening: bool, reason_type: Optional[str],
                 reason_text_value: Optional[str], contract_before: str, contract_after: str) -> str:
    """Spec 10.2 — die Sammelzeile (genau eine je Anlegen/Löschen, P20)."""
    head = (
        f"Arbeitszeit-Änderung ab {effective_from:%d.%m.%Y}{' gelöscht' if deleted else ''}: "
        f"{count} {'Eintrag' if count == 1 else 'Einträge'} neu berechnet, "
        f"Δ {_sign(delta_minutes)} Min, Saldo Δ {_sign(saldo_delta_minutes)} Min"
    )
    total_skipped = sum(skipped.values())
    if total_skipped:
        details = ", ".join(f"{skipped[k]} {SKIP_LABELS[k]}" for k in SKIP_LABELS if skipped.get(k))
        head += f", {total_skipped} übersprungen ({details})"
    parts = [head, f"Puffer {grace} Min"]
    if credit_reductions:
        noun = "Abwesenheits-Gutschrift" if credit_reductions == 1 else "Abwesenheits-Gutschriften"
        parts.append(f"{credit_reductions} {noun} gesenkt")
    if reset_of is not None:
        parts.append(f"Rücksetzung der Änderung ab {reset_of:%d.%m.%Y}")
    if shortening:
        parts.append("Verkürzung")
    if shortening and reason_type:
        parts.append(f"Grund: {reason_text(reason_type, reason_text_value)}")
    parts.append(f"Vertrag: {contract_before} → {contract_after}")
    return " · ".join(parts)


def parse_summary_note(note: Optional[str]) -> Optional[SummaryNote]:
    """Liest die festen Bausteine einer Sammelzeile. Der Freitext nach „Grund:"
    wird nie gelesen (P12): Kennzeichen werden nur VOR „ · Grund: " bzw.
    „ · Vertrag: " gesucht. Keine Sammelzeile → ``None``."""
    if not note:
        return None
    m = _HEAD.match(note)
    if m is None:
        return None
    cut = note.find(_GRUND)
    if cut == -1:
        cut = note.find(_VERTRAG)
    fixed = note[: cut + 3] if cut != -1 else note
    reset = _RESET.search(fixed)
    reason_type = None
    if note.find(_GRUND) != -1 and note.find(_GRUND) == cut:
        rest = note[cut + len(_GRUND):]
        for key, rt in REASON_TYPES.items():
            if rest.startswith(rt.prefix):
                reason_type = key
                break
    return SummaryNote(
        effective_from=datetime.strptime(m.group(1), "%d.%m.%Y").date(),
        deleted=bool(m.group(2)),
        count=int(m.group(3)),
        delta_minutes=int(m.group(4)),
        saldo_delta_minutes=int(m.group(5)),
        shortening=" · Verkürzung · " in fixed,
        reason_type=reason_type,
        reset_of=datetime.strptime(reset.group(1), "%d.%m.%Y").date() if reset else None,
    )


def entry_new_note(after_text: str, *, effective_from: date, deleted: bool, old_grace: Optional[int],
                   grace: int, shortening: bool, reason_type: Optional[str],
                   reason_text_value: Optional[str]) -> str:
    """Spec 10.1 — ``new_note`` der Einzelzeile: Anrechnung nachher + Auslöser,
    bei abweichendem gespeichertem Puffer „ · Puffer 15 → 10 Min" (E80; bei NULL
    kein Zusatz), bei Verkürzung der Grund mit unverändertem Präfix."""
    trigger = ("Löschung der Arbeitszeit-Änderung" if deleted else "Arbeitszeit-Änderung")
    text = f"{after_text} — {trigger} ab {effective_from:%d.%m.%Y}"
    if old_grace is not None and old_grace != grace:
        text += f" · Puffer {old_grace} → {grace} Min"
    if shortening and reason_type:
        text += f" · Grund: {reason_text(reason_type, reason_text_value)}"
    return text
```

Hinweis: `cut + 3` behält das führende „ · " des abgeschnittenen Bausteins, damit „ · Verkürzung · " und „ · Rücksetzung … · " auch direkt vor „Grund:"/„Vertrag:" erkannt werden.

- [ ] **Step 4: Test laufen lassen — muss grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_reclamp_audit.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reclamp_audit.py backend/tests/test_reclamp_audit.py
git commit -F - <<'EOF'
feat(bloecke): Protokoll-Modul der Neukappung (Sammelzeile, Grundtypen, Vertrags-Kurztext)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Schreib-, Lösch- und Vorschauschemas (Spec 11.2, 11.3, 11.5, 3.4)

**Files:**
- Modify: `backend/app/schemas/working_hours_change.py`
- Modify: `backend/app/routers/admin_users.py` (`_SCHEDULE_FIELD_LABELS`, neu `_nested_block_label`, `_schedule_input_error`)
- Test (neu): `backend/tests/test_wh_change_schema_blocks.py`

**Interfaces:**
- Consumes: `validate_week_blocks` (Task 1), `work_blocks_service.derive_targets`, `HOURS_FIELDS`, `WEEKDAY_LABELS` (Task 1/PR1), `reclamp_audit.compose_change_note`, `NOTE_MAX_LENGTH`, `NOTE_TOO_LONG_DETAIL` (Task 2)
- Produces (in `app.schemas.working_hours_change`):
  - `RetroReasonType = Literal["erfassungsfehler", "einvernehmlich", "sonstiges"]`
  - `class TimeBlockIn(BaseModel): start: str; end: str`
  - `class DayBlocksIn(BaseModel): blocks: List[TimeBlockIn]; pause_minutes: Optional[int]`
  - `class RetroReasonFields(BaseModel)`: `retroactive_reason_type`, `retroactive_reason_text` (10–400), `wage_risk_confirmed: bool = False`, `other_reason_risk_confirmed: bool = False`
  - `WorkingHoursChangeCreate(WorkingHoursChangeBase, RetroReasonFields)` + `blocks: Optional[List[DayBlocksIn]]`, `remove_legacy_window: bool`, `reset_of_change_id: Optional[UUID]`, Methode `blocks_json() -> Optional[list]`
  - `class WorkingHoursChangeDelete(RetroReasonFields)`
  - `BLOCKS_WITH_HOURS_DETAIL = "Tagesstunden werden aus den Arbeitszeit-Blöcken abgeleitet."`
  - `WorkingHoursChangeResponse` + `adjusted_time_entries: int = 0`, `skipped_time_entries: int = 0`
  - Vorschau-Untermodelle `TimeEntryMonthOut`, `TimeEntryChangeOut`, `SkippedEntryOut`, `AbsenceCreditReductionOut`, `ArbzgFindingsOut` und die neuen Felder aus 11.3 auf `WorkingHoursChangePreview` (alle mit Vorgabewert; zusätzlich `not_extendable_entries: List[TimeEntryChangeOut]` für die Anzeige „14.09., Ende 18:15")
  - `admin_users._nested_block_label(loc: tuple) -> Optional[str]`

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_wh_change_schema_blocks.py`:

```python
"""Spec 11.2/11.5/3.4: Schreibschema mit Blöcken, Schutzpaket-Felder, Fehlertexte."""
from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.admin_users import _nested_block_label, _schedule_input_error
from app.schemas.working_hours_change import (
    BLOCKS_WITH_HOURS_DETAIL, WorkingHoursChangeCreate, WorkingHoursChangeDelete,
    WorkingHoursChangePreview,
)
from tests.work_blocks_fixtures import K_BLOCKS, block_week

EFF = "2026-09-01"


def _error(body):
    with pytest.raises(ValidationError) as exc:
        WorkingHoursChangeCreate.model_validate(body)
    return _schedule_input_error(exc.value)


def test_blocks_derive_the_snapshot():
    c = WorkingHoursChangeCreate.model_validate({"effective_from": EFF, "blocks": K_BLOCKS})
    assert c.use_daily_schedule is True
    assert (c.hours_monday, c.hours_tuesday, c.weekly_hours, c.work_days_per_week) == (7.0, 0.0, 7.0, 1)
    assert c.blocks_json() == K_BLOCKS


def test_blocks_override_a_client_mode_and_work_days():
    c = WorkingHoursChangeCreate.model_validate(
        {"effective_from": EFF, "blocks": K_BLOCKS, "use_daily_schedule": False, "work_days_per_week": 5})
    assert (c.use_daily_schedule, c.work_days_per_week) == (True, 1)


@pytest.mark.parametrize("extra", [{"weekly_hours": 7.0}, {"hours_monday": 7.0}, {"weekly_hours": None}])
def test_blocks_with_hours_are_rejected(extra):
    assert _error({"effective_from": EFF, "blocks": K_BLOCKS, **extra}) == BLOCKS_WITH_HOURS_DETAIL


def test_block_rule_message_reaches_the_dialog():
    body = {"effective_from": EFF, "blocks": block_week(mon=[("08:07", "12:00")])}
    assert _error(body) == "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."


def test_nested_type_errors_get_a_label():
    week = block_week(mon=[("08:00", "12:00")])
    week[0]["blocks"][0]["start"] = 8
    assert _error({"effective_from": EFF, "blocks": week}) == "Mo, Block 1, Beginn: ungültiger Wert."
    week = block_week(tue=[("08:00", "12:00")])
    week[1]["pause_minutes"] = "x"
    assert _error({"effective_from": EFF, "blocks": week}) == "Di, Pause: ungültiger Wert."


@pytest.mark.parametrize("loc, expected", [
    (("blocks", 0, "blocks", 1, "start"), "Mo, Block 2, Beginn"),
    (("blocks", 4, "blocks", 0, "end"), "Fr, Block 1, Ende"),
    (("blocks", 2, "pause_minutes"), "Mi, Pause"),
    (("blocks", 3), "Do"),
    (("blocks", 7, "pause_minutes"), None),
    (("blocks", "x"), None),
    (("weekly_hours",), None),
    ((), None),
])
def test_nested_label(loc, expected):
    assert _nested_block_label(loc) == expected


def test_reason_text_length_and_note_total():
    short = {"effective_from": EFF, "weekly_hours": 30, "retroactive_reason_type": "erfassungsfehler",
             "retroactive_reason_text": "123456789"}
    assert _error(short) == "Die Begründung muss mindestens 10 Zeichen lang sein."
    too_long = dict(short, retroactive_reason_text="x" * 400, note="n" * 80)
    assert _error(too_long) == "Notiz und Begründung zusammen höchstens 500 Zeichen."
    fits = dict(short, retroactive_reason_text="x" * 400, note="n" * 60)
    assert WorkingHoursChangeCreate.model_validate(fits).note == "n" * 60


def test_unknown_reason_type_is_rejected():
    with pytest.raises(ValidationError):
        WorkingHoursChangeCreate.model_validate(
            {"effective_from": EFF, "weekly_hours": 30, "retroactive_reason_type": "irgendwas"})


def test_reset_and_legacy_flags():
    cid = uuid4()
    c = WorkingHoursChangeCreate.model_validate(
        {"effective_from": EFF, "weekly_hours": 30, "reset_of_change_id": str(cid), "remove_legacy_window": True})
    assert (c.reset_of_change_id, c.remove_legacy_window, c.blocks) == (cid, True, None)


def test_delete_body_defaults():
    d = WorkingHoursChangeDelete()
    assert (d.retroactive_reason_type, d.retroactive_reason_text, d.wage_risk_confirmed,
            d.other_reason_risk_confirmed) == (None, None, False, False)


def test_preview_new_fields_have_defaults():
    p = WorkingHoursChangePreview(
        is_retroactive=False, period_start=date(2026, 9, 1), period_end=date(2026, 9, 1),
        current_daily_target=8, new_daily_target=8, day_targets_current=[8] * 5, day_targets_new=[8] * 5,
        overtime_before=0, overtime_after=0, vacation_days_before=0, vacation_days_after=0, affected_absences=0,
    )
    assert (p.is_shortening, p.shortening_reasons, p.earliest_lossless_date, p.reset_body) == (False, [], None, None)
    assert p.arbzg_findings.weeks_over_48_presence == 0
    assert p.time_entry_changes == [] and p.not_extendable_entries == []
```

- [ ] **Step 2: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_schema_blocks.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'BLOCKS_WITH_HOURS_DETAIL'`.

- [ ] **Step 3: Schemas ergänzen**

`backend/app/schemas/working_hours_change.py` — Kopf ersetzen durch:

```python
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from typing import Any, List, Literal, Optional
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from app.schemas.validators import validate_week_blocks
from app.services import work_blocks_service

# Spec 11.4: blocks + weekly_hours/hours_* im selben Body.
BLOCKS_WITH_HOURS_DETAIL = "Tagesstunden werden aus den Arbeitszeit-Blöcken abgeleitet."
_HOURS_INPUT_FIELDS = frozenset({"weekly_hours", *work_blocks_service.HOURS_FIELDS})

# Spec 9.5 / 19.1 Nr. 7: Schlüssel eingefroren; Beschriftungen leben in
# reclamp_audit.REASON_TYPES.
RetroReasonType = Literal["erfassungsfehler", "einvernehmlich", "sonstiges"]


class TimeBlockIn(BaseModel):
    """Ein Block „von–bis" als ``"HH:MM"`` (Raster und Reihenfolge prüft
    ``validate_week_blocks`` mit deutschem Text)."""
    start: str
    end: str


class DayBlocksIn(BaseModel):
    """Ein Wochentag. Bewusst OHNE ``max_length``/``ge``: „höchstens drei Blöcke"
    und die Pausenregeln meldet ``validate_week_blocks`` mit dem Wortlaut aus 3.4 —
    eine Pydantic-Feldgrenze käme mit englischer Meldung zuerst."""
    blocks: List[TimeBlockIn] = Field(default_factory=list)
    pause_minutes: Optional[int] = None


class RetroReasonFields(BaseModel):
    """Spec 9.5/11.2: Schutzpaket — Pflicht, sobald die Änderung (bzw. das
    Löschen) nach 9.5 (a)–(c) verkürzt. Gleicher Body für Anlegen und DELETE."""
    retroactive_reason_type: Optional[RetroReasonType] = None
    retroactive_reason_text: Optional[str] = Field(None, min_length=10, max_length=400)  # P15
    wage_risk_confirmed: bool = False
    other_reason_risk_confirmed: bool = False  # P26: Pflicht bei „sonstiges"
```

`class WorkingHoursChangeCreate(WorkingHoursChangeBase):` ersetzen durch die folgende Kopfzeile plus Felder — der bestehende `check_mode` bleibt unverändert, `derive_from_blocks` steht **davor**, `check_note_length` danach (Pydantic führt `after`-Validatoren in Definitionsreihenfolge aus):

```python
class WorkingHoursChangeCreate(WorkingHoursChangeBase, RetroReasonFields):
    # Spec 11.2: gesetzt → Block-Modus; Soll wird abgeleitet (4.1/4.2).
    blocks: Optional[List[DayBlocksIn]] = None
    remove_legacy_window: bool = False   # P2: Altfenster ausdrücklich entfernen
    reset_of_change_id: Optional[UUID] = None  # P13: „auf vorherigen Stand zurücksetzen"

    def blocks_json(self) -> Optional[list]:
        """Kanonische JSON-Woche (Spec 3.1) oder ``None``."""
        return None if self.blocks is None else [d.model_dump() for d in self.blocks]

    @model_validator(mode='after')
    def derive_from_blocks(self):
        """Spec 4.2/11.2: Blöcke streng prüfen und das Soll ABLEITEN. Ein
        mitgeschickter ``weekly_hours``/``hours_*``-Wert neben ``blocks`` ist ein
        Widerspruch → 422 (anders als ``UserCreate``, das überschreibt)."""
        if self.blocks is None:
            return self
        if self.model_fields_set & _HOURS_INPUT_FIELDS:
            raise ValueError(BLOCKS_WITH_HOURS_DETAIL)
        week = validate_week_blocks(self.blocks)
        derived = work_blocks_service.derive_targets(week)
        self.blocks = [DayBlocksIn.model_validate(d) for d in week]
        self.use_daily_schedule = True
        for field in work_blocks_service.HOURS_FIELDS:
            setattr(self, field, float(derived[field]))
        self.weekly_hours = float(derived["weekly_hours"])
        self.work_days_per_week = derived["work_days_per_week"]
        return self
```

Nach dem bestehenden `check_mode` in derselben Klasse:

```python
    @model_validator(mode='after')
    def check_note_length(self):
        """Spec 9.5: Grund (mit Präfix) + Notiz ≤ 500 Zeichen — keine stille
        Kürzung. Lokaler Import: ``reclamp_audit`` zieht den Export-Service."""
        from app.services.reclamp_audit import NOTE_MAX_LENGTH, NOTE_TOO_LONG_DETAIL, compose_change_note
        if self.retroactive_reason_type and self.retroactive_reason_text:
            composed = compose_change_note(self.note, self.retroactive_reason_type, self.retroactive_reason_text)
            if composed is not None and len(composed) > NOTE_MAX_LENGTH:
                raise ValueError(NOTE_TOO_LONG_DETAIL)
        return self


class WorkingHoursChangeDelete(RetroReasonFields):
    """Spec 9.7/P8: optionaler JSON-Body von ``DELETE …/working-hours-changes/{id}``."""
```

In `WorkingHoursChangeResponse` nach `warning: Optional[str] = None`:

```python
    # Spec 11.1: Anzahl neu gekappter bzw. übersprungener Zeiteinträge (Toast).
    adjusted_time_entries: int = 0
    skipped_time_entries: int = 0
```

Vor `class WorkingHoursChangePreview` einfügen:

```python
class TimeEntryMonthOut(BaseModel):
    month: str            # "2026-09"
    entries: int
    net_before: float
    net_after: float


class TimeEntryChangeOut(BaseModel):
    entry_id: str
    date: date
    old_start: Optional[time] = None
    old_end: Optional[time] = None
    old_uncredited: int = 0
    old_net: float = 0.0
    new_start: Optional[time] = None
    new_end: Optional[time] = None
    new_uncredited: int = 0
    new_net: float = 0.0
    not_extendable: Optional[Literal["start", "end", "both"]] = None


class SkippedEntryOut(BaseModel):
    entry_id: str
    date: date
    reason: str


class AbsenceCreditReductionOut(BaseModel):
    absence_id: str
    date: date
    old_hours: float
    new_hours: float


class ArbzgFindingsOut(BaseModel):
    days_over_10_credited_before: int = 0
    days_over_10_credited_after: int = 0
    days_over_10_presence: int = 0
    weeks_over_48_credited_before: int = 0
    weeks_over_48_credited_after: int = 0
    weeks_over_48_presence: int = 0
```

In `WorkingHoursChangePreview` nach `closed_year_warning: Optional[str] = None` (Spec 11.3; `not_extendable_entries` trägt Datum und Kante für die Anzeige „14.09., Ende 18:15", die `not_extendable_count` allein nicht liefert):

```python
    grace_minutes: int = 0
    blocks_current: Optional[Any] = None
    blocks_new: Optional[Any] = None
    changed_weekdays: List[int] = Field(default_factory=list)
    affected_time_entries: int = 0
    time_entry_months: List[TimeEntryMonthOut] = Field(default_factory=list)
    time_entry_changes: List[TimeEntryChangeOut] = Field(default_factory=list)
    skipped_time_entries: List[SkippedEntryOut] = Field(default_factory=list)
    not_extendable_count: int = 0
    not_extendable_entries: List[TimeEntryChangeOut] = Field(default_factory=list)
    is_shortening: bool = False
    shortening_reasons: List[Literal["entries", "saldo", "absence_credit"]] = Field(default_factory=list)
    shortening_closed_years: List[int] = Field(default_factory=list)
    earliest_lossless_date: Optional[date] = None
    earliest_lossless_note: Optional[str] = None
    lost_credited_hours: float = 0.0
    target_delta_hours: float = 0.0
    credited_delta_hours: float = 0.0
    saldo_delta_hours: float = 0.0
    open_day_saldo_delta_hours: float = 0.0
    absence_f1_adjustments: int = 0
    absence_credit_reductions: List[AbsenceCreditReductionOut] = Field(default_factory=list)
    reset_body: Optional[dict] = None
    stale_entries_closed: int = 0
    arbzg_findings: ArbzgFindingsOut = Field(default_factory=ArbzgFindingsOut)
    milog_warning: List[str] = Field(default_factory=list)
    block_break_notices: List[str] = Field(default_factory=list)
```

- [ ] **Step 4: `_schedule_input_error` mit verschachtelten Labels (`admin_users.py`)**

In `_SCHEDULE_FIELD_LABELS` den Eintrag `"retroactive_reason_text": "Die Begründung",` ergänzen. Direkt nach dem Dict einfügen:

```python
_BLOCK_FIELD_LABELS = {"start": "Beginn", "end": "Ende"}


def _nested_block_label(loc: tuple) -> Optional[str]:
    """Spec 3.4: ``("blocks", 0, "blocks", 1, "start")`` → „Mo, Block 2, Beginn",
    ``("blocks", 0, "pause_minutes")`` → „Mo, Pause". Unerwartete Form → ``None``
    (der Aufrufer fällt auf den generischen Text zurück — nie IndexError/500)."""
    if len(loc) < 2 or loc[0] != "blocks" or not isinstance(loc[1], int) or not 0 <= loc[1] < 5:
        return None
    label = work_blocks_service.WEEKDAY_LABELS[loc[1]]
    rest = loc[2:]
    if not rest:
        return label
    if rest[0] == "pause_minutes":
        return f"{label}, Pause"
    if rest[0] == "blocks" and len(rest) >= 2 and isinstance(rest[1], int):
        text = f"{label}, Block {rest[1] + 1}"
        if len(rest) >= 3 and rest[2] in _BLOCK_FIELD_LABELS:
            text += f", {_BLOCK_FIELD_LABELS[rest[2]]}"
        return text
    if rest[0] == "blocks":
        return label
    return None
```

In `_schedule_input_error` zwischen dem `value_error`-Zweig und `label = next(…)`:

```python
    nested = _nested_block_label(tuple(err.get("loc") or ()))
    if nested is not None:
        return f"{nested}: ungültiger Wert."
```

und vor `if "le" in ctx:`:

```python
    if "min_length" in ctx:
        return f"{label} muss mindestens {ctx['min_length']} Zeichen lang sein."
    if "max_length" in ctx:
        return f"{label} darf höchstens {ctx['max_length']} Zeichen lang sein."
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_schema_blocks.py tests/test_wh_change_preview.py tests/test_wh_change_day_plan_create.py tests/test_migration_067_weekly_hours_guard.py -q -p no:cacheprovider`
Expected: PASS (die bestehenden Suiten nutzen noch GET-Vorschau und Typen ohne Blöcke — unverändert grün).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/working_hours_change.py backend/app/routers/admin_users.py backend/tests/test_wh_change_schema_blocks.py
git commit -F - <<'EOF'
feat(bloecke): Schreibschema mit Blöcken und Schutzpaket, Vorschau-Felder 11.3

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Startvertrag mit Blöcken beim Anlegen (Spec E28, 4.2, 9.8)

**Files:**
- Modify: `backend/app/schemas/user.py` (`UserCreate`)
- Modify: `backend/app/routers/admin_users.py` (`create_user`: Konstruktor)
- Modify: `backend/tests/test_no_live_work_blocks_read.py` (Erlaubnisliste)
- Test (erweitern): `backend/tests/test_users_api_work_blocks.py`

**Interfaces:**
- Consumes: `DayBlocksIn` (Task 3), `validate_week_blocks`, `derive_targets`, `HOURS_FIELDS` (Task 1)
- Produces: `UserCreate.work_blocks: Optional[List[DayBlocksIn]]` mit Validator `derive_from_work_blocks` (überschreibt `use_daily_schedule`, `hours_*`, `weekly_hours`, `work_days_per_week`; kein 422); `POST /api/admin/users` speichert `users.work_blocks` kanonisch

- [ ] **Step 1: Failing tests anhängen**

An `backend/tests/test_users_api_work_blocks.py` anhängen:

```python
from tests.work_blocks_fixtures import K_BLOCKS, block_week  # noqa: E402

BLOCK_USER = {**NEW_USER, "username": "blockneu", "weekly_hours": 40.0, "work_days_per_week": 5,
              "use_daily_schedule": False, "hours_monday": 9.0}
ANNA = block_week(pause=0, mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                  thu=[("08:00", "12:00")])


def test_post_with_work_blocks_derives_and_overrides(admin_client, _db_session):
    """Spec 4.2: abweichende Clientwerte werden überschrieben, kein 422."""
    resp = admin_client.post("/api/admin/users", json={**BLOCK_USER, "work_blocks": ANNA})
    assert resp.status_code == 201, resp.text
    body = resp.json()["user"]
    assert body["use_daily_schedule"] is True
    assert (body["hours_monday"], body["hours_tuesday"], body["hours_wednesday"]) == (7.0, 4.0, 0.0)
    assert (body["weekly_hours"], body["work_days_per_week"]) == (15.0, 3)
    assert body["work_blocks"] == ANNA
    assert body["work_blocks_today"] == ANNA


def test_post_with_invalid_work_blocks_is_422(admin_client):
    resp = admin_client.post("/api/admin/users",
                             json={**BLOCK_USER, "work_blocks": block_week(mon=[("08:07", "12:00")])})
    assert resp.status_code == 422, resp.text
    assert "5-Minuten-Raster" in resp.text


def test_post_with_work_blocks_and_track_hours_off_is_accepted(admin_client):
    """Spec 11.2: angenommen, ohne Wirkung, solange keine Stunden gezählt werden."""
    resp = admin_client.post("/api/admin/users",
                             json={**BLOCK_USER, "username": "blockleitend", "track_hours": False,
                                   "work_blocks": K_BLOCKS})
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["work_blocks"] == K_BLOCKS
```

In `backend/tests/test_no_live_work_blocks_read.py` die Erlaubnisliste um zwei Einträge erweitern (bestehende Einträge, auch die aus PR2, bleiben):

```python
    ("app/routers/admin_users.py", "create_user"),           # Spec 9.8 / E28: Startvertrag
    ("app/schemas/user.py", "derive_from_work_blocks"),      # Spec 4.2: Ableitung im Schreibschema
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_users_api_work_blocks.py tests/test_no_live_work_blocks_read.py -q -p no:cacheprovider`
Expected: FAIL — `work_blocks` wird ignoriert (`body["use_daily_schedule"] is False`), der Guard meldet die zwei fehlenden Fundstellen nicht (er läuft noch grün, die drei neuen API-Tests scheitern).

- [ ] **Step 3: `UserCreate` ergänzen**

`backend/app/schemas/user.py` — Importe ergänzen:

```python
from typing import Any, List, Optional
from app.schemas.validators import validate_week_blocks
from app.schemas.working_hours_change import DayBlocksIn
from app.services import work_blocks_service
```

In `UserCreate` direkt nach `role: UserRole = UserRole.EMPLOYEE` (vor dem PR1-Feld `legacy_window_fields_sent`):

```python
    # Spec 2026-10-08 (E28, 4.2): Startvertrag mit Arbeitszeit-Blöcken. STRENG
    # geprüft — nur in diesem Schreibschema, nie in den Leseschemas (E29).
    work_blocks: Optional[List[DayBlocksIn]] = None
```

und **vor** `check_daily_schedule_matches_weekly_hours` (Definitionsreihenfolge = Ausführungsreihenfolge):

```python
    @model_validator(mode='after')
    def derive_from_work_blocks(self):
        """Spec 4.2: ableiten und ÜBERSCHREIBEN statt 422 — ``UserBase.weekly_hours``
        ist Pflichtfeld, das Anlegeformular schickt es immer mit (Präzedenz
        „Fund E"). ``track_hours=False`` wird angenommen (11.2)."""
        if self.work_blocks is None:
            return self
        week = validate_week_blocks(self.work_blocks)
        derived = work_blocks_service.derive_targets(week)
        self.work_blocks = [DayBlocksIn.model_validate(d) for d in week]
        self.use_daily_schedule = True
        for field in work_blocks_service.HOURS_FIELDS:
            setattr(self, field, float(derived[field]))
        self.weekly_hours = float(derived["weekly_hours"])
        self.work_days_per_week = derived["work_days_per_week"]
        return self
```

- [ ] **Step 4: `create_user` speichert die Blöcke**

Im `User(...)`-Konstruktor von `create_user` nach `use_fixed_monthly_target=user_data.use_fixed_monthly_target,` einfügen:

```python
        # Spec E28: Startvertrag — kanonische JSON-Woche (Strings, nie time).
        work_blocks=(
            [d.model_dump() for d in user_data.work_blocks]
            if user_data.work_blocks is not None else None
        ),
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_users_api_work_blocks.py tests/test_no_live_work_blocks_read.py tests/test_user_create_daily_schedule_validation.py tests/test_endpoints.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/user.py backend/app/routers/admin_users.py backend/tests/test_users_api_work_blocks.py backend/tests/test_no_live_work_blocks_read.py
git commit -F - <<'EOF'
feat(bloecke): Anlegen mit Arbeitszeit-Blöcken leitet das Soll ab (E28)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Plan-Hinweise `block_break_notices` (Spec P9, 11.3)

**Files:**
- Modify: `backend/app/services/work_blocks_service.py` (am Dateiende)
- Test (neu): `backend/tests/test_work_blocks_plan_notices.py`

**Interfaces:**
- Consumes: `hhmm_to_minutes`, `minutes_to_hhmm`, `WEEKDAY_LABELS` (PR1)
- Produces: `work_blocks_service.block_break_notices(week: Optional[list], grace: int, *, exempt: bool) -> list[str]` — nie eine Ausnahme für gültige neue Wochen; nur Hinweise (P9: „Kein 422"). Aufgerufen von der Vorschau (Task 10) mit der validierten Woche, dem aktuellen Mandanten-Puffer und `user.exempt_from_arbzg`.

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_work_blocks_plan_notices.py`:

```python
"""Spec P9: Plan-Hinweise über den GANZEN Tagesplan — nicht blockierend."""
from app.services.work_blocks_service import block_break_notices
from tests.work_blocks_fixtures import block_week


def test_gap_under_15_minutes_is_no_break_and_disappears():
    week = block_week(mon=[("07:00", "12:00"), ("12:10", "17:10")])
    notices = block_break_notices(week, 15, exempt=False)
    assert "Mo: geplant 10:00 h Arbeit, eingeplante Pausen 0 Min – nach § 4 ArbZG sind mindestens 45 Minuten nötig." in notices
    assert ("Mo: Die Lücke 12:00–12:10 ist nicht länger als der doppelte Puffer (15 Min) und wird vollständig "
            "angerechnet. Eine geplante Pause bitte als „Pause innerhalb der Blöcke“ erfassen.") in notices
    assert any(n.startswith("Mo: Tagessoll 10:00 h – mehr als 8 Stunden") for n in notices)


def test_two_20_minute_gaps_are_not_enough_for_10_20_hours():
    week = block_week(mon=[("07:00", "10:40"), ("11:00", "14:20"), ("14:40", "18:00")])
    notices = block_break_notices(week, 0, exempt=False)
    assert "Mo: geplant 10:20 h Arbeit, eingeplante Pausen 40 Min – nach § 4 ArbZG sind mindestens 45 Minuten nötig." in notices
    assert ("Mo: Tagessoll 10:20 h – geplanter Verstoß gegen § 3 ArbZG; eine Erfassung nach diesem Plan lehnt "
            "die Zeiterfassung mit 400 ab.") in notices


def test_lunch_gap_of_30_minutes_at_grace_15_disappears():
    notices = block_break_notices(block_week(mon=[("08:00", "12:00"), ("12:30", "16:30")]), 15, exempt=False)
    assert any(n.startswith("Mo: Die Lücke 12:00–12:30 ist nicht länger als der doppelte Puffer (15 Min)") for n in notices)


def test_long_stretch_without_gap_when_pause_is_zero():
    notices = block_break_notices(block_week(mon=[("07:00", "14:00"), ("14:30", "16:00")]), 0, exempt=False)
    assert ("Mo: geplant mehr als 6 Stunden am Stück ohne Lücke von mindestens 15 Minuten (07:00–14:00) – "
            "nach § 4 ArbZG ist spätestens nach 6 Stunden eine Pause nötig.") in notices


def test_pause_inside_the_blocks_counts_for_section_4():
    assert block_break_notices(block_week(pause=45, mon=[("07:00", "17:00")]), 15, exempt=False) == [
        "Mo: Tagessoll 9:15 h – mehr als 8 Stunden sind nur zulässig, wenn im Durchschnitt von 24 Wochen "
        "8 Stunden je Werktag nicht überschritten werden (§ 3 ArbZG)."
    ]


def test_week_over_48_hours():
    day = [("07:00", "17:00")]
    notices = block_break_notices(block_week(pause=45, mon=day, tue=day, wed=day, thu=day, fri=day), 15, exempt=False)
    assert "Wochensoll 46:15 h – mehr als 48 Stunden je Woche (§ 3 ArbZG)." not in notices
    week = block_week(mon=day, tue=day, wed=day, thu=day, fri=day)
    assert "Wochensoll 50:00 h – mehr als 48 Stunden je Woche (§ 3 ArbZG)." in block_break_notices(week, 15, exempt=False)


def test_exempt_keeps_only_the_gap_notice():
    week = block_week(mon=[("07:00", "12:00"), ("12:10", "17:10")])
    notices = block_break_notices(week, 15, exempt=True)
    assert len(notices) == 1 and notices[0].startswith("Mo: Die Lücke 12:00–12:10")


def test_plain_plan_and_empty_input_give_no_notice():
    assert block_break_notices(block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")]), 15, exempt=False) == []
    assert block_break_notices(None, 15, exempt=False) == []
```

- [ ] **Step 2: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_work_blocks_plan_notices.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'block_break_notices'`.

- [ ] **Step 3: Implementieren**

Am Ende von `backend/app/services/work_blocks_service.py`:

```python
def _hm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _stretches(spans: list) -> list:
    """Zusammenhängende Arbeitsstrecken: Blöcke mit einer Lücke unter 15 Minuten
    gelten als eine Strecke (§ 4 ArbZG: Pausenabschnitte ab 15 Minuten)."""
    merged = []
    for start, end in spans:
        if merged and start - merged[-1][1] < 15:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def block_break_notices(week: Optional[list], grace: int, *, exempt: bool) -> list:
    """Spec P9 — nicht blockierende Plan-Hinweise aus dem GANZEN Tagesplan.

    (a) § 4: geplante Arbeit = Σ Blöcke − Pause, Bedarf 30 bzw. 45 Min; geplante
        Pausen = Pause + Σ ROHE Lücken ≥ 15 Min; bei Pause 0 zusätzlich eine
        Strecke ohne Lücke ≥ 15 Min über 6 h.
    (b) Eine Lücke ≤ 2 × aktueller Puffer verschwindet in der Anrechnung.
    (c) § 3: Tagessoll > 10 h (geplanter Verstoß), > 8 h (24-Wochen-Schnitt),
        Wochensoll > 48 h.
    ``exempt`` (§ 18 ArbZG) unterdrückt (a) und (c). Erwartet eine gültige neue
    Woche (``validate_week_blocks``); Altzeilen/``None`` → keine Hinweise."""
    notices: list = []
    if not week:
        return notices
    weekly_net = 0
    for idx, day in enumerate(week):
        spans = [(hhmm_to_minutes(b["start"]), hhmm_to_minutes(b["end"])) for b in day.get("blocks") or []]
        if not spans:
            continue
        label = WEEKDAY_LABELS[idx]
        pause = int(day.get("pause_minutes") or 0)
        net = sum(end - start for start, end in spans) - pause
        weekly_net += net
        gaps = [(spans[i][1], spans[i + 1][0]) for i in range(len(spans) - 1)]
        if not exempt:
            need = 45 if net > 9 * 60 else 30 if net > 6 * 60 else 0
            planned = pause + sum(ge - gs for gs, ge in gaps if ge - gs >= 15)
            if need and planned < need:
                notices.append(
                    f"{label}: geplant {_hm(net)} h Arbeit, eingeplante Pausen {planned} Min – "
                    f"nach § 4 ArbZG sind mindestens {need} Minuten nötig."
                )
            elif pause == 0:
                for start, end in _stretches(spans):
                    if end - start > 6 * 60:
                        notices.append(
                            f"{label}: geplant mehr als 6 Stunden am Stück ohne Lücke von mindestens "
                            f"15 Minuten ({minutes_to_hhmm(start)}–{minutes_to_hhmm(end)}) – nach § 4 ArbZG "
                            f"ist spätestens nach 6 Stunden eine Pause nötig."
                        )
                        break
        for gs, ge in gaps:
            if ge - gs <= 2 * grace:
                notices.append(
                    # Wortlaut zusammenhängend halten — das Doku-Gate (PR4) sucht ihn per grep.
                    f"{label}: Die Lücke {minutes_to_hhmm(gs)}–{minutes_to_hhmm(ge)} "
                    f"ist nicht länger als der doppelte Puffer ({grace} Min) und wird vollständig angerechnet. "
                    f"Eine geplante Pause bitte als „Pause innerhalb der Blöcke“ erfassen."
                )
        if not exempt:
            if net > 10 * 60:
                notices.append(
                    f"{label}: Tagessoll {_hm(net)} h – geplanter Verstoß gegen § 3 ArbZG; eine Erfassung "
                    f"nach diesem Plan lehnt die Zeiterfassung mit 400 ab."
                )
            elif net > 8 * 60:
                notices.append(
                    f"{label}: Tagessoll {_hm(net)} h – mehr als 8 Stunden sind nur zulässig, wenn im "
                    f"Durchschnitt von 24 Wochen 8 Stunden je Werktag nicht überschritten werden (§ 3 ArbZG)."
                )
    if not exempt and weekly_net > 48 * 60:
        notices.append(f"Wochensoll {_hm(weekly_net)} h – mehr als 48 Stunden je Woche (§ 3 ArbZG).")
    return notices
```

- [ ] **Step 4: Test laufen lassen — muss grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_work_blocks_plan_notices.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/work_blocks_service.py backend/tests/test_work_blocks_plan_notices.py
git commit -F - <<'EOF'
feat(bloecke): Plan-Hinweise zu § 3/§ 4 ArbZG und verschwindenden Lücken (P9)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 6: Wirkungsfenster mit Zeiteinträgen und F1-Klemmung (Spec 9.1, 9.6, E51, P27)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#493/#494/#496/#500/#501 haben `calculation_service.py` erweitert; die hier geänderten Funktionen `retarget_window`/`retarget_absence_hours` sind laut PR1-Abgleich unverändert — vor Step 4 per `grep -n "def retarget_window\|def retarget_absence_hours\|class AbsenceRetarget\|class RetargetWindow" backend/app/services/calculation_service.py` die Anker prüfen.)

**Files:**
- Modify: `backend/app/services/calculation_service.py` (`RetargetWindow`, `retarget_window`, `AbsenceRetarget`, `retarget_absence_hours`, neu `absence_full_targets`)
- Modify: `backend/app/routers/admin_users.py` (die drei Aufrufe von `retarget_absence_hours` — Übergangsstand bis Task 9–11)
- Create: `backend/tests/wh_change_helpers.py`
- Test (neu): `backend/tests/test_retarget_f1.py`
- Modify (Aufrufstellen): `backend/tests/test_retarget_absence_hours.py`, `test_retarget_day_plan.py`, `test_absence_raw_hours.py`

**Interfaces:**
- Consumes: `credit_day_weight`, `get_daily_target_for_date`, `get_schedule_for_date` (Bestand/PR1); `TimeEntry.net_hours` (PR1 Task 4)
- Produces:
  - `RetargetWindow(start, end, last_absence, last_time_entry)` + Eigenschaft `has_time_entries`; offenes Ende = `max(effective_from, heute, last_absence, last_time_entry)`
  - `AbsenceRetarget` + Pflichtfelder `f1_clamped: bool`, `credit_reduction: bool`
  - `retarget_absence_hours(db, user, start, end, *, old_full_target_by_date: Dict[date, Decimal], dry_run: bool = False) -> List[AbsenceRetarget]` — F1 nach Spec 9.6 (`kept_net_by_date` aus geschlossenen Einträgen, nach dem flush der Neukappung geladen)
  - `absence_full_targets(db, user, start, end) -> Dict[date, Decimal]` — volles Tagessoll je Nicht-OVERTIME-Abwesenheitsdatum im Fenster, mit dem zum Aufrufzeitpunkt gültigen Snapshot (Spec 9.3 Schritt 3)
  - Test-Bausteine `tests/wh_change_helpers.py`: `TODAY`, `EFF`, `MONDAYS`, `RETRO_REASON`, `ANNA_WEEK`, `t`, `freeze`, `with_pauses`, `change_row`, `add_row`, `entry`, `absence`, `set_grace`, `admin_client`, `reclamp_logs`

- [ ] **Step 1: Test-Bausteine anlegen**

`backend/tests/wh_change_helpers.py`:

```python
"""Test-Bausteine für PR3 (Spec 9–12): eingefrorenes „heute", Verlaufszeilen,
Einträge, Abwesenheiten. Eine Quelle für alle Neukappungs-Suiten, damit „heute",
Puffer und Verlaufszeilen überall gleich gebaut werden."""
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, TimeEntry, TimeEntryAuditLog, WorkingHoursChange
from app.models.system_setting import SystemSetting
from app.services import timezone_service, work_blocks_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.work_blocks_fixtures import block_week

TODAY = date(2026, 10, 8)      # Donnerstag — Beispiel aus Spec 12.1
EFF = date(2026, 9, 1)         # Dienstag
MONDAYS = (date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28), date(2026, 10, 5))

# Ein vollständiges Schutzpaket (Spec 9.5) für Suiten, die die Rückrechnung
# prüfen und nicht das Schutzpaket selbst.
RETRO_REASON = {
    "retroactive_reason_type": "erfassungsfehler",
    "retroactive_reason_text": "Hinterlegte Arbeitszeit war falsch erfasst",
    "wage_risk_confirmed": True,
}

# Spec 12.1: Anna — Mo 08–12 + 15–18, Di 08–12, Do 08–12, Pause 0 → 15 h/Woche.
ANNA_WEEK = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                       thu=[("08:00", "12:00")])

_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri")


def t(h: int, m: int = 0) -> time:
    return time(h, m)


def freeze(monkeypatch, d: date = TODAY, at: time = time(10, 0)) -> None:
    """„Heute"/„jetzt" für ALLE Aufrufer: ``today_local`` löst ``now_local`` zur
    Laufzeit über die Modulglobalen von ``timezone_service`` auf."""
    monkeypatch.setattr(timezone_service, "now_local",
                        lambda: datetime.combine(d, at, tzinfo=timezone_service.LOCAL_TZ))


def with_pauses(week: list, **pauses: int) -> list:
    """Kopie der Woche mit Pausen je Tag (``mon=60``) — ``block_week`` setzt eine
    Pause für alle Tage mit Blöcken."""
    out = [dict(day, blocks=[dict(b) for b in day["blocks"]]) for day in week]
    for key, minutes in pauses.items():
        out[_DAY_KEYS.index(key)]["pause_minutes"] = minutes
    return out


def change_row(user, effective_from: date, *, week=None, weekly_hours=None, day_hours=None,
               blocks=None, note=None) -> WorkingHoursChange:
    """Ungespeicherte Verlaufszeile: NEUE Blöcke (``week``, Soll materialisiert wie
    der Dialog), Tagesplan (``day_hours``) oder gleichmäßig (``weekly_hours``);
    ``blocks`` setzt bei den beiden letzten ein Altfenster."""
    common = dict(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=effective_from, note=note)
    if week is not None:
        d = work_blocks_service.derive_targets(week)
        return WorkingHoursChange(
            **common, weekly_hours=d["weekly_hours"], use_daily_schedule=True,
            **{f: d[f] for f in work_blocks_service.HOURS_FIELDS},
            work_days_per_week=d["work_days_per_week"], blocks=week,
        )
    if day_hours is not None:
        values = [Decimal(str(v)) if v else None for v in day_hours]
        return WorkingHoursChange(
            **common, weekly_hours=sum((v for v in values if v), Decimal("0")), use_daily_schedule=True,
            **dict(zip(work_blocks_service.HOURS_FIELDS, values)),
            work_days_per_week=sum(1 for v in values if v), blocks=blocks,
        )
    return WorkingHoursChange(**common, weekly_hours=Decimal(str(weekly_hours)), use_daily_schedule=False,
                              work_days_per_week=5, blocks=blocks)


def add_row(db, user, effective_from: date, **kwargs) -> WorkingHoursChange:
    row = change_row(user, effective_from, **kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def entry(db, user, d: date, start: time, end: Optional[time], *, raw_start=None, raw_end=None,
          uncredited: int = 0, grace: Optional[int] = 15, brk: int = 0, credit_override: bool = False,
          auto_closed: bool = False) -> TimeEntry:
    e = TimeEntry(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d, start_time=start, end_time=end,
        raw_start_time=raw_start, raw_end_time=raw_end, break_minutes=brk, uncredited_minutes=uncredited,
        clamp_grace_minutes=grace, credit_override=credit_override, auto_closed=auto_closed,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def absence(db, user, d: date, typ=AbsenceType.SICK, hours: float = 8.0, half_day: bool = False) -> Absence:
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=typ, hours=hours, half_day=half_day)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def set_grace(db, minutes: int) -> None:
    db.add(SystemSetting(key="work_window_grace_minutes", value=str(minutes), tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def admin_client(db, admin) -> TestClient:
    """TestClient mit überschriebener DB/Auth — der Aufrufer räumt per
    ``test_app.dependency_overrides.clear()`` auf (Fixture-Teardown)."""
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: admin
    test_app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(test_app)


def reclamp_logs(db, user, *, summary: Optional[bool] = None) -> list:
    """``wh_reclamp``-Zeilen der Person; ``summary=True`` nur Sammelzeilen,
    ``False`` nur Einzelzeilen."""
    q = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == user.id,
        TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID,
        TimeEntryAuditLog.source == "wh_reclamp",
    )
    if summary is True:
        q = q.filter(TimeEntryAuditLog.time_entry_id.is_(None), TimeEntryAuditLog.old_date.is_(None))
    elif summary is False:
        q = q.filter(TimeEntryAuditLog.time_entry_id.isnot(None))
    return q.order_by(TimeEntryAuditLog.created_at).all()
```

- [ ] **Step 2: Failing tests schreiben**

`backend/tests/test_retarget_f1.py`:

```python
"""Spec 9.6 (E51, P27): F1-Klemmung in retarget_absence_hours und Wirkungsfenster
mit Zeiteinträgen (9.1). Tabelle 9.6: Tagessoll vorher 8 h, 4 h Arbeit am Krank-Tag."""
from datetime import date, timedelta
from decimal import Decimal

from app.models import AbsenceType
from app.models.system_setting import SystemSetting
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import absence, add_row, entry, freeze, t

MON = date(2026, 9, 14)
WINDOW = (date(2026, 9, 1), date(2026, 9, 30))
OLD = {MON: Decimal("8")}


def _run(db, user, old=OLD):
    return cs.retarget_absence_hours(db, user, *WINDOW, old_full_target_by_date=old)


def test_regular_clamped_mixed_day_with_target_drop_is_not_a_reduction(db, test_user):
    a = absence(db, test_user, MON, AbsenceType.SICK, 4.0)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
    [rec] = _run(db, test_user)
    assert (rec.old_hours, rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (
        Decimal("4.00"), Decimal("2.00"), True, False)
    db.refresh(a)
    assert float(a.hours) == 2.0


def test_double_credit_before_1_18_with_unchanged_target_is_a_reduction(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    [rec] = _run(db, test_user)
    assert (rec.old_hours, rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (
        Decimal("8.00"), Decimal("4.00"), True, True)


def test_double_credit_with_target_drop_is_a_reduction(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
    [rec] = _run(db, test_user)
    assert (rec.new_hours, rec.credit_reduction) == (Decimal("2.00"), True)


def test_entry_gaining_on_a_mixed_day_reduces_the_credit(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 4.0)
    entry(db, test_user, MON, t(8), t(13), grace=None)   # nach der Neukappung 5 h Arbeit
    [rec] = _run(db, test_user)
    assert (rec.old_hours, rec.new_hours, rec.credit_reduction) == (Decimal("4.00"), Decimal("3.00"), True)


def test_already_clamped_and_unchanged_is_not_returned(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 4.0)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    assert _run(db, test_user) == []


def test_rounding_to_0_01_hours(db, test_user):
    """Tagessoll 7,92 h: (2 − 3,92) gegen (6 − 7,92) — beide −1,92."""
    add_row(db, test_user, date(2026, 1, 1), day_hours=(7.92, 8, 8, 8, 8))
    absence(db, test_user, MON, AbsenceType.SICK, 3.92)
    entry(db, test_user, MON, t(8), t(12), grace=None)
    add_row(db, test_user, date(2026, 9, 1), day_hours=(6, 8, 8, 8, 8))
    [rec] = _run(db, test_user, {MON: Decimal("7.92")})
    assert (rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (Decimal("2.00"), True, False)


def test_sick_day_without_work_follows_the_target(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
    [rec] = _run(db, test_user)
    assert (rec.new_hours, rec.f1_clamped, rec.credit_reduction) == (Decimal("6.00"), False, False)


def test_open_entries_do_not_count_as_kept_work(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    entry(db, test_user, MON, t(8), None, grace=None)
    assert _run(db, test_user) == []


def test_half_special_day_stays_saldo_neutral(db, test_user):
    """Spec 9.6: 24.12. halber Sondertag + Krank + 3 h Arbeit, Tagessoll 8 →
    Soll 4 h, Gutschrift höchstens 1 h, Saldo des Tages 0."""
    xmas = date(2026, 12, 24)
    db.add(SystemSetting(key="special_day_dec24_mode", value="half_day", tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    absence(db, test_user, xmas, AbsenceType.SICK, 8.0)
    entry(db, test_user, xmas, t(8), t(11), grace=None)
    [rec] = cs.retarget_absence_hours(db, test_user, date(2026, 12, 1), date(2026, 12, 31),
                                      old_full_target_by_date={xmas: Decimal("8")})
    assert rec.new_hours == Decimal("2.00")   # × Gewicht 0,5 = 1 h Gutschrift
    saldo = cs.get_range_actual(db, test_user, xmas, xmas) - cs.get_range_target(db, test_user, xmas, xmas)
    assert saldo == Decimal("0")


def test_absence_full_targets_skips_overtime(db, test_user):
    absence(db, test_user, MON, AbsenceType.SICK, 8.0)
    absence(db, test_user, MON + timedelta(days=1), AbsenceType.OVERTIME, 8.0)
    assert cs.absence_full_targets(db, test_user, *WINDOW) == {MON: Decimal("8")}


def test_retarget_window_knows_time_entries(db, test_user, monkeypatch):
    freeze(monkeypatch)
    future = date(2026, 10, 20)
    entry(db, test_user, future, t(8), t(12), grace=None)
    w = cs.retarget_window(db, test_user, date(2026, 9, 1))
    assert (w.last_time_entry, w.has_time_entries, w.end) == (future, True, future)
    add_row(db, test_user, date(2026, 10, 12), weekly_hours=30)
    w = cs.retarget_window(db, test_user, date(2026, 9, 1))
    assert (w.last_time_entry, w.has_time_entries, w.end) == (None, False, date(2026, 10, 11))
```

- [ ] **Step 3: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_retarget_f1.py -q -p no:cacheprovider`
Expected: FAIL — `TypeError: retarget_absence_hours() got an unexpected keyword argument 'old_full_target_by_date'`.

- [ ] **Step 4: `calculation_service.py` umbauen**

`RetargetWindow` — nach `last_absence: Optional[date]` (samt Docstring) einfügen und eine Eigenschaft ergänzen:

```python
    last_time_entry: Optional[date]
    """Spec 9.1: spätestes Zeiteintragsdatum im Bereich; ``None`` = keiner."""

    @property
    def has_time_entries(self) -> bool:
        return self.last_time_entry is not None
```

`retarget_window` — nach `last_absence = absence_q.scalar()`:

```python
    # Spec 9.1: auch Zeiteinträge bestimmen das offene Ende — die Neukappung
    # muss jeden bereits erfassten Eintrag im Wirkungsbereich erreichen.
    entry_q = db.query(func.max(TimeEntry.date)).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026
        TimeEntry.date >= effective_from,
    )
    if hard_end is not None:
        entry_q = entry_q.filter(TimeEntry.date <= hard_end)
    last_time_entry = entry_q.scalar()
```

und das offene Ende sowie die Rückgabe:

```python
        end = max(d for d in (effective_from, today_local(), last_absence, last_time_entry) if d is not None)

    return RetargetWindow(start=effective_from, end=end, last_absence=last_absence,
                          last_time_entry=last_time_entry)
```

`AbsenceRetarget` — nach `absence_type: AbsenceType`:

```python
    # Spec 9.6 (P6: ohne Vorgabewert): hat die F1-Klemmung gegriffen, und senkt
    # sie die Gutschrift STÄRKER als das Tagessoll des Tages (9.5 (c))?
    f1_clamped: bool
    credit_reduction: bool
```

`retarget_absence_hours` — Signatur:

```python
def retarget_absence_hours(
    db: Session,
    user: User,
    start: date,
    end: date,
    *,
    old_full_target_by_date: Dict[date, Decimal],
    dry_run: bool = False,
) -> List[AbsenceRetarget]:
```

Im Docstring vor „``dry_run=True`` ermittelt nur" einfügen:

```python
    Spec 9.6 (E51): F1-Klemmung — bleiben am Tag GESCHLOSSENE Zeiteinträge
    stehen, wird ``hours`` auf den nicht gearbeiteten Rest geklemmt (gleiche Regel
    wie ``absences.create_absence``), in Gutschrifts-Einheiten über
    :func:`credit_day_weight`. ``kept_net_by_date`` wird hier geladen — nach dem
    flush der Neukappung, also mit den neuen Netto-Werten. ``credit_reduction``
    markiert eine Senkung STÄRKER als das Tagessoll (9.5 (c)); dafür braucht es
    das volle Tagessoll VOR der Änderung (``old_full_target_by_date``, Pflicht,
    :func:`absence_full_targets`).
```

Nach dem Laden von `absences` einfügen:

```python
    kept_net_by_date: Dict[date, float] = {}
    for kept in db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026
        TimeEntry.date >= start,
        TimeEntry.date <= end,
        TimeEntry.end_time.isnot(None),
    ).all():
        kept_net_by_date[kept.date] = kept_net_by_date.get(kept.date, 0.0) + float(kept.net_hours)
    special_cfgs = {
        yr: special_days_service.get_special_day_config(db, user.tenant_id, yr)
        for yr in {a.date.year for a in absences if (a.date.month, a.date.day) in ((12, 24), (12, 31))}
    }
```

In der Schleife den Block ab `new_hours = (target / 2) if a.half_day else target` bis einschließlich des `changed.append(AbsenceRetarget(...))` ersetzen durch:

```python
        new_hours_f = float((target / 2) if a.half_day else target)
        old_hours_f = float(a.hours)
        f1_clamped = False
        credit_reduction = False
        kept_net = kept_net_by_date.get(d, 0.0)
        if kept_net > 0:
            # Spec 9.6: Vergleich in GUTSCHRIFTS-Einheiten — die Gutschrift ist
            # new_hours × w (Halbtags-Sondertag 0,5, frei 0, sonst 1,0); das
            # wirksame Tagessoll trägt denselben Faktor.
            w = float(credit_day_weight(d, holidays, special_cfgs.get(d.year)))
            if w > 0:
                full_target = float(target)
                cap_credit = max(0.0, full_target * w - kept_net)
                clamped = round(max(0.0, min(new_hours_f, cap_credit / w)), 2)
                f1_clamped = clamped < new_hours_f
                new_hours_f = clamped
                if f1_clamped and new_hours_f < old_hours_f:
                    old_full = float(old_full_target_by_date[d])
                    credit_reduction = (round((new_hours_f - old_hours_f) * w, 2)
                                        < round((full_target - old_full) * w, 2))
        new_hours = Decimal(str(new_hours_f)).quantize(Decimal('0.01'))
        old_hours = Decimal(str(a.hours)).quantize(Decimal('0.01'))
        if old_hours == new_hours:
            continue

        # KEINE stille Obergrenze (CLAUDE.md „no silent caps").
        changed.append(AbsenceRetarget(
            absence_id=a.id, date=d, old_hours=old_hours,
            new_hours=new_hours, absence_type=a.type,
            f1_clamped=f1_clamped, credit_reduction=credit_reduction,
        ))
```

Nach `retarget_absence_hours` einfügen:

```python
def absence_full_targets(db: Session, user: User, start: date, end: date) -> Dict[date, Decimal]:
    """Spec 9.3 Schritt 3: das VOLLE Tagessoll je Abwesenheitsdatum (ohne
    OVERTIME) im Fenster, mit dem zum Aufrufzeitpunkt gültigen Snapshot. Der
    Aufrufer ruft das VOR dem Anwenden der Änderung — es ist das „vorher" für
    das Kriterium 9.5 (c)."""
    if start > end:
        return {}
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
    ).all()
    dates = {
        row[0] for row in db.query(Absence.date).filter(
            Absence.user_id == user.id,
            Absence.tenant_id == user.tenant_id,  # F-026
            Absence.date >= start,
            Absence.date <= end,
            Absence.type != AbsenceType.OVERTIME,
        ).all()
    }
    return {
        d: get_daily_target_for_date(user, d, get_schedule_for_date(db, user, d, wh_changes))
        for d in dates
    }
```

- [ ] **Step 5: Übergangsstand der drei Router-Aufrufe (`admin_users.py`)**

Die Endpunkte werden in Task 9–11 neu geschrieben; bis dahin brauchen sie nur das Pflichtargument, berechnet **vor** dem Anwenden der Änderung.

`create_working_hours_change`: unmittelbar vor `change = WorkingHoursChange(` einfügen

```python
    _window_before = calculation_service.retarget_window(db, user, change_data.effective_from)
    _old_full = calculation_service.absence_full_targets(db, user, _window_before.start, _window_before.end)
```

und im Aufruf `calculation_service.retarget_absence_hours(db, user, window.start, window.end)` das Argument `old_full_target_by_date=_old_full` ergänzen.

`preview_working_hours_change`: direkt vor `try:` des Simulationsblocks

```python
        _old_full = calculation_service.absence_full_targets(db, user, period_start, period_end)
```

und `old_full_target_by_date=_old_full` am Aufruf ergänzen.

`delete_working_hours_change`: unmittelbar vor `db.delete(change)`

```python
    _window_before = calculation_service.retarget_window(db, user, change.effective_from)
    _old_full = calculation_service.absence_full_targets(db, user, _window_before.start, _window_before.end)
```

und `old_full_target_by_date=_old_full` am Aufruf ergänzen.

- [ ] **Step 6: Bestehende Test-Aufrufe ergänzen**

Diese Suiten rufen `retarget_absence_hours` ohne Zeiteinträge auf — das Vorher-Tagessoll wird dort nie gelesen, `{}` genügt. Aus der Repo-Wurzel:

```bash
python3 - <<'PYEOF'
import pathlib
token = "retarget_absence_hours("
for name in ("test_retarget_absence_hours.py", "test_retarget_day_plan.py", "test_absence_raw_hours.py"):
    path = pathlib.Path("backend/tests") / name
    src = path.read_text(encoding="utf-8")
    out, i = [], 0
    while True:
        j = src.find(token, i)
        if j == -1:
            out.append(src[i:])
            break
        k, depth = j + len(token), 1
        while depth:
            depth += {"(": 1, ")": -1}.get(src[k], 0)
            k += 1
        call = src[j:k]
        if "old_full_target_by_date" not in call:
            call = call[:-1].rstrip().rstrip(",") + ", old_full_target_by_date={})"
        out.append(src[i:j])
        out.append(call)
        i = k
    path.write_text("".join(out), encoding="utf-8")
    print(name, src.count(token), "Aufrufe")
PYEOF
grep -c "old_full_target_by_date={}" backend/tests/test_retarget_absence_hours.py backend/tests/test_retarget_day_plan.py backend/tests/test_absence_raw_hours.py
```

Expected: je Datei gleiche Zahl Aufrufe und Treffer (Stand `3d46c2f`: 8 / 2 / 6).

- [ ] **Step 7: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_retarget_f1.py tests/test_retarget_absence_hours.py tests/test_retarget_day_plan.py tests/test_absence_raw_hours.py tests/test_wh_change_retroactive.py tests/test_wh_change_preview.py tests/test_wh_change_day_plan_delete.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/calculation_service.py backend/app/routers/admin_users.py backend/tests/wh_change_helpers.py backend/tests/test_retarget_f1.py backend/tests/test_retarget_absence_hours.py backend/tests/test_retarget_day_plan.py backend/tests/test_absence_raw_hours.py
git commit -F - <<'EOF'
feat(bloecke): F1-Klemmung in der Abwesenheits-Rückrechnung, Wirkungsfenster mit Zeiteinträgen (9.1, 9.6)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 7: Neukappungs-Kern `reclamp_time_entries` und P1-Knickstellen (Spec 9.2, E47–E50, P1)

**Files:**
- Modify: `backend/app/services/work_window_service.py` (Importe, neue Typen und Funktionen am Dateiende)
- Test (neu): `backend/tests/test_reclamp_core.py`

**Interfaces:**
- Consumes: `clamp`, `credit_gaps`, `get_scheduled_blocks`, `_min`, `_shift_min`, `_overlap`, `_LAST_MINUTE` (PR1 Task 3); `calculation_service.get_schedule_for_date`, `_within_employment_window`; `special_days_service.free_special_days_in_range`; Test-Bausteine aus Task 6; im Test `rest_time_service.check_rest_time_violations(db, user, year, month=None)` (Bestand, §5 auf `raw_end_time or end_time`)
- Produces (in `app.services.work_window_service`):
  - `class ReclampChange(NamedTuple): entry_id; date; old_start; old_end; old_uncredited: int; old_net: Decimal; new_start; new_end; new_uncredited: int; new_net: Decimal; not_extendable: Optional[str]; old_grace: Optional[int]`
  - `class ReclampSkip(NamedTuple): entry_id; date; reason: str` (`open | soll_free_day | track_hours_off | outside_employment | credit_override | unique_collision`)
  - `class ReclampResult(NamedTuple): changed: list; skipped: list; flagged: list`
  - `reclamp_time_entries(db, user, start: date, end: date, weekdays: set[int], prev_blocks_by_weekday: Optional[tuple], grace: int) -> ReclampResult` — setzt ORM-Attribute, kein commit, kein Protokoll
  - `credited_minutes_for(blocks: list[tuple[int, int]], grace: int, start_min: int, end_min: int) -> int` (rein, ohne Pause)
  - `open_entry_loses(old_blocks: list, new_blocks: list, grace: int, start: time, now: time) -> bool` (P1-Knickstellen-Prüfung)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_reclamp_core.py`:

```python
"""Spec 9.2 (E47–E50) und P1: Massen-Neukappung und Knickstellen-Prüfung."""
from datetime import date, time
from decimal import Decimal

from app.models import User, UserRole
from app.models.public_holiday import PublicHoliday
from app.services import rest_time_service, work_blocks_service, work_window_service as wws
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import add_row, entry, t
from tests.work_blocks_fixtures import K_BLOCKS, block_week

MON = date(2026, 6, 1)
JUNE = (date(2026, 6, 1), date(2026, 6, 30))
OLD = block_week(mon=[("08:00", "18:00")], tue=[("08:00", "12:00")])
NEW = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")])


def _setup(db, user, old=OLD, new=NEW):
    add_row(db, user, date(2026, 1, 1), week=old)
    add_row(db, user, MON, week=new)
    return work_blocks_service.parse_week_blocks(old).blocks


def _run(db, user, prev, weekdays=(0,), grace=15):
    return wws.reclamp_time_entries(db, user, *JUNE, set(weekdays), prev, grace)


def test_gap_is_withheld_and_stamps_stay(db, test_user):
    prev = _setup(db, test_user)
    e = entry(db, test_user, MON, t(8), t(18))
    result = _run(db, test_user, prev)
    [c] = result.changed
    assert (c.old_net, c.new_net, c.old_uncredited, c.new_uncredited) == (Decimal("10.00"), Decimal("7.50"), 0, 150)
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time) == (t(8), t(18), None, None)
    assert (e.uncredited_minutes, e.clamp_grace_minutes, c.old_grace) == (150, 15, 15)
    assert result.skipped == [] and result.flagged == []


def test_hull_shrink_starts_from_the_raw_stamps(db, test_user):
    """E48: Quelle ist der Rohstempel — kein kumulatives Doppelkappen."""
    prev = _setup(db, test_user, new=block_week(mon=[("09:00", "17:00")], tue=[("08:00", "12:00")]))
    e = entry(db, test_user, MON, t(7, 45), t(18, 15), raw_start=t(7), raw_end=t(19))
    [c] = _run(db, test_user, prev).changed
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time) == (t(8, 45), t(17, 15), t(7), t(19))
    assert (c.old_net, c.new_net) == (Decimal("10.50"), Decimal("8.50"))


def test_unchanged_entry_only_gets_the_current_grace(db, test_user):
    """E47/E79: jeder geprüfte Eintrag an einem geänderten Wochentag bekommt den
    aktuellen Puffer — ohne Zeile in ``changed``."""
    prev = _setup(db, test_user)
    e = entry(db, test_user, MON, t(8), t(12), grace=None)
    result = _run(db, test_user, prev, grace=10)
    assert result.changed == [] and e.clamp_grace_minutes == 10


def test_unchanged_weekday_is_not_touched(db, test_user):
    prev = _setup(db, test_user)
    tue = entry(db, test_user, date(2026, 6, 2), t(8), t(12), grace=10)
    assert _run(db, test_user, prev, grace=15) == wws.ReclampResult([], [], [])
    assert tue.clamp_grace_minutes == 10


def test_every_skip_reason_is_reported(db, test_user):
    prev = _setup(db, test_user)
    db.add(PublicHoliday(date=date(2026, 6, 8), name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    invalidate_holiday_cache()
    test_user.last_work_day = date(2026, 6, 20)
    db.commit()
    entry(db, test_user, MON, t(8), None)
    entry(db, test_user, date(2026, 6, 8), t(8), t(18))
    entry(db, test_user, date(2026, 6, 15), t(15), t(18), credit_override=True)
    entry(db, test_user, date(2026, 6, 22), t(8), t(18))
    reasons = {s.date: s.reason for s in _run(db, test_user, prev).skipped}
    invalidate_holiday_cache()
    assert reasons == {
        MON: "open",
        date(2026, 6, 8): "soll_free_day",
        date(2026, 6, 15): "credit_override",
        date(2026, 6, 22): "outside_employment",
    }


def test_track_hours_off_skips_everything(db, default_tenant):
    lead = User(username="leitend", email="l@x.de", password_hash="h", first_name="L", last_name="T",
                role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
                track_hours=False, tenant_id=DEFAULT_TENANT_ID)
    db.add(lead)
    db.commit()
    prev = _setup(db, lead)
    e = entry(db, lead, MON, t(8), t(18))
    result = _run(db, lead, prev)
    assert [s.reason for s in result.skipped] == ["track_hours_off"]
    assert e.uncredited_minutes == 0


def test_unique_collision_keeps_the_entry(db, test_user):
    prev = _setup(db, test_user, old=block_week(mon=[("08:00", "12:00")]),
                  new=block_week(mon=[("08:05", "12:00")]))
    a = entry(db, test_user, MON, t(7, 45), t(9), raw_start=t(7, 30))
    entry(db, test_user, MON, t(7, 50), t(7, 55))
    result = _run(db, test_user, prev)
    assert [(s.entry_id, s.reason) for s in result.skipped] == [(a.id, "unique_collision")]
    assert (a.start_time, a.raw_start_time) == (t(7, 45), t(7, 30))


def test_not_extendable_at_the_old_edge(db, test_user):
    """E50: Rohstempel vor 1.19.1 verloren — gespeicherte Zeit liegt exakt auf der
    alten Kante, die neue Hülle ist weiter."""
    prev = _setup(db, test_user, old=block_week(mon=[("15:00", "18:00")]),
                  new=block_week(mon=[("15:00", "19:00")]))
    lost = entry(db, test_user, MON, t(15), t(18, 15))
    kept = entry(db, test_user, date(2026, 6, 8), t(15), t(18, 15), raw_end=t(18, 30))
    result = _run(db, test_user, prev)
    assert [(c.entry_id, c.not_extendable) for c in result.flagged] == [(lost.id, "end")]
    assert [c.entry_id for c in result.changed] == [kept.id]
    assert (kept.end_time, kept.raw_end_time) == (t(18, 30), None)


def test_rest_time_after_reclamp_counts_from_the_raw_stamp(db, test_user):
    """Spec 17.4 / UC-Review R3: nach der Neukappung misst §5 weiter die tatsächliche
    Anwesenheit — Rohstempel 19:00, nicht das gekappte Ende 18:15. Ab 19:00 bis zum
    Folgetag 05:30 sind es 10,5 h (Verstoß); ab 18:15 wären es 11,25 h (keiner)."""
    prev = _setup(db, test_user, old=block_week(mon=[("08:00", "19:00")], tue=[("08:00", "12:00")]),
                  new=block_week(mon=[("08:00", "18:00")], tue=[("08:00", "12:00")]))
    e = entry(db, test_user, MON, t(8), t(19))
    entry(db, test_user, date(2026, 6, 2), t(5, 30), t(9))   # Dienstag, nicht neu gekappt (weekdays={0})
    [c] = _run(db, test_user, prev).changed
    assert (c.entry_id, e.end_time, e.raw_end_time) == (e.id, t(18, 15), t(19))
    db.flush()
    [v] = rest_time_service.check_rest_time_violations(db, test_user, 2026, month=6)
    assert (v["day1_date"], v["day1_end"], v["day2_start"], v["actual_rest_hours"]) == (
        "2026-06-01", "19:00:00", "05:30:00", 10.5)


def test_second_run_changes_nothing(db, test_user):
    prev = _setup(db, test_user)
    entry(db, test_user, MON, t(8), t(18))
    assert len(_run(db, test_user, prev).changed) == 1
    db.flush()
    again = _run(db, test_user, prev)
    assert again.changed == [] and again.skipped == []


def test_split_stamps_around_the_planned_gap(db, test_user):
    """Review Focus 2: zwei Einträge um die Mittagslücke — Beginnzeiten bleiben,
    jeder Eintrag trägt seine eigenen Lückenminuten, keine Kollision."""
    prev = _setup(db, test_user)
    morning = entry(db, test_user, MON, t(8), t(12, 40))
    afternoon = entry(db, test_user, MON, t(14, 20), t(18))
    result = _run(db, test_user, prev)
    assert result.skipped == []
    assert (morning.start_time, morning.uncredited_minutes) == (t(8), 25)
    assert (afternoon.start_time, afternoon.uncredited_minutes) == (t(14, 20), 25)


def test_auto_closed_entry_reclamps_from_its_synthetic_end(db, test_user):
    prev = _setup(db, test_user)
    e = entry(db, test_user, MON, t(8), t(18, 15), raw_end=t(23, 59), auto_closed=True)
    [c] = _run(db, test_user, prev).changed
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes, e.auto_closed) == (t(18, 15), t(23, 59), 150, True)
    assert c.new_net == Decimal("7.75")


def test_credited_minutes_for():
    k = [(480, 720), (900, 1080)]
    assert wws.credited_minutes_for(k, 15, 480, 1080) == 450        # K1
    assert wws.credited_minutes_for(k, 15, 420, 1140) == 480        # K7: Hülle + Lücke
    assert wws.credited_minutes_for(k, 15, 300, 420) == 0           # K8: Kollaps
    assert wws.credited_minutes_for([], 15, 480, 1080) == 600


def test_open_entry_loses_checks_every_kink():
    old = [(480, 720)]
    assert wws.open_entry_loses(old, [(480, 780)], 15, time(8), time(10)) is False   # Verlängerung
    assert wws.open_entry_loses(old, [(480, 660)], 15, time(8), time(10)) is True    # Hülle kürzer
    assert wws.open_entry_loses(old, [(480, 660)], 15, time(8), time(13)) is True    # auch nach Hüllenende
    assert wws.open_entry_loses(old, [(540, 720)], 15, time(8), time(8, 10)) is True  # Beginn vor neuer Hülle
    assert wws.open_entry_loses([(480, 720), (900, 1080)], [(480, 720), (840, 1080)], 15,
                                time(8), time(10)) is False                          # Lücke kleiner
    assert wws.open_entry_loses([], [], 15, time(8), time(10)) is False
```

- [ ] **Step 2: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_reclamp_core.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'app.services.work_window_service' has no attribute 'reclamp_time_entries'`.

- [ ] **Step 3: Implementieren**

`backend/app/services/work_window_service.py` — Importe ergänzen:

```python
from decimal import Decimal
from typing import Any, NamedTuple, Optional

from app.models import TimeEntry, WorkingHoursChange
```

Am Dateiende anhängen:

```python
# ── Spec 9.2: Massen-Neukappung einer Arbeitszeit-Änderung ─────────────────


class ReclampChange(NamedTuple):
    entry_id: Any
    date: date
    old_start: Optional[time]
    old_end: Optional[time]
    old_uncredited: int
    old_net: Decimal
    new_start: Optional[time]
    new_end: Optional[time]
    new_uncredited: int
    new_net: Decimal
    not_extendable: Optional[str]      # None | "start" | "end" | "both" (E50)
    old_grace: Optional[int]           # clamp_grace_minutes vorher (E79)


class ReclampSkip(NamedTuple):
    entry_id: Any
    date: date
    reason: str   # open | soll_free_day | track_hours_off | outside_employment
                  # | credit_override | unique_collision


class ReclampResult(NamedTuple):
    changed: list
    skipped: list
    flagged: list      # nicht erweiterbar, auch wenn unverändert (E50)


def _soll_free_dates(db: Session, tenant_id, start: date, end: date) -> set:
    """Feiertage + freie Sondertage des Fensters — EIN Vorladen für die
    Neukappung (6.1-Vorladeparameter von ``clamp``)."""
    from app.models.public_holiday import PublicHoliday
    from app.services.special_days_service import free_special_days_in_range

    holidays = {
        h.date for h in db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == tenant_id,  # F-026
            PublicHoliday.date >= start,
            PublicHoliday.date <= end,
        ).all()
    }
    return holidays | set(free_special_days_in_range(db, tenant_id, start, end))


def _not_extendable(entry, old_day: list, new_day: list, grace: int,
                    old_grace: Optional[int]) -> Optional[str]:
    """E50: Seite ohne Rohstempel, gespeicherte Zeit exakt auf der ALTEN
    Hüllenkante (mit dem gespeicherten Puffer, sonst dem aktuellen) und die neue
    Hülle ist auf dieser Seite weiter → der Eintrag kann nicht erweitert werden,
    weil der echte Stempel vor 1.19.1 verloren ging."""
    if not old_day or not new_day:
        return None
    g_old = old_grace if old_grace is not None else grace
    sides = []
    if entry.raw_start_time is None and entry.start_time is not None and entry.start_time.second == 0:
        old_floor = _shift_min(old_day[0][0], -g_old)
        if _min(entry.start_time) == old_floor and _shift_min(new_day[0][0], -grace) < old_floor:
            sides.append("start")
    if entry.raw_end_time is None and entry.end_time is not None and entry.end_time.second == 0:
        old_ceil = _shift_min(old_day[-1][1], g_old)
        if _min(entry.end_time) == old_ceil and _shift_min(new_day[-1][1], grace) > old_ceil:
            sides.append("end")
    if not sides:
        return None
    return sides[0] if len(sides) == 1 else "both"


def reclamp_time_entries(db: Session, user, start: date, end: date, weekdays: set,
                         prev_blocks_by_weekday: Optional[tuple], grace: int) -> ReclampResult:
    """Spec 9.2 — kappt die Einträge in ``[start, end]`` an den geänderten
    ``weekdays`` gegen den NEUEN Snapshot (der Aufrufer hat ihn bereits
    geflusht). Quelle ist der Rohstempel, sonst die gespeicherte Zeit (E48).
    Aktueller Mandanten-Puffer ``grace`` (E47), geschrieben in jeden geprüften
    Eintrag (E79, auch ohne Zeitänderung, ohne Eintrag in ``changed``).
    Setzt ORM-Attribute (kein ``query.update``), kein commit, kein Protokoll —
    beides gehört dem Router; die Vorschau rollt zurück. Idempotent."""
    weekdays = set(weekdays)
    if not weekdays or start > end:
        return ReclampResult([], [], [])
    entries = [
        e for e in db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id,
            TimeEntry.tenant_id == user.tenant_id,  # F-026
            TimeEntry.date >= start,
            TimeEntry.date <= end,
        ).order_by(TimeEntry.date, TimeEntry.start_time).all()
        if e.date.weekday() in weekdays
    ]
    if not entries:
        return ReclampResult([], [], [])
    if not getattr(user, "track_hours", True):  # Schritt 1
        return ReclampResult([], [ReclampSkip(e.id, e.date, "track_hours_off") for e in entries], [])

    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
    ).all()
    soll_free = _soll_free_dates(db, user.tenant_id, start, end)
    planned_start = {e.id: e.start_time for e in entries}
    same_day: dict = {}
    for e in entries:
        same_day.setdefault(e.date, []).append(e)

    changed, skipped, flagged = [], [], []
    for e in entries:
        if e.end_time is None:                                            # Schritt 2
            skipped.append(ReclampSkip(e.id, e.date, "open"))
            continue
        if not calculation_service._within_employment_window(user, e.date):  # Schritt 3
            skipped.append(ReclampSkip(e.id, e.date, "outside_employment"))
            continue
        if e.credit_override:                                              # Schritt 4
            skipped.append(ReclampSkip(e.id, e.date, "credit_override"))
            continue
        new_sched = calculation_service.get_schedule_for_date(db, user, e.date, wh_changes)
        if new_sched.blocks and new_sched.blocks[e.date.weekday()] and e.date in soll_free:  # Schritt 5
            skipped.append(ReclampSkip(e.id, e.date, "soll_free_day"))
            continue
        src_start = e.raw_start_time or e.start_time                      # Schritt 6
        src_end = e.raw_end_time or e.end_time
        r = clamp(db, user, e.date, src_start, src_end, grace, credit_override=False,
                  wh_changes=wh_changes, soll_free_dates=soll_free)       # Schritt 7
        if r.eff_start in {planned_start[o.id] for o in same_day[e.date] if o.id != e.id}:  # Schritt 8
            skipped.append(ReclampSkip(e.id, e.date, "unique_collision"))
            continue
        old_grace = e.clamp_grace_minutes                                  # Schritt 9
        old_day = list(prev_blocks_by_weekday[e.date.weekday()]) if prev_blocks_by_weekday else []
        new_day = get_scheduled_blocks(db, user, e.date, wh_changes=wh_changes, soll_free_dates=soll_free)
        flag = _not_extendable(e, old_day, new_day, grace, old_grace)    # Schritt 12 (vor dem Setzen)
        if r.grace_minutes is not None:
            e.clamp_grace_minutes = r.grace_minutes
        old_vals = (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, int(e.uncredited_minutes or 0))
        new_vals = (r.eff_start, r.eff_end, r.raw_start, r.raw_end, int(r.uncredited_minutes))
        old_net = Decimal(str(e.net_hours))
        if old_vals == new_vals:                                           # Schritt 10
            if flag:
                flagged.append(ReclampChange(e.id, e.date, e.start_time, e.end_time, old_vals[4], old_net,
                                             e.start_time, e.end_time, old_vals[4], old_net, flag, old_grace))
            continue
        (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, e.uncredited_minutes) = new_vals  # Schritt 11
        planned_start[e.id] = r.eff_start
        change = ReclampChange(e.id, e.date, old_vals[0], old_vals[1], old_vals[4], old_net,
                               r.eff_start, r.eff_end, new_vals[4], Decimal(str(e.net_hours)), flag, old_grace)
        changed.append(change)
        if flag:
            flagged.append(change)
    return ReclampResult(changed, skipped, flagged)


def credited_minutes_for(blocks: list, grace: int, start_min: int, end_min: int) -> int:
    """Angerechnete Minuten (ohne Pause) eines Eintrags ``start``–``end`` gegen
    die Blöcke EINES Tages — dieselbe Regel wie ``_clamp_core``, rein in Minuten
    und ohne Datenbank (für die P1-Knickstellen-Prüfung)."""
    if not blocks:
        return max(0, end_min - start_min)
    s = max(start_min, _shift_min(blocks[0][0], -grace))
    e = min(end_min, _shift_min(blocks[-1][1], grace))
    if s >= e:
        return 0
    return e - s - sum(_overlap(s, e, gs, ge) for gs, ge in credit_gaps(blocks, grace))


def open_entry_loses(old_blocks: list, new_blocks: list, grace: int, start: time, now: time) -> bool:
    """P1: verliert der offene Eintrag von heute für IRGENDEIN mögliches Ende ≥
    jetzt? ``angerechnet_neu(Ende) − angerechnet_alt(Ende)`` ist stückweise linear
    mit Knicken an Hüllen- und Lückenkanten beider Snapshots — geprüft wird an
    ``max(jetzt, Beginn)``, an jeder Knickstelle danach und an 23:59. Gleicher
    Puffer für beide Seiten: das Ausstempeln kappt mit dem gespeicherten
    Puffer des Eintrags (E80)."""
    s = _min(start)
    lo = max(_min(now), s)
    points = {lo, _LAST_MINUTE}
    for blocks in (old_blocks, new_blocks):
        if blocks:
            points.update({_shift_min(blocks[0][0], -grace), _shift_min(blocks[-1][1], grace)})
            for gs, ge in credit_gaps(blocks, grace):
                points.update({gs, ge})
    for p in sorted(x for x in points if lo <= x <= _LAST_MINUTE):
        if credited_minutes_for(new_blocks, grace, s, p) < credited_minutes_for(old_blocks, grace, s, p):
            return True
    return False
```

Falls beim Import ein Zirkelbezug `app.models` ↔ `work_window_service` auftritt, den Import `from app.models import TimeEntry, WorkingHoursChange` in die Funktion `reclamp_time_entries` verlegen — sonst nichts ändern.

- [ ] **Step 4: Test laufen lassen — muss grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_reclamp_core.py tests/test_clamp_blocks.py tests/test_work_window_service.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/work_window_service.py backend/tests/test_reclamp_core.py
git commit -F - <<'EOF'
feat(bloecke): Massen-Neukappung reclamp_time_entries und P1-Knickstellen-Prüfung (9.2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 8: `wh_change_service` — ein Rechenpfad, Klassifikation, Schutzpaket-Texte (Spec 9.3–9.5, 9.7, 11.3, 11.4, P1, P23, P25)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499 hat `routers/time_entries.py` umgebaut; dieser Task ruft nur `_close_stale_entry(db, entry, *, changed_by_id=None)` aus PR1 Task 8 — vor Step 3 `grep -n "def _close_stale_entry" -A6 backend/app/routers/time_entries.py` prüfen.)

**Files:**
- Create: `backend/app/services/wh_change_service.py`
- Test (neu): `backend/tests/test_wh_change_service.py`

**Interfaces:**
- Consumes: `retarget_window`, `RetargetWindow.has_absences`, `retarget_absence_hours(…, old_full_target_by_date=…)`, `absence_full_targets`, `AbsenceRetarget.f1_clamped/credit_reduction` (Task 6); `reclamp_time_entries`, `ReclampResult`, `open_entry_loses` (Task 7); `get_grace_minutes`, `grace_for_entry`, `get_scheduled_blocks`, `presence_minutes` (PR1); `work_blocks_service.changed_weekdays`, `ParsedWeek`, `is_legacy_week`, `week_blocks_to_json`, `HOURS_FIELDS` (Task 1/PR1); `calculation_service.get_schedule_for_date`, `get_soll_cutoff_date`, `get_monthly_target`, `get_monthly_actual`, `get_range_target`, `get_range_actual`, `closed_years_in_range`; `time_entries._close_stale_entry` (PR1 Task 8)
- Produces (in `app.services.wh_change_service`):
  - `class ChangeImpact(NamedTuple)`: `window`, `grace: int`, `old_schedule`, `new_schedule`, `changed_weekdays: list[int]`, `stale_closed: int`, `reclamp: ReclampResult`, `open_entry_loses: bool`, `absences: list[AbsenceRetarget]`, `credit_reductions: list[AbsenceRetarget]`, `target_delta: Decimal`, `credited_delta: Decimal`, `saldo_delta: Decimal`, `open_day_saldo_delta: Decimal`, `shortening_reasons: list[str]`, `shortening_closed_years: list[int]`, `earliest_lossless_date: Optional[date]`, `earliest_lossless_note: Optional[str]`, `months: list[dict]`, `arbzg: dict`, `entries_before: dict` + Eigenschaft `is_shortening`
  - `run_change(db, user, *, admin_id, effective_from: date, apply: Callable[[], None]) -> ChangeImpact` — Schritte 2–7 aus 9.3; kein commit, kein Protokoll, keine Sperre
  - `preview_fields(impact: ChangeImpact, user) -> dict` — die 11.3-Felder für `WorkingHoursChangePreview`
  - `milog_warnings(user, impact) -> list[str]`; `MILOG_ACCOUNT_WARNING`, `MILOG_GENERAL_WARNING`
  - `criteria_text(impact) -> str`; `closed_year_detail(years: list[int]) -> str`; `SONSTIGES_CONFIRM_DETAIL`
  - `protection_error(impact, reason, *, deleting: bool, reset_offered: bool) -> Optional[str]` — `reason` trägt die vier `RetroReasonFields` (oder ist `None`)
  - `reset_body(predecessor, effective_from: date, change_id) -> dict` (P13, Anlege-Body der Rücksetzung)
  - `P25_NOTE` als Formatstring

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_wh_change_service.py`:

```python
"""Spec 9.3–9.5: der eine Rechenpfad der Rückwirkung und seine Klassifikation.

„heute" = Do 08.10.2026 10:00 (Spec 12.1). Jeder Test ruft ``run_change`` direkt
und rollt danach nicht zurück — die Fixture-Session wird je Test verworfen."""
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models import AbsenceType, TimeEntryAuditLog, YearCarryover
from app.schemas.working_hours_change import WorkingHoursChangeDelete
from app.services import calculation_service, wh_change_service as svc
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import (
    ANNA_WEEK, EFF, MONDAYS, RETRO_REASON, TODAY, absence, add_row, change_row, entry, freeze, set_grace,
    t, with_pauses,
)
from tests.work_blocks_fixtures import block_week, legacy_week

TUE_THU = dict(tue=[("08:00", "12:00")], thu=[("08:00", "12:00")])
SHORT = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], **TUE_THU)
LONGER = block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], **TUE_THU)
LONGER_PAUSED = with_pauses(LONGER, mon=60)
TOMORROW = TODAY + timedelta(days=1)


def _run(db, user, admin, eff=EFF, **row):
    return svc.run_change(db, user, admin_id=admin.id, effective_from=eff,
                          apply=lambda: db.add(change_row(user, eff, **row)))


def _anna(db, user, *, afternoon_14=None, afternoon_21=None, vacation=True):
    """Spec 12.1: Montage im Wirkungsbereich je 08–12 und 15–18; 28.09.
    nachmittags anerkannt; 07.09. Urlaub (7 h)."""
    add_row(db, user, date(2026, 3, 1), week=ANNA_WEEK)
    if vacation:
        absence(db, user, MONDAYS[0], AbsenceType.VACATION, 7.0)
    for d in MONDAYS[1:]:
        entry(db, user, d, t(8), t(12))
        if d == MONDAYS[1] and afternoon_14:
            entry(db, user, d, t(15), afternoon_14[0], raw_end=afternoon_14[1])
        elif d == MONDAYS[2] and afternoon_21:
            entry(db, user, d, t(15), afternoon_21[0], raw_end=afternoon_21[1])
        else:
            entry(db, user, d, t(15), t(18), credit_override=(d == MONDAYS[3]))


class TestSpecStates:
    def test_first_state_shortening_by_entries(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        _anna(db, test_user)
        impact = _run(db, test_user, test_admin, week=SHORT)
        assert [(c.date, c.old_net, c.new_net) for c in impact.reclamp.changed] == [
            (MONDAYS[1], Decimal("3.00"), Decimal("2.25")),
            (MONDAYS[2], Decimal("3.00"), Decimal("2.25")),
            (MONDAYS[4], Decimal("3.00"), Decimal("2.25")),
        ]
        assert [(s.date, s.reason) for s in impact.reclamp.skipped] == [(MONDAYS[3], "credit_override")]
        assert (impact.target_delta, impact.credited_delta, impact.saldo_delta) == (
            Decimal("-4"), Decimal("-2.25"), Decimal("1.75"))
        assert impact.shortening_reasons == ["entries"]
        assert impact.earliest_lossless_date == TODAY
        assert [(a.date, a.old_hours, a.new_hours) for a in impact.absences] == [
            (MONDAYS[0], Decimal("7.00"), Decimal("6.00"))]
        assert impact.months == [
            {"month": "2026-09", "entries": 2, "net_before": 6.0, "net_after": 4.5},
            {"month": "2026-10", "entries": 1, "net_before": 3.0, "net_after": 2.25},
        ]
        assert (impact.changed_weekdays, impact.grace) == ([0], 15)

    def test_second_state_lengthening_with_equal_target(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        _anna(db, test_user, afternoon_14=(t(18, 15), None), afternoon_21=(t(18, 15), t(18, 30)))
        impact = _run(db, test_user, test_admin, week=LONGER_PAUSED)
        assert [(c.date, c.old_net, c.new_net) for c in impact.reclamp.changed] == [
            (MONDAYS[2], Decimal("3.25"), Decimal("3.50"))]
        assert [(c.date, c.not_extendable, c.old_end) for c in impact.reclamp.flagged] == [
            (MONDAYS[1], "end", t(18, 15))]
        assert (impact.target_delta, impact.credited_delta, impact.saldo_delta) == (
            Decimal("0"), Decimal("0.25"), Decimal("0.25"))
        assert (impact.shortening_reasons, impact.earliest_lossless_date, impact.absences) == ([], None, [])

    def test_third_state_target_raise_is_a_shortening(self, db, test_user, test_admin, monkeypatch):
        """19.1 Nr. 1 Pflichtfall: kein Eintrag verliert, das Konto sinkt."""
        freeze(monkeypatch)
        _anna(db, test_user, afternoon_14=(t(18, 15), None), afternoon_21=(t(18, 15), t(18, 30)))
        impact = _run(db, test_user, test_admin, week=LONGER)
        assert (impact.target_delta, impact.credited_delta, impact.saldo_delta) == (
            Decimal("4"), Decimal("0.25"), Decimal("-3.75"))
        assert (impact.shortening_reasons, impact.earliest_lossless_date) == (["saldo"], TODAY)
        assert [(a.old_hours, a.new_hours) for a in impact.absences] == [(Decimal("7.00"), Decimal("8.00"))]


class TestSaldoCriterion:
    def test_minus_one_hundredth_is_a_shortening_zero_is_not(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 1, 1), day_hours=(8, 8, 8, 8, 8))
        oct5 = date(2026, 10, 5)
        impact = _run(db, test_user, test_admin, eff=oct5, day_hours=(8.01, 8, 8, 8, 8))
        assert (impact.saldo_delta, impact.shortening_reasons) == (Decimal("-0.01"), ["saldo"])
        db.rollback()
        impact = _run(db, test_user, test_admin, eff=oct5, day_hours=(8, 8, 8, 8, 8.01))
        assert (impact.saldo_delta, impact.shortening_reasons) == (Decimal("0"), [])

    def test_target_drop_with_sick_day_without_work(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 8.0)
        impact = _run(db, test_user, test_admin, weekly_hours=30)
        assert [(a.new_hours, a.f1_clamped) for a in impact.absences] == [(Decimal("6.00"), False)]
        assert impact.shortening_reasons == []

    def test_closed_year_loss_counts_even_if_the_total_gains(self, db, test_user, test_admin, monkeypatch):
        """Gewinn im laufenden Jahr, Verlust im abgeschlossenen Vorjahr → Verkürzung."""
        freeze(monkeypatch)
        test_user.first_work_day, test_user.last_work_day = date(2025, 1, 1), date(2026, 1, 12)
        db.add(YearCarryover(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                             overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing"))
        db.commit()
        add_row(db, test_user, date(2025, 1, 1), day_hours=(8, 8, 8, 8, 8))
        impact = _run(db, test_user, test_admin, eff=date(2025, 12, 29), day_hours=(12, 8, 8, 0, 8))
        assert impact.saldo_delta == Decimal("4")
        assert (impact.shortening_reasons, impact.shortening_closed_years) == (["saldo"], [2025])
        assert svc.protection_error(impact, WorkingHoursChangeDelete(**RETRO_REASON), deleting=False,
                                    reset_offered=False) == svc.closed_year_detail([2025])

    def test_two_closed_years_name_the_larger_one(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        test_user.first_work_day = date(2024, 1, 1)
        for year in (2025, 2026):
            db.add(YearCarryover(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, year=year,
                                 overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing"))
        db.commit()
        add_row(db, test_user, date(2024, 1, 1), day_hours=(8, 8, 8, 8, 8))
        impact = _run(db, test_user, test_admin, eff=date(2024, 6, 3), day_hours=(9, 8, 8, 8, 8))
        assert impact.shortening_closed_years == [2024, 2025]
        assert svc.closed_year_detail(impact.shortening_closed_years) == (
            "Rückwirkende Verkürzung in das abgeschlossene Jahr 2025 ist gesperrt. "
            "Bitte die Änderung frühestens ab 01.01.2026 wirksam werden lassen.")


class TestAbsenceCreditCriterion:
    def test_regularly_clamped_mixed_day_with_target_drop_is_neutral(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 4.0)
        entry(db, test_user, MONDAYS[1], t(8), t(12), grace=None)
        impact = _run(db, test_user, test_admin, weekly_hours=30)
        assert [(a.new_hours, a.f1_clamped, a.credit_reduction) for a in impact.absences] == [
            (Decimal("2.00"), True, False)]
        assert (impact.credit_reductions, impact.shortening_reasons) == ([], [])

    def test_pre_1_18_double_credit_on_an_unchanged_weekday(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 1, 1), day_hours=(8, 8, 8, 8, 8))
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 8.0)
        entry(db, test_user, MONDAYS[1], t(8), t(12), grace=None)
        impact = _run(db, test_user, test_admin, day_hours=(8, 8, 8, 8, 4))
        assert [(a.date, a.old_hours, a.new_hours) for a in impact.credit_reductions] == [
            (MONDAYS[1], Decimal("8.00"), Decimal("4.00"))]
        assert (impact.shortening_reasons, impact.earliest_lossless_date) == (["absence_credit"], TODAY)

    def test_entry_gaining_on_a_mixed_day(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        set_grace(db, 0)
        add_row(db, test_user, date(2026, 3, 1), week=block_week(mon=[("08:00", "12:00"), ("14:00", "18:00")]))
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 4.0)
        entry(db, test_user, MONDAYS[1], t(8), t(13), uncredited=60, grace=0)
        impact = _run(db, test_user, test_admin, week=block_week(mon=[("08:00", "13:00"), ("15:00", "18:00")]))
        assert [(c.old_net, c.new_net) for c in impact.reclamp.changed] == [(Decimal("4.00"), Decimal("5.00"))]
        assert [(a.old_hours, a.new_hours) for a in impact.credit_reductions] == [(Decimal("4.00"), Decimal("3.00"))]
        assert (impact.saldo_delta, impact.shortening_reasons) == (Decimal("0"), ["absence_credit"])


class TestToday:
    """P1/9.5 (b): heute offener Tag, geschlossener Eintrag heute, kein Eintrag heute."""

    def test_target_raise_while_clocked_in(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), None)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "13:00")])
        impact = _run(db, test_user, test_admin, eff=TODAY, week=week)
        assert (impact.saldo_delta, impact.open_day_saldo_delta) == (Decimal("0"), Decimal("-1"))
        assert (impact.shortening_reasons, impact.earliest_lossless_date) == (["saldo"], TOMORROW)
        assert [(s.date, s.reason) for s in impact.reclamp.skipped] == [(TODAY, "open")]
        assert impact.open_entry_loses is False
        db.rollback()
        assert _run(db, test_user, test_admin, eff=TOMORROW, week=week).shortening_reasons == []

    def test_pause_compensation_while_clocked_in_is_no_shortening(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), None)
        week = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                                      thu=[("08:00", "13:00")]), thu=60)
        assert _run(db, test_user, test_admin, eff=TODAY, week=week).shortening_reasons == []

    def test_open_entry_whose_hull_shrinks_loses(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), None)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "11:00")])
        impact = _run(db, test_user, test_admin, eff=TODAY, week=week)
        assert (impact.open_entry_loses, impact.shortening_reasons, impact.earliest_lossless_date) == (
            True, ["entries"], TOMORROW)

    def test_target_raise_with_a_closed_entry_today(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), t(9))
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "13:00")])
        impact = _run(db, test_user, test_admin, eff=TODAY, week=week)
        assert (impact.saldo_delta, impact.shortening_reasons, impact.earliest_lossless_date) == (
            Decimal("-1"), ["saldo"], TOMORROW)

    def test_without_any_entry_today_the_default_is_today(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "13:00")])
        impact = _run(db, test_user, test_admin, week=week)
        assert (impact.saldo_delta, impact.earliest_lossless_date) == (Decimal("-5"), TODAY)
        db.rollback()
        assert _run(db, test_user, test_admin, eff=TODAY, week=week).shortening_reasons == []

    def test_p25_earliest_reaches_the_next_change(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        add_row(db, test_user, TODAY, week=ANNA_WEEK)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "13:00")])
        impact = _run(db, test_user, test_admin, week=week)
        assert impact.earliest_lossless_date is None
        assert impact.earliest_lossless_note == (
            "Die Änderung liegt vollständig vor der Änderung ab 08.10.2026; "
            "nur rückwirkend mit Begründung oder abbrechen.")


class TestStaleEntriesAndGrace:
    def test_open_entry_of_a_past_day_is_closed_first_then_reclamped(self, db, test_user, test_admin, monkeypatch):
        """P23 (19.1 Nr. 5): geschlossen unter dem ALTEN Snapshot (Audit auto_close
        mit der handelnden Admin), danach regulär neu gekappt; das Schließen geht
        nicht in den Saldo ein."""
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        tuesday = date(2026, 10, 6)
        stale = entry(db, test_user, tuesday, t(8), None)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "11:00")],
                          thu=[("08:00", "12:00")])
        impact = _run(db, test_user, test_admin, week=week)
        assert impact.stale_closed == 1
        assert [(c.entry_id, c.old_end, c.new_end) for c in impact.reclamp.changed] == [
            (stale.id, t(12, 15), t(11, 15))]
        assert impact.reclamp.skipped == []
        assert impact.saldo_delta == Decimal("5")
        audit = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.time_entry_id == stale.id,
                                                   TimeEntryAuditLog.source == "auto_close").one()
        assert audit.changed_by == test_admin.id

    def test_mass_reclamp_writes_the_current_grace(self, db, test_user, test_admin, monkeypatch):
        """E47/E79/E80: aktueller Puffer 10, gespeichert 15 — ein Eintrag verliert;
        alle geprüften Einträge geänderter Wochentage tragen danach 10."""
        freeze(monkeypatch)
        set_grace(db, 10)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        e1 = entry(db, test_user, MONDAYS[1], t(8), t(12))
        e2 = entry(db, test_user, MONDAYS[2], t(15), t(18, 15), raw_end=t(18, 40))
        e3 = entry(db, test_user, MONDAYS[3], t(7, 45), t(12), raw_start=t(7, 30))
        e4 = entry(db, test_user, MONDAYS[4], t(8), t(12), grace=None)
        e5 = entry(db, test_user, date(2026, 9, 15), t(8), t(12))
        e6 = entry(db, test_user, MONDAYS[1], t(15), t(18), credit_override=True)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:30")], **TUE_THU)
        impact = _run(db, test_user, test_admin, week=week)
        assert sorted(c.entry_id for c in impact.reclamp.changed) == sorted([e2.id, e3.id])
        assert {c.entry_id: c.old_grace for c in impact.reclamp.changed} == {e2.id: 15, e3.id: 15}
        assert "entries" in impact.shortening_reasons
        assert [e.clamp_grace_minutes for e in (e1, e2, e3, e4, e5, e6)] == [10, 10, 10, 10, 15, 15]
        assert (e3.start_time, e3.raw_start_time) == (t(7, 50), t(7, 30))


def test_arbzg_findings_before_after_and_presence(db, test_user, test_admin, monkeypatch):
    freeze(monkeypatch)
    ten = [("07:00", "17:00")]
    add_row(db, test_user, date(2026, 3, 1), week=block_week(mon=ten, tue=ten, wed=ten, thu=ten, fri=ten))
    for offset in range(5):
        entry(db, test_user, MONDAYS[1] + timedelta(days=offset), t(7), t(17))
    eight = [("07:00", "15:00")]
    impact = _run(db, test_user, test_admin, week=block_week(mon=eight, tue=eight, wed=eight, thu=eight, fri=eight))
    assert impact.arbzg == {
        "days_over_10_credited_before": 0, "days_over_10_credited_after": 0, "days_over_10_presence": 0,
        "weeks_over_48_credited_before": 1, "weeks_over_48_credited_after": 0, "weeks_over_48_presence": 1,
    }


class TestTexts:
    def _impact(self, **overrides):
        base = dict(
            window=None, grace=15, old_schedule=None, new_schedule=None, changed_weekdays=[0], stale_closed=0,
            reclamp=None, open_entry_loses=False, absences=[], credit_reductions=[],
            target_delta=Decimal("0"), credited_delta=Decimal("0"), saldo_delta=Decimal("0"),
            open_day_saldo_delta=Decimal("0"), shortening_reasons=[], shortening_closed_years=[],
            earliest_lossless_date=TODAY, earliest_lossless_note=None, months=[], arbzg={}, entries_before={},
        )
        base.update(overrides)
        return svc.ChangeImpact(**base)

    def _reclamp(self, losing: int):
        from app.services.work_window_service import ReclampChange, ReclampResult
        changes = [ReclampChange(uuid4(), MONDAYS[1], t(15), t(18), 0, Decimal("3"), t(15), t(17, 15), 0,
                                 Decimal("2.25"), None, 15) for _ in range(losing)]
        return ReclampResult(changes, [], [])

    def test_shortening_messages(self):
        a = self._impact(reclamp=self._reclamp(3), shortening_reasons=["entries"])
        assert svc.protection_error(a, None, deleting=False, reset_offered=False) == (
            "Rückwirkende Verkürzung (3 Einträge verlieren angerechnete Zeit): Bitte Grund, Begründung und die "
            "Bestätigung zum Vergütungsrisiko angeben – oder die Änderung ab dem 08.10.2026 wirksam werden lassen.")
        b = self._impact(reclamp=self._reclamp(0), shortening_reasons=["saldo"], saldo_delta=Decimal("-3.75"))
        assert "(Überstundenkonto −3:45 h)" in svc.protection_error(b, None, deleting=False, reset_offered=False)
        o = self._impact(reclamp=self._reclamp(0), shortening_reasons=["saldo"], open_day_saldo_delta=Decimal("-1"))
        assert "(Soll heute +1:00 h während eingestempelt)" in svc.protection_error(
            o, None, deleting=False, reset_offered=False)
        c = self._impact(reclamp=self._reclamp(0), shortening_reasons=["absence_credit"], credit_reductions=[object()])
        assert "(1 Abwesenheits-Gutschrift sinkt)" in svc.protection_error(c, None, deleting=False, reset_offered=False)

    def test_delete_messages_and_p25(self):
        a = self._impact(reclamp=self._reclamp(1), shortening_reasons=["entries"])
        assert svc.protection_error(a, None, deleting=True, reset_offered=True) == (
            "Das Löschen verkürzt rückwirkend (1 Eintrag verliert angerechnete Zeit): Bitte Grund, Begründung und "
            "die Bestätigung zum Vergütungsrisiko angeben – oder ab dem 08.10.2026 auf den vorherigen Stand "
            "zurücksetzen.")
        assert svc.protection_error(a, None, deleting=True, reset_offered=False).endswith("– oder abbrechen.")
        note = svc.P25_NOTE.format(date="01.10.2026")
        n = self._impact(reclamp=self._reclamp(1), shortening_reasons=["entries"], earliest_lossless_date=None,
                         earliest_lossless_note=note)
        assert svc.protection_error(n, None, deleting=False, reset_offered=False).endswith(f"– oder abbrechen: {note}")

    def test_reason_rules(self):
        a = self._impact(reclamp=self._reclamp(1), shortening_reasons=["entries"])
        assert svc.protection_error(a, WorkingHoursChangeDelete(**RETRO_REASON), deleting=False,
                                    reset_offered=False) is None
        other = WorkingHoursChangeDelete(**dict(RETRO_REASON, retroactive_reason_type="sonstiges"))
        assert svc.protection_error(a, other, deleting=False, reset_offered=False) == svc.SONSTIGES_CONFIRM_DETAIL
        no_hook = WorkingHoursChangeDelete(**dict(RETRO_REASON, wage_risk_confirmed=False))
        assert svc.protection_error(a, no_hook, deleting=False, reset_offered=False).startswith("Rückwirkende Verkürzung")
        assert svc.protection_error(self._impact(), None, deleting=False, reset_offered=False) is None

    def test_milog_warnings(self, test_user):
        shortening = self._impact(reclamp=self._reclamp(1), shortening_reasons=["entries"])
        assert svc.milog_warnings(test_user, shortening) == [svc.MILOG_GENERAL_WARNING]
        test_user.agreed_monthly_hours = 43.0
        assert svc.milog_warnings(test_user, shortening) == [svc.MILOG_ACCOUNT_WARNING, svc.MILOG_GENERAL_WARNING]
        assert svc.milog_warnings(test_user, self._impact()) == []


def test_reset_body_for_every_kind_of_predecessor():
    cid = uuid4()

    def sched(**kw):
        base = dict(weekly_hours=Decimal("40"), use_daily_schedule=False, day_hours=(None,) * 5,
                    work_days_per_week=5, blocks=None, block_pauses=None)
        base.update(kw)
        return calculation_service.Schedule(**base)

    assert svc.reset_body(sched(), TODAY, cid) == {
        "effective_from": "2026-10-08", "reset_of_change_id": str(cid), "use_daily_schedule": False,
        "weekly_hours": 40.0, "work_days_per_week": 5, "remove_legacy_window": True}
    from app.services import work_blocks_service as wbs
    new = wbs.parse_week_blocks(ANNA_WEEK)
    assert svc.reset_body(sched(blocks=new.blocks, block_pauses=new.pauses), TODAY, cid) == {
        "effective_from": "2026-10-08", "reset_of_change_id": str(cid), "blocks": ANNA_WEEK}
    legacy = wbs.parse_week_blocks(legacy_week(mon=("07:30", "16:30")))
    body = svc.reset_body(sched(blocks=legacy.blocks, block_pauses=legacy.pauses, use_daily_schedule=True,
                                day_hours=(Decimal("8"), Decimal("8"), None, None, None), work_days_per_week=2),
                          TODAY, cid)
    assert body == {"effective_from": "2026-10-08", "reset_of_change_id": str(cid), "use_daily_schedule": True,
                    "hours_monday": 8.0, "hours_tuesday": 8.0, "hours_wednesday": None, "hours_thursday": None,
                    "hours_friday": None, "work_days_per_week": 2}
```

- [ ] **Step 2: Test laufen lassen — muss scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_service.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'wh_change_service'`.

- [ ] **Step 3: `wh_change_service.py` anlegen**

`backend/app/services/wh_change_service.py`:

```python
"""Spec 2026-10-08, Abschnitt 9: Rückwirkung einer Arbeitszeit-Änderung.

EIN Rechenpfad (9.3 Schritte 2–7) für Anlegen, Löschen und beide Vorschauen:

2. offene Einträge vergangener Tage im Wirkungsbereich schließen (P23) — unter
   dem ALTEN Snapshot, mit der handelnden Admin als ``changed_by``;
3. Saldo, heutigen Tag und volles Tagessoll je Abwesenheit VORHER festhalten;
4. die Änderung anwenden (Callback: Zeile anlegen bzw. löschen);
5. Einträge der geänderten Wochentage neu kappen (aktueller Puffer, E47);
6. Abwesenheiten mit F1-Klemmung nachziehen (E51 — erst Einträge, dann
   Abwesenheiten);
7. Saldo nachher und Klassifikation nach 9.4/9.5 (a)–(c).

Kein commit, kein Protokoll, keine Sperre: das gehört dem Router — die Vorschau
rollt danach zurück und darf nichts festschreiben (E57).
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Dict, List, NamedTuple, Optional

from sqlalchemy.orm import Session

from app.models import TimeEntry, User, WorkingHoursChange
from app.services import (
    calculation_service, timezone_service, work_blocks_service, work_window_service,
)

SHORTENING_ENTRIES = "entries"
SHORTENING_SALDO = "saldo"
SHORTENING_ABSENCE_CREDIT = "absence_credit"

P25_NOTE = "Die Änderung liegt vollständig vor der Änderung ab {date}; nur rückwirkend mit Begründung oder abbrechen."
MILOG_ACCOUNT_WARNING = (
    "Diese Person führt ein Arbeitszeitkonto nach § 2 Abs. 2 MiLoG bzw. hat eine vereinbarte "
    "Monatsarbeitszeit. Eine rückwirkende Kürzung angerechneter Zeit verändert den Kontostand und kann "
    "Mindestlohnansprüche sowie die 12-Monats-Ausgleichsfrist berühren."
)
MILOG_GENERAL_WARNING = (
    "Bei Minijob oder Vergütung in Mindestlohnhöhe kann die Kürzung Mindestlohnansprüche (§§ 1, 3 MiLoG) "
    "und die Aufzeichnung nach § 17 MiLoG berühren."
)
SONSTIGES_CONFIRM_DETAIL = (
    "Bei „Sonstiges“ bitte bestätigen, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht "
    "nicht gedeckt ist."
)
_ASK = "Bitte Grund, Begründung und die Bestätigung zum Vergütungsrisiko angeben"
_ZERO = Decimal("0")


class ChangeImpact(NamedTuple):
    window: object
    grace: int
    old_schedule: object
    new_schedule: object
    changed_weekdays: list
    stale_closed: int
    reclamp: object
    open_entry_loses: bool
    absences: list
    credit_reductions: list
    target_delta: Decimal
    credited_delta: Decimal
    saldo_delta: Decimal
    open_day_saldo_delta: Decimal
    shortening_reasons: list
    shortening_closed_years: list
    earliest_lossless_date: Optional[date]
    earliest_lossless_note: Optional[str]
    months: list
    arbzg: dict
    entries_before: dict

    @property
    def is_shortening(self) -> bool:
        return bool(self.shortening_reasons)


def _saldo_by_year(db: Session, user: User, start: date, end: date, cutoff: date) -> Dict[int, tuple]:
    """Spec 9.5 (b): (Soll, Ist) je Jahr über die Monate des Wirkungsbereichs bis
    zum Saldo-Stichtag (#313), über ``get_monthly_target``/``get_monthly_actual``
    (der #377-Fix-Modus geht so mit), OHNE Jahresüberträge. Tage vor ``start``
    im ersten Monat ändern sich durch die Änderung nicht — sie fallen in der
    Differenz heraus."""
    last = min(end, cutoff)
    result: Dict[int, tuple] = {}
    if last < start:
        return result
    y, m = start.year, start.month
    while (y, m) <= (last.year, last.month):
        target = calculation_service.get_monthly_target(db, user, y, m, up_to_date=cutoff)
        actual = calculation_service.get_monthly_actual(db, user, y, m, up_to_date=cutoff)
        t0, a0 = result.get(y, (_ZERO, _ZERO))
        result[y] = (t0 + target, a0 + actual)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return result


def _day_saldo(db: Session, user: User, d: date) -> Decimal:
    """Saldo-Anteil EINES Tages (Gutschrift/Ist − Soll), wie die Monatsfunktionen
    ihn zählen; ein offener Eintrag trägt 0 h bei."""
    return (calculation_service.get_range_actual(db, user, d, d)
            - calculation_service.get_range_target(db, user, d, d))


def _closed_entries(db: Session, user: User, start: date, end: date) -> List[TimeEntry]:
    return db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026
        TimeEntry.date >= start,
        TimeEntry.date <= end,
        TimeEntry.end_time.isnot(None),
    ).all()


def _snapshot(e: TimeEntry) -> TimeEntry:
    """Transiente Kopie (nie in der Session) — „vorher" für Protokoll (10.1) und
    ArbZG-Befunde (P22)."""
    return TimeEntry(date=e.date, start_time=e.start_time, end_time=e.end_time,
                     raw_start_time=e.raw_start_time, raw_end_time=e.raw_end_time,
                     break_minutes=e.break_minutes, uncredited_minutes=e.uncredited_minutes,
                     auto_closed=e.auto_closed)


def _arbzg_counts(entries, value) -> tuple:
    per_day: Dict = defaultdict(Decimal)
    per_week: Dict = defaultdict(Decimal)
    for e in entries:
        v = value(e)
        per_day[e.date] += v
        per_week[e.date.isocalendar()[:2]] += v
    return (sum(1 for v in per_day.values() if v > 10), sum(1 for v in per_week.values() if v > 48))


def _next_change(db: Session, user: User, effective_from: date) -> Optional[WorkingHoursChange]:
    return db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
        WorkingHoursChange.effective_from > effective_from,
    ).order_by(WorkingHoursChange.effective_from.asc()).first()


def run_change(db: Session, user: User, *, admin_id, effective_from: date,
               apply: Callable[[], None]) -> ChangeImpact:
    """Spec 9.3 Schritte 2–7 (Docstring des Moduls)."""
    from app.routers.time_entries import _close_stale_entry  # lokal: kein Router-Import beim Modul-Laden

    today = timezone_service.today_local()
    window = calculation_service.retarget_window(db, user, effective_from)

    # Schritt 2 (P23)
    stale = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026
        TimeEntry.end_time.is_(None),
        TimeEntry.date >= window.start,
        TimeEntry.date <= window.end,
        TimeEntry.date < today,
    ).order_by(TimeEntry.date).all()
    for e in stale:
        _close_stale_entry(db, e, changed_by_id=admin_id)
    if stale:
        db.flush()

    # Schritt 3
    old_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    cutoff = calculation_service.get_soll_cutoff_date(db, user, today)
    today_in_window = window.start <= today <= window.end
    open_today = None
    if today_in_window:
        open_today = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id,
            TimeEntry.tenant_id == user.tenant_id,  # F-026
            TimeEntry.date == today,
            TimeEntry.end_time.is_(None),
        ).first()
    open_day = open_today is not None and cutoff < today
    today_counts = today_in_window and cutoff == today
    saldo_before = _saldo_by_year(db, user, window.start, window.end, cutoff)
    open_day_before = _day_saldo(db, user, today) if open_day else _ZERO
    today_before = _day_saldo(db, user, today) if today_counts else _ZERO
    old_full = calculation_service.absence_full_targets(db, user, window.start, window.end)
    old_today_blocks = work_window_service.get_scheduled_blocks(db, user, today) if open_today else []
    before = {e.id: _snapshot(e) for e in _closed_entries(db, user, window.start, window.end)}

    # Schritt 4
    apply()
    db.flush()

    # Schritt 5
    new_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    weekdays = work_blocks_service.changed_weekdays(old_schedule.blocks, new_schedule.blocks)
    grace = work_window_service.get_grace_minutes(db, user.tenant_id)
    reclamp = work_window_service.reclamp_time_entries(
        db, user, window.start, window.end, set(weekdays), old_schedule.blocks, grace)
    db.flush()
    open_loses = False
    if (open_today is not None and user.track_hours and not open_today.credit_override
            and today.weekday() in weekdays):
        open_loses = work_window_service.open_entry_loses(
            old_today_blocks, work_window_service.get_scheduled_blocks(db, user, today),
            work_window_service.grace_for_entry(db, open_today), open_today.start_time,
            timezone_service.now_local().time(),
        )

    # Schritt 6 (E51: erst Einträge, dann Abwesenheiten)
    absences = []
    if window.has_absences:
        absences = calculation_service.retarget_absence_hours(
            db, user, window.start, window.end, old_full_target_by_date=old_full)

    # Schritt 7
    saldo_after = _saldo_by_year(db, user, window.start, window.end, cutoff)
    years = sorted(set(saldo_before) | set(saldo_after))
    zero = (_ZERO, _ZERO)
    target_delta = sum((saldo_after.get(y, zero)[0] - saldo_before.get(y, zero)[0] for y in years), _ZERO)
    credited_delta = sum((saldo_after.get(y, zero)[1] - saldo_before.get(y, zero)[1] for y in years), _ZERO)
    saldo_by_year = {
        y: (saldo_after.get(y, zero)[1] - saldo_after.get(y, zero)[0])
        - (saldo_before.get(y, zero)[1] - saldo_before.get(y, zero)[0])
        for y in years
    }
    saldo_delta = credited_delta - target_delta
    open_day_delta = (_day_saldo(db, user, today) - open_day_before) if open_day else _ZERO
    today_delta = (_day_saldo(db, user, today) - today_before) if today_counts else _ZERO

    losing = [c for c in reclamp.changed if c.new_net < c.old_net]
    reductions = [a for a in absences if a.credit_reduction]
    closed = calculation_service.closed_years_in_range(
        db, user.tenant_id, range(window.start.year, window.end.year + 1))
    reasons = []
    if losing or open_loses:
        reasons.append(SHORTENING_ENTRIES)
    if saldo_delta < 0 or open_day_delta < 0 or any(saldo_by_year.get(y, _ZERO) < 0 for y in closed):
        reasons.append(SHORTENING_SALDO)
    if reductions:
        reasons.append(SHORTENING_ABSENCE_CREDIT)
    loss_years = ({c.date.year for c in losing} | {a.date.year for a in reductions}
                  | {y for y, d in saldo_by_year.items() if d < 0})
    if open_loses or open_day_delta < 0:
        loss_years.add(today.year)

    earliest, note = None, None
    if reasons:
        tomorrow = today + timedelta(days=1)
        candidates = [today]
        if losing:
            candidates.append(max(c.date for c in losing) + timedelta(days=1))
        if reductions:
            candidates.append(max(a.date for a in reductions) + timedelta(days=1))
        if open_loses or today_delta < 0 or open_day_delta < 0:
            candidates.append(tomorrow)                                   # H (P1)
        earliest = max(candidates)
        nxt = _next_change(db, user, effective_from)
        if nxt is not None and earliest >= nxt.effective_from:           # P25
            note = P25_NOTE.format(date=nxt.effective_from.strftime("%d.%m.%Y"))
            earliest = None

    months: Dict[str, list] = defaultdict(lambda: [0, _ZERO, _ZERO])
    for c in reclamp.changed:
        bucket = months[c.date.strftime("%Y-%m")]
        bucket[0] += 1
        bucket[1] += c.old_net
        bucket[2] += c.new_net
    after = _closed_entries(db, user, window.start, window.end)
    credited_before = _arbzg_counts(before.values(), lambda e: Decimal(str(e.net_hours)))
    credited_after = _arbzg_counts(after, lambda e: Decimal(str(e.net_hours)))
    presence = _arbzg_counts(after, lambda e: Decimal(work_window_service.presence_minutes(e)) / Decimal(60))

    return ChangeImpact(
        window=window, grace=grace, old_schedule=old_schedule, new_schedule=new_schedule,
        changed_weekdays=weekdays, stale_closed=len(stale), reclamp=reclamp, open_entry_loses=open_loses,
        absences=absences, credit_reductions=reductions, target_delta=target_delta,
        credited_delta=credited_delta, saldo_delta=saldo_delta, open_day_saldo_delta=open_day_delta,
        shortening_reasons=reasons,
        shortening_closed_years=sorted(y for y in closed if y in loss_years) if reasons else [],
        earliest_lossless_date=earliest, earliest_lossless_note=note,
        months=[{"month": k, "entries": v[0], "net_before": float(v[1]), "net_after": float(v[2])}
                for k, v in sorted(months.items())],
        arbzg={
            "days_over_10_credited_before": credited_before[0],
            "days_over_10_credited_after": credited_after[0],
            "days_over_10_presence": presence[0],
            "weeks_over_48_credited_before": credited_before[1],
            "weeks_over_48_credited_after": credited_after[1],
            "weeks_over_48_presence": presence[1],
        },
        entries_before=before,
    )


def _change_out(c) -> dict:
    return {
        "entry_id": str(c.entry_id), "date": c.date,
        "old_start": c.old_start, "old_end": c.old_end, "old_uncredited": c.old_uncredited,
        "old_net": float(c.old_net), "new_start": c.new_start, "new_end": c.new_end,
        "new_uncredited": c.new_uncredited, "new_net": float(c.new_net), "not_extendable": c.not_extendable,
    }


def milog_warnings(user, impact: ChangeImpact) -> List[str]:
    """Spec 9.5/P26: nur bei einer Verkürzung — Konto-/Monatszeit-Satz bei
    ``milog_working_time_account`` oder ``agreed_monthly_hours``, der allgemeine
    Mindestlohnsatz bei JEDER (Minijobber ohne Kennzeichen, Risiko 9)."""
    if not impact.is_shortening:
        return []
    out = []
    if getattr(user, "milog_working_time_account", False) or getattr(user, "agreed_monthly_hours", None):
        out.append(MILOG_ACCOUNT_WARNING)
    out.append(MILOG_GENERAL_WARNING)
    return out


def preview_fields(impact: ChangeImpact, user) -> dict:
    """Spec 11.3: die neuen Vorschau-Felder aus EINEM flush/Rollback-Lauf."""
    changed = impact.reclamp.changed
    return {
        "changed_weekdays": impact.changed_weekdays,
        "affected_time_entries": len(changed),
        "time_entry_months": impact.months,
        "time_entry_changes": [_change_out(c) for c in changed],
        "skipped_time_entries": [
            {"entry_id": str(s.entry_id), "date": s.date, "reason": s.reason} for s in impact.reclamp.skipped],
        "not_extendable_count": len(impact.reclamp.flagged),
        "not_extendable_entries": [_change_out(c) for c in impact.reclamp.flagged],
        "is_shortening": impact.is_shortening,
        "shortening_reasons": impact.shortening_reasons,
        "shortening_closed_years": impact.shortening_closed_years,
        "earliest_lossless_date": impact.earliest_lossless_date,
        "earliest_lossless_note": impact.earliest_lossless_note,
        "lost_credited_hours": float(sum((c.old_net - c.new_net for c in changed if c.new_net < c.old_net), _ZERO)),
        "target_delta_hours": float(impact.target_delta),
        "credited_delta_hours": float(impact.credited_delta),
        "saldo_delta_hours": float(impact.saldo_delta),
        "open_day_saldo_delta_hours": float(impact.open_day_saldo_delta),
        "absence_f1_adjustments": sum(1 for a in impact.absences if a.f1_clamped),
        "absence_credit_reductions": [
            {"absence_id": str(a.absence_id), "date": a.date, "old_hours": float(a.old_hours),
             "new_hours": float(a.new_hours)} for a in impact.credit_reductions],
        "stale_entries_closed": impact.stale_closed,
        "arbzg_findings": impact.arbzg,
        "milog_warning": milog_warnings(user, impact),
        "affected_absences": len(impact.absences),
    }


def _hm(hours) -> str:
    minutes = int(round(abs(Decimal(hours)) * 60))
    return f"{minutes // 60}:{minutes % 60:02d}"


def _signed(hours) -> str:
    return ("−" if Decimal(hours) < 0 else "+") + _hm(hours)


def criteria_text(impact: ChangeImpact) -> str:
    """Spec 11.4: {Kriterien} — „3 Einträge verlieren angerechnete Zeit;
    Überstundenkonto −3:45 h; 1 Abwesenheits-Gutschrift sinkt" bzw. „Soll heute
    +1:00 h während eingestempelt"."""
    parts = []
    if SHORTENING_ENTRIES in impact.shortening_reasons:
        n = sum(1 for c in impact.reclamp.changed if c.new_net < c.old_net) + (1 if impact.open_entry_loses else 0)
        parts.append("1 Eintrag verliert angerechnete Zeit" if n == 1 else f"{n} Einträge verlieren angerechnete Zeit")
    if SHORTENING_SALDO in impact.shortening_reasons:
        if impact.saldo_delta < 0:
            parts.append(f"Überstundenkonto {_signed(impact.saldo_delta)} h")
        if impact.open_day_saldo_delta < 0:
            parts.append(f"Soll heute {_signed(-impact.open_day_saldo_delta)} h während eingestempelt")
        if impact.saldo_delta >= 0 and impact.open_day_saldo_delta >= 0:
            years = ", ".join(str(y) for y in impact.shortening_closed_years)
            parts.append(f"Überstundenkonto im abgeschlossenen Jahr {years} gesenkt")
    if SHORTENING_ABSENCE_CREDIT in impact.shortening_reasons:
        n = len(impact.credit_reductions)
        parts.append("1 Abwesenheits-Gutschrift sinkt" if n == 1 else f"{n} Abwesenheits-Gutschriften sinken")
    return "; ".join(parts)


def closed_year_detail(years: List[int]) -> str:
    """Spec 11.4 — genannt wird das GRÖSSTE Jahr (sonst scheiterte auch der Vorschlag)."""
    y = max(years)
    return (f"Rückwirkende Verkürzung in das abgeschlossene Jahr {y} ist gesperrt. "
            f"Bitte die Änderung frühestens ab 01.01.{y + 1} wirksam werden lassen.")


def protection_error(impact: ChangeImpact, reason, *, deleting: bool, reset_offered: bool) -> Optional[str]:
    """Spec 9.5/11.4 — ``None`` = speicherbar, sonst der 400-Text. Reihenfolge:
    abgeschlossenes Jahr (auch mit Grund gesperrt) → fehlender Grund/Haken →
    „Sonstiges" ohne zweiten Haken."""
    if not impact.is_shortening:
        return None
    if impact.shortening_closed_years:
        return closed_year_detail(impact.shortening_closed_years)
    complete = bool(reason is not None and reason.retroactive_reason_type
                    and reason.retroactive_reason_text and reason.wage_risk_confirmed)
    if not complete:
        crit = criteria_text(impact)
        if deleting:
            head = f"Das Löschen verkürzt rückwirkend ({crit}): {_ASK}"
            if reset_offered and impact.earliest_lossless_date is not None:
                return (f"{head} – oder ab dem {impact.earliest_lossless_date:%d.%m.%Y} "
                        f"auf den vorherigen Stand zurücksetzen.")
        else:
            head = f"Rückwirkende Verkürzung ({crit}): {_ASK}"
            if impact.earliest_lossless_date is not None:
                return f"{head} – oder die Änderung ab dem {impact.earliest_lossless_date:%d.%m.%Y} wirksam werden lassen."
        if impact.earliest_lossless_note:
            return f"{head} – oder abbrechen: {impact.earliest_lossless_note}"
        return f"{head} – oder abbrechen."
    if reason.retroactive_reason_type == "sonstiges" and not reason.other_reason_risk_confirmed:
        return SONSTIGES_CONFIRM_DETAIL
    return None


def reset_body(predecessor, effective_from: date, change_id) -> dict:
    """P13/9.7 — fertiger Anlege-Body „ab ‹Datum› auf den vorherigen Stand
    zurücksetzen": der Vorgänger-Snapshot samt neuen Blöcken; ein Altfenster
    trägt der Server selbst nach (der Schreibweg nimmt keine Altfenster an),
    deshalb nur Modusfelder und — ohne Fenster — ``remove_legacy_window``."""
    body: dict = {"effective_from": effective_from.isoformat(), "reset_of_change_id": str(change_id)}
    parsed = (None if predecessor.blocks is None
              else work_blocks_service.ParsedWeek(predecessor.blocks, predecessor.block_pauses))
    if parsed is not None and not work_blocks_service.is_legacy_week(parsed):
        body["blocks"] = work_blocks_service.week_blocks_to_json(parsed.blocks, parsed.pauses)
        return body
    if predecessor.use_daily_schedule:
        body["use_daily_schedule"] = True
        for key, value in zip(work_blocks_service.HOURS_FIELDS, predecessor.day_hours):
            body[key] = None if value is None else float(value)
    else:
        body["use_daily_schedule"] = False
        body["weekly_hours"] = float(predecessor.weekly_hours)
    body["work_days_per_week"] = int(predecessor.work_days_per_week)
    if parsed is None:
        body["remove_legacy_window"] = True
    return body
```

- [ ] **Step 4: Test laufen lassen — muss grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_service.py -q -p no:cacheprovider`
Expected: PASS. Scheitert ein Zahlenwert in `TestSpecStates`, zuerst die Annahme der Spec-Nachrechnung (12.1, „Nachrechnung") prüfen — die Werte sind dort hergeleitet; nicht die Erwartung an den Code anpassen, ohne die Abweichung zu verstehen.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/wh_change_service.py backend/tests/test_wh_change_service.py
git commit -F - <<'EOF'
feat(bloecke): ein Rechenpfad der Rückwirkung mit Verkürzungskriterien (a)–(c) und earliest_lossless_date

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 9: Anlege-Endpunkt — Ankersperre, Block-Modus, Rücksetzung, Schutzpaket, Protokoll (Spec 9.3, 9.5, 10, 11.1, 11.2, 11.4, P2, P13, P20, P24)

**Files:**
- Modify: `backend/app/routers/admin_users.py` (Importe; neu `_parse_change_body`, `_reset_target`, `_target_blocks`, `_reset_matches`, `_insert_change_rows`, `_log_reclamp`; `create_working_hours_change` komplett ersetzt; `update_user`-Meldung)
- Test (neu): `backend/tests/test_reclamp.py`
- Modify (Bestandstests der Anlege-Seite, Spec 17.6): `backend/tests/test_wh_change_retroactive.py`, `backend/tests/test_fix2_whchange_daily_schedule.py`, `backend/tests/test_absence_raw_hours.py`

**Interfaces:**
- Consumes: `WorkingHoursChangeCreate` (Task 3), `wh_change_service.run_change`, `protection_error` (Task 8), `reclamp_audit.*` (Task 2), `work_window_service.credit_summary_text` (PR2 Task 1), `_comparable_snapshot`, `_carried_blocks`, `_sync_user_from_change`, `_normalise_schedule_input` (PR1 Task 12/Bestand), `lock_user_row` (Bestand); für die Tests zusätzlich `RETRO_REASON` (Task 6), Anerkennen-Endpunkt `POST /api/admin/time-entries/{id}/credit-override` (PR2 Task 5), `POST /api/admin/users/{id}/anonymize`, `lifecycle_service.anonymize_tenant`, `GET /api/admin/audit/verify-integrity`, `calculation_service.get_soll_cutoff_date`, `get_overtime_history`, `get_overtime_account` (Bestand)
- Produces (in `app.routers.admin_users`):
  - `_parse_change_body(raw) -> WorkingHoursChangeCreate` — Pydantic-Fehler als 422 mit deutschem `detail` (`_schedule_input_error`); ein bereits gebautes Schema geht unverändert durch (Direktaufrufe der Bestandstests)
  - `RESET_CONFLICT_DETAIL = "Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."`
  - `_reset_target(db, user, current_user, change_data) -> Optional[tuple[WorkingHoursChange, Schedule]]` (404, wenn fremd)
  - `_target_blocks(db, user, change_data, reset_schedule) -> tuple[Optional[tuple], Optional[tuple]]`
  - `_reset_matches(change_data, norm, reset_schedule) -> bool`
  - `_insert_change_rows(db, user, current_user, change_data, norm, new_blocks, new_pauses, *, sync: bool) -> WorkingHoursChange`
  - `_log_reclamp(db, *, user, admin, impact, effective_from, deleted, reason_type, reason_text, reset_of) -> None`
  - `POST /api/admin/users/{id}/working-hours-changes`: Body untypisiert entgegengenommen und per `_parse_change_body` geprüft; Antwort zusätzlich `adjusted_time_entries`, `skipped_time_entries`

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_reclamp.py`:

```python
"""Spec 9.3–9.5, 10, 11.2/11.4: Anlegen einer Arbeitszeit-Änderung (HTTP).

„heute" = Do 08.10.2026 10:00. Die Rechenregeln selbst prüft
test_wh_change_service.py; hier geht es um Sperre, Schutzpaket, 400/404/422,
Rollback, Antwortfelder und Protokoll."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

import app.routers.admin_users as admin_users_router
from app.core.audit_integrity import verify_row
from app.models import (
    AbsenceType, TimeEntry, TimeEntryAuditLog, User, UserRole, WorkingHoursChange, YearCarryover,
)
from app.services import calculation_service, lifecycle_service, wh_change_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.wh_change_helpers import (
    ANNA_WEEK, EFF, MONDAYS, RETRO_REASON, absence, add_row, admin_client, entry, freeze, reclamp_logs,
    set_grace, t, with_pauses,
)
from tests.work_blocks_fixtures import K_BLOCKS, block_week, legacy_week

TUE_THU = dict(tue=[("08:00", "12:00")], thu=[("08:00", "12:00")])
SHORT = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], **TUE_THU)
LONGER = block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], **TUE_THU)
REASON_TEXT = RETRO_REASON["retroactive_reason_text"]


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch)
    c = admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _post(client, user, body):
    return client.post(f"/api/admin/users/{user.id}/working-hours-changes", json=body)


def _anna(db, user):
    add_row(db, user, date(2026, 3, 1), week=ANNA_WEEK)
    absence(db, user, MONDAYS[0], AbsenceType.VACATION, 7.0)
    for d in MONDAYS[1:]:
        entry(db, user, d, t(8), t(12))
        entry(db, user, d, t(15), t(18), credit_override=(d == MONDAYS[3]))


def _employee(db, username, **kw):
    u = User(username=username, email=f"{username}@x.de", password_hash="h", first_name=username, last_name="T",
             role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
             tenant_id=DEFAULT_TENANT_ID, **kw)
    db.add(u)
    db.commit()
    return u


class TestShorteningByEntries:
    def test_without_reason_is_400_and_changes_nothing(self, client, db, test_user):
        _anna(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"] == (
            "Rückwirkende Verkürzung (3 Einträge verlieren angerechnete Zeit): Bitte Grund, Begründung und die "
            "Bestätigung zum Vergütungsrisiko angeben – oder die Änderung ab dem 08.10.2026 wirksam werden lassen.")
        db.expire_all()
        assert db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).count() == 1
        afternoons = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id, TimeEntry.start_time == t(15)).all()
        assert {e.end_time for e in afternoons} == {t(18)}
        assert reclamp_logs(db, test_user) == []

    def test_stale_entry_closing_is_rolled_back_with_the_400(self, client, db, test_user):
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        stale = entry(db, test_user, date(2026, 10, 6), t(8), None)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "11:00")],
                          thu=[("08:00", "12:00")])
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": week}).status_code == 400
        db.expire_all()
        assert db.get(TimeEntry, stale.id).end_time is None

    def test_with_reason_saves_note_counts_and_audit(self, client, db, test_user, test_admin):
        _anna(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT, **RETRO_REASON})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["note"] == f"[Erfassungsfehler korrigiert] {REASON_TEXT}"
        assert (body["adjusted_time_entries"], body["skipped_time_entries"], body["adjusted_absences"]) == (3, 1, 1)
        assert body["blocks"] == SHORT
        rows = reclamp_logs(db, test_user, summary=False)
        assert len(rows) == 3
        first = next(r for r in rows if r.new_date == MONDAYS[1])
        assert (first.old_start_time, first.old_end_time, first.new_end_time, first.changed_by) == (
            t(15), t(18), t(17, 15), test_admin.id)
        assert first.old_note == "angerechnet 3:00 h"
        assert first.new_note == (
            "angerechnet 2:15 h, nicht angerechnet 0:45 h — Arbeitszeit-Änderung ab 01.09.2026 "
            f"· Grund: [Erfassungsfehler korrigiert] {REASON_TEXT}")
        [summary] = reclamp_logs(db, test_user, summary=True)
        assert (summary.changed_by, summary.new_date, summary.time_entry_id) == (test_admin.id, None, None)
        assert summary.new_note == (
            "Arbeitszeit-Änderung ab 01.09.2026: 3 Einträge neu berechnet, Δ -135 Min, Saldo Δ +105 Min, "
            f"1 übersprungen (1 anerkannt) · Puffer 15 Min · Verkürzung · Grund: [Erfassungsfehler korrigiert] "
            f"{REASON_TEXT} · Vertrag: Mo 08:00–12:00+15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 → "
            "Mo 08:00–12:00+15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00")
        all_rows = reclamp_logs(db, test_user)
        assert all(verify_row(r) for r in all_rows) and all(len(r.source) <= 40 for r in all_rows)

    def test_sonstiges_needs_the_second_hook(self, client, db, test_user):
        _anna(db, test_user)
        body = {"effective_from": "2026-09-01", "blocks": SHORT, **RETRO_REASON,
                "retroactive_reason_type": "sonstiges"}
        resp = _post(client, test_user, body)
        assert (resp.status_code, resp.json()["detail"]) == (400, wh_change_service.SONSTIGES_CONFIRM_DETAIL)
        resp = _post(client, test_user, {**body, "other_reason_risk_confirmed": True})
        assert resp.status_code == 201, resp.text
        assert resp.json()["note"].startswith("[Sonstiges] ")

    def test_reason_text_with_nine_characters_is_422(self, client, db, test_user):
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 45,
                                         **RETRO_REASON, "retroactive_reason_text": "123456789"})
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"] == "Die Begründung muss mindestens 10 Zeichen lang sein."


class TestShorteningBySaldo:
    def test_target_raise_with_blocks_needs_a_reason(self, client, db, test_user):
        _anna(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER})
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Rückwirkende Verkürzung (Überstundenkonto −")
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER,
                                         **RETRO_REASON}).status_code == 201

    def test_the_same_raise_from_today_needs_no_reason(self, client, db, test_user):
        _anna(db, test_user)
        assert _post(client, test_user, {"effective_from": "2026-10-08", "blocks": LONGER}).status_code == 201

    def test_pure_weekly_hours_raise_without_blocks(self, client, db, test_user):
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 45})
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Rückwirkende Verkürzung (Überstundenkonto −")

    def test_legacy_window_to_blocks_with_a_higher_target(self, client, db, test_user):
        window = ("08:00", "16:00")
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=30,
                blocks=legacy_week(mon=window, tue=window, wed=window, thu=window, fri=window))
        day = [window]
        blocks = block_week(pause=30, mon=day, tue=day, wed=day, thu=day, fri=day)
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": blocks}).status_code == 400
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": blocks, **RETRO_REASON})
        assert resp.status_code == 201, resp.text
        assert resp.json()["adjusted_time_entries"] == 0

    def test_smaller_pause_raises_the_target(self, client, db, test_user):
        week = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], **TUE_THU), mon=60)
        add_row(db, test_user, date(2026, 3, 1), week=week)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": with_pauses(week, mon=30)})
        assert resp.status_code == 400, resp.text


class TestClosedYears:
    def _closed_2025(self, db, user):
        user.first_work_day = date(2025, 1, 1)
        db.add(YearCarryover(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                             overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing"))
        db.commit()

    def test_shortening_into_a_closed_year_is_400_even_with_reason(self, client, db, test_user):
        self._closed_2025(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2025-06-02", "weekly_hours": 45, **RETRO_REASON})
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"] == wh_change_service.closed_year_detail([2025])

    def test_lengthening_into_a_closed_year_only_warns(self, client, db, test_user):
        self._closed_2025(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2025-06-02", "weekly_hours": 35})
        assert resp.status_code == 201, resp.text
        assert "Jahresabschluss 2025" in resp.json()["warning"]


class TestModesAndFlags:
    def test_blocks_with_weekly_hours_is_422(self, client, test_user):
        resp = _post(client, test_user, {"effective_from": "2026-11-02", "blocks": K_BLOCKS, "weekly_hours": 7})
        assert (resp.status_code, resp.json()["detail"]) == (422, "Tagesstunden werden aus den Arbeitszeit-Blöcken abgeleitet.")

    def test_track_hours_off_accepts_blocks_and_skips_entries(self, client, db):
        lead = _employee(db, "leitend3", track_hours=False)
        entry(db, lead, MONDAYS[1], t(8), t(18))
        resp = _post(client, lead, {"effective_from": "2026-09-01", "blocks": K_BLOCKS})
        assert resp.status_code == 201, resp.text
        assert (resp.json()["blocks"], resp.json()["hours_monday"]) == (K_BLOCKS, 7.0)
        assert (resp.json()["adjusted_time_entries"], resp.json()["skipped_time_entries"]) == (0, 1)

    @pytest.mark.parametrize("track_hours", [True, False])
    def test_switch_from_blocks_to_weekly_ends_the_blocks(self, client, db, track_hours):
        """P24 (19.1 Nr. 6): blocks = NULL ab dem Wirkungsdatum, auch bei
        track_hours=false; die Vorgängerzeile behält ihre Blöcke."""
        u = _employee(db, f"p24_{track_hours}", track_hours=track_hours)
        add_row(db, u, date(2026, 3, 1), week=ANNA_WEEK)
        resp = _post(client, u, {"effective_from": "2026-10-12", "weekly_hours": 15})
        assert resp.status_code == 201, resp.text
        assert resp.json()["blocks"] is None
        rows = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == u.id).order_by(
            WorkingHoursChange.effective_from).all()
        assert [r.blocks for r in rows] == [ANNA_WEEK, None]

    def test_remove_legacy_window(self, client, db, test_user):
        legacy = legacy_week(mon=("08:00", "17:00"))
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, blocks=legacy)
        carried = _post(client, test_user, {"effective_from": "2026-10-12", "weekly_hours": 38})
        assert carried.json()["blocks"] == legacy
        removed = _post(client, test_user, {"effective_from": "2026-10-19", "weekly_hours": 38,
                                            "remove_legacy_window": True})
        assert removed.status_code == 201, removed.text
        assert removed.json()["blocks"] is None

    def test_reset_of_a_foreign_change_is_404(self, client, db, test_user):
        other = _employee(db, "fremd")
        foreign = add_row(db, other, date(2026, 3, 1), weekly_hours=30)
        resp = _post(client, test_user, {"effective_from": "2026-10-12", "weekly_hours": 30,
                                         "reset_of_change_id": str(foreign.id)})
        assert resp.status_code == 404, resp.text

    def test_saturday_effective_date(self, client, db, test_user):
        """Review Focus 3: Wirkungsdatum Samstag 01.08.2026."""
        _anna(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2026-08-01", "blocks": SHORT, **RETRO_REASON})
        assert resp.status_code == 201, resp.text
        assert resp.json()["adjusted_time_entries"] == 3
        [summary] = reclamp_logs(db, test_user, summary=True)
        assert summary.new_note.startswith("Arbeitszeit-Änderung ab 01.08.2026: 3 Einträge neu berechnet")

    def test_future_change_without_entries_writes_exactly_one_summary(self, client, db, test_user, test_admin):
        """P20: auch ohne Einträge, Abwesenheiten oder Blöcke."""
        resp = _post(client, test_user, {"effective_from": "2026-11-02", "weekly_hours": 25})
        assert resp.status_code == 201, resp.text
        [summary] = reclamp_logs(db, test_user, summary=True)
        assert summary.changed_by == test_admin.id
        assert summary.new_note == (
            "Arbeitszeit-Änderung ab 02.11.2026: 0 Einträge neu berechnet, Δ +0 Min, Saldo Δ +0 Min "
            "· Puffer 15 Min · Vertrag: 40,0 h/Woche (gleichmäßig, 5 Tage) → 25,0 h/Woche (gleichmäßig, 5 Tage)")
        assert reclamp_logs(db, test_user, summary=False) == []

    def test_entry_rows_name_a_deviating_stored_grace(self, client, db, test_user):
        set_grace(db, 10)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        e3 = entry(db, test_user, MONDAYS[3], t(7, 45), t(12), raw_start=t(7, 30))
        entry(db, test_user, MONDAYS[1], t(8), t(12))
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:30")], **TUE_THU)
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": week,
                                         **RETRO_REASON}).status_code == 201
        [row] = reclamp_logs(db, test_user, summary=False)
        assert row.time_entry_id == e3.id
        assert " · Puffer 15 → 10 Min" in row.new_note
        [summary] = reclamp_logs(db, test_user, summary=True)
        assert " · Puffer 10 Min · " in summary.new_note

    def test_put_message_names_the_new_button(self, client, test_user):
        resp = client.put(f"/api/admin/users/{test_user.id}", json={"weekly_hours": 30})
        assert resp.status_code == 400, resp.text
        assert "„Arbeitszeit anpassen…“" in resp.json()["detail"]

    def test_anchor_lock_is_taken_before_the_reclamp(self, client, db, test_user, monkeypatch):
        calls = []
        real_lock = admin_users_router.lock_user_row
        real_run = wh_change_service.run_change
        monkeypatch.setattr(admin_users_router, "lock_user_row",
                            lambda *a, **k: calls.append("lock") or real_lock(*a, **k))
        monkeypatch.setattr(wh_change_service, "run_change",
                            lambda *a, **k: calls.append("run") or real_run(*a, **k))
        assert _post(client, test_user, {"effective_from": "2026-11-02", "weekly_hours": 30}).status_code == 201
        assert calls == ["lock", "run"]


class TestOvertimeHistoryParity:
    def test_history_matches_account_under_the_cutoff_after_reclamp(self, client, db, test_user):
        """Spec 17.5 / #313: nach der Neukappung bleibt ``get_overtime_history`` unter
        dem Saldo-Stichtag bitgleich zu ``get_overtime_account`` (Pflichtinvariante
        aus test_saldo_cutoff.py) — beide lesen die neu gekappten Einträge und die
        nachgezogenen Abwesenheiten."""
        _anna(db, test_user)
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT,
                                         **RETRO_REASON}).status_code == 201
        db.expire_all()
        user = db.get(User, test_user.id)
        cutoff = calculation_service.get_soll_cutoff_date(db, user)
        history = calculation_service.get_overtime_history(db, user, 2026, 10, cutoff_date=cutoff)
        last = max(history)  # (2026, 10) — der laufende Monat, vom Stichtag getrimmt
        assert last == (2026, 10)
        for year, month in ((2026, 9), last):
            assert history[(year, month)] == calculation_service.get_overtime_account(
                db, user, year, month, cutoff_date=cutoff), (year, month)


class TestAuditAfterAnonymisation:
    """Spec 17.5 ``test_reclamp_audit``: ``wh_reclamp``- und ``credit_override``-Zeilen
    tragen ``row_hash`` (#121). Beide Anonymisierungspfade schreiben Protokollnotizen
    über die Objektschicht um (1.18.1) — danach meldet verify-integrity weiter keine
    manipulierte Zeile."""

    def _reclamp_and_recognize(self, client, db, user):
        _anna(db, user)
        assert _post(client, user, {"effective_from": "2026-09-01", "blocks": SHORT,
                                    **RETRO_REASON}).status_code == 201
        cut = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id, TimeEntry.tenant_id == DEFAULT_TENANT_ID,
            TimeEntry.date == MONDAYS[1], TimeEntry.start_time == t(15)).one()
        assert cut.uncredited_minutes == 0 and cut.end_time == t(17, 15)  # Hülle gekürzt → anerkennbar
        resp = client.post(f"/api/admin/time-entries/{cut.id}/credit-override")
        assert resp.status_code == 200, resp.text
        sources = {r.source for r in db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.user_id == user.id, TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID)}
        assert {"wh_reclamp", "credit_override"} <= sources

    def _assert_intact(self, client):
        report = client.get("/api/admin/audit/verify-integrity").json()
        assert (report["tampered"], report["intact"]) == (0, True), report["tampered_ids"]

    def test_after_user_anonymisation(self, client, db, test_user):
        self._reclamp_and_recognize(client, db, test_user)
        test_user.is_active = False   # ohne deactivated_at: Legacy-Zweig, keine 14-Tage-Sperrfrist
        db.commit()
        resp = client.post(f"/api/admin/users/{test_user.id}/anonymize")
        assert resp.status_code == 200, resp.text
        self._assert_intact(client)

    def test_after_tenant_anonymisation(self, client, db, test_user, default_tenant):
        self._reclamp_and_recognize(client, db, test_user)
        lifecycle_service.anonymize_tenant(db, default_tenant)
        self._assert_intact(client)
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_reclamp.py -q -p no:cacheprovider`
Expected: FAIL — u. a. 201 statt 400 (kein Schutzpaket), fehlende Felder `adjusted_time_entries`, keine `wh_reclamp`-Zeilen.

- [ ] **Step 3: Importe (`admin_users.py`)**

```python
from collections import Counter
from typing import Annotated, Any, List, NamedTuple, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status, Query
from app.schemas.working_hours_change import (
    WorkingHoursChangeCreate, WorkingHoursChangeDelete, WorkingHoursChangePreview, WorkingHoursChangeResponse,
)
from app.services import (
    auth_service, calculation_service, lifecycle_service, milog_service, reclamp_audit, settings_service,
    wh_change_service, work_blocks_service, work_window_service,
)
```

(Die bestehenden Zeilen `from typing import …`, `from fastapi import …`, `from app.schemas.working_hours_change import …` und `from app.services import …` werden durch diese ersetzt.)

- [ ] **Step 4: Hilfsfunktionen vor `create_working_hours_change` einfügen**

```python
_CHANGE_NOT_FOUND = "Stundenänderung nicht gefunden"
RESET_CONFLICT_DETAIL = "Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."


def _parse_change_body(raw) -> WorkingHoursChangeCreate:
    """Spec 11.1/3.4: Anlegen und Vorschau prüfen den Body mit DERSELBEN Regel;
    ein Verstoß wird deutscher Klartext (``_schedule_input_error``) — beim
    Speichern als 422, in der Vorschau als ``blocked_reason``. Ein bereits
    gebautes Schema (Direktaufruf in Tests) geht unverändert durch."""
    if isinstance(raw, WorkingHoursChangeCreate):
        return raw
    try:
        return WorkingHoursChangeCreate.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_schedule_input_error(exc)) from None


def _reset_target(db: Session, user: User, current_user: User, change_data: WorkingHoursChangeCreate):
    """P13: (zurückgesetzte Zeile, ihr Vorgänger-Snapshot) — 404, wenn die Zeile
    nicht im Mandanten bzw. nicht bei dieser Person existiert."""
    if change_data.reset_of_change_id is None:
        return None
    row = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.id == change_data.reset_of_change_id,
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail=_CHANGE_NOT_FOUND)
    return row, calculation_service.get_schedule_for_date(db, user, row.effective_from - timedelta(days=1))


def _target_blocks(db: Session, user: User, change_data: WorkingHoursChangeCreate, reset_schedule) -> tuple:
    """Welche Blöcke die neue Zeile trägt (Schedule-Format):
    Rücksetzung → die des Vorgängers (auch ein Altfenster, das der Schreibweg
    sonst nie annimmt); Block-Modus → die gesendeten; ``remove_legacy_window``
    → keine; sonst P2/P24 (``_carried_blocks``: Altfenster läuft weiter, neue
    Blöcke enden mit einem Moduswechsel)."""
    if reset_schedule is not None:
        return reset_schedule.blocks, reset_schedule.block_pauses
    if change_data.blocks is not None:
        parsed = work_blocks_service.parse_week_blocks(change_data.blocks_json())
        return (parsed.blocks, parsed.pauses) if parsed else (None, None)
    if change_data.remove_legacy_window:
        return None, None
    return _carried_blocks(calculation_service.get_schedule_for_date(db, user, change_data.effective_from))


def _reset_matches(change_data: WorkingHoursChangeCreate, norm, reset_schedule) -> bool:
    """P13/11.2: entspricht der Body noch dem Vorgänger-Snapshot der
    zurückgesetzten Zeile? Ein Altfenster ist im Body nicht darstellbar und wird
    deshalb nicht verglichen (der Server übernimmt es selbst)."""
    body = (work_blocks_service.parse_week_blocks(change_data.blocks_json())
            if change_data.blocks is not None else None)
    target = (None if reset_schedule.blocks is None
              else work_blocks_service.ParsedWeek(reset_schedule.blocks, reset_schedule.block_pauses))
    expected = None if work_blocks_service.is_legacy_week(target) else target
    return _comparable_snapshot(
        norm.weekly_hours, norm.use_daily_schedule, norm.day_hours, norm.work_days_per_week,
        body.blocks if body else None, body.pauses if body else None,
    ) == _comparable_snapshot(
        reset_schedule.weekly_hours, reset_schedule.use_daily_schedule, reset_schedule.day_hours,
        reset_schedule.work_days_per_week,
        expected.blocks if expected else None, expected.pauses if expected else None,
    )


def _insert_change_rows(db: Session, user: User, current_user: User, change_data: WorkingHoursChangeCreate,
                        norm, new_blocks, new_pauses, *, sync: bool) -> WorkingHoursChange:
    """Spec 9.3 Schritt 4 — Basis-Zeile (nur ohne Historie; #415/#431, friert
    auch die Blöcke der Vergangenheit ein, E8), neue Zeile, flush und — im
    Schreibpfad — Spiegel der User-Zeile (E9). Unverändert gegenüber der
    bisherigen Logik von ``create_working_hours_change`` (Begründungen dort im
    Git-Verlauf); neu sind nur die Blöcke."""
    has_history = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).first() is not None
    if not has_history:
        current = calculation_service.get_schedule_for_date(
            db, user, change_data.effective_from - timedelta(days=1))
        if _comparable_snapshot(
            current.weekly_hours, current.use_daily_schedule, current.day_hours,
            current.work_days_per_week, current.blocks, current.block_pauses,
        ) != _comparable_snapshot(
            norm.weekly_hours, norm.use_daily_schedule, norm.day_hours,
            norm.work_days_per_week, new_blocks, new_pauses,
        ):
            candidates = [change_data.effective_from - timedelta(days=1)]
            if user.first_work_day:
                candidates.append(user.first_work_day)
            oldest_entry = db.query(func.min(TimeEntry.date)).filter(
                TimeEntry.user_id == user.id, TimeEntry.tenant_id == current_user.tenant_id,  # F-026
            ).scalar()
            oldest_absence = db.query(func.min(Absence.date)).filter(
                Absence.user_id == user.id, Absence.tenant_id == current_user.tenant_id,  # F-026
            ).scalar()
            candidates += [d for d in (oldest_entry, oldest_absence) if d]
            db.add(WorkingHoursChange(
                user_id=user.id, tenant_id=current_user.tenant_id, effective_from=min(candidates),
                weekly_hours=current.weekly_hours, use_daily_schedule=current.use_daily_schedule,
                hours_monday=current.day_hours[0], hours_tuesday=current.day_hours[1],
                hours_wednesday=current.day_hours[2], hours_thursday=current.day_hours[3],
                hours_friday=current.day_hours[4], work_days_per_week=current.work_days_per_week,
                blocks=work_blocks_service.week_blocks_to_json(current.blocks, current.block_pauses),
                note="Automatisch erfasster Ausgangswert vor der ersten Stundenänderung",
            ))
    change = WorkingHoursChange(
        user_id=user.id, tenant_id=current_user.tenant_id, effective_from=change_data.effective_from,
        weekly_hours=norm.weekly_hours, use_daily_schedule=norm.use_daily_schedule,
        hours_monday=norm.day_hours[0], hours_tuesday=norm.day_hours[1],
        hours_wednesday=norm.day_hours[2], hours_thursday=norm.day_hours[3],
        hours_friday=norm.day_hours[4], work_days_per_week=norm.work_days_per_week,
        blocks=work_blocks_service.week_blocks_to_json(new_blocks, new_pauses),
        note=change_data.note,
    )
    db.add(change)
    # Finding 4 (Review 2026-07-14): autoflush=False — ohne flush sähen die
    # folgenden Abfragen die neue Zeile nicht.
    db.flush()
    if sync and change_data.effective_from <= today_local():
        most_recent = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user.id,
            WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
            WorkingHoursChange.effective_from <= today_local(),
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
        if most_recent:
            _sync_user_from_change(user, most_recent)
    return change


def _log_reclamp(db: Session, *, user: User, admin: User, impact, effective_from: date, deleted: bool,
                 reason_type: Optional[str], reason_text: Optional[str], reset_of: Optional[date]) -> None:
    """Spec 10.1/10.2 — je neu gekapptem Eintrag eine Zeile und IMMER genau eine
    Sammelzeile (P20). Per ``db.add`` (row_hash, #121); die Vorschau ruft das nie."""
    shortening = impact.is_shortening
    changed = impact.reclamp.changed
    entries = {}
    if changed:
        entries = {e.id: e for e in db.query(TimeEntry).filter(
            TimeEntry.id.in_([c.entry_id for c in changed]),
            TimeEntry.tenant_id == user.tenant_id,  # F-026
        ).all()}
    for c in changed:
        e = entries[c.entry_id]
        db.add(TimeEntryAuditLog(
            time_entry_id=e.id, user_id=user.id, changed_by=admin.id, action="update",
            source=reclamp_audit.AUDIT_SOURCE, old_date=e.date, new_date=e.date,
            old_start_time=c.old_start, old_end_time=c.old_end,
            new_start_time=c.new_start, new_end_time=c.new_end,
            old_break_minutes=e.break_minutes, new_break_minutes=e.break_minutes,
            old_note=work_window_service.credit_summary_text(impact.entries_before[c.entry_id]),
            new_note=reclamp_audit.entry_new_note(
                work_window_service.credit_summary_text(e), effective_from=effective_from, deleted=deleted,
                old_grace=c.old_grace, grace=impact.grace, shortening=shortening,
                reason_type=reason_type, reason_text_value=reason_text),
            tenant_id=user.tenant_id,
        ))
    db.add(TimeEntryAuditLog(
        time_entry_id=None, user_id=user.id, changed_by=admin.id, action="update",
        source=reclamp_audit.AUDIT_SOURCE,
        new_note=reclamp_audit.summary_note(
            effective_from=effective_from, deleted=deleted, count=len(changed),
            delta_minutes=int(round(sum(float(c.new_net - c.old_net) for c in changed) * 60)),
            saldo_delta_minutes=int(round(float(impact.saldo_delta) * 60)),
            skipped=dict(Counter(s.reason for s in impact.reclamp.skipped)),
            grace=impact.grace, credit_reductions=len(impact.credit_reductions), reset_of=reset_of,
            shortening=shortening, reason_type=reason_type, reason_text_value=reason_text,
            contract_before=reclamp_audit.contract_text(impact.old_schedule, compact=True),
            contract_after=reclamp_audit.contract_text(impact.new_schedule, compact=True),
        ),
        tenant_id=user.tenant_id,
    ))
```

- [ ] **Step 5: `create_working_hours_change` ersetzen**

Die komplette Funktion (Dekorator bis `return change`) ersetzen durch:

```python
@router.post("/users/{user_id}/working-hours-changes", response_model=WorkingHoursChangeResponse, status_code=status.HTTP_201_CREATED)
def create_working_hours_change(
    user_id: str,
    change_data: Annotated[Any, Body()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Arbeitszeit-Änderung anlegen (Spec 9.3) — eine Transaktion unter der
    Ankersperre: Rechenpfad ``wh_change_service.run_change`` (P23-Schließen,
    Neukappung, F1-Rückrechnung, Klassifikation), Schutzpaket (9.5), Protokoll
    (10), Jahresabschluss-Warnung, commit. Ein Verstoß rollt ALLES zurück."""
    change_data = _parse_change_body(change_data)
    user = _get_user_in_tenant(db, user_id, current_user)
    # E52/P5: Ankersperre ZUERST — parallele Schreiber warten und lösen danach
    # den neuen Snapshot auf.
    lock_user_row(db, current_user.tenant_id, user.id)

    if db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        WorkingHoursChange.effective_from == change_data.effective_from,
    ).first():
        raise HTTPException(
            status_code=400,
            detail=f"Eine Stundenänderung für den {change_data.effective_from.strftime('%d.%m.%Y')} existiert bereits",
        )

    reset = _reset_target(db, user, current_user, change_data)
    reset_row, reset_schedule = reset if reset else (None, None)
    norm = _normalise_schedule_input(change_data, user)
    if reset_schedule is not None and not _reset_matches(change_data, norm, reset_schedule):
        raise HTTPException(status_code=409, detail=RESET_CONFLICT_DETAIL)
    new_blocks, new_pauses = _target_blocks(db, user, change_data, reset_schedule)

    created = {}

    def _apply():
        created["row"] = _insert_change_rows(db, user, current_user, change_data, norm,
                                             new_blocks, new_pauses, sync=True)

    impact = wh_change_service.run_change(
        db, user, admin_id=current_user.id, effective_from=change_data.effective_from, apply=_apply)
    error = wh_change_service.protection_error(impact, change_data, deleting=False, reset_offered=False)
    if error:
        db.rollback()  # verwirft Schritte 2–6 (9.3 Schritt 7)
        raise HTTPException(status_code=400, detail=error)

    change = created["row"]
    reason_type = change_data.retroactive_reason_type if impact.is_shortening else None
    change.note = reclamp_audit.compose_change_note(
        change_data.note, reason_type, change_data.retroactive_reason_text)
    _log_reclamp(db, user=user, admin=current_user, impact=impact, effective_from=change_data.effective_from,
                 deleted=False, reason_type=reason_type, reason_text=change_data.retroactive_reason_text,
                 reset_of=reset_row.effective_from if reset_row else None)
    _log_wh_change_retarget(
        db, user=user, admin=current_user, tenant_id=current_user.tenant_id,
        effective_from=impact.window.start, period_end=impact.window.end, adjusted=impact.absences,
        prefix="Arbeitszeit-Änderung", suffix="auf neues Tagessoll nachgezogen",
    )
    # Fix #5: abgeschlossenes Jahr im Wirkungsbereich → nur melden, nie neu rechnen.
    warning = calculation_service.stale_year_closing_warning(
        db, current_user.tenant_id, range(impact.window.start.year, impact.window.end.year + 1))
    db.commit()
    db.refresh(change)
    change.adjusted_absences = len(impact.absences)
    change.adjusted_time_entries = len(impact.reclamp.changed)
    change.skipped_time_entries = len(impact.reclamp.skipped)
    change.warning = warning
    return change
```

- [ ] **Step 6: Meldung der PUT-Sperre (`update_user`)**

Im 400-`detail` des `_HISTORISED_FIELDS`-Blocks „„Wochenstunden anpassen“" durch „„Arbeitszeit anpassen…“" ersetzen; der Text lautet danach (Spec 11.4):

```python
            detail=(
                "Wochenstunden, Tagesstunden, Arbeitstage und Arbeitszeit-Blöcke "
                "werden über „Arbeitszeit anpassen…“ mit Wirkungsdatum geändert, "
                "damit Historie und Soll vergangener Monate korrekt bleiben."
            ),
```

- [ ] **Step 7: Bestandstests der Anlege-Seite auf das Schutzpaket umstellen (Spec 17.6, 19 Nr. 4)**

Ab diesem Task ist jede rückwirkende Soll-**Erhöhung** beim Anlegen eine Verkürzung nach 9.5 (b). Bestandstests, die eine solche Änderung ohne Grund anlegen, prüfen die Rückrechnung, nicht das Schutzpaket — sie senden jetzt `**RETRO_REASON`; ein Test, der ausdrücklich das Speichern ohne Grund prüfte, wird auf die 400-Erwartung umgestellt. Fälle, die einen realen Vorfall kodieren, werden umgeschrieben, nie gelöscht. Die Lösch-Seite (das Löschen einer Senkung hebt das Soll wieder an) stellt Task 11 zusammen mit dem neuen Lösch-Endpunkt um — bis dahin läuft das Löschen über den alten Endpunkt und bleibt grün.

`backend/tests/test_wh_change_retroactive.py` — Import ergänzen und die drei Erhöhungen 20 → 40 h in `TestLegacyHalfDayAbsencesSurvive` mit dem Schutzpaket senden:

```python
from tests.wh_change_helpers import RETRO_REASON
```

```bash
sed -i 's/WorkingHoursChangeCreate(effective_from=mon, weekly_hours=40.0)/WorkingHoursChangeCreate(effective_from=mon, weekly_hours=40.0, **RETRO_REASON)/' backend/tests/test_wh_change_retroactive.py
grep -c "\*\*RETRO_REASON" backend/tests/test_wh_change_retroactive.py
```

Expected: genau `3`.

`backend/tests/test_fix2_whchange_daily_schedule.py` — Import ergänzen:

```python
from tests.wh_change_helpers import RETRO_REASON
```

In `test_whchange_second_superseding_change_updates_to_new_value` die zweite Änderung (20 → 30 h, rückwirkend ab 01.06.2020) ergänzen:

```python
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2020, 6, 1), weekly_hours=30.0, **RETRO_REASON,
        ),
```

`backend/tests/test_absence_raw_hours.py` — die Anlegeaufrufe senken das Soll (40 → 20 h) und bleiben ohne Grund zulässig; umgestellt wird nur das Präfix der Anlege-Seite (Spec 10.3, `_log_wh_change_retarget(prefix="Arbeitszeit-Änderung")` aus Step 5):

```bash
sed -i 's/Krank 4,0 h — Wochenstunden-Änderung ab /Krank 4,0 h — Arbeitszeit-Änderung ab /' backend/tests/test_absence_raw_hours.py
grep -n "Wochenstunden-Änderung" backend/tests/test_absence_raw_hours.py
```

Expected: als Zusicherung nur noch „Löschung der Wochenstunden-Änderung" in `test_delete_writes_per_absence_rows_too` — das ist bis Task 11 richtig (alter Lösch-Endpunkt, Task 11 stellt es um). Scheitert ein Anlegeaufruf in dieser Datei dennoch mit 400 „Rückwirkende Verkürzung …", bekommt er `**RETRO_REASON` (Import `from tests.wh_change_helpers import RETRO_REASON`).

- [ ] **Step 8: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_reclamp.py tests/test_wh_change_legacy_blocks.py tests/test_wh_change_day_plan_create.py tests/test_users_api_work_blocks.py tests/test_wh_change_retroactive.py tests/test_fix2_whchange_daily_schedule.py tests/test_absence_raw_hours.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 9: Volle SQLite-Suite — keine neuen Fehlschläge**

Run (vorher `pgrep -af pytest`): `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py --ignore=tests/test_073_migration_pg.py --ignore=tests/test_net_hours_parity_pg.py --ignore=tests/test_reclamp_concurrency.py`
Expected: keine neuen Fehlschläge gegenüber den Ausgangszahlen (Global Constraints). Scheitert ein weiterer Bestandstest beim **Anlegen** mit 400 „Rückwirkende Verkürzung …", gilt dieselbe Regel wie in Step 7: prüft er die Rückrechnung, bekommt der Anlege-Body `**RETRO_REASON` (HTTP: im JSON); prüft er ausdrücklich das Speichern ohne Grund, wird die Erwartung auf 400 umgestellt — die Datei kommt dann mit in den Commit. Ein Fehlschlag auf der Lösch-Seite ist in diesem Task ein Fehler (das Löschen ist noch unverändert) und wird hier behoben, nicht nach Task 11 verschoben. Einen Test nie löschen.

- [ ] **Step 10: Commit**

```bash
git add backend/app/routers/admin_users.py backend/tests/test_reclamp.py backend/tests/test_wh_change_retroactive.py backend/tests/test_fix2_whchange_daily_schedule.py backend/tests/test_absence_raw_hours.py
git commit -F - <<'EOF'
feat(bloecke): Arbeitszeit-Änderung mit Neukappung, Schutzpaket und Protokoll (9.3, 9.5, 10)

Bestandstests mit rückwirkender Soll-Erhöhung beim Anlegen senden das
Schutzpaket (17.6).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 10: Vorschau per `POST` mit untypisiertem Body (Spec 11.1, 11.3, 9.3, P9)

**Files:**
- Modify: `backend/app/routers/admin_users.py` (`preview_working_hours_change` komplett ersetzt)
- Modify: `backend/tests/test_wh_change_preview.py` (GET → POST)
- Test (neu): `backend/tests/test_wh_change_preview_blocks.py`

**Interfaces:**
- Consumes: `_reset_target`, `_reset_matches`, `_target_blocks`, `_insert_change_rows(…, sync=False)`, `RESET_CONFLICT_DETAIL` (Task 9); `wh_change_service.run_change`, `preview_fields` (Task 8); `work_blocks_service.block_break_notices` (Task 5); `_schedule_input_error` (Task 3)
- Produces: `POST /api/admin/users/{id}/working-hours-changes/preview` — Body wie Speichern (untypisiert), Antwort `WorkingHoursChangePreview` mit allen 11.3-Feldern; Eingabefehler, fremde/abweichende Rücksetzung und belegtes Datum → `blocked_reason`; fehlendes/ungültiges Datum → `blocked_reason = "Bitte ein gültiges Wirkungsdatum angeben."`; das alte `GET …/preview` antwortet 405. `PREVIEW_DATE_MISSING` als Konstante.
- Produces (Hilfsfunktion in `app.routers.admin_users`, von Task 11 für `delete-preview` mitbenutzt): `_week_day_targets(user: User, effective_from: date, schedule: Schedule) -> List[float]` — Tagessoll Mo–Fr des übergebenen Snapshots als `float`, aus `get_daily_target_for_date` ab dem Montag der Woche von `effective_from` (Vorschaufelder `day_targets_current`/`day_targets_new`)

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_wh_change_preview_blocks.py`:

```python
"""Spec 11.1/11.3: Vorschau per POST — untypisiert, nie 422 beim Tippen, rollt
immer zurück, protokolliert nie."""
from datetime import date

import pytest

from app.models import Absence, AbsenceType, TimeEntry, TimeEntryAuditLog, WorkingHoursChange
from app.routers.admin_users import PREVIEW_DATE_MISSING, RESET_CONFLICT_DETAIL
from app.services import wh_change_service
from tests.test_endpoints import test_app
from tests.wh_change_helpers import (
    ANNA_WEEK, MONDAYS, absence, add_row, admin_client, entry, freeze, t, with_pauses,
)
from tests.work_blocks_fixtures import block_week

TUE_THU = dict(tue=[("08:00", "12:00")], thu=[("08:00", "12:00")])
SHORT = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], **TUE_THU)
LONGER_PAUSED = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], **TUE_THU), mon=60)


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch)
    c = admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _preview(client, user, body):
    resp = client.post(f"/api/admin/users/{user.id}/working-hours-changes/preview", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _anna(db, user, *, afternoon_14=None, afternoon_21=None):
    add_row(db, user, date(2026, 3, 1), week=ANNA_WEEK)
    absence(db, user, MONDAYS[0], AbsenceType.VACATION, 7.0)
    for d in MONDAYS[1:]:
        entry(db, user, d, t(8), t(12))
        if d == MONDAYS[1] and afternoon_14:
            entry(db, user, d, t(15), afternoon_14[0], raw_end=afternoon_14[1])
        elif d == MONDAYS[2] and afternoon_21:
            entry(db, user, d, t(15), afternoon_21[0], raw_end=afternoon_21[1])
        else:
            entry(db, user, d, t(15), t(18), credit_override=(d == MONDAYS[3]))


def _week_with(mon):
    week = block_week(**TUE_THU)
    week[0] = mon
    return week


class TestUnfinishedInput:
    """Review Focus 1: unfertige Eingaben kommen als blocked_reason, nie als 422."""

    @pytest.mark.parametrize("mon, message", [
        ({"blocks": [{"start": "", "end": "12:00"}], "pause_minutes": 0}, "Mo, Block 1: Uhrzeit im Format HH:MM angeben."),
        ({"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": None}, "Mo: Pause angeben (0, wenn keine)."),
        ({"blocks": [{"start": "08:07", "end": "12:00"}], "pause_minutes": 0},
         "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."),
        ({"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": 240},
         "Mo: Pause muss kürzer sein als die Gesamtzeit der Blöcke."),
        ({"blocks": [{"start": 8, "end": "12:00"}], "pause_minutes": 0}, "Mo, Block 1, Beginn: ungültiger Wert."),
    ])
    def test_unfinished_blocks(self, client, test_user, mon, message):
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": _week_with(mon)})
        assert body["blocked_reason"] == message
        assert body["affected_time_entries"] == 0

    @pytest.mark.parametrize("raw", [{}, {"effective_from": "2026-13-01", "weekly_hours": 30}, {"weekly_hours": 30}])
    def test_missing_or_broken_date(self, client, test_user, raw):
        assert _preview(client, test_user, raw)["blocked_reason"] == PREVIEW_DATE_MISSING

    def test_old_get_preview_is_gone(self, client, test_user):
        resp = client.get(f"/api/admin/users/{test_user.id}/working-hours-changes/preview"
                          f"?effective_from=2026-09-01&weekly_hours=30")
        assert resp.status_code == 405


class TestImpactFields:
    def test_first_state(self, client, db, test_user):
        _anna(db, test_user)
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert (body["is_retroactive"], body["period_start"], body["period_end"]) == (True, "2026-09-01", "2026-10-08")
        assert (body["grace_minutes"], body["changed_weekdays"], body["affected_time_entries"]) == (15, [0], 3)
        assert body["time_entry_months"] == [
            {"month": "2026-09", "entries": 2, "net_before": 6.0, "net_after": 4.5},
            {"month": "2026-10", "entries": 1, "net_before": 3.0, "net_after": 2.25},
        ]
        assert [s["reason"] for s in body["skipped_time_entries"]] == ["credit_override"]
        assert (body["target_delta_hours"], body["credited_delta_hours"], body["saldo_delta_hours"]) == (-4.0, -2.25, 1.75)
        assert (body["is_shortening"], body["shortening_reasons"], body["earliest_lossless_date"]) == (
            True, ["entries"], "2026-10-08")
        assert (body["lost_credited_hours"], body["affected_absences"]) == (2.25, 1)
        assert body["blocks_current"] == ANNA_WEEK and body["blocks_new"] == SHORT
        assert body["time_entry_changes"][0]["new_end"] == "17:15:00"
        assert body["overtime_after"] - body["overtime_before"] == pytest.approx(1.75)
        assert body["milog_warning"] == [wh_change_service.MILOG_GENERAL_WARNING]

    def test_preview_writes_and_logs_nothing(self, client, db, test_user):
        _anna(db, test_user)
        stale = entry(db, test_user, date(2026, 10, 6), t(8), None)

        def state():
            db.expire_all()
            return (
                sorted((str(e.id), e.start_time, e.end_time, e.raw_start_time, e.raw_end_time,
                        e.uncredited_minutes, e.clamp_grace_minutes)
                       for e in db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id)),
                sorted(float(a.hours) for a in db.query(Absence).filter(Absence.user_id == test_user.id)),
                db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).count(),
                db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.user_id == test_user.id).count(),
            )

        before = state()
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert body["stale_entries_closed"] == 1
        assert state() == before
        db.refresh(stale)
        assert stale.end_time is None

    def test_second_preview_at_the_earliest_date_is_lossless(self, client, db, test_user):
        _anna(db, test_user)
        first = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        second = _preview(client, test_user, {"effective_from": first["earliest_lossless_date"], "blocks": SHORT})
        assert (second["is_shortening"], second["affected_time_entries"]) == (False, 0)

    def test_milog_warning_with_agreed_monthly_hours(self, client, db, test_user):
        _anna(db, test_user)
        test_user.agreed_monthly_hours = 65.0
        db.commit()
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert body["milog_warning"] == [wh_change_service.MILOG_ACCOUNT_WARNING, wh_change_service.MILOG_GENERAL_WARNING]

    def test_lengthening_lists_the_not_extendable_entry(self, client, db, test_user):
        _anna(db, test_user, afternoon_14=(t(18, 15), None), afternoon_21=(t(18, 15), t(18, 30)))
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER_PAUSED})
        assert (body["is_shortening"], body["milog_warning"], body["not_extendable_count"]) == (False, [], 1)
        [flag] = body["not_extendable_entries"]
        assert (flag["date"], flag["not_extendable"], flag["old_end"]) == ("2026-09-14", "end", "18:15:00")

    def test_plan_notices_come_with_the_preview(self, client, test_user):
        body = _preview(client, test_user, {"effective_from": "2026-11-02",
                                            "blocks": block_week(mon=[("07:00", "12:00"), ("12:10", "17:10")])})
        assert ("Mo: geplant 10:00 h Arbeit, eingeplante Pausen 0 Min – nach § 4 ArbZG sind mindestens 45 Minuten "
                "nötig.") in body["block_break_notices"]
        assert body["blocked_reason"] is None

    def test_reset_body_that_no_longer_matches_is_blocked(self, client, db, test_user):
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=40)
        later = add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
        body = _preview(client, test_user, {"effective_from": "2026-10-08", "use_daily_schedule": False,
                                            "weekly_hours": 39, "work_days_per_week": 5,
                                            "reset_of_change_id": str(later.id)})
        assert body["blocked_reason"] == RESET_CONFLICT_DETAIL

    def test_pure_block_shift_is_a_change_unchanged_blocks_are_not(self, client, db, test_user):
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, date(2026, 9, 15), t(8), t(12))
        shifted = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("09:00", "13:00")],
                             thu=[("08:00", "12:00")])
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": shifted})
        assert (body["changed_weekdays"], body["affected_time_entries"]) == ([1], 1)
        same = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": ANNA_WEEK})
        assert (same["changed_weekdays"], same["affected_time_entries"], same["is_shortening"]) == ([], 0, False)

    def test_saturday_effective_date(self, client, db, test_user):
        """Review Focus 3."""
        _anna(db, test_user)
        body = _preview(client, test_user, {"effective_from": "2026-08-01", "blocks": SHORT})
        assert (body["period_start"], body["affected_time_entries"], body["earliest_lossless_date"]) == (
            "2026-08-01", 3, "2026-10-08")
```

- [ ] **Step 2: Bestandssuite auf POST umstellen (`test_wh_change_preview.py`)**

Den Helfer `_url` ersetzen durch:

```python
def _req(user_id, eff, hours=20.0):
    """Spec 11.1: die Vorschau ist POST mit JSON-Body (dieselbe Body-Verarbeitung
    wie beim Speichern)."""
    return {"url": f"/api/admin/users/{user_id}/working-hours-changes/preview",
            "json": {"effective_from": eff.isoformat(), "weekly_hours": hours}}
```

den Helfer `_preview` ersetzen durch:

```python
def _preview(client, user, eff, **params):
    """Vorschau mit beliebigen Snapshot-Feldern (Tagesplan-Modus)."""
    return client.post(
        f"/api/admin/users/{user.id}/working-hours-changes/preview",
        json={"effective_from": eff.isoformat(), **params},
    )
```

und die Aufrufe umschreiben (aus der Repo-Wurzel):

```bash
sed -i 's/client\.get(_url(/client.post(**_req(/g; s/ c\.get(_url(/ c.post(**_req(/g' backend/tests/test_wh_change_preview.py
grep -c "_req(" backend/tests/test_wh_change_preview.py
grep -n "_url(\|\.get(" backend/tests/test_wh_change_preview.py
```

Expected: `_req(` mindestens 30 Treffer; die zweite Suche zeigt keine Vorschau-Aufrufe mehr (nur ggf. Verlaufs-GETs).

- [ ] **Step 3: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_preview_blocks.py tests/test_wh_change_preview.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'PREVIEW_DATE_MISSING'`; in der Bestandssuite 405 auf POST.

- [ ] **Step 4: Endpunkt ersetzen**

`preview_working_hours_change` komplett (Dekorator bis Ende der Funktion) ersetzen durch:

```python
PREVIEW_DATE_MISSING = "Bitte ein gültiges Wirkungsdatum angeben."


def _week_day_targets(user: User, effective_from: date, schedule) -> List[float]:
    """Tagessoll je Wochentag Mo…Fr (Fund 3, Release-Review 1.17.0): der Montag
    der Woche trägt nur den Wochentag, die Snapshots sind explizit übergeben."""
    week_monday = effective_from - timedelta(days=effective_from.weekday())
    return [float(calculation_service.get_daily_target_for_date(user, week_monday + timedelta(days=i), schedule))
            for i in range(5)]


@router.post("/users/{user_id}/working-hours-changes/preview", response_model=WorkingHoursChangePreview)
def preview_working_hours_change(
    user_id: str,
    body: Annotated[Any, Body()] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Spec 11.1/11.3 — strikt lesende Vorschau. Body wie beim Speichern, aber
    UNTYPISIERT entgegengenommen und intern geprüft: ein Verstoß ist
    ``blocked_reason``, nie ein hartes 422 beim Tippen. Führt dieselben Schritte
    2–7 wie das Speichern in EINEM flush/Rollback-Lauf aus (inkl. P23-Schließen,
    Neukappung, F1-Rückrechnung) und rollt IMMER zurück — nichts wird
    geschrieben, nichts protokolliert, keine Ankersperre (9.3)."""
    user = _get_user_in_tenant(db, user_id, current_user)
    today = today_local()
    raw = body if isinstance(body, dict) else {}
    try:
        effective_from = date.fromisoformat(str(raw.get("effective_from")))
    except ValueError:
        effective_from = None
    if effective_from is None:
        effective_from, raw = today, {}
        date_error = PREVIEW_DATE_MISSING
    else:
        date_error = None

    window = calculation_service.retarget_window(db, user, effective_from)
    current_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    input_error = date_error
    change_data = norm = reset_schedule = None
    if input_error is None:
        try:
            change_data = WorkingHoursChangeCreate.model_validate(raw)
            norm = _normalise_schedule_input(change_data, user)
        except ValidationError as exc:
            input_error = _schedule_input_error(exc)
    if change_data is not None and input_error is None and change_data.reset_of_change_id is not None:
        try:
            reset_schedule = _reset_target(db, user, current_user, change_data)[1]
            if not _reset_matches(change_data, norm, reset_schedule):
                input_error = RESET_CONFLICT_DETAIL
        except HTTPException as exc:
            input_error = str(exc.detail)

    new_schedule = current_schedule
    new_blocks, new_pauses = current_schedule.blocks, current_schedule.block_pauses
    if norm is not None and input_error is None:
        new_blocks, new_pauses = _target_blocks(db, user, change_data, reset_schedule)
        new_schedule = calculation_service.Schedule(
            weekly_hours=Decimal(str(norm.weekly_hours)),
            use_daily_schedule=norm.use_daily_schedule,
            day_hours=tuple(None if v is None else Decimal(str(v)) for v in norm.day_hours),
            work_days_per_week=norm.work_days_per_week,
            blocks=new_blocks,
            block_pauses=new_pauses,
        )
    day_targets_current = _week_day_targets(user, effective_from, current_schedule)
    day_targets_new = _week_day_targets(user, effective_from, new_schedule)

    blocked_reason = input_error
    if not blocked_reason and db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        WorkingHoursChange.effective_from == effective_from,
    ).first():
        blocked_reason = f"Eine Stundenänderung für den {effective_from.strftime('%d.%m.%Y')} existiert bereits"

    # Kurzschluss „Snapshot unverändert" — einschließlich kanonischer Blöcke und
    # Pausen (11.3): eine reine Blockänderung IST eine Änderung.
    snapshot_unchanged = norm is not None and not blocked_reason and _comparable_snapshot(
        current_schedule.weekly_hours, current_schedule.use_daily_schedule,
        current_schedule.day_hours, current_schedule.work_days_per_week,
        current_schedule.blocks, current_schedule.block_pauses,
    ) == _comparable_snapshot(
        norm.weekly_hours, norm.use_daily_schedule, norm.day_hours, norm.work_days_per_week,
        new_blocks, new_pauses,
    )

    # Saldo-Monatsgrenze = heute (Review-Fund 4, Fix-Runde 1), getrimmt über den Stichtag.
    cutoff = calculation_service.get_soll_cutoff_date(db, user)
    vacation_year = window.start.year
    overtime_before = float(calculation_service.get_overtime_account(
        db, user, today.year, today.month, cutoff_date=cutoff))
    vacation_before = float(calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
    overtime_after, vacation_after = overtime_before, vacation_before
    fields: dict = {"affected_absences": 0}
    if not blocked_reason and not snapshot_unchanged:
        try:
            impact = wh_change_service.run_change(
                db, user, admin_id=current_user.id, effective_from=effective_from,
                apply=lambda: _insert_change_rows(db, user, current_user, change_data, norm,
                                                  new_blocks, new_pauses, sync=False),
            )
            overtime_after = float(calculation_service.get_overtime_account(
                db, user, today.year, today.month, cutoff_date=cutoff))
            vacation_after = float(calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
            fields = wh_change_service.preview_fields(impact, user)
        finally:
            db.rollback()

    closed_years = calculation_service.closed_years_in_range(
        db, current_user.tenant_id, range(window.start.year, window.end.year + 1))
    grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    notices = []
    if change_data is not None and change_data.blocks is not None and input_error is None:
        notices = work_blocks_service.block_break_notices(
            change_data.blocks_json(), grace, exempt=bool(getattr(user, "exempt_from_arbzg", False)))

    return WorkingHoursChangePreview(
        is_retroactive=effective_from < today,
        period_start=window.start,
        period_end=window.end,
        current_daily_target=_planned_day_mean(day_targets_current),
        new_daily_target=_planned_day_mean(day_targets_new),
        day_targets_current=day_targets_current,
        day_targets_new=day_targets_new,
        overtime_before=overtime_before,
        overtime_after=overtime_after,
        vacation_days_before=vacation_before,
        vacation_days_after=vacation_after,
        blocked_reason=blocked_reason,
        closed_years=closed_years,
        closed_year_warning=calculation_service.closed_year_warning_text(closed_years),
        grace_minutes=grace,
        blocks_current=work_blocks_service.week_blocks_to_json(current_schedule.blocks, current_schedule.block_pauses),
        blocks_new=work_blocks_service.week_blocks_to_json(new_blocks, new_pauses),
        block_break_notices=notices,
        **fields,
    )
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_preview_blocks.py tests/test_wh_change_preview.py tests/test_wh_change_legacy_blocks.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin_users.py backend/tests/test_wh_change_preview.py backend/tests/test_wh_change_preview_blocks.py
git commit -F - <<'EOF'
feat(bloecke): Vorschau per POST mit Neukappung, Verkürzungskriterien und Plan-Hinweisen (11.1, 11.3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 11: Löschen mit `delete-preview`, Schutzpaket und „auf vorherigen Stand zurücksetzen" (Spec 9.7, P8, P13, 11.1, 11.4)

**Files:**
- Modify: `backend/app/routers/admin_users.py` (neu `_change_in_tenant`, `_earliest_row_lock_detail`, `delete_preview_working_hours_change`; `delete_working_hours_change` komplett ersetzt)
- Test (neu): `backend/tests/test_wh_change_delete_reclamp.py`
- Modify (Bestandstests der Lösch-Seite, Spec 17.6): `backend/tests/test_wh_change_retroactive.py`, `backend/tests/test_wh_change_day_plan_delete.py`, `backend/tests/test_absence_raw_hours.py`, `backend/tests/test_wh_change_legacy_blocks.py`

**Interfaces:**
- Consumes: `WorkingHoursChangeDelete` (Task 3); `RETRO_REASON` (Task 6); `run_change`, `preview_fields`, `protection_error`, `reset_body` (Task 8); `_log_reclamp` (Task 9); `_week_day_targets(user: User, effective_from: date, schedule: Schedule) -> List[float]` (Task 10); `_sync_user_from_change` (PR1)
- Produces:
  - `POST /api/admin/users/{id}/working-hours-changes/{change_id}/delete-preview` — Antwort 11.3 plus `reset_body` (nur wenn das Löschen verkürzt **und** `earliest_lossless_date` nach dem `effective_from` der Zeile liegt; sonst `null`); früheste Zeile → `blocked_reason`
  - `DELETE …/{change_id}` mit optionalem Body `WorkingHoursChangeDelete`; 200 `{adjusted_absences, adjusted_time_entries, skipped_time_entries, warning}` sobald etwas angepasst oder gewarnt wurde, sonst 204
  - `_change_in_tenant(db, user_id, change_id, current_user) -> WorkingHoursChange` (404), `_earliest_row_lock_detail(db, user, current_user, change) -> Optional[str]`

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_wh_change_delete_reclamp.py`:

```python
"""Spec 9.7/P13 (19.1 Nr. 4): Löschen einer Verlaufszeile — symmetrische
Rückrechnung, Verkürzungsschutz, Rücksetzung statt Löschen."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import AbsenceType, TimeEntry, WorkingHoursChange, YearCarryover
from app.services import wh_change_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.wh_change_helpers import (
    ANNA_WEEK, MONDAYS, RETRO_REASON, absence, add_row, admin_client, entry, freeze, reclamp_logs, t,
    with_pauses,
)
from tests.work_blocks_fixtures import block_week

LONGER_PAUSED = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], tue=[("08:00", "12:00")],
                                       thu=[("08:00", "12:00")]), mon=60)


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch)
    c = admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _create(client, user, body):
    resp = client.post(f"/api/admin/users/{user.id}/working-hours-changes", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _delete_preview(client, user, change_id):
    resp = client.post(f"/api/admin/users/{user.id}/working-hours-changes/{change_id}/delete-preview", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _delete(client, user, change_id, body=None):
    return client.request("DELETE", f"/api/admin/users/{user.id}/working-hours-changes/{change_id}", json=body)


def _rows(db, user):
    db.expire_all()
    return [(r.effective_from, float(r.weekly_hours)) for r in db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id).order_by(WorkingHoursChange.effective_from)]


class TestReset:
    def test_deleting_a_target_drop_is_a_shortening_with_reset_body(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["shortening_reasons"], body["earliest_lossless_date"]) == (
            True, ["saldo"], "2026-10-08")
        assert body["reset_body"] == {
            "effective_from": "2026-10-08", "reset_of_change_id": change["id"], "use_daily_schedule": False,
            "weekly_hours": 40.0, "work_days_per_week": 5, "remove_legacy_window": True}

    def test_reset_body_creates_a_new_row_and_keeps_the_old_one(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        reset = _delete_preview(client, test_user, change["id"])["reset_body"]
        created = _create(client, test_user, reset)
        assert created["adjusted_time_entries"] == 0
        assert _rows(db, test_user) == [(date(2026, 8, 31), 40.0), (date(2026, 9, 1), 30.0), (date(2026, 10, 8), 40.0)]
        notes = [s.new_note for s in reclamp_logs(db, test_user, summary=True)]
        assert any(" · Rücksetzung der Änderung ab 01.09.2026 · " in n for n in notes)

    def test_changed_reset_body_is_409(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        reset = _delete_preview(client, test_user, change["id"])["reset_body"]
        resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes", json={**reset, "weekly_hours": 39})
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == "Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."

    def test_reset_body_with_blocks_is_accepted_after_track_hours_went_off(self, client, db, test_user):
        """Spec 17.2 / P24: die Rücksetzung trägt die Blöcke der Vorgängerzeile. Wurde
        die Person inzwischen auf track_hours=false gestellt (leitend, #191), nimmt
        der Anlege-Endpunkt den unveränderten reset_body trotzdem an — Blöcke sind
        dort zulässig („ohne Wirkung", 11.2), die Zeile behält sie."""
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        shorter = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], tue=[("08:00", "12:00")],
                             thu=[("08:00", "12:00")])
        change = _create(client, test_user, {"effective_from": "2026-09-01", "blocks": shorter})
        reset = _delete_preview(client, test_user, change["id"])["reset_body"]
        assert reset == {"effective_from": "2026-10-08", "reset_of_change_id": change["id"], "blocks": ANNA_WEEK}
        test_user.track_hours = False
        db.commit()
        resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes", json=reset)
        assert resp.status_code == 201, resp.text
        assert resp.json()["blocks"] == ANNA_WEEK
        db.expire_all()
        last = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == test_user.id, WorkingHoursChange.tenant_id == DEFAULT_TENANT_ID,
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
        assert (last.effective_from, last.blocks) == (date(2026, 10, 8), ANNA_WEEK)

    def test_no_reset_body_when_deleting_does_not_shorten(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 45, **RETRO_REASON})
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["reset_body"]) == (False, None)

    def test_no_reset_body_when_p25_applies(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        _create(client, test_user, {"effective_from": "2026-10-08", "weekly_hours": 35})
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["reset_body"], body["earliest_lossless_date"]) == (True, None, None)
        resp = _delete(client, test_user, change["id"])
        assert resp.status_code == 400
        assert resp.json()["detail"].endswith(
            "– oder abbrechen: Die Änderung liegt vollständig vor der Änderung ab 08.10.2026; "
            "nur rückwirkend mit Begründung oder abbrechen.")


class TestRetroactiveDelete:
    def test_without_reason_is_400_with_reset_hint(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        resp = _delete(client, test_user, change["id"])
        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert detail.startswith("Das Löschen verkürzt rückwirkend (Überstundenkonto −")
        assert detail.endswith("– oder ab dem 08.10.2026 auf den vorherigen Stand zurücksetzen.")
        assert len(_rows(db, test_user)) == 2

    def test_with_reason_deletes_and_answers_204_without_adjustments(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        assert _delete(client, test_user, change["id"], RETRO_REASON).status_code == 204
        assert _rows(db, test_user) == [(date(2026, 8, 31), 40.0)]
        [summary] = [s for s in reclamp_logs(db, test_user, summary=True) if " gelöscht: " in s.new_note]
        assert summary.new_note.startswith("Arbeitszeit-Änderung ab 01.09.2026 gelöscht: 0 Einträge neu berechnet")
        assert " · Verkürzung · Grund: [Erfassungsfehler korrigiert] " in summary.new_note

    def test_with_reason_and_an_adjusted_absence_answers_200(self, client, db, test_user):
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 8.0)
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        resp = _delete(client, test_user, change["id"], RETRO_REASON)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"adjusted_absences": 1, "adjusted_time_entries": 0, "skipped_time_entries": 0,
                               "warning": None}

    def test_loss_in_a_closed_year_is_400(self, client, db, test_user):
        test_user.first_work_day = date(2025, 1, 1)
        db.add(YearCarryover(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                             overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing"))
        db.commit()
        change = _create(client, test_user, {"effective_from": "2025-06-02", "weekly_hours": 30})
        resp = _delete(client, test_user, change["id"], RETRO_REASON)
        assert (resp.status_code, resp.json()["detail"]) == (400, wh_change_service.closed_year_detail([2025]))

    def test_earliest_row_stays_locked(self, client, db, test_user):
        _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        baseline = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).order_by(
            WorkingHoursChange.effective_from).first()
        body = _delete_preview(client, test_user, baseline.id)
        assert body["blocked_reason"].startswith("Dies ist die früheste erfasste Stundenänderung")
        assert _delete(client, test_user, baseline.id).status_code == 400


def test_create_then_delete_restores_every_entry(client, db, test_user):
    """Spec 17.5 Reversibilität: anlegen + löschen → alle Einträge byte-gleich."""
    add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
    for d in MONDAYS[1:]:
        entry(db, test_user, d, t(8), t(12))
    entry(db, test_user, MONDAYS[1], t(15), t(18, 15))
    entry(db, test_user, MONDAYS[2], t(15), t(18, 15), raw_end=t(18, 30))
    entry(db, test_user, MONDAYS[4], t(15), t(18))

    def snapshot():
        db.expire_all()
        return sorted((str(e.id), e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, e.uncredited_minutes)
                      for e in db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id))

    before = snapshot()
    change = _create(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER_PAUSED})
    assert change["adjusted_time_entries"] == 1
    assert snapshot() != before
    resp = _delete(client, test_user, change["id"], RETRO_REASON)
    assert resp.status_code == 200, resp.text
    assert snapshot() == before
    db.expire_all()
    assert {e.clamp_grace_minutes for e in db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id)} == {15}
    [row] = [r for r in reclamp_logs(db, test_user, summary=False) if "Löschung" in r.new_note]
    assert row.new_note.endswith("— Löschung der Arbeitszeit-Änderung ab 01.09.2026 · Grund: "
                                      f"[Erfassungsfehler korrigiert] {RETRO_REASON['retroactive_reason_text']}")
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_delete_reclamp.py -q -p no:cacheprovider`
Expected: FAIL — 404/405 auf `delete-preview`, kein 400 beim Löschen.

- [ ] **Step 3: Hilfsfunktionen und `delete-preview`**

Vor `delete_working_hours_change` einfügen:

```python
def _change_in_tenant(db: Session, user_id: str, change_id, current_user: User) -> WorkingHoursChange:
    """F-026: Verlaufszeile der Person im Mandanten, sonst 404."""
    change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.id == change_id,
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,
    ).first()
    if not change:
        raise HTTPException(status_code=404, detail=_CHANGE_NOT_FOUND)
    return change


def _earliest_row_lock_detail(db: Session, user: User, current_user: User, change: WorkingHoursChange) -> Optional[str]:
    """Critical fix (Review-Fund, bestehende Regel): die früheste Zeile verankert
    den davor gültigen Wert — gesperrt, solange spätere existieren."""
    rows = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).order_by(WorkingHoursChange.effective_from.asc()).all()
    if len(rows) > 1 and rows[0].id == change.id:
        return (
            "Dies ist die früheste erfasste Stundenänderung dieses "
            "Mitarbeiters — sie verankert den davor gültigen Wert, der "
            "sonst nirgends mehr gespeichert ist. Bitte zuerst die "
            "späteren Änderungen löschen, wenn die Historie komplett "
            "zurückgesetzt werden soll."
        )
    return None


@router.post("/users/{user_id}/working-hours-changes/{change_id}/delete-preview",
             response_model=WorkingHoursChangePreview)
def delete_preview_working_hours_change(
    user_id: str,
    change_id: str,
    body: Annotated[Any, Body()] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Spec 9.7/P8 — Vorschau des Löschens (gleiche Antwortform wie die
    Vorschau): Rückrechnung gegen den Vorgänger-Snapshot in flush/Rollback,
    Klassifikation nach 9.5 (a)–(c), ``reset_body`` für „ab ‹Datum› auf den
    vorherigen Stand zurücksetzen" (P13), wenn das Löschen verkürzt und das
    früheste verlustfreie Datum nach dem Wirkungsdatum der Zeile liegt."""
    change = _change_in_tenant(db, user_id, change_id, current_user)
    user = _get_user_in_tenant(db, user_id, current_user)
    today = today_local()
    effective_from = change.effective_from
    window = calculation_service.retarget_window(db, user, effective_from)
    current_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    predecessor = calculation_service.get_schedule_for_date(db, user, effective_from - timedelta(days=1))
    blocked_reason = _earliest_row_lock_detail(db, user, current_user, change)
    cutoff = calculation_service.get_soll_cutoff_date(db, user)
    vacation_year = window.start.year
    overtime_before = float(calculation_service.get_overtime_account(
        db, user, today.year, today.month, cutoff_date=cutoff))
    vacation_before = float(calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
    overtime_after, vacation_after = overtime_before, vacation_before
    fields: dict = {"affected_absences": 0}
    reset = None
    if not blocked_reason:
        try:
            impact = wh_change_service.run_change(
                db, user, admin_id=current_user.id, effective_from=effective_from,
                apply=lambda: db.delete(change),
            )
            overtime_after = float(calculation_service.get_overtime_account(
                db, user, today.year, today.month, cutoff_date=cutoff))
            vacation_after = float(calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
            fields = wh_change_service.preview_fields(impact, user)
            earliest = impact.earliest_lossless_date
            if impact.is_shortening and earliest is not None and earliest > effective_from:
                reset = wh_change_service.reset_body(predecessor, earliest, change.id)
        finally:
            db.rollback()
    closed_years = calculation_service.closed_years_in_range(
        db, current_user.tenant_id, range(window.start.year, window.end.year + 1))
    day_targets_current = _week_day_targets(user, effective_from, current_schedule)
    day_targets_new = _week_day_targets(user, effective_from, predecessor)
    return WorkingHoursChangePreview(
        is_retroactive=effective_from < today,
        period_start=window.start,
        period_end=window.end,
        current_daily_target=_planned_day_mean(day_targets_current),
        new_daily_target=_planned_day_mean(day_targets_new),
        day_targets_current=day_targets_current,
        day_targets_new=day_targets_new,
        overtime_before=overtime_before,
        overtime_after=overtime_after,
        vacation_days_before=vacation_before,
        vacation_days_after=vacation_after,
        blocked_reason=blocked_reason,
        closed_years=closed_years,
        closed_year_warning=calculation_service.closed_year_warning_text(closed_years),
        grace_minutes=work_window_service.get_grace_minutes(db, current_user.tenant_id),
        blocks_current=work_blocks_service.week_blocks_to_json(current_schedule.blocks, current_schedule.block_pauses),
        blocks_new=work_blocks_service.week_blocks_to_json(predecessor.blocks, predecessor.block_pauses),
        reset_body=reset,
        **fields,
    )
```

- [ ] **Step 4: `delete_working_hours_change` ersetzen**

Die komplette Funktion ersetzen durch:

```python
@router.delete("/users/{user_id}/working-hours-changes/{change_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_working_hours_change(
    user_id: str,
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    body: Annotated[Optional[WorkingHoursChangeDelete], Body()] = None,
):
    """Spec 9.7 — symmetrisches Löschen: dieselbe Transaktion wie das Anlegen
    (Ankersperre, P23, Neukappung gegen den Vorgänger-Snapshot, F1-Rückrechnung,
    Klassifikation, Protokoll inkl. Sammelzeile „… gelöscht", Jahreswarnung).
    Verkürzt das Löschen, braucht es das Schutzpaket im optionalen Body (P8);
    der verlustfreie Weg ist die Rücksetzung per ``reset_body`` (P13)."""
    change = _change_in_tenant(db, user_id, change_id, current_user)
    user = _get_user_in_tenant(db, user_id, current_user)
    lock_user_row(db, current_user.tenant_id, user.id)  # E52/P5
    lock_detail = _earliest_row_lock_detail(db, user, current_user, change)
    if lock_detail:
        raise HTTPException(status_code=400, detail=lock_detail)
    effective_from = change.effective_from

    def _apply():
        db.delete(change)
        db.flush()
        most_recent = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user.id,
            WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
            WorkingHoursChange.effective_from <= today_local(),
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
        if most_recent:
            _sync_user_from_change(user, most_recent)  # #431: derselbe Resync wie beim Anlegen

    impact = wh_change_service.run_change(
        db, user, admin_id=current_user.id, effective_from=effective_from, apply=_apply)
    earliest = impact.earliest_lossless_date
    error = wh_change_service.protection_error(
        impact, body, deleting=True, reset_offered=earliest is not None and earliest > effective_from)
    if error:
        db.rollback()
        raise HTTPException(status_code=400, detail=error)

    reason_type = body.retroactive_reason_type if (body is not None and impact.is_shortening) else None
    _log_reclamp(db, user=user, admin=current_user, impact=impact, effective_from=effective_from, deleted=True,
                 reason_type=reason_type, reason_text=body.retroactive_reason_text if body else None, reset_of=None)
    _log_wh_change_retarget(
        db, user=user, admin=current_user, tenant_id=current_user.tenant_id,
        effective_from=impact.window.start, period_end=impact.window.end, adjusted=impact.absences,
        prefix="Löschung der Arbeitszeit-Änderung", suffix="auf den davor gültigen Wert zurückgerechnet",
    )
    warning = calculation_service.stale_year_closing_warning(
        db, current_user.tenant_id, range(impact.window.start.year, impact.window.end.year + 1))
    db.commit()
    if impact.absences or impact.reclamp.changed or warning:
        return JSONResponse(status_code=200, content={
            "adjusted_absences": len(impact.absences),
            "adjusted_time_entries": len(impact.reclamp.changed),
            "skipped_time_entries": len(impact.reclamp.skipped),
            "warning": warning,
        })
    return None
```

- [ ] **Step 5: Bestandstests der Lösch-Seite auf das Schutzpaket umstellen (Spec 17.6, 19 Nr. 4)**

Ab diesem Task ist auch das Löschen einer Senkung — es hebt das Soll rückwirkend wieder an — eine Verkürzung nach 9.5 (b), und der Lösch-Endpunkt antwortet nach Spec 9.7 mit 200, sobald er etwas angepasst hat. Die Bestandstests der Lösch-Seite prüfen die Rückrechnung, nicht das Schutzpaket; sie senden den Grund immer mit (ohne Wirkung, wo nichts verkürzt). Das Schutzpaket selbst prüft `test_wh_change_delete_reclamp.py`. Tests werden umgeschrieben, nie gelöscht.

`backend/tests/test_wh_change_retroactive.py` — die Importzeile `from app.schemas.working_hours_change import WorkingHoursChangeCreate` wird

```python
from app.schemas.working_hours_change import WorkingHoursChangeCreate, WorkingHoursChangeDelete
```

(`from tests.wh_change_helpers import RETRO_REASON` steht seit Task 9 Step 7). Alle direkten Lösch-Aufrufe auf einen Wrapper umlenken (die Importzeile enthält `delete_working_hours_change,` ohne Klammer und bleibt unberührt):

```bash
sed -i 's/delete_working_hours_change(/_delete(/g' backend/tests/test_wh_change_retroactive.py
grep -c "_delete(" backend/tests/test_wh_change_retroactive.py
```

Expected: ≥ 14 Treffer.

Direkt nach der Funktion `_next_monday` einfügen:

```python
def _delete(**kwargs):
    """Spec 2026-10-08 (19.1 Nr. 1): ein Löschen, das das Soll rückwirkend wieder
    anhebt, ist eine Verkürzung (9.5 (b)) und braucht Grund und Haken. Diese Suite
    prüft die Rückrechnung, nicht das Schutzpaket — sie schickt den Grund immer
    mit (ohne Wirkung, wo nichts verkürzt). Das Schutzpaket selbst prüft
    test_wh_change_delete_reclamp.py."""
    return delete_working_hours_change(**kwargs, body=WorkingHoursChangeDelete(**RETRO_REASON))
```

`test_delete_of_closed_year_returns_200_with_warning` vollständig ersetzen (das Löschen einer **Senkung** in ein abgeschlossenes Jahr wäre jetzt eine gesperrte Verkürzung — der I3-Fall „Löschen meldet den Jahresabschluss" wird mit dem Löschen einer **Erhöhung** geprüft):

```python
    def test_delete_of_closed_year_returns_200_with_warning(self, db, default_tenant):
        """I3 (Abschluss-Review) + Spec 2026-10-08 (9.5 (b)): das Löschen rechnet
        dasselbe Fenster zurück wie das Anlegen und muss den Jahresabschluss genauso
        melden (200 + ``{"warning": …}``). Gelöscht wird eine Änderung, die das Soll
        im abgeschlossenen Jahr ERHÖHT hatte — das Löschen senkt es dort wieder,
        ist also keine Verkürzung. Das Löschen einer Senkung wäre dort gesperrt
        (400, test_wh_change_delete_reclamp.py)."""
        admin = _admin(db, "wh_delwarn_admin")
        last_year = today_local().year - 1
        emp = _make_user(db, "wh_delwarn_emp", weekly_hours=40.0, first_work_day=date(last_year, 1, 1))
        db.add(YearCarryover(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, year=last_year + 1,
            overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing",
        ))
        db.add(WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, effective_from=date(last_year, 1, 1),
            weekly_hours=Decimal("40.0"), use_daily_schedule=False, work_days_per_week=5,
        ))
        raised = WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, effective_from=date(last_year, 6, 1),
            weekly_hours=Decimal("45.0"), use_daily_schedule=False, work_days_per_week=5,
        )
        db.add(raised)
        db.commit()

        response = _delete(user_id=str(emp.id), change_id=str(raised.id), db=db, current_user=admin)

        assert response is not None, "mit Warnung: 200 + Body statt 204"
        assert response.status_code == 200
        body = json.loads(response.body)
        assert str(last_year) in body["warning"]
```

In `test_delete_without_closed_year_still_204` die Zeile `_absence(db, emp, mon, AbsenceType.VACATION, 8.0)` löschen — seit Spec 9.7 antwortet das Löschen mit 200, sobald es etwas angepasst hat; ohne angepasste Abwesenheit bleibt es 204. Den Docstring-losen Test um einen Kommentar ergänzen:

```python
        # Spec 9.7: 200 mit Zusammenfassung, sobald etwas angepasst oder gewarnt
        # wurde — hier gibt es weder Abwesenheiten noch Einträge im Fenster.
```

`backend/tests/test_wh_change_day_plan_delete.py` — Import `from tests.wh_change_helpers import RETRO_REASON` ergänzen und den Lösch-Aufruf ersetzen:

```python
    d = client.request(
        "DELETE",
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes/{change_id}",
        headers=admin_headers,
        # Spec 9.5 (b): das Löschen der Senkung hebt das Montags-Soll rückwirkend
        # wieder an — Verkürzung, also mit Grund und Haken.
        json=RETRO_REASON,
    )
```

`backend/tests/test_absence_raw_hours.py` — Importe: `WorkingHoursChangeDelete` neben `WorkingHoursChangeCreate` importieren, `from tests.wh_change_helpers import RETRO_REASON` ergänzen (falls nicht schon aus Task 9 vorhanden). Im Test `test_delete_writes_per_absence_rows_too` den Lösch-Aufruf ergänzen:

```python
        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin, body=WorkingHoursChangeDelete(**RETRO_REASON),
        )
```

und die Präfixe der Lösch-Seite (Spec 10.3: „Löschung der Arbeitszeit-Änderung", Step 4):

```bash
sed -i 's/%Löschung der Wochenstunden-Änderung%/%Löschung der Arbeitszeit-Änderung%/; s/Urlaub 8,0 h — Löschung der Wochenstunden-Änderung ab /Urlaub 8,0 h — Löschung der Arbeitszeit-Änderung ab /' backend/tests/test_absence_raw_hours.py
grep -n "Wochenstunden-Änderung" backend/tests/test_absence_raw_hours.py
```

Expected: die letzte Suche zeigt nur noch Docstrings/Kommentare, keine Zusicherung.

`backend/tests/test_wh_change_legacy_blocks.py` (PR1 Task 12) — Import `from tests.wh_change_helpers import RETRO_REASON` ergänzen; in `test_delete_resyncs_the_user_mirror` den Lösch-Aufruf ersetzen (das Löschen der 30-h-Zeile hebt das Soll ab 01.06. auf 40 h — Verkürzung):

```python
    resp = admin_client.request(
        "DELETE", f"/api/admin/users/{employee_user.id}/working-hours-changes/{later.id}", json=RETRO_REASON)
```

- [ ] **Step 6: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_delete_reclamp.py tests/test_reclamp.py tests/test_wh_change_preview_blocks.py tests/test_wh_change_retroactive.py tests/test_wh_change_day_plan_delete.py tests/test_absence_raw_hours.py tests/test_wh_change_legacy_blocks.py tests/test_fix2_whchange_daily_schedule.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Volle SQLite-Suite — keine neuen Fehlschläge**

Run (vorher `pgrep -af pytest`): `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py --ignore=tests/test_073_migration_pg.py --ignore=tests/test_net_hours_parity_pg.py --ignore=tests/test_reclamp_concurrency.py`
Expected: keine neuen Fehlschläge gegenüber den Ausgangszahlen. Scheitert ein weiterer Bestandstest mit 400 „Das Löschen verkürzt rückwirkend …" oder an 200 statt 204: prüft er die Rückrechnung, bekommt der Löschaufruf `body=WorkingHoursChangeDelete(**RETRO_REASON)` (HTTP: `json=RETRO_REASON`) bzw. die Erwartung 200 mit Zusammenfassung; prüft er ausdrücklich das Löschen ohne Grund, wird die Erwartung auf 400 umgestellt — die Datei kommt mit in den Commit. Einen Test nie löschen.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/admin_users.py backend/tests/test_wh_change_delete_reclamp.py backend/tests/test_wh_change_retroactive.py backend/tests/test_wh_change_day_plan_delete.py backend/tests/test_absence_raw_hours.py backend/tests/test_wh_change_legacy_blocks.py
git commit -F - <<'EOF'
feat(bloecke): Löschen mit delete-preview, Verkürzungsschutz und Rücksetzung auf den vorherigen Stand (9.7, P13)

Bestandstests der Lösch-Seite senden das Schutzpaket (17.6).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 12: Gesamtprüfung Backend nach Task 9–11 (Spec 17.6, 19 Nr. 4)

Die Umstellung der Bestandstests ist in die verursachenden Tasks gewandert (Anlege-Seite: Task 9 Step 7, Lösch-Seite: Task 11 Step 5) — jeder dieser Commits ist für sich grün. Dieser Task ist nur noch die zusammenfassende Prüfung vor den PG-Wettläufen und dem Frontend; er ändert keinen Code, solange nichts scheitert.

**Files:** keine (nur Prüfung; Funde werden im Bereich des verursachenden Tasks behoben und separat committet)

**Interfaces:**
- Consumes: Tasks 1–11
- Produces: Nachweis „Backend PR3 bis hier grün" — umgestellte Bestandssuiten, neue Suiten, volle SQLite-Suite

- [ ] **Step 1: Umgestellte und neue Suiten zusammen**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_wh_change_retroactive.py tests/test_fix2_whchange_daily_schedule.py tests/test_wh_change_day_plan_delete.py tests/test_absence_raw_hours.py tests/test_wh_change_legacy_blocks.py tests/test_reclamp.py tests/test_reclamp_core.py tests/test_reclamp_audit.py tests/test_wh_change_service.py tests/test_wh_change_delete_reclamp.py tests/test_wh_change_preview.py tests/test_wh_change_preview_blocks.py tests/test_retarget_f1.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 2: Volle SQLite-Suite**

Run (vorher `pgrep -af pytest`): `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py --ignore=tests/test_073_migration_pg.py --ignore=tests/test_net_hours_parity_pg.py --ignore=tests/test_reclamp_concurrency.py`
Expected: keine neuen Fehlschläge gegenüber den Ausgangszahlen vor Task 1.

- [ ] **Step 3: Rückstände ausschließen**

```bash
grep -rn 'prefix="\(Löschung der \)\?Wochenstunden-Änderung\|— \(Löschung der \)\?Wochenstunden-Änderung ab \|%Löschung der Wochenstunden-Änderung%' backend/app backend/tests
grep -rln "pytest.mark.skip\|pytest.skip(" backend/tests/test_reclamp*.py backend/tests/test_wh_change_delete_reclamp.py
```

Expected: die erste Suche ohne Treffer (kein Code-Pfad und keine Zusicherung mehr mit dem alten Präfix; Docstrings mit „Wochenstunden-Änderung" bleiben unberührt); die zweite zeigt nur `test_reclamp_concurrency.py` (modulweiter Skip ohne PostgreSQL). Scheitert ein Schritt, im Bereich des verursachenden Tasks (9 bzw. 11) beheben und mit eigenem Commit festhalten.

---

### Task 13: Nebenläufigkeit auf PostgreSQL — `test_reclamp_concurrency.py` (Spec 17.5, P5, E52)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#499: `clock_out` verlangt bei fehlender Pause eine Begründung — der Test schickt 45 Min Pause; `create_time_entry`-Signatur vor Step 1 mit `grep -n "^def create_time_entry" -A4 backend/app/routers/time_entries.py` prüfen.)

**Files:**
- Create: `backend/tests/test_reclamp_concurrency.py`
- Modify: `.github/workflows/cross-tenant-ci.yml`, `scripts/local-ci.sh`

**Interfaces:**
- Consumes: `admin_users.create_working_hours_change` (Task 9), `wh_change_service.run_change` (Task 8), `time_entries.clock_out`, `time_entries.create_time_entry`, `time_entries.get_clock_status` (Auto-Close über `_close_stale_entry`, PR1 Task 8), `admin_time_entries.admin_update_time_entry`, `admin_change_requests.review_change_request` (UPDATE-Zweig), `time_entries._now_local`/`_today_local`, `app.schemas.time_entry.today_local` (Bestand; Ankersperre aller fünf Pfade aus PR1 Task 7), Schemas `ClockOutRequest`, `TimeEntryCreate`, `TimeEntryUpdate`, `ChangeRequestReview`, Modell `ChangeRequest` (Bestand), Anerkennen-Endpunkt `POST /api/admin/time-entries/{entry_id}/credit-override` (PR2 Task 5 — Voraussetzung; fehlt er in der Routentabelle, scheitert der Test hart)
- Produces: PG-only-Datei mit modulweitem Skip ohne PostgreSQL-URL — je ein Wettlauf für `clock_out`, `create_time_entry`, `admin_update_time_entry`, die CR-Genehmigung (UPDATE), den Auto-Close in `GET /clock-status` und das Anerkennen (Spec 17.5); eingehängt in Actions und `local-ci.sh`

- [ ] **Step 1: Test schreiben**

`backend/tests/test_reclamp_concurrency.py`:

```python
"""Spec 2026-10-08, 17.5 (PostgreSQL-only): Nebenläufigkeit der Arbeitszeit-Änderung.

Ein Schreiber, der während einer laufenden Änderung auf die Ankersperre trifft
(P5), wartet und kappt danach mit den NEUEN Blöcken — unter READ COMMITTED läse
er sonst noch den alten Snapshot und bliebe von der Neukappung unerfasst.
Parametrisiert über alle Pfade aus 17.5: clock_out, create_time_entry,
admin_update_time_entry, CR-Genehmigung (UPDATE) und der Auto-Close in
GET /clock-status. Anerkennen parallel zu einer Neukappung desselben Eintrags
endet ohne Deadlock (Anker vor Zeile, 13.3). Muster: test_concurrency.py (echte
Endpunkt-Funktionen, SessionLocal + set_tenant_context)."""
from __future__ import annotations

import os
import threading
import time as time_module
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import text, create_engine

APP_DB_URL = os.environ.get("APP_DB_URL") or os.environ.get("DATABASE_URL")
ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not APP_DB_URL or not ADMIN_DB_URL or not ADMIN_DB_URL.startswith("postgresql"):
    pytest.skip("test_reclamp_concurrency.py braucht PostgreSQL (APP_DB_URL + ADMIN_DB_URL)",
                allow_module_level=True)

import app.schemas.time_entry as time_entry_schemas  # noqa: E402
from app.database import SessionLocal, set_tenant_context  # noqa: E402
from app.models import ChangeRequest, TimeEntry, User, WorkingHoursChange  # noqa: E402
from app.models.change_request import ChangeRequestStatus, ChangeRequestType  # noqa: E402
from app.routers import admin_change_requests, admin_time_entries, admin_users, time_entries  # noqa: E402
from app.schemas.change_request import ChangeRequestReview  # noqa: E402
from app.schemas.time_entry import ClockOutRequest, TimeEntryCreate, TimeEntryUpdate  # noqa: E402
from app.schemas.working_hours_change import WorkingHoursChangeCreate  # noqa: E402
from app.services import wh_change_service  # noqa: E402
from app.services.timezone_service import LOCAL_TZ  # noqa: E402

TENANT_ID = uuid.UUID("ccccccc3-0000-4000-8000-000000000001")
USER_ID = uuid.UUID("ccccccc3-0000-4000-8000-000000000100")
ADMIN_ID = uuid.UUID("ccccccc3-0000-4000-8000-000000000200")
DAY = date(2099, 6, 1)  # Montag
NEXT_DAY = DAY + timedelta(days=1)  # „heute" für den Auto-Close eines offenen Eintrags von gestern
EMPTY = {"blocks": [], "pause_minutes": 0}
OLD = [{"blocks": [{"start": "08:00", "end": "18:00"}], "pause_minutes": 0}] + [EMPTY] * 4
NEW = [{"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "16:00"}],
        "pause_minutes": 0}] + [EMPTY] * 4


@pytest.fixture(scope="module")
def admin_engine():
    eng = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    yield eng
    eng.dispose()


def _wipe(conn):
    # change_requests vor time_entries (FK time_entry_id), Protokoll zuerst (FK change_request_id).
    for table in ("time_entry_audit_logs", "change_requests", "time_entries", "working_hours_changes", "absences"):
        conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": str(TENANT_ID)})


@pytest.fixture(scope="module")
def seed(admin_engine):
    conn = admin_engine.connect()
    _wipe(conn)
    conn.execute(text("DELETE FROM security_events WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("INSERT INTO tenants (id, name, slug, is_active, mode) "
                      "VALUES (:id, 'Reclamp Wettlauf', 'reclamp-wettlauf', true, 'multi')"), {"id": str(TENANT_ID)})
    for uid, name, role in ((USER_ID, "reclamp_user", "EMPLOYEE"), (ADMIN_ID, "reclamp_admin", "ADMIN")):
        conn.execute(text("""
            INSERT INTO users (id, tenant_id, username, email, password_hash, first_name, last_name, role,
                               weekly_hours, vacation_days, work_days_per_week, is_active)
            VALUES (:id, :tid, :u, :e, 'not-real', 'R', 'Test', :role, 10, 30, 1, true)
        """), {"id": str(uid), "tid": str(TENANT_ID), "u": name, "e": f"{name}@test.local", "role": role})
    yield
    _wipe(conn)
    conn.execute(text("DELETE FROM security_events WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})
    conn.close()


@pytest.fixture
def fresh(seed, admin_engine):
    conn = admin_engine.connect()
    _wipe(conn)
    conn.close()
    session = SessionLocal()
    set_tenant_context(session, TENANT_ID)
    session.add(WorkingHoursChange(
        user_id=USER_ID, tenant_id=TENANT_ID, effective_from=date(2099, 1, 1), weekly_hours=10,
        use_daily_schedule=True, hours_monday=10, hours_tuesday=0, hours_wednesday=0, hours_thursday=0,
        hours_friday=0, work_days_per_week=1, blocks=OLD,
    ))
    session.commit()
    session.close()
    yield


def _with_session(fn):
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        return fn(session)
    finally:
        session.close()


def _change_thread(results: list):
    def run(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        try:
            admin_users.create_working_hours_change(
                user_id=str(USER_ID), change_data=WorkingHoursChangeCreate(effective_from=DAY, blocks=NEW),
                db=session, current_user=admin)
            results.append(("change", time_module.monotonic()))
        except Exception as exc:  # pragma: no cover — Fehler sichtbar machen
            session.rollback()
            results.append(("change-error", repr(exc)))
    _with_session(run)


def _race(monkeypatch, writer, *, today=DAY, now=time(18, 0)):
    """Thread A legt die Änderung an und hält die Ankersperre 0,8 s (verzögerter
    Rechenpfad); Thread B startet erst, wenn A die Sperre hat. ``today``/``now``
    gelten nur für Schreiber B (``time_entries`` und die Datumsprüfung der
    Eintrags-Schemas) — A rechnet mit dem echten „heute", für A ist die Änderung
    ab ``DAY`` also zukunftsdatiert und schließt keinen offenen Eintrag selbst."""
    has_lock = threading.Event()
    real_run = wh_change_service.run_change

    def slow_run(*args, **kwargs):
        has_lock.set()            # create_working_hours_change sperrt VOR run_change
        time_module.sleep(0.8)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(wh_change_service, "run_change", slow_run)
    monkeypatch.setattr(time_entries, "_today_local", lambda: today)
    monkeypatch.setattr(time_entries, "_now_local", lambda: datetime.combine(today, now, tzinfo=LOCAL_TZ))
    # TimeEntryCreate.validate_not_future bindet today_local beim Import — ohne
    # diesen Patch lehnt das Schema DAY (2099) als Zukunftsdatum ab.
    monkeypatch.setattr(time_entry_schemas, "today_local", lambda: today)
    results: list = []
    a = threading.Thread(target=_change_thread, args=(results,))

    def b_target():
        has_lock.wait(timeout=5)
        try:
            _with_session(writer)
            results.append(("writer", time_module.monotonic()))
        except Exception as exc:  # pragma: no cover
            results.append(("writer-error", repr(exc)))

    b = threading.Thread(target=b_target)
    a.start(); b.start(); a.join(timeout=30); b.join(timeout=30)
    return dict((r[0], r[1]) for r in results)


def _the_entry():
    return _with_session(lambda s: s.query(TimeEntry).filter(TimeEntry.user_id == USER_ID, TimeEntry.date == DAY).one())


def _add(obj):
    """Legt ``obj`` in einer eigenen Sitzung an und gibt die ID zurück."""
    return _with_session(lambda s: (s.add(obj), s.commit(), obj.id)[2])


def _closed_entry():
    """Geschlossener Montagseintrag 08:00–17:00 unter den ALTEN Blöcken (08–18,
    Hülle 07:45–18:15): ungekappt, nichts nicht angerechnet."""
    return _add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8),
                          end_time=time(17), break_minutes=45, clamp_grace_minutes=15))


def _assert_waited_and_clamped(done, raw_end=time(18, 0)):
    assert "change" in done and "writer" in done, done
    assert done["writer"] >= done["change"]
    e = _the_entry()
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes) == (time(16, 15), raw_end, 150)
    return e


def test_clock_out_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    _with_session(lambda s: (s.add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8),
                                             end_time=None, break_minutes=0, clamp_grace_minutes=15)), s.commit()))

    def writer(session):
        user = session.query(User).filter(User.id == USER_ID).first()
        time_entries.clock_out(body=ClockOutRequest(break_minutes=45), db=session, current_user=user)

    done = _race(monkeypatch, writer)
    assert "change" in done and "writer" in done, done
    assert done["writer"] >= done["change"]
    e = _the_entry()
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes) == (time(16, 15), time(18, 0), 150)


def test_create_time_entry_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    def writer(session):
        user = session.query(User).filter(User.id == USER_ID).first()
        time_entries.create_time_entry(
            entry_data=TimeEntryCreate(date=DAY, start_time=time(8), end_time=time(18), break_minutes=45),
            db=session, current_user=user)

    done = _race(monkeypatch, writer)
    assert "change" in done and "writer" in done, done
    e = _the_entry()
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes) == (time(16, 15), time(18, 0), 150)


def test_admin_update_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    """PUT /api/admin/time-entries/{id}: das neue Ende 18:00 wird mit den NEUEN
    Blöcken gekappt (Hülle 16:15, Lücke 12:15–14:45), nicht mit dem alten Snapshot."""
    entry_id = _closed_entry()

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        admin_time_entries.admin_update_time_entry(
            entry_id=str(entry_id), entry_data=TimeEntryUpdate(end_time=time(18), break_minutes=45),
            db=session, current_user=admin)

    _assert_waited_and_clamped(_race(monkeypatch, writer))


def test_change_request_approval_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    """POST /api/admin/change-requests/{id}/review, UPDATE-Zweig."""
    entry_id = _closed_entry()
    cr_id = _add(ChangeRequest(
        tenant_id=TENANT_ID, user_id=USER_ID, entry_kind="time_entry", request_type=ChangeRequestType.UPDATE,
        status=ChangeRequestStatus.PENDING, time_entry_id=entry_id, proposed_date=DAY,
        proposed_start_time=time(8), proposed_end_time=time(18), proposed_break_minutes=45,
        reason="Wettlauf-Test: tatsächliches Ende nachgetragen"))

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        admin_change_requests.review_change_request(
            request_id=str(cr_id), review=ChangeRequestReview(action="approve"), db=session, current_user=admin)

    _assert_waited_and_clamped(_race(monkeypatch, writer))


def test_clock_status_auto_close_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    """GET /api/time-entries/clock-status mit offenem Eintrag von gestern: der
    Auto-Close (PR1 Task 8, Ende 23:59 über clamp) nimmt die Ankersperre zuerst
    und kappt danach mit den neuen Blöcken."""
    _add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8),
                   end_time=None, break_minutes=0, clamp_grace_minutes=15))

    def writer(session):
        user = session.query(User).filter(User.id == USER_ID).first()
        time_entries.get_clock_status(db=session, current_user=user)

    e = _assert_waited_and_clamped(_race(monkeypatch, writer, today=NEXT_DAY, now=time(8, 0)),
                                   raw_end=time(23, 59))
    assert e.auto_closed is True


def test_credit_override_parallel_to_a_reclamp_does_not_deadlock(fresh, monkeypatch):
    from app.main import app
    endpoint = next((r.endpoint for r in app.routes
                     if getattr(r, "path", "") == "/api/admin/time-entries/{entry_id}/credit-override"), None)
    # PR2 ist Voraussetzung von PR3 (Global Constraints) — kein stilles Überspringen.
    assert endpoint is not None, "Anerkennen-Endpunkt (PR2 Task 5) fehlt in der Routentabelle"
    entry_id = _with_session(lambda s: (lambda e: (s.add(e), s.commit(), e.id)[2])(TimeEntry(
        tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8), end_time=time(18),
        break_minutes=45, clamp_grace_minutes=15)))

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        endpoint(entry_id=str(entry_id), db=session, current_user=admin)

    done = _race(monkeypatch, writer)
    assert "change" in done and "writer" in done, done   # kein 40P01 auf einer der beiden Seiten
    e = _the_entry()
    assert (e.credit_override, e.uncredited_minutes, e.start_time, e.end_time) == (True, 0, time(8), time(18))
```

- [ ] **Step 2: Ohne PostgreSQL wird übersprungen**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_reclamp_concurrency.py -q -p no:cacheprovider`
Expected: `1 skipped`.

- [ ] **Step 3: Gegen eine Wegwerf-PG18 laufen lassen**

Aus der Repo-Wurzel — derselbe Ablauf wie PR1 Task 14 Step 3 (eigenes Netz `pz073`, Migration bis `head`, App-Rolle mit Zufallspasswort), nur die Dateiliste:

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
  praxiszeit-backend python -c "from alembic.config import main; main(['upgrade','head'])" > /dev/null
docker exec -i pz073-pg psql -q -U praxiszeit -d praxiszeit < backend/init-db-user.sql
docker exec pz073-pg psql -q -U praxiszeit -d praxiszeit -c "ALTER ROLE praxiszeit_app PASSWORD '${APPPW}'"
docker run --rm --network pz073 -v "$PWD/backend":/app:ro -w /app --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X \
  -e APP_DB_USER=praxiszeit_app -e APP_DB_PASSWORD="$APPPW" -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e TZ=Europe/Berlin \
  -e DATABASE_URL="$APPURL" -e APP_DB_URL="$APPURL" -e DATABASE_URL_MIGRATIONS="$URL" -e ADMIN_DB_URL="$URL" \
  praxiszeit-backend python -m pytest tests/test_reclamp_concurrency.py tests/test_concurrency.py tests/test_tenant_rls.py -q -p no:cacheprovider
BASHEOF
```

Expected: alle Tests der drei Dateien `passed`, davon sechs in `test_reclamp_concurrency.py` (clock_out, create_time_entry, admin_update_time_entry, CR-Genehmigung, Auto-Close in clock-status, Anerkennen); **kein** `skipped`. Fehlt der Anerkennen-Endpunkt, ist PR2 nicht gemergt — Task stoppen, nicht überspringen. Scheitert ein Wettlauf mit „deadlock", ist die Ankersperre in einem Schreibpfad nicht die erste Sperre (PR1 Task 7) — den Test nicht lockern. Steht nach einem der drei neuen Wettläufe das alte Ende bzw. `uncredited_minutes == 0`, hat der Pfad den Snapshot vor der Ankersperre gelesen (P5) — den Pfad korrigieren, nicht die Erwartung.

- [ ] **Step 4: In Actions und `local-ci.sh` einhängen**

`.github/workflows/cross-tenant-ci.yml`, SQLite-Schritt — nach `--ignore=tests/test_net_hours_parity_pg.py \`:

```yaml
            --ignore=tests/test_reclamp_concurrency.py \
```

PostgreSQL-Schritt — die Dateiliste wird:

```yaml
          pytest tests/test_tenant_rls.py tests/test_purge_user_postgres.py \
            tests/test_concurrency.py tests/test_invalid_uuid_postgres.py \
            tests/test_073_migration_pg.py tests/test_net_hours_parity_pg.py \
            tests/test_reclamp_concurrency.py \
            -p no:asyncio -v
```

`scripts/local-ci.sh`, Schritt 1 — nach `--ignore=tests/test_net_hours_parity_pg.py \`:

```bash
       --ignore=tests/test_reclamp_concurrency.py \
```

Schritt 2 — `tests/test_reclamp_concurrency.py` an die Dateiliste anhängen und den Zählkommentar um 6 erhöhen (Stand nach PR1: 52 → 58, „+ 6 reclamp concurrency" in der Aufzählung; hat PR2 den Kommentar schon verändert, dessen Stand + 6).

Kontrolle: `bash -n scripts/local-ci.sh` ohne Ausgabe.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_reclamp_concurrency.py .github/workflows/cross-tenant-ci.yml scripts/local-ci.sh
git commit -F - <<'EOF'
test(bloecke): Wettlauf Arbeitszeit-Änderung gegen Schreibpfade und Anerkennen auf PostgreSQL

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 14: Berichtstext der Vertragsänderungen mit Blöcken (Spec 15.2, E71)

Spec 20 nennt 15.2 in keiner Phase ausdrücklich; erreichbar wird eine reine Blockänderung erst mit PR3 (vorher tragen alle Verlaufszeilen einer Person dasselbe Altfenster, E20). Deshalb liegt der Berichtstext hier. **Vorprüfung:** `grep -n "def blocks_changed" backend/app/services/calculation_service.py` — liefert PR2 die Funktion bereits, diesen Task nur gegen die Tests aus Step 1 abgleichen (die Wortlaute dort sind verbindlich) und Doppeltes nicht neu anlegen.

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#497/#498 haben `export_service.py`/`ods_export_service.py` umgebaut; geändert wird hier nur `_format_segment_change` — Anker per `grep -n "def _format_segment_change\|def format_weekly_hours_history" backend/app/services/export_service.py` prüfen. ODS nutzt `format_weekly_hours_history` und zieht automatisch mit.)

**Files:**
- Modify: `backend/app/services/calculation_service.py` (`ScheduleSegment`, `weekly_hours_segments`, neu `blocks_changed`)
- Modify: `backend/app/services/export_service.py` (`_format_segment_change`, Importe)
- Modify: `backend/app/schemas/reports.py` (`WeeklyHoursChangeInPeriod`)
- Modify: `frontend/src/utils/workBlocks.ts` (neu `formatBlocksText`), `frontend/src/utils/formatters.ts` (`WeeklyHoursChangeInPeriod`, `formatWeeklyHoursChanges`)
- Test (neu): `backend/tests/test_format_blocks_history.py`
- Test (erweitern): `frontend/src/utils/formatters.test.ts`, `frontend/src/utils/workBlocks.test.ts`

**Interfaces:**
- Consumes: `work_blocks_service.blocks_text`, `ParsedWeek`, `is_legacy_week`, `week_blocks_to_json` (Task 1/PR1); `formatWeekBlocks`, `isLegacyWeek`, `WEEKDAY_LABELS` (PR1 Task 15)
- Produces:
  - `ScheduleSegment.blocks: Optional[tuple] = None`, `ScheduleSegment.block_pauses: Optional[tuple] = None` (mit Vorgabewert: eine übersehene Konstruktion meint „keine Blöcke" und bleibt byte-identisch)
  - `calculation_service.blocks_changed(previous, segment) -> bool`
  - `WeeklyHoursChangeInPeriod.blocks: Optional[Any] = None`, `.blocks_changed: bool = False`
  - Frontend `formatBlocksText(week: WeekBlocks | null | undefined, opts?: { compact?: boolean }): string | null` (wortgleich zu `blocks_text`)
  - Wortlaute (15.2): ohne `blocks_changed` byte-identisch; neue Blöcke `ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche`; PDF-Kurzform `ab 01.09.2026: Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00 = 11,5 h/Woche`; Altfenster `<bisheriger Wortlaut> · Mo 07:30–16:30 (nur Kappung)`; Blöcke entfernt `<bisheriger Wortlaut> · ohne Arbeitszeit-Blöcke`

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_format_blocks_history.py`:

```python
"""Spec 15.2: Berichtstext der Vertragsänderungen — Blöcke nur, wenn sie sich
geändert haben; ohne Blockänderung byte-identisch zu 1.19.3."""
from datetime import date

from app.schemas.reports import WeeklyHoursChangeInPeriod
from app.services import calculation_service as cs
from app.services.export_service import format_weekly_hours_history
from tests.wh_change_helpers import add_row, with_pauses
from tests.work_blocks_fixtures import K_BLOCKS, block_week, legacy_week

YEAR = (date(2026, 1, 1), date(2026, 12, 31))
B = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "13:00")]), mon=30)


def _segments(db, user):
    return cs.weekly_hours_segments(db, user, *YEAR)


def test_new_blocks_long_and_compact(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), week=K_BLOCKS)
    add_row(db, test_user, date(2026, 9, 1), week=B)
    segs = _segments(db, test_user)
    assert format_weekly_hours_history(segs) == (
        "ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche")
    assert format_weekly_hours_history(segs, compact=True) == (
        "ab 01.09.2026: Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00 = 11,5 h/Woche")


def test_removing_blocks_appends_the_note(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), week=B)
    add_row(db, test_user, date(2026, 10, 1), day_hours=(6.5, 5, 0, 0, 0))
    assert format_weekly_hours_history(_segments(db, test_user)) == (
        "ab 01.10.2026: Mo 6,5 / Di 5,0 = 11,5 h/Woche · ohne Arbeitszeit-Blöcke")


def test_legacy_window_names_the_window(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=40, blocks=legacy_week(mon=("07:30", "16:30")))
    assert format_weekly_hours_history(_segments(db, test_user)) == (
        "ab 01.09.2026: 40,0 Std/Woche · Mo 07:30–16:30 (nur Kappung)")


def test_pause_change_only_is_a_block_change(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), week=B)
    add_row(db, test_user, date(2026, 9, 1), week=with_pauses(B, mon=60))
    assert format_weekly_hours_history(_segments(db, test_user)) == (
        "ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 60 Min) / Di 08:00–13:00 = 11,0 h/Woche")


def test_without_block_change_the_text_is_byte_identical(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
    assert format_weekly_hours_history(_segments(db, test_user)) == "ab 01.09.2026: 30,0 Std/Woche"


def test_same_legacy_window_in_every_row_creates_no_segment(db, test_user):
    """E20/E22: alle Verlaufszeilen tragen nach 073 dasselbe Altfenster."""
    legacy = legacy_week(mon=("07:30", "16:30"))
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, blocks=legacy)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=40, blocks=legacy)
    assert len(_segments(db, test_user)) == 1


def test_api_carries_blocks_and_the_flag(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), week=K_BLOCKS)
    add_row(db, test_user, date(2026, 9, 1), week=B)
    first, second = _segments(db, test_user)
    out = WeeklyHoursChangeInPeriod.from_segment(second, previous=first)
    assert (out.blocks, out.blocks_changed) == (B, True)
    assert WeeklyHoursChangeInPeriod.from_segment(first).blocks_changed is False
```

An `frontend/src/utils/workBlocks.test.ts` anhängen (Import `formatBlocksText` ergänzen):

```ts
describe('formatBlocksText (Spec 15.2, Zwilling von work_blocks_service.blocks_text)', () => {
  const week: WeekBlocks = [
    { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
    { blocks: [{ start: '08:00', end: '13:00' }], pause_minutes: 0 },
    EMPTY_NEW, EMPTY_NEW, EMPTY_NEW,
  ];

  it('lang und kurz wie das Backend', () => {
    expect(formatBlocksText(week)).toBe('Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00');
    expect(formatBlocksText(week, { compact: true })).toBe('Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00');
  });

  it('Altwerte ohne Pausenangabe, null ohne Blöcke', () => {
    expect(formatBlocksText(LEGACY_WEEK)).toBe('Mo 07:37–16:30 / Fr 07:30–23:59');
    expect(formatBlocksText(null)).toBeNull();
  });
});
```

An `frontend/src/utils/formatters.test.ts` anhängen (Import `formatWeeklyHoursChanges` ist dort vorhanden; sonst ergänzen):

```ts
describe('formatWeeklyHoursChanges mit Arbeitszeit-Blöcken (Spec 15.2, wortgleich zum Backend)', () => {
  const B = [
    { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
    { blocks: [{ start: '08:00', end: '13:00' }], pause_minutes: 0 },
    { blocks: [], pause_minutes: 0 }, { blocks: [], pause_minutes: 0 }, { blocks: [], pause_minutes: 0 },
  ];
  const legacyEmpty = { blocks: [], pause_minutes: null };

  it('neue Blöcke', () => {
    expect(formatWeeklyHoursChanges([{
      effective_from: '2026-09-01', weekly_hours: 11.5, use_daily_schedule: true,
      day_hours: [6.5, 5, null, null, null], work_days_per_week: 2, blocks: B, blocks_changed: true,
    }])).toBe('ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche');
  });

  it('Blöcke entfernt', () => {
    expect(formatWeeklyHoursChanges([{
      effective_from: '2026-10-01', weekly_hours: 11.5, use_daily_schedule: true,
      day_hours: [6.5, 5, null, null, null], work_days_per_week: 2, blocks: null, blocks_changed: true,
    }])).toBe('ab 01.10.2026: Mo 6,5 / Di 5,0 = 11,5 h/Woche · ohne Arbeitszeit-Blöcke');
  });

  it('Altfenster', () => {
    expect(formatWeeklyHoursChanges([{
      effective_from: '2026-09-01', weekly_hours: 40, use_daily_schedule: false, work_days_per_week: 5,
      blocks: [{ blocks: [{ start: '07:30', end: '16:30' }], pause_minutes: null }, legacyEmpty, legacyEmpty,
        legacyEmpty, legacyEmpty],
      blocks_changed: true,
    }])).toBe('ab 01.09.2026: 40,0 Std/Woche · Mo 07:30–16:30 (nur Kappung)');
  });

  it('ohne Blockänderung byte-identisch', () => {
    expect(formatWeeklyHoursChanges([{ effective_from: '2026-09-01', weekly_hours: 30, blocks: B }]))
      .toBe('ab 01.09.2026: 30,0 Std/Woche');
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_format_blocks_history.py -q -p no:cacheprovider`
Run (aus `frontend/`): `npx vitest run src/utils/formatters.test.ts src/utils/workBlocks.test.ts --pool=threads`
Expected: FAIL — Backend ohne Blocktext (bisheriger Wortlaut, `test_pause_change_only…` ein Segment zu wenig), Frontend `formatBlocksText is not a function`.

- [ ] **Step 3: Backend umsetzen**

`calculation_service.py` — `ScheduleSegment` nach `work_days_per_week: int`:

```python
    # Spec 15.2: Blöcke und Pausen des Segments (Schedule-Format). Mit
    # Vorgabewert: eine übersehene Konstruktion meint „keine Blöcke" und schreibt
    # den bisherigen Wortlaut byte-identisch.
    blocks: Optional[tuple] = None
    block_pauses: Optional[tuple] = None
```

In `weekly_hours_segments` den `ScheduleSegment(...)`-Aufruf ergänzen:

```python
            blocks=schedule.blocks,
            block_pauses=schedule.block_pauses if schedule.blocks is not None else None,
```

Nach `work_days_changed` einfügen:

```python
def blocks_changed(previous, segment) -> bool:
    """Spec 15.2: Ändert dieses Segment die Arbeitszeit-Blöcke (inkl. Pausen)
    gegenüber dem vorhergehenden? DIE eine Quelle für Datei-Export und API-Feld
    (Zwilling von :func:`work_days_changed`). ``previous is None`` → False."""
    if previous is None:
        return False

    def key(seg):
        blocks = getattr(seg, "blocks", None)
        return blocks, (getattr(seg, "block_pauses", None) if blocks is not None else None)

    return key(previous) != key(segment)
```

`export_service.py` — Import ergänzen:

```python
from app.services import calculation_service, practice_name_service, special_days_service, work_blocks_service
```

Die bestehende Funktion `_format_segment_change` in `_format_segment_change_base` umbenennen (Rumpf unverändert) und direkt danach einfügen:

```python
def _format_segment_change(segment, previous=None, compact: bool = False) -> str:
    """Spec 15.2: wie bisher (``_format_segment_change_base``) — Blöcke nur, wenn
    sie sich gegenüber ``previous`` geändert haben (``blocks_changed``):
    neue Blöcke ersetzen den Satz, ein Altfenster und das Entfernen von Blöcken
    werden angehängt. Frontend-Zwilling ``formatWeeklyHoursChanges`` (wortgleich)."""
    base = _format_segment_change_base(segment, previous, compact=compact)
    if not calculation_service.blocks_changed(previous, segment):
        return base
    if segment.blocks is None:
        return f"{base} · ohne Arbeitszeit-Blöcke"
    spans = work_blocks_service.blocks_text(segment.blocks, segment.block_pauses, compact=compact)
    if work_blocks_service.is_legacy_week(work_blocks_service.ParsedWeek(segment.blocks, segment.block_pauses)):
        return f"{base} · {spans} (nur Kappung)"
    total = _de_hours_compact if compact else _de_hours_exact
    return f"ab {segment.start.strftime('%d.%m.%Y')}: {spans} = {total(segment.weekly_hours)} h/Woche"
```

`schemas/reports.py` — in `WeeklyHoursChangeInPeriod` nach `work_days_changed: bool = False`:

```python
    # Spec 15.2: Blöcke des Segments (kanonische JSON-Woche, locker) und ob sie
    # sich gegenüber dem vorhergehenden Segment ändern — vom Server, aus
    # derselben Regel wie der Datei-Export (``calculation_service.blocks_changed``).
    blocks: Optional[Any] = None
    blocks_changed: bool = False
```

`from typing import List, Optional` → `from typing import Any, List, Optional`. In `from_segment` den lokalen Import und die Rückgabe ergänzen:

```python
        from app.services.calculation_service import blocks_changed, work_days_changed
        from app.services.work_blocks_service import week_blocks_to_json
```

```python
            work_days_changed=work_days_changed(previous, segment),
            blocks=week_blocks_to_json(getattr(segment, "blocks", None), getattr(segment, "block_pauses", None)),
            blocks_changed=blocks_changed(previous, segment),
```

- [ ] **Step 4: Frontend-Zwilling umsetzen**

`frontend/src/utils/workBlocks.ts` — anhängen:

```ts
/** Spec 15.2 — Zwilling von `work_blocks_service.blocks_text` (wortgleich):
 * lang „Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00",
 * kurz „Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00". `null` ohne Blöcke. */
export function formatBlocksText(
  week: WeekBlocks | null | undefined,
  { compact = false }: { compact?: boolean } = {},
): string | null {
  if (!Array.isArray(week)) return null;
  const parts = week.flatMap((day, index) => {
    const blocks = day?.blocks ?? [];
    if (blocks.length === 0 || index >= WEEKDAY_LABELS.length) return [];
    const spans = blocks.map((b) => `${b.start}–${b.end}`);
    const pause = day.pause_minutes;
    const text = compact
      ? spans.join('+') + (pause ? ` P${pause}` : '')
      : spans.join(' + ') + (pause ? ` (Pause ${pause} Min)` : '');
    return [`${WEEKDAY_LABELS[index]} ${text}`];
  });
  return parts.length > 0 ? parts.join(' / ') : null;
}
```

`frontend/src/utils/formatters.ts` — Importe ergänzen:

```ts
import type { WeekBlocks } from '../types/workBlocks';
import { formatBlocksText, isLegacyWeek } from './workBlocks';
```

im Interface `WeeklyHoursChangeInPeriod` nach `work_days_changed?: boolean;`:

```ts
  /** Spec 15.2: Blöcke des Segments und ob sie sich gegenüber dem vorhergehenden
   * ändern (vom Server, `calculation_service.blocks_changed`). */
  blocks?: WeekBlocks | null;
  blocks_changed?: boolean;
```

und den Rumpf von `formatWeeklyHoursChanges` ersetzen durch:

```ts
  if (!changes || changes.length === 0) return '';
  return changes
    .map((c) => {
      const [y, m, d] = c.effective_from.split('-');
      const prefix = `ab ${d}.${m}.${y}: `;
      let base: string | null = null;
      let suffix = '';
      if (c.use_daily_schedule) {
        const plan = formatDayPlan(c.day_hours);
        if (plan) base = `${prefix}${plan} = ${deHoursExact(c.weekly_hours)} h/Woche`;
      } else {
        suffix = workDaysSuffix(c);
      }
      if (base === null) base = `${prefix}${deHoursExact(c.weekly_hours)} Std/Woche${suffix}`;
      // Spec 15.2: Blöcke nur, wenn sie sich geändert haben — Zwilling von
      // export_service._format_segment_change.
      if (!c.blocks_changed) return base;
      const spans = formatBlocksText(c.blocks);
      if (!spans) return `${base} · ohne Arbeitszeit-Blöcke`;
      if (isLegacyWeek(c.blocks)) return `${base} · ${spans} (nur Kappung)`;
      return `${prefix}${spans} = ${deHoursExact(c.weekly_hours)} h/Woche`;
    })
    .join('; ');
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_format_blocks_history.py tests/test_415_working_hours_history_reports.py tests/test_497_498_export_day_rows.py -q -p no:cacheprovider`
Run (aus `frontend/`): `npx vitest run src/utils/formatters.test.ts src/utils/workBlocks.test.ts --pool=threads` und `npx tsc --noEmit`
Expected: PASS, `tsc` ohne Ausgabe. (Existiert `test_497_498_export_day_rows.py` auf dem Ausführungsstand nicht, entfällt die Datei aus dem Aufruf.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/calculation_service.py backend/app/services/export_service.py backend/app/schemas/reports.py backend/tests/test_format_blocks_history.py frontend/src/utils/workBlocks.ts frontend/src/utils/workBlocks.test.ts frontend/src/utils/formatters.ts frontend/src/utils/formatters.test.ts
git commit -F - <<'EOF'
feat(bloecke): Berichtstext der Vertragsänderungen nennt geänderte Arbeitszeit-Blöcke (15.2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 15: Dashboard-Hinweise an die Mitarbeitenden (Spec 14, P20, P12, E68)

**⚠ Nach Issue-Merge Zeilen/Signaturen abgleichen** (#493/#494/#500/#501 haben `pages/Dashboard.tsx` und `routers/dashboard.py` umgebaut — vor Step 4/5 `grep -n "def get_dashboard\|return MonthlyDashboard" backend/app/routers/dashboard.py` und `grep -n "interface DashboardData\|Missing Bookings Warning - Own" frontend/src/pages/Dashboard.tsx` prüfen; maßgeblich sind diese Anker.)

**Files:**
- Modify: `backend/app/services/reclamp_audit.py` (neu `notice_text`, `schedule_change_notices`)
- Modify: `backend/app/schemas/reports.py` (`ScheduleChangeNotice`, `MonthlyDashboard.schedule_change_notices`)
- Modify: `backend/app/routers/dashboard.py` (`get_dashboard`)
- Create: `frontend/src/components/ScheduleChangeNotices.tsx`, `frontend/src/components/ScheduleChangeNotices.test.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/Dashboard.test.tsx`
- Test (neu): `backend/tests/test_dashboard_schedule_notice.py`

**Interfaces:**
- Consumes: `parse_summary_note`, `SummaryNote`, `REASON_TYPES`, `contract_text` (Task 2); `calculation_service.get_schedule_for_date` (PR1)
- Produces:
  - `reclamp_audit.NOTICE_DAYS = 30`; `notice_text(db, user, parsed: SummaryNote, today: date) -> str`; `schedule_change_notices(db, user, *, now: Optional[datetime] = None) -> list[dict]` (Schlüssel `created_at`, `effective_from`, `kind` ∈ `change|reset|delete`, `text`; jüngste zuerst)
  - Schema `ScheduleChangeNotice`; `MonthlyDashboard.schedule_change_notices: List[ScheduleChangeNotice] = []`
  - Frontend `components/ScheduleChangeNotices.tsx` (Default-Export, Prop `notices?: ScheduleChangeNotice[] | null`), exportierter Typ `ScheduleChangeNotice`

- [ ] **Step 1: Failing tests schreiben (Backend)**

`backend/tests/test_dashboard_schedule_notice.py`:

```python
"""Spec 14/P20: Dashboard-Hinweis aus den Sammelzeilen der letzten 30 Tage —
bei jeder Änderung (auch „ab heute", zukunftsdatiert, Löschung, Rücksetzung),
nur eigene Zeilen, nie Präfix oder Freitext des Grundes (P12)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import TimeEntryAuditLog, User, UserRole
from app.services import reclamp_audit as ra
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.wh_change_helpers import ANNA_WEEK, add_row, admin_client, freeze
from tests.work_blocks_fixtures import block_week

NOW = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
SHORT = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], tue=[("08:00", "12:00")], thu=[("08:00", "12:00")])


def _summary_row(db, user, admin, note, *, created, entry_dates=False):
    row = TimeEntryAuditLog(
        time_entry_id=None, user_id=user.id, changed_by=admin.id, action="update", source="wh_reclamp",
        new_note=note, tenant_id=DEFAULT_TENANT_ID, created_at=created,
        old_date=date(2026, 9, 14) if entry_dates else None, new_date=date(2026, 9, 14) if entry_dates else None,
    )
    db.add(row)
    db.commit()
    return row


def _note(**kw):
    base = dict(effective_from=date(2026, 9, 1), deleted=False, count=0, delta_minutes=0, saldo_delta_minutes=0,
                skipped={}, grace=15, credit_reductions=0, reset_of=None, shortening=False, reason_type=None,
                reason_text_value=None, contract_before="a", contract_after="b")
    base.update(kw)
    return ra.summary_note(**base)


@pytest.fixture
def anna(db, test_user, monkeypatch):
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 9, 1), week=SHORT)
    return test_user


def test_past_change_with_counts_saldo_and_reason_label(db, anna, test_admin):
    _summary_row(db, anna, test_admin, _note(count=3, delta_minutes=-135, saldo_delta_minutes=-225,
                                             shortening=True, reason_type="erfassungsfehler",
                                             reason_text_value="Geheimer Freitext Reha"),
                 created=NOW - timedelta(days=2))
    [notice] = ra.schedule_change_notices(db, anna, now=NOW)
    assert notice["kind"] == "change"
    assert notice["text"] == (
        "Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / "
        "Do 08:00–12:00). 3 Einträge neu berechnet, angerechnete Zeit −2:15 h. Überstundenkonto im Zeitraum "
        "−3:45 h. Rückwirkende Verkürzung – Grund: Arbeitszeit war falsch hinterlegt (Fehlerkorrektur).")
    assert "[Erfassungsfehler korrigiert]" not in notice["text"] and "Reha" not in notice["text"]


def test_future_reset_and_delete_texts(db, anna, test_admin):
    add_row(db, anna, date(2026, 11, 2), weekly_hours=25)
    _summary_row(db, anna, test_admin, _note(effective_from=date(2026, 11, 2)), created=NOW - timedelta(days=3))
    _summary_row(db, anna, test_admin, _note(effective_from=date(2026, 10, 8), reset_of=date(2026, 9, 1)),
                 created=NOW - timedelta(days=2))
    _summary_row(db, anna, test_admin, _note(deleted=True, count=1, delta_minutes=15, saldo_delta_minutes=15),
                 created=NOW - timedelta(days=1))
    texts = [n["text"] for n in ra.schedule_change_notices(db, anna, now=NOW)]
    assert texts == [
        "Die Arbeitszeit-Änderung ab 01.09.2026 wurde zurückgenommen. 1 Eintrag neu berechnet, angerechnete Zeit "
        "+0:15 h. Überstundenkonto im Zeitraum +0:15 h.",
        "Die Arbeitszeit-Änderung ab 01.09.2026 wurde ab 08.10.2026 auf den vorherigen Stand zurückgesetzt "
        "(neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00).",
        "Ihre Arbeitszeit ändert sich ab 02.11.2026 (neu: 25,0 h/Woche (gleichmäßig, 5 Tage)).",
    ]


def test_future_reset_uses_the_future_tense(db, anna, test_admin):
    _summary_row(db, anna, test_admin, _note(effective_from=date(2026, 10, 12), reset_of=date(2026, 9, 1)),
                 created=NOW - timedelta(hours=1))
    [notice] = ra.schedule_change_notices(db, anna, now=NOW)
    assert notice["text"].startswith("Die Arbeitszeit-Änderung ab 01.09.2026 wird ab 12.10.2026 auf den vorherigen Stand")
    assert notice["kind"] == "reset"


def test_only_own_recent_parseable_summary_rows(db, anna, test_admin):
    other = User(username="kollegin", email="k@x.de", password_hash="h", first_name="K", last_name="T",
                 role=UserRole.EMPLOYEE, weekly_hours=40, work_days_per_week=5, vacation_days=30,
                 tenant_id=DEFAULT_TENANT_ID)
    db.add(other)
    db.commit()
    _summary_row(db, anna, test_admin, _note(), created=NOW - timedelta(days=31))                 # zu alt
    _summary_row(db, other, test_admin, _note(), created=NOW - timedelta(days=1))                 # fremd
    _summary_row(db, anna, test_admin, "angerechnet 2:15 h — Arbeitszeit-Änderung ab 01.09.2026",
                 created=NOW - timedelta(days=1), entry_dates=True)                               # Einzelzeile, Eintrag gelöscht
    _summary_row(db, anna, test_admin, "kein Format", created=NOW - timedelta(days=1))           # nicht lesbar
    _summary_row(db, anna, test_admin, _note(), created=NOW - timedelta(days=29))                 # zählt
    assert len(ra.schedule_change_notices(db, anna, now=NOW)) == 1


def test_dashboard_endpoint_shows_a_change_made_today(db, test_user, test_admin, monkeypatch):
    """P20: auch eine Änderung „ab heute" ohne Neukappung erzeugt einen Hinweis."""
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
    admin = admin_client(db, test_admin)
    assert admin.post(f"/api/admin/users/{test_user.id}/working-hours-changes",
                      json={"effective_from": "2026-10-08", "blocks": SHORT}).status_code == 201
    test_app.dependency_overrides.clear()
    employee = admin_client(db, test_user)   # get_current_user → die Person selbst
    body = employee.get("/api/dashboard/").json()
    test_app.dependency_overrides.clear()
    assert [n["text"] for n in body["schedule_change_notices"]] == [
        "Ihre Arbeitszeit wurde ab 08.10.2026 geändert (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / "
        "Do 08:00–12:00)."]
```

- [ ] **Step 2: Failing tests schreiben (Frontend)**

`frontend/src/components/ScheduleChangeNotices.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import ScheduleChangeNotices from './ScheduleChangeNotices';

const RESET = 'Die Arbeitszeit-Änderung ab 01.09.2026 wurde ab 09.10.2026 auf den vorherigen Stand zurückgesetzt (neu: 25,0 h/Woche (gleichmäßig, 5 Tage)).';
const CHANGE = 'Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: Mo 08:00–12:00). 3 Einträge neu berechnet, angerechnete Zeit −2:15 h. Überstundenkonto im Zeitraum −3:45 h. Rückwirkende Verkürzung – Grund: Arbeitszeit war falsch hinterlegt (Fehlerkorrektur).';

function renderNotices(notices: unknown) {
  return render(<MemoryRouter><ScheduleChangeNotices notices={notices as never} /></MemoryRouter>);
}

describe('ScheduleChangeNotices (Spec 14, P20)', () => {
  it('zeigt jeden Hinweis und den Link aufs Profil', () => {
    renderNotices([
      { created_at: '2026-10-09T08:00:00Z', effective_from: '2026-10-09', kind: 'reset', text: RESET },
      { created_at: '2026-10-08T08:00:00Z', effective_from: '2026-09-01', kind: 'change', text: CHANGE },
    ]);
    expect(screen.getByRole('heading', { name: 'Hinweis zu Ihrer Arbeitszeit' })).toBeInTheDocument();
    expect(screen.getByText(RESET)).toBeInTheDocument();
    expect(screen.getByText(CHANGE)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Arbeitszeit im Profil ansehen/ })).toHaveAttribute('href', '/profile');
  });

  it('rendert nichts ohne Hinweise', () => {
    const { container } = renderNotices([]);
    expect(container).toBeEmptyDOMElement();
    expect(renderNotices(undefined).container).toBeEmptyDOMElement();
  });
});
```

An `frontend/src/pages/Dashboard.test.tsx` anhängen:

```tsx
describe('Spec 14: Dashboard-Hinweise zur Arbeitszeit', () => {
  it('zeigt die Hinweise aus GET /dashboard', async () => {
    mockDashboardEndpoints();
    const base = getMock.getMockImplementation()!;
    getMock.mockImplementation((url: string) => {
      if (url === '/dashboard') {
        return Promise.resolve({ data: {
          year: 2026, month: 10, target_hours: 0, actual_hours: 0, balance: 0,
          schedule_change_notices: [{
            created_at: '2026-10-08T08:00:00Z', effective_from: '2026-11-02', kind: 'change',
            text: 'Ihre Arbeitszeit ändert sich ab 02.11.2026 (neu: 25,0 h/Woche (gleichmäßig, 5 Tage)).',
          }],
        } });
      }
      return base(url);
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(await screen.findByText('Ihre Arbeitszeit ändert sich ab 02.11.2026 (neu: 25,0 h/Woche (gleichmäßig, 5 Tage)).'))
      .toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Tests laufen lassen — müssen scheitern**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_dashboard_schedule_notice.py -q -p no:cacheprovider`
Run (aus `frontend/`): `npx vitest run src/components/ScheduleChangeNotices.test.tsx src/pages/Dashboard.test.tsx --pool=threads`
Expected: FAIL — `AttributeError: … has no attribute 'schedule_change_notices'`; Frontend „Failed to resolve import ./ScheduleChangeNotices".

- [ ] **Step 4: Backend umsetzen**

`reclamp_audit.py` — Importe ergänzen:

```python
from datetime import date, datetime, timedelta, timezone
from typing import List, NamedTuple, Optional

from app.services import calculation_service, timezone_service, work_blocks_service
```

am Dateiende anhängen:

```python
NOTICE_DAYS = 30


def _signed_hm(minutes: int) -> str:
    sign = "−" if minutes < 0 else "+"
    m = abs(int(minutes))
    return f"{sign}{m // 60}:{m % 60:02d}"


def notice_text(db, user, parsed: SummaryNote, today: date) -> str:
    """Spec 14 — Text je Sammelzeile. „neu: …" ist der Kurztext des HEUTE für
    ``effective_from`` aufgelösten Snapshots (``get_schedule_for_date``), nie
    ``users.work_blocks``; der Grund erscheint nur als Beschriftung des
    Grundtyps (P12, 19.1 Nr. 7)."""
    eff = parsed.effective_from.strftime("%d.%m.%Y")
    if parsed.deleted:
        text = f"Die Arbeitszeit-Änderung ab {eff} wurde zurückgenommen."
    else:
        neu = contract_text(calculation_service.get_schedule_for_date(db, user, parsed.effective_from), compact=False)
        if parsed.reset_of is not None:
            verb = "wurde" if parsed.effective_from <= today else "wird"
            text = (f"Die Arbeitszeit-Änderung ab {parsed.reset_of:%d.%m.%Y} {verb} ab {eff} "
                    f"auf den vorherigen Stand zurückgesetzt (neu: {neu}).")
        elif parsed.effective_from <= today:
            text = f"Ihre Arbeitszeit wurde ab {eff} geändert (neu: {neu})."
        else:
            text = f"Ihre Arbeitszeit ändert sich ab {eff} (neu: {neu})."
    if parsed.count > 0:
        noun = "Eintrag" if parsed.count == 1 else "Einträge"
        text += f" {parsed.count} {noun} neu berechnet, angerechnete Zeit {_signed_hm(parsed.delta_minutes)} h."
    if parsed.saldo_delta_minutes != 0:
        text += f" Überstundenkonto im Zeitraum {_signed_hm(parsed.saldo_delta_minutes)} h."
    if parsed.shortening:
        label = REASON_TYPES[parsed.reason_type].label if parsed.reason_type else None
        text += f" Rückwirkende Verkürzung – Grund: {label}." if label else " Rückwirkende Verkürzung."
    return text


def schedule_change_notices(db, user, *, now: Optional[datetime] = None) -> List[dict]:
    """Spec 14/P20 — alle Sammelzeilen der Person der letzten 30 Tage, jüngste
    zuerst, nur die, die ``parse_summary_note`` liest (eine Einzelzeile, deren
    Eintrag gelöscht wurde, verdrängt so keinen Hinweis). Keine
    Bestätigungstabelle. Die 30-Tage-Grenze wird in Python geprüft: SQLite
    liefert ``created_at`` ohne Zeitzone."""
    from app.models import TimeEntryAuditLog

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=NOTICE_DAYS)
    rows = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == user.id,
        TimeEntryAuditLog.tenant_id == user.tenant_id,  # F-026
        TimeEntryAuditLog.source == AUDIT_SOURCE,
        TimeEntryAuditLog.time_entry_id.is_(None),
        TimeEntryAuditLog.old_date.is_(None),
        TimeEntryAuditLog.new_date.is_(None),
    ).order_by(TimeEntryAuditLog.created_at.desc()).all()
    today = timezone_service.today_local()
    notices = []
    for row in rows:
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        if created < since:
            continue
        parsed = parse_summary_note(row.new_note)
        if parsed is None:
            continue
        kind = "delete" if parsed.deleted else ("reset" if parsed.reset_of is not None else "change")
        notices.append({"created_at": created, "effective_from": parsed.effective_from, "kind": kind,
                        "text": notice_text(db, user, parsed, today)})
    return notices
```

`schemas/reports.py` — `from datetime import date` → `from datetime import date, datetime`, `from typing import List, Optional` → `from typing import Any, List, Literal, Optional`; vor `class MonthlyDashboard` einfügen und `MonthlyDashboard` ergänzen:

```python
class ScheduleChangeNotice(BaseModel):
    """Spec 14/P20: ein Hinweis zu einer Arbeitszeit-Änderung (letzte 30 Tage)."""
    created_at: datetime
    effective_from: date
    kind: Literal["change", "reset", "delete"]
    text: str
```

```python
    # Spec 14: Hinweise zu Arbeitszeit-Änderungen der letzten 30 Tage, jüngste zuerst.
    schedule_change_notices: List[ScheduleChangeNotice] = []
```

`routers/dashboard.py` — `from app.services import calculation_service, milog_service, reclamp_audit` und in `get_dashboard` das `MonthlyDashboard(...)` ergänzen:

```python
        balance=balance,
        # Spec 14/P20: nur eigene Sammelzeilen (current_user), auch unter Impersonation.
        schedule_change_notices=reclamp_audit.schedule_change_notices(db, current_user),
```

- [ ] **Step 5: Frontend umsetzen**

`frontend/src/components/ScheduleChangeNotices.tsx`:

```tsx
import { Link } from 'react-router-dom';
import { Info } from 'lucide-react';

/** Spec 14/P20: ein Hinweis aus GET /dashboard (Text kommt fertig vom Server —
 * EINE Quelle für Wortlaut, Beschriftung des Grundtyps und „neu: …"). */
export interface ScheduleChangeNotice {
  created_at: string;
  effective_from: string;
  kind: 'change' | 'reset' | 'delete';
  text: string;
}

export default function ScheduleChangeNotices({ notices }: { notices?: ScheduleChangeNotice[] | null }) {
  if (!notices || notices.length === 0) return null;
  return (
    <section aria-labelledby="schedule-notices-title" className="bg-blue-50 border border-blue-200 rounded-2xl p-4 mb-6">
      <div className="flex items-start gap-3">
        <Info className="text-blue-600 shrink-0 mt-0.5" size={20} aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <h3 id="schedule-notices-title" className="text-sm font-semibold text-blue-900">
            Hinweis zu Ihrer Arbeitszeit
          </h3>
          <ul className="mt-1 space-y-1">
            {notices.map((n) => (
              <li key={`${n.created_at}-${n.kind}-${n.effective_from}`} className="text-sm text-blue-900">
                {n.text}
              </li>
            ))}
          </ul>
          <Link to="/profile" className="inline-block mt-2 text-sm font-medium text-blue-800 underline hover:no-underline">
            Arbeitszeit im Profil ansehen →
          </Link>
        </div>
      </div>
    </section>
  );
}
```

`frontend/src/pages/Dashboard.tsx` — Importe:

```tsx
import ScheduleChangeNotices, { type ScheduleChangeNotice } from '../components/ScheduleChangeNotices';
```

im Interface `DashboardData` nach `balance: number;`:

```tsx
  schedule_change_notices?: ScheduleChangeNotice[];  // Spec 14/P20
```

und direkt vor dem Kommentar `{/* Missing Bookings Warning - Own */}`:

```tsx
      {/* Spec 14/P20: Hinweise zu Arbeitszeit-Änderungen der letzten 30 Tage */}
      <ScheduleChangeNotices notices={dashboardData?.schedule_change_notices} />
```

- [ ] **Step 6: Tests laufen lassen — müssen grün sein**

Run: `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/test_dashboard_schedule_notice.py tests/test_reclamp_audit.py -q -p no:cacheprovider`
Run (aus `frontend/`): `npx vitest run src/components/ScheduleChangeNotices.test.tsx src/pages/Dashboard.test.tsx --pool=threads` und `npx tsc --noEmit`
Expected: PASS, `tsc` ohne Ausgabe.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/reclamp_audit.py backend/app/schemas/reports.py backend/app/routers/dashboard.py backend/tests/test_dashboard_schedule_notice.py frontend/src/components/ScheduleChangeNotices.tsx frontend/src/components/ScheduleChangeNotices.test.tsx frontend/src/pages/Dashboard.tsx frontend/src/pages/Dashboard.test.tsx
git commit -F - <<'EOF'
feat(bloecke): Dashboard-Hinweis bei jeder Arbeitszeit-Änderung, abgeleitet aus der Sammelzeile (14, P20)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 16: Frontend-Rechenhelfer, Antworttypen und feste Dialogtexte (Spec 3.4, 4.1, 9.5, 11.3, 12.1, P26)

**Files:**
- Modify: `frontend/src/utils/workBlocks.ts` (anhängen)
- Create: `frontend/src/pages/admin/users/workingHoursTypes.ts`, `frontend/src/pages/admin/users/workingHoursTexts.ts`, `frontend/src/pages/admin/users/workingHoursTexts.test.ts`
- Test (erweitern): `frontend/src/utils/workBlocks.test.ts`

**Interfaces:**
- Consumes: `WEEKDAY_LABELS`, `TimeBlock`/`DayBlocks`/`WeekBlocks` (PR1 Task 15); `deHoursExact` (Bestand)
- Produces:
  - `utils/workBlocks.ts`: `emptyWeek(): WeekBlocks`, `parseHhmm(value): number | null` (streng; PR2s `hhmmToMinutes` bleibt unverändert), `minutesToHm(minutes: number): string`, `interface DayTotals { grossMinutes; pauseMinutes; netMinutes }`, `sumBlocks(day: DayBlocks): DayTotals`, `minutesToTargetHours(net: number): number` (HALF_EVEN exakt), `deriveTargets(week: WeekBlocks): { hours: number[]; weeklyHours: number; workDays: number }`, `validateWeekBlocks(week): string | null` (Texte wortgleich zu Task 1)
  - `workingHoursTypes.ts`: `WorkingHoursChange`, `ShorteningReason`, `TimeEntryChange`, `ArbzgFindings`, `WorkingHoursChangePreview` (alle neuen 11.3-Felder optional, damit Bestandsfixtures typprüfen)
  - `workingHoursTexts.ts`: `LEGAL_HINT`, `JARBSCHG_HINT`, `LEGACY_BOX_TITLE`, `BLOCKS_WITHOUT_EFFECT`, `modeSwitchHint(date: string)`, `REASON_HELP`, `WAGE_SENTENCE`, `OTHER_WARNING`, `OTHER_CONFIRM`, `type RetroReasonKey`, `REASON_OPTIONS: {value; label; confirm}[]`, `type ShorteningOption = 'lossless' | 'retro'`, `interface ReasonState { type: RetroReasonKey | ''; text: string; wageConfirmed: boolean; otherConfirmed: boolean }`, `EMPTY_REASON`, `reasonComplete(r): boolean`, `reasonPayload(r): Record<string, unknown>`, `SKIP_LABELS`, `closedYearMessage(years: number[]): string | null`, `formatDate(iso)`, `shortDate(iso)`, `monthLabel(yyyyMm)`, `hm(hours)`, `signedHm(hours)`, `signedDays(value)`, `savedMessage(created, verb: 'Gespeichert' | 'Gelöscht' = 'Gespeichert')`

- [ ] **Step 1: Failing tests schreiben**

An `frontend/src/utils/workBlocks.test.ts` anhängen (Importe `deriveTargets, emptyWeek, minutesToHm, sumBlocks, validateWeekBlocks` ergänzen):

```ts
const day = (blocks: [string, string][], pause: number | null = 0) => ({
  blocks: blocks.map(([start, end]) => ({ start, end })), pause_minutes: pause,
});
const E = { blocks: [], pause_minutes: 0 };
const W = (mon: ReturnType<typeof day>, tue: ReturnType<typeof day> | typeof E = E): WeekBlocks => [mon, tue, E, E, E];

describe('deriveTargets (Spec 4.1, wortgleiche Fälle zu test_derive_targets.py)', () => {
  it.each([
    [[['08:00', '12:00'], ['15:00', '18:00']], 30, 6.5],
    [[['08:00', '12:05']], 0, 4.08],
    [[['07:30', '12:00'], ['13:00', '16:25']], 0, 7.92],
  ] as [[string, string][], number, number][])('%j, Pause %i → %f h', (blocks, pause, expected) => {
    const d = deriveTargets(W(day(blocks, pause)));
    expect(d.hours).toEqual([expected, 0, 0, 0, 0]);
    expect([d.weeklyHours, d.workDays]).toEqual([expected, 1]);
  });

  it('drei Blöcke zu 55 Minuten', () => {
    expect(deriveTargets(W(day([['08:00', '08:55'], ['09:00', '09:55'], ['10:00', '10:55']]))).hours[0]).toBe(2.75);
  });
});

describe('validateWeekBlocks (Spec 3.4, wortgleiche Texte zu test_work_blocks_validation.py)', () => {
  const ADJ = 'Mo: Block 2 muss nach dem Ende von Block 1 beginnen; aneinandergrenzende Blöcke bitte als einen Block erfassen.';
  it.each([
    [W(day([['06:00', '07:00'], ['08:00', '09:00'], ['10:00', '11:00'], ['12:00', '13:00']])), 'Mo: höchstens drei Blöcke je Tag.'],
    [W(day([['8:00', '12:00']])), 'Mo, Block 1: Uhrzeit im Format HH:MM angeben.'],
    [W(day([['', '12:00']])), 'Mo, Block 1: Uhrzeit im Format HH:MM angeben.'],
    [W(day([['08:07', '12:00']])), 'Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).'],
    [W(E, day([['08:00', '12:00'], ['13:00', '12:30']])), 'Di, Block 2: Beginn muss vor dem Ende liegen.'],
    [W(day([['08:00', '12:00'], ['12:00', '13:00']])), ADJ],
    [W(day([['13:00', '14:00'], ['08:00', '12:00']])), ADJ],
    [W(day([['08:00', '12:00']], 240)), 'Mo: Pause muss kürzer sein als die Gesamtzeit der Blöcke.'],
    [W(day([['08:00', '12:00']], null)), 'Mo: Pause angeben (0, wenn keine).'],
    [W(day([['08:00', '12:00']], 7)), 'Mo: Pause in Minuten im 5-Minuten-Raster angeben.'],
    [[day([['08:00', '12:00']]), E, { blocks: [], pause_minutes: 15 }, E, E], 'Mi: Pause nur an Tagen mit Blöcken.'],
    [[E, E, E, E, E], 'Mindestens ein Wochentag braucht einen Block.'],
    [Array(5).fill(day([['00:00', '12:05']])), 'Die Wochensumme darf 60 Stunden nicht überschreiten.'],
    [[E, E, E, E], 'Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet.'],
  ] as [WeekBlocks, string][])('%#: %s', (week, message) => {
    expect(validateWeekBlocks(week)).toBe(message);
  });

  it('Grenzwerte sind gültig', () => {
    expect(validateWeekBlocks(W(day([['06:00', '07:00'], ['08:00', '09:00'], ['10:00', '11:00']])))).toBeNull();
    expect(validateWeekBlocks(W(day([['08:05', '12:00']], 235)))).toBeNull();
    expect(validateWeekBlocks(Array(5).fill(day([['00:00', '12:00']])))).toBeNull();
    expect(validateWeekBlocks(W(day([['08:00', '23:55']])))).toBeNull();
  });
});

describe('sumBlocks / minutesToHm / emptyWeek', () => {
  it('7:55 h bleibt Minuten-genau (Review Focus 5)', () => {
    const totals = sumBlocks(day([['07:30', '12:00'], ['13:00', '16:25']]));
    expect([totals.grossMinutes, totals.pauseMinutes, totals.netMinutes]).toEqual([475, 0, 475]);
    expect(minutesToHm(475)).toBe('7:55');
  });

  it('unvollständige Blöcke zählen nicht, eine leere Pause zählt 0', () => {
    expect(sumBlocks(day([['08:00', '']], null))).toEqual({ grossMinutes: 0, pauseMinutes: 0, netMinutes: 0 });
  });

  it('leere Woche hat fünf Tage ohne Blöcke mit Pause 0', () => {
    expect(emptyWeek()).toEqual([E, E, E, E, E]);
  });
});
```

`frontend/src/pages/admin/users/workingHoursTexts.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import {
  EMPTY_REASON, REASON_OPTIONS, closedYearMessage, hm, reasonComplete, reasonPayload, savedMessage, signedDays,
  signedHm,
} from './workingHoursTexts';

describe('workingHoursTexts', () => {
  it('Grundtypen: neue Beschriftungen, unveränderte Schlüssel (19.1 Nr. 7)', () => {
    expect(REASON_OPTIONS.map((o) => [o.value, o.label])).toEqual([
      ['erfassungsfehler', 'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)'],
      ['einvernehmlich', 'Mit der beschäftigten Person vereinbart'],
      ['sonstiges', 'Sonstiges'],
    ]);
    for (const o of REASON_OPTIONS) {
      expect(o.confirm).toMatch(/Auf den Mindestlohn für geleistete Stunden kann nicht verzichtet werden \(§ 3 MiLoG\)\.$/);
    }
  });

  it('Pflichtangaben je Grundtyp (P15, P26)', () => {
    const ok = { type: 'erfassungsfehler' as const, text: 'zehn Zeichen', wageConfirmed: true, otherConfirmed: false };
    expect(reasonComplete(ok)).toBe(true);
    expect(reasonComplete({ ...ok, text: 'neun Zeic' })).toBe(false);
    expect(reasonComplete({ ...ok, wageConfirmed: false })).toBe(false);
    expect(reasonComplete({ ...ok, type: 'sonstiges' })).toBe(false);
    expect(reasonComplete({ ...ok, type: 'sonstiges', otherConfirmed: true })).toBe(true);
    expect(reasonComplete(EMPTY_REASON)).toBe(false);
    expect(reasonPayload({ ...ok, text: '  zehn Zeichen  ' })).toEqual({
      retroactive_reason_type: 'erfassungsfehler', retroactive_reason_text: 'zehn Zeichen',
      wage_risk_confirmed: true, other_reason_risk_confirmed: false,
    });
  });

  it('Stundenformate', () => {
    expect([hm(2.25), signedHm(-3.75), signedHm(1.75), signedHm(0)]).toEqual(['2:15', '−3:45', '+1:45', '0:00']);
    expect([signedDays(1), signedDays(-1.5), signedDays(0)]).toEqual(['+1,0', '−1,5', '0,0']);
  });

  it('gesperrtes abgeschlossenes Jahr nennt das größte Jahr (11.4)', () => {
    expect(closedYearMessage([2024, 2025])).toBe(
      'Rückwirkende Verkürzung in das abgeschlossene Jahr 2025 ist gesperrt. Bitte die Änderung frühestens ab 01.01.2026 wirksam werden lassen.',
    );
    expect(closedYearMessage([])).toBeNull();
  });

  it('Toast nach dem Speichern (12.1)', () => {
    expect(savedMessage({ adjusted_time_entries: 3, skipped_time_entries: 1, adjusted_absences: 1 })).toBe(
      'Gespeichert. 3 Zeiteinträge neu berechnet, 1 übersprungen, 1 Abwesenheit angepasst.',
    );
    expect(savedMessage({ adjusted_absences: 3 })).toBe('Gespeichert. 3 Abwesenheiten angepasst.');
    expect(savedMessage({})).toBe('Gespeichert.');
    expect(savedMessage({ adjusted_time_entries: 1 }, 'Gelöscht')).toBe('Gelöscht. 1 Zeiteintrag neu berechnet.');
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/utils/workBlocks.test.ts src/pages/admin/users/workingHoursTexts.test.ts --pool=threads`
Expected: FAIL — „deriveTargets is not a function", „Failed to resolve import ./workingHoursTexts".

- [ ] **Step 3: `utils/workBlocks.ts` ergänzen**

Den Typ-Import (nach PR2: `import type { TimeBlock, WeekBlocks } from '../types/workBlocks';`) auf `import type { DayBlocks, TimeBlock, WeekBlocks } from '../types/workBlocks';` erweitern — PR2s lockeres `hhmmToMinutes` bleibt unverändert, der strenge Parser heißt deshalb `parseHhmm` — und anhängen:

```ts
const WEEK_LIMIT_MINUTES = 60 * 60;

/** Fünf Tage ohne Blöcke, Pause 0 — Ausgangszustand des Editors. */
export function emptyWeek(): WeekBlocks {
  return WEEKDAY_LABELS.map(() => ({ blocks: [], pause_minutes: 0 }));
}

/** "HH:MM" → Minuten seit Mitternacht, `null` bei jedem anderen Format. */
export function parseHhmm(value: string | null | undefined): number | null {
  if (typeof value !== 'string' || !/^\d{2}:\d{2}$/.test(value)) return null;
  const hours = Number(value.slice(0, 2));
  const minutes = Number(value.slice(3));
  return hours > 23 || minutes > 59 ? null : hours * 60 + minutes;
}

/** Minuten → "H:MM" (Anzeige des Editors, Review Focus 5: Minuten-genau). */
export function minutesToHm(minutes: number): string {
  const abs = Math.abs(Math.round(minutes));
  return `${minutes < 0 ? '−' : ''}${Math.floor(abs / 60)}:${String(abs % 60).padStart(2, '0')}`;
}

export interface DayTotals {
  grossMinutes: number;
  pauseMinutes: number;
  netMinutes: number;
}

/** Live-Summen eines Tages; unvollständige Blöcke zählen nicht, eine leere Pause 0. */
export function sumBlocks(day: DayBlocks): DayTotals {
  const gross = (day?.blocks ?? []).reduce((sum, b) => {
    const s = parseHhmm(b.start);
    const e = parseHhmm(b.end);
    return s !== null && e !== null && e > s ? sum + (e - s) : sum;
  }, 0);
  const pause = (day?.blocks ?? []).length && typeof day.pause_minutes === 'number' ? day.pause_minutes : 0;
  return { grossMinutes: gross, pauseMinutes: pause, netMinutes: Math.max(0, gross - pause) };
}

/** Spec 4.1: Netto-Minuten → Tagessoll in Stunden, 0,01 HALF_EVEN — exakt ohne
 * Fließkomma: Hundertstel = 5n/3, der Rest 5n mod 3 ist nie genau 1,5. */
export function minutesToTargetHours(net: number): number {
  const five = 5 * net;
  return (Math.floor(five / 3) + (five % 3 === 2 ? 1 : 0)) / 100;
}

/** Zwilling von `work_blocks_service.derive_targets` (nur Anzeige/Vergleich). */
export function deriveTargets(week: WeekBlocks): { hours: number[]; weeklyHours: number; workDays: number } {
  const hours = WEEKDAY_LABELS.map((_, i) => {
    const d = week[i];
    return d && d.blocks.length ? minutesToTargetHours(sumBlocks(d).netMinutes) : 0;
  });
  return {
    hours,
    weeklyHours: Math.round(hours.reduce((a, b) => a + b, 0) * 100) / 100,
    workDays: week.filter((d) => d.blocks.length > 0).length,
  };
}

/** Zwilling von `schemas/validators.validate_week_blocks` — wortgleiche Texte
 * (Spec 3.4), Text der ERSTEN verletzten Regel oder `null`. */
export function validateWeekBlocks(week: WeekBlocks | null | undefined): string | null {
  if (!Array.isArray(week) || week.length !== 5) return 'Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet.';
  let totalNet = 0;
  for (let i = 0; i < 5; i++) {
    const label = WEEKDAY_LABELS[i];
    const blocks = week[i]?.blocks ?? [];
    if (blocks.length > 3) return `${label}: höchstens drei Blöcke je Tag.`;
    const spans: [number, number][] = [];
    for (let n = 0; n < blocks.length; n++) {
      const s = parseHhmm(blocks[n].start);
      const e = parseHhmm(blocks[n].end);
      if (s === null || e === null) return `${label}, Block ${n + 1}: Uhrzeit im Format HH:MM angeben.`;
      if (s % 5 || e % 5) return `${label}, Block ${n + 1}: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).`;
      if (s >= e) return `${label}, Block ${n + 1}: Beginn muss vor dem Ende liegen.`;
      spans.push([s, e]);
    }
    for (let n = 1; n < spans.length; n++) {
      if (spans[n][0] <= spans[n - 1][1]) {
        return `${label}: Block ${n + 1} muss nach dem Ende von Block ${n} beginnen; aneinandergrenzende Blöcke bitte als einen Block erfassen.`;
      }
    }
    const pause = week[i]?.pause_minutes;
    if (pause === null || pause === undefined) return `${label}: Pause angeben (0, wenn keine).`;
    if (!Number.isInteger(pause) || pause < 0 || pause % 5) return `${label}: Pause in Minuten im 5-Minuten-Raster angeben.`;
    if (!spans.length && pause !== 0) return `${label}: Pause nur an Tagen mit Blöcken.`;
    const gross = spans.reduce((sum, [s, e]) => sum + e - s, 0);
    if (spans.length && pause >= gross) return `${label}: Pause muss kürzer sein als die Gesamtzeit der Blöcke.`;
    if (spans.length) totalNet += gross - pause;
  }
  if (!week.some((d) => (d?.blocks ?? []).length > 0)) return 'Mindestens ein Wochentag braucht einen Block.';
  if (totalNet > WEEK_LIMIT_MINUTES) return 'Die Wochensumme darf 60 Stunden nicht überschreiten.';
  return null;
}
```

- [ ] **Step 4: Antworttypen anlegen**

`frontend/src/pages/admin/users/workingHoursTypes.ts`:

```ts
// Spec 2026-10-08, 11.3: Antwortformen des Dialogs „Arbeitszeit & Wochenstunden".
// Die neuen Vorschau-Felder sind optional — eine ältere Antwort (oder ein
// Testdouble) muss sie nicht tragen.
import type { WeekBlocks } from '../../../types/workBlocks';

/** #431: eine Verlaufszeile ist ein vollständiger Vertrags-Snapshot ab `effective_from`. */
export interface WorkingHoursChange {
  id: string;
  user_id: string;
  effective_from: string;
  weekly_hours: number;
  use_daily_schedule?: boolean;
  hours_monday?: number | null;
  hours_tuesday?: number | null;
  hours_wednesday?: number | null;
  hours_thursday?: number | null;
  hours_friday?: number | null;
  work_days_per_week?: number | null;
  note?: string | null;
  created_at: string;
  blocks?: WeekBlocks | null;
}

export type ShorteningReason = 'entries' | 'saldo' | 'absence_credit';

export interface TimeEntryChange {
  entry_id: string;
  date: string;
  old_start: string | null;
  old_end: string | null;
  old_uncredited: number;
  old_net: number;
  new_start: string | null;
  new_end: string | null;
  new_uncredited: number;
  new_net: number;
  not_extendable: 'start' | 'end' | 'both' | null;
}

export interface ArbzgFindings {
  days_over_10_credited_before: number;
  days_over_10_credited_after: number;
  days_over_10_presence: number;
  weeks_over_48_credited_before: number;
  weeks_over_48_credited_after: number;
  weeks_over_48_presence: number;
}

export interface WorkingHoursChangePreview {
  is_retroactive: boolean;
  period_start: string;
  period_end: string;
  current_daily_target: number;
  new_daily_target: number;
  day_targets_current: number[];
  day_targets_new: number[];
  overtime_before: number;
  overtime_after: number;
  vacation_days_before: number;
  vacation_days_after: number;
  affected_absences: number;
  blocked_reason: string | null;
  closed_years: number[];
  closed_year_warning: string | null;
  grace_minutes?: number;
  blocks_current?: WeekBlocks | null;
  blocks_new?: WeekBlocks | null;
  changed_weekdays?: number[];
  affected_time_entries?: number;
  time_entry_months?: { month: string; entries: number; net_before: number; net_after: number }[];
  time_entry_changes?: TimeEntryChange[];
  skipped_time_entries?: { entry_id: string; date: string; reason: string }[];
  not_extendable_count?: number;
  not_extendable_entries?: TimeEntryChange[];
  is_shortening?: boolean;
  shortening_reasons?: ShorteningReason[];
  shortening_closed_years?: number[];
  earliest_lossless_date?: string | null;
  earliest_lossless_note?: string | null;
  lost_credited_hours?: number;
  target_delta_hours?: number;
  credited_delta_hours?: number;
  saldo_delta_hours?: number;
  open_day_saldo_delta_hours?: number;
  absence_f1_adjustments?: number;
  absence_credit_reductions?: { absence_id: string; date: string; old_hours: number; new_hours: number }[];
  reset_body?: Record<string, unknown> | null;
  stale_entries_closed?: number;
  arbzg_findings?: ArbzgFindings;
  milog_warning?: string[];
  block_break_notices?: string[];
}
```

- [ ] **Step 5: Feste Texte und Helfer anlegen**

`frontend/src/pages/admin/users/workingHoursTexts.ts`:

```ts
// Spec 2026-10-08, 12.1/9.5/P26: feste Texte des Dialogs „Arbeitszeit &
// Wochenstunden" — an EINER Stelle, damit Dialog, Verkürzungs-Kasten und
// Lösch-Dialog wortgleich bleiben. Die Grundtyp-SCHLÜSSEL sind eingefroren
// (Backend `reclamp_audit.REASON_TYPES`), die Oberfläche zeigt nur die Beschriftungen.
import { deHoursExact } from '../../../utils/formatters';

export const LEGAL_HINT =
  'Ändert sich der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und braucht das '
  + 'Einverständnis der beschäftigten Person. Die Lage kann, soweit der Vertrag sie nicht festlegt, im Rahmen des '
  + 'Direktionsrechts (§ 106 GewO) nach billigem Ermessen und mit angemessener Ankündigung nur für die Zukunft '
  + 'geändert werden. Vereinbarte Arbeitszeiten und Pausen sind spätestens am Tag des Wirksamwerdens schriftlich '
  + 'mitzuteilen (§ 3 NachwG). Mit Betriebsrat ist die Änderung mitbestimmungspflichtig (§ 87 Abs. 1 Nr. 2, 3 und 6 '
  + 'BetrVG). PraxisZeit prüft das nicht.';
export const JARBSCHG_HINT =
  'Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG); PraxisZeit prüft diese nicht.';
export const LEGACY_BOX_TITLE = 'Arbeitszeit-Fenster (Altbestand, nur Kappung)';
export const BLOCKS_WITHOUT_EFFECT = 'Arbeitszeit-Blöcke gespeichert, ohne Wirkung (keine Stundenzählung)';
export const modeSwitchHint = (date: string) =>
  `Die Arbeitszeit-Blöcke enden mit dieser Änderung; ab ${date} wird nicht mehr gekappt.`;

export const REASON_HELP = 'Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.';
export const WAGE_SENTENCE =
  'Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde, ist unabhängig von der Anrechnung '
  + 'zu vergüten (§ 611a, § 612 BGB). Auf den Mindestlohn für geleistete Stunden kann nicht verzichtet werden (§ 3 MiLoG).';
export const OTHER_WARNING =
  'Eine einseitige rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO wirkt nur für die Zukunft); '
  + 'geleistete Arbeit bleibt zu vergüten.';
export const OTHER_CONFIRM = 'Mir ist bewusst, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht nicht gedeckt ist.';

export type RetroReasonKey = 'erfassungsfehler' | 'einvernehmlich' | 'sonstiges';
export const REASON_OPTIONS: { value: RetroReasonKey; label: string; confirm: string }[] = [
  {
    value: 'erfassungsfehler',
    label: 'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)',
    confirm: `Ich habe geprüft, dass die hinterlegte Arbeitszeit falsch war (Fehlerkorrektur). ${WAGE_SENTENCE}`,
  },
  {
    value: 'einvernehmlich',
    label: 'Mit der beschäftigten Person vereinbart',
    confirm: `Ich habe geprüft, dass die rückwirkende Änderung mit der beschäftigten Person vereinbart ist. ${WAGE_SENTENCE}`,
  },
  { value: 'sonstiges', label: 'Sonstiges', confirm: `Ich habe die Gründe geprüft. ${WAGE_SENTENCE}` },
];

export type ShorteningOption = 'lossless' | 'retro';

export interface ReasonState {
  type: RetroReasonKey | '';
  text: string;
  wageConfirmed: boolean;
  otherConfirmed: boolean;
}

export const EMPTY_REASON: ReasonState = { type: '', text: '', wageConfirmed: false, otherConfirmed: false };

/** P15/P26: Grundtyp, 10–400 Zeichen Begründung, Haken; bei „Sonstiges" zweiter Haken. */
export function reasonComplete(r: ReasonState): boolean {
  const len = r.text.trim().length;
  return !!r.type && len >= 10 && len <= 400 && r.wageConfirmed && (r.type !== 'sonstiges' || r.otherConfirmed);
}

/** Body-Felder des Schutzpakets (Anlegen und DELETE, Spec 11.2). */
export function reasonPayload(r: ReasonState): Record<string, unknown> {
  return {
    retroactive_reason_type: r.type,
    retroactive_reason_text: r.text.trim(),
    wage_risk_confirmed: r.wageConfirmed,
    other_reason_risk_confirmed: r.type === 'sonstiges' ? r.otherConfirmed : false,
  };
}

/** Wie `reclamp_audit.SKIP_LABELS`. */
export const SKIP_LABELS: Record<string, string> = {
  credit_override: 'anerkannt',
  open: 'offen',
  soll_free_day: 'Sonn-/Feiertag',
  track_hours_off: 'ohne Stundenzählung',
  outside_employment: 'außerhalb der Beschäftigung',
  unique_collision: 'Überschneidung',
};

/** Spec 11.4 — Wortlaut des 400 bei Verlust in einem abgeschlossenen Jahr (größtes Jahr). */
export function closedYearMessage(years: number[] | null | undefined): string | null {
  if (!years || years.length === 0) return null;
  const y = Math.max(...years);
  return `Rückwirkende Verkürzung in das abgeschlossene Jahr ${y} ist gesperrt. Bitte die Änderung frühestens ab 01.01.${y + 1} wirksam werden lassen.`;
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y}`;
}

export function shortDate(iso: string): string {
  const [, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.`;
}

const MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
export function monthLabel(yyyyMm: string): string {
  const [y, m] = yyyyMm.split('-');
  return `${MONTHS[Number(m) - 1]} ${y}`;
}

export function hm(hours: number): string {
  const minutes = Math.round(Math.abs(hours) * 60);
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}

/** „+1:45" / „−3:45" (U+2212) / „0:00". */
export function signedHm(hours: number): string {
  const minutes = Math.round(hours * 60);
  return `${minutes > 0 ? '+' : minutes < 0 ? '−' : ''}${hm(hours)}`;
}

/** „+1,0" / „−1,5" / „0,0" — Urlaubstage in DE-Schreibweise. */
export function signedDays(value: number): string {
  const v = Math.round(value * 100) / 100;
  const text = deHoursExact(Math.abs(v));
  return v > 0 ? `+${text}` : v < 0 ? `−${text}` : text;
}

/** Spec 12.1 — Toast nach dem Speichern (bzw. Löschen, gleiche Zählung). */
export function savedMessage(
  created: { adjusted_time_entries?: number; skipped_time_entries?: number; adjusted_absences?: number },
  verb: 'Gespeichert' | 'Gelöscht' = 'Gespeichert',
): string {
  const parts: string[] = [];
  const n = created.adjusted_time_entries ?? 0;
  const k = created.skipped_time_entries ?? 0;
  const a = created.adjusted_absences ?? 0;
  // Wortlaute zusammenhängend im Quelltext — das Doku-Gate (PR4) sucht sie per grep.
  if (n > 0) parts.push(n === 1 ? '1 Zeiteintrag neu berechnet' : `${n} Zeiteinträge neu berechnet`);
  if (k > 0) parts.push(`${k} übersprungen`);
  if (a > 0) parts.push(`${a} ${a === 1 ? 'Abwesenheit' : 'Abwesenheiten'} angepasst`);
  return parts.length ? `${verb}. ${parts.join(', ')}.` : `${verb}.`;
}
```

- [ ] **Step 6: Tests laufen lassen — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/utils/workBlocks.test.ts src/pages/admin/users/workingHoursTexts.test.ts --pool=threads` und `npx tsc --noEmit`
Expected: PASS, `tsc` ohne Ausgabe.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/utils/workBlocks.ts frontend/src/utils/workBlocks.test.ts frontend/src/pages/admin/users/workingHoursTypes.ts frontend/src/pages/admin/users/workingHoursTexts.ts frontend/src/pages/admin/users/workingHoursTexts.test.ts
git commit -F - <<'EOF'
feat(bloecke): Frontend-Zwillinge der Blockregeln, Antworttypen und feste Dialogtexte

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 17: `WorkBlocksEditor` (Spec 12.1 „Block-Editor", E59)

**Files:**
- Create: `frontend/src/components/WorkBlocksEditor.tsx`, `frontend/src/components/WorkBlocksEditor.test.tsx`

**Interfaces:**
- Consumes: `WEEKDAY_LABELS`, `sumBlocks`, `minutesToHm`, `validateWeekBlocks` (Task 16); `WeekBlocks`, `DayBlocks` (PR1)
- Produces: `export default function WorkBlocksEditor(props: { value: WeekBlocks; onChange: (week: WeekBlocks) => void; idPrefix?: string })` — kontrolliert; Beschriftungen: Zeiten `"{Mo} Block {n} von"` / `"{Mo} Block {n} bis"`, Pause `"{Mo} Pause innerhalb der Blöcke (Min)"`, Knöpfe `"{Mo}: Block hinzufügen"` / `"{Mo} Block {n} entfernen"`; je Tag Zeile `data-testid="{idPrefix}-day-{i}"` mit „Gesamtzeit H:MM h · Pause H:MM h · Tagessoll H:MM h", Wochenzeile `data-testid="{idPrefix}-week"`; Validierungstext als `role="alert"`

- [ ] **Step 1: Failing tests schreiben**

`frontend/src/components/WorkBlocksEditor.test.tsx`:

```tsx
import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import WorkBlocksEditor from './WorkBlocksEditor';
import { emptyWeek } from '../utils/workBlocks';
import type { WeekBlocks } from '../types/workBlocks';

function Harness({ initial }: { initial: WeekBlocks }) {
  const [week, setWeek] = useState(initial);
  return <WorkBlocksEditor value={week} onChange={setWeek} idPrefix="t" />;
}

const E = { blocks: [], pause_minutes: 0 };

describe('WorkBlocksEditor (Spec 12.1)', () => {
  it('leere Woche: kein Arbeitstag, Block anlegen, Fehlertext beim leeren Block', () => {
    render(<Harness initial={emptyWeek()} />);
    expect(screen.getAllByText('kein Arbeitstag')).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    expect(screen.getByLabelText('Mo Block 1 von')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Mo, Block 1: Uhrzeit im Format HH:MM angeben.');
  });

  it('zeigt live Gesamtzeit, Pause, Tagessoll und die Wochensumme', () => {
    render(<Harness initial={emptyWeek()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 1 bis'), { target: { value: '12:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 2 von'), { target: { value: '15:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '18:00' } });
    fireEvent.change(screen.getByLabelText('Mo Pause innerhalb der Blöcke (Min)'), { target: { value: '30' } });
    expect(screen.getByTestId('t-day-0')).toHaveTextContent('Gesamtzeit 7:00 h · Pause 0:30 h · Tagessoll 6:30 h');
    expect(screen.getByTestId('t-week')).toHaveTextContent(
      'Woche: Gesamtzeit 7:00 h · Pause 0:30 h · Wochensoll 6:30 h · 1 Arbeitstag');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('Tagessoll minutengenau (Review Focus 5: 7:55 h, nicht 7,92)', () => {
    const week: WeekBlocks = [
      { blocks: [{ start: '07:30', end: '12:00' }, { start: '13:00', end: '16:25' }], pause_minutes: 0 }, E, E, E, E,
    ];
    render(<Harness initial={week} />);
    expect(screen.getByTestId('t-day-0')).toHaveTextContent('Tagessoll 7:55 h');
  });

  it('höchstens drei Blöcke, Entfernen setzt die Pause eines leeren Tages auf 0', () => {
    render(<Harness initial={emptyWeek()} />);
    const add = screen.getByRole('button', { name: 'Di: Block hinzufügen' });
    fireEvent.click(add);
    fireEvent.click(add);
    fireEvent.click(add);
    expect(add).toBeDisabled();
    for (const n of [3, 2, 1]) fireEvent.click(screen.getByRole('button', { name: `Di Block ${n} entfernen` }));
    expect(screen.getAllByText('kein Arbeitstag')).toHaveLength(5);
    expect(screen.queryByRole('alert')).toHaveTextContent('Mindestens ein Wochentag braucht einen Block.');
  });

  it('leere Pause verlangt eine Angabe, Altwerte melden das Raster (Review Focus 4)', () => {
    const legacy: WeekBlocks = [{ blocks: [{ start: '07:37', end: '23:59' }], pause_minutes: null }, E, E, E, E];
    render(<Harness initial={legacy} />);
    expect(screen.getByLabelText('Mo Block 1 von')).toHaveValue('07:37');
    expect(screen.getByRole('alert')).toHaveTextContent('Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).');
    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '07:35' } });
    fireEvent.change(screen.getByLabelText('Mo Block 1 bis'), { target: { value: '16:30' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Mo: Pause angeben (0, wenn keine).');
  });
});
```

- [ ] **Step 2: Test laufen lassen — muss scheitern**

Run (aus `frontend/`): `npx vitest run src/components/WorkBlocksEditor.test.tsx --pool=threads`
Expected: FAIL — „Failed to resolve import ./WorkBlocksEditor".

- [ ] **Step 3: Komponente anlegen**

`frontend/src/components/WorkBlocksEditor.tsx`:

```tsx
import { Plus, X } from 'lucide-react';
import type { DayBlocks, WeekBlocks } from '../types/workBlocks';
import { WEEKDAY_LABELS, minutesToHm, sumBlocks, validateWeekBlocks } from '../utils/workBlocks';

interface WorkBlocksEditorProps {
  value: WeekBlocks;
  onChange: (week: WeekBlocks) => void;
  idPrefix?: string;
}

/**
 * Spec 2026-10-08, 12.1: je Wochentag bis zu drei Blöcke „von–bis" im
 * 5-Minuten-Raster und die „Pause innerhalb der Blöcke"; live je Tag
 * „Gesamtzeit · Pause · Tagessoll" und die Wochensumme. Gemeinsam für den
 * Dialog „Arbeitszeit & Wochenstunden" und das Anlegeformular.
 *
 * Angezeigt wird MINUTENGENAU (7:55 h) — gespeichert rundet der Server auf
 * 0,01 h (7,92 h, Spec 4.1). Validierungstexte wortgleich zum Backend (3.4).
 */
export default function WorkBlocksEditor({ value, onChange, idPrefix = 'wb' }: WorkBlocksEditorProps) {
  const updateDay = (index: number, day: DayBlocks) => onChange(value.map((d, i) => (i === index ? day : d)));
  const error = validateWeekBlocks(value);
  const totals = value.reduce(
    (acc, day) => {
      const t = sumBlocks(day);
      return { gross: acc.gross + t.grossMinutes, pause: acc.pause + t.pauseMinutes, net: acc.net + t.netMinutes };
    },
    { gross: 0, pause: 0, net: 0 },
  );
  const workDays = value.filter((d) => d.blocks.length > 0).length;

  return (
    <div className="space-y-2">
      {WEEKDAY_LABELS.map((label, i) => {
        const day = value[i] ?? { blocks: [], pause_minutes: 0 };
        const t = sumBlocks(day);
        return (
          <div key={label} className="rounded-lg border border-gray-200 bg-white p-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-7 font-medium text-gray-800">{label}</span>
              {day.blocks.length === 0 && <span className="text-sm text-gray-500">kein Arbeitstag</span>}
              {day.blocks.map((block, n) => (
                <span key={n} className="flex items-center gap-1">
                  <input
                    type="time"
                    step={300}
                    aria-label={`${label} Block ${n + 1} von`}
                    value={block.start}
                    onChange={(e) => updateDay(i, {
                      ...day, blocks: day.blocks.map((b, k) => (k === n ? { ...b, start: e.target.value } : b)),
                    })}
                    className="px-1 py-0.5 border border-gray-300 rounded-sm text-sm"
                  />
                  <span aria-hidden="true">–</span>
                  <input
                    type="time"
                    step={300}
                    aria-label={`${label} Block ${n + 1} bis`}
                    value={block.end}
                    onChange={(e) => updateDay(i, {
                      ...day, blocks: day.blocks.map((b, k) => (k === n ? { ...b, end: e.target.value } : b)),
                    })}
                    className="px-1 py-0.5 border border-gray-300 rounded-sm text-sm"
                  />
                  <button
                    type="button"
                    aria-label={`${label} Block ${n + 1} entfernen`}
                    onClick={() => {
                      const blocks = day.blocks.filter((_, k) => k !== n);
                      updateDay(i, { blocks, pause_minutes: blocks.length ? day.pause_minutes : 0 });
                    }}
                    className="text-gray-500 hover:text-red-600"
                  >
                    <X size={14} />
                  </button>
                </span>
              ))}
              <button
                type="button"
                aria-label={`${label}: Block hinzufügen`}
                disabled={day.blocks.length >= 3}
                onClick={() => updateDay(i, {
                  blocks: [...day.blocks, { start: '', end: '' }],
                  pause_minutes: day.blocks.length ? day.pause_minutes : 0,
                })}
                className="flex items-center gap-0.5 text-sm text-primary disabled:text-gray-300"
              >
                <Plus size={14} /> Block
              </button>
              {day.blocks.length > 0 && (
                <label className="ml-auto flex items-center gap-1 text-sm text-gray-700">
                  Pause innerhalb
                  <input
                    type="number"
                    min={0}
                    step={5}
                    aria-label={`${label} Pause innerhalb der Blöcke (Min)`}
                    value={day.pause_minutes ?? ''}
                    onChange={(e) => updateDay(i, {
                      ...day, pause_minutes: e.target.value === '' ? null : Number(e.target.value),
                    })}
                    className="w-16 px-1 py-0.5 border border-gray-300 rounded-sm text-sm text-right"
                  />
                  Min
                </label>
              )}
            </div>
            {day.blocks.length > 0 && (
              <p className="mt-1 text-xs text-gray-600" data-testid={`${idPrefix}-day-${i}`}>
                Gesamtzeit {minutesToHm(t.grossMinutes)} h · Pause {minutesToHm(t.pauseMinutes)} h · Tagessoll{' '}
                {minutesToHm(t.netMinutes)} h
              </p>
            )}
          </div>
        );
      })}
      <p className="text-sm text-gray-800" data-testid={`${idPrefix}-week`}>
        Woche: Gesamtzeit {minutesToHm(totals.gross)} h · Pause {minutesToHm(totals.pause)} h · Wochensoll{' '}
        {minutesToHm(totals.net)} h · {workDays} {workDays === 1 ? 'Arbeitstag' : 'Arbeitstage'}
      </p>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Test laufen lassen — muss grün sein**

Run (aus `frontend/`): `npx vitest run src/components/WorkBlocksEditor.test.tsx --pool=threads` und `npx tsc --noEmit`
Expected: PASS, `tsc` ohne Ausgabe.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WorkBlocksEditor.tsx frontend/src/components/WorkBlocksEditor.test.tsx
git commit -F - <<'EOF'
feat(bloecke): Block-Editor mit Live-Summen und wortgleicher Validierung

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 18a: Auswirkungs-Box `WhImpactBox` (Spec 9.4, 11.3, 12.1)

Eigenständige Anzeige-Komponente für die Vorschau einer Änderung **und** die `delete-preview` (Task 20). Getrennt vom Dialog-Umbau (Task 18b), damit sie für sich geprüft und freigegeben werden kann.

**Files:**
- Create: `frontend/src/pages/admin/users/WhImpactBox.tsx`, `frontend/src/pages/admin/users/WhImpactBox.test.tsx`

**Interfaces:**
- Consumes: `WorkingHoursChangePreview`, `TimeEntryChange` (Task 16, `workingHoursTypes.ts`); `SKIP_LABELS`, `hm`, `monthLabel`, `shortDate`, `signedDays`, `signedHm` (Task 16, `workingHoursTexts.ts`); `WEEKDAY_LABELS` (PR1); `deHoursExact` (Bestand, `utils/formatters.ts`)
- Produces:
  - `WhImpactBox({ preview }: { preview: WorkingHoursChangePreview })` — Zeilen „Auswirkung (Puffer N Min) · geänderte Tage: …", Tagessoll je Wochentag, „Zeiteinträge: n neu berechnet · k übersprungen (…)", Monatsliste, „nicht erweiterbar", geschlossene Alteinträge, „n Abwesenheit(en) betroffen.", F1-Zusatz, Tabelle Soll/Angerechnet/Überstunden/Urlaub, ArbZG-Befunde, Knopf „Einzelheiten" (Einträge alt → neu, übersprungene, gesenkte Gutschriften)

- [ ] **Step 1: Failing test schreiben**

`frontend/src/pages/admin/users/WhImpactBox.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import WhImpactBox from './WhImpactBox';
import type { WorkingHoursChangePreview } from './workingHoursTypes';

const BASE: WorkingHoursChangePreview = {
  is_retroactive: true, period_start: '2026-09-01', period_end: '2026-10-08',
  current_daily_target: 7, new_daily_target: 6,
  day_targets_current: [7, 4, 0, 4, 0], day_targets_new: [6, 4, 0, 4, 0],
  overtime_before: 12.5, overtime_after: 14.25, vacation_days_before: 10, vacation_days_after: 10,
  affected_absences: 1, blocked_reason: null, closed_years: [], closed_year_warning: null,
};

// Spec 12.1, erster Zustand (Mo-Nachmittag 15–18 → 15–17 ab 01.09.2026).
const FIRST_STATE: WorkingHoursChangePreview = {
  ...BASE,
  grace_minutes: 15,
  changed_weekdays: [0],
  affected_time_entries: 3,
  time_entry_months: [
    { month: '2026-09', entries: 2, net_before: 6, net_after: 4.5 },
    { month: '2026-10', entries: 1, net_before: 3, net_after: 2.25 },
  ],
  time_entry_changes: [{
    entry_id: 'e1', date: '2026-09-14', old_start: '15:00:00', old_end: '18:00:00', old_uncredited: 0, old_net: 3,
    new_start: '15:00:00', new_end: '17:15:00', new_uncredited: 0, new_net: 2.25, not_extendable: null,
  }],
  skipped_time_entries: [{ entry_id: 'e9', date: '2026-09-28', reason: 'credit_override' }],
  not_extendable_count: 0,
  not_extendable_entries: [],
  target_delta_hours: -4,
  credited_delta_hours: -2.25,
  saldo_delta_hours: 1.75,
  absence_f1_adjustments: 0,
  absence_credit_reductions: [],
  stale_entries_closed: 0,
};

describe('WhImpactBox (Spec 12.1)', () => {
  it('zeigt Puffer, geänderte Tage, Einträge je Monat und Übersprungene', () => {
    render(<WhImpactBox preview={FIRST_STATE} />);
    expect(screen.getByText('Auswirkung (Puffer 15 Min) · geänderte Tage: Mo')).toBeInTheDocument();
    expect(screen.getByText('Zeiteinträge: 3 neu berechnet · 1 übersprungen (1 anerkannt)')).toBeInTheDocument();
    expect(screen.getByText('Sep 2026 · 2 Einträge · 6:00 h → 4:30 h')).toBeInTheDocument();
    expect(screen.getByText('Okt 2026 · 1 Eintrag · 3:00 h → 2:15 h')).toBeInTheDocument();
    expect(screen.getByText(/Tagessoll je Wochentag: Mo 7,0 → 6,0 · Di 4,0 → 4,0 · Do 4,0 → 4,0/)).toBeInTheDocument();
  });

  it('trennt Soll und angerechnete Zeit (9.4) und zeigt Überstunden in H:MM', () => {
    render(<WhImpactBox preview={FIRST_STATE} />);
    const soll = screen.getByRole('row', { name: /Soll im Zeitraum/ });
    expect(soll).toHaveTextContent('−4:00 h');
    expect(screen.getByRole('row', { name: /Angerechnet/ })).toHaveTextContent('−2:15 h');
    const over = screen.getByRole('row', { name: /Überstunden/ });
    expect(over).toHaveTextContent('+12:30 h');
    expect(over).toHaveTextContent('+14:15 h');
    expect(over).toHaveTextContent('+1:45 h');
  });

  it('nennt nicht erweiterbare Einträge mit Datum und Seite (zweiter Zustand)', () => {
    const change = {
      entry_id: 'e2', date: '2026-09-14', old_start: '15:00:00', old_end: '18:15:00', old_uncredited: 0, old_net: 3.25,
      new_start: '15:00:00', new_end: '18:15:00', new_uncredited: 0, new_net: 3.25, not_extendable: 'end' as const,
    };
    render(<WhImpactBox preview={{ ...FIRST_STATE, not_extendable_count: 1, not_extendable_entries: [change] }} />);
    expect(screen.getByText('1 Eintrag ohne Rohstempel – nicht erweiterbar (14.09., Ende 18:15)')).toBeInTheDocument();
  });

  it('meldet geschlossene Alteinträge, F1-Angleichungen und ArbZG-Befunde', () => {
    render(<WhImpactBox preview={{
      ...FIRST_STATE, stale_entries_closed: 2, absence_f1_adjustments: 1,
      arbzg_findings: {
        days_over_10_credited_before: 0, days_over_10_credited_after: 0, days_over_10_presence: 1,
        weeks_over_48_credited_before: 3, weeks_over_48_credited_after: 0, weeks_over_48_presence: 3,
      },
    }} />);
    expect(screen.getByText('2 offene Einträge vergangener Tage werden vorher automatisch geschlossen.')).toBeInTheDocument();
    expect(screen.getByText('1 Abwesenheit(en) betroffen, davon 1 auf das Tagessoll abzüglich der Arbeit desselben Tages begrenzt.'))
      .toBeInTheDocument();
    expect(screen.getByText('Wochen > 48 h: angerechnet bisher 3, neu 0 · laut Stempel 3')).toBeInTheDocument();
    expect(screen.queryByText(/Tage > 10 h/)).not.toBeInTheDocument();
  });

  it('Einzelheiten: Einträge alt → neu, Übersprungene, gesenkte Gutschriften', () => {
    render(<WhImpactBox preview={{
      ...FIRST_STATE,
      absence_credit_reductions: [{ absence_id: 'a1', date: '2026-09-21', old_hours: 8, new_hours: 4 }],
    }} />);
    expect(screen.queryByText(/14\.09\. 15:00–18:00/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Einzelheiten' }));
    expect(screen.getByText('14.09. 15:00–18:00 → 15:00–17:15 (3:00 h → 2:15 h)')).toBeInTheDocument();
    expect(screen.getByText('28.09. übersprungen: anerkannt')).toBeInTheDocument();
    expect(screen.getByText('Gutschrift 21.09.: 8:00 h → 4:00 h')).toBeInTheDocument();
  });

  it('Bestandsantwort ohne neue Felder: nur Abwesenheiten und Tabelle', () => {
    render(<WhImpactBox preview={BASE} />);
    expect(screen.getByText('1 Abwesenheit(en) betroffen.')).toBeInTheDocument();
    expect(screen.queryByText(/Auswirkung \(Puffer/)).not.toBeInTheDocument();
    expect(screen.queryByRole('row', { name: /Soll im Zeitraum/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Einzelheiten' })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Test laufen lassen — muss scheitern**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/WhImpactBox.test.tsx --pool=threads`
Expected: FAIL — „Failed to resolve import ./WhImpactBox".

- [ ] **Step 3: `WhImpactBox.tsx` anlegen**

```tsx
import { useState } from 'react';
import { deHoursExact } from '../../../utils/formatters';
import { WEEKDAY_LABELS } from '../../../utils/workBlocks';
import type { TimeEntryChange, WorkingHoursChangePreview } from './workingHoursTypes';
import { SKIP_LABELS, hm, monthLabel, shortDate, signedDays, signedHm } from './workingHoursTexts';

function round2(value: number): number {
  return Number.isFinite(value) ? Math.round(value * 100) / 100 : 0;
}

const clock = (t: string | null) => (t ? t.slice(0, 5) : '–');

function notExtendableText(c: TimeEntryChange): string {
  if (c.not_extendable === 'start') return `${shortDate(c.date)}, Beginn ${clock(c.old_start)}`;
  if (c.not_extendable === 'both') return `${shortDate(c.date)}, Beginn ${clock(c.old_start)}, Ende ${clock(c.old_end)}`;
  return `${shortDate(c.date)}, Ende ${clock(c.old_end)}`;
}

function skippedSummary(reasons: string[]): string {
  const counts = new Map<string, number>();
  reasons.forEach((r) => counts.set(r, (counts.get(r) ?? 0) + 1));
  return [...counts].map(([r, n]) => `${n} ${SKIP_LABELS[r] ?? r}`).join(', ');
}

/**
 * Spec 2026-10-08, 12.1/9.4: Inhalt der Auswirkungs-Box — gemeinsam für die
 * Vorschau einer Änderung und die `delete-preview`. Ältere Antworten ohne die
 * Felder aus 11.3 zeigen nur Abwesenheiten und Tabelle.
 */
export default function WhImpactBox({ preview }: { preview: WorkingHoursChangePreview }) {
  const [details, setDetails] = useState(false);
  const changedDays = (preview.changed_weekdays ?? []).map((i) => WEEKDAY_LABELS[i]).join(', ');
  const entries = preview.affected_time_entries ?? 0;
  const skipped = preview.skipped_time_entries ?? [];
  const notExtendable = preview.not_extendable_entries ?? [];
  const changes = preview.time_entry_changes ?? [];
  const reductions = preview.absence_credit_reductions ?? [];
  const stale = preview.stale_entries_closed ?? 0;
  const f1 = preview.absence_f1_adjustments ?? 0;
  const overtimeDelta = round2(preview.overtime_after - preview.overtime_before);
  const vacationDelta = round2(preview.vacation_days_after - preview.vacation_days_before);
  const vacationYear = preview.period_start.slice(0, 4);
  const arbzg = preview.arbzg_findings;

  const dayTargets = (() => {
    const before = preview.day_targets_current;
    const after = preview.day_targets_new;
    if (!Array.isArray(before) || !Array.isArray(after)) return '';
    const parts = WEEKDAY_LABELS.map((label, i) => {
      const cur = before[i] ?? 0;
      const next = after[i] ?? 0;
      return cur <= 0 && next <= 0 ? null : `${label} ${deHoursExact(cur)} → ${deHoursExact(next)}`;
    }).filter((p): p is string => p !== null);
    return parts.length ? `Tagessoll je Wochentag: ${parts.join(' · ')}` : '';
  })();

  const hasDetails = changes.length > 0 || skipped.length > 0 || reductions.length > 0;

  return (
    <div className="mt-1 space-y-1 text-amber-900">
      {preview.grace_minutes !== undefined && (
        <p>{`Auswirkung (Puffer ${preview.grace_minutes} Min)${changedDays ? ` · geänderte Tage: ${changedDays}` : ''}`}</p>
      )}
      {dayTargets && <p className="text-amber-800">{dayTargets}</p>}
      {(entries > 0 || skipped.length > 0) && (
        <p>
          {`Zeiteinträge: ${entries} neu berechnet`
            + (skipped.length ? ` · ${skipped.length} übersprungen (${skippedSummary(skipped.map((s) => s.reason))})` : '')}
        </p>
      )}
      {(preview.time_entry_months ?? []).length > 0 && (
        <ul className="pl-4 text-amber-800">
          {(preview.time_entry_months ?? []).map((m) => (
            <li key={m.month}>
              {`${monthLabel(m.month)} · ${m.entries} ${m.entries === 1 ? 'Eintrag' : 'Einträge'} · ${hm(m.net_before)} h → ${hm(m.net_after)} h`}
            </li>
          ))}
        </ul>
      )}
      {notExtendable.length > 0 && (
        <p>
          {`${notExtendable.length} ${notExtendable.length === 1 ? 'Eintrag' : 'Einträge'} ohne Rohstempel – nicht erweiterbar (${notExtendable.map(notExtendableText).join('; ')})`}
        </p>
      )}
      {stale > 0 && (
        <p>
          {stale === 1
            ? '1 offener Eintrag eines vergangenen Tages wird vorher automatisch geschlossen.'
            : `${stale} offene Einträge vergangener Tage werden vorher automatisch geschlossen.`}
        </p>
      )}
      <p className="text-amber-800">
        {`${preview.affected_absences} Abwesenheit(en) betroffen`
          + (f1 > 0 ? `, davon ${f1} auf das Tagessoll abzüglich der Arbeit desselben Tages begrenzt.` : '.')}
      </p>
      <table className="mt-2 w-full">
        <thead>
          <tr className="text-xs uppercase text-amber-700">
            <th scope="col" className="text-left font-medium">Auswirkung</th>
            <th scope="col" className="text-right font-medium">bisher</th>
            <th scope="col" className="text-right font-medium">neu</th>
            <th scope="col" className="text-right font-medium">
              <span aria-hidden="true">Δ</span>
              <span className="sr-only">Änderung</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {preview.target_delta_hours !== undefined && (
            <tr>
              <th scope="row" className="text-left font-medium">Soll im Zeitraum</th>
              <td /><td />
              <td className="text-right font-medium">{`${signedHm(preview.target_delta_hours)} h`}</td>
            </tr>
          )}
          {preview.credited_delta_hours !== undefined && (
            <tr>
              <th scope="row" className="text-left font-medium">Angerechnet</th>
              <td /><td />
              <td className="text-right font-medium">{`${signedHm(preview.credited_delta_hours)} h`}</td>
            </tr>
          )}
          <tr>
            <th scope="row" className="text-left font-medium">Überstunden</th>
            <td className="text-right">{`${signedHm(preview.overtime_before)} h`}</td>
            <td className="text-right">{`${signedHm(preview.overtime_after)} h`}</td>
            <td className="text-right font-medium">{`${signedHm(overtimeDelta)} h`}</td>
          </tr>
          <tr>
            {/* Die Urlaubszahlen gehören zum Jahr des Wirkungszeitraums. */}
            <th scope="row" className="text-left font-medium">{`Urlaub ${vacationYear}`}</th>
            <td className="text-right">{`${deHoursExact(preview.vacation_days_before)} Tage`}</td>
            <td className="text-right">{`${deHoursExact(preview.vacation_days_after)} Tage`}</td>
            <td className="text-right font-medium">{`${signedDays(vacationDelta)} Tage`}</td>
          </tr>
        </tbody>
      </table>
      {arbzg && arbzg.days_over_10_credited_before !== arbzg.days_over_10_credited_after && (
        <p>{`Tage > 10 h: angerechnet bisher ${arbzg.days_over_10_credited_before}, neu ${arbzg.days_over_10_credited_after} · laut Stempel ${arbzg.days_over_10_presence}`}</p>
      )}
      {arbzg && arbzg.weeks_over_48_credited_before !== arbzg.weeks_over_48_credited_after && (
        <p>{`Wochen > 48 h: angerechnet bisher ${arbzg.weeks_over_48_credited_before}, neu ${arbzg.weeks_over_48_credited_after} · laut Stempel ${arbzg.weeks_over_48_presence}`}</p>
      )}
      {hasDetails && (
        <>
          <button
            type="button"
            aria-expanded={details}
            onClick={() => setDetails((d) => !d)}
            className="text-sm font-medium text-amber-900 underline hover:no-underline"
          >
            Einzelheiten
          </button>
          {details && (
            <ul className="pl-4 text-xs text-amber-900 space-y-0.5">
              {changes.map((c) => (
                <li key={c.entry_id}>
                  {`${shortDate(c.date)} ${clock(c.old_start)}–${clock(c.old_end)} → ${clock(c.new_start)}–${clock(c.new_end)} (${hm(c.old_net)} h → ${hm(c.new_net)} h)`}
                </li>
              ))}
              {skipped.map((s) => (
                <li key={s.entry_id}>{`${shortDate(s.date)} übersprungen: ${SKIP_LABELS[s.reason] ?? s.reason}`}</li>
              ))}
              {reductions.map((r) => (
                <li key={r.absence_id}>{`Gutschrift ${shortDate(r.date)}: ${hm(r.old_hours)} h → ${hm(r.new_hours)} h`}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Test, Typprüfung, Lint — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/WhImpactBox.test.tsx --pool=threads`, dann `npx tsc --noEmit` und `npx eslint src/pages/admin/users/WhImpactBox.tsx`
Expected: PASS, `tsc` ohne Ausgabe, eslint `0 errors`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/users/WhImpactBox.tsx frontend/src/pages/admin/users/WhImpactBox.test.tsx
git commit -F - <<'EOF'
feat(bloecke): Auswirkungs-Box der Arbeitszeit-Änderung (WhImpactBox)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 18b: WorkingHoursModal — Block-Modus, POST-Vorschau, Altfenster (Spec 4.3, 4.4, 9.4, 11.1, 11.3, 12.1, P2, P9, P24)

**Files:**
- Modify (komplett ersetzen): `frontend/src/pages/admin/users/WorkingHoursModal.tsx`
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.test.tsx` (Mock-Kopf, Fixture-Typen, Wortlaute; neuer `describe`-Block am Dateiende)

**Interfaces:**
- Consumes: `WhImpactBox({ preview })` (Task 18a, gerendert in der Auswirkungs-Box des Dialogs); `WorkBlocksEditor` (Task 17); `deriveTargets`, `emptyWeek`, `validateWeekBlocks` (Task 16), `formatBlocksText` (Task 14), `isLegacyWeek`, `WEEKDAY_LABELS` (PR1); `WorkingHoursChange`, `WorkingHoursChangePreview`, `LEGAL_HINT`, `JARBSCHG_HINT`, `LEGACY_BOX_TITLE`, `BLOCKS_WITHOUT_EFFECT`, `modeSwitchHint`, `SKIP_LABELS`, `formatDate`, `shortDate`, `monthLabel`, `hm`, `signedHm`, `signedDays`, `savedMessage` (Task 16); `showResponseWarning` (Bestand, `utils/arbzgWarnings.ts`); `POST …/working-hours-changes/preview` (Task 10), Anlege-Body (Task 9)
- Produces:
  - `WorkingHoursModal`-Props zusätzlich `currentBlocks?: WeekBlocks | null`, `trackHours?: boolean` (Vorgabe `true`)
  - Im Modul (für Task 19/20): `type Mode = 'even' | 'days' | 'blocks'`, `interface ScheduleSnapshot { …; blocks: WeekBlocks | null }`, `formFromSnapshot(s, effectiveFrom, trackHours): FormState`, `comparableSnapshot(s, withBlocks): string`, `dayBefore(iso)`, `todayIso()`; im Komponentenrumpf die Namen `previewKey`, `scheduleBody`, `sentDate`, `shown`, `shownLoading`, `shownError`, `saveDisabled`

Zielbild (Spec 12.1): Modus „Gleichmäßig / Nach Tagen / Nach Arbeitsblöcken" (dritter nur bei Stundenzählung), Block-Editor, Rechtshinweise fest darunter, Plan-Hinweise aus der Vorschau, Altfenster-Kasten mit „In Arbeitszeit-Blöcke umwandeln" / „Fenster entfernen", Hinweis beim Moduswechsel weg von Blöcken, Vorschau per `POST` mit Effekt-Schlüssel `JSON.stringify(body)`, Bestätigungspflicht zusätzlich bei `affected_time_entries > 0` (auch bei Wirkungsdatum heute), Knopf „Speichern", Toast „Gespeichert. …" plus `warning`. Die Bestätigungsregeln aus 1.17.0/#431 (rückwirkend, gebuchte Abwesenheiten, Saldo-/Urlaubswirkung) bleiben — 9.4 **ergänzt** einen Auslöser, nimmt keinen weg. Der Lösch-Ablauf bleibt in diesem Task unverändert (Task 20 ersetzt ihn); die Verkürzungs-Wahl kommt in Task 19 — bis dahin antwortet ein Speichern mit Verkürzung mit dem 400 aus Task 9 (Fehler-Toast).

- [ ] **Step 1: Bestandstests umstellen (Mock-Kopf, Typen, Wortlaute)**

In `frontend/src/pages/admin/users/WorkingHoursModal.test.tsx`:

Den Block von `const getMock = vi.fn();` bis einschließlich der schließenden `}));` des `vi.mock('../../../api/client', …)` ersetzen durch:

```ts
const getMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
const deletePreviewMock = vi.fn();
// Spec 11.1: die Vorschau ist seit PR3 ein POST mit JSON-Body. Die Bestandstests
// prüfen weiterhin `getMock`-Aufrufe mit `params` — der Body wird dafür als
// `params` durchgereicht; `transport` hält fest, was WIRKLICH gesendet wurde.
const transport: { method: string; url: string; body?: unknown }[] = [];
vi.mock('../../../api/client', () => ({
  default: {
    get: (url: string, config?: unknown) => {
      transport.push({ method: 'get', url });
      return getMock(url, config);
    },
    post: (url: string, body?: unknown) => {
      transport.push({ method: 'post', url, body });
      if (String(url).includes('/delete-preview')) return deletePreviewMock(url, body);
      if (String(url).includes('/preview')) return getMock(url, { params: body });
      return postMock(url, body);
    },
    delete: (...a: unknown[]) => deleteMock(...a),
  },
}));
```

Den Typ `HistoryRow` um `blocks?: WeekBlocks | null;` erweitern, den kompletten `type PreviewOverrides = Partial<{ … }>;` ersetzen durch `type PreviewOverrides = Partial<WorkingHoursChangePreview>;` und nach `import WorkingHoursModal from './WorkingHoursModal';` ergänzen:

```ts
import type { WorkingHoursChangePreview } from './workingHoursTypes';
import type { WeekBlocks } from '../../../types/workBlocks';
import { JARBSCHG_HINT, LEGACY_BOX_TITLE, LEGAL_HINT } from './workingHoursTexts';
```

Im `beforeEach` nach `deleteMock.mockReset().mockResolvedValue({});`:

```ts
  transport.length = 0;
  deletePreviewMock.mockReset().mockResolvedValue(previewResponse({
    is_retroactive: false, affected_absences: 0, is_shortening: false, reset_body: null,
  }));
```

Wortlaute (Knopf „Speichern", Toast 12.1, Stunden in H:MM laut 12.1-Beispiel) — aus `frontend/`:

```bash
sed -i \
  -e 's/Hinzufügen/Speichern/g' \
  -e 's#/erfolgreich hinzugefügt/#/Gespeichert/#' \
  -e 's#/3 Abwesenheit\\(en\\) auf das neue Tagessoll umgerechnet/#/Gespeichert\\. 3 Abwesenheiten angepasst\\./#' \
  -e 's#/−47,5/#/−47:30/#' \
  -e "s#'−4,0 h'#'−4:00 h'#" \
  src/pages/admin/users/WorkingHoursModal.test.tsx
grep -c "Hinzufügen\|erfolgreich hinzugefügt\|−47,5\|'−4,0 h'\|auf das neue Tagessoll umgerechnet" src/pages/admin/users/WorkingHoursModal.test.tsx
```

Expected: `0`. Die Lösch-Tests (`describe('Löschen einer Stundenänderung'`) bleiben in diesem Task unverändert.

- [ ] **Step 2: Neue Failing tests**

An `WorkingHoursModal.test.tsx` anhängen:

```tsx
const day = (blocks: [string, string][], pause: number | null = 0) => ({
  blocks: blocks.map(([start, end]) => ({ start, end })), pause_minutes: pause,
});
const NONE = { blocks: [], pause_minutes: 0 };
// Spec 12.1: Anna Beispiel — Mo 08–12 + 15–18, Di 08–12, Do 08–12.
const ANNA_BLOCKS: WeekBlocks = [day([['08:00', '12:00'], ['15:00', '18:00']]), day([['08:00', '12:00']]), NONE,
  day([['08:00', '12:00']]), NONE];
const ANNA_ROW = {
  id: 'c-anna', effective_from: '2026-03-01', weekly_hours: 15, use_daily_schedule: true,
  hours_monday: 7, hours_tuesday: 4, hours_wednesday: 0, hours_thursday: 4, hours_friday: 0,
  work_days_per_week: 3, blocks: ANNA_BLOCKS,
};
const ANNA_PROPS = {
  currentWeeklyHours: 15, currentUseDailySchedule: true, currentDayHours: [7, 4, 0, 4, 0],
  currentWorkDays: 3, currentBlocks: ANNA_BLOCKS,
};
// Spec 4.4: Altzeile aus Migration 073 — Pausen NULL, Altwerte unverändert.
const LEGACY_DAY = (blocks: [string, string][]) => day(blocks, null);
const LEGACY_BLOCKS: WeekBlocks = [LEGACY_DAY([['07:37', '16:30']]), LEGACY_DAY([]), LEGACY_DAY([]), LEGACY_DAY([]),
  LEGACY_DAY([['07:30', '23:59']])];
const LEGACY_ROW = { id: 'c-legacy', effective_from: '2026-01-01', weekly_hours: 40, blocks: LEGACY_BLOCKS };

function mockHistory(rows: Array<HistoryRow>, overrides: PreviewOverrides = {}) {
  getMock.mockImplementation((url: string) => {
    if (String(url).includes('/preview')) return Promise.resolve(previewResponse(overrides));
    return Promise.resolve(historyResponse(rows));
  });
}
const QUIET: PreviewOverrides = { is_retroactive: false, affected_absences: 0, period_start: '2026-07-26', period_end: '2026-07-26' };
const previewPosts = () => transport.filter((t) => t.method === 'post' && t.url.endsWith('/working-hours-changes/preview'));

describe('Spec 2026-10-08 (PR3): Block-Modus und POST-Vorschau', () => {
  it('öffnet mit heute gültigen Blöcken im Block-Modus und meldet „nichts zu speichern"', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    expect(screen.getByRole('heading', { name: 'Arbeitszeit & Wochenstunden' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' })).toBeChecked();
    expect(screen.getByLabelText('Mo Block 2 bis')).toHaveValue('18:00');
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
  });

  it('Review Focus 5: 7:55 h bleibt nach dem Speichern als 7,92 h ohne Scheinunterschied', async () => {
    const blocks: WeekBlocks = [day([['07:30', '12:00'], ['13:00', '16:25']]), NONE, NONE, NONE, NONE];
    mockHistory([{
      id: 'c1', effective_from: '2026-03-01', weekly_hours: 7.92, use_daily_schedule: true,
      hours_monday: 7.92, hours_tuesday: 0, hours_wednesday: 0, hours_thursday: 0, hours_friday: 0,
      work_days_per_week: 1, blocks,
    }], QUIET);
    renderModal({
      currentWeeklyHours: 7.92, currentUseDailySchedule: true, currentDayHours: [7.92, 0, 0, 0, 0],
      currentWorkDays: 1, currentBlocks: blocks,
    });
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    expect(screen.getByTestId('wh-blocks-day-0')).toHaveTextContent('Tagessoll 7:55 h');
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
  });

  it('Vorschau und Speichern senden nur die Blöcke — per POST mit JSON-Body, nie als Query', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '17:00' } });
    await flushDebounce();

    await waitFor(() => {
      const body = previewPosts().at(-1)?.body as Record<string, unknown>;
      expect(body.effective_from).toBe('2026-07-26');
      expect((body.blocks as WeekBlocks)[0].blocks[1]).toEqual({ start: '15:00', end: '17:00' });
      for (const key of ['weekly_hours', 'use_daily_schedule', 'work_days_per_week', 'hours_monday']) {
        expect(body).not.toHaveProperty(key);
      }
    });
    expect(transport.some((t) => t.method === 'get' && t.url.includes('/preview'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const [url, body] = postMock.mock.calls.at(-1)!;
    expect(url).toBe('/admin/users/u1/working-hours-changes');
    expect(body).toMatchObject({ effective_from: '2026-07-26', note: '' });
    expect((body as { blocks: WeekBlocks }).blocks[0].blocks[1].end).toBe('17:00');
    expect(body).not.toHaveProperty('weekly_hours');
  });

  it('stabiler Effekt-Schlüssel: eine Vorschau je Eingabepause, Notiz und gleicher Wert lösen keine aus', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    await flushDebounce();
    expect(previewPosts()).toHaveLength(1);

    fireEvent.change(screen.getByLabelText('Notiz (optional)'), { target: { value: 'Umstellung' } });
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '18:00' } });
    await flushDebounce();
    expect(previewPosts()).toHaveLength(1);

    fireEvent.change(screen.getByLabelText('Mo Block 2 von'), { target: { value: '14:30' } });
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '17:30' } });
    await flushDebounce();
    expect(previewPosts()).toHaveLength(2);
  });

  it('Review Focus 1: unfertige Eingabe → blocked_reason aus der Vorschau, Speichern gesperrt, kein Haken', async () => {
    mockHistory([ANNA_ROW], { ...QUIET, blocked_reason: 'Mo, Block 3: Uhrzeit im Format HH:MM angeben.' });
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText('Mo, Block 3: Uhrzeit im Format HH:MM angeben.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Mo, Block 3: Uhrzeit im Format HH:MM angeben.');
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('Bestätigung Pflicht bei affected_time_entries > 0 — Wirkungsdatum heute', async () => {
    mockPreview({ ...QUIET, affected_time_entries: 2 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText(/Betrifft bereits erfasste Zeiteinträge/)).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: /Speichern/ });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /Auswirkungen geprüft/ }));
    expect(submit).not.toBeDisabled();
  });

  it('Bestätigung Pflicht bei affected_time_entries > 0 — Wirkungsdatum in der Vergangenheit', async () => {
    mockPreview({ affected_absences: 0, affected_time_entries: 3 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '45' } });
    await flushDebounce();

    const box = await screen.findByRole('status');
    expect(within(box).getByText(/Rückwirkende Änderung/)).toBeInTheDocument();
    expect(within(box).getByText(/Zeiteinträge: 3 neu berechnet/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /Auswirkungen geprüft/ }));
    expect(screen.getByRole('button', { name: /Speichern/ })).not.toBeDisabled();
  });

  it('kein Haken, wenn Einträge und Abwesenheiten 0 sind und Saldo/Urlaub gleich bleiben (Datum heute)', async () => {
    mockPreview({ ...QUIET, affected_time_entries: 0 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Speichern/ })).not.toBeDisabled();
  });

  it('Rechtshinweise stehen fest unter dem Editor, Plan-Hinweise kommen aus der Vorschau', async () => {
    const notice = 'Mo: geplant 10:00 h Arbeit, eingeplante Pausen 0 Min – nach § 4 ArbZG sind mindestens 45 Minuten nötig.';
    mockHistory([ANNA_ROW], { ...QUIET, block_break_notices: [notice] });
    renderModal(ANNA_PROPS);
    expect(await screen.findByText(LEGAL_HINT)).toBeInTheDocument();
    expect(screen.getByText(JARBSCHG_HINT)).toBeInTheDocument();
    await flushDebounce();
    const list = await screen.findByRole('list', { name: 'Hinweise zum Plan' });
    expect(within(list).getByText(notice)).toBeInTheDocument();
  });

  it('Moduswechsel weg von Blöcken nennt das Ende der Blöcke (P24)', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    expect(screen.queryByText(/Die Arbeitszeit-Blöcke enden/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: /Gleichmäßig/ }));
    expect(screen.getByText('Die Arbeitszeit-Blöcke enden mit dieser Änderung; ab 26.07.2026 wird nicht mehr gekappt.'))
      .toBeInTheDocument();
  });

  it('track_hours=false: kein Block-Modus, Blöcke „ohne Wirkung", jede Änderung beendet sie (P24)', async () => {
    mockHistory([ANNA_ROW], QUIET);
    renderModal({ ...ANNA_PROPS, trackHours: false });
    await screen.findByText(/Ab 01\.03\.2026 bis heute/);
    expect(screen.queryByRole('radio', { name: 'Nach Arbeitsblöcken' })).not.toBeInTheDocument();
    // Kopfzeile + Verlaufszeile
    expect(screen.getAllByText(/^Arbeitszeit-Blöcke gespeichert, ohne Wirkung \(keine Stundenzählung\): Mo 08:00/))
      .toHaveLength(2);
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Montag'), { target: { value: '8' } });
    expect(screen.getByText(/Die Arbeitszeit-Blöcke enden mit dieser Änderung/)).toBeInTheDocument();
    await flushDebounce();
    expect(previewPosts().at(-1)?.body).not.toHaveProperty('blocks');
  });

  it('Altfenster: Kasten mit Werten, „Fenster entfernen" sendet remove_legacy_window', async () => {
    mockHistory([LEGACY_ROW], QUIET);
    renderModal({ currentBlocks: LEGACY_BLOCKS });
    await screen.findByText(/Ab 01\.01\.2026 bis heute/);
    const box = screen.getByRole('group', { name: LEGACY_BOX_TITLE });
    expect(within(box).getByText('Mo 07:37–16:30 / Fr 07:30–23:59')).toBeInTheDocument();
    expect(screen.getByText(/Noch nichts zu speichern/)).toBeInTheDocument();

    fireEvent.click(within(box).getByRole('button', { name: 'Fenster entfernen' }));
    expect(within(box).getByRole('button', { name: 'Fenster behalten' })).toBeInTheDocument();
    expect(screen.queryByText(/Noch nichts zu speichern/)).not.toBeInTheDocument();
    await flushDebounce();
    expect(previewPosts().at(-1)?.body).toMatchObject({ remove_legacy_window: true, use_daily_schedule: false });
  });

  it('Review Focus 4: „In Arbeitszeit-Blöcke umwandeln" zeigt Altwerte unverändert, verlangt Raster und Pause', async () => {
    mockHistory([LEGACY_ROW], QUIET);
    renderModal({ currentBlocks: LEGACY_BLOCKS });
    await screen.findByText(/Ab 01\.01\.2026 bis heute/);
    fireEvent.click(screen.getByRole('button', { name: 'In Arbeitszeit-Blöcke umwandeln' }));

    expect(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' })).toBeChecked();
    expect(screen.getByLabelText('Mo Block 1 von')).toHaveValue('07:37');
    expect(screen.getByLabelText('Fr Block 1 bis')).toHaveValue('23:59');
    expect(screen.getByRole('alert')).toHaveTextContent('Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).');
    const submit = screen.getByRole('button', { name: /Speichern/ });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '07:35' } });
    fireEvent.change(screen.getByLabelText('Fr Block 1 bis'), { target: { value: '16:00' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Mo: Pause angeben (0, wenn keine).');
    fireEvent.change(screen.getByLabelText('Mo Pause innerhalb der Blöcke (Min)'), { target: { value: '30' } });
    fireEvent.change(screen.getByLabelText('Fr Pause innerhalb der Blöcke (Min)'), { target: { value: '0' } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await flushDebounce();
    await waitFor(() => expect(submit).not.toBeDisabled());
  });

  it('Verlauf zeigt die Blöcke jeder Zeile, Altzeilen als Altbestand', async () => {
    mockHistory([LEGACY_ROW, ANNA_ROW], QUIET);
    renderModal(ANNA_PROPS);
    expect(await screen.findByText(`${LEGACY_BOX_TITLE}: Mo 07:37–16:30 / Fr 07:30–23:59`)).toBeInTheDocument();
    expect(screen.getAllByText('Arbeitszeit-Blöcke: Mo 08:00–12:00 + 15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00'))
      .toHaveLength(2); // Kopfzeile + Verlaufszeile
  });

  it('Toast nach dem Speichern nennt Einträge, Übersprungene und Abwesenheiten (12.1)', async () => {
    mockPreview(QUIET);
    postMock.mockResolvedValue({ data: {
      id: 'c-x', adjusted_time_entries: 3, skipped_time_entries: 1, adjusted_absences: 1, warning: null,
    } });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));
    expect(await screen.findByText('Gespeichert. 3 Zeiteinträge neu berechnet, 1 übersprungen, 1 Abwesenheit angepasst.'))
      .toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/WorkingHoursModal.test.tsx --pool=threads`
Expected: FAIL — im Modal-Test scheitern die umgestellten Bestandstests (kein „Speichern"-Knopf, Vorschau noch per GET → `getMock` ohne `params`-Body) und der neue Block.

- [ ] **Step 4: `WorkingHoursModal.tsx` komplett ersetzen**

```tsx
import { useState, useEffect, useMemo } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../../api/client';
import { Save, X, Trash2, Info } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import { useConfirm } from '../../../hooks/useConfirm';
import ConfirmDialog from '../../../components/ConfirmDialog';
import WorkBlocksEditor from '../../../components/WorkBlocksEditor';
import { getErrorMessage } from '../../../utils/errorMessage';
import { parseHours, deHoursExact, formatDayPlan } from '../../../utils/formatters';
import { showResponseWarning } from '../../../utils/arbzgWarnings';
import {
  deriveTargets, emptyWeek, formatBlocksText, isLegacyWeek, validateWeekBlocks,
} from '../../../utils/workBlocks';
import type { WeekBlocks } from '../../../types/workBlocks';
import type { WorkingHoursChange, WorkingHoursChangePreview } from './workingHoursTypes';
import WhImpactBox from './WhImpactBox';
import {
  BLOCKS_WITHOUT_EFFECT, JARBSCHG_HINT, LEGACY_BOX_TITLE, LEGAL_HINT, formatDate, modeSwitchHint, savedMessage,
} from './workingHoursTexts';

interface WorkingHoursModalProps {
  userId: string;
  userName: string;
  currentWeeklyHours: number;
  // #431: der Rest des aktuell gueltigen Snapshots — nur RUECKFALL, solange
  // der Verlauf nicht geladen ist (siehe `scheduleAt`).
  currentUseDailySchedule?: boolean;
  currentDayHours?: (number | null)[];
  currentWorkDays?: number;
  // Spec 2026-10-08 (12.1): heute gültige Blöcke (`work_blocks_today`) — ebenfalls
  // nur Rückfall — und die Stundenzählung (ohne sie kein Block-Modus, P24).
  currentBlocks?: WeekBlocks | null;
  trackHours?: boolean;
  onClose: () => void;
  onChanged: () => void;
}

// #431: Die fuenf Wochentagsfelder an EINER Stelle — Feldname (= API-Feld),
// Beschriftung des Eingabefelds und Kurzform.
const DAY_FIELDS = [
  { key: 'hours_monday', label: 'Montag', short: 'Mo' },
  { key: 'hours_tuesday', label: 'Dienstag', short: 'Di' },
  { key: 'hours_wednesday', label: 'Mittwoch', short: 'Mi' },
  { key: 'hours_thursday', label: 'Donnerstag', short: 'Do' },
  { key: 'hours_friday', label: 'Freitag', short: 'Fr' },
] as const;

type DayFieldKey = typeof DAY_FIELDS[number]['key'];

const NO_DAY_HOURS: (number | null)[] = [null, null, null, null, null];

/** Spec 12.1: „Gleichmäßig" / „Nach Tagen" / „Nach Arbeitsblöcken". */
type Mode = 'even' | 'days' | 'blocks';

/** #431 + Spec 3.1: der Vertrags-Snapshot, wie ihn Dialog und Backend sehen. */
interface ScheduleSnapshot {
  weekly_hours: number;
  use_daily_schedule: boolean;
  /** Fünf Werte, Index 0 = Montag. 0 = kein geplanter Arbeitstag. */
  day_hours: number[];
  work_days_per_week: number;
  /** Blöcke der Zeile — neu (mit Pausen) oder Altfenster (Pausen NULL) — oder `null`. */
  blocks: WeekBlocks | null;
}

interface FormState {
  effective_from: string;
  mode: Mode;
  weekly_hours: number;
  hours_monday: number;
  hours_tuesday: number;
  hours_wednesday: number;
  hours_thursday: number;
  hours_friday: number;
  work_days_per_week: number;
  blocks: WeekBlocks;
  /** P2: Altfenster ausdrücklich entfernen statt übernehmen. */
  remove_legacy_window: boolean;
  note: string;
}

function round2(value: number): number {
  return Number.isFinite(value) ? Math.round(value * 100) / 100 : 0;
}

function normaliseDayHours(values: (number | null | undefined)[]): number[] {
  return DAY_FIELDS.map((_, i) => {
    const v = values[i];
    return typeof v === 'number' && Number.isFinite(v) ? v : 0;
  });
}

function dayFieldsFromSnapshot(dayHours: number[]): Record<DayFieldKey, number> {
  return {
    hours_monday: dayHours[0],
    hours_tuesday: dayHours[1],
    hours_wednesday: dayHours[2],
    hours_thursday: dayHours[3],
    hours_friday: dayHours[4],
  };
}

function hasNewBlocks(week: WeekBlocks | null): boolean {
  return Array.isArray(week) && !isLegacyWeek(week);
}

function hasLegacyBlocks(week: WeekBlocks | null): boolean {
  return Array.isArray(week) && isLegacyWeek(week);
}

function scheduleFromChange(change: WorkingHoursChange, fallbackWorkDays: number): ScheduleSnapshot {
  return {
    weekly_hours: change.weekly_hours,
    use_daily_schedule: !!change.use_daily_schedule,
    day_hours: normaliseDayHours([
      change.hours_monday, change.hours_tuesday, change.hours_wednesday,
      change.hours_thursday, change.hours_friday,
    ]),
    work_days_per_week: change.work_days_per_week ?? fallbackWorkDays,
    blocks: Array.isArray(change.blocks) ? change.blocks : null,
  };
}

// Fund 3 (Release-Review 1.17.0), #431: der zu einem Datum gültige Snapshot
// kommt aus dem geladenen Verlauf (jüngste Zeile mit effective_from <= datum),
// nicht aus den Props — wie `calculation_service.get_schedule_for_date`.
function scheduleAt(
  changes: WorkingHoursChange[], iso: string, fallback: ScheduleSnapshot,
): ScheduleSnapshot {
  let latest: WorkingHoursChange | null = null;
  for (const c of changes) {
    if (c.effective_from <= iso && (!latest || c.effective_from > latest.effective_from)) {
      latest = c;
    }
  }
  return latest ? scheduleFromChange(latest, fallback.work_days_per_week) : fallback;
}

/** #431: Snapshot als Klartext — wortgleich zum Datei-Export. */
function describeSchedule(s: ScheduleSnapshot): string {
  const days = `${s.work_days_per_week} Tage/Woche`;
  if (s.use_daily_schedule) {
    const plan = formatDayPlan(s.day_hours);
    if (plan) return `${plan} = ${deHoursExact(s.weekly_hours)} Std/Woche · ${days}`;
  }
  return `${deHoursExact(s.weekly_hours)} Std/Woche · ${days}`;
}

/** Blockzeile für Kopf und Verlauf (Spec 12.1/4.4). */
function blocksLine(week: WeekBlocks | null, trackHours: boolean): string | null {
  const text = formatBlocksText(week);
  if (!text) return null;
  if (!trackHours) return `${BLOCKS_WITHOUT_EFFECT}: ${text}`;
  return hasLegacyBlocks(week) ? `${LEGACY_BOX_TITLE}: ${text}` : `Arbeitszeit-Blöcke: ${text}`;
}

/** Kanonische Vergleichsform der Blöcke (Schlüsselreihenfolge egal). */
function blocksKey(week: WeekBlocks | null): string | null {
  if (!Array.isArray(week)) return null;
  return JSON.stringify(week.map((d) => [d.blocks.map((b) => [b.start, b.end]), d.pause_minutes]));
}

/**
 * #431 + Spec 12.1: DIE Definition von „hat sich etwas geändert" — wie
 * `admin_users._comparable_snapshot`, jetzt mit Blöcken und Pausen. Ohne
 * Stundenzählung zählen die Blöcke nicht (sie wirken nicht; beendet werden sie
 * von jeder echten Änderung, P24).
 */
function comparableSnapshot(s: ScheduleSnapshot, withBlocks: boolean): string {
  return JSON.stringify([
    round2(s.weekly_hours),
    s.use_daily_schedule,
    s.use_daily_schedule ? s.day_hours.map(round2) : [0, 0, 0, 0, 0],
    s.work_days_per_week,
    withBlocks ? blocksKey(s.blocks) : null,
  ]);
}

/** Formularstand aus einem Snapshot: Block-Modus, sobald neue Blöcke gelten. */
function formFromSnapshot(s: ScheduleSnapshot, effectiveFrom: string, trackHours: boolean): FormState {
  const blocksMode = trackHours && hasNewBlocks(s.blocks);
  return {
    effective_from: effectiveFrom,
    mode: blocksMode ? 'blocks' : s.use_daily_schedule ? 'days' : 'even',
    weekly_hours: s.weekly_hours,
    ...dayFieldsFromSnapshot(s.day_hours),
    work_days_per_week: s.work_days_per_week,
    blocks: blocksMode && s.blocks ? s.blocks : emptyWeek(),
    remove_legacy_window: false,
    note: '',
  };
}

/** Spec 4.4: Altfenster vorbefüllt in den Block-Modus — Werte unverändert
 * (07:37, 23:59), Pause leer und Pflicht an Tagen mit Blöcken. */
function legacyToEditable(week: WeekBlocks): WeekBlocks {
  return week.map((d) => ({
    blocks: d.blocks.map((b) => ({ start: b.start.slice(0, 5), end: b.end.slice(0, 5) })),
    pause_minutes: d.blocks.length ? null : 0,
  }));
}

// Kalendertag VOR dem ISO-Datum — UTC-basiert (reine Tagesarithmetik).
function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().split('T')[0];
}

// M1 (Abschluss-Review): „heute" in der LOKALEN Zeitzone, nicht `toISOString()`
// (UTC) — sonst hält der Dialog zwischen 00:00 und 02:00 das gestrige Datum für
// „heute" und umgeht die Bestätigungspflicht.
function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const PREVIEW_DEBOUNCE_MS = 400;

export default function WorkingHoursModal({
  userId,
  userName,
  currentWeeklyHours,
  currentUseDailySchedule = false,
  currentDayHours = NO_DAY_HOURS,
  currentWorkDays = 5,
  currentBlocks = null,
  trackHours = true,
  onClose,
  onChanged,
}: WorkingHoursModalProps) {
  const toast = useToast();
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();
  const [hoursChanges, setHoursChanges] = useState<WorkingHoursChange[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const propsSchedule = useMemo<ScheduleSnapshot>(() => ({
    weekly_hours: currentWeeklyHours,
    use_daily_schedule: currentUseDailySchedule,
    day_hours: normaliseDayHours(currentDayHours),
    work_days_per_week: currentWorkDays,
    blocks: currentBlocks,
  }), [currentWeeklyHours, currentUseDailySchedule, currentDayHours, currentWorkDays, currentBlocks]);

  const [formData, setFormData] = useState<FormState>(() => formFromSnapshot(propsSchedule, todayIso(), trackHours));

  const [preview, setPreview] = useState<WorkingHoursChangePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  // Fund 4 (1.17.0): ein Vorschau-Fehler wird angezeigt, mit „Erneut prüfen".
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewRetryToken, setPreviewRetryToken] = useState(0);
  const [confirmedRetroactive, setConfirmedRetroactive] = useState(false);

  const dayValues = DAY_FIELDS.map((f) => formData[f.key]);
  const daySum = round2(dayValues.reduce((sum, h) => sum + h, 0));
  const plannedDays = dayValues.filter((h) => h > 0).length;
  const derived = useMemo(() => deriveTargets(formData.blocks), [formData.blocks]);
  const blocksError = formData.mode === 'blocks' ? validateWeekBlocks(formData.blocks) : null;

  const displaySchedule = useMemo(
    () => scheduleAt(hoursChanges, todayIso(), propsSchedule),
    [hoursChanges, propsSchedule],
  );
  // Verglichen wird gegen den Stand AM WIRKUNGSDATUM (#431).
  const baselineSchedule = scheduleAt(hoursChanges, formData.effective_from, propsSchedule);
  const baselineLegacy = hasLegacyBlocks(baselineSchedule.blocks);
  const baselineNewBlocks = hasNewBlocks(baselineSchedule.blocks);
  // P2: ein Altfenster wird in „Gleichmäßig"/„Nach Tagen" übernommen, außer
  // es wird ausdrücklich entfernt.
  const removeLegacy = baselineLegacy && formData.remove_legacy_window;
  const carriedBlocks = baselineLegacy && !formData.remove_legacy_window ? baselineSchedule.blocks : null;

  // #431 + Spec 11.1/11.2: Vorschau-Body UND Anlege-Body aus DERSELBEN Quelle.
  // Block-Modus sendet nur `blocks` — Stundenwerte daneben weist der Server mit
  // 422 ab (er leitet sie selbst ab, 4.2).
  const scheduleBody: Record<string, unknown> = (() => {
    if (formData.mode === 'blocks') return { blocks: formData.blocks };
    const legacy = removeLegacy ? { remove_legacy_window: true } : {};
    if (formData.mode === 'days') {
      const body: Record<string, unknown> = { use_daily_schedule: true, ...legacy };
      DAY_FIELDS.forEach((f, i) => { body[f.key] = dayValues[i]; });
      // Wochensumme setzt der Server (`check_mode`); Arbeitstage = Tage mit Stunden.
      if (plannedDays > 0) body.work_days_per_week = plannedDays;
      return body;
    }
    return {
      use_daily_schedule: false,
      weekly_hours: formData.weekly_hours,
      work_days_per_week: formData.work_days_per_week,
      ...legacy,
    };
  })();
  // Spec 12.1: der Effekt-Schlüssel ist der serialisierte Body — ein String,
  // also stabil über Renderläufe (sonst Anfragesturm).
  const previewKey = JSON.stringify({ effective_from: formData.effective_from, ...scheduleBody });

  useEffect(() => {
    fetchHoursChanges();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // Vorschau für JEDES Wirkungsdatum (Release-Review 1.17.0), jetzt per POST
  // (Spec 11.1). Fund 1: `cancelled` verwirft verspätete Antworten.
  useEffect(() => {
    setConfirmedRetroactive(false);
    setPreviewLoading(true);
    setPreviewError(null);
    let cancelled = false;
    const handle = setTimeout(() => {
      apiClient
        .post(`/admin/users/${userId}/working-hours-changes/preview`, JSON.parse(previewKey))
        .then((res) => {
          if (!cancelled) setPreview(res.data);
        })
        .catch((error) => {
          if (cancelled) return;
          setPreview(null);
          setPreviewError(getErrorMessage(error, 'Auswirkungen konnten nicht geprüft werden'));
        })
        .finally(() => {
          if (!cancelled) setPreviewLoading(false);
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [userId, previewKey, previewRetryToken]);

  const fetchHoursChanges = async (): Promise<WorkingHoursChange[]> => {
    try {
      const response = await apiClient.get(`/admin/users/${userId}/working-hours-changes`);
      const list: WorkingHoursChange[] = Array.isArray(response.data) ? response.data : []; // #382
      setHoursChanges(list);
      return list;
    } catch (error) {
      toast.error('Fehler beim Laden der Stundenhistorie');
      return hoursChanges;
    }
  };

  const historyEndDates = useMemo(() => {
    const asc = [...hoursChanges].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
    const map = new Map<string, string | null>();
    asc.forEach((c, idx) => {
      const next = asc[idx + 1];
      map.set(c.id, next ? dayBefore(next.effective_from) : null);
    });
    return map;
  }, [hoursChanges]);

  // I4: die früheste Zeile ist gesperrt, solange spätere existieren.
  const lockedEarliestId = useMemo(() => {
    if (hoursChanges.length < 2) return null;
    const asc = [...hoursChanges].sort((a, b) => a.effective_from.localeCompare(b.effective_from));
    return asc[0].id;
  }, [hoursChanges]);

  const LOCKED_EARLIEST_HINT =
    'Die früheste erfasste Stundenänderung verankert den davor gültigen Wert — '
    + 'bitte zuerst die späteren Änderungen löschen.';

  // Was gesendet wird und was die Auswirkungs-Box zeigt.
  const sentDate = formData.effective_from;
  const shown: WorkingHoursChangePreview | null = preview;
  const shownLoading = previewLoading;
  const shownError = previewError;
  const isRetroactive = sentDate < todayIso();

  const blockedReason = shown?.blocked_reason ?? null;
  const affectsBookedAbsences = !!shown && !blockedReason && shown.affected_absences > 0;
  // Spec 9.4/12.1: neu gekappte Einträge verlangen die Bestätigung — auch ab heute.
  const affectsEntries = !!shown && !blockedReason && (shown.affected_time_entries ?? 0) > 0;
  const overtimeDelta = shown ? round2(shown.overtime_after - shown.overtime_before) : 0;
  const vacationDelta = shown ? round2(shown.vacation_days_after - shown.vacation_days_before) : 0;
  // Abschluss-Review #431, Fund 2: eine reine Saldo-/Urlaubswirkung zählt mit.
  const affectsBalance = !!shown && !blockedReason && (overtimeDelta !== 0 || vacationDelta !== 0);
  const needsConfirmation = affectsEntries || affectsBookedAbsences || affectsBalance;
  const showImpactBox = isRetroactive || needsConfirmation || !!blockedReason;

  const inputSchedule: ScheduleSnapshot = formData.mode === 'blocks'
    ? {
      weekly_hours: derived.weeklyHours,
      use_daily_schedule: true,
      day_hours: derived.hours,
      work_days_per_week: derived.workDays || formData.work_days_per_week,
      blocks: formData.blocks,
    }
    : {
      weekly_hours: formData.mode === 'days' ? daySum : formData.weekly_hours,
      use_daily_schedule: formData.mode === 'days',
      day_hours: dayValues,
      work_days_per_week: formData.mode === 'days'
        ? (plannedDays || formData.work_days_per_week)
        : formData.work_days_per_week,
      blocks: carriedBlocks,
    };
  const snapshotUnchanged =
    comparableSnapshot(inputSchedule, trackHours) === comparableSnapshot(baselineSchedule, trackHours);

  // Rückwirkend: Vorschau muss da und bestätigt sein. Ab heute sperrt nur ein
  // positiver Befund (fällt die Vorschau aus, bleibt Speichern möglich).
  const saveDisabled =
    submitting ||
    !!blockedReason ||
    !!blocksError ||
    snapshotUnchanged ||
    (isRetroactive && (shownLoading || !shown || !confirmedRetroactive)) ||
    (!isRetroactive && needsConfirmation && !confirmedRetroactive);

  const setDayHours = (key: DayFieldKey, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: parseHours(value) }));
  };

  const handleAddHoursChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saveDisabled) return;
    setSubmitting(true);
    try {
      const res = await apiClient.post(`/admin/users/${userId}/working-hours-changes`, {
        effective_from: sentDate,
        note: formData.note,
        ...scheduleBody,
      });
      const freshChanges = await fetchHoursChanges();
      onChanged();
      // Fund 3: Formular aus dem frisch geladenen Verlauf, nicht aus den Props.
      setFormData(formFromSnapshot(scheduleAt(freshChanges, todayIso(), propsSchedule), todayIso(), trackHours));
      setPreview(null);
      setConfirmedRetroactive(false);
      const created: {
        adjusted_time_entries?: number; skipped_time_entries?: number; adjusted_absences?: number;
        warning?: string | null;
      } = res.data ?? {};
      toast.success(savedMessage(created));
      showResponseWarning(toast, created);
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Fehler beim Speichern'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteHoursChange = (changeId: string) => {
    confirm({
      title: 'Stundenänderung löschen',
      message: 'Möchten Sie diese Stundenänderung wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
      onConfirm: async () => {
        try {
          const res = await apiClient.delete(`/admin/users/${userId}/working-hours-changes/${changeId}`);
          await fetchHoursChanges();
          onChanged();
          toast.success('Stundenänderung erfolgreich gelöscht');
          const body = res?.data;
          const warning = body && typeof body === 'object' ? (body as { warning?: string }).warning : undefined;
          if (warning) {
            toast.warning(warning);
          }
        } catch (error: unknown) {
          toast.error(getErrorMessage(error, 'Fehler beim Löschen der Stundenänderung'));
        }
      },
    });
  };

  const balanceUnchangedAhead =
    !!shown && !isRetroactive && overtimeDelta === 0 && vacationDelta === 0;
  const displayBlocksLine = blocksLine(displaySchedule.blocks, trackHours);
  const planNotices = preview?.block_break_notices ?? [];

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
      <div
        className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
        onClick={onClose}
      >
        <FocusTrap
          focusTrapOptions={{
            allowOutsideClick: true,
            escapeDeactivates: true,
            onDeactivate: onClose,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="hours-modal-title"
            className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 z-10 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 id="hours-modal-title" className="text-2xl font-bold text-gray-900">
                  Arbeitszeit &amp; Wochenstunden
                </h2>
                <p className="text-sm text-gray-600 mt-1">
                  {userName} • Aktuell: {describeSchedule(displaySchedule)}
                </p>
                {displayBlocksLine && <p className="text-sm text-gray-600">{displayBlocksLine}</p>}
              </div>
              <button
                onClick={onClose}
                className="text-gray-500 hover:text-gray-700"
                aria-label={`Arbeitszeit & Wochenstunden für ${userName} schließen`}
              >
                <X size={24} />
              </button>
            </div>

            <div className="p-6">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <h3 className="font-semibold text-blue-900 mb-3">Neue Änderung</h3>
                <form onSubmit={handleAddHoursChange} className="space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <label htmlFor="wh-effective-from" className="block text-sm font-medium text-gray-700 mb-1">
                        Gültig ab
                      </label>
                      <input
                        id="wh-effective-from"
                        type="date"
                        value={formData.effective_from}
                        onChange={(e) => setFormData({ ...formData, effective_from: e.target.value })}
                        required
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label htmlFor="wh-note" className="block text-sm font-medium text-gray-700 mb-1">
                        Notiz (optional)
                      </label>
                      <input
                        id="wh-note"
                        type="text"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="z.B. Teilzeitänderung"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                      />
                    </div>
                  </div>

                  <fieldset className="border border-blue-200 rounded-lg p-3 bg-white">
                    <legend className="px-1 text-sm font-medium text-gray-700">Ab diesem Datum gilt</legend>
                    <div className="flex flex-wrap gap-4 mb-3">
                      {([
                        ['even', 'Gleichmäßig'],
                        ['days', 'Nach Tagen'],
                        ...(trackHours ? [['blocks', 'Nach Arbeitsblöcken']] : []),
                      ] as [Mode, string][]).map(([value, label]) => (
                        <label key={value} className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer">
                          <input
                            type="radio"
                            name="wh-mode"
                            checked={formData.mode === value}
                            onChange={() => setFormData((prev) => ({ ...prev, mode: value }))}
                            className="w-4 h-4 text-primary border-gray-300 focus:ring-primary"
                          />
                          {label}
                        </label>
                      ))}
                    </div>

                    {formData.mode === 'blocks' ? (
                      <WorkBlocksEditor
                        value={formData.blocks}
                        onChange={(blocks) => setFormData((prev) => ({ ...prev, blocks }))}
                        idPrefix="wh-blocks"
                      />
                    ) : formData.mode === 'days' ? (
                      <div className="grid grid-cols-5 gap-2">
                        {DAY_FIELDS.map((f) => (
                          <div key={f.key}>
                            <label htmlFor={`wh-${f.key}`} className="block text-xs font-medium text-gray-600 mb-1">
                              {f.label}
                            </label>
                            <input
                              id={`wh-${f.key}`}
                              type="number"
                              // Fund C (#431): Viertelstunden wie im Anlegeformular.
                              step="0.25"
                              min="0"
                              max="24"
                              value={formData[f.key]}
                              onChange={(e) => setDayHours(f.key, e.target.value)}
                              className="w-full px-2 py-1 text-center border border-gray-300 rounded-sm focus:ring-2 focus:ring-primary text-sm"
                            />
                          </div>
                        ))}
                        <p className="col-span-5 text-sm text-gray-700 mt-1">
                          → {deHoursExact(daySum)} h/Woche · {plannedDays}{' '}
                          {plannedDays === 1 ? 'Arbeitstag' : 'Arbeitstage'}
                        </p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <label htmlFor="wh-weekly-hours" className="block text-sm font-medium text-gray-700 mb-1">
                            Wochenstunden
                          </label>
                          <input
                            id="wh-weekly-hours"
                            type="number"
                            step="0.25"
                            value={formData.weekly_hours}
                            onChange={(e) => setFormData({ ...formData, weekly_hours: parseHours(e.target.value) })}
                            required
                            min="0"
                            max="60"
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                          />
                        </div>
                        <div>
                          <label htmlFor="wh-work-days" className="block text-sm font-medium text-gray-700 mb-1">
                            Arbeitstage pro Woche
                          </label>
                          <input
                            id="wh-work-days"
                            type="number"
                            step="1"
                            min="1"
                            max="7"
                            value={formData.work_days_per_week}
                            onChange={(e) => setFormData({
                              ...formData,
                              work_days_per_week: Math.round(parseHours(e.target.value)),
                            })}
                            required
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                          />
                        </div>
                      </div>
                    )}
                  </fieldset>

                  {/* Spec 4.4: Altfenster — Aktionen „umwandeln" / „entfernen". */}
                  {baselineLegacy && formData.mode !== 'blocks' && (
                    <div
                      role="group"
                      aria-labelledby="wh-legacy-title"
                      className="rounded-lg border border-gray-300 bg-gray-50 p-3 text-sm"
                    >
                      <p id="wh-legacy-title" className="font-medium text-gray-800">{LEGACY_BOX_TITLE}</p>
                      <p className="text-gray-700 mt-1">{formatBlocksText(baselineSchedule.blocks)}</p>
                      <p className="text-gray-600 mt-1">
                        {formData.remove_legacy_window
                          ? `Das Fenster wird ab ${formatDate(formData.effective_from)} entfernt; danach wird nicht mehr gekappt.`
                          : 'Bleibt mit dieser Änderung bestehen: kappt die erfasste Zeit, ändert das Tagessoll nicht.'}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {trackHours && (
                          <button
                            type="button"
                            onClick={() => setFormData((prev) => ({
                              ...prev,
                              mode: 'blocks',
                              blocks: legacyToEditable(baselineSchedule.blocks ?? emptyWeek()),
                              remove_legacy_window: false,
                            }))}
                            className="px-3 py-1 rounded-lg border border-gray-300 bg-white text-gray-800 hover:bg-gray-100"
                          >
                            In Arbeitszeit-Blöcke umwandeln
                          </button>
                        )}
                        <button
                          type="button"
                          aria-pressed={formData.remove_legacy_window}
                          onClick={() => setFormData((prev) => ({ ...prev, remove_legacy_window: !prev.remove_legacy_window }))}
                          className="px-3 py-1 rounded-lg border border-gray-300 bg-white text-gray-800 hover:bg-gray-100"
                        >
                          {formData.remove_legacy_window ? 'Fenster behalten' : 'Fenster entfernen'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* P24: Moduswechsel weg von Blöcken — vor dem Speichern nennen. */}
                  {baselineNewBlocks && formData.mode !== 'blocks' && !snapshotUnchanged && (
                    <p className="text-sm font-medium text-amber-800">
                      {modeSwitchHint(formatDate(formData.effective_from))}
                    </p>
                  )}

                  <div className="space-y-1 text-xs text-gray-600">
                    <p className="flex gap-1"><Info size={14} className="shrink-0 mt-0.5" aria-hidden="true" />{LEGAL_HINT}</p>
                    <p className="flex gap-1"><Info size={14} className="shrink-0 mt-0.5" aria-hidden="true" />{JARBSCHG_HINT}</p>
                  </div>

                  {/* P9: Plan-Hinweise — nicht blockierend. */}
                  {planNotices.length > 0 && (
                    <ul aria-label="Hinweise zum Plan" className="list-disc pl-5 text-sm text-blue-900 space-y-0.5">
                      {planNotices.map((n) => <li key={n}>{n}</li>)}
                    </ul>
                  )}

                  {showImpactBox && (
                    <div
                      role="status"
                      className={`rounded-lg border p-3 text-sm ${
                        blockedReason || shownError ? 'bg-red-50 border-red-300' : 'bg-amber-50 border-amber-300'
                      }`}
                    >
                      {shownLoading ? (
                        <p className="text-gray-600">Prüfe Auswirkungen…</p>
                      ) : shown ? (
                        <>
                          {/* Fund A (#431): blockedReason entscheidet vor allen anderen Gründen. */}
                          <p className="font-semibold text-amber-900">
                            {blockedReason
                              ? 'Änderung nicht möglich'
                              : isRetroactive
                                ? 'Rückwirkende Änderung'
                                : affectsEntries
                                  ? 'Betrifft bereits erfasste Zeiteinträge'
                                  : affectsBookedAbsences
                                    ? 'Betrifft bereits gebuchte Abwesenheiten'
                                    : 'Ändert Überstunden oder Urlaubsverbrauch'}:{' '}
                            {formatDate(shown.period_start)} – {formatDate(shown.period_end)}
                          </p>
                          {!blockedReason && <WhImpactBox preview={shown} />}
                          {balanceUnchangedAhead && (
                            <p className="text-amber-800 mt-1">
                              Saldo und Urlaub stehen auf dem Stand von heute — die Änderung
                              wirkt erst ab dem {formatDate(sentDate)}. Die oben
                              genannten Abwesenheiten werden trotzdem umgeschrieben.
                            </p>
                          )}
                          {shown.closed_year_warning && (
                            <p className="text-amber-900 font-medium mt-1">{shown.closed_year_warning}</p>
                          )}
                          {blockedReason ? (
                            <p className="text-red-700 font-medium mt-2">{blockedReason}</p>
                          ) : (
                            <label className="flex items-center gap-2 mt-2 text-amber-900 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={confirmedRetroactive}
                                onChange={(e) => setConfirmedRetroactive(e.target.checked)}
                                className="w-4 h-4 text-amber-600 border-gray-300 rounded-sm focus:ring-amber-500"
                              />
                              Ich habe die Auswirkungen geprüft und möchte speichern
                            </label>
                          )}
                        </>
                      ) : shownError ? (
                        <>
                          <p className="text-red-700 font-medium">{shownError}</p>
                          <button
                            type="button"
                            onClick={() => setPreviewRetryToken((t) => t + 1)}
                            className="mt-2 text-sm font-medium text-red-700 underline hover:no-underline"
                          >
                            Erneut prüfen
                          </button>
                        </>
                      ) : null}
                    </div>
                  )}

                  {snapshotUnchanged && !blockedReason && (
                    <p className="text-sm text-gray-600">
                      Noch nichts zu speichern — die Eingabe entspricht dem Stand, der
                      am {formatDate(formData.effective_from)} ohnehin gilt.
                    </p>
                  )}

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={onClose}
                      className="flex-1 px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
                    >
                      Abbrechen
                    </button>
                    <button
                      type="submit"
                      disabled={saveDisabled}
                      className="flex-1 bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center justify-center space-x-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Save size={18} />
                      <span>Speichern</span>
                    </button>
                  </div>
                </form>
              </div>

              <div>
                <h3 className="font-semibold text-gray-900 mb-3">Verlauf</h3>
                {hoursChanges.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">Keine Änderungen vorhanden</p>
                ) : (
                  <div className="space-y-3">
                    {hoursChanges.map((change) => {
                      const end = historyEndDates.get(change.id);
                      const rowBlocks = blocksLine(Array.isArray(change.blocks) ? change.blocks : null, trackHours);
                      return (
                        <div
                          key={change.id}
                          className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex items-center justify-between"
                        >
                          <div>
                            <p className="font-medium text-gray-900">
                              Ab {formatDate(change.effective_from)} bis {end ? formatDate(end) : 'heute'}:{' '}
                              {describeSchedule(scheduleFromChange(change, propsSchedule.work_days_per_week))}
                            </p>
                            {rowBlocks && <p className="text-sm text-gray-700 mt-1">{rowBlocks}</p>}
                            {change.note && <p className="text-sm text-gray-600 mt-1">{change.note}</p>}
                            <p className="text-xs text-gray-500 mt-1">
                              Erstellt: {new Date(change.created_at).toLocaleDateString('de-DE', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                          </div>
                          {change.id === lockedEarliestId ? (
                            <span title={LOCKED_EARLIEST_HINT} className="shrink-0">
                              <button
                                type="button"
                                disabled
                                aria-label="Löschen nicht möglich – früheste Stundenänderung"
                                className="text-gray-300 cursor-not-allowed"
                              >
                                <Trash2 size={18} />
                              </button>
                            </span>
                          ) : (
                            <button
                              onClick={() => handleDeleteHoursChange(change.id)}
                              className="text-red-600 hover:text-red-800"
                              title="Löschen"
                            >
                              <Trash2 size={18} />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-800">
                  <strong>Hinweis:</strong> Die Berechnungen von Soll-Stunden berücksichtigen automatisch die
                  historischen Werte — bei „Gleichmäßig", „Nach Tagen" <strong>und</strong> „Nach
                  Arbeitsblöcken", auch über einen Moduswechsel hinweg. Bei „Nach Arbeitsblöcken" ist das
                  Tagessoll die Gesamtzeit der Blöcke minus der Pause innerhalb der Blöcke; erfasste Zeit
                  wird an den Blockrändern mit dem Puffer gekappt.
                </p>
              </div>
            </div>
          </div>
        </FocusTrap>
      </div>
    </>
  );
}
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/WhImpactBox.test.tsx src/pages/admin/users/WorkingHoursModal.test.tsx --pool=threads`, dann `npx tsc --noEmit` und `npx eslint src/pages/admin/users/WorkingHoursModal.tsx`
Expected: alle PASS (Bestandstests mit den umgestellten Wortlauten eingeschlossen, `WhImpactBox.test.tsx` unverändert grün), `tsc` ohne Ausgabe, eslint `0 errors`. Scheitert `findByRole('status')` an einem zweiten Treffer, rendert ein Toast mit `role="status"` — dann im betroffenen Test `within(screen.getByRole('dialog'))` verwenden, nicht die Rolle der Box ändern.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/admin/users/WorkingHoursModal.tsx frontend/src/pages/admin/users/WorkingHoursModal.test.tsx
git commit -F - <<'EOF'
feat(bloecke): Dialog „Arbeitszeit & Wochenstunden" mit Block-Modus, POST-Vorschau und Altfenster-Aktionen

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 19: Verkürzungs-Kasten — zwei Optionen, Grundtypen, Haken, MiLoG (Spec 9.5, 12.1, F24, P1, P15, P25, P26, 19.1 Nr. 1/2/7)

**Files:**
- Create: `frontend/src/pages/admin/users/ShorteningChoice.tsx`, `frontend/src/pages/admin/users/ShorteningChoice.test.tsx`
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.tsx` (Importe, Zustand, Vorschau-Effekt, Ableitungen, zweite Vorschau, `saveDisabled`, Anlege-Body, JSX)
- Test (erweitern): `frontend/src/pages/admin/users/WorkingHoursModal.test.tsx`

**Interfaces:**
- Consumes: `REASON_OPTIONS`, `REASON_HELP`, `OTHER_WARNING`, `OTHER_CONFIRM`, `ReasonState`, `EMPTY_REASON`, `reasonComplete`, `reasonPayload`, `closedYearMessage`, `ShorteningOption`, `formatDate`, `hm` (Task 16); `WorkingHoursChangePreview` mit `is_shortening`, `shortening_reasons`, `shortening_closed_years`, `earliest_lossless_date`, `earliest_lossless_note`, `lost_credited_hours`, `saldo_delta_hours`, `open_day_saldo_delta_hours`, `target_delta_hours`, `absence_credit_reductions`, `milog_warning` (Task 10/16); Modal-Namen `previewKey`, `sentDate`, `shown`, `shownLoading`, `shownError`, `saveDisabled` (Task 18b)
- Produces (in `ShorteningChoice.tsx`):
  - `shorteningHeadlines(p: WorkingHoursChangePreview): string[]` — Kopfzeilen je Kriterium (12.1)
  - `losslessLabel(p: WorkingHoursChangePreview, today: string): string | null` — „Ab heute (TT.MM.JJJJ) wirksam – …" / „Ab TT.MM.JJJJ wirksam – …", `null` bei `earliest_lossless_date = null`
  - `retroLabel(requestedDate: string): string` — „Rückwirkend ab TT.MM.JJJJ mit Neuberechnung"
  - `RetroReasonFields({ value, onChange, idPrefix, milogWarnings })` — Grund (Hilfetext immer sichtbar), Begründung (10–400), Haken je Grundtyp, bei „Sonstiges" rote Warnung + zweiter Haken, MiLoG-Sätze
  - `default ShorteningChoice({ preview, losslessText, losslessNote?, retroText, option, onOptionChange, closedText, reason, onReasonChange, idPrefix })` — `section` (Rolle `region`, Name „Verkürzung")

Regeln (F24): Ob der Kasten erscheint und welche Optionen er hat, entscheidet **immer** die Vorschau des eingegebenen Datums (`requestedDate` = Feld „Gültig ab", bleibt beim Umschalten unverändert). Standard ist Option 1; sie sendet `earliest_lossless_date` ohne Grund und zeigt in der Auswirkungs-Box eine **zweite** Vorschau für dieses Datum. Option 2 sendet das eingegebene Datum mit Grund/Begründung/Haken. `shortening_closed_years` nicht leer → Option 2 deaktiviert mit dem Text der 400-Meldung. Der Kasten steht **vor** der Auswirkungs-Box, damit der Haken „Ich habe die Auswirkungen geprüft" das letzte Element vor „Speichern" bleibt.

- [ ] **Step 1: Failing tests schreiben**

`frontend/src/pages/admin/users/ShorteningChoice.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { losslessLabel, retroLabel, shorteningHeadlines } from './ShorteningChoice';
import type { WorkingHoursChangePreview } from './workingHoursTypes';

const P = (o: Partial<WorkingHoursChangePreview>): WorkingHoursChangePreview => ({
  is_retroactive: true, period_start: '2026-09-01', period_end: '2026-10-08',
  current_daily_target: 7, new_daily_target: 6, day_targets_current: [7, 4, 0, 4, 0], day_targets_new: [6, 4, 0, 4, 0],
  overtime_before: 12.5, overtime_after: 14.25, vacation_days_before: 10, vacation_days_after: 10,
  affected_absences: 0, blocked_reason: null, closed_years: [], closed_year_warning: null,
  is_shortening: true, ...o,
});
const losing = (id: string) => ({
  entry_id: id, date: '2026-09-14', old_start: '15:00:00', old_end: '18:00:00', old_uncredited: 0, old_net: 3,
  new_start: '15:00:00', new_end: '17:15:00', new_uncredited: 0, new_net: 2.25, not_extendable: null,
});

describe('shorteningHeadlines (Spec 12.1)', () => {
  it('(a) Einträge mit Summe', () => {
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries'], lost_credited_hours: 2.25,
      time_entry_changes: [losing('a'), losing('b'), losing('c')],
    }))).toEqual(['3 Einträge verlieren angerechnete Zeit (zusammen 2:15 h)']);
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries'], lost_credited_hours: 0.75, time_entry_changes: [losing('a')],
    }))).toEqual(['1 Eintrag verliert angerechnete Zeit (zusammen 0:45 h)']);
  });

  it('(b) Saldo mit Soll-Zusatz, nur wenn kein Eintrag verliert (dritter Zustand)', () => {
    expect(shorteningHeadlines(P({ shortening_reasons: ['saldo'], saldo_delta_hours: -3.75, target_delta_hours: 4 })))
      .toEqual(['Das Überstundenkonto sinkt im Wirkungsbereich um 3:45 h (höheres Soll), obwohl kein Eintrag angerechnete Zeit verliert']);
    expect(shorteningHeadlines(P({
      shortening_reasons: ['entries', 'saldo'], saldo_delta_hours: -1, target_delta_hours: 0, lost_credited_hours: 1,
      time_entry_changes: [losing('a')],
    }))[1]).toBe('Das Überstundenkonto sinkt im Wirkungsbereich um 1:00 h');
  });

  it('(b) offener Tag heute und Anteil eines abgeschlossenen Jahres', () => {
    expect(shorteningHeadlines(P({ shortening_reasons: ['saldo'], saldo_delta_hours: 0, open_day_saldo_delta_hours: -1 })))
      .toEqual(['Heute steigt das Soll um 1:00 h, während die Person eingestempelt ist – das Überstundenkonto sinkt beim Ausstempeln.']);
    expect(shorteningHeadlines(P({
      shortening_reasons: ['saldo'], saldo_delta_hours: 0.5, open_day_saldo_delta_hours: 0, shortening_closed_years: [2025],
    }))).toEqual(['Das Überstundenkonto sinkt im abgeschlossenen Jahr 2025']);
  });

  it('(c) Gutschriften, mehrere Kriterien untereinander', () => {
    const lines = shorteningHeadlines(P({
      shortening_reasons: ['entries', 'saldo', 'absence_credit'], lost_credited_hours: 0.75,
      time_entry_changes: [losing('a')], saldo_delta_hours: -2, target_delta_hours: 0,
      absence_credit_reductions: [
        { absence_id: 'x', date: '2026-09-21', old_hours: 8, new_hours: 4 },
        { absence_id: 'y', date: '2026-09-28', old_hours: 8, new_hours: 4 },
      ],
    }));
    expect(lines).toHaveLength(3);
    expect(lines[2]).toBe('2 Abwesenheits-Gutschriften sinken stärker als das Tagessoll (Arbeit und Gutschrift am selben Tag)');
  });
});

describe('Optionsbeschriftungen (P1, P25)', () => {
  it('„Ab heute (…)", „Ab ‹Datum›", null', () => {
    expect(losslessLabel(P({ shortening_reasons: ['entries'], earliest_lossless_date: '2026-10-08' }), '2026-10-08'))
      .toBe('Ab heute (08.10.2026) wirksam – vergangene Einträge bleiben unverändert');
    expect(losslessLabel(P({ shortening_reasons: ['saldo'], earliest_lossless_date: '2026-10-09' }), '2026-10-08'))
      .toBe('Ab 09.10.2026 wirksam – vergangene Tage bleiben unverändert');
    expect(losslessLabel(P({ earliest_lossless_date: null }), '2026-10-08')).toBeNull();
    expect(retroLabel('2026-09-01')).toBe('Rückwirkend ab 01.09.2026 mit Neuberechnung');
  });
});
```

An `WorkingHoursModal.test.tsx` anhängen:

```tsx
const LOSING = (id: string) => ({
  entry_id: id, date: '2026-06-08', old_start: '15:00:00', old_end: '18:00:00', old_uncredited: 0, old_net: 3,
  new_start: '15:00:00', new_end: '17:15:00', new_uncredited: 0, new_net: 2.25, not_extendable: null,
});
const MILOG_GENERAL = 'Bei Minijob oder Vergütung in Mindestlohnhöhe kann die Kürzung Mindestlohnansprüche (§§ 1, 3 MiLoG) und die Aufzeichnung nach § 17 MiLoG berühren.';
const P25_NOTE = 'Die Änderung liegt vollständig vor der Änderung ab 01.07.2026; nur rückwirkend mit Begründung oder abbrechen.';
// Vorschau des EINGEGEBENEN Datums 01.06.2026: Verkürzung nach (a).
const SHORTENING: PreviewOverrides = {
  is_retroactive: true, period_start: '2026-06-01', period_end: '2026-07-26', affected_absences: 0,
  affected_time_entries: 3, is_shortening: true, shortening_reasons: ['entries'], shortening_closed_years: [],
  earliest_lossless_date: '2026-07-26', earliest_lossless_note: null, lost_credited_hours: 2.25,
  time_entry_changes: [LOSING('a'), LOSING('b'), LOSING('c')], milog_warning: [MILOG_GENERAL],
};

// Jede andere Vorschau (Option 1, Datum heute/morgen) ist verlustfrei und still.
function mockShortening(short: PreviewOverrides = {}) {
  getMock.mockImplementation((url: string, config?: { params?: { effective_from?: string } }) => {
    if (String(url).includes('/preview')) {
      return Promise.resolve(previewResponse(config?.params?.effective_from === '2026-06-01'
        ? { ...SHORTENING, ...short }
        : { ...QUIET, is_shortening: false, shortening_reasons: [] }));
    }
    return Promise.resolve(historyResponse([]));
  });
}

async function enterShortening() {
  renderModal();
  await screen.findByText('Keine Änderungen vorhanden');
  fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
  fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
  await flushDebounce();
  return screen.findByRole('region', { name: 'Verkürzung' });
}

const lastPreviewParams = () =>
  getMock.mock.calls.filter((c) => String(c[0]).includes('/preview')).at(-1)?.[1]?.params as Record<string, unknown>;

describe('Spec 2026-10-08 (PR3): Verkürzungs-Kasten', () => {
  it('Standard Option 1 „Ab heute (…) wirksam": eigene Vorschau, sendet earliest_lossless_date ohne Grund', async () => {
    mockShortening();
    const region = await enterShortening();
    expect(within(region).getByText('3 Einträge verlieren angerechnete Zeit (zusammen 2:15 h)')).toBeInTheDocument();
    expect(within(region).getByRole('radio', {
      name: 'Ab heute (26.07.2026) wirksam – vergangene Einträge bleiben unverändert',
    })).toBeChecked();
    expect(within(region).queryByLabelText('Grund')).not.toBeInTheDocument();
    await waitFor(() => expect(lastPreviewParams()).toMatchObject({ effective_from: '2026-07-26', weekly_hours: 20 }));

    const submit = screen.getByRole('button', { name: /Speichern/ });
    await waitFor(() => expect(submit).not.toBeDisabled());
    fireEvent.click(submit);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const body = postMock.mock.calls.at(-1)![1];
    expect(body).toMatchObject({ effective_from: '2026-07-26', weekly_hours: 20 });
    expect(body).not.toHaveProperty('retroactive_reason_type');
  });

  it('F24: Option 2 und zurück behält das eingegebene Datum; Grundtypen, Hilfetext, Haken, gesendete Schlüssel', async () => {
    mockShortening();
    const region = await enterShortening();
    fireEvent.click(within(region).getByRole('radio', { name: 'Rückwirkend ab 01.06.2026 mit Neuberechnung' }));
    expect(screen.getByLabelText('Gültig ab')).toHaveValue('2026-06-01');

    const select = within(region).getByLabelText('Grund');
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Bitte wählen…', 'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)', 'Mit der beschäftigten Person vereinbart',
      'Sonstiges',
    ]);
    expect(within(region).getByText('Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.'))
      .toBeInTheDocument();
    expect(within(region).getByText(MILOG_GENERAL)).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: /Speichern/ });
    expect(submit).toBeDisabled();

    fireEvent.click(within(region).getByRole('radio', { name: /^Ab heute \(26\.07\.2026\) wirksam/ }));
    expect(screen.getByLabelText('Gültig ab')).toHaveValue('2026-06-01');
    fireEvent.click(within(region).getByRole('radio', { name: /^Rückwirkend ab 01\.06\.2026/ }));

    fireEvent.change(within(region).getByLabelText('Grund'), { target: { value: 'erfassungsfehler' } });
    expect(within(region).getByText('Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.'))
      .toBeInTheDocument();
    fireEvent.change(within(region).getByLabelText('Begründung'), { target: { value: 'Blöcke falsch erfasst' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /Auswirkungen geprüft/ }));
    expect(submit).toBeDisabled();
    fireEvent.click(within(region).getByRole('checkbox', {
      name: /^Ich habe geprüft, dass die hinterlegte Arbeitszeit falsch war \(Fehlerkorrektur\)\. Tatsächlich geleistete Arbeit/,
    }));
    expect(submit).not.toBeDisabled();

    fireEvent.click(submit);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls.at(-1)![1]).toMatchObject({
      effective_from: '2026-06-01', weekly_hours: 20, retroactive_reason_type: 'erfassungsfehler',
      retroactive_reason_text: 'Blöcke falsch erfasst', wage_risk_confirmed: true, other_reason_risk_confirmed: false,
    });
  });

  it('Begründung unter 10 Zeichen hält Speichern gesperrt (P15)', async () => {
    mockShortening({ earliest_lossless_date: null, earliest_lossless_note: P25_NOTE });
    const region = await enterShortening();
    fireEvent.change(within(region).getByLabelText('Grund'), { target: { value: 'einvernehmlich' } });
    fireEvent.change(within(region).getByLabelText('Begründung'), { target: { value: 'zu kurz' } });
    fireEvent.click(within(region).getByRole('checkbox', { name: /mit der beschäftigten Person vereinbart ist/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Auswirkungen geprüft/ }));
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
    fireEvent.change(within(region).getByLabelText('Begründung'), { target: { value: 'Mit Frau B. vereinbart' } });
    expect(screen.getByRole('button', { name: /Speichern/ })).not.toBeDisabled();
  });

  it('„Ab ‹Datum› wirksam", wenn heute schon etwas verliert (P1)', async () => {
    mockShortening({ earliest_lossless_date: '2026-07-27' });
    const region = await enterShortening();
    expect(within(region).getByRole('radio', { name: 'Ab 27.07.2026 wirksam – vergangene Einträge bleiben unverändert' }))
      .toBeChecked();
    await waitFor(() => expect(lastPreviewParams()).toMatchObject({ effective_from: '2026-07-27' }));
  });

  it('P25: earliest_lossless_date = null → nur Option 2 mit Hinweistext', async () => {
    mockShortening({ earliest_lossless_date: null, earliest_lossless_note: P25_NOTE });
    const region = await enterShortening();
    expect(within(region).queryByRole('radio', { name: /^Ab / })).not.toBeInTheDocument();
    expect(within(region).getByText(P25_NOTE)).toBeInTheDocument();
    expect(within(region).getByRole('radio', { name: /^Rückwirkend ab 01\.06\.2026/ })).toBeChecked();
    expect(within(region).getByLabelText('Grund')).toBeInTheDocument();
  });

  it('„Sonstiges": rote Warnung und zweiter Haken sind Pflicht (P26)', async () => {
    mockShortening({ earliest_lossless_date: null, earliest_lossless_note: P25_NOTE });
    const region = await enterShortening();
    fireEvent.change(within(region).getByLabelText('Grund'), { target: { value: 'sonstiges' } });
    fireEvent.change(within(region).getByLabelText('Begründung'), { target: { value: 'Sonstiger Grund mit Text' } });
    fireEvent.click(within(region).getByRole('checkbox', { name: /^Ich habe die Gründe geprüft\./ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Auswirkungen geprüft/ }));
    expect(within(region).getByText(
      'Eine einseitige rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO wirkt nur für die Zukunft); geleistete Arbeit bleibt zu vergüten.',
    )).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: /Speichern/ });
    expect(submit).toBeDisabled();
    fireEvent.click(within(region).getByRole('checkbox', {
      name: 'Mir ist bewusst, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht nicht gedeckt ist.',
    }));
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls.at(-1)![1]).toMatchObject({
      retroactive_reason_type: 'sonstiges', other_reason_risk_confirmed: true, wage_risk_confirmed: true,
    });
  });

  it('Soll-Erhöhung ohne verlierenden Eintrag: Saldo-Kopfzeile und „vergangene Tage" (dritter Zustand, 19.1 Nr. 1)', async () => {
    mockShortening({
      shortening_reasons: ['saldo'], affected_time_entries: 1, saldo_delta_hours: -3.75, target_delta_hours: 4,
      credited_delta_hours: 0.25, lost_credited_hours: 0, time_entry_changes: [],
    });
    const region = await enterShortening();
    expect(within(region).getByText(
      'Das Überstundenkonto sinkt im Wirkungsbereich um 3:45 h (höheres Soll), obwohl kein Eintrag angerechnete Zeit verliert',
    )).toBeInTheDocument();
    expect(within(region).getByRole('radio', { name: 'Ab heute (26.07.2026) wirksam – vergangene Tage bleiben unverändert' }))
      .toBeChecked();
    fireEvent.click(within(region).getByRole('radio', { name: /^Rückwirkend ab/ }));
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled();
  });

  it('Gutschrift-Kriterium (c): Kopfzeile, Liste unter „Einzelheiten"', async () => {
    mockShortening({
      shortening_reasons: ['absence_credit'], affected_time_entries: 0, time_entry_changes: [],
      absence_credit_reductions: [{ absence_id: 'a1', date: '2026-06-15', old_hours: 8, new_hours: 4 }],
    });
    const region = await enterShortening();
    expect(within(region).getByText(
      '1 Abwesenheits-Gutschrift sinkt stärker als das Tagessoll (Arbeit und Gutschrift am selben Tag)',
    )).toBeInTheDocument();
    fireEvent.click(within(region).getByRole('radio', { name: /^Rückwirkend ab/ }));
    const box = await screen.findByRole('status');
    fireEvent.click(within(box).getByRole('button', { name: 'Einzelheiten' }));
    expect(within(box).getByText('Gutschrift 15.06.: 8:00 h → 4:00 h')).toBeInTheDocument();
  });

  it('abgeschlossenes Jahr: Option 2 deaktiviert mit dem Text der 400-Meldung, Option 1 bleibt', async () => {
    mockShortening({ shortening_closed_years: [2025] });
    const region = await enterShortening();
    expect(within(region).getByRole('radio', { name: /^Rückwirkend ab/ })).toBeDisabled();
    expect(within(region).getByText(
      'Rückwirkende Verkürzung in das abgeschlossene Jahr 2025 ist gesperrt. Bitte die Änderung frühestens ab 01.01.2026 wirksam werden lassen.',
    )).toBeInTheDocument();
    expect(within(region).getByRole('radio', { name: /^Ab heute/ })).toBeChecked();
  });

  it('Verlängerung (zweiter Zustand) zeigt keinen Kasten', async () => {
    mockShortening({ is_shortening: false, shortening_reasons: [], affected_time_entries: 1 });
    renderModal();
    await screen.findByText('Keine Änderungen vorhanden');
    fireEvent.change(screen.getByLabelText('Gültig ab'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('Wochenstunden'), { target: { value: '20' } });
    await flushDebounce();
    await screen.findByRole('status');
    expect(screen.queryByRole('region', { name: 'Verkürzung' })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/ShorteningChoice.test.tsx src/pages/admin/users/WorkingHoursModal.test.tsx --pool=threads`
Expected: FAIL — `./ShorteningChoice` fehlt; im Modal-Test kein `region` „Verkürzung".

- [ ] **Step 3: `ShorteningChoice.tsx` anlegen**

```tsx
import { AlertTriangle } from 'lucide-react';
import type { WorkingHoursChangePreview } from './workingHoursTypes';
import {
  OTHER_CONFIRM, OTHER_WARNING, REASON_HELP, REASON_OPTIONS, formatDate, hm,
  type ReasonState, type RetroReasonKey, type ShorteningOption,
} from './workingHoursTexts';

/** Spec 12.1: Kopfzeile je erfülltem Kriterium aus `shortening_reasons` (9.5). */
export function shorteningHeadlines(p: WorkingHoursChangePreview): string[] {
  const reasons = p.shortening_reasons ?? [];
  const out: string[] = [];
  if (reasons.includes('entries')) {
    // Der heute offene Eintrag (P1) steht nicht in `time_entry_changes` — fehlt
    // jede geschlossene Zeile, ist er der eine verlierende Eintrag.
    const n = (p.time_entry_changes ?? []).filter((c) => c.new_net < c.old_net).length || 1;
    const lost = p.lost_credited_hours ?? 0;
    out.push(`${n === 1 ? '1 Eintrag verliert' : `${n} Einträge verlieren`} angerechnete Zeit`
      + (lost > 0 ? ` (zusammen ${hm(lost)} h)` : ''));
  }
  if (reasons.includes('saldo')) {
    const saldo = p.saldo_delta_hours ?? 0;
    const openDay = p.open_day_saldo_delta_hours ?? 0;
    if (saldo < 0) {
      const extra = !reasons.includes('entries') && (p.target_delta_hours ?? 0) > 0
        ? ' (höheres Soll), obwohl kein Eintrag angerechnete Zeit verliert'
        : '';
      out.push(`Das Überstundenkonto sinkt im Wirkungsbereich um ${hm(saldo)} h${extra}`);
    }
    if (openDay < 0) {
      out.push(`Heute steigt das Soll um ${hm(openDay)} h, während die Person eingestempelt ist – das Überstundenkonto sinkt beim Ausstempeln.`);
    }
    if (saldo >= 0 && openDay >= 0) {
      out.push(`Das Überstundenkonto sinkt im abgeschlossenen Jahr ${(p.shortening_closed_years ?? []).join(', ')}`);
    }
  }
  if (reasons.includes('absence_credit')) {
    const n = (p.absence_credit_reductions ?? []).length;
    out.push(`${n === 1 ? '1 Abwesenheits-Gutschrift sinkt' : `${n} Abwesenheits-Gutschriften sinken`} stärker als das `
      + 'Tagessoll (Arbeit und Gutschrift am selben Tag)');
  }
  return out;
}

/** P1/P25: Beschriftung der verlustfreien Option oder `null` (nicht angeboten). */
export function losslessLabel(p: WorkingHoursChangePreview, today: string): string | null {
  const d = p.earliest_lossless_date;
  if (!d) return null;
  const suffix = (p.shortening_reasons ?? []).includes('entries')
    ? 'vergangene Einträge bleiben unverändert'
    : 'vergangene Tage bleiben unverändert';
  return d === today ? `Ab heute (${formatDate(d)}) wirksam – ${suffix}` : `Ab ${formatDate(d)} wirksam – ${suffix}`;
}

export function retroLabel(requestedDate: string): string {
  return `Rückwirkend ab ${formatDate(requestedDate)} mit Neuberechnung`;
}

interface RetroReasonFieldsProps {
  value: ReasonState;
  onChange: (value: ReasonState) => void;
  idPrefix: string;
  milogWarnings?: string[];
}

/** Spec 12.1/P26: Grund, Begründung (10–400), Bestätigung je Grundtyp. Ein
 * Wechsel des Grundtyps setzt die Haken zurück — ihr Wortlaut ändert sich. */
export function RetroReasonFields({ value, onChange, idPrefix, milogWarnings = [] }: RetroReasonFieldsProps) {
  const option = REASON_OPTIONS.find((o) => o.value === value.type);
  const length = value.text.trim().length;
  return (
    <div className="mt-2 space-y-2 pl-6">
      <div>
        <label htmlFor={`${idPrefix}-reason-type`} className="block text-sm font-medium text-gray-800">Grund</label>
        <select
          id={`${idPrefix}-reason-type`}
          value={value.type}
          onChange={(e) => onChange({
            ...value, type: e.target.value as RetroReasonKey | '', wageConfirmed: false, otherConfirmed: false,
          })}
          className="mt-1 w-full px-2 py-1 border border-gray-300 rounded-lg text-sm"
        >
          <option value="">Bitte wählen…</option>
          {REASON_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <p className="text-xs text-gray-600 mt-1">{REASON_HELP}</p>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-reason-text`} className="block text-sm font-medium text-gray-800">Begründung</label>
        <textarea
          id={`${idPrefix}-reason-text`}
          value={value.text}
          maxLength={400}
          rows={2}
          onChange={(e) => onChange({ ...value, text: e.target.value })}
          className="mt-1 w-full px-2 py-1 border border-gray-300 rounded-lg text-sm"
        />
        <p className="text-xs text-gray-500">{`${length}/400 Zeichen (mindestens 10)`}</p>
      </div>
      {option && (
        <label className="flex items-start gap-2 text-gray-900">
          <input
            type="checkbox"
            checked={value.wageConfirmed}
            onChange={(e) => onChange({ ...value, wageConfirmed: e.target.checked })}
            className="mt-0.5 w-4 h-4"
          />
          <span>{option.confirm}</span>
        </label>
      )}
      {value.type === 'sonstiges' && (
        <>
          <p className="font-medium text-red-700">{OTHER_WARNING}</p>
          <label className="flex items-start gap-2 text-gray-900">
            <input
              type="checkbox"
              checked={value.otherConfirmed}
              onChange={(e) => onChange({ ...value, otherConfirmed: e.target.checked })}
              className="mt-0.5 w-4 h-4"
            />
            <span>{OTHER_CONFIRM}</span>
          </label>
        </>
      )}
      {milogWarnings.map((w) => (
        <p key={w} className="flex gap-1 text-amber-900">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden="true" />
          {w}
        </p>
      ))}
    </div>
  );
}

interface ShorteningChoiceProps {
  preview: WorkingHoursChangePreview;
  /** Option 1 — `null`: nicht angeboten (P25). */
  losslessText: string | null;
  /** Erklärung unter Option 1, wenn gewählt (Rücksetzung beim Löschen). */
  losslessNote?: string | null;
  retroText: string;
  option: ShorteningOption;
  onOptionChange: (option: ShorteningOption) => void;
  /** Text der 400-Meldung bei Verlust in einem abgeschlossenen Jahr. */
  closedText: string | null;
  reason: ReasonState;
  onReasonChange: (reason: ReasonState) => void;
  idPrefix: string;
}

/**
 * Spec 2026-10-08, 9.5/12.1: Kasten „Verkürzung" — gemeinsam für Anlegen und
 * Löschen. Die Optionen leiten sich IMMER aus der Vorschau des eingegebenen
 * Datums ab (F24); was gesendet wird, entscheidet der Aufrufer.
 */
export default function ShorteningChoice({
  preview, losslessText, losslessNote, retroText, option, onOptionChange, closedText, reason, onReasonChange,
  idPrefix,
}: ShorteningChoiceProps) {
  const retroSelected = option === 'retro' || losslessText === null;
  return (
    <section
      aria-labelledby={`${idPrefix}-title`}
      className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm"
    >
      <p id={`${idPrefix}-title`} className="flex items-center gap-1 font-semibold text-red-900">
        <AlertTriangle size={16} aria-hidden="true" />
        Verkürzung
      </p>
      <ul className="mt-1 list-disc pl-5 text-red-900">
        {shorteningHeadlines(preview).map((line) => <li key={line}>{line}</li>)}
      </ul>
      <fieldset className="mt-2 space-y-1">
        <legend className="sr-only">Wirksamkeit</legend>
        {losslessText !== null ? (
          <label className="flex items-center gap-2 text-gray-900 cursor-pointer">
            <input
              type="radio"
              name={`${idPrefix}-option`}
              checked={!retroSelected}
              onChange={() => onOptionChange('lossless')}
              className="w-4 h-4"
            />
            {losslessText}
          </label>
        ) : (
          preview.earliest_lossless_note && <p className="text-gray-800">{preview.earliest_lossless_note}</p>
        )}
        {!retroSelected && losslessNote && <p className="pl-6 text-gray-700">{losslessNote}</p>}
        <label className={`flex items-center gap-2 ${closedText ? 'text-gray-400' : 'text-gray-900 cursor-pointer'}`}>
          <input
            type="radio"
            name={`${idPrefix}-option`}
            checked={retroSelected && !closedText}
            disabled={!!closedText}
            onChange={() => onOptionChange('retro')}
            className="w-4 h-4"
          />
          {retroText}
        </label>
        {closedText && <p className="pl-6 font-medium text-red-700">{closedText}</p>}
      </fieldset>
      {retroSelected && !closedText && (
        <RetroReasonFields
          value={reason}
          onChange={onReasonChange}
          idPrefix={idPrefix}
          milogWarnings={preview.milog_warning ?? []}
        />
      )}
    </section>
  );
}
```

- [ ] **Step 4: Modal anbinden**

In `WorkingHoursModal.tsx`:

(1) Importe — nach `import WhImpactBox from './WhImpactBox';`:

```ts
import ShorteningChoice, { losslessLabel, retroLabel } from './ShorteningChoice';
```

und den Import aus `./workingHoursTexts` ersetzen durch:

```ts
import {
  BLOCKS_WITHOUT_EFFECT, EMPTY_REASON, JARBSCHG_HINT, LEGACY_BOX_TITLE, LEGAL_HINT, closedYearMessage, formatDate,
  modeSwitchHint, reasonComplete, reasonPayload, savedMessage, type ReasonState, type ShorteningOption,
} from './workingHoursTexts';
```

(2) Zustand — nach `const [confirmedRetroactive, setConfirmedRetroactive] = useState(false);`:

```ts
  // Spec 12.1 (F24): Verkürzungs-Wahl. Das eingegebene Datum und seine Vorschau
  // bleiben stehen; Option 1 sendet `earliest_lossless_date` und zeigt dafür
  // eine zweite Vorschau.
  const [shorteningOption, setShorteningOption] = useState<ShorteningOption>('lossless');
  const [reason, setReason] = useState<ReasonState>(EMPTY_REASON);
  const [losslessPreview, setLosslessPreview] = useState<WorkingHoursChangePreview | null>(null);
  const [losslessLoading, setLosslessLoading] = useState(false);
  const [losslessError, setLosslessError] = useState<string | null>(null);
```

(3) Im Vorschau-Effekt nach `setPreviewError(null);`:

```ts
    // Neue Eingabe → neue Bewertung; Standard ist wieder Option 1 (12.1).
    setShorteningOption('lossless');
```

(4) Den Block

```ts
  // Was gesendet wird und was die Auswirkungs-Box zeigt.
  const sentDate = formData.effective_from;
  const shown: WorkingHoursChangePreview | null = preview;
  const shownLoading = previewLoading;
  const shownError = previewError;
  const isRetroactive = sentDate < todayIso();
```

ersetzen durch:

```ts
  // Spec 9.5/12.1 (F24): ob verkürzt wird und welche Optionen es gibt, steht
  // IMMER in der Vorschau des eingegebenen Datums.
  const isShortening = !previewLoading && !!preview && !preview.blocked_reason && !!preview.is_shortening;
  const losslessDate = isShortening ? (preview?.earliest_lossless_date ?? null) : null;
  const closedText = isShortening ? closedYearMessage(preview?.shortening_closed_years) : null;
  const useLossless = losslessDate !== null && shorteningOption === 'lossless';
  const needsReason = isShortening && !useLossless;
  const losslessKey = useLossless
    ? JSON.stringify({ ...JSON.parse(previewKey), effective_from: losslessDate })
    : null;

  // Option 1: zweite Vorschau für `earliest_lossless_date` (ohne Debounce — der
  // Schlüssel ändert sich nur mit einer neuen Antwort oder einem Klick).
  useEffect(() => {
    if (!losslessKey) {
      setLosslessPreview(null);
      return;
    }
    setConfirmedRetroactive(false);
    setLosslessLoading(true);
    setLosslessError(null);
    let cancelled = false;
    apiClient
      .post(`/admin/users/${userId}/working-hours-changes/preview`, JSON.parse(losslessKey))
      .then((res) => {
        if (!cancelled) setLosslessPreview(res.data);
      })
      .catch((error) => {
        if (cancelled) return;
        setLosslessPreview(null);
        setLosslessError(getErrorMessage(error, 'Auswirkungen konnten nicht geprüft werden'));
      })
      .finally(() => {
        if (!cancelled) setLosslessLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, losslessKey, previewRetryToken]);

  // Was gesendet wird und was die Auswirkungs-Box zeigt.
  const sentDate = useLossless && losslessDate ? losslessDate : formData.effective_from;
  const shown: WorkingHoursChangePreview | null = useLossless ? losslessPreview : preview;
  const shownLoading = useLossless ? losslessLoading : previewLoading;
  const shownError = useLossless ? losslessError : previewError;
  const isRetroactive = sentDate < todayIso();
```

(5) In `saveDisabled` nach `snapshotUnchanged ||`:

```ts
    (useLossless && (shownLoading || !shown)) ||
    // P15/P26/11.4: Option 2 nur mit allen Pflichtangaben, nie in ein abgeschlossenes Jahr.
    (needsReason && (!!closedText || !reasonComplete(reason))) ||
```

(6) Anlege-Body — `...scheduleBody,` im POST von `handleAddHoursChange` ergänzen zu:

```ts
        ...scheduleBody,
        ...(needsReason ? reasonPayload(reason) : {}),
```

und nach `setConfirmedRetroactive(false);` im Erfolgszweig:

```ts
      setReason(EMPTY_REASON);
      setShorteningOption('lossless');
```

(7) JSX — direkt vor `{showImpactBox && (`:

```tsx
                  {/* Spec 12.1: vor der Box, damit der Haken das letzte Element vor „Speichern" bleibt. */}
                  {isShortening && preview && (
                    <ShorteningChoice
                      preview={preview}
                      losslessText={losslessLabel(preview, todayIso())}
                      retroText={retroLabel(formData.effective_from)}
                      option={useLossless ? 'lossless' : 'retro'}
                      onOptionChange={(o) => {
                        setShorteningOption(o);
                        setConfirmedRetroactive(false);
                      }}
                      closedText={closedText}
                      reason={reason}
                      onReasonChange={setReason}
                      idPrefix="wh-short"
                    />
                  )}
```

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/ShorteningChoice.test.tsx src/pages/admin/users/WorkingHoursModal.test.tsx --pool=threads`, `npx tsc --noEmit`
Expected: PASS (die Bestandstests ohne `is_shortening` in der Vorschau bleiben unberührt — ihr Kasten erscheint nie), `tsc` ohne Ausgabe.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/admin/users/ShorteningChoice.tsx frontend/src/pages/admin/users/ShorteningChoice.test.tsx frontend/src/pages/admin/users/WorkingHoursModal.tsx frontend/src/pages/admin/users/WorkingHoursModal.test.tsx
git commit -F - <<'EOF'
feat(bloecke): Verkürzungs-Kasten mit verlustfreiem Standard, Grundtypen, Bestätigungen und MiLoG-Hinweisen (F24)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 20: Löschen nur an der jüngsten Zeile — `delete-preview`, Rücksetzung, rückwirkendes Löschen (Spec 9.7, 12.1, P8, P13, P25)

**Files:**
- Create: `frontend/src/pages/admin/users/WhDeletePanel.tsx`
- Modify: `frontend/src/pages/admin/users/workingHoursTexts.ts` (`dayBefore` anhängen)
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.tsx` (Importe, `useConfirm`/`ConfirmDialog` raus, `dayBefore` raus, jüngste Zeile, Lösch-Panel)
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.test.tsx` (`describe('Löschen einer Stundenänderung'` komplett ersetzen)

**Interfaces:**
- Consumes: `ShorteningChoice` (Task 19), `WhImpactBox` (Task 18a), `savedMessage(…, 'Gelöscht')`, `reasonPayload`, `reasonComplete`, `closedYearMessage`, `EMPTY_REASON` (Task 16); `POST …/{id}/delete-preview` mit `reset_body`, `DELETE …/{id}` mit optionalem Body (Task 11); 409 `RESET_CONFLICT_DETAIL` (Task 9)
- Produces:
  - `workingHoursTexts.dayBefore(iso: string): string`
  - `WhDeletePanel({ userId, change, onCancel, onDone })` — Rolle `alertdialog`, Name „Arbeitszeit-Änderung ab TT.MM.JJJJ löschen"; Knöpfe „Abbrechen", „Löschen" bzw. „Zurücksetzen"

- [ ] **Step 1: Failing tests — Lösch-Block ersetzen**

In `WorkingHoursModal.test.tsx` den kompletten `describe('Löschen einer Stundenänderung', () => { … });` ersetzen durch:

```tsx
describe('Löschen einer Arbeitszeit-Änderung (Spec 9.7/P13)', () => {
  const TWO_ROWS = [
    { id: 'c2', effective_from: '2026-06-01', weekly_hours: 30 },
    { id: 'c1', effective_from: '2026-01-01', weekly_hours: 40 },
  ];
  const RESET_BODY = {
    effective_from: '2026-07-27', reset_of_change_id: 'c2', use_daily_schedule: false, weekly_hours: 40,
    work_days_per_week: 5,
  };
  const SHORT_DELETE: PreviewOverrides = {
    is_retroactive: true, period_start: '2026-06-01', period_end: '2026-07-26', affected_absences: 0,
    is_shortening: true, shortening_reasons: ['saldo'], saldo_delta_hours: -40, target_delta_hours: 40,
    shortening_closed_years: [], earliest_lossless_date: '2026-07-27', reset_body: RESET_BODY,
  };

  async function openDelete(rows: Array<HistoryRow> = TWO_ROWS) {
    mockHistory(rows, QUIET);
    renderModal({ currentWeeklyHours: 30 });
    await screen.findByText(/Ab 01\.06\.2026 bis heute/);
    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    return screen.findByRole('alertdialog', { name: 'Arbeitszeit-Änderung ab 01.06.2026 löschen' });
  }

  it('[Löschen] steht nur an der jüngsten Zeile', async () => {
    mockHistory(TWO_ROWS, QUIET);
    renderModal({ currentWeeklyHours: 30 });
    await screen.findByText(/Ab 01\.01\.2026 bis 31\.05\.2026/);
    expect(screen.getAllByRole('button', { name: 'Löschen' })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /Löschen nicht möglich/ })).not.toBeInTheDocument();
  });

  it('ohne Verkürzung: einfache Bestätigung mit Vorschau, Toast und Jahreswarnung aus der 200-Antwort', async () => {
    deleteMock.mockResolvedValue({
      status: 200,
      data: { adjusted_absences: 1, adjusted_time_entries: 0, skipped_time_entries: 0,
        warning: 'Das Jahr 2025 ist bereits abgeschlossen — der Carryover 2026 könnte veraltet sein.' },
    });
    const dialog = await openDelete();
    expect(deletePreviewMock).toHaveBeenCalledWith('/admin/users/u1/working-hours-changes/c2/delete-preview', {});
    const del = within(dialog).getByRole('button', { name: 'Löschen' });
    await waitFor(() => expect(del).not.toBeDisabled());
    expect(within(dialog).queryByRole('region', { name: 'Verkürzung' })).not.toBeInTheDocument();
    fireEvent.click(del);

    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('/admin/users/u1/working-hours-changes/c2'));
    expect(await screen.findByText('Gelöscht. 1 Abwesenheit angepasst.')).toBeInTheDocument();
    expect(await screen.findByText(/2025 ist bereits abgeschlossen/)).toBeInTheDocument();
  });

  it('leere 204-Antwort: „Gelöscht." ohne Warnung', async () => {
    deleteMock.mockResolvedValue({ status: 204, data: '' });
    const dialog = await openDelete();
    const del = within(dialog).getByRole('button', { name: 'Löschen' });
    await waitFor(() => expect(del).not.toBeDisabled());
    fireEvent.click(del);
    expect(await screen.findByText('Gelöscht.')).toBeInTheDocument();
    expect(screen.queryByText(/abgeschlossen/)).not.toBeInTheDocument();
  });

  it('zeigt die Backend-Begründung statt einer pauschalen Fehlermeldung', async () => {
    deleteMock.mockRejectedValue({
      response: { data: { detail: 'Dies ist die früheste erfasste Stundenänderung dieses Mitarbeiters.' } },
    });
    const dialog = await openDelete();
    const del = within(dialog).getByRole('button', { name: 'Löschen' });
    await waitFor(() => expect(del).not.toBeDisabled());
    fireEvent.click(del);
    expect(await screen.findByText(/früheste erfasste Stundenänderung/)).toBeInTheDocument();
  });

  it('blocked_reason der delete-preview sperrt das Löschen', async () => {
    deletePreviewMock.mockResolvedValue(previewResponse({
      ...QUIET, blocked_reason: 'Die früheste Änderung verankert den davor gültigen Wert.',
    }));
    const dialog = await openDelete();
    expect(await within(dialog).findByText('Die früheste Änderung verankert den davor gültigen Wert.')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Löschen' })).toBeDisabled();
  });

  it('Verkürzung: Standard „auf vorherigen Stand zurücksetzen" sendet reset_body unverändert, Vorschau mit demselben Body', async () => {
    deletePreviewMock.mockResolvedValue(previewResponse(SHORT_DELETE));
    postMock.mockResolvedValue({ data: { id: 'c3', adjusted_time_entries: 0, adjusted_absences: 0, warning: null } });
    const dialog = await openDelete();
    const region = await within(dialog).findByRole('region', { name: 'Verkürzung' });
    expect(within(region).getByRole('radio', { name: 'Ab 27.07.2026 auf den vorherigen Stand zurücksetzen' })).toBeChecked();
    expect(within(region).getByText(
      'Die Änderung ab 01.06.2026 bleibt bis 26.07.2026 wirksam und im Verlauf stehen; ab 27.07.2026 gilt wieder der vorherige Stand.',
    )).toBeInTheDocument();
    // Die Vorschau des Hauptformulars kann nach dieser Anfrage noch eintreffen —
    // deshalb „irgendeine Vorschau mit genau diesem Body", nicht „die letzte".
    const previewBodies = () =>
      getMock.mock.calls.filter((c) => String(c[0]).includes('/preview')).map((c) => c[1]?.params);
    await waitFor(() => expect(previewBodies()).toContainEqual(RESET_BODY));

    const reset = within(dialog).getByRole('button', { name: 'Zurücksetzen' });
    await waitFor(() => expect(reset).not.toBeDisabled());
    fireEvent.click(reset);
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/admin/users/u1/working-hours-changes', RESET_BODY));
    expect(deleteMock).not.toHaveBeenCalled();
    expect(await screen.findByText('Gespeichert.')).toBeInTheDocument();
  });

  it('409 bei der Rücksetzung lädt die delete-preview neu', async () => {
    deletePreviewMock.mockResolvedValue(previewResponse(SHORT_DELETE));
    postMock.mockRejectedValue({ response: { status: 409, data: {
      detail: 'Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.',
    } } });
    const dialog = await openDelete();
    const reset = await within(dialog).findByRole('button', { name: 'Zurücksetzen' });
    await waitFor(() => expect(reset).not.toBeDisabled());
    fireEvent.click(reset);
    expect(await screen.findByText(/bitte die Vorschau neu laden/)).toBeInTheDocument();
    await waitFor(() => expect(deletePreviewMock).toHaveBeenCalledTimes(2));
  });

  it('„Rückwirkend löschen mit Neuberechnung" sendet Grund und Haken als DELETE-Body', async () => {
    deletePreviewMock.mockResolvedValue(previewResponse(SHORT_DELETE));
    deleteMock.mockResolvedValue({ status: 200, data: { adjusted_absences: 0, adjusted_time_entries: 2, skipped_time_entries: 0, warning: null } });
    const dialog = await openDelete();
    const region = await within(dialog).findByRole('region', { name: 'Verkürzung' });
    fireEvent.click(within(region).getByRole('radio', { name: 'Rückwirkend löschen mit Neuberechnung' }));
    const del = within(dialog).getByRole('button', { name: 'Löschen' });
    expect(del).toBeDisabled();
    fireEvent.change(within(region).getByLabelText('Grund'), { target: { value: 'einvernehmlich' } });
    fireEvent.change(within(region).getByLabelText('Begründung'), { target: { value: 'Mit Frau B. vereinbart' } });
    fireEvent.click(within(region).getByRole('checkbox', { name: /mit der beschäftigten Person vereinbart ist/ }));
    expect(del).not.toBeDisabled();
    fireEvent.click(del);
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('/admin/users/u1/working-hours-changes/c2', {
      data: {
        retroactive_reason_type: 'einvernehmlich', retroactive_reason_text: 'Mit Frau B. vereinbart',
        wage_risk_confirmed: true, other_reason_risk_confirmed: false,
      },
    }));
    expect(await screen.findByText('Gelöscht. 2 Zeiteinträge neu berechnet.')).toBeInTheDocument();
  });

  it('reset_body = null → nur „Rückwirkend löschen"', async () => {
    deletePreviewMock.mockResolvedValue(previewResponse({ ...SHORT_DELETE, reset_body: null }));
    const dialog = await openDelete();
    const region = await within(dialog).findByRole('region', { name: 'Verkürzung' });
    expect(within(region).queryByRole('radio', { name: /zurücksetzen/ })).not.toBeInTheDocument();
    expect(within(region).getByRole('radio', { name: 'Rückwirkend löschen mit Neuberechnung' })).toBeChecked();
    expect(within(dialog).queryByRole('button', { name: 'Zurücksetzen' })).not.toBeInTheDocument();
  });

  it('abgeschlossenes Jahr: rückwirkendes Löschen deaktiviert mit dem Text der 400-Meldung', async () => {
    deletePreviewMock.mockResolvedValue(previewResponse({ ...SHORT_DELETE, shortening_closed_years: [2025] }));
    const dialog = await openDelete();
    const region = await within(dialog).findByRole('region', { name: 'Verkürzung' });
    expect(within(region).getByRole('radio', { name: 'Rückwirkend löschen mit Neuberechnung' })).toBeDisabled();
    expect(within(region).getByText(/abgeschlossene Jahr 2025 ist gesperrt/)).toBeInTheDocument();
  });

  it('„Abbrechen" schließt das Panel ohne Anfrage', async () => {
    const dialog = await openDelete();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Abbrechen' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(deleteMock).not.toHaveBeenCalled();
  });
});
```

Der Block nutzt `mockHistory`, `QUIET` und `HistoryRow` aus Task 18b — ihn deshalb ans Dateiende verschieben (hinter den Verkürzungs-Block), statt ihn an der alten Stelle zu lassen.

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/WorkingHoursModal.test.tsx --pool=threads`
Expected: FAIL — zwei „Löschen"-Knöpfe bzw. ein deaktivierter „Löschen nicht möglich", kein `alertdialog` mit dem neuen Namen, `deletePreviewMock` nie aufgerufen.

- [ ] **Step 3: `dayBefore` nach `workingHoursTexts.ts` verlegen**

An `workingHoursTexts.ts` anhängen:

```ts
/** Kalendertag VOR dem ISO-Datum — UTC-basiert (reine Tagesarithmetik). */
export function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().split('T')[0];
}
```

- [ ] **Step 4: `WhDeletePanel.tsx` anlegen**

```tsx
import { useEffect, useState } from 'react';
import apiClient from '../../../api/client';
import { useToast } from '../../../contexts/ToastContext';
import { getErrorMessage } from '../../../utils/errorMessage';
import { showResponseWarning } from '../../../utils/arbzgWarnings';
import ShorteningChoice from './ShorteningChoice';
import WhImpactBox from './WhImpactBox';
import type { WorkingHoursChange, WorkingHoursChangePreview } from './workingHoursTypes';
import {
  EMPTY_REASON, closedYearMessage, dayBefore, formatDate, reasonComplete, reasonPayload, savedMessage,
  type ReasonState, type ShorteningOption,
} from './workingHoursTexts';

interface WhDeletePanelProps {
  userId: string;
  change: WorkingHoursChange;
  onCancel: () => void;
  onDone: () => Promise<void> | void;
}

/**
 * Spec 2026-10-08, 9.7/12.1/P13: Löschen einer Verlaufszeile mit Vorschau
 * (`delete-preview`). Verkürzt das Löschen, ist der Standard die Rücksetzung
 * auf den vorherigen Stand — `reset_body` geht UNVERÄNDERT an den
 * Anlege-Endpunkt, der Client baut den Snapshot nie selbst nach.
 */
export default function WhDeletePanel({ userId, change, onCancel, onDone }: WhDeletePanelProps) {
  const toast = useToast();
  const base = `/admin/users/${userId}/working-hours-changes/${change.id}`;
  const [dp, setDp] = useState<WorkingHoursChangePreview | null>(null);
  const [dpError, setDpError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [option, setOption] = useState<ShorteningOption>('lossless');
  const [reason, setReason] = useState<ReasonState>(EMPTY_REASON);
  const [resetPreview, setResetPreview] = useState<WorkingHoursChangePreview | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setDp(null);
    setDpError(null);
    setOption('lossless');
    apiClient
      .post(`${base}/delete-preview`, {})
      .then((res) => {
        if (!cancelled) setDp(res.data);
      })
      .catch((error) => {
        if (!cancelled) setDpError(getErrorMessage(error, 'Auswirkungen konnten nicht geprüft werden'));
      });
    return () => {
      cancelled = true;
    };
  }, [base, reloadToken]);

  const blocked = dp?.blocked_reason ?? null;
  const isShortening = !!dp && !blocked && !!dp.is_shortening;
  const resetBody = isShortening ? (dp?.reset_body ?? null) : null;
  const resetDate = typeof resetBody?.effective_from === 'string' ? resetBody.effective_from : null;
  const useReset = resetBody !== null && resetDate !== null && option === 'lossless';
  const needsReason = isShortening && !useReset;
  const closedText = isShortening ? closedYearMessage(dp?.shortening_closed_years) : null;
  const resetKey = useReset ? JSON.stringify(resetBody) : null;

  // Spec 12.1: die Box zeigt für die Rücksetzung die Vorschau mit DEMSELBEN Body.
  useEffect(() => {
    if (!resetKey) {
      setResetPreview(null);
      return;
    }
    let cancelled = false;
    apiClient
      .post(`/admin/users/${userId}/working-hours-changes/preview`, JSON.parse(resetKey))
      .then((res) => {
        if (!cancelled) setResetPreview(res.data);
      })
      .catch(() => {
        if (!cancelled) setResetPreview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, resetKey]);

  const shown = useReset ? resetPreview : dp;
  const actionDisabled = busy || !dp || !!blocked
    || (useReset && (!resetPreview || !!resetPreview.blocked_reason))
    || (needsReason && (!!closedText || !reasonComplete(reason)));

  const runReset = async () => {
    setBusy(true);
    try {
      const res = await apiClient.post(`/admin/users/${userId}/working-hours-changes`, resetBody);
      toast.success(savedMessage(res.data ?? {}));
      showResponseWarning(toast, res.data);
      await onDone();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Fehler beim Zurücksetzen'));
      // 11.4: 409 — der vorherige Stand hat sich geändert → delete-preview neu laden.
      if ((error as { response?: { status?: number } })?.response?.status === 409) {
        setReloadToken((t) => t + 1);
      }
    } finally {
      setBusy(false);
    }
  };

  const runDelete = async () => {
    setBusy(true);
    try {
      const res = needsReason
        ? await apiClient.delete(base, { data: reasonPayload(reason) })
        : await apiClient.delete(base);
      // I3: 200 + Zählung/Warnung oder 204 ohne Body (axios: data === '').
      const data = res?.data && typeof res.data === 'object' ? res.data : {};
      toast.success(savedMessage(data, 'Gelöscht'));
      showResponseWarning(toast, data);
      await onDone();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Fehler beim Löschen der Stundenänderung'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      role="alertdialog"
      aria-labelledby="wh-delete-title"
      className="mb-4 rounded-lg border border-red-300 bg-white p-4 text-sm space-y-2"
    >
      <h4 id="wh-delete-title" className="font-semibold text-gray-900">
        {`Arbeitszeit-Änderung ab ${formatDate(change.effective_from)} löschen`}
      </h4>
      {dpError ? (
        <>
          <p className="font-medium text-red-700">{dpError}</p>
          <button
            type="button"
            onClick={() => setReloadToken((t) => t + 1)}
            className="text-sm font-medium text-red-700 underline hover:no-underline"
          >
            Erneut prüfen
          </button>
        </>
      ) : !dp ? (
        <p className="text-gray-600">Prüfe Auswirkungen…</p>
      ) : blocked ? (
        <p className="font-medium text-red-700">{blocked}</p>
      ) : (
        <>
          {isShortening && (
            <ShorteningChoice
              preview={dp}
              losslessText={resetDate ? `Ab ${formatDate(resetDate)} auf den vorherigen Stand zurücksetzen` : null}
              losslessNote={resetDate
                ? `Die Änderung ab ${formatDate(change.effective_from)} bleibt bis ${formatDate(dayBefore(resetDate))} `
                  + `wirksam und im Verlauf stehen; ab ${formatDate(resetDate)} gilt wieder der vorherige Stand.`
                : null}
              retroText="Rückwirkend löschen mit Neuberechnung"
              option={useReset ? 'lossless' : 'retro'}
              onOptionChange={setOption}
              closedText={closedText}
              reason={reason}
              onReasonChange={setReason}
              idPrefix="wh-del"
            />
          )}
          {shown && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3">
              <p className="font-semibold text-amber-900">
                {`${useReset ? 'Auswirkung der Rücksetzung' : 'Auswirkung des Löschens'}: `
                  + `${formatDate(shown.period_start)} – ${formatDate(shown.period_end)}`}
              </p>
              <WhImpactBox preview={shown} />
            </div>
          )}
        </>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
        >
          Abbrechen
        </button>
        {useReset ? (
          <button
            type="button"
            disabled={actionDisabled}
            onClick={runReset}
            className="px-3 py-1.5 rounded-lg bg-primary text-white disabled:opacity-50"
          >
            Zurücksetzen
          </button>
        ) : (
          <button
            type="button"
            disabled={actionDisabled}
            onClick={runDelete}
            className="px-3 py-1.5 rounded-lg bg-red-600 text-white disabled:opacity-50"
          >
            Löschen
          </button>
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Modal umstellen**

In `WorkingHoursModal.tsx`:

(1) Die Zeilen `import { useConfirm } from '../../../hooks/useConfirm';` und `import ConfirmDialog from '../../../components/ConfirmDialog';` löschen; nach `import ShorteningChoice, …` ergänzen `import WhDeletePanel from './WhDeletePanel';`; im Import aus `./workingHoursTexts` `dayBefore` ergänzen; die lokale Funktion `dayBefore` (samt Kommentar „Kalendertag VOR dem ISO-Datum …") löschen.

(2) `const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();` ersetzen durch:

```ts
  // Spec 12.1/9.7: Lösch-Panel der jüngsten Zeile.
  const [deleting, setDeleting] = useState<WorkingHoursChange | null>(null);
```

(3) Den Block von `// I4: die früheste Zeile ist gesperrt, solange spätere existieren.` bis einschließlich `+ 'bitte zuerst die späteren Änderungen löschen.';` ersetzen durch:

```ts
  // Spec 12.1: [Löschen] nur an der JÜNGSTEN Zeile (die früheste bleibt damit
  // gesperrt, solange spätere existieren — I4; der Server prüft es weiter).
  const youngestId = useMemo(() => {
    let latest: WorkingHoursChange | null = null;
    for (const c of hoursChanges) {
      if (!latest || c.effective_from > latest.effective_from) latest = c;
    }
    return latest?.id ?? null;
  }, [hoursChanges]);
```

(4) Die komplette Funktion `const handleDeleteHoursChange = (changeId: string) => { … };` ersetzen durch:

```ts
  const finishDelete = async () => {
    setDeleting(null);
    await fetchHoursChanges();
    onChanged();
  };
```

(5) Im JSX das Element `<ConfirmDialog … />` (sieben Props) löschen.

(6) Unter `<h3 className="font-semibold text-gray-900 mb-3">Verlauf</h3>`:

```tsx
                {deleting && (
                  <WhDeletePanel
                    key={deleting.id}
                    userId={userId}
                    change={deleting}
                    onCancel={() => setDeleting(null)}
                    onDone={finishDelete}
                  />
                )}
```

(7) In der Verlaufszeile den Ausdruck `{change.id === lockedEarliestId ? ( … ) : ( … )}` ersetzen durch:

```tsx
                          {change.id === youngestId && (
                            <button
                              type="button"
                              onClick={() => setDeleting(change)}
                              className="text-red-600 hover:text-red-800"
                              title="Löschen"
                            >
                              <Trash2 size={18} />
                            </button>
                          )}
```

- [ ] **Step 6: Tests laufen lassen — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/ --pool=threads`, `npx tsc --noEmit`, `npx eslint src/pages/admin/users/`
Expected: PASS, `tsc` ohne Ausgabe, eslint `0 errors` (kein ungenutzter `useConfirm`-Import mehr).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/admin/users/WhDeletePanel.tsx frontend/src/pages/admin/users/workingHoursTexts.ts frontend/src/pages/admin/users/WorkingHoursModal.tsx frontend/src/pages/admin/users/WorkingHoursModal.test.tsx
git commit -F - <<'EOF'
feat(bloecke): Löschen nur an der jüngsten Zeile mit delete-preview, Rücksetzung auf den vorherigen Stand und rückwirkendem Löschen

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 21: Anlegeformular mit Blöcken, Knopf „Arbeitszeit anpassen…", Benutzerliste (Spec 12.1, 12.2, E28, E58)

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx` (Importe, Zustand, Submit, Wochenstunden-/Arbeitstage-Eingabe beim Anlegen, Modus-Abschnitt, Knopftexte)
- Modify: `frontend/src/pages/admin/Users.tsx` (Dialog-Props, Titel/aria-Labels)
- Test: `frontend/src/pages/admin/users/UserForm.test.tsx` (Knopfname, neuer `describe`-Block), `frontend/src/pages/admin/Users.test.tsx` (Fake-Dialog, neuer Test)

**Interfaces:**
- Consumes: `WorkBlocksEditor` (Task 17); `deriveTargets`, `emptyWeek`, `validateWeekBlocks` (Task 16); `UserCreate.work_blocks` (Task 4); `WorkingHoursModal`-Props `currentBlocks`, `trackHours` (Task 18b); `User.work_blocks_today`, `UserForm`-Prop `displayBlocks` (PR1)
- Produces: Anlegen mit „Gleichmäßig / Nach Tagen / Nach Arbeitsblöcken" (Radiogruppe; „Nach Tagen" behält die `id="use_daily_schedule"`), Payload mit `work_blocks` + abgeleiteten Feldern; Knopftext „Arbeitszeit anpassen…" in `UserForm`; Uhr-Symbol der Liste mit Titel „Arbeitszeit & Wochenstunden" und aria-Label „Arbeitszeit & Wochenstunden für ‹Vorname Nachname›" bzw. „Arbeitszeit & Wochenstunden anzeigen"

- [ ] **Step 1: Failing tests schreiben**

Aus `frontend/`:

```bash
sed -i 's/Wochenstunden anpassen/Arbeitszeit anpassen/g' src/pages/admin/users/UserForm.test.tsx src/pages/admin/Users.test.tsx
```

An `src/pages/admin/users/UserForm.test.tsx` anhängen:

```tsx
describe('Spec 2026-10-08 (12.2): Anlegen mit Arbeitszeit-Blöcken', () => {
  function fillBasics() {
    fireEvent.change(screen.getByLabelText(/Benutzername/i), { target: { value: 'blockneu' } });
    fireEvent.change(screen.getByLabelText('Passwort *'), { target: { value: 'TestPass123!' } });
    fireEvent.change(screen.getByLabelText('Vorname'), { target: { value: 'Anna' } });
    fireEvent.change(screen.getByLabelText('Nachname'), { target: { value: 'Beispiel' } });
  }

  function enterAnnaMonday() {
    fireEvent.click(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 1 bis'), { target: { value: '12:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 2 von'), { target: { value: '15:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '18:00' } });
    fireEvent.change(screen.getByLabelText('Mo Pause innerhalb der Blöcke (Min)'), { target: { value: '30' } });
  }

  it('drei Modi; „Nach Arbeitsblöcken" zeigt den Editor und leitet Wochenstunden/Arbeitstage schreibgeschützt ab', () => {
    renderForm({ editUser: null });
    expect(screen.getByRole('radio', { name: 'Gleichmäßig' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Nach Tagen' })).not.toBeChecked();
    enterAnnaMonday();
    expect(screen.getByTestId('f-blocks-day-0')).toHaveTextContent('Tagessoll 6:30 h');
    const weekly = document.getElementById('f-weekly-hours') as HTMLInputElement;
    expect(weekly).toHaveAttribute('readonly');
    expect(weekly.value).toBe('6.5');
    const workDays = document.getElementById('f-work-days') as HTMLInputElement;
    expect(workDays).toHaveAttribute('readonly');
    expect(workDays.value).toBe('1');
  });

  it('sendet work_blocks samt abgeleiteten Feldern (der Server leitet erneut ab, 4.2)', async () => {
    renderForm({ editUser: null });
    fillBasics();
    enterAnnaMonday();
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const body = postMock.mock.calls[0][1];
    expect(body).toMatchObject({
      use_daily_schedule: true, weekly_hours: 6.5, work_days_per_week: 1, hours_monday: 6.5, hours_tuesday: 0,
    });
    expect(body.work_blocks[0]).toEqual({
      blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30,
    });
    expect(body.work_blocks[1]).toEqual({ blocks: [], pause_minutes: 0 });
  });

  it('sperrt Speichern bei ungültigen Blöcken mit der wortgleichen Meldung (3.4)', () => {
    renderForm({ editUser: null });
    fireEvent.click(screen.getByRole('radio', { name: 'Nach Arbeitsblöcken' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Mindestens ein Wochentag braucht einen Block.');
    expect(screen.getByRole('button', { name: /Speichern/i })).toBeDisabled();
  });

  it('ohne Stundenzählung: Editor ausgeblendet, keine Blöcke im Payload', async () => {
    renderForm({ editUser: null });
    fillBasics();
    enterAnnaMonday();
    fireEvent.click(screen.getByLabelText('Stundenzählung aktiv (Soll-Stunden werden berechnet)'));
    expect(screen.queryByRole('radio', { name: 'Nach Arbeitsblöcken' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1]).not.toHaveProperty('work_blocks');
  });

  it('Bearbeiten: Knopf heißt „Arbeitszeit anpassen…", kein Modus-Umschalter', () => {
    renderForm({ editUser: baseEditUser });
    expect(screen.getByRole('button', { name: 'Arbeitszeit anpassen…' })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Nach Arbeitsblöcken' })).not.toBeInTheDocument();
  });
});
```

`baseEditUser` ist im `describe('Task 6+11: …')` lokal deklariert — für den neuen Block die Deklaration (`const baseEditUser = { … };`) unverändert auf Modulebene vor beide `describe`-Blöcke ziehen.

In `src/pages/admin/Users.test.tsx` `FakeWorkingHoursModal` ersetzen durch:

```tsx
function FakeWorkingHoursModal(props: { onChanged: () => void; currentBlocks?: unknown; trackHours?: boolean }) {
  return (
    <div>
      <span data-testid="modal-track-hours">{String(props.trackHours)}</span>
      <span data-testid="modal-blocks">{JSON.stringify(props.currentBlocks ?? null)}</span>
      <button type="button" onClick={props.onChanged}>
        Stundenänderung speichern (simuliert)
      </button>
    </div>
  );
}
```

und am Dateiende anhängen:

```tsx
describe('Spec 2026-10-08 (12.1): Dialog bekommt heute gültige Blöcke und Stundenzählung', () => {
  it('reicht work_blocks_today und track_hours an den Dialog weiter', async () => {
    const blocks = [{ blocks: [{ start: '08:00', end: '12:00' }], pause_minutes: 0 }];
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/admin/users-overview')) return Promise.resolve({ data: [] });
      if (String(url) === '/admin/users') {
        return Promise.resolve({ data: [makeUser({ track_hours: false, work_blocks_today: blocks as never })] });
      }
      return Promise.resolve({ data: [] });
    });
    renderPage();
    await screen.findAllByText('Doe, Jane');
    fireEvent.click(screen.getAllByRole('button', { name: 'Arbeitszeit & Wochenstunden für Jane Doe' })[0]);
    expect(await screen.findByTestId('modal-track-hours')).toHaveTextContent('false');
    expect(screen.getByTestId('modal-blocks')).toHaveTextContent('08:00');
  });
});
```

- [ ] **Step 2: Tests laufen lassen — müssen scheitern**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/UserForm.test.tsx src/pages/admin/Users.test.tsx --pool=threads`
Expected: FAIL — kein Radio „Gleichmäßig"/„Nach Arbeitsblöcken", Knopf heißt noch „Wochenstunden anpassen…", kein Uhr-Knopf mit dem neuen aria-Label.

- [ ] **Step 3: `UserForm.tsx`**

(1) Den Import aus `'../../../utils/workBlocks'` (PR1: `formatWeekBlocks, isLegacyWeek`) ersetzen durch:

```ts
import { deriveTargets, emptyWeek, formatWeekBlocks, isLegacyWeek, validateWeekBlocks } from '../../../utils/workBlocks';
import WorkBlocksEditor from '../../../components/WorkBlocksEditor';
```

(2) Nach `const [submitting, setSubmitting] = useState(false);`:

```ts
  // Spec 2026-10-08 (12.2/E28): Startvertrag mit Arbeitszeit-Blöcken — nur
  // beim Anlegen; danach ändern sich Blöcke ausschließlich über den Dialog.
  const [blocksMode, setBlocksMode] = useState(false);
  const [createBlocks, setCreateBlocks] = useState<WeekBlocks>(() => emptyWeek());
```

(3) Unmittelbar vor `const handleSubmit = async (e: React.FormEvent) => {`:

```ts
  // Ohne Stundenzählung kein Block-Modus (12.2): der Abschnitt ist dann
  // ausgeblendet und der Payload trägt keine Blöcke.
  const createBlocksActive = !editUser && blocksMode && formData.track_hours;
  const createDerived = deriveTargets(createBlocks);
  const createBlocksError = createBlocksActive ? validateWeekBlocks(createBlocks) : null;
```

(4) In `handleSubmit` nach `if (submitting) return;`:

```ts
    if (createBlocksError) return;
```

(5) `const res = await apiClient.post('/admin/users', payload);` ersetzen durch:

```ts
        // Spec 4.2: der Server leitet aus `work_blocks` erneut ab und
        // überschreibt; die mitgeschickten Werte halten den Payload in sich stimmig.
        const createPayload = createBlocksActive
          ? {
            ...payload,
            use_daily_schedule: true,
            weekly_hours: createDerived.weeklyHours,
            work_days_per_week: createDerived.workDays,
            hours_monday: createDerived.hours[0],
            hours_tuesday: createDerived.hours[1],
            hours_wednesday: createDerived.hours[2],
            hours_thursday: createDerived.hours[3],
            hours_friday: createDerived.hours[4],
            work_blocks: createBlocks,
          }
          : payload;
        const res = await apiClient.post('/admin/users', createPayload);
```

(6) Im Anlege-Zweig des Wochenstunden-Felds (`<input id="f-weekly-hours" type="number" … />`) `value={formData.weekly_hours}` ersetzen durch `value={createBlocksActive ? createDerived.weeklyHours : formData.weekly_hours}` und nach `onChange={…}` ergänzen `readOnly={createBlocksActive}`; im Anlege-Zweig von „Arbeitstage pro Woche" (`<input id="f-work-days" …>`) ebenso `value={createBlocksActive ? createDerived.workDays : formData.work_days_per_week}` und `readOnly={createBlocksActive}`.

(7) Im Anlege-Zweig des Abschnitts „Daily Schedule Toggle" den Block

```tsx
                  <div className="flex items-center space-x-2 mb-3">
                    <input
                      type="checkbox"
                      id="use_daily_schedule"
                      …
                    </label>
                  </div>
```

(vom `<div className="flex items-center space-x-2 mb-3">` bis zu seinem schließenden `</div>`) ersetzen durch:

```tsx
                  <fieldset className="mb-3">
                    <legend className="text-sm font-medium text-gray-700 mb-1">Arbeitszeit</legend>
                    <div className="flex flex-wrap gap-4">
                      <label className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer">
                        <input
                          type="radio"
                          name="f-schedule-mode"
                          checked={!createBlocksActive && !formData.use_daily_schedule}
                          onChange={() => {
                            setBlocksMode(false);
                            setFormData({ ...formData, use_daily_schedule: false });
                          }}
                          className="w-4 h-4 text-primary border-gray-300 focus:ring-primary"
                        />
                        Gleichmäßig
                      </label>
                      <label className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer">
                        <input
                          type="radio"
                          id="use_daily_schedule"
                          name="f-schedule-mode"
                          checked={!createBlocksActive && formData.use_daily_schedule}
                          onChange={() => {
                            setBlocksMode(false);
                            setFormData({ ...formData, use_daily_schedule: true });
                          }}
                          className="w-4 h-4 text-primary border-gray-300 focus:ring-primary"
                        />
                        {formData.use_fixed_monthly_target ? 'Nach Tagen (geplante Anwesenheit)' : 'Nach Tagen'}
                      </label>
                      <label className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer">
                        <input
                          type="radio"
                          name="f-schedule-mode"
                          checked={createBlocksActive}
                          onChange={() => setBlocksMode(true)}
                          className="w-4 h-4 text-primary border-gray-300 focus:ring-primary"
                        />
                        Nach Arbeitsblöcken
                      </label>
                    </div>
                  </fieldset>
```

Die Bedingung des Tagesstunden-Rasters `{formData.use_daily_schedule && (` → `{!createBlocksActive && formData.use_daily_schedule && (`; direkt danach einfügen:

```tsx
                  {createBlocksActive && (
                    <>
                      <WorkBlocksEditor value={createBlocks} onChange={setCreateBlocks} idPrefix="f-blocks" />
                      <p className="text-xs text-gray-500 mt-2">
                        Wochenstunden, Tagessoll und Arbeitstage werden aus den Blöcken abgeleitet.
                      </p>
                    </>
                  )}
```

(8) Am Speichern-Knopf `disabled={submitting}` → `disabled={submitting || !!createBlocksError}`.

(9) Texte: `sed -i 's/Wochenstunden anpassen…/Arbeitszeit anpassen…/g' src/pages/admin/users/UserForm.tsx` (Knopf und die drei Hinweise „Änderung über „…" mit Wirkungsdatum.").

- [ ] **Step 4: `Users.tsx`**

Im `<WorkingHoursModal …>` nach `currentWorkDays={hoursModalUser.work_days_per_week}`:

```tsx
          // Spec 2026-10-08 (12.1): heute gültige Blöcke und Stundenzählung —
          // ohne Stundenzählung kein Block-Modus (P24).
          currentBlocks={hoursModalUser.work_blocks_today ?? null}
          trackHours={hoursModalUser.track_hours}
```

Titel und aria-Labels des Uhr-Symbols (E58) — aus `frontend/`:

```bash
sed -i \
  -e 's/title="Wochenstunden & Tagesplan"/title="Arbeitszeit \& Wochenstunden"/g' \
  -e 's/aria-label={`Wochenstunden & Tagesplan für /aria-label={`Arbeitszeit \& Wochenstunden für /' \
  -e 's/aria-label="Wochenstunden & Tagesplan anzeigen"/aria-label="Arbeitszeit \& Wochenstunden anzeigen"/' \
  -e 's/Wochenstunden anpassen…/Arbeitszeit anpassen…/g' \
  src/pages/admin/Users.tsx
grep -c "Tagesplan\"\|Tagesplan für\|Tagesplan anzeigen" src/pages/admin/Users.tsx
```

Expected: `0`.

- [ ] **Step 5: Tests laufen lassen — müssen grün sein**

Run (aus `frontend/`): `npx vitest run src/pages/admin/users/UserForm.test.tsx src/pages/admin/Users.test.tsx --pool=threads`, `npx tsc --noEmit`, dann die volle Suite `npx vitest run --pool=threads`
Expected: PASS; volle Suite ohne neue Fehlschläge gegenüber den Ausgangszahlen; `tsc` ohne Ausgabe.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/admin/users/UserForm.tsx frontend/src/pages/admin/users/UserForm.test.tsx frontend/src/pages/admin/Users.tsx frontend/src/pages/admin/Users.test.tsx
git commit -F - <<'EOF'
feat(bloecke): Anlegen mit Arbeitszeit-Blöcken, Knopf „Arbeitszeit anpassen…", Dialog mit heute gültigen Blöcken

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 22: E2E — `work-blocks.spec.ts` und `user-management.spec.ts` (Spec 17.8)

**Files:**
- Create: `e2e/tests/admin/work-blocks.spec.ts`
- Modify: `e2e/tests/admin/user-management.spec.ts`

**Interfaces:**
- Consumes: Fixtures `adminPage`, `adminApi`, `createUser`, `createTimeEntry`, `testEmployee`, `employeePage`, `browser` (Bestand, `e2e/fixtures` bzw. Playwright); `ApiHelper` (`e2e/helpers/api.helper.ts`); `daysAgo`, `weekdayFromNow`, `today`, `currentMonth` (`e2e/helpers/date.helper.ts`); Oberflächen aus Task 16–21; aus PR2: Profilkarte „Meine Arbeitszeit" (Task 10), `CreditOverrideButton` mit Bestätigung „Zeit anerkennen" und Toast „Zeit anerkannt" (Task 15), `RawStampNote`-Kennzeichen „anerkannt" (Task 14), „Anrechnung beantragen" in der Zeiterfassung, `ChangeRequestForm` mit Titel „Änderungsantrag: Anrechnung beantragen", Antragsprüfung mit Kennzeichen „Anrechnung beantragt" und Knopf „Genehmigen und anerkennen" (Task 16); Dashboard-Hinweis (Task 15)
- Produces: E2E-Szenarien 1–8 aus 17.8 in `work-blocks.spec.ts`

Je Test **eigene** Mitarbeitende (`workers: 2`; eine Neuberechnung kappt sonst fremde Einträge). Die Zeiteinträge der Tests 2, 3 und 8 liegen nachmittags bzw. in der Lücke, keiner über sechs Stunden — §4 (#499) greift dort nie. Die Tests 5 und 7 brauchen den Fall K1 (08:00–18:00 über die Lücke 12:15–14:45): das Lückensegment (150 Min ≥ 15) zählt nach PR1 Task 5 als Pausenabschnitt, §4 ist damit erfüllt, und §3 rechnet beim Anlegen mit den angerechneten 7:30 h; nach dem Anerkennen blockiert §3/§4 nie (P4). Beide Tests nehmen einen **vergangenen** Werktag (`weekdayFromNow(-7)`, überspringt Wochenende und Feiertage — dort gäbe es keine Blöcke und damit keine nicht angerechnete Zeit), weil „Anrechnung beantragen" nur an vergangenen Tagen angeboten wird; liegt er im Vormonat, blättern sie zurück.

- [ ] **Step 1: `work-blocks.spec.ts` anlegen**

```ts
import { test, expect } from '../../fixtures/base.fixture';
import { purgeUser } from '../../fixtures/test-data.fixture';
import { ApiHelper } from '../../helpers/api.helper';
import { currentMonth, daysAgo, today, weekdayFromNow } from '../../helpers/date.helper';
import type { Browser, Page } from '@playwright/test';

// Spec 2026-10-08, 17.8 — Arbeitszeit-Blöcke Ende zu Ende.
type Day = { blocks: { start: string; end: string }[]; pause_minutes: number };
const day = (spans: [string, string][], pause = 0): Day => ({
  blocks: spans.map(([start, end]) => ({ start, end })), pause_minutes: pause,
});
const week = (d: Day): Day[] => [d, d, d, d, d];
const SPLIT = week(day([['08:00', '12:00'], ['15:00', '18:00']]));      // Tagessoll 7:00
const MORNING = week(day([['08:00', '12:00']]));                         // Tagessoll 4:00

const deDate = (iso: string) => iso.split('-').reverse().join('.');

async function employeeWithBlocks(createUser: (d: Record<string, unknown>) => Promise<any>, blocks: Day[], tag: string) {
  const unique = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  return createUser({
    username: `e2e_blocks_${tag}_${unique}`,
    password: 'TestPass123!',
    first_name: 'Block',
    last_name: `${tag}${unique}`,
    role: 'employee',
    weekly_hours: 40,
    work_days_per_week: 5,
    vacation_days: 30,
    track_hours: true,
    work_blocks: blocks,
  });
}

// Login als die eigene Testperson (Muster `employeePage` in e2e/fixtures/test-data.fixture.ts):
// Refresh-Cookie aus dem Node-Login in einen frischen Kontext, Onboarding serverseitig abschließen.
async function loginAs(browser: Browser, username: string, password: string) {
  const api = new ApiHelper();
  const login = await api.login(username, password);
  await api.post('/auth/onboarding/complete').catch(() => {});
  const user = { ...login.user, onboarding_completed_at: new Date().toISOString() };
  const context = await browser.newContext();
  await context.addCookies([{
    name: 'refresh_token', value: api.refreshCookie, url: 'http://localhost/api/auth/refresh',
    httpOnly: true, sameSite: 'Lax',
  }]);
  const page = await context.newPage();
  await page.addInitScript((u) => {
    localStorage.setItem('auth-storage', JSON.stringify({ state: { user: u, isAuthenticated: true }, version: 0 }));
  }, user);
  await page.goto('/');
  await page.waitForURL('/');
  return { page, context };
}

async function openDialog(page: Page, lastName: string) {
  await page.goto('/admin/users');
  await expect(page.getByRole('heading', { name: 'Benutzerverwaltung' })).toBeVisible();
  await page.getByPlaceholder('Suche nach Name oder Benutzername...').fill(lastName);
  const clock = page.getByRole('button', { name: new RegExp(`^Arbeitszeit & Wochenstunden für Block ${lastName}$`) }).first();
  await expect(clock).toBeVisible({ timeout: 5000 });
  await clock.click();
  const dialog = page.getByRole('dialog', { name: /Wochenstunden/i });
  await expect(dialog).toBeVisible({ timeout: 5000 });
  return dialog;
}

test.describe('Arbeitszeit-Blöcke (Spec 2026-10-08)', () => {
  test('1: Anlegen mit Blöcken → Tagessoll in der Benutzerliste', async ({ adminPage, adminApi }) => {
    const unique = `${Date.now()}`;
    const lastName = `Anlage${unique}`;
    await adminPage.goto('/admin/users');
    await adminPage.getByRole('button', { name: 'Neue:r Mitarbeiter:in' }).click();
    await adminPage.locator('#f-username').fill(`e2e_blocks_new_${unique}`);
    await adminPage.locator('#f-firstname').fill('Block');
    await adminPage.locator('#f-lastname').fill(lastName);
    await adminPage.locator('#f-password').fill('TestPass123!');
    await adminPage.getByRole('radio', { name: 'Nach Arbeitsblöcken' }).check();
    await adminPage.getByRole('button', { name: 'Mo: Block hinzufügen' }).click();
    await adminPage.getByLabel('Mo Block 1 von').fill('08:00');
    await adminPage.getByLabel('Mo Block 1 bis').fill('12:00');
    await adminPage.getByRole('button', { name: 'Mo: Block hinzufügen' }).click();
    await adminPage.getByLabel('Mo Block 2 von').fill('15:00');
    await adminPage.getByLabel('Mo Block 2 bis').fill('18:00');
    await adminPage.getByLabel('Mo Pause innerhalb der Blöcke (Min)').fill('30');
    await expect(adminPage.getByTestId('f-blocks-day-0')).toContainText('Tagessoll 6:30 h');
    await adminPage.getByRole('button', { name: 'Speichern' }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'erstellt' })).toBeVisible({ timeout: 10000 });

    const users = await adminApi.get('/admin/users?include_inactive=true&include_hidden=true&limit=500');
    const created = users.find((u: any) => u.last_name === lastName);
    try {
      expect(created).toBeTruthy();
      expect([created.hours_monday, created.weekly_hours, created.work_days_per_week]).toEqual([6.5, 6.5, 1]);
      await adminPage.getByPlaceholder('Suche nach Name oder Benutzername...').fill(lastName);
      await expect(adminPage.locator('tr', { hasText: lastName }).first()).toContainText('6.5');
    } finally {
      if (created) await purgeUser(adminApi, created.id);
    }
  });

  test('2: rückwirkende Verlängerung — Vorschau nennt den Eintrag, Journal zeigt neuen Wert und Lückenzeile', async ({
    adminPage, createUser, createTimeEntry,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Verl');
    const workday = weekdayFromNow(-14);
    // 11:00–16:00 liegt über der Lücke (12:15–14:45 nach Puffer) → 2:30 h angerechnet.
    await createTimeEntry(user.id, { date: workday, start_time: '11:00', end_time: '16:00', break_minutes: 0 });

    const dialog = await openDialog(adminPage, user.last_name);
    await dialog.getByLabel('Gültig ab').fill(daysAgo(21));
    // Nachmittag 14:00–18:00 mit 60 Min Pause: Tagessoll bleibt 7:00 h, die Lücke schrumpft.
    for (const label of ['Mo', 'Di', 'Mi', 'Do', 'Fr']) {
      await dialog.getByLabel(`${label} Block 2 von`).fill('14:00');
      await dialog.getByLabel(`${label} Pause innerhalb der Blöcke (Min)`).fill('60');
    }
    await expect(dialog.getByText(/^Rückwirkende Änderung:/)).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText('Zeiteinträge: 1 neu berechnet')).toBeVisible();
    await expect(dialog.getByRole('region', { name: 'Verkürzung' })).toHaveCount(0);
    await dialog.getByLabel('Ich habe die Auswirkungen geprüft und möchte speichern').check();
    await dialog.getByRole('button', { name: 'Speichern' }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert. 1 Zeiteintrag neu berechnet' }))
      .toBeVisible({ timeout: 10000 });

    await adminPage.goto(`/admin/users/${user.id}/journal`);
    await expect(adminPage.getByRole('heading', { name: 'Monatsjournal' })).toBeVisible({ timeout: 10000 });
    if (workday.slice(0, 7) !== currentMonth()) {
      await adminPage.getByRole('button', { name: 'Vorheriger Monat' }).click();
    }
    await expect(adminPage.getByText(/1:30 h zwischen den Blöcken nicht angerechnet/).first()).toBeVisible({ timeout: 10000 });
  });

  test('3: Verkürzung — Standard „Ab heute", danach rückwirkend mit Grund und Haken', async ({
    adminPage, createUser, createTimeEntry,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Kurz');
    await createTimeEntry(user.id, { date: weekdayFromNow(-14), start_time: '15:00', end_time: '18:00', break_minutes: 0 });

    const dialog = await openDialog(adminPage, user.last_name);
    const shorten = async () => {
      for (const label of ['Mo', 'Di', 'Mi', 'Do', 'Fr']) {
        await dialog.getByLabel(`${label} Block 2 bis`).fill('17:00');
      }
    };
    await dialog.getByLabel('Gültig ab').fill(daysAgo(21));
    await shorten();
    const region = dialog.getByRole('region', { name: 'Verkürzung' });
    await expect(region).toBeVisible({ timeout: 10000 });
    await expect(region.getByText(/^1 Eintrag verliert angerechnete Zeit/)).toBeVisible();
    const lossless = region.getByRole('radio', {
      name: `Ab heute (${deDate(today())}) wirksam – vergangene Einträge bleiben unverändert`,
    });
    await expect(lossless).toBeChecked();
    const save = dialog.getByRole('button', { name: 'Speichern' });
    await expect(save).toBeEnabled({ timeout: 10000 });
    await save.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert' }).first()).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(today())} bis heute:`))).toBeVisible({ timeout: 5000 });

    // Dieselbe Kürzung jetzt rückwirkend: die nächste Änderung (heute) begrenzt
    // das verlustfreie Datum → nur Option 2 (P25).
    await dialog.getByLabel('Gültig ab').fill(daysAgo(21));
    await expect(region).toBeVisible({ timeout: 10000 });
    await expect(region.getByRole('radio', { name: /^Ab heute/ })).toHaveCount(0);
    await expect(region.getByLabel('Grund').locator('option')).toHaveText([
      'Bitte wählen…', 'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)', 'Mit der beschäftigten Person vereinbart',
      'Sonstiges',
    ]);
    await expect(save).toBeDisabled();
    await region.getByLabel('Grund').selectOption('erfassungsfehler');
    await region.getByLabel('Begründung').fill('Nachmittagsblock war falsch hinterlegt');
    await region.getByRole('checkbox', { name: /hinterlegte Arbeitszeit falsch war/ }).check();
    await dialog.getByLabel('Ich habe die Auswirkungen geprüft und möchte speichern').check();
    await expect(save).toBeEnabled();
    await save.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: '1 Zeiteintrag neu berechnet' })).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(daysAgo(21))} bis `))).toBeVisible();
  });

  test('4: rückwirkende Soll-Erhöhung ohne verlierenden Eintrag verlangt Grund und Haken (19.1 Nr. 1)', async ({
    adminPage, createUser,
  }) => {
    const user = await employeeWithBlocks(createUser, MORNING, 'Soll');
    const dialog = await openDialog(adminPage, user.last_name);
    await dialog.getByLabel('Gültig ab').fill(daysAgo(14));
    for (const label of ['Mo', 'Di', 'Mi', 'Do', 'Fr']) {
      await dialog.getByLabel(`${label} Block 1 bis`).fill('13:00');
    }
    const region = dialog.getByRole('region', { name: 'Verkürzung' });
    await expect(region).toBeVisible({ timeout: 10000 });
    await expect(region.getByText(/^Das Überstundenkonto sinkt im Wirkungsbereich um .* \(höheres Soll\), obwohl kein Eintrag angerechnete Zeit verliert$/))
      .toBeVisible();
    await region.getByRole('radio', { name: /^Rückwirkend ab/ }).check();
    const save = dialog.getByRole('button', { name: 'Speichern' });
    await dialog.getByLabel('Ich habe die Auswirkungen geprüft und möchte speichern').check();
    await expect(save).toBeDisabled();
    await region.getByLabel('Grund').selectOption('einvernehmlich');
    await region.getByLabel('Begründung').fill('Mit der Mitarbeiterin vereinbart');
    await region.getByRole('checkbox', { name: /mit der beschäftigten Person vereinbart ist/ }).check();
    await expect(save).toBeEnabled();
    await save.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert' }).first()).toBeVisible({ timeout: 10000 });
  });

  test('5: Anerkennen im Admin-Dashboard — Kennzeichen „anerkannt", Netto 10:00 (13.3)', async ({
    adminPage, adminApi, createUser, createTimeEntry,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Anerk');
    const workday = weekdayFromNow(-7);
    // K1: 08:00–18:00 über die Lücke → 7:30 h angerechnet, 2:30 h nicht angerechnet.
    const entry = await createTimeEntry(user.id, { date: workday, start_time: '08:00', end_time: '18:00', break_minutes: 0 });

    await adminPage.goto('/admin');
    await expect(adminPage.getByRole('heading', { name: 'Admin-Dashboard' })).toBeVisible();
    if (workday.slice(0, 7) !== currentMonth()) {
      await adminPage.getByRole('button', { name: 'Vorheriger Monat' }).click();
    }
    await adminPage.waitForLoadState('networkidle');
    const employeeRow = adminPage.locator(`[aria-label*="${user.last_name}"]`).first();
    await expect(employeeRow).toBeVisible({ timeout: 10000 });
    await employeeRow.click();
    // Das Detail-Modal über seinen Schließen-Knopf adressieren — der Bestätigungsdialog ist ein zweiter Dialog.
    const details = adminPage.getByRole('dialog').filter({
      has: adminPage.getByRole('button', { name: `Details für ${user.first_name} ${user.last_name} schließen` }),
    });
    await expect(details).toBeVisible({ timeout: 5000 });
    const row = details.locator('tr').filter({
      has: adminPage.locator(`button[aria-label="Eintrag vom ${deDate(workday)} bearbeiten"]`),
    });
    await expect(row).toBeVisible({ timeout: 10000 });

    await row.getByRole('button', { name: 'Anerkennen' }).click();
    await expect(adminPage.getByText(/^Die gesamte gestempelte Zeit \(08:00–18:00\) wird angerechnet\./)).toBeVisible();
    await adminPage.getByRole('button', { name: 'Zeit anerkennen' }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Zeit anerkannt' }).first()).toBeVisible({ timeout: 10000 });

    await expect(row.getByText('anerkannt', { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(row).toContainText('10:00 h');   // Netto-Spalte (PR2 Task 14), vorher 7:30 h
    await expect(row.getByRole('button', { name: 'Anerkennen' })).toHaveCount(0);
    const entries = await adminApi.get(`/time-entries?user_id=${user.id}&month=${workday.slice(0, 7)}`);
    const recognized = entries.find((e: any) => e.id === entry.id);
    expect([recognized.credit_override, recognized.net_hours, recognized.not_credited_minutes]).toEqual([true, 10, 0]);
  });

  test('6: Mitarbeiter-Sicht — Profilkarte und Dashboard-Hinweis nach einer Änderung „ab heute"', async ({
    adminApi, employeePage, testEmployee,
  }) => {
    const blocks = week(day([['08:00', '12:00'], ['13:00', '17:00']]));
    await adminApi.post(`/admin/users/${testEmployee.id}/working-hours-changes`, { effective_from: today(), blocks });

    await employeePage.goto('/');
    await expect(employeePage.getByText(new RegExp(`Ihre Arbeitszeit wurde ab ${deDate(today()).replace(/\./g, '\\.')} geändert`)))
      .toBeVisible({ timeout: 10000 });

    await employeePage.goto('/profile');
    await expect(employeePage.getByRole('heading', { name: 'Meine Arbeitszeit' })).toBeVisible({ timeout: 10000 });
    await expect(employeePage.getByRole('list', { name: 'Arbeitszeit heute' })).toContainText('Mo 08:00–12:00 + 13:00–17:00');
  });

  test('7: Mitarbeiterin beantragt die Anrechnung, Verwaltung genehmigt und erkennt an (P21)', async ({
    browser, adminPage, adminApi, createUser, createTimeEntry,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Antrag');
    const workday = weekdayFromNow(-7);  // Anträge gibt es nur für vergangene Tage
    const entry = await createTimeEntry(user.id, { date: workday, start_time: '08:00', end_time: '18:00', break_minutes: 0 });
    const reason = `E2E Anrechnung ${Date.now()}-${Math.random().toString(36).slice(2, 8)}: Patienten in der Pause versorgt`;

    const employee = await loginAs(browser, user.username, 'TestPass123!');
    try {
      const page = employee.page;
      await page.goto('/time-tracking');
      if (workday.slice(0, 7) !== currentMonth()) {
        await page.getByRole('button', { name: 'Vorheriger Monat' }).click();
      }
      // Tabelle und Mobilkarte rendern beide eine RawStampNote — nur die sichtbare zählt.
      const request = page.locator('button:visible', { hasText: 'Anrechnung beantragen' });
      await expect(request).toHaveCount(1, { timeout: 10000 });
      await request.click();
      await expect(page.getByRole('heading', { name: 'Änderungsantrag: Anrechnung beantragen' })).toBeVisible({ timeout: 5000 });
      // ChangeRequestForm: Felder „Von"/„Bis" tragen die IDs cr-start/cr-end (Rohstempel vorbelegt, P21).
      await expect(page.locator('#cr-start')).toHaveValue('08:00');
      await expect(page.locator('#cr-end')).toHaveValue('18:00');
      await page.getByPlaceholder('Warum ist diese Änderung notwendig?').fill(reason);
      await page.getByRole('button', { name: 'Antrag stellen' }).click();
      await expect(page.locator('[role="alert"]').filter({ hasText: 'Antrag auf Anrechnung eingereicht' })).toBeVisible({ timeout: 10000 });
    } finally {
      await employee.context.close();
    }

    await adminPage.goto('/admin/change-requests');
    await expect(adminPage.getByRole('heading', { name: 'Änderungsanträge' })).toBeVisible();
    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');
    const card = adminPage.locator('div.bg-white').filter({ hasText: reason }).last();
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.getByText('Anrechnung beantragt')).toBeVisible();
    await expect(card.getByText('Nicht angerechnet (Lücke): 2:30 h')).toBeVisible();
    await card.getByRole('button', { name: 'Genehmigen und anerkennen' }).click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: /genehmigt/ }).first()).toBeVisible({ timeout: 10000 });
    await expect(card).toHaveCount(0, { timeout: 10000 });

    const entries = await adminApi.get(`/time-entries?user_id=${user.id}&month=${workday.slice(0, 7)}`);
    const recognized = entries.find((e: any) => e.id === entry.id);
    expect([recognized.credit_override, recognized.net_hours, recognized.not_credited_minutes]).toEqual([true, 10, 0]);
  });

  test('8: Löschen einer verkürzenden Änderung → Standard „auf vorherigen Stand zurücksetzen" (19.1 Nr. 4)', async ({
    adminPage, adminApi, createUser,
  }) => {
    const user = await employeeWithBlocks(createUser, SPLIT, 'Reset');
    // Soll-Senkung rückwirkend: verlängert (Saldo steigt) → ohne Grund zulässig.
    const lowered = week(day([['08:00', '12:00'], ['15:00', '17:00']]));
    const effective = daysAgo(14);
    await adminApi.post(`/admin/users/${user.id}/working-hours-changes`, { effective_from: effective, blocks: lowered });

    const dialog = await openDialog(adminPage, user.last_name);
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(effective)} bis heute:`))).toBeVisible({ timeout: 5000 });
    await dialog.getByRole('button', { name: 'Löschen' }).click();
    const panel = dialog.getByRole('alertdialog', { name: `Arbeitszeit-Änderung ab ${deDate(effective)} löschen` });
    const region = panel.getByRole('region', { name: 'Verkürzung' });
    await expect(region).toBeVisible({ timeout: 10000 });
    await expect(region.getByRole('radio', { name: `Ab ${deDate(today())} auf den vorherigen Stand zurücksetzen` })).toBeChecked();
    const reset = panel.getByRole('button', { name: 'Zurücksetzen' });
    await expect(reset).toBeEnabled({ timeout: 10000 });
    await reset.click();
    await expect(adminPage.locator('[role="alert"]').filter({ hasText: 'Gespeichert' }).first()).toBeVisible({ timeout: 10000 });

    // Die zurückgesetzte Zeile bleibt stehen (jetzt mit Ende), die neue gilt ab heute.
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(effective)} bis `))).toBeVisible();
    await expect(dialog.getByText(new RegExp(`^Ab ${deDate(today())} bis heute:`))).toBeVisible();
  });
});
```

Hinweis zu Test 8: ist `today()` ein Wochenende, ändert sich am Saldo nichts mehr, aber `earliest_lossless_date` bleibt heute — die Beschriftung bleibt „Ab ‹heute› …" (Spec 9.5, `max(heute, …)`), ein Sonderfall entsteht nicht (Review Focus 3).

- [ ] **Step 2: `user-management.spec.ts` anpassen**

Aus `e2e/`:

```bash
sed -i \
  -e "s/'Wochenstunden anpassen…'/'Arbeitszeit anpassen…'/g" \
  -e "s/name: 'Hinzufügen'/name: 'Speichern'/g" \
  -e "s/hasText: 'hinzugefügt'/hasText: 'Gespeichert'/g" \
  -e "s/Ich habe die Auswirkungen geprüft und möchte trotzdem speichern/Ich habe die Auswirkungen geprüft und möchte speichern/g" \
  tests/admin/user-management.spec.ts
grep -c "Wochenstunden anpassen…'\|'Hinzufügen'\|'hinzugefügt'\|trotzdem speichern" tests/admin/user-management.spec.ts
```

Expected: `0`.

Im Test `'Tagesplan rückwirkend über den Dialog ändern'` erhöht der neue Donnerstag das Soll rückwirkend → Saldo sinkt → Verkürzung nach 9.5 (b). Standard ist dann Option 1 — die Auswirkungs-Box zeigt die Vorschau für heute, „Rückwirkende Änderung:" erschiene nie. Deshalb direkt nach `await expect(dialog.getByText('→ 23,0 h/Woche · 4 Arbeitstage')).toBeVisible();` (vor der Erwartung `/^Rückwirkende Änderung:/`) einfügen:

```ts
      // Spec 9.5 (b), 19.1 Nr. 1: rückwirkende Soll-Erhöhung → Verkürzungs-Kasten;
      // gewollt ist hier die rückwirkende Variante mit Grund und Haken.
      const region = dialog.getByRole('region', { name: 'Verkürzung' });
      await expect(region).toBeVisible({ timeout: 10000 });
      await region.getByRole('radio', { name: /^Rückwirkend ab/ }).check();
      await region.getByLabel('Grund').selectOption('einvernehmlich');
      await region.getByLabel('Begründung').fill('Donnerstag mit der Mitarbeiterin vereinbart');
      await region.getByRole('checkbox', { name: /mit der beschäftigten Person vereinbart ist/ }).check();
```

Die folgenden Bestandserwartungen („Rückwirkende Änderung:", „Tagessoll je Wochentag: … Do 0,0 → 5,0", Speichern gesperrt bis zum Bestätigungshaken, „bis heute: Mo 8,0 / Di 6,0 / Mi 4,0 / Do 5,0 = 23,0 Std/Woche", Basis-Zeile) bleiben unverändert: mit Option 2 zeigt die Box die Vorschau des eingegebenen Datums, und gespeichert wird ab diesem Datum. Der Test `'rückwirkende Stundenänderung warnt und verlangt Bestätigung'` senkt das Soll (40 → 20 h) und bleibt eine Verlängerung — keine weitere Änderung.

- [ ] **Step 3: Listen- und Typprüfung**

Run (aus `e2e/`): `npx --no-install playwright test --list tests/admin/work-blocks.spec.ts tests/admin/user-management.spec.ts` und `npx tsc --noEmit -p .`
Expected: acht Tests in `work-blocks.spec.ts` (Szenarien 1–8), die bisherigen in `user-management.spec.ts`; `tsc` ohne Ausgabe.

- [ ] **Step 4: Lauf gegen den Docker-Stack**

Vorher `.env` mit `LOGIN_RATE_LIMIT=10000/minute` und `REFRESH_RATE_LIMIT=10000/minute`, dann `docker compose build backend frontend && docker compose up -d` (Migration 073 aus PR1 ist im Image). Run (aus `e2e/`):
`npx playwright test tests/admin/work-blocks.spec.ts tests/admin/user-management.spec.ts --output=/tmp/pz-e2e-pr3`
Expected: alle grün. Scheitert Test 2 an „1:30 h zwischen den Blöcken", zuerst prüfen, ob PR2s `RawStampNote` im Journal steht (`grep -n "zwischen den Blöcken" frontend/src/components/RawStampNote.tsx`) — der Wortlaut gehört zu PR2 (13.1), nicht hierher. Scheitern die Tests 5 oder 7 an einem Knopf- oder Toast-Text, gegen PR2 Task 15/16 abgleichen (`grep -n "Zeit anerkennen\|Zeit anerkannt\|Antrag auf Anrechnung eingereicht\|Genehmigen und anerkennen" -r frontend/src`) — die Wortlaute gehören zu PR2, die Tests folgen ihnen.

- [ ] **Step 5: Commit**

```bash
git add e2e/tests/admin/work-blocks.spec.ts e2e/tests/admin/user-management.spec.ts
git commit -F - <<'EOF'
test(bloecke): E2E für Anlegen mit Blöcken, rückwirkende Verlängerung/Verkürzung, Soll-Erhöhung, Anerkennen, Mitarbeiter-Sicht, Anrechnung beantragen und Rücksetzung

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---
### Task 23: Gesamtlauf

Nach den Umbauten an `admin_users`, `calculation_service`, `work_window_service` und den Dialogen laufen bis hier weder alle PG-Suiten noch der Vite-Build, ESLint über `src`, `local-ci.sh` oder die volle E2E-Suite (Task 13 fährt drei PG-Dateien, Task 22 zwei E2E-Specs). Vorbild: PR2 Task 19.

**Files:** keine (nur Prüfung; Funde werden im Bereich des verursachenden Tasks behoben und separat committet)

**Interfaces:**
- Consumes: alle Tasks 1–22
- Produces: Nachweis „PR3 grün" — SQLite-Vollsuite, alle PG-Suiten inkl. `test_reclamp_concurrency.py`, Vitest-Vollsuite, `tsc`, ESLint, Vite-Build, volle Playwright-Suite

- [ ] **Step 1: Backend-Vollsuite (SQLite)**

Run (vorher `pgrep -af pytest`): `rm -f backend/test.db backend/test.db-wal backend/test.db-shm && docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py --ignore=tests/test_073_migration_pg.py --ignore=tests/test_net_hours_parity_pg.py --ignore=tests/test_reclamp_concurrency.py`
Expected: keine neuen Fehlschläge gegenüber den Ausgangszahlen vor Task 1.

- [ ] **Step 2: Postgres-Suiten und Gesamt-CI**

Run: `bash scripts/local-ci.sh`
Expected: alle Stufen grün — Backend SQLite und PostgreSQL mit **allen** PG-Dateien (`test_tenant_rls.py`, `test_purge_user_postgres.py`, `test_concurrency.py`, `test_invalid_uuid_postgres.py`, `test_073_migration_pg.py`, `test_net_hours_parity_pg.py`, `test_reclamp_concurrency.py` mit sechs Tests, keiner `skipped`), Vitest, `tsc`, ESLint, Vite-Build. Läuft die E2E-Stufe mit, vorher die Auth-Rate-Limits anheben (Step 4); hängt Vitest mit dem Fork-Pool, die Stufe mit `--pool=threads` fahren. Die Zahl der PG-Tests entspricht dem Zählkommentar aus Task 13 Step 4.

- [ ] **Step 3: Frontend separat (falls `local-ci.sh` die Stufe übersprungen hat)**

Run (aus `frontend/`): `npx vitest run --pool=threads && npx tsc --noEmit && npx eslint src && npm run build`
Expected: PASS; Vitest ohne neue Fehlschläge gegenüber der Ausgangszahl, `tsc` ohne Ausgabe, eslint `0 errors`, Build ohne Fehler.

- [ ] **Step 4: Volle Playwright-Suite**

In `.env` `LOGIN_RATE_LIMIT=10000/minute` und `REFRESH_RATE_LIMIT=10000/minute` setzen (sonst HTTP-429-Sturm, CLAUDE.md), dann `docker compose build backend frontend && docker compose up -d` (Migration 073 aus PR1 ist im Image). Run (aus `e2e/`):
`npx playwright test --output=/tmp/pz-e2e-pr3-full`
Expected: keine neuen Fehlschläge gegenüber der E2E-Ausgangszahl vor Task 1; `work-blocks.spec.ts` (acht Tests) und `user-management.spec.ts` grün. Ein Fehlschlag in einer fremden Spec, der auf einen Knopf- oder Dialogtext zielt („Wochenstunden anpassen…", „Hinzufügen", „trotzdem speichern"), gehört zu Task 21/22 und wird dort nachgezogen. Danach die beiden Rate-Limit-Zeilen in `.env` wieder entfernen.

- [ ] **Step 5: Rückstände ausschließen**

```bash
grep -rn "Wochenstunden anpassen…" frontend/src/pages frontend/src/components/WorkBlocksEditor.tsx e2e/tests
grep -rn "working-hours-changes/preview" frontend/src | grep -F ".get("
```

Expected: keine Treffer (alter Knopftext nur noch in `DocViewer.tsx` — das zieht PR4 nach; die Vorschau läuft nur noch per `POST`).

---

## Übergabe an PR4

PR4 (Doku) zitiert die folgenden Wortlaute und Namen aus dem Code dieses PRs; ihr Gate (`scripts/check-doc-sync.sh`, Gruppe `group_code`) sucht sie **zusammenhängend** im Quelltext. Wer hier einen Text umformuliert oder über zwei String-Literale verteilt, bricht das Gate — Änderungen an diesen Stellen nur zusammen mit der Spec.

| Schnittstelle / Wortlaut | Ort | Task |
|---|---|---|
| `work_blocks_service.HOURS_FIELDS`, `derive_targets`, `changed_weekdays`, `blocks_text`, `block_break_notices` | `backend/app/services/work_blocks_service.py` | 1, 5 |
| `validators.validate_week_blocks` (Texte 3.4) | `backend/app/schemas/validators.py` | 1 |
| `reclamp_audit.AUDIT_SOURCE`, `REASON_TYPES`, `ReasonType`, `reason_text`, `compose_change_note`, `contract_text`, `summary_note`, `SummaryNote`, `parse_summary_note`, `entry_new_note`, `NOTICE_DAYS`, `notice_text`, `schedule_change_notices` | `backend/app/services/reclamp_audit.py` | 2, 15 |
| `RetroReasonType`, `TimeBlockIn`, `DayBlocksIn`, `RetroReasonFields`, `WorkingHoursChangeCreate.blocks/remove_legacy_window/reset_of_change_id/blocks_json`, `WorkingHoursChangeDelete`, Vorschau-Felder 11.3 | `backend/app/schemas/working_hours_change.py` | 3 |
| `UserCreate.work_blocks` | `backend/app/schemas/user.py` | 4 |
| `RetargetWindow.last_time_entry`, `AbsenceRetarget.f1_clamped/credit_reduction`, `retarget_absence_hours(…, old_full_target_by_date, dry_run)`, `absence_full_targets`, `ScheduleSegment.blocks/block_pauses`, `blocks_changed` | `backend/app/services/calculation_service.py` | 6, 14 |
| `ReclampChange`, `ReclampSkip`, `ReclampResult`, `reclamp_time_entries`, `credited_minutes_for`, `open_entry_loses` | `backend/app/services/work_window_service.py` | 7 |
| `wh_change_service.run_change`, `ChangeImpact`, `preview_fields`, `criteria_text`, `closed_year_detail`, `protection_error`, `reset_body`, `milog_warnings`, `P25_NOTE`, `MILOG_*_WARNING`, `SONSTIGES_CONFIRM_DETAIL` | `backend/app/services/wh_change_service.py` | 8 |
| `POST …/working-hours-changes` (Schutzpaket, Rücksetzung), `POST …/preview`, `POST …/{id}/delete-preview`, `DELETE …/{id}` mit Body; `RESET_CONFLICT_DETAIL`, `PREVIEW_DATE_MISSING` | `backend/app/routers/admin_users.py` | 9–11 |
| `MonthlyDashboard.schedule_change_notices`, `ScheduleChangeNotice` | `backend/app/schemas/reports.py`, `routers/dashboard.py` | 15 |
| `parseHhmm`, `minutesToHm`, `sumBlocks`, `minutesToTargetHours`, `deriveTargets`, `validateWeekBlocks`, `emptyWeek`, `formatBlocksText` | `frontend/src/utils/workBlocks.ts` | 14, 16 |
| `WorkBlocksEditor`, `ScheduleChangeNotices` | `frontend/src/components/` | 15, 17 |
| `WhImpactBox`, `ShorteningChoice` (+ `shorteningHeadlines`, `losslessLabel`, `retroLabel`, `RetroReasonFields`), `WhDeletePanel`, `workingHoursTexts`, `workingHoursTypes` | `frontend/src/pages/admin/users/` | 16, 18a–20 |
| Oberflächentexte: „Arbeitszeit anpassen…", „Arbeitszeit & Wochenstunden", „Nach Arbeitsblöcken", „Pause innerhalb der Blöcke", „Ich habe die Auswirkungen geprüft und möchte speichern", „… wirksam – vergangene Einträge bleiben unverändert", „Rückwirkend ab … mit Neuberechnung", die drei Grundtyp-Beschriftungen, Hilfetext, die drei Bestätigungstexte, Vergütungssatz, „Sonstiges"-Warnung und zweiter Haken, „… auf den vorherigen Stand zurücksetzen", „Rückwirkend löschen mit Neuberechnung", Altfenster-Kasten und seine zwei Aktionen, Moduswechsel-Hinweis, „ohne Wirkung (keine Stundenzählung)", Rechtshinweis und JArbSchG-Zeile, Plan-Hinweise, Toast „Gespeichert. n Zeiteinträge neu berechnet …" | `workingHoursTexts.ts`, `ShorteningChoice.tsx`, `WhDeletePanel.tsx`, `WorkingHoursModal.tsx`, `WorkBlocksEditor.tsx`, `UserForm.tsx`, `work_blocks_service.py`, `wh_change_service.py` | 5, 8, 16–21 |

Doku-Flächen, die PR4 auf diesen Stand bringt (nicht in PR3): `docs/handbuch/*.md` + `frontend/public/help/*.md` (Spiegel), `DocViewer.tsx`, Schnellstart, pzweb-Anleitungen, `docs/BERECHNUNGEN.md`, `docs/GLOSSAR.md`, `CLAUDE.md`, Release-Notes 1.20.0. Die E2E-Specs bleiben bei PR3.
