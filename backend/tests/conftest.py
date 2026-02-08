import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User, UserRole
from app.services import auth_service


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
def test_user(db):
    """Create a test employee user."""
    user = User(
        email="test@example.com",
        password_hash=auth_service.hash_password("testpassword123"),
        first_name="Test",
        last_name="User",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_admin(db):
    """Create a test admin user."""
    admin = User(
        email="admin@example.com",
        password_hash=auth_service.hash_password("adminpassword123"),
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        is_active=True
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin
