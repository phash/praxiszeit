"""Vorschau vor einer Wochenstunden-Änderung.

Der Dialog muss VOR dem Speichern zeigen, was eine rückwirkende Änderung
anfasst — Zeitraum, altes/neues Tagessoll, Anzahl betroffener Abwesenheiten und
ob ein abgeschlossenes Jahr berührt wird. Und er muss die Fälle kennen, in denen
der Schreib-Endpoint ablehnen würde, damit der Nutzer nicht in einen 400 läuft.

Der Endpoint ist strikt lesend.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, User, UserRole, WorkingHoursChange, YearCarryover
from app.services import auth_service
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


def _client(db, admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: admin
    test_app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(test_app)


@pytest.fixture
def client(db, test_admin):
    c = _client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _url(user_id, eff, hours=20.0):
    return (f"/api/admin/users/{user_id}/working-hours-changes/preview"
            f"?effective_from={eff.isoformat()}&weekly_hours={hours}")


def _absence(db, user, d, typ=AbsenceType.VACATION, hours=8.0):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                type=typ, hours=hours, half_day=False)
    db.add(a); db.commit()
    return a


def _last_monday(before_days=30):
    """Ein Montag in der Vergangenheit — vermeidet Wochenend-Sonderfälle."""
    d = today_local() - timedelta(days=before_days)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return d


def _next_monday(after_days=14):
    """Ein Montag in der Zukunft — vermeidet Wochenend-Sonderfälle."""
    d = today_local() + timedelta(days=after_days)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def _last_sunday(before_days=30):
    """Ein SONNTAG in der Vergangenheit — für den Wochenend-Stichtag."""
    d = today_local() - timedelta(days=before_days)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


class TestRetroactiveDetection:
    def test_future_date_is_not_retroactive(self, client, test_user):
        r = client.get(_url(test_user.id, today_local() + timedelta(days=7)))
        assert r.status_code == 200, r.text
        assert r.json()["is_retroactive"] is False
        assert r.json()["affected_absences"] == 0

    def test_today_is_not_retroactive(self, client, test_user):
        r = client.get(_url(test_user.id, today_local()))
        assert r.status_code == 200, r.text
        assert r.json()["is_retroactive"] is False

    def test_yesterday_is_retroactive(self, client, test_user):
        r = client.get(_url(test_user.id, today_local() - timedelta(days=1)))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_retroactive"] is True
        assert body["period_end"] == today_local().isoformat()


class TestNumbers:
    def test_counts_affected_absences(self, client, db, test_user):
        mon = _last_monday()
        _absence(db, test_user, mon)
        _absence(db, test_user, mon + timedelta(days=1))
        r = client.get(_url(test_user.id, mon))
        assert r.json()["affected_absences"] == 2

    def test_overtime_is_not_counted(self, client, db, test_user):
        mon = _last_monday()
        _absence(db, test_user, mon, AbsenceType.OVERTIME)
        assert client.get(_url(test_user.id, mon)).json()["affected_absences"] == 0

    def test_reports_old_and_new_daily_target(self, client, test_user):
        r = client.get(_url(test_user.id, _last_monday(), hours=20.0))
        body = r.json()
        assert body["current_daily_target"] == 8.0
        assert body["new_daily_target"] == 4.0

    def test_weekend_effective_date_still_reports_the_contract_targets(self, client, db, test_user):
        """Fund 3 (Release-Review 1.17.0): Das Wirkungsdatum ist typischerweise
        ein Monatserster — 4 der 12 Monatsersten 2026 fallen auf ein Wochenende.
        Die Vorschau berechnete beide Tagessoll-Werte für GENAU diesen Stichtag,
        und ``get_daily_target_for_date`` liefert am Wochenende hart 0 → der
        Dialog zeigte „Tagessoll 0.0h → 0.0h. N Abwesenheit(en) betroffen." Die
        beiden Zahlen widersprachen sich, und der einzige quantitative Beleg vor
        einer §16-relevanten Freigabe war wertlos."""
        sunday = _last_sunday()
        assert sunday.weekday() >= 5, "Vorbedingung: Stichtag ist ein Wochenendtag"
        # Eine Abwesenheit an einem WERKTAG im Zeitraum: affected_absences > 0,
        # während die Tagessoll-Anzeige 0.0 → 0.0 behauptete.
        _absence(db, test_user, sunday + timedelta(days=1))

        body = client.get(_url(test_user.id, sunday, hours=20.0)).json()

        assert body["current_daily_target"] == 8.0
        assert body["new_daily_target"] == 4.0
        assert body["affected_absences"] == 1

    def test_preview_changes_nothing(self, client, db, test_user):
        """Strikt lesend — weder Abwesenheit noch Historie darf sich bewegen."""
        mon = _last_monday()
        a = _absence(db, test_user, mon)
        client.get(_url(test_user.id, mon))
        db.refresh(a)
        assert float(a.hours) == 8.0
        assert db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == test_user.id
        ).count() == 0


class TestEffectWindow:
    """Release-Review 1.17.0: ``period_end``/``affected_absences`` bilden den
    WIRKUNGSBEREICH der Änderung ab (bis zum Tag vor der nächsten Änderung,
    sonst offen — praktisch bis zur spätesten gebuchten Abwesenheit), nicht
    „bis heute". Sonst korrigiert das Speichern still Daten, die die Vorschau
    dem Admin nie angekündigt hat.

    ``is_retroactive`` behält bewusst seine Bedeutung: „Datum liegt vor heute" —
    genau die Aussage, die der Admin im Warnhinweis liest.
    """

    def test_future_date_with_booked_absence_is_counted(self, client, db, test_user):
        eff = _next_monday(after_days=14)
        absence_day = eff + timedelta(days=1)
        _absence(db, test_user, absence_day, AbsenceType.TRAINING)

        body = client.get(_url(test_user.id, eff)).json()

        assert body["is_retroactive"] is False, "Bedeutung unverändert: Datum ab heute"
        assert body["affected_absences"] == 1, "die bereits gebuchte Zeile wird angefasst"
        assert body["period_start"] == eff.isoformat()
        assert body["period_end"] == absence_day.isoformat()

    def test_period_end_stops_before_the_next_change(self, client, db, test_user):
        first = _next_monday(after_days=7)
        second = first + timedelta(days=28)
        db.add(WorkingHoursChange(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=second, weekly_hours=Decimal("40.0"),
        ))
        db.commit()
        _absence(db, test_user, first + timedelta(days=1), AbsenceType.TRAINING)
        _absence(db, test_user, second + timedelta(days=1), AbsenceType.TRAINING)

        body = client.get(_url(test_user.id, first)).json()

        assert body["period_end"] == (second - timedelta(days=1)).isoformat()
        assert body["affected_absences"] == 1, "nur die Zeile im eigenen Wirkungsbereich"

    def test_retroactive_period_end_extends_to_a_future_absence(self, client, db, test_user):
        mon = _last_monday()
        future_day = _next_monday(after_days=7) + timedelta(days=1)
        _absence(db, test_user, mon)
        _absence(db, test_user, future_day, AbsenceType.TRAINING)

        body = client.get(_url(test_user.id, mon)).json()

        assert body["is_retroactive"] is True
        assert body["period_end"] == future_day.isoformat()
        assert body["affected_absences"] == 2


class TestBlockedReasons:
    def test_daily_schedule_user_is_blocked(self, client, db, test_user):
        test_user.use_daily_schedule = True
        db.commit()
        body = client.get(_url(test_user.id, _last_monday())).json()
        assert body["blocked_reason"] is not None
        assert "Tagesplan" in body["blocked_reason"]

    def test_duplicate_date_is_blocked(self, client, db, test_user):
        eff = _last_monday()
        db.add(WorkingHoursChange(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=eff, weekly_hours=Decimal("30.0"),
        ))
        db.commit()
        body = client.get(_url(test_user.id, eff)).json()
        assert body["blocked_reason"] is not None
        assert "existiert bereits" in body["blocked_reason"]

    def test_normal_case_is_not_blocked(self, client, test_user):
        assert client.get(_url(test_user.id, _last_monday())).json()["blocked_reason"] is None

    def test_duplicate_date_reports_zero_affected_absences(self, client, db, test_user):
        """Regression: blockiert wegen Duplikat-Datum -> KEIN Dry-Run-Insert, also
        affected_absences bleibt 0.

        Ohne das `not blocked_reason`-Gate würde der Endpoint trotzdem eine
        temporäre WorkingHoursChange-Zeile mit demselben effective_from einfügen
        und flushen. get_weekly_hours_for_date hat keine Sekundärsortierung und
        wählt reproduzierbar die BESTEHENDE Zeile — die Zählung liefe dann gegen
        den falschen Wochenstunden-Wert. Mit zwei Abwesenheiten im Zeitraum würde
        das ohne den Fix affected_absences == 2 statt 0 liefern.
        """
        eff = _last_monday()
        db.add(WorkingHoursChange(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=eff, weekly_hours=Decimal("30.0"),
        ))
        db.commit()
        _absence(db, test_user, eff)
        _absence(db, test_user, eff + timedelta(days=1))
        body = client.get(_url(test_user.id, eff)).json()
        assert body["blocked_reason"] is not None
        assert body["affected_absences"] == 0


class TestClosedYears:
    def test_closed_year_is_reported(self, client, db, test_user):
        """Ein Jahr gilt als abgeschlossen, wenn ein YearCarryover für Y+1 existiert."""
        last_year = today_local().year - 1
        db.add(YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            year=last_year + 1, overtime_hours=Decimal("0"),
            vacation_days=Decimal("0"), source="year_closing",
        ))
        db.commit()
        r = client.get(_url(test_user.id, date(last_year, 6, 1)))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["closed_year_warning"] is not None
        assert body["closed_years"] == [last_year]

    def test_open_year_has_no_warning(self, client, test_user):
        body = client.get(_url(test_user.id, _last_monday())).json()
        assert body["closed_year_warning"] is None
        assert body["closed_years"] == []

    def test_multiple_closed_years_are_all_reported(self, client, db, test_user):
        """Ein Zeitraum über ZWEI abgeschlossene Jahre -> beide in closed_years,
        nicht nur das früheste (closed_year_warning bleibt bewusst auf das
        früheste beschränkt — reiner Anzeigetext)."""
        first_year = today_local().year - 2
        second_year = today_local().year - 1
        for y in (first_year, second_year):
            db.add(YearCarryover(
                user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
                year=y + 1, overtime_hours=Decimal("0"),
                vacation_days=Decimal("0"), source="year_closing",
            ))
        db.commit()
        r = client.get(_url(test_user.id, date(first_year, 6, 1)))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["closed_years"] == [first_year, second_year]
        assert body["closed_year_warning"] is not None
        assert str(first_year) in body["closed_year_warning"]


class TestAuthorization:
    def test_foreign_tenant_user_is_404(self, client, db):
        foreign = User(
            username="wh_foreign", email="wh_foreign@x.de",
            password_hash=auth_service.hash_password("Test2025!Password"),
            first_name="F", last_name="T", role=UserRole.EMPLOYEE,
            weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
            is_active=True, tenant_id=uuid.uuid4(),
        )
        db.add(foreign); db.commit(); db.refresh(foreign)
        assert client.get(_url(foreign.id, _last_monday())).status_code == 404

    def test_employee_is_forbidden(self, db, test_user):
        """Ohne require_admin-Override greift die echte Rolle."""
        def _override_db():
            yield db
        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = lambda: test_user
        try:
            c = TestClient(test_app)
            assert c.get(_url(test_user.id, _last_monday())).status_code == 403
        finally:
            test_app.dependency_overrides.clear()
