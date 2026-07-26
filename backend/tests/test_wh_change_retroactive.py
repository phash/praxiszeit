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
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models import (
    Absence, AbsenceType, TimeEntryAuditLog, User, UserRole,
    WorkingHoursChange, YearCarryover,
)
from app.routers.admin_users import create_working_hours_change, delete_working_hours_change
from app.schemas.working_hours_change import WorkingHoursChangeCreate
from app.services.timezone_service import today_local
from tests.conftest import DEFAULT_TENANT_ID


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

    def test_future_change_adjusts_nothing(self, db, default_tenant):
        """Ein Wirkungsdatum in der Zukunft betrifft nur noch nicht gebuchte Tage
        — retarget_absence_hours darf gar nicht erst aufgerufen werden."""
        admin = _admin(db)
        emp = _make_user(db, "wh_future_emp", weekly_hours=40.0)
        future = today_local() + timedelta(days=14)
        # Eine Abwesenheit HEUTE — läge (fälschlich) im Fenster, wenn die
        # Implementierung period_end statt effective_from als Startpunkt nähme.
        a = _absence(db, emp, today_local(), AbsenceType.VACATION, 8.0)

        result = create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=future, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        db.refresh(a)
        assert float(a.hours) == 8.0, "unverändert"
        assert result.adjusted_absences == 0
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

    def test_delete_of_future_change_adjusts_nothing(self, db, default_tenant):
        """Ein Wirkungsdatum in der Zukunft hat beim Anlegen keine Abwesenheit
        berührt — die Löschung darf dann ebenfalls nichts zurückrechnen."""
        admin = _admin(db, "wh_delfut_admin")
        emp = _make_user(db, "wh_delfut_emp", weekly_hours=40.0)
        future = today_local() + timedelta(days=14)
        # Eine Abwesenheit HEUTE — läge (fälschlich) im Fenster, würde die
        # Implementierung period_end statt effective_from als Startpunkt
        # nehmen oder den Zukunfts-Guard vergessen.
        a = _absence(db, emp, today_local(), AbsenceType.VACATION, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=future, weekly_hours=20.0),
            db=db, current_user=admin,
        )
        change = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == emp.id,
            WorkingHoursChange.effective_from == future,
        ).first()
        assert change is not None

        delete_working_hours_change(
            user_id=str(emp.id), change_id=str(change.id),
            db=db, current_user=admin,
        )

        db.refresh(a)
        assert float(a.hours) == 8.0, "unverändert"
        count = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "wh_change",
        ).count()
        assert count == 0


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
