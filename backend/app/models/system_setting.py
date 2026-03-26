from sqlalchemy import Column, String, Text, DateTime, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base


class SystemSetting(Base):
    """Key-value store for runtime-configurable application settings."""

    __tablename__ = "system_settings"
    __table_args__ = (
        PrimaryKeyConstraint('key', 'tenant_id'),
    )

    key = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<SystemSetting(key={self.key}, tenant_id={self.tenant_id}, value={self.value})>"
