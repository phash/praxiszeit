"""Residual-Fixes F136: Gutschrift am verkürzten Tag — TRAINING, Tagessoll aus der
datierten Verlaufszeile (nicht aus der Live-Zeile) und Exporte für Personen ohne
Stundenzählung bzw. am letzten Tag des Beschäftigungsfensters."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import AbsenceType
from app.services import calculation_service as cs
from app.services import export_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.reduced_days_helpers import reduce_day
from tests.test_497_498_export_day_rows import _xlsx_day_rows, _xlsx_employee_sheet
from tests.wh_change_helpers import absence, add_row

D24 = date(2026, 12, 24)   # Donnerstag, Heiligabend max 4 h


def _delta(db, user, d):
    return cs.get_range_actual(db, user, d, d) - cs.get_range_target(db, user, d, d)


def test_training_on_reduced_day_is_weighted_min_t_x_over_t(db, test_user):
    """Tagessoll 8 h, Verkürzung auf 4 h → Gewicht 4/8: 8 h TRAINING zählen 4 h, Tag neutral."""
    reduce_day(db, D24, "4")
    absence(db, test_user, D24, AbsenceType.TRAINING, hours=8.0)
    assert cs.get_range_actual(db, test_user, D24, D24) == Decimal("4")
    assert cs.get_range_target(db, test_user, D24, D24) == Decimal("4")
    assert _delta(db, test_user, D24) == Decimal("0")


def test_credit_weight_uses_dated_daily_target_not_live_user_row(db, test_user):
    """Live-Zeile 40 h/Woche (8 h), aber ab 01.11. gilt per Verlaufszeile 15 h/Woche
    (3 h). 3 h < Obergrenze 4 h → Gewicht 1: die Krankheit zählt voll (3 h), Tag neutral.
    Mit dem Live-Tagessoll (8 h) wäre das Gewicht 0,5 und der Tag nicht neutral."""
    reduce_day(db, D24, "4")
    add_row(db, test_user, date(2026, 11, 1), weekly_hours=15,
            vacation_days=test_user.vacation_days, track_hours=True,
            milog_working_time_account=False, agreed_monthly_hours=None,
            use_fixed_monthly_target=False)
    db.refresh(test_user)
    assert Decimal(str(test_user.weekly_hours)) == Decimal("40")   # Live-Zeile bleibt 8 h/Tag
    absence(db, test_user, D24, AbsenceType.SICK, hours=3.0)
    assert cs.get_range_target(db, test_user, D24, D24) == Decimal("3")
    assert cs.get_range_actual(db, test_user, D24, D24) == Decimal("3")
    assert _delta(db, test_user, D24) == Decimal("0")


def _day_row(db, user, d):
    bio = export_service.generate_monthly_report(db, d.year, d.month, tenant_id=DEFAULT_TENANT_ID)
    return _xlsx_day_rows(_xlsx_employee_sheet(bio, user))[d]


def test_export_sick_on_reduced_day_without_hour_counting(db, test_user):
    """Person ohne Stundenzählung: Tagessoll 0, Differenz 0 — die Krankheit am verkürzten
    Tag erzeugt weder Plus noch Minus in der Datei."""
    reduce_day(db, D24, "4")
    test_user.track_hours = False
    db.commit()
    absence(db, test_user, D24, AbsenceType.SICK, hours=0.0)
    row = _day_row(db, test_user, D24)
    assert row[6] in (0, 0.0, None)   # Soll
    assert row[7] in (0, 0.0, None)   # Differenz


def test_export_sick_on_reduced_last_day_of_employment_window(db, test_user):
    """Letzter Arbeitstag = der verkürzte Tag: Soll 4 h, Gutschrift 4 h, Differenz 0;
    Σ Tages-Differenz = Saldo des Monats."""
    reduce_day(db, D24, "4")
    test_user.last_work_day = D24
    db.commit()
    absence(db, test_user, D24, AbsenceType.SICK, hours=8.0)
    row = _day_row(db, test_user, D24)
    assert row[6] == pytest.approx(4.0)
    assert row[7] == pytest.approx(0.0, abs=0.01)
    bio = export_service.generate_monthly_report(db, 2026, 12, tenant_id=DEFAULT_TENANT_ID)
    rows = _xlsx_day_rows(_xlsx_employee_sheet(bio, test_user))
    saldo = cs.get_monthly_balance(db, test_user, 2026, 12)
    assert sum(r[7] for r in rows.values()) == pytest.approx(float(saldo), abs=0.01)
