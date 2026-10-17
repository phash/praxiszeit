"""Spec 2026-10-08, 7.1 Nr. 11/12, 7.3, 7.4, E38, E80, P3: XLS-Import und Blöcke."""
import uuid
from datetime import date, datetime, time

import pytest

from app.models import TimeEntry
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.services.xls_import_service import (
    CREDIT_OVERRIDE_IMPORT_NOTE, ImportedEntry, _calc_break_minutes, execute_import, parse_xls,
)
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week, legacy_week

HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]
LEGACY = legacy_week(mon=("08:00", "17:00"))


def _xls(*rows):
    return _make_xls_bytes([HEADER, *[_make_data_row(a, b) for a, b in rows]])


def _row(start, end, **kw):
    return ImportedEntry(date=MON, start_time=start, end_time=end, break_minutes=kw.pop("break_minutes", 0),
                         note=None, has_conflict=False, arbzg_warnings=[], **kw)


def _entry(db, user, start, end, **kw):
    e = TimeEntry(tenant_id=kw.pop("tenant_id", DEFAULT_TENANT_ID), user_id=user.id,
                  date=kw.pop("day", MON), start_time=start, end_time=end,
                  break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def _grace(db, minutes):
    db.add(SystemSetting(key="work_window_grace_minutes", value=str(minutes), tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def _run(db, user, admin, entries, overwrite=False):
    return execute_import(user.id, entries, overwrite=overwrite, db=db, changed_by_id=admin.id,
                          filename="t.xls", tenant_id=DEFAULT_TENANT_ID)


@pytest.mark.parametrize("start, end, segments, expected", [
    (time(8), time(18), [150], 0),        # K1: Lücke deckt §4 (heute 45 → Doppelabzug)
    (time(8), time(17, 30), [10], 45),    # Segment < 15 deckt nichts
    (time(8), time(17), [20], 15),        # Rest 10 Min → auf 15 aufgerundet (§4 Satz 2)
    (time(8), time(16, 1), [], 30),       # ohne Blöcke wie bisher
])
def test_auto_pause_rest(start, end, segments, expected):
    assert _calc_break_minutes(start, end, segments) == expected


def test_k1_preview_gap_note_without_raw_and_no_s3_s4_warning(db, test_user):
    """8.2: K1 als Import ergibt keine §3/§4-Warnung (angerechnet 7:30 h, Lücke
    deckt §4) — auch nicht in der Tagesaggregation mit einem DB-Eintrag direkt
    danach; der reine Lückenfall bekommt trotzdem den Kappungshinweis.

    Die harten Prüfungen der Vorschau melden „… Netto-Arbeitszeit …"; der weiche
    Anwesenheits-Hinweis (8.3, PR2) beginnt ebenfalls mit „§4 ArbZG:" und ist
    für K1 laut Spec gewollt — er rechnet auf den Stempeln, nicht auf der
    angerechneten Zeit."""
    test_user.work_blocks = K_BLOCKS
    db.commit()
    _entry(db, test_user, time(18), time(18, 30))
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 18, 0))), test_user.id, db)
    assert (row.start_time, row.end_time, row.raw_start_time, row.raw_end_time) == (time(8), time(18), None, None)
    assert (row.uncredited_minutes, row.break_minutes) == (150, 0)
    assert not [w for w in row.arbzg_warnings if "Netto-Arbeitszeit" in w], row.arbzg_warnings
    assert any(w.startswith("§4 ArbZG: Durchgehend über die Lücke") for w in row.arbzg_warnings)
    assert any(w.startswith("Zwischen den Arbeitsblöcken (12:15–14:45") for w in row.arbzg_warnings)


def test_confirm_ignores_client_uncredited_and_break(db, test_user, test_admin):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    _run(db, test_user, test_admin, [_row(time(8), time(18), break_minutes=45, uncredited_minutes=999)])
    e = db.query(TimeEntry).one()
    assert (e.uncredited_minutes, e.break_minutes, e.clamp_grace_minutes) == (150, 0, 15)


def test_confirm_schema_has_no_uncredited_input():
    """E11 / Spec 7.1 („``ImportedEntry``-Eingabe"): ``/confirm`` nimmt
    ``uncredited_minutes`` gar nicht erst an — das Feld gibt es nur in der
    Vorschau-Antwort. Ein mitgeschickter Wert fällt beim Einlesen weg."""
    from app.routers.import_xls import ConfirmRequest

    body = ConfirmRequest.model_validate({
        "user_id": str(uuid.uuid4()), "overwrite": False,
        "entries": [{"date": MON.isoformat(), "start_time": "08:00", "end_time": "18:00",
                     "break_minutes": 0, "note": None, "has_conflict": False,
                     "arbzg_warnings": [], "uncredited_minutes": 999}],
    })
    assert "uncredited_minutes" not in type(body.entries[0]).model_fields
    assert not hasattr(body.entries[0], "uncredited_minutes")
    assert "uncredited_minutes" in ImportedEntry.model_fields


def test_day_without_blocks_keeps_client_raw_on_new_entry(db, test_user, test_admin):
    _run(db, test_user, test_admin, [_row(time(7, 15), time(16), raw_start_time=time(6, 30))])
    e = db.query(TimeEntry).one()
    assert (e.start_time, e.raw_start_time, e.uncredited_minutes, e.clamp_grace_minutes) == (
        time(7, 15), time(6, 30), 0, None)


def test_track_hours_false_with_blocks_keeps_client_raw(db, test_user, test_admin):
    """E38/F27: clamp_applies prüft track_hours — sonst löschte die Kappung, die
    gar nicht stattfindet, einen mitgelieferten Rohstempel."""
    test_user.work_blocks = LEGACY
    test_user.track_hours = False
    db.commit()
    _run(db, test_user, test_admin, [_row(time(7, 15), time(16), raw_start_time=time(6, 30))])
    e = db.query(TimeEntry).one()
    assert (e.start_time, e.raw_start_time) == (time(7, 15), time(6, 30))


def test_foreign_tenant_rows_are_invisible(db, test_user, test_admin):
    """7.3/F-026: Konfliktsuche und Überschreiben nur im eigenen Mandanten."""
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd-xls")
    db.add(other)
    db.commit()
    foreign = _entry(db, test_user, time(8), time(12), tenant_id=other.id, note="fremd")
    # Fremde Zeilen dürfen auch §4-Tagessumme und §5-Vortag nicht speisen.
    _entry(db, test_user, time(20), time(23), tenant_id=other.id, day=date(2026, 5, 31))
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 13, 0))), test_user.id, db)
    assert row.has_conflict is False
    assert not [w for w in row.arbzg_warnings if w.startswith(("§4", "§5"))], row.arbzg_warnings
    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert (result.imported, result.overwritten) == (1, 0)
    db.refresh(foreign)
    assert (foreign.end_time, foreign.note) == (time(12), "fremd")


def test_preview_rejects_a_person_of_another_tenant(db, test_user):
    """F-026: der Router reicht den Mandanten der Verwaltung durch; eine Person
    eines anderen Mandanten gibt es für die Vorschau nicht."""
    with pytest.raises(ValueError, match="Benutzer nicht gefunden"):
        parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 13, 0))), test_user.id, db,
                  tenant_id=uuid.uuid4())


def test_rest_time_uses_the_raw_end(db, test_user):
    """7.3: §5 gegen den Rohstempel (raw_end or end) wie rest_time_service."""
    _entry(db, test_user, time(12), time(20), day=date(2026, 5, 31), raw_end_time=time(23, 0))
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 12, 0))), test_user.id, db)
    assert any(w.startswith("§5 ArbZG: Ruhezeit 9.0h") for w in row.arbzg_warnings), row.arbzg_warnings


def test_rest_time_uses_the_raw_start_of_a_clamped_row(db, test_user):
    """7.3: auch der BEGINN zählt für §5 als Rohstempel — die Datei sagt 06:00,
    angerechnet wird ab 07:45; die Ruhezeit seit 20:00 beträgt 10 h, nicht 11:45 h."""
    test_user.work_blocks = LEGACY
    db.commit()
    _entry(db, test_user, time(12), time(20), day=date(2026, 5, 31))
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 6, 0), _dt(2026, 6, 1, 12, 0))), test_user.id, db)
    assert (row.start_time, row.raw_start_time) == (time(7, 45), time(6, 0))
    assert any(w.startswith("§5 ArbZG: Ruhezeit 10.0h") for w in row.arbzg_warnings), row.arbzg_warnings


def test_overwriting_an_acknowledged_entry_keeps_the_flag_and_warns(db, test_user, test_admin):
    test_user.work_blocks = LEGACY
    db.commit()
    e = _entry(db, test_user, time(8), time(17), credit_override=True)
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 18, 30))), test_user.id, db)
    assert row.has_conflict is True
    assert (row.end_time, row.raw_end_time) == (time(18, 30), None)
    assert CREDIT_OVERRIDE_IMPORT_NOTE in row.arbzg_warnings
    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert result.overwritten == 1
    db.refresh(e)
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes, e.credit_override) == (time(18, 30), None, 0, True)


# Review Focus 3: Re-Import desselben Tages nach einer Puffer-Senkung.
def test_reimport_after_grace_reduction_finds_the_entry_and_keeps_its_grace(db, test_user, test_admin):
    test_user.work_blocks = LEGACY
    db.commit()
    e = _entry(db, test_user, time(7, 45), time(16), raw_start_time=time(7, 0), clamp_grace_minutes=15)
    _grace(db, 10)
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 7, 0), _dt(2026, 6, 1, 16, 0))), test_user.id, db)
    assert (row.has_conflict, row.start_time, row.raw_start_time) == (True, time(7, 45), time(7, 0))
    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert (result.imported, result.overwritten) == (0, 1)
    assert db.query(TimeEntry).count() == 1
    db.refresh(e)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes, e.auto_closed) == (time(7, 45), time(7, 0), 15, False)


def test_overwrite_k1_sets_uncredited_grace_and_clears_auto_closed(db, test_user, test_admin):
    """7.1 Nr. 12 / 17.3 / P18: der Überschreib-Zweig schreibt ``uncredited``,
    den angewandten Puffer (vorher NULL) und ``auto_closed = false`` — die
    Datei liefert ein echtes Ende. Die Auto-Pause rechnet die Lücke ein (K1: 0)."""
    test_user.work_blocks = K_BLOCKS
    db.commit()
    e = _entry(db, test_user, time(8), time(18), auto_closed=True, break_minutes=45)
    assert (e.uncredited_minutes, e.clamp_grace_minutes) == (0, None)
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 18, 0))), test_user.id, db)
    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert (result.imported, result.overwritten) == (0, 1)
    db.refresh(e)
    assert (e.uncredited_minutes, e.clamp_grace_minutes, e.auto_closed, e.break_minutes) == (150, 15, False, 0)


def test_overwrite_reclamps_an_entry_stored_before_blocks(db, test_user, test_admin):
    """Ein ungekappt gespeicherter Eintrag (Bestand ohne Blöcke, raw NULL) wird
    beim Überschreiben gekappt: neuer Beginn, Rohstempel und Puffer gespeichert —
    kein zweiter Eintrag daneben."""
    test_user.work_blocks = LEGACY
    db.commit()
    e = _entry(db, test_user, time(7), time(16))
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 7, 0), _dt(2026, 6, 1, 16, 0))), test_user.id, db)
    assert row.has_conflict is True
    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert (result.imported, result.overwritten) == (0, 1)
    assert db.query(TimeEntry).count() == 1
    db.refresh(e)
    assert (e.start_time, e.raw_start_time, e.clamp_grace_minutes) == (time(7, 45), time(7), 15)


def test_overwrite_skips_when_the_new_start_is_taken(db, test_user, test_admin):
    """Der Beginn eines überschriebenen Eintrags kann sich durch dessen
    gespeicherten Puffer ändern — trifft er einen anderen Eintrag, wird die
    Zeile übersprungen statt an ``uq_tenant_user_date_start`` zu scheitern."""
    test_user.work_blocks = LEGACY
    db.commit()
    x = _entry(db, test_user, time(7), time(12), clamp_grace_minutes=30)
    _entry(db, test_user, time(7, 30), time(7, 40))
    result = _run(db, test_user, test_admin, [_row(time(7), time(12))], overwrite=True)
    assert (result.overwritten, result.skipped) == (0, 1)
    assert any("beginnt bereits um 07:30" in w for w in result.warnings)
    db.refresh(x)
    assert x.start_time == time(7)


# ── PR2: Netto vom Server und Anwesenheits-Hinweise in der Vorschau (7.4, 8.3) ──
def _k1_row():
    return _xls((datetime(2026, 6, 1, 8, 0), datetime(2026, 6, 1, 18, 0)))


def test_preview_net_hours_from_the_server(db, test_user):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    [e] = parse_xls(_k1_row(), test_user.id, db)
    assert (e.uncredited_minutes, e.break_minutes, e.net_hours) == (150, 0, 7.5)


def test_preview_not_credited_counts_gap_and_envelope(db, test_user):
    """P19: „nicht angerechnet" der Vorschau = Lücke + Hülle — dieselbe Quelle
    wie RawStampNote/Journal/Export (``work_window_service.not_credited_minutes``),
    nie ``uncredited_minutes`` allein. 07:00–19:00 bei K-Blöcken: Hülle 45 + 45,
    Lücke 150 → 4:00 h; angerechnet 8:00 h (07:45–18:15 − 2:30)."""
    test_user.work_blocks = K_BLOCKS
    db.commit()
    [e] = parse_xls(_xls((datetime(2026, 6, 1, 7, 0), datetime(2026, 6, 1, 19, 0))), test_user.id, db)
    assert (e.uncredited_minutes, e.not_credited_minutes, e.net_hours) == (150, 240, 8.0)
    assert e.model_dump()["not_credited_minutes"] == 240


def test_preview_lists_the_presence_hint_as_plain_text(db, test_user):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    [e] = parse_xls(_k1_row(), test_user.id, db)
    assert any(w.startswith("§4 ArbZG: Durchgehend über die Lücke") for w in e.arbzg_warnings)
    assert not any(w.startswith(("PRESENCE_", "BREAK_IN_GAP")) for w in e.arbzg_warnings)


# Review Focus 4: der überschriebene Bestandseintrag zählt in der Anwesenheit nicht doppelt.
def test_reimport_does_not_double_count_presence(db, test_user):
    test_user.work_blocks = K_BLOCKS
    _entry(db, test_user, time(8), time(12, 30), uncredited_minutes=15, clamp_grace_minutes=15)
    [e] = parse_xls(_xls((datetime(2026, 6, 1, 8, 0), datetime(2026, 6, 1, 12, 30))), test_user.id, db)
    assert e.has_conflict is True
    assert not any("Laut Stempel" in w or "Durchgehend" in w for w in e.arbzg_warnings), e.arbzg_warnings


# Review Focus 4 (Review Task 12): auch die harte §3/§4-Tagesaggregation zählt den
# überschriebenen Bestandseintrag nicht mit. Sonst stünde in derselben Zeile ein
# doppelt gezählter §3-Hinweis neben dem Anwesenheits-Hinweis, der ihn korrekt
# weglässt — und das daraus abgeleitete „§4 bestanden" (P14) wäre ebenfalls falsch.
def test_reimport_k1_does_not_double_count_the_hard_checks(db, test_user):
    test_user.work_blocks = K_BLOCKS
    db.commit()
    _entry(db, test_user, time(8), time(18), uncredited_minutes=150, clamp_grace_minutes=15)
    [e] = parse_xls(_k1_row(), test_user.id, db)
    assert e.has_conflict is True
    assert not [w for w in e.arbzg_warnings if "Netto-Arbeitszeit" in w], e.arbzg_warnings
    assert any(w.startswith("§4 ArbZG: Durchgehend über die Lücke") for w in e.arbzg_warnings)


def test_reimport_clamped_row_shows_presence_but_no_hard_s3(db, test_user):
    """07:00–19:00 bei K-Blöcken: angerechnet 8:00 h, anwesend 12:00 h. Der
    Re-Import meldet nur PRESENCE_DAILY — kein §3 „16.0h" aus doppelter Zählung,
    das dem „Angerechnet werden 8:00 h" daneben widerspräche."""
    test_user.work_blocks = K_BLOCKS
    db.commit()
    _entry(db, test_user, time(7, 45), time(18, 15), raw_start_time=time(7), raw_end_time=time(19),
           uncredited_minutes=150, clamp_grace_minutes=15)
    [e] = parse_xls(_xls((datetime(2026, 6, 1, 7, 0), datetime(2026, 6, 1, 19, 0))), test_user.id, db)
    assert e.has_conflict is True
    assert not [w for w in e.arbzg_warnings if "Netto-Arbeitszeit" in w], e.arbzg_warnings
    assert any(w.startswith("§3 ArbZG: Laut Stempel 12:00 h anwesend") for w in e.arbzg_warnings)


def test_reimport_of_a_legacy_row_has_no_warnings(db, test_user):
    test_user.work_blocks = LEGACY
    db.commit()
    _entry(db, test_user, time(8), time(16, 30), break_minutes=30)
    [e] = parse_xls(_xls((datetime(2026, 6, 1, 8, 0), datetime(2026, 6, 1, 16, 30))), test_user.id, db)
    assert e.has_conflict is True
    assert e.arbzg_warnings == []


def test_exempt_person_gets_no_presence_hint(db, test_user):
    test_user.work_blocks = K_BLOCKS
    test_user.exempt_from_arbzg = True
    db.commit()
    [e] = parse_xls(_k1_row(), test_user.id, db)
    assert not any("Laut Stempel" in w or "Durchgehend" in w for w in e.arbzg_warnings)


def test_preview_week_presence_hint(db, test_user):
    """Spec 8.3 (P22) „Ausgegeben an … XLS-Vorschau": Mo–Fr 08:00–18:00 bei
    Blöcken 08–12 + 15–18 → angerechnet 37:30 h, anwesend 50 h. Die Freitagszeile
    trägt den Wochenhinweis (Bestand + bisherige Zeilen der Woche), Donnerstag
    (40 h) noch nicht."""
    days = ("mon", "tue", "wed", "thu", "fri")
    test_user.work_blocks = block_week(**{d: [("08:00", "12:00"), ("15:00", "18:00")] for d in days})
    db.commit()
    rows = [(datetime(2026, 6, i, 8, 0), datetime(2026, 6, i, 18, 0)) for i in range(1, 6)]
    preview = parse_xls(_xls(*rows), test_user.id, db)
    week = "§3 ArbZG: Laut Stempel 50:00 h in dieser Woche anwesend"
    assert any(w.startswith(week) for w in preview[4].arbzg_warnings), preview[4].arbzg_warnings
    assert "Angerechnet werden 37:30 h" in next(w for w in preview[4].arbzg_warnings if w.startswith(week))
    assert not any("in dieser Woche" in w for p in preview[:4] for w in p.arbzg_warnings)


def test_preview_auto_pause_rest_gets_no_break_in_gap_hint(db, test_user):
    """E45 / 8.4 Zeile 1: die Auto-Pause der Vorschau IST bereits die Maßnahme
    gegen den Doppelabzug — sie trägt nur den §4-Rest, den die Lückensegmente
    nicht decken. Blöcke 08–12 + 12:50–17:00, Puffer 15 → Lückensegment
    12:15–12:35 (20 Min) deckt §4 zu 20 von 30 Min; Auto-Pause 10 → 15 (§4 Satz 2).
    ``BREAK_IN_GAP`` („bitte die Pause auf 0 setzen") wäre hier falsch: mit
    Pause 0 meldete ``validate_daily_break`` einen §4-Verstoß (Gesamtpause 20).
    Der Anwesenheits-Hinweis bleibt."""
    test_user.work_blocks = block_week(mon=[("08:00", "12:00"), ("12:50", "17:00")])
    db.commit()
    [e] = parse_xls(_xls((datetime(2026, 6, 1, 8, 0), datetime(2026, 6, 1, 17, 0))), test_user.id, db)
    assert (e.uncredited_minutes, e.break_minutes, e.net_hours) == (20, 15, 8.42)
    assert not any(w.startswith("Pause in der Lücke") for w in e.arbzg_warnings), e.arbzg_warnings
    assert any(w.startswith("§4 ArbZG: Durchgehend über die Lücke") for w in e.arbzg_warnings)


def test_preview_short_gap_segment_gets_no_break_in_gap_hint(db, test_user):
    """Lückensegment < 15 Min (Blöcke 08–12 + 12:40–17:00 → 12:15–12:25) deckt
    nichts; die Auto-Pause trägt den vollen §4-Bedarf (30). Auch hier kein
    „bitte die Pause auf 0 setzen" — es bliebe gar keine Pause."""
    test_user.work_blocks = block_week(mon=[("08:00", "12:00"), ("12:40", "17:00")])
    db.commit()
    [e] = parse_xls(_xls((datetime(2026, 6, 1, 8, 0), datetime(2026, 6, 1, 17, 0))), test_user.id, db)
    assert (e.uncredited_minutes, e.break_minutes) == (10, 30)
    assert not any(w.startswith("Pause in der Lücke") for w in e.arbzg_warnings), e.arbzg_warnings


def test_confirm_schema_has_no_net_or_not_credited_input():
    """E11: ``net_hours`` und ``not_credited_minutes`` sind nur Anzeige der
    Vorschau — ``/confirm`` rechnet neu und nimmt sie nicht an."""
    from app.routers.import_xls import ConfirmRequest

    body = ConfirmRequest.model_validate({
        "user_id": str(uuid.uuid4()), "overwrite": False,
        "entries": [{"date": MON.isoformat(), "start_time": "08:00", "end_time": "18:00",
                     "break_minutes": 0, "note": None, "has_conflict": False,
                     "arbzg_warnings": [], "net_hours": 99.0, "not_credited_minutes": 999}],
    })
    fields = type(body.entries[0]).model_fields
    assert "net_hours" not in fields and "not_credited_minutes" not in fields
