"""Spec 15.2: Berichtstext der Vertragsänderungen — Blöcke nur, wenn sie sich
geändert haben; ohne Blockänderung byte-identisch zu 1.19.3."""
from datetime import date

from app.schemas.reports import WeeklyHoursChangeInPeriod
from app.services import calculation_service as cs
from app.services.export_service import format_weekly_hours_history
from tests.wh_change_helpers import add_row, with_pauses
from tests.work_blocks_fixtures import K_BLOCKS, block_week, legacy_week

YEAR = (date(2026, 1, 1), date(2026, 12, 31))
B = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "13:00")]), mon=30)


def _segments(db, user):
    return cs.weekly_hours_segments(db, user, *YEAR)


def test_new_blocks_long_and_compact(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), week=K_BLOCKS)
    add_row(db, test_user, date(2026, 9, 1), week=B)
    segs = _segments(db, test_user)
    assert format_weekly_hours_history(segs) == (
        "ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche")
    assert format_weekly_hours_history(segs, compact=True) == (
        "ab 01.09.2026: Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00 = 11,5 h/Woche")


def test_removing_blocks_appends_the_note(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), week=B)
    add_row(db, test_user, date(2026, 10, 1), day_hours=(6.5, 5, 0, 0, 0))
    assert format_weekly_hours_history(_segments(db, test_user)) == (
        "ab 01.10.2026: Mo 6,5 / Di 5,0 = 11,5 h/Woche · ohne Arbeitszeit-Blöcke")


def test_legacy_window_names_the_window(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=40, blocks=legacy_week(mon=("07:30", "16:30")))
    assert format_weekly_hours_history(_segments(db, test_user)) == (
        "ab 01.09.2026: 40,0 Std/Woche · Mo 07:30–16:30 (nur Kappung)")


def test_pause_change_only_is_a_block_change(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), week=B)
    add_row(db, test_user, date(2026, 9, 1), week=with_pauses(B, mon=60))
    assert format_weekly_hours_history(_segments(db, test_user)) == (
        "ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 60 Min) / Di 08:00–13:00 = 11,0 h/Woche")


def test_without_block_change_the_text_is_byte_identical(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
    assert format_weekly_hours_history(_segments(db, test_user)) == "ab 01.09.2026: 30,0 Std/Woche"


def test_same_legacy_window_in_every_row_creates_no_segment(db, test_user):
    """E20/E22: alle Verlaufszeilen tragen nach 073 dasselbe Altfenster."""
    legacy = legacy_week(mon=("07:30", "16:30"))
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, blocks=legacy)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=40, blocks=legacy)
    assert len(_segments(db, test_user)) == 1


def test_api_carries_blocks_and_the_flag(db, test_user):
    add_row(db, test_user, date(2026, 1, 1), week=K_BLOCKS)
    add_row(db, test_user, date(2026, 9, 1), week=B)
    first, second = _segments(db, test_user)
    out = WeeklyHoursChangeInPeriod.from_segment(second, previous=first)
    assert (out.blocks, out.blocks_changed) == (B, True)
    assert WeeklyHoursChangeInPeriod.from_segment(first).blocks_changed is False


def test_unchanged_legacy_window_keeps_the_frozen_wording(db, test_user):
    """E20: nach 073 trägt jede Verlaufszeile dasselbe Altfenster — eine reine
    Wochenstunden-Änderung bleibt wortgleich zu 1.19.3 (kein Fenster-Zusatz)."""
    legacy = legacy_week(mon=("07:30", "16:30"))
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, blocks=legacy)
    add_row(db, test_user, date(2026, 9, 1), weekly_hours=30, blocks=legacy)
    segs = _segments(db, test_user)
    assert format_weekly_hours_history(segs) == "ab 01.09.2026: 30,0 Std/Woche"
    assert format_weekly_hours_history(segs, compact=True) == "ab 01.09.2026: 30,0 Std/Woche"
    assert WeeklyHoursChangeInPeriod.from_segment(segs[1], previous=segs[0]).blocks_changed is False
