"""Tests for editing PENDING vacation requests (employee + admin)."""

from datetime import date, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TimeEntryAuditLog
from app.models.tenant import Tenant
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _create_test_app() -> FastAPI:
    from app.routers import admin_vacations, vacation_requests

    app = FastAPI(title="PraxisZeit Vacation-Edit Test")
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


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, username, role=UserRole.EMPLOYEE, tenant_id=None):
    from app.services import auth_service
    u = User(
        username=username, email=f"{username}@example.com",
        password_hash=auth_service.hash_password("x"),
        first_name=username.title(), last_name="Test",
        role=role, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True,
        tenant_id=tenant_id or DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def employee(db, default_tenant):
    return _user(db, "emp")


@pytest.fixture
def other_employee(db, default_tenant):
    return _user(db, "emp2")


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "adm", role=UserRole.ADMIN)


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


def _vr(db, user, status_val=VacationRequestStatus.PENDING.value, start=None,
        end=None, absence_type="vacation", hours=8.0, note=None):
    vr = VacationRequest(
        user_id=user.id, tenant_id=user.tenant_id,
        date=start or date.today() + timedelta(days=30),
        end_date=end, hours=hours,
        absence_type=absence_type, status=status_val, note=note,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


# ===========================================================================
# Employee edit own pending
# ===========================================================================

class TestEmployeeEdit:
    def test_edit_pending_updates_fields(self, db, employee, employee_client):
        vr = _vr(db, employee, note="alt")
        new_date = (date.today() + timedelta(days=40)).isoformat()
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"date": new_date, "note": "neu", "hours": 6.0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["date"] == new_date
        assert body["note"] == "neu"
        assert body["hours"] == 6.0

    def test_edit_writes_audit_row(self, db, employee, employee_client):
        vr = _vr(db, employee, note="alt")
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "neu"}
        )
        assert resp.status_code == 200, resp.text
        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).all()
        assert len(audits) == 1
        a = audits[0]
        assert a.action == "update"
        assert a.user_id == employee.id
        assert a.changed_by == employee.id
        assert "alt" in (a.old_note or "")
        assert "neu" in (a.new_note or "")
        assert a.tenant_id == DEFAULT_TENANT_ID

    def test_edit_noop_writes_no_audit(self, db, employee, employee_client):
        vr = _vr(db, employee, note="same")
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "same"}
        )
        assert resp.status_code == 200
        assert resp.json()["note"] == "same"
        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).count()
        assert audits == 0

    def test_edit_foreign_request_forbidden(
        self, db, employee, other_employee, other_employee_client
    ):
        vr = _vr(db, employee)
        resp = other_employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "hack"}
        )
        assert resp.status_code == 403

    def test_edit_approved_rejected(self, db, employee, employee_client):
        vr = _vr(db, employee, status_val=VacationRequestStatus.APPROVED.value)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "x"}
        )
        assert resp.status_code == 400

    def test_edit_rejected_rejected(self, db, employee, employee_client):
        vr = _vr(db, employee, status_val=VacationRequestStatus.REJECTED.value)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "x"}
        )
        assert resp.status_code == 400

    def test_edit_withdrawn_rejected(self, db, employee, employee_client):
        vr = _vr(db, employee, status_val=VacationRequestStatus.WITHDRAWN.value)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "x"}
        )
        assert resp.status_code == 400

    def test_edit_invalid_range_rejected(self, db, employee, employee_client):
        start = date.today() + timedelta(days=30)
        vr = _vr(db, employee, start=start, end=start + timedelta(days=2))
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"end_date": (start - timedelta(days=1)).isoformat()},
        )
        assert resp.status_code == 400

    def test_edit_before_first_work_day_rejected(
        self, db, employee, employee_client
    ):
        employee.first_work_day = date.today() + timedelta(days=10)
        db.commit()
        vr = _vr(db, employee, start=date.today() + timedelta(days=30))
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"date": (date.today() + timedelta(days=5)).isoformat()},
        )
        assert resp.status_code == 400

    def test_edit_overlap_with_other_pending_rejected(
        self, db, employee, employee_client
    ):
        existing_start = date.today() + timedelta(days=60)
        _vr(db, employee, start=existing_start, end=existing_start + timedelta(days=4))
        target = _vr(db, employee, start=date.today() + timedelta(days=80))
        resp = employee_client.patch(
            f"/api/vacation-requests/{target.id}",
            json={"date": (existing_start + timedelta(days=2)).isoformat()},
        )
        assert resp.status_code == 409

    def test_edit_self_overlap_allowed(self, db, employee, employee_client):
        start = date.today() + timedelta(days=30)
        vr = _vr(db, employee, start=start, end=start + timedelta(days=4))
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"date": (start + timedelta(days=1)).isoformat()},
        )
        assert resp.status_code == 200, resp.text

    def test_edit_invalid_absence_type_rejected(
        self, db, employee, employee_client
    ):
        vr = _vr(db, employee)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"absence_type": "sick"}
        )
        # Pydantic validation -> 422
        assert resp.status_code == 422

    def test_edit_clear_end_date_via_explicit_null(
        self, db, employee, employee_client
    ):
        """Sending end_date: null collapses a range to a single-day request."""
        start = date.today() + timedelta(days=30)
        vr = _vr(db, employee, start=start, end=start + timedelta(days=4))
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"end_date": None}
        )
        assert resp.status_code == 200, resp.text
        db.refresh(vr)
        assert vr.end_date is None


# ===========================================================================
# Admin edit any pending in tenant
# ===========================================================================

class TestAdminEdit:
    def test_admin_edits_employee_pending(self, db, employee, admin, admin_client):
        vr = _vr(db, employee, note="alt")
        resp = admin_client.patch(
            f"/api/admin/vacation-requests/{vr.id}", json={"note": "admin-edit"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["note"] == "admin-edit"

        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).all()
        assert len(audits) == 1
        a = audits[0]
        assert a.user_id == employee.id          # affected user
        assert a.changed_by == admin.id          # acting principal

    def test_admin_cannot_edit_foreign_tenant(self, db, default_tenant, admin_client):
        from uuid import uuid4
        foreign_tid = uuid4()
        foreign = Tenant(id=foreign_tid, name="Foreign", slug="foreign",
                         is_active=True, mode="single")
        db.add(foreign)
        db.commit()
        foreign_emp = _user(db, "foreign_emp", tenant_id=foreign_tid)
        vr = _vr(db, foreign_emp)
        resp = admin_client.patch(
            f"/api/admin/vacation-requests/{vr.id}", json={"note": "hack"}
        )
        assert resp.status_code == 404  # 404 — don't leak existence

    def test_admin_cannot_edit_approved(self, db, employee, admin_client):
        vr = _vr(db, employee, status_val=VacationRequestStatus.APPROVED.value)
        resp = admin_client.patch(
            f"/api/admin/vacation-requests/{vr.id}", json={"note": "x"}
        )
        assert resp.status_code == 400
