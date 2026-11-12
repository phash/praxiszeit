"""FE-1 (Release-Review 1.24.0): das Monatsjournal liefert zu jeder Abwesenheit
den Grundtyp (``base_type``) und den eigenen Grund (``reason_id``), damit das
Bearbeiten-Formular einen gültigen ``POST /absences`` bauen kann. ``type`` trägt
bei einem eigenen Grund dessen NAMEN — ein Re-POST damit scheiterte mit 422,
nachdem die alte Abwesenheit schon gelöscht war.

Beide Felder werden maskiert wie ``type`` (Art. 9 DSGVO, Parität zu
``_absence_export_label``): ohne Gesundheitsdaten → ``None``.
"""
from datetime import date
from decimal import Decimal

from app.models import Absence, AbsenceReason, AbsenceType
from app.schemas.journal import JournalResponse
from app.services import journal_service
from tests.conftest import DEFAULT_TENANT_ID


def _reason_absence(db, user, d):
    r = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Kind krank",
                      base_behavior="unpaid_free", is_active=True,
                      tracks_child_sick_limit=True)
    db.add(r); db.commit(); db.refresh(r)
    a = Absence(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d,
                type=AbsenceType.OTHER, hours=Decimal("8"), reason_id=r.id)
    db.add(a); db.commit()
    return r


def _abs(result, iso):
    return next(d for d in result["days"] if d["date"] == iso)["absences"][0]


def test_reason_absence_carries_base_type_and_reason_id(db, test_user):
    r = _reason_absence(db, test_user, date(2026, 3, 5))
    result = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=True)
    a = _abs(result, "2026-03-05")
    assert a["type"] == "Kind krank"
    assert a["base_type"] == "other"
    assert a["reason_id"] == str(r.id)
    # response_model filtert fehlende Felder still weg (CLAUDE.md #485)
    validated = JournalResponse.model_validate(result).model_dump()
    va = next(d for d in validated["days"] if d["date"] == "2026-03-05")["absences"][0]
    assert va["base_type"] == "other"
    assert va["reason_id"] == str(r.id)


def test_reason_absence_masked_without_health_data(db, test_user):
    _reason_absence(db, test_user, date(2026, 3, 5))
    result = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=False)
    a = _abs(result, "2026-03-05")
    assert a["type"] == "absent"
    assert a["base_type"] is None
    assert a["reason_id"] is None


def test_sick_masked_base_type_without_health_data(db, test_user):
    db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id,
                   date=date(2026, 3, 5), type=AbsenceType.SICK, hours=Decimal("8")))
    db.commit()
    masked = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=False)
    assert _abs(masked, "2026-03-05")["base_type"] is None
    shown = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=True)
    a = _abs(shown, "2026-03-05")
    assert a["base_type"] == "sick"
    assert a["reason_id"] is None


def test_plain_vacation_always_carries_base_type(db, test_user):
    db.add(Absence(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id,
                   date=date(2026, 3, 5), type=AbsenceType.VACATION, hours=Decimal("8")))
    db.commit()
    result = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=False)
    a = _abs(result, "2026-03-05")
    assert a["type"] == "vacation"
    assert a["base_type"] == "vacation"
    assert a["reason_id"] is None
