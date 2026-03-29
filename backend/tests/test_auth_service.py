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
        """Secret must be a string."""
        secret = generate_totp_secret()
        assert isinstance(secret, str)

    def test_proper_length(self):
        """Secret should be a base32 string of standard length (>=16 chars)."""
        secret = generate_totp_secret()
        assert len(secret) >= 16

    def test_valid_base32(self):
        """Secret must be valid base32 (pyotp can use it)."""
        secret = generate_totp_secret()
        # Should not raise
        totp = pyotp.TOTP(secret)
        assert totp.now() is not None

    def test_unique_secrets(self):
        """Each call should generate a different secret."""
        secrets = {generate_totp_secret() for _ in range(10)}
        assert len(secrets) == 10


class TestGetTotpUri:
    """Test get_totp_uri() function."""

    def test_returns_otpauth_uri(self):
        """URI must start with otpauth://totp/."""
        secret = generate_totp_secret()
        uri = get_totp_uri("testuser", secret)
        assert uri.startswith("otpauth://totp/")

    def test_contains_username(self):
        """URI must contain the username."""
        secret = generate_totp_secret()
        uri = get_totp_uri("testuser", secret)
        assert "testuser" in uri

    def test_contains_issuer(self):
        """URI must contain the issuer (PraxisZeit)."""
        secret = generate_totp_secret()
        uri = get_totp_uri("testuser", secret)
        assert "PraxisZeit" in uri

    def test_contains_secret_param(self):
        """URI must contain the secret parameter."""
        secret = generate_totp_secret()
        uri = get_totp_uri("testuser", secret)
        assert f"secret={secret}" in uri


class TestVerifyTotp:
    """Test verify_totp() function."""

    def test_valid_code_returns_true(self):
        """A freshly generated code for the same secret must verify."""
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True

    def test_invalid_code_returns_false(self):
        """An incorrect code must not verify."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_empty_code_returns_false(self):
        """An empty code must not verify."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "") is False

    def test_wrong_secret_returns_false(self):
        """Code from a different secret must not verify."""
        secret1 = generate_totp_secret()
        secret2 = generate_totp_secret()
        code = pyotp.TOTP(secret1).now()
        assert verify_totp(secret2, code) is False


class TestHashPassword:
    """Test hash_password() function."""

    def test_returns_string(self):
        """Hash must be a string."""
        result = hash_password("testpassword")
        assert isinstance(result, str)

    def test_returns_bcrypt_hash(self):
        """Hash must start with $2b$ (bcrypt prefix)."""
        result = hash_password("testpassword")
        assert result.startswith("$2b$")

    def test_different_from_plaintext(self):
        """Hash must not equal the plaintext password."""
        password = "testpassword"
        result = hash_password(password)
        assert result != password

    def test_different_hashes_for_same_password(self):
        """Two hashes of the same password should differ (salted)."""
        h1 = hash_password("testpassword")
        h2 = hash_password("testpassword")
        assert h1 != h2


class TestVerifyPassword:
    """Test verify_password() function."""

    def test_correct_password_returns_true(self):
        """Correct password must verify against its hash."""
        password = "mysecurepassword"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password_returns_false(self):
        """Wrong password must not verify."""
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_empty_password_returns_false(self):
        """Empty password must not verify against a non-empty hash."""
        hashed = hash_password("realpassword")
        assert verify_password("", hashed) is False

    def test_password_with_special_chars(self):
        """Passwords with special characters must work."""
        password = "P@$$w0rd!#%^&*()"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
