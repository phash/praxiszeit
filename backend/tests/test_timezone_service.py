"""Tests for timezone service (Europe/Berlin)."""
import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from app.services.timezone_service import today_local, now_local, LOCAL_TZ


class TestTodayLocal:
    """Test today_local() function."""

    def test_returns_date_object(self):
        """today_local() must return a date instance."""
        result = today_local()
        assert isinstance(result, date)

    def test_returns_date_not_datetime(self):
        """today_local() must return a pure date, not a datetime."""
        result = today_local()
        # datetime is a subclass of date, so check explicitly
        assert type(result) is date

    def test_reasonable_date(self):
        """Returned date should be today or very close (no timezone confusion)."""
        result = today_local()
        utc_today = datetime.now(ZoneInfo("UTC")).date()
        # Can differ by at most 1 day due to timezone offset
        diff = abs((result - utc_today).days)
        assert diff <= 1


class TestNowLocal:
    """Test now_local() function."""

    def test_returns_datetime_object(self):
        """now_local() must return a datetime instance."""
        result = now_local()
        assert isinstance(result, datetime)

    def test_timezone_aware(self):
        """now_local() must return a timezone-aware datetime."""
        result = now_local()
        assert result.tzinfo is not None

    def test_europe_berlin_timezone(self):
        """now_local() must return datetime in Europe/Berlin timezone."""
        result = now_local()
        # The timezone key should be Europe/Berlin
        assert str(result.tzinfo) == "Europe/Berlin"

    def test_consistent_with_today_local(self):
        """now_local().date() should equal today_local()."""
        # These calls happen within the same second, should match
        now = now_local()
        today = today_local()
        assert now.date() == today


class TestLocalTzConstant:
    """Test LOCAL_TZ constant."""

    def test_local_tz_is_europe_berlin(self):
        """LOCAL_TZ must be Europe/Berlin."""
        assert str(LOCAL_TZ) == "Europe/Berlin"

    def test_local_tz_is_zoneinfo(self):
        """LOCAL_TZ must be a ZoneInfo instance."""
        assert isinstance(LOCAL_TZ, ZoneInfo)
