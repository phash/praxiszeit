"""Tests for export service (monthly Excel report generation)."""
import pytest
from datetime import date, time
from io import BytesIO
from app.models import User, UserRole, TimeEntry
from app.services.export_service import generate_monthly_report
from tests.conftest import DEFAULT_TENANT_ID


def _make_time_entry(db, user, entry_date, start_h, end_h, break_min=0):
    """Helper to create a time entry."""
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=entry_date,
        start_time=time(start_h, 0),
        end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    return entry


class TestGenerateMonthlyReport:
    """Test generate_monthly_report() core behavior."""

    def test_returns_bytesio(self, db, test_user):
        """Report must return a BytesIO object."""
        result = generate_monthly_report(db, 2026, 1)
        assert isinstance(result, BytesIO)

    def test_returns_xlsx_magic_bytes(self, db, test_user):
        """Returned bytes must start with PK (ZIP/XLSX magic bytes)."""
        result = generate_monthly_report(db, 2026, 1)
        data = result.read()
        assert len(data) > 0
        # XLSX files are ZIP archives, starting with PK (0x504B)
        assert data[:2] == b'PK'

    def test_report_with_time_entries(self, db, test_user):
        """Report with time entries should still produce valid XLSX."""
        _make_time_entry(db, test_user, date(2026, 1, 5), 8, 17, 30)
        _make_time_entry(db, test_user, date(2026, 1, 6), 9, 16, 30)
        _make_time_entry(db, test_user, date(2026, 1, 7), 8, 12, 0)

        result = generate_monthly_report(db, 2026, 1)
        data = result.read()
        assert len(data) > 0
        assert data[:2] == b'PK'

    def test_report_empty_month(self, db, test_user):
        """Report for a month with no entries should still produce valid XLSX."""
        result = generate_monthly_report(db, 2026, 6)
        data = result.read()
        assert len(data) > 0
        assert data[:2] == b'PK'

    def test_report_no_active_users_raises(self, db, test_user):
        """Report with no active users raises IndexError (openpyxl requires >=1 sheet).
        Known limitation: the code removes the default sheet and creates no replacements."""
        test_user.is_active = False
        db.commit()

        with pytest.raises(IndexError, match="At least one sheet must be visible"):
            generate_monthly_report(db, 2026, 1)

    def test_report_with_health_data_flag(self, db, test_user):
        """Report with include_health_data=True should produce valid XLSX."""
        _make_time_entry(db, test_user, date(2026, 1, 5), 8, 17, 30)
        result = generate_monthly_report(db, 2026, 1, include_health_data=True)
        data = result.read()
        assert len(data) > 0
        assert data[:2] == b'PK'

    def test_report_size_increases_with_entries(self, db, test_user):
        """Report with entries should be larger than an empty report."""
        result_empty = generate_monthly_report(db, 2026, 2)
        size_empty = len(result_empty.read())

        # Add entries for March
        for day in range(2, 28):
            try:
                d = date(2026, 3, day)
                if d.weekday() < 5:  # weekdays only
                    _make_time_entry(db, test_user, d, 8, 17, 30)
            except ValueError:
                pass

        result_full = generate_monthly_report(db, 2026, 3)
        size_full = len(result_full.read())

        assert size_full > size_empty
