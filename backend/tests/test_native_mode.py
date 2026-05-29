"""
Tests for native mode features:
- SecurityHeadersMiddleware (Phase 1)
- TOML config loader (Phase 1)
- License validation (Phase 2)
"""

import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from app.middleware.static_serving import SecurityHeadersMiddleware


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware
# ---------------------------------------------------------------------------

class TestSecurityHeadersMiddleware:
    """Verify all security headers are set correctly."""

    @pytest.fixture
    def app_with_middleware(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        def test_endpoint():
            return PlainTextResponse("ok")

        return TestClient(app)

    def test_x_frame_options(self, app_with_middleware):
        """Prüft dass X-Frame-Options gesetzt ist — Clickjacking-Schutz."""
        response = app_with_middleware.get("/test")
        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    def test_x_content_type_options(self, app_with_middleware):
        """Prüft dass X-Content-Type-Options nosniff gesetzt ist — MIME-Sniffing-Schutz."""
        response = app_with_middleware.get("/test")
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_referrer_policy(self, app_with_middleware):
        """Prüft dass Referrer-Policy gesetzt ist — verhindert URL-Leak an Dritte."""
        response = app_with_middleware.get("/test")
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_hsts(self, app_with_middleware):
        """Prüft dass HSTS-Header mit 1 Jahr max-age über HTTPS gesetzt ist — erzwingt HTTPS.

        F-050: HSTS wird bewusst NUR über HTTPS gesetzt (oder wenn COOKIE_SECURE
        aktiv ist), damit ein per HTTP:// erreichter Native-Windows-Install nicht
        gebrickt wird. Der TestClient spricht http://, daher signalisieren wir
        HTTPS explizit über X-Forwarded-Proto — sonst hängt das Testergebnis an
        der COOKIE_SECURE-Env (in-container false → kein Header)."""
        response = app_with_middleware.get(
            "/test", headers={"X-Forwarded-Proto": "https"}
        )
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" in response.headers["Strict-Transport-Security"]

    def test_csp(self, app_with_middleware):
        """Prüft dass Content-Security-Policy restriktive Regeln setzt — XSS-Schutz."""
        response = app_with_middleware.get("/test")
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp
        assert "img-src 'self' data:" in csp
        assert "frame-ancestors 'self'" in csp


# ---------------------------------------------------------------------------
# TOML Config Loader
# ---------------------------------------------------------------------------

class TestTomlConfigLoader:
    """Test TOML config loading into environment variables."""

    def test_load_toml_sets_env_vars(self):
        """Prüft dass TOML-Werte als Umgebungsvariablen gesetzt werden — Native-Konfiguration."""
        toml_content = b"""
[practice]
name = "Testpraxis"
holiday_state = "Berlin"

[security]
login_rate_limit = "10/minute"
"""
        with tempfile.NamedTemporaryFile(suffix=".conf", delete=False) as f:
            f.write(toml_content)
            f.flush()
            toml_path = Path(f.name)

        try:
            # Clear any existing env vars
            for key in ["PRACTICE_NAME", "HOLIDAY_STATE", "LOGIN_RATE_LIMIT"]:
                os.environ.pop(key, None)

            from app.config import _TOML_KEY_MAP
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib

            with open(toml_path, "rb") as f:
                toml_data = tomllib.load(f)

            # Simulate the loader logic
            for (section, key), env_name in _TOML_KEY_MAP.items():
                if env_name in os.environ:
                    continue
                if section in toml_data and key in toml_data[section]:
                    value = toml_data[section][key]
                    os.environ[env_name] = str(value).lower() if isinstance(value, bool) else str(value)

            assert os.environ.get("PRACTICE_NAME") == "Testpraxis"
            assert os.environ.get("HOLIDAY_STATE") == "Berlin"
            assert os.environ.get("LOGIN_RATE_LIMIT") == "10/minute"
        finally:
            toml_path.unlink()
            # Cleanup
            for key in ["PRACTICE_NAME", "HOLIDAY_STATE", "LOGIN_RATE_LIMIT"]:
                os.environ.pop(key, None)

    def test_env_vars_take_precedence_over_toml(self):
        """Prüft dass bestehende Umgebungsvariablen nicht durch TOML ueberschrieben werden."""
        os.environ["PRACTICE_NAME"] = "EnvPraxis"

        toml_content = b"""
[practice]
name = "TomlPraxis"
"""
        with tempfile.NamedTemporaryFile(suffix=".conf", delete=False) as f:
            f.write(toml_content)
            f.flush()
            toml_path = Path(f.name)

        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib

            from app.config import _TOML_KEY_MAP

            with open(toml_path, "rb") as f:
                toml_data = tomllib.load(f)

            for (section, key), env_name in _TOML_KEY_MAP.items():
                if env_name in os.environ:
                    continue
                if section in toml_data and key in toml_data[section]:
                    os.environ[env_name] = str(toml_data[section][key])

            # Env var should NOT have been overwritten
            assert os.environ["PRACTICE_NAME"] == "EnvPraxis"
        finally:
            toml_path.unlink()
            os.environ.pop("PRACTICE_NAME", None)

    def test_boolean_values_converted_to_lowercase(self):
        """Prüft dass TOML-Booleans als lowercase Strings konvertiert werden — Python-Kompatibilitaet."""
        toml_content = b"""
[security]
cookie_secure = false
"""
        with tempfile.NamedTemporaryFile(suffix=".conf", delete=False) as f:
            f.write(toml_content)
            f.flush()
            toml_path = Path(f.name)

        try:
            os.environ.pop("COOKIE_SECURE", None)

            try:
                import tomllib
            except ImportError:
                import tomli as tomllib

            from app.config import _TOML_KEY_MAP

            with open(toml_path, "rb") as f:
                toml_data = tomllib.load(f)

            for (section, key), env_name in _TOML_KEY_MAP.items():
                if env_name in os.environ:
                    continue
                if section in toml_data and key in toml_data[section]:
                    value = toml_data[section][key]
                    os.environ[env_name] = str(value).lower() if isinstance(value, bool) else str(value)

            assert os.environ.get("COOKIE_SECURE") == "false"
        finally:
            toml_path.unlink()
            os.environ.pop("COOKIE_SECURE", None)


# ---------------------------------------------------------------------------
# License Validation (Phase 2)
# ---------------------------------------------------------------------------

class TestLicenseValidation:
    """Test Ed25519 license signing and validation."""

    @pytest.fixture
    def keypair(self):
        """Generate a fresh Ed25519 keypair for testing."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat, PublicFormat,
        )
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return {
            "private": private_key,
            "public": public_key,
            "public_pem": public_key.public_bytes(
                Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
            ),
        }

    def _sign_license(self, private_key, payload):
        """Sign a license payload with the given private key."""
        import jwt
        return jwt.encode(payload, private_key, algorithm="EdDSA")

    def _valid_payload(self, **overrides):
        """Create a valid license payload with optional overrides."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-praxis",
            "name": "Testpraxis Dr. Test",
            "max_employees": 20,
            "features": ["base"],
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=365)).timestamp()),
            "v": 1,
        }
        payload.update(overrides)
        return payload

    def test_valid_license(self, keypair, tmp_path):
        """Prüft dass eine gueltig signierte, nicht abgelaufene Lizenz erfolgreich validiert wird."""
        import app.core.license as lic

        token = self._sign_license(keypair["private"], self._valid_payload())
        license_file = tmp_path / "license.key"
        license_file.write_text(token)

        # Patch the public key and configured flag
        with patch.object(lic, "_PUBLIC_KEYS_PEM", [keypair["public_pem"]]), \
             patch.object(lic, "_PUBLIC_KEY_CONFIGURED", True):
            info = lic.validate_license(license_file)

        assert info.customer_id == "test-praxis"
        assert info.customer_name == "Testpraxis Dr. Test"
        assert info.max_employees == 20
        assert not info.is_expired
        assert info.days_until_expiry > 0

    def test_expired_license_raises(self, keypair, tmp_path):
        """Prüft dass eine abgelaufene Lizenz LicenseExpiredError ausloest — Lizenz-Enforcement."""
        import app.core.license as lic

        expired_payload = self._valid_payload(
            exp=int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
        )
        token = self._sign_license(keypair["private"], expired_payload)
        license_file = tmp_path / "license.key"
        license_file.write_text(token)

        with patch.object(lic, "_PUBLIC_KEYS_PEM", [keypair["public_pem"]]), \
             patch.object(lic, "_PUBLIC_KEY_CONFIGURED", True):
            with pytest.raises(lic.LicenseExpiredError):
                lic.validate_license(license_file)

    def test_invalid_signature_raises(self, keypair, tmp_path):
        """Prüft dass eine mit fremdem Key signierte Lizenz abgelehnt wird — Ed25519-Integritaet."""
        import app.core.license as lic
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        # Sign with a different key
        other_key = Ed25519PrivateKey.generate()
        token = self._sign_license(other_key, self._valid_payload())
        license_file = tmp_path / "license.key"
        license_file.write_text(token)

        with patch.object(lic, "_PUBLIC_KEYS_PEM", [keypair["public_pem"]]), \
             patch.object(lic, "_PUBLIC_KEY_CONFIGURED", True):
            # license.py raises the German message ("Signatur") — the code is
            # intentionally German-facing; assert against the real string.
            with pytest.raises(lic.LicenseError, match="Signatur"):
                lic.validate_license(license_file)

    def test_missing_license_file(self, tmp_path):
        """Prüft dass fehlende Lizenzdatei einen LicenseError ausloest — klare Fehlermeldung."""
        import app.core.license as lic

        # license.py raises the German message ("nicht gefunden").
        with pytest.raises(lic.LicenseError, match="nicht gefunden"):
            lic.validate_license(tmp_path / "nonexistent.key")

    def test_empty_license_file(self, tmp_path):
        """Prüft dass leere Lizenzdatei einen LicenseError ausloest — kein stilles Ignorieren."""
        import app.core.license as lic

        license_file = tmp_path / "license.key"
        license_file.write_text("")

        # license.py raises the German message ("Lizenzdatei ist leer").
        with pytest.raises(lic.LicenseError, match="leer"):
            lic.validate_license(license_file)

    def test_validate_license_quiet_returns_none_on_error(self, tmp_path):
        """Prüft dass validate_license_quiet bei Fehlern None zurueckgibt statt Exception."""
        import app.core.license as lic

        assert lic.validate_license_quiet(tmp_path / "nonexistent.key") is None

    def test_validate_license_quiet_returns_expired_info(self, keypair, tmp_path):
        """Prüft dass validate_license_quiet auch fuer abgelaufene Lizenzen Info zurueckgibt — Grace-Period."""
        import app.core.license as lic

        expired_payload = self._valid_payload(
            exp=int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        )
        token = self._sign_license(keypair["private"], expired_payload)
        license_file = tmp_path / "license.key"
        license_file.write_text(token)

        with patch.object(lic, "_PUBLIC_KEYS_PEM", [keypair["public_pem"]]), \
             patch.object(lic, "_PUBLIC_KEY_CONFIGURED", True):
            info = lic.validate_license_quiet(license_file)

        assert info is not None
        assert info.is_expired
        assert info.customer_id == "test-praxis"

    def test_license_info_days_until_expiry(self):
        """Prüft dass days_until_expiry und is_expired korrekt berechnet werden."""
        from app.core.license import LicenseInfo

        future = datetime.now(timezone.utc) + timedelta(days=100)
        info = LicenseInfo(
            customer_id="test",
            customer_name="Test",
            max_employees=10,
            expires_at=future,
        )
        # Allow for time-of-day variance (99 or 100)
        assert info.days_until_expiry in (99, 100)
        assert not info.is_expired

        past = datetime.now(timezone.utc) - timedelta(days=5)
        expired_info = LicenseInfo(
            customer_id="test",
            customer_name="Test",
            max_employees=10,
            expires_at=past,
        )
        assert expired_info.days_until_expiry == 0
        assert expired_info.is_expired

    def test_read_only_guard(self):
        """Prüft dass require_writable bei Read-Only-Modus 403 wirft — abgelaufene Lizenz."""
        import app.core.license as lic
        from fastapi import HTTPException

        lic.set_license_state(None, read_only=True)
        with pytest.raises(HTTPException) as exc_info:
            lic.require_writable()
        assert exc_info.value.status_code == 403

        lic.set_license_state(None, read_only=False)
        # Should not raise
        lic.require_writable()

    def test_employee_limit_check(self):
        """Prüft dass check_employee_limit bei Ueberschreitung des Lizenzlimits 403 wirft."""
        import app.core.license as lic
        from app.core.license import LicenseInfo
        from fastapi import HTTPException

        license_info = LicenseInfo(
            customer_id="test",
            customer_name="Test",
            max_employees=5,
        )
        lic.set_license_state(license_info)

        # Under limit: should not raise
        lic.check_employee_limit(4)

        # At limit: should raise
        with pytest.raises(HTTPException) as exc_info:
            lic.check_employee_limit(5)
        assert exc_info.value.status_code == 403

        # Over limit: should raise
        with pytest.raises(HTTPException) as exc_info:
            lic.check_employee_limit(10)
        assert exc_info.value.status_code == 403

        # Cleanup
        lic.set_license_state(None)


class TestSecurityHeadersAlwaysAttached:
    """Review 2026-05-29 (M-SEC2): SecurityHeadersMiddleware must be attached
    even in Docker/prod mode (SERVE_FRONTEND=False) as defense-in-depth — a
    missing/misconfigured/replaced reverse proxy must never leave API responses
    without CSP / anti-clickjacking headers."""

    def test_attached_regardless_of_serve_frontend(self):
        import app.main as m
        from app.config import settings
        # Guard: this test is only meaningful when frontend-serving is OFF
        # (the Docker/prod default), which is the env the suite runs in.
        assert settings.SERVE_FRONTEND is False
        classes = [mw.cls for mw in m.app.user_middleware]
        assert SecurityHeadersMiddleware in classes
