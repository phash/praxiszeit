"""Cross-tenant isolation for Schichtplanung (#305).

Mirrors test_cross_tenant_api.py: a Tenant-A admin must never read/update/delete
Tenant-B shift-planning data, even when guessing UUIDs. Runs on SQLite and
exercises the explicit F-026 ``tenant_id ==`` filters (RLS is covered separately
against Postgres).
"""
import uuid
from datetime import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.models.shift_planning import (
    Location,
    Workstation,
    ShiftPlan,
    ShiftSlot,
    ShiftAssignment,
)
from app.services import auth_service
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app

BASE = "/api/shift-planning"
TENANT_A_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
TENANT_B_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")


@pytest.fixture(scope="function")
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


@pytest.fixture(scope="function")
def two_tenants(_db_session):
    for tid, name in [(TENANT_A_ID, "Tenant A"), (TENANT_B_ID, "Tenant B")]:
        _db_session.add(Tenant(id=tid, name=name, slug=f"t-{tid.hex[:8]}", is_active=True, mode="multi"))
    # enable the feature for BOTH tenants so the 404s we assert come from the
    # F-026 filter, not from the feature flag.
    for tid in (TENANT_A_ID, TENANT_B_ID):
        _db_session.add(SystemSetting(key="shift_planning_enabled", tenant_id=tid, value="true"))
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
def tenant_b_data(_db_session, two_tenants):
    """A full set of Tenant-B shift-planning rows."""
    emp_b = _make_user(_db_session, TENANT_B_ID, username="emp_b")
    loc = Location(tenant_id=TENANT_B_ID, name="B-Standort")
    _db_session.add(loc)
    _db_session.flush()
    ws = Workstation(tenant_id=TENANT_B_ID, name="B-Tresen", location_id=loc.id)
    _db_session.add(ws)
    _db_session.flush()
    plan = ShiftPlan(tenant_id=TENANT_B_ID, name="B-Plan", is_active=True, created_by=emp_b.id)
    _db_session.add(plan)
    _db_session.flush()
    slot = ShiftSlot(
        tenant_id=TENANT_B_ID, shift_plan_id=plan.id, workstation_id=ws.id,
        weekday=0, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
    )
    _db_session.add(slot)
    _db_session.flush()
    assignment = ShiftAssignment(tenant_id=TENANT_B_ID, shift_slot_id=slot.id, user_id=emp_b.id)
    _db_session.add(assignment)
    _db_session.commit()
    return {"loc": loc, "ws": ws, "plan": plan, "slot": slot, "emp": emp_b}


@pytest.fixture(scope="function")
def client_a(_db_session, admin_a):
    def _override_db():
        yield _db_session

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: admin_a
    test_app.dependency_overrides[require_admin] = lambda: admin_a
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


# ─── isolation tests ─────────────────────────────────────────────────


def test_lists_exclude_tenant_b(client_a, tenant_b_data):
    assert client_a.get(f"{BASE}/plans").json() == []
    assert client_a.get(f"{BASE}/locations").json() == []
    assert client_a.get(f"{BASE}/workstations").json() == []


def test_cannot_read_tenant_b_plan(client_a, tenant_b_data):
    assert client_a.get(f"{BASE}/plans/{tenant_b_data['plan'].id}").status_code == 404


def test_cannot_update_tenant_b_plan(client_a, tenant_b_data, _db_session):
    r = client_a.put(
        f"{BASE}/plans/{tenant_b_data['plan'].id}",
        json={"name": "hijacked", "description": "x"},
    )
    assert r.status_code == 404
    _db_session.expire_all()
    victim = _db_session.query(ShiftPlan).filter(ShiftPlan.id == tenant_b_data["plan"].id).first()
    assert victim.name == "B-Plan"


def test_cannot_delete_tenant_b_plan(client_a, tenant_b_data, _db_session):
    assert client_a.delete(f"{BASE}/plans/{tenant_b_data['plan'].id}").status_code == 404
    _db_session.expire_all()
    assert _db_session.query(ShiftPlan).filter(ShiftPlan.id == tenant_b_data["plan"].id).first() is not None


def test_cannot_update_tenant_b_slot(client_a, tenant_b_data):
    r = client_a.put(
        f"{BASE}/slots/{tenant_b_data['slot'].id}",
        json={"workstation_id": str(tenant_b_data["ws"].id), "weekday": 1,
              "start_time": "09:00", "end_time": "10:00", "min_staff": 0},
    )
    assert r.status_code == 404


def test_cannot_delete_tenant_b_location_or_workstation(client_a, tenant_b_data):
    assert client_a.delete(f"{BASE}/locations/{tenant_b_data['loc'].id}").status_code == 404
    assert client_a.delete(f"{BASE}/workstations/{tenant_b_data['ws'].id}").status_code == 404


def test_cannot_assign_into_tenant_b_slot(client_a, tenant_b_data, admin_a):
    r = client_a.put(
        f"{BASE}/slots/{tenant_b_data['slot'].id}/assignments",
        json={"user_ids": [str(admin_a.id)]},
    )
    assert r.status_code == 404
