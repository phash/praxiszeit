from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, status
from fastapi.responses import JSONResponse
from urllib.parse import quote
from app.core.limiter import limiter
from app.core import totp_crypto
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, timedelta, timezone
import base64
import logging
import secrets
from collections import OrderedDict
from app.database import get_db, set_superadmin_context
from app.middleware.csrf import CSRF_COOKIE_NAME
from app.models import User, TimeEntry, Absence, TimeEntryAuditLog
from app.models.tenant import Tenant

# Audit A09 (OWASP Security Logging Failures): security-relevant auth events
# are emitted as structured application-log records on a dedicated logger.
# These go to stdout → Docker logs / journald → the standard forensic/SIEM
# sink (persists across restarts). Marker prefix "AUTH " + a stable event
# keyword keeps the records greppable for a SIEM.
#
# CRITICAL: never log the password, JWT, refresh token, or TOTP secret. We log
# the submitted *username* (attacker-supplied identifier, useful for forensics)
# but not the email.
security_logger = logging.getLogger("praxiszeit.security")

# F-039: In-memory failed login tracking as an OrderedDict LRU so eviction
# is O(1) instead of O(n log n). Also fixes the attacker-evicts-real-user
# scenario: under attack the LRU drops the *oldest* attacker entries, not
# the legitimate victim's.
#
# NOTE: still per-worker, not shared across gunicorn workers. For
# multi-worker deployments consider Redis-backed slowapi instead.
_failed_logins: "OrderedDict[str, list[datetime]]" = OrderedDict()
_MAX_TRACKED_USERS = 10000
_LOCKOUT_ATTEMPTS = 5
_LOCKOUT_WINDOW = timedelta(minutes=15)

from app.schemas.user import (
    LoginRequest, LoginResponse, RefreshResponse, UserResponse, UserListResponse,
    ChangePasswordRequest, UpdateCalendarColorRequest,
    TotpSetupResponse, TotpVerifyRequest, TotpDisableRequest,
)
from app.services import auth_service
from app.middleware.auth import get_current_user
from app.config import settings

# F-040: Pre-computed bcrypt hash of a random string. Used to equalise
# verify timing for non-existent users so login latency no longer leaks
# user existence. Must be initialized AFTER the auth_service import.
_DUMMY_BCRYPT_HASH = auth_service.hash_password(secrets.token_urlsafe(32))

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

def _record_failed_login(username_lower: str, now: datetime) -> None:
    """F-039: Append a failed attempt and maintain LRU ordering.

    The OrderedDict pops the oldest entry in O(1) once the cap is hit. The
    move_to_end() call keeps the victim's entry "hot" so a flood of bogus
    usernames can't evict their lockout record.
    """
    attempts = _failed_logins.get(username_lower)
    if attempts is None:
        _failed_logins[username_lower] = [now]
    else:
        attempts.append(now)
        _failed_logins.move_to_end(username_lower)

    while len(_failed_logins) > _MAX_TRACKED_USERS:
        _failed_logins.popitem(last=False)  # oldest first


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


def _set_csrf_cookie(response: Response) -> None:
    """
    F-024: Set the CSRF double-submit cookie.

    Must be non-HttpOnly so that frontend JS (axios interceptor) can read it
    and mirror it into the X-CSRF-Token header on mutating requests. The
    secret is scoped to the whole app because CSRF protection applies to
    every unsafe endpoint, not just /auth/*. Regenerated on every login and
    refresh so that a stolen token has a short lifetime.
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )


def _delete_csrf_cookie(response: Response) -> None:
    """Clear the CSRF cookie on logout."""
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(request: Request, response: Response, login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with username and password.
    F-010: Returns access token in JSON; refresh token set as HttpOnly cookie.
    F-019: If TOTP is enabled, requires totp_code in the request body.
    """
    # Account lockout: block after 5 failed attempts within 15 minutes
    username_lower = login_data.username.lower()
    now = datetime.now(timezone.utc)
    attempts = _failed_logins.get(username_lower, [])
    # Prune old attempts outside the window
    attempts = [t for t in attempts if now - t < _LOCKOUT_WINDOW]
    if attempts:
        _failed_logins[username_lower] = attempts
        _failed_logins.move_to_end(username_lower)
    elif username_lower in _failed_logins:
        del _failed_logins[username_lower]

    if len(attempts) >= _LOCKOUT_ATTEMPTS:
        security_logger.warning("AUTH account_locked user=%s attempts=%d", username_lower, len(attempts))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Konto vorübergehend gesperrt. Bitte in 15 Minuten erneut versuchen."
        )

    # Login needs to see all users across tenants (no tenant context yet)
    set_superadmin_context(db)
    user = db.query(User).filter(func.lower(User.username) == login_data.username.lower()).first()

    if not user or not user.is_active:
        # F-040: Run a dummy bcrypt verify so the response time does not
        # reveal whether the user exists. The dummy hash is generated at
        # module load time from a random string (see _DUMMY_BCRYPT_HASH).
        auth_service.verify_password(login_data.password, _DUMMY_BCRYPT_HASH)
        _record_failed_login(username_lower, now)
        # M-001 (DSGVO Art. 5 Abs. 1 lit. f/c): do NOT distinguish a deactivated
        # account from a non-existent one in the security log. A distinct
        # reason=inactive_user would let anyone with log access infer that a
        # specific (e.g. terminated) employee's account exists — leaking
        # employment status. Both cases log the same neutral reason; the HTTP
        # response is already identical (and timing-equalised via the dummy
        # bcrypt verify above). Active-account failures keep their own reason
        # codes (bad_password/bad_totp), which only reveal what colleagues
        # already know (the person works here).
        security_logger.warning(
            "AUTH login_failed user=%s reason=%s", username_lower, "unknown_user",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort"
        )

    if not auth_service.verify_password(login_data.password, user.password_hash):
        _record_failed_login(username_lower, now)
        security_logger.warning("AUTH login_failed user=%s reason=%s", username_lower, "bad_password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort"
        )

    # F-041: opportunistic re-hash of legacy bcrypt (72-byte truncated) to
    # bcrypt_sha256. Runs only on successful login, so users migrate
    # silently without being forced to reset their password. Don't bump
    # token_version — the password didn't actually change.
    if auth_service.needs_rehash(user.password_hash):
        user.password_hash = auth_service.hash_password(login_data.password)
        db.commit()

    # Check tenant is active before issuing tokens
    if user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if tenant and not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant deaktiviert"
            )

    # F-019: TOTP check with replay protection (per-user counter)
    if user.totp_enabled:
        if not login_data.totp_code:
            # Not a hard failure (the client is expected to re-submit with a
            # code), but record it so a SIEM can correlate the 2FA challenge.
            security_logger.info("AUTH totp_required user=%s", username_lower)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TOTP-Code erforderlich",
                headers={"X-Requires-TOTP": "true"},
            )
        stored_secret = user.totp_secret
        plain_secret = totp_crypto.decrypt_secret(stored_secret)
        accepted_counter = auth_service.verify_totp_with_counter(
            plain_secret, login_data.totp_code, user.last_totp_counter
        )
        if accepted_counter is None:
            _record_failed_login(username_lower, now)
            security_logger.warning("AUTH login_failed user=%s reason=%s", username_lower, "bad_totp")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungültiger TOTP-Code",
            )
        user.last_totp_counter = accepted_counter
        # DSGVO Art. 32: Bestands-Klartext-Secret bei erfolgreichem Login auf
        # Fernet-Verschlüsselung migrieren (analog bcrypt-Rehash-on-login).
        # M-2: kein zweites Decrypt — decrypt_secret gibt Legacy-Klartext unverändert
        # zurück, ein Fernet-Token nie (Ciphertext != Base32-Klartext).
        if plain_secret == stored_secret:
            user.totp_secret = totp_crypto.encrypt_secret(plain_secret)
        db.add(user)
        db.commit()

    # Clear failed login counter on success
    _failed_logins.pop(username_lower, None)

    tenant_id_str = str(user.tenant_id) if user.tenant_id else None
    access_token = auth_service.create_access_token(str(user.id), user.role.value, user.token_version, tenant_id_str)
    refresh_token = auth_service.create_refresh_token(str(user.id), user.token_version, tenant_id_str)

    # F-010: deliver refresh token via HttpOnly cookie, not in JSON
    _set_refresh_cookie(response, refresh_token)
    # F-024: issue a fresh CSRF double-submit token
    _set_csrf_cookie(response)

    security_logger.info("AUTH login_success user=%s", username_lower)

    return LoginResponse(
        access_token=access_token,
        user=UserListResponse.model_validate(user),
    )


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit(settings.REFRESH_RATE_LIMIT)
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
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
    # F-024: rotate the CSRF token on every refresh so that a stolen cookie
    # has a short lifetime bounded by the access-token refresh cadence.
    _set_csrf_cookie(response)
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
    _delete_csrf_cookie(response)
    security_logger.info("AUTH logout user=%s", current_user.username)
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
    response: Response,
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change password for the current authenticated user.
    Requires current password verification.
    """
    if not auth_service.verify_password(password_data.current_password, current_user.password_hash):
        security_logger.warning(
            "AUTH password_change_failed user=%s reason=%s",
            current_user.username, "wrong_current_password",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aktuelles Passwort ist falsch"
        )

    new_password_hash = auth_service.hash_password(password_data.new_password)
    current_user.password_hash = new_password_hash
    current_user.token_version += 1
    db.commit()
    db.refresh(current_user)

    security_logger.warning("AUTH password_changed user=%s", current_user.username)

    # Issue a fresh token so the frontend session stays valid after the version bump
    tenant_id_str = str(current_user.tenant_id) if current_user.tenant_id else None
    new_access_token = auth_service.create_access_token(
        str(current_user.id), current_user.role.value, current_user.token_version, tenant_id_str
    )
    # AUTH-05: Auch ein frisches Refresh- + CSRF-Cookie setzen. Sonst trägt das
    # Refresh-Cookie weiter die ALTE token_version → der nächste /refresh nach
    # Ablauf des Access-Tokens scheitert am token_version-Check (stiller Logout).
    new_refresh_token = auth_service.create_refresh_token(
        str(current_user.id), current_user.token_version, tenant_id_str
    )
    _set_refresh_cookie(response, new_refresh_token)
    _set_csrf_cookie(response)
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


@router.post("/onboarding/complete", response_model=UserResponse)
def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Markiert die Erst-Login-Onboarding-Tour als gesehen (idempotent).

    NULL onboarding_completed_at = noch nicht gesehen -> Frontend zeigt das
    rollenspezifische Welcome-Modal. Nach Bestaetigung ruft das Frontend diesen
    Endpoint, sodass es bei kuenftigen Logins (auch auf anderen Geraeten) nicht
    erneut erscheint.
    """
    if current_user.onboarding_completed_at is None:
        current_user.onboarding_completed_at = datetime.now(timezone.utc)
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

    F-060: E-Mail changes are audit-logged. If a password-reset-by-email
    flow is added in a future release, an attacker with a short-lived XSS
    foothold could silently swap the address and then trigger a reset.
    The audit log gives admins a forensic trail to detect that.
    """
    old_email = current_user.email
    email_changed = False

    if profile_data.first_name is not None:
        current_user.first_name = profile_data.first_name
    if profile_data.last_name is not None:
        current_user.last_name = profile_data.last_name
    if profile_data.email is not None:
        new_email = profile_data.email if profile_data.email.strip() else None
        if new_email != old_email:
            current_user.email = new_email
            email_changed = True

    if email_changed:
        # Write a standalone audit row (action="profile_update") so the
        # change is visible even though update_profile touches the user
        # table, not the time_entries table.
        audit = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="profile_update",
            source="self_service",
            old_note=f"E-Mail geändert: {old_email or '(leer)'} → {current_user.email or '(leer)'}",
            tenant_id=current_user.tenant_id,
        )
        db.add(audit)

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
                # H-001 (DSGVO Art. 20): the raw stamp (actual attendance before
                # the soll-window clamp) is the data subject's own personal data
                # and must be part of the export. NULL when no clamping occurred.
                "raw_start_time": str(e.raw_start_time) if e.raw_start_time else None,
                "raw_end_time": str(e.raw_end_time) if e.raw_end_time else None,
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
            # Review 2026-06-23: username ist nicht zeichen-restringiert (kann " /
            # Sonderzeichen enthalten) -> RFC-5987-konform encoden statt roh in den
            # Header zu interpolieren.
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(
                f"PraxisZeit_Datenauszug_{current_user.username}.json"
            ),
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
    # Review 2026-06-23: nur bis zur Grenze + 1 Byte lesen, statt den ganzen Body
    # in den Speicher zu ziehen und erst danach zu pruefen (Memory-DoS-Verstaerker).
    contents = await file.read(512_001)
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
    current_user.totp_secret = totp_crypto.encrypt_secret(secret)
    # M-1: Counter mit dem neuen Secret zurücksetzen, sonst kann ein Setup direkt
    # nach einem Login im selben 30s-Fenster nicht bestätigt werden (Replay-Guard).
    current_user.last_totp_counter = None
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

    # M-SEC4: use the replay-safe verifier (same as /login) and persist the
    # accepted counter, so the code that activates 2FA cannot then be replayed
    # against /login within the ±30s window.
    accepted_counter = auth_service.verify_totp_with_counter(
        totp_crypto.decrypt_secret(current_user.totp_secret), verify_data.code, current_user.last_totp_counter
    )
    if accepted_counter is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger TOTP-Code. Bitte prüfen Sie Ihre Authenticator-App."
        )

    current_user.last_totp_counter = accepted_counter
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
    # M-1: Counter zurücksetzen — sonst lehnt ein Re-Enroll im selben 30s-Fenster
    # den ersten Code als Replay ab (neuer Counter == altem last_totp_counter).
    current_user.last_totp_counter = None
    # S-L03: invalidate other sessions on a security-relevant change, mirroring
    # deactivate / set-password / role-change. Disabling 2FA must not leave
    # stale sessions authenticated.
    current_user.token_version = (current_user.token_version or 0) + 1
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)
