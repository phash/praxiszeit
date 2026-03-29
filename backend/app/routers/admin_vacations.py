"""Admin sub-router: Vacation Request Management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from app.database import get_db
from app.models import User, Absence, PublicHoliday, AbsenceType
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.middleware.auth import require_admin
from app.schemas.vacation_request import VacationRequestResponse, VacationRequestReview
from app.services import calculation_service
from app.services.calculation_service import count_workdays

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _enrich_vr_response(vr: VacationRequest, db: Session) -> VacationRequestResponse:
    resp = VacationRequestResponse.model_validate(vr)
    user = db.query(User).filter(User.id == vr.user_id).first()
    if user:
        resp.user_first_name = user.first_name
        resp.user_last_name = user.last_name
    if vr.reviewed_by:
        reviewer = db.query(User).filter(User.id == vr.reviewed_by).first()
        if reviewer:
            resp.reviewer_first_name = reviewer.first_name
            resp.reviewer_last_name = reviewer.last_name
    # Compute workdays
    end = vr.end_date if vr.end_date else vr.date
    resp.days = count_workdays(db, vr.date, end)
    return resp


@router.get("/vacation-requests", response_model=List[VacationRequestResponse])
def list_all_vacation_requests(
    request_status: Optional[str] = Query(None, alias="status"),
    user_id: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all vacation requests (admin view)."""
    query = db.query(VacationRequest)
    if request_status:
        query = query.filter(VacationRequest.status == request_status)
    if user_id:
        query = query.filter(VacationRequest.user_id == user_id)
    requests = query.order_by(VacationRequest.created_at.desc()).offset(skip).limit(limit).all()
    return [_enrich_vr_response(vr, db) for vr in requests]


@router.post("/vacation-requests/{request_id}/review", response_model=VacationRequestResponse)
def review_vacation_request(
    request_id: str,
    review: VacationRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Approve or reject a vacation request.
    On approve: creates Absence entries for all working days in the range.
    """
    from decimal import Decimal

    vr = db.query(VacationRequest).filter(VacationRequest.id == request_id).first()
    if not vr:
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")
    if vr.status != VacationRequestStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Antrag wurde bereits bearbeitet")

    vr.reviewed_by = current_user.id
    vr.reviewed_at = datetime.now(timezone.utc)

    if review.action == "reject":
        vr.status = VacationRequestStatus.REJECTED.value
        vr.rejection_reason = review.rejection_reason
        db.commit()
        db.refresh(vr)
        return _enrich_vr_response(vr, db)

    # Approve: create absence entries (same logic as create_absence in absences.py)
    target_user = db.query(User).filter(User.id == vr.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    start_date = vr.date
    end_date = vr.end_date if vr.end_date else vr.date

    # Collect affected years for holidays
    years = set()
    cur = start_date
    while cur <= end_date:
        years.add(cur.year)
        cur += timedelta(days=1)

    holidays = set()
    for year in years:
        for h in db.query(PublicHoliday).filter(PublicHoliday.year == year).all():
            holidays.add(h.date)

    # Determine working days
    dates_to_create = []
    cur = start_date
    while cur <= end_date:
        if cur.weekday() < 5 and cur not in holidays:
            dates_to_create.append(cur)
        cur += timedelta(days=1)

    if not dates_to_create:
        raise HTTPException(status_code=400, detail="Keine gültigen Arbeitstage im Zeitraum")

    # Check for existing vacation absences on those days
    for d in dates_to_create:
        existing = db.query(Absence).filter(
            Absence.user_id == target_user.id,
            Absence.date == d,
            Absence.type == AbsenceType.VACATION,
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Es existiert bereits ein Urlaubseintrag am {d.strftime('%d.%m.%Y')}",
            )

    # Check vacation budget (per-day hours via calculation_service)
    vacation_account = calculation_service.get_vacation_account(db, target_user, start_date.year)
    total_hours_needed = sum(
        float(calculation_service.get_daily_target_for_date(target_user, d))
        for d in dates_to_create
    )
    if float(vacation_account['remaining_hours']) - total_hours_needed < 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Urlaubstage überschritten: Verfügbares Guthaben "
                f"({float(vacation_account['remaining_hours']):.1f}h) reicht nicht für die "
                f"beantragten Tage ({float(total_hours_needed):.1f}h)."
            ),
        )

    # Create absence entries
    for d in dates_to_create:
        if getattr(target_user, 'use_daily_schedule', False):
            hours_for_day = float(calculation_service.get_daily_target_for_date(target_user, d))
            if hours_for_day == 0:
                continue
        else:
            hours_for_day = float(vr.hours)

        absence = Absence(
            user_id=target_user.id,
            tenant_id=current_user.tenant_id,
            date=d,
            end_date=vr.end_date,
            type=AbsenceType.VACATION,
            hours=hours_for_day,
            note=vr.note,
        )
        db.add(absence)

    vr.status = VacationRequestStatus.APPROVED.value
    db.commit()
    db.refresh(vr)
    return _enrich_vr_response(vr, db)
