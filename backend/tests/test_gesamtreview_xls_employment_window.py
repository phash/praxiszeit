"""Gesamtreview 1.20 (Parallelpfad zu Review-Fund 8): der XLS-Import achtet auf
das Beschäftigungsfenster der Zielperson.

Einstempeln, beide Anlege-/Bearbeiten-Routen und die Antragsgenehmigung lehnen
ein Datum vor ``first_work_day`` bzw. nach ``last_work_day`` mit 400 ab. Der
Import speicherte solche Zeilen still: ``imported=1``, keine Warnung — der
Eintrag fiel danach aus dem gefensterten Ist (#195) heraus, ohne dass es jemand
sah.

Jetzt überspringt der Import sie sichtbar, wie Zeilen mit Ende ≤ Beginn: in der
Vorschau mit einem Hinweis, in ``/confirm`` mit einer Warnung im Ergebnis. Die
Zeile zählt für keinen Tag (Pause, §3/§4, §5, Anwesenheit) und ersetzt keinen
vorhandenen Eintrag — auch nicht mit „überschreiben".
"""
from datetime import date, time

from app.models import TimeEntry
from app.services.xls_import_service import ImportedEntry, execute_import, parse_xls
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes

HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]
THU = date(2026, 9, 24)
LAST = date(2026, 9, 25)          # Freitag = letzter Arbeitstag
AFTER = date(2026, 9, 29)         # Dienstag danach
BEFORE = date(2026, 9, 30)        # Mittwoch vor dem ersten Arbeitstag
FIRST = date(2026, 10, 1)         # Donnerstag = erster Arbeitstag

AFTER_NOTE = "Wird übersprungen — Datum liegt nach dem letzten Arbeitstag (25.09.2026)."
BEFORE_NOTE = "Wird übersprungen — Datum liegt vor dem ersten Arbeitstag (01.10.2026)."


def _xls(*rows):
    return _make_xls_bytes([HEADER, *[_make_data_row(a, b) for a, b in rows]])


def _at(d, h, m=0):
    return _dt(d.year, d.month, d.day, h, m)


def _run(db, user, admin, rows, overwrite=False):
    return execute_import(user.id, rows, overwrite=overwrite, db=db, changed_by_id=admin.id,
                          filename="fenster.xls", tenant_id=DEFAULT_TENANT_ID)


def _stored(db, user):
    db.expire_all()
    return [
        (e.date, e.start_time, e.end_time)
        for e in db.query(TimeEntry).filter(TimeEntry.user_id == user.id)
        .order_by(TimeEntry.date, TimeEntry.start_time).all()
    ]


def test_preview_marks_a_row_after_the_last_work_day(db, test_user):
    test_user.last_work_day = LAST
    db.commit()
    rows = parse_xls(_xls((_at(THU, 8), _at(THU, 12)), (_at(AFTER, 8), _at(AFTER, 12))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    assert AFTER_NOTE not in rows[0].arbzg_warnings, rows[0].arbzg_warnings
    assert rows[1].arbzg_warnings == [AFTER_NOTE]
    assert rows[1].has_conflict is False


def test_preview_marks_a_row_before_the_first_work_day(db, test_user):
    test_user.first_work_day = FIRST
    db.commit()
    rows = parse_xls(_xls((_at(BEFORE, 8), _at(BEFORE, 12)), (_at(FIRST, 8), _at(FIRST, 12))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    assert rows[0].arbzg_warnings == [BEFORE_NOTE]
    assert BEFORE_NOTE not in rows[1].arbzg_warnings, rows[1].arbzg_warnings


def test_preview_row_outside_carries_only_the_skip_note(db, test_user):
    """06:00–18:00 löste sonst §3 (mehr als 10 h) aus — für eine Zeile, die nie
    gespeichert wird, wäre jede weitere Meldung Lärm."""
    test_user.last_work_day = LAST
    db.commit()
    rows = parse_xls(_xls((_at(AFTER, 6), _at(AFTER, 18))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    assert rows[0].arbzg_warnings == [AFTER_NOTE]
    assert rows[0].break_minutes == 0


def test_skipped_row_sets_no_end_of_work_for_the_rest_time(db, test_user):
    """30.09. bis 23:00 liegt vor dem ersten Arbeitstag und wird übersprungen —
    der 01.10. ab 07:00 bekommt deshalb keinen §5-Hinweis (8 h Ruhezeit)."""
    test_user.first_work_day = FIRST
    db.commit()
    rows = parse_xls(_xls((_at(BEFORE, 15), _at(BEFORE, 23)), (_at(FIRST, 7), _at(FIRST, 12))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    assert not any(w.startswith("§5") for w in rows[1].arbzg_warnings), rows[1].arbzg_warnings


def test_confirm_skips_rows_outside_with_a_visible_warning(db, test_user, test_admin):
    """Die Sonde aus dem Review: ``last_work_day`` 25.09., Zeile vom 29.09."""
    test_user.last_work_day = LAST
    db.commit()
    rows = parse_xls(_xls((_at(THU, 8), _at(THU, 12)), (_at(AFTER, 8), _at(AFTER, 12))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    result = _run(db, test_user, test_admin, rows)
    assert (result.imported, result.overwritten, result.skipped) == (1, 0, 1)
    assert "29.09.2026: übersprungen — Datum liegt nach dem letzten Arbeitstag (25.09.2026)." \
        in result.warnings, result.warnings
    # Der Vorschau-Hinweis wird nicht zusätzlich als Warnung übernommen.
    assert not any(AFTER_NOTE in w for w in result.warnings), result.warnings
    assert _stored(db, test_user) == [(THU, time(8), time(12))]


def test_confirm_checks_the_window_itself(db, test_user, test_admin):
    """``/confirm`` nimmt die Zeilen vom Client — ohne Vorschau-Hinweis wird
    trotzdem übersprungen."""
    test_user.first_work_day = FIRST
    db.commit()
    forged = ImportedEntry(date=BEFORE, start_time=time(8), end_time=time(12), break_minutes=0,
                           note=None, has_conflict=False, arbzg_warnings=[])
    result = _run(db, test_user, test_admin, [forged])
    assert (result.imported, result.skipped) == (0, 1)
    assert result.warnings == [
        "30.09.2026: übersprungen — Datum liegt vor dem ersten Arbeitstag (01.10.2026)."
    ]
    assert _stored(db, test_user) == []


def test_row_outside_replaces_no_entry_even_with_overwrite(db, test_user, test_admin):
    """Ein Alteintrag vom 29.09. (angelegt, bevor der letzte Arbeitstag gesetzt
    war) bleibt stehen: die Zeile der Datei wird übersprungen, statt ihn zu
    überschreiben."""
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=AFTER,
                     start_time=time(8), end_time=time(12), break_minutes=0))
    test_user.last_work_day = LAST
    db.commit()
    rows = parse_xls(_xls((_at(AFTER, 8), _at(AFTER, 13))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    assert rows[0].has_conflict is False
    assert rows[0].arbzg_warnings == [AFTER_NOTE]
    result = _run(db, test_user, test_admin, rows, overwrite=True)
    assert (result.imported, result.overwritten, result.skipped) == (0, 0, 1)
    assert _stored(db, test_user) == [(AFTER, time(8), time(12))]


def test_rows_inside_the_window_are_unchanged(db, test_user, test_admin):
    """Kontrollfall: Fenster gesetzt, alle Zeilen darin → normaler Import."""
    test_user.first_work_day = date(2026, 9, 1)
    test_user.last_work_day = LAST
    db.commit()
    rows = parse_xls(_xls((_at(THU, 8), _at(THU, 12)), (_at(LAST, 8), _at(LAST, 12))),
                     test_user.id, db, tenant_id=DEFAULT_TENANT_ID)
    assert all(r.arbzg_warnings == [] for r in rows), [r.arbzg_warnings for r in rows]
    result = _run(db, test_user, test_admin, rows)
    assert (result.imported, result.skipped, result.warnings) == (2, 0, [])
