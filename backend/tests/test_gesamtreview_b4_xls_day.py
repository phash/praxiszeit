"""Gesamtreview 1.20 (B4): XLS-Import rechnet je TAG statt je Zeile.

1. Die Vorschau zählt einen Bestandseintrag, den eine SPÄTERE Zeile derselben
   Datei überschreibt, für die früheren Zeilen des Tages nicht mehr mit in §3/§4
   (bis hierher wurde ``replaced_ids`` erst beim Erreichen der überschreibenden
   Zeile gefüllt).
"""
from datetime import time

from app.models import TimeEntry
from app.services.xls_import_service import parse_xls
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes
from tests.work_blocks_fixtures import MON, legacy_week

HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]


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


def _hard(row):
    """Die harten §3/§4-Meldungen der Vorschau (die weichen Anwesenheits-Hinweise
    beginnen ebenfalls mit „§3/§4 ArbZG:", nennen aber keine Netto-Arbeitszeit)."""
    return [w for w in row.arbzg_warnings if "Netto-Arbeitszeit" in w]


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
