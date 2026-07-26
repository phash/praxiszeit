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
from app.routers.admin_users import (
    create_user, create_working_hours_change, delete_working_hours_change, update_user,
)
from app.schemas.user import UserCreate, UserUpdate
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

    def test_post_user_with_weekly_hours_still_works(self, db, default_tenant):
        admin = _admin(db, "wh_post_admin")

        result = create_user(
            user_data=UserCreate(
                username="wh_post_new_emp", first_name="Neu", last_name="User",
                weekly_hours=32.0, vacation_days=30, work_days_per_week=5,
                password="Neu" + "Pass" + "2025" + "!",
            ),
            db=db, current_user=admin,
        )

        assert result.user.weekly_hours == 32.0
        created = db.query(User).filter(User.username == "wh_post_new_emp").first()
        assert created is not None
        assert float(created.weekly_hours) == 32.0
