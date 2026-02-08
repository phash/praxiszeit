from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract, and_
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.models import User, TimeEntry, UserRole
from app.middleware.auth import get_current_user
from app.schemas.time_entry import TimeEntryCreate, TimeEntryUpdate, TimeEntryResponse
from app.services.holiday_service import is_holiday

router = APIRouter(prefix="/api/time-entries", tags=["time-entries"])


@router.get("/", response_model=List[TimeEntryResponse])
def list_time_entries(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List time entries.
    Regular users can only see their own entries.
    Admins can filter by user_id.
    """
    query = db.query(TimeEntry)

    # If user_id is provided, only admin can filter by it
    if user_id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
        query = query.filter(TimeEntry.user_id == user_id)
    else:
        # Regular users only see their own entries
        query = query.filter(TimeEntry.user_id == current_user.id)

    # Filter by month if provided
    if month:
        try:
            year, month_num = map(int, month.split('-'))
            query = query.filter(
                extract('year', TimeEntry.date) == year,
                extract('month', TimeEntry.date) == month_num
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    entries = query.order_by(TimeEntry.date.desc(), TimeEntry.start_time.desc()).all()
    return entries


@router.get("/{entry_id}", response_model=TimeEntryResponse)
def get_time_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific time entry."""
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Check permissions
    if entry.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    return entry


@router.post("/", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def create_time_entry(
    entry_data: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new time entry."""

    # Check for overlapping entries on the same date
    existing = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.date == entry_data.date,
        TimeEntry.start_time == entry_data.start_time
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Es existiert bereits ein Eintrag mit dieser Startzeit an diesem Datum"
        )

    # Warning if it's a weekend or holiday
    weekday = entry_data.date.weekday()
    if weekday >= 5:
        # It's a weekend - could add a warning mechanism
        pass

    if is_holiday(db, entry_data.date):
        # It's a public holiday - could add a warning
        pass

    # Create entry
    entry = TimeEntry(
        user_id=current_user.id,
        date=entry_data.date,
        start_time=entry_data.start_time,
        end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes,
        note=entry_data.note
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry


@router.put("/{entry_id}", response_model=TimeEntryResponse)
def update_time_entry(
    entry_id: str,
    entry_data: TimeEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a time entry."""
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Check permissions
    if entry.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    # Update fields
    update_data = entry_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    # Validate end_time > start_time
    if entry.end_time <= entry.start_time:
        raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

    db.commit()
    db.refresh(entry)

    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a time entry."""
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Check permissions
    if entry.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    db.delete(entry)
    db.commit()

    return None
