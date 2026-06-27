"""#314: Betriebsferien über den Jahresurlaub hinaus als Überstundenabbau buchen.

Globales Setting `closure_overtime_after_vacation` (Default aus). Ist es an UND
zählt die Schließung als Urlaub (`counts_as_vacation`), werden Closure-Arbeitstage
chronologisch zuerst als VACATION gebucht (bis das Rest-Urlaubsbudget erschöpft
ist) und danach als OVERTIME (Überstundenausgleich → Überstundenkonto sinkt,
darf ins Minus) — statt Minus-Urlaub zu erzeugen.
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

# Mon–Thu in a clean week (4 workdays), no holidays seeded.
MON, TUE, WED, THU = date(2025, 3, 10), date(2025, 3, 11), date(2025, 3, 12), date(2025, 3, 13)


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
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("test123"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


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


def _set_toggle(db, on: bool):
    db.add(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                         value="true" if on else "false"))
    db.commit()


def _create_closure(client, counts_as_vacation=True):
    r = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": MON.isoformat(), "end_date": THU.isoformat(),
        "counts_as_vacation": counts_as_vacation,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _types(db, user, closure_id):
    return [a.type for a in db.query(Absence).filter(
        Absence.user_id == user.id, Absence.closure_id == uuid.UUID(closure_id),
    ).order_by(Absence.date).all()]


class TestClosureOvertimeSplit:
    def test_setting_off_all_vacation(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_off", vacation_days=2)  # low budget, but setting OFF
        _set_toggle(db, False)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.VACATION] * 4

    def test_budget_covers_all(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_full", vacation_days=30)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.VACATION] * 4

    def test_partial_budget_splits_vacation_then_overtime(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_part", vacation_days=2)  # exactly 2 days budget
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        # first 2 days consume the budget as VACATION, the rest become OVERTIME
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]

    def test_zero_budget_all_overtime(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_zero", vacation_days=0)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.OVERTIME] * 4

    def test_paid_leave_closure_ignores_setting(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_pl", vacation_days=0)
        _set_toggle(db, True)
        c = _create_closure(admin_client, counts_as_vacation=False)
        # not a vacation closure → setting does not apply, stays PAID_LEAVE
        assert _types(db, emp, c["id"]) == [AbsenceType.PAID_LEAVE] * 4

    def test_skip_does_not_consume_budget(self, db, default_tenant, admin_client):
        # ArbZG-audit #4: a day skipped (here: pre-existing foreign SICK absence)
        # must NOT consume the vacation budget.
        emp = _make_user(db, "e_skip", vacation_days=1)
        db.add(Absence(user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=MON,
                       type=AbsenceType.SICK, hours=8.0))
        db.commit()
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        # MON is skipped (foreign SICK); the 1-day budget is still free for TUE → VACATION,
        # WED/THU become OVERTIME. (If the skip had consumed the budget, TUE would be OVERTIME.)
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]


def _update(client, cid, counts_as_vacation, name="BF"):
    r = client.put(f"/api/company-closures/{cid}", json={
        "name": name, "start_date": MON.isoformat(), "end_date": THU.isoformat(),
        "counts_as_vacation": counts_as_vacation,
    })
    assert r.status_code == 200, r.text
    return r.json()


class TestClosureOvertimeSplitUpdate:
    def test_update_resplits_and_keeps_overtime(self, db, default_tenant, admin_client):
        # ArbZG-audit #1: a PUT must not turn budget-exhausted OVERTIME days back
        # into VACATION. Re-saving the split closure re-splits identically.
        emp = _make_user(db, "e_up", vacation_days=2)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]
        _update(admin_client, c["id"], counts_as_vacation=True, name="BF-neu")
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]

    def test_double_toggle_through_paid_leave_no_minus_vacation(self, db, default_tenant, admin_client):
        # The exact audit bug: split → Freistellung → zurück zu Urlaub must NOT
        # produce 4× VACATION at budget 2 (= minus-vacation), but re-split.
        emp = _make_user(db, "e_dt", vacation_days=2)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        _update(admin_client, c["id"], counts_as_vacation=False)  # → all PAID_LEAVE
        assert _types(db, emp, c["id"]) == [AbsenceType.PAID_LEAVE] * 4
        _update(admin_client, c["id"], counts_as_vacation=True)   # → re-split, NOT 4× VACATION
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]
