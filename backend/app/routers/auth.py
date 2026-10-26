from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from urllib.parse import quote
from app.core.limiter import limiter, _get_real_ip
from app.core.db_errors import _CONTROL_CHARS
from app.core import totp_crypto
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import logging
import secrets
from collections import OrderedDict
from app.database import get_db, set_superadmin_context
from app.middleware.csrf import CSRF_COOKIE_NAME
from app.models import (
    User, TimeEntry, Absence, TimeEntryAuditLog, ImpersonationSession, WorkingHoursChange,
)
from app.models.tenant import Tenant
from app.models.security_event import (
    EVENT_TOTP_DISABLED_SELF, EVENT_TOTP_ENABLED, SecurityEvent,
)
from app.services.timezone_service import now_local

# Audit A09 (OWASP Security Logging Failures): security-relevant auth events
# are emitted as structured application-log records on a dedicated logger.
# These go to stdout → Docker logs / journald → the standard forensic/SIEM
# sink (persists across restarts). Marker prefix "AUTH " + a stable event
# keyword keeps the records greppable for a SIEM.
#
# CRITICAL: never log the password, JWT, refresh token, or TOTP secret. We log
# the submitted *username* of EXISTING accounts (useful for forensics) but not
# the email. Sicherheits-Review 2026-10: a name that matches no account is only
# logged in redacted form (``_redact_username``) — people regularly type their
# password into the username field — and every logged name is flattened
# (``_safe_log_text``) so a newline in the input cannot forge log lines.
security_logger = logging.getLogger("praxiszeit.security")


def _safe_log_text(text: Optional[str], limit: int = 100) -> str:
    """Steuerzeichen (inkl. CR/LF, U+2028/9) einebnen und kuerzen — gleiche
    Zeichenklasse wie ``app.core.db_errors`` (#483)."""
    return _CONTROL_CHARS.sub(" ", text or "")[:limit]


def _redact_username(username_lower: str) -> str:
    """Kurze, nicht umkehrbare Form eines eingegebenen Namens ohne Konto.

    Erste zwei Zeichen + 12 Hex-Stellen HMAC-SHA256 (Schluessel SECRET_KEY):
    gleiche Eingabe → gleiche Kennung (Angriffe bleiben korrelierbar), aber ein
    ins Namensfeld getipptes Passwort steht nicht lesbar im Protokoll und laesst
    sich ohne den Schluessel auch nicht per Woerterbuch zurueckrechnen."""
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), username_lower.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:12]
    return f"{_safe_log_text(username_lower[:2], 2)}…#{digest}"

# F-039: In-memory failed login tracking as an OrderedDict LRU so eviction
# is O(1) instead of O(n log n). Also fixes the attacker-evicts-real-user
# scenario: under attack the LRU drops the *oldest* attacker entries, not
# the legitimate victim's.
#
# NOTE: still per-worker, not shared across gunicorn workers. For
# multi-worker deployments consider Redis-backed slowapi instead.
#
# Sicherheits-Review 2026-10: the lockout is keyed on (username, client IP) —
# keyed on the name alone, anyone could lock ``admin`` out of the practice with
# five bad attempts every 15 minutes. A second, much higher cap per username
# (``_GLOBAL_LOCKOUT_ATTEMPTS``) still bounds a brute force spread over many
# IPs. Keys: ``("ip", username, ip)`` and ``("user", username)``.
_failed_logins: "OrderedDict[tuple, list[datetime]]" = OrderedDict()
_MAX_TRACKED_USERS = 10000
_LOCKOUT_ATTEMPTS = 5
_GLOBAL_LOCKOUT_ATTEMPTS = 50
_LOCKOUT_WINDOW = timedelta(minutes=15)

from app.schemas.user import (
    LoginRequest, LoginResponse, RefreshResponse, UserResponse, UserListResponse,
    ChangePasswordRequest, UpdateCalendarColorRequest,
    TotpSetupRequest, TotpSetupResponse, TotpVerifyRequest, TotpDisableRequest,
)
from app.schemas.work_schedule import MyWorkScheduleResponse
from app.services import auth_service
from app.services import work_schedule_service
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

def _lockout_keys(username_lower: str, client_ip: str) -> tuple[tuple, tuple]:
    return ("ip", username_lower, client_ip), ("user", username_lower)


def _record_failed_login(username_lower: str, client_ip: str, now: datetime) -> None:
    """F-039: Append a failed attempt and maintain LRU ordering.

    The OrderedDict pops the oldest entry in O(1) once the cap is hit. The
    move_to_end() call keeps the victim's entry "hot" so a flood of bogus
    usernames can't evict their lockout record. Both the per-(name, IP) and the
    per-name counter are updated.
    """
    for key in _lockout_keys(username_lower, client_ip):
        attempts = _failed_logins.get(key)
        if attempts is None:
            _failed_logins[key] = [now]
        else:
            attempts.append(now)
            _failed_logins.move_to_end(key)

    while len(_failed_logins) > _MAX_TRACKED_USERS:
        _failed_logins.popitem(last=False)  # oldest first


def _recent_attempts(key: tuple, now: datetime) -> int:
    """Prune attempts outside the window and return how many remain."""
    attempts = [t for t in _failed_logins.get(key, []) if now - t < _LOCKOUT_WINDOW]
    if attempts:
        _failed_logins[key] = attempts
        _failed_logins.move_to_end(key)
    else:
        _failed_logins.pop(key, None)
    return len(attempts)


router = APIRouter(prefix="/api/auth", tags=["auth"])


TOTP_ALREADY_ENABLED_DETAIL = (
    "2FA ist bereits aktiv. Um ein neues Gerät einzurichten, 2FA zuerst "
    "deaktivieren (Passwort und aktueller Code) und dann neu einrichten."
)


def _log_self_security_event(db: Session, user: User, event: str, detail: str) -> None:
    """Eine ``security_events``-Zeile fuer einen Vorgang, den die Person an
    ihrem EIGENEN Konto ausloest — Muster ``admin_users._log_account_event``
    (actor = Konto-ID, nie Klarname; gleiche Transaktion wie der Vorgang)."""
    db.add(SecurityEvent(
        tenant_id=user.tenant_id,
        event=event,
        subject_user_id=user.id,
        actor=f"user:{user.id}",
        detail=detail,
    ))


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
    # Account lockout: block after 5 failed attempts within 15 minutes from the
    # same client IP, or after 50 from anywhere (Sicherheits-Review 2026-10).
    # Checked BEFORE the user lookup → same 429 for existing and unknown names.
    username_lower = login_data.username.lower()
    client_ip = _get_real_ip(request)
    now = datetime.now(timezone.utc)
    ip_key, user_key = _lockout_keys(username_lower, client_ip)
    ip_attempts = _recent_attempts(ip_key, now)
    user_attempts = _recent_attempts(user_key, now)

    if ip_attempts >= _LOCKOUT_ATTEMPTS or user_attempts >= _GLOBAL_LOCKOUT_ATTEMPTS:
        # Whether the name exists is unknown here → redacted form.
        security_logger.warning(
            "AUTH account_locked user=%s scope=%s attempts=%d",
            _redact_username(username_lower),
            "ip" if ip_attempts >= _LOCKOUT_ATTEMPTS else "global",
            max(ip_attempts, user_attempts),
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Konto vorübergehend gesperrt. Bitte in 15 Minuten erneut versuchen."
        )

    # Login needs to see all users across tenants (no tenant context yet)
    set_superadmin_context(db)
    # Fix #5: username is only unique per (tenant_id, username) — in SaaS two
    # tenants may share one. ``.first()`` could authenticate the WRONG account,
    # so load ALL matches and refuse when more than one ACTIVE account shares the
    # name (neutral error, no info leak). On-prem (single tenant) always matches
    # at most one → unchanged.
    matching_users = (
        db.query(User)
        .filter(func.lower(User.username) == login_data.username.lower())
        .all()
    )
    active_matches = [u for u in matching_users if u.is_active]
    if len(active_matches) > 1:
        # Equalise timing (dummy verify), record the failure and log the
        # ambiguity for ops — but never reveal which/that accounts exist.
        auth_service.verify_password(login_data.password, _DUMMY_BCRYPT_HASH)
        _record_failed_login(username_lower, client_ip, now)
        security_logger.warning(
            "AUTH login_ambiguous user=%s active_matches=%d",
            _safe_log_text(username_lower), len(active_matches),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort",
        )
    user = active_matches[0] if active_matches else (matching_users[0] if matching_users else None)

    if not user or not user.is_active:
        # F-040: Run a dummy bcrypt verify so the response time does not
        # reveal whether the user exists. The dummy hash is generated at
        # module load time from a random string (see _DUMMY_BCRYPT_HASH).
        auth_service.verify_password(login_data.password, _DUMMY_BCRYPT_HASH)
        _record_failed_login(username_lower, client_ip, now)
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
            "AUTH login_failed user=%s reason=%s", _redact_username(username_lower), "unknown_user",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Benutzername oder Passwort"
        )

    if not auth_service.verify_password(login_data.password, user.password_hash):
        _record_failed_login(username_lower, client_ip, now)
        security_logger.warning(
            "AUTH login_failed user=%s reason=%s", _safe_log_text(username_lower), "bad_password",
        )
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
            security_logger.info("AUTH totp_required user=%s", _safe_log_text(username_lower))
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
            _record_failed_login(username_lower, client_ip, now)
            security_logger.warning(
                "AUTH login_failed user=%s reason=%s", _safe_log_text(username_lower), "bad_totp",
            )
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

    # Clear this client's failed-login counter on success. The per-name cap is
    # deliberately NOT reset: otherwise every successful login of the real user
    # would hand a distributed attacker a fresh budget of 50 attempts.
    _failed_logins.pop(ip_key, None)

    tenant_id_str = str(user.tenant_id) if user.tenant_id else None
    access_token = auth_service.create_access_token(str(user.id), user.role.value, user.token_version, tenant_id_str)
    refresh_token = auth_service.create_refresh_token(str(user.id), user.token_version, tenant_id_str)

    # F-010: deliver refresh token via HttpOnly cookie, not in JSON
    _set_refresh_cookie(response, refresh_token)
    # F-024: issue a fresh CSRF double-submit token
    _set_csrf_cookie(response)

    security_logger.info("AUTH login_success user=%s", _safe_log_text(username_lower))

    # Spec 11.1: heute gültige Blöcke (locker, E29 — nie ein 500 im Login).
    from app.services import calculation_service
    from app.services.timezone_service import today_local
    calculation_service.attach_work_blocks_today(db, [user], today_local())

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


_optional_bearer = HTTPBearer(auto_error=False)


def get_optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like ``get_current_user`` but returns None instead of 401 — only for
    logout, which must work after the access token has expired.

    An impersonation token never counts here: logging out under it would bump
    the *employee's* token_version (the read-only middleware already rejects
    that POST; this is the second line).
    """
    if credentials is None:
        return None
    try:
        user = get_current_user(request, credentials, db)
    except HTTPException:
        return None
    if getattr(request.state, "is_impersonating", False):
        return None
    return user


def _user_from_refresh_cookie(request: Request, db: Session) -> Optional[User]:
    """The account behind a still-valid refresh cookie, else None.

    Same checks as ``/refresh`` (type, active account, current token_version):
    a stale or foreign cookie revokes nothing.
    """
    token = request.cookies.get(_REFRESH_COOKIE)
    if not token:
        return None
    payload = auth_service.decode_token(token)
    if not payload or payload.get("type") != "refresh" or not payload.get("sub"):
        return None
    set_superadmin_context(db)
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        return None
    if payload.get("tv", 0) != user.token_version:
        return None
    return user


def _revoke_sessions(db: Session, user: User) -> None:
    """token_version++ and close the user's open impersonation sessions."""
    user.token_version = (user.token_version or 0) + 1
    open_sessions = (
        db.query(ImpersonationSession)
        .filter(
            ImpersonationSession.impersonator_id == user.id,
            ImpersonationSession.tenant_id == user.tenant_id,
            ImpersonationSession.ended_at.is_(None),
        )
        .all()
    )
    for session in open_sessions:
        session.ended_at = now_local()


@router.post("/logout")
@router.post("/refresh/logout")
def logout(
    request: Request,
    response: Response,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Logout: invalidates all tokens (increments token_version) and clears the refresh cookie.

    Security-Audit 2026-07-25 (F2): the token_version bump now also kills any
    outstanding impersonation token (they carry ``imp_tv``). We additionally
    close the open ``impersonation_sessions`` rows so the DSGVO Art. 5(2)
    accountability log has an ``ended_at`` instead of dangling open forever
    when an admin logs out without pressing "Zurück zu Admin".

    Sicherheits-Review 2026-10: logout no longer requires a valid access token.
    After the 30-min access token had expired, logout used to 401 — the
    frontend cleared its state, but the refresh cookie and the server session
    stayed valid for 7 days (shared practice PC: the next person just called
    /refresh). Now the cookies are ALWAYS deleted, and the session is revoked
    via the access token if valid, otherwise via the refresh cookie. The
    refresh cookie is path-scoped to ``/api/auth/refresh``, so the browser only
    sends it to ``/api/auth/refresh/logout`` — the frontend calls that path;
    ``/api/auth/logout`` stays for API clients and older frontends.
    CSRF: unchanged (double-submit enforced by the middleware when the cookie
    is present); a forged cross-site logout can at worst end a session.
    """
    users: dict = {}
    if current_user is not None:
        users[current_user.id] = current_user
    cookie_user = _user_from_refresh_cookie(request, db)
    if cookie_user is not None and cookie_user.id not in users:
        users[cookie_user.id] = cookie_user

    for user in users.values():
        _revoke_sessions(db, user)
    if users:
        db.commit()

    _delete_refresh_cookie(response)
    _delete_csrf_cookie(response)
    if users:
        for user in users.values():
            security_logger.info("AUTH logout user=%s", _safe_log_text(user.username))
    else:
        security_logger.info("AUTH logout user=%s", "-")
    return {"message": "Erfolgreich abgemeldet"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Return the full profile of the authenticated user, including profile_picture.
    Use this to lazily load data not included in the login response.
    """
    return UserResponse.model_validate(current_user)


@router.get("/me/work-schedule", response_model=MyWorkScheduleResponse)
def get_my_work_schedule(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spec 2026-10-08, 14 / E67: die heute gültigen Arbeitszeit-Blöcke und ihr
    Verlauf — nur eigene Daten, ohne Freitext (P12)."""
    return work_schedule_service.build_my_work_schedule(db, current_user, now_local().date())


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
            _safe_log_text(current_user.username), "wrong_current_password",
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

    security_logger.warning("AUTH password_changed user=%s", _safe_log_text(current_user.username))

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
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    DSGVO Art. 20 – Datenportabilität: export all personal data as JSON.

    Sicherheits-Review 2026-10: not under impersonation — the export is the
    data subject's own request (Art. 15/20); an admin viewing "as employee"
    would otherwise pull the full personal-data package in the employee's name.
    """
    if getattr(request.state, "is_impersonating", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Der Datenauszug ist in der Ansicht als Mitarbeiter:in nicht verfügbar.",
        )
    time_entries = db.query(TimeEntry).filter(TimeEntry.tenant_id == current_user.tenant_id, TimeEntry.user_id == current_user.id).order_by(TimeEntry.date).all()
    absences = db.query(Absence).filter(Absence.tenant_id == current_user.tenant_id, Absence.user_id == current_user.id).order_by(Absence.date).all()
    # #431: die Stundenhistorie ist ein vollstaendiger Vertrags-Snapshot je
    # Wirkungsdatum (Soll-relevant) und gehoert damit in den Art.-20-Export.
    # F-026: tenant_id explizit mitfiltern (belt-and-suspenders zu RLS).
    working_hours_changes = (
        db.query(WorkingHoursChange)
        .filter(
            WorkingHoursChange.user_id == current_user.id,
            WorkingHoursChange.tenant_id == current_user.tenant_id,
        )
        .order_by(WorkingHoursChange.effective_from)
        .all()
    )

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
            "vacation_days": float(current_user.vacation_days),  # #408: Numeric(4,1)→Decimal; JSONResponse/json.dumps kann Decimal nicht serialisieren
            "work_blocks": current_user.work_blocks,  # Spec 15.3 / E72: wie gespeichert
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
                # Spec 2026-10-08 (15.3): nur int/bool/None — rohes JSONResponse.
                "uncredited_minutes": int(e.uncredited_minutes or 0),
                "credit_override": bool(e.credit_override),
                "auto_closed": bool(e.auto_closed),
                "clamp_grace_minutes": e.clamp_grace_minutes,
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
        # #431: Vertragshistorie (Wochenstunden/Tagesplan je Wirkungsdatum).
        # Numeric(4,2)-Felder float()-gecastet — Decimal-Leak-Klasse #383/#408,
        # dieser Export laeuft ueber rohes JSONResponse(content=data), nicht
        # jsonable_encoder.
        "stundenhistorie": [
            {
                "effective_from": str(h.effective_from),
                "weekly_hours": float(h.weekly_hours) if h.weekly_hours is not None else None,
                "use_daily_schedule": h.use_daily_schedule,
                "hours_monday": float(h.hours_monday) if h.hours_monday is not None else None,
                "hours_tuesday": float(h.hours_tuesday) if h.hours_tuesday is not None else None,
                "hours_wednesday": float(h.hours_wednesday) if h.hours_wednesday is not None else None,
                "hours_thursday": float(h.hours_thursday) if h.hours_thursday is not None else None,
                "hours_friday": float(h.hours_friday) if h.hours_friday is not None else None,
                "work_days_per_week": h.work_days_per_week,
                "blocks": h.blocks,  # Spec 15.3: wie gespeichert, NULL = keine Blöcke
                "note": h.note,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in working_hours_changes
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
    setup_data: TotpSetupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    F-019: Initiate TOTP setup.
    Generates a new secret and saves it on the user (totp_enabled stays False
    until the user verifies with a valid code via /totp/verify).
    Returns the otpauth:// URI for QR rendering and the raw secret for manual entry.

    Security-Audit 2026-07-25 (F1): requires the current password. Without it,
    anyone holding a valid access token (stolen token, unattended session) could
    (a) overwrite an ACTIVE enrollment — the victim's authenticator stops working
    while the attacker's starts — or (b) switch 2FA on for an account that had
    none, locking the owner out for good the moment they change their password.
    ``/totp/disable`` already required the password; this closes the weaker path
    that bypassed it.

    Sicherheits-Review 2026-10: refused while 2FA is ACTIVE. Previously a new
    secret replaced the active one immediately (``totp_enabled`` stayed True),
    so an unverified secret was live — cancelling the wizard locked the owner
    out, and password alone sufficed to swap the second factor. Re-enrolling now
    means: disable (password + current code), then set up again.
    """
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=TOTP_ALREADY_ENABLED_DETAIL,
        )
    if not auth_service.verify_password(setup_data.password, current_user.password_hash):
        security_logger.warning(
            "AUTH totp_setup_failed user=%s reason=%s",
            _safe_log_text(current_user.username), "wrong_password",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwort ist falsch"
        )

    secret = auth_service.generate_totp_secret()
    current_user.totp_secret = totp_crypto.encrypt_secret(secret)
    # M-1: Counter mit dem neuen Secret zurücksetzen, sonst kann ein Setup direkt
    # nach einem Login im selben 30s-Fenster nicht bestätigt werden (Replay-Guard).
    current_user.last_totp_counter = None
    db.commit()

    # A09: jede Ausgabe eines neuen Secrets gehoert in die Security-Spur.
    security_logger.warning(
        "AUTH totp_secret_issued user=%s", _safe_log_text(current_user.username),
    )

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
    was_enabled = bool(current_user.totp_enabled)
    current_user.totp_enabled = True
    if not was_enabled:
        _log_self_security_event(db, current_user, EVENT_TOTP_ENABLED,
                                 "Zwei-Faktor im Profil eingeschaltet")
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

    Sicherheits-Review 2026-10: additionally requires a valid CURRENT code
    (replay-safe, same verifier as /login) — the password alone (shoulder-
    surfed, reused) must not remove the second factor from an open session.
    Writes a ``security_events`` row. Lost device: no self-service path; the
    CLI ``praxiszeit-server.py reset-admin-password --disable-2fa`` (native)
    resets it.
    """
    if not auth_service.verify_password(disable_data.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwort ist falsch"
        )
    if current_user.totp_enabled and current_user.totp_secret:
        accepted_counter = auth_service.verify_totp_with_counter(
            totp_crypto.decrypt_secret(current_user.totp_secret),
            disable_data.code,
            current_user.last_totp_counter,
        )
        if accepted_counter is None:
            # Release-Review 1.20.2: a code already consumed at login is still
            # shown by the app — tell the user to wait for the next one instead
            # of calling it invalid. The replay protection itself stays.
            replayed = current_user.last_totp_counter is not None and auth_service.verify_totp_with_counter(
                totp_crypto.decrypt_secret(current_user.totp_secret),
                disable_data.code,
                None,
            ) is not None
            security_logger.warning(
                "AUTH totp_disable_failed user=%s reason=%s",
                _safe_log_text(current_user.username), "replayed_totp" if replayed else "bad_totp",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Dieser 2FA-Code wurde bereits verwendet. Bitte den nächsten Code der Authenticator-App abwarten."
                    if replayed else
                    "Ungültiger 2FA-Code. Bitte den aktuellen Code aus der Authenticator-App eingeben."
                ),
            )
        _log_self_security_event(db, current_user, EVENT_TOTP_DISABLED_SELF,
                                 "Zwei-Faktor im Profil abgeschaltet")

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
