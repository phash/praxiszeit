"""
Concurrency integration tests against real Postgres.

These tests exist to catch races that can only manifest under true parallel
execution — they would silently pass against SQLite, which serialises at the
connection level. The runtime dependency is identical to test_tenant_rls.py:
the backend container's DATABASE_URL.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import date, time, datetime

import pytest
from sqlalchemy import create_engine, text

APP_DB_URL = os.environ.get("APP_DB_URL") or os.environ.get("DATABASE_URL")
ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not APP_DB_URL or not ADMIN_DB_URL:
    pytest.skip(
        "test_concurrency.py needs DATABASE_URL + DATABASE_URL_MIGRATIONS; "
        "run with `docker compose exec backend pytest …`.",
        allow_module_level=True,
    )

# F-Review (wrong-test finding): exercise the REAL locking/read code from
# app/routers/time_entries.py instead of a hand-rolled raw-SQL reimplementation
# that diverged from it (and silently omitted the F-026 tenant filter).
#
# Review 2026-07-14 (fix-A6c): go one step further and call the REAL
# `clock_in()` endpoint function itself (not just `_get_open_entry`), so the
# test exercises the User-row anchor lock added in front of it. A bare
# `SELECT ... FOR UPDATE` on zero matching rows locks nothing under READ
# COMMITTED — see the long comment in `clock_in` — so calling only
# `_get_open_entry` would never prove the anchor lock does anything.
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal, set_tenant_context
from app.models import User
from app.routers import time_entries
from app.schemas.time_entry import ClockInRequest
from app.services.timezone_service import LOCAL_TZ


TENANT_ID = uuid.UUID("ccccccc1-0000-4000-8000-000000000001")
USER_ID = uuid.UUID("ccccccc1-0000-4000-8000-000000000100")


@pytest.fixture(scope="module")
def admin_engine():
    eng = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def app_engine():
    eng = create_engine(APP_DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def concurrency_seed(admin_engine):
    """Create the test tenant + user; clean up after module."""
    conn = admin_engine.connect()
    # Best-effort pre-cleanup
    conn.execute(text("DELETE FROM time_entry_audit_logs WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM time_entries WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})

    conn.execute(text("""
        INSERT INTO tenants (id, name, slug, is_active, mode)
        VALUES (:id, :name, :slug, true, 'multi')
    """), {"id": str(TENANT_ID), "name": "Concurrency Test", "slug": "concurrency-test"})

    conn.execute(text("""
        INSERT INTO users (id, tenant_id, username, email, password_hash,
                           first_name, last_name, role, weekly_hours,
                           vacation_days, work_days_per_week, is_active)
        VALUES (:id, :tid, :u, :e, 'not-real', 'C', 'Test', 'EMPLOYEE',
                40, 30, 5, true)
    """), {
        "id": str(USER_ID), "tid": str(TENANT_ID),
        "u": "concurrency_test_user", "e": "concurrency@test.local",
    })

    yield

    conn.execute(text("DELETE FROM time_entry_audit_logs WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM time_entries WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})
    conn.close()


# fix-A6c: fixed "today" for both threads, but a DIFFERENT clock-in minute
# per thread. This deliberately keeps `uq_tenant_user_date_start` (tenant,
# user, date, start_time) from being able to catch a duplicate — the two
# inserts have different `start_time` values — so the ONLY thing that can
# still prevent a double-clock-in here is the User-row anchor lock in
# `clock_in`. A same-minute race would let the unique constraint mask a
# missing/removed anchor lock (see fix-A6b-report.md); this test must not
# depend on that safety net if it is to have teeth against a regression.
_FAKE_TODAY = date(2099, 6, 1)
_fake_time_by_thread: dict = {}


def _fake_now_local():
    t = _fake_time_by_thread[threading.get_ident()]
    return datetime.combine(_FAKE_TODAY, t, tzinfo=LOCAL_TZ)


def _fake_today_local():
    return _FAKE_TODAY


def _run_clock_in_attempt(
    results: list,
    idx: int,
    barrier: threading.Barrier,
    fake_time,
):
    """Call the REAL `app.routers.time_entries.clock_in()` endpoint function
    directly (not a reimplementation) so the test exercises everything the
    endpoint does, including the User-row anchor lock added in front of
    `_get_open_entry`. `time_entries._now_local`/`_today_local` are
    monkeypatched module-wide by the test (before threads start) to
    `_fake_now_local`/`_fake_today_local`; this thread registers its own
    fixed `fake_time` under its thread-id so both threads land on the same
    fake "today" but a different minute (see module comment above).

    Uses `app.database.SessionLocal` + `set_tenant_context` (the REAL
    production wiring, not a raw `SET LOCAL` on an ad-hoc sessionmaker):
    `clock_in` does `db.refresh(entry)` AFTER `db.commit()`, which starts a
    new transaction, and plain `SET LOCAL` is transaction-scoped — only
    `SessionLocal`'s `after_begin` event listener (registered in
    app/database.py) re-applies `app.tenant_id` on that new transaction, so
    the post-commit refresh still passes RLS.
    """
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        current_user = session.query(User).filter(User.id == USER_ID).first()
        _fake_time_by_thread[threading.get_ident()] = fake_time

        # Align the two threads so they enter clock_in() at nearly the same
        # instant — this is the actual concurrency being tested.
        barrier.wait(timeout=5)

        time_entries.clock_in(
            body=ClockInRequest(note=None), db=session, current_user=current_user,
        )
        results.append(("inserted", idx))
    except HTTPException as e:
        # "Bereits eingestempelt" — the expected loser outcome when the
        # anchor lock correctly serializes the two attempts.
        session.rollback()
        results.append(("rejected", idx, e.status_code))
    except IntegrityError as e:
        session.rollback()
        results.append(("error", idx, "IntegrityError"))
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", idx, type(e).__name__))
    finally:
        del _fake_time_by_thread[threading.get_ident()]
        session.close()


def test_parallel_clock_in_serializes(app_engine, concurrency_seed, admin_engine, monkeypatch):
    """
    Two threads race the REAL `clock_in()` endpoint function from
    app/routers/time_entries.py (not a raw-SQL reimplementation) for the SAME
    user, at nearly the same instant, on the same fake "today" but different
    minutes (so the `uq_tenant_user_date_start` unique constraint cannot mask
    a broken/missing anchor lock — see module comment above). Only ONE of the
    two racing attempts may survive as an open entry — otherwise the user
    ends up with two overlapping open entries, which is exactly the §16
    double-clock-in gap this test guards against.

    Regression coverage: commenting out the `db.query(User)...with_for_update()`
    anchor lock in `clock_in` (VULN-009 / review 2026-07-14 fix) makes this
    test fail with 2 inserted/open entries instead of 1 — verified manually
    against Postgres 18 as part of the fix, see fix-A6c-report.md.
    """
    # Ensure the user has no open entry before the race starts
    admin = admin_engine.connect()
    admin.execute(text("DELETE FROM time_entries WHERE user_id = :u"), {"u": str(USER_ID)})
    admin.close()

    monkeypatch.setattr(time_entries, "_now_local", _fake_now_local)
    monkeypatch.setattr(time_entries, "_today_local", _fake_today_local)

    results: list = []
    barrier = threading.Barrier(2)
    t1 = threading.Thread(
        target=_run_clock_in_attempt, args=(results, 1, barrier, time(9, 0)),
    )
    t2 = threading.Thread(
        target=_run_clock_in_attempt, args=(results, 2, barrier, time(9, 1)),
    )
    t1.start(); t2.start(); t1.join(); t2.join()

    outcomes = [r[0] for r in results]
    inserted = outcomes.count("inserted")
    errored = [r for r in results if r[0] == "error"]
    # The loser must be rejected either by the application-level "Bereits
    # eingestempelt" check (outcome "rejected") or, as a defense-in-depth
    # backstop, by a DB-level unique/exclusion violation (outcome "error" /
    # IntegrityError) — never a silent duplicate and never an unrelated crash.
    for r in errored:
        assert r[2] == "IntegrityError", f"Unexpected error type on loser thread: {r}"
    assert inserted == 1, f"Expected exactly 1 insert, got outcomes={outcomes}"

    # Verify DB state: exactly one open entry
    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        count = conn.execute(
            text("SELECT COUNT(*) FROM time_entries WHERE user_id = :u AND end_time IS NULL"),
            {"u": str(USER_ID)},
        ).scalar()
        assert count == 1
