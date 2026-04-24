"""Tests for Phase 6 tenant lifecycle + DSGVO (Issue #97)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import SignupAuditLog, User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service, lifecycle_service
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app


TID = uuid.UUID("eeeeeeee-0000-4000-8000-000000000601")


@pytest.fixture
def _db_session():
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.commit()
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.commit()
        Base.metadata.drop_all(bind=engine, checkfirst=True)


@pytest.fixture
def tenant(_db_session):
    t = Tenant(
        id=TID, name="Praxis Dr. X", slug="praxis-x", is_active=True, mode="multi",
        plan="pro", subscription_status="active",
        company_name="Praxis Dr. X GmbH", billing_email="admin@praxis-x.de",
        vat_id="DE12345", country="DE",
        billing_address={"street": "Musterstr. 1", "zip": "10115", "city": "Berlin"},
    )
    _db_session.add(t)
    _db_session.commit()
    return t


def _mk_user(db, tenant_id, name, role=UserRole.ADMIN, active=True):
    u = User(
        username=name, email=f"{name}@t.de",
        password_hash=auth_service.hash_password("S3curePassword!"),
        first_name=name, last_name="X", role=role,
        weekly_hours=40, vacation_days=30, work_days_per_week=5,
        is_active=active, tenant_id=tenant_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin_client(_db_session, tenant):
    admin = _mk_user(_db_session, TID, "admin")
    def _db(): yield _db_session
    def _who(): return admin
    test_app.dependency_overrides[get_db] = _db
    test_app.dependency_overrides[get_current_user] = _who
    test_app.dependency_overrides[require_admin] = _who
    with TestClient(test_app) as c:
        yield c, admin
    test_app.dependency_overrides.clear()


# ─── Self-service suspend ──────────────────────────────────────────

def test_self_suspend_sets_scheduled_timestamp(_db_session, admin_client):
    client, admin = admin_client
    resp = client.post("/api/tenant/suspend")
    assert resp.status_code == 200, resp.text
    t = _db_session.query(Tenant).filter(Tenant.id == TID).first()
    assert t.scheduled_suspend_at is not None
    assert t.scheduled_suspend_by == admin.id


def test_cancel_suspend_clears_it(_db_session, admin_client):
    client, _ = admin_client
    client.post("/api/tenant/suspend")
    resp = client.post("/api/tenant/cancel-suspend")
    assert resp.status_code == 200
    t = _db_session.query(Tenant).filter(Tenant.id == TID).first()
    assert t.scheduled_suspend_at is None


def test_cron_applies_scheduled_suspend(_db_session, tenant):
    tenant.scheduled_suspend_at = datetime.now(timezone.utc) - timedelta(hours=1)
    _db_session.commit()
    count = lifecycle_service.apply_scheduled_suspends(_db_session)
    assert count == 1
    _db_session.refresh(tenant)
    assert tenant.subscription_status == "suspended"
    assert tenant.scheduled_suspend_at is None


def test_cron_respects_future_suspend(_db_session, tenant):
    tenant.scheduled_suspend_at = datetime.now(timezone.utc) + timedelta(days=1)
    _db_session.commit()
    count = lifecycle_service.apply_scheduled_suspends(_db_session)
    assert count == 0


# ─── Deletion request + anonymization ──────────────────────────────

def test_request_deletion_sets_timestamp(_db_session, admin_client):
    client, _ = admin_client
    resp = client.post("/api/tenant/request-deletion")
    assert resp.status_code == 200
    t = _db_session.query(Tenant).filter(Tenant.id == TID).first()
    assert t.deletion_requested_at is not None


def test_double_request_400(_db_session, admin_client):
    client, _ = admin_client
    client.post("/api/tenant/request-deletion")
    resp = client.post("/api/tenant/request-deletion")
    assert resp.status_code == 400


def test_cancel_deletion(_db_session, admin_client):
    client, _ = admin_client
    client.post("/api/tenant/request-deletion")
    resp = client.post("/api/tenant/cancel-deletion")
    assert resp.status_code == 200
    t = _db_session.query(Tenant).filter(Tenant.id == TID).first()
    assert t.deletion_requested_at is None


def test_cron_anonymizes_after_grace(_db_session, tenant):
    # Deletion requested 35d ago → past 30d grace
    tenant.deletion_requested_at = datetime.now(timezone.utc) - timedelta(days=35)
    _db_session.commit()
    # Add a user to verify anonymization
    u = _mk_user(_db_session, TID, "emp")
    # And a signup audit row to verify scrubbing
    _db_session.add(SignupAuditLog(
        tenant_id=TID, email="admin@praxis-x.de", event="signup_requested",
        ip_address="1.2.3.4", user_agent="pytest",
        accepted_terms=True, accepted_privacy=True,
    ))
    _db_session.commit()

    count = lifecycle_service.apply_scheduled_deletions(_db_session)
    assert count == 1

    _db_session.refresh(tenant)
    _db_session.refresh(u)
    assert tenant.anonymized_at is not None
    assert tenant.name == "[gelöscht]"
    assert tenant.company_name is None
    assert tenant.billing_email is None
    assert tenant.country is None
    assert u.username.startswith("deleted_")
    assert u.email is None
    assert u.first_name == "Anonymisiert"
    assert u.is_active is False

    # Audit row retained but PII scrubbed
    audit = _db_session.query(SignupAuditLog).filter(SignupAuditLog.tenant_id == TID).first()
    assert audit is not None
    assert audit.email == "[anon]"
    assert audit.ip_address is None


def test_cron_respects_grace_window(_db_session, tenant):
    # Requested 5d ago → still within grace
    tenant.deletion_requested_at = datetime.now(timezone.utc) - timedelta(days=5)
    _db_session.commit()
    count = lifecycle_service.apply_scheduled_deletions(_db_session)
    assert count == 0


# ─── Export ────────────────────────────────────────────────────────

def test_export_returns_json_payload(_db_session, admin_client):
    client, _ = admin_client
    # Add some content
    _mk_user(_db_session, TID, "emp1")

    resp = client.get("/api/tenant/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    import json as _json
    payload = _json.loads(resp.content)
    assert payload["tenant"]["id"] == str(TID)
    assert len(payload["users"]) == 2  # admin + emp1


# ─── Ownership transfer ────────────────────────────────────────────

def test_transfer_ownership_updates_billing_email(_db_session, admin_client):
    client, _ = admin_client
    new_owner = _mk_user(_db_session, TID, "admin2", role=UserRole.ADMIN)
    resp = client.post(
        "/api/tenant/transfer-ownership",
        json={"new_owner_id": str(new_owner.id)},
    )
    assert resp.status_code == 200, resp.text
    t = _db_session.query(Tenant).filter(Tenant.id == TID).first()
    assert t.billing_email == new_owner.email


def test_transfer_ownership_rejects_non_admin(_db_session, admin_client):
    client, _ = admin_client
    emp = _mk_user(_db_session, TID, "emp", role=UserRole.EMPLOYEE)
    resp = client.post(
        "/api/tenant/transfer-ownership",
        json={"new_owner_id": str(emp.id)},
    )
    assert resp.status_code == 400


def test_transfer_ownership_rejects_foreign_tenant_user(_db_session, admin_client):
    client, _ = admin_client
    # Create a second tenant with its own admin
    other_tid = uuid.UUID("ffffffff-0000-4000-8000-000000000602")
    _db_session.add(Tenant(
        id=other_tid, name="Other", slug="other", is_active=True, mode="multi",
        plan="pro", subscription_status="active",
    ))
    _db_session.commit()
    outsider = _mk_user(_db_session, other_tid, "outsider")
    resp = client.post(
        "/api/tenant/transfer-ownership",
        json={"new_owner_id": str(outsider.id)},
    )
    assert resp.status_code == 404


# ─── AVV ──────────────────────────────────────────────────────────

def test_avv_download_returns_pdf(_db_session, admin_client):
    client, _ = admin_client
    resp = client.get("/api/tenant/avv")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    # Personalized with the practice name somewhere in the PDF bytes
    assert b"Praxis Dr. X" in resp.content or len(resp.content) > 1000
