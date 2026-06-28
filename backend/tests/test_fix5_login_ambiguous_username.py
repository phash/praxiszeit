"""Fix #5: login by username is ambiguous when two tenants share a username.
On ambiguity the login must be REFUSED (never authenticate the wrong account),
with a neutral error. A unique username still logs in.
"""
import uuid

from unittest.mock import patch
from fastapi.testclient import TestClient

from app.database import get_db
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service

from tests.test_endpoints import test_app as app
from tests.test_endpoints import _db_session  # noqa: F401  (pytest fixture)

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def _tenant(db, tid, slug):
    t = Tenant(id=tid, name=slug, slug=slug, is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, tid, username, password, active=True):
    u = User(
        username=username, email=f"{username}-{tid}@t.de",
        password_hash=auth_service.hash_password(password),
        first_name="F", last_name="L", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=active, tenant_id=tid,
    )
    db.add(u)
    db.commit()
    return u


def _login(db, username, password):
    def _override_db():
        yield db
    app.dependency_overrides[get_db] = _override_db
    try:
        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(app) as client:
                return client.post("/api/auth/login", json={
                    "username": username, "password": password,
                })
    finally:
        app.dependency_overrides.clear()


def test_ambiguous_username_rejected(_db_session):
    db = _db_session
    _tenant(db, DEFAULT_TENANT_ID, "default")
    _tenant(db, OTHER_TENANT_ID, "other")
    # Same username, two ACTIVE accounts in different tenants, different passwords.
    _user(db, DEFAULT_TENANT_ID, "fix5shared", "PassOne2025!")
    _user(db, OTHER_TENANT_ID, "fix5shared", "PassTwo2025!")

    # Even with a password that is valid for ONE of the accounts, the login is
    # refused — we must not authenticate the wrong (or any) account.
    resp = _login(db, "fix5shared", "PassOne2025!")
    assert resp.status_code == 401
    assert "access_token" not in resp.json()


def test_unique_username_still_logs_in(_db_session):
    db = _db_session
    _tenant(db, DEFAULT_TENANT_ID, "default")
    _tenant(db, OTHER_TENANT_ID, "other")
    # Same username but the OTHER tenant's account is INACTIVE → unambiguous.
    _user(db, DEFAULT_TENANT_ID, "fix5unique", "PassOne2025!")
    _user(db, OTHER_TENANT_ID, "fix5unique", "PassTwo2025!", active=False)

    resp = _login(db, "fix5unique", "PassOne2025!")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["username"] == "fix5unique"
