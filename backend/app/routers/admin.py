from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List, Optional
from datetime import date, datetime, timezone
from app.database import get_db
from app.models import User, TimeEntry, WorkingHoursChange, ChangeRequest, ChangeRequestStatus, ChangeRequestType, TimeEntryAuditLog, UserRole
from app.middleware.auth import require_admin
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserCreateResponse, AdminSetPassword
from app.schemas.working_hours_change import WorkingHoursChangeCreate, WorkingHoursChangeResponse
from app.schemas.change_request import ChangeRequestResponse, ChangeRequestReview
from app.schemas.time_entry import TimeEntryCreate, TimeEntryResponse
from app.schemas.time_entry_audit_log import AuditLogResponse
from app.services import auth_service
from app.services.break_validation_service import validate_daily_break
from app.routers.time_entries import (
    _calculate_daily_net_hours, _is_night_work,
    MAX_DAILY_HOURS_HARD, MAX_NIGHT_WORKER_DAILY_WARN,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _get_field(entry, field: str):
    """Get a field from either an ORM object or a dict."""
    return getattr(entry, field, None) if hasattr(entry, field) else entry.get(field)


def _create_audit_log(
    db: Session,
    time_entry_id,
    user_id,
    changed_by,
    action: str,
    old_entry=None,
    new_entry=None,
    source: str = "manual",
    change_request_id=None,
):
    """Create an audit log entry for a time entry change."""
    log = TimeEntryAuditLog(
        time_entry_id=time_entry_id,
        user_id=user_id,
        changed_by=changed_by,
        action=action,
        source=source,
        change_request_id=change_request_id,
    )
    if old_entry:
        log.old_date = _get_field(old_entry, 'date')
        log.old_start_time = _get_field(old_entry, 'start_time')
        log.old_end_time = _get_field(old_entry, 'end_time')
        log.old_break_minutes = _get_field(old_entry, 'break_minutes')
        log.old_note = _get_field(old_entry, 'note')
    if new_entry:
        log.new_date = _get_field(new_entry, 'date')
        log.new_start_time = _get_field(new_entry, 'start_time')
        log.new_end_time = _get_field(new_entry, 'end_time')
        log.new_break_minutes = _get_field(new_entry, 'break_minutes')
        log.new_note = _get_field(new_entry, 'note')
    db.add(log)
    return log


def _enrich_cr_response(cr: ChangeRequest, db: Session) -> ChangeRequestResponse:
    """Add user names to the change request response."""
    response = ChangeRequestResponse.model_validate(cr)
    user = db.query(User).filter(User.id == cr.user_id).first()
    if user:
        response.user_first_name = user.first_name
        response.user_last_name = user.last_name
    if cr.reviewed_by:
        reviewer = db.query(User).filter(User.id == cr.reviewed_by).first()
        if reviewer:
            response.reviewer_first_name = reviewer.first_name
            response.reviewer_last_name = reviewer.last_name
    return response


def _enrich_audit_response(log: TimeEntryAuditLog, db: Session) -> AuditLogResponse:
    """Add user names to the audit log response."""
    response = AuditLogResponse.model_validate(log)
    user = db.query(User).filter(User.id == log.user_id).first()
    if user:
        response.user_first_name = user.first_name
        response.user_last_name = user.last_name
    changer = db.query(User).filter(User.id == log.changed_by).first()
    if changer:
        response.changed_by_first_name = changer.first_name
        response.changed_by_last_name = changer.last_name
    return response


# ── User Management ──────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserResponse])
def list_users(
    include_inactive: bool = False,
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List users (admin only). By default only active, visible users."""
    query = db.query(User)
    if not include_inactive:
        query = query.filter(User.is_active == True)
    if not include_hidden:
        query = query.filter(User.is_hidden == False)
    users = query.order_by(User.last_name, User.first_name).all()
    return users


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Get a specific user by ID (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    return user


@router.post("/users", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_data: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Create a new user (admin only)."""
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Benutzername bereits vergeben")

    new_user = User(
        username=user_data.username,
        email=user_data.email or None,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        role=user_data.role,
        weekly_hours=user_data.weekly_hours,
        vacation_days=user_data.vacation_days,
        work_days_per_week=user_data.work_days_per_week,
        track_hours=user_data.track_hours,
        calendar_color=user_data.calendar_color,
        use_daily_schedule=user_data.use_daily_schedule,
        hours_monday=user_data.hours_monday,
        hours_tuesday=user_data.hours_tuesday,
        hours_wednesday=user_data.hours_wednesday,
        hours_thursday=user_data.hours_thursday,
        hours_friday=user_data.hours_friday,
        password_hash=auth_service.hash_password(user_data.password),
        is_active=True,
        exempt_from_arbzg=user_data.exempt_from_arbzg,
        is_night_worker=user_data.is_night_worker,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return UserCreateResponse(
        user=UserResponse.model_validate(new_user)
    )


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update user data (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    if user_data.username and user_data.username != user.username:
        existing = db.query(User).filter(User.username == user_data.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Benutzername bereits vergeben")

    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/set-password")
def set_password(
    user_id: str,
    body: AdminSetPassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Set a new password for a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.password_hash = auth_service.hash_password(body.password)
    user.token_version += 1  # Invalidate all existing tokens
    db.commit()

    return {"message": f"Passwort für {user.first_name} {user.last_name} wurde gesetzt"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Deactivate a user (soft delete, admin only)."""
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="Sie können sich nicht selbst deaktivieren")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.is_active = False
    user.token_version += 1  # Invalidate all existing tokens
    db.commit()
    return None


@router.post("/users/{user_id}/reactivate", response_model=UserResponse)
def reactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Reactivate a previously deactivated user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/toggle-hidden", response_model=UserResponse)
def toggle_hidden_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Toggle the is_hidden flag for a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.is_hidden = not user.is_hidden
    db.commit()
    db.refresh(user)
    return user


# ── Working Hours Changes ────────────────────────────────────────────────

@router.get("/users/{user_id}/working-hours-changes", response_model=List[WorkingHoursChangeResponse])
def list_working_hours_changes(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get working hours change history for a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id
    ).order_by(WorkingHoursChange.effective_from.desc()).all()
    return changes


@router.post("/users/{user_id}/working-hours-changes", response_model=WorkingHoursChangeResponse, status_code=status.HTTP_201_CREATED)
def create_working_hours_change(
    user_id: str,
    change_data: WorkingHoursChangeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new working hours change for a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    existing = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.effective_from == change_data.effective_from
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Eine Stundenänderung für den {change_data.effective_from.strftime('%d.%m.%Y')} existiert bereits"
        )

    change = WorkingHoursChange(
        user_id=user_id,
        effective_from=change_data.effective_from,
        weekly_hours=change_data.weekly_hours,
        note=change_data.note
    )
    db.add(change)

    if change_data.effective_from <= date.today():
        most_recent = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user_id,
            WorkingHoursChange.effective_from <= date.today()
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
        if most_recent:
            user.weekly_hours = most_recent.weekly_hours

    db.commit()
    db.refresh(change)
    return change


@router.delete("/users/{user_id}/working-hours-changes/{change_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_working_hours_change(
    user_id: str,
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a working hours change (admin only)."""
    change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.id == change_id,
        WorkingHoursChange.user_id == user_id
    ).first()

    if not change:
        raise HTTPException(status_code=404, detail="Stundenänderung nicht gefunden")

    user = db.query(User).filter(User.id == user_id).first()
    db.delete(change)
    db.commit()

    most_recent = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.effective_from <= date.today()
    ).order_by(WorkingHoursChange.effective_from.desc()).first()

    if most_recent:
        user.weekly_hours = most_recent.weekly_hours
        db.commit()

    return None


# ── Change Request Management (Admin) ───────────────────────────────────

@router.get("/change-requests", response_model=List[ChangeRequestResponse])
def list_all_change_requests(
    request_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all change requests (admin view)."""
    query = db.query(ChangeRequest)
    if request_status:
        query = query.filter(ChangeRequest.status == request_status)
    if user_id:
        query = query.filter(ChangeRequest.user_id == user_id)
    requests = query.order_by(ChangeRequest.created_at.desc()).all()
    return [_enrich_cr_response(cr, db) for cr in requests]


@router.get("/change-requests/{request_id}", response_model=ChangeRequestResponse)
def get_change_request_admin(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get a specific change request (admin view)."""
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    return _enrich_cr_response(cr, db)


@router.post("/change-requests/{request_id}/review", response_model=ChangeRequestResponse)
def review_change_request(
    request_id: str,
    review: ChangeRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Approve or reject a change request."""
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    if cr.status != ChangeRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Antrag wurde bereits bearbeitet")

    if review.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Ungültige Aktion (approve/reject)")

    if review.action == "reject":
        cr.status = ChangeRequestStatus.REJECTED
        cr.reviewed_by = current_user.id
        cr.reviewed_at = datetime.now(timezone.utc)
        cr.rejection_reason = review.rejection_reason
        db.commit()
        db.refresh(cr)
        return _enrich_cr_response(cr, db)

    # Approve: apply the change
    cr.status = ChangeRequestStatus.APPROVED
    cr.reviewed_by = current_user.id
    cr.reviewed_at = datetime.now(timezone.utc)

    if cr.request_type == ChangeRequestType.CREATE:
        # Create new time entry
        entry = TimeEntry(
            user_id=cr.user_id,
            date=cr.proposed_date,
            start_time=cr.proposed_start_time,
            end_time=cr.proposed_end_time,
            break_minutes=cr.proposed_break_minutes or 0,
            note=cr.proposed_note,
        )
        db.add(entry)
        db.flush()  # Get the entry ID
        cr.time_entry_id = entry.id
        _create_audit_log(
            db, entry.id, cr.user_id, current_user.id,
            action="create", new_entry=entry,
            source="change_request", change_request_id=cr.id,
        )

    elif cr.request_type == ChangeRequestType.UPDATE:
        entry = db.query(TimeEntry).filter(TimeEntry.id == cr.time_entry_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Zeiteintrag nicht mehr vorhanden")
        # Audit log with old values
        _create_audit_log(
            db, entry.id, cr.user_id, current_user.id,
            action="update", old_entry=entry,
            new_entry={
                "date": cr.proposed_date,
                "start_time": cr.proposed_start_time,
                "end_time": cr.proposed_end_time,
                "break_minutes": cr.proposed_break_minutes,
                "note": cr.proposed_note,
            },
            source="change_request", change_request_id=cr.id,
        )
        # Apply changes
        entry.date = cr.proposed_date
        entry.start_time = cr.proposed_start_time
        entry.end_time = cr.proposed_end_time
        entry.break_minutes = cr.proposed_break_minutes if cr.proposed_break_minutes is not None else entry.break_minutes
        if cr.proposed_note is not None:
            entry.note = cr.proposed_note

    elif cr.request_type == ChangeRequestType.DELETE:
        entry = db.query(TimeEntry).filter(TimeEntry.id == cr.time_entry_id).first()
        if entry:
            _create_audit_log(
                db, entry.id, cr.user_id, current_user.id,
                action="delete", old_entry=entry,
                source="change_request", change_request_id=cr.id,
            )
            db.delete(entry)

    db.commit()
    db.refresh(cr)

    cr_response = _enrich_cr_response(cr, db)

    # §6 Abs. 2 ArbZG: Warnung für Nachtarbeitnehmer bei Genehmigung
    if (
        review.action == "approve"
        and cr.request_type in (ChangeRequestType.CREATE, ChangeRequestType.UPDATE)
        and cr.proposed_start_time
        and cr.proposed_end_time
    ):
        cr_user = db.query(User).filter(User.id == cr.user_id).first()
        if cr_user and cr_user.is_night_worker:
            daily_hours_cr = _calculate_daily_net_hours(
                db=db,
                user_id=cr.user_id,
                entry_date=cr.proposed_date,
                start_time=cr.proposed_start_time,
                end_time=cr.proposed_end_time,
                break_minutes=cr.proposed_break_minutes or 0,
            )
            if (
                _is_night_work(cr.proposed_start_time, cr.proposed_end_time)
                and daily_hours_cr > MAX_NIGHT_WORKER_DAILY_WARN
            ):
                cr_response.warnings.append(
                    f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours_cr:.1f}h). "
                    "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
                )

    return cr_response


# ── Admin Time Entry Management ─────────────────────────────────────────

@router.post("/users/{user_id}/time-entries", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def admin_create_time_entry(
    user_id: str,
    entry_data: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin creates a time entry for an employee."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # Break validation (§4 ArbZG)
    break_error = validate_daily_break(
        db=db, user_id=user.id, entry_date=entry_data.date,
        start_time=entry_data.start_time, end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes,
    )
    if break_error:
        raise HTTPException(status_code=400, detail=break_error)

    # §3 ArbZG: daily hours hard limit
    daily_hours = _calculate_daily_net_hours(
        db=db, user_id=user.id, entry_date=entry_data.date,
        start_time=entry_data.start_time, end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes,
    )
    if daily_hours > MAX_DAILY_HOURS_HARD:
        raise HTTPException(
            status_code=422,
            detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
        )

    admin_create_warnings: list[str] = []
    if (
        user.is_night_worker
        and _is_night_work(entry_data.start_time, entry_data.end_time)
        and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
    ):
        admin_create_warnings.append(
            f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
            "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
        )

    entry = TimeEntry(
        user_id=user.id,
        date=entry_data.date,
        start_time=entry_data.start_time,
        end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes,
        note=entry_data.note,
    )
    db.add(entry)
    db.flush()

    _create_audit_log(
        db, entry.id, user.id, current_user.id,
        action="create", new_entry=entry, source="manual",
    )

    db.commit()
    db.refresh(entry)
    response = TimeEntryResponse.model_validate(entry)
    response.warnings = admin_create_warnings
    return response


@router.put("/time-entries/{entry_id}", response_model=TimeEntryResponse)
def admin_update_time_entry(
    entry_id: str,
    entry_data: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin updates a time entry with audit logging."""
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Break validation (§4 ArbZG)
    break_error = validate_daily_break(
        db=db, user_id=entry.user_id, entry_date=entry_data.date,
        start_time=entry_data.start_time, end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes, exclude_entry_id=entry.id,
    )
    if break_error:
        raise HTTPException(status_code=400, detail=break_error)

    # §3 ArbZG: daily hours hard limit
    daily_hours = _calculate_daily_net_hours(
        db=db, user_id=entry.user_id, entry_date=entry_data.date,
        start_time=entry_data.start_time, end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes, exclude_entry_id=entry.id,
    )
    if daily_hours > MAX_DAILY_HOURS_HARD:
        raise HTTPException(
            status_code=422,
            detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
        )

    # Create audit log before changing
    _create_audit_log(
        db, entry.id, entry.user_id, current_user.id,
        action="update", old_entry=entry,
        new_entry={
            "date": entry_data.date,
            "start_time": entry_data.start_time,
            "end_time": entry_data.end_time,
            "break_minutes": entry_data.break_minutes,
            "note": entry_data.note,
        },
        source="manual",
    )

    entry.date = entry_data.date
    entry.start_time = entry_data.start_time
    entry.end_time = entry_data.end_time
    entry.break_minutes = entry_data.break_minutes
    entry.note = entry_data.note

    db.commit()
    db.refresh(entry)

    admin_update_warnings: list[str] = []
    affected_user = db.query(User).filter(User.id == entry.user_id).first()
    if (
        affected_user
        and affected_user.is_night_worker
        and _is_night_work(entry.start_time, entry.end_time)
        and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
    ):
        admin_update_warnings.append(
            f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
            "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
        )

    response = TimeEntryResponse.model_validate(entry)
    response.warnings = admin_update_warnings
    return response


@router.delete("/time-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_time_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin deletes a time entry with audit logging."""
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    _create_audit_log(
        db, entry.id, entry.user_id, current_user.id,
        action="delete", old_entry=entry, source="manual",
    )

    db.delete(entry)
    db.commit()
    return None


# ── Audit Log ────────────────────────────────────────────────────────────

@router.get("/audit-log", response_model=List[AuditLogResponse])
def list_audit_log(
    user_id: Optional[str] = Query(None, description="Filter by affected user"),
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List audit log entries."""
    query = db.query(TimeEntryAuditLog)

    if user_id:
        query = query.filter(TimeEntryAuditLog.user_id == user_id)

    if month:
        try:
            year, month_num = map(int, month.split('-'))
            query = query.filter(
                extract('year', TimeEntryAuditLog.created_at) == year,
                extract('month', TimeEntryAuditLog.created_at) == month_num,
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    logs = query.order_by(TimeEntryAuditLog.created_at.desc()).all()
    return [_enrich_audit_response(log, db) for log in logs]
