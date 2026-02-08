from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List
from datetime import datetime
from io import BytesIO
from app.database import get_db
from app.models import User, Absence, AbsenceType
from app.middleware.auth import require_admin
from app.schemas.reports import EmployeeMonthlyReport, EmployeeYearlyAbsences
from app.services import calculation_service, export_service

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"], dependencies=[Depends(require_admin)])


@router.get("/monthly", response_model=List[EmployeeMonthlyReport])
def get_monthly_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get monthly report for all employees.
    Shows target, actual, balance, overtime, vacation, and sick hours.
    """
    try:
        year, month_num = map(int, month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    # Get all active users
    users = db.query(User).filter(User.is_active == True).order_by(User.last_name, User.first_name).all()

    reports = []

    for user in users:
        target = calculation_service.get_monthly_target(db, user, year, month_num)
        actual = calculation_service.get_monthly_actual(db, user, year, month_num)
        balance = calculation_service.get_monthly_balance(db, user, year, month_num)
        overtime = calculation_service.get_overtime_account(db, user, year, month_num)

        # Get vacation and sick hours for the month
        vacation_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.VACATION,
            extract('year', Absence.date) == year,
            extract('month', Absence.date) == month_num
        ).all()
        vacation_hours = sum(float(a.hours) for a in vacation_absences)

        sick_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.SICK,
            extract('year', Absence.date) == year,
            extract('month', Absence.date) == month_num
        ).all()
        sick_hours = sum(float(a.hours) for a in sick_absences)

        reports.append(EmployeeMonthlyReport(
            user_id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            weekly_hours=float(user.weekly_hours),
            target_hours=float(target),
            actual_hours=float(actual),
            balance=float(balance),
            overtime_cumulative=float(overtime),
            vacation_used_hours=vacation_hours,
            sick_hours=sick_hours
        ))

    return reports


@router.get("/yearly-absences", response_model=List[EmployeeYearlyAbsences])
def get_yearly_absences(
    year: int = Query(..., description="Year (e.g., 2025)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get yearly absence summary for all employees.
    Shows vacation, sick, training, and other days.
    """
    # Get all active users
    users = db.query(User).filter(User.is_active == True).order_by(User.last_name, User.first_name).all()

    results = []

    for user in users:
        # Get daily target hours for this user
        daily_target = calculation_service.get_daily_target(user)

        # If daily_target is 0, we can't calculate days
        if daily_target == 0:
            daily_target = Decimal('8.0')  # Use default 8h for calculation

        # Get all absences for the year
        vacation_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.VACATION,
            extract('year', Absence.date) == year
        ).all()
        vacation_hours = sum(float(a.hours) for a in vacation_absences)
        vacation_days = vacation_hours / float(daily_target)

        sick_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.SICK,
            extract('year', Absence.date) == year
        ).all()
        sick_hours = sum(float(a.hours) for a in sick_absences)
        sick_days = sick_hours / float(daily_target)

        training_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.TRAINING,
            extract('year', Absence.date) == year
        ).all()
        training_hours = sum(float(a.hours) for a in training_absences)
        training_days = training_hours / float(daily_target)

        other_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.OTHER,
            extract('year', Absence.date) == year
        ).all()
        other_hours = sum(float(a.hours) for a in other_absences)
        other_days = other_hours / float(daily_target)

        total_days = vacation_days + sick_days + training_days + other_days

        results.append(EmployeeYearlyAbsences(
            user_id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            vacation_days=vacation_days,
            sick_days=sick_days,
            training_days=training_days,
            other_days=other_days,
            total_days=total_days
        ))

    return results


@router.get("/export")
def export_monthly_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export monthly report as Excel file.
    Creates one sheet per employee with daily breakdown.
    """
    try:
        year, month_num = map(int, month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    # Generate Excel file
    excel_file = export_service.generate_monthly_report(db, year, month_num)

    # Create filename
    filename = f"PraxisZeit_Monatsreport_{year}_{month_num:02d}.xlsx"

    # Return as streaming response
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export-yearly")
def export_yearly_report(
    year: int = Query(..., description="Year (e.g., 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export yearly report as Excel file.
    Creates:
    - Overview sheet with all employees
    - Absences overview
    - Detail sheet per employee with monthly breakdown
    """
    # Generate Excel file
    excel_file = export_service.generate_yearly_report(db, year)

    # Create filename
    filename = f"PraxisZeit_Jahresreport_{year}.xlsx"

    # Return as streaming response
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export-yearly-classic")
def export_yearly_report_classic(
    year: int = Query(..., description="Year (e.g., 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export yearly report in classic format (compact, months as columns).
    Creates one sheet per employee with 12-month overview.
    """
    # Generate Excel file
    excel_file = export_service.generate_yearly_report_classic(db, year)

    # Create filename
    filename = f"PraxisZeit_Jahresreport_Classic_{year}.xlsx"

    # Return as streaming response
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
