"""Spec 2026-10-08, 15.3 / E72 (PR2): Auskunfts- und §16-Notfallexporte führen
Blöcke, Verlauf und die neuen Eintrags-/Antragsfelder — nur str/int/bool/None."""
import json
from datetime import date, time

from app.models import ChangeRequest, TimeEntry, WorkingHoursChange
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.routers import superadmin
from app.services import lifecycle_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, legacy_week

LEGACY = legacy_week(mon=("07:37", None))   # Altwert + Platzhalter 23:59
ENTRY_FIELDS = {"uncredited_minutes": 150, "credit_override": False, "auto_closed": False,
                "clamp_grace_minutes": 15}


def _seed(db, user):
    user.work_blocks = LEGACY
    db.add(WorkingHoursChange(user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
                              effective_from=date(2026, 9, 1), weekly_hours=40.0,
                              use_daily_schedule=False, work_days_per_week=5, blocks=K_BLOCKS,
                              note="Grund"))
    te = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                   start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                   raw_end_time=time(19), break_minutes=0, uncredited_minutes=150,
                   clamp_grace_minutes=15)
    db.add(te)
    db.commit()
    db.add(ChangeRequest(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
                         request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                         time_entry_id=te.id, proposed_date=MON, proposed_start_time=time(7),
                         proposed_end_time=time(19), proposed_break_minutes=0,
                         reason="Durchgearbeitet", request_credit_override=True,
                         original_uncredited_minutes=150))
    db.commit()
    return te


def _pick(d):
    return {k: d[k] for k in ENTRY_FIELDS}


def test_art15_self_export(_db_session, employee_user):
    _seed(_db_session, employee_user)
    payload = lifecycle_service.build_self_export_payload(_db_session, employee_user)
    json.dumps(payload)   # #383/#408: nur JSON-fähige Werte
    assert payload["subject"]["work_blocks"] == LEGACY
    assert payload["subject"]["working_hours_changes"][0]["blocks"] == K_BLOCKS
    assert _pick(payload["time_entries"][0]) == ENTRY_FIELDS
    cr = payload["change_requests"][0]
    assert (cr["request_credit_override"], cr["original_uncredited_minutes"]) == (True, 150)


def test_art15_categories_and_logic():
    meta = lifecycle_service._build_art15_meta()
    assert "Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause, Verlauf)" in meta["b_datenkategorien"]
    assert "nicht angerechnete Zeit und Anerkennungen" in meta["b_datenkategorien"]
    assert "zwischen den Blöcken" in meta["h_automatisierte_entscheidung"]


def test_art20_me_export(_db_session, employee_user, employee_client):
    _seed(_db_session, employee_user)
    r = employee_client.get("/api/auth/me/export")
    assert r.status_code == 200, r.text
    data = json.loads(r.content)
    assert data["stammdaten"]["work_blocks"] == LEGACY
    assert data["stundenhistorie"][0]["blocks"] == K_BLOCKS
    assert _pick(data["zeiteintraege"][0]) == ENTRY_FIELDS


def test_superadmin_emergency_export_dicts(_db_session, employee_user):
    te = _seed(_db_session, employee_user)
    history = _db_session.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == employee_user.id).all()
    user = superadmin._user_dict(employee_user, history)
    entry = superadmin._time_entry_dict(te)
    json.dumps(user)
    json.dumps(entry)
    assert user["work_blocks"] == LEGACY
    assert user["working_hours_changes"][0]["blocks"] == K_BLOCKS
    assert _pick(entry) == ENTRY_FIELDS
