"""Tests for plan-based seat enforcement + features (Phase 5 / Issue #96)."""

from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service
from app.services.plan_enforcement import (
    check_seat_limit, get_plan_features, seat_limit_for,
)
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app


TENANT_ID = uuid.UUID("dddddddd-0000-4000-8000-000000000501")


@pytest.fixture
def _db_session():
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


def _seed_tenant(db, plan, seat_override=None):
    t = Tenant(
        id=TENANT_ID, name="T", slug="t-seat", is_active=True, mode="multi",
        plan=plan, subscription_status="active", seat_limit=seat_override,
    )
    db.add(t)
    db.commit()
    return t


def _mk_user(db, username, *, active=True, role=UserRole.EMPLOYEE):
    u = User(
        username=username, email=f"{username}@t.de",
        password_hash=auth_service.hash_password("S3curePassword!"),
        first_name=username, last_name="X", role=role,
        weekly_hours=40, vacation_days=30, work_days_per_week=5,
        is_active=active, tenant_id=TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ─── pure helpers ────────────────────────────────────────────────

def test_plan_defaults():
    assert seat_limit_for(Tenant(plan="trial")) == 5
    assert seat_limit_for(Tenant(plan="starter")) == 5
    assert seat_limit_for(Tenant(plan="pro")) == 25
    assert seat_limit_for(Tenant(plan="enterprise")) is None


def test_seat_limit_override_wins():
    assert seat_limit_for(Tenant(plan="starter", seat_limit=50)) == 50
    assert seat_limit_for(Tenant(plan="pro", seat_limit=1)) == 1


def test_plan_feature_matrix():
    assert "sso" in get_plan_features("pro")
    assert "sso" not in get_plan_features("starter")
    assert "custom_branding" in get_plan_features("enterprise")
    assert "custom_branding" not in get_plan_features("pro")


# ─── check_seat_limit ────────────────────────────────────────────

def test_check_seat_limit_allows_below(_db_session):
    t = _seed_tenant(_db_session, "starter")
    _mk_user(_db_session, "u1")
    _mk_user(_db_session, "u2")
    # 2/5 — must not raise
    check_seat_limit(_db_session, t)


def test_check_seat_limit_blocks_at_limit(_db_session):
    t = _seed_tenant(_db_session, "starter")
    for i in range(5):
        _mk_user(_db_session, f"u{i}")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        check_seat_limit(_db_session, t)
    assert exc.value.status_code == 403


def test_check_seat_limit_inactive_users_do_not_count(_db_session):
    t = _seed_tenant(_db_session, "starter")
    for i in range(5):
        _mk_user(_db_session, f"a{i}", active=True)
    for i in range(3):
        _mk_user(_db_session, f"b{i}", active=False)
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        check_seat_limit(_db_session, t)


def test_check_seat_limit_enterprise_unlimited(_db_session):
    t = _seed_tenant(_db_session, "enterprise")
    for i in range(50):
        _mk_user(_db_session, f"x{i}")
    check_seat_limit(_db_session, t)  # must not raise


# ─── Endpoint: /api/admin/users enforces ─────────────────────────

@pytest.fixture
def admin_client(_db_session):
    t = _seed_tenant(_db_session, "starter")
    admin_user = _mk_user(_db_session, "admin@t.de", role=UserRole.ADMIN)

    def _db(): yield _db_session
    def _who(): return admin_user
    test_app.dependency_overrides[get_db] = _db
    test_app.dependency_overrides[get_current_user] = _who
    test_app.dependency_overrides[require_admin] = _who
    with TestClient(test_app) as c:
        yield c, t
    test_app.dependency_overrides.clear()


def test_create_user_blocked_at_seat_limit(_db_session, admin_client):
    client, t = admin_client
    # Admin counts as 1 seat; create 4 more to hit limit 5
    for i in range(4):
        _mk_user(_db_session, f"emp{i}")
    payload = {
        "username": "too_many", "password": "S3curePassword!",
        "first_name": "X", "last_name": "Y", "role": "employee",
        "weekly_hours": 40, "vacation_days": 30, "work_days_per_week": 5,
        "track_hours": True, "calendar_color": "#000000",
        "use_daily_schedule": False,
    }
    resp = client.post("/api/admin/users", json=payload)
    assert resp.status_code == 403, resp.text
    assert "Sitzlimit" in resp.json()["detail"]


def test_reactivate_blocked_at_seat_limit(_db_session, admin_client):
    client, t = admin_client
    # Admin + 4 active = 5. Plus one inactive who tries to reactivate.
    for i in range(4):
        _mk_user(_db_session, f"emp{i}")
    inactive = _mk_user(_db_session, "ghost", active=False)

    resp = client.post(f"/api/admin/users/{inactive.id}/reactivate")
    assert resp.status_code == 403, resp.text


# ─── /api/tenant/usage ────────────────────────────────────────────

def test_usage_endpoint_returns_seats_and_plan(_db_session, admin_client):
    client, _ = admin_client
    for i in range(2):
        _mk_user(_db_session, f"u{i}")
    resp = client.get("/api/tenant/usage")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["plan"] == "starter"
    assert data["seat_limit"] == 5
    # admin + 2 employees = 3
    assert data["used_seats"] == 3
    assert "reports" in data["features"]
    assert "sso" not in data["features"]  # starter


def test_usage_endpoint_enterprise_unlimited(_db_session):
    # Fresh tenant with plan=enterprise
    t = Tenant(
        id=TENANT_ID, name="E", slug="e-seat", is_active=True, mode="multi",
        plan="enterprise", subscription_status="active",
    )
    _db_session.add(t)
    _db_session.commit()
    admin_user = _mk_user(_db_session, "admin2", role=UserRole.ADMIN)

    def _db(): yield _db_session
    def _who(): return admin_user
    test_app.dependency_overrides[get_db] = _db
    test_app.dependency_overrides[get_current_user] = _who
    test_app.dependency_overrides[require_admin] = _who
    try:
        with TestClient(test_app) as client:
            resp = client.get("/api/tenant/usage")
            assert resp.status_code == 200, resp.text
            assert resp.json()["seat_limit"] is None
    finally:
        test_app.dependency_overrides.clear()
