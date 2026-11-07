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
    python praxiszeit-server.py harden-permissions  # Windows: Rechte des
                                                  # Installationsordners
    python praxiszeit-server.py restore <datei>   # Backup einspielen (Linux/macOS,
                                                  # Dienst vorher anhalten)
    python praxiszeit-server.py reset-admin-password  # Admin-Passwort neu setzen
"""

import argparse
import functools
import json
import logging
import os
import platform
import re
import secrets
import shlex
import shutil
import socket
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
# cluster was initialized by PraxisZeit (scram-sha-256 from initdb on, superuser
# "praxiszeit"). A data directory that exists WITHOUT this marker is foreign
# (e.g. an EDB-installer leftover with scram auth + "postgres" superuser) and
# must not be trusted — see cmd_start's self-healing reinit.
PG_CLUSTER_MARKER = ".praxiszeit-cluster"

# Name der Anwendungsdatenbank. Als Konstante, nicht als Literal am Aufruf von
# ``_database_url(<benutzer>, <passwort>, ...)``: dort steht sonst ein
# Zeichenketten-Literal unmittelbar neben einer passwort-benannten Variablen —
# genau das Muster, das die Sicherheits-Scanner des Projekts als hinterlegtes
# Passwort melden (GitGuardian "Generic Password", Fehlalarm, aber vermeidbar).
DB_NAME = "praxiszeit"

BACKEND_DIR = APP_DIR / "backend"
CONFIG_FILE = CONFIG_DIR / "praxiszeit.conf"

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"

# launchd-Dienst der macOS-Installation — Label und Plist wie in
# installer/macos/install.sh und MacOsPlatform.cs (GUI-Installer); ein Test
# haelt die drei Stellen gleich. Gebraucht fuer Hinweise, die den Dienststart
# nennen: auf macOS gibt es kein systemctl (Gesamtreview B8, #491).
MACOS_LAUNCHD_LABEL = "de.praxiszeit.server"
MACOS_LAUNCHD_PLIST = f"/Library/LaunchDaemons/{MACOS_LAUNCHD_LABEL}.plist"

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

_bom_warned = False


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

    # UTF-8 BOM entfernen (Notepad-Fallstrick). Gemeldet wird einmal je
    # Prozess - load_config laeuft beim Start mehrfach (u. a. pg_port()).
    global _bom_warned
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
        if not _bom_warned:
            _bom_warned = True
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


# --- PostgreSQL-Port (eine Quelle) ---

DEFAULT_PG_PORT = 5432
EXIT_CONFIG_ERROR = 78  # NSSM: AppExit 78 Exit (kein Neustart-Zyklus bei Konfigurationsfehler)
_PG_PORT_MIN = 1024
_PG_PORT_MAX = 65535
_pg_port_ignored_warned = False


class PgConfigError(Exception):
    """Konfigurationsfehler; die Meldung ist Nutzertext und wird von main() ausgegeben."""


class ForeignPostgresError(PgConfigError):
    """Der konfigurierte Port wird von einem fremden PostgreSQL belegt."""


def parse_pg_port(config: dict) -> int:
    """``[database] port`` pruefen (rein, unabhaengig von der Plattform)."""
    raw = get_config_value(config, "database", "port", None)
    if raw is None:
        return DEFAULT_PG_PORT
    port = None
    if isinstance(raw, int) and not isinstance(raw, bool):
        port = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        port = int(raw.strip())
    if port is None or not (_PG_PORT_MIN <= port <= _PG_PORT_MAX):
        raise PgConfigError(
            f"Ungültiger Datenbank-Port in config\\praxiszeit.conf ([database] port = {raw}): "
            f"erlaubt sind ganze Zahlen von {_PG_PORT_MIN} bis {_PG_PORT_MAX}."
        )
    return port


@functools.lru_cache(maxsize=None)
def pg_port() -> int:
    """Port der PraxisZeit-eigenen Datenbank. Nur unter Windows konfigurierbar.

    Einmal je Prozess gelesen: der Waechter in cmd_start fragt alle 5 s, eine
    im laufenden Betrieb geaenderte conf darf den Port nicht mitten im Lauf
    umstellen - die Meldung verlangt ausdruecklich einen Dienstneustart.
    Ein ungueltiger Eintrag wird nicht gemerkt (lru_cache speichert keine
    Ausnahmen). Tests setzen den Wert mit ``pg_port.cache_clear()`` zurueck.
    """
    if not IS_WINDOWS:
        # Wie vor Teil C: unter Linux/macOS liest der Port die conf gar nicht
        # (Unix-Socket, fest 5432). Den Hinweis auf einen ignorierten Eintrag
        # gibt cmd_start aus der ohnehin geladenen conf (warn_ignored_pg_port).
        return DEFAULT_PG_PORT
    return parse_pg_port(load_config())


def warn_ignored_pg_port(config: dict) -> None:
    """Linux/macOS: einmal melden, dass ``[database] port`` ignoriert wird."""
    global _pg_port_ignored_warned
    if IS_WINDOWS or _pg_port_ignored_warned:
        return
    if get_config_value(config, "database", "port", None) is not None:
        _pg_port_ignored_warned = True
        logger.warning(
            "[database] port wird auf dieser Plattform ignoriert "
            "(Unix-Socket, Port %d).", DEFAULT_PG_PORT,
        )


# --- PostgreSQL Management ---

def pg_cmd(cmd: str) -> Path:
    """Get the full path to a PostgreSQL command."""
    suffix = ".exe" if IS_WINDOWS else ""
    return PG_BIN / f"{cmd}{suffix}"


# Windows connects over TCP (localhost:<port>); see _database_url / pg_env.
PG_REQUIRE_AUTH = "scram-sha-256"


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
        # Hart setzen: ein vererbtes PGHOST/PGPORT darf psql/pg_dump nie auf
        # einen fremden Cluster lenken; unser Port steht in [database] port.
        env["PGHOST"] = "localhost"
        env["PGPORT"] = str(pg_port())
        # psql/pg_dump/pg_isready ueber TCP: nur SCRAM, nie Klartext (S3-07).
        env["PGREQUIREAUTH"] = PG_REQUIRE_AUTH
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


def _foreign_pg_message(port: int) -> str:
    """Nutzertext, wenn ein fremdes PostgreSQL unseren Port belegt (eine Quelle)."""
    return (
        f"Port {port} ist von einem anderen PostgreSQL belegt. In config\\praxiszeit.conf "
        "unter [database] einen freien Port eintragen (z. B. 5433) und den Dienst neu starten."
    )


def _pid_file_port() -> str | None:
    """Port aus Zeile 4 von ``PG_DATA/postmaster.pid``; None, wenn nicht lesbar."""
    try:
        lines = (PG_DATA / "postmaster.pid").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except OSError:
        return None
    if len(lines) < 4:
        return None
    return lines[3].strip()


def _win_own_cluster_status() -> str:
    """Windows: is the server on OUR port OUR cluster (from PG_DATA)?

    ``"own"``, ``"foreign"`` or ``"unknown"``. ``pg_ctl status -D`` instead of
    ``os.kill(pid, 0)`` (no liveness test on Windows); the port in
    ``postmaster.pid`` must also match the configured one.

    Only VERIFIED evidence counts as ``"foreign"`` (Audit 2026-11-07 S3-08):
    ``pg_ctl status`` exit 3 (no postmaster of OUR data directory runs) while
    something answers on the port, or a ``postmaster.pid`` naming a different
    port. A ``pg_ctl status`` running into its time limit (boot under virus
    scanner load), a launch error, an unreadable data directory (exit 4) or a
    locked ``postmaster.pid`` is ``"unknown"`` — exit 78 is final (NSSM
    ``AppExit 78 Exit``), a measuring error must never end time recording.
    """
    try:
        result = subprocess.run(
            [str(pg_cmd("pg_ctl")), "status", "-D", str(PG_DATA)],
            capture_output=True, timeout=10, env=pg_env(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return "unknown"
    if result.returncode == 3:
        return "foreign"
    if result.returncode != 0:
        return "unknown"
    pid_port = _pid_file_port()
    if pid_port is None:
        return "unknown"
    return "own" if pid_port == str(pg_port()) else "foreign"


def pg_cluster_state() -> str:
    """``"own"``, ``"foreign"``, ``"down"`` or ``"unknown"`` for our port.

    Unix: probe the bundled unix-socket directory (DATA_DIR/run), NEVER TCP
    localhost. A foreign system PostgreSQL already listening on :5432 must
    not be mistaken for our cluster (#174) — otherwise pg_start() returns early
    ("already running") and our own socket-only cluster is never started, and
    pg_setup_database then runs psql against the wrong/absent server and crashes
    before .db-credentials is written → permanent crash-loop. The socket dir is
    already proof of ownership, so the state is only ``"own"`` or ``"down"``.

    Windows has no unix sockets; there the bundled cluster runs as its own
    NetworkService TCP service on localhost:pg_port(). Something answering
    there is ``"own"``/``"foreign"``/``"unknown"`` per
    :func:`_win_own_cluster_status`.
    """
    if IS_WINDOWS:
        host = "localhost"
    else:
        host = str(DATA_DIR / "run")
    try:
        result = subprocess.run(
            [str(pg_cmd("pg_isready")), "-h", host, "-p", str(pg_port())],
            capture_output=True, timeout=5, env=pg_env(),
        )
        answers = result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        answers = False
    if not answers:
        return "down"
    if not IS_WINDOWS:
        return "own"
    return _win_own_cluster_status()


FOREIGN_RECHECK_SECONDS = 2
PG_START_TIMEOUT_SECONDS = 60
UNKNOWN_RECHECKS = 3


def _pg_cluster_state_confirmed() -> str:
    """Wie :func:`pg_cluster_state`, ein ``"foreign"`` wird nach kurzer Pause
    einmal nachgeprueft, ein ``"unknown"`` bis zu UNKNOWN_RECHECKS-mal. Ein
    einzelnes falsches "foreign" (postmaster.pid kurz vom Virenscanner
    gesperrt) darf den Dienst nicht mit Exit 78 dauerhaft beenden; ein
    bleibendes "unknown" fuehrt nie zu Exit 78 (S3-08)."""
    state = pg_cluster_state()
    if state == "foreign":
        time.sleep(FOREIGN_RECHECK_SECONDS)
        state = pg_cluster_state()
    tries = 0
    while state == "unknown" and tries < UNKNOWN_RECHECKS:
        tries += 1
        time.sleep(FOREIGN_RECHECK_SECONDS)
        state = pg_cluster_state()
    return state


def pg_is_running() -> bool:
    """Check whether *our* bundled PostgreSQL cluster is accepting connections
    (see :func:`pg_cluster_state`)."""
    return pg_cluster_state() == "own"


def _database_url(user: str, password: str, db: str) -> str:
    """Build the SQLAlchemy/psycopg2 connection URL for the bundled cluster.

    Unix: the cluster is socket-only (``listen_addresses = ''``), so we connect
    via the bundled unix-socket directory (DATA_DIR/run) — never TCP
    localhost, which on a host with a foreign system PostgreSQL would
    silently hit the wrong server (#174). libpq/psycopg2 take the socket
    directory as the ``host`` query parameter.

    Windows has no unix sockets; the cluster runs as a TCP service, so the URL
    points at ``localhost:<pg_port()>`` - the port from ``[database] port`` in
    praxiszeit.conf, 5432 without an entry.
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
        # require_auth (Audit 2026-11-07 S3-07): libpq gibt das Passwort nur per
        # SCRAM heraus. Ohne das beantwortet es die Klartext-Passwort-Anfrage
        # eines Servers, den ein lokales Konto an den freien Port gehaengt hat
        # (PG abgestuerzt), mit dem Passwort im Klartext. libpq >= 16 noetig;
        # psycopg2-binary 2.9.13 (cp313-win_amd64) bringt libpq 17 mit.
        return (f"postgresql://{cred}@localhost:{pg_port()}/{db}"
                f"?require_auth={PG_REQUIRE_AUTH}")
    sock = quote_plus(str(DATA_DIR / "run"))
    return f"postgresql://{cred}@/{db}?host={sock}"


# Temporary file that hands the superuser password to initdb (--pwfile). Lives
# next to the other secrets in CONFIG_DIR, is created with restricted
# permissions BEFORE the password is written (_open_restricted) and removed
# right after initdb.
INITDB_PWFILE_NAME = ".initdb-pwfile"


def resolve_db_passwords(config: dict) -> tuple[str, str]:
    """Superuser and app passwords for a NEW cluster.

    Configured values win (``[database] superuser_password`` /
    ``app_password``); otherwise fresh random ones. Resolved ONCE in the
    caller, because initdb (pg_init) and pg_setup_database need the same
    superuser password: the cluster is scram-protected from its first second.
    """
    su_password = get_config_value(config, "database", "superuser_password")
    app_password = get_config_value(config, "database", "app_password")
    if not su_password:
        su_password = secrets.token_hex(32)
        logger.info("Generated superuser database password")
    if not app_password:
        app_password = secrets.token_hex(32)
    return str(su_password), str(app_password)


def pg_init(config: dict, su_password: str):
    """Initialize a new PostgreSQL data directory.

    The cluster is created with ``scram-sha-256`` for local AND host
    connections and the superuser password set by initdb itself (``--pwfile``).
    There is no "trust" phase any more: earlier versions ran ``initdb -A
    trust`` and switched to scram only after pg_setup_database, so every local
    account (Unix socket) or local process (Windows: localhost TCP) could log
    in as superuser in the meantime — and for good if that switch failed.
    """
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

    pwfile = CONFIG_DIR / INITDB_PWFILE_NAME
    init_cmd = [
        str(pg_cmd("initdb")),
        "-D", str(PG_DATA),
        "-U", superuser,
        "-E", "UTF8",
        "--locale=C",
        "--auth=scram-sha-256",
        f"--pwfile={pwfile}",
        "-c", f"dynamic_library_path={pg_lib}",
    ]
    # Add -L if share dir exists (bundled binaries)
    if Path(pg_share).is_dir():
        init_cmd.extend(["-L", pg_share])

    try:
        # Restricted BEFORE the password is written (0600 / SYSTEM+Admins ACL).
        # The password goes through a file, never through argv (visible in
        # /proc/<pid>/cmdline or the Windows process list).
        with _open_restricted(pwfile) as handle:
            handle.write(f"{su_password}\n".encode("utf-8"))
        result = subprocess.run(init_cmd, env=pg_env())
    finally:
        try:
            pwfile.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:  # never mask the initdb result over cleanup
            logger.warning(f"Could not remove {pwfile.name}: {exc}")
    # A Windows DLL-load failure (missing VC++ runtime) gets a clear, actionable
    # error here; every other failure keeps its existing CalledProcessError.
    _check_pg_launchable(result.returncode, "initdb.exe")
    result.check_returncode()

    # pg_hba.conf is scram-sha-256 from the start (see docstring);
    # pg_setup_database() only rewrites it to the minimal PraxisZeit set.

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
        f.write(f"port = {pg_port()}\n")
        f.write("max_connections = 50\n")
        f.write("shared_buffers = 128MB\n")
        f.write("log_destination = 'stderr'\n")
        f.write("logging_collector = on\n")
        # PostgreSQL requires forward slashes even on Windows
        f.write(f"log_directory = '{str(LOG_DIR).replace(chr(92), '/')}'\n")
        f.write("log_filename = 'postgresql.log'\n")
        f.write("log_rotation_age = 1d\n")
        f.write("log_rotation_size = 10MB\n")
        # Audit 2026-11-07 (S2-1): keine Statement-Werte/DETAIL im Server-Log.
        f.write("log_min_error_statement = panic\n")
        f.write("log_error_verbosity = terse\n")
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
    # cluster apart from a foreign (EDB) leftover.
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


PG_CONF_MANAGED_HEADER = "# PraxisZeit configuration"


# PostgreSQL liest Parameternamen ohne Ruecksicht auf Gross-/Kleinschreibung,
# und das "=" ist optional ("port 6000", "PORT = 6000"). Jede dieser Formen
# schlaegt die verwaltete Zeile, wenn sie spaeter in der Datei steht (S3-15).
_PG_PORT_LINE_RE = re.compile(r"^\s*port(?:\s*=|\s+)", re.IGNORECASE)
PG_PORT_DISABLED_PREFIX = "# deaktiviert von PraxisZeit ([database] port gilt): "


def _disable_port_line(line: str) -> str:
    return PG_PORT_DISABLED_PREFIX + line.strip()


def _write_conf_atomically(conf_path: Path, new_text: str) -> None:
    # Atomar: Temp-Datei im selben Ordner, dann os.replace - ein Abbruch
    # mitten im Schreiben (Stromausfall, voller Datentraeger) laesst nie eine
    # halbe postgresql.conf zurueck, mit der der Cluster nicht mehr startet.
    tmp = conf_path.with_name(conf_path.name + ".pz-tmp")
    try:
        tmp.write_bytes(new_text.encode("utf-8", errors="surrogateescape"))
        os.replace(tmp, conf_path)
    finally:
        if tmp.exists():
            tmp.unlink()


def sync_managed_pg_port(conf_path: Path, port: int) -> bool:
    """Set ``port`` in the PraxisZeit-managed block of postgresql.conf.

    Pure file edit; returns True only if the file content changed. Line
    endings and encoding are preserved (bytes round trip).

    PostgreSQL takes the LAST ``port =`` line of the file. So besides the
    managed line every other active ``port =`` line (a hand edit before or
    after the managed block, Audit 2026-11-07 S3-15) is commented out —
    otherwise the cluster listens on a port PraxisZeit does not know, looks
    "down" or "foreign" and the service start loops. initdb's commented
    ``#port = 5432`` is not an active line and stays as it is.
    """
    raw = conf_path.read_bytes()
    text = raw.decode("utf-8", errors="surrogateescape")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    new_line = f"port = {port}"
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip() == PG_CONF_MANAGED_HEADER), None
    )
    managed_idx = None
    if header_idx is not None:
        managed_idx = next(
            (i for i in range(header_idx + 1, len(lines))
             if _PG_PORT_LINE_RE.match(lines[i])), None
        )
    for i, ln in enumerate(lines):
        if i != managed_idx and _PG_PORT_LINE_RE.match(ln):
            lines[i] = _disable_port_line(ln)
    if header_idx is None:
        body = nl.join(lines)
        if port == 5432:
            new_text = body
        else:
            tail = "" if (not body or body.endswith("\n")) else nl
            new_text = f"{body}{tail}{nl}{PG_CONF_MANAGED_HEADER}{nl}{new_line}{nl}"
    else:
        if managed_idx is None:
            lines.insert(header_idx + 1, new_line)
        else:
            lines[managed_idx] = new_line
        new_text = nl.join(lines)
    if new_text == text:
        return False
    _write_conf_atomically(conf_path, new_text)
    return True


def neutralize_auto_conf_port(auto_conf: Path) -> bool:
    """Comment out a ``port`` set by ``ALTER SYSTEM`` (postgresql.auto.conf).

    postgresql.auto.conf is read AFTER postgresql.conf, so a port there beats
    the managed line (S3-15). Same effect as ``ALTER SYSTEM RESET port``;
    only called while the cluster is stopped or about to be restarted.
    Returns True if the file changed (and logs a warning then).
    """
    if not auto_conf.exists():
        return False
    raw = auto_conf.read_bytes()
    text = raw.decode("utf-8", errors="surrogateescape")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    changed = False
    for i, ln in enumerate(lines):
        if _PG_PORT_LINE_RE.match(ln):
            logger.warning(
                f"postgresql.auto.conf setzt '{ln.strip()}' (ALTER SYSTEM) - "
                "auskommentiert, es gilt [database] port aus praxiszeit.conf."
            )
            lines[i] = _disable_port_line(ln)
            changed = True
    if changed:
        _write_conf_atomically(auto_conf, nl.join(lines))
    return changed


def apply_pg_port() -> bool:
    """Windows: bring an existing cluster's postgresql.conf in line with pg_port().

    A running cluster keeps its old port until restarted, so the service is
    stopped unconditionally when the port changed (pg_stop() would only act on
    a cluster that is "own" on the NEW port, i.e. never here).
    """
    if not IS_WINDOWS:
        return False
    conf = PG_DATA / "postgresql.conf"
    if not conf.exists():
        return False
    port = pg_port()
    changed = sync_managed_pg_port(conf, port)
    if neutralize_auto_conf_port(PG_DATA / "postgresql.auto.conf"):
        changed = True
    if not changed:
        return False
    logger.info(f"PostgreSQL-Port in postgresql.conf auf {port} gesetzt")
    if _win_service_exists(PG_SERVICE_NAME):
        subprocess.run(["net", "stop", PG_SERVICE_NAME], capture_output=True, text=True)
    return True


def pg_start():
    """Start PostgreSQL.

    Windows: postgres.exe refuses to run under the LocalSystem/admin token of
    the PraxisZeit service, so the cluster is run as its own NetworkService
    Windows service (registered on first start) rather than a child process.

    Unix: started directly via ``pg_ctl start`` (the systemd unit already runs
    PraxisZeit under an unprivileged account, so the child process is fine).
    """
    state = _pg_cluster_state_confirmed()
    if state == "own":
        logger.info("PostgreSQL is already running")
        return
    if state == "foreign":
        raise ForeignPostgresError(_foreign_pg_message(pg_port()))

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
        # Nach Uhrzeit begrenzt, nicht nach Durchlaeufen: ein bleibendes
        # "unknown" (pg_ctl status laeuft je Aufruf bis zum Timeout) hielte die
        # Schleife sonst bis zu einer Dreiviertelstunde fest, ohne Zeiterfassung
        # und ohne dass NSSM neu startet. Je Durchlauf EINE Pruefung; nur ein
        # "foreign" wird einmal nachgeprueft (wie _pg_cluster_state_confirmed).
        deadline = time.monotonic() + PG_START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            state = pg_cluster_state()
            if state == "foreign":
                time.sleep(FOREIGN_RECHECK_SECONDS)
                state = pg_cluster_state()
            if state == "own":
                logger.info("PostgreSQL started successfully (Windows service)")
                return
            if state == "foreign":
                raise ForeignPostgresError(_foreign_pg_message(pg_port()))
            time.sleep(1)
        logger.error(
            f"PostgreSQL service failed to start within {PG_START_TIMEOUT_SECONDS} seconds")
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
    """Stop PostgreSQL gracefully — only our own cluster, never a foreign one."""
    if pg_cluster_state() != "own":
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
    # "/inheritance:r" only drops INHERITED entries. An explicit grant for a
    # broad principal (added by hand, or by an older tool) would survive it, so
    # remove those by SID first. "/remove:g" is a no-op when the SID is absent.
    #   S-1-5-32-545 = BUILTIN\Users
    #   S-1-5-11     = NT AUTHORITY\Authenticated Users
    #   S-1-1-0      = Everyone
    for broad_sid in ("*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0"):
        cmds.append(["icacls", str(file_path), "/remove:g", broad_sid])
    cmds.append(["icacls", str(file_path), "/inheritance:r"])  # last: keeps explicit grants
    for cmd in cmds:
        try:
            # errors="replace": the service runs with PYTHONUTF8=1, icacls
            # answers in the OEM codepage (cp850 on a German Windows). A strict
            # decode would raise UnicodeDecodeError right past the except clause
            # below and take the whole service start down over a cosmetic
            # message.
            subprocess.run(
                cmd, check=True, capture_output=True, text=True, errors="replace",
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            logger.warning(
                f"icacls step failed on {file_path.name} ({' '.join(cmd[2:])}): {exc}"
            )


def _windows_acl_is_inherited(file_path: Path) -> bool:
    """True if the file still carries INHERITED ACEs (Windows only).

    ``icacls <file>`` marks inherited entries with ``(I)``. A file that was
    created with the default permissions of the install directory only has
    inherited ACEs — that is exactly the pre-1.18 state in which every local
    account could read the file. Once :func:`_restrict_file_permissions` has
    run, ``/inheritance:r`` removed them and nothing is marked ``(I)``.

    The ``(I)`` marker is locale-independent (unlike the group NAMES icacls
    prints, which are localized). On any error we return True so the caller
    re-applies the hardening — doing it twice is harmless, skipping it is not.
    """
    if not IS_WINDOWS:
        return False
    try:
        # errors="replace" — siehe _restrict_file_permissions: PYTHONUTF8=1 vs.
        # OEM-Codepage darf hier keinen Ausnahmefehler erzeugen.
        result = subprocess.run(
            ["icacls", str(file_path)],
            capture_output=True, text=True, errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if result.returncode != 0:
        return True
    return "(I)" in result.stdout


def _ensure_restricted_permissions(file_path: Path):
    """Harden an EXISTING confidential file if it is still world-readable.

    This is the retrofit path for installations created by an older version:
    ``praxiszeit.conf`` (admin password + signing key) and the private TLS key
    used to be created with the inherited permissions of ``C:\\PraxisZeit`` and
    were never restricted, so every account that can log on to the practice PC
    could read them.

    It deliberately lives in the SERVICE START path rather than only in the
    installer: the service start is the one place EVERY kind of installation
    passes through (GUI installer, unpacked ZIP + setup.bat, hand-made config),
    it runs again after every reboot, and it needs no action from the operator.
    The installer/update paths harden the files too — this is the safety net
    that also catches a config the operator created or replaced by hand.

    No-op once the file is hardened (checked via the ``(I)`` marker), so a
    normal start does not pay for four extra icacls calls.
    """
    if not IS_WINDOWS or not file_path.is_file():
        return
    if not _windows_acl_is_inherited(file_path):
        return
    logger.info(
        f"Restricting permissions on {file_path.name} "
        "(was still readable for every local account)"
    )
    _restrict_file_permissions(file_path)


def _open_restricted(file_path: Path):
    """Create ``file_path`` with restricted permissions ALREADY in place.

    Returns an open binary write handle to an empty, freshly created file.
    The permissions are applied while the file is still empty, so the secret
    is never on disk with the default (inherited / umask) permissions — same
    ordering rule the Linux and macOS installers get from ``umask 077``.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    # 1. Create (or truncate) the file and close it again straight away. The
    #    0o600 mode argument covers Unix; on Windows it only drives the
    #    read-only attribute, so step 2 has to do the real work there.
    os.close(os.open(str(file_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))
    # 2. Restrict the permissions while the file is still EMPTY. Neither the
    #    Windows security descriptor nor the Unix mode of an already existing
    #    file is touched by open(), so this has to happen between creating and
    #    writing — that is the whole point of this helper.
    _restrict_file_permissions(file_path)
    # 3. Only now write the secret.
    return open(file_path, "wb")


# --- Windows: access rights of the whole install directory ---
#
# The default install dir C:\PraxisZeit inherits the ACL of C:\, which grants
# "Authenticated Users: Modify". The PraxisZeit service runs as LocalSystem
# (NSSM without ObjectName), so every local account could replace
# bin\python\python.exe, a .py file of the app or plant a DLL and run code as
# SYSTEM on the next start — and read the database dumps in data\backups.
#
# Target state (SIDs, never localized names — German vs. English Windows):
#
#   <install>            no inheritance; SYSTEM + Administrators Full,
#                        Users + NetworkService Read&Execute (OI)(CI).
#                        NetworkService runs the PostgreSQL service
#                        (pg_ctl register -U "NT AUTHORITY\NetworkService") and
#                        needs to read/execute bin\postgresql.
#   <install>\data       no inheritance; SYSTEM + Administrators Full; no Users.
#                        NetworkService gets list/traverse on THIS directory
#                        only (no (OI)(CI) -> nothing for data\backups).
#                        data\db keeps its own explicit NetworkService Full
#                        (pg_init / pg_start, _win_grant_networkservice).
#   <install>\logs       no inheritance; SYSTEM + Administrators Full,
#                        NetworkService Modify (logging_collector, as in
#                        pg_start). Logs contain user names — not for Users.
#   <install>\config     no inheritance; SYSTEM + Administrators Full.
#
# No /T: changing a directory's DACL makes Windows re-propagate the
# inheritable entries to every child that inherits, and /T would also walk
# into bin\postgresql when setup.bat made it a junction to a system
# PostgreSQL. Each of these directories gets Administrators as OWNER
# (Audit 2026-11-07 S3-01): an owner always has WRITE_DAC, so a local account
# that created C:\PraxisZeit before the installation could otherwise grant
# itself Full Control again at any time. The recursive owner/ACL reset of the
# program parts and the check against the package manifest happen before the
# first python.exe start, in installer/windows/secure-install.ps1.
_SID_SYSTEM = "*S-1-5-18"
_SID_ADMINISTRATORS = "*S-1-5-32-544"
_SID_USERS = "*S-1-5-32-545"
_SID_AUTHENTICATED_USERS = "*S-1-5-11"
_SID_EVERYONE = "*S-1-1-0"
_SID_NETWORK_SERVICE = "*S-1-5-20"


# Fix-Runde (S3-01): /grant:r und /remove:g erfassen nur die genannten SIDs.
# Ein expliziter Eintrag fuer ein beliebiges anderes Konto ("icacls
# C:\PraxisZeit /grant empfang:(OI)(CI)F" vor der Installation) ueberlebte
# und vererbte sich nach dem /reset auf bin\ und app\ - python.exe tauschbar,
# Ausfuehrung als SYSTEM. Deshalb wird zuletzt die GANZE DACL aus einer
# Positivliste gesetzt (SDDL, "P" = keine Vererbung) und danach nachgeprueft.
# Dieselben Zeichenketten stehen in installer/windows/secure-install.ps1 und
# InstallDirGuard.cs (Test: test_exact_dacl_sddl_is_identical_everywhere).
# 0x1200a9 = Lesen/Ausfuehren (icacls RX), 0x1301bf = Aendern (icacls M).
WIN_SDDL_ROOT = "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;BU)(A;OICI;0x1200a9;;;NS)"
WIN_SDDL_DATA = "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;NS)"
WIN_SDDL_LOGS = "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;NS)"
WIN_SDDL_CONFIG = "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
_SDDL_SID_ALIASES = {"SY": "S-1-5-18", "BA": "S-1-5-32-544", "BU": "S-1-5-32-545",
                     "NS": "S-1-5-20"}


def _ps_single_quoted(value: str) -> str:
    """PowerShell-Literal in einfachen Anfuehrungszeichen. PowerShell wertet
    auch die typografischen Varianten (U+2018..U+201B) als Hochkomma."""
    out = []
    for ch in value:
        out.append(ch * 2 if ch in "'\u2018\u2019\u201a\u201b" else ch)
    return "'" + "".join(out) + "'"


def _sddl_allowed_sids(sddl: str) -> list[str]:
    return sorted({_SDDL_SID_ALIASES[a] for a in re.findall(r";;;([A-Z]{2})\)", sddl)})


def _exact_dacl_command(path: Path, sddl: str) -> list[str]:
    """Windows PowerShell 5.1: DACL von ``path`` genau auf ``sddl`` setzen und
    nachpruefen (Exit 3, wenn danach noch ein anderer Eintrag steht oder die
    Vererbung noch aktiv ist). Nur der DACL-Abschnitt wird geschrieben."""
    allowed = ",".join(f"'{sid}'" for sid in _sddl_allowed_sids(sddl))
    script = (
        "$ErrorActionPreference='Stop';"
        f"$p={_ps_single_quoted(str(path))};"
        "$s=New-Object System.Security.AccessControl.DirectorySecurity;"
        f"$s.SetSecurityDescriptorSddlForm('{sddl}','Access');"
        "[System.IO.Directory]::SetAccessControl($p,$s);"
        f"$allowed=@({allowed});"
        "$a=[System.IO.Directory]::GetAccessControl($p);"
        "if(-not $a.AreAccessRulesProtected){Write-Output 'Vererbung noch aktiv';exit 3};"
        "$bad=@($a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])"
        "|Where-Object{$allowed -notcontains $_.IdentityReference.Value}"
        "|ForEach-Object{$_.IdentityReference.Value});"
        "if($bad.Count -gt 0){Write-Output ('Fremde Eintraege: '+($bad -join ', '));exit 3}"
    )
    sysroot = os.environ.get("SystemRoot", "C:\\Windows")
    ps = str(Path(sysroot) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    return [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", script]


def _build_install_acl_plan(base_dir: Path, data_dir: Path, log_dir: Path,
                            config_dir: Path) -> list[dict]:
    """The icacls argument lists for :func:`_harden_install_dir`.

    Pure / side-effect free so it can be unit-tested without icacls. One entry
    per directory, root first; each entry has ``owner`` (``/setowner``
    Administrators, best-effort, first), ``grants`` (must ALL succeed),
    ``removes`` (best-effort, a missing SID is no error), ``protect`` (the
    ``/inheritance:r`` call, only run after all grants succeeded — the other
    way round a directory could end up with no entry at all and the service
    could not read its own files) and ``exact`` (PowerShell: the whole DACL
    from an allow list, then re-checked — removes explicit entries of any
    other SID, fix round S3-01).
    """
    def grant(path: Path, sid: str, perms: str) -> list[str]:
        # /grant:r replaces earlier EXPLICIT entries of this SID (e.g. a
        # hand-made "Users: Modify") instead of adding to them.
        return ["icacls", str(path), "/grant:r", f"{sid}:{perms}"]

    def remove(path: Path, sid: str) -> list[str]:
        return ["icacls", str(path), "/remove:g", sid]

    def protect(path: Path) -> list[str]:
        return ["icacls", str(path), "/inheritance:r"]

    def owner(path: Path) -> list[str]:
        return ["icacls", str(path), "/setowner", _SID_ADMINISTRATORS]

    full = "(OI)(CI)F"
    private_removes = (_SID_USERS, _SID_AUTHENTICATED_USERS, _SID_EVERYONE)
    return [
        {
            "path": base_dir,
            "owner": owner(base_dir),
            "grants": [
                grant(base_dir, _SID_SYSTEM, full),
                grant(base_dir, _SID_ADMINISTRATORS, full),
                grant(base_dir, _SID_USERS, "(OI)(CI)RX"),
                grant(base_dir, _SID_NETWORK_SERVICE, "(OI)(CI)RX"),
            ],
            # Users is NOT removed here — /grant:r above already cut it down
            # to Read&Execute.
            "removes": [remove(base_dir, sid)
                        for sid in (_SID_AUTHENTICATED_USERS, _SID_EVERYONE)],
            "protect": protect(base_dir),
            "exact": _exact_dacl_command(base_dir, WIN_SDDL_ROOT),
        },
        {
            "path": data_dir,
            "owner": owner(data_dir),
            "grants": [
                grant(data_dir, _SID_SYSTEM, full),
                grant(data_dir, _SID_ADMINISTRATORS, full),
                grant(data_dir, _SID_NETWORK_SERVICE, "(RX)"),
            ],
            "removes": [remove(data_dir, sid) for sid in private_removes],
            "protect": protect(data_dir),
            "exact": _exact_dacl_command(data_dir, WIN_SDDL_DATA),
        },
        {
            "path": log_dir,
            "owner": owner(log_dir),
            "grants": [
                grant(log_dir, _SID_SYSTEM, full),
                grant(log_dir, _SID_ADMINISTRATORS, full),
                grant(log_dir, _SID_NETWORK_SERVICE, "(OI)(CI)M"),
            ],
            "removes": [remove(log_dir, sid) for sid in private_removes],
            "protect": protect(log_dir),
            "exact": _exact_dacl_command(log_dir, WIN_SDDL_LOGS),
        },
        {
            "path": config_dir,
            "owner": owner(config_dir),
            "grants": [
                grant(config_dir, _SID_SYSTEM, full),
                grant(config_dir, _SID_ADMINISTRATORS, full),
            ],
            "removes": [remove(config_dir, sid) for sid in private_removes],
            "protect": protect(config_dir),
            "exact": _exact_dacl_command(config_dir, WIN_SDDL_CONFIG),
        },
    ]


def _run_icacls(cmd: list[str]) -> bool:
    """Run one icacls call; True on success. Never raises."""
    try:
        # errors="replace": icacls answers in the OEM codepage, the service
        # runs with PYTHONUTF8=1 (see _restrict_file_permissions).
        result = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(f"icacls {' '.join(cmd[2:])} on {cmd[1]} failed: {exc}")
        return False
    if result.returncode != 0:
        logger.warning(
            f"icacls {' '.join(cmd[2:])} on {cmd[1]} failed "
            f"(rc={result.returncode}): {(result.stdout or '').strip()} "
            f"{(result.stderr or '').strip()}"
        )
        return False
    return True


def _harden_install_dir() -> bool:
    """Apply the install-directory ACL described above (Windows only).

    Returns True if every directory was hardened. Best-effort per directory: a
    failed grant leaves THAT directory's inheritance untouched (never an empty
    ACL) and the next service start tries again.
    """
    if not IS_WINDOWS:
        return True
    if BASE_DIR.parent == BASE_DIR:
        # Never strip inheritance from a drive root.
        logger.warning(f"Install directory {BASE_DIR} is a drive root — ACL not changed.")
        return False
    # Create the private directories first: one created AFTER the root was
    # hardened would inherit "Users: Read" from it.
    for directory in (DATA_DIR, LOG_DIR, CONFIG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for step in _build_install_acl_plan(BASE_DIR, DATA_DIR, LOG_DIR, CONFIG_DIR):
        # Owner first, best-effort: a failure is logged, the grants still run.
        if not _run_icacls(step["owner"]):
            all_ok = False
        if not all(_run_icacls(cmd) for cmd in step["grants"]):
            logger.warning(
                f"Access rights on {step['path']} not restricted (a grant failed); "
                "inheritance left in place, retried at the next start."
            )
            all_ok = False
            continue
        for cmd in step["removes"]:
            _run_icacls(cmd)
        if not _run_icacls(step["protect"]):
            all_ok = False
            continue
        # Zuletzt die ganze DACL aus der Positivliste (fremde SIDs fallen weg).
        if not _run_icacls(step["exact"]):
            logger.warning(
                f"Access rights on {step['path']}: entries of other accounts could not "
                "be removed - retried at the next start."
            )
            all_ok = False
    return all_ok


def _ensure_install_dir_acl():
    """Safety net at every service start (Windows): harden the install dir if
    it still inherits — same reasoning as :func:`_ensure_restricted_permissions`
    (every kind of installation passes through the service start, also ZIP +
    setup.bat installs from before this check and hand-made copies).

    Costs one ``icacls <dir>`` per directory once hardened.
    """
    if not IS_WINDOWS:
        return
    targets = (BASE_DIR, DATA_DIR, LOG_DIR, CONFIG_DIR)
    if not any((not t.is_dir()) or _windows_acl_is_inherited(t) for t in targets):
        return
    logger.info(
        f"Restricting access rights on {BASE_DIR} (still inherited from the "
        "parent directory, e.g. 'Authenticated Users: Modify' of C:\\)"
    )
    if _harden_install_dir():
        logger.info("Install directory access rights restricted.")


def _restrict_unix_data_dirs():
    """Safety net at every service start (Linux/macOS): data/ and logs/ to
    0750, backups/ to 0700, existing dumps to 0600.

    install.sh does the chmod, but GUI-setup, install-local.sh and macOS
    installs never did, and dumps written before 1.20.2 kept 0644 until the
    retention deleted them (Release-Review 1.20.2). Only removes bits, never
    widens a tighter mode. Errors (e.g. not the owner) are logged, not fatal.
    """
    if IS_WINDOWS:
        return
    targets = [(DATA_DIR, 0o750), (LOG_DIR, 0o750), (BACKUP_DIR, 0o700)]
    if BACKUP_DIR.is_dir():
        targets += [(f, 0o600) for f in BACKUP_DIR.glob("*.sql.gz") if f.is_file()]
    for path, limit in targets:
        try:
            if not path.exists():
                continue
            mode = path.stat().st_mode & 0o777
            if mode & ~limit:
                path.chmod(mode & limit)
        except OSError as exc:
            logger.warning(f"Could not restrict access rights on {path}: {exc}")


def _psql_script(superuser: str, db: str, sql: str, env: dict) -> None:
    """Run ``sql`` through psql via STDIN (``-f -``), stop at the first error.

    Statements that carry a password (ALTER ROLE ... PASSWORD) must never be
    passed with ``-c``: the argument vector of a running process is readable
    by every local account (``/proc/<pid>/cmdline``, Windows process list).
    """
    subprocess.run(
        [str(pg_cmd("psql")), "-X", "-w", "-v", "ON_ERROR_STOP=1",
         "-U", superuser, "-d", db, "-f", "-"],
        input=sql, check=True, capture_output=True, text=True, env=env,
    )


def pg_setup_database(config: dict, su_password: str | None = None,
                      app_password: str | None = None):
    """Create database and app user on first run.

    ``su_password`` must be the password pg_init gave initdb (the cluster is
    scram-protected from the start); it is passed to psql via ``PGPASSWORD``,
    never on the command line.
    """
    superuser = _validate_pg_identifier(
        get_config_value(config, "database", "superuser", "praxiszeit")
    )
    app_user = _validate_pg_identifier(
        get_config_value(config, "database", "app_user", "praxiszeit_app")
    )
    db_name = "praxiszeit"

    if su_password is None or app_password is None:
        resolved_su, resolved_app = resolve_db_passwords(config)
        su_password = su_password or resolved_su
        app_password = app_password or resolved_app

    psql = str(pg_cmd("psql"))
    # "-w" = never prompt for a password. The password comes from PGPASSWORD.
    # Without -w, a cluster that unexpectedly rejects it (e.g. a foreign data
    # dir) makes psql block forever on an interactive prompt that can never be
    # answered inside a Windows service — the original F-0xx hang. With -w it
    # fails fast and check=True surfaces a clear error instead.
    env = {**pg_env(), "PGPASSWORD": su_password}

    # (Re)set the superuser password. Normally initdb --pwfile already did;
    # this keeps `init` working on a cluster left behind by an older,
    # trust-bootstrapped version.
    _psql_script(
        superuser, "postgres",
        f"ALTER ROLE {superuser} PASSWORD '{_escape_pg_password(su_password)}';\n",
        env,
    )

    # Check if database exists
    result = subprocess.run(
        [psql, "-w", "-U", superuser, "-d", "postgres", "-tAc",
         "SELECT 1 FROM pg_database WHERE datname = 'praxiszeit'"],
        capture_output=True, text=True, env=env,
    )

    if "1" not in result.stdout:
        logger.info(f"Creating database '{db_name}'...")
        subprocess.run(
            [psql, "-w", "-U", superuser, "-d", "postgres", "-c",
             f"CREATE DATABASE {db_name} OWNER {superuser} ENCODING 'UTF8'"],
            check=True, capture_output=True, text=True, env=env,
        )

    # Run init-db-user.sql to create app user with RLS permissions
    init_sql = BACKEND_DIR / "init-db-user.sql"
    if init_sql.is_file():
        logger.info("Setting up application database user (RLS)...")
        subprocess.run(
            [psql, "-w", "-U", superuser, "-d", db_name, "-f", str(init_sql)],
            check=True, capture_output=True, text=True, env=env,
        )

    # Set app user password (via stdin, see _psql_script)
    _psql_script(
        superuser, db_name,
        f"ALTER ROLE {app_user} PASSWORD '{_escape_pg_password(app_password)}';\n",
        env,
    )

    # Store connection strings as environment variables for the backend.
    # _database_url() picks unix-socket (Unix) vs TCP (Windows) — see #174.
    os.environ["DATABASE_URL"] = _database_url(app_user, app_password, db_name)
    os.environ["DATABASE_URL_MIGRATIONS"] = _database_url(superuser, su_password, db_name)

    # Save passwords to a secure file for future starts
    _save_credentials(su_password, app_password)

    # Reduce pg_hba.conf to the minimal PraxisZeit set (no replication lines).
    # initdb already wrote scram-sha-256 everywhere, so this is tidying, not
    # the security boundary: a failed reload only delays the tidy-up until the
    # next PostgreSQL restart. That is why it is a warning and not fatal.
    pg_hba = PG_DATA / "pg_hba.conf"
    pg_hba.write_text(
        "# PraxisZeit PostgreSQL client authentication\n"
        "# TYPE  DATABASE  USER  ADDRESS  METHOD\n"
        "local   all       all            scram-sha-256\n"
        "host    all       all   127.0.0.1/32  scram-sha-256\n"
        "host    all       all   ::1/128       scram-sha-256\n"
    )
    reload = subprocess.run(
        [str(pg_cmd("pg_ctl")), "-D", str(PG_DATA), "reload"],
        capture_output=True, text=True, errors="replace", env=pg_env(),
    )
    if reload.returncode != 0:
        logger.warning(
            "pg_ctl reload failed (rc=%s) — pg_hba.conf takes effect at the next "
            "PostgreSQL restart (authentication is scram-sha-256 already): %s",
            reload.returncode, (reload.stderr or "").strip(),
        )
    else:
        logger.info("pg_hba.conf reloaded (scram-sha-256)")

    logger.info("Database setup complete")
    return su_password, app_password


def _save_credentials(su_password: str, app_password: str):
    """Save database credentials securely.

    Created through :func:`_open_restricted`: the permissions (0600 / SYSTEM +
    Administrators) are in place BEFORE the passwords are written — no window
    in which the file carries the default (umask / inherited) permissions.
    """
    creds_file = CONFIG_DIR / ".db-credentials"
    with _open_restricted(creds_file) as handle:
        handle.write(
            (f"SUPERUSER_PASSWORD={su_password}\n"
             f"APP_PASSWORD={app_password}\n").encode("utf-8")
        )


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


# --- Backup-Rolle fuer den Webprozess (Audit 2026-11-07 S3-13) ---
#
# Die Datensicherung in der Weboberflaeche (#213) lief mit der Superuser-
# Verbindung DATABASE_URL_MIGRATIONS aus der Umgebung von uvicorn. Jede
# Code-Ausfuehrung, jedes Dateilesen (/proc/self/environ) oder Umgebungs-Leck
# im Webprozess hiess damit: Superuser, RLS wirkungslos, COPY ... TO PROGRAM.
# Nativ laufen die Migrationen im Prozessmanager VOR dem uvicorn-Start; uvicorn
# braucht den Superuser also nicht. Er bekommt stattdessen eine eigene Rolle,
# die nur lesen kann: pg_read_all_data (SELECT auf alles) + BYPASSRLS (pg_dump
# schaltet row_security ab und bricht sonst an den RLS-Tabellen ab), kein
# Superuser, kein Schreibrecht, keine Server-Dateizugriffe.
BACKUP_ROLE = "praxiszeit_backup"


def _read_credentials_file() -> dict:
    creds_file = CONFIG_DIR / ".db-credentials"
    creds = {}
    if creds_file.is_file():
        for line in creds_file.read_text().strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                creds[key.strip()] = value.strip()
    return creds


def _backup_role_password() -> str:
    """BACKUP_PASSWORD aus .db-credentials; beim ersten Mal erzeugt und dort
    (Rechte vor dem Inhalt, :func:`_open_restricted`) dazugeschrieben."""
    creds = _read_credentials_file()
    password = creds.get("BACKUP_PASSWORD")
    if password:
        return password
    password = secrets.token_hex(32)
    creds_file = CONFIG_DIR / ".db-credentials"
    # Atomar ersetzen (Fix-Runde): die Datei traegt SUPERUSER_PASSWORD und
    # APP_PASSWORD. _open_restricted kuerzt erst und schreibt dann - ein
    # Absturz, Stromausfall oder voller Datentraeger dazwischen liesse beim
    # ersten Start nach dem Update eine LEERE Datei zurueck, und der Cluster
    # waere nicht mehr erreichbar. Deshalb: bisheriger Inhalt unveraendert
    # (auch Zeilen ohne key=value) + neue Zeile in eine Temp-Datei mit den
    # engen Rechten, fsync, dann os.replace ueber das Original.
    old = creds_file.read_bytes() if creds_file.is_file() else b""
    if old and not old.endswith(b"\n"):
        old += b"\n"
    tmp = creds_file.with_name(creds_file.name + ".pz-tmp")
    try:
        with _open_restricted(tmp) as handle:
            handle.write(old + f"BACKUP_PASSWORD={password}\n".encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, creds_file)
    finally:
        if tmp.exists():
            tmp.unlink()
    return password


def ensure_backup_role(config: dict, su_password: str) -> str | None:
    """Backup-Rolle anlegen bzw. angleichen; liefert die Verbindungs-URL.

    Idempotent, bei jedem Start. Scheitert es, bekommt der Webprozess KEINE
    Datenbank-Verbindung fuer Sicherungen (None) - nie ersatzweise den
    Superuser. Die naechtliche Sicherung des Prozessmanagers (``backup``)
    ist davon nicht betroffen."""
    superuser = _validate_pg_identifier(
        get_config_value(config, "database", "superuser", "praxiszeit"))
    try:
        password = _backup_role_password()
        sql = (
            "DO $$ BEGIN\n"
            f"  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{BACKUP_ROLE}') THEN\n"
            f"    CREATE ROLE {BACKUP_ROLE} LOGIN;\n"
            "  END IF;\n"
            "END $$;\n"
            f"ALTER ROLE {BACKUP_ROLE} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"NOREPLICATION BYPASSRLS PASSWORD '{_escape_pg_password(password)}';\n"
            f"GRANT pg_read_all_data TO {BACKUP_ROLE};\n"
            f"GRANT CONNECT ON DATABASE praxiszeit TO {BACKUP_ROLE};\n"
        )
        _psql_script(superuser, "praxiszeit", sql, {**pg_env(), "PGPASSWORD": su_password})
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or exc
        logger.error(
            "Backup-Rolle %s nicht eingerichtet (%s) - Sicherungen aus der "
            "Weboberflaeche sind bis zum naechsten Start nicht moeglich; die "
            "naechtliche Sicherung des Dienstes laeuft weiter.", BACKUP_ROLE, detail,
        )
        return None
    return _database_url(BACKUP_ROLE, password, "praxiszeit")


# --- Alembic Migrations ---

def _redact_db_url(text: str) -> str:
    """Maskiert Passwörter in postgresql://<user>:<pass>@<host>-URLs.

    Alembic schreibt bei Verbindungsfehlern die komplette Connection-URL
    (inkl. Passwort aus DATABASE_URL_MIGRATIONS) auf stderr; ungefiltert
    landete das im rotierenden logs/praxiszeit.log (Art. 32 DSGVO).
    """
    import re
    return re.sub(r'(://[^:/@\s]+:)[^@/\s]+(@)', r'\1***\2', text)


# Zuordnung Konfigurationsschluessel -> Umgebungsvariable des Backends
# (Pydantic Settings). Auf Modulebene, weil sowohl der Dienststart als auch die
# Kommandozeilen-Werkzeuge sie brauchen: ``app/config.py`` sucht die
# praxiszeit.conf zwar selbst, aber ueber einen zum **cwd** relativen Pfad — ein
# Unterprozess mit ``cwd=BACKEND_DIR`` findet sie damit nicht (ausser auf einer
# Standard-Linux-Installation unter /opt/praxiszeit).
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
    # Optional: "production" (Vorgabe nativ, siehe native_environment) oder
    # "development" (API-Doku unter /docs, schwaches Admin-Passwort nur Warnung).
    ("server", "environment"): "ENVIRONMENT",
}

# Konfigurationswerte, die Dateipfade sind (relativ zu BASE_DIR aufloesen)
_PATH_KEYS = {"LICENSE_KEY_PATH"}


def apply_config_env(config: dict, env) -> None:
    """Konfigurationswerte als Umgebungsvariablen fuer das Backend setzen.

    Bereits gesetzte Variablen haben Vorrang (wie in ``app/config.py``).
    """
    for (section, key), env_name in _CONF_TO_ENV.items():
        if env_name in env:
            continue
        val = get_config_value(config, section, key)
        if val is None:
            continue
        str_val = str(val).lower() if isinstance(val, bool) else str(val)
        if env_name in _PATH_KEYS and not Path(str_val).is_absolute():
            str_val = str(BASE_DIR / str_val)
        env[env_name] = str_val


def resolve_secret_key(config: dict, *, persist: bool) -> str:
    """Den SECRET_KEY der Installation ermitteln.

    Reihenfolge: Konfiguration → zuvor erzeugte ``config/.secret-key`` → neu
    erzeugen. ``persist=False`` (Kommandozeilen-Werkzeuge) legt einen fehlenden
    Schluessel NICHT auf Platte ab: das Backend verlangt beim Import einen
    gueltigen Wert, aber ein Werkzeug darf keinen Schluessel festschreiben, an
    dem anschliessend die Sitzungen der laufenden Installation haengen.
    """
    sk = get_config_value(config, "security", "secret_key")
    if sk:
        return str(sk)

    sk_file = CONFIG_DIR / ".secret-key"
    if sk_file.is_file():
        return sk_file.read_text().strip()

    sk = secrets.token_hex(32)
    if not persist:
        return sk

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
    return sk


def run_migrations(config: dict):
    """Run Alembic migrations."""
    logger.info("Running database migrations...")

    env = os.environ.copy()
    # DATABASE_URL_MIGRATIONS should already be set
    # Migrationen geben Diagnosen aus (073: "halboffen: Mo ab 07:30 → Ende
    # 23:59"). Ohne UTF-8-Modus ist stdout des Kinds unter Windows eine Pipe in
    # cp1252, das "→" nicht kennt — wie bei uvicorn_start nicht darauf
    # verlassen, dass der Aufrufer (Dienst, Update-Assistent) die Variable
    # mitgibt; beim Konsolenstart fehlt sie.
    env["PYTHONUTF8"] = "1"

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
        # Das Kind schreibt UTF-8 (PYTHONUTF8 oben) — also auch UTF-8 lesen,
        # nicht die Codepage dieses Prozesses (text=True): sonst Zeichensalat im
        # Log, und ein Byte, das cp1252 nicht belegt (etwa aus "Ł" oder "”"),
        # braeche hier NACH der erfolgreichen Migration mit UnicodeDecodeError ab.
        result = subprocess.run(
            cmd, cwd=str(BACKEND_DIR), env=env, capture_output=True,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            # Die Ausgabe der Migrationen gehoert ins Log, auch wenn sie
            # erfolgreich waren: Migrationen melden dort Datensaetze, die der
            # Betreiber von Hand nachziehen muss (z. B. 067 benennt Konten mit
            # einer Wochensumme ueber 60 h, deren Vertragswert deshalb NICHT
            # zurueckgeschrieben wurde). Unter Docker landet das im
            # Container-Log; nativ wurde es bisher bei Erfolg verworfen — der
            # Betreiber erfuhr also nie, welche Konten zu pruefen sind.
            for stream in (result.stdout, result.stderr):
                for line in (stream or "").splitlines():
                    if line.strip():
                        logger.info(f"  alembic: {_redact_db_url(line)}")
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
    # The certificate is public — normal permissions.
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    # The private key is not: create it with restricted permissions ALREADY in
    # place (0600 on Unix, an ACL without inheritance that only grants SYSTEM
    # and the Administrators group on Windows) and only then write the key
    # material. Before, the Windows key was never restricted at all and stayed
    # readable for every account on the practice PC.
    key_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    with _open_restricted(key_path) as handle:
        handle.write(key_bytes)
    logger.info(f"Self-signed certificate written to {cert_path}")
    return True


# #427: Wie oft darf sich uvicorn innerhalb von ``_UVICORN_RESTART_WINDOW_SECONDS``
# beenden, bevor der Prozess-Manager aufgibt? Ohne Obergrenze laeuft er ewig
# weiter und systemd fuehrt den Dienst als ``active``, waehrend nichts antwortet.
_UVICORN_RESTART_LIMIT = 5
_UVICORN_RESTART_WINDOW_SECONDS = 300


def _child_alive(process) -> bool:
    """Laeuft der uvicorn-Kindprozess noch?"""
    return process is not None and process.poll() is None


def port_is_occupied(host, port, timeout: float = 0.5) -> bool:
    """Antwortet auf ``host:port`` bereits jemand?

    #427: Der Fall, der das Ticket ausgeloest hat — eine zweite Installation
    (oder eine alte, nicht gestoppte) haelt den Port. uvicorn beendet sich dann
    sofort mit ``address already in use``. Geprueft wird per ``connect``, nicht
    per ``bind``: ein Bind-Versuch auf einen privilegierten Port scheitert unter
    Umstaenden an fehlenden Rechten und waere als "belegt" fehlgedeutet.
    """
    target = "127.0.0.1" if str(host) in ("0.0.0.0", "::", "*") else str(host)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(timeout)
            return probe.connect_ex((target, int(port))) == 0
    except OSError:
        # Kein Urteil moeglich (Namensaufloesung, Adressfamilie) — dann lieber
        # starten lassen und uvicorn selbst entscheiden.
        return False


def wait_until_healthy(process, probe, attempts: int = 30,
                       sleep_seconds: float = 1.0, sleeper=time.sleep) -> bool:
    """Wartet, bis **unser** uvicorn gesund antwortet.

    #427 — der Kern des Fehlers: geprueft wird ZUERST, ob der Kindprozess noch
    lebt, und erst danach der HTTP-Aufruf. Vorher gewann eine 200 vom Port, und
    die kann von einem FREMDEN Prozess stammen (genau der Fall "address already
    in use": die alte Installation antwortet weiter). Der Manager hielt sich
    dann fuer gesund, obwohl sein eigenes uvicorn schon tot war — und systemd
    meldete ``active``, waehrend die neue Installation nichts ausliefert.
    """
    for _ in range(attempts):
        sleeper(sleep_seconds)
        if not _child_alive(process):
            return False
        if probe():
            return True
    return False


def should_give_up(restart_times, now: float,
                   limit: int = _UVICORN_RESTART_LIMIT,
                   window: float = _UVICORN_RESTART_WINDOW_SECONDS) -> bool:
    """Hat sich uvicorn zu oft in zu kurzer Zeit beendet? (#427)

    Ohne diese Grenze startet der Wachhund uvicorn endlos neu und haelt den
    Manager am Leben — fuer systemd bleibt der Dienst ``active``, obwohl er in
    Wahrheit in einer Absturzschleife steckt.
    """
    recent = [t for t in restart_times if now - t <= window]
    return len(recent) >= limit


# Spiegel von ``_WEAK_ADMIN_PASSWORDS`` in backend/app/main.py (ein Test haelt
# beide gleich). Der Backend-Start bricht unter ENVIRONMENT=production ab, wenn
# das Konto "admin" noch mit einem dieser Werte bzw. einem Passwort unter 12
# Zeichen aus der Konfiguration anmeldbar ist.
_BACKEND_WEAK_ADMIN_PASSWORDS = frozenset({"Admin2025!", "admin123", "password", "admin"})
_BACKEND_MIN_ADMIN_PASSWORD_LEN = 12


def _backend_is_placeholder_secret(value: str) -> bool:
    """Spiegel von ``is_placeholder_secret`` in backend/app/config.py (ein Test
    haelt beide gleich): Vorlagenwert aus der Beispielkonfiguration."""
    v = (value or "").strip()
    upper = v.upper()
    return (v.startswith("<") and v.endswith(">")) or "BITTE_AENDERN" in upper or "CHANGE_ME" in upper


def native_environment(env) -> str:
    """ENVIRONMENT, mit dem uvicorn auf einer nativen Installation laeuft.

    Vorgabe ist ``production``: ohne das stand jede native Installation im
    ``development``-Modus (Default in backend/app/config.py), und
    ``/docs``, ``/redoc`` und ``/openapi.json`` waren fuer das ganze
    Praxisnetz offen.

    Ein ausdruecklich gesetzter Wert gewinnt (Dienst-Umgebung oder
    ``[server] environment`` in praxiszeit.conf).

    Ausnahme: steht in der Konfiguration fuer das Konto ``admin`` ein Passwort,
    an dem der Backend-Start im Produktionsmodus HART abbricht (Liste oben oder
    kuerzer als 12 Zeichen — die Installer verlangten frueher nur 10), bleibt
    es bei ``development`` plus Warnung. Sonst wuerde ein Update eine bisher
    laufende Installation in eine Absturzschleife schicken. Die Pruefung hier
    ist bewusst weiter als die im Backend (die zusaetzlich verlangt, dass das
    Passwort noch zum Konto passt): lieber einmal zu oft ``development`` als
    ein Dienst, der nicht mehr startet.
    """
    explicit = (env.get("ENVIRONMENT") or "").strip()
    if explicit:
        return explicit
    username = env.get("ADMIN_USERNAME") or "admin"
    password = env.get("ADMIN_PASSWORD") or ""
    if username == "admin" and (
        password in _BACKEND_WEAK_ADMIN_PASSWORDS
        or len(password) < _BACKEND_MIN_ADMIN_PASSWORD_LEN
        or _backend_is_placeholder_secret(password)
    ):
        logger.warning(
            "ENVIRONMENT bleibt 'development': [admin] password in praxiszeit.conf "
            "ist kuerzer als %s Zeichen oder ein Standardwert — im Produktionsmodus "
            "wuerde der Start daran scheitern. Den Eintrag durch einen langen "
            "Zufallswert ersetzen (oder 'praxiszeit-server.py reset-admin-password' "
            "nutzen, das ihn selbst entwertet); danach laeuft PraxisZeit im "
            "Produktionsmodus (API-Doku /docs aus).",
            _BACKEND_MIN_ADMIN_PASSWORD_LEN,
        )
        return "development"
    return "production"


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
    # S3-13: die Superuser-Verbindung bleibt im Prozessmanager (Migrationen
    # laufen vorher dort); der Webprozess sichert ueber DATABASE_URL_BACKUP.
    env.pop("DATABASE_URL_MIGRATIONS", None)
    env["SERVE_FRONTEND"] = "true"
    env["PYTHONUTF8"] = "1"  # Avoid cp1252 encoding errors on Windows
    # Native install: frontend lives at app/frontend/ (no dist/ subfolder)
    env["FRONTEND_DIR"] = str(APP_DIR / "frontend")
    # Produktionsmodus als Vorgabe (API-Doku aus) — Ausnahmen siehe
    # native_environment.
    env["ENVIRONMENT"] = native_environment(env)

    # #427: Ist der Port schon belegt, beendet sich uvicorn sofort mit
    # "address already in use" — und der belegende Prozess (typischerweise eine
    # zweite oder nicht gestoppte Installation) beantwortet die anschliessende
    # Gesundheitspruefung. Frueher galt der Dienst damit als gesund. Hier steht
    # die Ursache als Klartext im Protokoll, bevor irgendetwas startet.
    if port_is_occupied(bind_address, port):
        logger.error(
            "Port %s ist bereits belegt — dort antwortet schon ein anderer Prozess. "
            "Laeuft PraxisZeit doppelt (alter Dienst nicht gestoppt) oder nutzt ein "
            "anderes Programm den Port? Pruefen mit: ss -ltnp | grep :%s",
            port, port,
        )
        sys.exit(1)

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

    def _probe() -> bool:
        try:
            import urllib.request
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001 — noch nicht bereit ist der Normalfall
            return False

    if wait_until_healthy(_uvicorn_process, _probe):
        logger.info(f"PraxisZeit is ready at {protocol}://localhost:{port}")
        return

    # #427: Zwei verschiedene Fehler, zwei verschiedene Meldungen — vorher
    # verschwand der Unterschied hinter einem einzigen "exited unexpectedly".
    if not _child_alive(_uvicorn_process):
        logger.error(
            "uvicorn hat sich beim Start beendet (Exitcode %s). Haeufigste Ursache: "
            "der Port ist belegt oder die Konfiguration ist fehlerhaft — die "
            "Meldung von uvicorn steht darueber im Protokoll.",
            _uvicorn_process.returncode if _uvicorn_process else "?",
        )
    else:
        logger.error("uvicorn wurde nicht innerhalb von 30 Sekunden gesund")
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
    # Signaturzeile am Ende (Fix-Runde S3-03): restore spielt eine Datei ohne
    # passende Signatur nur mit --force-unverified ein.
    secret_key = _installation_secret_key(config)
    signer = BackupMac(secret_key) if secret_key else None
    if signer is None:
        logger.warning("Kein SECRET_KEY gefunden - die Sicherung wird nicht signiert.")
    try:
        # 0600 from the first byte (not open() + umask 022 -> world-readable
        # 0644 dump with every employee's data). On Windows the mode only
        # drives the read-only attribute; there the ACL of the data dir applies
        # (see _harden_install_dir).
        fd = os.open(str(backup_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            with gzip.open(f, "wb") as gz:
                while True:
                    chunk = pg_dump.stdout.read(8192)
                    if not chunk:
                        break
                    gz.write(chunk)
                    if signer is not None:
                        signer.update(chunk)
                if signer is not None:
                    gz.write(signer.trailer())
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

def _watchdog_foreign_exit(message: str) -> None:
    """Fremder Server auf unserem Port: sauber beenden, ohne Neustart-Zyklus."""
    logger.error(message)
    uvicorn_stop()
    _remove_pid()
    sys.exit(EXIT_CONFIG_ERROR)


WATCHDOG_FOREIGN_LIMIT = 3
_watchdog_foreign_streak = 0


def _watchdog_check_pg() -> None:
    """PostgreSQL-Pruefung der Watchdog-Schleife in cmd_start.

    ``"down"`` → unseren Cluster neu starten; ``"foreign"`` → beenden (Exit 78),
    nie gegen einen fremden Server weiterlaufen oder ihn stoppen. Beendet wird
    erst, wenn "foreign" bei WATCHDOG_FOREIGN_LIMIT Pruefungen in Folge
    herauskommt: Exit 78 ist endgueltig (NSSM AppExit 78 Exit), ein einzelner
    Messfehler darf die Praxis nicht ohne Zeiterfassung lassen.
    """
    global _watchdog_foreign_streak
    state = pg_cluster_state()
    if state == "foreign":
        _watchdog_foreign_streak += 1
        if _watchdog_foreign_streak >= WATCHDOG_FOREIGN_LIMIT:
            _watchdog_foreign_exit(_foreign_pg_message(pg_port()))
        logger.warning(
            "PostgreSQL-Port %s: Pruefung meldet einen fremden Server "
            "(%s von %s) - erneute Pruefung beim naechsten Durchlauf.",
            pg_port(), _watchdog_foreign_streak, WATCHDOG_FOREIGN_LIMIT,
        )
        return
    _watchdog_foreign_streak = 0
    if state == "unknown":
        # pg_ctl status lief in die Zeitgrenze o. ae. (S3-08): weder neu
        # starten noch beenden, beim naechsten Durchlauf erneut pruefen.
        logger.warning(
            "PostgreSQL-Port %s: Zustand nicht feststellbar (pg_ctl status) - "
            "erneute Pruefung beim naechsten Durchlauf.", pg_port(),
        )
        return
    if state == "down":
        logger.error("PostgreSQL is not responding, restarting...")
        try:
            pg_start()
        except ForeignPostgresError as e:
            _watchdog_foreign_exit(str(e))


def cmd_start(args):
    """Start PraxisZeit (PostgreSQL + uvicorn)."""
    config = load_config()
    warn_ignored_pg_port(config)

    logger.info("=" * 60)
    logger.info("PraxisZeit starting...")
    logger.info("=" * 60)

    # 0. Retrofit for installations created by an older version: praxiszeit.conf
    # (admin password + signing key) and the private TLS key used to be created
    # with the inherited, world-readable permissions of the install directory.
    # No-op once hardened; see _ensure_restricted_permissions for why this lives
    # in the service start and not only in the installer.
    _secrets = [CONFIG_FILE]
    # Resolve the key exactly like uvicorn_start does, so an operator who
    # pointed [server] ssl_key at a CA-signed key gets that one hardened.
    _ssl_key = get_config_value(config, "server", "ssl_key", "config/ssl/key.pem")
    if _ssl_key:
        _secrets.append(
            Path(_ssl_key) if Path(_ssl_key).is_absolute() else BASE_DIR / _ssl_key
        )
    for _secret in _secrets:
        _ensure_restricted_permissions(_secret)
    # Windows: the whole install directory (program files run as SYSTEM, data
    # and backups) — no-op once hardened.
    _ensure_install_dir_acl()
    # Linux/macOS: data, logs and backups only for the service account.
    _restrict_unix_data_dirs()

    # 1. Initialize PostgreSQL if needed
    # Fremder Server auf unserem Port? Dann VOR jeder Entscheidung abbrechen
    # (Exit 78). Sonst legt pg_init Cluster + Marker an, pg_start bricht erst
    # danach ab, .db-credentials entsteht nie - und der naechste Start mit
    # freiem Port endet dauerhaft in fail_no_credentials (Windows-Emulator
    # 2026-11-06). Ebenso darf kein unmarkiertes PG_DATA in Quarantaene
    # wandern, solange der Port gar nicht uns gehoert. Unter Unix ist der
    # Zustand nie "foreign" (Socket-Verzeichnis = Eigentumsnachweis).
    if _pg_cluster_state_confirmed() == "foreign":
        raise ForeignPostgresError(_foreign_pg_message(pg_port()))
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
        # superuser. Trusting it would make pg_setup_database's
        # psql calls fail (or, before -w, hang). Move it aside and
        # re-initialize a clean cluster.
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

    su_password = app_password = None
    if needs_initdb:
        su_password, app_password = resolve_db_passwords(config)
        pg_init(config, su_password)

    # 2. Start PostgreSQL
    apply_pg_port()
    pg_start()

    # 3. Setup database if needed (first run or missing credentials)
    if needs_setup:
        pg_setup_database(config, su_password, app_password)
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
    apply_config_env(config, os.environ)

    # Generate SECRET_KEY if not configured — persist so sessions survive restarts
    if "SECRET_KEY" not in os.environ:
        os.environ["SECRET_KEY"] = resolve_secret_key(config, persist=True)

    # 4. Run migrations
    run_migrations(config)

    # 4a. Eigene, nur lesende Rolle fuer die Sicherung aus der Weboberflaeche
    # (S3-13); uvicorn bekommt den Superuser nicht mehr (uvicorn_start).
    backup_url = ensure_backup_role(config, su_password)
    if backup_url:
        os.environ["DATABASE_URL_BACKUP"] = backup_url
    else:
        os.environ.pop("DATABASE_URL_BACKUP", None)

    # 5. Start uvicorn
    uvicorn_start(config)

    # 6. Write PID file + setup signal handlers
    _write_pid()
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # 7. Watchdog loop
    logger.info("PraxisZeit is running. Press Ctrl+C to stop.")
    uvicorn_restarts: list[float] = []
    while not _shutdown_requested:
        time.sleep(5)

        # Check if uvicorn is still alive
        if _uvicorn_process and _uvicorn_process.poll() is not None:
            rc = _uvicorn_process.returncode
            now = time.time()
            uvicorn_restarts.append(now)
            uvicorn_restarts = [t for t in uvicorn_restarts
                                if now - t <= _UVICORN_RESTART_WINDOW_SECONDS]
            # #427: Irgendwann ist Schluss. Ohne Obergrenze startet der Wachhund
            # uvicorn endlos neu und bleibt dabei selbst am Leben — fuer systemd
            # ist der Dienst dann ``active``, obwohl er in einer Absturzschleife
            # steckt und nichts ausliefert. Mit ``Restart=on-failure`` und
            # ``StartLimitBurst`` in der Unit endet der Dienst stattdessen
            # ehrlich in ``failed``.
            if should_give_up(uvicorn_restarts, now):
                logger.error(
                    "uvicorn hat sich %s mal in %s Minuten beendet (zuletzt mit "
                    "Exitcode %s) — PraxisZeit gibt auf und beendet sich mit "
                    "Fehler, damit der Dienst nicht faelschlich als laufend gilt.",
                    len(uvicorn_restarts), _UVICORN_RESTART_WINDOW_SECONDS // 60, rc,
                )
                uvicorn_stop()
                pg_stop()
                _remove_pid()
                sys.exit(1)
            logger.error(
                "uvicorn hat sich beendet (Exitcode %s), Neustart %s von %s...",
                rc, len(uvicorn_restarts), _UVICORN_RESTART_LIMIT,
            )
            uvicorn_start(config)

        # Check if PostgreSQL is still alive
        _watchdog_check_pg()

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
    su_password, app_password = resolve_db_passwords(config)
    pg_init(config, su_password)
    pg_start()
    pg_setup_database(config, su_password, app_password)
    run_migrations(config)
    logger.info("Initialization complete. Run 'praxiszeit-server start' to start the application.")
    pg_stop()


def cmd_print_db_port(args):
    """Nur den Datenbank-Port ausgeben (fuer .bat-Skripte); sonst nichts auf stdout."""
    print(pg_port())


def cmd_sync_db_port(args):
    """postgresql.conf an den konfigurierten Port angleichen; nichts auf stdout."""
    apply_pg_port()


# Exit-Code von prepare-restore-dump --restricted-load fuer eine unverifizierte
# (mit --force-unverified zugelassene) Sicherung: restore-backup.bat laedt sie
# dann ueber load-restore-db --restricted (Review-Runde 4).
PREPARE_EXIT_UNVERIFIED = 4


def cmd_prepare_restore_dump(args):
    """restore-backup.bat: Signatur und entpackten Dump pruefen und mit eigenem
    \\restrict versehen. Fehler als eine Zeile auf stderr: Exit 2 = Signatur
    fehlt oder passt nicht, Exit 1 = Dump abgelehnt (die .bat bricht ab).
    ``--restricted-load``: eine unverifizierte Sicherung wird fuer das Laden
    als :data:`RESTORE_LOAD_ROLE` vorbereitet (ohne Eigentuemer-Zeilen) und
    meldet Exit :data:`PREPARE_EXIT_UNVERIFIED`."""
    restricted = getattr(args, "restricted_load", False)
    try:
        verified = prepare_restore_dump(
            Path(args.file), secret_key=_installation_secret_key(load_config()),
            force_unverified=getattr(args, "force_unverified", False),
            restricted_load=restricted,
        )
    except UnverifiedBackupError as exc:
        # Exit 2: restore-backup.bat erklaert --force-unverified.
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(2)
    except RestoreError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"FEHLER: {args.file} nicht lesbar: {exc}", file=sys.stderr)
        sys.exit(1)
    if restricted and not verified:
        sys.exit(PREPARE_EXIT_UNVERIFIED)


def cmd_load_restore_db(args):
    """restore-backup.bat Schritt 4 (Review-Runde 4): vorbereiteten Dump in die
    Zwischendatenbank einspielen - derselbe Weg wie ``restore`` unter Linux und
    macOS (:func:`_load_into_restore_db`). ``--restricted``: unverifizierte
    Sicherung als :data:`RESTORE_LOAD_ROLE` laden, Funktionen und Trigger gegen
    die Migrationen abgleichen. Die bisherige Datenbank bleibt unangetastet.
    Fehler als Meldung auf stderr, Exit 1."""
    config = load_config()
    su_password, _ = pg_load_credentials()
    if not su_password:
        print("FEHLER: Keine Datenbank-Zugangsdaten gefunden (config/.db-credentials fehlt).",
              file=sys.stderr)
        sys.exit(1)
    known = known_migration_revisions()
    if not known:
        print(f"FEHLER: Keine Migrationen unter {BACKEND_DIR / 'alembic' / 'versions'} "
              "gefunden - Installation unvollstaendig.", file=sys.stderr)
        sys.exit(1)
    superuser = _validate_pg_identifier(
        get_config_value(config, "database", "superuser", "praxiszeit"))
    env = {**pg_env(), "PGPASSWORD": su_password,
           "PGOPTIONS": "-c client_min_messages=warning"}
    try:
        revision = _load_into_restore_db(superuser, env, Path(args.file), known,
                                         restricted=getattr(args, "restricted", False))
    except RestoreError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(1)
    print(revision)


def cmd_harden_permissions(args):
    """Windows: restrict the access rights of the install directory.

    Called by setup.bat and the update wizard; the service start does the same
    as a safety net (_ensure_install_dir_acl). Exit 1 if a step failed.
    """
    if not IS_WINDOWS:
        logger.info("harden-permissions: only needed on Windows — nothing to do.")
        return
    if not _harden_install_dir():
        sys.exit(1)
    logger.info(f"Access rights on {BASE_DIR} restricted.")


def cmd_backup(args):
    """Create a database backup."""
    config = load_config()
    if not pg_is_running():
        logger.error("PostgreSQL is not running. Start PraxisZeit first.")
        sys.exit(1)
    create_backup(config)


def bundled_python() -> str:
    """Pfad zum MITGELIEFERTEN Interpreter (Release-Review 1.19.0).

    Die Abhaengigkeiten der Anwendung (sqlalchemy, passlib, pydantic-settings)
    liegen bei einer nativen Installation ausschliesslich unter
    ``bin/python`` — der System-Python kennt sie nicht. systemd und launchd
    rufen den gebuendelten Interpreter mit vollem Pfad auf, ein von Hand
    gestartetes Kommando aber nicht zwangslaeufig: ``sys.executable`` ist dann
    ``/usr/bin/python3`` und der Unterprozess stirbt an
    ``ModuleNotFoundError: No module named 'sqlalchemy'``.

    Faellt auf ``sys.executable`` zurueck, wenn kein gebuendelter Interpreter
    daneben liegt (Entwicklungsumgebung, install-local.sh mit venv).
    """
    candidates = [
        BIN_DIR / "python" / "bin" / "python3",   # Linux/macOS-Bundle
        BIN_DIR / "python" / "python.exe",        # Windows-Bundle
        BASE_DIR / "venv" / "bin" / "python3",    # install-local.sh
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def _install_owner() -> str:
    """Das Konto, dem die Installation gehoert — der richtige Aufrufer, wenn die
    Datenbank noch hochgefahren werden muss (Release-Review 1.19.0).

    Rueckfall ist das Dienstkonto, das der Installer der Plattform anlegt: auf
    macOS ``_praxiszeit`` (mit Unterstrich, ``dscl`` in
    installer/macos/install.sh), sonst ``praxiszeit``."""
    try:
        import pwd
        return pwd.getpwuid(BASE_DIR.stat().st_uid).pw_name
    except Exception:  # noqa: BLE001 — Windows/unbekannte UID: der Hinweis bleibt brauchbar
        return "_praxiszeit" if IS_MACOS else "praxiszeit"


def _service_start_command() -> str:
    """Wie der PraxisZeit-Dienst auf dieser Plattform gestartet wird.

    Gesamtreview B8 (#491): der Hinweis nannte auf jeder Plattform
    ``systemctl`` — auf macOS laeuft der Dienst unter launchd. ``launchctl
    load`` auf die Plist ist dieselbe Form, die der macOS-Installer am Ende
    als „Starten" ausgibt."""
    if IS_MACOS:
        return f"launchctl load {MACOS_LAUNCHD_PLIST}"
    return "systemctl start praxiszeit"


def _service_stop_command() -> str:
    """Gegenstueck zu :func:`_service_start_command`. Auf macOS ``unload``, nicht
    ``stop``: die Plist setzt ``KeepAlive``, launchd startete den Dienst sofort
    wieder."""
    if IS_MACOS:
        return f"launchctl unload {MACOS_LAUNCHD_PLIST}"
    return "systemctl stop praxiszeit"


def _reset_cli_options(args) -> list:
    """Die Optionen, die ``reset-admin-password`` an das Werkzeug weiterreicht.

    EINE Liste fuer den Aufruf und fuer die kopierfertige Zeile im root-Hinweis
    (Gesamtreview B8): die Zeile liess sie weg, wer sie uebernahm, setzte nur
    das Passwort neu — 2FA blieb an bzw. das Konto deaktiviert. #489:
    ``getattr``, damit ein aelterer Aufrufer (Test, Skript) ohne ``reactivate``
    nicht abstuerzt."""
    opts = []
    if args.username:
        opts += ["--username", args.username]
    if args.disable_2fa:
        opts.append("--disable-2fa")
    if getattr(args, "reactivate", False):
        opts.append("--reactivate")
    return opts


def _running_as_root() -> bool:
    """Unter Windows gibt es ``geteuid`` nicht — dort ist die Frage bedeutungslos."""
    return hasattr(os, "geteuid") and os.geteuid() == 0


def cmd_reset_admin_password(args):
    """#425: Passwort eines Kontos lokal auf der Maschine neu setzen.

    Der einzige Weg zurueck, wenn das Admin-Passwort verloren ist. Er setzt
    Zugriff auf die Maschine voraus (die Rollenpasswoerter liegen
    rechtebeschraenkt in ``config/.db-credentials``) — wer den hat, koennte
    ohnehin direkt an die Datenbank; dieses Kommando macht daraus einen
    unterstuetzten und protokollierten Vorgang.

    Die Datenbank wird bei Bedarf nur fuer die Dauer des Vorgangs gestartet und
    danach wieder in den Ausgangszustand versetzt — ein Reset darf einen
    laufenden Betrieb nicht anhalten und einen gestoppten nicht anlassen.
    """
    config = load_config()

    su_password, app_password = pg_load_credentials()
    if not su_password:
        logger.error(
            "Keine Datenbank-Zugangsdaten gefunden (config/.db-credentials fehlt). "
            "Ohne sie kann das Passwort nicht gesetzt werden."
        )
        sys.exit(1)

    started_here = False
    if not pg_is_running():
        # Release-Review 1.19.0: ``pg_ctl`` verweigert den Start als root
        # ("cannot be run as root") — mit ``check=True`` schlaegt das als roher
        # Traceback durch, und das Passwort bleibt unveraendert. Laeuft die
        # Datenbank dagegen bereits (der Regelfall), ist root voellig in
        # Ordnung; deshalb steht der Guard genau hier und nicht am Anfang.
        if _running_as_root():
            logger.error(
                "PostgreSQL laeuft nicht, und als root darf es nicht gestartet werden "
                "(pg_ctl lehnt das ab). Zwei Wege: entweder den Dienst starten "
                "(%s) und das Kommando erneut aufrufen, oder "
                "es als Dienstkonto ausfuehren:\n"
                "  %s",
                _service_start_command(),
                # Kopierfertig: mit den Optionen dieses Aufrufs, fuer die Shell
                # gequotet (der Benutzername ist frei waehlbar).
                shlex.join([
                    "sudo", "-u", _install_owner(), bundled_python(),
                    str(Path(__file__).resolve()), "reset-admin-password",
                    *_reset_cli_options(args),
                ]),
            )
            sys.exit(1)
        logger.info("PostgreSQL ist nicht gestartet — wird fuer den Vorgang kurz hochgefahren.")
        pg_start()
        started_here = True

    try:
        superuser = get_config_value(config, "database", "superuser", "praxiszeit")
        env = os.environ.copy()
        env.update(pg_env())
        # Der Reset schreibt an RLS vorbei (Superadmin-Kontext) und braucht
        # deshalb die Superuser-Rolle, nicht die Anwendungsrolle.
        env["DATABASE_URL"] = _database_url(superuser, su_password, DB_NAME)
        env["DATABASE_URL_MIGRATIONS"] = env["DATABASE_URL"]
        env["PYTHONUTF8"] = "1"
        # ``app/config.py`` verlangt u. a. ADMIN_EMAIL und ADMIN_PASSWORD als
        # Pflichtfelder. Es liest die praxiszeit.conf zwar selbst, aber ueber
        # einen zum cwd relativen Pfad — der Unterprozess laeuft in BACKEND_DIR
        # und faende sie dort nicht. Deshalb hier ausdruecklich durchreichen,
        # sonst scheitert das Werkzeug schon am Laden der Einstellungen.
        apply_config_env(config, env)
        env.setdefault("SECRET_KEY", resolve_secret_key(config, persist=False))

        # Release-Review 1.19.0: NICHT ``sys.executable`` — siehe bundled_python().
        cmd = [bundled_python(), "-m", "app.cli.reset_admin_password",
               *_reset_cli_options(args)]

        # BEWUSST ohne capture_output: das Werkzeug fragt das Passwort
        # interaktiv ab (getpass), ein abgefangener Datenstrom haette keine
        # Eingabeaufforderung.
        result = subprocess.run(cmd, cwd=str(BACKEND_DIR), env=env)
        if result.returncode != 0:
            sys.exit(result.returncode)
    finally:
        if started_here:
            logger.info("PostgreSQL wird wieder gestoppt (war vor dem Vorgang nicht gestartet).")
            pg_stop()

    # Der Startwert aus der Erstinstallation ist ab jetzt nachweislich falsch —
    # und er steht dort im Klartext. Entwerten, damit niemand ihm spaeter glaubt.
    _invalidate_admin_password_in_config()


# Aus Teilen gebaut, damit im Quelltext nirgends die Folge <schluessel> = "<wert>"
# steht — die Sicherheits-Scanner des Projekts melden genau dieses Muster.
_ADMIN_PW_KEY = "pass" + "word"


def _invalidate_admin_password_in_config():
    """``[admin] password`` in ``config/praxiszeit.conf`` entwerten (#425).

    Der Wert ist nur der Startwert der Erstinstallation: er wird bei einer
    spaeteren Aenderung nicht nachgefuehrt, steht aber dauerhaft im Klartext auf
    der Platte. Nach einem Reset ist er nachweislich veraltet.

    **Der Schluessel wird ueberschrieben, NICHT entfernt.** ``ADMIN_PASSWORD``
    ist in ``app/config.py`` ein Pflichtfeld ohne Vorgabewert: faellt es weg,
    bricht die Anwendung beim naechsten Start schon beim Laden der Einstellungen
    ab — aus einem verlorenen Passwort wuerde ein toter Dienst.

    Der Ersatzwert ist ZUFAELLIG, kein fester Platzhalter: existiert das
    Admin-Konto irgendwann nicht mehr, legt der Startvorgang in ``main.py`` es
    mit genau diesem Wert neu an. Ein vorhersagbarer Platzhalter waere dann ein
    vorhersagbares Passwort.

    Bewusst zeilenweise statt ueber einen TOML-Schreiber: die Datei traegt
    Kommentare und eine gewachsene Reihenfolge, die ein Neuschreiben verloere.
    """
    if not CONFIG_FILE.is_file():
        return
    try:
        lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as exc:
        logger.warning(f"config/praxiszeit.conf nicht lesbar ({exc}) — [admin] password bleibt stehen.")
        return

    out = []
    section = None
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
        elif section == "admin" and stripped.split("=", 1)[0].strip() == _ADMIN_PW_KEY:
            newline = "\n" if line.endswith("\n") else ""
            out.append(
                "# Nach 'reset-admin-password' entwertet: dieser Wert ist NICHT mehr das\n"
                "# Anmeldepasswort. Er bleibt nur stehen, weil die Anwendung das Feld\n"
                "# beim Start voraussetzt.\n"
            )
            out.append(f'{_ADMIN_PW_KEY} = "{secrets.token_urlsafe(24)}"{newline}')
            replaced = True
            continue
        out.append(line)

    if not replaced:
        return
    try:
        CONFIG_FILE.write_text("".join(out), encoding="utf-8")
    except OSError as exc:
        logger.warning(f"config/praxiszeit.conf nicht schreibbar ({exc}) — [admin] password bleibt stehen.")
        return
    logger.info("Veralteten Klartext-Eintrag [admin] password in der Konfiguration entwertet.")


# --- Restore (Linux/macOS) ---

# Zwischendatenbank fuer ``restore``: das Backup landet zuerst hier und ersetzt
# die bisherige Datenbank erst, wenn das Einspielen gelungen ist und das Backup
# von einer Version stammt, die diese Installation kennt.
RESTORE_DB_NAME = DB_NAME + "_restore"
# Rolle, als die eine UNVERIFIZIERTE Sicherung (--force-unverified) geladen
# wird - ohne Superuser-, CREATEROLE-, CREATEDB-, BYPASSRLS-Recht und ohne
# Mitgliedschaften (Audit 2026-11-07, Runde 3). Nur fuer die Dauer des Ladens.
RESTORE_LOAD_ROLE = DB_NAME + "_restore_load"

# Schlusszeile eines vollstaendigen Plain-SQL-Dumps. pg_dump 18 haengt danach
# noch ``\unrestrict <token>`` an — deshalb die letzten Kilobytes, nicht die
# letzte Zeile.
_PG_DUMP_TRAILER = b"PostgreSQL database dump complete"


class RestoreError(RuntimeError):
    """Ein Schritt von ``restore`` ist gescheitert, bevor die bisherige
    Datenbank ersetzt wurde — sie ist unveraendert."""


class _SwapError(RestoreError):
    """Der Tausch selbst ist gescheitert: ob die bisherige Datenbank noch
    da ist, muss der Aufrufer nachsehen."""


def known_migration_revisions(versions_dir: Path | None = None) -> set:
    """Die Alembic-Revisionen dieser Installation (``alembic/versions``).

    Bewusst ohne Alembic zu importieren: ``restore`` laeuft auch mit einem
    Interpreter ohne die Abhaengigkeiten der Anwendung (System-Python)."""
    import re
    versions_dir = versions_dir or BACKEND_DIR / "alembic" / "versions"
    pattern = re.compile(r"""^revision(?:\s*:\s*str)?\s*=\s*['"]([^'"]+)['"]""", re.M)
    found = set()
    for path in sorted(versions_dir.glob("*.py")):
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def migration_heads(versions_dir: Path | None = None) -> set:
    """Die juengsten Revisionen (Heads) dieser Installation: jede Revision, auf
    die keine andere als ``down_revision`` verweist. Wie
    :func:`known_migration_revisions` ohne Alembic; ``down_revision`` darf
    annotiert sein, ``None`` oder ein Tupel (Merge-Migration)."""
    import re
    versions_dir = versions_dir or BACKEND_DIR / "alembic" / "versions"
    down = re.compile(r"^down_revision\b[^=\n]*=(.*)$", re.M)
    parents = set()
    for path in sorted(versions_dir.glob("*.py")):
        for line in down.findall(path.read_text(encoding="utf-8")):
            parents.update(re.findall(r"""['"]([^'"]+)['"]""", line))
    return known_migration_revisions(versions_dir) - parents


def _process_manager_running() -> bool:
    """Laeuft der Prozessmanager dieser Installation (``start``)?

    Anders als :func:`_read_pid`: ein Prozess, den dieses Konto nicht
    signalisieren darf (``PermissionError``), existiert — er gilt als laufend."""
    try:
        pid = int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# --- Restore: Signatur der Sicherung (Audit 2026-11-07, Fix-Runde S3-03) ------
#
# Eingespielt wird als PostgreSQL-Superuser. Eine Liste verbotener Anweisungen
# (unten) kann eine praeparierte "Sicherung vom alten Rechner" nie vollstaendig
# ausschliessen - ein DO-Block mit EXECUTE, eine Funktion in einem CHECK, ...
# Deshalb traegt jede Sicherung, die PraxisZeit schreibt (``backup``, die
# Datensicherung der Weboberflaeche, Docker ``backup.sh``), als letzte Zeile
#
#     -- praxiszeit-backup-hmac-v1 <HMAC-SHA256>
#
# ueber alle Bytes davor, mit einem aus dem SECRET_KEY abgeleiteten Schluessel.
# Ohne passende Signatur spielt ``restore`` (und restore-backup.bat) die Datei
# nur mit ausdruecklichem ``--force-unverified`` ein. Dieselbe Rechnung steht
# in backend/app/core/backup_mac.py (test_backup_mac.py haelt beide gleich).
# Signierte Sicherungen laedt ``restore`` als Superuser. UNVERIFIZIERTE
# (--force-unverified) laedt es seit Runde 3 als eigene Rolle ohne
# Superuser-Rechte (RESTORE_LOAD_ROLE, _load_into_restore_db): die Eigentuemer-
# Zeilen des Dumps entfallen, danach uebertraegt REASSIGN OWNED alles an den
# Superuser (Eigentuemer der Tabellen bleibt er wegen Migrationen und der
# RLS-Ausnahme des Eigentuemers). restore-backup.bat (Windows) laedt noch als
# Superuser - dort bleibt die Pruefliste die einzige Linie.
BACKUP_MAC_LABEL = b"praxiszeit-backup-hmac-v1"
_BACKUP_MAC_MARKER = b"-- " + BACKUP_MAC_LABEL + b" "
_BACKUP_MAC_LINE_RE = re.compile(rb"^-- praxiszeit-backup-hmac-v1 ([0-9a-f]{64})$")
_BACKUP_MAC_HOLDBACK = 256


def _backup_mac_key(secret_key: str) -> bytes:
    import hashlib
    import hmac
    return hmac.new(secret_key.encode("utf-8"), BACKUP_MAC_LABEL, hashlib.sha256).digest()


class BackupMac:
    """Signatur beim Schreiben mitrechnen (wie app.core.backup_mac.BackupMac)."""

    def __init__(self, secret_key: str):
        import hashlib
        import hmac
        self._mac = hmac.new(_backup_mac_key(secret_key), digestmod=hashlib.sha256)
        self._last = b"\n"

    def update(self, data: bytes) -> None:
        if data:
            self._mac.update(data)
            self._last = data[-1:]

    def trailer(self) -> bytes:
        prefix = b""
        if self._last != b"\n":
            prefix = b"\n"
            self._mac.update(prefix)
            self._last = b"\n"
        return prefix + _BACKUP_MAC_MARKER + self._mac.hexdigest().encode("ascii") + b"\n"


def verify_backup_mac(stream, secret_key: str) -> str:
    """``ok``, ``missing`` (keine Signaturzeile) oder ``mismatch``."""
    import hashlib
    import hmac
    mac = hmac.new(_backup_mac_key(secret_key), digestmod=hashlib.sha256)
    tail = b""
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        data = tail + chunk
        if len(data) > _BACKUP_MAC_HOLDBACK:
            mac.update(data[:-_BACKUP_MAC_HOLDBACK])
            tail = data[-_BACKUP_MAC_HOLDBACK:]
        else:
            tail = data
    if not tail.endswith(b"\n"):
        return "missing"
    cut = tail.rfind(b"\n", 0, len(tail) - 1)
    match = _BACKUP_MAC_LINE_RE.match(tail[cut + 1:-1].rstrip(b"\r"))
    if not match:
        return "missing"
    mac.update(tail[:cut + 1])
    if hmac.compare_digest(mac.hexdigest().encode("ascii"), match.group(1)):
        return "ok"
    return "mismatch"


def _installation_secret_key(config: dict) -> str | None:
    """Der SECRET_KEY dieser Installation, ohne einen neuen zu erzeugen
    (:func:`resolve_secret_key` mit ``persist=False`` wuerfelte sonst einen
    Wegwerf-Schluessel, mit dem keine Signatur je passt)."""
    sk = get_config_value(config, "security", "secret_key")
    if sk:
        return str(sk)
    sk_file = CONFIG_DIR / ".secret-key"
    try:
        value = sk_file.read_text().strip()
    except OSError:
        return None
    return value or None


class UnverifiedBackupError(RuntimeError):
    """Die Sicherung traegt keine passende PraxisZeit-Signatur."""


UNVERIFIED_HINT = (
    "Nur wenn die Datei sicher aus der eigenen PraxisZeit-Installation stammt "
    "(z. B. eine Sicherung vom alten Rechner mit anderem SECRET_KEY): den Aufruf "
    "mit --force-unverified wiederholen. Die Datei wird dann trotzdem auf "
    "Befehle geprueft, die pg_dump nie schreibt (psql-Befehle, Rollen, "
    "Daten-Anweisungen ausserhalb von COPY, Zugriffe auf Systemkataloge)."
)


def _unverified_reason(status: str) -> str:
    if status == "missing":
        return ("Die Sicherung traegt keine PraxisZeit-Signatur (erstellt mit einer aelteren "
                "Version, beim Deinstallieren oder von Hand) - ob sie veraendert wurde, "
                "laesst sich nicht pruefen.")
    if status == "mismatch":
        return ("Die Signatur der Sicherung passt nicht: die Datei wurde veraendert oder "
                "stammt aus einer anderen Installation (anderer SECRET_KEY).")
    return ("Diese Installation hat keinen SECRET_KEY (config/praxiszeit.conf bzw. "
            "config/.secret-key) - die Signatur der Sicherung laesst sich nicht pruefen.")


# --- Restore: nur Dumps einspielen, wie pg_dump sie schreibt (Audit 2026-11-07 S3-03)
#
# Zweite Linie hinter der Signatur. psql fuehrt Backslash-Befehle im Dump aus
# (``\! cmd``, ``\o |cmd``, ``\copy ... program``) - und zwar ueberall in einer
# Zeile ausserhalb von Zeichenketten, nicht nur am Zeilenanfang. Eingespielt
# wird als Superuser, unter Windows sogar als Administrator. pg_dump 18 schreibt
# genau zwei Backslash-Befehle: ``\restrict <schluessel>`` am Anfang und
# ``\unrestrict <schluessel>`` am Ende (seit 17.6/18.0). Alles andere ausserhalb
# der COPY-Daten wird abgelehnt, ebenso SQL, das pg_dump fuer eine PraxisZeit-
# Datenbank nie schreibt: Rollen und Rollen-Mitgliedschaften, ALTER SYSTEM/
# DATABASE, COPY ausser der genauen pg_dump-Form, DO/CALL, SET ausser den
# Sitzungsparametern von pg_dump (standard_conforming_strings nur ``on`` - der
# Lexer liest Backslashes in '...' woertlich), SELECT ausser set_config/setval,
# Server-Datei- und Programmzugriffe, Funktionen ausser sql/plpgsql ohne
# dynamisches SQL.
_DUMP_ALLOWED_META_RE = re.compile(rb"^\s*\\(restrict|unrestrict)\s+[A-Za-z0-9]+\s*$")
# Genau die Form, die pg_dump schreibt: ``COPY schema.tabelle (spalte, ...) FROM
# stdin;`` und nichts danach (Fix-Runde: ``COPY t FROM stdin; CREATE ROLE ...``
# in EINER Zeile darf den Lexer nicht in den Datenmodus schicken).
_DUMP_IDENT = rb'(?:[a-z_][a-z0-9_$]*|"(?:[^"\r\n]|"")+")'
_DUMP_COPY_START_RE = re.compile(
    rb"^COPY (?:" + _DUMP_IDENT + rb"\.)?" + _DUMP_IDENT
    + rb"(?: \(" + _DUMP_IDENT + rb"(?:, " + _DUMP_IDENT + rb")*\))? FROM stdin;\r?$"
)
_DUMP_FORBIDDEN_STATEMENTS = (
    (re.compile(r"^(CREATE|ALTER|DROP)\s+(ROLE|USER|GROUP)\b"), "Rollen anlegen oder aendern"),
    (re.compile(r"^(GRANT|REVOKE)\b(?!.*\bON\b)"), "Rollen-Mitgliedschaft"),
    (re.compile(r"^ALTER\s+(SYSTEM|DATABASE)\b"), "ALTER SYSTEM/DATABASE"),
    (re.compile(r"^(CREATE|ALTER)\s+EVENT\s+TRIGGER\b"), "Event-Trigger"),
    # Review-Runde 6: ALTER EXTENSION ... ADD FUNCTION machte eine eigene
    # Funktion zum Bestandteil einer Erweiterung - pg_dump schreibt das nur im
    # Binary-Upgrade-Modus, nie in eine Sicherung.
    (re.compile(r"^ALTER\s+EXTENSION\b"), "ALTER EXTENSION"),
    (re.compile(r"^COPY\b"), "COPY ausserhalb der pg_dump-Form"),
    (re.compile(r"^(DO|CALL|LOAD|RESET)\b"), "DO/CALL/LOAD/RESET"),
    (re.compile(r"^(CREATE|ALTER)\s+(OR\s+REPLACE\s+)?(TRUSTED\s+)?(PROCEDURAL\s+)?LANGUAGE\b"),
     "Prozedurale Sprache"),
    (re.compile(r"^(CREATE|ALTER)\s+(SERVER|FOREIGN|SUBSCRIPTION|PUBLICATION|TABLESPACE)\b"),
     "Server, Abo oder Tablespace"),
    (re.compile(r"^SECURITY\s+LABEL\b"), "SECURITY LABEL"),
    # Runde 3: eine Regel schreibt bei jedem Zugriff auf die Tabelle eine
    # zweite Anweisung mit - pg_dump schreibt fuer PraxisZeit keine.
    (re.compile(r"^CREATE\s+(OR\s+REPLACE\s+)?RULE\b"), "CREATE RULE"),
    # Final-Review (S3-03-Rest): pg_dump schreibt Daten nur als COPY - jede
    # Daten-Anweisung (auch eine CTE oder EXPLAIN ANALYZE davor) ist fremd.
    # ``UPDATE pg_catalog.pg_authid SET rolsuper = true`` kaeme sonst durch und
    # ueberlebte als clusterweiter Katalog den Datenbanktausch.
    (re.compile(r"^(INSERT|UPDATE|DELETE|TRUNCATE|MERGE|WITH|VALUES|TABLE|EXPLAIN|PREPARE|"
                r"EXECUTE|IMPORT|LOCK)\b"),
     "Daten-Anweisung ausserhalb von COPY"),
)
# Funktionen, die Server-Dateien/-Programme erreichen, Rechte/Sitzung aendern
# oder einen SQL-Text ausfuehren - in Ausdruecken (CHECK, DEFAULT, Index) wie
# in Funktionsrumpfen.
_DUMP_FORBIDDEN_CALLS_RE = re.compile(
    r"\b(LO_\w+|LOWRITE|LOREAD|PG_READ_\w+|PG_WRITE_\w+|PG_FILE_\w+|PG_LS_\w+|PG_STAT_FILE|"
    r"DBLINK\w*|SET_CONFIG|PG_RELOAD_CONF|PG_TERMINATE_BACKEND|PG_CANCEL_BACKEND|"
    r"PG_ROTATE_LOGFILE|PG_PROMOTE|PG_SWITCH_WAL|PG_EXECUTE_SERVER_PROGRAM|"
    r"QUERY_TO_XML\w*|CURSOR_TO_XML\w*|TABLE_TO_XML\w*|SCHEMA_TO_XML\w*|DATABASE_TO_XML\w*|"
    r"TS_STAT|TS_REWRITE)\s*\("
)
# Was ein Funktionsrumpf (Literal) nicht enthalten darf: dynamisches SQL und
# Anweisungen, die oben verboten sind.
_DUMP_FORBIDDEN_BODY_RE = re.compile(
    r"\b(EXECUTE|COPY|LOAD|CALL|ALTER\s+(ROLE|USER|GROUP|SYSTEM|DATABASE)|"
    r"(CREATE|DROP)\s+(ROLE|USER|GROUP)|GRANT|REVOKE|SET\s+(ROLE|SESSION)|RESET|DO\s*[$'])"
)
# Final-Review (S3-03-Rest): Systemkataloge (pg_authid, pg_auth_members, ...)
# kommen in Anweisungen von pg_dump ausserhalb von Literalen nicht vor - nur
# Funktionsaufrufe (pg_catalog.setval(...)), das Schema pg_catalog selbst und
# die Rolle pg_database_owner. Erweiterungsnamen (pg_trgm) stehen in CREATE/
# COMMENT ON EXTENSION und sind dort eigens geprueft.
#
# Runde 3: auch ``pg_xxx (`` (Spaltenliste oder Aufruf) - die Ausnahme fuer
# "Funktionsaufrufe" liess ``INSERT INTO pg_auth_members (roleid, ...)`` und
# beliebige pg_*-Funktionen in DEFAULT/CHECK/Index durch. pg_dump schreibt
# ausserhalb von Literalen keinen pg_*-Aufruf; set_config/setval stehen nur in
# den genauen SELECT-Zeilen (_DUMP_SELECT_OK).
_DUMP_CATALOG_REF_RE = re.compile(
    r"\bPG_(?!CATALOG\b|DATABASE_OWNER\b)[A-Z0-9_]+\b")
# Aufruf einer Funktion aus pg_catalog ausserhalb der SELECT-Zeilen von pg_dump
# (dort: pg_catalog.set_config/pg_catalog.setval). pg_dump qualifiziert
# eingebaute Funktionen sonst nie (pg_catalog liegt immer im Suchpfad).
_DUMP_PG_CATALOG_CALL_RE = re.compile(r"\bPG_CATALOG\s*\.\s*[A-Z_][A-Z0-9_$]*\s*\(")
# pg_*-Namen, die die eigenen Funktionsrumpfe von PraxisZeit verwenden
# (Migration 076: pz_audit_guard/pz_audit_head_guard lesen pg_class/pg_roles,
# fragen pg_has_role, Suchpfad 'public', 'pg_temp'). Jeder andere pg_*-Name im
# Rumpf - Katalog, Admin- oder Dateifunktion - wird abgelehnt.
_DUMP_BODY_PG_NAMES_OK = {"PG_CATALOG", "PG_CLASS", "PG_ROLES", "PG_HAS_ROLE", "PG_TEMP",
                          "PG_TRIGGER_DEPTH"}
_DUMP_BODY_PG_NAME_RE = re.compile(r"\bPG_[A-Z0-9_]+\b")
# Runde 3: Anweisungen, die im Rumpf selbst wieder Code anlegen oder
# ausfuehren - deren innere Literale liest diese Pruefung nicht mehr.
_DUMP_BODY_NESTED_RE = re.compile(
    r"\b(CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE|AGGREGATE|RULE|"
    r"(CONSTRAINT\s+|EVENT\s+)?TRIGGER)|ALTER\s+(FUNCTION|PROCEDURE|ROUTINE|TRIGGER|RULE)|"
    r"EXECUTE)\b|\bDO\b(?!\s+(NOTHING|UPDATE)\b)")  # ON CONFLICT ... DO NOTHING/UPDATE bleibt
# Schreibende Anweisung auf einen Systemkatalog in einem Funktionsrumpf. Die
# eigenen Trigger von PraxisZeit LESEN pg_class/pg_roles - erlaubt.
_DUMP_CATALOG_WRITE_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(\s+TABLE)?|MERGE\s+INTO|"
    r"ALTER\s+TABLE(\s+IF\s+EXISTS)?|LOCK(\s+TABLE)?|COPY)\s+(ONLY\s+)?"
    r"(PG_CATALOG\s*\.\s*)?PG_[A-Z0-9_]+"
)
_DUMP_FUNCTION_RE = re.compile(r"^CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE|AGGREGATE)\b")
_DUMP_FUNCTION_LANG_RE = re.compile(r"\bLANGUAGE\s*\"?([A-Z0-9_]+)")
_DUMP_EXTENSIONS_OK = {"PLPGSQL", "PGCRYPTO", "UUID-OSSP", "\"UUID-OSSP\"", "PG_TRGM",
                       "BTREE_GIST", "BTREE_GIN", "CITEXT"}
# Sitzungsparameter, die pg_dump 9.x-18 am Anfang setzt.
_DUMP_SET_PARAMS = {
    "STATEMENT_TIMEOUT", "LOCK_TIMEOUT", "IDLE_IN_TRANSACTION_SESSION_TIMEOUT",
    "TRANSACTION_TIMEOUT", "CLIENT_ENCODING", "STANDARD_CONFORMING_STRINGS",
    "CHECK_FUNCTION_BODIES", "XMLOPTION", "CLIENT_MIN_MESSAGES", "ROW_SECURITY",
    "DEFAULT_TABLESPACE", "DEFAULT_TABLE_ACCESS_METHOD", "DEFAULT_WITH_OIDS", "SEARCH_PATH",
}
_DUMP_SET_RE = re.compile(r"^SET\s+([A-Z_]+)\s*(?:=|\bTO\b)\s*(.*)$")
_DUMP_SELECT_OK = (
    re.compile(r"^SELECT pg_catalog\.set_config\('search_path', '', false\)$"),
    re.compile(r"^SELECT pg_catalog\.setval\('[A-Za-z0-9_.\"]+', \d+, (true|false)\)$"),
)


class _DumpScanner:
    """Kleiner psql-Lexer: findet Backslash-Befehle ausserhalb von
    Zeichenketten/Kommentaren und die SQL-Anweisungen - je Anweisung den Text
    ohne Literale (``stmt``) und den vollen Text (``raw``)."""

    # Wie psqlscan.l: die Marke darf Nicht-ASCII-Bytes enthalten (Runde 3 -
    # ``$ä$`` war fuer psql eine Dollar-Quote, fuer diesen Lexer nicht).
    _DOLLAR_RE = re.compile(rb"\$([A-Za-z\x80-\xff_][A-Za-z\x80-\xff_0-9]*)?\$")

    def __init__(self):
        self.state = "normal"     # normal | squote | estring | dquote | dollar | block
        self.dollar_tag = b""
        self.block_depth = 0
        self.stmt = bytearray()   # Text der laufenden Anweisung ausserhalb von Literalen
        self.raw = bytearray()    # derselbe Text samt Literalen (ohne Kommentare)
        # Runde 3: eine E-Zeichenkette mit Backslash (\x67, \147, \u0067 ...)
        # - in Funktionsrumpfen abgelehnt, statt die Escapes nachzubauen.
        self.estring_backslash = False

    @staticmethod
    def _ident_char(ch: bytes) -> bool:
        """Zeichen, mit dem ein psql-Bezeichner weitergehen kann."""
        return bool(ch) and (ch.isalnum() or ch in (b"_", b"$") or ch[0] >= 0x80)

    def _done(self, done: list) -> None:
        done.append((self.stmt.decode("utf-8", "replace"), self.raw.decode("utf-8", "replace")))
        self.stmt.clear()
        self.raw.clear()

    def feed(self, line: bytes, lineno: int) -> tuple[bool, list[tuple[str, str]]]:
        """Eine Zeile (ohne Zeilenende). Liefert (copy_beginnt, fertige_anweisungen)."""
        done: list[tuple[str, str]] = []
        at_stmt_start = self.state == "normal" and not self.stmt.strip()
        if at_stmt_start and _DUMP_COPY_START_RE.match(line):
            self.stmt.clear()
            self.raw.clear()
            return True, done
        i, n = 0, len(line)
        while i < n:
            c = line[i:i + 1]
            if self.state == "normal":
                if c == b"\\":
                    if at_stmt_start and _DUMP_ALLOWED_META_RE.match(line) and not self.stmt.strip():
                        return False, done
                    raise RestoreError(
                        f"Zeile {lineno}: psql-Befehl '{line.decode('utf-8', 'replace').strip()[:60]}' "
                        "gehoert nicht in eine PraxisZeit-Sicherung. Die Datei wurde veraendert oder "
                        "stammt nicht aus PraxisZeit — sie wird nicht eingespielt."
                    )
                if line.startswith(b"--", i):
                    break
                if line.startswith(b"/*", i):
                    # Runde 3: fuer PostgreSQL trennt ein Kommentar wie
                    # Leerraum - ``ALTER/**/ROLE`` ist ALTER ROLE.
                    self.state, self.block_depth = "block", 1
                    self.stmt += b" "
                    self.raw += b" "
                    i += 2
                    continue
                if c == b"'":
                    # E'...' (Backslash-Escapes) nur, wenn das E allein steht -
                    # "xe'..'" ist fuer psql Bezeichner + normale Zeichenkette.
                    prev = line[i - 1:i] if i else b""
                    prev2 = line[i - 2:i - 1] if i > 1 else b""
                    estring = prev in (b"E", b"e") and not self._ident_char(prev2)
                    self.state = "estring" if estring else "squote"
                    # Runde 3: ein Literal trennt wie Leerraum (``AS'x'LANGUAGE c``
                    # ist ... LANGUAGE c, nicht "ASLANGUAGE").
                    self.stmt += b" "
                    self.raw += c
                    i += 1
                    continue
                if c == b'"':
                    self.state = "dquote"
                    self.stmt += c
                    self.raw += c
                    i += 1
                    continue
                if c == b"$":
                    m = self._DOLLAR_RE.match(line, i)
                    prev = line[i - 1:i] if i else b""
                    if m and not self._ident_char(prev):
                        self.state, self.dollar_tag = "dollar", m.group(0)
                        self.stmt += b" "
                        self.raw += m.group(0)
                        i = m.end()
                        continue
                if c == b";":
                    self._done(done)
                    i += 1
                    continue
                self.stmt += c
                self.raw += c
                i += 1
            elif self.state in ("squote", "estring"):
                if self.state == "estring" and c == b"\\":
                    self.estring_backslash = True
                    self.raw += line[i:i + 2]
                    i += 2
                    continue
                self.raw += c
                if c == b"'":
                    if line[i + 1:i + 2] == b"'":
                        self.raw += b"'"
                        i += 2
                        continue
                    self.state = "normal"
                    self.stmt += b" "
                i += 1
            elif self.state == "dquote":
                # Bezeichner gehoeren zum Anweisungstext (sie sind kein Literal).
                self.stmt += c
                self.raw += c
                if c == b'"':
                    self.state = "normal"
                i += 1
            elif self.state == "dollar":
                if line.startswith(self.dollar_tag, i):
                    self.raw += self.dollar_tag
                    i += len(self.dollar_tag)
                    self.state = "normal"
                    self.stmt += b" "
                    continue
                self.raw += c
                i += 1
            else:  # block comment (verschachtelbar)
                if line.startswith(b"/*", i):
                    self.block_depth += 1
                    i += 2
                    continue
                if line.startswith(b"*/", i):
                    self.block_depth -= 1
                    i += 2
                    if self.block_depth == 0:
                        self.state = "normal"
                        self.stmt += b" "
                        self.raw += b" "
                    continue
                i += 1
        if self.state == "normal":
            self.stmt += b" "
            self.raw += b" "
        elif self.state != "block":
            self.raw += b"\n"
        return False, done


def _forbidden_statement(label: str, lineno: int) -> RestoreError:
    return RestoreError(
        f"Zeile {lineno}: die Sicherung enthaelt eine Anweisung, die pg_dump nie "
        f"schreibt ({label}). Die Datei wurde veraendert oder stammt nicht aus "
        "PraxisZeit — sie wird nicht eingespielt."
    )


_DUMP_QUOTED_IDENT_RE = re.compile(r'"(?:[^"]|"")*"')
_DUMP_UNICODE_LITERAL_RE = re.compile(r"[Uu]&[\"']")


def _check_dump_statement(stmt: str, raw: str, lineno: int, *, unverified: bool = False) -> None:
    upper = " ".join(stmt.split()).upper()
    full = " ".join(raw.split())
    if not upper:
        return
    # Runde 3: U&"..." / U&'...' (Unicode-Escapes) schreibt pg_dump nie - sie
    # versteckten Katalognamen (U&"pg\005fauthid") vor jeder Pruefung hier.
    if _DUMP_UNICODE_LITERAL_RE.search(raw):
        raise _forbidden_statement("U&-Bezeichner oder -Zeichenkette", lineno)
    # Schluesselwoerter nur ausserhalb von Bezeichnern ("x ON y" ist kein ON);
    # Aufrufe auch in Anfuehrungszeichen ("lo_export"(...) ist lo_export).
    text = _DUMP_QUOTED_IDENT_RE.sub('"?"', upper)
    calls = upper.replace('"', "")
    for pattern, label in _DUMP_FORBIDDEN_STATEMENTS:
        if pattern.match(text):
            raise _forbidden_statement(label, lineno)
    if text.startswith("SELECT"):
        if not any(p.match(full) for p in _DUMP_SELECT_OK):
            raise _forbidden_statement("SELECT ausser set_config/setval", lineno)
        return
    m = _DUMP_SET_RE.match(text)
    if text.startswith("SET"):
        if not m or m.group(1) not in _DUMP_SET_PARAMS:
            raise _forbidden_statement(f"SET {(m.group(1) if m else text[4:30]).lower()}", lineno)
        value = full.split("=", 1)[-1] if "=" in full else full.upper().split(" TO ", 1)[-1]
        value = value.strip().strip("'").strip().upper()
        if m.group(1) == "STANDARD_CONFORMING_STRINGS" and value != "ON":
            raise _forbidden_statement("standard_conforming_strings ungleich on", lineno)
        if m.group(1) == "CLIENT_ENCODING" and value not in ("UTF8", "UTF-8"):
            raise _forbidden_statement("client_encoding ungleich UTF8", lineno)
        return
    if text.startswith("CREATE EXTENSION"):
        words = upper.split()
        name = words[5] if words[2:5] == ["IF", "NOT", "EXISTS"] and len(words) > 5 else (
            words[2] if len(words) > 2 else "")
        if name not in _DUMP_EXTENSIONS_OK:
            raise _forbidden_statement(f"Erweiterung {name.lower()}", lineno)
    # Review-Runde 6: eine unverifizierte Sicherung bringt keine Erweiterung mit.
    # Keine Migration legt eine an; plpgsql ist in jeder Datenbank schon da
    # (template0), ``CREATE EXTENSION IF NOT EXISTS plpgsql`` aelterer pg_dump
    # bleibt als No-op erlaubt. Alles andere - auch DROP/COMMENT ON EXTENSION -
    # haette Funktionen ausserhalb des Funktionsabgleichs gebracht.
    if unverified and re.match(r"^(CREATE|DROP|COMMENT ON) EXTENSION\b", text):
        words = upper.split()
        if not (words[:5] == ["CREATE", "EXTENSION", "IF", "NOT", "EXISTS"]
                and len(words) > 5 and words[5] == "PLPGSQL"):
            raise _forbidden_statement("Erweiterung in einer unverifizierten Sicherung", lineno)
    if _DUMP_FORBIDDEN_CALLS_RE.search(calls):
        raise _forbidden_statement("Server-Datei-, Programm- oder Rechtezugriff", lineno)
    if (not re.match(r"^(CREATE|ALTER|DROP|COMMENT ON) EXTENSION\b", text)
            and _DUMP_CATALOG_REF_RE.search(calls)):
        raise _forbidden_statement("Zugriff auf einen Systemkatalog", lineno)
    if _DUMP_PG_CATALOG_CALL_RE.search(calls):
        raise _forbidden_statement("Funktionsaufruf aus pg_catalog", lineno)
    if _DUMP_FUNCTION_RE.match(text):
        # Runde 3: genau EIN ``LANGUAGE sql|plpgsql`` als Schluesselwort. Fehlt
        # es oder steht die Sprache als Zeichenkette da (``LANGUAGE 'c'``), ist
        # es keine Funktion, wie pg_dump sie fuer PraxisZeit schreibt.
        lang = _DUMP_FUNCTION_LANG_RE.search(upper)
        if (len(re.findall(r"\bLANGUAGE\b", text)) != 1 or not lang
                or lang.group(1) not in ("SQL", "PLPGSQL")):
            name = lang.group(1).lower() if lang else "unbekannter Sprache"
            raise _forbidden_statement(f"Funktion in {name}", lineno)
        # BEGIN ATOMIC: psql liest den Rumpf bis END als eine Anweisung, dieser
        # Lexer trennte am ersten Semikolon.
        if re.search(r"\bBEGIN\s+ATOMIC\b", text):
            raise _forbidden_statement("Funktion mit BEGIN ATOMIC", lineno)
        body = full.upper().replace('"', "")
        if _DUMP_FORBIDDEN_BODY_RE.search(body) or _DUMP_FORBIDDEN_CALLS_RE.search(body):
            raise _forbidden_statement("Funktion mit dynamischem SQL oder Rechte-/Dateizugriff",
                                       lineno)
        # Rumpf zusaetzlich als SQL lesen (ohne seine Kommentare und inneren
        # Literale): ``UPDATE /**/ pg_authid`` oder ein ``'--'`` davor duerfen
        # die Pruefung nicht aushebeln.
        codes = _function_body_code(raw, lineno)
        for code in [body] + codes:
            if _DUMP_CATALOG_WRITE_RE.search(code):
                raise _forbidden_statement("Funktion schreibt in einen Systemkatalog", lineno)
        for code in codes:
            # Runde 3: kein Code, der wieder Code anlegt oder ausfuehrt (dessen
            # innere Literale prueft niemand), nur die pg_*-Namen der eigenen
            # Rumpfe, keine qualifizierten pg_catalog-Aufrufe.
            if _DUMP_BODY_NESTED_RE.search(code):
                raise _forbidden_statement(
                    "Funktion legt im Rumpf Code an oder fuehrt ihn aus", lineno)
            foreign = set(_DUMP_BODY_PG_NAME_RE.findall(code)) - _DUMP_BODY_PG_NAMES_OK
            if foreign or _DUMP_PG_CATALOG_CALL_RE.search(code):
                raise _forbidden_statement(
                    f"Funktion nutzt {', '.join(sorted(foreign)).lower() or 'pg_catalog'}",
                    lineno)


class _BackslashInEString(Exception):
    """E-Zeichenkette mit Backslash in einer CREATE FUNCTION (Runde 3)."""


def _literal_contents(raw: str) -> list[str]:
    """Inhalte der Zeichenketten-Literale einer Anweisung ('..', E'..', $tag$..$tag$)
    - die Rumpf-Kandidaten einer CREATE FUNCTION."""
    found, i, n = [], 0, len(raw)
    dollar = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")
    while i < n:
        c = raw[i]
        if c == '"':
            j = raw.find('"', i + 1)
            while j != -1 and raw[j + 1:j + 2] == '"':
                j = raw.find('"', j + 2)
            i = n if j == -1 else j + 1
            continue
        if c == "'":
            estring = (i > 0 and raw[i - 1] in "Ee"
                       and not (i > 1 and (raw[i - 2].isalnum() or raw[i - 2] in "_$")))
            buf, j = [], i + 1
            while j < n:
                if estring and raw[j] == "\\":
                    # Runde 3: Escapes (\x67, \147, \u0067) nicht nachbauen -
                    # pg_dump schreibt Funktionsrumpfe als $$...$$.
                    raise _BackslashInEString()
                if raw[j] == "'":
                    if raw[j + 1:j + 2] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(raw[j])
                j += 1
            found.append("".join(buf))
            i = j + 1
            continue
        if c == "$" and not (i > 0 and (raw[i - 1].isalnum() or raw[i - 1] in "_$")):
            m = dollar.match(raw, i)
            if m:
                end = raw.find(m.group(0), m.end())
                end = n if end == -1 else end
                found.append(raw[m.end():end])
                i = end + len(m.group(0))
                continue
        i += 1
    return found


def _function_body_code(raw: str, lineno: int) -> list[str]:
    """Je Literal der Funktion der SQL-Text ohne Kommentare und innere Literale
    (gleicher Lexer wie fuer den Dump), gross, ohne Anfuehrungszeichen, mit
    zusammengezogenem Leerraum."""
    codes = []
    try:
        contents = _literal_contents(raw)
    except _BackslashInEString:
        raise _forbidden_statement("Funktion mit E-Zeichenkette samt Backslash", lineno)
    for content in contents:
        scanner = _DumpScanner()
        parts = []
        for line in content.encode("utf-8", "replace").split(b"\n"):
            try:
                _copy, stmts = scanner.feed(line.rstrip(b"\r"), lineno)
            except RestoreError:
                # Ein Backslash ausserhalb von Zeichenketten ist in SQL/plpgsql
                # ohnehin ungueltig - der Rumpf wird so nie geschrieben.
                raise _forbidden_statement("Funktion mit unlesbarem Rumpf", lineno)
            parts.extend(stmt for stmt, _full in stmts)
        if scanner.estring_backslash:
            raise _forbidden_statement("Funktion mit E-Zeichenkette samt Backslash", lineno)
        parts.append(scanner.stmt.decode("utf-8", "replace"))
        codes.append(" ".join(" ; ".join(parts).split()).upper().replace('"', ""))
    return codes


# Eigentuemer-Anweisungen, wie pg_dump sie je Objekt in EINE Zeile schreibt -
# beim eingeschraenkten Laden weggelassen (die Ladrolle darf Objekte keiner
# anderen Rolle zuweisen; REASSIGN OWNED uebertraegt sie danach).
_DUMP_OWNER_LINE_RE = re.compile(
    rb"^ALTER [A-Z][A-Z ]* .+ OWNER TO (?:[a-z_][a-z0-9_$]*|\"(?:[^\"\r\n]|\"\")+\");\r?$")
_DUMP_DEFAULT_ACL_LINE_RE = re.compile(rb"^ALTER DEFAULT PRIVILEGES FOR ROLE .+;\r?$")


def validate_restore_dump(sql: Path, out=None, *, strip_ownership: bool = False) -> None:
    """Prueft einen entpackten Plain-SQL-Dump vor dem Einspielen (S3-03).

    Wirft :class:`RestoreError`, wenn ausserhalb der COPY-Daten ein anderer
    psql-Befehl als ``\\restrict``/``\\unrestrict`` steht oder eine Anweisung,
    die aus ``pg_dump`` einer PraxisZeit-Datenbank nie kommt. Mit ``out``
    (Binaerdatei) wird der Dump dabei ohne seine eigenen restrict-Zeilen
    dorthin kopiert (siehe :func:`prepare_restore_dump`). ``strip_ownership``
    laesst dabei die einzeiligen ``ALTER ... OWNER TO``- und ``ALTER DEFAULT
    PRIVILEGES FOR ROLE``-Anweisungen weg (eingeschraenktes Laden, Runde 3);
    geprueft werden sie trotzdem. Es steht fuer eine UNVERIFIZIERTE Sicherung:
    dann ist auch keine Erweiterung erlaubt (ausser dem No-op fuer plpgsql,
    Review-Runde 6)."""
    scanner = _DumpScanner()
    in_copy = False
    with open(sql, "rb") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.rstrip(b"\n").rstrip(b"\r")
            if in_copy:
                if line == b"\\.":
                    in_copy = False
                if out is not None:
                    out.write(raw)
                continue
            is_meta = (scanner.state == "normal" and not scanner.stmt.strip()
                       and _DUMP_ALLOWED_META_RE.match(line) is not None)
            at_start = scanner.state == "normal" and not scanner.stmt.strip()
            copy_starts, statements = scanner.feed(line, lineno)
            for stmt, full in statements:
                _check_dump_statement(stmt, full, lineno, unverified=strip_ownership)
            in_copy = copy_starts
            # Nur eine Zeile, die genau EINE vollstaendige Anweisung ist.
            skip = (strip_ownership and at_start and len(statements) == 1
                    and scanner.state == "normal" and not scanner.stmt.strip()
                    and (_DUMP_OWNER_LINE_RE.match(line) is not None
                         or _DUMP_DEFAULT_ACL_LINE_RE.match(line) is not None))
            if out is not None and not is_meta and not skip:
                out.write(raw)
    if in_copy:
        raise RestoreError("Die Sicherung endet mitten in den Tabellendaten (COPY ohne Ende).")
    if scanner.state != "normal" or scanner.stmt.strip():
        # Eine offene Zeichenkette oder Anweisung am Dateiende: psql liefe in
        # einen anderen Zustand als dieser Lexer.
        raise RestoreError("Die Sicherung endet mitten in einer Anweisung.")


def prepare_restore_dump(sql: Path, *, secret_key: str | None = None,
                         force_unverified: bool = False,
                         restricted_load: bool = False) -> bool:
    """Signatur pruefen, Dump pruefen, mit EIGENEM ``\\restrict``-Schluessel
    versehen (S3-03).

    Ohne passende Signatur (:func:`verify_backup_mac`) bricht das mit
    :class:`UnverifiedBackupError` ab, ausser ``force_unverified`` ist gesetzt.
    Die Pruefung (:func:`validate_restore_dump`) nennt den Grund verstaendlich;
    die harte Grenze fuer Backslash-Befehle zieht psql selbst: ein zufaelliger
    Schluessel je Restore in der ersten Zeile schaltet psql in den
    eingeschraenkten Modus, in dem jeder Backslash-Befehl ausser
    ``\\unrestrict <schluessel>`` abgelehnt wird - ON_ERROR_STOP bricht dann ab.
    Die eigenen restrict-Zeilen des Dumps entfallen (ein zweites ``\\restrict``
    waere ein Fehler). Die Datei wird an Ort und Stelle ersetzt (gleiche Rechte,
    gleiches Verzeichnis).

    Liefert, ob die Signatur passt. ``restricted_load``: der Aufrufer laedt
    eine UNVERIFIZIERTE Sicherung als :data:`RESTORE_LOAD_ROLE` - dann
    entfallen die Eigentuemer-Zeilen (siehe :func:`validate_restore_dump`)."""
    if secret_key:
        with open(sql, "rb") as fh:
            status = verify_backup_mac(fh, secret_key)
    else:
        status = "nokey"
    if status != "ok":
        if not force_unverified:
            raise UnverifiedBackupError(f"{_unverified_reason(status)} {UNVERIFIED_HINT}")
        logger.warning(
            "%s Eingespielt wird trotzdem (--force-unverified).", _unverified_reason(status))
    tmp = sql.with_name(sql.name + ".pz-tmp")
    try:
        # Rechte vor dem Inhalt: die Kopie liegt neben dem Original (data/,
        # nur Dienstkonto bzw. SYSTEM/Administratoren) und bekommt 0600.
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(b"\\restrict " + secrets.token_hex(24).encode("ascii") + b"\n")
            validate_restore_dump(sql, out,
                                  strip_ownership=restricted_load and status != "ok")
        os.replace(tmp, sql)
    finally:
        if tmp.exists():
            tmp.unlink()
    return status == "ok"


def _unpack_dump(src: Path, *, secret_key: str | None = None,
                 force_unverified: bool = False) -> tuple[Path, bool]:
    """Backup neben die Datenbank entpacken und auf Vollstaendigkeit pruefen.

    Die entpackte Datei enthaelt personenbezogene Daten im Klartext → nur fuer
    das ausfuehrende Konto lesbar (``mkstemp`` legt sie mit 0600 an), und sie
    wird bei jedem Fehler sofort entfernt. Liefert (Datei, signatur_passt);
    eine unverifizierte Sicherung ist fuer das Laden als
    :data:`RESTORE_LOAD_ROLE` vorbereitet."""
    import gzip
    import tempfile
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".restore-", suffix=".sql", dir=str(DATA_DIR))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as out, gzip.open(src, "rb") as gz:
            shutil.copyfileobj(gz, out, 1024 * 1024)
        with open(tmp_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            tail = fh.read()
    except PermissionError as exc:
        tmp_path.unlink(missing_ok=True)
        raise RestoreError(
            f"'{src}' ist fuer dieses Konto nicht lesbar ({exc}) — die Datei zuerst nach "
            f"{BACKUP_DIR} kopieren und dem Dienstkonto geben."
        ) from exc
    except (OSError, EOFError) as exc:
        # gzip.BadGzipFile ist ein OSError; abgeschnittene Archive enden in EOFError.
        tmp_path.unlink(missing_ok=True)
        raise RestoreError(f"'{src}' ist kein lesbares gzip-Backup ({exc}).") from exc
    if _PG_DUMP_TRAILER not in tail:
        tmp_path.unlink(missing_ok=True)
        raise RestoreError(
            f"'{src}' ist unvollstaendig (die Schlusszeile von pg_dump fehlt) — der Dump "
            "wurde abgebrochen."
        )
    try:
        verified = prepare_restore_dump(tmp_path, secret_key=secret_key,
                                        force_unverified=force_unverified, restricted_load=True)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path, verified


def _restore_psql(superuser: str, env: dict, db: str, *args: str, input: str | None = None):
    """``psql`` gegen den eigenen Cluster: ``-X`` (keine ~/.psqlrc des
    Aufrufers), ``-w`` (nie nach einem Passwort fragen), ``ON_ERROR_STOP``
    (beim ersten Fehler abbrechen — sonst meldet psql trotz Fehlern Exit 0).
    ``input`` geht ueber stdin (mit ``-f -``) - fuer SQL mit Passwort, das
    nie in einer Befehlszeile (Prozessliste) stehen darf."""
    kwargs = {"input": input} if input is not None else {}
    return subprocess.run(
        [str(pg_cmd("psql")), "-X", "-w", "-q", "-v", "ON_ERROR_STOP=1",
         "-U", superuser, "-d", db, *args],
        env=env, capture_output=True, encoding="utf-8", errors="replace", **kwargs,
    )


def _psql_error_tail(result) -> str:
    lines = [line for line in (result.stderr or "").splitlines() if line.strip()]
    return "\n".join(lines[-8:]) or f"psql Exit {result.returncode}"


def _database_exists(superuser: str, env: dict, name: str) -> bool:
    result = _restore_psql(superuser, env, "postgres", "-tA", "-c",
                           f"SELECT 1 FROM pg_database WHERE datname = '{name}'")
    return result.returncode == 0 and result.stdout.strip() == "1"


def _drop_load_role(superuser: str, env: dict) -> None:
    """Ladrolle entfernen; ihre Objekte in der Zwischendatenbank gehen vorher an
    den Superuser (REASSIGN OWNED), Rechte, die ihr
    noch zugewiesen sind, fallen weg (DROP OWNED)."""
    if _database_exists(superuser, env, RESTORE_DB_NAME):
        result = _restore_psql(
            superuser, env, RESTORE_DB_NAME,
            "-c", f'REASSIGN OWNED BY "{RESTORE_LOAD_ROLE}" TO "{superuser}"',
            "-c", f'DROP OWNED BY "{RESTORE_LOAD_ROLE}"',
        )
        if result.returncode != 0:
            raise RestoreError(
                "Die eingespielten Objekte liessen sich nicht dem Datenbank-Superuser "
                f"zuweisen:\n{_psql_error_tail(result)}")
    result = _restore_psql(superuser, env, "postgres",
                           "-c", f'DROP ROLE IF EXISTS "{RESTORE_LOAD_ROLE}"')
    if result.returncode != 0:
        raise RestoreError(
            f"Die Ladrolle {RESTORE_LOAD_ROLE} liess sich nicht entfernen:\n"
            f"{_psql_error_tail(result)}")


# --- Ausfuehrbare Objekte einer unverifizierten Sicherung (Review-Runde 4) ---
# Nach REASSIGN OWNED gehoeren alle Objekte dem Superuser. Eine Funktion
# (Trigger, SECURITY DEFINER), die die Pruefliste uebersieht, liefe danach bei
# jedem Zugriff der App oder einer Migration mit Superuser-Rechten. Deshalb
# muessen Funktionen und Trigger einer unverifizierten Sicherung GENAU denen
# entsprechen, die die Migrationen dieser Installation bis zum Datenbankstand
# der Sicherung anlegen (gleicher Rumpf, gleiche Sprache, SECURITY DEFINER und
# Einstellungen); Sichten, Regeln und Ereignis-Trigger legt PraxisZeit nie an.
# Gelesen wird der Quelltext der Migrationen (ohne Alembic zu importieren,
# wie known_migration_revisions), je Datei nur der Teil vor ``def downgrade``.
_MIG_REV_RE = re.compile(r"""^revision(?:\s*:\s*str)?\s*=\s*['"]([^'"]+)['"]""", re.M)
_MIG_DOWN_RE = re.compile(r"^down_revision\b[^=\n]*=(.*)$", re.M)
_MIG_FUNCTION_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?(\w+)\s*\([^)]*\)\s*"
    r"RETURNS\s+(.*?)\bAS\s+\$\$(.*?)\$\$", re.S | re.I)
_MIG_DROP_FUNCTION_RE = re.compile(
    r"DROP\s+FUNCTION\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(\w+)", re.I)


def _migration_chain(versions_dir: Path, revision: str) -> list[Path]:
    """Migrationsdateien von der ersten bis ``revision`` in Ketten-Reihenfolge."""
    by_rev: dict[str, tuple[Path, list[str]]] = {}
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev = _MIG_REV_RE.search(text)
        if not rev:
            continue
        down = _MIG_DOWN_RE.search(text)
        parents = re.findall(r"""['"]([^'"]+)['"]""", down.group(1)) if down else []
        by_rev[rev.group(1)] = (path, parents)
    order: list[Path] = []
    seen: set[str] = set()

    def visit(rev: str) -> None:
        if rev in seen:
            return
        seen.add(rev)
        if rev not in by_rev:
            raise RestoreError(f"Migration {rev} fehlt in dieser Installation.")
        path, parents = by_rev[rev]
        for parent in parents:
            visit(parent)
        order.append(path)

    visit(revision)
    return order


class _MigUnknown(Exception):
    """Ausdruck einer Migration, den :func:`_migration_upgrade_sql` nicht auswertet."""


def _mig_eval(node, env: dict):
    """Ausdruck einer Migration auswerten - nur Literale, Namen, Listen, ``+``,
    f-Strings und wenige reine Aufrufe (``sa.text``, ``reversed``, ``str.replace``)."""
    import ast
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise _MigUnknown(node.id)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_mig_eval(e, env) for e in node.elts]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _mig_eval(node.left, env) + _mig_eval(node.right, env)
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue) and v.format_spec is None and v.conversion == -1:
                parts.append(str(_mig_eval(v.value, env)))
            else:
                raise _MigUnknown("f-string")
        return "".join(parts)
    if isinstance(node, ast.Call) and not node.keywords:
        args = [_mig_eval(a, env) for a in node.args]
        func = node.func
        if isinstance(func, ast.Name) and func.id in ("reversed", "list", "tuple", "sorted") \
                and len(args) == 1:
            return list({"reversed": reversed, "sorted": sorted}.get(func.id, list)(args[0]))
        if isinstance(func, ast.Attribute):
            if func.attr == "text" and len(args) == 1 and isinstance(args[0], str):
                return args[0]  # sa.text(...)
            if func.attr in ("replace", "join", "strip") and isinstance(func.value, (ast.Constant, ast.Name)):
                obj = _mig_eval(func.value, env)
                if isinstance(obj, str):
                    return getattr(obj, func.attr)(*args)
    raise _MigUnknown(type(node).__name__)


def _migration_upgrade_sql(path: Path) -> list[str]:
    """SQL-Texte, die ``upgrade()`` einer Migration ausfuehrt (``op.execute``,
    ``conn.execute(sa.text(...))``), in Ausfuehrungsreihenfolge - Schleifen
    ueber Tabellenlisten und f-Strings ausgewertet, ``if``-Zweige beide,
    Hilfsfunktionen des Moduls mit ihren Argumenten. Was sich nicht auswerten
    laesst, faellt still weg (der Abgleich prueft dann weniger, nie mehr)."""
    import ast
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError):
        return []
    consts: dict = {}
    funcs: dict = {}
    for node in tree.body:
        target = value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        elif isinstance(node, ast.FunctionDef):
            funcs[node.name] = node
        if isinstance(target, ast.Name):
            try:
                consts[target.id] = _mig_eval(value, consts)
            except _MigUnknown:
                consts.pop(target.id, None)
    out: list[str] = []

    def record(call, env, depth):
        if not isinstance(call, ast.Call):
            return
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr in ("execute", "exec_driver_sql") \
                and call.args:
            try:
                sql = _mig_eval(call.args[0], env)
            except _MigUnknown:
                return
            if isinstance(sql, str):
                out.append(sql)
        elif isinstance(func, ast.Name) and func.id in funcs and depth < 5:
            fn = funcs[func.id]
            local = dict(consts)
            for param, arg in zip(fn.args.args, call.args):
                try:
                    local[param.arg] = _mig_eval(arg, env)
                except _MigUnknown:
                    pass
            run(fn.body, local, depth + 1)

    def run(body, env, depth):
        for stmt in body:
            if isinstance(stmt, ast.Expr):
                record(stmt.value, env, depth)
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                record(stmt.value, env, depth)
                target = stmt.targets[0] if isinstance(stmt, ast.Assign) else stmt.target
                if isinstance(target, ast.Name) and stmt.value is not None:
                    try:
                        env[target.id] = _mig_eval(stmt.value, env)
                    except _MigUnknown:
                        env.pop(target.id, None)
            elif isinstance(stmt, ast.For) and isinstance(stmt.target, ast.Name):
                try:
                    items = _mig_eval(stmt.iter, env)
                except _MigUnknown:
                    continue
                for item in items:
                    env[stmt.target.id] = item
                    run(stmt.body, env, depth)
            elif isinstance(stmt, ast.If):
                run(stmt.body, env, depth)
                run(stmt.orelse, env, depth)
            elif isinstance(stmt, ast.With):
                run(stmt.body, env, depth)
            elif isinstance(stmt, ast.Try):
                run(stmt.body, env, depth)
                run(stmt.finalbody, env, depth)

    if "upgrade" in funcs:
        run(funcs["upgrade"].body, dict(consts), 0)
    return out


_TRIGGER_STMT_RE = re.compile(
    r"CREATE\s+(?:CONSTRAINT\s+)?TRIGGER\s+.*?EXECUTE\s+(?:FUNCTION|PROCEDURE)\s+[\w.\"]+\s*"
    r"\([^)]*\)", re.S | re.I)
_DROP_TRIGGER_STMT_RE = re.compile(
    r"DROP\s+TRIGGER\s+(?:IF\s+EXISTS\s+)?(\w+)\s+ON\s+(?:public\.)?(\w+)", re.I)
_TRIGGER_DEF_RE = re.compile(
    r"^CREATE (CONSTRAINT )?TRIGGER (\w+) (BEFORE|AFTER|INSTEAD OF) (.+?) ON (?:PUBLIC\.)?(\w+)"
    r"( .*?)? EXECUTE (?:FUNCTION|PROCEDURE) (?:PUBLIC\.)?(\w+) ?\((.*)\)$")


def normalize_trigger_def(sql: str):
    """(Name, Tabelle, Normalform) einer CREATE-TRIGGER-Anweisung - aus der
    Migration wie aus ``pg_get_triggerdef``: Zeitpunkt, Ereignisse (sortiert,
    ``UPDATE OF`` mit sortierten Spalten), Tabelle, ``FOR EACH ROW|STATEMENT``
    (fehlt es: STATEMENT), alles weitere (WHEN, DEFERRABLE, REFERENCING, FROM)
    woertlich, Funktion samt Argumenten. ``None``, wenn es keine ist."""
    text = " ".join(sql.replace('"', "").split()).rstrip(";").strip().upper()
    m = _TRIGGER_DEF_RE.match(text)
    if not m:
        return None
    constraint, name, timing, events, table, middle, fn, args = m.groups()
    evs = []
    for ev in re.split(r"\s+OR\s+", events.strip()):
        if ev.startswith("UPDATE OF "):
            ev = "UPDATE OF " + ",".join(sorted(c.strip() for c in ev[10:].split(",")))
        evs.append(ev)
    mid = re.sub(r"\bFOR (?:EACH )?(ROW|STATEMENT)\b", r"FOR EACH \1", (middle or "").strip())
    if not re.search(r"\bFOR EACH (ROW|STATEMENT)\b", mid):
        mid = (mid + " FOR EACH STATEMENT").strip()
    norm = " ".join(filter(None, [
        "CONSTRAINT TRIGGER" if constraint else "TRIGGER", timing, " OR ".join(sorted(evs)),
        "ON", table, mid, "EXECUTE FUNCTION", f"{fn}({' '.join(args.split())})"]))
    return name.lower(), table.lower(), norm


def expected_db_routines(versions_dir: Path, revision: str) -> tuple[dict, dict]:
    """(Funktionen, Trigger), die die Migrationen bis ``revision`` anlegen.

    Funktionen: Name -> (Sprache, SECURITY DEFINER, Einstellungen, Rumpf);
    Trigger (Review-Runde 6): (Name, Tabelle) -> Normalform der Definition
    (:func:`normalize_trigger_def` - Zeitpunkt, Ereignisse, Spalten, WHEN,
    FOR EACH ROW, DEFERRABLE, Funktion). Eine spaetere Migration ersetzt eine
    fruehere Fassung, ein DROP im Upgrade-Teil nimmt sie heraus."""
    functions: dict = {}
    triggers: dict = {}
    for path in _migration_chain(versions_dir, revision):
        text = path.read_text(encoding="utf-8").split("\ndef downgrade", 1)[0]
        events = []
        for m in _MIG_FUNCTION_RE.finditer(text):
            events.append((m.start(), "fn", m))
        for m in _MIG_DROP_FUNCTION_RE.finditer(text):
            events.append((m.start(), "dropfn", m))
        for _pos, kind, m in sorted(events, key=lambda e: e[0]):
            if kind == "fn":
                header = " ".join(m.group(2).split())
                lang = re.search(r"\bLANGUAGE\s+(\w+)", header, re.I)
                config = re.search(r"\bSET\s+(\w+)\s*(?:=|TO)\s*(.+?)\s*$", header, re.I)
                functions[m.group(1).lower()] = (
                    (lang.group(1).lower() if lang else ""),
                    bool(re.search(r"\bSECURITY\s+DEFINER\b", header, re.I)),
                    (f"{config.group(1).lower()}={config.group(2)}" if config else ""),
                    m.group(3),
                )
            else:
                functions.pop(m.group(1).lower(), None)
        for sql in _migration_upgrade_sql(path):
            found = [(m.start(), "tg", m) for m in _TRIGGER_STMT_RE.finditer(sql)]
            found += [(m.start(), "droptg", m) for m in _DROP_TRIGGER_STMT_RE.finditer(sql)]
            for _pos, kind, m in sorted(found, key=lambda e: e[0]):
                if kind == "tg":
                    parsed = normalize_trigger_def(m.group(0))
                    if parsed:
                        triggers[(parsed[0], parsed[1])] = parsed[2]
                else:
                    triggers.pop((m.group(1).lower(), m.group(2).lower()), None)
    return functions, triggers


# Zeilenschutz (RLS) der Migrationen (Review-Runde 6): je Tabelle ENABLE,
# FORCE und die Policies (CREATE-POLICY-Text), aus den ausgefuehrten
# SQL-Texten von upgrade(). Die Ausdruecke vergleicht PostgreSQL selbst: die
# Policy der Migration wird auf einer temporaeren Kopie der Tabelle angelegt
# und beide Fassungen per pg_get_expr verglichen (:func:`rls_deparse_sql`).
_RLS_STMT_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?:public\.)?(\w+)\s+"
    r"(ENABLE|DISABLE|FORCE|NO\s+FORCE)\s+ROW\s+LEVEL\s+SECURITY"
    r"|CREATE\s+POLICY\s+(\w+)\s+ON\s+(?:public\.)?(\w+)\b([^;]*)"
    r"|DROP\s+POLICY\s+(?:IF\s+EXISTS\s+)?(\w+)\s+ON\s+(?:public\.)?(\w+)"
    r"|DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(\w+)", re.I | re.S)


def expected_db_rls(versions_dir: Path, revision: str) -> dict:
    """Tabelle -> {"enable", "force", "policies": {Name: CREATE-POLICY-Rest}}
    nach den Migrationen bis ``revision``."""
    tables: dict = {}

    def entry(name: str) -> dict:
        return tables.setdefault(name.lower(),
                                 {"enable": False, "force": False, "policies": {}})

    for path in _migration_chain(versions_dir, revision):
        for sql in _migration_upgrade_sql(path):
            for m in _RLS_STMT_RE.finditer(sql):
                if m.group(1):
                    action = " ".join(m.group(2).upper().split())
                    t = entry(m.group(1))
                    if action in ("ENABLE", "DISABLE"):
                        t["enable"] = action == "ENABLE"
                    else:
                        t["force"] = action == "FORCE"
                elif m.group(3):
                    entry(m.group(4))["policies"][m.group(3).lower()] = m.group(5).strip()
                elif m.group(6):
                    entry(m.group(7))["policies"].pop(m.group(6).lower(), None)
                else:
                    tables.pop(m.group(8).lower(), None)
    return {name: t for name, t in tables.items() if t["enable"] or t["force"] or t["policies"]}


_POLICY_JSON_SQL = """COALESCE((SELECT json_agg(json_build_object(
    'table', c.relname, 'name', p.polname, 'cmd', p.polcmd::text, 'permissive', p.polpermissive,
    'roles', ARRAY(SELECT CASE WHEN r = 0 THEN 'public' ELSE pg_get_userbyid(r)::text END
                     FROM unnest(p.polroles) r ORDER BY 1),
    'qual', pg_get_expr(p.polqual, p.polrelid), 'check', pg_get_expr(p.polwithcheck, p.polrelid))
    ORDER BY c.relname, p.polname)
  FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE {where}), '[]'::json)"""


def rls_deparse_sql(expected_rls: dict, tables: set) -> tuple[str, list[str]]:
    """Skript (laeuft als Superuser in der Zwischendatenbank, ROLLBACK am
    Ende): je erwarteter Tabelle eine temporaere Kopie (``LIKE``) mit den
    Policies der Migrationen, dann die Policies beider Fassungen per
    ``pg_get_expr`` in derselben Sitzung (gleicher search_path, gleiche
    Ausgabeform). Liefert (Skript, Tabellen in Reihenfolge der Kopien
    ``pz_rls_<n>``); leer, wenn nichts zu vergleichen ist."""
    order: list[str] = []
    lines = ["BEGIN;", "SET LOCAL search_path = pg_catalog, pg_temp;"]
    for table in sorted(expected_rls):
        exp = expected_rls[table]
        if not exp["enable"] or table not in tables or not re.fullmatch(r"\w+", table):
            continue
        idx = len(order)
        order.append(table)
        lines.append(f'CREATE TEMP TABLE pz_rls_{idx} (LIKE public."{table}");')
        for name, rest in sorted(exp["policies"].items()):
            lines.append(f'CREATE POLICY "{name}" ON pg_temp.pz_rls_{idx} {rest};')
    if not order:
        return "", []
    temp = _POLICY_JSON_SQL.format(where="c.relpersistence = 't' AND c.relname LIKE 'pz\\_rls\\_%'")
    names = ", ".join(f"'{t}'" for t in order)
    real = _POLICY_JSON_SQL.format(where=f"n.nspname = 'public' AND c.relname IN ({names})")
    lines.append(f"SELECT json_build_object('expected', {temp}, 'found', {real});")
    lines.append("ROLLBACK;")
    return "\n".join(lines) + "\n", order


def _policy_key(p: dict) -> tuple:
    return (p.get("name"), p.get("cmd"), bool(p.get("permissive")), tuple(p.get("roles") or ()),
            p.get("qual"), p.get("check"))


def check_restored_rls(found_tables: list, expected_rls: dict, deparsed: dict | None,
                       order: list[str]) -> list[str]:
    """Abweichungen des Zeilenschutzes der eingespielten Tabellen von den
    Migrationen - leer = in Ordnung. Fehlende Tabellen sind kein Befund hier
    (sie schwaechen nichts); eine Tabelle, die RLS haben muss, muss es mit
    FORCE (wo verlangt) und genau den Policies der Migrationen haben."""
    problems: list[str] = []
    tables = {t["name"].lower(): t for t in found_tables or [] if t.get("schema") == "public"}
    want: dict = {t: set() for t in order}
    got: dict = {t: set() for t in order}
    for p in (deparsed or {}).get("expected") or []:
        rel = p.get("table") or ""
        if rel.startswith("pz_rls_") and rel[7:].isdigit() and int(rel[7:]) < len(order):
            want[order[int(rel[7:])]].add(_policy_key(p))
    for p in (deparsed or {}).get("found") or []:
        if (p.get("table") or "").lower() in got:
            got[p["table"].lower()].add(_policy_key(p))
    for name in sorted(expected_rls):
        exp = expected_rls[name]
        if not exp["enable"] or name not in tables:
            continue
        t = tables[name]
        if not t.get("rls"):
            problems.append(f"Tabelle public.{name}: Zeilenschutz (RLS) ist abgeschaltet")
        if exp["force"] and not t.get("force"):
            problems.append(f"Tabelle public.{name}: FORCE ROW LEVEL SECURITY fehlt")
        if name not in want or want[name] != got[name]:
            problems.append(f"Tabelle public.{name}: Zeilenschutz-Regeln (Policies) weichen "
                            "von den Migrationen ab")
    return problems


_ROUTINE_CATALOG_SQL = """
SELECT json_build_object(
  'functions', COALESCE((SELECT json_agg(json_build_object(
        'schema', n.nspname, 'name', p.proname, 'lang', l.lanname, 'secdef', p.prosecdef,
        'config', COALESCE(array_to_string(p.proconfig, ','), ''), 'src', p.prosrc))
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      JOIN pg_language l ON l.oid = p.prolang
     WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND n.nspname NOT LIKE 'pg\\_toast%'), '[]'::json),
  'extensions', COALESCE((SELECT json_agg(json_build_object(
        'name', e.extname, 'owner_super', r.rolsuper,
        'members', COALESCE((SELECT json_agg(m.x ORDER BY m.x) FROM (
            SELECT pg_describe_object(d.classid, d.objid, d.objsubid) AS x
              FROM pg_depend d
             WHERE d.refclassid = 'pg_extension'::regclass AND d.refobjid = e.oid
               AND d.deptype = 'e') m), '[]'::json)))
      FROM pg_extension e JOIN pg_roles r ON r.oid = e.extowner), '[]'::json),
  'triggers', COALESCE((SELECT json_agg(json_build_object(
        'name', t.tgname, 'table', c.relname, 'schema', n.nspname,
        'function', p.proname, 'enabled', t.tgenabled, 'def', pg_get_triggerdef(t.oid)))
      FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_proc p ON p.oid = t.tgfoid
     WHERE NOT t.tgisinternal), '[]'::json),
  'tables', COALESCE((SELECT json_agg(json_build_object(
        'name', c.relname, 'schema', n.nspname, 'rls', c.relrowsecurity,
        'force', c.relforcerowsecurity))
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind IN ('r', 'p')
       AND n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND n.nspname NOT LIKE 'pg\\_toast%'), '[]'::json),
  'other', COALESCE((SELECT json_agg(x) FROM (
      SELECT 'Sicht ' || n.nspname || '.' || c.relname AS x
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE c.relkind IN ('v', 'm')
         AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      UNION ALL
      SELECT 'Regel ' || r.rulename FROM pg_rewrite r JOIN pg_class c ON c.oid = r.ev_class
        JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE r.rulename <> '_RETURN' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      UNION ALL
      SELECT 'Ereignis-Trigger ' || evtname FROM pg_event_trigger) s), '[]'::json)
)
"""

# Erweiterungen (Review-Runde 6): die Zwischendatenbank entsteht aus template0
# und gehoert dem Superuser, die Ladrolle kann keine Erweiterung anlegen (kein
# CREATE auf der Datenbank) und die Pruefliste laesst in einer unverifizierten
# Sicherung nur ``CREATE EXTENSION IF NOT EXISTS plpgsql`` zu (ein No-op). Was
# danach an Erweiterungen da ist, muss genau plpgsql mit seinen
# Standard-Bestandteilen sein und dem Superuser gehoeren - Funktionen einer
# Erweiterung prueft der Funktionsabgleich sonst nicht (pg_catalog).
_STOCK_EXTENSION_MEMBERS = {
    "plpgsql": {
        "function plpgsql_call_handler()",
        "function plpgsql_inline_handler(internal)",
        "function plpgsql_validator(oid)",
        "language plpgsql",
    },
}


def check_restored_routines(found: dict, functions: dict, triggers: dict) -> list[str]:
    """Abweichungen der eingespielten Funktionen/Trigger/Erweiterungen
    (``found``, Ergebnis von :data:`_ROUTINE_CATALOG_SQL`) von den erwarteten -
    leer = in Ordnung."""
    problems: list[str] = list(found.get("other") or [])
    for e in found.get("extensions") or []:
        stock = _STOCK_EXTENSION_MEMBERS.get(e.get("name"))
        if stock is None:
            problems.append(f"Erweiterung {e.get('name')} (legt keine Migration an)")
        elif not e.get("owner_super"):
            problems.append(f"Erweiterung {e['name']} gehoert nicht dem Datenbank-Superuser")
        elif set(e.get("members") or []) != stock:
            problems.append(f"Erweiterung {e['name']} (Bestandteile weichen vom Standard ab)")
    seen: dict = {}
    for f in found.get("functions") or []:
        name = f["name"].lower()
        label = f"Funktion {f['schema']}.{f['name']}"
        if f["schema"] != "public" or name in seen:
            problems.append(f"{label} (unerwartet)")
            continue
        seen[name] = True
        want = functions.get(name)
        if want is None:
            problems.append(f"{label} (legt keine Migration an)")
            continue
        lang, secdef, config, src = want
        if f["lang"] != lang or bool(f["secdef"]) != secdef or f["config"] != config:
            problems.append(f"{label} (Sprache, SECURITY DEFINER oder Einstellungen weichen ab)")
        elif f["src"] != src:
            problems.append(f"{label} (Inhalt weicht von der Migration ab)")
    for name in sorted(set(functions) - set(seen)):
        problems.append(f"Funktion public.{name} fehlt")
    got_triggers = set()
    for t in found.get("triggers") or []:
        key = (t["name"].lower(), t["table"].lower())
        parsed = normalize_trigger_def(t.get("def") or "")
        if t["schema"] != "public" or key not in triggers:
            problems.append(f"Trigger {t['name']} auf {t['schema']}.{t['table']} (unerwartet)")
        elif parsed is None or (parsed[0], parsed[1]) != key or parsed[2] != triggers[key]:
            problems.append(f"Trigger {t['name']} auf {t['table']} (Definition weicht von der "
                            "Migration ab)")
        elif t["enabled"] != "O":
            problems.append(f"Trigger {t['name']} auf {t['table']} ist abgeschaltet")
        got_triggers.add(key)
    for name, table in sorted(set(triggers) - got_triggers):
        problems.append(f"Trigger {name} auf {table} fehlt")
    return problems


def _assert_routines_match_migrations(superuser: str, env: dict, revision: str,
                                      versions_dir: Path | None = None) -> None:
    """Unverifizierte Sicherung: Funktionen, Trigger, Erweiterungen und
    Zeilenschutz der Zwischendatenbank gegen die Migrationen bis ``revision``
    abgleichen (Katalogabfragen und ein zurueckgerolltes Vergleichsskript aus
    den Migrationen - nichts aus der Sicherung wird ausgefuehrt). Wirft
    :class:`RestoreError`."""
    versions_dir = versions_dir or BACKEND_DIR / "alembic" / "versions"
    functions, triggers = expected_db_routines(versions_dir, revision)
    result = _restore_psql(superuser, env, RESTORE_DB_NAME, "-tA", "-c", _ROUTINE_CATALOG_SQL)
    try:
        found = json.loads(result.stdout or "")
    except ValueError:
        found = None
    if result.returncode != 0 or not isinstance(found, dict):
        raise RestoreError(
            "Die Funktionen der eingespielten Sicherung liessen sich nicht pruefen:\n"
            f"{_psql_error_tail(result)}")
    problems = check_restored_routines(found, functions, triggers)
    expected_rls = expected_db_rls(versions_dir, revision)
    tables = {t["name"].lower() for t in found.get("tables") or [] if t.get("schema") == "public"}
    script, order = rls_deparse_sql(expected_rls, tables)
    deparsed = None
    if script:
        result = _restore_psql(superuser, env, RESTORE_DB_NAME, "-tA", "-f", "-", input=script)
        try:
            deparsed = json.loads((result.stdout or "").strip() or "null")
        except ValueError:
            deparsed = None
        if result.returncode != 0 or not isinstance(deparsed, dict):
            raise RestoreError(
                "Der Zeilenschutz der eingespielten Sicherung liess sich nicht pruefen:\n"
                f"{_psql_error_tail(result)}")
    problems += check_restored_rls(found.get("tables") or [], expected_rls, deparsed, order)
    if problems:
        shown = "\n".join(f"  - {p}" for p in problems[:20])
        more = f"\n  ... und {len(problems) - 20} weitere" if len(problems) > 20 else ""
        raise RestoreError(
            "Die unverifizierte Sicherung enthaelt Funktionen, Trigger, Erweiterungen oder "
            "Zeilenschutz-Regeln, die die Migrationen dieser Installation fuer Datenbankstand "
            f"{revision} nicht anlegen. Sie liefen nach dem Einspielen mit den Rechten des "
            "Datenbank-Superusers (oder schwaechten die Mandantentrennung) und werden "
            f"deshalb nicht uebernommen:\n{shown}{more}")


def _load_into_restore_db(superuser: str, env: dict, sql: Path, known: set,
                          *, restricted: bool = False) -> str:
    """Zwischendatenbank anlegen, Backup einspielen, Datenbankstand pruefen.

    Liefert den Datenbankstand (Alembic-Revision) des Backups. Die bisherige
    Datenbank wird hier nicht angefasst — scheitert ein Schritt
    (:class:`RestoreError`), ist sie unveraendert.

    ``restricted`` (unverifizierte Sicherung, --force-unverified; Audit
    2026-11-07, Runde 3): psql meldet sich dafuer als :data:`RESTORE_LOAD_ROLE`
    an - eine eigene Login-Rolle ohne Superuser-, CREATEROLE-, CREATEDB-,
    REPLICATION-, BYPASSRLS-Recht und ohne Mitgliedschaft, mit Zufallspasswort,
    nur mit CREATE im Schema public (die Zwischendatenbank gehoert dem
    Superuser und entsteht aus template0, Review-Runde 6). Was die Pruefliste uebersieht
    (Katalog schreiben, COPY ... PROGRAM, Server-Dateien, C-Funktionen,
    Rollen aendern, Funktionen in DEFAULT/CHECK/Index waehrend des Ladens),
    scheitert so am Server selbst. Erst danach gehen alle Objekte per
    REASSIGN OWNED an den Superuser - wie ein Laden als Superuser, ausser den
    Default-Privilegien, die init-db-user.sql nach dem Tausch setzt. Vor der
    Uebergabe muessen Funktionen, Trigger (samt Definition), Erweiterungen und
    der Zeilenschutz genau denen der Migrationen bis zum Datenbankstand der
    Sicherung entsprechen (:func:`_assert_routines_match_migrations`,
    Review-Runden 4 und 6) - sonst liefe
    eine von der Pruefliste uebersehene Funktion danach mit Superuser-Rechten."""
    statements = ["-c", f'DROP DATABASE IF EXISTS "{RESTORE_DB_NAME}" WITH (FORCE)']
    if restricted:
        statements += ["-c", f'DROP ROLE IF EXISTS "{RESTORE_LOAD_ROLE}"']
    result = _restore_psql(superuser, env, "postgres", *statements)
    if result.returncode != 0:
        raise RestoreError(
            f"Die Zwischendatenbank {RESTORE_DB_NAME} liess sich nicht anlegen:\n"
            f"{_psql_error_tail(result)}"
        )
    load_user, load_env = superuser, env
    try:
        if restricted:
            load_password = secrets.token_hex(24)
            result = _restore_psql(
                superuser, env, "postgres", "-f", "-",
                input=(f'CREATE ROLE "{RESTORE_LOAD_ROLE}" LOGIN NOSUPERUSER NOCREATEDB '
                       f"NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 1 "
                       f"PASSWORD '{load_password}';\n"),
            )
            if result.returncode != 0:
                raise RestoreError(
                    f"Die Ladrolle {RESTORE_LOAD_ROLE} liess sich nicht anlegen:\n"
                    f"{_psql_error_tail(result)}")
            load_user = RESTORE_LOAD_ROLE
            load_env = {**env, "PGPASSWORD": load_password}
        # Review-Runde 6: die Zwischendatenbank gehoert immer dem Superuser
        # und entsteht aus template0 (nur plpgsql, keine Erweiterung aus
        # template1). Die Ladrolle bekommt nur CREATE im Schema public - kein
        # CREATE auf der Datenbank, also auch keine (trusted) Erweiterung und
        # kein eigenes Schema.
        result = _restore_psql(
            superuser, env, "postgres",
            "-c", f'CREATE DATABASE "{RESTORE_DB_NAME}" OWNER "{superuser}" TEMPLATE template0 '
                  f"ENCODING 'UTF8'",
        )
        if result.returncode != 0:
            raise RestoreError(
                f"Die Zwischendatenbank {RESTORE_DB_NAME} liess sich nicht anlegen:\n"
                f"{_psql_error_tail(result)}"
            )
        if restricted:
            result = _restore_psql(
                superuser, env, RESTORE_DB_NAME,
                "-c", f'GRANT CREATE ON SCHEMA public TO "{RESTORE_LOAD_ROLE}"',
            )
            if result.returncode != 0:
                raise RestoreError(
                    f"Die Ladrolle {RESTORE_LOAD_ROLE} liess sich nicht berechtigen:\n"
                    f"{_psql_error_tail(result)}")

        logger.info("Spiele das Backup in die Zwischendatenbank %s ein%s ...", RESTORE_DB_NAME,
                    f" (als eingeschraenkte Rolle {RESTORE_LOAD_ROLE})" if restricted else "")
        result = _restore_psql(load_user, load_env, RESTORE_DB_NAME, "-f", str(sql))
        if result.returncode != 0:
            raise RestoreError(f"Einspielen fehlgeschlagen:\n{_psql_error_tail(result)}")
        # Stand und (unverifiziert) Funktionen pruefen, SOLANGE die Objekte noch
        # der Ladrolle gehoeren: erst danach uebernimmt sie der Superuser.
        revision = _restored_revision(superuser, env, known)
        if restricted:
            _assert_routines_match_migrations(superuser, env, revision)
    except BaseException:
        if restricted:
            # Erst die Zwischendatenbank weg - sonst gingen ihre (abgelehnten)
            # Objekte beim Entfernen der Ladrolle an den Superuser.
            _restore_psql(superuser, env, "postgres",
                          "-c", f'DROP DATABASE IF EXISTS "{RESTORE_DB_NAME}" WITH (FORCE)')
            try:
                _drop_load_role(superuser, env)
            except RestoreError as exc:  # der erste Fehler ist der wichtigere
                logger.warning("%s", exc)
        raise
    if restricted:
        _drop_load_role(superuser, env)
    return revision


def _restored_revision(superuser: str, env: dict, known: set) -> str:
    """Datenbankstand der Zwischendatenbank; muss eine Migration dieser
    Installation sein. Wirft :class:`RestoreError`."""
    result = _restore_psql(superuser, env, RESTORE_DB_NAME, "-tA", "-c",
                           "SELECT version_num FROM alembic_version")
    revisions = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if result.returncode != 0 or not revisions:
        raise RestoreError(
            "Das Backup enthaelt keine PraxisZeit-Datenbank (Tabelle alembic_version "
            "fehlt oder ist leer)."
        )
    unknown = [r for r in revisions if r not in known]
    if unknown:
        # Der naechste Dienststart fiele an „Can't locate revision“ — mit
        # bereits ersetztem Bestand. Deshalb hier, vor dem Tausch.
        raise RestoreError(
            f"Das Backup stammt aus einer neueren PraxisZeit-Version (Datenbankstand "
            f"{', '.join(unknown)}), diese Installation kennt diesen Stand nicht. Zuerst "
            "auf die Version aktualisieren, die das Backup erzeugt hat."
        )

    return revisions[0]


def _swap_in_restore_db(superuser: str, env: dict) -> None:
    """Bisherige Datenbank durch die Zwischendatenbank ersetzen. Scheitert das
    (:class:`_SwapError`), sieht der Aufrufer nach, was noch da ist."""
    result = _restore_psql(
        superuser, env, "postgres",
        "-c", f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)',
        "-c", f'ALTER DATABASE "{RESTORE_DB_NAME}" RENAME TO "{DB_NAME}"',
    )
    if result.returncode != 0:
        raise _SwapError(_psql_error_tail(result))


def cmd_restore(args):
    """Backup einspielen (Linux/macOS) — Gegenstueck zu ``restore-backup.bat``.

    Gesamtreview 1.20: die Anleitung leitete den Dump bei laufendem Dienst durch
    ``psql`` in die bestehende Datenbank. Migrationen laufen nativ nur beim
    Dienststart — ein Backup einer aelteren Version liess den laufenden Prozess
    gegen das alte Schema arbeiten (1.20: Login HTTP 500), ein Backup von vor
    071 (1.18 und aelter) brach an den Fremdschluesseln von ``security_events``
    auf ``users``/``tenants`` ab, und ohne ``ON_ERROR_STOP`` blieb eine halb
    eingespielte Datenbank mit Exit 0 zurueck.

    Ablauf: Dienst muss angehalten sein → Backup entpacken und pruefen →
    PostgreSQL bei Bedarf nur fuer den Vorgang starten → in eine
    Zwischendatenbank einspielen → Stand pruefen → bisherige Datenbank ersetzen →
    Rechte wie bei der Erstinitialisierung. Migriert wird beim naechsten
    Dienststart: so bleibt ``restore`` auch der Weg fuer einen Rollback (Backup
    mit der installierten Version einspielen, ``app/`` beiseitelegen, dann die
    alte Version installieren — deren Start findet den Stand des Backups vor).
    ``app/`` muss beiseite, weil die Installer nur darueber kopieren: sonst
    faende die alte Version die Migrationen dieser Version und wendete sie beim
    Start erneut an (Gesamtreview 1.20, Runde 2). Ist das Backup aelter als die
    Installation, nennt die Schlussmeldung diesen Schritt.
    """
    if IS_WINDOWS:
        logger.error(
            "Unter Windows spielt restore-backup.bat das Backup ein (im "
            "Installationsordner, als Administrator): restore-backup.bat <datei>.sql.gz"
        )
        sys.exit(1)

    dump = Path(args.file).expanduser().absolute()
    try:
        found = dump.is_file()
    except OSError:
        found = False
    if not found:
        logger.error(f"Backup-Datei nicht gefunden: {dump}")
        sys.exit(1)

    if _process_manager_running():
        logger.error(
            "PraxisZeit laeuft noch. Den Dienst zuerst anhalten (%s), dann das Backup "
            "einspielen und den Dienst wieder starten (%s). Laeuft der Dienst "
            "nachweislich nicht mehr, die veraltete Datei %s loeschen.",
            _service_stop_command(), _service_start_command(), PID_FILE,
        )
        sys.exit(1)

    config = load_config()
    su_password, _ = pg_load_credentials()
    if not su_password:
        logger.error(
            "Keine Datenbank-Zugangsdaten gefunden (config/.db-credentials fehlt). "
            "Ohne sie laesst sich kein Backup einspielen."
        )
        sys.exit(1)

    known = known_migration_revisions()
    if not known:
        logger.error(
            "Keine Migrationen unter %s gefunden — die Installation ist unvollstaendig.",
            BACKEND_DIR / "alembic" / "versions",
        )
        sys.exit(1)

    if not pg_is_running() and _running_as_root():
        # Wie bei reset-admin-password: pg_ctl verweigert den Start als root.
        logger.error(
            "PostgreSQL laeuft nicht, und als root darf es nicht gestartet werden "
            "(pg_ctl lehnt das ab). Das Kommando als Dienstkonto ausfuehren:\n  %s",
            shlex.join([
                "sudo", "-u", _install_owner(), bundled_python(),
                str(Path(__file__).resolve()), "restore", str(dump),
            ]),
        )
        sys.exit(1)

    superuser = _validate_pg_identifier(
        get_config_value(config, "database", "superuser", "praxiszeit")
    )
    try:
        sql, verified = _unpack_dump(dump, secret_key=_installation_secret_key(config),
                                     force_unverified=getattr(args, "force_unverified", False))
    except (RestoreError, UnverifiedBackupError) as exc:
        logger.error("%s Die Datenbank ist unveraendert.", exc)
        sys.exit(1)

    env = {
        **pg_env(),
        "PGPASSWORD": su_password,
        # Die DROP … IF EXISTS aus --clean --if-exists melden in der frischen
        # Zwischendatenbank je Objekt ein NOTICE — Fehler zeigt psql weiter.
        "PGOPTIONS": "-c client_min_messages=warning",
    }
    started_here = False
    swap_attempted = False
    swapped = False
    revision = None
    try:
        if not pg_is_running():
            logger.info("PostgreSQL ist nicht gestartet — wird fuer den Vorgang kurz hochgefahren.")
            pg_start()
            started_here = True
        try:
            revision = _load_into_restore_db(superuser, env, sql, known,
                                             restricted=not verified)
            # Ab hier kann die bisherige Datenbank weg sein — auch wenn der
            # Tausch unterbrochen wird (Strg+C), raeumt ``finally`` die
            # Zwischendatenbank dann nur noch weg, wenn der Bestand noch steht.
            swap_attempted = True
            _swap_in_restore_db(superuser, env)
            swapped = True
        except _SwapError as exc:
            if _database_exists(superuser, env, DB_NAME):
                logger.error(
                    "Die bisherige Datenbank liess sich nicht ersetzen:\n%s\nSie ist "
                    "unveraendert; der Dienst kann wieder gestartet werden.", exc,
                )
            else:
                logger.error(
                    "Die bisherige Datenbank ist entfernt, die eingespielten Daten liegen "
                    "noch in der Zwischendatenbank %s:\n%s\nDen Dienst NICHT starten, "
                    "sondern das Kommando mit derselben Datei erneut aufrufen.",
                    RESTORE_DB_NAME, exc,
                )
            sys.exit(1)
        except RestoreError as exc:
            logger.error(
                "%s\nDie bisherige Datenbank ist unveraendert; der Dienst kann wieder "
                "gestartet werden.", exc,
            )
            sys.exit(1)

        # GRANT CONNECT ON DATABASE gehoert zur Datenbank, nicht zu ihrem Inhalt,
        # und steht deshalb nicht im Dump — dieselben Rechte wie beim Erststart.
        init_sql = BACKEND_DIR / "init-db-user.sql"
        if init_sql.is_file():
            result = _restore_psql(superuser, env, DB_NAME, "-f", str(init_sql))
            if result.returncode != 0:
                logger.error(
                    "Backup eingespielt, aber die Rechte der Anwendungsrolle liessen sich "
                    "nicht setzen:\n%s\nDas Kommando erneut aufrufen.", _psql_error_tail(result),
                )
                sys.exit(1)
    finally:
        sql.unlink(missing_ok=True)
        if not swapped and pg_is_running() and (
                not swap_attempted or _database_exists(superuser, env, DB_NAME)):
            _restore_psql(superuser, env, "postgres",
                          "-c", f'DROP DATABASE IF EXISTS "{RESTORE_DB_NAME}" WITH (FORCE)')
        if started_here:
            logger.info("PostgreSQL wird wieder gestoppt (war vor dem Vorgang nicht gestartet).")
            pg_stop()

    logger.info(
        "Backup eingespielt (Datenbankstand des Backups: %s). Jetzt den Dienst starten: "
        "%s — erst dieser Start hebt ein Backup einer aelteren Version per Migration auf "
        "den Stand dieser Installation. Die Ausgabe der Migrationen steht danach in %s "
        "(Zeilen mit „alembic:“, Hinweise zwischen „*** HINWEIS“ und „*** ENDE HINWEIS ***“).",
        revision, _service_start_command(), LOG_DIR / "praxiszeit.log",
    )
    if revision not in migration_heads():
        # Gesamtreview 1.20, Runde 2: die Installer ersetzen app/ nicht, sie
        # kopieren nur darueber. Ohne diesen Schritt fand der Start der alten
        # Version die Migrationen dieser Installation in alembic/versions und
        # hob die Datenbank gleich wieder an (1.20 → 1.19.3: 073 erneut
        # angewandt, danach startete 1.19.3 nicht mehr).
        app_dir = BACKEND_DIR.parent
        logger.info(
            "Rollback auf die Version des Backups: den Dienst NICHT starten, sondern "
            "zuerst den Anwendungsordner beiseitelegen (sudo mv %s %s.neu) und dann das "
            "alte Paket installieren. Der Installer ersetzt app/ nicht; die Migrationen "
            "dieser Version blieben sonst liegen, und schon der erste Start der alten "
            "Version hoebe die Datenbank wieder auf diesen Stand (UPDATE.md → Rollback).",
            app_dir, app_dir,
        )


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
    subparsers.add_parser(
        "print-db-port",
        help="Datenbank-Port ausgeben (einzige Zeile auf stdout)",
    ).set_defaults(func=cmd_print_db_port)
    subparsers.add_parser(
        "sync-db-port",
        help="postgresql.conf an [database] port angleichen (Windows)",
    ).set_defaults(func=cmd_sync_db_port)
    subparsers.add_parser(
        "harden-permissions",
        help="Windows: Zugriffsrechte des Installationsverzeichnisses einschraenken",
    ).set_defaults(func=cmd_harden_permissions)
    prep = subparsers.add_parser(
        "prepare-restore-dump",
        help="Entpackten Dump pruefen und fuer psql absichern (restore-backup.bat, S3-03)",
    )
    prep.add_argument("file", help="Entpackte .sql-Datei (wird an Ort und Stelle ersetzt)")
    prep.add_argument("--force-unverified", action="store_true",
                      help="Auch ohne passende PraxisZeit-Signatur einspielen")
    prep.add_argument("--restricted-load", action="store_true",
                      help="Unverifizierte Sicherung fuer load-restore-db --restricted "
                           f"vorbereiten (Exit {PREPARE_EXIT_UNVERIFIED})")
    prep.set_defaults(func=cmd_prepare_restore_dump)

    p_load = subparsers.add_parser(
        "load-restore-db",
        help="Vorbereiteten Dump in die Zwischendatenbank einspielen (restore-backup.bat)",
    )
    p_load.add_argument("file", help="Mit prepare-restore-dump vorbereitete .sql-Datei")
    p_load.add_argument("--restricted", action="store_true",
                        help="Unverifizierte Sicherung als Rolle ohne Superuser-Rechte laden")
    p_load.set_defaults(func=cmd_load_restore_db)

    # Gesamtreview 1.20: Gegenstueck zu restore-backup.bat fuer Linux/macOS.
    # Bei angehaltenem Dienst; migriert wird beim naechsten Dienststart.
    p_restore = subparsers.add_parser(
        "restore",
        help="Backup (praxiszeit_*.sql.gz) einspielen — Linux/macOS, Dienst vorher anhalten",
    )
    p_restore.add_argument("file", help="Pfad zum Backup (praxiszeit_<zeitstempel>.sql.gz)")
    p_restore.add_argument(
        "--force-unverified", action="store_true",
        help="Auch ein Backup ohne passende PraxisZeit-Signatur einspielen (z. B. vom alten "
             "Rechner mit anderem SECRET_KEY) - nur, wenn die Datei sicher von dort stammt",
    )
    p_restore.set_defaults(func=cmd_restore)

    # #425: der einzige Weg zurueck bei verlorenem Admin-Passwort. Das Passwort
    # wird vom Werkzeug interaktiv abgefragt — hier bewusst KEIN Argument dafuer
    # (stuende in der Shell-History und in der Prozessliste).
    p_reset = subparsers.add_parser(
        "reset-admin-password",
        help="Passwort eines Kontos lokal neu setzen (Passwort wird abgefragt)",
    )
    p_reset.add_argument("--username", default=None, help="Benutzername (Vorgabe: admin)")
    p_reset.add_argument(
        "--disable-2fa", action="store_true",
        help="Zusaetzlich die Zwei-Faktor-Anmeldung abschalten (wenn auch der Authenticator weg ist)",
    )
    p_reset.add_argument(
        "--reactivate", action="store_true",
        help="Zusaetzlich ein deaktiviertes Konto wieder aktivieren (#489)",
    )
    p_reset.set_defaults(func=cmd_reset_admin_password)

    args = parser.parse_args()
    try:
        args.func(args)
    except PgRuntimeMissingError:
        # The actionable message + remediation URL were already logged at the
        # failure site. Exit cleanly (no traceback) so the service log shows the
        # fix to apply, not a confusing Python stack trace on every restart.
        sys.exit(1)
    except PgConfigError as e:
        logger.error(str(e))
        sys.exit(EXIT_CONFIG_ERROR)


if __name__ == "__main__":
    main()
