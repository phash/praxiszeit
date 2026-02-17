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

    A violation occurs when the time between the end of one work day
    and the start of the next work day is less than min_rest_hours.

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

    entries = query.order_by(TimeEntry.date, TimeEntry.end_time).all()

    violations = []

    for i in range(1, len(entries)):
        prev = entries[i - 1]
        curr = entries[i]

        # Only compare consecutive days (skip gaps)
        if not prev.end_time or not curr.start_time:
            continue

        prev_end = datetime.combine(prev.date, prev.end_time)
        curr_start = datetime.combine(curr.date, curr.start_time)

        rest_duration = curr_start - prev_end
        rest_hours = rest_duration.total_seconds() / 3600

        if rest_hours < min_rest_hours:
            violations.append({
                "day1_date": str(prev.date),
                "day1_end": str(prev.end_time),
                "day2_date": str(curr.date),
                "day2_start": str(curr.start_time),
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
