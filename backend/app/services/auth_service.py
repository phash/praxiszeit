import base64
import binascii
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import pyotp
from jwt.exceptions import PyJWTError

from app.config import settings

# F-041 / VULN-014 follow-up: passlib 1.7.4 is unmaintained and incompatible with
# bcrypt >= 5.0 (bcrypt removed the ``__about__`` attribute that passlib's backend
# detection reads). We implement the bcrypt_sha256 scheme directly against the
# ``bcrypt`` PyCA library. The wire format is identical to passlib's v=2 protocol
# so existing DB hashes continue to verify without migration.
#
# Wire format:
#   $bcrypt-sha256$v=2,t=2b,r=<rounds>$<22-char salt>$<31-char hash>
#
# v=2 protocol (passlib 1.7.3+):
#   key = base64(HMAC-SHA256(key=salt.ascii, msg=password.utf8))
#   hash = bcrypt(key, salt, rounds)
#
# Keying HMAC with the salt defeats precomputed "password → SHA-256" tables
# that v=1 was vulnerable to. The base64-encoded HMAC digest is 44 bytes,
# always well under bcrypt's 72-byte silent-truncation boundary.

_BCRYPT_SHA256_PREFIX = "$bcrypt-sha256$"
_BCRYPT_SHA256_ROUNDS = 12

# JWT settings
ALGORITHM = "HS256"


def _v2_key(password: str, salt_22: str) -> bytes:
    """v=2 key fed to bcrypt: base64(HMAC-SHA256(salt, password))."""
    digest = hmac.new(
        salt_22.encode("ascii"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    # Standard base64 WITH "=" padding (matches passlib v=2).
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    """Hash a plain password using bcrypt_sha256 (wire-compatible with passlib)."""
    salt_raw = bcrypt.gensalt(rounds=_BCRYPT_SHA256_ROUNDS, prefix=b"2b").decode("ascii")
    salt_22 = salt_raw.split("$", 3)[3]
    key = _v2_key(password, salt_22)
    result = bcrypt.hashpw(key, salt_raw.encode("ascii")).decode("ascii")
    payload = result.split("$", 3)[3]  # "<22-salt><31-hash>"
    return (
        f"{_BCRYPT_SHA256_PREFIX}v=2,t=2b,r={_BCRYPT_SHA256_ROUNDS}$"
        f"{payload[:22]}${payload[22:]}"
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a stored hash.

    Handles both bcrypt_sha256 (new) and bare bcrypt (legacy pre-F-041) hashes.
    Never raises — corrupted or unknown hashes return False.
    """
    if not hashed_password:
        return False
    try:
        if hashed_password.startswith(_BCRYPT_SHA256_PREFIX):
            return _verify_bcrypt_sha256(plain_password, hashed_password)
        if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
            return _verify_legacy_bcrypt(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False
    return False


def _verify_bcrypt_sha256(password: str, hashed: str) -> bool:
    parts = hashed.split("$")
    # Expected: ['', 'bcrypt-sha256', 'v=2,t=2b,r=12', '<salt>', '<hash>']
    if len(parts) != 5 or parts[1] != "bcrypt-sha256":
        return False
    param_map: dict[str, str] = {}
    for kv in parts[2].split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            param_map[k] = v
    # Currently only the v=2 / t=2b variant is produced; reject anything else
    # loudly rather than silently mis-verifying. ``r=`` must be present too —
    # real passlib hashes always include it, and falling back to a default
    # cost would mask corruption as a successful verify against wrong work
    # factor.
    if (
        param_map.get("v") != "2"
        or param_map.get("t") != "2b"
        or "r" not in param_map
    ):
        return False
    try:
        rounds = int(param_map["r"])
    except ValueError:
        return False
    salt, hash_part = parts[3], parts[4]
    if len(salt) != 22 or len(hash_part) != 31:
        return False
    key = _v2_key(password, salt)
    bcrypt_fmt = f"$2b${rounds:02d}${salt}{hash_part}".encode("ascii")
    return bcrypt.checkpw(key, bcrypt_fmt)


def _verify_legacy_bcrypt(password: str, hashed: str) -> bool:
    pwd_bytes = password.encode("utf-8")
    # bcrypt 5 raises ValueError on > 72 bytes; bcrypt 4.x / OpenBSD silently
    # truncated. Preserve legacy verify semantics so pre-F-041 DB rows still
    # log in; F-041 rehash on successful login migrates them to bcrypt_sha256.
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    return bcrypt.checkpw(pwd_bytes, hashed.encode("ascii"))


def needs_rehash(hashed_password: str) -> bool:
    """Return True if the stored hash uses a deprecated scheme.

    Callers use this on a successful login to opportunistically upgrade legacy
    bare-bcrypt hashes to bcrypt_sha256. We also flag bcrypt_sha256 hashes
    whose cost factor is below the current target.
    """
    if not hashed_password:
        return False
    if not hashed_password.startswith(_BCRYPT_SHA256_PREFIX):
        return True
    # bcrypt_sha256 — flag for rehash if rounds < target
    parts = hashed_password.split("$")
    if len(parts) != 5:
        return True
    for kv in parts[2].split(","):
        if kv.startswith("r="):
            try:
                return int(kv[2:]) < _BCRYPT_SHA256_ROUNDS
            except ValueError:
                return True
    return True


def create_access_token(
    user_id: str,
    role: str,
    token_version: int = 0,
    tenant_id: str = None,
    impersonator_id: str = None,
    impersonation_session_id: str = None,
) -> str:
    """
    Create JWT access token with 30 minutes expiry.

    Args:
        user_id: User UUID as string
        role: User role (admin or employee)
        token_version: Current token version for revocation support
        tenant_id: Optional tenant UUID as string; added as "tid" claim if provided
        impersonator_id: #370 — when set, this is a read-only impersonation token;
            ``sub`` is the impersonated employee, ``imp`` records the real admin.
        impersonation_session_id: #370 — id of the impersonation_sessions row, for
            end-of-session logging (``imp_sid`` claim).

    Returns:
        Encoded JWT token
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "tv": token_version,
        "exp": expire
    }
    if tenant_id is not None:
        payload["tid"] = tenant_id
    if impersonator_id is not None:
        payload["imp"] = impersonator_id
    if impersonation_session_id is not None:
        payload["imp_sid"] = impersonation_session_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, token_version: int = 0, tenant_id: str = None) -> str:
    """
    Create JWT refresh token with 7 days expiry.

    Args:
        user_id: User UUID as string
        token_version: Current token version for revocation support
        tenant_id: Optional tenant UUID as string; added as "tid" claim if provided

    Returns:
        Encoded JWT token
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "tv": token_version,
        "exp": expire
    }
    if tenant_id is not None:
        payload["tid"] = tenant_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def generate_totp_secret() -> str:
    """Generate a random base32 TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(username: str, secret: str) -> str:
    """Build the otpauth:// provisioning URI for authenticator apps."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=settings.TOTP_ISSUER,
    )


def _verify_totp_unsafe(secret: str, code: str) -> bool:
    """INTERNAL/UNSAFE — verify a 6-digit TOTP code (±1 window, 30s tolerance).

    Audit R3 (A02): renamed from the former public ``verify_totp`` so it cannot
    be picked by accident. It does NOT protect against replay within the valid
    window. ALL production callers (login, sensitive actions) MUST use
    ``verify_totp_with_counter`` (persists a per-user counter). Kept only for the
    low-level TOTP-verification unit test.
    """
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def verify_totp_with_counter(
    secret: str,
    code: str,
    last_counter: Optional[int],
    *,
    valid_window: int = 1,
) -> Optional[int]:
    """Verify a TOTP code and return the accepted counter value, or None.

    TOTP codes remain valid across a ±30s window (by default) and without a
    persisted counter a captured code can be replayed against the login
    endpoint until it falls out of the window. This helper:

      1. Scans the accepted window for a matching code (constant-time
         comparison per candidate, same as pyotp.verify).
      2. Rejects any counter value that is ≤ last_counter (= already used).
      3. Returns the accepted counter so the caller can persist it.

    The caller is responsible for storing the returned counter on the user
    before the next call is dispatched.
    """
    import time as _time
    # Defensiv (Review 2026-06-23): ein nicht entschluesselbares Secret (SECRET_KEY
    # rotiert -> decrypt_secret gibt den Fernet-Ciphertext zurueck, der KEIN gueltiges
    # Base32 ist) wuerde pyotp's .at() ein binascii.Error werfen lassen -> HTTP 500
    # auf dem Login. Wir fangen das ab und behandeln es als saubere Ablehnung (None
    # -> "Ungueltiger TOTP-Code"); der Nutzer richtet 2FA neu ein.
    try:
        totp = pyotp.TOTP(secret)
        now = int(_time.time())
        step = totp.interval

        # Iterate windows oldest-first so that if two codes within the window
        # both match (pathological clock skew), we accept the highest counter.
        accepted: Optional[int] = None
        for offset in range(-valid_window, valid_window + 1):
            candidate_time = now + offset * step
            counter = candidate_time // step
            if last_counter is not None and counter <= last_counter:
                continue
            expected = totp.at(candidate_time)
            # pyotp's internal comparison is constant-time; fall back to `==`
            # for simplicity since the strings are fixed length.
            if _consteq(expected, code.strip()):
                # Keep scanning so we take the newest matching counter if any
                accepted = counter
        return accepted
    except (binascii.Error, ValueError):
        return None


def _consteq(a: str, b: str) -> bool:
    """Constant-time string comparison for equal-length strings."""
    if len(a) != len(b):
        return False
    result = 0
    for ca, cb in zip(a, b):
        result |= ord(ca) ^ ord(cb)
    return result == 0


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate JWT token.

    Args:
        token: JWT token string

    Returns:
        Token payload dict or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except PyJWTError:
        # Nur JWT-Fehler (expired/invalid/wrong-secret) = "Token ungültig" -> None.
        # NICHT `Exception` mitfangen: das maskierte echte Programmierfehler als
        # "ungültiges Token". Alle jwt.decode-Fehler sind PyJWTError-Subklassen.
        return None
