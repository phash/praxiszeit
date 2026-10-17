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
import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    Absence, AbsenceType, ChangeRequest, ChangeRequestStatus, ChangeRequestType,
    TimeEntry, TimeEntryAuditLog, User, UserRole, WorkingHoursChange,
)
from app.models.system_setting import SystemSetting
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.models.year_carryover import YearCarryover
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
    from app.routers import absences, admin_vacations, company_closures, vacation_requests
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    app.include_router(company_closures.router)
    app.include_router(vacation_requests.router)
    app.include_router(admin_vacations.router)
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


# ── Jahre ohne Kosten (Nachzug Gesamtreview B5) ───────────────────────────────
#
# Die Budget-Schleifen pruefen jedes Jahr des Zeitraums, auch eines, in dem die
# Buchung nichts kostet. Ein Resturlaub im Minus (erlaubt: Betriebsferien ohne
# Deckel, Fix #6) sperrte dort mit ``0 > -1`` eine Buchung, die in diesem Jahr
# gar nichts verbraucht. Der CREATE-Zweig des Aenderungsantrags prueft nur bei
# Kosten > 0 — die vier Schleifen ziehen jetzt nach.

# 28.12.2026 = Montag. 0 h vom 01.12.2026 bis 03.01.2027, ab Mo 04.01.2027 40 h.
DEC_MON_28, DEC_THU_31 = date(2026, 12, 28), date(2026, 12, 31)
JAN_MON_04, JAN_FRI_08 = date(2027, 1, 4), date(2027, 1, 8)
JAN_WEEK = {date(2027, 1, d) for d in range(4, 9)}


def _negative_2026_back_in_2027(db, username):
    """Resturlaub 2026 = 30 − 31 = −1 (Uebertrag), Dezember auf 0 h,
    ab 04.01.2027 wieder 40 h; 2027 volle 30 Tage."""
    u = _make_user(db, username, vacation_days=30)
    _zero_hours_from(db, u, date(2026, 12, 1))
    db.add(WorkingHoursChange(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID, effective_from=JAN_MON_04,
        weekly_hours=Decimal("40"), use_daily_schedule=False, work_days_per_week=5,
    ))
    db.add(YearCarryover(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
        vacation_days=Decimal("-31"), overtime_hours=Decimal("0"), source="manual",
    ))
    db.commit()
    assert _remaining(db, u) == pytest.approx(-1)
    return u


def _remaining_2027(db, user):
    db.expire_all()
    return calculation_service.get_vacation_account(db, user, 2027)["remaining_days"]


def _booked(db, user):
    db.expire_all()
    return {a.date for a in db.query(Absence).filter(Absence.user_id == user.id)}


def _approval_required(db):
    db.merge(SystemSetting(key="vacation_approval_required",
                           tenant_id=DEFAULT_TENANT_ID, value="true"))
    db.commit()


class TestYearWithoutCost:

    def test_direct_booking_ignores_negative_year_it_does_not_touch(self, db, admin):
        """28.12.2026–08.01.2027: 2026 kostet nichts (0 h), 2027 fuenf Tage.
        Vorher: 400 „Nicht genügend Urlaubstage für 2026 (-1.0 …)"."""
        emp = _negative_2026_back_in_2027(db, "b5_ny_direct")

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": DEC_MON_28.isoformat(),
            "end_date": JAN_FRI_08.isoformat(), "type": "vacation", "hours": 8.0,
        })

        assert r.status_code == 201, r.text
        assert _booked(db, emp) == JAN_WEEK
        assert _remaining(db, emp) == pytest.approx(-1)
        assert _remaining_2027(db, emp) == pytest.approx(25)

    def test_direct_booking_only_zero_hour_days_names_real_reason(self, db, admin):
        """Nur 0-h-Tage bei Resturlaub im Minus: die Antwort nennt den echten
        Grund („0 Stunden geplant"), nicht ein fehlendes Budget."""
        emp = _negative_2026_back_in_2027(db, "b5_ny_direct_zero")

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": DEC_MON_28.isoformat(),
            "end_date": DEC_THU_31.isoformat(), "type": "vacation", "hours": 8.0,
        })

        assert r.status_code == 400, r.text
        assert "0 Stunden geplant" in r.json()["detail"]
        assert "Urlaubstage" not in r.json()["detail"]

    def test_direct_booking_still_checks_the_year_it_costs(self, db, admin):
        """Kontrolle: kostet die Buchung im Minus-Jahr etwas, bleibt es 400."""
        emp = _negative_2026_back_in_2027(db, "b5_ny_direct_ctrl")

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": date(2026, 11, 30).isoformat(),
            "end_date": JAN_FRI_08.isoformat(), "type": "vacation", "hours": 8.0,
        })

        assert r.status_code == 400, r.text
        assert r.json()["detail"].startswith("Nicht genügend Urlaubstage für 2026")

    def test_request_create(self, db, admin):
        emp = _negative_2026_back_in_2027(db, "b5_ny_req_create")
        _approval_required(db)

        r = _client_as(db, emp).post("/api/vacation-requests/", json={
            "date": DEC_MON_28.isoformat(), "end_date": JAN_FRI_08.isoformat(),
            "hours": 8.0,
        })

        assert r.status_code == 201, r.text

    def test_request_edit(self, db, admin):
        emp = _negative_2026_back_in_2027(db, "b5_ny_req_edit")
        _approval_required(db)
        vr = VacationRequest(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=JAN_MON_04,
            end_date=JAN_FRI_08, hours=8.0, absence_type="vacation",
            half_day=False, status=VacationRequestStatus.PENDING.value,
        )
        db.add(vr)
        db.commit()

        r = _client_as(db, emp).patch(f"/api/vacation-requests/{vr.id}", json={
            "date": DEC_MON_28.isoformat(),
        })

        assert r.status_code == 200, r.text

    def test_request_approval_books_only_the_costing_year(self, db, admin):
        emp = _negative_2026_back_in_2027(db, "b5_ny_req_review")
        vr = VacationRequest(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=DEC_MON_28,
            end_date=JAN_FRI_08, hours=8.0, absence_type="vacation",
            half_day=False, status=VacationRequestStatus.PENDING.value,
        )
        db.add(vr)
        db.commit()

        r = _client_as(db, admin).post(
            f"/api/admin/vacation-requests/{vr.id}/review", json={"action": "approve"})

        assert r.status_code == 200, r.text
        assert _booked(db, emp) == JAN_WEEK
        assert _remaining_2027(db, emp) == pytest.approx(25)

    def test_budget_helper_skips_years_without_cost(self, db, default_tenant):
        """Der gemeinsame Helfer fragt das Konto eines Jahres ohne Kosten gar
        nicht erst — und meldet das erste Jahr, das nicht reicht."""
        emp = _negative_2026_back_in_2027(db, "b5_ny_helper")
        assert calculation_service.vacation_budget_shortfall(
            db, emp, {2027: Decimal("5")}) is None
        assert calculation_service.vacation_budget_shortfall(
            db, emp, {2026: Decimal("0"), 2027: Decimal("5")}) is None
        assert calculation_service.vacation_budget_shortfall(
            db, emp, {2026: Decimal("1"), 2027: Decimal("5")}) == (2026, pytest.approx(-1))


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


# ── Betriebsferien neu speichern: Altbestand an 0-h-Tagen (Nachzug B5) ────────
#
# Vor B5 legten Betriebsferien im gleichmaessigen Modus an Tagen ohne Tagessoll
# eine 0-h-„Urlaub"-Zeile an. Steht der Vertrag HEUTE auf 0 h, zaehlt das Konto
# jede davon als ganzen Urlaubstag. Neues Speichern raeumt sie jetzt in beiden
# Modi ab (vorher nur bei aktivem #314-Split, und dort mit der falschen
# Begruendung „werden neu gebucht").

def _legacy_zero_rows(db, closure_id, user, days):
    for d in days:
        db.add(Absence(
            user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
            type=AbsenceType.VACATION, hours=0.0, half_day=False,
            note="Betriebsferien: BF", closure_id=uuid.UUID(closure_id),
        ))
    db.commit()


def _resave(client, closure, name="BF neu"):
    r = client.put(f"/api/company-closures/{closure['id']}", json={
        "name": name, "start_date": closure["start_date"],
        "end_date": closure["end_date"], "counts_as_vacation": True,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _closure_rows(db, user):
    db.expire_all()
    return db.query(Absence).filter(
        Absence.user_id == user.id, Absence.closure_id.isnot(None)).all()


def _closure_audit_notes(db):
    db.expire_all()
    return [a.old_note for a in db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.source == "company_closure").all()]


def _split_on(db):
    db.merge(SystemSetting(key="closure_overtime_after_vacation",
                           tenant_id=DEFAULT_TENANT_ID, value="true"))
    db.commit()


class TestClosureResaveCleansZeroHourRows:

    def test_resave_removes_legacy_rows_without_split(self, db, admin):
        """Probe aus dem Review: Elternzeit seit 01.03., zwei Alt-Zeilen an
        0-h-Tagen, Umbenennen bei abgeschaltetem #314-Split → vorher blieben
        beide stehen. Seit Gesamtreview B11 zählt das Urlaubskonto sie schon
        nicht mehr (Stundenzählung an, Tag ohne Soll → 0; bis dahin Resturlaub
        28 statt 30) — das Neuspeichern räumt sie trotzdem ab."""
        emp = _current_parental(db, "b5_rs_off", 30)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _legacy_zero_rows(db, closure["id"], emp, [NOV_MON, NOV_TUE])
        assert len(_closure_rows(db, emp)) == 2
        assert _remaining(db, emp) == pytest.approx(30)

        _resave(client, closure)

        assert _closure_rows(db, emp) == []
        assert _remaining(db, emp) == pytest.approx(30)
        assert any("2 generierte Abwesenheit(en) gelöscht — Tag ohne Tagessoll" in n
                   for n in _closure_audit_notes(db))
        # Die echten Schliesstage der Admin (40 h) bleiben, nur umbenannt.
        admin_rows = _closure_rows(db, admin)
        assert len(admin_rows) == 5
        assert {a.note for a in admin_rows} == {"Betriebsferien: BF neu"}

    def test_resave_with_split_names_the_real_reason(self, db, admin):
        """Bei aktivem Split verschwanden die Alt-Zeilen schon vorher — aber
        unter „werden neu gebucht", obwohl nichts neu gebucht wird."""
        _split_on(db)
        emp = _current_parental(db, "b5_rs_on", 30)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _legacy_zero_rows(db, closure["id"], emp, [NOV_MON, NOV_TUE])

        _resave(client, closure)

        assert _closure_rows(db, emp) == []
        assert _remaining(db, emp) == pytest.approx(30)
        notes = _closure_audit_notes(db)
        assert any("2 generierte Abwesenheit(en) gelöscht — Tag ohne Tagessoll" in n
                   for n in notes)
        # Neu gebucht werden nur die fuenf Tage der Admin.
        assert any("5 generierte Abwesenheit(en) gelöscht — Neuaufteilung" in n
                   for n in notes)
        assert len(_closure_rows(db, admin)) == 5

    def test_planned_zero_hour_period_keeps_working_days(self, db, admin):
        """Gemischte Woche (0 h ab Mi): nur die Alt-Zeilen Mi–Fr gehen, Mo/Di
        (40 h) bleiben als echte Schliesstage."""
        emp = _planned_parental(db, "b5_rs_mixed", 30)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _legacy_zero_rows(db, closure["id"], emp, [NOV_WED, NOV_THU, NOV_FRI])

        _resave(client, closure)

        assert {a.date for a in _closure_rows(db, emp)} == {NOV_MON, NOV_TUE}

    def test_untracked_rows_stay(self, db, admin):
        """#191: ohne Stundenzaehlung ist das Tagessoll immer 0 — deren
        Schliesstage sind echte Urlaubstage und bleiben beim Neuspeichern."""
        emp = _make_user(db, "b5_rs_untracked", track_hours=False)
        _zero_hours_from(db, emp, NOV_WED)
        client = _client_as(db, admin)
        closure = _create_closure(client)

        _resave(client, closure)

        assert len(_closure_rows(db, emp)) == 5

    def test_non_participant_rows_stay_untouched(self, db, admin):
        """Wie bisher fasst das Neuspeichern Zeilen von Personen, die nicht
        (mehr) teilnehmen, nicht an (Release-Review 1.16.0) — die Bereinigung
        gilt den Teilnehmenden, deren Tage dieses Speichern neu entscheidet."""
        emp = _current_parental(db, "b5_rs_optout", 30)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _legacy_zero_rows(db, closure["id"], emp, [NOV_MON, NOV_TUE])
        emp.receives_company_closures = False
        db.commit()

        _resave(client, closure)

        assert len(_closure_rows(db, emp)) == 2


# ── Tage ohne Buchung: kein Schreibschritt (Nachzug B5) ───────────────────────
#
# Direktbuchung und Antrags-Genehmigung loeschten die Zeiteintraege (und bei
# „Krank waehrend Urlaub" den Urlaub) ALLER Kandidaten-Tage, uebersprangen die
# Tage ohne Tagessoll aber erst danach in der Buchungsschleife — dort blieb
# nichts zurueck: Ist und Saldo sanken. Die Betriebsferien pruefen dieselbe
# Bedingung bewusst VOR dem Loeschen. Welche Tage gebucht werden, steht jetzt
# vor dem ersten Schreibschritt fest; nur diese Tage werden angefasst.

def _entry(db, user, d, credit_override=False):
    e = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=time(8, 0), end_time=time(12, 0), break_minutes=0,
        credit_override=credit_override,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _entry_dates(db, user):
    db.expire_all()
    return {e.date for e in db.query(TimeEntry).filter(TimeEntry.user_id == user.id)}


def _day_plan_mo_mi_fr(db, username):
    """Teilzeit Mo/Mi/Fr je 8 h, Di/Do frei (Tagesplan)."""
    u = _make_user(db, username, weekly_hours=24.0)
    u.use_daily_schedule = True
    u.work_days_per_week = 3
    u.hours_monday, u.hours_tuesday, u.hours_wednesday = 8, None, 8
    u.hours_thursday, u.hours_friday = None, 8
    db.commit()
    db.refresh(u)
    return u


def _book(client, emp, start, end, absence_type="vacation", **extra):
    payload = {
        "user_id": str(emp.id), "date": start.isoformat(),
        "end_date": end.isoformat(), "type": absence_type, "hours": 8.0,
    }
    payload.update(extra)
    return client.post("/api/absences/", json=payload)


def _pending_request(db, emp, start, end, absence_type="vacation"):
    vr = VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=start,
        end_date=end, hours=8.0, absence_type=absence_type,
        half_day=False, status=VacationRequestStatus.PENDING.value,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


def _approve(db, admin, vr):
    return _client_as(db, admin).post(
        f"/api/admin/vacation-requests/{vr.id}/review", json={"action": "approve"})


class TestUnbookedDaysKeepTheirData:

    def test_direct_booking_keeps_entry_on_zero_hour_day(self, db, admin):
        """Probe aus dem Review: 0 h ab Mi, Zeiteintrag am Do, Urlaub Mo–Fr →
        gebucht Mo + Di; der Do-Eintrag verschwand ersatzlos."""
        emp = _planned_parental(db, "b5_te_direct", 30)
        _entry(db, emp, NOV_MON)
        _entry(db, emp, NOV_THU)

        r = _book(_client_as(db, admin), emp, NOV_MON, NOV_FRI)

        assert r.status_code == 201, r.text
        assert _booked(db, emp) == {NOV_MON, NOV_TUE}
        # Mo wird wie bisher durch die Abwesenheit ersetzt, Do bleibt.
        assert _entry_dates(db, emp) == {NOV_THU}

    def test_day_plan_stand_in_shift_survives_direct_booking(self, db, admin):
        """Realfall: Teilzeit Mo/Mi/Fr stempelt am freien Di eine Vertretung;
        Urlaub Mo–Fr darf die Di-Stunden nicht loeschen."""
        emp = _day_plan_mo_mi_fr(db, "b5_te_dayplan")
        _entry(db, emp, NOV_TUE)

        r = _book(_client_as(db, admin), emp, NOV_MON, NOV_FRI)

        assert r.status_code == 201, r.text
        assert _booked(db, emp) == {NOV_MON, NOV_WED, NOV_FRI}
        assert _entry_dates(db, emp) == {NOV_TUE}

    def test_other_types_follow_the_same_rule(self, db, admin):
        """Die Bedingung gilt fuer jeden Typ ausser Ueberstundenausgleich im
        gleichmaessigen Modus — hier Fortbildung."""
        emp = _day_plan_mo_mi_fr(db, "b5_te_training")
        _entry(db, emp, NOV_THU)

        r = _book(_client_as(db, admin), emp, NOV_MON, NOV_FRI, "training")

        assert r.status_code == 201, r.text
        assert _entry_dates(db, emp) == {NOV_THU}

    def test_sick_refund_keeps_vacation_on_zero_hour_day(self, db, admin):
        """„Krank waehrend Urlaub": der Urlaub eines Tages, an dem keine
        Krankmeldung gebucht wird (0 h), darf nicht ersatzlos verschwinden."""
        emp = _planned_parental(db, "b5_te_refund", 30)
        for d, h in ((NOV_MON, 8.0), (NOV_THU, 0.0)):
            db.add(Absence(user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                           type=AbsenceType.VACATION, hours=h, half_day=False))
        db.commit()

        r = _book(_client_as(db, admin), emp, NOV_MON, NOV_FRI, "sick",
                  refund_vacation=True)

        assert r.status_code == 201, r.text
        db.expire_all()
        by_date = {a.date: a.type for a in db.query(Absence).filter(Absence.user_id == emp.id)}
        assert by_date == {
            NOV_MON: AbsenceType.SICK, NOV_TUE: AbsenceType.SICK,
            NOV_THU: AbsenceType.VACATION,
        }

    def test_employee_recognized_entry_on_unbooked_day_does_not_block(self, db, admin):
        """Die 409 bei anerkanntem Eintrag schuetzt ihn vor dem Loeschen — an
        einem Tag, den die Buchung nicht anfasst, gibt es nichts zu schuetzen."""
        emp = _day_plan_mo_mi_fr(db, "b5_te_recognized")
        _entry(db, emp, NOV_TUE, credit_override=True)

        r = _client_as(db, emp).post("/api/absences/", json={
            "date": NOV_MON.isoformat(), "end_date": NOV_FRI.isoformat(),
            "type": "sick", "hours": 8.0,
        })

        assert r.status_code == 201, r.text
        assert _entry_dates(db, emp) == {NOV_TUE}

    def test_employee_recognized_entry_on_booked_day_still_blocks(self, db, admin):
        """Kontrolle: auf einem gebuchten Tag bleibt es bei der 409."""
        emp = _day_plan_mo_mi_fr(db, "b5_te_recognized_ctrl")
        _entry(db, emp, NOV_WED, credit_override=True)

        r = _client_as(db, emp).post("/api/absences/", json={
            "date": NOV_MON.isoformat(), "end_date": NOV_FRI.isoformat(),
            "type": "sick", "hours": 8.0,
        })

        assert r.status_code == 409, r.text
        assert "04.11.2026" in r.json()["detail"]

    def test_direct_booking_of_only_zero_hour_days_writes_nothing(self, db, admin):
        """Die 400 „0 Stunden geplant" faellt VOR dem ersten Schreibschritt —
        auch ein Flush danach loescht nichts."""
        emp = _planned_parental(db, "b5_te_direct_zero", 30)
        _entry(db, emp, NOV_THU)

        r = _book(_client_as(db, admin), emp, NOV_WED, NOV_FRI)

        assert r.status_code == 400, r.text
        assert "0 Stunden geplant" in r.json()["detail"]
        db.flush()
        assert _entry_dates(db, emp) == {NOV_THU}

    def test_approval_keeps_entry_on_zero_hour_day(self, db, admin):
        emp = _planned_parental(db, "b5_te_review", 30)
        _entry(db, emp, NOV_MON)
        _entry(db, emp, NOV_THU)
        vr = _pending_request(db, emp, NOV_MON, NOV_FRI)

        r = _approve(db, admin, vr)

        assert r.status_code == 200, r.text
        assert _booked(db, emp) == {NOV_MON, NOV_TUE}
        assert _entry_dates(db, emp) == {NOV_THU}

    def test_approval_day_plan_stand_in_shift_survives(self, db, admin):
        emp = _day_plan_mo_mi_fr(db, "b5_te_review_dayplan")
        _entry(db, emp, NOV_TUE)
        vr = _pending_request(db, emp, NOV_MON, NOV_FRI)

        r = _approve(db, admin, vr)

        assert r.status_code == 200, r.text
        assert _booked(db, emp) == {NOV_MON, NOV_WED, NOV_FRI}
        assert _entry_dates(db, emp) == {NOV_TUE}


class TestApprovalWithoutBookableDay:
    """Ein Antrag nur ueber Tage ohne Tagessoll wurde genehmigt und buchte
    nichts — die Person sah einen genehmigten Urlaub, der keinen Tag deckt.
    Die Direktbuchung antwortet auf denselben Fall mit 400 (U1)."""

    @pytest.mark.parametrize("vacation_days", [30, 0])
    def test_rejected_and_request_stays_pending(self, db, admin, vacation_days):
        emp = _planned_parental(db, f"b5_rv_zero_{vacation_days}", vacation_days)
        _entry(db, emp, NOV_THU)
        vr = _pending_request(db, emp, NOV_WED, NOV_FRI)

        r = _approve(db, admin, vr)

        assert r.status_code == 400, r.text
        assert "0 Stunden geplant" in r.json()["detail"]
        assert "Urlaubstage" not in r.json()["detail"]
        db.flush()
        db.expire_all()
        assert db.get(VacationRequest, vr.id).status == VacationRequestStatus.PENDING.value
        assert _booked(db, emp) == set()
        assert _entry_dates(db, emp) == {NOV_THU}

    def test_other_types_are_rejected_too(self, db, admin):
        emp = _day_plan_mo_mi_fr(db, "b5_rv_zero_training")
        vr = _pending_request(db, emp, NOV_TUE, NOV_TUE, "training")

        r = _approve(db, admin, vr)

        assert r.status_code == 400, r.text
        assert "0 Stunden geplant" in r.json()["detail"]
        db.expire_all()
        assert db.get(VacationRequest, vr.id).status == VacationRequestStatus.PENDING.value

    def test_same_text_as_direct_booking(self, db, admin):
        emp_a = _planned_parental(db, "b5_rv_text_a", 30)
        emp_b = _planned_parental(db, "b5_rv_text_b", 30)
        direct = _book(_client_as(db, admin), emp_a, NOV_WED, NOV_FRI)
        approval = _approve(db, admin, _pending_request(db, emp_b, NOV_WED, NOV_FRI))
        assert direct.status_code == approval.status_code == 400
        assert direct.json()["detail"] == approval.json()["detail"]


# ── Betriebsferien in einem abgeschlossenen Jahr (Nachzug B5) ─────────────────
#
# Das Neuspeichern raeumt 0-h-Altbestand ab — auch in einem Jahr, dessen
# Jahresabschluss schon erstellt ist. Der eingefrorene Uebertrag
# (YearCarryover Y+1) bleibt dabei stehen; das Loeschen einer Schliessung
# meldete das schon immer (Fix #5), Anlegen und Aendern schwiegen. Gemeldet wird
# nur, wenn sich an den Buchungen der Schliessung tatsaechlich etwas aendert —
# ein reines Umbenennen bleibt still.

def _close_year_2026(db, user):
    db.add(YearCarryover(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, year=2027,
        vacation_days=Decimal("28"), overtime_hours=Decimal("0"),
        source="year_closing",
    ))
    db.commit()


class TestClosureWarnsForClosedYear:

    def test_resave_cleanup_in_closed_year_warns(self, db, admin):
        """Probe aus dem Review: Elternzeit, zwei Alt-Zeilen, 2026 abgeschlossen.
        Das Neuspeichern hebt den Resturlaub 2026 von 28 auf 30 — der Uebertrag
        2027 bleibt bei 28, die Antwort schwieg."""
        emp = _current_parental(db, "b5_cy_cleanup", 30)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _legacy_zero_rows(db, closure["id"], emp, [NOV_MON, NOV_TUE])
        _close_year_2026(db, emp)

        body = _resave(client, closure)

        assert _remaining(db, emp) == pytest.approx(30)
        assert body["warning"] and "Jahresabschluss 2026" in body["warning"]

    def test_resave_with_split_in_closed_year_warns(self, db, admin):
        _split_on(db)
        emp = _current_parental(db, "b5_cy_cleanup_split", 30)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _legacy_zero_rows(db, closure["id"], emp, [NOV_MON, NOV_TUE])
        _close_year_2026(db, emp)

        body = _resave(client, closure)

        assert body["warning"] and "Jahresabschluss 2026" in body["warning"]

    def test_shrinking_range_in_closed_year_warns(self, db, admin):
        """Auch das Kuerzen des Zeitraums loescht Buchungen im
        abgeschlossenen Jahr."""
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _close_year_2026(db, admin)

        r = client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "BF", "start_date": NOV_MON.isoformat(),
            "end_date": NOV_WED.isoformat(), "counts_as_vacation": True,
        })

        assert r.status_code == 200, r.text
        assert r.json()["warning"] and "Jahresabschluss 2026" in r.json()["warning"]

    def test_switching_to_paid_leave_in_closed_year_warns(self, db, admin):
        """Urlaub → bezahlte Freistellung aendert den Urlaubsverbrauch des
        abgeschlossenen Jahres."""
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _close_year_2026(db, admin)

        r = client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "BF", "start_date": closure["start_date"],
            "end_date": closure["end_date"], "counts_as_vacation": False,
        })

        assert r.status_code == 200, r.text
        assert r.json()["warning"] and "Jahresabschluss 2026" in r.json()["warning"]

    @pytest.mark.parametrize("split", [False, True])
    def test_plain_rename_in_closed_year_stays_silent(self, db, admin, split):
        """Kontrolle: aendert sich an den Buchungen nichts (auch nicht durch
        die #314-Neuaufteilung), gibt es nichts zu pruefen."""
        if split:
            _split_on(db)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _close_year_2026(db, admin)

        body = _resave(client, closure)

        assert body["warning"] is None

    def test_cleanup_in_open_year_stays_silent(self, db, admin):
        """Kontrolle: ohne Jahresabschluss keine Warnung."""
        emp = _current_parental(db, "b5_cy_open", 30)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _legacy_zero_rows(db, closure["id"], emp, [NOV_MON, NOV_TUE])

        body = _resave(client, closure)

        assert body["warning"] is None

    def test_creating_closure_in_closed_year_warns(self, db, admin):
        """Eine nachgetragene Schliessung im abgeschlossenen Jahr bucht dort
        Urlaub — derselbe veraltete Uebertrag."""
        _close_year_2026(db, admin)

        body = _create_closure(_client_as(db, admin))

        assert body["warning"] and "Jahresabschluss 2026" in body["warning"]

    def test_creating_closure_in_open_year_stays_silent(self, db, admin):
        body = _create_closure(_client_as(db, admin))
        assert body["warning"] is None
