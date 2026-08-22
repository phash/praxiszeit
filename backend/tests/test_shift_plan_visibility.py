"""#443: Freigabe eines Schichtplans für Mitarbeitende (visible_to_employees)
und der Hinweistext je Slot (shift_slots.note).

Die Regel selbst lebt in ``shift_planning_service.is_plan_visible_to`` und wird
von ``list_plans`` und ``get_plan`` gemeinsam genutzt — vor #443 hatte jede der
beiden Stellen ihre eigene Inline-Kopie.
"""
from datetime import time

import pytest
from fastapi import HTTPException

from app.models import User, UserRole
from app.models.shift_planning import ShiftPlan, ShiftSlot, Workstation
from app.routers.shift_planning import get_plan, list_plans
from app.services import shift_planning_service
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID


def _user(db, username, role=UserRole.EMPLOYEE):
    u = User(
        username=username, email=f"{username}@t.de", password_hash="h",
        first_name="F", last_name="L", role=role, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _plan(db, creator, name, *, active=False, visible=False):
    p = ShiftPlan(
        tenant_id=DEFAULT_TENANT_ID, name=name, is_active=active,
        visible_to_employees=visible, created_by=creator.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _workstation(db, name):
    w = Workstation(tenant_id=DEFAULT_TENANT_ID, name=name)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def test_plan_defaults_to_not_visible(db, default_tenant):
    """Bestandsverhalten: ohne ausdrückliche Freigabe bleibt ein Plan intern."""
    admin = _user(db, "vis_admin_default", role=UserRole.ADMIN)
    p = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name="Ohne Angabe", created_by=admin.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.visible_to_employees is False


def test_slot_note_is_optional_and_stored(db, default_tenant):
    admin = _user(db, "vis_admin_note", role=UserRole.ADMIN)
    plan = _plan(db, admin, "Plan mit Hinweis")
    ws = _workstation(db, "Tresen")

    without = ShiftSlot(
        tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan.id, workstation_id=ws.id,
        weekday=0, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
    )
    db.add(without)
    db.commit()
    db.refresh(without)
    assert without.note is None

    with_note = ShiftSlot(
        tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan.id, workstation_id=ws.id,
        weekday=1, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
        note="Einarbeitung Azubi",
    )
    db.add(with_note)
    db.commit()
    db.refresh(with_note)
    assert with_note.note == "Einarbeitung Azubi"


def test_helper_admin_sees_everything(db, default_tenant):
    admin = _user(db, "vis_helper_admin", role=UserRole.ADMIN)
    draft = _plan(db, admin, "Reiner Entwurf")
    assert shift_planning_service.is_plan_visible_to(draft, today_local(), True) is True


def test_helper_released_plan_is_visible_without_being_active(db, default_tenant):
    admin = _user(db, "vis_helper_rel", role=UserRole.ADMIN)
    released = _plan(db, admin, "Ab September", visible=True)
    assert shift_planning_service.is_plan_active_on(released, today_local()) is False
    assert shift_planning_service.is_plan_visible_to(released, today_local(), False) is True


def test_helper_draft_stays_hidden(db, default_tenant):
    admin = _user(db, "vis_helper_draft", role=UserRole.ADMIN)
    draft = _plan(db, admin, "Nicht freigegeben")
    assert shift_planning_service.is_plan_visible_to(draft, today_local(), False) is False


def test_list_plans_shows_released_future_plan_to_employee(db, default_tenant):
    admin = _user(db, "vis_list_admin", role=UserRole.ADMIN)
    emp = _user(db, "vis_list_emp")
    _plan(db, admin, "Freigegeben", visible=True)
    _plan(db, admin, "Entwurf bleibt weg")

    names = {p["name"] for p in list_plans(db=db, current_user=emp)}
    assert "Freigegeben" in names
    assert "Entwurf bleibt weg" not in names


def test_get_plan_opens_released_plan_for_employee(db, default_tenant):
    admin = _user(db, "vis_get_admin", role=UserRole.ADMIN)
    emp = _user(db, "vis_get_emp")
    released = _plan(db, admin, "Freigegeben zum Oeffnen", visible=True)
    draft = _plan(db, admin, "Entwurf zum Oeffnen")

    assert get_plan(released.id, db=db, current_user=emp)["name"] == "Freigegeben zum Oeffnen"

    with pytest.raises(HTTPException) as exc:
        get_plan(draft.id, db=db, current_user=emp)
    assert exc.value.status_code == 404


from uuid import UUID as _UUID

from app.routers.shift_planning import (
    PlanDuplicateIn,
    PlanIn,
    create_plan,
    duplicate_plan,
    update_plan,
)

# Die Endpunkte werden hier als gewoehnliche Funktionen gerufen, nicht ueber
# HTTP — FastAPI wandelt den Pfadparameter also NICHT um. Die Antwort-Dicts
# tragen die Kennung als str, die Signaturen erwarten UUID.


def test_create_and_update_carry_the_release_flag(db, default_tenant):
    admin = _user(db, "vis_api_admin", role=UserRole.ADMIN)

    created = create_plan(PlanIn(name="Herbstplan", visible_to_employees=True), db=db, current_user=admin)
    assert created["visible_to_employees"] is True

    updated = update_plan(
        _UUID(created["id"]),
        PlanIn(name="Herbstplan", visible_to_employees=False),
        db=db,
        current_user=admin,
    )
    assert updated["visible_to_employees"] is False


def test_plan_detail_exposes_the_release_flag(db, default_tenant):
    admin = _user(db, "vis_detail_admin", role=UserRole.ADMIN)
    plan = _plan(db, admin, "Detailplan", visible=True)
    detail = get_plan(plan.id, db=db, current_user=admin)
    assert detail["visible_to_employees"] is True


def test_list_plans_exposes_the_release_flag(db, default_tenant):
    admin = _user(db, "vis_listflag_admin", role=UserRole.ADMIN)
    _plan(db, admin, "Listenplan", visible=True)
    row = next(p for p in list_plans(db=db, current_user=admin) if p["name"] == "Listenplan")
    assert row["visible_to_employees"] is True


def test_duplicate_does_not_inherit_the_release(db, default_tenant):
    """Eine Kopie ist ein Entwurf — sie darf nicht mit der Freigabe des
    Originals ins Leben treten (wie schon is_active und das Datumsfenster)."""
    admin = _user(db, "vis_dup_admin", role=UserRole.ADMIN)
    src = _plan(db, admin, "Original freigegeben", visible=True)

    copy = duplicate_plan(src.id, PlanDuplicateIn(name="Original freigegeben (Kopie)"), db=db, current_user=admin)
    assert copy["visible_to_employees"] is False
