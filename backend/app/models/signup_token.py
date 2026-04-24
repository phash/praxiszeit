"""Signup-verification token + DSGVO consent audit (Phase 3 / Issue #94)."""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class SignupToken(Base):
    """Opaque verification link. We store the hash, not the raw token."""

    __tablename__ = "signup_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SignupAuditLog(Base):
    """DSGVO Art. 7 consent proof. Survives tenant deletion for legal record."""

    __tablename__ = "signup_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # nullable — row survives tenant delete
    email = Column(String(255), nullable=False, index=True)
    # 'signup_requested' | 'email_verified' | 'resend_requested'
    event = Column(String(30), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    accepted_terms = Column(Boolean, nullable=True)
    accepted_privacy = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
