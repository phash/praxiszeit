"""P1 Fix-Runde 1 (Minor 6): ein Lösch-Antrag für einen Betriebsferien-Tag
(``absence.closure_id`` gesetzt) wird beim Stellen mit 400 abgelehnt —
Betriebsferien-Tage ändert nur die Verwaltung (wie ``absences.delete_absence``
mit ``CLOSURE_ABSENCE_DELETE_DETAIL``). Die Oberfläche bietet den Weg dort nicht
an; der Server sperrt ihn trotzdem."""
from datetime import date

from app.models import Absence, AbsenceType, ChangeRequest, CompanyClosure
from app.routers import change_requests as cr_router
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)

TODAY = date(2026, 6, 10)
PAST = date(2026, 6, 8)


def _freeze(monkeypatch):
    monkeypatch.setattr(cr_router, "today_local", lambda: TODAY)


def _absence(db, user, closure_id=None):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=PAST, type=AbsenceType.VACATION,
                hours=8.0, half_day=False, closure_id=closure_id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _closure(db, admin):
    c = CompanyClosure(tenant_id=DEFAULT_TENANT_ID, name="Sommer", start_date=PAST, end_date=PAST,
                       created_by=admin.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _request(client, absence):
    return client.post("/api/change-requests/", json={
        "request_type": "delete", "entry_kind": "absence", "absence_id": str(absence.id),
        "reason": "war doch da"})


def test_delete_request_for_closure_day_is_rejected(_db_session, employee_user, admin_user,
                                                    employee_client, monkeypatch):
    _freeze(monkeypatch)
    a = _absence(_db_session, employee_user, _closure(_db_session, admin_user).id)
    r = _request(employee_client, a)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == cr_router.CLOSURE_ABSENCE_CR_DETAIL
    assert _db_session.query(ChangeRequest).count() == 0


def test_delete_request_for_normal_absence_still_works(_db_session, employee_user,
                                                       employee_client, monkeypatch):
    _freeze(monkeypatch)
    r = _request(employee_client, _absence(_db_session, employee_user))
    assert r.status_code in (200, 201), r.text
    assert _db_session.query(ChangeRequest).count() == 1
