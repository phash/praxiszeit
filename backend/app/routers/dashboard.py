from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import List, Optional
from app.database import get_db
from app.models import User, TimeEntry, UserRole
from app.models.absence import Absence
from app.middleware.auth import get_current_user
from app.schemas.reports import MonthlyDashboard, OvertimeAccount, OvertimeHistory, VacationAccount, YtdOvertime, MissingBookings, MissingBookingEntry
from app.services import calculation_service
from app.services.holiday_service import is_holiday
from sqlalchemy import extract, and_

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _get_missing_bookings_for_user(db: Session, user: User) -> List[MissingBookingEntry]:
    """Find open entries (end_time NULL) and workdays without any entry/absence."""
    today = date.today()
    entries: List[MissingBookingEntry] = []

    # 1) Open entries: end_time is NULL, date < today
    open_entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.end_time.is_(None),
        TimeEntry.date < today,
    ).order_by(TimeEntry.date).all()

    for te in open_entries:
        entries.append(MissingBookingEntry(
            date=te.date,
            type="open",
            start_time=te.start_time.strftime("%H:%M") if te.start_time else None,
        ))

    # 2) Workdays without any time entry or absence (current month only)
    first_of_month = today.replace(day=1)
    # Respect first_work_day
    start_date = max(first_of_month, user.first_work_day) if user.first_work_day else first_of_month
    # Respect last_work_day
    end_date = min(today - timedelta(days=1), user.last_work_day) if user.last_work_day and user.last_work_day < today else today - timedelta(days=1)

    if start_date > end_date:
        return entries

    # Get all dates with time entries this month
    entry_dates = set(
        row[0] for row in db.query(TimeEntry.date).filter(
            TimeEntry.user_id == user.id,
            TimeEntry.date >= start_date,
            TimeEntry.date <= end_date,
        ).all()
    )

    # Get all dates with absences this month
    absence_dates = set()
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date <= end_date,
    ).all()
    for absence in absences:
        a_end = absence.end_date or absence.date
        d = max(absence.date, start_date)
        while d <= min(a_end, end_date):
            absence_dates.add(d)
            d += timedelta(days=1)

    # Determine work schedule
    day_hours = [None] * 7  # Mon=0..Sun=6
    if user.use_daily_schedule:
        day_hours[0] = float(user.hours_monday or 0)
        day_hours[1] = float(user.hours_tuesday or 0)
        day_hours[2] = float(user.hours_wednesday or 0)
        day_hours[3] = float(user.hours_thursday or 0)
        day_hours[4] = float(user.hours_friday or 0)
    else:
        daily = float(user.weekly_hours) / (user.work_days_per_week or 5)
        for i in range(user.work_days_per_week or 5):
            day_hours[i] = daily

    # Check each day
    d = start_date
    while d <= end_date:
        weekday = d.weekday()  # Mon=0..Sun=6
        is_workday = day_hours[weekday] is not None and day_hours[weekday] > 0
        if is_workday and d not in entry_dates and d not in absence_dates:
            if not is_holiday(db, d):
                entries.append(MissingBookingEntry(date=d, type="missing"))
        d += timedelta(days=1)

    entries.sort(key=lambda e: e.date)
    return entries


@router.get("/", response_model=MonthlyDashboard)
def get_dashboard(
    year: Optional[int] = Query(None, description="Year (default: current year)"),
    month: Optional[int] = Query(None, description="Month (default: current month)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get dashboard data for current or specified month.
    Shows target, actual, and balance for the month.
    """
    # Use current month if not specified
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    target = calculation_service.get_monthly_target(db, current_user, year, month)
    actual = calculation_service.get_monthly_actual(db, current_user, year, month)
    balance = calculation_service.get_monthly_balance(db, current_user, year, month)

    return MonthlyDashboard(
        year=year,
        month=month,
        target_hours=target,
        actual_hours=actual,
        balance=balance
    )


@router.get("/overtime", response_model=OvertimeAccount)
def get_overtime_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get overtime account with monthly history.
    Shows cumulative overtime balance and history for each month.
    """
    # Get first time entry to determine start
    first_entry = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id
    ).order_by(TimeEntry.date).first()

    history = []
    now = datetime.now()

    if first_entry:
        start_year = first_entry.date.year
        start_month = first_entry.date.month

        current_year = start_year
        current_month = start_month

        # Build history month by month
        while (current_year < now.year) or (current_year == now.year and current_month <= now.month):
            target = calculation_service.get_monthly_target(db, current_user, current_year, current_month)
            actual = calculation_service.get_monthly_actual(db, current_user, current_year, current_month)
            balance = actual - target
            cumulative = calculation_service.get_overtime_account(db, current_user, current_year, current_month)

            history.append(OvertimeHistory(
                year=current_year,
                month=current_month,
                target=target,
                actual=actual,
                balance=balance,
                cumulative=cumulative
            ))

            # Move to next month
            if current_month == 12:
                current_month = 1
                current_year += 1
            else:
                current_month += 1

    # Current balance
    current_balance = calculation_service.get_overtime_account(
        db, current_user, now.year, now.month
    )

    return OvertimeAccount(
        current_balance=current_balance,
        history=history
    )


@router.get("/ytd-overtime", response_model=YtdOvertime)
def get_ytd_overtime(
    year: Optional[int] = Query(None, description="Year (default: current year)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get year-to-date overtime summary.
    Calculates target and actual hours from Jan 1 to today.
    """
    now = datetime.now()
    year = year or now.year

    summary = calculation_service.get_ytd_summary(db, current_user, year)

    return YtdOvertime(
        year=year,
        **summary
    )


@router.get("/vacation", response_model=VacationAccount)
def get_vacation_account(
    year: Optional[int] = Query(None, description="Year (default: current year)"),
    user_id: Optional[str] = Query(None, description="User ID (admin only)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get vacation account for a year.
    Shows budget, used, and remaining vacation in hours and days.

    Regular users can only query their own data.
    Admins can query any user's data by providing user_id.
    """
    year = year or datetime.now().year

    # Determine which user to query
    target_user = current_user

    if user_id:
        # Only admins can query other users
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")

        target_user = db.query(User).filter(User.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    account = calculation_service.get_vacation_account(db, target_user, year)

    # Determine carryover deadline (individual or default: March 31 of next year)
    from datetime import date as date_type
    if target_user.vacation_carryover_deadline:
        carryover_deadline = target_user.vacation_carryover_deadline
    else:
        carryover_deadline = date_type(year + 1, 3, 31)

    # Warning: remaining vacation AND deadline hasn't passed yet
    today = date_type.today()
    has_warning = (
        float(account["remaining_days"]) > 0
        and today.year == year  # only warn for current year
        and today.month >= 10  # Q4 warning
    )

    return VacationAccount(
        year=year,
        carryover_deadline=carryover_deadline,
        has_carryover_warning=has_warning,
        **account
    )


@router.get("/missing-bookings", response_model=MissingBookings)
def get_missing_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get missing/open bookings for current user."""
    if not current_user.track_hours:
        return MissingBookings(
            user_id=str(current_user.id),
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            entries=[]
        )
    missing = _get_missing_bookings_for_user(db, current_user)
    return MissingBookings(
        user_id=str(current_user.id),
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        entries=missing
    )


@router.get("/missing-bookings/team", response_model=List[MissingBookings])
def get_team_missing_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get missing/open bookings for all active employees (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    users = db.query(User).filter(
        User.is_active == True,
        User.track_hours == True,
        User.is_hidden == False,
    ).order_by(User.last_name).all()

    results = []
    for user in users:
        missing = _get_missing_bookings_for_user(db, user)
        if missing:
            results.append(MissingBookings(
                user_id=str(user.id),
                first_name=user.first_name,
                last_name=user.last_name,
                entries=missing
            ))
    return results
