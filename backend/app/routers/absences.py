from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List, Optional
from datetime import timedelta, date
from app.services.timezone_service import today_local
from app.database import get_db
from app.models import User, Absence, AbsenceType, UserRole, PublicHoliday, TimeEntry, TimeEntryAuditLog
from app.middleware.auth import get_current_user
from app.schemas.absence import AbsenceCreate, AbsenceResponse, AbsenceCalendarEntry, TeamAbsenceEntry, NextVacationResponse
from app.services import calculation_service
from app.routers.admin_helpers import _create_audit_log

router = APIRouter(prefix="/api/absences", tags=["absences"])


@router.get("/daily-target")
def get_daily_target_for_date_endpoint(
    target_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get daily target hours for a specific date (for pre-filling absence forms)."""
    weekly = calculation_service.get_weekly_hours_for_date(db, current_user, target_date)
    daily = calculation_service.get_daily_target_for_date(current_user, target_date, weekly_hours=weekly)
    return {"date": str(target_date), "hours": float(daily)}


@router.get("/", response_model=List[AbsenceResponse])
def list_absences(
    year: Optional[int] = Query(None, description="Filter by year"),
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List absences.
    Regular users can only see their own absences.
    Admins can filter by user_id.
    """
    query = db.query(Absence)

    # If user_id is provided, only admin can filter by it
    if user_id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
        query = query.filter(Absence.user_id == user_id)
    else:
        # Regular users only see their own absences
        query = query.filter(Absence.user_id == current_user.id)

    # Filter by year if provided
    if year:
        query = query.filter(extract('year', Absence.date) == year)

    absences = query.order_by(Absence.date.desc()).all()
    return absences


@router.get("/calendar", response_model=List[AbsenceCalendarEntry])
def get_absence_calendar(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get absence calendar for all employees for a specific month.
    Visible to all authenticated users.
    """
    try:
        year, month_num = map(int, month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    # Get all absences for the month, fetching User columns in the same query
    rows = db.query(Absence, User.first_name, User.last_name).join(User).filter(
        User.is_active == True,
        User.is_hidden == False,
        extract('year', Absence.date) == year,
        extract('month', Absence.date) == month_num
    ).order_by(Absence.date).all()

    # Convert to calendar entries (no extra queries needed)
    # DSGVO Art. 9: Krankheitsdaten sind besonders schützenswert.
    # Nicht-Admins sehen fremde Krankmeldungen nur als "absent".
    calendar_entries = []
    for absence, first_name, last_name in rows:
        display_type = absence.type.value
        if (
            absence.type == AbsenceType.SICK
            and current_user.role != UserRole.ADMIN
            and absence.user_id != current_user.id
        ):
            display_type = "absent"
        calendar_entries.append(AbsenceCalendarEntry(
            date=absence.date,
            user_first_name=first_name,
            user_last_name=last_name,
            type=display_type,
            hours=absence.hours
        ))

    return calendar_entries


@router.get("/team/upcoming", response_model=List[TeamAbsenceEntry])
def get_team_upcoming_absences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get upcoming absences for all active employees.
    Visible to all authenticated users.
    Shows unique absence periods (groups consecutive days with same end_date).
    """
    today = today_local()

    # Get all future absences from active users, fetching User columns in the same query
    rows = db.query(
        Absence, User.first_name, User.last_name, User.calendar_color
    ).join(User).filter(
        User.is_active == True,
        User.is_hidden == False,
        Absence.date >= today
    ).order_by(Absence.date, User.last_name, User.first_name).all()

    # Group by user and end_date to avoid duplicates for date ranges
    seen = set()
    team_absences = []

    # DSGVO Art. 9: Krankheitsdaten sind besonders schützenswert.
    # Nicht-Admins sehen fremde Krankmeldungen nur als "absent".
    for absence, first_name, last_name, calendar_color in rows:
        # Create a unique key for this absence period
        key = (absence.user_id, absence.date, absence.end_date or absence.date, absence.type)

        if key not in seen:
            seen.add(key)
            display_type = absence.type.value
            if (
                absence.type == AbsenceType.SICK
                and current_user.role != UserRole.ADMIN
                and absence.user_id != current_user.id
            ):
                display_type = "absent"
            team_absences.append(TeamAbsenceEntry(
                date=absence.date,
                end_date=absence.end_date,
                user_first_name=first_name,
                user_last_name=last_name,
                user_color=calendar_color,
                type=display_type,
                hours=absence.hours,
            ))

    return team_absences


@router.get("/next-vacation", response_model=Optional[NextVacationResponse])
def get_next_vacation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the next upcoming vacation for the current user.
    Returns the start date, optional end date, and days until the vacation.
    Returns null if no upcoming vacation is found.
    """
    today = today_local()

    next_vacation = db.query(Absence).filter(
        Absence.user_id == current_user.id,
        Absence.type == AbsenceType.VACATION,
        Absence.date >= today
    ).order_by(Absence.date.asc()).first()

    if not next_vacation:
        return None

    days_until = (next_vacation.date - today).days

    return NextVacationResponse(
        date=next_vacation.date,
        end_date=next_vacation.end_date,
        days_until=days_until
    )


@router.post("/", response_model=List[AbsenceResponse], status_code=status.HTTP_201_CREATED)
def create_absence(
    absence_data: AbsenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create absence entry/entries.
    If end_date is provided, creates entries for all weekdays (Mon-Fri) in the range.
    For vacation type, check if remaining vacation is sufficient.
    """

    # Determine target user (admin can create for others)
    target_user = current_user
    if absence_data.user_id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
        target_user = db.query(User).filter(User.id == absence_data.user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # Determine date range
    start_date = absence_data.date
    end_date = absence_data.end_date if absence_data.end_date else absence_data.date

    # Validate date range
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="Enddatum muss nach dem Startdatum liegen"
        )

    # Arbeitszeitraum-Prüfung (I2)
    if target_user.first_work_day and start_date < target_user.first_work_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Datum liegt vor dem ersten Arbeitstag ({target_user.first_work_day.strftime('%d.%m.%Y')})"
        )
    if target_user.last_work_day and end_date > target_user.last_work_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Datum liegt nach dem letzten Arbeitstag ({target_user.last_work_day.strftime('%d.%m.%Y')})"
        )

    # Generate list of weekdays (Mon-Fri, excluding weekends and holidays)
    dates_to_create = []
    current_date = start_date

    # Get holidays for the affected years
    years = set()
    temp_date = start_date
    while temp_date <= end_date:
        years.add(temp_date.year)
        temp_date += timedelta(days=1)

    holidays = set()
    for year in years:
        year_holidays = db.query(PublicHoliday).filter(
            PublicHoliday.year == year
        ).all()
        holidays.update([h.date for h in year_holidays])

    # Collect all weekdays in range (excluding weekends and holidays)
    while current_date <= end_date:
        # Check if it's a weekday (0=Monday, 6=Sunday)
        if current_date.weekday() < 5 and current_date not in holidays:
            dates_to_create.append(current_date)
        current_date += timedelta(days=1)

    if not dates_to_create:
        raise HTTPException(
            status_code=400,
            detail="Keine gültigen Arbeitstage im angegebenen Zeitraum"
        )

    # Check for existing absences (any type — no double-booking allowed)
    skip_dates = []
    for date in dates_to_create:
        existing = db.query(Absence).filter(
            Absence.user_id == target_user.id,
            Absence.date == date,
        ).first()

        if existing:
            if existing.type == absence_data.type:
                skip_dates.append(date)  # Skip duplicate of same type (idempotent)
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Am {date.strftime('%d.%m.%Y')} existiert bereits eine Abwesenheit ({existing.type.value})"
                )
    dates_to_create = [d for d in dates_to_create if d not in skip_dates]

    if not dates_to_create:
        raise HTTPException(
            status_code=400,
            detail="Alle Tage im Zeitraum haben bereits eine Abwesenheit dieses Typs"
        )

    # For vacation, check remaining vacation days (per year for cross-year ranges)
    if absence_data.type == AbsenceType.VACATION:
        # Group dates by year for budget check
        dates_by_year = {}
        for d in dates_to_create:
            dates_by_year.setdefault(d.year, []).append(d)
        for check_year, year_dates in dates_by_year.items():
            vacation_account = calculation_service.get_vacation_account(db, target_user, check_year)
            year_hours_needed = float(absence_data.hours) * len(year_dates)
            if year_hours_needed > vacation_account["remaining_hours"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Nicht genügend Urlaubstage für {check_year} ({vacation_account['remaining_days']:.1f} Tage verfügbar)"
                )

    # If sick leave with vacation refund: remove overlapping vacation entries first
    refunded_vacation_dates = []
    if absence_data.type == AbsenceType.SICK and absence_data.refund_vacation:
        for date in dates_to_create:
            vacation_entry = db.query(Absence).filter(
                Absence.user_id == target_user.id,
                Absence.date == date,
                Absence.type == AbsenceType.VACATION
            ).first()
            if vacation_entry:
                # Audit-Log: Urlaubsrückgabe dokumentieren
                audit_log = TimeEntryAuditLog(
                    time_entry_id=None,
                    user_id=target_user.id,
                    changed_by=current_user.id,
                    action="delete",
                    old_date=vacation_entry.date,
                    old_start_time=vacation_entry.start_time,
                    old_end_time=vacation_entry.end_time,
                    old_note=f"absence:{vacation_entry.type.value}:{float(vacation_entry.hours)}h",
                    source="vacation_refund",
                    tenant_id=current_user.tenant_id,
                )
                db.add(audit_log)
                db.delete(vacation_entry)
                refunded_vacation_dates.append(date)

    # Delete existing time entries on affected dates (unless keep_time_entries for mixed days)
    if not absence_data.keep_time_entries:
        existing_entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == target_user.id,
            TimeEntry.tenant_id == current_user.tenant_id,
            TimeEntry.date.in_(dates_to_create),
        ).all()
        for entry in existing_entries:
            _create_audit_log(
                db, entry.id, target_user.id, current_user.id,
                action="delete", old_entry=entry,
                source="absence_creation",
                tenant_id=current_user.tenant_id,
            )
            db.delete(entry)

    # Create absences for all dates
    created_absences = []
    for date in dates_to_create:
        # §3 EntgFG: for sick leave always credit the employee's scheduled daily hours,
        # not a caller-supplied value. For daily-schedule users, use their per-weekday
        # target; for standard users, derive from weekly_hours / work_days_per_week.
        if absence_data.type == AbsenceType.SICK or getattr(target_user, 'use_daily_schedule', False):
            weekly = calculation_service.get_weekly_hours_for_date(db, target_user, date)
            hours_for_day = float(calculation_service.get_daily_target_for_date(target_user, date, weekly_hours=weekly))
            if hours_for_day == 0:
                continue  # Skip days with 0 scheduled hours
        else:
            hours_for_day = absence_data.hours

        absence = Absence(
            user_id=target_user.id,
            tenant_id=current_user.tenant_id,
            date=date,
            end_date=end_date if absence_data.end_date else None,  # Store end_date for reference
            type=absence_data.type,
            hours=hours_for_day,
            start_time=absence_data.start_time,
            end_time=absence_data.end_time,
            note=absence_data.note
        )
        db.add(absence)
        created_absences.append(absence)

    db.commit()

    # Refresh all created absences
    for absence in created_absences:
        db.refresh(absence)

    return created_absences


@router.delete("/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_absence(
    absence_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an absence entry."""
    absence = db.query(Absence).filter(Absence.id == absence_id).first()

    if not absence:
        raise HTTPException(status_code=404, detail="Abwesenheit nicht gefunden")

    # Check permissions
    if absence.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    db.delete(absence)
    db.commit()

    return None
