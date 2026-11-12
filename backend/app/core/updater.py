"""
PraxisZeit Update Checker

Checks for available updates against a central update server.
Updates are downloaded and applied by the Process Manager.

The update flow:
1. The admin dashboard triggers a check (POST /api/admin/updates/check, once per
   browser session; there is no background task)
2. Admin sees notification in dashboard
3. Admin triggers download via API
4. Admin triggers install via API -> Process Manager handles restart
"""

import base64
import json
import logging
import platform
import urllib.request
import urllib.error
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode, urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from app.core.license import _PUBLIC_KEY_PEM  # reuse the same trust root

logger = logging.getLogger(__name__)

# Current application version
APP_VERSION = "1.24.0"

# F-036: Allowed update-server host prefixes. The download URL returned by
# the server is refused unless its host matches one of these. Prevents a
# compromised update server from redirecting clients to an attacker-hosted
# tarball.
_ALLOWED_UPDATE_HOSTS = {
    "updates.praxiszeit.de",
    "updates.mr-development.de",
    "praxiszeit.mr-development.de",
}


def _load_update_public_key() -> Ed25519PublicKey:
    """Return the Ed25519 key used to verify update manifests.

    We reuse the license public key to avoid shipping two sets of trust
    material — the license issuer and the update signer are the same
    principal (Manuel / MR Development).
    """
    key = load_pem_public_key(_PUBLIC_KEY_PEM)
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimeError("Embedded update-signing public key is not Ed25519")
    return key


def _verify_manifest_signature(manifest: dict) -> None:
    """F-036: verify the Ed25519 signature over the update manifest.

    Manifest format::

        {
          "latest": "1.3.0",
          "download_url": "...",
          "changelog": "...",
          "size_mb": 12.3,
          "checksum_sha256": "abc...",
          "critical": false,
          "signature": "<base64-ed25519-sig-over-canonical-fields>"
        }

    The signature is computed over the UTF-8 encoding of the JSON dump of
    all fields except ``signature``, with ``sort_keys=True`` and
    ``separators=(',',':')`` for canonicalization. Any change to the
    manifest body invalidates the signature.

    Raises ``ValueError`` on missing or invalid signature.
    """
    signature_b64 = manifest.get("signature")
    if not signature_b64:
        raise ValueError("Update manifest is not signed")

    body = {k: v for k, v in manifest.items() if k != "signature"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

    try:
        signature = base64.b64decode(signature_b64)
    except Exception as exc:
        raise ValueError(f"Invalid signature encoding: {exc}")

    key = _load_update_public_key()
    try:
        key.verify(signature, payload)
    except InvalidSignature as exc:
        raise ValueError("Update manifest signature verification failed") from exc


def _check_manifest_expiry(manifest: dict, now: Optional[datetime] = None) -> None:
    """Audit 2026-11-07 S3-18: ein mitsigniertes ``expires`` (ISO 8601, mit
    Zeitzone) begrenzt, wie lange ein Manifest gilt.

    Ohne Ablauf koennte ein Angreifer im Netz ein altes, gueltig signiertes
    Manifest ("aktuell ist X") wieder einspielen und so ein neueres, kritisches
    Update verbergen (Freeze). ``expires`` ist Teil des signierten Inhalts (alle
    Felder ausser ``signature``). Fehlt es, gilt das Manifest wie bisher - der
    Update-Server liefert es noch nicht (pzweb); ein vorhandenes, aber
    unlesbares oder abgelaufenes ``expires`` fuehrt zur Ablehnung.

    Raises ``ValueError``.
    """
    expires = manifest.get("expires")
    if expires is None:
        return
    if not isinstance(expires, str):
        raise ValueError("Update manifest 'expires' is not a string")
    try:
        when = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Update manifest 'expires' unreadable: {expires!r}") from exc
    if when.tzinfo is None:
        raise ValueError("Update manifest 'expires' has no time zone")
    if (now or datetime.now(timezone.utc)) > when:
        raise ValueError(
            f"Update manifest expired at {expires} (stale or replayed manifest)"
        )


def _verify_download_host(download_url: str) -> None:
    """Refuse download URLs outside the allowlist. Enforces HTTPS as well."""
    parsed = urlparse(download_url)
    if parsed.scheme != "https":
        raise ValueError(f"Update download URL must use HTTPS: {download_url}")
    if parsed.hostname not in _ALLOWED_UPDATE_HOSTS:
        raise ValueError(
            f"Update download host '{parsed.hostname}' not in allowlist"
        )


def _version_tuple(v: str) -> tuple:
    """Parse 'X.Y.Z[-suffix]' into a comparable (major, minor, patch) int tuple.
    Non-numeric/pre-release suffixes are truncated (best-effort, defensive)."""
    parts = []
    for p in str(v).split(".")[:3]:
        digits = ""
        for ch in p:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _is_newer_version(candidate: str, current: str) -> bool:
    """Audit R3 (A08 anti-rollback): True only if *candidate* is strictly newer
    than *current*. A manifest signature is valid for ANY version the issuer ever
    signed, so a replayed/compromised update server could otherwise serve an
    older, validly-signed manifest to force a signed DOWNGRADE. Comparing by
    semver (not string ``!=``) makes equal-or-older versions a no-op."""
    return _version_tuple(candidate) > _version_tuple(current)


@dataclass
class UpdateInfo:
    """Available update information."""
    latest_version: str
    download_url: str
    changelog: str
    size_mb: float
    checksum_sha256: str
    critical: bool

    def to_dict(self) -> dict:
        return {
            "latest_version": self.latest_version,
            "current_version": APP_VERSION,
            "download_url": self.download_url,
            "changelog": self.changelog,
            "size_mb": self.size_mb,
            "checksum_sha256": self.checksum_sha256,
            "critical": self.critical,
            "update_available": _is_newer_version(self.latest_version, APP_VERSION),
        }


# --- Module state ---
_last_check: Optional[datetime] = None
_cached_update: Optional[UpdateInfo] = None
# ops-06: Grund des letzten gescheiterten Laufs (None = Server wurde erreicht und
# das Manifest angenommen). "Keine Updates" und "Server unerreichbar" sind sonst
# nicht zu unterscheiden.
_last_check_failure: Optional[str] = None


def get_last_check_failure() -> Optional[str]:
    return _last_check_failure


def _set_check_failure(reason: Optional[str]) -> None:
    """Merkt den Fehlerzustand; als Warnung nur beim Wechsel in den Fehlerzustand
    (ein Dauerfehler soll das Log nicht fluten, aber sichtbar sein)."""
    global _last_check_failure
    if reason and not _last_check_failure:
        logger.warning("Update-Prüfung fehlgeschlagen: %s", reason)
    _last_check_failure = reason


def check_for_updates(server_url: str, license_id: str = "") -> Optional[UpdateInfo]:
    """
    Check the update server for available updates.

    Args:
        server_url: Base URL of the update server
        license_id: Customer license ID for tracking

    Returns:
        UpdateInfo if update available, None if up to date or on error
    """
    global _last_check, _cached_update

    os_name = platform.system().lower()
    # ops-19: URL-kodieren, sonst verfälschen &, #, + oder Leerzeichen der Lizenz-ID
    # die Abfrage.
    query = urlencode({"version": APP_VERSION, "license_id": license_id, "os": os_name})
    url = f"{server_url.rstrip('/')}/v1/check?{query}"

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": f"PraxisZeit/{APP_VERSION}"})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        _set_check_failure(f"Update-Server nicht erreichbar ({type(e).__name__}: {e})")
        _last_check = datetime.now(timezone.utc)
        return _cached_update  # Return cached result if available

    _last_check = datetime.now(timezone.utc)

    # F-036: refuse the manifest unless it carries a valid Ed25519
    # signature from the trusted key.
    try:
        _verify_manifest_signature(data)
        _check_manifest_expiry(data)
    except ValueError as e:
        logger.warning(f"Update manifest rejected: {e}")
        _set_check_failure(f"Update-Manifest abgelehnt ({e})")
        _cached_update = None
        return None

    _set_check_failure(None)

    latest = data.get("latest", APP_VERSION)
    # Audit R3 (A08 anti-rollback): only treat a STRICTLY NEWER version as an
    # update. Equal OR older (a replayed, validly-signed downgrade manifest) is a
    # no-op — a valid signature alone must not be sufficient to move the client
    # to an older, potentially weaker build.
    if not _is_newer_version(latest, APP_VERSION):
        _cached_update = None
        return None

    download_url = data.get("download_url", "")
    # Verify host allowlist before caching the download URL for later use.
    try:
        _verify_download_host(download_url)
    except ValueError as e:
        logger.warning(f"Update rejected: {e}")
        _set_check_failure(f"Update abgelehnt ({e})")
        _cached_update = None
        return None

    _cached_update = UpdateInfo(
        latest_version=latest,
        download_url=download_url,
        changelog=data.get("changelog", ""),
        size_mb=data.get("size_mb", 0),
        checksum_sha256=data.get("checksum_sha256", ""),
        critical=data.get("critical", False),
    )

    if _cached_update.critical:
        logger.warning(f"Critical update available: {latest}")
    else:
        logger.info(f"Update available: {latest}")

    return _cached_update


def get_update_status() -> dict:
    """Get current update status for the admin API."""
    result = {
        "current_version": APP_VERSION,
        "last_check": _last_check.isoformat() if _last_check else None,
        "update_available": _cached_update is not None,
    }
    if _cached_update:
        result["update"] = _cached_update.to_dict()
    return result


def get_app_version() -> str:
    """Get the current application version."""
    return APP_VERSION
