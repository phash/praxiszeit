"""#494: ``GET /api/time-entries/clock-status`` liefert das Tages-Ist und das
Tagessoll von heute mit.

Die mobile Stempelkarte zeigte „x von y h heute" bisher aus ``elapsed_minutes``
— das ist allein die Laufzeit des gerade OFFENEN Eintrags. Bei geteilten
Diensten (Vormittag + Nachmittag, in Praxen die Regel) fehlte damit der bereits
abgeschlossene Block, und nach dem Ausstempeln sprang die Anzeige auf 0:00.

``today_net_minutes`` = Σ ``net_hours`` der heute abgeschlossenen Einträge
(gekappte Zeit, Pause abgezogen — derselbe Wert, der ins Ist geht) + laufende
Netto-Minuten des offenen Eintrags.

``today_target_hours`` = Tagessoll von heute aus dem DATUMSAUFGELÖSTEN
Vertrags-Snapshot (#431), nicht aus den Live-Feldern der User-Zeile, die das
Frontend vorher selbst las.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import TimeEntry
from app.models.working_hours_change import WorkingHoursChange
from tests.conftest import DEFAULT_TENANT_ID

# Donnerstag, wie im Ticket (Julia Wagner, 08.10.2026).
TODAY = dt.date(2026, 10, 8)


def _app() -> FastAPI:
    from app.routers import time_entries as te_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit #494 Test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(te_router.router)
    return app


_APP = _app()


@pytest.fixture
def frozen_now(monkeypatch):
    """Friert „jetzt" im time_entries-Router ein; Rückgabe: Setter für die Uhrzeit."""
    import app.routers.time_entries as te

    state = {"now": dt.datetime(2026, 10, 8, 17, 30)}
    monkeypatch.setattr(te, "_today_local", lambda: TODAY)
    monkeypatch.setattr(te, "_now_local", lambda: state["now"].replace(tzinfo=te.LOCAL_TZ))

    def set_time(h, m):
        state["now"] = dt.datetime(2026, 10, 8, h, m)

    return set_time


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


def _entry(user, d, start, end, break_min=0):
    return TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                     start_time=start, end_time=end, break_minutes=break_min)


def test_abgeschlossene_bloecke_zaehlen_ohne_offenen_eintrag(db, test_user, frozen_now):
    """Reproduktion aus dem Ticket: 07:43–12:04 + 14:17–17:00, beide geschlossen →
    7:04 h (424 min), obwohl kein Eintrag offen ist."""
    db.add(_entry(test_user, TODAY, dt.time(7, 43), dt.time(12, 4)))
    db.add(_entry(test_user, TODAY, dt.time(14, 17), dt.time(17, 0)))
    db.commit()

    r = _client(db, test_user).get("/api/time-entries/clock-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_clocked_in"] is False
    assert body["today_net_minutes"] == 261 + 163


def test_offener_nachmittagsblock_plus_vormittag(db, test_user, frozen_now):
    """Während des Nachmittagsblocks: Vormittag (4:21) + laufende Minuten (1:10)."""
    frozen_now(15, 27)
    db.add(_entry(test_user, TODAY, dt.time(7, 43), dt.time(12, 4)))
    db.add(_entry(test_user, TODAY, dt.time(14, 17), None))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["is_clocked_in"] is True
    assert body["elapsed_minutes"] == 70  # unverändert: nur der offene Block
    assert body["today_net_minutes"] == 261 + 70


def test_pause_wird_abgezogen_und_andere_tage_zaehlen_nicht(db, test_user, frozen_now):
    db.add(_entry(test_user, TODAY, dt.time(8, 0), dt.time(14, 0), break_min=30))  # 5:30
    db.add(_entry(test_user, TODAY - dt.timedelta(days=1), dt.time(8, 0), dt.time(16, 0)))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_net_minutes"] == 330


def test_offener_block_vor_gekapptem_beginn_zaehlt_nicht_negativ(db, test_user, frozen_now):
    """Ein auf das Arbeitszeitfenster gekappter Beginn kann nach „jetzt" liegen
    (Einstempeln 06:40, Fenster ab 07:30). Das darf das Tages-Ist nicht senken."""
    frozen_now(6, 40)
    db.add(_entry(test_user, TODAY, dt.time(7, 30), None))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_net_minutes"] == 0


def test_ohne_eintraege_null(db, test_user, frozen_now):
    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["is_clocked_in"] is False
    assert body["today_net_minutes"] == 0


def test_tagessoll_gleichmaessig(db, test_user, frozen_now):
    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_target_hours"] == pytest.approx(8.0)  # 40 h / 5 Tage


def test_tagessoll_kommt_aus_dem_snapshot_nicht_aus_der_user_zeile(db, test_user, frozen_now):
    """#431: ab heute gilt ein Tagesplan Do 7 h — die User-Zeile trägt noch die
    alten 40 h / 5 Tage (8 h). Maßgeblich ist der Snapshot."""
    db.add(WorkingHoursChange(
        tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, effective_from=TODAY,
        weekly_hours=Decimal("23.00"), use_daily_schedule=True,
        hours_monday=Decimal("7.00"), hours_tuesday=Decimal("4.50"), hours_wednesday=None,
        hours_thursday=Decimal("7.00"), hours_friday=Decimal("4.50"), work_days_per_week=4,
    ))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_target_hours"] == pytest.approx(7.0)


def test_tagessoll_wochenende_null(db, test_user, monkeypatch):
    import app.routers.time_entries as te

    saturday = dt.date(2026, 10, 10)
    monkeypatch.setattr(te, "_today_local", lambda: saturday)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 10, 10, 10, 0, tzinfo=te.LOCAL_TZ))

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_target_hours"] == 0.0


def test_fremder_mandant_zaehlt_nicht(db, test_user, frozen_now):
    """F-026: Einträge mit fremder tenant_id (Fehlzuordnung) fließen nicht ein."""
    import uuid
    from app.models.tenant import Tenant

    other = uuid.UUID("00000000-0000-0000-0000-000000000002")
    db.add(Tenant(id=other, name="Other", slug="other", is_active=True, mode="single"))
    db.commit()
    db.add(TimeEntry(user_id=test_user.id, tenant_id=other, date=TODAY,
                     start_time=dt.time(8, 0), end_time=dt.time(10, 0), break_minutes=0))
    db.add(_entry(test_user, TODAY, dt.time(11, 0), dt.time(12, 0)))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_net_minutes"] == 60
