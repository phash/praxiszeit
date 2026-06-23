"""#213 — DB-Backup-Verwaltung (manuell + geplant), nativ UND Docker.

Eine einheitliche Implementierung fuer beide Deployment-Arten: pg_dump laeuft mit
der **Superuser**-Verbindung ``DATABASE_URL_MIGRATIONS`` (die der Backend-Prozess
in beiden Modi ohnehin kennt — nativ via praxiszeit-server.py, Docker via compose).
Format ist Plain-SQL + gzip mit ``--clean --if-exists`` -> der Restore ist mit
``gunzip -c <datei>.sql.gz | psql`` idempotent in eine bereits befuellte DB
einspielbar (philvdb-Feedback #213: kein manuelles Leeren noetig, Restore war
bisher undokumentiert). KEIN ``-Fc`` (Custom-Format ist bereits komprimiert -> ein
zweites gzip erzeugt ein doppelt komprimiertes, nicht restorebares Artefakt — der
1.8.12-Bug).

pg_dump-Pfad: ``PRAXISZEIT_PG_DUMP`` (nativ setzt den gebuendelten Pfad) sonst
``pg_dump`` aus dem PATH (Docker-Image bringt postgresql-client mit).
Backup-Verzeichnis: SystemSetting ``backup_location`` (Override) sonst
``PRAXISZEIT_BACKUP_DIR`` (nativ) sonst ``/app/backups`` (Docker-Default).
"""
from __future__ import annotations

import gzip
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uuid

from sqlalchemy.orm import Session

from app.models import SystemSetting
from app.services import settings_service

logger = logging.getLogger(__name__)

# Default-Tenant (On-Prem ist single-tenant) — die Backup-Konfiguration ist eine
# globale System-Einstellung und wird hier abgelegt.
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Setting-Keys (global, unter dem Default-Tenant gespeichert — Backup ist eine
# System-Operation ueber die ganze DB, nicht tenant-scoped).
SETTING_ENABLED = "backup_enabled"
SETTING_HOUR = "backup_hour"            # 0..23, Stunde des taeglichen Laufs
SETTING_RETENTION_DAYS = "backup_retention_days"
SETTING_LOCATION = "backup_location"     # optionaler Pfad-Override

DEFAULT_RETENTION_DAYS = 30
DEFAULT_HOUR = 2
_BACKUP_GLOB = "praxiszeit_*.sql.gz"
_FILENAME_RE = re.compile(r"^praxiszeit_\d{8}_\d{6}\.sql\.gz$")


@dataclass
class BackupFile:
    filename: str
    size_bytes: int
    created_at: str  # ISO 8601 (UTC)


@dataclass
class BackupConfig:
    enabled: bool
    hour: int
    retention_days: int
    location: str  # der effektiv genutzte Pfad


# ---------------------------------------------------------------------------
# Konfiguration (SystemSetting, global unter Default-Tenant)
# ---------------------------------------------------------------------------

def _set_setting(db: Session, key: str, value: str) -> None:
    row = (
        db.query(SystemSetting)
        .filter(SystemSetting.key == key, SystemSetting.tenant_id == DEFAULT_TENANT_ID)
        .first()
    )
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value, tenant_id=DEFAULT_TENANT_ID))


def get_backup_dir(db: Session) -> Path:
    """Effektives Backup-Verzeichnis: Setting-Override > Env > Docker-Default."""
    override = (settings_service.get_setting(db, SETTING_LOCATION, tenant_id=DEFAULT_TENANT_ID) or "").strip()
    if override:
        return Path(override)
    env_dir = os.environ.get("PRAXISZEIT_BACKUP_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return Path("/app/backups")


def get_config(db: Session) -> BackupConfig:
    enabled = settings_service.get_bool_setting(db, SETTING_ENABLED, tenant_id=DEFAULT_TENANT_ID)
    try:
        hour = int(settings_service.get_setting(db, SETTING_HOUR, tenant_id=DEFAULT_TENANT_ID) or DEFAULT_HOUR)
    except ValueError:
        hour = DEFAULT_HOUR
    hour = min(23, max(0, hour))
    try:
        retention = int(settings_service.get_setting(db, SETTING_RETENTION_DAYS, tenant_id=DEFAULT_TENANT_ID) or DEFAULT_RETENTION_DAYS)
    except ValueError:
        retention = DEFAULT_RETENTION_DAYS
    retention = max(1, retention)
    return BackupConfig(
        enabled=enabled, hour=hour, retention_days=retention,
        location=str(get_backup_dir(db)),
    )


def update_config(
    db: Session,
    *,
    enabled: Optional[bool] = None,
    hour: Optional[int] = None,
    retention_days: Optional[int] = None,
    location: Optional[str] = None,
) -> BackupConfig:
    if enabled is not None:
        _set_setting(db, SETTING_ENABLED, "true" if enabled else "false")
    if hour is not None:
        _set_setting(db, SETTING_HOUR, str(min(23, max(0, int(hour)))))
    if retention_days is not None:
        _set_setting(db, SETTING_RETENTION_DAYS, str(max(1, int(retention_days))))
    if location is not None:
        loc = location.strip()
        if loc:
            # Schreibprobe (Review 2026-06-23): einen nicht beschreibbaren Pfad
            # ablehnen, statt ihn still zu speichern und erst beim naechsten Backup
            # (nur im Log sichtbar) scheitern zu lassen.
            try:
                probe_dir = Path(loc)
                probe_dir.mkdir(parents=True, exist_ok=True)
                probe = probe_dir / ".praxiszeit-write-test"
                probe.write_text("ok")
                probe.unlink()
            except OSError as e:
                raise BackupError(f"Backup-Verzeichnis '{loc}' ist nicht beschreibbar: {e}") from e
        _set_setting(db, SETTING_LOCATION, loc)
    db.commit()
    return get_config(db)


# ---------------------------------------------------------------------------
# Backup-Dateien
# ---------------------------------------------------------------------------

def list_backups(db: Session) -> list[BackupFile]:
    backup_dir = get_backup_dir(db)
    if not backup_dir.exists():
        return []
    out: list[BackupFile] = []
    for f in backup_dir.glob(_BACKUP_GLOB):
        if not _FILENAME_RE.match(f.name):  # nur exakte praxiszeit_<ts>.sql.gz
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        out.append(BackupFile(
            filename=f.name,
            size_bytes=st.st_size,
            created_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        ))
    # neueste zuerst
    out.sort(key=lambda b: b.filename, reverse=True)
    return out


def resolve_backup_path(db: Session, filename: str) -> Optional[Path]:
    """Path-Traversal-sicher: nur exakte praxiszeit_<ts>.sql.gz-Namen im Backup-Dir."""
    if not _FILENAME_RE.match(filename or ""):
        return None
    candidate = (get_backup_dir(db) / filename).resolve()
    backup_dir = get_backup_dir(db).resolve()
    if backup_dir not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def delete_backup(db: Session, filename: str) -> bool:
    path = resolve_backup_path(db, filename)
    if not path:
        return False
    path.unlink()
    return True


def prune_old_backups(db: Session, retention_days: Optional[int] = None) -> int:
    """Loescht Backups, deren mtime aelter als retention_days ist. Gibt Anzahl zurueck."""
    if retention_days is None:
        retention_days = get_config(db).retention_days
    cutoff = datetime.now(tz=timezone.utc).timestamp() - retention_days * 86400
    removed = 0
    for b in list_backups(db):
        path = resolve_backup_path(db, b.filename)
        if not path:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


# ---------------------------------------------------------------------------
# Backup erstellen (pg_dump --clean --if-exists | gzip)
# ---------------------------------------------------------------------------

def _pg_dump_bin() -> str:
    return os.environ.get("PRAXISZEIT_PG_DUMP", "").strip() or "pg_dump"


def _pg_dump_conn() -> Optional[tuple]:
    """Parst DATABASE_URL_MIGRATIONS in pg_dump-Verbindungsargumente + Passwort.

    Das Passwort wird NICHT in die argv gelegt — es waere sonst via
    /proc/<pid>/cmdline bzw. `ps auxww` von jedem lokalen Prozess lesbar (das ist
    die RLS-umgehende Superuser-Credential). Stattdessen geht es ueber PGPASSWORD
    ins Subprocess-Env (so macht es auch der native Pfad in praxiszeit-server.py).
    Behandelt die native Socket-Form `postgresql://u:p@/db?host=/run/sock`.
    Gibt (conn_args, password|None) zurueck oder None, wenn keine URL gesetzt ist.
    """
    raw = os.environ.get("DATABASE_URL_MIGRATIONS", "").strip()
    if not raw:
        return None
    raw = re.sub(r"^postgresql\+[a-z0-9]+://", "postgresql://", raw)
    from urllib.parse import urlparse, parse_qs, unquote
    p = urlparse(raw)
    qs = parse_qs(p.query)
    host = (qs.get("host", [None])[0]) or p.hostname  # Socket-Dir (Unix) oder TCP-Host
    args: list = []
    if host:
        args += ["-h", unquote(host)]
    if p.port:
        args += ["-p", str(p.port)]
    if p.username:
        args += ["-U", unquote(p.username)]
    args += ["-d", (p.path or "").lstrip("/") or "praxiszeit"]
    password = unquote(p.password) if p.password else None
    return args, password


class BackupError(RuntimeError):
    pass


def create_backup(db: Session) -> BackupFile:
    """Erzeugt ein komprimiertes Plain-SQL-Backup. Wirft BackupError bei Fehlern."""
    conn = _pg_dump_conn()
    if not conn:
        raise BackupError(
            "DATABASE_URL_MIGRATIONS ist nicht gesetzt — ohne Superuser-Verbindung "
            "kann kein vollstaendiges Backup erstellt werden."
        )
    conn_args, password = conn

    backup_dir = get_backup_dir(db)
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BackupError(f"Backup-Verzeichnis nicht beschreibbar: {e}") from e

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"praxiszeit_{timestamp}.sql.gz"
    logger.info("Erstelle Backup: %s", backup_file)

    # '-w': nie nach Passwort fragen (Passwort kommt via PGPASSWORD ins env, NICHT
    # in die argv) -> fail fast statt Haenger im Dienst-Kontext. '--clean
    # --if-exists' -> idempotenter Restore.
    cmd = [_pg_dump_bin(), "-w", "--clean", "--if-exists", *conn_args]
    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    except FileNotFoundError as e:
        raise BackupError(
            f"pg_dump nicht gefunden ({_pg_dump_bin()}). Im Docker-Image fehlt "
            f"postgresql-client; nativ muss PRAXISZEIT_PG_DUMP gesetzt sein."
        ) from e

    write_error: Optional[OSError] = None
    try:
        with gzip.open(backup_file, "wb") as gz:
            # DSGVO Art. 32: das Backup enthält personenbezogene Daten -> nur der
            # Dienst-Owner darf es lesen (gzip.open legt sonst per umask 0o644 an).
            os.chmod(backup_file, 0o600)
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(8192)
                if not chunk:
                    break
                gz.write(chunk)
    except OSError as e:  # z. B. Platte voll
        write_error = e
    finally:
        if proc.stdout:
            proc.stdout.close()

    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.stderr:
        proc.stderr.close()
    rc = proc.wait()

    if write_error is not None or rc != 0 or not backup_file.exists() or backup_file.stat().st_size == 0:
        # Truncated/leeres Backup nie als "fertig" stehen lassen.
        try:
            if backup_file.exists():
                backup_file.unlink()
        except OSError:
            pass
        detail = write_error or stderr.strip() or f"pg_dump Exit {rc}"
        raise BackupError(f"Backup fehlgeschlagen: {detail}")

    st = backup_file.stat()
    logger.info("Backup erstellt: %s (%d Bytes)", backup_file.name, st.st_size)
    return BackupFile(
        filename=backup_file.name,
        size_bytes=st.st_size,
        created_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
    )
