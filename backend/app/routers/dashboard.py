from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
from app.database import get_db
from app.models import User, TimeEntry, UserRole
from app.middleware.auth import get_current_user
from app.schemas.reports import MonthlyDashboard, OvertimeAccount, OvertimeHistory, VacationAccount
from app.services import calculation_service
from sqlalchemy import extract

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


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

    return VacationAccount(
        year=year,
        **account
    )
