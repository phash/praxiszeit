"""Release-Review 1.19.1 — Funde 1-3: Rohstempel-Erhalt beim Re-Speichern + Kollaps-Text."""
from datetime import time

import pytest

from app.services import work_window_service


class TestUnclampInput:
    """Fund: das Formular schickt die GEKAPPTE Zeit zurueck; ohne Ruecksetzung
    rechnet clamp() sie als neue Eingabe und wirft den Rohstempel weg (§16)."""

    def test_returns_raw_when_incoming_equals_previous_effective(self):
        assert work_window_service.unclamp_input(
            time(7, 45), prev_eff=time(7, 45), prev_raw=time(7, 37)
        ) == time(7, 37)

    def test_returns_incoming_on_a_real_change(self):
        assert work_window_service.unclamp_input(
            time(9, 0), prev_eff=time(7, 45), prev_raw=time(7, 37)
        ) == time(9, 0)

    def test_passes_through_when_nothing_was_clamped_before(self):
        assert work_window_service.unclamp_input(
            time(8, 0), prev_eff=time(8, 0), prev_raw=None
        ) == time(8, 0)

    def test_passes_through_none(self):
        assert work_window_service.unclamp_input(
            None, prev_eff=time(7, 45), prev_raw=time(7, 37)
        ) is None


class TestClampWarningCollapse:
    """Fund: liegt ein Eintrag ganz ausserhalb des Fensters, kollabiert clamp()
    auf einen Punkt und gab (start, start, start, end) zurueck — der Text las
    sich dann als 'Beginn 05:00 -> 05:00' und verschwieg die eigentliche Folge."""

    def test_no_part_for_an_unchanged_side(self):
        text = work_window_service.clamp_warning_text(
            raw_start=time(5, 0), raw_end=time(6, 0),
            eff_start=time(5, 0), eff_end=time(5, 0),
            grace_minutes=15,
        )
        assert text is not None
        assert "05:00 → 05:00" not in text, text

    def test_names_the_zero_hours_consequence(self):
        text = work_window_service.clamp_warning_text(
            raw_start=time(5, 0), raw_end=time(6, 0),
            eff_start=time(5, 0), eff_end=time(5, 0),
            grace_minutes=15,
        )
        assert "0 Stunden" in text, text

    def test_normal_clamp_text_unchanged(self):
        text = work_window_service.clamp_warning_text(
            raw_start=time(7, 0), raw_end=None,
            eff_start=time(7, 45), eff_end=time(16, 0),
            grace_minutes=15,
        )
        assert "Beginn 07:00 → 07:45" in text
        assert "0 Stunden" not in text
        assert "Puffer 15 Minuten" in text
