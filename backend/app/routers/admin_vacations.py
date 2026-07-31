"""Admin sub-router: Vacation Request Management."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from app.core.limiter import limiter
from app.database import get_db
from app.models import User, Absence, PublicHoliday, AbsenceType, TimeEntry, TimeEntryAuditLog, WorkingHoursChange
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.middleware.auth import require_admin
from app.schemas.vacation_request import VacationRequestResponse, VacationRequestReview, VacationRequestUpdate
from app.services import calculation_service, special_days_service, settings_service
from app.services.closure_split_service import resplit_year_closures
from app.services.timezone_service import today_local
from app.routers.admin_helpers import (
    _create_audit_log,
    _enrich_vr_response,
    _enrich_vr_responses,
    lock_user_row,
)
from app.routers.admin_users import _tenant_has_other_active_admin
from app.routers.vacation_requests import (
    cancel_approved_vacation_request,
    apply_vacation_request_patch,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/vacation-requests/pending-count")
def get_pending_vacation_request_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return count of pending vacation requests for admin badge."""
    # F-026: explicit tenant filter (RLS is the second line of defense).
    count = db.query(VacationRequest).filter(
        VacationRequest.status == VacationRequestStatus.PENDING.value,
        VacationRequest.tenant_id == current_user.tenant_id,
    ).count()
    return {"count": count}


# _enrich_vr_response / _enrich_vr_responses live in admin_helpers now (#219).


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
    # F-026: explicit tenant scoping on top of RLS.
    query = db.query(VacationRequest).filter(
        VacationRequest.tenant_id == current_user.tenant_id
    )
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

    # F-028: lock the VR row to prevent concurrent-click races where two
    # admin requests both pass the PENDING check and both try to create
    # absence entries. Also scope to the admin's tenant.
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
    if vr.status != VacationRequestStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Antrag wurde bereits bearbeitet")

    if review.action == "reject":
        # Ablehnen ist keine Selbst-Genehmigung -> die reviewed_*-Felder dürfen
        # hier gesetzt werden (sie belegen, wer wann abgelehnt hat).
        vr.reviewed_by = current_user.id
        vr.reviewed_at = datetime.now(timezone.utc)
        vr.status = VacationRequestStatus.REJECTED.value
        vr.rejection_reason = review.rejection_reason
        db.commit()
        db.refresh(vr)
        return _enrich_vr_response(vr, db)

    # CLAUDE.md "Precondition-Checks VOR Status-Änderung": die reviewed_*-Felder
    # werden auf dem Approve-Pfad erst NACH allen Vorbedingungen gesetzt (4-Augen
    # + Budget-/Arbeitstag-Checks weiter unten), nicht vorab.
    #
    # Audit A01: 4-eyes principle. An admin must not approve their OWN vacation
    # request — but ONLY when independent oversight is actually possible (another
    # active admin exists in the tenant). A sole-admin practice may still
    # self-approve (reviewed_by == user_id records it). Raised before any state
    # change / absence materialisation.
    if vr.user_id == current_user.id and _tenant_has_other_active_admin(db, current_user):
        raise HTTPException(
            status_code=403,
            detail=(
                "Eigene Urlaubsanträge dürfen nicht selbst genehmigt werden, "
                "wenn ein weiterer Admin vorhanden ist (4-Augen-Prinzip)."
            ),
        )

    # Approve: create absence entries (same logic as create_absence in absences.py)
    # F-026: explicit tenant scoping. BUG-3 (Review 2026-06-23): die Anker-Sperre
    # auf der User-Zeile serialisiert zwei gleichzeitige Genehmigungen fuer
    # denselben MA, sonst koennten beide den Urlaubsbudget-Check passieren und
    # das Budget ueberziehen.
    # Audit 2026-07-31 (Restklasse): ueber den gemeinsamen Helfer, also
    # ``FOR NO KEY UPDATE`` — dieser Pfad schreibt danach Audit-Zeilen mit
    # ``changed_by = handelnder Admin``. Begruendung im Kopf von
    # ``admin_helpers``. Die Ausschlusswirkung gegen andere Buchungspfade
    # (und damit der Budget-Schutz) bleibt unveraendert.
    target_user = lock_user_row(db, current_user.tenant_id, vr.user_id)
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
        # F-026 + CLAUDE.md PublicHoliday rule: standalone holiday queries must
        # be tenant-scoped explicitly (RLS does not always cover them).
        rows = db.query(PublicHoliday).filter(
            PublicHoliday.year == year,
            PublicHoliday.tenant_id == current_user.tenant_id,
        ).all()
        for h in rows:
            holidays.add(h.date)

    # AC-11: 'free'-Sondertage (24./31.12.) sind soll-frei → wie Feiertage
    # ausschließen, sonst kostet ein Urlaubsantrag über einen freien Tag fälschlich
    # einen Urlaubstag (free+counts_as_vacation wird separat im Konto gezählt).
    holidays |= special_days_service.free_special_days_in_range(
        db, current_user.tenant_id, start_date, end_date
    )

    # Determine working days
    dates_to_create = []
    cur = start_date
    while cur <= end_date:
        if cur.weekday() < 5 and cur not in holidays:
            dates_to_create.append(cur)
        cur += timedelta(days=1)

    if not dates_to_create:
        raise HTTPException(status_code=400, detail="Keine gültigen Arbeitstage im Zeitraum")

    # R2-c: block ANY pre-existing absence on those days, not just the same
    # type. The unique constraint is (tenant_id, user_id, date, type) — a
    # DIFFERENT type (e.g. an existing SICK absence) would slip past a
    # same-type-only check and let approval insert a second absence on the same
    # day (cross-type double-booking). One absence per day, period. Mirrors
    # create_absence. F-026: explicit tenant scoping; with_for_update() closes
    # the race between this probe and the INSERT below.
    for d in dates_to_create:
        existing = db.query(Absence).filter(
            Absence.user_id == target_user.id,
            Absence.tenant_id == current_user.tenant_id,
            Absence.date == d,
        ).with_for_update().first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Am {d.strftime('%d.%m.%Y')} existiert bereits eine Abwesenheit ({existing.type.value})",
            )

    # Check vacation budget only for VACATION type (per year for cross-year requests)
    if absence_type == AbsenceType.VACATION:
        dates_by_year = {}
        for d in dates_to_create:
            dates_by_year.setdefault(d.year, []).append(d)
        # Fix-Welle 4 #3: EINMAL je Anfrage laden statt je Tag eine Query in
        # ``is_vacation_billable_day`` (F-026: tenant-gefiltert).
        wh_changes = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == target_user.id,
            WorkingHoursChange.tenant_id == target_user.tenant_id,
        ).order_by(WorkingHoursChange.effective_from).all()
        for check_year, year_dates in dates_by_year.items():
            vacation_account = calculation_service.get_vacation_account(
                db, target_user, check_year, wh_changes=wh_changes
            )
            # #156/T2 + #167: tagebasiert (jeder Tag = 1, Halbtag = 0,5).
            # R1-3: skip days with 0h target (e.g. Mo/Mi/Fr user — mirrors the
            # creation loop which skips hours_for_day == 0). #431: der Modus wird
            # PRO TAG aufgeloest, nicht am Live-Flag gelesen (siehe
            # ``is_vacation_billable_day``, dort auch die track_hours=False-Ausnahme).
            billable_days = [
                d for d in year_dates
                if calculation_service.is_vacation_billable_day(db, target_user, d, wh_changes=wh_changes)
            ]
            # #394: Halbtags-Sondertag kostet 0,5 — Pre-Check muss get_vacation_account matchen.
            _base = 0.5 if vr.half_day else 1.0
            _cfg = special_days_service.get_special_day_config(db, target_user.tenant_id, check_year)
            days_needed = sum(
                _base * float(calculation_service.half_special_day_weight(d, _cfg))
                for d in billable_days
            )
            if days_needed > vacation_account["remaining_days"] + 1e-9:
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
        schedule = calculation_service.get_schedule_for_date(db, target_user, d)
        # #156/T1 + #167: Voll-Tag-Typen werden immer mit dem Tagessoll des Tages
        # gebucht (Tagesprinzip), nicht mit vr.hours (das den 8h-Default tragen
        # kann). Halber Tag = 0,5 × Tagessoll. NUR der Überstundenausgleich
        # (OVERTIME) behält die explizit beantragten Stunden — identisch zum
        # Direkt-Buchungspfad in absences.py. CLAUDE.md: die OVERTIME-Ausnahme
        # MUSS in BEIDEN Pfaden gepflegt werden (vorher fehlte sie hier → ein per
        # Antrag genehmigter Ausgleich buchte das Tagessoll statt der beantragten
        # Stunden; rechnerisch neutral, aber falsch in Anzeige/Reports).
        # #431: Modus aus dem zum DATUM aufgeloesten Snapshot (``schedule`` oben),
        # nicht vom Live-Flag der User-Zeile — identisch zu ``create_absence``.
        if absence_type != AbsenceType.OVERTIME or schedule.use_daily_schedule:
            hours_for_day = float(calculation_service.get_daily_target_for_date(target_user, d, schedule))
            # Review R3 (HIGH): only skip genuine 0h days for TRACKED users. For
            # track_hours=False the daily target is always 0; skipping would book
            # nothing, leaving the approved request with no absence rows and the
            # day-based vacation account at 0 used. dates_to_create already excludes
            # weekends/holidays → every remaining day is booked (hours stay 0).
            if hours_for_day == 0 and target_user.track_hours:
                continue
            if vr.half_day:
                hours_for_day = round(hours_for_day / 2, 2)
        else:
            hours_for_day = float(vr.hours)

        absence = Absence(
            user_id=target_user.id,
            tenant_id=current_user.tenant_id,
            date=d,
            end_date=vr.end_date,
            type=absence_type,
            hours=hours_for_day,
            # #205: Buchungs-Intent (Halbtag) auf der Absence persistieren ->
            # tagebasierter, WHChange-stabiler Urlaubsverbrauch.
            half_day=vr.half_day,
            note=vr.note,
        )
        db.add(absence)

    # Alle Vorbedingungen bestanden -> jetzt erst Reviewer + Genehmigung setzen.
    vr.reviewed_by = current_user.id
    vr.reviewed_at = datetime.now(timezone.utc)
    vr.status = VacationRequestStatus.APPROVED.value
    db.commit()
    db.refresh(vr)

    # Fix #3: an approved VACATION reduces the budget the #314 closure split
    # reserves up front → re-split the affected years (only when the toggle is on).
    if absence_type == AbsenceType.VACATION and settings_service.get_bool_setting(
        db, "closure_overtime_after_vacation", current_user.tenant_id, False
    ):
        for yr in {d.year for d in dates_to_create}:
            resplit_year_closures(db, current_user.tenant_id, yr)
        db.commit()
        db.refresh(vr)

    return _enrich_vr_response(vr, db)


@router.patch("/vacation-requests/{request_id}", response_model=VacationRequestResponse)
@limiter.limit("60/minute")
def update_vacation_request_as_admin(
    request: Request,
    request_id: str,
    data: VacationRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Edit a PENDING vacation request on behalf of the requesting employee.

    Tenant-scoped: returns 404 (not 403) if the row belongs to another
    tenant — don't leak existence. Validation runs against the target
    employee (not the admin) so work-day window + vacation budget are
    evaluated against them. Patch / audit logic is shared with the MA
    endpoint via ``apply_vacation_request_patch``.
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
    if vr.status != VacationRequestStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Nur offene Anträge können bearbeitet werden",
        )

    target_user = db.query(User).filter(
        User.id == vr.user_id,
        User.tenant_id == current_user.tenant_id,
    ).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    return apply_vacation_request_patch(
        db, vr, data, target_user=target_user, acting_user=current_user
    )


@router.delete("/vacation-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_vacation_request_as_admin(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin cancellation of a vacation request on behalf of the user.

    Mirrors the employee-side withdraw semantics + lets admins prune dead rows:
    - PENDING → delete the request row.
    - APPROVED with start date strictly in the future → delete associated
      absences + flip to WITHDRAWN (keeps the row for audit trail).
    - REJECTED → delete the request row (no side effects: a rejected request
      never produced absences, the rejection itself stays in the audit log).

    Tenant-scoped: admin cannot reach into foreign tenants.
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

    if vr.status == VacationRequestStatus.PENDING.value:
        db.delete(vr)
        db.commit()
        return None

    if vr.status == VacationRequestStatus.REJECTED.value:
        # No side effects (no absences were ever created), so a plain row
        # delete is safe. The original rejection event is preserved in the
        # admin audit log via the review endpoint.
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
        detail="Nur offene, abgelehnte oder genehmigte zukünftige Anträge können storniert werden",
    )
