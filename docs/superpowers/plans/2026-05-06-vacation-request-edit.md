# Vacation Request Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mitarbeiter und Admins können offene (`pending`) Urlaubsanträge editieren — mit Re-Validation, Audit-Eintrag, Modal-UI und E2E-Verifikation.

**Architecture:** Zwei PATCH-Endpoints (`/api/vacation-requests/{id}` für MA, `/api/admin/vacation-requests/{id}` für Admin) mit `with_for_update`-Lock. Beide schreiben einen `TimeEntryAuditLog`-Row mit `source="vacation_request_edit"`. Frontend: wiederverwendbare `VacationRequestEditModal`-Komponente (FocusTrap-Pattern wie `ConfirmDialog`), in Admin- und MA-Page eingebaut.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2 (Backend), React 18 + TS + Tailwind + axios (Frontend), pytest + Playwright (Tests).

**Spec:** `docs/superpowers/specs/2026-05-06-vacation-request-edit-design.md`

---

## File Structure

**Backend:**
- Modify: `backend/app/schemas/vacation_request.py` — neues `VacationRequestUpdate`-Schema
- Modify: `backend/app/routers/vacation_requests.py` — Audit-Helper + PATCH-Endpoint (MA)
- Modify: `backend/app/routers/admin_vacations.py` — PATCH-Endpoint (Admin)
- Create: `backend/tests/test_vacation_request_edit.py` — pytest

**Frontend:**
- Create: `frontend/src/components/VacationRequestEditModal.tsx`
- Modify: `frontend/src/pages/admin/VacationApprovals.tsx` — Hookup
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx` — Hookup

**E2E:**
- Modify: `e2e/tests/admin/vacation-approvals.spec.ts` — neuer Block "edit"
- Modify: `e2e/tests/employee/absences.spec.ts` — neuer Block "edit own pending vacation request"

---

## Task 1: Pydantic-Schema `VacationRequestUpdate`

**Files:**
- Modify: `backend/app/schemas/vacation_request.py`

- [ ] **Step 1: Add new schema after `VacationRequestCreate`**

Insert nach `VacationRequestCreate` (vor `VacationRequestReview`):

```python
class VacationRequestUpdate(BaseModel):
    """Partial update for a PENDING vacation request.

    All fields optional — caller may patch any subset. The router
    re-validates the full effective state (start <= end, budget,
    work-day window, overlap with other pending) after merging.
    """

    date: Optional[date] = None
    end_date: Optional[date] = None
    hours: Optional[float] = None
    note: Optional[str] = None
    absence_type: Optional[str] = None

    @field_validator('absence_type')
    @classmethod
    def validate_absence_type(cls, v):
        if v is None:
            return v
        allowed = {"vacation", "training", "overtime", "other"}
        if v not in allowed:
            raise ValueError(f'absence_type muss einer von {allowed} sein')
        return v
```

- [ ] **Step 2: Verify schema imports compile**

Run: `docker compose exec backend python -c "from app.schemas.vacation_request import VacationRequestUpdate; print(VacationRequestUpdate.model_fields.keys())"`
Expected: `dict_keys(['date', 'end_date', 'hours', 'note', 'absence_type'])`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/vacation_request.py
git commit -m "feat(vacation): VacationRequestUpdate schema for partial edits"
```

---

## Task 2: Audit-Format-Helper

**Files:**
- Modify: `backend/app/routers/vacation_requests.py:1-20` (helper) — add helper after `_enrich`
- Test: included in Task 4 integration tests

- [ ] **Step 1: Add helper function**

Insert direkt nach der `_enrich`-Funktion (Zeile ~42):

```python
def _format_vacation_request_audit_text(vr: VacationRequest) -> str:
    """Compact one-line representation of a vacation request for audit logs.

    Used as `old_note` / `new_note` payload on edit/cancel events. Note is
    truncated to 200 chars to keep audit-log queries cheap.
    """
    end = vr.end_date if vr.end_date else vr.date
    note = (vr.note or "").replace("\n", " ").strip()[:200]
    text = (
        f"vacation_request {vr.id} | "
        f"{vr.date}..{end} | "
        f"{vr.absence_type or 'vacation'} | "
        f"{float(vr.hours):.2f}h"
    )
    if note:
        text += f" | {note}"
    return text
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/vacation_requests.py
git commit -m "feat(vacation): audit-text formatter for VR edits"
```

---

## Task 3: MA-PATCH-Endpoint (employee edits own pending request)

**Files:**
- Modify: `backend/app/routers/vacation_requests.py` (insert vor dem `withdraw_vacation_request`-Endpoint)
- Test: see Task 4

- [ ] **Step 1: Add imports if missing**

Sicherstellen, dass am Top der Datei vorhanden ist:

```python
from app.schemas.vacation_request import (
    VacationRequestCreate,
    VacationRequestResponse,
    VacationRequestUpdate,
)
```

- [ ] **Step 2: Implement endpoint**

Insert nach dem `cancel_approved_vacation_request`-Helper, vor `withdraw_vacation_request`:

```python
@router.patch("/{request_id}", response_model=VacationRequestResponse)
def update_vacation_request(
    request_id: str,
    data: VacationRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit an own PENDING vacation request.

    All fields are optional; only the provided ones are updated. The
    router re-validates the resulting full state (range, work-day window,
    budget, pending-overlap) — same checks as create_vacation_request,
    but the overlap check excludes this request itself.
    """
    # F-028 / belt-and-suspenders tenant scoping (F-026)
    vr = (
        db.query(VacationRequest)
        .filter(
            VacationRequest.id == request_id,
            VacationRequest.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not vr:
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")
    if str(vr.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if vr.status != VacationRequestStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Nur offene Anträge können bearbeitet werden",
        )

    # Capture old state for audit BEFORE applying changes
    old_audit_text = _format_vacation_request_audit_text(vr)
    old_date = vr.date

    # Apply patch (merge provided fields)
    new_date = data.date if data.date is not None else vr.date
    new_end_date = data.end_date if data.end_date is not None else vr.end_date
    new_hours = data.hours if data.hours is not None else float(vr.hours)
    new_note = data.note if data.note is not None else vr.note
    new_absence_type = data.absence_type if data.absence_type is not None else vr.absence_type

    # No-op detection: if nothing actually changes, skip everything.
    no_change = (
        new_date == vr.date
        and new_end_date == vr.end_date
        and float(new_hours) == float(vr.hours)
        and new_note == vr.note
        and new_absence_type == vr.absence_type
    )
    if no_change:
        return _enrich(vr, db)

    # Re-validation: range sanity
    effective_end = new_end_date if new_end_date else new_date
    if effective_end < new_date:
        raise HTTPException(status_code=400, detail="Enddatum muss nach dem Startdatum liegen")

    # First/last work day window
    if current_user.first_work_day and new_date < current_user.first_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
    if current_user.last_work_day and effective_end > current_user.last_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")

    # Pending-overlap with OTHER requests
    other_pending = db.query(VacationRequest).filter(
        VacationRequest.id != vr.id,
        VacationRequest.user_id == current_user.id,
        VacationRequest.tenant_id == current_user.tenant_id,
        VacationRequest.status == VacationRequestStatus.PENDING.value,
        VacationRequest.date <= effective_end,
    ).all()
    for e in other_pending:
        e_end = e.end_date if e.end_date else e.date
        if e_end >= new_date:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Offener Urlaubsantrag für Zeitraum {e.date}–{e_end} existiert bereits",
            )

    # Vacation budget (vacation type only; pending requests don't reduce
    # the budget — only Absences do — so no self-exclude needed)
    if new_absence_type == "vacation":
        from app.services import calculation_service
        dates_by_year: dict[int, list] = {}
        d = new_date
        while d <= effective_end:
            if d.weekday() < 5:
                dates_by_year.setdefault(d.year, []).append(d)
            d += timedelta(days=1)
        for check_year, year_dates in dates_by_year.items():
            account = calculation_service.get_vacation_account(db, current_user, check_year)
            year_hours_needed = sum(
                float(calculation_service.get_daily_target_for_date(
                    current_user, dd,
                    weekly_hours=calculation_service.get_weekly_hours_for_date(db, current_user, dd),
                ))
                for dd in year_dates
            )
            if float(account['remaining_hours']) - year_hours_needed < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Nicht genügend Urlaubstage für {check_year} ({account['remaining_days']:.1f} Tage verfügbar)",
                )

    # Apply changes
    vr.date = new_date
    vr.end_date = new_end_date
    vr.hours = new_hours
    vr.note = new_note
    vr.absence_type = new_absence_type

    # Write audit row
    new_audit_text = _format_vacation_request_audit_text(vr)
    audit = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=vr.user_id,
        changed_by=current_user.id,
        action="update",
        old_date=old_date,
        new_date=vr.date,
        old_note=old_audit_text,
        new_note=new_audit_text,
        source="vacation_request_edit",
        tenant_id=vr.tenant_id,
    )
    db.add(audit)
    db.commit()
    db.refresh(vr)
    return _enrich(vr, db)
```

- [ ] **Step 3: Sanity-check the file compiles**

Run: `docker compose exec backend python -c "from app.routers.vacation_requests import update_vacation_request; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/vacation_requests.py
git commit -m "feat(vacation): MA PATCH endpoint for own pending requests"
```

---

## Task 4: Backend tests for MA-PATCH

**Files:**
- Create: `backend/tests/test_vacation_request_edit.py`

- [ ] **Step 1: Write the test file**

```python
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
        employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "neu"}
        )
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
        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).count()
        assert audits == 0

    def test_edit_foreign_request_forbidden(
        self, db, employee, other_employee, other_employee_client
    ):
        vr = _vr(db, employee)
        resp = other_employee_client.patch(
            f"/api/vacation-requests/{vr.id}", json={"note": "hack"}
        )
        assert resp.status_code == 403

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
        # Existing pending: 2026-06-01..2026-06-05
        existing_start = date.today() + timedelta(days=60)
        _vr(db, employee, start=existing_start, end=existing_start + timedelta(days=4))
        # Edit a different pending into overlap
        target = _vr(db, employee, start=date.today() + timedelta(days=80))
        resp = employee_client.patch(
            f"/api/vacation-requests/{target.id}",
            json={"date": (existing_start + timedelta(days=2)).isoformat()},
        )
        assert resp.status_code == 409

    def test_edit_self_overlap_allowed(self, db, employee, employee_client):
        # Editing within own date range must NOT trigger overlap on itself
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
        # Pydantic validation → 422
        assert resp.status_code == 422


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

        audits = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.source == "vacation_request_edit"
        ).all()
        assert len(audits) == 1
        a = audits[0]
        assert a.user_id == employee.id          # affected user
        assert a.changed_by == admin.id          # acting principal

    def test_admin_cannot_edit_foreign_tenant(self, db, default_tenant, admin_client):
        # Foreign tenant
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
```

- [ ] **Step 2: Run test to verify they fail (Admin endpoint not yet built)**

Run: `docker compose cp backend/tests/test_vacation_request_edit.py praxiszeit-backend-1:/app/tests/test_vacation_request_edit.py && docker compose exec backend pytest tests/test_vacation_request_edit.py -v`
Expected: TestEmployeeEdit-Tests sollten **passen** (Endpoint existiert), TestAdminEdit-Tests sollten **fehlschlagen** mit 404 oder 405 (Admin-Endpoint fehlt noch).

> Wenn Employee-Tests fehlschlagen: Backend-Container neu starten (`docker compose cp backend/app/routers/vacation_requests.py praxiszeit-backend-1:/app/app/routers/vacation_requests.py && docker compose cp backend/app/schemas/vacation_request.py praxiszeit-backend-1:/app/app/schemas/vacation_request.py && docker compose restart backend`).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_vacation_request_edit.py
git commit -m "test(vacation): pytest suite for VR edit (MA + admin)"
```

---

## Task 5: Admin-PATCH-Endpoint

**Files:**
- Modify: `backend/app/routers/admin_vacations.py`

- [ ] **Step 1: Add imports**

Sicherstellen am Top der Datei:

```python
from app.schemas.vacation_request import (
    VacationRequestResponse,
    VacationRequestReview,
    VacationRequestUpdate,
)
from app.models import TimeEntryAuditLog
from app.routers.vacation_requests import _format_vacation_request_audit_text
```

- [ ] **Step 2: Implement endpoint**

Insert nach `review_vacation_request`, vor `cancel_vacation_request_as_admin`:

```python
@router.patch("/vacation-requests/{request_id}", response_model=VacationRequestResponse)
def update_vacation_request_as_admin(
    request_id: str,
    data: VacationRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Edit a PENDING vacation request on behalf of the requesting employee.

    Tenant-scoped: 404 (not 403) if the row belongs to another tenant —
    don't leak existence. Mirrors the employee-side validation, but the
    target user is the original requester (not the admin).
    """
    vr = (
        db.query(VacationRequest)
        .filter(
            VacationRequest.id == request_id,
            VacationRequest.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not vr:
        raise HTTPException(status_code=404, detail="Urlaubsantrag nicht gefunden")
    if vr.status != VacationRequestStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Nur offene Anträge können bearbeitet werden",
        )

    # Resolve the target user (owner of the request)
    target_user = db.query(User).filter(
        User.id == vr.user_id,
        User.tenant_id == current_user.tenant_id,
    ).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    old_audit_text = _format_vacation_request_audit_text(vr)
    old_date = vr.date

    # Merge patch
    new_date = data.date if data.date is not None else vr.date
    new_end_date = data.end_date if data.end_date is not None else vr.end_date
    new_hours = data.hours if data.hours is not None else float(vr.hours)
    new_note = data.note if data.note is not None else vr.note
    new_absence_type = data.absence_type if data.absence_type is not None else vr.absence_type

    no_change = (
        new_date == vr.date
        and new_end_date == vr.end_date
        and float(new_hours) == float(vr.hours)
        and new_note == vr.note
        and new_absence_type == vr.absence_type
    )
    if no_change:
        return _enrich_vr_response(vr, db)

    # Re-validation against TARGET USER, not admin
    effective_end = new_end_date if new_end_date else new_date
    if effective_end < new_date:
        raise HTTPException(status_code=400, detail="Enddatum muss nach dem Startdatum liegen")
    if target_user.first_work_day and new_date < target_user.first_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
    if target_user.last_work_day and effective_end > target_user.last_work_day:
        raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")

    other_pending = db.query(VacationRequest).filter(
        VacationRequest.id != vr.id,
        VacationRequest.user_id == target_user.id,
        VacationRequest.tenant_id == current_user.tenant_id,
        VacationRequest.status == VacationRequestStatus.PENDING.value,
        VacationRequest.date <= effective_end,
    ).all()
    for e in other_pending:
        e_end = e.end_date if e.end_date else e.date
        if e_end >= new_date:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Offener Urlaubsantrag für Zeitraum {e.date}–{e_end} existiert bereits",
            )

    if new_absence_type == "vacation":
        dates_by_year: dict[int, list] = {}
        d = new_date
        while d <= effective_end:
            if d.weekday() < 5:
                dates_by_year.setdefault(d.year, []).append(d)
            d += timedelta(days=1)
        for check_year, year_dates in dates_by_year.items():
            account = calculation_service.get_vacation_account(db, target_user, check_year)
            year_hours_needed = sum(
                float(calculation_service.get_daily_target_for_date(
                    target_user, dd,
                    weekly_hours=calculation_service.get_weekly_hours_for_date(db, target_user, dd),
                ))
                for dd in year_dates
            )
            if float(account['remaining_hours']) - year_hours_needed < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Nicht genügend Urlaubstage für {check_year} ({account['remaining_days']:.1f} Tage verfügbar)",
                )

    # Apply
    vr.date = new_date
    vr.end_date = new_end_date
    vr.hours = new_hours
    vr.note = new_note
    vr.absence_type = new_absence_type

    new_audit_text = _format_vacation_request_audit_text(vr)
    audit = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=vr.user_id,                # affected employee
        changed_by=current_user.id,        # admin acting
        action="update",
        old_date=old_date,
        new_date=vr.date,
        old_note=old_audit_text,
        new_note=new_audit_text,
        source="vacation_request_edit",
        tenant_id=vr.tenant_id,
    )
    db.add(audit)
    db.commit()
    db.refresh(vr)
    return _enrich_vr_response(vr, db)
```

- [ ] **Step 3: Run admin pytest**

Run: `docker compose cp backend/app/routers/admin_vacations.py praxiszeit-backend-1:/app/app/routers/admin_vacations.py && docker compose restart backend && sleep 3 && docker compose exec backend pytest tests/test_vacation_request_edit.py -v`
Expected: alle Tests grün (TestEmployeeEdit + TestAdminEdit).

- [ ] **Step 4: Run regression-pertinent tests**

Run: `docker compose exec backend pytest tests/test_vacation_request_cancel.py tests/test_endpoints.py -v --no-header -q | tail -20`
Expected: kein Regress.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin_vacations.py
git commit -m "feat(vacation): admin PATCH endpoint for tenant-scoped edits"
```

---

## Task 6: Frontend `VacationRequestEditModal` component

**Files:**
- Create: `frontend/src/components/VacationRequestEditModal.tsx`

- [ ] **Step 1: Write component**

```typescript
import { useState, useEffect } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { getErrorMessage } from '../utils/errorMessage';
import { parseHours } from '../utils/formatters';

interface VacationRequest {
  id: string;
  date: string;
  end_date?: string;
  hours: number;
  absence_type?: string;
  note?: string;
}

interface VacationRequestEditModalProps {
  request: VacationRequest;
  mode: 'self' | 'admin';
  onClose: () => void;
  onSaved: () => void;
}

export default function VacationRequestEditModal({
  request,
  mode,
  onClose,
  onSaved,
}: VacationRequestEditModalProps) {
  const toast = useToast();
  const [isDateRange, setIsDateRange] = useState<boolean>(!!request.end_date);
  const [date, setDate] = useState<string>(request.date);
  const [endDate, setEndDate] = useState<string>(request.end_date ?? '');
  const [type, setType] = useState<string>(request.absence_type ?? 'vacation');
  const [hours, setHours] = useState<number>(Number(request.hours) || 8);
  const [note, setNote] = useState<string>(request.note ?? '');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setDate(request.date);
    setEndDate(request.end_date ?? '');
    setIsDateRange(!!request.end_date);
    setType(request.absence_type ?? 'vacation');
    setHours(Number(request.hours) || 8);
    setNote(request.note ?? '');
  }, [request.id]);

  const endpoint =
    mode === 'admin'
      ? `/admin/vacation-requests/${request.id}`
      : `/vacation-requests/${request.id}`;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await apiClient.patch(endpoint, {
        date,
        end_date: isDateRange && endDate ? endDate : null,
        hours,
        absence_type: type,
        note: note || null,
      });
      toast.success('Antrag aktualisiert');
      onSaved();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-10000 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <FocusTrap
        focusTrapOptions={{
          escapeDeactivates: true,
          onDeactivate: onClose,
          allowOutsideClick: true,
        }}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-vr-title"
          className="relative bg-white rounded-xl shadow-2xl max-w-lg w-full mx-4 p-6"
        >
          <h3 id="edit-vr-title" className="text-lg font-semibold text-gray-900 mb-4">
            Antrag bearbeiten
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
              <input
                id="edit-vr-isrange"
                type="checkbox"
                checked={isDateRange}
                onChange={(e) => {
                  setIsDateRange(e.target.checked);
                  if (!e.target.checked) setEndDate('');
                }}
                className="w-4 h-4 text-primary border-gray-300 rounded-sm focus:ring-primary"
              />
              <label htmlFor="edit-vr-isrange" className="text-sm font-medium text-gray-700 cursor-pointer">
                Zeitraum (mehrere Tage)
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {isDateRange ? 'Von' : 'Datum'}
                </label>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
              {isDateRange && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    min={date}
                    required={isDateRange}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                  />
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Typ</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                >
                  <option value="vacation">Urlaub</option>
                  <option value="training">Fortbildung (außer Haus)</option>
                  <option value="overtime">Überstundenausgleich</option>
                  <option value="other">Sonstiges</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Stunden {isDateRange && '(pro Tag)'}
                </label>
                <input
                  type="number"
                  inputMode="numeric"
                  step="0.5"
                  value={hours}
                  onChange={(e) => setHours(parseHours(e.target.value))}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-gray-400 mt-1">
                Bitte keine Gesundheitsangaben oder sensiblen Daten eintragen.
              </p>
            </div>

            <div className="mt-6 flex justify-end space-x-3">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                Abbrechen
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium text-white bg-primary hover:bg-primary-dark rounded-lg transition disabled:opacity-50"
              >
                {submitting ? 'Speichern…' : 'Speichern'}
              </button>
            </div>
          </form>
        </div>
      </FocusTrap>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd /home/manuel/claude/praxiszeit/frontend && npx tsc --noEmit`
Expected: No errors. Wenn `parseHours` fehlt → `frontend/src/utils/formatters.ts` prüfen (sollte existieren, da auch von `AbsenceCalendarPage` benutzt).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/VacationRequestEditModal.tsx
git commit -m "feat(vacation): VacationRequestEditModal component"
```

---

## Task 7: Hookup Admin-Page (`VacationApprovals.tsx`)

**Files:**
- Modify: `frontend/src/pages/admin/VacationApprovals.tsx`

- [ ] **Step 1: Add Pencil import + Modal import + state**

In `VacationApprovals.tsx`:

Find: `import { Clock, CheckCircle, XCircle, AlertCircle, Check, X, Trash2 } from 'lucide-react';`
Replace with: `import { Clock, CheckCircle, XCircle, AlertCircle, Check, X, Trash2, Pencil } from 'lucide-react';`

Find: `import { AbsenceType, ABSENCE_TYPE_LABELS, ABSENCE_TYPE_COLORS } from '../../constants/absenceTypes';`
Append after:
```typescript
import VacationRequestEditModal from '../../components/VacationRequestEditModal';
```

- [ ] **Step 2: Add edit-state hook**

Innerhalb der `VacationApprovals`-Funktion, nach dem `settingLoading`-state:

```typescript
const [editingRequest, setEditingRequest] = useState<VacationRequest | null>(null);
```

- [ ] **Step 3: Add edit-button to pending action bar**

Find:
```tsx
                      <div className="flex space-x-3">
                        <button
                          onClick={() => handleApprove(vr.id)}
                          className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg transition"
                        >
                          <Check size={16} />
                          <span>Genehmigen</span>
                        </button>
                        <button
                          onClick={() => setRejectingId(vr.id)}
                          className="flex items-center space-x-2 px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 text-sm rounded-lg transition"
                        >
                          <X size={16} />
                          <span>Ablehnen</span>
                        </button>
                      </div>
```

Replace with:
```tsx
                      <div className="flex space-x-3">
                        <button
                          onClick={() => handleApprove(vr.id)}
                          className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg transition"
                        >
                          <Check size={16} />
                          <span>Genehmigen</span>
                        </button>
                        <button
                          onClick={() => setEditingRequest(vr)}
                          className="flex items-center space-x-2 px-4 py-2 bg-blue-100 hover:bg-blue-200 text-blue-700 text-sm rounded-lg transition"
                        >
                          <Pencil size={16} />
                          <span>Bearbeiten</span>
                        </button>
                        <button
                          onClick={() => setRejectingId(vr.id)}
                          className="flex items-center space-x-2 px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 text-sm rounded-lg transition"
                        >
                          <X size={16} />
                          <span>Ablehnen</span>
                        </button>
                      </div>
```

- [ ] **Step 4: Render modal at component root**

Find: `      <ConfirmDialog`
Insert direkt davor (innerhalb des outer `<div>`):
```tsx
      {editingRequest && (
        <VacationRequestEditModal
          request={editingRequest}
          mode="admin"
          onClose={() => setEditingRequest(null)}
          onSaved={() => {
            setEditingRequest(null);
            fetchRequests();
          }}
        />
      )}
```

- [ ] **Step 5: Type-check + frontend rebuild**

Run: `cd /home/manuel/claude/praxiszeit/frontend && npx tsc --noEmit && cd .. && docker compose build frontend && docker compose up -d frontend`
Expected: clean tsc, frontend container restarts.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/admin/VacationApprovals.tsx
git commit -m "feat(vacation): admin VacationApprovals — Bearbeiten button + modal"
```

---

## Task 8: Hookup MA-Page (`AbsenceCalendarPage.tsx`)

**Files:**
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx`

- [ ] **Step 1: Add imports + state**

Find: `import { Plus, X, Trash2, Clock, CheckCircle, XCircle, ChevronLeft, ChevronRight } from 'lucide-react';`
Replace with: `import { Plus, X, Trash2, Clock, CheckCircle, XCircle, ChevronLeft, ChevronRight, Pencil } from 'lucide-react';`

Find the line: `import { useAuthStore } from '../stores/authStore';`
Append after:
```typescript
import VacationRequestEditModal from '../components/VacationRequestEditModal';
```

Innerhalb der Komponente, nach `const { confirmState, ... } = useConfirm();`:

```typescript
const [editingRequest, setEditingRequest] = useState<VacationRequest | null>(null);
```

- [ ] **Step 2: Add edit-button to pending card**

In dem Block, in dem der Trash-Button für `pending`/`approved future` gerendert wird (nach `if (!isPending && !isApprovedFuture) return null;`), ersetze den `return ( <button ...> )` Block mit einem Wrapper, der für `pending` zusätzlich einen Edit-Button rendert:

Find:
```tsx
                      return (
                        <button
                          onClick={() =>
                            confirm({
                              title: dialog.title,
                              message: dialog.message,
                              confirmLabel: dialog.confirmLabel,
                              variant: 'danger',
                              onConfirm: async () => {
                                try {
                                  await apiClient.delete(`/vacation-requests/${vr.id}`);
                                  toast.success(dialog.successMsg);
                                  fetchMyVacationRequests();
                                } catch (error) {
                                  toast.error(getErrorMessage(error, 'Fehler beim Zurückziehen'));
                                }
                              },
                            })
                          }
                          className="p-3 text-red-600 hover:bg-red-50 rounded-lg transition"
                          title={dialog.buttonTitle}
                        >
                          <Trash2 size={16} />
                        </button>
                      );
```

Replace with:
```tsx
                      return (
                        <div className="flex items-center space-x-1">
                          {isPending && (
                            <button
                              onClick={() => setEditingRequest(vr)}
                              className="p-3 text-blue-600 hover:bg-blue-50 rounded-lg transition"
                              title="Antrag bearbeiten"
                            >
                              <Pencil size={16} />
                            </button>
                          )}
                          <button
                            onClick={() =>
                              confirm({
                                title: dialog.title,
                                message: dialog.message,
                                confirmLabel: dialog.confirmLabel,
                                variant: 'danger',
                                onConfirm: async () => {
                                  try {
                                    await apiClient.delete(`/vacation-requests/${vr.id}`);
                                    toast.success(dialog.successMsg);
                                    fetchMyVacationRequests();
                                  } catch (error) {
                                    toast.error(getErrorMessage(error, 'Fehler beim Zurückziehen'));
                                  }
                                },
                              })
                            }
                            className="p-3 text-red-600 hover:bg-red-50 rounded-lg transition"
                            title={dialog.buttonTitle}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      );
```

- [ ] **Step 3: Render modal at component root**

Find:
```tsx
      <ConfirmDialog
        isOpen={confirmState.isOpen}
```
Insert davor:
```tsx
      {editingRequest && (
        <VacationRequestEditModal
          request={editingRequest}
          mode="self"
          onClose={() => setEditingRequest(null)}
          onSaved={() => {
            setEditingRequest(null);
            fetchMyVacationRequests();
          }}
        />
      )}
```

- [ ] **Step 4: Type-check + rebuild**

Run: `cd /home/manuel/claude/praxiszeit/frontend && npx tsc --noEmit && cd .. && docker compose build frontend && docker compose up -d frontend`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AbsenceCalendarPage.tsx
git commit -m "feat(vacation): MA AbsenceCalendar — Bearbeiten button + modal on pending"
```

---

## Task 9: E2E-Test Admin-Edit

**Files:**
- Modify: `e2e/tests/admin/vacation-approvals.spec.ts`

- [ ] **Step 1: Append new test inside `test.describe('Admin Vacation Approvals', …)`**

Insert vor der schließenden `});` des describe-Blocks:

```typescript
  test('admin edits pending vacation request — note + date', async ({
    adminPage,
    adminApi,
    createVacationRequest,
  }) => {
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });
    } catch {
      test.skip();
      return;
    }

    const startDate = weekdayFromNow(45);
    const newDate = weekdayFromNow(50);
    const uniqueNote = `E2E admin-edit ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const newNote = `${uniqueNote} edited`;
    try {
      await createVacationRequest({
        date: startDate,
        hours: 8,
        note: uniqueNote,
      });
    } catch {
      try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
      test.skip();
      return;
    }

    await adminPage.goto('/admin/vacation-approvals');
    await expect(adminPage.getByRole('heading', { name: 'Abwesenheitsanträge' })).toBeVisible();
    await adminPage.getByRole('button', { name: 'Offen' }).click();
    await adminPage.waitForLoadState('networkidle');

    const card = adminPage.locator('div.bg-white').filter({ hasText: uniqueNote }).first();
    await expect(card).toBeVisible({ timeout: 5000 });
    await card.getByRole('button', { name: 'Bearbeiten' }).click();

    // Modal opens
    const dialog = adminPage.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Change date + note
    await dialog.locator('input[type="date"]').first().fill(newDate);
    const noteInput = dialog.locator('input[type="text"]').first();
    await noteInput.fill(newNote);
    await dialog.getByRole('button', { name: 'Speichern' }).click();

    // Toast confirms
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: /aktualisiert/ })
    ).toBeVisible({ timeout: 10000 });

    // Card should reflect the new note (and disappear from old uniqueNote-only filter
    // because the new note CONTAINS the old uniqueNote — so we re-locate by suffix)
    await adminPage.waitForLoadState('networkidle');
    const updated = adminPage.locator('div.bg-white').filter({ hasText: 'edited' }).first();
    await expect(updated).toBeVisible({ timeout: 5000 });

    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
  });
```

- [ ] **Step 2: Run E2E test (Admin)**

Run: `cd /home/manuel/claude/praxiszeit/e2e && npx playwright test tests/admin/vacation-approvals.spec.ts -g "admin edits pending" --reporter=list`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add e2e/tests/admin/vacation-approvals.spec.ts
git commit -m "test(e2e): admin edits pending vacation request"
```

---

## Task 10: E2E-Test MA-Edit

**Files:**
- Modify: `e2e/tests/employee/absences.spec.ts`

- [ ] **Step 1: Read the file head to confirm import structure**

Run: `head -20 /home/manuel/claude/praxiszeit/e2e/tests/employee/absences.spec.ts`

Note vorhandene Imports + describe-Pattern, damit der neue Test sich daran orientieren kann.

- [ ] **Step 2: Append new test**

Innerhalb des passenden `test.describe`-Blocks (oder neuem) einfügen:

```typescript
  test('employee edits own pending vacation request — hours', async ({
    employeePage,
    adminApi,
    createVacationRequest,
  }) => {
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', { value: 'true' });
    } catch {
      test.skip();
      return;
    }

    const startDate = weekdayFromNow(48);
    const uniqueNote = `E2E self-edit ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      await createVacationRequest({
        date: startDate,
        hours: 8,
        note: uniqueNote,
      });
    } catch {
      try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
      test.skip();
      return;
    }

    await employeePage.goto('/abwesenheiten');
    await employeePage.getByRole('button', { name: /Meine Anträge/ }).click();
    await employeePage.waitForLoadState('networkidle');

    const card = employeePage.locator('div.bg-white').filter({ hasText: uniqueNote }).first();
    await expect(card).toBeVisible({ timeout: 5000 });
    await card.getByRole('button', { name: 'Antrag bearbeiten' }).click();

    const dialog = employeePage.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Change hours
    const hoursInput = dialog.locator('input[type="number"]').first();
    await hoursInput.fill('6');
    await dialog.getByRole('button', { name: 'Speichern' }).click();

    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /aktualisiert/ })
    ).toBeVisible({ timeout: 10000 });

    // The card should now show 6 h
    await employeePage.waitForLoadState('networkidle');
    const updated = employeePage.locator('div.bg-white').filter({ hasText: uniqueNote }).filter({ hasText: '6 h/Tag' }).first();
    await expect(updated).toBeVisible({ timeout: 5000 });

    try { await adminApi.put('/admin/settings/vacation_approval_required', { value: 'false' }); } catch {}
  });
```

> Note: prüfen, dass am Top der Datei `import { weekdayFromNow }` aus `../../helpers/date.helper` importiert ist. Falls nein, hinzufügen.

- [ ] **Step 3: Run E2E test (MA)**

Run: `cd /home/manuel/claude/praxiszeit/e2e && npx playwright test tests/employee/absences.spec.ts -g "employee edits own" --reporter=list`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add e2e/tests/employee/absences.spec.ts
git commit -m "test(e2e): MA edits own pending vacation request"
```

---

## Task 11: Final-Checks (Browser-Sichtprüfung + Audit-Verify)

**Files:**
- (manual)

- [ ] **Step 1: Run full E2E suite**

Run: `cd /home/manuel/claude/praxiszeit/e2e && npx playwright test --reporter=list`
Expected: kein Regress.

- [ ] **Step 2: Run full backend pytest**

Run: `docker compose exec backend pytest tests/ -v --no-header -q | tail -40`
Expected: alle Tests grün, keine vorher-grünen jetzt rot.

- [ ] **Step 3: Manual browser smoke-test**

```
1. Login als admin / Admin2025!
2. Settings → Genehmigungspflicht aktivieren
3. Login als Mitarbeiter
4. Abwesenheiten → Antrag stellen
5. Tab "Meine Anträge" → Pencil-Button → Modal → Hours ändern → Speichern → Toast
6. Reload → neue Stunden persistiert
7. Logout → Admin-Login
8. /admin/vacation-approvals → Card zeigt geänderte Stunden
9. Admin: Bearbeiten → Note anpassen → Speichern
10. /admin/audit (oder DB-Query) zeigt Audit-Row mit source=vacation_request_edit
```

- [ ] **Step 4: Audit-Verify per psql**

Run:
```bash
docker compose exec postgres psql -U praxiszeit -d praxiszeit -c "SELECT action, source, user_id, changed_by, old_note, new_note FROM time_entry_audit_logs WHERE source='vacation_request_edit' ORDER BY created_at DESC LIMIT 5;"
```

Expected: mindestens zwei Rows (eine vom MA-Edit, eine vom Admin-Edit), korrektes `user_id`/`changed_by`.

- [ ] **Step 5: Security/DSGVO-Review-Bericht zusammenstellen**

In Commit-Body / PR-Description die zwei Sektionen aus dem Spec-Dokument (Sektion 6 und 7) übernehmen, mit konkreten Verweisen auf die Implementation:
- AuthZ: `vr.user_id == current_user.id` Check in `vacation_requests.py`
- Tenant-Filter: `VacationRequest.tenant_id == current_user.tenant_id` in beiden Endpoints
- Audit-Eintrag: Code in beiden Endpoints, getestet in `test_vacation_request_edit.py::test_edit_writes_audit_row` + `test_admin_edits_employee_pending`
- DSGVO Art.9: `absence_type='sick'` rejected by Pydantic validator → `test_edit_invalid_absence_type_rejected`

---

## Self-Review Checklist (running this myself)

**Spec coverage:**
- [x] Section 1.1 Schema → Task 1
- [x] Section 1.2 MA-Endpoint → Task 3
- [x] Section 1.3 Admin-Endpoint → Task 5
- [x] Section 1.4 Audit-Helper → Task 2
- [x] Section 1.5 RLS / Tenant → Task 3 + Task 5 explizit Filter, Task 4 Test `test_admin_cannot_edit_foreign_tenant`
- [x] Section 2.1 Modal-Komponente → Task 6
- [x] Section 2.2 UI-Hookup → Task 7 + Task 8
- [x] Section 2.3 Refresh → Task 7 (`fetchRequests`) + Task 8 (`fetchMyVacationRequests`)
- [x] Section 3 Audit-Verhalten → Task 3/5 schreiben Audit-Row, Task 4 testet
- [x] Section 4 Backend-Tests (13 Cases) → Task 4 deckt alle 13 ab (counted: 11 in TestEmployeeEdit + 3 in TestAdminEdit = 14, leichter Overflow ok)
- [x] Section 5 E2E-Tests (3 Cases) → Task 9 (Admin) + Task 10 (MA) decken 3 von 3
- [x] Section 6 Security-Review → Task 11 Step 5
- [x] Section 7 DSGVO-Review → Task 11 Step 5

**Placeholder-Scan:** keine TBDs / "implement later" / "similar to" gefunden.

**Type consistency:** Schema heißt überall `VacationRequestUpdate`, Endpoint-Pfade `/api/vacation-requests/{id}` und `/api/admin/vacation-requests/{id}`, Source-String konsistent `vacation_request_edit` (21 chars), Test-Klassen `TestEmployeeEdit` + `TestAdminEdit`.
