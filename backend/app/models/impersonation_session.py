"""Impersonation-Session-Log (#370): read-only "Login als …".

Jede Impersonation-Session (ein Admin sieht die App aus MA-Sicht) wird hier
protokolliert — Rechenschaftspflicht Art. 5 Abs. 2 DSGVO. Die Impersonation ist
strikt read-only (``ImpersonationReadOnlyMiddleware``), es entstehen also keine
MA-zugerechneten Schreib-Aktionen; dieses Log belegt allein *wer wann wen*
angesehen hat.

Tenant-scoped (RLS ``tenant_isolation``, Migration 060). Beide User-FKs mit
``ondelete=CASCADE`` → der DSGVO-Purge (Art. 17) eines Users räumt seine
Sessions automatisch ab (kein ForeignKeyViolation auf Postgres); ``purge_user``
löscht sie zusätzlich explizit (SQLite-Tests laufen mit FK aus).
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ImpersonationSession(Base):
    __tablename__ = "impersonation_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    # The admin who started the session (real actor).
    impersonator_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The employee whose view was assumed.
    target_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_impersonation_sessions_tenant_started", "tenant_id", "started_at"),
    )

    def __repr__(self):
        return f"<ImpersonationSession(id={self.id}, impersonator={self.impersonator_id}, target={self.target_id})>"
