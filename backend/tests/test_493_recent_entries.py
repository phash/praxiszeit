"""#493: Die Karte „Letzte Einträge" (Mitarbeiter-Dashboard, mobil) braucht die
``n`` neuesten Einträge UNABHÄNGIG von der Monatsgrenze.

Bisher fragte sie ``GET /api/time-entries?month=<laufender Monat>`` — am
Monatsersten (vor dem ersten Stempeln) war die Karte deshalb leer, und am
2. eines Monats stand dort genau ein Eintrag statt der fünf letzten. Das
Dashboard fragt jetzt ``GET /api/time-entries/?limit=5`` ohne Monat. Diese
Tests halten den Vertrag fest, auf den es sich verlässt: ohne ``month`` sortiert
der Endpunkt absteigend (Datum, dann Beginn) und schneidet erst danach ab.
"""
import datetime as dt
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import TimeEntry
from tests.conftest import DEFAULT_TENANT_ID


def _app() -> FastAPI:
    from app.routers import time_entries as te_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit #493 Test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(te_router.router)
    return app


_APP = _app()


def _client(db, user):
    def override_db():
        yield db

    _APP.dependency_overrides[get_db] = override_db
    _APP.dependency_overrides[get_current_user] = lambda: user
    return TestClient(_APP)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _APP.dependency_overrides.clear()


def _entry(user, d, start, end, tenant_id=DEFAULT_TENANT_ID):
    return TimeEntry(user_id=user.id, tenant_id=tenant_id, date=d,
                     start_time=start, end_time=end, break_minutes=0)


def _ranges(body):
    return [(e["date"], e["start_time"][:5]) for e in body]


def test_neueste_ueber_die_monatsgrenze_neueste_zuerst(db, test_user):
    """Am 2. Oktober: ein Eintrag im Oktober, der Rest im September — die Karte
    zeigt die fünf neuesten, nicht nur den einen Oktober-Eintrag."""
    for d, start, end in [
        (dt.date(2026, 9, 28), dt.time(8, 0), dt.time(12, 0)),
        (dt.date(2026, 9, 29), dt.time(8, 0), dt.time(12, 0)),
        (dt.date(2026, 9, 30), dt.time(7, 41), dt.time(12, 0)),
        (dt.date(2026, 9, 30), dt.time(14, 11), dt.time(17, 0)),
        (dt.date(2026, 10, 1), dt.time(7, 39), dt.time(12, 5)),
        (dt.date(2026, 10, 2), dt.time(7, 44), None),  # läuft noch
    ]:
        db.add(_entry(test_user, d, start, end))
    db.commit()

    r = _client(db, test_user).get("/api/time-entries/?limit=5")
    assert r.status_code == 200, r.text
    assert _ranges(r.json()) == [
        ("2026-10-02", "07:44"),
        ("2026-10-01", "07:39"),
        ("2026-09-30", "14:11"),
        ("2026-09-30", "07:41"),
        ("2026-09-29", "08:00"),
    ]


def test_am_monatsersten_ohne_eintrag_im_monat_nicht_leer(db, test_user):
    """Reproduktion aus dem Ticket: am 1. vor dem ersten Stempeln lieferte die
    Monatsabfrage nichts — ohne ``month`` kommen die Einträge des Vormonats."""
    db.add(_entry(test_user, dt.date(2026, 9, 30), dt.time(8, 0), dt.time(16, 0)))
    db.commit()

    client = _client(db, test_user)
    assert client.get("/api/time-entries/?month=2026-10").json() == []
    assert _ranges(client.get("/api/time-entries/?limit=5").json()) == [("2026-09-30", "08:00")]


def test_nur_eigene_eintraege_des_eigenen_mandanten(db, test_user, test_admin):
    """Ohne ``month`` gelten dieselben Filter: eigene Einträge, eigener Mandant
    (F-026) — ein Kollegen-Eintrag oder eine fremd zugeordnete Zeile erscheint nicht."""
    from app.models.tenant import Tenant

    other = uuid.UUID("00000000-0000-0000-0000-000000000002")
    db.add(Tenant(id=other, name="Other", slug="other", is_active=True, mode="single"))
    db.commit()
    db.add(_entry(test_user, dt.date(2026, 10, 1), dt.time(8, 0), dt.time(9, 0)))
    db.add(_entry(test_admin, dt.date(2026, 10, 2), dt.time(8, 0), dt.time(9, 0)))
    db.add(_entry(test_user, dt.date(2026, 10, 3), dt.time(8, 0), dt.time(9, 0), tenant_id=other))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/?limit=5").json()
    assert _ranges(body) == [("2026-10-01", "08:00")]
