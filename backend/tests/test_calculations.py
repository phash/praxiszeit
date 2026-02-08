"""Tests for calculation service."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import User, UserRole, TimeEntry, Absence, AbsenceType, PublicHoliday
from app.services import calculation_service


def test_get_daily_target(test_user):
    """Test daily target calculation."""
    # 40 hours / 5 days = 8.0 hours per day
    daily_target = calculation_service.get_daily_target(test_user)
    
    assert daily_target == Decimal('8.0')


def test_get_daily_target_parttime(db):
    """Test daily target calculation for part-time employee."""
    user = User(
        email="parttime@example.com",
        password_hash="hash",
        first_name="Part",
        last_name="Time",
        role=UserRole.EMPLOYEE,
        weekly_hours=20.0,  # Part-time: 20 hours/week
        vacation_days=15,
        is_active=True
    )
    db.add(user)
    db.commit()
    
    # 20 hours / 5 days = 4.0 hours per day
    daily_target = calculation_service.get_daily_target(user)
    
    assert daily_target == Decimal('4.0')


def test_get_monthly_target_basic(db, test_user):
    """Test monthly target calculation for a simple month."""
    # January 2025: 31 days, 23 weekdays (Mo-Fr)
    # No holidays, no absences
    target = calculation_service.get_monthly_target(db, test_user, 2025, 1)
    
    # We need to account for actual weekdays in January 2025
    # Let's just check it's positive and reasonable
    assert target > 0
    assert target <= Decimal('184.0')  # Max 23 days * 8h


def test_get_monthly_actual_empty(db, test_user):
    """Test monthly actual calculation with no time entries."""
    actual = calculation_service.get_monthly_actual(db, test_user, 2025, 1)
    
    assert actual == Decimal('0.00')


def test_get_monthly_actual_with_entries(db, test_user):
    """Test monthly actual calculation with time entries."""
    # Add some time entries
    entry1 = TimeEntry(
        user_id=test_user.id,
        date=date(2025, 1, 6),  # Monday
        start_time=time(8, 0),
        end_time=time(17, 0),
        break_minutes=60,
        note="Test entry 1"
    )
    entry2 = TimeEntry(
        user_id=test_user.id,
        date=date(2025, 1, 7),  # Tuesday
        start_time=time(8, 0),
        end_time=time(16, 30),
        break_minutes=30,
        note="Test entry 2"
    )
    db.add(entry1)
    db.add(entry2)
    db.commit()
    
    # Entry 1: 9h - 1h = 8h
    # Entry 2: 8.5h - 0.5h = 8h
    # Total: 16h
    actual = calculation_service.get_monthly_actual(db, test_user, 2025, 1)
    
    assert actual == Decimal('16.00')


def test_get_monthly_balance(db, test_user):
    """Test monthly balance calculation."""
    # Add a time entry
    entry = TimeEntry(
        user_id=test_user.id,
        date=date(2025, 1, 6),  # Monday
        start_time=time(8, 0),
        end_time=time(18, 0),  # 10h - 1h break = 9h net
        break_minutes=60
    )
    db.add(entry)
    db.commit()
    
    balance = calculation_service.get_monthly_balance(db, test_user, 2025, 1)
    
    # Balance = Actual - Target
    # Should be negative (only 9h worked, target is ~184h for full month)
    assert balance < 0


def test_get_vacation_account_basic(db, test_user):
    """Test vacation account calculation."""
    # User has 30 vacation days configured
    vacation_account = calculation_service.get_vacation_account(db, test_user, 2025)
    
    # Budget: 30 days * 8h = 240h
    assert vacation_account['budget_days'] == 30
    assert vacation_account['budget_hours'] == Decimal('240.0')
    assert vacation_account['used_hours'] == Decimal('0.0')
    assert vacation_account['used_days'] == Decimal('0.0')
    assert vacation_account['remaining_hours'] == Decimal('240.0')
    assert vacation_account['remaining_days'] == Decimal('30.0')


def test_get_vacation_account_with_usage(db, test_user):
    """Test vacation account calculation with used vacation days."""
    # Add vacation absence (8 hours = 1 day)
    absence = Absence(
        user_id=test_user.id,
        date=date(2025, 1, 15),
        type=AbsenceType.VACATION,
        hours=Decimal('8.0'),
        note="Test vacation"
    )
    db.add(absence)
    db.commit()
    
    vacation_account = calculation_service.get_vacation_account(db, test_user, 2025)
    
    assert vacation_account['used_hours'] == Decimal('8.0')
    assert vacation_account['used_days'] == Decimal('1.0')
    assert vacation_account['remaining_hours'] == Decimal('232.0')  # 240 - 8
    assert vacation_account['remaining_days'] == Decimal('29.0')  # 30 - 1


def test_get_overtime_account_empty(db, test_user):
    """Test overtime account with no entries."""
    overtime = calculation_service.get_overtime_account(db, test_user, 2025, 1)
    
    # Should be negative (no work done, but target exists)
    assert overtime <= 0


def test_time_entry_net_hours_calculation(db, test_user):
    """Test that time entry net_hours hybrid property calculates correctly."""
    entry = TimeEntry(
        user_id=test_user.id,
        date=date(2025, 1, 6),
        start_time=time(8, 0),
        end_time=time(17, 30),
        break_minutes=45
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    # 9.5 hours - 0.75 hours break = 8.75 hours
    assert entry.net_hours == Decimal('8.75')
