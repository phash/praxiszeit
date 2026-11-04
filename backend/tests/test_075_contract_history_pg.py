"""Teil A (Vertragsverlauf), Task 16 (Postgres-only): Migration 075 auf echtem PostgreSQL.

Läuft in einer EIGENEN Wegwerf-Datenbank auf demselben Server (``CREATE
DATABASE`` als Superuser) — die geteilte Test-DB wird nie herabgestuft.
Alembic läuft als Unterprozess über ``from alembic.config import main``
(CLAUDE.md: kein ``python -m alembic`` wegen cwd-Shadowing). Muster
``test_073_migration_pg.py``.

Geprüft: Backfill der fünf Vertragsfelder in JEDE Verlaufszeile aus der
User-Zeile (``agreed_monthly_hours`` NULL bleibt NULL), NOT NULL der vier
Pflichtspalten, Byte-Identität von ``users`` und aller übrigen
``working_hours_changes``-Spalten nach Upgrade, Downgrade und erneutem Upgrade,
Downgrade entfernt die fünf Spalten — und der Backfill als Eigentümerin OHNE
Superuser-Recht unter FORCE RLS (nur dieser Lauf sieht, ob
``SET LOCAL app.is_superadmin`` greift).

Eingehängt in ``scripts/local-ci.sh`` Schritt 2 und den PostgreSQL-Schritt von
``.github/workflows/cross-tenant-ci.yml`` (im SQLite-Schritt per ``--ignore``).
"""
import os
import secrets
import subprocess
import sys
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_URL or not ADMIN_URL.startswith("postgresql"):
    pytest.skip(
        "test_075_contract_history_pg.py braucht PostgreSQL (ADMIN_DB_URL / DATABASE_URL_MIGRATIONS)",
        allow_module_level=True,
    )

BACKEND = Path(__file__).resolve().parents[1]
TENANT = "00000000-0000-0000-0000-000000000001"  # legt Migration 027 an
BASE_REV = "074_reduced_days"
HEAD_REV = "075_contract_history"
FIELDS = ("vacation_days", "track_hours", "milog_working_time_account",
          "agreed_monthly_hours", "use_fixed_monthly_target")
NOT_NULL = ("vacation_days", "track_hours", "milog_working_time_account", "use_fixed_monthly_target")

# Je Person die fünf Werte der User-Zeile: jede Person weicht in genau EINEM Feld
# vom Normalfall ab, damit ein vertauschter Spaltenbezug im Backfill auffällt.
NORMAL = {"vacation_days": Decimal("30.0"), "track_hours": True, "milog_working_time_account": False,
          "agreed_monthly_hours": None, "use_fixed_monthly_target": False}
PEOPLE = {
    "urlaub24": {**NORMAL, "vacation_days": Decimal("24.0")},
    "ohnezaehlung": {**NORMAL, "track_hours": False},
    "milog": {**NORMAL, "milog_working_time_account": True},
    "vereinbart": {**NORMAL, "milog_working_time_account": True, "agreed_monthly_hours": Decimal("43.3")},
    "fest": {**NORMAL, "milog_working_time_account": True, "agreed_monthly_hours": Decimal("43.3"),
             "use_fixed_monthly_target": True},
    "normal": dict(NORMAL),
}
U = {name: str(uuid.UUID(int=0x7575_0000_0000_4000_8000_0000_0000_0000 + i))
     for i, name in enumerate(PEOPLE, 1)}
DAYS = ("2025-01-01", "2026-01-01", "2026-06-01")


def _alembic(url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL_MIGRATIONS": url}
    proc = subprocess.run(
        [sys.executable, "-c", f"from alembic.config import main; main({list(args)!r})"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout + proc.stderr


def _md5(conn, sql: str) -> tuple:
    return tuple(conn.execute(text(
        f"SELECT count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM ({sql}) t"
    )).one())


def _columns(conn, table: str) -> list:
    return [c for (c,) in conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position"
    ), {"t": table}).all()]


def _bestand(conn) -> dict:
    """Spaltenlisten im Stand 074 aus ``information_schema`` (nicht von Hand:
    eine vergessene Spalte wäre genau die, die ein Fehler verändert)."""
    return {t: ", ".join(f'"{c}"' for c in _columns(conn, t)) for t in ("users", "working_hours_changes")}


def _snapshot(conn, lists: dict) -> dict:
    return {table: _md5(conn, f"SELECT {cols} FROM {table}") for table, cols in lists.items()}


@contextmanager
def _scratch_database():
    name = f"pz075_{uuid.uuid4().hex[:10]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def scratch():
    with _scratch_database() as db:
        yield db


@pytest.fixture
def owner_scratch():
    """Wegwerf-Datenbank plus eine Rolle OHNE Superuser- und BYPASSRLS-Recht.
    Teardown: erst die Datenbank (darin liegt alles, was ihr gehört), dann die Rolle."""
    role = f"pz075_owner_{uuid.uuid4().hex[:10]}"
    password = secrets.token_hex(16)
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"CREATE ROLE \"{role}\" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'"))
        with _scratch_database() as (url, engine):
            owner_url = make_url(url).set(username=role, password=password).render_as_string(hide_password=False)
            yield url, engine, role, owner_url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()


def _user(conn, key):
    values = PEOPLE[key]
    cols = ["id", "tenant_id", "username", "email", "password_hash", "first_name",
            "last_name", "role", "weekly_hours", "is_active", *FIELDS]
    params = {"id": U[key], "tenant_id": TENANT, "username": key, "email": f"{key}@x.de",
              "password_hash": "h", "first_name": key, "last_name": "T", "role": "EMPLOYEE",
              "weekly_hours": 40, "is_active": True, **values}
    conn.execute(text(
        f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"
    ), params)


def _history_rows(conn, key, n=3):
    base = 0x7676_0000_0000_4000_8000_0000_0000_0000 + 16 * list(PEOPLE).index(key)
    for i, day in enumerate(DAYS[:n]):
        conn.execute(text(
            "INSERT INTO working_hours_changes (id, tenant_id, user_id, effective_from, weekly_hours, note) "
            "VALUES (:id, :t, :u, :d, :w, :n)"
        ), {"id": str(uuid.UUID(int=base + i)), "t": TENANT, "u": U[key], "d": day,
            "w": 20 + 5 * i, "n": f"{key} {i}"})


def _seed_074(conn):
    for key in PEOPLE:
        _user(conn, key)
        _history_rows(conn, key)


def _row_values(conn) -> dict:
    """{username: [(f1..f5) je Verlaufszeile nach effective_from]}"""
    rows = conn.execute(text(
        f"SELECT u.username, {', '.join('w.' + f for f in FIELDS)} FROM working_hours_changes w "
        "JOIN users u ON u.id = w.user_id ORDER BY u.username, w.effective_from"
    )).all()
    out = {}
    for row in rows:
        out.setdefault(row[0], []).append(tuple(row[1:]))
    return out


def _expected(key) -> tuple:
    return tuple(PEOPLE[key][f] for f in FIELDS)


def test_round_trip_075_074_075_and_backfill(scratch):
    url, engine = scratch
    _alembic(url, "upgrade", BASE_REV)
    with engine.begin() as conn:
        _seed_074(conn)
    with engine.connect() as conn:
        bestand = _bestand(conn)
        before = _snapshot(conn, bestand)
        assert before["working_hours_changes"][0] == 3 * len(PEOPLE)

    out = _alembic(url, "upgrade", HEAD_REV)
    assert f"075: {3 * len(PEOPLE)} Verlaufszeilen" in out

    with engine.connect() as conn:
        values = _row_values(conn)
        assert set(values) == set(PEOPLE)
        for key in PEOPLE:
            assert values[key] == [_expected(key)] * 3, key
        assert values["normal"][0][FIELDS.index("agreed_monthly_hours")] is None  # NULL bleibt NULL
        columns = {c: (d, n, p, s) for c, d, n, p, s in conn.execute(text(
            "SELECT column_name, data_type, is_nullable, numeric_precision, numeric_scale "
            "FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'working_hours_changes'"
        )).all()}
        assert columns["vacation_days"] == ("numeric", "NO", 4, 1)
        assert columns["agreed_monthly_hours"] == ("numeric", "YES", 5, 1)
        for name in ("track_hours", "milog_working_time_account", "use_fixed_monthly_target"):
            assert columns[name] == ("boolean", "NO", None, None), name
        assert conn.execute(text(
            "SELECT count(*) FROM working_hours_changes WHERE " + " OR ".join(f"{c} IS NULL" for c in NOT_NULL)
        )).scalar() == 0
        # Bestandsspalten (Stand 074) unverändert, users vollständig
        assert _snapshot(conn, bestand) == before

    _alembic(url, "downgrade", BASE_REV)
    with engine.connect() as conn:
        remaining = set(_columns(conn, "working_hours_changes")) & set(FIELDS)
        assert remaining == set()
        assert _snapshot(conn, bestand) == before

    _alembic(url, "upgrade", HEAD_REV)
    with engine.connect() as conn:
        values = _row_values(conn)
        for key in PEOPLE:
            assert values[key] == [_expected(key)] * 3, key
        assert _snapshot(conn, bestand) == before


RLS_TABLES = ("users", "working_hours_changes")


def test_backfill_as_non_superuser_owner_under_force_rls(owner_scratch):
    """Die Migrationsrolle besitzt die Tabellen, ist aber KEIN Superuser — dann
    gilt FORCE RLS auch für sie, und ohne ``SET LOCAL app.is_superadmin`` träfe
    der Backfill keine Zeile und das anschließende NOT NULL bräche die Migration
    ab (mit entferntem ``SET LOCAL`` geprüft: ``NotNullViolation``). Die Werte
    liest der Test als Superuser an RLS vorbei."""
    url, engine, role, owner_url = owner_scratch
    _alembic(url, "upgrade", BASE_REV)
    with engine.begin() as conn:
        for key in ("urlaub24", "fest"):
            _user(conn, key)
            _history_rows(conn, key, n=2)
        conn.execute(text(
            "DO $$ DECLARE r record; BEGIN "
            "FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP "
            f"EXECUTE format('ALTER TABLE %I OWNER TO %I', r.tablename, '{role}'); "
            "END LOOP; END $$"
        ))
    with engine.connect() as conn:
        # Vorbedingung: sonst prüfte der Test still wieder den Superuser-Fall.
        assert conn.execute(text(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = :r"
        ), {"r": role}).scalar() is False
        assert dict(conn.execute(text(
            "SELECT c.relname, c.relrowsecurity AND c.relforcerowsecurity "
            "AND pg_get_userbyid(c.relowner) = :r "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY(:tables)"
        ), {"r": role, "tables": list(RLS_TABLES)}).all()) == {t: True for t in RLS_TABLES}

    out = _alembic(owner_url, "upgrade", HEAD_REV)
    assert "075: 4 Verlaufszeilen" in out

    with engine.connect() as conn:  # Superuser: liest an RLS vorbei
        values = _row_values(conn)
        assert values == {"urlaub24": [_expected("urlaub24")] * 2, "fest": [_expected("fest")] * 2}
