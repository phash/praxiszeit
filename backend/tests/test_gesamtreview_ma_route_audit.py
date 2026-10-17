"""Gesamtreview 1.20 (Review-Fund 3): die MA-Route protokolliert Anlegen und
Bearbeiten wie die Verwaltungsroute.

``POST``/``PUT /api/time-entries`` schrieben nur bei einer §4-Ausnahme eine
Zeile ins Änderungsprotokoll. Admins nutzen die Route über die Zeiterfassung
für ihre eigenen Einträge an jedem Tag — eine nachträgliche Änderung eines
vergangenen Tages (auch die Korrektur des Auto-Close-Endes, P18, oder ein
Datumswechsel mit Neukappung, E39) blieb dort ohne Spur, während dieselbe
Änderung über ``/api/admin/time-entries`` immer eine Zeile ``manual`` schreibt.
Löschen und Ausstempeln auf der MA-Route protokollierten schon immer.
"""
from datetime import date, time

import pytest

from app.models import ChangeRequest, TimeEntry, TimeEntryAuditLog
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON

LAST_MON = date(2026, 5, 25)


def _entry(db, user, d, start, end, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def _logs(db, entry_id=None):
    db.expire_all()
    q = db.query(TimeEntryAuditLog)
    if entry_id is not None:
        q = q.filter(TimeEntryAuditLog.time_entry_id == entry_id)
    return q.all()


@pytest.fixture
def today_monday(monkeypatch):
    import app.routers.time_entries as te
    monkeypatch.setattr(te, "_today_local", lambda: MON)


def test_admin_self_edit_of_past_entry_is_logged(_db_session, admin_user, admin_client):
    """Eine Admin setzt in ihrer Zeiterfassung den Beginn eines Eintrags vom
    letzten Montag von 08:00 auf 06:00."""
    e = _entry(_db_session, admin_user, LAST_MON, time(8, 0), time(12, 0), note="alt")

    r = admin_client.put(f"/api/time-entries/{e.id}", json={
        "date": LAST_MON.isoformat(), "start_time": "06:00", "end_time": "12:00",
        "break_minutes": 0, "note": "neu",
    })

    assert r.status_code == 200, r.text
    (log,) = _logs(_db_session, e.id)
    assert log.action == "update"
    assert log.source == "manual"
    assert log.user_id == admin_user.id
    assert log.changed_by == admin_user.id
    assert (log.old_date, log.old_start_time, log.old_end_time) == (LAST_MON, time(8, 0), time(12, 0))
    assert (log.new_date, log.new_start_time, log.new_end_time) == (LAST_MON, time(6, 0), time(12, 0))
    assert (log.old_note, log.new_note) == ("alt", "neu")


def test_admin_corrects_auto_closed_end_is_logged(_db_session, admin_user, admin_client):
    """P18: aus dem synthetischen 23:59 wird ein echtes Ende — mit Spur."""
    admin_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _entry(_db_session, admin_user, MON, time(8, 0), time(18, 15),
               raw_end_time=time(23, 59), auto_closed=True, break_minutes=60)

    r = admin_client.put(f"/api/time-entries/{e.id}", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "17:30",
        "break_minutes": 60,
    })

    assert r.status_code == 200, r.text
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id).auto_closed is False
    (log,) = _logs(_db_session, e.id)
    assert log.action == "update"
    assert log.source == "manual"
    assert (log.old_end_time, log.new_end_time) == (time(18, 15), time(17, 30))


def test_admin_edit_of_other_persons_entry_on_ma_route_is_logged(
    _db_session, employee_user, admin_user, admin_client,
):
    """Die Route lässt Admins auch fremde Einträge bearbeiten — protokolliert
    wird die Person des Eintrags, geändert von der Admin."""
    e = _entry(_db_session, employee_user, LAST_MON, time(8, 0), time(12, 0))

    r = admin_client.put(f"/api/time-entries/{e.id}", json={"break_minutes": 15})

    assert r.status_code == 200, r.text
    (log,) = _logs(_db_session, e.id)
    assert log.user_id == employee_user.id
    assert log.changed_by == admin_user.id
    assert (log.old_break_minutes, log.new_break_minutes) == (0, 15)


def test_employee_same_day_edit_is_logged(
    _db_session, employee_user, employee_client, today_monday,
):
    e = _entry(_db_session, employee_user, MON, time(8, 0), time(12, 0))

    r = employee_client.put(f"/api/time-entries/{e.id}", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "11:30",
        "break_minutes": 0,
    })

    assert r.status_code == 200, r.text
    (log,) = _logs(_db_session, e.id)
    assert log.action == "update"
    assert log.source == "manual"
    assert log.changed_by == employee_user.id
    assert (log.old_end_time, log.new_end_time) == (time(12, 0), time(11, 30))


def test_waiver_edit_writes_one_row_with_waiver_source(
    _db_session, employee_user, employee_client, today_monday,
):
    """§4-Ausnahme ohne Genehmigungspflicht: genau EINE Zeile, Quelle wie bisher."""
    e = _entry(_db_session, employee_user, MON, time(8, 0), time(12, 0))

    r = employee_client.put(f"/api/time-entries/{e.id}", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "15:00",
        "break_minutes": 0, "break_waiver_reason": "Notfall",
    })

    assert r.status_code == 200, r.text
    (log,) = _logs(_db_session, e.id)
    assert log.source == "break_waiver"


def test_edit_filed_as_request_writes_no_row(
    _db_session, employee_user, employee_client, today_monday, monkeypatch,
):
    """202 (Genehmigungspflicht): nichts gespeichert, also nichts protokolliert —
    der Antrag protokolliert bei der Genehmigung."""
    import app.routers.time_entries as te
    monkeypatch.setattr(te, "_break_exception_requires_approval", lambda db, tid: True)
    e = _entry(_db_session, employee_user, MON, time(8, 0), time(12, 0))

    r = employee_client.put(f"/api/time-entries/{e.id}", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "15:00",
        "break_minutes": 0, "break_waiver_reason": "Notfall",
    })

    assert r.status_code == 202, r.text
    assert _logs(_db_session) == []
    assert _db_session.query(ChangeRequest).count() == 1


def test_admin_create_on_ma_route_is_logged(_db_session, admin_user, admin_client):
    r = admin_client.post("/api/time-entries/", json={
        "date": LAST_MON.isoformat(), "start_time": "08:00", "end_time": "12:00",
        "break_minutes": 0, "note": "nachgetragen",
    })

    assert r.status_code == 201, r.text
    entry_id = r.json()["id"]
    (log,) = _logs(_db_session)
    assert str(log.time_entry_id) == str(entry_id)
    assert log.action == "create"
    assert log.source == "manual"
    assert log.changed_by == admin_user.id
    assert (log.new_date, log.new_start_time, log.new_end_time) == (LAST_MON, time(8, 0), time(12, 0))
    assert log.new_note == "nachgetragen"


def test_employee_create_with_waiver_writes_one_row(
    _db_session, employee_user, employee_client, today_monday,
):
    r = employee_client.post("/api/time-entries/", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "15:00",
        "break_minutes": 0, "break_waiver_reason": "Notfall",
    })

    assert r.status_code == 201, r.text
    (log,) = _logs(_db_session)
    assert log.action == "create"
    assert log.source == "break_waiver"
