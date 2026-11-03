"""Teil A, Task 3: Urlaubsanspruch anteilig je Vertragssegment (Spec A3/A5).

``calculation_service.vacation_entitlement_days`` ist die EINZIGE Rechenstelle des
Anspruchs (ohne Übertrag). Der Ein-Segment-Fall bleibt bitgleich zur alten
Pro-rata-Rechnung von ``get_vacation_account`` (unten wörtlich kopiert)."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from app.models import YearCarryover
from app.services import calculation_service as cs
from tests.wh_change_helpers import add_row, change_row


def legacy_budget(value: Decimal, first_work_day, last_work_day, year: int) -> Decimal:
    """Wörtliche Kopie der Pro-rata-Zweige aus ``get_vacation_account`` vor Task 3
    (``git show f3f0bc45:backend/app/services/calculation_service.py``), mit
    ``user.vacation_days`` → ``value`` und ``user.first/last_work_day`` als Argumente."""
    class _U:
        pass
    user = _U()
    user.vacation_days = value
    user.first_work_day = first_work_day
    user.last_work_day = last_work_day
    # --- verbatim ab hier ---
    budget_days = Decimal(str(user.vacation_days))
    first_in_year = user.first_work_day and user.first_work_day.year == year
    last_in_year = user.last_work_day and user.last_work_day.year == year
    year_outside_window = bool(
        (user.last_work_day and user.last_work_day.year < year)
        or (user.first_work_day and user.first_work_day.year > year)
    )
    if year_outside_window:
        budget_days = Decimal('0')
    elif first_in_year and last_in_year:
        fwd = user.first_work_day
        fwd_days_in_month = monthrange(fwd.year, fwd.month)[1]
        fwd_days_remaining = fwd_days_in_month - fwd.day + 1  # inklusive Starttag
        months_remaining = (Decimal(str(12 - fwd.month))
                            + Decimal(str(fwd_days_remaining)) / Decimal(str(fwd_days_in_month)))
        lwd = user.last_work_day
        lwd_days_in_month = monthrange(lwd.year, lwd.month)[1]
        lwd_days_worked = lwd.day  # inklusive letzten Tag
        months_worked = (Decimal(str(lwd.month - 1))
                         + Decimal(str(lwd_days_worked)) / Decimal(str(lwd_days_in_month)))
        employed_months = max(Decimal('0'), months_remaining + months_worked - Decimal('12'))
        budget_days = (Decimal(str(user.vacation_days)) * employed_months / Decimal('12')).quantize(Decimal('0.1'))
    elif first_in_year:
        fwd = user.first_work_day
        days_in_month = monthrange(fwd.year, fwd.month)[1]
        days_remaining = days_in_month - fwd.day + 1  # inklusive Starttag
        months_remaining = Decimal(str(12 - fwd.month)) + Decimal(str(days_remaining)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_remaining / Decimal('12')).quantize(Decimal('0.1'))
    elif last_in_year:
        lwd = user.last_work_day
        days_in_month = monthrange(lwd.year, lwd.month)[1]
        days_worked = lwd.day  # inklusive letzten Tag
        months_worked = Decimal(str(lwd.month - 1)) + Decimal(str(days_worked)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_worked / Decimal('12')).quantize(Decimal('0.1'))
    return budget_days


def every_day(year: int, step: int = 1):
    d = date(year, 1, 1)
    while d.year == year:
        yield d
        d += timedelta(days=step)


def every_pair(year: int, step: int):
    days = list(every_day(year, step)) + [date(year, 12, 31)]
    for i, fwd in enumerate(days):
        for lwd in days[i:]:
            yield fwd, lwd


def test_customer_case_4_to_5_days_from_nov(db, test_user):   # spec A5
    test_user.first_work_day = date(2020, 1, 1)
    test_user.vacation_days = 24
    db.commit()
    add_row(db, test_user, date(2020, 1, 1), weekly_hours=40, vacation_days=24)
    add_row(db, test_user, date(2026, 11, 1), weekly_hours=40, vacation_days=30)
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("25.0")
    assert cs.vacation_entitlement_days(db, test_user, 2027) == Decimal("30.0")
    assert cs.vacation_entitlement_days(db, test_user, 2025) == Decimal("24.0")


def test_change_mid_month_is_day_exact(db, test_user):        # 24×(10+14/30)/12 + 30×(16/30+1)/12
    test_user.first_work_day = date(2020, 1, 1)
    db.commit()
    add_row(db, test_user, date(2020, 1, 1), weekly_hours=40, vacation_days=24)
    add_row(db, test_user, date(2026, 11, 15), weekly_hours=40, vacation_days=30)
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("24.8")


def test_change_in_entry_year_is_clipped_by_window(db, test_user):
    test_user.first_work_day = date(2026, 4, 1)
    db.commit()
    add_row(db, test_user, date(2026, 4, 1), weekly_hours=40, vacation_days=24)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=40, vacation_days=30)
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("20.0")


def test_no_rows_unchanged(db, test_user):
    test_user.vacation_days = Decimal("16.8")
    db.commit()
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("16.8")


def test_first_change_without_first_work_day_uses_old_value_before(db, test_user):
    # spec A5: no first_work_day, no bookings — before the first row = first row
    add_row(db, test_user, date(2026, 10, 31), weekly_hours=40, vacation_days=24)
    add_row(db, test_user, date(2026, 11, 1), weekly_hours=40, vacation_days=30)
    test_user.vacation_days = 30
    db.commit()
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("25.0")


def test_single_segment_matches_legacy_pro_rata_for_every_entry_and_exit_day(db, test_user):
    for value in (Decimal("24"), Decimal("30"), Decimal("16.8")):
        rows = [change_row(test_user, date(2020, 1, 1), weekly_hours=40, vacation_days=value,
                           track_hours=True, milog_working_time_account=False,
                           agreed_monthly_hours=None, use_fixed_monthly_target=False)]  # transient
        for d in every_day(2026):                       # entry only, exit only
            for fwd, lwd in ((d, None), (None, d)):
                test_user.first_work_day, test_user.last_work_day = fwd, lwd
                got = cs.vacation_entitlement_days(db, test_user, 2026, wh_changes=rows)
                assert got == legacy_budget(value, fwd, lwd, 2026), (value, fwd, lwd)
        for fwd, lwd in every_pair(2026, step=7):       # entry and exit in the same year, fwd <= lwd
            test_user.first_work_day, test_user.last_work_day = fwd, lwd
            got = cs.vacation_entitlement_days(db, test_user, 2026, wh_changes=rows)
            assert got == legacy_budget(value, fwd, lwd, 2026), (value, fwd, lwd)
    db.rollback()


def test_fix1_year_outside_window_has_no_budget_and_no_carryover(db, test_user):
    test_user.first_work_day = date(2020, 1, 1)
    test_user.last_work_day = date(2025, 6, 30)
    db.commit()
    add_row(db, test_user, date(2020, 1, 1), weekly_hours=40, vacation_days=24)
    db.add(YearCarryover(user_id=test_user.id, tenant_id=test_user.tenant_id, year=2026, vacation_days=5, overtime_hours=0))
    db.add(YearCarryover(user_id=test_user.id, tenant_id=test_user.tenant_id, year=2025, vacation_days=3, overtime_hours=0))
    db.commit()
    assert cs.get_vacation_account(db, test_user, 2026)["budget_days"] == 0
    assert cs.get_vacation_account(db, test_user, 2025)["budget_days"] == 15.0      # 24 × 6/12 = 12,0 + 3


def test_carryover_added_after_rounding_not_prorated(db, test_user):
    test_user.first_work_day = date(2020, 1, 1)
    db.commit()
    add_row(db, test_user, date(2020, 1, 1), weekly_hours=40, vacation_days=24)
    add_row(db, test_user, date(2026, 11, 15), weekly_hours=40, vacation_days=30)
    db.add(YearCarryover(user_id=test_user.id, tenant_id=test_user.tenant_id, year=2026, vacation_days=1, overtime_hours=0))
    db.commit()
    account = cs.get_vacation_account(db, test_user, 2026)
    assert account["budget_days"] == 25.8      # 24,8 + 1
    assert account["entitlement_days"] == 24.8
