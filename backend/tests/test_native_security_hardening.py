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
import re
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


@pytest.fixture(autouse=True)
def _fresh_pg_port(srv):
    """pg_port() is memoized per process; every test starts uncached."""
    srv.pg_port.cache_clear()
    yield
    srv.pg_port.cache_clear()


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

    def test_placeholder_admin_password_keeps_development(self, srv):
        assert srv.native_environment({"ADMIN_PASSWORD": "BITTE_AENDERN_min12zeichen"}) == "development"

    @pytest.mark.parametrize("value", [
        "BITTE_AENDERN_min12zeichen", "<initiales-admin-pw>", "<generierter-key-mindestens-64-hex-zeichen>",
        "CHANGE_ME_GENERATE_RANDOM_PASSWORD", " <x> ", "", "Sicheres-Passwort-2026", "a<b>c", "<offen",
    ])
    def test_placeholder_check_matches_backend(self, srv, value):
        from app.config import is_placeholder_secret
        assert srv._backend_is_placeholder_secret(value) == is_placeholder_secret(value)

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

    def test_no_recursive_switches(self, plan):
        # /T would walk into a bin\postgresql junction (system PostgreSQL).
        for step in plan:
            for cmd in [step["owner"]] + step["grants"] + step["removes"] + [step["protect"]]:
                assert "/T" not in cmd

    def test_every_dir_gets_administrators_as_owner(self, plan):
        """Audit 2026-11-07 S3-01: an owner always has WRITE_DAC. A local
        account that created C:\\PraxisZeit beforehand stays owner otherwise
        and can grant itself Full Control again at any time."""
        for step in plan:
            assert step["owner"] == ["icacls", str(step["path"]), "/setowner", "*S-1-5-32-544"]

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

    def test_exact_dacl_allows_only_the_intended_sids(self, srv, plan):
        """Fix round S3-01: the final step sets the WHOLE DACL (protected, no
        inheritance) - any other SID disappears - and re-checks the result."""
        expected = {
            "PraxisZeit": {"SY", "BA", "BU", "NS"},
            "data": {"SY", "BA", "NS"},
            "logs": {"SY", "BA", "NS"},
            "config": {"SY", "BA"},
        }
        for step in plan:
            cmd = step["exact"]
            script = cmd[-1]
            sddl = re.search(r"SetSecurityDescriptorSddlForm\('([^']+)','Access'\)", script).group(1)
            assert sddl.startswith("D:P(")
            assert set(re.findall(r";;;([A-Z]{2})\)", sddl)) == expected[Path(step["path"]).name]
            assert "AreAccessRulesProtected" in script and "exit 3" in script
            assert "GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])" in script
            assert cmd[0].endswith("powershell.exe") and "-NoProfile" in cmd

    def test_exact_dacl_quotes_the_path_for_powershell(self, srv):
        cmd = srv._exact_dacl_command(Path("C:/Pra'x\u2019is"), srv.WIN_SDDL_CONFIG)
        assert "$p='C:/Pra''x\u2019\u2019is';" in cmd[-1]

    def test_exact_dacl_sddl_is_identical_everywhere(self, srv):
        ps1 = _read("installer/windows/secure-install.ps1").decode("ascii")
        guard = _read("installer/setup/src/PraxisZeit.Setup.Core/Services/InstallDirGuard.cs").decode("utf-8")
        for name, value in (("Root", srv.WIN_SDDL_ROOT), ("Data", srv.WIN_SDDL_DATA),
                            ("Logs", srv.WIN_SDDL_LOGS), ("Config", srv.WIN_SDDL_CONFIG)):
            assert f"$Sddl{name} = '{value}'" in ps1
        assert f'"{srv.WIN_SDDL_ROOT}"' in guard

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
            assert mine[0][2:] == ["/setowner", "*S-1-5-32-544"]  # owner first
            assert mine[-1][2:] == ["/inheritance:r"]
            assert any(c[2] == "/grant:r" for c in mine)

    def test_failed_owner_change_still_hardens_but_reports(self, srv, tmp_path, monkeypatch):
        base = self._wire(srv, tmp_path, monkeypatch)
        calls = []

        def _run(cmd, *a, **kw):
            calls.append(list(cmd))
            if cmd[2] == "/setowner":
                return types.SimpleNamespace(returncode=5, stdout="", stderr="Zugriff verweigert")
            return _ok()

        monkeypatch.setattr(srv.subprocess, "run", _run)
        assert srv._harden_install_dir() is False
        assert ["icacls", str(base), "/inheritance:r"] in calls

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

    def _ps_calls(self, calls):
        return [c for c in calls if c[0].lower().endswith("powershell.exe")]

    def test_exact_dacl_runs_last_for_every_directory(self, srv, tmp_path, monkeypatch):
        """Fix round S3-01: a foreign explicit ACE (icacls /grant empfang:F on
        the pre-created root) is not covered by /grant:r + /remove:g of known
        SIDs. The whole DACL is replaced from an allow list after /inheritance:r."""
        base = self._wire(srv, tmp_path, monkeypatch)
        calls = []
        monkeypatch.setattr(srv.subprocess, "run",
                            lambda cmd, *a, **kw: calls.append(list(cmd)) or _ok())
        assert srv._harden_install_dir() is True
        ps = self._ps_calls(calls)
        assert len(ps) == 4
        for target, sddl in ((base, srv.WIN_SDDL_ROOT), (base / "data", srv.WIN_SDDL_DATA),
                             (base / "logs", srv.WIN_SDDL_LOGS), (base / "config", srv.WIN_SDDL_CONFIG)):
            cmd = srv._exact_dacl_command(target, sddl)
            assert cmd in calls
            assert calls.index(cmd) > calls.index(["icacls", str(target), "/inheritance:r"])

    def test_foreign_entry_left_behind_fails_the_hardening(self, srv, tmp_path, monkeypatch):
        self._wire(srv, tmp_path, monkeypatch)

        def _run(cmd, *a, **kw):
            if cmd[0].lower().endswith("powershell.exe"):  # verification: exit 3
                return types.SimpleNamespace(returncode=3, stdout="Fremde Eintraege: S-1-5-21-1-2-3-1001",
                                             stderr="")
            return _ok()

        monkeypatch.setattr(srv.subprocess, "run", _run)
        assert srv._harden_install_dir() is False

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


# LinuxPlatform.cs schrieb frueher ebenfalls eine Unit; die nie aufgerufene
# Registrierung ist entfernt (Audit 2026-11-07 S3-17).
@pytest.mark.parametrize("rel", [
    "installer/linux/praxiszeit.service",
    "installer/linux/install.sh",
    "installer/linux/install-local.sh",
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


# --- Audit 2026-11-07 S3-01: Installationsordner VOR dem ersten python.exe -----

def _code_lines(text: str, comment: str) -> str:
    """Nur ausfuehrbare Zeilen (Kommentare erklaeren den alten Weg)."""
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().upper().startswith(comment.upper()))


def _crlf_only(raw: bytes) -> bool:
    return b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def test_secure_install_ps1_is_crlf_ascii_and_sid_based():
    raw = _read("installer/windows/secure-install.ps1")
    assert _crlf_only(raw)
    text = raw.decode("ascii")  # PowerShell 5.1 liest UTF-8 ohne BOM als ANSI
    assert "/setowner" in text and "$SidAdmins" in text
    assert "'/inheritance:r'" in text
    assert "/reset" in text
    assert "payload-manifest.txt" in text
    assert "exit 2" in text  # fremde Dateien sperren mit Hinweis
    # nur SIDs, nie lokalisierte Gruppennamen
    for name in ("Administratoren", "Administrators", "Benutzer\'", "Everyone", "Jeder"):
        assert f"'{name}'" not in text
    # eine Verknuepfung bin\postgresql (System-PostgreSQL) wird nicht betreten
    assert "ReparsePoint" in text


def test_secure_install_ps1_replaces_foreign_entries_on_the_root():
    """Fix round S3-01: after the icacls grants the root DACL is rebuilt from
    an allow list and verified, before bin\\ and app\\ inherit it (/reset)."""
    text = _read("installer/windows/secure-install.ps1").decode("ascii")
    code = _code_lines(text, "#")
    exact = code.index("Set-ExactDacl $root $SddlRoot @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-32-545', 'S-1-5-20')")
    assert code.index("Invoke-Icacls @($root, '/inheritance:r')") < exact
    assert exact < code.index("'/reset'", code.index("$pgIsLink = Test-ReparsePoint $pgDir"))
    fn = code[code.index("function Set-ExactDacl"):code.index("function Test-ReparsePoint")]
    assert "SetSecurityDescriptorSddlForm($Sddl, 'Access')" in fn
    assert "AreAccessRulesProtected" in fn and "exit 1" in fn
    assert "GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])" in fn
    for name in ("data", "logs", "config"):
        assert f"'{name}' {{ Set-ExactDacl $p $Sddl{name.capitalize()} " in code


def _ps1_code() -> str:
    return _code_lines(_read("installer/windows/secure-install.ps1").decode("ascii"), "#")


def _ps1_function(code: str, name: str) -> str:
    fn = code[code.index(f"function {name}"):]
    return fn[:fn.index("\n}\n") + 3]


def _contents_block(code: str) -> str:
    start = code.index("'config' { Set-ExactDacl $p $SddlConfig")
    return code[start:code.index("if ($SkipManifest)")]


def test_secure_install_ps1_resets_the_contents_of_data_logs_config():
    """Final-Review (S3-01-Rest): data, logs und config bekamen nur auf dem Ordner
    selbst eine exakte DACL - ein vorab angelegtes data\\backups mit eigenem
    Eintrag behielt Lesezugriff auf jede Sicherung, ein leeres data\\db
    Schreibzugriff auf postgresql.conf. Die Inhalte gehen auf die geerbten
    Rechte zurueck."""
    block = _contents_block(_ps1_code())
    assert "foreach ($child in Get-ChildItem -LiteralPath $p -Force)" in block
    assert "Invoke-Icacls @($child.FullName, '/reset', '/T', '/C', '/Q')" in block
    assert "Invoke-Icacls @($child.FullName, '/reset', '/C', '/Q')" in block
    assert "Test-ReparsePoint $child.FullName" in block
    # Mandatory: ein gescheitertes Zuruecksetzen bricht ab (Exit 1), kein $false
    assert "'/reset', '/T', '/C', '/Q') $false" not in block


def test_secure_install_ps1_never_trusts_a_pg_version_file(srv):
    """Audit round 4: an initialised data\\db (PG_VERSION) used to be exempt from
    the reset. data\\db is now left alone only if it and everything below it is
    owned by, and grants access only to, SYSTEM, Administrators and the
    PostgreSQL service account; otherwise it is reset and gets back exactly the
    service entry pg_start grants."""
    code = _ps1_code()
    assert "PG_VERSION" not in code

    fn = _ps1_function(code, "Test-ServiceOnlyAcl")
    assert "$okSids = @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-20')" in fn
    assert "$okSids -notcontains $acl.GetOwner($sidType).Value) { return $false }" in fn
    assert "foreach ($rule in $acl.GetAccessRules($true, $true, $sidType))" in fn
    assert "$okSids -notcontains $rule.IdentityReference.Value) { return $false }" in fn
    assert "-band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }" in fn
    assert "if (Test-OddName $c.Name) { return $false }" in fn  # Runde 5
    # the whole tree, not only data\\db itself; any error -> not trusted
    assert "Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction Stop" in fn
    assert "$items.Push($c)" in fn
    assert fn.rstrip().endswith("return $true\n}")
    catch = fn[fn.index("} catch {"):]
    assert catch.split("}", 2)[1].strip() == "catch {\n        return $false"
    assert "Write-Output" not in fn  # its pipeline output is the verdict

    block = _contents_block(code)
    assert ("$isDb = ($entry.Name -eq 'data' -and $child.Name -eq 'db' -and $child.PSIsContainer)"
            in block)
    assert "if ($isDb -and $dbServiceOnly) { continue }" in block
    reset = block.index("Invoke-Icacls @($child.FullName, '/reset', '/T', '/C', '/Q')")
    grant_line = ("Invoke-Icacls @($child.FullName, '/grant', "
                  "\"${SidNetworkService}:(OI)(CI)F\", '/T', '/C', '/Q')")
    grant = block.index(grant_line)
    assert reset < grant
    gate = block.rindex("\n", 0, grant)
    assert block[block.rindex("\n", 0, gate) + 1:gate].strip() == "if ($isDb) {"
    # same ACE as praxiszeit-server.py grants the PostgreSQL service account
    server = srv._build_icacls_grant_args(Path("C:/x/data/db"), "F")
    assert server[2] == "/grant" and server[3] == "*S-1-5-20:(OI)(CI)F" and "/T" in server
    assert "$SidNetworkService = '*S-1-5-20'" in code


def test_secure_install_ps1_decides_trust_before_any_owner_change():
    """Audit round 5: the owner check of data\\db ran after ``icacls data
    /setowner Administrators /T`` - every owner it saw was already
    Administrators, so it could never fail. Trust is now decided before the
    first /setowner: the service-only verdict for data\\db, and the origin of
    files in data\\db and config (owner SYSTEM, Administrators, the database
    service or a local administrator). Files of unproven origin stop the
    install (exit 2) unless a PraxisZeit service registered for this folder
    proves an earlier elevated install."""
    code = _ps1_code()
    raw = _read("installer/windows/secure-install.ps1").decode("ascii")
    step0 = raw[raw.index("# --- 0. Vorab"):raw.index("# --- 1. Wurzel ---")]
    assert "$untrusted = @(Get-UntrustedFiles $dbDir @()) + @(Get-UntrustedFiles $configDir @('praxiszeit.conf.example'))" in step0
    assert "$evidence = Test-InstallEvidence $root" in step0
    assert "if ($untrusted.Count -gt 0 -and -not $evidence) {" in step0
    assert step0.index("if ($untrusted.Count -gt 0 -and -not $evidence) {") < step0.index("exit 2")
    assert "$dbServiceOnly = (Test-Path -LiteralPath $dbDir) -and (Test-ServiceOnlyAcl $dbDir)" in step0
    # nothing before step 0 changes owners or rights
    main = code[code.index("try {\n    $root = (Resolve-Path"):]
    assert main.index("Get-UntrustedFiles $dbDir") < main.index("'/setowner'")
    assert main.index("Test-ServiceOnlyAcl $dbDir") < main.index("'/setowner'")
    assert "Test-ServiceOnlyAcl $child.FullName" not in code  # no late (post-setowner) check

    fn = _ps1_function(code, "Get-UntrustedFiles")
    assert "$trusted = Get-TrustedOwnerSids" in fn
    assert "$item.GetAccessControl('Owner').GetOwner($sidType).Value" in fn
    assert "if ($trusted -notcontains $owner)" in fn
    assert "(Verknuepfung)" in fn and "(nicht lesbar)" in fn and "Test-OddName $c.Name" in fn
    sids = _ps1_function(code, "Get-TrustedOwnerSids")
    assert "@('S-1-5-18', 'S-1-5-32-544', 'S-1-5-20')" in sids
    assert "Get-LocalGroupMember -SID 'S-1-5-32-544'" in sids
    assert "WindowsIdentity]::GetCurrent().User.Value" in sids
    ev = _ps1_function(code, "Test-InstallEvidence")
    assert "@('PraxisZeit-PostgreSQL', 'PraxisZeit')" in ev
    assert "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\$svc" in ev and "ImagePath" in ev
    assert "$img.Replace('/', '\\').IndexOf($Root + '\\', [System.StringComparison]::OrdinalIgnoreCase)" in ev


def test_secure_install_ps1_refuses_a_preexisting_bin_postgresql_without_install():
    """Release review 1.23.0 (HIGH): setup.bat skips the PostgreSQL install when
    bin\\postgresql\\bin\\pg_ctl.exe already exists, and the manifest check
    skips bin\\postgresql. A folder or junction someone created there before
    the first install would become the database program run by the service.
    setup.bat creates bin\\postgresql only AFTER secure-install.ps1, so without
    a PraxisZeit service for this folder an existing one stops the install."""
    raw = _read("installer/windows/secure-install.ps1").decode("ascii")
    step0 = raw[raw.index("# --- 0. Vorab"):raw.index("# --- 1. Wurzel ---")]
    assert "$pgDirPre = Join-Path $root 'bin\\postgresql'" in step0
    # found by listing bin\\ - Test-Path follows a junction and reports a
    # dangling one as missing
    guard = "if (($null -ne (Get-EntryNoFollow $pgDirPre)) -and -not $evidence) {"
    assert guard in step0
    assert step0.index("$evidence = Test-InstallEvidence $root") < step0.index(guard)
    assert "exit 2" in step0[step0.index(guard):step0.index(guard) + 900]
    # setup.bat still calls secure-install.ps1 before it creates bin\\postgresql
    setup = _read("installer/windows/setup.bat").decode("ascii", "replace")
    assert setup.index("secure-install.ps1") < setup.index('mklink /J "%PG_INSTALL_DIR%"')
    assert setup.index("secure-install.ps1") < setup.index('--prefix "%PG_INSTALL_DIR%"')


def test_secure_install_ps1_locks_each_subtree_top_down_before_recursing():
    """Audit rounds 4+5: ``icacls /setowner|/reset /T`` follows junctions and
    symbolic links. A one-shot check before the recursive calls left a window:
    an account with an explicit ACE on a subfolder could create a link after
    the check. Every subtree is now locked top-down first - per directory owner
    + reset WITHOUT /T, then list it - refusing links, multi-link files and
    names ending in a space or dot (exit 2); only then run the /T calls."""
    code = _ps1_code()
    assert "-Recurse" not in code  # PS 5.1 -Recurse follows directory links itself
    assert "Assert-NoReparsePointBelow" not in code
    fn = _ps1_function(code, "Lock-TreeTopDown")
    lock = fn.index("Invoke-Icacls @($d, '/setowner', $SidAdmins, '/C', '/Q')")
    reset = fn.index("Invoke-Icacls @($d, '/reset', '/C', '/Q')")
    listing = fn.index("Get-ChildItem -LiteralPath $d -Force -ErrorAction Stop")
    assert lock < reset < listing  # lock before looking
    assert "'/T'" not in fn
    assert fn.index("if (-not (Test-DirLocked $d)) {") < lock
    assert "if (Test-OddName $item.Name) { $odd.Add($item.FullName); continue }" in fn
    check = fn.index("-band [System.IO.FileAttributes]::ReparsePoint")
    assert check < fn.index("$links.Add($item.FullName)") < fn.index("$stack.Push($item.FullName)")
    assert "elseif ([PzFileLinks]::Count($item.FullName) -ne 1) {" in fn
    assert "exit 1" in fn and "Write-TreeFindings $Dir $links $hard $odd" in fn
    findings = _ps1_function(code, "Write-TreeFindings")
    assert findings.count("exit 2") == 1
    locked = _ps1_function(code, "Test-DirLocked")
    assert "-ne 'S-1-5-32-544') { return $false }" in locked
    assert "AreAccessRulesProtected) { return $false }" in locked
    assert "if (-not $rule.IsInherited) { return $false }" in locked
    assert "Test-OddName" in code and "return ($Name -match '[ .]$')" in _ps1_function(code, "Test-OddName")
    # hard-link count: FILE_READ_ATTRIBUTES, no reparse following, \\?\ paths
    raw = _read("installer/windows/secure-install.ps1").decode("ascii")
    assert "GetFileInformationByHandle" in raw and "CreateFileW(p, 0x80, 7, IntPtr.Zero, 3, 0x02200000" in raw
    assert '@"\\\\?\\"' in raw
    add = raw.index("Add-Type -Language CSharp -TypeDefinition $PzFileLinksCode -ErrorAction Stop")
    assert "exit 1" in raw[add:add + 300]

    lines = code.splitlines()
    recursive = [i for i, line in enumerate(lines)
                 if "Invoke-Icacls @(" in line and "'/T'" in line]
    assert len(recursive) >= 7
    for i in recursive:
        target = lines[i].split("Invoke-Icacls @(", 1)[1].split(",", 1)[0].strip()
        j = i - 1
        while not lines[j].strip().startswith("Lock-TreeTopDown "):
            # the lock must sit in the same branch, not in a sibling one
            assert not (lines[j].strip().startswith("}") and _indent(lines[j]) < _indent(lines[i])), \
                (lines[i], lines[j])
            j -= 1
        assert lines[j].strip() == f"Lock-TreeTopDown {target}", lines[i]
    # single files get the same name/hard-link check before icacls
    singles = [i for i, line in enumerate(lines)
               if "Invoke-Icacls @(" in line and "'/setowner'" in line and "'/T'" not in line
               and "$d," not in line and "$root," not in line]
    for i in singles:
        target = lines[i].split("Invoke-Icacls @(", 1)[1].split(",", 1)[0].strip()
        if target == "$p" and "'bin'" in lines[i - 1] + lines[i - 2]:
            continue  # bin itself: its entries follow one by one
        prev = [lines[k].strip() for k in range(i - 3, i)]
        assert f"Assert-SingleFile {target}" in prev or target == "$p", lines[i]


def test_secure_install_ps1_refuses_links_at_the_first_level():
    """A junction data -> elsewhere (or data\\backups -> elsewhere) placed the
    database or the backups outside the secured folder; it used to be skipped."""
    code = _ps1_code()
    step2 = code[code.index("$pgIsLink = Test-ReparsePoint $pgDir"):code.index("if ($SkipManifest)")]
    root_check = step2.index("if (Test-ReparsePoint $p) {")
    assert "exit 2" in step2[root_check:root_check + 400]
    child_check = step2.index("if (Test-ReparsePoint $child.FullName) {")
    assert "exit 2" in step2[child_check:child_check + 400]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def test_setup_bat_secures_install_dir_before_any_python():
    raw = _read("installer/windows/setup.bat")
    assert _crlf_only(raw)
    text = raw.decode("ascii")
    secure = text.index('secure-install.ps1" -InstallDir "%DIR%."')
    assert secure < text.index('"%PYTHON%"')
    after = text[secure:secure + 200]
    assert 'set "SEC_RC=%errorlevel%"' in after
    assert 'if "%SEC_RC%"=="2" goto :fremde_dateien' in after
    # any other non-zero code (also negative ones) stops the setup
    assert 'if not "%SEC_RC%"=="0" goto :rechte_fehler' in after
    for label in (":fremde_dateien", ":rechte_fehler"):
        block = text[text.index("\r\n" + label + "\r\n"):]
        block = block[:block.index("exit /b 1")]
        assert "net start" not in block


def test_setup_bat_never_installs_from_the_internet():
    """S3-05: kein get-pip.py, kein ``pip install`` als Administrator."""
    text = _code_lines(_read("installer/windows/setup.bat").decode("ascii"), "REM")
    assert "get-pip" not in text
    assert "pip install" not in text
    assert 'import alembic, uvicorn, fastapi, sqlalchemy, psycopg2' in text


def test_update_wizard_secures_and_checks_before_python():
    raw = _read("installer/windows/update-wizard.ps1")
    assert _crlf_only(raw)
    text = raw.decode("utf-8")
    assert "get-pip" not in text.replace("get-pip.py --force-reinstall + ", "")
    assert "pip install --" not in text and "-m pip install" not in text
    # bestehende Installation: Rechte/Eigentuemer vor dem Backup (python.exe)
    acl = text.index("function Step-ACLFix")
    assert "Invoke-SecureInstall $InstallDir -SkipManifest" in text[acl:text.index("function Step-Backup")]
    # das Backup laeuft isoliert (keine .pth/sitecustomize aus der Vorversion)
    assert '"-I -S -X utf8 $quotedServer backup"' in text
    # nach dem Kopieren: Abgleich mit dem Paket, Fehler -> Dienst bleibt aus
    pip = text[text.index("function Step-PipInstall"):text.index("function Step-StopService")]
    assert "Invoke-SecureInstall $InstallDir\r\n" in pip
    assert pip.index("Invoke-SecureInstall") < pip.index("$python")
    upd = text[text.index("function Invoke-Update"):]
    ok5 = upd.index("if (-not $ok5)")
    assert "Step-StartService" not in upd[ok5:upd.index("}", ok5)]
    # Programmteile gespiegelt, damit keine Dateien der Vorversion liegen bleiben
    assert "foreach ($sub in @('bin\\python', 'app'))" in text
    assert "'/MIR'" in text


def test_update_md_describes_the_current_windows_wizard():
    """Fix round (doc sync): UPDATE.md must not promise a pip bootstrap or a
    merge-only copy any more - the wizard mirrors app/bin\\python, downloads
    nothing and keeps the service off after a manifest mismatch (exit 2)."""
    text = _read("docs/UPDATE.md").decode("utf-8")
    win = text[text.index("### Windows"):text.index("### Update-Hinweis in der App")]
    assert "pip-Bootstrap" not in win
    assert "/MIR" in win and "payload-manifest.txt" in win and "Exit 2" in win
    assert "nichts aus dem Internet" in win
    rollback = text[text.index("Windows (Administrator-Eingabeaufforderung)"):]
    assert "bis 1.22.x mischen nur darüber" in rollback and "/MIR" in rollback


def test_secure_install_ps1_ships_with_the_windows_package():
    text = _read("tools/build-release.sh").decode("utf-8")
    assert 'installer/windows/secure-install.ps1" "${WIN_DIR}/"' in text
    assert "payload-manifest.txt" in text


# --- Audit 2026-11-07 S3-11 / S3-12 --------------------------------------------

def test_install_sh_never_puts_the_superuser_password_into_argv():
    text = _code_lines(_read("installer/linux/install.sh").decode("utf-8"), "#")
    for line in text.splitlines():
        if "sudo" in line:
            assert "PGPASSWORD=" not in line, line
    assert 'PGPASSFILE="${PGPASS_FILE}"' in text
    assert "( umask 077; printf" in text
    assert text.count('rm -f "${PGPASS_FILE}"') >= 2  # Erfolg und Fehler


def test_macos_service_has_its_own_group_and_umask():
    text = _code_lines(_read("installer/macos/install.sh").decode("utf-8"), "#")
    assert ":staff" not in text
    assert "PrimaryGroupID 20" not in text
    assert 'chown -R _praxiszeit:_praxiszeit "${INSTALL_DIR}"' in text
    assert 'dscl . -create /Users/_praxiszeit PrimaryGroupID "$PZ_GID"' in text
    # beide launchd-Plists: eigene Gruppe + umask 077 (dezimal 63)
    assert text.count("<key>Umask</key>\n    <integer>63</integer>") == 2
    assert text.count("<key>GroupName</key>\n    <string>_praxiszeit</string>") == 2
    # kein `echo | grep -q` unter pipefail (SIGPIPE)
    assert 'grep -qx "$g" <<<"$USED_GIDS"' in text


# --- Audit 2026-11-07 S3-05: Lieferkette des Release-Builds ---------------------

def _build_sh() -> str:
    return _read("tools/build-release.sh").decode("utf-8")


def test_every_download_in_the_release_build_is_pinned():
    text = _build_sh()
    body = text[text.index("download_pinned() {"):]
    body = body[body.index("\n}\n") + 3:]  # Rest nach der Funktionsdefinition
    raw_downloads = [line for line in body.splitlines()
                     if re.match(r"\s*download\s", line) or "curl " in line and " -o " in line]
    # einziger roher curl: der EDB-Windows-Installer, direkt danach SHA-geprueft
    assert all("PG_WINDOWS_URL" in line for line in raw_downloads), raw_downloads
    for var in ("PYTHON_LINUX_SHA256", "PYTHON_WINDOWS_SHA256", "PYTHON_MACOS_X64_SHA256",
                "PYTHON_MACOS_ARM64_SHA256", "PG_LINUX_SHA256", "PG_MACOS_X64_SHA256",
                "PG_MACOS_ARM64_SHA256", "VC_REDIST_SHA256", "NSSM_SHA256"):
        assert re.search(rf'^{var}="[0-9a-f]{{64}}"', text, re.M), var
        assert f'"${var}"' in text, f"{var} wird nicht geprueft"
    assert "aka.ms" not in text.split("VC_REDIST_URL=", 1)[1].split("\n", 1)[0]
    assert "get-pip" not in text.replace("KEIN get-pip.py", "").replace("get-pip.py war", "")


def test_release_build_installs_only_hashed_wheels_from_the_lock():
    text = _build_sh()
    lines = text.splitlines()
    installs = [i for i, line in enumerate(lines) if "-m pip install" in line]
    assert len(installs) == 4, installs  # Linux + Windows, je Build-Werkzeug + Abhaengigkeiten
    for i in installs:
        block = "\n".join(lines[i:i + 5])
        block = block[:block.find("2>&1")]
        assert "--require-hashes" in block and "--only-binary :all:" in block, block
        assert "requirements.txt" not in block, block
        if "requirements-build.lock" not in block:
            # odfpy (nur Quellarchiv) ohne Build-Isolation mit dem gehashten setuptools
            assert "requirements.lock" in block and "--no-build-isolation" in block, block
            assert "--no-binary odfpy" in block, block
    assert 'cp "${REPO_DIR}/backend/requirements.lock"' in text
    assert 'cp "${REPO_DIR}/backend/requirements-build.lock"' in text


def test_release_build_pins_the_rockylinux_image_by_digest():
    text = _build_sh()
    assert re.search(r'^ROCKYLINUX_IMAGE="rockylinux:9@sha256:[0-9a-f]{64}"', text, re.M)
    assert "docker run --rm rockylinux" not in text
    assert 'docker run --rm "${ROCKYLINUX_IMAGE}"' in text


def test_macos_installer_installs_only_hashed_wheels():
    text = _code_lines(_read("installer/macos/install.sh").decode("utf-8"), "#")
    assert "get-pip" not in text
    lines = text.splitlines()
    installs = [i for i, line in enumerate(lines) if "-m pip install" in line]
    assert len(installs) == 2, installs
    blocks = ["\n".join(lines[i:i + 3]) for i in installs]
    assert all("--require-hashes" in b and "--only-binary :all:" in b for b in blocks), blocks
    assert "requirements-build.lock" in blocks[0]
    assert "requirements.lock" in blocks[1] and "--no-build-isolation" in blocks[1]
    assert "requirements.txt" not in "\n".join(blocks)


def test_backend_dockerfile_pins_the_base_image_by_digest():
    text = _read("backend/Dockerfile").decode("utf-8")
    froms = [line for line in text.splitlines() if line.startswith("FROM ")]
    assert froms and all(re.match(r"FROM python:[0-9.]+-slim-bookworm@sha256:[0-9a-f]{64}( AS \w+)?$", f)
                         for f in froms), froms



# --- Audit 2026-11-07 S3-13: der Webprozess bekommt den Superuser nicht --------

class TestBackupRole:
    def _wire(self, srv, tmp_path, monkeypatch, creds="SUPERUSER_PASSWORD=su\nAPP_PASSWORD=app\n"):
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / ".db-credentials").write_text(creds)
        monkeypatch.setattr(srv, "CONFIG_DIR", cfg)
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path / "data")
        return cfg

    def test_creates_read_only_role_and_keeps_existing_credentials(self, srv, tmp_path, monkeypatch):
        cfg = self._wire(srv, tmp_path, monkeypatch)
        calls = []
        monkeypatch.setattr(srv.subprocess, "run",
                            lambda cmd, *a, **kw: calls.append((list(cmd), kw)) or _ok())
        url = srv.ensure_backup_role({}, "su")
        creds = srv._read_credentials_file()
        assert creds["SUPERUSER_PASSWORD"] == "su" and creds["APP_PASSWORD"] == "app"
        assert len(creds["BACKUP_PASSWORD"]) == 64
        assert srv.pg_load_credentials() == ("su", "app")
        scheme = "postgresql" + "://"
        assert url.startswith(scheme + "praxiszeit_backup:" + creds["BACKUP_PASSWORD"] + "@")
        (cmd, kw), = calls
        sql = kw["input"]
        assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "-"  # Passwort ueber stdin
        assert all(creds["BACKUP_PASSWORD"] not in a for a in cmd)
        assert "NOSUPERUSER" in sql and "BYPASSRLS" in sql and "NOCREATEROLE" in sql
        assert "GRANT pg_read_all_data TO praxiszeit_backup" in sql
        assert "pg_write" not in sql and "SUPERUSER " not in sql.replace("NOSUPERUSER", "")
        assert kw["env"]["PGPASSWORD"] == "su"
        if os.name != "nt":
            assert stat.S_IMODE((cfg / ".db-credentials").stat().st_mode) == 0o600

    def test_password_is_stable_across_starts(self, srv, tmp_path, monkeypatch):
        self._wire(srv, tmp_path, monkeypatch)
        monkeypatch.setattr(srv.subprocess, "run", lambda *a, **kw: _ok())
        first = srv.ensure_backup_role({}, "su")
        assert srv.ensure_backup_role({}, "su") == first

    def test_interrupted_write_keeps_the_old_credentials(self, srv, tmp_path, monkeypatch):
        """Fix round: SUPERUSER_PASSWORD/APP_PASSWORD must survive a crash or a
        full disk while BACKUP_PASSWORD is added (temp file + os.replace)."""
        original = "SUPERUSER_PASSWORD=su\nAPP_PASSWORD=app\n# Notiz ohne Gleichheitszeichen\n"
        cfg = self._wire(srv, tmp_path, monkeypatch, creds=original)

        def _boom(src, dst):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(srv.os, "replace", _boom)
        with pytest.raises(OSError):
            srv._backup_role_password()
        assert (cfg / ".db-credentials").read_text() == original
        assert sorted(p.name for p in cfg.iterdir()) == [".db-credentials"]

    def test_added_password_keeps_every_existing_line(self, srv, tmp_path, monkeypatch):
        original = "SUPERUSER_PASSWORD=su\nAPP_PASSWORD=app\n# Notiz ohne Gleichheitszeichen"
        cfg = self._wire(srv, tmp_path, monkeypatch, creds=original)
        replaced = []
        real_replace = srv.os.replace
        monkeypatch.setattr(srv.os, "replace",
                            lambda a, b: replaced.append((Path(a).name, Path(b).name)) or real_replace(a, b))
        password = srv._backup_role_password()
        assert replaced == [(".db-credentials.pz-tmp", ".db-credentials")]
        text = (cfg / ".db-credentials").read_text()
        assert text == original + "\nBACKUP_PASSWORD=" + password + "\n"
        if os.name != "nt":
            assert stat.S_IMODE((cfg / ".db-credentials").stat().st_mode) == 0o600

    def test_failure_never_falls_back_to_superuser(self, srv, tmp_path, monkeypatch, caplog):
        self._wire(srv, tmp_path, monkeypatch)

        def _run(cmd, *a, **kw):
            raise srv.subprocess.CalledProcessError(1, cmd, stderr="ERROR: boom")

        monkeypatch.setattr(srv.subprocess, "run", _run)
        assert srv.ensure_backup_role({}, "su") is None
        assert "Backup-Rolle" in caplog.text

    def test_uvicorn_env_has_no_superuser_url(self, srv, tmp_path, monkeypatch):
        captured = {}

        def _popen(cmd, *a, **kw):
            captured["env"] = kw.get("env") or {}
            raise RuntimeError("stop here")

        scheme = "postgresql" + "://"
        monkeypatch.setenv("DATABASE_URL_MIGRATIONS", scheme + "su" + ":pw@/praxiszeit")
        monkeypatch.setenv("DATABASE_URL_BACKUP", scheme + "praxiszeit_backup" + ":pw@/praxiszeit")
        monkeypatch.setattr(srv.subprocess, "Popen", _popen)
        monkeypatch.setattr(srv, "port_is_occupied", lambda *a, **k: False)
        with pytest.raises(RuntimeError, match="stop here"):
            srv.uvicorn_start({})
        assert "DATABASE_URL_MIGRATIONS" not in captured["env"]
        assert captured["env"]["DATABASE_URL_BACKUP"].startswith(scheme + "praxiszeit_backup")
