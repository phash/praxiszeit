"""#408: Jahresurlaubsanspruch (User.vacation_days) mit Nachkommastelle.

Kundenreport (philvdb): eine 3-Tage-Teilzeitkraft hat 28×3/5 = 16,8 Urlaubstage.
Bisher nur ganzzahlig eingebbar → gerundet auf 17 → 0,2 Tage Ungerechtigkeit
vs. einer Kollegin mit unterjährigem Eintritt. `vacation_days` akzeptiert jetzt
Dezimalwerte (Numeric(4,1), Schema float, ge=0/le=50). Der Calc rechnete bereits
mit `Decimal(str(user.vacation_days))` — nur Speicher/Schema/Eingabe blockierten.
"""
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.models import User, UserRole
from app.schemas.user import UserBase, UserUpdate
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _base_kwargs(**over):
    kw = dict(
        username="dec", email="dec@t.l", first_name="De", last_name="Ci",
        weekly_hours=16.8, work_days_per_week=3, vacation_days=16.8,
    )
    kw.update(over)
    return kw


def test_userbase_accepts_decimal_vacation_days():
    m = UserBase(**_base_kwargs(vacation_days=16.8))
    assert float(m.vacation_days) == pytest.approx(16.8)


def test_userupdate_accepts_decimal_vacation_days():
    m = UserUpdate(vacation_days=22.4)
    assert float(m.vacation_days) == pytest.approx(22.4)


def test_vacation_days_rejects_over_50():
    with pytest.raises(ValidationError):
        UserBase(**_base_kwargs(vacation_days=50.1))


def test_vacation_days_rejects_negative():
    with pytest.raises(ValidationError):
        UserBase(**_base_kwargs(vacation_days=-0.5))


def test_vacation_days_whole_number_still_ok():
    m = UserBase(**_base_kwargs(vacation_days=30))
    assert float(m.vacation_days) == pytest.approx(30.0)


def _user(db, vacation_days):
    u = User(
        id=uuid.uuid4(), username=f"v{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.l",
        password_hash="x", first_name="V", last_name="D", role=UserRole.EMPLOYEE,
        weekly_hours=16.8, work_days_per_week=3, vacation_days=vacation_days,
        track_hours=True, use_daily_schedule=False, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_vacation_account_budget_is_decimal(db):
    """Ganzjährig beschäftigt, 16,8 Tage Anspruch, keine Abwesenheiten →
    Budget + Rest = 16,8 (nicht auf 16 oder 17 gerundet)."""
    u = _user(db, 16.8)
    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == pytest.approx(16.8, abs=0.05)
    assert acc["remaining_days"] == pytest.approx(16.8, abs=0.05)
