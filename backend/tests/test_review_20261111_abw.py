"""Code-Review 2026-11-11, Slice abw: abw-03, abw-05, abw-12, abw-14."""
from datetime import date

import pytest

from app.models import Absence, AbsenceType
from app.models.system_setting import SystemSetting
from app.models.year_carryover import YearCarryover
from app.routers import absences as absences_router
from app.routers import vacation_requests as vr_router
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
    endpoints_app,
)

TODAY = date(2026, 6, 10)  # Mittwoch
PAST = date(2026, 6, 8)
FUTURE = date(2026, 6, 15)  # Montag


@pytest.fixture
def approval_on(_db_session):
    _db_session.merge(SystemSetting(key="vacation_approval_required",
                                    tenant_id=DEFAULT_TENANT_ID, value="true"))
    _db_session.commit()


def _freeze(monkeypatch, today=TODAY):
    monkeypatch.setattr(absences_router, "today_local", lambda: today)
    monkeypatch.setattr(vr_router, "today_local", lambda: today)


# ── abw-14: limit-Untergrenze ────────────────────────────────────────

@pytest.mark.parametrize("path", ["/api/absences/", "/api/vacation-requests/"])
@pytest.mark.parametrize("limit", [0, -1])
def test_limit_below_one_is_422(employee_user, employee_client, path, limit):
    assert employee_client.get(f"{path}?limit={limit}").status_code == 422


def test_admin_limit_below_one_is_422(admin_user, admin_client):
    assert admin_client.get("/api/admin/vacation-requests?limit=-1").status_code == 422
    assert admin_client.get("/api/company-closures/?limit=0").status_code == 422


def test_absence_list_default_covers_a_full_year(_db_session, employee_user, employee_client):
    # abw-02: >100 Zeilen im Jahr dürfen nicht still abgeschnitten werden.
    from datetime import timedelta
    d = date(2026, 1, 1)
    for i in range(150):
        _db_session.add(Absence(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
                                date=d + timedelta(days=i), type=AbsenceType.SICK,
                                hours=8.0, half_day=False))
    _db_session.commit()
    r = employee_client.get("/api/absences/?year=2026")
    assert r.status_code == 200 and len(r.json()) == 150


# ── abw-12: Überstundenausgleich mit 0 Stunden ───────────────────────

def test_overtime_absence_zero_hours_rejected(employee_user, employee_client, monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/absences/", json={
        "date": FUTURE.isoformat(), "type": "overtime", "hours": 0})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == absences_router.OVERTIME_HOURS_DETAIL


def test_overtime_reason_zero_hours_rejected(_db_session, employee_user, employee_client,
                                             monkeypatch):
    # abw-12 (Nachtrag): eigener Grund mit base_behavior=overtime_comp wirkt wie Typ OVERTIME.
    from app.models import AbsenceReason
    reason = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Freizeitausgleich",
                           base_behavior="overtime_comp", is_active=True)
    _db_session.add(reason)
    _db_session.commit()
    _freeze(monkeypatch)
    r = employee_client.post("/api/absences/", json={
        "date": FUTURE.isoformat(), "type": "other", "hours": 0,
        "reason_id": str(reason.id)})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == absences_router.OVERTIME_HOURS_DETAIL


def test_overtime_request_zero_hours_rejected(employee_user, employee_client, approval_on,
                                              monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/vacation-requests/", json={
        "date": FUTURE.isoformat(), "hours": 0, "absence_type": "overtime"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == absences_router.OVERTIME_HOURS_DETAIL


# ── abw-03: Antragsweg spiegelt Vergangenheits-/Jahresabschluss-Sperre ─

def test_request_for_past_day_rejected_for_employee(employee_user, employee_client, approval_on,
                                                    monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/vacation-requests/", json={
        "date": PAST.isoformat(), "hours": 8, "absence_type": "training"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.PAST_DAY_ABSENCE_DETAIL


def test_request_in_closed_year_rejected(_db_session, employee_user, employee_client, approval_on,
                                         monkeypatch):
    _freeze(monkeypatch, today=date(2026, 12, 21))
    _db_session.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id,
                                  year=2027, overtime_hours=0, vacation_days=0,
                                  source="year_closing"))
    _db_session.commit()
    r = employee_client.post("/api/vacation-requests/", json={
        "date": "2026-12-23", "hours": 8, "absence_type": "training"})
    assert r.status_code == 409, r.text
    assert "2026" in r.json()["detail"]


def test_request_over_existing_absence_conflicts_up_front(_db_session, employee_user,
                                                          employee_client, approval_on,
                                                          monkeypatch):
    _freeze(monkeypatch)
    _db_session.add(Absence(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
                            date=FUTURE, type=AbsenceType.SICK, hours=8.0, half_day=False))
    _db_session.commit()
    r = employee_client.post("/api/vacation-requests/", json={
        "date": FUTURE.isoformat(), "hours": 8, "absence_type": "training"})
    assert r.status_code == 409, r.text
    assert "existiert bereits eine Abwesenheit" in r.json()["detail"]


def test_request_for_future_day_still_works(employee_user, employee_client, approval_on,
                                            monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/vacation-requests/", json={
        "date": FUTURE.isoformat(), "hours": 8, "absence_type": "training"})
    assert r.status_code == 201, r.text


def test_patch_to_past_day_rejected_for_employee(employee_user, employee_client, approval_on,
                                                 monkeypatch):
    _freeze(monkeypatch)
    r = employee_client.post("/api/vacation-requests/", json={
        "date": FUTURE.isoformat(), "hours": 8, "absence_type": "training"})
    rid = r.json()["id"]
    r = employee_client.patch(f"/api/vacation-requests/{rid}", json={"date": PAST.isoformat()})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == absences_router.PAST_DAY_ABSENCE_DETAIL


# ── abw-05: Admin-Buchung/-Löschung in abgeschlossenem Jahr warnt ───────

def _close_2026(db, user):
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, year=2027,
                         overtime_hours=0, vacation_days=0, source="year_closing"))
    db.commit()


def test_admin_booking_in_closed_year_warns(_db_session, employee_user, admin_client,
                                            monkeypatch):
    _freeze(monkeypatch, today=date(2026, 12, 21))
    _close_2026(_db_session, employee_user)
    r = admin_client.post("/api/absences/", json={
        "date": "2026-12-22", "type": "sick", "hours": 8, "user_id": str(employee_user.id)})
    assert r.status_code == 201, r.text
    warnings = r.json()[0].get("warnings") or []
    assert any("Jahresabschluss" in w or "abgeschlossen" in w for w in warnings), warnings


def test_admin_delete_in_closed_year_returns_warning(_db_session, employee_user, admin_client,
                                                     monkeypatch):
    _freeze(monkeypatch, today=date(2026, 12, 21))
    a = Absence(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 12, 22),
                type=AbsenceType.SICK, hours=8.0, half_day=False)
    _db_session.add(a)
    _close_2026(_db_session, employee_user)
    r = admin_client.delete(f"/api/absences/{a.id}")
    assert r.status_code == 200, r.text
    assert r.json().get("warning")


def test_admin_delete_open_year_still_204(_db_session, employee_user, admin_client, monkeypatch):
    _freeze(monkeypatch)
    a = Absence(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, date=FUTURE,
                type=AbsenceType.SICK, hours=8.0, half_day=False)
    _db_session.add(a)
    _db_session.commit()
    assert admin_client.delete(f"/api/absences/{a.id}").status_code == 204
