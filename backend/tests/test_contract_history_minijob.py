"""Teil A, Task 11: die drei Minijob-Felder (``milog_working_time_account``,
``agreed_monthly_hours``, ``use_fixed_monthly_target``) gelten MONATSWEISE laut
Vertrags-Snapshot am Monatsersten (``calculation_service.month_contract``) — nie
aus der Live-Spalte der User-Zeile (dem Spiegel des Heute).

Spec A5: eine Anhebung der vereinbarten Monatsstunden ab 2027 lässt das feste
Monats-Soll 2026 unverändert."""
from datetime import date, time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.services import calculation_service as cs
from app.services import milog_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_user, employee_user, endpoints_app, tenant,
)
from tests.wh_change_helpers import add_row, entry, freeze

MINIJOB = dict(milog_working_time_account=True, agreed_monthly_hours=Decimal("43.3"),
               use_fixed_monthly_target=True)


class _MO:
    def __init__(self, target, actual):
        self.target = Decimal(str(target))
        self.actual = Decimal(str(actual))
        self.cumulative = Decimal("0")


@pytest.fixture
def minijob_user(db, default_tenant):
    u = User(username="mj", email="mj@t.l", password_hash="x", first_name="M", last_name="J",
             role=UserRole.EMPLOYEE, weekly_hours=Decimal("10"), work_days_per_week=5,
             vacation_days=Decimal("30"), track_hours=True, is_active=True, tenant_id=DEFAULT_TENANT_ID,
             **MINIJOB)
    db.add(u)
    db.commit()
    db.refresh(u)
    add_row(db, u, date(2026, 1, 1), weekly_hours=10, vacation_days=Decimal("30"), track_hours=True,
            **MINIJOB)
    return u


def test_agreed_raise_from_2027_keeps_2026_target(db, minijob_user):   # spec A5
    before = [cs.get_monthly_target(db, minijob_user, 2026, m) for m in range(1, 13)]
    assert before == [Decimal("43.30")] * 12
    add_row(db, minijob_user, date(2027, 1, 1), weekly_hours=10, vacation_days=Decimal("30"),
            track_hours=True, agreed_monthly_hours=Decimal("45"), use_fixed_monthly_target=True,
            milog_working_time_account=True)
    minijob_user.agreed_monthly_hours = Decimal("45")
    db.commit()     # der Spiegel (wie nach einem Schreiben am/nach dem 01.01.2027)
    assert [cs.get_monthly_target(db, minijob_user, 2026, m) for m in range(1, 13)] == before
    assert cs.get_monthly_target(db, minijob_user, 2027, 3) == Decimal("45.00")
    assert cs.fixed_monthly_target(db, minijob_user, 2026, 12) == Decimal("43.30")
    assert cs.fixed_monthly_target(db, minijob_user, 2027, 1) == Decimal("45.00")
    ytd = cs.get_ytd_summary(db, minijob_user, 2026, cutoff_date=date(2026, 12, 31))
    assert ytd["target_hours"] == float(Decimal("43.30") * 12)


def test_fixed_mode_switched_on_mid_year_applies_from_month(db, minijob_user):
    row = db.query(cs.WorkingHoursChange).filter_by(user_id=minijob_user.id).one()
    row.use_fixed_monthly_target = False
    minijob_user.use_fixed_monthly_target = False
    db.commit()
    entry(db, minijob_user, date(2026, 1, 5), time(8, 0), time(10, 0), grace=None)
    daily = {m: cs.get_monthly_target(db, minijob_user, 2026, m) for m in range(1, 13)}
    assert daily[3] == Decimal("44.00")          # 22 Werktage × 2 h — Tagesrechnung
    add_row(db, minijob_user, date(2026, 7, 1), weekly_hours=10, vacation_days=Decimal("30"),
            track_hours=True, **MINIJOB)
    minijob_user.use_fixed_monthly_target = True   # Spiegel
    db.commit()
    after = {m: cs.get_monthly_target(db, minijob_user, 2026, m) for m in range(1, 13)}
    assert [after[m] for m in range(1, 7)] == [daily[m] for m in range(1, 7)]
    assert [after[m] for m in range(7, 13)] == [Decimal("43.30")] * 6
    assert cs.month_contract(db, minijob_user, 2026, 6).fixed_mode is False
    assert cs.month_contract(db, minijob_user, 2026, 7).fixed_mode is True
    # Ein Bereich über die Grenze: Juni Tagesrechnung + Juli fest.
    assert cs.get_range_target(db, minijob_user, date(2026, 6, 1), date(2026, 7, 31)) == \
        daily[6] + Decimal("43.30")
    # Konto-Pfade (Verlauf, Konto, Jahressumme) nehmen je Monat denselben Modus.
    hist = cs.get_overtime_history_detailed(db, minijob_user, 2026, 12)
    assert [hist[(2026, m)].target for m in range(1, 13)] == [after[m] for m in range(1, 13)]
    assert cs.get_overtime_account(db, minijob_user, 2026, 12) == hist[(2026, 12)].cumulative
    ytd = cs.get_ytd_summary(db, minijob_user, 2026, cutoff_date=date(2026, 12, 31))
    assert ytd["target_hours"] == float(sum(after.values()))


def test_milog_50_check_off_in_months_without_account(db, minijob_user):
    row = db.query(cs.WorkingHoursChange).filter_by(user_id=minijob_user.id).one()
    row.milog_working_time_account = False
    row.use_fixed_monthly_target = False
    db.commit()
    add_row(db, minijob_user, date(2026, 7, 1), weekly_hours=10, vacation_days=Decimal("30"),
            track_hours=True, **MINIJOB)
    assert milog_service.milog_50_check(db, minijob_user, 2026, 3, monthly_actual=Decimal("100")) is None
    assert milog_service.milog_50_check(db, minijob_user, 2026, 8, monthly_actual=Decimal("100")) is not None
    # Fix-Plausibilität ebenfalls je Monat.
    entry(db, minijob_user, date(2026, 3, 2), time(6, 0), time(20, 0), grace=None)
    assert milog_service.monthly_exceeded_check(db, minijob_user, 2026, 3) is None


def test_settlement_aging_skips_months_without_account(db, minijob_user):
    row = db.query(cs.WorkingHoursChange).filter_by(user_id=minijob_user.id).one()
    row.effective_from = date(2025, 1, 1)
    row.milog_working_time_account = False
    row.use_fixed_monthly_target = False
    db.commit()
    add_row(db, minijob_user, date(2025, 7, 1), weekly_hours=10, vacation_days=Decimal("30"),
            track_hours=True, **MINIJOB)
    detailed = {(2025, 2): _MO(0, 10), (2025, 8): _MO(0, 5), (2026, 3): _MO(0, 0)}
    res = milog_service.settlement_aging(db, minijob_user, date(2026, 3, 15), detailed=detailed)
    assert (res["oldest_year"], res["oldest_month"]) == (2025, 8)
    assert abs(res["hours"] - 5.0) < 0.01
    # Monat des Stichtags ohne Konto → keine Prüfung.
    add_row(db, minijob_user, date(2026, 3, 1), weekly_hours=10, vacation_days=Decimal("30"),
            track_hours=True, milog_working_time_account=False, agreed_monthly_hours=Decimal("43.3"),
            use_fixed_monthly_target=False)
    assert milog_service.settlement_aging(db, minijob_user, date(2026, 3, 15), detailed=detailed) is None


def test_agreed_monthly_hours_by_month(db, minijob_user):
    add_row(db, minijob_user, date(2027, 1, 1), weekly_hours=10, vacation_days=Decimal("30"),
            track_hours=True, agreed_monthly_hours=Decimal("45"), use_fixed_monthly_target=True,
            milog_working_time_account=True)
    minijob_user.agreed_monthly_hours = Decimal("45")
    db.commit()
    assert milog_service.agreed_monthly_hours(db, minijob_user, date(2026, 12, 1)) == Decimal("43.3")
    assert milog_service.agreed_monthly_hours(db, minijob_user, date(2027, 1, 1)) == Decimal("45")
    # NULL im Snapshot = abgeleitet aus den Wochenstunden zum Datum (nie die User-Zeile).
    add_row(db, minijob_user, date(2027, 2, 1), weekly_hours=12, vacation_days=Decimal("30"),
            track_hours=True, agreed_monthly_hours=None, use_fixed_monthly_target=False,
            milog_working_time_account=True)
    assert milog_service.agreed_monthly_hours(db, minijob_user, date(2027, 2, 1)) == \
        Decimal("12") * milog_service.AGREED_MONTHLY_FACTOR


def test_users_overview_milog_gate_uses_today_snapshot(_db_session, employee_user, admin_user, monkeypatch):
    db, u = _db_session, employee_user
    add_row(db, u, date(2026, 1, 1), weekly_hours=40, track_hours=True, milog_working_time_account=False,
            agreed_monthly_hours=None, use_fixed_monthly_target=False, vacation_days=Decimal("30"))
    add_row(db, u, date(2026, 12, 1), weekly_hours=40, track_hours=True, milog_working_time_account=True,
            agreed_monthly_hours=None, use_fixed_monthly_target=False, vacation_days=Decimal("30"))
    u.milog_working_time_account = False      # zukunftsdatierte Zeile, noch nicht gespiegelt
    db.commit()
    freeze(monkeypatch, date(2026, 12, 2))
    monkeypatch.setattr(milog_service, "milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    monkeypatch.setattr(milog_service, "settlement_aging", lambda *a, **k: None)
    monkeypatch.setattr(cs, "get_overtime_history_detailed", lambda *a, **k: {(2026, 12): _MO(0, 0)})

    def _override_db():
        yield db
    endpoints_app.dependency_overrides.clear()
    endpoints_app.dependency_overrides[get_db] = _override_db
    endpoints_app.dependency_overrides[get_current_user] = lambda: admin_user
    endpoints_app.dependency_overrides[require_admin] = lambda: admin_user
    try:
        rows = {r["user_id"]: r for r in TestClient(endpoints_app).get("/api/admin/users-overview").json()}
        assert any("MILOG_ACCOUNT_50" in w for w in rows[str(u.id)]["milog_warnings"])
        assert rows[str(admin_user.id)]["milog_warnings"] == []
    finally:
        endpoints_app.dependency_overrides.clear()
