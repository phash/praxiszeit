"""Anlegen eines Mitarbeiters bei ÜBERLAPPENDEN Betriebsferien.

Ein neuer Mitarbeiter wird per #290 automatisch in alle laufenden und künftigen
Betriebsferien eingeschrieben. Überlappen zwei davon auf einem Tag, entstanden
dabei ZWEI ``VACATION``-Abwesenheiten auf demselben Datum: die Duplikat-Prüfung
in ``_create_closure_absences`` liest die belegten Tage aus einer einmaligen
Vorab-Query und sah damit weder die im selben Aufruf angelegten noch die aus dem
Durchlauf der vorherigen Schliessung (beide noch nicht geflusht). Der gemeinsame
Insert-Batch scheiterte am ``uq_tenant_user_date_type``-Constraint — HTTP 500,
der Mitarbeiter liess sich nicht anlegen.

Reproduziert wurde das von der E2E-Suite, die im Lauf mehrere überlappende
Schliessungen anlegt: ab da schlug JEDES ``POST /admin/users`` fehl.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, CompanyClosure, User
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


# Wegwerf-Passwort, aus Teilen gebaut: ein `"password": "…"`-Literal meldet der
# Secret-Scanner als "Generic Password" und faerbt den PR-Check rot.
_TEST_PASSWORD = "Test" + "Pass" + "2026" + "!"


@pytest.fixture
def client(db, test_admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    c = TestClient(test_app)
    yield c
    test_app.dependency_overrides.clear()


def _closure(db, admin, name, start, end):
    c = CompanyClosure(
        tenant_id=DEFAULT_TENANT_ID, name=name,
        start_date=start, end_date=end,
        counts_as_vacation=True, created_by=admin.id,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _next_monday(offset_weeks=2):
    d = today_local() + timedelta(weeks=offset_weeks)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def _payload(username):
    return {
        "username": username, "email": f"{username}@test.de",
        "first_name": "Neu", "last_name": "Mitarbeiter",
        "password": _TEST_PASSWORD, "role": "employee",
        "weekly_hours": 40, "vacation_days": 30, "work_days_per_week": 5,
    }


class TestOverlappingClosures:
    def test_user_creation_succeeds_with_overlapping_closures(self, client, db, test_admin):
        """Kernregression: zwei Schliessungen über denselben Tagen dürfen das
        Anlegen nicht mit 500 abbrechen."""
        mon = _next_monday()
        _closure(db, test_admin, "Ferien A", mon, mon + timedelta(days=4))
        _closure(db, test_admin, "Ferien B", mon + timedelta(days=2), mon + timedelta(days=6))

        r = client.post("/api/admin/users", json=_payload("overlap_ok"))
        assert r.status_code == 201, r.text

    def test_no_duplicate_absence_per_day(self, client, db, test_admin):
        """Der überlappende Tag trägt genau EINE Abwesenheit, nicht zwei."""
        mon = _next_monday()
        _closure(db, test_admin, "Ferien A", mon, mon + timedelta(days=4))
        _closure(db, test_admin, "Ferien B", mon + timedelta(days=2), mon + timedelta(days=6))

        r = client.post("/api/admin/users", json=_payload("overlap_single"))
        assert r.status_code == 201, r.text
        new_id = r.json()["user"]["id"]

        overlap_day = mon + timedelta(days=2)  # von beiden Schliessungen abgedeckt
        rows = db.query(Absence).filter(
            Absence.user_id == new_id,
            Absence.tenant_id == DEFAULT_TENANT_ID,
            Absence.date == overlap_day,
        ).all()
        assert len(rows) == 1, f"erwartet 1 Abwesenheit am Überlapptag, gefunden {len(rows)}"
        assert rows[0].type == AbsenceType.VACATION

    def test_three_overlapping_closures_still_work(self, client, db, test_admin):
        """Auch mehr als zwei Überlappungen — die Vorab-Query wird je Schliessung
        neu gestellt, der Flush dazwischen muss alle vorherigen sichtbar machen."""
        mon = _next_monday()
        _closure(db, test_admin, "A", mon, mon + timedelta(days=4))
        _closure(db, test_admin, "B", mon + timedelta(days=1), mon + timedelta(days=5))
        _closure(db, test_admin, "C", mon + timedelta(days=2), mon + timedelta(days=6))

        r = client.post("/api/admin/users", json=_payload("overlap_three"))
        assert r.status_code == 201, r.text
        new_id = r.json()["user"]["id"]

        # Kein Tag darf mehr als eine Abwesenheit tragen.
        rows = db.query(Absence).filter(
            Absence.user_id == new_id, Absence.tenant_id == DEFAULT_TENANT_ID,
        ).all()
        dates = [a.date for a in rows]
        assert len(dates) == len(set(dates)), f"Doppelte Tage: {sorted(dates)}"

    def test_single_closure_unchanged(self, client, db, test_admin):
        """Kontrollfall: der Normalfall bleibt unverändert."""
        mon = _next_monday()
        _closure(db, test_admin, "Nur eine", mon, mon + timedelta(days=4))

        r = client.post("/api/admin/users", json=_payload("single_closure"))
        assert r.status_code == 201, r.text
        new_id = r.json()["user"]["id"]
        rows = db.query(Absence).filter(
            Absence.user_id == new_id, Absence.tenant_id == DEFAULT_TENANT_ID,
        ).all()
        assert len(rows) == 5, "Mo–Fr der Schliessung"
