"""Gesamtreview 1.20 (B4): XLS-Import rechnet je TAG statt je Zeile.

1. Die Vorschau zählt einen Bestandseintrag, den eine SPÄTERE Zeile derselben
   Datei überschreibt, für die früheren Zeilen des Tages nicht mehr mit in §3/§4
   (bis hierher wurde ``replaced_ids`` erst beim Erreichen der überschreibenden
   Zeile gefüllt).
2. Die Automatik-Pause gilt dem Tag (#499: §4 ist eine Tagesprüfung) — alle
   Zeilen des Tages plus der nicht überschriebene Bestand, dieselbe Regel wie
   ``validate_daily_break`` (``daily_break_figures``); der fehlende Rest steht an
   der längsten Zeile. Vorschau und ``/confirm`` rechnen gleich, ``/confirm``
   übernimmt die Pause nicht vom Client (Spec 7.4).
3. §5 misst zwischen Arbeitstagen (wie ``rest_time_service``): Ende des letzten
   Arbeitstags davor gegen den ersten Beginn des Tages — nie gegen die Vorzeile
   desselben Tages (geteilter Dienst).
"""
from datetime import date, time

from app.models import TimeEntry, TimeEntryAuditLog
from app.services.xls_import_service import ImportedEntry, execute_import, parse_xls
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes
from tests.work_blocks_fixtures import MON, legacy_week

HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]
SUN = date(2026, 5, 31)


def _xls(*rows):
    return _make_xls_bytes([HEADER, *[_make_data_row(a, b) for a, b in rows]])


def _mon(h, m=0):
    return _dt(2026, 6, 1, h, m)


def _entry(db, user, start, end, *, day=MON, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=day, start_time=start,
                  end_time=end, break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def _row(start, end, *, break_minutes=0, day=MON, **kw):
    return ImportedEntry(date=day, start_time=start, end_time=end, break_minutes=break_minutes,
                         note=None, has_conflict=False, arbzg_warnings=[], **kw)


def _run(db, user, admin, rows, overwrite=False):
    return execute_import(user.id, rows, overwrite=overwrite, db=db, changed_by_id=admin.id,
                          filename="b4.xls", tenant_id=DEFAULT_TENANT_ID)


def _hard(row):
    """Die harten §3/§4-Meldungen der Vorschau (die weichen Anwesenheits-Hinweise
    beginnen ebenfalls mit „§3/§4 ArbZG:", nennen aber keine Netto-Arbeitszeit)."""
    return [w for w in row.arbzg_warnings if "Netto-Arbeitszeit" in w]


def _rest(row):
    return [w for w in row.arbzg_warnings if w.startswith("§5")]


# ── Punkt 1: ein später überschriebener Bestandseintrag zählt auch vorher nicht ──

def test_first_row_ignores_an_entry_a_later_row_replaces(db, test_user):
    """Bestand 08:00–12:00 und 12:00–19:00; der Re-Import kürzt den Nachmittag auf
    12:00–16:00. Die Vormittagszeile darf den alten Nachmittag (7 h) nicht mehr in
    ihre Tagessumme nehmen — er wird von der zweiten Zeile ersetzt („11.0h")."""
    _entry(db, test_user, time(8), time(12))
    _entry(db, test_user, time(12), time(19))
    rows = parse_xls(_xls((_mon(8), _mon(12)), (_mon(12), _mon(16))), test_user.id, db)
    assert [r.has_conflict for r in rows] == [True, True]
    assert _hard(rows[0]) == [], rows[0].arbzg_warnings
    assert _hard(rows[1]) == [], rows[1].arbzg_warnings


def test_first_row_presence_ignores_an_entry_a_later_row_replaces(db, test_user):
    """Dieselbe Menge für die Anwesenheit: der alte Abend (gestempelt bis 23:00,
    angerechnet bis 17:15) eines später ersetzten Eintrags darf keinen
    Tageshinweis „laut Stempel 15:00 h" auslösen."""
    test_user.work_blocks = legacy_week(mon=("08:00", "17:00"))
    db.commit()
    _entry(db, test_user, time(8), time(12))
    _entry(db, test_user, time(12), time(17, 15), raw_end_time=time(23), clamp_grace_minutes=15)
    rows = parse_xls(_xls((_mon(8), _mon(12)), (_mon(12), _mon(16))), test_user.id, db)
    assert [r.has_conflict for r in rows] == [True, True]
    assert not any("Laut Stempel" in w for w in rows[0].arbzg_warnings), rows[0].arbzg_warnings


# ── Punkt 2a: Automatik-Pause je Tag ─────────────────────────────────────────

def test_preview_auto_pause_covers_the_day_not_each_row(db, test_user):
    """08:00–11:00 + 11:05–15:30: einzeln unter 6 h, zusammen 7:25 h mit einem
    Abstand unter 15 Min (keine Pause). Bisher je Zeile 0 → der Tag stand ohne
    Pause da; jetzt 30 Min an der längeren Zeile."""
    rows = parse_xls(_xls((_mon(8), _mon(11)), (_mon(11, 5), _mon(15, 30))), test_user.id, db)
    assert [r.break_minutes for r in rows] == [0, 30]
    assert [r.net_hours for r in rows] == [3.0, 3.92]
    assert not any(_hard(r) for r in rows), [r.arbzg_warnings for r in rows]


def test_preview_auto_pause_counts_the_gap_between_rows(db, test_user):
    """06:30–12:45 (6:15 h) + 13:15–16:00: der Abstand von 30 Min deckt die
    Pausenpflicht des Tages (9 h → 30 Min) schon. Je Zeile zog der Import für die
    erste Zeile zusätzlich 30 Min ab (Doppelabzug)."""
    rows = parse_xls(_xls((_mon(6, 30), _mon(12, 45)), (_mon(13, 15), _mon(16))), test_user.id, db)
    assert [r.break_minutes for r in rows] == [0, 0]
    assert [r.net_hours for r in rows] == [6.25, 2.75]
    assert not any(_hard(r) for r in rows)


def test_preview_auto_pause_rest_goes_to_the_longest_row(db, test_user):
    """07:00–13:30 + 14:00–20:30 (je 6:30 h, Abstand 30): Tag 13 h → 45 Min Bedarf,
    30 gedeckt → Rest 15 an der ersten der beiden gleich langen Zeilen. Je Zeile
    waren es 30 + 30 = 60 Min."""
    rows = parse_xls(_xls((_mon(7), _mon(13, 30)), (_mon(14), _mon(20, 30))), test_user.id, db)
    assert [r.break_minutes for r in rows] == [15, 0]


def test_preview_auto_pause_includes_kept_entries_of_the_day(db, test_user):
    """Bestand 08:00–11:00 ohne Pause bleibt stehen (anderer Beginn); die Zeile
    11:00–15:30 macht den Tag zu 7:30 h am Stück → 30 Min an der Importzeile."""
    _entry(db, test_user, time(8), time(11))
    [row] = parse_xls(_xls((_mon(11), _mon(15, 30))), test_user.id, db)
    assert row.has_conflict is False
    assert row.break_minutes == 30
    assert _hard(row) == []


def test_confirm_auto_pause_per_day_with_blocks(db, test_user, test_admin):
    """``/confirm`` rechnet an Tagen mit Blöcken selbst — ebenfalls je Tag."""
    test_user.work_blocks = legacy_week(mon=("07:00", "17:00"))
    db.commit()
    _run(db, test_user, test_admin, [_row(time(8), time(11)), _row(time(11, 5), time(15, 30))])
    stored = db.query(TimeEntry).order_by(TimeEntry.start_time).all()
    assert [e.break_minutes for e in stored] == [0, 30]


def test_confirm_does_not_take_the_break_from_the_client(db, test_user, test_admin):
    """Spec 7.4: ``/confirm`` übernimmt die Pause nicht vom Client — auch an Tagen
    ohne Blöcke (bisher dort ungeprüft übernommen)."""
    _run(db, test_user, test_admin, [
        _row(time(8), time(11), break_minutes=0), _row(time(11, 5), time(15, 30), break_minutes=0),
        _row(time(8), time(17), break_minutes=0, day=date(2026, 6, 2)),
    ])
    stored = db.query(TimeEntry).order_by(TimeEntry.date, TimeEntry.start_time).all()
    assert [e.break_minutes for e in stored] == [0, 30, 30]


def test_confirm_matches_the_preview(db, test_user, test_admin):
    """Unveränderte Vorschau → dieselben Pausen in der Datenbank, das Protokoll
    nennt die gespeicherte Pause."""
    xls = _xls((_mon(7), _mon(13, 30)), (_mon(14), _mon(20, 30)))
    preview = parse_xls(xls, test_user.id, db)
    _run(db, test_user, test_admin, preview)
    stored = db.query(TimeEntry).order_by(TimeEntry.start_time).all()
    assert [e.break_minutes for e in stored] == [r.break_minutes for r in preview] == [15, 0]
    logs = {
        l.time_entry_id: l.new_break_minutes
        for l in db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.action == "create").all()
    }
    assert [logs[e.id] for e in stored] == [15, 0]


def test_confirm_keeps_skipped_conflicts_in_the_day(db, test_user, test_admin):
    """Ohne „überschreiben" bleibt der Bestand stehen und zählt für die Tages-Pause
    der neuen Zeile mit: Bestand 08:00–11:00 (Zeile übersprungen) + neue Zeile
    11:00–15:30 → 30 Min an der neuen Zeile."""
    _entry(db, test_user, time(8), time(11))
    result = _run(db, test_user, test_admin, [_row(time(8), time(10)), _row(time(11), time(15, 30))])
    assert (result.imported, result.skipped) == (1, 1)
    new = db.query(TimeEntry).filter(TimeEntry.start_time == time(11)).one()
    assert new.break_minutes == 30


def test_confirm_overwrite_logs_old_and_new_break(db, test_user, test_admin):
    """Die Protokollzeile entsteht erst mit der Tages-Pause — ``new_break_minutes``
    geht in den Manipulationsschutz (#121) ein, die Zeile muss danach prüfbar sein."""
    from app.core.audit_integrity import verify_row

    _entry(db, test_user, time(8), time(17), break_minutes=45)
    _run(db, test_user, test_admin, [_row(time(8), time(16))], overwrite=True)
    log = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.action == "update").one()
    assert (log.old_break_minutes, log.new_break_minutes) == (45, 30)
    assert all(verify_row(l) for l in db.query(TimeEntryAuditLog).all())


# ── Punkt 2b: §5 zwischen Arbeitstagen ───────────────────────────────────────

def test_split_shift_gets_no_rest_time_warning(db, test_user):
    """Geteilter Dienst 08:00–12:00 + 14:00–18:00: die zweite Zeile verglich §5
    mit dem Ende der ersten (2 h) — das ist eine Pause, keine Ruhezeit."""
    rows = parse_xls(_xls((_mon(8), _mon(12)), (_mon(14), _mon(18))), test_user.id, db)
    assert [_rest(r) for r in rows] == [[], []]


def test_rest_time_is_reported_once_per_day(db, test_user):
    """Vortag bis 23:00, geteilter Dienst ab 07:00: §5 (8 h) einmal an der ersten
    Zeile des Tages — die zweite wiederholt ihn nicht."""
    _entry(db, test_user, time(15), time(23), day=SUN)
    rows = parse_xls(_xls((_mon(7), _mon(11)), (_mon(11, 30), _mon(15))), test_user.id, db)
    assert [len(_rest(r)) for r in rows] == [1, 0]
    assert _rest(rows[0])[0].startswith("§5 ArbZG: Ruhezeit 8.0h"), rows[0].arbzg_warnings


def test_rest_time_uses_the_last_end_of_the_previous_day(db, test_user):
    """Der Vortag endet mit einem Bestandseintrag, der nicht in der Datei steht
    (19:00–23:00): §5 misst ab 23:00, nicht ab dem Ende der Vortagszeile der
    Datei (12:00)."""
    _entry(db, test_user, time(19), time(23), day=SUN)
    rows = parse_xls(_xls((_dt(2026, 5, 31, 8, 0), _dt(2026, 5, 31, 12, 0)), (_mon(8), _mon(12))),
                     test_user.id, db)
    assert _rest(rows[1]) and _rest(rows[1])[0].startswith("§5 ArbZG: Ruhezeit 9.0h"), rows[1].arbzg_warnings


def test_rest_time_ignores_a_replaced_entry_of_the_previous_day(db, test_user):
    """Ein Vortagseintrag, den die Datei überschreibt (früher Feierabend statt
    23:00), zählt für §5 nicht mehr."""
    _entry(db, test_user, time(15), time(23), day=SUN)
    rows = parse_xls(_xls((_dt(2026, 5, 31, 15, 0), _dt(2026, 5, 31, 18, 0)), (_mon(7), _mon(12))),
                     test_user.id, db)
    assert rows[0].has_conflict is True
    assert _rest(rows[1]) == [], rows[1].arbzg_warnings
