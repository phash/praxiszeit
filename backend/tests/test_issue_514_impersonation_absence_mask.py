"""#514: under impersonation ("Login als …") the absence read routes mask
health data the same way ``/journal/me`` does since the 2026-10-26 security
review (Art. 9 DSGVO).

``GET /api/absences/``, ``/calendar`` and ``/team/upcoming`` returned the
impersonated person's SICK/OTHER/PAID_LEAVE and custom-reason absences with
type, note and reason. The admin can read them through the admin path too,
but there a ``health_data_read`` row is written; the impersonation path read
them without that row and without masking.
"""
import uuid
from datetime import date, timedelta

from fastapi import Request

from app.middleware.auth import get_current_user
from app.models import Absence, AbsenceType
from app.models import AbsenceReason
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, employee_client, employee_user, tenant, endpoints_app,
)

DAY = date.today() + timedelta(days=10)


def _impersonate(user):
    def _override(request: Request):
        request.state.is_impersonating = True
        request.state.impersonator_id = str(uuid.uuid4())
        return user
    endpoints_app.dependency_overrides[get_current_user] = _override


def _absence(db, user, d, type_, note=None, reason_id=None):
    db.add(Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                   type=type_, hours=8.0, note=note, reason_id=reason_id))
    db.commit()


def _reason(db):
    r = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Reha",
                      base_behavior="worked", is_active=True)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _by_date(rows, d):
    return [r for r in rows if r["date"] == d.isoformat()]


def test_list_masks_sick_under_impersonation(_db_session, employee_user, employee_client):
    _absence(_db_session, employee_user, DAY, AbsenceType.SICK, note="Grippe")
    _impersonate(employee_user)
    rows = employee_client.get(f"/api/absences/?year={DAY.year}").json()
    (row,) = _by_date(rows, DAY)
    assert row["type"] == "absent"
    assert row["note"] is None


def test_list_masks_custom_reason_under_impersonation(_db_session, employee_user, employee_client):
    reason = _reason(_db_session)
    _absence(_db_session, employee_user, DAY, AbsenceType.TRAINING, note="Klinik", reason_id=reason.id)
    _impersonate(employee_user)
    (row,) = _by_date(employee_client.get(f"/api/absences/?year={DAY.year}").json(), DAY)
    assert row["type"] == "absent"
    assert row["note"] is None
    assert row["reason_id"] is None


def test_list_keeps_vacation_under_impersonation(_db_session, employee_user, employee_client):
    _absence(_db_session, employee_user, DAY, AbsenceType.VACATION, note="Urlaub Spanien")
    _impersonate(employee_user)
    (row,) = _by_date(employee_client.get(f"/api/absences/?year={DAY.year}").json(), DAY)
    assert row["type"] == "vacation"
    assert row["note"] == "Urlaub Spanien"


def test_list_own_view_shows_sick(_db_session, employee_user, employee_client):
    _absence(_db_session, employee_user, DAY, AbsenceType.SICK, note="Grippe")
    (row,) = _by_date(employee_client.get(f"/api/absences/?year={DAY.year}").json(), DAY)
    assert row["type"] == "sick"
    assert row["note"] == "Grippe"


def test_calendar_masks_own_sick_under_impersonation(_db_session, employee_user, employee_client):
    _absence(_db_session, employee_user, DAY, AbsenceType.SICK)
    _impersonate(employee_user)
    month = f"{DAY.year}-{DAY.month:02d}"
    (row,) = _by_date(employee_client.get(f"/api/absences/calendar?month={month}").json(), DAY)
    assert row["type"] == "absent"


def test_calendar_own_view_shows_sick(_db_session, employee_user, employee_client):
    _absence(_db_session, employee_user, DAY, AbsenceType.SICK)
    month = f"{DAY.year}-{DAY.month:02d}"
    (row,) = _by_date(employee_client.get(f"/api/absences/calendar?month={month}").json(), DAY)
    assert row["type"] == "sick"


def test_team_upcoming_masks_own_paid_leave_under_impersonation(
        _db_session, employee_user, employee_client):
    _absence(_db_session, employee_user, DAY, AbsenceType.PAID_LEAVE)
    _impersonate(employee_user)
    (row,) = _by_date(employee_client.get("/api/absences/team/upcoming").json(), DAY)
    assert row["type"] == "absent"


def test_team_upcoming_own_view_shows_paid_leave(_db_session, employee_user, employee_client):
    _absence(_db_session, employee_user, DAY, AbsenceType.PAID_LEAVE)
    (row,) = _by_date(employee_client.get("/api/absences/team/upcoming").json(), DAY)
    assert row["type"] == "paid_leave"
