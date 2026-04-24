"""/api/billing/* — Stripe-powered self-service (Phase 4 / Issue #95).

The checkout + portal endpoints require admin auth and redirect to
Stripe-hosted pages. The webhook is unauthenticated (Stripe-signed).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db, set_superadmin_context
from app.middleware.auth import require_admin
from app.models import Tenant, User
from app.services import stripe_service


router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str  # 'starter' | 'pro'
    yearly: bool = False
    success_url: str
    cancel_url: str


class UrlResponse(BaseModel):
    url: str


def _own_tenant(db: Session, user: User) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant nicht gefunden")
    return tenant


@router.post("/checkout", response_model=UrlResponse)
def checkout(
    body: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UrlResponse:
    tenant = _own_tenant(db, current_user)
    url = stripe_service.create_checkout_session(
        db,
        tenant,
        plan=body.plan,
        yearly=body.yearly,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
    )
    return UrlResponse(url=url)


class PortalRequest(BaseModel):
    return_url: str


@router.post("/portal", response_model=UrlResponse)
def portal(
    body: PortalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UrlResponse:
    tenant = _own_tenant(db, current_user)
    url = stripe_service.create_portal_session(tenant, return_url=body.return_url)
    return UrlResponse(url=url)


# ─── Webhook (unauthenticated, Stripe-signed) ──────────────────────────

webhook_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _webhook_db():
    """Webhook is unauthenticated — runs with superadmin context so it can
    update any tenant's subscription state."""
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        yield db
    finally:
        db.close()


@webhook_router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(_webhook_db)):
    sig = request.headers.get("stripe-signature", "")
    payload = await request.body()
    event = stripe_service.verify_and_parse_event(payload, sig)
    result = stripe_service.handle_event(db, event)
    return result
