"""Tests for auth service (TOTP, password hashing)."""
import pytest
import pyotp
from app.services.auth_service import (
    generate_totp_secret,
    get_totp_uri,
    _verify_totp_unsafe,
    hash_password,
    verify_password,
    needs_rehash,
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
    """Test _verify_totp_unsafe() function."""

    def test_valid_code_returns_true(self):
        """Prüft dass ein aktuell gültiger TOTP-Code korrekt verifiziert wird."""
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert _verify_totp_unsafe(secret, code) is True

    def test_invalid_code_returns_false(self):
        """Prüft dass ein falscher TOTP-Code abgelehnt wird — Schutz vor Brute-Force."""
        secret = generate_totp_secret()
        assert _verify_totp_unsafe(secret, "000000") is False

    def test_empty_code_returns_false(self):
        """Prüft dass ein leerer Code abgelehnt wird — Edge Case bei fehlender Eingabe."""
        secret = generate_totp_secret()
        assert _verify_totp_unsafe(secret, "") is False

    def test_wrong_secret_returns_false(self):
        """Prüft dass ein Code von einem anderen Secret abgelehnt wird — verhindert Account-Übernahme."""
        secret1 = generate_totp_secret()
        secret2 = generate_totp_secret()
        code = pyotp.TOTP(secret1).now()
        assert _verify_totp_unsafe(secret2, code) is False


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
        the bcrypt_sha256 format starts with '$bcrypt-sha256$'. Legacy $2b$
        hashes from older installs still verify (backward-compat branch in
        verify_password()), but all NEW hashes must use the new scheme.
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


class TestPasslibCompat:
    """Regression vectors: hashes produced by passlib 1.7.4 + bcrypt 4.2.1 must
    continue to verify after the passlib-free rewrite (F-041 follow-up).

    These are real hashes generated with ``CryptContext(schemes=['bcrypt_sha256'])``
    before passlib was removed. If any of them stops verifying, existing user
    password hashes in production DBs would silently stop working on login.
    """

    PASSLIB_VECTORS = [
        ("testpassword", "$bcrypt-sha256$v=2,t=2b,r=12$XOgw9xO4/KMdlL56Tz6Z6O$OaWWc/yhklq/RoNdTydBp291qJ5V2OK"),
        ("Admin2026!", "$bcrypt-sha256$v=2,t=2b,r=12$tew4zwINaJT/M2L8cDKpqu$7aY3JGSS0oC/SxUlYov5SL/L0qBLySu"),
        ("mysecurepassword", "$bcrypt-sha256$v=2,t=2b,r=12$6WMfoaMJa3MpexPWb7mlUO$Udhgk89gbrRjBIYMmeChILvT.hJLEku"),
        ("P@$$w0rd!#%^&*()", "$bcrypt-sha256$v=2,t=2b,r=12$ocalEDjOjyU3107DI4FG.O$.2Cnb7xNtpLrbES8h2Lv2tHXmcKj162"),
    ]

    @pytest.mark.parametrize("password,hashed", PASSLIB_VECTORS)
    def test_passlib_generated_hash_verifies(self, password, hashed):
        assert verify_password(password, hashed) is True

    @pytest.mark.parametrize("password,hashed", PASSLIB_VECTORS)
    def test_passlib_generated_hash_wrong_password_fails(self, password, hashed):
        assert verify_password(password + "x", hashed) is False

    def test_legacy_bare_bcrypt_hash_still_verifies(self):
        """Pre-F-041 installs stored bare $2b$ bcrypt hashes. Those must still
        verify so existing users can log in; a successful login triggers the
        F-041 opportunistic rehash path in routers/auth.py.
        """
        # Generated via: bcrypt.hashpw(b"legacypass", bcrypt.gensalt(rounds=12))
        # The legacy-bcrypt code path truncates at 72 bytes to match the old
        # silent-truncation semantics that bcrypt 5 now rejects with ValueError.
        import bcrypt as _bcrypt
        legacy_hash = _bcrypt.hashpw(b"legacypass", _bcrypt.gensalt(rounds=4)).decode("ascii")
        assert legacy_hash.startswith("$2b$")
        assert verify_password("legacypass", legacy_hash) is True
        assert verify_password("wrongpass", legacy_hash) is False

    def test_long_password_over_72_bytes_on_bcrypt_sha256(self):
        """bcrypt_sha256's whole point: passwords > 72 bytes don't collide.
        Two passwords sharing a 72-byte prefix must hash to distinct values.
        """
        long_a = "a" * 100 + "DIFFERENT_TAIL_A"
        long_b = "a" * 100 + "DIFFERENT_TAIL_B"
        hashed_a = hash_password(long_a)
        assert verify_password(long_a, hashed_a) is True
        assert verify_password(long_b, hashed_a) is False


class TestNeedsRehash:
    """Test needs_rehash() — F-041 opportunistic migration signal."""

    def test_new_bcrypt_sha256_hash_does_not_need_rehash(self):
        hashed = hash_password("anypassword")
        assert needs_rehash(hashed) is False

    def test_bare_bcrypt_hash_needs_rehash(self):
        """Pre-F-041 bare bcrypt hashes should be flagged for migration."""
        import bcrypt as _bcrypt
        legacy = _bcrypt.hashpw(b"pwd", _bcrypt.gensalt(rounds=4)).decode("ascii")
        assert needs_rehash(legacy) is True

    def test_empty_hash_does_not_need_rehash(self):
        # Defensive: no hash → no user → nothing to rehash.
        assert needs_rehash("") is False
        assert needs_rehash(None) is False  # type: ignore[arg-type]

    def test_lower_cost_factor_needs_rehash(self):
        # A bcrypt_sha256 hash with rounds < 12 should be flagged for upgrade.
        hash_at_rounds = _make_v2_hash("pw", rounds=10)
        assert needs_rehash(hash_at_rounds) is True

    def test_higher_cost_factor_does_not_need_rehash(self):
        # If someone manually raised the cost above the target, we should not
        # downgrade them. needs_rehash is asymmetric: only flag < target.
        hash_at_rounds = _make_v2_hash("pw", rounds=13)
        assert needs_rehash(hash_at_rounds) is False


class TestEdgeCaseHashes:
    """Hashes with unusual shapes must fail cleanly, never silently verify."""

    def test_v1_hash_format_is_rejected(self):
        """passlib v=1 hashes (pre-2017, bcrypt(sha256(pwd)) without HMAC) are
        not supported — must return False, never accidentally verify against
        the v=2 HMAC path."""
        v1_hash = "$bcrypt-sha256$2b,12$XOgw9xO4/KMdlL56Tz6Z6O$OaWWc/yhklq/RoNdTydBp291qJ5V2OK"
        assert verify_password("anything", v1_hash) is False

    def test_hash_missing_rounds_param_is_rejected(self):
        """A hash without r= is malformed. Defaulting to the current target
        rounds would mask corruption as a successful verify."""
        no_rounds = "$bcrypt-sha256$v=2,t=2b$XOgw9xO4/KMdlL56Tz6Z6O$OaWWc/yhklq/RoNdTydBp291qJ5V2OK"
        assert verify_password("testpassword", no_rounds) is False

    def test_password_with_null_byte_verifies(self):
        """HMAC-SHA256 is byte-safe, so NUL bytes in the password should
        hash cleanly. (Bare bcrypt stops at the first NUL, which was one of
        the reasons for bcrypt_sha256 in the first place.)"""
        password = "abc\x00def"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
        # A password matching only the pre-NUL prefix must NOT verify —
        # this is the bug bcrypt_sha256 fixes vs bare bcrypt.
        assert verify_password("abc", hashed) is False

    def test_hash_with_wrong_salt_length_is_rejected(self):
        too_short = "$bcrypt-sha256$v=2,t=2b,r=12$shortsalt$OaWWc/yhklq/RoNdTydBp291qJ5V2OK"
        assert verify_password("testpassword", too_short) is False


def _make_v2_hash(password: str, *, rounds: int) -> str:
    """Produce a bcrypt_sha256 v=2 hash at arbitrary cost — test helper."""
    import base64 as _b64
    import hashlib as _hashlib
    import hmac as _hmac
    import bcrypt as _bcrypt

    salt_raw = _bcrypt.gensalt(rounds=rounds, prefix=b"2b").decode("ascii")
    salt_22 = salt_raw.split("$", 3)[3]
    key = _b64.b64encode(
        _hmac.new(salt_22.encode("ascii"), password.encode("utf-8"), _hashlib.sha256).digest()
    )
    result = _bcrypt.hashpw(key, salt_raw.encode("ascii")).decode("ascii")
    payload = result.split("$", 3)[3]
    return f"$bcrypt-sha256$v=2,t=2b,r={rounds}${payload[:22]}${payload[22:]}"
