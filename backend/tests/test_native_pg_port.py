"""Tests for the single PostgreSQL port source in ``praxiszeit-server.py``.

``[database] port`` is honoured on Windows only; Linux/macOS stay socket-only
on 5432. Loaded via importlib like test_native_pg_lifecycle.py.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_SERVER_PATH = Path(__file__).resolve().parents[2] / "praxiszeit-server.py"

pytestmark = pytest.mark.skipif(
    not _SERVER_PATH.exists(),
    reason=f"praxiszeit-server.py not reachable at {_SERVER_PATH} "
    "(native orchestrator not present, e.g. inside the docker backend container)",
)


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("praxiszeit_server_pgport", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParsePgPort:
    def test_missing_entry_is_default(self, srv):
        assert srv.parse_pg_port({}) == 5432

    def test_int_entry(self, srv):
        assert srv.parse_pg_port({"database": {"port": 5433}}) == 5433

    def test_numeric_string_entry(self, srv):
        assert srv.parse_pg_port({"database": {"port": "5433"}}) == 5433

    @pytest.mark.parametrize("raw", [0, 80, 1023, 65536, "abc", "54.3", True, -1])
    def test_invalid_entry_raises_with_copy(self, srv, raw):
        with pytest.raises(srv.PgConfigError) as e:
            srv.parse_pg_port({"database": {"port": raw}})
        assert "erlaubt sind ganze Zahlen von 1024 bis 65535" in str(e.value)

    def test_foreign_error_is_a_config_error(self, srv):
        assert issubclass(srv.ForeignPostgresError, srv.PgConfigError)


class TestPgPortPlatform:
    def test_windows_reads_config(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        assert srv.pg_port() == 5433

    def test_unix_ignores_entry(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        assert srv.pg_port() == 5432


class TestPrintDbPortCli:
    def test_prints_port_only(self, srv, monkeypatch, capsys):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        monkeypatch.setattr(sys, "argv", ["x", "print-db-port"])
        srv.main()
        assert capsys.readouterr().out == "5433\n"

    def test_invalid_config_exits_78(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": "abc"}})
        monkeypatch.setattr(sys, "argv", ["x", "print-db-port"])
        with pytest.raises(SystemExit) as e:
            srv.main()
        assert e.value.code == 78


class TestClientsUsePort:
    @pytest.fixture(autouse=True)
    def _win(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})

    def test_database_url_windows_uses_configured_port(self, srv):
        assert (
            srv._database_url("praxiszeit_app", "pw", "praxiszeit")
            == "postgresql://praxiszeit_app:pw@localhost:5433/praxiszeit"
        )

    def test_pg_env_windows_overrides_inherited_host_and_port(self, srv, monkeypatch):
        monkeypatch.setenv("PGPORT", "9999")
        monkeypatch.setenv("PGHOST", "db.example")
        env = srv.pg_env()
        assert env["PGPORT"] == "5433"
        assert env["PGHOST"] == "localhost"

    def test_pg_isready_probe_uses_configured_port(self, srv, monkeypatch):
        captured = {}

        def _run(argv, *a, **kw):
            captured["argv"] = list(argv)
            from unittest.mock import MagicMock
            m = MagicMock()
            m.returncode = 0
            return m

        monkeypatch.setattr(srv.subprocess, "run", _run)
        srv.pg_is_running()
        argv = captured["argv"]
        assert argv[argv.index("-p") + 1] == "5433", argv

    def test_pg_init_windows_writes_configured_port(self, srv, tmp_path, monkeypatch):
        import types

        pg_data = tmp_path / "db"
        pg_data.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(srv, "PG_DATA", pg_data)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)
        monkeypatch.setattr(srv, "BIN_DIR", tmp_path / "bin")
        monkeypatch.setattr(srv, "LOG_DIR", log_dir)
        monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path / "config")
        monkeypatch.setattr(
            srv.subprocess, "run",
            lambda *a, **kw: types.SimpleNamespace(returncode=0, check_returncode=lambda: None),
        )
        srv.pg_init({}, "su-pw")
        conf = (pg_data / "postgresql.conf").read_text()
        assert "\nport = 5433\n" in conf
        assert "listen_addresses = 'localhost'" in conf

    def test_unix_url_and_env_unchanged(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)
        assert "localhost:" not in srv._database_url("u", "pw", "db")
        monkeypatch.setenv("PGPORT", "9999")
        assert "PGPORT" not in srv.pg_env()
