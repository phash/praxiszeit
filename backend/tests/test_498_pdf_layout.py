"""#498 / Gesamtreview 1.20 (B7): Optik der PDF-Ausdrucke.

Die Monats-PDF und der Schichtplan-Aushang wurden mit geteilten Diensten,
mehrzeiligem Von/Bis, Unterbrechung, nicht angerechneter Zeit, langen
Freitexten und vollen Einteilungen gerendert und angesehen. Gefunden:

* **Monats-PDF, Zeilenhöhe:** reportlab teilt eine Tabellenzeile ohne
  ``splitInRow`` nicht über einen Seitenumbruch. Die Spalte „Bemerkung“ sammelt
  die Notizen ALLER Einträge des Tages (``note`` ist unbegrenzt, der §10-Grund
  bis 2000 Zeichen) — wird die Zeile höher als die Seite, wirft ``doc.build``
  eine ``LayoutError``: HTTP 500 für den Monatsbericht der GANZEN Praxis, nicht
  nur für die eine Person (derselbe Fehler wie C-1 im Schichtplan-Aushang).
* **Monats-PDF, Seitenumbruch:** geteilte Dienste machen die Tageszeilen
  zwei- bis dreizeilig, die Tabelle läuft öfter auf eine zweite Seite. Die
  trug weder Namen noch Monat — ein loses Blatt eines §16-Belegs war keiner
  Person zuzuordnen. Jetzt nennt eine Fußzeile auf jeder Seite Person, Monat
  und Seite (je Person ab 1 gezählt).
* **Monats-PDF, Zusammenfassung:** sie brach über den Seitenumbruch
  („Zusammenfassung“ unten auf Seite 1, die Zahlen auf Seite 2) — jetzt als
  Block zusammengehalten.
* **Monats-PDF, Spalte „Diff.“:** positive/negative Werte standen linksbündig,
  ±0 zentriert; in der Zusammenfassung saßen „Saldo Monat“ und „Überstunden
  kumuliert“ wegen eines anderen Zeilenabstands höher als ihre Beschriftung.
* **Aushang:** Namen brachen mitten im Namen um („… Dana Stein, Ella“ /
  „Fischer-Wagner …“) — liest sich am Schwarzen Brett wie zwei Personen.
"""
import base64
import re
import zlib
from datetime import date, time

from reportlab.lib.enums import TA_CENTER

from app.models import TimeEntry, User, UserRole
from app.services import auth_service, export_service, shift_plan_export_service
from tests.conftest import DEFAULT_TENANT_ID

YEAR, MONTH = 2026, 9


def _entry(db, user, d, start, end, break_min=0, note=None):
    db.add(TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                     start_time=start, end_time=end, break_minutes=break_min, note=note))
    db.commit()


def _weekdays(year=YEAR, month=MONTH):
    d = date(year, month, 1)
    while d.month == month:
        if d.weekday() < 5:
            yield d
        d = date.fromordinal(d.toordinal() + 1)


def _pdf(db):
    out = export_service.generate_monthly_report_pdf(db, YEAR, MONTH, tenant_id=DEFAULT_TENANT_ID)
    data = out.getvalue()
    assert data[:4] == b"%PDF"
    return data


def _page_texts(data: bytes) -> list:
    """Text je Seite. reportlab schreibt je Seite genau einen Inhaltsstrom
    (Standardschriften werden nicht eingebettet); Oktal-Escapes wie in
    ``test_shift_plan_pdf._pdf_text`` zurückübersetzt."""
    pages = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        chunk = match.group(1).strip()
        decoded = chunk
        for decoder in (lambda x: zlib.decompress(base64.a85decode(x, adobe=True)), zlib.decompress):
            try:
                decoded = decoder(chunk)
                break
            except Exception:  # noqa: BLE001 — nächster Dekodierversuch
                continue
        text = decoded.decode("latin-1", "replace")
        if " Tj" not in text and "TJ" not in text:
            continue
        pages.append(re.sub(r"\\([0-3][0-7]{2})", lambda m: chr(int(m.group(1), 8)), text))
    return pages


def _second_user(db):
    u = User(
        username="zweite", email="zweite@example.com",
        password_hash=auth_service.hash_password("x12345678"),
        first_name="Zweite", last_name="Person", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    return u


def _capture_tables(monkeypatch, with_kwargs=False):
    import reportlab.platypus as rp
    captured = []
    orig = rp.Table

    class _Spy(orig):
        def __init__(self, data, *a, **kw):
            captured.append((data, kw) if with_kwargs else data)
            super().__init__(data, *a, **kw)

    monkeypatch.setattr(rp, "Table", _Spy)
    return captured


# ─── Monats-PDF ─────────────────────────────────────────────────────────


def test_overlong_day_row_breaks_across_pages_instead_of_failing(db, test_user):
    """Eine Notiz länger als eine Seite: früher ``LayoutError`` (HTTP 500 für
    alle), jetzt läuft die Zeile auf der nächsten Seite weiter — vollständig,
    nichts abgeschnitten. ~190 Textzeilen ≈ 3,6 Seiten: mittig ausgerichtet
    zerfiel der Rest der Zeile in eine Kaskade fast leerer Seiten aus
    wiederholten Kopfzeilen (9 statt 4 Seiten beim Rendern) — die Zeile
    steht deshalb oben ausgerichtet."""
    note = "Ausführliche Dokumentation des Einsatzes mit allen Einzelheiten. " * 120 + "ENDMARKE"
    _entry(db, test_user, date(2026, 9, 3), time(8, 0), time(12, 0), note=note)

    pages = _page_texts(_pdf(db))

    assert 2 <= len(pages) <= 6, len(pages)
    assert "ENDMARKE" in "".join(pages)


def test_ordinary_rows_are_never_split_across_pages(db, test_user, monkeypatch):
    """In der Zeile umbrechen darf reportlab nur, wenn eine Zeile auf keine
    Seite passt. Sonst rutscht eine mehrzeilige Zeile (geteilter Dienst) als
    Ganzes auf die nächste Seite, statt „07:45" unten auf Seite 1 und
    „14:00" oben auf Seite 2 zu stehen."""
    for d in _weekdays():
        _entry(db, test_user, d, time(7, 0), time(9, 0))
        _entry(db, test_user, d, time(9, 30), time(12, 0))
        _entry(db, test_user, d, time(13, 0), time(15, 0))
        _entry(db, test_user, d, time(15, 30), time(17, 30))
    captured = _capture_tables(monkeypatch, with_kwargs=True)
    _pdf(db)

    main_kw = next(kw for data, kw in captured if data and getattr(data[0][0], "text", "") == "Datum")
    assert not main_kw.get("splitInRow")


def test_every_page_names_the_employee_and_month(db, test_user):
    """Geteilte Dienste an jedem Werktag: die Tabelle läuft auf eine zweite
    Seite. Jede Seite nennt genau die Person, deren Zahlen darauf stehen —
    auch die erste Seite der nächsten Person nicht mehr die vorige."""
    for d in _weekdays():
        _entry(db, test_user, d, time(7, 45), time(12, 0))
        _entry(db, test_user, d, time(14, 0), time(17, 30))
    _second_user(db)

    pages = _page_texts(_pdf(db))
    # Je Seite genau EIN Name; Reihenfolge der Personen nach Nachname
    # („Person" vor „User"), jede Person beginnt auf einer neuen Seite.
    names = [[n for n in ("Zweite Person", "Test User") if n in p] for p in pages]
    assert all(len(n) == 1 for n in names), names
    order = [n[0] for n in names]
    assert order == sorted(order, key=["Zweite Person", "Test User"].index), order
    test_user_pages = [p for p, n in zip(pages, order) if n == "Test User"]
    assert len(test_user_pages) >= 2

    for page in pages:
        assert "Monatsreport September 2026" in page
    # Seitenzählung je Person: die Fortsetzungsseite von Test User ist
    # „Seite 2", ihre erste Seite „Seite 1" (nicht die Fortsetzung der Zählung
    # der Person davor).
    assert "Seite 1" in test_user_pages[0]
    assert "Seite 2" in test_user_pages[1]


def test_summary_is_never_split_across_pages(db, test_user):
    """Mit jedem weiteren geteilten Dienst wächst die Tabelle um eine Zeile
    Text — irgendwo dazwischen endete sie so, dass die Zusammenfassung auf
    zwei Seiten zerfiel. Für jede Länge: Kopf und letzte Zeile auf derselben
    Seite."""
    for d in _weekdays():
        _entry(db, test_user, d, time(7, 45), time(12, 0))
        _entry(db, test_user, d, time(14, 0), time(17, 30))
        pages = _page_texts(_pdf(db))
        head = [i for i, p in enumerate(pages) if "Zusammenfassung" in p]
        # Klammern stehen im PDF-String escaped: „\(Min\)".
        tail = [i for i, p in enumerate(pages) if r"Nicht angerechnet \(Min\):" in p]
        assert head == tail, f"Zusammenfassung getrennt bei Tabellenende {d}: {head} / {tail}"


def test_diff_column_is_centered_for_every_sign(db, test_user, monkeypatch):
    _entry(db, test_user, date(2026, 9, 1), time(8, 0), time(17, 0))   # +1
    _entry(db, test_user, date(2026, 9, 2), time(8, 0), time(15, 0))   # −1
    _entry(db, test_user, date(2026, 9, 3), time(8, 0), time(16, 0))   # ±0
    captured = _capture_tables(monkeypatch)
    _pdf(db)

    main = next(t for t in captured if t and getattr(t[0][0], "text", "") == "Datum")
    diff_col = [getattr(c, "text", "") for c in main[0]].index("Diff.")
    cells = {r[0].text: r[diff_col] for r in main[1:]}

    assert [cells[k].text for k in ("01.09.2026", "02.09.2026", "03.09.2026")] == ["+1.00", "-1.00", "+0.00"]
    for k in ("01.09.2026", "02.09.2026", "03.09.2026"):
        assert cells[k].style.alignment == TA_CENTER, k


def test_summary_values_share_the_label_line_height(db, test_user, monkeypatch):
    """„Saldo Monat"/„Überstunden kumuliert" trugen einen eigenen Stil ohne
    Zeilenabstand (Vorgabe 12 statt 10) — ihre Zeilen waren höher und der Wert
    saß über der Beschriftung."""
    _entry(db, test_user, date(2026, 9, 1), time(8, 0), time(17, 0))
    captured = _capture_tables(monkeypatch)
    _pdf(db)

    summary = next(t for t in captured if t and getattr(t[0][0], "text", "") == "Zusammenfassung")
    for label, value in summary[1:]:
        assert value.style.leading == label.style.leading, label.text


# ─── Schichtplan-Aushang ────────────────────────────────────────────────


def _cell_lines(paragraph, width):
    """Die Zeilen, in die reportlab den Absatz bei ``width`` umbricht."""
    paragraph.wrap(width, 10_000)
    lines = []
    for line in paragraph.blPara.lines:
        words = getattr(line, "words", None)
        if words is None:  # einfacher Absatz: (Breite, [Wörter])
            lines.append(" ".join(line[1]))
        else:
            lines.append("".join(getattr(w, "text", "") for w in words))
    return lines


# Schmalste Spalte des Aushangs: sieben Wochentage im Querformat
# ((273 mm − 38 mm) / 7 ≈ 95 pt, abzüglich 2 × 4 pt Innenabstand).
SEVEN_DAY_TEXT_WIDTH = 87
FITTING = ["Anna Meier", "Carla Dorn", "Dana Stein", "Ella Fischer-Wagner",
           "Frieda Schulze", "Greta Hoffmann"]
TOO_WIDE = "Hanna Zimmermann-Schmidt"   # ≈ 106 pt — passt in keine Zeile


def _assignment_lines(names):
    cell = shift_plan_export_service._cell_paragraph([{
        "start_time": "08:00", "end_time": "16:00", "note": None, "min_staff": 1,
        "assignments": [{"user_name": n} for n in names],
    }], text_width=SEVEN_DAY_TEXT_WIDTH)
    return [line.replace("\xa0", " ") for line in _cell_lines(cell, SEVEN_DAY_TEXT_WIDTH)]


def test_names_in_the_shift_plan_do_not_break_inside_a_name():
    lines = _assignment_lines(FITTING + [TOO_WIDE])

    for n in FITTING:
        assert any(n in line for line in lines), (n, lines)


def test_a_name_wider_than_the_column_breaks_between_its_words():
    """Geschützt würde reportlab einen zu breiten Namen mitten im Wort trennen
    („Anna Meier, Hanna Zim" / „mermann-Schmidt, …", reportlab 4.5) — er
    bricht deshalb wie bisher an seinem Leerzeichen, jedes Wort bleibt ganz."""
    lines = _assignment_lines(["Anna Meier", TOO_WIDE, "Carla Dorn"])
    words = {w.rstrip(",") for line in lines for w in line.split()}

    for word in TOO_WIDE.split():
        assert word in words, (word, lines)


def test_the_printout_protects_names_at_the_real_column_width():
    """Der Renderer reicht die echte Spaltenbreite hinein: jeder passende Name
    steht im Ausdruck in EINER Textzeile (reportlab schreibt je Zeile einen
    ``(…) Tj``-String und das geschützte Leerzeichen als normales — kopierter
    Text bleibt unauffällig)."""
    out = shift_plan_export_service.generate_plan_pdf(
        {"name": "Plan", "active_today": True, "slots": [{
            "id": "s", "workstation_name": "Labor", "weekday": 0, "start_time": "08:00",
            "end_time": "16:00", "note": None, "min_staff": 1,
            "assignments": [{"user_name": n} for n in FITTING + [TOO_WIDE]],
        }]},
        weekdays=[0, 1, 2, 3, 4, 5, 6], workstation_order=["Labor"],
        practice_name=None, generated_on=date(2026, 10, 16),
    )
    text = "".join(_page_texts(out.getvalue()))
    for n in FITTING:
        assert n in text, n
