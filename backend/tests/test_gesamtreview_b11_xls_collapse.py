"""Gesamtreview 1.20 (B11, Altfehler aus B4): eine XLS-Zeile ganz außerhalb der
Hülle wird wie an jedem anderen Schreibweg gekappt (Kollaps, 0 h angerechnet,
Rohstempel bleibt — §16), nicht übersprungen.

Bis hierher prüfte ``/confirm`` „Ende nach Beginn" auf den GEKAPPTEN Zeiten der
Vorschau (18:00–18:00) und übersprang die Zeile mit „Endzeit (18:00) liegt nicht
nach Startzeit (18:00). Über-Mitternacht-Schichten …" — der Rohstempel 18:00–20:00
ging verloren. Die Reihenfolgeprüfung gilt der Datei-Zeile (Rohstempel).
"""
from datetime import time

from app.models import TimeEntry
from app.services.xls_import_service import execute_import, parse_xls
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes
from tests.work_blocks_fixtures import legacy_week

HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]


def _xls(*rows):
    return _make_xls_bytes([HEADER, *[_make_data_row(a, b) for a, b in rows]])


def _mon(h, m=0):
    return _dt(2026, 6, 1, h, m)


def _run(db, user, admin, rows, overwrite=False):
    return execute_import(user.id, rows, overwrite=overwrite, db=db, changed_by_id=admin.id,
                          filename="b11.xls", tenant_id=DEFAULT_TENANT_ID)


def _blocks(db, user):
    user.work_blocks = legacy_week(mon=("08:00", "12:00"))
    db.commit()


def test_preview_collapsed_row_counts_with_zero_hours(db, test_user):
    """Block 08–12, Zeile 18:00–20:00: Vorschau zeigt 0 h angerechnet, den
    Rohstempel und den Kollaps-Hinweis — kein „übersprungen"."""
    _blocks(db, test_user)
    [row] = parse_xls(_xls((_mon(18), _mon(20))), test_user.id, db)
    assert (row.start_time, row.end_time) == (time(18), time(18))
    assert (row.raw_start_time, row.raw_end_time) == (time(18), time(20))
    assert row.net_hours == 0.0
    assert any("vollstaendig ausserhalb" in w for w in row.arbzg_warnings), row.arbzg_warnings
    assert not any("bersprungen" in w for w in row.arbzg_warnings), row.arbzg_warnings


def test_confirm_stores_collapsed_row_with_raw_stamp(db, test_user, test_admin):
    """``/confirm`` legt den Eintrag mit 0 h an und erhält den Rohstempel (§16)."""
    _blocks(db, test_user)
    preview = parse_xls(_xls((_mon(18), _mon(20))), test_user.id, db)
    result = _run(db, test_user, test_admin, preview)
    assert (result.imported, result.skipped) == (1, 0), result.warnings
    assert not any("liegt nicht nach Startzeit" in w for w in result.warnings), result.warnings
    e = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).one()
    assert (e.start_time, e.end_time) == (time(18), time(18))
    assert (e.raw_start_time, e.raw_end_time) == (time(18), time(20))
    assert float(e.net_hours) == 0.0
    assert e.break_minutes == 0


def test_collapsed_row_replaces_existing_entry(db, test_user, test_admin):
    """Die Kollaps-Zeile zählt (anders als eine Zeile mit Ende ≤ Beginn): mit
    „überschreiben" ersetzt sie den Bestand mit demselben Rohbeginn."""
    _blocks(db, test_user)
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=_mon(0).date(),
                     start_time=time(18), end_time=time(18), raw_start_time=time(18),
                     raw_end_time=time(19), break_minutes=0))
    db.commit()
    preview = parse_xls(_xls((_mon(18), _mon(20))), test_user.id, db)
    assert preview[0].has_conflict is True
    result = _run(db, test_user, test_admin, preview, overwrite=True)
    assert (result.imported, result.overwritten, result.skipped) == (0, 1, 0), result.warnings
    e = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).one()
    assert e.raw_end_time == time(20)


def test_row_with_end_before_start_is_still_skipped(db, test_user, test_admin):
    """Kontrolle: die Datei-Zeile 20:00–18:00 bleibt übersprungen — die Prüfung
    gilt dem Rohstempel und nennt ihn."""
    _blocks(db, test_user)
    preview = parse_xls(_xls((_mon(20), _mon(18))), test_user.id, db)
    result = _run(db, test_user, test_admin, preview)
    assert (result.imported, result.skipped) == (0, 1)
    assert any("Endzeit (18:00) liegt nicht nach Startzeit (20:00)" in w for w in result.warnings), \
        result.warnings
    assert db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).count() == 0


# --- Review-Nachzug B11: Zweig ohne Kappung folgt nicht blind den Client-Zeiten ---

def test_unclamped_forged_end_before_start_takes_file_times(db, test_user, test_admin):
    """Ohne Kappung (``track_hours=False``) und mit gefälschter Zeile
    (gespeicherte Zeiten 12:00–08:00, Rohstempel 08:00–12:00): nie ein Eintrag
    mit Ende vor Beginn — es gilt die Datei-Zeile."""
    test_user.track_hours = False
    db.commit()
    [row] = parse_xls(_xls((_mon(8), _mon(12))), test_user.id, db)
    forged = row.model_copy(update={
        "start_time": time(12), "end_time": time(8),
        "raw_start_time": time(8), "raw_end_time": time(12),
    })
    result = _run(db, test_user, test_admin, [forged])
    entries = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).all()
    for e in entries:
        assert e.end_time > e.start_time, (e.start_time, e.end_time)
    assert result.imported == 1, result.warnings
    [e] = entries
    assert (e.start_time, e.end_time) == (time(8), time(12))


def test_stale_collapse_preview_without_clamp_credits_file_row(db, test_user, test_admin):
    """Vorschau mit Blöcken kollabiert 18:00–20:00 auf 18:00–18:00; vor
    ``/confirm`` entfällt die Kappung (``track_hours=False``). Gespeichert wird
    die Datei-Zeile 18:00–20:00 (2 h), nicht der veraltete Kollaps mit 0 h."""
    _blocks(db, test_user)
    preview = parse_xls(_xls((_mon(18), _mon(20))), test_user.id, db)
    assert (preview[0].start_time, preview[0].end_time) == (time(18), time(18))
    test_user.track_hours = False
    db.commit()
    result = _run(db, test_user, test_admin, preview)
    assert (result.imported, result.skipped) == (1, 0), result.warnings
    e = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).one()
    assert (e.start_time, e.end_time) == (time(18), time(20))
    assert float(e.net_hours) == 2.0
