"""Teil B: verkuerzter Tag -> Tagessoll = min(Tagessoll laut Snapshot, X) an jeder Soll-Stelle."""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import (
    User, UserRole, Absence, AbsenceType, PublicHoliday, TimeEntry, ReducedDay,
)
from app.models.system_setting import SystemSetting
from app.services import calculation_service, special_days_service
from tests.conftest import DEFAULT_TENANT_ID

D24 = date(2026, 12, 24)   # Thursday
RM = date(2026, 2, 16)     # Monday, custom reduced day
TH = date(2026, 2, 19)     # Thursday, custom reduced day
SAT = date(2026, 2, 14)


def _reduce(db, d, hours):
    if (d.month, d.day) in ((12, 24), (12, 31)):
        prefix = "special_day_dec24" if d.day == 24 else "special_day_dec31"
        for k, v in ((f"{prefix}_mode", "max_hours"), (f"{prefix}_max_hours", str(hours))):
            db.add(SystemSetting(key=k, value=v, description=k, tenant_id=DEFAULT_TENANT_ID))
    else:
        db.add(ReducedDay(tenant_id=DEFAULT_TENANT_ID, date=d, label="Brueckentag",
                          max_hours=Decimal(str(hours))))
    db.commit()


def _day_soll(db, user, d):
    return calculation_service.get_range_target(db, user, d, d)


def _mk(db, **kw):
    base = dict(username="u3", email="u3@t.l", password_hash="x", first_name="U",
                last_name="3", role=UserRole.EMPLOYEE, weekly_hours=Decimal("15"),
                work_days_per_week=5, track_hours=True, is_active=True,
                tenant_id=DEFAULT_TENANT_ID)
    base.update(kw)
    u = User(**base)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user_3h(db, default_tenant):
    return _mk(db)


@pytest.fixture
def fixed_user(db, default_tenant):
    return _mk(db, username="fx", email="fx@t.l", weekly_hours=Decimal("16"),
               work_days_per_week=2, use_daily_schedule=True,
               use_fixed_monthly_target=True, agreed_monthly_hours=Decimal("40"),
               hours_monday=Decimal("8"), hours_thursday=Decimal("8"))


@pytest.fixture
def fixed_user_3h_thursday(db, default_tenant):
    return _mk(db, username="fx3", email="fx3@t.l", weekly_hours=Decimal("6"),
               work_days_per_week=2, use_daily_schedule=True,
               use_fixed_monthly_target=True, agreed_monthly_hours=Decimal("40"),
               hours_monday=Decimal("3"), hours_thursday=Decimal("3"))


def test_dec24_max_hours_caps_8h_person(db, test_user):
    _reduce(db, D24, "4")
    assert _day_soll(db, test_user, D24) == Decimal("4")


def test_dec24_max_hours_keeps_3h_person(db, user_3h):
    _reduce(db, D24, "4")
    assert _day_soll(db, user_3h, D24) == Decimal("3")


def test_dec24_max_hours_person_without_thursday(db, day_plan_user):
    _reduce(db, D24, "4")
    assert _day_soll(db, day_plan_user, D24) == Decimal("0")


def test_custom_day_caps_8h_person(db, test_user):
    _reduce(db, TH, "4")
    assert _day_soll(db, test_user, TH) == Decimal("4")


def test_custom_day_keeps_3h_person(db, user_3h):
    _reduce(db, TH, "4")
    assert _day_soll(db, user_3h, TH) == Decimal("3")


def test_custom_day_person_without_thursday(db, day_plan_user):
    _reduce(db, TH, "4")
    assert _day_soll(db, day_plan_user, TH) == Decimal("0")


def test_custom_day_caps_and_holiday_wins(db, test_user):
    _reduce(db, RM, "4")
    assert _day_soll(db, test_user, RM) == Decimal("4")
    db.add(PublicHoliday(tenant_id=DEFAULT_TENANT_ID, date=RM, name="X", year=2026,
                         is_custom=True, source="admin"))
    db.commit()
    assert _day_soll(db, test_user, RM) == Decimal("0")


def test_custom_day_on_weekend_no_effect(db, test_user):
    before = calculation_service.get_monthly_target(db, test_user, 2026, 2)
    _reduce(db, SAT, "4")
    assert _day_soll(db, test_user, SAT) == Decimal("0")
    assert calculation_service.get_monthly_target(db, test_user, 2026, 2) == before


def test_worked_6h_gives_plus_2(db, test_user):
    _reduce(db, D24, "4")
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=D24,
                     start_time=time(8, 0), end_time=time(14, 0), break_minutes=0))
    db.commit()
    soll = _day_soll(db, test_user, D24)
    ist = calculation_service.get_range_actual(db, test_user, D24, D24)
    assert ist - soll == Decimal("2")


def test_half_day_absence_on_reduced_day(db, test_user):
    _reduce(db, D24, "4")
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=D24,
                   type=AbsenceType.VACATION, hours=Decimal("2"), half_day=True))
    db.commit()
    assert _day_soll(db, test_user, D24) == Decimal("2")


def test_gross_monthly_target_uses_cap(db, test_user):
    plain = calculation_service.get_gross_monthly_target(db, test_user, 2026, 12)
    _reduce(db, D24, "4")
    assert calculation_service.get_gross_monthly_target(db, test_user, 2026, 12) == plain - Decimal("4")


def test_presence_target_shows_cap(db, test_user):
    _reduce(db, D24, "4")
    assert calculation_service.get_day_presence_target(db, test_user, D24) == Decimal("4.00")


def test_fixed_mode_month_target_unchanged(db, fixed_user):
    before = calculation_service.get_monthly_target(db, fixed_user, 2026, 12)
    _reduce(db, D24, "4")
    assert calculation_service.get_monthly_target(db, fixed_user, 2026, 12) == before


def test_fixed_planned_hours_min_not_half(db, fixed_user_3h_thursday, fixed_user):
    _reduce(db, D24, "4")
    cfg = special_days_service.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    assert calculation_service._fixed_planned_hours(db, fixed_user_3h_thursday, D24, cfg) == Decimal("3")
    assert calculation_service._fixed_planned_hours(db, fixed_user, D24, cfg) == Decimal("4")


def test_future_freizeitausgleich_on_reduced_day(db, test_user):
    _reduce(db, D24, "4")
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=D24,
                   type=AbsenceType.OVERTIME, hours=Decimal("8")))
    db.commit()
    assert calculation_service.future_freizeitausgleich_impact(
        db, test_user, cutoff_date=date(2026, 11, 2), today=date(2026, 11, 3)
    ) == Decimal("4.00")
