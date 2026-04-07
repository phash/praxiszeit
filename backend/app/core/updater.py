"""
PraxisZeit Update Checker

Checks for available updates against a central update server.
Updates are downloaded and applied by the Process Manager.

The update flow:
1. Backend periodically checks for updates (background task)
2. Admin sees notification in dashboard
3. Admin triggers download via API
4. Admin triggers install via API -> Process Manager handles restart
"""

import hashlib
import json
import logging
import platform
import shutil
import tempfile
import urllib.request
import urllib.error
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Current application version
APP_VERSION = "1.2.1"


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
            "update_available": self.latest_version != APP_VERSION,
        }


# --- Module state ---
_last_check: Optional[datetime] = None
_cached_update: Optional[UpdateInfo] = None


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
    url = (
        f"{server_url.rstrip('/')}/v1/check"
        f"?version={APP_VERSION}"
        f"&license_id={license_id}"
        f"&os={os_name}"
    )

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": f"PraxisZeit/{APP_VERSION}"})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.debug(f"Update check failed (non-critical): {e}")
        _last_check = datetime.now(timezone.utc)
        return _cached_update  # Return cached result if available

    _last_check = datetime.now(timezone.utc)

    latest = data.get("latest", APP_VERSION)
    if latest == APP_VERSION:
        _cached_update = None
        return None

    _cached_update = UpdateInfo(
        latest_version=latest,
        download_url=data.get("download_url", ""),
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


def download_update(update: UpdateInfo, target_dir: Path) -> Path:
    """
    Download an update package and verify its checksum.

    Args:
        update: UpdateInfo with download URL and checksum
        target_dir: Directory to save the downloaded package

    Returns:
        Path to the downloaded file

    Raises:
        ValueError: If checksum verification fails
        urllib.error.URLError: If download fails
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"praxiszeit-{update.latest_version}-{platform.system().lower()}.tar.gz"
    target_path = target_dir / filename

    logger.info(f"Downloading update {update.latest_version} ({update.size_mb} MB)...")

    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        update.download_url,
        headers={"User-Agent": f"PraxisZeit/{APP_VERSION}"},
    )

    hasher = hashlib.sha256()
    with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
        with open(target_path, "wb") as f:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                hasher.update(chunk)

    # Verify checksum
    if update.checksum_sha256:
        actual = hasher.hexdigest()
        if actual != update.checksum_sha256:
            target_path.unlink()
            raise ValueError(
                f"Checksum mismatch! Expected {update.checksum_sha256[:16]}..., "
                f"got {actual[:16]}..."
            )
        logger.info("Checksum verified")

    logger.info(f"Update downloaded: {target_path}")
    return target_path


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
