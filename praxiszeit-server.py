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

BACKEND_DIR = APP_DIR / "backend"
CONFIG_FILE = CONFIG_DIR / "praxiszeit.conf"

IS_WINDOWS = platform.system() == "Windows"

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


def pg_is_running() -> bool:
    """Check if PostgreSQL is running."""
    try:
        result = subprocess.run(
            [str(pg_cmd("pg_isready")), "-h", "localhost", "-p", "5432"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


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

    subprocess.run(init_cmd, check=True)

    # pg_hba.conf starts with trust — pg_setup_database() will set passwords
    # and then harden to scram-sha-256 via pg_harden_auth().

    # Configure postgresql.conf for local-only access
    pg_conf = PG_DATA / "postgresql.conf"
    with open(pg_conf, "a") as f:
        f.write("\n# PraxisZeit configuration\n")
        f.write("listen_addresses = 'localhost'\n")
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

    logger.info("PostgreSQL data directory initialized")


def pg_start():
    """Start PostgreSQL."""
    if pg_is_running():
        logger.info("PostgreSQL is already running")
        return

    logger.info("Starting PostgreSQL...")

    log_file = LOG_DIR / "postgresql-startup.log"

    subprocess.run(
        [
            str(pg_cmd("pg_ctl")),
            "-D", str(PG_DATA),
            "-l", str(log_file),
            "start",
        ],
        check=True,
    )

    # Wait for PostgreSQL to be ready
    for i in range(30):
        if pg_is_running():
            logger.info("PostgreSQL started successfully")
            return
        time.sleep(1)

    logger.error("PostgreSQL failed to start within 30 seconds")
    # Print log for debugging
    if log_file.exists():
        logger.error(f"Startup log:\n{log_file.read_text()[-2000:]}")
    sys.exit(1)


def pg_stop():
    """Stop PostgreSQL gracefully."""
    if not pg_is_running():
        logger.info("PostgreSQL is not running")
        return

    logger.info("Stopping PostgreSQL...")
    subprocess.run(
        [
            str(pg_cmd("pg_ctl")),
            "-D", str(PG_DATA),
            "-m", "fast",
            "stop",
        ],
        check=True,
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
    if IS_WINDOWS:
        try:
            username = os.environ.get("USERNAME", os.environ.get("USER", ""))
            cmds = [["icacls", str(file_path), "/inheritance:r"]]
            if username:
                cmds.append(["icacls", str(file_path), "/grant:r", f"{username}:(R,W)"])
            cmds.append(["icacls", str(file_path), "/grant", "SYSTEM:(R,W)"])
            # F-037: local Administrators group (SID, locale-independent)
            cmds.append(["icacls", str(file_path), "/grant", "*S-1-5-32-544:(R)"])
            for cmd in cmds:
                subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(f"Could not restrict permissions on {file_path.name}")
    else:
        file_path.chmod(0o600)


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

    # Set superuser password
    escaped_su_pw = _escape_pg_password(su_password)
    subprocess.run(
        [psql, "-U", superuser, "-d", "postgres",
         "-c", f"ALTER ROLE {superuser} PASSWORD '{escaped_su_pw}'"],
        check=True, capture_output=True,
    )

    # Check if database exists
    result = subprocess.run(
        [psql, "-U", superuser, "-d", "postgres", "-tAc",
         "SELECT 1 FROM pg_database WHERE datname = 'praxiszeit'"],
        capture_output=True, text=True,
    )

    if "1" not in result.stdout:
        logger.info(f"Creating database '{db_name}'...")
        subprocess.run(
            [psql, "-U", superuser, "-d", "postgres", "-c",
             f"CREATE DATABASE {db_name} OWNER {superuser} ENCODING 'UTF8'"],
            check=True, capture_output=True,
        )

    # Run init-db-user.sql to create app user with RLS permissions
    init_sql = BACKEND_DIR / "init-db-user.sql"
    if init_sql.is_file():
        logger.info("Setting up application database user (RLS)...")
        subprocess.run(
            [psql, "-U", superuser, "-d", db_name, "-f", str(init_sql)],
            check=True, capture_output=True,
        )

    # Set app user password
    escaped_app_pw = _escape_pg_password(app_password)
    subprocess.run(
        [psql, "-U", superuser, "-d", db_name,
         "-c", f"ALTER ROLE {app_user} PASSWORD '{escaped_app_pw}'"],
        check=True, capture_output=True,
    )

    # Store connection strings as environment variables for the backend
    from urllib.parse import quote_plus
    os.environ["DATABASE_URL"] = (
        f"postgresql://{app_user}:{quote_plus(app_password)}@localhost:5432/{db_name}"
    )
    os.environ["DATABASE_URL_MIGRATIONS"] = (
        f"postgresql://{superuser}:{quote_plus(su_password)}@localhost:5432/{db_name}"
    )

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
        capture_output=True,
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

def run_migrations(config: dict):
    """Run Alembic migrations."""
    logger.info("Running database migrations...")

    env = os.environ.copy()
    # DATABASE_URL_MIGRATIONS should already be set

    python = sys.executable
    result = subprocess.run(
        [python, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"Migration failed:\n{result.stderr}")
        sys.exit(1)

    logger.info("Migrations complete")


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

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"praxiszeit_{timestamp}.sql.gz"

    logger.info(f"Creating backup: {backup_file}")

    pg_dump = subprocess.Popen(
        [str(pg_cmd("pg_dump")), "-U", superuser, "-d", "praxiszeit", "-Fc"],
        stdout=subprocess.PIPE,
        env={**os.environ, "PGPASSWORD": su_password} if su_password else os.environ,
    )

    with open(backup_file, "wb") as f:
        import gzip
        with gzip.open(f, "wb") as gz:
            while True:
                chunk = pg_dump.stdout.read(8192)
                if not chunk:
                    break
                gz.write(chunk)

    pg_dump.wait()
    if pg_dump.returncode != 0:
        logger.error("Backup failed!")
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


# --- Main Commands ---

def cmd_start(args):
    """Start PraxisZeit (PostgreSQL + uvicorn)."""
    config = load_config()

    logger.info("=" * 60)
    logger.info("PraxisZeit starting...")
    logger.info("=" * 60)

    # 1. Initialize PostgreSQL if needed
    needs_initdb = not PG_DATA.exists() or not any(PG_DATA.iterdir())
    creds_file = CONFIG_DIR / ".db-credentials"
    needs_setup = needs_initdb or not creds_file.is_file()

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
            from urllib.parse import quote_plus
            superuser = get_config_value(config, "database", "superuser", "praxiszeit")
            app_user = get_config_value(config, "database", "app_user", "praxiszeit_app")
            os.environ["DATABASE_URL"] = (
                f"postgresql://{app_user}:{quote_plus(app_password)}@localhost:5432/praxiszeit"
            )
            os.environ["DATABASE_URL_MIGRATIONS"] = (
                f"postgresql://{superuser}:{quote_plus(su_password)}@localhost:5432/praxiszeit"
            )
        else:
            logger.error("Database credentials not found. Run 'praxiszeit-server init' first.")
            pg_stop()
            sys.exit(1)

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
                sk_file.write_text(sk)
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
                [str(pg_cmd("psql")), "-U", superuser, "-d", "praxiszeit",
                 "-tAc", "SELECT count(*) FROM users WHERE is_active = true"],
                capture_output=True, text=True,
                env={**os.environ, "PGPASSWORD": su_password},
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
    args.func(args)


if __name__ == "__main__":
    main()
