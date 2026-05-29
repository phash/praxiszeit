"""Tests for self-service signup (Phase 3, Issue #94).

Covers:
- POST /api/public/signup happy path (tenant + inactive admin + token)
- /verify-email activates admin and consumes token (idempotent-ish)
- Expired / reused / unknown tokens → 410
- Resend invalidates old tokens and issues a new one
- DEPLOYMENT_MODE=onprem → all /api/public/* endpoints 404
- DSGVO: audit log row per event with IP + UA + consent flags
- Email already in use → 409
- Trial cron suspends expired trials without Stripe subscription
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.database import Base, SessionLocal, get_db
from app.models import SignupAuditLog, SignupToken, User, UserRole
from app.models.tenant import Tenant
from app.services import signup_service
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app


# ----- Test harness -----------------------------------------------------

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
def saas_client(_db_session, monkeypatch):
    """Client with DEPLOYMENT_MODE=saas + public endpoints pointed at the
    in-memory SQLite session. We override the _public_db dependency to
    yield the test session instead of opening a real SessionLocal + RLS.
    """
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "saas")

    from app.routers.public_signup import _public_db

    def _db_override():
        yield _db_session

    test_app.dependency_overrides[_public_db] = _db_override
    test_app.dependency_overrides[get_db] = _db_override
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


@pytest.fixture
def onprem_client(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "onprem")
    with TestClient(test_app) as client:
        yield client


_PAYLOAD = {
    "practice_name": "Zahnarztpraxis Dr. Müller",
    "admin_email": "chef@praxis-mueller.de",
    "admin_first_name": "Anna",
    "admin_last_name": "Müller",
    "admin_password": "S3curePassword!",
    "accept_terms": True,
    "accept_privacy": True,
    "country": "de",
}


# ----- onprem gating ----------------------------------------------------

def test_signup_404_in_onprem(onprem_client):
    resp = onprem_client.post("/api/public/signup", json=_PAYLOAD)
    assert resp.status_code == 404


def test_verify_404_in_onprem(onprem_client):
    resp = onprem_client.get("/api/public/verify-email?token=anything")
    assert resp.status_code == 404


def test_resend_404_in_onprem(onprem_client):
    resp = onprem_client.post("/api/public/resend-verification", json={"email": "x@y.de"})
    assert resp.status_code == 404


# ----- signup happy path ------------------------------------------------

def test_signup_creates_tenant_and_inactive_admin(saas_client, _db_session):
    with patch("app.routers.public_signup.send_verification_email", return_value=True) as mail:
        resp = saas_client.post("/api/public/signup", json=_PAYLOAD)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "tenant_id" in body

    tenant = _db_session.query(Tenant).filter(Tenant.id == uuid.UUID(body["tenant_id"])).first()
    assert tenant is not None
    assert tenant.plan == "trial"
    assert tenant.subscription_status == "active"
    assert tenant.trial_ends_at is not None
    assert tenant.country == "DE"
    assert tenant.billing_email == _PAYLOAD["admin_email"]

    admin = _db_session.query(User).filter(User.email == _PAYLOAD["admin_email"]).first()
    assert admin is not None
    assert admin.is_active is False
    assert admin.role == UserRole.ADMIN

    # Mail attempted
    assert mail.called

    # Audit row present with consent flags
    audit = (
        _db_session.query(SignupAuditLog)
        .filter(SignupAuditLog.email == _PAYLOAD["admin_email"], SignupAuditLog.event == "signup_requested")
        .first()
    )
    assert audit is not None
    assert audit.accepted_terms is True
    assert audit.accepted_privacy is True


def test_signup_duplicate_email_is_enumeration_safe(saas_client, _db_session):
    """Review 2026-05-29 (M-API5): a duplicate email must NOT be distinguishable
    from a fresh signup. Previously the second attempt returned 409, leaking
    that the address has an account. Now both return an identical 201 + a
    shape-identical body, and no second tenant is created."""
    # First signup + manually activate
    with patch("app.routers.public_signup.send_verification_email", return_value=True):
        r1 = saas_client.post("/api/public/signup", json=_PAYLOAD)
    assert r1.status_code == 201
    u = _db_session.query(User).filter(User.email == _PAYLOAD["admin_email"]).first()
    u.is_active = True
    _db_session.commit()
    tenants_before = _db_session.query(Tenant).count()

    # Second signup with the SAME (now active) email: must look identical.
    with patch("app.routers.public_signup.send_verification_email", return_value=True):
        r2 = saas_client.post("/api/public/signup", json=_PAYLOAD)
    assert r2.status_code == 201, r2.text
    assert "tenant_id" in r2.json()
    # No NEW tenant must have been created for the duplicate.
    assert _db_session.query(Tenant).count() == tenants_before
    # And no second admin row for that email.
    admins = (
        _db_session.query(User)
        .filter(User.email == _PAYLOAD["admin_email"], User.role == UserRole.ADMIN)
        .count()
    )
    assert admins == 1


def test_signup_rejects_missing_consent(saas_client, _db_session):
    payload = dict(_PAYLOAD, accept_terms=False)
    resp = saas_client.post("/api/public/signup", json=payload)
    assert resp.status_code == 422


def test_signup_rejects_short_password(saas_client, _db_session):
    payload = dict(_PAYLOAD, admin_password="short")
    resp = saas_client.post("/api/public/signup", json=payload)
    assert resp.status_code == 422


# ----- verify flow ------------------------------------------------------

def _create_signup(db, **overrides):
    payload = dict(
        practice_name="Praxis A",
        admin_email="a@praxis-a.de",
        admin_first_name="A",
        admin_last_name="Alpha",
        admin_password="S3curePassword!",
        country="DE",
        ip_address="127.0.0.1",
        user_agent="pytest",
        accepted_terms=True,
        accepted_privacy=True,
    )
    payload.update(overrides)
    return signup_service.signup(db, **payload)


def test_verify_activates_admin(saas_client, _db_session):
    result = _create_signup(_db_session)
    resp = saas_client.get(f"/api/public/verify-email?token={result.verification_token}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant_id"] == str(result.tenant_id)

    u = _db_session.query(User).filter(User.id == result.user_id).first()
    assert u.is_active is True

    tok = _db_session.query(SignupToken).filter(SignupToken.user_id == result.user_id).first()
    assert tok.consumed_at is not None


def test_verify_rejects_reused_token(saas_client, _db_session):
    result = _create_signup(_db_session)
    saas_client.get(f"/api/public/verify-email?token={result.verification_token}")
    resp = saas_client.get(f"/api/public/verify-email?token={result.verification_token}")
    assert resp.status_code == 410


def test_verify_rejects_expired_token(saas_client, _db_session):
    result = _create_signup(_db_session, admin_email="expired@x.de")
    tok = _db_session.query(SignupToken).filter(SignupToken.user_id == result.user_id).first()
    tok.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    _db_session.commit()
    resp = saas_client.get(f"/api/public/verify-email?token={result.verification_token}")
    assert resp.status_code == 410


def test_verify_rejects_unknown_token(saas_client, _db_session):
    resp = saas_client.get("/api/public/verify-email?token=totally-bogus-token")
    assert resp.status_code == 410


# ----- resend -----------------------------------------------------------

def test_resend_issues_new_token_and_invalidates_old(saas_client, _db_session):
    result = _create_signup(_db_session, admin_email="resend@x.de")
    old_token = result.verification_token

    with patch("app.routers.public_signup.send_verification_email", return_value=True) as mail:
        resp = saas_client.post("/api/public/resend-verification", json={"email": "resend@x.de"})
    assert resp.status_code == 202
    assert mail.called

    # Old token must be consumed (inactive)
    resp2 = saas_client.get(f"/api/public/verify-email?token={old_token}")
    assert resp2.status_code == 410


def test_resend_returns_202_for_unknown_email(saas_client):
    """Must NOT reveal whether the email is known (enumeration protection)."""
    with patch("app.routers.public_signup.send_verification_email", return_value=True) as mail:
        resp = saas_client.post(
            "/api/public/resend-verification",
            json={"email": "never-registered@example.com"},
        )
    assert resp.status_code == 202
    assert not mail.called


# ----- trial suspension cron -------------------------------------------

def test_suspend_expired_trials(_db_session):
    # Active trial with stripe sub → keep
    t1 = Tenant(
        id=uuid.uuid4(), name="T1", slug="t1", is_active=True, mode="multi",
        plan="trial", subscription_status="active",
        trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
        stripe_subscription_id="sub_already_paying",
    )
    # Expired trial without Stripe → suspend
    t2 = Tenant(
        id=uuid.uuid4(), name="T2", slug="t2", is_active=True, mode="multi",
        plan="trial", subscription_status="active",
        trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    # Still within trial → keep
    t3 = Tenant(
        id=uuid.uuid4(), name="T3", slug="t3", is_active=True, mode="multi",
        plan="trial", subscription_status="active",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    _db_session.add_all([t1, t2, t3])
    _db_session.commit()

    count = signup_service.suspend_expired_trials(_db_session)
    assert count == 1

    _db_session.refresh(t1)
    _db_session.refresh(t2)
    _db_session.refresh(t3)
    assert t1.subscription_status == "active"
    assert t2.subscription_status == "suspended"
    assert t3.subscription_status == "active"
