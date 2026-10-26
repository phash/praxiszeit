"""Security hardening of the native orchestrator ``praxiszeit-server.py`` and
its installers (security review 2026-10).

1. Windows: the install directory (C:\\PraxisZeit) inherited "Authenticated
   Users: Modify" from C:\\ while the service runs as LocalSystem — code
   execution as SYSTEM and readable dumps. ``_build_install_acl_plan`` /
   ``_harden_install_dir`` / ``_ensure_install_dir_acl`` + setup.bat.
3. Backups were written with plain open() (0644 under umask 022); the systemd
   units had no UMask.
4. ``.db-credentials`` was written first and restricted afterwards.
5. DB passwords were passed on the psql command line (ALTER ROLE ... -c).
6. initdb ran with ``-A trust`` and only later switched to scram.
7. Native installs ran with ENVIRONMENT=development (/docs etc. open).

Like test_native_pg_lifecycle.py the module skips when the orchestrator is
not reachable (docker backend image without the repo mount).
"""
import ast
import importlib.util
import os
import stat
import sys
import types
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SERVER_PATH = _REPO / "praxiszeit-server.py"

pytestmark = pytest.mark.skipif(
    not _SERVER_PATH.exists(),
    reason=f"praxiszeit-server.py not reachable at {_SERVER_PATH}",
)


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("praxiszeit_server_hardening", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ok(**kw):
    return types.SimpleNamespace(returncode=0, stdout="", stderr="",
                                 check_returncode=lambda: None, **kw)


# --- 6. initdb: scram from the start, password via restricted pwfile ---------

class TestInitdbScramFromTheStart:
    def _wire(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        pg_data = tmp_path / "data" / "db"
        pg_data.mkdir(parents=True)
        monkeypatch.setattr(srv, "PG_DATA", pg_data)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path / "data")
        monkeypatch.setattr(srv, "BIN_DIR", tmp_path / "bin")
        monkeypatch.setattr(srv, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path / "config")
        return pg_data

    def test_initdb_uses_scram_and_pwfile_not_trust(self, srv, tmp_path, monkeypatch):
        self._wire(srv, tmp_path, monkeypatch)
        seen = {}

        def _fake_run(cmd, *a, **kw):
            seen["cmd"] = list(cmd)
            pw_arg = next(c for c in cmd if c.startswith("--pwfile="))
            pwfile = Path(pw_arg.split("=", 1)[1])
            seen["pw_content"] = pwfile.read_text()
            seen["pw_mode"] = stat.S_IMODE(pwfile.stat().st_mode)
            return _ok()

        monkeypatch.setattr(srv.subprocess, "run", _fake_run)
        srv.pg_init({}, "geheim-123")

        cmd = seen["cmd"]
        assert "trust" not in cmd and "-A" not in cmd
        assert "--auth=scram-sha-256" in cmd
        # The password itself is never part of the argument vector.
        assert not any("geheim-123" in c for c in cmd)
        assert seen["pw_content"].strip() == "geheim-123"
        assert seen["pw_mode"] == 0o600
        # ... and the file is gone afterwards.
        assert not (tmp_path / "config" / srv.INITDB_PWFILE_NAME).exists()

    def test_pwfile_removed_even_if_initdb_fails(self, srv, tmp_path, monkeypatch):
        self._wire(srv, tmp_path, monkeypatch)

        def _fail(cmd, *a, **kw):
            def _raise():
                raise srv.subprocess.CalledProcessError(1, cmd)
            return types.SimpleNamespace(returncode=1, check_returncode=_raise)

        monkeypatch.setattr(srv.subprocess, "run", _fail)
        with pytest.raises(srv.subprocess.CalledProcessError):
            srv.pg_init({}, "geheim-123")
        assert not (tmp_path / "config" / srv.INITDB_PWFILE_NAME).exists()

    def test_resolve_db_passwords_prefers_config(self, srv):
        su, app = srv.resolve_db_passwords(
            {"database": {"superuser_password": "a", "app_password": "b"}}
        )
        assert (su, app) == ("a", "b")

    def test_resolve_db_passwords_generates_random(self, srv):
        su, app = srv.resolve_db_passwords({})
        assert len(su) == 64 and len(app) == 64 and su != app

    def test_cmd_start_hands_the_same_password_to_initdb_and_setup(
        self, srv, tmp_path, monkeypatch
    ):
        pg_data = self._wire(srv, tmp_path, monkeypatch)
        (tmp_path / "config").mkdir()
        monkeypatch.setattr(srv, "load_config", lambda: {})
        monkeypatch.setattr(srv, "_ensure_install_dir_acl", lambda: None)
        got = {}

        def _pg_init(config, su_password):
            got["init"] = su_password
            (pg_data / "PG_VERSION").write_text("18\n")

        def _setup(config, su_password, app_password):
            got["setup"] = (su_password, app_password)
            raise RuntimeError("STOP")

        monkeypatch.setattr(srv, "pg_init", _pg_init)
        monkeypatch.setattr(srv, "pg_start", lambda: None)
        monkeypatch.setattr(srv, "pg_setup_database", _setup)
        with pytest.raises(RuntimeError, match="STOP"):
            srv.cmd_start(None)
        assert got["init"] == got["setup"][0]
        assert got["setup"][1] and got["setup"][1] != got["init"]


# --- 5. passwords never on the psql command line -----------------------------

class TestSetupDatabaseKeepsPasswordsOffArgv:
    def _run(self, srv, tmp_path, monkeypatch, reload_rc=0):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "PG_DATA", tmp_path / "db")
        (tmp_path / "db").mkdir()
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)
        monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path / "config")
        monkeypatch.setattr(srv, "BACKEND_DIR", tmp_path / "backend")
        monkeypatch.setattr(srv.os, "environ", dict(os.environ))
        calls = []

        def _fake_run(cmd, *a, **kw):
            calls.append((list(cmd), kw))
            if "reload" in cmd:
                return types.SimpleNamespace(returncode=reload_rc, stdout="",
                                             stderr="could not send signal")
            return _ok()

        monkeypatch.setattr(srv.subprocess, "run", _fake_run)
        srv.pg_setup_database({}, "SU-SECRET-PW", "APP-SECRET-PW")
        return calls

    def test_no_password_in_any_argv(self, srv, tmp_path, monkeypatch):
        calls = self._run(srv, tmp_path, monkeypatch)
        for cmd, _ in calls:
            joined = " ".join(cmd)
            assert "SU-SECRET-PW" not in joined
            assert "APP-SECRET-PW" not in joined

    def test_alter_role_goes_through_stdin(self, srv, tmp_path, monkeypatch):
        calls = self._run(srv, tmp_path, monkeypatch)
        stdin_sql = [kw.get("input") or "" for _, kw in calls]
        assert any("ALTER ROLE praxiszeit_app PASSWORD 'APP-SECRET-PW'" in s for s in stdin_sql)
        assert any("ALTER ROLE praxiszeit PASSWORD 'SU-SECRET-PW'" in s for s in stdin_sql)
        for cmd, kw in calls:
            if kw.get("input"):
                assert cmd[-2:] == ["-f", "-"]
                assert "ON_ERROR_STOP=1" in cmd

    def test_psql_authenticates_via_pgpassword(self, srv, tmp_path, monkeypatch):
        calls = self._run(srv, tmp_path, monkeypatch)
        psql_calls = [kw for cmd, kw in calls if Path(cmd[0]).name.startswith("psql")]
        assert psql_calls
        assert all(kw["env"].get("PGPASSWORD") == "SU-SECRET-PW" for kw in psql_calls)

    def test_failed_reload_is_reported_not_ignored(self, srv, tmp_path, monkeypatch, caplog):
        with caplog.at_level("WARNING"):
            self._run(srv, tmp_path, monkeypatch, reload_rc=1)
        assert any("pg_ctl reload failed" in r.message for r in caplog.records)


# --- 4. .db-credentials restricted before the secrets are written ------------

class TestCredentialsFileRestrictedBeforeWrite:
    def test_permissions_set_while_file_is_empty(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path)
        sizes = []
        real = srv._restrict_file_permissions

        def _spy(path):
            sizes.append(path.stat().st_size)
            real(path)

        monkeypatch.setattr(srv, "_restrict_file_permissions", _spy)
        srv._save_credentials("su", "app")
        creds = tmp_path / ".db-credentials"
        assert sizes == [0]
        assert creds.read_text() == "SUPERUSER_PASSWORD=su\nAPP_PASSWORD=app\n"
        if os.name == "posix":
            assert stat.S_IMODE(creds.stat().st_mode) == 0o600
        monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path)
        assert srv.pg_load_credentials() == ("su", "app")


# --- 3. backups 0600 ----------------------------------------------------------

@pytest.mark.skipif(os.name != "posix", reason="Unix file mode")
def test_backup_file_is_0600_despite_umask(srv, tmp_path, monkeypatch):
    import io
    monkeypatch.setattr(srv, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(srv, "pg_load_credentials", lambda: ("pw", "app"))

    class _FakeDump:
        def __init__(self, *a, **kw):
            self.stdout = io.BytesIO(b"-- dump\n" * 100)
            self.returncode = 0

        def wait(self):
            return 0

    monkeypatch.setattr(srv.subprocess, "Popen", _FakeDump)
    old = os.umask(0o022)
    try:
        backup = srv.create_backup({})
    finally:
        os.umask(old)
    assert backup is not None and backup.exists()
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


# --- 7. production mode on native installs -----------------------------------

class TestNativeEnvironment:
    def test_default_is_production(self, srv):
        env = {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "x" * 32}
        assert srv.native_environment(env) == "production"

    def test_explicit_value_wins(self, srv):
        env = {"ENVIRONMENT": "development", "ADMIN_PASSWORD": "x" * 32}
        assert srv.native_environment(env) == "development"

    @pytest.mark.parametrize("pw", ["Admin2025!", "admin123", "Kurz-10Zch", "12345678901"])
    def test_weak_admin_password_keeps_development(self, srv, pw, caplog):
        # Production would abort the backend start on these (main.py) — the
        # orchestrator must not turn an update into a crash loop.
        with caplog.at_level("WARNING"):
            assert srv.native_environment({"ADMIN_PASSWORD": pw}) == "development"
        assert any("development" in r.message for r in caplog.records)

    def test_weak_password_of_other_username_is_no_blocker(self, srv):
        env = {"ADMIN_USERNAME": "chefin", "ADMIN_PASSWORD": "admin"}
        assert srv.native_environment(env) == "production"

    def test_conf_key_maps_to_environment(self, srv):
        env = {}
        srv.apply_config_env({"server": {"environment": "development"}}, env)
        assert env["ENVIRONMENT"] == "development"

    def test_weak_list_matches_backend(self, srv):
        tree = ast.parse((_REPO / "backend" / "app" / "main.py").read_text(encoding="utf-8"))
        backend = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_WEAK_ADMIN_PASSWORDS" for t in node.targets
            ):
                backend = {elt.value for elt in node.value.args[0].elts}
        assert backend == set(srv._BACKEND_WEAK_ADMIN_PASSWORDS)
        main_src = (_REPO / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        assert f"len(settings.ADMIN_PASSWORD) < {srv._BACKEND_MIN_ADMIN_PASSWORD_LEN}" in main_src


# --- 1. Windows: install directory ACL ---------------------------------------

class TestInstallAclPlan:
    @pytest.fixture
    def plan(self, srv):
        base = Path("C:/PraxisZeit")
        return srv._build_install_acl_plan(base, base / "data", base / "logs", base / "config")

    def _by_path(self, plan, name):
        return next(p for p in plan if Path(p["path"]).name == name)

    def test_root_first_and_all_private_dirs_covered(self, plan):
        assert [Path(p["path"]).name for p in plan] == ["PraxisZeit", "data", "logs", "config"]

    def test_only_sids_never_localized_names(self, plan):
        for step in plan:
            for cmd in step["grants"] + step["removes"]:
                principal = cmd[3]
                assert principal.startswith("*S-1-"), cmd

    def test_every_dir_drops_inheritance(self, plan):
        for step in plan:
            assert step["protect"][2:] == ["/inheritance:r"]

    def test_no_recursive_or_owner_switches(self, plan):
        # /T would walk into a bin\postgresql junction (system PostgreSQL).
        for step in plan:
            for cmd in step["grants"] + step["removes"] + [step["protect"]]:
                assert "/T" not in cmd and "/setowner" not in cmd

    def test_root_users_read_execute_only(self, plan):
        root = plan[0]
        users = [c for c in root["grants"] if c[3].startswith("*S-1-5-32-545:")]
        assert users == [["icacls", str(Path("C:/PraxisZeit")), "/grant:r", "*S-1-5-32-545:(OI)(CI)RX"]]
        # Authenticated Users / Everyone explicitly removed.
        removed = {c[3] for c in root["removes"]}
        assert removed == {"*S-1-5-11", "*S-1-1-0"}

    def test_system_and_admins_full_everywhere(self, plan):
        for step in plan:
            grants = {c[3] for c in step["grants"]}
            assert "*S-1-5-18:(OI)(CI)F" in grants
            assert "*S-1-5-32-544:(OI)(CI)F" in grants

    @pytest.mark.parametrize("name", ["data", "logs", "config"])
    def test_private_dirs_without_users(self, plan, name):
        step = self._by_path(plan, name)
        assert not any(c[3].startswith(("*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0"))
                       for c in step["grants"])
        assert {c[3] for c in step["removes"]} == {"*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0"}

    def test_postgres_service_account_keeps_what_it_needs(self, plan):
        ns = "*S-1-5-20:"
        root = {c[3] for c in plan[0]["grants"]}
        assert ns + "(OI)(CI)RX" in root           # read/execute bin\postgresql
        data = {c[3] for c in self._by_path(plan, "data")["grants"]}
        # traverse/list on data itself, NOT inherited into data\backups
        assert ns + "(RX)" in data
        logs = {c[3] for c in self._by_path(plan, "logs")["grants"]}
        assert ns + "(OI)(CI)M" in logs            # logging_collector (as pg_start)
        config = {c[3] for c in self._by_path(plan, "config")["grants"]}
        assert not any(g.startswith(ns) for g in config)


class TestHardenInstallDirRunner:
    def _wire(self, srv, tmp_path, monkeypatch):
        base = tmp_path / "PraxisZeit"
        base.mkdir()
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "BASE_DIR", base)
        monkeypatch.setattr(srv, "DATA_DIR", base / "data")
        monkeypatch.setattr(srv, "LOG_DIR", base / "logs")
        monkeypatch.setattr(srv, "CONFIG_DIR", base / "config")
        return base

    def test_grants_before_protect_and_dirs_created(self, srv, tmp_path, monkeypatch):
        base = self._wire(srv, tmp_path, monkeypatch)
        calls = []
        monkeypatch.setattr(srv.subprocess, "run",
                            lambda cmd, *a, **kw: calls.append(list(cmd)) or _ok())
        assert srv._harden_install_dir() is True
        for d in ("data", "logs", "config"):
            assert (base / d).is_dir()
        for target in (base, base / "data", base / "logs", base / "config"):
            mine = [c for c in calls if c[1] == str(target)]
            assert mine[-1][2:] == ["/inheritance:r"]
            assert any(c[2] == "/grant:r" for c in mine)

    def test_failed_grant_never_strips_inheritance(self, srv, tmp_path, monkeypatch):
        base = self._wire(srv, tmp_path, monkeypatch)
        calls = []

        def _run(cmd, *a, **kw):
            calls.append(list(cmd))
            if cmd[1] == str(base / "data") and cmd[2] == "/grant:r" and "S-1-5-32-544" in cmd[3]:
                return types.SimpleNamespace(returncode=5, stdout="", stderr="Zugriff verweigert")
            return _ok()

        monkeypatch.setattr(srv.subprocess, "run", _run)
        assert srv._harden_install_dir() is False
        data_calls = [c for c in calls if c[1] == str(base / "data")]
        assert ["icacls", str(base / "data"), "/inheritance:r"] not in data_calls
        # the other directories are still hardened
        assert ["icacls", str(base / "logs"), "/inheritance:r"] in calls

    def test_drive_root_is_never_touched(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "BASE_DIR", Path(Path.cwd().anchor))
        monkeypatch.setattr(srv.subprocess, "run",
                            lambda *a, **kw: pytest.fail("icacls on a drive root"))
        assert srv._harden_install_dir() is False

    def test_noop_off_windows(self, srv, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv.subprocess, "run",
                            lambda *a, **kw: pytest.fail("icacls off Windows"))
        assert srv._harden_install_dir() is True
        srv._ensure_install_dir_acl()


class TestEnsureInstallDirAclAtStart:
    def _wire(self, srv, tmp_path, monkeypatch):
        base = tmp_path / "PraxisZeit"
        for d in ("data", "logs", "config"):
            (base / d).mkdir(parents=True)
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "BASE_DIR", base)
        monkeypatch.setattr(srv, "DATA_DIR", base / "data")
        monkeypatch.setattr(srv, "LOG_DIR", base / "logs")
        monkeypatch.setattr(srv, "CONFIG_DIR", base / "config")
        hardened = []
        monkeypatch.setattr(srv, "_harden_install_dir", lambda: hardened.append(1) or True)
        return base, hardened

    def test_inherited_root_triggers_hardening(self, srv, tmp_path, monkeypatch):
        base, hardened = self._wire(srv, tmp_path, monkeypatch)
        monkeypatch.setattr(srv, "_windows_acl_is_inherited", lambda p: p == base)
        srv._ensure_install_dir_acl()
        assert hardened == [1]

    def test_hardened_install_is_left_alone(self, srv, tmp_path, monkeypatch):
        _, hardened = self._wire(srv, tmp_path, monkeypatch)
        monkeypatch.setattr(srv, "_windows_acl_is_inherited", lambda p: False)
        srv._ensure_install_dir_acl()
        assert hardened == []

    def test_cmd_start_runs_the_safety_net(self, srv, monkeypatch):
        called = []
        monkeypatch.setattr(srv, "load_config", lambda: {})
        monkeypatch.setattr(srv, "_ensure_restricted_permissions", lambda p: None)

        def _net():
            called.append(1)
            raise RuntimeError("STOP")

        monkeypatch.setattr(srv, "_ensure_install_dir_acl", _net)
        with pytest.raises(RuntimeError, match="STOP"):
            srv.cmd_start(None)
        assert called == [1]

    def test_subcommand_is_registered(self, srv, monkeypatch):
        called = []
        monkeypatch.setattr(srv, "cmd_harden_permissions", lambda args: called.append(args))
        monkeypatch.setattr(sys, "argv", ["praxiszeit-server.py", "harden-permissions"])
        srv.main()
        assert len(called) == 1


# --- installer sources ---------------------------------------------------------

def _read(rel):
    return (_REPO / rel).read_bytes()


def test_setup_bat_hardens_install_dir_and_stays_crlf():
    raw = _read("installer/windows/setup.bat")
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    assert b'praxiszeit-server.py" harden-permissions' in raw


def test_update_wizard_hardens_install_dir_and_stays_crlf():
    raw = _read("installer/windows/update-wizard.ps1")
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert b"harden-permissions" in raw


@pytest.mark.parametrize("rel", [
    "installer/linux/praxiszeit.service",
    "installer/linux/install.sh",
    "installer/linux/install-local.sh",
    "installer/setup/src/PraxisZeit.Setup.Core/Platform/LinuxPlatform.cs",
])
def test_every_service_unit_sets_umask(rel):
    text = _read(rel).decode("utf-8")
    # Section headers only (the #427 comments mention "[Service]" in prose).
    services = sum(1 for line in text.splitlines() if line.strip() == "[Service]")
    assert services >= 1
    # install.sh writes two units (service + backup) — each needs it.
    assert text.count("UMask=0077") == services, rel


def test_install_sh_restricts_data_and_logs():
    text = _read("installer/linux/install.sh").decode("utf-8")
    assert 'chmod 750 "${INSTALL_DIR}/data" "${INSTALL_DIR}/logs"' in text


# --- Release-Review 1.20.2: Unix data/logs/backups at every service start -----
# install.sh chmods data/ and logs/ to 750, but GUI setup, install-local.sh and
# macOS installs never did; dumps written before 1.20.2 kept 0644.

@pytest.mark.skipif(os.name != "posix", reason="Unix file mode")
class TestRestrictUnixDataDirsAtStart:
    def _wire(self, srv, tmp_path, monkeypatch):
        data, logs = tmp_path / "data", tmp_path / "logs"
        backups = data / "backups"
        backups.mkdir(parents=True)
        logs.mkdir()
        for d in (data, logs, backups):
            d.chmod(0o755)
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "DATA_DIR", data)
        monkeypatch.setattr(srv, "LOG_DIR", logs)
        monkeypatch.setattr(srv, "BACKUP_DIR", backups)
        return data, logs, backups

    def test_dirs_lose_world_access_and_old_dumps_become_0600(self, srv, tmp_path, monkeypatch):
        data, logs, backups = self._wire(srv, tmp_path, monkeypatch)
        old_dump = backups / "praxiszeit_20261001_030000.sql.gz"
        old_dump.write_bytes(b"x")
        old_dump.chmod(0o644)
        srv._restrict_unix_data_dirs()
        assert stat.S_IMODE(data.stat().st_mode) == 0o750
        assert stat.S_IMODE(logs.stat().st_mode) == 0o750
        assert stat.S_IMODE(backups.stat().st_mode) == 0o700
        assert stat.S_IMODE(old_dump.stat().st_mode) == 0o600

    def test_never_widens_tighter_modes(self, srv, tmp_path, monkeypatch):
        data, logs, backups = self._wire(srv, tmp_path, monkeypatch)
        data.chmod(0o700)
        srv._restrict_unix_data_dirs()
        assert stat.S_IMODE(data.stat().st_mode) == 0o700

    def test_noop_on_windows(self, srv, tmp_path, monkeypatch):
        data, logs, backups = self._wire(srv, tmp_path, monkeypatch)
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        srv._restrict_unix_data_dirs()
        assert stat.S_IMODE(data.stat().st_mode) == 0o755

    def test_called_from_cmd_start(self, srv):
        src = Path(srv.__file__).read_text(encoding="utf-8")
        body = src.split("def cmd_start(", 1)[1].split("\ndef ", 1)[0]
        assert "_restrict_unix_data_dirs()" in body
