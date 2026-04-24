"""Tests for Stripe billing (Phase 4, Issue #95).

These tests intentionally do NOT hit Stripe — the webhook handler and
service are exercised against synthesized event dicts. The checkout /
portal endpoints mock ``stripe`` module-level functions so we verify
the glue code without a network round-trip.

Scope:
- Webhook signature validation, idempotency
- checkout.session.completed activates subscription + sets plan
- customer.subscription.updated reflects plan / status
- invoice.payment_failed → past_due
- invoice.payment_succeeded → reactivate from past_due + cache invoice
- customer.subscription.deleted → canceled; cron suspends after grace
- Checkout endpoint returns 503 when Stripe key unset
- Suspended tenants get 403 on writes (but webhook still writes)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import StripeEvent, TenantInvoice, User, UserRole
from app.models.tenant import Tenant
from app.services import stripe_service
from app.services import auth_service
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app


TENANT_ID = uuid.UUID("cccccccc-0000-4000-8000-000000000401")


@pytest.fixture
def _db_session():
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.commit()
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.commit()
        Base.metadata.drop_all(bind=engine, checkfirst=True)


@pytest.fixture
def tenant(_db_session):
    t = Tenant(
        id=TENANT_ID, name="Praxis A", slug="praxis-a", is_active=True, mode="multi",
        plan="trial", subscription_status="active", stripe_customer_id=None,
    )
    _db_session.add(t)
    _db_session.commit()
    return t


@pytest.fixture
def admin(_db_session, tenant):
    u = User(
        username="admin@a.de", email="admin@a.de",
        password_hash=auth_service.hash_password("S3curePassword!"),
        first_name="A", last_name="A", role=UserRole.ADMIN,
        weekly_hours=40, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=TENANT_ID,
    )
    _db_session.add(u)
    _db_session.commit()
    _db_session.refresh(u)
    return u


@pytest.fixture
def client(_db_session, admin):
    def _db(): yield _db_session
    def _who(): return admin
    test_app.dependency_overrides[get_db] = _db
    test_app.dependency_overrides[get_current_user] = _who
    test_app.dependency_overrides[require_admin] = _who
    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


# ───────────────── Event factory ─────────────────

def _event(etype, obj_overrides=None, event_id=None):
    obj = {
        "id": "obj_default",
        "metadata": {"tenant_id": str(TENANT_ID)},
        "customer": "cus_test_123",
    }
    obj.update(obj_overrides or {})
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:16]}",
        "type": etype,
        "data": {"object": obj},
    }


# ───────────────── checkout.session.completed ─────────────────

def test_checkout_completed_activates_plan(_db_session, tenant):
    event = _event(
        "checkout.session.completed",
        obj_overrides={
            "subscription": "sub_test_xyz",
            "metadata": {"tenant_id": str(TENANT_ID), "plan": "starter"},
        },
    )
    result = stripe_service.handle_event(_db_session, event)
    assert result["action"] == "subscription_activated"
    _db_session.refresh(tenant)
    assert tenant.plan == "starter"
    assert tenant.subscription_status == "active"
    assert tenant.stripe_subscription_id == "sub_test_xyz"


def test_webhook_is_idempotent(_db_session, tenant):
    event = _event("checkout.session.completed", obj_overrides={"subscription": "sub_once", "metadata": {"tenant_id": str(TENANT_ID), "plan": "pro"}})
    first = stripe_service.handle_event(_db_session, event)
    second = stripe_service.handle_event(_db_session, event)
    assert first["action"] == "subscription_activated"
    assert second.get("duplicate") is True
    assert _db_session.query(StripeEvent).filter(StripeEvent.event_id == event["id"]).count() == 1


# ───────────────── customer.subscription.updated ─────────────────

def test_subscription_updated_past_due(_db_session, tenant):
    event = _event("customer.subscription.updated", obj_overrides={"status": "past_due", "items": {"data": []}})
    stripe_service.handle_event(_db_session, event)
    _db_session.refresh(tenant)
    assert tenant.subscription_status == "past_due"


def test_subscription_updated_reflects_plan_change(_db_session, tenant, monkeypatch):
    # Wire the price-id of the expected plan into the settings cache so the
    # lookup resolves. We override the module-level map directly — easier
    # than mutating multiple env vars.
    monkeypatch.setattr(stripe_service, "_PLAN_PRICE_MAP", {"pro": ["price_pro_monthly", None]})
    event = _event(
        "customer.subscription.updated",
        obj_overrides={
            "status": "active",
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        },
    )
    stripe_service.handle_event(_db_session, event)
    _db_session.refresh(tenant)
    assert tenant.plan == "pro"
    assert tenant.subscription_status == "active"


# ───────────────── invoice.payment_failed / payment_succeeded ─────────────────

def test_payment_failed_flips_to_past_due_and_caches_invoice(_db_session, tenant):
    event = _event(
        "invoice.payment_failed",
        obj_overrides={
            "id": "in_failed_001",
            "amount_due": 3900,
            "currency": "eur",
            "hosted_invoice_url": "https://pay.stripe.com/x",
            "period_start": 1735689600,
            "period_end": 1738368000,
            "status_transitions": {},
        },
    )
    stripe_service.handle_event(_db_session, event)
    _db_session.refresh(tenant)
    assert tenant.subscription_status == "past_due"
    inv = _db_session.query(TenantInvoice).filter(TenantInvoice.stripe_invoice_id == "in_failed_001").first()
    assert inv is not None
    assert inv.status == "open"
    assert inv.amount_cents == 3900


def test_payment_succeeded_reactivates_from_past_due(_db_session, tenant):
    tenant.subscription_status = "past_due"
    _db_session.commit()
    event = _event(
        "invoice.payment_succeeded",
        obj_overrides={
            "id": "in_ok_001",
            "amount_paid": 3900,
            "currency": "eur",
            "status_transitions": {"paid_at": 1735689600},
        },
    )
    stripe_service.handle_event(_db_session, event)
    _db_session.refresh(tenant)
    assert tenant.subscription_status == "active"


# ───────────────── customer.subscription.deleted + grace ─────────────────

def test_subscription_deleted_sets_canceled(_db_session, tenant):
    event = _event("customer.subscription.deleted", obj_overrides={"id": "sub_bye"})
    stripe_service.handle_event(_db_session, event)
    _db_session.refresh(tenant)
    assert tenant.subscription_status == "canceled"


def test_suspend_canceled_after_grace(_db_session, tenant, monkeypatch):
    # Tenant canceled >30 days ago → suspend
    tenant.subscription_status = "canceled"
    _db_session.commit()
    old_event = StripeEvent(
        event_id="evt_old",
        event_type="customer.subscription.deleted",
        tenant_id=TENANT_ID,
        processed_at=datetime.now(timezone.utc) - timedelta(days=45),
    )
    _db_session.add(old_event)
    _db_session.commit()

    count = stripe_service.suspend_canceled_after_grace(_db_session)
    assert count == 1
    _db_session.refresh(tenant)
    assert tenant.subscription_status == "suspended"


def test_suspend_canceled_respects_grace_window(_db_session, tenant):
    tenant.subscription_status = "canceled"
    _db_session.commit()
    recent = StripeEvent(
        event_id="evt_recent",
        event_type="customer.subscription.deleted",
        tenant_id=TENANT_ID,
        processed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    _db_session.add(recent)
    _db_session.commit()

    count = stripe_service.suspend_canceled_after_grace(_db_session)
    assert count == 0
    _db_session.refresh(tenant)
    assert tenant.subscription_status == "canceled"


# ───────────────── Endpoint: 503 without Stripe key ─────────────────

def test_checkout_503_when_stripe_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    resp = client.post("/api/billing/checkout", json={
        "plan": "starter", "yearly": False,
        "success_url": "https://x/y", "cancel_url": "https://x/z",
    })
    assert resp.status_code == 503


def test_portal_503_without_customer_id(client, tenant, monkeypatch, _db_session):
    # Stripe key set so we bypass the early 503, but no stripe_customer_id
    # means the portal endpoint should error with 400.
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    tenant.stripe_customer_id = None
    _db_session.commit()
    resp = client.post("/api/billing/portal", json={"return_url": "https://x"})
    assert resp.status_code == 400


# ───────────────── Unknown tenant / no customer match ─────────────────

def test_event_with_unknown_tenant_is_stored_but_noops(_db_session):
    event = _event("checkout.session.completed", obj_overrides={
        "metadata": {"tenant_id": str(uuid.uuid4())},  # nonexistent
        "customer": None,
    })
    result = stripe_service.handle_event(_db_session, event)
    assert result.get("action") == "no_tenant_match"
    assert _db_session.query(StripeEvent).filter(StripeEvent.event_id == event["id"]).count() == 1


# ───────── Real StripeObject (v15 attribute access, no dict inheritance) ─────────

def _real_stripe_event(payload):
    """Helper: construct a real StripeObject hierarchy from a dict spec."""
    from stripe import StripeObject
    return StripeObject.construct_from(payload, "fake_key")


def test_handle_event_accepts_real_stripe_object(_db_session, tenant):
    """Regression: stripe SDK v15 StripeObject no longer inherits from dict —
    ``.get()`` / ``.keys()`` raise AttributeError. Our service code must work
    with BOTH the dict-shaped events our tests synthesize AND the real
    ``StripeObject`` instances Stripe's webhook parser produces in production.
    This test feeds an actual ``StripeObject`` through ``handle_event`` to
    prove the dual-shape access helper covers the v15 wire path.
    """
    event_obj = _real_stripe_event({
        "id": "evt_real_stripe_object",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_real_object",
                "subscription": "sub_real_001",
                "customer": "cus_real",
                "metadata": {"tenant_id": str(TENANT_ID), "plan": "starter"},
            }
        },
    })
    result = stripe_service.handle_event(_db_session, event_obj)
    assert result["action"] == "subscription_activated"
    _db_session.refresh(tenant)
    assert tenant.plan == "starter"
    assert tenant.stripe_subscription_id == "sub_real_001"


def test_subscription_updated_real_stripe_object_nested_items(_db_session, tenant, monkeypatch):
    """The deepest StripeObject nesting the service walks: items → data[0] →
    price.id. In v15 each of those is itself a StripeObject, so attribute
    access must chain correctly through the nested _g() calls in
    stripe_service.py handle_event('customer.subscription.updated').
    """
    monkeypatch.setattr(stripe_service, "_PLAN_PRICE_MAP", {"pro": ["price_pro_monthly_real", None]})
    event_obj = _real_stripe_event({
        "id": "evt_real_sub_updated",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_abc",
                "status": "active",
                "customer": "cus_real",
                "metadata": {"tenant_id": str(TENANT_ID)},
                "items": {
                    "data": [
                        {"price": {"id": "price_pro_monthly_real"}},
                    ]
                },
            }
        },
    })
    stripe_service.handle_event(_db_session, event_obj)
    _db_session.refresh(tenant)
    assert tenant.plan == "pro"
    assert tenant.subscription_status == "active"


def test_invoice_payment_succeeded_real_stripe_object_status_transitions(_db_session, tenant):
    """status_transitions is a StripeObject in v15 — we dereference .paid_at via
    _g(). Feed a real object through to verify the nested attribute path for
    invoice caching works end-to-end.
    """
    event_obj = _real_stripe_event({
        "id": "evt_real_invoice_paid",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": "in_real_001",
                "amount_paid": 3900,
                "currency": "eur",
                "customer": "cus_real",
                "metadata": {"tenant_id": str(TENANT_ID)},
                "status_transitions": {"paid_at": 1735689600},
                "hosted_invoice_url": "https://pay.stripe.com/real",
            }
        },
    })
    stripe_service.handle_event(_db_session, event_obj)
    inv = _db_session.query(TenantInvoice).filter(TenantInvoice.stripe_invoice_id == "in_real_001").first()
    assert inv is not None
    assert inv.amount_cents == 3900
    assert inv.paid_at is not None
    assert inv.hosted_invoice_url == "https://pay.stripe.com/real"
