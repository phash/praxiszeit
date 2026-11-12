"""Review 2026-11-11, Slice „antrag": Änderungsanträge (Backend-Funde 02/03/04/09/12/13/14/17/18/19/21)."""
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models import (
    Absence, AbsenceReason, AbsenceType, ChangeRequest, TimeEntry, TimeEntryAuditLog,
)
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)


def _past_weekday(n=5):
    d = today_local() - timedelta(days=n)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _time_cr(client, d, start="07:00:00", end="11:00:00"):
    return client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": d.isoformat(),
        "proposed_start_time": start, "proposed_end_time": end,
        "proposed_break_minutes": 0, "reason": "vergessen",
    })


def _abs_cr(client, d, **kw):
    body = {"request_type": "create", "entry_kind": "absence",
            "proposed_date": d.isoformat(), "proposed_absence_type": "sick",
            "proposed_absence_hours": 8, "reason": "krank"}
    body.update(kw)
    return client.post("/api/change-requests/", json=body)


def _absence(db, user, d, **kw):
    a = Absence(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                type=kw.pop("type", AbsenceType.VACATION), hours=8, **kw)
    db.add(a)
    db.commit()
    return a


# antrag-03 -------------------------------------------------------------
def test_open_absence_cr_does_not_block_time_entry_create(employee_client):
    d = _past_weekday()
    assert _abs_cr(employee_client, d).status_code == 201
    r = _time_cr(employee_client, d)
    assert r.status_code == 201, r.text


def test_two_shifts_same_day_allowed_same_start_blocked(employee_client):
    d = _past_weekday()
    assert _time_cr(employee_client, d, "07:00:00", "11:00:00").status_code == 201
    assert _time_cr(employee_client, d, "13:00:00", "17:00:00").status_code == 201
    r = _time_cr(employee_client, d, "07:00:00", "09:00:00")
    assert r.status_code == 400
    assert "Datum" in r.json()["detail"]


# antrag-09 -------------------------------------------------------------
@pytest.mark.parametrize("url", ["/api/change-requests/?limit=-1", "/api/change-requests/?limit=0"])
def test_employee_list_limit_lower_bound(employee_client, url):
    assert employee_client.get(url).status_code == 422


def test_admin_list_limit_lower_bound(admin_client):
    assert admin_client.get("/api/admin/change-requests?limit=-5").status_code == 422


# antrag-12 / 13 --------------------------------------------------------
def test_absence_cr_outside_employment_window_rejected_on_creation(
        _db_session, employee_user, employee_client):
    d = _past_weekday()
    employee_user.first_work_day = d + timedelta(days=1)
    _db_session.commit()
    r = _abs_cr(employee_client, d)
    assert r.status_code == 400
    assert r.json()["detail"] == "Datum liegt vor dem ersten Arbeitstag"


def test_absence_update_cr_rejects_future_existing_absence(
        _db_session, employee_user, employee_client):
    future = today_local() + timedelta(days=7)
    a = _absence(_db_session, employee_user, future)
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "entry_kind": "absence", "absence_id": str(a.id),
        "proposed_date": _past_weekday().isoformat(), "proposed_absence_type": "vacation",
        "proposed_absence_hours": 8, "reason": "umbuchen",
    })
    assert r.status_code == 400, r.text


# antrag-04 -------------------------------------------------------------
def test_approval_rejects_delete_of_closure_absence(
        _db_session, employee_user, admin_client):
    a = _absence(_db_session, employee_user, _past_weekday())
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="absence",
        request_type=ChangeRequestType.DELETE, status=ChangeRequestStatus.PENDING,
        absence_id=a.id, original_date=a.date, original_absence_type="vacation",
        original_absence_hours=8, reason="weg")
    _db_session.add(cr)
    _db_session.commit()
    # nachträglich zur Betriebsferien-Zeile geworden
    from app.models import CompanyClosure
    closure = CompanyClosure(tenant_id=DEFAULT_TENANT_ID, name="Ferien",
                             start_date=a.date, end_date=a.date, created_by=employee_user.id)
    _db_session.add(closure)
    _db_session.commit()
    a.closure_id = closure.id
    _db_session.commit()
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 400, r.text
    _db_session.expire_all()
    assert _db_session.get(ChangeRequest, cr.id).status == ChangeRequestStatus.PENDING
    assert _db_session.get(Absence, a.id) is not None


# antrag-02 -------------------------------------------------------------
def test_update_audit_keeps_unchanged_break_and_note(_db_session, employee_user, admin_client):
    d = _past_weekday()
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=d,
                  start_time=time(8, 0), end_time=time(12, 0), break_minutes=30,
                  note="Notiz X")
    _db_session.add(e)
    _db_session.commit()
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="time_entry",
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
        time_entry_id=e.id, proposed_date=d, proposed_start_time=time(8, 0),
        proposed_end_time=time(13, 0), proposed_break_minutes=None, proposed_note=None,
        original_date=d, original_start_time=time(8, 0), original_end_time=time(12, 0),
        original_break_minutes=30, original_note="Notiz X", reason="Ende")
    _db_session.add(cr)
    _db_session.commit()
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    log = (_db_session.query(TimeEntryAuditLog)
           .filter(TimeEntryAuditLog.change_request_id == cr.id).one())
    assert log.new_break_minutes == 30
    assert log.new_note == "Notiz X"


# antrag-14 / 18 --------------------------------------------------------
def _reason(db, **kw):
    r = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Kind krank",
                      base_behavior="paid_free", **kw)
    db.add(r)
    db.commit()
    return r


def test_type_change_without_new_reason_clears_reason(_db_session, employee_user, admin_client):
    reason = _reason(_db_session)
    a = _absence(_db_session, employee_user, _past_weekday(), type=AbsenceType.PAID_LEAVE,
                 reason_id=reason.id)
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="absence",
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
        absence_id=a.id, proposed_date=a.date, proposed_absence_type="vacation",
        proposed_absence_hours=8, original_date=a.date, original_absence_type="paid_leave",
        original_absence_hours=8, reason="Typ")
    _db_session.add(cr)
    _db_session.commit()
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    _db_session.expire_all()
    got = _db_session.get(Absence, a.id)
    assert got.type == AbsenceType.VACATION
    assert got.reason_id is None


def test_response_carries_reason_label(_db_session, employee_user, admin_client):
    reason = _reason(_db_session)
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="absence",
        request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
        proposed_date=_past_weekday(), proposed_absence_type="paid_leave",
        proposed_absence_hours=8, proposed_reason_id=reason.id, reason="Kind")
    _db_session.add(cr)
    _db_session.commit()
    rows = admin_client.get("/api/admin/change-requests").json()
    assert rows[0]["proposed_reason_label"] == "Kind krank"
    assert rows[0]["proposed_reason_id"] == str(reason.id)


# antrag-17 -------------------------------------------------------------
def test_date_filter_uses_berlin_day_boundaries(_db_session, employee_user, admin_client):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="time_entry",
        request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
        proposed_date=date(2026, 10, 20), proposed_start_time=time(8, 0),
        proposed_end_time=time(9, 0), reason="x",
        created_at=datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc))  # 01.11. 00:30 Berlin
    _db_session.add(cr)
    _db_session.commit()
    nov = admin_client.get("/api/admin/change-requests?date_from=2026-11-01&date_to=2026-11-30").json()
    okt = admin_client.get("/api/admin/change-requests?date_from=2026-10-01&date_to=2026-10-31").json()
    assert len(nov) == 1
    assert okt == []


# antrag-19 -------------------------------------------------------------
def test_create_takes_user_anchor_lock_before_duplicate_probe(employee_client, employee_user, monkeypatch):
    from app.routers import change_requests as mod
    calls = []
    real = mod.lock_user_row
    monkeypatch.setattr(mod, "lock_user_row", lambda db, t, u: (calls.append(u), real(db, t, u))[1])
    assert _time_cr(employee_client, _past_weekday()).status_code == 201
    assert calls == [employee_user.id]


# antrag-21 -------------------------------------------------------------
def test_bulk_review_survives_unexpected_error(_db_session, employee_user, admin_client, monkeypatch):
    ids = []
    for h in (8, 10):
        cr = ChangeRequest(
            tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="time_entry",
            request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
            proposed_date=_past_weekday(), proposed_start_time=time(h, 0),
            proposed_end_time=time(h + 1, 0), proposed_break_minutes=0, reason="x")
        _db_session.add(cr)
        _db_session.commit()
        ids.append(str(cr.id))
    from app.routers import admin_change_requests as mod
    real = mod.review_change_request

    def flaky(request_id, **kw):
        if request_id == ids[0]:
            raise RuntimeError("boom")
        return real(request_id=request_id, **kw)
    monkeypatch.setattr(mod, "review_change_request", flaky)
    r = admin_client.post("/api/admin/change-requests/bulk-review",
                          json={"request_ids": ids, "action": "approve"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["succeeded"], body["failed"]) == (1, 1)
    assert "boom" not in r.text
