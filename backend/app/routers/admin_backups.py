"""#213 — Admin-Sub-Router: DB-Backup-Verwaltung (manuell + geplant, nativ/Docker).

Liste vorhandener Backups, manueller Sofort-Trigger, Zeitplan-/Aufbewahrungs-/
Pfad-Konfiguration und Download/Loeschen. Die eigentliche Backup-Logik (pg_dump
--clean --if-exists | gzip, fuer beide Deployment-Arten) liegt im backup_service.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import User
from app.middleware.auth import require_admin
from app.services import backup_service

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


class BackupOverview(BaseModel):
    config: BackupConfigResponse
    backups: List[BackupFileResponse]


class BackupConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = Field(None, ge=0, le=23)
    retention_days: Optional[int] = Field(None, ge=1, le=3650)
    location: Optional[str] = None


def _cfg(c) -> BackupConfigResponse:
    return BackupConfigResponse(
        enabled=c.enabled, hour=c.hour, retention_days=c.retention_days, location=c.location,
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
def create_backup_now(db: Session = Depends(get_db)):
    """Sofort ein Backup erstellen (manueller Trigger) + alte gemaess Aufbewahrung loeschen."""
    try:
        result = backup_service.create_backup(db)
    except backup_service.BackupError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    backup_service.prune_old_backups(db)
    return _file(result)


@router.put("/config", response_model=BackupConfigResponse)
def update_config(payload: BackupConfigUpdate, db: Session = Depends(get_db)):
    """Zeitplan (enabled/hour), Aufbewahrung (Tage) und Pfad-Override setzen."""
    cfg = backup_service.update_config(
        db,
        enabled=payload.enabled,
        hour=payload.hour,
        retention_days=payload.retention_days,
        location=payload.location,
    )
    return _cfg(cfg)


@router.get("/{filename}/download")
def download_backup(filename: str, db: Session = Depends(get_db)):
    """Eine Backup-Datei herunterladen (path-traversal-sicher im backup_service)."""
    path = backup_service.resolve_backup_path(db, filename)
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup nicht gefunden")
    return FileResponse(path, media_type="application/gzip", filename=filename)


@router.delete("/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(filename: str, db: Session = Depends(get_db)):
    """Eine Backup-Datei loeschen."""
    if not backup_service.delete_backup(db, filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup nicht gefunden")
