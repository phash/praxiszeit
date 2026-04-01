from datetime import date, datetime, timedelta
from app.services.timezone_service import today_local
from decimal import Decimal
from calendar import monthrange
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType, WorkingHoursChange, YearCarryover


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
    Calculate daily target hours based on weekly hours and work days.

    Formula: weekly_hours / work_days_per_week

    Examples:
    - 20h at 2 days → 10h/day
    - 20h at 5 days → 4h/day
    - 40h at 5 days → 8h/day

    NOTE: Does NOT consider per-day schedule. Use get_daily_target_for_date()
    for date-aware calculations.

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

    # Use work_days_per_week instead of hardcoded 5
    work_days = Decimal(str(user.work_days_per_week))

    if work_days == 0:  # Safety check
        return Decimal('0')

    return (weekly_hours / work_days).quantize(Decimal('0.01'))


def get_daily_target_for_date(user: User, target_date: date, weekly_hours: Decimal = None) -> Decimal:
    """
    Calculate daily target hours for a specific date.

    If user has use_daily_schedule=True, returns the hours configured
    for that specific weekday (Mon–Fri). Weekends always return 0.

    If use_daily_schedule=False, falls back to get_daily_target().

    Args:
        user: User object
        target_date: The specific date
        weekly_hours: Optional weekly hours override (used when use_daily_schedule=False)

    Returns:
        Daily target hours as Decimal
    """
    if not user.track_hours:
        return Decimal('0')

    weekday = target_date.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

    if weekday >= 5:
        return Decimal('0')

    if getattr(user, 'use_daily_schedule', False):
        day_columns = [
            user.hours_monday,
            user.hours_tuesday,
            user.hours_wednesday,
            user.hours_thursday,
            user.hours_friday,
        ]
        day_hours = day_columns[weekday]
        if day_hours is None:
            return Decimal('0')
        return Decimal(str(day_hours)).quantize(Decimal('0.01'))

    return get_daily_target(user, weekly_hours)


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

    # Exclude TRAINING, SICK, and OVERTIME from target reduction:
    # - TRAINING counts as worked time (außer Haus)
    # - SICK: §3 EntgFG - employee must be credited as if they worked the planned hours
    # - OVERTIME: Überstundenausgleich – Soll bleibt bestehen, Tag zählt als 0h Ist,
    #   dadurch reduziert sich das Überstundenkonto um die geplanten Stunden
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        extract('year', Absence.date) == year,
        extract('month', Absence.date) == month,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME])
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
        daily_target = get_daily_target_for_date(user, d, weekly_hours)

        monthly_target += daily_target

    return monthly_target.quantize(Decimal('0.01'))


def get_monthly_actual(db: Session, user: User, year: int, month: int) -> Decimal:
    """
    Calculate actual hours worked in a month.
    Sum of all net_hours from TimeEntry records + credited absence hours.

    Training (Fortbildung) and sick-leave (Kranktage) hours count as worked time:
    - Training: employee is absent but credited for the planned hours.
    - Sick: §3 EntgFG – employee must be credited as if they worked the planned hours.

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

    # Training and sick hours count as actual worked hours:
    # - TRAINING: außer Haus, credited as worked
    # - SICK: §3 EntgFG - credited as if the planned hours were worked
    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
        extract('year', Absence.date) == year,
        extract('month', Absence.date) == month,
    ).all()
    credited_hours = sum((Decimal(str(a.hours)) for a in credited_absences), Decimal('0'))

    return (Decimal(str(total)) + credited_hours).quantize(Decimal('0.01'))


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
    Calculate cumulative overtime account up to specified month.

    If a YearCarryover exists, uses it as the starting balance and only
    iterates months from that year forward (avoids double-counting).
    Otherwise falls back to calculating from the first time entry.

    Args:
        db: Database session
        user: User object
        up_to_year: Year to calculate up to (inclusive)
        up_to_month: Month to calculate up to (inclusive)

    Returns:
        Cumulative overtime as Decimal
    """
    if not user.track_hours:
        return Decimal('0.00')

    up_to_date = date(up_to_year, up_to_month, monthrange(up_to_year, up_to_month)[1])

    # --- determine starting point ---
    # Find the most recent carryover at or before up_to_year
    latest_carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year <= up_to_year,
    ).order_by(YearCarryover.year.desc()).first()

    if latest_carryover:
        # Start from Jan of the carryover year with the carryover value
        start_year = latest_carryover.year
        start_month = 1
        initial_balance = Decimal(str(latest_carryover.overtime_hours))
        start_date = date(start_year, 1, 1)
    else:
        # No carryover: start from first time entry
        first_entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id
        ).order_by(TimeEntry.date).first()

        if not first_entry:
            return Decimal('0.00')

        start_year = first_entry.date.year
        start_month = first_entry.date.month
        initial_balance = Decimal('0.00')
        start_date = date(start_year, start_month, 1)

    # --- single-pass bulk fetches ---
    # All time entries in range (group by month in memory)
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start_date,
        TimeEntry.date <= up_to_date,
    ).all()
    actual_by_month: Dict[tuple, Decimal] = {}
    for e in entries:
        key = (e.date.year, e.date.month)
        actual_by_month[key] = actual_by_month.get(key, Decimal('0')) + Decimal(str(e.net_hours))

    # Training and sick hours count as actual worked hours (§3 EntgFG)
    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all()
    for ca in credited_absences:
        key = (ca.date.year, ca.date.month)
        actual_by_month[key] = actual_by_month.get(key, Decimal('0')) + Decimal(str(ca.hours))

    # All absences in range (exclude TRAINING, SICK, OVERTIME — same rule as get_monthly_target)
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    absence_dates: set[date] = {a.date for a in absences}

    # All public holidays in range
    holidays = db.query(PublicHoliday).filter(
        PublicHoliday.date >= start_date,
        PublicHoliday.date <= up_to_date,
    ).all()
    holiday_dates: set[date] = {h.date for h in holidays}

    # All working-hours changes for this user
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
    ).order_by(WorkingHoursChange.effective_from).all()

    def _weekly_hours_for_date(d: date) -> Decimal:
        """Return the weekly hours effective on date d (no DB query)."""
        result = Decimal(str(user.weekly_hours))
        for change in wh_changes:
            if change.effective_from <= d:
                result = Decimal(str(change.weekly_hours))
            else:
                break
        return result

    # --- iterate months and compute balance in memory ---
    total_balance = initial_balance
    current_year, current_month = start_year, start_month

    while (current_year < up_to_year) or (current_year == up_to_year and current_month <= up_to_month):
        key = (current_year, current_month)

        # Monthly target (mirrors get_monthly_target logic)
        _, last_day = monthrange(current_year, current_month)
        monthly_target = Decimal('0')
        for day in range(1, last_day + 1):
            d = date(current_year, current_month, day)
            if d.weekday() >= 5:
                continue
            if d in holiday_dates or d in absence_dates:
                continue
            weekly_hours = _weekly_hours_for_date(d)
            daily_target = get_daily_target_for_date(user, d, weekly_hours)
            monthly_target += daily_target

        monthly_actual = actual_by_month.get(key, Decimal('0'))
        total_balance += (monthly_actual - monthly_target)

        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1

    return total_balance.quantize(Decimal('0.01'))


def get_ytd_summary(db: Session, user: User, year: int = None) -> Dict:
    """
    Calculate year-to-date summary from Jan 1 to today.

    Sums daily targets and actual hours for all working days from Jan 1
    of the given year up to and including today.

    Args:
        db: Database session
        user: User object
        year: Year (default: current year)

    Returns:
        Dict with target_hours, actual_hours, overtime
    """
    if not user.track_hours:
        return {"target_hours": 0.0, "actual_hours": 0.0, "overtime": 0.0}

    today = today_local()
    if year is None:
        year = today.year

    # End date: today if current year, else Dec 31
    end = today if year == today.year else date(year, 12, 31)
    start = date(year, 1, 1)

    if start > end:
        return {"target_hours": 0.0, "actual_hours": 0.0, "overtime": 0.0}

    # Fetch holidays in range
    holidays = db.query(PublicHoliday).filter(
        PublicHoliday.date >= start,
        PublicHoliday.date <= end,
    ).all()
    holiday_dates: set = {h.date for h in holidays}

    # Fetch absences in range (exclude TRAINING, SICK, OVERTIME - same as get_monthly_target)
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start,
        Absence.date <= end,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    absence_dates: set = {a.date for a in absences}

    # Fetch working hours changes
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
    ).order_by(WorkingHoursChange.effective_from).all()

    def _weekly_hours_for_date(d: date) -> Decimal:
        result = Decimal(str(user.weekly_hours))
        for change in wh_changes:
            if change.effective_from <= d:
                result = Decimal(str(change.weekly_hours))
            else:
                break
        return result

    # Sum daily targets
    total_target = Decimal('0')
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holiday_dates and current not in absence_dates:
            weekly_hours = _weekly_hours_for_date(current)
            daily_target = get_daily_target_for_date(user, current, weekly_hours)
            total_target += daily_target
        current += timedelta(days=1)

    # Sum actual hours (time entries + credited absence hours: training + sick)
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start,
        TimeEntry.date <= end,
    ).all()
    total_actual = sum((Decimal(str(e.net_hours)) for e in entries), start=Decimal('0'))

    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start,
        Absence.date <= end,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all()
    total_actual += sum((Decimal(str(a.hours)) for a in credited_absences), start=Decimal('0'))

    # Include overtime carryover for this year
    carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year == year,
    ).first()
    carryover_hours = Decimal(str(carryover.overtime_hours)) if carryover else Decimal('0')

    overtime = total_actual - total_target + carryover_hours

    return {
        "target_hours": float(total_target.quantize(Decimal('0.01'))),
        "actual_hours": float(total_actual.quantize(Decimal('0.01'))),
        "overtime": float(overtime.quantize(Decimal('0.01'))),
        "carryover_hours": float(carryover_hours.quantize(Decimal('0.01'))),
    }


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

    # Calculate budget in hours, pro-rated for first/last work day
    budget_days = Decimal(str(user.vacation_days))
    if user.first_work_day and user.first_work_day.year == year:
        fwd = user.first_work_day
        days_in_month = monthrange(fwd.year, fwd.month)[1]
        days_remaining = days_in_month - fwd.day + 1  # inklusive Starttag
        # Vollständige Monate nach Startmonat + Anteil des Startmonats
        months_remaining = Decimal(str(12 - fwd.month)) + Decimal(str(days_remaining)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_remaining / Decimal('12')).quantize(Decimal('0.1'))
    if user.last_work_day and user.last_work_day.year == year:
        lwd = user.last_work_day
        days_in_month = monthrange(lwd.year, lwd.month)[1]
        days_worked = lwd.day  # inklusive letzten Tag
        # Vollständige Monate vor Endmonat + Anteil des Endmonats
        months_worked = Decimal(str(lwd.month - 1)) + Decimal(str(days_worked)) / Decimal(str(days_in_month))
        budget_days_last = (Decimal(str(user.vacation_days)) * months_worked / Decimal('12')).quantize(Decimal('0.1'))
        budget_days = min(budget_days, budget_days_last)
    # Add carryover vacation days from previous year
    carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year == year,
    ).first()
    carryover_days = Decimal(str(carryover.vacation_days)) if carryover else Decimal('0')
    budget_days += carryover_days

    budget_hours = budget_days * daily_target

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
        "budget_hours": float(budget_hours.quantize(Decimal('0.01'))),
        "budget_days": float(budget_days),
        "used_hours": float(used_hours.quantize(Decimal('0.01'))),
        "used_days": float(used_days.quantize(Decimal('0.1'))),
        "remaining_hours": float(remaining_hours.quantize(Decimal('0.01'))),
        "remaining_days": float(remaining_days.quantize(Decimal('0.1')))
    }


def count_workdays(db: Session, start: date, end: date) -> int:
    """Count weekdays (Mon-Fri) excluding public holidays between start and end (inclusive)."""
    years: set = set()
    cur = start
    while cur <= end:
        years.add(cur.year)
        cur += timedelta(days=1)

    holidays: set = set()
    for year in years:
        year_holidays = db.query(PublicHoliday).filter(PublicHoliday.year == year).all()
        holidays.update(h.date for h in year_holidays)

    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur not in holidays:
            count += 1
        cur += timedelta(days=1)
    return count


def create_year_closing(db: Session, year: int, users: list) -> list:
    """
    Create year-end closing for all given users.

    For each user, calculates the cumulative overtime balance at Dec 31
    and the remaining vacation days, then creates/updates a YearCarryover
    record for year+1.

    Args:
        db: Database session
        year: The year being closed (carryovers are created for year+1)
        users: List of User objects

    Returns:
        List of dicts with user info and carryover values
    """
    next_year = year + 1
    results = []

    for user in users:
        # Calculate overtime balance at end of year
        overtime_balance = get_overtime_account(db, user, year, 12)

        # Calculate remaining vacation days
        vacation_account = get_vacation_account(db, user, year)
        remaining_vacation = Decimal(str(vacation_account['remaining_days']))

        # Create or update carryover for next year
        carryover = db.query(YearCarryover).filter(
            YearCarryover.user_id == user.id,
            YearCarryover.year == next_year,
        ).first()

        if carryover:
            carryover.overtime_hours = overtime_balance
            carryover.vacation_days = remaining_vacation
        else:
            carryover = YearCarryover(
                user_id=user.id,
                tenant_id=user.tenant_id,
                year=next_year,
                overtime_hours=overtime_balance,
                vacation_days=remaining_vacation,
            )
            db.add(carryover)

        results.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "overtime_hours": float(overtime_balance),
            "vacation_days": float(remaining_vacation.quantize(Decimal('0.1'))),
        })

    db.commit()
    return results
