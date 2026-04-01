from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta, date

from app.database import get_db
from app.models import User, UserRole, PublicHoliday
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.models.system_setting import SystemSetting
from app.middleware.auth import get_current_user
from app.schemas.vacation_request import VacationRequestCreate, VacationRequestResponse
from app.services.calculation_service import count_workdays

router = APIRouter(prefix="/api/vacation-requests", tags=["vacation-requests"])


def get_setting(db: Session, key: str, tenant_id, default: str = "") -> str:
    """Retrieve a tenant-scoped value from system_settings."""
    s = db.query(SystemSetting).filter(
        SystemSetting.key == key,
        SystemSetting.tenant_id == tenant_id,
    ).first()
    return s.value if s else default


def _enrich(vr: VacationRequest, db: Session) -> VacationRequestResponse:
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


@router.post("/", response_model=VacationRequestResponse, status_code=status.HTTP_201_CREATED)
def create_vacation_request(
    data: VacationRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a vacation approval request.
    Only available when vacation_approval_required=true.
    """
    if get_setting(db, "vacation_approval_required", current_user.tenant_id, "false").lower() != "true":
        raise HTTPException(
            status_code=400,
            detail="Urlaubsanträge sind nicht aktiviert. Urlaub direkt über Abwesenheiten buchen.",
        )

    vr = VacationRequest(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        date=data.date,
        end_date=data.end_date,
        hours=data.hours,
        absence_type=data.absence_type or "vacation",
        note=data.note,
        status=VacationRequestStatus.PENDING.value,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return _enrich(vr, db)


@router.get("/", response_model=List[VacationRequestResponse])
def list_my_vacation_requests(
    year: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's vacation requests."""
    query = db.query(VacationRequest).filter(VacationRequest.user_id == current_user.id)
    if year:
        from sqlalchemy import extract
        query = query.filter(extract('year', VacationRequest.date) == year)
    if status:
        query = query.filter(VacationRequest.status == status)
    requests = query.order_by(VacationRequest.created_at.desc()).all()
    return [_enrich(vr, db) for vr in requests]


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_vacation_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Withdraw (delete) a pending vacation request. Only own pending requests."""
    vr = db.query(VacationRequest).filter(VacationRequest.id == request_id).first()
    if not vr:
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")
    if str(vr.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if vr.status != VacationRequestStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Nur offene Anträge können zurückgezogen werden")
    db.delete(vr)
    db.commit()
    return None
