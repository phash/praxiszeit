"""M2-Fix: Integration-Tests fuer LicenseReadOnlyMiddleware.

Komplementaer zu:
- test_license_signature_mismatch.py  — pure validator-Regression (Schluessel-Mismatch)
- test_license_readonly_dsgvo_exempt.py — DSGVO-Allowlist + Login-Regression

Diese Datei deckt die breitere Verhaltens-Matrix der Middleware ab:

1. Method-Matrix:    POST/PUT/PATCH/DELETE auf realen App-Endpoints werden
                     im Read-Only-Modus mit 403 + License-Marker geblockt.
2. Method-Indep.:    GET/HEAD/OPTIONS gehen *immer* durch (nur _WRITE_METHODS
                     wird gefiltert).
3. Auth-Exempts:     /api/auth/login|logout|refresh|password-reset bleiben
                     erreichbar (Read-Only ist kein Auth-Lockout).
4. Bypass-Check:     Admin-Status hebt Read-Only NICHT auf (die Middleware
                     liest die Lizenz, nicht den User).
5. SaaS-Pfad:        Im SaaS-Mode greift die Onprem-Lizenz nicht — Writes
                     ohne Tenant-Bezug (unauthenticated) gehen durch.

Wie test_license_readonly_dsgvo_exempt.py verzichten wir auf vollstaendiges
get_db-Wiring: der Test soll nur das Middleware-Verhalten beweisen, nicht
die Endpoint-Logik. Wir erkennen den License-Block am 403-Status +
'Lizenz abgelaufen' im detail.
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
# Test-App-Builder. Wir koppeln die echten Router an, damit Paths existieren
# und das Routing realistisch ist. Endpoint-internes Verhalten (DB, Auth)
# ist fuer License-Middleware irrelevant — uns interessiert nur, ob der
# Request *vor* dem Endpoint geblockt wird oder durchgeht.
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    from app.routers import (
        auth as auth_router,
        admin as admin_router,
        time_entries as te_router,
        absences as absences_router,
        vacation_requests as vr_router,
        tenant_billing,
        me as me_router,
        dashboard as dashboard_router,
        reports as reports_router,
        superadmin as superadmin_router,
    )
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="License-Middleware-Integration-Test")

    # Rate-Limiting deaktivieren, damit die Method-Matrix nicht in Login-
    # Lockouts laeuft (Login-Rate-Limit ist sehr eng).
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(LicenseReadOnlyMiddleware)

    app.include_router(auth_router.router)
    app.include_router(admin_router.router)
    app.include_router(te_router.router)
    app.include_router(absences_router.router)
    app.include_router(vr_router.router)
    app.include_router(tenant_billing.router)
    app.include_router(me_router.router)
    app.include_router(dashboard_router.router)
    app.include_router(reports_router.router)
    app.include_router(superadmin_router.router)

    # Drei Mini-Routen fuer die Methoden-Matrix — bewusst trivial, damit der
    # Endpoint nie 500 wirft und wir die Middleware-Entscheidung isoliert
    # sehen koennen.
    @app.get("/__mw_probe")
    def probe_get():
        return {"ok": True}

    @app.post("/__mw_probe")
    def probe_post():
        return {"ok": True}

    @app.put("/__mw_probe")
    def probe_put():
        return {"ok": True}

    @app.patch("/__mw_probe")
    def probe_patch():
        return {"ok": True}

    @app.delete("/__mw_probe")
    def probe_delete():
        return {"ok": True}

    @app.head("/__mw_probe")
    def probe_head():
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def onprem_mode(monkeypatch):
    """Erzwingt onprem-DEPLOYMENT_MODE — sonst greift der Lizenz-Check ueberhaupt
    nicht (nur _check_saas_suspend laeuft, der ohne JWT no-op ist)."""
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "onprem")
    yield


@pytest.fixture
def saas_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "saas")
    yield


@pytest.fixture
def read_only_license():
    """Lizenz in Read-Only versetzen; nach dem Test zurueckdrehen."""
    license_module.set_license_state(None, read_only=True)
    yield
    license_module.set_license_state(None, read_only=False)


@pytest.fixture
def writable_license():
    """Lizenz NICHT in Read-Only — Default-Zustand. Macht den Negativ-Pfad
    (Writes gehen durch wenn nicht read_only) sichtbar."""
    license_module.set_license_state(None, read_only=False)
    yield


@pytest.fixture
def client_readonly(onprem_mode, read_only_license):
    app = _build_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_writable(onprem_mode, writable_license):
    app = _build_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_saas_readonly(saas_mode, read_only_license):
    """SaaS-Modus + read_only-Flag — der Onprem-Check darf nicht greifen,
    der SaaS-Check (subscription_status) ohne JWT no-op."""
    app = _build_app()
    return TestClient(app, raise_server_exceptions=False)


LICENSE_BLOCK_MARKER = "Lizenz abgelaufen"


def _was_blocked_by_license(response) -> bool:
    if response.status_code != 403:
        return False
    try:
        detail = response.json().get("detail", "")
    except Exception:
        return False
    return LICENSE_BLOCK_MARKER in detail


# ---------------------------------------------------------------------------
# 1. Method-Matrix: alle Write-Methoden werden geblockt
# ---------------------------------------------------------------------------

class TestWriteMethodMatrix:
    """_WRITE_METHODS = {POST, PUT, PATCH, DELETE}. Wir beweisen das gegen
    ECHTE App-Endpoints (nicht nur die Mini-Probe), damit ein versehentliches
    Loch in der Router-Registrierung sichtbar wuerde."""

    def test_post_clock_in_blocked(self, client_readonly):
        resp = client_readonly.post("/api/time-entries/clock-in")
        assert _was_blocked_by_license(resp)

    def test_post_clock_out_blocked(self, client_readonly):
        resp = client_readonly.post("/api/time-entries/clock-out")
        assert _was_blocked_by_license(resp)

    def test_post_manual_entry_blocked(self, client_readonly):
        resp = client_readonly.post("/api/time-entries/", json={})
        assert _was_blocked_by_license(resp)

    def test_put_time_entry_blocked(self, client_readonly):
        entry_id = uuid.uuid4()
        resp = client_readonly.put(f"/api/time-entries/{entry_id}", json={})
        assert _was_blocked_by_license(resp)

    def test_delete_time_entry_blocked(self, client_readonly):
        entry_id = uuid.uuid4()
        resp = client_readonly.delete(f"/api/time-entries/{entry_id}")
        assert _was_blocked_by_license(resp)

    def test_put_admin_user_blocked(self, client_readonly):
        """PUT /api/admin/users/{id} (User-Update) — nicht in der DSGVO-Allowlist."""
        user_id = uuid.uuid4()
        resp = client_readonly.put(f"/api/admin/users/{user_id}", json={})
        assert _was_blocked_by_license(resp)

    def test_delete_admin_user_blocked(self, client_readonly):
        """DELETE /api/admin/users/{id} (Soft-Delete) — nicht das DSGVO-Purge,
        also bleibt der License-Block aktiv."""
        user_id = uuid.uuid4()
        resp = client_readonly.delete(f"/api/admin/users/{user_id}")
        assert _was_blocked_by_license(resp)

    def test_patch_vacation_request_blocked(self, client_readonly):
        """PATCH ist die seltenste Write-Method — sicher abdecken."""
        request_id = uuid.uuid4()
        resp = client_readonly.patch(
            f"/api/vacation-requests/{request_id}", json={}
        )
        assert _was_blocked_by_license(resp)

    def test_patch_tenant_billing_blocked(self, client_readonly):
        """PATCH /api/tenant/billing — bewusst NICHT in der DSGVO-Allowlist
        (steht im Pattern-Test schon, hier auch via Integration)."""
        resp = client_readonly.patch("/api/tenant/billing", json={})
        assert _was_blocked_by_license(resp)

    def test_post_absence_blocked(self, client_readonly):
        resp = client_readonly.post("/api/absences/", json={})
        assert _was_blocked_by_license(resp)

    def test_post_admin_change_request_review_blocked(self, client_readonly):
        request_id = uuid.uuid4()
        resp = client_readonly.post(
            f"/api/admin/change-requests/{request_id}/review", json={}
        )
        assert _was_blocked_by_license(resp)


# ---------------------------------------------------------------------------
# 2. Method-Independence: GET/HEAD/OPTIONS gehen IMMER durch
# ---------------------------------------------------------------------------

class TestReadMethodsAlwaysPass:
    """Nur _WRITE_METHODS wird gefiltert. GET/HEAD/OPTIONS muessen unabhaengig
    vom Lizenzstatus durchgelassen werden — sonst werden Auskunft (Art. 15
    DSGVO), Export (§16 ArbZG) und Health-Checks blockiert."""

    def test_get_health_passes(self, client_readonly):
        # /api/health ist auf dieser Mini-App nicht registriert, aber unser
        # generischer Probe-Endpoint reicht fuer den Methoden-Beweis.
        resp = client_readonly.get("/__mw_probe")
        assert resp.status_code == 200
        assert not _was_blocked_by_license(resp)

    def test_head_passes(self, client_readonly):
        resp = client_readonly.head("/__mw_probe")
        # HEAD darf nicht 403 + LICENSE_BLOCK liefern. FastAPI gibt 200 zurueck.
        assert resp.status_code == 200
        assert not _was_blocked_by_license(resp)

    def test_options_passes(self, client_readonly):
        """OPTIONS wird vom Router automatisch beantwortet (allow-methods)."""
        resp = client_readonly.options("/__mw_probe")
        assert resp.status_code in (200, 405)
        # Der Wichtige Punkt: KEIN License-Block (403 + Marker).
        assert not _was_blocked_by_license(resp)

    def test_get_real_endpoint_passes(self, client_readonly):
        """Reale GET-Route (data-export) — beweist methoden-Unabhaengigkeit
        auch an einem App-Endpoint, nicht nur am Probe."""
        resp = client_readonly.get("/api/me/data-export")
        assert not _was_blocked_by_license(resp), (
            f"License-Middleware hat GET data-export geblockt: "
            f"status={resp.status_code} body={resp.text[:200]}"
        )

    def test_get_admin_users_passes(self, client_readonly):
        resp = client_readonly.get("/api/admin/users")
        assert not _was_blocked_by_license(resp)

    def test_get_admin_settings_passes(self, client_readonly):
        resp = client_readonly.get("/api/admin/settings")
        assert not _was_blocked_by_license(resp)

    def test_get_dashboard_passes(self, client_readonly):
        resp = client_readonly.get("/api/dashboard/")
        assert not _was_blocked_by_license(resp)

    def test_get_reports_export_passes(self, client_readonly):
        """§16-ArbZG-Export ist im Read-Only-Modus essentiell."""
        resp = client_readonly.get("/api/reports/export")
        assert not _was_blocked_by_license(resp)


# ---------------------------------------------------------------------------
# 3. Auth-Exempts: Login/Logout/Refresh + Password-Reset
# ---------------------------------------------------------------------------

class TestAuthExemptPaths:
    """_EXEMPT_PATH_PREFIXES garantiert dass Admins sich noch einloggen
    koennen — sonst wuerde Read-Only sie aussperren und ein §16-Export
    waere unmoeglich."""

    def test_login_post_passes(self, client_readonly):
        resp = client_readonly.post(
            "/api/auth/login", json={"username": "x", "password": "y"}
        )
        assert not _was_blocked_by_license(resp)

    def test_refresh_post_passes(self, client_readonly):
        resp = client_readonly.post("/api/auth/refresh")
        assert not _was_blocked_by_license(resp)

    def test_logout_post_passes(self, client_readonly):
        resp = client_readonly.post("/api/auth/logout")
        assert not _was_blocked_by_license(resp)

    def test_password_reset_prefix_request_passes(self, client_readonly):
        """Der Prefix /api/auth/password-reset ist exempt. Endpoint
        existiert aktuell noch nicht (Feature-Roadmap) — Middleware muss
        also 404 vom Router durchlassen, NICHT 403 vom License-Block.
        Wenn der Endpoint spaeter hinzukommt, bleibt der Test gruen."""
        resp = client_readonly.post(
            "/api/auth/password-reset/request", json={"email": "x@y.z"}
        )
        # 404 ist OK (Endpoint existiert nicht). Wichtig: kein 403 von License.
        assert not _was_blocked_by_license(resp)

    def test_password_reset_prefix_confirm_passes(self, client_readonly):
        resp = client_readonly.post(
            "/api/auth/password-reset/confirm", json={"token": "t", "new": "p"}
        )
        assert not _was_blocked_by_license(resp)

    def test_change_password_NOT_exempt(self, client_readonly):
        """/api/auth/change-password (eingeloggte Aenderung) ist NICHT in
        der Exempt-Liste — bewusst, da Read-Only auch Passwort-Aenderungen
        sperrt. Vermeidet Gaming via Doppel-Account-Anlegen. Das ist
        einer der Edge-Cases die das Spec-Verhalten festschreiben."""
        resp = client_readonly.post(
            "/api/auth/change-password",
            json={"current_password": "x", "new_password": "y"},
        )
        assert _was_blocked_by_license(resp), (
            f"change-password sollte im Read-Only geblockt sein, "
            f"war aber {resp.status_code}: {resp.text[:200]}"
        )


# ---------------------------------------------------------------------------
# 4. Bypass-Check: Admin-Status hebt Read-Only nicht auf
# ---------------------------------------------------------------------------

class TestNoUserPrivilegeBypass:
    """Die Middleware liest NUR den Lizenz-Flag, nicht den User. Ein
    Admin-User darf im Read-Only-Modus also NICHT mehr schreiben als ein
    normaler User. (Schutz gegen versehentlichen Privilege-Bypass falls
    spaeter `if user.is_admin: skip` eingebaut wuerde.)
    """

    def test_admin_write_blocked_same_as_normal(self, client_readonly):
        """Wir simulieren keinen echten Admin-Login — der Punkt ist:
        Selbst mit Admin-Endpoints im Spiel kommt die Middleware-403
        VOR der Auth-Pruefung. Beweisbar daran dass der License-Marker
        und nicht ein Auth-401 zurueckkommt."""
        # POST /api/admin/users (Create) — admin-protected aber NICHT
        # in der DSGVO-Allowlist.
        resp = client_readonly.post(
            "/api/admin/users",
            json={"username": "neu", "password": "p"},
            headers={"Authorization": "Bearer ANY_TOKEN"},
        )
        assert _was_blocked_by_license(resp), (
            f"Erwartet License-Block VOR Auth-Pruefung, bekam "
            f"{resp.status_code}: {resp.text[:200]}"
        )

    def test_superadmin_write_also_blocked(self, client_readonly):
        """Superadmin-Endpoints sind ebenfalls write-blockiert. Selbst
        ein Cron-Aufruf darf im Read-Only nicht durchgehen, weil sonst
        Metriken / Trial-Checks Daten schreiben wuerden."""
        resp = client_readonly.post("/api/superadmin/cron/metrics-refresh")
        assert _was_blocked_by_license(resp)


# ---------------------------------------------------------------------------
# 5. Negativ-Pfad: bei aktiver Lizenz greift die Middleware NICHT
# ---------------------------------------------------------------------------

class TestWritableLicensePassesThrough:
    """Wenn read_only=False (Default), darf die Middleware *keine* Writes
    blockieren — sie soll No-Op sein. Sonst waere der Default-Modus
    bereits gestoert."""

    def test_post_probe_passes_when_writable(self, client_writable):
        resp = client_writable.post("/__mw_probe")
        assert resp.status_code == 200
        assert not _was_blocked_by_license(resp)

    def test_put_probe_passes_when_writable(self, client_writable):
        resp = client_writable.put("/__mw_probe")
        assert resp.status_code == 200

    def test_delete_probe_passes_when_writable(self, client_writable):
        resp = client_writable.delete("/__mw_probe")
        assert resp.status_code == 200

    def test_real_clock_in_passes_when_writable(self, client_writable):
        """Reale App-Route: clock-in. Im writable-Modus darf KEIN
        License-403 kommen — nur Auth-401/422 vom Endpoint selbst."""
        resp = client_writable.post("/api/time-entries/clock-in")
        assert not _was_blocked_by_license(resp)


# ---------------------------------------------------------------------------
# 6. SaaS-Pfad: Onprem-Read-Only-Flag greift im SaaS-Mode NICHT
# ---------------------------------------------------------------------------

class TestSaasModeIgnoresOnpremFlag:
    """Im SaaS-Mode wird der read_only-Flag NICHT konsultiert (der ist nur
    fuer Onprem-Native-Installs). Stattdessen prueft die Middleware
    `subscription_status='suspended'` per JWT. Ohne JWT ist der Check
    No-Op — Writes gehen durch.

    Das beweist, dass ein versehentliches Setzen von license_module.
    set_license_state(read_only=True) im SaaS-Mode keine Production-
    Auswirkung hat.
    """

    def test_saas_write_not_blocked_by_onprem_flag(self, client_saas_readonly):
        resp = client_saas_readonly.post("/__mw_probe")
        # Im SaaS-Mode + ohne JWT muss der Write durchgehen.
        assert resp.status_code == 200
        assert not _was_blocked_by_license(resp)

    def test_saas_real_write_not_blocked_by_onprem_flag(self, client_saas_readonly):
        resp = client_saas_readonly.post("/api/time-entries/clock-in")
        # Auch hier: kein License-Marker. Endpoint selbst kann 401/422 liefern.
        assert not _was_blocked_by_license(resp)
