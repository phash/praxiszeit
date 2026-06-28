"""#314: Betriebsferien über den Jahresurlaub hinaus als Überstundenabbau buchen.

Globales Setting `closure_overtime_after_vacation` (Default aus). Ist es an UND
zählt die Schließung als Urlaub (`counts_as_vacation`), werden Closure-Arbeitstage
chronologisch zuerst als VACATION gebucht (bis das Rest-Urlaubsbudget erschöpft
ist) und danach als OVERTIME (Überstundenausgleich → Überstundenkonto sinkt,
darf ins Minus) — statt Minus-Urlaub zu erzeugen.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, Absence, AbsenceType
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

# Mon–Thu in a clean week (4 workdays), no holidays seeded.
MON, TUE, WED, THU = date(2025, 3, 10), date(2025, 3, 11), date(2025, 3, 12), date(2025, 3, 13)


def _create_test_app() -> FastAPI:
    from app.routers import company_closures
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30, track_hours=True):
    u = User(
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("test123"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=track_hours, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "admin1", role=UserRole.ADMIN)


@pytest.fixture
def admin_client(db, admin):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: admin
    _app.dependency_overrides[require_admin] = lambda: admin
    yield TestClient(_app)
    _app.dependency_overrides.clear()


def _set_toggle(db, on: bool):
    # merge → upsert: safe to call twice (flip OFF→ON) despite the (key, tenant_id) PK.
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def _create_closure(client, counts_as_vacation=True):
    r = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": MON.isoformat(), "end_date": THU.isoformat(),
        "counts_as_vacation": counts_as_vacation,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _types(db, user, closure_id):
    return [a.type for a in db.query(Absence).filter(
        Absence.user_id == user.id, Absence.closure_id == uuid.UUID(closure_id),
    ).order_by(Absence.date).all()]


class TestClosureOvertimeSplit:
    def test_setting_off_all_vacation(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_off", vacation_days=2)  # low budget, but setting OFF
        _set_toggle(db, False)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.VACATION] * 4

    def test_budget_covers_all(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_full", vacation_days=30)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.VACATION] * 4

    def test_partial_budget_splits_vacation_then_overtime(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_part", vacation_days=2)  # exactly 2 days budget
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        # first 2 days consume the budget as VACATION, the rest become OVERTIME
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]

    def test_zero_target_scheduled_day_does_not_consume_budget(self, db, default_tenant, admin_client):
        # round-1 finding: a use_daily_schedule part-timer's 0-target weekday must
        # NOT consume the vacation budget, else real working days wrongly go to OVERTIME.
        FRI = date(2025, 3, 14)
        emp = User(
            username="e_dsched", email="dsched@x.de", password_hash=auth_service.hash_password("test123"),
            first_name="D", last_name="S", role=UserRole.EMPLOYEE, weekly_hours=24.0, vacation_days=2,
            work_days_per_week=3, is_active=True, track_hours=True, use_daily_schedule=True,
            hours_monday=8, hours_tuesday=0, hours_wednesday=8, hours_thursday=0, hours_friday=8,
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(emp); db.commit(); db.refresh(emp)
        _set_toggle(db, True)
        r = admin_client.post("/api/company-closures/", json={
            "name": "BF", "start_date": MON.isoformat(), "end_date": FRI.isoformat(), "counts_as_vacation": True,
        })
        assert r.status_code == 201, r.text
        c = r.json()
        by_date = {a.date: a.type for a in db.query(Absence).filter(
            Absence.user_id == emp.id, Absence.closure_id == uuid.UUID(c["id"])).all()}
        # the two real 8h days (Mon, Wed) consume the 2-day budget as VACATION; Fri → OVERTIME.
        # Tue/Thu are 0-target days and must NOT have burned budget.
        assert by_date[MON] == AbsenceType.VACATION
        assert by_date[WED] == AbsenceType.VACATION
        assert by_date[FRI] == AbsenceType.OVERTIME

    def test_zero_budget_all_overtime(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_zero", vacation_days=0)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.OVERTIME] * 4

    def test_paid_leave_closure_ignores_setting(self, db, default_tenant, admin_client):
        emp = _make_user(db, "e_pl", vacation_days=0)
        _set_toggle(db, True)
        c = _create_closure(admin_client, counts_as_vacation=False)
        # not a vacation closure → setting does not apply, stays PAID_LEAVE
        assert _types(db, emp, c["id"]) == [AbsenceType.PAID_LEAVE] * 4

    def test_skip_does_not_consume_budget(self, db, default_tenant, admin_client):
        # ArbZG-audit #4: a day skipped (here: pre-existing foreign SICK absence)
        # must NOT consume the vacation budget.
        emp = _make_user(db, "e_skip", vacation_days=1)
        db.add(Absence(user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=MON,
                       type=AbsenceType.SICK, hours=8.0))
        db.commit()
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        # MON is skipped (foreign SICK); the 1-day budget is still free for TUE → VACATION,
        # WED/THU become OVERTIME. (If the skip had consumed the budget, TUE would be OVERTIME.)
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]


def _update(client, cid, counts_as_vacation, name="BF"):
    r = client.put(f"/api/company-closures/{cid}", json={
        "name": name, "start_date": MON.isoformat(), "end_date": THU.isoformat(),
        "counts_as_vacation": counts_as_vacation,
    })
    assert r.status_code == 200, r.text
    return r.json()


class TestClosureOvertimeSplitUpdate:
    def test_update_resplits_and_keeps_overtime(self, db, default_tenant, admin_client):
        # ArbZG-audit #1: a PUT must not turn budget-exhausted OVERTIME days back
        # into VACATION. Re-saving the split closure re-splits identically.
        emp = _make_user(db, "e_up", vacation_days=2)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]
        _update(admin_client, c["id"], counts_as_vacation=True, name="BF-neu")
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]

    def test_resave_applies_split_after_enabling_toggle(self, db, default_tenant, admin_client):
        # #314 follow-up (customer philvdb): a closure booked while the toggle was
        # OFF is all-VACATION (= minus-vacation once the budget is exceeded). After
        # the admin flips the global switch ON, a plain re-save (no date/flag change)
        # must re-apply the split so the surplus days become OVERTIME instead of
        # minus-vacation. Flipping the switch alone is not enough; re-saving is.
        emp = _make_user(db, "e_resave", vacation_days=2)
        _set_toggle(db, False)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.VACATION] * 4
        _set_toggle(db, True)
        _update(admin_client, c["id"], counts_as_vacation=True)  # plain re-save, unchanged name/dates
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]

    def test_rename_resplits_idempotently(self, db, default_tenant, admin_client):
        # #314 follow-up: re-save now re-applies the split (so flipping the global
        # toggle takes effect on existing closures via a re-save). A rename therefore
        # delete-and-recreates the in-range absences, but the re-split is computed
        # against the budget WITHOUT this closure's own days → value-stable
        # (idempotent): VACATION while the budget covers, OVERTIME after.
        emp = _make_user(db, "e_rn", vacation_days=2)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        _update(admin_client, c["id"], counts_as_vacation=True, name="BF-umbenannt")
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]

    def test_untracked_employee_keeps_vacation_not_overtime(self, db, default_tenant, admin_client):
        # Review finding: an untracked MA (track_hours=False) has no overtime
        # account → the split must NOT apply (legacy VACATION), otherwise the
        # surplus day vanishes from all accounting.
        emp = _make_user(db, "e_unt", vacation_days=0, track_hours=False)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.VACATION] * 4


def _book_vacation_workdays(db, user, start: date, count: int):
    """Book `count` VACATION workdays starting at `start` (skips weekends)."""
    d, booked = start, 0
    while booked < count:
        if d.weekday() < 5:
            db.add(Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                           type=AbsenceType.VACATION, hours=8.0, half_day=False))
            booked += 1
        d += timedelta(days=1)
    db.commit()


class TestClosureOvertimeSplitBudgetAndOffday:
    """#314 reopened (philvdb): die Closure zehrt den VERBLEIBENDEN Jahres-Resturlaub
    chronologisch bis 0 auf und bucht den Rest als Überstundenausgleich — NIE
    Minus-Urlaub, auch wenn SPÄTER im Jahr Urlaub (Sommer) gebucht ist (der zählt
    korrekt mit). Plus: an Nicht-Arbeitstagen eines use_daily_schedule-Teilzeitlers
    wird keine irreführende 0-Std-Urlaubszeile gebucht."""

    def test_future_vacation_consumes_remaining_then_overtime_no_minus(self, db, default_tenant, admin_client):
        # Bereits (für den Sommer) gebuchter Urlaub schöpft das Jahresbudget mit aus:
        # die Closure darf nur den VERBLEIBENDEN Urlaub als VACATION nehmen, der Rest
        # wird Überstundenausgleich. Der Jahresurlaub darf dadurch NIE ins Minus.
        from app.services import calculation_service
        emp = _make_user(db, "e_future", vacation_days=10)
        _book_vacation_workdays(db, emp, date(2025, 8, 4), 8)  # 8 von 10 Tagen im Sommer verplant
        _set_toggle(db, True)
        c = _create_closure(admin_client)  # MON..THU (4 Arbeitstage im März)
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]
        # Kein Minus-Urlaub: 8 (Sommer) + 2 (Closure-Urlaub) = 10 = Budget.
        assert calculation_service.get_vacation_account(db, emp, 2025)["remaining_days"] == 0.0

    def test_past_vacation_reduces_closure_budget(self, db, default_tenant, admin_client):
        # 2 vacation days taken BEFORE the closure (February) with budget 3 →
        # only 1 day left at closure time → 1 VACATION + 3 OVERTIME.
        emp = _make_user(db, "e_past", vacation_days=3)
        _book_vacation_workdays(db, emp, date(2025, 2, 3), 2)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]

    def test_use_daily_schedule_offday_not_booked(self, db, default_tenant, admin_client):
        # #314 secondary: a use_daily_schedule part-timer (Mon/Wed/Fri only) must NOT
        # get a misleading 0-hour VACATION row on their non-work weekdays (Tue/Thu).
        FRI = date(2025, 3, 14)
        emp = User(
            username="e_offday", email="offday@x.de", password_hash=auth_service.hash_password("test123"),
            first_name="O", last_name="D", role=UserRole.EMPLOYEE, weekly_hours=24.0, vacation_days=30,
            work_days_per_week=3, is_active=True, track_hours=True, use_daily_schedule=True,
            hours_monday=8, hours_tuesday=0, hours_wednesday=8, hours_thursday=0, hours_friday=8,
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(emp); db.commit(); db.refresh(emp)
        _set_toggle(db, True)
        r = admin_client.post("/api/company-closures/", json={
            "name": "BF", "start_date": MON.isoformat(), "end_date": FRI.isoformat(), "counts_as_vacation": True})
        assert r.status_code == 201, r.text
        booked = {a.date for a in db.query(Absence).filter(
            Absence.user_id == emp.id, Absence.closure_id == uuid.UUID(r.json()["id"])).all()}
        assert booked == {MON, WED, FRI}  # Tue/Thu (0-Tagessoll) NOT booked

    def test_untracked_booked_on_all_workdays(self, db, default_tenant, admin_client):
        # Counter-test to the off-day skip: an untracked MA (track_hours=False,
        # daily_target always 0) must STILL get one VACATION per workday (Tagesprinzip
        # #191) — the skip is only for use_daily_schedule off-weekdays.
        emp = _make_user(db, "e_unt2", vacation_days=30, track_hours=False)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        assert _types(db, emp, c["id"]) == [AbsenceType.VACATION] * 4

    def test_double_toggle_through_paid_leave_no_minus_vacation(self, db, default_tenant, admin_client):
        # The exact audit bug: split → Freistellung → zurück zu Urlaub must NOT
        # produce 4× VACATION at budget 2 (= minus-vacation), but re-split.
        emp = _make_user(db, "e_dt", vacation_days=2)
        _set_toggle(db, True)
        c = _create_closure(admin_client)
        _update(admin_client, c["id"], counts_as_vacation=False)  # → all PAID_LEAVE
        assert _types(db, emp, c["id"]) == [AbsenceType.PAID_LEAVE] * 4
        _update(admin_client, c["id"], counts_as_vacation=True)   # → re-split, NOT 4× VACATION
        assert _types(db, emp, c["id"]) == [
            AbsenceType.VACATION, AbsenceType.VACATION, AbsenceType.OVERTIME, AbsenceType.OVERTIME,
        ]
