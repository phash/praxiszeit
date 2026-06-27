"""1.12.1 review regression: out-of-range month in a YYYY-MM query param must
return HTTP 400, not leak a 500 from a downstream monthrange()/date() call."""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.services.date_filters import parse_year_month
from tests.test_endpoints import test_app


def test_parse_year_month_valid():
    assert parse_year_month("2026-06") == (2026, 6)
    assert parse_year_month("2026-01") == (2026, 1)
    assert parse_year_month("2026-12") == (2026, 12)


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "2026-99", "abc-06", "2026", "2026-6-1", ""])
def test_parse_year_month_invalid_raises(bad):
    with pytest.raises(ValueError):
        parse_year_month(bad)


@pytest.fixture
def admin_c(db, test_admin):
    def _od():
        yield db
    test_app.dependency_overrides[get_db] = _od
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def test_monthly_report_out_of_range_month_returns_400(admin_c):
    assert admin_c.get("/api/admin/reports/monthly?month=2026-13").status_code == 400
    assert admin_c.get("/api/admin/reports/monthly?month=2026-00").status_code == 400


def test_absences_calendar_out_of_range_month_returns_400(admin_c):
    assert admin_c.get("/api/absences/calendar?month=2026-13").status_code == 400
