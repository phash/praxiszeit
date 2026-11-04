"""Teil A, Task 5: Regeln am Schreibweg der Vertragsfelder.

- Minijob-Felder (``milog_working_time_account``, ``agreed_monthly_hours``,
  ``use_fixed_monthly_target``) ändern sich nur zum Monatsersten (422).
- Der feste Monats-Soll wird auf dem ZUSAMMENGEFÜHRTEN Snapshot geprüft (400),
  nicht nur auf dem Body — beim Anlegen und in der Vorschau (``blocked_reason``).
- Ein ausdrückliches ``null`` für die vier Pflichtfelder ist 422;
  ``agreed_monthly_hours: null`` heißt weiterhin „abgeleitet".
- ``PUT /api/admin/users/{id}`` lehnt die fünf Vertragsfelder ab (genau ein
  Schreibweg je historisiertem Feld)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import WorkingHoursChange
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import admin_client, freeze
from tests.test_endpoints import test_app

TODAY = date(2026, 11, 3)
MONTH_START = "Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten."
FIXED_TRACK = "Fester Monats-Soll setzt Stundenzählung (track_hours) voraus."
FIXED_AGREED = "Fester Monats-Soll braucht eine vereinbarte Monatsarbeitszeit (> 0)."
FIXED_MILOG = "Fester Monats-Soll setzt das MiLoG-Arbeitszeitkonto voraus."
PUT_LOCK = (
    "Wochenstunden, Tagesstunden, Arbeitstage, Arbeitszeit-Blöcke, Urlaubsanspruch, "
    "Stundenzählung und Minijob-Einstellungen werden über „Arbeitszeit anpassen…“ mit "
    "Wirkungsdatum geändert, damit Historie und Soll vergangener Monate korrekt bleiben."
)


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch, TODAY)
    yield admin_client(db, test_admin)
    test_app.dependency_overrides.clear()


def url(user) -> str:
    return f"/api/admin/users/{user.id}/working-hours-changes"


def same_hours(user) -> dict:
    return {"weekly_hours": float(user.weekly_hours), "work_days_per_week": int(user.work_days_per_week)}


def rows_of(db, user) -> list:
    db.expire_all()
    return db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == DEFAULT_TENANT_ID,
    ).order_by(WorkingHoursChange.effective_from).all()


@pytest.fixture
def fixed_person(db, test_user):
    """Minijob mit festem Monats-Soll — keine Verlaufszeile, Snapshot = User-Zeile."""
    test_user.track_hours = True
    test_user.milog_working_time_account = True
    test_user.agreed_monthly_hours = Decimal("43.3")
    test_user.use_fixed_monthly_target = True
    db.commit()
    return test_user


# --- Minijob nur zum Monatsersten -----------------------------------------

def test_minijob_field_change_on_15th_is_422(db, test_user, client):
    r = client.post(url(test_user), json={"effective_from": "2027-01-15", "agreed_monthly_hours": 45.0,
                                          **same_hours(test_user)})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == MONTH_START
    assert rows_of(db, test_user) == []


@pytest.mark.parametrize("field,value", [
    ("milog_working_time_account", True), ("agreed_monthly_hours", 45.0),
])
def test_each_minijob_field_mid_month_is_422(db, test_user, client, field, value):
    r = client.post(url(test_user), json={"effective_from": "2027-01-15", field: value, **same_hours(test_user)})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == MONTH_START


def test_minijob_field_change_on_1st_ok(db, test_user, client):
    r = client.post(url(test_user), json={"effective_from": "2027-01-01", "agreed_monthly_hours": 45.0,
                                          **same_hours(test_user)})
    assert r.status_code == 201, r.text
    assert rows_of(db, test_user)[-1].agreed_monthly_hours == Decimal("45.0")


def test_unchanged_minijob_value_mid_month_ok(db, fixed_person, client):
    """Gesendet, aber gleich dem Snapshot → keine Minijob-Änderung."""
    r = client.post(url(fixed_person), json={"effective_from": "2027-01-15", "weekly_hours": 10,
                                             "work_days_per_week": 5, "agreed_monthly_hours": 43.3,
                                             "milog_working_time_account": True})
    assert r.status_code == 201, r.text


def test_hours_only_change_mid_month_keeps_minijob_fields(db, fixed_person, client):
    r = client.post(url(fixed_person), json={"effective_from": "2027-01-15", "weekly_hours": 10,
                                             "work_days_per_week": 5})
    assert r.status_code == 201, r.text
    new = rows_of(db, fixed_person)[-1]
    assert (new.milog_working_time_account, new.agreed_monthly_hours, new.use_fixed_monthly_target) == (
        True, Decimal("43.3"), True)


# --- fester Monats-Soll auf dem Snapshot -----------------------------------

def test_fixed_mode_requires_track_hours_on_snapshot(db, fixed_person, client):
    r = client.post(url(fixed_person), json={"effective_from": "2027-01-01", "track_hours": False,
                                             **same_hours(fixed_person)})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == FIXED_TRACK
    assert rows_of(db, fixed_person) == []


def test_fixed_mode_requires_milog_on_snapshot(db, fixed_person, client):
    r = client.post(url(fixed_person), json={"effective_from": "2027-01-01", "milog_working_time_account": False,
                                             **same_hours(fixed_person)})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == FIXED_MILOG


def test_fixed_mode_requires_agreed_on_snapshot(db, fixed_person, client):
    r = client.post(url(fixed_person), json={"effective_from": "2027-01-01", "agreed_monthly_hours": None,
                                             **same_hours(fixed_person)})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == FIXED_AGREED


def test_switching_fixed_on_without_prerequisites_is_400(db, test_user, client):
    r = client.post(url(test_user), json={"effective_from": "2027-01-01", "use_fixed_monthly_target": True,
                                          "agreed_monthly_hours": 40.0, **same_hours(test_user)})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == FIXED_MILOG


def test_switching_fixed_on_with_prerequisites_ok(db, test_user, client):
    r = client.post(url(test_user), json={"effective_from": "2027-01-01", "use_fixed_monthly_target": True,
                                          "milog_working_time_account": True, "agreed_monthly_hours": 40.0,
                                          **same_hours(test_user)})
    assert r.status_code == 201, r.text


def test_preview_reports_rule_errors_as_blocked_reason(db, fixed_person, client):
    r = client.post(url(fixed_person) + "/preview", json={"effective_from": "2027-01-15",
                                                          "agreed_monthly_hours": 45.0, **same_hours(fixed_person)})
    assert r.status_code == 200, r.text
    assert r.json()["blocked_reason"] == MONTH_START
    r = client.post(url(fixed_person) + "/preview", json={"effective_from": "2027-01-01", "track_hours": False,
                                                          **same_hours(fixed_person)})
    assert r.status_code == 200, r.text
    assert r.json()["blocked_reason"] == FIXED_TRACK
    r = client.post(url(fixed_person) + "/preview", json={"effective_from": "2027-01-15", "weekly_hours": 10,
                                                          "work_days_per_week": 5})
    assert r.status_code == 200, r.text
    assert r.json()["blocked_reason"] is None


# --- ausdrückliches null ---------------------------------------------------

@pytest.mark.parametrize("field", ["vacation_days", "track_hours", "milog_working_time_account",
                                   "use_fixed_monthly_target"])
def test_explicit_null_for_required_contract_field_is_422(db, test_user, client, field):
    r = client.post(url(test_user), json={"effective_from": "2027-01-01", field: None, **same_hours(test_user)})
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], str) and "leer" in r.json()["detail"]
    assert rows_of(db, test_user) == []
    p = client.post(url(test_user) + "/preview", json={"effective_from": "2027-01-01", field: None,
                                                       **same_hours(test_user)})
    assert p.status_code == 200 and p.json()["blocked_reason"] == r.json()["detail"]


def test_explicit_null_agreed_still_means_derived(db, test_user, client):
    test_user.agreed_monthly_hours = Decimal("50.0")
    db.commit()
    r = client.post(url(test_user), json={"effective_from": "2027-01-01", "agreed_monthly_hours": None,
                                          **same_hours(test_user)})
    assert r.status_code == 201, r.text
    assert rows_of(db, test_user)[-1].agreed_monthly_hours is None


# --- PUT-Sperre --------------------------------------------------------------

@pytest.mark.parametrize("field,value", [("vacation_days", 30), ("track_hours", False),
                                         ("milog_working_time_account", True), ("agreed_monthly_hours", 45),
                                         ("use_fixed_monthly_target", True)])
def test_put_user_rejects_historised_contract_field(db, test_user, client, field, value):
    before = getattr(test_user, field)
    r = client.put(f"/api/admin/users/{test_user.id}", json={field: value})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == PUT_LOCK
    db.expire_all()
    assert getattr(test_user, field) == before


def test_put_user_without_contract_fields_ok(db, test_user, client):
    r = client.put(f"/api/admin/users/{test_user.id}", json={
        "first_name": "Erika", "last_name": "Muster", "email": "erika@example.de",
        "role": "employee", "calendar_color": "#93C5FD", "exempt_from_arbzg": False,
        "receives_company_closures": True,
    })
    assert r.status_code == 200, r.text
    assert r.json()["first_name"] == "Erika"
