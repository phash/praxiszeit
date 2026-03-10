"""Tests für xls_import_service: Parsing, ArbZG-Checks, execute_import."""
import io
import pytest
from datetime import date, time, datetime

import xlrd
import xlwt  # xlwt für .xls-Erstellung in Tests (xlrd 1.2 liest, xlwt schreibt)

from app.models import TimeEntry
from app.services.xls_import_service import (
    _calc_break_minutes,
    _check_arbzg,
    _excel_serial_to_datetime,
    parse_xls,
    execute_import,
    ImportedEntry,
    MAX_FILE_SIZE_BYTES,
)


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _make_xls_bytes(rows: list[list]) -> bytes:
    """Erstellt eine minimale XLS-Datei mit Sheet 'Zeiterfassung'."""
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Zeiterfassung")
    date_style = xlwt.easyxf(num_format_str="DD.MM.YYYY HH:MM")
    for row_idx, row in enumerate(rows):
        for col_idx, val in enumerate(row):
            if isinstance(val, datetime):
                ws.write(row_idx, col_idx, val, date_style)
            else:
                ws.write(row_idx, col_idx, val)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _dt(year, month, day, hour, minute) -> datetime:
    return datetime(year, month, day, hour, minute)


def _make_data_row(ein_dt: datetime, aus_dt: datetime, notiz: str = ""):
    """Eine gültige Datenzeile für das Sheet."""
    return ["12.01", "Mo", "05:30", ein_dt, aus_dt, notiz]


# ── _calc_break_minutes ───────────────────────────────────────────────────────

def test_break_under_6h_is_0():
    assert _calc_break_minutes(time(8, 0), time(13, 59)) == 0


def test_break_exactly_6h_is_0():
    assert _calc_break_minutes(time(8, 0), time(14, 0)) == 0


def test_break_over_6h_is_30():
    assert _calc_break_minutes(time(8, 0), time(14, 1)) == 30


def test_break_exactly_9h_is_30():
    # Grenze: exakt 9h brutto → noch 30min (>9h = 45min)
    assert _calc_break_minutes(time(7, 0), time(16, 0)) == 30


def test_break_over_9h_is_45():
    assert _calc_break_minutes(time(7, 0), time(16, 1)) == 45


# ── _check_arbzg ─────────────────────────────────────────────────────────────

def test_no_warnings_for_normal_entry():
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 15), time(12, 45), 30, None)
    assert warnings == []


def test_warning_for_over_10h():
    # §3 prüft auf Netto-Stunden (brutto - pause).
    # 7:00–18:30 = 11.5h brutto, 45min Pause → 10.75h netto > 10h → §3-Warnung
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(18, 30), 45, None)
    assert any("§3" in w for w in warnings)


def test_warning_for_night_work():
    # 22:00–06:00 → Nachtarbeit
    warnings = _check_arbzg(date(2026, 1, 12), time(22, 0), time(6, 0), 0, None)
    assert any("§6" in w for w in warnings)


def test_warning_for_insufficient_rest():
    prev_end = datetime(2026, 1, 11, 23, 0)  # Vortag 23:00
    # Heutiger Start 8:00 → Ruhezeit 9h < 11h → Warnung
    warnings = _check_arbzg(date(2026, 1, 12), time(8, 0), time(14, 0), 30, prev_end)
    assert any("§5" in w for w in warnings)


def test_no_rest_warning_for_sufficient_rest():
    prev_end = datetime(2026, 1, 11, 18, 0)  # Vortag 18:00
    # Heutiger Start 7:15 → Ruhezeit 13.25h > 11h → keine Warnung
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 15), time(12, 45), 30, prev_end)
    assert not any("§5" in w for w in warnings)


def test_exempt_user_gets_no_warnings():
    # §18: exempt=True → alle Prüfungen übersprungen
    prev_end = datetime(2026, 1, 11, 23, 0)  # nur 9h Ruhezeit
    warnings = _check_arbzg(
        date(2026, 1, 12), time(7, 0), time(18, 30), 45, prev_end,
        exempt=True,
    )
    assert warnings == []


def test_night_worker_8h_warning():
    # §6 Abs. 2: is_night_worker=True → Warnung ab >8h netto statt >10h
    # 7:00–16:30 = 9.5h brutto, 45min Pause → 8.75h netto → über 8h-Limit
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(16, 30), 45, None, is_night_worker=True)
    assert any("§6 Abs. 2" in w for w in warnings)
    assert not any("§3" in w for w in warnings)  # §3 nicht zusätzlich


def test_night_worker_no_warning_under_8h():
    # 7:00–14:30 = 7.5h brutto, 30min Pause → 7h netto → unter 8h → keine §6-Abs.-2-Warnung
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(14, 30), 30, None, is_night_worker=True)
    assert not any("§6 Abs. 2" in w for w in warnings)


def test_non_night_worker_no_8h_warning():
    # Normaler User mit 9h netto → §3-Warnung, kein §6-Abs.-2
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(18, 30), 45, None, is_night_worker=False)
    assert any("§3" in w for w in warnings)
    assert not any("§6 Abs. 2" in w for w in warnings)


# ── parse_xls ────────────────────────────────────────────────────────────────

def test_parse_xls_extracts_data_rows(db, test_user):
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        ["W03", "", "", "", "", ""],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45)),
        _make_data_row(_dt(2026, 1, 14, 7, 15), _dt(2026, 1, 14, 14, 0)),
        ["Total:", "", "11:15", "", "", ""],
        ["", "", "", "", "", ""],
    ]
    xls_bytes = _make_xls_bytes(rows)
    entries = parse_xls(xls_bytes, test_user.id, db)
    assert len(entries) == 2
    assert entries[0].date == date(2026, 1, 12)
    assert entries[0].start_time == time(7, 15)
    assert entries[0].end_time == time(12, 45)


def test_parse_xls_calculates_breaks(db, test_user):
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 14, 0)),  # 6h45 > 6h → 30min
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].break_minutes == 30


def test_parse_xls_detects_conflict(db, test_user):
    # Vorhandenen Eintrag in DB anlegen
    existing = TimeEntry(
        user_id=test_user.id,
        date=date(2026, 1, 12),
        start_time=time(7, 15),
        end_time=time(12, 45),
        break_minutes=30,
    )
    db.add(existing)
    db.commit()

    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45)),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].has_conflict is True


def test_parse_xls_no_conflict_for_new_entry(db, test_user):
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45)),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].has_conflict is False


def test_parse_xls_wrong_sheet_raises(db, test_user):
    wb = xlwt.Workbook()
    wb.add_sheet("FalschesSheet")
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError, match="Sheet 'Zeiterfassung' nicht gefunden"):
        parse_xls(buf.getvalue(), test_user.id, db)


def test_parse_xls_empty_sheet_raises(db, test_user):
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        ["Total:", "", "00:00", "", "", ""],
    ]
    with pytest.raises(ValueError, match="Keine Datenzeilen"):
        parse_xls(_make_xls_bytes(rows), test_user.id, db)


def test_parse_xls_file_too_large_raises(db, test_user):
    with pytest.raises(ValueError, match="zu groß"):
        parse_xls(b"x" * (MAX_FILE_SIZE_BYTES + 1), test_user.id, db)


def test_parse_xls_includes_note(db, test_user):
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45), "Arzttermin"),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].note == "Arzttermin"


def test_parse_xls_empty_note_is_none(db, test_user):
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45), ""),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].note is None


def test_parse_xls_exempt_user_no_arbzg_warnings(db, test_user):
    # §18: exempt_from_arbzg=True → keine Warnungen, auch bei langer Arbeitszeit
    test_user.exempt_from_arbzg = True
    db.commit()
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 0), _dt(2026, 1, 12, 18, 30)),  # 10.75h netto
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].arbzg_warnings == []


def test_parse_xls_night_worker_gets_8h_warning(db, test_user):
    # §6 Abs. 2: is_night_worker=True → 8h-Warnung statt 10h
    test_user.is_night_worker = True
    db.commit()
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        # 7:00–16:30 = 9.5h brutto, 45min Pause → 8.75h netto → über 8h-Limit
        _make_data_row(_dt(2026, 1, 12, 7, 0), _dt(2026, 1, 12, 16, 30)),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert any("§6 Abs. 2" in w for w in entries[0].arbzg_warnings)


# ── execute_import ────────────────────────────────────────────────────────────

def _make_entries(n=1) -> list[ImportedEntry]:
    return [
        ImportedEntry(
            date=date(2026, 1, 12 + i),
            start_time=time(7, 15),
            end_time=time(12, 45),
            break_minutes=30,
            note=None,
            has_conflict=False,
            arbzg_warnings=[],
        )
        for i in range(n)
    ]


def test_execute_import_creates_entries(db, test_user, test_admin):
    entries = _make_entries(2)
    result = execute_import(test_user.id, entries, overwrite=False, db=db,
                            changed_by_id=test_admin.id, filename="test.xls")
    assert result.imported == 2
    assert result.skipped == 0
    assert result.overwritten == 0
    db_entries = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).all()
    assert len(db_entries) == 2


def test_execute_import_skips_conflict_without_overwrite(db, test_user, test_admin):
    # Vorhandener Eintrag
    existing = TimeEntry(user_id=test_user.id, date=date(2026, 1, 12),
                         start_time=time(7, 15), end_time=time(12, 45), break_minutes=30)
    db.add(existing)
    db.commit()

    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(13, 0), break_minutes=30, note=None,
                             has_conflict=True, arbzg_warnings=[])]
    result = execute_import(test_user.id, entries, overwrite=False, db=db,
                            changed_by_id=test_admin.id, filename="test.xls")
    assert result.skipped == 1
    assert result.imported == 0
    # Bestehender Eintrag unverändert
    db.refresh(existing)
    assert existing.end_time == time(12, 45)


def test_execute_import_overwrites_conflict(db, test_user, test_admin):
    existing = TimeEntry(user_id=test_user.id, date=date(2026, 1, 12),
                         start_time=time(7, 15), end_time=time(12, 45), break_minutes=30)
    db.add(existing)
    db.commit()

    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(13, 0), break_minutes=30, note="updated",
                             has_conflict=True, arbzg_warnings=[])]
    result = execute_import(test_user.id, entries, overwrite=True, db=db,
                            changed_by_id=test_admin.id, filename="test.xls")
    assert result.overwritten == 1
    db.refresh(existing)
    assert existing.end_time == time(13, 0)
    assert existing.note == "updated"


def test_execute_import_writes_audit_log(db, test_user, test_admin):
    from app.models import TimeEntryAuditLog
    entries = _make_entries(1)
    execute_import(test_user.id, entries, overwrite=False, db=db,
                   changed_by_id=test_admin.id, filename="test.xls")
    logs = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.user_id == test_user.id).all()
    # 1 create-Log + 1 summary-Log
    assert len(logs) == 2
    actions = {l.action for l in logs}
    assert "create" in actions
    assert "import" in actions


def test_execute_import_audit_log_for_overwrite(db, test_user, test_admin):
    """Jeder überschriebene Eintrag erhält einen eigenen Audit-Log-Eintrag mit alten Werten."""
    from app.models import TimeEntryAuditLog
    existing = TimeEntry(user_id=test_user.id, date=date(2026, 1, 12),
                         start_time=time(7, 15), end_time=time(12, 45), break_minutes=30,
                         note="alt")
    db.add(existing)
    db.commit()

    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(13, 0), break_minutes=30, note="neu",
                             has_conflict=True, arbzg_warnings=[])]
    execute_import(test_user.id, entries, overwrite=True, db=db,
                   changed_by_id=test_admin.id, filename="test.xls")

    update_logs = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == test_user.id,
        TimeEntryAuditLog.action == "update",
    ).all()
    assert len(update_logs) == 1
    assert update_logs[0].old_end_time == time(12, 45)  # alter Wert gespeichert
    assert update_logs[0].old_note == "alt"
    assert update_logs[0].new_note == "neu"


def test_execute_import_returns_arbzg_warnings(db, test_user, test_admin):
    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(12, 45), break_minutes=30, note=None,
                             has_conflict=False, arbzg_warnings=["§3 ArbZG: Test-Warnung"])]
    result = execute_import(test_user.id, entries, overwrite=False, db=db,
                            changed_by_id=test_admin.id, filename="test.xls")
    assert len(result.warnings) == 1
    assert "§3" in result.warnings[0]
