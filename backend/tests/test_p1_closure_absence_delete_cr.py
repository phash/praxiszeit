"""P1/P2 (Handbuch-Funde): Änderungsanträge auf einen Betriebsferien-Tag
(``absence.closure_id`` gesetzt) werden beim Stellen mit 400 abgelehnt —
Betriebsferien-Tage ändert nur die Verwaltung. Meldung = dieselbe Konstante wie
beim direkten Löschen (``absences.CLOSURE_ABSENCE_DELETE_DETAIL``). Die Prüfung
läuft VOR den übrigen Prüfungen, damit ein Betriebsferien-Tag immer diese Meldung
bekommt (auch heute/Zukunft, auch beim UPDATE-Antrag mit Typ/Stunden)."""
from datetime import date

import pytest

from app.models import Absence, AbsenceType, ChangeRequest, CompanyClosure
from app.routers import absences as absences_router
from app.routers import change_requests as cr_router
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)

TODAY = date(2026, 6, 10)
PAST = date(2026, 6, 8)
FUTURE = date(2026, 6, 15)


def _freeze(monkeypatch):
    monkeypatch.setattr(cr_router, "today_local", lambda: TODAY)


def _absence(db, user, closure_id=None, day=PAST):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=day, type=AbsenceType.VACATION,
                hours=8.0, half_day=False, closure_id=closure_id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _closure(db, admin, day=PAST):
    c = CompanyClosure(tenant_id=DEFAULT_TENANT_ID, name="Sommer", start_date=day, end_date=day,
                       created_by=admin.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _delete_request(client, absence):
    return client.post("/api/change-requests/", json={
        "request_type": "delete", "entry_kind": "absence", "absence_id": str(absence.id),
        "reason": "war doch da"})


def _update_request(client, absence, day=PAST):
    return client.post("/api/change-requests/", json={
        "request_type": "update", "entry_kind": "absence", "absence_id": str(absence.id),
        "proposed_absence_type": "sick", "proposed_date": day.isoformat(),
        "proposed_absence_hours": 8.0, "reason": "war krank"})


@pytest.mark.parametrize("day", [PAST, TODAY, FUTURE])
def test_delete_request_for_closure_day_is_rejected(_db_session, employee_user, admin_user,
                                                    employee_client, monkeypatch, day):
    _freeze(monkeypatch)
    a = _absence(_db_session, employee_user, _closure(_db_session, admin_user, day).id, day)
    r = _delete_request(employee_client, a)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == absences_router.CLOSURE_ABSENCE_DELETE_DETAIL
    assert _db_session.query(ChangeRequest).count() == 0


def test_update_request_for_closure_day_is_rejected(_db_session, employee_user, admin_user,
                                                    employee_client, monkeypatch):
    _freeze(monkeypatch)
    a = _absence(_db_session, employee_user, _closure(_db_session, admin_user).id)
    r = _update_request(employee_client, a)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == absences_router.CLOSURE_ABSENCE_DELETE_DETAIL
    assert _db_session.query(ChangeRequest).count() == 0


def test_delete_request_for_normal_absence_still_works(_db_session, employee_user,
                                                       employee_client, monkeypatch):
    _freeze(monkeypatch)
    r = _delete_request(employee_client, _absence(_db_session, employee_user))
    assert r.status_code in (200, 201), r.text
    assert _db_session.query(ChangeRequest).count() == 1


def test_update_request_for_normal_absence_still_works(_db_session, employee_user,
                                                       employee_client, monkeypatch):
    _freeze(monkeypatch)
    r = _update_request(employee_client, _absence(_db_session, employee_user))
    assert r.status_code in (200, 201), r.text
    assert _db_session.query(ChangeRequest).count() == 1
