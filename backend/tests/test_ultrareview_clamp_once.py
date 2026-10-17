"""Ultrareview 1.20 (Fund A): jede Kappung läuft je Schreibpfad nur EINMAL.

Die Schreibpfade riefen ``work_window_service.clamp(...)`` und danach
``gap_segments(...)`` mit identischen Argumenten — beide führten ``_clamp_core``
komplett aus (Snapshot, Feiertage, Sondertage: doppelte DB-Roundtrips), die
Antragsgenehmigung sogar bis zu viermal. Laufen die Argumente zweier Aufrufe
auseinander, stimmt zudem ``sum(segments) == uncredited_minutes`` nicht mehr.
``clamp_with_segments`` liefert beides aus einem Lauf.

Geprüft wird je Pfad: kein ``_clamp_core``-Aufruf mit identischen Argumenten
zweimal — und das Ergebnis ist das bisherige (K1: 08:00–18:00 gegen
08–12 + 15–18, Lücke 12:15–14:45 = 150 Min.).
"""
import datetime as dt
from collections import Counter
from datetime import time

import pytest

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.services import work_window_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
    endpoints_app,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON

import app.routers.time_entries as te


@pytest.fixture
def core_calls(monkeypatch):
    calls = Counter()
    real = work_window_service._clamp_core

    def spy(db, user, d, start, end, grace, *, credit_override, wh_changes, soll_free_dates):
        calls[(getattr(user, "id", None), d, start, end, grace, credit_override,
               id(wh_changes), id(soll_free_dates))] += 1
        return real(db, user, d, start, end, grace, credit_override=credit_override,
                    wh_changes=wh_changes, soll_free_dates=soll_free_dates)

    monkeypatch.setattr(work_window_service, "_clamp_core", spy)
    return calls


def _no_repeat(calls):
    assert calls, "keine Kappung gelaufen"
    repeated = {k: n for k, n in calls.items() if n > 1}
    assert not repeated, f"Kappung mehrfach mit identischen Eingaben: {repeated}"


def _blocks(db, user):
    user.work_blocks = K_BLOCKS
    db.commit()


def _entry(db, user, start, end, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=kw.pop("day", MON),
                  start_time=start, end_time=end, break_minutes=kw.pop("break_minutes", 0),
                  clamp_grace_minutes=15, **kw)
    db.add(e)
    db.commit()
    return e


def _k1(db, entry_id):
    db.expire_all()
    e = db.get(TimeEntry, entry_id)
    assert (e.start_time, e.end_time, e.uncredited_minutes) == (time(8), time(18), 150)
    return e


def test_clamp_with_segments_matches_the_single_calls(_db_session, employee_user):
    _blocks(_db_session, employee_user)
    args = (_db_session, employee_user, MON, time(7), time(18, 40), 15)
    r, segs = work_window_service.clamp_with_segments(*args, credit_override=False)
    assert r == work_window_service.clamp(*args, credit_override=False)
    assert segs == work_window_service.gap_segments(*args, credit_override=False)
    assert (r.eff_start, r.eff_end, r.uncredited_minutes, segs) == (
        time(7, 45), time(18, 15), 150, [150])


def test_admin_create(_db_session, employee_user, admin_client, core_calls):
    _blocks(_db_session, employee_user)
    r = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "18:00",
        "break_minutes": 0})
    assert r.status_code in (200, 201), r.text
    _no_repeat(core_calls)
    _k1(_db_session, r.json()["id"])


def test_admin_update(_db_session, employee_user, admin_client, core_calls):
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8), time(12))
    r = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "18:00"})
    assert r.status_code == 200, r.text
    _no_repeat(core_calls)
    _k1(_db_session, e.id)


def test_ma_create(_db_session, admin_user, admin_client, core_calls):
    _blocks(_db_session, admin_user)
    r = admin_client.post("/api/time-entries", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "18:00",
        "break_minutes": 0})
    assert r.status_code in (200, 201), r.text
    _no_repeat(core_calls)
    _k1(_db_session, r.json()["id"])


def test_ma_update(_db_session, admin_user, admin_client, core_calls):
    _blocks(_db_session, admin_user)
    e = _entry(_db_session, admin_user, time(8), time(12))
    r = admin_client.put(f"/api/time-entries/{e.id}", json={"end_time": "18:00"})
    assert r.status_code == 200, r.text
    _no_repeat(core_calls)
    _k1(_db_session, e.id)


def test_clock_out(_db_session, employee_user, employee_client, core_calls, monkeypatch):
    _blocks(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(
        MON.year, MON.month, MON.day, 18, 0, tzinfo=te.LOCAL_TZ))
    e = _entry(_db_session, employee_user, time(8), None)
    r = employee_client.post("/api/time-entries/clock-out", json={})
    assert r.status_code == 200, r.text
    _no_repeat(core_calls)
    _k1(_db_session, e.id)


def test_change_request_create(_db_session, employee_user, employee_client, core_calls):
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8), time(12))
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id),
        "proposed_date": MON.isoformat(), "proposed_start_time": "08:00",
        "proposed_end_time": "18:00", "proposed_break_minutes": 0, "reason": "vergessen"})
    assert r.status_code == 201, r.text
    _no_repeat(core_calls)


@pytest.mark.parametrize("kind", ["create", "update"])
def test_change_request_approval(_db_session, employee_user, admin_client, core_calls, kind):
    """Bis zu vier Kappungen (Duplikat-Sonde, Vorprüfung, Segmente, Schreiben)
    mit identischen Eingaben → eine."""
    _blocks(_db_session, employee_user)
    e = _entry(_db_session, employee_user, time(8), time(12)) if kind == "update" else None
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="time_entry",
        request_type=ChangeRequestType.UPDATE if e else ChangeRequestType.CREATE,
        status=ChangeRequestStatus.PENDING, time_entry_id=e.id if e else None,
        proposed_date=MON, proposed_start_time=time(8), proposed_end_time=time(18),
        proposed_break_minutes=0, reason="vergessen")
    if e is not None:
        cr.original_date, cr.original_start_time, cr.original_end_time = e.date, e.start_time, e.end_time
        cr.original_break_minutes, cr.original_uncredited_minutes = 0, 0
    _db_session.add(cr)
    _db_session.commit()
    core_calls.clear()
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert r.status_code == 200, r.text
    _no_repeat(core_calls)
    _db_session.expire_all()
    _k1(_db_session, _db_session.get(ChangeRequest, cr.id).time_entry_id)


def test_xls_preview_and_confirm(db, test_user, test_admin, core_calls):
    from app.services.xls_import_service import execute_import, parse_xls
    from tests.test_xls_blocks import _xls
    from tests.test_xls_import_service import _dt

    _blocks(db, test_user)
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 18, 0))), test_user.id, db)
    _no_repeat(core_calls)
    assert (row.start_time, row.end_time, row.uncredited_minutes) == (time(8), time(18), 150)

    core_calls.clear()
    execute_import(test_user.id, [row], overwrite=False, db=db, changed_by_id=test_admin.id,
                   filename="t.xls", tenant_id=DEFAULT_TENANT_ID)
    _no_repeat(core_calls)
    (e,) = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).all()
    _k1(db, e.id)
