"""Tenant-billing self-service endpoints (Phase 2, Issue #93).

Read-only-ish: admins can read their tenant's billing state and invoice
history, and PATCH a narrow set of billing-address fields. plan /
subscription_status / stripe_* are off-limits — those are driven by the
Stripe webhook (Phase 4) and the superadmin.
"""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import require_admin
from app.models import Tenant, TenantInvoice, User
from app.schemas.tenant import (
    TenantBillingResponse,
    TenantBillingUpdate,
    TenantInvoiceResponse,
)


router = APIRouter(prefix="/api/tenant", tags=["tenant-billing"])


@router.get("/usage")
def get_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return seat usage + plan features for the banner / billing UI."""
    from app.services.plan_enforcement import (
        active_seat_count, get_plan_features, seat_limit_for,
    )
    tenant = _get_own_tenant(db, current_user)
    return {
        "plan": tenant.plan,
        "subscription_status": tenant.subscription_status,
        "used_seats": active_seat_count(db, tenant.id),
        "seat_limit": seat_limit_for(tenant),  # None = unlimited
        "features": sorted(get_plan_features(tenant.plan)),
        "trial_ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
    }


def _get_own_tenant(db: Session, current_user: User) -> Tenant:
    """Fetch the caller's tenant. Explicit filter belt-and-suspenders:
    RLS would already scope this, but matching Phase 0 Issue #91 pattern."""
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == current_user.tenant_id)
        .first()
    )
    if tenant is None:
        # Should not happen — means the JWT tid claim outlived the tenant row.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nicht gefunden")
    return tenant


@router.get("/billing", response_model=TenantBillingResponse)
def get_billing(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TenantBillingResponse:
    """Return the caller tenant's current billing state + plan."""
    tenant = _get_own_tenant(db, current_user)
    return TenantBillingResponse(
        id=str(tenant.id),
        plan=tenant.plan,
        subscription_status=tenant.subscription_status,
        trial_ends_at=tenant.trial_ends_at,
        seat_limit=tenant.seat_limit,
        stripe_customer_id=tenant.stripe_customer_id,
        stripe_subscription_id=tenant.stripe_subscription_id,
        billing_email=tenant.billing_email,
        company_name=tenant.company_name,
        vat_id=tenant.vat_id,
        country=tenant.country,
        billing_address=tenant.billing_address,
    )


@router.patch("/billing", response_model=TenantBillingResponse)
def update_billing(
    body: TenantBillingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TenantBillingResponse:
    """Update a narrow set of billing-address fields.

    plan / subscription_status / stripe_* are intentionally not here —
    those are owned by the Stripe webhook and the superadmin.
    """
    tenant = _get_own_tenant(db, current_user)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "billing_address" and value is not None:
            # Pydantic model → dict for JSONB storage.
            setattr(tenant, field, value if isinstance(value, dict) else value.model_dump())
        elif field == "country" and value is not None:
            setattr(tenant, field, value.upper())
        else:
            setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    return TenantBillingResponse(
        id=str(tenant.id),
        plan=tenant.plan,
        subscription_status=tenant.subscription_status,
        trial_ends_at=tenant.trial_ends_at,
        seat_limit=tenant.seat_limit,
        stripe_customer_id=tenant.stripe_customer_id,
        stripe_subscription_id=tenant.stripe_subscription_id,
        billing_email=tenant.billing_email,
        company_name=tenant.company_name,
        vat_id=tenant.vat_id,
        country=tenant.country,
        billing_address=tenant.billing_address,
    )


@router.get("/invoices", response_model=List[TenantInvoiceResponse])
def list_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> List[TenantInvoiceResponse]:
    """List the caller tenant's cached Stripe invoices, newest first."""
    rows = (
        db.query(TenantInvoice)
        # Belt-and-suspenders (Issue #91 / F-026): RLS already scopes this,
        # but an explicit filter survives a missing SET LOCAL.
        .filter(TenantInvoice.tenant_id == current_user.tenant_id)
        .order_by(TenantInvoice.created_at.desc())
        .all()
    )
    return [
        TenantInvoiceResponse(
            id=str(r.id),
            stripe_invoice_id=r.stripe_invoice_id,
            amount_cents=r.amount_cents,
            currency=r.currency,
            status=r.status,
            paid_at=r.paid_at,
            period_start=r.period_start,
            period_end=r.period_end,
            hosted_invoice_url=r.hosted_invoice_url,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ─── Lifecycle endpoints (Phase 6, Issue #97) ──────────────────────────

class TransferOwnershipRequest(BaseModel):
    new_owner_id: str


@router.post("/suspend")
def self_suspend(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin schedules self-suspension 7 days from now (grace window so
    the UI can reverse it before the cron applies it)."""
    from app.services import lifecycle_service
    tenant = _get_own_tenant(db, current_user)
    when = lifecycle_service.request_suspend(db, tenant, current_user)
    return {"scheduled_suspend_at": when.isoformat()}


@router.post("/cancel-suspend")
def cancel_self_suspend(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services import lifecycle_service
    tenant = _get_own_tenant(db, current_user)
    lifecycle_service.cancel_suspend(db, tenant)
    return {"ok": True}


@router.post("/request-deletion")
def request_deletion(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin requests tenant deletion. Cron anonymizes after 30d grace.
    The response includes the deadline so the UI can show a countdown."""
    from app.services import lifecycle_service
    tenant = _get_own_tenant(db, current_user)
    deadline = lifecycle_service.request_deletion(db, tenant, current_user)
    return {"anonymize_after": deadline.isoformat()}


@router.post("/cancel-deletion")
def cancel_deletion(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services import lifecycle_service
    tenant = _get_own_tenant(db, current_user)
    lifecycle_service.cancel_deletion(db, tenant)
    return {"ok": True}


@router.post("/transfer-ownership")
def transfer_ownership(
    body: TransferOwnershipRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services import lifecycle_service
    import uuid as _uuid
    try:
        new_owner_uuid = _uuid.UUID(body.new_owner_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültige new_owner_id")
    new_owner = lifecycle_service.transfer_ownership(db, current_user, new_owner_uuid)
    return {"ok": True, "new_owner_id": str(new_owner.id), "new_owner_email": new_owner.email}


@router.get("/export")
def export(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin self-service full data export (JSON). Mirrors the superadmin
    ArbZG export but scoped to the caller's own tenant."""
    from app.services import lifecycle_service
    tenant = _get_own_tenant(db, current_user)
    payload = lifecycle_service.build_tenant_export_payload(db, tenant, requester=current_user)
    blob = lifecycle_service.export_as_json_bytes(payload)
    filename = (
        f"PraxisZeit_Export_{tenant.slug}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    )
    return StreamingResponse(
        iter([blob]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/avv")
def download_avv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Personalised AVV draft PDF. DRAFT — legal review required."""
    from app.services.avv_generator import generate_avv_pdf
    tenant = _get_own_tenant(db, current_user)
    pdf = generate_avv_pdf(tenant)
    filename = f"PraxisZeit_AVV_{tenant.slug}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
