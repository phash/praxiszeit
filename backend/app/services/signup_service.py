"""Self-service signup provisioning (Phase 3 / Issue #94).

Flow:
1. ``signup()`` — creates an inactive tenant + inactive admin, stores a
   hashed verification token, writes an audit row, returns the opaque
   token (caller mails it).
2. ``verify()`` — consumes the token, activates admin + tenant.
3. ``resend()`` — invalidates outstanding tokens, issues a new one.

Tenant is intentionally created as ``is_active=True`` but the admin is
``is_active=False``; that way RLS queries keyed on tenant_id don't need
a separate ``pending_activation`` branch, while the user can't log in
yet. A ``trial_ends_at`` 14 days in the future is set during signup.

Tokens are 32-byte ``secrets.token_urlsafe`` values; we store only the
SHA-256 hash so a DB leak doesn't expose verification URLs.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import SignupAuditLog, SignupToken, Tenant, User, UserRole
from app.services import auth_service


VERIFY_TOKEN_TTL_HOURS = 24
TRIAL_LENGTH_DAYS = 14


@dataclass
class SignupResult:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    verification_token: str  # raw token — caller mails it, we only store the hash


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _slug_from_name(name: str, existing_slugs: set[str]) -> str:
    """Deterministic tenant slug — lowercased, non-alnum removed, deduplicated."""
    import re
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "praxis"
    base = base[:60]
    candidate = base
    i = 2
    while candidate in existing_slugs:
        suffix = f"-{i}"
        candidate = f"{base[:60 - len(suffix)]}{suffix}"
        i += 1
    return candidate


def _email_already_admin(db: Session, email: str) -> bool:
    """An email may only be the admin of ONE active tenant at a time.

    Emails belonging to inactive (pending-verification) admins are allowed
    to re-register — we simply recycle the tenant via ``resend``-equivalent
    semantics in a future iteration; for now we block on an existing row.
    """
    return (
        db.query(User)
        .filter(User.email == email, User.role == UserRole.ADMIN, User.is_active == True)  # noqa: E712
        .first()
        is not None
    )


def signup(
    db: Session,
    *,
    practice_name: str,
    admin_email: str,
    admin_first_name: str,
    admin_last_name: str,
    admin_password: str,
    country: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    accepted_terms: bool,
    accepted_privacy: bool,
) -> SignupResult:
    """Create tenant + inactive admin, return verification token."""
    if _email_already_admin(db, admin_email):
        # Audit the rejection too — a signal for brute-forcing existing accounts.
        db.add(SignupAuditLog(
            email=admin_email, event="signup_rejected_email_exists",
            ip_address=ip_address, user_agent=user_agent,
            accepted_terms=accepted_terms, accepted_privacy=accepted_privacy,
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-Mail-Adresse bereits registriert",
        )

    # Collision-avoiding slug
    existing = {s for (s,) in db.query(Tenant.slug).all()}
    slug = _slug_from_name(practice_name, existing)

    tenant = Tenant(
        id=uuid.uuid4(),
        name=practice_name,
        slug=slug,
        is_active=True,
        mode="multi",
        plan="trial",
        subscription_status="active",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=TRIAL_LENGTH_DAYS),
        country=country.upper(),
        billing_email=admin_email,
    )
    db.add(tenant)
    db.flush()  # get tenant.id populated for FK

    admin = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        username=admin_email,
        email=admin_email,
        password_hash=auth_service.hash_password(admin_password),
        first_name=admin_first_name,
        last_name=admin_last_name,
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=False,  # activates on verify
    )
    db.add(admin)
    db.flush()

    raw_token = secrets.token_urlsafe(32)
    db.add(SignupToken(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=admin.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=VERIFY_TOKEN_TTL_HOURS),
    ))

    db.add(SignupAuditLog(
        tenant_id=tenant.id,
        email=admin_email,
        event="signup_requested",
        ip_address=ip_address,
        user_agent=user_agent,
        accepted_terms=accepted_terms,
        accepted_privacy=accepted_privacy,
    ))
    db.commit()

    return SignupResult(
        tenant_id=tenant.id,
        user_id=admin.id,
        verification_token=raw_token,
    )


def verify(db: Session, *, raw_token: str, ip_address: Optional[str], user_agent: Optional[str]) -> uuid.UUID:
    """Activate the admin + return the tenant_id. Raises 410 on expired/used."""
    token_hash = _hash_token(raw_token)
    row: Optional[SignupToken] = (
        db.query(SignupToken).filter(SignupToken.token_hash == token_hash).first()
    )
    if row is None or row.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token ungültig oder bereits verwendet")

    now = datetime.now(timezone.utc)
    # row.expires_at might come back as tz-aware from Postgres and tz-naive
    # from SQLite (some dialects strip tz). Normalize both sides to tz-aware
    # so the comparison works on every backend the test matrix uses.
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token abgelaufen")

    user: Optional[User] = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Konto existiert nicht mehr")

    user.is_active = True
    row.consumed_at = now
    db.add(SignupAuditLog(
        tenant_id=row.tenant_id,
        email=user.email,
        event="email_verified",
        ip_address=ip_address,
        user_agent=user_agent,
    ))
    db.commit()
    return row.tenant_id


def resend(db: Session, *, email: str, ip_address: Optional[str], user_agent: Optional[str]) -> Optional[SignupResult]:
    """Invalidate outstanding tokens for ``email`` and issue a new one.

    Returns None when no inactive admin exists for ``email`` — the public
    endpoint returns 202 regardless so enumeration is harmless.
    """
    user: Optional[User] = (
        db.query(User)
        .filter(User.email == email, User.role == UserRole.ADMIN, User.is_active == False)  # noqa: E712
        .first()
    )
    if user is None:
        db.add(SignupAuditLog(
            email=email, event="resend_rejected_unknown",
            ip_address=ip_address, user_agent=user_agent,
        ))
        db.commit()
        return None

    # Invalidate any outstanding token so the previous link stops working.
    (
        db.query(SignupToken)
        .filter(SignupToken.user_id == user.id, SignupToken.consumed_at.is_(None))
        .update({SignupToken.consumed_at: datetime.now(timezone.utc)}, synchronize_session=False)
    )
    raw_token = secrets.token_urlsafe(32)
    db.add(SignupToken(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=VERIFY_TOKEN_TTL_HOURS),
    ))
    db.add(SignupAuditLog(
        tenant_id=user.tenant_id, email=email, event="resend_requested",
        ip_address=ip_address, user_agent=user_agent,
    ))
    db.commit()
    return SignupResult(tenant_id=user.tenant_id, user_id=user.id, verification_token=raw_token)


def suspend_expired_trials(db: Session) -> int:
    """Move tenants whose trial has ended AND have no Stripe subscription to
    ``subscription_status='suspended'``. Returns the number of rows updated.

    Called by the operator cron (bare endpoint under /api/superadmin) — no
    scheduler dependency yet.
    """
    now = datetime.now(timezone.utc)
    q = (
        db.query(Tenant)
        .filter(
            Tenant.plan == "trial",
            Tenant.trial_ends_at.isnot(None),
            Tenant.trial_ends_at < now,
            Tenant.stripe_subscription_id.is_(None),
            Tenant.subscription_status == "active",
        )
    )
    updated = q.update({Tenant.subscription_status: "suspended"}, synchronize_session=False)
    db.commit()
    return updated
