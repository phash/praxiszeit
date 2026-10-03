"""#479: KV-Dienst am Sonntag im Monatsjournal eintragen.

Das Journal bot an Wochenend- und Feiertagen keinen Knopf zum Anlegen. Der
Frontend-Fix schaltet ihn frei und verlaesst sich dabei auf zwei Backend-Wege,
die diese Tests festhalten:

- Mitarbeitende: Aenderungsantrag fuer einen vergangenen Sonntag, Admin
  genehmigt, der Eintrag erscheint in der Tageszeile des Journals.
- Admins: direkter Eintrag fuer einen Sonntag ueber
  ``POST /api/admin/users/{id}/time-entries``.
"""
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.middleware.auth import get_current_user, require_admin
from app.database import get_db
from app.models import ChangeRequest, ChangeRequestStatus, TimeEntry
from app.services import journal_service
from app.services.timezone_service import today_local
from tests.test_break_waiver import (  # noqa: F401 — Fixtures
    _app, db, default_tenant, employee, admin, admin_client,
)


def _past_sunday():
    today = today_local()
    return today - timedelta(days=(today.weekday() - 6) % 7 + 7)


def _journal_day(db, user, d):
    days = journal_service.get_journal(db, user, d.year, d.month)["days"]
    return next(x for x in days if x["date"] == d.isoformat())


def test_sonntagsantrag_der_mitarbeiterin_landet_im_journal(db, employee, admin):
    sunday = _past_sunday()

    def override_db():
        yield db

    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: employee
    _app.dependency_overrides[require_admin] = lambda: admin
    client = TestClient(_app)
    try:
        resp = client.post("/api/change-requests/", json={
            "request_type": "create",
            "entry_kind": "time_entry",
            "reason": "KV-Dienst",
            "proposed_date": sunday.isoformat(),
            "proposed_start_time": "09:00",
            "proposed_end_time": "16:00",
            "proposed_break_minutes": 30,
        })
        assert resp.status_code == 201, resp.text
        cr_id = resp.json()["id"]

        _app.dependency_overrides[get_current_user] = lambda: admin
        review = client.post(
            f"/api/admin/change-requests/{cr_id}/review", json={"action": "approve"},
        )
        assert review.status_code == 200, review.text
    finally:
        _app.dependency_overrides.clear()

    cr = db.query(ChangeRequest).filter(ChangeRequest.id == uuid.UUID(cr_id)).one()
    assert cr.status == ChangeRequestStatus.APPROVED

    day = _journal_day(db, employee, sunday)
    assert day["type"] == "weekend"
    assert len(day["time_entries"]) == 1
    assert day["actual_hours"] == pytest.approx(6.5)
    assert day["target_hours"] == pytest.approx(0)
    assert day["balance"] == pytest.approx(6.5)


def test_admin_traegt_sonntagsdienst_direkt_ein(db, employee, admin_client):
    sunday = _past_sunday()
    resp = admin_client.post(f"/api/admin/users/{employee.id}/time-entries", json={
        "date": sunday.isoformat(),
        "start_time": "09:00",
        "end_time": "16:00",
        "break_minutes": 30,
        "note": "KVB",
    })
    assert resp.status_code == 201, resp.text

    assert db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).count() == 1
    day = _journal_day(db, employee, sunday)
    assert day["actual_hours"] == pytest.approx(6.5)
    assert day["balance"] == pytest.approx(6.5)
