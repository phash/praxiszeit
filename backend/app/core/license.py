"""
Offline license validation for PraxisZeit native installations.

Licenses are Ed25519-signed JWTs containing customer info, employee limits,
and expiry dates. The public key is embedded here; the private key stays
with the license issuer (Manuel / MR Development).

License lifecycle:
- Valid: full functionality
- Expired: read-only mode (data viewable + exportable, no new entries — ArbZG-compliant)
- Missing/invalid: app refuses to start (native mode only)
- Employee limit exceeded: warning, no new users can be created
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

logger = logging.getLogger(__name__)

# Ed25519 public key for license verification.
# The corresponding private key is kept secure by the license issuer.
# Replace this with your actual public key after generating a keypair
# with tools/license-generator.py
_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAt8zaDoRf4KldrPMxmX0uKhoaOrIAyU4wtgtn489WxdI=
-----END PUBLIC KEY-----"""

_PUBLIC_KEY_CONFIGURED = True


class LicenseError(Exception):
    """Raised when license validation fails."""
    pass


class LicenseExpiredError(LicenseError):
    """Raised when the license has expired (app should enter read-only mode)."""
    pass


@dataclass
class LicenseInfo:
    """Parsed and validated license information."""
    customer_id: str
    customer_name: str
    max_employees: int
    features: List[str] = field(default_factory=lambda: ["base"])
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    version: int = 1

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def days_until_expiry(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, delta.days)


def _get_public_key() -> Ed25519PublicKey:
    """Load the embedded Ed25519 public key."""
    try:
        key = load_pem_public_key(_PUBLIC_KEY_PEM)
        if not isinstance(key, Ed25519PublicKey):
            raise LicenseError("Embedded public key is not Ed25519")
        return key
    except Exception as e:
        raise LicenseError(f"Failed to load license public key: {e}")


def validate_license(license_path: Path) -> LicenseInfo:
    """
    Validate a license file and return parsed license info.

    Args:
        license_path: Path to the license.key file

    Returns:
        LicenseInfo with validated claims

    Raises:
        LicenseError: If the license is missing, invalid, or has bad signature
        LicenseExpiredError: If the license has expired
    """
    if not license_path.is_file():
        raise LicenseError(f"License file not found: {license_path}")

    license_token = license_path.read_text().strip()
    if not license_token:
        raise LicenseError("License file is empty")

    if not _PUBLIC_KEY_CONFIGURED:
        raise LicenseError(
            "License public key not configured. "
            "Generate a keypair with: python tools/license-generator.py generate-keypair"
        )

    public_key = _get_public_key()

    try:
        payload = jwt.decode(
            license_token,
            public_key,
            algorithms=["EdDSA"],
            options={
                "require": ["sub", "name", "max_employees", "iat"],
                "verify_exp": False,  # We handle expiry ourselves (read-only mode)
            },
        )
    except jwt.InvalidSignatureError:
        raise LicenseError("License signature is invalid — file may be corrupted or tampered with")
    except jwt.DecodeError as e:
        raise LicenseError(f"License file is not a valid token: {e}")
    except jwt.MissingRequiredClaimError as e:
        raise LicenseError(f"License is missing required field: {e}")

    info = LicenseInfo(
        customer_id=payload["sub"],
        customer_name=payload["name"],
        max_employees=int(payload["max_employees"]),
        features=payload.get("features", ["base"]),
        issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None,
        version=payload.get("v", 1),
    )

    if info.is_expired:
        raise LicenseExpiredError(
            f"License for '{info.customer_name}' expired on "
            f"{info.expires_at.strftime('%Y-%m-%d')}. "
            f"The application will run in read-only mode."
        )

    return info


def validate_license_quiet(license_path: Path) -> Optional[LicenseInfo]:
    """
    Validate license without raising on expiry.
    Returns LicenseInfo (possibly expired) or None on hard errors.
    Used for periodic re-validation and status display.
    """
    if not license_path.is_file():
        return None

    license_token = license_path.read_text().strip()
    if not license_token or not _PUBLIC_KEY_CONFIGURED:
        return None

    public_key = _get_public_key()

    try:
        payload = jwt.decode(
            license_token,
            public_key,
            algorithms=["EdDSA"],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError:
        return None

    return LicenseInfo(
        customer_id=payload.get("sub", ""),
        customer_name=payload.get("name", ""),
        max_employees=int(payload.get("max_employees", 0)),
        features=payload.get("features", ["base"]),
        issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc) if "iat" in payload else None,
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None,
        version=payload.get("v", 1),
    )


# --- Module-level license state (set during startup) ---

_current_license: Optional[LicenseInfo] = None
_license_read_only: bool = False


def get_current_license() -> Optional[LicenseInfo]:
    """Get the currently loaded license info."""
    return _current_license


def is_read_only() -> bool:
    """Check if the app is in read-only mode due to expired license."""
    return _license_read_only


def set_license_state(license_info: Optional[LicenseInfo], read_only: bool = False):
    """Set the module-level license state (called during startup)."""
    global _current_license, _license_read_only
    _current_license = license_info
    _license_read_only = read_only


def require_writable():
    """
    FastAPI dependency that blocks write operations when license is expired.
    Use in POST/PUT/DELETE endpoints that create or modify data.

    Usage:
        @router.post("/api/time-entries", dependencies=[Depends(require_writable)])
        def create_entry(...): ...
    """
    from fastapi import HTTPException
    if _license_read_only:
        raise HTTPException(
            status_code=403,
            detail="Lizenz abgelaufen. Die Anwendung befindet sich im Nur-Lese-Modus. "
                   "Bitte erneuern Sie Ihre Lizenz.",
        )


def check_employee_limit(current_count: int):
    """
    Check if adding another employee would exceed the license limit.
    Call before creating a new user.

    Args:
        current_count: Current number of active employees

    Raises:
        HTTPException: If the limit would be exceeded
    """
    from fastapi import HTTPException
    if _current_license and current_count >= _current_license.max_employees:
        raise HTTPException(
            status_code=403,
            detail=f"Mitarbeiter-Limit erreicht ({_current_license.max_employees}). "
                   f"Bitte upgraden Sie Ihre Lizenz.",
        )
