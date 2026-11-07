"""#213 — DB-Backup-Verwaltung (manuell + geplant), nativ UND Docker.

Eine einheitliche Implementierung fuer beide Deployment-Arten: pg_dump laeuft nativ
mit der nur lesenden Rolle ``praxiszeit_backup`` (``DATABASE_URL_BACKUP``, S3-13) —
nativ von praxiszeit-server.py angelegt, unter Docker von ``docker-start.sh``
(``app.core.backup_role``); uvicorn kennt den Superuser in beiden Fällen nicht.
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
import tempfile
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


def _backend_root() -> Path:
    """Wurzel des laufenden Backend-Codes (Docker: ``/app``; nativ:
    ``<install>/app/backend``) — dieselbe Basis, gegen die ``main.py`` einen
    relativen ``FRONTEND_DIR`` auflöst."""
    return Path(__file__).resolve().parent.parent.parent


def _forbidden_backup_roots() -> list[Path]:
    """Verzeichnisse, in denen nie ein Datenbank-Dump liegen darf.

    Sicherheits-Review 2026-10: nativ liefert FastAPI ``FRONTEND_DIR`` ohne Login
    aus (``SPAFallbackMiddleware``/``StaticFiles``). Ein Backup-Ort darin machte
    jeden nächtlichen Dump für jeden im Netz herunterladbar. Ebenfalls gesperrt:
    das Python-Paket ``app`` und nativ das ganze Programmverzeichnis
    ``<install>/app`` (Backend + Frontend; das Update ersetzt es per
    ``rsync --delete``). Docker-Default ``/app/backups`` bleibt erlaubt."""
    from app.config import settings

    frontend = Path(settings.FRONTEND_DIR)
    if not frontend.is_absolute():
        frontend = _backend_root() / settings.FRONTEND_DIR
    roots = [frontend.resolve(), (_backend_root() / "app").resolve()]
    if settings.SERVE_FRONTEND:
        roots.append(_backend_root().parent.resolve())
    return roots


def _is_windows() -> bool:
    return os.name == "nt"


_WIN_DRIVE_REMOTE = 4  # GetDriveTypeW: DRIVE_REMOTE (Netzlaufwerk)


def _win_drive_type(path: str) -> int:
    """GetDriveTypeW für das Laufwerk von ``path`` (nur Windows aufgerufen)."""
    import ctypes  # noqa: PLC0415 — nur unter Windows

    import ntpath  # noqa: PLC0415

    drive = ntpath.splitdrive(path)[0]
    return int(ctypes.windll.kernel32.GetDriveTypeW(drive + "\\"))  # type: ignore[attr-defined]


def _win_public_roots() -> list[str]:
    """Ordner, die unter Windows jedes lokale Konto lesen kann (Kleinbuchstaben,
    ohne abschließenden Trenner)."""
    sysdrive = os.environ.get("SystemDrive", "C:")
    sysroot = os.environ.get("SystemRoot", sysdrive + "\\Windows")
    roots = {
        os.environ.get("PUBLIC", "") or sysdrive + "\\Users\\Public",
        # Fix-Runde (S3-04): das ganze Profil-Verzeichnis. Der Dienst läuft als
        # SYSTEM und hat kein eigenes Profil darunter - jeder Ordner dort gehört
        # einem Konto dieses Rechners (oder ist für alle lesbar).
        sysdrive + "\\Users",
        sysroot,
        sysdrive + "\\Temp",
        # Systemordner anderer Programme: ihre Rechte ändert PraxisZeit nicht.
        os.environ.get("ProgramData", "") or sysdrive + "\\ProgramData",
        os.environ.get("ProgramFiles", "") or sysdrive + "\\Program Files",
        os.environ.get("ProgramFiles(x86)", "") or sysdrive + "\\Program Files (x86)",
        os.environ.get("ProgramW6432", ""),
    }
    return sorted({r.rstrip("\\/").lower() for r in roots if r})


def _default_backup_dir() -> Optional[Path]:
    """Das Standard-Verzeichnis der Installation (nativ ``data/backups`` aus
    ``PRAXISZEIT_BACKUP_DIR``), sonst None."""
    env_dir = os.environ.get("PRAXISZEIT_BACKUP_DIR", "").strip()
    return Path(env_dir) if env_dir else None


def _is_default_backup_dir(path: Path) -> bool:
    default = _default_backup_dir()
    if default is None:
        return False
    try:
        return os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(default))
    except (OSError, ValueError):
        return False


UNC_LOCATION_DETAIL = (
    "Dieser Backup-Ort ist nicht erlaubt: Netzwerkpfade (\\\\Server\\Freigabe) und "
    "Netzlaufwerke sind gesperrt. Die Sicherungen enthalten Gesundheitsdaten und "
    "bleiben auf diesem Rechner; für eine Kopie außer Haus siehe die Anleitung "
    "zur Datensicherung."
)
PUBLIC_LOCATION_DETAIL = (
    "Dieser Backup-Ort ist nicht erlaubt: der Ordner ist für alle Konten dieses "
    "Rechners lesbar (z. B. C:\\Users\\Public) oder ein Systemordner. Bitte einen "
    "eigenen Ordner wählen, z. B. das Standard-Verzeichnis data\\backups."
)
DRIVE_ROOT_LOCATION_DETAIL = (
    "Dieser Backup-Ort ist nicht erlaubt: bitte nicht direkt das Stammverzeichnis "
    "eines Laufwerks wählen, sondern einen Ordner darin."
)


def location_rejection_reason(loc: str) -> Optional[str]:
    """Grund, warum ``loc`` als Backup-Ort gesperrt ist, sonst None.

    Audit 2026-11-07 S3-04: nativ läuft der Dienst unter Windows als SYSTEM.
    Ein UNC-Pfad ließe ihn sofort eine SMB-Verbindung zu einem fremden Rechner
    aufbauen (Anmeldung mit dem Computerkonto), ein öffentlicher Ordner machte
    jeden Dump für alle lesbar. Die rein textuellen Prüfungen laufen VOR jedem
    Dateisystemzugriff (realpath/exists würden den Server bereits kontaktieren).
    """
    raw = (loc or "").strip()
    if raw.startswith(("\\\\", "//")):  # UNC, \\?\ und \\.\ (auf jedem System)
        return UNC_LOCATION_DETAIL
    if _is_windows():
        import ntpath  # noqa: PLC0415 — Windows-Pfadregeln auch im Linux-Test

        drive = ntpath.splitdrive(raw)[0]
        if not drive or len(drive) != 2 or drive[1] != ":":
            return UNC_LOCATION_DETAIL
        try:
            if _win_drive_type(raw) == _WIN_DRIVE_REMOTE:
                return UNC_LOCATION_DETAIL
        except (OSError, AttributeError, ValueError):
            return UNC_LOCATION_DETAIL
        norm = ntpath.normpath(raw).rstrip("\\/").lower()
        default = _default_backup_dir()
        is_default = default is not None and norm == ntpath.normpath(str(default)).rstrip("\\/").lower()
        for root in _win_public_roots():
            if not is_default and (norm == root or norm.startswith(root + "\\")):
                return PUBLIC_LOCATION_DETAIL
    if _is_forbidden_location(raw):
        return FORBIDDEN_LOCATION_DETAIL
    try:
        real = Path(os.path.realpath(raw))
    except (OSError, ValueError):
        return FORBIDDEN_LOCATION_DETAIL
    if real.parent == real:
        return DRIVE_ROOT_LOCATION_DETAIL
    return None


# SIDs statt Namen (deutsches vs. englisches Windows), wie praxiszeit-server.py.
_WIN_SID_SYSTEM = "*S-1-5-18"
_WIN_SID_ADMINISTRATORS = "*S-1-5-32-544"
_WIN_SIDS_REMOVED = ("*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0")  # Benutzer, Auth. Benutzer, Jeder


def _win_restrict_dir_commands(path: Path) -> list[list[str]]:
    """icacls-Aufrufe: nur SYSTEM + Administratoren, Vererbung gekappt (S2-4).

    Erst die Grants, dann die Entfernungen, zuletzt ``/inheritance:r`` — sonst
    könnte der Ordner kurz ohne jeden Eintrag dastehen."""
    p = str(path)
    return [
        ["icacls", p, "/grant:r", f"{_WIN_SID_SYSTEM}:(OI)(CI)F"],
        ["icacls", p, "/grant:r", f"{_WIN_SID_ADMINISTRATORS}:(OI)(CI)F"],
        *[["icacls", p, "/remove:g", sid] for sid in _WIN_SIDS_REMOVED],
        ["icacls", p, "/inheritance:r"],
    ]


def restrict_backup_dir_acl(path: Path) -> bool:
    """Windows: Rechte des Backup-Ordners auf SYSTEM + Administratoren einschränken.

    ``os.open(..., 0o600)`` wirkt unter Windows nicht; ohne das erbte jeder Dump
    die Rechte des gewählten Ordners (S2-4). No-op (True) außerhalb von Windows.
    Neue Dateien im Ordner erben danach nur noch diese Einträge."""
    if not _is_windows():
        return True
    cmds = _win_restrict_dir_commands(path)
    grants, removes, protect = cmds[:2], cmds[2:-1], cmds[-1]
    for cmd in grants:
        if not _run_icacls(cmd):
            return False
    for cmd in removes:
        _run_icacls(cmd)  # ein nicht vorhandener Eintrag ist kein Fehler
    return _run_icacls(protect)


# Fix-Runde (S3-04): Rechte nur an Ordnern ändern, die PraxisZeit selbst
# angelegt hat (oder am Standard-Verzeichnis der Installation). Ein BESTEHENDER
# Ordner, den ein Admin in der Weboberfläche einträgt, wird nur geprüft: der
# Dienst läuft als SYSTEM, ein /inheritance:r + /remove auf einem fremden Baum
# (D:\\Praxis\\Scans, ein Profil, ProgramData) sperrte alle Konten und andere
# Programme aus - eine Wirkung auf Betriebssystem-Ebene aus einer Web-Rolle.
_WIN_ALLOWED_DIR_SIDS = frozenset({"S-1-5-18", "S-1-5-32-544"})  # SYSTEM, Administratoren

_WIN_ACL_REPORT_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "$a=Get-Acl -LiteralPath $env:PZ_ACL_PATH;"
    "'OWNER '+$a.GetOwner([System.Security.Principal.SecurityIdentifier]).Value;"
    "'PROTECTED '+$a.AreAccessRulesProtected;"
    "foreach($r in $a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))"
    "{'RULE '+$r.IdentityReference.Value+' '+$r.AccessControlType}"
)


def _win_acl_report(path: Path) -> Optional[str]:
    """Eigentümer, Vererbung und Einträge des Ordners als Text (SIDs), None bei
    Fehler. Der Pfad geht über die Umgebung, nie in den Befehlstext."""
    sysroot = os.environ.get("SystemRoot", "C:\\Windows")
    ps = os.path.join(sysroot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    try:
        result = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-Command", _WIN_ACL_REPORT_SCRIPT],
            capture_output=True, text=True, errors="replace", timeout=60,
            env={**os.environ, "PZ_ACL_PATH": str(path)},
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("Rechte von %s nicht lesbar: %s", path, e)
        return None
    if result.returncode != 0:
        logger.warning("Rechte von %s nicht lesbar (rc=%s): %s", path, result.returncode,
                       (result.stderr or result.stdout or "").strip())
        return None
    return result.stdout


def win_acl_report_is_private(report: Optional[str]) -> bool:
    """True, wenn nur SYSTEM/Administratoren Zugriff haben, sie Eigentümer sind
    und keine Rechte vom übergeordneten Ordner geerbt werden."""
    if not report:
        return False
    owner = None
    protected = False
    for line in report.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        if parts[0] == "OWNER" and len(parts) == 2:
            owner = parts[1]
        elif parts[0] == "PROTECTED" and len(parts) == 2:
            protected = parts[1].lower() == "true"
        elif parts[0] == "RULE" and len(parts) == 3:
            if parts[2] == "Allow" and parts[1] not in _WIN_ALLOWED_DIR_SIDS:
                return False
    return protected and owner in _WIN_ALLOWED_DIR_SIDS


EXISTING_DIR_ACL_DETAIL = (
    "Dieser Ordner existiert bereits und ist nicht nur für SYSTEM und Administratoren "
    "zugänglich (oder erbt Rechte vom übergeordneten Ordner). PraxisZeit ändert die "
    "Rechte bestehender Ordner nicht. Bitte einen NEUEN Ordnernamen eintragen - "
    "PraxisZeit legt ihn dann mit passenden Rechten an."
)


def _existing_dir_is_private(path: Path) -> bool:
    """Windows: Rechte eines bestehenden Ordners prüfen (nie ändern).
    Außerhalb von Windows True (dort schützt 0600 jede Datei)."""
    if not _is_windows():
        return True
    return win_acl_report_is_private(_win_acl_report(path))


def secure_backup_dir(path: Path, *, created: bool) -> None:
    """Rechte des Backup-Ordners vor dem ersten Byte sicherstellen.

    Selbst angelegt oder Standard-Verzeichnis der Installation → einschränken;
    bestehender, vom Admin gewählter Ordner → nur prüfen. Wirft BackupError."""
    if created or _is_default_backup_dir(path):
        if not restrict_backup_dir_acl(path):
            raise BackupError(ACL_FAILED_DETAIL)
        return
    if not _existing_dir_is_private(path):
        raise BackupError(EXISTING_DIR_ACL_DETAIL)


def _run_icacls(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("icacls %s fehlgeschlagen: %s", " ".join(cmd[2:]), e)
        return False
    if result.returncode != 0:
        logger.warning(
            "icacls %s auf %s fehlgeschlagen (rc=%s): %s", " ".join(cmd[2:]), cmd[1],
            result.returncode, (result.stdout or result.stderr or "").strip(),
        )
        return False
    return True


ACL_FAILED_DETAIL = (
    "Die Zugriffsrechte des Backup-Ordners konnten nicht auf SYSTEM und "
    "Administratoren eingeschränkt werden. Bitte einen anderen Ordner wählen."
)


def _is_forbidden_location(loc: str) -> bool:
    """True, wenn ``loc`` (Symlinks und ``..`` aufgelöst) in einem gesperrten
    Verzeichnis liegt oder es selbst ist."""
    try:
        real = Path(os.path.realpath(loc))
    except (OSError, ValueError):
        return True
    for root in _forbidden_backup_roots():
        if real == root or root in real.parents:
            return True
    return False


FORBIDDEN_LOCATION_DETAIL = (
    "Dieser Backup-Ort ist nicht erlaubt: er liegt im Web-Verzeichnis oder im "
    "Programmverzeichnis von PraxisZeit, von wo Dateien ohne Anmeldung abrufbar "
    "wären oder beim Update gelöscht würden. Bitte einen Ordner außerhalb wählen "
    "(z. B. das Standard-Verzeichnis data/backups)."
)


def get_backup_dir(db: Session) -> Path:
    """Effektives Backup-Verzeichnis: Setting-Override > Env > Docker-Default.

    Ein gespeicherter Override, der (z. B. aus der Zeit vor der Prüfung in
    ``update_config``) in einem gesperrten Verzeichnis liegt, wird ignoriert."""
    override = (settings_service.get_setting(db, SETTING_LOCATION, tenant_id=DEFAULT_TENANT_ID) or "").strip()
    if override:
        if location_rejection_reason(override) is None:
            return Path(override)
        logger.warning(
            "Backup-Ort %r ist gesperrt (Web-/Programmverzeichnis, Netzwerkpfad oder "
            "öffentlicher Ordner) und wird ignoriert", override
        )
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
        reason = location_rejection_reason(loc) if loc else None
        if reason:
            raise BackupError(reason)
        if loc:
            # Schreibprobe (Review 2026-06-23): einen nicht beschreibbaren Pfad
            # ablehnen, statt ihn still zu speichern und erst beim naechsten Backup
            # (nur im Log sichtbar) scheitern zu lassen.
            try:
                probe_dir = Path(loc)
                # KEIN mkdir(parents=True): ein Admin könnte sonst per Setting
                # beliebige Verzeichnisbäume auf dem Host anlegen lassen (Review:
                # Privilege-Surface auf Native-Installs). Das übergeordnete
                # Verzeichnis muss existieren; nur das letzte Segment wird angelegt.
                created = False
                if not probe_dir.exists():
                    if not probe_dir.parent.is_dir():
                        raise BackupError(
                            f"Übergeordnetes Verzeichnis von '{loc}' existiert nicht — "
                            "bitte den Pfad manuell anlegen."
                        )
                    probe_dir.mkdir()
                    created = True
                # Windows: Rechte VOR dem ersten Byte (S2-4) - eingeschränkt nur
                # an einem eben angelegten Ordner, ein bestehender wird geprüft.
                secure_backup_dir(probe_dir, created=created)
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
    backup_dir = get_backup_dir(db)
    candidate = (backup_dir / filename).resolve()
    if backup_dir.resolve() not in candidate.parents:
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


def _backup_db_url() -> str:
    """Verbindung fuer pg_dump: die nur lesende Rolle ``praxiszeit_backup``
    (``DATABASE_URL_BACKUP``, Audit 2026-11-07 S3-13 - der Webprozess kennt den
    Superuser weder nativ noch unter Docker). ``DATABASE_URL_MIGRATIONS`` nur
    noch als Rueckfall fuer Aufrufe ausserhalb von uvicorn (Tests, Werkzeuge)."""
    return (os.environ.get("DATABASE_URL_BACKUP", "").strip()
            or os.environ.get("DATABASE_URL_MIGRATIONS", "").strip())


def _pg_dump_conn() -> Optional[tuple]:
    """Parst DATABASE_URL_MIGRATIONS in pg_dump-Verbindungsargumente + Passwort.

    Das Passwort wird NICHT in die argv gelegt — es waere sonst via
    /proc/<pid>/cmdline bzw. `ps auxww` von jedem lokalen Prozess lesbar (das ist
    die RLS-umgehende Superuser-Credential). Stattdessen geht es ueber PGPASSWORD
    ins Subprocess-Env (so macht es auch der native Pfad in praxiszeit-server.py).
    Behandelt die native Socket-Form `postgresql://u:p@/db?host=/run/sock`.
    Gibt (conn_args, password|None) zurueck oder None, wenn keine URL gesetzt ist.
    """
    raw = _backup_db_url()
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


def _pg_require_auth() -> Optional[str]:
    """``require_auth`` aus DATABASE_URL_MIGRATIONS (nativ Windows gesetzt)."""
    raw = _backup_db_url()
    if not raw:
        return None
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(raw).query)
    value = (qs.get("require_auth", [None])[0] or "").strip()
    return value or None


class BackupError(RuntimeError):
    pass


# S2-6: Grenzen fuer den pg_dump-Lauf.
_PG_DUMP_LOCK_WAIT = "300s"        # max. Warten auf eine Tabellensperre
_PG_DUMP_EXIT_TIMEOUT = 120        # s zwischen Ende von stdout und Prozessende
_PG_DUMP_STDERR_TAIL = 4000        # Bytes der Fehlermeldung in der BackupError


def create_backup(db: Session) -> BackupFile:
    """Erzeugt ein komprimiertes Plain-SQL-Backup. Wirft BackupError bei Fehlern."""
    conn = _pg_dump_conn()
    if not conn:
        raise BackupError(
            "Keine Datenbank-Verbindung fuer Sicherungen (DATABASE_URL_BACKUP bzw. "
            "DATABASE_URL_MIGRATIONS ist nicht gesetzt) — Details im Protokoll des Dienstes."
        )
    conn_args, password = conn

    backup_dir = get_backup_dir(db)
    created = not backup_dir.exists()
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BackupError(f"Backup-Verzeichnis nicht beschreibbar: {e}") from e
    # Windows: jeder Dump erbt die Rechte des Ordners (0o600 wirkt dort nicht).
    # Kein Dump in einen Ordner, der für andere Konten lesbar ist; Rechte
    # geändert werden nur an selbst angelegten Ordnern und am Standard-Ordner.
    secure_backup_dir(backup_dir, created=created)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"praxiszeit_{timestamp}.sql.gz"
    logger.info("Erstelle Backup: %s", backup_file)

    # '-w': nie nach Passwort fragen (Passwort kommt via PGPASSWORD ins env, NICHT
    # in die argv) -> fail fast statt Haenger im Dienst-Kontext. '--clean
    # --if-exists' -> idempotenter Restore.
    # Audit 2026-11-07 (S2-6): '--lock-wait-timeout' -> eine fremde Tabellensperre
    # laesst den (geplanten) Lauf nicht endlos haengen.
    cmd = [_pg_dump_bin(), "-w", "--clean", "--if-exists",
           f"--lock-wait-timeout={_PG_DUMP_LOCK_WAIT}", *conn_args]
    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password
    require_auth = _pg_require_auth()
    if require_auth:
        # S3-07: pg_dump darf das Passwort nur per SCRAM preisgeben, nie im
        # Klartext an einen Server, der sich an den freien Port gehängt hat.
        env["PGREQUIREAUTH"] = require_auth
    # Audit 2026-11-07 (S2-6): stderr in eine temporaere DATEI statt in eine
    # Pipe. Mit zwei Pipes las der Elternprozess nur stdout bis zum Ende —
    # schrieb pg_dump vorher mehr als den Pipe-Puffer (~64 KB) an Warnungen nach
    # stderr, blockierten beide Prozesse fuer immer (Deadlock).
    errfile = tempfile.TemporaryFile()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errfile, env=env)
    except FileNotFoundError as e:
        errfile.close()
        raise BackupError(
            f"pg_dump nicht gefunden ({_pg_dump_bin()}). Im Docker-Image fehlt "
            f"postgresql-client; nativ muss PRAXISZEIT_PG_DUMP gesetzt sein."
        ) from e

    write_error: Optional[OSError] = None
    # Signaturzeile am Ende (Fix-Runde S3-03): ein Restore spielt eine Datei
    # ohne passende Signatur nur mit --force-unverified ein.
    from app.config import settings
    from app.core.backup_mac import BackupMac

    signer = BackupMac(settings.SECRET_KEY)
    try:
        # DSGVO Art. 32: das Backup enthält personenbezogene Daten -> ATOMAR nur
        # Owner-lesbar anlegen (os.open mit 0o600), nicht erst gzip.open(umask 0644)
        # + nachträgliches chmod (dazwischen kurz world-readable).
        _fd = os.open(backup_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(_fd, "wb") as _raw, gzip.GzipFile(fileobj=_raw, mode="wb") as gz:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(8192)
                if not chunk:
                    break
                gz.write(chunk)
                signer.update(chunk)
            gz.write(signer.trailer())
    except OSError as e:  # z. B. Platte voll
        write_error = e
    finally:
        if proc.stdout:
            proc.stdout.close()

    try:
        rc = proc.wait(timeout=_PG_DUMP_EXIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = proc.wait()
    errfile.seek(0)
    # Nur das Ende — eine Fehlermeldung steht am Schluss, Warnungen davor.
    stderr = errfile.read()[-_PG_DUMP_STDERR_TAIL:].decode("utf-8", "replace")
    errfile.close()

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
