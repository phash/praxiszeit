"""Phase 8 — public /api/status endpoint (Issue #99)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_status_returns_healthy_shape():
    client = TestClient(app)
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in {"ok", "degraded"}
    assert "components" in data
    # Keys must always be present (the UI depends on them)
    for key in ("api", "database", "stripe_configured", "mail_configured"):
        assert key in data["components"]


def test_status_does_not_require_auth():
    client = TestClient(app)
    resp = client.get("/api/status")
    assert resp.status_code == 200
