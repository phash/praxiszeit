"""Tests für ArbZG §4 Pausenvalidierung."""
import pytest
from datetime import date, time
from app.models import TimeEntry
from app.services.break_validation_service import validate_daily_break


def make_entry(db, user, start_h, start_m, end_h, end_m, break_min=0, d=None):
    """Helper: Zeiteintrag erstellen und committen."""
    entry = TimeEntry(
        user_id=user.id,
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
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(14, 0), break_minutes=0)
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
    make_entry(db, test_user, 8, 0, 12, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(13, 0), time(16, 1), break_minutes=0)
    assert result is None  # 60min gap > 30min needed


def test_gap_not_sufficient_for_long_day(db, test_user):
    make_entry(db, test_user, 8, 0, 12, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(12, 20), time(17, 41), break_minutes=0)
    assert result is not None
    assert "45 Minuten" in result


def test_multiple_entries_cumulated(db, test_user):
    make_entry(db, test_user, 8, 0, 10, 0, break_min=0)
    make_entry(db, test_user, 10, 0, 12, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(12, 0), time(14, 1), break_minutes=0)
    assert result is not None


def test_exclude_entry_id_skips_existing(db, test_user):
    existing = make_entry(db, test_user, 8, 0, 16, 0, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(14, 0), break_minutes=0, exclude_entry_id=existing.id)
    assert result is None


def test_without_exclude_old_entry_counted(db, test_user):
    # Existing entry: 8:00-14:01 (361min net). New entry starts 14:30 (only 29min gap).
    # Without exclude: net=361+30=391 > 360, effective_break=29 < 30 → violation.
    make_entry(db, test_user, 8, 0, 14, 1, break_min=0)
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(14, 30), time(15, 0), break_minutes=0)
    assert result is not None


def test_open_entry_without_end_time_ignored(db, test_user):
    entry = TimeEntry(user_id=test_user.id, date=date(2026, 3, 10), start_time=time(8, 0), end_time=None, break_minutes=0)
    db.add(entry)
    db.commit()
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(14, 1), break_minutes=0)
    assert result is not None


def test_different_dates_independent(db, test_user):
    make_entry(db, test_user, 8, 0, 14, 1, break_min=0, d=date(2026, 3, 9))
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(13, 0), break_minutes=0)
    assert result is None


def test_zero_net_hours_no_error(db, test_user):
    result = validate_daily_break(db, test_user.id, date(2026, 3, 10), time(8, 0), time(8, 0), break_minutes=0)
    assert result is None
