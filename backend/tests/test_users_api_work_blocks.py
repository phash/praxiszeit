"""Spec 2026-10-08, 11.1/11.4/11.5 (PR1): Benutzer-API und Arbeitszeit-Blöcke.

* Altfelder ``scheduled_*`` → 400 „Bitte Seite neu laden" (E26), erkannt am Präfix.
* ``work_blocks`` per PUT → 400 (E27, genau ein Schreibweg).
* Leseschemas LOCKER (E29): Altwerte wie 07:37 oder der Platzhalter 23:59
  dürfen weder Login noch Benutzerliste in einen HTTP 500 verwandeln.
* ``work_blocks_today`` ist datumsaufgelöst (11.1) — eine zukunftsdatierte
  Verlaufszeile wirkt heute noch nicht, eine ab heute oder früher gültige
  verdrängt ``users.work_blocks``; NULL in der Zeile heißt „keine Blöcke"
  (E8, kein Rückfall). Der Preload in ``attach_work_blocks_today`` ordnet die
  Zeilen je Person zu und filtert nach Mandant (F-026).
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.models import WorkingHoursChange
from app.models.tenant import Tenant
from app.routers.admin_users import LEGACY_WINDOW_FIELDS_DETAIL
from app.services import calculation_service
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_user, endpoints_app, tenant,
)
from tests.work_blocks_fixtures import legacy_week

# 07:37 (kein 5-Minuten-Raster) und der Platzhalter 23:59 aus Migration 073.
ODD = legacy_week(mon=("07:37", "16:30"), fri=("07:30", None))
LATER = legacy_week(mon=("09:00", "17:00"))
ADMIN_OWN = legacy_week(tue=("10:00", "14:00"))
NEW_USER = {
    "username": "neu", "first_name": "Neu", "last_name": "Person", "weekly_hours": 40.0,
    "vacation_days": 30, "work_days_per_week": 5, "password": "NeuPerson2025!",
}


def test_legacy_detail_text_is_the_spec_text():
    assert LEGACY_WINDOW_FIELDS_DETAIL == (
        "Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) "
        "wurden durch Arbeitszeit-Blöcke ersetzt."
    )


def test_put_with_work_blocks_is_400(admin_client, employee_user):
    resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={"work_blocks": ODD})
    assert resp.status_code == 400, resp.text
    assert "Arbeitszeit-Blöcke" in resp.json()["detail"]


def test_put_with_legacy_prefix_is_400_and_changes_nothing(admin_client, employee_user, _db_session):
    resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={
        "first_name": "Neu", "scheduled_start_monday": "08:00"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == LEGACY_WINDOW_FIELDS_DETAIL
    _db_session.refresh(employee_user)
    assert employee_user.first_name == "Max"


def test_post_with_legacy_prefix_is_400(admin_client):
    resp = admin_client.post("/api/admin/users", json={**NEW_USER, "scheduled_end_friday": "15:00"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == LEGACY_WINDOW_FIELDS_DETAIL


def test_post_without_legacy_fields_has_no_window_keys(admin_client):
    resp = admin_client.post("/api/admin/users", json=NEW_USER)
    assert resp.status_code == 201, resp.text
    body = resp.json()["user"]
    assert [k for k in body if k.startswith("scheduled_")] == []
    assert body["work_blocks"] is None
    assert body["work_blocks_today"] is None


def test_list_and_get_resolve_work_blocks_today(admin_client, employee_user, _db_session):
    employee_user.work_blocks = ODD
    _db_session.add(WorkingHoursChange(
        user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=today_local() + timedelta(days=1), weekly_hours=40,
        use_daily_schedule=False, work_days_per_week=5, blocks=LATER,
    ))
    _db_session.commit()
    listed = next(u for u in admin_client.get("/api/admin/users").json()
                  if u["id"] == str(employee_user.id))
    assert listed["work_blocks"] == ODD
    assert listed["work_blocks_today"] == ODD  # die Zeile ab morgen wirkt heute nicht
    single = admin_client.get(f"/api/admin/users/{employee_user.id}")
    assert single.status_code == 200, single.text
    assert single.json()["work_blocks_today"] == ODD


def test_structurally_broken_blocks_do_not_break_the_list(admin_client, employee_user, _db_session):
    employee_user.work_blocks = [{"blocks": "kaputt", "pause_minutes": None}] * 5
    _db_session.commit()
    resp = admin_client.get("/api/admin/users")
    assert resp.status_code == 200, resp.text
    listed = next(u for u in resp.json() if u["id"] == str(employee_user.id))
    assert listed["work_blocks_today"] is None


def test_login_with_legacy_blocks_is_200(_db_session, employee_user):
    employee_user.work_blocks = ODD
    _db_session.commit()

    def _override_db():
        yield _db_session

    endpoints_app.dependency_overrides[get_db] = _override_db
    try:
        with patch("app.routers.auth.set_superadmin_context"):
            with TestClient(endpoints_app) as client:
                resp = client.post("/api/auth/login", json={
                    "username": "employee", "password": "Employee2025!"})
    finally:
        endpoints_app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["work_blocks"] == ODD
    assert resp.json()["user"]["work_blocks_today"] == ODD


def test_impersonation_response_carries_work_blocks_today(admin_client, employee_user, _db_session):
    """Spec 11.1: die Impersonation-Antwort trägt dieselben Felder wie der Login."""
    employee_user.work_blocks = ODD
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/users/{employee_user.id}/impersonate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["work_blocks"] == ODD
    assert resp.json()["user"]["work_blocks_today"] == ODD


def _history_row(user, *, days_from_today, blocks, tenant_id=DEFAULT_TENANT_ID):
    return WorkingHoursChange(
        user_id=user.id, tenant_id=tenant_id,
        effective_from=today_local() + timedelta(days=days_from_today), weekly_hours=40,
        use_daily_schedule=False, work_days_per_week=5, blocks=blocks,
    )


def _listed_and_single(admin_client, user):
    resp = admin_client.get("/api/admin/users")
    assert resp.status_code == 200, resp.text
    listed = next(u for u in resp.json() if u["id"] == str(user.id))
    single = admin_client.get(f"/api/admin/users/{user.id}")
    assert single.status_code == 200, single.text
    return listed, single.json()


@pytest.mark.parametrize("days_from_today", [-3, 0], ids=["gestern-und-frueher", "ab-heute"])
def test_history_row_valid_today_overrides_work_blocks(
    admin_client, employee_user, _db_session, days_from_today,
):
    """Spec 11.1: nach einer Stundenänderung zeigt die Liste die NEU gültigen
    Blöcke (UserForm ``freshEditingUser.work_blocks_today``); ``work_blocks``
    bleibt der Rohwert der User-Zeile."""
    employee_user.work_blocks = ODD
    _db_session.add(_history_row(employee_user, days_from_today=days_from_today, blocks=LATER))
    _db_session.commit()
    for body in _listed_and_single(admin_client, employee_user):
        assert body["work_blocks"] == ODD
        assert body["work_blocks_today"] == LATER


def test_history_row_with_null_blocks_means_no_blocks(admin_client, employee_user, _db_session):
    """E8: NULL in der gültigen Verlaufszeile = keine Blöcke, KEIN Rückfall auf
    ``users.work_blocks``."""
    employee_user.work_blocks = ODD
    _db_session.add(_history_row(employee_user, days_from_today=-3, blocks=None))
    _db_session.commit()
    for body in _listed_and_single(admin_client, employee_user):
        assert body["work_blocks"] == ODD
        assert body["work_blocks_today"] is None


def test_list_preload_assigns_history_rows_per_person(
    admin_client, admin_user, employee_user, _db_session,
):
    """EIN Preload für alle gelisteten Personen — die Zeile der einen darf
    nicht bei der anderen landen (und umgekehrt deren Rückfall nicht fehlen)."""
    employee_user.work_blocks = ODD
    admin_user.work_blocks = ADMIN_OWN
    _db_session.add(_history_row(employee_user, days_from_today=-3, blocks=LATER))
    _db_session.commit()
    resp = admin_client.get("/api/admin/users")
    assert resp.status_code == 200, resp.text
    by_id = {u["id"]: u for u in resp.json()}
    assert by_id[str(employee_user.id)]["work_blocks_today"] == LATER
    assert by_id[str(admin_user.id)]["work_blocks_today"] == ADMIN_OWN


def test_attach_ignores_history_rows_of_foreign_tenant(employee_user, _db_session):
    """F-026: eine Verlaufszeile mit fremder ``tenant_id`` (falsch gesetzt oder
    Superadmin-Kontext ohne RLS) wirkt nicht — es bleibt der Rückfall."""
    foreign = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd-work-blocks")
    _db_session.add(foreign)
    employee_user.work_blocks = ODD
    _db_session.add(_history_row(employee_user, days_from_today=-3, blocks=LATER,
                                 tenant_id=foreign.id))
    _db_session.commit()
    calculation_service.attach_work_blocks_today(_db_session, [employee_user], today_local())
    assert employee_user.work_blocks_today == ODD


def test_put_response_carries_work_blocks_today(admin_client, employee_user, _db_session):
    """Spec 11.1 (Plan „Produces"): auch die Bearbeiten-Antwort trägt
    ``work_blocks_today`` datumsaufgelöst — das UserForm übernimmt sie nach dem
    Speichern. Ohne den Preload in ``update_user`` käme still ``null``."""
    employee_user.work_blocks = ODD
    _db_session.add(_history_row(employee_user, days_from_today=-3, blocks=LATER))
    _db_session.commit()
    resp = admin_client.put(f"/api/admin/users/{employee_user.id}", json={"first_name": "Neu"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["work_blocks"] == ODD
    assert resp.json()["work_blocks_today"] == LATER


# --- PR3 Task 4 (Spec E28, 4.2, 9.8): Startvertrag mit Blöcken beim Anlegen ---

from tests.work_blocks_fixtures import K_BLOCKS, block_week  # noqa: E402

BLOCK_USER = {**NEW_USER, "username": "blockneu", "weekly_hours": 40.0, "work_days_per_week": 5,
              "use_daily_schedule": False, "hours_monday": 9.0}
ANNA = block_week(pause=0, mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                  thu=[("08:00", "12:00")])


def test_post_with_work_blocks_derives_and_overrides(admin_client, _db_session):
    """Spec 4.2: abweichende Clientwerte werden überschrieben, kein 422."""
    resp = admin_client.post("/api/admin/users", json={**BLOCK_USER, "work_blocks": ANNA})
    assert resp.status_code == 201, resp.text
    body = resp.json()["user"]
    assert body["use_daily_schedule"] is True
    assert (body["hours_monday"], body["hours_tuesday"], body["hours_wednesday"]) == (7.0, 4.0, 0.0)
    assert (body["weekly_hours"], body["work_days_per_week"]) == (15.0, 3)
    assert body["work_blocks"] == ANNA
    assert body["work_blocks_today"] == ANNA


def test_post_with_invalid_work_blocks_is_422(admin_client):
    resp = admin_client.post("/api/admin/users",
                             json={**BLOCK_USER, "work_blocks": block_week(mon=[("08:07", "12:00")])})
    assert resp.status_code == 422, resp.text
    assert "5-Minuten-Raster" in resp.text


def test_post_with_work_blocks_and_track_hours_off_is_accepted(admin_client):
    """Spec 11.2/17.2: angenommen, ohne Wirkung, solange keine Stunden gezählt
    werden — aber die Zeile trägt die Blöcke UND die abgeleiteten ``hours_*``
    (K_BLOCKS: Mo 08–12 + 15–18, Pause 0). Eine Ableitung, die bei
    ``track_hours=False`` übersprungen würde, fiele hier auf."""
    resp = admin_client.post("/api/admin/users",
                             json={**BLOCK_USER, "username": "blockleitend", "track_hours": False,
                                   "work_blocks": K_BLOCKS})
    assert resp.status_code == 201, resp.text
    body = resp.json()["user"]
    assert body["work_blocks"] == K_BLOCKS
    assert body["use_daily_schedule"] is True
    assert body["hours_monday"] == 7.0
    assert (body["weekly_hours"], body["work_days_per_week"]) == (7.0, 1)


_NO_DAY_VALUES = {f: None for f in ("hours_monday", "hours_tuesday", "hours_wednesday",
                                    "hours_thursday", "hours_friday")}
_DAY_VALUES_OVER_60 = {**_NO_DAY_VALUES, "hours_monday": 24.0, "hours_tuesday": 24.0,
                       "hours_wednesday": 24.0}


@pytest.mark.parametrize("day_values", [_NO_DAY_VALUES, _DAY_VALUES_OVER_60],
                         ids=["ohne-tageswerte", "tageswerte-ueber-60"])
def test_post_with_work_blocks_derives_before_the_daily_schedule_check(admin_client, day_values):
    """Spec 4.2: ``derive_from_work_blocks`` läuft VOR
    ``check_daily_schedule_matches_weekly_hours``. Genau diese Form schickt das
    Anlegeformular (``use_daily_schedule: true`` neben ``work_blocks``). In
    umgekehrter Reihenfolge prüfte die Quervalidierung die mitgeschickten
    Tageswerte — ohne Werte 422 „Im Tagesplan-Modus …", mit 24/24/24 422
    „Die Summe der Tagesstunden …" — statt sie zu überschreiben."""
    resp = admin_client.post("/api/admin/users", json={
        **BLOCK_USER, "username": "blocktagesplan", "use_daily_schedule": True,
        **day_values, "work_blocks": ANNA,
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()["user"]
    assert body["use_daily_schedule"] is True
    assert (body["hours_monday"], body["hours_tuesday"], body["hours_wednesday"]) == (7.0, 4.0, 0.0)
    assert (body["weekly_hours"], body["work_days_per_week"]) == (15.0, 3)


# --- Review Task 4, Fund 2 (Spec 3.4/11.4): Blockfehler beim Anlegen als deutscher Klartext ---
# Spec 3.4 gilt für BEIDE Schreibschemas: „422, deutsch, über _schedule_input_error
# mit Feld-Label". Ohne eigene Prüfung käme FastAPIs Standard-422 zurück — Regeltext
# mit Präfix „Value error, ", Typfehler englisch („Input should be a valid string").


def test_post_block_rule_violation_is_a_plain_german_detail(admin_client):
    resp = admin_client.post("/api/admin/users",
                             json={**BLOCK_USER, "work_blocks": block_week(mon=[("08:07", "12:00")])})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."


def test_post_block_type_error_names_weekday_block_and_field(admin_client):
    week = block_week(tue=[("08:00", "12:00"), ("13:00", "16:00")])
    week[1]["blocks"][1]["end"] = 1600
    resp = admin_client.post("/api/admin/users", json={**BLOCK_USER, "work_blocks": week})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Di, Block 2, Ende: ungültiger Wert."


def _six_days_sixth_broken():
    week = block_week(mon=[("08:00", "12:00")])
    week.append({"blocks": [{"start": 1, "end": "12:00"}], "pause_minutes": 0})
    return week


@pytest.mark.parametrize("work_blocks", ["x", {"mo": []}, _six_days_sixth_broken()],
                         ids=["text", "objekt", "sechster-tag-typfehler"])
def test_post_wrong_week_shape_gets_the_five_days_text(admin_client, work_blocks):
    """Review Task 4: ``work_blocks`` als String/Objekt (``list_type`` an der Wurzel)
    oder ein Typfehler am sechsten Tag fängt Pydantic vor ``validate_week_blocks`` ab.
    Ohne eigenen Zweig kam FastAPIs englische Standard-422 („Input should be a valid
    list") — Spec 3.4 sieht für „genau 5 Einträge" den deutschen Text vor."""
    resp = admin_client.post("/api/admin/users", json={**BLOCK_USER, "work_blocks": work_blocks})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet."


def test_post_labelled_field_and_other_rule_texts_are_german_too(admin_client):
    """Dieselbe Übersetzung greift für die Feld-Labels aus ``_schedule_input_error``
    und für die übrigen ``UserCreate``-Regeltexte (ohne „Value error, ")."""
    resp = admin_client.post("/api/admin/users", json={**NEW_USER, "username": "zuviel", "weekly_hours": 70})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Die Wochenstunden dürfen höchstens 60 betragen."
    resp = admin_client.post("/api/admin/users",
                             json={**NEW_USER, "username": "schwach", "password": "nurkleinbuchstaben1"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Passwort muss mindestens einen Grossbuchstaben enthalten"


def test_post_error_without_german_text_keeps_the_standard_422(admin_client):
    """Ohne deutschen Text (kein Regeltext, kein Feld-Label) bleibt es bei der
    Standard-422 mit ``loc`` — ein pauschales „Ungültige Eingabe." verlöre die
    Angabe, welches Feld fehlt."""
    body = {k: v for k, v in NEW_USER.items() if k != "first_name"}
    resp = admin_client.post("/api/admin/users", json={**body, "username": "ohnevorname"})
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert (detail[0]["type"], detail[0]["loc"]) == ("missing", ["body", "first_name"])
