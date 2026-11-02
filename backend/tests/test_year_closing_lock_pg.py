"""Year-closing advisory lock against **real PostgreSQL** (2026-11-02).

SQLite has no ``pg_advisory_xact_lock``, so the SQLite suite never saw that
the old two-argument call (int, bigint) does not exist and aborted the
transaction. This file proves the lock call succeeds and the transaction stays
usable afterwards. Module-level skip without PostgreSQL, wired into
``scripts/local-ci.sh`` step 2 and the PostgreSQL step of
``.github/workflows/cross-tenant-ci.yml``.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_DB_URL:
    pytest.skip("test_year_closing_lock_pg.py braucht DATABASE_URL_MIGRATIONS (oder ADMIN_DB_URL).",
                allow_module_level=True)

from app.routers.admin_carryovers import lock_year_closing


def test_lock_succeeds_and_transaction_stays_usable():
    eng = create_engine(ADMIN_DB_URL)
    s = sessionmaker(bind=eng)()
    try:
        lock_year_closing(s, "00000000-0000-0000-0000-000000000001", 2025)
        assert s.execute(text("SELECT 1")).scalar() == 1
        held = s.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                              "AND pid = pg_backend_pid()")).scalar()
        assert held == 1
    finally:
        s.rollback()
        s.close()
        eng.dispose()
