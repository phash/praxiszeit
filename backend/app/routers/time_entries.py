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
from uuid import UUID as UUIDType

router = APIRouter(prefix="/api/time-entries", tags=["time-entries"])


MAX_DAILY_HOURS_HARD = 10.0         # §3 ArbZG: absolute Obergrenze
MAX_DAILY_HOURS_WARN = 8.0          # §3 ArbZG: Regelgrenze (Warnung)
MAX_WEEKLY_HOURS_WARN = 48.0        # §3 ArbZG: 6 Werktage × 8h Durchschnitt = 48h/Woche
MAX_NIGHT_WORKER_DAILY_WARN = 8.0   # §6 Abs. 2 ArbZG: Tageslimit für Nachtarbeitnehmer
NIGHT_THRESHOLD_MINUTES = 120       # §2 Abs. 4 ArbZG: mind. 2h Nachtzeit = Nachtarbeit
NIGHT_START = time(23, 0)
NIGHT_END   = time(6, 0)


def _calculate_daily_net_hours(
    db: Session,
    user_id: UUIDType,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    exclude_entry_id=None,
) -> float:
    """Sum up all net hours for a user on a given date, including the new/updated entry."""
    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.date == entry_date,
        TimeEntry.end_time.isnot(None),
    )
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    existing = query.all()

    def net_h(st: time, et: time, brk: int) -> float:
        mins = (et.hour * 60 + et.minute) - (st.hour * 60 + st.minute)
        return max(0.0, (mins - brk) / 60.0)

    total = sum(net_h(e.start_time, e.end_time, e.break_minutes) for e in existing)
    total += net_h(start_time, end_time, break_minutes)
    return total


def _calculate_weekly_net_hours(
    db: Session,
    user_id: UUIDType,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    exclude_entry_id=None,
) -> float:
    """Sum all net hours for the ISO calendar week containing entry_date, including the new/updated entry."""
    from datetime import timedelta
    iso = entry_date.isocalendar()
    # Monday of that ISO week
    monday = entry_date - timedelta(days=entry_date.weekday())
    sunday = monday + timedelta(days=6)

    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.date >= monday,
        TimeEntry.date <= sunday,
        TimeEntry.end_time.isnot(None),
    )
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    existing = query.all()

    def net_h(st: time, et: time, brk: int) -> float:
        mins = (et.hour * 60 + et.minute) - (st.hour * 60 + st.minute)
        return max(0.0, (mins - brk) / 60.0)

    total = sum(net_h(e.start_time, e.end_time, e.break_minutes) for e in existing)
    total += net_h(start_time, end_time, break_minutes)
    return total


def _is_night_work(start_time: time, end_time: time) -> bool:
    """Gibt True zurück wenn >2h Nachtzeit (23:00–06:00) überschnitten werden (§2 Abs. 4 ArbZG)."""
    def to_min(t: time) -> int:
        return t.hour * 60 + t.minute

    s = to_min(start_time)
    e = to_min(end_time)
    if e <= s:  # Mitternachtsübergang
        e += 1440

    # Nachtzeit-Segmente in Minuten seit Tagesbeginn:
    # 0–360 = 00:00–06:00, 1380–1440 = 23:00–24:00, 1440–1800 = 00:00–06:00 (Folgetag)
    night_minutes = 0
    night_minutes += max(0, min(e, 360) - max(s, 0))       # 00:00–06:00
    night_minutes += max(0, min(e, 1440) - max(s, 1380))   # 23:00–24:00
    night_minutes += max(0, min(e, 1800) - max(s, 1440))   # 00:00–06:00 (nach Mitternacht)
    return night_minutes > NIGHT_THRESHOLD_MINUTES


def _enrich_response(
    response: "TimeEntryResponse",
    entry: TimeEntry,
    current_user: User,
    db: Session,
    warnings: "list[str] | None" = None,
) -> "TimeEntryResponse":
    """Set computed fields on a TimeEntryResponse."""
    response.is_editable = _compute_is_editable(entry, current_user)
    weekday = entry.date.weekday()
    holiday = is_holiday(db, entry.date)
    response.is_sunday_or_holiday = weekday == 6 or bool(holiday)
    response.is_night_work = (
        _is_night_work(entry.start_time, entry.end_time)
        if entry.end_time else False
    )
    response.warnings = warnings or []
    return response


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
    _enrich_response(response_entry, open_entry, current_user, db)

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
    new_end_time = now.time().replace(second=0, microsecond=0)
    exempt = current_user.exempt_from_arbzg

    # §3 ArbZG: check daily hours before committing – skipped for exempt users
    daily_hours = _calculate_daily_net_hours(
        db=db,
        user_id=current_user.id,
        entry_date=open_entry.date,
        start_time=open_entry.start_time,
        end_time=new_end_time,
        break_minutes=body.break_minutes,
        exclude_entry_id=open_entry.id,
    )
    if not exempt and daily_hours > MAX_DAILY_HOURS_HARD:
        raise HTTPException(
            status_code=422,
            detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
        )

    open_entry.end_time = new_end_time
    open_entry.break_minutes = body.break_minutes
    if body.note:
        open_entry.note = body.note

    db.commit()
    db.refresh(open_entry)

    clock_out_warnings: list[str] = []
    if not exempt:
        if daily_hours > MAX_DAILY_HOURS_WARN:
            clock_out_warnings.append("DAILY_HOURS_WARNING")
        weekly_hours_out = _calculate_weekly_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=open_entry.date,
            start_time=open_entry.start_time,
            end_time=new_end_time,
            break_minutes=body.break_minutes,
            exclude_entry_id=open_entry.id,
        )
        if weekly_hours_out > MAX_WEEKLY_HOURS_WARN:
            clock_out_warnings.append("WEEKLY_HOURS_WARNING")
        if open_entry.date.weekday() == 6:
            clock_out_warnings.append("SUNDAY_WORK")
        if is_holiday(db, open_entry.date):
            clock_out_warnings.append("HOLIDAY_WORK")
        if (
            current_user.is_night_worker
            and _is_night_work(open_entry.start_time, new_end_time)
            and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            clock_out_warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    response = TimeEntryResponse.model_validate(open_entry)
    _enrich_response(response, open_entry, current_user, db, warnings=clock_out_warnings)
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

    results = []
    for entry in entries:
        response = TimeEntryResponse.model_validate(entry)
        _enrich_response(response, entry, current_user, db)
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
    _enrich_response(response, entry, current_user, db)
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

    exempt = current_user.exempt_from_arbzg

    # Break validation (ArbZG §4) – skipped for exempt users
    if not exempt:
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

    # §3 ArbZG: daily hours check – skipped for exempt users
    daily_hours = _calculate_daily_net_hours(
        db=db,
        user_id=current_user.id,
        entry_date=entry_data.date,
        start_time=entry_data.start_time,
        end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes,
    )
    if not exempt and daily_hours > MAX_DAILY_HOURS_HARD:
        raise HTTPException(
            status_code=422,
            detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG)."
        )

    # Collect warnings (also skipped for exempt users)
    warnings: list[str] = []
    if not exempt:
        if daily_hours > MAX_DAILY_HOURS_WARN:
            warnings.append("DAILY_HOURS_WARNING")
        weekly_hours = _calculate_weekly_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=entry_data.date,
            start_time=entry_data.start_time,
            end_time=entry_data.end_time,
            break_minutes=entry_data.break_minutes,
        )
        if weekly_hours > MAX_WEEKLY_HOURS_WARN:
            warnings.append("WEEKLY_HOURS_WARNING")
        weekday = entry_data.date.weekday()
        is_sunday = weekday == 6
        holiday = is_holiday(db, entry_data.date)
        if is_sunday:
            warnings.append("SUNDAY_WORK")
        if holiday:
            warnings.append("HOLIDAY_WORK")
        if (
            current_user.is_night_worker
            and _is_night_work(entry_data.start_time, entry_data.end_time)
            and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    # Create entry
    entry = TimeEntry(
        user_id=current_user.id,
        date=entry_data.date,
        start_time=entry_data.start_time,
        end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes,
        note=entry_data.note,
        sunday_exception_reason=entry_data.sunday_exception_reason,
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    response = TimeEntryResponse.model_validate(entry)
    _enrich_response(response, entry, current_user, db, warnings=warnings)
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

    exempt = current_user.exempt_from_arbzg

    # Break validation (ArbZG §4) – skipped for exempt users
    if not exempt and entry.end_time is not None:
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

    # §3 ArbZG: daily hours check – skipped for exempt users
    if not exempt and entry.end_time is not None:
        daily_hours = _calculate_daily_net_hours(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=entry.id,
        )
        if daily_hours > MAX_DAILY_HOURS_HARD:
            raise HTTPException(
                status_code=422,
                detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG)."
            )

    db.commit()
    db.refresh(entry)

    update_warnings: list[str] = []
    if not exempt and entry.end_time is not None:
        saved_hours = _calculate_daily_net_hours(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=None,
        )
        if saved_hours > MAX_DAILY_HOURS_WARN:
            update_warnings.append("DAILY_HOURS_WARNING")
        weekly = _calculate_weekly_net_hours(
            db=db,
            user_id=entry.user_id,
            entry_date=entry.date,
            start_time=entry.start_time,
            end_time=entry.end_time,
            break_minutes=entry.break_minutes,
            exclude_entry_id=None,
        )
        if weekly > MAX_WEEKLY_HOURS_WARN:
            update_warnings.append("WEEKLY_HOURS_WARNING")

    if not exempt:
        entry_weekday = entry.date.weekday()
        if entry_weekday == 6:
            update_warnings.append("SUNDAY_WORK")
        entry_is_holiday = is_holiday(db, entry.date)
        if entry_is_holiday:
            update_warnings.append("HOLIDAY_WORK")
        if (
            entry.end_time is not None
            and current_user.is_night_worker
            and _is_night_work(entry.start_time, entry.end_time)
            and saved_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            update_warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({saved_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    response = TimeEntryResponse.model_validate(entry)
    _enrich_response(response, entry, current_user, db, warnings=update_warnings)
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
