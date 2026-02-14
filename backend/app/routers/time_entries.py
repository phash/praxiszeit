from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract, and_
from typing import List, Optional
from datetime import datetime, date, time
from app.database import get_db
from app.models import User, TimeEntry, UserRole
from app.middleware.auth import get_current_user
from app.schemas.time_entry import (
    TimeEntryCreate, TimeEntryUpdate, TimeEntryResponse,
    ClockInRequest, ClockOutRequest, ClockStatusResponse,
)
from app.services.holiday_service import is_holiday
from app.services.break_validation_service import validate_daily_break

router = APIRouter(prefix="/api/time-entries", tags=["time-entries"])


def _compute_is_editable(entry: TimeEntry, current_user: User) -> bool:
    """Check if a time entry is editable by the current user."""
    if current_user.role == UserRole.ADMIN:
        return True
    return entry.date == date.today()


def _get_open_entry(db: Session, user_id) -> Optional[TimeEntry]:
    """Find an open (clocked-in, no end_time) entry for the user."""
    return db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.end_time.is_(None),
    ).first()


def _close_stale_entry(db: Session, entry: TimeEntry) -> None:
    """Close a stale open entry at 23:59 of its date."""
    entry.end_time = time(23, 59)
    entry.note = (entry.note or '') + ' [auto-closed]'
    if entry.note.startswith(' '):
        entry.note = entry.note.strip()
    db.commit()


# --- Clock endpoints (must be BEFORE /{entry_id} to avoid route conflicts) ---

@router.get("/clock-status", response_model=ClockStatusResponse)
def get_clock_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current clock-in/out status for the authenticated user."""
    open_entry = _get_open_entry(db, current_user.id)

    if not open_entry:
        return ClockStatusResponse(is_clocked_in=False)

    # If the open entry is from a previous day, auto-close it
    if open_entry.date != date.today():
        _close_stale_entry(db, open_entry)
        return ClockStatusResponse(is_clocked_in=False)

    # Calculate elapsed minutes
    now = datetime.now()
    start_dt = datetime.combine(open_entry.date, open_entry.start_time)
    elapsed = int((now - start_dt).total_seconds() / 60)

    response_entry = TimeEntryResponse.model_validate(open_entry)
    response_entry.is_editable = _compute_is_editable(open_entry, current_user)

    return ClockStatusResponse(
        is_clocked_in=True,
        current_entry=response_entry,
        elapsed_minutes=elapsed,
    )


@router.post("/clock-in", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def clock_in(
    body: ClockInRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clock in: create a time entry with start_time=now, end_time=NULL."""
    # Check for existing open entry
    open_entry = _get_open_entry(db, current_user.id)
    if open_entry:
        if open_entry.date != date.today():
            # Stale entry from a previous day: auto-close
            _close_stale_entry(db, open_entry)
        else:
            raise HTTPException(
                status_code=400,
                detail="Bereits eingestempelt. Bitte zuerst ausstempeln.",
            )

    now = datetime.now()
    entry = TimeEntry(
        user_id=current_user.id,
        date=now.date(),
        start_time=now.time().replace(second=0, microsecond=0),
        end_time=None,
        break_minutes=0,
        note=body.note,
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    response = TimeEntryResponse.model_validate(entry)
    response.is_editable = True
    return response


@router.post("/clock-out", response_model=TimeEntryResponse)
def clock_out(
    body: ClockOutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clock out: set end_time=now and break_minutes on the open entry."""
    open_entry = _get_open_entry(db, current_user.id)

    if not open_entry:
        raise HTTPException(
            status_code=400,
            detail="Nicht eingestempelt. Bitte zuerst einstempeln.",
        )

    # If stale entry from a previous day, auto-close and error
    if open_entry.date != date.today():
        _close_stale_entry(db, open_entry)
        raise HTTPException(
            status_code=400,
            detail="Offener Eintrag von einem früheren Tag wurde automatisch geschlossen. Bitte neu einstempeln.",
        )

    now = datetime.now()
    open_entry.end_time = now.time().replace(second=0, microsecond=0)
    open_entry.break_minutes = body.break_minutes
    if body.note:
        open_entry.note = body.note

    db.commit()
    db.refresh(open_entry)

    response = TimeEntryResponse.model_validate(open_entry)
    response.is_editable = _compute_is_editable(open_entry, current_user)
    return response


# --- Standard CRUD endpoints ---

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

    # Add is_editable flag to each entry
    results = []
    for entry in entries:
        response = TimeEntryResponse.model_validate(entry)
        response.is_editable = _compute_is_editable(entry, current_user)
        results.append(response)

    return results


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

    response = TimeEntryResponse.model_validate(entry)
    response.is_editable = _compute_is_editable(entry, current_user)
    return response


@router.post("/", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def create_time_entry(
    entry_data: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new time entry."""

    # Edit protection: employees can only create entries for today
    if current_user.role != UserRole.ADMIN and entry_data.date != date.today():
        raise HTTPException(
            status_code=403,
            detail="Einträge für vergangene Tage können nur per Änderungsantrag erstellt werden"
        )

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

    # Break validation (ArbZG §4)
    break_error = validate_daily_break(
        db=db,
        user_id=current_user.id,
        entry_date=entry_data.date,
        start_time=entry_data.start_time,
        end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes,
    )
    if break_error:
        raise HTTPException(status_code=400, detail=break_error)

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

    response = TimeEntryResponse.model_validate(entry)
    response.is_editable = _compute_is_editable(entry, current_user)
    return response


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

    # Edit protection: employees can only edit today's entries
    if current_user.role != UserRole.ADMIN and entry.date != date.today():
        raise HTTPException(
            status_code=403,
            detail="Einträge vergangener Tage können nur per Änderungsantrag geändert werden"
        )

    # Update fields
    update_data = entry_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    # Validate end_time > start_time (only if both are set)
    if entry.end_time is not None and entry.end_time <= entry.start_time:
        raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

    # Break validation (ArbZG §4) - only if entry is complete
    if entry.end_time is not None:
        break_error = validate_daily_break(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=entry.id,
        )
        if break_error:
            raise HTTPException(status_code=400, detail=break_error)

    db.commit()
    db.refresh(entry)

    response = TimeEntryResponse.model_validate(entry)
    response.is_editable = _compute_is_editable(entry, current_user)
    return response


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

    # Edit protection: employees can only delete today's entries
    if current_user.role != UserRole.ADMIN and entry.date != date.today():
        raise HTTPException(
            status_code=403,
            detail="Einträge vergangener Tage können nur per Änderungsantrag gelöscht werden"
        )

    db.delete(entry)
    db.commit()

    return None
