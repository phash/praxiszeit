"""Tests for #189: Betriebsferien-Teilnahme über ``receives_company_closures``
statt über die Admin-Rolle.

Hintergrund: Bisher filterte ``company_closures`` hart ``User.role != ADMIN``
raus, sodass ein Admin, der zugleich (ltd.) Angestellter ist, KEINE
Betriebsferien bekam (#189). Neu: ein per-User-Flag
``receives_company_closures`` (Default True) steuert die Teilnahme,
unabhängig von der Rolle.

Covers:
- Admin-User (Flag Default True) bekommt Closure-Absences (Regression #189).
- User mit Flag=False wird ausgeschlossen.
- Normaler Mitarbeiter bekommt weiterhin Absences.
- ``affected_employees`` zählt nach Flag, nicht nach Rolle (POST + GET).
- PUT re-synct einen neu berechtigten User (Recovery-Pfad für
  Bestands-Closures, die noch unter der alten Rollen-Logik entstanden).
"""

import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, CompanyClosure
from app.models.tenant import Tenant
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

# A clean Mon-Wed work stretch in March 2025 with no public holidays seeded.
MON = date(2025, 3, 10)
TUE = date(2025, 3, 11)
WED = date(2025, 3, 12)


def _create_test_app() -> FastAPI:
    from app.routers import company_closures

    app = FastAPI(title="PraxisZeit Closure receives-flag Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

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


def _make_user(db, username, role=UserRole.EMPLOYEE, receives_company_closures=True):
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
        receives_company_closures=receives_company_closures,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin(db, default_tenant):
    # The acting admin is ALSO an employee here (the #189 scenario: an admin
    # who tracks time / has a vacation account).
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


def _closure_absences(db, user, closure_id):
    return db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.closure_id == uuid.UUID(closure_id),
    ).order_by(Absence.date).all()


class TestReceivesFlagDrivesParticipation:
    def test_admin_with_default_flag_receives_closure_absences(self, db, admin, admin_client):
        """#189: Ein Admin (Flag Default True) bekommt Betriebsferien-Absences."""
        closure = _create_closure(admin_client, "Sommer", MON, WED)
        absences = _closure_absences(db, admin, closure["id"])
        assert {a.date for a in absences} == {MON, TUE, WED}

    def test_opted_out_user_receives_no_closure_absences(self, db, default_tenant, admin_client):
        """Ein User mit receives_company_closures=False bleibt außen vor."""
        optout = _make_user(db, "optout", receives_company_closures=False)
        closure = _create_closure(admin_client, "Sommer", MON, WED)
        assert _closure_absences(db, optout, closure["id"]) == []

    def test_regular_employee_still_receives_closure_absences(self, db, default_tenant, admin_client):
        """Kontrolle: normaler Mitarbeiter (Flag Default True) bekommt weiterhin Absences."""
        emp = _make_user(db, "emp1")
        closure = _create_closure(admin_client, "Sommer", MON, WED)
        assert {a.date for a in _closure_absences(db, emp, closure["id"])} == {MON, TUE, WED}


class TestAffectedCount:
    def test_affected_count_follows_flag_not_role(self, db, default_tenant, admin_client):
        """affected_employees zählt nach Flag, nicht nach Rolle (POST + GET).

        Asymmetrisch gewählt, damit Rollen-Logik (emp1 + optout = 2) und
        Flag-Logik (emp1 + admin + admin2 = 3) unterschiedliche Zahlen liefern.
        """
        _make_user(db, "emp1")  # EMPLOYEE, eligible both ways
        _make_user(db, "optout", receives_company_closures=False)  # EMPLOYEE, flag off -> excluded
        _make_user(db, "admin2", role=UserRole.ADMIN)  # ADMIN, flag on -> eligible by flag only
        # Plus the acting admin (ADMIN, flag on). Flag-logic total: emp1 + admin + admin2 = 3.
        body = _create_closure(admin_client, "Sommer", MON, WED)
        assert body["affected_employees"] == 3

        listing = admin_client.get("/api/company-closures/")
        assert listing.status_code == 200, listing.text
        assert listing.json()[0]["affected_employees"] == 3


class TestPutResyncsNewlyEligible:
    def test_put_backfills_user_after_flag_enabled(self, db, default_tenant, admin_client):
        """Recovery-Pfad: ein zunächst ausgeschlossener User wird nach Flag=True
        durch erneutes Speichern (PUT) der Betriebsferien nachgetragen."""
        latecomer = _make_user(db, "late", receives_company_closures=False)
        closure = _create_closure(admin_client, "Sommer", MON, WED)
        assert _closure_absences(db, latecomer, closure["id"]) == []

        # Enable participation, then re-save the closure unchanged.
        latecomer.receives_company_closures = True
        db.commit()
        resp = admin_client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "Sommer",
            "start_date": MON.isoformat(),
            "end_date": WED.isoformat(),
            "counts_as_vacation": True,
        })
        assert resp.status_code == 200, resp.text

        db.expire_all()
        assert {a.date for a in _closure_absences(db, latecomer, closure["id"])} == {MON, TUE, WED}
