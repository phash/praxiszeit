"""Tests for #371: konfigurierbare Wochentage im Schichtplaner.

The tenant setting ``shift_planning_weekdays`` (CSV of 0=Mo … 6=So) drives the
whole planning surface: week-view columns (frontend), slot creation and the
auto-generator all respect it. Default is Mo–Fr.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models.system_setting import SystemSetting
from app.services import shift_planning_service as sps
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

BASE = "/api/shift-planning"


# ─── service helper: get_planning_weekdays ───────────────────────────


class TestGetPlanningWeekdays:
    def test_default_is_mon_to_fri_when_unset(self, db, default_tenant):
        assert sps.get_planning_weekdays(db, DEFAULT_TENANT_ID) == [0, 1, 2, 3, 4]

    def test_reads_configured_value(self, db, default_tenant):
        db.add(SystemSetting(key="shift_planning_weekdays", tenant_id=DEFAULT_TENANT_ID, value="0,2,4"))
        db.commit()
        assert sps.get_planning_weekdays(db, DEFAULT_TENANT_ID) == [0, 2, 4]

    def test_normalises_unsorted_and_deduped(self, db, default_tenant):
        db.add(SystemSetting(key="shift_planning_weekdays", tenant_id=DEFAULT_TENANT_ID, value="4,0,0,2"))
        db.commit()
        assert sps.get_planning_weekdays(db, DEFAULT_TENANT_ID) == [0, 2, 4]

    def test_falls_back_to_default_on_garbage(self, db, default_tenant):
        db.add(SystemSetting(key="shift_planning_weekdays", tenant_id=DEFAULT_TENANT_ID, value="nonsense"))
        db.commit()
        assert sps.get_planning_weekdays(db, DEFAULT_TENANT_ID) == [0, 1, 2, 3, 4]

    def test_falls_back_to_default_on_empty(self, db, default_tenant):
        db.add(SystemSetting(key="shift_planning_weekdays", tenant_id=DEFAULT_TENANT_ID, value=""))
        db.commit()
        assert sps.get_planning_weekdays(db, DEFAULT_TENANT_ID) == [0, 1, 2, 3, 4]

    def test_is_weekday_enabled(self, db, default_tenant):
        db.add(SystemSetting(key="shift_planning_weekdays", tenant_id=DEFAULT_TENANT_ID, value="0,1,2,3,4"))
        db.commit()
        assert sps.is_weekday_enabled(db, DEFAULT_TENANT_ID, 4) is True
        assert sps.is_weekday_enabled(db, DEFAULT_TENANT_ID, 5) is False

    def test_weekdays_are_tenant_scoped(self, db, default_tenant):
        # each tenant has its own weekday config (get_setting filters by tenant_id)
        other_tid = uuid.uuid4()
        db.add(SystemSetting(key="shift_planning_weekdays", tenant_id=DEFAULT_TENANT_ID, value="0,1,2,3,4"))
        db.add(SystemSetting(key="shift_planning_weekdays", tenant_id=other_tid, value="5,6"))
        db.commit()
        assert sps.get_planning_weekdays(db, DEFAULT_TENANT_ID) == [0, 1, 2, 3, 4]
        assert sps.get_planning_weekdays(db, other_tid) == [5, 6]


# ─── helpers / fixtures ──────────────────────────────────────────────


def _admin_client(db, user):
    def _override_db():
        yield db

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[require_admin] = lambda: user
    return TestClient(test_app)


@pytest.fixture
def admin_client(db, test_admin):
    c = _admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


# ─── setting validation via PUT /api/admin/settings/{key} ────────────


class TestWeekdaySettingValidation:
    KEY = "shift_planning_weekdays"

    def _put(self, client, value):
        return client.put(f"/api/admin/settings/{self.KEY}", json={"value": value})

    def test_valid_accepted(self, admin_client):
        r = self._put(admin_client, "0,1,2,3,4")
        assert r.status_code == 200, r.text

    def test_normalises_unsorted_and_deduped(self, admin_client, db):
        r = self._put(admin_client, "4,0,0,2")
        assert r.status_code == 200, r.text
        row = db.query(SystemSetting).filter(
            SystemSetting.key == self.KEY, SystemSetting.tenant_id == DEFAULT_TENANT_ID
        ).first()
        assert row.value == "0,2,4"

    def test_empty_rejected(self, admin_client):
        assert self._put(admin_client, "").status_code == 400

    def test_out_of_range_rejected(self, admin_client):
        assert self._put(admin_client, "7").status_code == 400
        assert self._put(admin_client, "-1").status_code == 400

    def test_non_numeric_rejected(self, admin_client):
        assert self._put(admin_client, "mo,di").status_code == 400


# ─── slot creation/update respects configured weekdays ───────────────


def _enable_shift_planning(db):
    db.add(SystemSetting(key="shift_planning_enabled", tenant_id=DEFAULT_TENANT_ID, value="true"))
    db.commit()


def _set_weekdays(db, csv):
    row = db.query(SystemSetting).filter(
        SystemSetting.key == "shift_planning_weekdays", SystemSetting.tenant_id == DEFAULT_TENANT_ID
    ).first()
    if row:
        row.value = csv
    else:
        db.add(SystemSetting(key="shift_planning_weekdays", tenant_id=DEFAULT_TENANT_ID, value=csv))
    db.commit()


def _mk_ws_and_plan(client):
    ws = client.post(f"{BASE}/workstations", json={"name": "Tresen", "color": "#FF8800"})
    assert ws.status_code == 201, ws.text
    plan = client.post(f"{BASE}/plans", json={"name": "Std", "description": ""})
    assert plan.status_code == 201, plan.text
    return ws.json()["id"], plan.json()["id"]


class TestSlotWeekdayEnforcement:
    def _slot_body(self, ws_id, weekday):
        return {"workstation_id": ws_id, "weekday": weekday, "start_time": "08:00", "end_time": "12:00", "min_staff": 1}

    def test_create_on_enabled_weekday_ok(self, admin_client, db):
        _enable_shift_planning(db)
        _set_weekdays(db, "0,1,2,3,4")
        ws_id, plan_id = _mk_ws_and_plan(admin_client)
        r = admin_client.post(f"{BASE}/plans/{plan_id}/slots", json=self._slot_body(ws_id, 2))
        assert r.status_code == 201, r.text

    def test_create_on_disabled_weekday_400(self, admin_client, db):
        _enable_shift_planning(db)
        _set_weekdays(db, "0,1,2,3,4")
        ws_id, plan_id = _mk_ws_and_plan(admin_client)
        r = admin_client.post(f"{BASE}/plans/{plan_id}/slots", json=self._slot_body(ws_id, 5))
        assert r.status_code == 400, r.text

    def test_update_to_disabled_weekday_400(self, admin_client, db):
        _enable_shift_planning(db)
        _set_weekdays(db, "0,1,2,3,4")
        ws_id, plan_id = _mk_ws_and_plan(admin_client)
        created = admin_client.post(f"{BASE}/plans/{plan_id}/slots", json=self._slot_body(ws_id, 0))
        slot_id = created.json()["id"]
        r = admin_client.put(f"{BASE}/slots/{slot_id}", json=self._slot_body(ws_id, 6))
        assert r.status_code == 400, r.text


# ─── get_my_today respects configured weekdays (#371, review #2) ──────


class TestMyTodayWeekday:
    def _setup_today_assignment(self, db, user):
        from app.models.shift_planning import ShiftPlan, ShiftSlot, ShiftAssignment, Workstation
        from app.services.timezone_service import today_local
        import uuid as _uuid
        from datetime import time
        weekday = today_local().weekday()
        ws = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Tresen")
        db.add(ws); db.commit(); db.refresh(ws)
        plan = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name="Aktiv", is_active=True, created_by=_uuid.uuid4())
        db.add(plan); db.commit(); db.refresh(plan)
        slot = ShiftSlot(
            tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan.id, workstation_id=ws.id,
            weekday=weekday, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
        )
        db.add(slot); db.commit(); db.refresh(slot)
        db.add(ShiftAssignment(tenant_id=DEFAULT_TENANT_ID, shift_slot_id=slot.id, user_id=user.id))
        db.commit()
        return weekday

    def test_assignment_shows_when_weekday_enabled(self, db, test_user):
        weekday = self._setup_today_assignment(db, test_user)
        _set_weekdays(db, ",".join(str(i) for i in range(7)))  # all enabled
        result = sps.get_my_today(db, test_user)
        assert len(result["entries"]) == 1

    def test_assignment_hidden_when_today_weekday_disabled(self, db, test_user):
        weekday = self._setup_today_assignment(db, test_user)
        # enable every weekday EXCEPT today's → the legacy assignment must vanish
        enabled = [i for i in range(7) if i != weekday] or [0]
        _set_weekdays(db, ",".join(str(i) for i in enabled))
        result = sps.get_my_today(db, test_user)
        assert result["entries"] == []


# ─── plan detail excludes disabled-weekday slots (#371, review #1) ────


class TestPlanDetailWeekday:
    def _mk_slot_direct(self, db, plan_id, ws_id, weekday, min_staff=2):
        from app.models.shift_planning import ShiftSlot
        from datetime import time
        s = ShiftSlot(
            tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan_id, workstation_id=ws_id,
            weekday=weekday, start_time=time(8, 0), end_time=time(12, 0), min_staff=min_staff,
        )
        db.add(s); db.commit(); db.refresh(s)
        return s

    def test_disabled_weekday_slot_not_in_detail_nor_validation(self, admin_client, db):
        _enable_shift_planning(db)
        _set_weekdays(db, "0,1,2,3,4")
        ws_id, plan_id = _mk_ws_and_plan(admin_client)
        import uuid as _uuid
        # legacy understaffed slot on Saturday (disabled), created directly (bypasses the 400 guard)
        sat = self._mk_slot_direct(db, _uuid.UUID(plan_id), _uuid.UUID(ws_id), weekday=5)
        detail = admin_client.get(f"{BASE}/plans/{plan_id}").json()
        slot_ids = {s["id"] for s in detail["slots"]}
        assert str(sat.id) not in slot_ids
        # the phantom understaffed slot must NOT make the plan invalid
        assert detail["validation"]["is_valid"] is True
        assert str(sat.id) not in detail["validation"]["understaffed_slot_ids"]

    def test_duplicate_preserves_disabled_weekday_slots(self, admin_client, db):
        # A duplicate is a faithful 1:1 copy: legacy slots on disabled weekdays are
        # preserved (no silent data loss). They stay filtered from detail/validation
        # (per the fix above) until the weekday is re-enabled.
        from app.models.shift_planning import ShiftSlot
        _enable_shift_planning(db)
        _set_weekdays(db, "0,1,2,3,4")
        ws_id, plan_id = _mk_ws_and_plan(admin_client)
        import uuid as _uuid
        self._mk_slot_direct(db, _uuid.UUID(plan_id), _uuid.UUID(ws_id), weekday=6, min_staff=1)
        dup = admin_client.post(f"{BASE}/plans/{plan_id}/duplicate", json={"name": "Kopie"})
        assert dup.status_code == 201, dup.text
        dup_id = dup.json()["id"]
        # the copied plan physically contains the Sunday slot in the DB
        copied = db.query(ShiftSlot).filter(
            ShiftSlot.shift_plan_id == _uuid.UUID(dup_id), ShiftSlot.weekday == 6
        ).count()
        assert copied == 1
