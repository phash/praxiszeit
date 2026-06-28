"""Fix #5: die CR-Absence-Pfade (CREATE/UPDATE/DELETE) riefen NICHT
closure_split_service.resplit_year_closures — alle anderen VACATION-anlegen/
löschen-Pfade tun das (bei aktivem Setting closure_overtime_after_vacation),
damit Betriebsferien-Tage korrekt zwischen VACATION/OVERTIME umklappen.

Szenario: Betriebsferien mit reserviertem OVERTIME-Puffer; ein CR storniert
(DELETE) bzw. ändert (UPDATE: VACATION→SICK) privaten Urlaub → ein
Closure-OVERTIME-Tag klappt korrekt auf VACATION zurück.
"""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    User, UserRole, Absence, AbsenceType,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.services import auth_service
from app.routers.admin_change_requests import review_change_request
from app.schemas.change_request import ChangeRequestReview
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

MON, TUE, WED, THU = date(2025, 3, 10), date(2025, 3, 11), date(2025, 3, 12), date(2025, 3, 13)
PRIV_VAC_DAY = date(2025, 3, 3)  # Montag vor der Schließung, Arbeitstag


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


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30, **kwargs):
    defaults = dict(
        email=f"{username}@x.de", password_hash=auth_service.hash_password("t"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0,
        vacation_days=vacation_days, work_days_per_week=5, is_active=True,
        track_hours=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
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
    return _make_user(db, "admin1", role=UserRole.ADMIN, receives_company_closures=False)


@pytest.fixture
def admin_client(db, admin):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: admin
    _app.dependency_overrides[require_admin] = lambda: admin
    yield TestClient(_app)
    _app.dependency_overrides.clear()


def _make_closure(admin_client):
    r = admin_client.post("/api/company-closures/", json={
        "name": "BF", "start_date": MON.isoformat(), "end_date": THU.isoformat(),
        "counts_as_vacation": True,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _make_absence_cr(db, user, request_type, **kwargs):
    defaults = dict(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=request_type, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="Test",
    )
    defaults.update(kwargs)
    cr = ChangeRequest(**defaults)
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


def test_cr_delete_private_vacation_flips_closure_back(db, default_tenant, admin, admin_client):
    """CR-DELETE eines privaten Urlaubstags → 1 Budget-Tag frei → Resplit →
    ein Closure-OVERTIME-Tag klappt auf VACATION (3 VAC + 1 OT statt 2/2)."""
    emp = _make_user(db, "e_del", vacation_days=3)
    _set_toggle(db, True)

    priv = Absence(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=PRIV_VAC_DAY,
        type=AbsenceType.VACATION, hours=8.0, half_day=False,
    )
    db.add(priv)
    db.commit()
    db.refresh(priv)

    closure_id = _make_closure(admin_client)
    before = _closure_types(db, emp, closure_id)
    assert before.count(AbsenceType.VACATION) == 2
    assert before.count(AbsenceType.OVERTIME) == 2

    cr = _make_absence_cr(db, emp, ChangeRequestType.DELETE, absence_id=priv.id)
    review_change_request(
        request_id=str(cr.id),
        review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )

    after = _closure_types(db, emp, closure_id)
    assert after.count(AbsenceType.VACATION) == 3, after
    assert after.count(AbsenceType.OVERTIME) == 1, after


def test_cr_update_vacation_to_sick_flips_closure_back(db, default_tenant, admin, admin_client):
    """CR-UPDATE: privater VACATION→SICK → 1 Budget-Tag frei → Resplit →
    Closure 3 VAC + 1 OT statt 2/2."""
    emp = _make_user(db, "e_upd", vacation_days=3)
    _set_toggle(db, True)

    priv = Absence(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=PRIV_VAC_DAY,
        type=AbsenceType.VACATION, hours=8.0, half_day=False,
    )
    db.add(priv)
    db.commit()
    db.refresh(priv)

    closure_id = _make_closure(admin_client)
    assert _closure_types(db, emp, closure_id).count(AbsenceType.OVERTIME) == 2

    cr = _make_absence_cr(
        db, emp, ChangeRequestType.UPDATE,
        absence_id=priv.id, proposed_date=PRIV_VAC_DAY,
        proposed_absence_type="sick", proposed_absence_hours=8.0,
    )
    review_change_request(
        request_id=str(cr.id),
        review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )

    after = _closure_types(db, emp, closure_id)
    assert after.count(AbsenceType.VACATION) == 3, after
    assert after.count(AbsenceType.OVERTIME) == 1, after


def test_cr_delete_no_resplit_when_toggle_off(db, default_tenant, admin, admin_client):
    """Setting AUS: Closure bleibt alles VACATION (kein Split); CR-DELETE des
    privaten Urlaubs ändert daran nichts (kein Resplit, kein Crash)."""
    emp = _make_user(db, "e_off", vacation_days=3)
    _set_toggle(db, False)

    priv = Absence(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=PRIV_VAC_DAY,
        type=AbsenceType.VACATION, hours=8.0, half_day=False,
    )
    db.add(priv)
    db.commit()
    db.refresh(priv)

    closure_id = _make_closure(admin_client)
    assert _closure_types(db, emp, closure_id) == [AbsenceType.VACATION] * 4

    cr = _make_absence_cr(db, emp, ChangeRequestType.DELETE, absence_id=priv.id)
    review_change_request(
        request_id=str(cr.id),
        review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )
    assert _closure_types(db, emp, closure_id) == [AbsenceType.VACATION] * 4
