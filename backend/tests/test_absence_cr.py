"""Tests für Änderungsanträge mit Absence-Typen und Absence-Zeiten."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import (
    User, UserRole, TimeEntry, Absence, AbsenceType,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_user(db, username="cr_user", email="cr@test.de", **kwargs):
    defaults = dict(
        password_hash="hash", first_name="CR", last_name="User",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    user = User(username=username, email=email, **defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_absence(db, user, d, absence_type, hours, start_t=None, end_t=None):
    absence = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        date=d, type=absence_type, hours=hours,
        start_time=start_t, end_time=end_t,
    )
    db.add(absence)
    db.commit()
    return absence


def _make_absence_cr(db, user, request_type="create", **kwargs):
    defaults = dict(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=request_type, entry_kind="absence",
        status=ChangeRequestStatus.PENDING,
        reason="Testantrag",
    )
    defaults.update(kwargs)
    cr = ChangeRequest(**defaults)
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


class TestAbsenceCRModel:
    """Absence-CR Model-Tests."""

    def test_create_absence_cr_pending(self, db, test_user):
        cr = _make_absence_cr(db, test_user,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="sick",
            proposed_absence_hours=8.0,
        )
        assert cr.entry_kind == "absence"
        assert cr.status == ChangeRequestStatus.PENDING
        assert cr.proposed_absence_type == "sick"

    def test_absence_cr_with_times(self, db, test_user):
        cr = _make_absence_cr(db, test_user,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="training",
            proposed_absence_hours=3.0,
            proposed_start_time=time(14, 0),
            proposed_end_time=time(17, 0),
        )
        assert cr.proposed_start_time == time(14, 0)
        assert cr.proposed_end_time == time(17, 0)

    def test_absence_cr_update_snapshots_original(self, db, test_user):
        absence = _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, 8.0)
        cr = _make_absence_cr(db, test_user,
            request_type="update",
            absence_id=absence.id,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="sick",
            proposed_absence_hours=8.0,
            original_absence_type="vacation",
            original_absence_hours=8.0,
        )
        assert cr.original_absence_type == "vacation"
        assert str(cr.absence_id) == str(absence.id)

    def test_entry_kind_default_is_time_entry(self, db, test_user):
        cr = ChangeRequest(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            request_type="create", status=ChangeRequestStatus.PENDING,
            reason="Test", proposed_date=date(2026, 3, 10),
            proposed_start_time=time(8, 0), proposed_end_time=time(16, 0),
        )
        db.add(cr)
        db.commit()
        db.refresh(cr)
        assert cr.entry_kind == "time_entry"


class TestAbsenceStartEndTime:
    """Absence mit Start-/Endzeit."""

    def test_absence_with_times(self, db, test_user):
        absence = _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.TRAINING, 3.0,
            start_t=time(14, 0), end_t=time(17, 0))
        assert absence.start_time == time(14, 0)
        assert absence.end_time == time(17, 0)

    def test_absence_whole_day_no_times(self, db, test_user):
        absence = _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.VACATION, 8.0)
        assert absence.start_time is None
        assert absence.end_time is None

    def test_absence_times_in_journal(self, db, test_user):
        """Absence mit Zeiten zeigt start_time/end_time im Journal."""
        from app.services import journal_service
        _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.TRAINING, 3.0,
            start_t=time(14, 0), end_t=time(17, 0))
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert len(day["absences"]) == 1
        assert day["absences"][0]["start_time"] == "14:00"
        assert day["absences"][0]["end_time"] == "17:00"

    def test_absence_whole_day_no_times_in_journal(self, db, test_user):
        """Ganztags-Absence zeigt None für start_time/end_time im Journal."""
        from app.services import journal_service
        _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.VACATION, 8.0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["absences"][0]["start_time"] is None
        assert day["absences"][0]["end_time"] is None
