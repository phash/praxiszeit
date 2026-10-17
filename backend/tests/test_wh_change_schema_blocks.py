"""Spec 11.2/11.5/3.4: Schreibschema mit Blöcken, Schutzpaket-Felder, Fehlertexte."""
from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.admin_users import _block_root_error, _nested_block_label, _schedule_input_error
from app.schemas.working_hours_change import (
    BLOCKS_WITH_HOURS_DETAIL, WorkingHoursChangeCreate, WorkingHoursChangeDelete,
    WorkingHoursChangePreview, WorkingHoursChangeResponse,
)
from tests.work_blocks_fixtures import K_BLOCKS, block_week

EFF = "2026-09-01"


def _error(body):
    with pytest.raises(ValidationError) as exc:
        WorkingHoursChangeCreate.model_validate(body)
    return _schedule_input_error(exc.value)


def test_blocks_derive_the_snapshot():
    c = WorkingHoursChangeCreate.model_validate({"effective_from": EFF, "blocks": K_BLOCKS})
    assert c.use_daily_schedule is True
    assert (c.hours_monday, c.hours_tuesday, c.weekly_hours, c.work_days_per_week) == (7.0, 0.0, 7.0, 1)
    assert c.blocks_json() == K_BLOCKS


def test_blocks_round_the_day_target_like_derive_targets():
    """Review Focus 5: 07:30–12:00 + 13:00–16:25 = 7:55 h → gespeichert 7,92."""
    week = block_week(tue=[("07:30", "12:00"), ("13:00", "16:25")])
    c = WorkingHoursChangeCreate.model_validate({"effective_from": EFF, "blocks": week})
    assert (c.hours_monday, c.hours_tuesday, c.weekly_hours) == (0.0, 7.92, 7.92)


def test_blocks_override_a_client_mode_and_work_days():
    c = WorkingHoursChangeCreate.model_validate(
        {"effective_from": EFF, "blocks": K_BLOCKS, "use_daily_schedule": False, "work_days_per_week": 5})
    assert (c.use_daily_schedule, c.work_days_per_week) == (True, 1)


def test_without_blocks_the_mode_rules_stay_unchanged():
    c = WorkingHoursChangeCreate.model_validate({"effective_from": EFF, "weekly_hours": 30})
    assert (c.blocks, c.blocks_json(), c.use_daily_schedule, c.weekly_hours) == (None, None, False, 30)
    assert _error({"effective_from": EFF}) == "Wochenstunden sind im gleichmäßigen Modus Pflicht."


@pytest.mark.parametrize("extra", [{"weekly_hours": 7.0}, {"hours_monday": 7.0}, {"weekly_hours": None}])
def test_blocks_with_hours_are_rejected(extra):
    assert _error({"effective_from": EFF, "blocks": K_BLOCKS, **extra}) == BLOCKS_WITH_HOURS_DETAIL


def test_block_rule_message_reaches_the_dialog():
    body = {"effective_from": EFF, "blocks": block_week(mon=[("08:07", "12:00")])}
    assert _error(body) == "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."


def test_unfinished_editor_input_gets_the_rule_text():
    """Review Focus 1: leeres ``<input type="time">`` und leere Pause."""
    week = block_week(mon=[("08:00", "12:00")])
    week[0]["blocks"][0]["end"] = ""
    assert _error({"effective_from": EFF, "blocks": week}) == "Mo, Block 1: Uhrzeit im Format HH:MM angeben."
    week = block_week(mon=[("08:00", "12:00")])
    week[0]["pause_minutes"] = None
    assert _error({"effective_from": EFF, "blocks": week}) == "Mo: Pause angeben (0, wenn keine)."


def test_nested_type_errors_get_a_label():
    week = block_week(mon=[("08:00", "12:00")])
    week[0]["blocks"][0]["start"] = 8
    assert _error({"effective_from": EFF, "blocks": week}) == "Mo, Block 1, Beginn: ungültiger Wert."
    week = block_week(mon=[("08:00", "12:00")])
    week[0]["blocks"] = 5
    assert _error({"effective_from": EFF, "blocks": week}) == "Mo: ungültiger Wert."
    assert _error({"effective_from": EFF, "blocks": [1, 2, 3, 4, 5]}) == "Mo: ungültiger Wert."


WEEK_SHAPE = "Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet."


def _six_days_sixth_broken():
    """Sechs Tage, der sechste mit einem Typfehler (``start: 1``) — Pydantic meldet
    ihn an ``("blocks", 5, "blocks", 0, "start")``, BEVOR ``validate_week_blocks``
    die Länge prüfen kann."""
    week = block_week(mon=[("08:00", "12:00")])
    week.append({"blocks": [{"start": 1, "end": "12:00"}], "pause_minutes": 0})
    return week


@pytest.mark.parametrize("blocks", ["Mo 8-12", {"mo": []}, _six_days_sixth_broken()],
                         ids=["text", "objekt", "sechster-tag-typfehler"])
def test_wrong_week_shape_gets_the_five_days_text(blocks):
    """Review Task 4: eine falsche Form an der Wurzel (keine Liste, Typfehler ab dem
    sechsten Tag) fängt Pydantic vor ``validate_week_blocks`` ab — ohne eigenen Zweig
    gab die Vorschau „Ungültige Eingabe." statt des 3.4-Texts der Regel „genau 5
    Einträge", den dieselbe Regel bei ``[]`` oder sechs gültigen Tagen schon liefert."""
    assert _error({"effective_from": EFF, "blocks": blocks}) == WEEK_SHAPE
    assert _error({"effective_from": EFF, "blocks": []}) == WEEK_SHAPE


@pytest.mark.parametrize("loc, expected", [
    (("blocks",), WEEK_SHAPE),
    (("work_blocks",), WEEK_SHAPE),
    (("blocks", 5, "blocks", 0, "start"), WEEK_SHAPE),
    (("work_blocks", 7), WEEK_SHAPE),
    (("blocks", -1), WEEK_SHAPE),
    # Mo–Fr gehören dem Tageslabel (``_nested_block_label``), nicht der Wurzel.
    (("blocks", 0, "blocks", 0, "start"), None),
    (("work_blocks", 4), None),
    (("blocks", "x"), None),
    (("weekly_hours",), None),
    ((), None),
])
def test_block_root_error(loc, expected):
    assert _block_root_error(loc) == expected


@pytest.mark.parametrize("pause", ["x", "30", 30.0, True])
def test_pause_must_be_a_real_integer(pause):
    """Spec 3.4: ganzzahlig — kein bool, keine Zeichenkette, keine Kommazahl. Pydantic
    wandelte ``"30"``/``30.0``/``True`` sonst still in ``int`` um; die Regel und ihr
    Wortlaut leben allein in ``validate_week_blocks``."""
    week = block_week(tue=[("08:00", "12:00")])
    week[1]["pause_minutes"] = pause
    assert _error({"effective_from": EFF, "blocks": week}) == "Di: Pause in Minuten im 5-Minuten-Raster angeben."


@pytest.mark.parametrize("loc, expected", [
    (("blocks", 0, "blocks", 1, "start"), "Mo, Block 2, Beginn"),
    # Review Task 4, Fund 2: dieselben Labels unter der Wurzel von UserCreate.
    (("work_blocks", 0, "blocks", 1, "start"), "Mo, Block 2, Beginn"),
    (("work_blocks", 2, "pause_minutes"), "Mi, Pause"),
    (("work_blocks",), None),
    (("blocks", 4, "blocks", 0, "end"), "Fr, Block 1, Ende"),
    (("blocks", 1, "blocks", 0), "Di, Block 1"),
    (("blocks", 0, "blocks"), "Mo"),
    (("blocks", 2, "pause_minutes"), "Mi, Pause"),
    (("blocks", 3), "Do"),
    (("blocks", 7, "pause_minutes"), None),
    (("blocks", -1), None),
    (("blocks", "x"), None),
    (("blocks", 0, "irgendwas"), None),
    (("blocks",), None),
    (("weekly_hours",), None),
    ((), None),
])
def test_nested_label(loc, expected):
    assert _nested_block_label(loc) == expected


def test_field_limits_are_written_in_german_number_format():
    """Review Task 4: Pydantic liefert die Grenze eines ``float``-Felds als
    ``60.0`` — im deutschen Satz „höchstens 60.0" (Punkt, Nachkommastelle). Der
    Text erscheint als ``blocked_reason`` UND seit dem Fund als 422 beim Anlegen."""
    assert _error({"effective_from": EFF, "weekly_hours": 61}) == (
        "Die Wochenstunden dürfen höchstens 60 betragen.")
    assert _error({"effective_from": EFF, "use_daily_schedule": True, "hours_monday": 24.5}) == (
        "Die Stunden für Montag dürfen höchstens 24 betragen.")
    assert _error({"effective_from": EFF, "weekly_hours": -1}) == (
        "Die Wochenstunden dürfen nicht kleiner als 0 sein.")
    assert _error({"effective_from": EFF, "weekly_hours": 30, "work_days_per_week": 0}) == (
        "Die Arbeitstage pro Woche dürfen nicht kleiner als 1 sein.")


def test_reason_text_length_and_note_total():
    short = {"effective_from": EFF, "weekly_hours": 30, "retroactive_reason_type": "erfassungsfehler",
             "retroactive_reason_text": "123456789"}
    assert _error(short) == "Die Begründung muss mindestens 10 Zeichen lang sein."
    assert _error(dict(short, retroactive_reason_text="x" * 401)) == (
        "Die Begründung darf höchstens 400 Zeichen lang sein.")
    too_long = dict(short, retroactive_reason_text="x" * 400, note="n" * 80)
    assert _error(too_long) == "Notiz und Begründung zusammen höchstens 500 Zeichen."
    fits = dict(short, retroactive_reason_text="x" * 400, note="n" * 60)
    assert WorkingHoursChangeCreate.model_validate(fits).note == "n" * 60


def test_note_total_boundary_is_exactly_500():
    """Spec 9.5: „> 500 → 422" — genau 500 Zeichen gehen durch, 501 nicht.
    Präfix „[Erfassungsfehler korrigiert]" (29) + Leerzeichen + 400 Zeichen
    Begründung + „ · " (3) + Notiz: bei 67 Zeichen Notiz exakt 500."""
    from app.services.reclamp_audit import compose_change_note
    base = {"effective_from": EFF, "weekly_hours": 30, "retroactive_reason_type": "erfassungsfehler",
            "retroactive_reason_text": "x" * 400}
    assert len(compose_change_note("n" * 67, "erfassungsfehler", "x" * 400)) == 500
    assert WorkingHoursChangeCreate.model_validate(dict(base, note="n" * 67)).note == "n" * 67
    assert _error(dict(base, note="n" * 68)) == "Notiz und Begründung zusammen höchstens 500 Zeichen."


def test_note_without_reason_is_capped_at_500():
    """Review Task 3: ``working_hours_changes.note`` ist ``String(500)``. Ohne
    Begründung speichert der Schreibpfad die Notiz unverändert — 501 Zeichen
    liefen bisher durchs Schema und brachen erst auf PostgreSQL mit SQLSTATE
    22001 ab (HTTP 500; ``db_errors`` übersetzt nur 22P02). SQLite sieht die
    Spaltenlänge nicht, deshalb sitzt der Beleg am Schema."""
    from app.services.reclamp_audit import NOTE_ONLY_TOO_LONG_DETAIL
    base = {"effective_from": EFF, "weekly_hours": 30}
    assert WorkingHoursChangeCreate.model_validate(dict(base, note="n" * 500)).note == "n" * 500
    assert _error(dict(base, note="n" * 501)) == NOTE_ONLY_TOO_LONG_DETAIL
    assert NOTE_ONLY_TOO_LONG_DETAIL == "Die Notiz darf höchstens 500 Zeichen lang sein."
    # Grundtyp ohne Begründungstext: der Schreibpfad setzt keinen Präfix davor
    # (ohne Text gibt es kein Schutzpaket), gespeichert wird die Notiz allein.
    assert _error(dict(base, note="n" * 501, retroactive_reason_type="sonstiges")) == (
        NOTE_ONLY_TOO_LONG_DETAIL)


def test_padded_note_with_reason_is_measured_as_stored_without_reason():
    """Das Schema weiß nicht, ob die Änderung verkürzt: verkürzt sie nicht,
    speichert der Schreibpfad die Notiz OHNE Grund und UNGETRIMMT
    (``compose_change_note(note, None, …)``). Eine mit Leerzeichen aufgefüllte
    Notiz passt dann zusammengesetzt (getrimmt), roh aber nicht in die Spalte."""
    body = {"effective_from": EFF, "weekly_hours": 30, "retroactive_reason_type": "einvernehmlich",
            "retroactive_reason_text": "Montags bis 19 Uhr vereinbart", "note": "Teilzeit" + " " * 493}
    from app.services.reclamp_audit import NOTE_ONLY_TOO_LONG_DETAIL
    assert _error(body) == NOTE_ONLY_TOO_LONG_DETAIL


def test_reason_text_of_the_wrong_type_gets_a_singular_sentence():
    """Review Task 3: „Die Begründung" ist das einzige Label im Singular — der
    Plural-Ausweichtext („… sind kein gültiger Wert.") passt dort nicht. Ab der
    POST-Vorschau mit untypisiertem Body ist der Fall über echte Endpunkte
    erreichbar."""
    body = {"effective_from": EFF, "weekly_hours": 30, "retroactive_reason_type": "erfassungsfehler",
            "retroactive_reason_text": 12345678901}
    assert _error(body) == "Die Begründung muss ein Text sein."
    with pytest.raises(ValidationError) as exc:
        WorkingHoursChangeDelete.model_validate({"retroactive_reason_text": ["Liste"]})
    assert _schedule_input_error(exc.value) == "Die Begründung muss ein Text sein."


def test_reason_text_counts_without_surrounding_whitespace():
    """P15: „mindestens 10 Zeichen" meint Text, nicht Leerzeichen — gespeichert wird
    die Begründung ohnehin getrimmt (``compose_change_note``)."""
    body = {"effective_from": EFF, "weekly_hours": 30, "retroactive_reason_type": "einvernehmlich",
            "retroactive_reason_text": "      kurz      "}
    assert _error(body) == "Die Begründung muss mindestens 10 Zeichen lang sein."
    ok = WorkingHoursChangeCreate.model_validate(dict(body, retroactive_reason_text="  Montags bis 19 Uhr  "))
    assert ok.retroactive_reason_text == "Montags bis 19 Uhr"
    with pytest.raises(ValidationError):
        WorkingHoursChangeDelete.model_validate({"retroactive_reason_text": "  " + "x" * 9 + "  "})


def test_unknown_reason_type_is_rejected():
    with pytest.raises(ValidationError):
        WorkingHoursChangeCreate.model_validate(
            {"effective_from": EFF, "weekly_hours": 30, "retroactive_reason_type": "irgendwas"})


def test_protection_fields_are_accepted_together_with_blocks():
    c = WorkingHoursChangeCreate.model_validate({
        "effective_from": EFF, "blocks": K_BLOCKS, "retroactive_reason_type": "sonstiges",
        "retroactive_reason_text": "Vertrag rückwirkend angepasst", "wage_risk_confirmed": True,
        "other_reason_risk_confirmed": True,
    })
    assert (c.retroactive_reason_type, c.wage_risk_confirmed, c.other_reason_risk_confirmed) == (
        "sonstiges", True, True)


def test_reset_and_legacy_flags():
    cid = uuid4()
    c = WorkingHoursChangeCreate.model_validate(
        {"effective_from": EFF, "weekly_hours": 30, "reset_of_change_id": str(cid), "remove_legacy_window": True})
    assert (c.reset_of_change_id, c.remove_legacy_window, c.blocks) == (cid, True, None)


def test_delete_body_defaults():
    d = WorkingHoursChangeDelete()
    assert (d.retroactive_reason_type, d.retroactive_reason_text, d.wage_risk_confirmed,
            d.other_reason_risk_confirmed) == (None, None, False, False)
    with pytest.raises(ValidationError):
        WorkingHoursChangeDelete.model_validate({"retroactive_reason_text": "zu kurz"})


def test_response_counts_default_to_zero():
    fields = WorkingHoursChangeResponse.model_fields
    assert (fields["adjusted_time_entries"].default, fields["skipped_time_entries"].default) == (0, 0)


def test_preview_new_fields_have_defaults():
    p = WorkingHoursChangePreview(
        is_retroactive=False, period_start=date(2026, 9, 1), period_end=date(2026, 9, 1),
        current_daily_target=8, new_daily_target=8, day_targets_current=[8] * 5, day_targets_new=[8] * 5,
        overtime_before=0, overtime_after=0, vacation_days_before=0, vacation_days_after=0, affected_absences=0,
    )
    assert (p.is_shortening, p.shortening_reasons, p.earliest_lossless_date, p.reset_body) == (False, [], None, None)
    assert p.arbzg_findings.weeks_over_48_presence == 0
    assert p.time_entry_changes == [] and p.not_extendable_entries == []
    assert (p.grace_minutes, p.affected_time_entries, p.stale_entries_closed, p.saldo_delta_hours) == (0, 0, 0, 0.0)
    assert (p.blocks_current, p.blocks_new, p.milog_warning, p.block_break_notices) == (None, None, [], [])
