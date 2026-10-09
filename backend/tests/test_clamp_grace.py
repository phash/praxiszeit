"""Spec E79/E80 (19.1 Nr. 8): jeder gekappte Eintrag merkt sich seinen Puffer;
Einzel-Neukappungen kappen mit dem gespeicherten Wert weiter."""
import datetime as dt
from datetime import date, time

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

import app.routers.time_entries as te

NEXT_MON = date(2026, 6, 8)
SATURDAY = date(2026, 6, 6)


def _grace(db, minutes):
    row = db.query(SystemSetting).filter(SystemSetting.key == "work_window_grace_minutes").first()
    if row is None:
        db.add(SystemSetting(key="work_window_grace_minutes", value=str(minutes), tenant_id=DEFAULT_TENANT_ID))
    else:
        row.value = str(minutes)
    db.commit()


def _window(db, user):
    user.work_blocks = legacy_week(mon=("08:00", "17:00"))
    db.commit()


def _admin_create(client, user, start="07:00", end="16:00", brk=30):
    resp = client.post(f"/api/admin/users/{user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": start, "end_time": end, "break_minutes": brk})
    assert resp.status_code == 201, resp.text
    return resp


def _only(db):
    entry = db.query(TimeEntry).one()
    db.refresh(entry)
    return entry


def test_new_entries_store_current_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7, 0), 15)


def test_employee_create_and_clock_in_store_current_grace(_db_session, employee_user, employee_client, monkeypatch):
    _window(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 7, 0))
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    assert _only(_db_session).clamp_grace_minutes == 15


def test_employee_create_stores_current_grace(_db_session, employee_user, employee_client, monkeypatch):
    _window(_db_session, employee_user)
    _grace(_db_session, 10)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.post("/api/time-entries", json={
        "date": MON.isoformat(), "start_time": "07:00", "end_time": "16:00", "break_minutes": 30})
    assert resp.status_code == 201, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 50), time(7, 0), 10)


def test_cr_create_stores_current_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _grace(_db_session, 10)
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
                       proposed_date=MON, proposed_start_time=time(7, 0),
                       proposed_end_time=time(16, 0), proposed_break_minutes=30, reason="Nachtrag")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 50), time(7, 0), 10)


def test_cr_update_precheck_uses_stored_grace(_db_session, employee_user, admin_client):
    """Vorprüfung und Schreibzweig kappen mit DEMSELBEN Puffer (E80): gespeichert
    0, aktuell 120. Mit dem aktuellen Puffer prüfte die Vorprüfung 07:00–18:00
    (10,5 h → §3-422), geschrieben würde aber 08:00–17:00 (8,5 h)."""
    _window(_db_session, employee_user)
    _grace(_db_session, 0)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 120)
    e = _only(_db_session)
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=e.id, proposed_date=MON, proposed_start_time=time(7, 0),
                       proposed_end_time=time(18, 0), proposed_break_minutes=30, reason="Länger")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, e.clamp_grace_minutes) == (
        time(8, 0), time(17, 0), time(7, 0), time(18, 0), 0)


def test_admin_full_form_resave_keeps_stored_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 0)
    e = _only(_db_session)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={
        "start_time": "07:45", "end_time": "16:00", "break_minutes": 30, "note": "Korrektur"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7, 0), 15)


def test_employee_edit_keeps_stored_grace(_db_session, employee_user, employee_client, monkeypatch):
    _window(_db_session, employee_user)
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(7, 45), raw_start_time=time(7, 0), end_time=time(16, 0),
                              break_minutes=30, clamp_grace_minutes=15))
    _db_session.commit()
    _grace(_db_session, 0)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    e = _only(_db_session)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"start_time": "07:00", "end_time": "16:00"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.clamp_grace_minutes) == (time(7, 45), 15)


def test_admin_date_change_keeps_stored_grace_and_names_it(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 0)
    e = _only(_db_session)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"date": NEXT_MON.isoformat()})
    assert resp.status_code == 200, resp.text
    assert any("Puffer 15 Minuten" in w for w in resp.json()["warnings"])
    e = _only(_db_session)
    assert (e.date, e.start_time, e.clamp_grace_minutes) == (NEXT_MON, time(7, 45), 15)


def test_cr_update_keeps_stored_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 0)
    e = _only(_db_session)
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=e.id, proposed_date=MON, proposed_start_time=time(7, 45),
                       proposed_end_time=time(16, 0), proposed_break_minutes=30, reason="Notiz")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7, 0), 15)


def test_clock_out_uses_grace_of_open_entry(_db_session, employee_user, employee_client, monkeypatch):
    _window(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 7, 0))
    assert employee_client.post("/api/time-entries/clock-in", json={}).status_code == 201
    _grace(_db_session, 0)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 30))
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 30})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.end_time, e.raw_end_time, e.clamp_grace_minutes) == (time(17, 15), time(17, 30), 15)


def test_null_grace_uses_current_and_stores_it(_db_session, employee_user, admin_client):
    """Restfall (Spec 19 Nr. 2a): Bestand ohne gespeicherten Puffer kappt bei der
    Bearbeitung mit dem aktuellen Puffer — und merkt ihn sich danach."""
    _window(_db_session, employee_user)
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(7, 45), raw_start_time=time(7, 0), end_time=time(16, 0),
                              break_minutes=30, clamp_grace_minutes=None))
    _db_session.commit()
    _grace(_db_session, 10)
    e = _only(_db_session)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"start_time": "07:45", "end_time": "16:00"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.clamp_grace_minutes) == (time(7, 50), 10)


def test_day_without_blocks_keeps_stored_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _admin_create(admin_client, employee_user)
    _grace(_db_session, 0)
    e = _only(_db_session)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"date": SATURDAY.isoformat()}).status_code == 200
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 0), None, 15)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"date": MON.isoformat()}).status_code == 200
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7, 0), 15)


def test_credit_override_sets_no_grace(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    _db_session.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                              start_time=time(7, 0), end_time=time(16, 0), break_minutes=30,
                              credit_override=True))
    _db_session.commit()
    e = _only(_db_session)
    assert admin_client.put(f"/api/admin/time-entries/{e.id}", json={"start_time": "06:30"}).status_code == 200
    e = _only(_db_session)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes, e.credit_override) == (time(6, 30), None, None, True)


def test_schemas_never_accept_server_side_fields(_db_session, employee_user, admin_client):
    _window(_db_session, employee_user)
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "07:00", "end_time": "16:00", "break_minutes": 30,
        "clamp_grace_minutes": 99, "uncredited_minutes": 999, "credit_override": True, "auto_closed": True})
    assert resp.status_code == 201, resp.text
    e = _only(_db_session)
    assert (e.clamp_grace_minutes, e.uncredited_minutes, e.credit_override, e.auto_closed) == (15, 0, False, False)


# Review Focus 2: Formular-Re-Save (Notiz/Pause) an einem lückengekappten Eintrag.
def test_admin_full_form_resave_keeps_gap_state(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    _admin_create(admin_client, employee_user, "07:00", "19:00", 0)          # K7
    _grace(_db_session, 0)
    e = _only(_db_session)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={
        "start_time": "07:45", "end_time": "18:15", "break_minutes": 30, "note": "Korrektur"})
    assert resp.status_code == 200, resp.text
    e = _only(_db_session)
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time) == (
        time(7, 45), time(18, 15), time(7, 0), time(19, 0))
    assert (e.uncredited_minutes, e.clamp_grace_minutes, e.break_minutes) == (150, 15, 30)
