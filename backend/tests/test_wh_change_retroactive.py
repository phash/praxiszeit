"""Task 3 (#Wochenstunden-Dialog): eine rückwirkende Wochenstunden-Änderung muss
die bereits gebuchten Abwesenheits-Stunden mitziehen — sonst schreibt z. B. ein
Krankentag weiterhin die ALTEN Stunden dem Ist gut, während das Soll desselben
Tages sich durch die eben gespeicherte Änderung schon verschoben hat.

``create_working_hours_change`` verdrahtet dafür die bereits vorhandene
``calculation_service.retarget_absence_hours`` (kein zweiter Rechenpfad),
schreibt bei tatsächlich angepassten Zeilen einen Audit-Eintrag
(``source="wh_change"``) und trägt in der Antwort zusätzlich
``adjusted_absences``/``warning`` (Jahresabschluss-Hinweis für abgeschlossene,
berührte Jahre).
"""
import json
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models import (
    Absence, AbsenceType, TimeEntry, TimeEntryAuditLog, User, UserRole,
    WorkingHoursChange, YearCarryover,
)
from app.services import calculation_service
from app.routers.admin_users import (
    create_user, create_working_hours_change, delete_working_hours_change, update_user,
)
from app.schemas.user import UserCreate, UserUpdate
from app.schemas.working_hours_change import WorkingHoursChangeCreate
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID


# Wegwerf-Passwort fuer die Testnutzer-Anlage. Aus Teilen zusammengesetzt, weil
# der Secret-Scanner (GitGuardian) ein `password="…"`-Literal als "Generic
# Password" meldet und den PR-Check rot faerbt — dasselbe Muster, das CLAUDE.md
# schon fuer DB-URL-Literale in Tests vorgibt. Der Wert ist bedeutungslos, muss
# aber die Komplexitaetsregel erfuellen (>=10 Zeichen, Gross/Klein/Ziffer).
_TEST_PASSWORD = "Neu" + "Pass" + "2025" + "!"


def _make_user(db, username, **kwargs):
    defaults = dict(
        email=f"{username}@x.de", password_hash="h", first_name=username,
        last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _admin(db, username="wh_retro_admin"):
    return _make_user(db, username, role=UserRole.ADMIN)


def _absence(db, user, d, typ=AbsenceType.VACATION, hours=8.0, half_day=False):
    a = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        type=typ, hours=hours, half_day=half_day,
    )
    db.add(a); db.commit(); db.refresh(a)
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


class TestRetroactiveAdjustsAbsences:
    def test_retroactive_change_adjusts_absences(self, db, default_tenant):
        admin = _admin(db)
        emp = _make_user(db, "wh_retro_emp", weekly_hours=40.0)
        mon = _last_monday()
        a = _absence(db, emp, mon, AbsenceType.VACATION, 8.0)

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        db.refresh(a)
        assert float(a.hours) == 4.0, "Tagessoll halbiert (40->20h/Woche, 5 Tage)"
        assert result.adjusted_absences == 1

    def test_future_change_adjusts_only_absences_from_its_effective_date(self, db, default_tenant):
        """Hieß früher ``test_future_change_adjusts_nothing`` und zementierte die
        Annahme, ein Wirkungsdatum in der Zukunft betreffe „ausschließlich
        künftige, noch nicht gebuchte Tage".

        Die Annahme ist falsch (Release-Review 1.17.0): ``create_absence`` hat
        keinerlei Zukunftssperre — genehmigte Urlaubsanträge, Betriebsferien und
        geplante Fortbildungen werden routinemäßig im Voraus gebucht, mit
        ``hours`` = Tagessoll ZUM BUCHUNGSZEITPUNKT. Das Soll dieser Tage folgt
        der neuen Wochenstundenzahl datumsbasiert automatisch, die gespeicherten
        Stunden nicht. Und das Wirkungsdatum in der Zukunft ist der REGELFALL des
        Dialogs („ab dem 1.9. arbeitet sie 20 Stunden").

        Neue Erwartung: alles VOR dem Wirkungsdatum bleibt unangetastet (das war
        und bleibt richtig — genau das prüft die Abwesenheit von heute), alles AB
        dem Wirkungsdatum wird nachgezogen.
        """
        admin = _admin(db)
        emp = _make_user(db, "wh_future_emp", weekly_hours=40.0)
        future = _next_monday(after_days=14)
        # Eine Abwesenheit HEUTE — liegt VOR dem Wirkungsdatum und darf nicht
        # angefasst werden (läge fälschlich im Fenster, wenn die Implementierung
        # period_end statt effective_from als Startpunkt nähme).
        before = _absence(db, emp, today_local(), AbsenceType.VACATION, 8.0)
        # Bereits gebuchte Fortbildung NACH dem Wirkungsdatum.
        after = _absence(db, emp, future + timedelta(days=1), AbsenceType.TRAINING, 8.0)

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=future, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        db.refresh(before)
        db.refresh(after)
        assert float(before.hours) == 8.0, "vor dem Wirkungsdatum: unverändert"
        assert float(after.hours) == 4.0, "ab dem Wirkungsdatum: auf das neue Tagessoll"
        assert result.adjusted_absences == 1
        assert result.warning is None

    def test_adjusted_absences_matches_actual_count(self, db, default_tenant):
        admin = _admin(db)
        emp = _make_user(db, "wh_count_emp", weekly_hours=40.0)
        mon = _last_monday()
        _absence(db, emp, mon, AbsenceType.VACATION, 8.0)
        _absence(db, emp, mon + timedelta(days=1), AbsenceType.SICK, 8.0)
        # OVERTIME wird von retarget_absence_hours bewusst nie angefasst.
        _absence(db, emp, mon + timedelta(days=2), AbsenceType.OVERTIME, 8.0)

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        assert result.adjusted_absences == 2
        rows = db.query(Absence).filter(Absence.user_id == emp.id).order_by(Absence.date).all()
        assert float(rows[0].hours) == 4.0
        assert float(rows[1].hours) == 4.0
        assert float(rows[2].hours) == 8.0, "OVERTIME bleibt unangetastet"


class TestEffectWindow:
    """Release-Review 1.17.0: Das Retarget-Fenster ist der WIRKUNGSBEREICH der
    geänderten Zeile — von ``effective_from`` bis zum Tag vor der nächsten
    ``WorkingHoursChange``, sonst offen (praktisch begrenzt auf die späteste
    gebuchte Abwesenheit). NICHT bis „heute": bereits gebuchte zukünftige
    Abwesenheiten (genehmigter Urlaub, Betriebsferien, geplante Fortbildung)
    tragen sonst dauerhaft die Stunden des ALTEN Vertrags, während das Soll
    desselben Tages schon dem neuen folgt.
    """

    def test_retroactive_change_also_reaches_future_absences(self, db, default_tenant):
        """Auch bei einer RÜCKWIRKENDEN Änderung endete das Fenster bei heute —
        eine für nächste Woche bereits erfasste Fortbildung blieb stehen."""
        admin = _admin(db, "wh_win1_admin")
        emp = _make_user(db, "wh_win1_emp", weekly_hours=40.0)
        past = _last_monday(before_days=30)
        soon = _next_monday(after_days=7)
        past_a = _absence(db, emp, past, AbsenceType.SICK, 8.0)
        future_a = _absence(db, emp, soon, AbsenceType.TRAINING, 8.0)

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=past, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        db.refresh(past_a)
        db.refresh(future_a)
        assert float(past_a.hours) == 4.0
        assert float(future_a.hours) == 4.0, "auch die zukünftige Zeile wird nachgezogen"
        assert result.adjusted_absences == 2

    def test_window_ends_before_the_next_change(self, db, default_tenant):
        """Der Wirkungsbereich einer Zeile endet am Tag VOR der nächsten
        Änderung — was danach liegt, gehört bereits einem anderen Vertragswert
        und darf nicht mit umgeschrieben werden."""
        admin = _admin(db, "wh_win2_admin")
        emp = _make_user(db, "wh_win2_emp", weekly_hours=40.0)
        first = _next_monday(after_days=7)
        second = first + timedelta(days=28)
        # Die SPÄTERE Zeile existiert bereits (direkt angelegt, damit keine
        # Basis-Zeile entsteht und die Reihenfolge deterministisch ist).
        db.add(WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=second, weekly_hours=Decimal("40.0"),
        ))
        db.commit()
        inside = _absence(db, emp, first + timedelta(days=1), AbsenceType.TRAINING, 8.0)
        outside = _absence(db, emp, second + timedelta(days=1), AbsenceType.TRAINING, 8.0)

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=first, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        db.refresh(inside)
        db.refresh(outside)
        assert float(inside.hours) == 4.0, "im Wirkungsbereich der neuen Zeile"
        assert float(outside.hours) == 8.0, "hinter der nächsten Änderung: unangetastet"
        assert result.adjusted_absences == 1

    def test_no_absence_in_window_means_no_retarget_and_no_audit_row(self, db, default_tenant):
        """Auslöser ist „es gibt eine betroffene Abwesenheit", nicht das Datum.
        Ohne Abwesenheit im Wirkungsbereich passiert nichts — kein Retarget,
        keine Audit-Zeile, keine Warnung."""
        admin = _admin(db, "wh_win3_admin")
        emp = _make_user(db, "wh_win3_emp", weekly_hours=40.0)
        future = _next_monday(after_days=14)
        # Abwesenheit NUR vor dem Wirkungsdatum.
        earlier = _absence(db, emp, _last_monday(), AbsenceType.VACATION, 8.0)

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=future, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        db.refresh(earlier)
        assert float(earlier.hours) == 8.0
        assert result.adjusted_absences == 0
        assert result.warning is None
        assert db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "wh_change",
        ).count() == 0

    def test_future_vacation_hours_move_but_days_do_not(self, db, default_tenant):
        """Tagesprinzip (§3 BUrlG): der Urlaubs-TAGE-Verbrauch hängt nicht an
        ``hours`` und darf sich durch das Nachziehen NIE bewegen — auch nicht
        für einen bereits genehmigten künftigen Urlaub."""
        admin = _admin(db, "wh_win4_admin")
        emp = _make_user(db, "wh_win4_emp", weekly_hours=40.0)
        future = _next_monday(after_days=21)
        a = _absence(db, emp, future + timedelta(days=1), AbsenceType.VACATION, 8.0)

        db.expire_all()
        emp = db.query(User).filter(User.username == "wh_win4_emp").first()
        before_days = calculation_service.get_vacation_account(db, emp, future.year)["used_days"]
        assert float(before_days) > 0, "Vorbedingung: der künftige Urlaub zählt bereits"

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=future, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        db.refresh(a)
        assert float(a.hours) == 4.0, "Stunden folgen dem neuen Tagessoll"
        db.expire_all()
        emp = db.query(User).filter(User.username == "wh_win4_emp").first()
        after_days = calculation_service.get_vacation_account(db, emp, future.year)["used_days"]
        assert float(after_days) == float(before_days), "Urlaubs-TAGE unverändert"


class TestBaselineRowStillCreated:
    def test_baseline_row_still_created_on_first_change(self, db, default_tenant):
        """1.16.0-Verhalten (Release-Review #415-Folgefund) darf durch Task 3
        nicht kaputtgehen: die allererste Änderung eines Nutzers friert den
        bisherigen Vertragswert als Basis-Zeile ein."""
        admin = _admin(db)
        emp = _make_user(db, "wh_baseline_emp", weekly_hours=40.0)
        mon = _last_monday()

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        rows = (
            db.query(WorkingHoursChange)
            .filter(WorkingHoursChange.user_id == emp.id)
            .order_by(WorkingHoursChange.effective_from)
            .all()
        )
        assert len(rows) == 2
        assert float(rows[0].weekly_hours) == 40.0, "Ausgangswert eingefroren"
        assert rows[0].effective_from < mon
        assert float(rows[1].weekly_hours) == 20.0

    def test_baseline_covers_whole_past_without_first_work_day(self, db, default_tenant):
        """I5 (Abschluss-Review): ``first_work_day`` ist nullable und in der
        Praxis oft leer. Vorher lag die Basis-Zeile dann auf
        ``effective_from - 1 Tag`` und deckte GENAU EINEN Tag ab — alles davor
        fiel auf ``user.weekly_hours`` zurück, das derselbe Request gerade auf
        den NEUEN Wert setzt. Das Soll aller früheren Monate verschob sich
        still."""
        admin = _admin(db, "wh_base_admin")
        emp = _make_user(db, "wh_base_emp", weekly_hours=40.0)  # first_work_day = None
        assert emp.first_work_day is None
        long_ago = _last_monday(before_days=400)
        _absence(db, emp, long_ago, AbsenceType.VACATION, 8.0)
        mon = _last_monday(before_days=30)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        rows = (
            db.query(WorkingHoursChange)
            .filter(WorkingHoursChange.user_id == emp.id)
            .order_by(WorkingHoursChange.effective_from)
            .all()
        )
        assert len(rows) == 2
        assert rows[0].effective_from <= long_ago, "Basis-Zeile deckt die älteste Buchung ab"
        db.expire_all()
        emp = db.query(User).filter(User.username == "wh_base_emp").first()
        weekly_then = calculation_service.get_weekly_hours_for_date(db, emp, long_ago)
        assert float(weekly_then) == 40.0, "Soll weit in der Vergangenheit unverändert"

    def test_baseline_covers_oldest_time_entry(self, db, default_tenant):
        """Auch eine reine Zeitbuchung (ohne Abwesenheit, ohne first_work_day)
        muss von der Basis-Zeile abgedeckt sein."""
        admin = _admin(db, "wh_base2_admin")
        emp = _make_user(db, "wh_base2_emp", weekly_hours=40.0)
        long_ago = _last_monday(before_days=400)
        db.add(TimeEntry(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=long_ago,
            start_time=time(9, 0), end_time=time(17, 0), break_minutes=30,
        ))
        db.commit()
        mon = _last_monday(before_days=30)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        earliest = (
            db.query(WorkingHoursChange)
            .filter(WorkingHoursChange.user_id == emp.id)
            .order_by(WorkingHoursChange.effective_from)
            .first()
        )
        assert earliest.effective_from <= long_ago
        db.expire_all()
        emp = db.query(User).filter(User.username == "wh_base2_emp").first()
        assert float(
            calculation_service.get_weekly_hours_for_date(db, emp, long_ago)
        ) == 40.0


class TestAuditLog:
    def test_audit_row_written(self, db, default_tenant):
        admin = _admin(db)
        emp = _make_user(db, "wh_audit_emp", weekly_hours=40.0)
        mon = _last_monday()
        _absence(db, emp, mon, AbsenceType.VACATION, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        logs = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID,
            TimeEntryAuditLog.source == "wh_change",
        ).all()
        assert len(logs) == 1
        log = logs[0]
        assert log.action == "update"
        assert len(log.source) <= 40
        assert log.user_id == emp.id
        assert log.changed_by == admin.id

    def test_no_audit_row_when_nothing_adjusted(self, db, default_tenant):
        """Kein angepasstes Absence -> keine Audit-Zeile (keine leere Rausch-Zeile)."""
        admin = _admin(db)
        emp = _make_user(db, "wh_no_audit_emp", weekly_hours=40.0)
        mon = _last_monday()
        # Keine Abwesenheit im Fenster.

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        count = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "wh_change",
        ).count()
        assert count == 0


class TestClosedYearWarning:
    def test_closed_year_returns_warning(self, db, default_tenant):
        """Ein Jahr Y gilt als abgeschlossen, wenn ein YearCarryover für Y+1 im
        Tenant existiert."""
        admin = _admin(db)
        emp = _make_user(db, "wh_closed_emp", weekly_hours=40.0)
        last_year = today_local().year - 1
        db.add(YearCarryover(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            year=last_year + 1, overtime_hours=Decimal("0"),
            vacation_days=Decimal("0"), source="year_closing",
        ))
        db.commit()

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(
                effective_from=date(last_year, 6, 1), weekly_hours=20.0,
            ),
            db=db, current_user=admin,
        )

        assert result.warning is not None
        assert str(last_year) in result.warning

    def test_open_year_has_no_warning(self, db, default_tenant):
        admin = _admin(db)
        emp = _make_user(db, "wh_open_emp", weekly_hours=40.0)
        mon = _last_monday()

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        assert result.warning is None

    def test_delete_of_closed_year_returns_200_with_warning(self, db, default_tenant):
        """I3 (Abschluss-Review): Das Löschen rechnet dasselbe Fenster zurück
        wie das Anlegen und kann denselben eingefrorenen Carryover entwerten —
        es muss den Hinweis genauso melden. Muster von ``delete_closure`` /
        ``cancel_vacation_request_as_admin``: 200 + ``{"warning": …}``."""
        admin = _admin(db, "wh_delwarn_admin")
        last_year = today_local().year - 1
        emp = _make_user(
            db, "wh_delwarn_emp", weekly_hours=40.0,
            first_work_day=date(last_year, 1, 1),
        )
        db.add(YearCarryover(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            year=last_year + 1, overtime_hours=Decimal("0"),
            vacation_days=Decimal("0"), source="year_closing",
        ))
        db.commit()
        # Eine Abwesenheit im abgeschlossenen Jahr, damit die Rückrechnung
        # tatsächlich etwas anfasst (2026-06-01 ist ein Montag).
        _absence(db, emp, date(last_year, 6, 1), AbsenceType.VACATION, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(
                effective_from=date(last_year, 6, 1), weekly_hours=20.0,
            ),
            db=db, current_user=admin,
        )
        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == date(last_year, 6, 1),
        ).first()
        assert change is not None

        response = delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        assert response is not None, "mit Warnung: 200 + Body statt 204"
        assert response.status_code == 200
        body = json.loads(response.body)
        assert str(last_year) in body["warning"]

    def test_delete_without_closed_year_still_204(self, db, default_tenant):
        admin = _admin(db, "wh_delnowarn_admin")
        emp = _make_user(db, "wh_delnowarn_emp", weekly_hours=40.0)
        mon = _last_monday()
        _absence(db, emp, mon, AbsenceType.VACATION, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )
        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == mon,
        ).first()

        response = delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )
        assert response is None, "ohne Warnung weiterhin 204 No Content"


class TestStillRejectedCases:
    def test_daily_schedule_still_400(self, db, default_tenant):
        admin = _admin(db, "wh_ds_admin")
        emp = _make_user(
            db, "wh_ds_emp", use_daily_schedule=True,
            hours_monday=8.0, hours_tuesday=8.0, hours_wednesday=8.0,
            hours_thursday=8.0, hours_friday=8.0,
        )
        mon = _last_monday()
        a = _absence(db, emp, mon, AbsenceType.VACATION, 8.0)

        with pytest.raises(HTTPException) as exc:
            create_working_hours_change(
                user_id=str(emp.id),
                change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
                db=db, current_user=admin,
            )
        assert exc.value.status_code == 400

        # Nichts geändert: weder WorkingHoursChange noch Absence-Stunden.
        assert db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id
        ).count() == 0
        db.refresh(a)
        assert float(a.hours) == 8.0

    def test_delete_does_not_retarget_daily_schedule_user(self, db, default_tenant):
        """I1 (Abschluss-Review): Anlegen lehnt Tagesplan-MA mit 400 ab, das
        Löschen rief ``retarget_absence_hours`` trotzdem ungefiltert auf und
        schrieb ihre gebuchten Abwesenheits-Stunden auf das Tagesplan-Soll um
        (8 h → 6 h) — eine stille §16-Änderung ohne Bezug zur Aktion. Löschen
        bleibt erlaubt (sonst wären Alt-Zeilen unlöschbar), rechnet aber
        nichts mehr zurück."""
        admin = _admin(db, "wh_dsdel_admin")
        mon = _last_monday()
        emp = _make_user(
            db, "wh_dsdel_emp", use_daily_schedule=True,
            hours_monday=6.0, hours_tuesday=6.0, hours_wednesday=6.0,
            hours_thursday=6.0, hours_friday=6.0,
        )
        # Bereits gebuchte Abwesenheit mit 8 h (aus der Zeit vor der
        # Tagesplan-Umstellung).
        a = _absence(db, emp, mon, AbsenceType.VACATION, 8.0)
        # Alt-Zeile aus derselben Zeit — direkt angelegt, da create sie heute
        # mit 400 ablehnen würde.
        change = WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=mon, weekly_hours=Decimal("20.0"),
        )
        db.add(change)
        db.commit()
        db.refresh(change)

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        assert db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id
        ).count() == 0, "Löschen bleibt möglich"
        db.refresh(a)
        assert float(a.hours) == 8.0, "Abwesenheits-Stunden unangetastet (nicht 6.0)"

    def test_duplicate_date_still_400(self, db, default_tenant):
        admin = _admin(db, "wh_dup_admin")
        emp = _make_user(db, "wh_dup_emp", weekly_hours=40.0)
        mon = _last_monday()
        db.add(WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=mon, weekly_hours=Decimal("30.0"),
        ))
        db.commit()
        a = _absence(db, emp, mon, AbsenceType.VACATION, 8.0)

        with pytest.raises(HTTPException) as exc:
            create_working_hours_change(
                user_id=str(emp.id),
                change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
                db=db, current_user=admin,
            )
        assert exc.value.status_code == 400
        assert "existiert bereits" in exc.value.detail

        # Nur die eine (vorbestehende) Zeile — kein zweiter Insert, keine
        # Rückrechnung ausgelöst.
        rows = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id
        ).all()
        assert len(rows) == 1
        assert float(rows[0].weekly_hours) == 30.0
        db.refresh(a)
        assert float(a.hours) == 8.0


class TestDeleteRestoresAbsenceHours:
    """Task 4: Löschen einer Wochenstunden-Änderung muss die beim Anlegen
    nachgezogenen Abwesenheits-Stunden zurückrechnen — sonst bleibt nach einer
    versehentlich angelegten und wieder entfernten Änderung ein falscher Stand
    stehen. ``delete_working_hours_change`` ruft dafür (nach dem bestehenden
    Nachführen von ``user.weekly_hours``) erneut ``retarget_absence_hours``
    auf, jetzt gegen den verbliebenen gültigen Wert."""

    def test_delete_restores_absence_hours(self, db, default_tenant):
        admin = _admin(db, "wh_del_admin")
        emp = _make_user(db, "wh_del_emp", weekly_hours=40.0)
        mon = _last_monday()
        a = _absence(db, emp, mon, AbsenceType.VACATION, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )
        db.refresh(a)
        assert float(a.hours) == 4.0, "Vorbedingung: Anlegen hat die Stunden angepasst"

        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == mon,
        ).first()
        assert change is not None

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        db.refresh(a)
        assert float(a.hours) == 8.0, "wieder auf dem ursprünglichen Wert (40h/Woche)"
        db.refresh(emp)
        assert float(emp.weekly_hours) == 40.0, "Basis-Zeile (Ausgangswert) greift wieder"

    def test_delete_of_future_change_rewinds_absences_from_its_effective_date(self, db, default_tenant):
        """Hieß früher ``test_delete_of_future_change_adjusts_nothing``.

        Seit das Anlegen einer zukunftsdatierten Änderung die bereits gebuchten
        Abwesenheiten AB dem Wirkungsdatum nachzieht (Release-Review 1.17.0),
        muss das Löschen symmetrisch zurückrechnen — sonst bliebe nach einer
        versehentlich angelegten und wieder entfernten Änderung ein falscher
        Stand stehen. Was VOR dem Wirkungsdatum liegt, bleibt weiterhin
        unangetastet.
        """
        admin = _admin(db, "wh_delfut_admin")
        emp = _make_user(db, "wh_delfut_emp", weekly_hours=40.0)
        future = _next_monday(after_days=14)
        # Eine Abwesenheit HEUTE — läge (fälschlich) im Fenster, würde die
        # Implementierung period_end statt effective_from als Startpunkt nehmen.
        before = _absence(db, emp, today_local(), AbsenceType.VACATION, 8.0)
        after = _absence(db, emp, future + timedelta(days=1), AbsenceType.TRAINING, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=future, weekly_hours=20.0),
            db=db, current_user=admin,
        )
        db.refresh(after)
        assert float(after.hours) == 4.0, "Vorbedingung: Anlegen hat nachgezogen"

        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == future,
        ).first()
        assert change is not None

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        db.refresh(before)
        db.refresh(after)
        assert float(before.hours) == 8.0, "vor dem Wirkungsdatum: nie angefasst"
        assert float(after.hours) == 8.0, "zurück auf den davor gültigen Wert"

    def test_delete_window_ends_before_the_next_change(self, db, default_tenant):
        """Auch beim Zurückrechnen endet der Wirkungsbereich am Tag vor der
        nächsten Änderung."""
        admin = _admin(db, "wh_delwin_admin")
        emp = _make_user(db, "wh_delwin_emp", weekly_hours=20.0)
        base = _last_monday(before_days=60)
        first = _next_monday(after_days=7)
        second = first + timedelta(days=28)
        # Basis-Zeile in der Vergangenheit: sonst wäre `first` die FRÜHESTE
        # Zeile und das Löschen mit 400 abgelehnt (sie verankert den davor
        # gültigen Wert).
        db.add(WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=base, weekly_hours=Decimal("20.0"), note="Basis",
        ))
        first_row = WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=first, weekly_hours=Decimal("40.0"),
        )
        db.add(first_row)
        db.add(WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=second, weekly_hours=Decimal("40.0"),
        ))
        db.commit()
        db.refresh(first_row)
        # Im Wirkungsbereich der zu löschenden Zeile, mit deren Tagessoll (8 h).
        inside = _absence(db, emp, first + timedelta(days=1), AbsenceType.TRAINING, 8.0)
        # Hinter der nächsten Änderung — gehört ihr, nicht der gelöschten.
        outside = _absence(db, emp, second + timedelta(days=1), AbsenceType.TRAINING, 8.0)

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(first_row.id),
            db=db, current_user=admin,
        )

        db.refresh(inside)
        db.refresh(outside)
        assert float(inside.hours) == 4.0, "fällt auf user.weekly_hours (20 h) zurück"
        assert float(outside.hours) == 8.0, "hinter der nächsten Änderung: unangetastet"


class TestDeleteAuditLog:
    def test_delete_writes_audit_row_when_adjusted(self, db, default_tenant):
        admin = _admin(db, "wh_delaudit_admin")
        emp = _make_user(db, "wh_delaudit_emp", weekly_hours=40.0)
        mon = _last_monday()
        _absence(db, emp, mon, AbsenceType.VACATION, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )
        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == mon,
        ).first()

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        logs = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID,
            TimeEntryAuditLog.source == "wh_change",
            TimeEntryAuditLog.new_note.like("Löschung%"),
        ).all()
        assert len(logs) == 1
        log = logs[0]
        assert log.action == "update"
        assert len(log.source) <= 40
        assert log.user_id == emp.id
        assert log.changed_by == admin.id

    def test_delete_writes_no_audit_row_when_nothing_adjusted(self, db, default_tenant):
        """Kein angepasstes Absence (kein Absence im Fenster) -> keine
        Audit-Zeile für die Löschung."""
        admin = _admin(db, "wh_delnoaudit_admin")
        emp = _make_user(db, "wh_delnoaudit_emp", weekly_hours=40.0)
        mon = _last_monday()
        # Keine Abwesenheit im Fenster.

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )
        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == mon,
        ).first()

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        count = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "wh_change",
            TimeEntryAuditLog.new_note.like("Löschung%"),
        ).count()
        assert count == 0


class TestDeleteEarliestRowRejected:
    """Critical fix (Review-Fund): deleting the EARLIEST ``WorkingHoursChange``
    row while later rows still exist must be rejected with 400. That row is
    the only place the value that applied BEFORE the very first recorded
    change is stored (either the #415 auto-baseline or the admin's
    first-ever manual entry). Without the guard, deleting it silently
    resynced ``user.weekly_hours`` to a LATER row's value and
    ``retarget_absence_hours`` then recomputed an already-correct absence
    against the WRONG daily target — a real reported incident (40h baseline
    + later 20h change; deleting the baseline halved an absence that was
    correctly booked at 8h under the old 40h contract)."""

    def test_delete_earliest_of_two_rejected_with_400(self, db, default_tenant):
        admin = _admin(db, "wh_delfirst_admin")
        mon = _last_monday()
        # first_work_day pins the auto-baseline's effective_from to a known,
        # deterministic WEEKDAY (Friday before `mon`) instead of the
        # `effective_from - 1 day` fallback, which would land on a Sunday
        # (daily target 0 there regardless of weekly_hours — unsuitable to
        # demonstrate the bug).
        friday_before = mon - timedelta(days=3)
        emp = _make_user(db, "wh_delfirst_emp", weekly_hours=40.0, first_work_day=friday_before)

        # Abwesenheit VOR dem Wirkungsdatum der ersten Aenderung — traegt
        # korrekt 8h (40h/Woche, 5 Tage).
        a = _absence(db, emp, friday_before, AbsenceType.VACATION, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        rows = (
            db.query(WorkingHoursChange)
            .filter(WorkingHoursChange.user_id == emp.id)
            .order_by(WorkingHoursChange.effective_from)
            .all()
        )
        assert len(rows) == 2, "Basis-Zeile (automatisch) + echte Aenderung"
        earliest = rows[0]
        assert earliest.effective_from == friday_before
        assert float(earliest.weekly_hours) == 40.0

        db.refresh(a)
        assert float(a.hours) == 8.0, (
            "Vorbedingung: die Basis-Zeile liegt vor dem Wirkungsdatum, die "
            "Erst-Anlage beruehrt diesen Tag nicht"
        )

        with pytest.raises(HTTPException) as exc:
            delete_working_hours_change(
                user_id=str(emp.id), change_id=str(earliest.id),
                db=db, current_user=admin,
            )
        assert exc.value.status_code == 400

        # Nichts veraendert: die Zeile existiert noch, die
        # Abwesenheits-Stunden stehen unveraendert.
        rows_after = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id
        ).all()
        assert len(rows_after) == 2
        db.refresh(a)
        assert float(a.hours) == 8.0
        db.refresh(emp)
        assert float(emp.weekly_hours) == 20.0, "unveraendert (durch die Erst-Anlage gesetzt)"

    def test_delete_only_row_still_succeeds(self, db, default_tenant):
        """Erlaubt: die einzige vorhandene Zeile darf geloescht werden — dann
        greift ``user.weekly_hours`` wieder als einzige Wahrheit, es gibt
        nichts, worauf noch zurueckgefallen werden koennte."""
        admin = _admin(db, "wh_delonly_admin")
        emp = _make_user(db, "wh_delonly_emp", weekly_hours=40.0)
        mon = _last_monday()
        change = WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=mon, weekly_hours=Decimal("20.0"),
        )
        db.add(change)
        db.commit()
        db.refresh(change)

        assert db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id
        ).count() == 1

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        assert db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id
        ).count() == 0

    def test_delete_later_of_two_still_succeeds_and_falls_back_to_earlier(self, db, default_tenant):
        """Erlaubt: die NICHT-frueheste Zeile darf jederzeit geloescht werden.
        Die Rueckrechnung muss danach korrekt auf das Tagessoll der
        verbleibenden (frueheren) Zeile zurueckfallen."""
        admin = _admin(db, "wh_dellater_admin")
        early = _last_monday(before_days=60)
        later = _last_monday(before_days=30)
        emp = _make_user(db, "wh_dellater_emp", weekly_hours=20.0, first_work_day=early)

        earliest_row = WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=early, weekly_hours=Decimal("40.0"),
            note="Basis",
        )
        later_row = WorkingHoursChange(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            effective_from=later, weekly_hours=Decimal("20.0"),
        )
        db.add(earliest_row)
        db.add(later_row)
        db.commit()
        db.refresh(later_row)

        # Abwesenheit am Tag der SPAETEREN Zeile, mit dem zu dieser Zeit
        # gueltigen 20h/Woche-Tagessoll (4h) gebucht.
        a = _absence(db, emp, later, AbsenceType.VACATION, 4.0)

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(later_row.id),
            db=db, current_user=admin,
        )

        rows = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == emp.id).all()
        assert len(rows) == 1
        assert rows[0].id == earliest_row.id, "fruehere Zeile bleibt bestehen"

        db.refresh(emp)
        assert float(emp.weekly_hours) == 40.0, "user.weekly_hours faellt auf die fruehere Zeile zurueck"

        db.refresh(a)
        assert float(a.hours) == 8.0, (
            "Rueckrechnung greift korrekt auf das Tagessoll der frueheren "
            "Zeile (40h/Woche)"
        )


class TestLegacyHalfDayAbsencesSurvive:
    """C1 (Abschluss-Review): ``Absence.half_day`` ist nullable — Zeilen von vor
    #205 tragen NULL, und genau fuer die zaehlen ``get_vacation_account`` /
    ``absence_days`` die TAGE stundenbasiert (``hours / Tagessoll``). Wuerde die
    Rueckrechnung dort das volle Tagessoll schreiben, aenderte sich der
    Urlaubs-TAGE-Verbrauch (0,5 -> 1,0) und die einzige Spur des Halbtags waere
    weg: auch das Loeschen der Aenderung stellt die urspruenglichen Stunden
    nicht wieder her. Die tagebasierte Invariante (§3 BUrlG) ist unantastbar."""

    def _legacy_half_day(self, db):
        """20 h/Woche (4 h/Tag) + eine Legacy-Halbtags-Abwesenheit mit 2 h."""
        admin = _admin(db, "wh_legacy_admin")
        start = _last_monday(before_days=90)
        emp = _make_user(db, "wh_legacy_emp", weekly_hours=20.0, first_work_day=start)
        mon = _last_monday(before_days=30)
        a = _absence(db, emp, mon, AbsenceType.VACATION, 2.0, half_day=None)
        return admin, emp, mon, a

    def test_create_leaves_legacy_half_day_untouched(self, db, default_tenant):
        admin, emp, mon, a = self._legacy_half_day(db)

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=40.0),
            db=db, current_user=admin,
        )

        db.refresh(a)
        assert float(a.hours) == 2.0, "Legacy-Halbtag unveraendert (nicht 8.0)"
        assert result.adjusted_absences == 0

    def test_create_then_delete_restores_nothing_because_nothing_changed(self, db, default_tenant):
        """Nicht ruecknehmbar waere der eigentliche Schaden: nach create+delete
        stuende ohne den Fix 4.0 statt der urspruenglichen 2.0."""
        admin, emp, mon, a = self._legacy_half_day(db)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=40.0),
            db=db, current_user=admin,
        )
        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == mon,
        ).first()
        assert change is not None

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        db.refresh(a)
        assert float(a.hours) == 2.0, "auch nach create+delete unveraendert"

    def test_vacation_days_unchanged_across_create_and_delete(self, db, default_tenant):
        admin, emp, mon, a = self._legacy_half_day(db)

        db.expire_all()
        before = calculation_service.get_vacation_account(db, emp, mon.year)["used_days"]

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=40.0),
            db=db, current_user=admin,
        )
        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == mon,
        ).first()
        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        db.expire_all()
        after = calculation_service.get_vacation_account(db, emp, mon.year)["used_days"]
        assert float(after) == float(before), "Urlaubs-TAGE unveraendert"


class TestPutRejectsWeeklyHours:
    """Task 5: ``user.weekly_hours`` ist zugleich der Rückfallwert für alle
    Tage vor der ersten erfassten ``WorkingHoursChange`` — ein direktes PUT
    würde das Feld still überschreiben und damit rückwirkend das Soll bereits
    abgeschlossener Monate verschieben, ohne Historie-Zeile und ohne
    Absence-Retarget. ``update_user`` lehnt ``weekly_hours`` im Payload daher
    mit 400 ab, BEVOR irgendetwas geschrieben wird. ``create_user`` (POST)
    bleibt unverändert — dort existiert noch keine Historie."""

    def test_put_user_with_weekly_hours_is_rejected(self, db, default_tenant):
        admin = _admin(db, "wh_put_admin")
        emp = _make_user(db, "wh_put_emp", weekly_hours=40.0)

        with pytest.raises(HTTPException) as exc:
            update_user(
                user_id=str(emp.id),
                user_data=UserUpdate(weekly_hours=30.0),
                db=db, current_user=admin,
            )
        assert exc.value.status_code == 400

        db.refresh(emp)
        assert float(emp.weekly_hours) == 40.0, "Nutzer in der DB unverändert"

    def test_put_user_without_weekly_hours_succeeds(self, db, default_tenant):
        admin = _admin(db, "wh_put2_admin")
        emp = _make_user(db, "wh_put2_emp", weekly_hours=40.0)

        result = update_user(
            user_id=str(emp.id),
            user_data=UserUpdate(first_name="Geändert"),
            db=db, current_user=admin,
        )

        assert result.first_name == "Geändert"
        db.refresh(emp)
        assert emp.first_name == "Geändert"
        assert float(emp.weekly_hours) == 40.0, "unberührt"

    def test_put_weekly_hours_allowed_for_daily_schedule_user(self, db, default_tenant):
        """I2 (Abschluss-Review): Für Tagesplan-MA ist der Änderungs-Endpoint
        gesperrt (400) — die PUT-Sperre fror ihre Wochenstunden damit dauerhaft
        ein, obwohl das Formular weiter „bitte anpassen!" verlangt und der
        falsche Wert in §16-Berichtsköpfe, die MiLoG-Ableitung (×13/3), die
        Schichtplanung und die Benutzerliste fließt. Ihr Tagessoll kommt aus
        hours_monday…friday, weekly_hours treibt bei ihnen kein Soll."""
        admin = _admin(db, "wh_putds_admin")
        emp = _make_user(
            db, "wh_putds_emp", weekly_hours=40.0, use_daily_schedule=True,
            hours_monday=6.0, hours_tuesday=6.0, hours_wednesday=6.0,
            hours_thursday=6.0, hours_friday=6.0,
        )

        result = update_user(
            user_id=str(emp.id),
            user_data=UserUpdate(weekly_hours=30.0),
            db=db, current_user=admin,
        )

        assert float(result.weekly_hours) == 30.0
        db.refresh(emp)
        assert float(emp.weekly_hours) == 30.0

    def test_put_weekly_hours_rejected_when_daily_schedule_is_switched_off(self, db, default_tenant):
        """Gegenrichtung: Wer den Tagesplan im selben PUT ABschaltet, faellt
        wieder unter die Sperre — danach traebe weekly_hours das Soll."""
        admin = _admin(db, "wh_putds2_admin")
        emp = _make_user(
            db, "wh_putds2_emp", weekly_hours=40.0, use_daily_schedule=True,
            hours_monday=6.0, hours_tuesday=6.0, hours_wednesday=6.0,
            hours_thursday=6.0, hours_friday=6.0,
        )

        with pytest.raises(HTTPException) as exc:
            update_user(
                user_id=str(emp.id),
                user_data=UserUpdate(weekly_hours=30.0, use_daily_schedule=False),
                db=db, current_user=admin,
            )
        assert exc.value.status_code == 400

        db.refresh(emp)
        assert float(emp.weekly_hours) == 40.0, "Nutzer in der DB unveraendert"
        assert emp.use_daily_schedule is True

    def test_post_user_with_weekly_hours_still_works(self, db, default_tenant):
        admin = _admin(db, "wh_post_admin")

        result = create_user(
            user_data=UserCreate(
                username="wh_post_new_emp", first_name="Neu", last_name="User",
                weekly_hours=32.0, vacation_days=30, work_days_per_week=5,
                password=_TEST_PASSWORD,
            ),
            db=db, current_user=admin,
        )

        assert result.user.weekly_hours == 32.0
        created = db.query(User).filter(User.username == "wh_post_new_emp").first()
        assert created is not None
        assert float(created.weekly_hours) == 32.0
