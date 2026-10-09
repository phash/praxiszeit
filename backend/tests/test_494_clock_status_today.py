"""#494: ``GET /api/time-entries/clock-status`` liefert das Tages-Ist und das
Tagessoll von heute mit.

Die mobile Stempelkarte zeigte „x von y h heute" bisher aus ``elapsed_minutes``
— das ist allein die Laufzeit des gerade OFFENEN Eintrags. Bei geteilten
Diensten (Vormittag + Nachmittag, in Praxen die Regel) fehlte damit der bereits
abgeschlossene Block, und nach dem Ausstempeln sprang die Anzeige auf 0:00.

``today_net_minutes`` = Σ ``net_hours`` der heute abgeschlossenen Einträge
(gekappte Zeit, Pause abgezogen — derselbe Wert, der ins Ist geht) + laufende
Netto-Minuten des offenen Eintrags.

``today_target_hours`` = Tagessoll von heute aus dem DATUMSAUFGELÖSTEN
Vertrags-Snapshot (#431), nicht aus den Live-Feldern der User-Zeile, die das
Frontend vorher selbst las.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import TimeEntry
from app.models.working_hours_change import WorkingHoursChange
from tests.conftest import DEFAULT_TENANT_ID

# Donnerstag, wie im Ticket (Julia Wagner, 08.10.2026).
TODAY = dt.date(2026, 10, 8)


def _app() -> FastAPI:
    from app.routers import time_entries as te_router
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit #494 Test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(te_router.router)
    return app


_APP = _app()


@pytest.fixture
def frozen_now(monkeypatch):
    """Friert „jetzt" im time_entries-Router ein; Rückgabe: Setter für die Uhrzeit."""
    import app.routers.time_entries as te

    state = {"now": dt.datetime(2026, 10, 8, 17, 30)}
    monkeypatch.setattr(te, "_today_local", lambda: TODAY)
    monkeypatch.setattr(te, "_now_local", lambda: state["now"].replace(tzinfo=te.LOCAL_TZ))

    def set_time(h, m):
        state["now"] = dt.datetime(2026, 10, 8, h, m)

    return set_time


def _client(db, user):
    def override_db():
        yield db

    _APP.dependency_overrides[get_db] = override_db
    _APP.dependency_overrides[get_current_user] = lambda: user
    return TestClient(_APP)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _APP.dependency_overrides.clear()


def _entry(user, d, start, end, break_min=0):
    return TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                     start_time=start, end_time=end, break_minutes=break_min)


def test_abgeschlossene_bloecke_zaehlen_ohne_offenen_eintrag(db, test_user, frozen_now):
    """Reproduktion aus dem Ticket: 07:43–12:04 + 14:17–17:00, beide geschlossen →
    7:04 h (424 min), obwohl kein Eintrag offen ist."""
    db.add(_entry(test_user, TODAY, dt.time(7, 43), dt.time(12, 4)))
    db.add(_entry(test_user, TODAY, dt.time(14, 17), dt.time(17, 0)))
    db.commit()

    r = _client(db, test_user).get("/api/time-entries/clock-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_clocked_in"] is False
    assert body["today_net_minutes"] == 261 + 163


def test_offener_nachmittagsblock_plus_vormittag(db, test_user, frozen_now):
    """Während des Nachmittagsblocks: Vormittag (4:21) + laufende Minuten (1:10)."""
    frozen_now(15, 27)
    db.add(_entry(test_user, TODAY, dt.time(7, 43), dt.time(12, 4)))
    db.add(_entry(test_user, TODAY, dt.time(14, 17), None))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["is_clocked_in"] is True
    assert body["elapsed_minutes"] == 70  # unverändert: nur der offene Block
    assert body["today_net_minutes"] == 261 + 70


def test_pause_wird_abgezogen_und_andere_tage_zaehlen_nicht(db, test_user, frozen_now):
    db.add(_entry(test_user, TODAY, dt.time(8, 0), dt.time(14, 0), break_min=30))  # 5:30
    db.add(_entry(test_user, TODAY - dt.timedelta(days=1), dt.time(8, 0), dt.time(16, 0)))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_net_minutes"] == 330


def test_offener_block_vor_gekapptem_beginn_zaehlt_nicht_negativ(db, test_user, frozen_now):
    """Ein auf das Arbeitszeitfenster gekappter Beginn kann nach „jetzt" liegen
    (Einstempeln 06:40, Fenster ab 07:30). Das darf das Tages-Ist nicht senken."""
    frozen_now(6, 40)
    db.add(_entry(test_user, TODAY, dt.time(7, 30), None))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_net_minutes"] == 0


def test_ohne_eintraege_null(db, test_user, frozen_now):
    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["is_clocked_in"] is False
    assert body["today_net_minutes"] == 0


def test_tagessoll_gleichmaessig(db, test_user, frozen_now):
    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_target_hours"] == pytest.approx(8.0)  # 40 h / 5 Tage


def test_tagessoll_kommt_aus_dem_snapshot_nicht_aus_der_user_zeile(db, test_user, frozen_now):
    """#431: ab heute gilt ein Tagesplan Do 7 h — die User-Zeile trägt noch die
    alten 40 h / 5 Tage (8 h). Maßgeblich ist der Snapshot."""
    db.add(WorkingHoursChange(
        tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, effective_from=TODAY,
        weekly_hours=Decimal("23.00"), use_daily_schedule=True,
        hours_monday=Decimal("7.00"), hours_tuesday=Decimal("4.50"), hours_wednesday=None,
        hours_thursday=Decimal("7.00"), hours_friday=Decimal("4.50"), work_days_per_week=4,
    ))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_target_hours"] == pytest.approx(7.0)


def test_tagessoll_wochenende_null(db, test_user, monkeypatch):
    import app.routers.time_entries as te

    saturday = dt.date(2026, 10, 10)
    monkeypatch.setattr(te, "_today_local", lambda: saturday)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 10, 10, 10, 0, tzinfo=te.LOCAL_TZ))

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_target_hours"] == 0.0


def test_fremder_mandant_zaehlt_nicht(db, test_user, frozen_now):
    """F-026: Einträge mit fremder tenant_id (Fehlzuordnung) fließen nicht ein."""
    import uuid
    from app.models.tenant import Tenant

    other = uuid.UUID("00000000-0000-0000-0000-000000000002")
    db.add(Tenant(id=other, name="Other", slug="other", is_active=True, mode="single"))
    db.commit()
    db.add(TimeEntry(user_id=test_user.id, tenant_id=other, date=TODAY,
                     start_time=dt.time(8, 0), end_time=dt.time(10, 0), break_minutes=0))
    db.add(_entry(test_user, TODAY, dt.time(11, 0), dt.time(12, 0)))
    db.commit()

    body = _client(db, test_user).get("/api/time-entries/clock-status").json()
    assert body["today_net_minutes"] == 60


# ---------------------------------------------------------------------------
# Review F1: ``today_target_hours`` folgt der Soll-STRUKTUR des Tages.
#
# Vorher lieferte das Feld den reinen Wochentags-Vertragswert. Am Feiertag, im
# Urlaub, bei Krankheit oder am halben 24.12. zeigte die mobile Karte deshalb rot
# „Noch nicht eingestempelt — 0:00 von 8:00 h heute". Das Frontend blendet Rot
# und die Zeile „x von y" bei Tagessoll 0 aus — der Server muss also 0 liefern,
# wenn heute niemand stempeln muss.
# ---------------------------------------------------------------------------

def _at(monkeypatch, d, h=10, m=0):
    """Friert „heute" auf ``d`` ein (ohne die feste TODAY-Fixture)."""
    import app.routers.time_entries as te

    monkeypatch.setattr(te, "_today_local", lambda: d)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(d.year, d.month, d.day, h, m, tzinfo=te.LOCAL_TZ))


def _target(db, user):
    r = _client(db, user).get("/api/time-entries/clock-status")
    assert r.status_code == 200, r.text
    return r.json()["today_target_hours"]


def _absence(user, d, type_, half_day=None, start=None, end=None, hours="8.00", tenant_id=DEFAULT_TENANT_ID):
    from app.models import Absence

    return Absence(user_id=user.id, tenant_id=tenant_id, date=d, type=type_,
                   hours=Decimal(hours), half_day=half_day, start_time=start, end_time=end)


def test_tagessoll_feiertag_null(db, test_user, monkeypatch):
    """1. Weihnachtsfeiertag 2026 = Freitag: kein Soll, keine rote Karte."""
    from app.models import PublicHoliday

    xmas = dt.date(2026, 12, 25)
    db.add(PublicHoliday(date=xmas, name="1. Weihnachtstag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    _at(monkeypatch, xmas)

    assert _target(db, test_user) == 0.0


def test_tagessoll_feiertag_fremder_mandant_zaehlt_nicht(db, test_user, frozen_now):
    """F-026: ein Feiertag eines anderen Mandanten senkt das Soll nicht."""
    import uuid
    from app.models import PublicHoliday
    from app.models.tenant import Tenant

    other = uuid.UUID("00000000-0000-0000-0000-000000000002")
    db.add(Tenant(id=other, name="Other", slug="other", is_active=True, mode="single"))
    db.commit()
    db.add(PublicHoliday(date=TODAY, name="Fremd", year=2026, tenant_id=other))
    db.commit()

    assert _target(db, test_user) == pytest.approx(8.0)


@pytest.mark.parametrize("type_name", ["VACATION", "SICK", "TRAINING", "OVERTIME", "PAID_LEAVE", "OTHER"])
def test_tagessoll_ganztaegige_abwesenheit_null(db, test_user, frozen_now, type_name):
    """Ganztägig abwesend → heute muss niemand stempeln. Das gilt ausdrücklich
    auch für Krank/Fortbildung/Überstundenausgleich, die das Soll in der
    Saldo-Rechnung NICHT senken (Gutschrift bzw. Konto-Abbau) — die Karte zeigte
    dort sonst weiter rot."""
    from app.models import AbsenceType

    db.add(_absence(test_user, TODAY, getattr(AbsenceType, type_name)))
    db.commit()

    assert _target(db, test_user) == 0.0


def test_tagessoll_halber_urlaubstag(db, test_user, frozen_now):
    from app.models import AbsenceType

    db.add(_absence(test_user, TODAY, AbsenceType.VACATION, half_day=True, hours="4.00"))
    db.commit()

    assert _target(db, test_user) == pytest.approx(4.0)


def test_tagessoll_halb_krank_halb_urlaub_null(db, test_user, frozen_now):
    """Misch-Tag ½ Urlaub + ½ Krank deckt den ganzen Tag ab."""
    from app.models import AbsenceType

    db.add(_absence(test_user, TODAY, AbsenceType.VACATION, half_day=True, hours="4.00"))
    db.add(_absence(test_user, TODAY, AbsenceType.SICK, half_day=True, hours="4.00"))
    db.commit()

    assert _target(db, test_user) == 0.0


def test_tagessoll_abwesenheit_fremder_mandant_zaehlt_nicht(db, test_user, frozen_now):
    """F-026: eine Abwesenheit mit fremder tenant_id (Fehlzuordnung) senkt nichts."""
    import uuid
    from app.models import AbsenceType
    from app.models.tenant import Tenant

    other = uuid.UUID("00000000-0000-0000-0000-000000000002")
    db.add(Tenant(id=other, name="Other", slug="other", is_active=True, mode="single"))
    db.commit()
    db.add(_absence(test_user, TODAY, AbsenceType.SICK, tenant_id=other))
    db.commit()

    assert _target(db, test_user) == pytest.approx(8.0)


def test_tagessoll_stundenweise_abwesenheit_laesst_soll_stehen(db, test_user, frozen_now):
    """Bewusst: eine Abwesenheit mit Uhrzeiten (z. B. Arzttermin 08–10 Uhr)
    deckt nicht den ganzen Tag ab — die Mitarbeiterin kommt danach noch."""
    from app.models import AbsenceType

    db.add(_absence(test_user, TODAY, AbsenceType.OTHER, start=dt.time(8, 0), end=dt.time(10, 0), hours="2.00"))
    db.commit()

    assert _target(db, test_user) == pytest.approx(8.0)


def _special_day(db, key, mode):
    from app.models.system_setting import SystemSetting

    db.add(SystemSetting(key=key, value=mode, description=key, tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def test_tagessoll_halber_heiligabend(db, test_user, monkeypatch):
    """#146/#394: 24.12. als halber Arbeitstag → 0,5 × Tagessoll."""
    _special_day(db, "special_day_dec24_mode", "half_day")
    _at(monkeypatch, dt.date(2026, 12, 24))

    assert _target(db, test_user) == pytest.approx(4.0)


def test_tagessoll_freier_silvester(db, test_user, monkeypatch):
    _special_day(db, "special_day_dec31_mode", "free")
    _at(monkeypatch, dt.date(2026, 12, 31))

    assert _target(db, test_user) == 0.0


def test_tagessoll_vor_eintritt_null(db, test_user, frozen_now):
    """#193: vor dem ersten Arbeitstag gibt es kein Soll."""
    test_user.first_work_day = TODAY + dt.timedelta(days=7)
    db.commit()

    assert _target(db, test_user) == 0.0


def test_tagessoll_nach_austritt_null(db, test_user, frozen_now):
    test_user.last_work_day = TODAY - dt.timedelta(days=1)
    db.commit()

    assert _target(db, test_user) == 0.0


def test_tagessoll_ohne_stundenzaehlung_null(db, test_user, frozen_now):
    """#191: leitende Angestellte (track_hours=False) haben kein Tagessoll."""
    test_user.track_hours = False
    db.commit()

    assert _target(db, test_user) == 0.0


def _fixed_mode(db, user):
    """#377 Baustein 2b: festes Monats-Soll mit Tagesplan Do 3 h."""
    user.milog_working_time_account = True
    user.agreed_monthly_hours = Decimal("43.00")
    user.use_fixed_monthly_target = True
    user.use_daily_schedule = True
    user.weekly_hours = 10.0
    user.hours_monday = Decimal("4.00")
    user.hours_tuesday = Decimal("3.00")
    user.hours_thursday = Decimal("3.00")
    user.work_days_per_week = 3
    db.commit()


def test_tagessoll_fester_monatsmodus_geplante_stunden(db, test_user, frozen_now):
    """Fix-Modus: die Karte zeigt die geplanten Stunden des Wochentags (nicht den
    Monats-Anteil, den get_range_target für einen einzelnen Tag liefern würde)."""
    _fixed_mode(db, test_user)

    assert _target(db, test_user) == pytest.approx(3.0)


def test_tagessoll_fester_monatsmodus_feiertag_null(db, test_user, frozen_now):
    from app.models import PublicHoliday

    _fixed_mode(db, test_user)
    db.add(PublicHoliday(date=TODAY, name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()

    assert _target(db, test_user) == 0.0
