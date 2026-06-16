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
from unittest.mock import patch

import pytest

# --- Load the hyphenated orchestrator script as a module ----------------------
# Resolves to <repo>/praxiszeit-server.py on the host (backend/tests/ → repo
# root). The docker backend image only copies the backend/ build context to
# /app, so the orchestrator script is NOT present there — skip the whole module
# rather than erroring 44× when it is unreachable (e.g. `docker compose exec
# backend pytest`, which local-ci uses). These tests run on the host / native
# build env, mirroring how test_tenant_rls/test_concurrency are env-scoped.
_SERVER_PATH = Path(__file__).resolve().parents[2] / "praxiszeit-server.py"

pytestmark = pytest.mark.skipif(
    not _SERVER_PATH.exists(),
    reason=f"praxiszeit-server.py not reachable at {_SERVER_PATH} "
    "(native orchestrator not present, e.g. inside the docker backend container)",
)


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


# --- VC++ runtime diagnostic (Windows DLL-load failure) ----------------------

class TestVcRuntimeDiagnostic:
    """Field report 2026-05-26: on a fresh Windows the bundled PostgreSQL
    binaries could not be loaded because the Microsoft Visual C++ Redistributable
    was missing (setup.bat ran the EDB installer with ``--install_runtimes 0``).
    ``initdb.exe`` exited with 3221225781 = 0xC0000135 (STATUS_DLL_NOT_FOUND)
    and the NSSM service looped forever on an opaque ``CalledProcessError``.
    ``_check_pg_launchable`` turns that exit code into a clear, actionable error
    so the service log says *what to install* instead of dumping a stack trace.
    """

    def test_dll_not_found_raises_actionable_error(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        with pytest.raises(srv.PgRuntimeMissingError) as exc:
            srv._check_pg_launchable(3221225781, "initdb.exe")
        msg = str(exc.value)
        assert "initdb.exe" in msg                 # names the failing binary
        assert srv.VC_REDIST_URL in msg            # points at the actual fix

    def test_signed_int_variant_also_detected(self, srv, monkeypatch):
        # Some Python/Windows combos surface the NTSTATUS as its signed twin.
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        with pytest.raises(srv.PgRuntimeMissingError):
            srv._check_pg_launchable(-1073741515, "postgres.exe")

    def test_dll_init_failed_also_detected(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        with pytest.raises(srv.PgRuntimeMissingError):
            srv._check_pg_launchable(0xC0000142, "initdb.exe")

    def test_success_is_noop(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        srv._check_pg_launchable(0, "initdb.exe")  # must not raise

    def test_ordinary_failure_is_noop(self, srv, monkeypatch):
        # A normal initdb failure (e.g. "directory not empty", rc=1) must fall
        # through to CalledProcessError, NOT be mis-reported as a missing runtime.
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        srv._check_pg_launchable(1, "initdb.exe")  # must not raise

    def test_non_windows_is_noop(self, srv, monkeypatch):
        # The same magic number on Linux means something else entirely.
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        srv._check_pg_launchable(3221225781, "initdb")  # must not raise


# --- cmd_start: lost-credentials recovery ------------------------------------

class TestLostCredentialsFailFast:
    """Regression guard for the M5 audit finding: when ``config/.db-credentials``
    is lost but the data directory still carries our cluster marker, the old
    code path would call ``pg_setup_database`` against the scram-hardened
    cluster — which then hangs or errors opaquely. ``cmd_start`` must instead
    fail fast with a clear pointer to the recovery docs.
    """

    def _wire_paths(self, srv, tmp_path, monkeypatch, *, marker, creds):
        data = tmp_path / "db"
        data.mkdir()
        # Make ``any(PG_DATA.iterdir())`` true so ``needs_initdb`` is False.
        (data / "PG_VERSION").write_text("16\n")
        if marker:
            (data / srv.PG_CLUSTER_MARKER).write_text("praxiszeit-managed\n", encoding="utf-8")
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        if creds:
            (config_dir / ".db-credentials").write_text("SUPERUSER_PASSWORD=x\nAPP_PASSWORD=y\n")
        monkeypatch.setattr(srv, "PG_DATA", data)
        monkeypatch.setattr(srv, "CONFIG_DIR", config_dir)
        return data, config_dir

    def test_marker_present_creds_missing_exits_with_recovery_pointer(
        self, srv, tmp_path, monkeypatch, caplog
    ):
        self._wire_paths(srv, tmp_path, monkeypatch, marker=True, creds=False)
        monkeypatch.setattr(srv, "load_config", lambda: {})
        # Guard: if the fail-fast branch is missed, the next step would touch
        # the real cluster. Make the rest of cmd_start explode loudly instead.
        def _boom(*a, **kw):
            raise AssertionError("cmd_start fell through past the fail-fast branch")
        monkeypatch.setattr(srv, "pg_init", _boom)
        monkeypatch.setattr(srv, "pg_start", _boom)
        monkeypatch.setattr(srv, "pg_setup_database", _boom)
        monkeypatch.setattr(srv, "_quarantine_pg_data", _boom)

        with caplog.at_level("ERROR"), pytest.raises(SystemExit) as exc_info:
            srv.cmd_start(None)

        assert exc_info.value.code == 1
        # Must point the operator at the docs, not at a scram error.
        joined = " ".join(rec.message for rec in caplog.records)
        assert ".db-credentials" in joined
        assert "Disaster Recovery" in joined
        assert "INSTALL-NATIVE.md" in joined

    def test_marker_absent_creds_missing_still_quarantines(
        self, srv, tmp_path, monkeypatch
    ):
        """Sanity guard: the new fail-fast branch must NOT swallow the existing
        foreign-cluster recovery path. Marker absent + creds missing = the
        directory looks foreign, so cmd_start should still call the quarantine
        helper rather than aborting.
        """
        data, _ = self._wire_paths(srv, tmp_path, monkeypatch, marker=False, creds=False)
        monkeypatch.setattr(srv, "load_config", lambda: {})

        called = {"quarantine": 0, "init": 0, "start": 0, "setup": 0}

        def _quarantine():
            called["quarantine"] += 1
            backup = data.parent / "db.foreign-test"
            data.rename(backup)
            data.mkdir()
            return backup

        monkeypatch.setattr(srv, "_quarantine_pg_data", _quarantine)
        monkeypatch.setattr(srv, "pg_is_running", lambda: False)
        monkeypatch.setattr(srv, "pg_stop", lambda: None)
        # Stop cmd_start before it leaves the lifecycle section we care about.
        def _stop_here(*a, **kw):
            called["init"] += 1
            raise RuntimeError("STOP_AT_PG_INIT")
        monkeypatch.setattr(srv, "pg_init", _stop_here)

        with pytest.raises(RuntimeError, match="STOP_AT_PG_INIT"):
            srv.cmd_start(None)

        assert called["quarantine"] == 1
        assert called["init"] == 1


# --- M3: granular Windows ACLs (LOG_DIR != PG_DATA) --------------------------

class TestBuildIcaclsGrantArgs:
    """Pure-function tests for the icacls argv builder. Right-sizing the LOG_DIR
    ACL to Modify (instead of Full Control) is M3's anti-forensics hardening: a
    compromised NetworkService process must not be able to rewrite ACLs on the
    audit trail.
    """

    def test_default_is_full_control_for_backward_compat(self, srv, tmp_path):
        # Older call sites still invoke _win_grant_networkservice(path) without
        # a perms kwarg; the default must remain Full Control so PG_DATA keeps
        # working without per-caller updates.
        args = srv._build_icacls_grant_args(tmp_path)
        assert args[0] == "icacls"
        assert args[1] == str(tmp_path)
        assert "/grant" in args
        assert "*S-1-5-20:(OI)(CI)F" in args
        assert "/T" in args
        assert "/Q" in args

    def test_modify_perms_for_log_dir(self, srv, tmp_path):
        # M3: LOG_DIR gets (M)odify — no permission-change, no take-ownership.
        args = srv._build_icacls_grant_args(tmp_path, perms="M")
        assert "*S-1-5-20:(OI)(CI)M" in args
        # Negative guard: no accidental Full Control slipped in.
        assert "*S-1-5-20:(OI)(CI)F" not in args

    @pytest.mark.parametrize("perms,expected_ace", [
        ("F", "*S-1-5-20:(OI)(CI)F"),
        ("M", "*S-1-5-20:(OI)(CI)M"),
        ("R,W", "*S-1-5-20:(OI)(CI)R,W"),
    ])
    def test_perms_round_trip_into_ace(self, srv, tmp_path, perms, expected_ace):
        args = srv._build_icacls_grant_args(tmp_path, perms=perms)
        assert expected_ace in args

    def test_uses_locale_independent_networkservice_sid(self, srv, tmp_path):
        # S-1-5-20 is the well-known SID for NT AUTHORITY\NetworkService and
        # works on German/English/etc. Windows installations. Regression guard:
        # don't accidentally switch to the localized name "NetworkService"
        # (which breaks on de-DE Windows).
        args = srv._build_icacls_grant_args(tmp_path)
        joined = " ".join(args)
        assert "S-1-5-20" in joined
        assert "NetworkService" not in joined  # the localizable form, not the SID


class TestWinGrantNetworkservice:
    """The thin subprocess wrapper. We mock subprocess.run so the tests don't
    actually try to run icacls on Linux CI.
    """

    def test_log_dir_call_site_uses_modify_perms(self, srv, tmp_path):
        with patch.object(srv.subprocess, "run") as mock_run:
            srv._win_grant_networkservice(tmp_path, perms="M")
        mock_run.assert_called_once()
        argv = mock_run.call_args.args[0]
        assert "*S-1-5-20:(OI)(CI)M" in argv

    def test_pg_data_call_site_keeps_full_control(self, srv, tmp_path):
        with patch.object(srv.subprocess, "run") as mock_run:
            srv._win_grant_networkservice(tmp_path, perms="F")
        argv = mock_run.call_args.args[0]
        assert "*S-1-5-20:(OI)(CI)F" in argv

    def test_default_is_full_control(self, srv, tmp_path):
        # Backwards-compat: no perms kwarg = (F)ull (matches the pre-M3 signature).
        with patch.object(srv.subprocess, "run") as mock_run:
            srv._win_grant_networkservice(tmp_path)
        argv = mock_run.call_args.args[0]
        assert "*S-1-5-20:(OI)(CI)F" in argv


# --- M4: cmd_start branching matrix ------------------------------------------

class TestForeignPgIsolation:
    """#174: a foreign system PostgreSQL listening on TCP localhost:5432 must
    NEVER be mistaken for our bundled cluster.

    Field repro (Debian/Ubuntu host with system PG on :5432): ``pg_is_running``
    TCP-probed localhost:5432, got a false positive from the foreign server,
    so ``pg_start`` returned early ("already running") and our own cluster was
    never started. ``pg_setup_database`` then ran psql against a cluster that
    wasn't there (no socket) / the wrong one and crashed before writing
    ``.db-credentials`` → permanent crash-loop.

    Fix: on Unix the bundled cluster is socket-only (``listen_addresses = ''``)
    in ``DATA_DIR/run``. The running-check and every connection URL must target
    that unix socket, never TCP :5432. Windows has no unix sockets and keeps
    its TCP service unchanged.
    """

    def _capture_run(self, srv, monkeypatch):
        captured = {}

        def _run(argv, *a, **kw):
            captured["argv"] = list(argv)
            from unittest.mock import MagicMock
            m = MagicMock()
            m.returncode = 0
            return m

        monkeypatch.setattr(srv.subprocess, "run", _run)
        return captured

    def test_pg_is_running_unix_probes_own_socket_not_tcp(
        self, srv, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)
        captured = self._capture_run(srv, monkeypatch)

        srv.pg_is_running()

        argv = captured["argv"]
        # -h must point at OUR socket directory, never a TCP host that a foreign
        # system PostgreSQL on :5432 would happily answer.
        assert str(tmp_path / "run") in argv, f"socket dir not in probe: {argv}"
        assert "localhost" not in argv, f"must not TCP-probe localhost: {argv}"

    def test_pg_is_running_windows_uses_tcp_localhost(self, srv, monkeypatch):
        # Windows has no unix sockets; the bundled cluster runs as a TCP service.
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        captured = self._capture_run(srv, monkeypatch)

        srv.pg_is_running()

        assert "localhost" in captured["argv"]

    def test_database_url_unix_uses_socket(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)

        url = srv._database_url("praxiszeit_app", "p@ss/w0rd", "praxiszeit")

        assert "@localhost:5432" not in url, f"must not use TCP :5432: {url}"
        assert "host=" in url, f"must connect via unix socket dir: {url}"
        assert "run" in url, f"socket dir DATA_DIR/run missing: {url}"
        # password special chars must be url-encoded (psycopg2/SQLAlchemy)
        assert "p%40ss%2Fw0rd" in url

    def test_database_url_windows_uses_tcp(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)

        url = srv._database_url("praxiszeit_app", "pw", "praxiszeit")

        assert url == "postgresql://praxiszeit_app:pw@localhost:5432/praxiszeit"

    def test_pg_init_unix_is_socket_only(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        pg_data = tmp_path / "db"
        pg_data.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(srv, "PG_DATA", pg_data)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)
        monkeypatch.setattr(srv, "BIN_DIR", tmp_path / "bin")
        monkeypatch.setattr(srv, "LOG_DIR", log_dir)

        import types

        def _fake_run(*a, **kw):
            return types.SimpleNamespace(returncode=0, check_returncode=lambda: None)

        monkeypatch.setattr(srv.subprocess, "run", _fake_run)

        srv.pg_init({})

        conf = (pg_data / "postgresql.conf").read_text()
        # Socket-only: no TCP listener at all, so a foreign PG already bound to
        # :5432 can never collide with our cluster (#174).
        assert "listen_addresses = ''" in conf, conf
        assert "listen_addresses = 'localhost'" not in conf, conf
        # The socket directory must still be our own data dir.
        assert f"unix_socket_directories = '{tmp_path / 'run'}'" in conf


class TestDecidePgInitAction:
    """Pure-function unit tests for the cmd_start branch matrix. Each row in
    the table in :func:`_decide_pg_init_action`'s docstring gets one test.
    """

    def test_empty_data_dir_means_init(self, srv):
        # Empty PGDATA → first run.
        assert srv._decide_pg_init_action(
            pg_data_populated=False, has_marker=False, has_credentials=False,
        ) == srv.PG_ACTION_INIT

    @pytest.mark.parametrize("has_marker,has_credentials", [
        (True, True), (True, False), (False, True), (False, False),
    ])
    def test_empty_data_dir_init_is_unaffected_by_marker_or_creds(
        self, srv, has_marker, has_credentials,
    ):
        # When PG_DATA is empty, the other inputs don't matter — we always init.
        assert srv._decide_pg_init_action(
            pg_data_populated=False,
            has_marker=has_marker,
            has_credentials=has_credentials,
        ) == srv.PG_ACTION_INIT

    def test_marker_and_creds_means_start_existing(self, srv):
        # Healthy PraxisZeit cluster — just start it.
        assert srv._decide_pg_init_action(
            pg_data_populated=True, has_marker=True, has_credentials=True,
        ) == srv.PG_ACTION_START_EXISTING

    def test_marker_but_no_creds_fails_fast(self, srv):
        # M5 regression guard: NEVER quarantine our own cluster. Surface the
        # recovery doc instead of running pg_setup_database against a scram
        # cluster whose password we no longer know.
        assert srv._decide_pg_init_action(
            pg_data_populated=True, has_marker=True, has_credentials=False,
        ) == srv.PG_ACTION_FAIL_NO_CREDS

    def test_no_marker_but_creds_backfills(self, srv):
        # Pre-1.5.1 upgrade path: data + creds, no marker. Adopt the cluster
        # by writing the marker, then start it (do NOT reinit).
        assert srv._decide_pg_init_action(
            pg_data_populated=True, has_marker=False, has_credentials=True,
        ) == srv.PG_ACTION_BACKFILL_MARKER

    def test_no_marker_no_creds_quarantines(self, srv):
        # Foreign / EDB-installer leftover. Move it aside (never delete) and
        # init a clean cluster.
        assert srv._decide_pg_init_action(
            pg_data_populated=True, has_marker=False, has_credentials=False,
        ) == srv.PG_ACTION_QUARANTINE_AND_INIT


class TestCmdStartBranching:
    """Integration tests for the self-healing decision tree in ``cmd_start``.

    We build real filesystem fixtures (tmp_path) so the "does PGDATA exist /
    is it populated / is the marker present / is .db-credentials present"
    detection runs against actual paths — the bug class we're guarding
    against is precisely a path-detection mistake.

    Subprocess-heavy helpers (pg_init, pg_start, pg_setup_database,
    pg_load_credentials) are stubbed so the test never tries to start a real
    PostgreSQL. Instead we assert which side effects ``cmd_start`` chose.
    """

    @staticmethod
    def _make_paths(srv, tmp_path, monkeypatch, *, populate, marker, creds):
        data = tmp_path / "db"
        data.mkdir()
        if populate:
            (data / "PG_VERSION").write_text("16\n")
        if marker:
            (data / srv.PG_CLUSTER_MARKER).write_text(
                "praxiszeit-managed\n", encoding="utf-8"
            )
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        if creds:
            (config_dir / ".db-credentials").write_text(
                "SUPERUSER_PASSWORD=x\nAPP_PASSWORD=y\n"
            )
        monkeypatch.setattr(srv, "PG_DATA", data)
        monkeypatch.setattr(srv, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(srv, "load_config", lambda: {})
        return data, config_dir

    @staticmethod
    def _record_calls(srv, monkeypatch):
        """Replace the side-effecting helpers with recorders. Returns a dict
        that the test can assert against."""
        calls = {
            "pg_init": 0, "pg_start": 0, "pg_setup_database": 0,
            "quarantine": 0, "pg_stop": 0, "win_unregister": 0,
            "env_set": False,
        }

        def _pg_init(config):
            calls["pg_init"] += 1

        def _pg_start():
            calls["pg_start"] += 1

        def _pg_setup_database(config):
            calls["pg_setup_database"] += 1

        def _quarantine():
            calls["quarantine"] += 1
            # Mirror the real quarantine behaviour: PG_DATA must end up empty.
            for p in list(srv.PG_DATA.iterdir()):
                if p.is_dir():
                    # remove non-empty dirs too
                    import shutil
                    shutil.rmtree(p)
                else:
                    p.unlink()
            return srv.PG_DATA.parent / "db.foreign-test"

        def _pg_stop():
            calls["pg_stop"] += 1

        def _win_unregister():
            calls["win_unregister"] += 1

        def _pg_load_credentials():
            calls["env_set"] = True
            return "su-pw", "app-pw"

        # Stop cmd_start before it tries to spawn uvicorn / Alembic.
        def _stop_signal(*a, **kw):
            raise RuntimeError("STOP_BEFORE_UVICORN")

        monkeypatch.setattr(srv, "pg_init", _pg_init)
        monkeypatch.setattr(srv, "pg_start", _pg_start)
        monkeypatch.setattr(srv, "pg_setup_database", _pg_setup_database)
        monkeypatch.setattr(srv, "_quarantine_pg_data", _quarantine)
        monkeypatch.setattr(srv, "pg_stop", _pg_stop)
        monkeypatch.setattr(srv, "pg_is_running", lambda: False)
        monkeypatch.setattr(srv, "_win_pg_unregister", _win_unregister)
        monkeypatch.setattr(srv, "_win_service_exists", lambda name: False)
        monkeypatch.setattr(srv, "pg_load_credentials", _pg_load_credentials)
        # cmd_start's later steps spawn uvicorn and run Alembic. Stub everything
        # past the lifecycle section so the test stays hermetic and aborts the
        # moment cmd_start tries to leave the section under test.
        monkeypatch.setattr(srv, "run_migrations", _stop_signal)
        monkeypatch.setattr(srv, "uvicorn_start", _stop_signal)
        return calls

    def test_scenario_a_empty_pgdata_initialises(self, srv, tmp_path, monkeypatch):
        """A: empty PGDATA → init + setup + start."""
        data, _ = self._make_paths(
            srv, tmp_path, monkeypatch, populate=False, marker=False, creds=False,
        )
        calls = self._record_calls(srv, monkeypatch)

        with pytest.raises(RuntimeError, match="STOP_BEFORE_UVICORN"):
            srv.cmd_start(None)

        assert calls["pg_init"] == 1
        assert calls["pg_start"] == 1
        assert calls["pg_setup_database"] == 1, "init path must bootstrap roles"
        assert calls["quarantine"] == 0, "empty PGDATA must NOT be quarantined"

    def test_scenario_b_marker_and_creds_just_starts(self, srv, tmp_path, monkeypatch):
        """B: PGDATA + marker + creds → start_existing (no init, no setup,
        no quarantine)."""
        self._make_paths(
            srv, tmp_path, monkeypatch, populate=True, marker=True, creds=True,
        )
        calls = self._record_calls(srv, monkeypatch)

        with pytest.raises(RuntimeError, match="STOP_BEFORE_UVICORN"):
            srv.cmd_start(None)

        assert calls["pg_init"] == 0, "healthy cluster must not be reinitialized"
        assert calls["pg_setup_database"] == 0, "healthy cluster must not be re-bootstrapped"
        assert calls["quarantine"] == 0, "healthy cluster must not be quarantined"
        assert calls["pg_start"] == 1
        assert calls["env_set"] is True, "existing creds must be loaded"

    def test_scenario_c_marker_no_creds_fails_fast(self, srv, tmp_path, monkeypatch, caplog):
        """C: PGDATA + marker + NO creds → fail-fast with recovery pointer.

        Regression guard for M5: NEVER quarantine our own cluster. The marker
        proves it's ours; reiniting would destroy real customer data.
        """
        self._make_paths(
            srv, tmp_path, monkeypatch, populate=True, marker=True, creds=False,
        )
        calls = self._record_calls(srv, monkeypatch)

        with caplog.at_level("ERROR"), pytest.raises(SystemExit) as exc_info:
            srv.cmd_start(None)

        assert exc_info.value.code == 1
        assert calls["pg_init"] == 0, "must NOT reinit our own cluster"
        assert calls["quarantine"] == 0, "must NEVER quarantine our own cluster"
        assert calls["pg_start"] == 0, "must not even try to start it"
        joined = " ".join(rec.message for rec in caplog.records)
        assert "Disaster Recovery" in joined
        assert "INSTALL-NATIVE.md" in joined

    def test_scenario_d_no_marker_no_creds_quarantines_and_reinits(
        self, srv, tmp_path, monkeypatch
    ):
        """D: PGDATA + NO marker + NO creds → foreign cluster → quarantine + init."""
        self._make_paths(
            srv, tmp_path, monkeypatch, populate=True, marker=False, creds=False,
        )
        calls = self._record_calls(srv, monkeypatch)

        with pytest.raises(RuntimeError, match="STOP_BEFORE_UVICORN"):
            srv.cmd_start(None)

        assert calls["quarantine"] == 1, "foreign cluster must be moved aside"
        assert calls["pg_init"] == 1, "fresh cluster must be initialized after quarantine"
        assert calls["pg_setup_database"] == 1, "fresh cluster must be bootstrapped"
        assert calls["pg_start"] == 1

    def test_scenario_e_no_marker_with_creds_backfills(self, srv, tmp_path, monkeypatch):
        """E: PGDATA + NO marker + creds → pre-1.5.1 upgrade → backfill marker, start.

        Critical: must NOT quarantine (would destroy production data!) and must
        NOT reinit. Just adopt the cluster by writing the marker, then start.
        """
        data, _ = self._make_paths(
            srv, tmp_path, monkeypatch, populate=True, marker=False, creds=True,
        )
        calls = self._record_calls(srv, monkeypatch)

        with pytest.raises(RuntimeError, match="STOP_BEFORE_UVICORN"):
            srv.cmd_start(None)

        assert calls["quarantine"] == 0, "pre-marker upgrade must NEVER quarantine"
        assert calls["pg_init"] == 0, "pre-marker upgrade must NOT reinit"
        assert calls["pg_setup_database"] == 0, "creds already exist; no bootstrap"
        assert calls["pg_start"] == 1
        # Marker must now be on disk so the next start sees scenario B.
        assert (data / srv.PG_CLUSTER_MARKER).is_file(), "marker must be backfilled"
