"""Teil B Task 4: Gutschrift (SICK/TRAINING) folgt dem verkuerzten Soll,
Urlaub am verkuerzten Tag kostet 0,5 Tag, eigene verkuerzte Tage (z. B.
Rosenmontag) laden ihre Config auch ohne 24./31.12.-Vorfilter."""
from datetime import date, time
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, TimeEntry
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.reduced_days_helpers import make_user_3h, reduce_day as _reduce

D24 = date(2026, 12, 24)   # Donnerstag
RM = date(2026, 2, 16)     # Rosenmontag (Montag), eigener verkuerzter Tag


def _absence(db, user, d, atype, hours, half_day=False):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=atype,
                hours=Decimal(str(hours)), half_day=half_day)
    db.add(a)
    db.commit()
    return a


def _entry(db, user, d, start, end):
    e = TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                  start_time=start, end_time=end, break_minutes=0)
    db.add(e)
    db.commit()
    return e


def _day_delta(db, user, d):
    return (calculation_service.get_range_actual(db, user, d, d)
            - calculation_service.get_range_target(db, user, d, d))


@pytest.fixture
def user_3h(db, default_tenant):
    return make_user_3h(db)


def _client(db, admin):
    from app.core.limiter import limiter
    from app.routers import absences
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(app)


def _post_sick_keep(db, admin, user, d):
    client = _client(db, admin)
    resp = client.post("/api/absences/", json={
        "user_id": str(user.id), "date": d.isoformat(), "type": "sick",
        "hours": 8.0, "keep_time_entries": True,
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body[0] if isinstance(body, list) else body


def test_credit_weight_max_hours():
    cfg = {D24: {"mode": "max_hours", "counts_as_vacation": False, "max_hours": Decimal("4"), "label": "Heiligabend"}}
    assert calculation_service.credit_day_weight(D24, set(), cfg, daily_target=Decimal("8")) == Decimal("0.5")
    assert calculation_service.credit_day_weight(D24, set(), cfg, daily_target=Decimal("3")) == Decimal("1")
    assert calculation_service.credit_day_weight(D24, set(), cfg, daily_target=Decimal("0")) == Decimal("0")
    with pytest.raises(ValueError, match="daily_target"):
        calculation_service.credit_day_weight(D24, set(), cfg)
    assert (Decimal("7") * calculation_service.credit_day_weight(D24, set(), cfg, daily_target=Decimal("7"))).quantize(Decimal("0.01")) == Decimal("4.00")


def test_credit_weight_holiday_and_weekend_beat_reduced_day():
    sat = date(2026, 12, 26)
    cfg = {D24: {"mode": "max_hours", "counts_as_vacation": False, "max_hours": Decimal("4"), "label": "x"},
           sat: {"mode": "max_hours", "counts_as_vacation": False, "max_hours": Decimal("4"), "label": "x"}}
    assert calculation_service.credit_day_weight(D24, {D24}, cfg) == Decimal("0")
    assert calculation_service.credit_day_weight(sat, set(), cfg) == Decimal("0")


def test_sick_on_reduced_day_saldo_neutral(db, test_user):
    _reduce(db, D24, "4")
    # Startpunkt fuer Konto/Historie (erster Zeiteintrag im Dezember)
    _entry(db, test_user, date(2026, 12, 1), time(8, 0), time(16, 0))
    sick = _absence(db, test_user, D24, AbsenceType.SICK, 8)

    assert _day_delta(db, test_user, D24) == Decimal("0")

    acc_with = calculation_service.get_overtime_account(db, test_user, 2026, 12)
    ytd_with = calculation_service.get_ytd_summary(db, test_user, 2026, cutoff_date=date(2026, 12, 31))["overtime"]
    hist_with = calculation_service.get_overtime_history(db, test_user, 2026, 12)[(2026, 12)]
    db.delete(sick)
    db.commit()
    acc_without = calculation_service.get_overtime_account(db, test_user, 2026, 12)
    ytd_without = calculation_service.get_ytd_summary(db, test_user, 2026, cutoff_date=date(2026, 12, 31))["overtime"]
    hist_without = calculation_service.get_overtime_history(db, test_user, 2026, 12)[(2026, 12)]

    # Ohne Krankmeldung fehlen am Tag 4 h Soll; mit ihr ist der Tag neutral.
    assert acc_with - acc_without == Decimal("4")
    assert Decimal(str(ytd_with)) - Decimal(str(ytd_without)) == Decimal("4")
    assert hist_with == acc_with
    assert hist_without == acc_without


def test_sick_on_custom_day_credited_reduced(db, test_user):
    _reduce(db, RM, "4")
    _entry(db, test_user, date(2026, 2, 2), time(8, 0), time(16, 0))
    sick = _absence(db, test_user, RM, AbsenceType.SICK, 8)

    assert calculation_service.get_range_actual(db, test_user, RM, RM) == Decimal("4")
    assert _day_delta(db, test_user, RM) == Decimal("0")

    acc_with = calculation_service.get_overtime_account(db, test_user, 2026, 2)
    db.delete(sick)
    db.commit()
    acc_without = calculation_service.get_overtime_account(db, test_user, 2026, 2)
    assert acc_with - acc_without == Decimal("4")


def test_mixed_day_custom_date_f1_uses_reduced_weight(db, test_user, test_admin):
    _reduce(db, RM, "4")
    _entry(db, test_user, RM, time(8, 0), time(10, 0))  # 2 h
    body = _post_sick_keep(db, test_admin, test_user, RM)
    assert float(body["hours"]) == 4.0, body["hours"]
    assert _day_delta(db, test_user, RM) == Decimal("0")


def test_vacation_costs_half_day(db, test_user):
    _reduce(db, D24, "4")
    a = _absence(db, test_user, D24, AbsenceType.VACATION, 8)
    assert calculation_service.get_vacation_account(db, test_user, 2026)["used_days"] == 0.5
    assert calculation_service.absence_days(db, test_user, [a]) == Decimal("0.5")


def test_vacation_costs_half_day_for_3h_person(db, user_3h):
    _reduce(db, D24, "4")
    a = _absence(db, user_3h, D24, AbsenceType.VACATION, 3)
    assert calculation_service.get_vacation_account(db, user_3h, 2026)["used_days"] == 0.5
    assert calculation_service.absence_days(db, user_3h, [a]) == Decimal("0.5")


def test_vacation_costs_half_day_on_custom_day(db, test_user):
    _reduce(db, RM, "4")
    a = _absence(db, test_user, RM, AbsenceType.VACATION, 8)
    assert calculation_service.get_vacation_account(db, test_user, 2026)["used_days"] == 0.5
    assert calculation_service.absence_days(db, test_user, [a]) == Decimal("0.5")


def test_mixed_day_sick_keep_entries_no_500(db, test_user, test_admin):
    _reduce(db, D24, "4")
    _entry(db, test_user, D24, time(8, 0), time(10, 0))  # 2 h
    body = _post_sick_keep(db, test_admin, test_user, D24)
    assert float(body["hours"]) == 4.0, body["hours"]
    credit = calculation_service.get_range_actual(db, test_user, D24, D24) - Decimal("2")
    assert credit == Decimal("2")
    assert _day_delta(db, test_user, D24) == Decimal("0")


def test_retarget_on_reduced_day_no_error(db, test_user):
    _reduce(db, D24, "4")
    sick = _absence(db, test_user, D24, AbsenceType.SICK, 8, half_day=False)
    _entry(db, test_user, D24, time(8, 0), time(9, 0))  # 1 h
    changed = calculation_service.retarget_absence_hours(
        db, test_user, D24, D24, old_full_target_by_date={D24: Decimal("8")})
    db.refresh(sick)
    assert Decimal(str(sick.hours)) == Decimal("6.00")
    assert len(changed) == 1 and changed[0].f1_clamped
    assert calculation_service.get_range_actual(db, test_user, D24, D24) == Decimal("4")
    assert _day_delta(db, test_user, D24) == Decimal("0")


def test_f1_clamp_for_day_on_reduced_day(db, test_user):
    _reduce(db, RM, "4")
    _entry(db, test_user, RM, time(8, 0), time(10, 0))  # 2 h
    assert calculation_service.f1_clamp_for_day(db, test_user, RM, 8.0, 8.0) == 4.0
