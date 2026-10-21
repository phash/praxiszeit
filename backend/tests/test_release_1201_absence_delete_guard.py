"""Release-Review 1.20.1: ``DELETE /api/absences/{id}`` durch Mitarbeitende.

Mitarbeitende durften bisher jede eigene Abwesenheit löschen — auch
Betriebsferien-Tage (``closure_id``) und Urlaub aus einem GENEHMIGTEN
Urlaubsantrag (auch vergangene Tage). Damit kamen die Urlaubstage zurück, der
Antrag blieb ``approved`` ohne Abwesenheiten und die Regel „genehmigte Anträge
nur vor Beginn zurückziehen" (``vacation_requests.withdraw_vacation_request``)
war umgangen. Gegenstück zur Sperre in ``create_absence`` (MA-ABS-01).
"""
from datetime import date

from app.models import Absence, AbsenceType
from app.models.company_closure import CompanyClosure
from app.models.system_setting import SystemSetting
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.routers import absences as absences_router
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)

DAY = date(2026, 3, 10)  # Dienstag


def _absence(db, user, d=DAY, t=AbsenceType.VACATION, closure_id=None):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=t,
                hours=8.0, half_day=False, closure_id=closure_id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _closure(db, admin):
    c = CompanyClosure(tenant_id=DEFAULT_TENANT_ID, name="BF", start_date=DAY,
                       end_date=DAY, counts_as_vacation=True, created_by=admin.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _vr(db, user, start, end=None, status=VacationRequestStatus.APPROVED.value):
    vr = VacationRequest(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=start,
                         end_date=end, hours=8.0, absence_type="vacation", status=status)
    db.add(vr)
    db.commit()
    return vr


def _approval_required(db, on=True):
    db.merge(SystemSetting(key="vacation_approval_required", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def _exists(db, absence_id):
    db.expire_all()
    return db.query(Absence).filter(Absence.id == absence_id).first() is not None


def test_employee_cannot_delete_closure_absence(_db_session, employee_user, admin_user,
                                                employee_client):
    c = _closure(_db_session, admin_user)
    a = _absence(_db_session, employee_user, closure_id=c.id)
    r = employee_client.delete(f"/api/absences/{a.id}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.CLOSURE_ABSENCE_DELETE_DETAIL
    assert _exists(_db_session, a.id)


def test_employee_cannot_delete_vacation_from_approved_request(
        _db_session, employee_user, employee_client):
    _vr(_db_session, employee_user, date(2026, 3, 9), date(2026, 3, 13))
    a = _absence(_db_session, employee_user)
    r = employee_client.delete(f"/api/absences/{a.id}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.APPROVED_VACATION_DELETE_DETAIL
    assert _exists(_db_session, a.id)


def test_employee_cannot_delete_vacation_from_approved_single_day_request(
        _db_session, employee_user, employee_client):
    _vr(_db_session, employee_user, DAY)
    a = _absence(_db_session, employee_user)
    assert employee_client.delete(f"/api/absences/{a.id}").status_code == 409


def test_employee_cannot_delete_vacation_when_approval_required(
        _db_session, employee_user, employee_client):
    _approval_required(_db_session, True)
    a = _absence(_db_session, employee_user)
    r = employee_client.delete(f"/api/absences/{a.id}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.APPROVED_VACATION_DELETE_DETAIL
    assert _exists(_db_session, a.id)


def test_employee_can_delete_own_sick(_db_session, employee_user, employee_client):
    _approval_required(_db_session, True)
    a = _absence(_db_session, employee_user, t=AbsenceType.SICK)
    assert employee_client.delete(f"/api/absences/{a.id}").status_code == 204
    assert not _exists(_db_session, a.id)


def test_employee_can_delete_direct_vacation_without_approval_or_request(
        _db_session, employee_user, employee_client):
    _approval_required(_db_session, False)
    # Andere Anträge stören nicht: abgelehnt am selben Tag, genehmigt an anderem Tag.
    _vr(_db_session, employee_user, DAY, status=VacationRequestStatus.REJECTED.value)
    _vr(_db_session, employee_user, date(2026, 4, 1), date(2026, 4, 3))
    a = _absence(_db_session, employee_user)
    assert employee_client.delete(f"/api/absences/{a.id}").status_code == 204
    assert not _exists(_db_session, a.id)


def test_admin_can_delete_closure_absence(_db_session, employee_user, admin_user, admin_client):
    c = _closure(_db_session, admin_user)
    a = _absence(_db_session, employee_user, closure_id=c.id)
    assert admin_client.delete(f"/api/absences/{a.id}").status_code == 204
    assert not _exists(_db_session, a.id)


def test_admin_can_delete_vacation_from_approved_request(
        _db_session, employee_user, admin_client):
    _approval_required(_db_session, True)
    _vr(_db_session, employee_user, DAY)
    a = _absence(_db_session, employee_user)
    assert admin_client.delete(f"/api/absences/{a.id}").status_code == 204
