from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class ErrorLog(Base):
    """Aggregated error log for admin monitoring."""

    __tablename__ = "error_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level = Column(String(20), nullable=False, index=True)          # 'error', 'warning', 'critical'
    logger = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    path = Column(String(500), nullable=True)
    method = Column(String(10), nullable=True)
    status_code = Column(Integer, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    fingerprint = Column(String(64), nullable=False, index=True)    # SHA256 for deduplication
    count = Column(Integer, nullable=False, default=1)
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(20), nullable=False, default='open')     # 'open', 'ignored', 'resolved'
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    github_issue_url = Column(String(500), nullable=True)

    def __repr__(self):
        return f"<ErrorLog(id={self.id}, level={self.level}, count={self.count}, status={self.status})>"
