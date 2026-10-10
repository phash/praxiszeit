"""Spec 2026-10-08, 15.1 / 17.6 (PR2): Spalte „Nicht angerechnet (Min)" —
angehängt (XLSX/ODS Spalte 13, PDF Spalte 12), Wert je Tag = Σ
not_credited_minutes (Lücke + Hülle, P19), Summenzeile = Σ Zeitraum."""
from datetime import date, time

import pytest

from app.models import TimeEntry
from app.services import export_service, ods_export_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_497_498_export_day_rows import (
    MONTH, XLSX_HEADERS_1_TO_10, YEAR, _as_date, _minutes, _ods_day_rows, _ods_header,
    _ods_rows, _ods_table, _pdf_main_table, _xlsx_employee_sheet,
)

K7_DAY = date(2026, 9, 7)       # Mo
PLAIN_DAY = date(2026, 9, 8)    # Di — ohne Kappung
EMPTY_DAY = date(2026, 9, 9)    # Mi — nichts erfasst
K15_DAY = date(2026, 9, 14)     # Mo — automatisch geschlossen
HEADER = "Nicht angerechnet (Min)"


@pytest.fixture
def month(db, test_user):
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=K7_DAY,
                     start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                     raw_end_time=time(19), break_minutes=0, uncredited_minutes=150,
                     clamp_grace_minutes=15))
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=PLAIN_DAY,
                     start_time=time(8), end_time=time(16, 30), break_minutes=30))
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=K15_DAY,
                     start_time=time(8), end_time=time(18, 15), raw_end_time=time(23, 59),
                     break_minutes=0, uncredited_minutes=150, auto_closed=True))
    db.commit()
    return test_user


def _xlsx_rows(sheet):
    rows = {}
    for r in sheet.iter_rows(min_col=1, max_col=13, values_only=True):
        d = _as_date(r[0])
        if isinstance(d, date):
            rows[d] = list(r)
    return rows


def _label_value(sheet, label):
    for r in sheet.iter_rows(min_col=1, max_col=2, values_only=True):
        if r[0] == label:
            return r[1]
    raise AssertionError(f"Zeile {label!r} fehlt")


@pytest.mark.parametrize("yearly", [False, True])
def test_xlsx_column_13_values_and_sum(db, month, yearly):
    if yearly:
        bio = export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID)
        header_row, label = 3, "Nicht angerechnet (Min) Jahr:"
    else:
        bio = export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
        header_row, label = 4, "Nicht angerechnet (Min) Monat:"
    sheet = _xlsx_employee_sheet(bio, month, yearly=yearly)
    headers = [sheet.cell(row=header_row, column=c).value for c in range(1, 14)]
    assert headers[:10] == XLSX_HEADERS_1_TO_10, "Spalten 1–10 bleiben, wo sie sind"
    assert headers[10:] == ["Unterbrechung (Min)", "Arbeitsblöcke", HEADER]
    rows = _xlsx_rows(sheet)
    assert rows[K7_DAY][12] == 240      # K7: Lücke 150 + Hülle 90
    assert rows[K15_DAY][12] == 150     # K15: Endseite 23:59 zählt nicht (P18)
    assert rows[PLAIN_DAY][12] == 0
    assert rows[EMPTY_DAY][12] is None
    assert _label_value(sheet, label) == 390


def test_xlsx_row_rule_subtracts_the_gap_share_only(db, month):
    """15.1: Bis − Von − Pause − Unterbrechung − Σ uncredited = Netto. Mit der
    Spalte 13 (240, enthält die Hülle) ginge die Zeile NICHT auf."""
    sheet = _xlsx_employee_sheet(export_service.generate_monthly_report(
        db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID), month)
    r = _xlsx_rows(sheet)[K7_DAY]
    von, bis, pause, netto, gap = r[2], r[3], r[4], r[5], r[10]
    assert (_minutes(bis) - _minutes(von) - pause - gap - 150) / 60 == pytest.approx(netto, abs=0.01)
    assert (_minutes(bis) - _minutes(von) - pause - gap - r[12]) / 60 != pytest.approx(netto, abs=0.01)


@pytest.mark.parametrize("yearly", [False, True])
def test_ods_column_13(db, month, yearly):
    if yearly:
        bio = ods_export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID)
    else:
        bio = ods_export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    table = _ods_table(bio, f"{month.last_name} {month.first_name}"[:31])
    header = _ods_header(table)
    assert header[:10] == XLSX_HEADERS_1_TO_10
    assert header[10:13] == ["Unterbrechung (Min)", "Arbeitsblöcke", HEADER]
    rows = _ods_day_rows(table)
    assert rows[K7_DAY][12][1] == "240"
    assert rows[K15_DAY][12][1] == "150"
    assert rows[PLAIN_DAY][12][1] == "0"


def test_ods_monthly_sum_row(db, month):
    table = _ods_table(ods_export_service.generate_monthly_report(
        db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID), f"{month.last_name} {month.first_name}"[:31])
    row = next(r for r in _ods_rows(table) if r and r[0][0] == "Nicht angerechnet (Min) Monat:")
    assert row[1][1] == "390"


def test_ods_yearly_sum_rows(db, month):
    """Gesamtreview PR2 (Fund 12): das ODS-Jahresblatt endete ohne Summen —
    das XLSX-Jahresblatt desselben Berichts trägt „Nicht angerechnet (Min)
    Jahr:" und „Nachtarbeitstage (§6 ArbZG):" (Spec 15.1/17.6 Parität)."""
    # Ein Nachtdienst im März (00:00–03:00 = 3 h Nachtzeit, §2 Abs. 4 ArbZG).
    db.add(TimeEntry(user_id=month.id, tenant_id=DEFAULT_TENANT_ID, date=date(YEAR, 3, 3),
                     start_time=time(0), end_time=time(3), break_minutes=0))
    db.commit()
    table = _ods_table(ods_export_service.generate_yearly_report(
        db, YEAR, tenant_id=DEFAULT_TENANT_ID), f"{month.last_name} {month.first_name}"[:31])
    rows = _ods_rows(table)
    year_row = next(r for r in rows if r and r[0][0] == "Nicht angerechnet (Min) Jahr:")
    assert year_row[1][1] == "390"
    night_row = next(r for r in rows if r and r[0][0] == "Nachtarbeitstage (§6 ArbZG):")
    assert night_row[1][1] == "1"
    # Parität zum XLSX-Jahresblatt desselben Berichts.
    sheet = _xlsx_employee_sheet(export_service.generate_yearly_report(
        db, YEAR, tenant_id=DEFAULT_TENANT_ID), month, yearly=True)
    assert _label_value(sheet, "Nicht angerechnet (Min) Jahr:") == 390
    assert _label_value(sheet, "Nachtarbeitstage (§6 ArbZG):") == 1


def test_pdf_last_column(db, month, monkeypatch):
    header, rows = _pdf_main_table(db, monkeypatch)
    assert len(header) == 12
    assert header[-1] == "Nicht angerechnet (Min)"
    assert header.index("Unterbr. (Min)") == 5, "Spalte 6 bleibt die Unterbrechung"
    assert rows[K7_DAY][-1] == "240"
    assert rows[K15_DAY][-1] == "150"
    assert rows[EMPTY_DAY][-1] == ""


def test_day_credit_minutes_helper():
    k7 = TimeEntry(start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                   raw_end_time=time(19), break_minutes=0, uncredited_minutes=150)
    plain = TimeEntry(start_time=time(8), end_time=time(12), break_minutes=0, uncredited_minutes=0)
    assert export_service.day_credit_minutes([k7, plain]) == export_service.DayCredit(240, 150)
    assert export_service.day_credit_minutes([]) == export_service.DayCredit(None, 0)


def test_pdf_summary_row(db, month, monkeypatch):
    """Summenzeile „Nicht angerechnet (Min):" im PDF-Zusammenfassungsblock."""
    import reportlab.platypus as rp
    captured = []
    orig = rp.Table

    class _Spy(orig):
        def __init__(self, data, *a, **kw):
            captured.append(data)
            super().__init__(data, *a, **kw)

    monkeypatch.setattr(rp, "Table", _Spy)
    export_service.generate_monthly_report_pdf(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)

    def _txt(c):
        return getattr(c, "text", c if isinstance(c, str) else "")

    summary = next(t for t in captured if t and _txt(t[0][0]) == "Zusammenfassung")
    values = {_txt(r[0]): _txt(r[1]) for r in summary[1:]}
    assert values["Nicht angerechnet (Min):"] == "390"


def test_pdf_header_two_lines_and_width_267mm(db, month, monkeypatch):
    """Spec 15.1: Kopf zweizeilig „Nicht angerechnet / (Min)", Spaltenbreiten
    neu auf 267 mm (A4 quer abzüglich Ränder). Bei 18 mm brach reportlab den
    Kopf dreizeilig um („Nicht" / „angerechnet" / „(Min)")."""
    import reportlab.platypus as rp
    from reportlab.lib.units import mm
    captured = []
    orig = rp.Table

    class _Spy(orig):
        def __init__(self, data, *a, **kw):
            captured.append((data, kw.get("colWidths")))
            super().__init__(data, *a, **kw)

    monkeypatch.setattr(rp, "Table", _Spy)
    export_service.generate_monthly_report_pdf(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    data, widths = next((d, w) for d, w in captured
                        if d and getattr(d[0][0], "text", None) == "Datum")
    assert len(widths) == 12
    assert sum(widths) == pytest.approx(267 * mm)
    head = data[0][-1]
    head.wrap(widths[-1] - 6, 1000)  # LEFT-/RIGHTPADDING je 3 pt
    assert len(head.blPara.lines) == 2
