"""Tests for the Einweisungs-/Skill-Matrix (#305 M2d): workstation qualifications.

CRUD + matrix shape + my-qualifications + the per-assignment `qualified` flag and
`unqualified_slot_ids` in plan detail + flag-gating. Cross-tenant isolation is in
test_qualifications_cross_tenant.py.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

BASE = "/api/shift-planning"


def _enable_flag(db, tenant_id=DEFAULT_TENANT_ID):
    db.add(SystemSetting(key="shift_planning_enabled", tenant_id=tenant_id, value="true"))
    db.commit()


@pytest.fixture
def enabled(db, default_tenant):
    _enable_flag(db)


def _client(db, user, *, admin=False):
    def _override_db():
        yield db

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    if admin:
        test_app.dependency_overrides[require_admin] = lambda: user
    return TestClient(test_app)


@pytest.fixture
def admin_client(db, test_admin):
    c = _client(db, test_admin, admin=True)
    yield c
    test_app.dependency_overrides.clear()


@pytest.fixture
def employee_client(db, test_user):
    c = _client(db, test_user, admin=False)
    yield c
    test_app.dependency_overrides.clear()


def _mk_workstation(client, name="Tresen"):
    r = client.post(f"{BASE}/workstations", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _set_quals(client, user_id, ws_ids):
    r = client.put(f"{BASE}/qualifications/{user_id}", json={"workstation_ids": ws_ids})
    assert r.status_code == 200, r.text
    return r.json()


def _mk_plan_slot_assign(admin_client, ws_id, user_id):
    pid = admin_client.post(f"{BASE}/plans", json={"name": f"P-{uuid.uuid4().hex[:6]}"}).json()["id"]
    sid = admin_client.post(
        f"{BASE}/plans/{pid}/slots",
        json={"workstation_id": ws_id, "weekday": 0, "start_time": "08:00", "end_time": "12:00", "min_staff": 1},
    ).json()["id"]
    admin_client.put(f"{BASE}/slots/{sid}/assignments", json={"user_ids": [user_id]})
    return pid, sid


# ─── gating ──────────────────────────────────────────────────────────


def test_qualifications_404_when_flag_off(db, default_tenant, admin_client):
    assert admin_client.get(f"{BASE}/qualifications").status_code == 404
    assert admin_client.get(f"{BASE}/me/qualifications").status_code == 404


# ─── CRUD + matrix ───────────────────────────────────────────────────


class TestQualificationsCrud:
    def test_set_and_matrix(self, enabled, admin_client, test_user):
        ws1 = _mk_workstation(admin_client, "Tresen")
        ws2 = _mk_workstation(admin_client, "Labor")
        _set_quals(admin_client, str(test_user.id), [ws1])

        m = admin_client.get(f"{BASE}/qualifications").json()
        assert {w["id"] for w in m["workstations"]} >= {ws1, ws2}
        assert any(u["id"] == str(test_user.id) for u in m["users"])
        pairs = {(q["user_id"], q["workstation_id"]) for q in m["qualifications"]}
        assert (str(test_user.id), ws1) in pairs
        assert (str(test_user.id), ws2) not in pairs

    def test_put_replaces_and_dedups(self, enabled, admin_client, test_user):
        ws1 = _mk_workstation(admin_client, "A")
        ws2 = _mk_workstation(admin_client, "B")
        r = _set_quals(admin_client, str(test_user.id), [ws1, ws1, ws2])  # dup collapses
        assert sorted(r["workstation_ids"]) == sorted([ws1, ws2])
        # replace with just ws2
        r2 = _set_quals(admin_client, str(test_user.id), [ws2])
        assert r2["workstation_ids"] == [ws2]
        # empty clears
        r3 = _set_quals(admin_client, str(test_user.id), [])
        assert r3["workstation_ids"] == []

    def test_put_unknown_workstation_404(self, enabled, admin_client, test_user):
        r = admin_client.put(
            f"{BASE}/qualifications/{test_user.id}", json={"workstation_ids": [str(uuid.uuid4())]}
        )
        assert r.status_code == 404, r.text

    def test_put_unknown_user_404(self, enabled, admin_client):
        ws = _mk_workstation(admin_client)
        r = admin_client.put(f"{BASE}/qualifications/{uuid.uuid4()}", json={"workstation_ids": [ws]})
        assert r.status_code == 404, r.text

    def test_employee_cannot_set(self, enabled, employee_client, test_user):
        r = employee_client.put(f"{BASE}/qualifications/{test_user.id}", json={"workstation_ids": []})
        assert r.status_code == 403


# ─── my-qualifications (employee self view) ──────────────────────────


class TestMyQualifications:
    def test_employee_sees_own(self, enabled, admin_client, employee_client, test_user):
        ws1 = _mk_workstation(admin_client, "Tresen")
        _mk_workstation(admin_client, "Labor")
        _set_quals(admin_client, str(test_user.id), [ws1])
        data = employee_client.get(f"{BASE}/me/qualifications").json()
        names = {w["name"] for w in data["workstations"]}
        assert names == {"Tresen"}


# ─── qualified flag in slot detail ───────────────────────────────────


class TestQualifiedFlag:
    def test_assignment_qualified_flag_and_unqualified_slots(self, enabled, admin_client, test_user):
        ws = _mk_workstation(admin_client, "Labor")
        pid, sid = _mk_plan_slot_assign(admin_client, ws, str(test_user.id))

        # not qualified yet → qualified=false + slot flagged unqualified
        detail = admin_client.get(f"{BASE}/plans/{pid}").json()
        slot = detail["slots"][0]
        assert slot["assignments"][0]["qualified"] is False
        assert sid in detail["validation"]["unqualified_slot_ids"]

        # qualify the user → qualified=true + slot no longer unqualified
        _set_quals(admin_client, str(test_user.id), [ws])
        detail2 = admin_client.get(f"{BASE}/plans/{pid}").json()
        assert detail2["slots"][0]["assignments"][0]["qualified"] is True
        assert sid not in detail2["validation"]["unqualified_slot_ids"]

    def test_employee_does_not_see_qualification_gaps(self, enabled, employee_client, db, default_tenant, test_user):
        """Per-person 'not trained' competency data is admin-only (privacy).

        (The admin-DOES-see-it case is covered by the test above; here we seed
        directly so only the employee client's get_current_user is active.)
        """
        from datetime import time
        from app.models.shift_planning import Workstation, ShiftPlan, ShiftSlot, ShiftAssignment

        ws = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Labor")
        db.add(ws)
        db.flush()
        plan = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name="P", is_active=True, created_by=test_user.id)
        db.add(plan)
        db.flush()
        slot = ShiftSlot(
            tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan.id, workstation_id=ws.id,
            weekday=0, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
        )
        db.add(slot)
        db.flush()
        db.add(ShiftAssignment(tenant_id=DEFAULT_TENANT_ID, shift_slot_id=slot.id, user_id=test_user.id))
        db.commit()

        e = employee_client.get(f"{BASE}/plans/{plan.id}").json()
        assert "qualified" not in e["slots"][0]["assignments"][0]
        assert e["slots"][0]["unqualified"] is False
        assert e["validation"]["unqualified_slot_ids"] == []
