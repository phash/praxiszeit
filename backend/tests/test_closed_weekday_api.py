"""Kundenfall 2026-10-30 über die API: Arbeitszeit ab Stichtag von „Mo 07:30–13:00
+ 15:00–18:00" auf „Di 07:30–13:00, Do 15:00–18:00" umstellen. Danach zählt
Arbeit am Montag erst nach Anerkennung; das Frontend erfährt den Tag ohne
Blöcke über ``blockless_workday`` (``/clock-status``, ``/day-blocks``)."""
from datetime import date, datetime, time

import pytest

import app.routers.time_entries as te
from app.middleware.auth import require_admin
from app.services import timezone_service, work_window_service as wws
from tests.test_endpoints import test_app
from tests.wh_change_helpers import add_row, admin_client, freeze
from tests.work_blocks_fixtures import block_week

OLD_WEEK = block_week(mon=[("07:30", "13:00"), ("15:00", "18:00")])
NEW_WEEK = block_week(tue=[("07:30", "13:00")], thu=[("15:00", "18:00")])
CHANGE_DAY = date(2026, 10, 8)     # Do — Änderung wird eingetragen
EFFECTIVE = date(2026, 10, 12)     # Mo — neue Zeiten gelten ab hier
NEXT_MON = date(2026, 10, 19)
NEXT_TUE = date(2026, 10, 20)


def _at(monkeypatch, d, at=time(18, 0)):
    freeze(monkeypatch, d, at)
    monkeypatch.setattr(te, "_now_local", lambda: datetime.combine(d, at, tzinfo=timezone_service.LOCAL_TZ))


@pytest.fixture
def switched(db, test_user, test_admin, monkeypatch):
    add_row(db, test_user, date(2026, 1, 1), week=OLD_WEEK)
    _at(monkeypatch, CHANGE_DAY)
    admin = admin_client(db, test_admin)
    resp = admin.post(f"/api/admin/users/{test_user.id}/working-hours-changes",
                      json={"effective_from": EFFECTIVE.isoformat(), "blocks": NEW_WEEK})
    test_app.dependency_overrides.clear()
    assert resp.status_code == 201, resp.text
    employee = admin_client(db, test_user)
    del test_app.dependency_overrides[require_admin]
    yield employee
    test_app.dependency_overrides.clear()


def _create(client, d, start, end):
    resp = client.post("/api/time-entries", json={
        "date": d.isoformat(), "start_time": start, "end_time": end, "break_minutes": 0})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_monday_after_the_switch_credits_nothing(switched, monkeypatch):
    _at(monkeypatch, NEXT_MON)
    body = _create(switched, NEXT_MON, "07:30", "13:00")
    assert float(body["net_hours"]) == 0.0
    assert any(wws.CLOSED_DAY_TEXT in w and wws.EMPLOYEE_CREDIT_HINT in w for w in body["warnings"]), body


def test_tuesday_after_the_switch_is_clamped_to_its_block(switched, monkeypatch):
    _at(monkeypatch, NEXT_TUE)
    body = _create(switched, NEXT_TUE, "07:00", "13:30")
    assert (body["start_time"][:5], body["end_time"][:5], float(body["net_hours"])) == ("07:15", "13:15", 6.0)


def test_clock_status_and_day_blocks_report_the_closed_day(switched, monkeypatch):
    _at(monkeypatch, NEXT_MON, time(9, 0))
    status = switched.get("/api/time-entries/clock-status").json()
    assert (status["blocks_today"], status["blockless_workday"]) == ([], True)
    day = switched.get(f"/api/time-entries/day-blocks?date={NEXT_TUE.isoformat()}").json()
    assert (day["blocks"], day["blockless_workday"]) == ([{"start": "07:30", "end": "13:00"}], False)
    sat = switched.get("/api/time-entries/day-blocks?date=2026-10-24").json()
    assert (sat["blocks"], sat["blockless_workday"]) == ([], False)


def test_running_entry_on_a_closed_day_counts_zero(switched, monkeypatch):
    _at(monkeypatch, NEXT_MON, time(8, 0))
    assert switched.post("/api/time-entries/clock-in", json={}).status_code in (200, 201)
    _at(monkeypatch, NEXT_MON, time(11, 0))
    status = switched.get("/api/time-entries/clock-status").json()
    assert (status["is_clocked_in"], status["today_net_minutes"]) == (True, 0)


# Release-Review 1.21 (Fund 2): ein auf 0 h zusammengezogener Eintrag
# (Beginn = Ende, Rohende bleibt) muss bearbeitbar bleiben. Eine reine
# Notiz-Änderung darf nicht am gespeicherten Paar scheitern; die Formulare
# belegen das Rohende vor (Frontend), ein Antrag mit dem gespeicherten Paar
# ist derselbe Eintrag (``unclamp_input``/``end_input_for``).
def _collapsed_monday(switched, monkeypatch):
    _at(monkeypatch, NEXT_MON)
    body = _create(switched, NEXT_MON, "08:00", "12:00")
    assert (body["start_time"][:5], body["end_time"][:5]) == ("08:00", "08:00")
    return body["id"]


def test_employee_can_edit_note_of_collapsed_entry(switched, monkeypatch):
    eid = _collapsed_monday(switched, monkeypatch)
    r = switched.put(f"/api/time-entries/{eid}", json={"note": "nur Notiz"})
    assert r.status_code == 200, r.text
    r = switched.put(f"/api/time-entries/{eid}", json={
        "date": NEXT_MON.isoformat(), "start_time": "08:00", "end_time": "12:00", "break_minutes": 0,
        "note": "Formular mit Rohende"})
    assert r.status_code == 200, r.text
    assert (r.json()["start_time"][:5], r.json()["end_time"][:5], r.json()["raw_end_time"][:5]) == (
        "08:00", "08:00", "12:00")


def test_change_request_echoing_the_collapsed_pair_is_accepted(switched, monkeypatch):
    eid = _collapsed_monday(switched, monkeypatch)
    _at(monkeypatch, NEXT_TUE)
    r = switched.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": eid, "proposed_date": NEXT_MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "08:00", "proposed_break_minutes": 0,
        "reason": "Pause korrigiert"})
    assert r.status_code == 201, r.text


def test_real_end_before_start_is_still_rejected(switched, monkeypatch):
    eid = _collapsed_monday(switched, monkeypatch)
    r = switched.put(f"/api/time-entries/{eid}", json={"start_time": "10:00", "end_time": "09:00"})
    assert r.status_code in (400, 422)


# Release-Review 1.21 (Fund 3): ein Eintrag von vor 1.21 an einem Werktag ohne
# Blöcke (ungekappt gespeichert, ohne Rohstempel) wird beim Speichern mit der
# neuen Regel neu gerechnet — wie ein Feiertagseintrag nach #484. Das darf nie
# still passieren: die Antwort trägt den Hinweis.
def _legacy_entry(db, user):
    from app.models import TimeEntry
    from tests.conftest import DEFAULT_TENANT_ID
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=NEXT_MON, start_time=time(8),
                  end_time=time(16), break_minutes=30)
    db.add(e)
    db.commit()
    return e


def test_admin_unchanged_save_of_old_entry_warns(db, test_user, test_admin, switched, monkeypatch):
    e = _legacy_entry(db, test_user)
    _at(monkeypatch, NEXT_TUE)
    admin = admin_client(db, test_admin)
    r = admin.put(f"/api/admin/time-entries/{e.id}", json={
        "date": NEXT_MON.isoformat(), "start_time": "08:00", "end_time": "16:00", "break_minutes": 30,
        "note": "nur Notiz"})
    test_app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert float(r.json()["net_hours"]) == 0.0
    assert any(wws.CLOSED_DAY_TEXT in w for w in r.json().get("warnings") or []), r.json()


def test_employee_unchanged_save_of_old_entry_warns(db, test_user, switched, monkeypatch):
    e = _legacy_entry(db, test_user)
    _at(monkeypatch, NEXT_MON)
    r = switched.put(f"/api/time-entries/{e.id}", json={
        "date": NEXT_MON.isoformat(), "start_time": "08:00", "end_time": "16:00", "break_minutes": 30,
        "note": "nur Notiz"})
    assert r.status_code == 200, r.text
    assert float(r.json()["net_hours"]) == 0.0
    assert any(wws.CLOSED_DAY_TEXT in w for w in r.json().get("warnings") or []), r.json()


# Release-Review 1.21 (Fund 1): vergessen auszustempeln an einem Werktag ohne
# Blöcke — der Auto-Close zieht den Eintrag auf 0 h zusammen (Rohende 23:59 ist
# kein Stempel, also „nichts nicht angerechnet"). „Anrechnung beantragen" mit
# dem tatsächlichen Ende muss trotzdem gehen.
def test_credit_request_for_auto_closed_collapsed_entry(db, test_user, test_admin, switched, monkeypatch):
    from app.models import TimeEntry
    from tests.conftest import DEFAULT_TENANT_ID
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=NEXT_MON, start_time=time(8),
                  end_time=time(8), raw_end_time=time(23, 59), auto_closed=True, break_minutes=0,
                  clamp_grace_minutes=15)
    db.add(e)
    db.commit()
    _at(monkeypatch, NEXT_TUE)
    r = switched.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id), "proposed_date": NEXT_MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "12:00", "proposed_break_minutes": 0,
        "reason": "Vertretung am freien Tag", "request_credit_override": True})
    assert r.status_code == 201, r.text
    test_app.dependency_overrides.clear()
    admin = admin_client(db, test_admin)
    r = admin.post(f"/api/admin/change-requests/{r.json()['id']}/review",
                   json={"action": "approve", "grant_credit_override": True})
    test_app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    db.refresh(e)
    assert (e.start_time, e.end_time, e.credit_override, float(e.net_hours)) == (time(8), time(12), True, 4.0)


def test_credit_request_without_actual_end_is_still_rejected(db, test_user, switched, monkeypatch):
    from app.models import TimeEntry
    from tests.conftest import DEFAULT_TENANT_ID
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=NEXT_MON, start_time=time(8),
                  end_time=time(8), raw_end_time=time(23, 59), auto_closed=True, break_minutes=0)
    db.add(e)
    db.commit()
    _at(monkeypatch, NEXT_TUE)
    r = switched.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(e.id), "proposed_date": NEXT_MON.isoformat(),
        "proposed_start_time": "08:00", "proposed_end_time": "08:00", "proposed_break_minutes": 0,
        "reason": "x", "request_credit_override": True})
    assert r.status_code == 400
