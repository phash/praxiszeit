"""Fix #3: approving an absence CR (CREATE / date-or-type-changing UPDATE) must
delete the time entries on the target day, mirroring create_absence — otherwise
the absence AND the time entry both count toward Ist (Saldo inflation).
"""
from datetime import date, time

from app.models import (
    User, UserRole, TimeEntry, Absence, AbsenceType,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
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


def _time_entry(db, user, d):
    te = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=time(8, 0), end_time=time(16, 0), break_minutes=30,
    )
    db.add(te)
    db.commit()
    db.refresh(te)
    return te


def test_create_absence_cr_clears_time_entry(db, default_tenant):
    admin = _user(db, "fix3_admin", role=UserRole.ADMIN)
    emp = _user(db, "fix3_emp")
    d = date(2026, 3, 10)  # Tuesday, workday
    te = _time_entry(db, emp, d)
    cr = ChangeRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.CREATE, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="Urlaub",
        proposed_date=d, proposed_absence_type="vacation",
        proposed_absence_hours=8.0,
    )
    db.add(cr)
    db.commit()
    cr_id = cr.id

    review_change_request(
        str(cr_id), ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )

    # time entry gone
    assert db.query(TimeEntry).filter(TimeEntry.id == te.id).first() is None
    # absence created on that day
    assert db.query(Absence).filter(
        Absence.user_id == emp.id, Absence.date == d,
        Absence.type == AbsenceType.VACATION,
    ).first() is not None


def test_update_absence_cr_date_change_clears_new_day_time_entry(db, default_tenant):
    admin = _user(db, "fix3_admin2", role=UserRole.ADMIN)
    emp = _user(db, "fix3_emp2")
    old_day = date(2026, 3, 10)
    new_day = date(2026, 3, 11)
    # existing absence on old_day
    absence = Absence(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=old_day,
        type=AbsenceType.VACATION, hours=8.0,
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)
    # a time entry on the NEW day the absence is being moved to
    te = _time_entry(db, emp, new_day)

    cr = ChangeRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.UPDATE, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="verschoben",
        absence_id=absence.id,
        proposed_date=new_day, proposed_absence_type="vacation",
        original_absence_type="vacation", original_date=old_day,
    )
    db.add(cr)
    db.commit()
    cr_id = cr.id

    review_change_request(
        str(cr_id), ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )

    assert db.query(TimeEntry).filter(TimeEntry.id == te.id).first() is None
    db.refresh(absence)
    assert absence.date == new_day
