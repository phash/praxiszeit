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
