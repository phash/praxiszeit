"""#431: die Vertragshistorie im §16-Notfall-Export des Superadmins.

Seit #431 sind ``working_hours_changes`` die autoritative Quelle des Tagessolls
— ``get_schedule_for_date`` loest daraus Wochenstunden, Modus, Tageswerte und
Arbeitstage je Datum auf. Der Art.-15-Export (``lifecycle_service``) und der
Art.-20-Export (``auth.py``) fuehren die Historie folgerichtig mit; der
Superadmin-§16-Export lieferte als einzige Vertragsangabe den HEUTIGEN
``weekly_hours``.

Bei einem deaktivierten Tenant ist er der einzige erreichbare Weg
(``/api/tenant/export`` ist dann gesperrt) — ohne die Historie laesst sich das
Soll vergangener Monate aus dem Dokument nicht mehr herleiten.

Fehlerklasse #383/#408 mitgeprueft: der Payload geht durch rohes ``json.dumps``
(nicht ``jsonable_encoder``), jedes ``Numeric``-Feld MUSS ``float()``-gecastet
sein — sonst HTTP 500 beim Serialisieren.
"""
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db, Base
from app.middleware.auth import require_superadmin
from app.models import User, UserRole, WorkingHoursChange
from app.models.tenant import Tenant
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

OTHER_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000ff")


def _create_test_app() -> FastAPI:
    from app.routers import superadmin
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(superadmin.router)
    return app


_app = _create_test_app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def tenants(db):
    a = Tenant(id=DEFAULT_TENANT_ID, name="Praxis A", slug="a", is_active=False, mode="single")
    b = Tenant(id=OTHER_TENANT_ID, name="Praxis B", slug="b", is_active=True, mode="single")
    db.add_all([a, b])
    db.commit()
    return a, b


def _make_user(db, tenant_id, username, **kw):
    u = User(username=username, email=f"{username}@x.de",
             password_hash=auth_service.hash_password("x"),
             first_name=username, last_name="T", role=UserRole.EMPLOYEE,
             weekly_hours=Decimal("17.75"), vacation_days=30,
             work_days_per_week=4, is_active=True, tenant_id=tenant_id, **kw)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _superadmin(db):
    u = User(username="root", email="root@x.de",
             password_hash=auth_service.hash_password("x"),
             first_name="Root", last_name="Admin", role=UserRole.ADMIN,
             weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
             is_active=True, tenant_id=None)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _export(db, tenant_id, monkeypatch):
    root = _superadmin(db)
    from app.routers import superadmin as sa_router
    # SQLite kennt kein RLS -> set_superadmin_context (SET LOCAL) no-oppen.
    monkeypatch.setattr(sa_router, "set_superadmin_context", lambda _db: None)

    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[require_superadmin] = lambda: root
    client = TestClient(_app)
    r = client.get(f"/api/superadmin/tenants/{tenant_id}/arbzg-export")
    _app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    return json.loads(r.content)


@pytest.fixture
def seeded(db, tenants):
    """MA von Praxis A mit Moduswechsel; ein zweiter MA in Praxis B."""
    a_user = _make_user(db, DEFAULT_TENANT_ID, "empA",
                        use_daily_schedule=True, hours_monday=Decimal("4.25"),
                        hours_tuesday=Decimal("4.5"), hours_wednesday=Decimal("4.5"),
                        hours_thursday=Decimal("4.5"))
    b_user = _make_user(db, OTHER_TENANT_ID, "empB")
    db.add(WorkingHoursChange(
        user_id=a_user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("40.0"),
        use_daily_schedule=False, work_days_per_week=5, note="Start"))
    db.add(WorkingHoursChange(
        user_id=a_user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=date(2026, 3, 1), weekly_hours=Decimal("17.75"),
        use_daily_schedule=True, hours_monday=Decimal("4.25"),
        hours_tuesday=Decimal("4.5"), hours_wednesday=Decimal("4.5"),
        hours_thursday=Decimal("4.5"), work_days_per_week=4, note="Teilzeit"))
    # Fremd-Tenant-Zeile: darf NIE im Export von Praxis A auftauchen.
    db.add(WorkingHoursChange(
        user_id=b_user.id, tenant_id=OTHER_TENANT_ID,
        effective_from=date(2026, 2, 1), weekly_hours=Decimal("30.0"),
        use_daily_schedule=False, work_days_per_week=5, note="FREMD"))
    db.commit()
    return a_user, b_user


def test_export_carries_contract_history(db, seeded, monkeypatch):
    """Reproduktion: ohne Historie ist das Soll vergangener Monate aus dem
    §16-Dokument nicht herleitbar."""
    a_user, _ = seeded
    payload = _export(db, DEFAULT_TENANT_ID, monkeypatch)

    row = next(u for u in payload["users"] if u["username"] == "empA")
    history = row["working_hours_changes"]
    assert [h["effective_from"] for h in history] == ["2026-01-01", "2026-03-01"]
    assert history[0]["weekly_hours"] == 40.0
    assert history[0]["use_daily_schedule"] is False
    assert history[1]["weekly_hours"] == 17.75
    assert history[1]["use_daily_schedule"] is True
    assert history[1]["hours_monday"] == 4.25
    assert history[1]["work_days_per_week"] == 4
    assert history[1]["note"] == "Teilzeit"


def test_export_carries_day_plan_fields_of_the_user_row(db, seeded, monkeypatch):
    """Die User-Zeile ist der Rueckfallwert fuer die Zeit VOR der ersten
    erfassten Aenderung — ohne ihre Tagesplan-Felder bleibt dieser Zeitraum
    unbestimmt."""
    payload = _export(db, DEFAULT_TENANT_ID, monkeypatch)
    row = next(u for u in payload["users"] if u["username"] == "empA")

    assert row["use_daily_schedule"] is True
    assert row["work_days_per_week"] == 4
    assert row["hours_monday"] == 4.25
    assert row["hours_friday"] is None
    assert row["track_hours"] is True
    # Die krumme Wochenstundenzahl ueberlebt (Migration 069).
    assert row["weekly_hours"] == 17.75


def test_history_is_tenant_scoped(db, seeded, monkeypatch):
    """``set_superadmin_context`` hebelt RLS auf — der explizite Tenant-Filter
    ist hier PFLICHT, nicht Guertel-und-Hosentraeger."""
    payload = _export(db, DEFAULT_TENANT_ID, monkeypatch)

    assert {u["username"] for u in payload["users"]} == {"empA"}
    all_notes = [
        h["note"]
        for u in payload["users"]
        for h in u["working_hours_changes"]
    ]
    assert "FREMD" not in all_notes


def test_numeric_fields_are_json_serialisable(db, seeded, monkeypatch):
    """Fehlerklasse #383/#408: rohes ``json.dumps`` kann ``Decimal`` nicht
    serialisieren. Der Export darf nirgends ein ungecastetes ``Numeric``
    durchreichen — sonst HTTP 500 fuer den gesamten Notfall-Export."""
    payload = _export(db, DEFAULT_TENANT_ID, monkeypatch)
    row = next(u for u in payload["users"] if u["username"] == "empA")

    for key in ("weekly_hours", "hours_monday", "hours_tuesday",
                "hours_wednesday", "hours_thursday", "hours_friday"):
        assert row[key] is None or isinstance(row[key], float), key
    for h in row["working_hours_changes"]:
        for key in ("weekly_hours", "hours_monday", "hours_tuesday",
                    "hours_wednesday", "hours_thursday", "hours_friday"):
            assert h[key] is None or isinstance(h[key], float), key
    # Ein zweiter, direkter Serialisierungsdurchlauf faengt jeden Rest-Decimal.
    json.dumps(payload)


def test_user_without_history_gets_empty_list(db, tenants, monkeypatch):
    """Kein Sonderfall/None — eine leere Liste, wie im Art.-15-Export."""
    _make_user(db, DEFAULT_TENANT_ID, "plain")
    payload = _export(db, DEFAULT_TENANT_ID, monkeypatch)

    row = next(u for u in payload["users"] if u["username"] == "plain")
    assert row["working_hours_changes"] == []
