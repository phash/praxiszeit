"""Review 2026-11-11 (ui-07, ui-08, ui-09): Generator und Zuweisungen der Schichtplanung."""
import uuid
from datetime import date, time, timedelta

import pytest

from app.models import User
from app.models.absence import Absence, AbsenceType
from app.models.public_holiday import PublicHoliday
from app.models.shift_planning import ShiftAssignment, ShiftPlan
from app.services import calculation_service, holiday_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_shift_plan_generator import (  # noqa: F401  (Fixtures wiederverwendet)
    BASE, TARGET_MONDAY, admin_client, employee_client, enabled,
    _assigned_user_ids, _emp, _generate, _plan, _qualify, _slot, _ws,
)


def _active_plan(db, name):
    p = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name=name, is_active=True, created_by=uuid.uuid4())
    db.add(p); db.commit(); db.refresh(p)
    return p


class TestGeneratorReadsCalendar:
    def test_holiday_slot_is_skipped_and_reported(self, enabled, admin_client, db):
        a = _emp(db, "ha")
        ws = _ws(db, "Tresen")
        _qualify(db, a, ws)
        plan = _plan(db)
        thursday = _slot(db, plan, ws, weekday=3)
        monday = _slot(db, plan, ws, weekday=0)
        holiday_date = TARGET_MONDAY + timedelta(days=3)
        db.add(PublicHoliday(
            tenant_id=DEFAULT_TENANT_ID, date=holiday_date, name="Testfeiertag",
            year=holiday_date.year, source="admin", is_custom=True,
        ))
        db.commit()
        holiday_service.invalidate_holiday_cache()

        out = _generate(admin_client, plan.id)
        assert str(thursday.id) in out["generation"]["skipped_slot_ids"]
        assert str(thursday.id) not in out["generation"]["unfilled_slot_ids"]
        assert _assigned_user_ids(out["plan"], str(thursday.id)) == set()
        assert _assigned_user_ids(out["plan"], str(monday.id)) == {str(a.id)}

    def test_timed_absence_blocks_only_overlapping_slots(self, enabled, admin_client, db):
        a = _emp(db, "ta")
        ws = _ws(db, "Labor")
        _qualify(db, a, ws)
        plan = _plan(db)
        morning = _slot(db, plan, ws, weekday=1, start="08:00", end="12:00")
        afternoon = _slot(db, plan, ws, weekday=1, start="13:00", end="17:00")
        db.add(Absence(
            tenant_id=DEFAULT_TENANT_ID, user_id=a.id, date=TARGET_MONDAY + timedelta(days=1),
            type=AbsenceType.VACATION, hours=4,
            start_time=time(8, 0), end_time=time(12, 0),
        ))
        db.commit()
        out = _generate(admin_client, plan.id)
        assert _assigned_user_ids(out["plan"], str(morning.id)) == set()
        assert _assigned_user_ids(out["plan"], str(afternoon.id)) == {str(a.id)}

    def test_assignment_in_other_active_plan_blocks_overlap(self, enabled, admin_client, db):
        a, b = _emp(db, "xa"), _emp(db, "xb")
        ws = _ws(db, "Tresen")
        _qualify(db, a, ws); _qualify(db, b, ws)
        other = _active_plan(db, "Andere")
        other_slot = _slot(db, other, ws, weekday=2, start="08:00", end="12:00")
        db.add(ShiftAssignment(tenant_id=DEFAULT_TENANT_ID, shift_slot_id=other_slot.id, user_id=a.id))
        db.commit()
        plan = _plan(db)
        mine = _slot(db, plan, ws, weekday=2, start="10:00", end="14:00")
        out = _generate(admin_client, plan.id)
        assert _assigned_user_ids(out["plan"], str(mine.id)) == {str(b.id)}


class TestOvertimeLookup:
    def test_overtime_only_for_candidates_and_failure_does_not_break(self, enabled, admin_client, db, monkeypatch):
        qualified, other = _emp(db, "oq"), _emp(db, "oo")
        ws = _ws(db, "Tresen")
        _qualify(db, qualified, ws)  # `other` ist nirgends Kandidat
        plan = _plan(db)
        s = _slot(db, plan, ws, weekday=0)
        calls = []

        def boom(db_, user, *a, **k):
            calls.append(user.id)
            raise RuntimeError("defekte Daten")

        monkeypatch.setattr(calculation_service, "get_overtime_account", boom)
        out = _generate(admin_client, plan.id)
        assert _assigned_user_ids(out["plan"], str(s.id)) == {str(qualified.id)}
        assert other.id not in calls


class TestSetAssignments:
    def test_inactive_user_cannot_be_newly_assigned(self, enabled, admin_client, db):
        gone = _emp(db, "gone")
        gone.is_active = False
        db.commit()
        ws = _ws(db, "Tresen")
        s = _slot(db, _plan(db), ws)
        r = admin_client.put(f"{BASE}/slots/{s.id}/assignments", json={"user_ids": [str(gone.id)]})
        assert r.status_code == 400, r.text

    def test_already_assigned_inactive_user_may_stay_and_be_removed(self, enabled, admin_client, db):
        gone = _emp(db, "gone2")
        ws = _ws(db, "Tresen")
        s = _slot(db, _plan(db), ws)
        db.add(ShiftAssignment(tenant_id=DEFAULT_TENANT_ID, shift_slot_id=s.id, user_id=gone.id))
        gone.is_active = False
        db.commit()
        r = admin_client.put(f"{BASE}/slots/{s.id}/assignments", json={"user_ids": [str(gone.id)]})
        assert r.status_code == 200, r.text
        r = admin_client.put(f"{BASE}/slots/{s.id}/assignments", json={"user_ids": []})
        assert r.status_code == 200, r.text


class TestPlanDetailFlags:
    def _two_overlapping(self, db):
        a = _emp(db, "da")
        ws = _ws(db, "Tresen")
        ws2 = _ws(db, "Labor")
        plan = _plan(db)
        s1 = _slot(db, plan, ws, weekday=0, start="08:00", end="12:00")
        s2 = _slot(db, plan, ws2, weekday=0, start="10:00", end="14:00")
        s3 = _slot(db, plan, ws2, weekday=0, start="14:00", end="16:00")
        for s in (s1, s2, s3):
            db.add(ShiftAssignment(tenant_id=DEFAULT_TENANT_ID, shift_slot_id=s.id, user_id=a.id))
        db.commit()
        return plan, s1, s2, s3, a

    def test_admin_sees_double_booked_and_inactive_flags(self, enabled, admin_client, db):
        plan, s1, s2, s3, a = self._two_overlapping(db)
        a.is_active = False
        db.commit()
        d = admin_client.get(f"{BASE}/plans/{plan.id}").json()
        by_id = {s["id"]: s for s in d["slots"]}
        assert by_id[str(s1.id)]["double_booked"] is True
        assert by_id[str(s2.id)]["double_booked"] is True
        assert by_id[str(s3.id)]["double_booked"] is False  # grenzt nur an
        assert by_id[str(s1.id)]["assignments"][0]["double_booked"] is True
        assert by_id[str(s1.id)]["assignments"][0]["inactive"] is True

    def test_employee_view_has_no_double_booked_or_inactive_flags(self, enabled, employee_client, db):
        plan, s1, *_ = self._two_overlapping(db)
        plan.is_active = True
        db.commit()
        d = employee_client.get(f"{BASE}/plans/{plan.id}").json()
        slot = next(s for s in d["slots"] if s["id"] == str(s1.id))
        assert "double_booked" not in slot
        assert "double_booked" not in slot["assignments"][0]
        assert "inactive" not in slot["assignments"][0]
