# backend/app/routers/journal.py
"""Journal-Router: Monatsjournal für Admin und Mitarbeiter."""
import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import User, TimeEntryAuditLog
from app.middleware.auth import get_current_user, require_admin
from app.services import journal_service
from app.services.timezone_service import now_local
from app.schemas.journal import JournalResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["journal"])


@router.get("/admin/users/{user_id}/journal", response_model=JournalResponse)
def get_user_journal(
    user_id: str,
    year: int = Query(default=None, ge=2000, le=2100, description="Jahr (Standard: aktuell)"),
    month: int = Query(default=None, ge=1, le=12, description="Monat 1-12 (Standard: aktuell)"),
    include_health_data: bool = Query(False, description="Krankheitsdaten einschließen (Art. 9 DSGVO)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Monatsjournal eines Mitarbeiters (Admin-Zugriff).

    Fix #6 (Art. 9 DSGVO): SICK-Tage sind standardmäßig maskiert; mit
    ``include_health_data=true`` werden sie ausgeliefert und der Zugriff im
    F-020-Audit (action="health_data_read") protokolliert — konsistent zu
    reports.py.
    """
    now = now_local()
    year = year or now.year
    month = month or now.month

    # F-026: explicit tenant scoping
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user.tenant_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    result = journal_service.get_journal(
        db, user, year, month, include_health_data=include_health_data,
    )

    # F-020: audit the sensitive health-data read (Art. 9) — only persisted after
    # the journal was built successfully (no orphan audit on a failed build).
    if include_health_data:
        logger.info(
            "DSGVO-Datenzugriff: Monatsjournal %s-%02d von %s gelesen von Admin %s",
            year, month, user.username, current_user.username,
        )
        db.add(TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_data_read",
            source="dsgvo",
            new_note=(
                f"Monatsjournal {year}-{month:02d} von {user.username} "
                f"(inkl. Krankheitsdaten) gelesen von Admin: {current_user.username}"
            ),
            tenant_id=current_user.tenant_id,
        ))
        db.commit()

    return result


@router.get("/journal/me", response_model=JournalResponse)
def get_my_journal(
    year: int = Query(default=None, ge=2000, le=2100, description="Jahr (Standard: aktuell)"),
    month: int = Query(default=None, ge=1, le=12, description="Monat 1-12 (Standard: aktuell)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Monatsjournal des aktuell eingeloggten Mitarbeiters."""
    now = now_local()
    year = year or now.year
    month = month or now.month

    return journal_service.get_journal(db, current_user, year, month)
