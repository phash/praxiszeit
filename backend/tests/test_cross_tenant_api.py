"""
Cross-tenant API isolation tests.

These tests verify the APPLICATION-LAYER tenant scoping that sits on top of
PostgreSQL RLS. RLS-level isolation is covered by test_tenant_rls.py against
a real Postgres; these tests run on SQLite and exercise the explicit
`tenant_id == current_user.tenant_id` filters that CLAUDE.md mandates as
belt-and-suspenders defence (F-026).

Goal: a user authenticated as a member of Tenant A must never be able to
read, update, or delete data owned by Tenant B — even when they guess or
scrape the UUID of a Tenant B resource.
"""

import uuid
import pytest
from datetime import date, time, timedelta, datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TimeEntry, ChangeRequest, ChangeRequestStatus, ChangeRequestType
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app

TENANT_A_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
TENANT_B_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")


@pytest.fixture(scope="function")
def _db_session():
    """Fresh SQLite session per test."""
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.commit()
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.commit()
        Base.metadata.drop_all(bind=engine, checkfirst=True)


@pytest.fixture(scope="function")
def two_tenants(_db_session):
    """Create two isolated tenants."""
    for tid, name in [(TENANT_A_ID, "Tenant A"), (TENANT_B_ID, "Tenant B")]:
        _db_session.add(Tenant(id=tid, name=name, slug=f"t-{tid.hex[:8]}", is_active=True, mode="multi"))
    _db_session.commit()
    return TENANT_A_ID, TENANT_B_ID


def _make_user(db, tenant_id, *, role=UserRole.EMPLOYEE, username=None):
    u = User(
        username=username or f"user_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@test.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Test",
        last_name="User",
        role=role,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture(scope="function")
def admin_a(_db_session, two_tenants):
    return _make_user(_db_session, TENANT_A_ID, role=UserRole.ADMIN, username="admin_a")


@pytest.fixture(scope="function")
def employee_b(_db_session, two_tenants):
    return _make_user(_db_session, TENANT_B_ID, role=UserRole.EMPLOYEE, username="employee_b")


@pytest.fixture(scope="function")
def admin_b(_db_session, two_tenants):
    return _make_user(_db_session, TENANT_B_ID, role=UserRole.ADMIN, username="admin_b")


@pytest.fixture(scope="function")
def client_as_admin_a(_db_session, admin_a):
    """Authenticated as admin of Tenant A."""
    def _override_db():
        yield _db_session

    def _current():
        return admin_a

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _current
    test_app.dependency_overrides[require_admin] = _current

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


# ─── Tests ──────────────────────────────────────────────────────────────


def test_admin_a_cannot_read_tenant_b_user(_db_session, client_as_admin_a, employee_b):
    """GET /admin/users/{tenant_b_user_id} — must return 404 from _get_user_in_tenant (F-026)."""
    resp = client_as_admin_a.get(f"/api/admin/users/{employee_b.id}")
    assert resp.status_code == 404, resp.text


def test_admin_a_cannot_update_tenant_b_user(_db_session, client_as_admin_a, employee_b):
    """PUT /admin/users/{tenant_b_user_id} — must return 404 before mutation."""
    resp = client_as_admin_a.put(
        f"/api/admin/users/{employee_b.id}",
        json={"first_name": "Compromised"},
    )
    assert resp.status_code == 404, resp.text

    # Verify the victim's name was NOT changed
    _db_session.expire_all()
    victim = _db_session.query(User).filter(User.id == employee_b.id).first()
    assert victim.first_name == "Test"


def test_admin_a_cannot_deactivate_tenant_b_user(_db_session, client_as_admin_a, employee_b):
    """POST /admin/users/{tenant_b_user_id}/deactivate — must not touch victim."""
    resp = client_as_admin_a.post(f"/api/admin/users/{employee_b.id}/deactivate")
    assert resp.status_code == 404, resp.text

    _db_session.expire_all()
    victim = _db_session.query(User).filter(User.id == employee_b.id).first()
    assert victim.is_active is True


def test_admin_a_cannot_reset_tenant_b_user_password(_db_session, client_as_admin_a, employee_b):
    """POST /admin/users/{tenant_b_user_id}/set-password — must not succeed."""
    original_hash = employee_b.password_hash
    resp = client_as_admin_a.post(
        f"/api/admin/users/{employee_b.id}/set-password",
        json={"password": "AttackerKnows2025!"},
    )
    assert resp.status_code == 404, resp.text

    _db_session.expire_all()
    victim = _db_session.query(User).filter(User.id == employee_b.id).first()
    assert victim.password_hash == original_hash


def test_admin_a_cannot_approve_tenant_b_change_request(_db_session, client_as_admin_a, employee_b):
    """
    POST /admin/change-requests/{cr_id}/review — tenant filter in the review
    query (admin_change_requests.py:95) must make Tenant B's CR invisible to
    Tenant A's admin, even when the CR id is known.
    """
    cr = ChangeRequest(
        id=uuid.uuid4(),
        user_id=employee_b.id,
        tenant_id=TENANT_B_ID,
        request_type=ChangeRequestType.CREATE,
        status=ChangeRequestStatus.PENDING,
        proposed_date=date.today(),
        proposed_start_time=time(8, 0),
        proposed_end_time=time(16, 0),
        proposed_break_minutes=30,
        reason="test",
        entry_kind="time_entry",
    )
    _db_session.add(cr)
    _db_session.commit()

    resp = client_as_admin_a.post(
        f"/api/admin/change-requests/{cr.id}/review",
        json={"action": "approve"},
    )
    assert resp.status_code == 404, resp.text

    _db_session.expire_all()
    stored = _db_session.query(ChangeRequest).filter(ChangeRequest.id == cr.id).first()
    assert stored.status == ChangeRequestStatus.PENDING


def test_admin_a_bulk_approve_ignores_tenant_b_crs(_db_session, client_as_admin_a, employee_b):
    """Bulk approve: every item for Tenant B must be reported as failed, nothing mutated."""
    cr_b = ChangeRequest(
        id=uuid.uuid4(),
        user_id=employee_b.id,
        tenant_id=TENANT_B_ID,
        request_type=ChangeRequestType.CREATE,
        status=ChangeRequestStatus.PENDING,
        proposed_date=date.today(),
        proposed_start_time=time(9, 0),
        proposed_end_time=time(17, 0),
        proposed_break_minutes=30,
        reason="test",
        entry_kind="time_entry",
    )
    _db_session.add(cr_b)
    _db_session.commit()

    resp = client_as_admin_a.post(
        "/api/admin/change-requests/bulk-review",
        json={"request_ids": [str(cr_b.id)], "action": "approve"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["succeeded"] == 0
    assert body["failed"] == 1

    _db_session.expire_all()
    stored = _db_session.query(ChangeRequest).filter(ChangeRequest.id == cr_b.id).first()
    assert stored.status == ChangeRequestStatus.PENDING
