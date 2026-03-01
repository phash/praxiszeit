from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class SystemSetting(Base):
    """Key-value store for runtime-configurable application settings."""

    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<SystemSetting(key={self.key}, value={self.value})>"
