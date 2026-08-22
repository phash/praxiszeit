"""#443: Freigabe eines Schichtplans für Mitarbeitende (visible_to_employees)
und der Hinweistext je Slot (shift_slots.note).

Die Regel selbst lebt in ``shift_planning_service.is_plan_visible_to`` und wird
von ``list_plans`` und ``get_plan`` gemeinsam genutzt — vor #443 hatte jede der
beiden Stellen ihre eigene Inline-Kopie.
"""
from datetime import time

from app.models import User, UserRole
from app.models.shift_planning import ShiftPlan, ShiftSlot, Workstation
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
