"""Teil B Task 7: Admin-CRUD ``/api/admin/reduced-days`` mit automatischem
Neubuchen der Betriebsferien (``company_closures.resave_closures_for_dates``).

Rosenmontag 16.02.2026 (Montag) in einer Schließung 14.–20.02.2026 — ohne
Feiertage im Testmandanten sind 16.–20.02. Arbeitstage (8 h bei 40 h/Woche).
"""

import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    Absence, AbsenceType, CompanyClosure, ReducedDay, TimeEntry, TimeEntryAuditLog,
    User, UserRole,
)
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.year_carryover import YearCarryover
from tests.conftest import DEFAULT_TENANT_ID, TestingSessionLocal, engine

OTHER_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000fe")

RM = date(2026, 2, 16)
TUE = date(2026, 2, 17)
REBOOK_REASON = "Sondertag oder verkürzter Tag geändert, wird neu gebucht"


def _create_test_app() -> FastAPI:
    from app.routers import company_closures, reduced_days

    app = FastAPI(title="PraxisZeit Reduced Days Test")
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(company_closures.router)
    app.include_router(reduced_days.router)
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


def _make_tenant(db, tenant_id, slug):
    db.add(Tenant(id=tenant_id, name=slug.capitalize(), slug=slug, is_active=True, mode="single"))
    db.commit()


def _make_user(db, tenant_id, username, role=UserRole.EMPLOYEE, **kw):
    from app.services import auth_service
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=auth_service.hash_password("test123"),
        first_name=username,
        last_name="Test",
        role=role,
        weekly_hours=40.0,
        vacation_days=kw.pop("vacation_days", 30),
        work_days_per_week=5,
        is_active=True,
        tenant_id=tenant_id,
        **kw,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin(db):
    _make_tenant(db, DEFAULT_TENANT_ID, "default")
    # Der Admin nimmt nicht an Betriebsferien teil (übersichtlichere Zählungen).
    return _make_user(db, DEFAULT_TENANT_ID, "admin1", role=UserRole.ADMIN,
                      receives_company_closures=False)


@pytest.fixture
def employee(db, admin):
    return _make_user(db, DEFAULT_TENANT_ID, "emp1")


@pytest.fixture
def client(db, admin):
    def override_db():
        yield db

    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: admin
    _app.dependency_overrides[require_admin] = lambda: admin
    yield TestClient(_app)
    _app.dependency_overrides.clear()


def _closure(client, start=date(2026, 2, 14), end=date(2026, 2, 20), name="Fasching"):
    resp = client.post("/api/company-closures/", json={
        "name": name, "start_date": start.isoformat(), "end_date": end.isoformat(),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post_rm(client, d=RM, hours=4, label="Rosenmontag"):
    return client.post("/api/admin/reduced-days/", json={
        "date": d.isoformat(), "label": label, "max_hours": hours,
    })


def _row(db, user, d):
    db.expire_all()
    return db.query(Absence).filter(Absence.user_id == user.id, Absence.date == d).first()


def _booking_set(db):
    db.expire_all()
    return {
        (a.user_id, a.date, a.type, float(a.hours), a.closure_id)
        for a in db.query(Absence).all()
    }


def _audit_count(db):
    db.expire_all()
    return db.query(TimeEntryAuditLog).count()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def test_create_list_update_delete(client, db):
    resp = _post_rm(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["max_hours"] == 4.0
    assert body["label"] == "Rosenmontag"
    assert body["date"] == "2026-02-16"
    assert body["warning"] is None
    rid = body["id"]

    lst = client.get("/api/admin/reduced-days/?year=2026")
    assert lst.status_code == 200
    assert [r["id"] for r in lst.json()] == [rid]
    assert client.get("/api/admin/reduced-days/?year=2025").json() == []

    put = client.put(f"/api/admin/reduced-days/{rid}", json={
        "date": "2026-02-16", "label": "Rosenmontag", "max_hours": 5,
    })
    assert put.status_code == 200, put.text
    assert put.json()["max_hours"] == 5.0

    dele = client.delete(f"/api/admin/reduced-days/{rid}")
    assert dele.status_code == 204, dele.text
    db.expire_all()
    assert db.query(ReducedDay).count() == 0


def test_list_sorted_by_date(client):
    assert _post_rm(client, d=date(2026, 3, 2), label="B").status_code == 201
    assert _post_rm(client, d=date(2026, 1, 5), label="A").status_code == 201
    dates = [r["date"] for r in client.get("/api/admin/reduced-days/?year=2026").json()]
    assert dates == ["2026-01-05", "2026-03-02"]


@pytest.mark.parametrize("d", ["2026-12-24", "2026-12-31"])
def test_dec24_dec31_rejected(client, d):
    resp = client.post("/api/admin/reduced-days/", json={"date": d, "label": "X", "max_hours": 4})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden."
    ok = _post_rm(client)
    put = client.put(f"/api/admin/reduced-days/{ok.json()['id']}", json={
        "date": d, "label": "X", "max_hours": 4,
    })
    assert put.status_code == 400
    assert put.json()["detail"] == "Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden."


def test_duplicate_409(client):
    assert _post_rm(client).status_code == 201
    resp = _post_rm(client, label="Nochmal")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Für dieses Datum ist bereits ein verkürzter Tag eingetragen."
    # PUT auf ein bereits belegtes Datum
    other = _post_rm(client, d=TUE, label="Faschingsdienstag").json()
    put = client.put(f"/api/admin/reduced-days/{other['id']}", json={
        "date": RM.isoformat(), "label": "x", "max_hours": 4,
    })
    assert put.status_code == 409
    assert put.json()["detail"] == "Für dieses Datum ist bereits ein verkürzter Tag eingetragen."


def test_duplicate_integrity_error_path_409(client, db, monkeypatch):
    """Rennen: die Vorabprüfung sieht nichts, das UNIQUE greift → 409, kein 500."""
    from app.routers import reduced_days
    assert _post_rm(client).status_code == 201
    monkeypatch.setattr(reduced_days, "_date_taken", lambda *a, **k: False)
    resp = _post_rm(client, label="Rennen")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Für dieses Datum ist bereits ein verkürzter Tag eingetragen."
    db.expire_all()
    assert db.query(ReducedDay).count() == 1


@pytest.mark.parametrize("h", [0, 0.2, 12.25, 4.3])
def test_hours_validation_422(client, h):
    resp = _post_rm(client, hours=h)
    assert resp.status_code == 422
    assert "Die Stundenzahl muss zwischen 0,25 und 12 liegen (in Schritten von 0,25)." in resp.text


@pytest.mark.parametrize("h", [0.25, 12])
def test_hours_bounds_accepted(client, h):
    resp = _post_rm(client, hours=h)
    assert resp.status_code == 201, resp.text
    assert resp.json()["max_hours"] == float(h)


def test_label_blank_422(client):
    assert _post_rm(client, label="   ").status_code == 422
    assert _post_rm(client, label="x" * 101).status_code == 422


def test_foreign_tenant_404(client, db):
    _make_tenant(db, OTHER_TENANT_ID, "other")
    foreign = ReducedDay(tenant_id=OTHER_TENANT_ID, date=RM, label="Fremd", max_hours=Decimal("4"))
    db.add(foreign)
    db.commit()

    put = client.put(f"/api/admin/reduced-days/{foreign.id}", json={
        "date": RM.isoformat(), "label": "x", "max_hours": 4,
    })
    assert put.status_code == 404
    assert put.json()["detail"] == "Verkürzter Tag nicht gefunden"
    dele = client.delete(f"/api/admin/reduced-days/{foreign.id}")
    assert dele.status_code == 404
    assert dele.json()["detail"] == "Verkürzter Tag nicht gefunden"
    assert client.get("/api/admin/reduced-days/?year=2026").json() == []
    # Gleiches Datum im eigenen Mandanten bleibt frei (UNIQUE je Mandant).
    assert _post_rm(client).status_code == 201
    assert client.delete(f"/api/admin/reduced-days/{uuid.uuid4()}").status_code == 404


# ---------------------------------------------------------------------------
# Betriebsferien neu buchen
# ---------------------------------------------------------------------------

def test_create_resaves_existing_closure(client, db, employee):
    from app.services import calculation_service
    _closure(client)
    assert float(_row(db, employee, RM).hours) == 8.0
    used_before = calculation_service.get_vacation_account(db, employee, 2026)["used_days"]
    audits_before = _audit_count(db)

    resp = _post_rm(client)
    assert resp.status_code == 201, resp.text
    assert resp.json()["warning"] is None

    row = _row(db, employee, RM)
    assert float(row.hours) == 4.0
    assert row.half_day is False
    assert row.type == AbsenceType.VACATION
    assert float(_row(db, employee, TUE).hours) == 8.0
    used_after = calculation_service.get_vacation_account(db, employee, 2026)["used_days"]
    assert float(used_before) - float(used_after) == pytest.approx(0.5)

    db.expire_all()
    audits = db.query(TimeEntryAuditLog).all()
    assert len(audits) == audits_before + 1
    assert any(REBOOK_REASON in (a.old_note or "") for a in audits)


def test_move_date_rebooks_both(client, db, employee):
    _closure(client)
    rid = _post_rm(client).json()["id"]
    assert float(_row(db, employee, RM).hours) == 4.0

    put = client.put(f"/api/admin/reduced-days/{rid}", json={
        "date": TUE.isoformat(), "label": "Faschingsdienstag", "max_hours": 4,
    })
    assert put.status_code == 200, put.text
    assert float(_row(db, employee, RM).hours) == 8.0
    assert float(_row(db, employee, TUE).hours) == 4.0


def test_label_only_is_noop(client, db, employee):
    _closure(client)
    rid = _post_rm(client).json()["id"]
    before = _booking_set(db)
    audits = _audit_count(db)

    put = client.put(f"/api/admin/reduced-days/{rid}", json={
        "date": RM.isoformat(), "label": "Rosenmontag (Karneval)", "max_hours": 4,
    })
    assert put.status_code == 200, put.text
    assert put.json()["warning"] is None
    assert put.json()["label"] == "Rosenmontag (Karneval)"
    assert _booking_set(db) == before
    assert _audit_count(db) == audits


def test_delete_restores_full_target(client, db, employee):
    _closure(client)
    rid = _post_rm(client).json()["id"]
    assert float(_row(db, employee, RM).hours) == 4.0
    assert client.delete(f"/api/admin/reduced-days/{rid}").status_code == 204
    assert float(_row(db, employee, RM).hours) == 8.0


def test_resave_respects_worked_day(client, db, employee):
    emp2 = _make_user(db, DEFAULT_TENANT_ID, "emp2")
    _closure(client)
    # emp1: Closure-Zeile UND Arbeitszeit am 16.02. → nichts wird gelöscht.
    # emp2: nur Arbeitszeit (Closure-Zeile entfernt) → nichts wird gebucht.
    db.delete(_row(db, emp2, RM))
    for u in (employee, emp2):
        db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=RM,
                         start_time=time(8, 0), end_time=time(12, 0), break_minutes=0))
    db.commit()

    assert _post_rm(client).status_code == 201
    assert float(_row(db, employee, RM).hours) == 8.0
    assert _row(db, emp2, RM) is None
    db.expire_all()
    assert db.query(TimeEntry).filter(TimeEntry.date == RM).count() == 2


def test_resave_keeps_rows_of_former_participants(client, db, employee):
    gone = _make_user(db, DEFAULT_TENANT_ID, "gone")
    _closure(client)
    gone.is_active = False
    db.commit()

    assert _post_rm(client).status_code == 201
    assert float(_row(db, gone, RM).hours) == 8.0
    assert float(_row(db, employee, RM).hours) == 4.0


def test_resave_runs_314_split(client, db, admin):
    from app.services.closure_split_service import resplit_year_closures
    emp = _make_user(db, DEFAULT_TENANT_ID, "lowbudget", vacation_days=1)
    db.add(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID, value="true"))
    db.commit()
    _closure(client)

    assert _post_rm(client).status_code == 201
    db.expire_all()
    rows = {a.date: a for a in db.query(Absence).filter(Absence.user_id == emp.id).all()}
    types_after_post = {d: a.type for d, a in rows.items()}
    # Budget 1 Tag: nur der 16.02. (verkürzt, 0,5 Tage) ist Urlaub; der 17.02. kostet
    # einen ganzen Tag (Rest 0,5 < 1) → Überstundenausgleich, ebenso 18.–20.02.
    assert types_after_post == {
        RM: AbsenceType.VACATION,
        **{date(2026, 2, d): AbsenceType.OVERTIME for d in (17, 18, 19, 20)},
    }
    assert float(rows[RM].hours) == 4.0

    resplit_year_closures(db, DEFAULT_TENANT_ID, 2026, admin)
    db.flush()
    db.expire_all()
    assert {
        a.date: a.type for a in db.query(Absence).filter(Absence.user_id == emp.id).all()
    } == types_after_post
    db.rollback()


def test_closed_year_warns_without_resave(client, db, employee):
    _closure(client, start=date(2025, 12, 22), end=date(2025, 12, 30), name="Winter")
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=employee.id, year=2026,
                         overtime_hours=0, vacation_days=0, source="year_closing"))
    db.commit()
    before = _booking_set(db)
    assert float(_row(db, employee, date(2025, 12, 29)).hours) == 8.0

    resp = _post_rm(client, d=date(2025, 12, 29), label="Brückentag")
    assert resp.status_code == 201, resp.text
    assert "2025" in (resp.json()["warning"] or "")
    assert _booking_set(db) == before


def test_atomic_on_resave_error(client, db, employee, monkeypatch):
    from app.routers import company_closures
    _closure(client)
    before = _booking_set(db)

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(company_closures, "_create_closure_absences", boom)
    with pytest.raises(RuntimeError):
        _post_rm(client)
    db.rollback()
    assert db.query(ReducedDay).count() == 0
    assert _booking_set(db) == before


def test_closure_years(db, admin):
    from app.routers.company_closures import closure_years
    db.add_all([
        CompanyClosure(name="A", start_date=date(2025, 12, 29), end_date=date(2026, 1, 2),
                       created_by=admin.id, tenant_id=DEFAULT_TENANT_ID),
        CompanyClosure(name="B", start_date=date(2028, 5, 1), end_date=date(2028, 5, 3),
                       created_by=admin.id, tenant_id=DEFAULT_TENANT_ID),
    ])
    _make_tenant(db, OTHER_TENANT_ID, "other")
    other_admin = _make_user(db, OTHER_TENANT_ID, "oadmin", role=UserRole.ADMIN)
    db.add(CompanyClosure(name="X", start_date=date(2030, 1, 1), end_date=date(2030, 1, 2),
                          created_by=other_admin.id, tenant_id=OTHER_TENANT_ID))
    db.commit()
    assert closure_years(db, DEFAULT_TENANT_ID) == {2025, 2026, 2028}


@pytest.mark.parametrize("d", ["0202-02-12", "1999-12-30", "2101-01-02"])
def test_implausible_date_422(client, d):
    """F027/F104: Tippfehler-Datum außerhalb 2000–2100 → deutsche 422."""
    r = client.post("/api/admin/reduced-days/",
                    json={"date": d, "label": "X", "max_hours": 4})
    assert r.status_code == 422, r.text
    assert "01.01.2000" in r.text


def test_list_without_year_is_limited(client):
    """F128: ohne Jahresfilter begrenzt ``limit`` die Antwort."""
    _post_rm(client)
    _post_rm(client, d=TUE, label="Dienstag")
    r = client.get("/api/admin/reduced-days/?limit=1")
    assert r.status_code == 200 and len(r.json()) == 1
    assert client.get("/api/admin/reduced-days/?limit=5000").status_code == 422


def test_unknown_id_404_on_update_and_delete(client):
    rid = str(uuid.uuid4())
    body = {"date": RM.isoformat(), "label": "X", "max_hours": 4}
    assert client.put(f"/api/admin/reduced-days/{rid}", json=body).status_code == 404
    assert client.delete(f"/api/admin/reduced-days/{rid}").status_code == 404


def test_is_settings_special_day():
    from app.services import special_days_service as sds
    assert sds.is_settings_special_day(date(2026, 12, 24))
    assert sds.is_settings_special_day(date(2030, 12, 31))
    assert not sds.is_settings_special_day(date(2026, 12, 25))
