"""#329: arbitrary date-range Soll/Ist helpers (basis for the weekly admin view).

``get_range_target`` / ``get_range_actual`` mirror the monthly versions but take
an explicit ``[start, end]`` (inclusive) range, so a calendar week — which may
span a month (or year) boundary — can be computed in one call.
"""
from decimal import Decimal
from datetime import date, time

from app.models import TimeEntry, Absence, AbsenceType
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID

# KW 26/2026 — Mon 22.06. .. Sun 28.06.
MON = date(2026, 6, 22)
TUE = date(2026, 6, 23)
WED = date(2026, 6, 24)
SUN = date(2026, 6, 28)


def _entry(user, d, start=time(8, 0), end=time(17, 0), break_min=60):
    return TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=start, end_time=end, break_minutes=break_min,
    )


class TestRangeTarget:
    def test_full_week_is_five_workdays(self, db, test_user):
        # 40h/5d → 8h/day; Mon–Sun has 5 workdays → 40h. Weekend contributes 0.
        target = calculation_service.get_range_target(db, test_user, MON, SUN)
        assert target == Decimal('40.00')

    def test_partial_mon_to_wed(self, db, test_user):
        target = calculation_service.get_range_target(db, test_user, MON, WED)
        assert target == Decimal('24.00')

    def test_respects_cutoff(self, db, test_user):
        # up_to_date trims the range (e.g. #313 "bis heute"): Mon–Sun capped at Wed → 24h.
        target = calculation_service.get_range_target(db, test_user, MON, SUN, up_to_date=WED)
        assert target == Decimal('24.00')

    def test_absence_reduces_target(self, db, test_user):
        db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=TUE,
                       type=AbsenceType.VACATION, hours=8.0))
        db.commit()
        target = calculation_service.get_range_target(db, test_user, MON, SUN)
        assert target == Decimal('32.00')  # 5 workdays − 1 vacation day

    def test_spans_month_boundary(self, db, test_user):
        # Mon 29.06. .. Sun 05.07. → workdays Jun 29/30 + Jul 1/2/3 = 5 × 8h = 40h.
        target = calculation_service.get_range_target(
            db, test_user, date(2026, 6, 29), date(2026, 7, 5)
        )
        assert target == Decimal('40.00')


class TestRangeActual:
    def test_empty_range_is_zero(self, db, test_user):
        assert calculation_service.get_range_actual(db, test_user, MON, SUN) == Decimal('0.00')

    def test_sums_only_entries_in_range(self, db, test_user):
        db.add(_entry(test_user, MON))   # 8h, in range
        db.add(_entry(test_user, TUE))   # 8h, in range
        db.add(_entry(test_user, date(2026, 6, 19)))  # 8h, previous week — must NOT count
        db.commit()
        actual = calculation_service.get_range_actual(db, test_user, MON, SUN)
        assert actual == Decimal('16.00')

    def test_respects_cutoff(self, db, test_user):
        db.add(_entry(test_user, MON))   # 8h
        db.add(_entry(test_user, WED))   # 8h, after the cutoff
        db.commit()
        actual = calculation_service.get_range_actual(db, test_user, MON, SUN, up_to_date=TUE)
        assert actual == Decimal('8.00')
