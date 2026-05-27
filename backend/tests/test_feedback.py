"""Tests fuer In-App Bug-Reporting Proxy (#136).

Endpoint: POST /api/feedback/report  ->  pzweb POST /v1/bugs (multipart, httpx).
Der Outbound-Call wird gemockt (kein echter pzweb-Call in Tests). Verifiziert:
korrektes Multipart (license_id aus Lizenz, app_version/os ergaenzt, severity),
Status-Mapping (201/403/429/Netzwerkfehler) und der "keine Lizenz"-Fall.
"""

import platform
import types

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_test_app() -> FastAPI:
    from app.routers import feedback
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit Feedback Test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(feedback.router)
    return app


_app = _create_test_app()

_CUSTOMER_ID = "pz-00000000-0000-0000-0000-000000000001"
VALID = {"title": "Es hakt", "description": "Beim Stempeln passiert X", "severity": "high"}


class _FakeLicense:
    def __init__(self, customer_id=_CUSTOMER_ID):
        self.customer_id = customer_id


class _Recorder:
    """Records outbound httpx.post calls and returns a canned response (or raises)."""
    def __init__(self, response=None, exc=None):
        self.calls = []
        self._response = response
        self._exc = exc

    def __call__(self, url, *args, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        if self._exc is not None:
            raise self._exc
        return self._response


def _patch_post(monkeypatch, response=None, exc=None):
    from app.routers import feedback
    rec = _Recorder(response=response, exc=exc)
    monkeypatch.setattr(feedback.httpx, "post", rec)
    return rec


@pytest.fixture
def client():
    from app.middleware.auth import get_current_user
    _app.dependency_overrides[get_current_user] = lambda: types.SimpleNamespace(
        id="u", username="tester"
    )
    c = TestClient(_app)
    yield c
    _app.dependency_overrides.clear()


@pytest.fixture
def mock_license(monkeypatch):
    monkeypatch.setattr("app.core.license.get_current_license", lambda: _FakeLicense())


def test_happy_path_maps_201_to_200_and_sends_correct_multipart(client, mock_license, monkeypatch):
    rec = _patch_post(
        monkeypatch,
        response=httpx.Response(201, json={"id": "bug-123", "status": "received"}),
    )
    resp = client.post("/api/feedback/report", json=VALID)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "received"
    assert body["id"] == "bug-123"

    # Exactly one outbound call to {base}/v1/bugs as multipart with the right fields.
    assert len(rec.calls) == 1
    call = rec.calls[0]
    assert call["url"].endswith("/v1/bugs")
    files = call["kwargs"]["files"]
    from app.core.updater import APP_VERSION
    assert files["license_id"][1] == _CUSTOMER_ID
    assert files["title"][1] == "Es hakt"
    assert files["description"][1] == "Beim Stempeln passiert X"
    assert files["severity"][1] == "high"
    assert files["app_version"][1] == APP_VERSION
    assert files["os"][1] == platform.system().lower()


def test_default_severity_is_medium(client, mock_license, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    resp = client.post(
        "/api/feedback/report",
        json={"title": "T", "description": "D"},  # severity omitted
    )
    assert resp.status_code == 200
    assert rec.calls[0]["kwargs"]["files"]["severity"][1] == "medium"


def test_403_maps_to_409(client, mock_license, monkeypatch):
    _patch_post(monkeypatch, response=httpx.Response(403, json={"detail": "inactive"}))
    resp = client.post("/api/feedback/report", json=VALID)
    assert resp.status_code == 409


def test_429_maps_to_429(client, mock_license, monkeypatch):
    _patch_post(monkeypatch, response=httpx.Response(429))
    resp = client.post("/api/feedback/report", json=VALID)
    assert resp.status_code == 429


def test_network_error_maps_to_502(client, mock_license, monkeypatch):
    _patch_post(monkeypatch, exc=httpx.ConnectError("boom"))
    resp = client.post("/api/feedback/report", json=VALID)
    assert resp.status_code == 502


def test_no_license_returns_400_and_does_not_call_pzweb(client, monkeypatch):
    monkeypatch.setattr("app.core.license.get_current_license", lambda: None)
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    resp = client.post("/api/feedback/report", json=VALID)
    assert resp.status_code == 400
    assert rec.calls == []  # never reach out to pzweb without a license_id


def test_title_too_long_returns_422(client, mock_license, monkeypatch):
    _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    resp = client.post("/api/feedback/report", json={**VALID, "title": "x" * 201})
    assert resp.status_code == 422


def test_invalid_severity_returns_422(client, mock_license, monkeypatch):
    _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    resp = client.post("/api/feedback/report", json={**VALID, "severity": "urgent"})
    assert resp.status_code == 422
