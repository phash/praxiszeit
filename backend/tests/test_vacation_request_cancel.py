"""Tests for vacation request cancellation (GitHub Issue #90).

Covers withdrawal / cancellation of vacation requests from both the
employee side and the admin-on-behalf side, including the newly allowed
case of cancelling APPROVED requests whose start date lies in the future.
"""

from datetime import date, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType, TimeEntryAuditLog
from app.models.tenant import Tenant
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _create_test_app() -> FastAPI:
    from app.routers import admin_vacations, vacation_requests

    app = FastAPI(title="PraxisZeit Vacation-Cancel Test")
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(admin_vacations.router)
    app.include_router(vacation_requests.router)
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
    tenant = Tenant(
        id=DEFAULT_TENANT_ID, name="Default", slug="default",
        is_active=True, mode="single",
    )
    db.add(tenant)
    db.commit()
    return tenant


@pytest.fixture
def employee(db, default_tenant):
    from app.services import auth_service
    u = User(
        username="emp", email="emp@example.com",
        password_hash=auth_service.hash_password("x"),
        first_name="Anna", last_name="Müller",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def other_employee(db, default_tenant):
    from app.services import auth_service
    u = User(
        username="emp2", email="emp2@example.com",
        password_hash=auth_service.hash_password("x"),
        first_name="Ben", last_name="Schmidt",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    from app.services import auth_service
    u = User(
        username="adm", email="adm@example.com",
        password_hash=auth_service.hash_password("x"),
        first_name="Chef", last_name="Admin",
        role=UserRole.ADMIN, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_client(db_session, current_user):
    def override_db():
        yield db_session
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: current_user
    _app.dependency_overrides[require_admin] = lambda: current_user
    client = TestClient(_app)
    yield client
    _app.dependency_overrides.clear()


@pytest.fixture
def employee_client(db, employee):
    yield from _make_client(db, employee)


@pytest.fixture
def other_employee_client(db, other_employee):
    yield from _make_client(db, other_employee)


@pytest.fixture
def admin_client(db, admin):
    yield from _make_client(db, admin)


def _vr(db, user, status_val, start, end=None, absence_type="vacation", hours=8.0):
    vr = VacationRequest(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        date=start, end_date=end, hours=hours,
        absence_type=absence_type, status=status_val,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


def _abs(db, user, d, absence_type=AbsenceType.VACATION, hours=8.0):
    a = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        date=d, type=absence_type, hours=hours,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ---------------------------------------------------------------------------
# Employee-side withdraw
# ---------------------------------------------------------------------------

class TestEmployeeWithdraw:
    def test_withdraw_pending_deletes_request(self, db, employee, employee_client):
        """Offenen Antrag zurückziehen → DB-Row verschwindet (bestehendes Verhalten, Regression-Check)."""
        vr = _vr(db, employee, VacationRequestStatus.PENDING.value, date.today() + timedelta(days=30))
        resp = employee_client.delete(f"/api/vacation-requests/{vr.id}")
        assert resp.status_code == 204
        assert db.query(VacationRequest).filter(VacationRequest.id == vr.id).first() is None

    def test_withdraw_approved_future_deletes_absences_and_flags_withdrawn(
        self, db, employee, employee_client
    ):
        """Genehmigten zukünftigen Antrag stornieren → Absences werden gelöscht, VR→WITHDRAWN."""
        start = date.today() + timedelta(days=30)
        end = start + timedelta(days=2)
        vr = _vr(db, employee, VacationRequestStatus.APPROVED.value, start, end)
        _abs(db, employee, start)
        _abs(db, employee, start + timedelta(days=1))
        _abs(db, employee, end)

        resp = employee_client.delete(f"/api/vacation-requests/{vr.id}")
        assert resp.status_code == 204

        db.refresh(vr)
        assert vr.status == VacationRequestStatus.WITHDRAWN.value

        remaining = db.query(Absence).filter(Absence.user_id == employee.id).count()
        assert remaining == 0

        # Audit-trail documents the cancellation
        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_cancel"
        ).all()
        assert len(audits) == 3

    def test_withdraw_approved_past_is_rejected(self, db, employee, employee_client):
        """Start in der Vergangenheit → 400, weil Arbeitstag(e) bereits ausgefallen sind."""
        yesterday = date.today() - timedelta(days=1)
        vr = _vr(db, employee, VacationRequestStatus.APPROVED.value, yesterday)
        _abs(db, employee, yesterday)

        resp = employee_client.delete(f"/api/vacation-requests/{vr.id}")
        assert resp.status_code == 400

        # State untouched
        db.refresh(vr)
        assert vr.status == VacationRequestStatus.APPROVED.value
        assert db.query(Absence).filter(Absence.user_id == employee.id).count() == 1

    def test_withdraw_approved_today_is_rejected(self, db, employee, employee_client):
        """Start = heute → schon begonnen, Storno verweigert."""
        vr = _vr(db, employee, VacationRequestStatus.APPROVED.value, date.today())
        resp = employee_client.delete(f"/api/vacation-requests/{vr.id}")
        assert resp.status_code == 400

    def test_withdraw_rejected_is_rejected(self, db, employee, employee_client):
        """Abgelehnte Anträge sind nicht zurückziehbar — nichts zu stornieren."""
        vr = _vr(db, employee, VacationRequestStatus.REJECTED.value,
                 date.today() + timedelta(days=10))
        resp = employee_client.delete(f"/api/vacation-requests/{vr.id}")
        assert resp.status_code == 400

    def test_withdraw_foreign_request_returns_404(
        self, db, employee, other_employee, other_employee_client
    ):
        """#120: Fremden Antrag zurückziehen → 404 (wie unbekannt), auch im
        selben Tenant — kein Existenz-Leak via Response-Code."""
        vr = _vr(db, employee, VacationRequestStatus.PENDING.value,
                 date.today() + timedelta(days=30))
        resp = other_employee_client.delete(f"/api/vacation-requests/{vr.id}")
        assert resp.status_code == 404

    def test_withdraw_only_matching_absence_type_is_deleted(
        self, db, employee, employee_client
    ):
        """Bei Storno nur Absences vom selben Typ löschen (z.B. vacation), andere Typen bleiben."""
        start = date.today() + timedelta(days=30)
        vr = _vr(db, employee, VacationRequestStatus.APPROVED.value, start,
                 absence_type="vacation")
        _abs(db, employee, start, absence_type=AbsenceType.VACATION)
        _abs(db, employee, start, absence_type=AbsenceType.TRAINING)

        resp = employee_client.delete(f"/api/vacation-requests/{vr.id}")
        assert resp.status_code == 204

        types = {a.type for a in db.query(Absence).all()}
        assert types == {AbsenceType.TRAINING}


# ---------------------------------------------------------------------------
# Admin-side cancel
# ---------------------------------------------------------------------------

class TestAdminCancel:
    def test_admin_cancels_approved_future_request(self, db, employee, admin_client):
        """Admin kann genehmigten zukünftigen Antrag stellvertretend stornieren."""
        start = date.today() + timedelta(days=14)
        vr = _vr(db, employee, VacationRequestStatus.APPROVED.value, start)
        _abs(db, employee, start)

        resp = admin_client.delete(f"/api/admin/vacation-requests/{vr.id}")
        assert resp.status_code == 204

        db.refresh(vr)
        assert vr.status == VacationRequestStatus.WITHDRAWN.value
        assert db.query(Absence).filter(Absence.user_id == employee.id).count() == 0

    def test_admin_cancels_pending_request(self, db, employee, admin_client):
        """Offener Antrag via Admin-Storno → DB-Row verschwindet."""
        vr = _vr(db, employee, VacationRequestStatus.PENDING.value,
                 date.today() + timedelta(days=5))
        resp = admin_client.delete(f"/api/admin/vacation-requests/{vr.id}")
        assert resp.status_code == 204
        assert db.query(VacationRequest).filter(VacationRequest.id == vr.id).first() is None

    def test_admin_cannot_cancel_started_vacation(self, db, employee, admin_client):
        """Angefangener Urlaub (start <= heute) — Admin-Storno verweigert."""
        vr = _vr(db, employee, VacationRequestStatus.APPROVED.value, date.today())
        resp = admin_client.delete(f"/api/admin/vacation-requests/{vr.id}")
        assert resp.status_code == 400

    def test_admin_404_for_unknown_id(self, admin_client):
        resp = admin_client.delete("/api/admin/vacation-requests/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_admin_can_delete_rejected_request(self, db, employee, admin_client):
        """Abgelehnte Anträge dürfen vom Admin geprundet werden — keine Side-Effects
        (es gibt keine Absences zu einem rejected request), die Ablehnung selbst
        bleibt im Audit-Log erhalten. Vorher gab der Endpoint 400 zurück, was
        u.a. die E2E-Cleanup-Fixture brach (rejected leftovers akkumulierten)."""
        vr = _vr(
            db, employee, VacationRequestStatus.REJECTED.value,
            date.today() + timedelta(days=10),
        )
        vr.rejection_reason = "E2E reject"
        db.commit()

        resp = admin_client.delete(f"/api/admin/vacation-requests/{vr.id}")
        assert resp.status_code == 204
        assert db.query(VacationRequest).filter(VacationRequest.id == vr.id).first() is None
