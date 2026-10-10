"""Spec 2026-10-08, Abschnitt 14 / E67 / P12 (PR2): GET /api/auth/me/work-schedule —
heute gültige Blöcke und Verlauf, datumsaufgelöst, ohne Freitext."""
import datetime as dt
import uuid
from datetime import date

import app.routers.auth as auth_router
from app.models import WorkingHoursChange
from app.models.tenant import Tenant
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, legacy_week

TODAY = date(2026, 10, 8)
LEGACY = legacy_week(mon=("07:30", "16:30"))


def _row(db, user, effective_from, blocks, **kw):
    row = WorkingHoursChange(
        user_id=user.id, tenant_id=kw.pop("tenant_id", DEFAULT_TENANT_ID),
        effective_from=effective_from, weekly_hours=kw.pop("weekly_hours", 40.0),
        use_daily_schedule=False, work_days_per_week=5, blocks=blocks,
        note=kw.pop("note", None), **kw)
    db.add(row)
    db.commit()
    return row


def _get(client, monkeypatch, d=TODAY):
    monkeypatch.setattr(auth_router, "now_local", lambda: dt.datetime(d.year, d.month, d.day, 10, 0))
    r = client.get("/api/auth/me/work-schedule")
    assert r.status_code == 200, r.text
    return r


def test_without_history_resolves_the_fallback(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    body = _get(employee_client, monkeypatch).json()
    assert body["today"]["date"] == "2026-10-08"
    assert body["today"]["blocks"] == K_BLOCKS
    assert body["today"]["day_targets"] == [8.0, 8.0, 8.0, 8.0, 8.0]
    assert body["today"]["weekly_hours"] == 40.0
    assert body["history"] == []


def test_history_with_until_future_row_and_no_note(_db_session, employee_user, employee_client, monkeypatch):
    _row(_db_session, employee_user, date(2026, 1, 1), LEGACY, note="Grund mit Klarnamen")
    _row(_db_session, employee_user, date(2026, 9, 1), K_BLOCKS, weekly_hours=20.0)
    _row(_db_session, employee_user, date(2026, 11, 1), None, weekly_hours=25.0)   # zukunftsdatiert
    r = _get(employee_client, monkeypatch)
    body = r.json()
    assert [h["effective_from"] for h in body["history"]] == ["2026-01-01", "2026-09-01", "2026-11-01"]
    assert [h["effective_until"] for h in body["history"]] == ["2026-08-31", "2026-10-31", None]
    assert body["history"][0]["blocks"] == LEGACY
    assert body["history"][1]["day_targets"] == [4.0, 4.0, 4.0, 4.0, 4.0]
    assert body["history"][2]["blocks"] is None
    assert body["today"]["blocks"] == K_BLOCKS        # die Novemberzeile wirkt heute nicht
    assert body["today"]["weekly_hours"] == 20.0
    assert "Klarnamen" not in r.text                  # P12: kein Freitext


def test_rows_of_another_tenant_are_ignored(_db_session, employee_user, employee_client, monkeypatch):
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    _db_session.add(other)
    _db_session.commit()
    _row(_db_session, employee_user, date(2026, 9, 1), K_BLOCKS, tenant_id=other.id)
    assert _get(employee_client, monkeypatch).json()["history"] == []


# Review Task 10: die Karte braucht den Modus, sonst nennt sie Werte „Tagessoll", die
# keins sind — #377-Fix-Modus (Tageswerte = geplante Anwesenheit) bzw. #191 ohne
# Stundenzählung (kein Soll, keine Kappung, E35/E63).

def test_regular_mode_counts_hours_without_fixed_target(_db_session, employee_user, employee_client, monkeypatch):
    body = _get(employee_client, monkeypatch).json()
    assert body["track_hours"] is True
    assert body["fixed_monthly_hours"] is None


def test_fixed_mode_names_the_flat_monthly_hours(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.weekly_hours = 10.0
    employee_user.milog_working_time_account = True
    employee_user.agreed_monthly_hours = 43.0
    employee_user.use_fixed_monthly_target = True
    _db_session.commit()
    body = _get(employee_client, monkeypatch).json()
    assert body["fixed_monthly_hours"] == 43.0
    # Die Tageswerte bleiben die geplante Anwesenheit (wie journal_service, Finding 3 #377).
    assert body["today"]["day_targets"] == [2.0, 2.0, 2.0, 2.0, 2.0]
    assert body["track_hours"] is True


def test_fixed_flag_without_agreed_hours_is_no_fixed_mode(_db_session, employee_user, employee_client, monkeypatch):
    # #463: dieselbe Bedingung wie journal_service.fixed_mode — das Flag allein genügt nicht.
    employee_user.use_fixed_monthly_target = True
    employee_user.agreed_monthly_hours = None
    _db_session.commit()
    assert _get(employee_client, monkeypatch).json()["fixed_monthly_hours"] is None


def test_without_hour_tracking(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.track_hours = False
    employee_user.work_blocks = LEGACY
    _db_session.commit()
    body = _get(employee_client, monkeypatch).json()
    assert body["track_hours"] is False
    assert body["today"]["day_targets"] == [0.0, 0.0, 0.0, 0.0, 0.0]
    assert body["today"]["blocks"] == LEGACY
