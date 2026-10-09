"""Spec 2026-10-08, 17.1 (Postgres-only): Migration 073 auf echtem PostgreSQL.

Läuft in einer EIGENEN Wegwerf-Datenbank auf demselben Server (``CREATE
DATABASE`` als Superuser) — die geteilte Test-DB wird nie herabgestuft.
Alembic läuft als Unterprozess über ``from alembic.config import main``
(CLAUDE.md: kein ``python -m alembic`` wegen cwd-Shadowing).

Geprüft: Backfill (zweiseitig, halboffen, invertiert, Sekunden, nur invertiert),
Verlaufszeilen, ``auto_closed``-Backfill, ``clamp_grace_minutes`` NULL,
Spaltentypen, Diagnose-Ausgabe, Byte-Identität der Bestandsspalten,
Downgrade aus der HÜLLE inkl. Diagnose, Round-Trip 073 → 072 → 073.

Eingehängt in ``scripts/local-ci.sh`` Schritt 2 und den PostgreSQL-Schritt von
``.github/workflows/cross-tenant-ci.yml`` (im SQLite-Schritt per ``--ignore``).
"""
import json
import os
import subprocess
import sys
import uuid
from datetime import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
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
OLD_TE = "id, user_id, date, start_time, end_time, break_minutes, raw_start_time, raw_end_time, note"
OLD_WH = "id, user_id, effective_from, weekly_hours, use_daily_schedule, work_days_per_week"


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


@pytest.fixture(scope="module")
def scratch():
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
        conn.execute(text(
            "INSERT INTO working_hours_changes (id, tenant_id, user_id, effective_from, weekly_hours) "
            "VALUES (:id, :t, :u, :d, 40)"
        ), {"id": str(uuid.UUID(int=0x2222_0000_0000_4000_8000_0000_0000_0000 + i)),
            "t": TENANT, "u": U[who], "d": day})
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
        conn.execute(text(
            "INSERT INTO time_entries (id, tenant_id, user_id, date, start_time, end_time, raw_end_time, break_minutes) "
            "VALUES (:id, :t, :u, :d, :s, :e, :re, 0)"
        ), {"id": E[key], "t": TENANT, "u": U[who], "d": day, "s": time(8, 0), "e": end, "re": raw_end})
    for key in ("autoclose", "korrigiert", "nachgekappt", "nachgekappt_echt"):
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
        te_before = _md5(conn, f"SELECT {OLD_TE} FROM time_entries")
        wh_before = _md5(conn, f"SELECT {OLD_WH} FROM working_hours_changes")

    out = _alembic(url, "upgrade", "073_work_blocks")
    assert "*** HINWEIS (Migration 073) ***" in out
    assert "übernommen: 5 Konten, 2 Verlaufszeilen." in out
    assert "halboffen: Fr ab 07:30 → Ende 23:59 (Kappung unverändert)" in out
    assert "halboffen: Mo bis 16:30 → Beginn 00:00 (Kappung unverändert)" in out
    assert "Sekunden abgeschnitten: Mo 07:30:45 → 07:30" in out
    assert "nicht übernommen: Mo 17:00–08:00" in out
    assert "nicht übernommen: Mi 17:00–08:00" in out

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
        assert _md5(conn, f"SELECT {OLD_TE} FROM time_entries") == te_before
        assert _md5(conn, f"SELECT {OLD_WH} FROM working_hours_changes") == wh_before
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
        assert _md5(conn, f"SELECT {OLD_TE} FROM time_entries") == te_before

    _alembic(url, "upgrade", "073_work_blocks")
    with engine.connect() as conn:
        for key in ("zwei", "halbende", "sek", "ohne", "nurinvers"):
            assert _blocks(conn, key) == first_upgrade[key], key
        assert _blocks(conn, "mehr") == [_one("08:00", "18:00")] + [EMPTY] * 4
        assert _md5(conn, f"SELECT {OLD_TE} FROM time_entries") == te_before
