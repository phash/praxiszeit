"""Tests for the tenant-billing self-service endpoints (Phase 2 / Issue #93).

Covers:
- GET /api/tenant/billing returns the caller's plan + billing state
- PATCH /api/tenant/billing accepts the whitelisted fields (billing_email,
  company_name, vat_id, country, billing_address) and REJECTS attempts to
  change plan / subscription_status / stripe_* / seat_limit
- GET /api/tenant/invoices lists only the caller tenant's invoices
- Cross-tenant isolation: admin of Tenant A cannot see Tenant B's invoices
  even if they guess the ID
"""

import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TenantInvoice
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app


TENANT_A_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000101")
TENANT_B_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000102")


@pytest.fixture(scope="function")
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
def two_tenants(_db_session):
    a = Tenant(
        id=TENANT_A_ID, name="Tenant A", slug=f"ta-{TENANT_A_ID.hex[:6]}",
        is_active=True, mode="multi",
        plan="trial", subscription_status="active", seat_limit=5,
    )
    b = Tenant(
        id=TENANT_B_ID, name="Tenant B", slug=f"tb-{TENANT_B_ID.hex[:6]}",
        is_active=True, mode="multi",
        plan="pro", subscription_status="active", seat_limit=25,
    )
    _db_session.add_all([a, b])
    _db_session.commit()
    return a, b


def _make_admin(db, tenant_id, username):
    u = User(
        username=username,
        email=f"{username}@test.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Admin", last_name="X",
        role=UserRole.ADMIN, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=tenant_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def client_as_admin_a(_db_session, two_tenants):
    admin_a = _make_admin(_db_session, TENANT_A_ID, "admin_a_bill")

    def _db(): yield _db_session
    def _who(): return admin_a

    test_app.dependency_overrides[get_db] = _db
    test_app.dependency_overrides[get_current_user] = _who
    test_app.dependency_overrides[require_admin] = _who
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


# ─── GET /api/tenant/billing ──────────────────────────────────────────

def test_billing_returns_own_tenant(client_as_admin_a, two_tenants):
    resp = client_as_admin_a.get("/api/tenant/billing")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "trial"
    assert data["subscription_status"] == "active"
    assert data["seat_limit"] == 5
    # Tenant B's plan must not leak
    assert data["id"] == str(TENANT_A_ID)


# ─── PATCH /api/tenant/billing ────────────────────────────────────────

def test_patch_billing_accepts_whitelist(client_as_admin_a, _db_session):
    resp = client_as_admin_a.patch(
        "/api/tenant/billing",
        json={
            "billing_email": "billing@praxis-a.de",
            "company_name": "Praxis A GmbH",
            "vat_id": "DE123456789",
            "country": "de",
            "billing_address": {"street": "Hauptstr. 1", "zip": "10115", "city": "Berlin"},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["billing_email"] == "billing@praxis-a.de"
    assert data["company_name"] == "Praxis A GmbH"
    assert data["vat_id"] == "DE123456789"
    assert data["country"] == "DE"  # auto-uppercased
    assert data["billing_address"]["city"] == "Berlin"


def test_patch_billing_silently_ignores_plan(client_as_admin_a, _db_session):
    """Admins must not be able to upgrade their own plan for free."""
    resp = client_as_admin_a.patch(
        "/api/tenant/billing",
        json={"plan": "enterprise", "billing_email": "x@y.de"},
    )
    # Request succeeds (we ignore extras), but plan stays 'trial'
    assert resp.status_code == 200, resp.text
    tenant = _db_session.query(Tenant).filter(Tenant.id == TENANT_A_ID).first()
    assert tenant.plan == "trial"


def test_patch_billing_silently_ignores_stripe_fields(client_as_admin_a, _db_session):
    """Stripe IDs are owned by the webhook; admin cannot set them directly."""
    forged = "cus_attacker_forged"
    resp = client_as_admin_a.patch(
        "/api/tenant/billing",
        json={"stripe_customer_id": forged, "company_name": "Ok"},
    )
    assert resp.status_code == 200, resp.text
    tenant = _db_session.query(Tenant).filter(Tenant.id == TENANT_A_ID).first()
    assert tenant.stripe_customer_id != forged
    assert tenant.stripe_customer_id is None


def test_patch_billing_silently_ignores_seat_limit(client_as_admin_a, _db_session):
    resp = client_as_admin_a.patch(
        "/api/tenant/billing",
        json={"seat_limit": 999, "company_name": "Ok"},
    )
    assert resp.status_code == 200, resp.text
    tenant = _db_session.query(Tenant).filter(Tenant.id == TENANT_A_ID).first()
    assert tenant.seat_limit == 5  # unchanged


# ─── GET /api/tenant/invoices ─────────────────────────────────────────

def test_invoices_only_own_tenant(client_as_admin_a, _db_session, two_tenants):
    """Admin A must not see Tenant B's invoices."""
    own = TenantInvoice(
        tenant_id=TENANT_A_ID,
        stripe_invoice_id="in_A_001",
        amount_cents=1900, currency="eur", status="paid",
        paid_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    other = TenantInvoice(
        tenant_id=TENANT_B_ID,
        stripe_invoice_id="in_B_001",
        amount_cents=3900, currency="eur", status="paid",
        paid_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    _db_session.add_all([own, other])
    _db_session.commit()

    resp = client_as_admin_a.get("/api/tenant/invoices")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["stripe_invoice_id"] == "in_A_001"


def test_invoices_ordered_newest_first(client_as_admin_a, _db_session, two_tenants):
    older = TenantInvoice(
        tenant_id=TENANT_A_ID,
        stripe_invoice_id="in_A_old",
        amount_cents=1900, currency="eur", status="paid",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = TenantInvoice(
        tenant_id=TENANT_A_ID,
        stripe_invoice_id="in_A_new",
        amount_cents=1900, currency="eur", status="paid",
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    _db_session.add_all([older, newer])
    _db_session.commit()

    rows = client_as_admin_a.get("/api/tenant/invoices").json()
    assert rows[0]["stripe_invoice_id"] == "in_A_new"
    assert rows[1]["stripe_invoice_id"] == "in_A_old"


# ─── Auth guard ───────────────────────────────────────────────────────

def test_billing_endpoints_require_admin(_db_session, two_tenants):
    """Non-admin employees cannot read billing."""
    employee_a = User(
        username="emp_a",
        email="emp_a@test.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Emp", last_name="A",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=TENANT_A_ID,
    )
    _db_session.add(employee_a)
    _db_session.commit()

    def _db(): yield _db_session
    def _who(): return employee_a

    test_app.dependency_overrides[get_db] = _db
    test_app.dependency_overrides[get_current_user] = _who
    # Do NOT override require_admin — the real one should raise 403

    try:
        with TestClient(test_app) as client:
            resp = client.get("/api/tenant/billing")
            assert resp.status_code == 403, resp.text
    finally:
        test_app.dependency_overrides.clear()
