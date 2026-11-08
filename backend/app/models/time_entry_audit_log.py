from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, Index, SmallInteger, String, Date, Time, Integer, Text, DateTime, ForeignKey, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import logging
import uuid
from app.database import Base

logger = logging.getLogger(__name__)


class TimeEntryAuditLog(Base):
    """Audit log for all changes to time entries."""

    __tablename__ = "time_entry_audit_logs"
    __table_args__ = (
        Index("uq_audit_tenant_chain_seq", "tenant_id", "chain_seq", unique=True),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    time_entry_id = Column(UUID(as_uuid=True), ForeignKey("time_entries.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)  # affected employee
    # #537 (A2-8, Migration 076): nullable + ON DELETE SET NULL — die
    # Endloeschung eines Urhebers (Art. 17) laesst die Zeile stehen und zeigt
    # "geloeschte Person"; vorher wurde die Zeile auf den handelnden Verwalter
    # umgehaengt und die Urheberschaft damit umgeschrieben.
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # admin who made change

    # #537 (A2-1): unveraenderliche Kopien der drei Fremdschluessel, beim Anlegen
    # gesetzt (Listener unten) und nie genullt. Die Pruefsumme laeuft ueber sie,
    # nicht ueber die Fremdschluessel, die PostgreSQL bei einer Loeschung nullt.
    entry_ref = Column(UUID(as_uuid=True), nullable=True, index=True)
    changed_by_ref = Column(UUID(as_uuid=True), nullable=True)
    change_request_ref = Column(UUID(as_uuid=True), nullable=True)

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

    # #537 (A2-3): die tatsaechlichen Stempel neben den angerechneten Zeiten —
    # Rohbeginn/Rohende, Ende der Anwesenheit (``work_window_service.
    # presence_end``) und nicht angerechnete Minuten, je vorher/nachher.
    # Gefuellt zentral im ``before_flush``-Listener aus dem Zeiteintrag, damit
    # jede Schreibstelle (auch Loeschungen) sie mitschreibt.
    old_raw_start_time = Column(Time, nullable=True)
    old_raw_end_time = Column(Time, nullable=True)
    old_presence_end_time = Column(Time, nullable=True)
    old_uncredited_minutes = Column(Integer, nullable=True)
    new_raw_start_time = Column(Time, nullable=True)
    new_raw_end_time = Column(Time, nullable=True)
    new_presence_end_time = Column(Time, nullable=True)
    new_uncredited_minutes = Column(Integer, nullable=True)

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
    # #537: Pruefsummen-Schema. NULL = Altbestand (v2-Hash oder ungehasht),
    # 3 = Schema mit festen Verweisen, created_at und Rohstempeln.
    hash_version = Column(SmallInteger, nullable=True)

    # #537 (A2-2): Kettenglied je Mandant, gesetzt beim Versiegeln
    # (``audit_chain_service.seal_chain``), nie beim Anlegen. Eine geloeschte
    # Zeile hinterlaesst eine Luecke in ``chain_seq``.
    chain_seq = Column(BigInteger, nullable=True)
    chain_prev = Column(String(64), nullable=True)
    chain_hash = Column(String(64), nullable=True)

    def __repr__(self):
        return f"<TimeEntryAuditLog(id={self.id}, action={self.action}, user_id={self.user_id})>"


@event.listens_for(TimeEntryAuditLog, "before_insert")
def _audit_set_row_hash(mapper, connection, target):
    """#121/#537: Bei jedem Insert den row_hash berechnen — zentral hier, statt an
    den ~40 Audit-Insert-Stellen. id muss vorher feststehen (wird in den Hash
    gebunden, damit ein gueltiges (Inhalt, Hash)-Paar nicht unter neuer id
    replayt werden kann); der Python-Default uuid4 ist zur before_insert-Zeit
    nicht garantiert gesetzt. ``created_at`` wird hier gesetzt (statt vom
    Server), weil es seit v3 in der Pruefsumme steht.

    Ein Fehler beim Hashen wird NICHT mehr verschluckt (vorher: Zeile mit
    ``row_hash = NULL``, die als Altbestand durchging, A2-2): ohne Pruefsumme
    keine Protokollzeile, und ohne Protokollzeile keine Aenderung.
    Lazy-Import, damit das Model-Modul nicht app.config zieht."""
    from app.core import audit_integrity

    if target.id is None:
        target.id = uuid.uuid4()
    if target.created_at is None:
        target.created_at = datetime.now(timezone.utc)
    if target.entry_ref is None:
        target.entry_ref = target.time_entry_id
    if target.changed_by_ref is None:
        target.changed_by_ref = target.changed_by
    if target.change_request_ref is None:
        target.change_request_ref = target.change_request_id
    target.hash_version = audit_integrity.CURRENT_HASH_VERSION
    target.row_hash = audit_integrity.compute_row_hash(target)
