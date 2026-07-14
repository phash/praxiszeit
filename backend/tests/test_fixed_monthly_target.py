"""#377 Baustein 2b: zentrale Fix-Monats-Soll-Helper."""
from datetime import date
from decimal import Decimal
import pytest
from app.models import User, UserRole, Absence, AbsenceType, PublicHoliday
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID


def _mk(db, **kw):
    base = dict(username="fx", email="fx@t.l", password_hash="x", first_name="F",
                last_name="X", role=UserRole.EMPLOYEE, weekly_hours=Decimal("10"),
                work_days_per_week=2, track_hours=True, is_active=True,
                use_daily_schedule=True, use_fixed_monthly_target=True,
                agreed_monthly_hours=Decimal("40"),
                hours_monday=Decimal("3"), hours_wednesday=Decimal("3"),
                tenant_id=DEFAULT_TENANT_ID)
    base.update(kw)
    u = User(**base); db.add(u); db.commit(); db.refresh(u)
    return u


def test_fixed_target_is_flat_across_months(db, default_tenant):
    u = _mk(db)
    # März 2025 (5 Montage) vs Feb 2025 (4 Montage) → beide 40h fix.
    assert cs.fixed_monthly_target(u, 2025, 3) == Decimal("40.00")
    assert cs.fixed_monthly_target(u, 2025, 2) == Decimal("40.00")


def test_fixed_target_prorata_on_entry(db, default_tenant):
    u = _mk(db, first_work_day=date(2025, 3, 16))  # 16 von 31 Tagen im Fenster
    assert cs.fixed_monthly_target(u, 2025, 3) == (Decimal("40") * 16 / 31).quantize(Decimal("0.01"))


def test_fixed_target_zero_when_flag_off(db, default_tenant):
    u = _mk(db, use_fixed_monthly_target=False)
    assert cs.fixed_monthly_target(u, 2025, 3) == Decimal("0")


def test_credit_holiday_on_planned_day(db, default_tenant):
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 3), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Montag
    db.commit()
    # geplante Mo-Stunden = 3 → Gutschrift 3
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("3.00")


def test_credit_holiday_on_unplanned_day_is_zero(db, default_tenant):
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 4), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Dienstag, ungeplant
    db.commit()
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("0.00")


def test_credit_vacation_but_not_sick(db, default_tenant):
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.VACATION, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 12),
                   type=AbsenceType.SICK, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.commit()
    # NUR VACATION zählt hier (SICK läuft über credited_absences → keine Doppelgutschrift)
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("3.00")


def test_unpaid_other_reduces_soll(db, default_tenant):
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.commit()
    assert cs.fixed_month_unpaid_reduction(db, u, 2025, 3) == Decimal("3.00")
