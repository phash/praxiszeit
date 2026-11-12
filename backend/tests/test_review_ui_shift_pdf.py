"""Review 2026-11-11 (ui-24): PDF-Aushang — Unicode-Namen und Fußzeile mit Seitenzahl."""
from tests.test_shift_plan_pdf import _detail, _pdf_text, _render


def _slot(name, ws="Tresen", wd=0, start="08:00"):
    return {
        "id": f"s-{name}-{wd}-{start}", "workstation_name": ws, "weekday": wd,
        "start_time": start, "end_time": "12:00", "note": None,
        "assignments": [{"user_name": name}],
    }


def test_footer_has_plan_name_and_page_numbers_in_helvetica_case():
    buf = _render()
    text = _pdf_text(buf)
    assert "Normalzustand" in text
    assert "Seite 1 von 1" in text
    assert b"/FontFile2" not in buf.getvalue()  # nur Westeuropa → Helvetica, nichts eingebettet


def test_non_winansi_names_use_the_embedded_unicode_font():
    slots = [_slot("Małgorzata Kowalska"), _slot("Işıl Öz", wd=1), _slot("Дарья Петрова", wd=2)]
    buf = _render(slots=slots)
    raw = buf.getvalue()
    assert raw[:4] == b"%PDF"
    assert b"/FontFile2" in raw  # TrueType (DejaVu Sans, Subset) eingebettet


def test_multi_page_plan_numbers_every_page():
    # viele Zeilen → mehrere Seiten; „von y“ nennt die Gesamtzahl
    slots = [_slot(f"Person {i}", ws=f"Platz {i:02d}", wd=0) for i in range(60)]
    buf = _render(slots=slots)
    text = _pdf_text(buf)
    assert "Seite 1 von" in text and "Seite 2 von" in text
