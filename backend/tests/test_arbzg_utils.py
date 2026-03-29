"""Tests for ArbZG utility functions (§2 Abs. 4 / §6 ArbZG)."""
import pytest
from datetime import time
from app.services.arbzg_utils import is_night_work, NIGHT_THRESHOLD_MINUTES


class TestIsNightWork:
    """Test is_night_work() which checks if >2h of night time (23:00–06:00) overlap."""

    def test_full_night_shift_22_to_06(self):
        """22:00-06:00 spans 7h of night time (23:00-06:00) → night work."""
        assert is_night_work(time(22, 0), time(6, 0)) is True

    def test_night_shift_23_to_05(self):
        """23:00-05:00 spans 5h of night time → night work."""
        assert is_night_work(time(23, 0), time(5, 0)) is True

    def test_regular_day_shift_08_to_17(self):
        """08:00-17:00 has 0h night time → NOT night work."""
        assert is_night_work(time(8, 0), time(17, 0)) is False

    def test_boundary_2259_to_2301(self):
        """22:59-23:01 has only 1 minute in night time (23:00-23:01) → NOT night work.
        ArbZG §2 Abs. 4 requires >2h (120 min) in 23:00-06:00."""
        assert is_night_work(time(22, 59), time(23, 1)) is False

    def test_boundary_0559_to_0800(self):
        """05:59-08:00 has only 1 minute in night time (05:59-06:00) → NOT night work."""
        assert is_night_work(time(5, 59), time(8, 0)) is False

    def test_spanning_midnight_20_to_02(self):
        """20:00-02:00 spans 3h night time (23:00-02:00) → night work."""
        assert is_night_work(time(20, 0), time(2, 0)) is True

    def test_none_start_time(self):
        """None start_time → gracefully returns False."""
        assert is_night_work(None, time(6, 0)) is False

    def test_none_end_time(self):
        """None end_time → gracefully returns False."""
        assert is_night_work(time(22, 0), None) is False

    def test_both_none(self):
        """Both times None → gracefully returns False."""
        assert is_night_work(None, None) is False

    def test_exactly_2h_night_not_exceeded(self):
        """23:00-01:00 = exactly 2h night time. Threshold is >2h, so False."""
        assert is_night_work(time(23, 0), time(1, 0)) is False

    def test_just_over_2h_night(self):
        """23:00-01:01 = 2h1min night time. >2h → True."""
        assert is_night_work(time(23, 0), time(1, 1)) is True

    def test_early_morning_shift_04_to_08(self):
        """04:00-08:00 has 2h night time (04:00-06:00). Not >2h → False."""
        assert is_night_work(time(4, 0), time(8, 0)) is False

    def test_early_morning_03_to_08(self):
        """03:00-08:00 has 3h night time (03:00-06:00) → night work."""
        assert is_night_work(time(3, 0), time(8, 0)) is True

    def test_late_evening_shift_21_to_2330(self):
        """21:00-23:30 has only 30min night time (23:00-23:30) → NOT night work."""
        assert is_night_work(time(21, 0), time(23, 30)) is False

    def test_night_threshold_constant(self):
        """NIGHT_THRESHOLD_MINUTES should be 120 (2 hours) per ArbZG §2 Abs. 4."""
        assert NIGHT_THRESHOLD_MINUTES == 120
