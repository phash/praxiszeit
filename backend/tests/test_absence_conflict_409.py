"""Audit 2026-07-31 (A2), Rückfallebene: ein Unique-Verstoß beim Anlegen einer
Abwesenheit muss als verständliche 409 herauskommen — nie als nackter
``IntegrityError`` (HTTP 500).

Die echte Kollision ist nach dem Fix praktisch unerreichbar: die Anker-Sperre
auf der Benutzerzeile serialisiert alle Buchungspfade, und jede parallele
Sitzung, die bereits eine Abwesenheit eingefügt hat, hält über deren
Fremdschlüssel implizit ein ``FOR KEY SHARE`` auf derselben Benutzerzeile
(siehe ``tests/test_concurrency.py``). Der Übersetzer um ``db.commit()`` bleibt
Gürtel-und-Hosenträger — geprüft wird er hier per Fehlerinjektion, weil sich der
Zustand sonst nicht mehr deterministisch herstellen lässt.
"""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User, UserRole
from tests.conftest import DEFAULT_TENANT_ID


def _app() -> FastAPI:
    from app.routers import absences
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    return app


_APP = _app()


@pytest.fixture(autouse=True)
def _clear():
    yield
    _APP.dependency_overrides.clear()


def _client(db, user):
    def odb():
        yield db
    _APP.dependency_overrides[get_db] = odb
    _APP.dependency_overrides[get_current_user] = lambda: user
    return TestClient(_APP)


def _employee(db):
    u = User(
        id=uuid.uuid4(), username=f"c409{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.l",
        password_hash="x", first_name="Kon", last_name="Flikt", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
        track_hours=True, use_daily_schedule=False, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _inject_unique_violation(monkeypatch, db):
    """Lässt den ersten ``db.commit()`` so scheitern wie Postgres bei einem
    Verstoß gegen ``uq_tenant_user_date_type``."""
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError(
                "INSERT INTO absences ...", {},
                Exception('duplicate key value violates unique constraint '
                          '"uq_tenant_user_date_type"'),
            )
        raise AssertionError("commit darf nach dem Fehler nicht erneut laufen")

    monkeypatch.setattr(db, "commit", flaky_commit)
    return calls


def test_unique_violation_becomes_409_single_day(db, default_tenant, monkeypatch):
    u = _employee(db)
    _inject_unique_violation(monkeypatch, db)

    resp = _client(db, u).post("/api/absences", json={
        "date": "2026-03-03", "type": "sick", "hours": 8,
    })

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "03.03.2026" in detail
    assert "zeitgleich" in detail


def test_unique_violation_becomes_409_range(db, default_tenant, monkeypatch):
    u = _employee(db)
    _inject_unique_violation(monkeypatch, db)

    resp = _client(db, u).post("/api/absences", json={
        "date": "2026-03-03", "end_date": "2026-03-05", "type": "sick", "hours": 8,
    })

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    # Bei Zeiträumen nennt die Meldung die Spanne, nicht jeden Einzeltag.
    assert "03.03.2026–05.03.2026" in detail
