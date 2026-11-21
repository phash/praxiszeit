"""Plan 2026-11-21 Task 9 (PostgreSQL-only): Sammel-Anerkennen unter echten
Zeilensperren.

Zwei Sammelaufrufe auf dieselben Einträge — in umgekehrter Reihenfolge der IDs
im Body — laufen gleichzeitig. Erwartet: kein Deadlock (40P01). Der erste
erkennt alle an, der zweite wartet an der Ankersperre (P5) und meldet danach
``already``. Dazu: ein Fehler im zweiten Eintrag rollt den ersten auf echter
PostgreSQL zurück (alles oder nichts), und die Kollision mit einem belegten
Beginn ist ein sauberes 409 statt eines IntegrityError gegen den Unique-Index.

Muster: ``test_reclamp_concurrency.py`` (echte Endpunkt-Funktionen,
``SessionLocal`` + ``set_tenant_context``, eigener Mandant)."""
from __future__ import annotations

import os
import threading
import time as time_module
import uuid
from datetime import date, time

import pytest
from sqlalchemy import create_engine, text

APP_DB_URL = os.environ.get("APP_DB_URL") or os.environ.get("DATABASE_URL")
ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not APP_DB_URL or not ADMIN_DB_URL or not ADMIN_DB_URL.startswith("postgresql"):
    pytest.skip("test_credit_override_bulk_pg.py braucht PostgreSQL (APP_DB_URL + ADMIN_DB_URL)",
                allow_module_level=True)

from fastapi import HTTPException  # noqa: E402

from app.database import SessionLocal, set_tenant_context  # noqa: E402
from app.models import TimeEntry, TimeEntryAuditLog, User  # noqa: E402
from app.routers import admin_time_entries  # noqa: E402
from app.schemas.time_entry import BulkCreditOverrideRequest  # noqa: E402
from app.services import credit_override_service  # noqa: E402

TENANT_ID = uuid.UUID("ccccccc9-0000-4000-8000-000000000001")
USER_ID = uuid.UUID("ccccccc9-0000-4000-8000-000000000100")
ADMIN_ID = uuid.UUID("ccccccc9-0000-4000-8000-000000000200")
DAY = date(2099, 6, 1)  # Montag
LOW_ID = uuid.UUID("ccccccc9-0000-4000-8000-00000000e001")
HIGH_ID = uuid.UUID("ccccccc9-0000-4000-8000-00000000e002")


@pytest.fixture(scope="module")
def admin_engine():
    eng = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    yield eng
    eng.dispose()


def _wipe(conn):
    for table in ("time_entry_audit_logs", "time_entries", "absences"):
        conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": str(TENANT_ID)})


@pytest.fixture(scope="module")
def seed(admin_engine):
    conn = admin_engine.connect()
    _wipe(conn)
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("INSERT INTO tenants (id, name, slug, is_active, mode) "
                      "VALUES (:id, 'Sammel Anerkennen', 'sammel-anerkennen', true, 'multi')"),
                 {"id": str(TENANT_ID)})
    for uid, name, role in ((USER_ID, "bulk_user", "EMPLOYEE"), (ADMIN_ID, "bulk_admin", "ADMIN")):
        conn.execute(text("""
            INSERT INTO users (id, tenant_id, username, email, password_hash, first_name, last_name, role,
                               weekly_hours, vacation_days, work_days_per_week, is_active)
            VALUES (:id, :tid, :u, :e, 'not-real', 'Petra', 'Schulz', :role, 40, 30, 5, true)
        """), {"id": str(uid), "tid": str(TENANT_ID), "u": name, "e": f"{name}@test.local", "role": role})
    yield
    _wipe(conn)
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})
    conn.close()


@pytest.fixture
def fresh(seed, admin_engine):
    conn = admin_engine.connect()
    _wipe(conn)
    conn.close()
    yield


def _with_session(fn):
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        return fn(session)
    finally:
        session.close()


def _add(entry_id, start, end, **kw):
    """Gekappter Eintrag wie nach einer Neukappung (Rohstempel daneben)."""
    def run(s):
        s.add(TimeEntry(id=entry_id, tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=start,
                        end_time=end, break_minutes=0, clamp_grace_minutes=15, **kw))
        s.commit()
    _with_session(run)
    return entry_id


def _bulk(session, ids):
    admin = session.query(User).filter(User.id == ADMIN_ID).first()
    return admin_time_entries.admin_bulk_credit_override(
        user_id=str(USER_ID), body=BulkCreditOverrideRequest(entry_ids=list(ids)),
        db=session, current_user=admin)


def _entries():
    return _with_session(lambda s: {
        e.id: (e.credit_override, e.start_time, e.end_time)
        for e in s.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID).all()})


def _override_logs():
    return _with_session(lambda s: s.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == TENANT_ID,
        TimeEntryAuditLog.source == credit_override_service.CREDIT_OVERRIDE_SOURCE).count())


def test_parallel_bulk_calls_do_not_deadlock(fresh, monkeypatch):
    """A hält nach dem ersten Anerkennen die Sperren noch 0,8 s; B startet in
    diesem Fenster mit den IDs in umgekehrter Reihenfolge. B wartet an der
    Ankersperre, sieht danach A's Commit und meldet beide als ``already``."""
    a_id = _add(LOW_ID, time(7, 45), time(12), raw_start_time=time(7), raw_end_time=time(12),
                uncredited_minutes=45)
    b_id = _add(HIGH_ID, time(13), time(18, 15), raw_start_time=time(13), raw_end_time=time(19),
                uncredited_minutes=45)

    holding = threading.Event()
    real_apply = credit_override_service.apply_credit_override
    first = threading.Lock()

    def slow_apply(*args, **kwargs):
        result = real_apply(*args, **kwargs)
        if first.acquire(blocking=False):  # nur der allererste Aufruf (Thread A)
            holding.set()
            time_module.sleep(0.8)
        return result

    monkeypatch.setattr(credit_override_service, "apply_credit_override", slow_apply)
    results: dict = {}

    def thread_a():
        try:
            results["a"] = _with_session(lambda s: _bulk(s, [a_id, b_id]))
        except Exception as exc:  # pragma: no cover — Fehler sichtbar machen
            results["a_error"] = repr(exc)

    def thread_b():
        holding.wait(timeout=5)
        results["b_start"] = time_module.monotonic()
        try:
            results["b"] = _with_session(lambda s: _bulk(s, [b_id, a_id]))
            results["b_done"] = time_module.monotonic()
        except Exception as exc:  # pragma: no cover
            results["b_error"] = repr(exc)

    ta, tb = threading.Thread(target=thread_a), threading.Thread(target=thread_b)
    ta.start(); tb.start(); ta.join(timeout=30); tb.join(timeout=30)

    assert "a_error" not in results and "b_error" not in results, results
    assert (results["a"].recognized, results["a"].already) == (2, 0)
    assert (results["b"].recognized, results["b"].already) == (0, 2)
    # B stand an der Ankersperre, bis A committet hatte (A schläft 0,8 s darin).
    # Nicht gegen ``a_done`` vergleichen: A rechnet nach dem Commit noch die Warnungen.
    assert results["b_done"] - results["b_start"] >= 0.5, results
    got = _entries()
    assert got[a_id] == (True, time(7), time(12))
    assert got[b_id] == (True, time(13), time(19))
    assert _override_logs() == 2   # B schreibt keine zweite Zeile


def test_failure_rolls_back_on_postgres(fresh):
    """Alles oder nichts auf echter PostgreSQL: der erste Eintrag (niedrigere
    ID) ist schon anerkannt und geflusht, wenn der zweite (automatisch
    geschlossen) scheitert — nach dem 400 ist nichts gespeichert."""
    good = _add(LOW_ID, time(7, 45), time(12), raw_start_time=time(7), raw_end_time=time(12),
                uncredited_minutes=45)
    closed = _add(HIGH_ID, time(13), time(18, 15), raw_end_time=time(23, 59), auto_closed=True)

    def run(s):
        with pytest.raises(HTTPException) as exc:
            _bulk(s, [closed, good])
        return exc.value

    err = _with_session(run)
    assert err.status_code == 400
    assert err.detail == f"{DAY.strftime('%d.%m.%Y')}: {credit_override_service.AUTO_CLOSED_DETAIL}"
    got = _entries()
    assert got[good] == (False, time(7, 45), time(12))
    assert got[closed][0] is False
    assert _override_logs() == 0


def test_start_collision_is_409_not_integrity_error(fresh):
    """Anerkennen legte den Beginn auf einen schon belegten Beginn desselben
    Tages: 409 mit ``start_taken_detail`` vor dem UPDATE, kein IntegrityError
    gegen ``uq_tenant_user_date_start`` (→ 500)."""
    _add(LOW_ID, time(7), time(7, 30))
    clamped = _add(HIGH_ID, time(7, 45), time(12), raw_start_time=time(7), raw_end_time=time(12),
                   uncredited_minutes=45)

    def run(s):
        with pytest.raises(HTTPException) as exc:
            _bulk(s, [clamped])
        return exc.value

    err = _with_session(run)
    assert err.status_code == 409
    assert err.detail == f"{DAY.strftime('%d.%m.%Y')}: {credit_override_service.start_taken_detail(time(7))}"
    assert _entries()[clamped] == (False, time(7, 45), time(12))
