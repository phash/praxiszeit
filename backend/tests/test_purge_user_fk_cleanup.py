"""1.12.1 review regression: DSGVO Art.17 purge must clean up ALL users.id FK
dependents without crashing.

- HIGH: time_entry_audit_logs.changed_by is NOT NULL → must be reassigned to the
  acting admin (a SET NULL raised an IntegrityError and aborted the erasure for
  any user who had ever clocked out).
- MEDIUM: company_closure.created_by / change_request.reviewed_by /
  signup_tokens.user_id have no ON DELETE rule → must be reassigned/nullified/
  deleted before db.delete(user), else Postgres FK-violates (SQLite runs FK off,
  so these assert the cleanup *behaviour*).
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    User, UserRole, TimeEntryAuditLog, CompanyClosure, ChangeRequest, SignupToken,
)
from app.models.change_request import ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


@pytest.fixture
def admin_client(db, test_admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def _deactivated_user(db, name):
    u = User(
        username=name, email=f"{name}@x.de", password_hash="x", first_name=name,
        last_name="P", role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=False, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_purge_user_with_authored_audit_rows(admin_client, db, test_admin):
    # HIGH: changed_by is NOT NULL → reassign, never SET NULL.
    u = _deactivated_user(db, "audit_self")
    # (a) the user's OWN clock-out row (user_id == changed_by == u.id): the
    #     reassign touches changed_by BEFORE the user_id-delete removes it → with
    #     the old SET NULL code this 500s on the NOT NULL column. End state: deleted.
    own = TimeEntryAuditLog(
        tenant_id=DEFAULT_TENANT_ID, time_entry_id=None, user_id=u.id,
        changed_by=u.id, action="clock_out", source="manual",
    )
    # (b) a row the purged user authored on SOMEONE ELSE's entry → must be
    #     reassigned to the acting admin and SURVIVE (its audit trail is kept).
    other = TimeEntryAuditLog(
        tenant_id=DEFAULT_TENANT_ID, time_entry_id=None, user_id=test_admin.id,
        changed_by=u.id, action="update", source="manual",
    )
    db.add_all([own, other])
    db.commit()
    oid = other.id
    r = admin_client.delete(f"/api/admin/users/{u.id}/purge")
    assert r.status_code == 200, r.text  # HIGH regression: no NOT NULL IntegrityError
    db.expire_all()
    row = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.id == oid).first()
    assert row is not None and row.changed_by == test_admin.id


def test_purge_user_who_created_company_closure(admin_client, db, test_admin):
    u = _deactivated_user(db, "closure_creator")
    c = CompanyClosure(
        tenant_id=DEFAULT_TENANT_ID, name="BF", start_date=date(2020, 1, 1),
        end_date=date(2020, 1, 3), created_by=u.id,
    )
    db.add(c)
    db.commit()
    cid = c.id
    assert admin_client.delete(f"/api/admin/users/{u.id}/purge").status_code == 200
    db.expire_all()
    closure = db.query(CompanyClosure).filter(CompanyClosure.id == cid).first()
    assert closure is not None and closure.created_by == test_admin.id


def test_purge_user_with_signup_token(admin_client, db):
    u = _deactivated_user(db, "token_user")
    db.add(SignupToken(
        tenant_id=DEFAULT_TENANT_ID, user_id=u.id, token_hash="h" + uuid.uuid4().hex,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    ))
    db.commit()
    uid = u.id
    assert admin_client.delete(f"/api/admin/users/{u.id}/purge").status_code == 200
    db.expire_all()
    assert db.query(SignupToken).filter(SignupToken.user_id == uid).count() == 0


def test_purge_user_who_reviewed_change_request(admin_client, db, test_user):
    reviewer = _deactivated_user(db, "cr_reviewer")
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id,
        request_type=ChangeRequestType.UPDATE, reason="x", reviewed_by=reviewer.id,
    )
    db.add(cr)
    db.commit()
    crid = cr.id
    assert admin_client.delete(f"/api/admin/users/{reviewer.id}/purge").status_code == 200
    db.expire_all()
    got = db.query(ChangeRequest).filter(ChangeRequest.id == crid).first()
    assert got is not None and got.reviewed_by is None
