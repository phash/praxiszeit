"""Audit 2026-11-07 (#543): Konten, Anmeldung, 2FA, Sicherungen.

S1-02 Sicherungen: Download nur mit Passwort, jede Aktion in ``security_events``.
S1-03 Konto angelegt / Benutzername geändert → ``security_events``.
S1-04 2FA: persistente Obergrenze je Konto, Fehlversuche in ``security_events``.
S1-05 2FA: Zähler atomar beansprucht (paralleler Replay).
S1-06 Passwort-Rückfragen (Passwort ändern, 2FA) unter der Login-Sperre.
S1-07 Geräte-Cookie: fremde Fehlversuche sperren einen bekannten Browser nicht aus.
S1-08 „Login als"-Sitzungen enden spätestens mit dem Token.
S1-09 Verwaltung setzt die 2FA einer anderen Person zurück.
"""
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.core import totp_crypto
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import ImpersonationSession, User, UserRole
from app.models import security_event as se
from app.models.security_event import SecurityEvent
from app.routers import auth as auth_router
from app.routers import impersonation as imp_router
from app.services import auth_service
from app.services import backup_service as bs
from tests.conftest import DEFAULT_TENANT_ID, TestingSessionLocal
from tests.test_endpoints import test_app

USER_PW = "testpassword123"  # noqa: S105 — conftest fixture
ADMIN_PW = "adminpassword123"  # noqa: S105 — conftest fixture


@pytest.fixture(autouse=True)
def _clean():
    auth_router._failed_logins.clear()
    yield
    test_app.dependency_overrides.clear()
    auth_router._failed_logins.clear()


@pytest.fixture
def raw_client(db):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    with patch("app.routers.auth.set_superadmin_context"), \
         patch("app.middleware.auth.set_superadmin_context"), \
         patch("app.middleware.auth.set_tenant_context"):
        with TestClient(test_app) as c:
            yield c


def _client_as(db, user, *, admin=False):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    if admin:
        test_app.dependency_overrides[require_admin] = lambda: user
    return TestClient(test_app)


def _login(client, ip, username, password, totp=None, device=None):
    body = {"username": username, "password": password}
    if totp is not None:
        body["totp_code"] = totp
    cookies = {"pz_device": device} if device else None
    with patch("app.routers.auth._get_real_ip", return_value=ip):
        if cookies:
            client.cookies.set("pz_device", device)
        r = client.post("/api/auth/login", json=body)
        client.cookies.clear()
        return r


def _device_cookie(response) -> str:
    for header in response.headers.get_list("set-cookie"):
        m = re.match(r"pz_device=([^;]+)", header)
        if m:
            return m.group(1)
    raise AssertionError("kein Geräte-Cookie gesetzt")


def _enable_totp(db, user):
    secret = auth_service.generate_totp_secret()
    user.totp_secret = totp_crypto.encrypt_secret(secret)
    user.totp_enabled = True
    user.last_totp_counter = None
    db.commit()
    return secret


def _events(db, event):
    return db.query(SecurityEvent).filter(SecurityEvent.event == event).all()


def _wrong(code):
    return "000000" if code != "000000" else "111111"


# ── S1-07: Geräte-Cookie ─────────────────────────────────────────────


class TestDeviceCookie:
    def _flood(self, client, username):
        for i in range(auth_router._GLOBAL_LOCKOUT_ATTEMPTS):
            _login(client, f"10.7.{i // 250}.{i % 250}", username, "falsch")

    def test_known_browser_passes_global_lock(self, raw_client, test_user):
        ok = _login(raw_client, "10.0.0.5", "testuser", USER_PW)
        assert ok.status_code == 200, ok.text
        device = _device_cookie(ok)
        self._flood(raw_client, "testuser")
        # Ohne Geräte-Cookie: gesperrt (Brute-Force-Grenze bleibt) ...
        assert _login(raw_client, "10.0.0.5", "testuser", USER_PW).status_code == 429
        # ... der bekannte Browser kommt durch.
        r = _login(raw_client, "10.0.0.5", "testuser", USER_PW, device=device)
        assert r.status_code == 200, r.text

    def test_known_browser_passes_shared_proxy_ip_lock(self, raw_client, test_user):
        ok = _login(raw_client, "172.17.0.1", "testuser", USER_PW)
        device = _device_cookie(ok)
        for _ in range(auth_router._LOCKOUT_ATTEMPTS):
            _login(raw_client, "172.17.0.1", "testuser", "falsch")
        assert _login(raw_client, "172.17.0.1", "testuser", USER_PW).status_code == 429
        assert _login(raw_client, "172.17.0.1", "testuser", USER_PW, device=device).status_code == 200

    def test_device_has_own_small_budget(self, raw_client, test_user):
        device = _device_cookie(_login(raw_client, "10.0.0.5", "testuser", USER_PW))
        self._flood(raw_client, "testuser")
        for _ in range(auth_router._LOCKOUT_ATTEMPTS):
            assert _login(raw_client, "10.0.0.5", "testuser", "falsch",
                          device=device).status_code == 401
        assert _login(raw_client, "10.0.0.5", "testuser", USER_PW,
                      device=device).status_code == 429

    def test_device_of_other_account_does_not_unlock(self, raw_client, test_user, test_admin):
        device = _device_cookie(_login(raw_client, "10.0.0.5", "adminuser", ADMIN_PW))
        self._flood(raw_client, "testuser")
        assert _login(raw_client, "10.0.0.5", "testuser", USER_PW,
                      device=device).status_code == 429

    def test_forged_device_cookie_is_ignored(self, raw_client, test_user):
        self._flood(raw_client, "testuser")
        forged = f"{test_user.id}.abc.{'0' * 32}"
        assert _login(raw_client, "10.0.0.5", "testuser", USER_PW,
                      device=forged).status_code == 429


# ── S1-04 / S1-05: 2FA ───────────────────────────────────────────────


class TestTotpHardening:
    def test_wrong_code_writes_security_event(self, raw_client, db, test_user):
        secret = _enable_totp(db, test_user)
        r = _login(raw_client, "10.0.0.9", "testuser", USER_PW,
                   totp=_wrong(pyotp.TOTP(secret).now()))
        assert r.status_code == 401
        rows = _events(db, se.EVENT_TOTP_FAILED)
        assert len(rows) == 1
        assert rows[0].subject_user_id == test_user.id
        assert rows[0].actor == "login:10.0.0.9"

    def test_persistent_cap_survives_restart(self, raw_client, db, test_user):
        secret = _enable_totp(db, test_user)
        for i in range(auth_router._TOTP_FAILURE_LIMIT):
            # je eigene IP: die IP-Sperre (5) greift so nicht vorher
            _login(raw_client, f"10.3.0.{i}", "testuser", USER_PW,
                   totp=_wrong(pyotp.TOTP(secret).now()))
        assert len(_events(db, se.EVENT_TOTP_LOCKED)) == 1
        auth_router._failed_logins.clear()  # Neustart: In-Memory-Zähler weg
        r = _login(raw_client, "10.4.0.1", "testuser", USER_PW, totp=pyotp.TOTP(secret).now())
        assert r.status_code == 429
        assert r.json()["detail"] == auth_router.TOTP_LOCKED_DETAIL

    def test_old_failures_fall_out_of_window(self, raw_client, db, test_user):
        secret = _enable_totp(db, test_user)
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        for _ in range(auth_router._TOTP_FAILURE_LIMIT):
            db.add(SecurityEvent(tenant_id=DEFAULT_TENANT_ID, event=se.EVENT_TOTP_FAILED,
                                 subject_user_id=test_user.id, actor="login:x", created_at=old))
        db.commit()
        r = _login(raw_client, "10.4.0.2", "testuser", USER_PW, totp=pyotp.TOTP(secret).now())
        assert r.status_code == 200, r.text

    def test_claim_counter_is_atomic_against_stale_read(self, db, test_user):
        """Zwei Anfragen lesen denselben alten Zähler; nur eine gewinnt."""
        _enable_totp(db, test_user)
        other = TestingSessionLocal()
        try:
            stale = other.get(User, test_user.id)  # liest last_totp_counter = None
            assert stale.last_totp_counter is None
            assert auth_router.claim_totp_counter(db, test_user, 1000) is True
            db.commit()
            # Die zweite Anfrage hat den alten Stand im Speicher — trotzdem 0 Zeilen.
            assert auth_router.claim_totp_counter(other, stale, 1000) is False
            assert auth_router.claim_totp_counter(other, stale, 1001) is True
            other.commit()
        finally:
            other.close()

    def test_login_rejects_code_claimed_in_parallel(self, raw_client, db, test_user):
        secret = _enable_totp(db, test_user)
        code = pyotp.TOTP(secret).now()
        counter = auth_service.verify_totp_with_counter(secret, code, None)
        real_verify = auth_service.verify_totp_with_counter

        def _verify_then_race(sec, c, last):
            accepted = real_verify(sec, c, last)
            # Die parallele Anmeldung beansprucht denselben Zähler zuerst.
            s2 = TestingSessionLocal()
            s2.query(User).filter(User.id == test_user.id).update(
                {User.last_totp_counter: counter}, synchronize_session=False)
            s2.commit()
            s2.close()
            return accepted

        with patch.object(auth_router.auth_service, "verify_totp_with_counter", _verify_then_race):
            r = _login(raw_client, "10.0.0.11", "testuser", USER_PW, totp=code)
        assert r.status_code == 401, r.text

    def test_disable_wrong_code_counts(self, db, test_user):
        secret = _enable_totp(db, test_user)
        c = _client_as(db, test_user)
        r = c.request("DELETE", "/api/auth/totp/disable",
                      json={"password": USER_PW, "code": _wrong(pyotp.TOTP(secret).now())})
        assert r.status_code == 400
        assert len(_events(db, se.EVENT_TOTP_FAILED)) == 1


# ── S1-06: Passwort-Rückfragen unter der Login-Sperre ────────────────


class TestPasswordStepUp:
    @pytest.mark.parametrize("method,path,field", [
        ("POST", "/api/auth/change-password", "current_password"),
        ("POST", "/api/auth/totp/setup", "password"),
    ])
    def test_wrong_password_locks_and_revokes(self, db, test_user, method, path, field):
        c = _client_as(db, test_user)
        before = test_user.token_version or 0
        body = {field: "falsch"}
        if field == "current_password":
            body["new_password"] = "NeuesPasswort2026"
        with patch("app.routers.auth._get_real_ip", return_value="10.5.0.1"), \
             patch.object(auth_router.limiter, "enabled", False):
            codes = [c.request(method, path, json=body).status_code
                     for _ in range(auth_router._LOCKOUT_ATTEMPTS)]
            assert codes[:-1] == [400] * (auth_router._LOCKOUT_ATTEMPTS - 1)
            assert codes[-1] == 429
            # danach auch mit dem richtigen Passwort gesperrt
            body[field] = USER_PW
            assert c.request(method, path, json=body).status_code == 429
        db.refresh(test_user)
        assert test_user.token_version == before + 1
        assert len(_events(db, se.EVENT_PASSWORD_CHECK_LOCKOUT)) == 1

    def test_step_up_failures_count_into_login_lock(self, raw_client, db, test_user):
        c = _client_as(db, test_user)
        with patch("app.routers.auth._get_real_ip", return_value="10.5.0.2"), \
             patch.object(auth_router.limiter, "enabled", False):
            for _ in range(auth_router._LOCKOUT_ATTEMPTS - 1):
                c.post("/api/auth/totp/setup", json={"password": "falsch"})
        test_app.dependency_overrides.pop(get_current_user, None)
        assert _login(raw_client, "10.5.0.2", "testuser", "falsch").status_code == 401
        assert _login(raw_client, "10.5.0.2", "testuser", USER_PW).status_code == 429


# ── S1-08: „Login als"-Sitzungen ─────────────────────────────────────


class TestImpersonationExpiry:
    def _session(self, db, admin, user, minutes_ago):
        s = ImpersonationSession(tenant_id=DEFAULT_TENANT_ID, impersonator_id=admin.id,
                                 target_id=user.id,
                                 started_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    def test_open_session_ends_with_token(self, db, test_admin, test_user):
        s = self._session(db, test_admin, test_user, 120)
        end = imp_router.effective_ended_at(s)
        assert end is not None
        started = s.started_at if s.started_at.tzinfo else s.started_at.replace(tzinfo=timezone.utc)
        assert end == started + imp_router.impersonation_token_lifetime()

    def test_running_session_stays_open(self, db, test_admin, test_user):
        s = self._session(db, test_admin, test_user, 5)
        assert imp_router.effective_ended_at(s) is None

    def test_next_login_closes_expired_sessions(self, raw_client, db, test_admin, test_user):
        old = self._session(db, test_admin, test_user, 120)
        running = self._session(db, test_admin, test_user, 5)
        assert _login(raw_client, "10.0.0.20", "adminuser", ADMIN_PW).status_code == 200
        db.expire_all()
        assert db.get(ImpersonationSession, old.id).ended_at is not None
        assert db.get(ImpersonationSession, running.id).ended_at is None

    def test_list_shows_token_expiry_for_closed_tab(self, db, test_admin, test_user):
        self._session(db, test_admin, test_user, 120)
        c = _client_as(db, test_admin, admin=True)
        rows = c.get("/api/admin/impersonation-sessions").json()
        assert rows[0]["ended_at"] is not None


# ── S1-09: 2FA zurücksetzen durch die Verwaltung ─────────────────────


class TestAdminTotpReset:
    def test_reset_with_password(self, db, test_admin, test_user):
        _enable_totp(db, test_user)
        before = test_user.token_version or 0
        c = _client_as(db, test_admin, admin=True)
        r = c.post(f"/api/admin/users/{test_user.id}/totp-reset", json={"password": ADMIN_PW})
        assert r.status_code == 200, r.text
        db.refresh(test_user)
        assert test_user.totp_enabled is False
        assert test_user.totp_secret is None
        assert test_user.token_version == before + 1
        rows = _events(db, se.EVENT_TOTP_RESET_BY_ADMIN)
        assert len(rows) == 1
        assert rows[0].subject_user_id == test_user.id
        assert rows[0].actor == f"user:{test_admin.id}"

    def test_wrong_password_refused(self, db, test_admin, test_user):
        _enable_totp(db, test_user)
        c = _client_as(db, test_admin, admin=True)
        r = c.post(f"/api/admin/users/{test_user.id}/totp-reset", json={"password": "falsch"})
        assert r.status_code == 400
        db.refresh(test_user)
        assert test_user.totp_enabled is True
        assert _events(db, se.EVENT_TOTP_RESET_BY_ADMIN) == []

    def test_not_for_own_account(self, db, test_admin):
        _enable_totp(db, test_admin)
        c = _client_as(db, test_admin, admin=True)
        r = c.post(f"/api/admin/users/{test_admin.id}/totp-reset", json={"password": ADMIN_PW})
        assert r.status_code == 400

    def test_employee_forbidden(self, db, test_user, test_admin):
        def _odb():
            yield db
        test_app.dependency_overrides[get_db] = _odb
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        r = TestClient(test_app).post(f"/api/admin/users/{test_admin.id}/totp-reset",
                                      json={"password": USER_PW})
        assert r.status_code == 403


# ── S1-03: Konto angelegt / umbenannt ────────────────────────────────


class TestAccountEvents:
    def test_create_user_logged_with_role(self, db, test_admin):
        c = _client_as(db, test_admin, admin=True)
        r = c.post("/api/admin/users", json={
            "username": "neueradmin", "password": "SicheresPasswort2026", "first_name": "N",
            "last_name": "A", "role": "admin", "weekly_hours": 40, "vacation_days": 30,
            "work_days_per_week": 5})
        assert r.status_code in (200, 201), r.text
        rows = _events(db, se.EVENT_USER_CREATED)
        assert len(rows) == 1
        assert "Admin" in rows[0].detail
        assert rows[0].actor == f"user:{test_admin.id}"

    def test_username_change_logged(self, db, test_admin, test_user):
        c = _client_as(db, test_admin, admin=True)
        r = c.put(f"/api/admin/users/{test_user.id}", json={"username": "umbenannt"})
        assert r.status_code == 200, r.text
        rows = _events(db, se.EVENT_USERNAME_CHANGED)
        assert len(rows) == 1 and rows[0].subject_user_id == test_user.id
        # gleicher Name: keine Zeile
        c.put(f"/api/admin/users/{test_user.id}", json={"username": "umbenannt"})
        assert len(_events(db, se.EVENT_USERNAME_CHANGED)) == 1


# ── S1-02: Sicherungen ───────────────────────────────────────────────


class TestBackupAccountability:
    @pytest.fixture
    def backups(self, db, test_admin, tmp_path, monkeypatch):
        monkeypatch.delenv("PRAXISZEIT_BACKUP_DIR", raising=False)
        bs.update_config(db, location=str(tmp_path))
        f = tmp_path / "praxiszeit_20260101_010101.sql.gz"
        f.write_bytes(b"dump")
        return _client_as(db, test_admin, admin=True), f

    def test_get_download_is_gone(self, backups):
        c, f = backups
        assert c.get(f"/api/admin/backups/{f.name}/download").status_code == 405

    def test_download_requires_password(self, backups, db):
        c, f = backups
        r = c.post(f"/api/admin/backups/{f.name}/download", json={"password": "falsch"})
        assert r.status_code == 400
        assert _events(db, se.EVENT_BACKUP_DOWNLOADED) == []
        assert c.post(f"/api/admin/backups/{f.name}/download", json={}).status_code == 422

    def test_download_with_password_is_logged(self, backups, db, test_admin):
        c, f = backups
        r = c.post(f"/api/admin/backups/{f.name}/download", json={"password": ADMIN_PW})
        assert r.status_code == 200, r.text
        assert r.content == b"dump"
        rows = _events(db, se.EVENT_BACKUP_DOWNLOADED)
        assert len(rows) == 1
        assert f.name in rows[0].detail
        assert rows[0].actor == f"user:{test_admin.id}"

    def test_delete_and_config_are_logged(self, backups, db, tmp_path):
        c, f = backups
        assert c.delete(f"/api/admin/backups/{f.name}").status_code == 204
        assert len(_events(db, se.EVENT_BACKUP_DELETED)) == 1
        r = c.put("/api/admin/backups/config", json={"enabled": True, "hour": 4})
        assert r.status_code == 200
        rows = _events(db, se.EVENT_BACKUP_CONFIG_CHANGED)
        assert len(rows) == 1 and "Uhrzeit" in rows[0].detail
        # unverändert speichern: keine Zeile
        c.put("/api/admin/backups/config", json={"enabled": True, "hour": 4})
        assert len(_events(db, se.EVENT_BACKUP_CONFIG_CHANGED)) == 1

    def test_create_is_logged(self, backups, db, monkeypatch):
        c, _ = backups
        from tests.test_admin_backups_router import _FakePopen
        _scheme = "postgresql://"
        monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _scheme + "su:pw@db:5432/praxiszeit")
        monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen())
        r = c.post("/api/admin/backups")
        assert r.status_code == 201, r.text
        rows = _events(db, se.EVENT_BACKUP_CREATED)
        assert len(rows) == 1 and r.json()["filename"] in rows[0].detail
