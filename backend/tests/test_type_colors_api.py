"""API-Tests für Typ-Farben (#157): GET /api/me/type-colors (jeder Nutzer),
GET/PUT /api/admin/settings/type-colors (Admin)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.services import type_colors_service as svc


def _app() -> FastAPI:
    from app.routers import me as me_router, admin as admin_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="TypeColors Test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(me_router.router)
    app.include_router(admin_router.router)
    return app


_APP = _app()


def _client(db, current, *, admin=None):
    def _odb():
        yield db
    _APP.dependency_overrides[get_db] = _odb
    _APP.dependency_overrides[get_current_user] = lambda: current
    _APP.dependency_overrides[require_admin] = lambda: (admin or current)
    return TestClient(_APP)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _APP.dependency_overrides.clear()


def test_me_type_colors_returns_defaults(db, test_user):
    client = _client(db, test_user)
    resp = client.get("/api/me/type-colors")
    assert resp.status_code == 200, resp.text
    assert resp.json() == svc.DEFAULT_TYPE_COLORS


def test_admin_put_then_me_get_reflects_change(db, test_user, test_admin):
    admin_client = _client(db, test_admin)
    put = admin_client.put("/api/admin/settings/type-colors", json={"vacation": "#123456"})
    assert put.status_code == 200, put.text
    assert put.json()["vacation"] == "#123456"

    # an employee in the same tenant sees the configured colour
    emp_client = _client(db, test_user)
    got = emp_client.get("/api/me/type-colors")
    assert got.status_code == 200
    assert got.json()["vacation"] == "#123456"
    assert got.json()["work"] == svc.DEFAULT_TYPE_COLORS["work"]


def test_admin_put_rejects_invalid_hex(db, test_admin):
    admin_client = _client(db, test_admin)
    resp = admin_client.put("/api/admin/settings/type-colors", json={"vacation": "red"})
    assert resp.status_code == 400, resp.text


def test_admin_put_rejects_unknown_type(db, test_admin):
    admin_client = _client(db, test_admin)
    resp = admin_client.put("/api/admin/settings/type-colors", json={"holiday": "#112233"})
    assert resp.status_code == 400, resp.text


def test_admin_get_type_colors(db, test_admin):
    admin_client = _client(db, test_admin)
    resp = admin_client.get("/api/admin/settings/type-colors")
    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == set(svc.DEFAULT_TYPE_COLORS)
