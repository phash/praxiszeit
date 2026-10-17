"""Gesamtreview 1.20: Feiertags- und Sondertagsänderungen nennen die
Zeiteinträge, deren Kappung danach nicht mehr stimmt.

Ob ein Tag gegen die Arbeitszeit-Blöcke gekappt wird, entscheidet sich beim
Schreiben des Eintrags (E35/#484: Feiertag und „freier" Sondertag → keine
Kappung). Ändert die Verwaltung danach, ob ein Tag soll-frei ist — eigener
Feiertag angelegt/verschoben/gelöscht, Bundesland gewechselt, 24./31.12.
zwischen „frei" und Arbeitstag umgestellt —, bleibt die gespeicherte Kappung
stehen. Eine automatische Neukappung wäre eine rückwirkende Änderung der
angerechneten Zeit ohne Vorschau (Verkürzung nur mit Grund, Spec 9.5); die
Endpunkte melden deshalb die betroffenen Einträge in ``warning``, neu
berechnet wird ein Eintrag beim unveränderten Speichern durch die Verwaltung
(``test_work_window_integration.py::test_alter_gekappter_feiertagseintrag_…``).
"""

import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import TimeEntry, User, UserRole
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.services import auth_service, holiday_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.work_blocks_fixtures import block_week


def _app():
    from app.routers import admin_settings, holidays

    app = FastAPI()
    app.include_router(holidays.router)
    app.include_router(admin_settings.router)
    return app


@pytest.fixture
def client(db, test_admin):
    app = _app()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: test_admin
    app.dependency_overrides[require_admin] = lambda: test_admin
    holiday_service.invalidate_holiday_cache()
    with TestClient(app) as c:
        yield c
    holiday_service.invalidate_holiday_cache()


@pytest.fixture
def mitarbeiterin(db, default_tenant):
    # Blöcke Mo–Fr 08:00–12:00 und 15:00–18:00, Puffer 15 (Default).
    tag = [("08:00", "12:00"), ("15:00", "18:00")]
    u = User(
        username="ma_sollfrei", email="ma_sollfrei@example.com",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Mia", last_name="Muster", role=UserRole.EMPLOYEE,
        weekly_hours=35.0, vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
        work_blocks=block_week(mon=tag, tue=tag, wed=tag, thu=tag, fri=tag),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _gekappt(db, user, d, **kw):
    """Eintrag 07:30–13:00, gestempelt an einem normalen Arbeitstag:
    angerechnet 08:00–12:15 (Hülle), Rohstempel erhalten."""
    e = TimeEntry(
        user_id=user.id, tenant_id=user.tenant_id, date=d,
        start_time=dt.time(8, 0), end_time=dt.time(12, 15),
        raw_start_time=dt.time(7, 30), raw_end_time=dt.time(13, 0),
        break_minutes=0, uncredited_minutes=0, clamp_grace_minutes=15, **kw,
    )
    db.add(e)
    db.commit()
    return e


def _ungekappt(db, user, d):
    """Eintrag 07:00–18:00 an einem Feiertag (keine Kappung, E35)."""
    e = TimeEntry(
        user_id=user.id, tenant_id=user.tenant_id, date=d,
        start_time=dt.time(7, 0), end_time=dt.time(18, 0),
        break_minutes=60, uncredited_minutes=0,
    )
    db.add(e)
    db.commit()
    return e


def _hint(resp):
    return (resp.json() or {}).get("warning") or ""


# ── Eigene Feiertage ─────────────────────────────────────────────────────────

def test_feiertag_anlegen_nennt_den_gekappten_eintrag(db, client, mitarbeiterin):
    _gekappt(db, mitarbeiterin, dt.date(2026, 8, 14))
    resp = client.post("/api/holidays/", json={"name": "Schützenfest", "date": "2026-08-14"})
    assert resp.status_code == 201, resp.text
    text = _hint(resp)
    assert "1 Eintrag: 14.08.2026" in text, text
    assert "unverändert speichern" in text


def test_feiertag_anlegen_ohne_eintraege_bleibt_still(db, client, mitarbeiterin):
    resp = client.post("/api/holidays/", json={"name": "Schützenfest", "date": "2026-08-14"})
    assert resp.status_code == 201, resp.text
    assert resp.json().get("warning") is None


def test_eintrag_innerhalb_der_bloecke_zaehlt_nicht(db, client, mitarbeiterin):
    """08:30–11:30 liegt im Block — mit und ohne Feiertag dieselbe Anrechnung."""
    db.add(TimeEntry(user_id=mitarbeiterin.id, tenant_id=DEFAULT_TENANT_ID,
                     date=dt.date(2026, 8, 14), start_time=dt.time(8, 30),
                     end_time=dt.time(11, 30), break_minutes=0))
    db.commit()
    resp = client.post("/api/holidays/", json={"name": "Schützenfest", "date": "2026-08-14"})
    assert resp.status_code == 201, resp.text
    assert resp.json().get("warning") is None


def test_anerkannt_offen_und_ohne_stundenzaehlung_zaehlen_nicht(db, client, mitarbeiterin, default_tenant):
    _gekappt(db, mitarbeiterin, dt.date(2026, 8, 14), credit_override=True)
    db.add(TimeEntry(user_id=mitarbeiterin.id, tenant_id=DEFAULT_TENANT_ID,
                     date=dt.date(2026, 8, 14), start_time=dt.time(14, 0), end_time=None,
                     break_minutes=0))
    ohne = User(
        username="ma_ohne", email="ma_ohne@example.com",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Otto", last_name="Ohne", role=UserRole.EMPLOYEE,
        weekly_hours=35.0, vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID, track_hours=False,
        work_blocks=mitarbeiterin.work_blocks,
    )
    db.add(ohne)
    db.commit()
    _gekappt(db, ohne, dt.date(2026, 8, 14))
    resp = client.post("/api/holidays/", json={"name": "Schützenfest", "date": "2026-08-14"})
    assert resp.status_code == 201, resp.text
    assert resp.json().get("warning") is None


def test_feiertag_loeschen_nennt_den_ungekappten_eintrag(db, client, mitarbeiterin):
    h = PublicHoliday(date=dt.date(2026, 8, 14), name="Schützenfest", year=2026,
                      tenant_id=DEFAULT_TENANT_ID, is_custom=True, source="admin")
    db.add(h)
    db.commit()
    _ungekappt(db, mitarbeiterin, dt.date(2026, 8, 14))
    resp = client.delete(f"/api/holidays/{h.id}")
    assert resp.status_code == 200, resp.text
    assert "1 Eintrag: 14.08.2026" in _hint(resp)


def test_feiertag_verschieben_prueft_altes_und_neues_datum(db, client, mitarbeiterin):
    h = PublicHoliday(date=dt.date(2026, 8, 14), name="Schützenfest", year=2026,
                      tenant_id=DEFAULT_TENANT_ID, is_custom=True, source="admin")
    db.add(h)
    db.commit()
    _ungekappt(db, mitarbeiterin, dt.date(2026, 8, 14))
    _gekappt(db, mitarbeiterin, dt.date(2026, 8, 21))
    resp = client.put(f"/api/holidays/{h.id}", json={"date": "2026-08-21"})
    assert resp.status_code == 200, resp.text
    assert "2 Einträge: 14.08.2026, 21.08.2026" in _hint(resp)


def test_fremder_mandant_zaehlt_nicht(db, client, mitarbeiterin):
    """F-026: Einträge eines anderen Mandanten am selben Datum bleiben außen vor."""
    import uuid
    from app.models.tenant import Tenant
    other_tid = uuid.UUID("cccccccc-1200-4000-8000-000000000120")
    db.add(Tenant(id=other_tid, name="Fremd", slug="fremd-gr", is_active=True, mode="multi"))
    fremd = User(
        username="ma_fremd", email="ma_fremd@example.com",
        password_hash=auth_service.hash_password("Test2025!Password"),
        first_name="Fritz", last_name="Fremd", role=UserRole.EMPLOYEE,
        weekly_hours=35.0, vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=other_tid, work_blocks=mitarbeiterin.work_blocks,
    )
    db.add(fremd)
    db.commit()
    _gekappt(db, fremd, dt.date(2026, 8, 14))
    resp = client.post("/api/holidays/", json={"name": "Schützenfest", "date": "2026-08-14"})
    assert resp.status_code == 201, resp.text
    assert resp.json().get("warning") is None


# ── Bundesland ───────────────────────────────────────────────────────────────

def test_bundesland_wechsel_nennt_den_eintrag_am_weggefallenen_feiertag(db, client, mitarbeiterin):
    """BY → BE: Heilige Drei Könige (Di 06.01.2026) wird Arbeitstag."""
    db.add(SystemSetting(key="holiday_state", value="Bayern", description="holiday_state",
                         tenant_id=DEFAULT_TENANT_ID))
    holiday_service.sync_holidays(db, 2026, "Bayern", tenant_id=DEFAULT_TENANT_ID)
    db.commit()
    _ungekappt(db, mitarbeiterin, dt.date(2026, 1, 6))
    resp = client.put("/api/admin/settings/holiday_state", json={"value": "Berlin"})
    assert resp.status_code == 200, resp.text
    assert "1 Eintrag: 06.01.2026" in _hint(resp)


# ── Sondertage ───────────────────────────────────────────────────────────────

def test_sondertag_auf_frei_nennt_den_gekappten_eintrag(db, client, mitarbeiterin):
    _gekappt(db, mitarbeiterin, dt.date(2025, 12, 24))
    resp = client.put("/api/admin/settings/special_day_dec24_mode", json={"value": "free"})
    assert resp.status_code == 200, resp.text
    assert "1 Eintrag: 24.12.2025" in _hint(resp)


def test_sondertag_halbtag_behaelt_die_bloecke_und_bleibt_still(db, client, mitarbeiterin):
    _gekappt(db, mitarbeiterin, dt.date(2025, 12, 24))
    resp = client.put("/api/admin/settings/special_day_dec24_mode", json={"value": "half_day"})
    assert resp.status_code == 200, resp.text
    assert "warning" not in resp.json()
