"""Tests for the native installer's PostgreSQL lifecycle decision logic in
``praxiszeit-server.py``.

The orchestrator script is intentionally not importable as a normal module
(hyphenated filename, runs as the Windows/systemd service entry point), so we
load it via importlib. We only cover the *pure* decision logic here — the
subprocess / Windows-service orchestration is exercised by the manual
post-build install test, not by unit tests.

Regression guard for the native-Windows reinit bug: a foreign PostgreSQL data
directory (EDB leftover, scram auth, "postgres" superuser) used to make
pg_setup_database's trust-based psql calls hang forever on a password prompt.
The cluster marker lets cmd_start tell our own trust-bootstrapped cluster apart
from a foreign one and reinitialize cleanly.
"""
import importlib.util
from pathlib import Path

import pytest

# --- Load the hyphenated orchestrator script as a module ----------------------
_SERVER_PATH = Path(__file__).resolve().parents[2] / "praxiszeit-server.py"


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("praxiszeit_server", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Cluster marker / "is this our cluster" ----------------------------------

class TestClusterMarker:
    def test_marker_absent_means_not_ours(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "PG_DATA", tmp_path)
        assert srv._pg_data_is_ours() is False

    def test_marker_present_means_ours(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "PG_DATA", tmp_path)
        (tmp_path / srv.PG_CLUSTER_MARKER).write_text("praxiszeit-managed\n", encoding="utf-8")
        assert srv._pg_data_is_ours() is True

    def test_marker_constant_is_dotfile(self, srv):
        # Must live inside PGDATA without colliding with PostgreSQL's own files.
        assert srv.PG_CLUSTER_MARKER.startswith(".")
        assert srv.PG_CLUSTER_MARKER not in ("PG_VERSION", "postgresql.conf", "pg_hba.conf")


class TestQuarantinePgData:
    def test_quarantine_preserves_old_dir_and_recreates_empty(self, srv, tmp_path, monkeypatch):
        data = tmp_path / "db"
        data.mkdir()
        (data / "PG_VERSION").write_text("16\n")
        (data / "base").mkdir()
        monkeypatch.setattr(srv, "PG_DATA", data)

        backup = srv._quarantine_pg_data()

        # Fresh, empty data dir is recreated...
        assert data.is_dir()
        assert list(data.iterdir()) == []
        # ...and the old content is preserved under the backup, NOT deleted
        # (regression guard: never destroy a possibly-real cluster).
        assert backup.is_dir()
        assert (backup / "PG_VERSION").read_text() == "16\n"
        assert (backup / "base").is_dir()

    def test_quarantine_creates_dir_when_missing(self, srv, tmp_path, monkeypatch):
        data = tmp_path / "db"
        monkeypatch.setattr(srv, "PG_DATA", data)

        srv._quarantine_pg_data()

        assert data.is_dir()


# --- PG identifier / password escaping (regression) --------------------------

class TestIdentifierAndEscaping:
    def test_valid_identifier_passes_through(self, srv):
        assert srv._validate_pg_identifier("praxiszeit_app") == "praxiszeit_app"

    @pytest.mark.parametrize("bad", ["1abc", "drop;table", "user name", "a-b", "naïve"])
    def test_invalid_identifier_rejected(self, srv, bad):
        with pytest.raises(ValueError):
            srv._validate_pg_identifier(bad)

    def test_password_single_quotes_doubled(self, srv):
        assert srv._escape_pg_password("a'b") == "a''b"
        assert srv._escape_pg_password("no-quotes") == "no-quotes"


# --- Windows service name constant -------------------------------------------

def test_pg_service_name_matches_installer(srv):
    # setup.bat registers the EDB service under this exact name; the server
    # must use the same name so it can detect/unregister a leftover service.
    assert srv.PG_SERVICE_NAME == "PraxisZeit-PostgreSQL"
