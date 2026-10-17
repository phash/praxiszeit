"""Gesamtreview 1.20 (Parallelpfad zu Review-Fund 2): ``clock_in`` prüft
Duplikate auf dem GEKAPPTEN Beginn.

Einstempeln vor der Hülle schreibt den Beginn der Hülle (07:30 → 07:45, #201).
Wer nach einem Fehlstempel aus- und gleich wieder einstempelt, landet erneut
auf 07:45 — bis Gesamtreview 1.20 ohne jede Sonde: erst der Index
``uq_tenant_user_date_start`` schlug zu (IntegrityError → HTTP 500), der
Stempel ging verloren (§16). Ohne Blöcke dieselbe Kollision, wenn Aus- und
Einstempeln in dieselbe Minute fallen (Sekunden werden abgeschnitten).

Alle Geschwisterpfade antworten dort mit 409 (``create_time_entry``, beide
Bearbeiten-Routen, Admin-Anlegen, Antragsgenehmigung); ``clock_in`` jetzt auch,
mit einem Klartext, der sagt, wie es weitergeht.
"""
import datetime as dt
from datetime import time

import pytest

from app.models import TimeEntry
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON

import app.routers.time_entries as te


def _detail(hhmm):
    return (
        f"Einstempeln nicht möglich: Ein Zeiteintrag von heute beginnt bereits um "
        f"{hhmm}, und der neue Eintrag würde ebenfalls um {hhmm} beginnen. Bitte den "
        f"vorhandenen Eintrag in der Zeiterfassung bearbeiten oder nach {hhmm} "
        f"erneut einstempeln."
    )


@pytest.fixture
def clock(monkeypatch):
    """Friert „jetzt" auf Montag ``MON`` ein; Rückgabe: Setter für die Uhrzeit."""
    monkeypatch.setattr(te, "_today_local", lambda: MON)

    def at(hh, mm):
        monkeypatch.setattr(
            te, "_now_local",
            lambda: dt.datetime(MON.year, MON.month, MON.day, hh, mm, tzinfo=te.LOCAL_TZ),
        )
    return at


def _entries(db, user):
    db.expire_all()
    return (
        db.query(TimeEntry)
        .filter(TimeEntry.user_id == user.id)
        .order_by(TimeEntry.start_time)
        .all()
    )


def test_second_early_clock_in_is_409_not_500(_db_session, employee_user, employee_client, clock):
    """Sonde aus dem Review: K_BLOCKS (Hülle ab 07:45), ein → aus → früh wieder ein."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()

    clock(7, 30)
    r = employee_client.post("/api/time-entries/clock-in", json={})
    assert r.status_code == 201, r.text
    clock(7, 36)
    r = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0})
    assert r.status_code == 200, r.text

    clock(7, 40)
    r = employee_client.post("/api/time-entries/clock-in", json={})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == _detail("07:45")

    # Nichts geschrieben, nicht eingestempelt: der erste Eintrag steht unverändert.
    rows = _entries(_db_session, employee_user)
    assert len(rows) == 1
    assert rows[0].start_time == time(7, 45)
    assert rows[0].raw_start_time == time(7, 30)
    assert rows[0].end_time is not None
    status = employee_client.get("/api/time-entries/clock-status").json()
    assert status["is_clocked_in"] is False


def test_clock_in_exactly_on_hull_start_collides_too(_db_session, employee_user, employee_client, clock):
    """07:45 selbst ist nicht „vor der Hülle", landet aber auf demselben Beginn."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    clock(7, 30)
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    clock(7, 36)
    assert employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0}).status_code == 200

    clock(7, 45)
    r = employee_client.post("/api/time-entries/clock-in", json={})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == _detail("07:45")


def test_clock_in_after_the_named_minute_works(_db_session, employee_user, employee_client, clock):
    """Der Hinweis „nach 07:45 erneut einstempeln" stimmt: 07:46 geht durch."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    clock(7, 30)
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    clock(7, 36)
    assert employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0}).status_code == 200
    clock(7, 40)
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 409

    clock(7, 46)
    r = employee_client.post("/api/time-entries/clock-in", json={})
    assert r.status_code == 201, r.text
    starts = [e.start_time for e in _entries(_db_session, employee_user)]
    assert starts == [time(7, 45), time(7, 46)]


def test_same_minute_without_blocks_is_409(_db_session, employee_user, employee_client, clock):
    """Ohne Blöcke: ein, aus und wieder ein in derselben Minute."""
    clock(10, 0)
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    assert employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0}).status_code == 200

    r = employee_client.post("/api/time-entries/clock-in", json={})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == _detail("10:00")
    assert len(_entries(_db_session, employee_user)) == 1

    clock(10, 1)
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201


def test_entry_of_another_day_is_no_collision(_db_session, employee_user, employee_client, clock):
    """Die Sonde gilt dem heutigen Datum: gleicher Beginn an einem anderen Tag stört nicht."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    _db_session.add(TimeEntry(
        tenant_id=employee_user.tenant_id, user_id=employee_user.id,
        date=MON - dt.timedelta(days=7), start_time=time(7, 45), raw_start_time=time(7, 30),
        end_time=time(16, 0), break_minutes=30,
    ))
    _db_session.commit()
    clock(7, 30)
    r = employee_client.post("/api/time-entries/clock-in", json={})
    assert r.status_code == 201, r.text
