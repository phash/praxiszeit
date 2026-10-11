"""Gesamtreview 1.20, Bündel B1 (Punkt 3; PR1-Sicherheitsprüfung F2): Sekunden
in manuell eingegebenen Zeiten.

Stempeln (``clock_in``/``clock_out``) und die XLS-Datei liefern Minuten, die
Oberfläche ebenso. Nur über die API kamen Sekunden an — und dort rechnete das
System uneinheitlich: ``net_hours`` zählte sie, die Lückenüberlappung
(``_min``) und die Vergleiche gegen gespeicherte Zeiten (``same_minute``)
nicht, ``unclamp_input`` dagegen exakt. Folgen: 30 Sekunden Lücke wurden
angerechnet, und ein „07:45:30" (= das gekappte 07:45) galt als neue Eingabe,
die den Rohstempel 07:30 löschte (§16). Jetzt schneiden alle manuellen
Eingangsschemata (Eintrag anlegen/bearbeiten in beiden Rollen, Änderungsantrag,
XLS-Bestätigung) Sekunden ab — wie Stempeln und XLS-Datei.
"""
from datetime import date, time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import ChangeRequest, TimeEntry
from app.schemas.change_request import ChangeRequestCreate
from app.schemas.time_entry import TimeEntryCreate, TimeEntryUpdate
from app.services.xls_import_service import ImportedEntry, ImportedEntryIn, execute_import
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON

import app.routers.time_entries as te


# ── Schemata ────────────────────────────────────────────────────────────────

def test_create_schema_drops_seconds():
    m = TimeEntryCreate(date=MON, start_time="08:00:30", end_time="12:00:45")
    assert (m.start_time, m.end_time) == (time(8), time(12))


def test_create_schema_orders_on_minutes():
    """08:00:10–08:00:50 ist auf die Minute dieselbe Zeit — kein Eintrag."""
    with pytest.raises(ValidationError, match="Endzeit muss nach Startzeit liegen"):
        TimeEntryCreate(date=MON, start_time="08:00:10", end_time="08:00:50")


def test_update_schema_drops_seconds():
    m = TimeEntryUpdate(start_time="07:45:30", end_time="23:59:30")
    assert (m.start_time, m.end_time) == (time(7, 45), time(23, 59))


def test_change_request_schema_drops_seconds():
    m = ChangeRequestCreate(request_type="create", proposed_date=MON,
                            proposed_start_time="08:00:30", proposed_end_time="12:00:45",
                            reason="x")
    assert (m.proposed_start_time, m.proposed_end_time) == (time(8), time(12))


def test_import_schema_drops_seconds():
    m = ImportedEntryIn(date=MON, start_time="08:00:30", end_time="12:00:45", break_minutes=0,
                        note=None, has_conflict=False, arbzg_warnings=[],
                        raw_start_time="07:30:15", raw_end_time="19:00:59")
    assert (m.start_time, m.end_time, m.raw_start_time, m.raw_end_time) == (
        time(8), time(12), time(7, 30), time(19))


# ── Schreibwege ─────────────────────────────────────────────────────────────

def _stored(db):
    db.expire_all()
    return db.query(TimeEntry).one()


def test_admin_create_stores_minutes(_db_session, employee_user, admin_client):
    r = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "08:00:30", "end_time": "12:00:45"})
    assert r.status_code == 201, r.text
    e = _stored(_db_session)
    assert (e.start_time, e.end_time, e.net_hours) == (time(8), time(12), Decimal("4.0"))


def test_gap_overlap_and_net_agree(_db_session, employee_user, admin_client):
    """Ende 12:30:30 in der Lücke 12:15–14:45: 15 Minuten nicht angerechnet,
    angerechnet 4:15 h — nicht 4:15:30 (net 4.26)."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    r = admin_client.post(f"/api/admin/users/{employee_user.id}/time-entries", json={
        "date": MON.isoformat(), "start_time": "08:00", "end_time": "12:30:30"})
    assert r.status_code == 201, r.text
    e = _stored(_db_session)
    assert (e.end_time, e.uncredited_minutes, e.net_hours) == (time(12, 30), 15, Decimal("4.25"))


@pytest.mark.parametrize("route", ["/api/admin/time-entries", "/api/time-entries"],
                         ids=["admin-route", "ma-route"])
def test_resubmitted_clamped_start_with_seconds_keeps_the_raw_stamp(
        _db_session, employee_user, admin_client, route):
    """Das gekappte 07:45 mit Sekunden zurückgeschickt ist dasselbe 07:45 — der
    Rohstempel 07:30 (§16, Grundlage von §5) bleibt."""
    employee_user.work_blocks = K_BLOCKS
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                  start_time=time(7, 45), end_time=time(12), raw_start_time=time(7, 30),
                  break_minutes=0, clamp_grace_minutes=15)
    _db_session.add(e)
    _db_session.commit()
    r = admin_client.put(f"{route}/{e.id}", json={"start_time": "07:45:30", "note": "geprüft"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.start_time, e.raw_start_time, e.note) == (time(7, 45), time(7, 30), "geprüft")


def test_employee_create_stores_minutes(_db_session, employee_user, employee_client, monkeypatch):
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    r = employee_client.post("/api/time-entries", json={
        "date": MON.isoformat(), "start_time": "08:00:30", "end_time": "12:00:45"})
    assert r.status_code == 201, r.text
    e = _stored(_db_session)
    assert (e.start_time, e.end_time) == (time(8), time(12))


def test_change_request_stores_minutes(_db_session, employee_user, employee_client):
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": MON.isoformat(),
        "proposed_start_time": "08:00:30", "proposed_end_time": "12:00:45",
        "proposed_break_minutes": 0, "reason": "vergessen"})
    assert r.status_code == 201, r.text
    _db_session.expire_all()
    cr = _db_session.query(ChangeRequest).one()
    assert (cr.proposed_start_time, cr.proposed_end_time) == (time(8), time(12))


def test_import_confirm_stores_minutes(db, test_user, test_admin):
    row = ImportedEntry(date=date(2026, 6, 1), start_time=time(8, 0, 30), end_time=time(12, 0, 45),
                        break_minutes=0, note=None, has_conflict=False, arbzg_warnings=[])
    execute_import(test_user.id, [row], overwrite=False, db=db, changed_by_id=test_admin.id,
                   filename="t.xls", tenant_id=DEFAULT_TENANT_ID)
    e = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).one()
    assert (e.start_time, e.end_time) == (time(8), time(12))
