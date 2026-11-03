"""Teil B (Task 6): §16-Exporte und Monatsjournal rechnen verkürzte Tage wie die Berechnung."""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import Absence, AbsenceType, ReducedDay, TimeEntry
from app.models.system_setting import SystemSetting
from app.services import calculation_service as cs
from app.services import export_service, ods_export_service, journal_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_497_498_export_day_rows import (
    _ods_day_rows, _ods_table, _pdf_main_table, _xlsx_day_rows, _xlsx_employee_sheet,
)
from tests.test_audit_20260731_export_ist import _xlsx_summary

YEAR, MONTH = 2026, 12
D23 = date(2026, 12, 23)   # Mi, Urlaub
D24 = date(2026, 12, 24)   # Do, Heiligabend max 4 h, Krank
D28 = date(2026, 12, 28)   # Mo, eigener Tag max 6 h, 6 h gestempelt
SUMMARY = ("Soll-Stunden Monat:", "Ist-Stunden Monat:", "Saldo Monat:")


@pytest.fixture
def dec_month(db, test_user):
    for k, v in (("special_day_dec24_mode", "max_hours"), ("special_day_dec24_max_hours", "4")):
        db.add(SystemSetting(key=k, value=v, description=k, tenant_id=DEFAULT_TENANT_ID))
    db.add(ReducedDay(tenant_id=DEFAULT_TENANT_ID, date=D28, label="Brueckentag",
                      max_hours=Decimal("6")))
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=D28,
                     start_time=time(8, 0), end_time=time(14, 0), break_minutes=0))
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=D24,
                   type=AbsenceType.SICK, hours=4.0))
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=D23,
                   type=AbsenceType.VACATION, hours=8.0))
    db.commit()
    return test_user


def _name(u):
    return f"{u.last_name} {u.first_name}"[:31]


def test_xlsx_monthly_day_soll_and_summary(db, dec_month):
    bio = export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    rows = _xlsx_day_rows(_xlsx_employee_sheet(bio, dec_month))
    assert rows[D24][6] == pytest.approx(4.0)
    assert rows[D28][6] == pytest.approx(6.0)
    target = cs.get_monthly_target(db, dec_month, YEAR, MONTH)
    actual = cs.get_monthly_actual(db, dec_month, YEAR, MONTH)
    s = _xlsx_summary(export_service.generate_monthly_report(
        db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID), dec_month, SUMMARY)
    assert s["Soll-Stunden Monat:"] == pytest.approx(float(target))
    assert s["Ist-Stunden Monat:"] == pytest.approx(float(actual))
    assert s["Saldo Monat:"] == pytest.approx(float(actual - target))
    assert sum(r[7] for r in rows.values()) == pytest.approx(float(actual - target), abs=0.01)


def test_xlsx_yearly_employee_sheet_parity(db, dec_month):
    bio = export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID)
    rows = _xlsx_day_rows(_xlsx_employee_sheet(bio, dec_month, yearly=True))
    assert rows[D24][6] == pytest.approx(4.0)
    s = _xlsx_summary(export_service.generate_yearly_report(
        db, YEAR, tenant_id=DEFAULT_TENANT_ID), dec_month, ("Soll-Stunden Jahr:",))
    expected = sum(cs.get_monthly_target(db, dec_month, YEAR, m) for m in range(1, 13))
    assert s["Soll-Stunden Jahr:"] == pytest.approx(float(expected))


def test_ods_monthly_parity(db, dec_month):
    from app.services.ods_export_service import _doc_with_styles, _monthly_sheet
    from tests.test_ods_export_service import _summary_value
    target = cs.get_monthly_target(db, dec_month, YEAR, MONTH)
    actual = cs.get_monthly_actual(db, dec_month, YEAR, MONTH)
    doc, bold, normal = _doc_with_styles()
    _monthly_sheet(doc, db, dec_month, YEAR, MONTH, bold, normal)
    sheet = _name(dec_month)
    assert _summary_value(doc, sheet, "Soll-Stunden Monat:") == pytest.approx(float(target))
    assert _summary_value(doc, sheet, "Ist-Stunden Monat:") == pytest.approx(float(actual))
    assert _summary_value(doc, sheet, "Saldo Monat:") == pytest.approx(float(actual - target))


def test_ods_yearly_employee_day_soll(db, dec_month):
    table = _ods_table(ods_export_service.generate_yearly_report(
        db, YEAR, tenant_id=DEFAULT_TENANT_ID), _name(dec_month))
    rows = _ods_day_rows(table)
    assert float(rows[D24][6][1]) == pytest.approx(4.0)
    assert float(rows[D28][6][1]) == pytest.approx(6.0)
    # SICK 4 h * (4/8) = 2 h Gutschrift gegen Soll 4 h
    assert float(rows[D24][7][1]) == pytest.approx(-2.0)


def test_pdf_monthly_builds_on_reduced_day(db, dec_month, monkeypatch):
    header, rows = _pdf_main_table(db, monkeypatch, YEAR, MONTH)
    soll_idx = next(i for i, h in enumerate(header) if h.startswith("Soll"))
    assert rows[D24][soll_idx] == "4.00"
    assert rows[D28][soll_idx] == "6.00"


def test_journal_day_rows_and_summary(db, dec_month):
    j = journal_service.get_journal(db, dec_month, YEAR, MONTH)
    days = {d["date"] if isinstance(d["date"], date) else date.fromisoformat(str(d["date"])): d
            for d in j["days"]}
    assert days[D24]["target_hours"] == pytest.approx(4.0)
    assert days[D28]["target_hours"] == pytest.approx(6.0)
    # SICK 4 h auf Tag mit Soll 8 -> Gewicht 4/8, Gutschrift 2 h; Saldo des Tages = 2 - 4
    assert days[D24]["actual_hours"] == pytest.approx(2.0)
    assert j["monthly_summary"]["target_hours"] == pytest.approx(
        float(cs.get_monthly_target(db, dec_month, YEAR, MONTH)), abs=0.01)
    assert j["monthly_summary"]["actual_hours"] == pytest.approx(
        float(cs.get_monthly_actual(db, dec_month, YEAR, MONTH)), abs=0.01)
