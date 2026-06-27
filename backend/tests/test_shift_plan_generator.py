"""Tests for the Auto-Generierung (#305 M2): POST /plans/{id}/generate (greedy)."""
import uuid
from datetime import date, timedelta, time

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.system_setting import SystemSetting
from app.models.absence import Absence, AbsenceType
from app.models.shift_planning import (
    Workstation, ShiftPlan, ShiftSlot, ShiftAssignment, WorkstationQualification,
)
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

BASE = "/api/shift-planning"
# Monday of the target week (computed so it is always a Monday).
_d = date(2026, 7, 1)
TARGET_MONDAY = _d - timedelta(days=_d.weekday())


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


def _emp(db, username):
    u = User(
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("Test2025!Password"),
        first_name=username, last_name="E", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _ws(db, name):
    w = Workstation(tenant_id=DEFAULT_TENANT_ID, name=name)
    db.add(w); db.commit(); db.refresh(w)
    return w


def _plan(db, name="P"):
    p = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name=name, is_active=False, created_by=uuid.uuid4())
    db.add(p); db.commit(); db.refresh(p)
    return p


def _slot(db, plan, ws, *, weekday=0, start="08:00", end="12:00", min_staff=1):
    s = ShiftSlot(
        tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan.id, workstation_id=ws.id, weekday=weekday,
        start_time=time(*map(int, start.split(":"))), end_time=time(*map(int, end.split(":"))), min_staff=min_staff,
    )
    db.add(s); db.commit(); db.refresh(s)
    return s


def _qualify(db, user, ws):
    db.add(WorkstationQualification(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, workstation_id=ws.id))
    db.commit()


def _generate(client, plan_id, mode="replace"):
    r = client.post(f"{BASE}/plans/{plan_id}/generate", json={"target_monday": TARGET_MONDAY.isoformat(), "mode": mode})
    assert r.status_code == 200, r.text
    return r.json()


def _assigned_user_ids(detail, slot_id):
    for s in detail["slots"]:
        if s["id"] == slot_id:
            return {a["user_id"] for a in s["assignments"]}
    return set()


class TestGenerator:
    def test_only_qualified_assigned(self, enabled, admin_client, db):
        a, b = _emp(db, "qa"), _emp(db, "qb")
        ws = _ws(db, "Labor")
        _qualify(db, a, ws)  # only A qualified
        plan = _plan(db)
        s = _slot(db, plan, ws, weekday=0, min_staff=1)
        res = _generate(admin_client, str(plan.id))
        assigned = _assigned_user_ids(res["plan"], str(s.id))
        assert assigned == {str(a.id)}

    def test_absent_excluded(self, enabled, admin_client, db):
        a, b = _emp(db, "aa"), _emp(db, "ab")
        ws = _ws(db, "Tresen")
        _qualify(db, a, ws); _qualify(db, b, ws)
        # A is on full-day vacation on the slot's date (Monday of target week)
        db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=a.id, date=TARGET_MONDAY, type=AbsenceType.VACATION, hours=8))
        db.commit()
        plan = _plan(db)
        s = _slot(db, plan, ws, weekday=0, min_staff=1)
        res = _generate(admin_client, str(plan.id))
        assert _assigned_user_ids(res["plan"], str(s.id)) == {str(b.id)}

    def test_half_day_absence_does_not_block(self, enabled, admin_client, db):
        # round-2 finding: a HALF-day absence must not block the whole day.
        a = _emp(db, "ha")
        ws = _ws(db, "WSH")
        _qualify(db, a, ws)
        db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=a.id, date=TARGET_MONDAY,
                       type=AbsenceType.VACATION, hours=4, half_day=True))
        db.commit()
        plan = _plan(db)
        s = _slot(db, plan, ws, weekday=0, min_staff=1)
        res = _generate(admin_client, str(plan.id))
        assert _assigned_user_ids(res["plan"], str(s.id)) == {str(a.id)}

    def test_min_staff_and_balance(self, enabled, admin_client, db):
        a, b = _emp(db, "ba"), _emp(db, "bb")
        ws = _ws(db, "WS")
        _qualify(db, a, ws); _qualify(db, b, ws)
        plan = _plan(db)
        s1 = _slot(db, plan, ws, weekday=0, min_staff=1)
        s2 = _slot(db, plan, ws, weekday=1, min_staff=1)  # different weekday, no overlap
        res = _generate(admin_client, str(plan.id))
        # balance: each employee staffs exactly one of the two slots
        all_assigned = _assigned_user_ids(res["plan"], str(s1.id)) | _assigned_user_ids(res["plan"], str(s2.id))
        assert all_assigned == {str(a.id), str(b.id)}
        assert res["generation"]["unfilled_slot_ids"] == []

    def test_no_double_booking_overlap(self, enabled, admin_client, db):
        a = _emp(db, "ca")
        ws = _ws(db, "WS2")
        _qualify(db, a, ws)
        plan = _plan(db)
        s1 = _slot(db, plan, ws, weekday=0, start="08:00", end="12:00", min_staff=1)
        s2 = _slot(db, plan, ws, weekday=0, start="10:00", end="14:00", min_staff=1)  # overlaps s1
        res = _generate(admin_client, str(plan.id))
        a1 = _assigned_user_ids(res["plan"], str(s1.id))
        a2 = _assigned_user_ids(res["plan"], str(s2.id))
        # the single user can only be in one of the overlapping slots
        assert (a1 == {str(a.id)}) != (a2 == {str(a.id)})  # exactly one
        assert len(res["generation"]["unfilled_slot_ids"]) == 1

    def test_unfilled_when_no_candidate(self, enabled, admin_client, db):
        ws = _ws(db, "Niemand")  # nobody qualified
        plan = _plan(db)
        s = _slot(db, plan, ws, weekday=0, min_staff=1)
        res = _generate(admin_client, str(plan.id))
        assert str(s.id) in res["generation"]["unfilled_slot_ids"]
        assert _assigned_user_ids(res["plan"], str(s.id)) == set()

    def test_min_staff_zero_fills_one(self, enabled, admin_client, db):
        a = _emp(db, "za")
        ws = _ws(db, "WS0")
        _qualify(db, a, ws)
        plan = _plan(db)
        s = _slot(db, plan, ws, weekday=0, min_staff=0)  # max(1,0) = 1
        res = _generate(admin_client, str(plan.id))
        assert _assigned_user_ids(res["plan"], str(s.id)) == {str(a.id)}

    def test_replace_vs_fill_gaps(self, enabled, admin_client, db):
        a, b = _emp(db, "ra"), _emp(db, "rb")
        ws = _ws(db, "WSR")
        _qualify(db, a, ws); _qualify(db, b, ws)
        plan = _plan(db)
        s = _slot(db, plan, ws, weekday=0, min_staff=2)
        # pre-assign A manually
        db.add(ShiftAssignment(tenant_id=DEFAULT_TENANT_ID, shift_slot_id=s.id, user_id=a.id)); db.commit()
        # fill_gaps keeps A, adds B to reach min_staff 2
        res = _generate(admin_client, str(plan.id), mode="fill_gaps")
        assert _assigned_user_ids(res["plan"], str(s.id)) == {str(a.id), str(b.id)}


class TestGeneratorAuth:
    def test_employee_forbidden(self, enabled, employee_client, db):
        plan = _plan(db)
        r = employee_client.post(f"{BASE}/plans/{plan.id}/generate", json={"target_monday": TARGET_MONDAY.isoformat()})
        assert r.status_code == 403

    def test_flag_off_404(self, db, default_tenant, admin_client):
        plan = _plan(db)
        r = admin_client.post(f"{BASE}/plans/{plan.id}/generate", json={"target_monday": TARGET_MONDAY.isoformat()})
        assert r.status_code == 404
