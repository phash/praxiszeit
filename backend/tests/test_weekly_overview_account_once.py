"""Ultrareview (Performance): ``/api/dashboard/weekly-overview`` rechnete das
Überstundenkonto je Woche komplett neu — bis zu 53 volle Kontoberechnungen
(alle Einträge/Abwesenheiten ab Übertrag bzw. erstem Eintrag) pro Seitenaufruf.

Jetzt rechnet ``calculation_service.get_week_summaries`` alle Wochen mit EINER
Kontoberechnung (``get_overtime_accounts``: Daten einmal laden, Monatsdeltas je
(Monat, wirksamer Stichtag) einmal rechnen). Die Zahlen bleiben byte-identisch
zur Einzelrechnung je Woche (``get_week_summary`` → ``get_overtime_account``),
die der Admin-Wochenbericht (#500) weiter nutzt.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, TimeEntry, YearCarryover
from tests.conftest import DEFAULT_TENANT_ID

# Donnerstag, KW 1/2027. Die laufende Woche beginnt am Mo 04.01.2027; 53 Wochen
# zurück reichen bis Anfang Januar 2026 — mit Monatswechseln in Wochen, dem
# Jahreswechsel (KW 53/2026: 28.12.–03.01.) und zwei Jahresüberträgen.
TODAY = dt.date(2027, 1, 7)


def _app() -> FastAPI:
    from app.routers import dashboard as dashboard_router
    from app.routers import reports as reports_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit Wochenübersicht-Perf Test")
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
    import app.routers.dashboard as dash
    import app.routers.reports as rep
    from app.services import calculation_service as calc

    monkeypatch.setattr(dash, "today_local", lambda: TODAY)
    monkeypatch.setattr(dash, "now_local", lambda: dt.datetime(2027, 1, 7, 18, 0))
    monkeypatch.setattr(rep, "now_local", lambda: dt.datetime(2027, 1, 7, 18, 0))
    monkeypatch.setattr(calc, "today_local", lambda: TODAY)


def _client(db, user):
    def override_db():
        yield db

    _APP.dependency_overrides[get_db] = override_db
    _APP.dependency_overrides[get_current_user] = lambda: user
    _APP.dependency_overrides[require_admin] = lambda: user
    return TestClient(_APP)


def _seed(db, user):
    """Ein gutes Jahr Daten: Eintritt 01.12.2025, wechselnde Tageslängen,
    Lücken, Urlaub, Krankheit, zwei Jahresüberträge und ein heute bereits
    abgeschlossener Eintrag (Stichtag #313 = heute)."""
    user.first_work_day = dt.date(2025, 12, 1)
    db.add(YearCarryover(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                         overtime_hours=3.25, vacation_days=0))
    db.add(YearCarryover(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, year=2027,
                         overtime_hours=-7.5, vacation_days=0))
    ends = [dt.time(16, 0), dt.time(15, 30), dt.time(17, 15), dt.time(16, 45), dt.time(14, 10)]
    d = dt.date(2025, 12, 1)
    i = 0
    while d < TODAY:
        if d.weekday() < 5:
            i += 1
            if i % 37 == 0:
                db.add(Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                               type=AbsenceType.VACATION, hours=8))
            elif i % 41 == 0:
                db.add(Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                               type=AbsenceType.SICK, hours=8))
            elif i % 13 != 0:  # ab und zu ein vergessener Tag
                db.add(TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                                 start_time=dt.time(8, 0), end_time=ends[i % 5],
                                 break_minutes=30 if i % 3 else 0))
        d += dt.timedelta(days=1)
    # Heute schon ausgestempelt → Stichtag heute.
    db.add(TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=TODAY,
                     start_time=dt.time(7, 45), end_time=dt.time(12, 5), break_minutes=0))
    db.commit()
    return user


def _reference_rows(db, user):
    """Die Rechnung VOR dem Umbau: je Woche get_week_summary mit eigener
    Kontoberechnung (get_overtime_account)."""
    from app.services import calculation_service as calc

    cutoff = calc.get_soll_cutoff_date(db, user)
    assert cutoff == TODAY
    current_monday = TODAY - dt.timedelta(days=TODAY.weekday())
    monday = current_monday - dt.timedelta(weeks=52)
    rows = []
    while monday <= current_monday:
        wk_end = monday + dt.timedelta(days=6)
        ot_cutoff = min(wk_end, cutoff)
        rows.append({
            "week_start": monday.isoformat(),
            "target": float(calc.get_range_target(db, user, monday, wk_end, up_to_date=cutoff)),
            "actual": float(calc.get_range_actual(db, user, monday, wk_end, up_to_date=cutoff)),
            "cumulative": float(calc.get_overtime_account(
                db, user, wk_end.year, wk_end.month, cutoff_date=ot_cutoff)),
        })
        monday += dt.timedelta(weeks=1)
    return rows


def _count_account_calls(monkeypatch):
    from app.services import calculation_service as calc

    calls = []
    for name in ("get_overtime_account", "get_overtime_accounts"):
        orig = getattr(calc, name, None)
        if orig is None:
            continue

        def wrapper(*a, _orig=orig, _name=name, **k):
            calls.append(_name)
            return _orig(*a, **k)

        monkeypatch.setattr(calc, name, wrapper)
    return calls


@pytest.fixture(params=["tages_soll", "festes_monats_soll"])
def seeded_user(request, db, test_user):
    if request.param == "festes_monats_soll":
        test_user.milog_working_time_account = True
        test_user.agreed_monthly_hours = Decimal("150.0")
        test_user.use_fixed_monthly_target = True
    return _seed(db, test_user)


def test_53_wochen_hoechstens_eine_kontoberechnung(db, seeded_user, frozen_today, monkeypatch):
    calls = _count_account_calls(monkeypatch)
    r = _client(db, seeded_user).get("/api/dashboard/weekly-overview?weeks=53")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 53
    assert len(calls) <= 1, calls


def test_53_wochen_byte_identisch_zur_einzelrechnung(db, seeded_user, frozen_today):
    rows = _client(db, seeded_user).get("/api/dashboard/weekly-overview?weeks=53").json()
    reference = _reference_rows(db, seeded_user)

    assert [r["week_start"] for r in rows] == [r["week_start"] for r in reference]
    # Der Szenario-Aufbau deckt ab, was er abdecken soll.
    assert rows[0]["week_start"] == "2026-01-05"
    assert "2026-12-28" in [r["week_start"] for r in rows]  # Jahreswechsel in der Woche
    for row, ref in zip(rows, reference):
        for key in ("target", "actual", "cumulative"):
            assert row[key] == ref[key], (row["week_start"], key, row[key], ref[key])
        assert row["balance"] == float((Decimal(str(ref["actual"])) - Decimal(str(ref["target"])))
                                       .quantize(Decimal("0.01")))
    # Konto springt am Jahresübertrag 2027 (Woche mit Ende im Januar 2027).
    assert len({r["cumulative"] for r in rows}) > 10
    assert rows[-2]["week_start"] == "2026-12-28"


# Fingerabdruck der vollständigen Antwort (alle 53 Zeilen, alle Felder), erzeugt
# mit der Einzelrechnung je Woche VOR dem Umbau.
_SNAPSHOT_SHA256 = {
    "tages_soll": "462f25d617ddd65b0d4831947887e77dfed9511a7014f03bf343a5c01b6eed87",
    "festes_monats_soll": "75c63615be593b6b63a8ae254be62d53da11e4fbb6986c71bc0ebf04f7393adb",
}


def test_53_wochen_antwort_unveraendert_zum_stand_vor_dem_umbau(db, seeded_user, frozen_today, request):
    import hashlib
    import json

    rows = _client(db, seeded_user).get("/api/dashboard/weekly-overview?weeks=53").json()
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    assert digest == _SNAPSHOT_SHA256[request.node.callspec.params["seeded_user"]]


def test_admin_wochenbericht_gleiche_zahlen(db, seeded_user, test_admin, frozen_today):
    """#500: Admin-Wochenbericht (Einzelrechnung) = Wochenzeile des Dashboards."""
    mine = {row["week_start"]: row for row in
            _client(db, seeded_user).get("/api/dashboard/weekly-overview?weeks=53").json()}
    for monday in ("2026-03-30", "2026-08-31", "2026-12-28", "2027-01-04"):
        admin_rows = _client(db, test_admin).get(
            f"/api/admin/reports/weekly?week_start={monday}").json()
        admin_row = next(r for r in admin_rows if r["user_id"] == str(seeded_user.id))
        row = mine[monday]
        assert row["target"] == admin_row["target_hours"]
        assert row["actual"] == admin_row["actual_hours"]
        assert row["balance"] == admin_row["balance"]
        assert row["cumulative"] == admin_row["overtime_cumulative"]


def test_konto_batch_gleich_einzelaufrufen(db, seeded_user, frozen_today):
    """get_overtime_accounts liefert je Punkt exakt (Decimal-gleich) den Wert
    von get_overtime_account — auch für Stichtage vor/nach dem Monatsende,
    Monate ohne Stichtag und Punkte vor dem ersten Eintrag."""
    from app.services import calculation_service as calc

    points = [
        (2025, 11, None), (2025, 12, None), (2025, 12, dt.date(2025, 12, 10)),
        (2026, 1, dt.date(2025, 12, 31)), (2026, 2, dt.date(2026, 2, 28)),
        (2026, 2, dt.date(2026, 3, 5)), (2026, 6, None), (2026, 12, dt.date(2026, 12, 31)),
        (2027, 1, dt.date(2026, 12, 31)), (2027, 1, dt.date(2027, 1, 3)), (2027, 1, TODAY),
        (2027, 1, None),
    ]
    batch = calc.get_overtime_accounts(db, seeded_user, points)
    single = [calc.get_overtime_account(db, seeded_user, y, m, cutoff_date=c) for (y, m, c) in points]
    assert [str(v) for v in batch] == [str(v) for v in single]
