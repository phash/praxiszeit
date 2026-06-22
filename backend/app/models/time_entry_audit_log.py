from sqlalchemy import Column, String, Date, Time, Integer, Text, DateTime, ForeignKey, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import logging
import uuid
from app.database import Base

logger = logging.getLogger(__name__)


class TimeEntryAuditLog(Base):
    """Audit log for all changes to time entries."""

    __tablename__ = "time_entry_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    time_entry_id = Column(UUID(as_uuid=True), ForeignKey("time_entries.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)  # affected employee
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)  # admin who made change

    # Originally 20 chars (create/update/delete); widened to 40 in migration 044
    # because arbzg_superadmin_export (23) and license_readonly_mode_entered (29)
    # overflowed varchar(20) → StringDataRightTruncation → 500 on Postgres.
    action = Column(String(40), nullable=False)  # "create", "update", "delete"

    # Old values (null for create)
    old_date = Column(Date, nullable=True)
    old_start_time = Column(Time, nullable=True)
    old_end_time = Column(Time, nullable=True)
    old_break_minutes = Column(Integer, nullable=True)
    old_note = Column(Text, nullable=True)

    # New values (null for delete)
    new_date = Column(Date, nullable=True)
    new_start_time = Column(Time, nullable=True)
    new_end_time = Column(Time, nullable=True)
    new_break_minutes = Column(Integer, nullable=True)
    new_note = Column(Text, nullable=True)

    # Originally 20 chars (manual / import / change_request); widened to 40 in
    # migration 037 because vacation_request_cancel (24 chars) didn't fit.
    source = Column(String(40), nullable=False, default="manual")  # e.g. manual, import, change_request, vacation_request_cancel
    change_request_id = Column(UUID(as_uuid=True), ForeignKey("change_requests.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # #121: Tamper-Evidence. HMAC-SHA256 (64 Hex-Zeichen) ueber den Row-Inhalt,
    # mit einem aus SECRET_KEY abgeleiteten Schluessel (siehe app/core/
    # audit_integrity.py). Nullable: vor diesem Feature geschriebene Rows haben
    # keinen Hash ("legacy", nicht "tampered").
    row_hash = Column(String(64), nullable=True)

    def __repr__(self):
        return f"<TimeEntryAuditLog(id={self.id}, action={self.action}, user_id={self.user_id})>"


@event.listens_for(TimeEntryAuditLog, "before_insert")
def _audit_set_row_hash(mapper, connection, target):
    """#121: Bei jedem Insert den row_hash berechnen — zentral hier, statt an den
    ~15 Audit-Insert-Stellen. id muss vorher feststehen (wird in den Hash gebunden,
    damit ein gueltiges (Inhalt, Hash)-Paar nicht unter neuer id replayt werden
    kann); der Python-Default uuid4 ist zur before_insert-Zeit nicht garantiert
    gesetzt. Lazy-Import, damit das Model-Modul nicht app.config zieht."""
    if target.id is None:
        target.id = uuid.uuid4()
    try:
        from app.core import audit_integrity
        target.row_hash = audit_integrity.compute_row_hash(target)
    except Exception:  # pragma: no cover - ein Hash-Fehler darf den Audit-Insert NIE kippen
        logger.exception("audit row_hash konnte nicht berechnet werden")
        target.row_hash = None
