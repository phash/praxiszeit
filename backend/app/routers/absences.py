from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List, Optional
from datetime import timedelta
from app.database import get_db
from app.models import User, Absence, AbsenceType, UserRole, PublicHoliday
from app.middleware.auth import get_current_user
from app.schemas.absence import AbsenceCreate, AbsenceResponse, AbsenceCalendarEntry
from app.services import calculation_service

router = APIRouter(prefix="/api/absences", tags=["absences"])


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

    # Get all absences for the month
    absences = db.query(Absence).join(User).filter(
        User.is_active == True,
        extract('year', Absence.date) == year,
        extract('month', Absence.date) == month_num
    ).order_by(Absence.date).all()

    # Convert to calendar entries
    calendar_entries = []
    for absence in absences:
        user = db.query(User).filter(User.id == absence.user_id).first()
        if user:
            calendar_entries.append(AbsenceCalendarEntry(
                date=absence.date,
                user_first_name=user.first_name,
                user_last_name=user.last_name,
                type=absence.type,
                hours=absence.hours
            ))

    return calendar_entries


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

    # Determine date range
    start_date = absence_data.date
    end_date = absence_data.end_date if absence_data.end_date else absence_data.date

    # Validate date range
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="Enddatum muss nach dem Startdatum liegen"
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

    # Check for existing absences
    for date in dates_to_create:
        existing = db.query(Absence).filter(
            Absence.user_id == current_user.id,
            Absence.date == date,
            Absence.type == absence_data.type
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Es existiert bereits eine Abwesenheit dieses Typs am {date.strftime('%d.%m.%Y')}"
            )

    # For vacation, check remaining vacation days
    if absence_data.type == AbsenceType.VACATION:
        vacation_account = calculation_service.get_vacation_account(
            db, current_user, start_date.year
        )
        total_hours_needed = absence_data.hours * len(dates_to_create)
        new_remaining = vacation_account['remaining_hours'] - total_hours_needed

        if new_remaining < 0:
            # Warning but don't block (could require admin approval in production)
            pass

    # Create absences for all dates
    created_absences = []
    for date in dates_to_create:
        absence = Absence(
            user_id=current_user.id,
            date=date,
            end_date=end_date if absence_data.end_date else None,  # Store end_date for reference
            type=absence_data.type,
            hours=absence_data.hours,
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
