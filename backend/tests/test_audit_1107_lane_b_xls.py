"""Audit 2026-11-07, Lane B — XLS-Import (#538 A1-02, #540 A1-07) und
Sommerzeit bei der Ruhezeit (#540 A1-10)."""
from datetime import date, time

from app.models import TimeEntry
from app.services import rest_time_service
from app.services.timezone_service import hours_between
from app.services.xls_import_service import parse_xls
from tests.test_gesamtreview_b4_xls_day import _entry, _mon, _row, _run, _xls

PREFIX = "Wird übersprungen — "


# ── A1-07: § 3 serverseitig, hart ─────────────────────────────────────────────

def test_preview_skips_a_day_over_10h(db, test_user):
    [row] = parse_xls(_xls((_mon(6), _mon(18))), test_user.id, db)  # 12 h − 45 Min.
    assert row.arbzg_warnings == [
        PREFIX + "die Tagesarbeitszeit beträgt 11:15 h und überschreitet die Höchstgrenze "
        "von 10 h nach § 3 ArbZG. Bitte den Tag von Hand erfassen."
    ]


def test_preview_keeps_exactly_10h(db, test_user):
    [row] = parse_xls(_xls((_mon(7), _mon(17, 45))), test_user.id, db)  # 10:45 − 45 = 10:00
    assert not any(w.startswith(PREFIX) for w in row.arbzg_warnings), row.arbzg_warnings


def test_confirm_enforces_10h_without_trusting_client_warnings(db, test_user, test_admin):
    """Ein /confirm mit leeren Warnungen (Probe des Audits: 06:00–22:00) legt den
    Tag nicht an — der Server rechnet § 3 selbst."""
    result = _run(db, test_user, test_admin, [_row(time(6), time(22))])
    assert (result.imported, result.skipped) == (0, 1)
    assert any("§ 3 ArbZG" in w and w.startswith("01.06.2026: übersprungen") for w in result.warnings)
    assert db.query(TimeEntry).count() == 0


def test_confirm_counts_the_standing_entries_of_the_day(db, test_user, test_admin):
    _entry(db, test_user, time(6), time(12))
    result = _run(db, test_user, test_admin, [_row(time(12), time(18))])
    assert (result.imported, result.skipped) == (0, 1)
    assert db.query(TimeEntry).count() == 1


def test_exempt_person_is_not_limited(db, test_user, test_admin):
    test_user.exempt_from_arbzg = True
    db.commit()
    result = _run(db, test_user, test_admin, [_row(time(6), time(22))])
    assert result.imported == 1


# ── A1-02: Überschneidungen im Import ─────────────────────────────────────────

def test_preview_skips_a_row_overlapping_a_standing_entry(db, test_user):
    _entry(db, test_user, time(8), time(12))
    [row] = parse_xls(_xls((_mon(11), _mon(14))), test_user.id, db)
    assert row.arbzg_warnings == [
        PREFIX + "die Zeile überschneidet sich mit dem Eintrag 08:00–12:00 (Zeiteinträge "
        "einer Person dürfen sich nicht überschneiden)."
    ]
    assert row.has_conflict is False


def test_preview_skips_the_later_of_two_overlapping_rows(db, test_user):
    first, second = parse_xls(_xls((_mon(8), _mon(12)), (_mon(11), _mon(13))), test_user.id, db)
    assert not any(w.startswith(PREFIX) for w in first.arbzg_warnings)
    assert second.arbzg_warnings[0].startswith(PREFIX + "die Zeile überschneidet sich mit dem Eintrag 08:00–12:00")


def test_overwriting_the_matched_entry_is_no_overlap(db, test_user, test_admin):
    """Die Zeile, die einen Bestandseintrag (gleicher Beginn) überschreibt, prüft
    gegen die ÜBRIGEN Einträge — nicht gegen den, den sie ersetzt."""
    _entry(db, test_user, time(8), time(12))
    [row] = parse_xls(_xls((_mon(8), _mon(13))), test_user.id, db)
    assert row.has_conflict is True
    assert not any(w.startswith(PREFIX) for w in row.arbzg_warnings)
    result = _run(db, test_user, test_admin, [_row(time(8), time(13))], overwrite=True)
    assert result.overwritten == 1


def test_confirm_skips_overlapping_rows(db, test_user, test_admin):
    _entry(db, test_user, time(8), time(12))
    result = _run(db, test_user, test_admin, [_row(time(11), time(14)), _row(time(14), time(15))])
    assert (result.imported, result.skipped) == (1, 1)
    assert any("überschneidet sich mit dem Eintrag 08:00–12:00" in w for w in result.warnings)
    assert sorted((e.start_time, e.end_time) for e in db.query(TimeEntry).all()) == [
        (time(8), time(12)), (time(14), time(15))]


def test_confirm_skips_a_row_overlapping_an_earlier_row_of_the_file(db, test_user, test_admin):
    result = _run(db, test_user, test_admin, [_row(time(8), time(12)), _row(time(11), time(13))])
    assert (result.imported, result.skipped) == (1, 1)


# ── A1-10: Ruhezeit über die Zeitumstellung ───────────────────────────────────

def test_hours_between_respects_dst():
    # Sa 28.03.2026 20:00 → So 29.03. 07:00: real 10 h (Uhr springt 02→03).
    assert hours_between(date(2026, 3, 28), time(20), date(2026, 3, 29), time(7)) == 10.0
    # Sa 24.10.2026 20:00 → So 25.10. 07:00: real 12 h (Uhr springt 03→02).
    assert hours_between(date(2026, 10, 24), time(20), date(2026, 10, 25), time(7)) == 12.0
    assert hours_between(date(2026, 6, 1), time(20), date(2026, 6, 2), time(7)) == 11.0


def test_rest_time_report_counts_real_hours_over_dst(db, test_user):
    _entry(db, test_user, time(12), time(20), day=date(2026, 3, 28))
    _entry(db, test_user, time(7), time(12), day=date(2026, 3, 29))
    [v] = rest_time_service.check_rest_time_violations(db, test_user, 2026, 3)
    assert v["actual_rest_hours"] == 10.0
