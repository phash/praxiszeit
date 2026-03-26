"""Tests für ArbZG §4 Pausenvalidierung."""
import pytest
from datetime import date, time
from app.models import TimeEntry
from app.services.break_validation_service import validate_daily_break
from tests.conftest import DEFAULT_TENANT_ID


def _make_entry(db, user, start_h, start_m, end_h, end_m, break_min=0, d=None):
    """Helper: Zeiteintrag erstellen und committen."""
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d or date(2026, 3, 10),
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_under_6h_no_break_required(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(13, 59), break_minutes=0)
    assert result is None


def test_exactly_6h_no_break_required(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(14, 0), break_minutes=0)
    assert result is None


def test_over_6h_without_break_fails(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(14, 31), break_minutes=0)
    assert result is not None
    assert "30 Minuten" in result


def test_over_6h_with_30min_break_ok(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(14, 31), break_minutes=30)
    assert result is None


def test_over_9h_with_30min_break_fails(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(17, 31), break_minutes=30)
    assert result is not None
    assert "45 Minuten" in result


def test_over_9h_with_45min_break_ok(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(17, 31), break_minutes=45)
    assert result is None


def test_exactly_9h_needs_only_30min(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(17, 0), break_minutes=30)
    assert result is None


def test_gap_between_entries_counts_as_break(db, test_user):
    _make_entry(db, test_user, 8, 0, 12, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(13, 0), time(16, 1), break_minutes=0)
    assert result is None  # 60min gap > 30min needed


def test_gap_not_sufficient_for_long_day(db, test_user):
    _make_entry(db, test_user, 8, 0, 12, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(12, 20), time(17, 41), break_minutes=0)
    assert result is not None
    assert "45 Minuten" in result


def test_multiple_entries_cumulated(db, test_user):
    _make_entry(db, test_user, 8, 0, 10, 0, break_min=0)
    _make_entry(db, test_user, 10, 0, 12, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(12, 0), time(14, 1), break_minutes=0)
    assert result is not None
    assert "30 Minuten" in result


def test_exclude_entry_id_skips_existing(db, test_user):
    existing = _make_entry(db, test_user, 8, 0, 16, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(14, 0), break_minutes=0, exclude_entry_id=existing.id)
    assert result is None


def test_without_exclude_old_entry_counted(db, test_user):
    # Existing entry: 8:00-14:01 (361min net). New entry starts 14:30 (only 29min gap).
    # Without exclude: net=361+30=391 > 360, effective_break=29 < 30 → violation.
    _make_entry(db, test_user, 8, 0, 14, 1, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(14, 30), time(15, 0), break_minutes=0)
    assert result is not None


def test_open_entry_without_end_time_ignored(db, test_user):
    """Open entries (end_time=None) are ignored when counting work time."""
    # Open clock-in entry - should NOT count toward work time
    open_entry = TimeEntry(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=date(2026, 3, 10),
        start_time=time(6, 0),
        end_time=None,  # Open!
        break_minutes=0,
    )
    db.add(open_entry)
    db.commit()
    # New entry alone: only 5 hours (under 6h threshold)
    # If open entry were counted: 7h total → would require 30min break
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(13, 0), break_minutes=0
    )
    assert result is None  # Open entry correctly ignored


def test_different_dates_independent(db, test_user):
    _make_entry(db, test_user, 8, 0, 14, 1, break_min=0, d=date(2026, 3, 9))
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(13, 0), break_minutes=0)
    assert result is None


def test_zero_net_hours_no_error(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(8, 0), break_minutes=0)
    assert result is None


def test_gap_under_15min_not_counted_as_break(db, test_user):
    """§4 Satz 2 ArbZG: Pausenabschnitte unter 15 Min zählen nicht."""
    # 08:00-11:00 (3h) + 5min gap + 11:05-14:10 (3h05m) = 6h05m net, only 5min gap
    _make_entry(db, test_user, 8, 0, 11, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(11, 5), time(14, 10), break_minutes=0)
    assert result is not None
    assert "30 Minuten" in result


def test_gap_exactly_15min_counts_as_break(db, test_user):
    """§4 Satz 2 ArbZG: 15 Min Pause ist der Mindestwert — zählt."""
    # 08:00-11:00 (3h) + 15min gap + 11:15-14:16 (3h01m) = 6h01m net, 15min gap
    _make_entry(db, test_user, 8, 0, 11, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(11, 15), time(14, 16), break_minutes=15)
    assert result is None  # 15min gap + 15min declared = 30min >= 30min


def test_six_5min_gaps_not_valid_break(db, test_user):
    """§4 Satz 2: 6×5min = 30min Summe, aber kein Abschnitt >= 15min → keine gültige Pause."""
    # 5 entries × ~75min + new entry = ~6h25m gross, five 5-min gaps = 25min (none >= 15min)
    _make_entry(db, test_user, 8, 0, 9, 15, break_min=0)   # 75min
    _make_entry(db, test_user, 9, 20, 10, 35, break_min=0)  # 75min
    _make_entry(db, test_user, 10, 40, 11, 55, break_min=0) # 75min
    _make_entry(db, test_user, 12, 0, 13, 15, break_min=0)  # 75min
    _make_entry(db, test_user, 13, 20, 14, 35, break_min=0) # 75min
    # New entry: 14:40-15:07 → total gross = 75×5+27 = 402min, net = 402 > 360
    # Gaps: 5+5+5+5+5 = 25min total, but none >= 15min → effective break = 0
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(14, 40), time(15, 7), break_minutes=0)
    assert result is not None
    assert "30 Minuten" in result


def test_two_15min_gaps_valid_break(db, test_user):
    """§4 Satz 2: 2×15min = 30min, jeder Abschnitt >= 15min → gültig."""
    _make_entry(db, test_user, 8, 0, 10, 30, break_min=0)
    _make_entry(db, test_user, 10, 45, 13, 15, break_min=0)
    # New entry: 13:30-14:31 → total net = 6h31m, two 15-min gaps = 30min
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(13, 30), time(14, 31), break_minutes=0)
    assert result is None
