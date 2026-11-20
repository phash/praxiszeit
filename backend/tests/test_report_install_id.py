"""Task 3 (#557): persistent install_id in system_settings."""
import logging
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.system_setting import SystemSetting
from app.services import report_install_id as rid
from app.services.report_install_id import (
    DEFAULT_TENANT_ID,
    INSTALL_ID_SETTING_KEY,
    get_or_create_install_id,
)
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("default_tenant")


@pytest.fixture(autouse=True)
def _no_pg_context(monkeypatch):
    # SQLite kennt SET LOCAL nicht (gleiches Muster wie test_audit_1107_s2.py).
    monkeypatch.setattr(rid, "set_superadmin_context", lambda db: None)


def _rows(db):
    db.expire_all()
    return db.query(SystemSetting).filter(SystemSetting.key == INSTALL_ID_SETTING_KEY).all()


def test_creates_uuid4_once_and_reuses_it(db):
    first = get_or_create_install_id(TestingSessionLocal)
    second = get_or_create_install_id(TestingSessionLocal)
    assert first == second
    assert uuid.UUID(first).version == 4
    assert first == first.lower()
    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0].tenant_id == DEFAULT_TENANT_ID
    assert rows[0].value == first


def test_invalid_stored_value_is_replaced(db):
    db.add(SystemSetting(key=INSTALL_ID_SETTING_KEY, value="not-a-uuid", tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    value = get_or_create_install_id(TestingSessionLocal)
    assert uuid.UUID(value).version == 4
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].value == value


def test_concurrent_insert_integrity_error_rereads_existing(db, monkeypatch):
    other = "11111111-1111-4111-8111-111111111111"
    real_commit = TestingSessionLocal.class_.commit
    state = {"n": 0}

    def commit(self):
        if state["n"] == 0:
            state["n"] = 1
            s2 = TestingSessionLocal()
            s2.add(SystemSetting(key=INSTALL_ID_SETTING_KEY, value=other, tenant_id=DEFAULT_TENANT_ID))
            real_commit(s2)
            s2.close()
            raise IntegrityError("insert", {}, Exception("unique"))
        return real_commit(self)

    monkeypatch.setattr(TestingSessionLocal.class_, "commit", commit)
    assert get_or_create_install_id(TestingSessionLocal) == other


def test_db_failure_returns_uuid_and_does_not_raise(caplog):
    def broken():
        raise RuntimeError("secret-db-detail")

    with caplog.at_level(logging.WARNING):
        value = get_or_create_install_id(broken)
    assert uuid.UUID(value).version == 4
    assert any(r.levelno == logging.WARNING for r in caplog.records)
