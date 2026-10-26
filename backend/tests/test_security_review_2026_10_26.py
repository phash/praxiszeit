"""Security-Review 2026-10-26 (Lane: Zeiteinträge/Journal/Impersonation).

1. Impersonation ist auch für GET-Pfade mit Nebenwirkung lesend:
   (a) ``/clock-status`` schließt unter Impersonation keinen alten Eintrag,
   (b) ``/journal/me`` maskiert unter Impersonation Gesundheitsdaten (Art. 9),
   (c) ``/me/data-export`` ist unter Impersonation gesperrt (403).
2. Mitarbeitende löschen über ``POST /absences`` keine Zeiteinträge vergangener
   Tage (Änderungsantrag).
3. Ein CREATE-Änderungsantrag trägt keine ``time_entry_id``; die Anreicherung
   zeigt nur Einträge der antragstellenden Person.
4. ``admin_delete_time_entry`` nimmt zuerst die Ankersperre (P5).
5. Die Art.-9-Protokollzeile des Admin-Journals nennt die betroffene Person.
"""
import uuid
from datetime import date, time, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import app.routers.absences as absences_router
import app.routers.admin_time_entries as ate
import app.routers.time_entries as te
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import (
    Absence, AbsenceType, ChangeRequest, TimeEntry, TimeEntryAuditLog, User,
)
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.user import UserRole
from app.routers import admin_helpers
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
    endpoints_app,
)

MON = date(2026, 6, 1)


def _entry(db, user, d, start, end, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                  start_time=start, end_time=end, break_minutes=0, **kw)
    db.add(e)
    db.commit()
    return e


def _impersonate(app, user):
    """get_current_user wie die echte Abhängigkeit unter einem Impersonation-
    Token: Nutzer = Mitarbeitende Person, ``request.state.is_impersonating``."""
    def _override(request: Request):
        request.state.is_impersonating = True
        request.state.impersonator_id = str(uuid.uuid4())
        return user
    app.dependency_overrides[get_current_user] = _override


# ─── 1a: clock-status ────────────────────────────────────────────────


def test_clock_status_under_impersonation_does_not_auto_close(
        _db_session, employee_user, employee_client, monkeypatch):
    stale = _entry(_db_session, employee_user, MON, time(8), None)
    monkeypatch.setattr(te, "_today_local", lambda: MON + timedelta(days=1))
    _impersonate(endpoints_app, employee_user)
    r = employee_client.get("/api/time-entries/clock-status")
    assert r.status_code == 200, r.text
    assert r.json()["is_clocked_in"] is False
    _db_session.expire_all()
    e = _db_session.get(TimeEntry, stale.id)
    assert e.end_time is None
    assert not e.auto_closed
    assert _db_session.query(TimeEntryAuditLog).count() == 0


def test_clock_status_without_impersonation_still_auto_closes(
        _db_session, employee_user, employee_client, monkeypatch):
    stale = _entry(_db_session, employee_user, MON, time(8), None)
    monkeypatch.setattr(te, "_today_local", lambda: MON + timedelta(days=1))
    assert employee_client.get("/api/time-entries/clock-status").status_code == 200
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, stale.id).end_time is not None


# ─── 1b: journal/me ──────────────────────────────────────────────────


def _sick_absence(db, user, d):
    db.add(Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                   type=AbsenceType.SICK, hours=8.0))
    db.commit()


def test_journal_me_masks_health_data_under_impersonation(
        _db_session, employee_user, employee_client):
    _sick_absence(_db_session, employee_user, date(2026, 3, 10))
    _impersonate(endpoints_app, employee_user)
    body = employee_client.get("/api/journal/me?year=2026&month=3").json()
    day = next(d for d in body["days"] if d["date"] == "2026-03-10")
    assert day["type"] == "absent"
    assert day["absences"][0]["type"] == "absent"


def test_journal_me_own_view_shows_sick(_db_session, employee_user, employee_client):
    _sick_absence(_db_session, employee_user, date(2026, 3, 10))
    body = employee_client.get("/api/journal/me?year=2026&month=3").json()
    day = next(d for d in body["days"] if d["date"] == "2026-03-10")
    assert day["type"] == "sick"


# ─── 1c: me/data-export ──────────────────────────────────────────────


@pytest.fixture
def me_app(_db_session):
    from app.core.limiter import limiter
    from app.routers import me
    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.include_router(me.router)

    def _override_db():
        yield _db_session
    app.dependency_overrides[get_db] = _override_db
    return app


def test_data_export_forbidden_under_impersonation(_db_session, employee_user, me_app):
    _impersonate(me_app, employee_user)
    r = TestClient(me_app).get("/api/me/data-export")
    assert r.status_code == 403, r.text
    assert _db_session.query(TimeEntryAuditLog).count() == 0


def test_data_export_allowed_for_self(_db_session, employee_user, me_app):
    me_app.dependency_overrides[get_current_user] = lambda: employee_user
    r = TestClient(me_app).get("/api/me/data-export")
    assert r.status_code == 200, r.text


# ─── 2: Abwesenheit löscht keine Einträge vergangener Tage ───────────


def test_employee_past_absence_does_not_delete_entries(
        _db_session, employee_user, employee_client, monkeypatch):
    monkeypatch.setattr(absences_router, "today_local", lambda: MON + timedelta(days=7))
    e = _entry(_db_session, employee_user, MON, time(8), time(12))
    r = employee_client.post("/api/absences/", json={
        "date": MON.isoformat(), "type": "sick", "hours": 8})
    assert r.status_code == 400, r.text
    assert "Änderungsantrag" in r.json()["detail"]
    assert "01.06.2026" in r.json()["detail"]
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is not None
    assert _db_session.query(Absence).count() == 0


def test_employee_past_absence_without_entries_still_allowed(
        _db_session, employee_user, employee_client, monkeypatch):
    """Krankmeldung für gestern ohne Einträge bleibt direkt buchbar."""
    monkeypatch.setattr(absences_router, "today_local", lambda: MON + timedelta(days=7))
    r = employee_client.post("/api/absences/", json={
        "date": MON.isoformat(), "type": "sick", "hours": 8})
    assert r.status_code == 201, r.text


def test_employee_past_absence_keeping_entries_allowed(
        _db_session, employee_user, employee_client, monkeypatch):
    monkeypatch.setattr(absences_router, "today_local", lambda: MON + timedelta(days=7))
    e = _entry(_db_session, employee_user, MON, time(8), time(12))
    r = employee_client.post("/api/absences/", json={
        "date": MON.isoformat(), "type": "sick", "hours": 8, "keep_time_entries": True})
    assert r.status_code == 201, r.text
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is not None


def test_employee_today_absence_still_replaces_entries(
        _db_session, employee_user, employee_client, monkeypatch):
    monkeypatch.setattr(absences_router, "today_local", lambda: MON)
    e = _entry(_db_session, employee_user, MON, time(8), time(12))
    r = employee_client.post("/api/absences/", json={
        "date": MON.isoformat(), "type": "sick", "hours": 8})
    assert r.status_code == 201, r.text
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is None


def test_admin_past_absence_still_replaces_entries(
        _db_session, employee_user, admin_client, monkeypatch):
    monkeypatch.setattr(absences_router, "today_local", lambda: MON + timedelta(days=7))
    e = _entry(_db_session, employee_user, MON, time(8), time(12))
    r = admin_client.post("/api/absences/", json={
        "user_id": str(employee_user.id), "date": MON.isoformat(), "type": "sick", "hours": 8})
    assert r.status_code == 201, r.text
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is None


# ─── 3: CREATE-Antrag mit fremder time_entry_id ──────────────────────


def _colleague(db):
    u = User(username="kollegin", email="k@test.de",
             password_hash=auth_service.hash_password("Kollegin2025!x"),
             first_name="K", last_name="L", role=UserRole.EMPLOYEE, weekly_hours=40.0,
             vacation_days=30, work_days_per_week=5, is_active=True,
             tenant_id=DEFAULT_TENANT_ID)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_create_cr_ignores_foreign_time_entry_id(_db_session, employee_user, employee_client):
    other = _colleague(_db_session)
    foreign = _entry(_db_session, other, MON, time(7, 13), time(15, 47),
                     raw_start_time=time(6, 1), raw_end_time=time(18, 2))
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "entry_kind": "time_entry",
        "time_entry_id": str(foreign.id), "reason": "Nachtrag",
        "proposed_date": MON.isoformat(), "proposed_start_time": "08:00",
        "proposed_end_time": "12:00", "proposed_break_minutes": 0,
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body.get("time_entry_id") is None
    assert body.get("entry_raw_start_time") is None
    assert body.get("entry_start_time") is None
    cr = _db_session.query(ChangeRequest).one()
    assert cr.time_entry_id is None


def test_enrichment_hides_foreign_entry_of_stored_cr(_db_session, employee_user, employee_client):
    """Bestand: ein schon gespeicherter Antrag mit fremder ``time_entry_id``
    zeigt deren Zeiten nicht."""
    other = _colleague(_db_session)
    foreign = _entry(_db_session, other, MON, time(7, 13), time(15, 47),
                     raw_start_time=time(6, 1), raw_end_time=time(18, 2))
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
                       entry_kind="time_entry", request_type=ChangeRequestType.CREATE,
                       status=ChangeRequestStatus.PENDING, time_entry_id=foreign.id,
                       proposed_date=MON, proposed_start_time=time(8),
                       proposed_end_time=time(12), proposed_break_minutes=0, reason="x")
    _db_session.add(cr)
    _db_session.commit()
    rows = admin_helpers._enrich_cr_responses([cr], _db_session)
    assert rows[0].entry_raw_start_time is None
    assert rows[0].entry_start_time is None
    assert rows[0].entry_end_time is None


# ─── 4: admin_delete_time_entry — Ankersperre zuerst ─────────────────


def test_admin_delete_locks_anchor_before_entry(_db_session, employee_user, admin_client,
                                                monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    log = []
    real_lock = admin_helpers.lock_user_row

    def spy_lock(db, tenant_id, user_id):
        log.append(("lock", str(user_id)))
        return real_lock(db, tenant_id, user_id)

    monkeypatch.setattr(ate, "lock_user_row", spy_lock, raising=False)

    def on_execute(state):
        if (state.is_select
                and getattr(state.statement, "_for_update_arg", None) is not None
                and any(m.class_ is TimeEntry for m in state.all_mappers)):
            log.append(("row_lock",))

    e = _entry(_db_session, employee_user, MON, time(8), time(12))
    event.listen(Session, "do_orm_execute", on_execute)
    try:
        r = admin_client.delete(f"/api/admin/time-entries/{e.id}")
    finally:
        event.remove(Session, "do_orm_execute", on_execute)
    assert r.status_code == 204, r.text
    assert log and log[0] == ("lock", str(employee_user.id)), log
    assert ("row_lock",) in log, log


def test_admin_delete_unknown_entry_takes_no_lock(_db_session, admin_client, monkeypatch):
    log = []
    monkeypatch.setattr(ate, "lock_user_row",
                        lambda *a, **kw: log.append("lock"), raising=False)
    r = admin_client.delete(f"/api/admin/time-entries/{uuid.uuid4()}")
    assert r.status_code == 404
    assert log == []


# ─── 5: Art.-9-Protokollzeile nennt die betroffene Person ────────────


def test_admin_journal_health_audit_names_subject(_db_session, employee_user, admin_user,
                                                  admin_client):
    _sick_absence(_db_session, employee_user, date(2026, 3, 10))
    r = admin_client.get(
        f"/api/admin/users/{employee_user.id}/journal?year=2026&month=3&include_health_data=true")
    assert r.status_code == 200, r.text
    row = _db_session.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.action == "health_data_read").one()
    assert str(row.user_id) == str(employee_user.id)
    assert str(row.changed_by) == str(admin_user.id)
