"""#121: Tamper-Evidence der time_entry_audit_logs (HMAC row_hash)."""
import re
from datetime import date, time

from app.core import audit_integrity
from app.models import TimeEntryAuditLog
from tests.conftest import DEFAULT_TENANT_ID


def _make_audit(db, test_user, test_admin, **overrides):
    fields = dict(
        tenant_id=DEFAULT_TENANT_ID,
        user_id=test_user.id,
        changed_by=test_admin.id,
        action="update",
        source="manual",
        old_date=date(2026, 1, 6),
        old_start_time=time(8, 0),
        old_end_time=time(16, 0),
        old_break_minutes=30,
        old_note="vorher",
        new_date=date(2026, 1, 6),
        new_start_time=time(8, 0),
        new_end_time=time(17, 0),
        new_break_minutes=60,
        new_note="nachher",
    )
    fields.update(overrides)
    audit = TimeEntryAuditLog(**fields)
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def test_before_insert_sets_row_hash(db, test_user, test_admin):
    """Der before_insert-Event setzt automatisch einen 64-stelligen Hex-Hash."""
    audit = _make_audit(db, test_user, test_admin)
    assert audit.row_hash is not None
    assert re.fullmatch(r"[0-9a-f]{64}", audit.row_hash)


def test_compute_row_hash_deterministic(db, test_user, test_admin):
    audit = _make_audit(db, test_user, test_admin)
    assert audit_integrity.compute_row_hash(audit) == audit_integrity.compute_row_hash(audit)


def test_verify_intact_row(db, test_user, test_admin):
    audit = _make_audit(db, test_user, test_admin)
    assert audit_integrity.verify_row(audit) is True


def test_verify_detects_content_tampering(db, test_user, test_admin):
    """Nachtraegliche Aenderung des Inhalts (ohne Re-Hash — es gibt KEINEN
    before_update-Event) bricht die Verifikation."""
    audit = _make_audit(db, test_user, test_admin)
    assert audit_integrity.verify_row(audit) is True

    audit.new_note = "HEIMLICH GEAENDERT"
    db.commit()
    db.refresh(audit)
    # row_hash blieb der alte -> Inhalt passt nicht mehr.
    assert audit.row_hash is not None
    assert audit_integrity.verify_row(audit) is False


def test_verify_detects_forged_hash(db, test_user, test_admin):
    audit = _make_audit(db, test_user, test_admin)
    audit.row_hash = "0" * 64  # geraten/gefaelscht ohne Schluessel
    assert audit_integrity.verify_row(audit) is False


def test_id_is_bound_into_hash(db, test_user, test_admin):
    """Gleicher Inhalt, andere id -> anderer Hash (verhindert Replay unter neuer id)."""
    a = _make_audit(db, test_user, test_admin)
    import uuid
    h_other_id = audit_integrity.compute_row_hash(
        type("X", (), {**{f: getattr(a, f) for f in audit_integrity._HASHED_FIELDS}, "id": uuid.uuid4()})()
    )
    assert h_other_id != a.row_hash


def test_legacy_row_without_hash_not_verifiable(db, test_user, test_admin):
    """Eine Row ohne row_hash (Legacy / vor dem Feature) gilt als nicht
    verifizierbar — verify_row False, aber NICHT als Manipulation zu werten."""
    audit = _make_audit(db, test_user, test_admin)
    audit.row_hash = None
    assert audit_integrity.verify_row(audit) is False
