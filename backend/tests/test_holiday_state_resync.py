"""Bundesland-Wechsel erzeugt die gesetzlichen Feiertage ALLER Jahre neu.

Gesamtreview 1.20 (B9): ``PUT /api/admin/settings/holiday_state`` löschte die
gesetzlichen Feiertage (``source='workalendar'``) des Mandanten über ALLE Jahre,
``sync_current_and_next_year`` legte aber nur das laufende und das nächste Jahr
neu an. Frühere Jahre standen danach ohne Feiertage da — jeder Feiertag wurde
zum Arbeitstag, Soll, Saldo, Überstundenkonto und §16-Exporte dieser Jahre
änderten sich still, auch für abgeschlossene Jahre und ohne Hinweis. Jeder
E2E-Lauf (settings.spec.ts schaltet Bayern ↔ Berlin) leerte so auf der
Zielinstanz alle Jahre vor dem laufenden.

Handbuch und Einstellungsseite versprechen „alle gesetzlichen Feiertage werden
automatisch neu berechnet" — jetzt stimmt das: jedes Jahr, für das der Mandant
gesetzliche Feiertage hatte, wird für das neue Bundesland neu erzeugt (dazu wie
bisher das laufende und das nächste Jahr). Eigene Feiertage (#143) bleiben.
Ändern sich dabei Feiertage eines bereits abgeschlossenen Jahres, trägt die
Antwort ``warning`` (Fix #5, wie Storno/Betriebsferien) — der Übertrag wird nie
automatisch neu berechnet.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.services.timezone_service import today_local
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models.public_holiday import PublicHoliday
from app.models.year_carryover import YearCarryover
from app.services import holiday_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

URL = "/api/admin/settings/holiday_state"
OTHER_TENANT_ID = uuid.UUID("b9b9b9b9-0000-4000-8000-00000000f1a7")


@pytest.fixture(autouse=True)
def _clear_holiday_cache():
    holiday_service.invalidate_holiday_cache()
    yield
    holiday_service.invalidate_holiday_cache()


@pytest.fixture
def admin_client(db, test_admin):
    def _override_db():
        yield db

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def _past_year() -> int:
    return today_local().year - 1


def _seed_bavaria(db, *years, tenant_id=DEFAULT_TENANT_ID):
    """Wie der Betrieb: jedes Jahr wurde einmal als laufendes Jahr synchronisiert."""
    current = today_local().year
    for y in sorted(set(years) | {current, current + 1}):
        holiday_service.sync_holidays(db, y, "Bayern", tenant_id=tenant_id)
    db.commit()


def _dates(db, year, tenant_id=DEFAULT_TENANT_ID, source=None):
    q = db.query(PublicHoliday.date).filter(
        PublicHoliday.tenant_id == tenant_id, PublicHoliday.year == year,
    )
    if source is not None:
        q = q.filter(PublicHoliday.source == source)
    return {d for (d,) in q.all()}


def _expected(state, year):
    return set(holiday_service._german_holidays(state, year).keys())


def test_state_change_regenerates_earlier_year(db, admin_client):
    past = _past_year()
    _seed_bavaria(db, past)
    assert _dates(db, past) == _expected("Bayern", past)

    resp = admin_client.put(URL, json={"value": "Berlin"})
    assert resp.status_code == 200, resp.text

    db.expire_all()
    assert _dates(db, past) == _expected("Berlin", past)
    assert date(past, 3, 8) in _dates(db, past)       # Frauentag (Berlin)
    assert date(past, 1, 6) not in _dates(db, past)   # Heilige Drei Könige (Bayern)
    current = today_local().year
    assert _dates(db, current) == _expected("Berlin", current)
    assert _dates(db, current + 1) == _expected("Berlin", current + 1)


def test_round_trip_restores_earlier_year(db, admin_client):
    """Genau der E2E-Ablauf: umschalten und wieder zurück — die Feiertagstabelle
    steht danach wie vorher, nicht nur der Einstellungswert."""
    past = _past_year()
    _seed_bavaria(db, past - 1, past)
    before = {y: _dates(db, y) for y in (past - 1, past)}

    assert admin_client.put(URL, json={"value": "Berlin"}).status_code == 200
    assert admin_client.put(URL, json={"value": "Bayern"}).status_code == 200

    db.expire_all()
    assert {y: _dates(db, y) for y in (past - 1, past)} == before


def test_custom_holiday_in_earlier_year_survives(db, admin_client):
    past = _past_year()
    _seed_bavaria(db, past)
    db.add(PublicHoliday(
        date=date(past, 7, 6), name="Schützenfest", year=past,
        tenant_id=DEFAULT_TENANT_ID, is_custom=True, source="admin",
    ))
    db.commit()

    assert admin_client.put(URL, json={"value": "Berlin"}).status_code == 200

    db.expire_all()
    assert _dates(db, past, source="admin") == {date(past, 7, 6)}
    assert _dates(db, past, source="workalendar") == _expected("Berlin", past)


def test_year_without_statutory_holidays_is_not_filled(db, admin_client):
    """Nur Jahre, für die es gesetzliche Feiertage gab, werden neu erzeugt — ein
    Jahr mit ausschließlich eigenen Feiertagen bleibt so, wie es ist."""
    past = _past_year()
    _seed_bavaria(db)
    db.add(PublicHoliday(
        date=date(past - 3, 7, 6), name="Schützenfest", year=past - 3,
        tenant_id=DEFAULT_TENANT_ID, is_custom=True, source="admin",
    ))
    db.commit()

    assert admin_client.put(URL, json={"value": "Berlin"}).status_code == 200

    db.expire_all()
    assert _dates(db, past - 3) == {date(past - 3, 7, 6)}


def test_other_tenant_untouched(db, admin_client):
    """F-026: die Jahre und die Löschung kommen nur aus dem eigenen Mandanten."""
    past = _past_year()
    _seed_bavaria(db)
    holiday_service.sync_holidays(db, past - 2, "Bayern", tenant_id=OTHER_TENANT_ID)
    db.commit()
    other_before = _dates(db, past - 2, tenant_id=OTHER_TENANT_ID)
    assert other_before

    assert admin_client.put(URL, json={"value": "Berlin"}).status_code == 200

    db.expire_all()
    assert _dates(db, past - 2, tenant_id=OTHER_TENANT_ID) == other_before
    # Das Jahr des fremden Mandanten wird beim eigenen nicht angelegt.
    assert _dates(db, past - 2) == set()


def test_warning_when_changed_year_is_closed(db, admin_client, test_admin):
    past = _past_year()
    _seed_bavaria(db, past)
    db.add(YearCarryover(
        tenant_id=DEFAULT_TENANT_ID, user_id=test_admin.id, year=past + 1,
        overtime_hours=0, vacation_days=0,
    ))
    db.commit()

    resp = admin_client.put(URL, json={"value": "Berlin"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["value"] == "Berlin"
    assert body["warning"] == (
        f"Jahresabschluss {past} bereits erfolgt — Carryover {past + 1} ist nun "
        f"veraltet, bitte Jahresabschluss erneut ausführen."
    )


def test_no_warning_without_closed_year(db, admin_client):
    past = _past_year()
    _seed_bavaria(db, past)

    resp = admin_client.put(URL, json={"value": "Berlin"})
    assert resp.status_code == 200, resp.text
    assert resp.json().get("warning") is None


def test_no_warning_for_closed_year_without_holidays(db, admin_client, test_admin):
    """Ein abgeschlossenes Jahr ohne gesetzliche Feiertage bleibt unberührt —
    dann gibt es auch nichts zu warnen."""
    past = _past_year()
    _seed_bavaria(db)
    db.add(YearCarryover(
        tenant_id=DEFAULT_TENANT_ID, user_id=test_admin.id, year=past - 1,
        overtime_hours=0, vacation_days=0,
    ))
    db.commit()

    resp = admin_client.put(URL, json={"value": "Berlin"})
    assert resp.status_code == 200, resp.text
    assert resp.json().get("warning") is None
