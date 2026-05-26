"""
Tenant-isolation tests for the error_logs admin endpoints (Issue #127).

In SaaS mode each tenant-admin must only see error log entries that belong
to their own tenant. In onprem mode behaviour is unchanged — admins see
the entire (single-tenant) aggregate.

These tests follow the belt-and-suspenders pattern from test_cross_tenant_api.py:
RLS itself is exercised by test_tenant_rls.py against Postgres; here we
verify the application-layer ``tenant_id`` filter that sits on top of it,
running on the SQLite test engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import ErrorLog, User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app


TENANT_A_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-00000000a127")
TENANT_B_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000b127")


# ─── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
def _db_session():
    """Fresh SQLite session per test."""
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


@pytest.fixture(scope="function")
def two_tenants(_db_session):
    """Create two isolated tenants."""
    for tid, name in [(TENANT_A_ID, "Tenant A"), (TENANT_B_ID, "Tenant B")]:
        _db_session.add(
            Tenant(id=tid, name=name, slug=f"t-{tid.hex[:8]}", is_active=True, mode="multi")
        )
    _db_session.commit()
    return TENANT_A_ID, TENANT_B_ID


def _make_admin(db, tenant_id, username):
    u = User(
        username=username,
        email=f"{username}@test.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Admin",
        last_name="Test",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture(scope="function")
def admin_a(_db_session, two_tenants):
    return _make_admin(_db_session, TENANT_A_ID, "admin_a_127")


@pytest.fixture(scope="function")
def admin_b(_db_session, two_tenants):
    return _make_admin(_db_session, TENANT_B_ID, "admin_b_127")


def _make_error(db, tenant_id, message: str, status: str = "open"):
    """Insert a deterministic ErrorLog row for the given tenant."""
    now = datetime.now(timezone.utc)
    entry = ErrorLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        level="error",
        logger="tests.tenant_isolation",
        message=message,
        fingerprint=uuid.uuid4().hex + uuid.uuid4().hex,  # 64 hex chars
        count=1,
        first_seen=now,
        last_seen=now,
        status=status,
    )
    db.add(entry)
    db.commit()
    return entry


@pytest.fixture(scope="function")
def errors_two_tenants(_db_session, two_tenants):
    """Seed two errors per tenant — 4 rows total."""
    return {
        TENANT_A_ID: [
            _make_error(_db_session, TENANT_A_ID, "A-err-1", status="open"),
            _make_error(_db_session, TENANT_A_ID, "A-err-2", status="resolved"),
        ],
        TENANT_B_ID: [
            _make_error(_db_session, TENANT_B_ID, "B-err-1", status="open"),
            _make_error(_db_session, TENANT_B_ID, "B-err-2", status="ignored"),
        ],
    }


def _client_as(user):
    """Build a TestClient authenticated as ``user`` against the shared session."""

    def _override_db():
        # The session is injected by the test via _db_session fixture; we
        # cannot capture it here, so callers wire dependency_overrides[get_db]
        # themselves. This helper only overrides the auth deps.
        raise RuntimeError("use _make_client(db, user) instead")  # pragma: no cover


def _make_client(db_session, user):
    """Authenticated TestClient pinned to ``db_session`` as ``user``."""

    def _override_db():
        yield db_session

    def _current():
        return user

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _current
    test_app.dependency_overrides[require_admin] = _current
    return TestClient(test_app)


@pytest.fixture(scope="function")
def saas_client_admin_a(_db_session, admin_a, monkeypatch):
    """SaaS-mode client authenticated as Tenant A admin."""
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "saas")
    with _make_client(_db_session, admin_a) as client:
        yield client
    test_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def saas_client_admin_b(_db_session, admin_b, monkeypatch):
    """SaaS-mode client authenticated as Tenant B admin."""
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "saas")
    with _make_client(_db_session, admin_b) as client:
        yield client
    test_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def onprem_client_admin_a(_db_session, admin_a, monkeypatch):
    """Onprem-mode client authenticated as the Tenant A admin (legacy behaviour)."""
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "onprem")
    with _make_client(_db_session, admin_a) as client:
        yield client
    test_app.dependency_overrides.clear()


# ─── SaaS mode: cross-tenant isolation ──────────────────────────────────


def test_saas_list_returns_only_own_tenant_errors(
    saas_client_admin_a, errors_two_tenants
):
    """In SaaS mode the list endpoint must hide foreign tenants' errors (Issue #127)."""
    resp = saas_client_admin_a.get("/api/admin/errors/")
    assert resp.status_code == 200, resp.text

    messages = {e["message"] for e in resp.json()}
    assert messages == {"A-err-1", "A-err-2"}
    assert "B-err-1" not in messages
    assert "B-err-2" not in messages


def test_saas_summary_counts_only_own_tenant(
    saas_client_admin_a, errors_two_tenants
):
    """Summary counts must reference only the caller's tenant in SaaS mode."""
    resp = saas_client_admin_a.get("/api/admin/errors/summary")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    # Tenant A seed: 1 open + 1 resolved → no "ignored" key
    assert body.get("open") == 1
    assert body.get("resolved") == 1
    assert "ignored" not in body  # belongs to Tenant B


def test_saas_other_tenant_admin_sees_own_subset(
    saas_client_admin_b, errors_two_tenants
):
    """The Tenant B admin sees only Tenant B errors — symmetric to test above."""
    resp = saas_client_admin_b.get("/api/admin/errors/")
    assert resp.status_code == 200, resp.text

    messages = {e["message"] for e in resp.json()}
    assert messages == {"B-err-1", "B-err-2"}

    summary = saas_client_admin_b.get("/api/admin/errors/summary").json()
    assert summary.get("open") == 1
    assert summary.get("ignored") == 1
    assert "resolved" not in summary  # belongs to Tenant A


def test_saas_list_with_status_filter_still_scoped(
    saas_client_admin_a, errors_two_tenants
):
    """``?status=open`` combined with tenant filter must intersect both."""
    resp = saas_client_admin_a.get("/api/admin/errors/?status=open")
    assert resp.status_code == 200, resp.text

    items = resp.json()
    assert len(items) == 1
    assert items[0]["message"] == "A-err-1"
    assert items[0]["status"] == "open"


# ─── On-prem mode: legacy unscoped behaviour ────────────────────────────


def test_onprem_list_returns_all_tenants(
    onprem_client_admin_a, errors_two_tenants
):
    """In onprem mode the admin sees the full aggregate (single-tenant install)."""
    resp = onprem_client_admin_a.get("/api/admin/errors/")
    assert resp.status_code == 200, resp.text

    messages = {e["message"] for e in resp.json()}
    assert messages == {"A-err-1", "A-err-2", "B-err-1", "B-err-2"}


def test_onprem_summary_counts_all_tenants(
    onprem_client_admin_a, errors_two_tenants
):
    """Onprem summary keeps legacy unfiltered counts."""
    resp = onprem_client_admin_a.get("/api/admin/errors/summary")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body.get("open") == 2  # A-err-1 + B-err-1
    assert body.get("resolved") == 1  # A-err-2
    assert body.get("ignored") == 1  # B-err-2


# ─── Service-level smoke tests ──────────────────────────────────────────


def test_service_get_errors_filters_when_tenant_id_set(
    _db_session, errors_two_tenants
):
    """Direct service call with ``tenant_id=`` returns only matching rows."""
    from app.services import error_log_service

    rows = error_log_service.get_errors(_db_session, tenant_id=TENANT_A_ID)
    assert {r.message for r in rows} == {"A-err-1", "A-err-2"}


def test_service_get_error_summary_filters_when_tenant_id_set(
    _db_session, errors_two_tenants
):
    from app.services import error_log_service as svc

    body_a = svc.get_error_summary(_db_session, tenant_id=TENANT_A_ID)
    assert body_a == {"open": 1, "resolved": 1}

    body_b = svc.get_error_summary(_db_session, tenant_id=TENANT_B_ID)
    assert body_b == {"open": 1, "ignored": 1}


def test_service_get_errors_no_tenant_returns_all(
    _db_session, errors_two_tenants
):
    """Onprem path: ``tenant_id=None`` must return the unfiltered aggregate."""
    from app.services import error_log_service

    rows = error_log_service.get_errors(_db_session, tenant_id=None)
    assert {r.message for r in rows} == {
        "A-err-1",
        "A-err-2",
        "B-err-1",
        "B-err-2",
    }


# ─── H1 regression: capture-path attribution + NULL-tenant visibility ────


def test_service_log_error_persists_tenant_id(_db_session, two_tenants):
    """``log_error(tenant_id=...)`` must write the tenant onto the row.

    Regression guard for the H1 issue where capture paths dropped the
    tenant_id, causing all freshly-captured rows to be NULL and thus filtered
    out by the SaaS GET filter in PR #127.
    """
    from app.services import error_log_service

    entry = error_log_service.log_error(
        _db_session,
        level="error",
        logger_name="tests.h1",
        message="explicit tenant write",
        path="/api/foo",
        method="GET",
        status_code=500,
        tenant_id=TENANT_A_ID,
    )
    assert entry.tenant_id == TENANT_A_ID

    refetched = (
        _db_session.query(ErrorLog).filter(ErrorLog.id == entry.id).first()
    )
    assert refetched is not None
    assert refetched.tenant_id == TENANT_A_ID


def test_service_log_error_without_tenant_leaves_null(_db_session, two_tenants):
    """``log_error`` without tenant_id (DBErrorHandler / infra) stays NULL."""
    from app.services import error_log_service

    entry = error_log_service.log_error(
        _db_session,
        level="critical",
        logger_name="tests.h1.infra",
        message="db connection blew up",
    )
    assert entry.tenant_id is None


def test_saas_admin_sees_null_tenant_infra_errors(
    _db_session, saas_client_admin_a, errors_two_tenants
):
    """SaaS tenant-admins must also see NULL-tenant infrastructure errors.

    Design call (see ``_scope_to_tenant`` docstring): hiding NULL rows would
    silently swallow DB-connection failures, startup issues, and any error
    captured before ``get_current_user`` populated ``request.state.tenant_id``.
    """
    # Seed an infrastructure error with tenant_id=NULL (DBErrorHandler path).
    _make_error(_db_session, None, "INFRA-null-1", status="open")

    resp = saas_client_admin_a.get("/api/admin/errors/")
    assert resp.status_code == 200, resp.text

    messages = {e["message"] for e in resp.json()}
    # Own tenant rows + NULL-tenant infra row, no Tenant B leakage.
    assert "A-err-1" in messages
    assert "A-err-2" in messages
    assert "INFRA-null-1" in messages
    assert "B-err-1" not in messages
    assert "B-err-2" not in messages


def test_saas_summary_includes_null_tenant_infra(
    _db_session, saas_client_admin_a, errors_two_tenants
):
    """Summary counts include NULL-tenant infra errors for the SaaS admin."""
    _make_error(_db_session, None, "INFRA-null-2", status="open")

    resp = saas_client_admin_a.get("/api/admin/errors/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Tenant A seed: open=1, resolved=1; +1 NULL open → open=2, resolved=1.
    assert body.get("open") == 2
    assert body.get("resolved") == 1
    assert "ignored" not in body  # belongs to Tenant B


def test_saas_admin_b_does_not_see_tenant_a_via_null_loophole(
    _db_session, saas_client_admin_b, errors_two_tenants
):
    """Sanity: the NULL-tenant exception must not leak Tenant A rows."""
    _make_error(_db_session, None, "INFRA-null-3", status="open")

    resp = saas_client_admin_b.get("/api/admin/errors/")
    assert resp.status_code == 200, resp.text
    messages = {e["message"] for e in resp.json()}
    assert messages == {"B-err-1", "B-err-2", "INFRA-null-3"}


# ─── Capture-middleware end-to-end attribution ──────────────────────────


def test_capture_middleware_attributes_tenant_from_request_state(
    _db_session, admin_a, monkeypatch
):
    """A 5xx captured by ``capture_errors_middleware`` must carry the caller's tenant_id.

    We can't easily exercise the real middleware in the SQLite test app
    (the test_app overrides auth via dependency_overrides and never invokes
    the production auth dep that writes ``request.state.tenant_id``), so we
    drive the helper directly with a synthetic request to lock the contract.
    """
    from types import SimpleNamespace
    from app.main import _tenant_from_request

    fake_req = SimpleNamespace(
        state=SimpleNamespace(tenant_id=str(TENANT_A_ID)),
        headers={},
    )
    assert _tenant_from_request(fake_req) == str(TENANT_A_ID)

    # Falls back to None when neither state nor bearer token are present.
    fake_anon = SimpleNamespace(state=SimpleNamespace(), headers={})
    assert _tenant_from_request(fake_anon) is None


def test_capture_middleware_falls_back_to_jwt_when_state_unset(
    _db_session, admin_a, monkeypatch
):
    """When ``request.state.tenant_id`` is unset, decode the bearer JWT."""
    from types import SimpleNamespace
    from app.main import _tenant_from_request
    from app.services import auth_service

    token = auth_service.create_access_token(
        user_id=str(admin_a.id),
        role=admin_a.role.value,
        token_version=admin_a.token_version,
        tenant_id=str(TENANT_A_ID),
    )
    fake_req = SimpleNamespace(
        state=SimpleNamespace(),
        headers={"authorization": f"Bearer {token}"},
    )
    assert _tenant_from_request(fake_req) == str(TENANT_A_ID)
