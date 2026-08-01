"""Audit 2026-07-31 — Funde U1 (Serverseite) und U2 (Serverseite).

U1/Serverseite: ``POST /api/absences`` antwortete mit **201 und einer leeren
Liste**, wenn an allen Zieltagen 0 Stunden geplant sind (Tagesplan-Mitarbeitende
mit einem freien Wochentag). Das Monatsjournal meldete daraufhin „Gespeichert",
obwohl nichts entstanden ist — und hatte den alten Eintrag zuvor bereits
geloescht. Eine Buchung, die nichts bucht, ist ein Fehler und gehoert als 400
mit verstaendlichem Grund beantwortet.

U2/Serverseite: ``PUT /api/time-entries/{id}`` schloss einen LAUFENDEN Eintrag
(ohne Ende) klaglos mit einer Uhrzeit, die noch gar nicht erreicht ist. Das
Frontend belegte das Feld „Bis" beim Bearbeiten mit dem festen Wert 17:00 vor
und schickte es immer mit — der laufende Eintrag wurde also stillschweigend auf
17:00 geschlossen. Fuer §16 ist das eine erfundene Zeit.

Harness wie tests/test_milog.py (lokale _app() + dependency_overrides).
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user
from app.models import User, UserRole, TimeEntry
from app.models.tenant import Tenant
from app.services import auth_service
from app.services.timezone_service import LOCAL_TZ, today_local
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _app() -> FastAPI:
    from app.routers import absences, time_entries
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    a = FastAPI()
    limiter.enabled = False
    a.state.limiter = limiter
    a.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    a.include_router(absences.router)
    a.include_router(time_entries.router)
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
def tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="D", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _client(db, user):
    def odb():
        yield db
    app.dependency_overrides[get_db] = odb
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user(db, **kw):
    defaults = dict(
        id=uuid.uuid4(),
        username=f"u{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@t.local",
        password_hash=auth_service.hash_password("test123"),
        first_name="Test", last_name="User", role=UserRole.EMPLOYEE,
        weekly_hours=40, work_days_per_week=5, vacation_days=30,
        track_hours=True, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kw)
    u = User(**defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------------------------------------------------------------------------
# U1 (Serverseite): keine Buchung -> 400 statt „201 mit leerer Liste"
# ---------------------------------------------------------------------------

class TestAbsenceWithoutBookableDay:
    """Ein Tagesplan-MA mit 0 geplanten Stunden am Zieltag."""

    def _dayplan_user(self, db):
        # Tagesplan: Mo/Mi/Fr je 8 h, Di/Do frei (None == 0 h).
        return _user(
            db, use_daily_schedule=True,
            hours_monday=8, hours_tuesday=None, hours_wednesday=8,
            hours_thursday=None, hours_friday=8,
        )

    def test_zero_hour_day_is_rejected_not_silently_empty(self, db, tenant):
        """RED: 2026-03-03 ist ein Dienstag, an dem 0 h geplant sind. Die
        Erzeugungsschleife ueberspringt ihn (``hours_for_day == 0`` bei
        ``track_hours``) — die Antwort war 201 mit ``[]``. Erwartet: 400 mit
        verstaendlichem Grund, damit das Journal nicht „Gespeichert" meldet,
        obwohl nichts gebucht wurde."""
        u = self._dayplan_user(db)
        resp = _client(db, u).post("/api/absences", json={
            "date": "2026-03-03", "type": "sick", "hours": 8,
        })
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]
        assert "0" in resp.json()["detail"] or "geplant" in resp.json()["detail"].lower()

    def test_zero_hour_day_creates_nothing(self, db, tenant):
        """Die abgelehnte Buchung darf auch keine Zeile hinterlassen."""
        from app.models import Absence
        u = self._dayplan_user(db)
        _client(db, u).post("/api/absences", json={
            "date": "2026-03-03", "type": "sick", "hours": 8,
        })
        assert db.query(Absence).filter(Absence.user_id == u.id).count() == 0

    def test_range_with_one_bookable_day_still_succeeds(self, db, tenant):
        """Kontrolltest (Byte-Identitaet): sobald EIN Tag buchbar ist, bleibt
        alles wie bisher — Di frei, Mi gebucht (201, eine Zeile)."""
        u = self._dayplan_user(db)
        resp = _client(db, u).post("/api/absences", json={
            "date": "2026-03-03", "end_date": "2026-03-04", "type": "sick", "hours": 8,
        })
        assert resp.status_code == 201, resp.text
        rows = resp.json()
        assert [r["date"] for r in rows] == ["2026-03-04"]

    def test_normal_user_unaffected(self, db, tenant):
        """Kontrolltest: der Regelfall (gleichmaessige Woche) bleibt 201."""
        u = _user(db)
        resp = _client(db, u).post("/api/absences", json={
            "date": "2026-03-03", "type": "sick", "hours": 8,
        })
        assert resp.status_code == 201, resp.text
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# U2 (Serverseite): ein laufender Eintrag darf nicht in die Zukunft geschlossen
# werden
# ---------------------------------------------------------------------------

class TestClosingRunningEntryInTheFuture:

    # Startzeit + eingefrorene Uhr so gewaehlt, dass die §4-Pausenpruefung
    # (>6 h) nicht mitspricht — geprueft wird hier NUR die Zukunfts-Sperre.
    def _open_entry(self, db, user, start=time(13, 0)):
        e = TimeEntry(
            user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
            date=today_local(), start_time=start, end_time=None, break_minutes=0,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        return e

    def _freeze_now(self, monkeypatch, hour=14):
        """Die Router-lokale Uhr auf heute HH:00 festnageln (der Test darf nicht
        von der Laufzeit-Uhrzeit abhaengen)."""
        frozen = datetime.combine(today_local(), time(hour, 0)).replace(tzinfo=LOCAL_TZ)
        monkeypatch.setattr("app.routers.time_entries._now_local", lambda: frozen)

    def test_future_end_on_running_entry_is_rejected(self, db, tenant, monkeypatch):
        """RED: 17:00 ist um 12:00 noch nicht erreicht — der laufende Eintrag
        wurde trotzdem stillschweigend geschlossen (und beim naechsten
        Einstempeln entstand eine zweite, ueberlappende Zeile)."""
        u = _user(db)
        e = self._open_entry(db, u)
        self._freeze_now(monkeypatch, 14)
        resp = _client(db, u).put(f"/api/time-entries/{e.id}", json={"end_time": "17:00"})
        assert resp.status_code == 400, resp.text
        assert "Zukunft" in resp.json()["detail"]

    def test_rejected_entry_stays_open(self, db, tenant, monkeypatch):
        """Der abgelehnte PUT darf den Eintrag nicht halb schliessen."""
        u = _user(db)
        e = self._open_entry(db, u)
        self._freeze_now(monkeypatch, 14)
        _client(db, u).put(f"/api/time-entries/{e.id}", json={"end_time": "17:00"})
        db.expire_all()
        assert db.query(TimeEntry).filter(TimeEntry.id == e.id).first().end_time is None

    def test_past_end_on_running_entry_still_works(self, db, tenant, monkeypatch):
        """Kontrolltest: das legitime nachtraegliche Schliessen auf eine bereits
        vergangene Uhrzeit bleibt unveraendert erlaubt."""
        u = _user(db)
        e = self._open_entry(db, u)
        self._freeze_now(monkeypatch, 14)
        resp = _client(db, u).put(f"/api/time-entries/{e.id}", json={"end_time": "13:45"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["end_time"].startswith("13:45")

    def test_note_only_update_on_running_entry_unaffected(self, db, tenant, monkeypatch):
        """Kontrolltest: ein Teil-Update ohne ``end_time`` (genau das, was das
        Frontend nach dem Fix schickt) laesst den Eintrag offen und geht durch."""
        u = _user(db)
        e = self._open_entry(db, u)
        self._freeze_now(monkeypatch, 14)
        resp = _client(db, u).put(f"/api/time-entries/{e.id}", json={"note": "Nachtrag"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["end_time"] is None

    def test_closed_entry_is_not_touched_by_the_guard(self, db, tenant, monkeypatch):
        """Kontrolltest / bewusste Abgrenzung: die Sperre greift NUR beim
        Schliessen eines laufenden Eintrags. Ein bereits geschlossener Eintrag
        wird weiter unveraendert behandelt (der Anlege-Pfad laesst eine
        heutige Zukunftszeit ebenfalls zu; eine einseitige Sperre nur im PUT
        waere asymmetrisch — siehe Bericht)."""
        u = _user(db)
        e = TimeEntry(
            user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=today_local(),
            start_time=time(7, 0), end_time=time(10, 0), break_minutes=0,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        self._freeze_now(monkeypatch, 14)
        resp = _client(db, u).put(f"/api/time-entries/{e.id}", json={"end_time": "13:00"})
        assert resp.status_code == 200, resp.text

    def test_guard_ignores_other_days(self, db, tenant, monkeypatch):
        """Kontrolltest: die Sperre gilt nur fuer HEUTE — ein Admin, der einen
        alten offenen Eintrag nachtraeglich schliesst, ist nicht betroffen."""
        admin = _user(db, role=UserRole.ADMIN)
        e = TimeEntry(
            user_id=admin.id, tenant_id=DEFAULT_TENANT_ID,
            date=today_local() - timedelta(days=3),
            start_time=time(13, 0), end_time=None, break_minutes=0,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        self._freeze_now(monkeypatch, 14)
        resp = _client(db, admin).put(f"/api/time-entries/{e.id}", json={"end_time": "17:00"})
        assert resp.status_code == 200, resp.text
