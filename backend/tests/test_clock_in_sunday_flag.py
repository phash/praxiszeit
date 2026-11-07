"""Release-Test 1.23.0: die Antwort von ``POST /clock-in`` trägt dieselben
berechneten Felder wie ``/clock-status`` und ``/clock-out`` — an einem Sonntag
also ``is_sunday_or_holiday = True`` (vorher fest False, weil clock_in die
Antwort ohne ``_enrich_response`` baute)."""
from datetime import date, datetime, time

import app.routers.time_entries as te
from app.middleware.auth import require_admin
from app.services import timezone_service
from tests.wh_change_helpers import admin_client, freeze

SUNDAY = date(2026, 11, 8)
MONDAY = date(2026, 11, 9)


def _at(monkeypatch, d, at):
    freeze(monkeypatch, d, at)
    monkeypatch.setattr(te, "_now_local", lambda: datetime.combine(d, at, tzinfo=timezone_service.LOCAL_TZ))


def _employee(db, test_user):
    client = admin_client(db, test_user)
    from tests.test_endpoints import test_app
    test_app.dependency_overrides.pop(require_admin, None)
    return client


def test_clock_in_on_sunday_reports_the_flag(db, test_user, monkeypatch):
    _at(monkeypatch, SUNDAY, time(9, 0))
    resp = _employee(db, test_user).post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_sunday_or_holiday"] is True
    assert body["is_editable"] is True


def test_clock_in_on_monday_keeps_the_flag_false(db, test_user, monkeypatch):
    _at(monkeypatch, MONDAY, time(9, 0))
    resp = _employee(db, test_user).post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_sunday_or_holiday"] is False
