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
