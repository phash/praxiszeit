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


import pytest
from fastapi import HTTPException

from app.models import User, UserRole
from app.models.shift_planning import ShiftPlan
from app.routers.shift_planning import export_plan_pdf
from tests.conftest import DEFAULT_TENANT_ID


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
    return b"".join(response.body_iterator)


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
