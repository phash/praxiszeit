"""Unit tests for TOTP replay protection (verify_totp_with_counter)."""

import time as time_mod

import pyotp
import pytest

from app.services import auth_service


@pytest.fixture
def secret():
    return pyotp.random_base32()


def test_accepts_valid_current_code(secret):
    code = pyotp.TOTP(secret).now()
    accepted = auth_service.verify_totp_with_counter(secret, code, last_counter=None)
    assert accepted is not None
    # Counter equals floor(now / 30) at the time of check
    assert accepted == int(time_mod.time()) // 30


def test_rejects_invalid_code(secret):
    assert auth_service.verify_totp_with_counter(secret, "000000", last_counter=None) is None


def test_rejects_replay_of_same_code(secret):
    code = pyotp.TOTP(secret).now()
    first = auth_service.verify_totp_with_counter(secret, code, last_counter=None)
    assert first is not None

    # Immediate replay with the last counter already stored must be rejected
    second = auth_service.verify_totp_with_counter(secret, code, last_counter=first)
    assert second is None


def test_rejects_replay_of_older_counter(secret):
    # Simulate: attacker snapshots code at t-30s, admin logs in at t (newer
    # counter accepted), attacker tries to replay the old code.
    totp = pyotp.TOTP(secret)
    now = int(time_mod.time())
    current_counter = now // 30

    # Produce a code from one window earlier
    earlier_code = totp.at(now - 30)
    # User already logged in successfully with a later counter
    result = auth_service.verify_totp_with_counter(
        secret, earlier_code, last_counter=current_counter
    )
    assert result is None


def test_accepts_next_window_code_after_previous_use(secret):
    # After user logs in with counter N, counter N+1 (next 30s code) should
    # work the moment clock advances — normal re-login flow.
    totp = pyotp.TOTP(secret)
    now = int(time_mod.time())
    current_counter = now // 30
    next_code = totp.at(now + 30)

    accepted = auth_service.verify_totp_with_counter(
        secret, next_code, last_counter=current_counter
    )
    assert accepted == current_counter + 1


# ─── Endpoint-level: activation code must not be replayable (M-SEC4) ─────────

import uuid as _uuid
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User, UserRole
from tests.conftest import engine, TestingSessionLocal, DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from app.database import Base as _Base


@pytest.fixture
def _totp_db():
    _Base.metadata.create_all(bind=engine)
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()
        _Base.metadata.drop_all(bind=engine)


@pytest.fixture
def _totp_user(_totp_db):
    from app.models.tenant import Tenant
    _totp_db.add(Tenant(id=DEFAULT_TENANT_ID, name="D", slug="d", is_active=True, mode="single"))
    u = User(
        id=_uuid.uuid4(), username="totpuser", email="totp@test.local",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="T", last_name="U", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
        totp_secret=pyotp.random_base32(), totp_enabled=False,
        last_totp_counter=None,
    )
    _totp_db.add(u)
    _totp_db.commit()
    _totp_db.refresh(u)
    return u


def test_totp_activation_persists_counter_and_blocks_replay(_totp_db, _totp_user):
    """M-SEC4: /totp/verify must consume the code (persist last_totp_counter)
    so the same code cannot later be replayed against /login."""
    def _override_db():
        yield _totp_db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: _totp_user
    try:
        code = pyotp.TOTP(_totp_user.totp_secret).now()
        with TestClient(test_app) as client:
            resp = client.post("/api/auth/totp/verify", json={"code": code})
        assert resp.status_code == 200, resp.text
        _totp_db.expire_all()
        refreshed = _totp_db.query(User).filter(User.id == _totp_user.id).first()
        assert refreshed.totp_enabled is True
        # The activation code's counter must now be persisted …
        assert refreshed.last_totp_counter is not None
        # … so replaying that exact code is rejected by the counter check.
        assert auth_service.verify_totp_with_counter(
            refreshed.totp_secret, code, refreshed.last_totp_counter
        ) is None
    finally:
        test_app.dependency_overrides.clear()


def test_verify_totp_with_invalid_base32_secret_returns_none():
    """Review 2026-06-23: ein nicht entschluesselbares Secret (SECRET_KEY rotiert ->
    decrypt_secret gibt den Fernet-Ciphertext zurueck, der KEIN gueltiges Base32 ist)
    liess pyotp.TOTP.at() ein binascii.Error werfen -> HTTP 500 auf dem Login.
    verify_totp_with_counter faengt das jetzt und lehnt sauber ab (None)."""
    # Fernet-Token-aehnlich: enthaelt Kleinbuchstaben/-/_/= -> kein Base32.
    assert auth_service.verify_totp_with_counter(
        "gAAAAAB_not-valid-base32_=", "123456", last_counter=None
    ) is None
    # Auch ein leerer/zu kurzer Secret-String darf nicht crashen.
    assert auth_service.verify_totp_with_counter("", "123456", last_counter=None) is None
