"""Task 15: Abwesenheits-Stunden revisionssicher — Rohwert + Einzelprotokoll.

``retarget_absence_hours`` ueberschreibt ``Absence.hours`` in place. Vor diesem
Task war der vorherige Wert danach unwiederbringlich weg, und protokolliert wurde
nur eine Sammelmeldung („N Abwesenheit(en) … nachgezogen") — WELCHE Zeile von
WELCHEM Wert auf WELCHEN ging, stand nirgends. Stellte sich eine Berechnung als
falsch heraus, gab es keinen Weg zurueck.

Zwei Sicherungen, die sich ergaenzen:

1. ``Absence.raw_hours`` — der beim Buchen gesetzte Wert. Die Rueckrechnung fasst
   ihn NIE an, egal wie oft sie laeuft. ``TimeEntry`` hat mit
   ``raw_start_time``/``raw_end_time`` (#201) genau dieselbe Sicherung.
2. Je tatsaechlich geaenderter Abwesenheit eine Audit-Zeile mit Datum, altem und
   neuem Wert plus Ausloeser — zusaetzlich zur Sammelzeile.

``raw_hours`` fliesst in KEINE Berechnung ein (Soll/Ist/Urlaub bleiben
eingefroren); es ist reine Rueckversicherung.
"""
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import (
    Absence, AbsenceType, ChangeRequest, ChangeRequestStatus, ChangeRequestType,
    TimeEntryAuditLog, User, UserRole, WorkingHoursChange,
)
from app.routers.admin_users import (
    create_working_hours_change, delete_working_hours_change,
    preview_working_hours_change,
)
from app.schemas.working_hours_change import WorkingHoursChangeCreate
from app.services import calculation_service
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


def _admin(db, username="raw_admin"):
    return _make_user(db, username, role=UserRole.ADMIN)


def _absence(db, user, d, typ=AbsenceType.VACATION, hours=8.0, half_day=False):
    a = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        type=typ, hours=hours, half_day=half_day,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _last_monday(before_days=30):
    d = today_local() - timedelta(days=before_days)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return d


def _wh_change(db, user, effective_from, weekly):
    db.add(WorkingHoursChange(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        effective_from=effective_from, weekly_hours=Decimal(str(weekly)),
    ))
    db.commit()


# 2026-03-09 = Montag
MON = date(2026, 3, 9)
TUE = date(2026, 3, 10)
WINDOW = (date(2026, 3, 1), date(2026, 3, 31))


class TestRawHoursIsSetOnBooking:
    """Der ``before_insert``-Listener deckt ALLE Buchungspfade ab — die Pfade
    selbst setzen ``raw_hours`` nicht."""

    def test_direct_booking_sets_raw_hours(self, db, default_tenant):
        """Direktpfad ``absences.create_absence``."""
        from app.routers.absences import create_absence
        from app.schemas.absence import AbsenceCreate

        emp = _make_user(db, "raw_direct_emp", weekly_hours=40.0)
        created = create_absence(
            absence_data=AbsenceCreate(
                date=MON, type=AbsenceType.VACATION, hours=8.0,
            ),
            db=db, current_user=emp,
        )

        assert len(created) == 1
        db.expire_all()
        row = db.query(Absence).filter(Absence.user_id == emp.id).one()
        assert float(row.raw_hours) == float(row.hours) == 8.0

    def test_vacation_request_approval_sets_raw_hours(self, db, default_tenant):
        """Antragspfad ``admin_vacations.review_vacation_request``."""
        from app.models.vacation_request import VacationRequest, VacationRequestStatus
        from app.routers.admin_vacations import review_vacation_request
        from app.schemas.vacation_request import VacationRequestReview

        emp = _make_user(db, "raw_vr_emp", weekly_hours=40.0)
        admin = _admin(db, "raw_vr_admin")
        vr = VacationRequest(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            date=MON, end_date=TUE, hours=8.0, absence_type="vacation",
            status=VacationRequestStatus.PENDING.value,
        )
        db.add(vr)
        db.commit()
        db.refresh(vr)

        review_vacation_request(
            request_id=str(vr.id),
            review=VacationRequestReview(action="approve"),
            db=db, current_user=admin,
        )

        db.expire_all()
        rows = db.query(Absence).filter(Absence.user_id == emp.id).all()
        assert len(rows) == 2
        assert all(float(r.raw_hours) == float(r.hours) == 8.0 for r in rows)


class TestRetargetNeverTouchesRawHours:
    """Der Kern des Auftrags: die Rueckrechnung darf den Rohwert NIE anfassen."""

    def test_retarget_moves_hours_but_not_raw_hours(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _wh_change(db, test_user, date(2026, 3, 1), 20.0)

        calculation_service.retarget_absence_hours(db, test_user, *WINDOW)
        db.commit()

        db.expire_all()
        row = db.query(Absence).filter(Absence.id == a.id).one()
        assert float(row.hours) == 4.0
        assert float(row.raw_hours) == 8.0, "der gebuchte Rohwert bleibt stehen"

    def test_repeated_retarget_keeps_the_original_raw_value(self, db, test_user):
        """Mehrfaches Nachrechnen (40 → 20 → 10 h/Woche) darf den Rohwert nicht
        stufenweise mitziehen — sonst waere nach der zweiten Rueckrechnung nur
        noch das Ergebnis der ersten rekonstruierbar."""
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)

        _wh_change(db, test_user, date(2026, 3, 1), 20.0)
        calculation_service.retarget_absence_hours(db, test_user, *WINDOW)
        db.commit()
        _wh_change(db, test_user, date(2026, 3, 2), 10.0)
        calculation_service.retarget_absence_hours(db, test_user, *WINDOW)
        db.commit()

        db.expire_all()
        row = db.query(Absence).filter(Absence.id == a.id).one()
        assert float(row.hours) == 2.0
        assert float(row.raw_hours) == 8.0

    def test_dry_run_touches_neither(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.VACATION, 8.0)
        _wh_change(db, test_user, date(2026, 3, 1), 20.0)

        calculation_service.retarget_absence_hours(db, test_user, *WINDOW, dry_run=True)

        db.expire_all()
        row = db.query(Absence).filter(Absence.id == a.id).one()
        assert float(row.hours) == 8.0
        assert float(row.raw_hours) == 8.0


class TestRetargetReturnsRecords:
    """``retarget_absence_hours`` liefert WELCHE Zeilen es geaendert hat."""

    def test_records_carry_id_date_old_and_new(self, db, test_user):
        a = _absence(db, test_user, MON, AbsenceType.SICK, 8.0)
        _wh_change(db, test_user, date(2026, 3, 1), 20.0)

        changed = calculation_service.retarget_absence_hours(db, test_user, *WINDOW)

        assert len(changed) == 1
        rec = changed[0]
        assert rec.absence_id == a.id
        assert rec.date == MON
        assert float(rec.old_hours) == 8.0
        assert float(rec.new_hours) == 4.0
        assert rec.absence_type == AbsenceType.SICK

    def test_empty_window_returns_empty_list(self, db, test_user):
        assert calculation_service.retarget_absence_hours(
            db, test_user, date(2026, 3, 31), date(2026, 3, 1)
        ) == []


class TestHumanCorrectionSetsBoth:
    """Eine menschliche Korrektur bucht neu — dort IST der neue Wert der
    gebuchte, also wandert er auch in ``raw_hours``."""

    def test_change_request_approval_updates_raw_hours(self, db, default_tenant):
        from app.routers.admin_change_requests import review_change_request
        from app.schemas.change_request import ChangeRequestReview

        # Teilzeit 20 h / 5 Tage -> Tagessoll 4 h.
        emp = _make_user(db, "raw_cr_emp", weekly_hours=20.0)
        admin = _admin(db, "raw_cr_admin")
        a = _absence(db, emp, MON, AbsenceType.VACATION, 8.0)
        cr = ChangeRequest(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
            request_type=ChangeRequestType.UPDATE, entry_kind="absence",
            status=ChangeRequestStatus.PENDING, reason="Korrektur",
            absence_id=a.id, proposed_date=MON, proposed_absence_type="sick",
        )
        db.add(cr)
        db.commit()

        review_change_request(
            request_id=str(cr.id),
            review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )

        db.expire_all()
        row = db.query(Absence).filter(Absence.id == a.id).one()
        assert float(row.hours) == 4.0
        assert float(row.raw_hours) == 4.0, "menschliche Neubuchung zieht den Rohwert mit"


def _wh_logs(db, note_like=None):
    q = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID,
        TimeEntryAuditLog.source == "wh_change",
    )
    if note_like is not None:
        q = q.filter(TimeEntryAuditLog.new_note.like(note_like))
    return q.all()


class TestPerAbsenceAuditRows:
    def test_one_row_per_changed_absence_plus_the_summary(self, db, default_tenant):
        admin = _admin(db, "raw_audit_admin")
        emp = _make_user(db, "raw_audit_emp", weekly_hours=40.0)
        mon = _last_monday()
        _absence(db, emp, mon, AbsenceType.SICK, 8.0)
        _absence(db, emp, mon + timedelta(days=1), AbsenceType.VACATION, 8.0)

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        logs = _wh_logs(db)
        # 1 Sammelzeile (ohne Datum) + 1 Zeile je geaenderter Abwesenheit.
        summary = [x for x in logs if x.new_date is None]
        per_row = [x for x in logs if x.new_date is not None]
        assert len(summary) == 1, "die Sammelzeile bleibt erhalten"
        assert len(per_row) == 2

        by_date = {x.new_date: x for x in per_row}
        assert set(by_date) == {mon, mon + timedelta(days=1)}
        sick = by_date[mon]
        assert sick.action == "update"
        assert sick.source == "wh_change"
        assert len(sick.source) <= 40
        assert sick.user_id == emp.id
        assert sick.changed_by == admin.id
        assert sick.time_entry_id is None
        assert sick.old_date == mon
        assert sick.old_note == "Krank 8,0 h"
        assert sick.new_note.startswith("Krank 4,0 h — Wochenstunden-Änderung ab ")
        assert mon.strftime("%d.%m.%Y") in sick.new_note

    def test_delete_writes_per_absence_rows_too(self, db, default_tenant):
        admin = _admin(db, "raw_del_admin")
        emp = _make_user(db, "raw_del_emp", weekly_hours=40.0)
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

        # Die Einzelzeile beginnt mit dem Typ-Label, der Auslöser steht dahinter.
        rows = [x for x in _wh_logs(db, "%Löschung der Wochenstunden-Änderung%")
                if x.new_date is not None]
        assert len(rows) == 1
        assert rows[0].old_note == "Urlaub 4,0 h"
        assert rows[0].new_note.startswith("Urlaub 8,0 h — Löschung der Wochenstunden-Änderung ab ")

    def test_no_rows_when_nothing_changed(self, db, default_tenant):
        admin = _admin(db, "raw_noop_admin")
        emp = _make_user(db, "raw_noop_emp", weekly_hours=40.0)
        mon = _last_monday()

        create_working_hours_change(
            user_id=str(emp.id),
            change_data=WorkingHoursChangeCreate(effective_from=mon, weekly_hours=20.0),
            db=db, current_user=admin,
        )

        assert _wh_logs(db) == []


class TestPreviewWritesNoAuditRow:
    """Die Vorschau ruft dieselbe Rueckrechnung und rollt danach zurueck — sie
    darf KEIN Protokoll schreiben, sonst protokolliert jeder Tastendruck im
    Dialog eine Aenderung, die nie stattfand."""

    def test_preview_leaves_the_audit_log_untouched(self, db, default_tenant):
        admin = _admin(db, "raw_prev_admin")
        emp = _make_user(db, "raw_prev_emp", weekly_hours=40.0)
        mon = _last_monday()
        _absence(db, emp, mon, AbsenceType.VACATION, 8.0)

        before = db.query(TimeEntryAuditLog).count()
        # Direktaufruf: die ``Query(...)``-Defaults der Signatur sind ausserhalb
        # von FastAPI keine Werte, sondern Query-Objekte — alle Parameter
        # explizit setzen.
        result = preview_working_hours_change(
            user_id=str(emp.id), effective_from=mon, weekly_hours=20.0,
            use_daily_schedule=False, hours_monday=None, hours_tuesday=None,
            hours_wednesday=None, hours_thursday=None, hours_friday=None,
            work_days_per_week=None,
            db=db, current_user=admin,
        )
        after = db.query(TimeEntryAuditLog).count()

        assert result.affected_absences == 1, "Vorbedingung: die Vorschau sieht die Zeile"
        assert after == before, "die Vorschau schreibt keine Audit-Zeile"


class TestDsgvoExport:
    def test_self_export_stays_json_serialisable(self, db, default_tenant):
        """Fehlerklasse #383/#408: ``Numeric`` liefert beim Lesen ``Decimal``,
        und dieser Export laeuft ueber rohes ``json.dumps``."""
        from app.services import lifecycle_service

        emp = _make_user(db, "raw_dsgvo_emp", weekly_hours=40.0)
        _absence(db, emp, MON, AbsenceType.VACATION, 8.0)

        db.expire_all()
        emp = db.query(User).filter(User.username == "raw_dsgvo_emp").one()
        payload = lifecycle_service.build_self_export_payload(db, emp)

        json.dumps(payload)  # darf NICHT werfen
        assert payload["absences"][0]["raw_hours"] == 8.0

    def test_superadmin_export_dict_stays_json_serialisable(self, db, default_tenant):
        """§16-Notfall-Export: eigener Dict-Bauer, gleiche Fehlerklasse."""
        from app.routers import superadmin

        emp = _make_user(db, "raw_sa_emp", weekly_hours=40.0)
        _absence(db, emp, MON, AbsenceType.SICK, 8.0)

        db.expire_all()
        row = db.query(Absence).filter(Absence.user_id == emp.id).one()
        payload = superadmin._absence_dict(row)

        json.dumps(payload)  # darf NICHT werfen
        assert payload["raw_hours"] == 8.0
