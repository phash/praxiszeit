"""Vuln-3 (CVE-2026-48710 "BadHost"): Starlette <1.0.1 desyncs
``request.url.path`` from the routed path when the Host header is malformed.
The app branches on ``request.url.path`` (CSRF exemption, license enforcement,
SPA-vs-API routing) and ships no Host validation. Mitigation: a configurable
``ALLOWED_HOSTS`` allowlist wired via TrustedHostMiddleware so internet-facing
deployments can reject spoofed/malformed Host headers. Default ``*`` is a no-op
so existing on-prem/LAN-by-IP deployments and tests keep working."""
import pytest


def test_allowed_hosts_default_is_permissive(monkeypatch):
    from app.config import settings
    from app.main import _allowed_hosts
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", "*")
    assert _allowed_hosts() == ["*"]


def test_allowed_hosts_parses_and_trims_configured_list(monkeypatch):
    from app.config import settings
    from app.main import _allowed_hosts
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", " praxis.example.com , localhost ")
    assert _allowed_hosts() == ["praxis.example.com", "localhost"]


def test_app_wires_trusted_host_middleware():
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from app.main import app
    assert any(m.cls is TrustedHostMiddleware for m in app.user_middleware), \
        "TrustedHostMiddleware must be wired so ALLOWED_HOSTS can be enforced"


def test_trusted_host_rejects_disallowed_host_when_configured():
    """Mechanism check: with a real allowlist, a spoofed Host is rejected."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[Route("/", ok)],
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=["allowed.example"])],
    )
    c = TestClient(app)
    assert c.get("/", headers={"host": "allowed.example"}).status_code == 200
    assert c.get("/", headers={"host": "evil.example"}).status_code == 400
