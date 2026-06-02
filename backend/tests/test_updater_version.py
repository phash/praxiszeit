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
