# Teil A — Vertragsverlauf Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Holiday entitlement, „Stundenzählung aktiv“ and the three Minijob fields get a validity date. They live in the `working_hours_changes` contract snapshot, are changed only in the dialog „Arbeitszeit & Wochenstunden“ with an effective date, and every calculation reads them for the date or month it calculates, never live from `users`.

**Architecture:** Migration 075 adds five columns to `working_hours_changes` and backfills them from `users`, so every result stays bit-identical. `calculation_service.Schedule` carries the five values. `get_schedule_for_date` resolves them, and so do three new helpers: `tracks_hours_on`, `month_contract` and `vacation_entitlement_days`. The write path (`create_working_hours_change`, preview, delete, reset) carries them through `_NormalisedSchedule`, `_comparable_snapshot`, `_frozen_row` and `_sync_user_from_change`. A `track_hours` change runs through `wh_change_service.run_change` (Variante A): all weekdays count as changed, entries are re-clamped or unclamped, and absences are retargeted between 0 and the day target.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL 18 (SQLite in unit tests), React 18 + TypeScript, Vitest + RTL.

**Spec:** `docs/superpowers/specs/2026-11-03-vertragsverlauf-und-verkuerzte-tage-design.md` (Teil A: A1–A5, Teil-A share of section 5, section 7).

**Branch:** start from `master` after the Teil B PR (migration 074) is merged, e.g. `feat/vertragsverlauf`. Teil A is its own PR.

## Global Constraints

- Migration **075**: file `backend/alembic/versions/2026_11_10_1200-075_contract_history.py`, `revision = "075_contract_history"` (≤ 32 characters). The plan **assumes** `down_revision = "074_reduced_days"`. Before writing the file, run `ls backend/alembic/versions | grep 074` and `grep -n "^revision" backend/alembic/versions/*074*` and use the real id. If 074 is not merged yet, stop and ask.
- Alembic is never run via `python -m alembic`. Use `python -c "from alembic.config import main; main([...])"`.
- The column types are fixed: `vacation_days Numeric(4,1)`, `track_hours Boolean`, `milog_working_time_account Boolean`, `agreed_monthly_hours Numeric(5,1)` nullable (NULL = derived from `weekly_hours`, never "read the user row"), `use_fixed_monthly_target Boolean`. After the backfill, the four non-optional columns are NOT NULL. There is no Python default on the model.
- **Anti-goals (spec section 4):** no past result changes through migration 075. There is exactly one write path per historised field. NULL in a history row never means "read `users`". `UserForm` edit never sends one of the five fields.
- Resolution rule for the five fields. With no row at all, they come from the user row. With rows, a date before the first row gets **the first row's values**. Otherwise the latest row with `effective_from <= date` applies. The rule for `weekly_hours`/mode/days/blocks is unchanged (before the first row: user row).
- Entitlement rounding: 0.1 with `Decimal.quantize(Decimal('0.1'))` (default context, as today). A year with exactly one full-year segment returns the value unrounded.
- Minijob fields change only on the first of a month. Otherwise the request gets 422 with exactly `Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten.`
- Fixed-mode admissibility is checked on the new row's **snapshot** and gives 400 with the existing texts: `Fester Monats-Soll braucht eine vereinbarte Monatsarbeitszeit (> 0).` / `Fester Monats-Soll setzt Stundenzählung (track_hours) voraus.` / `Fester Monats-Soll setzt das MiLoG-Arbeitszeitkonto voraus.`
- German UI strings, verbatim:
  - section `Urlaub und Abrechnung`
  - field `Urlaubsanspruch pro Jahr ab diesem Datum`
  - link `Vorschlag übernehmen (N)`, e.g. `Vorschlag übernehmen (30)`. N is the bare German number (`30`, `13,1`) from a new `formatDayNumber(n)` in `utils/formatters.ts` (`String(Math.round(n * 100) / 100).replace('.', ',')`). Do **not** use `formatDayCount` here: it appends the unit (`formatDayCount(30)` = `30 Tage`, `utils/formatters.ts:145-150`), which would give `(30 Tage)` and `Urlaub 30 Tage Tage/Jahr`.
  - history card `Urlaub 30 Tage/Jahr` (`Urlaub ${formatDayNumber(n)} Tage/Jahr`)
  - vacation row `Urlaub verbraucht {Jahr}`
  - new rows `Urlaubsanspruch {Jahr}`
  - UserForm hint `Ändern über „Arbeitszeit anpassen…“`
- F-026: every new query on a tenant-scoped table carries `Model.tenant_id == …`. `working_hours_changes` already has RLS, and no policy change is needed.
- Performance: load each person's history once (the `wh_changes` preload). There is no query per day. `users-overview` keeps exactly one `working_hours_changes` query.
- Backend unit test command, written as `bt <args>` below. Run it from the repo root:
  ```bash
  rm -f backend/test.db backend/test.db-wal backend/test.db-shm; docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app \
    -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid \
    -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development \
    -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend \
    python -m pytest <args> -q -p no:cacheprovider
  ```
- Full backend suite = `bt tests/` plus `--ignore=` for every PG file. Use the list in `scripts/local-ci.sh` step 1, which today is `test_tenant_rls.py`, `test_073_migration_pg.py`, `test_net_hours_parity_pg.py`, `test_reclamp_concurrency.py`, `test_handbuch_seed_pg.py`, `test_year_closing_lock_pg.py`, `test_concurrency.py`, plus any 074 PG file from Teil B, plus `test_075_contract_history_pg.py` from Task 16 on. Expected: `N passed` and `0 failed`.
- Frontend test command, written as `ft <file>` below:
  `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx vitest run <file> --pool=threads`.
  Type check: the same prefix with `npx tsc --noEmit`. Full suite: `npx vitest run --pool=threads --maxWorkers=2`.
- Never run vitest, pytest, Playwright and `docker build` at the same time (memory limit).
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
  Use `git commit -F - <<'EOF' … EOF`.

## Review Focus

1. **A minijob person changes only hours on the 15th.** The three Minijob fields are not sent, or are sent unchanged, so they are inherited and the request must be accepted (201). This is not a 422. Owner: Task 5, test `test_hours_only_change_mid_month_keeps_minijob_fields`.
2. **A future-dated row becomes valid with no write since then (no scheduler).** "Today" questions (`/dashboard/missing-bookings`, own dashboard, `/me/work-schedule`, `users-overview` MiLoG gate) must read the snapshot for today, not the unmirrored `users` column. Owner: Task 9, test `test_future_row_switching_track_hours_off_applies_without_mirror`.
3. **Pure contract change in the dialog (only the entitlement or the checkbox).** The preview must refresh, because the five fields are part of `previewKey`. The impact box must show (a non-zero entitlement Δ counts as an effect), and "Speichern" must stay enabled. Owner: Task 14, test `shows the impact box for a pure entitlement change`.
4. **Decimal entitlement in the suggestion (#408).** 17,5 days at 4 → 3 days gives 13,125 → suggestion 13,1. 24 at 4 → 5 gives 30. The suggestion never divides by 0, and there is none while `plannedDays`/`derived.workDays` is 0. Owner: Task 13, tests `suggests 13,1 for 17,5 days from 4 to 3 days` and `no suggestion without work days`.
5. **Block mode with „Stundenzählung aktiv“ unchecked.** The body sends `blocks` plus `track_hours: false`. The server stores the blocks, and they are inert like today (no clamping on untracked days). The dialog keeps the blocks and shows them as "ohne Wirkung" (`BLOCKS_WITHOUT_EFFECT`, `WorkingHoursModal.tsx:188`), with no 422. Today the mode option „Nach Arbeitsblöcken“ is only offered while the `trackHours` prop is true (`:759`); unchecking the box in the form must not switch the mode or drop the blocks. Owners: Task 10, test `test_blocks_with_track_hours_off_are_stored_and_inert` (server), and Task 13, test `unchecking Stundenzählung in block mode keeps the blocks in the body` (dialog).

---

## File Structure

| File | Responsibility (change) |
|---|---|
| `backend/alembic/versions/2026_11_10_1200-075_contract_history.py` | new: columns, backfill, NOT NULL, downgrade |
| `backend/app/models/working_hours_change.py` | five columns |
| `backend/app/services/calculation_service.py` | `Schedule` fields, resolver rule, `tracks_hours_on`, `month_contract`, `vacation_entitlement_days`, per-day `track_hours` and per-month Minijob in all calc paths |
| `backend/app/schemas/working_hours_change.py` | five optional fields (inherit when not sent), `VacationEntitlementOut`, preview field, `"vacation_entitlement"` reason literal |
| `backend/app/schemas/user.py` | `ScheduleTodayResponse` gets the five fields |
| `backend/app/routers/admin_users.py` | normalise, compare, freeze, mirror, Minijob rules, earliest-row replacement, preview fields, `_HISTORISED_FIELDS`, `users_overview` gate |
| `backend/app/services/wh_change_service.py` | changed weekdays on a `track_hours` change, entitlement classification, `criteria_text`, `reset_body`, open entry/MiLoG gates |
| `backend/app/services/work_window_service.py` | clamp per-day `track_hours` (clamp/unclamp) |
| `backend/app/services/reclamp_audit.py` | `contract_pair` for the summary row |
| `backend/app/services/milog_service.py`, `journal_service.py`, `work_schedule_service.py`, `closure_split_service.py`, `export_service.py`, `ods_export_service.py` | month/day snapshot instead of user row |
| `backend/app/routers/{dashboard,reports,team_schedule,time_entries,company_closures,admin_change_requests}.py` | same |
| `backend/tests/conftest.py`, `backend/tests/wh_change_helpers.py` | insert-fill listener (tests only), `change_row(**contract)` |
| `backend/tests/test_contract_history_*.py` | new tests (one file per task, names below) |
| `backend/tests/test_075_contract_history_pg.py` | new PG round trip |
| `tools/migration-075/probe_075.py` | new bit-identity probe |
| `frontend/src/pages/admin/users/ContractTermsFields.tsx` | new: shared controls (entitlement, Stundenzählung, MiLoG, Monatsstunden, Fix-Modus) |
| `frontend/src/pages/admin/users/{WorkingHoursModal,WhImpactBox,WhDeletePanel,UserForm,workingHoursTypes,workingHoursTexts}.tsx/.ts` | dialog section, preview rows, reason, read-only edit |
| `frontend/src/pages/admin/{Users,TeamSchedule,AdminDashboard}.tsx`, `frontend/src/types/user.ts` | props, `schedule_today`, wording fix |
| docs (5 surfaces), `CLAUDE.md`, `scripts/check-doc-sync.sh` | Task 17 |

---

### Task 1: Migration 075 and model columns

**Files:**
- Create: `backend/alembic/versions/2026_11_10_1200-075_contract_history.py`
- Modify: `backend/app/models/working_hours_change.py` (after `blocks`, before `note`)
- Modify: `backend/tests/conftest.py` (listener), `backend/tests/wh_change_helpers.py:58-79` (`change_row`)
- Modify: `backend/create_test_data.py:275` (the only `WorkingHoursChange(` constructor outside `app/` and `tests/`; `create_handbuch_testdata.py` has none). In `app/` there are exactly two: `admin_users._frozen_row` (`:1717`) and `_insert_change_rows` (`:1796`); Task 4 fills them.
- Test: `backend/tests/test_contract_history_model.py`

**Interfaces:**
- Produces: the columns `WorkingHoursChange.vacation_days`, `.track_hours`, `.milog_working_time_account`, `.agreed_monthly_hours`, `.use_fixed_monthly_target`. Also `change_row(user, effective_from, *, …, **contract)`, which passes any of the five names straight to the constructor.

- [ ] **Step 1: Write the failing tests** in `test_contract_history_model.py`:

```python
def test_columns_exist_and_four_are_not_nullable():
    cols = WorkingHoursChange.__table__.c
    for name in ("vacation_days", "track_hours", "milog_working_time_account", "use_fixed_monthly_target"):
        assert cols[name].nullable is False
    assert cols["agreed_monthly_hours"].nullable is True
    assert str(cols["vacation_days"].type) == "NUMERIC(4, 1)"
    assert str(cols["agreed_monthly_hours"].type) == "NUMERIC(5, 1)"

def test_test_listener_fills_unset_fields_from_user(db, test_user):
    test_user.vacation_days = 24; test_user.agreed_monthly_hours = Decimal("43.3"); db.commit()
    row = add_row(db, test_user, date(2026, 1, 1), weekly_hours=20)
    assert row.vacation_days == Decimal("24.0") and row.track_hours is True
    assert row.agreed_monthly_hours == Decimal("43.3")

def test_listener_keeps_explicit_none_for_agreed(db, test_user):
    test_user.agreed_monthly_hours = Decimal("43.3"); db.commit()
    row = add_row(db, test_user, date(2026, 1, 1), weekly_hours=20, agreed_monthly_hours=None)
    assert row.agreed_monthly_hours is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bt tests/test_contract_history_model.py`
Expected: FAIL with `KeyError: 'vacation_days'`.

- [ ] **Step 3: Implement**
  - Model: add the five columns with the types from Global Constraints, `nullable=False` for the four, and no `default`. Add a short comment: "075: Vertrags-Snapshot; NULL in agreed = abgeleitet, nie Rückfall auf users".
  - Migration `upgrade()`:
    1. `op.add_column` all five, nullable.
    2. On PG, call `SET LOCAL app.is_superadmin = 'true'` (same pattern as `_superadmin()` in 073).
    3. `UPDATE working_hours_changes AS w SET vacation_days = u.vacation_days, track_hours = u.track_hours, milog_working_time_account = u.milog_working_time_account, agreed_monthly_hours = u.agreed_monthly_hours, use_fixed_monthly_target = u.use_fixed_monthly_target FROM users AS u WHERE u.id = w.user_id`.
    4. `op.alter_column(..., nullable=False)` for the four.
    5. Print `075: n Verlaufszeilen übernommen` (count).
  - `downgrade()` drops the five columns. The module docstring is German and explains why the backfill keeps every result unchanged.
  - Test-only listener in `conftest.py`: register `event.listen(WorkingHoursChange, "before_insert", _fill_contract_from_user)`. It fills an attribute only when it was **never assigned** (`sqlalchemy.inspect(target).attrs[name].history.added` is empty). It reads the values with `connection.execute(select(User.__table__.c[...]).where(User.__table__.c.id == target.user_id))`. Docstring: "nur Tests — Produktion setzt alle fünf ausdrücklich (NOT NULL scheitert laut)".
  - `change_row`: accept `**contract` and merge it into `common`.
  - `create_test_data.py`: set the five fields from the user it creates.
  - Between this task and Task 4 the two production constructors do not set the five columns yet. In tests the listener covers them; on a real database an insert would fail with NOT NULL. Do not deploy or hand out the branch between Task 1 and Task 4.

- [ ] **Step 4: Run the tests and the migration smoke**

Run: `bt tests/test_contract_history_model.py tests/test_schedule_history_model.py`
Expected: PASS.

- [ ] **Step 5: Full backend suite** (command from Global Constraints)

Expected: `0 failed`. Nothing reads the columns yet.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/2026_11_10_1200-075_contract_history.py backend/app/models/working_hours_change.py backend/tests/conftest.py backend/tests/wh_change_helpers.py backend/tests/test_contract_history_model.py backend/create_test_data.py
git commit -F - <<'EOF'
feat(db): migration 075 — contract history fields on working_hours_changes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `Schedule` carries the five fields; resolution rule

**Files:**
- Modify: `backend/app/services/calculation_service.py:16-33` (`Schedule`), `:94-146` (`get_schedule_for_date`), `:196-212` (`schedule_display_json`)
- Modify: `backend/app/schemas/user.py:235` (`ScheduleTodayResponse`)
- Modify: `backend/app/routers/admin_users.py:2238` (preview `Schedule(...)`: pass the current schedule's five values for now; Task 4 replaces them)
- Modify tests that build `Schedule(...)`: `tests/test_reclamp_audit.py`, `tests/test_wh_change_legacy_blocks.py`, `tests/test_wh_change_service.py` (find all with `grep -rn "Schedule(" backend/tests backend/app`)
- Test: `backend/tests/test_contract_history_resolver.py`

**Interfaces:**
- Produces:
  - `Schedule` gains, in this order after `block_pauses`: `vacation_days: Decimal`, `track_hours: bool`, `milog_working_time_account: bool`, `agreed_monthly_hours: Optional[Decimal]`, `use_fixed_monthly_target: bool`. None of them has a default.
  - `calculation_service.tracks_hours_on(db, user, d: date, wh_changes=None) -> bool`.
  - New private helper `calculation_service._earliest_change(db, user, wh_changes=None) -> Optional[WorkingHoursChange]`, the twin of `_latest_change` (`:36-57`): same query/in-memory semantics, `ORDER BY effective_from ASC LIMIT 1`, F-026 filter.
  - `schedule_display_json(schedule)` adds `vacation_days` (float), `track_hours`, `milog_working_time_account`, `agreed_monthly_hours` (float|None), `use_fixed_monthly_target`.

- [ ] **Step 1: Write the failing tests**

```python
def test_no_rows_reads_user_row(db, test_user):
    test_user.vacation_days = 24; db.commit()
    s = cs.get_schedule_for_date(db, test_user, date(2026, 3, 1))
    assert s.vacation_days == Decimal("24.0") and s.track_hours is True and s.agreed_monthly_hours is None

def test_before_first_row_uses_first_row_values_not_user_row(db, test_user):
    add_row(db, test_user, date(2026, 10, 31), weekly_hours=40, vacation_days=24, track_hours=True)
    test_user.vacation_days = 30; test_user.track_hours = False; db.commit()   # mirror moved on
    s = cs.get_schedule_for_date(db, test_user, date(2026, 1, 5))
    assert s.vacation_days == Decimal("24.0") and s.track_hours is True
    assert s.weekly_hours == Decimal(str(test_user.weekly_hours))  # hours rule unchanged

def test_preload_path_identical(db, test_user):
    rows = [add_row(db, test_user, date(2026, 6, 1), weekly_hours=20, vacation_days=20)]
    for d in (date(2026, 1, 1), date(2026, 6, 1), date(2027, 1, 1)):
        assert cs.get_schedule_for_date(db, test_user, d) == cs.get_schedule_for_date(db, test_user, d, wh_changes=rows)

def test_schedule_display_json_has_contract_fields(db, test_user):
    j = cs.schedule_display_json(cs.get_schedule_for_date(db, test_user, date(2026, 1, 1)))
    assert {"vacation_days", "track_hours", "milog_working_time_account",
            "agreed_monthly_hours", "use_fixed_monthly_target"} <= j.keys()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bt tests/test_contract_history_resolver.py`
Expected: FAIL with `AttributeError: 'Schedule' object has no attribute 'vacation_days'`.

- [ ] **Step 3: Implement**
  - Extend `Schedule`.
  - In `get_schedule_for_date`:
    - When a row is found, read the five fields from it. Convert `vacation_days` and `agreed_monthly_hours` with `_dec_or_none`.
    - When no row is found, take the five fields from the earliest row of the person (new helper `_earliest_change`, see Interfaces), else from the user row. In-memory path: min over `wh_changes`. Query path: `ORDER BY effective_from ASC LIMIT 1` with the F-026 filter.
    - Weekly hours, mode, days and blocks keep the user-row fallback.
  - Update the docstring "EINZIGE Stelle" to name the five fields.
  - `tracks_hours_on` returns `get_schedule_for_date(...).track_hours`.
  - Extend `ScheduleTodayResponse` with the five fields (Optional, float for numbers).
  - Fix all `Schedule(...)` constructors. The test helpers' `_schedule(...)` get keyword defaults *in the test helper only* (`vacation_days=Decimal("30"), track_hours=True, …`).

- [ ] **Step 4: Run the tests**

Run: `bt tests/test_contract_history_resolver.py tests/test_schedule_resolver.py tests/test_449_schedule_preload.py tests/test_reclamp_audit.py tests/test_wh_change_service.py tests/test_wh_change_legacy_blocks.py tests/test_users_api_schedule_today.py`
Expected: PASS.

- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`feat(calc): Schedule carries entitlement, track_hours and minijob fields`)

---

### Task 3: Entitlement per segment in `get_vacation_account`

**Files:**
- Modify: `backend/app/services/calculation_service.py:2942-3050` (`get_vacation_account` budget part and docstring `:2958`)
- Test: `backend/tests/test_contract_history_entitlement.py`

**Interfaces:**
- Consumes: `Schedule.vacation_days` and the resolution rule (Task 2).
- Produces:
  - `calculation_service.vacation_entitlement_days(db, user, year: int, wh_changes=None) -> Decimal`. This is the budget **without** carryover, and it is the only place the entitlement is computed.
  - `get_vacation_account(...)` returns an extra key `"entitlement_days": float`.
  - Private `_legacy_window_pro_rata(value: Decimal, year: int, first_work_day, last_work_day) -> Decimal`: the three pro-rata branches of today's `get_vacation_account` (`:2993-3037`), moved verbatim, used for the single-segment case.

- [ ] **Step 1: Write the failing tests**

```python
def test_customer_case_4_to_5_days_from_nov(db, test_user):   # spec A5
    test_user.first_work_day = date(2020, 1, 1); test_user.vacation_days = 24; db.commit()
    add_row(db, test_user, date(2020, 1, 1), weekly_hours=40, vacation_days=24)
    add_row(db, test_user, date(2026, 11, 1), weekly_hours=40, vacation_days=30)
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("25.0")
    assert cs.vacation_entitlement_days(db, test_user, 2027) == Decimal("30.0")
    assert cs.vacation_entitlement_days(db, test_user, 2025) == Decimal("24.0")

def test_change_mid_month_is_day_exact(db, test_user):        # 24×(10+14/30)/12 + 30×(16/30+1)/12
    ...rows 2020-01-01 (24) and 2026-11-15 (30)...
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("24.8")

def test_change_in_entry_year_is_clipped_by_window(db, test_user):
    test_user.first_work_day = date(2026, 4, 1); ...rows 2026-04-01 (24), 2026-09-01 (30)...
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("20.0")

def test_no_rows_unchanged(db, test_user):
    test_user.vacation_days = Decimal("16.8"); db.commit()
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("16.8")

def test_first_change_without_first_work_day_uses_old_value_before(db, test_user):
    # spec A5: no first_work_day, no bookings — before the first row = first row
    add_row(db, test_user, date(2026, 10, 31), weekly_hours=40, vacation_days=24)
    add_row(db, test_user, date(2026, 11, 1), weekly_hours=40, vacation_days=30)
    test_user.vacation_days = 30; db.commit()
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("25.0")

def test_single_segment_matches_legacy_pro_rata_for_every_entry_and_exit_day(db, test_user):
    # legacy_budget = verbatim copy (in the test file) of get_vacation_account :2993-3037 before Task 3
    for value in (Decimal("24"), Decimal("30"), Decimal("16.8")):
        rows = [WorkingHoursChange(user_id=test_user.id, tenant_id=test_user.tenant_id,
                                   effective_from=date(2020, 1, 1), vacation_days=value, ...)]  # transient
        for d in every_day(2026):                       # entry only, exit only
            for fwd, lwd in ((d, None), (None, d)):
                test_user.first_work_day, test_user.last_work_day = fwd, lwd
                assert cs.vacation_entitlement_days(db, test_user, 2026, wh_changes=rows) == legacy_budget(value, fwd, lwd, 2026)
        for fwd, lwd in every_pair(2026, step=7):       # entry and exit in the same year, fwd <= lwd
            ...same assertion...

def test_fix1_year_outside_window_has_no_budget_and_no_carryover(db, test_user):
    test_user.first_work_day = date(2020, 1, 1); test_user.last_work_day = date(2025, 6, 30); db.commit()
    add_row(db, test_user, date(2020, 1, 1), weekly_hours=40, vacation_days=24)
    db.add(YearCarryover(user_id=test_user.id, tenant_id=test_user.tenant_id, year=2026, vacation_days=5, overtime_hours=0))
    db.add(YearCarryover(user_id=test_user.id, tenant_id=test_user.tenant_id, year=2025, vacation_days=3, overtime_hours=0)); db.commit()
    assert cs.get_vacation_account(db, test_user, 2026)["budget_days"] == 0
    assert cs.get_vacation_account(db, test_user, 2025)["budget_days"] == 15.0      # 24 × 6/12 = 12,0 + 3

def test_carryover_added_after_rounding_not_prorated(db, test_user):
    # rows 2020-01-01 (24) and 2026-11-15 (30), carryover 2026 = 1
    assert cs.get_vacation_account(db, test_user, 2026)["budget_days"] == 25.8      # 24,8 + 1
    assert cs.get_vacation_account(db, test_user, 2026)["entitlement_days"] == 24.8
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bt tests/test_contract_history_entitlement.py`
Expected: FAIL with `AttributeError: … has no attribute 'vacation_entitlement_days'`.

- [ ] **Step 3: Implement `vacation_entitlement_days`**

```
window = [max(01.01., first_work_day), min(31.12., last_work_day)]; empty → Decimal('0')
runs  = adjacent equal vacation_days merged, from the rows (resolution rule), cut to window
if len(runs) == 1:
    value = runs[0].value
    return value if window is the whole year
           else legacy_window_pro_rata(value, user, year)   # old three branches, moved verbatim
total = Σ value × month_share(run.start, run.end) / 12
        month_share = full months as integers + partial months as Decimal(days)/Decimal(days_in_month)
return total.quantize(Decimal('0.1'))
```

  - `get_vacation_account` keeps `year_outside_window` (Fix #1) and the carryover block. It replaces `budget_days = …` and the three pro-rata branches with `vacation_entitlement_days(db, user, year, wh_changes)`, and adds `entitlement_days` to both return dicts.
  - Fix the docstring at `:2958`: "budget_hours = budget_days × Tagessoll des Snapshots am Stichtag".

- [ ] **Step 4: Run the tests**

Run: `bt tests/test_contract_history_entitlement.py tests/test_calc_preload.py tests/test_vacation_half_day.py tests/test_gesamtreview_b11_vacation_untracked.py`
Expected: PASS.

- [ ] **Step 5: Full backend suite.** Expected: `0 failed`. An existing test that first adds history rows and then changes `user.vacation_days` directly, expecting the new budget, models a state that cannot arise after 075 (the row would carry the value). Fix such a test by passing `vacation_days=` to the row (`add_row(..., vacation_days=…)`), never by adding a user-row fallback to the resolver. List each changed test in the commit message.
- [ ] **Step 6: Commit** (`feat(calc): vacation entitlement prorated per contract segment`)

---

### Task 4: Write path carries the five fields

**Files:**
- Modify: `backend/app/schemas/working_hours_change.py:77-95` (`WorkingHoursChangeBase`)
- Modify: `backend/app/routers/admin_users.py`:
  - `:150-183` `_comparable_snapshot`
  - `:203-249` `_NormalisedSchedule` / `_normalise_schedule_input`
  - `:252-286` `_sync_user_from_change`
  - `:1654-1677` `_reset_matches`
  - `:1714-1726` `_frozen_row`
  - `:1741-1813` `_insert_change_rows`
  - all `_comparable_snapshot(` and `_normalise_schedule_input(` call sites: `_reset_matches` `:1669/1672`, `_insert_change_rows` `:1781/1784`, create `:1921`, preview `:2215` and `:2266/2270`
  - preview `Schedule(...)` at `:2238`
- Modify: `backend/app/services/wh_change_service.py:458-479` (`reset_body`)
- Modify: `backend/tests/conftest.py` (fixture `no_contract_fill`, which removes the Task 1 listener for one test)
- Test: `backend/tests/test_contract_history_write.py`

**Interfaces:**
- Consumes: `Schedule` (Task 2).
- Produces:
  - `WorkingHoursChangeBase` gains `vacation_days: Optional[float] = Field(None, ge=0, le=50)`, `track_hours: Optional[bool] = None`, `milog_working_time_account: Optional[bool] = None`, `agreed_monthly_hours: Optional[float] = Field(None, gt=0, le=400)` (same bound as `UserBase`, `schemas/user.py:53`) and `use_fixed_monthly_target: Optional[bool] = None`. A field **not in `model_fields_set`** means "inherit from the snapshot at `effective_from`". `agreed_monthly_hours: null` sent explicitly means "derived".
  - `_normalise_schedule_input(change_data, user, current: Schedule) -> _NormalisedSchedule`. It carries the five extra fields, resolved: sent value, else `current`.
  - `_comparable_snapshot(weekly_hours, use_daily_schedule, day_hours, work_days_per_week, blocks, block_pauses, contract: tuple)`, where `contract = (Decimal vacation_days, track_hours, milog, Decimal|None agreed, fixed)`.
  - The helper `_contract_of(schedule_or_norm) -> tuple` builds that tuple.
  - `reset_body(predecessor, effective_from, change_id)` always contains the five fields.

- [ ] **Step 1: Write the failing tests**

All API tests freeze today with `freeze(monkeypatch, date(2026, 11, 3))` (`wh_change_helpers.freeze`).

```python
def test_pure_vacation_change_is_saveable_and_freezes_baseline(db, test_user, client):
    test_user.vacation_days = 24; test_user.work_days_per_week = 4; db.commit()
    r = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes",
                    json={"effective_from": "2026-11-01", "weekly_hours": float(test_user.weekly_hours),
                          "work_days_per_week": 4, "vacation_days": 30})
    assert r.status_code == 201, r.text
    rows = sorted(rows_of(db, test_user), key=lambda w: w.effective_from)
    assert [float(w.vacation_days) for w in rows] == [24.0, 30.0]          # baseline froze 24
    assert float(db.get(User, test_user.id).vacation_days) == 30.0          # mirror (eff ≤ today)

def test_customer_case_end_to_end(db, test_user, client, monkeypatch):    # spec A5, both bullets
    # no rows, no first_work_day, no bookings; 40 h / 4 days, vacation 24
    r = client.post(url, json={"effective_from": "2026-11-01", "weekly_hours": 40,
                               "work_days_per_week": 5, "vacation_days": 30})
    assert r.status_code == 201, r.text
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("25.0")
    assert cs.vacation_entitlement_days(db, test_user, 2027) == Decimal("30.0")
    assert cs.vacation_entitlement_days(db, test_user, 2025) == Decimal("24.0")
    assert float(db.get(User, test_user.id).vacation_days) == 30.0
def test_omitted_fields_inherit_snapshot_not_user_row(...):
    # row 2026-01-01 vacation 24, user row edited to 28 in the DB; POST without vacation_days → new row 24
def test_future_dated_change_not_mirrored(...):   # freeze today 2026-11-03, eff 2027-01-01 → users.vacation_days unchanged
def test_preview_snapshot_unchanged_false_for_contract_only_change(...):
    # preview body equal hours + vacation_days 30 → affected fields computed, blocked_reason None
def test_reset_body_in_block_mode_keeps_entitlement():
    pred = schedule(blocks=WEEK, vacation_days=Decimal("24"), track_hours=True, ...)
    body = wh_change_service.reset_body(pred, date(2026, 12, 1), uuid4())
    assert body["vacation_days"] == 24.0 and body["track_hours"] is True and "blocks" in body
def test_reset_matches_compares_contract_fields(...):   # reset body with vacation 30 against pred 24 → 409
def test_delete_restores_mirror(...):   # delete youngest row → users.vacation_days back to 24
def test_write_paths_set_all_five_without_test_listener(no_contract_fill, ...):
    # create (baseline + new row), gap row, reset body and delete all succeed with the
    # listener removed; every stored row has the four NOT NULL fields set (risk: the
    # listener would otherwise hide a production constructor that forgets a field)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bt tests/test_contract_history_write.py`
Expected: FAIL. The rows have no new values, and `vacation_days` is ignored.

- [ ] **Step 3: Implement**
  1. **Schema fields.** Add the five fields to `WorkingHoursChangeBase`. `WorkingHoursChangeResponse` gets them from the attributes, so the history GET shows them.
  2. **Normalisation.** `_normalise_schedule_input` gets the extra parameter `current`:
     - In create, `current = get_schedule_for_date(db, user, change_data.effective_from)`, resolved **before** `apply`.
     - In preview, `current_schedule`.
  3. **Snapshot comparison.** `_comparable_snapshot` gets the `contract` tuple. Every call site passes it:
     - `_insert_change_rows` baseline trigger
     - preview `snapshot_unchanged`
     - `_reset_matches`, which compares `_contract_of(norm)` with `_contract_of(reset_schedule)`
  4. **Frozen rows.** `_frozen_row` copies the five fields from `schedule`.
  5. **New row.** `_insert_change_rows` writes them from `norm`.
  6. **Mirror.** `_sync_user_from_change` copies all five onto the user row, including `agreed_monthly_hours = None`.
  7. **Reset body.** `reset_body` writes the five fields into `body` **before** the block-mode `return` at `:465`.
  8. **Preview.** Build the preview `new_schedule` from `norm`'s five fields.

- [ ] **Step 4: Run the tests**

Run: `bt tests/test_contract_history_write.py tests/test_wh_change_preview.py tests/test_wh_change_retroactive.py tests/test_wh_change_day_plan_create.py tests/test_wh_change_day_plan_delete.py tests/test_wh_change_delete_reclamp.py tests/test_wh_change_preview_blocks.py`
Expected: PASS.

- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`feat(wh-change): entitlement, track_hours and minijob fields in the contract snapshot`)

---

### Task 5: Minijob rules and the `PUT /admin/users` lock

**Files:**
- Modify: `backend/app/routers/admin_users.py`:
  - `:1281-1296` `_HISTORISED_FIELDS` and its message
  - `:1310-1342`: remove the `eff_fixed` block; its inputs can no longer arrive
  - create (after `_normalise_schedule_input` at `:1921`) and preview (after `:2215`): new rule check after normalisation
- Test: `backend/tests/test_contract_history_rules.py`. Update the tests that PUT one of the five fields and now get 400. Find them with `grep -rlE "vacation_days|track_hours|milog_working_time_account|agreed_monthly_hours|use_fixed_monthly_target" backend/tests | xargs grep -l "\.put("` (38 files match today; most only create users, so check each hit), among them `tests/test_user_fixed_mode_validation.py` (the `eff_fixed` PUT cases). Each such test either moves to the dialog path (`POST …/working-hours-changes`) or asserts the new 400.
- Modify: `e2e/tests/admin/minijob-milog.spec.ts:79` (`adminApi.put(…, { milog_working_time_account: false })` → `adminApi.post(`/admin/users/${empId}/working-hours-changes`, { effective_from: <first of the current month>, weekly_hours: MILOG_WEEKLY_HOURS, work_days_per_week: 5, milog_working_time_account: false })`). The create-mode E2E checks (`#track_hours` in `prod-release-features.spec.ts:100`, `visual-prod-release.spec.ts:22`) stay valid because Task 13 keeps the element ids in create mode.

**Interfaces:**
- Consumes: `_NormalisedSchedule` with its five fields (Task 4).
- Produces:
  - `admin_users._contract_rule_error(norm, current: Schedule, effective_from: date) -> Optional[tuple[int, str]]`, which returns `(422, MINIJOB_MONTH_START_DETAIL)` or `(400, <fixed-mode text>)` or `None`.
  - The constant `MINIJOB_MONTH_START_DETAIL = "Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten."`

- [ ] **Step 1: Write the failing tests**

```python
def test_minijob_field_change_on_15th_is_422(...):
    r = post(eff="2027-01-15", agreed_monthly_hours=45.0, **same_hours)
    assert r.status_code == 422 and r.json()["detail"] == "Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten."
def test_minijob_field_change_on_1st_ok(...):                       # 201
def test_hours_only_change_mid_month_keeps_minijob_fields(...):     # Review Focus 1: fixed-mode person, eff 15th, no minijob keys → 201
def test_fixed_mode_requires_track_hours_on_snapshot(...):
    # person fixed=True, milog=True, agreed 43.3; POST eff 1st with track_hours=False only
    assert r.status_code == 400 and r.json()["detail"] == "Fester Monats-Soll setzt Stundenzählung (track_hours) voraus."
def test_preview_reports_rule_errors_as_blocked_reason(...):         # same two texts, 200 with blocked_reason
@pytest.mark.parametrize("field,value", [("vacation_days", 30), ("track_hours", False),
    ("milog_working_time_account", True), ("agreed_monthly_hours", 45), ("use_fixed_monthly_target", True)])
def test_put_user_rejects_historised_contract_field(field, value, ...):   # 400
def test_put_user_without_contract_fields_ok(...):                   # 200 (UserForm edit payload)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bt tests/test_contract_history_rules.py`
Expected: FAIL. The current responses are 201 and 200.

- [ ] **Step 3: Implement**
  - The Minijob month rule fires when any of `milog_working_time_account`, `agreed_monthly_hours`, `use_fixed_monthly_target` in `norm` differs from `current` **and** `effective_from.day != 1`.
  - The fixed-mode rule runs on `norm`: fixed ⇒ `agreed > 0`, `track_hours is True`, `milog is True`. It reuses the three existing texts, moved to module constants.
  - Create raises `HTTPException(status, detail)`. Preview sets `blocked_reason = detail`.
  - Add the five names to `_HISTORISED_FIELDS`. New detail: `Wochenstunden, Tagesstunden, Arbeitstage, Arbeitszeit-Blöcke, Urlaubsanspruch, Stundenzählung und Minijob-Einstellungen werden über „Arbeitszeit anpassen…“ mit Wirkungsdatum geändert, damit Historie und Soll vergangener Monate korrekt bleiben.` Update existing tests asserting the old text.

- [ ] **Step 4: Run the tests**

Run: `bt tests/test_contract_history_rules.py tests/test_schedule_mode_switch_guards.py tests/test_user_fixed_mode_validation.py`, plus the other updated PUT tests, and the e2e type check `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/e2e":/app -w /app node:20 npx tsc --noEmit`.
Expected: PASS, tsc 0 errors. (Until Task 15 the UserForm edit still sends `vacation_days` and gets 400 in the real app; Tasks 5 and 15 ship in the same PR.)

- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`feat(admin-users): minijob changes only at month start; contract fields locked on PUT`)

---

### Task 6: Correction at the earliest row (replace instead of "Datum schon belegt")

**Files:**
- Modify: `backend/app/routers/admin_users.py`:
  - create: the duplicate check at `:1906-1914` and `_apply`
  - preview: the duplicate check at `:2254-2259` (sets `blocked_reason`)
  - `_insert_change_rows`: new keyword `replace: Optional[WorkingHoursChange]`
- Test: `backend/tests/test_contract_history_correction.py`

**Interfaces:**
- Consumes: Task 4 normalisation.
- Produces: `_earliest_row(db, user, tenant_id) -> Optional[WorkingHoursChange]`. `_insert_change_rows(..., replace=row)` overwrites the snapshot columns of `row` in place (keeping `id` and `effective_from`, note = `change_data.note`), flushes, **then** runs `_freeze_gap_before`, and returns `row`.

- [ ] **Step 1: Write the failing tests**

```python
def test_change_at_earliest_row_date_replaces_it(...):
    # rows 2020-01-01 (24, baseline) and 2026-11-01 (30); POST eff 2020-01-01 vacation 28
    assert r.status_code == 201 and len(rows) == 2
    assert float(rows[0].vacation_days) == 28.0 and rows[0].id == baseline_id
    assert cs.vacation_entitlement_days(db, u, 2025) == Decimal("28.0")
def test_same_date_on_later_row_still_400(...):     # "Eine Stundenänderung für den 01.11.2026 existiert bereits"
def test_preview_at_earliest_row_has_no_blocked_reason(...):
def test_correction_writes_summary_row_and_requires_reason_when_shortening(...):
    # retro decrease 24 → 20 at earliest row → 400 without reason (Task 7 reason), 201 with reason
```

The last test is marked `xfail(strict=True)` until Task 7. Task 7 removes the mark.

- [ ] **Step 2: Run them to verify they fail**

Run: `bt tests/test_contract_history_correction.py`
Expected: FAIL with 400 "existiert bereits".

- [ ] **Step 3: Implement.** If the row at `effective_from` is the earliest row, set `replace=row`. Otherwise keep the 400. Do the same in the preview. The rest (protection package, audit rows, mirror) stays unchanged.
- [ ] **Step 4: Run the tests.** `bt tests/test_contract_history_correction.py tests/test_wh_change_retroactive.py`. Expected: PASS (one xfail).
- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`feat(wh-change): correct the earliest contract row in place`)

---

### Task 7: Entitlement in both previews, shortening reason, audit text

**Files:**
- Modify: `backend/app/services/wh_change_service.py`:
  - `:29-31` constants
  - `ChangeImpact`
  - `run_change` steps 3 and 7
  - `preview_fields`
  - `criteria_text`
- Modify: `backend/app/schemas/working_hours_change.py:293-420`: `VacationEntitlementOut`, the `vacation_entitlement` field, and the reason literal at `:396`
- Modify: `backend/app/routers/admin_users.py`: `_log_reclamp` (`contract_before/after`) and the delete-preview (`:2425-2505`)
- Modify: `backend/app/services/reclamp_audit.py:104-136`
- Test: `backend/tests/test_contract_history_preview.py`. Remove the `xfail` from Task 6.

**Interfaces:**
- Consumes: `vacation_entitlement_days` (Task 3).
- Produces:
  - `SHORTENING_VACATION_ENTITLEMENT = "vacation_entitlement"`.
  - `ChangeImpact.entitlement: dict[int, tuple[Decimal, Decimal]]` (year → before, after), covering the years `{eff.year, eff.year + 1} ∪ range(eff.year, today.year + 1)`.
  - Preview field `vacation_entitlement: List[VacationEntitlementOut{year: int, before: float, after: float}]` for `[eff.year, eff.year + 1]`, in both `…/preview` and `…/delete-preview`.
  - `reclamp_audit.contract_pair(old: Schedule, new: Schedule) -> tuple[str, str]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_preview_shows_entitlement_for_year_and_next(...):    # customer case, today frozen 2026-11-03
    p = client.post(preview_url, json=body(eff="2026-11-01", work_days_per_week=5, vacation_days=30)).json()
    assert p["vacation_entitlement"] == [{"year": 2026, "before": 24.0, "after": 25.0},
                                         {"year": 2027, "before": 24.0, "after": 30.0}]
def test_delete_preview_shows_entitlement_back(...):            # 2026: 25 → 24, 2027: 30 → 24
def test_retroactive_entitlement_decrease_is_shortening(...):
    # person 24 since 2020 (baseline row); eff 2026-10-01 (< today 2026-11-03), vacation 20
    # 2026: 24 → 24×9/12 + 20×3/12 = 23
    assert "vacation_entitlement" in p["shortening_reasons"]
    r = post_without_reason(...)
    assert r.status_code == 400 and "Urlaubsanspruch 2026 24 → 23 Tage" in r.json()["detail"]
def test_decrease_from_today_or_future_is_not_shortening(...):  # eff 2026-11-03 and 2027-01-01
def test_summary_row_names_changed_contract_terms(...):
    note = summary_row(db, u).new_note
    assert note.endswith("Vertrag: 40,0 h/Woche (gleichmäßig, 4 Tage) · Urlaub 24 → 40,0 h/Woche (gleichmäßig, 5 Tage) · Urlaub 30")
    assert reclamp_audit.parse_summary_note(note) is not None
def test_hours_only_change_summary_text_unchanged(...):         # no " · Urlaub" suffix when the entitlement is equal
def test_entitlement_change_in_closed_year_warns_and_recalculates_nothing(...):   # spec A4 „Abgeschlossene Jahre“
    # YearCarryover year=2026 source="year_closing" (2025 closed); eff 2025-06-01 vacation 30, with reason
    assert r.status_code == 201 and r.json()["warning"]          # stale_year_closing_warning text
    assert carryover_2026.vacation_days unchanged                # nothing recalculated (Fix #5)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bt tests/test_contract_history_preview.py`
Expected: FAIL with `KeyError: 'vacation_entitlement'`.

- [ ] **Step 3: Implement**
  - **Classification in `run_change`.**
    - Step 3 computes `ent_before`. Step 7 computes `ent_after`.
    - When `effective_from < today` and any year in `range(eff.year, today.year + 1)` has `after < before`, append `SHORTENING_VACATION_ENTITLEMENT`.
    - Those years join `loss_years`.
    - `earliest_lossless_date` candidates are unchanged, because `today` is already a candidate.
  - **`criteria_text`.**
    - The part reads `Urlaubsanspruch {Jahr} {alt} → {neu} Tage`, joined by `; `.
    - Numbers use German decimals without a trailing `,0` (`24`, `24,5`). Add one helper `reclamp_audit.format_days_de(value) -> str` and use it here and in `contract_pair` (one formatter for both texts).
  - **`contract_pair`.**
    - It appends each term that differs between `old` and `new` to both sides, in this order:
      1. ` · Urlaub {format_days_de(n)}`
      2. ` · mit Stundenzählung` / ` · ohne Stundenzählung`
      3. ` · MiLoG-Konto an` / ` · MiLoG-Konto aus`
      4. ` · Monatsstunden {format_hours_de(h)}` / ` · Monatsstunden abgeleitet`
      5. ` · festes Monats-Soll an` / ` · festes Monats-Soll aus`
    - `_log_reclamp` uses it instead of the two `contract_text(..., compact=True)` calls.
    - `contract_text` itself stays unchanged (it is the dashboard hint).
    - `_HEAD`/`_RESET` are untouched.
  - **Schemas.** Add `"vacation_entitlement"` to the `shortening_reasons` Literal. Add `VacationEntitlementOut`.
  - **Preview.** In the no-run branch (snapshot unchanged or blocked), `before == after` from one call.

- [ ] **Step 4: Run the tests**

Run: `bt tests/test_contract_history_preview.py tests/test_contract_history_correction.py tests/test_reclamp_audit.py tests/test_wh_change_preview.py`
Expected: PASS.

- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`feat(wh-change): entitlement before/after in previews; retroactive decrease needs a reason`)

---

### Task 8: `track_hours` per day — `calculation_service`

**Files:**
- Modify: `backend/app/services/calculation_service.py`, at these sites (verify the line numbers with `grep -n "track_hours" backend/app/services/calculation_service.py`):

| Site | New rule |
|---|---|
| `get_daily_target_for_date` `:969` | `if not schedule.track_hours: return 0` (central switch for every per-day Soll loop) |
| `get_daily_target` `:939` | unchanged (no date, only for the classic export corner); Task 12 allowlist |
| `counts_vacation_by_day_only` `:897-912` | new signature `counts_vacation_by_day_only(db, user, d, wh_changes=None) -> bool` = `not tracks_hours_on(...)` |
| `is_vacation_billable_day` `:1041` | resolve `schedule` first (moves above the gate), then `if not schedule.track_hours: return True`. `absence_booking_dates` (`:1053`, via `:1085`) and `request_day_count`/`vacation_day_cost_by_year` (`:3284`) follow automatically |
| `get_day_presence_target` `:1566` | `tracks_hours_on(db, user, d)` |
| `future_freizeitausgleich_impact` `:1629` | per OVERTIME day: skip untracked days; fixed mode per month (Task 11) |
| `get_range_target` `:1726`, `get_gross_monthly_target` `:1953` | drop the early return (per-day via `get_daily_target_for_date`) |
| `get_overtime_accounts` `:2071`, `get_overtime_history_detailed` `:2402`, `get_ytd_summary` `:2629` | drop the early return; in the month loop, Ist of time entries **and** SICK/TRAINING credits on untracked days count 0 (Soll is 0 through the central switch) |
| `get_range_actual` | unchanged (has no gate today; keeps exports bit-identical) |
| `_vacation_reference_daily_target` `:2922` | `schedule.track_hours` of the reference-date snapshot |
| `get_vacation_account` `:3141` day-only branch, `absence_days` `:2812` | one loop: each absence/deduction day is counted in its own day's mode. Returned `"track_hours"` sentinel and `budget_hours` = reference-date snapshot |
| `retarget_absence_hours` `:653` | removed in Task 10 (not here) |

- Modify: `backend/app/routers/admin_change_requests.py:66` (`_vacation_day_contribution`), which now calls `counts_vacation_by_day_only(db, user, d)`.
- Test: `backend/tests/test_contract_history_track_hours_calc.py`

**Interfaces:**
- Consumes: `tracks_hours_on`, `Schedule.track_hours` (Task 2).
- Produces: the new `counts_vacation_by_day_only(db, user, d, wh_changes=None) -> bool`. All other public signatures are unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_track_hours_off_from_july_keeps_january_to_june(db, test_user):     # spec A5
    seed entries Mon–Fri 2026-01..2026-09, 9 h net each (+1 h/day), row 2026-01-01 tracked, 40 h/5 days
    before = [cs.get_overtime_account(db, test_user, 2026, m) for m in range(1, 7)]
    add_row(db, test_user, date(2026, 7, 1), weekly_hours=40, track_hours=False)
    test_user.track_hours = False; db.commit()      # the mirror after the write (realistic state)
    assert [cs.get_overtime_account(db, test_user, 2026, m) for m in range(1, 7)] == before
    assert cs.get_overtime_account(db, test_user, 2026, 9) == before[-1]       # July–Sept add 0
    assert cs.get_monthly_target(db, test_user, 2026, 8) == Decimal("0.00")
def test_ytd_summary_mixed_year(...):           # Soll/Ist only for Jan–Jun
def test_vacation_used_days_mixed_year(...):    # June vacation counted by hours/target, August vacation 1 day each
def test_counts_vacation_by_day_only_per_day(...):
def test_always_tracked_and_always_untracked_unchanged(...):   # bit-identical vs. without rows
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bt tests/test_contract_history_track_hours_calc.py`
Expected: FAIL. The account reads the live flag.

- [ ] **Step 3: Implement** per the table. The `wh_changes` preload each function already loads is passed to `tracks_hours_on`, so there is no per-day query.
- [ ] **Step 4: Run the tests.** `bt tests/test_contract_history_track_hours_calc.py tests/test_gesamtreview_b11_vacation_untracked.py tests/test_calc_preload.py tests/test_494_clock_status_today.py`. Expected: PASS.
- [ ] **Step 5: Full backend suite.** Expected: `0 failed`. Same rule as Task 3 Step 5: a test that adds rows and then flips `user.track_hours` directly gets `track_hours=` on its row instead.
- [ ] **Step 6: Commit** (`feat(calc): track_hours resolved per day`)

---

### Task 9: `track_hours` per day — other services and routers

**Files (each `user.track_hours` / `User.track_hours` read becomes a snapshot read):**

| Site | Snapshot |
|---|---|
| `routers/company_closures.py:297, 338, 778` | `schedule.track_hours` of the workday (the schedule is already resolved at `:313`); `:297` (`emp_split`) becomes per workday; `:778` per linked absence date |
| `services/closure_split_service.py:124` | per day: untracked closure days keep VACATION, tracked days take part in the split |
| `routers/dashboard.py:32` (`_get_missing_bookings_for_user`), `:288`, `:408` | `tracks_hours_on(db, user, today_local())` |
| `routers/dashboard.py:435` (SQL filter in `get_team_missing_bookings`, `GET /api/dashboard/missing-bookings/team`) | load active visible users, filter in Python with `tracks_hours_on(today)` (one `working_hours_changes` preload for all) |
| `routers/reports.py:113, 169, 256, 311` | `tracks_hours_in_range(db, user, start, end, wh_changes)` = any day tracked |
| `routers/team_schedule.py:67` | snapshot at the requested date |
| `services/work_schedule_service.py:54` | snapshot today |
| `routers/time_entries.py:387` | `tracks_hours_on(today)` |
| `routers/admin_users.py:615` (`users_overview` response) | snapshot today (preload `_uwh`) |
| `services/wh_change_service.py:238` | `impact`'s new snapshot for today: `tracks_hours_on(db, user, today)` after `apply` |

- Modify: `backend/app/services/calculation_service.py`, new `tracks_hours_in_range(db, user, start, end, wh_changes=None) -> bool`.
- Test: `backend/tests/test_contract_history_track_hours_routes.py`

**Interfaces:**
- Consumes: `tracks_hours_on` (Task 2).
- Produces: `tracks_hours_in_range(db, user, start: date, end: date, wh_changes=None) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_future_row_switching_track_hours_off_applies_without_mirror(...):   # Review Focus 2
    add_row(db, u, date(2026, 12, 1), weekly_hours=40, track_hours=False)    # u.track_hours stays True
    entry(db, u, date(2026, 12, 1), t(8), None)                             # open entry → would be „Buchung fehlt“
    freeze(monkeypatch, date(2026, 12, 2))
    assert employee_client.get("/api/dashboard/missing-bookings").json()["entries"] == []
    assert str(u.id) not in [x["user_id"] for x in admin_client.get("/api/dashboard/missing-bookings/team").json()]
def test_closure_on_untracked_day_books_vacation_day_without_hours(...):
def test_closure_split_mixed_year(...):
def test_reports_monthly_track_hours_flag_per_period(...):
def test_team_schedule_uses_snapshot_at_date(...):
```

(Response shape: `schemas/reports.py:216` `MissingBookings{user_id, first_name, last_name, entries}`.)

- [ ] **Step 2: Run them to verify they fail.** `bt tests/test_contract_history_track_hours_routes.py`. Expected: FAIL.
- [ ] **Step 3: Implement** per the table.
- [ ] **Step 4: Run the tests.** `bt tests/test_contract_history_track_hours_routes.py tests/test_closure_overtime_split.py tests/test_team_schedule.py tests/test_me_work_schedule.py`. Expected: PASS.
- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`feat: dashboards, reports and closures read track_hours from the snapshot`)

---

### Task 10: Retroactive `track_hours` change (Variante A)

**Files:**
- Modify: `backend/app/services/wh_change_service.py` (`run_change` step 5: weekdays)
- Modify: `backend/app/services/work_window_service.py`:
  - `:194-203` `clamp_applies`
  - `:218-220` `_clamp_core`
  - `:853-854` `reclamp_time_entries` step 1
  - `:977` `stale_clamp_entries`
- Modify: `backend/app/services/calculation_service.py:653` and the day loop in `retarget_absence_hours`
- Test: `backend/tests/test_contract_history_track_hours_retro.py`

**Interfaces:**
- Consumes: `Schedule.track_hours`, `tracks_hours_on`.
- Produces: no new public names. `clamp(...)` returns the unclamped result (`raw_*=None`, `uncredited=0`, `grace_minutes=None`) on days whose snapshot has `track_hours=False`.

- [ ] **Step 1: Write the failing tests**

```python
def test_track_hours_on_from_june_retroactive(db, u, admin_client, monkeypatch):   # spec A3 test
    # u untracked since 2026-01-01 (row), blocks 08:00–12:00 Mo–Fr, pause 0 → day target 4,00 h
    # (derive_targets); entry 2026-06-02 07:00–13:00 (raw none); grace 15 → hull 07:45–12:15
    # vacation 2026-06-03 hours 0; today frozen 2026-11-03
    may_before = cs.get_monthly_balance(db, u, 2026, 5)
    r = admin_client.post(url, json=body(eff="2026-06-01", track_hours=True, reason=FULL_REASON))
    assert r.status_code == 201
    assert float(absence_0603.hours) == 4.0            # day target from the blocks, not 8
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time) == (t(7, 45), t(12, 15), t(7), t(13))
    assert cs.get_monthly_balance(db, u, 2026, 5) == may_before
    assert summary_row(db, u) is not None
def test_delete_restores_bit_identical(...):
    snapshot = state(db, u)   # per entry (start,end,raw_start,raw_end,uncredited,net_hours,auto_closed),
                              # per absence (hours, raw_hours), monthly balance 2026-01..12
    create; delete (with reason); assert state(db, u) == snapshot
def test_track_hours_off_unclamps_and_zeroes_absences(...):     # raw → effective, uncredited 0, SICK/VACATION hours 0
def test_credit_override_entry_untouched(...):
def test_changed_weekdays_all_on_track_hours_change(...):       # impact.changed_weekdays == [0,1,2,3,4]
def test_blocks_with_track_hours_off_are_stored_and_inert(...): # Review Focus 5: 201, row.blocks set, entries unclamped
```

- [ ] **Step 2: Run them to verify they fail.** `bt tests/test_contract_history_track_hours_retro.py`. Expected: FAIL. Absence hours stay 0, and the entries are unchanged.
- [ ] **Step 3: Implement**
  - **`run_change` step 5:** `weekdays = [0,1,2,3,4] if old_schedule.track_hours != new_schedule.track_hours else changed_weekdays(...)`.
  - **`_clamp_core` / `clamp_applies` / `stale_clamp_entries`:** replace the user flag with `tracks_hours_on(db, user, d, wh_changes=wh_changes)`.
  - **`reclamp_time_entries`:** delete step 1. Per entry, a day whose new snapshot is untracked goes through `clamp`, which returns raw = effective. The existing P18 23:59 handling stays. `credit_override` is still skipped (step 4).
  - **`retarget_absence_hours`:**
    - Drop the user-level early return.
    - On a day whose snapshot is untracked, the target is 0 for every non-OVERTIME type (also VACATION/PAID_LEAVE/OTHER, not only SICK/TRAINING).
    - On tracked days the existing rules apply.
    - `raw_hours` stays untouched.
  - **Documented decision:** `clamp_grace_minutes` is not reset by the unclamp. The bit-identity test excludes it, and its docstring says why.
- [ ] **Step 4: Run the tests.** `bt tests/test_contract_history_track_hours_retro.py tests/test_wh_change_retroactive.py tests/test_wh_change_delete_reclamp.py tests/test_credit_override.py tests/test_retarget_absence_hours.py`. Expected: PASS.
- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`feat(wh-change): retroactive track_hours change re-clamps entries and retargets absences`)

---

### Task 11: Minijob fields per month

**Files:**
- Modify: `backend/app/services/calculation_service.py`:
  - `:1090-1107` `fixed_monthly_target`
  - `:1249-1270` `fixed_month_credit` / `fixed_month_unpaid_reduction`
  - `:1645`, `:1731`, `:1895`, `:2116`, `:2523`, `:2657` (fixed-mode branches)
- Modify: `backend/app/services/milog_service.py:34-150`, `journal_service.py:111-112`, `work_schedule_service.py:46-55`, `routers/team_schedule.py:68`
- Modify: `routers/dashboard.py:221`, `routers/time_entries.py:887, 1235, 1819`, `routers/admin_users.py:587`, `services/wh_change_service.py:344-354` (`milog_warnings(user, impact)`: read `impact.new_schedule.milog_working_time_account` / `.agreed_monthly_hours`, the snapshot at `effective_from`; no new parameter)
- Modify: `backend/tests/test_fixed_monthly_target.py:26-37` (calls `cs.fixed_monthly_target(u, …)` → new signature with `db`); `calculation_service.py:1745` is the only production caller
- Test: `backend/tests/test_contract_history_minijob.py`

**Interfaces:**
- Consumes: `Schedule` fields (Task 2).
- Produces:
  - `MonthContract(NamedTuple)` with `track_hours: bool`, `milog_working_time_account: bool`, `agreed_monthly_hours: Optional[Decimal]`, `use_fixed_monthly_target: bool`, and the property `fixed_mode -> bool` (`use_fixed_monthly_target and agreed_monthly_hours and agreed > 0`).
  - `calculation_service.month_contract(db, user, year: int, month: int, wh_changes=None) -> MonthContract` (snapshot on the first of the month).
  - `fixed_monthly_target(db, user, year, month, wh_changes=None) -> Decimal` (new first parameter `db`).
  - `milog_service.agreed_monthly_hours(db, user, ref_date)` reads `month_contract(ref_date.year, ref_date.month).agreed_monthly_hours`. Explicit value → exact. NULL → `weekly_hours(ref_date) × 13/3`.

- [ ] **Step 1: Write the failing tests**

```python
def test_agreed_raise_from_2027_keeps_2026_target(db, minijob_user):   # spec A5
    # fixed mode, agreed 43.3, rows 2026-01-01; new row 2027-01-01 agreed 45
    before = [cs.get_monthly_target(db, minijob_user, 2026, m) for m in range(1, 13)]
    add_row(db, minijob_user, date(2027, 1, 1), weekly_hours=10, agreed_monthly_hours=45,
            use_fixed_monthly_target=True, milog_working_time_account=True)
    minijob_user.agreed_monthly_hours = 45; db.commit()     # the mirror (as after a write on/after 2027-01-01)
    assert [cs.get_monthly_target(db, minijob_user, 2026, m) for m in range(1, 13)] == before
    assert cs.get_monthly_target(db, minijob_user, 2027, 3) == Decimal("45.00")
def test_fixed_mode_switched_on_mid_year_applies_from_month(...):
def test_milog_50_check_off_in_months_without_account(...):
def test_settlement_aging_skips_months_without_account(...):
def test_agreed_monthly_hours_by_month(...):     # milog_service.agreed_monthly_hours(db, u, date(2026, 12, 1)) == 43.3, 2027 → 45
def test_users_overview_milog_gate_uses_today_snapshot(...):
```

- [ ] **Step 2: Run them to verify they fail.** `bt tests/test_contract_history_minijob.py`. Expected: FAIL. The 2026 targets read the mirrored 45 instead of 43,3.
- [ ] **Step 3: Implement**
  - Every `getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None)` becomes `month_contract(db, user, y, m, wh_changes).fixed_mode` **inside the month loop**, not once per person.
  - In `get_overtime_accounts`, replace the single `fixed_mode` (`:2116`) with a per-month value in `_month_delta`.
  - `milog_50_check`, `monthly_exceeded_check` and `settlement_aging` gate on the month contract. `settlement_aging` FIFO takes only the months with `milog_working_time_account=True`, and it returns `None` when the `as_of` month has no account.
  - Push sites gate on `month_contract(today)`.
  - Every gate that today reads `user.milog_working_time_account and user.track_hours` (`milog_service.py:62, 136`, `dashboard.py:221`, `admin_users.py:587`) reads both from the same `MonthContract` (`mc.milog_working_time_account and mc.track_hours`); `milog_service.py:105` likewise (`mc.use_fixed_monthly_target and mc.track_hours`).
- [ ] **Step 4: Run the tests.** `bt tests/test_contract_history_minijob.py` plus the existing `tests/test_*377*` / `tests/test_*milog*` / `tests/test_*fixed*` (find them with `ls backend/tests | grep -i "milog\|377\|fixed"`). Expected: PASS.
- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`feat(calc): minijob settings resolved per month`)

---

### Task 12: Guard against live reads, and `users-overview` without N+1

**Files:**
- Create: `backend/tests/test_no_live_contract_field_read.py` (pattern `tests/test_no_live_work_blocks_read.py`)
- Modify: `backend/tests/test_calc_preload.py::test_users_overview_preload_constant_query_count` (extend)
- Modify: any remaining site the guard finds

**Interfaces:**
- Consumes: everything from Tasks 2–11.

- [ ] **Step 1: Write the guard test**
  - It uses `ast` over `app/services` and `app/routers`.
  - Flag `Attribute` nodes (any `ctx`) with `attr in FIELDS` (the five names) whose value is
    - `ast.Name` with `id in USER_NAMES = {"user", "u", "current_user", "employee", "emp", "User"}`, or
    - an `ast.Subscript` or `ast.Call` (e.g. `_participants_by_id[a.user_id].track_hours`, `company_closures.py:778`; `users.get(id).track_hours`). Snapshot reads always go through a named variable (`schedule`, `mc`, `norm`, `row`), so these receivers are user rows.
  - Also flag `getattr/setattr/hasattr(<such receiver>, "<field>")`.
  - Not flagged (and so not in `ALLOWED`): reads on request bodies (`user_data.track_hours` in `create_user` `:1194`, `update_data`), on history rows and on schedules.
  - The result must equal `ALLOWED`:

```python
ALLOWED = {
    ("app/services/calculation_service.py", "get_schedule_for_date"),   # no-row fallback
    ("app/services/calculation_service.py", "get_daily_target"),        # legacy, classic export corner
    ("app/routers/admin_users.py", "_sync_user_from_change"),           # mirror
    ("app/routers/auth.py", "export_my_data"),                          # Art. 15/20 raw export
    ("app/services/lifecycle_service.py", "_user_dict"),
    ("app/routers/superadmin.py", "_user_dict"),
}
```

  Also add `assert ("app/routers/admin_users.py", "_sync_user_from_change") in found`, so the finder is not vacuous. If the implementer must allow another site, it goes in with a one-line reason comment.

- [ ] **Step 2: Extend the N+1 test** with a fixed-mode MiLoG person with two rows and a person with a mid-year `track_hours` change. It still asserts `counts["wh"] == 1`.
- [ ] **Step 3: Run.** `bt tests/test_no_live_contract_field_read.py tests/test_calc_preload.py`. Expected: first FAIL, listing the leftover sites.
- [ ] **Step 4: Fix the leftover sites** (snapshot read with the preload), then rerun. Expected: PASS.
- [ ] **Step 5: Full backend suite.** Expected: `0 failed`.
- [ ] **Step 6: Commit** (`test: guard against live reads of historised contract fields`)

---

### Task 13: Dialog section „Urlaub und Abrechnung“

**Files:**
- Create: `frontend/src/pages/admin/users/ContractTermsFields.tsx`. It holds the entitlement input and the controls cut out of `UserForm.tsx`: „Stundenzählung aktiv“ checkbox `:712-724`, MiLoG block `:752-~840`. Their labels and dependencies stay unchanged.
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.tsx`:
  - `:66-92` `ScheduleSnapshot`/`FormState`
  - `:124` `scheduleFromChange`
  - `:144` `scheduleAt`
  - `:214` `comparableSnapshot`
  - `:226` `formFromSnapshot`
  - `:360-384` `scheduleBody`/`previewKey`
  - `:549-570` `inputSchedule`
  - JSX after the hours fields (~`:842`)
  - history cards `:1064-1080`
  - prop `trackHours` → form value
- Modify: `frontend/src/pages/admin/users/workingHoursTypes.ts:8-24` (five optional fields)
- Modify: `frontend/src/types/user.ts:14` (`interface ScheduleToday`, used by `User.schedule_today` at `:68`)
- Modify: `frontend/src/utils/formatters.ts` (new `formatDayNumber`, next to `formatDayCount` `:145`)
- Modify: `frontend/src/pages/admin/Users.tsx:970-994`, `frontend/src/pages/admin/TeamSchedule.tsx:444` (pass `currentContract` from `schedule_today`)
- Modify: `frontend/src/pages/admin/users/UserForm.tsx` (create mode uses `ContractTermsFields`)
- Test: `frontend/src/pages/admin/users/WorkingHoursModal.test.tsx`, `ContractTermsFields.test.tsx`, `frontend/src/utils/formatters.test.ts`

**Interfaces:**
- Consumes: the history GET fields and `schedule_today` fields (Tasks 2/4).
- Produces:
  - `export interface ContractTerms { vacation_days: number; track_hours: boolean; milog_working_time_account: boolean; agreed_monthly_hours: number | null; use_fixed_monthly_target: boolean }` in `workingHoursTypes.ts`.
  - `export function suggestEntitlement(oldDays: number, oldWd: number, newWd: number): number | null`. Returns `null` when `oldWd <= 0 || newWd <= 0 || newWd === oldWd`, else `Math.round(oldDays * newWd / oldWd * 10) / 10`.
  - `<ContractTermsFields value={ContractTerms} onChange={(v) => void} mode="create" | "change" suggestion={number | null} idPrefix={string} />`. In `UserForm` (create) `idPrefix=""`, so the element ids stay `vacation_days`, `track_hours`, `milog_working_time_account` (E2E: `prod-release-features.spec.ts:100`, `visual-prod-release.spec.ts:22`); in the dialog `idPrefix="wh-"`, so no id is duplicated while both are mounted.
  - `formatDayNumber(n: number): string` in `utils/formatters.ts` — bare German number without unit (`30`, `13,1`, `24,5`).
  - Prop `currentContract?: ContractTerms` on `WorkingHoursModal`.

- [ ] **Step 1: Write the failing tests**

```tsx
it('suggests 30 for 24 days from 4 to 5 days', () => expect(suggestEntitlement(24, 4, 5)).toBe(30));
it('suggests 13,1 for 17,5 days from 4 to 3 days', () => expect(suggestEntitlement(17.5, 4, 3)).toBe(13.1));
it('no suggestion without work days', () => expect(suggestEntitlement(24, 4, 0)).toBeNull());
it('auto-follows the suggestion until edited, then offers „Vorschlag übernehmen (30)"', async () => {
  // render modal with history 24 / 4 days; set work days 5 → field shows 30
  // type 28 → field 28, link text "Vorschlag übernehmen (30)" visible; click → 30
});
it('sends the five contract fields in preview and create body', ...);  // previewKey includes them
it('a pure entitlement change enables Speichern', ...);                // comparableSnapshot includes contract
it('history card shows „Urlaub 30 Tage/Jahr" and „ohne Stundenzählung"', ...);
it('scheduleAt before the first row uses the first row contract', ...);
it('unchecking Stundenzählung in block mode keeps the blocks in the body', ...);   // Review Focus 5
  // history row with blocks, mode „Nach Arbeitsblöcken“; uncheck „Stundenzählung aktiv“ →
  // mode unchanged, create body has `blocks` and `track_hours: false`, blocks line shows the „ohne Wirkung“ text
// in src/utils/formatters.test.ts:
it('formatDayNumber', () => { expect(formatDayNumber(30)).toBe('30'); expect(formatDayNumber(13.1)).toBe('13,1'); });
```

- [ ] **Step 2: Run them to verify they fail.** `ft src/pages/admin/users/WorkingHoursModal.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - The section heading is `Urlaub und Abrechnung`. The entitlement label is `Urlaubsanspruch pro Jahr ab diesem Datum` (number, `step="0.1"`, `min="0"`, `max="50"`).
  - Keep the state `entitlementTouched: boolean`. While it is `false`, a work-day change sets `vacation_days = suggestion`. Once `true`, show the link `Vorschlag übernehmen (${formatDayNumber(s)})`.
  - Block-mode availability and `blocksLine`/`describeSchedule` read the **form's** `track_hours` instead of the `trackHours` prop; the option „Nach Arbeitsblöcken“ stays offered while the current mode is `blocks`, so unchecking the box never drops the blocks.
  - "New work days" means: `formData.work_days_per_week` in even mode, `plannedDays` in days mode, `derived.workDays` in blocks mode. "Old" values are the baseline snapshot at `effective_from`.
  - `scheduleBody` spreads `...contract` in **all** modes, also the blocks branch.
  - `comparableSnapshot` appends the contract.
  - History card lines:
    - `Urlaub {formatDayNumber(n)} Tage/Jahr`
    - `ohne Stundenzählung` when false
    - when MiLoG is on: `MiLoG-Arbeitszeitkonto` · `{h} h/Monat vereinbart` (if set) · `festes Monats-Soll` (if on)
- [ ] **Step 4: Run the tests.** `ft src/pages/admin/users/WorkingHoursModal.test.tsx`, `ft src/pages/admin/users/ContractTermsFields.test.tsx`, `ft src/pages/admin/users/UserForm.test.tsx`, `ft src/utils/formatters.test.ts` (the `formatDayNumber` case goes there), plus `npx tsc --noEmit`. Expected: PASS, tsc 0 errors.
- [ ] **Step 5: Commit** (`feat(ui): contract terms in the working-hours dialog with entitlement suggestion`)

---

### Task 14: Impact box, shortening reason, delete panel

**Files:**
- Modify: `frontend/src/pages/admin/users/WhImpactBox.tsx:60-170`
- Modify: `frontend/src/pages/admin/users/workingHoursTypes.ts:27` (`ShorteningReason`), `:54-100` (`interface WorkingHoursChangePreview`)
- Modify: `frontend/src/pages/admin/users/workingHoursTexts.ts:196-235` (`shorteningHeadlines`)
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.tsx:533-546` (`affectsBalance`)
- Modify: `frontend/src/pages/admin/users/WhDeletePanel.tsx` (shows the same box rows from the delete-preview)
- Test: `WhImpactBox.test.tsx`, `workingHoursTexts.test.ts`, `WorkingHoursModal.test.tsx`

**Interfaces:**
- Consumes: `vacation_entitlement` and `"vacation_entitlement"` (Task 7).
- Produces: `ShorteningReason = 'entries' | 'saldo' | 'absence_credit' | 'vacation_entitlement'`, and `WorkingHoursChangePreview.vacation_entitlement?: { year: number; before: number; after: number }[]`.

- [ ] **Step 1: Write the failing tests**

```tsx
it('renames the used row to „Urlaub verbraucht 2026"', ...);
it('shows „Urlaubsanspruch 2026" 24 → 25 and „Urlaubsanspruch 2027" 24 → 30', ...);
it('headline for vacation_entitlement', () =>
  expect(shorteningHeadlines(p({ shortening_reasons: ['vacation_entitlement'],
    vacation_entitlement: [{ year: 2026, before: 24.5, after: 24 }, { year: 2027, before: 30, after: 30 }] })))
    .toContain('Der Urlaubsanspruch 2026 sinkt von 24,5 auf 24 Tage'));
it('shows the impact box for a pure entitlement change', ...);   // Review Focus 3
it('delete panel shows entitlement before → after', ...);
```

- [ ] **Step 2: Run them to verify they fail.** `ft src/pages/admin/users/WhImpactBox.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - Rows: `Urlaub verbraucht ${vacationYear}` (renamed), then one row `Urlaubsanspruch ${year}` per entry, with before, after and signed Δ via `formatDayCount`/`signedDays`.
  - `affectsBalance` also counts `vacation_entitlement.some(e => e.before !== e.after)`.
  - Headline: `Der Urlaubsanspruch {Jahr} sinkt von {alt} auf {neu} Tage` (numbers via `formatDayNumber`), one per sinking year.
- [ ] **Step 4: Run the tests.** The three test files plus `tsc`. Expected: PASS.
- [ ] **Step 5: Commit** (`feat(ui): entitlement rows and shortening reason in the impact box`)

---

### Task 15: `UserForm` edit is read-only for the five fields; AdminDashboard wording

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx`:
  - `:300-305` (strip the five fields from `updateData`)
  - `:621-646` and `ContractTermsFields` usage (edit = display of `editUser.schedule_today` values + hint + button „Arbeitszeit anpassen…“, which calls `onOpenHoursHistory`)
- Modify: `frontend/src/pages/admin/AdminDashboard.tsx:249`
- Test: `frontend/src/pages/admin/users/UserForm.test.tsx`, `frontend/src/pages/admin/AdminDashboard.test.tsx` (exists)

**Interfaces:**
- Consumes: `ContractTermsFields mode="create"` (Task 13), `schedule_today` (Task 2).

- [ ] **Step 1: Write the failing tests**

```tsx
it('edit PUT never sends the five contract fields', async () => {
  // render with editUser, submit → apiClient.put payload has none of
  // vacation_days, track_hours, milog_working_time_account, agreed_monthly_hours, use_fixed_monthly_target
});
it('edit shows today\'s entitlement read-only with „Ändern über „Arbeitszeit anpassen…“"', ...);
it('create keeps the editable field and the 30 × days ÷ 5 suggestion', ...);
it('year-closing delete dialog says manual carryovers stay', ...);
```

- [ ] **Step 2: Run them to verify they fail.** `ft src/pages/admin/users/UserForm.test.tsx` and `ft src/pages/admin/AdminDashboard.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - In edit mode, show the values from `editUser.schedule_today` as text: `{formatDayNumber(n)} Tage/Jahr`, `Stundenzählung aktiv`/`ohne Stundenzählung`, and the Minijob values if MiLoG is on. Below them goes the hint `Ändern über „Arbeitszeit anpassen…“` and the existing `Arbeitszeit anpassen…` button.
  - AdminDashboard: replace `Manuelle Übernahmen für ${currentYear + 1} gehen ebenfalls verloren.` with `Von Hand eingetragene Übernahmen für ${currentYear + 1} bleiben erhalten.`
- [ ] **Step 4: Run the tests** and `tsc`. Expected: PASS.
- [ ] **Step 5: Full frontend suite** `npx vitest run --pool=threads --maxWorkers=2`. Expected: all pass.
- [ ] **Step 6: Commit** (`feat(ui): user form shows contract terms read-only when editing`)

---

### Task 16: PostgreSQL round trip and bit-identity probe

**Files:**
- Create: `backend/tests/test_075_contract_history_pg.py` (pattern `tests/test_073_migration_pg.py`: own throwaway DB, alembic subprocess, `_md5` comparisons)
- Create: `tools/migration-075/probe_075.py` (pattern `tools/migration-073/probe_073.py`)
- Modify: `scripts/local-ci.sh:82-88` (`--ignore`) and `:121-125` (PG step, update the reference-count comment), `.github/workflows/cross-tenant-ci.yml:70-78` (`--ignore`) and `:116-120` (PG step)

**Interfaces:**
- Consumes: migration 075 (Task 1) and every calc change.

- [ ] **Step 1: Write the PG test**

```python
def test_round_trip_075_074_075_and_backfill():
    # seed on 074: users with vacation 24 / track False / milog True / agreed 43.3 / fixed True, 3 rows each
    up to 075 → every row carries its user's five values; the four columns are NOT NULL; agreed NULL stays NULL
    users and all other working_hours_changes columns byte-identical (_md5) after up, down and up again
    down to 074 → the five columns are gone
def test_backfill_as_non_superuser_owner_under_force_rls():   # like 073
```

- [ ] **Step 2: Run on PG**

```bash
docker compose cp backend/alembic backend:/app/ && docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_075_contract_history_pg.py -q </dev/null
```

Expected: `2 passed`.

- [ ] **Step 3: Write `probe_075.py`.**
  - Per person and per year from the first booking to `PROBE_TODAY + 1 year`, it writes sorted JSON with:
    - `get_vacation_account` (all keys except `entitlement_days`, which is new)
    - `get_overtime_account` per month
    - `get_monthly_target`/`get_monthly_actual` per month
    - `get_ytd_summary`
    - `get_overtime_history_detailed`
    - `milog_service.settlement_aging` for MiLoG persons
  - Usage (module docstring):
    1. Restore the prod backup into a throwaway PG 18.
    2. Run the base code (`master` before Teil A) on 074 → `a.json`.
    3. Upgrade to 075.
    4. Run the PR code → `b.json`.
    5. `diff a.json b.json` must be empty.
- [ ] **Step 4: Run the probe** against a copy of the current prod backup (Manuel provides it; see `reference_migration-testing`). Expected: empty `diff`. Record the result in the PR description.
- [ ] **Step 5: Wire it into CI.** Add the new file to both `--ignore` lists and both PG steps.
  Run `bash scripts/local-ci.sh`. Expected: all steps `ok`.
- [ ] **Step 6: Commit** (`test(pg): migration 075 round trip and bit-identity probe`)

---

### Task 17: Documentation (5 surfaces), CLAUDE.md, doc-sync

**Files:**
- `docs/BERECHNUNGEN.md` §8.1 (`:622-643`):
  - Entitlement prorated per segment: formula, customer example 24 × 10/12 + 30 × 2/12 = 25,0, rounding 0,1, a single full-year segment unrounded.
  - Correct the stale line "`get_daily_target(user)` … nicht datumsabhängig" to "Snapshot am Stichtag".
  - §11 (`:1019-1048`, the note at `:1030`): remove "⚠️ Offen (#191)", since the year closing includes untracked persons.
  - New subsection "Stundenzählung und Minijob-Einstellungen ab Datum" (per day / per month, month-first rule); §12.1 „Ohne Stundenzählung“ (`:1051`) and §10.4/10.5 (`:943-1018`) say that the flag and the Minijob values apply from their effective date.
- `docs/GLOSSAR.md`: term "Urlaubsanspruch (anteilig nach Vertragsabschnitten)".
- `docs/handbuch/HANDBUCH-ADMIN.md` `:172-207`: the dialog section „Urlaub und Abrechnung“, suggestion, „Vorschlag übernehmen“, read-only edit form, correction at the earliest row, 422 rule. Also `CHEATSHEET-ADMIN.md:22-27`.
- `frontend/src/components/DocViewer.tsx` (`:198`, `:214`, `:459`, `:525`, `:605`, and `SchnellstartAdmin`) and `frontend/src/constants/helpContent.tsx:198`: the same wording.
- Mirror: copy `HANDBUCH-ADMIN.md` and `CHEATSHEET-ADMIN.md` to `frontend/public/help/`, byte-identical (never `BERECHNUNGEN`/`GLOSSAR`).
- pzweb `/home/manuel/claude/pzweb/frontend/src/pages/marketing/anleitung/HandbuchAdmin.tsx` and `AnleitungBerechnungen.tsx` (plus their tests; run the tests in docker `node:20`). This goes in a separate pzweb PR, merged with the release.
- `scripts/check-doc-sync.sh`:
  - new function `group_vertragsverlauf()` above the line `# --- weitere Gruppen werden oberhalb dieser Zeile eingefügt ---` (`all` discovers groups by `declare -F`), with `need_code` for `Urlaub und Abrechnung`, `Urlaubsanspruch pro Jahr ab diesem Datum`, `Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten.`
  - `need` in the handbook and `DocViewer.tsx`
  - `forbid` `Manuelle Übernahmen für` in `AdminDashboard.tsx`
- `CLAUDE.md`:
  - The rule „Neuer Soll-Treiber → in den Snapshot“ now names the five fields.
  - New one-line rule: "Urlaubsanspruch = `calculation_service.vacation_entitlement_days` (Segmente, 0,1), `track_hours` je Tag (`tracks_hours_on`), Minijob je Monat (`month_contract`); nie `user.<feld>` (Guard `test_no_live_contract_field_read.py`)".
  - Remove the stale "⚠️ Jahresabschluss-Carryover … für untracked noch offen".
  - Add the new PG file to the test-command `--ignore` list and to the "Test-Stratifizierung" list.
- Test: `frontend/src/components/DocViewer.test.tsx`

- [ ] **Step 1: Add the `vertragsverlauf` group and the DocViewer test assertions first.**
  Run `bash scripts/check-doc-sync.sh all`. Expected: FAIL with `FEHLT …` lines.
- [ ] **Step 2: Update all five surfaces and CLAUDE.md.**
- [ ] **Step 3: Verify.**
  Run `bash scripts/check-doc-sync.sh all` and `ft src/components/DocViewer.test.tsx`. Expected: exit 0, PASS.
- [ ] **Step 4: Commit** (`docs: contract history for entitlement, Stundenzählung and minijob settings`)

---

## After the merge (Manuel, spec section 7)

These steps are not code.

1. Once 1.22.0/1.23.0 is installed at the customer, open the dialog for the employee. Enter a change from **01.11.2026** with work days 5 and `Urlaubsanspruch pro Jahr ab diesem Datum` = 30 (the suggestion already shows 30).
2. Check the preview: „Urlaubsanspruch 2026: 24 → 25 · 2027: 24 → 30“.
3. After saving, remove the manual +1 from the 2026 carryover (`CarryoverModal`).
