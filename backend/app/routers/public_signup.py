"""Public (no-auth) self-service signup endpoints (Phase 3 / Issue #94).

All routes return 404 in ``onprem`` deployment mode — the Docker +
Native-Installer flavour doesn't have a multi-tenant landing page.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deployment import is_saas
from app.core.limiter import limiter
from app.database import SessionLocal, set_superadmin_context
from app.schemas.signup import (
    ResendVerificationRequest,
    SignupRequest,
    SignupResponse,
    VerifyResponse,
)
from app.services import signup_service
from app.services.mail_service import send_verification_email


router = APIRouter(prefix="/api/public", tags=["public-signup"])


def _saas_only():
    """Dependency that 404s in onprem mode."""
    if not is_saas():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _public_db():
    """Public endpoints run without a user-session, so we open a SessionLocal
    directly and set superadmin context so RLS doesn't bite on inserts."""
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        yield db
    finally:
        db.close()


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    # Behind nginx the X-Forwarded-For header carries the real IP; trust
    # it only because the app is fronted by a reverse proxy we control.
    xff = request.headers.get("x-forwarded-for")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)
    ua = request.headers.get("user-agent")
    # Guard against overly long UAs — column is varchar(500).
    if ua and len(ua) > 500:
        ua = ua[:500]
    return ip, ua


@router.post("/signup", response_model=SignupResponse, status_code=201)
@limiter.limit("5/hour")
def signup(
    request: Request,
    body: SignupRequest,
    _=Depends(_saas_only),
    db: Session = Depends(_public_db),
) -> SignupResponse:
    ip, ua = _client_meta(request)
    result = signup_service.signup(
        db,
        practice_name=body.practice_name,
        admin_email=body.admin_email,
        admin_first_name=body.admin_first_name,
        admin_last_name=body.admin_last_name,
        admin_password=body.admin_password,
        country=body.country,
        ip_address=ip,
        user_agent=ua,
        accepted_terms=body.accept_terms,
        accepted_privacy=body.accept_privacy,
    )
    # Build verification URL from the origin header; fall back to the
    # path-only form if the request came in without Origin (e.g. curl).
    origin = request.headers.get("origin") or ""
    verify_url = f"{origin.rstrip('/')}/verify?token={result.verification_token}"
    send_verification_email(
        to=body.admin_email,
        verification_url=verify_url,
        practice_name=body.practice_name,
    )
    return SignupResponse(tenant_id=str(result.tenant_id))


@router.get("/verify-email", response_model=VerifyResponse)
@limiter.limit("10/minute")
def verify_email(
    request: Request,
    token: str,
    _=Depends(_saas_only),
    db: Session = Depends(_public_db),
) -> VerifyResponse:
    if not token:
        raise HTTPException(status_code=400, detail="token fehlt")
    ip, ua = _client_meta(request)
    tenant_id = signup_service.verify(db, raw_token=token, ip_address=ip, user_agent=ua)
    return VerifyResponse(tenant_id=str(tenant_id))


@router.post("/resend-verification", status_code=202)
@limiter.limit("3/hour")
def resend_verification(
    request: Request,
    body: ResendVerificationRequest,
    _=Depends(_saas_only),
    db: Session = Depends(_public_db),
):
    """Always 202, regardless of whether the email exists — prevents
    enumeration. If the email matches an inactive admin, a new token
    is issued and mailed."""
    ip, ua = _client_meta(request)
    result = signup_service.resend(db, email=body.email, ip_address=ip, user_agent=ua)
    if result is not None:
        origin = request.headers.get("origin") or ""
        verify_url = f"{origin.rstrip('/')}/verify?token={result.verification_token}"
        send_verification_email(
            to=body.email,
            verification_url=verify_url,
            practice_name="PraxisZeit",  # best-effort without looking up tenant
        )
    return {"message": "Wenn diese Adresse registriert ist, senden wir eine neue Verifizierungsmail."}
