"""Fix #1: vacation budget for years ENTIRELY outside the employment window.

The pro-rata branches in ``get_vacation_account`` only handle the entry/exit
*year*. A year completely before ``first_work_day`` (future hire) or completely
after ``last_work_day`` (departed employee) had no ``else`` branch, so it kept
the full ``vacation_days`` budget (+ carryover) → phantom entitlement that even
fed the carryover. Such years must grant zero budget.
"""
from datetime import date

from app.models import User, UserRole, YearCarryover
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _mk(db, username, first_work_day=None, last_work_day=None, vacation_days=30):
    u = User(
        username=username, email=f"{username}@x.de", password_hash="h",
        first_name=username, last_name="T", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=vacation_days, work_days_per_week=5,
        is_active=True, track_hours=True, tenant_id=DEFAULT_TENANT_ID,
        first_work_day=first_work_day, last_work_day=last_work_day,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_year_after_last_work_day_has_zero_budget(db, default_tenant):
    u = _mk(db, "leaver", last_work_day=date(2025, 6, 30))
    acc = calculation_service.get_vacation_account(db, u, 2026)  # year AFTER exit
    assert acc["budget_days"] == 0.0
    assert acc["remaining_days"] == 0.0


def test_year_before_first_work_day_has_zero_budget(db, default_tenant):
    u = _mk(db, "starter", first_work_day=date(2026, 9, 1))
    acc = calculation_service.get_vacation_account(db, u, 2025)  # year BEFORE entry
    assert acc["budget_days"] == 0.0
    assert acc["remaining_days"] == 0.0


def test_out_of_window_year_ignores_carryover(db, default_tenant):
    # Even a stray carryover row must not resurrect a budget for a year the
    # employee was not employed at all.
    u = _mk(db, "leaver2", last_work_day=date(2025, 6, 30))
    db.add(YearCarryover(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                         overtime_hours=0, vacation_days=10))
    db.commit()
    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == 0.0
    assert acc["remaining_days"] == 0.0


def test_entry_year_still_pro_rata(db, default_tenant):
    # Guard must NOT affect the entry year itself (regression guard).
    u = _mk(db, "starter2", first_work_day=date(2026, 9, 1))
    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == 10.0  # 30 * (Sep-Dec = 4 months) / 12
