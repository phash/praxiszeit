"""075: Vertrags-Snapshot (Urlaub, Stundenzaehlung, MiLoG) an working_hours_changes."""
from datetime import date
from decimal import Decimal

from app.models import WorkingHoursChange
from tests.wh_change_helpers import add_row


def test_columns_exist_and_four_are_not_nullable():
    cols = WorkingHoursChange.__table__.c
    for name in ("vacation_days", "track_hours", "milog_working_time_account", "use_fixed_monthly_target"):
        assert cols[name].nullable is False
    assert cols["agreed_monthly_hours"].nullable is True
    assert str(cols["vacation_days"].type) == "NUMERIC(4, 1)"
    assert str(cols["agreed_monthly_hours"].type) == "NUMERIC(5, 1)"


def test_test_listener_fills_unset_fields_from_user(db, test_user):
    test_user.vacation_days = 24
    test_user.agreed_monthly_hours = Decimal("43.3")
    db.commit()
    row = add_row(db, test_user, date(2026, 1, 1), weekly_hours=20)
    assert row.vacation_days == Decimal("24.0") and row.track_hours is True
    assert row.agreed_monthly_hours == Decimal("43.3")


def test_listener_keeps_explicit_none_for_agreed(db, test_user):
    test_user.agreed_monthly_hours = Decimal("43.3")
    db.commit()
    row = add_row(db, test_user, date(2026, 1, 1), weekly_hours=20, agreed_monthly_hours=None)
    assert row.agreed_monthly_hours is None
