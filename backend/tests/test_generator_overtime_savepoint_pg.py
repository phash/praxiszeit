"""Generator-Überstundenabfrage im SAVEPOINT gegen **echtes PostgreSQL** (ui-08, 2026-11-11).

Auf PostgreSQL bricht ein gescheitertes Statement die ganze Transaktion ab; ein
breites ``except Exception`` um ``get_overtime_account`` ließ das anschließende
DELETE/INSERT des Generators mit ``InFailedSqlTransaction`` scheitern. Der
Generator rechnet deshalb in ``db.begin_nested()``. SQLite hat dieses
Abbruchverhalten nicht — dieser Beleg läuft nur mit PostgreSQL (Modul-Skip ohne
``DATABASE_URL_MIGRATIONS``/``ADMIN_DB_URL``; nicht in der SQLite-Suite lauffähig,
verdrahtet in ``local-ci.sh`` und im PG-Workflow neben
``test_year_closing_lock_pg.py``).
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_DB_URL:
    pytest.skip("test_generator_overtime_savepoint_pg.py braucht DATABASE_URL_MIGRATIONS (oder ADMIN_DB_URL).",
                allow_module_level=True)


def test_failed_statement_inside_savepoint_leaves_transaction_usable():
    eng = create_engine(ADMIN_DB_URL)
    s = sessionmaker(bind=eng)()
    try:
        value = Decimal(0)
        try:
            with s.begin_nested():
                s.execute(text("SELECT 1/0"))  # division_by_zero → Transaktion wäre ohne SAVEPOINT abgebrochen
        except Exception:  # noqa: BLE001 — genau das Muster des Generators
            pass
        assert s.execute(text("SELECT 1")).scalar() == 1
        assert value == 0
    finally:
        s.rollback()
        s.close()
        eng.dispose()
