"""Spec 2026-10-08, Abschnitt 3: JSON-Form der Arbeitszeit-Blöcke."""
import pytest

from app.services import work_blocks_service as wbs
from tests.work_blocks_fixtures import K_BLOCKS, block_week, legacy_week

CANONICAL = [
    {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], "pause_minutes": 30},
    {"blocks": [{"start": "08:00", "end": "13:00"}], "pause_minutes": 0},
    {"blocks": [], "pause_minutes": 0},
    {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], "pause_minutes": 30},
    {"blocks": [], "pause_minutes": 0},
]


def test_parse_canonical_example():
    parsed = wbs.parse_week_blocks(CANONICAL)
    assert parsed.blocks[0] == ((480, 720), (900, 1080))
    assert parsed.blocks[2] == ()
    assert parsed.pauses == (30, 0, 0, 30, 0)
    assert wbs.is_legacy_week(parsed) is False


def test_parse_legacy_row_with_placeholders_and_odd_minutes():
    week = legacy_week(mon=("07:37", "16:30"), fri=("07:30", None), tue=(None, "16:00"))
    parsed = wbs.parse_week_blocks(week)
    assert parsed.blocks[0] == ((457, 990),)
    assert parsed.blocks[1] == ((0, 960),)
    assert parsed.blocks[4] == ((450, 1439),)
    assert parsed.pauses == (None,) * 5
    assert wbs.is_legacy_week(parsed) is True


@pytest.mark.parametrize("raw", [None, block_week(), legacy_week()])
def test_none_and_five_empty_days_are_the_same(raw):
    assert wbs.parse_week_blocks(raw) is None


def test_round_trip_keeps_canonical_form():
    for raw in (CANONICAL, legacy_week(mon=("07:30", None)), K_BLOCKS):
        parsed = wbs.parse_week_blocks(raw)
        assert wbs.week_blocks_to_json(parsed.blocks, parsed.pauses) == raw


def test_unsorted_blocks_are_sorted():
    raw = block_week(mon=[("15:00", "18:00"), ("08:00", "12:00")])
    assert wbs.parse_week_blocks(raw).blocks[0] == ((480, 720), (900, 1080))


def test_week_blocks_to_json_none():
    assert wbs.week_blocks_to_json(None, None) is None


@pytest.mark.parametrize("raw", [
    CANONICAL[:4],                                                      # vier Tage
    block_week(mon=[("7:30", "12:00")]),                                # kein HH:MM
    # Stunde 24 am ENDE: Beginn liegt davor, nur die Stundengrenze greift
    # (``("24:00", "23:00")`` scheiterte schon an Beginn >= Ende).
    block_week(mon=[("08:00", "24:00")]),                               # Stunde 24
    block_week(mon=[("08:00", "09:60")]),                               # Minute 60
    block_week(mon=[("12:00", "08:00")]),                               # Beginn >= Ende
    block_week(mon=[("08:00", "12:00"), ("11:00", "14:00")]),           # Überlappung
    [{"blocks": "x", "pause_minutes": 0}] * 5,                          # kein Block-Array
    [{"blocks": [{"start": "08:00"}], "pause_minutes": 0}] + block_week()[1:],  # Block ohne end
    [{"blocks": [], "pause_minutes": -5}] + block_week()[1:],           # negative Pause
    # bool ist in Python ein int — ``True`` darf nicht als Pause 1 durchgehen.
    # Tag MIT Block, damit die Woche nicht leer ist und die Prüfung unabhängig
    # davon greift, wann „fünf leere Tage ≡ None" entschieden wird.
    [{"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": True}] + block_week()[1:],
])
def test_structural_errors_raise(raw):
    with pytest.raises(ValueError):
        wbs.parse_week_blocks(raw)


def test_minutes_helpers():
    assert wbs.hhmm_to_minutes("07:37") == 457
    assert wbs.minutes_to_hhmm(1439) == "23:59"
    with pytest.raises(ValueError):
        wbs.hhmm_to_minutes("7:37")
