"""Stripe-API wrapper + webhook dispatcher (Phase 4 / Issue #95).

Design notes
------------
- ``_require_stripe()`` raises 503 when ``STRIPE_SECRET_KEY`` is unset —
  we don't want an admin to get as far as the Checkout redirect and then
  see Stripe's own error. The billing UI checks ``/api/system/info`` to
  decide whether to render billing actions.
- Webhook processing is idempotent via the ``stripe_events`` table. We
  insert the ``event_id`` row BEFORE any state mutation, so a duplicate
  delivery during a race hits a UNIQUE violation and short-circuits.
- The module keeps the plan-name → price-id mapping local; the source of
  truth for which price is which plan is ``_plan_from_price_id()``. When
  you add new Stripe products, update that function and the
  ``STRIPE_PRICE_*`` settings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import StripeEvent, TenantInvoice
from app.models.tenant import Tenant


logger = logging.getLogger(__name__)


def _g(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from a Stripe object or a dict, returning ``default`` when missing.

    Stripe Python SDK v15 dropped dict inheritance from ``StripeObject`` — ``.get()``
    / ``.keys()`` / ``.items()`` / iteration all raise ``AttributeError`` now, while
    ``obj["key"]`` subscripting still works. Our webhook tests still synthesize
    events as plain dicts (simpler than instantiating real ``StripeObject``s), so
    the service code must handle both shapes. This helper bridges them without
    leaking the choice into every call site.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _require_stripe():
    """Lazy-import stripe + assert a secret key is configured. Raises
    503 when billing is not operational so callers don't crash with an
    AttributeError or an unhelpful Stripe SDK error."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zahlungsabwicklung nicht konfiguriert",
        )
    import stripe  # type: ignore[import-not-found]
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def is_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


# ───────────────── Plan ↔ price mapping ───────────────────────────────

_PLAN_PRICE_MAP: dict[str, list[Optional[str]]] = {
    "starter": [settings.STRIPE_PRICE_STARTER_MONTHLY, settings.STRIPE_PRICE_STARTER_YEARLY],
    "pro": [settings.STRIPE_PRICE_PRO_MONTHLY, settings.STRIPE_PRICE_PRO_YEARLY],
}


def _plan_from_price_id(price_id: Optional[str]) -> Optional[str]:
    """Reverse map a Stripe price_id → our internal plan string."""
    if not price_id:
        return None
    for plan, prices in _PLAN_PRICE_MAP.items():
        if price_id in (p for p in prices if p):
            return plan
    return None


def price_id_for_plan(plan: str, *, yearly: bool = False) -> str:
    """Raise 400 when the plan isn't covered by configured Stripe prices."""
    prices = _PLAN_PRICE_MAP.get(plan)
    if not prices:
        raise HTTPException(status_code=400, detail=f"Unbekannter Plan: {plan}")
    candidate = prices[1] if yearly else prices[0]
    if not candidate:
        raise HTTPException(
            status_code=503,
            detail=f"Preis für Plan '{plan}' (yearly={yearly}) nicht konfiguriert",
        )
    return candidate


# ───────────────── Customer / Checkout / Portal ───────────────────────

def ensure_customer(db: Session, tenant: Tenant) -> str:
    """Return ``tenant.stripe_customer_id`` — create a Stripe customer if the
    tenant doesn't have one yet. Commits the tenant row."""
    stripe = _require_stripe()
    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id

    customer = stripe.Customer.create(
        name=tenant.company_name or tenant.name,
        email=tenant.billing_email,
        metadata={"tenant_id": str(tenant.id)},
    )
    tenant.stripe_customer_id = customer.id
    db.commit()
    return tenant.stripe_customer_id


def create_checkout_session(
    db: Session,
    tenant: Tenant,
    *,
    plan: str,
    yearly: bool,
    success_url: str,
    cancel_url: str,
) -> str:
    """Return a Stripe Checkout URL for the caller to redirect to."""
    stripe = _require_stripe()
    customer_id = ensure_customer(db, tenant)
    price_id = price_id_for_plan(plan, yearly=yearly)
    session_ = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tenant_id": str(tenant.id), "plan": plan},
    )
    return session_.url


def create_portal_session(tenant: Tenant, *, return_url: str) -> str:
    """Return a Stripe Customer-Portal URL for billing self-service."""
    stripe = _require_stripe()
    if not tenant.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Kein Stripe-Kunden-Account verknüpft")
    portal = stripe.billing_portal.Session.create(
        customer=tenant.stripe_customer_id,
        return_url=return_url,
    )
    return portal.url


# ───────────────── Webhook ────────────────────────────────────────────

def verify_and_parse_event(payload: bytes, sig_header: str):
    """Verify the Stripe signature and return the parsed event. Raises 400
    on any signature mismatch so we don't act on forged payloads."""
    stripe = _require_stripe()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    try:
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except Exception:  # stripe.error.SignatureVerificationError in real runs
        raise HTTPException(status_code=400, detail="Invalid signature")


def _tenant_from_event(db: Session, event) -> Optional[Tenant]:
    """Pull the tenant_id out of metadata (preferred) or match by
    stripe_customer_id as a fallback."""
    obj = event["data"]["object"]
    meta = _g(obj, "metadata") or {}
    tid = _g(meta, "tenant_id")
    if tid:
        return db.query(Tenant).filter(Tenant.id == tid).first()
    customer_id = _g(obj, "customer")
    if customer_id:
        return db.query(Tenant).filter(Tenant.stripe_customer_id == customer_id).first()
    return None


def _record_event(db: Session, event, tenant: Optional[Tenant]) -> bool:
    """Insert a ``stripe_events`` row. Returns False if the event was already
    recorded (duplicate delivery) and processing should be skipped."""
    record = StripeEvent(
        event_id=event["id"],
        event_type=event["type"],
        tenant_id=tenant.id if tenant else None,
        payload_excerpt=str(_g(event, "data"))[:4000],
    )
    try:
        db.add(record)
        db.flush()  # surfaces the unique violation before we mutate tenants
    except IntegrityError:
        db.rollback()
        logger.info("stripe webhook duplicate delivery ignored: %s", event["id"])
        return False
    return True


def handle_event(db: Session, event) -> dict:
    """Process a verified webhook event. Returns a summary dict for logging.

    Handles:
      - checkout.session.completed     → activate subscription + plan
      - customer.subscription.updated  → reflect plan / status change
      - customer.subscription.deleted  → canceled → schedule suspend
      - invoice.payment_succeeded      → update tenant_invoices + reactivate
      - invoice.payment_failed         → past_due
    """
    tenant = _tenant_from_event(db, event)
    if not _record_event(db, event, tenant):
        return {"duplicate": True, "event_id": event["id"]}

    etype = event["type"]
    obj = event["data"]["object"]
    action = "noop"

    if tenant is None:
        # We still persisted the event row so it's audited; but there's
        # nothing to mutate.
        db.commit()
        return {"action": "no_tenant_match", "event_id": event["id"]}

    if etype == "checkout.session.completed":
        # Mode=subscription → the session contains a subscription id.
        plan = _g(_g(obj, "metadata") or {}, "plan")
        tenant.stripe_subscription_id = _g(obj, "subscription") or tenant.stripe_subscription_id
        tenant.subscription_status = "active"
        if plan:
            tenant.plan = plan
            try:
                from app.services.alerting import alert_plan_upgrade
                alert_plan_upgrade(tenant.name, plan)
            except Exception:  # noqa: BLE001
                pass
        action = "subscription_activated"

    elif etype == "customer.subscription.updated":
        items_container = _g(obj, "items") or {}
        items = _g(items_container, "data") or []
        if items:
            price = _g(_g(items[0], "price"), "id")
            plan = _plan_from_price_id(price)
            if plan:
                tenant.plan = plan
        status_ = _g(obj, "status")  # active | past_due | canceled | …
        if status_ == "active":
            tenant.subscription_status = "active"
        elif status_ == "past_due":
            tenant.subscription_status = "past_due"
        elif status_ in ("canceled", "unpaid", "incomplete_expired"):
            tenant.subscription_status = "canceled"
        action = f"subscription_status={tenant.subscription_status}"

    elif etype == "customer.subscription.deleted":
        tenant.subscription_status = "canceled"
        action = "subscription_canceled"

    elif etype == "invoice.payment_succeeded":
        _upsert_invoice(db, tenant, obj, status_="paid")
        # If the tenant was past_due, a successful payment restores them.
        if tenant.subscription_status in ("past_due", "suspended"):
            tenant.subscription_status = "active"
        action = "invoice_paid"

    elif etype == "invoice.payment_failed":
        _upsert_invoice(db, tenant, obj, status_="open")
        tenant.subscription_status = "past_due"
        action = "invoice_failed"

    db.commit()
    return {"action": action, "event_id": event["id"], "tenant_id": str(tenant.id)}


def _upsert_invoice(db: Session, tenant: Tenant, obj, *, status_: str) -> None:
    inv_id = _g(obj, "id")
    if not inv_id:
        return
    existing: Optional[TenantInvoice] = (
        db.query(TenantInvoice).filter(TenantInvoice.stripe_invoice_id == inv_id).first()
    )
    # Stripe gives period as unix timestamps inside each line item; for
    # the cache we store the overall invoice period from the top-level
    # keys when available, otherwise fall back to None.
    def _ts(v):
        return datetime.fromtimestamp(v, tz=timezone.utc) if v else None

    transitions = _g(obj, "status_transitions") or {}
    paid_at = _ts(_g(transitions, "paid_at"))

    if existing is None:
        db.add(TenantInvoice(
            tenant_id=tenant.id,
            stripe_invoice_id=inv_id,
            amount_cents=_g(obj, "amount_paid") or _g(obj, "amount_due") or 0,
            currency=(_g(obj, "currency") or "eur").lower(),
            status=status_,
            paid_at=paid_at,
            period_start=_ts(_g(obj, "period_start")),
            period_end=_ts(_g(obj, "period_end")),
            hosted_invoice_url=_g(obj, "hosted_invoice_url"),
        ))
    else:
        existing.status = status_
        existing.amount_cents = _g(obj, "amount_paid") or _g(obj, "amount_due") or existing.amount_cents
        existing.paid_at = paid_at or existing.paid_at
        existing.hosted_invoice_url = _g(obj, "hosted_invoice_url") or existing.hosted_invoice_url


# ───────────────── Cron: canceled → suspended after grace ────────────

def suspend_canceled_after_grace(db: Session) -> int:
    """Flip tenants whose subscription has been 'canceled' for longer than
    STRIPE_CANCEL_GRACE_DAYS over to 'suspended'. Called from the
    /api/superadmin/cron/trial-check endpoint alongside trial suspension."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.STRIPE_CANCEL_GRACE_DAYS)
    q = (
        db.query(Tenant)
        .filter(
            Tenant.subscription_status == "canceled",
            # We don't track cancellation timestamp explicitly yet; use the
            # most recent StripeEvent of type customer.subscription.deleted.
        )
    )
    # Join in a subquery to find canceled-at timestamps.
    to_suspend = []
    for tenant in q.all():
        last_cancel = (
            db.query(StripeEvent)
            .filter(
                StripeEvent.tenant_id == tenant.id,
                StripeEvent.event_type == "customer.subscription.deleted",
            )
            .order_by(StripeEvent.processed_at.desc())
            .first()
        )
        if last_cancel:
            # SQLite strips timezone info; normalize both sides to tz-aware
            # UTC before comparing (same pattern as signup_service.verify).
            processed = last_cancel.processed_at
            if processed.tzinfo is None:
                processed = processed.replace(tzinfo=timezone.utc)
            if processed < cutoff:
                to_suspend.append(tenant)

    for tenant in to_suspend:
        tenant.subscription_status = "suspended"

    if to_suspend:
        db.commit()
    return len(to_suspend)
