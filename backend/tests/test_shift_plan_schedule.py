"""Tests for KW-/Ganzjahres-Planung (#305 M2): plan date windows + my-today resolution."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models.system_setting import SystemSetting
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

BASE = "/api/shift-planning"


@pytest.fixture
def enabled(db, default_tenant):
    db.add(SystemSetting(key="shift_planning_enabled", tenant_id=DEFAULT_TENANT_ID, value="true"))
    db.commit()


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


def _mk_plan(client, name="P"):
    return client.post(f"{BASE}/plans", json={"name": name}).json()["id"]


def _set_window(client, pid, frm, until, name="P"):
    r = client.put(f"{BASE}/plans/{pid}", json={
        "name": name, "description": None,
        "active_from_date": frm, "active_until_date": until,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _today_slot_for(admin_client, pid, user_id):
    ws = admin_client.post(f"{BASE}/workstations", json={"name": f"WS-{user_id[:4]}"}).json()["id"]
    wd = today_local().weekday()
    sid = admin_client.post(f"{BASE}/plans/{pid}/slots", json={
        "workstation_id": ws, "weekday": wd, "start_time": "08:00", "end_time": "12:00", "min_staff": 1,
    }).json()["id"]
    admin_client.put(f"{BASE}/slots/{sid}/assignments", json={"user_ids": [user_id]})
    return sid


class TestDateWindowApi:
    def test_put_sets_and_returns_window(self, enabled, admin_client):
        pid = _mk_plan(admin_client)
        r = _set_window(admin_client, pid, "2026-07-01", "2026-08-31")
        assert r["active_from_date"] == "2026-07-01"
        assert r["active_until_date"] == "2026-08-31"
        # surfaced in the list too
        plans = {p["id"]: p for p in admin_client.get(f"{BASE}/plans").json()}
        assert plans[pid]["active_from_date"] == "2026-07-01"

    def test_put_rejects_from_after_until(self, enabled, admin_client):
        pid = _mk_plan(admin_client)
        r = admin_client.put(f"{BASE}/plans/{pid}", json={
            "name": "P", "active_from_date": "2026-08-01", "active_until_date": "2026-07-01",
        })
        assert r.status_code == 400, r.text

    def test_clear_window(self, enabled, admin_client):
        pid = _mk_plan(admin_client)
        _set_window(admin_client, pid, "2026-07-01", "2026-08-31")
        r = _set_window(admin_client, pid, None, None)
        assert r["active_from_date"] is None and r["active_until_date"] is None


class TestMyTodayResolution:
    def test_window_covering_today_is_active(self, enabled, admin_client, employee_client, test_user):
        pid = _mk_plan(admin_client, "Windowed")
        _today_slot_for(admin_client, pid, str(test_user.id))
        today = today_local()
        _set_window(admin_client, pid,
                    (today - timedelta(days=2)).isoformat(),
                    (today + timedelta(days=2)).isoformat(), name="Windowed")
        # plan is NOT is_active, but the window covers today
        data = employee_client.get(f"{BASE}/my-today").json()
        assert len(data["entries"]) == 1

    def test_window_in_past_is_inactive(self, enabled, admin_client, employee_client, test_user):
        pid = _mk_plan(admin_client, "Past")
        _today_slot_for(admin_client, pid, str(test_user.id))
        today = today_local()
        _set_window(admin_client, pid,
                    (today - timedelta(days=30)).isoformat(),
                    (today - timedelta(days=10)).isoformat(), name="Past")
        assert employee_client.get(f"{BASE}/my-today").json()["entries"] == []

    def test_open_ended_windows(self, enabled, admin_client, employee_client, test_user):
        pid = _mk_plan(admin_client, "OpenEnd")
        _today_slot_for(admin_client, pid, str(test_user.id))
        today = today_local()
        # from <= today, until = NULL → active
        _set_window(admin_client, pid, (today - timedelta(days=1)).isoformat(), None, name="OpenEnd")
        assert len(employee_client.get(f"{BASE}/my-today").json()["entries"]) == 1
        # from = NULL, until >= today → active
        _set_window(admin_client, pid, None, (today + timedelta(days=1)).isoformat(), name="OpenEnd")
        assert len(employee_client.get(f"{BASE}/my-today").json()["entries"]) == 1

    def test_no_window_no_active_flag_is_inactive(self, enabled, admin_client, employee_client, test_user):
        pid = _mk_plan(admin_client, "Neither")
        _today_slot_for(admin_client, pid, str(test_user.id))
        # no is_active, no window → not active
        assert employee_client.get(f"{BASE}/my-today").json()["entries"] == []
