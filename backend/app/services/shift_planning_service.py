"""Service helpers for Schichtplanung (#305).

Pure-ish helpers kept out of the router: the soft under-staffing validation and
the "my shifts today" resolution (union of the user's assignments across all
*active* plans for today's weekday in Europe/Berlin).

Reminder: this feature is a planning artefact only — nothing here touches the
ArbZG / Soll-Ist calculation model.
"""
from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.shift_planning import (
    ShiftPlan,
    ShiftSlot,
    ShiftAssignment,
    Workstation,
    Location,
    WorkstationQualification,
)
from app.services.timezone_service import today_local


def qualified_user_ids(db: Session, tenant_id, workstation_id) -> set:
    """Set of user-ids (as str) trained/qualified for a workstation (#305 M2d)."""
    rows = (
        db.query(WorkstationQualification.user_id)
        .filter(
            WorkstationQualification.tenant_id == tenant_id,
            WorkstationQualification.workstation_id == workstation_id,
        )
        .all()
    )
    return {str(r[0]) for r in rows}


def is_understaffed(min_staff: int, assignment_count: int) -> bool:
    """A slot is under-staffed when it requires staff and has too few assigned.

    ``min_staff == 0`` means "no minimum" → never under-staffed. The flag is a
    soft warning; it never blocks saving or activating a plan.
    """
    return min_staff > 0 and assignment_count < min_staff


def _hhmm(t) -> str:
    """Format a ``datetime.time`` as ``HH:MM`` (no seconds)."""
    return t.strftime("%H:%M")


def get_my_today(db: Session, user) -> dict:
    """Return the logged-in user's shift assignments for *today*.

    Resolution: today's weekday (Europe/Berlin) × all **active** plans of the
    tenant × slots the user is assigned to. Multiple active plans are unioned.
    """
    today = today_local()
    weekday = today.weekday()
    tid = user.tenant_id

    rows = (
        db.query(
            ShiftPlan.id.label("plan_id"),
            ShiftPlan.name.label("plan_name"),
            ShiftSlot.start_time.label("start_time"),
            ShiftSlot.end_time.label("end_time"),
            Workstation.name.label("workstation_name"),
            Location.name.label("location_name"),
        )
        .join(ShiftSlot, ShiftSlot.shift_plan_id == ShiftPlan.id)
        .join(ShiftAssignment, ShiftAssignment.shift_slot_id == ShiftSlot.id)
        .join(Workstation, ShiftSlot.workstation_id == Workstation.id)
        .outerjoin(Location, Workstation.location_id == Location.id)
        .filter(
            ShiftPlan.tenant_id == tid,
            ShiftPlan.is_active.is_(True),
            ShiftSlot.tenant_id == tid,
            ShiftSlot.weekday == weekday,
            ShiftAssignment.tenant_id == tid,
            ShiftAssignment.user_id == user.id,
        )
        .order_by(ShiftSlot.start_time, ShiftSlot.end_time)
        .all()
    )

    entries: List[dict] = [
        {
            "plan_id": str(r.plan_id),
            "plan_name": r.plan_name,
            "workstation_name": r.workstation_name,
            "location_name": r.location_name,
            "start_time": _hhmm(r.start_time),
            "end_time": _hhmm(r.end_time),
        }
        for r in rows
    ]

    return {
        "date": today.isoformat(),
        "weekday": weekday,
        "entries": entries,
    }
