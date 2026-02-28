from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List
from decimal import Decimal
from io import BytesIO
from datetime import date
from app.database import get_db
from app.models import User, Absence, AbsenceType, TimeEntry
from app.middleware.auth import require_admin
from app.schemas.reports import EmployeeMonthlyReport, EmployeeYearlyAbsences
from app.services import calculation_service, export_service, ods_export_service, rest_time_service

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"], dependencies=[Depends(require_admin)])


def _get_active_visible_users(db: Session) -> list:
    """Return all active, non-hidden users ordered by name."""
    return db.query(User).filter(
        User.is_active == True,
        User.is_hidden == False
    ).order_by(User.last_name, User.first_name).all()


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

    users = _get_active_visible_users(db)

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
    users = _get_active_visible_users(db)

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

        # Calculate remaining vacation
        vacation_account = calculation_service.get_vacation_account(db, user, year)
        remaining_vacation_days = vacation_account['remaining_days']

        # Calculate cumulative overtime for the year (up to December)
        overtime_year = calculation_service.get_overtime_account(db, user, year, 12)

        results.append(EmployeeYearlyAbsences(
            user_id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            vacation_days=vacation_days,
            remaining_vacation_days=float(remaining_vacation_days),
            sick_days=sick_days,
            training_days=training_days,
            other_days=other_days,
            overtime_year=float(overtime_year),
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


ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"


@router.get("/export-ods")
def export_monthly_report_ods(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export monthly report as ODS file (Open Document Spreadsheet)."""
    try:
        year, month_num = map(int, month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    ods_file = ods_export_service.generate_monthly_report(db, year, month_num)
    filename = f"PraxisZeit_Monatsreport_{year}_{month_num:02d}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export-yearly-ods")
def export_yearly_report_ods(
    year: int = Query(..., description="Year (e.g., 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export yearly detailed report as ODS file."""
    ods_file = ods_export_service.generate_yearly_report(db, year)
    filename = f"PraxisZeit_Jahresreport_{year}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export-yearly-classic-ods")
def export_yearly_report_classic_ods(
    year: int = Query(..., description="Year (e.g., 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export yearly classic report as ODS file."""
    ods_file = ods_export_service.generate_yearly_report_classic(db, year)
    filename = f"PraxisZeit_Jahresreport_Classic_{year}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/rest-time-violations")
def get_rest_time_violations(
    year: int = Query(..., description="Year to check"),
    month: int = Query(None, description="Optional month to check"),
    min_rest_hours: float = Query(None, description="Minimum rest hours (default: 11)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get rest time violations for all employees.
    A violation occurs when the time between two work shifts is less than min_rest_hours.
    Default minimum rest time: 11 hours (German law ArbZG §5).
    """
    violations = rest_time_service.check_all_users_violations(
        db, year, month, min_rest_hours
    )
    return {
        "year": year,
        "month": month,
        "min_rest_hours": min_rest_hours or rest_time_service.DEFAULT_MIN_REST_HOURS,
        "total_violations": sum(v["violation_count"] for v in violations),
        "employees_affected": len(violations),
        "violations": violations
    }


@router.get("/sunday-summary")
def get_sunday_summary(
    year: int = Query(..., description="Year to check (e.g., 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    §11 ArbZG: Get Sunday/holiday work summary per employee for a given year.
    Reports how many Sundays each employee worked and whether the legal minimum
    of 15 free Sundays per year is met.
    """
    import calendar

    # Count total Sundays in the year
    total_sundays = sum(
        1 for m in range(1, 13)
        for d in range(1, calendar.monthrange(year, m)[1] + 1)
        if date(year, m, d).weekday() == 6
    )
    min_free_sundays = 15

    users = _get_active_visible_users(db)
    result = []

    for user in users:
        # Get all entries on Sundays in this year
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                extract("year", TimeEntry.date) == year,
            )
            .all()
        )
        sundays_worked = {
            e.date for e in entries if e.date.weekday() == 6
        }
        sundays_worked_count = len(sundays_worked)
        free_sundays = total_sundays - sundays_worked_count

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "sundays_worked": sundays_worked_count,
            "free_sundays": free_sundays,
            "total_sundays_in_year": total_sundays,
            "compliant": free_sundays >= min_free_sundays,
        })

    return {
        "year": year,
        "total_sundays_in_year": total_sundays,
        "min_free_sundays": min_free_sundays,
        "employees": result,
        "non_compliant_count": sum(1 for r in result if not r["compliant"]),
    }


@router.get("/night-work-summary")
def get_night_work_summary(
    year: int = Query(..., description="Year to check (e.g., 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    §6 ArbZG: Night work summary per employee for a given year.
    Night hours: 23:00–06:00. Reports how many days each employee
    performed night work and whether they qualify as Nachtarbeitnehmer (>=48 days/year).
    """
    from datetime import time as time_type

    NIGHT_START = time_type(23, 0)
    NIGHT_END = time_type(6, 0)

    def is_night_work(start, end):
        if start is None or end is None:
            return False
        return start < NIGHT_END or end > NIGHT_START

    users = _get_active_visible_users(db)
    result = []
    threshold = 48  # §6 ArbZG: Nachtarbeitnehmer if >= 48 days/year

    for user in users:
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                extract("year", TimeEntry.date) == year,
                TimeEntry.end_time.isnot(None),
            )
            .order_by(TimeEntry.date)
            .all()
        )

        night_days = {
            e.date for e in entries if is_night_work(e.start_time, e.end_time)
        }
        night_days_count = len(night_days)

        # Group by month
        by_month: dict = {}
        for d in sorted(night_days):
            m = d.month
            by_month[m] = by_month.get(m, 0) + 1

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "night_work_days": night_days_count,
            "is_nachtarbeitnehmer": night_days_count >= threshold,
            "nachtarbeitnehmer_threshold": threshold,
            "by_month": [{"month": m, "days": c} for m, c in sorted(by_month.items())],
        })

    return {
        "year": year,
        "nachtarbeitnehmer_threshold": threshold,
        "employees": result,
        "nachtarbeitnehmer_count": sum(1 for r in result if r["is_nachtarbeitnehmer"]),
    }


@router.get("/compensatory-rest")
def get_compensatory_rest(
    year: int = Query(..., description="Year to check (e.g., 2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    §11 ArbZG: Compensatory rest day tracking.
    After Sunday work → 1 free day within 2 weeks.
    After holiday work → 1 free day within 8 weeks.
    A 'free day' is any weekday without a time entry (Mo-Sa excluding Sundays).
    """
    from datetime import timedelta

    users = _get_active_visible_users(db)
    result = []

    for user in users:
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                extract("year", TimeEntry.date) == year,
                TimeEntry.end_time.isnot(None),
            )
            .all()
        )

        worked_dates = {e.date for e in entries}

        # Get all dates worked on Sundays or holidays
        from app.services.holiday_service import is_holiday as _is_holiday

        sunday_holidays_worked = []
        for e in entries:
            weekday = e.date.weekday()
            is_sun = weekday == 6
            is_hol = _is_holiday(db, e.date)
            if is_sun or is_hol:
                sunday_holidays_worked.append({
                    "date": e.date,
                    "type": "sunday" if is_sun else "holiday",
                })

        # Deduplicate by date
        seen = set()
        unique_days = []
        for item in sunday_holidays_worked:
            if item["date"] not in seen:
                seen.add(item["date"])
                unique_days.append(item)

        violations = []
        for item in unique_days:
            d = item["date"]
            day_type = item["type"]
            window_days = 14 if day_type == "sunday" else 56  # 2 or 8 weeks

            # Find any free day (Mon–Sat, no entry) within window after d
            compensated = False
            for offset in range(1, window_days + 1):
                candidate = d + timedelta(days=offset)
                # Free day = Mon(0)–Sat(5), not worked
                if 0 <= candidate.weekday() <= 5 and candidate not in worked_dates:
                    compensated = True
                    break

            if not compensated:
                violations.append({
                    "date": d.isoformat(),
                    "type": day_type,
                    "window_weeks": window_days // 7,
                })

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "sunday_holiday_days_worked": len(unique_days),
            "violations": violations,
            "violation_count": len(violations),
            "compliant": len(violations) == 0,
        })

    return {
        "year": year,
        "employees": result,
        "total_violations": sum(r["violation_count"] for r in result),
        "non_compliant_count": sum(1 for r in result if not r["compliant"]),
    }
