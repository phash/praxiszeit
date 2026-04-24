"""Pydantic schemas for tenant billing (Phase 2, Issue #93).

``PATCH /api/tenant/billing`` intentionally excludes plan/stripe_*/
subscription_status — those fields are owned by the Stripe webhook and
the superadmin, not by self-service admins.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


Plan = Literal["trial", "starter", "pro", "enterprise"]
SubscriptionStatus = Literal["active", "past_due", "canceled", "suspended"]


class BillingAddress(BaseModel):
    """Free-form billing address — shape is advisory, not DB-enforced."""

    street: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    # country is duplicated at the tenant level (ISO-3166-1 alpha-2) because
    # the tenant-level field drives tax logic; the nested copy is for display.
    country: Optional[str] = None


class TenantBillingResponse(BaseModel):
    """Full billing state returned by GET /api/tenant/billing."""

    id: str
    plan: Plan
    subscription_status: SubscriptionStatus
    trial_ends_at: Optional[datetime] = None
    seat_limit: Optional[int] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    billing_email: Optional[str] = None
    company_name: Optional[str] = None
    vat_id: Optional[str] = None
    country: Optional[str] = None
    billing_address: Optional[BillingAddress] = None

    model_config = ConfigDict(from_attributes=True)


class TenantBillingUpdate(BaseModel):
    """Admin-editable subset of billing fields.

    plan / subscription_status / stripe_* are deliberately NOT here —
    they are driven by Stripe webhooks (Phase 4) or by superadmin.
    """

    billing_email: Optional[EmailStr] = None
    company_name: Optional[str] = Field(None, max_length=255)
    vat_id: Optional[str] = Field(None, max_length=50)
    country: Optional[str] = Field(None, min_length=2, max_length=2)
    billing_address: Optional[BillingAddress] = None


class TenantInvoiceResponse(BaseModel):
    id: str
    stripe_invoice_id: str
    amount_cents: int
    currency: str
    status: str
    paid_at: Optional[datetime] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    hosted_invoice_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
