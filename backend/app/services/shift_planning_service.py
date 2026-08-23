"""Service helpers for Schichtplanung (#305).

Pure-ish helpers kept out of the router: the soft under-staffing validation and
the "my shifts today" resolution (union of the user's assignments across all
*active* plans for today's weekday in Europe/Berlin).

Reminder: this feature is a planning artefact only — nothing here touches the
ArbZG / Soll-Ist calculation model.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import or_, and_
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
from app.services import settings_service

# #371: configurable planning weekdays (0=Mo … 6=So). Default Mo–Fr.
WEEKDAYS_SETTING_KEY = "shift_planning_weekdays"
DEFAULT_WEEKDAYS = [0, 1, 2, 3, 4]


def parse_weekdays(raw) -> List[int]:
    """Parse a CSV weekday string ("0,2,4") into a sorted, deduped list of
    ints in 0..6. Returns ``DEFAULT_WEEKDAYS`` on empty/garbage input so a
    broken setting never leaves the planner with zero days."""
    if not raw:
        return list(DEFAULT_WEEKDAYS)
    days = set()
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError:
            return list(DEFAULT_WEEKDAYS)
        if not 0 <= n <= 6:
            return list(DEFAULT_WEEKDAYS)
        days.add(n)
    if not days:
        return list(DEFAULT_WEEKDAYS)
    return sorted(days)


def get_planning_weekdays(db: Session, tenant_id) -> List[int]:
    """Configured planning weekdays for the tenant (0=Mo … 6=So), Default Mo–Fr."""
    raw = settings_service.get_setting(db, WEEKDAYS_SETTING_KEY, tenant_id=tenant_id, default=None)
    return parse_weekdays(raw)


def is_weekday_enabled(db: Session, tenant_id, weekday: int) -> bool:
    """True if ``weekday`` is an enabled planning day for the tenant."""
    return weekday in get_planning_weekdays(db, tenant_id)


def is_plan_active_on(plan, d) -> bool:
    """#305 M2: a plan is active on date ``d`` if manually is_active OR its
    optional date window covers ``d`` (NULL = open grenze; the window only
    counts when at least one bound is set)."""
    if plan.is_active:
        return True
    frm, until = plan.active_from_date, plan.active_until_date
    if frm is None and until is None:
        return False
    return (frm is None or frm <= d) and (until is None or until >= d)


def is_plan_visible_to(plan, d, is_admin: bool) -> bool:
    """#443: Darf dieser Nutzer den Plan sehen?

    Admins sehen jeden Plan ihres Mandanten. Für alle anderen gilt: der Plan ist
    an ``d`` aktiv ODER er wurde ausdrücklich für Mitarbeitende freigegeben.

    Diese Funktion ist die EINZIGE Quelle der Regel. ``list_plans`` und
    ``get_plan`` hatten bis #443 je eine eigene Inline-Kopie — genau das Muster,
    das im Projekt schon mehrfach auseinandergelaufen ist (CR-Genehmigung,
    Feiertags-Guard). Eine neue Lesefläche ruft diesen Helfer, sie baut die
    Bedingung nicht nach.
    """
    if is_admin:
        return True
    return is_plan_active_on(plan, d) or bool(plan.visible_to_employees)


def plan_active_filter(d):
    """SQLAlchemy filter expression equivalent to ``is_plan_active_on`` for date ``d``."""
    has_window = or_(ShiftPlan.active_from_date.isnot(None), ShiftPlan.active_until_date.isnot(None))
    in_window = and_(
        or_(ShiftPlan.active_from_date.is_(None), ShiftPlan.active_from_date <= d),
        or_(ShiftPlan.active_until_date.is_(None), ShiftPlan.active_until_date >= d),
    )
    return or_(ShiftPlan.is_active.is_(True), and_(has_window, in_window))


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

    # #371: a weekday switched off in the planner has no shifts — don't surface a
    # legacy assignment left over from when it was enabled.
    if not is_weekday_enabled(db, tid, weekday):
        return {"date": today.isoformat(), "weekday": weekday, "entries": []}

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
            plan_active_filter(today),
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
