"""Tests for the DEPLOYMENT_MODE switch (Phase 1, Issue #92).

Covers:
- is_saas() / is_onprem() helpers reflect the setting
- /api/system/info returns the current mode without auth
- Default is 'onprem' so existing installations upgrade seamlessly
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core import deployment


@pytest.fixture
def saas_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "saas")
    yield


@pytest.fixture
def onprem_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "onprem")
    yield


class TestDeploymentHelpers:
    def test_onprem_helpers(self, onprem_mode):
        assert deployment.is_onprem() is True
        assert deployment.is_saas() is False

    def test_saas_helpers(self, saas_mode):
        assert deployment.is_saas() is True
        assert deployment.is_onprem() is False

    def test_default_mode_is_onprem(self):
        # Belt & suspenders: the Literal type already constrains this, but
        # flipping the default would silently break existing installs.
        from app.config import Settings
        model_fields = Settings.model_fields
        assert model_fields["DEPLOYMENT_MODE"].default == "onprem"


class TestSystemInfoEndpoint:
    """/api/system/info is a minimal public endpoint."""

    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app)

    def test_returns_deployment_mode_and_version(self, client, onprem_mode):
        response = client.get("/api/system/info")
        assert response.status_code == 200
        data = response.json()
        assert data["deployment_mode"] == "onprem"
        assert "version" in data

    def test_saas_mode_reflected_in_response(self, client, saas_mode):
        response = client.get("/api/system/info")
        assert response.status_code == 200
        assert response.json()["deployment_mode"] == "saas"

    def test_no_auth_required(self, client):
        # No Authorization header — must still return 200. SPA fetches this
        # on first paint to decide whether to show signup UI.
        response = client.get("/api/system/info")
        assert response.status_code == 200

    def test_beta_flag_present(self, client):
        # Während der Beta liefert /api/system/info beta=true → Frontend-Badge.
        response = client.get("/api/system/info")
        assert response.json().get("beta") is True

    def test_shift_planning_weekdays_default_mon_fri(self, client):
        # #371: public weekday config for the shift planner; default Mo–Fr so the
        # frontend can render the correct week-view columns pre-login.
        response = client.get("/api/system/info")
        data = response.json()
        assert data["shift_planning_weekdays"] == [0, 1, 2, 3, 4]

    def test_response_does_not_leak_internal_state(self, client, onprem_mode):
        # Intentionally tight schema: no env, no ADMIN_EMAIL, no DB status.
        # onboarding_enabled and shift_planning_enabled are public UI
        # feature-toggles (welcome tour / Schichtplanung #305), not internal
        # state — exposed deliberately so the frontend can branch pre-login.
        response = client.get("/api/system/info")
        data = response.json()
        assert set(data.keys()) == {
            "deployment_mode",
            "version",
            "beta",
            "onboarding_enabled",
            "shift_planning_enabled",
            "shift_planning_weekdays",
        }


class TestBetaMode:
    """Beta-Phase: Lizenzpruefung komplett deaktiviert."""

    def test_beta_mode_defaults_true(self):
        from app.config import Settings
        assert Settings.model_fields["BETA_MODE"].default is True
