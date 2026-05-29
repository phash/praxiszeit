"""Phase 7 tests — per-tenant metrics, MRR calc, alerts, superadmin
tenant-overview endpoint."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_superadmin
from app.models import TimeEntry, User, UserRole
from app.models.tenant import Tenant
from app.services import alerting, auth_service
from app.services.metrics_refresh import compute_mrr_details, refresh_all
from app.services.tenant_metrics import (
    praxiszeit_active_tenants,
    praxiszeit_mrr_cents,
    praxiszeit_tenant_dau,
    praxiszeit_tenant_employees,
)
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app


TID_A = uuid.UUID("01020304-0000-4000-8000-000000000701")
TID_B = uuid.UUID("01020304-0000-4000-8000-000000000702")


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


def _seed_universe(db):
    # One starter tenant with 5 active seats, one pro with 10, one trial with 3
    starter = Tenant(
        id=TID_A, name="Starter AG", slug="starter", is_active=True, mode="multi",
        plan="starter", subscription_status="active",
    )
    pro = Tenant(
        id=TID_B, name="Pro GmbH", slug="pro", is_active=True, mode="multi",
        plan="pro", subscription_status="active",
    )
    db.add_all([starter, pro])
    db.commit()

    for i in range(5):
        db.add(User(
            username=f"s{i}", email=f"s{i}@a.de",
            password_hash=auth_service.hash_password("S3cure!Password"),
            first_name="S", last_name="X", role=UserRole.EMPLOYEE,
            weekly_hours=40, vacation_days=30, work_days_per_week=5,
            is_active=True, tenant_id=TID_A,
        ))
    for i in range(10):
        db.add(User(
            username=f"p{i}", email=f"p{i}@b.de",
            password_hash=auth_service.hash_password("S3cure!Password"),
            first_name="P", last_name="X", role=UserRole.EMPLOYEE,
            weekly_hours=40, vacation_days=30, work_days_per_week=5,
            is_active=True, tenant_id=TID_B,
        ))
    db.commit()
    return starter, pro


# ─── MRR calc ─────────────────────────────────────────────────────

def test_mrr_details_sums_active_plans(_db_session):
    _seed_universe(_db_session)
    out = compute_mrr_details(_db_session)
    # starter: 5 seats × €19/mo = €95 = 9500 cents
    # pro:    10 seats × €39/mo = €390 = 39000 cents
    assert out["by_plan"]["starter"] == 9500
    assert out["by_plan"]["pro"] == 39000
    assert out["mrr_cents"] == 9500 + 39000
    assert out["arr_cents"] == (9500 + 39000) * 12


def test_mrr_excludes_past_due_tenants(_db_session):
    starter, pro = _seed_universe(_db_session)
    pro.subscription_status = "past_due"
    _db_session.commit()
    out = compute_mrr_details(_db_session)
    assert out["by_plan"]["pro"] == 0
    assert out["mrr_cents"] == 9500


# ─── refresh_all sets gauges ─────────────────────────────────────

def test_refresh_all_updates_gauges(_db_session):
    _seed_universe(_db_session)
    summary = refresh_all(_db_session)
    assert summary["tenants"] == 2
    assert summary["active_tenants"] == 2
    assert praxiszeit_active_tenants._value.get() == 2
    # Per-tenant gauge — direct lookup
    assert praxiszeit_tenant_employees.labels(tenant_id=str(TID_A))._value.get() == 5
    assert praxiszeit_tenant_employees.labels(tenant_id=str(TID_B))._value.get() == 10


def test_dau_counts_recent_time_entries(_db_session):
    starter, _ = _seed_universe(_db_session)
    users = _db_session.query(User).filter(User.tenant_id == TID_A).all()
    today = date.today()
    # 2 distinct users logged time today → DAU=2 for starter
    for u in users[:2]:
        _db_session.add(TimeEntry(
            user_id=u.id, tenant_id=TID_A, date=today,
            start_time=time(9, 0), end_time=time(17, 0), break_minutes=30,
        ))
    _db_session.commit()
    refresh_all(_db_session)
    assert praxiszeit_tenant_dau.labels(tenant_id=str(TID_A))._value.get() == 2


# ─── Alerts ──────────────────────────────────────────────────────

def test_alert_logs_when_slack_unset(caplog, monkeypatch):
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", None)
    with caplog.at_level("INFO"):
        assert alerting.alert("hello") is True
    assert "alerting (no Slack" in caplog.text


def test_alert_posts_to_slack_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.example/x")
    mock_resp = type("R", (), {"status": 200, "__enter__": lambda s: s, "__exit__": lambda *a: None})()
    with patch("urllib.request.urlopen", return_value=mock_resp) as u:
        assert alerting.alert("hi") is True
    assert u.called


# ─── Superadmin tenant-overview endpoint ─────────────────────────

@pytest.fixture
def superadmin_client(_db_session):
    _seed_universe(_db_session)
    superadmin = User(
        id=uuid.uuid4(),
        username="sa", email="sa@x",
        password_hash=auth_service.hash_password("S3curePassword!"),
        first_name="Super", last_name="Admin",
        role=UserRole.ADMIN,  # role isn't the gate; tenant_id IS NULL is
        weekly_hours=40, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=None,
    )
    _db_session.add(superadmin)
    _db_session.commit()

    def _db(): yield _db_session
    def _who(): return superadmin
    test_app.dependency_overrides[get_db] = _db
    test_app.dependency_overrides[get_current_user] = _who
    test_app.dependency_overrides[require_superadmin] = _who
    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def test_tenants_overview_returns_paginated_list(superadmin_client):
    # SQLite has no SET LOCAL → patch the RLS context helper out for the call.
    with patch("app.routers.superadmin.set_superadmin_context"):
        resp = superadmin_client.get("/api/superadmin/tenants-overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    names = {t["name"] for t in data["tenants"]}
    assert names == {"Starter AG", "Pro GmbH"}
    pro = next(t for t in data["tenants"] if t["plan"] == "pro")
    assert pro["mrr_cents"] == 10 * 3900


def test_tenants_overview_filter_by_plan(superadmin_client):
    with patch("app.routers.superadmin.set_superadmin_context"):
        resp = superadmin_client.get("/api/superadmin/tenants-overview?status_filter=trial")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_superadmin_mrr_endpoint(superadmin_client):
    with patch("app.routers.superadmin.set_superadmin_context"):
        resp = superadmin_client.get("/api/superadmin/metrics/mrr")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mrr_cents"] == 9500 + 39000
    assert data["arr_cents"] == (9500 + 39000) * 12


def test_alert_new_signup_does_not_leak_email(monkeypatch):
    """M-DSG2: the signup Slack alert must not contain the admin's email —
    Slack is an undisclosed sub-processor, so no data-subject PII may leave
    the instance. Practice name (business data) is acceptable."""
    captured = {}

    def _capture(text, **kw):
        captured["text"] = text
        return True

    monkeypatch.setattr(alerting, "alert", _capture)
    alerting.alert_new_signup("Praxis Dr. Müller")
    assert "@" not in captured["text"]
    assert "Praxis Dr. Müller" in captured["text"]
