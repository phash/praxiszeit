import pytest
import uuid
from datetime import date
from sqlalchemy import create_engine, event, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy import types as sa_types
from app.database import Base
from app.models import User, UserRole
from app.services import auth_service

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Test database URL
TEST_DATABASE_URL = "sqlite:///./test.db"

# Create test engine with SQLite-compatible UUID handling.
# postgresql.UUID(as_uuid=True) stores UUIDs as binary BLOBs in SQLite,
# which causes 'int has no attribute replace' on readback.
# We override the UUID type to use VARCHAR(36) in SQLite.
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class _SQLiteUUID(sa_types.TypeDecorator):
    """Store UUID values as CHAR(36) strings in SQLite."""
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


# Monkeypatch PostgreSQL UUID so it stores as VARCHAR in SQLite.
# We wrap the original class so that on SQLite we swap impl to String.
_original_pg_uuid_init = PG_UUID.__init__


def _patched_pg_uuid_init(self, as_uuid=True, *args, **kwargs):
    _original_pg_uuid_init(self, as_uuid=as_uuid, *args, **kwargs)

# Swap out the impl for the SQLite engine by using render_as_batch-style
# approach: listen for column creation and override UUID type on SQLite.

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# Override postgresql.UUID columns to use VARCHAR(36) for SQLite.
# We do this by patching the PG_UUID result/bind processors.
from sqlalchemy.dialects import sqlite as sqlite_dialect


@event.listens_for(engine, "connect")
def _sqlite_compat(dbapi_conn, _record):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")


# The cleanest approach: use a TypeDecorator that wraps all postgresql.UUID
# columns in the test engine.  We accomplish this via a compile-time override.
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine


# We need the UUID columns to render as VARCHAR(36) in SQLite.
# Patch PG_UUID result_processor and bind_processor so they handle strings
# (what SQLite stores/returns) correctly even when as_uuid=True.
def _pg_uuid_result_processor_sqlite(self, dialect, coltype):
    """SQLite-compatible result processor for postgresql.UUID."""
    def process(value):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return value
    return process


def _pg_uuid_bind_processor_sqlite(self, dialect):
    """SQLite-compatible bind processor for postgresql.UUID."""
    def process(value):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)
    return process


# Monkey-patch the PG_UUID processors for SQLite dialect only
from sqlalchemy.dialects.sqlite import base as sqlite_base

_orig_result = PG_UUID.result_processor
_orig_bind = PG_UUID.bind_processor


def _patched_result_processor(self, dialect, coltype):
    if dialect.name == 'sqlite':
        return _pg_uuid_result_processor_sqlite(self, dialect, coltype)
    return _orig_result(self, dialect, coltype)


def _patched_bind_processor(self, dialect):
    if dialect.name == 'sqlite':
        return _pg_uuid_bind_processor_sqlite(self, dialect)
    return _orig_bind(self, dialect)


PG_UUID.result_processor = _patched_result_processor
PG_UUID.bind_processor = _patched_bind_processor


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def default_tenant(db):
    """Create the default tenant for tests."""
    from app.models.tenant import Tenant
    tenant = Tenant(
        id=DEFAULT_TENANT_ID,
        name="Default",
        slug="default",
        is_active=True,
        mode="single",
    )
    db.add(tenant)
    db.commit()
    # Note: skip db.refresh() — postgresql.UUID(as_uuid=True) has SQLite
    # compatibility issues when reading back explicitly-set UUID primary keys.
    # The tenant object already has all values set; refresh is not needed.
    return tenant


@pytest.fixture(scope="function")
def test_user(db, default_tenant):
    """Create a test employee user."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=auth_service.hash_password("testpassword123"),
        first_name="Test",
        last_name="User",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_admin(db, default_tenant):
    """Create a test admin user."""
    admin = User(
        username="adminuser",
        email="admin@example.com",
        password_hash=auth_service.hash_password("adminpassword123"),
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@pytest.fixture(scope="function")
def public_holiday(db, default_tenant):
    """Ein Feiertag (Neujahr 2026) für Tests."""
    from app.models.public_holiday import PublicHoliday
    h = PublicHoliday(
        date=date(2026, 1, 1),
        name="Neujahr",
        year=2026,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(h)
    db.commit()
    # Note: db.refresh() may fail in SQLite when the object has a FK to
    # a UUID-PK table; the object already has all needed fields set.
    return h


@pytest.fixture(scope="function")
def working_hours_change(db, test_user):
    """Historische Arbeitsstunden-Änderung (20h ab 2026-01-01) für test_user."""
    from app.models import WorkingHoursChange
    change = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=DEFAULT_TENANT_ID,
        weekly_hours=20.0,
        effective_from=date(2026, 1, 1),
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    return change
