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
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

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
    danach; der reine Lückenfall bekommt trotzdem den Kappungshinweis."""
    test_user.work_blocks = K_BLOCKS
    db.commit()
    _entry(db, test_user, time(18), time(18, 30))
    [row] = parse_xls(_xls((_dt(2026, 6, 1, 8, 0), _dt(2026, 6, 1, 18, 0))), test_user.id, db)
    assert (row.start_time, row.end_time, row.raw_start_time, row.raw_end_time) == (time(8), time(18), None, None)
    assert (row.uncredited_minutes, row.break_minutes) == (150, 0)
    assert not [w for w in row.arbzg_warnings if w.startswith(("§3", "§4"))], row.arbzg_warnings
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
