"""#415 — Stundenänderungen in Monats- und Jahresberichten darstellen.

Modell (``working_hours_changes``), Endpoints, UI (WorkingHoursModal) und die
Soll/Ist-Berechnung (``get_weekly_hours_for_date`` in allen Per-Tag-Schleifen)
existierten bereits. Offen war Punkt 4 des Issues: die **Darstellung**.

Konkret war das §16-Dokument selbstwidersprüchlich — die Tageszeilen rechneten
historisch korrekt, die Kopfzeile/Spalte „Wochenstunden" zeigte aber den
AKTUELLEN Vertragswert. Wer im März von 20 h auf 30 h wechselte, bekam einen
Märzbericht mit „30,0 Wochenstunden" über Tageszeilen, die für die erste
Monatshälfte mit 20 h gerechnet hatten.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.models import TimeEntry, WorkingHoursChange
from app.services import calculation_service
from app.services.export_service import format_weekly_hours_history
from tests.conftest import DEFAULT_TENANT_ID


def _mk_change(db, user, effective_from, weekly_hours, note=None):
    c = WorkingHoursChange(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        effective_from=effective_from,
        weekly_hours=Decimal(str(weekly_hours)),
        note=note,
    )
    db.add(c)
    db.commit()
    return c


def _load_xlsx(bio: BytesIO):
    bio.seek(0)
    return load_workbook(BytesIO(bio.read()))


# ─────────────────────────────────────────────────────────────────────
# calculation_service.weekly_hours_segments — die eine Quelle
# ─────────────────────────────────────────────────────────────────────


class TestWeeklyHoursSegments:
    def test_no_changes_is_a_single_segment(self, db, test_user):
        segs = calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 3, 1), date(2026, 3, 31)
        )
        assert segs == [(date(2026, 3, 1), date(2026, 3, 31), Decimal("40.0"))]

    def test_change_inside_the_period_splits_it(self, db, test_user):
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        segs = calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 3, 1), date(2026, 3, 31)
        )
        assert segs == [
            (date(2026, 3, 1), date(2026, 3, 14), Decimal("40.0")),
            (date(2026, 3, 15), date(2026, 3, 31), Decimal("30.0")),
        ]

    def test_change_before_the_period_applies_for_the_whole_period(self, db, test_user):
        _mk_change(db, test_user, date(2026, 1, 1), 20)
        segs = calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 3, 1), date(2026, 3, 31)
        )
        assert segs == [(date(2026, 3, 1), date(2026, 3, 31), Decimal("20.0"))]

    def test_change_after_the_period_is_ignored(self, db, test_user):
        _mk_change(db, test_user, date(2026, 4, 1), 20)
        segs = calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 3, 1), date(2026, 3, 31)
        )
        assert segs == [(date(2026, 3, 1), date(2026, 3, 31), Decimal("40.0"))]

    def test_change_exactly_on_the_first_day_is_one_segment(self, db, test_user):
        _mk_change(db, test_user, date(2026, 3, 1), 25)
        segs = calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 3, 1), date(2026, 3, 31)
        )
        assert segs == [(date(2026, 3, 1), date(2026, 3, 31), Decimal("25.0"))]

    def test_multiple_changes_produce_multiple_segments(self, db, test_user):
        _mk_change(db, test_user, date(2026, 3, 10), 30)
        _mk_change(db, test_user, date(2026, 3, 20), 10)
        segs = calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 3, 1), date(2026, 3, 31)
        )
        assert [s[2] for s in segs] == [Decimal("40.0"), Decimal("30.0"), Decimal("10.0")]
        assert [s[0] for s in segs] == [date(2026, 3, 1), date(2026, 3, 10), date(2026, 3, 20)]

    def test_change_to_the_same_value_is_not_a_visible_change(self, db, test_user):
        """Ein Eintrag, der die Stundenzahl nicht aendert, darf im Bericht
        keine Pseudo-Aenderung erzeugen."""
        _mk_change(db, test_user, date(2026, 3, 15), 40)
        segs = calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 3, 1), date(2026, 3, 31)
        )
        assert segs == [(date(2026, 3, 1), date(2026, 3, 31), Decimal("40.0"))]

    def test_year_range_spans_all_changes(self, db, test_user):
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        _mk_change(db, test_user, date(2026, 9, 1), 20)
        segs = calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 1, 1), date(2026, 12, 31)
        )
        assert len(segs) == 3
        assert segs[-1] == (date(2026, 9, 1), date(2026, 12, 31), Decimal("20.0"))

    def test_empty_range_returns_nothing(self, db, test_user):
        assert calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 3, 31), date(2026, 3, 1)
        ) == []

    def test_preloaded_changes_match_the_db_path(self, db, test_user):
        """Der Preload-Pfad (Hot-Loop) muss byte-identisch zum DB-Pfad sein."""
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        preload = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == test_user.id
        ).all()
        assert calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 1, 1), date(2026, 12, 31), wh_changes=preload
        ) == calculation_service.weekly_hours_segments(
            db, test_user, date(2026, 1, 1), date(2026, 12, 31)
        )


# ─────────────────────────────────────────────────────────────────────
# Textdarstellung
# ─────────────────────────────────────────────────────────────────────


class TestFormatWeeklyHoursHistory:
    def test_single_segment_renders_empty(self):
        assert format_weekly_hours_history(
            [(date(2026, 3, 1), date(2026, 3, 31), Decimal("40.0"))]
        ) == ""

    def test_no_segments_render_empty(self):
        assert format_weekly_hours_history([]) == ""

    def test_one_change_is_named_with_date_and_value(self):
        text = format_weekly_hours_history([
            (date(2026, 3, 1), date(2026, 3, 14), Decimal("40.0")),
            (date(2026, 3, 15), date(2026, 3, 31), Decimal("30.0")),
        ])
        assert text == "ab 15.03.2026: 30,0 Std/Woche"

    def test_multiple_changes_are_joined(self):
        text = format_weekly_hours_history([
            (date(2026, 1, 1), date(2026, 3, 9), Decimal("40.0")),
            (date(2026, 3, 10), date(2026, 8, 31), Decimal("30.0")),
            (date(2026, 9, 1), date(2026, 12, 31), Decimal("20.5")),
        ])
        assert text == "ab 10.03.2026: 30,0 Std/Woche; ab 01.09.2026: 20,5 Std/Woche"


# ─────────────────────────────────────────────────────────────────────
# XLSX
# ─────────────────────────────────────────────────────────────────────


class TestXlsxMonthlyReportShowsHistory:
    def test_header_uses_hours_valid_at_month_start_not_current(self, db, test_user):
        """Kernregression: die Kopfzeile darf nicht den AKTUELLEN Vertragswert
        zeigen, waehrend die Tageszeilen historisch rechnen.

        Aufbau so, dass sich beide Werte unterscheiden: eine Aenderung VOR dem
        Monat setzt den zum 01.03. gueltigen Wert auf 40 h, eine zweite Aenderung
        im Monat bringt ihn auf 20 h — ``user.weekly_hours`` (der aktuelle
        Vertragswert) steht auf 20. Die alte Implementierung schrieb 20 in die
        Kopfzeile, obwohl die Tageszeilen der ersten Monatshaelfte mit 40 h
        rechneten.
        """
        from app.services.export_service import generate_monthly_report
        _mk_change(db, test_user, date(2026, 1, 1), 40)
        _mk_change(db, test_user, date(2026, 3, 15), 20)
        test_user.weekly_hours = Decimal("20.0")  # aktueller Vertragswert
        db.commit()

        wb = _load_xlsx(generate_monthly_report(db, 2026, 3))
        sheet = wb[f"{test_user.last_name} {test_user.first_name}"[:31]]
        assert sheet.cell(row=1, column=5).value == 40.0
        assert sheet.cell(row=1, column=6).value == "ab 15.03.2026: 20,0 Std/Woche"

    def test_header_carries_the_change_note(self, db, test_user):
        from app.services.export_service import generate_monthly_report
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        wb = _load_xlsx(generate_monthly_report(db, 2026, 3))
        sheet = wb[f"{test_user.last_name} {test_user.first_name}"[:31]]
        assert sheet.cell(row=1, column=6).value == "ab 15.03.2026: 30,0 Std/Woche"

    def test_no_change_leaves_the_note_cell_empty(self, db, test_user):
        from app.services.export_service import generate_monthly_report
        wb = _load_xlsx(generate_monthly_report(db, 2026, 3))
        sheet = wb[f"{test_user.last_name} {test_user.first_name}"[:31]]
        assert sheet.cell(row=1, column=5).value == 40.0
        assert not sheet.cell(row=1, column=6).value


class TestXlsxYearlyReportShowsHistory:
    def test_overview_has_a_changes_column(self, db, test_user):
        from app.services.export_service import generate_yearly_report
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        wb = _load_xlsx(generate_yearly_report(db, 2026))
        sheet = wb["Jahresübersicht"]
        headers = [sheet.cell(row=3, column=c).value for c in range(1, 13)]
        assert "Stundenänderungen" in headers
        col = headers.index("Stundenänderungen") + 1
        assert sheet.cell(row=4, column=col).value == "ab 15.03.2026: 30,0 Std/Woche"

    def test_overview_weekly_hours_is_the_year_start_value(self, db, test_user):
        """Wie beim Monatsbericht: die Spalte zeigt den zum 01.01. gueltigen
        Wert, nicht den heute im Vertrag stehenden."""
        from app.services.export_service import generate_yearly_report
        _mk_change(db, test_user, date(2025, 1, 1), 40)
        _mk_change(db, test_user, date(2026, 3, 15), 20)
        test_user.weekly_hours = Decimal("20.0")
        db.commit()
        wb = _load_xlsx(generate_yearly_report(db, 2026))
        sheet = wb["Jahresübersicht"]
        assert sheet.cell(row=4, column=2).value == 40.0
        assert sheet.cell(row=4, column=11).value == "ab 15.03.2026: 20,0 Std/Woche"

    def test_employee_sheet_names_the_change(self, db, test_user):
        from app.services.export_service import generate_yearly_report
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        wb = _load_xlsx(generate_yearly_report(db, 2026))
        sheet = wb[test_user.last_name[:20]]
        row2 = [sheet.cell(row=2, column=c).value for c in range(1, 11)]
        assert "Wochenstunden:" in row2
        assert any(v == "ab 15.03.2026: 30,0 Std/Woche" for v in row2)


class TestPdfMonthlyReportShowsHistory:
    def test_pdf_builds_with_a_change_in_the_period(self, db, test_user):
        """Der PDF-Meta-Text wird um die Aenderung ergaenzt — reportlab muss den
        laengeren Paragraph fehlerfrei bauen (unbalancierte Tags => 500)."""
        from app.services.export_service import generate_monthly_report_pdf
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        out = generate_monthly_report_pdf(db, 2026, 3)
        out.seek(0)
        assert out.read()[:5] == b"%PDF-"


# ─────────────────────────────────────────────────────────────────────
# ODS — Parität zu XLSX (CLAUDE.md: drei Exporter parieren)
# ─────────────────────────────────────────────────────────────────────


class TestOdsParity:
    def test_monthly_ods_carries_the_change_note(self, db, test_user):
        import zipfile
        from app.services.ods_export_service import generate_monthly_report
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        out = generate_monthly_report(db, 2026, 3)
        out.seek(0)
        content = zipfile.ZipFile(out).read("content.xml").decode("utf-8")
        assert "ab 15.03.2026: 30,0 Std/Woche" in content

    def test_yearly_ods_overview_has_the_changes_column(self, db, test_user):
        import zipfile
        from app.services.ods_export_service import generate_yearly_report
        _mk_change(db, test_user, date(2026, 3, 15), 30)
        out = generate_yearly_report(db, 2026)
        out.seek(0)
        content = zipfile.ZipFile(out).read("content.xml").decode("utf-8")
        assert "Stundenänderungen" in content
        assert "ab 15.03.2026: 30,0 Std/Woche" in content


# ─────────────────────────────────────────────────────────────────────
# API — der Monatsbericht transportiert die Änderungen in die UI
# ─────────────────────────────────────────────────────────────────────


class TestMonthlyReportApi:
    def test_report_carries_weekly_hours_changes(self, db, test_admin, test_user):
        from fastapi.testclient import TestClient
        from app.database import get_db
        from app.middleware.auth import get_current_user, require_admin
        from tests.test_endpoints import test_app

        _mk_change(db, test_user, date(2026, 3, 15), 30)

        def _override_db():
            yield db
        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = lambda: test_admin
        test_app.dependency_overrides[require_admin] = lambda: test_admin
        try:
            r = TestClient(test_app).get("/api/admin/reports/monthly?month=2026-03")
            assert r.status_code == 200, r.text
            row = [x for x in r.json() if x["user_id"] == str(test_user.id)][0]
            assert row["weekly_hours"] == 40.0
            assert row["weekly_hours_changes"] == [
                {"effective_from": "2026-03-15", "weekly_hours": 30.0}
            ]
        finally:
            test_app.dependency_overrides.clear()

    def test_report_without_changes_has_an_empty_list(self, db, test_admin, test_user):
        from fastapi.testclient import TestClient
        from app.database import get_db
        from app.middleware.auth import get_current_user, require_admin
        from tests.test_endpoints import test_app

        def _override_db():
            yield db
        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = lambda: test_admin
        test_app.dependency_overrides[require_admin] = lambda: test_admin
        try:
            r = TestClient(test_app).get("/api/admin/reports/monthly?month=2026-03")
            row = [x for x in r.json() if x["user_id"] == str(test_user.id)][0]
            assert row["weekly_hours_changes"] == []
        finally:
            test_app.dependency_overrides.clear()
