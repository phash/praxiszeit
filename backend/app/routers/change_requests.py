from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.services.timezone_service import today_local
from app.database import get_db
from app.models import User, TimeEntry, ChangeRequest, ChangeRequestType, ChangeRequestStatus, UserRole, Absence, AbsenceType
from app.middleware.auth import get_current_user
from app.schemas.change_request import ChangeRequestCreate, ChangeRequestResponse
from app.services.break_validation_service import validate_daily_break
from app.routers.time_entries import (
    _calculate_daily_net_hours,
    MAX_DAILY_HOURS_HARD, MAX_NIGHT_WORKER_DAILY_WARN,
)
from app.services.arbzg_utils import is_night_work

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

    # --- Absence CR branch ---
    if data.entry_kind == "absence":
        # For UPDATE/DELETE: absence_id required, fetch and validate ownership
        absence = None
        if data.request_type in ("update", "delete"):
            if not data.absence_id:
                raise HTTPException(status_code=400, detail="absence_id erforderlich für Absence-Änderung/Löschung")
            absence = db.query(Absence).filter(Absence.id == data.absence_id).first()
            if not absence:
                raise HTTPException(status_code=404, detail="Abwesenheit nicht gefunden")
            if absence.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Zugriff verweigert")

        # For CREATE/UPDATE: validate required fields
        if data.request_type in ("create", "update"):
            if not data.proposed_absence_type:
                raise HTTPException(status_code=400, detail="Abwesenheitstyp erforderlich")
            if not data.proposed_date:
                raise HTTPException(status_code=400, detail="Datum erforderlich")
            if data.proposed_date >= today_local():
                raise HTTPException(status_code=400, detail="Änderungsanträge sind nur für vergangene Tage möglich")
            # Validate absence type is valid
            try:
                AbsenceType(data.proposed_absence_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Ungültiger Abwesenheitstyp: {data.proposed_absence_type}")
            # Need either hours or start/end time
            if data.proposed_absence_hours is None and not (data.proposed_start_time and data.proposed_end_time):
                raise HTTPException(status_code=400, detail="Stunden oder Start-/Endzeit erforderlich")
            if data.proposed_start_time and data.proposed_end_time:
                if data.proposed_start_time >= data.proposed_end_time:
                    raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

        # For DELETE: validate absence exists (already fetched above)
        if data.request_type == "delete" and absence:
            if absence.date >= today_local():
                raise HTTPException(status_code=400, detail="Heutige Einträge können direkt gelöscht werden")

        # Create the CR
        cr = ChangeRequest(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            request_type=data.request_type,
            entry_kind="absence",
            absence_id=data.absence_id if data.request_type in ("update", "delete") else None,
            proposed_date=data.proposed_date,
            proposed_start_time=data.proposed_start_time,
            proposed_end_time=data.proposed_end_time,
            proposed_absence_type=data.proposed_absence_type,
            proposed_absence_hours=data.proposed_absence_hours,
            reason=data.reason,
        )

        # Snapshot original values for update/delete
        if data.request_type in ("update", "delete") and absence:
            cr.original_date = absence.date
            cr.original_absence_type = absence.type.value
            cr.original_absence_hours = float(absence.hours)
            cr.original_start_time = absence.start_time
            cr.original_end_time = absence.end_time

        db.add(cr)
        db.commit()
        db.refresh(cr)
        return _enrich_response(cr, db)

    # --- TimeEntry CR branch (existing logic) ---

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
        if data.proposed_date >= today_local():
            raise HTTPException(status_code=400, detail="Änderungsanträge sind nur für vergangene Tage möglich")
        # Arbeitszeitraum-Prüfung (I1)
        if current_user.first_work_day and data.proposed_date < current_user.first_work_day:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datum liegt vor dem ersten Arbeitstag")
        if current_user.last_work_day and data.proposed_date > current_user.last_work_day:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datum liegt nach dem letzten Arbeitstag")

    # For UPDATE, proposed values required and must be for past day
    if data.request_type == "update":
        if not all([data.proposed_date, data.proposed_start_time, data.proposed_end_time]):
            raise HTTPException(status_code=400, detail="Datum, Von und Bis sind erforderlich")
        if data.proposed_date >= today_local():
            raise HTTPException(status_code=400, detail="Änderungsanträge sind nur für vergangene Tage möglich")
        # Arbeitszeitraum-Prüfung (I1)
        if data.proposed_date:
            if current_user.first_work_day and data.proposed_date < current_user.first_work_day:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datum liegt vor dem ersten Arbeitstag")
            if current_user.last_work_day and data.proposed_date > current_user.last_work_day:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datum liegt nach dem letzten Arbeitstag")

    # Time range validation for CREATE and UPDATE
    if data.request_type in ("create", "update") and data.proposed_start_time and data.proposed_end_time:
        if data.proposed_start_time >= data.proposed_end_time:
            raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

    # For DELETE, entry must be from past
    if data.request_type == "delete" and entry:
        if entry.date >= today_local():
            raise HTTPException(status_code=400, detail="Heutige Einträge können direkt gelöscht werden")

    # Break validation for CREATE and UPDATE (§18-Ausnahme: exempt_from_arbzg überspringt §3/§4)
    if not current_user.exempt_from_arbzg and data.request_type in ("create", "update") and data.proposed_date:
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

        # §3 ArbZG: daily hours hard limit
        daily_hours = _calculate_daily_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=data.proposed_start_time,
            end_time=data.proposed_end_time,
            break_minutes=data.proposed_break_minutes or 0,
            exclude_entry_id=entry.id if entry else None,
        )
        if daily_hours > MAX_DAILY_HOURS_HARD:
            raise HTTPException(
                status_code=422,
                detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
            )

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
        tenant_id=current_user.tenant_id,
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

    response = _enrich_response(cr, db)

    # §6 Abs. 2 ArbZG: Warnung für Nachtarbeitnehmer (§18-Ausnahme beachten)
    if (
        not current_user.exempt_from_arbzg
        and data.request_type in ("create", "update")
        and data.proposed_start_time
        and data.proposed_end_time
    ):
        daily_hours_check = _calculate_daily_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=data.proposed_start_time,
            end_time=data.proposed_end_time,
            break_minutes=data.proposed_break_minutes or 0,
            exclude_entry_id=entry.id if entry else None,
        )
        if (
            current_user.is_night_worker
            and is_night_work(data.proposed_start_time, data.proposed_end_time)
            and daily_hours_check > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            response.warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours_check:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    return response


@router.get("/", response_model=List[ChangeRequestResponse])
def list_change_requests(
    request_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List own change requests (employee view)."""
    query = db.query(ChangeRequest).filter(ChangeRequest.user_id == current_user.id)

    if request_status:
        try:
            status_enum = ChangeRequestStatus(request_status)
            query = query.filter(ChangeRequest.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Status: {request_status}"
            )

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
    if cr.user_id != current_user.id and current_user.role != UserRole.ADMIN:
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
