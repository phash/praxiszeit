from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.core.limiter import limiter
from app.services.date_filters import date_in_year, date_in_month
from typing import List, Optional
from datetime import datetime, timezone, timedelta, date

from app.database import get_db
from app.models import User, UserRole, PublicHoliday, Absence, AbsenceType, TimeEntryAuditLog
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.middleware.auth import get_current_user
from app.schemas.vacation_request import VacationRequestCreate, VacationRequestResponse, VacationRequestUpdate
from app.services.timezone_service import today_local
from app.services import settings_service
from app.services.closure_split_service import resplit_year_closures
# #219: single shared VR-enricher (was duplicated here as a per-item N+1 copy of
# admin_vacations._enrich_vr_responses). _enrich = thin single-item alias.
from app.routers.admin_helpers import _enrich_vr_response as _enrich, _enrich_vr_responses

router = APIRouter(prefix="/api/vacation-requests", tags=["vacation-requests"])


def format_vacation_request_audit_text(vr: VacationRequest) -> str:
    """Compact one-line representation of a vacation request for audit logs.

    Used as `old_note` / `new_note` payload on edit/cancel events. Note is
    truncated to 200 chars to keep audit-log queries cheap. The `|`
    separator is also stripped from the note so users can't forge fake
    audit-row shapes via log injection (CWE-117).
    """
    end = vr.end_date if vr.end_date else vr.date
    note = (vr.note or "").replace("\n", " ").replace("|", "/").strip()[:200]
    text = (
        f"vacation_request {vr.id} | "
        f"{vr.date}..{end} | "
        f"{vr.absence_type or 'vacation'} | "
        f"{float(vr.hours):.2f}h"
    )
    if note:
        text += f" | {note}"
    return text


def apply_vacation_request_patch(
    db: Session,
    vr: VacationRequest,
    data: "VacationRequestUpdate",
    target_user: User,
    acting_user: User,
) -> VacationRequestResponse:
    """Shared edit logic for the MA + Admin PATCH endpoints.

    Caller is responsible for:
      * loading `vr` with `with_for_update()` and a tenant filter,
      * verifying status == PENDING,
      * authorising the actor (owner check for MA, role check for Admin),
      * resolving `target_user` (== current user for MA, == vr owner for
        Admin) so validation runs against the right account.

    This helper handles the actual mutation + audit. Inputs are
    normalised (notes stripped, hours rounded) so trivially-different
    payloads don't flood the audit log (CWE-117 amplification + DSGVO
    Art. 5(1)(c) data minimisation).
    """
    old_audit_text = format_vacation_request_audit_text(vr)
    old_date = vr.date

    # Apply patch. model_fields_set distinguishes "field absent" (keep DB)
    # from "field=null" (clear nullable). Inputs are normalised before any
    # equality compare so " x " vs "x" doesn't trigger a spurious audit.
    fields_set = data.model_fields_set
    new_date = data.date if "date" in fields_set and data.date is not None else vr.date
    new_end_date = data.end_date if "end_date" in fields_set else vr.end_date
    if "hours" in fields_set and data.hours is not None:
        new_hours = round(float(data.hours), 2)
    else:
        new_hours = round(float(vr.hours), 2)
    if "note" in fields_set:
        new_note = (data.note or "").strip() if data.note is not None else None
    else:
        new_note = vr.note
    new_absence_type = data.absence_type if "absence_type" in fields_set and data.absence_type is not None else vr.absence_type

    no_change = (
        new_date == vr.date
        and new_end_date == vr.end_date
        and new_hours == round(float(vr.hours), 2)
        and (new_note or None) == (vr.note or None)
        and new_absence_type == vr.absence_type
    )
    if no_change:
        return _enrich(vr, db)

    effective_end = new_end_date if new_end_date else new_date
    if effective_end < new_date:
        raise HTTPException(status_code=400, detail="Enddatum muss nach dem Startdatum liegen")
    # Same bound as the POST path: an approved request overwrites time entries
    # per workday — a PATCH must not be able to silently extend to an unbounded span.
    if (effective_end - new_date).days > 366:
        raise HTTPException(status_code=400, detail="Der Zeitraum darf maximal ein Jahr umfassen")
    if target_user.first_work_day and new_date < target_user.first_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
    if target_user.last_work_day and effective_end > target_user.last_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")

    other_pending = db.query(VacationRequest).filter(
        VacationRequest.id != vr.id,
        VacationRequest.user_id == target_user.id,
        VacationRequest.tenant_id == vr.tenant_id,
        VacationRequest.status == VacationRequestStatus.PENDING.value,
        VacationRequest.date <= effective_end,
    ).all()
    for e in other_pending:
        e_end = e.end_date if e.end_date else e.date
        if e_end >= new_date:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Offener Urlaubsantrag für Zeitraum {e.date}–{e_end} existiert bereits",
            )

    if new_absence_type == "vacation":
        from app.services import calculation_service, special_days_service
        # Public holidays are excluded from the budget calc to stay
        # consistent with the approve flow (admin_vacations.py:155-180).
        # Without this, PATCH false-positives "insufficient budget" for
        # ranges that contain holidays which approval would not consume.
        years_in_range = set()
        d = new_date
        while d <= effective_end:
            years_in_range.add(d.year)
            d += timedelta(days=1)
        holiday_dates: set = set()
        if years_in_range:
            for h in db.query(PublicHoliday).filter(
                PublicHoliday.year.in_(years_in_range),
                PublicHoliday.tenant_id == vr.tenant_id,
            ).all():
                holiday_dates.add(h.date)
        # F-10 / AC-11: 'free'-Sondertage (24./31.12.) sind ebenfalls soll-frei
        # und dürfen genau wie Feiertage nicht als verbrauchter Urlaubstag
        # zählen — Parität mit admin_vacations.review_vacation_request.
        holiday_dates |= special_days_service.free_special_days_in_range(
            db, vr.tenant_id, new_date, effective_end
        )

        dates_by_year: dict[int, list] = {}
        d = new_date
        while d <= effective_end:
            if d.weekday() < 5 and d not in holiday_dates:
                dates_by_year.setdefault(d.year, []).append(d)
            d += timedelta(days=1)
        # #196: tagebasiert prüfen (konsistent mit POST-Pfad / create_absence /
        # review_vacation_request). Der frühere remaining_hours-Check lief für
        # track_hours=False ins Leere (remaining_hours == 0 UND year_hours_needed
        # == 0 → nie blockiert). half_day ist im Edit nicht änderbar → vr.half_day.
        # R1-3: skip days with 0h target (e.g. Mo/Mi/Fr user — mirrors the
        # creation/approval loop which skips hours_for_day == 0). #431: der Modus
        # wird PRO TAG aufgeloest, nicht am Live-Flag gelesen (siehe
        # ``is_vacation_billable_day``, dort auch die track_hours=False-Ausnahme).
        day_factor = 0.5 if vr.half_day else 1.0
        for check_year, year_dates in dates_by_year.items():
            account = calculation_service.get_vacation_account(db, target_user, check_year)
            billable_days = [
                dd for dd in year_dates
                if calculation_service.is_vacation_billable_day(db, target_user, dd)
            ]
            # #394: Halbtags-Sondertag kostet 0,5 — Pre-Check muss get_vacation_account matchen.
            _cfg = special_days_service.get_special_day_config(db, target_user.tenant_id, check_year)
            days_needed = sum(
                day_factor * float(calculation_service.half_special_day_weight(d, _cfg))
                for d in billable_days
            )
            if days_needed > float(account['remaining_days']) + 1e-9:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Nicht genügend Urlaubstage für {check_year} ({account['remaining_days']:.1f} Tage verfügbar)",
                )

    vr.date = new_date
    vr.end_date = new_end_date
    vr.hours = new_hours
    vr.note = new_note
    vr.absence_type = new_absence_type
    vr.last_modified_by = acting_user.id
    vr.last_modified_at = datetime.now(timezone.utc)

    new_audit_text = format_vacation_request_audit_text(vr)
    audit = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=vr.user_id,
        changed_by=acting_user.id,
        action="update",
        old_date=old_date,
        new_date=vr.date,
        old_note=old_audit_text,
        new_note=new_audit_text,
        source="vacation_request_edit",
        tenant_id=vr.tenant_id,
    )
    db.add(audit)
    db.commit()
    db.refresh(vr)
    return _enrich(vr, db)


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
    if not settings_service.get_bool_setting(db, "vacation_approval_required", tenant_id=current_user.tenant_id):
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
    # Bound the range: an approved request books an absence per workday AND
    # overwrites time entries on those days — an unbounded span is a data-loss
    # amplifier and never a legitimate single request.
    if (end_date - start_date).days > 366:
        raise HTTPException(
            status_code=400,
            detail="Der Zeitraum darf maximal ein Jahr umfassen",
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
        from app.services import calculation_service, special_days_service
        # R2-c: exclude public holidays from the budget count — parity with the
        # PATCH path (apply_vacation_request_patch) and the approve flow
        # (admin_vacations.review_vacation_request). Without this the POST
        # false-positives "nicht genügend Urlaubstage" for ranges that contain
        # holidays which approval would never consume.
        years_in_range = set()
        d = start_date
        while d <= end_date:
            years_in_range.add(d.year)
            d += timedelta(days=1)
        holiday_dates: set = set()
        if years_in_range:
            for h in db.query(PublicHoliday).filter(
                PublicHoliday.year.in_(years_in_range),
                PublicHoliday.tenant_id == current_user.tenant_id,
            ).all():
                holiday_dates.add(h.date)
        # F-10 / AC-11: 'free'-Sondertage (24./31.12.) sind ebenfalls soll-frei
        # und dürfen genau wie Feiertage nicht als verbrauchter Urlaubstag
        # zählen — Parität mit dem PATCH-Pfad und
        # admin_vacations.review_vacation_request.
        holiday_dates |= special_days_service.free_special_days_in_range(
            db, current_user.tenant_id, start_date, end_date
        )

        dates_by_year: dict[int, list] = {}
        d = start_date
        while d <= end_date:
            if d.weekday() < 5 and d not in holiday_dates:  # workdays, no holidays
                dates_by_year.setdefault(d.year, []).append(d)
            d += timedelta(days=1)

        # Tagesprinzip: tagebasiert prüfen (konsistent mit create_absence /
        # review_vacation_request). half_day verbraucht 0,5 Tage pro Tag —
        # sonst würde ein halber Tag bei genau 0,5 Resttagen fälschlich abgelehnt.
        # R1-3: skip days with 0h target (e.g. Mo/Mi/Fr user — mirrors the
        # creation/approval loop which skips hours_for_day == 0). #431: der Modus
        # wird PRO TAG aufgeloest, nicht am Live-Flag gelesen (siehe
        # ``is_vacation_billable_day``, dort auch die track_hours=False-Ausnahme).
        day_factor = 0.5 if data.half_day else 1.0
        for check_year, year_dates in dates_by_year.items():
            account = calculation_service.get_vacation_account(db, current_user, check_year)
            billable_days = [
                dd for dd in year_dates
                if calculation_service.is_vacation_billable_day(db, current_user, dd)
            ]
            # #394: Halbtags-Sondertag kostet 0,5 — Pre-Check muss get_vacation_account matchen.
            _cfg = special_days_service.get_special_day_config(db, current_user.tenant_id, check_year)
            days_needed = sum(
                day_factor * float(calculation_service.half_special_day_weight(d, _cfg))
                for d in billable_days
            )
            if days_needed > float(account['remaining_days']) + 1e-9:
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
        half_day=data.half_day,
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
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's vacation requests."""
    query = db.query(VacationRequest).filter(
        VacationRequest.user_id == current_user.id,
        VacationRequest.tenant_id == current_user.tenant_id,  # F-026
    )
    if year:
        from sqlalchemy import extract
        query = query.filter(date_in_year(VacationRequest.date, year))
    if status:
        query = query.filter(VacationRequest.status == status)
    requests = query.order_by(VacationRequest.created_at.desc()).offset(skip).limit(limit).all()
    return _enrich_vr_responses(requests, db)  # #219: batch (was per-item N+1)


def cancel_approved_vacation_request(
    db: Session,
    vr: VacationRequest,
    cancelled_by: User,
) -> Optional[str]:
    """Delete absences created by an APPROVED vacation request and mark it WITHDRAWN.

    Precondition (caller-enforced): vr.status == APPROVED and the entire
    vacation range lies in the future (vr.date > today). Uses an audit log row
    per deleted absence (DSGVO Art. 5 Abs. 2).

    Fix #5: returns a non-destructive ``warning`` string when the cancelled
    range touches an already-closed year (a YearCarryover for year+1 exists) —
    that frozen carryover is now stale. Returns None otherwise. (No automatic
    recompute: that could overwrite manual carryover adjustments.)
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

    # Fix #5: non-destructive stale-closing warning for the touched year(s).
    from app.services import calculation_service
    return calculation_service.stale_year_closing_warning(
        db, vr.tenant_id, range(vr.date.year, end_date.year + 1)
    )


@router.patch("/{request_id}", response_model=VacationRequestResponse)
@limiter.limit("60/minute")
def update_vacation_request(
    request: Request,
    request_id: str,
    data: VacationRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit an own PENDING vacation request. Delegates the patch /
    validation / audit work to ``apply_vacation_request_patch``."""
    vr = (
        db.query(VacationRequest)
        .filter(
            VacationRequest.id == request_id,
            VacationRequest.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not vr:
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")
    if str(vr.user_id) != str(current_user.id):
        # #120: 404 statt 403 — ein fremder (Same-Tenant-)Antrag wird wie ein
        # unbekannter behandelt, damit der Response-Code nicht die Existenz einer
        # fremden VR-ID im eigenen Tenant verraet (gleiche Meldung wie "not found").
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")
    if vr.status != VacationRequestStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Nur offene Anträge können bearbeitet werden",
        )
    return apply_vacation_request_patch(
        db, vr, data, target_user=current_user, acting_user=current_user
    )


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

    Row is locked via ``with_for_update`` to close the
    edit-vs-withdraw race the edit-feature review flagged: if an admin
    is mid-PATCH on a pending request and the user clicks Withdraw, we
    don't want a torn state where the audit row is written for an edit
    that lost to a concurrent delete.
    """
    vr = (
        db.query(VacationRequest)
        .filter(
            VacationRequest.id == request_id,
            VacationRequest.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not vr:
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")
    if str(vr.user_id) != str(current_user.id):
        # #120: 404 statt 403 — ein fremder (Same-Tenant-)Antrag wird wie ein
        # unbekannter behandelt, damit der Response-Code nicht die Existenz einer
        # fremden VR-ID im eigenen Tenant verraet (gleiche Meldung wie "not found").
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")

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
        vr_end = vr.end_date if vr.end_date else vr.date
        years = set(range(vr.date.year, vr_end.year + 1))
        warning = cancel_approved_vacation_request(db, vr, current_user)
        # Fix #3: cancelling a VACATION frees budget → re-split the affected years
        # so a closure OVERTIME day can flip back to VACATION (only when the
        # toggle is on). Flush the deletes first so they leave the budget snapshot.
        if settings_service.get_bool_setting(
            db, "closure_overtime_after_vacation", current_user.tenant_id, False
        ):
            db.flush()
            for yr in years:
                resplit_year_closures(db, current_user.tenant_id, yr)
        db.commit()
        # Fix #5: surface the stale-closing warning (200 + body) when present;
        # otherwise the normal 204 No Content.
        if warning:
            return JSONResponse(status_code=200, content={"warning": warning})
        return None

    raise HTTPException(
        status_code=400,
        detail="Nur offene oder genehmigte zukünftige Anträge können storniert werden",
    )
