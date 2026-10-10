"""Spec 2026-10-08, 8.3 / 8.4 (P14, P22): weiche Warnungen auf der Anwesenheit
laut Stempel und der Pausen-Doppelabzug (PR2)."""
import uuid
from datetime import time, timedelta

from app.models import TimeEntry
from app.models.tenant import Tenant
from app.services import presence_service as ps
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import MON


def _e(start, end, brk=0, unc=0, raw_start=None, raw_end=None, auto=False):
    return TimeEntry(start_time=start, end_time=end, break_minutes=brk, uncredited_minutes=unc,
                     raw_start_time=raw_start, raw_end_time=raw_end, auto_closed=auto)


def _codes(warnings):
    return [w.split(":", 1)[0] for w in warnings]


def test_k1_break_with_gap_text():
    day = ps.day_presence([_e(time(8), time(18), unc=150)])
    assert day == ps.DayPresence(600, 450, 0, True)
    assert ps.daily_presence_warnings(day, break_check_passed=True) == [
        "PRESENCE_BREAK: §4 ArbZG: Durchgehend über die Lücke zwischen den Arbeitsblöcken "
        "gestempelt – eine Ruhepause ist nicht erfasst (10:00 h Anwesenheit). Die Lücke gilt "
        "nur dann als Pause, wenn sie tatsächlich frei war."
    ]


def test_k7_daily_and_break():
    day = ps.day_presence([_e(time(7, 45), time(18, 15), unc=150, raw_start=time(7), raw_end=time(19))])
    warnings = ps.daily_presence_warnings(day, break_check_passed=True)
    assert _codes(warnings) == ["PRESENCE_DAILY_HOURS", "PRESENCE_BREAK"]
    assert warnings[0] == (
        "PRESENCE_DAILY_HOURS: §3 ArbZG: Laut Stempel 12:00 h anwesend (abzüglich erfasster "
        "Pausen) – mehr als 10 Stunden. Angerechnet werden 8:00 h; die Höchstgrenze gilt für "
        "die tatsächliche Arbeitszeit."
    )


def test_k9_recorded_pause_too_short_k21_enough():
    k9 = ps.day_presence([_e(time(8), time(18), brk=30, unc=150)])
    assert k9.presence_minutes == 570 and k9.recorded_break_minutes == 30
    assert _codes(ps.daily_presence_warnings(k9, break_check_passed=True)) == ["PRESENCE_BREAK"]
    k21 = ps.day_presence([_e(time(8), time(18), brk=45, unc=150)])
    assert ps.daily_presence_warnings(k21, break_check_passed=True) == []


def test_k19_warns_although_credited_time_needs_no_break():
    day = ps.day_presence([_e(time(8), time(18), unc=270)])
    assert _codes(ps.daily_presence_warnings(day, break_check_passed=True)) == ["PRESENCE_BREAK"]


def test_hull_only_text():
    day = ps.day_presence([_e(time(8), time(13, 45), raw_start=time(6))])
    assert ps.daily_presence_warnings(day, break_check_passed=True) == [
        "PRESENCE_BREAK: §4 ArbZG: Laut Stempel 7:45 h anwesend ohne ausreichende erfasste "
        "Ruhepause; angerechnet werden nur 5:45 h. Die Pausenpflicht gilt für die tatsächliche "
        "Arbeitszeit."
    ]


def test_failed_or_waived_break_check_suppresses_presence_break():
    day = ps.day_presence([_e(time(8), time(18), unc=150)])
    assert ps.daily_presence_warnings(day, break_check_passed=False) == []


def test_hard_daily_limit_on_credited_time_suppresses_presence_daily():
    day = ps.day_presence([_e(time(7), time(18, 30))])     # angerechnet 11:30 h → harte §3 griff
    assert "PRESENCE_DAILY_HOURS" not in _codes(ps.daily_presence_warnings(day, break_check_passed=True))


def test_auto_closed_presence_ends_at_the_effective_end():
    """P18: 23:59 ist kein Stempel — mit 23:59 wären es 14:59 h + 1 h Anwesenheit."""
    auto = _e(time(10), time(18, 15), raw_end=time(23, 59), auto=True)
    later = _e(time(19), time(20))
    day = ps.day_presence([auto, later])
    assert day.presence_minutes == 495 + 60
    assert "PRESENCE_DAILY_HOURS" not in _codes(ps.daily_presence_warnings(day, break_check_passed=True))


# Review Focus 1: ohne Kappung ist Anwesenheit = Anrechnung — keine Zusatzwarnung.
def test_regular_days_without_blocks_never_warn():
    for entries in (
        [_e(time(8), time(17), brk=45)],
        [_e(time(8), time(12)), _e(time(12, 30), time(17))],
        [_e(time(8), time(14, 30), brk=30)],
    ):
        day = ps.day_presence(entries)
        assert ps.daily_presence_warnings(day, break_check_passed=True) == [], entries


def test_gap_between_entries_counts_as_recorded_break_overlap_does_not():
    assert ps.day_presence([_e(time(8), time(12)), _e(time(12, 30), time(17))]).recorded_break_minutes == 30
    overlap = ps.day_presence([_e(time(8), time(12)), _e(time(11), time(13))])
    assert overlap.recorded_break_minutes == 0


def test_weekly_presence():
    clamped = [_e(time(8), time(18), unc=150) for _ in range(5)]
    assert ps.weekly_presence_warning(clamped) == (
        "PRESENCE_WEEKLY_HOURS: §3 ArbZG: Laut Stempel 50:00 h in dieser Woche anwesend "
        "(abzüglich erfasster Pausen) – mehr als 48 Stunden. Angerechnet werden 37:30 h; "
        "die Grenze gilt für die tatsächliche Arbeitszeit."
    )
    # angerechnet selbst > 48 h → WEEKLY_HOURS_WARNING kam schon (P22)
    assert ps.weekly_presence_warning([_e(time(8), time(18)) for _ in range(5)]) is None


def test_break_in_gap():
    assert ps.break_in_gap_warning(_e(time(8), time(18), brk=30, unc=150)) == (
        "BREAK_IN_GAP: Pause in der Lücke wird zusätzlich abgezogen: 30 Min Pause und 2:30 h "
        "nicht angerechnet zwischen den Arbeitsblöcken. Lag die Pause in der Lücke, bitte die "
        "Pause auf 0 setzen."
    )
    assert ps.break_in_gap_warning(_e(time(8), time(18), unc=150)) is None
    assert ps.break_in_gap_warning(_e(time(7, 45), time(16), brk=30, raw_start=time(7))) is None


def test_presence_warnings_reads_the_day_and_week_from_the_db(db, test_user):
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    db.add(other)
    k9 = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON,
                   start_time=time(8), end_time=time(18), break_minutes=30, uncredited_minutes=150)
    db.add(k9)
    # F-026: fremder Mandant — gezählt ergäbe das 11:00 h Anwesenheit (PRESENCE_DAILY).
    db.add(TimeEntry(tenant_id=other.id, user_id=test_user.id, date=MON,
                     start_time=time(19), end_time=time(20, 30), break_minutes=0))
    db.commit()
    warnings = ps.presence_warnings(db, test_user, MON, break_check_passed=True, entry=k9)
    assert _codes(warnings) == ["BREAK_IN_GAP", "PRESENCE_BREAK"]
    test_user.exempt_from_arbzg = True
    assert ps.presence_warnings(db, test_user, MON, break_check_passed=True, entry=k9) == []


def test_presence_warnings_week(db, test_user):
    for i in range(5):
        db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=MON + timedelta(days=i),
                         start_time=time(8), end_time=time(18), break_minutes=0, uncredited_minutes=150))
    db.commit()
    codes = _codes(ps.presence_warnings(db, test_user, MON + timedelta(days=4), break_check_passed=True))
    assert codes == ["PRESENCE_BREAK", "PRESENCE_WEEKLY_HOURS"]
