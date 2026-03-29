"""Tests for year closing (Jahresabschluss) creation and deletion."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import User, UserRole, TimeEntry, Absence, AbsenceType, YearCarryover
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_user(db, username, weekly_hours=40.0, vacation_days=30):
    """Helper to create a test user with track_hours=True."""
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash="hash",
        first_name=username.capitalize(),
        last_name="Test",
        role=UserRole.EMPLOYEE,
        weekly_hours=weekly_hours,
        vacation_days=vacation_days,
        work_days_per_week=5,
        is_active=True,
        track_hours=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_time_entry(db, user, entry_date, start_h, end_h, break_min=0):
    """Helper to create a time entry."""
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=entry_date,
        start_time=time(start_h, 0),
        end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    return entry


def _make_carryover(db, user, year, overtime_hours=0.0, vacation_days=0.0):
    """Helper to create a YearCarryover record."""
    carryover = YearCarryover(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        year=year,
        overtime_hours=overtime_hours,
        vacation_days=vacation_days,
    )
    db.add(carryover)
    db.commit()
    return carryover


# --- create_year_closing tests ---


def test_create_year_closing_creates_carryovers(db, default_tenant):
    """Year closing creates carryover records for next year."""
    user = _make_user(db, "alice")

    results = calculation_service.create_year_closing(db, 2025, [user])

    assert len(results) == 1
    assert results[0]["user_id"] == str(user.id)

    # Carryover should exist for 2026
    carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year == 2026,
    ).first()
    assert carryover is not None


def test_create_year_closing_multiple_users(db, default_tenant):
    """Year closing processes all users."""
    users = [_make_user(db, f"user{i}") for i in range(3)]

    results = calculation_service.create_year_closing(db, 2025, users)

    assert len(results) == 3
    carryovers = db.query(YearCarryover).filter(
        YearCarryover.year == 2026,
    ).all()
    assert len(carryovers) == 3


def test_create_year_closing_overwrites_existing(db, default_tenant):
    """Year closing updates existing carryover records."""
    user = _make_user(db, "bob")
    _make_carryover(db, user, year=2026, overtime_hours=99.0, vacation_days=99.0)

    calculation_service.create_year_closing(db, 2025, [user])

    carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year == 2026,
    ).first()
    # Should have been recalculated, not 99.0 anymore
    assert carryover is not None
    assert float(carryover.overtime_hours) != 99.0


def test_create_year_closing_with_overtime(db, default_tenant):
    """Year closing captures overtime balance correctly."""
    user = _make_user(db, "carol", weekly_hours=40.0)

    # Add some time entries in Dec 2025 to create overtime
    # Dec 1, 2025 is a Monday
    for day in range(1, 6):  # Mon-Fri first week
        _make_time_entry(db, user, date(2025, 12, day), 8, 18)  # 10h/day, 2h overtime each

    results = calculation_service.create_year_closing(db, 2025, [user])

    # Should have some overtime (exact value depends on full year calc)
    assert results[0]["overtime_hours"] != 0.0


# --- delete year closing tests ---


def test_delete_carryovers_for_year(db, default_tenant):
    """Deleting year closing removes all carryovers for the next year."""
    users = [_make_user(db, f"del_user{i}") for i in range(3)]
    for user in users:
        _make_carryover(db, user, year=2026, overtime_hours=10.0, vacation_days=5.0)

    # Verify they exist
    count_before = db.query(YearCarryover).filter(YearCarryover.year == 2026).count()
    assert count_before == 3

    # Delete all carryovers for year 2026 (= undo closing of 2025)
    deleted = db.query(YearCarryover).filter(YearCarryover.year == 2026).delete()
    db.commit()

    assert deleted == 3
    count_after = db.query(YearCarryover).filter(YearCarryover.year == 2026).count()
    assert count_after == 0


def test_delete_does_not_affect_other_years(db, default_tenant):
    """Deleting carryovers for one year does not affect other years."""
    user = _make_user(db, "keep_user")
    _make_carryover(db, user, year=2025, overtime_hours=5.0, vacation_days=2.0)
    _make_carryover(db, user, year=2026, overtime_hours=10.0, vacation_days=4.0)
    _make_carryover(db, user, year=2027, overtime_hours=15.0, vacation_days=6.0)

    # Delete only 2026
    db.query(YearCarryover).filter(YearCarryover.year == 2026).delete()
    db.commit()

    remaining = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
    ).order_by(YearCarryover.year).all()

    assert len(remaining) == 2
    assert remaining[0].year == 2025
    assert remaining[1].year == 2027


def test_delete_nonexistent_year_returns_zero(db, default_tenant):
    """Deleting carryovers for a year with no records returns 0."""
    deleted = db.query(YearCarryover).filter(YearCarryover.year == 2099).delete()
    db.commit()
    assert deleted == 0


def test_create_then_delete_roundtrip(db, default_tenant):
    """Full roundtrip: create year closing, then delete it."""
    users = [_make_user(db, f"rt_user{i}") for i in range(2)]

    # Create year closing for 2025 → carryovers for 2026
    results = calculation_service.create_year_closing(db, 2025, users)
    assert len(results) == 2

    carryovers = db.query(YearCarryover).filter(YearCarryover.year == 2026).all()
    assert len(carryovers) == 2

    # Delete year closing (remove carryovers for 2026)
    deleted = db.query(YearCarryover).filter(YearCarryover.year == 2026).delete()
    db.commit()

    assert deleted == 2
    remaining = db.query(YearCarryover).filter(YearCarryover.year == 2026).count()
    assert remaining == 0


def test_delete_preserves_manually_added_other_years(db, default_tenant):
    """Deleting year closing for 2025 only touches 2026 carryovers, not manual 2025 entries."""
    user = _make_user(db, "manual_user")

    # Manual carryover for 2025 (entered by admin for that year)
    _make_carryover(db, user, year=2025, overtime_hours=3.0, vacation_days=1.0)

    # Year closing for 2025 creates carryover for 2026
    calculation_service.create_year_closing(db, 2025, [user])

    # Delete year closing (2026 carryovers)
    db.query(YearCarryover).filter(YearCarryover.year == 2026).delete()
    db.commit()

    # 2025 manual carryover should still exist
    manual = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year == 2025,
    ).first()
    assert manual is not None
    assert float(manual.overtime_hours) == 3.0
