"""P1.7 (Handbuch-Funde 2026-11-11, Postgres-only): Migration 077 auf echtem PostgreSQL.

077 trägt ``absences.half_day`` für Altzeilen (vor #205/1.9.0, ``half_day IS
NULL``) nach — nur wo die Stunden eindeutig ein voller Tag (``hours ==
Tagessoll``) oder ein Halbtag (``hours == Tagessoll / 2``) laut Vertrags-
Snapshot des Datums sind. Alles andere bleibt NULL.

Läuft in einer EIGENEN Wegwerf-Datenbank (Muster ``test_075_contract_history_pg.py``):
Upgrade 076 → 077, Downgrade (bewusst ohne Rückänderung), erneutes Upgrade
(idempotent), übrige Spalten byte-identisch — und der Nachtrag als Eigentümerin
OHNE Superuser-Recht unter FORCE RLS (nur dort zeigt sich, ob ``SET LOCAL
app.is_superadmin`` greift).

Eingehängt in ``scripts/local-ci.sh`` Schritt 2 und den PostgreSQL-Schritt von
``.github/workflows/cross-tenant-ci.yml`` (im SQLite-Schritt per ``--ignore``).
"""
import os
import secrets
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from tests.pg_migration_helpers import alembic as _alembic, md5 as _md5, scratch_database

ADMIN_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_URL or not ADMIN_URL.startswith("postgresql"):
    pytest.skip(
        "test_077_legacy_half_day_pg.py braucht PostgreSQL (ADMIN_DB_URL / DATABASE_URL_MIGRATIONS)",
        allow_module_level=True,
    )

TENANT = "00000000-0000-0000-0000-000000000001"  # legt Migration 027 an
BASE_REV = "076_audit_chain"
HEAD_REV = "077_legacy_half_day"


def _uid(n: int) -> str:
    return str(uuid.UUID(int=0x7777_0000_0000_4000_8000_0000_0000_0000 + n))


EVEN, DAILY, UNTRACKED = _uid(1), _uid(2), _uid(3)

# (Schlüssel, Person, Datum, Typ, Stunden, start_time, end_date, half_day vorher, erwartet nach 077)
# 2026-01-05 = Montag.
ROWS = [
    # Gleichmäßig 40 h / 5 Tage, ohne Verlauf → Tagessoll 8,00 laut User-Zeile
    ("voll", EVEN, "2026-01-05", "VACATION", "8.00", None, None, None, False),
    ("halb", EVEN, "2026-01-06", "VACATION", "4.00", None, None, None, True),
    ("krank_voll", EVEN, "2026-01-07", "SICK", "8.00", None, None, None, False),
    ("uneindeutig", EVEN, "2026-01-08", "VACATION", "5.00", None, None, None, None),
    ("ueberstunden", EVEN, "2026-01-09", "OVERTIME", "8.00", None, None, None, None),
    ("mit_uhrzeit", EVEN, "2026-01-12", "OTHER", "8.00", "08:00", None, None, None),
    ("samstag", EVEN, "2026-01-10", "VACATION", "8.00", None, None, None, None),
    ("heiligabend", EVEN, "2025-12-24", "VACATION", "8.00", None, None, None, None),
    ("verkuerzt", EVEN, "2026-02-16", "VACATION", "8.00", None, None, None, None),
    ("zeitraum", EVEN, "2026-01-13", "VACATION", "8.00", None, "2026-01-14", None, None),
    ("schon_gesetzt", EVEN, "2026-01-15", "VACATION", "4.00", None, None, False, False),
    # Tagesplan: Verlauf ab 01.03. (Mo 4,5 / Di 4); User-Zeile = Spiegel des Heute.
    # Vor der ersten Zeile gilt die User-Zeile (Mo 4,5) — 5 h am 02.02. sind ein
    # gedrifteter Altwert und bleiben NULL.
    ("vor_verlauf", DAILY, "2026-02-02", "VACATION", "5.00", None, None, None, None),
    ("tagesplan_voll", DAILY, "2026-03-02", "VACATION", "4.50", None, None, None, False),
    ("tagesplan_halb", DAILY, "2026-03-03", "VACATION", "2.00", None, None, None, True),
    ("ungerader_cent", DAILY, "2026-03-04", "VACATION", "3.63", None, None, None, True),
    ("freier_tag", DAILY, "2026-03-05", "VACATION", "0.00", None, None, None, None),
    # Ohne Stundenzählung (Snapshot) → nie anfassen
    ("ohne_zaehlung", UNTRACKED, "2026-01-05", "VACATION", "0.00", None, None, None, None),
]
ABS = {key: _uid(100 + i) for i, (key, *_rest) in enumerate(ROWS)}


def _user(conn, uid, name, *, daily=False, track=True):
    conn.execute(text(
        "INSERT INTO users (id, tenant_id, username, email, password_hash, first_name, last_name, role, "
        "weekly_hours, work_days_per_week, use_daily_schedule, hours_monday, hours_tuesday, "
        "hours_wednesday, hours_thursday, hours_friday, track_hours, vacation_days, is_active) VALUES "
        "(:id, :t, :n, :e, 'h', :n, 'T', 'EMPLOYEE', :w, 5, :daily, :mo, :di, :mi, :do, :fr, :track, 30, true)"
    ), {"id": uid, "t": TENANT, "n": name, "e": f"{name}@x.de", "w": 18.75 if daily else 40,
        "daily": daily, "mo": 4.5 if daily else None, "di": 4 if daily else None,
        "mi": 7.25 if daily else None, "do": 0 if daily else None, "fr": 3 if daily else None,
        "track": track})


def _seed(conn):
    _user(conn, EVEN, "gleich")
    _user(conn, DAILY, "tagesplan", daily=True)
    _user(conn, UNTRACKED, "ohne", track=False)
    conn.execute(text(
        "INSERT INTO working_hours_changes (id, tenant_id, user_id, effective_from, weekly_hours, "
        "use_daily_schedule, hours_monday, hours_tuesday, hours_wednesday, hours_thursday, hours_friday, "
        "work_days_per_week, vacation_days, track_hours, milog_working_time_account, "
        "use_fixed_monthly_target, note) VALUES "
        "(:id, :t, :u, '2026-03-01', 18.75, true, 4.5, 4, 7.25, 0, 3, 4, 30, true, false, false, 'plan')"
    ), {"id": _uid(50), "t": TENANT, "u": DAILY})
    conn.execute(text(
        "INSERT INTO reduced_days (tenant_id, date, label, max_hours) "
        "VALUES (:t, '2026-02-16', 'Rosenmontag', 4)"
    ), {"t": TENANT})
    for key, uid, day, typ, hours, start, end, before, _exp in ROWS:
        conn.execute(text(
            "INSERT INTO absences (id, tenant_id, user_id, date, end_date, type, hours, start_time, "
            "end_time, half_day, note) VALUES (:id, :t, :u, :d, :end, :typ, :h, :s, :e, :hd, :n)"
        ), {"id": ABS[key], "t": TENANT, "u": uid, "d": day, "end": end, "typ": typ, "h": hours,
            "s": start, "e": "12:00" if start else None, "hd": before, "n": key})


def _half_days(conn) -> dict:
    rows = conn.execute(text("SELECT note, half_day FROM absences")).all()
    return dict(rows)


def _expected() -> dict:
    return {key: exp for key, *_rest, exp in ROWS}


def _other_columns(conn) -> tuple:
    cols = [c for (c,) in conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
        "AND table_name = 'absences' AND column_name <> 'half_day' ORDER BY ordinal_position"
    )).all()]
    return _md5(conn, f"SELECT {', '.join(cols)} FROM absences")


@pytest.fixture
def scratch():
    with scratch_database(ADMIN_URL, "pz077") as db:
        yield db


@pytest.fixture
def owner_scratch():
    role = f"pz077_owner_{uuid.uuid4().hex[:10]}"
    password = secrets.token_hex(16)
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"CREATE ROLE \"{role}\" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'"))
        with scratch_database(ADMIN_URL, "pz077") as (url, engine):
            owner_url = make_url(url).set(username=role, password=password).render_as_string(hide_password=False)
            yield url, engine, role, owner_url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()


def test_round_trip_077_076_077(scratch):
    url, engine = scratch
    _alembic(url, "upgrade", BASE_REV)
    with engine.begin() as conn:
        _seed(conn)
    with engine.connect() as conn:
        before = _other_columns(conn)
        assert before[0] == len(ROWS)

    out = _alembic(url, "upgrade", HEAD_REV)
    assert "077: 14 Altzeilen ohne half_day: 3 ganztaegig, 3 halbtaegig, 8 unveraendert" in out, out
    with engine.connect() as conn:
        assert _half_days(conn) == _expected()
        assert _other_columns(conn) == before  # nur half_day geändert

    # Downgrade: bewusst keine Rückänderung (reine Datenergänzung)
    _alembic(url, "downgrade", BASE_REV)
    with engine.connect() as conn:
        assert _half_days(conn) == _expected()
        assert _other_columns(conn) == before

    # Erneutes Upgrade: idempotent, die gesetzten Zeilen sind keine Kandidaten mehr
    out = _alembic(url, "upgrade", HEAD_REV)
    assert "077: 8 Altzeilen ohne half_day: 0 ganztaegig, 0 halbtaegig, 8 unveraendert" in out, out
    with engine.connect() as conn:
        assert _half_days(conn) == _expected()
        assert _other_columns(conn) == before


def test_backfill_as_non_superuser_owner_under_force_rls(owner_scratch):
    """Ohne ``SET LOCAL app.is_superadmin`` sähe die Eigentümerin unter FORCE
    RLS keine Zeile — die Migration liefe still durch und trüge nichts nach."""
    url, engine, role, owner_url = owner_scratch
    _alembic(url, "upgrade", BASE_REV)
    with engine.begin() as conn:
        _seed(conn)
        conn.execute(text(
            "DO $$ DECLARE r record; BEGIN "
            "FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP "
            f"EXECUTE format('ALTER TABLE %I OWNER TO %I', r.tablename, '{role}'); "
            "END LOOP; END $$"
        ))
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = :r"
        ), {"r": role}).scalar() is False
        assert dict(conn.execute(text(
            "SELECT c.relname, c.relrowsecurity AND c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY(:tables)"
        ), {"tables": ["absences", "users", "working_hours_changes", "reduced_days"]}).all()) == {
            "absences": True, "users": True, "working_hours_changes": True, "reduced_days": True}

    out = _alembic(owner_url, "upgrade", HEAD_REV)
    assert "3 ganztaegig, 3 halbtaegig" in out, out
    with engine.connect() as conn:  # Superuser: liest an RLS vorbei
        assert _half_days(conn) == _expected()
