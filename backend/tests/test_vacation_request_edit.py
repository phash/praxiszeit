"""Tests for editing PENDING vacation requests (employee + admin)."""

from datetime import date, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, TimeEntryAuditLog
from app.models.tenant import Tenant
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


def _create_test_app() -> FastAPI:
    from app.routers import admin_vacations, vacation_requests

    app = FastAPI(title="PraxisZeit Vacation-Edit Test")
    from app.core.limiter import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(admin_vacations.router)
    app.include_router(vacation_requests.router)
    return app


_app = _create_test_app()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _user(db, username, role=UserRole.EMPLOYEE, tenant_id=None):
    from app.services import auth_service
    u = User(
        username=username, email=f"{username}@example.com",
        password_hash=auth_service.hash_password("x"),
        first_name=username.title(), last_name="Test",
        role=role, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True,
        tenant_id=tenant_id or DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _user_custom(db, username, **kw):
    """User with overridable fields (track_hours, vacation_days, …)."""
    from app.services import auth_service
    defaults = dict(
        email=f"{username}@example.com", password_hash=auth_service.hash_password("x"),
        first_name=username.title(), last_name="Test", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kw)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def employee(db, default_tenant):
    return _user(db, "emp")


@pytest.fixture
def other_employee(db, default_tenant):
    return _user(db, "emp2")


@pytest.fixture
def admin(db, default_tenant):
    return _user(db, "adm", role=UserRole.ADMIN)


def _make_client(db_session, current_user):
    def override_db():
        yield db_session
    _app.dependency_overrides[get_db] = override_db
    _app.dependency_overrides[get_current_user] = lambda: current_user
    _app.dependency_overrides[require_admin] = lambda: current_user
    client = TestClient(_app)
    yield client
    _app.dependency_overrides.clear()


@pytest.fixture
def employee_client(db, employee):
    yield from _make_client(db, employee)


@pytest.fixture
def other_employee_client(db, other_employee):
    yield from _make_client(db, other_employee)


@pytest.fixture
def admin_client(db, admin):
    yield from _make_client(db, admin)


def _vr(db, user, status_val=VacationRequestStatus.PENDING.value, start=None,
        end=None, absence_type="vacation", hours=8.0, note=None):
    vr = VacationRequest(
        user_id=user.id, tenant_id=user.tenant_id,
        date=start or date.today() + timedelta(days=30),
        end_date=end, hours=hours,
        absence_type=absence_type, status=status_val, note=note,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


# ===========================================================================
# #196: Edit-Budget-Check tagebasiert (auch track_hours=False)
# ===========================================================================

class TestEditBudgetDayBased:
    """Der Edit-Pfad muss das Budget tagebasiert (remaining_days) prüfen — auch
    für track_hours=False, wo remaining_hours strukturell 0 ist."""

    def _patch_as(self, db, user, vr_id, body):
        def override_db():
            yield db
        _app.dependency_overrides[get_db] = override_db
        _app.dependency_overrides[get_current_user] = lambda: user
        try:
            return TestClient(_app).patch(f"/api/vacation-requests/{vr_id}", json=body)
        finally:
            _app.dependency_overrides.clear()

    def test_untracked_user_overbook_rejected(self, db, default_tenant):
        # leitende/r Angestellte/r: keine Stundenzählung, kleines Budget.
        u = _user_custom(db, "ltd", track_hours=False, vacation_days=2)
        vr = _vr(db, u, start=date(2026, 6, 8))  # Mo, Einzeltag
        # Edit auf Mo–Mi = 3 Werktage > 2 Resttage → muss abgelehnt werden.
        resp = self._patch_as(db, u, vr.id, {"end_date": date(2026, 6, 10).isoformat()})
        assert resp.status_code == 400, resp.text
        assert "Urlaubstage" in resp.json()["detail"]

    def test_untracked_user_within_budget_ok(self, db, default_tenant):
        u = _user_custom(db, "ltd2", track_hours=False, vacation_days=30)
        vr = _vr(db, u, start=date(2026, 6, 8))
        resp = self._patch_as(db, u, vr.id, {"end_date": date(2026, 6, 10).isoformat()})
        assert resp.status_code == 200, resp.text

    def test_tracked_user_overbook_still_rejected(self, db, default_tenant):
        # Kontrolle: getrackter User bleibt wie bisher korrekt blockiert.
        u = _user_custom(db, "trk", track_hours=True, vacation_days=2)
        vr = _vr(db, u, start=date(2026, 6, 8))
        resp = self._patch_as(db, u, vr.id, {"end_date": date(2026, 6, 10).isoformat()})
        assert resp.status_code == 400, resp.text


# ===========================================================================
# Employee edit own pending
# ===========================================================================

class TestEmployeeEdit:
    def test_edit_pending_updates_fields(self, db, employee, employee_client):
        vr = _vr(db, employee, note="alt")
        new_date = (date.today() + timedelta(days=40)).isoformat()
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"date": new_date, "note": "neu", "hours": 6.0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["date"] == new_date
        assert body["note"] == "neu"
        assert body["hours"] == 6.0

    def test_edit_writes_audit_row(self, db, employee, employee_client):
        vr = _vr(db, employee, note="alt")
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "neu"}
        )
        assert resp.status_code == 200, resp.text
        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).all()
        assert len(audits) == 1
        a = audits[0]
        assert a.action == "update"
        assert a.user_id == employee.id
        assert a.changed_by == employee.id
        assert "alt" in (a.old_note or "")
        assert "neu" in (a.new_note or "")
        assert a.tenant_id == DEFAULT_TENANT_ID

    def test_edit_noop_writes_no_audit(self, db, employee, employee_client):
        vr = _vr(db, employee, note="same")
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "same"}
        )
        assert resp.status_code == 200
        assert resp.json()["note"] == "same"
        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).count()
        assert audits == 0

    def test_edit_foreign_request_returns_404(
        self, db, employee, other_employee, other_employee_client
    ):
        # #120: Ein fremder Antrag im selben Tenant wird wie ein unbekannter
        # behandelt (404 statt 403) — der Response-Code verraet die Existenz
        # einer fremden VR-ID nicht.
        vr = _vr(db, employee)
        resp = other_employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "hack"}
        )
        assert resp.status_code == 404

    def test_edit_approved_rejected(self, db, employee, employee_client):
        vr = _vr(db, employee, status_val=VacationRequestStatus.APPROVED.value)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "x"}
        )
        assert resp.status_code == 400

    def test_edit_rejected_rejected(self, db, employee, employee_client):
        vr = _vr(db, employee, status_val=VacationRequestStatus.REJECTED.value)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "x"}
        )
        assert resp.status_code == 400

    def test_edit_withdrawn_rejected(self, db, employee, employee_client):
        vr = _vr(db, employee, status_val=VacationRequestStatus.WITHDRAWN.value)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "x"}
        )
        assert resp.status_code == 400

    def test_edit_invalid_range_rejected(self, db, employee, employee_client):
        start = date.today() + timedelta(days=30)
        vr = _vr(db, employee, start=start, end=start + timedelta(days=2))
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"end_date": (start - timedelta(days=1)).isoformat()},
        )
        assert resp.status_code == 400

    def test_edit_before_first_work_day_rejected(
        self, db, employee, employee_client
    ):
        employee.first_work_day = date.today() + timedelta(days=10)
        db.commit()
        vr = _vr(db, employee, start=date.today() + timedelta(days=30))
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"date": (date.today() + timedelta(days=5)).isoformat()},
        )
        assert resp.status_code == 400

    def test_edit_overlap_with_other_pending_rejected(
        self, db, employee, employee_client
    ):
        existing_start = date.today() + timedelta(days=60)
        _vr(db, employee, start=existing_start, end=existing_start + timedelta(days=4))
        target = _vr(db, employee, start=date.today() + timedelta(days=80))
        resp = employee_client.patch(
            f"/api/vacation-requests/{target.id}",
            json={"date": (existing_start + timedelta(days=2)).isoformat()},
        )
        assert resp.status_code == 409

    def test_edit_self_overlap_allowed(self, db, employee, employee_client):
        start = date.today() + timedelta(days=30)
        vr = _vr(db, employee, start=start, end=start + timedelta(days=4))
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"date": (start + timedelta(days=1)).isoformat()},
        )
        assert resp.status_code == 200, resp.text

    def test_edit_invalid_absence_type_rejected(
        self, db, employee, employee_client
    ):
        vr = _vr(db, employee)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"absence_type": "sick"}
        )
        # Pydantic validation -> 422
        assert resp.status_code == 422

    def test_edit_clear_end_date_via_explicit_null(
        self, db, employee, employee_client
    ):
        """Sending end_date: null collapses a range to a single-day request."""
        start = date.today() + timedelta(days=30)
        vr = _vr(db, employee, start=start, end=start + timedelta(days=4))
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"end_date": None}
        )
        assert resp.status_code == 200, resp.text
        db.refresh(vr)
        assert vr.end_date is None

    def test_edit_within_budget_does_not_self_count(
        self, db, employee, employee_client
    ):
        """Spec #9 regression: editing a pending request must NOT
        double-count its own hours against the vacation budget.

        Setup: tight budget = 2 vacation days. Pending request consumes
        the full budget. PATCH shifts the date range to a different week
        but keeps the same length. If the impl wrongly summed the
        existing pending hours into `account['remaining_hours']`, this
        edit would fail with 400 (budget). Pending requests must NOT
        consume budget — only Absences do.
        """
        employee.vacation_days = 2
        db.commit()
        # Mon + Tue in Q3 — deterministic weekdays, future-dated
        start = date(2026, 9, 7)        # Monday
        end = date(2026, 9, 8)          # Tuesday
        vr = _vr(db, employee, start=start, end=end, hours=8.0)
        # Shift to following week, same length
        new_start = date(2026, 9, 14)   # Monday
        new_end = date(2026, 9, 15)     # Tuesday
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={
                "date": new_start.isoformat(),
                "end_date": new_end.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        db.refresh(vr)
        assert vr.date == new_start
        assert vr.end_date == new_end

    def test_edit_exceeds_budget_rejected(
        self, db, employee, employee_client
    ):
        """Counterpart to self-exclude test: actual budget overflow
        must still be rejected. Sanity-check that the budget guard is
        intact and we didn't dilute it while fixing the double-count."""
        employee.vacation_days = 2
        db.commit()
        start = date(2026, 9, 7)        # Monday
        vr = _vr(db, employee, start=start, end=start + timedelta(days=1),
                 hours=8.0)
        # Try to extend to Mon-Fri = 5 weekdays, budget = 2 days
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"end_date": (start + timedelta(days=4)).isoformat()},
        )
        assert resp.status_code == 400

    def test_edit_unknown_field_rejected(self, db, employee, employee_client):
        """Mass-assignment guard: extra="forbid" rejects unknown fields
        like `status` / `reviewed_by` so a future refactor that blindly
        applies model_dump cannot bypass the approval workflow."""
        vr = _vr(db, employee)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"status": "approved", "note": "trying to self-approve"},
        )
        assert resp.status_code == 422

    def test_edit_negative_hours_rejected(self, db, employee, employee_client):
        """Field bounds: negative or absurd hours must be rejected at
        the schema layer before any DB write."""
        vr = _vr(db, employee)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"hours": -1.0}
        )
        assert resp.status_code == 422

    def test_edit_excessive_hours_rejected(self, db, employee, employee_client):
        """Field bounds: hours > 24 (one calendar day) must be rejected."""
        vr = _vr(db, employee)
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"hours": 9999.0}
        )
        assert resp.status_code == 422

    def test_edit_note_pipe_escaped_in_audit(
        self, db, employee, employee_client
    ):
        """Log-injection guard: `|` is the audit-text separator and must
        be neutralized in user-supplied notes so attackers cannot forge
        fake audit-row shapes (CWE-117)."""
        vr = _vr(db, employee, note="alt")
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}",
            json={"note": "fake | 2099-01-01..2099-12-31 | vacation | 999h"},
        )
        assert resp.status_code == 200, resp.text
        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).all()
        assert len(audits) == 1
        # The literal injected `|` must not appear in the new-note slice
        # past the legitimate format prefix.
        new_note = audits[0].new_note or ""
        # Split on the helper's separator: prefix has 4 segments before
        # the user-supplied note (`vacation_request <id> | <range> | <type>
        # | <hours> | <note>`). Anything more = injection succeeded.
        assert new_note.count("|") == 4, (
            f"User-supplied `|` not escaped: {new_note!r}"
        )


# ===========================================================================
# Admin edit any pending in tenant
# ===========================================================================

class TestAdminEdit:
    def test_admin_edits_employee_pending(self, db, employee, admin, admin_client):
        vr = _vr(db, employee, note="alt")
        resp = admin_client.patch(
            f"/api/admin/vacation-requests/{vr.id}", json={"note": "admin-edit"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["note"] == "admin-edit"

        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).all()
        assert len(audits) == 1
        a = audits[0]
        assert a.user_id == employee.id          # affected user
        assert a.changed_by == admin.id          # acting principal

    def test_admin_cannot_edit_foreign_tenant(self, db, default_tenant, admin_client):
        from uuid import uuid4
        foreign_tid = uuid4()
        foreign = Tenant(id=foreign_tid, name="Foreign", slug="foreign",
                         is_active=True, mode="single")
        db.add(foreign)
        db.commit()
        foreign_emp = _user(db, "foreign_emp", tenant_id=foreign_tid)
        vr = _vr(db, foreign_emp)
        resp = admin_client.patch(
            f"/api/admin/vacation-requests/{vr.id}", json={"note": "hack"}
        )
        assert resp.status_code == 404  # 404 — don't leak existence

    def test_admin_cannot_edit_approved(self, db, employee, admin_client):
        vr = _vr(db, employee, status_val=VacationRequestStatus.APPROVED.value)
        resp = admin_client.patch(
            f"/api/admin/vacation-requests/{vr.id}", json={"note": "x"}
        )
        assert resp.status_code == 400

    def test_admin_edit_sets_last_modified_by(
        self, db, employee, admin, admin_client
    ):
        """DSGVO transparency: when an admin edits a MA's request, the
        MA must be able to see WHO modified it. last_modified_by is the
        single source of truth — drives the 'Bearbeitet von Admin XY'
        badge on the MA's view."""
        vr = _vr(db, employee, note="alt")
        resp = admin_client.patch(
            f"/api/admin/vacation-requests/{vr.id}",
            json={"note": "admin änderung"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["last_modified_by"] == str(admin.id)
        assert body["last_modified_at"] is not None
        assert body["last_modifier_first_name"] == admin.first_name


class TestLastModifiedTracking:
    def test_self_edit_sets_self_as_modifier(
        self, db, employee, employee_client
    ):
        """A self-edit also bumps last_modified_by — the badge can then
        compare last_modified_by == user_id to decide whether to render
        as 'self-edited' (no badge) or 'admin-edited' (badge)."""
        vr = _vr(db, employee, note="alt")
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "neu"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["last_modified_by"] == str(employee.id)
        assert body["last_modified_at"] is not None

    def test_noop_edit_does_not_bump_last_modified(
        self, db, employee, employee_client
    ):
        """No-op edits must NOT touch last_modified_by — otherwise a
        spurious 'Bearbeitet von ...' badge would appear after a
        no-change PATCH."""
        vr = _vr(db, employee, note="same")
        resp = employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "same"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_modified_by"] is None
        assert body["last_modified_at"] is None


# ===========================================================================
# Review R2-c: POST-Budget-Check muss Feiertage ausschließen (Parität zum
# Edit-Pfad) + Approve darf nicht typ-übergreifend doppelt buchen
# ===========================================================================

def _enable_approval(db):
    from app.models.system_setting import SystemSetting
    db.add(SystemSetting(
        key="vacation_approval_required", tenant_id=DEFAULT_TENANT_ID,
        value="true", description="Urlaubsanträge aktiv",
    ))
    db.commit()


def _holiday(db, d):
    from app.models import PublicHoliday
    db.add(PublicHoliday(date=d, name="Testfeiertag", year=d.year, tenant_id=DEFAULT_TENANT_ID))
    db.commit()


class TestPostBudgetExcludesHolidays:
    """R2-c: Der POST-Budget-Check zählte ALLE Wochentage als verbraucht, ohne
    Feiertage auszuschließen — anders als der PATCH-/Approve-Pfad. Ein Antrag
    über einen Bereich mit Feiertag wurde dadurch fälschlich als 'nicht genügend
    Urlaubstage' abgelehnt, obwohl die Genehmigung den Feiertag gar nicht
    verbraucht."""

    def test_request_spanning_holiday_fits_budget(self, db, default_tenant):
        _enable_approval(db)
        # Budget = 4 Tage (Volljahr, kein Pro-rata).
        user = _user_custom(db, "budget4", vacation_days=4)
        client_gen = _make_client(db, user)
        client = next(client_gen)
        # Mo 08.06. – Fr 12.06.2026 = 5 Wochentage, Feiertag am Mi 10.06. → 4 billable.
        _holiday(db, date(2026, 6, 10))

        resp = client.post("/api/vacation-requests/", json={
            "date": "2026-06-08",
            "end_date": "2026-06-12",
            "hours": 8.0,
            "absence_type": "vacation",
        })
        # Mit Feiertags-Ausschluss: 4 ≤ 4 → 201. Ohne: 5 > 4 → 400.
        assert resp.status_code == 201, resp.text


# ===========================================================================
# Finding 10: POST + PATCH Budget-Check müssen 'free'-Sondertage (24./31.12.)
# genau wie Feiertage ausschließen — AC-11-Parität mit
# admin_vacations.review_vacation_request (holidays |=
# special_days_service.free_special_days_in_range(...)). Ohne den Ausschluss
# zählt ein soll-freier Sondertag fälschlich als verbrauchter Urlaubstag und
# ein Antrag über einen Bereich mit 24./31.12. wird false-positiv als
# "nicht genügend Urlaubstage" abgelehnt.
# ===========================================================================

def _set_special_day_free(db, key_prefix="special_day_dec24", counts_as_vacation="false"):
    from app.models.system_setting import SystemSetting
    db.add(SystemSetting(key=f"{key_prefix}_mode", tenant_id=DEFAULT_TENANT_ID, value="free"))
    db.add(SystemSetting(
        key=f"{key_prefix}_counts_as_vacation", tenant_id=DEFAULT_TENANT_ID,
        value=counts_as_vacation,
    ))
    db.commit()


class TestPostBudgetExcludesFreeSpecialDay:
    """F-10 (POST): Budget = 4 Tage, Bereich Mo 21.12.–Fr 25.12.2026 = 5
    Wochentage, davon 24.12. als 'free' konfiguriert → 4 billable Tage.
    Ohne den Ausschluss zählt der Check 5 > 4 → 400 (false positive)."""

    def test_request_spanning_free_day_fits_budget(self, db, default_tenant):
        _enable_approval(db)
        user = _user_custom(db, "budgetfree", vacation_days=4)
        client_gen = _make_client(db, user)
        client = next(client_gen)
        _set_special_day_free(db)

        resp = client.post("/api/vacation-requests/", json={
            "date": "2026-12-21",
            "end_date": "2026-12-25",
            "hours": 8.0,
            "absence_type": "vacation",
        })
        # Mit Free-Sondertag-Ausschluss: 4 ≤ 4 → 201. Ohne: 5 > 4 → 400.
        assert resp.status_code == 201, resp.text


class TestEditBudgetExcludesFreeSpecialDay:
    """F-10 (PATCH): dasselbe Szenario über den Edit-Budget-Check
    (apply_vacation_request_patch) — muss identisch mit dem POST-Pfad
    rechnen."""

    def test_edit_spanning_free_day_fits_budget(self, db, default_tenant):
        user = _user_custom(db, "editbudgetfree", vacation_days=4)
        vr = _vr(db, user, start=date(2026, 12, 21))
        _set_special_day_free(db)

        def override_db():
            yield db
        _app.dependency_overrides[get_db] = override_db
        _app.dependency_overrides[get_current_user] = lambda: user
        try:
            resp = TestClient(_app).patch(
                f"/api/vacation-requests/{vr.id}",
                json={"end_date": date(2026, 12, 25).isoformat()},
            )
        finally:
            _app.dependency_overrides.clear()
        # Mit Free-Sondertag-Ausschluss: 4 ≤ 4 → 200. Ohne: 5 > 4 → 400.
        assert resp.status_code == 200, resp.text


class TestVacationSelfApproval:
    """Audit A01 (4-Augen-Prinzip): ein Admin darf seinen EIGENEN Urlaubsantrag
    nur dann selbst genehmigen, wenn KEIN weiterer aktiver Admin existiert
    (Einzel-Admin-Praxis). Mit zweitem aktivem Admin → 403."""

    def test_self_approve_blocked_with_second_admin(self, db, admin, admin_client):
        from app.models import Absence
        _user(db, "adm2", role=UserRole.ADMIN)  # zweiter aktiver Admin
        # Zukünftiger Montag, damit es ein gültiger Arbeitstag ist.
        vr = _vr(db, admin, start=date(2026, 6, 8), end=None, absence_type="vacation")
        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 403, resp.text
        assert "selbst genehmigt" in resp.json()["detail"].lower()
        db.refresh(vr)
        assert vr.status == VacationRequestStatus.PENDING.value
        # Keine Abwesenheit materialisiert.
        assert db.query(Absence).filter(Absence.user_id == admin.id).count() == 0

    def test_self_approve_allowed_sole_admin(self, db, admin, admin_client):
        from app.models import Absence
        vr = _vr(db, admin, start=date(2026, 6, 8), end=None, absence_type="vacation")
        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 200, resp.text
        db.refresh(vr)
        assert vr.status == VacationRequestStatus.APPROVED.value
        assert vr.reviewed_by == admin.id
        assert db.query(Absence).filter(Absence.user_id == admin.id).count() == 1

    def test_reject_own_request_always_allowed(self, db, admin, admin_client):
        _user(db, "adm3", role=UserRole.ADMIN)  # zweiter aktiver Admin
        vr = _vr(db, admin, start=date(2026, 6, 8), end=None, absence_type="vacation")
        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "reject", "rejection_reason": "storno"},
        )
        assert resp.status_code == 200, resp.text
        db.refresh(vr)
        assert vr.status == VacationRequestStatus.REJECTED.value


class TestApproveNoCrossTypeDoubleBooking:
    """R2-c: review_vacation_request prüfte nur auf bestehende Abwesenheiten
    GLEICHEN Typs (+ ohne tenant_id-Filter). Existierte am Tag eine Abwesenheit
    anderen Typs (z.B. krank), rutschte die Genehmigung durch und legte eine
    zweite Abwesenheit (Urlaub) an → Doppelbuchung am selben Tag."""

    def test_approve_blocked_when_other_type_absence_exists(self, db, employee, admin, admin_client):
        from app.models import Absence, AbsenceType
        d = date(2026, 6, 15)  # Montag
        # Bestehende KRANK-Abwesenheit am Tag.
        db.add(Absence(
            user_id=employee.id, tenant_id=DEFAULT_TENANT_ID,
            date=d, type=AbsenceType.SICK, hours=8.0,
        ))
        db.commit()
        vr = _vr(db, employee, start=d, end=None, absence_type="vacation")

        resp = admin_client.post(
            f"/api/admin/vacation-requests/{vr.id}/review",
            json={"action": "approve"},
        )
        # Genehmigung muss blockieren (kein Doppel-Insert).
        assert resp.status_code in (400, 409), resp.text
        db.expire_all()
        n = db.query(Absence).filter(
            Absence.user_id == employee.id, Absence.date == d,
        ).count()
        assert n == 1  # weiterhin nur die KRANK-Abwesenheit, keine Doppelbuchung
