"""#443: Hinweistext je Einteilung (shift_slots.note).

Reines Anzeigefeld — es fließt in keine Prüfung und in keine Berechnung ein.
Leereingaben werden am Rand zu NULL normalisiert, damit die Anzeige nicht
zwischen "kein Hinweis" und "Hinweis aus Leerzeichen" unterscheiden muss.
"""
from datetime import time
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models import User, UserRole
from app.models.shift_planning import ShiftAssignment, ShiftPlan, Workstation
from app.models.system_setting import SystemSetting
from app.routers.shift_planning import (
    PlanDuplicateIn,
    SlotIn,
    create_slot,
    duplicate_plan,
    get_plan,
    update_slot,
)
from app.services import lifecycle_service
from tests.conftest import DEFAULT_TENANT_ID


def _admin(db, username):
    u = User(
        username=username, email=f"{username}@t.de", password_hash="h",
        first_name="A", last_name="D", role=UserRole.ADMIN, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _employee(db, username):
    u = User(
        username=username, email=f"{username}@t.de", password_hash="h",
        first_name="M", last_name="A", role=UserRole.EMPLOYEE, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _plan(db, admin, name):
    p = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name=name, created_by=admin.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _ws(db, name):
    w = Workstation(tenant_id=DEFAULT_TENANT_ID, name=name)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def _slot_in(ws_id, **over):
    base = dict(
        workstation_id=ws_id, weekday=0,
        start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
    )
    base.update(over)
    return SlotIn(**base)


def test_create_slot_stores_and_returns_the_note(db, default_tenant):
    admin = _admin(db, "note_create_admin")
    plan = _plan(db, admin, "Notizplan")
    ws = _ws(db, "Tresen Notiz")

    out = create_slot(plan.id, _slot_in(ws.id, note="Einarbeitung Azubi"), db=db, current_user=admin)
    assert out["note"] == "Einarbeitung Azubi"


def test_slot_without_note_returns_none(db, default_tenant):
    admin = _admin(db, "note_none_admin")
    plan = _plan(db, admin, "Notizplan ohne")
    ws = _ws(db, "Tresen ohne")

    out = create_slot(plan.id, _slot_in(ws.id), db=db, current_user=admin)
    assert out["note"] is None


def test_blank_note_is_normalised_to_none(db, default_tenant):
    admin = _admin(db, "note_blank_admin")
    plan = _plan(db, admin, "Notizplan blank")
    ws = _ws(db, "Tresen blank")

    out = create_slot(plan.id, _slot_in(ws.id, note="   "), db=db, current_user=admin)
    assert out["note"] is None


def test_update_slot_changes_and_clears_the_note(db, default_tenant):
    admin = _admin(db, "note_update_admin")
    plan = _plan(db, admin, "Notizplan update")
    ws = _ws(db, "Tresen update")

    created = create_slot(plan.id, _slot_in(ws.id, note="alt"), db=db, current_user=admin)
    # Direktaufruf statt HTTP: FastAPI wandelt den Pfadparameter nicht um.
    slot_id = UUID(created["id"])
    changed = update_slot(slot_id, _slot_in(ws.id, note="neu"), db=db, current_user=admin)
    assert changed["note"] == "neu"

    cleared = update_slot(slot_id, _slot_in(ws.id), db=db, current_user=admin)
    assert cleared["note"] is None


def test_note_longer_than_500_chars_is_rejected(db, default_tenant):
    ws_id = "00000000-0000-0000-0000-000000000009"
    with pytest.raises(ValidationError):
        _slot_in(ws_id, note="x" * 501)


def test_duplicate_plan_copies_slot_notes(db, default_tenant):
    admin = _admin(db, "note_dup_admin")
    plan = _plan(db, admin, "Notizplan Original")
    ws = _ws(db, "Tresen dup")
    create_slot(plan.id, _slot_in(ws.id, note="Einarbeitung Azubi"), db=db, current_user=admin)

    copy = duplicate_plan(plan.id, PlanDuplicateIn(name="Notizplan Kopie"), db=db, current_user=admin)
    detail = get_plan(UUID(copy["id"]), db=db, current_user=admin)
    assert [s["note"] for s in detail["slots"]] == ["Einarbeitung Azubi"]


def test_self_export_includes_the_note_on_own_shift_assignment(db, default_tenant):
    """Minor (Prüfrunde 2): die Art.-15-Selbstauskunft
    (``lifecycle_service.build_self_export_payload``) ließ ``note`` bislang
    kommentarlos aus, während ``anonymize_tenant`` das Feld im selben Modul
    mit der Begründung leert, es könne Personenbezug tragen — beides zugleich
    zu behaupten war widersprüchlich.

    Entscheidung (siehe Kommentar an der Abfrage in ``lifecycle_service.py``):
    der Hinweis wird in die eigene Selbstauskunft aufgenommen. Er ist ohnehin
    schon breiter sichtbar als jede Selbstauskunft (Bildschirm für alle mit
    Plansicht + PDF-Aushang am Schwarzen Brett) — ihn dem Mitarbeitenden
    selbst vorzuenthalten wäre widersprüchlich zu dieser bewussten
    öffentlichen Sichtbarkeit. Das Nullen bei ``anonymize_tenant`` ist eine
    Löschpflicht nach dem Ausscheiden, kein Zugriffsverbot für aktive
    Mitarbeitende auf die eigene Einteilung."""
    admin = _admin(db, "note_export_admin")
    emp = _employee(db, "note_export_emp")
    plan = _plan(db, admin, "Notizplan Export")
    ws = _ws(db, "Tresen Export")
    db.add(SystemSetting(key="shift_planning_enabled", tenant_id=DEFAULT_TENANT_ID, value="true"))
    db.commit()

    created = create_slot(
        plan.id, _slot_in(ws.id, note="Vertretung für Frau Schmidt"), db=db, current_user=admin,
    )
    db.add(ShiftAssignment(
        tenant_id=DEFAULT_TENANT_ID, shift_slot_id=UUID(created["id"]), user_id=emp.id,
    ))
    db.commit()

    payload = lifecycle_service.build_self_export_payload(db, emp)

    assert payload["shift_assignments"] == [{
        "plan": "Notizplan Export",
        "weekday": "Mo",
        "start_time": "08:00",
        "end_time": "12:00",
        "workstation": "Tresen Export",
        "note": "Vertretung für Frau Schmidt",
    }]
