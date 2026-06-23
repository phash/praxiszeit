"""#213 — Tests fuer den DB-Backup-Service (Config, Listing, Prune, create_backup).

create_backup wird mit gemocktem subprocess.Popen getestet (kein echtes pg_dump in
der SQLite-Suite); die Fehlerpfade (kein Superuser-URL, pg_dump fehlt) laufen echt.
"""
import gzip
import io
import os
import time

import pytest

from app.services import backup_service as bs


@pytest.fixture(autouse=True)
def _clear_backup_env(monkeypatch):
    monkeypatch.delenv("PRAXISZEIT_BACKUP_DIR", raising=False)
    monkeypatch.delenv("PRAXISZEIT_PG_DUMP", raising=False)
    monkeypatch.delenv("DATABASE_URL_MIGRATIONS", raising=False)


def _use_tmp_dir(db, tmp_path):
    bs.update_config(db, location=str(tmp_path))


# --- Config -----------------------------------------------------------------

def test_config_defaults(db, default_tenant):
    cfg = bs.get_config(db)
    assert cfg.enabled is False
    assert cfg.hour == bs.DEFAULT_HOUR
    assert cfg.retention_days == bs.DEFAULT_RETENTION_DAYS


def test_update_config_persists_and_clamps(db, default_tenant):
    cfg = bs.update_config(db, enabled=True, hour=99, retention_days=0, location="/var/backups/pz")
    assert cfg.enabled is True
    assert cfg.hour == 23          # geclamped auf 0..23
    assert cfg.retention_days == 1  # geclamped auf >=1
    assert cfg.location == "/var/backups/pz"
    # frisch gelesen identisch
    assert bs.get_config(db).enabled is True


def test_location_override_beats_env(db, default_tenant, tmp_path, monkeypatch):
    monkeypatch.setenv("PRAXISZEIT_BACKUP_DIR", "/env/dir")
    bs.update_config(db, location=str(tmp_path))
    assert bs.get_backup_dir(db) == tmp_path


def test_env_dir_used_when_no_override(db, default_tenant, monkeypatch):
    monkeypatch.setenv("PRAXISZEIT_BACKUP_DIR", "/env/dir")
    assert str(bs.get_backup_dir(db)) == "/env/dir"


# --- Listing / resolve ------------------------------------------------------

def test_list_backups_empty(db, default_tenant, tmp_path):
    _use_tmp_dir(db, tmp_path)
    assert bs.list_backups(db) == []


def test_list_backups_only_matching_names_newest_first(db, default_tenant, tmp_path):
    _use_tmp_dir(db, tmp_path)
    (tmp_path / "praxiszeit_20260101_010101.sql.gz").write_bytes(b"a")
    (tmp_path / "praxiszeit_20260202_020202.sql.gz").write_bytes(b"bb")
    (tmp_path / "random.txt").write_bytes(b"nope")
    (tmp_path / "praxiszeit_bad.sql.gz").write_bytes(b"x")  # falsches Muster
    names = [b.filename for b in bs.list_backups(db)]
    assert names == [
        "praxiszeit_20260202_020202.sql.gz",
        "praxiszeit_20260101_010101.sql.gz",
    ]


def test_resolve_backup_path_rejects_traversal(db, default_tenant, tmp_path):
    _use_tmp_dir(db, tmp_path)
    assert bs.resolve_backup_path(db, "../etc/passwd") is None
    assert bs.resolve_backup_path(db, "praxiszeit_../x.sql.gz") is None
    assert bs.resolve_backup_path(db, "evil.sql.gz") is None


def test_delete_backup(db, default_tenant, tmp_path):
    _use_tmp_dir(db, tmp_path)
    f = tmp_path / "praxiszeit_20260101_010101.sql.gz"
    f.write_bytes(b"x")
    assert bs.delete_backup(db, f.name) is True
    assert not f.exists()
    assert bs.delete_backup(db, "praxiszeit_20990101_000000.sql.gz") is False


def test_prune_old_backups(db, default_tenant, tmp_path):
    _use_tmp_dir(db, tmp_path)
    old = tmp_path / "praxiszeit_20200101_000000.sql.gz"
    new = tmp_path / "praxiszeit_20260101_000000.sql.gz"
    old.write_bytes(b"old"); new.write_bytes(b"new")
    # old auf vor 40 Tagen setzen
    forty_days_ago = time.time() - 40 * 86400
    os.utime(old, (forty_days_ago, forty_days_ago))
    removed = bs.prune_old_backups(db, retention_days=30)
    assert removed == 1
    assert not old.exists()
    assert new.exists()


# --- create_backup ----------------------------------------------------------

def test_create_backup_without_superuser_url_raises(db, default_tenant, tmp_path):
    _use_tmp_dir(db, tmp_path)
    with pytest.raises(bs.BackupError, match="DATABASE_URL_MIGRATIONS"):
        bs.create_backup(db)


class _FakePopen:
    def __init__(self, payload: bytes, rc: int = 0, stderr: bytes = b""):
        self.stdout = io.BytesIO(payload)
        self.stderr = io.BytesIO(stderr)
        self._rc = rc

    def wait(self):
        return self._rc


def test_create_backup_success_writes_gzipped_sql(db, default_tenant, tmp_path, monkeypatch):
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql://su:pw@db:5432/praxiszeit")
    sql = b"-- PraxisZeit dump\nDROP TABLE IF EXISTS x;\nCREATE TABLE x();\n"
    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen(sql))

    result = bs.create_backup(db)
    path = tmp_path / result.filename
    assert path.exists() and result.size_bytes > 0
    assert result.filename.startswith("praxiszeit_") and result.filename.endswith(".sql.gz")
    with gzip.open(path, "rb") as gz:
        assert gz.read() == sql  # plain-SQL, einfach gunzip-bar (Restore-Pfad)


def test_create_backup_strips_driver_suffix_in_url(db, default_tenant, tmp_path, monkeypatch):
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql+psycopg2://su:pw@db/praxiszeit")
    captured = {}

    def _fake_popen(cmd, **k):
        captured["cmd"] = cmd
        return _FakePopen(b"SELECT 1;")

    monkeypatch.setattr(bs.subprocess, "Popen", _fake_popen)
    bs.create_backup(db)
    assert captured["cmd"][-1] == "postgresql://su:pw@db/praxiszeit"  # +psycopg2 entfernt


def test_create_backup_pg_dump_failure_removes_partial(db, default_tenant, tmp_path, monkeypatch):
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql://su:pw@db/praxiszeit")
    monkeypatch.setattr(
        bs.subprocess, "Popen",
        lambda *a, **k: _FakePopen(b"", rc=1, stderr=b"FATAL: auth failed"),
    )
    with pytest.raises(bs.BackupError, match="auth failed"):
        bs.create_backup(db)
    assert list(tmp_path.glob("*.sql.gz")) == []  # kein truncated/leeres Artefakt
