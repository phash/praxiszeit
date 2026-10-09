"""Spec 7.1 Nr. 1–6, 8, 9: jede schreibende Stelle speichert uncredited_minutes."""
import datetime as dt
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

import app.routers.time_entries as te


def _blocks(db, user, blocks=K_BLOCKS):
    user.work_blocks = blocks
    db.commit()


def _entry(db, user, start, end, brk=0, day=MON):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=day,
                  start_time=start, end_time=end, break_minutes=brk)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _today(monkeypatch, hh=12, mm=0):
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, hh, mm))


def test_clock_in_in_gap(_db_session, employee_user, employee_client, monkeypatch):
    _blocks(_db_session, employee_user)
    _today(monkeypatch, 13, 0)
    resp = employee_client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text
    assert any(w.startswith("WORK_WINDOW_CLAMPED: Eingestempelt zwischen") for w in resp.json()["warnings"])
    entry = _db_session.query(TimeEntry).one()
    assert entry.uncredited_minutes == 0


def test_clock_out_k2b(_db_session, employee_user, employee_client, monkeypatch):
    _blocks(_db_session, employee_user)
    _entry(_db_session, employee_user, time(13, 0), None)
    _today(monkeypatch, 18, 0)
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0})
    assert resp.status_code == 200, resp.text
    entry = _db_session.query(TimeEntry).one()
    assert entry.uncredited_minutes == 105
    assert entry.net_hours == Decimal("3.25")


def test_employee_create_k21(_db_session, employee_user, employee_client, monkeypatch):
    _blocks(_db_session, employee_user)
    _today(monkeypatch)
    resp = employee_client.post("/api/time-entries/", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "18:00", "break_minutes": 45})
    assert resp.status_code == 201, resp.text
    entry = _db_session.query(TimeEntry).one()
    assert (entry.uncredited_minutes, entry.net_hours) == (150, Decimal("6.75"))


def test_employee_update_writes_uncredited(_db_session, employee_user, employee_client, monkeypatch):
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8, 0), time(12, 0))
    _today(monkeypatch, 19, 0)
    resp = employee_client.put(f"/api/time-entries/{e.id}", json={"end_time": "18:00", "break_minutes": 45})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.uncredited_minutes == 150


def test_admin_create_counts_daily_hours_on_credited_time(_db_session, employee_user, admin_client):
    """Spec 7.1 (Netto-Helfer): 06:00–19:00, Pause 45, Lücke 10:15–13:45 →
    angerechnet 8,75 h; ohne uncredited wären es 12,25 h und HTTP 422."""
    _blocks(_db_session, employee_user, block_week(mon=[("06:00", "10:00"), ("14:00", "19:00")]))
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "06:00", "end_time": "19:00", "break_minutes": 45})
    assert resp.status_code == 201, resp.text
    entry = _db_session.query(TimeEntry).one()
    assert (entry.uncredited_minutes, entry.net_hours) == (210, Decimal("8.75"))


def test_admin_update_writes_uncredited(_db_session, employee_user, admin_client):
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8, 0), time(12, 0))
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "18:00", "break_minutes": 45})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.uncredited_minutes == 150


def _cr(db, user, **kw):
    cr = ChangeRequest(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       status=ChangeRequestStatus.PENDING, proposed_date=MON,
                       proposed_start_time=time(8, 0), proposed_end_time=time(18, 0),
                       proposed_break_minutes=45, reason="Nachtrag", **kw)
    db.add(cr)
    db.commit()
    return cr


def test_cr_create_approval_writes_uncredited(_db_session, employee_user, admin_client):
    _blocks(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, request_type=ChangeRequestType.CREATE)
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    assert _db_session.query(TimeEntry).one().uncredited_minutes == 150


def test_cr_update_approval_writes_uncredited(_db_session, employee_user, admin_client):
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8, 0), time(12, 0))
    cr = _cr(_db_session, employee_user, request_type=ChangeRequestType.UPDATE, time_entry_id=e.id)
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.uncredited_minutes == 150


# Review Task 4: §3 (10-h-Hartgrenze, HTTP 422) rechnet an JEDER Tagesprüfung
# auf der angerechneten Zeit — nicht nur in admin_create (Test oben). Tag mit
# Lücke 10:15–13:45 (Puffer 15): 06:00–19:00, Pause 45 → roh 12,25 h (422),
# angerechnet 8,75 h. Die übrigen Tests dieser Datei bleiben mit 08:00–18:00
# (roh 9,25 h) unter der Grenze und sähen einen fehlenden Lückenabzug nicht.
GAP_BLOCKS = block_week(mon=[("06:00", "10:00"), ("14:00", "19:00")])
WIDE = {"start_time": "06:00", "end_time": "19:00", "break_minutes": 45}


def _ma_create(db, user, request):
    return request.getfixturevalue("employee_client").post(
        "/api/time-entries/", json={"date": MON.isoformat(), **WIDE})


def _ma_update(db, user, request):
    e = _entry(db, user, time(8, 0), time(12, 0))
    return request.getfixturevalue("employee_client").put(f"/api/time-entries/{e.id}", json=WIDE)


def _admin_update(db, user, request):
    e = _entry(db, user, time(8, 0), time(12, 0))
    return request.getfixturevalue("admin_client").put(f"/api/admin/time-entries/{e.id}", json=WIDE)


def _cr_approval(db, user, request):
    # Antrag direkt angelegt: der MA-Antragsweg prüft bis E40 noch roh und
    # lehnte 06:00–19:00 schon beim Stellen ab. Geprüft wird hier die
    # Vorprüfung der Genehmigung (Spec 7.1 Nr. 7, gilt auch für Bulk).
    cr = ChangeRequest(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
                       proposed_date=MON, proposed_start_time=time(6, 0), proposed_end_time=time(19, 0),
                       proposed_break_minutes=45, reason="Nachtrag")
    db.add(cr)
    db.commit()
    return request.getfixturevalue("admin_client").post(
        f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})


@pytest.mark.parametrize("path, expected_status", [
    (_ma_create, 201), (_ma_update, 200), (_admin_update, 200), (_cr_approval, 200),
], ids=["ma_create", "ma_update", "admin_update", "cr_approval"])
def test_daily_hard_cap_counts_credited_time(_db_session, employee_user, request, monkeypatch,
                                             path, expected_status):
    _blocks(_db_session, employee_user, GAP_BLOCKS)
    _today(monkeypatch, 19, 30)
    resp = path(_db_session, employee_user, request)
    assert resp.status_code == expected_status, resp.text
    _db_session.expire_all()
    entry = _db_session.query(TimeEntry).one()
    assert (entry.uncredited_minutes, entry.net_hours) == (210, Decimal("8.75"))


def test_clock_out_daily_check_counts_credited_time(_db_session, employee_user, employee_client, monkeypatch):
    """clock_out sperrt §3 nicht (Review R2-b), meldet aber DAILY_HOURS_HARD —
    auch das nur auf der angerechneten Zeit (8,75 h → nur die 8-h-Warnung)."""
    _blocks(_db_session, employee_user, GAP_BLOCKS)
    _entry(_db_session, employee_user, time(6, 0), None)
    _today(monkeypatch, 19, 0)
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 45})
    assert resp.status_code == 200, resp.text
    warnings = resp.json()["warnings"]
    assert not any(w.startswith("DAILY_HOURS_HARD") for w in warnings), warnings
    assert "DAILY_HOURS_WARNING" in warnings, warnings
    entry = _db_session.query(TimeEntry).one()
    assert (entry.uncredited_minutes, entry.net_hours) == (210, Decimal("8.75"))


# Review Task 4: Die 48-h-Wochenwarnung (Spec 7.1 Nr. 2/3/5) und die
# Tagesnachprüfung NACH dem Commit in update_time_entry (speist
# DAILY_HOURS_WARNING und §6) rechnen an JEDER Aufrufstelle auf der
# angerechneten Zeit. Mo–Do je 10,0 h ohne Blöcke (07:00–17:15, Pause 15),
# Fr mit Lücke 12:15–14:45: 08:00–18:00, Pause 45 → roh 9,25 h (Woche
# 49,25 h → beide Warnungen), angerechnet 6,75 h (Woche 46,75 h → keine).
# Die Nachprüfung der Antragsgenehmigung (Nr. 10) bleibt außen vor, bis E41
# (Task 9) die Doppelzählung des eben geschriebenen Eintrags behebt — sie
# warnte bis dahin ohnehin.
FRI = date(2026, 6, 5)
FRI_BLOCKS = block_week(fri=[("08:00", "12:00"), ("15:00", "18:00")])
FRI_DAY = {"start_time": "08:00", "end_time": "18:00", "break_minutes": 45}


def _seed_week(db, user):
    user.work_blocks = FRI_BLOCKS
    for d in range(1, 5):
        db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=date(2026, 6, d),
                         start_time=time(7, 0), end_time=time(17, 15), break_minutes=15))
    db.commit()


def _week_ma_create(db, user, request):
    return request.getfixturevalue("employee_client").post(
        "/api/time-entries/", json={"date": FRI.isoformat(), **FRI_DAY})


def _week_ma_update(db, user, request):
    e = _entry(db, user, time(8, 0), time(12, 0), day=FRI)
    return request.getfixturevalue("employee_client").put(f"/api/time-entries/{e.id}", json=FRI_DAY)


def _week_clock_out(db, user, request):
    _entry(db, user, time(8, 0), None, day=FRI)
    return request.getfixturevalue("employee_client").post(
        "/api/time-entries/clock-out", json={"break_minutes": 45})


def _week_admin_create(db, user, request):
    return request.getfixturevalue("admin_client").post(
        f"/api/admin/users/{user.id}/time-entries", json={"date": FRI.isoformat(), **FRI_DAY})


def _week_admin_update(db, user, request):
    e = _entry(db, user, time(8, 0), time(12, 0), day=FRI)
    return request.getfixturevalue("admin_client").put(f"/api/admin/time-entries/{e.id}", json=FRI_DAY)


@pytest.mark.parametrize("path", [
    _week_ma_create, _week_ma_update, _week_clock_out, _week_admin_create, _week_admin_update,
], ids=["ma_create", "ma_update", "clock_out", "admin_create", "admin_update"])
def test_weekly_and_post_commit_daily_warnings_use_credited_time(_db_session, employee_user, request,
                                                                 monkeypatch, path):
    _seed_week(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: FRI)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 5, 18, 0))
    resp = path(_db_session, employee_user, request)
    assert resp.status_code in (200, 201), resp.text
    warnings = resp.json()["warnings"]
    assert not any(w.startswith("WEEKLY_HOURS_WARNING") for w in warnings), warnings
    assert not any(w.startswith("DAILY_HOURS_WARNING") for w in warnings), warnings
    _db_session.expire_all()
    fri = _db_session.query(TimeEntry).filter(TimeEntry.date == FRI).one()
    assert (fri.uncredited_minutes, fri.net_hours) == (150, Decimal("6.75"))
