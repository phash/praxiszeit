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


def _run_clock_in_attempt(app_engine, results: list, idx: int, barrier: threading.Barrier):
    """Simulate the clock-in sequence from app/routers/time_entries.py with row lock.

    Mirrors `_get_open_entry(..., with_lock=True)` followed by an INSERT for a
    new open entry. Both threads race — the row-lock acquired by whichever
    thread enters the CRITICAL section first should serialize the second.
    """
    Session = sessionmaker(bind=app_engine)
    session = Session()
    try:
        session.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        # Align the two threads so they enter the critical section at nearly
        # the same instant.
        barrier.wait(timeout=5)

        # SELECT … FOR UPDATE on the user's open entries
        row = session.execute(
            text(
                "SELECT id FROM time_entries "
                "WHERE user_id = :uid AND end_time IS NULL "
                "FOR UPDATE"
            ),
            {"uid": str(USER_ID)},
        ).fetchone()

        if row is not None:
            # Another thread already opened a row and committed — reject
            results.append(("rejected", idx))
            session.rollback()
            return

        # No open entry, insert one
        new_id = uuid.uuid4()
        session.execute(
            text(
                "INSERT INTO time_entries (id, tenant_id, user_id, date, "
                "  start_time, break_minutes) "
                "VALUES (:id, :tid, :uid, :dt, :st, 0)"
            ),
            {
                "id": str(new_id),
                "tid": str(TENANT_ID),
                "uid": str(USER_ID),
                "dt": date(2099, 6, 1),
                "st": time(9, 0),
            },
        )
        session.commit()
        results.append(("inserted", idx))
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", idx, str(e)))
    finally:
        session.close()


def test_parallel_clock_in_serializes(app_engine, concurrency_seed, admin_engine):
    """
    Two threads try to create an open time entry simultaneously. The row-lock
    must serialise them so that only ONE insert succeeds — otherwise the user
    ends up with two overlapping open entries.
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
    # Exactly one should have inserted, exactly one should have been rejected
    # (or errored on the unique lock — acceptable). Two inserts = bug.
    inserted = outcomes.count("inserted")
    assert inserted == 1, f"Expected exactly 1 insert, got outcomes={outcomes}"

    # Verify DB state: exactly one open entry
    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        count = conn.execute(
            text("SELECT COUNT(*) FROM time_entries WHERE user_id = :u AND end_time IS NULL"),
            {"u": str(USER_ID)},
        ).scalar()
        assert count == 1
