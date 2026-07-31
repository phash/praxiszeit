"""#431: die Stundenhistorie (``working_hours_changes``) ist ein vollstaendiger
Vertrags-Snapshot (Wochenstunden, Tagesplan-Modus, Tageswerte) und damit
vertragsrelevantes, personenbezogenes Datum — sie gehoert in den Art.-15-
Export (``lifecycle_service``) und den Art.-20-Selbstexport
(``/api/auth/me/export``).

Beide Exportflaechen serialisieren ueber ROHES ``json.dumps``/``JSONResponse``,
nicht ueber FastAPIs ``jsonable_encoder``. ``weekly_hours``/``hours_monday``
usw. sind ``Numeric(4,2)`` -> SQLAlchemy liefert beim Lesen ``Decimal``, das
``json.dumps`` nicht serialisieren kann -> HTTP 500 fuer JEDEN Nutzer. Genau
diese Fehlerklasse hat das Projekt schon zweimal getroffen (#383/#408) -
jeder Test hier prueft deshalb die tatsaechliche JSON-Serialisierbarkeit,
nicht nur die Anwesenheit der Felder.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import WorkingHoursChange
from app.models.tenant import Tenant
from app.services import lifecycle_service
from tests.conftest import DEFAULT_TENANT_ID


def _add_change(db, user, **overrides):
    defaults = dict(
        user_id=user.id,
        tenant_id=user.tenant_id,
        effective_from=date(2026, 3, 1),
        weekly_hours=17.0,
        use_daily_schedule=True,
        hours_monday=8.0,
        hours_tuesday=5.0,
        hours_wednesday=4.0,
        work_days_per_week=3,
        note="Reduzierung wegen Elternzeit",
    )
    defaults.update(overrides)
    change = WorkingHoursChange(**defaults)
    db.add(change)
    db.commit()
    db.refresh(change)
    return change


# ───────────────── lifecycle_service._user_dict (Art. 15 Grundbaustein) ──

def test_export_contains_schedule_history_and_is_json_safe(db, test_user):
    """Brief-Step-1: die Stundenhistorie erscheint im Export UND json.dumps
    darf dabei nicht werfen (Decimal-Leak #383/#408)."""
    _add_change(db, test_user)

    data = lifecycle_service._user_dict(db, test_user)
    dumped = json.dumps(data)  # darf NICHT werfen

    assert "working_hours_changes" in data
    assert data["working_hours_changes"][0]["hours_monday"] == 8.0
    assert isinstance(data["working_hours_changes"][0]["hours_monday"], float)
    assert "8.0" in dumped or "8" in dumped


def test_user_dict_history_is_chronological(db, test_user):
    """Wie die anderen Sammlungen im Export (time_entries/absences/...):
    aufsteigend sortiert, nicht Insert-Reihenfolge."""
    _add_change(db, test_user, effective_from=date(2026, 6, 1), note="später")
    _add_change(db, test_user, effective_from=date(2026, 1, 1), note="früher")

    data = lifecycle_service._user_dict(db, test_user)
    dates = [h["effective_from"] for h in data["working_hours_changes"]]
    assert dates == sorted(dates)
    assert data["working_hours_changes"][0]["note"] == "früher"


def test_user_dict_history_empty_list_when_none(db, test_user):
    """Kein Vertragswechsel -> leere Liste, kein KeyError/None."""
    data = lifecycle_service._user_dict(db, test_user)
    assert data["working_hours_changes"] == []


def test_user_dict_history_excludes_other_users_rows(db, test_user, test_admin):
    """F-026 (belt-and-suspenders): die History eines ANDEREN Users im selben
    Tenant darf nicht im Export des angefragten Users auftauchen."""
    _add_change(db, test_admin, note="gehört dem Admin")
    own = _add_change(db, test_user, note="gehört test_user")

    data = lifecycle_service._user_dict(db, test_user)
    notes = [h["note"] for h in data["working_hours_changes"]]
    assert notes == ["gehört test_user"]
    assert str(own.id) == data["working_hours_changes"][0]["id"]


def test_user_dict_history_all_numeric_fields_are_float_or_none(db, test_user):
    """Jedes Numeric(4,2)-Feld einzeln pruefen — nicht nur eines, wie im
    Brief-Beispiel. Verhindert eine halbe Migration (#383 traf genau das)."""
    _add_change(
        db, test_user,
        weekly_hours=21.5, use_daily_schedule=True,
        hours_monday=8.25, hours_tuesday=5.5, hours_wednesday=4.0,
        hours_thursday=3.75, hours_friday=0.0, work_days_per_week=5,
    )
    data = lifecycle_service._user_dict(db, test_user)
    row = data["working_hours_changes"][0]
    for field in (
        "weekly_hours", "hours_monday", "hours_tuesday",
        "hours_wednesday", "hours_thursday", "hours_friday",
    ):
        assert isinstance(row[field], float), f"{field} ist {type(row[field])}, nicht float"
    json.dumps(data)  # darf NICHT werfen


# ───────────────── Ganzer Payload (Tenant-Export + Self-Service-Export) ──

def test_tenant_export_payload_json_safe_with_daily_schedule(db, day_plan_user):
    """build_tenant_export_payload (/api/tenant/export): voller Payload,
    inkl. Tagesplan-Modus (alle 5 Tageswerte gesetzt), muss json.dumps
    überstehen."""
    tenant = db.query(Tenant).filter(Tenant.id == DEFAULT_TENANT_ID).first()
    _add_change(
        db, day_plan_user,
        weekly_hours=17.0, use_daily_schedule=True,
        hours_monday=8.0, hours_tuesday=5.0, hours_wednesday=4.0,
        hours_thursday=0.0, hours_friday=0.0, work_days_per_week=3,
    )

    payload = lifecycle_service.build_tenant_export_payload(db, tenant, requester=day_plan_user)
    dumped = json.dumps(payload)  # darf NICHT werfen

    user_entry = next(u for u in payload["users"] if u["id"] == str(day_plan_user.id))
    assert user_entry["working_hours_changes"][0]["hours_wednesday"] == 4.0
    assert '"hours_wednesday": 4.0' in dumped or "4.0" in dumped


def test_self_export_payload_contains_history(db, test_user):
    """build_self_export_payload (/api/me/data-export, Art. 15): die History
    liegt unter subject.working_hours_changes."""
    _add_change(db, test_user, weekly_hours=17.75)

    payload = lifecycle_service.build_self_export_payload(db, test_user)
    json.dumps(payload)  # darf NICHT werfen

    assert payload["subject"]["working_hours_changes"][0]["weekly_hours"] == 17.75


# ───────────────── auth.py /api/auth/me/export (Art. 20) ─────────────────

def _export_client(db, user):
    # Der gemeinsame _app inkludiert den auth-Router (mit /me/export) nicht;
    # eigene Mini-App nur mit dem auth-Router (Muster aus test_break_waiver.py
    # TestDataExportRawStamp._export_client). /me/export ist nicht rate-
    # limited -> kein slowapi-State nötig.
    from app.routers import auth as auth_router
    app = FastAPI()
    app.include_router(auth_router.router)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_auth_me_export_contains_stundenhistorie_and_is_json_safe(db, test_user):
    _add_change(db, test_user)

    resp = _export_client(db, test_user).get("/api/auth/me/export")
    assert resp.status_code == 200, resp.text  # Decimal-Leak-Klasse #383/#408 wäre hier ein 500

    data = resp.json()
    assert "stundenhistorie" in data
    assert data["stundenhistorie"][0]["hours_monday"] == 8.0
    assert data["stundenhistorie"][0]["effective_from"] == "2026-03-01"
    assert data["stundenhistorie"][0]["note"] == "Reduzierung wegen Elternzeit"


def test_auth_me_export_stundenhistorie_empty_when_no_history(db, test_user):
    resp = _export_client(db, test_user).get("/api/auth/me/export")
    assert resp.status_code == 200, resp.text
    assert resp.json()["stundenhistorie"] == []


def test_auth_me_export_excludes_other_users_history(db, test_user, test_admin):
    """F-026: ein fremder User im selben Tenant darf nicht mit im Export
    des angefragten Users auftauchen."""
    _add_change(db, test_admin, note="Admin-Historie")
    _add_change(db, test_user, note="eigene Historie")

    resp = _export_client(db, test_user).get("/api/auth/me/export")
    assert resp.status_code == 200, resp.text
    notes = [h["note"] for h in resp.json()["stundenhistorie"]]
    assert notes == ["eigene Historie"]
