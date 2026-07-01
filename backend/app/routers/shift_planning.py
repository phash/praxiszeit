"""Schichtplanung (shift planning) router — Issue #305.

A pure planning artefact: weekly templates assigning employees to workstations
in time slots. Decoupled from the ArbZG / time-tracking calculation model.

The whole router is gated behind the tenant setting ``shift_planning_enabled``
(Default off): when the flag is off, every endpoint returns 404 so the feature
feels absent. Write endpoints additionally require admin. Read endpoints are
available to any authenticated user (read-only view + dashboard).
"""
import re
from datetime import date, time, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.shift_planning import (
    Location,
    Workstation,
    ShiftPlan,
    ShiftSlot,
    ShiftAssignment,
    WorkstationQualification,
)
from app.services import settings_service, shift_planning_service, shift_planning_generator
from app.services.timezone_service import today_local

# Hex colour `#RRGGBB` — the workstation colour column is String(7); anything
# longer would StringDataRightTruncation (500) on Postgres (SQLite tests don't
# enforce varchar length), so validate format + length at the edge.
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _commit_or_conflict(db: Session, detail: str) -> None:
    """Commit, translating a unique-constraint violation into a clean 409.

    The create/update endpoints pre-check names with a SELECT, but two admins
    racing on the same new name can both pass the check and then collide on the
    ``uq_tenant_*_name`` constraint at COMMIT. Without this guard the loser gets
    a 500 instead of the advertised 409 (no data is corrupted either way).
    """
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def require_shift_planning_enabled(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """Gate: 404 when the tenant has not enabled shift planning (Default off)."""
    if not settings_service.get_bool_setting(
        db, "shift_planning_enabled", tenant_id=current_user.tenant_id, default=False
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schichtplanung ist nicht aktiviert",
        )
    return current_user


router = APIRouter(
    prefix="/api/shift-planning",
    tags=["shift-planning"],
    dependencies=[Depends(require_shift_planning_enabled)],
)


# ─── schemas ─────────────────────────────────────────────────────────


class LocationIn(BaseModel):
    name: str
    sort_order: int = 0


class WorkstationIn(BaseModel):
    name: str
    location_id: Optional[UUID] = None
    color: Optional[str] = None
    sort_order: int = 0

    @field_validator("color")
    @classmethod
    def _hex_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip()
        if not _HEX_COLOR_RE.match(v):
            raise ValueError("Farbe muss im Format #RRGGBB angegeben werden")
        return v


class PlanIn(BaseModel):
    name: str
    description: Optional[str] = None
    active_from_date: Optional[date] = None
    active_until_date: Optional[date] = None


class PlanDuplicateIn(BaseModel):
    name: str  # #338: Name der Kopie


class SlotIn(BaseModel):
    workstation_id: UUID
    weekday: int
    start_time: time
    end_time: time
    min_staff: int = 0

    @field_validator("weekday")
    @classmethod
    def _weekday_range(cls, v: int) -> int:
        if not 0 <= v <= 6:
            raise ValueError("weekday muss zwischen 0 (Montag) und 6 (Sonntag) liegen")
        return v

    @field_validator("min_staff")
    @classmethod
    def _min_staff_nonneg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Mindestbesetzung darf nicht negativ sein")
        return v


class AssignmentsIn(BaseModel):
    user_ids: List[UUID]


class QualificationsIn(BaseModel):
    workstation_ids: List[UUID]


class GenerateIn(BaseModel):
    target_monday: date
    mode: str = "replace"

    @field_validator("mode")
    @classmethod
    def _mode_valid(cls, v: str) -> str:
        if v not in ("replace", "fill_gaps"):
            raise ValueError("mode muss 'replace' oder 'fill_gaps' sein")
        return v


# ─── serializers ─────────────────────────────────────────────────────


def _hhmm(t: time) -> str:
    return t.strftime("%H:%M")


def _loc_dict(loc: Location) -> dict:
    return {"id": str(loc.id), "name": loc.name, "sort_order": loc.sort_order}


def _ws_dict(ws: Workstation, location_name: Optional[str]) -> dict:
    return {
        "id": str(ws.id),
        "name": ws.name,
        "location_id": str(ws.location_id) if ws.location_id else None,
        "location_name": location_name,
        "color": ws.color,
        "sort_order": ws.sort_order,
    }


def _slot_dict(slot: ShiftSlot, ws: Optional[Workstation], assignments: List[dict]) -> dict:
    return {
        "id": str(slot.id),
        "workstation_id": str(slot.workstation_id),
        "workstation_name": ws.name if ws else None,
        "color": ws.color if ws else None,
        "weekday": slot.weekday,
        "start_time": _hhmm(slot.start_time),
        "end_time": _hhmm(slot.end_time),
        "min_staff": slot.min_staff,
        "understaffed": shift_planning_service.is_understaffed(slot.min_staff, len(assignments)),
        # #305 M2d: slot has ≥1 person not trained for its workstation (soft).
        "unqualified": any(not a.get("qualified", True) for a in assignments),
        "assignments": assignments,
    }


# ─── locations ───────────────────────────────────────────────────────


@router.get("/locations")
def list_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Location)
        .filter(Location.tenant_id == current_user.tenant_id)
        .order_by(Location.sort_order, Location.name)
        .all()
    )
    return [_loc_dict(loc) for loc in rows]


@router.post("/locations", status_code=status.HTTP_201_CREATED)
def create_location(
    data: LocationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    exists = (
        db.query(Location)
        .filter(Location.tenant_id == current_user.tenant_id, Location.name == name)
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Ein Standort mit diesem Namen existiert bereits")
    loc = Location(tenant_id=current_user.tenant_id, name=name, sort_order=data.sort_order)
    db.add(loc)
    _commit_or_conflict(db, "Ein Standort mit diesem Namen existiert bereits")
    db.refresh(loc)
    return _loc_dict(loc)


@router.put("/locations/{location_id}")
def update_location(
    location_id: UUID,
    data: LocationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    loc = (
        db.query(Location)
        .filter(Location.id == location_id, Location.tenant_id == current_user.tenant_id)
        .first()
    )
    if not loc:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    clash = (
        db.query(Location)
        .filter(
            Location.tenant_id == current_user.tenant_id,
            Location.name == name,
            Location.id != location_id,
        )
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="Ein Standort mit diesem Namen existiert bereits")
    loc.name = name
    loc.sort_order = data.sort_order
    _commit_or_conflict(db, "Ein Standort mit diesem Namen existiert bereits")
    db.refresh(loc)
    return _loc_dict(loc)


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    loc = (
        db.query(Location)
        .filter(Location.id == location_id, Location.tenant_id == current_user.tenant_id)
        .first()
    )
    if not loc:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")
    in_use = (
        db.query(Workstation)
        .filter(
            Workstation.tenant_id == current_user.tenant_id,
            Workstation.location_id == location_id,
        )
        .first()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="Standort wird von Arbeitsplätzen genutzt und kann nicht gelöscht werden",
        )
    db.delete(loc)
    db.commit()
    return None


# ─── workstations ────────────────────────────────────────────────────


def _location_name_map(db: Session, tenant_id) -> dict:
    return {
        loc.id: loc.name
        for loc in db.query(Location).filter(Location.tenant_id == tenant_id).all()
    }


@router.get("/workstations")
def list_workstations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    loc_names = _location_name_map(db, current_user.tenant_id)
    rows = (
        db.query(Workstation)
        .filter(Workstation.tenant_id == current_user.tenant_id)
        .order_by(Workstation.sort_order, Workstation.name)
        .all()
    )
    return [_ws_dict(ws, loc_names.get(ws.location_id)) for ws in rows]


def _validate_location(db: Session, tenant_id, location_id: Optional[UUID]):
    if location_id is None:
        return
    loc = (
        db.query(Location)
        .filter(Location.id == location_id, Location.tenant_id == tenant_id)
        .first()
    )
    if not loc:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")


@router.post("/workstations", status_code=status.HTTP_201_CREATED)
def create_workstation(
    data: WorkstationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    _validate_location(db, current_user.tenant_id, data.location_id)
    exists = (
        db.query(Workstation)
        .filter(Workstation.tenant_id == current_user.tenant_id, Workstation.name == name)
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Ein Arbeitsplatz mit diesem Namen existiert bereits")
    ws = Workstation(
        tenant_id=current_user.tenant_id,
        name=name,
        location_id=data.location_id,
        color=data.color,
        sort_order=data.sort_order,
    )
    db.add(ws)
    _commit_or_conflict(db, "Ein Arbeitsplatz mit diesem Namen existiert bereits")
    db.refresh(ws)
    loc_names = _location_name_map(db, current_user.tenant_id)
    return _ws_dict(ws, loc_names.get(ws.location_id))


@router.put("/workstations/{workstation_id}")
def update_workstation(
    workstation_id: UUID,
    data: WorkstationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ws = (
        db.query(Workstation)
        .filter(Workstation.id == workstation_id, Workstation.tenant_id == current_user.tenant_id)
        .first()
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Arbeitsplatz nicht gefunden")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    _validate_location(db, current_user.tenant_id, data.location_id)
    clash = (
        db.query(Workstation)
        .filter(
            Workstation.tenant_id == current_user.tenant_id,
            Workstation.name == name,
            Workstation.id != workstation_id,
        )
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="Ein Arbeitsplatz mit diesem Namen existiert bereits")
    ws.name = name
    ws.location_id = data.location_id
    ws.color = data.color
    ws.sort_order = data.sort_order
    _commit_or_conflict(db, "Ein Arbeitsplatz mit diesem Namen existiert bereits")
    db.refresh(ws)
    loc_names = _location_name_map(db, current_user.tenant_id)
    return _ws_dict(ws, loc_names.get(ws.location_id))


@router.delete("/workstations/{workstation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workstation(
    workstation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ws = (
        db.query(Workstation)
        .filter(Workstation.id == workstation_id, Workstation.tenant_id == current_user.tenant_id)
        .first()
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Arbeitsplatz nicht gefunden")
    in_use = (
        db.query(ShiftSlot)
        .filter(
            ShiftSlot.tenant_id == current_user.tenant_id,
            ShiftSlot.workstation_id == workstation_id,
        )
        .first()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="Arbeitsplatz wird in Schichtplänen genutzt und kann nicht gelöscht werden",
        )
    db.delete(ws)
    db.commit()
    return None


# ─── plans ───────────────────────────────────────────────────────────


def _assignment_counts(db: Session, tenant_id, slot_ids: List[UUID]) -> dict:
    if not slot_ids:
        return {}
    rows = (
        db.query(ShiftAssignment.shift_slot_id, func.count(ShiftAssignment.id))
        .filter(
            ShiftAssignment.tenant_id == tenant_id,
            ShiftAssignment.shift_slot_id.in_(slot_ids),
        )
        .group_by(ShiftAssignment.shift_slot_id)
        .all()
    )
    return {sid: cnt for sid, cnt in rows}


@router.get("/plans")
def list_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tid = current_user.tenant_id
    plans = (
        db.query(ShiftPlan)
        .filter(ShiftPlan.tenant_id == tid)
        .order_by(ShiftPlan.name)
        .all()
    )
    slots = (
        db.query(ShiftSlot)
        .filter(ShiftSlot.tenant_id == tid)
        .all()
    )
    counts = _assignment_counts(db, tid, [s.id for s in slots])
    slots_by_plan: dict = {}
    for s in slots:
        slots_by_plan.setdefault(s.shift_plan_id, []).append(s)

    today = today_local()
    # Fix #7: non-admins only see plans that are active today — inactive drafts
    # are an admin planning artefact and must be filtered server-side (the
    # frontend filtered, the backend did not).
    is_admin = current_user.role == UserRole.ADMIN
    result = []
    for p in plans:
        active_today = shift_planning_service.is_plan_active_on(p, today)
        if not is_admin and not active_today:
            continue
        p_slots = slots_by_plan.get(p.id, [])
        understaffed = [
            s for s in p_slots
            if shift_planning_service.is_understaffed(s.min_staff, counts.get(s.id, 0))
        ]
        result.append({
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "is_active": p.is_active,
            "active_from_date": _iso(p.active_from_date),
            "active_until_date": _iso(p.active_until_date),
            "active_today": active_today,
            "slot_count": len(p_slots),
            "is_valid": len(understaffed) == 0,
        })
    return result


def _plan_or_404(db: Session, tenant_id, plan_id: UUID) -> ShiftPlan:
    plan = (
        db.query(ShiftPlan)
        .filter(ShiftPlan.id == plan_id, ShiftPlan.tenant_id == tenant_id)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Schichtplan nicht gefunden")
    return plan


def _build_plan_detail(db: Session, tid, plan: ShiftPlan, is_admin: bool) -> dict:
    """Full plan detail (slots + assignments + validation). The per-person
    `qualified` / slot `unqualified` flags are included only for admins (#305 M2d)."""
    slots = (
        db.query(ShiftSlot)
        .filter(ShiftSlot.tenant_id == tid, ShiftSlot.shift_plan_id == plan.id)
        .order_by(ShiftSlot.weekday, ShiftSlot.start_time)
        .all()
    )
    ws_map = {
        w.id: w for w in db.query(Workstation).filter(Workstation.tenant_id == tid).all()
    }
    slot_ids = [s.id for s in slots]
    # assignments with user names, grouped per slot
    assign_rows = (
        db.query(ShiftAssignment, User)
        .join(User, ShiftAssignment.user_id == User.id)
        .filter(
            ShiftAssignment.tenant_id == tid,
            ShiftAssignment.shift_slot_id.in_(slot_ids) if slot_ids else False,
        )
        .all()
    )
    assigns_by_slot: dict = {}
    for a, u in assign_rows:
        assigns_by_slot.setdefault(a.shift_slot_id, []).append({
            "id": str(a.id),
            "user_id": str(a.user_id),
            "user_name": f"{u.first_name} {u.last_name}".strip(),
        })

    # #305 M2d: the per-person "trained / not trained" signal is HR-sensitive
    # competency data → ADMIN-ONLY. Non-admins (read-only view) get the
    # who-works-where + understaffing picture but NOT colleagues' qualification
    # gaps (consistent with the DSGVO masking of individual-sensitive data).
    qual_pairs = set()
    if is_admin:
        ws_in_plan = {s.workstation_id for s in slots}
        if ws_in_plan:
            for uid, wsid in (
                db.query(WorkstationQualification.user_id, WorkstationQualification.workstation_id)
                .filter(
                    WorkstationQualification.tenant_id == tid,
                    WorkstationQualification.workstation_id.in_(ws_in_plan),
                )
                .all()
            ):
                qual_pairs.add((str(uid), str(wsid)))

    slot_dicts = []
    understaffed_ids = []
    unqualified_ids = []
    for s in slots:
        a_list = assigns_by_slot.get(s.id, [])
        if is_admin:
            ws_key = str(s.workstation_id)
            for a in a_list:
                a["qualified"] = (a["user_id"], ws_key) in qual_pairs
        d = _slot_dict(s, ws_map.get(s.workstation_id), a_list)
        if d["understaffed"]:
            understaffed_ids.append(d["id"])
        if is_admin and d["unqualified"]:
            unqualified_ids.append(d["id"])
        slot_dicts.append(d)

    return {
        "id": str(plan.id),
        "name": plan.name,
        "description": plan.description,
        "is_active": plan.is_active,
        "active_from_date": _iso(plan.active_from_date),
        "active_until_date": _iso(plan.active_until_date),
        "active_today": shift_planning_service.is_plan_active_on(plan, today_local()),
        "slots": slot_dicts,
        "validation": {
            "is_valid": len(understaffed_ids) == 0,
            "understaffed_slot_ids": understaffed_ids,
            "unqualified_slot_ids": unqualified_ids,
        },
    }


@router.get("/plans/{plan_id}")
def get_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tid = current_user.tenant_id
    plan = _plan_or_404(db, tid, plan_id)
    is_admin = current_user.role == UserRole.ADMIN
    # Fix #7: non-admins can only open plans that are active today — an inactive
    # draft does not "exist" for them (404, consistent with list_plans filtering).
    if not is_admin and not shift_planning_service.is_plan_active_on(plan, today_local()):
        raise HTTPException(status_code=404, detail="Schichtplan nicht gefunden")
    return _build_plan_detail(db, tid, plan, is_admin)


@router.post("/plans/{plan_id}/generate")
def generate_plan(
    plan_id: UUID,
    data: GenerateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """#305 M2: greedy auto-fill the plan's slots for a target week (Monday).

    Reads absences/hours/overtime read-only; writes only assignments; does NOT
    activate the plan. Returns the refreshed plan detail + a generation summary.
    """
    tid = current_user.tenant_id
    plan = _plan_or_404(db, tid, plan_id)
    # normalise to the Monday of the chosen week
    monday = data.target_monday - timedelta(days=data.target_monday.weekday())
    gen = shift_planning_generator.generate_plan(db, tid, plan, monday, data.mode)
    detail = _build_plan_detail(db, tid, plan, True)  # admin path
    return {"plan": detail, "generation": gen}


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _plan_summary(plan: ShiftPlan) -> dict:
    return {
        "id": str(plan.id),
        "name": plan.name,
        "description": plan.description,
        "is_active": plan.is_active,
        "active_from_date": _iso(plan.active_from_date),
        "active_until_date": _iso(plan.active_until_date),
    }


def _validate_window(data: PlanIn) -> None:
    if data.active_from_date and data.active_until_date and data.active_from_date > data.active_until_date:
        raise HTTPException(status_code=400, detail="'aktiv von' darf nicht nach 'aktiv bis' liegen")


@router.post("/plans", status_code=status.HTTP_201_CREATED)
def create_plan(
    data: PlanIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    exists = (
        db.query(ShiftPlan)
        .filter(ShiftPlan.tenant_id == current_user.tenant_id, ShiftPlan.name == name)
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Ein Schichtplan mit diesem Namen existiert bereits")
    _validate_window(data)
    plan = ShiftPlan(
        tenant_id=current_user.tenant_id,
        name=name,
        description=data.description,
        is_active=False,
        active_from_date=data.active_from_date,
        active_until_date=data.active_until_date,
        created_by=current_user.id,
    )
    db.add(plan)
    _commit_or_conflict(db, "Ein Schichtplan mit diesem Namen existiert bereits")
    db.refresh(plan)
    return _plan_summary(plan)


@router.post("/plans/{plan_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_plan(
    plan_id: UUID,
    data: PlanDuplicateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """#338: Schichtplan inkl. Slots + Zuweisungen duplizieren. Die Kopie ist ein
    INAKTIVER Entwurf OHNE Aktiv-Datumsfenster (sie soll nicht versehentlich neben
    dem Original aktiv werden); Arbeitsplätze/Einweisungen sind nicht plan-gebunden
    und werden daher nicht kopiert. Alles tenant-scoped (F-026)."""
    tid = current_user.tenant_id
    src = _plan_or_404(db, tid, plan_id)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    clash = (
        db.query(ShiftPlan)
        .filter(ShiftPlan.tenant_id == tid, ShiftPlan.name == name)
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="Ein Schichtplan mit diesem Namen existiert bereits")

    new_plan = ShiftPlan(
        tenant_id=tid,
        name=name,
        description=src.description,
        is_active=False,
        active_from_date=None,
        active_until_date=None,
        created_by=current_user.id,
    )
    db.add(new_plan)
    db.flush()  # new_plan.id

    src_slots = (
        db.query(ShiftSlot)
        .filter(ShiftSlot.tenant_id == tid, ShiftSlot.shift_plan_id == src.id)
        .all()
    )
    for s in src_slots:
        ns = ShiftSlot(
            tenant_id=tid,
            shift_plan_id=new_plan.id,
            workstation_id=s.workstation_id,
            weekday=s.weekday,
            start_time=s.start_time,
            end_time=s.end_time,
            min_staff=s.min_staff,
        )
        db.add(ns)
        db.flush()  # ns.id
        src_assigns = (
            db.query(ShiftAssignment)
            .filter(ShiftAssignment.tenant_id == tid, ShiftAssignment.shift_slot_id == s.id)
            .all()
        )
        for a in src_assigns:
            db.add(ShiftAssignment(tenant_id=tid, shift_slot_id=ns.id, user_id=a.user_id))

    _commit_or_conflict(db, "Ein Schichtplan mit diesem Namen existiert bereits")
    db.refresh(new_plan)
    return _plan_summary(new_plan)


@router.put("/plans/{plan_id}")
def update_plan(
    plan_id: UUID,
    data: PlanIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    plan = _plan_or_404(db, current_user.tenant_id, plan_id)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    clash = (
        db.query(ShiftPlan)
        .filter(
            ShiftPlan.tenant_id == current_user.tenant_id,
            ShiftPlan.name == name,
            ShiftPlan.id != plan_id,
        )
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="Ein Schichtplan mit diesem Namen existiert bereits")
    _validate_window(data)
    plan.name = name
    plan.description = data.description
    plan.active_from_date = data.active_from_date
    plan.active_until_date = data.active_until_date
    _commit_or_conflict(db, "Ein Schichtplan mit diesem Namen existiert bereits")
    db.refresh(plan)
    return _plan_summary(plan)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    plan = _plan_or_404(db, current_user.tenant_id, plan_id)
    db.delete(plan)  # cascades to slots + assignments (ORM + DB)
    db.commit()
    return None


@router.post("/plans/{plan_id}/activate")
def activate_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    plan = _plan_or_404(db, current_user.tenant_id, plan_id)
    plan.is_active = True
    db.commit()
    db.refresh(plan)
    return _plan_summary(plan)


@router.post("/plans/{plan_id}/deactivate")
def deactivate_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    plan = _plan_or_404(db, current_user.tenant_id, plan_id)
    plan.is_active = False
    db.commit()
    db.refresh(plan)
    return _plan_summary(plan)


# ─── slots ───────────────────────────────────────────────────────────


def _slot_or_404(db: Session, tenant_id, slot_id: UUID) -> ShiftSlot:
    slot = (
        db.query(ShiftSlot)
        .filter(ShiftSlot.id == slot_id, ShiftSlot.tenant_id == tenant_id)
        .first()
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Schicht-Slot nicht gefunden")
    return slot


def _validate_workstation(db: Session, tenant_id, workstation_id: UUID) -> Workstation:
    ws = (
        db.query(Workstation)
        .filter(Workstation.id == workstation_id, Workstation.tenant_id == tenant_id)
        .first()
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Arbeitsplatz nicht gefunden")
    return ws


def _validate_weekday_enabled(db: Session, tenant_id, weekday: int) -> None:
    """#371: reject slots on a weekday the tenant has switched off in the planner."""
    if not shift_planning_service.is_weekday_enabled(db, tenant_id, weekday):
        raise HTTPException(
            status_code=400,
            detail="Dieser Wochentag ist im Schichtplaner deaktiviert.",
        )


def _single_slot_dict(db: Session, tenant_id, slot: ShiftSlot) -> dict:
    ws = db.query(Workstation).filter(
        Workstation.id == slot.workstation_id, Workstation.tenant_id == tenant_id
    ).first()
    rows = (
        db.query(ShiftAssignment, User)
        .join(User, ShiftAssignment.user_id == User.id)
        .filter(ShiftAssignment.tenant_id == tenant_id, ShiftAssignment.shift_slot_id == slot.id)
        .all()
    )
    qualified = shift_planning_service.qualified_user_ids(db, tenant_id, slot.workstation_id)
    a_list = [
        {
            "id": str(a.id),
            "user_id": str(a.user_id),
            "user_name": f"{u.first_name} {u.last_name}".strip(),
            "qualified": str(a.user_id) in qualified,
        }
        for a, u in rows
    ]
    return _slot_dict(slot, ws, a_list)


@router.post("/plans/{plan_id}/slots", status_code=status.HTTP_201_CREATED)
def create_slot(
    plan_id: UUID,
    data: SlotIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tid = current_user.tenant_id
    _plan_or_404(db, tid, plan_id)
    if data.end_time <= data.start_time:
        raise HTTPException(status_code=400, detail="Ende muss nach dem Beginn liegen")
    _validate_weekday_enabled(db, tid, data.weekday)
    _validate_workstation(db, tid, data.workstation_id)
    slot = ShiftSlot(
        tenant_id=tid,
        shift_plan_id=plan_id,
        workstation_id=data.workstation_id,
        weekday=data.weekday,
        start_time=data.start_time,
        end_time=data.end_time,
        min_staff=data.min_staff,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return _single_slot_dict(db, tid, slot)


@router.put("/slots/{slot_id}")
def update_slot(
    slot_id: UUID,
    data: SlotIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tid = current_user.tenant_id
    slot = _slot_or_404(db, tid, slot_id)
    if data.end_time <= data.start_time:
        raise HTTPException(status_code=400, detail="Ende muss nach dem Beginn liegen")
    _validate_weekday_enabled(db, tid, data.weekday)
    _validate_workstation(db, tid, data.workstation_id)
    slot.workstation_id = data.workstation_id
    slot.weekday = data.weekday
    slot.start_time = data.start_time
    slot.end_time = data.end_time
    slot.min_staff = data.min_staff
    db.commit()
    db.refresh(slot)
    return _single_slot_dict(db, tid, slot)


@router.delete("/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slot(
    slot_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    slot = _slot_or_404(db, current_user.tenant_id, slot_id)
    db.delete(slot)  # cascades assignments
    db.commit()
    return None


# ─── assignments ─────────────────────────────────────────────────────


@router.put("/slots/{slot_id}/assignments")
def set_assignments(
    slot_id: UUID,
    data: AssignmentsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tid = current_user.tenant_id
    slot = _slot_or_404(db, tid, slot_id)

    unique_ids = list(dict.fromkeys(data.user_ids))  # dedup, preserve order
    if unique_ids:
        found = (
            db.query(User)
            .filter(User.id.in_(unique_ids), User.tenant_id == tid)
            .all()
        )
        found_map = {u.id: u for u in found}
        if len(found_map) != len(unique_ids):
            raise HTTPException(status_code=404, detail="Mindestens ein Mitarbeiter wurde nicht gefunden")
    else:
        found_map = {}

    # replace the slot's assignments (idempotent set semantics)
    db.query(ShiftAssignment).filter(
        ShiftAssignment.tenant_id == tid,
        ShiftAssignment.shift_slot_id == slot.id,
    ).delete(synchronize_session=False)

    assignments = []
    for uid in unique_ids:
        a = ShiftAssignment(tenant_id=tid, shift_slot_id=slot.id, user_id=uid)
        db.add(a)
        db.flush()
        u = found_map[uid]
        assignments.append({
            "id": str(a.id),
            "user_id": str(uid),
            "user_name": f"{u.first_name} {u.last_name}".strip(),
        })
    # concurrent double-submit can race the delete+insert into the
    # uq_tenant_slot_user constraint → 409 instead of a 500 (review finding).
    _commit_or_conflict(db, "Die Zuweisungen wurden zwischenzeitlich geändert, bitte erneut versuchen")
    return {"slot_id": str(slot.id), "assignments": assignments}


# ─── qualifications / Einweisungen (#305 M2d) ────────────────────────


@router.get("/qualifications")
def get_qualifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Matrix: active employees × workstations + the set qualifications."""
    tid = current_user.tenant_id
    loc_names = _location_name_map(db, tid)
    workstations = (
        db.query(Workstation)
        .filter(Workstation.tenant_id == tid)
        .order_by(Workstation.sort_order, Workstation.name)
        .all()
    )
    users = (
        db.query(User)
        .filter(User.tenant_id == tid, User.is_active.is_(True), User.is_hidden.is_(False))
        .order_by(User.last_name, User.first_name)
        .all()
    )
    quals = (
        db.query(WorkstationQualification)
        .filter(WorkstationQualification.tenant_id == tid)
        .all()
    )
    return {
        "workstations": [_ws_dict(w, loc_names.get(w.location_id)) for w in workstations],
        "users": [
            {"id": str(u.id), "first_name": u.first_name, "last_name": u.last_name} for u in users
        ],
        "qualifications": [
            {"user_id": str(q.user_id), "workstation_id": str(q.workstation_id)} for q in quals
        ],
    }


@router.put("/qualifications/{user_id}")
def set_user_qualifications(
    user_id: UUID,
    data: QualificationsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Replace a user's workstation qualifications (idempotent set, dedup)."""
    tid = current_user.tenant_id
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    unique_ws = list(dict.fromkeys(data.workstation_ids))
    if unique_ws:
        found = (
            db.query(Workstation.id)
            .filter(Workstation.id.in_(unique_ws), Workstation.tenant_id == tid)
            .all()
        )
        if len({r[0] for r in found}) != len(unique_ws):
            raise HTTPException(status_code=404, detail="Mindestens ein Arbeitsplatz wurde nicht gefunden")

    db.query(WorkstationQualification).filter(
        WorkstationQualification.tenant_id == tid,
        WorkstationQualification.user_id == user_id,
    ).delete(synchronize_session=False)
    for wsid in unique_ws:
        db.add(WorkstationQualification(tenant_id=tid, user_id=user_id, workstation_id=wsid))
    db.commit()
    return {"user_id": str(user_id), "workstation_ids": [str(w) for w in unique_ws]}


@router.get("/me/qualifications")
def my_qualifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The logged-in employee's own workstation qualifications."""
    tid = current_user.tenant_id
    loc_names = _location_name_map(db, tid)
    rows = (
        db.query(Workstation)
        .join(WorkstationQualification, WorkstationQualification.workstation_id == Workstation.id)
        .filter(
            WorkstationQualification.tenant_id == tid,
            WorkstationQualification.user_id == current_user.id,
            Workstation.tenant_id == tid,
        )
        .order_by(Workstation.sort_order, Workstation.name)
        .all()
    )
    return {"workstations": [_ws_dict(w, loc_names.get(w.location_id)) for w in rows]}


# ─── dashboard ───────────────────────────────────────────────────────


@router.get("/my-today")
def my_today(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return shift_planning_service.get_my_today(db, current_user)
