# backend/app/routers/journal.py
"""Journal-Router: Monatsjournal für Admin und Mitarbeiter."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import User
from app.middleware.auth import get_current_user, require_admin
from app.services import journal_service
from app.schemas.journal import JournalResponse

router = APIRouter(prefix="/api", tags=["journal"])


@router.get("/admin/users/{user_id}/journal", response_model=JournalResponse)
def get_user_journal(
    user_id: str,
    year: int = Query(default=None, ge=2000, le=2100, description="Jahr (Standard: aktuell)"),
    month: int = Query(default=None, ge=1, le=12, description="Monat 1-12 (Standard: aktuell)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Monatsjournal eines Mitarbeiters (Admin-Zugriff)."""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    return journal_service.get_journal(db, user, year, month)


@router.get("/journal/me", response_model=JournalResponse)
def get_my_journal(
    year: int = Query(default=None, ge=2000, le=2100, description="Jahr (Standard: aktuell)"),
    month: int = Query(default=None, ge=1, le=12, description="Monat 1-12 (Standard: aktuell)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Monatsjournal des aktuell eingeloggten Mitarbeiters."""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    return journal_service.get_journal(db, current_user, year, month)
