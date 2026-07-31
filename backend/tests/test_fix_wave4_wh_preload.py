"""Fix-Welle 4 #3: WorkingHoursChange-Preload fuer Urlaubs-Vorpruefungen.

``is_vacation_billable_day`` akzeptiert seit #431 einen ``wh_changes``-Preload,
wurde aber an den vier Vorpruefungs-Call-Sites (absences.create_absence,
admin_vacations.review_vacation_request, vacation_requests.apply_vacation_
request_patch + create_vacation_request) OHNE Preload aufgerufen: eine Query
pro Tag des Zeitraums, wo im gleichmaessigen Modus vorher NULL Queries noetig
gewesen waeren. Dasselbe Muster steckte in ``closure_split_service.
resplit_year_closures``: die Walk-Schleife (+ die beiden Budget-Vorschleifen)
loesten ``get_schedule_for_date`` pro Closure-/Privat-Urlaubstag OHNE Preload
auf.

Byte-Identitaet der zugrunde liegenden Calc-Funktionen (``is_vacation_
billable_day`` / ``get_schedule_for_date`` / ``get_vacation_account`` mit vs.
ohne Preload) ist bereits bewiesen in ``test_schedule_mode_switch_guards.py``,
``test_schedule_resolver.py`` und ``test_calc_preload.py`` — Preload-Parameter
sind an all diesen Funktionen rein additiv (Default ``None`` = alter
Query-Pfad). Dieser Test misst zusaetzlich, was Fix-Welle 4 #3 tatsaechlich
aendert: die Zahl der ``working_hours_changes``-Queries der BUDGET-VORPRUEFUNG
ist jetzt KONSTANT statt proportional zur Range-/Absence-Zahl.

Hinweis (Fund waehrend dieser Fix-Welle, NICHT behoben — siehe Bericht):
``absences.create_absence`` (Zeile ~577) und ``admin_vacations.
review_vacation_request`` (Zeile ~275) haben je Endpoint EINE ZWEITE,
separate Schleife, die die eigentlichen ``Absence``-Zeilen anlegt und dabei
``get_schedule_for_date`` PRO GEBUCHTEM TAG ohne Preload aufruft — derselbe
Fehlermuster, aber ausserhalb der vier vom Review benannten Vorpruefungs-
Call-Sites. Die Tests fuer diese beiden Endpoints isolieren deshalb den
DELTA zwischen einer kurzen und einer langen Range: waechst er exakt um die
Tagesdifferenz, kommt der Zuwachs vollstaendig aus der (hier unveraenderten)
Buchungsschleife — die Vorpruefung selbst traegt keine Pro-Tag-Kosten mehr.
"""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import event
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType, WorkingHoursChange, CompanyClosure
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.services import auth_service, calculation_service
from app.services.closure_split_service import resplit_year_closures
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

# Zwei volle Arbeitswochen (Mo-Fr) im gleichmaessigen Modus — 10 Werktage.
RANGE_START = date(2026, 3, 2)   # Montag
RANGE_END = date(2026, 3, 13)    # Freitag (2 Wochen spaeter)


def _create_test_app() -> FastAPI:
    from app.routers import absences, admin_vacations, vacation_requests, company_closures
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    app.include_router(admin_vacations.router)
    app.include_router(vacation_requests.router)
    app.include_router(company_closures.router)
    return app


_app = _create_test_app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30):
    u = User(
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("test123"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "adm4", role=UserRole.ADMIN)


@pytest.fixture
def emp(db, default_tenant):
    return _make_user(db, "emp4")


def _client_as(db, user, admin_too=None):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: user
    _app.dependency_overrides[require_admin] = lambda: (admin_too or user)
    return TestClient(_app)


class _WhQueryCounter:
    """Zaehlt SELECTs gegen working_hours_changes waehrend des with-Blocks."""

    def __init__(self):
        self.count = 0

    def __enter__(self):
        def _listener(conn, cursor, statement, parameters, context, executemany):
            if "from working_hours_changes" in statement.lower():
                self.count += 1
        self._listener = _listener
        event.listen(engine, "before_cursor_execute", _listener)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._listener)


def test_create_absence_precheck_wh_queries_do_not_scale_with_range(db, default_tenant, admin):
    """absences.create_absence: die Budget-VORPRUEFUNG darf mit der Range-
    Laenge NICHT mehr WHChange-Queries kosten (Fix-Welle 4 #3). Isoliert per
    Delta zwischen 2 und 10 Werktagen von der separaten, hier unveraenderten
    Buchungsschleife (s. Modul-Docstring) — waechst der Delta exakt um die
    Tagesdifferenz, stammt der GESAMTE Zuwachs aus der Buchungsschleife."""
    short_user = _make_user(db, "short4", vacation_days=30)
    long_user = _make_user(db, "long4", vacation_days=30)
    client = _client_as(db, admin)
    short_end = RANGE_START + timedelta(days=1)  # Mo+Di = 2 Werktage

    with _WhQueryCounter() as c_short:
        r1 = client.post("/api/absences/", json={
            "date": RANGE_START.isoformat(), "end_date": short_end.isoformat(),
            "type": "vacation", "hours": 8, "user_id": str(short_user.id),
        })
    assert r1.status_code == 201, r1.text
    n_short = len(r1.json())
    assert n_short == 2

    with _WhQueryCounter() as c_long:
        r2 = client.post("/api/absences/", json={
            "date": RANGE_START.isoformat(), "end_date": RANGE_END.isoformat(),
            "type": "vacation", "hours": 8, "user_id": str(long_user.id),
        })
    assert r2.status_code == 201, r2.text
    n_long = len(r2.json())
    assert n_long == 10  # 2 volle Wochen, keine Feiertage im Testfenster

    day_delta = n_long - n_short
    query_delta = c_long.count - c_short.count
    assert query_delta == day_delta, (
        f"WHChange-Queries wachsen ueber den Buchungsschleifen-Anteil hinaus "
        f"({c_short.count} -> {c_long.count} bei {n_short} -> {n_long} Tagen) "
        f"— die Vorpruefung selbst ist nicht mehr O(1)?"
    )

    # Byte-Identitaet: das Ergebnis (verbrauchte/verbleibende Urlaubstage)
    # entspricht exakt der Ground-Truth-Berechnung ohne jeden Preload.
    account = calculation_service.get_vacation_account(db, long_user, RANGE_START.year)
    assert account["used_days"] == 10.0
    assert account["remaining_days"] == 20.0


def test_review_vacation_request_precheck_wh_queries_do_not_scale_with_range(db, default_tenant, admin):
    """admin_vacations.review_vacation_request (Genehmigung, approve): dieselbe
    Delta-Messung wie oben, ueber den Antrags-Genehmigungspfad."""
    short_user = _make_user(db, "short4b", vacation_days=30)
    long_user = _make_user(db, "long4b", vacation_days=30)
    short_end = RANGE_START + timedelta(days=1)
    vr_short = VacationRequest(
        user_id=short_user.id, tenant_id=DEFAULT_TENANT_ID, date=RANGE_START, end_date=short_end,
        hours=8, absence_type="vacation", status=VacationRequestStatus.PENDING.value,
    )
    vr_long = VacationRequest(
        user_id=long_user.id, tenant_id=DEFAULT_TENANT_ID, date=RANGE_START, end_date=RANGE_END,
        hours=8, absence_type="vacation", status=VacationRequestStatus.PENDING.value,
    )
    db.add(vr_short); db.add(vr_long); db.commit(); db.refresh(vr_short); db.refresh(vr_long)

    client = _client_as(db, admin)
    with _WhQueryCounter() as c_short:
        r1 = client.post(f"/api/admin/vacation-requests/{vr_short.id}/review", json={"action": "approve"})
    assert r1.status_code == 200, r1.text

    with _WhQueryCounter() as c_long:
        r2 = client.post(f"/api/admin/vacation-requests/{vr_long.id}/review", json={"action": "approve"})
    assert r2.status_code == 200, r2.text

    day_delta = 10 - 2
    query_delta = c_long.count - c_short.count
    assert query_delta == day_delta, (
        f"WHChange-Queries wachsen ueber den Buchungsschleifen-Anteil hinaus "
        f"({c_short.count} -> {c_long.count}) — die Vorpruefung selbst ist "
        f"nicht mehr O(1)?"
    )

    account = calculation_service.get_vacation_account(db, long_user, RANGE_START.year)
    assert account["used_days"] == 10.0
    assert account["remaining_days"] == 20.0


def test_vacation_request_patch_wh_query_count_is_constant(db, default_tenant, emp):
    """vacation_requests.update_vacation_request (PATCH, eigener Antrag) —
    ruft apply_vacation_request_patch auf; die Budget-Vorpruefung durchlaeuft
    denselben Preload-Pfad wie die anderen drei Call-Sites."""
    vr = VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=RANGE_START,
        end_date=RANGE_START + timedelta(days=1), hours=8, absence_type="vacation",
        status=VacationRequestStatus.PENDING.value,
    )
    db.add(vr); db.commit(); db.refresh(vr)

    client = _client_as(db, emp)
    with _WhQueryCounter() as c:
        r = client.patch(f"/api/vacation-requests/{vr.id}", json={"end_date": RANGE_END.isoformat()})
    assert r.status_code == 200, r.text
    assert c.count == 1, f"erwartet 1 WHChange-Preload, gemessen {c.count}"


def test_vacation_request_create_wh_query_count_is_constant(db, default_tenant, emp):
    """vacation_requests.create_vacation_request (POST, eigener Antrag) bei
    aktivierter Genehmigungspflicht."""
    db.merge(SystemSetting(key="vacation_approval_required", tenant_id=DEFAULT_TENANT_ID, value="true"))
    db.commit()

    client = _client_as(db, emp)
    with _WhQueryCounter() as c:
        r = client.post("/api/vacation-requests/", json={
            "date": RANGE_START.isoformat(), "end_date": RANGE_END.isoformat(),
            "hours": 8, "absence_type": "vacation",
        })
    assert r.status_code == 201, r.text
    assert c.count == 1, f"erwartet 1 WHChange-Preload, gemessen {c.count}"


def _set_closure_toggle(db, on: bool):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def test_resplit_year_closures_wh_query_count_is_constant(db, default_tenant, admin):
    """closure_split_service.resplit_year_closures: 5 MA x 5 Schliesstage.
    Vorher loeste JEDE Walk-/Budget-Zeile eine eigene get_schedule_for_date-
    Query aus (bis zu 3 je Absence -> hier bis zu 75); jetzt EIN Preload je
    Tenant/Jahr (F-026-gefiltert), unabhaengig von MA- oder Tageszahl."""
    _set_closure_toggle(db, True)
    employees = [_make_user(db, f"cx{i}", vacation_days=2) for i in range(5)]  # knappes Budget
    mon = date(2026, 6, 1)  # Montag
    closure = CompanyClosure(
        tenant_id=DEFAULT_TENANT_ID, name="BF-Preload-Test",
        start_date=mon, end_date=mon + timedelta(days=4),
        counts_as_vacation=True, created_by=admin.id,
    )
    db.add(closure); db.commit(); db.refresh(closure)
    closure_id = closure.id
    for emp_u in employees:
        for offset in range(5):  # Mo-Fr
            db.add(Absence(
                user_id=emp_u.id, tenant_id=DEFAULT_TENANT_ID, date=mon + timedelta(days=offset),
                type=AbsenceType.VACATION, hours=8, half_day=False, closure_id=closure_id,
            ))
    db.commit()

    with _WhQueryCounter() as c:
        resplit_year_closures(db, DEFAULT_TENANT_ID, 2026)
    # EIN Preload fuer alle 5 MA zusammen (nicht 5, nicht 25) — der eigentliche
    # N+1-Beweis: die Query-Zahl waechst NICHT mit MA- oder Tageszahl.
    assert c.count == 1, f"erwartet 1 WHChange-Preload, gemessen {c.count}"

    # Byte-Identitaet der KLASSIFIZIERUNG gegen die (ungeaenderte) Fachlogik:
    # Budget 2 Tage -> erste 2 Kalendertage VACATION, Rest OVERTIME.
    for emp_u in employees:
        rows = db.query(Absence).filter(
            Absence.user_id == emp_u.id, Absence.closure_id == closure_id,
        ).order_by(Absence.date).all()
        assert [r.type for r in rows] == (
            [AbsenceType.VACATION] * 2 + [AbsenceType.OVERTIME] * 3
        )
