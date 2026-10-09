"""#499 (Kundenmeldung): aneinandergereihte Zeiteinträge umgehen die §4-Pausenprüfung.

Gemeldet: 08:49–13:59 + 13:59–18:00 (9 h 11 min ohne Pause) und
08:58–13:51 + 14:12–18:03 (21 min Lücke bei 8 h 44 min Arbeit). Beide Tage
entstanden über das STEMPELN: der Ausstempel-Dialog prüfte nur den eben
laufenden Block (je < 6 h → kein Hinweis), und der Server meldete den
Tagesverstoß beim Ausstempeln nur als weiche Warnung — der Eintrag wurde
ohne Pause und ohne Begründung geschlossen.

§4 ArbZG: Pause ist eine Unterbrechung von mindestens 15 Minuten; eine
kürzere Lücke zwischen zwei Einträgen ist keine. Maßgeblich ist der ganze
Tag. Seit #499 lehnt deshalb auch das Ausstempeln einen §4-Verstoß ohne
dokumentierte Ausnahme ab (400) — wie jeder andere Schreibpfad.

Teil 2: Mandanten-Schalter ``break_exception_allowed`` (Default an). Aus →
die Ausnahme „Pflicht-Pause war nicht möglich" wird an allen Schreibpfaden
serverseitig abgelehnt (400 bzw. 422 bei der Genehmigung).
"""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    User, UserRole, TimeEntry,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.services import auth_service
from app.services.break_validation_service import validate_daily_break
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _create_test_app() -> FastAPI:
    from app.routers import (
        time_entries as te_router,
        change_requests,
        admin as admin_router,
    )

    app = FastAPI(title="PraxisZeit #499 Test")

    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(te_router.router)
    app.include_router(change_requests.router)
    app.include_router(admin_router.router)
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


@pytest.fixture(scope="function")
def default_tenant(db):
    tenant = Tenant(
        id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single",
    )
    db.add(tenant)
    db.commit()
    return tenant


def _user(db, username, role, exempt=False):
    u = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=auth_service.hash_password("test123"),
        first_name="Vor",
        last_name=username,
        role=role,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        exempt_from_arbzg=exempt,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def employee(db, default_tenant):
    return _user(db, "emp499", UserRole.EMPLOYEE)


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "adm499", UserRole.ADMIN)


@pytest.fixture
def client_as(db):
    """Ein Client; ``client_as(user)`` schaltet den angemeldeten Nutzer um."""
    def override_db():
        yield db

    _app.dependency_overrides[get_db] = override_db
    client = TestClient(_app)

    def _as(user):
        _app.dependency_overrides[get_current_user] = lambda: user
        _app.dependency_overrides[require_admin] = lambda: user
        return client

    yield _as
    _app.dependency_overrides.clear()


def _setting(db, key, value):
    db.add(SystemSetting(key=key, tenant_id=DEFAULT_TENANT_ID, value=value, description=key))
    db.commit()


def _disable_waiver(db):
    _setting(db, "break_exception_allowed", "false")


def _entry(db, user, d, start, end, brk=0):
    e = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=start, end_time=end, break_minutes=brk,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _freeze_now(monkeypatch, hh, mm):
    import app.routers.time_entries as te
    today = today_local()
    fixed = datetime(today.year, today.month, today.day, hh, mm, tzinfo=te.LOCAL_TZ)
    monkeypatch.setattr(te, "_now_local", lambda: fixed)
    monkeypatch.setattr(te, "_today_local", lambda: today)
    return today


def _open_after(db, employee, today, closed_start, closed_end, open_start):
    """Ein geschlossener Block plus ein laufender Block (Stempel-Situation)."""
    _entry(db, employee, today, closed_start, closed_end)
    return _entry(db, employee, today, open_start, None)


# ---------------------------------------------------------------------------
# Teil 1 — Stempeln: der Tag zählt, nicht der laufende Block
# ---------------------------------------------------------------------------

class TestClockOutChainedEntries:

    def test_kundenfall_nahtlos_ohne_pause_wird_abgelehnt(self, db, employee, client_as, monkeypatch):
        """08:49–13:59 + 13:59–18:00 = 9 h 11 min ohne Pause → 400, Eintrag bleibt offen."""
        today = _freeze_now(monkeypatch, 18, 0)
        open_entry = _open_after(db, employee, today, time(8, 49), time(13, 59), time(13, 59))

        resp = client_as(employee).post("/api/time-entries/clock-out", json={"break_minutes": 0})

        assert resp.status_code == 400, resp.text
        assert "45 Minuten" in resp.json()["detail"]
        db.expire_all()
        assert db.get(TimeEntry, open_entry.id).end_time is None

    def test_kundenfall_21_minuten_luecke_reicht_nicht(self, db, employee, client_as, monkeypatch):
        """08:58–13:51 + 14:12–18:03: 21 min Lücke bei 8 h 44 min Arbeit → 400 (30 min nötig)."""
        today = _freeze_now(monkeypatch, 18, 3)
        open_entry = _open_after(db, employee, today, time(8, 58), time(13, 51), time(14, 12))

        resp = client_as(employee).post("/api/time-entries/clock-out", json={"break_minutes": 0})

        assert resp.status_code == 400, resp.text
        assert "30 Minuten" in resp.json()["detail"]
        db.expire_all()
        assert db.get(TimeEntry, open_entry.id).end_time is None

    def test_luecke_unter_15_minuten_ist_keine_pause(self, db, employee, client_as, monkeypatch):
        """Eine Lücke von 10 min zwischen zwei Blöcken zählt nicht als Pause (§4 Satz 2)."""
        today = _freeze_now(monkeypatch, 15, 0)
        _open_after(db, employee, today, time(8, 0), time(12, 0), time(12, 10))

        resp = client_as(employee).post("/api/time-entries/clock-out", json={"break_minutes": 0})

        assert resp.status_code == 400, resp.text

    def test_mit_nachgetragener_pause_wird_geschlossen(self, db, employee, client_as, monkeypatch):
        """Gegenprobe: dieselbe Kette mit 45 min Pause → 200, Pause gespeichert."""
        today = _freeze_now(monkeypatch, 18, 0)
        open_entry = _open_after(db, employee, today, time(8, 49), time(13, 59), time(13, 59))

        resp = client_as(employee).post("/api/time-entries/clock-out", json={"break_minutes": 45})

        assert resp.status_code == 200, resp.text
        db.expire_all()
        e = db.get(TimeEntry, open_entry.id)
        assert e.end_time == time(18, 0)
        assert e.break_minutes == 45

    def test_mit_begruendung_wird_geschlossen_und_dokumentiert(self, db, employee, client_as, monkeypatch):
        """Ausnahme erlaubt (Default): Kette + Begründung → 200 mit BREAK_WAIVER."""
        today = _freeze_now(monkeypatch, 18, 0)
        open_entry = _open_after(db, employee, today, time(8, 49), time(13, 59), time(13, 59))

        resp = client_as(employee).post("/api/time-entries/clock-out", json={
            "break_minutes": 0, "break_waiver_reason": "Notfall, keine Vertretung",
        })

        assert resp.status_code == 200, resp.text
        assert any(w.startswith("BREAK_WAIVER") for w in resp.json()["warnings"])
        db.expire_all()
        assert db.get(TimeEntry, open_entry.id).break_waiver_reason == "Notfall, keine Vertretung"

    def test_kurzer_tag_bleibt_unberuehrt(self, db, employee, client_as, monkeypatch):
        """Regression: ein Tag unter 6 h braucht keine Pause — Ausstempeln wie bisher."""
        today = _freeze_now(monkeypatch, 13, 0)
        _open_after(db, employee, today, time(8, 0), time(10, 0), time(10, 0))

        resp = client_as(employee).post("/api/time-entries/clock-out", json={"break_minutes": 0})

        assert resp.status_code == 200, resp.text

    def test_befreite_mitarbeitende_werden_nicht_geprueft(self, db, client_as, default_tenant, monkeypatch):
        """§18 ArbZG: befreite MA stempeln auch ohne Pause aus."""
        boss = _user(db, "lead499", UserRole.EMPLOYEE, exempt=True)
        today = _freeze_now(monkeypatch, 18, 0)
        _open_after(db, boss, today, time(8, 0), time(13, 0), time(13, 0))

        resp = client_as(boss).post("/api/time-entries/clock-out", json={"break_minutes": 0})

        assert resp.status_code == 200, resp.text


class TestOtherWritePathsSeeTheWholeDay:
    """Absicherung: die übrigen Schreibpfade prüfen eine Kette bereits als Tag."""

    def test_manueller_eintrag_nahtlos_angehaengt(self, db, employee, client_as):
        today = today_local()
        _entry(db, employee, today, time(8, 0), time(13, 0))
        resp = client_as(employee).post("/api/time-entries/", json={
            "date": today.isoformat(), "start_time": "13:00", "end_time": "17:30", "break_minutes": 0,
        })
        assert resp.status_code == 400, resp.text

    def test_admin_eintrag_nahtlos_angehaengt(self, db, employee, admin, client_as):
        d = today_local() - timedelta(days=1)
        _entry(db, employee, d, time(8, 0), time(13, 0))
        resp = client_as(admin).post(f"/api/admin/users/{employee.id}/time-entries", json={
            "date": d.isoformat(), "start_time": "13:05", "end_time": "17:30", "break_minutes": 0,
        })
        assert resp.status_code == 400, resp.text

    def test_antrag_nahtlos_angehaengt(self, db, employee, client_as):
        d = today_local() - timedelta(days=7)
        _entry(db, employee, d, time(8, 0), time(13, 0))
        resp = client_as(employee).post("/api/change-requests/", json={
            "request_type": "create", "proposed_date": d.isoformat(),
            "proposed_start_time": "13:00", "proposed_end_time": "17:30",
            "proposed_break_minutes": 0, "reason": "vergessen",
        })
        assert resp.status_code == 400, resp.text


class TestValidateDailyBreakTenantFilter:
    """F-026: die Tagesabfrage filtert zusätzlich explizit nach Mandant."""

    def test_fremder_mandant_zaehlt_nicht(self, db, employee):
        d = date(2026, 3, 10)
        other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd", is_active=True, mode="single")
        db.add(other)
        db.commit()
        # Fehlerhaft zugeordnete Zeile: gleiche user_id, fremde tenant_id.
        stray = TimeEntry(
            user_id=employee.id, tenant_id=other.id, date=d,
            start_time=time(8, 0), end_time=time(14, 0), break_minutes=0,
        )
        db.add(stray)
        db.commit()

        result = validate_daily_break(
            db, employee, d, time(14, 0), time(15, 0), 0,
            uncredited_segments=[], tenant_id=DEFAULT_TENANT_ID,
        )

        assert result is None


# ---------------------------------------------------------------------------
# Teil 2 — Schalter „Pflicht-Pause war nicht möglich" abschaltbar
# ---------------------------------------------------------------------------

_OVER_6H = {"start_time": "08:00", "end_time": "15:30", "break_minutes": 0}


class TestBreakExceptionSetting:

    def test_admin_kann_schalter_setzen(self, db, admin, client_as):
        resp = client_as(admin).put("/api/admin/settings/break_exception_allowed", json={"value": "false"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["value"] == "false"

    def test_schalter_nimmt_nur_bool(self, db, admin, client_as):
        resp = client_as(admin).put("/api/admin/settings/break_exception_allowed", json={"value": "vielleicht"})
        assert resp.status_code == 400

    def test_default_an_ausnahme_wirkt(self, db, employee, client_as):
        """Ohne Zeile in system_settings bleibt das bisherige Verhalten (Ausnahme erlaubt)."""
        resp = client_as(employee).post("/api/time-entries/", json={
            "date": today_local().isoformat(), **_OVER_6H, "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["break_waiver_reason"] == "Notfall"


class TestBreakExceptionDisabled:
    """``break_exception_allowed = false`` → jede Ausnahme wird serverseitig abgelehnt."""

    def test_ma_anlegen_mit_begruendung_400(self, db, employee, client_as):
        _disable_waiver(db)
        resp = client_as(employee).post("/api/time-entries/", json={
            "date": today_local().isoformat(), **_OVER_6H, "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 400, resp.text
        assert "abgeschaltet" in resp.json()["detail"]
        assert db.query(TimeEntry).count() == 0

    def test_ma_anlegen_mit_genehmigungspflicht_erzeugt_keinen_antrag(self, db, employee, client_as):
        _disable_waiver(db)
        _setting(db, "break_exception_requires_approval", "true")
        resp = client_as(employee).post("/api/time-entries/", json={
            "date": today_local().isoformat(), **_OVER_6H, "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 400, resp.text
        assert db.query(ChangeRequest).count() == 0

    def test_ma_anlegen_mit_ausreichender_pause_geht(self, db, employee, client_as):
        _disable_waiver(db)
        resp = client_as(employee).post("/api/time-entries/", json={
            "date": today_local().isoformat(), "start_time": "08:00", "end_time": "15:30",
            "break_minutes": 30,
        })
        assert resp.status_code == 201, resp.text

    def test_ma_bearbeiten_mit_begruendung_400(self, db, employee, client_as):
        _disable_waiver(db)
        e = _entry(db, employee, today_local(), time(8, 0), time(15, 30), brk=30)
        resp = client_as(employee).put(f"/api/time-entries/{e.id}", json={
            "break_minutes": 0, "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 400, resp.text
        assert "abgeschaltet" in resp.json()["detail"]
        db.refresh(e)
        assert e.break_minutes == 30

    def test_ausstempeln_mit_begruendung_400(self, db, employee, client_as, monkeypatch):
        _disable_waiver(db)
        today = _freeze_now(monkeypatch, 15, 30)
        open_entry = _entry(db, employee, today, time(8, 0), None)
        resp = client_as(employee).post("/api/time-entries/clock-out", json={
            "break_minutes": 0, "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 400, resp.text
        assert "abgeschaltet" in resp.json()["detail"]
        db.expire_all()
        assert db.get(TimeEntry, open_entry.id).end_time is None

    def test_admin_anlegen_mit_begruendung_400(self, db, employee, admin, client_as):
        _disable_waiver(db)
        d = today_local() - timedelta(days=1)
        resp = client_as(admin).post(f"/api/admin/users/{employee.id}/time-entries", json={
            "date": d.isoformat(), **_OVER_6H, "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 400, resp.text
        assert "abgeschaltet" in resp.json()["detail"]

    def test_admin_bearbeiten_mit_begruendung_400(self, db, employee, admin, client_as):
        _disable_waiver(db)
        d = today_local() - timedelta(days=1)
        e = _entry(db, employee, d, time(8, 0), time(15, 30), brk=30)
        resp = client_as(admin).put(f"/api/admin/time-entries/{e.id}", json={
            "break_minutes": 0, "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 400, resp.text
        assert "abgeschaltet" in resp.json()["detail"]
        db.refresh(e)
        assert e.break_minutes == 30

    def test_antrag_mit_begruendung_400(self, db, employee, client_as):
        _disable_waiver(db)
        d = today_local() - timedelta(days=7)
        resp = client_as(employee).post("/api/change-requests/", json={
            "request_type": "create", "proposed_date": d.isoformat(),
            "proposed_start_time": "08:00", "proposed_end_time": "15:46",
            "proposed_break_minutes": 0, "reason": "Korrektur",
            "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 400, resp.text
        assert "abgeschaltet" in resp.json()["detail"]
        assert db.query(ChangeRequest).count() == 0

    def test_offener_ausnahme_antrag_wird_nach_abschalten_nicht_genehmigt(
        self, db, employee, admin, client_as,
    ):
        """Ein vor dem Abschalten gestellter Ausnahme-Antrag wird bei der
        Genehmigung erneut gegen §4 geprüft (422) und bleibt offen."""
        d = today_local() - timedelta(days=7)
        cr = ChangeRequest(
            user_id=employee.id, tenant_id=DEFAULT_TENANT_ID,
            request_type=ChangeRequestType.CREATE, entry_kind="time_entry",
            status=ChangeRequestStatus.PENDING, proposed_date=d,
            proposed_start_time=time(8, 0), proposed_end_time=time(15, 46),
            proposed_break_minutes=0, reason="Notfall", break_waiver_reason="Notfall",
        )
        db.add(cr)
        db.commit()
        _disable_waiver(db)

        resp = client_as(admin).post(
            f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"},
        )

        assert resp.status_code == 422, resp.text
        assert "abgeschaltet" in resp.json()["detail"]
        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.PENDING
        assert db.query(TimeEntry).count() == 0


class TestSystemInfoExposesSwitch:

    @pytest.fixture(autouse=True)
    def _public_session(self, monkeypatch):
        """system_info öffnet eine eigene Session → auf die Test-Engine
        umbiegen; ``set_superadmin_context`` schickt SET-Statements, die
        SQLite nicht kennt (ohne no-op fiele system_info still auf Defaults)."""
        import app.main as main_module
        monkeypatch.setattr(main_module, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr("app.database.set_superadmin_context", lambda _db: None)

    def test_default_true(self, db, default_tenant):
        import app.main as main_module
        body = TestClient(main_module.app).get("/api/system/info").json()
        assert body["break_exception_allowed"] is True

    def test_false_when_disabled(self, db, default_tenant):
        import app.main as main_module
        _disable_waiver(db)
        body = TestClient(main_module.app).get("/api/system/info").json()
        assert body["break_exception_allowed"] is False


# ---------------------------------------------------------------------------
# Review-Nachzug zu #499
# ---------------------------------------------------------------------------

class TestClockOutIgnoresApprovalRequirement:
    """Review F1: Das Ausstempeln kennt die Genehmigungspflicht bewusst nicht.

    Der Eintrag MUSS geschlossen werden (§16 ArbZG: die Zeit ist geleistet);
    eine zulässige Begründung wird sofort wirksam und steht im
    Änderungsprotokoll (Quelle ``break_waiver``). Ein Antrag entsteht nicht —
    die Genehmigungspflicht gilt für manuelle Erfassung, Bearbeitung und
    Anträge. Der Test hält das fest, damit eine Änderung bewusst geschieht und
    Handbuch/Einstellungen-Karte mitgezogen werden.
    """

    def test_begruendung_wirkt_sofort_trotz_genehmigungspflicht(
        self, db, employee, client_as, monkeypatch,
    ):
        from app.models import TimeEntryAuditLog

        _setting(db, "break_exception_requires_approval", "true")
        today = _freeze_now(monkeypatch, 18, 0)
        open_entry = _open_after(db, employee, today, time(8, 49), time(13, 59), time(13, 59))

        resp = client_as(employee).post("/api/time-entries/clock-out", json={
            "break_minutes": 0, "break_waiver_reason": "Notfall",
        })

        assert resp.status_code == 200, resp.text
        db.expire_all()
        e = db.get(TimeEntry, open_entry.id)
        assert e.end_time == time(18, 0)
        assert e.break_waiver_reason == "Notfall"
        assert db.query(ChangeRequest).count() == 0
        assert db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.time_entry_id == open_entry.id,
            TimeEntryAuditLog.source == "break_waiver",
        ).count() == 1


class TestOwnWaiverRequestAfterSwitchOff:
    """Review F3: Die 4-Augen-Sperre für eigene Pflicht-Pause-Ausnahmen (SEC-E)
    richtet sich nach der WIRKSAMEN Ausnahme. Ist der Schalter aus, verwirft die
    Genehmigung die gespeicherte Begründung und prüft §4 neu — dann gewährt sie
    keine Ausnahme mehr, und die Sperre (403 mit falschem Grund) darf nicht
    greifen. Einzel-Admin-Praxen dürfen gewöhnliche eigene Anträge genehmigen (A01).
    """

    def _own_waiver_cr(self, db, admin, d):
        """Nachtrag 12:00–15:00 an einen Vormittag 08:00–12:00 ohne Pause —
        beim Stellen ein §4-Verstoß, darum mit Ausnahme-Begründung."""
        cr = ChangeRequest(
            user_id=admin.id, tenant_id=DEFAULT_TENANT_ID,
            request_type=ChangeRequestType.CREATE, entry_kind="time_entry",
            status=ChangeRequestStatus.PENDING, proposed_date=d,
            proposed_start_time=time(12, 0), proposed_end_time=time(15, 0),
            proposed_break_minutes=0, reason="Nachtrag", break_waiver_reason="Notfall",
        )
        db.add(cr)
        db.commit()
        return cr

    def test_tag_inzwischen_konform_wird_genehmigt(self, db, admin, client_as):
        d = today_local() - timedelta(days=7)
        morning = _entry(db, admin, d, time(8, 0), time(12, 0))
        cr = self._own_waiver_cr(db, admin, d)
        _disable_waiver(db)
        # Inzwischen wurde die Pause am Vormittag nachgetragen → Tag erfüllt §4.
        morning.break_minutes = 30
        db.commit()

        resp = client_as(admin).post(
            f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"},
        )

        assert resp.status_code == 200, resp.text
        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.APPROVED
        created = db.query(TimeEntry).filter(
            TimeEntry.user_id == admin.id, TimeEntry.start_time == time(12, 0),
        ).one()
        assert created.break_waiver_reason is None

    def test_tag_weiter_verstoss_meldet_pause_statt_4_augen(self, db, admin, client_as):
        d = today_local() - timedelta(days=7)
        _entry(db, admin, d, time(8, 0), time(12, 0))
        cr = self._own_waiver_cr(db, admin, d)
        _disable_waiver(db)

        resp = client_as(admin).post(
            f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"},
        )

        assert resp.status_code == 422, resp.text
        assert "abgeschaltet" in resp.json()["detail"]
        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.PENDING

    def test_schalter_an_bleibt_403(self, db, admin, client_as):
        """Gegenprobe: mit erlaubter Ausnahme bleibt SEC-E unverändert hart."""
        d = today_local() - timedelta(days=7)
        _entry(db, admin, d, time(8, 0), time(12, 0))
        cr = self._own_waiver_cr(db, admin, d)

        resp = client_as(admin).post(
            f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"},
        )

        assert resp.status_code == 403, resp.text
        assert "selbst genehmigt" in resp.json()["detail"]


class TestWaiverOnlyStoredWhenNeeded:
    """Review F4: Ein Antrag speichert die Begründung nur, wenn sie eine §4-
    Ausnahme tatsächlich trägt. Sonst übersprang die Genehmigung die §4-
    Neuprüfung (``waiver_reason is None``-Gate) und materialisierte den Eintrag
    als ``break_waiver``, obwohl der Tag inzwischen gegen §4 verstößt."""

    def test_begruendung_ohne_verstoss_wird_nicht_gespeichert(self, db, employee, client_as):
        d = today_local() - timedelta(days=7)
        resp = client_as(employee).post("/api/change-requests/", json={
            "request_type": "create", "proposed_date": d.isoformat(),
            "proposed_start_time": "12:00", "proposed_end_time": "15:00",
            "proposed_break_minutes": 0, "reason": "vergessen",
            "break_waiver_reason": "Notfall",
        })

        assert resp.status_code == 201, resp.text
        cr = db.query(ChangeRequest).one()
        assert cr.break_waiver_reason is None

    def test_begruendung_mit_verstoss_wird_gespeichert(self, db, employee, client_as):
        """Gegenprobe: echter §4-Verstoß → Begründung bleibt am Antrag."""
        d = today_local() - timedelta(days=7)
        _entry(db, employee, d, time(8, 0), time(12, 0))
        resp = client_as(employee).post("/api/change-requests/", json={
            "request_type": "create", "proposed_date": d.isoformat(),
            "proposed_start_time": "12:00", "proposed_end_time": "15:00",
            "proposed_break_minutes": 0, "reason": "vergessen",
            "break_waiver_reason": "Notfall",
        })

        assert resp.status_code == 201, resp.text
        assert db.query(ChangeRequest).one().break_waiver_reason == "Notfall"

    def test_genehmigung_prueft_spaeteren_tagesverstoss(self, db, employee, admin, client_as):
        """Antrag war beim Stellen §4-konform (Begründung überflüssig); bis zur
        Genehmigung kam ein Vormittag dazu → 422 statt stiller break_waiver-Buchung."""
        d = today_local() - timedelta(days=7)
        resp = client_as(employee).post("/api/change-requests/", json={
            "request_type": "create", "proposed_date": d.isoformat(),
            "proposed_start_time": "12:00", "proposed_end_time": "15:00",
            "proposed_break_minutes": 0, "reason": "vergessen",
            "break_waiver_reason": "Notfall",
        })
        assert resp.status_code == 201, resp.text
        cr_id = resp.json()["id"]
        _entry(db, employee, d, time(8, 0), time(12, 0))

        review = client_as(admin).post(
            f"/api/admin/change-requests/{cr_id}/review", json={"action": "approve"},
        )

        assert review.status_code == 422, review.text
        assert db.query(TimeEntry).filter(TimeEntry.start_time == time(12, 0)).count() == 0
