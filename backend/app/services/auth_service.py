from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import pyotp
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from app.config import settings

# F-041: Password hashing context.
# - New hashes use bcrypt_sha256, which pre-hashes the password with SHA-256
#   and then feeds the 43-char base64 output into bcrypt. This eliminates
#   the bcrypt 72-byte truncation that silently made >72-char passphrases
#   interchangeable.
# - ``deprecated=["bcrypt"]`` marks existing bcrypt hashes as legacy but
#   still verifiable; passlib's ``needs_update()`` can be used to migrate
#   them opportunistically on the next successful login.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    default="bcrypt_sha256",
    deprecated=["bcrypt"],
)

# JWT settings
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plain password. Uses bcrypt_sha256 (no 72-byte truncation)."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a stored hash.

    Accepts both legacy bcrypt hashes and new bcrypt_sha256 hashes
    transparently via passlib's CryptContext.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Malformed hash (shouldn't happen with our own hashes, but be
        # defensive so a corrupted user row can't crash the login path).
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Return True if the stored hash uses a deprecated scheme.

    Callers can use this on a successful login to opportunistically
    upgrade legacy bcrypt hashes to bcrypt_sha256.
    """
    try:
        return pwd_context.needs_update(hashed_password)
    except ValueError:
        return False


def create_access_token(user_id: str, role: str, token_version: int = 0, tenant_id: str = None) -> str:
    """
    Create JWT access token with 30 minutes expiry.

    Args:
        user_id: User UUID as string
        role: User role (admin or employee)
        token_version: Current token version for revocation support
        tenant_id: Optional tenant UUID as string; added as "tid" claim if provided

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


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code. Allows ±1 window (30s tolerance)."""
    return pyotp.TOTP(secret).verify(code, valid_window=1)


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
    except (PyJWTError, Exception):
        return None
