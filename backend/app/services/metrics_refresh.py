"""Background refresh of per-tenant gauges + billing KPIs
(Phase 7 / Issue #98).

These gauges can't be point-in-time updated by request handlers (DAU,
employee count, storage are SELECT COUNT queries). The operator cron
invokes /api/superadmin/cron/metrics-refresh once per day/hour.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User
from app.models.tenant import Tenant
from app.services.tenant_metrics import (
    praxiszeit_active_tenants,
    praxiszeit_mrr_cents,
    praxiszeit_tenant_dau,
    praxiszeit_tenant_employees,
    praxiszeit_tenant_storage_bytes,
    praxiszeit_trial_tenants,
)


# Monthly price in cents per plan. Kept in-code (not DB) because we
# always want the RESOURCE price, not whatever discount a single tenant
# negotiated — MRR should reflect steady-state revenue.
_PLAN_MONTHLY_CENTS: dict[str, int] = {
    "starter": 1900,   # €19 / seat / month
    "pro": 3900,       # €39 / seat / month
    "enterprise": 0,   # per-contract, don't double-count in public MRR
}


def refresh_all(db: Session) -> dict[str, float]:
    """Recompute every tenant-labelled gauge + aggregate KPIs. Returns a
    summary dict for logging."""
    tenants = db.query(Tenant).filter(Tenant.is_active == True).all()  # noqa: E712

    # Per-tenant employee counts
    for t in tenants:
        count = (
            db.query(User)
            .filter(User.tenant_id == t.id, User.is_active == True)  # noqa: E712
            .count()
        )
        praxiszeit_tenant_employees.labels(tenant_id=str(t.id)).set(count)

    # DAU: users who appeared in any TimeEntry in the last 24 h.
    from app.models import TimeEntry
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    since_date = since.date()
    dau_rows = (
        db.query(TimeEntry.tenant_id, func.count(func.distinct(TimeEntry.user_id)))
        .filter(TimeEntry.date >= since_date)
        .group_by(TimeEntry.tenant_id)
        .all()
    )
    dau_by_tid = {str(tid): count for tid, count in dau_rows}
    for t in tenants:
        praxiszeit_tenant_dau.labels(tenant_id=str(t.id)).set(dau_by_tid.get(str(t.id), 0))

    # Storage: row count × guesstimate 200 bytes/row. Cheap proxy; good
    # enough for a dashboard trend line. Don't JOIN pg_total_relation_size
    # because that requires superuser perms inside Postgres.
    for t in tenants:
        te = db.query(TimeEntry).filter(TimeEntry.tenant_id == t.id).count()
        praxiszeit_tenant_storage_bytes.labels(tenant_id=str(t.id)).set(te * 200)

    # Aggregates
    active_tenants = [t for t in tenants if t.subscription_status == "active"]
    trial_tenants = [t for t in tenants if t.plan == "trial"]
    praxiszeit_active_tenants.set(len(active_tenants))
    praxiszeit_trial_tenants.set(len(trial_tenants))

    # MRR: sum of monthly prices × seats for active non-trial tenants.
    mrr = 0
    for t in active_tenants:
        if t.plan == "trial" or t.plan == "enterprise":
            continue
        seats = (
            db.query(User)
            .filter(User.tenant_id == t.id, User.is_active == True)  # noqa: E712
            .count()
        )
        mrr += _PLAN_MONTHLY_CENTS.get(t.plan, 0) * max(1, seats)
    praxiszeit_mrr_cents.set(mrr)

    return {
        "tenants": len(tenants),
        "active_tenants": len(active_tenants),
        "trial_tenants": len(trial_tenants),
        "mrr_cents": mrr,
    }


def compute_mrr_details(db: Session) -> dict:
    """Return a more detailed MRR breakdown for the superadmin dashboard."""
    by_plan = {"starter": 0, "pro": 0, "enterprise": 0}
    for t in db.query(Tenant).filter(
        Tenant.is_active == True,  # noqa: E712
        Tenant.subscription_status == "active",
    ).all():
        if t.plan in by_plan:
            seats = (
                db.query(User)
                .filter(User.tenant_id == t.id, User.is_active == True)  # noqa: E712
                .count()
            )
            by_plan[t.plan] += _PLAN_MONTHLY_CENTS.get(t.plan, 0) * max(1, seats)

    mrr_cents = by_plan["starter"] + by_plan["pro"]
    return {
        "mrr_cents": mrr_cents,
        "arr_cents": mrr_cents * 12,
        "by_plan": by_plan,
    }
