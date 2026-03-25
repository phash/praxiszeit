import pytest
import uuid
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User, UserRole
from app.services import auth_service

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Test database URL
TEST_DATABASE_URL = "sqlite:///./test.db"

# Create test engine
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
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
    db.refresh(tenant)
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
    db.refresh(h)
    return h


@pytest.fixture(scope="function")
def working_hours_change(db, test_user):
    """Historische Arbeitsstunden-Änderung (20h ab 2026-01-01) für test_user."""
    from app.models import WorkingHoursChange
    change = WorkingHoursChange(
        user_id=test_user.id,
        weekly_hours=20.0,
        effective_from=date(2026, 1, 1),
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    return change
