"""#213 — Admin-Sub-Router: DB-Backup-Verwaltung (manuell + geplant, nativ/Docker).

Liste vorhandener Backups, manueller Sofort-Trigger, Zeitplan-/Aufbewahrungs-/
Pfad-Konfiguration und Download/Loeschen. Die eigentliche Backup-Logik (pg_dump
--clean --if-exists | gzip, fuer beide Deployment-Arten) liegt im backup_service.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.middleware.auth import require_admin
from app.models import User
from app.models.security_event import (
    EVENT_BACKUP_CONFIG_CHANGED, EVENT_BACKUP_CREATED, EVENT_BACKUP_DELETED,
    EVENT_BACKUP_DOWNLOADED, SecurityEvent,
)
from app.schemas.user import PasswordConfirmation
from app.services import backup_service

# ⚠️ SaaS-Gate (#100): Ein Backup ist ein Voll-Dump der GESAMTEN DB (alle Tenants,
# inkl. Art.-9-naher Abwesenheitsdaten). Auf On-Prem (single-tenant) gehoert es dem
# Admin — korrekt. VOR dem SaaS-Cutover MUSS dieser Router auf require_superadmin
# umgestellt (oder aus der Tenant-Admin-Oberflaeche entfernt) werden, sonst kann ein
# Tenant-Admin die Daten aller Tenants exportieren.
router = APIRouter(prefix="/api/admin/backups", tags=["admin", "backup"],
                   dependencies=[Depends(require_admin)])


class BackupFileResponse(BaseModel):
    filename: str
    size_bytes: int
    created_at: str


class BackupConfigResponse(BaseModel):
    enabled: bool
    hour: int
    retention_days: int
    location: str
    location_override: str = ""


class BackupOverview(BaseModel):
    config: BackupConfigResponse
    backups: List[BackupFileResponse]


class BackupConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = Field(None, ge=0, le=23)
    retention_days: Optional[int] = Field(None, ge=1, le=3650)
    location: Optional[str] = None


def _log_backup_event(db: Session, current_user: User, event: str, detail: str) -> None:
    """Audit 2026-11-07 (S1-02): jede Aktion an Datenbank-Sicherungen nach
    ``security_events`` (Art. 5 Abs. 2, Art. 32 DSGVO). Eine Sicherung ist ein
    Voll-Dump mit allen Gesundheitsdaten — bisher der einzige Offenlegungsweg
    ohne Spur. ``actor`` = Konto-ID (Muster ``admin_users._log_account_event``),
    kein betroffenes Konto."""
    db.add(SecurityEvent(
        tenant_id=current_user.tenant_id,
        event=event,
        subject_user_id=None,
        actor=f"user:{current_user.id}",
        detail=detail,
    ))
    db.commit()


def _cfg(c) -> BackupConfigResponse:
    return BackupConfigResponse(
        enabled=c.enabled, hour=c.hour, retention_days=c.retention_days, location=c.location,
        location_override=c.location_override,
    )


def _file(b) -> BackupFileResponse:
    return BackupFileResponse(filename=b.filename, size_bytes=b.size_bytes, created_at=b.created_at)


@router.get("", response_model=BackupOverview)
def list_backups(db: Session = Depends(get_db)):
    """Konfiguration + vorhandene Backup-Dateien (neueste zuerst)."""
    return BackupOverview(
        config=_cfg(backup_service.get_config(db)),
        backups=[_file(b) for b in backup_service.list_backups(db)],
    )


@router.post("", response_model=BackupFileResponse, status_code=status.HTTP_201_CREATED)
def create_backup_now(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Sofort ein Backup erstellen (manueller Trigger) + alte gemaess Aufbewahrung loeschen."""
    try:
        result = backup_service.create_backup(db)
    except backup_service.BackupError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    backup_service.prune_old_backups(db)
    _log_backup_event(db, current_user, EVENT_BACKUP_CREATED, f"Sicherung erstellt: {result.filename}")
    return _file(result)


@router.put("/config", response_model=BackupConfigResponse)
def update_config(payload: BackupConfigUpdate, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    """Zeitplan (enabled/hour), Aufbewahrung (Tage) und Pfad-Override setzen."""
    before = backup_service.get_config(db)
    before = (before.enabled, before.hour, before.retention_days, before.location)
    try:
        cfg = backup_service.update_config(
            db,
            enabled=payload.enabled,
            hour=payload.hour,
            retention_days=payload.retention_days,
            location=payload.location,
        )
    except backup_service.BackupError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    changes = []
    if cfg.enabled != before[0]:
        changes.append(f"Zeitplan {'an' if cfg.enabled else 'aus'}")
    if cfg.hour != before[1]:
        changes.append(f"Uhrzeit {before[1]} → {cfg.hour} Uhr")
    if cfg.retention_days != before[2]:
        changes.append(f"Aufbewahrung {before[2]} → {cfg.retention_days} Tage")
    if cfg.location != before[3]:
        changes.append(f"Speicherort {before[3]} → {cfg.location}")
    if changes:
        _log_backup_event(db, current_user, EVENT_BACKUP_CONFIG_CHANGED,
                          "Sicherungs-Einstellungen: " + "; ".join(changes))
    return _cfg(cfg)


@router.post("/{filename}/download")
def download_backup(filename: str, body: PasswordConfirmation, request: Request,
                    db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Eine Backup-Datei herunterladen (path-traversal-sicher im backup_service).

    Audit 2026-11-07 (S1-02): POST mit dem Passwort der handelnden Verwaltung
    (Step-up wie beim 2FA-Einrichten; gleiche Sperre wie der Login). Ein
    unbeaufsichtigtes Admin-Fenster oder ein gestohlenes Access-Token reicht
    damit nicht mehr, um die ganze Datenbank mitzunehmen. Jeder Download steht
    in ``security_events``."""
    from app.routers.auth import confirm_current_password
    confirm_current_password(db, request, current_user, body.password,
                             purpose="Sicherung herunterladen")
    path = backup_service.resolve_backup_path(db, filename)
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup nicht gefunden")
    _log_backup_event(db, current_user, EVENT_BACKUP_DOWNLOADED, f"Sicherung heruntergeladen: {filename}")
    return FileResponse(path, media_type="application/gzip", filename=filename)


@router.delete("/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(filename: str, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    """Eine Backup-Datei loeschen."""
    if not backup_service.delete_backup(db, filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup nicht gefunden")
    _log_backup_event(db, current_user, EVENT_BACKUP_DELETED, f"Sicherung gelöscht: {filename}")
