from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas.user import LoginRequest, LoginResponse, RefreshRequest, RefreshResponse, UserResponse, ChangePasswordRequest, UpdateCalendarColorRequest
from app.services import auth_service
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with username and password.
    Returns access token (30min) and refresh token (7 days).
    """
    # Find user by username
    user = db.query(User).filter(User.username == login_data.username).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort"
        )

    # Verify password
    if not auth_service.verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort"
        )

    # Create tokens
    access_token = auth_service.create_access_token(str(user.id), user.role.value, user.token_version)
    refresh_token = auth_service.create_refresh_token(str(user.id), user.token_version)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user)
    )


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("10/minute")
def refresh_token(request: Request, refresh_data: RefreshRequest, db: Session = Depends(get_db)):
    """
    Refresh access token using refresh token.
    Returns new access token.
    """
    # Decode refresh token
    payload = auth_service.decode_token(refresh_data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder abgelaufener Refresh Token"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Token"
        )

    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden oder deaktiviert"
        )

    # Validate token version
    token_version = payload.get("tv", 0)
    if token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token wurde widerrufen. Bitte erneut anmelden."
        )

    # Create new access token
    access_token = auth_service.create_access_token(str(user.id), user.role.value, user.token_version)

    return RefreshResponse(access_token=access_token)


@router.post("/logout")
def logout():
    """
    Logout endpoint.
    Client should delete tokens locally.
    (Optional: implement token blocklist for additional security)
    """
    return {"message": "Erfolgreich abgemeldet"}


@router.post("/change-password")
@limiter.limit("3/minute")
def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change password for the current authenticated user.
    Requires current password verification.
    """
    # Verify current password
    if not auth_service.verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aktuelles Passwort ist falsch"
        )

    # Hash new password
    new_password_hash = auth_service.hash_password(password_data.new_password)

    # Update password and invalidate all existing tokens
    current_user.password_hash = new_password_hash
    current_user.token_version += 1
    db.commit()

    return {"message": "Passwort erfolgreich geändert"}


@router.put("/calendar-color", response_model=UserResponse)
def update_calendar_color(
    request: UpdateCalendarColorRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update calendar color for the current authenticated user.
    """
    current_user.calendar_color = request.calendar_color
    db.commit()
    db.refresh(current_user)

    return UserResponse.model_validate(current_user)
