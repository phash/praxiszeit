"""#377 Baustein 2b: use_fixed_monthly_target Schema-Feld + Validierung.

Harness wie backend/tests/test_milog.py (lokale _app() + dependency_overrides,
/api-Pfade, headerloser TestClient).
"""
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

USERS = "/api/admin/users"


def _app() -> FastAPI:
    from app.routers import admin
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    a = FastAPI()
    limiter.enabled = False
    a.state.limiter = limiter
    a.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    a.include_router(admin.router)
    return a


app = _app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="D", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, username, role=UserRole.EMPLOYEE, weekly=Decimal("40")):
    u = User(username=username, email=f"{username}@x.de",
             password_hash=auth_service.hash_password("test123"),
             first_name=username, last_name="T", role=role, weekly_hours=weekly,
             vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "admin1", role=UserRole.ADMIN, weekly=Decimal("40"))


def _client_as(db, user, admin_user):
    def od():
        yield db
    app.dependency_overrides[get_db] = od
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


BASE_PAYLOAD = {
    "username": "fx", "first_name": "F", "last_name": "X", "password": "E2ePass1234!",
    "role": "employee", "weekly_hours": 40, "vacation_days": 30, "work_days_per_week": 5,
}


# --------------------------------------------------------------------------- #
# UserCreate validation
# --------------------------------------------------------------------------- #
def test_create_fixed_target_without_agreed_hours_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "use_fixed_monthly_target": True,
        "track_hours": True,
        "milog_working_time_account": True,
        # agreed_monthly_hours missing
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_fixed_target_with_track_hours_false_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": False,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_fixed_target_with_milog_false_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": False,
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_fixed_target_with_all_requirements_ok(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 201, resp.text
    uid = resp.json()["user"]["id"]
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert row["use_fixed_monthly_target"] is True
    assert row["agreed_monthly_hours"] == 173.3
    app.dependency_overrides.clear()


def test_create_without_fixed_target_ignores_missing_agreed(db, admin, default_tenant):
    # Sanity: default flag False must NOT trigger the new validator at all.
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={**BASE_PAYLOAD, "username": "plain"})
    assert resp.status_code == 201, resp.text
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# UserUpdate validation (partial payloads)
# --------------------------------------------------------------------------- #
def _create_plain_user(client, username="upduser"):
    resp = client.post(USERS, json={**BASE_PAYLOAD, "username": username})
    assert resp.status_code == 201, resp.text
    return resp.json()["user"]["id"]


def test_update_turn_on_fixed_target_without_agreed_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd1")
    resp = client.put(f"{USERS}/{uid}", json={"use_fixed_monthly_target": True})
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_update_turn_on_fixed_target_with_track_hours_false_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd2")
    resp = client.put(f"{USERS}/{uid}", json={
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": False,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_update_turn_on_fixed_target_with_milog_false_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd3")
    resp = client.put(f"{USERS}/{uid}", json={
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": False,
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_update_turn_on_fixed_target_missing_track_hours_field_fails(db, admin, default_tenant):
    # Partial update sets flag True but omits track_hours/milog entirely (None) —
    # must be treated the same as explicitly False, not silently trusted from DB.
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd4")
    resp = client.put(f"{USERS}/{uid}", json={
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_update_turn_on_fixed_target_with_all_requirements_ok(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd5")
    resp = client.put(f"{USERS}/{uid}", json={
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 200, resp.text
    assert client.get(f"{USERS}/{uid}").json()["use_fixed_monthly_target"] is True
    app.dependency_overrides.clear()


def test_update_unrelated_field_without_flag_unaffected(db, admin, default_tenant):
    # Existing partial-update flows (unrelated fields) must not be broken by the
    # new validator when use_fixed_monthly_target is not part of the payload.
    client = _client_as(db, admin, admin)
    uid = _create_plain_user(client, "upd6")
    resp = client.put(f"{USERS}/{uid}", json={"first_name": "Changed"})
    assert resp.status_code == 200, resp.text
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Release-Review 1.15.0 (#377 Baustein 2b): partial updates that turn OFF a
# prerequisite while use_fixed_monthly_target is NOT in the payload. The
# UserUpdate schema validator only sees this payload (not the DB row), so it
# skips (flag absent → falsy → no check). Without a router-level effective-
# state guard this silently persists an INVALID row (use_fixed_monthly_target
# still True in the DB, but milog/track_hours off) — the plausibility warning
# goes dark and the design invariant is broken.
# --------------------------------------------------------------------------- #
def _create_fixed_target_user(client, username):
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "username": username,
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["user"]["id"]


def test_update_isolated_milog_off_on_fixed_target_user_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_fixed_target_user(client, "iso1")
    resp = client.put(f"{USERS}/{uid}", json={"milog_working_time_account": False})
    assert resp.status_code == 400, resp.text
    # DB row must remain untouched/consistent — the invariant-breaking update
    # must not have been persisted.
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert row["use_fixed_monthly_target"] is True
    assert row["milog_working_time_account"] is True
    app.dependency_overrides.clear()


def test_update_isolated_track_hours_off_on_fixed_target_user_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = _create_fixed_target_user(client, "iso2")
    resp = client.put(f"{USERS}/{uid}", json={"track_hours": False})
    assert resp.status_code == 400, resp.text
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert row["use_fixed_monthly_target"] is True
    assert row["track_hours"] is True
    app.dependency_overrides.clear()


def test_update_normal_field_on_fixed_target_user_still_ok(db, admin, default_tenant):
    # Sanity: a normal update on an existing fixed-target user that does not
    # touch any of the four invariant fields must keep working (200).
    client = _client_as(db, admin, admin)
    uid = _create_fixed_target_user(client, "iso3")
    resp = client.put(f"{USERS}/{uid}", json={"first_name": "Changed"})
    assert resp.status_code == 200, resp.text
    app.dependency_overrides.clear()


def test_update_disable_fixed_target_and_milog_together_ok(db, admin, default_tenant):
    # Turning the flag itself off in the same payload is the documented,
    # correct way to leave fixed mode — must stay allowed.
    client = _client_as(db, admin, admin)
    uid = _create_fixed_target_user(client, "iso4")
    resp = client.put(f"{USERS}/{uid}", json={
        "use_fixed_monthly_target": False,
        "milog_working_time_account": False,
    })
    assert resp.status_code == 200, resp.text
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# UserListResponse round-trip
# --------------------------------------------------------------------------- #
def test_userlist_carries_use_fixed_monthly_target(db, admin, default_tenant):
    # Regression: das Edit-Formular liest die Liste; fehlt das Feld dort,
    # setzt jeder Save es still auf Default (wie #376/#377-Lektion).
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "username": "listcheck",
        "use_fixed_monthly_target": True,
        "agreed_monthly_hours": 173.3,
        "track_hours": True,
        "milog_working_time_account": True,
    })
    assert resp.status_code == 201, resp.text
    uid = resp.json()["user"]["id"]
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert "use_fixed_monthly_target" in row
    assert row["use_fixed_monthly_target"] is True
    app.dependency_overrides.clear()
