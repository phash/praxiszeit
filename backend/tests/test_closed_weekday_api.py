"""Kundenfall 2026-10-30 über die API: Arbeitszeit ab Stichtag von „Mo 07:30–13:00
+ 15:00–18:00" auf „Di 07:30–13:00, Do 15:00–18:00" umstellen. Danach zählt
Arbeit am Montag erst nach Anerkennung; das Frontend erfährt den Tag ohne
Blöcke über ``blockless_workday`` (``/clock-status``, ``/day-blocks``)."""
from datetime import date, datetime, time

import pytest

import app.routers.time_entries as te
from app.middleware.auth import require_admin
from app.services import timezone_service, work_window_service as wws
from tests.test_endpoints import test_app
from tests.wh_change_helpers import add_row, admin_client, freeze
from tests.work_blocks_fixtures import block_week

OLD_WEEK = block_week(mon=[("07:30", "13:00"), ("15:00", "18:00")])
NEW_WEEK = block_week(tue=[("07:30", "13:00")], thu=[("15:00", "18:00")])
CHANGE_DAY = date(2026, 10, 8)     # Do — Änderung wird eingetragen
EFFECTIVE = date(2026, 10, 12)     # Mo — neue Zeiten gelten ab hier
NEXT_MON = date(2026, 10, 19)
NEXT_TUE = date(2026, 10, 20)


def _at(monkeypatch, d, at=time(18, 0)):
    freeze(monkeypatch, d, at)
    monkeypatch.setattr(te, "_now_local", lambda: datetime.combine(d, at, tzinfo=timezone_service.LOCAL_TZ))


@pytest.fixture
def switched(db, test_user, test_admin, monkeypatch):
    add_row(db, test_user, date(2026, 1, 1), week=OLD_WEEK)
    _at(monkeypatch, CHANGE_DAY)
    admin = admin_client(db, test_admin)
    resp = admin.post(f"/api/admin/users/{test_user.id}/working-hours-changes",
                      json={"effective_from": EFFECTIVE.isoformat(), "blocks": NEW_WEEK})
    test_app.dependency_overrides.clear()
    assert resp.status_code == 201, resp.text
    employee = admin_client(db, test_user)
    del test_app.dependency_overrides[require_admin]
    yield employee
    test_app.dependency_overrides.clear()


def _create(client, d, start, end):
    resp = client.post("/api/time-entries", json={
        "date": d.isoformat(), "start_time": start, "end_time": end, "break_minutes": 0})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_monday_after_the_switch_credits_nothing(switched, monkeypatch):
    _at(monkeypatch, NEXT_MON)
    body = _create(switched, NEXT_MON, "07:30", "13:00")
    assert float(body["net_hours"]) == 0.0
    assert any(wws.CLOSED_DAY_TEXT in w and wws.EMPLOYEE_CREDIT_HINT in w for w in body["warnings"]), body


def test_tuesday_after_the_switch_is_clamped_to_its_block(switched, monkeypatch):
    _at(monkeypatch, NEXT_TUE)
    body = _create(switched, NEXT_TUE, "07:00", "13:30")
    assert (body["start_time"][:5], body["end_time"][:5], float(body["net_hours"])) == ("07:15", "13:15", 6.0)


def test_clock_status_and_day_blocks_report_the_closed_day(switched, monkeypatch):
    _at(monkeypatch, NEXT_MON, time(9, 0))
    status = switched.get("/api/time-entries/clock-status").json()
    assert (status["blocks_today"], status["blockless_workday"]) == ([], True)
    day = switched.get(f"/api/time-entries/day-blocks?date={NEXT_TUE.isoformat()}").json()
    assert (day["blocks"], day["blockless_workday"]) == ([{"start": "07:30", "end": "13:00"}], False)
    sat = switched.get("/api/time-entries/day-blocks?date=2026-10-24").json()
    assert (sat["blocks"], sat["blockless_workday"]) == ([], False)


def test_running_entry_on_a_closed_day_counts_zero(switched, monkeypatch):
    _at(monkeypatch, NEXT_MON, time(8, 0))
    assert switched.post("/api/time-entries/clock-in", json={}).status_code in (200, 201)
    _at(monkeypatch, NEXT_MON, time(11, 0))
    status = switched.get("/api/time-entries/clock-status").json()
    assert (status["is_clocked_in"], status["today_net_minutes"]) == (True, 0)
