"""Fix #8: removing a private VACATION day (storno via delete_absence, or a SICK
refund in create_absence) frees budget that the #314 Betriebsferien split reserves
up front → a closure OVERTIME day must flip back to VACATION (toggle on).
"""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.services import auth_service
from app.routers.absences import delete_absence, create_absence
from app.schemas.absence import AbsenceCreate
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

MON, TUE, WED, THU = date(2025, 3, 10), date(2025, 3, 11), date(2025, 3, 12), date(2025, 3, 13)
PRIV_VAC_DAY = date(2025, 3, 3)  # a Monday before the closure (a workday in 2025)


def _create_test_app() -> FastAPI:
    from app.routers import company_closures
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30):
    u = User(
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("t"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _set_toggle(db, on):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def _closure_types(db, emp, closure_id):
    return [a.type for a in db.query(Absence).filter(
        Absence.user_id == emp.id, Absence.closure_id == uuid.UUID(closure_id),
    ).order_by(Absence.date).all()]


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "admin1", role=UserRole.ADMIN)


@pytest.fixture
def admin_client(db, admin):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: admin
    _app.dependency_overrides[require_admin] = lambda: admin
    yield TestClient(_app)
    _app.dependency_overrides.clear()


def test_delete_private_vacation_flips_closure_overtime_back(db, default_tenant, admin_client):
    emp = _make_user(db, "e_resplit", vacation_days=3)  # budget = 3
    _set_toggle(db, True)

    # A private vacation day consumes 1 of the 3 budget days.
    priv = Absence(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=PRIV_VAC_DAY,
        type=AbsenceType.VACATION, hours=8.0, half_day=False,
    )
    db.add(priv)
    db.commit()
    db.refresh(priv)

    # Closure Mon–Thu (4 workdays). With budget 3 − 1 private = 2, the split is
    # 2× VACATION then 2× OVERTIME.
    r = admin_client.post("/api/company-closures/", json={
        "name": "BF", "start_date": MON.isoformat(), "end_date": THU.isoformat(),
        "counts_as_vacation": True,
    })
    assert r.status_code == 201, r.text
    closure_id = r.json()["id"]

    before = _closure_types(db, emp, closure_id)
    assert before.count(AbsenceType.VACATION) == 2
    assert before.count(AbsenceType.OVERTIME) == 2

    # Storno the private vacation → frees 1 budget day → re-split → 3× VACATION.
    delete_absence(str(priv.id), db=db, current_user=emp)

    after = _closure_types(db, emp, closure_id)
    assert after.count(AbsenceType.VACATION) == 3
    assert after.count(AbsenceType.OVERTIME) == 1


def test_sick_refund_flips_closure_overtime_back(db, default_tenant, admin_client):
    """A SICK booking that refunds (deletes) an overlapping private VACATION frees
    budget → closure OVERTIME flips back to VACATION."""
    emp = _make_user(db, "e_refund", vacation_days=3)
    _set_toggle(db, True)

    priv = Absence(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=PRIV_VAC_DAY,
        type=AbsenceType.VACATION, hours=8.0, half_day=False,
    )
    db.add(priv)
    db.commit()

    r = admin_client.post("/api/company-closures/", json={
        "name": "BF", "start_date": MON.isoformat(), "end_date": THU.isoformat(),
        "counts_as_vacation": True,
    })
    assert r.status_code == 201, r.text
    closure_id = r.json()["id"]
    assert _closure_types(db, emp, closure_id).count(AbsenceType.VACATION) == 2

    # SICK on the private-vacation day with refund → deletes the VACATION.
    # (non-admin self-booking: do NOT pass user_id — target defaults to self)
    create_absence(
        AbsenceCreate(
            date=PRIV_VAC_DAY, type=AbsenceType.SICK,
            hours=8.0, refund_vacation=True,
        ),
        db=db, current_user=emp,
    )

    after = _closure_types(db, emp, closure_id)
    assert after.count(AbsenceType.VACATION) == 3
    assert after.count(AbsenceType.OVERTIME) == 1
