from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.database import get_db
from app.models import User, TimeEntry, ChangeRequest, ChangeRequestType, ChangeRequestStatus
from app.middleware.auth import get_current_user
from app.schemas.change_request import ChangeRequestCreate, ChangeRequestResponse
from app.services.break_validation_service import validate_daily_break

router = APIRouter(prefix="/api/change-requests", tags=["change-requests"])


def _enrich_response(cr: ChangeRequest, db: Session) -> ChangeRequestResponse:
    """Add user names to the change request response."""
    response = ChangeRequestResponse.model_validate(cr)

    user = db.query(User).filter(User.id == cr.user_id).first()
    if user:
        response.user_first_name = user.first_name
        response.user_last_name = user.last_name

    if cr.reviewed_by:
        reviewer = db.query(User).filter(User.id == cr.reviewed_by).first()
        if reviewer:
            response.reviewer_first_name = reviewer.first_name
            response.reviewer_last_name = reviewer.last_name

    return response


@router.post("/", response_model=ChangeRequestResponse, status_code=status.HTTP_201_CREATED)
def create_change_request(
    data: ChangeRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Employee creates a change request for a past day."""

    # Validate request_type
    if data.request_type not in ("create", "update", "delete"):
        raise HTTPException(status_code=400, detail="Ungültiger Antragstyp")

    # For UPDATE and DELETE, time_entry_id is required
    entry = None
    if data.request_type in ("update", "delete"):
        if not data.time_entry_id:
            raise HTTPException(status_code=400, detail="time_entry_id erforderlich für Änderung/Löschung")
        entry = db.query(TimeEntry).filter(TimeEntry.id == data.time_entry_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")
        if entry.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")

    # For CREATE, proposed values are required
    if data.request_type == "create":
        if not all([data.proposed_date, data.proposed_start_time, data.proposed_end_time]):
            raise HTTPException(status_code=400, detail="Datum, Von und Bis sind für neue Einträge erforderlich")
        # Must be for a past day
        if data.proposed_date >= date.today():
            raise HTTPException(status_code=400, detail="Änderungsanträge sind nur für vergangene Tage möglich")

    # For UPDATE, proposed values required and must be for past day
    if data.request_type == "update":
        if not all([data.proposed_date, data.proposed_start_time, data.proposed_end_time]):
            raise HTTPException(status_code=400, detail="Datum, Von und Bis sind erforderlich")

    # For DELETE, entry must be from past
    if data.request_type == "delete" and entry:
        if entry.date >= date.today():
            raise HTTPException(status_code=400, detail="Heutige Einträge können direkt gelöscht werden")

    # Break validation for CREATE and UPDATE
    if data.request_type in ("create", "update") and data.proposed_date:
        break_error = validate_daily_break(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=data.proposed_start_time,
            end_time=data.proposed_end_time,
            break_minutes=data.proposed_break_minutes or 0,
            exclude_entry_id=entry.id if entry else None,
        )
        if break_error:
            raise HTTPException(status_code=400, detail=break_error)

    # Check for duplicate pending requests
    existing_pending = db.query(ChangeRequest).filter(
        ChangeRequest.user_id == current_user.id,
        ChangeRequest.status == ChangeRequestStatus.PENDING,
    )
    if data.time_entry_id:
        existing_pending = existing_pending.filter(
            ChangeRequest.time_entry_id == data.time_entry_id
        )
    if data.request_type == "create" and data.proposed_date:
        existing_pending = existing_pending.filter(
            ChangeRequest.request_type == ChangeRequestType.CREATE,
            ChangeRequest.proposed_date == data.proposed_date,
        )
    existing = existing_pending.first()
    if existing and data.time_entry_id:
        raise HTTPException(status_code=400, detail="Es existiert bereits ein offener Antrag für diesen Eintrag")

    # Create the change request
    cr = ChangeRequest(
        user_id=current_user.id,
        request_type=data.request_type,
        time_entry_id=data.time_entry_id,
        proposed_date=data.proposed_date,
        proposed_start_time=data.proposed_start_time,
        proposed_end_time=data.proposed_end_time,
        proposed_break_minutes=data.proposed_break_minutes,
        proposed_note=data.proposed_note,
        reason=data.reason,
    )

    # Snapshot original values
    if entry:
        cr.original_date = entry.date
        cr.original_start_time = entry.start_time
        cr.original_end_time = entry.end_time
        cr.original_break_minutes = entry.break_minutes
        cr.original_note = entry.note

    db.add(cr)
    db.commit()
    db.refresh(cr)

    return _enrich_response(cr, db)


@router.get("/", response_model=List[ChangeRequestResponse])
def list_change_requests(
    request_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List own change requests (employee view)."""
    query = db.query(ChangeRequest).filter(ChangeRequest.user_id == current_user.id)

    if request_status:
        query = query.filter(ChangeRequest.status == request_status)

    requests = query.order_by(ChangeRequest.created_at.desc()).all()
    return [_enrich_response(cr, db) for cr in requests]


@router.get("/{request_id}", response_model=ChangeRequestResponse)
def get_change_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific change request."""
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    if cr.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    return _enrich_response(cr, db)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_change_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Withdraw a pending change request."""
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    if cr.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if cr.status != ChangeRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Nur offene Anträge können zurückgezogen werden")

    db.delete(cr)
    db.commit()
    return None
