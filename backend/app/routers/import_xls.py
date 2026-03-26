"""
Admin-Endpoints für den XLS-Import von historischen Zeiterfassungsdaten.
POST /api/admin/import/preview  — Datei parsen, Vorschau zurückgeben
POST /api/admin/import/confirm  — Import ausführen
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from app.database import get_db
from app.middleware.auth import require_admin
from app.models import User
from app.services.xls_import_service import (
    ImportedEntry,
    ImportResult,
    parse_xls,
    execute_import,
)

router = APIRouter(
    prefix="/api/admin/import",
    tags=["admin-import"],
    dependencies=[Depends(require_admin)],
)


class PreviewResponse(BaseModel):
    entries: list[ImportedEntry]
    total: int
    conflicts: int
    arbzg_warnings: int


class ConfirmRequest(BaseModel):
    user_id: uuid.UUID
    overwrite: bool
    entries: list[ImportedEntry]
    filename: Optional[str] = "import.xls"


@router.post("/preview", response_model=PreviewResponse)
def preview_import(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """
    Parst die hochgeladene XLS-Datei und gibt eine Vorschau der zu importierenden
    Einträge zurück, inklusive Konflikt- und ArbZG-Warnung-Flags.
    Führt noch KEINEN Import durch.
    """
    # Benutzer verifizieren
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=400, detail="Benutzer nicht gefunden")

    # Size check before reading entire file into memory (5MB limit)
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Datei zu groß (max. 5 MB)")

    try:
        entries = parse_xls(content, user_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PreviewResponse(
        entries=entries,
        total=len(entries),
        conflicts=sum(1 for e in entries if e.has_conflict),
        arbzg_warnings=sum(len(e.arbzg_warnings) for e in entries),
    )


@router.post("/confirm", response_model=ImportResult)
def confirm_import(
    body: ConfirmRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """
    Führt den Import aus. Bei overwrite=True werden Konflikte überschrieben,
    sonst übersprungen. Schreibt Audit-Log-Einträge.
    """
    target_user = db.query(User).filter(User.id == body.user_id).first()
    if not target_user:
        raise HTTPException(status_code=400, detail="Benutzer nicht gefunden")

    return execute_import(
        user_id=body.user_id,
        entries=body.entries,
        overwrite=body.overwrite,
        db=db,
        changed_by_id=current_admin.id,
        filename=body.filename or "import.xls",
        tenant_id=current_admin.tenant_id,
    )
