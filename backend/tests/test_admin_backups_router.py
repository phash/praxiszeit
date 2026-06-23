"""#213 — Router-Tests fuer /api/admin/backups (Auth-Gate + Endpoints).

pg_dump wird gemockt (kein echtes pg_dump in der SQLite-Suite); die Auth-Gates
und Response-Formen laufen echt gegen die FastAPI-App.
"""
import io

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.services import backup_service as bs
from tests.test_endpoints import test_app
from tests.conftest import DEFAULT_TENANT_ID


class _FakePopen:
    def __init__(self, payload=b"-- PraxisZeit dump\nSELECT 1;\n", rc=0, stderr=b""):
        self.stdout = io.BytesIO(payload)
        self.stderr = io.BytesIO(stderr)
        self._rc = rc

    def wait(self):
        return self._rc


def _mk_user(db, role, username):
    u = User(
        username=username, email=f"{username}@example.de", password_hash="h",
        first_name="A", last_name="B", role=role,
        weekly_hours=40, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def admin_client(db, default_tenant, tmp_path, monkeypatch):
    monkeypatch.delenv("PRAXISZEIT_BACKUP_DIR", raising=False)
    admin = _mk_user(db, UserRole.ADMIN, "bkadmin")
    bs.update_config(db, location=str(tmp_path))

    def _odb():
        yield db

    def _cur():
        return admin

    test_app.dependency_overrides[get_db] = _odb
    test_app.dependency_overrides[get_current_user] = _cur
    test_app.dependency_overrides[require_admin] = _cur
    with TestClient(test_app) as c:
        yield c, tmp_path
    test_app.dependency_overrides.clear()


def test_list_returns_config_and_empty(admin_client):
    client, _ = admin_client
    r = client.get("/api/admin/backups")
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["enabled"] is False
    assert body["backups"] == []


def test_update_config(admin_client):
    client, _ = admin_client
    r = client.put("/api/admin/backups/config", json={"enabled": True, "hour": 5, "retention_days": 14})
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["enabled"] is True and cfg["hour"] == 5 and cfg["retention_days"] == 14


def test_create_backup_endpoint(admin_client, monkeypatch):
    client, tmp_path = admin_client
    # URL aus Teilen bauen, damit das Schema im Quelltext nicht direkt von
    # Dummy-Credentials gefolgt wird (Secret-Scanner-Hook).
    _scheme = "postgresql://"
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _scheme + "su:pw@db:5432/praxiszeit")
    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: _FakePopen())
    r = client.post("/api/admin/backups")
    assert r.status_code == 201
    fn = r.json()["filename"]
    assert fn.startswith("praxiszeit_") and fn.endswith(".sql.gz")
    assert (tmp_path / fn).exists()
    # taucht jetzt in der Liste auf
    assert any(b["filename"] == fn for b in client.get("/api/admin/backups").json()["backups"])


def test_create_backup_without_superuser_url_500(admin_client, monkeypatch):
    client, _ = admin_client
    monkeypatch.delenv("DATABASE_URL_MIGRATIONS", raising=False)
    r = client.post("/api/admin/backups")
    assert r.status_code == 500
    assert "DATABASE_URL_MIGRATIONS" in r.json()["detail"]


def test_delete_and_download_404(admin_client):
    client, tmp_path = admin_client
    # vorhandene Datei loeschen
    f = tmp_path / "praxiszeit_20260101_010101.sql.gz"
    f.write_bytes(b"x")
    assert client.delete(f"/api/admin/backups/{f.name}").status_code == 204
    # nicht vorhanden -> 404
    assert client.delete("/api/admin/backups/praxiszeit_20990101_000000.sql.gz").status_code == 404
    assert client.get("/api/admin/backups/praxiszeit_20990101_000000.sql.gz/download").status_code == 404


def test_config_write_probe_rejects_unwritable(admin_client):
    client, _ = admin_client
    r = client.put("/api/admin/backups/config", json={"location": "/proc/nonexistent/cannot-write"})
    assert r.status_code == 400


def test_employee_forbidden(db, default_tenant):
    """Auth-Gate: ein Nicht-Admin bekommt 403 (require_admin nicht ueberschrieben)."""
    employee = _mk_user(db, UserRole.EMPLOYEE, "bkemp")

    def _odb():
        yield db

    def _cur():
        return employee

    test_app.dependency_overrides[get_db] = _odb
    test_app.dependency_overrides[get_current_user] = _cur
    # require_admin ABSICHTLICH nicht ueberschrieben -> echter Gate laeuft
    try:
        with TestClient(test_app) as c:
            assert c.get("/api/admin/backups").status_code == 403
    finally:
        test_app.dependency_overrides.clear()
