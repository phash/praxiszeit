"""Year-closing guards & carryover provenance.

Fix #4: create_year_closing must refuse (409) while a PENDING VacationRequest
        overlaps the closing year (approving it later would move the frozen
        balance), mirroring the existing PENDING ChangeRequest guard.
Fix #5: idempotent year closing (no duplicate carryover) + a non-destructive
        ``warning`` on retroactive changes to an already-closed year.
Fix #7: ``YearCarryover.source`` distinguishes year-closing rows from manual
        ones, so delete_year_closing only removes the former.
"""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db, Base
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType, YearCarryover
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.services import auth_service, calculation_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _create_test_app() -> FastAPI:
    from app.routers import admin_carryovers, vacation_requests, admin_vacations, company_closures
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(admin_carryovers.router)
    app.include_router(vacation_requests.router)
    app.include_router(admin_vacations.router)
    app.include_router(company_closures.router)
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


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30):
    u = User(
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("x"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "adm1", role=UserRole.ADMIN)


@pytest.fixture
def emp(db, default_tenant):
    return _make_user(db, "emp1")


def _client_as(db, user):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: user
    _app.dependency_overrides[require_admin] = lambda: user
    return TestClient(_app)


def _set_toggle(db, on: bool):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


# --- Fix #4: PENDING VacationRequest guard ------------------------------------


def test_year_closing_blocked_by_pending_vacation_request(db, default_tenant, admin, emp):
    db.add(VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 7, 1),
        end_date=date(2025, 7, 5), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.PENDING.value))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 409, r.text
    assert "Urlaubsantr" in r.json()["detail"]


def test_year_closing_allows_pending_request_in_other_year(db, default_tenant, admin, emp):
    db.add(VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 7, 1),
        end_date=date(2026, 7, 5), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.PENDING.value))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text


def test_year_closing_ignores_non_pending_request(db, default_tenant, admin, emp):
    db.add(VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 7, 1),
        end_date=date(2025, 7, 5), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.APPROVED.value))
    db.commit()
    r = _client_as(db, admin).post("/api/admin/year-closing/2025")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text


# --- Fix #5: idempotency + stale-closing warning ------------------------------


def test_double_year_closing_is_idempotent(db, default_tenant, admin, emp):
    client = _client_as(db, admin)
    r1 = client.post("/api/admin/year-closing/2025")
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/admin/year-closing/2025")
    assert r2.status_code == 200, r2.text
    _app.dependency_overrides.clear()
    # Exactly one carryover per active user for 2026 (no duplicate rows).
    rows = db.query(YearCarryover).filter(YearCarryover.year == 2026).all()
    assert len(rows) == 2  # admin + emp
    per_user = {r.user_id for r in rows}
    assert len(per_user) == 2


def test_cancel_vacation_after_closing_returns_stale_warning(db, default_tenant, admin, emp):
    # Close a FUTURE year so the approved vacation is still cancellable.
    calculation_service.create_year_closing(db, 2027, [emp])  # → carryover 2028
    vr = VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2027, 3, 2),
        end_date=date(2027, 3, 3), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.APPROVED.value)
    db.add(vr)
    db.add(Absence(user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2027, 3, 2),
                   type=AbsenceType.VACATION, hours=8.0, half_day=False))
    db.commit()
    db.refresh(vr)

    r = _client_as(db, emp).delete(f"/api/vacation-requests/{vr.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert "Jahresabschluss 2027" in r.json()["warning"]


def test_cancel_vacation_without_closing_returns_204(db, default_tenant, admin, emp):
    vr = VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=date(2027, 3, 2),
        end_date=date(2027, 3, 3), hours=8.0, absence_type="vacation",
        status=VacationRequestStatus.APPROVED.value)
    db.add(vr)
    db.commit()
    db.refresh(vr)
    r = _client_as(db, emp).delete(f"/api/vacation-requests/{vr.id}")
    _app.dependency_overrides.clear()
    assert r.status_code == 204, r.text


def test_delete_closure_after_closing_returns_stale_warning(db, default_tenant, admin, emp):
    _set_toggle(db, False)
    # Create a 2027 closure, then close 2027 → carryover 2028 exists.
    client = _client_as(db, admin)
    c = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": "2027-03-01", "end_date": "2027-03-04",
        "counts_as_vacation": True})
    assert c.status_code == 201, c.text
    calculation_service.create_year_closing(db, 2027, [emp, admin])
    r = client.delete(f"/api/company-closures/{c.json()['id']}")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert "Jahresabschluss 2027" in r.json()["warning"]
