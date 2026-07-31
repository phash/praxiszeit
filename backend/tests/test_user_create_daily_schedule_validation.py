"""Fund E (Abschluss-Review #431): Quervalidierung Tagesplan <-> weekly_hours
beim ANLEGEN eines Nutzers.

`UserBase.weekly_hours` ist beim Anlegen ein eigenes, vom Admin direkt
editierbares Pflichtfeld — anders als im Wochenstunden-Dialog
(`WorkingHoursChangeCreate.check_mode`, das Vorbild dieser Regel) koppelt das
Anlege-Formular es NICHT an die Tageswerte. Ohne Gegenprobe liess sich
`use_daily_schedule=True` mit Tagen 8/5/4 UND `weekly_hours=40` gleichzeitig
anlegen — ein Widerspruch, der (solange keine WorkingHoursChange-Zeile
existiert) dauerhaft ueber `get_schedule_for_date`s Rueckfall auf die
User-Spalten in JEDER #415-Flaeche steht.

Harness wie `test_user_fixed_mode_validation.py` (lokale `_app()` +
dependency_overrides, `/api`-Pfade, headerloser TestClient).
"""
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

USERS = "/api/admin/users"


def _app() -> FastAPI:
    from app.routers import admin
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    a = FastAPI()
    limiter.enabled = False
    a.state.limiter = limiter
    a.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    a.include_router(admin.router)
    return a


app = _app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="D", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, username, role=UserRole.EMPLOYEE, weekly=Decimal("40")):
    u = User(username=username, email=f"{username}@x.de",
             password_hash=auth_service.hash_password("test123"),
             first_name=username, last_name="T", role=role, weekly_hours=weekly,
             vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "admin1", role=UserRole.ADMIN, weekly=Decimal("40"))


def _client_as(db, user, admin_user):
    def od():
        yield db
    app.dependency_overrides[get_db] = od
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


BASE_PAYLOAD = {
    "username": "dp", "first_name": "D", "last_name": "P", "password": "E2ePass1234!",
    "role": "employee", "vacation_days": 30, "work_days_per_week": 5,
}


def test_create_daily_schedule_aligns_mismatched_weekly_hours_to_day_sum(db, admin, default_tenant):
    """Der Kernfall aus dem Fund: use_daily_schedule=True, Tage 8/5/4 (Summe 17)
    UND ein widersprechendes weekly_hours=40 — angelegt wird mit der Summe."""
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "weekly_hours": 40,  # widerspricht der Tagessumme — muss NICHT stehen bleiben
        "use_daily_schedule": True,
        "hours_monday": 8, "hours_tuesday": 5, "hours_wednesday": 4,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["weekly_hours"] == 17.0
    uid = resp.json()["user"]["id"]
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert row["weekly_hours"] == 17.0
    app.dependency_overrides.clear()


def test_create_daily_schedule_with_already_consistent_weekly_hours_is_unchanged(db, admin, default_tenant):
    """Angleichen ist idempotent — ein bereits konsistenter Wert bleibt exakt
    derselbe (kein Rundungs-Umweg ueber die Summe)."""
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "username": "dp2",
        "weekly_hours": 17,
        "use_daily_schedule": True,
        "hours_monday": 8, "hours_tuesday": 5, "hours_wednesday": 4,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["weekly_hours"] == 17.0
    app.dependency_overrides.clear()


def test_create_daily_schedule_without_any_day_hours_fails(db, admin, default_tenant):
    """Gleiche Regel wie `WorkingHoursChangeCreate.check_mode`: der Tagesplan-
    Modus braucht mindestens einen Wochentag mit Stunden — sonst waere die
    Zeile die per-Schema-eigentlich-unmoegliche Leerform, die andernorts
    (`format_day_plan`-Doku) als Bestandsschutz-Ausnahme behandelt wird."""
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "username": "dp3",
        "weekly_hours": 40,
        "use_daily_schedule": True,
        # kein einziger hours_* Wert gesetzt
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_daily_schedule_sum_over_60_fails(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={
        **BASE_PAYLOAD,
        "username": "dp4",
        "weekly_hours": 40,
        "use_daily_schedule": True,
        "hours_monday": 20, "hours_tuesday": 20, "hours_wednesday": 20, "hours_thursday": 5,
    })
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_uniform_mode_is_unaffected_by_the_new_validator(db, admin, default_tenant):
    """Sanity/Byte-Identitaet: use_daily_schedule=False (Default) darf den
    neuen Validator gar nicht erst ausloesen — die ueberwiegende Mehrheit der
    Mitarbeitenden bleibt unveraendert."""
    client = _client_as(db, admin, admin)
    resp = client.post(USERS, json={**BASE_PAYLOAD, "username": "plain", "weekly_hours": 40})
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["weekly_hours"] == 40.0
    app.dependency_overrides.clear()


def test_reading_a_legacy_inconsistent_user_does_not_500_or_rewrite_the_stored_value(db, admin, default_tenant):
    """Regression guard: die Quervalidierung lebt bewusst NUR auf `UserCreate`,
    NICHT auf `UserBase` (das auch `UserResponse` fuer GET /users/{id} erbt) —
    exakt die Falle, vor der `WorkingHoursChangeCreate.check_mode` bereits
    warnt ("ein mode='after'-Validator liefe auch beim Lesen"). Eine
    Bestandszeile, die vor diesem Fix (oder vor Migration 067) inkonsistent
    angelegt wurde, muss weiterhin ohne 500 lesbar sein — UND ihren
    tatsaechlich gespeicherten Wert zeigen, nicht einen beim Lesen
    umgerechneten oder gar einen HTTP 500 wegen der "mindestens ein Tag"-
    Regel bei einer (hier bewusst) leeren Historie."""
    legacy = _user(db, "legacy_inconsistent", weekly=Decimal("40"))
    legacy.use_daily_schedule = True
    legacy.hours_monday = Decimal("8")
    legacy.hours_tuesday = Decimal("5")
    legacy.hours_wednesday = Decimal("4")
    # weekly_hours bleibt bewusst 40 — der Widerspruch, den Migration 067 bei
    # Historienzeilen behebt, aber die USER-Zeile selbst hier absichtlich
    # (fuer den Test) unrepariert laesst.
    db.commit()

    client = _client_as(db, admin, admin)
    resp = client.get(f"{USERS}/{legacy.id}")
    assert resp.status_code == 200, resp.text
    # Der gespeicherte (widerspruechliche) Wert kommt unveraendert durch —
    # kein stiller Recompute beim Lesen.
    assert resp.json()["weekly_hours"] == 40.0
    app.dependency_overrides.clear()
