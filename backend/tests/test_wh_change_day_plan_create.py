"""#431: Tagesplan-Änderungen über den Stundenverlauf-Endpoint.

Mitarbeitende mit individuellem Tagesplan waren von der Stunden-Historie
ausgeschlossen (HTTP 400) — ihr Tagessoll kam live aus
``users.hours_monday…friday``, eine Historien-Zeile hätte darauf keinerlei
Wirkung gehabt und nur einen still falschen §16-Beleg erzeugt (UI zeigt den
neuen Wert, das Soll rechnet mit dem alten).

Seit #431 trägt ``working_hours_changes`` den VOLLSTÄNDIGEN Vertrags-Snapshot
(Modus + Tageswerte + Arbeitstage + Wochenstunden) und ``get_schedule_for_date``
löst ihn je Datum auf. Dieser Schreibpfad füllt den Snapshot, damit die Sperre
fallen kann.

Die Tests fahren bewusst über HTTP (``TestClient``): nur so wird auch die
Schema-Validierung (422) und die Serialisierung der neuen Response-Felder
geprüft. ``admin_headers`` braucht es dafür nicht — die Auth-Dependencies sind
wie in ``test_wh_change_preview.py`` überschrieben.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, WorkingHoursChange
from app.services import calculation_service
from app.services.timezone_service import today_local
from tests.test_endpoints import test_app


@pytest.fixture
def client(db, test_admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def _url(user_id):
    return f"/api/admin/users/{user_id}/working-hours-changes"


def _next_monday(after_days=14):
    """Ein Montag in der Zukunft — vermeidet Wochenend-Sonderfälle."""
    d = today_local() + timedelta(days=after_days)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def _rows(db, user):
    return (
        db.query(WorkingHoursChange)
        .filter(WorkingHoursChange.user_id == user.id)
        .order_by(WorkingHoursChange.effective_from)
        .all()
    )


class TestDayPlanRowIsCreated:
    def test_creates_day_plan_row(self, client, db, day_plan_user):
        r = client.post(
            _url(day_plan_user.id),
            json={
                "effective_from": str(today_local() + timedelta(days=30)),
                "use_daily_schedule": True,
                "hours_monday": 8.0, "hours_tuesday": 5.0, "hours_wednesday": 4.0,
                "work_days_per_week": 3,
                "note": "Teilzeit",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["use_daily_schedule"] is True
        assert body["hours_monday"] == 8.0
        assert body["hours_tuesday"] == 5.0
        assert body["hours_wednesday"] == 4.0
        assert body["hours_thursday"] is None
        assert body["hours_friday"] is None
        assert body["work_days_per_week"] == 3
        # Serverseitig als Summe der Tageswerte gesetzt — der Client schickt im
        # Tagesplan-Modus keinen eigenen Wochenstunden-Wert.
        assert body["weekly_hours"] == 17.0

    def test_snapshot_is_persisted_not_just_echoed(self, client, db, day_plan_user):
        """Die Snapshot-Spalten müssen in der DB stehen — eine Zeile mit
        ``use_daily_schedule=False`` (Column-Default) kippte den Mitarbeitenden
        ab ihrem Wirkungsdatum still in den Wochenstunden-Modus."""
        eff = _next_monday()
        r = client.post(
            _url(day_plan_user.id),
            json={
                "effective_from": str(eff),
                "use_daily_schedule": True,
                "hours_monday": 4.0, "hours_tuesday": 5.0, "hours_wednesday": 4.0,
                "work_days_per_week": 3,
            },
        )
        assert r.status_code == 201, r.text

        row = [c for c in _rows(db, day_plan_user) if c.effective_from == eff][0]
        assert row.use_daily_schedule is True
        assert Decimal(str(row.hours_monday)) == Decimal("4.00")
        assert Decimal(str(row.hours_tuesday)) == Decimal("5.00")
        assert Decimal(str(row.hours_wednesday)) == Decimal("4.00")
        assert row.hours_thursday is None
        assert row.hours_friday is None
        assert row.work_days_per_week == 3
        assert Decimal(str(row.weekly_hours)) == Decimal("13.0")

    def test_change_actually_moves_the_daily_target(self, client, db, day_plan_user):
        """Der ursprüngliche Grund für die 400-Sperre: eine Historien-Zeile war
        für diese Gruppe wirkungslos. Genau das muss jetzt nachweisbar anders
        sein — vor dem Wirkungsdatum gilt der alte Montag (8 h), ab dem
        Wirkungsdatum der neue (4 h)."""
        eff = _next_monday()
        r = client.post(
            _url(day_plan_user.id),
            json={
                "effective_from": str(eff),
                "use_daily_schedule": True,
                "hours_monday": 4.0, "hours_tuesday": 5.0, "hours_wednesday": 4.0,
                "work_days_per_week": 3,
            },
        )
        assert r.status_code == 201, r.text

        db.expire_all()
        emp = db.query(User).filter(User.id == day_plan_user.id).first()

        before = eff - timedelta(days=7)
        assert calculation_service.get_daily_target_for_date(
            emp, before,
            calculation_service.get_schedule_for_date(db, emp, before),
        ) == Decimal("8.00"), "vor dem Wirkungsdatum der alte Tagesplan"
        assert calculation_service.get_daily_target_for_date(
            emp, eff,
            calculation_service.get_schedule_for_date(db, emp, eff),
        ) == Decimal("4.00"), "ab dem Wirkungsdatum der neue Tagesplan"


class TestSchemaValidation:
    def test_rejects_day_plan_without_any_hours(self, client, day_plan_user):
        r = client.post(
            _url(day_plan_user.id),
            json={"effective_from": str(today_local()), "use_daily_schedule": True},
        )
        assert r.status_code == 422, r.text

    def test_rejects_weekly_mode_without_weekly_hours(self, client, test_user):
        r = client.post(
            _url(test_user.id),
            json={"effective_from": str(today_local()), "use_daily_schedule": False},
        )
        assert r.status_code == 422, r.text

    def test_rejects_day_hours_in_weekly_mode(self, client, test_user):
        """Tagesstunden ohne Tagesplan-Modus wären inert — das Soll käme weiter
        aus ``weekly_hours / work_days_per_week``. Eine solche Zeile ist immer
        ein Eingabefehler."""
        r = client.post(
            _url(test_user.id),
            json={
                "effective_from": str(today_local()),
                "weekly_hours": 20.0,
                "hours_monday": 4.0,
            },
        )
        assert r.status_code == 422, r.text

    def test_rejects_day_plan_sum_above_60(self, client, day_plan_user):
        r = client.post(
            _url(day_plan_user.id),
            json={
                "effective_from": str(today_local()),
                "use_daily_schedule": True,
                "hours_monday": 13.0, "hours_tuesday": 13.0, "hours_wednesday": 13.0,
                "hours_thursday": 13.0, "hours_friday": 13.0,
            },
        )
        assert r.status_code == 422, r.text


class TestBaselineRow:
    def test_baseline_row_freezes_the_day_plan_past(self, client, db, day_plan_user):
        """Die erste Änderung eines Tagesplan-MA legt eine Basis-Zeile mit dem
        BISHERIGEN Plan an — sonst gälte der neue Plan rückwirkend für die
        gesamte Vergangenheit (``get_schedule_for_date`` fällt für jeden Tag vor
        der ersten Zeile auf die User-Felder zurück, und genau die überschreibt
        der Resync)."""
        r = client.post(
            _url(day_plan_user.id),
            json={
                "effective_from": str(today_local()),
                "use_daily_schedule": True,
                "hours_monday": 4.0, "hours_wednesday": 2.0, "work_days_per_week": 2,
            },
        )
        assert r.status_code == 201, r.text

        rows = _rows(db, day_plan_user)
        assert len(rows) == 2
        baseline = rows[0]
        assert baseline.effective_from < today_local()
        assert baseline.use_daily_schedule is True
        assert Decimal(str(baseline.hours_monday)) == Decimal("8.00")   # alter Plan
        assert Decimal(str(baseline.hours_tuesday)) == Decimal("5.00")
        assert Decimal(str(baseline.hours_wednesday)) == Decimal("4.00")
        assert baseline.work_days_per_week == 3
        assert "Ausgangswert" in (baseline.note or "")

    def test_baseline_row_when_only_the_mode_changes(self, client, db, day_plan_user):
        """Der Vergleich muss den VOLLEN Snapshot sehen, nicht nur die
        Wochenstunden: hier bleiben 17 h/Woche gleich, aber der Modus kippt."""
        r = client.post(
            _url(day_plan_user.id),
            json={
                "effective_from": str(today_local()),
                "use_daily_schedule": False,
                "weekly_hours": 17.0, "work_days_per_week": 3,
            },
        )
        assert r.status_code == 201, r.text

        rows = _rows(db, day_plan_user)
        assert len(rows) == 2, "Wochenstunden identisch, Modus verschieden → Basis-Zeile"
        assert rows[0].use_daily_schedule is True
        assert Decimal(str(rows[0].hours_monday)) == Decimal("8.00")

    def test_no_baseline_row_for_identical_weekly_snapshot(self, client, db, test_user):
        """Byte-Identität: ein gleichmäßiger MA ohne Änderung am Snapshot
        bekommt weiterhin KEINE Basis-Zeile (sonst entstünde eine
        Pseudo-Änderung)."""
        r = client.post(
            _url(test_user.id),
            json={"effective_from": str(today_local()), "weekly_hours": 40.0},
        )
        assert r.status_code == 201, r.text
        assert len(_rows(db, test_user)) == 1

    def test_no_baseline_row_for_inert_leftover_day_hours(self, client, db, test_user):
        """Ein MA, dem der Tagesplan früher abgeschaltet wurde, kann inerte
        ``hours_*``-Reste auf der User-Zeile tragen (``update_user`` räumt sie
        nicht ab). Im gleichmäßigen Modus treiben sie kein Soll — sie dürfen
        deshalb keine Basis-Zeile auslösen, sonst verhielte sich ein
        gleichmäßiger MA anders als vor #431."""
        test_user.hours_monday = 8.0
        test_user.hours_tuesday = 8.0
        db.commit()

        r = client.post(
            _url(test_user.id),
            json={"effective_from": str(today_local()), "weekly_hours": 40.0},
        )
        assert r.status_code == 201, r.text
        assert len(_rows(db, test_user)) == 1


class TestUserRowResync:
    def test_mode_switch_to_weekly(self, client, db, day_plan_user):
        r = client.post(
            _url(day_plan_user.id),
            json={
                "effective_from": str(today_local()),
                "use_daily_schedule": False,
                "weekly_hours": 20.0, "work_days_per_week": 5,
            },
        )
        assert r.status_code == 201, r.text
        db.refresh(day_plan_user)
        assert day_plan_user.use_daily_schedule is False
        assert Decimal(str(day_plan_user.weekly_hours)) == Decimal("20.0")
        assert day_plan_user.hours_monday is None
        assert day_plan_user.hours_tuesday is None
        assert day_plan_user.hours_wednesday is None
        assert day_plan_user.work_days_per_week == 5

    def test_switch_into_day_plan(self, client, db, test_user):
        """Gegenrichtung: ein gleichmäßiger MA wechselt in den Tagesplan."""
        r = client.post(
            _url(test_user.id),
            json={
                "effective_from": str(today_local()),
                "use_daily_schedule": True,
                "hours_monday": 6.0, "hours_tuesday": 6.0, "hours_wednesday": 6.0,
                "work_days_per_week": 3,
            },
        )
        assert r.status_code == 201, r.text
        db.refresh(test_user)
        assert test_user.use_daily_schedule is True
        assert Decimal(str(test_user.hours_monday)) == Decimal("6.00")
        assert Decimal(str(test_user.weekly_hours)) == Decimal("18.0")
        assert test_user.work_days_per_week == 3

    def test_future_dated_change_leaves_user_row_alone(self, client, db, day_plan_user):
        """Unverändert: erst ab dem Wirkungsdatum zieht die User-Zeile nach."""
        r = client.post(
            _url(day_plan_user.id),
            json={
                "effective_from": str(_next_monday()),
                "use_daily_schedule": True,
                "hours_monday": 4.0, "hours_tuesday": 4.0, "work_days_per_week": 2,
            },
        )
        assert r.status_code == 201, r.text
        db.refresh(day_plan_user)
        assert Decimal(str(day_plan_user.hours_monday)) == Decimal("8.00")
        assert day_plan_user.work_days_per_week == 3


class TestListingStaysReadable:
    """Die Modus-Validierung sitzt bewusst NUR am Create-Schema. Säße sie an
    ``WorkingHoursChangeBase``, liefe sie auch beim Lesen (``from_attributes``)
    — und Bestandszeilen, die sie verletzen, wären dann nicht mehr abrufbar
    (HTTP 500 statt Liste). Solche Zeilen gibt es real: der 067-Backfill setzt
    ``use_daily_schedule`` aus der User-Zeile, ohne dass dort Tagesstunden
    gesetzt sein müssten."""

    def test_legacy_row_without_day_hours_is_still_listable(self, client, db, day_plan_user):
        db.add(WorkingHoursChange(
            user_id=day_plan_user.id,
            tenant_id=day_plan_user.tenant_id,
            effective_from=today_local() - timedelta(days=365),
            weekly_hours=Decimal("17.0"),
            use_daily_schedule=True,      # Backfill-Zustand, keine Tageswerte
        ))
        db.commit()

        r = client.get(_url(day_plan_user.id))
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1
        assert r.json()[0]["hours_monday"] is None


class TestSnapshotCompleteness:
    def test_weekly_row_freezes_work_days_per_week(self, client, db, test_user):
        """Das Modell sagt: „neue Zeilen setzen ihn immer" — NULL bedeutet
        Rückfall auf die (veränderliche) User-Zeile und wäre kein vollständiger
        Snapshot."""
        r = client.post(
            _url(test_user.id),
            json={"effective_from": str(today_local()), "weekly_hours": 20.0},
        )
        assert r.status_code == 201, r.text
        for row in _rows(db, test_user):
            assert row.work_days_per_week == 5

    def test_weekly_row_has_no_day_hours(self, client, db, test_user):
        r = client.post(
            _url(test_user.id),
            json={"effective_from": str(today_local()), "weekly_hours": 20.0},
        )
        assert r.status_code == 201, r.text
        row = [c for c in _rows(db, test_user) if c.effective_from == today_local()][0]
        assert row.use_daily_schedule is False
        assert row.hours_monday is None
        assert row.hours_friday is None
