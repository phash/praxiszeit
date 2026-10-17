"""Spec 2026-10-08, 17.1 (Postgres-only): Migration 073 auf echtem PostgreSQL.

Läuft in einer EIGENEN Wegwerf-Datenbank auf demselben Server (``CREATE
DATABASE`` als Superuser) — die geteilte Test-DB wird nie herabgestuft.
Alembic läuft als Unterprozess über ``from alembic.config import main``
(CLAUDE.md: kein ``python -m alembic`` wegen cwd-Shadowing).

Geprüft: Backfill (zweiseitig, halboffen, invertiert, Sekunden, nur invertiert),
Verlaufszeilen, ``auto_closed``-Backfill, ``clamp_grace_minutes`` NULL,
Spaltentypen, Diagnose-Ausgabe, Byte-Identität der Bestandsspalten
(``time_entries``, ``working_hours_changes`` vollständig, ``users`` ohne die
Fensterspalten; nach jedem der drei Schritte), Downgrade aus der HÜLLE inkl.
Diagnose, Round-Trip 073 → 072 → 073 — und der Backfill als Eigentümerin OHNE
Superuser-Recht unter FORCE RLS (die Rolle ``praxiszeit`` ist in Docker, CI und
auf der Prod-Kopie Superuser und umgeht RLS; nur dieser Lauf sieht, ob
``SET LOCAL app.is_superadmin`` greift).

Eingehängt in ``scripts/local-ci.sh`` Schritt 2 und den PostgreSQL-Schritt von
``.github/workflows/cross-tenant-ci.yml`` (im SQLite-Schritt per ``--ignore``).
"""
import json
import os
import secrets
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import time
from pathlib import Path

import pytest
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_URL or not ADMIN_URL.startswith("postgresql"):
    pytest.skip(
        "test_073_migration_pg.py braucht PostgreSQL (ADMIN_DB_URL / DATABASE_URL_MIGRATIONS)",
        allow_module_level=True,
    )

BACKEND = Path(__file__).resolve().parents[1]
TENANT = "00000000-0000-0000-0000-000000000001"  # legt Migration 027 an
U = {name: str(uuid.UUID(int=0x1111_0000_0000_4000_8000_0000_0000_0000 + i))
     for i, name in enumerate(("zwei", "halbende", "invers", "sek", "nurinvers", "ohne", "mehr"), 1)}
E = {name: str(uuid.UUID(int=0x3333_0000_0000_4000_8000_0000_0000_0000 + i))
     for i, name in enumerate(("autoclose", "korrigiert", "ohne_protokoll", "mehr",
                               "nachgekappt", "nachgekappt_echt"), 1)}
WINDOW_COLUMNS = [f"scheduled_{k}_{d}" for d in ("monday", "tuesday", "wednesday", "thursday", "friday")
                  for k in ("start", "end")]
# Bestandstabellen des Vergleichs (Spec 17.1) und die Spalten, die dabei
# herausfallen: die Fenster prüft der Test einzeln, sie ändern sich gewollt.
COMPARED_TABLES = {"time_entries": (), "working_hours_changes": (), "users": tuple(WINDOW_COLUMNS)}


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


def _bestand(conn) -> dict:
    """Spaltenlisten der Bestandstabellen im Stand 072, in der Reihenfolge der
    Tabelle aus ``information_schema`` (nicht von Hand: eine vergessene Spalte
    wäre genau die, die ein Fehler verändert)."""
    lists = {}
    for table, skip in COMPARED_TABLES.items():
        names = [c for (c,) in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position"
        ), {"t": table}).all() if c not in skip]
        lists[table] = ", ".join(f'"{c}"' for c in names)
    return lists


def _snapshot(conn, lists: dict) -> dict:
    return {table: _md5(conn, f"SELECT {cols} FROM {table}") for table, cols in lists.items()}


@contextmanager
def _scratch_database():
    name = f"pz073_{uuid.uuid4().hex[:10]}"
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


@pytest.fixture(scope="module")
def scratch():
    with _scratch_database() as db:
        yield db


@pytest.fixture
def owner_scratch():
    """Wegwerf-Datenbank plus eine Rolle OHNE Superuser- und BYPASSRLS-Recht.

    Die Rolle ist clusterweit, deshalb räumt der Teardown in dieser Reihenfolge
    ab: erst die Datenbank (darin liegt alles, was ihr gehört), dann die Rolle."""
    role = f"pz073_owner_{uuid.uuid4().hex[:10]}"
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


def _user(conn, key, **window):
    cols = ["id", "tenant_id", "username", "email", "password_hash", "first_name",
            "last_name", "role", "weekly_hours", "vacation_days", "is_active", *window]
    params = {"id": U[key], "tenant_id": TENANT, "username": key, "email": f"{key}@x.de",
              "password_hash": "h", "first_name": key, "last_name": "T", "role": "EMPLOYEE",
              "weekly_hours": 40, "vacation_days": 30, "is_active": True, **window}
    conn.execute(text(
        f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"
    ), params)


def _seed_072(conn):
    _user(conn, "zwei", **{f"scheduled_{k}_{d}": (time(7, 30) if k == "start" else time(16, 30))
                           for d in ("monday", "tuesday", "wednesday", "thursday") for k in ("start", "end")},
          scheduled_start_friday=time(7, 30))
    _user(conn, "halbende", scheduled_end_monday=time(16, 30))
    _user(conn, "invers", scheduled_start_monday=time(17, 0), scheduled_end_monday=time(8, 0),
          scheduled_start_tuesday=time(8, 0), scheduled_end_tuesday=time(16, 0))
    _user(conn, "sek", scheduled_start_monday=time(7, 30, 45), scheduled_end_monday=time(16, 30))
    _user(conn, "nurinvers", scheduled_start_wednesday=time(17, 0), scheduled_end_wednesday=time(8, 0))
    _user(conn, "ohne")
    _user(conn, "mehr", scheduled_start_monday=time(8, 0), scheduled_end_monday=time(18, 0))
    for i, (who, day) in enumerate((("zwei", "2026-01-01"), ("zwei", "2026-06-01"), ("nurinvers", "2026-01-01")), 1):
        _history_row(conn, i, who, day)
    # "nachgekappt": 072-Auto-Close (23:59), danach das ganze Formular gespeichert →
    # 072 kappte die 23:59 auf das Fensterende und hielt sie als Rohende fest
    # (dieselbe Form wie der neue Auto-Close). "nachgekappt_echt": Kontrolle, echtes
    # Ende 19:00 außerhalb des Fensters.
    for key, who, day, end, raw_end in (("autoclose", "zwei", "2026-06-01", time(23, 59), None),
                                        ("korrigiert", "zwei", "2026-06-02", time(17, 0), None),
                                        ("ohne_protokoll", "zwei", "2026-06-03", time(23, 59), None),
                                        ("mehr", "mehr", "2026-06-01", time(18, 0), None),
                                        ("nachgekappt", "zwei", "2026-06-08", time(16, 45), time(23, 59)),
                                        ("nachgekappt_echt", "zwei", "2026-06-09", time(16, 45), time(19, 0))):
        _entry(conn, key, who, day, end, raw_end)
    for key in ("autoclose", "korrigiert", "nachgekappt", "nachgekappt_echt"):
        _auto_close_log(conn, key)


def _history_row(conn, i, who, day):
    conn.execute(text(
        "INSERT INTO working_hours_changes (id, tenant_id, user_id, effective_from, weekly_hours) "
        "VALUES (:id, :t, :u, :d, 40)"
    ), {"id": str(uuid.UUID(int=0x2222_0000_0000_4000_8000_0000_0000_0000 + i)),
        "t": TENANT, "u": U[who], "d": day})


def _entry(conn, key, who, day, end, raw_end=None):
    conn.execute(text(
        "INSERT INTO time_entries (id, tenant_id, user_id, date, start_time, end_time, raw_end_time, break_minutes) "
        "VALUES (:id, :t, :u, :d, :s, :e, :re, 0)"
    ), {"id": E[key], "t": TENANT, "u": U[who], "d": day, "s": time(8, 0), "e": end, "re": raw_end})


def _auto_close_log(conn, key):
    conn.execute(text(
        "INSERT INTO time_entry_audit_logs (tenant_id, time_entry_id, user_id, changed_by, action, source, new_end_time) "
        "VALUES (:t, :e, :u, :u, 'update', 'auto_close', :end)"
    ), {"t": TENANT, "e": E[key], "u": U["zwei"], "end": time(23, 59)})


def _blocks(conn, key):
    return conn.execute(text("SELECT work_blocks FROM users WHERE id = :id"), {"id": U[key]}).scalar()


def _one(start, end):
    return {"blocks": [{"start": start, "end": end}], "pause_minutes": None}


EMPTY = {"blocks": [], "pause_minutes": None}


def test_073_upgrade_downgrade_round_trip(scratch):
    url, engine = scratch
    _alembic(url, "upgrade", "072_cr_sunday_reason")
    with engine.begin() as conn:
        _seed_072(conn)
    with engine.connect() as conn:
        bestand = _bestand(conn)
        before = _snapshot(conn, bestand)

    out = _alembic(url, "upgrade", "073_work_blocks")
    assert "*** HINWEIS (Migration 073) ***" in out
    assert "übernommen: 5 Konten, 2 Verlaufszeilen." in out
    assert "halboffen: Fr ab 07:30 → Ende 23:59 (Kappung unverändert)" in out
    assert "halboffen: Mo bis 16:30 → Beginn 00:00 (Kappung unverändert)" in out
    assert "Sekunden abgeschnitten: Mo 07:30:45 → 07:30" in out
    assert "nicht übernommen: Mo 17:00–08:00" in out
    assert "nicht übernommen: Mi 17:00–08:00" in out
    # Spec 17.1: "nurinvers" (nur invertierte Fenster) zählt nicht als erwartetes
    # Konto. Der einzige Lauf, in dem die Zählprobe überhaupt rechnet — die
    # SQLite-Tests prüfen nur die Helfer und rufen ``upgrade()`` nie auf.
    assert "Abweichung" not in out

    with engine.connect() as conn:
        assert _blocks(conn, "zwei") == [_one("07:30", "16:30")] * 4 + [_one("07:30", "23:59")]
        assert _blocks(conn, "halbende") == [_one("00:00", "16:30")] + [EMPTY] * 4
        assert _blocks(conn, "invers") == [EMPTY, _one("08:00", "16:00")] + [EMPTY] * 3
        assert _blocks(conn, "sek") == [_one("07:30", "16:30")] + [EMPTY] * 4
        assert _blocks(conn, "nurinvers") is None
        assert _blocks(conn, "ohne") is None
        wh = conn.execute(text(
            "SELECT user_id::text, blocks FROM working_hours_changes ORDER BY user_id, effective_from"
        )).all()
        assert [(u, b is None) for u, b in wh] == [(U["zwei"], False), (U["zwei"], False), (U["nurinvers"], True)]
        assert all(b == _blocks(conn, "zwei") for u, b in wh if u == U["zwei"])
        flags = dict(conn.execute(text("SELECT id::text, auto_closed FROM time_entries")).all())
        assert flags == {E["autoclose"]: True, E["korrigiert"]: False,
                         E["ohne_protokoll"]: False, E["mehr"]: False,
                         E["nachgekappt"]: True, E["nachgekappt_echt"]: False}
        assert conn.execute(text(
            "SELECT count(*) FROM time_entries WHERE clamp_grace_minutes IS NOT NULL "
            "OR uncredited_minutes <> 0 OR credit_override"
        )).scalar() == 0
        columns = {(t, c): (d, n, dflt) for t, c, d, n, dflt in conn.execute(text(
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema = 'public'"
        )).all()}
        assert not [c for (t, c) in columns if t == "users" and c.startswith("scheduled_")]
        assert columns[("users", "work_blocks")][:2] == ("jsonb", "YES")
        assert columns[("working_hours_changes", "blocks")][:2] == ("jsonb", "YES")
        assert columns[("time_entries", "uncredited_minutes")] == ("integer", "NO", "0")
        assert columns[("time_entries", "credit_override")] == ("boolean", "NO", "false")
        assert columns[("time_entries", "auto_closed")] == ("boolean", "NO", "false")
        assert columns[("time_entries", "clamp_grace_minutes")][:2] == ("integer", "YES")
        assert columns[("change_requests", "request_credit_override")] == ("boolean", "NO", "false")
        assert columns[("change_requests", "original_uncredited_minutes")][:2] == ("integer", "YES")
        assert _snapshot(conn, bestand) == before
    with engine.connect() as conn:
        first_upgrade = {k: _blocks(conn, k) for k in U}

    # Mehrblock-Stand wie nach PR3 simulieren, dazu Lücken-, Anerkennungs- und Antragsdaten.
    multi = [{"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}],
              "pause_minutes": 0}] + [{"blocks": [], "pause_minutes": 0}] * 4
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET work_blocks = CAST(:j AS JSONB) WHERE id = :id"),
                     {"j": json.dumps(multi), "id": U["mehr"]})
        conn.execute(text("UPDATE time_entries SET uncredited_minutes = 150, credit_override = true "
                          "WHERE id = :id"), {"id": E["mehr"]})
        conn.execute(text(
            "INSERT INTO change_requests (tenant_id, user_id, request_type, status, reason, request_credit_override) "
            "VALUES (:t, :u, 'update', 'pending', 'x', true)"
        ), {"t": TENANT, "u": U["mehr"]})

    out = _alembic(url, "downgrade", "072_cr_sunday_reason")
    assert "*** HINWEIS (Migration 073, Downgrade) ***" in out
    assert ("mehr (Mandant 0000…0001): Mo 08:00–12:00 + 15:00–18:00 → Fenster 08:00–18:00 "
            "(wieder angerechnete Lücken: 12:00–15:00)") in out
    assert "mehr (Mandant 0000…0001): 1 Eintrag, zusammen 2,50 h" in out
    # Mit Zeilenende: die Zeile für nicht angerechnete Zeit beginnt genauso.
    assert "Anerkannte Einträge (das Kennzeichen entfällt):\n  - mehr (Mandant 0000…0001): 1 Eintrag\n" in out
    assert "1 offener Antrag „Anrechnung beantragen“ wird" in out
    with engine.connect() as conn:
        windows = {row[0]: row[1:] for row in conn.execute(text(
            f"SELECT username, {', '.join(WINDOW_COLUMNS)} FROM users ORDER BY username"
        )).all()}
        assert windows["mehr"][:2] == (time(8, 0), time(18, 0))           # Hülle, nicht 12:00
        assert windows["zwei"][8:10] == (time(7, 30), None)                 # Platzhalter 23:59 → NULL
        assert windows["halbende"][:2] == (None, time(16, 30))              # Platzhalter 00:00 → NULL
        assert windows["sek"][:2] == (time(7, 30), time(16, 30))            # Sekunden bleiben weg
        assert windows["invers"][:4] == (None, None, time(8, 0), time(16, 0))
        remaining = {c for (c,) in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name IN "
            "('work_blocks', 'blocks', 'uncredited_minutes', 'credit_override', 'auto_closed', "
            "'clamp_grace_minutes', 'request_credit_override', 'original_uncredited_minutes')"
        )).all()}
        assert remaining == set()
        assert _snapshot(conn, bestand) == before

    _alembic(url, "upgrade", "073_work_blocks")
    with engine.connect() as conn:
        for key in ("zwei", "halbende", "sek", "ohne", "nurinvers"):
            assert _blocks(conn, key) == first_upgrade[key], key
        assert _blocks(conn, "mehr") == [_one("08:00", "18:00")] + [EMPTY] * 4
        assert _snapshot(conn, bestand) == before


RLS_TABLES = ("users", "working_hours_changes", "time_entries", "time_entry_audit_logs")


def test_073_backfill_as_owner_under_force_rls(owner_scratch):
    """Spec 5.2 Schritt 2 / 17.1: „Backfill als praxiszeit unter FORCE RLS trifft
    alle Zeilen". Die Migrationsrolle besitzt die Tabellen, ist aber KEIN
    Superuser — dann gilt FORCE RLS auch für sie, und ohne
    ``SET LOCAL app.is_superadmin`` sähe der Backfill keine einzige Zeile.

    Zugesichert wird die ZÄHLUNG, nicht das Fehlen der Zeile „Abweichung …
    (RLS?)": die Zählprobe vergleicht aktualisierte mit gelesenen Konten, und
    RLS filtert das Lesen genauso wie das Schreiben — sie meldet bei diesem
    Fehlerbild „0 Konten" ohne jede Abweichung."""
    url, engine, role, owner_url = owner_scratch
    _alembic(url, "upgrade", "072_cr_sunday_reason")
    with engine.begin() as conn:
        _user(conn, "zwei", scheduled_start_monday=time(8, 0), scheduled_end_monday=time(16, 0))
        _history_row(conn, 1, "zwei", "2026-01-01")
        _entry(conn, "autoclose", "zwei", "2026-06-01", time(23, 59))
        _auto_close_log(conn, "autoclose")
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
            "WHERE n.nspname = 'public' AND c.relname IN :tables"
        ).bindparams(bindparam("tables", expanding=True)),
            {"r": role, "tables": list(RLS_TABLES)}).all()) == {t: True for t in RLS_TABLES}

    out = _alembic(owner_url, "upgrade", "073_work_blocks")
    assert "übernommen: 1 Konto, 1 Verlaufszeile." in out

    with engine.connect() as conn:  # Superuser: liest an RLS vorbei
        assert _blocks(conn, "zwei") == [_one("08:00", "16:00")] + [EMPTY] * 4
        assert conn.execute(text(
            "SELECT blocks IS NOT NULL FROM working_hours_changes WHERE user_id = :u"
        ), {"u": U["zwei"]}).scalars().all() == [True]
        assert conn.execute(text(
            "SELECT auto_closed FROM time_entries WHERE id = :id"
        ), {"id": E["autoclose"]}).scalar() is True
