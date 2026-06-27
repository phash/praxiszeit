"""Tests für Änderungsanträge mit Absence-Typen und Absence-Zeiten."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import (
    User, UserRole, TimeEntry, Absence, AbsenceType,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_user(db, username="cr_user", email="cr@test.de", **kwargs):
    defaults = dict(
        password_hash="hash", first_name="CR", last_name="User",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    user = User(username=username, email=email, **defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_absence(db, user, d, absence_type, hours, start_t=None, end_t=None):
    absence = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        date=d, type=absence_type, hours=hours,
        start_time=start_t, end_time=end_t,
    )
    db.add(absence)
    db.commit()
    return absence


def _make_absence_cr(db, user, request_type="create", **kwargs):
    defaults = dict(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=request_type, entry_kind="absence",
        status=ChangeRequestStatus.PENDING,
        reason="Testantrag",
    )
    defaults.update(kwargs)
    cr = ChangeRequest(**defaults)
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


class TestAbsenceCRModel:
    """Absence-CR Model-Tests."""

    def test_create_absence_cr_pending(self, db, test_user):
        """Prüft dass ein neuer Absence-CR mit Status PENDING und korrektem entry_kind='absence' erstellt wird."""
        cr = _make_absence_cr(db, test_user,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="sick",
            proposed_absence_hours=8.0,
        )
        assert cr.entry_kind == "absence"
        assert cr.status == ChangeRequestStatus.PENDING
        assert cr.proposed_absence_type == "sick"

    def test_absence_cr_with_times(self, db, test_user):
        """Prüft dass Absence-CRs optionale Start-/Endzeiten speichern können (Halbtags-Abwesenheiten)."""
        cr = _make_absence_cr(db, test_user,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="training",
            proposed_absence_hours=3.0,
            proposed_start_time=time(14, 0),
            proposed_end_time=time(17, 0),
        )
        assert cr.proposed_start_time == time(14, 0)
        assert cr.proposed_end_time == time(17, 0)

    def test_absence_cr_update_snapshots_original(self, db, test_user):
        """Prüft dass Update-CRs den Originalzustand snapshotten — nötig für Diff-Anzeige und Rollback."""
        absence = _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, 8.0)
        cr = _make_absence_cr(db, test_user,
            request_type="update",
            absence_id=absence.id,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="sick",
            proposed_absence_hours=8.0,
            original_absence_type="vacation",
            original_absence_hours=8.0,
        )
        assert cr.original_absence_type == "vacation"
        assert str(cr.absence_id) == str(absence.id)

    def test_entry_kind_default_is_time_entry(self, db, test_user):
        """Prüft dass entry_kind ohne explizite Angabe auf 'time_entry' defaulted — Abwärtskompatibilität."""
        cr = ChangeRequest(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            request_type="create", status=ChangeRequestStatus.PENDING,
            reason="Test", proposed_date=date(2026, 3, 10),
            proposed_start_time=time(8, 0), proposed_end_time=time(16, 0),
        )
        db.add(cr)
        db.commit()
        db.refresh(cr)
        assert cr.entry_kind == "time_entry"


class TestAbsenceStartEndTime:
    """Absence mit Start-/Endzeit."""

    def test_absence_with_times(self, db, test_user):
        """Prüft dass Absence mit expliziten Start-/Endzeiten korrekt persistiert wird (Halbtags-Support)."""
        absence = _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.TRAINING, 3.0,
            start_t=time(14, 0), end_t=time(17, 0))
        assert absence.start_time == time(14, 0)
        assert absence.end_time == time(17, 0)

    def test_absence_whole_day_no_times(self, db, test_user):
        """Prüft dass Ganztags-Absences NULL für start_time/end_time haben (Convention: NULL = ganzer Tag)."""
        absence = _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.VACATION, 8.0)
        assert absence.start_time is None
        assert absence.end_time is None

    def test_absence_times_in_journal(self, db, test_user):
        """Absence mit Zeiten zeigt start_time/end_time im Journal."""
        from app.services import journal_service
        _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.TRAINING, 3.0,
            start_t=time(14, 0), end_t=time(17, 0))
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert len(day["absences"]) == 1
        assert day["absences"][0]["start_time"] == "14:00"
        assert day["absences"][0]["end_time"] == "17:00"

    def test_absence_whole_day_no_times_in_journal(self, db, test_user):
        """Ganztags-Absence zeigt None für start_time/end_time im Journal."""
        from app.services import journal_service
        _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.VACATION, 8.0)
        journal = journal_service.get_journal(db, test_user, 2026, 3)
        day = next(d for d in journal["days"] if d["date"] == "2026-03-10")
        assert day["absences"][0]["start_time"] is None
        assert day["absences"][0]["end_time"] is None


class TestAbsenceCRApprovalDuplicate:
    """Review R2-a: Genehmigung eines Absence-CREATE-Antrags darf NICHT mit
    500 (IntegrityError gegen uq_tenant_user_date_type) crashen oder den Antrag
    in einen un-genehmigbaren PENDING-Zustand wedgen, wenn am Zieltag bereits
    eine Abwesenheit existiert. Spiegelt das Verhalten von ``create_absence``:
    gleicher Typ = idempotent (genehmigen + kein Doppel-Insert), anderer
    Typ = sauberer 409 statt stiller Doppelbuchung."""

    def _admin(self, db):
        return _make_user(db, username="cr_admin_dup", email="admindup@test.de",
                          role=UserRole.ADMIN)

    def test_approve_same_type_is_idempotent_no_500(self, db):
        """Existiert bereits eine Abwesenheit GLEICHEN Typs am Tag, darf die
        Genehmigung NICHT mit IntegrityError/500 fehlschlagen — sie soll
        idempotent durchlaufen (kein Doppel-Insert), CR = APPROVED."""
        from app.routers.admin_change_requests import review_change_request
        from app.schemas.change_request import ChangeRequestReview

        emp = _make_user(db, username="dup_emp1", email="dupemp1@test.de")
        admin = self._admin(db)
        d = date(2026, 6, 1)  # Montag, Arbeitstag
        _make_absence(db, emp, d, AbsenceType.SICK, 8.0)
        cr = _make_absence_cr(
            db, emp, request_type=ChangeRequestType.CREATE,
            proposed_date=d, proposed_absence_type="sick",
            proposed_absence_hours=8.0,
        )

        review_change_request(
            request_id=str(cr.id),
            review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )

        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.APPROVED
        # Kein Doppel-Insert: genau EINE Abwesenheit am Tag.
        n = db.query(Absence).filter(
            Absence.user_id == emp.id, Absence.date == d,
        ).count()
        assert n == 1

    def test_approve_conflicting_type_raises_409_no_double_booking(self, db):
        """Existiert eine Abwesenheit ANDEREN Typs am Tag, soll die Genehmigung
        einen sauberen 409 werfen (statt still doppelt zu buchen), CR bleibt
        PENDING (Transaktion zurückgerollt)."""
        from fastapi import HTTPException
        from app.routers.admin_change_requests import review_change_request
        from app.schemas.change_request import ChangeRequestReview

        emp = _make_user(db, username="dup_emp2", email="dupemp2@test.de")
        admin = self._admin(db)
        d = date(2026, 6, 1)
        _make_absence(db, emp, d, AbsenceType.VACATION, 8.0)
        cr = _make_absence_cr(
            db, emp, request_type=ChangeRequestType.CREATE,
            proposed_date=d, proposed_absence_type="sick",
            proposed_absence_hours=8.0,
        )

        with pytest.raises(HTTPException) as exc:
            review_change_request(
                request_id=str(cr.id),
                review=ChangeRequestReview(action="approve"),
                db=db, current_user=admin,
            )
        assert exc.value.status_code == 409
        db.rollback()
        db.refresh(cr)
        assert cr.status == ChangeRequestStatus.PENDING


class TestAbsenceCRBooksTagessoll:
    """#6 (Tagesprinzip): die Genehmigung eines Voll-Tag-Absence-CR bucht das
    TAGESSOLL des Tages, NICHT den vom Antragsteller gelieferten Wert (8h-Default).
    Nur OVERTIME behält explizite Stunden — wie create_absence/review_vacation_request."""

    def _admin(self, db):
        return _make_user(db, username="cr_admin_ts", email="admints@test.de",
                          role=UserRole.ADMIN)

    def test_vacation_cr_books_daily_target_not_client_hours(self, db):
        from app.routers.admin_change_requests import review_change_request
        from app.schemas.change_request import ChangeRequestReview

        # Teilzeit 20h/5 Tage → Tagessoll 4h. Der Antrag schickt den 8h-Default.
        emp = _make_user(db, username="pt_vac", email="ptvac@test.de", weekly_hours=20.0)
        admin = self._admin(db)
        d = date(2026, 6, 1)  # Montag, Arbeitstag
        cr = _make_absence_cr(
            db, emp, request_type=ChangeRequestType.CREATE,
            proposed_date=d, proposed_absence_type="vacation",
            proposed_absence_hours=8.0,
        )

        review_change_request(
            request_id=str(cr.id),
            review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )

        absence = db.query(Absence).filter(
            Absence.user_id == emp.id, Absence.date == d,
        ).one()
        # Tagessoll 4h, NICHT die 8h aus dem Antrag.
        assert float(absence.hours) == 4.0, f"expected Tagessoll 4h, got {absence.hours}"
        # Tagebasiert: genau 1 Urlaubstag verbraucht (Bug buchte 8/4 = 2 Tage).
        acc = calculation_service.get_vacation_account(db, emp, 2026)
        assert float(acc['used_days']) == 1.0, acc['used_days']

    def test_overtime_cr_keeps_explicit_hours(self, db):
        from app.routers.admin_change_requests import review_change_request
        from app.schemas.change_request import ChangeRequestReview

        # Vollzeit (Tagessoll 8h), OVERTIME-Ausgleich über 3h beantragt.
        emp = _make_user(db, username="ot_emp", email="otemp@test.de", weekly_hours=40.0)
        admin = self._admin(db)
        d = date(2026, 6, 2)  # Dienstag
        cr = _make_absence_cr(
            db, emp, request_type=ChangeRequestType.CREATE,
            proposed_date=d, proposed_absence_type="overtime",
            proposed_absence_hours=3.0,
        )

        review_change_request(
            request_id=str(cr.id),
            review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )

        absence = db.query(Absence).filter(
            Absence.user_id == emp.id, Absence.date == d,
        ).one()
        # OVERTIME behält die explizit beantragten 3h (nicht das 8h-Tagessoll).
        assert float(absence.hours) == 3.0, f"expected explicit 3h, got {absence.hours}"
        # Keine Doppelbuchung: weiterhin nur die ursprüngliche Vacation-Absence.
        n = db.query(Absence).filter(
            Absence.user_id == emp.id, Absence.date == d,
        ).count()
        assert n == 1


class TestAbsenceCRCustomReason:
    """#312: ein Abwesenheits-CR mit eigenem Grund (proposed_reason_id) trägt
    diesen durch die Genehmigung — die erzeugte Absence hat den über das
    Basis-Verhalten gemappten Typ UND die reason_id."""

    def _admin(self, db):
        return _make_user(db, username="cr_admin_reason", email="adminreason@test.de", role=UserRole.ADMIN)

    def test_cr_approval_carries_reason_id(self, db):
        from app.routers.admin_change_requests import review_change_request
        from app.schemas.change_request import ChangeRequestReview
        from app.models import AbsenceReason

        emp = _make_user(db, username="cr_reason_emp", email="crreason@test.de")
        admin = self._admin(db)
        reason = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Schule", base_behavior="worked", is_active=True)
        db.add(reason); db.commit(); db.refresh(reason)
        d = date(2026, 6, 2)  # Dienstag, Arbeitstag
        cr = _make_absence_cr(
            db, emp, request_type=ChangeRequestType.CREATE,
            proposed_date=d, proposed_absence_type="training",  # worked → TRAINING
            proposed_absence_hours=8.0, proposed_reason_id=reason.id,
        )
        review_change_request(
            request_id=str(cr.id), review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )
        a = db.query(Absence).filter(Absence.user_id == emp.id, Absence.date == d).one()
        assert a.type == AbsenceType.TRAINING
        assert a.reason_id == reason.id
