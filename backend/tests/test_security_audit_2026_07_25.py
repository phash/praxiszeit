"""Security-Audit 2026-07-25 — Regressionstests fuer die drei Findings.

F1 (MEDIUM) ``POST /api/auth/totp/setup`` verlangt jetzt IMMER das Passwort.
    Vorher konnte jeder mit einem gueltigen Access-Token (gestohlenes Token,
    unbeaufsichtigte Session) das TOTP-Secret ueberschreiben bzw. neu setzen:
    der Authenticator des Opfers wurde ungueltig, der des Angreifers gueltig —
    2FA-Uebernahme + Aussperrung ohne Kenntnis des Passworts. ``/totp/disable``
    verlangte das Passwort bereits; der schwaechere setup-Pfad hebelte das aus.

F3 (LOW)  ``GET /api/settings`` (public, no-auth) gibt keine Lizenznehmer-
    Identitaet mehr preis (customer_name / max_employees / days_until_expiry /
    is_expired). Nur noch das nicht-identifizierende ``read_only``-Boolean.

F2 (LOW)  Impersonation-Token traegt ``imp_tv`` (token_version des Admins) und
    wird ungueltig, sobald sich diese aendert (Logout / set-password /
    Rollenwechsel). Zusaetzlich schliesst ``/api/auth/logout`` die offenen
    Impersonation-Sessions des Admins.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.core import totp_crypto
from app.database import get_db
from app.middleware import auth as auth_mw
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, ImpersonationSession
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


TEST_USER_PASSWORD = "testpassword123"  # noqa: S105 — matches the conftest fixture


def _client(db, user, *, admin=False):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    if admin:
        test_app.dependency_overrides[require_admin] = lambda: user
    return TestClient(test_app)


@pytest.fixture
def user_client(db, test_user):
    c = _client(db, test_user)
    yield c
    test_app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db, test_admin):
    c = _client(db, test_admin, admin=True)
    yield c
    test_app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────
# F1 — TOTP-Setup verlangt das Passwort
# ─────────────────────────────────────────────────────────────────────


class TestTotpSetupRequiresPassword:
    def test_setup_without_body_is_rejected(self, user_client, db, test_user):
        """Ohne Body (= altes Verhalten) gibt es kein Secret mehr."""
        r = user_client.post("/api/auth/totp/setup")
        assert r.status_code == 422, r.text
        db.refresh(test_user)
        assert test_user.totp_secret is None

    def test_setup_with_wrong_password_is_rejected(self, user_client, db, test_user):
        r = user_client.post("/api/auth/totp/setup", json={"password": "wrong-password"})
        assert r.status_code == 400, r.text
        db.refresh(test_user)
        assert test_user.totp_secret is None

    def test_setup_with_correct_password_issues_secret(self, user_client, db, test_user):
        r = user_client.post("/api/auth/totp/setup", json={"password": TEST_USER_PASSWORD})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["secret"]
        assert body["otpauth_uri"].startswith("otpauth://totp/")
        db.refresh(test_user)
        # gespeichert wird der Fernet-Ciphertext, nicht der Klartext
        assert test_user.totp_secret is not None
        assert totp_crypto.decrypt_secret(test_user.totp_secret) == body["secret"]

    def test_active_enrollment_survives_a_password_less_takeover_attempt(
        self, user_client, db, test_user
    ):
        """Kernregression: ein aktives 2FA-Enrollment darf ohne Passwort NICHT
        ueberschrieben werden — sonst sperrt ein Angreifer mit gestohlenem
        Access-Token das Opfer aus seinem eigenen Konto aus."""
        original_plain = auth_service.generate_totp_secret()
        test_user.totp_secret = totp_crypto.encrypt_secret(original_plain)
        test_user.totp_enabled = True
        db.commit()

        assert user_client.post("/api/auth/totp/setup").status_code == 422
        assert user_client.post(
            "/api/auth/totp/setup", json={"password": "not-the-password"}
        ).status_code == 400

        db.refresh(test_user)
        assert test_user.totp_enabled is True
        assert totp_crypto.decrypt_secret(test_user.totp_secret) == original_plain

    def test_reenrollment_with_password_is_allowed(self, user_client, db, test_user):
        """Der legitime Weg (Geraetewechsel mit Passwort) bleibt offen."""
        original_plain = auth_service.generate_totp_secret()
        test_user.totp_secret = totp_crypto.encrypt_secret(original_plain)
        test_user.totp_enabled = True
        db.commit()

        r = user_client.post("/api/auth/totp/setup", json={"password": TEST_USER_PASSWORD})
        assert r.status_code == 200, r.text
        db.refresh(test_user)
        assert totp_crypto.decrypt_secret(test_user.totp_secret) == r.json()["secret"]
        assert totp_crypto.decrypt_secret(test_user.totp_secret) != original_plain


# ─────────────────────────────────────────────────────────────────────
# F3 — /api/settings leakt keine Lizenznehmer-Identitaet
# ─────────────────────────────────────────────────────────────────────


class TestPublicSettingsLicenseDisclosure:
    def _info(self, **kw):
        from app.core.license import LicenseInfo
        base = dict(customer_id="cust-1", customer_name="Praxis Dr. Müller", max_employees=25)
        base.update(kw)
        return LicenseInfo(**base)

    def test_no_license_loaded_returns_none(self):
        from app.main import _public_license_state
        with patch("app.core.license.get_current_license", return_value=None):
            assert _public_license_state() is None

    def test_only_read_only_boolean_is_exposed(self):
        from app.main import _public_license_state
        with patch("app.core.license.get_current_license", return_value=self._info()), \
             patch("app.core.license.is_read_only", return_value=True):
            state = _public_license_state()
        assert state == {"read_only": True}

    def test_identifying_fields_are_never_exposed(self):
        """Explizite Negativliste — verhindert ein versehentliches Wieder-
        Hinzufuegen der Praxis-Identitaet auf dem no-auth-Endpoint."""
        from app.main import _public_license_state
        with patch("app.core.license.get_current_license", return_value=self._info()), \
             patch("app.core.license.is_read_only", return_value=False):
            state = _public_license_state()
        for leaked in ("customer_name", "customer_id", "max_employees",
                       "days_until_expiry", "is_expired"):
            assert leaked not in state


# ─────────────────────────────────────────────────────────────────────
# F2 — Impersonation-Token an die token_version des Admins gebunden
# ─────────────────────────────────────────────────────────────────────


def _mk_employee(db, username="imp_target"):
    u = User(
        username=username, email=f"{username}@x.de",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name=username, last_name="Test", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _resolve(db, token):
    """Ruft das echte ``get_current_user`` auf (RLS-Setter gepatcht — SQLite
    kennt kein SET LOCAL)."""
    req = SimpleNamespace(state=SimpleNamespace())
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with patch("app.middleware.auth.set_superadmin_context"), \
         patch("app.middleware.auth.set_tenant_context"):
        return auth_mw.get_current_user(request=req, credentials=creds, db=db)


class TestImpersonationTokenVersionBinding:
    def test_token_carries_imp_tv_claim(self):
        token = auth_service.create_access_token(
            user_id=str(uuid.uuid4()), role="employee", tenant_id=str(DEFAULT_TENANT_ID),
            impersonator_id=str(uuid.uuid4()), impersonation_session_id=str(uuid.uuid4()),
            impersonator_token_version=7,
        )
        assert auth_service.decode_token(token)["imp_tv"] == 7

    def test_normal_token_has_no_imp_tv(self):
        token = auth_service.create_access_token(
            user_id=str(uuid.uuid4()), role="employee", tenant_id=str(DEFAULT_TENANT_ID),
        )
        assert "imp_tv" not in auth_service.decode_token(token)

    def test_start_impersonation_stamps_current_admin_token_version(
        self, admin_client, db, test_admin
    ):
        test_admin.token_version = 3
        db.commit()
        emp = _mk_employee(db, "imp_tv_emp")
        r = admin_client.post(f"/api/admin/users/{emp.id}/impersonate")
        assert r.status_code == 200, r.text
        assert auth_service.decode_token(r.json()["access_token"])["imp_tv"] == 3

    def test_validate_impersonator_rejects_stale_token_version(self, db, test_admin):
        test_admin.token_version = 5
        db.commit()
        with pytest.raises(HTTPException) as exc:
            auth_mw.validate_impersonator(test_admin, test_admin.tenant_id, 4)
        assert exc.value.status_code == 401

    def test_validate_impersonator_rejects_missing_token_version(self, db, test_admin):
        """Alt-Tokens ohne ``imp_tv`` sind fail-closed (30-Min-Fenster beim Deploy)."""
        with pytest.raises(HTTPException) as exc:
            auth_mw.validate_impersonator(test_admin, test_admin.tenant_id, None)
        assert exc.value.status_code == 401

    def test_impersonation_token_dies_when_admin_logs_out(
        self, admin_client, db, test_admin
    ):
        emp = _mk_employee(db, "imp_logout_emp")
        r = admin_client.post(f"/api/admin/users/{emp.id}/impersonate")
        token = r.json()["access_token"]

        # solange die Admin-Session lebt, loest das Token den Mitarbeiter auf
        assert _resolve(db, token).id == emp.id

        # Logout des Admins (bumpt dessen token_version)
        assert admin_client.post("/api/auth/logout").status_code == 200
        db.refresh(test_admin)

        with pytest.raises(HTTPException) as exc:
            _resolve(db, token)
        assert exc.value.status_code == 401

    def test_logout_closes_open_impersonation_sessions(
        self, admin_client, db, test_admin
    ):
        emp = _mk_employee(db, "imp_close_emp")
        admin_client.post(f"/api/admin/users/{emp.id}/impersonate")
        session = (
            db.query(ImpersonationSession)
            .filter(ImpersonationSession.impersonator_id == test_admin.id)
            .first()
        )
        assert session is not None and session.ended_at is None

        assert admin_client.post("/api/auth/logout").status_code == 200

        db.refresh(session)
        assert session.ended_at is not None
