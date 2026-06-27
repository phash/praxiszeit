"""#312 Custom absence reasons — admin CRUD + employee read.

Tenant-scoped (RLS + explicit F-026 filters). The admin manages reasons in
Settings; every authenticated user can read the active list for the booking
picker. The reason's ``base_behavior`` is mapped to a built-in AbsenceType at
booking time (see absences.create_absence) so the calculation stays unchanged.
"""
import re
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, AbsenceReason, Absence
from app.schemas.absence_reason import AbsenceReasonCreate, AbsenceReasonUpdate, AbsenceReasonResponse

admin_router = APIRouter(
    prefix="/api/admin/absence-reasons", tags=["absence-reasons"],
    dependencies=[Depends(require_admin)],
)
read_router = APIRouter(prefix="/api/absence-reasons", tags=["absence-reasons"])

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_color(color) -> None:
    if color is not None and not _HEX.match(color):
        raise HTTPException(status_code=400, detail="Farbe muss im Format #RRGGBB sein")


def _reason_or_404(db: Session, tenant_id, reason_id: UUID) -> AbsenceReason:
    # F-026: explicit tenant scope on top of RLS.
    r = (
        db.query(AbsenceReason)
        .filter(AbsenceReason.id == reason_id, AbsenceReason.tenant_id == tenant_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Abwesenheitsgrund nicht gefunden")
    return r


@admin_router.get("", response_model=List[AbsenceReasonResponse])
def list_reasons(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    q = db.query(AbsenceReason).filter(AbsenceReason.tenant_id == current_user.tenant_id)
    if not include_inactive:
        q = q.filter(AbsenceReason.is_active.is_(True))
    return q.order_by(AbsenceReason.sort_order, AbsenceReason.name).all()


@admin_router.post("", response_model=AbsenceReasonResponse, status_code=201)
def create_reason(
    data: AbsenceReasonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    _validate_color(data.color)
    exists = (
        db.query(AbsenceReason)
        .filter(AbsenceReason.tenant_id == current_user.tenant_id, AbsenceReason.name == name)
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Ein Abwesenheitsgrund mit diesem Namen existiert bereits")
    r = AbsenceReason(
        tenant_id=current_user.tenant_id, name=name, color=data.color,
        base_behavior=data.base_behavior.value, sort_order=data.sort_order, is_active=True,
    )
    db.add(r)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ein Abwesenheitsgrund mit diesem Namen existiert bereits")
    db.refresh(r)
    return r


@admin_router.put("/{reason_id}", response_model=AbsenceReasonResponse)
def update_reason(
    reason_id: UUID,
    data: AbsenceReasonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    r = _reason_or_404(db, current_user.tenant_id, reason_id)
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
        clash = (
            db.query(AbsenceReason)
            .filter(
                AbsenceReason.tenant_id == current_user.tenant_id,
                AbsenceReason.name == name,
                AbsenceReason.id != reason_id,
            )
            .first()
        )
        if clash:
            raise HTTPException(status_code=409, detail="Ein Abwesenheitsgrund mit diesem Namen existiert bereits")
        r.name = name
    if data.color is not None:
        if data.color == "":
            r.color = None  # explicit clear
        else:
            _validate_color(data.color)
            r.color = data.color
    if data.is_active is not None:
        r.is_active = data.is_active
    if data.sort_order is not None:
        r.sort_order = data.sort_order
    db.commit()
    db.refresh(r)
    return r


@admin_router.delete("/{reason_id}", status_code=204)
def delete_reason(
    reason_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    r = _reason_or_404(db, current_user.tenant_id, reason_id)
    # Only delete if unused — otherwise the admin should deactivate instead
    # (an in-use reason backs real absences). F-026: tenant-scoped check.
    used = (
        db.query(Absence.id)
        .filter(Absence.reason_id == reason_id, Absence.tenant_id == current_user.tenant_id)
        .first()
    )
    if used:
        raise HTTPException(
            status_code=409,
            detail="Grund wird noch von Abwesenheiten genutzt — bitte stattdessen deaktivieren",
        )
    db.delete(r)
    db.commit()


@read_router.get("", response_model=List[AbsenceReasonResponse])
def my_reasons(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Active reasons for the booking picker (any authenticated user)."""
    return (
        db.query(AbsenceReason)
        .filter(AbsenceReason.tenant_id == current_user.tenant_id, AbsenceReason.is_active.is_(True))
        .order_by(AbsenceReason.sort_order, AbsenceReason.name)
        .all()
    )
