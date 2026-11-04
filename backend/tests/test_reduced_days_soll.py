"""Teil B: verkuerzter Tag -> Tagessoll = min(Tagessoll laut Snapshot, X) an jeder Soll-Stelle."""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import Absence, AbsenceType, PublicHoliday, TimeEntry
from app.models.system_setting import SystemSetting
from app.services import calculation_service, special_days_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import add_row
from tests.reduced_days_helpers import make_user_3h, reduce_day as _reduce

D24 = date(2026, 12, 24)   # Thursday
RM = date(2026, 2, 16)     # Monday, custom reduced day
TH = date(2026, 2, 19)     # Thursday, custom reduced day
SAT = date(2026, 2, 14)


def _day_soll(db, user, d):
    return calculation_service.get_range_target(db, user, d, d)


_mk = make_user_3h


def _fixed(db, name, weekly, day_hours):
    """Minijob mit festem Monats-Soll (Mo + Do ``day_hours`` h): der gültige Zustand
    des Schreibwegs — MiLoG-Konto an — und der Modus kommt aus der Verlaufszeile
    (Snapshot), nicht aus der User-Zeile."""
    flags = dict(milog_working_time_account=True, use_fixed_monthly_target=True,
                 agreed_monthly_hours=Decimal("40"))
    u = _mk(db, username=name, email=f"{name}@t.l", weekly_hours=weekly, work_days_per_week=2,
            use_daily_schedule=True, hours_monday=Decimal(day_hours), hours_thursday=Decimal(day_hours),
            **flags)
    add_row(db, u, date(2020, 1, 1), day_hours=[day_hours, None, None, day_hours, None],
            vacation_days=Decimal("30"), track_hours=True, **flags)
    return u


@pytest.fixture
def user_3h(db, default_tenant):
    return _mk(db)


@pytest.fixture
def fixed_user(db, default_tenant):
    return _fixed(db, "fx", Decimal("16"), 8)


@pytest.fixture
def fixed_user_3h_thursday(db, default_tenant):
    return _fixed(db, "fx3", Decimal("6"), 3)


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


def test_sick_credit_on_reduced_day_is_exact_no_negative_zero(db, default_tenant):
    """F014: ``min(t, X) ÷ t`` ist periodisch (3,75 ÷ 11,93). Die Gutschrift
    eines Kranktags am verkürzten Tag trifft das Soll exakt — kein ``-0.00``."""
    u = _mk(db, username="t1193", email="t1193@t.l", weekly_hours=Decimal("59.65"))
    _reduce(db, RM, "3.75")
    sick = Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=RM,
                   type=AbsenceType.SICK, hours=Decimal("11.93"))
    db.add(sick)
    db.commit()
    cfg = special_days_service.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    credit = calculation_service.credited_absence_hours(
        [sick], RM, set(), cfg, daily_target=Decimal("11.93"))
    assert credit == Decimal("3.75")
    soll = special_days_service.special_day_target(RM, Decimal("11.93"), cfg)
    assert str((credit - soll).quantize(Decimal("0.01"))) == "0.00"
    assert calculation_service.get_range_actual(db, u, RM, RM) == Decimal("3.75")


@pytest.mark.parametrize("mode,expected", [("half_day", "4"), ("free", "8"), ("working_day", "8")])
def test_fixed_planned_hours_other_modes_unchanged(db, fixed_user, mode, expected):
    """F058/F082: ``_fixed_planned_hours`` nutzt ``special_day_target``; ``half_day``
    halbiert, ``free`` behält bewusst die vollen Planstunden (wie vor Teil B)."""
    db.add(SystemSetting(key="special_day_dec24_mode", value=mode, description="x",
                         tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    cfg = special_days_service.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    assert calculation_service._fixed_planned_hours(db, fixed_user, D24, cfg) == Decimal(expected)
