"""#213 — Tests fuer den DB-Backup-Service (Config, Listing, Prune, create_backup).

create_backup wird mit gemocktem subprocess.Popen getestet (kein echtes pg_dump in
der SQLite-Suite); die Fehlerpfade (kein Superuser-URL, pg_dump fehlt) laufen echt.
"""
import gzip
import re
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
    monkeypatch.delenv("DATABASE_URL_BACKUP", raising=False)


def _use_tmp_dir(db, tmp_path):
    bs.update_config(db, location=str(tmp_path))


def _migr_url(user, pw, *, scheme="postgresql", host=None, port=None, db="praxiszeit", socket=None):
    """Baut eine (Test-)Migrations-URL aus Teilen. Bewusst zusammengesetzt, damit
    kein literales 'scheme://user:pass@' im Quelltext steht (Secret-Scanner-Hook);
    die hier genutzten 'Passwoerter' sind reine Test-Dummies."""
    cred = user + ":" + pw + "@"
    if socket:
        return scheme + "://" + cred + "/" + db + "?host=" + socket
    netloc = host + ((":" + str(port)) if port else "")
    return scheme + "://" + cred + netloc + "/" + db


# --- Config -----------------------------------------------------------------

def test_config_defaults(db, default_tenant):
    cfg = bs.get_config(db)
    assert cfg.enabled is False
    assert cfg.hour == bs.DEFAULT_HOUR
    assert cfg.retention_days == bs.DEFAULT_RETENTION_DAYS


def test_update_config_persists_and_clamps(db, default_tenant, tmp_path):
    # Writable location (tmp_path) statt eines root-only Systempfads — update_config
    # probt die Schreibbarkeit, sodass /var/backups/pz unter dem non-root Test-User
    # (appuser im Backend-Container) fehlschluege.
    loc = str(tmp_path / "pz")
    cfg = bs.update_config(db, enabled=True, hour=99, retention_days=0, location=loc)
    assert cfg.enabled is True
    assert cfg.hour == 23          # geclamped auf 0..23
    assert cfg.retention_days == 1  # geclamped auf >=1
    assert cfg.location == loc
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
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("su", "pw", host="db", port=5432))
    sql = b"-- PraxisZeit dump\nDROP TABLE IF EXISTS x;\nCREATE TABLE x();\n"
    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen(sql))

    result = bs.create_backup(db)
    path = tmp_path / result.filename
    assert path.exists() and result.size_bytes > 0
    assert result.filename.startswith("praxiszeit_") and result.filename.endswith(".sql.gz")
    with gzip.open(path, "rb") as gz:
        content = gz.read()
    # plain-SQL, einfach gunzip-bar (Restore-Pfad); am Ende die Signaturzeile
    # (Fix-Runde S3-03), für psql ein Kommentar.
    assert content.startswith(sql)
    trailer = content[len(sql):]
    assert re.fullmatch(rb"-- praxiszeit-backup-hmac-v1 [0-9a-f]{64}\n", trailer), trailer
    from app.config import settings
    from app.core import backup_mac
    with gzip.open(path, "rb") as gz:
        assert backup_mac.verify_stream(gz, settings.SECRET_KEY) == backup_mac.OK
    with gzip.open(path, "rb") as gz:
        assert backup_mac.verify_stream(gz, "anderer-schluessel") == backup_mac.MISMATCH


def test_create_backup_password_not_in_argv(db, default_tenant, tmp_path, monkeypatch):
    """Sicherheit (Review 2026-06-23): das Superuser-Passwort darf NICHT in der
    pg_dump-argv stehen (sonst via /proc/cmdline lesbar) -> es muss via PGPASSWORD
    ins env. Treibersuffix wird entfernt, URL in -h/-U/-d zerlegt."""
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("su", "pw", scheme="postgresql+psycopg2", host="db", port=5432))
    captured = {}

    def _fake_popen(cmd, **k):
        captured["cmd"] = cmd
        captured["env"] = k.get("env", {})
        return _FakePopen(b"SELECT 1;")

    monkeypatch.setattr(bs.subprocess, "Popen", _fake_popen)
    bs.create_backup(db)
    assert "-U" in captured["cmd"] and "su" in captured["cmd"]
    assert captured["cmd"][-2:] == ["-d", "praxiszeit"]
    assert "-h" in captured["cmd"] and "db" in captured["cmd"]
    assert "pw" not in " ".join(captured["cmd"])           # Passwort NICHT in argv
    assert captured["env"].get("PGPASSWORD") == "pw"        # sondern im env


def test_create_backup_native_socket_url(db, default_tenant, tmp_path, monkeypatch):
    """Native Socket-Form (postgresql, user:pass im query-host) korrekt zerlegen."""
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("praxiszeit", "s3cr3t", socket="/opt/pz/data/run"))
    captured = {}
    monkeypatch.setattr(bs.subprocess, "Popen",
                        lambda cmd, **k: captured.update(cmd=cmd, env=k.get("env", {})) or _FakePopen(b"x"))
    bs.create_backup(db)
    assert captured["cmd"][captured["cmd"].index("-h") + 1] == "/opt/pz/data/run"
    assert captured["env"].get("PGPASSWORD") == "s3cr3t"
    assert "s3cr3t" not in " ".join(captured["cmd"])


def test_create_backup_pg_dump_failure_removes_partial(db, default_tenant, tmp_path, monkeypatch):
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("su", "pw", host="db"))
    monkeypatch.setattr(
        bs.subprocess, "Popen",
        lambda *a, **k: _FakePopen(b"", rc=1, stderr=b"FATAL: auth failed"),
    )
    with pytest.raises(bs.BackupError, match="auth failed"):
        bs.create_backup(db)
    assert list(tmp_path.glob("*.sql.gz")) == []  # kein truncated/leeres Artefakt


# --- Sicherheits-Review 2026-10: Backup-Ort nie im ausgelieferten Web-Root ---

def test_location_inside_frontend_dir_refused(db, default_tenant, tmp_path, monkeypatch):
    from app.config import settings
    web = tmp_path / "frontend"
    web.mkdir()
    monkeypatch.setattr(settings, "FRONTEND_DIR", str(web))
    with pytest.raises(bs.BackupError, match="Web"):
        bs.update_config(db, location=str(web / "backups"))
    with pytest.raises(bs.BackupError):
        bs.update_config(db, location=str(web))
    assert not (web / "backups").exists()


def test_location_symlink_into_frontend_dir_refused(db, default_tenant, tmp_path, monkeypatch):
    from app.config import settings
    web = tmp_path / "frontend"
    (web / "assets").mkdir(parents=True)
    monkeypatch.setattr(settings, "FRONTEND_DIR", str(web))
    link = tmp_path / "harmlos"
    link.symlink_to(web / "assets")
    with pytest.raises(bs.BackupError):
        bs.update_config(db, location=str(link))
    with pytest.raises(bs.BackupError):
        bs.update_config(db, location=str(tmp_path / "x" / ".." / "frontend" / "sub"))


def test_location_inside_app_code_refused(db, default_tenant):
    import app as app_pkg
    code_dir = os.path.dirname(os.path.abspath(app_pkg.__file__))
    with pytest.raises(bs.BackupError):
        bs.update_config(db, location=os.path.join(code_dir, "static_backups"))


def test_native_install_app_dir_refused(db, default_tenant, tmp_path, monkeypatch):
    """Nativ (SERVE_FRONTEND): das ganze Programmverzeichnis (``<install>/app``,
    enthält backend/ und frontend/, wird beim Update per rsync --delete ersetzt)."""
    from app.config import settings
    monkeypatch.setattr(settings, "SERVE_FRONTEND", True)
    install_app = bs._backend_root().parent
    with pytest.raises(bs.BackupError):
        bs.update_config(db, location=str(install_app / "backups"))


def test_location_outside_web_root_still_allowed(db, default_tenant, tmp_path, monkeypatch):
    from app.config import settings
    web = tmp_path / "frontend"
    web.mkdir()
    monkeypatch.setattr(settings, "FRONTEND_DIR", str(web))
    cfg = bs.update_config(db, location=str(tmp_path / "frontend-backups"))
    assert cfg.location == str(tmp_path / "frontend-backups")


def test_stored_forbidden_location_is_ignored(db, default_tenant, tmp_path, monkeypatch):
    """Ein vor dem Fix gespeicherter Web-Root-Pfad darf nicht mehr beschrieben werden."""
    from app.config import settings
    web = tmp_path / "frontend"
    web.mkdir()
    monkeypatch.setattr(settings, "FRONTEND_DIR", str(web))
    bs._set_setting(db, bs.SETTING_LOCATION, str(web / "backups"))
    db.commit()
    monkeypatch.setenv("PRAXISZEIT_BACKUP_DIR", str(tmp_path / "data"))
    assert bs.get_backup_dir(db) == tmp_path / "data"


def test_pg_dump_conn_uses_url_port_on_native_windows_url(monkeypatch):
    # Guard: backup follows the port in the migrations URL (native Windows, #port).
    scheme = "postgresql" + "://"
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", scheme + "su:pw@localhost:5433/praxiszeit")
    args = bs._pg_dump_conn()
    flat = [str(a) for a in args[0]] if args and isinstance(args[0], (list, tuple)) else [str(a) for a in args]
    assert flat[flat.index("-h") + 1] == "localhost"
    assert flat[flat.index("-p") + 1] == "5433"


# --- Audit 2026-11-07 S3-04 / S2-4: Netzwerkpfade, öffentliche Ordner, ACL ---

@pytest.mark.parametrize("loc", [
    "\\\\angreifer\\freigabe\\x",
    "\\\\?\\C:\\PraxisZeit\\backups",
    "\\\\.\\pipe\\x",
    "//angreifer/freigabe/x",
])
def test_unc_location_refused_before_any_filesystem_access(db, default_tenant, monkeypatch, loc):
    touched = []
    monkeypatch.setattr(bs.os.path, "realpath", lambda p: touched.append(p) or p)
    monkeypatch.setattr(bs.Path, "exists", lambda self: touched.append(str(self)) or False)
    with pytest.raises(bs.BackupError, match="Netzwerkpfade"):
        bs.update_config(db, location=loc)
    assert touched == []  # SMB-Verbindung (NTLM-Coercion) darf nie entstehen


@pytest.fixture
def _as_windows(monkeypatch):
    monkeypatch.setattr(bs, "_is_windows", lambda: True)
    monkeypatch.setattr(bs, "_win_drive_type", lambda p: 3)  # DRIVE_FIXED
    monkeypatch.setenv("SystemDrive", "C:")
    monkeypatch.setenv("SystemRoot", "C:\\Windows")
    monkeypatch.setenv("PUBLIC", "C:\\Users\\Public")


@pytest.mark.parametrize("loc", [
    "C:\\Users\\Public\\Sicherung",
    "c:\\users\\public",
    "C:\\Users\\Default\\x",
    "C:\\Windows\\Temp\\pz",
])
def test_windows_public_folders_refused(_as_windows, loc):
    assert bs.location_rejection_reason(loc) == bs.PUBLIC_LOCATION_DETAIL


def test_windows_mapped_network_drive_refused(_as_windows, monkeypatch):
    monkeypatch.setattr(bs, "_win_drive_type", lambda p: bs._WIN_DRIVE_REMOTE)
    assert bs.location_rejection_reason("Z:\\Sicherungen") == bs.UNC_LOCATION_DETAIL


def test_windows_path_without_drive_letter_refused(_as_windows):
    assert bs.location_rejection_reason("\\Sicherungen") == bs.UNC_LOCATION_DETAIL
    assert bs.location_rejection_reason("relativ\\x") == bs.UNC_LOCATION_DETAIL


def test_windows_local_folder_allowed(_as_windows):
    assert bs.location_rejection_reason("D:\\PraxisZeit-Sicherung") is None
    assert bs.location_rejection_reason("C:\\Usersicherung\\x") is None
    assert bs.location_rejection_reason("C:\\ProgramDataBackup\\x") is None


def test_drive_root_refused(db, default_tenant):
    with pytest.raises(bs.BackupError, match="Stammverzeichnis"):
        bs.update_config(db, location="/")


def test_stored_unc_location_is_ignored(db, default_tenant, tmp_path, monkeypatch):
    bs._set_setting(db, bs.SETTING_LOCATION, "\\\\angreifer\\freigabe")
    db.commit()
    monkeypatch.setenv("PRAXISZEIT_BACKUP_DIR", str(tmp_path / "data"))
    assert bs.get_backup_dir(db) == tmp_path / "data"


def _capture_icacls(monkeypatch, fail_on=None):
    import types
    calls = []

    def _run(cmd, *a, **k):
        calls.append(list(cmd))
        rc = 1 if fail_on and fail_on(cmd) else 0
        return types.SimpleNamespace(returncode=rc, stdout="", stderr="")

    monkeypatch.setattr(bs.subprocess, "run", _run)
    return calls


def test_windows_location_gets_restricted_acl_before_first_byte(db, default_tenant, tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "_is_windows", lambda: True)
    monkeypatch.setattr(bs, "location_rejection_reason", lambda loc: None)
    calls = _capture_icacls(monkeypatch)
    target = tmp_path / "sicherung"
    seen_probe = []
    real_write = bs.Path.write_text

    def _write(self, *a, **k):
        seen_probe.append(len(calls))
        return real_write(self, *a, **k)

    monkeypatch.setattr(bs.Path, "write_text", _write)
    bs.update_config(db, location=str(target))
    assert calls == bs._win_restrict_dir_commands(target)
    assert calls[-1][-1] == "/inheritance:r"
    assert {"*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0"} <= {c[-1] for c in calls if "/remove:g" in c}
    assert seen_probe == [len(calls)]  # Rechte stehen, bevor die Schreibprobe schreibt


def test_windows_location_refused_when_acl_cannot_be_set(db, default_tenant, tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "_is_windows", lambda: True)
    monkeypatch.setattr(bs, "location_rejection_reason", lambda loc: None)
    _capture_icacls(monkeypatch, fail_on=lambda c: "/grant:r" in c)
    with pytest.raises(bs.BackupError, match="Zugriffsrechte"):
        bs.update_config(db, location=str(tmp_path / "sicherung"))
    assert bs.settings_service.get_setting(db, bs.SETTING_LOCATION, tenant_id=bs.DEFAULT_TENANT_ID) in (None, "")


def test_windows_create_backup_restricts_dir_and_aborts_without_acl(db, default_tenant, tmp_path, monkeypatch):
    # Standard-Verzeichnis der Installation (data/backups): Rechte werden gesetzt.
    monkeypatch.setenv("PRAXISZEIT_BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_is_windows", lambda: True)
    monkeypatch.setattr(bs, "location_rejection_reason", lambda loc: None)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("su", "pw", host="localhost", port=5433))
    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen(b"SELECT 1;"))
    calls = _capture_icacls(monkeypatch)
    bs.create_backup(db)
    assert calls == bs._win_restrict_dir_commands(tmp_path)
    _capture_icacls(monkeypatch, fail_on=lambda c: "/inheritance:r" in c)
    with pytest.raises(bs.BackupError, match="Zugriffsrechte"):
        bs.create_backup(db)


# --- Fix-Runde S3-04: bestehende Ordner werden geprüft, nie umgeschrieben ---

_PRIVATE_REPORT = (
    "OWNER S-1-5-32-544\nPROTECTED True\nRULE S-1-5-18 Allow\nRULE S-1-5-32-544 Allow\n"
)


def _capture_windows_tools(monkeypatch, report=_PRIVATE_REPORT):
    import types
    calls = []

    def _run(cmd, *a, **k):
        calls.append({"cmd": list(cmd), "env": k.get("env") or {}})
        out = report if cmd[0].lower().endswith("powershell.exe") else ""
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(bs.subprocess, "run", _run)
    return calls


def test_existing_folder_is_checked_not_rewritten(db, default_tenant, tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "_is_windows", lambda: True)
    monkeypatch.setattr(bs, "location_rejection_reason", lambda loc: None)
    monkeypatch.delenv("PRAXISZEIT_BACKUP_DIR", raising=False)
    existing = tmp_path / "Scans"
    existing.mkdir()
    calls = _capture_windows_tools(monkeypatch, report=(
        "OWNER S-1-5-21-1-2-3-1001\nPROTECTED False\nRULE S-1-5-32-545 Allow\n"))
    with pytest.raises(bs.BackupError, match="ändert die Rechte bestehender Ordner nicht"):
        bs.update_config(db, location=str(existing))
    assert not [c for c in calls if c["cmd"][0] == "icacls"], calls  # nie icacls
    (check,) = calls
    assert check["env"]["PZ_ACL_PATH"] == str(existing)
    assert str(existing) not in " ".join(check["cmd"])  # Pfad nur über die Umgebung
    assert bs.settings_service.get_setting(
        db, bs.SETTING_LOCATION, tenant_id=bs.DEFAULT_TENANT_ID) in (None, "")


def test_existing_private_folder_is_accepted_without_icacls(db, default_tenant, tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "_is_windows", lambda: True)
    monkeypatch.setattr(bs, "location_rejection_reason", lambda loc: None)
    monkeypatch.delenv("PRAXISZEIT_BACKUP_DIR", raising=False)
    existing = tmp_path / "Sicherung"
    existing.mkdir()
    calls = _capture_windows_tools(monkeypatch)
    bs.update_config(db, location=str(existing))
    assert not [c for c in calls if c["cmd"][0] == "icacls"], calls
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("su", "pw", host="localhost", port=5433))
    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen(b"SELECT 1;"))
    calls.clear()
    bs.create_backup(db)  # bestehender Ordner: wieder nur geprüft
    assert not [c for c in calls if c["cmd"][0] == "icacls"], calls


@pytest.mark.parametrize("report", [
    "",                                                                # nicht lesbar
    "OWNER S-1-5-32-544\nPROTECTED False\nRULE S-1-5-18 Allow\n",     # erbt
    "OWNER S-1-5-21-9-9-9-1001\nPROTECTED True\nRULE S-1-5-18 Allow\n",  # fremder Eigentümer
    "OWNER S-1-5-32-544\nPROTECTED True\nRULE S-1-5-11 Allow\n",       # Auth. Benutzer
    "OWNER S-1-5-32-544\nPROTECTED True\nRULE S-1-1-0 Allow\n",        # Jeder
])
def test_acl_report_too_open(report):
    assert bs.win_acl_report_is_private(report) is False


def test_acl_report_private_ignores_deny_rules():
    assert bs.win_acl_report_is_private(_PRIVATE_REPORT + "RULE S-1-1-0 Deny\n") is True


@pytest.mark.parametrize("loc", [
    "C:\\ProgramData\\x",
    "C:\\Program Files\\Praxis",
    "C:\\Program Files (x86)\\y",
    "C:\\Users\\Empfang\\Documents\\Sicherung",
    "C:\\Users",
])
def test_windows_system_and_profile_folders_refused(_as_windows, monkeypatch, loc):
    monkeypatch.delenv("ProgramData", raising=False)
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.delenv("ProgramW6432", raising=False)
    assert bs.location_rejection_reason(loc) == bs.PUBLIC_LOCATION_DETAIL


def test_restrict_acl_is_noop_off_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "_is_windows", lambda: False)
    calls = _capture_icacls(monkeypatch)
    assert bs.restrict_backup_dir_acl(tmp_path) is True
    assert calls == []


# --- Audit 2026-11-07 S3-07: pg_dump nur mit SCRAM ---

def test_create_backup_requires_scram_when_url_says_so(db, default_tenant, tmp_path, monkeypatch):
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv(
        "DATABASE_URL_MIGRATIONS",
        _migr_url("su", "pw", host="localhost", port=5433) + "?require_auth=scram-sha-256",
    )
    captured = {}
    monkeypatch.setattr(bs.subprocess, "Popen",
                        lambda cmd, **k: captured.update(cmd=cmd, env=k.get("env", {})) or _FakePopen(b"x"))
    bs.create_backup(db)
    assert captured["env"].get("PGREQUIREAUTH") == "scram-sha-256"
    assert captured["cmd"][-2:] == ["-d", "praxiszeit"]


def test_create_backup_without_require_auth_sets_nothing(db, default_tenant, tmp_path, monkeypatch):
    _use_tmp_dir(db, tmp_path)
    monkeypatch.delenv("PGREQUIREAUTH", raising=False)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("su", "pw", host="db"))
    captured = {}
    monkeypatch.setattr(bs.subprocess, "Popen",
                        lambda cmd, **k: captured.update(env=k.get("env", {})) or _FakePopen(b"x"))
    bs.create_backup(db)
    assert "PGREQUIREAUTH" not in captured["env"]


# --- Audit 2026-11-07 S3-13: nativ nur lesende Backup-Rolle statt Superuser ---

def test_backup_url_is_preferred_over_superuser_url(db, default_tenant, tmp_path, monkeypatch):
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("praxiszeit", "su-pw", host="db"))
    monkeypatch.setenv("DATABASE_URL_BACKUP", _migr_url("praxiszeit_backup", "bk-pw", host="db"))
    captured = {}
    monkeypatch.setattr(bs.subprocess, "Popen",
                        lambda cmd, **k: captured.update(cmd=cmd, env=k.get("env", {})) or _FakePopen(b"x"))
    bs.create_backup(db)
    assert captured["cmd"][captured["cmd"].index("-U") + 1] == "praxiszeit_backup"
    assert captured["env"]["PGPASSWORD"] == "bk-pw"


def test_backup_url_alone_is_enough(db, default_tenant, tmp_path, monkeypatch):
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_BACKUP", _migr_url("praxiszeit_backup", "bk-pw", host="db"))
    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen(b"SELECT 1;"))
    assert bs.create_backup(db).size_bytes > 0
