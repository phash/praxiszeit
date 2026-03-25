from sqlalchemy import Column, Date, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.database import Base


class PublicHoliday(Base):
    """Public holiday model for Bavarian holidays."""

    __tablename__ = "public_holidays"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False, index=True)

    def __repr__(self):
        return f"<PublicHoliday(date={self.date}, name={self.name})>"
