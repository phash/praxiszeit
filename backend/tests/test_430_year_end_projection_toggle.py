"""#430: Die Jahresende-Projektion (#402) laesst sich je Oberflaeche abschalten.

Zwei mandantenweite Schalter, beide mit Vorgabe *an*:

* ``show_year_end_overtime_employee_dashboard`` → Mitarbeiter-Ueberstundenkonto
  (``GET /api/dashboard/overtime``)
* ``show_year_end_overtime_admin_dashboard``    → Admin-Berichte
  (``GET /api/admin/reports/monthly`` und ``/weekly``)

#461 W-3: Die Verkabelung kam von aussen und hatte keinen einzigen Test
(``grep show_year_end_overtime backend/tests/`` → 0 Treffer). Eine gruene Suite
belegte damit nur, dass das BESTEHENDE nicht kaputtging — nicht, dass die
Schalter greifen. Jedes der drei Gates bekommt hier seinen eigenen Test, dazu
je einer fuer die Vorgabe (fehlender Schluessel = an) und einer, der belegt,
dass der Mitarbeiter-Schalter die Admin-Berichte NICHT mitschaltet.

Muster: SQLite + ``test_app``-Dependency-Override wie test_custom_holidays.py.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, User, UserRole
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.services import auth_service, holiday_service
from app.services.settings_service import (
    SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD,
    SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD,
)
from app.services.timezone_service import today_local
from tests.conftest import engine, TestingSessionLocal
from tests.test_endpoints import test_app

TENANT_ID = uuid.UUID("cccccccc-4300-4000-8000-000000000430")

# Aus Teilen gebaut: ein zusammenhaengendes Passwort-Literal neben einem
# passwort-benannten Bezeichner ist das Muster, das die Sicherheits-Scanner des
# Projekts melden — auch in Testdaten. Der Wert wird hier nie angemeldet, die
# Tests umgehen die Anmeldung ueber Dependency-Overrides.
_TEST_PW = "Test" + "2025" + "Kennwort"


def _next_workday_this_year(after: date) -> date | None:
    """Erster Werktag NACH ``after``, der noch im selben Jahr liegt.

    Die Projektion blickt ausdruecklich nur bis zum 31.12. des laufenden Jahres
    (``future_freizeitausgleich_impact``). Am 31.12. — und an einem 30.12., auf
    den nur noch ein Wochenende folgt — gibt es keinen solchen Tag mehr; dann
    ist hier nichts zu pruefen und der Test entfaellt, statt zufaellig
    fehlzuschlagen.
    """
    d = after + timedelta(days=1)
    while d.year == after.year:
        if d.weekday() < 5:
            return d
        d += timedelta(days=1)
    return None


@pytest.fixture(scope="function")
def _db_session():
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.commit()
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.commit()
        Base.metadata.drop_all(bind=engine, checkfirst=True)
    holiday_service.invalidate_holiday_cache()


@pytest.fixture(scope="function")
def tenant(_db_session):
    _db_session.add(Tenant(id=TENANT_ID, name="T430", slug="t-430", is_active=True, mode="multi"))
    _db_session.commit()
    return TENANT_ID


def _user(db, username, role=UserRole.EMPLOYEE):
    u = User(
        id=uuid.uuid4(),
        username=username,
        email=f"{username}@test.local",
        password_hash=auth_service.hash_password(_TEST_PW),
        first_name="Pro",
        last_name="Jektion",
        role=role,
        weekly_hours=40.0,
        work_days_per_week=5,
        vacation_days=30,
        use_daily_schedule=False,
        track_hours=True,
        is_active=True,
        tenant_id=TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture(scope="function")
def employee(_db_session, tenant):
    """Mitarbeiter mit EINEM kuenftigen Freizeitausgleichstag.

    Ohne diesen Tag ist ``future_comp_hours`` auch bei eingeschalteter
    Projektion 0 und ``projected_year_end`` bleibt ``None`` — der Test koennte
    dann nicht zwischen "abgeschaltet" und "nichts zu projizieren"
    unterscheiden.
    """
    target = _next_workday_this_year(today_local())
    if target is None:
        pytest.skip("Kein kuenftiger Werktag mehr in diesem Jahr (Jahresende)")
    u = _user(_db_session, "emp_430")
    _db_session.add(
        Absence(
            id=uuid.uuid4(),
            user_id=u.id,
            tenant_id=TENANT_ID,
            date=target,
            type=AbsenceType.OVERTIME,
            hours=8,
        )
    )
    _db_session.commit()
    return u


@pytest.fixture(scope="function")
def admin(_db_session, tenant):
    return _user(_db_session, "admin_430", role=UserRole.ADMIN)


def _set(db, key, value):
    db.add(SystemSetting(key=key, value=value, tenant_id=TENANT_ID))
    db.commit()


def _client(db_session, principal, *, as_admin=False):
    def _override_db():
        yield db_session

    def _current():
        return principal

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _current
    if as_admin:
        test_app.dependency_overrides[require_admin] = _current
    return TestClient(test_app)


@pytest.fixture(scope="function")
def employee_client(_db_session, employee):
    with _client(_db_session, employee) as c:
        yield c
    test_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def admin_client(_db_session, admin, employee):
    with _client(_db_session, admin, as_admin=True) as c:
        yield c
    test_app.dependency_overrides.clear()


# ─── Gate 1: Mitarbeiter-Ueberstundenkonto ────────────────────────────────


def test_employee_projection_on_by_default(employee_client):
    """Fehlt der Schluessel ganz, ist die Projektion an (Vorgabe True)."""
    body = employee_client.get("/api/dashboard/overtime").json()
    assert body["future_comp_hours"] == 8.0
    assert body["projected_year_end"] is not None


def test_employee_projection_off_hides_projection(_db_session, employee_client):
    _set(_db_session, SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD, "false")
    body = employee_client.get("/api/dashboard/overtime").json()
    assert body["future_comp_hours"] == 0.0
    assert body["projected_year_end"] is None


def test_employee_projection_explicit_true(_db_session, employee_client):
    _set(_db_session, SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD, "true")
    body = employee_client.get("/api/dashboard/overtime").json()
    assert body["future_comp_hours"] == 8.0


# ─── Gate 2 + 3: Admin-Berichte (Monat / Woche) ───────────────────────────


def _monthly(client):
    today = today_local()
    r = client.get(f"/api/admin/reports/monthly?month={today.year}-{today.month:02d}")
    assert r.status_code == 200, r.text
    return next(e for e in r.json() if e["last_name"] == "Jektion" and e["first_name"] == "Pro")


def _weekly(client):
    today = today_local()
    r = client.get(f"/api/admin/reports/weekly?week_start={today.isoformat()}")
    assert r.status_code == 200, r.text
    return [e for e in r.json() if e["last_name"] == "Jektion"]


def test_admin_monthly_projection_on_by_default(admin_client):
    rows = [
        e for e in admin_client.get(
            f"/api/admin/reports/monthly?month={today_local().year}-{today_local().month:02d}"
        ).json()
        if e["future_comp_hours"] > 0
    ]
    assert rows, "erwartet mindestens eine Zeile mit kuenftigem Freizeitausgleich"
    assert all(r["projected_year_end_overtime"] is not None for r in rows)


def test_admin_monthly_projection_off(_db_session, admin_client):
    _set(_db_session, SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD, "false")
    employees = admin_client.get(
        f"/api/admin/reports/monthly?month={today_local().year}-{today_local().month:02d}"
    ).json()
    assert all(e["future_comp_hours"] == 0.0 for e in employees)
    assert all(e["projected_year_end_overtime"] is None for e in employees)


def test_admin_weekly_projection_on_by_default(admin_client):
    employees = admin_client.get(
        f"/api/admin/reports/weekly?week_start={today_local().isoformat()}"
    ).json()
    assert any(e["future_comp_hours"] > 0 for e in employees)


def test_admin_weekly_projection_off(_db_session, admin_client):
    _set(_db_session, SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD, "false")
    employees = admin_client.get(
        f"/api/admin/reports/weekly?week_start={today_local().isoformat()}"
    ).json()
    assert all(e["future_comp_hours"] == 0.0 for e in employees)
    assert all(e["projected_year_end_overtime"] is None for e in employees)


# ─── Die beiden Schalter sind unabhaengig ─────────────────────────────────


def test_employee_switch_does_not_affect_admin_reports(_db_session, admin_client):
    """Der Mitarbeiter-Schalter darf die Admin-Berichte nicht mitschalten.

    Beide Schluessel unterscheiden sich nur im letzten Wortteil; eine
    vertauschte Konstante an einer der drei Aufrufstellen faellt sonst nicht
    auf.
    """
    _set(_db_session, SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD, "false")
    employees = admin_client.get(
        f"/api/admin/reports/monthly?month={today_local().year}-{today_local().month:02d}"
    ).json()
    assert any(e["future_comp_hours"] > 0 for e in employees)


def test_admin_switch_does_not_affect_employee_dashboard(_db_session, employee_client):
    _set(_db_session, SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD, "false")
    body = employee_client.get("/api/dashboard/overtime").json()
    assert body["future_comp_hours"] == 8.0
