"""#313 — Monatssaldo nur bis zum letzten abgeschlossenen Arbeitstag (Stichtag/cutoff)."""
from datetime import date, time, timedelta
from decimal import Decimal

from app.models import TimeEntry
from app.services import calculation_service as calc
from tests.conftest import DEFAULT_TENANT_ID


def _entry(db, user, d, start=time(8, 0), end=time(16, 0), brk=0):
    e = TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                  start_time=start, end_time=end, break_minutes=brk)
    db.add(e)
    db.commit()
    return e


class TestSollCutoffDate:
    def test_today_counts_when_clocked_out(self, db, test_user):
        today = date(2025, 1, 15)
        _entry(db, test_user, today)  # completed (end_time set)
        assert calc.get_soll_cutoff_date(db, test_user, today=today) == today

    def test_yesterday_when_today_has_no_completed_entry(self, db, test_user):
        today = date(2025, 1, 15)
        # open entry (still clocked in) does NOT count today
        db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=today,
                         start_time=time(8, 0), end_time=None))
        db.commit()
        assert calc.get_soll_cutoff_date(db, test_user, today=today) == today - timedelta(days=1)

    def test_yesterday_when_no_entry_at_all(self, db, test_user):
        today = date(2025, 1, 15)
        assert calc.get_soll_cutoff_date(db, test_user, today=today) == today - timedelta(days=1)


class TestMonthlyTargetCutoff:
    def test_up_to_date_trims_current_month(self, db, test_user):
        full = calc.get_monthly_target(db, test_user, 2025, 1)
        mid = calc.get_monthly_target(db, test_user, 2025, 1, up_to_date=date(2025, 1, 15))
        assert Decimal('0') < mid < full

    def test_month_end_equals_full_month(self, db, test_user):
        full = calc.get_monthly_target(db, test_user, 2025, 1)
        assert calc.get_monthly_target(db, test_user, 2025, 1, up_to_date=date(2025, 1, 31)) == full

    def test_before_month_is_zero(self, db, test_user):
        assert calc.get_monthly_target(db, test_user, 2025, 1, up_to_date=date(2024, 12, 31)) == Decimal('0.00')

    def test_default_is_unchanged(self, db, test_user):
        # regression: no cutoff == old behaviour
        assert calc.get_monthly_target(db, test_user, 2025, 1, up_to_date=None) == \
            calc.get_monthly_target(db, test_user, 2025, 1)


class TestMonthlyActualCutoff:
    def test_entries_after_cutoff_excluded(self, db, test_user):
        _entry(db, test_user, date(2025, 1, 6))   # 8h
        _entry(db, test_user, date(2025, 1, 20))  # 8h
        full = calc.get_monthly_actual(db, test_user, 2025, 1)
        trimmed = calc.get_monthly_actual(db, test_user, 2025, 1, up_to_date=date(2025, 1, 10))
        assert full == Decimal('16.00')
        assert trimmed == Decimal('8.00')


class TestOvertimeAccountCutoff:
    def test_cutoff_removes_month_start_minus(self, db, test_user):
        # one worked day, rest of month not yet due
        _entry(db, test_user, date(2025, 1, 6))  # 8h Ist
        full = calc.get_overtime_account(db, test_user, 2025, 1)  # whole-month Soll → deep minus
        cut = calc.get_overtime_account(db, test_user, 2025, 1, cutoff_date=date(2025, 1, 6))
        assert cut > full  # trimming the un-worked rest of the month lifts the balance

    def test_default_is_unchanged(self, db, test_user):
        _entry(db, test_user, date(2025, 1, 6))
        assert calc.get_overtime_account(db, test_user, 2025, 1, cutoff_date=None) == \
            calc.get_overtime_account(db, test_user, 2025, 1)

    def test_history_matches_account_with_cutoff(self, db, test_user):
        # ArbZG-audit #4: the chart's cumulative (get_overtime_history) must stay
        # bit-identical to get_overtime_account under the SAME cutoff (the
        # dashboard relies on this — cf. pinned test_overtime_history_matches_account).
        _entry(db, test_user, date(2025, 1, 6))
        _entry(db, test_user, date(2025, 1, 20))
        cutoff = date(2025, 1, 10)
        history = calc.get_overtime_history(db, test_user, 2025, 1, cutoff_date=cutoff)
        assert history.get((2025, 1)) == calc.get_overtime_account(db, test_user, 2025, 1, cutoff_date=cutoff)
