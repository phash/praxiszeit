"""Tests for auth service (TOTP, password hashing)."""
import pytest
import pyotp
from app.services.auth_service import (
    generate_totp_secret,
    get_totp_uri,
    verify_totp,
    hash_password,
    verify_password,
)


class TestGenerateTotpSecret:
    """Test generate_totp_secret() function."""

    def test_returns_string(self):
        """Prüft dass das TOTP-Secret ein String ist — nötig für QR-Code-Generierung."""
        secret = generate_totp_secret()
        assert isinstance(secret, str)

    def test_proper_length(self):
        """Prüft dass das Secret mindestens 16 Zeichen lang ist — Standard für TOTP-Sicherheit."""
        secret = generate_totp_secret()
        assert len(secret) >= 16

    def test_valid_base32(self):
        """Prüft dass das Secret gültiges Base32 ist und von Authenticator-Apps gelesen werden kann."""
        secret = generate_totp_secret()
        # Should not raise
        totp = pyotp.TOTP(secret)
        assert totp.now() is not None

    def test_unique_secrets(self):
        """Prüft dass jedes generierte Secret einzigartig ist — verhindert 2FA-Kollisionen."""
        secrets = {generate_totp_secret() for _ in range(10)}
        assert len(secrets) == 10


class TestGetTotpUri:
    """Test get_totp_uri() function."""

    def test_returns_otpauth_uri(self):
        """Prüft dass die URI mit otpauth://totp/ beginnt — nötig für QR-Code-Scan."""
        secret = generate_totp_secret()
        uri = get_totp_uri("testuser", secret)
        assert uri.startswith("otpauth://totp/")

    def test_contains_username(self):
        """Prüft dass der Benutzername in der URI enthalten ist — Zuordnung im Authenticator."""
        secret = generate_totp_secret()
        uri = get_totp_uri("testuser", secret)
        assert "testuser" in uri

    def test_contains_issuer(self):
        """Prüft dass PraxisZeit als Issuer in der URI steht — Branding im Authenticator."""
        secret = generate_totp_secret()
        uri = get_totp_uri("testuser", secret)
        assert "PraxisZeit" in uri

    def test_contains_secret_param(self):
        """Prüft dass das Secret als Parameter in der URI enthalten ist — ohne geht kein TOTP."""
        secret = generate_totp_secret()
        uri = get_totp_uri("testuser", secret)
        assert f"secret={secret}" in uri


class TestVerifyTotp:
    """Test verify_totp() function."""

    def test_valid_code_returns_true(self):
        """Prüft dass ein aktuell gültiger TOTP-Code korrekt verifiziert wird."""
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True

    def test_invalid_code_returns_false(self):
        """Prüft dass ein falscher TOTP-Code abgelehnt wird — Schutz vor Brute-Force."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_empty_code_returns_false(self):
        """Prüft dass ein leerer Code abgelehnt wird — Edge Case bei fehlender Eingabe."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "") is False

    def test_wrong_secret_returns_false(self):
        """Prüft dass ein Code von einem anderen Secret abgelehnt wird — verhindert Account-Übernahme."""
        secret1 = generate_totp_secret()
        secret2 = generate_totp_secret()
        code = pyotp.TOTP(secret1).now()
        assert verify_totp(secret2, code) is False


class TestHashPassword:
    """Test hash_password() function."""

    def test_returns_string(self):
        """Prüft dass der Hash ein String ist — nötig für DB-Speicherung."""
        result = hash_password("testpassword")
        assert isinstance(result, str)

    def test_returns_bcrypt_sha256_hash(self):
        """
        F-041: bcrypt_sha256 prefix instead of bare bcrypt.
        The SHA-256 pre-hash eliminates the 72-byte truncation gotcha and
        the passlib format starts with '$bcrypt-sha256$'. Legacy $2b$
        hashes from older installs still verify (backward-compat path
        in CryptContext), but all NEW hashes must use the new scheme.
        """
        result = hash_password("testpassword")
        assert result.startswith("$bcrypt-sha256$")

    def test_different_from_plaintext(self):
        """Prüft dass der Hash nicht dem Klartext-Passwort entspricht — Grundvoraussetzung."""
        password = "testpassword"
        result = hash_password(password)
        assert result != password

    def test_different_hashes_for_same_password(self):
        """Prüft dass gleiches Passwort verschiedene Hashes erzeugt — Salt verhindert Rainbow-Tables."""
        h1 = hash_password("testpassword")
        h2 = hash_password("testpassword")
        assert h1 != h2


class TestVerifyPassword:
    """Test verify_password() function."""

    def test_correct_password_returns_true(self):
        """Prüft dass korrektes Passwort gegen seinen Hash verifiziert — Login-Grundlage."""
        password = "mysecurepassword"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password_returns_false(self):
        """Prüft dass falsches Passwort abgelehnt wird — Schutz vor unbefugtem Zugriff."""
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_empty_password_returns_false(self):
        """Prüft dass leeres Passwort abgelehnt wird — Edge Case bei fehlender Eingabe."""
        hashed = hash_password("realpassword")
        assert verify_password("", hashed) is False

    def test_password_with_special_chars(self):
        """Prüft dass Sonderzeichen im Passwort korrekt gehasht werden — kein Encoding-Problem."""
        password = "P@$$w0rd!#%^&*()"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
