"""Regressionstests für die Runde-3-Findings (ArbZG/DSGVO).

- ArbZG §5: die Ruhezeitberechnung nutzt die ungekappten Rohstempel (#201), nicht
  die work-window-gekappten Zeiten — sonst bleibt ein echter Verstoß unentdeckt.
- DSGVO Art.15/§16: der Selbstexport trägt reason_id + Klartextnamen des eigenen
  Abwesenheitsgrundes (#312).
"""
import uuid
from datetime import date, time

from app.models import User, UserRole, TimeEntry, Absence, AbsenceType, AbsenceReason
from app.models.absence import AbsenceReasonBehavior
from app.services import rest_time_service, lifecycle_service
from tests.conftest import DEFAULT_TENANT_ID


def _user(db, name="rt_user"):
    u = User(
        id=uuid.uuid4(), username=f"{name}_{uuid.uuid4().hex[:5]}",
        email=f"{uuid.uuid4().hex[:5]}@t.local", password_hash="x",
        first_name="Rest", last_name="Zeit", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_rest_time_violation_uses_raw_end_time(db):
    """§5: Tag 1 gekappt 17:00 (raw 21:00), Tag 2 Start 07:00. Gekappt wären das
    14h Ruhe (konform) — tatsächlich nur 10h (Verstoß). Die Prüfung muss den
    Rohstempel heranziehen und den Verstoß melden."""
    u = _user(db)
    db.add(TimeEntry(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 2),
        start_time=time(8, 0), end_time=time(17, 0), raw_end_time=time(21, 0),
    ))
    db.add(TimeEntry(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 3),
        start_time=time(7, 0), end_time=time(15, 0),
    ))
    db.commit()
    violations = rest_time_service.check_rest_time_violations(db, u, 2026, month=3)
    # Genau der 02.→03.03.-Übergang muss als Verstoß auftauchen (10h < 11h).
    assert any(v.get("actual_rest_hours", 99) < 11 for v in violations), violations


def test_self_export_includes_custom_reason(db):
    """DSGVO Art.15/§16: eine Abwesenheit mit eigenem Grund liefert reason_id +
    Klartextnamen im Selbstexport."""
    u = _user(db, "exp_user")
    reason = AbsenceReason(
        id=uuid.uuid4(), tenant_id=DEFAULT_TENANT_ID, name="Berufsschule",
        base_behavior=AbsenceReasonBehavior.WORKED.value, is_active=True,
    )
    db.add(reason)
    db.commit()
    db.add(Absence(
        user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 3, 4),
        type=AbsenceType.TRAINING, hours=8.0, reason_id=reason.id,
    ))
    db.commit()
    payload = lifecycle_service.build_self_export_payload(db, u)
    rid = str(reason.id)
    assert any(a.get("reason_id") == rid for a in payload["absences"]), payload["absences"]
    assert payload["reason_names"].get(rid) == "Berufsschule"
