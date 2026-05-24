"""Tests for Stripe webhook payload PII scrubbing (Issue #129).

Before this change, ``stripe_service._record_event`` stored
``str(event.data)[:4000]`` in ``stripe_events.payload_excerpt`` — which
includes ``customer_email``, ``customer_details.name``,
``billing_address`` and other DSGVO-relevant fields straight from Stripe.

The fix replaces that with a whitelist-only excerpt
(``_build_safe_payload_excerpt``). These tests exist to make sure the
whitelist is the single source of truth: nothing that isn't explicitly
allow-listed may show up in the stored excerpt.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.database import Base
from app.models import StripeEvent
from app.models.tenant import Tenant
from app.services import stripe_service
from tests.conftest import engine, TestingSessionLocal


TENANT_ID = uuid.UUID("dddddddd-0000-4000-8000-000000000909")


# ───────────────── Fixtures ─────────────────

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
        id=TENANT_ID,
        name="Praxis PII-Test",
        slug="praxis-pii-test",
        is_active=True,
        mode="multi",
        plan="trial",
        subscription_status="active",
    )
    _db_session.add(t)
    _db_session.commit()
    return t


# ───────────────── Pure helper tests ─────────────────

# Realistic-ish Stripe ``checkout.session.completed`` payload that bundles all
# the PII fields we used to leak. Field names + structure mirror the real
# Stripe API (see docs/api/checkout/sessions/object).
_PII_EVENT_DATA = {
    "object": {
        "id": "cs_test_abc123",
        "object": "checkout.session",
        "amount_total": 4900,
        "currency": "eur",
        "customer": "cus_PrivacyTest",
        "subscription": "sub_PrivacyTest",
        "status": "complete",
        "metadata": {"tenant_id": str(TENANT_ID), "plan": "starter"},
        # ---- PII below: none of this may end up in the excerpt ----
        "customer_email": "hans.mueller@example.com",
        "customer_details": {
            "email": "hans.mueller@example.com",
            "name": "Hans Müller",
            "phone": "+49 170 1234567",
            "address": {
                "line1": "Musterstrasse 1",
                "city": "Berlin",
                "postal_code": "10115",
                "country": "DE",
            },
            "tax_ids": [{"type": "eu_vat", "value": "DE123456789"}],
        },
        "shipping": {
            "name": "Hans Müller",
            "address": {"line1": "Musterstrasse 1", "city": "Berlin"},
        },
        "receipt_email": "hans.mueller@example.com",
    }
}


def test_excerpt_omits_email_and_name():
    excerpt = stripe_service._build_safe_payload_excerpt(_PII_EVENT_DATA)
    assert "hans.mueller@example.com" not in excerpt
    assert "Hans Müller" not in excerpt
    assert "Hans M\\u00fcller" not in excerpt  # JSON-escaped form, just in case


def test_excerpt_omits_address_and_phone():
    excerpt = stripe_service._build_safe_payload_excerpt(_PII_EVENT_DATA)
    for forbidden in (
        "Musterstrasse 1",
        "Berlin",
        "10115",
        "+49 170 1234567",
        "DE123456789",
    ):
        assert forbidden not in excerpt, f"PII leaked: {forbidden!r} in excerpt"


def test_excerpt_omits_customer_details_container():
    excerpt = stripe_service._build_safe_payload_excerpt(_PII_EVENT_DATA)
    # The whole container keys for PII data must also be gone — otherwise an
    # empty {} object would still tell an attacker the shape was present.
    for forbidden_key in ("customer_email", "customer_details", "shipping", "receipt_email"):
        assert forbidden_key not in excerpt


def test_excerpt_keeps_object_id_amount_currency():
    excerpt = stripe_service._build_safe_payload_excerpt(_PII_EVENT_DATA)
    parsed = json.loads(excerpt)
    assert parsed["object_id"] == "cs_test_abc123"
    assert parsed["currency"] == "eur"
    assert parsed["amount"] == 4900
    assert parsed["customer"] == "cus_PrivacyTest"
    assert parsed["subscription"] == "sub_PrivacyTest"
    assert parsed["object_status"] == "complete"


def test_excerpt_keeps_our_own_metadata_for_correlation():
    excerpt = stripe_service._build_safe_payload_excerpt(_PII_EVENT_DATA)
    parsed = json.loads(excerpt)
    assert parsed["metadata"] == {"tenant_id": str(TENANT_ID), "plan": "starter"}


def test_excerpt_whitelist_blocks_unknown_fields():
    """A newly-added Stripe field that we haven't reviewed for PII must
    NOT silently appear in the excerpt. Whitelist beats blacklist."""
    event_data = {
        "object": {
            "id": "in_test",
            "amount_paid": 1000,
            "currency": "eur",
            # Imagine Stripe adds these in a future API version:
            "customer_phone": "+49 170 9999999",
            "biometric_signature": "deadbeef",
            "national_id": "123-45-6789",
            "ip_address": "203.0.113.42",
        }
    }
    excerpt = stripe_service._build_safe_payload_excerpt(event_data)
    for forbidden in (
        "customer_phone",
        "+49 170 9999999",
        "biometric_signature",
        "deadbeef",
        "national_id",
        "123-45-6789",
        "ip_address",
        "203.0.113.42",
    ):
        assert forbidden not in excerpt, f"Whitelist leak: {forbidden!r}"


def test_excerpt_uses_amount_due_for_failed_invoices():
    """``invoice.payment_failed`` only has ``amount_due``, not
    ``amount`` / ``amount_total`` / ``amount_paid`` — we fall back through
    the alternatives so the audit trail still captures the figure."""
    event_data = {
        "object": {
            "id": "in_due",
            "amount_due": 3900,
            "currency": "eur",
            "status": "open",
        }
    }
    excerpt = stripe_service._build_safe_payload_excerpt(event_data)
    parsed = json.loads(excerpt)
    assert parsed["amount"] == 3900


def test_excerpt_is_truncated_to_safety_cap():
    """A pathological metadata blob must not let the excerpt grow without
    bound — the 4000-char cap is our safety net."""
    big = "x" * 10_000
    event_data = {
        "object": {
            "id": "obj_big",
            "currency": "eur",
            "metadata": {"tenant_id": big, "plan": big},
        }
    }
    excerpt = stripe_service._build_safe_payload_excerpt(event_data)
    assert len(excerpt) <= stripe_service._PAYLOAD_EXCERPT_MAX_LEN


def test_excerpt_handles_missing_object():
    """Defensive: malformed event without ``object`` must not blow up."""
    excerpt = stripe_service._build_safe_payload_excerpt({})
    parsed = json.loads(excerpt)
    assert parsed["object_id"] is None
    # And: no PII to leak when there's no input data at all.
    assert "@" not in excerpt


def test_excerpt_handles_none_event_data():
    excerpt = stripe_service._build_safe_payload_excerpt(None)
    parsed = json.loads(excerpt)
    assert parsed["object_id"] is None


# ───────────────── Integration: _record_event writes scrubbed excerpt ─────────────────

def test_record_event_persists_only_scrubbed_excerpt(_db_session, tenant):
    """End-to-end: when ``handle_event`` runs on an event carrying PII,
    the stored ``stripe_events.payload_excerpt`` row must NOT contain
    any of the PII strings."""
    event = {
        "id": f"evt_pii_{uuid.uuid4().hex[:12]}",
        "type": "checkout.session.completed",
        "data": _PII_EVENT_DATA,
    }
    result = stripe_service.handle_event(_db_session, event)
    assert result["action"] == "subscription_activated"

    row = (
        _db_session.query(StripeEvent)
        .filter(StripeEvent.event_id == event["id"])
        .one()
    )
    assert row.payload_excerpt is not None
    assert "hans.mueller@example.com" not in row.payload_excerpt
    assert "Hans Müller" not in row.payload_excerpt
    assert "Musterstrasse 1" not in row.payload_excerpt
    assert "+49 170 1234567" not in row.payload_excerpt
    assert "DE123456789" not in row.payload_excerpt
    # Useful audit info is still there:
    parsed = json.loads(row.payload_excerpt)
    assert parsed["object_id"] == "cs_test_abc123"
    assert parsed["amount"] == 4900
    assert parsed["metadata"]["tenant_id"] == str(TENANT_ID)


def test_record_event_handles_real_stripe_object_without_leaking(_db_session, tenant):
    """The v15 StripeObject path must scrub PII too, not just plain dicts."""
    from stripe import StripeObject
    event = StripeObject.construct_from({
        "id": f"evt_real_pii_{uuid.uuid4().hex[:12]}",
        "type": "checkout.session.completed",
        "data": _PII_EVENT_DATA,
    }, "fake_key")
    stripe_service.handle_event(_db_session, event)

    row = (
        _db_session.query(StripeEvent)
        .filter(StripeEvent.event_id == event["id"])
        .one()
    )
    assert "hans.mueller@example.com" not in row.payload_excerpt
    assert "Hans Müller" not in row.payload_excerpt
    parsed = json.loads(row.payload_excerpt)
    assert parsed["object_id"] == "cs_test_abc123"
