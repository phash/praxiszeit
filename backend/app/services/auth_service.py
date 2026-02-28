from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import pyotp
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from app.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plain password using bcrypt."""
    # Truncate to 72 bytes (bcrypt limitation)
    password = password[:72]
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    # Truncate to 72 bytes (bcrypt limitation)
    plain_password = plain_password[:72]
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, role: str, token_version: int = 0) -> str:
    """
    Create JWT access token with 30 minutes expiry.

    Args:
        user_id: User UUID as string
        role: User role (admin or employee)
        token_version: Current token version for revocation support

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
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    """
    Create JWT refresh token with 7 days expiry.

    Args:
        user_id: User UUID as string
        token_version: Current token version for revocation support

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
