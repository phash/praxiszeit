"""Code-Review 2026-11-11, Slice auth (auth-01/05/11/15/16/20)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
import pyotp
import pytest

from app.config import settings
from app.routers import auth as auth_router
from app.services import auth_service
from tests.test_audit_1107_s1_auth import _client_as, _enable_totp, USER_PW
from tests.test_child_sick import admin, admin_client, default_tenant, SETTINGS  # noqa: F401
from tests.conftest import db, test_user, default_tenant as _dt  # noqa: F401


def test_totp_disable_reissues_session(db, test_user):
    """auth-01: Versionssprung ohne neues Token beendete die eigene Sitzung."""
    secret = _enable_totp(db, test_user)
    c = _client_as(db, test_user)
    before = test_user.token_version or 0
    with patch.object(auth_router.limiter, "enabled", False):
        r = c.request("DELETE", "/api/auth/totp/disable",
                      json={"password": USER_PW, "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totp_enabled"] is False
    token = body["access_token"]
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    db.refresh(test_user)
    assert test_user.token_version == before + 1
    assert payload["tv"] == test_user.token_version
    assert "refresh_token" in r.headers.get("set-cookie", "") or r.cookies


def test_holiday_state_failure_message_does_not_claim_saved_nor_leak(admin_client, db):
    """auth-05"""
    with patch("app.services.holiday_service.resync_state",
               side_effect=RuntimeError("SELECT secret FROM x")):
        r = admin_client.put(f"{SETTINGS}/holiday_state", json={"value": "Sachsen"})
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert "SELECT" not in detail
    assert "gespeichert, aber" not in detail
    assert "nichts gespeichert" in detail


@pytest.mark.parametrize("raw,stored", [(" 15", "15"), ("+15", "15"), ("015", "15")])
def test_child_sick_default_is_normalised(admin_client, raw, stored):
    """auth-16"""
    r = admin_client.put(f"{SETTINGS}/child_sick_days_default", json={"value": raw})
    assert r.status_code == 200, r.text
    assert r.json()["value"] == stored


@pytest.mark.parametrize("raw", ["", "abc", "-1", "367"])
def test_child_sick_default_rejects_with_german_text(admin_client, raw):
    r = admin_client.put(f"{SETTINGS}/child_sick_days_default", json={"value": raw})
    assert r.status_code == 400
    assert "child_sick_days_default" not in r.json()["detail"]


def test_profile_name_blank_is_rejected(db, test_user):
    """auth-15"""
    c = _client_as(db, test_user)
    r = c.put("/api/auth/profile", json={"first_name": "   "})
    assert r.status_code == 422


def test_capture_middleware_survives_failing_error_log(monkeypatch):
    """auth-11: ein ausgefallenes error_log darf die fertige 503 nicht verdrängen."""
    import app.main as main
    from app.services import error_log_service as els
    monkeypatch.setattr(main, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(els, "log_error", MagicMock(side_effect=RuntimeError("db down")))
    request = SimpleNamespace(url=SimpleNamespace(path="/api/health"), method="GET",
                              state=SimpleNamespace(), headers={})
    resp = SimpleNamespace(status_code=503)

    async def _ok(_req):
        return resp

    assert asyncio.run(main.capture_errors_middleware(request, _ok)) is resp

    async def _boom(_req):
        raise ValueError("orig")

    with pytest.raises(ValueError, match="orig"):
        asyncio.run(main.capture_errors_middleware(request, _boom))
