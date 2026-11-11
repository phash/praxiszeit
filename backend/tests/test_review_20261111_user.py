"""Review 2026-11-11 (Slice user): user-01/10/11/19/20."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, User, UserRole
from app.models.absence import AbsenceType
from app.models.security_event import EVENT_USER_HIDDEN, EVENT_USER_SHOWN, SecurityEvent
from app.services import auth_service, lifecycle_service
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


@pytest.fixture
def client_as(db):
    def _client(user):
        def _override_db():
            yield db
        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[require_admin] = lambda: user
        return TestClient(test_app)
    yield _client
    test_app.dependency_overrides.clear()


def _inactive(db, username="ruhend", **kw):
    u = User(
        id=uuid.uuid4(), username=username, email=f"{username}@praxis.invalid",
        password_hash=auth_service.hash_password("AltesPasswort123!"),
        first_name="Ruhend", last_name="Test", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=False, tenant_id=DEFAULT_TENANT_ID,
        deactivated_at=datetime.now(timezone.utc) - timedelta(days=30), **kw,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class TestAnonymizedAccount:
    def test_user01_anonymize_invalidates_old_password(self, db, test_admin, client_as):
        gone = _inactive(db)
        r = client_as(test_admin).post(f"/api/admin/users/{gone.id}/anonymize")
        assert r.status_code == 200, r.text
        db.expire_all()
        fresh = db.get(User, gone.id)
        assert not auth_service.verify_password("AltesPasswort123!", fresh.password_hash)

    def test_user01_anonymized_account_cannot_be_reactivated(self, db, test_admin, client_as):
        gone = _inactive(db, username="deleted_ab12cd34")
        r = client_as(test_admin).post(f"/api/admin/users/{gone.id}/reactivate")
        assert r.status_code == 400, r.text
        db.expire_all()
        assert db.get(User, gone.id).is_active is False

    def test_user01_normal_inactive_account_still_reactivates(self, db, test_admin, client_as):
        gone = _inactive(db)
        r = client_as(test_admin).post(f"/api/admin/users/{gone.id}/reactivate")
        assert r.status_code == 200, r.text


class TestDeletionCandidates:
    def test_user10_recent_absence_blocks_purge_like_purge_user(self, db, test_admin, client_as):
        gone = _inactive(db)
        db.add(Absence(
            id=uuid.uuid4(), tenant_id=DEFAULT_TENANT_ID, user_id=gone.id,
            date=today_local() - timedelta(days=10), type=AbsenceType.VACATION, hours=8,
        ))
        db.commit()
        r = client_as(test_admin).get("/api/admin/users/deletion-candidates")
        assert r.status_code == 200, r.text
        row = next(x for x in r.json() if x["user_id"] == str(gone.id))
        assert row["can_purge"] is False
        assert client_as(test_admin).delete(f"/api/admin/users/{gone.id}/purge").status_code == 409


class TestEmailNormalisation:
    def test_user11_empty_email_becomes_null(self, db, test_admin, test_user, client_as):
        r = client_as(test_admin).put(f"/api/admin/users/{test_user.id}", json={"email": "  "})
        assert r.status_code == 200, r.text
        db.expire_all()
        assert db.get(User, test_user.id).email is None

    def test_user11_invalid_new_email_is_rejected(self, db, test_admin, test_user, client_as):
        r = client_as(test_admin).put(f"/api/admin/users/{test_user.id}", json={"email": "ohne-at"})
        assert r.status_code == 422, r.text
        db.expire_all()
        assert db.get(User, test_user.id).email == "test@example.com"

    def test_user11_unchanged_legacy_value_does_not_block_other_edits(self, db, test_admin, test_user, client_as):
        test_user.email = "altwert"
        db.commit()
        r = client_as(test_admin).put(
            f"/api/admin/users/{test_user.id}", json={"email": "altwert", "department": "MFA"})
        assert r.status_code == 200, r.text

    def test_user11_valid_email_is_saved_trimmed(self, db, test_admin, test_user, client_as):
        r = client_as(test_admin).put(
            f"/api/admin/users/{test_user.id}", json={"email": " neu@praxis.de "})
        assert r.status_code == 200, r.text
        db.expire_all()
        assert db.get(User, test_user.id).email == "neu@praxis.de"


class TestHiddenToggle:
    def _events(self, db, user, event):
        return db.query(SecurityEvent).filter(
            SecurityEvent.subject_user_id == user.id, SecurityEvent.event == event).count()

    def test_user20_explicit_target_is_idempotent_and_logged_once(self, db, test_admin, test_user, client_as):
        c = client_as(test_admin)
        for _ in range(2):
            r = c.post(f"/api/admin/users/{test_user.id}/toggle-hidden?hidden=true")
            assert r.status_code == 200 and r.json()["is_hidden"] is True
        assert self._events(db, test_user, EVENT_USER_HIDDEN) == 1
        r = c.post(f"/api/admin/users/{test_user.id}/toggle-hidden?hidden=false")
        assert r.json()["is_hidden"] is False
        assert self._events(db, test_user, EVENT_USER_SHOWN) == 1

    def test_user20_without_parameter_still_toggles(self, db, test_admin, test_user, client_as):
        r = client_as(test_admin).post(f"/api/admin/users/{test_user.id}/toggle-hidden")
        assert r.json()["is_hidden"] is True
        assert self._events(db, test_user, EVENT_USER_HIDDEN) == 1

    def test_user20_put_is_hidden_is_logged(self, db, test_admin, test_user, client_as):
        r = client_as(test_admin).put(f"/api/admin/users/{test_user.id}", json={"is_hidden": True})
        assert r.status_code == 200, r.text
        assert self._events(db, test_user, EVENT_USER_HIDDEN) == 1


class TestExportHeaderUsesSnapshot:
    def test_user19_art15_header_follows_todays_snapshot(self, db, test_user, working_hours_change):
        assert float(test_user.weekly_hours) == 40.0  # veraltete User-Zeile
        d = lifecycle_service._user_dict(db, test_user)
        assert d["weekly_hours"] == 20.0
        assert d["working_hours_changes"][0]["weekly_hours"] == 20.0
