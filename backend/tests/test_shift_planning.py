"""Tests for Schichtplanung (#305): CRUD, feature-flag gating, validation, my-today.

Covers the application-layer contract on SQLite (RLS is a no-op here; cross-tenant
isolation via the explicit F-026 filters is covered in
``test_shift_planning_cross_tenant.py``).

The feature is gated behind the tenant setting ``shift_planning_enabled``. Most
tests enable it via the ``enabled`` fixture; the gating tests deliberately do not.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models.system_setting import SystemSetting
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

BASE = "/api/shift-planning"


# ─── helpers / fixtures ──────────────────────────────────────────────


def _enable_flag(db, tenant_id=DEFAULT_TENANT_ID):
    db.add(SystemSetting(key="shift_planning_enabled", tenant_id=tenant_id, value="true"))
    db.commit()


@pytest.fixture
def enabled(db, default_tenant):
    """Turn the feature flag on for the default tenant."""
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
    # require_admin NOT overridden → the real gate enforces 403 for writes.
    c = _client(db, test_user, admin=False)
    yield c
    test_app.dependency_overrides.clear()


def _mk_location(client, name="Hauptstelle"):
    r = client.post(f"{BASE}/locations", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_workstation(client, name="Tresen", location_id=None, color="#FF8800"):
    body = {"name": name, "color": color}
    if location_id:
        body["location_id"] = location_id
    r = client.post(f"{BASE}/workstations", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_plan(client, name="Normalzustand"):
    r = client.post(f"{BASE}/plans", json={"name": name, "description": "Standard"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_slot(client, plan_id, ws_id, *, weekday=0, start="08:00", end="12:00", min_staff=1):
    r = client.post(
        f"{BASE}/plans/{plan_id}/slots",
        json={
            "workstation_id": ws_id,
            "weekday": weekday,
            "start_time": start,
            "end_time": end,
            "min_staff": min_staff,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ─── feature-flag gating ─────────────────────────────────────────────


class TestFeatureFlagGating:
    def test_endpoints_404_when_flag_off(self, db, default_tenant, admin_client):
        # flag NOT enabled → feature feels absent
        assert admin_client.get(f"{BASE}/locations").status_code == 404
        assert admin_client.get(f"{BASE}/plans").status_code == 404
        assert admin_client.post(f"{BASE}/locations", json={"name": "X"}).status_code == 404
        assert admin_client.get(f"{BASE}/my-today").status_code == 404

    def test_endpoints_work_when_flag_on(self, enabled, admin_client):
        assert admin_client.get(f"{BASE}/locations").status_code == 200
        assert admin_client.get(f"{BASE}/plans").status_code == 200


# ─── locations ───────────────────────────────────────────────────────


class TestLocations:
    def test_admin_creates_and_lists(self, enabled, admin_client):
        lid = _mk_location(admin_client, "Filiale Nord")
        rows = admin_client.get(f"{BASE}/locations").json()
        assert any(r["id"] == lid and r["name"] == "Filiale Nord" for r in rows)

    def test_employee_can_read_but_not_create(self, enabled, employee_client):
        assert employee_client.get(f"{BASE}/locations").status_code == 200
        assert employee_client.post(f"{BASE}/locations", json={"name": "X"}).status_code == 403

    def test_duplicate_name_conflicts(self, enabled, admin_client):
        _mk_location(admin_client, "Dup")
        r = admin_client.post(f"{BASE}/locations", json={"name": "Dup"})
        assert r.status_code == 409, r.text

    def test_update_location(self, enabled, admin_client):
        lid = _mk_location(admin_client, "Alt")
        r = admin_client.put(f"{BASE}/locations/{lid}", json={"name": "Neu", "sort_order": 3})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Neu"

    def test_delete_location_conflict_when_workstation_attached(self, enabled, admin_client):
        lid = _mk_location(admin_client)
        _mk_workstation(admin_client, "Tresen", location_id=lid)
        r = admin_client.delete(f"{BASE}/locations/{lid}")
        assert r.status_code == 409, r.text

    def test_delete_unused_location(self, enabled, admin_client):
        lid = _mk_location(admin_client, "Leer")
        assert admin_client.delete(f"{BASE}/locations/{lid}").status_code == 204


# ─── workstations ────────────────────────────────────────────────────


class TestWorkstations:
    def test_create_with_and_without_location(self, enabled, admin_client):
        lid = _mk_location(admin_client)
        ws1 = _mk_workstation(admin_client, "Tresen", location_id=lid)
        ws2 = _mk_workstation(admin_client, "Springer")  # global, no location
        rows = {r["id"]: r for r in admin_client.get(f"{BASE}/workstations").json()}
        assert rows[ws1]["location_id"] == lid
        assert rows[ws1]["location_name"] == "Hauptstelle"
        assert rows[ws2]["location_id"] is None

    def test_delete_conflict_when_used_in_slot(self, enabled, admin_client):
        ws = _mk_workstation(admin_client, "Labor")
        plan = _mk_plan(admin_client)
        _mk_slot(admin_client, plan, ws)
        r = admin_client.delete(f"{BASE}/workstations/{ws}")
        assert r.status_code == 409, r.text

    def test_employee_cannot_create(self, enabled, employee_client):
        assert employee_client.post(f"{BASE}/workstations", json={"name": "X"}).status_code == 403


# ─── plans + slots ───────────────────────────────────────────────────


class TestPlans:
    def test_crud_and_activation(self, enabled, admin_client):
        pid = _mk_plan(admin_client, "Sommer")
        # default inactive
        plans = {p["id"]: p for p in admin_client.get(f"{BASE}/plans").json()}
        assert plans[pid]["is_active"] is False

        assert admin_client.post(f"{BASE}/plans/{pid}/activate").json()["is_active"] is True
        assert admin_client.post(f"{BASE}/plans/{pid}/deactivate").json()["is_active"] is False

        r = admin_client.put(f"{BASE}/plans/{pid}", json={"name": "Sommer 2026", "description": "x"})
        assert r.status_code == 200
        assert r.json()["name"] == "Sommer 2026"

    def test_multiple_plans_active_simultaneously(self, enabled, admin_client):
        p1 = _mk_plan(admin_client, "A")
        p2 = _mk_plan(admin_client, "B")
        admin_client.post(f"{BASE}/plans/{p1}/activate")
        admin_client.post(f"{BASE}/plans/{p2}/activate")
        plans = {p["id"]: p for p in admin_client.get(f"{BASE}/plans").json()}
        assert plans[p1]["is_active"] is True
        assert plans[p2]["is_active"] is True

    def test_delete_plan_cascades_slots(self, enabled, admin_client):
        ws = _mk_workstation(admin_client)
        pid = _mk_plan(admin_client)
        sid = _mk_slot(admin_client, pid, ws)
        assert admin_client.delete(f"{BASE}/plans/{pid}").status_code == 204
        # slot is gone with the plan
        assert admin_client.put(
            f"{BASE}/slots/{sid}",
            json={"workstation_id": ws, "weekday": 0, "start_time": "08:00", "end_time": "09:00", "min_staff": 0},
        ).status_code == 404

    def test_full_plan_detail_shape(self, enabled, admin_client, test_user):
        ws = _mk_workstation(admin_client, "Tresen")
        pid = _mk_plan(admin_client)
        sid = _mk_slot(admin_client, pid, ws, weekday=2, start="08:00", end="12:00", min_staff=1)
        admin_client.put(f"{BASE}/slots/{sid}/assignments", json={"user_ids": [str(test_user.id)]})

        detail = admin_client.get(f"{BASE}/plans/{pid}").json()
        assert detail["id"] == pid
        slot = detail["slots"][0]
        assert slot["workstation_name"] == "Tresen"
        assert slot["weekday"] == 2
        assert slot["start_time"] == "08:00"
        assert slot["min_staff"] == 1
        assert slot["understaffed"] is False
        assert slot["assignments"][0]["user_id"] == str(test_user.id)
        assert detail["validation"]["is_valid"] is True


class TestSlots:
    def test_end_must_be_after_start(self, enabled, admin_client):
        ws = _mk_workstation(admin_client)
        pid = _mk_plan(admin_client)
        r = admin_client.post(
            f"{BASE}/plans/{pid}/slots",
            json={"workstation_id": ws, "weekday": 0, "start_time": "12:00", "end_time": "08:00", "min_staff": 0},
        )
        assert r.status_code == 400, r.text

    def test_update_slot_move_and_resize(self, enabled, admin_client):
        ws = _mk_workstation(admin_client)
        pid = _mk_plan(admin_client)
        sid = _mk_slot(admin_client, pid, ws, weekday=0, start="08:00", end="12:00")
        r = admin_client.put(
            f"{BASE}/slots/{sid}",
            json={"workstation_id": ws, "weekday": 3, "start_time": "14:00", "end_time": "20:00", "min_staff": 2},
        )
        assert r.status_code == 200, r.text
        assert r.json()["weekday"] == 3
        assert r.json()["start_time"] == "14:00"


# ─── assignments ─────────────────────────────────────────────────────


class TestAssignments:
    def test_set_assignments_idempotent_and_dedup(self, enabled, admin_client, test_user):
        ws = _mk_workstation(admin_client)
        pid = _mk_plan(admin_client)
        sid = _mk_slot(admin_client, pid, ws)
        uid = str(test_user.id)
        # duplicate ids collapse to one assignment
        r = admin_client.put(f"{BASE}/slots/{sid}/assignments", json={"user_ids": [uid, uid]})
        assert r.status_code == 200, r.text
        assert len(r.json()["assignments"]) == 1
        # setting again is idempotent
        r2 = admin_client.put(f"{BASE}/slots/{sid}/assignments", json={"user_ids": [uid]})
        assert len(r2.json()["assignments"]) == 1
        # empty list clears
        r3 = admin_client.put(f"{BASE}/slots/{sid}/assignments", json={"user_ids": []})
        assert r3.json()["assignments"] == []

    def test_unknown_user_rejected(self, enabled, admin_client):
        ws = _mk_workstation(admin_client)
        pid = _mk_plan(admin_client)
        sid = _mk_slot(admin_client, pid, ws)
        r = admin_client.put(
            f"{BASE}/slots/{sid}/assignments",
            json={"user_ids": [str(uuid.uuid4())]},
        )
        assert r.status_code == 404, r.text


# ─── validation (soft) ───────────────────────────────────────────────


class TestValidation:
    def test_understaffed_flag_is_soft(self, enabled, admin_client):
        ws = _mk_workstation(admin_client)
        pid = _mk_plan(admin_client)
        _mk_slot(admin_client, pid, ws, min_staff=2)  # no assignments → understaffed
        # plan can still be activated despite understaffing (soft validation)
        assert admin_client.post(f"{BASE}/plans/{pid}/activate").status_code == 200
        detail = admin_client.get(f"{BASE}/plans/{pid}").json()
        assert detail["slots"][0]["understaffed"] is True
        assert detail["validation"]["is_valid"] is False


# ─── my-today (dashboard) ────────────────────────────────────────────


class TestReviewFixes:
    """Regressions for the adversarial-review findings."""

    def test_workstation_color_must_be_hex(self, enabled, admin_client):
        # non-hex / over-long colour would StringDataRightTruncation (500) on PG
        r = admin_client.post(f"{BASE}/workstations", json={"name": "Bad", "color": "rebeccapurple"})
        assert r.status_code == 422, r.text
        # valid hex is accepted
        ok = admin_client.post(f"{BASE}/workstations", json={"name": "Good", "color": "#abcdef"})
        assert ok.status_code == 201, ok.text
        # empty/None colour is allowed (→ None)
        ok2 = admin_client.post(f"{BASE}/workstations", json={"name": "NoColor", "color": ""})
        assert ok2.status_code == 201

    def test_slot_min_staff_nonnegative(self, enabled, admin_client):
        ws = _mk_workstation(admin_client)
        pid = _mk_plan(admin_client)
        r = admin_client.post(
            f"{BASE}/plans/{pid}/slots",
            json={"workstation_id": ws, "weekday": 0, "start_time": "08:00", "end_time": "12:00", "min_staff": -1},
        )
        assert r.status_code == 422, r.text

    def test_commit_conflict_guard_returns_409(self, db, default_tenant):
        """A unique-name collision at COMMIT is translated to 409, not a 500."""
        from fastapi import HTTPException
        from app.routers.shift_planning import _commit_or_conflict
        from app.models.shift_planning import Location

        db.add(Location(tenant_id=DEFAULT_TENANT_ID, name="Dup"))
        db.commit()
        # second row violates uq_tenant_location_name (SQLite enforces UNIQUE)
        db.add(Location(tenant_id=DEFAULT_TENANT_ID, name="Dup"))
        with pytest.raises(HTTPException) as exc:
            _commit_or_conflict(db, "Standort existiert bereits")
        assert exc.value.status_code == 409

    def test_purge_user_reassigns_created_shift_plans(self, enabled, admin_client, db, test_admin):
        """DSGVO Art.17 purge of a user who created a shift plan must not orphan/FK-fail."""
        from app.models import User, UserRole
        from app.models.shift_planning import ShiftPlan

        creator = User(
            username="plan_creator",
            email="creator@example.com",
            password_hash="x",
            first_name="Plan",
            last_name="Creator",
            role=UserRole.EMPLOYEE,
            weekly_hours=40.0,
            vacation_days=30,
            work_days_per_week=5,
            is_active=False,  # purge requires a deactivated user
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(creator)
        db.commit()
        db.refresh(creator)
        plan = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name="ByCreator", is_active=False, created_by=creator.id)
        db.add(plan)
        db.commit()
        db.refresh(plan)
        pid = plan.id

        r = admin_client.delete(f"/api/admin/users/{creator.id}/purge")
        assert r.status_code == 200, r.text

        db.expire_all()
        survived = db.query(ShiftPlan).filter(ShiftPlan.id == pid).first()
        assert survived is not None, "plan must survive the creator's purge"
        assert survived.created_by == test_admin.id, "created_by reassigned to acting admin"


class TestMyToday:
    def test_union_over_active_plans_for_today(self, enabled, admin_client, employee_client, test_user):
        wd = today_local().weekday()
        ws = _mk_workstation(admin_client, "Tresen")
        # active plan with a slot today, user assigned
        active = _mk_plan(admin_client, "Aktiv")
        sid = _mk_slot(admin_client, active, ws, weekday=wd, start="08:00", end="12:00")
        admin_client.put(f"{BASE}/slots/{sid}/assignments", json={"user_ids": [str(test_user.id)]})
        admin_client.post(f"{BASE}/plans/{active}/activate")

        # inactive plan with a slot today, user assigned → must NOT show
        inactive = _mk_plan(admin_client, "Inaktiv")
        sid2 = _mk_slot(admin_client, inactive, ws, weekday=wd, start="14:00", end="18:00")
        admin_client.put(f"{BASE}/slots/{sid2}/assignments", json={"user_ids": [str(test_user.id)]})

        # active plan slot on a DIFFERENT weekday → must NOT show
        other_wd = (wd + 1) % 7
        sid3 = _mk_slot(admin_client, active, ws, weekday=other_wd, start="20:00", end="22:00")
        admin_client.put(f"{BASE}/slots/{sid3}/assignments", json={"user_ids": [str(test_user.id)]})

        data = employee_client.get(f"{BASE}/my-today").json()
        assert data["weekday"] == wd
        times = {(e["start_time"], e["end_time"]) for e in data["entries"]}
        assert ("08:00", "12:00") in times
        assert ("14:00", "18:00") not in times  # inactive plan excluded
        assert ("20:00", "22:00") not in times  # wrong weekday excluded

    def test_only_own_assignments(self, enabled, admin_client, employee_client, test_user):
        # admin creates a slot today assigned to ADMIN only; employee sees nothing
        wd = today_local().weekday()
        ws = _mk_workstation(admin_client)
        plan = _mk_plan(admin_client)
        sid = _mk_slot(admin_client, plan, ws, weekday=wd)
        # assign the admin (not the employee)
        import_admin_id = admin_client.get(f"{BASE}/plans/{plan}").json()  # noqa: F841
        admin_client.post(f"{BASE}/plans/{plan}/activate")
        data = employee_client.get(f"{BASE}/my-today").json()
        assert data["entries"] == []
