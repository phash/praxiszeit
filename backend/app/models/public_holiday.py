from sqlalchemy import Boolean, Column, Date, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.database import Base


class PublicHoliday(Base):
    """Public holiday model.

    Holds both workalendar-seeded statutory holidays (per Bundesland) and
    admin-created local/regional holidays (Schützenfest, Karneval, …).

    ``source`` distinguishes provenance:
    * ``'workalendar'`` — auto-seeded; deleted/regenerated on a Bundesland resync.
    * ``'admin'``       — manually maintained; survives a resync.

    ``is_custom`` mirrors ``source == 'admin'`` and is exposed to the frontend
    so the UI can offer edit/delete only for custom rows. Both standard and
    custom rows live in the same table, so they reduce Sollzeit identically.
    """

    __tablename__ = "public_holidays"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False, index=True)
    is_custom = Column(Boolean, nullable=False, default=False, server_default="false")
    source = Column(String(20), nullable=False, default="workalendar", server_default="workalendar")

    def __repr__(self):
        return f"<PublicHoliday(date={self.date}, name={self.name}, source={self.source})>"
