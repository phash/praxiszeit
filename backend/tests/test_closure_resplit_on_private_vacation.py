"""Fix #3: private-vacation write paths trigger the #314 closure re-split.

The re-split reserves all non-closure VACATION up front. So booking / cancelling
private vacation must re-classify the year's Betriebsferien — otherwise a
cancelled private vacation leaves a closure day stranded on OVERTIME even though
budget is free again.

Demonstrable direction (the budget guard blocks over-budget bookings, so the
flip can only be shown via a STORNO that frees budget): cancelling an approved
private vacation flips a closure OVERTIME day back to VACATION.
"""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db, Base
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

# 4 closure workdays in March 2027 (Mon..Thu) + 2 private vacation days in Jan 2027.
C_MON, C_THU = date(2027, 3, 1), date(2027, 3, 4)
PV1, PV2 = date(2027, 1, 5), date(2027, 1, 6)  # Tue, Wed


def _create_test_app() -> FastAPI:
    from app.routers import company_closures, admin_vacations, vacation_requests, absences
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(company_closures.router)
    app.include_router(admin_vacations.router)
    app.include_router(vacation_requests.router)
    app.include_router(absences.router)
    return app


_app = _create_test_app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=4, track_hours=True):
    u = User(
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("x"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=track_hours, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "adm1", role=UserRole.ADMIN, vacation_days=30)


@pytest.fixture
def emp(db, default_tenant):
    return _make_user(db, "emp1", vacation_days=4)


def _client_as(db, user, *, admin_user=None):
    """TestClient with get_db bound to the test session and get_current_user=user.
    If ``admin_user`` is given, require_admin resolves to it (defaults to user)."""
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: user
    _app.dependency_overrides[require_admin] = lambda: (admin_user or user)
    return TestClient(_app)


def _set_toggle(db, on: bool):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def _closure_types(db, emp, closure_id):
    return {a.date: a.type for a in db.query(Absence).filter(
        Absence.user_id == emp.id, Absence.closure_id == uuid.UUID(closure_id)).all()}


def _seed_approved_private_vacation(db, emp):
    """Approved future VR + its two VACATION absences (closure_id=None)."""
    vr = VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=PV1, end_date=PV2,
        hours=8.0, absence_type="vacation", status=VacationRequestStatus.APPROVED.value,
    )
    db.add(vr)
    for d in (PV1, PV2):
        db.add(Absence(user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                       type=AbsenceType.VACATION, hours=8.0, half_day=False))
    db.commit()
    db.refresh(vr)
    return vr


def _create_closure(client):
    r = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": C_MON.isoformat(), "end_date": C_THU.isoformat(),
        "counts_as_vacation": True})
    assert r.status_code == 201, r.text
    return r.json()


def test_employee_withdraw_flips_closure_overtime_back_to_vacation(db, default_tenant, emp, admin):
    _set_toggle(db, True)
    vr = _seed_approved_private_vacation(db, emp)
    c = _create_closure(_client_as(db, admin))
    # 4 closure days, budget 4, 2 private booked → 2 VACATION + 2 OVERTIME.
    before = _closure_types(db, emp, c["id"])
    assert list(before.values()).count(AbsenceType.VACATION) == 2
    assert list(before.values()).count(AbsenceType.OVERTIME) == 2

    r = _client_as(db, emp).delete(f"/api/vacation-requests/{vr.id}")
    assert r.status_code == 204, r.text
    _app.dependency_overrides.clear()

    db.expire_all()
    after = _closure_types(db, emp, c["id"])
    assert set(after.values()) == {AbsenceType.VACATION}


def test_admin_cancel_flips_closure_overtime_back_to_vacation(db, default_tenant, emp, admin):
    _set_toggle(db, True)
    vr = _seed_approved_private_vacation(db, emp)
    client = _client_as(db, admin)
    c = _create_closure(client)
    before = _closure_types(db, emp, c["id"])
    assert list(before.values()).count(AbsenceType.OVERTIME) == 2

    r = client.delete(f"/api/admin/vacation-requests/{vr.id}")
    assert r.status_code == 204, r.text
    _app.dependency_overrides.clear()

    db.expire_all()
    after = _closure_types(db, emp, c["id"])
    assert set(after.values()) == {AbsenceType.VACATION}


def test_booking_private_vacation_runs_resplit_no_spurious_flip(db, default_tenant, admin):
    # Headroom case: a closure with spare budget + a later private booking must NOT
    # spuriously flip a closure day to OVERTIME (exercises the create_absence
    # resplit path; the budget guard blocks over-budget bookings, so no flip).
    emp = _make_user(db, "emp_book", vacation_days=6)
    _set_toggle(db, True)
    client = _client_as(db, admin)
    c = _create_closure(client)  # 4 days, budget 6 → all VACATION
    assert set(_closure_types(db, emp, c["id"]).values()) == {AbsenceType.VACATION}

    r = client.post("/api/absences/", json={
        "user_id": str(emp.id), "date": PV1.isoformat(), "type": "vacation", "hours": 8.0})
    assert r.status_code == 201, r.text
    _app.dependency_overrides.clear()

    db.expire_all()
    # Budget 6, closure 4 + private 1 = 5 ≤ 6 → closure stays all VACATION.
    assert set(_closure_types(db, emp, c["id"]).values()) == {AbsenceType.VACATION}
