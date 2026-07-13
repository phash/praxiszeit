"""Admin sub-router: Change Request Management."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, date, timedelta
from app.database import get_db
from app.models import User, TimeEntry, ChangeRequest, ChangeRequestStatus, ChangeRequestType, Absence, AbsenceType, AbsenceReason
from app.middleware.auth import require_admin
from app.schemas.change_request import (
    ChangeRequestResponse,
    ChangeRequestReview,
    ChangeRequestBulkReview,
    ChangeRequestBulkReviewItemResult,
    ChangeRequestBulkReviewResult,
)
from app.schemas.time_entry import TimeEntryResponse
from app.routers.admin_helpers import _create_audit_log, _enrich_cr_response, _enrich_cr_responses
from app.routers.admin_users import _tenant_has_other_active_admin
from app.routers.time_entries import (
    _calculate_daily_net_hours, _calculate_weekly_net_hours,
    MAX_DAILY_HOURS_HARD, MAX_NIGHT_WORKER_DAILY_WARN, MAX_WEEKLY_HOURS_WARN,
    BREAK_WAIVER_SOURCE,
)
from app.services.break_validation_service import validate_daily_break
from app.services.arbzg_utils import is_night_work
from app.services.calculation_service import (
    get_weekly_hours_for_date, get_daily_target_for_date, get_vacation_account,
    get_daily_target, child_sick_cap, child_sick_days_used, half_special_day_weight,
)
from app.services import work_window_service, settings_service, special_days_service
from app.services.closure_split_service import resplit_year_closures
from app.models.time_entry_audit_log import TimeEntryAuditLog

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _vacation_day_contribution(db, user, d, half_day) -> float:
    """Fix #4: tagebasierter Urlaubsverbrauch EINES VACATION-Tags am Datum ``d``,
    exakt nach der Regel in ``get_vacation_account``: untracked (Tagessoll 0
    gesamt) → 0,5/1,0; sonst Tagessoll-des-Tages ≤ 0 → 0, sonst 0,5 (Halbtag)
    bzw. 1,0 (voller Tag). ``half_day=None`` (Legacy/CR-Default) zählt als voller
    Tag (ein CR bucht ganztags). Wird für den Netto-Neuverbrauch-Vergleich im
    UPDATE-Budget-Check verwendet."""
    # #394: an einem Halbtags-Sondertag (24./31.12.) kostet der Urlaubstag 0,5 —
    # exakt wie get_vacation_account/absence_days (zentraler Helper).
    _cfg = special_days_service.get_special_day_config(db, user.tenant_id, d.year)
    weight = float(half_special_day_weight(d, _cfg))
    if get_daily_target(user) <= 0:  # untracked / work_days_per_week == 0
        return (0.5 if half_day else 1.0) * weight
    dt = get_daily_target_for_date(user, d, get_weekly_hours_for_date(db, user, d))
    if dt <= 0:
        return 0.0
    return (0.5 if half_day else 1.0) * weight


def _delete_day_time_entries(db, user_id, tenant_id, target_date, changed_by, cr_id):
    """Fix #3: delete all time entries of a user on a given day (with audit),
    mirroring create_absence — an absence and a time entry on the same day must
    not both count toward Ist. Tenant-scoped (F-026)."""
    if target_date is None:
        return
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.tenant_id == tenant_id,
        TimeEntry.date == target_date,
    ).all()
    for te in entries:
        _create_audit_log(
            db, te.id, user_id, changed_by,
            action="delete", old_entry=te,
            source="change_request", change_request_id=cr_id,
            tenant_id=tenant_id,
        )
        db.delete(te)


@router.get("/change-requests/pending-count")
def get_pending_change_request_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return count of pending change requests for admin badge."""
    # F-026: explicit tenant filter (RLS is the second line of defense).
    count = db.query(ChangeRequest).filter(
        ChangeRequest.status == ChangeRequestStatus.PENDING,
        ChangeRequest.tenant_id == current_user.tenant_id,
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
    # F-026: explicit tenant scope before any optional filter.
    query = db.query(ChangeRequest).filter(
        ChangeRequest.tenant_id == current_user.tenant_id,
    )
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
    # F-026: scope by tenant so a guessed UUID from another tenant 404s
    # instead of leaking via RLS-bypass paths.
    cr = (
        db.query(ChangeRequest)
        .filter(
            ChangeRequest.id == request_id,
            ChangeRequest.tenant_id == current_user.tenant_id,
        )
        .first()
    )
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
    # F-028: Lock the CR row for the duration of this transaction so that
    # two concurrent approval requests cannot both pass the status check
    # and mutate state. Without with_for_update(), a double-click on "Approve"
    # for a DELETE CR would execute db.delete(entry) twice and raise 500;
    # for an UPDATE CR it would write the same audit log twice.
    cr = (
        db.query(ChangeRequest)
        .filter(
            ChangeRequest.id == request_id,
            ChangeRequest.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
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

    # SEC-E: 4-eyes principle for the break-waiver workflow. An admin must not
    # approve their OWN documented break-exception (#144 §4 ArbZG) — the whole
    # point of the approval mode is independent oversight.
    if cr.break_waiver_reason is not None and cr.user_id == current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Eigene Pflicht-Pause-Ausnahmen dürfen nicht selbst genehmigt werden.",
        )

    # Audit A01: 4-eyes principle for ORDINARY change-requests. An admin who is
    # also a tracked employee must not approve their OWN time-entry/absence CR —
    # but ONLY when independent oversight is actually possible (another active
    # admin exists). Sole-admin practices may still self-approve (the break-waiver
    # block above stays unconditional/stricter for §4 waivers). reviewed_by ==
    # user_id already records the allowed sole-admin self-approval.
    if cr.user_id == current_user.id and _tenant_has_other_active_admin(db, current_user):
        raise HTTPException(
            status_code=403,
            detail=(
                "Eigene Änderungsanträge dürfen nicht selbst genehmigt werden, "
                "wenn ein weiterer Admin vorhanden ist (4-Augen-Prinzip)."
            ),
        )

    # Approve: validate preconditions BEFORE changing status
    entry = None
    if cr.entry_kind != "absence":
        if cr.request_type == ChangeRequestType.CREATE:
            duplicate = db.query(TimeEntry).filter(
                TimeEntry.tenant_id == cr.tenant_id,
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
            # N-3: lock the target entry for the duration of the approval txn,
            # matching the update_time_entry path — prevents a concurrent admin
            # edit from racing the re-validation/materialisation below.
            entry = db.query(TimeEntry).filter(
                TimeEntry.id == cr.time_entry_id,
                TimeEntry.tenant_id == cr.tenant_id,
            ).with_for_update().first()
            if not entry:
                raise HTTPException(status_code=404, detail="Zeiteintrag nicht mehr vorhanden")
            # Check for unique constraint violation on date/start_time change
            if cr.proposed_date != entry.date or cr.proposed_start_time != entry.start_time:
                dup = db.query(TimeEntry).filter(
                    TimeEntry.tenant_id == cr.tenant_id,
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
            # N-3: lock the target entry for the duration of the approval txn,
            # matching the update_time_entry path — prevents a concurrent admin
            # edit from racing the re-validation/materialisation below.
            entry = db.query(TimeEntry).filter(
                TimeEntry.id == cr.time_entry_id,
                TimeEntry.tenant_id == cr.tenant_id,
            ).with_for_update().first()
            if not entry:
                raise HTTPException(status_code=404, detail="Zeiteintrag nicht mehr vorhanden")

        # C-1: Re-validate §3 (daily hard cap) and §4 (breaks) against the
        # CURRENT DB state before materialising a CREATE/UPDATE. The CR was
        # validated at creation time, but other same-day entries may have been
        # added in the meantime — without this re-check an approval could push
        # the day over the legal limits. A break-waiver (cr.break_waiver_reason)
        # excuses §4 only; the §3 10h ceiling is absolute and is NOT waivable.
        if (
            cr.request_type in (ChangeRequestType.CREATE, ChangeRequestType.UPDATE)
            and cr.proposed_start_time
            and cr.proposed_end_time
        ):
            cr_user = db.query(User).filter(
                User.id == cr.user_id,
                User.tenant_id == cr.tenant_id,
            ).first()
            if cr_user and not cr_user.exempt_from_arbzg:
                # On UPDATE the proposed values replace the existing entry, so
                # exclude it from the daily picture (mirrors update_time_entry).
                exclude_id = entry.id if cr.request_type == ChangeRequestType.UPDATE and entry else None

                # §16/#201: the CR carries the employee's RAW proposed times.
                # §3/§4 compliance is assessed on the CREDITED (clamped) time —
                # exactly as create_time_entry/update_time_entry do — so clamp to
                # the soll-window first, then re-validate. Checking the raw span
                # here would wrongly reject an entry whose credited time is legal
                # (e.g. a wide raw stamp the window clamps back under 10h).
                _grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
                _eff_start, _eff_end, _, _ = work_window_service.clamp(
                    cr_user, cr.proposed_date,
                    cr.proposed_start_time, cr.proposed_end_time, _grace,
                )

                daily_hours_revalidate = _calculate_daily_net_hours(
                    db=db,
                    user_id=cr.user_id,
                    entry_date=cr.proposed_date,
                    start_time=_eff_start,
                    end_time=_eff_end,
                    break_minutes=cr.proposed_break_minutes or 0,
                    exclude_entry_id=exclude_id,
                    tenant_id=cr.tenant_id,
                )
                if daily_hours_revalidate > MAX_DAILY_HOURS_HARD:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Tagesarbeitszeit würde {daily_hours_revalidate:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
                    )

                # §4 break validation — skipped only when a documented waiver
                # is attached (waiver excuses §4, never §3).
                if cr.break_waiver_reason is None:
                    break_error = validate_daily_break(
                        db=db,
                        user_id=cr.user_id,
                        entry_date=cr.proposed_date,
                        start_time=_eff_start,
                        end_time=_eff_end,
                        break_minutes=cr.proposed_break_minutes or 0,
                        exclude_entry_id=exclude_id,
                    )
                    if break_error:
                        raise HTTPException(status_code=422, detail=break_error)

    # Absence CR preconditions
    absence = None
    # Review R2-a: a pre-existing absence on the target day that the CREATE
    # path would collide with. Same type → idempotent (skip the insert below);
    # different type → raised as 409 here, before any state change.
    existing_absence = None
    if cr.entry_kind == "absence":
        if cr.request_type in (ChangeRequestType.UPDATE, ChangeRequestType.DELETE):
            absence = db.query(Absence).filter(Absence.id == cr.absence_id, Absence.tenant_id == cr.tenant_id).first()
            if not absence:
                raise HTTPException(status_code=404, detail="Abwesenheit nicht mehr vorhanden")

        # Arbeitszeitraum-Prüfung für Absence CREATE/UPDATE
        if cr.request_type in (ChangeRequestType.CREATE, ChangeRequestType.UPDATE):
            cr_user = db.query(User).filter(User.id == cr.user_id, User.tenant_id == cr.tenant_id).first()
            if cr_user and cr.proposed_date:
                if cr_user.first_work_day and cr.proposed_date < cr_user.first_work_day:
                    raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
                if cr_user.last_work_day and cr.proposed_date > cr_user.last_work_day:
                    raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")

        # Review R2-a: guard the CREATE materialisation against double-booking.
        # Without this, approving a CREATE-CR whose target day already has an
        # absence either crashes with 500 (uq_tenant_user_date_type violation
        # for the SAME type — which then rolls back the status flip and wedges
        # the CR PENDING / un-approvable) or silently double-books (a DIFFERENT
        # type slips past the unique constraint). Mirror create_absence: same
        # type = idempotent skip, different type = clean 409. with_for_update()
        # closes the race between this probe and the INSERT below.
        if cr.request_type == ChangeRequestType.CREATE and cr.proposed_date:
            existing_absence = (
                db.query(Absence)
                .filter(
                    Absence.user_id == cr.user_id,
                    Absence.tenant_id == cr.tenant_id,
                    Absence.date == cr.proposed_date,
                )
                .with_for_update()
                .first()
            )
            if existing_absence and existing_absence.type.value != cr.proposed_absence_type:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Am {cr.proposed_date.strftime('%d.%m.%Y')} existiert bereits "
                        f"eine Abwesenheit ({existing_absence.type.value})"
                    ),
                )

    # All preconditions met — now mark as approved
    cr.status = ChangeRequestStatus.APPROVED
    cr.reviewed_by = current_user.id
    cr.reviewed_at = datetime.now(timezone.utc)

    # Use the CR's tenant_id (from the requesting user), not the admin's
    cr_tenant_id = cr.tenant_id

    # TimeEntry CR actions
    if cr.entry_kind != "absence":
        if cr.request_type == ChangeRequestType.CREATE:
            # #201: clamp proposed times to the CR employee's soll window.
            _cr_user_te = db.query(User).filter(
                User.id == cr.user_id,
                User.tenant_id == cr.tenant_id,
            ).first()
            _grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
            eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(
                _cr_user_te, cr.proposed_date,
                cr.proposed_start_time, cr.proposed_end_time, _grace,
            )
            entry = TimeEntry(
                user_id=cr.user_id,
                tenant_id=cr_tenant_id,
                date=cr.proposed_date,
                start_time=eff_start,
                end_time=eff_end,
                raw_start_time=raw_start,
                raw_end_time=raw_end,
                break_minutes=cr.proposed_break_minutes or 0,
                note=cr.proposed_note,
                # #144 §4 ArbZG: materialise the documented break-exception on
                # the entry so the deviation stays auditable after approval.
                break_waiver_reason=cr.break_waiver_reason,
            )
            db.add(entry)
            db.flush()
            cr.time_entry_id = entry.id
            # #144 §4 ArbZG: if this CR materialises a break-waiver, mark the
            # audit source as 'break_waiver' so the waiver origin is traceable
            # consistently with the direct (non-approval) path.
            _create_audit_log(
                db, entry.id, cr.user_id, current_user.id,
                action="create", new_entry=entry,
                source=BREAK_WAIVER_SOURCE if cr.break_waiver_reason is not None else "change_request",
                change_request_id=cr.id,
                tenant_id=cr_tenant_id,
            )

        elif cr.request_type == ChangeRequestType.UPDATE:
            # entry already fetched in precondition check above
            # #201: clamp proposed times to the CR employee's soll window.
            _cr_user_te = db.query(User).filter(
                User.id == cr.user_id,
                User.tenant_id == cr.tenant_id,
            ).first()
            _grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
            eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(
                _cr_user_te, cr.proposed_date,
                cr.proposed_start_time, cr.proposed_end_time, _grace,
            )
            # #144 §4 ArbZG: mark the audit source as 'break_waiver' when this
            # CR carries a documented break-exception, mirroring the direct path.
            _create_audit_log(
                db, entry.id, cr.user_id, current_user.id,
                action="update", old_entry=entry,
                new_entry={
                    "date": cr.proposed_date,
                    "start_time": eff_start,
                    "end_time": eff_end,
                    "break_minutes": cr.proposed_break_minutes,
                    "note": cr.proposed_note,
                },
                source=BREAK_WAIVER_SOURCE if cr.break_waiver_reason is not None else "change_request",
                change_request_id=cr.id,
                tenant_id=cr_tenant_id,
            )
            entry.date = cr.proposed_date
            entry.start_time = eff_start
            entry.end_time = eff_end
            entry.raw_start_time = raw_start
            entry.raw_end_time = raw_end
            entry.break_minutes = cr.proposed_break_minutes if cr.proposed_break_minutes is not None else entry.break_minutes
            if cr.proposed_note is not None:
                entry.note = cr.proposed_note
            # #144 §4 ArbZG: carry the documented break-exception onto the entry.
            if cr.break_waiver_reason is not None:
                entry.break_waiver_reason = cr.break_waiver_reason

        elif cr.request_type == ChangeRequestType.DELETE:
            # entry already fetched in precondition check above
            _create_audit_log(
                db, entry.id, cr.user_id, current_user.id,
                action="delete", old_entry=entry,
                source="change_request", change_request_id=cr.id,
                tenant_id=cr_tenant_id,
            )
            db.delete(entry)

    # Absence CR actions
    # Fix #5: collect the years whose Betriebsferien must be re-split after this
    # approval — every VACATION-creating/-removing path triggers resplit so a
    # closure day can flip VACATION<->OVERTIME (toggle-gated, see end of fn).
    _resplit_years: set = set()
    if cr.entry_kind == "absence":
        if cr.request_type == ChangeRequestType.CREATE and existing_absence is not None:
            # Review R2-a: idempotent — an absence of the SAME type already
            # exists for this day (different types were rejected with 409 in the
            # precondition above). Approve the CR and link it to the existing
            # row instead of inserting a duplicate (which would violate
            # uq_tenant_user_date_type and 500/wedge the CR).
            cr.absence_id = existing_absence.id
            # Review R3: still record an audit row so the approval-against-an-
            # existing-absence stays traceable (§16) — every other CR branch
            # writes one; the idempotent link must not be the silent exception.
            audit = TimeEntryAuditLog(
                time_entry_id=None,
                user_id=cr.user_id,
                changed_by=current_user.id,
                action="create",
                new_date=existing_absence.date,
                new_start_time=existing_absence.start_time,
                new_end_time=existing_absence.end_time,
                new_note=(
                    f"absence:{existing_absence.type.value}:"
                    f"{float(existing_absence.hours)}h (link-existing)"
                ),
                source="change_request",
                change_request_id=cr.id,
                tenant_id=cr_tenant_id,
            )
            db.add(audit)
        elif cr.request_type == ChangeRequestType.CREATE:
            # CLAUDE.md / Tagesprinzip: Voll-Tag-Abwesenheitstypen buchen das
            # TAGESSOLL des Tages, NICHT den vom Antragsteller eingetragenen Wert
            # (8h-Client-Default). Nur der Überstundenausgleich (OVERTIME) behält
            # seine explizit beantragten Stunden — identisch zu create_absence
            # und review_vacation_request (die §3-EntgFG-Krank-Gutschrift ist
            # derselbe Tagessoll-Wert). Ohne diese Regel buchte ein per CR
            # genehmigter Urlaub die 8h und verbrauchte bei Teilzeit (4h/Tag)
            # doppelten Urlaub (8/4 = 2 Tage statt 1).
            cr_user = db.query(User).filter(User.id == cr.user_id, User.tenant_id == cr.tenant_id).first()
            _is_overtime = cr.proposed_absence_type == AbsenceType.OVERTIME.value
            if cr_user and (not _is_overtime or getattr(cr_user, "use_daily_schedule", False)):
                weekly = get_weekly_hours_for_date(db, cr_user, cr.proposed_date)
                hours = float(get_daily_target_for_date(cr_user, cr.proposed_date, weekly))
            else:
                hours = float(cr.proposed_absence_hours) if cr.proposed_absence_hours else 0

            # M-2: Urlaubsbudget-Prüfung VOR dem INSERT — wie review_vacation_request
            # und create_absence. Ohne diese Prüfung konnte ein per CR genehmigter
            # Urlaub das verbleibende Budget überziehen (der Direkt-Buchungs- und der
            # Antrags-Pfad prüfen, dieser nicht). Tagesprinzip (#156/#167): 1 freier
            # Arbeitstag = 1 Urlaubstag. Die CR bucht genau EINEN Tag (cr.proposed_date)
            # und kennt KEIN half_day-Feld → days_needed = 1,0 für einen abrechenbaren
            # Tag. Für use_daily_schedule+track_hours-User zählt ein 0h-Tag nicht.
            if (
                cr_user
                and cr.proposed_absence_type == AbsenceType.VACATION.value
                and cr.proposed_date
            ):
                _bill_day = True
                if getattr(cr_user, "use_daily_schedule", False) and cr_user.track_hours:
                    _bw = get_weekly_hours_for_date(db, cr_user, cr.proposed_date)
                    _bill_day = float(get_daily_target_for_date(cr_user, cr.proposed_date, _bw)) > 0
                if _bill_day:
                    vacation_account = get_vacation_account(db, cr_user, cr.proposed_date.year)
                    # #394: ein Halbtags-Sondertag (24./31.12.) kostet nur 0,5.
                    _cfg = special_days_service.get_special_day_config(db, cr_user.tenant_id, cr.proposed_date.year)
                    days_needed = float(half_special_day_weight(cr.proposed_date, _cfg))
                    if days_needed > vacation_account["remaining_days"] + 1e-9:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                f"Nicht genügend Urlaubstage für {cr.proposed_date.year} "
                                f"({vacation_account['remaining_days']:.1f} Tage verfügbar)"
                            ),
                        )

            new_absence = Absence(
                user_id=cr.user_id,
                tenant_id=cr_tenant_id,
                date=cr.proposed_date,
                type=AbsenceType(cr.proposed_absence_type),
                hours=hours,
                start_time=cr.proposed_start_time,
                end_time=cr.proposed_end_time,
                reason_id=cr.proposed_reason_id,  # #312: carry the custom reason through
            )
            db.add(new_absence)
            db.flush()
            cr.absence_id = new_absence.id

            # Fix #5: a newly materialised VACATION consumes budget the closure
            # split reserves up front → re-split that year.
            if new_absence.type == AbsenceType.VACATION and cr.proposed_date:
                _resplit_years.add(cr.proposed_date.year)

            # Fix #3: mirror create_absence — a newly materialised absence must
            # clear the day's time entries, otherwise the absence AND the time
            # entry both count → Ist/Saldo inflation. Audited (§16) with the CR
            # origin as source. The direct booking path does this; the CR
            # approval path previously did not.
            _delete_day_time_entries(
                db, cr.user_id, cr_tenant_id, cr.proposed_date, current_user.id, cr.id,
            )

            # Audit-Log für Absence-CR CREATE
            audit = TimeEntryAuditLog(
                time_entry_id=None,
                user_id=cr.user_id,
                changed_by=current_user.id,
                action="create",
                new_date=cr.proposed_date,
                new_start_time=cr.proposed_start_time,
                new_end_time=cr.proposed_end_time,
                new_note=f"absence:{cr.proposed_absence_type}:{hours}h",
                source="change_request",
                change_request_id=cr.id,
                tenant_id=cr_tenant_id,
            )
            db.add(audit)

        elif cr.request_type == ChangeRequestType.UPDATE:
            # absence already fetched in precondition check above
            # Fix #3: snapshot the pre-mutation date/type so we can clear the
            # target day's time entries when the absence moves to a new day or
            # changes into a full-day type (parity with create_absence).
            _orig_abs_date = absence.date
            _orig_abs_type = absence.type
            # M-4: Bei Datumswechsel prüfen, ob am Zieltag bereits eine andere
            # Abwesenheit liegt — sonst verletzt das UPDATE den Unique-Constraint
            # (tenant_id, user_id, date, type) und crasht mit 500. Spiegelt die
            # Existenz-Prüfung des CREATE-Pfads (Z.307-325); with_for_update()
            # schließt die Race zwischen Prüfung und Schreiben. Die eigene
            # Absence (absence.id) wird ausgeklammert.
            if cr.proposed_date and cr.proposed_date != absence.date:
                conflicting_absence = (
                    db.query(Absence)
                    .filter(
                        Absence.user_id == cr.user_id,
                        Absence.tenant_id == cr.tenant_id,
                        Absence.date == cr.proposed_date,
                        Absence.id != absence.id,
                    )
                    .with_for_update()
                    .first()
                )
                if conflicting_absence:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Am {cr.proposed_date.strftime('%d.%m.%Y')} existiert bereits "
                            f"eine Abwesenheit ({conflicting_absence.type.value})"
                        ),
                    )

            # Fix #4: Urlaubsbudget-Prüfung VOR der Mutation — der CREATE-Branch
            # prüft sie (M-2), der UPDATE-Branch tat es nicht → ein per CR
            # genehmigtes UPDATE auf VACATION (insb. Typwechsel→VACATION oder
            # Datumswechsel) konnte das Budget überziehen. Tagebasiert
            # (#156/#167). Self-Exclude: geprüft wird der NETTO-Neuverbrauch
            # (post − bisher schon gezählt) gegen den Rest des ZIEL-Jahres, damit
            # ein reiner Zeit-Edit eines bestehenden Urlaubstags (net_new=0) nicht
            # an einem evtl. negativen Rest scheitert.
            _bud_user = db.query(User).filter(
                User.id == cr.user_id, User.tenant_id == cr_tenant_id
            ).first()
            _target_type = (
                AbsenceType(cr.proposed_absence_type)
                if cr.proposed_absence_type else absence.type
            )
            _target_date = cr.proposed_date or absence.date
            if _bud_user and _target_type == AbsenceType.VACATION and _target_date:
                _target_year = _target_date.year
                _post_days = _vacation_day_contribution(
                    db, _bud_user, _target_date, absence.half_day
                )
                _current_days = (
                    _vacation_day_contribution(db, _bud_user, absence.date, absence.half_day)
                    if (absence.type == AbsenceType.VACATION
                        and absence.date.year == _target_year)
                    else 0.0
                )
                _net_new = _post_days - _current_days
                if _net_new > 1e-9:
                    _vac_acc = get_vacation_account(db, _bud_user, _target_year)
                    if _net_new > _vac_acc["remaining_days"] + 1e-9:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                f"Nicht genügend Urlaubstage für {_target_year} "
                                f"({_vac_acc['remaining_days']:.1f} Tage verfügbar)"
                            ),
                        )

            # Audit-Log für Absence-CR UPDATE (alte Werte sichern)
            audit = TimeEntryAuditLog(
                time_entry_id=None,
                user_id=cr.user_id,
                changed_by=current_user.id,
                action="update",
                old_date=absence.date,
                old_start_time=absence.start_time,
                old_end_time=absence.end_time,
                old_note=f"absence:{absence.type.value}:{float(absence.hours)}h",
                source="change_request",
                change_request_id=cr.id,
                tenant_id=cr_tenant_id,
            )

            if cr.proposed_absence_type:
                absence.type = AbsenceType(cr.proposed_absence_type)
            # #312: only set the reason when the CR actually carried one — mirror the
            # type guard above so an unrelated absence-UPDATE (no reason proposed)
            # does not silently clear an existing custom reason.
            if cr.proposed_reason_id is not None:
                absence.reason_id = cr.proposed_reason_id
            # H-1: Voll-Tag-Typen aufs Tagessoll des Tages umbuchen — identisch zum
            # CREATE-Pfad (Z.460-466), create_absence und review_vacation_request.
            # Bei Typwechsel (z.B. OVERTIME→VACATION) dürfen NICHT die alten
            # expliziten Stunden bleiben, sonst verbraucht Teilzeit (4h/Tag) bei
            # 8h doppelten Urlaub. Nur OVERTIME behält explizite Stunden.
            _upd_user = db.query(User).filter(
                User.id == cr.user_id, User.tenant_id == cr_tenant_id
            ).first()
            _upd_date = cr.proposed_date or absence.date
            _upd_is_overtime = absence.type == AbsenceType.OVERTIME
            if _upd_user and (not _upd_is_overtime or getattr(_upd_user, "use_daily_schedule", False)):
                _upd_weekly = get_weekly_hours_for_date(db, _upd_user, _upd_date)
                absence.hours = float(get_daily_target_for_date(_upd_user, _upd_date, _upd_weekly))
            elif cr.proposed_absence_hours is not None:
                absence.hours = float(cr.proposed_absence_hours)
            if cr.proposed_date:
                absence.date = cr.proposed_date
            absence.start_time = cr.proposed_start_time
            absence.end_time = cr.proposed_end_time

            # Neue Werte im Audit nachtragen
            audit.new_date = absence.date
            audit.new_start_time = absence.start_time
            audit.new_end_time = absence.end_time
            audit.new_note = f"absence:{absence.type.value}:{float(absence.hours)}h"
            db.add(audit)

            # Fix #3: when the absence moved to a new day or changed type, clear
            # the (new) target day's time entries so absence + entry don't
            # double-count (mirror create_absence). A pure time-only edit on the
            # same day/type leaves entries alone (they were cleared at creation).
            if absence.date != _orig_abs_date or absence.type != _orig_abs_type:
                _delete_day_time_entries(
                    db, cr.user_id, cr_tenant_id, absence.date, current_user.id, cr.id,
                )

            # Fix #5: a VACATION added or removed (type change) or moved (date
            # change) shifts the closure-split budget → re-split BOTH the old and
            # the new year when VACATION is involved on either side.
            if _orig_abs_type == AbsenceType.VACATION:
                _resplit_years.add(_orig_abs_date.year)
            if absence.type == AbsenceType.VACATION:
                _resplit_years.add(absence.date.year)

        elif cr.request_type == ChangeRequestType.DELETE:
            # Audit-Log für Absence-CR DELETE
            audit = TimeEntryAuditLog(
                time_entry_id=None,
                user_id=cr.user_id,
                changed_by=current_user.id,
                action="delete",
                old_date=absence.date,
                old_start_time=absence.start_time,
                old_end_time=absence.end_time,
                old_note=f"absence:{absence.type.value}:{float(absence.hours)}h",
                source="change_request",
                change_request_id=cr.id,
                tenant_id=cr_tenant_id,
            )
            db.add(audit)
            # Fix #1 (belt-and-suspenders): null any ChangeRequest still
            # referencing this absence before deleting it. The FK is ON DELETE
            # SET NULL on new DBs, but a not-yet-migrated install may still have
            # NO ACTION → the delete would FK-violate (500). Tenant-scoped.
            db.query(ChangeRequest).filter(
                ChangeRequest.absence_id == absence.id,
                ChangeRequest.tenant_id == cr_tenant_id,
            ).update({ChangeRequest.absence_id: None}, synchronize_session=False)
            # Fix #5: deleting a VACATION frees budget the closure split reserved
            # → a closure OVERTIME day can flip back to VACATION (capture the year
            # BEFORE delete, attributes expire afterwards).
            if absence.type == AbsenceType.VACATION:
                _resplit_years.add(absence.date.year)
            db.delete(absence)

    db.commit()
    db.refresh(cr)

    # Fix #5: re-split the affected years' Betriebsferien so closure days flip
    # VACATION<->OVERTIME after a VACATION-relevant approval — mirrors the direct
    # booking / vacation-request paths. Toggle-gated; the main commit above made
    # the absence change visible to the budget snapshot inside resplit.
    if _resplit_years and settings_service.get_bool_setting(
        db, "closure_overtime_after_vacation", cr_tenant_id, False
    ):
        for _yr in _resplit_years:
            resplit_year_closures(db, cr_tenant_id, _yr)
        db.commit()
        db.refresh(cr)

    cr_response = _enrich_cr_response(cr, db)

    # #376: weiche Kind-krank-Limit-Warnung (spiegelt create_absence). TOP-LEVEL —
    # NICHT im ArbZG-Block unten, der bei Ganztags-Absencen (kein proposed_start/
    # end_time) übersprungen würde. Deckt CREATE UND UPDATE-in-Kind-krank ab
    # (beide setzen absence.reason_id = cr.proposed_reason_id). Nicht blockierend.
    if (
        review.action == "approve"
        and cr.entry_kind == "absence"
        and cr.request_type in (ChangeRequestType.CREATE, ChangeRequestType.UPDATE)
        and cr.proposed_reason_id is not None
        and cr.proposed_date is not None
    ):
        cs_reason = db.query(AbsenceReason).filter(
            AbsenceReason.id == cr.proposed_reason_id,
            AbsenceReason.tenant_id == cr.tenant_id,  # F-026
        ).first()
        if cs_reason is not None and cs_reason.tracks_child_sick_limit:
            cs_user = db.query(User).filter(
                User.id == cr.user_id, User.tenant_id == cr.tenant_id
            ).first()
            if cs_user is not None:
                _cs_cap = child_sick_cap(db, cs_user)
                _cs_used = child_sick_days_used(db, cs_user, cr.proposed_date.year)
                if _cs_used > _cs_cap:
                    cr_response.warnings.append(
                        f"CHILD_SICK_LIMIT: Kind-krank-Anspruch überschritten "
                        f"({_cs_used:.1f} von {_cs_cap} Tagen {cr.proposed_date.year} verbraucht, §45 SGB V)."
                    )

    # NOTE: ArbZG warnings are informational and calculated post-commit.
    # Hard limits (§3 daily max, §4 breaks) are enforced at CR creation time.
    # §6 Abs. 2 / §3 ArbZG: Warnungen bei CREATE/UPDATE-Genehmigung
    if (
        review.action == "approve"
        and cr.request_type in (ChangeRequestType.CREATE, ChangeRequestType.UPDATE)
        and cr.proposed_start_time
        and cr.proposed_end_time
    ):
        cr_user = db.query(User).filter(User.id == cr.user_id, User.tenant_id == cr.tenant_id).first()
        if cr_user and not cr_user.exempt_from_arbzg:
            # §16/#201: assess the informational ArbZG warnings on the CREDITED
            # (clamped) time too — consistent with the §3/§4 hard re-check above
            # and the create/update paths. The CR stores the RAW proposed times.
            _wgrace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
            _w_start, _w_end, _, _ = work_window_service.clamp(
                cr_user, cr.proposed_date,
                cr.proposed_start_time, cr.proposed_end_time, _wgrace,
            )
            daily_hours_cr = _calculate_daily_net_hours(
                db=db,
                user_id=cr.user_id,
                entry_date=cr.proposed_date,
                start_time=_w_start,
                end_time=_w_end,
                break_minutes=cr.proposed_break_minutes or 0,
                tenant_id=cr.tenant_id,
            )

            # SS6 Abs. 2: Nachtarbeitnehmer-Tageslimit
            if (
                cr_user.is_night_worker
                and is_night_work(_w_start, _w_end)
                and daily_hours_cr > MAX_NIGHT_WORKER_DAILY_WARN
            ):
                cr_response.warnings.append(
                    f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours_cr:.1f}h). "
                    "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
                )

            # §3 ArbZG: Wochenarbeitszeit-Warnung (48h)
            weekly = _calculate_weekly_net_hours(
                db=db,
                user_id=cr.user_id,
                entry_date=cr.proposed_date,
                start_time=_w_start,
                end_time=_w_end,
                break_minutes=cr.proposed_break_minutes or 0,
                tenant_id=cr.tenant_id,
            )
            if weekly > MAX_WEEKLY_HOURS_WARN:
                cr_response.warnings.append(
                    f"§3 ArbZG: Wochenarbeitszeit {weekly:.1f}h überschreitet 48h-Grenze."
                )

    return cr_response


@router.post("/change-requests/bulk-review", response_model=ChangeRequestBulkReviewResult)
def bulk_review_change_requests(
    body: ChangeRequestBulkReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Approve or reject many change requests in one call. Each item runs through
    the same precondition checks as the single-review endpoint; failures for
    individual items (stale state, conflicts, non-pending status) are reported
    per-item but do not abort the remaining items.
    """
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Ungültige Aktion (approve/reject)")

    items: list[ChangeRequestBulkReviewItemResult] = []
    succeeded = 0
    failed = 0

    single_body = ChangeRequestReview(action=body.action, rejection_reason=body.rejection_reason)

    for request_id in body.request_ids:
        try:
            review_change_request(
                request_id=str(request_id),
                review=single_body,
                db=db,
                current_user=current_user,
            )
            items.append(ChangeRequestBulkReviewItemResult(
                request_id=request_id,
                status="approved" if body.action == "approve" else "rejected",
            ))
            succeeded += 1
        except HTTPException as exc:
            # N-4: each successful review_change_request commits before
            # returning, so this rollback only discards the FAILED item's
            # partial (un-committed) flush — earlier successes are already
            # persisted. Continue so the admin doesn't have to retry a 50-item
            # batch after one stale row.
            db.rollback()
            items.append(ChangeRequestBulkReviewItemResult(
                request_id=request_id,
                status="failed",
                error=str(exc.detail),
            ))
            failed += 1

    return ChangeRequestBulkReviewResult(
        succeeded=succeeded,
        failed=failed,
        items=items,
    )
