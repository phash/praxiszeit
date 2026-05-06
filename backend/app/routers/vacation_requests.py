from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.services.date_filters import date_in_year, date_in_month
from typing import List, Optional
from datetime import datetime, timezone, timedelta, date

from app.database import get_db
from app.models import User, UserRole, PublicHoliday, Absence, AbsenceType, TimeEntryAuditLog
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.models.system_setting import SystemSetting
from app.middleware.auth import get_current_user
from app.schemas.vacation_request import VacationRequestCreate, VacationRequestResponse
from app.services.calculation_service import count_workdays
from app.services.timezone_service import today_local

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


def _format_vacation_request_audit_text(vr: VacationRequest) -> str:
    """Compact one-line representation of a vacation request for audit logs.

    Used as `old_note` / `new_note` payload on edit/cancel events. Note is
    truncated to 200 chars to keep audit-log queries cheap.
    """
    end = vr.end_date if vr.end_date else vr.date
    note = (vr.note or "").replace("\n", " ").strip()[:200]
    text = (
        f"vacation_request {vr.id} | "
        f"{vr.date}..{end} | "
        f"{vr.absence_type or 'vacation'} | "
        f"{float(vr.hours):.2f}h"
    )
    if note:
        text += f" | {note}"
    return text


@router.post("/", response_model=VacationRequestResponse, status_code=status.HTTP_201_CREATED)
def create_vacation_request(
    data: VacationRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a vacation approval request.
    Only available when vacation_approval_required=true.

    F-045: validation parity with create_absence — reject invalid ranges,
    past dates, first/last_work_day violations and duplicate-pending
    requests up front so they don't reach the admin review queue as
    garbage.
    """
    if get_setting(db, "vacation_approval_required", current_user.tenant_id, "false").lower() != "true":
        raise HTTPException(
            status_code=400,
            detail="Urlaubsanträge sind nicht aktiviert. Urlaub direkt über Abwesenheiten buchen.",
        )

    # 1. date range sanity
    start_date = data.date
    end_date = data.end_date if data.end_date else data.date
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="Enddatum muss nach dem Startdatum liegen",
        )

    # 2. first_work_day / last_work_day (parity with create_absence)
    if current_user.first_work_day and start_date < current_user.first_work_day:
        raise HTTPException(
            status_code=400,
            detail="Datum liegt vor dem ersten Arbeitstag",
        )
    if current_user.last_work_day and end_date > current_user.last_work_day:
        raise HTTPException(
            status_code=400,
            detail="Datum liegt nach dem letzten Arbeitstag",
        )

    # 3. reject duplicate PENDING requests that overlap this range for
    # the same user (prevents double-submission from impatient users)
    existing_pending = db.query(VacationRequest).filter(
        VacationRequest.user_id == current_user.id,
        VacationRequest.tenant_id == current_user.tenant_id,
        VacationRequest.status == VacationRequestStatus.PENDING.value,
        VacationRequest.date <= end_date,
        # range overlap: existing.end_date >= new.start_date
        # end_date is NULL-safe via COALESCE to date
    ).all()
    for e in existing_pending:
        e_end = e.end_date if e.end_date else e.date
        if e_end >= start_date:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Offener Urlaubsantrag für Zeitraum {e.date}–{e_end} existiert bereits",
            )

    # 4. vacation budget check — only for the default 'vacation' type
    absence_type = data.absence_type or "vacation"
    if absence_type == "vacation":
        from app.services import calculation_service
        dates_by_year: dict[int, list] = {}
        d = start_date
        while d <= end_date:
            if d.weekday() < 5:  # workdays only
                dates_by_year.setdefault(d.year, []).append(d)
            d += timedelta(days=1)

        for check_year, year_dates in dates_by_year.items():
            account = calculation_service.get_vacation_account(db, current_user, check_year)
            year_hours_needed = sum(
                float(calculation_service.get_daily_target_for_date(
                    current_user, d,
                    weekly_hours=calculation_service.get_weekly_hours_for_date(db, current_user, d),
                ))
                for d in year_dates
            )
            if float(account['remaining_hours']) - year_hours_needed < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Nicht genügend Urlaubstage für {check_year} ({account['remaining_days']:.1f} Tage verfügbar)",
                )

    vr = VacationRequest(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        date=data.date,
        end_date=data.end_date,
        hours=data.hours,
        absence_type=absence_type,
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
        query = query.filter(date_in_year(VacationRequest.date, year))
    if status:
        query = query.filter(VacationRequest.status == status)
    requests = query.order_by(VacationRequest.created_at.desc()).all()
    return [_enrich(vr, db) for vr in requests]


def cancel_approved_vacation_request(
    db: Session,
    vr: VacationRequest,
    cancelled_by: User,
) -> int:
    """Delete absences created by an APPROVED vacation request and mark it WITHDRAWN.

    Precondition (caller-enforced): vr.status == APPROVED and the entire
    vacation range lies in the future (vr.date > today). Returns the number
    of absences deleted. Uses an audit log row per deleted absence (DSGVO
    Art. 5 Abs. 2).
    """
    end_date = vr.end_date if vr.end_date else vr.date
    try:
        absence_type_enum = AbsenceType(vr.absence_type or "vacation")
    except ValueError:
        absence_type_enum = AbsenceType.VACATION

    absences_to_remove = db.query(Absence).filter(
        Absence.tenant_id == vr.tenant_id,
        Absence.user_id == vr.user_id,
        Absence.date >= vr.date,
        Absence.date <= end_date,
        Absence.type == absence_type_enum,
    ).all()

    for absence in absences_to_remove:
        audit = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=absence.user_id,
            changed_by=cancelled_by.id,
            action="delete",
            old_date=absence.date,
            old_note=f"absence:{absence.type.value}:{float(absence.hours)}h (cancelled vacation_request {vr.id})",
            source="vacation_request_cancel",
            tenant_id=vr.tenant_id,
        )
        db.add(audit)
        db.delete(absence)

    vr.status = VacationRequestStatus.WITHDRAWN.value
    return len(absences_to_remove)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_vacation_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Withdraw / cancel a vacation request (own only).

    - PENDING → delete the request row.
    - APPROVED with start date strictly in the future → delete the
      associated Absence rows and flip the request to WITHDRAWN. Past /
      started vacations cannot be cancelled because the work day has
      already happened (or is happening).
    """
    vr = db.query(VacationRequest).filter(VacationRequest.id == request_id).first()
    if not vr:
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")
    if str(vr.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    if vr.status == VacationRequestStatus.PENDING.value:
        db.delete(vr)
        db.commit()
        return None

    if vr.status == VacationRequestStatus.APPROVED.value:
        if vr.date <= today_local():
            raise HTTPException(
                status_code=400,
                detail="Genehmigte Anträge können nur storniert werden, wenn der Zeitraum noch nicht begonnen hat",
            )
        cancel_approved_vacation_request(db, vr, current_user)
        db.commit()
        return None

    raise HTTPException(
        status_code=400,
        detail="Nur offene oder genehmigte zukünftige Anträge können storniert werden",
    )
