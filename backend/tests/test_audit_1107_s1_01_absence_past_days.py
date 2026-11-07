"""Audit 2026-11-07, S1-01 (#542): Abwesenheiten an vergangenen Tagen.

Mitarbeitende buchen und löschen Abwesenheiten vergangener Tage nur noch per
Änderungsantrag (wie Zeiteinträge). Sie löschen nie eine Abwesenheit, die
jemand anders gebucht hat, und nie eine in einem abgeschlossenen Jahr.
Admins bleiben unverändert. Der Abwesenheits-Antrag für vergangene Tage geht
weiter.
"""
from datetime import date, timedelta

from app.models import Absence, AbsenceType, ChangeRequest, TimeEntryAuditLog
from app.models.year_carryover import YearCarryover
from app.routers import absences as absences_router
from app.routers import change_requests as cr_router
from tests.conftest import DEFAULT_TENANT_ID
from app.middleware.auth import get_current_user
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
    endpoints_app,
)

TODAY = date(2026, 6, 10)  # Mittwoch
PAST = date(2026, 6, 8)    # Montag
FUTURE = date(2026, 6, 15)  # Montag


def _freeze(monkeypatch, today=TODAY):
    monkeypatch.setattr(absences_router, "today_local", lambda: today)
    monkeypatch.setattr(cr_router, "today_local", lambda: today)


def _act_as(user):
    """admin_client und employee_client teilen ``endpoints_app`` — innerhalb
    eines Tests die handelnde Person umschalten."""
    endpoints_app.dependency_overrides[get_current_user] = lambda: user


def _absence(db, user, d, t=AbsenceType.SICK):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=t,
                hours=8.0, half_day=False)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _exists(db, absence_id):
    db.expire_all()
    return db.query(Absence).filter(Absence.id == absence_id).first() is not None


# ── Anlegen ──────────────────────────────────────────────────────────


def test_employee_cannot_book_past_day(_db_session, employee_user, employee_client, monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/absences/", json={
        "date": PAST.isoformat(), "type": "training", "hours": 8})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.PAST_DAY_ABSENCE_DETAIL
    assert _db_session.query(Absence).count() == 0


def test_employee_cannot_book_range_starting_in_past(_db_session, employee_user, employee_client,
                                                     monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/absences/", json={
        "date": PAST.isoformat(), "end_date": FUTURE.isoformat(), "type": "sick", "hours": 8})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.PAST_DAY_ABSENCE_DETAIL
    assert _db_session.query(Absence).count() == 0


def test_employee_can_book_today_and_future(_db_session, employee_user, employee_client,
                                            monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/absences/", json={
        "date": TODAY.isoformat(), "type": "sick", "hours": 8})
    assert r.status_code == 201, r.text
    r = employee_client.post("/api/absences/", json={
        "date": FUTURE.isoformat(), "type": "vacation", "hours": 8})
    assert r.status_code == 201, r.text


def test_admin_books_past_day_unchanged(_db_session, employee_user, admin_client, monkeypatch):
    _freeze(monkeypatch)
    r = admin_client.post("/api/absences/", json={
        "user_id": str(employee_user.id), "date": PAST.isoformat(), "type": "sick", "hours": 8})
    assert r.status_code == 201, r.text


def test_booking_writes_audit_row_with_booker(_db_session, employee_user, admin_user,
                                              admin_client, monkeypatch):
    _freeze(monkeypatch)
    r = admin_client.post("/api/absences/", json={
        "user_id": str(employee_user.id), "date": FUTURE.isoformat(), "type": "vacation",
        "hours": 8})
    assert r.status_code == 201, r.text
    row = _db_session.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.action == "create",
        TimeEntryAuditLog.new_date == FUTURE,
    ).one()
    assert row.changed_by == admin_user.id
    assert row.user_id == employee_user.id
    assert row.new_note.startswith("absence:vacation:")


# ── Löschen ──────────────────────────────────────────────────────────


def test_employee_cannot_delete_past_absence(_db_session, employee_user, employee_client,
                                             monkeypatch):
    _freeze(monkeypatch)
    a = _absence(_db_session, employee_user, PAST)
    r = employee_client.delete(f"/api/absences/{a.id}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.PAST_DAY_ABSENCE_DETAIL
    assert _exists(_db_session, a.id)


def test_employee_cannot_delete_absence_booked_by_admin(_db_session, employee_user,
                                                        admin_user, admin_client,
                                                        monkeypatch):
    _freeze(monkeypatch)
    r = admin_client.post("/api/absences/", json={
        "user_id": str(employee_user.id), "date": FUTURE.isoformat(), "type": "vacation",
        "hours": 8})
    assert r.status_code == 201, r.text
    absence_id = r.json()[0]["id"]
    _act_as(employee_user)
    r = admin_client.delete(f"/api/absences/{absence_id}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.FOREIGN_ABSENCE_DELETE_DETAIL
    assert _exists(_db_session, absence_id)


def test_employee_deletes_own_future_absence(_db_session, employee_user, employee_client,
                                             monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/absences/", json={
        "date": FUTURE.isoformat(), "type": "vacation", "hours": 8})
    assert r.status_code == 201, r.text
    absence_id = r.json()[0]["id"]
    r = employee_client.delete(f"/api/absences/{absence_id}")
    assert r.status_code == 204, r.text
    assert not _exists(_db_session, absence_id)


def test_rebooking_by_employee_after_admin_delete_is_own_again(
        _db_session, employee_user, admin_user, admin_client, monkeypatch):
    """Maßgeblich ist die JÜNGSTE Buchungszeile des Tages."""
    _freeze(monkeypatch)
    r = admin_client.post("/api/absences/", json={
        "user_id": str(employee_user.id), "date": FUTURE.isoformat(), "type": "vacation",
        "hours": 8})
    assert admin_client.delete(f"/api/absences/{r.json()[0]['id']}").status_code == 204
    # Zeitstempel unterscheidbar machen (SQLite: Sekundenauflösung)
    row = _db_session.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.action == "create").one()
    row.created_at = row.created_at - timedelta(minutes=5)
    _db_session.commit()
    _act_as(employee_user)
    r = admin_client.post("/api/absences/", json={
        "date": FUTURE.isoformat(), "type": "vacation", "hours": 8})
    assert r.status_code == 201, r.text
    r = admin_client.delete(f"/api/absences/{r.json()[0]['id']}")
    assert r.status_code == 204, r.text


def test_employee_cannot_delete_in_closed_year(_db_session, employee_user, employee_client,
                                               monkeypatch):
    # Jahresabschluss 2026 schon im Dezember erfolgt; die Abwesenheit liegt danach.
    _freeze(monkeypatch, today=date(2026, 12, 21))
    a = _absence(_db_session, employee_user, date(2026, 12, 22))
    _db_session.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id,
                                  year=2027, overtime_hours=0, vacation_days=0,
                                  source="year_closing"))
    _db_session.commit()
    r = employee_client.delete(f"/api/absences/{a.id}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.CLOSED_YEAR_ABSENCE_DETAIL.format(year=2026)
    assert _exists(_db_session, a.id)
    # Anlegen in dem Jahr ebenso gesperrt.
    r = employee_client.post("/api/absences/", json={
        "date": "2026-12-23", "type": "sick", "hours": 8})
    assert r.status_code == 409, r.text
    assert "2026" in r.json()["detail"]


def test_manual_carryover_does_not_close_year(_db_session, employee_user, employee_client,
                                              monkeypatch):
    _freeze(monkeypatch, today=date(2026, 12, 21))
    a = _absence(_db_session, employee_user, date(2026, 12, 22))
    _db_session.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id,
                                  year=2027, overtime_hours=0, vacation_days=0,
                                  source="manual"))
    _db_session.commit()
    r = employee_client.delete(f"/api/absences/{a.id}")
    assert r.status_code == 204, r.text


def test_admin_deletes_past_absence_unchanged(_db_session, employee_user, admin_client,
                                              monkeypatch):
    _freeze(monkeypatch)
    a = _absence(_db_session, employee_user, PAST)
    r = admin_client.delete(f"/api/absences/{a.id}")
    assert r.status_code == 204, r.text


# ── Der Antragsweg für vergangene Tage bleibt offen ──────────────────


def test_change_request_for_past_absence_still_works(_db_session, employee_user,
                                                     employee_client, monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "entry_kind": "absence", "proposed_date": PAST.isoformat(),
        "proposed_absence_type": "sick", "proposed_absence_hours": 8, "reason": "krank"})
    assert r.status_code in (200, 201), r.text
    a = _absence(_db_session, employee_user, PAST - timedelta(days=7))
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "delete", "entry_kind": "absence", "absence_id": str(a.id),
        "reason": "war doch da"})
    assert r.status_code in (200, 201), r.text
    assert _db_session.query(ChangeRequest).count() == 2
