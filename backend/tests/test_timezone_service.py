"""Tests for timezone service (Europe/Berlin)."""
import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from app.services.timezone_service import today_local, now_local, LOCAL_TZ


class TestTodayLocal:
    """Test today_local() function."""

    def test_returns_date_object(self):
        """Prüft dass today_local() ein date-Objekt liefert — Basis für alle datumsbasierten Berechnungen."""
        result = today_local()
        assert isinstance(result, date)

    def test_returns_date_not_datetime(self):
        """Prüft dass today_local() ein reines date und kein datetime liefert — verhindert unerwartete Zeitvergleiche."""
        result = today_local()
        # datetime is a subclass of date, so check explicitly
        assert type(result) is date

    def test_reasonable_date(self):
        """Prüft dass das Datum maximal 1 Tag von UTC abweicht — keine Zeitzonen-Verwechslung."""
        result = today_local()
        utc_today = datetime.now(ZoneInfo("UTC")).date()
        # Can differ by at most 1 day due to timezone offset
        diff = abs((result - utc_today).days)
        assert diff <= 1


class TestNowLocal:
    """Test now_local() function."""

    def test_returns_datetime_object(self):
        """Prüft dass now_local() ein datetime-Objekt liefert — für Stempel-Zeitstempel benötigt."""
        result = now_local()
        assert isinstance(result, datetime)

    def test_timezone_aware(self):
        """Prüft dass now_local() timezone-aware ist — naive datetimes führen zu falschen Ruhezeitberechnungen."""
        result = now_local()
        assert result.tzinfo is not None

    def test_europe_berlin_timezone(self):
        """Prüft dass now_local() Europe/Berlin verwendet — deutsche Arztpraxen arbeiten in CET/CEST."""
        result = now_local()
        # The timezone key should be Europe/Berlin
        assert str(result.tzinfo) == "Europe/Berlin"

    def test_consistent_with_today_local(self):
        """Prüft dass now_local().date() und today_local() konsistent sind — keine divergierenden Datumsquellen."""
        # These calls happen within the same second, should match
        now = now_local()
        today = today_local()
        assert now.date() == today


class TestLocalTzConstant:
    """Test LOCAL_TZ constant."""

    def test_local_tz_is_europe_berlin(self):
        """Prüft dass LOCAL_TZ auf Europe/Berlin gesetzt ist — Single Source of Truth für die Zeitzone."""
        assert str(LOCAL_TZ) == "Europe/Berlin"

    def test_local_tz_is_zoneinfo(self):
        """Prüft dass LOCAL_TZ eine ZoneInfo-Instanz ist — kein pytz, kein String."""
        assert isinstance(LOCAL_TZ, ZoneInfo)
