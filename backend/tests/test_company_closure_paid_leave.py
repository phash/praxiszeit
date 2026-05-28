"""Tests for Betriebsferien als Urlaub vs. bezahlte Freistellung (#145).

Covers:
- counts_as_vacation=False -> generated absences are PAID_LEAVE.
- PAID_LEAVE does NOT deduct the vacation budget (get_vacation_account).
- PAID_LEAVE reduces the monthly target to 0 on those days (like OTHER).
- PAID_LEAVE is balance-neutral (target drops, no actual credit).
- counts_as_vacation=True (default) keeps the legacy VACATION behaviour
  and DOES deduct the budget.
- PUT switching the flag re-types the still-linked absences.
- The response carries the flag back.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType, CompanyClosure
from app.models.tenant import Tenant
from app.services import calculation_service
from tests.conftest import (
    DEFAULT_TENANT_ID,
    engine,
    TestingSessionLocal,
)

# A clean Mon-Fri work week in March 2025 with no public holidays seeded.
MON = date(2025, 3, 10)
TUE = date(2025, 3, 11)
WED = date(2025, 3, 12)
THU = date(2025, 3, 13)
FRI = date(2025, 3, 14)

YEAR = 2025
MONTH = 3


# ---------------------------------------------------------------------------
# Test app setup
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    from app.routers import company_closures

    app = FastAPI(title="PraxisZeit Paid-Leave Closure Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(company_closures.router)
    return app


_app = _create_test_app()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
    tenant = Tenant(
        id=DEFAULT_TENANT_ID,
        name="Default",
        slug="default",
        is_active=True,
        mode="single",
    )
    db.add(tenant)
    db.commit()
    return tenant


def _make_user(db, username, role=UserRole.EMPLOYEE):
    from app.services import auth_service
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=auth_service.hash_password("test123"),
        first_name=username,
        last_name="Test",
        role=role,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def employee(db, default_tenant):
    return _make_user(db, "emp1")


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "admin1", role=UserRole.ADMIN)


def _make_client(db_session, current_user):
    def override_db():
        try:
            yield db_session
        finally:
            pass

    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: current_user
    _app.dependency_overrides[require_admin] = lambda: current_user

    client = TestClient(_app)
    yield client
    _app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db, admin):
    yield from _make_client(db, admin)


def _create_closure(client, name, start, end, counts_as_vacation=True):
    resp = client.post("/api/company-closures/", json={
        "name": name,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "counts_as_vacation": counts_as_vacation,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _closure_absences(db, employee, closure_id):
    return db.query(Absence).filter(
        Absence.user_id == employee.id,
        Absence.closure_id == uuid.UUID(closure_id),
    ).order_by(Absence.date).all()


# ---------------------------------------------------------------------------
# Absence type follows the flag
# ---------------------------------------------------------------------------

class TestAbsenceTypeFollowsFlag:
    def test_paid_leave_closure_creates_paid_leave_absences(self, db, employee, admin_client):
        """Prüft dass counts_as_vacation=False PAID_LEAVE-Absences erzeugt (REQ-1/REQ-2)."""
        closure = _create_closure(admin_client, "Freistellung", MON, WED, counts_as_vacation=False)

        absences = _closure_absences(db, employee, closure["id"])
        assert {a.date for a in absences} == {MON, TUE, WED}
        assert all(a.type == AbsenceType.PAID_LEAVE for a in absences)

    def test_default_closure_creates_vacation_absences(self, db, employee, admin_client):
        """Prüft dass der Default (counts_as_vacation=True) weiterhin VACATION erzeugt."""
        closure = _create_closure(admin_client, "Urlaub", MON, WED)

        absences = _closure_absences(db, employee, closure["id"])
        assert {a.date for a in absences} == {MON, TUE, WED}
        assert all(a.type == AbsenceType.VACATION for a in absences)

    def test_flag_omitted_defaults_to_vacation(self, db, employee, admin_client):
        """Prüft dass ein fehlendes Flag im Body als Urlaub (Default) interpretiert wird."""
        resp = admin_client.post("/api/company-closures/", json={
            "name": "Ohne Flag",
            "start_date": MON.isoformat(),
            "end_date": TUE.isoformat(),
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["counts_as_vacation"] is True
        absences = _closure_absences(db, employee, body["id"])
        assert all(a.type == AbsenceType.VACATION for a in absences)


# ---------------------------------------------------------------------------
# Vacation budget is NOT deducted by PAID_LEAVE
# ---------------------------------------------------------------------------

class TestVacationBudgetUntouched:
    def test_paid_leave_does_not_deduct_vacation_budget(self, db, employee, admin_client):
        """Prüft dass bezahlte Freistellung das Urlaubskonto unverändert lässt (REQ-1)."""
        before = calculation_service.get_vacation_account(db, employee, YEAR)

        _create_closure(admin_client, "Freistellung", MON, FRI, counts_as_vacation=False)
        db.expire_all()

        after = calculation_service.get_vacation_account(db, employee, YEAR)
        # No vacation used; remaining is identical to before the closure.
        assert after["used_hours"] == 0.0
        assert after["used_days"] == 0.0
        assert after["remaining_hours"] == before["remaining_hours"]
        assert after["remaining_days"] == before["remaining_days"]

    def test_vacation_closure_does_deduct_budget(self, db, employee, admin_client):
        """Kontrolle: Urlaub-Betriebsferien ziehen das Urlaubskonto wie bisher ab."""
        before = calculation_service.get_vacation_account(db, employee, YEAR)

        _create_closure(admin_client, "Urlaub", MON, FRI, counts_as_vacation=True)
        db.expire_all()

        after = calculation_service.get_vacation_account(db, employee, YEAR)
        # 5 workdays * 8h = 40h used.
        assert after["used_hours"] == 40.0
        assert after["used_days"] == 5.0
        assert after["remaining_hours"] == pytest.approx(before["remaining_hours"] - 40.0)

    def test_get_vacation_account_excludes_paid_leave_directly(self, db, employee):
        """Prüft auf Service-Ebene, dass get_vacation_account PAID_LEAVE ignoriert."""
        # One VACATION day and one PAID_LEAVE day, same week.
        db.add(Absence(
            user_id=employee.id, tenant_id=DEFAULT_TENANT_ID,
            date=MON, type=AbsenceType.VACATION, hours=8.0,
        ))
        db.add(Absence(
            user_id=employee.id, tenant_id=DEFAULT_TENANT_ID,
            date=TUE, type=AbsenceType.PAID_LEAVE, hours=8.0,
        ))
        db.commit()

        account = calculation_service.get_vacation_account(db, employee, YEAR)
        # Only the VACATION day counts towards used vacation.
        assert account["used_hours"] == 8.0
        assert account["used_days"] == 1.0


# ---------------------------------------------------------------------------
# Target reduction + balance neutrality
# ---------------------------------------------------------------------------

class TestTargetAndBalance:
    def test_paid_leave_reduces_target_to_zero_on_those_days(self, db, employee, admin_client):
        """Prüft dass die Sollzeit der Freistellungstage entfällt (REQ-1)."""
        target_before = calculation_service.get_monthly_target(db, employee, YEAR, MONTH)

        _create_closure(admin_client, "Freistellung", MON, FRI, counts_as_vacation=False)
        db.expire_all()

        target_after = calculation_service.get_monthly_target(db, employee, YEAR, MONTH)
        # 5 workdays * 8h target removed.
        assert target_after == (target_before - Decimal("40.00"))

    def test_paid_leave_is_balance_neutral(self, db, employee, admin_client):
        """Prüft dass bezahlte Freistellung das Überstundenkonto nicht verschiebt."""
        # Balance with no entries at all on the (otherwise empty) month is the
        # negative of the full month target. After a PAID_LEAVE closure the
        # covered days drop out of BOTH target and actual, so the balance
        # improves by exactly the removed target (no deficit on those days).
        balance_before = calculation_service.get_monthly_balance(db, employee, YEAR, MONTH)

        _create_closure(admin_client, "Freistellung", MON, FRI, counts_as_vacation=False)
        db.expire_all()

        balance_after = calculation_service.get_monthly_balance(db, employee, YEAR, MONTH)
        # Target dropped by 40h, actual unchanged (0 credit) -> balance rises 40h.
        assert balance_after == (balance_before + Decimal("40.00"))

    def test_paid_leave_matches_other_semantics(self, db, employee, admin_client):
        """Prüft dass PAID_LEAVE rechen-mechanisch identisch zu OTHER ist."""
        # PAID_LEAVE closure on MON-WED.
        _create_closure(admin_client, "Freistellung", MON, WED, counts_as_vacation=False)
        db.expire_all()
        target_paid = calculation_service.get_monthly_target(db, employee, YEAR, MONTH)
        balance_paid = calculation_service.get_monthly_balance(db, employee, YEAR, MONTH)

        # Swap the PAID_LEAVE rows to OTHER and recompute — must be identical.
        for a in db.query(Absence).filter(Absence.user_id == employee.id).all():
            a.type = AbsenceType.OTHER
        db.commit()
        db.expire_all()
        target_other = calculation_service.get_monthly_target(db, employee, YEAR, MONTH)
        balance_other = calculation_service.get_monthly_balance(db, employee, YEAR, MONTH)

        assert target_paid == target_other
        assert balance_paid == balance_other


# ---------------------------------------------------------------------------
# PUT switching the flag re-types linked absences
# ---------------------------------------------------------------------------

class TestPutSwitchesType:
    def test_switch_vacation_to_paid_leave(self, db, employee, admin_client):
        """Prüft dass Umstellen von Urlaub auf Freistellung den Absence-Typ ändert."""
        closure = _create_closure(admin_client, "Sommer", MON, WED, counts_as_vacation=True)
        assert all(a.type == AbsenceType.VACATION for a in _closure_absences(db, employee, closure["id"]))

        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Sommer",
            "start_date": MON.isoformat(),
            "end_date": WED.isoformat(),
            "counts_as_vacation": False,
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["counts_as_vacation"] is False

        db.expire_all()
        absences = _closure_absences(db, employee, closure["id"])
        assert {a.date for a in absences} == {MON, TUE, WED}
        assert all(a.type == AbsenceType.PAID_LEAVE for a in absences)

        # Budget freed up again after the switch.
        account = calculation_service.get_vacation_account(db, employee, YEAR)
        assert account["used_hours"] == 0.0

    def test_switch_paid_leave_to_vacation(self, db, employee, admin_client):
        """Prüft dass Umstellen von Freistellung auf Urlaub den Absence-Typ ändert."""
        closure = _create_closure(admin_client, "Sommer", MON, WED, counts_as_vacation=False)
        assert all(a.type == AbsenceType.PAID_LEAVE for a in _closure_absences(db, employee, closure["id"]))

        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Sommer",
            "start_date": MON.isoformat(),
            "end_date": WED.isoformat(),
            "counts_as_vacation": True,
        })
        assert resp.status_code == 200, resp.text

        db.expire_all()
        absences = _closure_absences(db, employee, closure["id"])
        assert all(a.type == AbsenceType.VACATION for a in absences)
        # 3 workdays * 8h now deducted from the budget.
        account = calculation_service.get_vacation_account(db, employee, YEAR)
        assert account["used_hours"] == 24.0
