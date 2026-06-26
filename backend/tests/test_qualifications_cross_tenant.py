"""Cross-tenant isolation for the Einweisungs-/Skill-Matrix (#305 M2d)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.models.shift_planning import Workstation, WorkstationQualification
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
    for tid in (TENANT_A_ID, TENANT_B_ID):
        _db_session.add(SystemSetting(key="shift_planning_enabled", tenant_id=tid, value="true"))
    _db_session.commit()
    return TENANT_A_ID, TENANT_B_ID


def _make_user(db, tenant_id, *, role=UserRole.EMPLOYEE, username=None):
    u = User(
        username=username or f"user_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@test.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Test", last_name="User", role=role,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=tenant_id,
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
    emp_b = _make_user(_db_session, TENANT_B_ID, username="emp_b")
    ws_b = Workstation(tenant_id=TENANT_B_ID, name="B-Tresen")
    _db_session.add(ws_b)
    _db_session.flush()
    qual = WorkstationQualification(tenant_id=TENANT_B_ID, user_id=emp_b.id, workstation_id=ws_b.id)
    _db_session.add(qual)
    _db_session.commit()
    return {"emp": emp_b, "ws": ws_b}


@pytest.fixture(scope="function")
def client_a(_db_session, admin_a):
    def _override_db():
        yield _db_session

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: admin_a
    test_app.dependency_overrides[require_admin] = lambda: admin_a
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def test_matrix_excludes_tenant_b(client_a, tenant_b_data):
    m = client_a.get(f"{BASE}/qualifications").json()
    assert all(u["id"] != str(tenant_b_data["emp"].id) for u in m["users"])
    assert all(w["id"] != str(tenant_b_data["ws"].id) for w in m["workstations"])
    assert m["qualifications"] == []


def test_cannot_set_quals_for_tenant_b_user(client_a, tenant_b_data):
    # B-User is not in admin_a's tenant → 404
    r = client_a.put(f"{BASE}/qualifications/{tenant_b_data['emp'].id}", json={"workstation_ids": []})
    assert r.status_code == 404, r.text


def test_cannot_use_tenant_b_workstation(client_a, tenant_b_data, admin_a):
    # admin_a's own user, but a Tenant-B workstation → 404 (ws not in tenant)
    r = client_a.put(
        f"{BASE}/qualifications/{admin_a.id}",
        json={"workstation_ids": [str(tenant_b_data["ws"].id)]},
    )
    assert r.status_code == 404, r.text
