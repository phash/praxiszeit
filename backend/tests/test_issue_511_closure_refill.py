"""#511: a closure day that was skipped because the employee already had a
private absence there must be booked once that absence goes away.

``_create_closure_absences`` skips every day that already holds an absence. If
the private vacation is later withdrawn, cancelled or deleted, the day used to
stay empty: full daily target, no absence, the overtime account dropped by one
day and the mandatory leave was not counted. Every path that frees such a day
now books the closure day again (``closure_split_service.rebook_freed_closure_days``).
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    User, UserRole, Absence, AbsenceType, ChangeRequest, TimeEntry,
)
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.routers.absences import delete_absence
from app.routers.admin_change_requests import review_change_request
from app.routers.admin_vacations import cancel_vacation_request_as_admin
from app.routers.vacation_requests import withdraw_vacation_request
from app.schemas.change_request import ChangeRequestReview
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _future_monday() -> date:
    """First Monday of March next year: in the future (withdraw/cancel only
    accept future requests) and clear of holidays and the 24./31.12. special days."""
    d = date(date.today().year + 1, 3, 1)
    return d + timedelta(days=(7 - d.weekday()) % 7)


MON = _future_monday()
TUE, WED, THU = MON + timedelta(days=1), MON + timedelta(days=2), MON + timedelta(days=3)


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


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30, receives=True):
    u = User(
        username=username, email=f"{username}@x.de", password_hash=auth_service.hash_password("t"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0, vacation_days=vacation_days,
        work_days_per_week=5, is_active=True, track_hours=True, tenant_id=DEFAULT_TENANT_ID,
        receives_company_closures=receives,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "admin1", role=UserRole.ADMIN, receives=False)


@pytest.fixture
def admin_client(db, admin):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: admin
    _app.dependency_overrides[require_admin] = lambda: admin
    yield TestClient(_app)
    _app.dependency_overrides.clear()


def _private_vacation(db, emp, days):
    rows = []
    for d in days:
        a = Absence(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=d,
            type=AbsenceType.VACATION, hours=8.0, half_day=False,
        )
        db.add(a)
        rows.append(a)
    db.commit()
    for a in rows:
        db.refresh(a)
    return rows


def _approved_vr(db, emp, start, end):
    vr = VacationRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=start, end_date=end,
        hours=8.0, absence_type="vacation", status=VacationRequestStatus.APPROVED.value,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


def _make_closure(admin_client, counts_as_vacation=True):
    r = admin_client.post("/api/company-closures/", json={
        "name": "BF", "start_date": MON.isoformat(), "end_date": THU.isoformat(),
        "counts_as_vacation": counts_as_vacation,
    })
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


def _closure_days(db, emp, closure_id):
    return sorted(a.date for a in db.query(Absence).filter(
        Absence.user_id == emp.id, Absence.closure_id == closure_id,
    ).all())


def _set_toggle(db, on):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def test_delete_private_vacation_rebooks_closure_day(db, admin, admin_client):
    emp = _make_user(db, "e_del")
    priv_tue, _ = _private_vacation(db, emp, [TUE, WED])
    closure_id = _make_closure(admin_client)
    assert _closure_days(db, emp, closure_id) == [MON, THU]

    delete_absence(str(priv_tue.id), db=db, current_user=admin)

    assert _closure_days(db, emp, closure_id) == [MON, TUE, THU]
    tue = db.query(Absence).filter(Absence.user_id == emp.id, Absence.date == TUE).one()
    assert tue.type == AbsenceType.VACATION
    assert tue.note == "Betriebsferien: BF"


def test_deleting_a_closure_day_itself_is_not_rebooked(db, admin, admin_client):
    """The admin deliberately removes a closure day (e.g. the person worked) —
    putting it straight back would make the delete impossible."""
    emp = _make_user(db, "e_closure_del")
    closure_id = _make_closure(admin_client)
    tue = db.query(Absence).filter(Absence.user_id == emp.id, Absence.date == TUE).one()

    delete_absence(str(tue.id), db=db, current_user=admin)

    assert _closure_days(db, emp, closure_id) == [MON, WED, THU]


def test_withdraw_approved_vacation_request_rebooks_closure_days(db, admin, admin_client):
    emp = _make_user(db, "e_withdraw")
    _private_vacation(db, emp, [TUE, WED])
    vr = _approved_vr(db, emp, TUE, WED)
    closure_id = _make_closure(admin_client)
    assert _closure_days(db, emp, closure_id) == [MON, THU]

    withdraw_vacation_request(str(vr.id), db=db, current_user=emp)

    assert _closure_days(db, emp, closure_id) == [MON, TUE, WED, THU]


def test_admin_cancel_approved_vacation_request_rebooks_closure_days(db, admin, admin_client):
    emp = _make_user(db, "e_cancel")
    _private_vacation(db, emp, [TUE, WED])
    vr = _approved_vr(db, emp, TUE, WED)
    closure_id = _make_closure(admin_client)

    cancel_vacation_request_as_admin(str(vr.id), db=db, current_user=admin)

    assert _closure_days(db, emp, closure_id) == [MON, TUE, WED, THU]


def test_cancel_keeps_closure_days_inside_the_request_range(db, admin, admin_client):
    """A request range that overlaps closure days must not take the closure's
    own VACATION rows with it on cancel."""
    emp = _make_user(db, "e_overlap")
    closure_id = _make_closure(admin_client)
    vr = _approved_vr(db, emp, WED, THU + timedelta(days=1))  # Wed–Fri, Fri private
    _private_vacation(db, emp, [THU + timedelta(days=1)])

    withdraw_vacation_request(str(vr.id), db=db, current_user=emp)

    assert _closure_days(db, emp, closure_id) == [MON, TUE, WED, THU]
    assert db.query(Absence).filter(
        Absence.user_id == emp.id, Absence.date == THU + timedelta(days=1),
    ).count() == 0


def _absence_cr(db, emp, request_type, **kwargs):
    cr = ChangeRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, request_type=request_type,
        entry_kind="absence", status=ChangeRequestStatus.PENDING, reason="Test", **kwargs,
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


def test_cr_delete_rebooks_closure_day(db, admin, admin_client):
    emp = _make_user(db, "e_cr_del")
    priv_tue, = _private_vacation(db, emp, [TUE])
    closure_id = _make_closure(admin_client)

    cr = _absence_cr(db, emp, ChangeRequestType.DELETE, absence_id=priv_tue.id)
    review_change_request(
        request_id=str(cr.id), review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )

    assert _closure_days(db, emp, closure_id) == [MON, TUE, WED, THU]


def test_cr_update_moving_away_rebooks_the_old_day(db, admin, admin_client):
    emp = _make_user(db, "e_cr_move")
    priv_tue, = _private_vacation(db, emp, [TUE])
    closure_id = _make_closure(admin_client)
    later = THU + timedelta(days=7)

    cr = _absence_cr(
        db, emp, ChangeRequestType.UPDATE, absence_id=priv_tue.id,
        proposed_date=later, proposed_absence_type="vacation",
    )
    review_change_request(
        request_id=str(cr.id), review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )

    assert _closure_days(db, emp, closure_id) == [MON, TUE, WED, THU]


def test_non_participant_gets_nothing(db, admin, admin_client):
    emp = _make_user(db, "e_out", receives=False)
    priv_tue, = _private_vacation(db, emp, [TUE])
    closure_id = _make_closure(admin_client)

    delete_absence(str(priv_tue.id), db=db, current_user=admin)

    assert _closure_days(db, emp, closure_id) == []


def test_day_with_logged_work_is_not_rebooked(db, admin, admin_client):
    """Rebooking never replaces logged work (#290, delete_time_entries=False)."""
    from datetime import time
    emp = _make_user(db, "e_work")
    priv_tue, = _private_vacation(db, emp, [TUE])
    closure_id = _make_closure(admin_client)
    db.add(TimeEntry(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=TUE,
        start_time=time(8, 0), end_time=time(12, 0), break_minutes=0,
    ))
    db.commit()

    delete_absence(str(priv_tue.id), db=db, current_user=admin)

    assert _closure_days(db, emp, closure_id) == [MON, WED, THU]
    assert db.query(TimeEntry).filter(TimeEntry.user_id == emp.id).count() == 1


def test_rebooked_day_follows_the_overtime_split(db, admin, admin_client):
    """Toggle on, no vacation budget: every closure day is OVERTIME. The
    rebooked day must be OVERTIME too, never minus vacation."""
    emp = _make_user(db, "e_split", vacation_days=0)
    _set_toggle(db, True)
    priv_tue, = _private_vacation(db, emp, [TUE])
    closure_id = _make_closure(admin_client)

    delete_absence(str(priv_tue.id), db=db, current_user=admin)

    rows = db.query(Absence).filter(
        Absence.user_id == emp.id, Absence.closure_id == closure_id,
    ).order_by(Absence.date).all()
    assert [r.date for r in rows] == [MON, TUE, WED, THU]
    assert all(r.type == AbsenceType.OVERTIME for r in rows), [(r.date, r.type) for r in rows]
