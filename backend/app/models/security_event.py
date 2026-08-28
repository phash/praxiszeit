"""#425: Ablage fuer sicherheitsrelevante Vorgaenge (Art. 5 Abs. 2 DSGVO).

Bewusst getrennt von ``time_entry_audit_logs``: das ist die §16-Domaene und
ueber ``row_hash`` (#121) manipulationsgeschuetzt — dort gehoert kein
Passwort-Reset hinein. Bewusst auch nicht das rotierende Anwendungsprotokoll:
ein Nachweis, der nach ein paar Wochen weg ist, ist keiner.

``tenant_id`` darf NULL sein (Vorgang ohne Mandantenbezug). ``actor`` beschreibt,
WER gehandelt hat, auch wenn das kein Anwendungskonto war — beim
Kommandozeilen-Reset z. B. ``cli:root@<host>``.
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base

# Ereignis-Kennungen. String(50) — laenger schneidet PostgreSQL beim INSERT hart
# ab (dieselbe Falle wie time_entry_audit_logs.source, dort real passiert).
EVENT_ADMIN_PASSWORD_RESET = "admin_password_reset_cli"
EVENT_TOTP_DISABLED = "totp_disabled_cli"


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    event = Column(String(50), nullable=False, index=True)
    # ON DELETE SET NULL: eine Protokollzeile darf den Art.-17-Hard-Delete eines
    # Nutzers niemals blockieren (siehe purge_user; bei #305 real passiert).
    subject_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor = Column(String(200), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<SecurityEvent(event={self.event}, actor={self.actor}, at={self.created_at})>"
