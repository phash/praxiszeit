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

# Ed25519 public keys for license verification.
# The corresponding private keys are kept secure by the license issuer.
#
# WICHTIG: Es werden MEHRERE Schlüssel akzeptiert. In 1.5.x wurde der Public Key
# einmal rotiert (B5ZiJro… -> t8zaDoRf…). Dabei wurden alle vorher ausgestellten
# Kundenlizenzen ungültig und ein Produktiv-Server fiel in den Read-Only-Modus.
# Deshalb akzeptieren wir hier sowohl den aktuellen (NEU) als auch den alten
# (ALT) Schlüssel: eine mit einem der beiden privaten Schlüssel signierte Lizenz
# bleibt gültig. Neue Schlüssel IMMER vorne anhängen, alte NIE einfach entfernen
# (sonst werden Bestandslizenzen wieder ungültig). Muss byte-für-byte mit der
# Liste in installer/setup/.../LicenseValidator.cs synchron bleiben.
_PUBLIC_KEYS_PEM = [
    # NEU — aktuelle Shop-Ausstellung (gepaart mit dem privaten Key im pzweb-Repo)
    b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAt8zaDoRf4KldrPMxmX0uKhoaOrIAyU4wtgtn489WxdI=
-----END PUBLIC KEY-----""",
    # ALT — Bestandslizenzen, die vor der 1.5.x-Rotation ausgestellt wurden
    b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAB5ZiJro6fDM8M5BupMCdTWjVIFkPn+hsNYHNlajzIyY=
-----END PUBLIC KEY-----""",
]

_PUBLIC_KEY_CONFIGURED = True

# Backward-compat: updater.py nutzt diesen Namen als Trust-Root für die
# Update-Manifest-Signatur. Manifeste werden live vom Update-Server mit dem
# AKTUELLEN privaten Schlüssel signiert → der erste (neueste) Key ist korrekt.
_PUBLIC_KEY_PEM = _PUBLIC_KEYS_PEM[0]


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


def _get_public_keys() -> List[Ed25519PublicKey]:
    """Load all embedded Ed25519 public keys (current + legacy)."""
    keys: List[Ed25519PublicKey] = []
    for pem in _PUBLIC_KEYS_PEM:
        try:
            key = load_pem_public_key(pem)
        except Exception as e:
            raise LicenseError(f"Failed to load license public key: {e}")
        if not isinstance(key, Ed25519PublicKey):
            raise LicenseError("Embedded public key is not Ed25519")
        keys.append(key)
    if not keys:
        raise LicenseError("Kein Lizenz-Public-Key konfiguriert")
    return keys


def _decode_with_any_key(license_token: str, *, require: Optional[List[str]] = None) -> dict:
    """Decode/verify the JWT against EACH accepted public key.

    Returns the payload on the first key whose signature verifies. Only a
    signature mismatch is retried across keys — a malformed token (DecodeError)
    or a missing required claim is the same for every key and propagates
    immediately. Raises jwt.InvalidSignatureError if NO key matches.
    """
    options = {"verify_exp": False}
    if require is not None:
        options["require"] = require
    last_sig_error: Optional[Exception] = None
    for key in _get_public_keys():
        try:
            return jwt.decode(license_token, key, algorithms=["EdDSA"], options=options)
        except jwt.InvalidSignatureError as e:
            last_sig_error = e
            continue
    raise last_sig_error or jwt.InvalidSignatureError("Signature verification failed")


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
        raise LicenseError(f"Lizenzdatei nicht gefunden: {license_path}")

    # utf-8-sig: entfernt ein evtl. vorhandenes UTF-8-BOM (z.B. wenn die Datei
    # einmal mit Notepad gespeichert wurde) — sonst würde das BOM den JWT-Header
    # zerstören und die Lizenz fälschlich als „beschädigt" gelten.
    license_token = license_path.read_text(encoding="utf-8-sig").strip()
    if not license_token:
        raise LicenseError("Lizenzdatei ist leer")

    if not _PUBLIC_KEY_CONFIGURED:
        raise LicenseError(
            "License public key not configured. "
            "Generate a keypair with: python tools/license-generator.py generate-keypair"
        )

    try:
        payload = _decode_with_any_key(
            license_token,
            require=["sub", "name", "max_employees", "iat"],
        )
    except jwt.InvalidSignatureError:
        # Die Lizenz wurde mit einem Schlüssel signiert, der zu KEINEM der
        # hinterlegten Public Keys passt (weder aktuell noch Bestand). NICHT
        # „korrupt/manipuliert" behaupten — das ist irreführend.
        raise LicenseError(
            "Lizenz-Signatur passt zu keinem hinterlegten Schlüssel. "
            "Die Lizenz wurde vermutlich für eine andere Schlüsselversion "
            "ausgestellt. Bitte eine aktuelle Lizenz im Shop "
            "(praxiszeit.mr-development.de) holen und config/license.key ersetzen."
        )
    except jwt.DecodeError as e:
        raise LicenseError(
            f"Lizenzdatei ist kein gültiges Token (Format/Inhalt beschädigt): {e}"
        )
    except jwt.MissingRequiredClaimError as e:
        raise LicenseError(f"Lizenz fehlt ein Pflichtfeld: {e}")

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

    license_token = license_path.read_text(encoding="utf-8-sig").strip()
    if not license_token or not _PUBLIC_KEY_CONFIGURED:
        return None

    try:
        payload = _decode_with_any_key(license_token)
    except jwt.PyJWTError:
        return None
    except LicenseError:
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
    FastAPI dependency that raises 403 while the license is in read-only mode.

    NOT attached to any route as a ``Depends`` — write enforcement is done
    globally by ``LicenseReadOnlyMiddleware`` (see ``app/middleware/license.py``),
    which covers every write endpoint by default instead of relying on each
    new one remembering to add this dependency. Kept as a small, directly
    testable unit (see ``test_read_only_guard`` in ``test_native_mode.py``)
    for the read-only-state check itself.
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
