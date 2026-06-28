"""Fix #7: shift-plan read endpoints must gate non-admins server-side.

list_plans returns only plans active today for non-admins; get_plan 404s a
non-admin on an inactive (draft) plan. Admins see everything.
"""
import pytest
from fastapi import HTTPException

from app.models import User, UserRole
from app.models.shift_planning import ShiftPlan
from app.routers.shift_planning import list_plans, get_plan
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


def _plan(db, creator, name, active):
    p = ShiftPlan(
        tenant_id=DEFAULT_TENANT_ID, name=name, is_active=active,
        created_by=creator.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_list_plans_hides_inactive_drafts_from_non_admin(db, default_tenant):
    admin = _user(db, "fix7_admin", role=UserRole.ADMIN)
    emp = _user(db, "fix7_emp")
    active = _plan(db, admin, "Aktiv", active=True)
    draft = _plan(db, admin, "Entwurf", active=False)

    emp_view = list_plans(db=db, current_user=emp)
    names = {p["name"] for p in emp_view}
    assert "Aktiv" in names
    assert "Entwurf" not in names

    admin_view = list_plans(db=db, current_user=admin)
    admin_names = {p["name"] for p in admin_view}
    assert {"Aktiv", "Entwurf"} <= admin_names


def test_get_plan_404s_non_admin_on_inactive(db, default_tenant):
    admin = _user(db, "fix7_admin2", role=UserRole.ADMIN)
    emp = _user(db, "fix7_emp2")
    draft = _plan(db, admin, "Entwurf2", active=False)

    with pytest.raises(HTTPException) as exc:
        get_plan(draft.id, db=db, current_user=emp)
    assert exc.value.status_code == 404

    # admin can open the draft
    detail = get_plan(draft.id, db=db, current_user=admin)
    assert detail["name"] == "Entwurf2"

    # non-admin CAN open an active plan
    active = _plan(db, admin, "Aktiv2", active=True)
    ok = get_plan(active.id, db=db, current_user=emp)
    assert ok["name"] == "Aktiv2"
