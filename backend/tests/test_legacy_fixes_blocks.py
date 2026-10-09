"""Spec 7.2 / 2.7: E39, E40, E41 — und P3 (409), P28."""
import datetime as dt
from datetime import date, time

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

import app.routers.time_entries as te

FRI_BEFORE = date(2026, 5, 29)


def _entry(db, user, d, start, end, brk=0, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=brk, **kw)
    db.add(e)
    db.commit()
    return e


def test_e39_employee_date_change_reclamps_and_warns(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = legacy_week(fri=("08:00", "17:00"))
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(7, 0), time(16, 0), 30)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"date": FRI_BEFORE.isoformat()})
    assert resp.status_code == 200, resp.text
    assert any(w.startswith("WORK_WINDOW_CLAMPED") for w in resp.json()["warnings"])
    _db_session.refresh(e)
    assert (e.date, e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (FRI_BEFORE, time(7, 45), time(7, 0), 15)


def test_e40_request_validates_on_credited_time_and_stores_raw(_db_session, employee_user, employee_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "18:00",
        "proposed_break_minutes": 0, "reason": "Nachtrag Teilschicht"})
    assert resp.status_code == 201, resp.text
    cr = _db_session.query(ChangeRequest).one()
    assert (cr.proposed_start_time, cr.proposed_end_time) == (time(8, 0), time(18, 0))


def test_p28_request_snapshots_uncredited(_db_session, employee_user, employee_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _entry(_db_session, employee_user, MON, time(8), time(18), 45,
               uncredited_minutes=150, clamp_grace_minutes=15)
    resp = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id), "proposed_date": MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "18:00",
        "proposed_break_minutes": 45, "reason": "Notiz"})
    assert resp.status_code == 201, resp.text
    assert _db_session.query(ChangeRequest).one().original_uncredited_minutes == 150


def test_e41_post_commit_check_counts_entry_once(_db_session, employee_user, admin_client):
    for day in range(1, 5):                                  # Mo–Do je 9,5 h = 38 h
        _entry(_db_session, employee_user, date(2026, 6, day), time(7), time(17, 15), 45)
    fri = _entry(_db_session, employee_user, date(2026, 6, 5), time(8), time(14))   # 6 h → 44 h
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=fri.id, proposed_date=date(2026, 6, 5),
                       proposed_start_time=time(8), proposed_end_time=time(14),
                       proposed_break_minutes=0, proposed_note="Nachtrag", reason="Notiz")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    assert not [w for w in resp.json()["warnings"] if "Wochenarbeitszeit" in w], resp.json()["warnings"]


def test_p3_employee_put_on_acknowledged_entry_is_409(_db_session, employee_user, employee_client, monkeypatch):
    e = _entry(_db_session, employee_user, MON, time(8), time(12), credit_override=True)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"note": "x"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Anerkannter Eintrag – Änderung bitte per Änderungsantrag."


def test_p3_admin_on_the_employee_route_keeps_the_flag(_db_session, employee_user, admin_client):
    """P3 nennt „MA-PUT": die Verwaltung bestätigt neue Zeiten ausdrücklich —
    auch wenn sie den Mitarbeiter-Endpunkt benutzt (TimeTracking-Seite)."""
    employee_user.work_blocks = legacy_week(mon=("08:00", "12:00"))  # ohne Anerkennung: Ende → 12:15
    e = _entry(_db_session, employee_user, MON, time(7), time(12), credit_override=True)
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={"end_time": "12:30"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.credit_override) == (time(12, 30), None, True)


def test_employee_put_ignores_server_side_fields(_db_session, employee_user, employee_client, monkeypatch):
    """Spec 7.1 Nr. 4/E11: uncredited_minutes, credit_override, auto_closed,
    clamp_grace_minutes nie über die generische setattr-Schleife."""
    e = _entry(_db_session, employee_user, MON, time(8), time(12))
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={
        "note": "x", "uncredited_minutes": 999, "credit_override": True,
        "auto_closed": True, "clamp_grace_minutes": 99})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.uncredited_minutes, e.credit_override, e.auto_closed, e.clamp_grace_minutes) == (0, False, False, None)


def test_p3_admin_edit_and_cr_update_keep_flag(_db_session, employee_user, admin_client):
    e = _entry(_db_session, employee_user, MON, time(8), time(12), credit_override=True)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "12:30"}).status_code == 200
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=e.id, proposed_date=MON, proposed_start_time=time(8),
                       proposed_end_time=time(13), proposed_break_minutes=0, reason="Notiz")
    _db_session.add(cr)
    _db_session.commit()
    assert admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"}).status_code == 200
    _db_session.refresh(e)
    assert (e.end_time, e.credit_override) == (time(13), True)
