"""Tests for ArbZG utility functions (§2 Abs. 4 / §6 ArbZG)."""
import pytest
from datetime import time
from app.services.arbzg_utils import is_night_work, NIGHT_THRESHOLD_MINUTES


class TestIsNightWork:
    """Test is_night_work() which checks if >2h of night time (23:00–06:00) overlap."""

    def test_full_night_shift_22_to_06(self):
        """§6 ArbZG: 22-06 Uhr hat 7h Nachtzeit (23-06) — klar Nachtarbeit."""
        assert is_night_work(time(22, 0), time(6, 0)) is True

    def test_night_shift_23_to_05(self):
        """§6 ArbZG: 23-05 Uhr liegt komplett in der Nachtzeit — 5h Überlappung."""
        assert is_night_work(time(23, 0), time(5, 0)) is True

    def test_regular_day_shift_08_to_17(self):
        """Prüft dass reguläre Tagschicht (08-17 Uhr) keine Nachtarbeit ist."""
        assert is_night_work(time(8, 0), time(17, 0)) is False

    def test_boundary_2259_to_2301(self):
        """§2 Abs. 4 ArbZG: Nur 1 Min in Nachtzeit (23:00-23:01) — weit unter 2h-Schwelle."""
        assert is_night_work(time(22, 59), time(23, 1)) is False

    def test_boundary_0559_to_0800(self):
        """§2 Abs. 4 ArbZG: Nur 1 Min in Nachtzeit (05:59-06:00) — Grenzfall am Morgen."""
        assert is_night_work(time(5, 59), time(8, 0)) is False

    def test_spanning_midnight_20_to_02(self):
        """§6 ArbZG: Mitternachtsübergreifend 20-02 Uhr hat 3h Nachtzeit — Nachtarbeit."""
        assert is_night_work(time(20, 0), time(2, 0)) is True

    def test_none_start_time(self):
        """Prüft dass None als Startzeit graceful False ergibt — offene Einträge absichern."""
        assert is_night_work(None, time(6, 0)) is False

    def test_none_end_time(self):
        """Prüft dass None als Endzeit graceful False ergibt — laufende Stempelung absichern."""
        assert is_night_work(time(22, 0), None) is False

    def test_both_none(self):
        """Prüft dass beide Zeiten None graceful False ergibt — doppelter Edge Case."""
        assert is_night_work(None, None) is False

    def test_exactly_2h_night_not_exceeded(self):
        """§2 Abs. 4 ArbZG: Exakt 2h Nachtzeit reicht nicht — Schwelle ist MEHR als 2h."""
        assert is_night_work(time(23, 0), time(1, 0)) is False

    def test_just_over_2h_night(self):
        """§2 Abs. 4 ArbZG: 2h01min Nachtzeit überschreitet die Schwelle — knappster Grenzfall."""
        assert is_night_work(time(23, 0), time(1, 1)) is True

    def test_early_morning_shift_04_to_08(self):
        """§2 Abs. 4 ArbZG: Frühschicht 04-08 Uhr hat exakt 2h Nachtzeit — keine Nachtarbeit."""
        assert is_night_work(time(4, 0), time(8, 0)) is False

    def test_early_morning_03_to_08(self):
        """§6 ArbZG: Frühschicht 03-08 Uhr hat 3h Nachtzeit (03-06) — Nachtarbeit."""
        assert is_night_work(time(3, 0), time(8, 0)) is True

    def test_late_evening_shift_21_to_2330(self):
        """§2 Abs. 4 ArbZG: Spätschicht 21-23:30 hat nur 30min Nachtzeit — keine Nachtarbeit."""
        assert is_night_work(time(21, 0), time(23, 30)) is False

    def test_night_threshold_constant(self):
        """Prüft dass die Nachtzeit-Schwelle 120 Min (2h) beträgt — §2 Abs. 4 ArbZG Vorgabe."""
        assert NIGHT_THRESHOLD_MINUTES == 120
