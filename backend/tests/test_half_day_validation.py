"""Review M1: half_day is a single-day concept.

Both AbsenceCreate (admin direct booking) and VacationRequestCreate (MA self
service) must reject half_day=True on a multi-day range, otherwise the booking
loop would halve every day of the range (surprising + inconsistent with the UI).
Pure-pydantic tests — no DB needed.
"""
import pytest
from datetime import date
from pydantic import ValidationError

from app.schemas.absence import AbsenceCreate
from app.schemas.vacation_request import VacationRequestCreate
from app.models.absence import AbsenceType


def test_absence_half_day_rejects_multiday():
    with pytest.raises(ValidationError):
        AbsenceCreate(
            date=date(2026, 3, 2),
            end_date=date(2026, 3, 6),
            type=AbsenceType.VACATION,
            hours=8,
            half_day=True,
        )


def test_absence_half_day_accepts_single_day():
    a = AbsenceCreate(date=date(2026, 3, 2), type=AbsenceType.VACATION, hours=8, half_day=True)
    assert a.half_day is True


def test_absence_half_day_accepts_explicit_same_start_end():
    a = AbsenceCreate(
        date=date(2026, 3, 2),
        end_date=date(2026, 3, 2),
        type=AbsenceType.VACATION,
        hours=8,
        half_day=True,
    )
    assert a.half_day is True


def test_absence_multiday_without_half_day_is_fine():
    a = AbsenceCreate(
        date=date(2026, 3, 2),
        end_date=date(2026, 3, 6),
        type=AbsenceType.VACATION,
        hours=8,
        half_day=False,
    )
    assert a.end_date == date(2026, 3, 6)


def test_vacation_request_half_day_rejects_multiday():
    with pytest.raises(ValidationError):
        VacationRequestCreate(
            date=date(2026, 3, 2),
            end_date=date(2026, 3, 6),
            hours=8,
            half_day=True,
        )


def test_vacation_request_half_day_accepts_single_day():
    vr = VacationRequestCreate(date=date(2026, 3, 2), hours=8, half_day=True)
    assert vr.half_day is True


# --- Release-Review 1.18.2: dieselbe Regel im PATCH-Pfad -----------------------
#
# Die Einzeltag-Regel lebte nur in den Create-Schemas. `VacationRequestUpdate`
# kannte `half_day` gar nicht, also blieb die Flagge beim Umbau eines
# Halbtags-Antrags in einen Zeitraum still gesetzt — und die Genehmigung
# halbierte anschließend JEDEN Werktag des Zeitraums: 5 freie Tage kosteten
# 2,5 Urlaubstage, und an jedem Tag blieb ein halbes Tagessoll unabgedeckt
# stehen (dauerhaftes Minus im Überstundenkonto, widersprüchlicher §16-Beleg).
# Erreichbar ohne Admin: Antrag mit „halber Tag" anlegen, dann im
# Bearbeiten-Dialog „Zeitraum (mehrere Tage)" setzen.

from datetime import date as _d, timedelta as _td

import pytest
from fastapi import HTTPException

from app.models import User, UserRole, VacationRequest
from app.models.vacation_request import VacationRequestStatus
from app.routers.vacation_requests import apply_vacation_request_patch
from app.schemas.vacation_request import VacationRequestUpdate
from tests.conftest import DEFAULT_TENANT_ID


def _emp(db):
    u = User(
        username="hd_emp", email="hd_emp@t.de", password_hash="h",
        first_name="H", last_name="D", role=UserRole.EMPLOYEE, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _half_day_request(db, user):
    monday = _d(2026, 9, 14)
    vr = VacationRequest(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=monday, end_date=None,
        hours=4.0, half_day=True, status=VacationRequestStatus.PENDING.value,
        absence_type="VACATION",
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


def test_patch_cannot_turn_a_half_day_request_into_a_range(db, default_tenant):
    user = _emp(db)
    vr = _half_day_request(db, user)

    with pytest.raises(HTTPException) as exc:
        apply_vacation_request_patch(
            db, vr,
            VacationRequestUpdate(end_date=vr.date + _td(days=4)),
            target_user=user, acting_user=user,
        )
    assert exc.value.status_code == 400
    assert "Einzeltag" in exc.value.detail
    db.refresh(vr)
    assert vr.end_date is None
    assert vr.half_day is True


def test_patch_may_clear_half_day_together_with_the_range(db, default_tenant):
    # Der ehrliche Weg zum Zeitraum: die Halbtags-Flagge im selben PATCH löschen.
    user = _emp(db)
    vr = _half_day_request(db, user)

    apply_vacation_request_patch(
        db, vr,
        VacationRequestUpdate(end_date=vr.date + _td(days=4), half_day=False, hours=8.0),
        target_user=user, acting_user=user,
    )
    db.refresh(vr)
    assert vr.half_day is False
    assert vr.end_date == _d(2026, 9, 18)


def test_patch_keeps_half_day_on_a_single_day_edit(db, default_tenant):
    user = _emp(db)
    vr = _half_day_request(db, user)

    apply_vacation_request_patch(
        db, vr,
        VacationRequestUpdate(date=vr.date + _td(days=1)),
        target_user=user, acting_user=user,
    )
    db.refresh(vr)
    assert vr.half_day is True
    assert vr.date == _d(2026, 9, 15)
