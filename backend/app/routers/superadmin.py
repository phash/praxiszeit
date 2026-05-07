"""Superadmin router.

Endpoints under /api/superadmin/* require a superadmin account (User with
tenant_id IS NULL) and are explicitly permitted to touch deactivated tenants
so that §16 ArbZG mandatory export / retention can still be served after a
customer tenant has been archived.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, set_superadmin_context
from app.middleware.auth import require_superadmin
from app.models import (
    Absence,
    ChangeRequest,
    TimeEntry,
    TimeEntryAuditLog,
    User,
)
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/superadmin",
    tags=["superadmin"],
    dependencies=[Depends(require_superadmin)],
)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _user_dict(u: User) -> dict:
    return {
        "id": str(u.id),
        "username": u.username,
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "role": u.role.value if hasattr(u.role, "value") else str(u.role),
        "weekly_hours": float(u.weekly_hours) if u.weekly_hours is not None else None,
        "is_active": u.is_active,
        "first_work_day": _iso(u.first_work_day),
        "last_work_day": _iso(u.last_work_day),
        "exempt_from_arbzg": u.exempt_from_arbzg,
        "is_night_worker": u.is_night_worker,
    }


def _time_entry_dict(te: TimeEntry) -> dict:
    return {
        "id": str(te.id),
        "user_id": str(te.user_id),
        "date": _iso(te.date),
        "start_time": _iso(te.start_time),
        "end_time": _iso(te.end_time),
        "break_minutes": te.break_minutes,
        "note": te.note,
        "sunday_exception_reason": te.sunday_exception_reason,
    }


def _absence_dict(a: Absence) -> dict:
    return {
        "id": str(a.id),
        "user_id": str(a.user_id),
        "date": _iso(a.date),
        "type": a.type.value if hasattr(a.type, "value") else str(a.type),
        "hours": float(a.hours) if a.hours is not None else None,
        "start_time": _iso(a.start_time),
        "end_time": _iso(a.end_time),
    }


def _audit_dict(log: TimeEntryAuditLog) -> dict:
    return {
        "id": str(log.id),
        "time_entry_id": str(log.time_entry_id) if log.time_entry_id else None,
        "user_id": str(log.user_id),
        "changed_by": str(log.changed_by),
        "action": log.action,
        "source": log.source,
        "created_at": _iso(log.created_at),
        "old_date": _iso(log.old_date),
        "old_start_time": _iso(log.old_start_time),
        "old_end_time": _iso(log.old_end_time),
        "old_break_minutes": log.old_break_minutes,
        "old_note": log.old_note,
        "new_date": _iso(log.new_date),
        "new_start_time": _iso(log.new_start_time),
        "new_end_time": _iso(log.new_end_time),
        "new_break_minutes": log.new_break_minutes,
        "new_note": log.new_note,
    }


@router.get("/tenants", response_model=List[dict])
def list_all_tenants(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    """List every tenant in the installation (active + deactivated)."""
    set_superadmin_context(db)
    query = db.query(Tenant)
    if not include_inactive:
        query = query.filter(Tenant.is_active == True)  # noqa: E712
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "is_active": t.is_active,
            "mode": t.mode,
        }
        for t in query.order_by(Tenant.name).all()
    ]


@router.get("/tenants/{tenant_id}/arbzg-export")
def export_tenant_arbzg_data(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """
    §16 ArbZG mandatory export of all retention-relevant records for one tenant.

    Works regardless of `tenants.is_active` so that a deactivated customer
    can still have their ≥2-year records produced on labour-inspection
    request. Returns a single JSON document streamed as a download.
    """
    set_superadmin_context(db)

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant nicht gefunden")

    users = db.query(User).filter(User.tenant_id == tenant_id).all()
    time_entries = db.query(TimeEntry).filter(TimeEntry.tenant_id == tenant_id).all()
    absences = db.query(Absence).filter(Absence.tenant_id == tenant_id).all()
    audit_logs = (
        db.query(TimeEntryAuditLog)
        .filter(TimeEntryAuditLog.tenant_id == tenant_id)
        .order_by(TimeEntryAuditLog.created_at.desc())
        .all()
    )

    payload = {
        "export_generated_at": datetime.now(timezone.utc).isoformat(),
        "export_generated_by": str(current_user.id),
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "is_active": tenant.is_active,
            "mode": tenant.mode,
        },
        "users": [_user_dict(u) for u in users],
        "time_entries": [_time_entry_dict(t) for t in time_entries],
        "absences": [_absence_dict(a) for a in absences],
        "audit_logs": [_audit_dict(log) for log in audit_logs],
    }

    # Record the export itself in the audit log so a labour inspector can
    # verify who pulled the records and when.
    marker = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=current_user.id,
        changed_by=current_user.id,
        action="arbzg_superadmin_export",
        source="dsgvo",
        new_note=(
            f"Superadmin export of tenant {tenant.name} "
            f"(users={len(users)}, time_entries={len(time_entries)}, "
            f"absences={len(absences)}, audit_logs={len(audit_logs)})"
        ),
        tenant_id=tenant_id,
    )
    db.add(marker)
    db.commit()

    buffer = BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    filename = f"PraxisZeit_ArbZG-Export_{tenant.slug}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return StreamingResponse(
        buffer,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tenants-overview")
def tenants_overview(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
    status_filter: str | None = Query(None, pattern="^(active|trial|past_due|suspended|canceled)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Paginated tenant listing for the Superadmin Dashboard (Phase 7).

    Returns plan, status, trial-days-remaining, active-seats, MRR-contribution.
    """
    from app.services.metrics_refresh import _PLAN_MONTHLY_CENTS
    set_superadmin_context(db)
    q = db.query(Tenant)
    if status_filter == "trial":
        q = q.filter(Tenant.plan == "trial")
    elif status_filter in {"active", "past_due", "suspended", "canceled"}:
        q = q.filter(Tenant.subscription_status == status_filter)

    total = q.count()
    rows = q.order_by(Tenant.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    now = datetime.now(timezone.utc)
    out = []
    for t in rows:
        seats = (
            db.query(User)
            .filter(User.tenant_id == t.id, User.is_active == True)  # noqa: E712
            .count()
        )
        trial_days_left = None
        if t.plan == "trial" and t.trial_ends_at:
            ends = t.trial_ends_at if t.trial_ends_at.tzinfo else t.trial_ends_at.replace(tzinfo=timezone.utc)
            trial_days_left = max(0, (ends - now).days)
        mrr_contrib = 0
        if t.plan in _PLAN_MONTHLY_CENTS and t.subscription_status == "active":
            mrr_contrib = _PLAN_MONTHLY_CENTS[t.plan] * max(1, seats)
        out.append({
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "plan": t.plan,
            "subscription_status": t.subscription_status,
            "seats": seats,
            "seat_limit": t.seat_limit,
            "trial_ends_at": t.trial_ends_at.isoformat() if t.trial_ends_at else None,
            "trial_days_left": trial_days_left,
            "mrr_cents": mrr_contrib,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "deletion_requested_at": t.deletion_requested_at.isoformat() if t.deletion_requested_at else None,
            "anonymized_at": t.anonymized_at.isoformat() if t.anonymized_at else None,
        })
    return {"total": total, "page": page, "per_page": per_page, "tenants": out}


@router.get("/metrics/mrr")
def mrr_details(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Detailed MRR breakdown for dashboard KPIs."""
    from app.services.metrics_refresh import compute_mrr_details
    set_superadmin_context(db)
    return compute_mrr_details(db)


@router.post("/cron/metrics-refresh")
def cron_metrics_refresh(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Recompute per-tenant Prometheus gauges + billing KPIs."""
    from app.services.metrics_refresh import refresh_all
    set_superadmin_context(db)
    return refresh_all(db)


@router.post("/cron/trial-check")
def cron_trial_check(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Suspend tenants whose trial has expired AND who have no Stripe
    subscription. Called by an external cron; exposed under superadmin
    so only an authenticated operator can trigger it manually. The
    Stripe-webhook in Phase 4 will be the self-healing inverse (reactivate)."""
    from app.services.signup_service import suspend_expired_trials
    from app.services.stripe_service import suspend_canceled_after_grace
    from app.services.lifecycle_service import (
        apply_scheduled_suspends,
        apply_scheduled_deletions,
        purge_expired_vacation_audit_logs,
    )
    trials = suspend_expired_trials(db)
    canceled = suspend_canceled_after_grace(db)
    scheduled = apply_scheduled_suspends(db)
    anonymized = apply_scheduled_deletions(db)
    audit_purged = purge_expired_vacation_audit_logs(db)
    return {
        "suspended_trials": trials,
        "suspended_canceled": canceled,
        "suspended_scheduled": scheduled,
        "anonymized_tenants": anonymized,
        "vacation_audit_purged": audit_purged,
    }
