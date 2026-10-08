"""#496: „Arbeitstage" eines Abwesenheitsantrags zaehlt nach derselben Regel wie
die Buchung bei der Genehmigung.

Vorher setzte ``admin_helpers._enrich_vr_responses`` ``days`` ueber
``count_workdays`` = stumpf Mo–Fr ohne Feiertage. Die Genehmigung bucht und
verbraucht aber nur die Tage, an denen die Person laut ihrem zum DATUM
aufgeloesten Vertrags-Snapshot (#431) ueberhaupt arbeitet, ein Halbtag kostet
0,5, ein 'free'-Sondertag (24./31.12.) gar nichts, ein 'half_day'-Sondertag 0,5
(#394). Die Admin entschied im Genehmigungsdialog also auf Basis einer Zahl, die
dem Urlaubskonto nach der Genehmigung widersprach — bei jeder Teilzeitkraft mit
Tagesplan sichtbar (Kunden-Demo: Julia Wagner, Mi frei, Antrag Mo–Fr → „5 Tage",
gebucht 4).

Beide Lesepfade (Admin-Liste + „Meine Anträge" der Mitarbeitenden) laufen ueber
denselben Enricher; beide werden hier geprueft. Zusaetzlich nageln die
Paritaetstests fest, dass die angezeigte Zahl exakt dem entspricht, was die
Genehmigung danach im Urlaubskonto verbraucht.
"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, PublicHoliday, User, UserRole, WorkingHoursChange
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.services import auth_service, calculation_service
from tests.conftest import DEFAULT_TENANT_ID, TestingSessionLocal, engine

# 02.11.2026 ist ein Montag (Reproduktion aus dem Issue).
NOV_MON, NOV_FRI = date(2026, 11, 2), date(2026, 11, 6)
NOV_WED = date(2026, 11, 4)
# 21.12.2026 = Montag, 24.12.2026 = Donnerstag.
DEC_MON, DEC_THU = date(2026, 12, 21), date(2026, 12, 24)


def _create_test_app() -> FastAPI:
    from app.core.limiter import limiter
    from app.routers import admin_vacations, vacation_requests
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(admin_vacations.router)
    app.include_router(vacation_requests.router)
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


@pytest.fixture(scope="function")
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default",
               is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, *, role=UserRole.EMPLOYEE, vacation_days=30,
               track_hours=True, use_daily_schedule=False, weekly_hours=40.0,
               work_days_per_week=5, day_hours=(None,) * 5, last_work_day=None):
    u = User(
        username=username, email=f"{username}@x.de",
        password_hash=auth_service.hash_password("x"),
        first_name=username, last_name="T", role=role,
        weekly_hours=weekly_hours, vacation_days=vacation_days,
        work_days_per_week=work_days_per_week, is_active=True,
        track_hours=track_hours, use_daily_schedule=use_daily_schedule,
        hours_monday=day_hours[0], hours_tuesday=day_hours[1],
        hours_wednesday=day_hours[2], hours_thursday=day_hours[3],
        hours_friday=day_hours[4], last_work_day=last_work_day,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _julia(db, username="j.wagner"):
    """Die Kunden-Demo-Konstellation: 4-Tage-Woche, Tagesplan
    Mo 7 / Di 4,5 / Mi 0 / Do 7 / Fr 4,5."""
    return _make_user(
        db, username, use_daily_schedule=True, weekly_hours=23.0,
        work_days_per_week=4, day_hours=(7.0, 4.5, 0.0, 7.0, 4.5),
    )


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "adm1", role=UserRole.ADMIN)


def _pending(db, user, start, end=None, *, half_day=False, absence_type="vacation"):
    vr = VacationRequest(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=start, end_date=end,
        hours=8.0, absence_type=absence_type, half_day=half_day,
        status=VacationRequestStatus.PENDING.value,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


def _client_as(db, user):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: user
    _app.dependency_overrides[require_admin] = lambda: user
    return TestClient(_app)


def _admin_days(db, admin, vr):
    r = _client_as(db, admin).get("/api/admin/vacation-requests")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x["id"] == str(vr.id))
    return row["days"]


def _own_days(db, emp, vr):
    r = _client_as(db, emp).get("/api/vacation-requests/")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x["id"] == str(vr.id))
    return row["days"]


def _approve(db, admin, vr):
    r = _client_as(db, admin).post(
        f"/api/admin/vacation-requests/{vr.id}/review", json={"action": "approve"})
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    return r.json()


def _set(db, key, value):
    db.add(SystemSetting(key=key, tenant_id=DEFAULT_TENANT_ID, value=value))
    db.commit()


# ── Reproduktion aus dem Issue ───────────────────────────────────────────────

class TestDayPlanWithFreeWeekday:

    def test_admin_list_counts_only_the_four_working_days(self, db, admin):
        emp = _julia(db)
        vr = _pending(db, emp, NOV_MON, NOV_FRI)
        assert _admin_days(db, admin, vr) == 4

    def test_employee_list_shows_the_same_number(self, db, admin):
        """„Meine Anträge" laeuft ueber denselben Enricher — dieselbe Zahl."""
        emp = _julia(db)
        vr = _pending(db, emp, NOV_MON, NOV_FRI)
        assert _own_days(db, emp, vr) == 4

    def test_free_weekday_without_value_counts_as_well(self, db, admin):
        """Mi ``None`` (nicht eingetragen) statt 0 h — derselbe freie Tag."""
        emp = _make_user(db, "none_wed", use_daily_schedule=True, weekly_hours=23.0,
                         work_days_per_week=4, day_hours=(7.0, 4.5, None, 7.0, 4.5))
        vr = _pending(db, emp, NOV_MON, NOV_FRI)
        assert _admin_days(db, admin, vr) == 4

    def test_display_matches_what_approval_consumes(self, db, admin):
        """Die angezeigte Zahl ist exakt der Verbrauch nach der Genehmigung."""
        emp = _julia(db)
        vr = _pending(db, emp, NOV_MON, NOV_FRI)
        shown = _admin_days(db, admin, vr)

        approved = _approve(db, admin, vr)

        assert approved["days"] == shown == 4
        booked = db.query(Absence).filter(Absence.user_id == emp.id).all()
        assert NOV_WED not in {a.date for a in booked}
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(shown)

    def test_non_vacation_request_counts_the_same_days(self, db, admin):
        """Auch ein Fortbildungs-Antrag bucht nur die Arbeitstage der Person —
        die Anzeige „Arbeitstage" gilt fuer jeden Antragstyp."""
        emp = _julia(db)
        vr = _pending(db, emp, NOV_MON, NOV_FRI, absence_type="training")
        assert _admin_days(db, admin, vr) == 4
        _approve(db, admin, vr)
        assert db.query(Absence).filter(Absence.user_id == emp.id).count() == 4


# ── Halbtag ──────────────────────────────────────────────────────────────────

class TestHalfDay:

    def test_half_day_request_shows_half_a_day(self, db, admin):
        emp = _make_user(db, "half")
        vr = _pending(db, emp, NOV_MON, half_day=True)
        assert _admin_days(db, admin, vr) == 0.5
        _approve(db, admin, vr)
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(0.5)


# ── Sondertage 24./31.12. ────────────────────────────────────────────────────

class TestSpecialDays:

    def test_free_special_day_does_not_count(self, db, admin):
        """24.12. als 'free' ist kein Arbeitstag — Mo–Do kostet 3, nicht 4."""
        _set(db, "special_day_dec24_mode", "free")
        _set(db, "special_day_dec24_counts_as_vacation", "false")
        emp = _make_user(db, "free24")
        vr = _pending(db, emp, DEC_MON, DEC_THU)
        assert _admin_days(db, admin, vr) == 3
        _approve(db, admin, vr)
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(3)

    def test_half_special_day_counts_half(self, db, admin):
        """24.12. als halber Feiertag kostet 0,5 (#394) — Mo–Do = 3,5."""
        _set(db, "special_day_dec24_mode", "half_day")
        emp = _make_user(db, "half24")
        vr = _pending(db, emp, DEC_MON, DEC_THU)
        assert _admin_days(db, admin, vr) == 3.5
        _approve(db, admin, vr)
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(3.5)

    def test_without_special_day_rule_all_four_count(self, db, admin):
        """Kontrolle: ohne Sondertags-Regel ist der 24.12. ein normaler Arbeitstag."""
        emp = _make_user(db, "plain24")
        vr = _pending(db, emp, DEC_MON, DEC_THU)
        assert _admin_days(db, admin, vr) == 4


# ── #431: Snapshot je Datum, nicht das Live-Flag ─────────────────────────────

class TestResolvedSchedulePerDate:

    def test_mode_switch_inside_the_request(self, db, admin):
        """Mo/Mi/Fr-Tagesplan bis 30.09.2026, ab 01.10. gleichmaessig (Live-Zeile
        steht bereits auf gleichmaessig). Antrag Mo 28.09.–Fr 02.10.: Di 29.09.
        ist im alten Plan frei → 4 Tage, nicht 5."""
        emp = _make_user(db, "switcher", weekly_hours=40.0, work_days_per_week=5)
        db.add(WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=date(2026, 1, 1), weekly_hours=Decimal("24.0"),
            use_daily_schedule=True, hours_monday=Decimal("8.0"),
            hours_wednesday=Decimal("8.0"), hours_friday=Decimal("8.0"),
            work_days_per_week=3,
        ))
        db.add(WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=date(2026, 10, 1), weekly_hours=Decimal("40.0"),
            use_daily_schedule=False, work_days_per_week=5,
        ))
        db.commit()
        vr = _pending(db, emp, date(2026, 9, 28), date(2026, 10, 2))
        assert _admin_days(db, admin, vr) == 4
        _approve(db, admin, vr)
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(4)


# ── Was sich NICHT aendern darf ──────────────────────────────────────────────

class TestUnchangedCases:

    def test_full_time_week_still_five(self, db, admin):
        emp = _make_user(db, "fulltime")
        vr = _pending(db, emp, NOV_MON, NOV_FRI)
        assert _admin_days(db, admin, vr) == 5

    def test_public_holiday_still_excluded(self, db, admin):
        db.add(PublicHoliday(date=NOV_WED, name="Testfeiertag", year=2026,
                             tenant_id=DEFAULT_TENANT_ID))
        db.commit()
        emp = _make_user(db, "holiday")
        vr = _pending(db, emp, NOV_MON, NOV_FRI)
        assert _admin_days(db, admin, vr) == 4

    def test_untracked_employee_counts_every_working_day(self, db, admin):
        """Leitende Angestellte (#191): Tagessoll immer 0, tagebasiert zaehlt
        trotzdem jeder Werktag — sie duerfen nicht auf 0 fallen."""
        emp = _make_user(db, "lead", track_hours=False)
        vr = _pending(db, emp, NOV_MON, NOV_FRI)
        assert _admin_days(db, admin, vr) == 5

    def test_weekend_only_request_is_zero(self, db, admin):
        emp = _make_user(db, "weekend")
        vr = _pending(db, emp, date(2026, 11, 7), date(2026, 11, 8))
        assert _admin_days(db, admin, vr) == 0


# ── Beschaeftigungsfenster ───────────────────────────────────────────────────

class TestEmploymentWindow:

    def test_days_after_last_work_day_do_not_count(self, db, admin):
        """Antrag Mo–Fr gestellt, danach Austritt zum Mi gesetzt
        (``update_user`` raeumt offene Antraege nicht ab). Do/Fr sind keine
        Arbeitstage der Person mehr — das Urlaubskonto zaehlt sie ebenfalls
        nicht (Audit 2026-07-31, Fund B)."""
        emp = _make_user(db, "leaver")
        vr = _pending(db, emp, NOV_MON, NOV_FRI)
        emp.last_work_day = NOV_WED
        db.commit()
        assert _admin_days(db, admin, vr) == 3


# ── Kein N+1 in der Liste ────────────────────────────────────────────────────

class TestListQueryCost:

    def test_contract_history_is_loaded_once_for_the_whole_list(self, db, admin):
        """Die Tage-Zaehlung loest den Tagesplan je Datum auf. Die Vertrags-
        Historie laedt der Enricher EINMAL fuer alle Antraege der Liste — nicht
        je Antrag und erst recht nicht je Tag (Liste bis 500 Eintraege)."""
        emps = [_julia(db, f"j{i}") for i in range(3)]
        for e in emps:
            _pending(db, e, NOV_MON, NOV_FRI)
            _pending(db, e, DEC_MON, DEC_THU)

        count = {"n": 0}

        def _listener(conn, cursor, statement, parameters, context, executemany):
            if "from working_hours_changes" in statement.lower():
                count["n"] += 1

        event.listen(engine, "before_cursor_execute", _listener)
        try:
            r = _client_as(db, admin).get("/api/admin/vacation-requests")
        finally:
            event.remove(engine, "before_cursor_execute", _listener)
            _app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        # Nov Mo–Fr = 4 (Mi frei), Dez Mo–Do = 3 (Mi frei).
        assert sorted(x["days"] for x in r.json()) == [3, 3, 3, 4, 4, 4]
        assert count["n"] == 1, f"erwartet 1 Historien-Abfrage, gemessen {count['n']}"
