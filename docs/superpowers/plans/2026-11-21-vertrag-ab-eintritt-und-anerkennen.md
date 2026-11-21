# Vertrag ab Eintritt · Anerkennen einfacher · feste Leiste · Hilfe-Icons — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Admin kann einen versehentlich „ab heute“ gespeicherten Vertrag mit einem Klick ab dem ersten Arbeitstag gelten lassen und dabei betroffene Aushilfe-Einträge im selben Schritt anerkennen. Im Monatsjournal kann sie mehrere Einträge auf einmal anerkennen. Beim Bearbeiten bleibt der Name sichtbar, und an Feldern gibt es „?“-Kurzhilfen mit Link ins Handbuch.

**Architecture:**
- Das Anerkennen im Dialog läuft innerhalb von `wh_change_service.run_change` zwischen Neukappung und Abwesenheits-Rückrechnung. Damit nutzen Vorschau und Speichern denselben Rechenpfad.
- Das Sammel-Anerkennen ist ein eigener Admin-Endpunkt, der `credit_override_service.apply_credit_override` in einer Transaktion je Eintrag ruft.
- Frontend: reine Hilfsfunktionen in `utils/`, Darstellung in den bestehenden Komponenten. Die Kurzhilfen stehen in einem Register mit Anker-Test.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, pytest (SQLite plus ein PG-Test), React 18, TypeScript, Tailwind, Vitest mit RTL, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-20-vertrag-ab-eintritt-und-anerkennen-design.md`

## Global Constraints

- **Keine Migration.** Keine neue Spalte, keine neue `source`. Anerkennen protokolliert weiter als `credit_override` (15 Zeichen).
- **Sperrordnung (P5):** zuerst die Ankersperre der Person (`lock_user_row` / `_lock_and_reload`), dann die Eintragszeilen über `credit_override_service.load_entry_locked`, aufsteigend nach `id`. Fremde oder unbekannte Eintrags-ID → 404 `"Zeiteintrag nicht gefunden"` **vor** jeder Zeilensperre.
- **F-026:** Jede Abfrage auf `time_entries` filtert `TimeEntry.tenant_id == …`.
- **Vorschauen nehmen keine Sperren und protokollieren nie.** Sie rollen zurück.
- **Anerkennen bleibt unumkehrbar.** Es gibt keine Rücknahme, auch nicht beim Löschen einer Arbeitszeit-Änderung.
- **Format von `summary_note` / `parse_summary_note` ist eingefroren** (`app/services/reclamp_audit.py`).
- **Texte:** deutsch, Sie-Form. Fehlertexte zum Anerkennen nur aus `credit_override_service` (`OPEN_ENTRY_DETAIL`, `AUTO_CLOSED_DETAIL`, `start_taken_detail`) bzw. `utils/creditOverride.ts`, nie neu formulieren. Verbotene Begriffe: `frontend/src/handbuch/content/forbiddenTerms.ts`.
- **Hinweistext** (Teil 1, wörtlich, Daten eingesetzt): `Vom {erster Arbeitstag} (erster Arbeitstag) bis zum {Vortag} gilt noch der Vertrag vom Anlegen ({Beschreibung}). Soll die heutige Arbeitszeit schon ab dem ersten Arbeitstag gelten?`. Knopf: `Ab {erster Arbeitstag} übernehmen`.
- **Hinweis unter der Anerkennen-Liste** (wörtlich): `Anerkannte Einträge zählen mit der ganzen gestempelten Zeit, auch bei späteren Änderungen. Anerkennen lässt sich nicht zurücknehmen.`
- **Speichern-Knopf mit Auswahl:** `Speichern und {n} Einträge anerkennen` (n = 1: `Speichern und 1 Eintrag anerkennen`).
- **Sammel-Endpunkt:** 1–200 IDs, alles oder nichts.
- **Tests laufen auf testbox** (globale Regel), mit Ausnahme einzelner Tests unter ~30 s. Backend-Einzeltest lokal:
  `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest <datei>::<test> -q -p no:cacheprovider`
  Im Folgenden kurz `PYTEST <datei>::<test>`. Frontend-Einzeltest: `cd frontend && npx vitest run <datei> --pool=threads`. Vollsuiten: `bash scripts/local-ci.sh` über `tb-run` auf testbox.
- **Doku-Sync:** Quelle des Handbuchs ist `frontend/src/handbuch/content/praxisleitung.ts`. Danach `cd frontend && npm run handbuch:md` und `bash scripts/check-doc-sync.sh all`.

## Review Focus

1. **Admin wählt einen Eintrag an, wählt ihn wieder ab und speichert.** Erwartet: Der abgewählte Eintrag wird nicht anerkannt, die Verkürzung gilt für ihn wie heute (Schutzpaket). Test in Task 4: `test_unselected_entry_still_requires_reason`.
2. **Gewählter Eintrag gehört einer anderen Person** (manipulierter Body). Erwartet: 404 ohne jede Zeilensperre, nichts gespeichert. Test in Task 4: `test_foreign_recognize_id_404_before_lock`.
3. **Eintrag liegt außerhalb der Änderung** (z. B. September bei Wirkung ab 01.10.). Erwartet: 400 „… ist von dieser Änderung nicht betroffen“, nichts gespeichert. Test in Task 3: `test_recognize_id_outside_change_rejected`.
4. **Zwei Einträge am selben Tag, Anerkennen würde den Beginn auf einen belegten Beginn legen.** Erwartet: 409 mit `start_taken_detail`, die ganze Arbeitszeit-Änderung wird zurückgerollt. Test in Task 4: `test_recognize_collision_rolls_back_change`.
5. **Sammel-Anerkennen mit einem automatisch geschlossenen Eintrag in der Auswahl.** Erwartet: 400 `AUTO_CLOSED_DETAIL` mit Datum, kein anderer Eintrag anerkannt. Das Frontend bietet dort kein Häkchen an. Tests in Task 9 (`test_bulk_all_or_nothing_auto_closed`) und Task 10 (`isRecognizable` false bei `auto_closed`).

---

## PR 1 — Hinweis „ab erstem Arbeitstag“, Anerkennen im Dialog, feste Leiste

### Task 1: `is_baseline` in der Verlaufsantwort

**Files:**
- Modify: `backend/app/services/reclamp_audit.py` (Konstante aufnehmen)
- Modify: `backend/app/routers/admin_users.py:1967` (Konstante von dort importieren statt definieren; alle Verwendungen bleiben)
- Modify: `backend/app/schemas/working_hours_change.py:237` (`WorkingHoursChangeResponse`)
- Modify: `frontend/src/pages/admin/users/workingHoursTypes.ts` (`WorkingHoursChange.is_baseline?: boolean`)
- Test: `backend/tests/test_wh_change_baseline_flag.py`

**Interfaces:**
- Produces: `reclamp_audit.BASELINE_ROW_NOTE: str` (gleicher Wortlaut wie heute). `WorkingHoursChangeResponse.is_baseline: bool` ist `True` genau dann, wenn `note == BASELINE_ROW_NOTE`. Gesetzt über `model_validator(mode="after")`.

- [ ] **Step 1: Write the failing test.** `test_baseline_row_flagged_in_listing`:
  - Person mit `first_work_day=date(2026,10,1)`, Blöcke 5 Tage.
  - Änderung ab `2026-11-20` auf Mo + Di per `POST /api/admin/users/{id}/working-hours-changes`.
  - `GET …/working-hours-changes` liefert zwei Zeilen. Die Zeile vom 01.10. hat `is_baseline is True`, die vom 20.11. hat `is_baseline is False`.
  - Zweiter Test `test_replaced_baseline_loses_flag`: Danach Änderung ab `2026-10-01` mit Mo + Di. Die Zeile vom 01.10. hat jetzt `is_baseline is False`.
- [ ] **Step 2:** `PYTEST tests/test_wh_change_baseline_flag.py`. Erwartet: FAIL (Feld fehlt).
- [ ] **Step 3:** Konstante verschieben und Validator ergänzen.
- [ ] **Step 4:** Test erneut. Erwartet: PASS. Zusätzlich `PYTEST tests/test_wh_change_service.py`, erwartet: PASS.
- [ ] **Step 5: Commit** `feat(wh-change): flag the automatic baseline row in the history`

### Task 2: `apply_credit_override` mit Vorher-Stand fürs Protokoll

**Files:**
- Modify: `backend/app/services/credit_override_service.py:72`
- Test: `backend/tests/test_credit_override.py` (neuer Test anhängen)

**Interfaces:**
- Produces: `apply_credit_override(db, entry, *, changed_by_id, on_request: bool, change_request_id=None, audit_before: Optional[TimeEntry] = None) -> bool`. Ist `audit_before` gesetzt, nimmt die Protokollzeile `old_start_time`, `old_end_time` und `old_note` (`work_window_service.credit_summary_text(audit_before)`) daraus statt aus dem aktuellen Eintrag. Alles andere bleibt unverändert.

- [ ] **Step 1: Write the failing test.** `test_audit_before_sets_old_values`:
  - Eintrag 07:48–12:01, danach per Hand auf start = end = 07:48 kollabiert (raw 07:48–12:01).
  - Aufruf mit einer transienten Kopie des Zustands 07:48–12:01 (`wh_change_service._snapshot`).
  - Die `credit_override`-Zeile hat `old_end_time == time(12,1)`, und `old_note` beginnt mit dem `credit_summary_text` der Kopie.
- [ ] **Step 2:** `PYTEST tests/test_credit_override.py::test_audit_before_sets_old_values`. Erwartet: FAIL (unerwartetes Schlüsselwort).
- [ ] **Step 3:** Parameter einbauen.
- [ ] **Step 4:** `PYTEST tests/test_credit_override.py`. Erwartet: alle PASS.
- [ ] **Step 5: Commit** `feat(credit-override): optional before-state for the audit row`

### Task 3: `run_change` erkennt gewählte Einträge an

**Files:**
- Modify: `backend/app/services/wh_change_service.py` (`ChangeImpact`, `run_change`, `_change_out`, `preview_fields`)
- Modify: `backend/app/schemas/working_hours_change.py:290` (`TimeEntryChangeOut`)
- Test: `backend/tests/test_wh_change_recognize.py`

**Interfaces:**
- Consumes: Task 2 `apply_credit_override(..., audit_before=...)`.
- Produces:
  - `run_change(db, user, *, admin_id, effective_from, apply, after_close=None, recognize_entry_ids: frozenset = frozenset(), lock_recognized: bool = False) -> ChangeImpact`
  - `ChangeImpact.recognized_ids: frozenset` (anerkannte IDs dieses Laufs)
  - `ChangeImpact.entry_flags: dict` mit `entry_id → {"recognizable": bool, "blockless_workday": bool, "newly_clamped": bool}` für jede ID in `reclamp.changed`
  - Property `ChangeImpact.logged_changes -> list`: `reclamp.changed` ohne `recognized_ids`
  - `TimeEntryChangeOut` erhält vier Felder mit Default `False`: `recognizable`, `recognized`, `blockless_workday`, `newly_clamped`
  - Fehlertext-Konstante `NOT_AFFECTED_DETAIL = "Der Eintrag vom {date} ist von dieser Änderung nicht betroffen."`

**Ablauf in `run_change`** (nach Schritt 5, also nach `reclamp_time_entries` + flush, vor Schritt 6):
1. `changed_ids = {c.entry_id for c in reclamp.changed}`.
2. Jede ID aus `recognize_entry_ids`, die nicht in `changed_ids` liegt, führt zu `HTTPException(400, NOT_AFFECTED_DETAIL)`. Datum aus einer F-026-gefilterten Abfrage; unbekannte IDs hat der Router schon mit 404 abgewiesen.
3. Für die übrigen IDs, sortiert nach `str(id)`: Eintrag laden (bei `lock_recognized` mit `credit_override_service.load_entry_locked`, sonst F-026-Query) und `apply_credit_override(db, e, changed_by_id=admin_id, on_request=False, audit_before=before[e.id])` aufrufen.
4. `entry_flags` je geänderter ID:
   - `recognizable` = Eintrag geschlossen, nicht `auto_closed`, nicht schon vor dem Lauf `credit_override`.
   - `blockless_workday` = `work_window_service.credit_blocks(db, user, c.date) == []`.
   - `newly_clamped` = am Datum hätte der alte Snapshot nicht gekappt: `old_tracked.get(c.date) is False` oder alte Blöcke des Wochentags laut `old_schedule` `None` (Altzeile 073, kein Blockmodell). Ein Hilfsfunktion `_old_day_unclamped(old_schedule, old_tracked, d) -> bool` mit eigenem Test.
5. `losing` und die `months`-Statistik nutzen `logged_changes` statt `reclamp.changed`.

**`preview_fields`:**
- `time_entry_changes` listet weiter **alle** `reclamp.changed`, jeweils mit den vier Flags (`recognized` = ID in `recognized_ids`).
- `affected_time_entries` und `lost_credited_hours` rechnen über `logged_changes`.

- [ ] **Step 1: Write the failing tests** in `test_wh_change_recognize.py`. Kundenfall-Fixture `_customer_case(db)`:
  - `first_work_day=2026-10-01`, Basiszeile 5 Tage mit Blöcken 07:55–13:25 + 14:55–17:55 (Muster `tests/work_blocks_fixtures.block_week`).
  - Geschlossene Einträge: Mi 07.10. 07:48–12:01, Do 08.10. 07:48–12:36, Mo 12.10. 07:47–12:00.
  - `apply` legt eine Zeile ab 01.10. mit Blöcken nur Mo + Di an (Helper aus `tests/wh_change_helpers.py`).
  - `test_without_selection_is_entries_shortening`: `SHORTENING_ENTRIES in impact.shortening_reasons`, 07.10. hat `new_net == 0` und `entry_flags[id]["blockless_workday"] is True`.
  - `test_selection_removes_shortening`: Mit `recognize_entry_ids={07.10., 08.10.}` ist `SHORTENING_ENTRIES not in impact.shortening_reasons`. Beide Einträge haben `credit_override is True`, `net_hours == Decimal("4.22")` bzw. `Decimal("4.80")` (gestempelt, Pause 0). `impact.logged_changes` enthält sie nicht.
  - `test_recognize_id_outside_change_rejected`: Eine ID eines Eintrags vom 15.09. ergibt 400 mit `"15.09.2026"` im Text.
  - `test_auto_closed_selection_rejected`: Eintrag `auto_closed=True` gewählt → 400 `AUTO_CLOSED_DETAIL`.
  - `test_newly_clamped_flag`: Basiszeile **ohne** Blöcke (Stundenmodell), neue Zeile mit Blöcken Mo + Di → `newly_clamped is True` am Mo-Eintrag.
  - `test_preview_fields_flags`: `preview_fields(impact)["time_entry_changes"]` enthält für 07.10. `recognized: True, recognizable: True, blockless_workday: True`.
- [ ] **Step 2:** `PYTEST tests/test_wh_change_recognize.py`. Erwartet: FAIL.
- [ ] **Step 3:** Implementieren wie oben. Der Builder prüft am Misch-Tag-Test (Step 4), ob `reapply_f1_for_day` in `apply_credit_override` und danach `retarget_absence_hours` dasselbe Ergebnis liefern. Weicht es ab, bekommt `apply_credit_override` den Schalter `reapply_f1: bool = True`, und `run_change` übergibt `False`.
- [ ] **Step 4:** Misch-Tag-Test ergänzen. `test_recognize_on_mixed_day_f1_matches_single`: Am 07.10. zusätzlich SICK mit `keep_time_entries`. Gutschrift der Abwesenheit nach `run_change` mit Auswahl == Gutschrift nach Einzel-Anerkennen auf demselben Ausgangszustand. Genau eine `credit_override`-Zeile je Eintrag. Dann `PYTEST tests/test_wh_change_recognize.py tests/test_wh_change_service.py tests/test_wh_change_preview.py`. Erwartet: PASS.
- [ ] **Step 5: Commit** `feat(wh-change): recognise selected entries inside run_change`

### Task 4: Router — Feld, Prüfung, Speichern, Vorschau, Protokoll

**Files:**
- Modify: `backend/app/schemas/working_hours_change.py:116` (`WorkingHoursChangeCreate.recognize_entry_ids: List[UUID] = []`, höchstens 200)
- Modify: `backend/app/routers/admin_users.py`:
  - `create_working_hours_change` ~`:2235`
  - Vorschau `:2521`
  - `_log_reclamp` `:2184`
  - `adjusted_time_entries` `:2327`
- Test: `backend/tests/test_wh_change_recognize_api.py`, `backend/tests/test_write_path_locks.py` (neuer Test)

**Interfaces:**
- Consumes: Task 3 `run_change(..., recognize_entry_ids, lock_recognized)`, `ChangeImpact.logged_changes`.
- Produces: Helfer `_assert_entries_of_user(db, user, tenant_id, ids) -> None`, der ungesperrt prüft und 404 wirft. Wird in Task 9 wiederverwendet. Das Speichern übergibt `lock_recognized=True`, die Vorschau `False`.

**Reihenfolge im Speicherpfad:**
1. `_parse_change_body`
2. `_get_user_in_tenant`
3. `_assert_entries_of_user`
4. `_lock_and_reload`
5. weiter wie bisher

`_log_reclamp` iteriert über `impact.logged_changes`. Die Sammelzeile zählt `count`/`delta_minutes` daraus. `adjusted_time_entries = len(impact.logged_changes)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_create_with_selection_needs_no_reason`: Kundenfall über API. `POST` mit Blöcken Mo + Di ab 01.10. und `recognize_entry_ids=[07.10., 08.10.]`, ohne Grund → 201. Danach `GET /api/admin/users/{id}/journal?year=2026&month=10` (bzw. der vorhandene Journal-Endpunkt): Soll am 07.10. ist 0, Ist am 07.10. ist 4,22.
  - `test_unselected_entry_still_requires_reason`: Nur 07.10. gewählt, 08.10. nicht → 400 mit dem `protection_error`-Text, nichts gespeichert (Eintrag 07.10. weiter `credit_override is False`).
  - `test_preview_equals_save`: Vorschau mit Auswahl, dann Speichern mit gleichem Body → `saldo_delta_hours` der Vorschau == Saldoänderung laut `get_overtime_account` vorher/nachher.
  - `test_summary_row_excludes_recognized`: Die Sammelzeile `wh_reclamp` meldet über `reclamp_audit.parse_summary_note` `count == 1` (nur der 12.10.), die zwei anerkannten Einträge haben keine `wh_reclamp`-Zeile, und je eine `credit_override`-Zeile hat `old_end_time` 12:01 bzw. 12:36.
  - `test_recognize_collision_rolls_back_change`: Zweiter Eintrag am 07.10. beginnt um 07:48 nach Anerkennen-Kollision → 409, kein `WorkingHoursChange` ab 01.10. gespeichert.
  - In `test_write_path_locks.py`: `test_foreign_recognize_id_404_before_lock`. Eintrag einer anderen Person derselben Praxis → 404, und `lock_user_row` wurde nicht aufgerufen (Muster `test_update_foreign_entry_takes_no_lock`).
- [ ] **Step 2:** `PYTEST tests/test_wh_change_recognize_api.py`. Erwartet: FAIL.
- [ ] **Step 3:** Implementieren.
- [ ] **Step 4:** Auf testbox die Dateien `tests/test_wh_change_*.py tests/test_write_path_locks.py tests/test_credit_override.py tests/test_reclamp_audit.py` laufen lassen. Erwartet: PASS.
- [ ] **Step 5: Commit** `feat(wh-change): recognise entries when saving a working-hours change`

### Task 5: Hinweis „Ab erstem Arbeitstag übernehmen“

**Files:**
- Create: `frontend/src/utils/firstWorkDayHint.ts`, `frontend/src/utils/firstWorkDayHint.test.ts`
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.tsx` (neues Prop `firstWorkDay?: string | null`; Hinweis unter dem Datumsfeld ~`:860`)
- Modify: `frontend/src/pages/admin/Users.tsx:1076`, `frontend/src/pages/admin/TeamSchedule.tsx:469` (Prop durchreichen)
- Modify (umgesetzt, nachgetragen): `backend/app/schemas/team_schedule.py` (`TeamScheduleRow.first_work_day`) + Router-Zeile, die es füllt — TeamSchedule.tsx braucht den ersten Arbeitstag für das Prop; Test `test_row_carries_the_first_work_day`. Im PR-Text erwähnen.
- Test: `frontend/src/pages/admin/users/WorkingHoursModal.test.tsx`

**Interfaces:**
- Consumes: Task 1 `WorkingHoursChange.is_baseline`.
- Produces: `firstWorkDayHint(firstWorkDay: string | null | undefined, changes: WorkingHoursChange[], effectiveFrom: string, fallback: ScheduleSnapshot, today: string): { applyFrom: string; until: string; source: WorkingHoursChange | null; startSchedule: ScheduleSnapshot } | null` (umgesetzt; `fallback` = Vertrag aus den Dialog-Props wie in `scheduleAt`, `today` = lokales Datum, `startSchedule` = Vertrag am ersten Arbeitstag für den Hinweistext).
  - **Fall A** (noch nichts gespeichert): Es gibt keine Zeile mit `!is_baseline`, und `effectiveFrom > firstWorkDay`. Dann `applyFrom = firstWorkDay`, `until = Vortag(effectiveFrom)`, `source = null` (Formular bleibt).
  - **Fall B** (gespeichert): Es gibt genau eine Zeile mit `!is_baseline` und `effective_from <= heute` (geplante Zukunftszeilen zählen nicht und werden nie `source`). Sie liegt nach `firstWorkDay`, und keine `!is_baseline`-Zeile liegt auf oder vor `firstWorkDay`. Ihr Vertrag weicht laut `comparableSnapshot` von `scheduleAt(changes, firstWorkDay)` ab. Dann `source` = diese Zeile, `until = Vortag(source.effective_from)`.
  - Sonst `null`.
  - `comparableSnapshot`, `scheduleAt` und `formFromSnapshot` werden dafür aus `WorkingHoursModal.tsx` in `frontend/src/pages/admin/users/workingHoursSnapshot.ts` verschoben und exportiert. Das Modal importiert sie von dort.

Knopfaktion: Formular = `formFromSnapshot(source ? scheduleFromChange(source) : aktuelles Formular, applyFrom)`. Die Vorschau läuft danach über den vorhandenen Debounce.

- [ ] **Step 1: Write failing tests** in `firstWorkDayHint.test.ts`:
  - Fall A liefert `{applyFrom:'2026-10-01', until:'2026-11-19'}` bei `effectiveFrom='2026-11-20'`.
  - Fall B mit Basiszeile 01.10. (5 Tage) und Zeile 20.11. (Mo + Di) liefert `source.effective_from === '2026-11-20'`.
  - `null` bei zwei echten Zeilen.
  - `null`, wenn der Vertrag am ersten Arbeitstag gleich ist.
  - `null` ohne `firstWorkDay`.
  - `null` bei `effectiveFrom === firstWorkDay`.
  - Im Modal-Test: Der Hinweistext (Global Constraints) erscheint. Klick auf `Ab 01.10.2026 übernehmen` setzt das Datumsfeld auf `2026-10-01`.
- [ ] **Step 2:** `npx vitest run src/utils/firstWorkDayHint.test.ts src/pages/admin/users/WorkingHoursModal.test.tsx --pool=threads`. Erwartet: FAIL.
- [ ] **Step 3:** Implementieren.
- [ ] **Step 4:** Gleicher Befehl. Erwartet: PASS. Danach `npx tsc --noEmit`, erwartet: keine Fehler.
- [ ] **Step 5: Commit** `feat(wh-modal): offer the first work day when the contract starts too late`

### Task 6: Anerkennen-Liste im Dialog

**Files:**
- Create: `frontend/src/pages/admin/users/RecognizeEntriesList.tsx` (+ `.test.tsx`)
- Create: `frontend/src/pages/admin/users/recognizeSelection.ts` (+ `.test.ts`)
- Modify: `frontend/src/pages/admin/users/workingHoursTypes.ts` (`TimeEntryChange` + vier Flags; Body-Feld `recognize_entry_ids`)
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.tsx` (State, `scheduleBody`, Speichern-Text, `ShorteningChoice` nur bei `is_shortening`)
- Modify: `frontend/src/pages/admin/users/WhImpactBox.tsx` (Liste über der Einzelheiten-Liste einhängen)

**Interfaces:**
- Consumes: Task 3/4 Felder `recognizable`, `recognized`, `blockless_workday`, `newly_clamped`; Body `recognize_entry_ids`.
- Produces:
  - `losingEntries(changes: TimeEntryChange[]): TimeEntryChange[]` liefert Einträge mit `new_net < old_net`.
  - `defaultSelection(changes): Set<string>` liefert verlierende Einträge mit `recognizable && (blockless_workday || newly_clamped)`.
  - `<RecognizeEntriesList changes selected onChange />` rendert Zeilen im Format `Mi 07.10. · gestempelt 07:48–12:01 · bisher 4:13 h → neu 0:00 h` + Kennzeichen „Tag ohne Block“. Dazu „Alle auswählen“ / „Keine“, deaktivierte Häkchen mit `AUTO_CLOSED_HINT` bei `!recognizable` und den Hinweis aus Global Constraints. Zeitformat über `formatHoursHM`.

**Modal-Verhalten:**
- Solange die Admin nichts angeklickt hat (`recognizeTouched=false`), übernimmt jede neue Vorschau `defaultSelection`.
- Danach bleibt ihre Auswahl stehen. IDs, die in der neuen Vorschau fehlen, fallen heraus.
- Die Auswahl ist Teil von `scheduleBody` und damit des Vorschau-Schlüssels.

- [ ] **Step 1: Write failing tests:**
  - `recognizeSelection.test.ts`:
    - Vorauswahl nimmt 07.10. (blockless) und den `newly_clamped`-Eintrag.
    - Ein am Rand gekappter Eintrag wird nicht gewählt.
    - `!recognizable` wird nie gewählt.
  - `RecognizeEntriesList.test.tsx`:
    - Zeilentext wie oben.
    - Deaktiviertes Häkchen mit Hinweis.
    - „Alle auswählen“ wählt nur anerkennbare.
  - Modal-Test:
    - Nach Vorschau mit `is_shortening:false` und zwei gewählten Einträgen heißt der Knopf `Speichern und 2 Einträge anerkennen`, und `ShorteningChoice` fehlt.
    - Der Speichern-Body enthält `recognize_entry_ids` mit beiden IDs.
    - Abwählen löst eine neue Vorschau mit leerer Liste aus.
- [ ] **Step 2:** `npx vitest run src/pages/admin/users --pool=threads`. Erwartet: FAIL.
- [ ] **Step 3:** Implementieren.
- [ ] **Step 4:** Gleicher Befehl. Erwartet: PASS. Dazu `npx tsc --noEmit` und `npx eslint src/pages/admin/users`, beide ohne Fehler.
- [ ] **Step 5: Commit** `feat(wh-modal): select entries to recognise while changing the contract`

### Task 7: Feste Leiste „wen bearbeite ich“

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx:440-446`. Kopf wird `sticky top-0 z-20 bg-white border-b`, das Formular bekommt `id="user-form"`. Rechts in der Leiste Speichern (`type="submit" form="user-form"`) und Abbrechen. Abbrechen ruft ein neues optionales Prop `onCancel?: () => void`, das `Users.tsx` übergibt: dieselbe Aktion wie der heutige Abbrechen-Weg.
- Modify: `frontend/src/pages/admin/Users.tsx:490` (`onCancel` übergeben)
- Modify: `frontend/src/components/MonthlyJournal.tsx:225` (neues Prop `headerSlot?: ReactNode`; die Monatsnavigation wird `sticky top-0 z-20 bg-background` und rendert `headerSlot` links davon)
- Modify: `frontend/src/pages/admin/UserJournal.tsx` (Zurück-Knopf und Titel als `headerSlot` übergeben statt darüber)
- Test: `frontend/src/pages/admin/users/UserForm.test.tsx`, `frontend/src/components/MonthlyJournal.test.tsx`

**Interfaces:**
- Produces: Leistentext `Bearbeiten: {Vorname} {Nachname} ({benutzername})` bzw. `Neue:n Benutzer:in anlegen`. Auf dem Handy: Name mit `truncate`, Knöpfe als Symbole (`Save`, `X` aus lucide) mit `aria-label="Speichern"` / `"Abbrechen"`.

- [ ] **Step 1: Write failing tests:**
  - UserForm mit `editUser` Petra/Schulz/ps rendert `Bearbeiten: Petra Schulz (ps)` in einem Element mit Klasse `sticky`.
  - Klick auf den oberen Speichern-Knopf löst `onSaved`-Pfad wie der untere aus (gemockter `apiClient.put`).
  - MonthlyJournal mit `headerSlot={<span>X</span>}` rendert `X` im sticky-Container der Navigation.
- [ ] **Step 2:** `npx vitest run src/pages/admin/users/UserForm.test.tsx src/components/MonthlyJournal.test.tsx --pool=threads`. Erwartet: FAIL.
- [ ] **Step 3:** Implementieren. Scroll-Container ist `<main>` (`Layout.tsx:489`, `overflow-y-auto`), `sticky top-0` greift dort. Auf dem Handy liegt die feste App-Kopfzeile außerhalb von `main` (`pt-16`), also ist kein zusätzlicher Versatz nötig. Im Browser bei 375 px Breite und 1280 px Breite nachsehen.
- [ ] **Step 4:** Tests erneut. Erwartet: PASS.
- [ ] **Step 5: Commit** `feat(admin): keep the edited person visible while scrolling`

### Task 8: Handbuch, Doku-Sync und E2E für PR 1

**Files:**
- Modify: `frontend/src/handbuch/content/praxisleitung.ts`:
  - neue Aufgabe `id: 'vertrag-ab-eintritt'` direkt nach `rueckwirkend-aendern` (`:1498`)
  - Ergänzung von `auswirkung-pruefen` (`:1514`) und `nicht-angerechnet-anerkennen` (`:1564`): zweiter Weg „im Dialog beim Speichern“
- Generated: `docs/handbuch/HANDBUCH-ADMIN.md`, `frontend/public/help/HANDBUCH-ADMIN.md` (`npm run handbuch:md`)
- Modify: `docs/handbuch/CHEATSHEET-ADMIN.md` + Spiegel `frontend/public/help/CHEATSHEET-ADMIN.md` (eine Zeile, byte-identisch)
- Modify: `scripts/check-doc-sync.sh`: neue Gruppe `vertrag_ab_eintritt`. Sie prüft, dass der Hinweistext und der Knopftext aus Global Constraints wörtlich in `WorkingHoursModal.tsx`/`firstWorkDayHint.ts` **und** in `praxisleitung.ts` stehen, und hängt die Gruppe an `all`.
- Modify: `CHANGELOG.md` (Abschnitt „Unreleased“)
- Create: `e2e/tests/admin/contract-from-first-work-day.spec.ts`

**Aufgabe `vertrag-ab-eintritt`:**
- Titel: „Die Arbeitszeit gilt erst ab heute – wie korrigiere ich sie ab dem ersten Arbeitstag?“
- Schritte nach Spec §9: Symptom, Dialog mit Hinweis, Anerkennen-Liste, Speichern, Journal prüfen.
- Rechenbeispiel ohne Kundennamen: 2 Tage à 8 h, zwei Aushilfe-Tage à 4 h. Ohne Anerkennen 0 h angerechnet, mit Anerkennen +8 h.
- Tipp (`tone: 'warn'`): Anerkennen lässt sich nicht zurücknehmen.

- [ ] **Step 1:** E2E-Spec schreiben:
  - Admin legt eine Person mit erstem Arbeitstag am Monatsersten des Vormonats an (`weekdayFromNow`-Helfer für Daten; Cleanup über Fixtures).
  - Sie stempelt per Admin-API an einem Mittwoch.
  - Arbeitszeit-Änderung „ab heute“ mit Mo + Di speichern.
  - Dialog neu öffnen → Hinweis sichtbar → übernehmen → Liste zeigt den Mittwoch vorausgewählt → Speichern.
  - Journal zeigt am Mittwoch Soll leer/0 und „anerkannt“.
  - Locators in `main` scopen, mit `TZ=Europe/Berlin` fahren.
- [ ] **Step 2:** Handbuch-Text schreiben, dann `cd frontend && npm run handbuch:md`.
- [ ] **Step 3:** `bash scripts/check-doc-sync.sh all`. Erwartet: Exit 0. Danach `npx vitest run src/handbuch src/constants --pool=threads`, erwartet: PASS.
- [ ] **Step 4:** Auf testbox `bash scripts/local-ci.sh` über `tb-run` (inkl. E2E mit erhöhten Rate-Limits laut CLAUDE.md). Erwartet: grün.
- [ ] **Step 5: Commit** `docs(handbuch): correct a contract from the first work day`. Danach PR 1 öffnen (Basis `master`). Text mit Kundenfall ohne Namen.

---

## PR 2 — Sammel-Anerkennen im Monatsjournal

### Task 9: Endpunkt `POST /api/admin/users/{user_id}/time-entries/credit-override`

**Files:**
- Modify: `backend/app/routers/admin_time_entries.py` (neben `admin_credit_override` `:748`)
- Modify: `backend/app/schemas/time_entry.py` (`BulkCreditOverrideRequest`, `BulkCreditOverrideResponse`)
- Test: `backend/tests/test_credit_override_bulk.py`, `backend/tests/test_credit_override_bulk_pg.py`

**Interfaces:**
- Consumes: Task 4 `_assert_entries_of_user` (nach `app/routers/admin_helpers.py` verschieben, falls `admin_time_entries` `admin_users` sonst importieren müsste).
- Produces:
  - `BulkCreditOverrideRequest { entry_ids: List[UUID] }` mit `min_length=1`, `max_length=200`, Duplikate werden entfernt.
  - `BulkCreditOverrideResponse { recognized: int, already: int, warnings: List[str] }`.
- Ablauf:
  1. `_get_user_in_tenant`
  2. `_assert_entries_of_user` (404 vor Sperre)
  3. `lock_user_row`
  4. Einträge über `load_entry_locked`, sortiert nach `str(id)`
  5. `apply_credit_override` je Eintrag. Eine `HTTPException` wird mit vorangestelltem Datum (`"07.10.2026: " + detail`) neu geworfen, nach `db.rollback()`.
  6. `commit`
  7. Warnungen `override_warnings` je anerkanntem Eintrag, dedupliziert in Reihenfolge.
- Der Einzel-Endpunkt bleibt unverändert.

- [ ] **Step 1: Write failing tests:**
  - `test_bulk_recognizes_all`: zwei Einträge → `recognized == 2`, beide `credit_override`, zwei Audit-Zeilen.
  - `test_bulk_idempotent`: ein schon anerkannter + ein neuer → `recognized 1, already 1`.
  - `test_bulk_all_or_nothing_auto_closed`: ein `auto_closed` dabei → 400, `detail` beginnt mit dem Datum und endet mit `AUTO_CLOSED_DETAIL`, der andere Eintrag bleibt `credit_override is False`.
  - `test_bulk_foreign_entry_404_no_lock`: wie Task 4.
  - `test_bulk_rejects_201_ids`: 422.
  - PG-Datei (`_pg`-Muster, siehe `test_year_closing_lock_pg.py`): zwei parallele Sammelaufrufe auf dieselben Einträge enden ohne Deadlock. Einer erkennt an, der andere meldet `already`.
- [ ] **Step 2:** `PYTEST tests/test_credit_override_bulk.py`. Erwartet: FAIL.
- [ ] **Step 3:** Implementieren. Die neue `_pg`-Datei in `scripts/local-ci.sh` und in den `--ignore`-Listen (CLAUDE.md-Testbefehl, `local-ci.sh`) aufnehmen.
- [ ] **Step 4:** `PYTEST tests/test_credit_override_bulk.py`, erwartet: PASS. PG-Test auf testbox laut `local-ci.sh`, erwartet: PASS.
- [ ] **Step 5: Commit** `feat(credit-override): recognise several entries in one request`

### Task 10: Auswahl im Monatsjournal

**Files:**
- Modify: `frontend/src/utils/creditOverride.ts`:
  - `isRecognizable(entry): boolean` mit der heutigen Bedingung aus `CreditOverrideButton.tsx:40` (`!credit_override && end_time && notCredited > 0`)
  - `canRecognizeNow(entry): boolean` = `isRecognizable && !auto_closed`
  - `bulkConfirmText(count: number, extraMinutes: number): string`
- Modify: `frontend/src/components/CreditOverrideButton.tsx` (nutzt `isRecognizable`)
- Modify: `frontend/src/components/MonthlyJournal.tsx` (nur `isAdminView`):
  - Häkchen je Eintrag mit `canRecognizeNow`
  - Kopfaktion „Alle nicht angerechneten auswählen“
  - Aktionsleiste „Ausgewählte anerkennen (n)“ in der sticky Navigation aus Task 7
  - Bestätigung über `useConfirm` mit `bulkConfirmText`
  - `POST /admin/users/{userId}/time-entries/credit-override`, danach neu laden und `showArbzgWarnings`
- Test: `frontend/src/utils/creditOverride.test.ts`, `frontend/src/components/MonthlyJournal.test.tsx`

**Interfaces:**
- Consumes: Task 9 Endpunkt.
- `bulkConfirmText(2, 512)` liefert: `2 Einträge werden mit der ganzen gestempelten Zeit angerechnet (zusätzlich 8:32 h). Anerkennen lässt sich nicht zurücknehmen. Der Vorgang wird protokolliert.` (n = 1: `1 Eintrag wird …`)

- [ ] **Step 1: Write failing tests:**
  - `isRecognizable` und `canRecognizeNow` bei offen, `auto_closed`, schon anerkannt und 0 nicht angerechnet.
  - `bulkConfirmText` exakt wie oben.
  - Journal: Häkchen nur in Adminansicht, „Alle … auswählen“ zählt nur erlaubte, Knopf zeigt `(2)`, Bestätigen sendet den Body `{entry_ids:[a,b]}`.
- [ ] **Step 2:** `npx vitest run src/utils/creditOverride.test.ts src/components/MonthlyJournal.test.tsx --pool=threads`. Erwartet: FAIL.
- [ ] **Step 3:** Implementieren.
- [ ] **Step 4:** Gleicher Befehl + `npx tsc --noEmit`. Erwartet: PASS.
- [ ] **Step 5: Commit** `feat(journal): recognise several entries at once`

### Task 11: Handbuch und E2E für PR 2

**Files:**
- Modify: `frontend/src/handbuch/content/praxisleitung.ts`, Aufgabe `nicht-angerechnet-anerkennen`: Schritt „mehrere auf einmal“ mit Häkchen, Knopf „Ausgewählte anerkennen (n)“ und Bestätigung
- Generated: `npm run handbuch:md`
- Modify: `docs/handbuch/CHEATSHEET-ADMIN.md` + Spiegel
- Modify: `scripts/check-doc-sync.sh`, Gruppe `vertrag_ab_eintritt` um `Ausgewählte anerkennen` erweitern
- Modify: `CHANGELOG.md`
- Create: `e2e/tests/admin/journal-bulk-recognize.spec.ts` (zwei Einträge außerhalb der Blöcke → beide wählen → bestätigen → „anerkannt“ an beiden)

- [ ] **Step 1:** E2E-Spec und Handbuchtext schreiben, `npm run handbuch:md`.
- [ ] **Step 2:** `bash scripts/check-doc-sync.sh all`. Erwartet: Exit 0.
- [ ] **Step 3:** `local-ci.sh` über `tb-run` auf testbox. Erwartet: grün.
- [ ] **Step 4: Commit** `docs(handbuch): recognise several entries in the journal`. PR 2 öffnen.

---

## PR 3 — „?“-Kurzhilfen

### Task 12: Komponente `HandbookHint` und Register

**Files:**
- Create: `frontend/src/constants/handbookHints.ts`
- Create: `frontend/src/components/HandbookHint.tsx` (+ `HandbookHint.test.tsx`)
- Create: `frontend/src/constants/handbookHints.test.ts`
- Modify: `frontend/src/constants/helpContent.test.ts`. Den Anker-Prüfer als `anchorExists(book: HandbookId, anchor: string): boolean` exportieren (bzw. in `handbuch/validate.ts` auslagern) und in beiden Tests nutzen.

**Interfaces:**
- Produces:
  - `type HintId` = String-Literal-Union der Registerschlüssel.
  - `handbookHints: Record<HintId, { book: HandbookId; anchor: string; title: string; text: string }>`.
  - `<HandbookHint hintId={…} />`: Knopf `HelpCircle` 16 px, `aria-label="Hilfe: {title}"`.
  - Popover mit Titel, Text und `<Link to="/help/{book}#{anchor}">Mehr im Handbuch →</Link>`.
  - Schließt mit Esc, mit Klick daneben und beim Fokusverlust aus dem Popover.
  - Unter 640 px als Bottom-Sheet (`fixed inset-x-0 bottom-0`).

- [ ] **Step 1: Write failing tests:**
  - Register: Jeder Eintrag hat `anchorExists === true`. `text` hat höchstens 3 Sätze und keinen Begriff aus `forbiddenTerms`.
  - Jeder Schlüssel kommt in `src/**/*.tsx` als `hintId="<schlüssel>"` vor (Quelltextsuche über `import.meta.glob('/src/**/*.tsx', { as: 'raw', eager: true })`). Dieser Test bleibt bis Task 13 rot. Markiere ihn in Task 12 mit `it.todo` und schalte ihn in Task 13 scharf.
  - Komponente: Klick öffnet, Esc schließt, Link-`href` ist `/help/praxisleitung#rueckwirkend-aendern`.
- [ ] **Step 2:** `npx vitest run src/components/HandbookHint.test.tsx src/constants --pool=threads`. Erwartet: FAIL.
- [ ] **Step 3:** Implementieren, Register zunächst mit einem Eintrag `wh-effective-date` → `praxisleitung#rueckwirkend-aendern`.
- [ ] **Step 4:** Gleicher Befehl. Erwartet: PASS.
- [ ] **Step 5: Commit** `feat(help): inline handbook hints`

### Task 13: Kurzhilfen an Admin- und Mitarbeiterseiten setzen

**Files:**
- Modify: `frontend/src/constants/handbookHints.ts` (Einträge ergänzen)
- Modify, je Einsatzstelle neben dem Label:
  - `UserForm.tsx`, `ContractTermsFields.tsx`
  - `WorkingHoursModal.tsx`, `WhImpactBox.tsx`, `ShorteningChoice.tsx`, `RecognizeEntriesList.tsx`
  - `MonthlyJournal.tsx`
  - `pages/admin/Settings.tsx`, `ReducedDaysCard.tsx`
  - Berichte-/Jahresabschluss-Seite, Abwesenheitsgründe
  - Mitarbeiter-Dashboard-Karten, `RawStampNote.tsx`, Änderungsantrag-Formular
- Modify: `frontend/src/constants/handbookHints.test.ts` (`it.todo` → scharf)

**Vorgehen:**
- Startliste aus Spec §10 abarbeiten.
- Für jede Stelle die passende Kapitel- oder Aufgaben-ID in `praxisleitung.ts` bzw. `mitarbeitende.ts` suchen (`grep -n "id: '" …`).
- Ein Icon nur setzen, wenn der Abschnitt genau diese Stelle erklärt.
- Kurztext = 1–3 Sätze, sinngemäß aus dem Abschnitt, Sie-Form.
- Stellen ohne passenden Abschnitt in der PR-Beschreibung auflisten statt raten.
- Mitarbeiterseiten verlinken `book: 'mitarbeitende'`.

- [ ] **Step 1:** Register-Einträge und Einsatzstellen ergänzen. `handbookHints.test.ts` scharf schalten.
- [ ] **Step 2:** `npx vitest run src/constants src/components src/pages --pool=threads --maxWorkers=2`. Erwartet: PASS (bestehende Snapshot-/Text-Tests ggf. um das Icon anpassen, nie Zusicherungen löschen).
- [ ] **Step 3:** `npx tsc --noEmit && npx eslint src`. Erwartet: keine Fehler.
- [ ] **Step 4:** Sichtprüfung im Browser (Admin + MA, 375 px und 1280 px): Icon sitzt neben dem Label, Popover verdeckt kein Eingabefeld dauerhaft.
- [ ] **Step 5: Commit** `feat(help): handbook hints on admin and employee pages`

### Task 14: Handbuch-Hinweis auf die Kurzhilfen, Doku, CI

**Files:**
- Modify: `frontend/src/handbuch/content/praxisleitung.ts` und `mitarbeitende.ts`, im Kapitel zur Hilfe/Navigation: ein Satz „Das ?-Symbol neben einem Feld erklärt es kurz und führt zum passenden Abschnitt.“
- Modify: `frontend/src/constants/helpContent.tsx`, Eintrag „Hilfe & Navigation“ (`:420`): gleicher Satz
- Generated: `npm run handbuch:md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1:** Texte ergänzen, `npm run handbuch:md`.
- [ ] **Step 2:** `bash scripts/check-doc-sync.sh all`. Erwartet: Exit 0.
- [ ] **Step 3:** `local-ci.sh` über `tb-run` auf testbox. Erwartet: grün.
- [ ] **Step 4: Commit** `docs(handbuch): mention the inline hints`. PR 3 öffnen.

### Task 15: pzweb-Anleitung nachziehen

**Files:** im Repo `../pzweb`: `frontend/src/pages/marketing/anleitung/*` (Handbuch-Kopie per Sync-Skript, siehe `check-doc-sync.sh handbuch_pzweb`)

- [ ] **Step 1:** Im pzweb-Repo einen Branch anlegen und das Sync-Skript laufen lassen (Befehl steht in `scripts/check-doc-sync.sh` Gruppe `handbuch_pzweb`).
- [ ] **Step 2:** `PZWEB_DIR=../pzweb bash scripts/check-doc-sync.sh handbuch_pzweb`. Erwartet: Exit 0. pzweb-Tests in Docker `node:20`. Erwartet: PASS.
- [ ] **Step 3:** pzweb-PR öffnen. Er wird erst mit dem Release gemergt (Notiz in der PR-Beschreibung).
