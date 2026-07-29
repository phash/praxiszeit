"""#431: Löschen einer Tagesplan-Änderung rechnet symmetrisch zurück.

Der Schreibpfad (``create_working_hours_change``) nimmt seit #431
Tagesplan-Änderungen an und schreibt den vollständigen Vertrags-Snapshot
(Modus + Tageswerte + Arbeitstage). Das Löschen (``delete_working_hours_change``)
hing dahinter zurück: ein ``_uses_daily_schedule``-Guard übersprang für diese
Gruppe sowohl ``retarget_absence_hours`` als auch
``stale_year_closing_warning`` — genau die Rückrechnung, die für alle anderen
Mitarbeitenden längst gilt. Dieser Test belegt, dass das Löschen jetzt
symmetrisch zum Anlegen zurückrechnet.

Fährt bewusst über HTTP (``TestClient``), wie ``test_wh_change_day_plan_create.py``
— ``admin_headers`` ist wegen der überschriebenen Auth-Dependencies inert,
bleibt aber im Signaturbild, das der Rest der Suite für admin-authentifizierte
Requests verwendet. ``db_session`` ist ein Alias auf die ``db``-Fixture aus
``conftest.py``.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, WorkingHoursChange
from tests.test_endpoints import test_app


@pytest.fixture
def client(db, test_admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    # Die Auth-Dependencies sind oben per Override ersetzt — der Header-Inhalt
    # wird nie ausgewertet, bleibt aber Teil der Requests, wie es ein echter
    # admin-authentifizierter Client täte.
    return {"Authorization": "Bearer test"}


@pytest.fixture
def db_session(db):
    return db


def test_delete_pulls_absence_hours_back(client, admin_headers, db_session, day_plan_user):
    past = date.today() - timedelta(days=20)
    db_session.add(WorkingHoursChange(
        user_id=day_plan_user.id, tenant_id=day_plan_user.tenant_id,
        effective_from=past - timedelta(days=200), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_tuesday=Decimal("5.0"), hours_wednesday=Decimal("4.0"),
        work_days_per_week=3))
    db_session.commit()

    r = client.post(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes",
        headers=admin_headers,
        json={"effective_from": str(past), "use_daily_schedule": True,
              "hours_monday": 4.0, "hours_tuesday": 5.0, "hours_wednesday": 4.0,
              "work_days_per_week": 3})
    assert r.status_code == 201, r.text
    change_id = r.json()["id"]

    monday = past + timedelta(days=(7 - past.weekday()) % 7)
    db_session.add(Absence(
        user_id=day_plan_user.id, tenant_id=day_plan_user.tenant_id, date=monday,
        type=AbsenceType.SICK, hours=4.0, half_day=False))
    db_session.commit()

    d = client.delete(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes/{change_id}",
        headers=admin_headers)
    assert d.status_code in (200, 204), d.text

    row = db_session.query(Absence).filter(Absence.date == monday).first()
    db_session.refresh(row)
    assert Decimal(str(row.hours)) == Decimal("8.00")   # zurueck auf den alten Plan
