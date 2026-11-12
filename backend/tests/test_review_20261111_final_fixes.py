"""Code-Review 2026-11-11, Schlussrunde: B1-B4."""
import gzip
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.models import Absence, AbsenceType
from app.models.system_setting import SystemSetting
from app.routers import absences as absences_router
from app.routers import admin_users
from app.routers import vacation_requests as vr_router
from app.services import backup_service as bs
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
    endpoints_app,
)


# ── B1: Antragsprobe prüft nur buchbare Tage ─────────────────────────

def test_request_over_legacy_absence_on_weekend_is_not_refused(
        _db_session, employee_user, employee_client, monkeypatch):
    """Eine (Alt-)Abwesenheit an einem Samstag blockiert den Antrag Fr–Mo nicht:
    die Genehmigung bucht den Samstag ohnehin nie (``request_workday_candidates``)."""
    _db_session.merge(SystemSetting(key="vacation_approval_required",
                                    tenant_id=DEFAULT_TENANT_ID, value="true"))
    today = date(2026, 6, 10)
    monkeypatch.setattr(absences_router, "today_local", lambda: today)
    monkeypatch.setattr(vr_router, "today_local", lambda: today)
    _db_session.add(Absence(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
                            date=date(2026, 6, 13), type=AbsenceType.SICK,
                            hours=8.0, half_day=False))
    _db_session.commit()
    r = employee_client.post("/api/vacation-requests/", json={
        "date": "2026-06-12", "end_date": "2026-06-15", "hours": 8,
        "absence_type": "training"})
    assert r.status_code < 300, r.text


# ── B2: Sperrfrist nach Berliner Kalendertag ─────────────────────────

def test_grace_days_use_berlin_date_of_deactivation(monkeypatch):
    # 22:30 UTC am 01.06. = 00:30 Berlin am 02.06.
    user = SimpleNamespace(deactivated_at=datetime(2026, 6, 1, 22, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(admin_users, "today_local", lambda: date(2026, 6, 15))
    assert admin_users._grace_days_since_deactivation(user) == 13


def test_grace_end_is_berlin_date_plus_14(monkeypatch):
    user = SimpleNamespace(deactivated_at=datetime(2026, 6, 1, 22, 30, tzinfo=timezone.utc))
    assert admin_users._grace_period_end(user) == date(2026, 6, 16)


# ── B3: CORS legt X-Hidden-With-Data-Count offen ─────────────────────

def test_cors_exposes_hidden_count_header():
    from starlette.middleware.cors import CORSMiddleware
    from app import main
    cors = [m for m in main.app.user_middleware if m.cls is CORSMiddleware]
    assert cors
    exposed = cors[0].kwargs["expose_headers"]
    assert "X-Hidden-With-Data-Count" in exposed
    assert "X-Requires-TOTP" in exposed


# ── B4: Backup räumt bei Fehlern vor dem Dump auf ────────────────────

def _backup_env(db, tmp_path, monkeypatch):
    from tests.test_backup_service import _use_tmp_dir, _migr_url
    _use_tmp_dir(db, tmp_path)
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _migr_url("su", "pw", host="db"))


def test_backup_signer_failure_leaves_no_file_and_no_process(db, default_tenant, tmp_path, monkeypatch):
    _backup_env(db, tmp_path, monkeypatch)
    spawned = []
    monkeypatch.setattr(bs.subprocess, "Popen", lambda *a, **k: spawned.append(1))
    from app.core import backup_mac

    def boom(*a, **k):
        raise RuntimeError("kaputter Schluessel")
    monkeypatch.setattr(backup_mac, "BackupMac", boom)
    with pytest.raises(RuntimeError):
        bs.create_backup(db)
    assert list(tmp_path.iterdir()) == []
    assert spawned == []  # kein pg_dump-Prozess gestartet


def test_backup_popen_oserror_leaves_no_file(db, default_tenant, tmp_path, monkeypatch):
    _backup_env(db, tmp_path, monkeypatch)

    def boom(*a, **k):
        raise PermissionError("nicht ausfuehrbar")
    monkeypatch.setattr(bs.subprocess, "Popen", boom)
    with pytest.raises(PermissionError):
        bs.create_backup(db)
    assert list(tmp_path.iterdir()) == []
