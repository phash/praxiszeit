"""Audit A09 — structured application-log records for auth events.

OWASP A09 (Security Logging Failures): authentication events must leave a
forensic trail. These tests assert that the auth router emits greppable
``AUTH <event>`` records via Python ``logging`` (stdout → Docker logs /
journald → SIEM), covering:

- login_failed (wrong password / unknown user)
- login_success
- account_locked (lockout threshold)
- logout / token revocation
- password_changed

CRITICAL guarantee asserted here: NO password, JWT, refresh token, or TOTP
secret ever appears in a log record. The submitted username is logged (it is
the attacker-supplied identifier and useful for forensics); the email is not.

The test app reuses the proven login harness from ``test_endpoints.py``
(SQLite + ``set_superadmin_context`` patch). caplog captures the dedicated
``praxiszeit.security`` logger.
"""

import logging

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user

# Reuse the same lightweight test app + fixtures from test_endpoints.
# Import the app under a non-``test_`` alias so pytest does not try to collect
# it as a test object (it is a FastAPI instance).
from tests.test_endpoints import test_app as app  # noqa: F401
from tests.test_endpoints import (  # noqa: F401  (fixtures used by pytest)
    _db_session,
    tenant,
    employee_user,
)

SECURITY_LOGGER = "praxiszeit.security"

# A password used in the failure tests — must NEVER turn up in a log record.
SECRET_PASSWORD = "SuperSecret-DoNotLog-9999!"


def _login(client, username, password, totp_code=None):
    body = {"username": username, "password": password}
    if totp_code is not None:
        body["totp_code"] = totp_code
    return client.post("/api/auth/login", json=body)


@pytest.fixture(scope="function")
def login_client(_db_session):
    """TestClient for the real (unauthenticated) login endpoint.

    ``set_superadmin_context`` is patched out because SQLite has no SET LOCAL
    (mirrors TestAuthLogin in test_endpoints.py).
    """
    def _override_db():
        yield _db_session

    app.dependency_overrides[get_db] = _override_db
    with patch("app.routers.auth.set_superadmin_context"):
        with TestClient(app) as client:
            yield client
    app.dependency_overrides.clear()


def _no_credentials_leaked(caplog, *, password):
    """Assert no record text contains the password or token-ish material."""
    for rec in caplog.records:
        msg = rec.getMessage()
        assert password not in msg, f"password leaked into log: {msg!r}"
        # Crude JWT detector: three base64 segments joined by dots.
        assert "eyJ" not in msg, f"possible JWT leaked into log: {msg!r}"


class TestLoginFailedLogging:
    def test_wrong_password_emits_login_failed_warning(self, login_client, employee_user, caplog):
        with caplog.at_level(logging.WARNING, logger=SECURITY_LOGGER):
            resp = _login(login_client, "employee", SECRET_PASSWORD)

        assert resp.status_code == 401
        recs = [r for r in caplog.records if "AUTH login_failed" in r.getMessage()]
        assert recs, "expected an 'AUTH login_failed' record on wrong password"
        assert recs[0].levelno == logging.WARNING
        assert "employee" in recs[0].getMessage()
        _no_credentials_leaked(caplog, password=SECRET_PASSWORD)

    def test_unknown_user_emits_login_failed_warning(self, login_client, tenant, caplog):
        with caplog.at_level(logging.WARNING, logger=SECURITY_LOGGER):
            resp = _login(login_client, "ghost", SECRET_PASSWORD)

        assert resp.status_code == 401
        recs = [r for r in caplog.records if "AUTH login_failed" in r.getMessage()]
        assert recs, "expected an 'AUTH login_failed' record on unknown user"
        assert "ghost" in recs[0].getMessage()
        _no_credentials_leaked(caplog, password=SECRET_PASSWORD)


class TestLoginSuccessLogging:
    def test_valid_login_emits_login_success_info(self, login_client, employee_user, caplog):
        with caplog.at_level(logging.INFO, logger=SECURITY_LOGGER):
            resp = _login(login_client, "employee", "Employee2025!")

        assert resp.status_code == 200
        recs = [r for r in caplog.records if "AUTH login_success" in r.getMessage()]
        assert recs, "expected an 'AUTH login_success' record on valid login"
        assert recs[0].levelno == logging.INFO
        assert "employee" in recs[0].getMessage()
        # The issued access token must not be logged.
        _no_credentials_leaked(caplog, password="Employee2025!")


class TestAccountLockedLogging:
    def test_lockout_threshold_emits_account_locked_warning(self, login_client, employee_user, caplog):
        """After _LOCKOUT_ATTEMPTS failures within the window, the next attempt
        is locked out (429) and emits an 'AUTH account_locked' record."""
        from app.routers import auth as auth_router

        # Clean slate for the in-memory tracker.
        auth_router._failed_logins.clear()

        with caplog.at_level(logging.WARNING, logger=SECURITY_LOGGER):
            for _ in range(auth_router._LOCKOUT_ATTEMPTS):
                _login(login_client, "employee", SECRET_PASSWORD)
            # This attempt should trip the lockout (>= threshold).
            locked = _login(login_client, "employee", SECRET_PASSWORD)

        assert locked.status_code == 429
        recs = [r for r in caplog.records if "AUTH account_locked" in r.getMessage()]
        assert recs, "expected an 'AUTH account_locked' record once lockout trips"
        assert recs[0].levelno == logging.WARNING
        assert "employee" in recs[0].getMessage()
        _no_credentials_leaked(caplog, password=SECRET_PASSWORD)
        auth_router._failed_logins.clear()


class TestLogoutLogging:
    def test_logout_emits_logout_info(self, _db_session, employee_user, caplog):
        """Logout revokes tokens (token_version++). Authenticated via the
        get_current_user override (same pattern as employee_client)."""
        def _override_db():
            yield _db_session

        def _override_current_user():
            return employee_user

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_current_user
        try:
            with caplog.at_level(logging.INFO, logger=SECURITY_LOGGER):
                with TestClient(app) as client:
                    resp = client.post("/api/auth/logout")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        recs = [r for r in caplog.records if "AUTH logout" in r.getMessage()]
        assert recs, "expected an 'AUTH logout' record on logout"
        assert recs[0].levelno == logging.INFO
        assert "employee" in recs[0].getMessage()


class TestPasswordChangedLogging:
    def test_change_password_emits_password_changed_warning(self, _db_session, employee_user, caplog):
        def _override_db():
            yield _db_session

        def _override_current_user():
            return employee_user

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_current_user
        try:
            with caplog.at_level(logging.WARNING, logger=SECURITY_LOGGER):
                with TestClient(app) as client:
                    resp = client.post("/api/auth/change-password", json={
                        "current_password": "Employee2025!",
                        "new_password": SECRET_PASSWORD,
                    })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        recs = [r for r in caplog.records if "AUTH password_changed" in r.getMessage()]
        assert recs, "expected an 'AUTH password_changed' record"
        assert recs[0].levelno == logging.WARNING
        assert "employee" in recs[0].getMessage()
        # The new password must not appear in any record.
        _no_credentials_leaked(caplog, password=SECRET_PASSWORD)
