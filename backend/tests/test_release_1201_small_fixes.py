"""Release-Review 1.20.1: kleine Funde, die je als HTTP 500 bzw. falscher
Exportwert endeten.

1. XLS-Import: beschaedigte/abgeschnittene .xls (OLE2-Kopf korrekt, Rest kaputt)
   -> xlrd wirft CompDocError/IndexError statt XLRDError -> 500. Soll: 400.
2. Betriebsferien-Name ohne Laengengrenze (Spalte String(255)) -> 500 auf PG.
   Soll: 422 bei > 255 Zeichen und bei leerem Namen.
3. Monat/Jahr ohne Grenzen (z. B. /api/dashboard?month=13 -> IllegalMonthError).
   Soll: 422.
4. Mandanten-Export: ``change_requests[].status`` lieferte
   'ChangeRequestStatus.APPROVED' statt 'approved'.
5. Reaktivieren umging das Mitarbeiter-Limit der Lizenz.
"""
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import license as license_mod
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.change_request import ChangeRequest, ChangeRequestStatus, ChangeRequestType
from app.models.tenant import Tenant
from app.services import lifecycle_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

_XLS_DIR = Path(__file__).resolve().parents[2] / "e2e" / "test-data"


def _sample_xls_bytes() -> bytes:
    files = sorted(_XLS_DIR.glob("timerec_*.xls"))
    if files:
        return files[0].read_bytes()
    # Fallback (Backend-Container ohne e2e/): OLE2-Kopf + Muell.
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 4096


@pytest.fixture
def client_as(db):
    def _client(user):
        def _override_db():
            yield db
        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[require_admin] = lambda: user
        return TestClient(test_app)
    yield _client
    test_app.dependency_overrides.clear()


# ── Fund 1: beschaedigte XLS ──────────────────────────────────────────────

class TestTruncatedXls:
    @pytest.mark.parametrize("length", [1024, 8])
    def test_truncated_xls_is_400(self, test_admin, test_user, client_as, length):
        content = _sample_xls_bytes()[:length]
        assert content.startswith(b"\xd0\xcf\x11\xe0")
        r = client_as(test_admin).post(
            "/api/admin/import/preview",
            files={"file": ("kaputt.xls", content, "application/vnd.ms-excel")},
            data={"user_id": str(test_user.id)},
        )
        assert r.status_code == 400, r.text
        assert "beschädigt" in r.json()["detail"]

    def test_parse_xls_raises_value_error(self, db, test_user):
        from app.services.xls_import_service import parse_xls
        with pytest.raises(ValueError, match="beschädigt"):
            parse_xls(_sample_xls_bytes()[:1024], test_user.id, db, tenant_id=DEFAULT_TENANT_ID)


# ── Fund 2: Betriebsferien-Name ───────────────────────────────────────────

class TestClosureNameLength:
    def _body(self, name):
        return {"name": name, "start_date": "2026-08-03", "end_date": "2026-08-07"}

    @pytest.mark.parametrize("name", ["x" * 256, ""])
    def test_create_rejects_invalid_name(self, test_admin, client_as, name):
        r = client_as(test_admin).post("/api/company-closures/", json=self._body(name))
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("name", ["x" * 256, ""])
    def test_update_rejects_invalid_name(self, test_admin, client_as, name):
        r = client_as(test_admin).put(f"/api/company-closures/{uuid.uuid4()}", json=self._body(name))
        assert r.status_code == 422, r.text

    def test_create_accepts_255(self, test_admin, client_as):
        r = client_as(test_admin).post("/api/company-closures/", json=self._body("x" * 255))
        assert r.status_code == 201, r.text


# ── Fund 3: Monat/Jahr-Grenzen ────────────────────────────────────────────

class TestMonthYearBounds:
    @pytest.mark.parametrize("url", [
        "/api/dashboard/?month=13",
        "/api/dashboard/?month=0",
        "/api/dashboard/?year=0",
        "/api/admin/reports/rest-time-violations?year=2026&month=13",
        "/api/admin/reports/rest-time-violations?year=0",
        "/api/admin/reports/sunday-summary?year=0",
        "/api/holidays/?year=0",
    ])
    def test_out_of_range_is_422(self, test_admin, client_as, url):
        r = client_as(test_admin).get(url)
        assert r.status_code == 422, r.text

    def test_valid_month_still_ok(self, test_admin, client_as):
        r = client_as(test_admin).get("/api/dashboard/?year=2026&month=12")
        assert r.status_code == 200, r.text


# ── Fund 4: Export-Status als Enum-Wert ───────────────────────────────────

def test_tenant_export_change_request_status_is_value(db, test_admin, test_user):
    db.add(ChangeRequest(
        user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.APPROVED,
        reason="Test", proposed_date=date(2026, 5, 4),
    ))
    db.commit()
    tenant = db.query(Tenant).filter(Tenant.id == DEFAULT_TENANT_ID).one()
    payload = lifecycle_service.build_tenant_export_payload(db, tenant, requester=test_admin)
    statuses = {c["status"] for c in payload["change_requests"]}
    assert statuses == {"approved"}


# ── Fund 5: Reaktivieren respektiert das Lizenz-Limit ─────────────────────

class TestReactivateEmployeeLimit:
    def _inactive(self, db):
        u = User(
            id=uuid.uuid4(), username="ruhend", email="ruhend@praxis.invalid",
            password_hash="x", first_name="Ruhend", last_name="Test",
            role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
            work_days_per_week=5, is_active=False, tenant_id=DEFAULT_TENANT_ID,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def _active_count(self, db):
        return db.query(User).filter(
            User.tenant_id == DEFAULT_TENANT_ID, User.is_active == True,  # noqa: E712
        ).count()

    def test_reactivate_blocked_at_limit(self, db, test_admin, client_as, monkeypatch):
        gone = self._inactive(db)
        monkeypatch.setattr(license_mod, "_current_license",
                            SimpleNamespace(max_employees=self._active_count(db)))
        r = client_as(test_admin).post(f"/api/admin/users/{gone.id}/reactivate")
        assert r.status_code == 403, r.text
        db.expire_all()
        assert db.get(User, gone.id).is_active is False

    def test_reactivate_allowed_below_limit(self, db, test_admin, client_as, monkeypatch):
        gone = self._inactive(db)
        monkeypatch.setattr(license_mod, "_current_license",
                            SimpleNamespace(max_employees=self._active_count(db) + 1))
        r = client_as(test_admin).post(f"/api/admin/users/{gone.id}/reactivate")
        assert r.status_code == 200, r.text

    def test_reactivate_already_active_not_blocked(self, db, test_admin, test_user, client_as, monkeypatch):
        # Bereits aktives Konto belegt keinen zusaetzlichen Platz -> idempotent.
        monkeypatch.setattr(license_mod, "_current_license",
                            SimpleNamespace(max_employees=self._active_count(db)))
        r = client_as(test_admin).post(f"/api/admin/users/{test_user.id}/reactivate")
        assert r.status_code == 200, r.text


# ── Fund 6: 5-MB-Import erreicht das Backend ──────────────────────────────
# Der XLS-Import verspricht 5 MB (import_xls.py), aber nginx (2M) UND die
# Backend-RequestSizeLimitMiddleware (2 MB, unbedingt, auch nativ) schnitten
# vorher ab -> 413. Die Grenze gilt jetzt pfadgenau: 6 MB nur fuer
# /api/admin/import/, sonst bleibt es bei 2 MB.

def _size_app(**kw):
    from fastapi import FastAPI, Request
    from app.middleware.static_serving import RequestSizeLimitMiddleware

    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, **kw)

    @app.post("/api/admin/import/preview")
    async def _imp(request: Request):
        return {"n": len(await request.body())}

    @app.post("/api/other")
    async def _other(request: Request):
        return {"n": len(await request.body())}

    return app


class TestImportSizeLimit:
    MB = 1024 * 1024

    def _client(self):
        return TestClient(_size_app(max_size=2 * self.MB,
                                    path_limits={"/api/admin/import/": 6 * self.MB}))

    def test_import_path_accepts_5mb(self):
        r = self._client().post("/api/admin/import/preview", content=b"x" * (5 * self.MB))
        assert r.status_code == 200, r.text

    def test_import_path_still_capped(self):
        r = self._client().post("/api/admin/import/preview", content=b"x" * (6 * self.MB + 1))
        assert r.status_code == 413

    def test_other_paths_keep_2mb(self):
        r = self._client().post("/api/other", content=b"x" * (2 * self.MB + 1))
        assert r.status_code == 413

    def test_real_app_configures_import_limit(self):
        from app.main import app as real_app
        from app.middleware.static_serving import RequestSizeLimitMiddleware
        mw = next(m for m in real_app.user_middleware if m.cls is RequestSizeLimitMiddleware)
        assert mw.kwargs["max_size"] == 2 * self.MB
        assert mw.kwargs["path_limits"] == {"/api/admin/import/": 6 * self.MB}

    @pytest.mark.parametrize("conf", ["frontend/nginx.conf", "ssl/nginx-ssl.conf"])
    def test_nginx_import_location_allows_6m(self, conf):
        path = Path(__file__).resolve().parents[2] / conf
        if not path.exists():
            pytest.skip(f"{conf} nicht im Container eingebunden")
        text = path.read_text()
        assert "client_max_body_size 2M;" in text
        block = text.split("location ^~ /api/admin/import/ {", 1)[1].split("}", 1)[0]
        assert "client_max_body_size 6M;" in block
        assert "proxy_set_header Host $http_host;" in block
