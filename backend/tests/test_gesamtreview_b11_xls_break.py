"""Gesamtreview 1.20 (B11, Produktentscheidung 2026-10-17): XLS-Import, §4-Rest.

Der Import zieht die gesetzliche Mindestpause je Tag automatisch ab
(``_day_break_minutes``). Bleibt danach ein §4-Fehlbetrag — die Zeilen der Datei
können die Pause nicht tragen, z. B. eine kurze Zeile neben einem langen
vorhandenen Eintrag —, übernimmt der Import diesen Tag NICHT, unabhängig vom
Schalter ``break_exception_allowed`` (der Import kennt keine Begründung, kann also
keine §4-Ausnahme belegen). Vorschau und Ergebnis nennen den Grund; die Zeilen
ersetzen keinen vorhandenen Eintrag und zählen für keinen Tag mit. Bis hierher
legte der Import den Tag mit fehlender Pause an, die Vorschau meldete nur §4.
"""
from datetime import date, time

import pytest

from app.models import TimeEntry, TimeEntryAuditLog
from app.models.system_setting import SystemSetting
from app.services.xls_import_service import execute_import, parse_xls
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_xls_import_service import _dt, _make_data_row, _make_xls_bytes
from tests.work_blocks_fixtures import MON

HEADER = ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"]
TUE = date(2026, 6, 2)


def _reason(n):
    return (f"die Pause nach § 4 ArbZG lässt sich mit den Zeilen dieses Tages nicht abziehen "
            f"(es fehlen {n} Min). Bitte den Tag von Hand erfassen")


def _xls(*rows):
    return _make_xls_bytes([HEADER, *[_make_data_row(a, b) for a, b in rows]])


def _mon(h, m=0):
    return _dt(2026, 6, 1, h, m)


def _tue(h, m=0):
    return _dt(2026, 6, 2, h, m)


def _entry(db, user, start, end, *, day=MON, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=day, start_time=start,
                  end_time=end, break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def _run(db, user, admin, rows, overwrite=False):
    return execute_import(user.id, rows, overwrite=overwrite, db=db, changed_by_id=admin.id,
                          filename="b11.xls", tenant_id=DEFAULT_TENANT_ID)


def _switch(db, allowed):
    if not allowed:
        db.add(SystemSetting(key="break_exception_allowed", value="false",
                             tenant_id=DEFAULT_TENANT_ID))
        db.commit()


def _stored(db, user):
    return [
        (e.date, e.start_time, e.end_time, e.break_minutes, e.raw_end_time)
        for e in db.query(TimeEntry).filter(TimeEntry.user_id == user.id)
        .order_by(TimeEntry.date, TimeEntry.start_time).all()
    ]


@pytest.mark.parametrize("allowed", [True, False])
def test_preview_marks_a_day_without_carryable_break_as_skipped(db, test_user, allowed):
    """Bestand 08:00–17:00 ohne Pause + Zeile 17:00–17:20: der Tag braucht 30 Min
    (9:00 h nach dem Abzug), die Zeile trägt 20 → es fehlen 10 Min."""
    _switch(db, allowed)
    _entry(db, test_user, time(8), time(17))
    [row] = parse_xls(_xls((_mon(17), _mon(17, 20))), test_user.id, db)
    assert row.arbzg_warnings == [f"Wird übersprungen — {_reason(10)}."]
    assert row.has_conflict is False
    assert row.break_minutes == 0


@pytest.mark.parametrize("allowed", [True, False])
def test_confirm_skips_a_day_without_carryable_break(db, test_user, test_admin, allowed):
    _switch(db, allowed)
    _entry(db, test_user, time(8), time(17))
    preview = parse_xls(_xls((_mon(17), _mon(17, 20))), test_user.id, db)
    result = _run(db, test_user, test_admin, preview)
    assert (result.imported, result.overwritten, result.skipped) == (0, 0, 1)
    assert result.warnings == [f"01.06.2026: übersprungen — {_reason(10)}."]
    assert _stored(db, test_user) == [(MON, time(8), time(17), 0, None)]
    logs = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.time_entry_id.isnot(None)).all()
    assert logs == []


def test_skipped_day_replaces_no_entry(db, test_user, test_admin):
    """Bestand 08:00–17:00 und 17:00–17:30; die Zeile 17:00–17:20 träfe den
    zweiten über den Beginn. Der Tag fällt heraus → kein Konflikt in der Vorschau,
    und auch mit „überschreiben" bleibt der Bestand unverändert (kein halber Tag)."""
    _entry(db, test_user, time(8), time(17))
    _entry(db, test_user, time(17), time(17, 30))
    [row] = parse_xls(_xls((_mon(17), _mon(17, 20))), test_user.id, db)
    assert row.has_conflict is False
    assert row.arbzg_warnings[0].startswith("Wird übersprungen — die Pause nach § 4 ArbZG")

    result = _run(db, test_user, test_admin, [row], overwrite=True)
    assert (result.imported, result.overwritten, result.skipped) == (0, 0, 1)
    assert _stored(db, test_user) == [
        (MON, time(8), time(17), 0, None), (MON, time(17), time(17, 30), 0, None),
    ]


def test_confirm_skips_the_day_when_the_stock_changed_after_the_preview(db, test_user, test_admin):
    """Die Vorschau sah den Montag ohne Bestand (17:00–17:20 braucht keine Pause);
    bis zur Bestätigung entsteht 08:00–17:00. ``/confirm`` rechnet neu, nimmt den
    Montag mit demselben Grund zurück — der Dienstag wird übernommen."""
    preview = parse_xls(_xls((_mon(17), _mon(17, 20)), (_tue(8), _tue(12))), test_user.id, db)
    assert [r.arbzg_warnings for r in preview] == [[], []]
    _entry(db, test_user, time(8), time(17))
    result = _run(db, test_user, test_admin, preview)
    assert (result.imported, result.overwritten, result.skipped) == (1, 0, 1)
    assert f"01.06.2026: übersprungen — {_reason(10)}." in result.warnings
    assert _stored(db, test_user) == [
        (MON, time(8), time(17), 0, None), (TUE, time(8), time(12), 0, None),
    ]


def test_confirm_with_overwrite_restores_the_overwritten_entry(db, test_user, test_admin):
    """Ein überschriebener Eintrag eines zurückgenommenen Tages bekommt alle
    Werte zurück. Vorschau: Bestand 17:00–17:30 wird ersetzt, Tag ohne weiteren
    Bestand → keine Pause nötig. Bis zur Bestätigung entsteht 08:00–17:00."""
    old = _entry(db, test_user, time(17), time(17, 30), note="alt")
    preview = parse_xls(_xls((_mon(17), _mon(17, 20))), test_user.id, db)
    assert preview[0].has_conflict is True
    _entry(db, test_user, time(8), time(17))
    result = _run(db, test_user, test_admin, preview, overwrite=True)
    assert (result.imported, result.overwritten, result.skipped) == (0, 0, 1)
    db.refresh(old)
    assert (old.start_time, old.end_time, old.note, old.break_minutes) == \
        (time(17), time(17, 30), "alt", 0)


def test_day_with_carryable_break_is_imported(db, test_user, test_admin):
    """Kontrolle: Bestand 08:00–17:00 + 17:00–17:20 + 17:20–17:50 — die Zeilen
    tragen die 45 Min zusammen (B4) → der Tag wird übernommen."""
    _entry(db, test_user, time(8), time(17))
    preview = parse_xls(_xls((_mon(17), _mon(17, 20)), (_mon(17, 20), _mon(17, 50))),
                        test_user.id, db)
    assert [r.break_minutes for r in preview] == [15, 30]
    assert not any("bersprungen" in w for r in preview for w in r.arbzg_warnings)
    result = _run(db, test_user, test_admin, preview)
    assert (result.imported, result.skipped) == (2, 0)


def test_exempt_person_is_not_skipped(db, test_user, test_admin):
    """§18-befreit: keine §4-Prüfung, also auch kein Übersprung."""
    test_user.exempt_from_arbzg = True
    db.commit()
    _entry(db, test_user, time(8), time(17))
    preview = parse_xls(_xls((_mon(17), _mon(17, 20))), test_user.id, db)
    assert not any("bersprungen" in w for w in preview[0].arbzg_warnings)
    result = _run(db, test_user, test_admin, preview)
    assert (result.imported, result.skipped) == (1, 0)
