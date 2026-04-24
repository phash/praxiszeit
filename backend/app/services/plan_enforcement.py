"""Plan gating: seat limits + feature flags (Phase 5 / Issue #96).

Single source of truth for "what does plan X include?". The Stripe
webhook sets ``tenant.plan``; routes call ``check_seat_limit()`` and
``requires_feature()`` to enforce it.

Plan matrix:
    trial       5 seats    all features (so evaluators see the full UX)
    starter     5 seats    no SSO, no advanced reporting, no custom branding
    pro        25 seats    everything except custom branding
    enterprise  unlimited  everything + SLA (not modelled in code)

``seat_limit=None`` on the tenant row always means unlimited (overrides
the plan default). Superadmin can override the per-tenant seat_limit to
accommodate special deals without a plan change.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import User
from app.models.tenant import Tenant


# plan → (seat_limit, features)
_PLAN_DEFAULTS: dict[str, tuple[int | None, set[str]]] = {
    "trial": (5, {"reports", "change_requests", "sso", "advanced_reporting"}),
    "starter": (5, {"reports", "change_requests"}),
    "pro": (25, {"reports", "change_requests", "sso", "advanced_reporting"}),
    "enterprise": (None, {"reports", "change_requests", "sso", "advanced_reporting", "custom_branding"}),
}


def seat_limit_for(tenant: Tenant) -> int | None:
    """Effective seat limit: tenant.seat_limit override takes precedence
    over the plan default. None = unlimited."""
    if tenant.seat_limit is not None:
        return tenant.seat_limit
    default, _ = _PLAN_DEFAULTS.get(tenant.plan, (None, set()))
    return default


def get_plan_features(plan: str) -> set[str]:
    _, features = _PLAN_DEFAULTS.get(plan, (None, set()))
    return set(features)


def active_seat_count(db: Session, tenant_id) -> int:
    return (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active == True)  # noqa: E712
        .count()
    )


def check_seat_limit(db: Session, tenant: Tenant) -> None:
    """Raise 403 when the tenant is at or above its seat limit.

    Called by admin_users.create_user BEFORE db.add; keeps the race-window
    small but we still wrap the subsequent INSERT + COMMIT — we don't need
    a SELECT FOR UPDATE because a rare +1 over-provision is fine (the cron
    in Phase 6 can reconcile).
    """
    limit = seat_limit_for(tenant)
    if limit is None:
        return
    used = active_seat_count(db, tenant.id)
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Sitzlimit erreicht ({used}/{limit}). Bitte Plan upgraden, "
                "um weitere Mitarbeiter hinzuzufügen."
            ),
        )


def require_feature(tenant: Tenant, feature: str) -> None:
    """Raise 403 when the tenant's plan doesn't include ``feature``."""
    if feature not in get_plan_features(tenant.plan):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Feature '{feature}' nicht im aktuellen Plan enthalten",
        )
