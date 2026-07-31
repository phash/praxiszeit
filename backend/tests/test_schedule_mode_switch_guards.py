"""#431 Fix-Welle 1: Guards, die den MODUS entscheiden, muessen ihn zum DATUM
aufloesen — nicht von der User-Zeile lesen.

Seit #431 traegt jede ``WorkingHoursChange`` den vollstaendigen Vertrags-
Snapshot (``use_daily_schedule`` + Tageswerte + ``work_days_per_week``).
``users.use_daily_schedule`` ist damit nur noch der HEUTE gueltige Wert. Alle
Stellen, die „an diesem Tag gilt ein Tagesplan" entscheiden, muessen deshalb
ueber ``get_schedule_for_date`` gehen. Vor #431 konnten Live-Wert und
aufgeloester Wert nie divergieren, danach schon — genau daraus entstehen die
beiden hier abgesicherten Fehler:

* Fund 1 — die Urlaubs-Budget-Vorpruefungen filterten 0-Stunden-Tage am
  LIVE-Flag, waehrend der Filterwert (das Tagessoll) und die Buchungsschleife
  daneben datumsaufgeloest arbeiteten: Ablehnung mit 400, obwohl die Buchung
  weniger Budget verbraucht haette.
* Fund 2 — die Betriebsferien-Buchung uebersprang den 0-Stunden-Tag nur am
  LIVE-Flag: sie loeschte geleistete Arbeitszeit an einem Tag, an dem gar nicht
  zu schliessen war, und legte eine irrefuehrende 0-h-„Urlaub"-Zeile an.

Zusaetzlich abgesichert: die beiden #314-Klassifizierer (Buchung und
Re-Split) duerfen nicht divergieren, und fuer Mitarbeitende OHNE Moduswechsel
aendert sich nichts (Byte-Identitaet).
"""
import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db, Base
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    Absence, AbsenceType, TimeEntry, User, UserRole, WorkingHoursChange,
)
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.services import auth_service, calculation_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal

# Rueckwirkende Urlaubswoche (Mo–Fr) im Tagesplan-Zeitraum.
VAC_MON, VAC_FRI = date(2026, 7, 6), date(2026, 7, 10)
# Betriebsferien-Woche (Mo–Fr) im selben Tagesplan-Zeitraum.
CLO_MON, CLO_FRI = date(2026, 9, 7), date(2026, 9, 11)
CLO_TUE = date(2026, 9, 8)
# Ab hier gilt der gleichmaessige Modus (der Resync setzt die User-Zeile darauf).
SWITCH = date(2026, 10, 1)


def _create_test_app() -> FastAPI:
    from app.routers import absences, admin_vacations, company_closures, vacation_requests
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    app.include_router(admin_vacations.router)
    app.include_router(vacation_requests.router)
    app.include_router(company_closures.router)
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
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default",
               is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, *, role=UserRole.EMPLOYEE, vacation_days=4,
               track_hours=True, use_daily_schedule=False, weekly_hours=40.0,
               work_days_per_week=5, day_hours=(None,) * 5):
    u = User(
        username=username, email=f"{username}@x.de",
        password_hash=auth_service.hash_password("x"),
        first_name=username, last_name="T", role=role,
        weekly_hours=weekly_hours, vacation_days=vacation_days,
        work_days_per_week=work_days_per_week, is_active=True,
        track_hours=track_hours, use_daily_schedule=use_daily_schedule,
        hours_monday=day_hours[0], hours_tuesday=day_hours[1],
        hours_wednesday=day_hours[2], hours_thursday=day_hours[3],
        hours_friday=day_hours[4],
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _switched_user(db, username="switcher", vacation_days=4):
    """Mo/Mi/Fr-Tagesplan bis 30.09.2026, ab 01.10.2026 gleichmaessig.

    Die User-Zeile traegt den Zustand NACH dem Wechsel — genau das, was
    ``_sync_user_from_change`` beim Anlegen der zweiten Historien-Zeile
    zurueckspiegelt. Der Tagesplan lebt nur noch in der Historie.
    """
    u = _make_user(db, username, vacation_days=vacation_days,
                   use_daily_schedule=False, weekly_hours=40.0,
                   work_days_per_week=5)
    db.add(WorkingHoursChange(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("24.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_wednesday=Decimal("8.0"), hours_friday=Decimal("8.0"),
        work_days_per_week=3,
    ))
    db.add(WorkingHoursChange(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=SWITCH, weekly_hours=Decimal("40.0"),
        use_daily_schedule=False, work_days_per_week=5,
    ))
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin(db, default_tenant):
    return _make_user(db, "adm1", role=UserRole.ADMIN, vacation_days=30)


def _client_as(db, user, *, admin_user=None):
    def override_db():
        yield db
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: user
    _app.dependency_overrides[require_admin] = lambda: (admin_user or user)
    return TestClient(_app)


def _absences(db, user):
    return db.query(Absence).filter(Absence.user_id == user.id).order_by(Absence.date).all()


# ── Fund 1: Urlaubs-Vorpruefungen ────────────────────────────────────────────

class TestVacationPreCheckUsesResolvedMode:
    """Der Pre-Check muss genau so viel Budget verlangen, wie die Buchung
    danach verbraucht — auch ueber einen Moduswechsel hinweg."""

    def test_direct_booking_retroactive_into_day_plan_period(self, db, default_tenant, admin):
        """Fund 1, Reproduktion: rueckwirkender Urlaub Mo–Fr im Tagesplan-Zeitraum.

        Historisch sind nur Mo/Mi/Fr Arbeitstage -> die Buchung legt 3 Zeilen an
        und verbraucht 3 Tage. Der Pre-Check las das LIVE-Flag (False, weil der
        Resync die User-Zeile auf den gleichmaessigen Modus gestellt hat),
        zaehlte deshalb 5 Tage und lehnte bei 4 Resttagen mit 400 ab.
        """
        emp = _switched_user(db, vacation_days=4)
        client = _client_as(db, admin)

        r = client.post("/api/absences/", json={
            "user_id": str(emp.id), "date": VAC_MON.isoformat(),
            "end_date": VAC_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })
        _app.dependency_overrides.clear()

        assert r.status_code == 201, r.text
        booked = _absences(db, emp)
        assert [a.date for a in booked] == [
            date(2026, 7, 6), date(2026, 7, 8), date(2026, 7, 10)
        ]
        # ... und das Konto zaehlt genau die drei — Pre-Check und Buchung sind deckungsgleich.
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(3.0)

    def test_direct_booking_future_day_plan_while_flag_still_off(self, db, default_tenant, admin):
        """Die Gegenrichtung: der Tagesplan startet in der ZUKUNFT, die
        User-Zeile steht noch auf gleichmaessig (die Zeile wird erst am
        Wirkungsdatum nachgezogen)."""
        emp = _make_user(db, "future_plan", vacation_days=4)
        db.add(WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=date(2026, 7, 1), weekly_hours=Decimal("24.0"),
            use_daily_schedule=True, hours_monday=Decimal("8.0"),
            hours_wednesday=Decimal("8.0"), hours_friday=Decimal("8.0"),
            work_days_per_week=3,
        ))
        db.commit()

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": VAC_MON.isoformat(),
            "end_date": VAC_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })
        _app.dependency_overrides.clear()

        assert r.status_code == 201, r.text
        assert len(_absences(db, emp)) == 3

    def test_vacation_request_create_and_approval_agree(self, db, default_tenant, admin):
        """Antrag anlegen (MA) + Genehmigung (Admin) sind zwei weitere
        Vorpruefungen desselben Musters — beide muessen den Zeitraum
        durchlassen und am Ende 3 Zeilen buchen."""
        emp = _switched_user(db, "req_switcher", vacation_days=4)
        db.merge(SystemSetting(key="vacation_approval_required",
                               tenant_id=DEFAULT_TENANT_ID, value="true"))
        db.commit()

        r = _client_as(db, emp).post("/api/vacation-requests/", json={
            "date": VAC_MON.isoformat(), "end_date": VAC_FRI.isoformat(),
            "hours": 8.0, "absence_type": "vacation",
        })
        assert r.status_code == 201, r.text
        vr_id = r.json()["id"]

        r = _client_as(db, admin).post(
            f"/api/admin/vacation-requests/{vr_id}/review", json={"action": "approve"})
        _app.dependency_overrides.clear()
        assert r.status_code == 200, r.text

        assert [a.date for a in _absences(db, emp)] == [
            date(2026, 7, 6), date(2026, 7, 8), date(2026, 7, 10)
        ]


class TestVacationPreCheckByteIdentity:
    """Ohne Moduswechsel darf sich nichts aendern."""

    def test_even_mode_without_history_still_costs_five_days(self, db, default_tenant, admin):
        emp = _make_user(db, "even_plain", vacation_days=5)

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": VAC_MON.isoformat(),
            "end_date": VAC_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })
        _app.dependency_overrides.clear()

        assert r.status_code == 201, r.text
        assert len(_absences(db, emp)) == 5
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(5.0)

    def test_even_mode_over_budget_still_rejected(self, db, default_tenant, admin):
        """Der Pre-Check bleibt scharf: 5 Werktage bei 4 Resttagen -> 400."""
        emp = _make_user(db, "even_tight", vacation_days=4)

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": VAC_MON.isoformat(),
            "end_date": VAC_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })
        _app.dependency_overrides.clear()

        assert r.status_code == 400, r.text
        assert _absences(db, emp) == []

    def test_stable_day_plan_without_history_unchanged(self, db, default_tenant, admin):
        """Tagesplan-MA OHNE Historie: 3 abrechenbare Tage wie bisher."""
        emp = _make_user(db, "plan_plain", vacation_days=4, use_daily_schedule=True,
                         weekly_hours=24.0, work_days_per_week=3,
                         day_hours=(8.0, None, 8.0, None, 8.0))

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": VAC_MON.isoformat(),
            "end_date": VAC_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })
        _app.dependency_overrides.clear()

        assert r.status_code == 201, r.text
        assert len(_absences(db, emp)) == 3

    def test_untracked_employee_still_counts_every_weekday(self, db, default_tenant, admin):
        """#191: leitende Angestellte (track_hours=False) haben immer Tagessoll 0
        und muessen trotzdem tagebasiert 5 Tage verbrauchen — sie duerfen vom
        0-Stunden-Filter NIE erfasst werden."""
        emp = _make_user(db, "untracked", vacation_days=5, track_hours=False)

        r = _client_as(db, admin).post("/api/absences/", json={
            "user_id": str(emp.id), "date": VAC_MON.isoformat(),
            "end_date": VAC_FRI.isoformat(), "type": "vacation", "hours": 8.0,
        })
        _app.dependency_overrides.clear()

        assert r.status_code == 201, r.text
        assert len(_absences(db, emp)) == 5
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(5.0)


class TestIsVacationBillableDayHelper:
    """Der gemeinsame Helfer selbst — DIE eine Quelle aller Vorpruefungen."""

    def test_resolves_mode_per_date(self, db, default_tenant):
        emp = _switched_user(db, "helper_user")
        # Di im Tagesplan-Zeitraum: historisch 0 h -> nicht abrechenbar.
        assert calculation_service.is_vacation_billable_day(db, emp, date(2026, 7, 7)) is False
        # Derselbe Wochentag NACH dem Wechsel: gleichmaessiger Modus -> abrechenbar.
        assert calculation_service.is_vacation_billable_day(db, emp, date(2026, 10, 6)) is True

    def test_untracked_always_billable(self, db, default_tenant):
        emp = _make_user(db, "helper_untracked", track_hours=False)
        assert calculation_service.is_vacation_billable_day(db, emp, date(2026, 7, 7)) is True

    def test_preload_matches_query_path(self, db, default_tenant):
        emp = _switched_user(db, "helper_preload")
        preload = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id).all()
        for d in (date(2026, 7, 6), date(2026, 7, 7), date(2026, 10, 5), date(2026, 10, 6)):
            assert calculation_service.is_vacation_billable_day(db, emp, d) == \
                   calculation_service.is_vacation_billable_day(db, emp, d, wh_changes=preload)


# ── Fund 2: Betriebsferien ───────────────────────────────────────────────────

def _set_toggle(db, on: bool):
    db.merge(SystemSetting(key="closure_overtime_after_vacation",
                           tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def _create_closure(client, start=CLO_MON, end=CLO_FRI, counts_as_vacation=True):
    r = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": start.isoformat(), "end_date": end.isoformat(),
        "counts_as_vacation": counts_as_vacation})
    assert r.status_code == 201, r.text
    return r.json()


class TestClosureBookingUsesResolvedMode:

    def test_zero_hour_day_is_skipped_and_work_survives(self, db, default_tenant, admin):
        """Fund 2, Reproduktion: der MA stand zum Closure-Datum im Tagesplan
        (Di = 0 h), steht heute aber gleichmaessig da.

        Der Skip-Guard las das LIVE-Flag -> er griff nicht: die geleistete
        Arbeitszeit am Dienstag wurde geloescht und eine 0-h-„Urlaub"-Zeile
        angelegt.
        """
        emp = _switched_user(db, "clo_switcher", vacation_days=10)
        db.add(TimeEntry(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=CLO_TUE,
            start_time=time(9, 0), end_time=time(13, 0), break_minutes=0,
        ))
        db.commit()

        _create_closure(_client_as(db, admin))
        _app.dependency_overrides.clear()
        db.expire_all()

        # Der Dienstag ist kein Arbeitstag dieses MA -> keine Buchung ...
        booked = {a.date for a in _absences(db, emp)}
        assert CLO_TUE not in booked
        assert booked == {date(2026, 9, 7), date(2026, 9, 9), date(2026, 9, 11)}
        # ... und die geleistete Arbeitszeit ueberlebt.
        assert db.query(TimeEntry).filter(
            TimeEntry.user_id == emp.id, TimeEntry.date == CLO_TUE).count() == 1
        # Keine irrefuehrende 0-h-Zeile.
        assert all(float(a.hours) > 0 for a in _absences(db, emp))

    def test_stable_day_plan_without_history_unchanged(self, db, default_tenant, admin):
        emp = _make_user(db, "clo_plan", vacation_days=10, use_daily_schedule=True,
                         weekly_hours=24.0, work_days_per_week=3,
                         day_hours=(8.0, None, 8.0, None, 8.0))
        _create_closure(_client_as(db, admin))
        _app.dependency_overrides.clear()
        db.expire_all()
        assert {a.date for a in _absences(db, emp)} == {
            date(2026, 9, 7), date(2026, 9, 9), date(2026, 9, 11)}

    def test_even_mode_books_all_five_days(self, db, default_tenant, admin):
        emp = _make_user(db, "clo_even", vacation_days=10)
        _create_closure(_client_as(db, admin))
        _app.dependency_overrides.clear()
        db.expire_all()
        assert len(_absences(db, emp)) == 5

    def test_untracked_still_books_every_closure_day(self, db, default_tenant, admin):
        """#191: track_hours=False -> Tagessoll immer 0, trotzdem 1 Urlaubstag
        pro Closure-Tag. Der Skip darf sie nie erfassen."""
        emp = _make_user(db, "clo_untracked", vacation_days=10, track_hours=False)
        _create_closure(_client_as(db, admin))
        _app.dependency_overrides.clear()
        db.expire_all()
        assert len(_absences(db, emp)) == 5


class TestResplitMatchesBookingClassifier:
    """Die beiden #314-Klassifizierer duerfen nicht divergieren."""

    def test_zero_target_row_does_not_consume_budget(self, db, default_tenant, admin):
        """Fund 2 (b), Reproduktion: eine Alt-Zeile mit Tagessoll 0 (aus einem
        Lauf VOR diesem Fix) darf im Re-Split keinen vollen Urlaubstag kosten.

        Sonst frisst sie das Budget eines echten 8-h-Arbeitstages auf, der
        dadurch faelschlich auf OVERTIME kippt und 8 h vom Ueberstundenkonto
        abzieht, obwohl noch Urlaub da war.
        """
        _set_toggle(db, True)
        emp = _switched_user(db, "resplit_legacy", vacation_days=3)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        _app.dependency_overrides.clear()
        db.expire_all()

        closure_id = uuid.UUID(closure["id"])
        # Alt-Zeile nachstellen, wie sie der ungefixte Buchungspfad erzeugt haette.
        db.add(Absence(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=CLO_TUE,
            type=AbsenceType.VACATION, hours=0.0, half_day=False,
            closure_id=closure_id, note="Betriebsferien: BF",
        ))
        db.commit()

        from app.services.closure_split_service import resplit_year_closures
        resplit_year_closures(db, DEFAULT_TENANT_ID, 2026)
        db.commit()
        db.expire_all()

        by_date = {a.date: a.type for a in _absences(db, emp)}
        # Budget 3, drei echte Arbeitstage -> alle drei bleiben VACATION.
        assert by_date[date(2026, 9, 7)] == AbsenceType.VACATION
        assert by_date[date(2026, 9, 9)] == AbsenceType.VACATION
        assert by_date[date(2026, 9, 11)] == AbsenceType.VACATION
        # Die 0-h-Zeile kostet nichts und bleibt beim Basistyp der Schliessung.
        assert by_date[CLO_TUE] == AbsenceType.VACATION

    def test_resave_with_split_removes_stale_zero_hour_row(self, db, default_tenant, admin):
        """Bestandszeilen aus einem Lauf VOR diesem Fix: bei aktivem #314-Split
        loescht das Re-Save alle in-range-Closure-Absencen und der (jetzt
        korrekte) Buchungspfad legt den 0-h-Tag nicht wieder an."""
        _set_toggle(db, True)
        emp = _switched_user(db, "resave_split", vacation_days=10)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        db.add(Absence(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=CLO_TUE,
            type=AbsenceType.VACATION, hours=0.0, half_day=False,
            closure_id=uuid.UUID(closure["id"]), note="Betriebsferien: BF",
        ))
        db.commit()

        r = client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "BF", "start_date": CLO_MON.isoformat(),
            "end_date": CLO_FRI.isoformat(), "counts_as_vacation": True})
        _app.dependency_overrides.clear()
        assert r.status_code == 200, r.text

        db.expire_all()
        assert CLO_TUE not in {a.date for a in _absences(db, emp)}

    def test_stale_zero_hour_row_is_accounting_neutral(self, db, default_tenant, admin):
        """Ohne aktiven Split behaelt das Re-Save die Bestandszeile (der
        Loeschzweig greift nur bei ``split_active``). Sie ist aber in BEIDEN
        tagebasierten Zaehlungen neutral — ``get_vacation_account.used_days`` und
        ``absence_days`` ueberspringen Tagessoll 0 —, also rein kosmetisch."""
        emp = _switched_user(db, "resave_nosplit", vacation_days=10)
        client = _client_as(db, admin)
        closure = _create_closure(client)
        db.add(Absence(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=CLO_TUE,
            type=AbsenceType.VACATION, hours=0.0, half_day=False,
            closure_id=uuid.UUID(closure["id"]), note="Betriebsferien: BF",
        ))
        db.commit()

        r = client.put(f"/api/company-closures/{closure['id']}", json={
            "name": "BF", "start_date": CLO_MON.isoformat(),
            "end_date": CLO_FRI.isoformat(), "counts_as_vacation": True})
        _app.dependency_overrides.clear()
        assert r.status_code == 200, r.text

        db.expire_all()
        rows = _absences(db, emp)
        assert CLO_TUE in {a.date for a in rows}          # bleibt stehen ...
        # ... kostet aber nichts: nur die drei echten Arbeitstage zaehlen.
        assert calculation_service.get_vacation_account(db, emp, 2026)["used_days"] == pytest.approx(3.0)
        assert float(calculation_service.absence_days(db, emp, rows)) == pytest.approx(3.0)

    def test_split_still_flips_to_overtime_when_budget_runs_out(self, db, default_tenant, admin):
        """Kontrolle: der Re-Split bleibt scharf — bei zu kleinem Budget kippt
        der spaetere Tag weiterhin auf OVERTIME."""
        _set_toggle(db, True)
        emp = _make_user(db, "resplit_tight", vacation_days=2)
        _create_closure(_client_as(db, admin))
        _app.dependency_overrides.clear()
        db.expire_all()

        types = [a.type for a in _absences(db, emp)]
        assert types.count(AbsenceType.VACATION) == 2
        assert types.count(AbsenceType.OVERTIME) == 3
