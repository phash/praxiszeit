"""Fix #1: deleting an absence referenced by a ChangeRequest must not crash and
must null the referencing CR.absence_id (belt-and-suspenders for the FK ondelete).

SQLite test DBs run with FK enforcement OFF, so a missing ON DELETE rule does not
raise here — we therefore assert the *application* behaviour: the referencing
ChangeRequest.absence_id is set to NULL on every absence-delete path.
"""
import uuid
from datetime import date, datetime, timezone

from app.models import (
    User, UserRole, Absence, AbsenceType,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.routers.absences import delete_absence
from app.routers.admin_change_requests import review_change_request
from app.schemas.change_request import ChangeRequestReview
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


def _absence(db, user, d=date(2026, 3, 10), t=AbsenceType.VACATION):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=t, hours=8.0)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_delete_absence_nulls_referencing_cr(db, default_tenant):
    """Direct delete_absence: a separate CR that references the absence has its
    absence_id nulled and the delete returns without crashing."""
    user = _user(db, "fix1_emp")
    absence = _absence(db, user)
    cr = ChangeRequest(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.UPDATE, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="x",
        absence_id=absence.id, proposed_date=absence.date,
        proposed_absence_type="sick",
    )
    db.add(cr)
    db.commit()
    cr_id = cr.id

    delete_absence(str(absence.id), db=db, current_user=user)

    assert db.query(Absence).filter(Absence.id == absence.id).first() is None
    refreshed = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    assert refreshed.absence_id is None


def test_approve_absence_delete_cr_nulls_link(db, default_tenant):
    """Approving an Absence-DELETE CR deletes the absence without crashing and the
    CR's own absence_id ends up NULL."""
    admin = _user(db, "fix1_admin", role=UserRole.ADMIN)
    emp = _user(db, "fix1_emp2")
    absence = _absence(db, emp)
    cr = ChangeRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.DELETE, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="weg damit",
        absence_id=absence.id,
        original_absence_type="vacation", original_absence_hours=8.0,
        original_date=absence.date,
    )
    db.add(cr)
    db.commit()
    cr_id = cr.id

    review_change_request(
        str(cr_id), ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )

    assert db.query(Absence).filter(Absence.id == absence.id).first() is None
    refreshed = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    assert refreshed.status == ChangeRequestStatus.APPROVED
    assert refreshed.absence_id is None
