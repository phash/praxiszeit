"""Gesamtreview 1.20 (B5, #496-Restschuld): ein Zeitraum mit 0 Wochenstunden
im gleichmaessigen Modus (``weekly_hours = 0``, Schema ``ge=0`` — z. B.
Elternzeit) zaehlt in JEDER Urlaubs-Vorpruefung genau so, wie die zugehoerige
Buchung danach das Konto belastet.

Bis hier entschied ``is_vacation_billable_day`` im gleichmaessigen Modus
pauschal ``True`` („jeder Werktag traegt weekly_hours / work_days > 0") — das
stimmt nur, solange ``weekly_hours > 0``. Die Antragspfade rechneten seit #496
schon strikt (``vacation_day_cost_by_year``), Direktbuchung und
Aenderungsantrag nicht:

* ``absences.create_absence`` verlangte Budget fuer Tage, die die
  Buchungsschleife danach als 0-Stunden-Tag ueberspringt → 400 „Nicht genügend
  Urlaubstage", obwohl die Buchung weniger verbraucht haette;
* ``admin_change_requests`` (CREATE) verlangte einen vollen Urlaubstag fuer
  einen Tag, der im Konto 0 kostet (0-h-Zeitraum, Wochenende);
* die Betriebsferien-Buchung uebersprang den 0-Stunden-Tag nur im
  Tagesplan-Modus und legte im gleichmaessigen Modus eine 0-h-„Urlaub"-Zeile
  an — bei einem HEUTE auf 0 h stehenden Vertrag zaehlte das Konto jede davon
  als ganzen Urlaubstag (Elternzeit verlor Urlaub an die Betriebsferien).
"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    Absence, AbsenceType, ChangeRequest, ChangeRequestStatus, ChangeRequestType,
    User, UserRole, WorkingHoursChange,
)
from app.routers.admin_change_requests import _vacation_day_contribution, review_change_request
from app.schemas.change_request import ChangeRequestReview
from app.services import auth_service, calculation_service
from tests.conftest import DEFAULT_TENANT_ID, engine

# 02.11.2026 = Montag. Ab Mi 04.11. gilt 0 h/Woche (geplante Elternzeit).
NOV_MON, NOV_TUE, NOV_WED = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)
NOV_THU, NOV_FRI, NOV_SAT = date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 7)
# Fuer einen HEUTE (Live-Zeile) auf 0 h stehenden Vertrag: Elternzeit seit 01.03.
PARENTAL_FROM = date(2026, 3, 1)


def _create_test_app() -> FastAPI:
    from app.core.limiter import limiter
    from app.routers import absences, company_closures
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    app.include_router(company_closures.router)
    return app


_app = _create_test_app()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _app.dependency_overrides.clear()


def _client_as(db, user):
    def override_db():
        yield db

    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: user
    _app.dependency_overrides[require_admin] = lambda: user
    return TestClient(_app)


def _make_user(db, username, *, role=UserRole.EMPLOYEE, vacation_days=30,
               weekly_hours=40.0, track_hours=True):
    u = User(
        username=username, email=f"{username}@x.de",
        password_hash=auth_service.hash_password("x"),
        first_name=username, last_name="T", role=role,
        weekly_hours=weekly_hours, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=track_hours,
        use_daily_schedule=False, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _zero_hours_from(db, user, effective_from):
    db.add(WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=effective_from, weekly_hours=Decimal("0"),
        use_daily_schedule=False, work_days_per_week=5,
    ))
    db.commit()


def _planned_parental(db, username, vacation_days):
    """Heute 40 h, ab Mi 04.11.2026 0 h (die Live-Zeile traegt noch 40 h)."""
    u = _make_user(db, username, vacation_days=vacation_days)
    _zero_hours_from(db, u, NOV_WED)
    return u


def _current_parental(db, username, vacation_days):
    """Seit 01.03.2026 0 h — die Live-Zeile spiegelt den heute gueltigen Wert."""
    u = _make_user(db, username, vacation_days=vacation_days, weekly_hours=0.0)
    _zero_hours_from(db, u, PARENTAL_FROM)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "b5_admin", role=UserRole.ADMIN)


def _remaining(db, user):
    db.expire_all()
    return calculation_service.get_vacation_account(db, user, 2026)["remaining_days"]


def _used(db, user):
    db.expire_all()
    return calculation_service.get_vacation_account(db, user, 2026)["used_days"]


# ── Der Helfer ────────────────────────────────────────────────────────────────

class TestHelper:

    def test_zero_hour_uniform_day_is_not_billable(self, db, default_tenant):
        u = _planned_parental(db, "b5_helper", 30)
        assert calculation_service.is_vacation_billable_day(db, u, NOV_TUE) is True
        assert calculation_service.is_vacation_billable_day(db, u, NOV_WED) is False
        assert calculation_service.is_vacation_billable_day(db, u, NOV_FRI) is False

    def test_untracked_stays_billable_in_zero_hour_period(self, db, default_tenant):
        u = _make_user(db, "b5_helper_untracked", track_hours=False)
        _zero_hours_from(db, u, NOV_WED)
        assert calculation_service.is_vacation_billable_day(db, u, NOV_WED) is True

    def test_cost_helper_uses_the_same_answer(self, db, default_tenant):
        u = _planned_parental(db, "b5_cost", 30)
        days = [NOV_MON, NOV_TUE, NOV_WED, NOV_THU, NOV_FRI]
        assert calculation_service.vacation_day_cost_by_year(db, u, days, False) == {
            2026: Decimal("2")}
        assert calculation_service.vacation_day_cost_by_year(
            db, u, days, False) == {2026: Decimal(sum(
                1 for d in days if calculation_service.is_vacation_billable_day(db, u, d)))}


# ── Direktbuchung ─────────────────────────────────────────────────────────────

class TestDirectBooking:

    def test_precheck_does_not_demand_budget_for_zero_hour_days(self, db, admin):
        """3 Resttage, Urlaub Mo–Fr, 0 h ab Mi: gebucht werden Mo + Di (2 Tage).
        Vorher verlangte die Vorpruefung 5 Tage → 400."""
        emp = _planned_parental(db, "b5_direct", 3)
        assert _remaining(db, emp) == pytest.approx(3)

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": NOV_MON.isoformat(),
            "end_date": NOV_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })

        assert r.status_code == 201, r.text
        booked = {a.date for a in db.query(Absence).filter(Absence.user_id == emp.id)}
        assert booked == {NOV_MON, NOV_TUE}
        assert _remaining(db, emp) == pytest.approx(1)

    def test_only_zero_hour_days_name_the_real_reason(self, db, admin):
        """Kein Resturlaub, Urlaub nur im 0-h-Zeitraum: die Buchung kostet
        nichts — die Antwort nennt den tatsaechlichen Grund (0 Stunden
        geplant), nicht ein fehlendes Budget."""
        emp = _planned_parental(db, "b5_direct_zero", 0)

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": NOV_WED.isoformat(),
            "end_date": NOV_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })

        assert r.status_code == 400, r.text
        assert "0 Stunden geplant" in r.json()["detail"]
        assert "Urlaubstage" not in r.json()["detail"]

    def test_normal_days_still_need_budget(self, db, admin):
        emp = _planned_parental(db, "b5_direct_ctrl", 1)
        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": NOV_MON.isoformat(),
            "end_date": NOV_TUE.isoformat(), "type": "vacation", "hours": 8.0,
        })
        assert r.status_code == 400, r.text
        assert r.json()["detail"].startswith("Nicht genügend Urlaubstage für 2026")

    def test_current_zero_hour_contract_books_nothing_and_costs_nothing(self, db, admin):
        """Heute auf 0 h (Live-Zeile 0): kein Tag wird gebucht, kein Budget
        verlangt — dieselbe Antwort wie oben, unabhaengig vom Live-Wert."""
        emp = _current_parental(db, "b5_direct_now", 0)
        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": NOV_MON.isoformat(),
            "end_date": NOV_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })
        assert r.status_code == 400, r.text
        assert "0 Stunden geplant" in r.json()["detail"]


def _count_statements(fn, needle):
    seen = {"n": 0}

    def _listener(conn, cursor, statement, parameters, context, executemany):
        if needle in statement.lower():
            seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _listener)
    return seen["n"]


def test_direct_precheck_loads_year_data_once(db, admin):
    """Die Vorpruefung laedt Feiertage/Sondertage je Jahr EINMAL (``year_cache``)
    — eine zweiwoechige Buchung stellt nicht mehr Feiertags-Abfragen als eine
    einwoechige."""
    emp_short = _make_user(db, "b5_q_short")
    emp_long = _make_user(db, "b5_q_long")

    def _book(emp, end):
        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": NOV_MON.isoformat(),
            "end_date": end.isoformat(), "type": "vacation", "hours": 8.0,
        })
        assert r.status_code == 201, r.text

    short = _count_statements(lambda: _book(emp_short, NOV_FRI), "from public_holidays")
    long = _count_statements(lambda: _book(emp_long, date(2026, 11, 13)), "from public_holidays")
    assert long == short


# ── Aenderungsantrag (CREATE) ─────────────────────────────────────────────────

def _absence_cr(db, user, d, absence_type="vacation"):
    cr = ChangeRequest(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.CREATE, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="Testantrag",
        proposed_date=d, proposed_absence_type=absence_type,
        proposed_absence_hours=8.0,
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


def _approve_cr(db, admin, cr):
    return review_change_request(
        request_id=str(cr.id), review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )


class TestChangeRequestCreate:

    def test_zero_hour_day_costs_nothing_and_needs_no_budget(self, db, admin):
        """0 Resttage, Urlaub per Antrag am Do im 0-h-Zeitraum: das Konto
        zaehlt den Tag mit 0 — die Vorpruefung verlangte vorher einen ganzen
        Tag und lehnte mit 400 ab."""
        emp = _planned_parental(db, "b5_cr_zero", 0)
        cr = _absence_cr(db, emp, NOV_THU)

        _approve_cr(db, admin, cr)

        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.APPROVED
        assert _used(db, emp) == pytest.approx(0)

    def test_weekend_day_needs_no_budget(self, db, admin):
        """Der Aenderungsantrag bucht bewusst auch am Wochenende
        (Samstagsdienst); ein Samstag hat Tagessoll 0 und kostet im Konto
        nichts."""
        emp = _make_user(db, "b5_cr_sat", vacation_days=0)
        cr = _absence_cr(db, emp, NOV_SAT)

        _approve_cr(db, admin, cr)

        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.APPROVED
        assert _used(db, emp) == pytest.approx(0)

    def test_working_day_still_needs_budget(self, db, admin):
        emp = _planned_parental(db, "b5_cr_ctrl", 0)
        cr = _absence_cr(db, emp, NOV_TUE)
        with pytest.raises(HTTPException) as exc:
            _approve_cr(db, admin, cr)
        assert exc.value.status_code == 400
        assert "Urlaubstage" in exc.value.detail

    @pytest.mark.parametrize("scenario, day", [
        ("planned", NOV_TUE),   # Arbeitstag vor dem 0-h-Zeitraum
        ("planned", NOV_THU),   # Tag im kuenftigen 0-h-Zeitraum
        ("planned", NOV_SAT),   # Wochenende
        ("current", NOV_THU),   # Vertrag steht HEUTE auf 0 h
    ])
    def test_precheck_equals_account_consumption(self, db, admin, scenario, day):
        """Paritaet: was die Vorpruefung des Aenderungsantrags verlangt, ist
        exakt das, was das Urlaubskonto nach der Genehmigung zusaetzlich
        zaehlt — in jeder Konstellation (auch bei einem heute auf 0 h
        stehenden Vertrag, dessen Konto ohne Tagessoll tagebasiert zaehlt)."""
        make = _planned_parental if scenario == "planned" else _current_parental
        emp = make(db, f"b5_cr_par_{scenario}_{day.day}", 30)
        demanded = _vacation_day_contribution(db, emp, day, False)
        before = _used(db, emp)

        _approve_cr(db, admin, _absence_cr(db, emp, day))

        assert _used(db, emp) - before == pytest.approx(demanded)


# ── Betriebsferien ────────────────────────────────────────────────────────────

def _create_closure(client, start=NOV_MON, end=NOV_FRI):
    r = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": start.isoformat(), "end_date": end.isoformat(),
        "counts_as_vacation": True})
    assert r.status_code == 201, r.text
    return r.json()


class TestClosureBooking:

    def test_zero_hour_uniform_days_are_skipped(self, db, admin):
        """Wie im Tagesplan-Modus: an einem Tag ohne Tagessoll gibt es nichts
        zu schliessen — keine 0-h-„Urlaub"-Zeile."""
        emp = _planned_parental(db, "b5_clo_planned", 30)

        _create_closure(_client_as(db, admin))

        db.expire_all()
        rows = db.query(Absence).filter(Absence.user_id == emp.id).all()
        assert {a.date for a in rows} == {NOV_MON, NOV_TUE}
        assert all(float(a.hours) > 0 for a in rows)

    def test_current_zero_hour_contract_keeps_its_vacation(self, db, admin):
        """Vertrag steht heute auf 0 h: das Konto zaehlt ohne Tagessoll jede
        Urlaubszeile als ganzen Tag. Vorher legte die Betriebsferien-Buchung
        fuenf 0-h-Zeilen an — die Elternzeit verlor fuenf Urlaubstage."""
        emp = _current_parental(db, "b5_clo_now", 30)
        assert _remaining(db, emp) == pytest.approx(30)

        _create_closure(_client_as(db, admin))

        db.expire_all()
        assert db.query(Absence).filter(Absence.user_id == emp.id).count() == 0
        assert _remaining(db, emp) == pytest.approx(30)

    def test_untracked_still_books_every_day(self, db, admin):
        """#191: ohne Stundenzaehlung ist das Tagessoll immer 0 — trotzdem
        1 Urlaubstag je Betriebsferientag; der Skip darf sie nie erfassen."""
        emp = _make_user(db, "b5_clo_untracked", track_hours=False)
        _zero_hours_from(db, emp, NOV_WED)

        _create_closure(_client_as(db, admin))

        db.expire_all()
        assert db.query(Absence).filter(Absence.user_id == emp.id).count() == 5
