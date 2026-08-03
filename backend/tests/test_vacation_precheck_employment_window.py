"""Release-Review 1.18.1: warum die Urlaubs-VORPRUEFUNG das
Beschaeftigungsfenster NICHT selbst kennen muss.

Der Befund
==========
``is_vacation_billable_day`` formuliert im eigenen Docstring die Invariante:

    "Sie muss exakt das sagen, was die zugehoerige Buchungsschleife danach tut —
    laufen die beiden auseinander, lehnt der Check eine Buchung mit 400 ab, die
    nachher weniger Budget verbraucht haette."

``a1cdc250`` (Audit 2026-07-31, Fund B) hat die VERBRAUCHS-Seite
(``get_vacation_account``) um das #193-Beschaeftigungsfenster beschnitten, den
Helfer aber nicht. Daraus wurde die Sorge abgeleitet, budget-gedeckte
Buchungen ueber ein Austrittsdatum hinaus wuerden seither faelschlich mit 400
abgelehnt.

Warum das nicht eintritt
========================
Alle vier Aufrufer der Vorpruefung sperren Tage ausserhalb des Fensters
VORHER — mit einer eigenen, ausdruecklichen 400 und einer anderen Meldung:

* ``absences.create_absence``            (Bereichs-Guard auf start/end)
* ``admin_vacations.review_vacation_request``  (Bereichs-Guard auf start/end)
* ``vacation_requests`` (Anlegen + Bearbeiten)  (Bereichs-Guard auf start/end)
* ``admin_change_requests.review_change_request`` (Guard auf proposed_date)

Weil das Fenster ein zusammenhaengender Zeitraum ist, folgt aus "irgendein Tag
des Bereichs liegt ausserhalb" zwingend "start < first_work_day ODER
end > last_work_day" — der Bereichs-Guard greift also immer, bevor die
Tagesliste ueberhaupt gebildet wird. Die Vorpruefung sieht nie einen Tag
ausserhalb des Fensters, und der Anwender bekommt die praezisere Meldung
("Datum liegt nach dem letzten Arbeitstag") statt einer irrefuehrenden
Budget-Ablehnung.

Diese Datei nagelt genau diese Reihenfolge fest. Faellt einer der Guards weg
(oder wird ein Bereichs-Guard zu einem Per-Tag-Filter umgebaut, der die
uebrigen Tage durchlaesst), muss der Helfer das Fenster mitziehen — dann wird
hier ein Test rot, statt dass es stillschweigend zur Fehlablehnung kommt.
"""
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User, UserRole
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _app() -> FastAPI:
    from app.routers import absences
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(absences.router)
    return app


_APP = _app()


@pytest.fixture(autouse=True)
def _clear():
    yield
    _APP.dependency_overrides.clear()


def _client(db, user):
    def odb():
        yield db
    _APP.dependency_overrides[get_db] = odb
    _APP.dependency_overrides[get_current_user] = lambda: user
    return TestClient(_APP)


def _employee(db, **kw):
    defaults = dict(
        password_hash="x", first_name="Aus", last_name="Tritt", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, work_days_per_week=5, vacation_days=4,
        track_hours=True, use_daily_schedule=False, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kw)
    marker = uuid.uuid4().hex[:6]
    u = User(id=uuid.uuid4(), username=f"aus{marker}", email=f"{marker}@t.l", **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# Mo–Fr; die letzten drei Tage liegen nach einem Austritt am 30.06.
MONTAG, FREITAG = date(2026, 6, 29), date(2026, 7, 3)


class TestFensterGuardLaeuftVorDerBudgetPruefung:
    """Der Bereichs-Guard entscheidet, nicht das Budget."""

    def test_bereich_ueber_den_austritt_hinaus_wird_mit_eigener_meldung_abgelehnt(
        self, db, default_tenant
    ):
        u = _employee(db, last_work_day=date(2026, 6, 30))
        r = _client(db, u).post("/api/absences", json={
            "date": MONTAG.isoformat(), "end_date": FREITAG.isoformat(),
            "type": "vacation", "hours": 8,
        })
        assert r.status_code == 400, r.text
        assert "letzten Arbeitstag" in r.json()["detail"], (
            "die Budget-Vorpruefung darf hier gar nicht erst zum Zuge kommen"
        )

    def test_bereich_vor_dem_eintritt_wird_mit_eigener_meldung_abgelehnt(
        self, db, default_tenant
    ):
        u = _employee(db, first_work_day=date(2026, 7, 1))
        r = _client(db, u).post("/api/absences", json={
            "date": MONTAG.isoformat(), "end_date": FREITAG.isoformat(),
            "type": "vacation", "hours": 8,
        })
        assert r.status_code == 400, r.text
        assert "ersten Arbeitstag" in r.json()["detail"]

    def test_bereich_ganz_im_fenster_wird_normal_gebucht(self, db, default_tenant):
        """Gegenprobe: liegt der Bereich im Fenster, entscheidet allein das
        Budget — 4 × 6/12 = 2,0 Tage decken die zwei gebuchten Tage."""
        u = _employee(db, last_work_day=date(2026, 6, 30))
        assert calculation_service.get_vacation_account(db, u, 2026)["budget_days"] == 2.0

        r = _client(db, u).post("/api/absences", json={
            "date": MONTAG.isoformat(), "end_date": date(2026, 6, 30).isoformat(),
            "type": "vacation", "hours": 8,
        })
        assert r.status_code == 201, r.text
        konto = calculation_service.get_vacation_account(db, u, 2026)
        assert konto["used_days"] == 2.0
        assert konto["remaining_days"] == 0.0

    def test_ueberziehung_im_fenster_wird_weiterhin_abgelehnt(self, db, default_tenant):
        """Der Budget-Schutz bleibt scharf: 1,0 Tag deckt zwei Tage nicht."""
        u = _employee(db, vacation_days=2, last_work_day=date(2026, 6, 30))
        assert calculation_service.get_vacation_account(db, u, 2026)["budget_days"] == 1.0

        r = _client(db, u).post("/api/absences", json={
            "date": MONTAG.isoformat(), "end_date": date(2026, 6, 30).isoformat(),
            "type": "vacation", "hours": 8,
        })
        assert r.status_code == 400, r.text
        assert "Urlaubstage" in r.json()["detail"]


class TestHelferBleibtBewusstFensterfrei:
    """Der Helfer beantwortet ausschliesslich "hat dieser Tag ein Soll?" — das
    Beschaeftigungsfenster ist im ``calculation_service`` durchgaengig Sache
    des Aufrufers (~20 Einzelstellen). Hier festgenagelt, damit die Aussage
    nicht versehentlich kippt."""

    def test_tag_ausserhalb_des_fensters_bleibt_abrechenbar(self, db, default_tenant):
        u = _employee(db, last_work_day=date(2026, 6, 30))
        assert calculation_service.is_vacation_billable_day(db, u, date(2026, 7, 1)) is True

    def test_ohne_fenster_unveraendert(self, db, default_tenant):
        u = _employee(db)
        assert calculation_service.is_vacation_billable_day(db, u, MONTAG) is True
        assert calculation_service.is_vacation_billable_day(db, u, FREITAG) is True
