"""Admin sub-router: Change Request Management."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, date, timedelta
from app.database import get_db
from app.models import User, TimeEntry, ChangeRequest, ChangeRequestStatus, ChangeRequestType
from app.middleware.auth import require_admin
from app.schemas.change_request import ChangeRequestResponse, ChangeRequestReview
from app.schemas.time_entry import TimeEntryResponse
from app.routers.admin_helpers import _create_audit_log, _enrich_cr_response, _enrich_cr_responses
from app.routers.time_entries import (
    _calculate_daily_net_hours, _calculate_weekly_net_hours,
    MAX_NIGHT_WORKER_DAILY_WARN, MAX_WEEKLY_HOURS_WARN,
)
from app.services.arbzg_utils import is_night_work

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/change-requests/pending-count")
def get_pending_change_request_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return count of pending change requests for admin badge."""
    count = db.query(ChangeRequest).filter(
        ChangeRequest.status == ChangeRequestStatus.PENDING
    ).count()
    return {"count": count}


@router.get("/change-requests", response_model=List[ChangeRequestResponse])
def list_all_change_requests(
    request_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    date_from: Optional[date] = Query(None, description="Filter: created_at >= date_from"),
    date_to: Optional[date] = Query(None, description="Filter: created_at <= date_to"),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all change requests (admin view)."""
    query = db.query(ChangeRequest)
    if request_status:
        try:
            status_enum = ChangeRequestStatus(request_status)
            query = query.filter(ChangeRequest.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungültiger Status: {request_status}")
    if user_id:
        query = query.filter(ChangeRequest.user_id == user_id)
    if date_from:
        query = query.filter(ChangeRequest.created_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        query = query.filter(ChangeRequest.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    requests = query.order_by(ChangeRequest.created_at.desc()).offset(skip).limit(limit).all()
    return _enrich_cr_responses(requests, db)


@router.get("/change-requests/{request_id}", response_model=ChangeRequestResponse)
def get_change_request_admin(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get a specific change request (admin view)."""
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    return _enrich_cr_response(cr, db)


@router.post("/change-requests/{request_id}/review", response_model=ChangeRequestResponse)
def review_change_request(
    request_id: str,
    review: ChangeRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Approve or reject a change request."""
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == request_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    if cr.status != ChangeRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Antrag wurde bereits bearbeitet")

    if review.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Ungültige Aktion (approve/reject)")

    if review.action == "reject":
        cr.status = ChangeRequestStatus.REJECTED
        cr.reviewed_by = current_user.id
        cr.reviewed_at = datetime.now(timezone.utc)
        cr.rejection_reason = review.rejection_reason
        db.commit()
        db.refresh(cr)
        return _enrich_cr_response(cr, db)

    # Approve: validate preconditions BEFORE changing status
    entry = None
    if cr.request_type == ChangeRequestType.CREATE:
        duplicate = db.query(TimeEntry).filter(
            TimeEntry.user_id == cr.user_id,
            TimeEntry.date == cr.proposed_date,
            TimeEntry.start_time == cr.proposed_start_time,
        ).first()
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ein Zeiteintrag mit diesem Datum und dieser Startzeit existiert bereits.",
            )
    elif cr.request_type == ChangeRequestType.UPDATE:
        entry = db.query(TimeEntry).filter(TimeEntry.id == cr.time_entry_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Zeiteintrag nicht mehr vorhanden")
        # Check for unique constraint violation on date/start_time change
        if cr.proposed_date != entry.date or cr.proposed_start_time != entry.start_time:
            dup = db.query(TimeEntry).filter(
                TimeEntry.user_id == cr.user_id,
                TimeEntry.date == cr.proposed_date,
                TimeEntry.start_time == cr.proposed_start_time,
                TimeEntry.id != entry.id,
            ).first()
            if dup:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ein Zeiteintrag mit diesem Datum und dieser Startzeit existiert bereits.",
                )

    elif cr.request_type == ChangeRequestType.DELETE:
        entry = db.query(TimeEntry).filter(TimeEntry.id == cr.time_entry_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Zeiteintrag nicht mehr vorhanden")

    # All preconditions met — now mark as approved
    cr.status = ChangeRequestStatus.APPROVED
    cr.reviewed_by = current_user.id
    cr.reviewed_at = datetime.now(timezone.utc)

    if cr.request_type == ChangeRequestType.CREATE:
        entry = TimeEntry(
            user_id=cr.user_id,
            tenant_id=current_user.tenant_id,
            date=cr.proposed_date,
            start_time=cr.proposed_start_time,
            end_time=cr.proposed_end_time,
            break_minutes=cr.proposed_break_minutes or 0,
            note=cr.proposed_note,
        )
        db.add(entry)
        db.flush()
        cr.time_entry_id = entry.id
        _create_audit_log(
            db, entry.id, cr.user_id, current_user.id,
            action="create", new_entry=entry,
            source="change_request", change_request_id=cr.id,
            tenant_id=current_user.tenant_id,
        )

    elif cr.request_type == ChangeRequestType.UPDATE:
        # entry already fetched in precondition check above
        _create_audit_log(
            db, entry.id, cr.user_id, current_user.id,
            action="update", old_entry=entry,
            new_entry={
                "date": cr.proposed_date,
                "start_time": cr.proposed_start_time,
                "end_time": cr.proposed_end_time,
                "break_minutes": cr.proposed_break_minutes,
                "note": cr.proposed_note,
            },
            source="change_request", change_request_id=cr.id,
            tenant_id=current_user.tenant_id,
        )
        entry.date = cr.proposed_date
        entry.start_time = cr.proposed_start_time
        entry.end_time = cr.proposed_end_time
        entry.break_minutes = cr.proposed_break_minutes if cr.proposed_break_minutes is not None else entry.break_minutes
        if cr.proposed_note is not None:
            entry.note = cr.proposed_note

    elif cr.request_type == ChangeRequestType.DELETE:
        # entry already fetched in precondition check above
        _create_audit_log(
            db, entry.id, cr.user_id, current_user.id,
            action="delete", old_entry=entry,
            source="change_request", change_request_id=cr.id,
            tenant_id=current_user.tenant_id,
        )
        db.delete(entry)

    db.commit()
    db.refresh(cr)

    cr_response = _enrich_cr_response(cr, db)

    # SS6 Abs. 2 / SS14 ArbZG: Warnungen bei CREATE/UPDATE-Genehmigung
    if (
        review.action == "approve"
        and cr.request_type in (ChangeRequestType.CREATE, ChangeRequestType.UPDATE)
        and cr.proposed_start_time
        and cr.proposed_end_time
    ):
        cr_user = db.query(User).filter(User.id == cr.user_id).first()
        if cr_user and not cr_user.exempt_from_arbzg:
            daily_hours_cr = _calculate_daily_net_hours(
                db=db,
                user_id=cr.user_id,
                entry_date=cr.proposed_date,
                start_time=cr.proposed_start_time,
                end_time=cr.proposed_end_time,
                break_minutes=cr.proposed_break_minutes or 0,
            )

            # SS6 Abs. 2: Nachtarbeitnehmer-Tageslimit
            if (
                cr_user.is_night_worker
                and is_night_work(cr.proposed_start_time, cr.proposed_end_time)
                and daily_hours_cr > MAX_NIGHT_WORKER_DAILY_WARN
            ):
                cr_response.warnings.append(
                    f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours_cr:.1f}h). "
                    "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
                )

            # SS14 ArbZG: Wochenarbeitszeit-Warnung (48h)
            weekly = _calculate_weekly_net_hours(
                db=db,
                user_id=cr.user_id,
                entry_date=cr.proposed_date,
                start_time=cr.proposed_start_time,
                end_time=cr.proposed_end_time,
                break_minutes=cr.proposed_break_minutes or 0,
            )
            if weekly > MAX_WEEKLY_HOURS_WARN:
                cr_response.warnings.append(
                    f"§14 ArbZG: Wochenarbeitszeit {weekly:.1f}h überschreitet 48h-Grenze."
                )

    return cr_response
