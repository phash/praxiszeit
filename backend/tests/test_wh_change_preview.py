"""Vorschau vor einer Wochenstunden-Änderung.

Der Dialog muss VOR dem Speichern zeigen, was eine rückwirkende Änderung
anfasst — Zeitraum, altes/neues Tagessoll, Anzahl betroffener Abwesenheiten und
ob ein abgeschlossenes Jahr berührt wird. Und er muss die Fälle kennen, in denen
der Schreib-Endpoint ablehnen würde, damit der Nutzer nicht in einen 400 läuft.

Der Endpoint ist strikt lesend.
"""
import uuid
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (Absence, AbsenceType, TimeEntry, User, UserRole,
                        WorkingHoursChange, YearCarryover)
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


def _first_monday_of_year():
    """Erster Montag des LAUFENDEN Jahres — liegt garantiert im selben Jahr wie
    ``date(today.year, 1, 1)`` (``_last_monday()`` kippt Anfang Januar ins
    Vorjahr und damit aus dem Urlaubsjahr der Vorschau heraus)."""
    d = date(today_local().year, 1, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def _preview(client, user, eff, **params):
    """Vorschau mit beliebigen Snapshot-Parametern (Tagesplan-Modus)."""
    return client.get(
        f"/api/admin/users/{user.id}/working-hours-changes/preview",
        params={"effective_from": eff.isoformat(), **params},
    )


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
    def test_daily_schedule_user_is_not_blocked_anymore(self, client, day_plan_user):
        """#431: Der Tagesplan-Zweig ist weg — seit Task 5 nimmt der POST solche
        Änderungen an, die Vorschau darf sie also nicht mehr als aussichtslos
        melden. Hier zusätzlich der Modus-WECHSEL Tagesplan → gleichmäßig:
        20 h auf 3 Arbeitstage = 6,67 h an jedem Wochentag."""
        body = client.get(_url(day_plan_user.id, _last_monday(), hours=20.0)).json()
        assert body["blocked_reason"] is None
        assert body["day_targets_current"] == [8.0, 5.0, 4.0, 0.0, 0.0]
        assert body["day_targets_new"] == [6.67] * 5

    def test_empty_day_plan_is_blocked(self, client, day_plan_user):
        """Tagesplan-Modus ohne einen einzigen Wochentag: der POST lehnte das mit
        derselben Begründung ab (``check_mode``) — die Vorschau meldet sie, statt
        den Dialog in einen Fehler laufen zu lassen, und zeigt KEINE erfundene
        Änderung an."""
        body = _preview(client, day_plan_user, today_local(),
                        use_daily_schedule=True, work_days_per_week=3).json()
        assert body["blocked_reason"] is not None
        assert "Wochentag" in body["blocked_reason"]
        assert body["day_targets_new"] == body["day_targets_current"]
        assert body["overtime_after"] == body["overtime_before"]

    def test_missing_weekly_hours_is_blocked(self, client, test_user):
        """Gleichmäßiger Modus ohne Wochenstunden — dieselbe Regel, andere Seite."""
        body = _preview(client, test_user, today_local()).json()
        assert body["blocked_reason"] is not None
        assert "Wochenstunden" in body["blocked_reason"]

    def test_value_above_the_limit_is_blocked_not_422(self, client, test_user):
        """Review-Fund 2: Die Zahlengrenzen leben ausschließlich im Schema, nicht
        zusätzlich an den Query-Parametern. Wer auf dem Weg zu „44,4" kurz „444"
        stehen hat, bekommt einen Hinweis — kein hartes 422 mitten im Tippen (der
        Endpoint feuert debounced bei jeder Eingabe)."""
        r = _preview(client, test_user, today_local(), weekly_hours=444)
        assert r.status_code == 200, r.text
        assert "60" in r.json()["blocked_reason"]

    def test_day_value_above_the_limit_is_blocked(self, client, day_plan_user):
        r = _preview(client, day_plan_user, today_local(), use_daily_schedule=True,
                     hours_monday=48, work_days_per_week=3)
        assert r.status_code == 200, r.text
        assert "24" in r.json()["blocked_reason"]

    def test_work_days_below_the_limit_is_blocked(self, client, test_user):
        r = _preview(client, test_user, today_local(),
                     weekly_hours=20.0, work_days_per_week=0)
        assert r.status_code == 200, r.text
        assert "Arbeitstage" in r.json()["blocked_reason"]

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


class TestDayPlanAndAccounts:
    """#431: Ein einzelner Skalar bildet einen Tagesplan nicht ab (Mo 8 / Di 0 /
    Mi 4), und die Bestätigungs-Checkbox stand bisher unter einer Zahl, die den
    Vorgang nicht beschreibt. Die Vorschau weist deshalb fünf Tagessoll-Paare
    sowie Saldo und Urlaub vorher/nachher aus."""

    def test_returns_five_day_pairs_for_day_plan(self, client, day_plan_user):
        r = _preview(client, day_plan_user, today_local(),
                     use_daily_schedule=True,
                     hours_monday=4.0, hours_tuesday=5.0, hours_wednesday=4.0,
                     work_days_per_week=3)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["blocked_reason"] is None          # frueher: Tagesplan-Sperre
        assert body["day_targets_current"] == [8.0, 5.0, 4.0, 0.0, 0.0]
        assert body["day_targets_new"] == [4.0, 5.0, 4.0, 0.0, 0.0]
        assert "overtime_before" in body and "overtime_after" in body
        assert "vacation_days_before" in body and "vacation_days_after" in body

    def test_scalar_daily_targets_are_the_mean_of_the_planned_days(self, client, day_plan_user):
        """``current_daily_target``/``new_daily_target`` bleiben Teil der API —
        als Mittel der Tage mit Soll > 0 (nicht über alle fünf Wochentage, sonst
        zöge ein freier Do/Fr den Wert künstlich nach unten)."""
        body = _preview(client, day_plan_user, today_local(),
                        use_daily_schedule=True,
                        hours_monday=4.0, hours_tuesday=5.0, hours_wednesday=4.0,
                        work_days_per_week=3).json()
        assert body["current_daily_target"] == 5.67   # (8+5+4)/3
        assert body["new_daily_target"] == 4.33       # (4+5+4)/3

    def test_overtime_reflects_the_hypothetical_change(self, client, db, day_plan_user):
        """Halbiertes Montags-Soll rueckwirkend => hoeherer Ueberstundensaldo."""
        mon = _last_monday()
        db.add(TimeEntry(user_id=day_plan_user.id, tenant_id=DEFAULT_TENANT_ID,
                         date=mon, start_time=time(8, 0), end_time=time(16, 0),
                         break_minutes=0))
        db.commit()
        body = _preview(client, day_plan_user, mon.replace(day=1),
                        use_daily_schedule=True,
                        hours_monday=4.0, hours_tuesday=5.0, hours_wednesday=4.0,
                        work_days_per_week=3).json()
        assert body["overtime_after"] > body["overtime_before"]

    def test_vacation_days_reflect_a_dropped_workday(self, client, db, day_plan_user):
        """Fällt der Montag aus dem Tagesplan, kostet ein Montags-Urlaub keinen
        Urlaubstag mehr (§3 BUrlG, tagebasiert) — genau das muss der Admin VOR
        dem Speichern sehen."""
        _absence(db, day_plan_user, _first_monday_of_year(), AbsenceType.VACATION)
        body = _preview(client, day_plan_user, date(today_local().year, 1, 1),
                        use_daily_schedule=True,
                        hours_monday=0, hours_tuesday=5.0, hours_wednesday=4.0,
                        work_days_per_week=2).json()
        assert body["vacation_days_before"] == 1.0
        assert body["vacation_days_after"] == 0.0

    def test_preview_writes_nothing(self, client, db, day_plan_user):
        before = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == day_plan_user.id).count()
        _preview(client, day_plan_user, today_local(),
                 use_daily_schedule=True, hours_monday=4.0, work_days_per_week=1)
        db.expire_all()
        assert db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == day_plan_user.id).count() == before

    def test_unchanged_snapshot_runs_no_simulation(self, client, db, test_user):
        """Review-Fund 1: Der Dialog ist mit den geltenden Werten vorbefüllt und
        feuert die Vorschau schon beim Öffnen — der unveränderte Snapshot ist der
        häufigste Fall überhaupt. Dann darf die Simulation gar nicht erst laufen:
        sie nimmt Zeilen-Schreibsperren auf die Abwesenheiten des Wirkungsfensters
        und hält sie über zwei volle Kontodurchrechnungen.

        Die abgedriftete Stundenzahl (6 h statt 8 h Tagessoll) macht das messbar:
        ein Retarget würde sie sofort anfassen und als ``affected_absences``
        auftauchen."""
        mon = _last_monday()
        _absence(db, test_user, mon, AbsenceType.VACATION, hours=6.0)

        same = client.get(_url(test_user.id, mon, hours=40.0)).json()
        assert same["blocked_reason"] is None
        assert same["affected_absences"] == 0, "keine Simulation, also nichts gezählt"
        assert same["overtime_after"] == same["overtime_before"]
        assert same["vacation_days_after"] == same["vacation_days_before"]
        assert same["day_targets_new"] == same["day_targets_current"]

        # Gegenprobe: dieselbe Ausgangslage mit ABWEICHENDEN Wochenstunden
        # simuliert sehr wohl — sonst wäre die Assertion oben wertlos.
        changed = client.get(_url(test_user.id, mon, hours=20.0)).json()
        assert changed["affected_absences"] == 1

    def test_unchanged_day_plan_runs_no_simulation(self, client, db, day_plan_user):
        """Derselbe Ausstieg im Tagesplan-Modus — der Vergleich läuft über
        ``_comparable_snapshot``, also über alle vier Snapshot-Werte."""
        mon = _last_monday()
        _absence(db, day_plan_user, mon, AbsenceType.VACATION, hours=6.0)
        body = _preview(client, day_plan_user, mon, use_daily_schedule=True,
                        hours_monday=8.0, hours_tuesday=5.0, hours_wednesday=4.0,
                        work_days_per_week=3).json()
        assert body["blocked_reason"] is None
        assert body["affected_absences"] == 0
        assert body["day_targets_new"] == body["day_targets_current"] == [8.0, 5.0, 4.0, 0.0, 0.0]

    def test_overtime_month_bound_matches_the_live_views(self, client, db, test_user, monkeypatch):
        """Review-Fund 4: Die Monatsobergrenze von ``get_overtime_account`` ist
        HEUTE, nicht der Saldo-Stichtag — genau wie in ``dashboard.get_overtime_account``
        und ``users_overview`` (``now.year, now.month`` + ``cutoff_date=cutoff``).

        Am 1. Januar vor dem ersten Ausstempeln liegt der Stichtag im Vorjahr.
        ``get_overtime_account`` wählt seinen Startpunkt über
        ``YearCarryover.year <= up_to_year``; mit der Vorjahres-Obergrenze fände
        es den Carryover des laufenden Jahres NICHT und lieferte einen anderen
        Wert als das Dashboard, gegen das der Admin den Dialog vergleicht.

        Hier nachgestellt: Stichtag ins Vorjahr gezogen, Carryover 99 h im
        laufenden Jahr. Obergrenze „heute" ⇒ 99.0; Obergrenze „Stichtag" ⇒ 0.0.
        """
        year = today_local().year
        db.add(YearCarryover(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, year=year,
            overtime_hours=Decimal("99"), vacation_days=Decimal("0"), source="manual",
        ))
        db.commit()
        monkeypatch.setattr(
            "app.services.calculation_service.get_soll_cutoff_date",
            lambda _db, _user, today=None: date(year - 1, 12, 31),
        )

        body = client.get(_url(test_user.id, date(year, 1, 1), hours=20.0)).json()

        assert body["overtime_before"] == 99.0

    def test_rollback_holds_even_if_the_flush_raises(self, client, db, test_user, monkeypatch):
        """Review-Fund 3: ``db.add``/``db.flush`` liegen MIT im ``try``. Wirft
        schon der Flush (z. B. ein Race zwischen Duplikat-Prüfung und Insert),
        darf es keinen Ausstiegspfad an der Rollback-Garantie vorbei geben.

        Beobachtbar ist das an der SESSION, nicht an der Datenbank: ohne den
        Rollback bleibt die hypothetische Zeile als ``pending`` in der Session
        hängen und würde von einem späteren ``commit()` auf derselben Session
        mitgeschrieben. (In Produktion stirbt die Session am Requestende, der
        Schaden bleibt dort theoretisch — die Garantie des Docstrings soll
        trotzdem lückenlos gelten.)"""
        mon = _last_monday()
        _absence(db, test_user, mon)

        def boom(*args, **kwargs):
            raise RuntimeError("simulierter Flush-Fehler")

        monkeypatch.setattr(db, "flush", boom)
        with pytest.raises(RuntimeError):
            client.get(_url(test_user.id, mon))
        monkeypatch.undo()

        assert not [o for o in db.new if isinstance(o, WorkingHoursChange)], \
            "die hypothetische Zeile hängt nach dem Fehler noch als pending in der Session"
        db.commit()
        assert db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == test_user.id).count() == 0

    def test_simulated_retarget_is_rolled_back(self, client, db, day_plan_user):
        """Der Saldo „nachher" muss gegen die NACHGEZOGENEN Abwesenheits-Stunden
        gerechnet werden (sonst schriebe ein Krankentag weiterhin die alten 8 h
        dem Ist gut, waehrend das Soll schon auf 4 h steht — ein Phantom-Plus,
        das nach dem Speichern verschwindet). Genau diese Simulation darf aber
        nichts hinterlassen."""
        mon = _last_monday()
        a = _absence(db, day_plan_user, mon, AbsenceType.SICK, hours=8.0)
        body = _preview(client, day_plan_user, mon,
                        use_daily_schedule=True,
                        hours_monday=4.0, hours_tuesday=5.0, hours_wednesday=4.0,
                        work_days_per_week=3).json()
        assert body["affected_absences"] == 1
        db.expire_all()
        db.refresh(a)
        assert float(a.hours) == 8.0, "die Simulation darf die Stunden nicht persistieren"


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
