"""Tests for JWT token creation and decoding.

Password-hashing tests live in ``test_auth_service.py`` — this module focuses
only on the JWT-specific paths (``create_access_token``, ``create_refresh_token``,
``decode_token``) to avoid duplicating assertions across files.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.services import auth_service


class TestCreateAccessToken:
    """``create_access_token`` returns a signed JWT with role + tv claims."""

    def test_payload_roundtrips(self):
        """Prüft dass alle gesetzten Claims (sub, role, type, tv) 1:1 über
        encode→decode erhalten bleiben — ein Payload-Drift würde Auth-Bugs
        verursachen (z.B. falsche Rolle nach Refresh)."""
        user_id = "test-user-id-123"
        role = "employee"
        tv = 7

        token = auth_service.create_access_token(user_id, role, token_version=tv)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[auth_service.ALGORITHM])

        assert payload["sub"] == user_id
        assert payload["role"] == role
        assert payload["type"] == "access"
        assert payload["tv"] == tv
        assert "tid" not in payload  # no tenant_id passed

    def test_tenant_id_claim_present_when_passed(self):
        """Prüft dass tid-Claim nur dann im Payload landet, wenn ein
        tenant_id übergeben wurde — Single-Tenant-Tokens müssen frei
        von tid sein (Abwärtskompatibilität On-Prem)."""
        token = auth_service.create_access_token(
            "u-1", "admin", tenant_id="tenant-123",
        )
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
        assert payload["tid"] == "tenant-123"

    def test_signed_with_hs256(self):
        """Prüft dass der Token mit dem in auth_service.ALGORITHM dokumentierten
        Algorithmus signiert wurde — ein ``alg: none``-Token oder alg-switch
        wäre eine kritische Schwachstelle (JWT-alg-confusion-Angriff)."""
        token = auth_service.create_access_token("u", "employee")
        # The header holds the alg; any tampering would make
        # decode-with-HS256 (see above) fail, but we also pin the header
        # explicitly so a regression that switches algorithms is caught.
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "HS256"

    def test_expiry_respects_settings(self):
        """Prüft dass der Token nach ACCESS_TOKEN_EXPIRE_MINUTES abläuft (±2s
        Slack für Testlauf) — ein Token der nie abläuft wäre ein Security-
        Bug auf Dauer."""
        before = datetime.now(timezone.utc)
        token = auth_service.create_access_token("u", "employee")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[auth_service.ALGORITHM])

        expected_exp = before + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        actual_exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        drift = abs((actual_exp - expected_exp).total_seconds())
        assert drift < 2, f"exp drift {drift}s exceeds 2s tolerance"


class TestCreateRefreshToken:
    """``create_refresh_token`` mirrors access tokens but with longer TTL
    and ``type=refresh``."""

    def test_payload_marked_as_refresh(self):
        """Prüft dass refresh-Tokens type=refresh haben — access-type würde den
        Refresh-Endpoint sonst täuschen (Token-Type-Confusion)."""
        token = auth_service.create_refresh_token("u-1", token_version=3)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
        assert payload["type"] == "refresh"
        assert payload["sub"] == "u-1"
        assert payload["tv"] == 3

    def test_refresh_ttl_is_days_not_minutes(self):
        """Prüft dass refresh-Tokens ~7 Tage gültig sind (REFRESH_TOKEN_EXPIRE_DAYS),
        also signifikant länger als access-Tokens — umgekehrt wäre die Trennung
        access/refresh sinnlos."""
        token = auth_service.create_refresh_token("u")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
        ttl = payload["exp"] - datetime.now(timezone.utc).timestamp()
        # Must be longer than the access-token TTL by at least 10x
        assert ttl > settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 * 10


class TestDecodeToken:
    """``decode_token`` is defensive — invalid input returns None, never raises."""

    def test_valid_access_token_roundtrip(self):
        """Prüft dass ein eben erzeugter access-Token cleanly decodiert wird."""
        token = auth_service.create_access_token("user-1", "employee")
        payload = auth_service.decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["type"] == "access"

    def test_valid_refresh_token_roundtrip(self):
        """Prüft dass ein eben erzeugter refresh-Token cleanly decodiert wird."""
        token = auth_service.create_refresh_token("user-1")
        payload = auth_service.decode_token(token)
        assert payload is not None
        assert payload["type"] == "refresh"

    @pytest.mark.parametrize("bad_token", [
        "invalid.token.here",
        "not-a-jwt-at-all",
        "",
        "a.b",                       # too few segments
        "a.b.c.d",                   # too many segments
        "eyJhbGciOiJIUzI1NiJ9.e30.", # empty signature
    ])
    def test_malformed_tokens_return_none_not_raise(self, bad_token):
        """Prüft dass defekte/tampered Tokens None liefern statt zu crashen —
        Login/Refresh-Handler verlassen sich auf diese Defensive."""
        assert auth_service.decode_token(bad_token) is None

    def test_wrong_secret_signature_rejected(self):
        """Prüft dass ein fremdsigniertes JWT verworfen wird — ohne diese
        Prüfung könnte jemand mit beliebigem Secret Tokens fälschen."""
        payload = {
            "sub": "attacker",
            "role": "admin",
            "type": "access",
            "tv": 0,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
        # >=32 Zeichen: PyJWT 2.13 warnt sonst (InsecureKeyLength). Hier irrelevant —
        # Testzweck ist nur "anderes Secret als SECRET_KEY -> gefälschtes Token verworfen".
        forged = jwt.encode(payload, "attacker-chosen-secret-0123456789abcdef", algorithm="HS256")
        assert auth_service.decode_token(forged) is None

    def test_expired_token_rejected(self):
        """Prüft dass abgelaufene Tokens abgewiesen werden — ein Token muss nach
        exp wertlos sein, sonst ist Session-Kürzung unmöglich."""
        expired = jwt.encode(
            {
                "sub": "u",
                "role": "employee",
                "type": "access",
                "tv": 0,
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        assert auth_service.decode_token(expired) is None


class TestLongPasswordVerify:
    """F-041 backstop: hash_password + verify_password must not silently
    collide for passwords >72 bytes (the old bcrypt truncation bug).

    Kept in this module as a cross-cutting scenario next to JWT tests —
    the scheme-level unit tests live in test_auth_service.py.
    """

    def test_verify_rejects_72byte_prefix_of_longer_password(self):
        """Prüft das Kern-Risiko von F-041: ein Angreifer mit Kenntnis der
        ersten 72 Bytes darf NICHT erfolgreich einloggen — HMAC über den
        ganzen String verhindert das."""
        long_password = "a" * 100
        hashed = auth_service.hash_password(long_password)
        assert auth_service.verify_password(long_password, hashed) is True
        assert auth_service.verify_password("a" * 72, hashed) is False
        assert auth_service.verify_password("b" * 100, hashed) is False
