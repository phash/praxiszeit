"""Tests for #371: konfigurierbare Wochentage im Schichtplaner.

The tenant setting ``shift_planning_weekdays`` (CSV of 0=Mo … 6=So) drives the
whole planning surface: week-view columns (frontend), slot creation and the
auto-generator all respect it. Default is Mo–Fr.
"""
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
