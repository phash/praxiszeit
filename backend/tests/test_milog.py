"""#377 Minijob/MiLoG: Flag-Persistenz, 50-%-Prüfung, 12-Monats-FIFO-Aging.

Harness wie backend/tests/test_child_sick.py (lokale _app() + dependency_overrides,
/api-Pfade, headerloser TestClient).
"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, YearCarryover
from app.models.tenant import Tenant
from app.services import auth_service, milog_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

USERS = "/api/admin/users"


def _app() -> FastAPI:
    from app.routers import admin, time_entries, dashboard
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    a = FastAPI()
    limiter.enabled = False
    a.state.limiter = limiter
    a.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    a.include_router(admin.router)
    a.include_router(time_entries.router)
    a.include_router(dashboard.router)
    return a


app = _app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="D", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, username, role=UserRole.EMPLOYEE, weekly=Decimal("7.62")):
    u = User(username=username, email=f"{username}@x.de",
             password_hash=auth_service.hash_password("test123"),
             first_name=username, last_name="T", role=role, weekly_hours=weekly,
             vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "admin1", role=UserRole.ADMIN, weekly=Decimal("40"))


@pytest.fixture
def employee(db, default_tenant):
    return _user(db, "emp1")


def _client_as(db, user, admin_user):
    def od():
        yield db
    app.dependency_overrides[get_db] = od
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Flag persistence (create + update) — incl. the UserListResponse round-trip
# --------------------------------------------------------------------------- #
def test_milog_flag_persisted_on_create_and_update(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = client.post(USERS, json={
        "username": "mj", "first_name": "M", "last_name": "J", "password": "E2ePass1234!",
        "role": "employee", "weekly_hours": 7.62, "vacation_days": 30, "work_days_per_week": 5,
        "milog_working_time_account": True,
    }).json()["user"]["id"]
    assert client.get(f"{USERS}/{uid}").json()["milog_working_time_account"] is True
    client.put(f"{USERS}/{uid}", json={"milog_working_time_account": False})
    assert client.get(f"{USERS}/{uid}").json()["milog_working_time_account"] is False
    app.dependency_overrides.clear()


def test_userlist_carries_milog_and_childsick(db, admin, default_tenant):
    # Regression: das Edit-Formular liest die Liste; fehlen die Felder dort,
    # setzt jeder Save sie still auf Default (#376 + #377).
    client = _client_as(db, admin, admin)
    uid = client.post(USERS, json={
        "username": "mj2", "first_name": "M", "last_name": "J", "password": "E2ePass1234!",
        "role": "employee", "weekly_hours": 7.62, "vacation_days": 30, "work_days_per_week": 5,
        "milog_working_time_account": True, "child_sick_days_per_year": 12,
    }).json()["user"]["id"]
    row = next(r for r in client.get(USERS).json() if r["id"] == uid)
    assert row["milog_working_time_account"] is True
    assert row["child_sick_days_per_year"] == 12
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# agreed_monthly_hours + 50% check (flat baseline)
# --------------------------------------------------------------------------- #
def test_agreed_monthly_hours_from_weekly(db, employee):
    employee.weekly_hours = Decimal("7.62")
    db.commit()
    got = milog_service.agreed_monthly_hours(db, employee, date(2026, 3, 1))
    assert Decimal("32.5") < got < Decimal("33.5")  # ≈ 33 h/Monat


def test_agreed_monthly_hours_explicit_override(db, employee):
    # #377 Baustein 2a: explizit gesetzte Monatszahl schlägt weekly×13/3.
    employee.agreed_monthly_hours = Decimal("40")
    db.commit()
    assert milog_service.agreed_monthly_hours(db, employee, date(2026, 3, 1)) == Decimal("40")
    # None → wieder aus den Wochenstunden abgeleitet.
    employee.agreed_monthly_hours = None
    db.commit()
    got = milog_service.agreed_monthly_hours(db, employee, date(2026, 3, 1))
    assert Decimal("32.5") < got < Decimal("33.5")


def test_milog_50_check_uses_explicit_monthly(db, employee):
    # #377 Baustein 2a: die 50-%-Grenze rechnet gegen die vereinbarte Monatszahl
    # (33 → Cap 16,5), unabhängig von weekly_hours.
    employee.milog_working_time_account = True
    employee.weekly_hours = Decimal("20")  # würde ≈86,7h/Monat ableiten — irrelevant
    employee.agreed_monthly_hours = Decimal("33")
    db.commit()
    chk = milog_service.milog_50_check(db, employee, 2026, 6, monthly_actual=55)
    assert chk is not None
    assert abs(chk["agreed_monthly"] - 33.0) < 0.01 and abs(chk["cap"] - 16.5) < 0.01
    # surplus 45−33 = 12 ≤ 16,5 → keine Warnung
    assert milog_service.milog_50_check(db, employee, 2026, 6, monthly_actual=45) is None


def test_milog_50_check_flat_baseline(db, employee, monkeypatch):
    employee.weekly_hours = Decimal("7.62")
    employee.milog_working_time_account = False
    db.commit()
    # Ist = 55h → surplus 55−33 = 22h > cap 16,5h
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: Decimal("55"))
    # Flag aus → None
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None
    employee.milog_working_time_account = True
    db.commit()
    res = milog_service.milog_50_check(db, employee, 2026, 3)
    assert res is not None and res["account_hours"] > res["cap"]
    assert "Mindestlohnhöhe" in res["caveat"]
    # Ist = 40h → surplus 7h < cap → None
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: Decimal("40"))
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None
    # track_hours aus → None trotz hoher Ist
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: Decimal("99"))
    employee.track_hours = False
    db.commit()
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None


def test_milog_50_check_at_cap_boundary_returns_none(db, employee, monkeypatch):
    # Strikt '>' — genau auf dem Cap ist KEINE Warnung. Dynamisch gerechnet, damit
    # der 7,62h-Fixture-Wert (agreed≈33,02) nicht hart verdrahtet werden muss.
    employee.weekly_hours = Decimal("7.62"); employee.milog_working_time_account = True
    db.commit()
    agreed = milog_service.agreed_monthly_hours(db, employee, date(2026, 3, 1))
    at_cap = agreed + agreed / 2  # surplus == cap
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: at_cap)
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: at_cap + Decimal("0.1"))  # knapp drüber
    assert milog_service.milog_50_check(db, employee, 2026, 3) is not None


def test_milog_50_check_zero_agreed_returns_none(db, employee, monkeypatch):
    # weekly_hours 0 → agreed 0 → kein sinnvoller Cap → keine Warnung trotz Ist.
    employee.weekly_hours = Decimal("0"); employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_actual",
                        lambda *a, **k: Decimal("40"))
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None


def test_flat_baseline_ignores_vacation_day(db, employee):
    # Flache Basis (Fix): ein VACATION-Tag im Monat darf die Konto-Plusstunden NICHT
    # erhöhen (unter dem alten balance-basierten Ansatz hätte der reduzierte Soll die
    # Kapazität aufgebläht). Gegen echte Berechnung, ohne Monkeypatch.
    from datetime import time as _time
    from app.models import TimeEntry, Absence, AbsenceType
    employee.weekly_hours = Decimal("7.62"); employee.milog_working_time_account = True
    db.commit()
    for d in (date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5), date(2026, 3, 6)):
        db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, date=d,
                         start_time=_time(8, 0), end_time=_time(16, 0), break_minutes=0))
    db.commit()
    acc_no_vac = milog_service.account_hours_in_month(db, employee, 2026, 3)
    db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, date=date(2026, 3, 9),
                   type=AbsenceType.VACATION, hours=Decimal("8"), half_day=False))
    db.commit()
    acc_with_vac = milog_service.account_hours_in_month(db, employee, 2026, 3)
    assert acc_no_vac == acc_with_vac and acc_no_vac > 0


# --------------------------------------------------------------------------- #
# settlement_aging FIFO + carryover seed + overdue semantics
# --------------------------------------------------------------------------- #
class _MO:
    def __init__(self, target, actual):
        self.target = Decimal(str(target))
        self.actual = Decimal(str(actual))
        self.cumulative = Decimal("0")


def test_settlement_aging_fifo_and_overdue(db, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    # +10h in 2025-01, −4h in 2025-06 (verbraucht Teil), Rest 6h altert
    hist = {(2025, 1): _MO(0, 10), (2025, 6): _MO(4, 0)}
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: hist)
    res = milog_service.settlement_aging(db, employee, date(2026, 3, 1))
    assert res["oldest_year"] == 2025 and res["oldest_month"] == 1
    assert abs(res["hours"] - 6.0) < 0.01
    assert res["age_months"] == 14 and res["overdue"] is True
    # Flag aus → None
    employee.milog_working_time_account = False
    db.commit()
    assert milog_service.settlement_aging(db, employee, date(2026, 3, 1)) is None


def test_settlement_aging_overdue_boundary(db, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    hist = {(2025, 3): _MO(0, 5)}
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: hist)
    # age 12 (2026-03) → NICHT überfällig, aber due_soon
    r12 = milog_service.settlement_aging(db, employee, date(2026, 3, 1))
    assert r12["age_months"] == 12 and r12["overdue"] is False and r12["due_soon"] is True
    # age 13 (2026-04) → überfällig
    r13 = milog_service.settlement_aging(db, employee, date(2026, 4, 1))
    assert r13["age_months"] == 13 and r13["overdue"] is True


def test_settlement_aging_seeds_carryover(db, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    # Jahresabschluss-Carryover 2025 = 8h offen; keine Monats-Deltas
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, year=2025,
                         overtime_hours=Decimal("8"), vacation_days=Decimal("0")))
    db.commit()
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: {(2025, 1): _MO(0, 0)})
    res = milog_service.settlement_aging(db, employee, date(2026, 6, 1))
    # geseedet auf Dez 2024 → sichtbar + überfällig
    assert res is not None and res["oldest_year"] == 2024 and res["oldest_month"] == 12
    assert abs(res["hours"] - 8.0) < 0.01 and res["overdue"] is True


# --------------------------------------------------------------------------- #
# Surfaces: users-overview (admin) · dashboard/overtime (MA) · create_time_entry
# --------------------------------------------------------------------------- #
def test_users_overview_milog_warnings(db, admin, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    monkeypatch.setattr("app.services.milog_service.settlement_aging", lambda *a, **k: None)
    # users-overview gatet den milog-Block auf non-empty detailed (Perf-Refaktor)
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: {(2025, 1): _MO(0, 0)})
    client = _client_as(db, admin, admin)
    rows = client.get(f"{USERS}-overview").json()
    row = next(r for r in rows if r["user_id"] == str(employee.id))
    assert any("MILOG_ACCOUNT_50" in w for w in row["milog_warnings"])
    # Flag aus → leer
    employee.milog_working_time_account = False
    db.commit()
    rows2 = client.get(f"{USERS}-overview").json()
    assert next(r for r in rows2 if r["user_id"] == str(employee.id))["milog_warnings"] == []
    app.dependency_overrides.clear()


def test_dashboard_overtime_milog_warnings(db, admin, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    monkeypatch.setattr("app.services.milog_service.settlement_aging",
                        lambda *a, **k: {"oldest_year": 2025, "oldest_month": 1, "age_months": 18,
                                         "hours": 9.0, "overdue": True, "due_soon": False})
    client = _client_as(db, employee, admin)
    body = client.get("/api/dashboard/overtime").json()
    assert any("MILOG_ACCOUNT_50" in w for w in body["milog_warnings"])
    assert any("MILOG_SETTLEMENT_DUE" in w for w in body["milog_warnings"])
    app.dependency_overrides.clear()


def test_settlement_aging_carries_deficit_overhang(db, employee, monkeypatch):
    # +5h (2025-01), −12h (2025-03) → Konto net −7h; +10h (2025-08) füllt erst das
    # Defizit (7h) auf, nur 3h bleiben gebankt (ab 2025-08), NICHT die vollen 10h.
    employee.milog_working_time_account = True
    db.commit()
    hist = {(2025, 1): _MO(0, 5), (2025, 3): _MO(12, 0), (2025, 8): _MO(0, 10)}
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: hist)
    res = milog_service.settlement_aging(db, employee, date(2026, 1, 1))
    assert res["oldest_year"] == 2025 and res["oldest_month"] == 8
    assert abs(res["hours"] - 3.0) < 0.01


def test_settlement_aging_incomplete_when_only_seed_carries(db, employee, monkeypatch):
    # Carryover 2026 = 4h offen, jung (Seed auf Dez 2025); as_of Feb 2026 → age 2,
    # nicht überfällig → incomplete (wahres Alter der gefalteten Historie unbekannt).
    employee.milog_working_time_account = True
    db.commit()
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, year=2026,
                         overtime_hours=Decimal("4"), vacation_days=Decimal("0")))
    db.commit()
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: {(2026, 1): _MO(0, 0)})
    res = milog_service.settlement_aging(db, employee, date(2026, 2, 1))
    assert res["incomplete"] is True and res["overdue"] is False
    assert "nicht vollständig" in milog_service.settlement_warning_text(res)


def test_settlement_aging_ignores_agreed_monthly(db, employee, monkeypatch):
    # #377 Baustein 2a (Review-Entscheid): das 12-Monats-Aging bleibt SOLL-basiert
    # und ignoriert agreed_monthly_hours — die vereinbarte Monatszahl steuert nur
    # die 50-%-Prüfung, NICHT die Konto-Akkumulation (Ist − tatsächliches Monats-
    # Soll; neutralisiert Urlaub/Feiertage/Teilmonate/Stichtag korrekt).
    employee.milog_working_time_account = True
    employee.agreed_monthly_hours = Decimal("40")  # darf das Aging NICHT beeinflussen
    db.commit()
    # Soll-basiert: _MO(target, actual) → delta = actual − target. _MO(0, 10) → +10.
    # (agreed-basiert wäre 10 − 40 = −30 → None.)
    hist = {(2025, 1): _MO(0, 10)}
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: hist)
    res = milog_service.settlement_aging(db, employee, date(2026, 3, 1))
    assert res is not None and abs(res["hours"] - 10.0) < 0.01  # target-basiert, agreed ignoriert



def test_settlement_aging_real_history(db, employee):
    # Ohne Monkeypatch: echte get_overtime_history_detailed-Integration + echter,
    # tenant-gefilterter YearCarryover-Query. Ein großer Alt-Carryover (100h) und
    # last_work_day direkt nach dem Seed-Monat, damit kein späterer Monats-Soll den
    # Bestand aufzehrt → der geseedete Alt-Bestand bleibt sichtbar + überfällig.
    from datetime import time as _time
    from app.models import TimeEntry
    employee.milog_working_time_account = True
    employee.first_work_day = date(2024, 1, 1)
    employee.last_work_day = date(2024, 1, 15)
    db.commit()
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, year=2024,
                         overtime_hours=Decimal("100"), vacation_days=Decimal("0")))
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, date=date(2024, 1, 10),
                     start_time=_time(8, 0), end_time=_time(12, 0), break_minutes=0))
    db.commit()
    res = milog_service.settlement_aging(db, employee, date(2026, 6, 1))
    assert res is not None
    assert res["oldest_year"] == 2023 and res["oldest_month"] == 12  # Seed = Dez Vorjahr
    assert res["overdue"] is True and res["hours"] > 50  # ~30 Monate alt, kaum aufgezehrt


def test_settlement_aging_full_current_month_soll_eats_seed(db, employee, monkeypatch):
    """#377 Regression (admin-overview Stichtag): der LAUFENDE (unvollständige)
    Monat darf NICHT mit vollem Monats-Soll gegen einen nur monats-bis-heute-Ist
    ins Aging fließen — das fabriziert ein Phantom-Defizit, das im FIFO die
    älteste überfällige Einlage aufzehrt und MILOG_SETTLEMENT_DUE unterdrückt.
    Der Stichtag-getrimmte Detail-Pass (aktueller Monat ~0) erhält den Bestand."""
    employee.milog_working_time_account = True
    db.commit()
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, year=2025,
                         overtime_hours=Decimal("8"), vacation_days=Decimal("0")))
    db.commit()
    # OHNE Stichtag: laufender Monat (2026,6) trägt volles Soll (40h) gegen 0 Ist
    # → −40 → verzehrt den 8h-Seed komplett → deposits leer → None (Warnung weg).
    monkeypatch.setattr(milog_service.calculation_service, "get_overtime_history_detailed",
                        lambda *a, **k: {(2026, 6): _MO(40, 0)})
    assert milog_service.settlement_aging(db, employee, date(2026, 6, 15)) is None
    # MIT Stichtag: laufender Monat auf monats-bis-heute getrimmt (~0 Soll) → Seed
    # überlebt, sichtbar + überfällig.
    monkeypatch.setattr(milog_service.calculation_service, "get_overtime_history_detailed",
                        lambda *a, **k: {(2026, 6): _MO(0, 0)})
    res = milog_service.settlement_aging(db, employee, date(2026, 6, 15))
    assert res is not None and res["overdue"] is True and abs(res["hours"] - 8.0) < 0.01


def test_settlement_aging_direct_call_applies_313_cutoff(db, employee):
    """FINDING 8 (review 2026-07-14): a DIRECT ``settlement_aging`` call (no
    ``detailed`` passed by the caller) must apply the #313 Saldo-Stichtag
    itself — otherwise the running, unfinished month is compared against a
    FULL month-Soll while only month-to-date Ist exists, fabricating a phantom
    deficit that eats the FIFO seed and silently drops MILOG_SETTLEMENT_DUE.
    Real integration (NO monkeypatch of get_overtime_history_detailed): the
    employee is only employed from 2026-06-01, has an 8h carryover seed
    (year=2025 → dated 2024-12, age 18 months → overdue), and has clocked
    exactly the daily target on every workday from 2026-06-01 up to (but not
    including) 2026-06-15 — i.e. Soll==Ist up to the #313 cutoff (2026-06-14).
    Without the cutoff, the FULL June Soll (through 06-30) is compared against
    the partial Ist → a deficit > 8h wipes the seed → None.
    """
    from datetime import time as _time, timedelta
    from app.models import TimeEntry

    employee.milog_working_time_account = True
    employee.weekly_hours = Decimal("40")
    employee.work_days_per_week = 5
    employee.first_work_day = date(2026, 6, 1)
    db.commit()
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, year=2025,
                         overtime_hours=Decimal("8"), vacation_days=Decimal("0")))
    d = date(2026, 6, 1)
    while d < date(2026, 6, 15):
        if d.weekday() < 5:
            db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, date=d,
                             start_time=_time(8, 0), end_time=_time(16, 0), break_minutes=0))
        d += timedelta(days=1)
    db.commit()

    res = milog_service.settlement_aging(db, employee, date(2026, 6, 15))
    assert res is not None, "phantom deficit from the untrimmed running month ate the FIFO seed"
    assert res["overdue"] is True
    assert abs(res["hours"] - 8.0) < 0.01


def test_users_overview_feeds_settlement_cutoff_trimmed_detail(db, admin, employee, monkeypatch):
    """#377 Regression: die Admin-Benutzerübersicht MUSS get_overtime_history_detailed
    MIT dem Saldo-Stichtag aufrufen (Parität zum MA-Dashboard, #313). Ohne cutoff
    verschwindet die MILOG_SETTLEMENT_DUE-Warnung des laufenden Monats aus der
    compliance-relevanten Arbeitgeber-Ansicht."""
    from app.services import calculation_service
    employee.milog_working_time_account = True
    db.commit()
    captured = {}

    def _spy(db_, u, y, m, **kwargs):
        if u.id == employee.id:
            captured["cutoff_date"] = kwargs.get("cutoff_date", "MISSING")
        return {(2025, 1): _MO(0, 0)}

    monkeypatch.setattr(calculation_service, "get_overtime_history_detailed", _spy)
    client = _client_as(db, admin, admin)
    client.get(f"{USERS}-overview")
    expected = calculation_service.get_soll_cutoff_date(db, employee)
    assert captured.get("cutoff_date") == expected  # Stichtag durchgereicht
    assert captured["cutoff_date"] is not None       # im laufenden Jahr nie None
    app.dependency_overrides.clear()


def test_create_time_entry_emits_milog_for_flagged_user(db, admin, employee, monkeypatch):
    from app.services.timezone_service import today_local
    employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    client = _client_as(db, employee, admin)
    today = today_local().isoformat()
    r = client.post("/api/time-entries/", json={
        "date": today, "start_time": "09:00", "end_time": "12:00", "break_minutes": 0})
    assert r.status_code == 201, r.text
    assert any("MILOG_ACCOUNT_50" in w for w in r.json().get("warnings", []))
    app.dependency_overrides.clear()


def test_clock_out_emits_milog_for_flagged_user(db, admin, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    client = _client_as(db, employee, admin)
    ci = client.post("/api/time-entries/clock-in", json={})
    assert ci.status_code == 201, ci.text
    co = client.post("/api/time-entries/clock-out", json={"break_minutes": 0})
    assert co.status_code == 200, co.text
    assert any("MILOG_ACCOUNT_50" in w for w in co.json().get("warnings", []))
    app.dependency_overrides.clear()


def test_update_time_entry_emits_milog_for_flagged_user(db, admin, employee, monkeypatch):
    from app.services.timezone_service import today_local
    employee.milog_working_time_account = True
    db.commit()
    client = _client_as(db, employee, admin)
    today = today_local().isoformat()
    created = client.post("/api/time-entries/", json={
        "date": today, "start_time": "09:00", "end_time": "12:00", "break_minutes": 0})
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5,
                                         "agreed_monthly": 33.0, "caveat": "x"})
    upd = client.put(f"/api/time-entries/{eid}", json={"end_time": "13:00"})
    assert upd.status_code == 200, upd.text
    assert any("MILOG_ACCOUNT_50" in w for w in upd.json().get("warnings", []))
    app.dependency_overrides.clear()


def test_users_overview_settlement_warning_branch(db, admin, employee, monkeypatch):
    employee.milog_working_time_account = True
    db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check", lambda *a, **k: None)
    # get_overtime_history_detailed muss non-empty sein, sonst wird der Block geskippt
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: {(2025, 1): _MO(0, 0)})
    monkeypatch.setattr("app.services.milog_service.settlement_aging",
                        lambda *a, **k: {"oldest_year": 2024, "oldest_month": 1, "age_months": 20,
                                         "hours": 9.0, "overdue": True, "due_soon": False,
                                         "incomplete": False})
    client = _client_as(db, admin, admin)
    row = next(r for r in client.get(f"{USERS}-overview").json() if r["user_id"] == str(employee.id))
    assert any("MILOG_SETTLEMENT_DUE" in w for w in row["milog_warnings"])
    # Nicht fällig (overdue/due_soon/incomplete alle False) → keine Settlement-Warnung
    monkeypatch.setattr("app.services.milog_service.settlement_aging",
                        lambda *a, **k: {"oldest_year": 2025, "oldest_month": 12, "age_months": 2,
                                         "hours": 3.0, "overdue": False, "due_soon": False,
                                         "incomplete": False})
    row2 = next(r for r in client.get(f"{USERS}-overview").json() if r["user_id"] == str(employee.id))
    assert not any("MILOG_SETTLEMENT_DUE" in w for w in row2["milog_warnings"])
    app.dependency_overrides.clear()


def test_agreed_monthly_hours_survives_create_and_list(db, admin):
    # #377 Baustein 2a: das Feld muss in UserCreate UND UserListResponse leben,
    # sonst Edit-Reset (wie #376/#377 latente Bugs).
    client = _client_as(db, admin, admin)
    r = client.post(f"{USERS}", json={
        "username": "mj_monthly", "first_name": "M", "last_name": "J",
        "role": "employee", "weekly_hours": 20.0, "vacation_days": 30,
        "work_days_per_week": 5, "password": "MonthlyPass2025!",
        "milog_working_time_account": True, "agreed_monthly_hours": 33,
    })
    assert r.status_code == 201, r.text
    rows = client.get(f"{USERS}").json()
    row = next(u for u in rows if u["username"] == "mj_monthly")
    assert row["agreed_monthly_hours"] == 33.0  # in der Liste → kein Edit-Reset
    app.dependency_overrides.clear()
