"""Fix #4: der UPDATE-Branch der CR-Genehmigung (review_change_request) setzte
absence.type=VACATION + buchte das Tagessoll OHNE Urlaubsbudget-Check — der
CREATE-Branch prüft ihn. → Eine Genehmigung konnte das Budget überziehen.

Geprüft wird der NETTO-Neuverbrauch (post − bisher gezählt), damit ein reiner
Zeit-Edit eines bestehenden Urlaubstags nicht fälschlich scheitert.
"""
from datetime import date, time

import pytest
from fastapi import HTTPException

from app.models import (
    User, UserRole, Absence, AbsenceType,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.routers.admin_change_requests import review_change_request
from app.schemas.change_request import ChangeRequestReview
from tests.conftest import DEFAULT_TENANT_ID

WORKDAY = date(2026, 3, 10)  # Dienstag


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30, **kwargs):
    defaults = dict(
        email=f"{username}@x.de", password_hash="h", first_name=username,
        last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_absence(db, user, d, absence_type, hours, half_day=False):
    a = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        type=absence_type, hours=hours, half_day=half_day,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _make_update_cr(db, user, absence, **kwargs):
    defaults = dict(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.UPDATE, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="Testantrag",
        absence_id=absence.id,
    )
    defaults.update(kwargs)
    cr = ChangeRequest(**defaults)
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


def test_update_to_vacation_overrun_rejected(db, default_tenant):
    """remaining_days=0, SICK-Absence per CR-UPDATE auf VACATION → 400."""
    admin = _make_user(db, "fx4_admin", role=UserRole.ADMIN)
    emp = _make_user(db, "fx4_emp", vacation_days=0)  # Budget 0 → remaining 0
    sick = _make_absence(db, emp, WORKDAY, AbsenceType.SICK, 8.0)
    cr = _make_update_cr(
        db, emp, sick,
        proposed_date=WORKDAY, proposed_absence_type="vacation",
        proposed_absence_hours=8.0,
    )
    with pytest.raises(HTTPException) as exc:
        review_change_request(
            request_id=str(cr.id),
            review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )
    assert exc.value.status_code == 400
    assert "Urlaubstage" in exc.value.detail
    db.rollback()
    db.refresh(sick)
    # Typ unverändert (Mutation nicht durchgeführt).
    assert sick.type == AbsenceType.SICK


def test_update_to_vacation_within_budget_ok(db, default_tenant):
    """Genug Budget → SICK→VACATION per CR-UPDATE wird genehmigt."""
    admin = _make_user(db, "fx4_admin2", role=UserRole.ADMIN)
    emp = _make_user(db, "fx4_emp2", vacation_days=30)
    sick = _make_absence(db, emp, WORKDAY, AbsenceType.SICK, 8.0)
    cr = _make_update_cr(
        db, emp, sick,
        proposed_date=WORKDAY, proposed_absence_type="vacation",
        proposed_absence_hours=8.0,
    )
    review_change_request(
        request_id=str(cr.id),
        review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )
    db.refresh(sick)
    assert sick.type == AbsenceType.VACATION


def test_update_existing_vacation_time_edit_not_blocked(db, default_tenant):
    """Reiner Zeit-Edit eines BESTEHENDEN Urlaubstags (Typ bleibt VACATION,
    Datum gleich) darf trotz remaining_days=0 NICHT scheitern (net_new=0)."""
    admin = _make_user(db, "fx4_admin3", role=UserRole.ADMIN)
    emp = _make_user(db, "fx4_emp3", vacation_days=1)  # Budget 1
    vac = _make_absence(db, emp, WORKDAY, AbsenceType.VACATION, 8.0)  # verbraucht 1 → rest 0
    cr = _make_update_cr(
        db, emp, vac,
        proposed_date=WORKDAY, proposed_absence_type="vacation",
        proposed_absence_hours=8.0,
        proposed_start_time=time(9, 0), proposed_end_time=time(13, 0),
    )
    # Darf NICHT 400 werfen, obwohl remaining_days == 0.
    review_change_request(
        request_id=str(cr.id),
        review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )
    db.refresh(vac)
    assert vac.type == AbsenceType.VACATION
