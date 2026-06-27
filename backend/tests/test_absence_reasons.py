"""#312 eigene Abwesenheitsgründe: CRUD + Buchungs-Integration + Maskierung."""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType, AbsenceReason
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

ADMIN_BASE = "/api/admin/absence-reasons"
READ_BASE = "/api/absence-reasons"
MON = date(2025, 3, 10)


def _app() -> FastAPI:
    from app.routers import absence_reasons, absences
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    a = FastAPI()
    limiter.enabled = False
    a.state.limiter = limiter
    a.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    a.include_router(absence_reasons.admin_router)
    a.include_router(absence_reasons.read_router)
    a.include_router(absences.router)
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
    db.add(t); db.commit(); return t


def _user(db, username, role=UserRole.EMPLOYEE):
    u = User(username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("test123"),
             first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=30,
             work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(u); db.commit(); db.refresh(u); return u


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "admin1", role=UserRole.ADMIN)


@pytest.fixture
def employee(db, default_tenant):
    return _user(db, "emp1")


def _client(db, user, admin_user):
    def od():
        yield db
    app.dependency_overrides[get_db] = od
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


@pytest.fixture
def admin_client(db, admin):
    c = _client(db, admin, admin)
    yield c
    app.dependency_overrides.clear()


def _mk(client, name="Schule", behavior="worked", color="#3366cc"):
    r = client.post(ADMIN_BASE, json={"name": name, "base_behavior": behavior, "color": color})
    assert r.status_code == 201, r.text
    return r.json()


class TestReasonCrud:
    def test_create_and_list(self, default_tenant, admin_client):
        body = _mk(admin_client)
        assert body["name"] == "Schule" and body["base_behavior"] == "worked" and body["is_active"] is True
        lst = admin_client.get(ADMIN_BASE).json()
        assert any(r["id"] == body["id"] for r in lst)

    def test_duplicate_name_409(self, default_tenant, admin_client):
        _mk(admin_client, name="Reha")
        r = admin_client.post(ADMIN_BASE, json={"name": "Reha", "base_behavior": "paid_free"})
        assert r.status_code == 409

    def test_invalid_behavior_422(self, default_tenant, admin_client):
        r = admin_client.post(ADMIN_BASE, json={"name": "X", "base_behavior": "nonsense"})
        assert r.status_code == 422

    def test_invalid_color_400(self, default_tenant, admin_client):
        r = admin_client.post(ADMIN_BASE, json={"name": "X", "base_behavior": "worked", "color": "blau"})
        assert r.status_code == 400

    def test_rename_and_recolor(self, default_tenant, admin_client):
        rid = _mk(admin_client)["id"]
        r = admin_client.put(f"{ADMIN_BASE}/{rid}", json={"name": "Berufsschule", "color": "#112233"})
        assert r.status_code == 200 and r.json()["name"] == "Berufsschule" and r.json()["color"] == "#112233"

    def test_base_behavior_locked(self, default_tenant, admin_client):
        rid = _mk(admin_client, behavior="worked")["id"]
        # PUT may carry base_behavior but it must NOT change (v1 lock)
        r = admin_client.put(f"{ADMIN_BASE}/{rid}", json={"base_behavior": "paid_free"})
        assert r.status_code in (200, 400)
        assert admin_client.get(ADMIN_BASE).json()[0]["base_behavior"] == "worked"

    def test_deactivate_hides_from_employee_read(self, default_tenant, admin_client, employee, db):
        rid = _mk(admin_client)["id"]
        emp_client = _client(db, employee, employee)  # employee-authed, shared db
        # employee read sees the active reason
        assert any(r["id"] == rid for r in emp_client.get(READ_BASE).json())
        admin_client.put(f"{ADMIN_BASE}/{rid}", json={"is_active": False})
        assert all(r["id"] != rid for r in emp_client.get(READ_BASE).json())

    def test_delete_unused(self, default_tenant, admin_client):
        rid = _mk(admin_client)["id"]
        assert admin_client.delete(f"{ADMIN_BASE}/{rid}").status_code == 204

    def test_rename_to_existing_name_409(self, default_tenant, admin_client):
        # round-1 finding 4: renaming to a duplicate must 409, not 500
        _mk(admin_client, name="Schule")
        rid_b = _mk(admin_client, name="Reha")["id"]
        assert admin_client.put(f"{ADMIN_BASE}/{rid_b}", json={"name": "Schule"}).status_code == 409

    def test_delete_blocked_by_pending_cr(self, default_tenant, admin_client, employee, db):
        # round-1 finding 5: a reason referenced by a pending CR must not be deleted
        from app.models import ChangeRequest, ChangeRequestStatus
        rid = _mk(admin_client)["id"]
        db.add(ChangeRequest(
            user_id=employee.id, tenant_id=DEFAULT_TENANT_ID, request_type="create",
            entry_kind="absence", status=ChangeRequestStatus.PENDING, reason="Antrag",
            proposed_date=MON, proposed_absence_type="training", proposed_absence_hours=8.0,
            proposed_reason_id=uuid.UUID(rid),
        ))
        db.commit()
        assert admin_client.delete(f"{ADMIN_BASE}/{rid}").status_code == 409

    def test_delete_in_use_409(self, default_tenant, admin_client, employee):
        rid = _mk(admin_client)["id"]
        admin_client.post("/api/absences/", json={
            "user_id": str(employee.id), "date": MON.isoformat(), "type": "vacation",
            "hours": 8, "reason_id": rid,
        })
        assert admin_client.delete(f"{ADMIN_BASE}/{rid}").status_code == 409

    def test_clear_color_with_empty_string(self, default_tenant, admin_client):
        rid = _mk(admin_client, color="#abcdef")["id"]
        r = admin_client.put(f"{ADMIN_BASE}/{rid}", json={"color": ""})
        assert r.status_code == 200 and r.json()["color"] is None


class TestBookingSecurity:
    def test_inactive_reason_rejected(self, default_tenant, admin_client, employee):
        rid = _mk(admin_client)["id"]
        admin_client.put(f"{ADMIN_BASE}/{rid}", json={"is_active": False})
        r = admin_client.post("/api/absences/", json={
            "user_id": str(employee.id), "date": MON.isoformat(), "type": "vacation",
            "hours": 8, "reason_id": rid,
        })
        assert r.status_code in (400, 404)

    def test_cross_tenant_reason_rejected(self, default_tenant, admin_client, employee, db):
        # a reason belonging to ANOTHER tenant must not be bookable here (F-026/IDOR)
        from app.models.tenant import Tenant
        other_tid = uuid.UUID("00000000-0000-0000-0000-0000000000ff")
        db.add(Tenant(id=other_tid, name="Other", slug="other", is_active=True, mode="single"))
        foreign = AbsenceReason(tenant_id=other_tid, name="Fremd", base_behavior="worked", is_active=True)
        db.add(foreign); db.commit(); db.refresh(foreign)
        r = admin_client.post("/api/absences/", json={
            "user_id": str(employee.id), "date": MON.isoformat(), "type": "vacation",
            "hours": 8, "reason_id": str(foreign.id),
        })
        assert r.status_code in (400, 404)
        # and it is invisible to this tenant's admin list
        assert all(x["id"] != str(foreign.id) for x in admin_client.get(ADMIN_BASE).json())


class TestBookingIntegration:
    def test_reason_sets_mapped_type(self, default_tenant, admin_client, employee, db):
        rid = _mk(admin_client, behavior="worked")["id"]  # → TRAINING
        r = admin_client.post("/api/absences/", json={
            "user_id": str(employee.id), "date": MON.isoformat(), "type": "vacation",
            "hours": 8, "reason_id": rid,
        })
        assert r.status_code == 201, r.text
        a = db.query(Absence).filter(Absence.user_id == employee.id, Absence.date == MON).first()
        assert a is not None and a.type == AbsenceType.TRAINING and str(a.reason_id) == rid

    def test_paid_free_maps_to_paid_leave(self, default_tenant, admin_client, employee, db):
        rid = _mk(admin_client, name="Sonderfrei", behavior="paid_free")["id"]
        admin_client.post("/api/absences/", json={
            "user_id": str(employee.id), "date": MON.isoformat(), "type": "other",
            "hours": 8, "reason_id": rid,
        })
        a = db.query(Absence).filter(Absence.user_id == employee.id, Absence.date == MON).first()
        assert a.type == AbsenceType.PAID_LEAVE

    def test_unknown_reason_rejected(self, default_tenant, admin_client, employee):
        r = admin_client.post("/api/absences/", json={
            "user_id": str(employee.id), "date": MON.isoformat(), "type": "vacation",
            "hours": 8, "reason_id": str(uuid.uuid4()),
        })
        assert r.status_code in (400, 404)


class TestMasking:
    def test_custom_reason_masked_for_colleague_shown_to_admin(self, default_tenant, admin_client, employee, db):
        rid = _mk(admin_client, name="Reha", behavior="paid_free")["id"]
        admin_client.post("/api/absences/", json={
            "user_id": str(employee.id), "date": MON.isoformat(), "type": "other",
            "hours": 8, "reason_id": rid,
        })
        # the admin sees the real reason label (do this BEFORE switching the
        # shared get_current_user override to the viewer below)
        mine_admin = [e for e in admin_client.get("/api/absences/calendar?month=2025-03").json()
                      if e["user_first_name"] == "emp1"]
        assert mine_admin and any(e["type"] == "Reha" for e in mine_admin)
        # a non-admin colleague must see the absence only as "absent" (DSGVO)
        viewer = _user(db, "viewer")
        vclient = _client(db, viewer, viewer)
        mine = [e for e in vclient.get("/api/absences/calendar?month=2025-03").json()
                if e["user_first_name"] == "emp1"]
        assert mine and all(e["type"] == "absent" for e in mine)
