"""Teil A: Schedule traegt die fuenf Vertragsfelder; Aufloesungsregel."""
from datetime import date
from decimal import Decimal

from app.services import calculation_service as cs
from tests.wh_change_helpers import add_row


def test_no_rows_reads_user_row(db, test_user):
    test_user.vacation_days = 24
    db.commit()
    s = cs.get_schedule_for_date(db, test_user, date(2026, 3, 1))
    assert s.vacation_days == Decimal("24.0") and s.track_hours is True and s.agreed_monthly_hours is None


def test_before_first_row_uses_first_row_values_not_user_row(db, test_user):
    add_row(db, test_user, date(2026, 10, 31), weekly_hours=40, vacation_days=24, track_hours=True)
    test_user.vacation_days = 30
    test_user.track_hours = False
    db.commit()  # Spiegel ist weitergewandert
    s = cs.get_schedule_for_date(db, test_user, date(2026, 1, 5))
    assert s.vacation_days == Decimal("24.0") and s.track_hours is True
    assert s.weekly_hours == Decimal(str(test_user.weekly_hours))  # Stundenregel unveraendert
    assert cs.tracks_hours_on(db, test_user, date(2026, 1, 5)) is True


def test_latest_row_wins_after_first(db, test_user):
    add_row(db, test_user, date(2026, 3, 1), weekly_hours=40, vacation_days=24)
    add_row(db, test_user, date(2026, 6, 1), weekly_hours=40, vacation_days=27, track_hours=False)
    s = cs.get_schedule_for_date(db, test_user, date(2026, 7, 1))
    assert s.vacation_days == Decimal("27.0") and s.track_hours is False
    assert cs.tracks_hours_on(db, test_user, date(2026, 7, 1)) is False


def test_preload_path_identical(db, test_user):
    rows = [add_row(db, test_user, date(2026, 3, 1), weekly_hours=40, vacation_days=24),
            add_row(db, test_user, date(2026, 6, 1), weekly_hours=20, vacation_days=20, track_hours=False),
            add_row(db, test_user, date(2026, 9, 1), weekly_hours=30, vacation_days=27)]
    for d in (date(2026, 1, 1), date(2026, 3, 1), date(2026, 5, 31), date(2026, 6, 1), date(2026, 8, 31),
              date(2026, 9, 1), date(2027, 1, 1)):
        assert cs.get_schedule_for_date(db, test_user, d) == cs.get_schedule_for_date(db, test_user, d, wh_changes=rows)


def test_schedule_display_json_has_contract_fields(db, test_user):
    j = cs.schedule_display_json(cs.get_schedule_for_date(db, test_user, date(2026, 1, 1)))
    assert {"vacation_days", "track_hours", "milog_working_time_account",
            "agreed_monthly_hours", "use_fixed_monthly_target"} <= j.keys()


def test_null_agreed_in_snapshot_is_not_filled_from_user_row(db, test_user):
    """F135 (3): ``agreed_monthly_hours=None`` in der Zeile heißt „abgeleitet" — die
    User-Zeile (Spiegel) füllt es nie auf."""
    test_user.agreed_monthly_hours = Decimal("45")
    db.commit()
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, vacation_days=24, agreed_monthly_hours=None)
    assert cs.get_schedule_for_date(db, test_user, date(2026, 6, 1)).agreed_monthly_hours is None
