"""Stripe webhook idempotency cache (Phase 4 / Issue #95)."""

from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class StripeEvent(Base):
    __tablename__ = "stripe_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(255), unique=True, nullable=False)
    event_type = Column(String(100), nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    payload_excerpt = Column(Text, nullable=True)
