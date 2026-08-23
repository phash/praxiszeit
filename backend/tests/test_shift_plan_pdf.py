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


import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.shift_planning import ShiftPlan
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
