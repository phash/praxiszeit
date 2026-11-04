"""Teil B: verkuerzter Tag (eigenes Datum, z. B. Brueckentag).

Soll an diesem Tag = min(Tagessoll laut Snapshot, ``max_hours``). Der 24./31.12.
laeuft weiter ueber die Sondertage-Einstellung, nicht ueber diese Tabelle.
"""
import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class ReducedDay(Base):
    __tablename__ = "reduced_days"
    __table_args__ = (
        UniqueConstraint("tenant_id", "date", name="uq_reduced_days_tenant_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Kein index=True: das UNIQUE (tenant_id, date) deckt tenant_id bereits ab.
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    date = Column(Date, nullable=False)
    label = Column(String(100), nullable=False)
    max_hours = Column(Numeric(4, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # ON DELETE SET NULL: darf den Art.-17-Hard-Delete (purge_user) nie blockieren.
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<ReducedDay(date={self.date}, max_hours={self.max_hours})>"
