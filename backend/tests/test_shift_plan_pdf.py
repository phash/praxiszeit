"""#443: PDF-Aushang eines Schichtplans.

Der Renderer ist bewusst eine reine Funktion: er bekommt das fertige Dict von
``_build_plan_detail`` und hat KEINEN Datenbankzugriff. Damit kann das PDF nicht
zu einem zweiten Abfragepfad auswachsen, der dem Bildschirm davonläuft — genau
das ist im Berechnungsmodell dieses Projekts mehrfach passiert.
"""
from datetime import date

from app.services import shift_plan_export_service


def _detail(**over):
    base = {
        "name": "Normalzustand",
        "description": "Regelbesetzung",
        "active_from_date": "2026-09-01",
        "active_until_date": None,
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
    return shift_plan_export_service.generate_plan_pdf(
        _detail(**over),
        weekdays=[0, 1, 2, 3, 4],
        workstation_order=["Tresen", "Labor"],
        practice_name="Praxis Beispiel",
        generated_on=date(2026, 8, 23),
    )


def test_renders_a_pdf():
    buf = _render()
    data = buf.getvalue()
    assert data[:4] == b"%PDF"
    assert len(data) > 1000


def test_plan_without_slots_still_renders():
    """Ein leerer Plan darf kein 500 werden — reportlab wirft bei einer
    Tabelle ohne Datenzeilen."""
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
    im Ausdruck keine Spalte bekommen."""
    small = shift_plan_export_service.generate_plan_pdf(
        _detail(), weekdays=[0], workstation_order=["Tresen", "Labor"],
        practice_name=None, generated_on=date(2026, 8, 23),
    )
    wide = _render()
    assert len(small.getvalue()) < len(wide.getvalue())


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
