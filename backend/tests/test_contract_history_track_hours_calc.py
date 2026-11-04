"""Teil A, Task 8: „Stundenzählung" (``track_hours``) je TAG aus dem
Vertrags-Snapshot statt aus der Live-Spalte der User-Zeile (Spec A5).

Eine Person, die ab Juli ohne Stundenzählung geführt wird, behält Januar–Juni
bitgleich; ab Juli entsteht weder Soll noch Ist. Urlaub zählt je Tag in dessen
eigenem Modus."""
from datetime import date, time, timedelta
from decimal import Decimal

from app.models import Absence, AbsenceType, WorkingHoursChange
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import add_row, entry


def _weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _seed_entries(db, user, start=date(2026, 1, 1), end=date(2026, 9, 30)):
    """Mo–Fr 08:00–17:00 ohne Pause = 9 h netto (+1 h je Tag bei 40 h / 5 Tagen)."""
    for d in _weekdays(start, end):
        entry(db, user, d, time(8, 0), time(17, 0), grace=None)


def _vacation(db, user, d, hours, half_day=None):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=AbsenceType.VACATION,
                hours=hours, half_day=half_day)
    db.add(a)
    db.commit()
    return a


def _switch_off_from_july(db, user):
    add_row(db, user, date(2026, 7, 1), weekly_hours=40, track_hours=False)
    user.track_hours = False   # Spiegel nach dem Schreiben (realistischer Zustand)
    db.commit()


def test_track_hours_off_from_july_keeps_january_to_june(db, test_user):     # spec A5
    _seed_entries(db, test_user)
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, track_hours=True)
    before = [cs.get_overtime_account(db, test_user, 2026, m) for m in range(1, 7)]
    assert before[0] > 0
    _switch_off_from_july(db, test_user)
    assert [cs.get_overtime_account(db, test_user, 2026, m) for m in range(1, 7)] == before
    assert cs.get_overtime_account(db, test_user, 2026, 9) == before[-1]       # Juli–Sept addieren 0
    assert cs.get_monthly_target(db, test_user, 2026, 8) == Decimal("0.00")
    assert cs.get_monthly_target(db, test_user, 2026, 6) > 0
    history = cs.get_overtime_history(db, test_user, 2026, 9)
    assert [history[(2026, m)] for m in range(1, 7)] == before
    assert history[(2026, 9)] == before[-1]


def test_ytd_summary_mixed_year(db, test_user):
    _seed_entries(db, test_user)
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, track_hours=True)
    _switch_off_from_july(db, test_user)
    jan_jun = list(_weekdays(date(2026, 1, 1), date(2026, 6, 30)))
    ytd = cs.get_ytd_summary(db, test_user, 2026, cutoff_date=date(2026, 9, 30))
    assert ytd["target_hours"] == float(8 * len(jan_jun))
    assert ytd["actual_hours"] == float(9 * len(jan_jun))
    assert ytd["overtime"] == float(len(jan_jun))


def test_sick_credit_on_untracked_day_counts_zero(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, track_hours=True)
    entry(db, test_user, date(2026, 6, 1), time(8, 0), time(17, 0), grace=None)
    sick = Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 8, 3),
                   type=AbsenceType.SICK, hours=8, half_day=False)
    db.add(sick)
    db.commit()
    _switch_off_from_july(db, test_user)
    june = cs.get_overtime_account(db, test_user, 2026, 6)
    assert cs.get_overtime_account(db, test_user, 2026, 8) == june
    assert cs.get_overtime_history_detailed(db, test_user, 2026, 8)[(2026, 8)].actual == Decimal("0.00")


def test_vacation_used_days_mixed_year(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, track_hours=True)
    _vacation(db, test_user, date(2026, 6, 10), hours=4)               # Altzeile: 4 h ÷ 8 h = 0,5
    _switch_off_from_july(db, test_user)
    _vacation(db, test_user, date(2026, 8, 3), hours=0)                 # ohne Stundenzählung: 1 Tag
    _vacation(db, test_user, date(2026, 8, 4), hours=0)
    acc = cs.get_vacation_account(db, test_user, 2026)
    assert acc["used_days"] == 2.5
    assert acc["track_hours"] is False          # Stichtag (heute) liegt im Zeitraum ohne Stundenzählung
    rows = db.query(Absence).filter(Absence.user_id == test_user.id).all()
    assert cs.absence_days(db, test_user, rows) == Decimal("2.5")


def test_counts_vacation_by_day_only_per_day(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, track_hours=True)
    _switch_off_from_july(db, test_user)
    assert cs.counts_vacation_by_day_only(db, test_user, date(2026, 6, 30)) is False
    assert cs.counts_vacation_by_day_only(db, test_user, date(2026, 7, 1)) is True
    rows = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).all()
    assert cs.counts_vacation_by_day_only(db, test_user, date(2026, 6, 30), wh_changes=rows) is False
    assert cs.is_vacation_billable_day(db, test_user, date(2026, 8, 3)) is True   # ohne Stundenzählung: jeder Werktag
    assert cs.get_day_presence_target(db, test_user, date(2026, 8, 3)) == Decimal("0")
    assert cs.get_day_presence_target(db, test_user, date(2026, 6, 1)) == Decimal("8.00")


def _snapshot(db, user):
    return (
        [cs.get_overtime_account(db, user, 2026, m) for m in range(1, 10)],
        cs.get_overtime_history_detailed(db, user, 2026, 9),
        cs.get_ytd_summary(db, user, 2026, cutoff_date=date(2026, 9, 30)),
        cs.get_vacation_account(db, user, 2026),
        [cs.get_monthly_target(db, user, 2026, m) for m in range(1, 10)],
        cs.get_gross_monthly_target(db, user, 2026, 3),
    )


def test_always_tracked_and_always_untracked_unchanged(db, test_user):
    _seed_entries(db, test_user, end=date(2026, 3, 31))
    _vacation(db, test_user, date(2026, 3, 10), hours=8, half_day=False)
    tracked_without_rows = _snapshot(db, test_user)
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, track_hours=True)
    add_row(db, test_user, date(2026, 2, 1), weekly_hours=40, track_hours=True)
    assert _snapshot(db, test_user) == tracked_without_rows

    for row in db.query(WorkingHoursChange).all():
        db.delete(row)
    test_user.track_hours = False
    db.commit()
    untracked_without_rows = _snapshot(db, test_user)
    assert untracked_without_rows[0] == [Decimal("0.00")] * 9
    assert untracked_without_rows[1] == {}
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, track_hours=False)
    add_row(db, test_user, date(2026, 2, 1), weekly_hours=40, track_hours=False)
    assert _snapshot(db, test_user) == untracked_without_rows
