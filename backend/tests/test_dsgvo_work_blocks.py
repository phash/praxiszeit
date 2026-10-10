"""Spec 2026-10-08, 15.3 / E72 (PR2): Auskunfts- und §16-Notfallexporte führen
Blöcke, Verlauf und die neuen Eintrags-/Antragsfelder — nur str/int/bool/None."""
import json
from datetime import date, time, timedelta

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
TUE, WED = MON + timedelta(days=1), MON + timedelta(days=2)
# Je Eintrag (nach Datum) die vier Felder. Die Fälle unterscheiden sich so, dass
# ein fest verdrahteter Wert, vertauschte Felder oder ein Ersatzwert für
# clamp_grace_minutes in jedem der drei Exporte auffallen:
# - MON: Lückenanteil nicht angerechnet (Regelfall der Blöcke);
# - TUE: automatisch geschlossen — P18: ohne auto_closed läse sich raw_end 23:59
#   als echter Stempel; nie gegen Blöcke gekappt → clamp_grace_minutes null
#   (E79; Spec 17.6 „int bzw. null");
# - WED: von der Verwaltung anerkannt.
ENTRY_FIELDS = {
    MON.isoformat(): {"uncredited_minutes": 150, "credit_override": False,
                      "auto_closed": False, "clamp_grace_minutes": 15},
    TUE.isoformat(): {"uncredited_minutes": 0, "credit_override": False,
                      "auto_closed": True, "clamp_grace_minutes": None},
    WED.isoformat(): {"uncredited_minutes": 0, "credit_override": True,
                      "auto_closed": False, "clamp_grace_minutes": 15},
}
# Je Antrag (nach vorgeschlagenem Datum) Anrechnungswunsch und Vorher-Snapshot.
# Zwei unterscheidbare Fälle, damit ein fest verdrahteter Wert auffällt:
# - MON: „Anrechnung beantragen" mit Snapshot der nicht angerechneten Minuten;
# - TUE: gewöhnlicher Änderungsantrag — kein Wunsch, kein Snapshot (False/null).
CR_FIELDS = {
    MON.isoformat(): (True, 150),
    TUE.isoformat(): (False, None),
}
# Verlauf: frühere Zeile ohne Blöcke (NULL), spätere mit K_BLOCKS. NULL bleibt
# NULL — nie Rückfall auf users.work_blocks (LEGACY) und nie [].
EARLY_FROM, LATE_FROM = date(2026, 3, 1), date(2026, 9, 1)
HISTORY_BLOCKS = {EARLY_FROM.isoformat(): None, LATE_FROM.isoformat(): K_BLOCKS}


def _seed(db, user):
    user.work_blocks = LEGACY
    db.add(WorkingHoursChange(user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
                              effective_from=LATE_FROM, weekly_hours=40.0,
                              use_daily_schedule=False, work_days_per_week=5, blocks=K_BLOCKS,
                              note="Grund"))
    db.add(WorkingHoursChange(user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
                              effective_from=EARLY_FROM, weekly_hours=40.0,
                              use_daily_schedule=False, work_days_per_week=5, blocks=None))
    te = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                   start_time=time(7, 45), end_time=time(18, 15), raw_start_time=time(7),
                   raw_end_time=time(19), break_minutes=0, uncredited_minutes=150,
                   clamp_grace_minutes=15)
    db.add(te)
    te_tue = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=TUE,
                       start_time=time(8), end_time=time(23, 59), raw_start_time=time(8),
                       raw_end_time=time(23, 59), break_minutes=0, uncredited_minutes=0,
                       credit_override=False, auto_closed=True, clamp_grace_minutes=None)
    db.add(te_tue)
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=WED,
                     start_time=time(7), end_time=time(19), raw_start_time=time(7),
                     raw_end_time=time(19), break_minutes=0, uncredited_minutes=0,
                     credit_override=True, auto_closed=False, clamp_grace_minutes=15))
    db.commit()
    db.add(ChangeRequest(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
                         request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                         time_entry_id=te.id, proposed_date=MON, proposed_start_time=time(7),
                         proposed_end_time=time(19), proposed_break_minutes=0,
                         reason="Durchgearbeitet", request_credit_override=True,
                         original_uncredited_minutes=150))
    db.add(ChangeRequest(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
                         request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                         time_entry_id=te_tue.id, proposed_date=TUE, proposed_start_time=time(8),
                         proposed_end_time=time(17, 30), proposed_break_minutes=0,
                         reason="Ende nachgetragen", request_credit_override=False,
                         original_uncredited_minutes=None))
    db.commit()
    return te


def _by_date(entries):
    """Die vier Felder je Eintrag, nach Datum — nicht nach Position."""
    fields = next(iter(ENTRY_FIELDS.values()))
    return {e["date"]: {k: e[k] for k in fields} for e in entries}


def _blocks_by_from(history):
    return {h["effective_from"]: h["blocks"] for h in history}


def test_art15_self_export(_db_session, employee_user):
    _seed(_db_session, employee_user)
    payload = lifecycle_service.build_self_export_payload(_db_session, employee_user)
    json.dumps(payload)   # #383/#408: nur JSON-fähige Werte
    assert payload["subject"]["work_blocks"] == LEGACY
    assert _blocks_by_from(payload["subject"]["working_hours_changes"]) == HISTORY_BLOCKS
    assert _by_date(payload["time_entries"]) == ENTRY_FIELDS
    assert {c["proposed_date"]: (c["request_credit_override"], c["original_uncredited_minutes"])
            for c in payload["change_requests"]} == CR_FIELDS


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
    assert _blocks_by_from(data["stundenhistorie"]) == HISTORY_BLOCKS
    assert _by_date(data["zeiteintraege"]) == ENTRY_FIELDS


def test_superadmin_emergency_export_dicts(_db_session, employee_user):
    _seed(_db_session, employee_user)
    # Wie export_tenant_data: Verlauf nach effective_from sortiert.
    history = _db_session.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == employee_user.id).order_by(
        WorkingHoursChange.effective_from).all()
    entries = _db_session.query(TimeEntry).filter(
        TimeEntry.user_id == employee_user.id).all()
    user = superadmin._user_dict(employee_user, history)
    entry_dicts = [superadmin._time_entry_dict(te) for te in entries]
    json.dumps(user)
    json.dumps(entry_dicts)
    assert user["work_blocks"] == LEGACY
    assert _blocks_by_from(user["working_hours_changes"]) == HISTORY_BLOCKS
    assert _by_date(entry_dicts) == ENTRY_FIELDS
