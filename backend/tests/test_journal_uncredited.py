"""Spec 2026-10-08, 13.2 (PR2): das Monatsjournal führt je Eintrag die nicht
angerechnete Zeit und im Summary die Monatssumme (Lücke + Hülle, P19)."""
from datetime import time, timedelta

from app.models import TimeEntry
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import MON

TUE = MON + timedelta(days=1)


def _seed(db, user):
    # K7: Lücke 150 + Hülle 90 = 240
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                     start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                     raw_end_time=time(19), break_minutes=0, uncredited_minutes=150,
                     clamp_grace_minutes=15))
    # K15: automatisch geschlossen — die Endseite 23:59 zählt nicht (P18)
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=TUE,
                     start_time=time(8), end_time=time(18, 15), raw_end_time=time(23, 59),
                     break_minutes=0, uncredited_minutes=150, auto_closed=True))
    db.commit()


def _day(body, d):
    return next(x for x in body["days"] if x["date"] == d.isoformat())


def _check(body):
    k7 = _day(body, MON)["time_entries"][0]
    assert (k7["uncredited_minutes"], k7["not_credited_minutes"],
            k7["credit_override"], k7["auto_closed"]) == (150, 240, False, False)
    k15 = _day(body, TUE)["time_entries"][0]
    assert (k15["not_credited_minutes"], k15["auto_closed"]) == (150, True)
    assert body["monthly_summary"]["not_credited_minutes_total"] == 390


def test_own_journal(_db_session, employee_user, employee_client):
    _seed(_db_session, employee_user)
    r = employee_client.get("/api/journal/me?year=2026&month=6")
    assert r.status_code == 200, r.text
    _check(r.json())


def test_admin_journal(_db_session, employee_user, admin_client):
    _seed(_db_session, employee_user)
    r = admin_client.get(f"/api/admin/users/{employee_user.id}/journal?year=2026&month=6")
    assert r.status_code == 200, r.text
    _check(r.json())


def test_month_without_clamping_reports_zero(_db_session, employee_user, employee_client):
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(8), end_time=time(16, 30), break_minutes=30))
    _db_session.commit()
    body = employee_client.get("/api/journal/me?year=2026&month=6").json()
    assert body["monthly_summary"]["not_credited_minutes_total"] == 0
    assert _day(body, MON)["time_entries"][0]["not_credited_minutes"] == 0
