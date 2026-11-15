"""Kundenfall 2026-11-15, Log-Audit Punkt 7 (BO-2): Ergebnis der letzten
Sicherung fuer das globale Admin-Banner.

Vertrag: ``data/backups/.last-result.json`` (geschrieben von
praxiszeit-server.py nach JEDEM Lauf, und vom In-App-Backup) →
``GET /api/admin/backups`` liefert ``last_result`` (gleiche Schluessel) oder
null, wenn die Datei fehlt oder kaputt ist — nie 500.
"""
import json

import pytest

from app.services import backup_service as bs
from tests.test_admin_backups_router import admin_client, _FakePopen  # noqa: F401

GOOD = {
    "ok": False, "finished_at": "2026-11-15T03:00:12+01:00", "file": None,
    "size_bytes": None, "error": "pg_dump fehlgeschlagen", "mirror_ok": None, "verified": False,
}


def test_last_result_null_without_file(admin_client):
    client, _ = admin_client
    r = client.get("/api/admin/backups")
    assert r.status_code == 200
    assert r.json()["last_result"] is None


def test_last_result_read_from_backup_dir(admin_client):
    client, tmp = admin_client
    (tmp / bs.LAST_RESULT_FILENAME).write_text(json.dumps(GOOD), encoding="utf-8")
    body = client.get("/api/admin/backups").json()
    assert body["last_result"] == GOOD


@pytest.mark.parametrize("content", [
    "{kaputt", "[]", '"x"', json.dumps({"finished_at": "x"}), json.dumps({"ok": "ja"}), "\xff\xfe",
])
def test_broken_file_gives_null_never_500(admin_client, content):
    client, tmp = admin_client
    (tmp / bs.LAST_RESULT_FILENAME).write_bytes(content.encode("utf-8", "surrogateescape")
                                                if isinstance(content, str) else content)
    r = client.get("/api/admin/backups")
    assert r.status_code == 200
    assert r.json()["last_result"] is None


def test_wrong_typed_optional_fields_become_null(admin_client):
    client, tmp = admin_client
    (tmp / bs.LAST_RESULT_FILENAME).write_text(json.dumps({
        "ok": True, "finished_at": "2026-11-15T03:00:12+01:00", "file": 5,
        "size_bytes": "gross", "error": None, "mirror_ok": "?", "verified": True, "extra": 1,
    }), encoding="utf-8")
    lr = client.get("/api/admin/backups").json()["last_result"]
    assert lr["ok"] is True and lr["verified"] is True
    assert lr["file"] is None and lr["size_bytes"] is None and lr["mirror_ok"] is None
    assert "extra" not in lr


def test_newest_of_override_and_native_dir_wins(admin_client, tmp_path_factory, monkeypatch):
    """Nativ schreibt praxiszeit-server.py nach data/backups (PRAXISZEIT_BACKUP_DIR),
    auch wenn in der Oberflaeche ein anderer Ort eingestellt ist."""
    client, override = admin_client
    native = tmp_path_factory.mktemp("native")
    monkeypatch.setenv("PRAXISZEIT_BACKUP_DIR", str(native))
    (override / bs.LAST_RESULT_FILENAME).write_text(json.dumps(
        {**GOOD, "ok": True, "finished_at": "2026-11-14T03:00:00+01:00"}), encoding="utf-8")
    (native / bs.LAST_RESULT_FILENAME).write_text(json.dumps(GOOD), encoding="utf-8")
    assert client.get("/api/admin/backups").json()["last_result"]["ok"] is False


def test_in_app_backup_writes_last_result_success_and_failure(admin_client, monkeypatch):
    client, tmp = admin_client
    _scheme = "postgresql://"
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _scheme + "su:pw@db:5432/praxiszeit")
    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen().attach(k))
    assert client.post("/api/admin/backups").status_code == 201
    lr = json.loads((tmp / bs.LAST_RESULT_FILENAME).read_text(encoding="utf-8"))
    assert lr["ok"] is True and lr["file"].startswith("praxiszeit_") and lr["size_bytes"] > 0
    assert lr["error"] is None and lr["mirror_ok"] is None
    assert "+" in lr["finished_at"] or lr["finished_at"].endswith("Z") or "-" in lr["finished_at"][19:]

    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen(payload=b"", rc=1, stderr=b"boom").attach(k))
    assert client.post("/api/admin/backups").status_code >= 400
    lr = json.loads((tmp / bs.LAST_RESULT_FILENAME).read_text(encoding="utf-8"))
    assert lr["ok"] is False and lr["file"] is None and lr["error"]
    # Die Statusdatei taucht nie als Sicherung auf.
    assert all(b["filename"] != bs.LAST_RESULT_FILENAME for b in client.get("/api/admin/backups").json()["backups"])


def test_write_last_result_removes_tmp_on_failure(tmp_path, monkeypatch):
    """Review-Fund: scheitert os.replace (Windows: Ziel offen, Platte voll),
    darf keine ``.last-result.json.<pid>.tmp`` im Sicherungsordner liegen bleiben."""
    def _boom(*_a, **_k):
        raise PermissionError("Zugriff verweigert")
    monkeypatch.setattr(bs.os, "replace", _boom)
    with pytest.raises(OSError):
        bs.write_last_result(tmp_path, ok=True, file="x.sql.gz", size_bytes=1)
    assert list(tmp_path.iterdir()) == []


# --- Endverifikation (Querabgleich der Lanes) ---------------------------------

@pytest.mark.parametrize("native, expected", [(True, True), (False, False)])
def test_scheduled_externally_follows_native_mode(admin_client, monkeypatch, native, expected):
    """Nativ sichert praxiszeit-server.py bzw. die Windows-Aufgabe 03:00
    unabhaengig vom In-App-Schalter - das Admin-Banner braucht das, sonst
    warnt es beim Kunden (Schalter aus) nie vor einer veralteten Sicherung."""
    from app.config import settings
    monkeypatch.setattr(settings, "SERVE_FRONTEND", native)
    client, _ = admin_client
    assert client.get("/api/admin/backups").json()["scheduled_externally"] is expected


def test_labelled_native_backup_is_listed_and_downloadable(admin_client, db):
    """A14: ``backup --label preupdate-<von>-<nach>`` erzeugt
    praxiszeit_<ts>_<label>.sql.gz - die Uebersicht muss sie zeigen."""
    client, tmp = admin_client
    name = "praxiszeit_20261115_101500_preupdate-1.22.0-1.24.1.sql.gz"
    (tmp / name).write_bytes(b"x")
    names = [b["filename"] for b in client.get("/api/admin/backups").json()["backups"]]
    assert name in names
    assert bs.resolve_backup_path(db, name) == (tmp / name).resolve()
    for bad in ["praxiszeit_20261115_101500_../x.sql.gz", "praxiszeit_20261115_101500_A.sql.gz",
                "praxiszeit_20261115_101500_" + "a" * 41 + ".sql.gz"]:
        assert not bs._FILENAME_RE.match(bad)


def test_prune_keeps_newest_three_preupdate_backups(admin_client, db):
    """Wie apply_backup_retention im Serverskript: die juengsten drei
    Sicherungen vor einem Update verfallen nie (A14)."""
    import os
    _, tmp = admin_client
    old = 1_000_000_000
    names = [f"praxiszeit_2026010{i}_120000_preupdate-1.{i}-1.{i + 1}.sql.gz" for i in range(1, 6)]
    plain = "praxiszeit_20260101_030000.sql.gz"
    for i, n in enumerate(names + [plain]):
        (tmp / n).write_bytes(b"x")
        os.utime(tmp / n, (old + i, old + i))
    bs.prune_old_backups(db, retention_days=1)
    left = sorted(p.name for p in tmp.glob("praxiszeit_*.sql.gz"))
    assert left == sorted(names[2:])
