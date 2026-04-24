from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from app.database import Base

# SQLite (used by the unit-test suite) can't compile JSONB. The variant
# falls back to plain JSON everywhere except Postgres, where JSONB gives
# us indexing + GIN + operator support.
_JsonType = JSON().with_variant(JSONB(), "postgresql")


class Tenant(Base):
    """Tenant model for multi-tenant isolation + SaaS billing state.

    Billing columns (Phase 2, Issue #93) are nullable because on-prem
    installs don't have a Stripe customer. For on-prem the default tenant
    is backfilled to ``plan='enterprise'``.
    """

    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    mode = Column(String(20), default="multi", nullable=False)  # 'single' | 'multi'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # SaaS billing (Phase 2)
    # Allowed plan values validated at the app layer (Pydantic enum); the DB
    # column stays free-form so future plans don't need a migration.
    plan = Column(String(20), default="trial", nullable=False)
    # 'active' | 'past_due' | 'canceled' | 'suspended'
    subscription_status = Column(String(20), default="active", nullable=False)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    seat_limit = Column(Integer, nullable=True)  # NULL = unlimited
    stripe_customer_id = Column(String(255), unique=True, nullable=True)
    stripe_subscription_id = Column(String(255), unique=True, nullable=True)
    billing_email = Column(String(255), nullable=True)
    company_name = Column(String(255), nullable=True)
    vat_id = Column(String(50), nullable=True)
    country = Column(String(2), nullable=True)  # ISO-3166-1 alpha-2
    billing_address = Column(_JsonType, nullable=True)

    def __repr__(self):
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"


class TenantInvoice(Base):
    """Cached mirror of Stripe invoices (populated by webhook in Phase 4).

    We keep the cache so the admin UI can show billing history without
    live-querying Stripe on every page load, and so RLS-filtered invoice
    listings work without embedding Stripe-customer knowledge in the
    database layer.
    """

    __tablename__ = "tenant_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    stripe_invoice_id = Column(String(255), unique=True, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), default="eur", nullable=False)
    # 'open' | 'paid' | 'uncollectible' | 'void' | 'draft' — mirrors Stripe
    status = Column(String(20), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    hosted_invoice_url = Column(String(), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<TenantInvoice(id={self.id}, tenant_id={self.tenant_id}, stripe={self.stripe_invoice_id})>"
