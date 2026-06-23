#!/usr/bin/env python3
"""
PraxisZeit Process Manager

Orchestrates PostgreSQL and uvicorn for native (non-Docker) installations.
Runs as a systemd service (Linux) or Windows Service (via nssm).

Usage:
    python praxiszeit-server.py start       # Start all services
    python praxiszeit-server.py stop        # Stop all services
    python praxiszeit-server.py status      # Check service status
    python praxiszeit-server.py init        # First-time initialization only
    python praxiszeit-server.py backup      # Create database backup
"""

import argparse
import logging
import os
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Determine base directory (where this script lives)
BASE_DIR = Path(__file__).resolve().parent

# Default paths (can be overridden via praxiszeit.conf)
BIN_DIR = BASE_DIR / "bin"
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
LOG_DIR = BASE_DIR / "logs"

PG_BIN = BIN_DIR / "postgresql" / "bin"
PG_DATA = DATA_DIR / "db"
BACKUP_DIR = DATA_DIR / "backups"

# Name of the dedicated PostgreSQL Windows service. On Windows postgres.exe
# refuses to run under the LocalSystem/admin token of the PraxisZeit service,
# so the cluster runs as its own NetworkService service instead of a child
# process (see pg_start). Reused as the service name when (re-)registering.
PG_SERVICE_NAME = "PraxisZeit-PostgreSQL"

# Marker file written into PG_DATA after *our* initdb. Its presence means the
# cluster was initialized by PraxisZeit (trust-bootstrapped, superuser
# "praxiszeit"). A data directory that exists WITHOUT this marker is foreign
# (e.g. an EDB-installer leftover with scram auth + "postgres" superuser) and
# must not be trusted — see cmd_start's self-healing reinit.
PG_CLUSTER_MARKER = ".praxiszeit-cluster"

BACKEND_DIR = APP_DIR / "backend"
CONFIG_FILE = CONFIG_DIR / "praxiszeit.conf"

IS_WINDOWS = platform.system() == "Windows"

# Windows NTSTATUS exit codes meaning the OS loader could not start a PG binary
# at all — it exited before running any of its own code, so there is no PG log
# to read. On Windows this is almost always a missing Microsoft Visual C++
# Redistributable: the EDB-built PostgreSQL binaries link vcruntime140*.dll.
# Field report 2026-05-26: a fresh-Windows install looped forever because
# initdb.exe exited with 3221225781 (0xC0000135) and the service kept retrying.
WIN_STATUS_DLL_NOT_FOUND = 0xC0000135    # 3221225781
WIN_STATUS_DLL_INIT_FAILED = 0xC0000142  # 3221225794
_WIN_DLL_LOAD_FAILURE_CODES = {
    WIN_STATUS_DLL_NOT_FOUND: "0xC0000135 STATUS_DLL_NOT_FOUND",
    WIN_STATUS_DLL_INIT_FAILED: "0xC0000142 STATUS_DLL_INIT_FAILED",
}
VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

# --- Logging ---

LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("praxiszeit")
logger.setLevel(logging.INFO)

_file_handler = RotatingFileHandler(
    LOG_DIR / "praxiszeit.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(_console_handler)


# --- Configuration ---

def load_config() -> dict:
    """Load configuration from praxiszeit.conf (TOML).

    Tolerant gegen UTF-8 BOM am Dateianfang: Notepad auf Windows fuegt
    beim Speichern still ein BOM hinzu, und Python's tomllib akzeptiert
    keinen BOM -> TOMLDecodeError "Invalid statement at line 1 col 1"
    obwohl die Datei inhaltlich korrekt ist. Wir strippen den BOM vor
    dem Parsen.
    """
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            logger.warning("TOML parser not available, using defaults")
            return {}

    if not CONFIG_FILE.is_file():
        return {}

    with open(CONFIG_FILE, "rb") as f:
        content = f.read()

    # UTF-8 BOM entfernen (Notepad-Fallstrick)
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
        logger.warning(
            "praxiszeit.conf enthielt UTF-8 BOM (vermutlich mit Notepad "
            "gespeichert) - wurde beim Laden entfernt. Bitte mit einem "
            "BOM-losen Editor neu speichern."
        )

    try:
        return tomllib.loads(content.decode("utf-8"))
    except UnicodeDecodeError as e:
        logger.error(
            f"praxiszeit.conf ist nicht valides UTF-8: {e}. "
            f"Bitte als UTF-8 (ohne BOM) speichern."
        )
        raise
    except tomllib.TOMLDecodeError as e:
        logger.error(
            f"praxiszeit.conf TOML-Syntax-Fehler: {e}. "
            f"Pruefe Anfuehrungszeichen, Kommata, Sections."
        )
        raise


def get_config_value(config: dict, section: str, key: str, default=None):
    """Get a value from the TOML config, with default fallback."""
    return config.get(section, {}).get(key, default)


# --- PostgreSQL Management ---

def pg_cmd(cmd: str) -> Path:
    """Get the full path to a PostgreSQL command."""
    suffix = ".exe" if IS_WINDOWS else ""
    return PG_BIN / f"{cmd}{suffix}"


def pg_env() -> dict:
    """Environment for PG subprocesses with bundled libs on the loader path.

    The bundled binaries link against transitive libraries (libpq, libicu,
    libssl, ...) shipped under bin/postgresql/lib/. On a target system whose
    distribution provides incompatible major versions of those libs (or none
    at all), the dynamic loader needs to look in our bundled lib dir first.
    """
    env = os.environ.copy()
    pg_lib = str(BIN_DIR / "postgresql" / "lib")
    if IS_WINDOWS:
        env["PATH"] = f"{pg_lib};{env.get('PATH', '')}"
    else:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{pg_lib}:{existing}" if existing else pg_lib
        # psql findet sonst den Unix-Socket im falschen Default-Pfad
        # (/var/run/postgresql) — wir verwenden unser eigenes Datenverzeichnis.
        # Hart setzen (nicht setdefault): ein vererbtes PGHOST/PGPORT aus der
        # Dienst-Umgebung würde psql/pg_dump sonst auf einen FREMDEN Cluster
        # lenken (z.B. eine System-PG). Wir wollen immer unseren eigenen Socket.
        env["PGHOST"] = str(DATA_DIR / "run")
        env.pop("PGPORT", None)
    return env


class PgRuntimeMissingError(RuntimeError):
    """A bundled PostgreSQL binary could not be launched by the OS loader.

    On Windows this is almost always the missing Microsoft Visual C++
    Redistributable: the EDB-built PG binaries link vcruntime140*.dll and exit
    with an NTSTATUS DLL-load code (e.g. 0xC0000135) BEFORE running any of
    their own code, so there is no PostgreSQL log to read. Surfacing a clear,
    actionable error beats an opaque CalledProcessError that the service
    manager then retries forever (field report 2026-05-26).
    """


def _vc_runtime_hint(exe: str, status_label: str | None = None) -> str:
    """Actionable message for a Windows PG binary the OS loader cannot start."""
    detail = f" ({status_label})" if status_label else ""
    return (
        f"{exe} konnte nicht gestartet werden{detail}. Auf diesem Windows fehlt "
        "die Microsoft Visual C++ Runtime, gegen die die gebuendelten "
        "PostgreSQL-Binaries gelinkt sind. Bitte als Administrator installieren: "
        f"{VC_REDIST_URL} — danach 'net start PraxisZeit' erneut ausfuehren."
    )


def _check_pg_launchable(returncode: int, exe: str) -> None:
    """Raise :class:`PgRuntimeMissingError` on a Windows DLL-load failure.

    No-op on non-Windows and on any non-DLL-load exit code, so it is safe to
    call right after every PG subprocess that launches a bundled binary.
    """
    if not IS_WINDOWS:
        return
    # Python may surface the NTSTATUS as the unsigned DWORD (3221225781) or its
    # signed-int twin (-1073741515); normalise to unsigned before the lookup.
    label = _WIN_DLL_LOAD_FAILURE_CODES.get(returncode & 0xFFFFFFFF)
    if label is None:
        return
    msg = _vc_runtime_hint(exe, label)
    logger.error(msg)
    raise PgRuntimeMissingError(msg)


def pg_is_running() -> bool:
    """Check whether *our* bundled PostgreSQL cluster is accepting connections.

    Unix: probe the bundled unix-socket directory (DATA_DIR/run), NEVER TCP
    localhost:5432. A foreign system PostgreSQL already listening on :5432 must
    not be mistaken for our cluster (#174) — otherwise pg_start() returns early
    ("already running") and our own socket-only cluster is never started, and
    pg_setup_database then runs psql against the wrong/absent server and crashes
    before .db-credentials is written → permanent crash-loop.

    Windows has no unix sockets; there the bundled cluster runs as its own
    NetworkService TCP service on localhost:5432, so the TCP probe is correct.
    """
    if IS_WINDOWS:
        host = "localhost"
    else:
        host = str(DATA_DIR / "run")
    try:
        result = subprocess.run(
            [str(pg_cmd("pg_isready")), "-h", host, "-p", "5432"],
            capture_output=True, timeout=5, env=pg_env(),
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _database_url(user: str, password: str, db: str) -> str:
    """Build the SQLAlchemy/psycopg2 connection URL for the bundled cluster.

    Unix: the cluster is socket-only (``listen_addresses = ''``), so we connect
    via the bundled unix-socket directory (DATA_DIR/run) — never TCP
    localhost:5432, which on a host with a foreign system PostgreSQL would
    silently hit the wrong server (#174). libpq/psycopg2 take the socket
    directory as the ``host`` query parameter.

    Windows has no unix sockets; the cluster runs as a TCP service, so the URL
    keeps the historic localhost:5432 form (unchanged behaviour).
    """
    from urllib.parse import quote, quote_plus
    # Build the userinfo (user:password) as a separate token so the source
    # never contains a literal "scheme://user:pass@" pattern — that would trip
    # the repo's secret-scanner pre-commit hook (false positive on f-string
    # placeholders). The produced URL is identical either way.
    # quote(safe="") (NOT quote_plus) for userinfo: in the userinfo component a
    # space/'+' must be %-encoded, not turned into '+' (quote_plus would corrupt
    # an operator-supplied password containing a space or '+').
    cred = f"{quote(user, safe='')}:{quote(password, safe='')}"
    if IS_WINDOWS:
        return f"postgresql://{cred}@localhost:5432/{db}"
    sock = quote_plus(str(DATA_DIR / "run"))
    return f"postgresql://{cred}@/{db}?host={sock}"


def pg_init(config: dict):
    """Initialize a new PostgreSQL data directory."""
    if PG_DATA.exists() and any(PG_DATA.iterdir()):
        logger.info("PostgreSQL data directory already initialized")
        return

    logger.info("Initializing PostgreSQL data directory...")
    PG_DATA.mkdir(parents=True, exist_ok=True)

    superuser = get_config_value(config, "database", "superuser", "praxiszeit")

    # -L: share directory (postgres.bki etc.)
    # -c dynamic_library_path: where to find extension .so files (dict_snowball etc.)
    pg_lib = str(BIN_DIR / "postgresql" / "lib").replace("\\", "/")
    pg_share = str(BIN_DIR / "postgresql" / "share" / "postgresql").replace("\\", "/")

    init_cmd = [
        str(pg_cmd("initdb")),
        "-D", str(PG_DATA),
        "-U", superuser,
        "-E", "UTF8",
        "--locale=C",
        "-A", "trust",
        "-c", f"dynamic_library_path={pg_lib}",
    ]
    # Add -L if share dir exists (bundled binaries)
    if Path(pg_share).is_dir():
        init_cmd.extend(["-L", pg_share])

    result = subprocess.run(init_cmd, env=pg_env())
    # A Windows DLL-load failure (missing VC++ runtime) gets a clear, actionable
    # error here; every other failure keeps its existing CalledProcessError.
    _check_pg_launchable(result.returncode, "initdb.exe")
    result.check_returncode()

    # pg_hba.conf starts with trust — pg_setup_database() will set passwords
    # and then harden to scram-sha-256 via pg_harden_auth().

    # Configure postgresql.conf for local-only access
    pg_conf = PG_DATA / "postgresql.conf"
    with open(pg_conf, "a") as f:
        f.write("\n# PraxisZeit configuration\n")
        if IS_WINDOWS:
            # Windows has no unix sockets; the cluster runs as a TCP service.
            f.write("listen_addresses = 'localhost'\n")
        else:
            # Socket-only on Unix: no TCP listener at all, so a foreign system
            # PostgreSQL already bound to :5432 can never collide with our
            # cluster (#174). Clients connect via the unix socket in
            # DATA_DIR/run (see unix_socket_directories below + _database_url).
            f.write("listen_addresses = ''\n")
        f.write("port = 5432\n")
        f.write("max_connections = 50\n")
        f.write("shared_buffers = 128MB\n")
        f.write("log_destination = 'stderr'\n")
        f.write("logging_collector = on\n")
        # PostgreSQL requires forward slashes even on Windows
        f.write(f"log_directory = '{str(LOG_DIR).replace(chr(92), '/')}'\n")
        f.write("log_filename = 'postgresql.log'\n")
        f.write("log_rotation_age = 1d\n")
        f.write("log_rotation_size = 10MB\n")
        # Extension libraries path (for bundled PostgreSQL)
        pg_lib = str(BIN_DIR / "postgresql" / "lib").replace("\\", "/")
        f.write(f"dynamic_library_path = '{pg_lib}'\n")
        # systemd ProtectSystem=strict blockt das default /var/run/postgresql.
        # Wir legen den Unix-Socket in unser eigenes Datenverzeichnis.
        if not IS_WINDOWS:
            pg_run = DATA_DIR / "run"
            pg_run.mkdir(parents=True, exist_ok=True)
            f.write(f"unix_socket_directories = '{pg_run}'\n")

    # Mark this cluster as PraxisZeit-managed so a later start can tell our own
    # trust-bootstrapped cluster apart from a foreign (EDB) leftover.
    (PG_DATA / PG_CLUSTER_MARKER).write_text("praxiszeit-managed\n", encoding="utf-8")

    # initdb restricts the data dir to the creating account (LocalSystem here).
    # The cluster is served by a NetworkService Windows service (see pg_start),
    # so grant that account access now — regardless of which start path
    # (register vs. start-existing-service) runs afterwards.
    if IS_WINDOWS:
        _win_grant_networkservice(PG_DATA)

    logger.info("PostgreSQL data directory initialized")


def _pg_data_is_ours() -> bool:
    """True if PG_DATA was initialized by PraxisZeit (cluster marker present)."""
    return (PG_DATA / PG_CLUSTER_MARKER).is_file()


# Decision constants for :func:`_decide_pg_init_action`. Kept as bare strings
# so the function stays trivially serialisable / loggable.
PG_ACTION_INIT = "init"
PG_ACTION_BACKFILL_MARKER = "backfill_marker"
PG_ACTION_QUARANTINE_AND_INIT = "quarantine_and_init"
PG_ACTION_START_EXISTING = "start_existing"
PG_ACTION_FAIL_NO_CREDS = "fail_no_credentials"


def _decide_pg_init_action(
    pg_data_populated: bool,
    has_marker: bool,
    has_credentials: bool,
) -> str:
    """Decide how :func:`cmd_start` should treat the on-disk PG_DATA.

    Pure function: takes only three booleans, returns one of the
    ``PG_ACTION_*`` constants. The whole point is to make the self-healing
    branch in ``cmd_start`` (PR #131 hotfix) trivially unit-testable.

    The matrix is:

    +-----------+--------+-------+-----------------------+--------------------------+
    | populated | marker | creds | action                | rationale                |
    +===========+========+=======+=======================+==========================+
    | False     | *      | *     | init                  | first run / empty PGDATA |
    +-----------+--------+-------+-----------------------+--------------------------+
    | True      | True   | True  | start_existing        | healthy PraxisZeit       |
    +-----------+--------+-------+-----------------------+--------------------------+
    | True      | True   | False | fail_no_credentials   | scram-hardened cluster,  |
    |           |        |       |                       | password unknown; caller |
    |           |        |       |                       | must surface recovery    |
    |           |        |       |                       | instructions             |
    +-----------+--------+-------+-----------------------+--------------------------+
    | True      | False  | True  | backfill_marker       | pre-marker (< 1.5.1)     |
    |           |        |       |                       | upgrade — adopt cluster, |
    |           |        |       |                       | then start_existing      |
    +-----------+--------+-------+-----------------------+--------------------------+
    | True      | False  | False | quarantine_and_init   | foreign / EDB leftover   |
    +-----------+--------+-------+-----------------------+--------------------------+

    Note the "marker + no creds" case: we deliberately do NOT quarantine
    here. The marker proves the cluster is ours; wiping the data would
    destroy real customer data. ``cmd_start`` exits with a recovery
    message instead — restore ``config/.db-credentials`` from backup, or
    remove the cluster marker to opt into a quarantine + reinit.
    """
    if not pg_data_populated:
        return PG_ACTION_INIT
    if has_marker:
        if has_credentials:
            return PG_ACTION_START_EXISTING
        return PG_ACTION_FAIL_NO_CREDS
    # No marker.
    if has_credentials:
        return PG_ACTION_BACKFILL_MARKER
    return PG_ACTION_QUARANTINE_AND_INIT


def _quarantine_pg_data() -> Path:
    """Move the existing data directory aside (never delete) and recreate an
    empty one, so a clean cluster can be initialized without risking data loss.

    We deliberately rename instead of deleting: if the directory turned out to
    hold a real (but un-credentialed) cluster rather than an EDB leftover, the
    operator can still recover it from the returned backup path. Returns the
    backup location.
    """
    backup = PG_DATA.parent / f"db.foreign-{time.strftime('%Y%m%d-%H%M%S')}"
    if PG_DATA.exists():
        PG_DATA.rename(backup)
    PG_DATA.mkdir(parents=True, exist_ok=True)
    return backup


# --- Windows service helpers (PostgreSQL runs as its own service) ---

def _win_service_exists(name: str) -> bool:
    """True if a Windows service with the given name is registered."""
    result = subprocess.run(["sc", "query", name], capture_output=True, text=True)
    # sc query returns 1060 (ERROR_SERVICE_DOES_NOT_EXIST) -> non-zero rc
    return result.returncode == 0


def _build_icacls_grant_args(path: Path, perms: str = "F") -> list[str]:
    """Build the icacls argv that grants NetworkService ``perms`` on ``path``.

    Pure / side-effect free so it can be unit-tested without invoking icacls.

    ``perms`` follows icacls' permission syntax. The two values we use:

    * ``"F"`` — Full Control. Required for PG_DATA: PostgreSQL creates/deletes
      tablespace files and rewrites configuration there.
    * ``"M"`` — Modify (read/write/append/delete OWN entries, NOT change ACL or
      take ownership). Right-sized for LOG_DIR: ``logging_collector`` only
      needs to create/append log files; we deliberately do NOT grant ``F`` so
      another NetworkService process can't tamper with permissions on the
      audit trail (anti-forensics hardening, M3).

    S-1-5-20 is the locale-independent SID for NT AUTHORITY\\NetworkService.
    ``(OI)(CI)`` propagates the ACE to existing and new child files/dirs;
    ``/T`` applies recursively to existing items; ``/Q`` suppresses per-file
    output.
    """
    return [
        "icacls", str(path), "/grant", f"*S-1-5-20:(OI)(CI){perms}", "/T", "/Q",
    ]


def _win_grant_networkservice(path: Path, perms: str = "F"):
    """Grant NT AUTHORITY\\NetworkService ``perms`` on ``path`` (default Full).

    initdb (run under the LocalSystem PraxisZeit service) restricts the data
    dir to the creating account; the NetworkService-owned postgres service
    could not otherwise read it.

    ``perms`` defaults to ``"F"`` for backward compatibility with older
    callers. Prefer the explicit form (``perms="M"``) for log directories so
    a compromised NetworkService process can't rewrite ACLs on the audit
    trail. See :func:`_build_icacls_grant_args` for the rationale.
    """
    subprocess.run(
        _build_icacls_grant_args(path, perms),
        capture_output=True, text=True,
    )


def _win_pg_unregister():
    """Stop and unregister the PostgreSQL Windows service, waiting until gone.

    Windows defers service deletion while a handle is open, which is exactly
    what made setup.bat's EDB cleanup unreliable. We stop, unregister, then
    poll until the service is really gone (or time out) so a subsequent
    register does not fail with "service already exists".
    """
    subprocess.run(["net", "stop", PG_SERVICE_NAME], capture_output=True, text=True)
    subprocess.run(
        [str(pg_cmd("pg_ctl")), "unregister", "-N", PG_SERVICE_NAME],
        capture_output=True, text=True, env=pg_env(),
    )
    for _ in range(15):
        if not _win_service_exists(PG_SERVICE_NAME):
            return
        time.sleep(1)
    logger.warning(
        f"Service {PG_SERVICE_NAME} still present after unregister; "
        "a reboot may be required if the next register fails."
    )


def _win_pg_register_and_start():
    """Register PostgreSQL as a NetworkService Windows service and start it.

    Note: pg_ctl's ``register`` subcommand only accepts -N/-D/-U/-P/-S/-e/-W/-t/-s/-o
    (no -l, no lowercase -w). Server logging is handled by logging_collector in
    postgresql.conf (see pg_init), so no log-file flag is needed here.
    """
    _win_grant_networkservice(PG_DATA)
    result = subprocess.run(
        [str(pg_cmd("pg_ctl")), "register",
         "-N", PG_SERVICE_NAME,
         "-D", str(PG_DATA),
         "-U", "NT AUTHORITY\\NetworkService",
         "-S", "auto"],
        capture_output=True, text=True, env=pg_env(),
    )
    if result.returncode != 0:
        logger.error(
            "pg_ctl register failed (rc=%s):\n%s\n%s",
            result.returncode, result.stdout, result.stderr,
        )
        sys.exit(1)
    subprocess.run(["net", "start", PG_SERVICE_NAME], capture_output=True, text=True)


def _dump_pg_startup_log() -> bool:
    """Log the tail of the PostgreSQL log(s) for debugging.

    Unix writes a startup log via ``pg_ctl start -l``; the Windows service path
    has no such file, so we also fall back to the logging_collector output
    (logs/postgresql.log) configured in pg_init.

    Returns ``True`` if a non-empty log was found and dumped. An empty result
    on Windows is itself a signal: postgres.exe never wrote a line, so it likely
    never executed (see the VC++-runtime hint in :func:`pg_start`).
    """
    for name in ("postgresql-startup.log", "postgresql.log"):
        log_file = LOG_DIR / name
        if log_file.exists() and log_file.stat().st_size > 0:
            logger.error(f"PostgreSQL log ({name}):\n{log_file.read_text(errors='replace')[-2000:]}")
            return True
    return False


def pg_start():
    """Start PostgreSQL.

    Windows: postgres.exe refuses to run under the LocalSystem/admin token of
    the PraxisZeit service, so the cluster is run as its own NetworkService
    Windows service (registered on first start) rather than a child process.

    Unix: started directly via ``pg_ctl start`` (the systemd unit already runs
    PraxisZeit under an unprivileged account, so the child process is fine).
    """
    if pg_is_running():
        logger.info("PostgreSQL is already running")
        return

    logger.info("Starting PostgreSQL...")

    if IS_WINDOWS:
        # Das PG-Dienstkonto (NetworkService) muss ins Datenverzeichnis UND nach
        # LOG_DIR schreiben koennen (postgresql.log via logging_collector). Ein
        # Update kann diese ACLs zuruecksetzen -> "could not open log file ...
        # Permission denied" -> der PG-Dienst startet nicht. Vor jedem Start
        # idempotent sicherstellen (genau dieser Fall hat eine Produktion lahmgelegt).
        #
        # LOG_DIR bekommt nur "Modify" (M3): logging_collector braucht
        # create+append+rotate, aber kein Recht ACLs umzuschreiben oder Owner
        # zu uebernehmen. Damit kann ein kompromittierter NetworkService-Prozess
        # die Audit-Logs nicht still manipulieren. PG_DATA bleibt Full Control,
        # weil PostgreSQL Tablespace-Dateien dort selbst verwaltet.
        _win_grant_networkservice(LOG_DIR, perms="M")
        _win_grant_networkservice(PG_DATA, perms="F")
        if _win_service_exists(PG_SERVICE_NAME):
            subprocess.run(["net", "start", PG_SERVICE_NAME], capture_output=True, text=True)
        else:
            _win_pg_register_and_start()
        # 60s statt 30s: auf manchen Windows-Maschinen ist der PG-Start langsam
        # (AV/ASLR, "could not reserve shared memory region"-Retries).
        for i in range(60):
            if pg_is_running():
                logger.info("PostgreSQL started successfully (Windows service)")
                return
            time.sleep(1)
        logger.error("PostgreSQL service failed to start within 60 seconds")
        if not _dump_pg_startup_log():
            # No server log at all => postgres.exe almost certainly never ran
            # (the service start failed before any logging). On a fresh Windows
            # that is overwhelmingly the missing VC++ runtime — same root cause
            # as the initdb.exe 0xC0000135 case, just on the re-start path where
            # PG runs as a service and we can't read its exit code directly.
            logger.error(_vc_runtime_hint("postgres.exe"))
        sys.exit(1)

    log_file = LOG_DIR / "postgresql-startup.log"

    subprocess.run(
        [
            str(pg_cmd("pg_ctl")),
            "-D", str(PG_DATA),
            "-l", str(log_file),
            "start",
        ],
        check=True, env=pg_env(),
    )

    # Wait for PostgreSQL to be ready
    for i in range(30):
        if pg_is_running():
            logger.info("PostgreSQL started successfully")
            return
        time.sleep(1)

    logger.error("PostgreSQL failed to start within 30 seconds")
    _dump_pg_startup_log()
    sys.exit(1)


def pg_stop():
    """Stop PostgreSQL gracefully."""
    if not pg_is_running():
        logger.info("PostgreSQL is not running")
        return

    logger.info("Stopping PostgreSQL...")
    if IS_WINDOWS:
        # Cluster runs as its own service (see pg_start) — stop it via SCM.
        subprocess.run(["net", "stop", PG_SERVICE_NAME], capture_output=True, text=True)
        logger.info("PostgreSQL stopped (Windows service)")
        return

    subprocess.run(
        [
            str(pg_cmd("pg_ctl")),
            "-D", str(PG_DATA),
            "-m", "fast",
            "stop",
        ],
        check=True, env=pg_env(),
    )
    logger.info("PostgreSQL stopped")


def _validate_pg_identifier(name: str) -> str:
    """Validate a PostgreSQL identifier to prevent SQL injection."""
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid PostgreSQL identifier: {name!r}")
    return name


def _escape_pg_password(password: str) -> str:
    """Escape a password for use in PostgreSQL ALTER ROLE ... PASSWORD '...'."""
    return password.replace("'", "''")


def _restrict_file_permissions(file_path: Path):
    """Restrict file permissions to current user + SYSTEM + local Administrators
    (Windows) or 0600 (Unix).

    F-037 (1.3.1): BUILTIN\\Administrators is granted read access so that a
    human admin can run CLI commands like ``praxiszeit-server.py backup``
    manually without tripping PermissionError on ``.db-credentials``. The
    SID ``*S-1-5-32-544`` is used instead of the localized group name so
    this works on German / English / other Windows locales identically.
    """
    if not IS_WINDOWS:
        file_path.chmod(0o600)
        return

    # SYSTEM (S-1-5-18) MUST retain read access: the service runs as LocalSystem
    # and reads .db-credentials on every start. Administrators (S-1-5-32-544) is
    # granted so a human admin can run CLI commands manually (F-037). SIDs are
    # used instead of localized names for locale independence.
    #
    # Each icacls step is best-effort and INDEPENDENT: if one fails (e.g. the
    # "<HOST>$" machine account a LocalSystem service reports as USERNAME), it
    # must not abort the rest — otherwise "/inheritance:r" could strip every ACE
    # and leave the file unreadable even for SYSTEM (observed PermissionError on
    # the next start). Explicit grants run BEFORE "/inheritance:r" so they
    # survive it.
    username = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    cmds = [
        ["icacls", str(file_path), "/grant", "*S-1-5-18:(R,W)"],     # SYSTEM
        ["icacls", str(file_path), "/grant", "*S-1-5-32-544:(R)"],   # Administrators
    ]
    # Only a real interactive user — never the machine account ("<HOST>$").
    if username and not username.endswith("$"):
        cmds.append(["icacls", str(file_path), "/grant", f"{username}:(R,W)"])
    cmds.append(["icacls", str(file_path), "/inheritance:r"])  # last: keeps explicit grants
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.warning(
                f"icacls step failed on {file_path.name} ({' '.join(cmd[2:])}): {exc}"
            )


def pg_setup_database(config: dict):
    """Create database and app user on first run."""
    superuser = _validate_pg_identifier(
        get_config_value(config, "database", "superuser", "praxiszeit")
    )
    app_user = _validate_pg_identifier(
        get_config_value(config, "database", "app_user", "praxiszeit_app")
    )
    db_name = "praxiszeit"

    # Generate passwords if not in config
    su_password = get_config_value(config, "database", "superuser_password")
    app_password = get_config_value(config, "database", "app_password")
    if not su_password:
        su_password = secrets.token_hex(32)
        logger.info("Generated superuser database password")
    if not app_password:
        app_password = secrets.token_hex(32)

    psql = str(pg_cmd("psql"))
    # "-w" = never prompt for a password. These calls run against a freshly
    # trust-bootstrapped cluster (initdb -A trust), so no password is needed.
    # Without -w, a cluster that unexpectedly requires scram auth (e.g. a
    # foreign data dir) makes psql block forever on an interactive prompt that
    # can never be answered inside a Windows service — the original F-0xx hang.
    # With -w it fails fast and check=True surfaces a clear error instead.
    subprocess.run(
        [psql, "-w", "-U", superuser, "-d", "postgres",
         "-c", f"ALTER ROLE {superuser} PASSWORD '{_escape_pg_password(su_password)}'"],
        check=True, capture_output=True, text=True, env=pg_env(),
    )

    # Check if database exists
    result = subprocess.run(
        [psql, "-w", "-U", superuser, "-d", "postgres", "-tAc",
         "SELECT 1 FROM pg_database WHERE datname = 'praxiszeit'"],
        capture_output=True, text=True, env=pg_env(),
    )

    if "1" not in result.stdout:
        logger.info(f"Creating database '{db_name}'...")
        subprocess.run(
            [psql, "-w", "-U", superuser, "-d", "postgres", "-c",
             f"CREATE DATABASE {db_name} OWNER {superuser} ENCODING 'UTF8'"],
            check=True, capture_output=True, text=True, env=pg_env(),
        )

    # Run init-db-user.sql to create app user with RLS permissions
    init_sql = BACKEND_DIR / "init-db-user.sql"
    if init_sql.is_file():
        logger.info("Setting up application database user (RLS)...")
        subprocess.run(
            [psql, "-w", "-U", superuser, "-d", db_name, "-f", str(init_sql)],
            check=True, capture_output=True, text=True, env=pg_env(),
        )

    # Set app user password
    escaped_app_pw = _escape_pg_password(app_password)
    subprocess.run(
        [psql, "-w", "-U", superuser, "-d", db_name,
         "-c", f"ALTER ROLE {app_user} PASSWORD '{escaped_app_pw}'"],
        check=True, capture_output=True, text=True, env=pg_env(),
    )

    # Store connection strings as environment variables for the backend.
    # _database_url() picks unix-socket (Unix) vs TCP (Windows) — see #174.
    os.environ["DATABASE_URL"] = _database_url(app_user, app_password, db_name)
    os.environ["DATABASE_URL_MIGRATIONS"] = _database_url(superuser, su_password, db_name)

    # Save passwords to a secure file for future starts
    _save_credentials(su_password, app_password)

    # Harden pg_hba.conf from trust to scram-sha-256 now that passwords are set
    pg_hba = PG_DATA / "pg_hba.conf"
    pg_hba.write_text(
        "# PraxisZeit PostgreSQL client authentication\n"
        "# TYPE  DATABASE  USER  ADDRESS  METHOD\n"
        "local   all       all            scram-sha-256\n"
        "host    all       all   127.0.0.1/32  scram-sha-256\n"
        "host    all       all   ::1/128       scram-sha-256\n"
    )
    subprocess.run(
        [str(pg_cmd("pg_ctl")), "-D", str(PG_DATA), "reload"],
        capture_output=True, env=pg_env(),
    )
    logger.info("Authentication hardened to scram-sha-256")

    logger.info("Database setup complete")
    return su_password, app_password


def _save_credentials(su_password: str, app_password: str):
    """Save database credentials securely."""
    creds_file = CONFIG_DIR / ".db-credentials"
    creds_file.write_text(
        f"SUPERUSER_PASSWORD={su_password}\n"
        f"APP_PASSWORD={app_password}\n"
    )
    _restrict_file_permissions(creds_file)


def pg_load_credentials():
    """Load saved database credentials for subsequent starts."""
    creds_file = CONFIG_DIR / ".db-credentials"
    if not creds_file.is_file():
        return None, None

    creds = {}
    for line in creds_file.read_text().strip().split("\n"):
        if "=" in line:
            key, value = line.split("=", 1)
            creds[key.strip()] = value.strip()

    return creds.get("SUPERUSER_PASSWORD"), creds.get("APP_PASSWORD")


# --- Alembic Migrations ---

def _redact_db_url(text: str) -> str:
    """Maskiert Passwörter in postgresql://<user>:<pass>@<host>-URLs.

    Alembic schreibt bei Verbindungsfehlern die komplette Connection-URL
    (inkl. Passwort aus DATABASE_URL_MIGRATIONS) auf stderr; ungefiltert
    landete das im rotierenden logs/praxiszeit.log (Art. 32 DSGVO).
    """
    import re
    return re.sub(r'(://[^:/@\s]+:)[^@/\s]+(@)', r'\1***\2', text)


def run_migrations(config: dict):
    """Run Alembic migrations."""
    logger.info("Running database migrations...")

    env = os.environ.copy()
    # DATABASE_URL_MIGRATIONS should already be set

    python = sys.executable
    # Invoke Alembic's CLI programmatically instead of `python -m alembic`:
    # `-m alembic` needs alembic/__main__.py to be resolvable, which can fail
    # transiently right after install while the OS/AV indexes the freshly
    # pip-installed package ("No module named alembic.__main__"). Importing
    # alembic.config is robust against that. A few retries cover the race.
    cmd = [
        python, "-c",
        "import sys; from alembic.config import main; main(sys.argv[1:])",
        "upgrade", "head",
    ]
    last_err = ""
    for attempt in range(1, 4):
        result = subprocess.run(
            cmd, cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info("Migrations complete")
            return
        last_err = result.stderr
        logger.warning(
            f"Migration attempt {attempt}/3 failed (rc={result.returncode}); "
            f"retrying in 3s...\n{_redact_db_url(result.stderr)}"
        )
        time.sleep(3)

    logger.error(f"Migration failed after 3 attempts:\n{_redact_db_url(last_err)}")
    sys.exit(1)


# --- PID File ---

PID_FILE = DATA_DIR / "praxiszeit.pid"


def _write_pid():
    """Write current process PID to file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _read_pid() -> int | None:
    """Read PID from file, return None if not found or invalid."""
    if not PID_FILE.is_file():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None


def _remove_pid():
    """Remove PID file."""
    PID_FILE.unlink(missing_ok=True)


# --- uvicorn Management ---

_uvicorn_process = None


def _detect_primary_ipv4():
    """Best-effort LAN IPv4 of this host (for the cert SubjectAltName)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def _ensure_self_signed_cert(cert_path: Path, key_path: Path, practice_name: str) -> bool:
    """Generate a self-signed cert/key pair at the given paths if missing.

    Native installs ship a config that points at config/ssl/cert.pem + key.pem
    and sets cookie_secure=true, but the installer does not currently place a
    cert there. Without this, uvicorn binds plain HTTP on the HTTPS port and the
    browser rejects the Secure refresh cookie -> broken login. Generating a
    self-signed cert here guarantees the configured SSL precondition holds.
    Operators can overwrite cert.pem/key.pem with a CA-signed pair at any time.

    Returns True if both files exist afterwards.
    """
    if cert_path.is_file() and key_path.is_file():
        return True
    try:
        import ipaddress
        import socket
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError:
        logger.warning(
            "SSL configured but cert/key missing and 'cryptography' is "
            "unavailable to generate one — starting without SSL."
        )
        return False

    logger.info("SSL cert/key missing — generating a self-signed certificate...")
    cert_path.parent.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, practice_name or "PraxisZeit"),
    ])
    sans = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
    primary = _detect_primary_ipv4()
    if primary and primary != "127.0.0.1":
        try:
            sans.append(x509.IPAddress(ipaddress.IPv4Address(primary)))
        except ipaddress.AddressValueError:
            pass
    # Also cover the machine hostname so access via https://<hostname>/ (common
    # on Windows/LAN) does not trip a name-mismatch error on top of the
    # self-signed warning.
    try:
        hostname = socket.gethostname()
        if hostname and hostname.lower() != "localhost":
            sans.append(x509.DNSName(hostname))
    except OSError:
        pass

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        # End-Entity-Server-Cert: ohne keyUsage + extendedKeyUsage=serverAuth
        # akzeptieren moderne Browser das Zertifikat nicht als Server-Cert
        # (Feldreport 2026-06). Dieser Laufzeit-Generator ist der Default-Pfad
        # für native Windows-/macOS-Installs und muss dieselben Extensions
        # setzen wie install.sh / generate-cert.sh / generate-self-signed-cert.py.
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=True,
                content_commitment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    if not IS_WINDOWS:
        try:
            key_path.chmod(0o600)
        except OSError:
            pass
    logger.info(f"Self-signed certificate written to {cert_path}")
    return True


def uvicorn_start(config: dict):
    """Start uvicorn with the FastAPI app."""
    global _uvicorn_process

    port = get_config_value(config, "server", "port", 443)
    ssl_cert = get_config_value(config, "server", "ssl_cert", "")
    ssl_key = get_config_value(config, "server", "ssl_key", "")
    # F-052: configurable bind address so a customer operator can restrict
    # to 127.0.0.1 if they reverse-proxy through IIS/Caddy. Default stays
    # 0.0.0.0 for backwards compatibility with existing Windows installs
    # that expect LAN access on port 443.
    bind_address = get_config_value(config, "server", "bind_address", "0.0.0.0")

    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", str(bind_address),
        "--port", str(port),
        "--proxy-headers",
        "--forwarded-allow-ips", "127.0.0.1,::1",
    ]

    # Add SSL if configured
    # F-053 (1.3.4): Relative paths in praxiszeit.conf like "config/ssl/cert.pem"
    # are resolved relative to BASE_DIR (the install root), not CONFIG_DIR —
    # otherwise "config/ssl/cert.pem" would resolve to
    # <install>/config/config/ssl/cert.pem and never match the actual file.
    # The default praxiszeit.conf.example uses "config/ssl/..." so BASE_DIR
    # is the correct base.
    ssl_enabled = False
    if ssl_cert and ssl_key:
        cert_path = BASE_DIR / ssl_cert if not Path(ssl_cert).is_absolute() else Path(ssl_cert)
        key_path = BASE_DIR / ssl_key if not Path(ssl_key).is_absolute() else Path(ssl_key)
        # Auto-generate a self-signed cert if the configured files are missing,
        # so a native install that requested SSL (cookie_secure=true) actually
        # serves HTTPS instead of silently degrading to plaintext + broken login.
        if not (cert_path.is_file() and key_path.is_file()):
            _ensure_self_signed_cert(
                cert_path, key_path,
                get_config_value(config, "practice", "name", "PraxisZeit"),
            )
        if cert_path.is_file() and key_path.is_file():
            cmd.extend(["--ssl-certfile", str(cert_path)])
            cmd.extend(["--ssl-keyfile", str(key_path)])
            logger.info(f"SSL enabled: {cert_path}")
            ssl_enabled = True
        else:
            logger.warning(
                f"SSL cert/key not found ({cert_path}, {key_path}), "
                f"starting without SSL"
            )

    # F-052: Loud warning if we're binding to a public interface without TLS.
    # Logged at WARNING level so it lands in the event log + startup.log.
    if bind_address in ("0.0.0.0", "::", "*") and not ssl_enabled:
        logger.warning(
            "===================================================================="
        )
        logger.warning(
            " SECURITY: Server is bound to %s WITHOUT TLS.", bind_address,
        )
        logger.warning(
            " Login cookies and patient-adjacent data traverse the network in"
        )
        logger.warning(
            " plaintext. Configure [server] ssl_cert/ssl_key in praxiszeit.conf,"
        )
        logger.warning(
            " or restrict to 127.0.0.1 via [server] bind_address = '127.0.0.1'."
        )
        logger.warning(
            "===================================================================="
        )

    # Set SERVE_FRONTEND=true for native mode
    env = os.environ.copy()
    env["SERVE_FRONTEND"] = "true"
    env["PYTHONUTF8"] = "1"  # Avoid cp1252 encoding errors on Windows
    # Native install: frontend lives at app/frontend/ (no dist/ subfolder)
    env["FRONTEND_DIR"] = str(APP_DIR / "frontend")

    logger.info(f"Starting uvicorn on port {port}...")

    _uvicorn_process = subprocess.Popen(
        cmd,
        cwd=str(BACKEND_DIR),
        env=env,
    )

    # Wait for health check
    # F-054 (1.3.4): Use ssl_enabled (actual state — file exists and was passed
    # to uvicorn) instead of the truthy check on config strings. Previously a
    # non-empty ssl_cert config entry whose file was missing caused the health
    # check to poll https:// against a plain-HTTP server, leading to an endless
    # "uvicorn failed to become healthy within 30 seconds" restart loop.
    protocol = "https" if ssl_enabled else "http"
    health_url = f"{protocol}://localhost:{port}/api/health"

    for i in range(30):
        time.sleep(1)
        try:
            import urllib.request
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                if resp.status == 200:
                    logger.info(f"PraxisZeit is ready at {protocol}://localhost:{port}")
                    return
        except Exception:
            if _uvicorn_process.poll() is not None:
                logger.error("uvicorn exited unexpectedly")
                sys.exit(1)

    logger.error("uvicorn failed to become healthy within 30 seconds")
    sys.exit(1)


def uvicorn_stop():
    """Stop uvicorn gracefully."""
    global _uvicorn_process
    if _uvicorn_process is None:
        return

    logger.info("Stopping uvicorn...")
    if IS_WINDOWS:
        _uvicorn_process.terminate()
    else:
        _uvicorn_process.send_signal(signal.SIGTERM)

    try:
        _uvicorn_process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        logger.warning("uvicorn did not stop gracefully, killing...")
        _uvicorn_process.kill()

    _uvicorn_process = None
    logger.info("uvicorn stopped")


# --- Database Backup ---

def create_backup(config: dict):
    """Create a compressed database backup."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    superuser = get_config_value(config, "database", "superuser", "praxiszeit")
    su_password, _ = pg_load_credentials()

    # Without credentials we cannot authenticate to the (scram) cluster. Bail
    # out instead of running pg_dump with no password — otherwise pg_dump blocks
    # forever on an interactive password prompt that can never be answered in a
    # service / headless-updater context (the backup-step hang on update).
    if not su_password:
        logger.error(
            "No database credentials found (.db-credentials missing) — "
            "skipping backup. The database is not initialized yet."
        )
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"praxiszeit_{timestamp}.sql.gz"

    logger.info(f"Creating backup: {backup_file}")

    # Plain-SQL-Format (NICHT -Fc!): pg_dumps Custom-Format ist bereits komprimiert;
    # ein zweites gzip darueber erzeugt ein DOPPELT komprimiertes Artefakt, das die
    # dokumentierten "gunzip | psql"-Restores NICHT einlesen koennen (psql parst
    # Custom-Format-Binaerdaten als SQL -> Syntaxfehler). Plain-SQL + gzip ist mit
    # "gunzip -c <datei>.sql.gz | psql" restorebar. "--clean --if-exists" macht den
    # Restore idempotent (DROP ... IF EXISTS vor jedem CREATE), auch in eine bereits
    # befuellte DB. "-w": nie nach Passwort fragen (fail fast statt Haenger).
    pg_dump = subprocess.Popen(
        [str(pg_cmd("pg_dump")), "-w", "--clean", "--if-exists",
         "-U", superuser, "-d", "praxiszeit"],
        stdout=subprocess.PIPE,
        env={**pg_env(), "PGPASSWORD": su_password},
    )

    import gzip
    write_error = None
    try:
        with open(backup_file, "wb") as f:
            with gzip.open(f, "wb") as gz:
                while True:
                    chunk = pg_dump.stdout.read(8192)
                    if not chunk:
                        break
                    gz.write(chunk)
    except OSError as e:  # z. B. Platte voll waehrend des Schreibens
        write_error = e
    finally:
        if pg_dump.stdout:
            pg_dump.stdout.close()

    pg_dump.wait()
    # Erfolg nur, wenn pg_dump sauber durchlief UND eine nicht-leere Datei entstand.
    # Sonst wuerde ein truncated/leeres Backup als "complete" geloggt und ueberlebte
    # die Retention -> stiller Datenverlust im Ernstfall.
    if (write_error is not None or pg_dump.returncode != 0
            or not backup_file.exists() or backup_file.stat().st_size == 0):
        logger.error(
            f"Backup failed (rc={pg_dump.returncode}, write_error={write_error})!"
        )
        backup_file.unlink(missing_ok=True)
        return None

    logger.info(f"Backup complete: {backup_file} ({backup_file.stat().st_size / 1024:.0f} KB)")

    # Cleanup old backups
    retention_days = get_config_value(config, "backup", "retention_days", 31)
    cutoff = time.time() - (retention_days * 86400)
    for old_backup in BACKUP_DIR.glob("praxiszeit_*.sql.gz"):
        if old_backup.stat().st_mtime < cutoff:
            old_backup.unlink()
            logger.info(f"Removed old backup: {old_backup.name}")

    return backup_file


# --- Signal Handling ---

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    logger.info(f"Received signal {signum}, shutting down...")
    _shutdown_requested = True


PG_UPGRADE_RESTORE_MARKER = DATA_DIR / ".pg-upgrade-restore"


def _restore_pending_major_upgrade():
    """PG-Major-Upgrade (z. B. 16 -> 18): install.sh hat mit den ALTEN Binaries
    gedumpt, das alte Datenverzeichnis zur Seite gelegt (``data/db.pgXX-<ts>``,
    NIE gelöscht) und den Dump-Pfad in den Marker geschrieben. Hier — nachdem
    cmd_start den frischen PGNN-Cluster initialisiert + die DB/Rollen angelegt hat
    — spielen wir den Dump in die leere ``praxiszeit``-DB ein. Idempotent: ohne
    Marker passiert nichts; bei Restore-Fehler bleibt der Marker + das alte
    Datenverzeichnis erhalten (recoverable), und wir brechen ab statt mit
    Teildaten weiterzulaufen."""
    if not PG_UPGRADE_RESTORE_MARKER.exists():
        return
    dump = Path(PG_UPGRADE_RESTORE_MARKER.read_text().strip())
    if not dump.is_file():
        # Marker da, Dump weg: NICHT stillschweigend mit leerer DB weiterlaufen —
        # die Alt-Daten liegen noch unter data/db.pg*. Abbrechen; der Operator
        # spielt den Dump zurück ODER entfernt den Marker bewusst.
        raise RuntimeError(
            f"PG-Upgrade-Marker vorhanden, aber Dump-Datei fehlt: {dump}. "
            "Bitte den Dump wiederherstellen oder data/.pg-upgrade-restore manuell entfernen, "
            "um einen Start ohne Restore zu erzwingen (Alt-Daten unter data/db.pg* erhalten)."
        )
    su_password, _ = pg_load_credentials()
    if not su_password:
        raise RuntimeError("PG-Upgrade-Restore: keine Superuser-Credentials gefunden.")
    logger.info("PostgreSQL-Major-Upgrade: spiele gesicherten Daten-Dump ein (%s)...", dump.name)
    # Streamend in eine temporäre .sql-Datei entpacken (NICHT den ganzen Dump in
    # den RAM laden -> kein OOM auf kleinen VPS) und per `psql -f` einspielen.
    # ON_ERROR_STOP=1: jeder echte Fehler -> Exit != 0 (die DROP … IF EXISTS aus
    # --clean --if-exists erzeugen in der frischen DB keine Fehler) — zuverlässiger
    # als das vorherige stderr-"ERROR"-Zeilenzählen.
    import gzip
    import shutil
    import tempfile
    env = {**pg_env(), "PGPASSWORD": su_password}
    tmp_path = None
    proc = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False, dir=str(DATA_DIR)) as tmp:
            tmp_path = tmp.name
            # DSGVO Art. 32: der entpackte Klartext-Dump enthält personenbezogene
            # Daten -> explizit nur Owner-lesbar (NamedTemporaryFile ist zwar schon
            # 0600, aber explizit = robust gegen künftige Umstellungen).
            os.chmod(tmp_path, 0o600)
            with gzip.open(dump, "rb") as gz:
                shutil.copyfileobj(gz, tmp)
        proc = subprocess.run(
            [str(pg_cmd("psql")), "-w", "-U", "praxiszeit", "-d", "praxiszeit",
             "-v", "ON_ERROR_STOP=1", "-f", tmp_path],
            env=env, capture_output=True,
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    if proc is None:
        # gzip/copy ist geflogen -> NICHT in den UnboundLocalError laufen, sondern
        # klar melden (Alt-Daten + Dump bleiben erhalten).
        raise RuntimeError(
            "PG-Upgrade-Restore: Dump konnte nicht entpackt werden (I/O-Fehler oder "
            "korrupte Datei) — alte Daten unter data/db.pg* erhalten."
        )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace") if proc.stderr else ""
        logger.error(
            "PG-Upgrade-Restore fehlgeschlagen (Exit %s). Das alte Datenverzeichnis "
            "(data/db.pg*) + der Dump bleiben erhalten — bitte manuell wiederherstellen. "
            "Letzte Fehler:\n%s",
            proc.returncode, "\n".join(stderr.splitlines()[-8:]),
        )
        raise RuntimeError("PG-Upgrade-Restore fehlgeschlagen — alte Daten unter data/db.pg* erhalten.")
    logger.info("PostgreSQL-Major-Upgrade: Daten erfolgreich eingespielt.")
    PG_UPGRADE_RESTORE_MARKER.unlink()


# --- Main Commands ---

def cmd_start(args):
    """Start PraxisZeit (PostgreSQL + uvicorn)."""
    config = load_config()

    logger.info("=" * 60)
    logger.info("PraxisZeit starting...")
    logger.info("=" * 60)

    # 1. Initialize PostgreSQL if needed
    creds_file = CONFIG_DIR / ".db-credentials"
    pg_data_populated = PG_DATA.exists() and any(PG_DATA.iterdir())
    action = _decide_pg_init_action(
        pg_data_populated=pg_data_populated,
        has_marker=_pg_data_is_ours(),
        has_credentials=creds_file.is_file(),
    )

    # Map the pure decision onto the actual side effects. ``needs_setup``
    # mirrors the previous semantics: "do we need to (re)bootstrap roles +
    # passwords?" — true on init, false when we're starting an existing
    # cluster with credentials.
    needs_initdb = action in (PG_ACTION_INIT, PG_ACTION_QUARANTINE_AND_INIT)
    needs_setup = needs_initdb

    if action == PG_ACTION_BACKFILL_MARKER:
        # Pre-marker upgrade (< 1.5.1): a healthy PraxisZeit cluster with
        # credentials but no marker file. Adopt it so a future credentials
        # loss is never mistaken for a foreign cluster and quarantined.
        try:
            (PG_DATA / PG_CLUSTER_MARKER).write_text("praxiszeit-managed\n", encoding="utf-8")
            logger.info("Backfilled PraxisZeit cluster marker on existing data directory.")
        except OSError as exc:
            logger.warning(f"Could not write cluster marker: {exc}")
        # After backfill we proceed as start_existing — no reinit, no setup.

    elif action == PG_ACTION_FAIL_NO_CREDS:
        # Marker says the cluster is ours (scram-hardened), but the
        # credentials file is gone — pg_setup_database would issue
        # ALTER ROLE / psql against a cluster whose password we no longer
        # know and either hang or report an opaque scram error. Tell the
        # operator exactly what to do instead of spinning. Recovery options
        # are documented in docs/INSTALL-NATIVE.md ("Disaster Recovery").
        logger.error(
            ".db-credentials is missing, but the data directory is already "
            "initialized (PraxisZeit cluster marker present). The cluster is "
            "scram-hardened and cannot be re-bootstrapped without its existing "
            "credentials. Recovery options are documented in "
            "docs/INSTALL-NATIVE.md (section 'Disaster Recovery: verlorene "
            ".db-credentials'). Short version: either restore "
            "config/.db-credentials from backup, or remove the cluster marker "
            "%s/.praxiszeit-cluster (the data dir will then be moved aside to "
            "data/db.foreign-<timestamp> and a fresh cluster will be created)."
            % str(PG_DATA)
        )
        sys.exit(1)

    elif action == PG_ACTION_QUARANTINE_AND_INIT:
        # Self-healing: PG_DATA exists but was NOT initialized by us
        # (no marker) and has no credentials file — typically an
        # EDB-installer leftover with scram auth and the "postgres"
        # superuser. Trusting it would make pg_setup_database's trust-based
        # psql calls fail (or, before -w, hang). Move it aside and
        # re-initialize a clean, trust-bootstrapped cluster.
        logger.warning(
            "PostgreSQL data directory exists but is not PraxisZeit-managed and "
            "no credentials file was found — moving it aside and reinitializing "
            "a clean cluster. The old directory is preserved (not deleted)."
        )
        if IS_WINDOWS and _win_service_exists(PG_SERVICE_NAME):
            _win_pg_unregister()
        elif pg_is_running():
            pg_stop()
        backup = _quarantine_pg_data()
        logger.warning(f"Previous data directory preserved at: {backup}")

    if needs_initdb:
        pg_init(config)

    # 2. Start PostgreSQL
    pg_start()

    # 3. Setup database if needed (first run or missing credentials)
    if needs_setup:
        pg_setup_database(config)
    else:
        # Load saved credentials
        su_password, app_password = pg_load_credentials()
        if su_password and app_password:
            superuser = get_config_value(config, "database", "superuser", "praxiszeit")
            app_user = get_config_value(config, "database", "app_user", "praxiszeit_app")
            os.environ["DATABASE_URL"] = _database_url(app_user, app_password, "praxiszeit")
            os.environ["DATABASE_URL_MIGRATIONS"] = _database_url(
                superuser, su_password, "praxiszeit"
            )
        else:
            logger.error("Database credentials not found. Run 'praxiszeit-server init' first.")
            pg_stop()
            sys.exit(1)

    # 3a1. PG-Major-Upgrade: falls install.sh die Alt-Daten gedumpt + zur Seite
    # gelegt hat (Marker), den Dump jetzt in den frischen Cluster einspielen.
    # Idempotent (no-op ohne Marker); läuft NACH pg_setup_database (DB + Rollen da).
    _restore_pending_major_upgrade()

    # 3a2. #213: Der Backup-Service im Backend braucht das Ziel-Verzeichnis UND
    # den gebuendelten pg_dump-Pfad — anders als im Docker-Image liegt pg_dump
    # nativ nicht im PATH. Beide statisch (nicht cred-abhaengig) -> hier einmal
    # fuer beide Start-Pfade (Erstsetup + Folgestart) gesetzt.
    os.environ["PRAXISZEIT_BACKUP_DIR"] = str(BACKUP_DIR)
    os.environ["PRAXISZEIT_PG_DUMP"] = str(pg_cmd("pg_dump"))

    # 3b. Set environment variables from config for backend (Pydantic Settings)
    _CONF_TO_ENV = {
        ("admin", "email"): "ADMIN_EMAIL",
        ("admin", "password"): "ADMIN_PASSWORD",
        ("admin", "username"): "ADMIN_USERNAME",
        ("admin", "first_name"): "ADMIN_FIRST_NAME",
        ("admin", "last_name"): "ADMIN_LAST_NAME",
        ("practice", "name"): "PRACTICE_NAME",
        ("practice", "address"): "PRACTICE_ADDRESS",
        ("practice", "holiday_state"): "HOLIDAY_STATE",
        ("security", "login_rate_limit"): "LOGIN_RATE_LIMIT",
        ("security", "cookie_secure"): "COOKIE_SECURE",
        ("license", "key_file"): "LICENSE_KEY_PATH",
        ("updates", "check_enabled"): "UPDATE_CHECK_ENABLED",
        ("updates", "server_url"): "UPDATE_SERVER_URL",
        ("updates", "check_interval_hours"): "UPDATE_CHECK_INTERVAL_HOURS",
        ("backup", "enabled"): "BACKUP_ENABLED",
        ("backup", "schedule"): "BACKUP_SCHEDULE",
        ("backup", "retention_days"): "BACKUP_RETENTION_DAYS",
    }
    # Config keys whose values are file paths (resolve relative to BASE_DIR)
    _PATH_KEYS = {"LICENSE_KEY_PATH"}
    for (section, key), env_name in _CONF_TO_ENV.items():
        if env_name not in os.environ:
            val = get_config_value(config, section, key)
            if val is not None:
                str_val = str(val).lower() if isinstance(val, bool) else str(val)
                if env_name in _PATH_KEYS and not Path(str_val).is_absolute():
                    str_val = str(BASE_DIR / str_val)
                os.environ[env_name] = str_val

    # Generate SECRET_KEY if not configured — persist so sessions survive restarts
    if "SECRET_KEY" not in os.environ:
        sk = get_config_value(config, "security", "secret_key")
        if not sk:
            # Check if previously generated key exists in credentials file
            sk_file = CONFIG_DIR / ".secret-key"
            if sk_file.is_file():
                sk = sk_file.read_text().strip()
            else:
                sk = secrets.token_hex(32)
                # Datei atomar mit 0600 anlegen (O_EXCL|mode) statt write_text +
                # nachträglichem chmod — schliesst das umask-Fenster, in dem die
                # frische .secret-key kurz world-readable sein konnte (Linux).
                # Auf Windows greift zusätzlich _restrict_file_permissions (ACL).
                try:
                    _fd = os.open(str(sk_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    try:
                        os.write(_fd, sk.encode("ascii"))
                    finally:
                        os.close(_fd)
                except FileExistsError:
                    # Race: anderer Start hat die Datei gerade angelegt — diese nutzen
                    sk = sk_file.read_text().strip()
                _restrict_file_permissions(sk_file)
                logger.info("Generated and saved SECRET_KEY")
        os.environ["SECRET_KEY"] = sk

    # 4. Run migrations
    run_migrations(config)

    # 5. Start uvicorn
    uvicorn_start(config)

    # 6. Write PID file + setup signal handlers
    _write_pid()
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # 7. Watchdog loop
    logger.info("PraxisZeit is running. Press Ctrl+C to stop.")
    while not _shutdown_requested:
        time.sleep(5)

        # Check if uvicorn is still alive
        if _uvicorn_process and _uvicorn_process.poll() is not None:
            logger.error("uvicorn exited unexpectedly, restarting...")
            uvicorn_start(config)

        # Check if PostgreSQL is still alive
        if not pg_is_running():
            logger.error("PostgreSQL is not responding, restarting...")
            pg_start()

    # Shutdown
    logger.info("Shutting down PraxisZeit...")
    uvicorn_stop()
    pg_stop()
    _remove_pid()
    logger.info("PraxisZeit stopped.")


def cmd_stop(args):
    """Stop PraxisZeit (finds running process via PID file)."""
    pid = _read_pid()
    if pid:
        logger.info(f"Sending SIGTERM to PraxisZeit process (PID {pid})...")
        try:
            os.kill(pid, signal.SIGTERM)
            # Wait for process to exit
            for _ in range(30):
                try:
                    os.kill(pid, 0)
                    time.sleep(1)
                except ProcessLookupError:
                    break
            logger.info("PraxisZeit stopped via PID file")
        except ProcessLookupError:
            logger.info("Process already stopped")
        _remove_pid()
    else:
        # Fallback: stop PostgreSQL directly
        logger.info("No PID file found, stopping PostgreSQL directly...")
        pg_stop()


def cmd_status(args):
    """Show service status."""
    pg_running = pg_is_running()
    print(f"PostgreSQL: {'running' if pg_running else 'stopped'}")

    # Check if uvicorn is responding
    try:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen("https://localhost/api/health", context=ctx, timeout=3):
            print("uvicorn:    running (healthy)")
    except Exception:
        try:
            with urllib.request.urlopen("http://localhost/api/health", timeout=3):
                print("uvicorn:    running (healthy, no SSL)")
        except Exception:
            print("uvicorn:    stopped or not responding")

    # Database info
    if pg_running:
        config = load_config()
        su_password, _ = pg_load_credentials()
        if su_password:
            superuser = get_config_value(config, "database", "superuser", "praxiszeit")
            result = subprocess.run(
                [str(pg_cmd("psql")), "-w", "-U", superuser, "-d", "praxiszeit",
                 "-tAc", "SELECT count(*) FROM users WHERE is_active = true"],
                capture_output=True, text=True,
                env={**pg_env(), "PGPASSWORD": su_password},
            )
            if result.returncode == 0:
                print(f"Active users: {result.stdout.strip()}")


def cmd_init(args):
    """First-time initialization only."""
    config = load_config()
    pg_init(config)
    pg_start()
    pg_setup_database(config)
    run_migrations(config)
    logger.info("Initialization complete. Run 'praxiszeit-server start' to start the application.")
    pg_stop()


def cmd_backup(args):
    """Create a database backup."""
    config = load_config()
    if not pg_is_running():
        logger.error("PostgreSQL is not running. Start PraxisZeit first.")
        sys.exit(1)
    create_backup(config)


def main():
    parser = argparse.ArgumentParser(
        description="PraxisZeit Process Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("start", help="Start PraxisZeit").set_defaults(func=cmd_start)
    subparsers.add_parser("stop", help="Stop PraxisZeit").set_defaults(func=cmd_stop)
    subparsers.add_parser("status", help="Show service status").set_defaults(func=cmd_status)
    subparsers.add_parser("init", help="First-time database initialization").set_defaults(func=cmd_init)
    subparsers.add_parser("backup", help="Create database backup").set_defaults(func=cmd_backup)

    args = parser.parse_args()
    try:
        args.func(args)
    except PgRuntimeMissingError:
        # The actionable message + remediation URL were already logged at the
        # failure site. Exit cleanly (no traceback) so the service log shows the
        # fix to apply, not a confusing Python stack trace on every restart.
        sys.exit(1)


if __name__ == "__main__":
    main()
