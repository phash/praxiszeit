"""
Service for calculating rest time violations between work shifts.

German law requires minimum 11 hours of rest between two working days.
"""
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.models import User, TimeEntry
from app.config import settings


DEFAULT_MIN_REST_HOURS = 11  # German law default


def get_min_rest_hours() -> float:
    """Get configured minimum rest time in hours."""
    return getattr(settings, 'MIN_REST_HOURS', DEFAULT_MIN_REST_HOURS)


def check_rest_time_violations(
    db: Session,
    user: User,
    year: int,
    month: Optional[int] = None,
    min_rest_hours: Optional[float] = None
) -> List[Dict]:
    """
    Check for rest time violations for a user.

    A violation occurs when the time between the end of the last entry
    of one work day and the start of the first entry of the next work day
    is less than min_rest_hours. Split shifts (multiple entries on the same
    day) are correctly handled by grouping entries by date first.

    Args:
        db: Database session
        user: User to check
        year: Year to check
        month: Optional month to check (None = full year)
        min_rest_hours: Minimum required rest hours (default: 11)

    Returns:
        List of violation dicts with date info and actual rest hours
    """
    if min_rest_hours is None:
        min_rest_hours = get_min_rest_hours()

    # Build query
    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.end_time.isnot(None)
    )

    from sqlalchemy import extract
    query = query.filter(extract('year', TimeEntry.date) == year)
    if month:
        query = query.filter(extract('month', TimeEntry.date) == month)

    entries = query.order_by(TimeEntry.date, TimeEntry.start_time).all()

    # Group entries by date: find the last end_time and first start_time per day.
    # This correctly handles split shifts (e.g. 08:00-12:00 + 14:00-18:00)
    # by not treating the intra-day gap as a rest-time violation.
    day_last_end: Dict = {}
    day_first_start: Dict = {}
    for entry in entries:
        if not entry.end_time or not entry.start_time:
            continue
        d = entry.date
        if d not in day_last_end or entry.end_time > day_last_end[d]:
            day_last_end[d] = entry.end_time
        if d not in day_first_start or entry.start_time < day_first_start[d]:
            day_first_start[d] = entry.start_time

    # Check rest time between consecutive days that have entries
    sorted_days = sorted(day_last_end.keys())
    violations = []

    for i in range(1, len(sorted_days)):
        prev_date = sorted_days[i - 1]
        curr_date = sorted_days[i]

        prev_end = datetime.combine(prev_date, day_last_end[prev_date])
        curr_start = datetime.combine(curr_date, day_first_start[curr_date])

        rest_hours = (curr_start - prev_end).total_seconds() / 3600

        if rest_hours < min_rest_hours:
            violations.append({
                "day1_date": str(prev_date),
                "day1_end": str(day_last_end[prev_date]),
                "day2_date": str(curr_date),
                "day2_start": str(day_first_start[curr_date]),
                "actual_rest_hours": round(rest_hours, 2),
                "min_rest_hours": min_rest_hours,
                "deficit_hours": round(min_rest_hours - rest_hours, 2),
            })

    return violations


def check_all_users_violations(
    db: Session,
    year: int,
    month: Optional[int] = None,
    min_rest_hours: Optional[float] = None
) -> List[Dict]:
    """
    Check rest time violations for all active employees.

    Returns list of violations grouped by employee.
    """
    from app.models import UserRole
    users = db.query(User).filter(User.is_active == True).all()

    all_violations = []
    for user in users:
        violations = check_rest_time_violations(db, user, year, month, min_rest_hours)
        if violations:
            all_violations.append({
                "user_id": str(user.id),
                "first_name": user.first_name,
                "last_name": user.last_name,
                "violations": violations,
                "violation_count": len(violations),
            })

    return all_violations
