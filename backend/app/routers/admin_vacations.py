"""Admin sub-router: Vacation Request Management."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from app.database import get_db
from app.models import User, Absence, PublicHoliday, AbsenceType, TimeEntry
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.middleware.auth import require_admin
from app.schemas.vacation_request import VacationRequestResponse, VacationRequestReview
from app.services import calculation_service
from app.services.calculation_service import count_workdays
from app.routers.admin_helpers import _create_audit_log

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _enrich_vr_response(vr: VacationRequest, db: Session) -> VacationRequestResponse:
    """Add user names to the vacation request response (single item)."""
    return _enrich_vr_responses([vr], db)[0]


def _enrich_vr_responses(vrs: list, db: Session) -> list[VacationRequestResponse]:
    """Add user names to vacation request responses (batch, single query)."""
    if not vrs:
        return []
    user_ids = set()
    for vr in vrs:
        user_ids.add(vr.user_id)
        if vr.reviewed_by:
            user_ids.add(vr.reviewed_by)
    user_ids.discard(None)
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {u.id: u for u in users}

    results = []
    for vr in vrs:
        resp = VacationRequestResponse.model_validate(vr)
        user = user_map.get(vr.user_id)
        if user:
            resp.user_first_name = user.first_name
            resp.user_last_name = user.last_name
        if vr.reviewed_by:
            reviewer = user_map.get(vr.reviewed_by)
            if reviewer:
                resp.reviewer_first_name = reviewer.first_name
                resp.reviewer_last_name = reviewer.last_name
        # Compute workdays
        end = vr.end_date if vr.end_date else vr.date
        resp.days = count_workdays(db, vr.date, end)
        results.append(resp)
    return results


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
    return _enrich_vr_responses(requests, db)


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

    # Determine absence type from the request
    absence_type_str = vr.absence_type or "vacation"
    try:
        absence_type = AbsenceType(absence_type_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Abwesenheitstyp: {absence_type_str}",
        )

    start_date = vr.date
    end_date = vr.end_date if vr.end_date else vr.date

    # Validate against employment period
    if target_user.first_work_day and start_date < target_user.first_work_day:
        raise HTTPException(
            status_code=400,
            detail=f"Datum liegt vor dem ersten Arbeitstag ({target_user.first_work_day.strftime('%d.%m.%Y')})",
        )
    if target_user.last_work_day and end_date > target_user.last_work_day:
        raise HTTPException(
            status_code=400,
            detail=f"Datum liegt nach dem letzten Arbeitstag ({target_user.last_work_day.strftime('%d.%m.%Y')})",
        )

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

    # Check for existing absences of the same type on those days
    for d in dates_to_create:
        existing = db.query(Absence).filter(
            Absence.user_id == target_user.id,
            Absence.date == d,
            Absence.type == absence_type,
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Es existiert bereits ein {absence_type_str}-Eintrag am {d.strftime('%d.%m.%Y')}",
            )

    # Check vacation budget only for VACATION type (per year for cross-year requests)
    if absence_type == AbsenceType.VACATION:
        dates_by_year = {}
        for d in dates_to_create:
            dates_by_year.setdefault(d.year, []).append(d)
        for check_year, year_dates in dates_by_year.items():
            vacation_account = calculation_service.get_vacation_account(db, target_user, check_year)
            year_hours_needed = sum(
                float(calculation_service.get_daily_target_for_date(
                    target_user, d,
                    weekly_hours=calculation_service.get_weekly_hours_for_date(db, target_user, d),
                ))
                for d in year_dates
            )
            if float(vacation_account['remaining_hours']) - year_hours_needed < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Nicht genügend Urlaubstage für {check_year} ({vacation_account['remaining_days']:.1f} Tage verfügbar)",
                )

    # Delete existing time entries on the affected dates (Fall 2: overwrite)
    # Log deletions for audit trail, then bulk-delete with tenant scope
    existing_entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == target_user.id,
        TimeEntry.tenant_id == current_user.tenant_id,
        TimeEntry.date.in_(dates_to_create),
    ).all()
    for entry in existing_entries:
        _create_audit_log(
            db, entry.id, target_user.id, current_user.id,
            action="delete", old_entry=entry,
            source="absence_request_approval",
            tenant_id=current_user.tenant_id,
        )
        db.delete(entry)

    # Create absence entries
    for d in dates_to_create:
        if getattr(target_user, 'use_daily_schedule', False):
            weekly = calculation_service.get_weekly_hours_for_date(db, target_user, d)
            hours_for_day = float(calculation_service.get_daily_target_for_date(target_user, d, weekly_hours=weekly))
            if hours_for_day == 0:
                continue
        else:
            hours_for_day = float(vr.hours)

        absence = Absence(
            user_id=target_user.id,
            tenant_id=current_user.tenant_id,
            date=d,
            end_date=vr.end_date,
            type=absence_type,
            hours=hours_for_day,
            note=vr.note,
        )
        db.add(absence)

    vr.status = VacationRequestStatus.APPROVED.value
    db.commit()
    db.refresh(vr)
    return _enrich_vr_response(vr, db)
