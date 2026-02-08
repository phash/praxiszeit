from datetime import date, datetime
from decimal import Decimal
from calendar import monthrange
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType, WorkingHoursChange


def get_weekly_hours_for_date(db: Session, user: User, target_date: date) -> Decimal:
    """
    Get the weekly hours that were valid for a specific date.
    Considers historical working hours changes.

    Args:
        db: Database session
        user: User object
        target_date: Date to get hours for

    Returns:
        Weekly hours as Decimal
    """
    # Find the most recent working hours change before or on target_date
    change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.effective_from <= target_date
    ).order_by(WorkingHoursChange.effective_from.desc()).first()

    if change:
        return Decimal(str(change.weekly_hours))

    # No historical change found, use current user value
    return Decimal(str(user.weekly_hours))


def get_daily_target(user: User, weekly_hours: Decimal = None) -> Decimal:
    """
    Calculate daily target hours based on weekly hours.
    Assumes 5-day work week.

    Args:
        user: User object
        weekly_hours: Optional weekly hours to use (if None, uses user.weekly_hours)

    Returns:
        Daily target hours as Decimal (0 if track_hours is False)
    """
    if not user.track_hours:
        return Decimal('0')

    if weekly_hours is None:
        weekly_hours = Decimal(str(user.weekly_hours))

    return weekly_hours / Decimal('5')


def get_working_days_in_month(db: Session, year: int, month: int) -> int:
    """
    Calculate number of working days (Mon-Fri) in a month.
    Excludes weekends but does NOT exclude holidays or absences.

    Args:
        db: Database session (unused, kept for consistency)
        year: Year
        month: Month (1-12)

    Returns:
        Number of working days (weekdays)
    """
    _, last_day = monthrange(year, month)
    working_days = 0

    for day in range(1, last_day + 1):
        d = date(year, month, day)
        # Count only weekdays (Mon-Fri)
        if d.weekday() < 5:
            working_days += 1

    return working_days


def get_monthly_target(db: Session, user: User, year: int, month: int) -> Decimal:
    """
    Calculate monthly target hours.

    Formula:
    For each weekday (Mon-Fri) in month:
        - Skip public holidays
        - Skip absence days
        - Add daily target (based on weekly hours valid for that date)

    IMPORTANT: Absences REDUCE the target, because the employee
    doesn't need to work on those days.

    This function now considers historical working hours changes,
    so if hours changed mid-month, both values are used correctly.

    Args:
        db: Database session
        user: User object
        year: Year
        month: Month (1-12)

    Returns:
        Monthly target hours as Decimal (0 if track_hours is False)
    """
    if not user.track_hours:
        return Decimal('0')

    # Get holidays and absences for the month
    holidays = db.query(PublicHoliday).filter(
        extract('year', PublicHoliday.date) == year,
        extract('month', PublicHoliday.date) == month
    ).all()
    holiday_dates = {h.date for h in holidays}

    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        extract('year', Absence.date) == year,
        extract('month', Absence.date) == month
    ).all()
    absence_dates = {a.date for a in absences}

    # Calculate target by iterating through each day
    _, last_day = monthrange(year, month)
    monthly_target = Decimal('0')

    for day in range(1, last_day + 1):
        d = date(year, month, day)

        # Skip weekends
        if d.weekday() >= 5:  # Saturday or Sunday
            continue

        # Skip holidays and absences
        if d in holiday_dates or d in absence_dates:
            continue

        # Get weekly hours valid for this specific date
        weekly_hours = get_weekly_hours_for_date(db, user, d)
        daily_target = get_daily_target(user, weekly_hours)

        monthly_target += daily_target

    return monthly_target.quantize(Decimal('0.01'))


def get_monthly_actual(db: Session, user: User, year: int, month: int) -> Decimal:
    """
    Calculate actual hours worked in a month.
    Sum of all net_hours from TimeEntry records.

    Args:
        db: Database session
        user: User object
        year: Year
        month: Month (1-12)

    Returns:
        Actual hours worked as Decimal
    """
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract('year', TimeEntry.date) == year,
        extract('month', TimeEntry.date) == month
    ).all()

    total = sum(entry.net_hours for entry in entries)

    return Decimal(str(total)).quantize(Decimal('0.01'))


def get_monthly_balance(db: Session, user: User, year: int, month: int) -> Decimal:
    """
    Calculate monthly balance (Actual - Target).

    Args:
        db: Database session
        user: User object
        year: Year
        month: Month (1-12)

    Returns:
        Monthly balance as Decimal (positive = overtime, negative = deficit)
    """
    target = get_monthly_target(db, user, year, month)
    actual = get_monthly_actual(db, user, year, month)

    balance = actual - target

    return balance.quantize(Decimal('0.01'))


def get_overtime_account(db: Session, user: User, up_to_year: int, up_to_month: int) -> Decimal:
    """
    Calculate cumulative overtime account from employment start up to specified month.
    This is the sum of all monthly balances.

    Args:
        db: Database session
        user: User object
        up_to_year: Year to calculate up to (inclusive)
        up_to_month: Month to calculate up to (inclusive)

    Returns:
        Cumulative overtime as Decimal
    """
    # Get the first time entry to determine employment start
    first_entry = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id
    ).order_by(TimeEntry.date).first()

    if not first_entry:
        return Decimal('0.00')

    start_year = first_entry.date.year
    start_month = first_entry.date.month

    total_balance = Decimal('0.00')

    # Iterate through all months from start to target month
    current_year = start_year
    current_month = start_month

    while (current_year < up_to_year) or (current_year == up_to_year and current_month <= up_to_month):
        balance = get_monthly_balance(db, user, current_year, current_month)
        total_balance += balance

        # Move to next month
        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1

    return total_balance.quantize(Decimal('0.01'))


def get_vacation_account(db: Session, user: User, year: int) -> Dict:
    """
    Calculate vacation account for a given year.

    Returns:
        budget_hours: Total vacation budget in hours (vacation_days × daily_target)
        budget_days: Total vacation days from user config
        used_hours: Hours of vacation taken
        used_days: Days of vacation taken (used_hours / daily_target)
        remaining_hours: Remaining vacation hours
        remaining_days: Remaining vacation days

    NOTE: Uses CURRENT weekly hours for conversion between days and hours.
    This ensures consistent display even if hours changed during the year.

    Args:
        db: Database session
        user: User object
        year: Year to calculate for

    Returns:
        Dict with vacation account details
    """
    # Use current weekly hours for conversion
    daily_target = get_daily_target(user)

    # Calculate budget in hours
    budget_days = user.vacation_days
    budget_hours = Decimal(str(budget_days)) * daily_target

    # Calculate used vacation hours
    vacation_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.type == AbsenceType.VACATION,
        extract('year', Absence.date) == year
    ).all()

    used_hours = sum((Decimal(str(a.hours)) for a in vacation_absences), start=Decimal('0'))
    used_days = used_hours / daily_target if daily_target > 0 else Decimal('0')

    # Calculate remaining
    remaining_hours = budget_hours - used_hours
    remaining_days = remaining_hours / daily_target if daily_target > 0 else Decimal('0')

    return {
        "budget_hours": budget_hours.quantize(Decimal('0.01')),
        "budget_days": budget_days,
        "used_hours": used_hours.quantize(Decimal('0.01')),
        "used_days": used_days.quantize(Decimal('0.1')),
        "remaining_hours": remaining_hours.quantize(Decimal('0.01')),
        "remaining_days": remaining_days.quantize(Decimal('0.1'))
    }
