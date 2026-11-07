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


@pytest.fixture(autouse=True)
def _fresh_pg_port(srv):
    """pg_port() is memoized per process; every test starts uncached."""
    srv.pg_port.cache_clear()
    yield
    srv.pg_port.cache_clear()


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

    def test_unix_never_reads_the_conf(self, srv, monkeypatch):
        """Behaviour before Teil C: a malformed conf must not surface through
        pg_port() on Linux/macOS."""
        monkeypatch.setattr(srv, "IS_WINDOWS", False)

        def _boom():
            raise RuntimeError("conf must not be read on Unix")

        monkeypatch.setattr(srv, "load_config", _boom)
        assert srv.pg_port() == 5432

    def test_unix_warns_once_about_an_ignored_entry(self, srv, monkeypatch, caplog):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "_pg_port_ignored_warned", False)
        with caplog.at_level("WARNING"):
            srv.warn_ignored_pg_port({"database": {"port": 5433}})
            srv.warn_ignored_pg_port({"database": {"port": 5433}})
        assert caplog.text.count("[database] port wird auf dieser Plattform ignoriert") == 1

    def test_windows_does_not_warn_about_the_entry(self, srv, monkeypatch, caplog):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "_pg_port_ignored_warned", False)
        with caplog.at_level("WARNING"):
            srv.warn_ignored_pg_port({"database": {"port": 5433}})
        assert "ignoriert" not in caplog.text

    def test_cmd_start_warns_from_the_loaded_config(self):
        src = _SERVER_PATH.read_text(encoding="utf-8")
        body = src[src.index("def cmd_start(args):"):src.index("def cmd_stop(args):")]
        assert "warn_ignored_pg_port(config)" in body


class TestBomWarningOnce:
    def test_bom_warning_once_per_process(self, srv, tmp_path, monkeypatch, caplog):
        conf = tmp_path / "praxiszeit.conf"
        conf.write_bytes(b"\xef\xbb\xbf[database]\nport = 5433\n")
        monkeypatch.setattr(srv, "CONFIG_FILE", conf)
        monkeypatch.setattr(srv, "_bom_warned", False)
        with caplog.at_level("WARNING"):
            assert srv.load_config() == {"database": {"port": 5433}}
            assert srv.load_config() == {"database": {"port": 5433}}
        assert caplog.text.count("UTF-8 BOM") == 1


class TestPgPortMemoized:
    """The watchdog calls pg_port() every 5 s; an edited conf must not switch
    the port of a running service (the message asks for a restart)."""

    def test_value_is_fixed_at_first_call(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        assert srv.pg_port() == 5433
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5434}})
        assert srv.pg_port() == 5433

    def test_cache_clear_rereads(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        assert srv.pg_port() == 5433
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5434}})
        srv.pg_port.cache_clear()
        assert srv.pg_port() == 5434

    def test_invalid_entry_is_not_cached(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": "abc"}})
        with pytest.raises(srv.PgConfigError):
            srv.pg_port()
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        assert srv.pg_port() == 5433


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
            "?require_auth=scram-sha-256"
        )

    def test_pg_env_windows_requires_scram(self, srv, monkeypatch):
        """S3-07: psql/pg_dump/pg_isready never answer a cleartext-password
        request of a server that took over the free port."""
        monkeypatch.setenv("PGREQUIREAUTH", "password")
        assert srv.pg_env()["PGREQUIREAUTH"] == "scram-sha-256"

    def test_require_auth_survives_sqlalchemy_url_parsing(self, srv):
        from sqlalchemy.engine import make_url
        url = make_url(srv._database_url("praxiszeit_app", "p w+%", "praxiszeit"))
        assert url.query == {"require_auth": "scram-sha-256"}
        assert url.password == "p w+%"
        assert url.port == 5433

    def test_pg_env_windows_overrides_inherited_host_and_port(self, srv, monkeypatch):
        monkeypatch.setenv("PGPORT", "9999")
        monkeypatch.setenv("PGHOST", "db.example")
        env = srv.pg_env()
        assert env["PGPORT"] == "5433"
        assert env["PGHOST"] == "localhost"

    def test_pg_isready_probe_uses_configured_port(self, srv, monkeypatch):
        captured = {}

        def _run(argv, *a, **kw):
            # Windows also runs pg_ctl status afterwards; keep the pg_isready call.
            if "pg_isready" in Path(str(argv[0])).name:
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


_FOREIGN_5433 = (
    "Port 5433 ist von einem anderen PostgreSQL belegt. In config\\praxiszeit.conf "
    "unter [database] einen freien Port eintragen (z. B. 5433) und den Dienst neu starten."
)


class TestClusterOwnership:
    """Windows: a foreign PostgreSQL answering on our port is never our cluster."""

    @pytest.fixture(autouse=True)
    def _win(self, srv, tmp_path, monkeypatch):
        pg_data = tmp_path / "db"
        pg_data.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "PG_DATA", pg_data)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)
        monkeypatch.setattr(srv, "LOG_DIR", log_dir)
        monkeypatch.setattr(srv, "load_config", lambda: {})
        monkeypatch.setattr(srv, "_win_grant_networkservice", lambda *a, **kw: None)
        monkeypatch.setattr(srv, "_win_service_exists", lambda name: True)
        monkeypatch.setattr(srv.time, "sleep", lambda s: None)
        monkeypatch.setattr(srv, "_watchdog_foreign_streak", 0)
        self.pg_data = pg_data

    def _fake(self, srv, monkeypatch, isready, status=0):
        calls = []

        def _run(argv, *a, **kw):
            import types
            argv = [str(x) for x in argv]
            calls.append(argv)
            name = Path(argv[0]).name
            rc = 0
            if name.startswith("pg_isready"):
                rc = isready
            elif name.startswith("pg_ctl") and "status" in argv:
                rc = status
            return types.SimpleNamespace(returncode=rc, stdout="", stderr="")

        monkeypatch.setattr(srv.subprocess, "run", _run)
        return calls

    def _pid_file(self, port_line):
        (self.pg_data / "postmaster.pid").write_text(
            f"1234\n{self.pg_data}\n1700000000\n{port_line}\n\nlocalhost\n", encoding="utf-8"
        )

    def test_down_when_nothing_answers(self, srv, monkeypatch):
        self._fake(srv, monkeypatch, isready=2)
        assert srv.pg_cluster_state() == "down"
        assert srv.pg_is_running() is False

    def test_own_cluster_on_default_port_is_running(self, srv, monkeypatch):
        self._fake(srv, monkeypatch, isready=0, status=0)
        self._pid_file("5432")
        assert srv.pg_cluster_state() == "own"
        assert srv.pg_is_running() is True

    def test_foreign_when_pid_file_missing(self, srv, monkeypatch):
        self._fake(srv, monkeypatch, isready=0, status=3)
        assert srv.pg_cluster_state() == "foreign"
        assert srv.pg_is_running() is False

    # Audit 2026-11-07 S3-08: only verified evidence is "foreign". pg_ctl said
    # "running" (exit 0) but postmaster.pid could not be read (virus scanner
    # lock) or is garbled -> "unknown", never exit 78.
    def test_unknown_when_status_ok_but_pid_file_missing(self, srv, monkeypatch):
        self._fake(srv, monkeypatch, isready=0, status=0)
        assert srv.pg_cluster_state() == "unknown"

    def test_unknown_when_pid_file_garbled(self, srv, monkeypatch):
        self._fake(srv, monkeypatch, isready=0, status=0)
        (self.pg_data / "postmaster.pid").write_bytes(b"\xff\xfe\x00garbage")
        assert srv.pg_cluster_state() == "unknown"

    def test_unknown_when_pg_ctl_status_times_out(self, srv, monkeypatch):
        import types

        def _run(argv, *a, **kw):
            name = Path(str(argv[0])).name
            if name.startswith("pg_ctl"):
                raise srv.subprocess.TimeoutExpired(argv, kw.get("timeout", 10))
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(srv.subprocess, "run", _run)
        self._pid_file("5432")
        assert srv.pg_cluster_state() == "unknown"
        assert srv.pg_is_running() is False

    def test_unknown_when_pg_ctl_cannot_launch(self, srv, monkeypatch):
        import types

        def _run(argv, *a, **kw):
            if Path(str(argv[0])).name.startswith("pg_ctl"):
                raise PermissionError("Zugriff verweigert")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(srv.subprocess, "run", _run)
        assert srv.pg_cluster_state() == "unknown"

    def test_unknown_when_data_dir_not_accessible(self, srv, monkeypatch):
        self._fake(srv, monkeypatch, isready=0, status=4)
        assert srv.pg_cluster_state() == "unknown"

    def test_confirmed_state_retries_unknown(self, srv, monkeypatch):
        states = iter(["unknown", "unknown", "own"])
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: next(states))
        assert srv._pg_cluster_state_confirmed() == "own"

    def test_confirmed_state_gives_up_as_unknown_not_foreign(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: "unknown")
        assert srv._pg_cluster_state_confirmed() == "unknown"

    def test_pg_start_never_raises_foreign_on_unknown(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: "unknown")
        calls = self._fake(srv, monkeypatch, isready=0)
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: "unknown")
        with pytest.raises(SystemExit) as e:
            srv.pg_start()
        assert e.value.code == 1  # NSSM restarts on 1, never the final 78
        assert any(c[:2] == ["net", "start"] for c in calls), calls

    def test_watchdog_unknown_neither_restarts_nor_exits(self, srv, monkeypatch):
        called = self._watch(srv, monkeypatch, ["foreign", "foreign", "unknown"] * 3)
        for _ in range(9):
            srv._watchdog_check_pg()
        assert called == []

    def test_foreign_when_pid_file_has_other_port(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        self._fake(srv, monkeypatch, isready=0, status=0)
        self._pid_file("5432")
        assert srv.pg_cluster_state() == "foreign"

    def test_pg_ctl_status_argv(self, srv, monkeypatch):
        calls = self._fake(srv, monkeypatch, isready=0, status=0)
        self._pid_file("5432")
        srv.pg_cluster_state()
        status_calls = [c for c in calls if "status" in c]
        assert status_calls == [
            [str(srv.pg_cmd("pg_ctl")), "status", "-D", str(self.pg_data)]
        ]

    def test_pg_start_raises_foreign_with_message(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        calls = self._fake(srv, monkeypatch, isready=0, status=3)
        with pytest.raises(srv.ForeignPostgresError) as e:
            srv.pg_start()
        assert str(e.value) == _FOREIGN_5433
        assert not any(c[:2] == ["net", "start"] for c in calls), calls

    def test_pg_start_poll_loop_raises_when_state_turns_foreign(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        states = iter(["down", "foreign", "foreign"])
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: next(states))
        self._fake(srv, monkeypatch, isready=2)
        with pytest.raises(srv.ForeignPostgresError) as e:
            srv.pg_start()
        assert str(e.value) == _FOREIGN_5433

    def test_main_exits_78_on_foreign(self, srv, monkeypatch, caplog):
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        self._fake(srv, monkeypatch, isready=0, status=3)
        monkeypatch.setattr(srv, "cmd_backup", lambda args: srv.pg_start())
        monkeypatch.setattr(sys, "argv", ["x", "backup"])
        with caplog.at_level("ERROR"), pytest.raises(SystemExit) as e:
            srv.main()
        assert e.value.code == 78
        assert _FOREIGN_5433 in caplog.text

    def _watch(self, srv, monkeypatch, states):
        seq = iter(states)
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: next(seq))
        called = []
        monkeypatch.setattr(srv, "pg_start", lambda: called.append("pg_start"))
        monkeypatch.setattr(srv, "uvicorn_stop", lambda: called.append("uvicorn_stop"))
        monkeypatch.setattr(srv, "_remove_pid", lambda: called.append("_remove_pid"))
        return called

    def test_watchdog_exits_after_three_foreign_checks(self, srv, monkeypatch, caplog):
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        called = self._watch(srv, monkeypatch, ["foreign"] * 3)
        srv._watchdog_check_pg()
        srv._watchdog_check_pg()
        assert called == []
        with caplog.at_level("ERROR"), pytest.raises(SystemExit) as e:
            srv._watchdog_check_pg()
        assert e.value.code == 78
        assert "pg_start" not in called
        assert called == ["uvicorn_stop", "_remove_pid"]
        assert _FOREIGN_5433 in caplog.text

    def test_watchdog_single_foreign_then_own_keeps_running(self, srv, monkeypatch):
        """A transient false "foreign" (pg_ctl status timeout, postmaster.pid
        briefly locked by a virus scanner) must not end the service for good."""
        called = self._watch(srv, monkeypatch, ["foreign", "own", "foreign", "foreign", "own"])
        for _ in range(5):
            srv._watchdog_check_pg()
        assert called == []

    def test_watchdog_down_resets_the_foreign_streak(self, srv, monkeypatch):
        called = self._watch(srv, monkeypatch, ["foreign", "foreign", "down", "foreign", "foreign"])
        for _ in range(5):
            srv._watchdog_check_pg()
        assert called == ["pg_start"]

    def test_pg_start_rechecks_a_foreign_verdict_once(self, srv, monkeypatch):
        states = iter(["foreign", "own"])
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: next(states))
        slept = []
        monkeypatch.setattr(srv.time, "sleep", lambda s: slept.append(s))
        calls = self._fake(srv, monkeypatch, isready=0)
        srv.pg_start()
        assert slept == [srv.FOREIGN_RECHECK_SECONDS]
        assert srv.FOREIGN_RECHECK_SECONDS == 2
        assert not any(c[:2] == ["net", "start"] for c in calls), calls

    def test_pg_start_raises_when_foreign_is_confirmed(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        states = iter(["foreign", "foreign"])
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: next(states))
        with pytest.raises(srv.ForeignPostgresError) as e:
            srv.pg_start()
        assert str(e.value) == _FOREIGN_5433

    def test_watchdog_restarts_own_cluster_when_down(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: "down")
        called = []
        monkeypatch.setattr(srv, "pg_start", lambda: called.append("pg_start"))
        srv._watchdog_check_pg()
        assert called == ["pg_start"]

    def test_watchdog_exits_when_restart_meets_foreign_server(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: "down")
        called = []

        def _start():
            raise srv.ForeignPostgresError(srv._foreign_pg_message(5433))

        monkeypatch.setattr(srv, "pg_start", _start)
        monkeypatch.setattr(srv, "uvicorn_stop", lambda: called.append("uvicorn_stop"))
        monkeypatch.setattr(srv, "_remove_pid", lambda: called.append("_remove_pid"))
        with pytest.raises(SystemExit) as e:
            srv._watchdog_check_pg()
        assert e.value.code == 78
        assert called == ["uvicorn_stop", "_remove_pid"]

    def test_watchdog_does_nothing_when_own(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: "own")
        called = []
        monkeypatch.setattr(srv, "pg_start", lambda: called.append("pg_start"))
        srv._watchdog_check_pg()
        assert called == []

    def test_pg_stop_ignores_foreign_server(self, srv, monkeypatch):
        calls = self._fake(srv, monkeypatch, isready=0, status=3)
        srv.pg_stop()
        assert not any(c[:2] == ["net", "stop"] for c in calls), calls

    def test_pg_stop_stops_own_cluster(self, srv, monkeypatch):
        calls = self._fake(srv, monkeypatch, isready=0, status=0)
        self._pid_file("5432")
        srv.pg_stop()
        assert any(c[:2] == ["net", "stop"] for c in calls), calls

    def test_unix_semantics_unchanged(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        calls = self._fake(srv, monkeypatch, isready=0, status=3)
        assert srv.pg_cluster_state() == "own"
        assert srv.pg_is_running() is True
        assert not any("status" in c for c in calls), calls

    def test_unix_down(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        self._fake(srv, monkeypatch, isready=2)
        assert srv.pg_cluster_state() == "down"


_INITDB_HEAD = "#port = 5432\t\t\t\t# (change requires restart)\n#max_connections = 100\n"
_MANAGED = (
    "\n# PraxisZeit configuration\nlisten_addresses = 'localhost'\n"
    "port = 5432\nmax_connections = 50\n"
)


class TestManagedConfPortSync:
    @staticmethod
    def _conf(tmp_path, text, crlf=False):
        p = tmp_path / "postgresql.conf"
        data = text.replace("\n", "\r\n") if crlf else text
        p.write_bytes(data.encode("utf-8"))
        return p

    def test_sync_is_noop_for_default_conf(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD + _MANAGED)
        before = p.read_bytes()
        assert srv.sync_managed_pg_port(p, 5432) is False
        assert p.read_bytes() == before

    def test_sync_rewrites_only_managed_line(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD + _MANAGED)
        assert srv.sync_managed_pg_port(p, 5433) is True
        assert p.read_text(encoding="utf-8") == (_INITDB_HEAD + _MANAGED).replace(
            "\nport = 5432\n", "\nport = 5433\n"
        )

    def test_sync_is_idempotent(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD + _MANAGED)
        assert srv.sync_managed_pg_port(p, 5433) is True
        after = p.read_bytes()
        assert srv.sync_managed_pg_port(p, 5433) is False
        assert p.read_bytes() == after

    def test_sync_writes_atomically(self, srv, tmp_path, monkeypatch):
        p = self._conf(tmp_path, "port = 5432\n")
        replaced = []
        real_replace = srv.os.replace

        def _replace(src, dst):
            replaced.append((Path(src), Path(dst)))
            real_replace(src, dst)

        monkeypatch.setattr(srv.os, "replace", _replace)
        assert srv.sync_managed_pg_port(p, 5433) is True
        assert len(replaced) == 1
        src, dst = replaced[0]
        assert dst == p and src.parent == p.parent and src != p
        assert sorted(x.name for x in tmp_path.iterdir()) == [p.name]

    def test_sync_keeps_crlf(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD + _MANAGED, crlf=True)
        assert srv.sync_managed_pg_port(p, 5433) is True
        data = p.read_bytes()
        assert b"port = 5433\r\n" in data
        assert data.count(b"\n") == data.count(b"\r\n")

    def test_sync_inserts_line_when_header_has_no_port(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD + "\n# PraxisZeit configuration\nfoo = 1\n")
        assert srv.sync_managed_pg_port(p, 5433) is True
        assert "# PraxisZeit configuration\nport = 5433\nfoo = 1\n" in p.read_text(
            encoding="utf-8"
        )

    def test_sync_appends_block_when_header_missing(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD)
        assert srv.sync_managed_pg_port(p, 5433) is True
        assert p.read_text(encoding="utf-8") == (
            _INITDB_HEAD + "\n# PraxisZeit configuration\nport = 5433\n"
        )
        q = tmp_path / "other.conf"
        q.write_bytes(_INITDB_HEAD.encode())
        assert srv.sync_managed_pg_port(q, 5432) is False
        assert q.read_bytes() == _INITDB_HEAD.encode()

    # Audit 2026-11-07 S3-15: PostgreSQL takes the LAST active port line.
    def test_sync_disables_hand_added_port_after_managed_block(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD + _MANAGED + "port = 6000\n")
        assert srv.sync_managed_pg_port(p, 5433) is True
        text = p.read_text(encoding="utf-8")
        active = [ln for ln in text.splitlines() if srv._PG_PORT_LINE_RE.match(ln)]
        assert active == ["port = 5433"]
        assert srv.PG_PORT_DISABLED_PREFIX + "port = 6000" in text
        # initdb's commented default stays untouched
        assert text.startswith("#port = 5432\t")

    def test_sync_disables_stray_port_even_on_default_port(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD + _MANAGED + "port = 6000\n")
        assert srv.sync_managed_pg_port(p, 5432) is True
        active = [ln for ln in p.read_text(encoding="utf-8").splitlines()
                  if srv._PG_PORT_LINE_RE.match(ln)]
        assert active == ["port = 5432"]

    def test_sync_disables_port_before_header_without_block(self, srv, tmp_path):
        p = self._conf(tmp_path, "port = 6000\n")
        assert srv.sync_managed_pg_port(p, 5432) is True
        assert p.read_text(encoding="utf-8") == srv.PG_PORT_DISABLED_PREFIX + "port = 6000\n"
        assert srv.sync_managed_pg_port(p, 5432) is False

    def test_sync_stray_port_keeps_crlf(self, srv, tmp_path):
        p = self._conf(tmp_path, _INITDB_HEAD + _MANAGED + "port = 6000\n", crlf=True)
        assert srv.sync_managed_pg_port(p, 5433) is True
        data = p.read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n")

    def test_auto_conf_port_is_neutralized(self, srv, tmp_path):
        auto = tmp_path / "postgresql.auto.conf"
        auto.write_bytes(b"# Do not edit this file manually!\nport = '6000'\n")
        assert srv.neutralize_auto_conf_port(auto) is True
        text = auto.read_text(encoding="utf-8")
        assert not [ln for ln in text.splitlines() if srv._PG_PORT_LINE_RE.match(ln)]
        assert srv.neutralize_auto_conf_port(auto) is False
        assert srv.neutralize_auto_conf_port(tmp_path / "missing.conf") is False

    def test_apply_pg_port_reports_change_from_auto_conf(self, srv, tmp_path, monkeypatch):
        pg_data = tmp_path / "db"
        pg_data.mkdir()
        (pg_data / "postgresql.conf").write_bytes((_INITDB_HEAD + _MANAGED).encode())
        (pg_data / "postgresql.auto.conf").write_bytes(b"port = '6000'\n")
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "PG_DATA", pg_data)
        monkeypatch.setattr(srv, "load_config", lambda: {})
        monkeypatch.setattr(srv, "_win_service_exists", lambda name: False)
        assert srv.apply_pg_port() is True

    def test_changed_port_stops_running_service_before_start(self, srv, tmp_path, monkeypatch):
        import types
        pg_data = tmp_path / "db"
        pg_data.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (pg_data / "postgresql.conf").write_bytes((_INITDB_HEAD + _MANAGED).encode())
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "PG_DATA", pg_data)
        monkeypatch.setattr(srv, "LOG_DIR", log_dir)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        monkeypatch.setattr(srv, "_win_grant_networkservice", lambda *a, **kw: None)
        monkeypatch.setattr(srv, "_win_service_exists", lambda name: True)
        monkeypatch.setattr(srv.time, "sleep", lambda s: None)
        calls = []

        def _run(argv, *a, **kw):
            argv = [str(x) for x in argv]
            calls.append(argv)
            rc = 2 if Path(argv[0]).name.startswith("pg_isready") else 0
            return types.SimpleNamespace(returncode=rc, stdout="", stderr="")

        monkeypatch.setattr(srv.subprocess, "run", _run)
        assert srv.apply_pg_port() is True
        with pytest.raises(SystemExit):
            srv.pg_start()  # nothing ever answers -> gives up after the net start
        stop = calls.index(["net", "stop", "PraxisZeit-PostgreSQL"])
        start = calls.index(["net", "start", "PraxisZeit-PostgreSQL"])
        assert stop < start
        assert "port = 5433" in (pg_data / "postgresql.conf").read_text(encoding="utf-8")

    def test_default_port_does_not_stop_service(self, srv, tmp_path, monkeypatch):
        pg_data = tmp_path / "db"
        pg_data.mkdir()
        (pg_data / "postgresql.conf").write_bytes((_INITDB_HEAD + _MANAGED).encode())
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "PG_DATA", pg_data)
        monkeypatch.setattr(srv, "load_config", lambda: {})
        monkeypatch.setattr(srv, "_win_service_exists", lambda name: True)
        calls = []
        monkeypatch.setattr(srv.subprocess, "run", lambda argv, *a, **kw: calls.append(argv))
        assert srv.apply_pg_port() is False
        assert calls == []

    def test_unix_is_noop(self, srv, tmp_path, monkeypatch):
        pg_data = tmp_path / "db"
        pg_data.mkdir()
        (pg_data / "postgresql.conf").write_bytes((_INITDB_HEAD + _MANAGED).encode())
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "PG_DATA", pg_data)
        monkeypatch.setattr(srv, "load_config", lambda: {"database": {"port": 5433}})
        assert srv.apply_pg_port() is False


_WIN = Path(__file__).resolve().parents[2] / "installer" / "windows"


def _win_text(name: str) -> str:
    raw = (_WIN / name).read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b""), f"{name} braucht CRLF"
    return raw.decode("utf-8")


class TestWindowsScripts:
    def test_uninstall_dump_uses_db_port(self):
        text = _win_text("uninstall.bat")
        dump = next(line for line in text.split("\r\n") if line.startswith('"%PG_DUMP%"'))
        assert "-p %DB_PORT%" in dump and "-h localhost" in dump, dump
        assert 'SET "DB_PORT=5432"' in text  # fallback if Python fails

    def test_install_service_sets_appexit_78(self):
        assert "AppExit 78 Exit" in _win_text("install-service.bat")

    def test_update_wizard_sets_appexit_78(self):
        assert "AppExit 78 Exit" in _win_text("update-wizard.ps1")

    def test_setup_bat_serverport_not_hardcoded(self):
        text = _win_text("setup.bat")
        assert "--serverport 5432" not in text
        assert "--serverport %DB_PORT%" in text

    def test_port_read_uses_outer_quote_pair(self):
        # cmd strips the first and last quote of a for /f command with >2 quotes
        for name in ("uninstall.bat", "setup.bat"):
            line = next(l for l in _win_text(name).split("\r\n") if "print-db-port" in l and "for /f" in l)
            assert '(`""%' in line and 'print-db-port 2>nul"`)' in line, line
            # Real cmd.exe (Windows 11 emulator, 2026-11-06): a caret inside the
            # outer quote pair stays literal, the program then receives the
            # argument "2>nul" and argparse rejects it.
            command = line[line.index("(`") + 2:line.index("`)")]
            assert "2^>nul" not in command, line
