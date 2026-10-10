"""Spec 2026-10-08, 8.4 / 11.1 / 14 (PR2): /clock-status liefert die Blöcke von
heute und den Puffer, mit dem das Ausstempeln kappen wird — in jedem Zweig."""
import datetime as dt
from datetime import date, time

import app.routers.time_entries as te
from app.models import PublicHoliday, TimeEntry
from app.models.system_setting import SystemSetting
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON, block_week

TUE = date(2026, 6, 2)
SAT = date(2026, 6, 6)
WEEK = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "13:00")])
MON_BLOCKS = [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}]


def _at(monkeypatch, d, hh=10):
    monkeypatch.setattr(te, "_today_local", lambda: d)
    # Zeitzonenbehaftet wie ``now_local`` — der eingestempelte Zweig rechnet
    # ``now - start_dt`` gegen ein LOCAL_TZ-Datum.
    monkeypatch.setattr(
        te, "_now_local", lambda: dt.datetime(d.year, d.month, d.day, hh, 0, tzinfo=te.LOCAL_TZ),
    )


def _grace(db, minutes):
    db.add(SystemSetting(key="work_window_grace_minutes", value=str(minutes), tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def _status(client):
    r = client.get("/api/time-entries/clock-status")
    assert r.status_code == 200, r.text
    return r.json()


def test_not_clocked_in_returns_blocks_and_tenant_grace(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = WEEK
    _db_session.commit()
    _grace(_db_session, 10)
    _at(monkeypatch, MON)
    body = _status(employee_client)
    assert body["is_clocked_in"] is False
    assert body["blocks_today"] == MON_BLOCKS
    assert body["grace_minutes"] == 10


def test_clocked_in_uses_the_stored_grace_of_the_open_entry(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = WEEK
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=None, break_minutes=0, clamp_grace_minutes=15))
    _db_session.commit()
    _grace(_db_session, 0)
    _at(monkeypatch, MON, 13)
    body = _status(employee_client)
    assert body["is_clocked_in"] is True
    assert body["grace_minutes"] == 15        # E80: der Puffer, mit dem clock_out kappen wird
    assert body["blocks_today"] == MON_BLOCKS
    assert body["current_entry"]["uncredited_minutes"] == 0
    assert body["current_entry"]["clamp_grace_minutes"] == 15


def test_clocked_in_without_stored_grace_falls_back_to_tenant_grace(
    _db_session, employee_user, employee_client, monkeypatch,
):
    """E80: ein offener Eintrag ohne gespeicherten Puffer (Bestand vor 073)
    wird beim Ausstempeln mit dem aktuellen Mandanten-Puffer gekappt."""
    employee_user.work_blocks = WEEK
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=None, break_minutes=0))
    _db_session.commit()
    _grace(_db_session, 5)
    _at(monkeypatch, MON, 13)
    body = _status(employee_client)
    assert body["is_clocked_in"] is True
    assert body["grace_minutes"] == 5


def test_stale_branch_closes_and_still_reports_today(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = WEEK
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=None, break_minutes=0, clamp_grace_minutes=15))
    _db_session.commit()
    _at(monkeypatch, TUE)
    body = _status(employee_client)
    assert body["is_clocked_in"] is False
    assert body["blocks_today"] == [{"start": "08:00", "end": "13:00"}]
    assert body["grace_minutes"] == 15        # kein offener Eintrag mehr → Mandanten-Puffer (Default)


def test_stale_branch_reports_tenant_grace_not_the_closed_entry(
    _db_session, employee_user, employee_client, monkeypatch,
):
    """Nach dem Stale-Auto-Close gibt es keinen offenen Eintrag mehr — der
    Puffer des geschlossenen Eintrags von gestern darf nicht durchsickern."""
    employee_user.work_blocks = WEEK
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=None, break_minutes=0, clamp_grace_minutes=30))
    _db_session.commit()
    _grace(_db_session, 10)
    _at(monkeypatch, TUE)
    body = _status(employee_client)
    assert body["is_clocked_in"] is False
    assert body["grace_minutes"] == 10


def test_no_blocks_on_saturday_and_without_hour_tracking(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = WEEK
    _db_session.commit()
    _at(monkeypatch, SAT)
    assert _status(employee_client)["blocks_today"] == []
    employee_user.track_hours = False
    _db_session.commit()
    _at(monkeypatch, MON)
    assert _status(employee_client)["blocks_today"] == []


def test_no_blocks_on_a_holiday(_db_session, employee_user, employee_client, monkeypatch):
    """#484: an einem Feiertag des Mandanten hat der Tag kein Soll und keine Blöcke."""
    employee_user.work_blocks = WEEK
    _db_session.add(PublicHoliday(tenant_id=DEFAULT_TENANT_ID, date=MON, name="Testfeiertag", year=MON.year))
    _db_session.commit()
    invalidate_holiday_cache()  # F-034: ein früherer Test kann 2026 ohne Feiertag gecacht haben
    try:
        _at(monkeypatch, MON)
        assert _status(employee_client)["blocks_today"] == []
    finally:
        invalidate_holiday_cache()


def test_no_blocks_without_work_blocks(_db_session, employee_user, employee_client, monkeypatch):
    """Personen ohne hinterlegte Blöcke: leere Liste, Puffer trotzdem gesetzt."""
    _at(monkeypatch, MON)
    body = _status(employee_client)
    assert body["blocks_today"] == []
    assert body["grace_minutes"] == 15
