"""P1.1 (Handbuch-Funde 2026-11-11): das Monatsjournal kennzeichnet
Betriebsferien-Tage an der Abwesenheit (``closure_day``). Das Frontend bietet
dort keinen Lösch-Antrag an — Betriebsferien-Tage ändert nur die Verwaltung
(``absences.CLOSURE_ABSENCE_DELETE_DETAIL``), wie im Abwesenheitskalender."""
from datetime import date

from app.models import Absence, CompanyClosure
from app.models.absence import AbsenceType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)

CLOSURE_DAY = date(2026, 6, 3)
SICK_DAY = date(2026, 6, 4)


def _seed(db, user, admin):
    closure = CompanyClosure(tenant_id=DEFAULT_TENANT_ID, name="Sommer", start_date=CLOSURE_DAY,
                             end_date=CLOSURE_DAY, created_by=admin.id)
    db.add(closure)
    db.flush()
    db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=CLOSURE_DAY,
                   type=AbsenceType.VACATION, hours=8, half_day=False, closure_id=closure.id,
                   note="Betriebsferien: Sommer"))
    db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=SICK_DAY,
                   type=AbsenceType.SICK, hours=8, half_day=False))
    db.commit()


def _absence(body, d):
    day = next(x for x in body["days"] if x["date"] == d.isoformat())
    return day["absences"][0]


def test_own_journal_marks_closure_day(_db_session, employee_user, admin_user, employee_client):
    _seed(_db_session, employee_user, admin_user)
    r = employee_client.get("/api/journal/me?year=2026&month=6")
    assert r.status_code == 200, r.text
    body = r.json()
    assert _absence(body, CLOSURE_DAY)["closure_day"] is True
    assert _absence(body, SICK_DAY)["closure_day"] is False


def test_admin_journal_marks_closure_day(_db_session, employee_user, admin_user, admin_client):
    _seed(_db_session, employee_user, admin_user)
    r = admin_client.get(f"/api/admin/users/{employee_user.id}/journal?year=2026&month=6")
    assert r.status_code == 200, r.text
    assert _absence(r.json(), CLOSURE_DAY)["closure_day"] is True
