"""#500: Wochenübersicht im Mitarbeiter-Dashboard (Umschalter Monat/Woche).

Vergessene Nachmittagsblöcke oder um 23:59 automatisch geschlossene Einträge
fallen pro Woche sofort auf, im Monat gehen sie unter. Das Dashboard bekommt
deshalb neben der Monatsübersicht eine Wochenansicht —
``GET /api/dashboard/weekly-overview`` liefert die letzten N ISO-Wochen der
angemeldeten Person mit Soll/Ist/Saldo und dem Überstundenkonto zum
Wochenende.

Rechenweg = derselbe wie im Wochenbericht des Admin-Dashboards (#329):
``calculation_service.get_week_summary`` ist die eine Quelle für beide
Flächen; die laufende Woche wird am #313-Saldo-Stichtag gekappt („bis heute",
wie die Monatsübersicht des Mitarbeiter-Dashboards).
"""
import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import TimeEntry, YearCarryover
from tests.conftest import DEFAULT_TENANT_ID

# Donnerstag, KW 41. Montag der laufenden Woche = 05.10.2026.
TODAY = dt.date(2026, 10, 8)
KW40 = dt.date(2026, 9, 28)
KW41 = dt.date(2026, 10, 5)


def _app() -> FastAPI:
    from app.routers import dashboard as dashboard_router
    from app.routers import reports as reports_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit #500 Test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(dashboard_router.router)
    app.include_router(reports_router.router)
    return app


_APP = _app()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _APP.dependency_overrides.clear()


@pytest.fixture
def frozen_today(monkeypatch):
    """„Heute" = Do 08.10.2026 — im Router UND im Saldo-Stichtag (#313)."""
    import app.routers.dashboard as dash
    import app.routers.reports as rep
    from app.services import calculation_service as calc

    monkeypatch.setattr(dash, "today_local", lambda: TODAY)
    monkeypatch.setattr(dash, "now_local", lambda: dt.datetime(2026, 10, 8, 9, 0))
    monkeypatch.setattr(rep, "now_local", lambda: dt.datetime(2026, 10, 8, 9, 0))
    monkeypatch.setattr(calc, "today_local", lambda: TODAY)


def _client(db, user):
    def override_db():
        yield db

    _APP.dependency_overrides[get_db] = override_db
    _APP.dependency_overrides[get_current_user] = lambda: user
    _APP.dependency_overrides[require_admin] = lambda: user
    return TestClient(_APP)


def _entry(user, d, start=dt.time(8, 0), end=dt.time(16, 0)):
    return TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                     start_time=start, end_time=end, break_minutes=0)


@pytest.fixture
def two_weeks(db, test_user):
    """Eintritt Mo 28.09.; KW 40 voll gearbeitet bis auf Do 01.10. (Nachmittag
    vergessen: nur 4 h); KW 41 Mo–Mi je 8 h, heute (Do) noch nicht ausgestempelt."""
    test_user.first_work_day = KW40
    for i in range(5):
        d = KW40 + dt.timedelta(days=i)
        end = dt.time(12, 0) if d == dt.date(2026, 10, 1) else dt.time(16, 0)
        db.add(_entry(test_user, d, end=end))
    for i in range(3):
        db.add(_entry(test_user, KW41 + dt.timedelta(days=i)))
    db.commit()
    return test_user


def test_wochen_chronologisch_mit_soll_ist_saldo_konto(db, two_weeks, frozen_today):
    r = _client(db, two_weeks).get("/api/dashboard/weekly-overview")
    assert r.status_code == 200, r.text
    rows = r.json()

    # Beginnt mit der Woche des ersten Eintrags (wie die Monatsübersicht mit dem
    # Monat des ersten Eintrags), älteste zuerst.
    assert [row["week_start"] for row in rows] == ["2026-09-28", "2026-10-05"]
    assert [row["week_end"] for row in rows] == ["2026-10-04", "2026-10-11"]
    assert [(row["iso_year"], row["iso_week"]) for row in rows] == [(2026, 40), (2026, 41)]

    kw40, kw41 = rows
    assert kw40["target"] == 40.0
    assert kw40["actual"] == 36.0
    assert kw40["balance"] == -4.0
    assert kw40["cumulative"] == -4.0

    # Laufende Woche „bis heute": heute ist noch nicht ausgestempelt → Stichtag
    # gestern (Mi), also 3 Tage Soll — kein Wochenanfangs-Minus.
    assert kw41["target"] == 24.0
    assert kw41["actual"] == 24.0
    assert kw41["balance"] == 0.0
    assert kw41["cumulative"] == -4.0


def test_heutiger_abgeschlossener_tag_zaehlt_mit(db, two_weeks, frozen_today):
    db.add(_entry(two_weeks, TODAY, end=dt.time(12, 0)))  # Do 4 h, ausgestempelt
    db.commit()

    kw41 = _client(db, two_weeks).get("/api/dashboard/weekly-overview").json()[-1]
    assert kw41["target"] == 32.0
    assert kw41["actual"] == 28.0
    assert kw41["balance"] == -4.0
    assert kw41["cumulative"] == -8.0


def test_konto_der_laufenden_woche_gleich_ueberstundenkonto(db, two_weeks, frozen_today):
    """Die letzte Wochenzeile endet auf demselben Konto wie die Kachel
    „Überstundenkonto" und die letzte Monatszeile."""
    client = _client(db, two_weeks)
    weekly = client.get("/api/dashboard/weekly-overview").json()
    overtime = client.get("/api/dashboard/overtime").json()
    assert weekly[-1]["cumulative"] == pytest.approx(overtime["current_balance"])
    assert overtime["history"][-1]["cumulative"] == pytest.approx(weekly[-1]["cumulative"])


def test_gleiche_zahlen_wie_wochenbericht_im_admin_dashboard(db, two_weeks, test_admin, frozen_today):
    """Parität zur Admin-Wochenansicht (#329) — dieselbe Rechnung, keine zweite."""
    mine = {row["week_start"]: row for row in
            _client(db, two_weeks).get("/api/dashboard/weekly-overview").json()}
    for monday in (KW40, KW41):
        admin_rows = _client(db, test_admin).get(
            f"/api/admin/reports/weekly?week_start={monday.isoformat()}"
        ).json()
        admin_row = next(r for r in admin_rows if r["user_id"] == str(two_weeks.id))
        row = mine[monday.isoformat()]
        assert row["target"] == admin_row["target_hours"]
        assert row["actual"] == admin_row["actual_hours"]
        assert row["balance"] == admin_row["balance"]
        assert row["cumulative"] == admin_row["overtime_cumulative"]


def test_anzahl_wochen_begrenzt(db, two_weeks, frozen_today):
    rows = _client(db, two_weeks).get("/api/dashboard/weekly-overview?weeks=1").json()
    assert [row["week_start"] for row in rows] == ["2026-10-05"]


def test_standard_acht_wochen_bei_langer_historie(db, test_user, frozen_today):
    db.add(_entry(test_user, dt.date(2026, 1, 5)))
    db.commit()
    rows = _client(db, test_user).get("/api/dashboard/weekly-overview").json()
    assert len(rows) == 8
    assert rows[0]["week_start"] == "2026-08-17"
    assert rows[-1]["week_start"] == "2026-10-05"


def test_wochenwerte_ueber_jahresuebertrag(db, test_user, frozen_today):
    """Ein Jahresübertrag (YearCarryover) ist Startwert des Kontos — die
    Wochenzeile übernimmt ihn wie die Monatsübersicht."""
    test_user.first_work_day = KW40
    db.add(YearCarryover(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                         overtime_hours=10.0, vacation_days=0))
    for i in range(5):
        db.add(_entry(test_user, KW40 + dt.timedelta(days=i)))
    db.commit()
    kw40 = _client(db, test_user).get("/api/dashboard/weekly-overview").json()[0]
    assert kw40["balance"] == 0.0
    assert kw40["cumulative"] == 10.0


@pytest.mark.parametrize("weeks", [0, 54])
def test_ungueltige_wochenanzahl(db, two_weeks, frozen_today, weeks):
    r = _client(db, two_weeks).get(f"/api/dashboard/weekly-overview?weeks={weeks}")
    assert r.status_code == 422


def test_ohne_eintraege_leer(db, test_user, frozen_today):
    assert _client(db, test_user).get("/api/dashboard/weekly-overview").json() == []


def test_ohne_stundenzaehlung_leer(db, two_weeks, frozen_today):
    two_weeks.track_hours = False
    db.commit()
    assert _client(db, two_weeks).get("/api/dashboard/weekly-overview").json() == []
