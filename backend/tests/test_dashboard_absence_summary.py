"""calc-03: GET /api/dashboard/absence-summary — tagebasierte Jahreszusammenfassung."""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import Absence, AbsenceType
from tests.conftest import DEFAULT_TENANT_ID


def _client(db, user):
    from app.routers import dashboard
    app = FastAPI()
    app.include_router(dashboard.router)

    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _abs(db, user, d, typ, hours, **kw):
    db.add(Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=typ, hours=hours, **kw))


def test_counts_days_per_type_including_paid_leave(db, test_user):
    _abs(db, test_user, date(2026, 3, 2), AbsenceType.SICK, 8.0)
    _abs(db, test_user, date(2026, 3, 3), AbsenceType.SICK, 8.0)
    _abs(db, test_user, date(2026, 3, 4), AbsenceType.TRAINING, 8.0)
    _abs(db, test_user, date(2026, 3, 5), AbsenceType.PAID_LEAVE, 8.0)
    _abs(db, test_user, date(2026, 3, 6), AbsenceType.OTHER, 4.0, half_day=True)
    _abs(db, test_user, date(2025, 3, 3), AbsenceType.SICK, 8.0)  # anderes Jahr
    db.commit()
    r = _client(db, test_user).get("/api/dashboard/absence-summary?year=2026")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sick_days"] == pytest.approx(2.0)
    assert d["training_days"] == pytest.approx(1.0)
    assert d["paid_leave_days"] == pytest.approx(1.0)
    assert d["other_days"] == pytest.approx(0.5)
    assert d["total_days"] == pytest.approx(d["vacation_days"] + 2.0 + 1.0 + 1.0 + 0.5 + d["overtime_days"])


def test_untracked_user_counts_days_not_hours(db, test_user):
    test_user.track_hours = False
    _abs(db, test_user, date(2026, 3, 2), AbsenceType.SICK, 0.0)
    _abs(db, test_user, date(2026, 3, 3), AbsenceType.TRAINING, 0.0)
    db.commit()
    d = _client(db, test_user).get("/api/dashboard/absence-summary?year=2026").json()
    assert d["sick_days"] == pytest.approx(1.0)
    assert d["training_days"] == pytest.approx(1.0)


def test_impersonation_masks_sensitive_counts(db, test_user):
    """SEC-01: unter Impersonation keine Krank/Sonstiges/Bez.-Freistellung-Zahlen."""
    from fastapi import Request
    from app.routers import dashboard
    _abs(db, test_user, date(2026, 3, 2), AbsenceType.SICK, 8.0)
    _abs(db, test_user, date(2026, 3, 3), AbsenceType.PAID_LEAVE, 8.0)
    _abs(db, test_user, date(2026, 3, 4), AbsenceType.OTHER, 8.0)
    _abs(db, test_user, date(2026, 3, 5), AbsenceType.TRAINING, 8.0)
    db.commit()
    app = FastAPI()
    app.include_router(dashboard.router)

    def override_db():
        yield db

    def impersonated(request: Request):
        request.state.is_impersonating = True
        return test_user
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = impersonated
    r = TestClient(app).get("/api/dashboard/absence-summary?year=2026")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sick_days"] is None
    assert d["other_days"] is None
    assert d["paid_leave_days"] is None
    assert d["training_days"] == pytest.approx(1.0)
    assert d["total_days"] == pytest.approx(d["vacation_days"] + 1.0 + d["overtime_days"])


def test_impersonation_excludes_custom_reason_absences(db, test_user):
    """SEC-01 Nachtrag: Abwesenheit mit eigenem Grund zählt unter Impersonation nirgends."""
    import uuid
    from fastapi import Request
    from app.models import AbsenceReason
    from app.routers import dashboard
    reason = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Reha", base_behavior="worked", is_active=True)
    db.add(reason)
    db.commit()
    _abs(db, test_user, date(2026, 3, 4), AbsenceType.TRAINING, 8.0, reason_id=reason.id)
    _abs(db, test_user, date(2026, 3, 5), AbsenceType.TRAINING, 8.0)
    db.commit()
    app = FastAPI()
    app.include_router(dashboard.router)

    def override_db():
        yield db

    def impersonated(request: Request):
        request.state.is_impersonating = True
        return test_user
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = impersonated
    d = TestClient(app).get("/api/dashboard/absence-summary?year=2026").json()
    assert d["training_days"] == pytest.approx(1.0)
    # Gegenprobe: ohne Impersonation zählen beide
    d2 = _client(db, test_user).get("/api/dashboard/absence-summary?year=2026").json()
    assert d2["training_days"] == pytest.approx(2.0)
