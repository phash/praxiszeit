"""Teil B (Verkuerzte Tage), Postgres-only: Migration 074 auf echtem PostgreSQL.

Laeuft in einer EIGENEN Wegwerf-Datenbank auf demselben Server (``CREATE
DATABASE`` als Superuser). Alembic laeuft als Unterprozess ueber
``from alembic.config import main`` (kein ``python -m alembic``, cwd-Shadowing).

Geprueft: Tabelle, Eindeutigkeit, RLS (ENABLE + FORCE + Policy), Spaltentypen,
``created_by`` ON DELETE SET NULL, Round-Trip 074 -> 073 -> 074 und
Byte-Identitaet der Bestandstabellen (Anti-Ziel 1: 074 aendert kein
Altergebnis, sie legt nur eine Tabelle an).

Eingehaengt in ``scripts/local-ci.sh`` Schritt 2 und den PostgreSQL-Schritt von
``.github/workflows/cross-tenant-ci.yml`` (im SQLite-Schritt per ``--ignore``).
"""
import os
from pathlib import Path

import pytest
from sqlalchemy import text
from tests.pg_migration_helpers import alembic as _alembic, md5 as _md5, scratch_database

ADMIN_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_URL or not ADMIN_URL.startswith("postgresql"):
    pytest.skip(
        "test_074_reduced_days_pg.py braucht PostgreSQL (ADMIN_DB_URL / DATABASE_URL_MIGRATIONS)",
        allow_module_level=True,
    )

BACKEND = Path(__file__).resolve().parents[1]
TENANT = "00000000-0000-0000-0000-000000000001"  # legt Migration 027 an
COMPARED = ("absences", "system_settings", "company_closures")


def _scratch_database():
    return scratch_database(ADMIN_URL, "pz074")


@pytest.fixture(scope="module")
def scratch():
    with _scratch_database() as db:
        yield db


def _snapshot(conn) -> dict:
    return {t: _md5(conn, f"SELECT * FROM {t}") for t in COMPARED}


def test_074_round_trip_keeps_existing_tables(scratch):
    url, engine = scratch
    _alembic(url, "upgrade", "073_work_blocks")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO system_settings (tenant_id, key, value) "
            "VALUES (:t, 'rd074_probe', 'x')"), {"t": TENANT})
        # F045/F136: echte Zeilen in den verglichenen Tabellen, sonst vergleicht der
        # md5-Schnappschuss (Anti-Ziel 1) leere Tabellen.
        uid = conn.execute(text(
            "INSERT INTO users (id, tenant_id, username, email, password_hash, first_name, last_name, "
            "role, weekly_hours, vacation_days, is_active) "
            "VALUES (gen_random_uuid(), :t, 'rd074', 'rd074@x.invalid', 'x', 'R', 'D', 'EMPLOYEE', 40, 30, true) "
            "RETURNING id"), {"t": TENANT}).scalar()
        conn.execute(text(
            "INSERT INTO company_closures (id, tenant_id, name, start_date, end_date, counts_as_vacation, "
            "created_by) VALUES (gen_random_uuid(), :t, 'BF', '2026-02-16', '2026-02-20', true, :u)"),
            {"t": TENANT, "u": uid})
        conn.execute(text(
            "INSERT INTO absences (id, tenant_id, user_id, date, type, hours) "
            "VALUES (gen_random_uuid(), :t, :u, '2026-02-17', 'VACATION', 8)"), {"t": TENANT, "u": uid})
    with engine.connect() as conn:
        before = _snapshot(conn)
    assert before["absences"][0] == 1 and before["company_closures"][0] == 1   # nicht leer

    _alembic(url, "upgrade", "074_reduced_days")
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
            "WHERE relname='reduced_days'")).scalar() is True
        assert conn.execute(text(
            "SELECT count(*) FROM pg_policies WHERE tablename='reduced_days' "
            "AND policyname='tenant_isolation'")).scalar() == 1
        assert "uq_reduced_days_tenant_date" in {r[0] for r in conn.execute(text(
            "SELECT conname FROM pg_constraint WHERE conrelid='reduced_days'::regclass"))}
        cols = {r[0]: r[1:] for r in conn.execute(text(
            "SELECT column_name, data_type, numeric_precision, numeric_scale, "
            "character_maximum_length, is_nullable FROM information_schema.columns "
            "WHERE table_name='reduced_days'"))}
        assert cols["max_hours"][:3] == ("numeric", 4, 2)
        assert cols["label"][0] == "character varying" and cols["label"][3] == 100
        assert cols["label"][4] == "NO" and cols["max_hours"][4] == "NO"
        assert cols["created_by"][4] == "YES"
        # created_by -> users ON DELETE SET NULL (confdeltype 'n')
        assert conn.execute(text(
            "SELECT con.confdeltype FROM pg_constraint con "
            "JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey) "
            "WHERE con.conrelid='reduced_days'::regclass AND con.contype='f' "
            "AND att.attname='created_by'")).scalar() == "n"
        assert _snapshot(conn) == before

    _alembic(url, "downgrade", "073_work_blocks")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('reduced_days')")).scalar() is None
        assert _snapshot(conn) == before

    _alembic(url, "upgrade", "074_reduced_days")
    with engine.connect() as conn:
        assert _snapshot(conn) == before


def test_074_unique_tenant_date_rejects_duplicate(scratch):
    """F136: ``uq_reduced_days_tenant_date`` wirkt (nicht nur dem Namen nach)."""
    from sqlalchemy.exc import IntegrityError
    url, engine = scratch
    _alembic(url, "upgrade", "074_reduced_days")
    insert = text("INSERT INTO reduced_days (tenant_id, date, label, max_hours) "
                  "VALUES (:t, '2026-02-16', 'Rosenmontag', 4)")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM reduced_days"))
        conn.execute(insert, {"t": TENANT})
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert, {"t": TENANT})
