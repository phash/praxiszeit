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
