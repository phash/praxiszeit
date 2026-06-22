import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract
from starlette.requests import Request
from typing import List
from decimal import Decimal
from io import BytesIO
from datetime import date
from urllib.parse import quote
from app.database import get_db
from app.models import User, Absence, AbsenceType, TimeEntry, TimeEntryAuditLog
from app.models.public_holiday import PublicHoliday
from app.middleware.auth import require_admin
from app.schemas.reports import EmployeeMonthlyReport, EmployeeYearlyAbsences
from app.services import calculation_service, export_service, ods_export_service, rest_time_service
from app.services.arbzg_utils import is_night_work
from app.services.date_filters import date_in_year, date_in_month
from app.core.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"], dependencies=[Depends(require_admin)])


def _get_active_visible_users(db: Session, tenant_id) -> list:
    """Return all active, non-hidden users for the given tenant, ordered by name.

    F-026: explicit tenant filter (RLS is the second line of defense).
    """
    return db.query(User).filter(
        User.tenant_id == tenant_id,
        User.is_active == True,
        User.is_hidden == False,
    ).order_by(User.last_name, User.first_name).all()


@router.get("/monthly", response_model=List[EmployeeMonthlyReport])
def get_monthly_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    include_health_data: bool = Query(False, description="Krankheitsdaten einschließen (Art. 9 DSGVO)"),
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

    if include_health_data:
        logger.info(
            "DSGVO-Datenzugriff: Monatsreport %s-%02d aufgerufen von Admin %s",
            year, month_num, current_user.username
        )
        # F-020: Audit log for sensitive health data read (Art. 9 – sick_hours in response)
        audit = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_data_read",
            source="dsgvo",
            new_note=f"Monatsreport {year}-{month_num:02d} (inkl. Krankheitsstunden) gelesen von Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(audit)
        db.commit()

    users = _get_active_visible_users(db, current_user.tenant_id)

    reports = []

    for user in users:
        target = calculation_service.get_monthly_target(db, user, year, month_num)
        actual = calculation_service.get_monthly_actual(db, user, year, month_num)
        # #150: target/actual sind bereits berechnet — get_monthly_balance würde
        # beide pro User redundant neu laden. Identisch zu dessen (actual-target).quantize.
        balance = (actual - target).quantize(Decimal('0.01'))
        overtime = calculation_service.get_overtime_account(db, user, year, month_num)

        # Get vacation and sick hours for the month (F-033: sargable)
        vacation_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.VACATION,
            date_in_month(Absence.date, year, month_num),
        ).all()
        vacation_hours = sum(float(a.hours) for a in vacation_absences)

        sick_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.SICK,
            date_in_month(Absence.date, year, month_num),
        ).all()
        sick_hours = sum(float(a.hours) for a in sick_absences)

        # Use weekly_hours valid at start of report month, not current value
        report_date = date(year, month_num, 1)
        hist_weekly = calculation_service.get_weekly_hours_for_date(db, user, report_date)

        reports.append(EmployeeMonthlyReport(
            user_id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            weekly_hours=float(hist_weekly),
            target_hours=float(target),
            actual_hours=float(actual),
            balance=float(balance),
            overtime_cumulative=float(overtime),
            vacation_used_hours=vacation_hours,
            sick_hours=sick_hours if include_health_data else 0.0,
            exempt_from_arbzg=bool(user.exempt_from_arbzg),
        ))

    return reports


@router.get("/yearly-absences", response_model=List[EmployeeYearlyAbsences])
def get_yearly_absences(
    year: int = Query(..., description="Year (e.g., 2025)"),
    include_health_data: bool = Query(False, description="Krankheitsdaten einschließen (Art. 9 DSGVO)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get yearly absence summary for all employees.
    Shows vacation, sick, training, and other days.
    """
    if include_health_data:
        logger.info(
            "DSGVO-Datenzugriff: Jahres-Abwesenheitsübersicht %d aufgerufen von Admin %s",
            year, current_user.username
        )
        # F-020: Audit log for sensitive health data read (Art. 9 – sick_days in response)
        audit = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_data_read",
            source="dsgvo",
            new_note=f"Jahres-Abwesenheitsübersicht {year} (inkl. Krankheitstage) gelesen von Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(audit)
        db.commit()

    users = _get_active_visible_users(db, current_user.tenant_id)

    results = []

    for user in users:
        # Uses current daily target for hours-to-days conversion — approximate for display.
        # The hour totals are always exact; only the "days" column is an approximation
        # when weekly_hours changed during the year.
        daily_target = calculation_service.get_daily_target(user)

        # If daily_target is 0, we can't calculate days
        if daily_target == 0:
            daily_target = Decimal('8.0')  # Use default 8h for calculation

        # F-033 + Sprint 3.4: fetch all absences for this user+year in ONE
        # query, group by type in Python. Previous code issued 5 separate
        # queries per user (one per type).
        all_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            date_in_year(Absence.date, year),
        ).all()
        hours_by_type: dict = {}
        for a in all_absences:
            hours_by_type[a.type] = hours_by_type.get(a.type, 0.0) + float(a.hours)

        # Vacation is reported DAY-BASED (Tagesprinzip §3 BUrlG) from the same
        # source as remaining below — so "budget − genommen == Rest" holds in the
        # same response. The hours/Ø-target approximation (used by the other
        # columns, documented above) diverges from the day principle for
        # use_daily_schedule employees; vacation is the maßgebliche value and
        # must not contradict the vacation account.
        vacation_account = calculation_service.get_vacation_account(db, user, year)
        vacation_days = float(vacation_account['used_days'])

        sick_hours = hours_by_type.get(AbsenceType.SICK, 0.0)
        sick_days = sick_hours / float(daily_target)

        training_hours = hours_by_type.get(AbsenceType.TRAINING, 0.0)
        training_days = training_hours / float(daily_target)

        overtime_comp_hours = hours_by_type.get(AbsenceType.OVERTIME, 0.0)
        overtime_comp_days = overtime_comp_hours / float(daily_target)

        other_hours = hours_by_type.get(AbsenceType.OTHER, 0.0)
        other_days = other_hours / float(daily_target)

        paid_leave_hours = hours_by_type.get(AbsenceType.PAID_LEAVE, 0.0)
        paid_leave_days = paid_leave_hours / float(daily_target)

        effective_sick_days = sick_days if include_health_data else 0.0
        total_days = vacation_days + effective_sick_days + training_days + overtime_comp_days + other_days + paid_leave_days

        # Remaining vacation from the same account fetched above (day-based).
        remaining_vacation_days = vacation_account['remaining_days']

        # Calculate overtime for the year (up to today for current year, full year otherwise)
        ytd = calculation_service.get_ytd_summary(db, user, year)
        overtime_year = ytd['overtime']

        results.append(EmployeeYearlyAbsences(
            user_id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            vacation_days=vacation_days,
            remaining_vacation_days=float(remaining_vacation_days),
            sick_days=effective_sick_days,
            training_days=training_days,
            overtime_comp_days=overtime_comp_days,
            other_days=other_days,
            paid_leave_days=paid_leave_days,
            overtime_year=float(overtime_year),
            total_days=total_days
        ))

    return results


@router.get("/export")
@limiter.limit("20/minute")
def export_monthly_report(
    request: Request,
    month: str = Query(..., description="Month in YYYY-MM format"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export monthly report as Excel file.
    Creates one sheet per employee with daily breakdown.
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged).
    """
    try:
        year, month_num = map(int, month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if include_health_data:
        log = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_export",
            source="dsgvo",
            new_note=f"Gesundheitsdaten (Art. 9 DSGVO) im Monatsreport {year}-{month_num:02d} exportiert – Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(log)
        db.commit()

    # Generate Excel file
    excel_file = export_service.generate_monthly_report(db, year, month_num, include_health_data, tenant_id=current_user.tenant_id)

    # F-053: release the DB connection before streaming. The workbook is
    # already fully materialised in the BytesIO, so holding a connection
    # during the client download is wasted pool capacity. Concurrent admin
    # exports would otherwise starve the default pool_size=5.
    db.close()

    # Create filename
    filename = f"PraxisZeit_Monatsreport_{year}_{month_num:02d}.xlsx"

    # Return as streaming response
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-yearly")
@limiter.limit("20/minute")
def export_yearly_report(
    request: Request,
    year: int = Query(..., description="Year (e.g., 2026)"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export yearly report as Excel file.
    Creates:
    - Overview sheet with all employees
    - Absences overview
    - Detail sheet per employee with monthly breakdown
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged).
    """
    if include_health_data:
        log = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_export",
            source="dsgvo",
            new_note=f"Gesundheitsdaten (Art. 9 DSGVO) im Jahresreport {year} exportiert – Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(log)
        db.commit()

    excel_file = export_service.generate_yearly_report(db, year, include_health_data, tenant_id=current_user.tenant_id)
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Jahresreport_{year}.xlsx"
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-yearly-classic")
@limiter.limit("20/minute")
def export_yearly_report_classic(
    request: Request,
    year: int = Query(..., description="Year (e.g., 2026)"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export yearly report in classic format (compact, months as columns).
    Creates one sheet per employee with 12-month overview.
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged).
    """
    if include_health_data:
        log = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_export",
            source="dsgvo",
            new_note=f"Gesundheitsdaten (Art. 9 DSGVO) im Jahresreport Classic {year} exportiert – Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(log)
        db.commit()

    excel_file = export_service.generate_yearly_report_classic(db, year, include_health_data, tenant_id=current_user.tenant_id)
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Jahresreport_Classic_{year}.xlsx"
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"


@router.get("/export-ods")
@limiter.limit("20/minute")
def export_monthly_report_ods(
    request: Request,
    month: str = Query(..., description="Month in YYYY-MM format"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export monthly report as ODS file (Open Document Spreadsheet).
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged)."""
    try:
        year, month_num = map(int, month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if include_health_data:
        log = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_export",
            source="dsgvo",
            new_note=f"Gesundheitsdaten (Art. 9 DSGVO) im ODS-Monatsreport {year}-{month_num:02d} exportiert – Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(log)
        db.commit()

    ods_file = ods_export_service.generate_monthly_report(db, year, month_num, include_health_data, tenant_id=current_user.tenant_id)
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Monatsreport_{year}_{month_num:02d}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-pdf")
@limiter.limit("20/minute")
def export_monthly_report_pdf(
    request: Request,
    month: str = Query(..., description="Month in YYYY-MM format"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export monthly report as PDF file (landscape A4, one page per employee)."""
    try:
        year, month_num = map(int, month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if include_health_data:
        log = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_export",
            source="dsgvo",
            new_note=f"Gesundheitsdaten (Art. 9 DSGVO) im PDF-Monatsreport {year}-{month_num:02d} exportiert – Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(log)
        db.commit()

    pdf_file = export_service.generate_monthly_report_pdf(db, year, month_num, include_health_data, tenant_id=current_user.tenant_id)
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Monatsreport_{year}_{month_num:02d}.pdf"
    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-yearly-ods")
@limiter.limit("20/minute")
def export_yearly_report_ods(
    request: Request,
    year: int = Query(..., description="Year (e.g., 2026)"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export yearly detailed report as ODS file.
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged)."""
    if include_health_data:
        log = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_export",
            source="dsgvo",
            new_note=f"Gesundheitsdaten (Art. 9 DSGVO) im ODS-Jahresreport {year} exportiert – Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(log)
        db.commit()
    ods_file = ods_export_service.generate_yearly_report(db, year, include_health_data, tenant_id=current_user.tenant_id)
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Jahresreport_{year}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-yearly-classic-ods")
@limiter.limit("20/minute")
def export_yearly_report_classic_ods(
    request: Request,
    year: int = Query(..., description="Year (e.g., 2026)"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export yearly classic report as ODS file.
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged)."""
    if include_health_data:
        log = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_export",
            source="dsgvo",
            new_note=f"Gesundheitsdaten (Art. 9 DSGVO) im ODS-Jahresreport Classic {year} exportiert – Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(log)
        db.commit()
    ods_file = ods_export_service.generate_yearly_report_classic(db, year, include_health_data, tenant_id=current_user.tenant_id)
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Jahresreport_Classic_{year}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
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
        db, year, month, min_rest_hours, tenant_id=current_user.tenant_id
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

    users = _get_active_visible_users(db, current_user.tenant_id)
    result = []

    for user in users:
        # Get all entries on Sundays in this year
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                date_in_year(TimeEntry.date, year),
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
    users = _get_active_visible_users(db, current_user.tenant_id)
    result = []
    threshold = 48  # §6 ArbZG: Nachtarbeitnehmer if >= 48 days/year

    for user in users:
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                date_in_year(TimeEntry.date, year),
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

    users = _get_active_visible_users(db, current_user.tenant_id)
    result = []

    for user in users:
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                date_in_year(TimeEntry.date, year),
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
            # F-026: is_holiday requires tenant_id per CLAUDE.md multi-tenant rules
            is_hol = _is_holiday(db, e.date, tenant_id=current_user.tenant_id)
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


@router.get("/24-week-average")
def get_24_week_averaging_period(
    end_date: date = Query(None, description="End of the 24-week window (default: today)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    §3 ArbZG: Daily hours may be extended to 10h only if the 8h daily average
    is maintained over 6 calendar months / 24 weeks.

    For each active employee, sums all net working hours in the window and
    compares to the allowed budget (8h × scheduled work days).

    M-ARB2: ``scheduled_work_days`` is computed per actual working day in the
    window — honouring the user's weekday schedule, historical working-hours
    changes, public holidays and full-day absences — instead of a flat
    ``24 × work_days_per_week``. A static denominator over- or under-states the
    averaging budget when the contract changed mid-window or the window contains
    holidays/absences, and could wrongly flag (or hide) a §3 violation.

    An employee flagged as non-compliant has systematically exceeded the 10h
    exception allowance and the ArbZG averaging clause no longer covers them.
    """
    from datetime import timedelta
    from app.services.timezone_service import today_local

    if end_date is None:
        # Europe/Berlin, not UTC/container time — consistent with all other
        # business-logic "today" stichtage (Dashboard, YTD, vacation warnings).
        # date.today() rolled the §3 24-week window by a day between 00:00–02:00 CET.
        end_date = today_local()
    start_date = end_date - timedelta(weeks=24)

    users = _get_active_visible_users(db, current_user.tenant_id)
    result = []

    # Public holidays for the whole window, tenant-scoped (fetched once).
    holiday_dates = {
        h.date
        for h in db.query(PublicHoliday).filter(
            PublicHoliday.date >= start_date,
            PublicHoliday.date <= end_date,
            PublicHoliday.tenant_id == current_user.tenant_id,
        ).all()
    }

    for user in users:
        if user.exempt_from_arbzg:
            continue

        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                TimeEntry.date >= start_date,
                TimeEntry.date <= end_date,
                TimeEntry.end_time.isnot(None),
            )
            .all()
        )
        total_hours = sum(float(e.net_hours or 0) for e in entries)

        # Absences that mean the employee was NOT scheduled to work that day.
        # Mirror get_monthly_target: TRAINING/SICK/OVERTIME keep the day
        # scheduled (the employee was due to work); VACATION/OTHER/PAID_LEAVE
        # remove it from the averaging denominator.
        absence_dates = {
            a.date
            for a in db.query(Absence).filter(
                Absence.user_id == user.id,
                Absence.date >= start_date,
                Absence.date <= end_date,
                Absence.type.notin_([
                    AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME,
                ]),
            ).all()
        }

        # Count actually-scheduled working days in the window (weekday schedule
        # + contract history via get_*_for_date, minus holidays/absences).
        scheduled_days = 0
        d = start_date
        while d <= end_date:
            if d.weekday() < 5 and d not in holiday_dates and d not in absence_dates:
                weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, d)
                if calculation_service.get_daily_target_for_date(user, d, weekly_hours) > 0:
                    scheduled_days += 1
            d += timedelta(days=1)

        max_budget = 8.0 * scheduled_days
        average = (total_hours / scheduled_days) if scheduled_days else 0.0

        # Count days where the employee exceeded 8h — these are the days
        # that actually consume the averaging budget.
        over_8h_count = 0
        by_date: dict = {}
        for e in entries:
            by_date.setdefault(e.date, 0.0)
            by_date[e.date] += float(e.net_hours or 0)
        for total in by_date.values():
            if total > 8.0:
                over_8h_count += 1

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "window_start": start_date.isoformat(),
            "window_end": end_date.isoformat(),
            "total_hours": round(total_hours, 2),
            "scheduled_work_days": scheduled_days,
            "max_budget_hours": round(max_budget, 2),
            "average_daily_hours": round(average, 2),
            "days_over_8h": over_8h_count,
            "compliant": average <= 8.0,
        })

    return {
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "employees": result,
        "non_compliant_count": sum(1 for r in result if not r["compliant"]),
    }
