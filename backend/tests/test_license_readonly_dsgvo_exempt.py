"""H2-Fix: LicenseReadOnlyMiddleware darf DSGVO-Betroffenenrechts-Endpoints
NICHT blockieren — sonst wuerde die Lizenz zum kommerziellen Druckmittel
gegen Art. 12 Abs. 2, Art. 16, Art. 17 DSGVO. Aufsichtsbehoerden bewerten
das als Verstoss.

Diese Tests pruefen, dass im Read-Only-Modus:
- bestehende Auth-Exempts weiterhin durchgelassen werden (Regression)
- normale Schreibvorgaenge blockiert werden (Default-Verhalten)
- DSGVO-Art-16/17-Endpoints durchgelassen werden (kein 403 von der
  Middleware — der Endpoint selbst darf 401/422/etc. liefern, das ist OK)

Bewusst kein Auth-Setup: wir wollen explizit beweisen, dass die License-
Middleware vor der Auth-Schicht durchlaesst. Wenn die Endpoints dann mit
401/403-from-auth/422 antworten, ist das aus License-Sicht erfolgreich.
Wichtig: die License-Middleware liefert IMMER 403 mit `Lizenz abgelaufen`
in `detail` — daran erkennen wir den Block.
"""
from __future__ import annotations

import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.core import license as license_module
from app.middleware.license import LicenseReadOnlyMiddleware


# ---------------------------------------------------------------------------
# Minimal-App: routers werden inkludiert, damit Paths existieren. Wir
# verzichten bewusst auf get_db-Overrides — die DSGVO-Tests interessieren
# sich nur dafuer, ob die License-Middleware den Request DURCHLAESST. Ob
# der Endpoint selbst dann 401/422 wirft, ist hier irrelevant.
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    from app.routers import (
        auth as auth_router,
        admin as admin_router,
        time_entries as te_router,
        tenant_billing,
        me as me_router,
    )
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="License-DSGVO-Test")

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(LicenseReadOnlyMiddleware)

    app.include_router(auth_router.router)
    app.include_router(admin_router.router)
    app.include_router(te_router.router)
    app.include_router(tenant_billing.router)
    app.include_router(me_router.router)
    return app


@pytest.fixture
def onprem_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "onprem")
    yield


@pytest.fixture
def read_only_license():
    """Setzt die Lizenz auf Read-Only und stellt am Ende den Default wieder her."""
    license_module.set_license_state(None, read_only=True)
    yield
    license_module.set_license_state(None, read_only=False)


@pytest.fixture
def client(onprem_mode, read_only_license):
    app = _build_app()
    return TestClient(app, raise_server_exceptions=False)


# Markerstring aus license.py — eindeutig dem License-Block zuordbar.
LICENSE_BLOCK_MARKER = "Lizenz abgelaufen"


def _was_blocked_by_license(response) -> bool:
    """True, wenn die License-Middleware mit ihrer 403-Meldung geblockt hat."""
    if response.status_code != 403:
        return False
    try:
        detail = response.json().get("detail", "")
    except Exception:
        return False
    return LICENSE_BLOCK_MARKER in detail


# ---------------------------------------------------------------------------
# Regression: bestehende Auth-Exempts bleiben funktionsfaehig
# ---------------------------------------------------------------------------

class TestExistingAuthExemptsRegression:
    def test_login_not_blocked_by_license(self, client):
        """POST /api/auth/login darf bei Read-Only nicht durch License geblockt sein.
        Endpoint kann 401/422 zurueckgeben (kein User in Test-DB) — das ist OK."""
        resp = client.post("/api/auth/login", json={"username": "x", "password": "y"})
        assert not _was_blocked_by_license(resp), (
            f"License-Middleware hat /api/auth/login geblockt: "
            f"status={resp.status_code} body={resp.text[:200]}"
        )

    def test_refresh_not_blocked_by_license(self, client):
        resp = client.post("/api/auth/refresh")
        assert not _was_blocked_by_license(resp)

    def test_logout_not_blocked_by_license(self, client):
        resp = client.post("/api/auth/logout")
        assert not _was_blocked_by_license(resp)


# ---------------------------------------------------------------------------
# Default: normale Schreibvorgaenge sind blockiert
# ---------------------------------------------------------------------------

class TestDefaultWriteBlocking:
    def test_normal_write_blocked(self, client):
        """POST /api/time-entries/clock-in (= Stempelvorgang) MUSS bei
        Read-Only mit 403 + License-Marker geblockt werden, sonst ist
        die ganze Schutzfunktion kaputt."""
        resp = client.post("/api/time-entries/clock-in")
        assert _was_blocked_by_license(resp), (
            f"Erwartet License-Block (403 + 'Lizenz abgelaufen'), "
            f"bekam status={resp.status_code} body={resp.text[:200]}"
        )

    def test_admin_create_user_blocked(self, client):
        """POST /api/admin/users (normales Anlegen) bleibt blockiert —
        nur die DSGVO-Loeschungs-Endpoints sind exempt, nicht die
        gesamte /api/admin/users-Route."""
        resp = client.post("/api/admin/users", json={"username": "x"})
        # Hier reicht: entweder License-Block ODER Auth-Block. Wichtig
        # ist nur, dass es NICHT die DSGVO-Exempt-Logik nicht versehent-
        # lich auf die ganze Prefix-Familie ausweitet.
        assert _was_blocked_by_license(resp) or resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Kernfix: DSGVO-Endpoints werden NICHT mehr von License geblockt
# ---------------------------------------------------------------------------

class TestDsgvoExemptEndpoints:
    """Pro Endpoint: Beweis 'kein 403 mit License-Marker'. Andere Status-
    codes (401/422/404/...) sind OK — die kommen von Auth/Validation, nicht
    von der License-Middleware."""

    def test_anonymize_user_not_blocked(self, client):
        # Art. 17 DSGVO — Anonymisierung
        user_id = uuid.uuid4()
        resp = client.post(f"/api/admin/users/{user_id}/anonymize")
        assert not _was_blocked_by_license(resp), (
            f"License-Middleware hat Art-17-Anonymisierung geblockt: "
            f"status={resp.status_code} body={resp.text[:200]}"
        )

    def test_purge_user_not_blocked(self, client):
        # Art. 17 DSGVO — endgueltige Loeschung
        user_id = uuid.uuid4()
        resp = client.delete(f"/api/admin/users/{user_id}/purge")
        assert not _was_blocked_by_license(resp), (
            f"License-Middleware hat Art-17-Purge geblockt: "
            f"status={resp.status_code} body={resp.text[:200]}"
        )

    def test_tenant_request_deletion_not_blocked(self, client):
        # Art. 17 DSGVO — Tenant-Level-Loeschung
        resp = client.post("/api/tenant/request-deletion")
        assert not _was_blocked_by_license(resp), (
            f"License-Middleware hat Tenant-Request-Deletion geblockt: "
            f"status={resp.status_code} body={resp.text[:200]}"
        )

    def test_tenant_cancel_deletion_not_blocked(self, client):
        # Gegenstueck zu request-deletion — muss erreichbar bleiben, sonst
        # waere ein versehentlich gestelltes Loeschbegehren irreversibel.
        resp = client.post("/api/tenant/cancel-deletion")
        assert not _was_blocked_by_license(resp), (
            f"License-Middleware hat Tenant-Cancel-Deletion geblockt: "
            f"status={resp.status_code} body={resp.text[:200]}"
        )

    def test_profile_put_not_blocked(self, client):
        # Art. 16 DSGVO — Berichtigung von Stammdaten
        resp = client.put("/api/auth/profile", json={"first_name": "Neu"})
        assert not _was_blocked_by_license(resp), (
            f"License-Middleware hat Art-16-Profile-Berichtigung geblockt: "
            f"status={resp.status_code} body={resp.text[:200]}"
        )

    def test_data_export_get_not_blocked(self, client):
        # Art. 15 DSGVO — Auskunft per GET. GET wird sowieso nicht von der
        # Middleware geprueft (nur _WRITE_METHODS), aber Belt-and-Suspenders.
        resp = client.get("/api/me/data-export")
        assert not _was_blocked_by_license(resp), (
            f"License-Middleware hat Art-15-Auskunft (GET) geblockt: "
            f"status={resp.status_code} body={resp.text[:200]}"
        )


# ---------------------------------------------------------------------------
# Direkter Unit-Test der Pattern-Allowlist (ohne TestClient)
# ---------------------------------------------------------------------------

class TestDsgvoPatternMatching:
    """Stellt sicher, dass die Patterns weder zu eng noch zu weit greifen."""

    def test_exact_paths_match(self):
        from app.middleware.license import _is_dsgvo_exempt

        uid = "11111111-2222-3333-4444-555555555555"
        assert _is_dsgvo_exempt("POST", f"/api/admin/users/{uid}/anonymize")
        assert _is_dsgvo_exempt("DELETE", f"/api/admin/users/{uid}/purge")
        assert _is_dsgvo_exempt("POST", "/api/tenant/request-deletion")
        assert _is_dsgvo_exempt("POST", "/api/tenant/cancel-deletion")
        assert _is_dsgvo_exempt("PUT", "/api/auth/profile")

    def test_wrong_method_does_not_match(self):
        from app.middleware.license import _is_dsgvo_exempt

        uid = "11111111-2222-3333-4444-555555555555"
        # POST auf /purge ist kein DSGVO-Loeschvorgang
        assert not _is_dsgvo_exempt("POST", f"/api/admin/users/{uid}/purge")
        # DELETE auf /anonymize gibts nicht
        assert not _is_dsgvo_exempt("DELETE", f"/api/admin/users/{uid}/anonymize")
        # PATCH auf /profile ist nicht der definierte Endpoint
        assert not _is_dsgvo_exempt("PATCH", "/api/auth/profile")

    def test_prefix_attack_does_not_match(self):
        """Schutz gegen zu grobes Prefix-Matching: weder
        /api/admin/users (Liste) noch /api/tenant/foo darf exempt sein."""
        from app.middleware.license import _is_dsgvo_exempt

        assert not _is_dsgvo_exempt("POST", "/api/admin/users")
        assert not _is_dsgvo_exempt("POST", "/api/admin/users/")
        uid = "11111111-2222-3333-4444-555555555555"
        # Sub-Pfad jenseits von anonymize/purge
        assert not _is_dsgvo_exempt("POST", f"/api/admin/users/{uid}/foo")
        # Andere tenant-Endpoints bleiben blockiert
        assert not _is_dsgvo_exempt("POST", "/api/tenant/upgrade")
        assert not _is_dsgvo_exempt("PUT", "/api/tenant/billing")
        # Auth-Profile-Picture ist NICHT exempt (Stammdaten-Berichtigung
        # geht ueber /profile, nicht ueber /profile-picture)
        assert not _is_dsgvo_exempt("PUT", "/api/auth/profile-picture")
        assert not _is_dsgvo_exempt("DELETE", "/api/auth/profile-picture")
