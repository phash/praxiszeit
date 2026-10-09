"""#501: Die plakative Jahresend-Warnung vor verfallendem Urlaub erst ab
mindestens 1,0 offenen Urlaubstagen.

Teilzeitkräfte haben oft Bruchteile von Urlaubstagen übrig (0,3 / 0,5 …), die
ins Folgejahr wandern und dort mit weiteren Bruchteilen zu ganzen Tagen
zusammengelegt werden. Ein solcher Rest ist kein „verfallender Urlaub", den man
noch schnell nehmen müsste — ein halber Urlaubstag lässt sich als ganzer Tag gar
nicht nehmen.

DIE eine Regel lebt in ``calculation_service.has_year_end_vacation_warning`` und
speist BEIDE Anzeigeflächen:
- ``GET /api/dashboard/vacation`` → ``has_carryover_warning`` (Mitarbeiter-Dashboard)
- ``GET /api/admin/reports/yearly-absences`` → ``has_year_end_warning``
  (Banner „Jahresend-Warnung: Offene Urlaubstage" im Admin-Dashboard)
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.services import calculation_service
from app.services.calculation_service import has_year_end_vacation_warning

OCT = dt.date(2026, 10, 15)


# --- die Regel selbst -------------------------------------------------------

@pytest.mark.parametrize("remaining, expected", [
    (0.0, False),
    (0.3, False),
    (0.5, False),
    (0.9, False),
    (1.0, True),
    (1.5, True),
    (12.0, True),
    (-2.0, False),
])
def test_schwelle_ein_ganzer_tag(remaining, expected):
    assert has_year_end_vacation_warning(remaining, 2026, OCT) is expected


def test_nimmt_auch_decimal():
    assert has_year_end_vacation_warning(Decimal("1.0"), 2026, OCT) is True
    assert has_year_end_vacation_warning(Decimal("0.9"), 2026, OCT) is False


def test_nur_im_vierten_quartal_des_laufenden_jahres():
    assert has_year_end_vacation_warning(5.0, 2026, dt.date(2026, 9, 30)) is False
    assert has_year_end_vacation_warning(5.0, 2026, dt.date(2026, 10, 1)) is True
    assert has_year_end_vacation_warning(5.0, 2025, OCT) is False  # Vorjahr
    assert has_year_end_vacation_warning(5.0, 2027, OCT) is False  # Folgejahr


# --- Flächen ---------------------------------------------------------------

def _app() -> FastAPI:
    from app.routers import dashboard as dashboard_router
    from app.routers import reports as reports_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit #501 Test")
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
def in_october(monkeypatch):
    """„Heute" = 15.10.2026 in beiden Routern."""
    import app.routers.dashboard as dash
    import app.routers.reports as rep

    monkeypatch.setattr(dash, "today_local", lambda: OCT)
    monkeypatch.setattr(rep, "today_local", lambda: OCT)


def _client(db, user):
    def override_db():
        yield db

    _APP.dependency_overrides[get_db] = override_db
    _APP.dependency_overrides[get_current_user] = lambda: user
    _APP.dependency_overrides[require_admin] = lambda: user
    return TestClient(_APP)


def _set_budget(db, user, days):
    user.vacation_days = days
    db.commit()
    # Rest = Budget (keine Abwesenheiten, kein Übertrag, ganzes Jahr beschäftigt)
    assert calculation_service.get_vacation_account(db, user, 2026)["remaining_days"] == pytest.approx(days)


@pytest.mark.parametrize("days, expected", [(0.5, False), (0.9, False), (1.0, True), (2.5, True)])
def test_mitarbeiter_dashboard_warnt_erst_ab_einem_tag(db, test_user, in_october, days, expected):
    _set_budget(db, test_user, days)

    r = _client(db, test_user).get("/api/dashboard/vacation?year=2026")
    assert r.status_code == 200, r.text
    assert r.json()["has_carryover_warning"] is expected


@pytest.mark.parametrize("days, expected", [(0.5, False), (1.0, True)])
def test_admin_jahresuebersicht_liefert_dieselbe_entscheidung(db, test_user, test_admin, in_october, days, expected):
    _set_budget(db, test_user, days)
    test_admin.vacation_days = 0  # Admin selbst ohne Rest → nie gewarnt
    db.commit()

    r = _client(db, test_admin).get("/api/admin/reports/yearly-absences?year=2026")
    assert r.status_code == 200, r.text
    rows = {row["user_id"]: row for row in r.json()}
    assert rows[str(test_user.id)]["remaining_vacation_days"] == pytest.approx(days)
    assert rows[str(test_user.id)]["has_year_end_warning"] is expected
    assert rows[str(test_admin.id)]["has_year_end_warning"] is False


def test_admin_jahresuebersicht_ausserhalb_q4_ohne_warnung(db, test_user, test_admin, monkeypatch):
    import app.routers.reports as rep

    monkeypatch.setattr(rep, "today_local", lambda: dt.date(2026, 6, 1))
    _set_budget(db, test_user, 10.0)

    r = _client(db, test_admin).get("/api/admin/reports/yearly-absences?year=2026")
    rows = {row["user_id"]: row for row in r.json()}
    assert rows[str(test_user.id)]["has_year_end_warning"] is False
