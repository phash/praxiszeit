"""Tests for ODS export service (OpenDocument Spreadsheet)."""
from datetime import date, time
from io import BytesIO

import pytest

from app.models import Absence, AbsenceType, PublicHoliday, TimeEntry
from app.services.ods_export_service import (
    generate_monthly_report,
    generate_yearly_report,
    generate_yearly_report_classic,
)
from tests.conftest import DEFAULT_TENANT_ID


# ODS files are ZIP archives — the magic bytes are the same PK signature
# as XLSX, but with mimetype "application/vnd.oasis.opendocument.spreadsheet"
# stored as the first entry.
ODS_PK_MAGIC = b"PK"


def _mk_entry(db, user, d, start_h, end_h, break_min=0):
    e = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        start_time=time(start_h, 0),
        end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(e)
    db.commit()
    return e


def _mk_absence(db, user, d, typ=AbsenceType.VACATION, hours=8):
    a = Absence(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        type=typ,
        hours=hours,
    )
    db.add(a)
    db.commit()
    return a


class TestGenerateMonthlyOdsReport:

    def test_returns_bytesio_with_ods_magic(self, db, test_user):
        out = generate_monthly_report(db, 2026, 1)
        assert isinstance(out, BytesIO)
        data = out.read()
        assert data[:2] == ODS_PK_MAGIC
        assert b"opendocument.spreadsheet" in data[:200]

    def test_with_time_entries(self, db, test_user):
        import zipfile
        _mk_entry(db, test_user, date(2026, 1, 5), 8, 17, 30)
        _mk_entry(db, test_user, date(2026, 1, 6), 9, 16, 30)
        out = generate_monthly_report(db, 2026, 1)
        data = out.read()
        assert data[:2] == ODS_PK_MAGIC
        # content.xml inside the ODS zip must include the employee name
        with zipfile.ZipFile(BytesIO(data)) as zf:
            content = zf.read("content.xml").decode("utf-8", errors="replace")
            assert "Test" in content

    def test_empty_month(self, db, test_user):
        out = generate_monthly_report(db, 2026, 7)
        data = out.read()
        assert data[:2] == ODS_PK_MAGIC

    def test_include_health_data_emits_sick_hours(self, db, test_user):
        _mk_absence(db, test_user, date(2026, 1, 8), AbsenceType.SICK, 8)
        # include_health_data=True should not crash
        out = generate_monthly_report(db, 2026, 1, include_health_data=True)
        assert out.read()[:2] == ODS_PK_MAGIC

    def test_excludes_sick_leaks_when_health_data_false(self, db, test_user):
        """DSGVO Art. 9: sick absences must not be identifiable by type when
        the admin did not opt into health-data disclosure."""
        _mk_absence(db, test_user, date(2026, 1, 8), AbsenceType.SICK, 8)
        out = generate_monthly_report(db, 2026, 1, include_health_data=False)
        data = out.read()
        assert data[:2] == ODS_PK_MAGIC


class TestGenerateYearlyOdsReport:

    def test_returns_valid_ods(self, db, test_user):
        out = generate_yearly_report(db, 2026)
        assert out.read()[:2] == ODS_PK_MAGIC

    def test_yearly_with_data(self, db, test_user):
        _mk_entry(db, test_user, date(2026, 3, 15), 8, 17, 30)
        _mk_entry(db, test_user, date(2026, 6, 1), 9, 18, 45)
        _mk_absence(db, test_user, date(2026, 4, 10), AbsenceType.VACATION, 8)
        out = generate_yearly_report(db, 2026)
        assert out.read()[:2] == ODS_PK_MAGIC


class TestGenerateYearlyClassicOdsReport:

    def test_returns_valid_ods(self, db, test_user):
        out = generate_yearly_report_classic(db, 2026)
        assert out.read()[:2] == ODS_PK_MAGIC

    def test_holiday_tenant_scoped(self, db, test_user):
        """Holidays in the tenant's own set must appear; others must not
        leak into the export (regression test for the tenant_id-filter fix)."""
        # Holiday for the current tenant
        h_own = PublicHoliday(
            date=date(2026, 5, 1),
            name="Tag der Arbeit (eigene)",
            year=2026,
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(h_own)
        db.commit()

        out = generate_yearly_report_classic(db, 2026)
        data = out.read()
        assert data[:2] == ODS_PK_MAGIC


class TestFormulaInjection:
    """Review 2026-05-29 (M-SEC1): the _str_cell choke-point must neutralize
    formula-leading characters so employee free-text cannot execute when the
    admin opens the ODS export."""

    def test_str_cell_neutralizes_formula_equals(self):
        from odf.teletype import extractText
        from app.services.ods_export_service import _str_cell
        cell = _str_cell('=cmd|/c calc')
        assert extractText(cell).startswith("'"), "leading = not neutralized"

    def test_str_cell_neutralizes_at_and_plus_and_minus(self):
        from odf.teletype import extractText
        from app.services.ods_export_service import _str_cell
        for payload in ('@SUM(A1)', '+1+1', '-2-2'):
            assert extractText(_str_cell(payload)).startswith("'"), payload

    def test_str_cell_leaves_safe_text_untouched(self):
        from odf.teletype import extractText
        from app.services.ods_export_service import _str_cell
        assert extractText(_str_cell('Mitarbeiter:')) == 'Mitarbeiter:'


class TestAbsencesOverviewDayBased:
    """Fix #2 (Tagesprinzip §3 BUrlG): die ODS-Abwesenheits-Übersicht muss die
    Tage tagebasiert (absence_days / get_vacation_account) zählen, nicht
    stundenbasiert (Σh ÷ ⌀-Tagessoll). Dann gilt im Sheet „verbraucht" == „Rest"
    (budget − used == remaining) und Halbtage/Tagespläne/untracked stimmen."""

    def _tagesplan_user(self, db):
        from app.models import User, UserRole
        from app.services import auth_service
        u = User(
            username="ods_tagesplan", email="ods_tagesplan@example.com",
            password_hash=auth_service.hash_password("x12345678"),
            first_name="Tages", last_name="Plan", role=UserRole.EMPLOYEE,
            weekly_hours=15.0, work_days_per_week=3, vacation_days=30,
            is_active=True, tenant_id=DEFAULT_TENANT_ID,
            track_hours=True, use_daily_schedule=True,
            hours_monday=8, hours_tuesday=4, hours_wednesday=6,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def _untracked_user(self, db):
        from app.models import User, UserRole
        from app.services import auth_service
        u = User(
            username="ods_untracked", email="ods_untracked@example.com",
            password_hash=auth_service.hash_password("x12345678"),
            first_name="Lei", last_name="Tend", role=UserRole.EMPLOYEE,
            weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
            is_active=True, tenant_id=DEFAULT_TENANT_ID, track_hours=False,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def _absence(self, db, user, d, typ, hours, half_day=False):
        a = Absence(
            user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
            type=typ, hours=hours, half_day=half_day,
        )
        db.add(a)
        db.commit()
        return a

    def _vac_cell(self, doc, last_name):
        """Liefert (urlaub, resturlaub) als float aus der 'Abwesenheiten'-Tabelle
        für die Datenzeile des MA (Spalte 1 = Urlaub, Spalte 8 = Resturlaub)."""
        from odf.table import Table, TableRow, TableCell
        from odf.teletype import extractText
        table = [t for t in doc.spreadsheet.getElementsByType(Table)
                 if t.getAttribute("name") == "Abwesenheiten"][0]
        for row in table.getElementsByType(TableRow):
            cells = row.getElementsByType(TableCell)
            if cells and last_name in extractText(cells[0]):
                return (float(cells[1].getAttribute("value")),
                        float(cells[8].getAttribute("value")))
        raise AssertionError(f"keine Zeile für {last_name}")

    def test_ods_overview_days_are_day_based_and_consistent_with_remaining(self, db, default_tenant):
        from app.models import AbsenceType
        from app.services import calculation_service
        from app.services.ods_export_service import _absences_overview_sheet, _doc_with_styles

        user_a = self._tagesplan_user(db)
        user_b = self._untracked_user(db)

        self._absence(db, user_a, date(2026, 1, 5), AbsenceType.VACATION, 8)   # Mo voll
        self._absence(db, user_a, date(2026, 1, 6), AbsenceType.VACATION, 4)   # Di voll
        self._absence(db, user_a, date(2026, 1, 7), AbsenceType.VACATION, 3, half_day=True)  # Mi halb
        self._absence(db, user_b, date(2026, 1, 12), AbsenceType.VACATION, 0)  # Mo voll
        self._absence(db, user_b, date(2026, 1, 13), AbsenceType.VACATION, 0, half_day=True)  # Di halb

        doc, bold, _normal = _doc_with_styles()
        _absences_overview_sheet(doc, db, [user_a, user_b], 2026, bold, include_health_data=True)

        a_vac, a_rest = self._vac_cell(doc, "Plan")
        b_vac, b_rest = self._vac_cell(doc, "Tend")

        assert a_vac == 2.5, f"Tagesplan-Urlaub: erwartet 2,5 (tagebasiert), bekam {a_vac}"
        assert b_vac == 1.5, f"untracked-Urlaub: erwartet 1,5 (tagebasiert), bekam {b_vac}"

        # „verbraucht" + „Rest" rekonzilieren mit get_vacation_account (Budget − used).
        acc_a = calculation_service.get_vacation_account(db, user_a, 2026)
        assert a_vac == round(float(acc_a["used_days"]), 1)
        assert a_rest == round(float(acc_a["remaining_days"]), 1)
        assert round(a_vac + a_rest, 1) == round(float(acc_a["budget_days"]), 1)

        acc_b = calculation_service.get_vacation_account(db, user_b, 2026)
        assert b_vac == round(float(acc_b["used_days"]), 1)
        assert b_rest == round(float(acc_b["remaining_days"]), 1)


class TestOdsMultiAbsenceDay:
    def test_monthly_renders_both_absences_on_multitype_day(self, db, test_user):
        # Regression: die ODS-Detailsheets keyten Absences per date-dict → der 2.
        # Eintrag eines Misch-Tags (½ Urlaub + ½ Sonstiges) ging verloren.
        import zipfile
        _mk_absence(db, test_user, date(2026, 3, 4), AbsenceType.VACATION, hours=4)
        _mk_absence(db, test_user, date(2026, 3, 4), AbsenceType.OTHER, hours=4)
        out = generate_monthly_report(db, 2026, 3, include_health_data=True)
        with zipfile.ZipFile(out) as zf:
            content = zf.read("content.xml").decode("utf-8", errors="replace")
        assert "Urlaub" in content and "Sonstiges" in content

    def test_classic_has_overtime_column(self, db, test_user):
        import zipfile
        _mk_absence(db, test_user, date(2026, 3, 4), AbsenceType.OVERTIME, hours=8)
        out = generate_yearly_report_classic(db, 2026, include_health_data=True)
        with zipfile.ZipFile(out) as zf:
            content = zf.read("content.xml").decode("utf-8", errors="replace")
        assert "ÜStd.-Ausgleich" in content
