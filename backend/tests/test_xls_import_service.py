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
from tests.conftest import DEFAULT_TENANT_ID


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
    """Prüft dass unter 6h Arbeitszeit keine Pflichtpause berechnet wird — §4 ArbZG."""
    assert _calc_break_minutes(time(8, 0), time(13, 59)) == 0


def test_break_exactly_6h_is_0():
    """Prüft dass exakt 6h Arbeitszeit noch keine Pflichtpause ausloest — §4 ArbZG Grenze."""
    assert _calc_break_minutes(time(8, 0), time(14, 0)) == 0


def test_break_over_6h_is_30():
    """Prüft dass ueber 6h Arbeitszeit 30min Pflichtpause berechnet wird — §4 Abs. 1 ArbZG."""
    assert _calc_break_minutes(time(8, 0), time(14, 1)) == 30


def test_break_exactly_9h_is_30():
    """Prüft dass exakt 9h Arbeitszeit noch 30min Pause ergibt — §4 Abs. 1 ArbZG Grenze."""
    assert _calc_break_minutes(time(7, 0), time(16, 0)) == 30


def test_break_over_9h_is_45():
    """Prüft dass ueber 9h Arbeitszeit 45min Pflichtpause berechnet wird — §4 Abs. 2 ArbZG."""
    assert _calc_break_minutes(time(7, 0), time(16, 1)) == 45


# ── _check_arbzg ─────────────────────────────────────────────────────────────

def test_no_warnings_for_normal_entry():
    """Prüft dass ein normaler Arbeitstag keine ArbZG-Warnungen erzeugt."""
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 15), time(12, 45), 30, None)
    assert warnings == []


def test_warning_for_over_10h():
    """Prüft dass ueber 10h Netto-Arbeitszeit eine §3 ArbZG-Warnung erzeugt — Hoechstarbeitszeit."""
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(18, 30), 45, None)
    assert any("§3" in w for w in warnings)


def test_warning_for_night_work():
    """Prüft dass Nachtarbeit (22:00-06:00) eine §6 ArbZG-Warnung erzeugt."""
    warnings = _check_arbzg(date(2026, 1, 12), time(22, 0), time(6, 0), 0, None)
    assert any("§6" in w for w in warnings)


def test_warning_for_insufficient_rest():
    """Prüft dass bei unter 11h Ruhezeit eine §5 ArbZG-Warnung erzeugt wird — Mindestruhezeit."""
    prev_end = datetime(2026, 1, 11, 23, 0)  # Vortag 23:00
    warnings = _check_arbzg(date(2026, 1, 12), time(8, 0), time(14, 0), 30, prev_end)
    assert any("§5" in w for w in warnings)


def test_no_rest_warning_for_sufficient_rest():
    """Prüft dass bei ausreichender Ruhezeit (>11h) keine §5-Warnung erzeugt wird."""
    prev_end = datetime(2026, 1, 11, 18, 0)  # Vortag 18:00
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 15), time(12, 45), 30, prev_end)
    assert not any("§5" in w for w in warnings)


def test_exempt_user_gets_no_warnings():
    """Prüft dass §18 ArbZG-befreite User keine Warnungen erhalten — leitende Angestellte."""
    prev_end = datetime(2026, 1, 11, 23, 0)
    warnings = _check_arbzg(
        date(2026, 1, 12), time(7, 0), time(18, 30), 45, prev_end,
        exempt=True,
    )
    assert warnings == []


def test_night_worker_8h_warning():
    """Prüft dass Nachtarbeitnehmer ab 8h Netto §6 Abs. 2 ArbZG-Warnung erhalten statt §3."""
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(16, 30), 45, None, is_night_worker=True)
    assert any("§6 Abs. 2" in w for w in warnings)
    assert not any("§3" in w for w in warnings)


def test_night_worker_no_warning_under_8h():
    """Prüft dass Nachtarbeitnehmer unter 8h keine §6 Abs. 2-Warnung erhalten."""
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(14, 30), 30, None, is_night_worker=True)
    assert not any("§6 Abs. 2" in w for w in warnings)


def test_non_night_worker_no_8h_warning():
    """Prüft dass normale User die §3-Warnung erhalten, nicht §6 Abs. 2 — kein Nachtarbeitnehmer."""
    warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(18, 30), 45, None, is_night_worker=False)
    assert any("§3" in w for w in warnings)
    assert not any("§6 Abs. 2" in w for w in warnings)


# ── parse_xls ────────────────────────────────────────────────────────────────

def test_parse_xls_extracts_data_rows(db, test_user):
    """Prüft dass parse_xls Datenzeilen korrekt extrahiert und Header/Footer ignoriert."""
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
    """Prüft dass parse_xls automatisch Pausen nach §4 ArbZG berechnet."""
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 14, 0)),  # 6h45 > 6h → 30min
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].break_minutes == 30


def test_parse_xls_detects_conflict(db, test_user):
    """Prüft dass Konflikte mit bestehenden DB-Eintraegen erkannt werden — Duplikat-Schutz."""
    existing = TimeEntry(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
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
    """Prüft dass neue Eintraege ohne DB-Duplikat kein Konflikt-Flag erhalten."""
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45)),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].has_conflict is False


def test_parse_xls_wrong_sheet_raises(db, test_user):
    """Prüft dass fehlendes Sheet 'Zeiterfassung' einen ValueError ausloest."""
    wb = xlwt.Workbook()
    wb.add_sheet("FalschesSheet")
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError, match="Sheet 'Zeiterfassung' nicht gefunden"):
        parse_xls(buf.getvalue(), test_user.id, db)


def test_parse_xls_empty_sheet_raises(db, test_user):
    """Prüft dass Sheet ohne Datenzeilen einen ValueError ausloest."""
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        ["Total:", "", "00:00", "", "", ""],
    ]
    with pytest.raises(ValueError, match="Keine Datenzeilen"):
        parse_xls(_make_xls_bytes(rows), test_user.id, db)


def test_parse_xls_file_too_large_raises(db, test_user):
    """Prüft dass zu grosse Dateien abgelehnt werden — DoS-Schutz."""
    with pytest.raises(ValueError, match="zu groß"):
        parse_xls(b"x" * (MAX_FILE_SIZE_BYTES + 1), test_user.id, db)


def test_parse_xls_includes_note(db, test_user):
    """Prüft dass Tagesnotizen aus der XLS-Datei korrekt uebernommen werden."""
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45), "Arzttermin"),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].note == "Arzttermin"


def test_parse_xls_empty_note_is_none(db, test_user):
    """Prüft dass leere Notizen als None gespeichert werden — kein Leerstring in DB."""
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45), ""),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].note is None


def test_parse_xls_exempt_user_no_arbzg_warnings(db, test_user):
    """Prüft dass §18 ArbZG-befreite User beim Import keine Warnungen erhalten."""
    test_user.exempt_from_arbzg = True
    db.commit()
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 0), _dt(2026, 1, 12, 18, 30)),  # 10.75h netto
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert entries[0].arbzg_warnings == []


def test_parse_xls_night_worker_gets_8h_warning(db, test_user):
    """Prüft dass Nachtarbeitnehmer beim Import die §6 Abs. 2 ArbZG 8h-Warnung erhalten."""
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
    """Prüft dass execute_import neue Eintraege in der DB anlegt — Basis-Importfunktion."""
    entries = _make_entries(2)
    result = execute_import(test_user.id, entries, overwrite=False, db=db,
                            changed_by_id=test_admin.id, filename="test.xls",
                            tenant_id=DEFAULT_TENANT_ID)
    assert result.imported == 2
    assert result.skipped == 0
    assert result.overwritten == 0
    db_entries = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).all()
    assert len(db_entries) == 2


def test_execute_import_skips_end_before_start(db, test_user, test_admin):
    """Guard: a row with end_time <= start_time (overnight / corrupt source) must
    NOT be silently imported. net_hours floors a negative duration to 0, so such a
    row would otherwise persist as a phantom 0h entry — wrong pay AND it disables
    the §3 daily-hours cap. The system's invariant is end > start (enforced on the
    interactive paths); the importer is the only write path that bypassed it, and
    /confirm even trusts client-supplied entries. Such rows are skipped + warned."""
    entries = [
        ImportedEntry(date=date(2026, 1, 12), start_time=time(8, 0), end_time=time(16, 0),
                      break_minutes=30, note="valid", has_conflict=False, arbzg_warnings=[]),
        ImportedEntry(date=date(2026, 1, 13), start_time=time(15, 0), end_time=time(7, 0),
                      break_minutes=0, note="overnight", has_conflict=False, arbzg_warnings=[]),
    ]
    result = execute_import(test_user.id, entries, overwrite=False, db=db,
                            changed_by_id=test_admin.id, filename="test.xls",
                            tenant_id=DEFAULT_TENANT_ID)
    assert result.imported == 1, "only the valid entry is imported"
    assert result.skipped == 1, "the end<=start entry is skipped"
    assert any("Endzeit" in w for w in result.warnings), "skip is surfaced as a warning"
    # the invalid row must NOT have been persisted as a 0h phantom entry
    bad = db.query(TimeEntry).filter(
        TimeEntry.user_id == test_user.id, TimeEntry.date == date(2026, 1, 13)
    ).all()
    assert bad == [], "no phantom entry for the end<=start row"


def test_execute_import_skips_conflict_without_overwrite(db, test_user, test_admin):
    """Prüft dass Konflikte ohne overwrite=True uebersprungen werden — bestehende Daten geschuetzt."""
    existing = TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 1, 12),
                         start_time=time(7, 15), end_time=time(12, 45), break_minutes=30)
    db.add(existing)
    db.commit()

    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(13, 0), break_minutes=30, note=None,
                             has_conflict=True, arbzg_warnings=[])]
    result = execute_import(test_user.id, entries, overwrite=False, db=db,
                            changed_by_id=test_admin.id, filename="test.xls",
                            tenant_id=DEFAULT_TENANT_ID)
    assert result.skipped == 1
    assert result.imported == 0
    # Bestehender Eintrag unverändert
    db.refresh(existing)
    assert existing.end_time == time(12, 45)


def test_execute_import_overwrites_conflict(db, test_user, test_admin):
    """Prüft dass Konflikte mit overwrite=True ueberschrieben werden — expliziter Admin-Wunsch."""
    existing = TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 1, 12),
                         start_time=time(7, 15), end_time=time(12, 45), break_minutes=30)
    db.add(existing)
    db.commit()

    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(13, 0), break_minutes=30, note="updated",
                             has_conflict=True, arbzg_warnings=[])]
    result = execute_import(test_user.id, entries, overwrite=True, db=db,
                            changed_by_id=test_admin.id, filename="test.xls",
                            tenant_id=DEFAULT_TENANT_ID)
    assert result.overwritten == 1
    db.refresh(existing)
    assert existing.end_time == time(13, 0)
    assert existing.note == "updated"


def test_execute_import_overwrite_preserves_raw_stamps(db, test_user, test_admin):
    """Audit R3/§16: Beim Overwrite müssen die Roh-Stempel (raw_start/raw_end)
    des Import-Eintrags auf den bestehenden Eintrag übernommen werden — sonst
    geht der §16-Nachweis der tatsächlichen Anwesenheit beim Überschreiben
    verloren (gekappter Wert bleibt, Rohwert verschwindet)."""
    existing = TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 1, 12),
                         start_time=time(7, 15), end_time=time(12, 45), break_minutes=30,
                         raw_start_time=None, raw_end_time=None)
    db.add(existing)
    db.commit()

    # Import-Eintrag mit gekapptem end + bewahrtem Roh-Ende (z.B. Soll-Fenster-Kappung).
    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(16, 0), break_minutes=30, note="ow",
                             has_conflict=True, arbzg_warnings=[],
                             raw_start_time=time(6, 30), raw_end_time=time(18, 0))]
    execute_import(test_user.id, entries, overwrite=True, db=db,
                   changed_by_id=test_admin.id, filename="test.xls",
                   tenant_id=DEFAULT_TENANT_ID)
    db.refresh(existing)
    assert existing.raw_start_time == time(6, 30)
    assert existing.raw_end_time == time(18, 0)


def test_execute_import_writes_audit_log(db, test_user, test_admin):
    """Prüft dass Import Audit-Logs schreibt — Nachvollziehbarkeit gemaess DSGVO Art. 5."""
    from app.models import TimeEntryAuditLog
    entries = _make_entries(1)
    execute_import(test_user.id, entries, overwrite=False, db=db,
                   changed_by_id=test_admin.id, filename="test.xls",
                   tenant_id=DEFAULT_TENANT_ID)
    logs = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.user_id == test_user.id).all()
    # 1 create-Log + 1 summary-Log
    assert len(logs) == 2
    actions = {l.action for l in logs}
    assert "create" in actions
    assert "import" in actions


def test_execute_import_audit_log_for_overwrite(db, test_user, test_admin):
    """Jeder überschriebene Eintrag erhält einen eigenen Audit-Log-Eintrag mit alten Werten."""
    from app.models import TimeEntryAuditLog
    existing = TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 1, 12),
                         start_time=time(7, 15), end_time=time(12, 45), break_minutes=30,
                         note="alt")
    db.add(existing)
    db.commit()

    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(13, 0), break_minutes=30, note="neu",
                             has_conflict=True, arbzg_warnings=[])]
    execute_import(test_user.id, entries, overwrite=True, db=db,
                   changed_by_id=test_admin.id, filename="test.xls",
                   tenant_id=DEFAULT_TENANT_ID)

    update_logs = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == test_user.id,
        TimeEntryAuditLog.action == "update",
    ).all()
    assert len(update_logs) == 1
    assert update_logs[0].old_end_time == time(12, 45)  # alter Wert gespeichert
    assert update_logs[0].old_note == "alt"
    assert update_logs[0].new_note == "neu"


def test_execute_import_returns_arbzg_warnings(db, test_user, test_admin):
    """Prüft dass ArbZG-Warnungen im Import-Ergebnis zurueckgegeben werden."""
    entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                             end_time=time(12, 45), break_minutes=30, note=None,
                             has_conflict=False, arbzg_warnings=["§3 ArbZG: Test-Warnung"])]
    result = execute_import(test_user.id, entries, overwrite=False, db=db,
                            changed_by_id=test_admin.id, filename="test.xls",
                            tenant_id=DEFAULT_TENANT_ID)
    assert len(result.warnings) == 1
    assert "§3" in result.warnings[0]


# ── work_window clamp im XLS-Import ─────────────────────────────────────────

def test_parse_xls_clamps_early_start_to_soll_window(db, test_user):
    """#201: Zeilen vor dem Soll-Fenster (inkl. Puffer) werden auf Fenster-Beginn minus
    Puffer gekappt; raw_start_time bewahrt den Rohwert."""
    # Montag 2026-01-12, Soll-Beginn 08:00
    test_user.scheduled_start_monday = time(8, 0)
    test_user.scheduled_end_monday = time(17, 0)
    db.commit()

    # Importzeile: 07:00 Uhr — 15 min Puffer → floor = 07:45
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 0), _dt(2026, 1, 12, 16, 0)),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert len(entries) == 1
    entry = entries[0]
    # Effektive Startzeit = 07:45 (Soll 08:00 minus 15 min Puffer)
    assert entry.start_time == time(7, 45), f"expected 07:45 but got {entry.start_time}"
    # Rohwert bewahrt
    assert entry.raw_start_time == time(7, 0), f"expected raw 07:00 but got {entry.raw_start_time}"
    # Ende unverändert (innerhalb des Fensters)
    assert entry.end_time == time(16, 0)
    assert entry.raw_end_time is None


def test_execute_import_stores_raw_start_time_in_db(db, test_user, test_admin):
    """#201: execute_import schreibt raw_start_time/-end_time in den TimeEntry."""
    test_user.scheduled_start_monday = time(8, 0)
    test_user.scheduled_end_monday = time(17, 0)
    db.commit()

    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 7, 0), _dt(2026, 1, 12, 16, 0)),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    execute_import(
        test_user.id, entries, overwrite=False, db=db,
        changed_by_id=test_admin.id, filename="test.xls",
        tenant_id=DEFAULT_TENANT_ID,
    )
    db_entry = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).first()
    assert db_entry is not None
    assert db_entry.start_time == time(7, 45)
    assert db_entry.raw_start_time == time(7, 0)
    assert db_entry.raw_end_time is None


# ── §3/§4 Tagesaggregation im Import (Fix A) ─────────────────────────────────

def test_parse_xls_two_batch_rows_same_day_trigger_s4_warning(db, test_user):
    """Fix A: Zwei Import-Zeilen am selben Tag, die einzeln <6h sind, aber zusammen >6h ohne
    ausreichende Pause bilden, müssen eine §4-ArbZG-Warnung auslösen.
    Vor dem Fix: keine Warnung (jede Zeile wurde isoliert geprüft).
    Nach dem Fix: §4-Warnung an der zweiten Zeile (Tages-Aggregation).
    """
    # 08:00–11:00 = 3h, 11:30–15:00 = 3,5h → Zusammen 6,5h netto (Lücke 30 min < min. 30 min
    # Pflichtpause für >6h?). Lücke von 30 min zwischen 11:00 und 11:30 ist genau 30 min
    # → Grenzfall: Pause >= 30 min → kein §4-Fehler. Um sicher eine Warnung zu erzeugen,
    # nutzen wir eine Lücke von 0 min: Zwei Blöcke 08:00–11:00 und 11:00–15:30 → 7,5h netto,
    # keine deklarierten Pausen, keine Lücke → Lücke 0 min → §4 Warnung.
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 8, 0), _dt(2026, 1, 12, 11, 0)),   # 3h, break=0
        _make_data_row(_dt(2026, 1, 12, 11, 0), _dt(2026, 1, 12, 15, 30)), # 4,5h, break=0
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert len(entries) == 2

    # Erster Eintrag: 3h, einzeln kein §4-Problem
    assert not any("§4" in w for w in entries[0].arbzg_warnings), (
        f"Erster Eintrag soll keine §4-Warnung haben: {entries[0].arbzg_warnings}"
    )

    # Zweiter Eintrag: bei Tagesaggregation zusammen 7,5h netto, 0 min Pause → §4-Warnung
    all_warnings_day = entries[0].arbzg_warnings + entries[1].arbzg_warnings
    assert any("§4" in w for w in all_warnings_day), (
        f"Tages-§4-Warnung erwartet, aber nicht gefunden. "
        f"Warnungen Eintrag 0: {entries[0].arbzg_warnings} | "
        f"Warnungen Eintrag 1: {entries[1].arbzg_warnings}"
    )


def test_parse_xls_two_batch_rows_same_day_no_spurious_s4_warning(db, test_user):
    """Fix A Negativ-Test: Zwei Import-Zeilen am selben Tag mit ausreichender Pause lösen
    keine §4-Warnung aus."""
    # 08:00–11:00 = 3h, 11:30–14:30 = 3h → Zusammen 6h netto, 30 min Lücke → kein §4-Problem
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 12, 8, 0), _dt(2026, 1, 12, 11, 0)),
        _make_data_row(_dt(2026, 1, 12, 11, 30), _dt(2026, 1, 12, 14, 30)),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    all_s4 = [w for e in entries for w in e.arbzg_warnings if "§4" in w]
    assert all_s4 == [], f"Keine §4-Warnung erwartet, aber erhalten: {all_s4}"


def test_parse_xls_db_entry_plus_import_same_day_trigger_s4_warning(db, test_user):
    """Fix A: Ein vorhandener DB-Eintrag + ein importierter Eintrag am selben Tag ergeben
    zusammen >6h ohne ausreichende Pause → §4-Warnung im Import-Eintrag."""
    # DB-Eintrag: 08:00–11:00 = 3h
    existing = TimeEntry(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=date(2026, 1, 14),
        start_time=time(8, 0),
        end_time=time(11, 0),
        break_minutes=0,
    )
    db.add(existing)
    db.commit()

    # Import-Zeile am selben Tag: 11:00–15:30 = 4,5h, keine Pause, keine Lücke → 7,5h gesamt
    rows = [
        ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
        _make_data_row(_dt(2026, 1, 14, 11, 0), _dt(2026, 1, 14, 15, 30)),
    ]
    entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
    assert len(entries) == 1
    assert any("§4" in w for w in entries[0].arbzg_warnings), (
        f"§4-Warnung erwartet (DB+Import), aber nicht gefunden: {entries[0].arbzg_warnings}"
    )
