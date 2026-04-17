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
