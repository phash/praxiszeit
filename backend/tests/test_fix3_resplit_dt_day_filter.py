"""Fix #3: resplit_year_closures berechnet ``consumed`` (privater Urlaub + freie
Sondertage) ohne den ``dt_day>0``-Filter, den get_vacation_account anwendet.

An einem für den MA freien Wochentag (use_daily_schedule, Tagessoll 0), der mit
einem freien+counts_as_vacation-Sondertag (24.12.) bzw. mit einem privaten
Urlaubstag zusammenfällt, überzählte ``consumed`` → closure_budget zu klein →
ein Closure-Tag fiel fälschlich auf OVERTIME statt VACATION.

2026: 24.12. ist ein Donnerstag → bei einem MA mit freiem Donnerstag ist das
Tagessoll dort 0.
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
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

# Saubere Woche im März 2026 (keine Feiertage): Mo/Di/Mi sind Arbeitstage,
# Do ist beim Test-MA frei.
MON, TUE, WED, THU = date(2026, 3, 9), date(2026, 3, 10), date(2026, 3, 11), date(2026, 3, 12)


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


def _daily_user(db, username, vacation_days):
    """MA mit individuellem Tagesplan: Mo/Di/Mi/Fr je 8h, Donnerstag FREI (0h)."""
    return _make_user(
        db, username, vacation_days=vacation_days, use_daily_schedule=True,
        hours_monday=8.0, hours_tuesday=8.0, hours_wednesday=8.0,
        hours_thursday=None, hours_friday=8.0,
    )


def _set_toggle(db, on):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def _set_dec24_free(db):
    db.merge(SystemSetting(key="special_day_dec24_mode", tenant_id=DEFAULT_TENANT_ID, value="free"))
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


def _make_closure_mon_wed(client):
    r = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": MON.isoformat(), "end_date": WED.isoformat(),
        "counts_as_vacation": True,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_free_special_day_on_off_day_not_counted(db, default_tenant, admin_client):
    """24.12. (Do, beim MA freier Tag → Tagessoll 0) darf consumed NICHT erhöhen:
    Budget 3, Closure Mo–Mi (3 Arbeitstage) → alle 3 bleiben VACATION."""
    emp = _daily_user(db, "e_freeday", vacation_days=3)
    _set_toggle(db, True)
    _set_dec24_free(db)  # 24.12.2026 = free + counts_as_vacation (Do)

    closure_id = _make_closure_mon_wed(admin_client)

    types = _closure_types(db, emp, closure_id)
    assert types == [AbsenceType.VACATION] * 3, types


def test_private_vacation_on_off_day_not_counted(db, default_tenant, admin_client):
    """Privater Urlaub an einem freien Donnerstag (Tagessoll 0) darf consumed
    NICHT erhöhen — Budget 3, Closure Mo–Mi → alle 3 bleiben VACATION."""
    emp = _daily_user(db, "e_privoff", vacation_days=3)
    _set_toggle(db, True)

    # Privater Urlaub am freien Donnerstag (dt_day=0). get_vacation_account
    # zählt ihn nicht (used_days unverändert); resplit darf das auch nicht.
    priv = Absence(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=THU,
        type=AbsenceType.VACATION, hours=0.0, half_day=False,
    )
    db.add(priv)
    db.commit()

    closure_id = _make_closure_mon_wed(admin_client)

    types = _closure_types(db, emp, closure_id)
    assert types == [AbsenceType.VACATION] * 3, types
