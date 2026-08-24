"""#443: PDF-Aushang eines Schichtplans.

Der Renderer ist bewusst eine reine Funktion: er bekommt das fertige Dict von
``_build_plan_detail`` und hat KEINEN Datenbankzugriff. Damit kann das PDF nicht
zu einem zweiten Abfragepfad auswachsen, der dem Bildschirm davonläuft — genau
das ist im Berechnungsmodell dieses Projekts mehrfach passiert.
"""
import base64
import re
import zlib
from datetime import date

from reportlab.pdfbase import pdfmetrics

from app.services import shift_plan_export_service


def _pdf_text(buf) -> str:
    """Der Text aus den Inhaltsströmen eines reportlab-PDF.

    ReportLab schreibt die Seiten als ``ASCII85Decode``+``FlateDecode``. Im
    Container ist keine PDF-Bibliothek installiert (``pdftotext`` u. ä. nicht
    garantiert vorhanden) — die Ströme werden mit Bordmitteln direkt dekodiert
    (Muster wie ``test_export_employment_window.py``/``test_export_endpoints.py``).
    """
    raw = buf.getvalue()
    parts: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        chunk = match.group(1).strip()
        decoded = chunk
        for decoder in (
            lambda x: zlib.decompress(base64.a85decode(x, adobe=True)),
            zlib.decompress,
        ):
            try:
                decoded = decoder(chunk)
                break
            except Exception:  # noqa: BLE001 — nächster Dekodierversuch
                continue
        parts.append(decoded.decode("latin-1", "replace"))
    text = "\n".join(parts)
    # reportlab escaped Umlaute/Sonderzeichen (alles außerhalb 0x20-0x7e) als
    # 3-stelliges Oktal-Escape (\ddd) INNERHALB der PDF-String-Literale, nicht
    # als rohes Byte — "ü" steht im Strom also als "\374", nicht als 0xFC.
    # NUR 3-stellige Oktalfolgen ersetzen (\( und \) für escapte Klammern,
    # von test_understaffed_slot_is_marked_in_the_printout u.a. bewusst als
    # literaler Backslash geprüft, bleiben unangetastet — die Regex greift
    # nur bei genau drei Ziffern).
    return re.sub(r"\\([0-3][0-7]{2})", lambda m: chr(int(m.group(1), 8)), text)


def _detail(**over):
    base = {
        "name": "Normalzustand",
        "description": "Regelbesetzung",
        "active_from_date": "2026-09-01",
        "active_until_date": None,
        # I-1: der Normalfall dieser Testdatei ist ein aktuell geltender Plan
        # (kein Vorschau-Vermerk im Ausdruck). Die I-1-Tests unten setzen
        # active_today explizit auf False, um genau den Vorschau-/Ablauf-Fall
        # zu prüfen.
        "active_today": True,
        "slots": [
            {
                "id": "s1",
                "workstation_name": "Tresen",
                "weekday": 0,
                "start_time": "08:00",
                "end_time": "12:00",
                "note": "Einarbeitung Azubi",
                "assignments": [{"user_name": "Anna Meier"}, {"user_name": "Carla Dorn"}],
            },
            {
                "id": "s2",
                "workstation_name": "Labor",
                "weekday": 1,
                "start_time": "09:00",
                "end_time": "17:00",
                "note": None,
                "assignments": [{"user_name": "Dana Stein"}],
            },
        ],
    }
    base.update(over)
    return base


def _render(**over):
    # #452: workstation_locations ist kein Feld von _detail() (das Slot-Dict
    # führt den Standort bewusst nicht, siehe generate_plan_pdf-Docstring) —
    # separat herausgelöst statt an _detail() durchgereicht.
    ws_locations = over.pop("workstation_locations", None)
    return shift_plan_export_service.generate_plan_pdf(
        _detail(**over),
        weekdays=[0, 1, 2, 3, 4],
        workstation_order=["Tresen", "Labor"],
        practice_name="Praxis Beispiel",
        generated_on=date(2026, 8, 23),
        workstation_locations=ws_locations,
    )


def test_renders_a_pdf():
    buf = _render()
    data = buf.getvalue()
    assert data[:4] == b"%PDF"
    assert len(data) > 1000


def test_plan_without_slots_still_renders():
    """Ein leerer Plan darf kein 500 werden — er rendert den Fließtext-Hinweis
    statt der Tabelle (siehe Kommentar bei ``len(table_data) == 1`` in
    ``shift_plan_export_service``)."""
    buf = _render(slots=[])
    assert buf.getvalue()[:4] == b"%PDF"


def test_markup_in_user_text_does_not_break_the_render():
    """reportlab parst innerhalb eines Paragraphen eine XML-ähnliche
    Mini-Auszeichnung. Ein Hinweis mit < oder & muss escaped werden, sonst
    bricht der Aufbau — oder schlimmer: er wird als Auszeichnung gedeutet."""
    slots = _detail()["slots"]
    slots[0]["note"] = "<b>Achtung</b> Meier & Sohn"
    slots[0]["assignments"] = [{"user_name": "Anna <script> Meier"}]
    buf = _render(slots=slots)
    assert buf.getvalue()[:4] == b"%PDF"


def test_disabled_weekdays_are_not_rendered():
    """#371: ein abgeschalteter Wochentag ist keine Planfläche — er darf auch
    im Ausdruck keine Spalte bekommen.

    Ein reiner Bytelängen-Vergleich (`len(small) < len(wide)`) fängt zwar eine
    Totalregression, sagt aber nichts darüber, ob die RICHTIGEN Tage entfallen
    — es könnte zufällig weniger herauskommen. Deshalb hier der Inhalt: die
    Kopfzeile trägt volle Wochentagsnamen (``WEEKDAY_LABELS``), also muss
    "Montag" (freigeschaltet, weekday=0) in beiden PDFs auftauchen, "Dienstag"
    (weekday=1, nur im breiten Plan freigeschaltet) nur in ``wide``."""
    small = shift_plan_export_service.generate_plan_pdf(
        _detail(), weekdays=[0], workstation_order=["Tresen", "Labor"],
        practice_name=None, generated_on=date(2026, 8, 23),
    )
    wide = _render()

    small_text = _pdf_text(small)
    wide_text = _pdf_text(wide)

    montag_in_small = "Montag" in small_text
    dienstag_in_small = "Dienstag" in small_text
    montag_in_wide = "Montag" in wide_text
    dienstag_in_wide = "Dienstag" in wide_text

    assert montag_in_small, "abgeschalteter Plan sollte den freigeschalteten Montag zeigen"
    assert not dienstag_in_small, "abgeschalteter Dienstag darf im Ausdruck keine Spalte bekommen"
    assert montag_in_wide, "voller Plan sollte Montag zeigen"
    assert dienstag_in_wide, "voller Plan sollte den freigeschalteten Dienstag zeigen"


def test_unknown_workstation_still_appears():
    """Ein Arbeitsplatz, der nicht in workstation_order steht (etwa weil er
    zwischen Abfrage und Rendern umbenannt wurde), darf nicht verschwinden."""
    slots = _detail()["slots"]
    slots.append({
        "id": "s3", "workstation_name": "Springer", "weekday": 2,
        "start_time": "10:00", "end_time": "14:00", "note": None,
        "assignments": [{"user_name": "Eva Ross"}],
    })
    buf = shift_plan_export_service.generate_plan_pdf(
        _detail(slots=slots), weekdays=[0, 1, 2, 3, 4],
        workstation_order=["Tresen", "Labor"],
        practice_name=None, generated_on=date(2026, 8, 23),
    )
    assert buf.getvalue()[:4] == b"%PDF"


def test_understaffed_slot_is_marked_in_the_printout():
    """M-3 (Abschlussgate, Fix-Runde 2): der Ausdruck druckte eine Unterbesetzung
    bislang kommentarlos mit, obwohl der Docstring von ``export_plan_pdf`` UND
    ``docs/SCHICHTPLANUNG.md`` behaupteten, er wuerde sie "automatisch erben".
    Ein Slot mit Mindestbesetzung 3 und zwei zugewiesenen Personen muss jetzt
    "Unterbesetzt (2/3)" zeigen; ein ausreichend besetzter Slot nicht."""
    slots = _detail()["slots"]
    slots[0]["min_staff"] = 3
    slots[0]["understaffed"] = True  # 2 zugewiesen ("Anna Meier", "Carla Dorn"), 3 gefordert
    slots[1]["min_staff"] = 1
    slots[1]["understaffed"] = False  # 1 zugewiesen, 1 gefordert -> erfuellt

    # reportlab schreibt runde Klammern im PDF-String-Literal maskiert
    # ("\(" / "\)") — der rohe Content-Stream, nicht die semantische Glyphe.
    text = _pdf_text(_render(slots=slots))
    assert r"Unterbesetzt \(2/3\)" in text
    assert r"Unterbesetzt \(1/1\)" not in text


def test_unassigned_slot_shows_the_staffing_shortfall():
    """Ein komplett unbesetzter Slot mit Mindestbesetzung zeigt den Sollwert
    mit ("nicht besetzt (0/2)"), nicht nur "nicht besetzt"."""
    slots = _detail()["slots"]
    slots[0]["assignments"] = []
    slots[0]["min_staff"] = 2
    slots[0]["understaffed"] = True

    text = _pdf_text(_render(slots=slots))
    assert r"nicht besetzt \(0/2\)" in text


def test_note_marker_is_representable_in_the_cell_font():
    """Fix-Runde 1 (#443): der Hinweis-Marker muss in der tatsächlich für die
    Tabellenzelle verwendeten Schrift (Helvetica/WinAnsiEncoding) darstellbar
    sein, ohne dass reportlab intern auf eine andere Schrift ausweicht.

    ``pdfmetrics.unicode2T1`` zerlegt einen Unicode-String in (Font, Bytes)-
    Segmente. Ein Zeichen, das die Zielschrift nicht kennt (z. B. der Pfeil
    "↳" in Helvetica/WinAnsiEncoding), erzeugt ein zusätzliches Segment in
    einer Ersatzschrift (ZapfDingbats) mit einem .notdef-artigen Ersatzglyph
    statt eines echten Pfeils — im Ausdruck ein schwarzes Kästchen. Genau EIN
    Segment, geschrieben in der Zellenschrift selbst, beweist, dass keine
    Ersatzschrift zum Einsatz kommt. Setzt jemand ``NOTE_MARKER`` auf den Pfeil
    zurück, schlägt dieser Test fehl (zwei Segmente, das erste in
    ZapfDingbats statt Helvetica)."""
    cell_font_name = shift_plan_export_service._CELL.fontName
    cell_font = pdfmetrics.getFont(cell_font_name)

    segments = pdfmetrics.unicode2T1(shift_plan_export_service.NOTE_MARKER, [cell_font])

    assert len(segments) == 1, (
        f"NOTE_MARKER erzwingt einen Font-Wechsel: {[f.fontName for f, _ in segments]}"
    )
    used_font, _raw_bytes = segments[0]
    assert used_font.fontName == cell_font_name


def test_wide_slot_notes_do_not_crash_the_layout():
    """C-1 (Prüfrunde 2, CRITICAL): reportlab kann eine Tabellenzeile nicht
    über einen Seitenumbruch teilen. Drei Einteilungen mit je 500-Zeichen-
    Hinweis (die erlaubte Höchstlänge von ``shift_slots.note``) am selben
    Arbeitsplatz/Tag machten die Zeile höher als der Rahmen (Querformat A4
    ≈ 515 pt) → ``doc.build`` warf eine ``LayoutError``, der Export blieb
    dauerhaft HTTP 500 (der Plan lässt sich nie wieder drucken). "Vormittag /
    Nachmittag / Spätsprechstunde" an einem Tresen sind bereits drei
    Einteilungen — gewöhnlicher Praxisbetrieb, kein Missbrauch.

    Ohne ``splitInRow=1`` an der ``Table``-Konstruktion in
    ``generate_plan_pdf`` schlägt dieser Test mit genau dieser ``LayoutError``
    fehl (verifiziert: Fund-Bericht round2-backend-report.md)."""
    note = "x" * 500
    slots = [
        {
            "id": f"wide{i}", "workstation_name": "Tresen", "weekday": 0,
            "start_time": "08:00", "end_time": "12:00", "note": note,
            "assignments": [{"user_name": "Anna Meier"}],
        }
        for i in range(3)
    ]
    buf = _render(slots=slots)
    assert buf.getvalue()[:4] == b"%PDF"


def test_many_assignments_in_one_cell_do_not_crash_the_layout():
    """Zweiter Fall derselben LayoutError-Klasse (C-1): statt langer
    Freitext-Hinweise sprengt hier allein die Personenzahl (~100+) in EINER
    Einteilung die Zeilenhöhe. Deckt die Grenze in die andere Richtung ab, wie
    vom Prüfer gefordert ("Personen in einer Einteilung" kippt schon bei
    deutlich weniger als hier verwendet). Ohne ``splitInRow=1`` schlägt auch
    dieser Test mit einer ``LayoutError`` fehl."""
    names = [{"user_name": f"Person Nr{i:03d}"} for i in range(150)]
    slots = [{
        "id": "crowd", "workstation_name": "Tresen", "weekday": 0,
        "start_time": "08:00", "end_time": "12:00", "note": None,
        "assignments": names,
    }]
    buf = _render(slots=slots)
    assert buf.getvalue()[:4] == b"%PDF"


def test_released_future_plan_is_marked_as_preview_in_the_printout():
    """I-1 (Prüfrunde 2, Important): der Bildschirm zeigt einem freigegebenen,
    noch nicht geltenden Plan einen blauen Hinweiskasten — der Ausdruck (das
    Artefakt, das ans Schwarze Brett geht) verriet davon bislang nichts.
    Gemessene Kopfzeile vor dem Fix: "Herbstplan · Default · Stand:
    23.08.2026" — neben dem geltenden Plan an derselben Pinnwand nicht zu
    unterscheiden."""
    text = _pdf_text(_render(active_today=False))
    assert "Vorschau" in text
    assert "gilt derzeit nicht" in text


def test_released_future_plan_without_any_date_window_is_still_marked():
    """Freigabe-Schalter (visible_to_employees) und Datumsfenster sind
    unabhängige Einstellungen (is_plan_visible_to) — der Vermerk darf NICHT
    an ein gesetztes active_from/until_date hängen, sonst greift er im
    Regelfall (freigegebener Entwurf ganz ohne Fenster) nicht."""
    text = _pdf_text(_render(active_today=False, active_from_date=None, active_until_date=None))
    assert "Vorschau" in text
    assert "gilt derzeit nicht" in text


def test_expired_plan_is_marked_as_no_longer_valid_not_as_preview():
    """Liegt active_until_date in der Vergangenheit, ist "Nicht mehr gültig"
    die ehrlichere Aussage als "Vorschau" — der Plan hat bereits gegolten,
    er gilt nicht erst noch."""
    text = _pdf_text(_render(active_today=False, active_from_date=None, active_until_date="2026-01-01"))
    assert "Nicht mehr gültig" in text
    assert "Vorschau" not in text


def test_currently_active_plan_carries_no_status_note():
    """Der Normalfall (aktuell geltender Plan) bleibt unverändert: kein
    Vorschau-/Ablauf-Vermerk in der Kopfzeile."""
    text = _pdf_text(_render(active_today=True))
    assert "Vorschau" not in text
    assert "Nicht mehr gültig" not in text


def test_uniform_location_appears_in_header_not_in_rows():
    """#452: Tragen ALLE Arbeitsplätze des Plans denselben Standort, steht er
    EINMAL in der Kopfzeile — nicht zusätzlich hinter jedem Arbeitsplatznamen.
    Reportlab schreibt runde Klammern im PDF-String-Literal maskiert
    ("\\(" / "\\)"), siehe test_understaffed_slot_is_marked_in_the_printout."""
    text = _pdf_text(_render(workstation_locations={"Tresen": "Hauptstelle", "Labor": "Hauptstelle"}))
    assert "Standort: Hauptstelle" in text
    assert r"Tresen \(Hauptstelle\)" not in text
    assert r"Labor \(Hauptstelle\)" not in text


def test_mixed_locations_appear_in_rows_not_header():
    """#452: unterschiedliche Standorte je Arbeitsplatz — der Standort steht
    dann je Zeile hinter dem Arbeitsplatznamen, NICHT (zusätzlich) einheitlich
    in der Kopfzeile."""
    text = _pdf_text(_render(workstation_locations={"Tresen": "Hauptstelle", "Labor": "Filiale"}))
    assert "Standort:" not in text
    assert r"Tresen \(Hauptstelle\)" in text
    assert r"Labor \(Filiale\)" in text


def test_mixed_locations_workstation_without_location_gets_no_suffix():
    """#452: im gemischten Fall bekommt ein Arbeitsplatz OHNE Standort keinen
    Klammer-Zusatz — "Labor" bleibt "Labor", nicht "Labor ()" o. ä."""
    text = _pdf_text(_render(workstation_locations={"Tresen": "Hauptstelle", "Labor": None}))
    assert "Standort:" not in text
    assert r"Tresen \(Hauptstelle\)" in text
    assert r"Labor \(" not in text


def test_no_location_set_shows_nothing():
    """#452: kein Arbeitsplatz des Plans trägt einen Standort (alle ``None``,
    oder ``workstation_locations`` ganz weggelassen wie vor #452) — dann taucht
    an keiner Stelle etwas auf, weder Kopfzeile noch Zeile."""
    text_explicit = _pdf_text(_render(workstation_locations={"Tresen": None, "Labor": None}))
    text_omitted = _pdf_text(_render())

    for text in (text_explicit, text_omitted):
        assert "Standort:" not in text
        assert r"Tresen \(" not in text
        assert r"Labor \(" not in text


import asyncio
from datetime import time as _time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.shift_planning import ShiftAssignment, ShiftPlan, ShiftSlot, Workstation
from app.models.system_setting import SystemSetting
from app.routers.shift_planning import export_plan_pdf
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


def _user(db, username, role=UserRole.EMPLOYEE):
    u = User(
        username=username, email=f"{username}@t.de", password_hash="h",
        first_name="F", last_name="L", role=role, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _plan(db, creator, name, *, active=False, visible=False):
    p = ShiftPlan(
        tenant_id=DEFAULT_TENANT_ID, name=name, is_active=active,
        visible_to_employees=visible, created_by=creator.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _body(response) -> bytes:
    """Liest den StreamingResponse-Rumpf synchron aus.

    Starlette wickelt jeden reinen Sync-Iterator (z. B. ein rohes ``BytesIO``)
    in ``iterate_in_threadpool`` ein — das Ergebnis ist ein ``async_generator``,
    der nur ``__anext__`` kennt. Ein Direktaufruf der Router-Funktion (wie in
    diesem Modul) läuft außerhalb jeder Ereignisschleife, kann also nicht
    ``async for`` benutzen — deshalb wird hier kurzzeitig eine eigene
    Ereignisschleife über ``asyncio.run`` aufgespannt, nur um den Generator
    leerzulesen. Über echtes ASGI (uvicorn/TestClient) übernimmt das ohnehin
    der Server selbst; siehe ``test_export_via_real_http_stream`` weiter unten.
    """

    async def _drain() -> bytes:
        return b"".join([chunk async for chunk in response.body_iterator])

    return asyncio.run(_drain())


def test_admin_can_export_a_draft(db, default_tenant):
    admin = _user(db, "pdf_admin", role=UserRole.ADMIN)
    plan = _plan(db, admin, "Entwurf zum Drucken")

    resp = export_plan_pdf(plan.id, db=db, current_user=admin)
    assert resp.media_type == "application/pdf"
    assert _body(resp)[:4] == b"%PDF"
    assert "attachment" in resp.headers["content-disposition"]


def test_employee_can_export_a_released_plan(db, default_tenant):
    """Der Mitarbeitende druckt nur, was er ohnehin am Bildschirm liest."""
    admin = _user(db, "pdf_rel_admin", role=UserRole.ADMIN)
    emp = _user(db, "pdf_rel_emp")
    plan = _plan(db, admin, "Freigegeben zum Drucken", visible=True)

    assert _body(export_plan_pdf(plan.id, db=db, current_user=emp))[:4] == b"%PDF"


def test_employee_cannot_export_an_invisible_plan(db, default_tenant):
    admin = _user(db, "pdf_hidden_admin", role=UserRole.ADMIN)
    emp = _user(db, "pdf_hidden_emp")
    plan = _plan(db, admin, "Entwurf bleibt zu")

    with pytest.raises(HTTPException) as exc:
        export_plan_pdf(plan.id, db=db, current_user=emp)
    assert exc.value.status_code == 404


def test_filename_is_sanitised(db, default_tenant):
    admin = _user(db, "pdf_name_admin", role=UserRole.ADMIN)
    plan = _plan(db, admin, 'Plan "Sommer"/2026')

    cd = export_plan_pdf(plan.id, db=db, current_user=admin).headers["content-disposition"]
    assert '"' not in cd.split("filename=")[1].split(";")[0].strip('"')
    assert "/" not in cd.split("filename=")[1].split(";")[0]


def _enable_shift_planning(db, tenant_id=DEFAULT_TENANT_ID):
    db.add(SystemSetting(key="shift_planning_enabled", tenant_id=tenant_id, value="true"))
    db.commit()


def _http_client(db, user, *, admin=False):
    """TestClient nach dem Muster von ``admin_client``/``employee_client`` in
    ``test_shift_planning.py`` — echtes ASGI statt Direktaufruf der Router-
    Funktion, damit auch das tatsächliche Streaming durchlaufen wird."""

    def _override_db():
        yield db

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    if admin:
        test_app.dependency_overrides[require_admin] = lambda: user
    return TestClient(test_app)


def test_export_via_real_http_stream_returns_pdf(db, default_tenant):
    """Die vier Tests oben rufen ``export_plan_pdf`` direkt auf und sehen dabei
    nie das echte Streaming — Starlette bekommt dort weder ASGI-Transport noch
    Ereignisschleife zu Gesicht. Dieser Test misst die Kette einmal wirklich
    durch: ein echter HTTP-Request über ``TestClient`` durchläuft denselben
    Async-Generator-Weg wie ein Browser oder ``curl``."""
    admin = _user(db, "pdf_http_admin", role=UserRole.ADMIN)
    plan = _plan(db, admin, "HTTP-Export")
    _enable_shift_planning(db)

    client = _http_client(db, admin, admin=True)
    try:
        resp = client.get(f"/api/shift-planning/plans/{plan.id}/export.pdf")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"
    finally:
        test_app.dependency_overrides.clear()


def test_export_via_real_http_404_when_flag_disabled(db, default_tenant):
    """Ohne aktiviertes Feature-Flag existiert die gesamte Schichtplanung nicht
    (404 über ``require_shift_planning_enabled``) — auch der Export-Endpunkt
    nicht. Bewusst kein ``_enable_shift_planning``-Aufruf: Default ist aus."""
    admin = _user(db, "pdf_http_admin_off", role=UserRole.ADMIN)
    plan = _plan(db, admin, "HTTP-Export ohne Flag")

    client = _http_client(db, admin, admin=True)
    try:
        resp = client.get(f"/api/shift-planning/plans/{plan.id}/export.pdf")
        assert resp.status_code == 404
    finally:
        test_app.dependency_overrides.clear()


def test_export_pdf_does_not_leak_qualification_flags_for_an_employee(db, default_tenant, monkeypatch):
    """R2-4 (Prüfrunde 2, Important): kein Test schützte bislang die
    admin-only-Zusage an GENAU dieser Fläche. Ein Prüfer hat ``is_admin`` in
    ``export_plan_pdf`` probeweise auf ein hartkodiertes ``True`` geändert —
    32 von 32 Tests blieben grün, weil der Renderer die Einweisungs-
    Kennzeichen heute nirgends druckt. Direkt daneben, in ``generate_plan``,
    steht bereits ein hartkodiertes ``True``; ein Copy-Paste oder eine
    naheliegende Erweiterung ("Unqualifiziert" auch im Ausdruck markieren)
    würde daraus ein Datenschutz-Leck machen, das kein Test bemerkt.

    ``test_shift_plan_visibility.py::test_build_plan_detail_hides_qualification_flags_from_non_admin``
    prüft ``_build_plan_detail`` bereits DIREKT — dieser Test prüft stattdessen
    die VERDRAHTUNG im Router: er fängt den Aufruf von
    ``shift_plan_export_service.generate_plan_pdf`` ab und belegt für einen
    Aufruf durch einen MITARBEITENDEN mit einer unqualifizierten Zuweisung,
    dass das übergebene ``detail``-Dict kein ``qualified``-Feld an den
    Zuweisungen trägt und ``validation.unqualified_slot_ids`` leer ist.

    Setzt man ``is_admin`` in ``export_plan_pdf`` hartkodiert auf ``True``,
    schlägt dieser Test fehl (verifiziert: Fund-Bericht
    round2-backend-report.md)."""
    from io import BytesIO

    from app.services import shift_plan_export_service

    admin = _user(db, "pdf_qual_admin", role=UserRole.ADMIN)
    emp = _user(db, "pdf_qual_emp")
    ws = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Labor")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    plan = _plan(db, admin, "Qualifikationsplan zum Drucken", visible=True)
    slot = ShiftSlot(
        tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan.id, workstation_id=ws.id,
        weekday=0, start_time=_time(8, 0), end_time=_time(12, 0), min_staff=1,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    # emp ist NICHT fuer "Labor" eingewiesen (keine WorkstationQualification) ->
    # in der Admin-Sicht waere der Slot "unqualified".
    db.add(ShiftAssignment(tenant_id=DEFAULT_TENANT_ID, shift_slot_id=slot.id, user_id=emp.id))
    db.commit()

    captured = {}

    def _fake_generate_plan_pdf(detail, **kwargs):
        captured["detail"] = detail
        return BytesIO(b"%PDF-fake")

    monkeypatch.setattr(shift_plan_export_service, "generate_plan_pdf", _fake_generate_plan_pdf)

    export_plan_pdf(plan.id, db=db, current_user=emp)

    assert "detail" in captured, "generate_plan_pdf wurde nicht aufgerufen"
    assignment = captured["detail"]["slots"][0]["assignments"][0]
    assert "qualified" not in assignment
    assert captured["detail"]["validation"]["unqualified_slot_ids"] == []


def test_export_pdf_orders_workstations_by_location_then_sort_order_then_name(db, default_tenant, monkeypatch):
    """Minor (Prüfrunde 2): §5.3 der Spezifikation verlangt Zeilen sortiert
    nach **Standort**, ``sort_order``, Name — vorher sortierte
    ``export_plan_pdf`` nur nach ``(Workstation.sort_order, Workstation.name)``,
    der Standort blieb unberücksichtigt. Arbeitsplätze desselben Standorts
    standen dadurch nicht zwangsläufig beieinander.

    "Zeta" (Standort "Hauptstelle", sort_order 0) und "Alpha" (Standort
    "Filiale", sort_order 1) sind bewusst so benannt, dass eine reine
    Namens-/sort_order-Sortierung OHNE Standort "Alpha" vor "Zeta" einordnen
    würde — nur die Standort-Gruppierung bringt "Zeta" nach vorn. Ein
    Arbeitsplatz ohne Standort fällt ans Ende."""
    from io import BytesIO

    from app.models.shift_planning import Location
    from app.services import shift_plan_export_service

    admin = _user(db, "pdf_order_admin", role=UserRole.ADMIN)

    loc_haupt = Location(tenant_id=DEFAULT_TENANT_ID, name="Hauptstelle", sort_order=0)
    loc_filiale = Location(tenant_id=DEFAULT_TENANT_ID, name="Filiale", sort_order=1)
    db.add_all([loc_haupt, loc_filiale])
    db.commit()
    db.refresh(loc_haupt)
    db.refresh(loc_filiale)

    ws_zeta_haupt = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Zeta", location_id=loc_haupt.id, sort_order=0)
    ws_alpha_filiale = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Alpha", location_id=loc_filiale.id, sort_order=0)
    ws_ohne_standort = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Springer", location_id=None, sort_order=0)
    db.add_all([ws_zeta_haupt, ws_alpha_filiale, ws_ohne_standort])
    db.commit()

    plan = _plan(db, admin, "Standort-Sortierung")

    captured = {}

    def _fake_generate_plan_pdf(detail, *, workstation_order, **kwargs):
        captured["workstation_order"] = workstation_order
        return BytesIO(b"%PDF-fake")

    monkeypatch.setattr(shift_plan_export_service, "generate_plan_pdf", _fake_generate_plan_pdf)

    export_plan_pdf(plan.id, db=db, current_user=admin)

    assert captured["workstation_order"] == ["Zeta", "Alpha", "Springer"]


def test_export_pdf_passes_workstation_locations_to_the_renderer(db, default_tenant, monkeypatch):
    """#452: der Renderer bleibt datenbankfrei (#443) — der Endpunkt reicht ihm
    deshalb eine Zuordnung Arbeitsplatz→Standort mit hinein, genau wie er das
    bereits mit ``workstation_order`` tut (Testfall direkt darüber, gleiches
    Standort-/Arbeitsplatz-Fixture). "Springer" hat keinen Standort und muss
    als ``None`` ankommen, nicht als fehlender Key oder Leerstring."""
    from io import BytesIO

    from app.models.shift_planning import Location
    from app.services import shift_plan_export_service

    admin = _user(db, "pdf_locmap_admin", role=UserRole.ADMIN)

    loc_haupt = Location(tenant_id=DEFAULT_TENANT_ID, name="Hauptstelle", sort_order=0)
    loc_filiale = Location(tenant_id=DEFAULT_TENANT_ID, name="Filiale", sort_order=1)
    db.add_all([loc_haupt, loc_filiale])
    db.commit()
    db.refresh(loc_haupt)
    db.refresh(loc_filiale)

    ws_zeta = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Zeta", location_id=loc_haupt.id, sort_order=0)
    ws_alpha = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Alpha", location_id=loc_filiale.id, sort_order=0)
    ws_springer = Workstation(tenant_id=DEFAULT_TENANT_ID, name="Springer", location_id=None, sort_order=0)
    db.add_all([ws_zeta, ws_alpha, ws_springer])
    db.commit()

    plan = _plan(db, admin, "Standort-Zuordnung")

    captured = {}

    def _fake_generate_plan_pdf(detail, *, workstation_locations, **kwargs):
        captured["workstation_locations"] = workstation_locations
        return BytesIO(b"%PDF-fake")

    monkeypatch.setattr(shift_plan_export_service, "generate_plan_pdf", _fake_generate_plan_pdf)

    export_plan_pdf(plan.id, db=db, current_user=admin)

    assert captured["workstation_locations"] == {
        "Zeta": "Hauptstelle",
        "Alpha": "Filiale",
        "Springer": None,
    }
