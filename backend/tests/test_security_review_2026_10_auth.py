"""Sicherheits-Review 2026-10 — Anmeldung, Abmeldung, 2FA, Selbstauskunft.

1. (MEDIUM) Abmelden muss auch mit abgelaufenem Access-Token wirken: Cookies
   loeschen und — wenn der Refresh-Cookie noch gueltig ist — die Sitzung
   serverseitig entwerten (token_version++). Sonst bleibt am geteilten
   Praxis-PC eine 7-Tage-Sitzung im Browser liegen. Der Refresh-Cookie ist auf
   ``/api/auth/refresh`` beschraenkt, deshalb gibt es den Pfad
   ``/api/auth/refresh/logout`` (gleiche Logik).
2. (MEDIUM) 2FA: ``/totp/setup`` bei aktiver 2FA → 400 (nicht still das
   aktive Secret ersetzen); ``/totp/disable`` verlangt zusaetzlich einen
   gueltigen Code und schreibt eine ``security_events``-Zeile.
3. (LOW) Admin setzt das EIGENE Passwort nicht ueber ``set-password``
   (ohne Nachweis des alten Passworts) → 400.
4. (LOW) Login-Protokoll: unbekannte Namen nur gekuerzt+gehasht, Steuerzeichen
   eingeebnet, ``username`` hoechstens 100 Zeichen.
5. (LOW) Kontosperre je (Name, Client-IP) + hohe Obergrenze je Name.
6. (MEDIUM) ``GET /api/auth/me/export`` unter Impersonation → 403.
"""
import logging
from unittest.mock import patch

import pyotp
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core import totp_crypto
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import ImpersonationSession
from app.models.security_event import EVENT_TOTP_DISABLED_SELF, SecurityEvent
from app.routers import auth as auth_router
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

TEST_USER_PASSWORD = "testpassword123"  # noqa: S105 — conftest fixture
SECURITY_LOGGER = "praxiszeit.security"


@pytest.fixture
def raw_client(db):
    """Client OHNE get_current_user-Override (echte Token-Pruefung).
    RLS-Setter gepatcht — SQLite kennt kein SET LOCAL."""
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    with patch("app.routers.auth.set_superadmin_context"), \
         patch("app.middleware.auth.set_superadmin_context"), \
         patch("app.middleware.auth.set_tenant_context"):
        with TestClient(test_app) as c:
            yield c
    test_app.dependency_overrides.clear()


def _client_as(db, user, *, admin=False):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[auth_router.get_optional_current_user] = lambda: user
    if admin:
        test_app.dependency_overrides[require_admin] = lambda: user
    return TestClient(test_app)


@pytest.fixture(autouse=True)
def _clean_overrides_and_lockout():
    auth_router._failed_logins.clear()
    yield
    test_app.dependency_overrides.clear()
    auth_router._failed_logins.clear()


def _refresh_cookie_for(user):
    return auth_service.create_refresh_token(
        str(user.id), user.token_version, str(DEFAULT_TENANT_ID)
    )


# ─────────────────────────────────────────────────────────────────────
# 1 — Abmelden ohne gueltiges Access-Token
# ─────────────────────────────────────────────────────────────────────


class TestLogoutWithoutAccessToken:
    @pytest.mark.parametrize("path", ["/api/auth/logout", "/api/auth/refresh/logout"])
    def test_logout_without_any_token_is_200_and_clears_cookies(self, raw_client, path):
        r = raw_client.post(path)
        assert r.status_code == 200, r.text
        set_cookie = " ".join(r.headers.get_list("set-cookie"))
        assert "refresh_token=" in set_cookie
        assert "csrf_token=" in set_cookie

    def test_expired_access_token_but_valid_refresh_cookie_revokes_session(
        self, raw_client, db, test_user
    ):
        before = test_user.token_version or 0
        refresh = _refresh_cookie_for(test_user)
        raw_client.cookies.set("refresh_token", refresh, path="/api/auth/refresh")
        r = raw_client.post(
            "/api/auth/refresh/logout",
            headers={"Authorization": "Bearer abgelaufen.oder.kaputt"},
        )
        assert r.status_code == 200, r.text
        db.refresh(test_user)
        assert test_user.token_version == before + 1
        # Der alte Refresh-Cookie taugt nicht mehr fuer eine neue Sitzung.
        raw_client.cookies.set("refresh_token", refresh, path="/api/auth/refresh")
        assert raw_client.post("/api/auth/refresh").status_code == 401

    def test_stale_refresh_cookie_does_not_bump(self, raw_client, db, test_user):
        stale = auth_service.create_refresh_token(
            str(test_user.id), (test_user.token_version or 0) - 1, str(DEFAULT_TENANT_ID)
        )
        before = test_user.token_version
        raw_client.cookies.set("refresh_token", stale, path="/api/auth/refresh")
        assert raw_client.post("/api/auth/refresh/logout").status_code == 200
        db.refresh(test_user)
        assert test_user.token_version == before

    def test_access_token_cannot_be_used_as_refresh_cookie(self, raw_client, db, test_user):
        access = auth_service.create_access_token(
            str(test_user.id), test_user.role.value, test_user.token_version, str(DEFAULT_TENANT_ID)
        )
        before = test_user.token_version
        raw_client.cookies.set("refresh_token", access, path="/api/auth/refresh")
        assert raw_client.post("/api/auth/refresh/logout").status_code == 200
        db.refresh(test_user)
        assert test_user.token_version == before

    def test_valid_access_token_still_revokes(self, raw_client, db, test_user):
        access = auth_service.create_access_token(
            str(test_user.id), test_user.role.value, test_user.token_version, str(DEFAULT_TENANT_ID)
        )
        before = test_user.token_version
        r = raw_client.post("/api/auth/logout", headers={"Authorization": f"Bearer {access}"})
        assert r.status_code == 200
        db.refresh(test_user)
        assert test_user.token_version == before + 1

    def test_refresh_cookie_logout_closes_impersonation_sessions(
        self, raw_client, db, test_admin, test_user
    ):
        session = ImpersonationSession(
            tenant_id=DEFAULT_TENANT_ID, impersonator_id=test_admin.id,
            target_id=test_user.id,
        )
        db.add(session)
        db.commit()
        raw_client.cookies.set(
            "refresh_token", _refresh_cookie_for(test_admin), path="/api/auth/refresh"
        )
        assert raw_client.post("/api/auth/refresh/logout").status_code == 200
        db.refresh(session)
        assert session.ended_at is not None


# ─────────────────────────────────────────────────────────────────────
# 2 — 2FA
# ─────────────────────────────────────────────────────────────────────


def _enable_totp(db, user):
    secret = auth_service.generate_totp_secret()
    user.totp_secret = totp_crypto.encrypt_secret(secret)
    user.totp_enabled = True
    user.last_totp_counter = None
    db.commit()
    return secret


class TestTotp:
    def test_setup_refused_while_enabled(self, db, test_user):
        secret = _enable_totp(db, test_user)
        c = _client_as(db, test_user)
        r = c.post("/api/auth/totp/setup", json={"password": TEST_USER_PASSWORD})
        assert r.status_code == 400
        assert "deaktivieren" in r.json()["detail"]
        db.refresh(test_user)
        assert test_user.totp_enabled is True
        assert totp_crypto.decrypt_secret(test_user.totp_secret) == secret

    def test_disable_requires_code(self, db, test_user):
        _enable_totp(db, test_user)
        c = _client_as(db, test_user)
        r = c.request("DELETE", "/api/auth/totp/disable", json={"password": TEST_USER_PASSWORD})
        assert r.status_code == 422
        db.refresh(test_user)
        assert test_user.totp_enabled is True

    def test_disable_rejects_wrong_code(self, db, test_user):
        secret = _enable_totp(db, test_user)
        good = pyotp.TOTP(secret).now()
        wrong = "000000" if good != "000000" else "111111"
        c = _client_as(db, test_user)
        r = c.request("DELETE", "/api/auth/totp/disable",
                      json={"password": TEST_USER_PASSWORD, "code": wrong})
        assert r.status_code == 400
        assert "bereits verwendet" not in r.json()["detail"]
        db.refresh(test_user)
        assert test_user.totp_enabled is True
        assert db.query(SecurityEvent).count() == 0

    def test_disable_with_password_and_code_logs_security_event(self, db, test_user):
        secret = _enable_totp(db, test_user)
        c = _client_as(db, test_user)
        r = c.request("DELETE", "/api/auth/totp/disable",
                      json={"password": TEST_USER_PASSWORD, "code": pyotp.TOTP(secret).now()})
        assert r.status_code == 200, r.text
        db.refresh(test_user)
        assert test_user.totp_enabled is False
        rows = db.query(SecurityEvent).filter(SecurityEvent.event == EVENT_TOTP_DISABLED_SELF).all()
        assert len(rows) == 1
        assert rows[0].subject_user_id == test_user.id
        assert rows[0].actor == f"user:{test_user.id}"

    def test_disable_code_is_replay_safe(self, db, test_user):
        """Ein bereits beim Login verbrauchter Code taugt nicht zum Abschalten."""
        secret = _enable_totp(db, test_user)
        code = pyotp.TOTP(secret).now()
        accepted = auth_service.verify_totp_with_counter(secret, code, None)
        test_user.last_totp_counter = accepted
        db.commit()
        c = _client_as(db, test_user)
        r = c.request("DELETE", "/api/auth/totp/disable",
                      json={"password": TEST_USER_PASSWORD, "code": code})
        assert r.status_code == 400
        # Release-Review 1.20.2: eigene Meldung statt "Ungültiger Code" — die
        # App zeigt den beim Login verbrauchten Code noch an.
        assert "bereits verwendet" in r.json()["detail"]
        db.refresh(test_user)
        assert test_user.totp_enabled is True

    def test_enable_logs_security_event(self, db, test_user):
        from app.models.security_event import EVENT_TOTP_ENABLED
        c = _client_as(db, test_user)
        setup = c.post("/api/auth/totp/setup", json={"password": TEST_USER_PASSWORD}).json()
        r = c.post("/api/auth/totp/verify", json={"code": pyotp.TOTP(setup["secret"]).now()})
        assert r.status_code == 200, r.text
        rows = db.query(SecurityEvent).filter(SecurityEvent.event == EVENT_TOTP_ENABLED).all()
        assert len(rows) == 1
        assert rows[0].actor == f"user:{test_user.id}"


# ─────────────────────────────────────────────────────────────────────
# 3 — set-password auf sich selbst
# ─────────────────────────────────────────────────────────────────────


class TestAdminSetOwnPassword:
    def test_admin_cannot_set_own_password_via_admin_route(self, db, test_admin):
        old_hash = test_admin.password_hash
        c = _client_as(db, test_admin, admin=True)
        r = c.post(f"/api/admin/users/{test_admin.id}/set-password",
                   json={"password": "Neues" + "Kennwort1"})
        assert r.status_code == 400
        assert "Passwort ändern" in r.json()["detail"]
        db.refresh(test_admin)
        assert test_admin.password_hash == old_hash

    def test_admin_can_still_set_foreign_password(self, db, test_admin, test_user):
        c = _client_as(db, test_admin, admin=True)
        r = c.post(f"/api/admin/users/{test_user.id}/set-password",
                   json={"password": "Neues" + "Kennwort1"})
        assert r.status_code == 200, r.text


# ─────────────────────────────────────────────────────────────────────
# 4 — Login-Protokoll
# ─────────────────────────────────────────────────────────────────────


class TestLoginLogging:
    def test_unknown_username_is_not_logged_verbatim(self, raw_client, default_tenant, caplog):
        typed_password = "Geheim-Passwort-im-Namensfeld-42"
        with caplog.at_level(logging.WARNING, logger=SECURITY_LOGGER):
            r = raw_client.post("/api/auth/login",
                                json={"username": typed_password, "password": "x"})
        assert r.status_code == 401
        msgs = [rec.getMessage() for rec in caplog.records if "login_failed" in rec.getMessage()]
        assert msgs
        for m in msgs:
            assert typed_password.lower() not in m.lower()
        assert auth_router._redact_username(typed_password.lower()) in msgs[0]

    def test_redaction_is_stable_and_short(self):
        a = auth_router._redact_username("irgendwer")
        assert a == auth_router._redact_username("irgendwer")
        assert a != auth_router._redact_username("irgendwen")
        assert "irgendwer" not in a
        assert len(a) <= 24

    def test_control_chars_are_flattened(self, raw_client, test_user, caplog):
        with caplog.at_level(logging.WARNING, logger=SECURITY_LOGGER):
            raw_client.post("/api/auth/login",
                            json={"username": "x\nAUTH login_success user=admin", "password": "x"})
        for rec in caplog.records:
            assert "\n" not in rec.getMessage()
            assert "\r" not in rec.getMessage()
        assert auth_router._safe_log_text("a\r\nb\x1bc") == "a b c"

    def test_username_max_length(self, raw_client, default_tenant):
        r = raw_client.post("/api/auth/login", json={"username": "a" * 101, "password": "x"})
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# 5 — Kontosperre je (Name, IP) + globale Obergrenze
# ─────────────────────────────────────────────────────────────────────


def _login_from(client, ip, username, password):
    with patch("app.routers.auth._get_real_ip", return_value=ip):
        return client.post("/api/auth/login", json={"username": username, "password": password})


class TestLockoutPerIp:
    def test_lockout_from_one_ip_does_not_lock_other_ip(self, raw_client, test_user):
        for _ in range(auth_router._LOCKOUT_ATTEMPTS):
            assert _login_from(raw_client, "10.0.0.66", "testuser", "falsch").status_code == 401
        assert _login_from(raw_client, "10.0.0.66", "testuser", "falsch").status_code == 429
        # Rechtmaessige Nutzerin an einem anderen Rechner kommt rein.
        ok = _login_from(raw_client, "10.0.0.5", "testuser", TEST_USER_PASSWORD)
        assert ok.status_code == 200, ok.text

    def test_global_cap_per_username(self, raw_client, test_user):
        for i in range(auth_router._GLOBAL_LOCKOUT_ATTEMPTS):
            _login_from(raw_client, f"10.1.{i // 250}.{i % 250}", "testuser", "falsch")
        r = _login_from(raw_client, "10.9.9.9", "testuser", TEST_USER_PASSWORD)
        assert r.status_code == 429

    def test_lockout_for_unknown_name_too(self, raw_client, default_tenant):
        for _ in range(auth_router._LOCKOUT_ATTEMPTS):
            _login_from(raw_client, "10.0.0.7", "gibtsnicht", "falsch")
        assert _login_from(raw_client, "10.0.0.7", "gibtsnicht", "falsch").status_code == 429

    def test_global_cap_is_much_higher(self):
        assert auth_router._GLOBAL_LOCKOUT_ATTEMPTS >= 10 * auth_router._LOCKOUT_ATTEMPTS


# ─────────────────────────────────────────────────────────────────────
# 6 — Selbstauskunft unter Impersonation
# ─────────────────────────────────────────────────────────────────────


class TestExportUnderImpersonation:
    def test_export_forbidden_while_impersonating(self, db, test_user):
        def _override_db():
            yield db

        def _imp_user(request: Request):
            request.state.is_impersonating = True
            return test_user

        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = _imp_user
        r = TestClient(test_app).get("/api/auth/me/export")
        assert r.status_code == 403

    def test_export_allowed_for_own_session(self, db, test_user):
        c = _client_as(db, test_user)
        assert c.get("/api/auth/me/export").status_code == 200
