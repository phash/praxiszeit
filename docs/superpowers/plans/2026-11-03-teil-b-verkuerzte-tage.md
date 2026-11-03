# Teil B — Verkürzte Tage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The admin can cap the daily target of the 24./31.12. and of freely chosen dates at X hours (`Tagessoll = min(Tagessoll laut Snapshot, X)`), with vacation costing 0.5 days, credits following the reduced target, and company closures re-booked automatically.

**Architecture:** One new tenant table `reduced_days` (migration 074) plus a fourth settings mode `max_hours` for 24./31.12. Both are resolved by the existing single source `special_days_service.get_special_day_config` (date-keyed). One new helper `special_days_service.special_day_target(d, daily_target, cfg)` replaces every inline `daily_target × factor`. `credit_day_weight` becomes target-aware and `half_special_day_weight` returns 0.5 for `max_hours`. A new admin router writes reduced days. Each write (and each change of the 24./31.12. setting) re-books the affected company-closure days in the same transaction through a new helper `company_closures.resave_closures_for_dates`. It follows the existing `closure_split_service.rebook_freed_closure_days` pattern (lock, delete the closure rows of the changed dates, `_create_closure_absences`, #314 resplit); `update_closure` itself is not touched.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, Alembic, PostgreSQL 18 (SQLite in the unit suite), openpyxl/odfpy/reportlab, React 18 + TypeScript + Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-03-vertragsverlauf-und-verkuerzte-tage-design.md`. This plan covers sections B1–B5, the Teil-B part of section 5 (Doku) and the release rule in the header. Read the spec sections a task names before you start it.

## Global Constraints

- Release rule (spec header): Teil B is its own PR and may ship alone as **1.22.0** with only migration **074**. Do not bump the version in this plan; `/buildrelease` does that. Work on a branch `feat/verkuerzte-tage` from `master`.
- Rule (B1): on a reduced day, **Tagessoll = min(Tagessoll laut Snapshot, X)**. X is in hours, step **0.25**, range **0.25–12**. A holiday beats a reduced day (target 0). On weekends it has no effect. If the snapshot target is 0, it stays 0.
- Credited time is **not** capped. Work blocks and clamping stay as they are: a reduced day keeps the blocks of its weekday, like `half_day` (#484). No time entries are re-clamped.
- Vacation on a reduced day costs **0.5 days for everyone**. The value comes from `calculation_service.half_special_day_weight` and is never written inline.
- SICK/TRAINING on a reduced day: weight `min(t, X) ÷ t`, where t is the **unweighted** snapshot target; t = 0 gives 0.
- Company closures on a reduced day book `hours = verkürztes Soll` with `half_day = False` and consumption 0.5 (#394 pattern).
- Fixed monthly target (#377 2b): the **month target stays unchanged**. Only `_fixed_planned_hours` uses `min(planned, X)` on a `max_hours` day, never `half_special_day_weight`.
- Settings: mode value `max_hours`; new keys `special_day_dec24_max_hours` and `special_day_dec31_max_hours` (part of the data model, names fixed). If the mode is `max_hours` and no valid hours value is stored, resolution falls back to `DEFAULT_MAX_HOURS = Decimal("4")`.
- Migration 074: table `reduced_days` with these columns:
  - `id` UUID PK
  - `tenant_id` FK `tenants.id` NOT NULL
  - `date` Date NOT NULL
  - `label` `String(100)` NOT NULL
  - `max_hours` `Numeric(4,2)` NOT NULL
  - `created_at` timestamptz `server_default now()`
  - `created_by` FK `users.id` `ON DELETE SET NULL`, nullable
  - unique `(tenant_id, date)`, name `uq_reduced_days_tenant_date`
  - `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy `tenant_isolation`, same text as migration 071
- Revision ID `074_reduced_days` (16 chars ≤ 32), `down_revision = "073_work_blocks"`, file `backend/alembic/versions/2026_11_03_1200-074_reduced_days.py`. Create and run it only via `python -c "from alembic.config import main; main([...])"`, never `python -m alembic`.
- Anti-goal 1: migration 074 changes no past result. It only adds a table, and the round-trip test proves existing tables are byte-identical.
- F-026: every new query on `reduced_days` also carries `ReducedDay.tenant_id == <tid>`, in list, lookup-by-id and delete.
- Fix #5: a change in a closed year only warns (`stale_year_closing_warning` / `closed_year_warning_text`) and never recalculates. **Decision for this plan:** the automatic closure re-save skips dates in closed years (`calculation_service.all_closed_years`); those years get the warning only.
- German UI and API strings fixed by the spec, verbatim:
  - mode label „Verkürzt auf X Stunden“ (spec: „verkürzt auf X Stunden“; capitalised as the first word of an option, like the other three options)
  - section title „Verkürzte Tage“
  - 400 for 24./31.12. as a custom date: „Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden.“
  - calendar and stamp-card fragment: „verkürzter Tag (max. 4 h)“
- German strings chosen by this plan (the spec leaves them open, section 6). Use them verbatim:
  - 409 duplicate: „Für dieses Datum ist bereits ein verkürzter Tag eingetragen.“
  - 404: „Verkürzter Tag nicht gefunden“
  - hours validation (400 in settings, 422 in the schema): „Die Stundenzahl muss zwischen 0,25 und 12 liegen (in Schritten von 0,25).“
  - closure audit reason: „Sondertag oder verkürzter Tag geändert, wird neu gebucht“
  - calendar label: `"<Name>: verkürzter Tag (max. <X> h)"`, where Name is „Heiligabend“, „Silvester“ or the custom label
  - hours formatting: German decimal comma, no trailing zeros (4 → „4“, 4.5 → „4,5“, 4.25 → „4,25“)
- Backend tests are never run in the shared container. From the repo root, define once per shell:
  `PYT() { rm -f backend/test.db backend/test.db-wal backend/test.db-shm; docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend":/app -w /app -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/t.db -e TZ=Europe/Berlin praxiszeit-backend python -m pytest "$@" -q -p no:cacheprovider; }`
  Full SQLite suite: `PYT tests/ --ignore=tests/test_tenant_rls.py --ignore=tests/test_073_migration_pg.py --ignore=tests/test_net_hours_parity_pg.py --ignore=tests/test_reclamp_concurrency.py --ignore=tests/test_handbuch_seed_pg.py --ignore=tests/test_year_closing_lock_pg.py --ignore=tests/test_concurrency.py --ignore=tests/test_074_reduced_days_pg.py`. That is the existing 7 PG files plus the new one.
- PG tests run against the dev stack after copying the code into the built container:
  `docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/ && docker compose cp backend/alembic backend:/app/ && docker compose exec -T backend python -c "from alembic.config import main; main(['upgrade','head'])" </dev/null && docker compose exec -T -e TZ=Europe/Berlin backend pytest <files> -q </dev/null`
  The `upgrade head` step is required: the container runs migrations only at start (`Dockerfile` CMD), and `test_tenant_rls.py` / `test_purge_user_postgres.py` need `reduced_days` in the dev database. Migration test 074 uses its own scratch database and does not depend on it.
- Frontend tests run in docker node:20 from the repo root:
  `FE() { docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/frontend":/app -w /app node:20 npx "$@"; }`
  Then use `FE vitest run <file> --pool=threads`, `FE tsc --noEmit`, `FE eslint src`. Never run vitest, pytest and docker build at the same time (OOM).
- Commits: `git commit -F - <<'EOF' … EOF`, last line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never `--no-verify`.
- Line numbers below were checked against `a0787572`. They are orientation only; function names are authoritative.

## Review Focus

1. **A custom reduced day that is not 24./31.12., at the four hard-coded date pre-filters.** `retarget_absence_hours` (`calculation_service.py:691-694`), `f1_clamp_for_day` (`:889-892`), `_credited_day_context` (`:1425`) and `absences.create_absence` (`absences.py:739-742`) load the special-day config only when the date is `(12, 24)` or `(12, 31)`. For Rosenmontag they would pass no cfg, the credit weight would stay 1, and SICK on that day would credit 8 h against a 4 h target (+4 h phantom overtime), or the F1 clamp would book 6 h instead of 4 h. Tests in Task 4: `test_sick_on_custom_day_credited_reduced` and `test_mixed_day_custom_date_f1_uses_reduced_weight`.
2. **Moving a reduced day to a new date (PUT with a new `date`).** Closures over **both** the old and the new date are re-booked. The old date goes back to the full target (`hours` 8, consumption 1), the new date gets 4 h and consumption 0.5. Test in Task 7.
3. **Changing only the label of a reduced day.** No closure re-save, no audit line, no warning. The closure booking set is identical before and after. Test in Task 7.
4. **A mixed day on a reduced day.** SICK booked with `keep_time_entries` next to a stamped entry runs through `credit_day_weight` in `absences.create_absence` (`absences.py:785`) and `retarget_absence_hours`. It must not raise the "daily_target required" error (500), and the F1 clamp uses the reduced credit. Test in Task 4.
5. **Mode `max_hours` saved before any hours value exists.** This happens with a direct API call, or when the frontend's sequential PUTs are interrupted. The day resolves to 4 h (`DEFAULT_MAX_HOURS`) and nothing returns 500. Test in Task 2.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/alembic/versions/2026_11_03_1200-074_reduced_days.py` (new) | Table + RLS, downgrade drops it |
| `backend/app/models/reduced_day.py` (new) | `ReducedDay` ORM model |
| `backend/app/services/special_days_service.py` | Modes, keys, config resolution incl. reduced days, `special_day_target`, labels, state diffs |
| `backend/app/services/calculation_service.py` | Soll sites, target-aware credit, half weight, fixed mode |
| `backend/app/routers/company_closures.py` | Reduced-target booking, `closure_years`, `resave_closures_for_dates` (`update_closure` unchanged) |
| `backend/app/routers/reduced_days.py` (new) | Admin CRUD `/api/admin/reduced-days` |
| `backend/app/schemas/reduced_day.py` (new) | Create/Update/Response schemas |
| `backend/app/routers/admin_settings.py` | `max_hours` validation, state-based warnings, closure re-save |
| `backend/app/routers/absences.py`, `time_entries.py`, `schemas/time_entry.py`, `main.py` | daily-target endpoint, stamp-card label, public payload |
| `backend/app/services/export_service.py`, `ods_export_service.py`, `journal_service.py` | Exports/journal use the helper |
| `frontend/src/utils/specialDays.ts` | Date-based lookup, `max_hours` label, `reducedDayLabel` |
| `frontend/src/components/ReducedDaysCard.tsx` (new) | CRUD list on the settings page |
| `frontend/src/pages/admin/Settings.tsx`, `pages/AbsenceCalendarPage.tsx`, `pages/Dashboard.tsx` | Mode UI, calendar colour, stamp-card line |

---

### Task 1: Migration 074, model, RLS and purge tests

**Files:**
- Create: `backend/alembic/versions/2026_11_03_1200-074_reduced_days.py`
- Create: `backend/app/models/reduced_day.py`
- Modify: `backend/app/models/__init__.py:18` (import + `__all__` entry `"ReducedDay"`)
- Create: `backend/tests/test_074_reduced_days_pg.py`
- Modify: `backend/tests/test_tenant_rls.py` (seed rows + new class), `backend/tests/test_purge_user_postgres.py`
- Modify: `scripts/local-ci.sh:81-88` (step 1 `--ignore`) and `:120-126` (step 2 list; update the reference-count comment above it). Modify `.github/workflows/cross-tenant-ci.yml:69-79` (SQLite `--ignore`) and `:116-121` (PG list).

**Interfaces:**
- Produces: `app.models.ReducedDay` with columns `id`, `tenant_id`, `date`, `label`, `max_hours` (Numeric(4,2)), `created_at`, `created_by`. Constraint name `uq_reduced_days_tenant_date`. Migration revision `"074_reduced_days"`.

- [ ] **Step 1: Write the failing PG migration test** `backend/tests/test_074_reduced_days_pg.py`. Copy the module skip, `_alembic`, `_md5` and `_scratch_database` pattern from `test_073_migration_pg.py:36-108`.

```python
def test_074_round_trip_keeps_existing_tables(scratch):
    url, engine = scratch
    _alembic(url, "upgrade", "073_work_blocks")
    # seed one absence + one system_setting in the default tenant, then snapshot
    before = {t: _md5(conn, f"SELECT * FROM {t}") for t in ("absences", "system_settings", "company_closures")}
    _alembic(url, "upgrade", "074_reduced_days")
    # table + constraint + RLS
    assert conn.execute(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname='reduced_days'")).scalar() is True
    assert conn.execute(text("SELECT count(*) FROM pg_policies WHERE tablename='reduced_days' AND policyname='tenant_isolation'")).scalar() == 1
    assert "uq_reduced_days_tenant_date" in {r[0] for r in conn.execute(text("SELECT conname FROM pg_constraint WHERE conrelid='reduced_days'::regclass"))}
    # numeric(4,2), label varchar(100), created_by ON DELETE SET NULL (confdeltype = 'n')
    _alembic(url, "downgrade", "073_work_blocks")
    assert conn.execute(text("SELECT to_regclass('reduced_days')")).scalar() is None
    _alembic(url, "upgrade", "074_reduced_days")
    after = {...same...}
    assert after == before
```

- [ ] **Step 2: Add RLS and purge tests.**
  - In `test_tenant_rls.py`, `seed_data` (`:82`) inserts one `reduced_days` row per tenant (2026-02-16, labels `rls_rd_a` / `rls_rd_b`). Add `DELETE FROM reduced_days WHERE tenant_id IN (:a, :b)` to **both** the pre-cleanup (`:92-98`) and the teardown (`:212-235`), before the `users`/`tenants` deletes. New class `TestReducedDaysIsolation` with:
    - `test_tenant_a_sees_only_own_reduced_days`: tenant A sees `rls_rd_a` and not `rls_rd_b`.
    - `test_tenant_a_cannot_insert_reduced_day_for_tenant_b`: the INSERT with `tenant_id = TENANT_B_ID` raises `ProgrammingError`/`DBAPIError` from the `WITH CHECK` policy.
  - In `test_purge_user_postgres.py`:
    - add `("reduced_days", "created_by")` to `SEEDED_USER_FK_COLUMNS` (`:116`). Without it, `TestFremdschluesselInventar::test_vorrichtung_deckt_alle_verweise_auf_nutzer_ab` goes red as soon as the model exists.
    - in the `welt` fixture, add one `ReducedDay(tenant_id=TENANT_ID, date=LONG_AGO, label="x", max_hours=Decimal("4"), created_by=VICTIM_ID)`.
    - in `TestEndloeschung`, add `test_verkuerzter_tag_bleibt_ohne_ersteller`: after the purge the row still exists and `created_by IS NULL`.
    - `test_modell_und_datenbank_nennen_dieselbe_loeschregel` then also checks that the model's `ondelete="SET NULL"` matches the migration (`confdeltype = 'n'`).

- [ ] **Step 3: Run the tests and confirm they fail.**
  Run: the PG command from Global Constraints with `tests/test_074_reduced_days_pg.py tests/test_tenant_rls.py::TestReducedDaysIsolation`
  Expected: FAIL. The alembic error is "Can't locate revision identified by '074_reduced_days'"; the RLS test fails with "relation reduced_days does not exist".

- [ ] **Step 4: Implement the migration and the model.**
  - Write the migration like `071_security_events` (`op.create_table`, index `ix_reduced_days_tenant_id`, RLS block, downgrade drops the policy, index and table).
  - Write the model with `__table_args__ = (UniqueConstraint("tenant_id", "date", name="uq_reduced_days_tenant_date"),)` and `created_by = Column(UUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)`. Model and migration must name the same delete rule, or the purge drift test fails.
  - `purge_user` needs no change because the FK is `SET NULL` (spec B2).

- [ ] **Step 5: Wire the new PG file into both pipelines.**
  - Add `--ignore=tests/test_074_reduced_days_pg.py` to the SQLite steps of `local-ci.sh` and `cross-tenant-ci.yml`.
  - Add `tests/test_074_reduced_days_pg.py` to both PG lists.
  - Update the reference-count comment in `local-ci.sh` (`:110-117`): 83 → 87 tests (+1 migration-074, +2 RLS, +1 purge), and „Same nine files“ → „Same ten files“.

- [ ] **Step 6: Run the tests and confirm they pass.**
  Run: the PG command with `tests/test_074_reduced_days_pg.py tests/test_tenant_rls.py tests/test_purge_user_postgres.py`
  Expected: all pass. Also run `PYT tests/test_special_days.py`. Expected: PASS, which shows that `create_all` on SQLite still works with the new model.

- [ ] **Step 7: Commit.**

```bash
git add backend/alembic/versions/2026_11_03_1200-074_reduced_days.py backend/app/models/reduced_day.py backend/app/models/__init__.py backend/tests/test_074_reduced_days_pg.py backend/tests/test_tenant_rls.py backend/tests/test_purge_user_postgres.py scripts/local-ci.sh .github/workflows/cross-tenant-ci.yml
git commit -F - <<'EOF'
feat(reduced-days): migration 074 adds the reduced_days table with RLS

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `special_days_service` — mode `max_hours`, reduced days in the config, one target helper, state diffs

**Files:**
- Modify: `backend/app/services/special_days_service.py` (whole module; module docstring updated to four modes + reduced days)
- Modify: `backend/app/routers/admin_settings.py:200-277` (switch the two callers to the state API, no behaviour change)
- Test: `backend/tests/test_reduced_days_config.py` (new)

**Interfaces:**
- Consumes: `ReducedDay` (Task 1).
- Produces, all in `special_days_service`:
  - `MODE_MAX_HOURS = "max_hours"`; `VALID_MODES` now includes it.
  - `MAX_HOURS_KEYS = {"special_day_dec24_max_hours", "special_day_dec31_max_hours"}`, part of `SETTING_KEYS`.
  - `DEFAULT_MAX_HOURS = Decimal("4")`, `MIN_MAX_HOURS = Decimal("0.25")`, `MAX_MAX_HOURS = Decimal("12")`.
  - `MAX_HOURS_ERROR = "Die Stundenzahl muss zwischen 0,25 und 12 liegen (in Schritten von 0,25)."`
  - `parse_max_hours(value) -> Decimal`: returns the value quantized to 0.01; raises `ValueError(MAX_HOURS_ERROR)` outside 0.25–12, off the 0.25 step, or when the value is not a number.
  - `get_special_day_settings(db, tenant_id) -> dict`: the existing four keys plus `special_day_dec24_max_hours` and `special_day_dec31_max_hours` as `float` (default 4.0; an invalid stored value also gives 4.0).
  - `get_special_day_config(db, tenant_id, year) -> Dict[date, dict]`: each entry is `{"mode", "counts_as_vacation", "max_hours": Optional[Decimal], "label": str}`.
    - Label for 24./31.12. is „Heiligabend“ / „Silvester“.
    - `max_hours` is set only when the mode is `max_hours`.
    - Every `ReducedDay` of the tenant in `year` is added as `mode="max_hours", counts_as_vacation=False`, with its own `max_hours` and `label`.
    - A settings entry on 24./31.12. wins over a stray row.
    - Two queries per call (settings + reduced days), both tenant-filtered.
  - `special_day_mode(d, cfg) -> Optional[str]`: the mode, or None when no entry exists.
  - `special_day_target(d: date, daily_target: Decimal, cfg: dict) -> Decimal`: `half_day` gives × 0.5, `free` gives 0, `max_hours` gives `min(daily_target, X)`, otherwise `daily_target`.
  - `configs_for_years(db, tenant_id, years) -> Dict[int, dict]`: one `get_special_day_config` per distinct year.
  - `format_hours_de(h: Decimal) -> str`: e.g. „4“, „4,5“, „4,25“.
  - `reduced_day_label(max_hours: Decimal) -> str`: returns `f"verkürzter Tag (max. {format_hours_de(max_hours)} h)"`.
  - `DayState = Tuple[str, Optional[bool], Optional[Decimal]]` = (mode, counts_as_vacation, max_hours). Like today's `_effective_state`, `counts_as_vacation` is set only for `free` and `max_hours` only for `max_hours`; both are `None` otherwise. That way an hours change while the mode is `working_day` is no change.
  - `setting_states(settings: dict, years) -> Dict[date, DayState]`.
  - `reduced_day_states(rows: Iterable[Tuple[date, Decimal]]) -> Dict[date, DayState]`.
  - `changed_dates(before, after) -> Set[date]`: union of the keys; a missing key counts as `("working_day", None, None)`.
  - `free_state_changed_dates(before_states, after_states) -> Set[date]`.
  - `years_affected_by_change(db, tenant_id, before_states, after_states) -> List[int]`: keeps only changed weekday dates without a holiday.
  - `special_day_target_factor` stays for `half_day`/`free` and returns `None` for `max_hours`. Only this module may call it (guard test in Task 3).

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_reduced_days_config.py`. In 2026, 24.12. and 31.12. are Thursdays, 16.02. is a Monday.

```python
@pytest.mark.parametrize("raw, ok", [("0.25", Decimal("0.25")), ("12", Decimal("12.00")), ("4,5", None), ("0.2", None), ("12.25", None), ("4.3", None), ("abc", None)])
def test_parse_max_hours(raw, ok): ...  # ok None → pytest.raises(ValueError, match="zwischen 0,25 und 12")

# helpers: _set_setting(db, key, value) and _set_special_day(db, prefix, mode) from test_special_days.py:34/39 (import or copy)

def test_config_includes_reduced_day(db, test_user):
    db.add(ReducedDay(tenant_id=DEFAULT_TENANT_ID, date=date(2026, 2, 16), label="Rosenmontag", max_hours=Decimal("4"))); db.commit()
    cfg = special_days_service.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    assert cfg[date(2026, 2, 16)] == {"mode": "max_hours", "counts_as_vacation": False, "max_hours": Decimal("4.00"), "label": "Rosenmontag"}
    assert date(2027, 2, 16) not in special_days_service.get_special_day_config(db, DEFAULT_TENANT_ID, 2027)

def test_config_ignores_other_tenant_reduced_day(db, test_user): ...  # row with a second tenant id → absent

def test_setting_max_hours_resolves(db, test_user):
    _set_setting(db, "special_day_dec24_mode", "max_hours"); _set_setting(db, "special_day_dec24_max_hours", "3.5")
    assert cfg[date(2026, 12, 24)]["max_hours"] == Decimal("3.50")

def test_mode_max_hours_without_hours_falls_back_to_4(db, test_user):   # Review Focus 5
    _set_setting(db, "special_day_dec24_mode", "max_hours")
    assert cfg[date(2026, 12, 24)]["max_hours"] == Decimal("4")
    assert special_days_service.get_special_day_settings(db, DEFAULT_TENANT_ID)["special_day_dec24_max_hours"] == 4.0

@pytest.mark.parametrize("mode, target, expected", [("max_hours", "8", "4"), ("max_hours", "3", "3"), ("max_hours", "0", "0"), ("half_day", "8", "4"), ("free", "8", "0"), ("working_day", "8", "8")])
def test_special_day_target(mode, target, expected): ...

def test_reduced_day_label():
    assert special_days_service.reduced_day_label(Decimal("4")) == "verkürzter Tag (max. 4 h)"
    assert special_days_service.reduced_day_label(Decimal("4.50")) == "verkürzter Tag (max. 4,5 h)"
    assert special_days_service.reduced_day_label(Decimal("4.25")) == "verkürzter Tag (max. 4,25 h)"

def test_changed_dates_compares_date_sets():
    before = special_days_service.reduced_day_states([(date(2026, 2, 16), Decimal("4"))])
    after = special_days_service.reduced_day_states([(date(2026, 2, 17), Decimal("4"))])
    assert special_days_service.changed_dates(before, after) == {date(2026, 2, 16), date(2026, 2, 17)}
    assert special_days_service.free_state_changed_dates(before, after) == set()

def test_years_affected_ignores_weekend_and_holiday(db, test_user): ...  # Sat 2026-02-14 and a holiday date → []
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `PYT tests/test_reduced_days_config.py`
  Expected: FAIL with `AttributeError: ... has no attribute 'parse_max_hours'`.

- [ ] **Step 3: Implement the interfaces above.** Then switch `admin_settings.update_setting` to the state API with identical behaviour:
  - `affected = years_affected_by_change(db, tid, setting_states(special_before, closed), setting_states(special_after, closed))`, where `closed = all_closed_years(...)`.
  - The clamp hint uses `free_state_changed_dates(setting_states(before, entry_years), setting_states(after, entry_years))`.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `PYT tests/test_reduced_days_config.py tests/test_special_days.py`
  Expected: all pass. This includes `test_router_special_day_*` and the unchanged `test_config_resolves_defaults` / `test_half_day_factor`.

- [ ] **Step 5: Commit.** Message: `feat(special-days): max_hours mode and reduced days in the special-day config`.

---

### Task 3: Soll sites through `special_day_target`, fixed mode, presence target

**Files:**
- Modify: `backend/app/services/calculation_service.py`:
  - `_day_soll_contribution` (`:1527-1529`)
  - `get_gross_monthly_target` (`:1979-1981`)
  - `_fixed_planned_hours` (`:1118-1132`)
  - `future_freizeitausgleich_impact` needs **no** change: it only reads OVERTIME up to `date(today.year, 12, 31)` (`:1652-1662`), so its single cfg for `today.year` (`:1677`) is always the right year. It gets the cap through `_day_soll_contribution` and `_fixed_planned_hours`; a test pins that.
- Test: `backend/tests/test_reduced_days_soll.py` (new), `backend/tests/test_no_special_factor_inline.py` (new guard)

**Interfaces:**
- Consumes: `special_days_service.special_day_target`, `special_day_mode`, `MODE_MAX_HOURS` (Task 2).
- Produces: unchanged signatures. `get_monthly_target`, `get_range_target`, `get_week_summary`, `get_overtime_account`, `get_ytd_summary`, `get_day_presence_target` and `get_gross_monthly_target` honour `max_hours`.

- [ ] **Step 1: Write the failing tests.** Fixtures: `test_user` (8 h daily); `user_3h` (`weekly_hours=15`, `work_days_per_week=5`); `day_plan_user` (Mon 8 / Tue 5 / Wed 4, no Thursday). Helper `_reduce(db, d, hours)` sets 24.12. to `max_hours`, or adds a `ReducedDay` for other dates.

```python
D24 = date(2026, 12, 24)        # Thursday
RM = date(2026, 2, 16)           # Monday, custom reduced day

def _day_soll(db, user, d): return calculation_service.get_range_target(db, user, d, d)

def test_dec24_max_hours_caps_8h_person(db, test_user):          _reduce(db, D24, "4"); assert _day_soll(db, test_user, D24) == Decimal("4")
def test_dec24_max_hours_keeps_3h_person(db, user_3h):           _reduce(db, D24, "4"); assert _day_soll(db, user_3h, D24) == Decimal("3")
def test_dec24_max_hours_person_without_thursday(db, day_plan_user): _reduce(db, D24, "4"); assert _day_soll(db, day_plan_user, D24) == Decimal("0")
TH = date(2026, 2, 19)           # Thursday, custom reduced day (spec B5: "Eigenes Datum: gleiche Fälle")
def test_custom_day_caps_8h_person(db, test_user):              _reduce(db, TH, "4"); assert _day_soll(db, test_user, TH) == Decimal("4")
def test_custom_day_keeps_3h_person(db, user_3h):               _reduce(db, TH, "4"); assert _day_soll(db, user_3h, TH) == Decimal("3")
def test_custom_day_person_without_thursday(db, day_plan_user): _reduce(db, TH, "4"); assert _day_soll(db, day_plan_user, TH) == Decimal("0")
def test_custom_day_caps_and_holiday_wins(db, test_user):
    _reduce(db, RM, "4"); assert _day_soll(db, test_user, RM) == Decimal("4")
    db.add(PublicHoliday(tenant_id=DEFAULT_TENANT_ID, date=RM, name="X", year=2026, is_custom=True, source="admin")); db.commit()
    assert _day_soll(db, test_user, RM) == Decimal("0")
def test_custom_day_on_weekend_no_effect(db, test_user): ...      # Sat 2026-02-14 → 0, month target unchanged
def test_worked_6h_gives_plus_2(db, test_user):                   # 6 h stamped on D24 → get_monthly_actual - get_monthly_target delta for the day = +2
def test_half_day_absence_on_reduced_day(db, test_user):          # half_day VACATION on D24 → day soll = min(8,4) × 0.5 = 2
def test_gross_monthly_target_uses_cap(db, test_user):            # get_gross_monthly_target(Dec) == plain target − 4
def test_presence_target_shows_cap(db, test_user):                # get_day_presence_target(db, test_user, D24) == Decimal("4.00")
def test_fixed_mode_month_target_unchanged(db, fixed_user):       # use_fixed_monthly_target: get_monthly_target(Dec) identical with/without _reduce
def test_fixed_planned_hours_min_not_half(db, fixed_user_3h_thursday):
    _reduce(db, D24, "4"); cfg = special_days_service.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    assert calculation_service._fixed_planned_hours(db, fixed_user_3h_thursday, D24, cfg) == Decimal("3")   # not 1.5
    # and an 8h-thursday fixed user → Decimal("4")
def test_future_freizeitausgleich_on_reduced_day(db, test_user):
    # OVERTIME hours=8 on D24 (max 4): future_freizeitausgleich_impact(db, test_user, cutoff_date=date(2026, 11, 2), today=date(2026, 11, 3)) == Decimal("4.00")
```

  `backend/tests/test_no_special_factor_inline.py` is a source scan of `app/`. It asserts that `special_day_target_factor(` occurs only in `app/services/special_days_service.py`. The pattern is `test_no_live_work_blocks_read.py`.

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `PYT tests/test_reduced_days_soll.py tests/test_no_special_factor_inline.py`
  Expected: FAIL. The cap tests return 8, and the guard lists `calculation_service.py`, the exports, `journal_service.py` and `company_closures.py`. The guard stays red until Task 6. Mark it `xfail(strict=True)` here and remove the marker in Task 6.

- [ ] **Step 3: Implement.**
  - `_day_soll_contribution` and `get_gross_monthly_target`: `daily_target = special_days_service.special_day_target(d, daily_target, cfg)`.
  - `_fixed_planned_hours`: if `special_day_mode(d, cfg) == MODE_MAX_HOURS`, return `min(planned, cfg[d]["max_hours"])`; otherwise keep `planned * half_special_day_weight(d, cfg)` unchanged. The `max_hours` branch must come first, because Task 4 makes `half_special_day_weight` return 0.5 for `max_hours`.
  - Update the docstrings of `_day_soll_contribution` and `get_day_presence_target` („#146-Sondertagsfaktor 24./31.12.“ → `special_day_target`, including reduced days).

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `PYT tests/test_reduced_days_soll.py tests/test_special_days.py tests/test_fix1_half_day_target.py tests/test_494_clock_status_today.py`
  Expected: PASS. The guard test reports `xfail`.

- [ ] **Step 5: Commit.** Message: `feat(reduced-days): daily target min(target, X) at every Soll site`.

---

### Task 4: Target-aware credit, 0.5 vacation cost, date pre-filters

**Files:**
- Modify: `backend/app/services/calculation_service.py`:
  - `credit_day_weight` (`:1318-1375`) and `credited_absence_hours` (`:1378-1400`)
  - `_credited_day_context` (`:1425`)
  - `half_special_day_weight` (`:2786-2799`)
  - pre-filters at `:691-694` (`retarget_absence_hours`) and `:889-893` (`f1_clamp_for_day`)
  - credit call sites `:772`, `:893`, `:1883`, `:2242`, `:2480`, `:2764`
- Modify: `backend/app/routers/absences.py:739-742` (pre-filter) and `:785-786` (pass `daily_target=full_target`)
- Test: `backend/tests/test_reduced_days_credit_vacation.py` (new)

**Interfaces:**
- Produces:
  - `credit_day_weight(d: date, holiday_dates: set, special_cfg: Optional[dict] = None, *, daily_target: Optional[Decimal] = None) -> Decimal`
    - weekend or holiday gives 0
    - `half_day` gives 0.5, `free` gives 0
    - `max_hours` gives `min(t, X) / t` with `t = Decimal(str(daily_target))`, and 0 when t ≤ 0
    - on a `max_hours` day with `daily_target is None`, raise `ValueError("credit_day_weight: daily_target ist an einem verkürzten Tag Pflicht")` (an overlooked call site fails loudly in tests)
    - otherwise 1
  - `credited_absence_hours(day_absences, d, holiday_dates, special_cfg=None, *, daily_target: Optional[Decimal] = None) -> Decimal` (passes `daily_target` through).
  - `_credit_weight(db, user, d, holiday_dates, special_cfg, wh_changes=None) -> Decimal` (module-private). It resolves the **unweighted** snapshot target (`get_daily_target_for_date(user, d, get_schedule_for_date(db, user, d, wh_changes=wh_changes))`) only when `special_day_mode(d, special_cfg) == MODE_MAX_HOURS`, then calls `credit_day_weight`. It is used at `:1883`, `:2242`, `:2480`, `:2764`.
  - `half_special_day_weight(d, special_cfg) -> Decimal`: returns 0.5 for `half_day` **and** `max_hours`.
  - Both `credit_day_weight` and `half_special_day_weight` decide by `special_days_service.special_day_mode(d, cfg)` and no longer call `special_day_target_factor` (the guard from Task 3 needs `calculation_service.py` clean after this task).
  - The pre-filters `(d.month, d.day) in ((12, 24), (12, 31))` go away at all four places (`calculation_service.py:691-694`, `:889-892`, `:1425`; `absences.py:739-742`); load `special_days_service.configs_for_years(db, tid, {years})` instead (Review Focus 1). `_credited_day_context` still loads nothing when there is no TRAINING/SICK absence in the range.
  - Retarget passes `daily_target=target` and `f1_clamp_for_day` passes `daily_target=full_target`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_reduced_days_credit_vacation.py`.

```python
def test_credit_weight_max_hours():
    cfg = {D24: {"mode": "max_hours", "counts_as_vacation": False, "max_hours": Decimal("4"), "label": "Heiligabend"}}
    assert calculation_service.credit_day_weight(D24, set(), cfg, daily_target=Decimal("8")) == Decimal("0.5")
    assert calculation_service.credit_day_weight(D24, set(), cfg, daily_target=Decimal("3")) == Decimal("1")
    assert calculation_service.credit_day_weight(D24, set(), cfg, daily_target=Decimal("0")) == Decimal("0")
    with pytest.raises(ValueError, match="daily_target"):
        calculation_service.credit_day_weight(D24, set(), cfg)
    assert (Decimal("7") * calculation_service.credit_day_weight(D24, set(), cfg, daily_target=Decimal("7"))).quantize(Decimal("0.01")) == Decimal("4.00")

def test_sick_on_reduced_day_saldo_neutral(db, test_user):     # SICK hours=8 on D24 (max 4): monthly actual − target delta for the day == 0; overtime account, ytd and history agree
def test_sick_on_custom_day_credited_reduced(db, test_user):    # Review Focus 1: RM custom day, SICK hours=8: get_range_actual(RM, RM) == Decimal("4"); get_overtime_account delta for RM == 0
def test_mixed_day_custom_date_f1_uses_reduced_weight(db, test_user, test_admin):   # Review Focus 1
    # 2 h stamped on RM (max 4), POST /api/absences type=sick keep_time_entries=True → stored hours == 4.0 (= (8×0.5 − 2) ÷ 0.5), not 6.0
def test_vacation_costs_half_day(db, test_user):                # VACATION on D24 → get_vacation_account(...)["used_days"] == 0.5; absence_days([...]) == Decimal("0.5")
def test_vacation_costs_half_day_for_3h_person(db, user_3h):     # also 0.5
def test_mixed_day_sick_keep_entries_no_500(db, test_user, test_admin):   # Review Focus 4; own FastAPI app with absences.router, get_current_user → test_admin
    # 2 h stamped on D24 (max 4), POST /api/absences type=sick keep_time_entries=True → 201 (not 500); stored hours == 4.0, credit = get_range_actual(D24, D24) − 2 == Decimal("2") (Ist 2 + 2 = Soll 4)
def test_retarget_on_reduced_day_no_error(db, test_user):       # SICK hours=8, half_day=False on D24 (max 4) + kept 1 h entry; calculation_service.retarget_absence_hours(db, test_user, D24, D24, old_full_target_by_date={D24: Decimal("8")}) → no ValueError; new hours == 6.0 (t=8, w=0.5: (8×0.5 − 1) ÷ 0.5), credit 3 + Ist 1 = Soll 4
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `PYT tests/test_reduced_days_credit_vacation.py`
  Expected: FAIL. `credit_day_weight` rejects the `daily_target` keyword (TypeError), and `used_days == 1.0`.

- [ ] **Step 3: Implement the interfaces above.** Rewrite the docstrings of `credit_day_weight` and `half_special_day_weight`: the old claim that the cfg only holds 24./31.12. is no longer true.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `PYT tests/test_reduced_days_credit_vacation.py tests/test_audit_20260731_feiertag_krank.py tests/test_special_days.py tests/test_vacation_half_day.py tests/test_credit_override.py tests/test_retarget_f1.py tests/test_absence_keep_time_entries_balance.py`
  Expected: PASS.

- [ ] **Step 5: Commit.** Message: `feat(reduced-days): credit follows the reduced target, vacation costs 0.5`.

---

### Task 5: Booking paths — closures book the reduced target, daily-target endpoint, budget checks

**Files:**
- Modify: `backend/app/routers/company_closures.py:238-247` (comment) and `:367-377` (booking)
- Modify: `backend/app/routers/absences.py:83-90` (`get_daily_target_for_date_endpoint`)
- Test: `backend/tests/test_reduced_days_booking.py` (new)

**Interfaces:**
- Consumes: `special_day_target`, `special_day_mode`, `half_special_day_weight` (Tasks 2 and 4).
- Produces: in `_create_closure_absences`:
  - skip when `special_day_mode(...) == MODE_FREE`
  - `booked_target = special_day_target(workday, day_target, cfg)`
  - `day_consumption = float(calculation_service.half_special_day_weight(workday, cfg))`
  - `half_day=False`
  - `GET /api/absences/daily-target?date=` returns `hours = special_day_target(d, daily, cfg)`.

- [ ] **Step 1: Write the failing tests.** Each test uses its own FastAPI app with the needed routers, like `test_company_closure_edit.py:45`. D24 is max 4 h, and the test user's budget is 30.

```python
def test_create_absence_vacation_costs_half(db, test_user, ...):      # POST /api/absences vacation D24 → hours 8.0 stored, used_days 0.5
def test_vacation_request_approval_costs_half(db, ...):                # POST /api/vacation-requests D24 + POST /api/admin/vacation-requests/{id}/review approve → used_days 0.5
def test_change_request_vacation_costs_half(db, ...):                  # entry_kind="absence" CR CREATE on D24 approved → used_days 0.5
def test_budget_check_counts_half(db, test_user, ...):                 # remaining 0.5 → vacation on D24 accepted (201); on 23.12. rejected (400)
def test_request_day_count_half(db, ...):                              # GET /api/admin/vacation-requests: a D24-only request has "days" == 0.5 (admin_helpers._enrich_vr_responses → request_day_count)
def test_closure_books_reduced_target(db, ...):                        # POST /api/company-closures 21.–31.12.2026: D24 row hours 4.0, half_day False; 3h-person D24 hours 3.0; consumption via get_vacation_account: D24 counts 0.5
def test_closure_split_consistent(db, ...):                            # closure_overtime_after_vacation=true, closure 23.–24.12.2026, remaining budget 1.5 days → 23.12. VACATION (1.0), D24 VACATION (0.5), remaining_days == 0; budget 1.0 → 23.12. VACATION, D24 OVERTIME; a re-save (PUT unchanged) yields the identical (date, type, hours) set
def test_daily_target_endpoint_reduced(db, test_user, ...):            # GET /api/absences/daily-target?date=2026-12-24 → {"hours": 4.0}; 2026-12-23 → 8.0
```


- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `PYT tests/test_reduced_days_booking.py`
  Expected: FAIL. Closure `hours` is 8.0 and the endpoint returns 8.0. The vacation-cost tests may already pass after Task 4; that is expected, and they pin the regression.

- [ ] **Step 3: Implement the interfaces above.**

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `PYT tests/test_reduced_days_booking.py tests/test_closure_overtime_split.py tests/test_company_closure_edit.py tests/test_round2_fixes.py tests/test_ultrareview_absence_candidates.py`
  Expected: PASS.

- [ ] **Step 5: Commit.** Message: `feat(reduced-days): closures book the reduced target, daily-target endpoint applies it`.

---

### Task 6: Exports and journal through the helper (parity)

**Files:**
- Modify: `backend/app/services/export_service.py`:
  - XLSX month `:821-828` and `:897`
  - XLSX yearly employee sheet `:1458` and `:1526`
  - PDF month `:2244` and `:2294`
- Modify: `backend/app/services/ods_export_service.py` month `:312` + `:343` and year `:682` + `:699`. In the month sheet the credit at `:312` comes before the factor at `:343`; reorder so that the raw target exists first.
- Modify: `backend/app/services/journal_service.py` `_eff_daily_target` (`:125-133`) and credit `:225`. `_eff_daily_target` returns the weighted target, so the credit needs the raw snapshot target of the day next to it (e.g. a small `_raw_daily_target(d)`), not the result of `_eff_daily_target`.
- Modify: `backend/tests/test_no_special_factor_inline.py` (remove `xfail`)
- Test: `backend/tests/test_reduced_days_exports.py` (new)

**Interfaces:**
- Consumes: `special_day_target`, and `credited_absence_hours(..., daily_target=raw)` (Task 4).
- Produces: at every site, `raw = get_daily_target_for_date(...)` and `daily_target = special_day_target(d, raw, cfg)`. Credits pass `daily_target=raw`, the unweighted value.

- [ ] **Step 1: Write the failing tests.** December 2026, D24 max 4 h, custom day 28.12. (Monday) max 6 h. Contents: one SICK on D24, 6 h stamped on 28.12., one VACATION on 23.12. Reuse `_xlsx_summary` from `test_audit_20260731_export_ist.py:95`, `_xlsx_employee_sheet` / `_xlsx_day_rows` / `_ods_table` / `_ods_day_rows` from `test_497_498_export_day_rows.py:102-142`, and the reportlab `Table` spy pattern from `test_498_pdf_layout.py`.

```python
def test_xlsx_monthly_day_soll_and_summary(db, dec_month):      # column 7 on D24 == 4.0, on 28.12. == 6.0; "Soll-Stunden Monat:" == get_monthly_target; "Ist-Stunden Monat:" == get_monthly_actual; Σ day "Differenz" == "Saldo Monat:"
def test_xlsx_yearly_employee_sheet_parity(db, dec_month):      # "Soll-Stunden Jahr:" == Σ get_monthly_target(2026, m)
def test_ods_monthly_parity(db, dec_month):                     # same three summary values as XLSX
def test_ods_yearly_employee_day_soll(db, dec_month):           # D24 soll cell 4.0
def test_pdf_monthly_builds_on_reduced_day(db, dec_month):      # monkeypatch reportlab.platypus.Table spy: D24 row soll cell text "4.00" (the PDF formats f"{float(target):.2f}", export_service.py:2314); PDF starts b"%PDF"
def test_journal_day_rows_and_summary(db, dec_month):           # journal_service month: D24 target_hours 4.0, SICK credit 4.0, monthly_summary == get_monthly_target/actual
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `PYT tests/test_reduced_days_exports.py tests/test_no_special_factor_inline.py`
  Expected: FAIL. The day soll is 8.0, and the credit call raises `ValueError` on D24. The guard is still `xfail`; remove the marker in Step 3.

- [ ] **Step 3: Implement** the replacements at every site listed above, and remove the `xfail`.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `PYT tests/test_reduced_days_exports.py tests/test_no_special_factor_inline.py tests/test_audit_20260731_export_ist.py tests/test_497_498_export_day_rows.py tests/test_special_days.py tests/test_ods_export_service.py`
  Expected: PASS.

- [ ] **Step 5: Commit.** Message: `feat(reduced-days): exports and journal use special_day_target`.

---

### Task 7: Reduced-days admin router with automatic closure re-save

**Files:**
- Modify: `backend/app/routers/company_closures.py` (add `closure_years` and `resave_closures_for_dates` next to `_create_closure_absences` `:188`; `update_closure` `:603-893` stays as it is)
- Create: `backend/app/schemas/reduced_day.py`, `backend/app/routers/reduced_days.py`
- Modify: `backend/app/main.py:575` (`app.include_router(reduced_days.router)` + import)
- Test: `backend/tests/test_reduced_days_router.py` (new); `backend/tests/test_cross_tenant_api.py` (two tests)

**Interfaces:**
- Produces in `company_closures.py`:
  - `CLOSURE_REBOOK_REASON = "Sondertag oder verkürzter Tag geändert, wird neu gebucht"`.
  - `closure_years(db, tenant_id) -> Set[int]`: the years covered by any closure of the tenant (F-026).
  - `resave_closures_for_dates(db, current_user, dates: Set[date]) -> Optional[str]`. It follows `closure_split_service.rebook_freed_closure_days` (`:267-357`), not `update_closure`:
    1. Drop dates in `calculation_service.all_closed_years(db, tid)` (Fix #5: those years only warn). If nothing is left, return `None` without another query.
    2. Load the tenant's closures that overlap `[min, max]` of the remaining dates and contain at least one of them (F-026). None → return `None`.
    3. Participants = active users with `receives_company_closures` (the `update_closure` set, `:690-695`). Load the linked rows of all these closures on the remaining dates. Call `_lock_participant_rows(db, tid, participants ∪ linked user ids ∪ {current_user.id})` **once, before the first delete** (`_lock_participant_rows` docstring: lock first, then write).
    4. Per closure: remember `_closure_booking_state` (before). Delete its linked rows on the remaining dates where the user is a participant and has no time entry on that date (#290, as `_worked_keys` in `update_closure` `:734-743`). Rows of former or deselected participants and rows on worked days stay. Write one `_audit_closure_absence_deletion(..., CLOSURE_REBOOK_REASON)` per closure, then `db.flush()`.
    5. Re-book with `_create_closure_absences(db, closure, workdays, participants, current_user, delete_time_entries=False)`, where `workdays` = remaining dates inside the closure minus weekends, holidays and `free` special days (`_get_workdays` + `free_special_days_in_range`, as `rebook_freed_closure_days` `:321-328`). A day that became `free` is therefore deleted and not booked again.
    6. If `closure.counts_as_vacation` and `closure_overtime_after_vacation` is on: `db.flush()`, then `_resplit_year_closures(db, tid, yr, current_user)` for every year of the remaining dates (as `update_closure` `:573`).
    7. Warning = `join_warnings` of `_closed_year_warning_for_changes(before, after)` over all closures. It never commits.
- Why not reuse `update_closure`: extracting its 290-line body would put every closure regression at risk for a feature that only needs a date-scoped re-booking. `update_closure` keeps its own behaviour; the existing closure suites prove it is untouched.
- Produces in `schemas/reduced_day.py`:
  - `ReducedDayCreate {date: date, label: constr(strip, 1..100), max_hours: Decimal}`, where a validator calls `parse_max_hours` → 422 with `MAX_HOURS_ERROR`.
  - `ReducedDayUpdate`: the same three fields (full replacement).
  - `ReducedDayResponse {id: str, date: date, label: str, max_hours: float, created_at: datetime, warning: Optional[str] = None}`.
- Produces in `routers/reduced_days.py`: `router = APIRouter(prefix="/api/admin/reduced-days", tags=["admin"], dependencies=[Depends(require_admin)])` with these endpoints:
  - `GET /?year=` → `List[ReducedDayResponse]`, sorted by date, tenant-filtered.
  - `POST /` → 201.
  - `PUT /{id}` → 200.
  - `DELETE /{id}` → 204, or 200 with `{"warning": …}` like `holidays.delete_holiday`.
  - Rules:
    - 24.12./31.12. (POST and PUT) → 400 „Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden.“
    - duplicate (pre-check + `IntegrityError` on `uq_reduced_days_tenant_date`) → 409 „Für dieses Datum ist bereits ein verkürzter Tag eingetragen.“
    - unknown or foreign id → 404 „Verkürzter Tag nicht gefunden“
  - Every write computes `before`/`after` with `reduced_day_states` and `changed = changed_dates(before, after)`. A label-only PUT gives an empty `changed`.
  - Warning = `join_warnings(stale_year_closing_warning(db, tid, years_affected_by_change(db, tid, before, after)), resave_closures_for_dates(db, current_user, changed))`.
  - Order: write the row, `db.flush()` (so `get_special_day_config` sees it), then `resave_closures_for_dates`, then one `db.commit()` at the end. The row and the closure re-save are in the same transaction. `created_by = current_user.id`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_create_list_update_delete(client, db):                 # POST {"date":"2026-02-16","label":"Rosenmontag","max_hours":4} → 201, max_hours 4.0; GET ?year=2026 lists it; PUT max 5 → 200; DELETE → 204
@pytest.mark.parametrize("d", ["2026-12-24", "2026-12-31"])
def test_dec24_dec31_rejected(client, d):                       # 400, detail == "Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden."
def test_duplicate_409(client):                                 # detail == "Für dieses Datum ist bereits ein verkürzter Tag eingetragen."
@pytest.mark.parametrize("h", [0, 0.2, 12.25, 4.3])
def test_hours_validation_422(client, h): ...
@pytest.mark.parametrize("h", [0.25, 12])
def test_hours_bounds_accepted(client, h): ...
def test_foreign_tenant_404(client, db):                        # row of a second tenant → PUT/DELETE 404 "Verkürzter Tag nicht gefunden", GET does not list it
def test_create_resaves_existing_closure(client, db):           # closure 14.–20.02.2026 booked first (16.02. hours 8); POST RM max 4 → 16.02. row hours 4.0, used_days drops by 0.5; audit line with the re-book reason
def test_move_date_rebooks_both(client, db):                    # Review Focus 2: PUT date 16.02.→17.02. → 16.02. hours 8.0, 17.02. hours 4.0
def test_label_only_is_noop(client, db):                        # Review Focus 3: closure booking set identical, no new TimeEntryAuditLog, response warning None
def test_delete_restores_full_target(client, db):               # DELETE → 16.02. hours 8.0
def test_resave_respects_worked_day(client, db):                # time entry on 16.02. for the participant → no closure row is created there, nothing is deleted (#290)
def test_resave_keeps_rows_of_former_participants(client, db):  # participant set is_active=False after the closure was booked → POST RM → that user's 16.02. row unchanged (hours 8.0)
def test_resave_runs_314_split(client, db):                     # split toggle on: types after POST == resplit_year_closures result
def test_closed_year_warns_without_resave(client, db):          # YearCarryover(year=2026, source="year_closing") for 2025 + closure in Dec 2025 → POST 2025-12-29 max 4 → warning names 2025, closure rows unchanged
def test_atomic_on_resave_error(client, db, monkeypatch):       # closure over 16.02. exists; monkeypatch company_closures._create_closure_absences to raise RuntimeError; with pytest.raises(RuntimeError) (TestClient re-raises) POST RM; db.rollback(); no reduced_days row, closure rows unchanged
```

  In `test_cross_tenant_api.py`, add `test_reduced_days_list_excludes_tenant_b` and `test_admin_a_cannot_delete_tenant_b_reduced_day`.

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `PYT tests/test_reduced_days_router.py tests/test_cross_tenant_api.py`
  Expected: FAIL with 404 for the route (the router does not exist yet).

- [ ] **Step 3: Implement** `closure_years` and `resave_closures_for_dates`, then the schemas, the router and the registration. `update_closure` is not edited.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `PYT tests/test_reduced_days_router.py tests/test_cross_tenant_api.py tests/test_company_closure_edit.py tests/test_closure_overtime_split.py tests/test_overlapping_closures_user_create.py tests/test_issue_511_closure_refill.py tests/test_company_closure_paid_leave.py`
  Expected: PASS.

- [ ] **Step 5: Commit.** Message: `feat(reduced-days): admin CRUD with automatic closure re-save`.

---

### Task 8: Settings 24./31.12. — `max_hours` validation and closure re-save

**Files:**
- Modify: `backend/app/routers/admin_settings.py:174-191` (validation) and `:250-278` (re-save + warnings)
- Test: `backend/tests/test_reduced_days_settings.py` (new)

**Interfaces:**
- Consumes: `parse_max_hours`, `MAX_HOURS_KEYS`, `setting_states`, `changed_dates` (Task 2); `company_closures.resave_closures_for_dates`, `closure_years` (Task 7).
- Produces:
  - A PUT of a `MAX_HOURS_KEYS` key stores `str(parse_max_hours(value))`, e.g. "4.00"; an invalid value returns 400 with `MAX_HOURS_ERROR`.
  - After the flush of any special-day key: `changed = changed_dates(setting_states(before, cy), setting_states(after, cy))` with `cy = closure_years(...)`.
  - The warning becomes `join_warnings(<existing closed-year text>, <existing clamp hint>, resave_closures_for_dates(db, current_user, changed))`, followed by one commit.
  - A PUT that does not change the state (same value, or hours while the mode is not `max_hours`) gives an empty `changed`, so no re-save and no warning. The existing `test_router_special_day_same_value_no_warning` and `test_router_vacation_flag_only_warns_when_day_is_free` must stay green.

- [ ] **Step 1: Write the failing tests.** Use `_settings_client` from `test_special_days.py` plus the closures router.

```python
def test_put_max_hours_valid_and_readback(db, test_admin):       # PUT special_day_dec24_max_hours "3.5" → 200; GET special-days → 3.5
@pytest.mark.parametrize("v", ["0", "12.5", "4.1", "x"])
def test_put_max_hours_invalid(db, test_admin, v):               # 400, detail == "Die Stundenzahl muss zwischen 0,25 und 12 liegen (in Schritten von 0,25)."
def test_put_mode_max_hours_accepted(db, test_admin): ...
def test_mode_change_resaves_closure(db, test_admin):            # closure 21.–31.12.2026 booked (D24 hours 8) → PUT mode max_hours (hours 4) → D24 hours 4.0
def test_hours_change_resaves_closure(db, test_admin):           # then PUT max_hours "2" → D24 hours 2.0
def test_hours_change_while_mode_working_day_noop(db, test_admin):  # closure rows identical, no audit
def test_half_day_to_working_day_resaves(db, test_admin):        # half_day booked 4.0 → working_day → 8.0 (the same re-save covers the existing modes)
def test_closed_year_not_resaved(db, test_admin):                # 2025 closed: a Dec-2025 closure keeps its hours, warning names 2025
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `PYT tests/test_reduced_days_settings.py`
  Expected: FAIL. The hours stay at 8.0, and an invalid value is accepted.

- [ ] **Step 3: Implement the interfaces above.**

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `PYT tests/test_reduced_days_settings.py tests/test_special_days.py`
  Expected: PASS.

- [ ] **Step 5: Commit.** Message: `feat(special-days): 24./31.12. max_hours setting re-saves affected closures`.

---

### Task 9: Public payload and stamp-card label (backend)

**Files:**
- Modify: `backend/app/main.py:727-760` (`get_public_settings`)
- Modify: `backend/app/schemas/time_entry.py:210-240` (`ClockStatusResponse`)
- Modify: `backend/app/routers/time_entries.py:401-490` (`get_clock_status`, both `ClockStatusResponse(...)` returns at `:457` and `:476`)
- Test: `backend/tests/test_reduced_days_public.py` (new)

**Interfaces:**
- Produces:
  - `special_days_service.list_reduced_days_public(db, tenant_id) -> List[dict]`: `[{"date": "YYYY-MM-DD", "label": str, "max_hours": float}]`, sorted, tenant-filtered.
  - `/api/settings` → `special_days` = `{**get_special_day_settings(...), "reduced_days": list_reduced_days_public(...)}`. It still carries no licensee identity (F3).
  - `special_days_service.day_label(d, cfg) -> Optional[str]`: `reduced_day_label(X)` for a `max_hours` entry, otherwise None.
  - `ClockStatusResponse.today_special_day_label: Optional[str] = None`, filled with `day_label(today, cfg)` on a weekday without a tenant holiday, in every branch.

- [ ] **Step 1: Write the failing tests.**

```python
def test_public_settings_lists_reduced_days(db, test_user, monkeypatch):
    # monkeypatch app.main.SessionLocal → tests.conftest.TestingSessionLocal; app.database.set_superadmin_context → no-op (SQLite, CLAUDE.md)
    body = app.main.get_public_settings()
    assert body["special_days"]["reduced_days"] == [{"date": "2026-02-16", "label": "Rosenmontag", "max_hours": 4.0}]
    assert body["special_days"]["special_day_dec24_max_hours"] == 4.0
    assert set(body) <= {"vacation_approval_required", "break_exception_requires_approval", "special_days", "license"}
def test_clock_status_label_on_reduced_day(db, test_user, monkeypatch):   # _today_local → 2026-02-16 → today_special_day_label == "verkürzter Tag (max. 4 h)", today_target_hours == 4.0
def test_clock_status_label_none_on_normal_day(...): ...
def test_clock_status_label_none_on_holiday(...): ...
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `PYT tests/test_reduced_days_public.py`
  Expected: FAIL with `KeyError: 'reduced_days'`.

- [ ] **Step 3: Implement the interfaces above.**

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `PYT tests/test_reduced_days_public.py tests/test_494_clock_status_today.py tests/test_clock_status_blocks.py`
  Expected: PASS.

- [ ] **Step 5: Commit.** Message: `feat(reduced-days): public payload and stamp-card label`.

---

### Task 10: Frontend — date-based `getSpecialDayInfo`, calendar, stamp card

**Files:**
- Modify: `frontend/src/utils/specialDays.ts`, `frontend/src/utils/specialDays.test.ts`
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx:790-792` and `:974-976` (colour: `special?.mode === 'half_day'` → `special && !special.isFree`, amber for `half_day` and `max_hours`)
- Modify: `frontend/src/pages/Dashboard.tsx:212-221` (clock-status type, after `today_target_hours` `:217`) and `:619` (line under „x von y h heute“)
- Test: `frontend/src/utils/specialDays.test.ts`, `frontend/src/pages/Dashboard.test.tsx`

**Interfaces:**
- Produces:
  - `SpecialDayMode = 'working_day' | 'half_day' | 'free' | 'max_hours'`.
  - `SpecialDaySettings` gains `special_day_dec24_max_hours: number`, `special_day_dec31_max_hours: number` and `reduced_days?: { date: string; label: string; max_hours: number }[]`.
  - `SpecialDayInfo.mode: 'free' | 'half_day' | 'max_hours'` and `maxHours?: number`.
  - `formatHoursDe(h: number): string`, the twin of `format_hours_de`.
  - `reducedDayLabel(maxHours: number): string`, the twin of `reduced_day_label`.
  - `getSpecialDayInfo(dateStr, settings)`:
    - 24./31.12. are resolved from the settings first (like the backend, where the settings entry wins); any other date is looked up in `reduced_days` by exact `date`.
    - `max_hours` gives the label `${name}: ${reducedDayLabel(x)}` and `isFree` false.
    - free and half_day labels stay as they are.

- [ ] **Step 1: Write the failing tests.**

```ts
it('labels a custom reduced day by date', () => {
  const s = { ...base, reduced_days: [{ date: '2027-02-08', label: 'Rosenmontag', max_hours: 4 }] };
  const info = getSpecialDayInfo('2027-02-08', s)!;
  expect(info.mode).toBe('max_hours'); expect(info.isFree).toBe(false);
  expect(info.label).toBe('Rosenmontag: verkürzter Tag (max. 4 h)');
  expect(getSpecialDayInfo('2028-02-08', s)).toBeNull();
});
it('labels 24.12. in max_hours mode', () => { /* dec24 max_hours 4.5 → 'Heiligabend: verkürzter Tag (max. 4,5 h)' */ });
it('formats hours like the backend', () => { expect(reducedDayLabel(4)).toBe('verkürzter Tag (max. 4 h)'); expect(reducedDayLabel(4.25)).toBe('verkürzter Tag (max. 4,25 h)'); });
// Dashboard.test.tsx: clock-status with today_special_day_label 'verkürzter Tag (max. 4 h)' and today_target_hours 4 → text 'verkürzter Tag (max. 4 h)' rendered; without the field → not rendered
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `FE vitest run src/utils/specialDays.test.ts src/pages/Dashboard.test.tsx --pool=threads`
  Expected: FAIL. `reducedDayLabel` is not exported, and the label is missing from the Dashboard.

- [ ] **Step 3: Implement.** Keep the existing labels „Heiligabend (frei)“ and „Silvester (½ Tag)“ unchanged.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `FE vitest run src/utils/specialDays.test.ts src/pages/Dashboard.test.tsx --pool=threads && FE tsc --noEmit`
  Expected: PASS, and tsc exits 0. (There is no `AbsenceCalendarPage.test.tsx`; the calendar colour follows `getSpecialDayInfo`, which `specialDays.test.ts` covers.)

- [ ] **Step 5: Commit.** Message: `feat(reduced-days): calendar and stamp card show reduced days`.

---

### Task 11: Frontend — settings page mode and the „Verkürzte Tage“ card

**Files:**
- Modify: `frontend/src/pages/admin/Settings.tsx`:
  - types at `:53-66` (`SpecialDayMode` + `SPECIAL_DAY_MODE_LABELS.max_hours = 'Verkürzt auf X Stunden'`)
  - save at `:341-370`: PUT `special_day_dec24_max_hours` and `special_day_dec31_max_hours` **before** the modes; collect the warnings of all six responses with the existing de-dupe
  - UI at `:895-985`: number field with label `Höchstens (Stunden)`, `step=0.25`, `min=0.25`, `max=12`, shown only when the mode is `max_hours`; one added sentence in the explanation paragraph; render `<ReducedDaysCard />` below the card
- Create: `frontend/src/components/ReducedDaysCard.tsx`, `frontend/src/components/ReducedDaysCard.test.tsx`
- Test: `frontend/src/pages/admin/Settings.test.tsx`

**Interfaces:**
- Consumes: `GET/POST/PUT/DELETE /api/admin/reduced-days` (Task 7), via `apiClient`.
- Produces: `ReducedDaysCard()` (no props):
  - heading „Verkürzte Tage“
  - year selector like the holiday list
  - table columns „Datum“ / „Bezeichnung“ / „Höchstens (Stunden)“
  - add row with buttons „Hinzufügen“, „Speichern“, „Löschen“
  - error detail through `getErrorMessage`, warnings through `showResponseWarning(toast, response.data)`
  - explanation text, verbatim: „Für einzelne Tage (z. B. Rosenmontag) beträgt das Soll höchstens die eingetragene Stundenzahl. Wer an dem Tag ohnehin weniger Soll hat, behält es. Urlaub an einem verkürzten Tag kostet einen halben Tag. Für den 24. und 31.12. die Einstellung Sondertage oben verwenden.“

- [ ] **Step 1: Write the failing tests.**

```ts
// Settings.test.tsx
it('shows the hours field only in max_hours mode and saves hours before mode', async () => {
  // select 'Verkürzt auf X Stunden' for 24.12. → input 'Höchstens (Stunden)' visible; type 4; Speichern
  // expect put calls order: ..._dec24_max_hours ('4') before ..._dec24_mode ('max_hours')
});
// ReducedDaysCard.test.tsx
it('lists, adds and deletes reduced days', ...);           // GET ?year=… mocked; Hinzufügen posts {date,label,max_hours}; Löschen calls delete
it('shows the server error for 24.12.', ...);              // POST 400 detail → toast.error('Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden.')
it('shows the closed-year warning', ...);                  // response.data.warning → showResponseWarning called
```

  Use `fireEvent` and the focus-trap mock from `src/test/setup.ts`. Load once on mount (`[]` dependencies), never on a `useToast()` reference (CLAUDE.md).

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run: `FE vitest run src/pages/admin/Settings.test.tsx src/components/ReducedDaysCard.test.tsx --pool=threads`
  Expected: FAIL, the component is not found.

- [ ] **Step 3: Implement the interfaces above.**

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run: `FE vitest run src/pages/admin/Settings.test.tsx src/components/ReducedDaysCard.test.tsx --pool=threads && FE tsc --noEmit && FE eslint src`
  Expected: PASS and 0 errors.

- [ ] **Step 5: Commit.** Message: `feat(reduced-days): settings UI for max_hours mode and custom reduced days`.

---

### Task 12: Documentation (5 sync surfaces), doc-sync gate, CLAUDE.md, CHANGELOG

**Files:**
- Modify: `docs/BERECHNUNGEN.md` (§12.2 „Sondertage 24.12. / 31.12.“ → four modes + verkürzte Tage, `special_day_target`, credit weight `min(t,X)/t`, cost 0.5, fixed-mode rule; §9.3 closure booking with reduced target)
- Modify: `docs/GLOSSAR.md` (new term „verkürzter Tag“)
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md` (§13 „Sondertage 24./31.12.“ (~`:746`) + calendar `:435-439` + closure `:525`), `docs/handbuch/CHEATSHEET-ADMIN.md` (`:38`, `:51`, `:125`). Mention the „verkürzter Tag (max. 4 h)“ display in `HANDBUCH-MITARBEITER.md` / `CHEATSHEET-MITARBEITER.md` where the calendar colours are described.
- Mirror: `frontend/public/help/` (HANDBUCH-ADMIN, CHEATSHEET-ADMIN, HANDBUCH-MITARBEITER, CHEATSHEET-MITARBEITER byte-identical; copy file by file, never `cp docs/handbuch/*.md`)
- Modify: `frontend/src/components/DocViewer.tsx` (section „7. Sondertage 24./31.12.“ `:530-540` + mention in `SchnellstartAdmin` `:664` settings line `:673`), `frontend/src/constants/helpContent.tsx` (settings help)
- Modify: pzweb `/home/manuel/claude/pzweb/frontend/src/pages/marketing/anleitung/HandbuchAdmin.tsx` (+ `AnleitungBerechnungen.tsx`); tests there in docker `node:20`. This change goes in a separate pzweb PR, merged with the release (memory: pzweb docs ship with the release).
- Modify: `scripts/check-doc-sync.sh` (new `group_verkuerzt`)
- Modify: `CLAUDE.md`:
  - "Urlaub und Abwesenheiten": `half_day` bullet → „0,5 für `half_day` und `max_hours`“
  - "Urlaub und Abwesenheiten": the `half_day`-Sondertage bullet (#394) → closures book `special_day_target` (`min(Tagessoll, X)` on a reduced day), still `half_day=False`; the guard replaces the „nie inline“ wording
  - "Berechnung": „Ist-Gutschrift“ bullet → target-aware `credit_day_weight(..., daily_target=)`
  - new bullet „Verkürzte Tage (074)“: `special_days_service.special_day_target` is the one source, guard `test_no_special_factor_inline.py`, `reduced_days` table, re-save via `company_closures.resave_closures_for_dates`, closed years only warn
  - test command: add `--ignore=tests/test_074_reduced_days_pg.py` and `--ignore=tests/test_year_closing_lock_pg.py`; „die ACHT PG-Dateien“ in "Test-Stratifizierung"
- Modify: `CHANGELOG.md` (new `## [Unreleased]` → `### ✨ Neu` „Verkürzte Tage“, `### ⚠️ Verhaltensänderung`: changing the 24./31.12. setting now re-saves affected company closures automatically; closed years only warn)

**Interfaces:**
- Consumes: the wordings fixed in Global Constraints and Tasks 7, 10 and 11.

- [ ] **Step 1: Write the failing gate.** Add `group_verkuerzt()` to `scripts/check-doc-sync.sh`:
  - `need_code` for „Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden.“, „verkürzter Tag (max.“ and „Die Stundenzahl muss zwischen 0,25 und 12 liegen (in Schritten von 0,25).“
  - `need_code_label frontend/src/components/ReducedDaysCard.tsx "Verkürzte Tage"`
  - `need docs/handbuch/HANDBUCH-ADMIN.md 'Verkürzt auf X Stunden'`
  - `need docs/handbuch/HANDBUCH-ADMIN.md 'verkürzter Tag (max. 4 h)'`
  - `need docs/GLOSSAR.md 'verkürzter Tag'`
  - `need docs/BERECHNUNGEN.md 'special_day_target'`
  - `need frontend/src/components/DocViewer.tsx 'Verkürzt auf X Stunden'`
  - `need frontend/src/constants/helpContent.tsx 'Verkürzte Tage'`
  - `forbid backend/app/services/calculation_service.py 'legt ausschliesslich die'` (the outdated `credit_day_weight` docstring, `:1367-1368`, that Task 4 rewrites)

- [ ] **Step 2: Run the gate and confirm it fails.**
  Run: `bash scripts/check-doc-sync.sh verkuerzt`
  Expected: exit 1 with `FEHLT` lines for the docs (the `need_code` lines already pass).

- [ ] **Step 3: Write the docs** on all five surfaces. Then sync the mirror and update CLAUDE.md and the CHANGELOG.

- [ ] **Step 4: Run the checks and confirm they pass.**
  Run: `bash scripts/check-doc-sync.sh all && FE vitest run src/components/DocViewer.test.tsx --pool=threads`
  Expected: exit 0 and PASS. For pzweb, run `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v /home/manuel/claude/pzweb/frontend:/app -w /app node:20 npx vitest run src/pages/marketing/anleitung --pool=threads`. Expected: PASS.

- [ ] **Step 5: Commit** the praxiszeit files. Commit pzweb separately in its own repo and branch.

---

### Task 13: Full verification

- [ ] **Step 1:** Run the full SQLite suite (command in Global Constraints). Expected: `… passed` and no new failures compared with the run on `master` before Task 1. Note that baseline count before Task 1.
- [ ] **Step 2:** Run the PG suite: the PG command with all nine PG files from `local-ci.sh` step 2 plus `tests/test_074_reduced_days_pg.py`. Expected: all pass.
- [ ] **Step 3:** Run the frontend checks: `FE vitest run --pool=threads --maxWorkers=2 && FE tsc --noEmit && FE eslint src`. Expected: PASS, 0 errors.
- [ ] **Step 4:** Run `bash scripts/check-doc-sync.sh all`. Expected: exit 0.
- [ ] **Step 5: Manual smoke on the dev stack.**
  1. Run `docker compose build backend frontend && docker compose up -d`.
  2. Set 24.12. to „Verkürzt auf X Stunden“ = 4, and add a „Rosenmontag“ reduced day.
  3. Check the calendar label, the mobile stamp card, a December XLSX export (D24 soll 4,00), and a closure over Christmas (D24 hours 4,00).
  4. Run a PUT with a 24.12. date. Expected: 400 with the spec text.
- [ ] **Step 6:** Do not commit at this step. Hand over to `superpowers:finishing-a-development-branch`.
