"""Admin sub-router: User Management + Working Hours Changes."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timezone, timedelta
from app.services.timezone_service import today_local
from app.database import get_db
from app.models import User, TimeEntry, Absence, WorkingHoursChange, ChangeRequest, TimeEntryAuditLog, UserRole
from app.middleware.auth import require_admin
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserCreateResponse, AdminSetPassword, UserListResponse
from app.schemas.working_hours_change import WorkingHoursChangeCreate, WorkingHoursChangeResponse
from app.services import auth_service

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ── User Management ──────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserListResponse])
def list_users(
    include_inactive: bool = False,
    include_hidden: bool = False,
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List users (admin only). By default only active, visible users."""
    query = db.query(User)
    if not include_inactive:
        query = query.filter(User.is_active == True)
    if not include_hidden:
        query = query.filter(User.is_hidden == False)
    users = query.order_by(User.last_name, User.first_name).offset(skip).limit(limit).all()
    return users


@router.get("/users/deletion-candidates")
def get_deletion_candidates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """DSGVO Art. 17: List inactive users with anonymization/purge eligibility."""
    inactive_users = db.query(User).filter(User.is_active == False).order_by(User.last_name, User.first_name).all()

    today = today_local()
    result = []

    for user in inactive_users:
        last_entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id
        ).order_by(TimeEntry.date.desc()).first()

        last_entry_date = last_entry.date if last_entry else None
        days_since = (today - last_entry_date).days if last_entry_date else None
        is_anonymized = user.username.startswith("deleted_")

        # Grace-Period-Berechnung (14 Tage nach Deaktivierung)
        grace_period_remaining = None
        grace_period_ends = None
        in_grace_period = False
        if user.deactivated_at is not None:
            days_deactivated = (today - user.deactivated_at.date()).days
            if days_deactivated < 14:
                grace_period_remaining = 14 - days_deactivated
                grace_period_ends = (user.deactivated_at + timedelta(days=14)).date().isoformat()
                in_grace_period = True

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "is_anonymized": is_anonymized,
            "deactivated_at": user.deactivated_at.isoformat() if user.deactivated_at else None,
            "grace_period_ends": grace_period_ends,
            "grace_period_remaining_days": grace_period_remaining,
            "in_grace_period": in_grace_period,
            "last_entry_date": last_entry_date.isoformat() if last_entry_date else None,
            "days_since_last_entry": days_since,
            "can_anonymize": not is_anonymized and not in_grace_period,
            "can_purge": last_entry_date is None or (days_since is not None and days_since >= 730),
        })

    return result


@router.post("/users/{user_id}/anonymize")
def anonymize_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """DSGVO Art. 17: Anonymize an inactive user in-place. Keeps time entries (ArbZG SS16 -- 2-year retention), deletes absences."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    if user.is_active:
        raise HTTPException(status_code=400, detail="Benutzer muss zuerst deaktiviert werden (Art. 17 DSGVO)")
    if user.username.startswith("deleted_"):
        raise HTTPException(status_code=400, detail="Benutzer wurde bereits anonymisiert")

    # 14-Tage-Grace-Period: Anonymisierung erst nach Ablauf der Frist erlaubt
    if user.deactivated_at is not None:
        days_since_deactivation = (datetime.now(timezone.utc).date() - user.deactivated_at.date()).days
        if days_since_deactivation < 14:
            remaining = 14 - days_since_deactivation
            grace_end = (user.deactivated_at + timedelta(days=14)).strftime('%d.%m.%Y')
            raise HTTPException(
                status_code=400,
                detail=f"Sperrfrist läuft noch {remaining} Tag(e). Anonymisierung frühestens am {grace_end} möglich."
            )
    elif user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer muss zuerst deaktiviert werden"
        )
    # If deactivated_at is None but user is inactive: allow anonymization (legacy user)

    user.first_name = "Gelöschter"
    user.last_name = "Benutzer"
    user.username = f"deleted_{str(user.id)[:8]}"
    user.email = None
    user.calendar_color = "#9CA3AF"

    # Delete absences (no statutory retention requirement)
    db.query(Absence).filter(Absence.user_id == user.id).delete()

    log = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=user.id,
        changed_by=current_user.id,
        action="dsgvo_anonymize",
        source="dsgvo",
        new_note=f"DSGVO-Anonymisierung durch Admin {current_user.username}",
        tenant_id=current_user.tenant_id,
    )
    db.add(log)
    db.commit()

    return {"message": "Benutzer erfolgreich anonymisiert (Art. 17 DSGVO). Zeiteinträge bleiben für ArbZG §16 erhalten."}


@router.delete("/users/{user_id}/purge")
def purge_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """DSGVO Art. 17: Permanently delete a user and all data. Only allowed after ArbZG SS16 retention period (730 days)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    if user.is_active:
        raise HTTPException(status_code=400, detail="Benutzer muss zuerst deaktiviert werden")

    last_entry = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id
    ).order_by(TimeEntry.date.desc()).first()

    if last_entry:
        days_since = (today_local() - last_entry.date).days
        if days_since < 730:
            raise HTTPException(
                status_code=409,
                detail=f"Aufbewahrungsfrist noch nicht abgelaufen. Letzter Eintrag: {last_entry.date.strftime('%d.%m.%Y')} ({days_since} Tage, Pflicht: 730 Tage gem. ArbZG §16)."
            )

    # Remove FK dependencies before deleting user.
    # For changed_by references: SET NULL to preserve other users' audit trails.
    db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.changed_by == user.id
    ).update({TimeEntryAuditLog.changed_by: None}, synchronize_session=False)
    # Delete the purged user's own audit log entries.
    db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.user_id == user.id).delete()

    # Audit after cleaning up the user's logs (use admin's own ID since target will be deleted)
    log = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=current_user.id,
        changed_by=current_user.id,
        action="dsgvo_purge",
        source="dsgvo",
        old_note=f"Endgültige Löschung von User-ID {user_id} ({user.first_name} {user.last_name}) durch Admin {current_user.username}",
        tenant_id=current_user.tenant_id,
    )
    db.add(log)
    db.flush()
    # Clean up vacation requests
    from app.models.vacation_request import VacationRequest
    db.query(VacationRequest).filter(VacationRequest.user_id == user.id).delete(synchronize_session=False)
    # Nullify reviewed_by references
    db.query(VacationRequest).filter(VacationRequest.reviewed_by == user.id).update(
        {"reviewed_by": None}, synchronize_session=False
    )
    db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == user.id).delete()
    db.query(ChangeRequest).filter(ChangeRequest.user_id == user.id).delete()
    db.query(TimeEntry).filter(TimeEntry.user_id == user.id).delete()
    db.query(Absence).filter(Absence.user_id == user.id).delete()
    db.delete(user)
    db.commit()

    return {"message": "Benutzer und alle zugehörigen Daten wurden endgültig gelöscht (Art. 17 DSGVO)."}


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
    existing_user = db.query(User).filter(func.lower(User.username) == user_data.username.lower()).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Benutzername bereits vergeben")

    new_user = User(
        username=user_data.username.lower(),
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
        first_work_day=user_data.first_work_day,
        last_work_day=user_data.last_work_day,
        tenant_id=current_user.tenant_id,
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

    if user_data.username and user_data.username.lower() != user.username.lower():
        existing = db.query(User).filter(func.lower(User.username) == user_data.username.lower()).first()
        if existing:
            raise HTTPException(status_code=400, detail="Benutzername bereits vergeben")

    update_data = user_data.model_dump(exclude_unset=True)
    update_data.pop('is_active', None)  # Prevent bypassing the dedicated deactivate endpoint

    # VULN-010: invalidate existing JWTs when role is changed
    role_changed = 'role' in update_data and update_data['role'] != user.role

    for field, value in update_data.items():
        setattr(user, field, value)

    if role_changed:
        user.token_version = (user.token_version or 0) + 1

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
    user.deactivated_at = datetime.now(timezone.utc)
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
    user.deactivated_at = None
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
        tenant_id=current_user.tenant_id,
        effective_from=change_data.effective_from,
        weekly_hours=change_data.weekly_hours,
        note=change_data.note
    )
    db.add(change)

    if change_data.effective_from <= today_local():
        most_recent = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user_id,
            WorkingHoursChange.effective_from <= today_local()
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
        WorkingHoursChange.effective_from <= today_local()
    ).order_by(WorkingHoursChange.effective_from.desc()).first()

    if most_recent:
        user.weekly_hours = most_recent.weekly_hours
        db.commit()

    return None
