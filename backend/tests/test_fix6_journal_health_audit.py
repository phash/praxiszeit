"""Fix #6: the admin monthly journal must gate SICK data behind
include_health_data and write an Art. 9 health_data_read audit when it is served
(mirrors reports.py). The masked default does not leak SICK as a day type.
"""
from datetime import date

from app.models import (
    User, UserRole, Absence, AbsenceType, TimeEntryAuditLog,
)
from app.routers.journal import get_user_journal
from app.services import journal_service
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


def _sick(db, user, d):
    a = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        type=AbsenceType.SICK, hours=8.0,
    )
    db.add(a)
    db.commit()


def _audit_count(db):
    return db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.action == "health_data_read",
    ).count()


def test_journal_with_health_data_writes_audit_and_shows_sick(db, default_tenant):
    admin = _user(db, "fix6_admin", role=UserRole.ADMIN)
    emp = _user(db, "fix6_emp")
    _sick(db, emp, date(2026, 3, 10))  # Tuesday

    assert _audit_count(db) == 0
    result = get_user_journal(
        str(emp.id), year=2026, month=3, include_health_data=True,
        db=db, current_user=admin,
    )
    assert _audit_count(db) == 1

    day = next(d for d in result["days"] if d["date"] == "2026-03-10")
    assert day["type"] == "sick"
    assert day["absences"][0]["type"] == "sick"


def test_journal_default_masks_sick_and_no_audit(db, default_tenant):
    admin = _user(db, "fix6_admin2", role=UserRole.ADMIN)
    emp = _user(db, "fix6_emp2")
    _sick(db, emp, date(2026, 3, 10))

    result = get_user_journal(
        str(emp.id), year=2026, month=3, include_health_data=False,
        db=db, current_user=admin,
    )
    assert _audit_count(db) == 0
    day = next(d for d in result["days"] if d["date"] == "2026-03-10")
    assert day["type"] == "absent"  # SICK masked
    assert day["absences"][0]["type"] == "absent"


def test_service_default_shows_sick_for_own_view(db, default_tenant):
    """`/journal/me` (own data) keeps the default include_health_data=True — the
    employee sees their own SICK days, unmasked, no audit."""
    emp = _user(db, "fix6_self")
    _sick(db, emp, date(2026, 3, 10))
    result = journal_service.get_journal(db, emp, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-10")
    assert day["type"] == "sick"
    assert _audit_count(db) == 0
