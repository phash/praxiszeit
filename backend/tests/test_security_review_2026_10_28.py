"""Passive security review 2026-10-28 — quick fixes.

1/7: template values from ``.env.example`` / ``praxiszeit.conf.example`` are
     public (repository) and never count as SECRET_KEY or admin password.
8:   a renamed admin does not come back as a second "admin" on restart.
"""
import pytest

from app import main as app_main
from app.config import Settings, is_placeholder_secret
from app.database import Base
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


@pytest.mark.parametrize("value", [
    "<generierter-key-mindestens-64-hex-zeichen>", "<initiales-admin-pw>",
    "BITTE_AENDERN_min12zeichen", "CHANGE_ME_GENERATE_RANDOM_PASSWORD",
])
def test_template_values_are_placeholders(value):
    assert is_placeholder_secret(value)


@pytest.mark.parametrize("value", ["9f" * 32, "Sicheres-Passwort-2026", "a<b>c"])
def test_real_values_are_not_placeholders(value):
    assert not is_placeholder_secret(value)


def test_secret_key_placeholder_is_rejected():
    with pytest.raises(ValueError, match="placeholder"):
        Settings.validate_secret_key("<generierter-key-mindestens-64-hex-zeichen>")


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    session.add(Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _admins(db):
    return db.query(User).filter(User.role == UserRole.ADMIN).all()


def test_bootstrap_creates_admin_on_empty_install(db, monkeypatch):
    monkeypatch.setattr(app_main.settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(app_main.settings, "ADMIN_PASSWORD", "Sicheres-Passwort-2026")
    app_main._bootstrap_admin(db, DEFAULT_TENANT_ID)
    assert [u.username for u in _admins(db)] == ["admin"]


def test_bootstrap_refuses_placeholder_password(db, monkeypatch):
    monkeypatch.setattr(app_main.settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(app_main.settings, "ADMIN_PASSWORD", "BITTE_AENDERN_min12zeichen")
    with pytest.raises(RuntimeError, match="placeholder"):
        app_main._bootstrap_admin(db, DEFAULT_TENANT_ID)
    assert _admins(db) == []


def test_renamed_admin_is_not_recreated(db, monkeypatch):
    monkeypatch.setattr(app_main.settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(app_main.settings, "ADMIN_PASSWORD", "Sicheres-Passwort-2026")
    db.add(User(
        username="chefin", email="chefin@x.de", password_hash=auth_service.hash_password("x" * 16),
        first_name="C", last_name="H", role=UserRole.ADMIN, weekly_hours=40.0, vacation_days=30,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    ))
    db.commit()
    app_main._bootstrap_admin(db, DEFAULT_TENANT_ID)
    assert [u.username for u in _admins(db)] == ["chefin"]
