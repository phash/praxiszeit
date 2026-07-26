"""Vorschau vor einer Wochenstunden-Änderung.

Der Dialog muss VOR dem Speichern zeigen, was eine rückwirkende Änderung
anfasst — Zeitraum, altes/neues Tagessoll, Anzahl betroffener Abwesenheiten und
ob ein abgeschlossenes Jahr berührt wird. Und er muss die Fälle kennen, in denen
der Schreib-Endpoint ablehnen würde, damit der Nutzer nicht in einen 400 läuft.

Der Endpoint ist strikt lesend.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, User, UserRole, WorkingHoursChange, YearCarryover
from app.services import auth_service
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


def _client(db, admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: admin
    test_app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(test_app)


@pytest.fixture
def client(db, test_admin):
    c = _client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _url(user_id, eff, hours=20.0):
    return (f"/api/admin/users/{user_id}/working-hours-changes/preview"
            f"?effective_from={eff.isoformat()}&weekly_hours={hours}")


def _absence(db, user, d, typ=AbsenceType.VACATION, hours=8.0):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                type=typ, hours=hours, half_day=False)
    db.add(a); db.commit()
    return a


def _last_monday(before_days=30):
    """Ein Montag in der Vergangenheit — vermeidet Wochenend-Sonderfälle."""
    d = today_local() - timedelta(days=before_days)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return d


class TestRetroactiveDetection:
    def test_future_date_is_not_retroactive(self, client, test_user):
        r = client.get(_url(test_user.id, today_local() + timedelta(days=7)))
        assert r.status_code == 200, r.text
        assert r.json()["is_retroactive"] is False
        assert r.json()["affected_absences"] == 0

    def test_today_is_not_retroactive(self, client, test_user):
        r = client.get(_url(test_user.id, today_local()))
        assert r.status_code == 200, r.text
        assert r.json()["is_retroactive"] is False

    def test_yesterday_is_retroactive(self, client, test_user):
        r = client.get(_url(test_user.id, today_local() - timedelta(days=1)))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_retroactive"] is True
        assert body["period_end"] == today_local().isoformat()


class TestNumbers:
    def test_counts_affected_absences(self, client, db, test_user):
        mon = _last_monday()
        _absence(db, test_user, mon)
        _absence(db, test_user, mon + timedelta(days=1))
        r = client.get(_url(test_user.id, mon))
        assert r.json()["affected_absences"] == 2

    def test_overtime_is_not_counted(self, client, db, test_user):
        mon = _last_monday()
        _absence(db, test_user, mon, AbsenceType.OVERTIME)
        assert client.get(_url(test_user.id, mon)).json()["affected_absences"] == 0

    def test_reports_old_and_new_daily_target(self, client, test_user):
        r = client.get(_url(test_user.id, _last_monday(), hours=20.0))
        body = r.json()
        assert body["current_daily_target"] == 8.0
        assert body["new_daily_target"] == 4.0

    def test_preview_changes_nothing(self, client, db, test_user):
        """Strikt lesend — weder Abwesenheit noch Historie darf sich bewegen."""
        mon = _last_monday()
        a = _absence(db, test_user, mon)
        client.get(_url(test_user.id, mon))
        db.refresh(a)
        assert float(a.hours) == 8.0
        assert db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == test_user.id
        ).count() == 0


class TestBlockedReasons:
    def test_daily_schedule_user_is_blocked(self, client, db, test_user):
        test_user.use_daily_schedule = True
        db.commit()
        body = client.get(_url(test_user.id, _last_monday())).json()
        assert body["blocked_reason"] is not None
        assert "Tagesplan" in body["blocked_reason"]

    def test_duplicate_date_is_blocked(self, client, db, test_user):
        eff = _last_monday()
        db.add(WorkingHoursChange(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=eff, weekly_hours=Decimal("30.0"),
        ))
        db.commit()
        body = client.get(_url(test_user.id, eff)).json()
        assert body["blocked_reason"] is not None
        assert "existiert bereits" in body["blocked_reason"]

    def test_normal_case_is_not_blocked(self, client, test_user):
        assert client.get(_url(test_user.id, _last_monday())).json()["blocked_reason"] is None


class TestClosedYears:
    def test_closed_year_is_reported(self, client, db, test_user):
        """Ein Jahr gilt als abgeschlossen, wenn ein YearCarryover für Y+1 existiert."""
        last_year = today_local().year - 1
        db.add(YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            year=last_year + 1, overtime_hours=Decimal("0"),
            vacation_days=Decimal("0"), source="year_closing",
        ))
        db.commit()
        r = client.get(_url(test_user.id, date(last_year, 6, 1)))
        assert r.status_code == 200, r.text
        assert r.json()["closed_year_warning"] is not None

    def test_open_year_has_no_warning(self, client, test_user):
        assert client.get(_url(test_user.id, _last_monday())).json()["closed_year_warning"] is None


class TestAuthorization:
    def test_foreign_tenant_user_is_404(self, client, db):
        foreign = User(
            username="wh_foreign", email="wh_foreign@x.de",
            password_hash=auth_service.hash_password("Test2025!Password"),
            first_name="F", last_name="T", role=UserRole.EMPLOYEE,
            weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
            is_active=True, tenant_id=uuid.uuid4(),
        )
        db.add(foreign); db.commit(); db.refresh(foreign)
        assert client.get(_url(foreign.id, _last_monday())).status_code == 404

    def test_employee_is_forbidden(self, db, test_user):
        """Ohne require_admin-Override greift die echte Rolle."""
        def _override_db():
            yield db
        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        try:
            c = TestClient(test_app)
            assert c.get(_url(test_user.id, _last_monday())).status_code == 403
        finally:
            test_app.dependency_overrides.clear()
