"""Spec 3.4: strenge Prüfung der Blöcke — nur in Schreibschemas."""
import pytest

from app.schemas.validators import validate_week_blocks
from tests.work_blocks_fixtures import K_BLOCKS, block_week

ADJACENT = "Mo: Block 2 muss nach dem Ende von Block 1 beginnen; aneinandergrenzende Blöcke bitte als einen Block erfassen."


def _days(*days):
    return list(days)


EMPTY = {"blocks": [], "pause_minutes": 0}
MON_8_12 = {"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": 0}

# Genau 60:00 h Blockzeit, aber die je Tag auf 0,01 gerundeten Tagessolls
# (Spec 4.1) ergeben 11,42 + 11,42 + 12,17 + 12,50 + 12,50 = 60,01 h — das ist
# der Wert, den ``derive_targets`` speichern würde und den ``le=60`` danach
# mit einem anderen Text ablehnte. Die 60-h-Regel aus 3.4 gilt der Σ Tagessoll.
ROUNDED_OVER_60 = block_week(
    mon=[("00:00", "11:25")], tue=[("00:00", "11:25")], wed=[("00:00", "12:10")],
    thu=[("00:00", "12:30")], fri=[("00:00", "12:30")],
)


@pytest.mark.parametrize("week, message", [
    (block_week()[:4], "Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet."),
    ("kaputt", "Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet."),
    (block_week(mon=[("06:00", "07:00"), ("08:00", "09:00"), ("10:00", "11:00"), ("12:00", "13:00")]),
     "Mo: höchstens drei Blöcke je Tag."),
    (block_week(mon=[("8:00", "12:00")]), "Mo, Block 1: Uhrzeit im Format HH:MM angeben."),
    (block_week(mon=[("", "12:00")]), "Mo, Block 1: Uhrzeit im Format HH:MM angeben."),
    (block_week(mon=[("08:07", "12:00")]), "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."),
    (block_week(mon=[("08:00", "23:59")]), "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."),
    (block_week(tue=[("08:00", "12:00"), ("13:00", "12:30")]), "Di, Block 2: Beginn muss vor dem Ende liegen."),
    (block_week(mon=[("08:00", "12:00"), ("12:00", "13:00")]), ADJACENT),
    (block_week(mon=[("13:00", "14:00"), ("08:00", "12:00")]), ADJACENT),
    (block_week(mon=[("08:00", "12:00"), ("11:00", "14:00")]), ADJACENT),
    (block_week(pause=240, mon=[("08:00", "12:00")]), "Mo: Pause muss kürzer sein als die Gesamtzeit der Blöcke."),
    (_days(MON_8_12, EMPTY, {"blocks": [], "pause_minutes": 15}, EMPTY, EMPTY), "Mi: Pause nur an Tagen mit Blöcken."),
    (_days({"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": None}, EMPTY, EMPTY, EMPTY, EMPTY),
     "Mo: Pause angeben (0, wenn keine)."),
    (block_week(pause=7, mon=[("08:00", "12:00")]), "Mo: Pause in Minuten im 5-Minuten-Raster angeben."),
    (block_week(pause=-5, mon=[("08:00", "12:00")]), "Mo: Pause in Minuten im 5-Minuten-Raster angeben."),
    # Spec 3.4 „ganzzahlig": keine Zeichenkette, keine Kommazahl, kein bool (Review Task 1)
    (block_week(pause="30", mon=[("08:00", "12:00")]), "Mo: Pause in Minuten im 5-Minuten-Raster angeben."),
    (block_week(pause=30.0, mon=[("08:00", "12:00")]), "Mo: Pause in Minuten im 5-Minuten-Raster angeben."),
    (block_week(pause=True, mon=[("08:00", "12:00")]), "Mo: Pause in Minuten im 5-Minuten-Raster angeben."),
    (block_week(), "Mindestens ein Wochentag braucht einen Block."),
    (block_week(mon=[("00:00", "12:05")], tue=[("00:00", "12:05")], wed=[("00:00", "12:05")],
                thu=[("00:00", "12:05")], fri=[("00:00", "12:05")]),
     "Die Wochensumme darf 60 Stunden nicht überschreiten."),
    (ROUNDED_OVER_60, "Die Wochensumme darf 60 Stunden nicht überschreiten."),
])
def test_each_rule_has_its_german_message(week, message):
    with pytest.raises(ValueError) as exc:
        validate_week_blocks(week)
    assert str(exc.value) == message


@pytest.mark.parametrize("week", [
    block_week(mon=[("06:00", "07:00"), ("08:00", "09:00"), ("10:00", "11:00")]),   # genau 3 Blöcke
    block_week(mon=[("08:05", "12:00")]),                                            # Raster 08:05
    block_week(pause=235, mon=[("08:00", "12:00")]),                                 # Pause = Σ − 5
    block_week(mon=[("00:00", "12:00")], tue=[("00:00", "12:00")], wed=[("00:00", "12:00")],
               thu=[("00:00", "12:00")], fri=[("00:00", "12:00")]),                  # genau 60 h
    block_week(mon=[("08:00", "23:55")]),                                            # größte Endzeit
])
def test_boundaries_are_valid(week):
    assert validate_week_blocks(week) == week


def test_week_limit_checks_the_stored_rounded_sum():
    """Die Grenze prüft denselben Wert, der gespeichert wird: Blockzeit genau
    60:00 h, gerundete Σ 60,01 h → abgelehnt; genau 60,00 h → gültig."""
    from decimal import Decimal

    from app.services.work_blocks_service import derive_targets

    assert derive_targets(ROUNDED_OVER_60)["weekly_hours"] == Decimal("60.01")
    exact = block_week(mon=[("00:00", "12:00")], tue=[("00:00", "12:00")], wed=[("00:00", "12:00")],
                       thu=[("00:00", "12:00")], fri=[("00:00", "12:00")])
    assert derive_targets(validate_week_blocks(exact))["weekly_hours"] == Decimal("60.00")


def test_returns_the_canonical_week_and_accepts_models():
    from pydantic import BaseModel

    class _Day(BaseModel):
        blocks: list
        pause_minutes: int | None

    assert validate_week_blocks(K_BLOCKS) == K_BLOCKS
    assert validate_week_blocks([_Day(**d) for d in K_BLOCKS]) == K_BLOCKS


@pytest.mark.parametrize("blocks", [5, {"start": "08:00", "end": "12:00"}, "08:00-12:00"])
def test_blocks_that_are_not_a_list_raise_value_error_not_type_error(blocks):
    """Ein ``TypeError`` im Validator wäre in Pydantic ein 500 statt einer Meldung."""
    week = _days({"blocks": blocks, "pause_minutes": 0}, EMPTY, EMPTY, EMPTY, EMPTY)
    with pytest.raises(ValueError) as exc:
        validate_week_blocks(week)
    assert str(exc.value) == "Mo: Tag nicht in der Form {blocks, pause_minutes}."
