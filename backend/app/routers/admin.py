from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import secrets
import string
from datetime import date
from app.database import get_db
from app.models import User, WorkingHoursChange
from app.middleware.auth import require_admin
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserCreateResponse, PasswordResetResponse
from app.schemas.working_hours_change import WorkingHoursChangeCreate, WorkingHoursChangeResponse
from app.services import auth_service

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def generate_temp_password(length: int = 12) -> str:
    """Generate a random temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@router.get("/users", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """List all users (admin only)."""
    users = db.query(User).order_by(User.last_name, User.first_name).all()
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
    """
    Create a new user (admin only).
    Generates a temporary password and returns it in the response.
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="E-Mail-Adresse bereits vergeben")

    # Generate temporary password
    temp_password = generate_temp_password()

    # Create user
    new_user = User(
        email=user_data.email,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        role=user_data.role,
        weekly_hours=user_data.weekly_hours,
        vacation_days=user_data.vacation_days,
        password_hash=auth_service.hash_password(temp_password),
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return UserCreateResponse(
        user=UserResponse.model_validate(new_user),
        temporary_password=temp_password
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

    # Check if email is being changed and if it's already taken
    if user_data.email and user_data.email != user.email:
        existing = db.query(User).filter(User.email == user_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="E-Mail-Adresse bereits vergeben")

    # Update fields
    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return user


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetResponse)
def reset_password(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Reset user password (admin only).
    Generates a new temporary password and returns it.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # Generate temporary password
    temp_password = generate_temp_password()

    # Update password
    user.password_hash = auth_service.hash_password(temp_password)
    db.commit()

    return PasswordResetResponse(
        message=f"Passwort für {user.first_name} {user.last_name} wurde zurückgesetzt",
        temporary_password=temp_password
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Deactivate a user (soft delete, admin only).
    Cannot deactivate yourself.
    """
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="Sie können sich nicht selbst deaktivieren")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.is_active = False
    db.commit()

    return None


# Working Hours Change Endpoints

@router.get("/users/{user_id}/working-hours-changes", response_model=List[WorkingHoursChangeResponse])
def list_working_hours_changes(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get working hours change history for a user (admin only).
    Returns all historical changes ordered by effective_from (newest first).
    """
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
    """
    Create a new working hours change for a user (admin only).

    Also updates the user's current weekly_hours if the change is effective today or in the past.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # Check if a change already exists for this exact date
    existing = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.effective_from == change_data.effective_from
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Eine Stundenänderung für den {change_data.effective_from.strftime('%d.%m.%Y')} existiert bereits"
        )

    # Create the change record
    change = WorkingHoursChange(
        user_id=user_id,
        effective_from=change_data.effective_from,
        weekly_hours=change_data.weekly_hours,
        note=change_data.note
    )

    db.add(change)

    # Update user's current weekly_hours if this change is effective today or in the past
    if change_data.effective_from <= date.today():
        # Find the most recent change (including the one we just created)
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
    """
    Delete a working hours change (admin only).

    Also updates the user's current weekly_hours if necessary.
    """
    change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.id == change_id,
        WorkingHoursChange.user_id == user_id
    ).first()

    if not change:
        raise HTTPException(status_code=404, detail="Stundenänderung nicht gefunden")

    user = db.query(User).filter(User.id == user_id).first()

    db.delete(change)
    db.commit()

    # Recalculate user's current weekly_hours
    most_recent = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.effective_from <= date.today()
    ).order_by(WorkingHoursChange.effective_from.desc()).first()

    if most_recent:
        user.weekly_hours = most_recent.weekly_hours
        db.commit()

    return None
