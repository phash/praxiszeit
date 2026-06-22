"""Tamper-evidence for ``time_entry_audit_logs`` (#121, Security-Review P4.2).

Each audit row carries a per-row HMAC (``row_hash``) over its integrity-relevant
content, keyed by a value DERIVED from ``SECRET_KEY`` via HKDF-SHA256 (same
pattern as ``app/core/totp_crypto.py``). The key therefore lives OUTSIDE the
database — ``SECRET_KEY`` is persisted in ``config/.secret-key`` / the
environment, never in a table — so an attacker who can only WRITE rows (e.g. via
an SQL-injection elsewhere) cannot forge a valid ``row_hash``, and any post-hoc
MODIFICATION of an existing audit row's content is detected by
``GET /api/admin/audit/verify-integrity``.

Scope / limits (v1):

* Detects: modification of audit content + forged rows (without the key). ``id``
  is part of the hash, so a valid (content, hash) pair cannot be replayed under
  a different id.
* ``created_at`` is intentionally NOT hashed (DB-assigned timestamp; excluding it
  avoids serialization round-trip false-positives between Postgres and the
  SQLite test engine).
* A strict ``prev_hash`` hash-CHAIN (which would additionally detect row
  DELETION via gaps) is deferred: it needs per-tenant insert serialization to
  avoid concurrency forks. DSGVO Art. 17 deletion intentionally leaves a gap —
  acceptable per #121.
* Rotating ``SECRET_KEY`` makes existing ``row_hash`` values unverifiable (same
  blast radius as session invalidation). Legacy rows (``row_hash IS NULL``,
  written before this feature) are reported as ``legacy``, not ``tampered``.
"""
import hashlib
import hmac
import logging

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

logger = logging.getLogger(__name__)

# Versioned context label — changing it (or SECRET_KEY) invalidates old hashes.
_HKDF_INFO = b"praxiszeit-audit-row-hmac-v1"

# Integrity-relevant fields that round-trip cleanly (UUID/date/time/int/str).
# created_at is excluded on purpose (see module docstring).
_HASHED_FIELDS = (
    "id", "tenant_id", "time_entry_id", "user_id", "changed_by",
    "action", "source",
    "old_date", "old_start_time", "old_end_time", "old_break_minutes", "old_note",
    "new_date", "new_start_time", "new_end_time", "new_break_minutes", "new_note",
    "change_request_id",
)


def _audit_key() -> bytes:
    """Derive the 32-byte HMAC key from SECRET_KEY. Cheap (a few hash ops) — not
    cached so tests that monkeypatch SECRET_KEY get the matching key."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(settings.SECRET_KEY.encode("utf-8"))


def _canonical(audit) -> bytes:
    # NULL und der Leerstring duerfen NICHT kollidieren -> NULL als Sentinel.
    parts = []
    for field in _HASHED_FIELDS:
        value = getattr(audit, field, None)
        parts.append("\x00" if value is None else str(value))
    return "|".join(parts).encode("utf-8")


def compute_row_hash(audit) -> str:
    """HMAC-SHA256 hex digest (64 chars) ueber den integritaetsrelevanten Inhalt."""
    return hmac.new(_audit_key(), _canonical(audit), hashlib.sha256).hexdigest()


def verify_row(audit) -> bool:
    """True wenn der gespeicherte row_hash zum neu berechneten passt.

    Nur fuer Rows MIT row_hash aufrufen (Legacy-Rows ohne Hash sind nicht
    verifizierbar). Nutzt compare_digest (konstante Zeit)."""
    return bool(audit.row_hash) and hmac.compare_digest(
        audit.row_hash, compute_row_hash(audit)
    )
