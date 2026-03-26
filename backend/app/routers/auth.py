from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, status
from fastapi.responses import JSONResponse
from app.core.limiter import limiter
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, timezone
import base64
from app.database import get_db, set_superadmin_context
from app.models import User, TimeEntry, Absence
from app.models.tenant import Tenant
from app.schemas.user import (
    LoginRequest, LoginResponse, RefreshResponse, UserResponse, UserListResponse,
    ChangePasswordRequest, UpdateCalendarColorRequest,
    TotpSetupResponse, TotpVerifyRequest, TotpDisableRequest,
)
from app.services import auth_service
from app.middleware.auth import get_current_user
from app.config import settings

# Cookie name and path constants
_REFRESH_COOKIE = "refresh_token"
_REFRESH_PATH = "/api/auth/refresh"

# Magic bytes for image format verification
_JPEG_MAGIC = b'\xff\xd8\xff'
_PNG_MAGIC  = b'\x89PNG'


class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=255)

    @field_validator('email', mode='before')
    @classmethod
    def validate_email_format(cls, v):
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return v
        from email_validator import validate_email, EmailNotValidError
        try:
            validate_email(v, check_deliverability=False)
        except EmailNotValidError as e:
            raise ValueError(f'Ungültiges E-Mail-Format: {e}')
        return v

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an HttpOnly cookie scoped to /api/auth/refresh."""
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path=_REFRESH_PATH,
    )


def _delete_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(key=_REFRESH_COOKIE, path=_REFRESH_PATH)


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(request: Request, response: Response, login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with username and password.
    F-010: Returns access token in JSON; refresh token set as HttpOnly cookie.
    F-019: If TOTP is enabled, requires totp_code in the request body.
    """
    # Login needs to see all users across tenants (no tenant context yet)
    set_superadmin_context(db)
    user = db.query(User).filter(func.lower(User.username) == login_data.username.lower()).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort"
        )

    if not auth_service.verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort"
        )

    # Check tenant is active before issuing tokens
    if user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if tenant and not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant deaktiviert"
            )

    # F-019: TOTP check
    if user.totp_enabled:
        if not login_data.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TOTP-Code erforderlich",
                headers={"X-Requires-TOTP": "true"},
            )
        if not auth_service.verify_totp(user.totp_secret, login_data.totp_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger TOTP-Code",
            )

    tenant_id_str = str(user.tenant_id) if user.tenant_id else None
    access_token = auth_service.create_access_token(str(user.id), user.role.value, user.token_version, tenant_id_str)
    refresh_token = auth_service.create_refresh_token(str(user.id), user.token_version, tenant_id_str)

    # F-010: deliver refresh token via HttpOnly cookie, not in JSON
    _set_refresh_cookie(response, refresh_token)

    return LoginResponse(
        access_token=access_token,
        user=UserListResponse.model_validate(user),
    )


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("10/minute")
def refresh_token(request: Request, db: Session = Depends(get_db)):
    """
    F-010: Refresh access token.
    The refresh token is read from the HttpOnly cookie – no request body needed.
    """
    token = request.cookies.get(_REFRESH_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh-Token fehlt"
        )

    payload = auth_service.decode_token(token)
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

    # Refresh needs to see user across tenants (token carries tid but RLS not set yet)
    set_superadmin_context(db)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden oder deaktiviert"
        )

    token_version = payload.get("tv", 0)
    if token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token wurde widerrufen. Bitte erneut anmelden."
        )

    # Check tenant is active before issuing new access token
    if user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if tenant and not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant deaktiviert"
            )

    tenant_id_str = str(user.tenant_id) if user.tenant_id else None
    access_token = auth_service.create_access_token(str(user.id), user.role.value, user.token_version, tenant_id_str)
    return RefreshResponse(access_token=access_token)


@router.post("/logout")
def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Logout: invalidates all tokens (increments token_version) and clears the refresh cookie.
    """
    current_user.token_version = (current_user.token_version or 0) + 1
    db.commit()
    _delete_refresh_cookie(response)
    return {"message": "Erfolgreich abgemeldet"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Return the full profile of the authenticated user, including profile_picture.
    Use this to lazily load data not included in the login response.
    """
    return UserResponse.model_validate(current_user)


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
    if not auth_service.verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aktuelles Passwort ist falsch"
        )

    new_password_hash = auth_service.hash_password(password_data.new_password)
    current_user.password_hash = new_password_hash
    current_user.token_version += 1
    db.commit()
    db.refresh(current_user)

    # Issue a fresh token so the frontend session stays valid after the version bump
    tenant_id_str = str(current_user.tenant_id) if current_user.tenant_id else None
    new_access_token = auth_service.create_access_token(
        str(current_user.id), current_user.role.value, current_user.token_version, tenant_id_str
    )
    return {"message": "Passwort erfolgreich geändert", "access_token": new_access_token}


@router.put("/calendar-color", response_model=UserResponse)
def update_calendar_color(
    request: UpdateCalendarColorRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update calendar color for the current authenticated user."""
    current_user.calendar_color = request.calendar_color
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.put("/profile", response_model=UserResponse)
def update_profile(
    profile_data: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    DSGVO Art. 16 – Berichtigungsrecht: update own name and email.
    """
    if profile_data.first_name is not None:
        current_user.first_name = profile_data.first_name
    if profile_data.last_name is not None:
        current_user.last_name = profile_data.last_name
    if profile_data.email is not None:
        current_user.email = profile_data.email if profile_data.email.strip() else None
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.get("/me/export")
def export_my_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    DSGVO Art. 20 – Datenportabilität: export all personal data as JSON.
    """
    time_entries = db.query(TimeEntry).filter(TimeEntry.user_id == current_user.id).order_by(TimeEntry.date).all()
    absences = db.query(Absence).filter(Absence.user_id == current_user.id).order_by(Absence.date).all()

    data = {
        "export_info": {
            "basis": "Art. 20 DSGVO – Recht auf Datenübertragbarkeit",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user_id": str(current_user.id),
        },
        "stammdaten": {
            "username": current_user.username,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "email": current_user.email,
            "role": current_user.role.value,
            "weekly_hours": float(current_user.weekly_hours),
            "vacation_days": current_user.vacation_days,
            "is_active": current_user.is_active,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "zeiteintraege": [
            {
                "date": str(e.date),
                "start_time": str(e.start_time),
                "end_time": str(e.end_time),
                "break_minutes": e.break_minutes,
                "note": e.note,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in time_entries
        ],
        "abwesenheiten": [
            {
                "date": str(a.date),
                "end_date": str(a.end_date) if a.end_date else None,
                "type": a.type.value,
                "note": a.note,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in absences
        ],
    }

    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": f'attachment; filename="PraxisZeit_Datenauszug_{current_user.username}.json"',
            "Content-Type": "application/json; charset=utf-8",
        }
    )


@router.put("/profile-picture", response_model=UserResponse)
@limiter.limit("20/minute")
async def update_profile_picture(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload profile picture. Max 500KB, JPEG or PNG only. Magic bytes verified."""
    contents = await file.read()
    if len(contents) > 512_000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bild zu groß (max. 500 KB)")

    # Magic bytes check – client-controlled Content-Type not trusted (C1)
    if contents[:3] == _JPEG_MAGIC:
        mime = "image/jpeg"
    elif contents[:4] == _PNG_MAGIC:
        mime = "image/png"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur JPEG oder PNG erlaubt")

    data_uri = f"data:{mime};base64,{base64.b64encode(contents).decode()}"
    current_user.profile_picture = data_uri
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.delete("/profile-picture", response_model=UserResponse)
def delete_profile_picture(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove profile picture."""
    current_user.profile_picture = None
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


# ── F-019: TOTP 2FA endpoints ────────────────────────────────────────────────

@router.post("/totp/setup", response_model=TotpSetupResponse)
@limiter.limit("3/minute")
def totp_setup(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    F-019: Initiate TOTP setup.
    Generates a new secret and saves it on the user (totp_enabled stays False
    until the user verifies with a valid code via /totp/verify).
    Returns the otpauth:// URI for QR rendering and the raw secret for manual entry.
    """
    secret = auth_service.generate_totp_secret()
    current_user.totp_secret = secret
    db.commit()

    return TotpSetupResponse(
        otpauth_uri=auth_service.get_totp_uri(current_user.username, secret),
        secret=secret,
    )


@router.post("/totp/verify", response_model=UserResponse)
@limiter.limit("3/minute")
def totp_verify(
    request: Request,
    verify_data: TotpVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    F-019: Verify TOTP code and activate 2FA.
    The user must have called /totp/setup first to get a secret.
    """
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP-Setup nicht initiiert. Bitte zuerst /totp/setup aufrufen."
        )

    if not auth_service.verify_totp(current_user.totp_secret, verify_data.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger TOTP-Code. Bitte prüfen Sie Ihre Authenticator-App."
        )

    current_user.totp_enabled = True
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.delete("/totp/disable", response_model=UserResponse)
@limiter.limit("3/minute")
def totp_disable(
    request: Request,
    disable_data: TotpDisableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    F-019: Disable TOTP 2FA. Requires current password confirmation.
    """
    if not auth_service.verify_password(disable_data.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwort ist falsch"
        )

    current_user.totp_secret = None
    current_user.totp_enabled = False
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)
