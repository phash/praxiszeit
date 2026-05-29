"""Admin sub-router: Admin Time Entry CRUD + Audit Log."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.services.date_filters import date_in_year, date_in_month
from sqlalchemy import extract
from typing import List, Optional
from app.database import get_db
from app.models import User, TimeEntry, TimeEntryAuditLog
from app.middleware.auth import require_admin
from app.schemas.time_entry import TimeEntryCreate, TimeEntryResponse, TimeEntryUpdate
from app.schemas.time_entry_audit_log import AuditLogResponse
from app.routers.admin_helpers import _create_audit_log, _enrich_audit_response, _enrich_audit_responses
from app.services.break_validation_service import validate_daily_break
from app.routers.time_entries import (
    _calculate_daily_net_hours, _calculate_weekly_net_hours,
    MAX_DAILY_HOURS_HARD, MAX_DAILY_HOURS_WARN, MAX_NIGHT_WORKER_DAILY_WARN, MAX_WEEKLY_HOURS_WARN,
    BREAK_WAIVER_SOURCE,
)
from app.services.arbzg_utils import is_night_work

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ── Admin Time Entry Management ─────────────────────────────────────────

@router.post("/users/{user_id}/time-entries", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED)
def admin_create_time_entry(
    user_id: str,
    entry_data: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin creates a time entry for an employee."""
    # F-026: explicit tenant scoping on user lookup (don't rely on RLS alone)
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user.tenant_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    admin_create_warnings: list[str] = []
    waiver_reason = (entry_data.break_waiver_reason or "").strip()
    break_waiver_active = False
    if not user.exempt_from_arbzg:
        # Break validation (§4 ArbZG)
        break_error = validate_daily_break(
            db=db, user_id=user.id, entry_date=entry_data.date,
            start_time=entry_data.start_time, end_time=entry_data.end_time,
            break_minutes=entry_data.break_minutes,
        )
        if break_error:
            # M-ARB3: parity with the employee path (#144) — a documented break
            # waiver lets the admin record the §4 deviation instead of being
            # hard-blocked. §3 (10h hard cap, below) is checked afterwards and
            # is NOT waivable.
            if not waiver_reason:
                raise HTTPException(status_code=400, detail=break_error)
            break_waiver_active = True
            admin_create_warnings.append(f"BREAK_WAIVER: {break_error}")

        # SS3 ArbZG: daily hours hard limit
        daily_hours = _calculate_daily_net_hours(
            db=db, user_id=user.id, entry_date=entry_data.date,
            start_time=entry_data.start_time, end_time=entry_data.end_time,
            break_minutes=entry_data.break_minutes,
        )
        if daily_hours > MAX_DAILY_HOURS_HARD:
            raise HTTPException(
                status_code=422,
                detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
            )

        # §3 ArbZG: Warnung bei Überschreitung der Regelgrenze (8h)
        if daily_hours > MAX_DAILY_HOURS_WARN:
            admin_create_warnings.append(f"DAILY_HOURS_WARNING: Tagesarbeitszeit beträgt {daily_hours:.1f}h (>{MAX_DAILY_HOURS_WARN}h)")

        # §3 ArbZG: Warnung bei Überschreitung der 48h-Wochengrenze
        weekly_hours = _calculate_weekly_net_hours(
            db=db, user_id=user.id, entry_date=entry_data.date,
            start_time=entry_data.start_time, end_time=entry_data.end_time,
            break_minutes=entry_data.break_minutes,
        )
        if weekly_hours > MAX_WEEKLY_HOURS_WARN:
            admin_create_warnings.append(f"WEEKLY_HOURS_WARNING: Wochenarbeitszeit beträgt {weekly_hours:.1f}h (>{MAX_WEEKLY_HOURS_WARN}h, §3 ArbZG)")

        # SS6 Abs. 2 ArbZG: Warnung für Nachtarbeitnehmer
        if (
            user.is_night_worker
            and is_night_work(entry_data.start_time, entry_data.end_time)
            and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            admin_create_warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    entry = TimeEntry(
        user_id=user.id,
        tenant_id=current_user.tenant_id,
        date=entry_data.date,
        start_time=entry_data.start_time,
        end_time=entry_data.end_time,
        break_minutes=entry_data.break_minutes,
        note=entry_data.note,
        break_waiver_reason=waiver_reason if break_waiver_active else None,
    )
    db.add(entry)
    db.flush()

    _create_audit_log(
        db, entry.id, user.id, current_user.id,
        action="create", new_entry=entry,
        source=BREAK_WAIVER_SOURCE if break_waiver_active else "manual",
        tenant_id=current_user.tenant_id,
    )

    db.commit()
    db.refresh(entry)
    response = TimeEntryResponse.model_validate(entry)
    response.warnings = admin_create_warnings
    return response


@router.put("/time-entries/{entry_id}", response_model=TimeEntryResponse)
def admin_update_time_entry(
    entry_id: str,
    entry_data: TimeEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin updates a time entry with audit logging."""
    # F-028: lock the row so two concurrent admin edits can't race between
    # validation and apply — otherwise state-B is written while state-A was
    # validated.
    entry = (
        db.query(TimeEntry)
        .filter(
            TimeEntry.id == entry_id,
            TimeEntry.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Get user for SS18 exempt check and night worker warning
    affected_user = db.query(User).filter(User.id == entry.user_id).first()

    # Use provided values or fall back to existing
    update_date = entry_data.date if entry_data.date is not None else entry.date
    update_start_time = entry_data.start_time if entry_data.start_time is not None else entry.start_time
    update_end_time = entry_data.end_time if entry_data.end_time is not None else entry.end_time
    update_break_minutes = entry_data.break_minutes if entry_data.break_minutes is not None else entry.break_minutes

    admin_update_warnings: list[str] = []
    waiver_reason = (entry_data.break_waiver_reason or "").strip()
    break_waiver_active = False
    if not affected_user or not affected_user.exempt_from_arbzg:
        # Break validation (§4 ArbZG)
        break_error = validate_daily_break(
            db=db, user_id=entry.user_id, entry_date=update_date,
            start_time=update_start_time, end_time=update_end_time,
            break_minutes=update_break_minutes, exclude_entry_id=entry.id,
        )
        if break_error:
            # M-ARB3: parity with the employee path (#144) — documented waiver
            # records the §4 deviation instead of a hard 400. §3 (below) stays
            # a hard cap.
            if not waiver_reason:
                raise HTTPException(status_code=400, detail=break_error)
            break_waiver_active = True
            admin_update_warnings.append(f"BREAK_WAIVER: {break_error}")

        # SS3 ArbZG: daily hours hard limit
        daily_hours = _calculate_daily_net_hours(
            db=db, user_id=entry.user_id, entry_date=update_date,
            start_time=update_start_time, end_time=update_end_time,
            break_minutes=update_break_minutes, exclude_entry_id=entry.id,
        )
        if daily_hours > MAX_DAILY_HOURS_HARD:
            raise HTTPException(
                status_code=422,
                detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
            )

        # §3 ArbZG: Warnung bei Überschreitung der Regelgrenze (8h)
        if daily_hours > MAX_DAILY_HOURS_WARN:
            admin_update_warnings.append(f"DAILY_HOURS_WARNING: Tagesarbeitszeit beträgt {daily_hours:.1f}h (>{MAX_DAILY_HOURS_WARN}h)")

        # §3 ArbZG: Warnung bei Überschreitung der 48h-Wochengrenze
        weekly_hours = _calculate_weekly_net_hours(
            db=db, user_id=entry.user_id, entry_date=update_date,
            start_time=update_start_time, end_time=update_end_time,
            break_minutes=update_break_minutes, exclude_entry_id=entry.id,
        )
        if weekly_hours > MAX_WEEKLY_HOURS_WARN:
            admin_update_warnings.append(f"WEEKLY_HOURS_WARNING: Wochenarbeitszeit beträgt {weekly_hours:.1f}h (>{MAX_WEEKLY_HOURS_WARN}h, §3 ArbZG)")

        # SS6 Abs. 2 ArbZG: Warnung für Nachtarbeitnehmer
        if (
            affected_user
            and affected_user.is_night_worker
            and is_night_work(update_start_time, update_end_time)
            and daily_hours > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            admin_update_warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

    # Create audit log before changing
    _create_audit_log(
        db, entry.id, entry.user_id, current_user.id,
        action="update", old_entry=entry,
        new_entry={
            "date": update_date,
            "start_time": update_start_time,
            "end_time": update_end_time,
            "break_minutes": update_break_minutes,
            "note": entry_data.note if entry_data.note is not None else entry.note,
        },
        source=BREAK_WAIVER_SOURCE if break_waiver_active else "manual",
        tenant_id=current_user.tenant_id,
    )

    # Apply only provided updates
    if entry_data.date is not None:
        entry.date = entry_data.date
    if entry_data.start_time is not None:
        entry.start_time = entry_data.start_time
    if entry_data.end_time is not None:
        entry.end_time = entry_data.end_time
    if entry_data.break_minutes is not None:
        entry.break_minutes = entry_data.break_minutes
    if entry_data.note is not None:
        entry.note = entry_data.note
    # M-ARB3: persist the documented §4 break waiver when one was supplied.
    if break_waiver_active:
        entry.break_waiver_reason = waiver_reason

    db.commit()
    db.refresh(entry)

    response = TimeEntryResponse.model_validate(entry)
    response.warnings = admin_update_warnings
    return response


@router.delete("/time-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_time_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin deletes a time entry with audit logging."""
    # F-026: explicit tenant scope so a guessed UUID from another tenant 404s.
    # F-028/S-M04: lock the row so a concurrent edit/delete can't race between
    # the lookup and the db.delete() below. Mirrors admin_update_time_entry.
    entry = (
        db.query(TimeEntry)
        .filter(
            TimeEntry.id == entry_id,
            TimeEntry.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    _create_audit_log(
        db, entry.id, entry.user_id, current_user.id,
        action="delete", old_entry=entry, source="manual",
        tenant_id=current_user.tenant_id,
    )

    db.delete(entry)
    db.commit()
    return None


# ── Audit Log ────────────────────────────────────────────────────────────

@router.get("/audit-log", response_model=List[AuditLogResponse])
def list_audit_log(
    user_id: Optional[str] = Query(None, description="Filter by affected user"),
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    before: Optional[str] = Query(
        None,
        description="Keyset cursor — ISO-8601 timestamp; return entries strictly older than this",
    ),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    List audit log entries.

    F-054: Supports two pagination modes — cursor-based (preferred) and
    offset-based (legacy). The audit log grows indefinitely; OFFSET N on
    a table with 100k+ rows forces Postgres to materialise and discard N
    rows on every page load, so the admin UI should switch to the
    ``before`` cursor ASAP. Pass the ``created_at`` of the last row from
    the previous page as ``before`` to fetch the next older page.
    """
    # F-026: explicit tenant scoping on top of RLS — the audit log carries the
    # most sensitive cross-tenant data (old/new note text, user ids).
    query = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == current_user.tenant_id
    )

    if user_id:
        query = query.filter(TimeEntryAuditLog.user_id == user_id)

    if month:
        try:
            year, month_num = map(int, month.split('-'))
            query = query.filter(
                date_in_month(TimeEntryAuditLog.created_at, year, month_num),
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if before:
        # Keyset pagination: skip OFFSET entirely, use a strict ``<`` on
        # the indexed created_at column.
        try:
            from datetime import datetime as _dt
            before_ts = _dt.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Ungültiges 'before' Format (ISO-8601 erwartet)",
            )
        query = query.filter(TimeEntryAuditLog.created_at < before_ts)
        logs = (
            query.order_by(TimeEntryAuditLog.created_at.desc())
            .limit(limit)
            .all()
        )
    else:
        # Legacy offset-based path — kept for backward compatibility with
        # the current frontend. Grows linearly with page index, deprecated
        # once the UI switches to 'before'.
        logs = (
            query.order_by(TimeEntryAuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
    return _enrich_audit_responses(logs, db)
