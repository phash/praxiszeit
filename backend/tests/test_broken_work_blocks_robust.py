"""Gesamtreview B3: strukturell kaputtes Blöcke-JSON (nur per Hand in der
Datenbank erzeugbar — jeder Schreibweg prüft streng) darf keine Fläche mit
HTTP 500 sperren.

Bis dahin warf der Resolver (``calculation_service.get_schedule_for_date``)
``ValueError``. Gefangen wurde das nur in ``attach_work_blocks_today`` (Login,
Benutzerliste); ``/me/work-schedule``, Dashboard, Admin-Monatsbericht (eine
kaputte Person sperrte die GANZE Team-Tabelle), Stempeln und jede
Soll-Rechnung endeten in HTTP 500. Jetzt gilt kaputtes JSON wie NULL als
„keine Blöcke" (E8) — Log-Warnung statt Absturz; das Soll liest Blöcke ohnehin
nie (es kommt aus den materialisierten ``hours_*``), die Kappung entfällt an
diesen Tagen wie an jedem Tag ohne Blöcke, und das Stempeln bleibt möglich
(§16 ArbZG: Aufzeichnung darf nicht an einem Datenfehler scheitern).
"""
import datetime as dt
import logging
from datetime import time, timedelta

import pytest

import app.routers.time_entries as te
from app.models import TimeEntry, WorkingHoursChange
from app.services import calculation_service
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

_LOGGER = "app.services.calculation_service"

BROKEN_FORMS = [
    pytest.param([{"blocks": "kaputt", "pause_minutes": None}] * 5, id="tag-blocks-kein-array"),
    pytest.param("Mo 8-12", id="wurzel-kein-array"),
    pytest.param([{"blocks": [], "pause_minutes": 0}] * 4, id="vier-tage"),
    pytest.param([{"blocks": [{"start": "25:00", "end": "26:00"}], "pause_minutes": 0}]
                 + [{"blocks": [], "pause_minutes": 0}] * 4, id="uhrzeit-ausserhalb"),
    pytest.param([{"blocks": [{"start": "08:00"}], "pause_minutes": 0}]
                 + [{"blocks": [], "pause_minutes": 0}] * 4, id="block-ohne-ende"),
    pytest.param([{"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": "30"}]
                 + [{"blocks": [], "pause_minutes": 0}] * 4, id="pause-als-text"),
]


def _wh_row(db, user, effective_from, blocks):
    row = WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=effective_from,
        weekly_hours=40, use_daily_schedule=False, work_days_per_week=5, blocks=blocks,
    )
    db.add(row)
    db.commit()
    return row


def _warnings(caplog):
    return [r for r in caplog.records
            if r.name == _LOGGER and r.levelno == logging.WARNING and "nicht lesbar" in r.getMessage()]


# ── Resolver ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("broken", BROKEN_FORMS)
def test_resolver_treats_broken_user_blocks_as_none(_db_session, employee_user, broken, caplog):
    employee_user.work_blocks = broken
    _db_session.commit()
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    sched = calculation_service.get_schedule_for_date(_db_session, employee_user, MON)
    assert sched.blocks is None and sched.block_pauses is None
    assert sched.weekly_hours == 40  # das Soll bleibt unberührt
    assert len(_warnings(caplog)) == 1, caplog.text


def test_resolver_treats_broken_history_row_as_none(_db_session, employee_user, caplog):
    row = _wh_row(_db_session, employee_user, MON - timedelta(days=7),
                  [{"blocks": "kaputt", "pause_minutes": 0}] * 5)
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    sched = calculation_service.get_schedule_for_date(_db_session, employee_user, MON, [row])
    assert sched.blocks is None
    assert str(row.id) in caplog.text


def test_resolver_logs_once_per_row(_db_session, employee_user, caplog):
    """Der Preload-Pfad (#449) löst hunderte Tage gegen DIESELBE Zeile auf — der
    Parse-Cache merkt sich auch das Scheitern, sonst flutete ein Jahresbericht
    das Log mit einer Warnung je Tag."""
    row = _wh_row(_db_session, employee_user, MON - timedelta(days=7),
                  [{"blocks": "kaputt", "pause_minutes": 0}] * 5)
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    for i in range(30):
        calculation_service.get_schedule_for_date(_db_session, employee_user, MON + timedelta(days=i), [row])
    assert len(_warnings(caplog)) == 1


def test_legacy_and_valid_blocks_still_resolve(_db_session, employee_user):
    """Gegenprobe: Altfenster (07:37, 23:59) und neue Blöcke bleiben lesbar."""
    employee_user.work_blocks = legacy_week(mon=("07:37", None))
    _db_session.commit()
    sched = calculation_service.get_schedule_for_date(_db_session, employee_user, MON)
    assert sched.blocks[0] == ((7 * 60 + 37, 23 * 60 + 59),)
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    sched = calculation_service.get_schedule_for_date(_db_session, employee_user, MON)
    assert sched.blocks[0] == ((480, 720), (900, 1080))


# ── Flächen ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("broken", BROKEN_FORMS)
def test_my_work_schedule_is_200(_db_session, employee_user, employee_client, broken):
    employee_user.work_blocks = broken
    _db_session.commit()
    resp = employee_client.get("/api/auth/me/work-schedule")
    assert resp.status_code == 200, resp.text
    assert resp.json()["today"]["blocks"] is None


def test_my_work_schedule_history_row_is_200(_db_session, employee_user, employee_client):
    _wh_row(_db_session, employee_user, today_local() - timedelta(days=30), K_BLOCKS)
    _wh_row(_db_session, employee_user, today_local() - timedelta(days=10),
            [{"blocks": "kaputt", "pause_minutes": 0}] * 5)
    resp = employee_client.get("/api/auth/me/work-schedule")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["history"][0]["blocks"] is not None
    assert body["history"][1]["blocks"] is None
    assert body["today"]["blocks"] is None


def test_dashboard_and_team_report_are_200(_db_session, employee_user, employee_client, admin_client):
    """Die Admin-Team-Tabelle rechnet ALLE Personen — eine kaputte Zeile sperrte
    sie für die ganze Praxis."""
    employee_user.work_blocks = [{"blocks": "kaputt", "pause_minutes": 0}] * 5
    _db_session.commit()
    assert employee_client.get("/api/dashboard/").status_code == 200
    month = today_local().strftime("%Y-%m")
    resp = admin_client.get(f"/api/admin/reports/monthly?month={month}")
    assert resp.status_code == 200, resp.text


def test_stamping_works_without_capping(_db_session, employee_user, employee_client, monkeypatch):
    """Ohne lesbare Blöcke gibt es keine Kappung (wie an jedem Tag ohne Blöcke)
    — gestempelt werden kann trotzdem."""
    employee_user.work_blocks = [{"blocks": "kaputt", "pause_minutes": 0}] * 5
    _db_session.commit()

    def at(hh):
        monkeypatch.setattr(te, "_today_local", lambda: MON)
        monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(MON.year, MON.month, MON.day, hh, 0))

    at(6)
    assert employee_client.get("/api/time-entries/clock-status").status_code == 200
    resp = employee_client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text
    at(10)
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 0})
    assert resp.status_code == 200, resp.text
    entry = _db_session.query(TimeEntry).filter(TimeEntry.user_id == employee_user.id).one()
    _db_session.refresh(entry)
    assert entry.start_time == time(6, 0)
    assert (entry.uncredited_minutes or 0) == 0


def test_working_hours_change_list_shows_unreadable_blocks_as_none(_db_session, employee_user, admin_client):
    """Das Leseschema bleibt locker (E29: Altwerte wie gespeichert), gibt aber
    unlesbare Blöcke als ``null`` aus — dieselbe Antwort, mit der die Rechnung
    arbeitet. Der Arbeitszeit-Dialog formatiert jede Verlaufszeile
    (``formatBlocksText``/``blocksKey``: ``day.blocks.map``) und stürzte an einem
    Tag mit ``"blocks": "kaputt"`` ab."""
    legacy = legacy_week(mon=("07:37", "23:59"))
    _wh_row(_db_session, employee_user, MON - timedelta(days=14), legacy)
    _wh_row(_db_session, employee_user, MON - timedelta(days=7),
            [{"blocks": "kaputt", "pause_minutes": 0}] * 5)
    resp = admin_client.get(f"/api/admin/users/{employee_user.id}/working-hours-changes")
    assert resp.status_code == 200, resp.text
    by_date = {r["effective_from"]: r["blocks"] for r in resp.json()}
    assert by_date[(MON - timedelta(days=14)).isoformat()] == legacy
    assert by_date[(MON - timedelta(days=7)).isoformat()] is None


def test_admin_repairs_broken_blocks_with_a_new_change(_db_session, employee_user, admin_client):
    """Der Reparaturweg: eine neue Arbeitszeit-Änderung über einer kaputten
    Zeile — Vorschau und Anlegen rechnen den alten Stand als „keine Blöcke"."""
    employee_user.work_blocks = [{"blocks": "kaputt", "pause_minutes": 0}] * 5
    _db_session.commit()
    body = {"effective_from": today_local().isoformat(), "blocks": K_BLOCKS}
    preview = admin_client.post(
        f"/api/admin/users/{employee_user.id}/working-hours-changes/preview", json=body)
    assert preview.status_code == 200, preview.text
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/working-hours-changes", json=body)
    assert resp.status_code == 201, resp.text
    _db_session.expire_all()
    sched = calculation_service.get_schedule_for_date(_db_session, employee_user, today_local())
    assert sched.blocks is not None
