"""Tests for #370: read-only Impersonation ("Login als …").

An admin can view the app as an employee (read-only). The impersonation access
token carries an ``imp`` claim (the real admin) so the acting party is never the
target; ``ImpersonationReadOnlyMiddleware`` blocks all writes; each session is
logged in ``impersonation_sessions``.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, ImpersonationSession
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


# ─── token claims ────────────────────────────────────────────────────


class TestImpersonationToken:
    def test_access_token_carries_imp_claims_when_passed(self):
        sid = str(uuid.uuid4())
        admin_id = str(uuid.uuid4())
        target_id = str(uuid.uuid4())
        token = auth_service.create_access_token(
            user_id=target_id, role="employee", tenant_id=str(DEFAULT_TENANT_ID),
            impersonator_id=admin_id, impersonation_session_id=sid,
        )
        payload = auth_service.decode_token(token)
        assert payload["sub"] == target_id
        assert payload["imp"] == admin_id
        assert payload["imp_sid"] == sid

    def test_access_token_has_no_imp_claims_by_default(self):
        token = auth_service.create_access_token(
            user_id=str(uuid.uuid4()), role="employee", tenant_id=str(DEFAULT_TENANT_ID),
        )
        payload = auth_service.decode_token(token)
        assert "imp" not in payload
        assert "imp_sid" not in payload


# ─── helpers / fixtures ──────────────────────────────────────────────


def _mk_user(db, username, *, role=UserRole.EMPLOYEE, active=True, tenant_id=DEFAULT_TENANT_ID):
    u = User(
        username=username, email=f"{username}@x.de",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name=username, last_name="Test", role=role,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=active, tenant_id=tenant_id,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _client(db, user, *, admin=False):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    if admin:
        test_app.dependency_overrides[require_admin] = lambda: user
    return TestClient(test_app)


@pytest.fixture
def admin_client(db, test_admin):
    c = _client(db, test_admin, admin=True)
    yield c
    test_app.dependency_overrides.clear()


@pytest.fixture
def employee_client(db, test_user):
    # require_admin NOT overridden → the real gate enforces 403.
    c = _client(db, test_user, admin=False)
    yield c
    test_app.dependency_overrides.clear()


# ─── POST /api/admin/users/{id}/impersonate ──────────────────────────


class TestImpersonateEndpoint:
    def test_admin_impersonates_employee(self, admin_client, db, test_admin):
        emp = _mk_user(db, "imp_emp")
        r = admin_client.post(f"/api/admin/users/{emp.id}/impersonate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body
        payload = auth_service.decode_token(body["access_token"])
        assert payload["sub"] == str(emp.id)
        assert payload["imp"] == str(test_admin.id)
        assert "imp_sid" in payload
        # session row created, still open
        sess = db.query(ImpersonationSession).filter(
            ImpersonationSession.target_id == emp.id
        ).first()
        assert sess is not None
        assert sess.impersonator_id == test_admin.id
        assert sess.ended_at is None

    def test_employee_forbidden(self, employee_client, db):
        emp = _mk_user(db, "imp_emp2")
        r = employee_client.post(f"/api/admin/users/{emp.id}/impersonate")
        assert r.status_code == 403

    def test_cannot_impersonate_admin(self, admin_client, db):
        other_admin = _mk_user(db, "imp_admin2", role=UserRole.ADMIN)
        r = admin_client.post(f"/api/admin/users/{other_admin.id}/impersonate")
        assert r.status_code == 403

    def test_cannot_impersonate_self(self, admin_client, test_admin):
        r = admin_client.post(f"/api/admin/users/{test_admin.id}/impersonate")
        assert r.status_code == 400

    def test_cannot_impersonate_other_tenant(self, admin_client, db):
        other_tid = uuid.uuid4()
        foreign = _mk_user(db, "imp_foreign", tenant_id=other_tid)
        r = admin_client.post(f"/api/admin/users/{foreign.id}/impersonate")
        assert r.status_code == 404

    def test_cannot_impersonate_inactive(self, admin_client, db):
        emp = _mk_user(db, "imp_inactive", active=False)
        r = admin_client.post(f"/api/admin/users/{emp.id}/impersonate")
        assert r.status_code == 400

    def test_missing_user_404(self, admin_client):
        r = admin_client.post(f"/api/admin/users/{uuid.uuid4()}/impersonate")
        assert r.status_code == 404


# ─── GET /api/admin/impersonation-sessions (accountability review) ───


class TestListImpersonationSessions:
    def test_lists_sessions_with_names(self, admin_client, db, test_admin):
        emp = _mk_user(db, "list_emp")
        db.add(ImpersonationSession(
            tenant_id=DEFAULT_TENANT_ID, impersonator_id=test_admin.id, target_id=emp.id,
        ))
        db.commit()
        r = admin_client.get("/api/admin/impersonation-sessions")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) >= 1
        row = rows[0]
        assert "impersonator_name" in row and "target_name" in row
        assert "started_at" in row and "ended_at" in row

    def test_employee_forbidden(self, employee_client):
        # employees must not see the accountability log
        assert employee_client.get("/api/admin/impersonation-sessions").status_code == 403


# ─── ImpersonationReadOnlyMiddleware ─────────────────────────────────


def _mini_app_with_middleware():
    from fastapi import FastAPI
    from app.middleware.impersonation import ImpersonationReadOnlyMiddleware

    app = FastAPI()
    app.add_middleware(ImpersonationReadOnlyMiddleware)

    @app.get("/api/dashboard")
    def _read():
        return {"ok": True}

    @app.post("/api/time-entries")
    def _write():
        return {"ok": True}

    @app.post("/api/admin/impersonate/end")
    def _end():
        return {"ok": True}

    return app


def _imp_token():
    return auth_service.create_access_token(
        user_id=str(uuid.uuid4()), role="employee", tenant_id=str(DEFAULT_TENANT_ID),
        impersonator_id=str(uuid.uuid4()), impersonation_session_id=str(uuid.uuid4()),
    )


def _plain_token():
    return auth_service.create_access_token(
        user_id=str(uuid.uuid4()), role="employee", tenant_id=str(DEFAULT_TENANT_ID),
    )


class TestImpersonationReadOnlyMiddleware:
    def _hdr(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_impersonation_blocks_writes(self):
        client = TestClient(_mini_app_with_middleware())
        r = client.post("/api/time-entries", headers=self._hdr(_imp_token()))
        assert r.status_code == 403

    def test_impersonation_allows_reads(self):
        client = TestClient(_mini_app_with_middleware())
        r = client.get("/api/dashboard", headers=self._hdr(_imp_token()))
        assert r.status_code == 200

    def test_impersonation_allows_end_endpoint(self):
        client = TestClient(_mini_app_with_middleware())
        r = client.post("/api/admin/impersonate/end", headers=self._hdr(_imp_token()))
        assert r.status_code == 200

    def test_plain_token_writes_pass(self):
        client = TestClient(_mini_app_with_middleware())
        r = client.post("/api/time-entries", headers=self._hdr(_plain_token()))
        assert r.status_code == 200

    def test_no_token_passes_through(self):
        # unauthenticated writes are the auth layer's problem, not ours
        client = TestClient(_mini_app_with_middleware())
        r = client.post("/api/time-entries")
        assert r.status_code == 200


# ─── POST /api/admin/impersonate/end (real token → get_current_user) ──


def _as_user_client(db, user):
    """Client where get_current_user resolves to ``user`` (override). The end
    endpoint reads imp_sid from the Authorization header token, so we still pass a
    real impersonation token — get_current_user's SET-LOCAL RLS path can't run on
    SQLite, hence the override."""
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(test_app)


class TestEndImpersonation:
    def _imp_token_for(self, target, admin, session_id):
        return auth_service.create_access_token(
            user_id=str(target.id), role=target.role.value, token_version=target.token_version,
            tenant_id=str(DEFAULT_TENANT_ID),
            impersonator_id=str(admin.id), impersonation_session_id=str(session_id),
        )

    def test_end_closes_session(self, db, test_admin):
        target = _mk_user(db, "end_emp")
        session = ImpersonationSession(
            tenant_id=DEFAULT_TENANT_ID, impersonator_id=test_admin.id, target_id=target.id,
        )
        db.add(session); db.commit(); db.refresh(session)
        token = self._imp_token_for(target, test_admin, session.id)
        client = _as_user_client(db, target)
        try:
            r = client.post("/api/admin/impersonate/end", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, r.text
            db.refresh(session)
            assert session.ended_at is not None
        finally:
            test_app.dependency_overrides.clear()

    def test_end_is_idempotent(self, db, test_admin):
        target = _mk_user(db, "end_emp2")
        session = ImpersonationSession(
            tenant_id=DEFAULT_TENANT_ID, impersonator_id=test_admin.id, target_id=target.id,
        )
        db.add(session); db.commit(); db.refresh(session)
        token = self._imp_token_for(target, test_admin, session.id)
        client = _as_user_client(db, target)
        try:
            first = client.post("/api/admin/impersonate/end", headers={"Authorization": f"Bearer {token}"})
            second = client.post("/api/admin/impersonate/end", headers={"Authorization": f"Bearer {token}"})
            assert first.status_code == 200
            assert second.status_code == 200
        finally:
            test_app.dependency_overrides.clear()

    def test_end_without_impersonation_claim_400(self, db, test_user):
        # a plain (non-impersonation) token has no imp_sid → nothing to end
        token = auth_service.create_access_token(
            user_id=str(test_user.id), role=test_user.role.value, token_version=test_user.token_version,
            tenant_id=str(DEFAULT_TENANT_ID),
        )
        client = _as_user_client(db, test_user)
        try:
            r = client.post("/api/admin/impersonate/end", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 400
        finally:
            test_app.dependency_overrides.clear()


# ─── impersonator validation (unit) ──────────────────────────────────


class TestValidateImpersonator:
    # Security-Audit 2026-07-25 (F2): validate_impersonator prüft zusätzlich die
    # token_version des Admins (``imp_tv``-Claim) — die Aufrufe geben sie mit.
    # Die Fälle "stale/fehlende imp_tv" liegen in
    # tests/test_security_audit_2026_07_25.py.
    def test_valid_admin_same_tenant_ok(self, db, test_admin):
        from app.middleware.auth import validate_impersonator
        # no exception
        validate_impersonator(test_admin, test_admin.tenant_id, test_admin.token_version or 0)

    def test_none_rejected(self):
        from app.middleware.auth import validate_impersonator
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_impersonator(None, DEFAULT_TENANT_ID, 0)
        assert exc.value.status_code == 401

    def test_employee_rejected(self, db, test_user):
        from app.middleware.auth import validate_impersonator
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_impersonator(test_user, test_user.tenant_id, test_user.token_version or 0)

    def test_inactive_admin_rejected(self, db):
        from app.middleware.auth import validate_impersonator
        from fastapi import HTTPException
        inactive_admin = _mk_user(db, "inactive_admin", role=UserRole.ADMIN, active=False)
        with pytest.raises(HTTPException):
            validate_impersonator(inactive_admin, DEFAULT_TENANT_ID, inactive_admin.token_version or 0)

    def test_wrong_tenant_rejected(self, db, test_admin):
        from app.middleware.auth import validate_impersonator
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_impersonator(test_admin, uuid.uuid4(), test_admin.token_version or 0)


# ─── session revocation on end (unit) ────────────────────────────────


class TestAssertSessionActive:
    def test_open_session_ok(self, db, test_admin):
        from app.middleware.auth import assert_impersonation_session_active
        target = _mk_user(db, "rev_ok")
        s = ImpersonationSession(tenant_id=DEFAULT_TENANT_ID, impersonator_id=test_admin.id, target_id=target.id)
        db.add(s); db.commit(); db.refresh(s)
        assert_impersonation_session_active(s)  # no raise

    def test_ended_session_rejected(self, db, test_admin):
        from app.middleware.auth import assert_impersonation_session_active
        from fastapi import HTTPException
        target = _mk_user(db, "rev_ended")
        s = ImpersonationSession(
            tenant_id=DEFAULT_TENANT_ID, impersonator_id=test_admin.id, target_id=target.id,
        )
        db.add(s); db.commit(); db.refresh(s)
        s.ended_at = __import__("app.services.timezone_service", fromlist=["now_local"]).now_local()
        db.commit()
        with pytest.raises(HTTPException) as exc:
            assert_impersonation_session_active(s)
        assert exc.value.status_code == 401

    def test_missing_session_rejected(self):
        from app.middleware.auth import assert_impersonation_session_active
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            assert_impersonation_session_active(None)
        assert exc.value.status_code == 401
