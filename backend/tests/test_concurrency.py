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
from datetime import date, time, timezone, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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
from app.models import TimeEntry
from app.routers.time_entries import _get_open_entry


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


def _run_clock_in_attempt(
    app_engine,
    results: list,
    idx: int,
    barrier: threading.Barrier,
    with_lock: bool = True,
):
    """Run the REAL clock-in read from app/routers/time_entries.py.

    Calls the actual `_get_open_entry(db, user_id, with_lock=…, tenant_id=…)`
    used by the `clock_in` endpoint (not a raw-SQL reimplementation), then —
    mirroring what `clock_in` does on a miss — inserts a new open TimeEntry
    via the ORM. Both threads use the SAME `start_time`, mirroring the real
    endpoint's `now().time().replace(second=0, microsecond=0)` truncation:
    two clock-in attempts racing within the same wall-clock minute (the
    realistic double-click/retry scenario `VULN-009` targets) compute an
    identical `start_time`.

    `with_lock` is a test-only knob (default True = the real production call
    shape). NOTE (verified empirically against real Postgres 18, see
    fix-A6b-report.md): for this "insert into a possibly-empty table" shape,
    PostgreSQL's row lock cannot serialize a phantom insert — `FOR UPDATE`
    only locks rows a query *returns*, and neither racing thread's SELECT
    ever returns a row here regardless of `with_lock`. The guarantee this
    test observes (never more than one surviving open entry for a same-
    minute race) is actually provided by the `uq_tenant_user_date_start`
    unique constraint, not by `_get_open_entry`'s lock. Flipping `with_lock`
    does not change this test's outcome — that is expected, not a bug in the
    test; see the report for the full analysis and the resulting concern.
    """
    Session = sessionmaker(bind=app_engine)
    session = Session()
    try:
        session.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        # Align the two threads so they enter the critical section at nearly
        # the same instant.
        barrier.wait(timeout=5)

        # The REAL locking read used by app.routers.time_entries.clock_in.
        open_entry = _get_open_entry(
            session, USER_ID, with_lock=with_lock, tenant_id=TENANT_ID,
        )

        if open_entry is not None:
            # Another thread already opened a row and committed — reject
            results.append(("rejected", idx))
            session.rollback()
            return

        # No open entry, insert one — same as clock_in's TimeEntry(...) + add.
        entry = TimeEntry(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            date=date(2099, 6, 1),
            start_time=time(9, 0),  # same for both threads, see docstring
            end_time=None,
            break_minutes=0,
        )
        session.add(entry)
        session.commit()
        results.append(("inserted", idx))
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", idx, type(e).__name__))
    finally:
        session.close()


def test_parallel_clock_in_serializes(app_engine, concurrency_seed, admin_engine):
    """
    Two threads race the REAL `_get_open_entry(..., with_lock=True)` read from
    app/routers/time_entries.py (not a raw-SQL reimplementation), then insert
    a new open TimeEntry on a miss — mirroring `clock_in` exactly, including
    its F-026 tenant filter and its minute-truncated `start_time`. Only ONE
    of the two racing attempts may survive as an open entry — otherwise the
    user ends up with two overlapping open entries.
    """
    # Ensure the user has no open entry before the race starts
    admin = admin_engine.connect()
    admin.execute(text("DELETE FROM time_entries WHERE user_id = :u"), {"u": str(USER_ID)})
    admin.close()

    results: list = []
    barrier = threading.Barrier(2)
    t1 = threading.Thread(target=_run_clock_in_attempt, args=(app_engine, results, 1, barrier))
    t2 = threading.Thread(target=_run_clock_in_attempt, args=(app_engine, results, 2, barrier))
    t1.start(); t2.start(); t1.join(); t2.join()

    outcomes = [r[0] for r in results]
    inserted = outcomes.count("inserted")
    errored = [r for r in results if r[0] == "error"]
    # The loser must be rejected either by the application-level open-entry
    # check (outcome "rejected") or by the DB's uq_tenant_user_date_start
    # unique constraint (outcome "error" / IntegrityError) — never a silent
    # duplicate and never an unrelated crash.
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
