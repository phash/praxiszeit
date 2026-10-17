"""Ultrareview 1.20 (Fund 1): ein HEUTE anerkannter Eintrag (credit_override)
sperrt MA-PUT/-DELETE mit 409 „… bitte per Änderungsantrag." — der Antrag
muss dann auch heute gestellt werden können, sonst ist der Verweis eine
Sackgasse („nur für vergangene Tage" bzw. „Heutige Einträge können direkt
gelöscht werden")."""
from datetime import datetime, time, timedelta

import app.routers.change_requests as cr_router
from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON


def _today_is_mon(monkeypatch, hour=20):
    monkeypatch.setattr(cr_router, "today_local", lambda: MON)
    monkeypatch.setattr(cr_router, "now_local", lambda: datetime.combine(MON, time(hour)))


def _entry(db, user, recognized=True):
    user.work_blocks = K_BLOCKS
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                  start_time=time(7), end_time=time(19), break_minutes=0,
                  uncredited_minutes=0 if recognized else 150,
                  credit_override=recognized)
    db.add(e)
    db.commit()
    return e


def _update(client, entry, **kw):
    body = {
        "request_type": "update",
        "time_entry_id": str(entry.id),
        "proposed_date": kw.pop("proposed_date", MON.isoformat()),
        "proposed_start_time": "08:00",
        "proposed_end_time": kw.pop("end", "16:30"),
        "proposed_break_minutes": 30,
        "reason": "Pause vergessen",
    }
    body.update(kw)
    return client.post("/api/change-requests/", json=body)


def _delete(client, entry):
    return client.post("/api/change-requests/", json={
        "request_type": "delete", "time_entry_id": str(entry.id),
        "reason": "Doppelt erfasst",
    })


def test_update_request_for_todays_recognized_entry_is_allowed(_db_session, employee_user,
                                                               employee_client, monkeypatch):
    _today_is_mon(monkeypatch)
    e = _entry(_db_session, employee_user)
    r = _update(employee_client, e)
    assert r.status_code == 201, r.text


def test_delete_request_for_todays_recognized_entry_is_allowed(_db_session, employee_user,
                                                               employee_client, monkeypatch):
    _today_is_mon(monkeypatch)
    e = _entry(_db_session, employee_user)
    r = _delete(employee_client, e)
    assert r.status_code == 201, r.text


def test_todays_ordinary_delete_request_stays_rejected(_db_session, employee_user,
                                                       employee_client, monkeypatch):
    _today_is_mon(monkeypatch)
    e = _entry(_db_session, employee_user, recognized=False)
    r = _delete(employee_client, e)
    assert (r.status_code, r.json()["detail"]) == (
        400, "Heutige Einträge können direkt gelöscht werden")


def test_recognized_today_cannot_move_into_the_future(_db_session, employee_user,
                                                      employee_client, monkeypatch):
    _today_is_mon(monkeypatch)
    e = _entry(_db_session, employee_user)
    r = _update(employee_client, e, proposed_date=(MON + timedelta(days=1)).isoformat())
    assert (r.status_code, r.json()["detail"]) == (
        400, "Änderungsanträge sind nur für vergangene Tage möglich")


def test_recognized_today_with_an_end_in_the_future_is_rejected(_db_session, employee_user,
                                                                employee_client, monkeypatch):
    """Die Anerkennung überlebt die Genehmigung — ein späteres Ende würde
    dauerhaft noch nicht gearbeitete Zeit anrechnen."""
    _today_is_mon(monkeypatch, hour=15)
    e = _entry(_db_session, employee_user)
    r = _update(employee_client, e)
    assert (r.status_code, r.json()["detail"]) == (
        400, cr_router.RECOGNIZED_TODAY_FUTURE_END_DETAIL)
    assert _db_session.query(ChangeRequest).count() == 0


def _cr(db, user, entry, request_type, **kw):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
        request_type=request_type, status=ChangeRequestStatus.PENDING,
        time_entry_id=entry.id, reason="Korrektur", **kw)
    db.add(cr)
    db.commit()
    return cr


def _approve(client, cr):
    return client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})


def test_approving_todays_requests(_db_session, employee_user, admin_client, monkeypatch):
    """Die Genehmigung kennt keine Tagesgrenze: UPDATE ändert den heutigen
    Eintrag und lässt die Anerkennung stehen, DELETE löscht ihn."""
    _today_is_mon(monkeypatch)
    e = _entry(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, ChangeRequestType.UPDATE, proposed_date=MON,
             proposed_start_time=time(8), proposed_end_time=time(16, 30),
             proposed_break_minutes=30)
    r = _approve(admin_client, cr)
    assert r.status_code == 200, r.text
    _db_session.expire_all()
    e = _db_session.get(TimeEntry, e.id)
    assert (e.start_time, e.end_time, e.break_minutes, e.credit_override) == (
        time(8), time(16, 30), 30, True)

    cr = _cr(_db_session, employee_user, e, ChangeRequestType.DELETE)
    r = _approve(admin_client, cr)
    assert r.status_code == 200, r.text
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is None
    assert {c.status for c in _db_session.query(ChangeRequest)} == {ChangeRequestStatus.APPROVED}
