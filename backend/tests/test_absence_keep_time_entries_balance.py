"""F1 (Release-Gate 1.18.0): Abwesenheit + behaltener Zeiteintrag am selben Tag
darf keinen Phantom-Saldo erzeugen.

Der „+"-Knopf im Monatsjournal schickt ``keep_time_entries=true``, sobald am
Zieltag schon ein Zeiteintrag liegt, und nie ``half_day``. Bisher bekam die
Abwesenheit trotzdem das VOLLE Tagessoll:

* **SICK/TRAINING** (nicht soll-reduzierend, ``hours`` werden dem Ist
  gutgeschrieben): Ist = gearbeitete Stunden + volles Tagessoll → 8 h Soll,
  4 h gearbeitet ⇒ Ist 12 h ⇒ **+4 h Phantom-Überstunden**.
* **OTHER/PAID_LEAVE/VACATION** (soll-reduzierend): das ganze Tagessoll fiel
  weg, die gearbeiteten Stunden blieben im Ist ⇒ ebenfalls **+4 h**.

Fix (zwei Hälften, beide hier über die volle Kette geprüft):

1. ``absences.create_absence`` klemmt die Stunden auf
   ``max(0, Tagessoll − erfasste Netto-Stunden des Tages)``, wenn am Zieltag
   ein Zeiteintrag bestehen bleibt.
2. ``calculation_service._day_soll_contribution`` streicht bei einer
   GANZTÄGIGEN soll-reduzierenden Abwesenheit nur noch den NICHT gearbeiteten
   Teil des Tages (``min(Tagessoll, gearbeitete Stunden)`` bleibt stehen).

Der Halbtagsfall (``half_day=True``, festgeschrieben in
``test_fix1_half_day_target.py``) bleibt unangetastet — er läuft weiter über
den ``half is True``-Zweig.
"""

import pytest
from datetime import date, time
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TimeEntry, Absence, AbsenceType
from app.models.tenant import Tenant
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

# 2026-03-09 = Montag … 2026-03-13 = Freitag (Woche ohne Feiertage)
MON, TUE, FRI = date(2026, 3, 9), date(2026, 3, 10), date(2026, 3, 13)


def _create_test_app() -> FastAPI:
    from app.routers import absences

    app = FastAPI(title="PraxisZeit F1 Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    return app


_app = _create_test_app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def default_tenant(db):
    tenant = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default",
                    is_active=True, mode="single")
    db.add(tenant)
    db.commit()
    return tenant


def _user(db, username, role):
    from app.services import auth_service
    u = User(
        username=username, email=f"{username}@example.com",
        password_hash=auth_service.hash_password("test123"),
        first_name="Test", last_name=username,
        role=role, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def employee(db, default_tenant):
    return _user(db, "emp1", UserRole.EMPLOYEE)


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "admin1", UserRole.ADMIN)


@pytest.fixture
def admin_client(db, admin):
    def override_db():
        yield db

    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: admin
    _app.dependency_overrides[require_admin] = lambda: admin
    yield TestClient(_app)
    _app.dependency_overrides.clear()


def _entry(db, user, d, start_h, end_h, break_min=0):
    e = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=time(start_h, 0), end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(e)
    db.commit()
    return e


def _post_absence(client, user, d, atype, **extra):
    payload = {
        "user_id": str(user.id),
        "date": d.isoformat(),
        "type": atype,
        "hours": 8.0,          # Journal-Default; serverseitig überschrieben
        "keep_time_entries": True,
    }
    payload.update(extra)
    resp = client.post("/api/absences/", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body[0] if isinstance(body, list) else body


def _balance(db, user, d=MON):
    target = calculation_service.get_range_target(db, user, d, d)
    actual = calculation_service.get_range_actual(db, user, d, d)
    return target, actual


# ---------------------------------------------------------------------------
# Der gemeldete Fehlerfall — beide Zweige
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("atype", ["sick", "training"])
def test_credited_absence_with_kept_entry_has_zero_balance(
        db, employee, admin_client, atype):
    """Ist-gutgeschriebener Typ: 8 h Soll, 08–12 gearbeitet, Ganztags-Buchung
    mit keep_time_entries ⇒ Soll 8 / Ist 8 (vorher Ist 12 → +4 h)."""
    _entry(db, employee, MON, 8, 12)  # 4 h
    body = _post_absence(admin_client, employee, MON, atype)

    assert float(body["hours"]) == 4.0, body["hours"]
    target, actual = _balance(db, employee)
    assert target == Decimal('8.00'), target
    assert actual == Decimal('8.00'), actual
    assert actual - target == Decimal('0.00')


@pytest.mark.parametrize("atype", ["other", "paid_leave", "vacation"])
def test_soll_reducing_absence_with_kept_entry_has_zero_balance(
        db, employee, admin_client, atype):
    """Soll-reduzierender Typ: die Abwesenheit streicht nur den NICHT
    gearbeiteten Teil ⇒ Soll 4 / Ist 4 (vorher Soll 0 / Ist 4 → +4 h)."""
    _entry(db, employee, MON, 8, 12)  # 4 h
    body = _post_absence(admin_client, employee, MON, atype)

    assert float(body["hours"]) == 4.0, body["hours"]
    target, actual = _balance(db, employee)
    assert target == Decimal('4.00'), target
    assert actual == Decimal('4.00'), actual
    assert actual - target == Decimal('0.00')


def test_kept_entry_longer_than_target_keeps_full_soll(db, employee, admin_client):
    """10 h gearbeitet, danach Ganztags-Urlaub mit keep_time_entries: die
    Abwesenheit streicht nichts mehr (Soll 8), das Mehr bleibt Überstunde."""
    _entry(db, employee, MON, 7, 17)  # 10 h
    body = _post_absence(admin_client, employee, MON, "vacation")

    assert float(body["hours"]) == 0.0, body["hours"]
    target, actual = _balance(db, employee)
    assert target == Decimal('8.00'), target
    assert actual == Decimal('10.00'), actual


def test_phantom_balance_gone_in_overtime_account(db, employee, admin_client):
    """Parallelpfad Überstundenkonto: Mo Misch-Tag, Di–Fr regulär ⇒ Saldo 0."""
    _entry(db, employee, MON, 8, 12)
    for d in (TUE, date(2026, 3, 11), date(2026, 3, 12), FRI):
        _entry(db, employee, d, 8, 16)
    _post_absence(admin_client, employee, MON, "paid_leave")

    target = calculation_service.get_range_target(db, employee, MON, FRI)
    actual = calculation_service.get_range_actual(db, employee, MON, FRI)
    assert target == Decimal('36.00'), target
    assert actual == Decimal('36.00'), actual


# ---------------------------------------------------------------------------
# Kontrolltests: ohne die Konstellation ändert sich NICHTS (Byte-Identität)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("atype,exp_target,exp_actual", [
    ("sick", Decimal('8.00'), Decimal('8.00')),
    ("training", Decimal('8.00'), Decimal('8.00')),
    ("vacation", Decimal('0.00'), Decimal('0.00')),
    ("paid_leave", Decimal('0.00'), Decimal('0.00')),
    ("other", Decimal('0.00'), Decimal('0.00')),
])
def test_control_no_time_entry_unchanged(db, employee, admin_client,
                                         atype, exp_target, exp_actual):
    """Kein Zeiteintrag am Tag ⇒ volles Tagessoll als Abwesenheitsstunden und
    die bisherige Soll-Behandlung — unverändert."""
    body = _post_absence(admin_client, employee, MON, atype)
    assert float(body["hours"]) == 8.0, body["hours"]
    target, actual = _balance(db, employee)
    assert target == exp_target, target
    assert actual == exp_actual, actual


def test_control_half_day_with_morning_work_unchanged(db, employee, admin_client):
    """Der gewollte Halbtagsfall (½ Urlaub vormittags, nachmittags gearbeitet)
    bleibt exakt wie in test_fix1_half_day_target.py: Soll 4 / Ist 4."""
    _entry(db, employee, MON, 8, 12)  # 4 h
    body = _post_absence(admin_client, employee, MON, "vacation", half_day=True)

    assert float(body["hours"]) == 4.0, body["hours"]
    target, actual = _balance(db, employee)
    assert target == Decimal('4.00'), target
    assert actual == Decimal('4.00'), actual


def test_control_legacy_full_day_absence_without_entry(db, employee):
    """Bestandsdaten: Ganztags-Abwesenheit mit „krummen" Stunden und OHNE
    Zeiteintrag streicht weiterhin das ganze Tagessoll (kein Rest-Soll)."""
    db.add(Absence(user_id=employee.id, tenant_id=DEFAULT_TENANT_ID, date=MON,
                   type=AbsenceType.VACATION, hours=4.0, half_day=False))
    db.commit()
    target, _ = _balance(db, employee)
    assert target == Decimal('0.00'), target


def test_control_default_delete_path_unchanged(db, employee, admin_client):
    """Ohne keep_time_entries wird der Zeiteintrag wie bisher gelöscht und die
    Abwesenheit bekommt das volle Tagessoll."""
    _entry(db, employee, MON, 8, 12)
    resp = admin_client.post("/api/absences/", json={
        "user_id": str(employee.id), "date": MON.isoformat(),
        "type": "sick", "hours": 8.0,
    })
    assert resp.status_code == 201, resp.text
    assert float(resp.json()[0]["hours"]) == 8.0
    assert db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).count() == 0
    target, actual = _balance(db, employee)
    assert target == Decimal('8.00')
    assert actual == Decimal('8.00')
