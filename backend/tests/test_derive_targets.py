"""Spec 4.1: Tagessoll aus NEUEN Blöcken — DIE eine Ableitung (derive_targets)."""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import TimeEntry, WorkingHoursChange
from app.services import calculation_service, work_blocks_service as wbs
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import block_week


@pytest.mark.parametrize("day, pause, expected", [
    ([("08:00", "12:00"), ("15:00", "18:00")], 30, Decimal("6.50")),
    ([("08:00", "12:05")], 0, Decimal("4.08")),                       # 4,0833…
    ([("07:30", "12:00"), ("13:00", "16:25")], 0, Decimal("7.92")),   # 7,9166…
])
def test_table_4_1(day, pause, expected):
    derived = wbs.derive_targets(block_week(pause=pause, mon=day))
    assert derived["hours_monday"] == expected
    assert derived["hours_tuesday"] == Decimal("0.00")
    assert derived["weekly_hours"] == expected
    assert derived["work_days_per_week"] == 1
    assert derived["use_daily_schedule"] is True


def test_week_sum_and_work_days():
    week = block_week(mon=[("08:00", "12:00")], tue=[("08:00", "13:00")], thu=[("08:00", "12:00")])
    derived = wbs.derive_targets(week)
    assert derived["weekly_hours"] == Decimal("13.00")
    assert derived["work_days_per_week"] == 3
    assert derived["hours_wednesday"] == Decimal("0.00")


def test_three_55_minute_blocks_stay_within_the_rounding_bound():
    """Spec 4.1: Abweichung ≤ 0,005 h × (Einträge + 1) — hier 2,76 gegen 2,75."""
    week = block_week(mon=[("08:00", "08:55"), ("09:00", "09:55"), ("10:00", "10:55")])
    assert wbs.derive_targets(week)["hours_monday"] == Decimal("2.75")
    nets = [
        TimeEntry(start_time=time(h, 0), end_time=time(h, 55), break_minutes=0, uncredited_minutes=0).net_hours
        for h in (8, 9, 10)
    ]
    assert sum(nets) == Decimal("2.76")
    assert sum(nets) - Decimal("2.75") <= Decimal("0.005") * (len(nets) + 1)


def test_coupled_to_get_daily_target_for_date(db, test_user):
    week = block_week(pause=30, mon=[("08:00", "12:00"), ("15:00", "18:00")])
    d = wbs.derive_targets(week)
    db.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=date(2026, 1, 1),
        blocks=week, weekly_hours=d["weekly_hours"], use_daily_schedule=True,
        hours_monday=d["hours_monday"], hours_tuesday=d["hours_tuesday"],
        hours_wednesday=d["hours_wednesday"], hours_thursday=d["hours_thursday"],
        hours_friday=d["hours_friday"], work_days_per_week=d["work_days_per_week"],
    ))
    db.commit()
    mon, tue = date(2026, 6, 1), date(2026, 6, 2)
    sched = calculation_service.get_schedule_for_date(db, test_user, mon)
    assert calculation_service.get_daily_target_for_date(test_user, mon, sched) == Decimal("6.50")
    assert calculation_service.get_daily_target_for_date(test_user, tue, sched) == Decimal("0")
