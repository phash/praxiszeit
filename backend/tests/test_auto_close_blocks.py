"""Spec K15, P18, E42: der Auto-Close kappt jetzt und kennzeichnet sich."""
import datetime as dt
from datetime import date, time
from decimal import Decimal

from app.models import ChangeRequest, TimeEntry, TimeEntryAuditLog
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

import app.routers.time_entries as te

TUE = date(2026, 6, 2)


def _open(db, user, start=time(8, 0), **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                  start_time=start, end_time=None, break_minutes=0, **kw)
    db.add(e)
    db.commit()
    return e


def _next_day_clock_in(client, monkeypatch):
    monkeypatch.setattr(te, "_today_local", lambda: TUE)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 2, 7, 30))
    resp = client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text


def test_k15_auto_close_clamps_and_flags(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes) == (time(18, 15), time(23, 59), 150)
    assert (e.auto_closed, e.clamp_grace_minutes, e.net_hours) == (True, 15, Decimal("7.75"))
    audit = _db_session.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.time_entry_id == e.id, TimeEntryAuditLog.source == "auto_close").one()
    assert audit.new_end_time == time(18, 15)


def test_without_blocks_end_stays_2359(_db_session, employee_user, employee_client, monkeypatch):
    e = _open(_db_session, employee_user)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)


def test_auto_close_uses_stored_grace(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.add(SystemSetting(key="work_window_grace_minutes", value="0", tenant_id=DEFAULT_TENANT_ID))
    _db_session.commit()
    e = _open(_db_session, employee_user, clamp_grace_minutes=15)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert e.end_time == time(18, 15)


def test_clock_status_stale_branch_closes_with_clamp(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: TUE)
    assert employee_client.get("/api/time-entries/clock-status").json()["is_clocked_in"] is False
    _db_session.refresh(e)
    assert (e.end_time, e.auto_closed) == (time(18, 15), True)


def _auto_close_directly(db, entry):
    """Ein Test mit ``admin_client`` UND ``employee_client`` sähe beide als
    dieselbe Person — beide Fixtures überschreiben ``get_current_user``, die
    zuletzt gebaute gewinnt. Deshalb den Auto-Close hier direkt aufrufen."""
    te._close_stale_entry(db, entry)
    db.commit()


def test_admin_end_correction_resets_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    assert e.auto_closed is True
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "17:00"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 0), None, False)


def test_admin_form_resave_keeps_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={
        "start_time": "08:00", "end_time": "18:15", "note": "geprüft"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)


# Review Focus 1: halboffenes Altfenster (Platzhalter 23:59) — wie 072.
def test_half_open_legacy_window_unchanged(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = legacy_week(mon=("08:00", None))
    _db_session.commit()
    e = _open(_db_session, employee_user, start=time(9, 0))
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes, e.auto_closed) == (time(23, 59), None, 0, True)


def test_half_open_legacy_window_late_clock_out(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = legacy_week(mon=("08:00", None))
    _db_session.commit()
    e = _open(_db_session, employee_user, start=time(9, 0))
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 22, 30))
    assert employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 45}).status_code == 200
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(22, 30), None, False)


# P18 (7.1): „Jeder Pfad außer dem Auto-Close, der end_time schreibt, setzt
# auto_closed = false" — auch Ausstempeln, die Bearbeiten-Route der Beschäftigten
# (Admins bearbeiten dort auch fremde Einträge vergangener Tage) und die
# Genehmigung eines Änderungsantrags (UPDATE). Ein unverändert mitgeschicktes
# wirksames Ende ist keine Korrektur: dann bleibt 23:59 synthetisch.

def test_clock_out_resets_flag(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    # Künstlicher Zustand (offener Eintrag mit Kennzeichen): hält fest, dass
    # clock_out das Kennzeichen selbst schreibt, statt sich auf den Default zu verlassen.
    e = _open(_db_session, employee_user, auto_closed=True)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 30})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.auto_closed) == (time(17, 0), False)


def test_employee_route_end_correction_resets_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={"end_time": "17:00"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 0), None, False)


def test_employee_route_form_resave_keeps_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={
        "start_time": "08:00", "end_time": "18:15", "note": "geprüft"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)


def _approve_update_cr(db, client, user, entry, end):
    cr = ChangeRequest(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=entry.id, proposed_date=MON, proposed_start_time=time(8, 0),
                       proposed_end_time=end, proposed_break_minutes=0,
                       reason="Ende nachgetragen")
    db.add(cr)
    db.commit()
    resp = client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text


def test_cr_update_end_correction_resets_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    _approve_update_cr(_db_session, admin_client, employee_user, e, time(17, 0))
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 0), None, False)


def test_cr_update_unchanged_end_keeps_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    _approve_update_cr(_db_session, admin_client, employee_user, e, time(18, 15))
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)
