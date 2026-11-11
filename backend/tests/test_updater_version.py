"""Audit R3 (A08 anti-rollback): die Update-Versionsentscheidung darf NUR bei
echt neuerer Version anschlagen — ein replaytes, gültig signiertes älteres
Manifest darf kein (signiertes) Downgrade auslösen."""
from app.core.updater import _is_newer_version, _version_tuple, UpdateInfo, APP_VERSION


def test_newer_version_is_update():
    assert _is_newer_version("1.8.2", "1.8.1") is True
    assert _is_newer_version("1.9.0", "1.8.1") is True
    assert _is_newer_version("2.0.0", "1.8.1") is True


def test_equal_version_is_not_update():
    assert _is_newer_version("1.8.1", "1.8.1") is False


def test_older_version_is_rejected_no_rollback():
    # Genau der Angriffsfall: alt-signiertes Manifest mit kleinerer Version.
    assert _is_newer_version("1.4.4", "1.8.1") is False
    assert _is_newer_version("1.8.0", "1.8.1") is False
    assert _is_newer_version("0.9.9", "1.8.1") is False


def test_semver_not_string_compare():
    # String-Vergleich würde "1.10.0" < "1.8.1" liefern — semver muss 1.10 > 1.8.
    assert _is_newer_version("1.10.0", "1.8.1") is True
    assert _version_tuple("1.10.0") > _version_tuple("1.8.1")


def test_prerelease_suffix_tolerated():
    assert _version_tuple("1.8.1-beta") == (1, 8, 1)
    assert _is_newer_version("1.8.2-rc1", "1.8.1") is True


def test_update_info_update_available_rejects_older():
    older = UpdateInfo(latest_version="1.4.4", download_url="", changelog="",
                       size_mb=0, checksum_sha256="", critical=False)
    assert older.to_dict()["update_available"] is False
    newer = UpdateInfo(latest_version="9.9.9", download_url="", changelog="",
                       size_mb=0, checksum_sha256="", critical=False)
    assert newer.to_dict()["update_available"] is True


# --- Audit 2026-11-07 S3-18: mitsigniertes Ablaufdatum gegen Freeze/Replay ---

from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402

from app.core import updater  # noqa: E402

_NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


def test_manifest_without_expires_still_accepted():
    updater._check_manifest_expiry({"latest": "1.0.0"}, now=_NOW)


@pytest.mark.parametrize("expires", ["2026-11-08T00:00:00Z", "2026-11-07T14:00:00+01:00"])
def test_manifest_valid_until_expiry(expires):
    updater._check_manifest_expiry({"expires": expires}, now=_NOW)


@pytest.mark.parametrize("expires", [
    "2026-11-01T00:00:00Z",      # abgelaufen (wiedereingespielt)
    "2026-11-08T00:00:00",       # ohne Zeitzone
    "naechste Woche",            # unlesbar
    1767225600,                  # kein String
])
def test_expired_or_broken_expiry_is_rejected(expires):
    with pytest.raises(ValueError):
        updater._check_manifest_expiry({"expires": expires}, now=_NOW)


def test_check_for_updates_rejects_expired_manifest(monkeypatch):
    import io
    import json

    body = json.dumps({"latest": "99.0.0", "download_url": "https://updates.mr-development.de/x.zip",
                       "expires": "2020-01-01T00:00:00Z", "signature": "x"}).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: _Resp(body))
    monkeypatch.setattr(updater, "_verify_manifest_signature", lambda m: None)
    assert updater.check_for_updates("https://updates.mr-development.de") is None
    monkeypatch.setattr(updater, "_check_manifest_expiry", lambda m: None)
    assert updater.check_for_updates("https://updates.mr-development.de") is not None


# --- Code-Review 2026-11-11 (ops-06, ops-19) ---

def test_update_url_is_urlencoded(monkeypatch):
    """ops-19: Sonderzeichen der Lizenz-ID verfälschen die Abfrage nicht."""
    seen = {}

    def fake_urlopen(req, *a, **k):
        seen["url"] = req.full_url
        raise OSError("down")

    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_urlopen)
    updater.check_for_updates("https://u.example", "a&b=c+d#e f")
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(seen["url"]).query)
    assert q["license_id"] == ["a&b=c+d#e f"]
    assert set(q) == {"version", "license_id", "os"}


def test_unreachable_server_is_reported_as_failure_not_as_current(monkeypatch):
    """ops-06: Netzfehler ist von 'aktuell' unterscheidbar; Erfolg räumt den Fehler weg."""
    def down(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(updater.urllib.request, "urlopen", down)
    updater._set_check_failure(None)
    monkeypatch.setattr(updater, "_cached_update", None)
    assert updater.check_for_updates("https://u.example") is None
    assert updater.get_last_check_failure() is not None

    import io, json

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    body = json.dumps({"latest": updater.APP_VERSION}).encode()
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: _Resp(body))
    monkeypatch.setattr(updater, "_verify_manifest_signature", lambda m: None)
    monkeypatch.setattr(updater, "_check_manifest_expiry", lambda m: None)
    assert updater.check_for_updates("https://u.example") is None
    assert updater.get_last_check_failure() is None


def test_check_endpoint_flags_failed_check(monkeypatch):
    from app.routers import admin_updates
    monkeypatch.setattr(admin_updates.settings, "UPDATE_SERVER_URL", "https://u.example")
    monkeypatch.setattr(admin_updates, "get_current_license", lambda: None)
    monkeypatch.setattr(admin_updates, "check_for_updates", lambda *a, **k: None)
    monkeypatch.setattr(admin_updates, "get_last_check_failure", lambda: "Server weg")
    r = admin_updates.trigger_update_check(current_user=None)
    assert r["check_failed"] is True and r["update_available"] is False
    monkeypatch.setattr(admin_updates, "get_last_check_failure", lambda: None)
    assert admin_updates.trigger_update_check(current_user=None)["check_failed"] is False
