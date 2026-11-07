"""Tamper-evidence for ``time_entry_audit_logs`` (#121, #537).

Each audit row carries a per-row HMAC (``row_hash``) over its integrity-relevant
content, keyed by a value DERIVED from ``SECRET_KEY`` via HKDF-SHA256 (same
pattern as ``app/core/totp_crypto.py``). The key therefore lives OUTSIDE the
database — ``SECRET_KEY`` is persisted in ``config/.secret-key`` / the
environment, never in a table — so an attacker who can only WRITE rows cannot
forge a valid ``row_hash``.

Hash versions:

* **v2** (``hash_version IS NULL``, rows written before migration 076): fields
  incl. the foreign keys ``time_entry_id``/``changed_by``/``change_request_id``.
  Those are ``ON DELETE SET NULL`` — deleting a time entry nulled the column and
  broke the hash (A2-1). Migration 076 copied the values into the immutable
  ``*_ref`` columns; v2 rows are verified against those copies. Rows whose entry
  was deleted BEFORE 076 cannot be told apart from tampering
  (``legacy_entry_deleted``).
* **v3** (``hash_version = 3``): hashes the ``*_ref`` copies instead of the
  foreign keys, ``created_at`` and the actual stamps (raw start/end, presence
  end, uncredited minutes). The foreign keys must be NULL or equal to their
  copy.

Row deletion: ``chain_seq``/``chain_prev``/``chain_hash`` link the rows of a
tenant into a chain (set when sealing, ``audit_chain_service``). A deleted
sealed row leaves a gap; legitimate deletions (Art. 17, retention) write a
hashed marker row that names the removed links. Rows not yet sealed (≤ 1 day,
the daily job seals) are protected only by the database rights: the app role
may not UPDATE/DELETE the table (trigger + revoked grants, migration 076).

Rotating ``SECRET_KEY`` makes existing hashes unverifiable (same blast radius as
session invalidation).
"""
import hashlib
import hmac
import logging
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

logger = logging.getLogger(__name__)

CURRENT_HASH_VERSION = 3

# Versioned context label — changing it (or SECRET_KEY) invalidiert alte Hashes.
# v2 (Review 2026-06-23, 2. Schleife): laengen-praefigierte Kanonisierung statt
# '|'-Join (Delimiter-Injection-Haertung). v3 nutzt denselben Schluessel; die
# Version steht selbst im kanonischen Text.
_HKDF_INFO = b"praxiszeit-audit-row-hmac-v2"
_HKDF_INFO_CHAIN = b"praxiszeit-audit-chain-v1"

# v2: Feldliste unveraendert (Altbestand muss pruefbar bleiben). Die drei
# Fremdschluessel werden beim Pruefen durch ihre festen Kopien ersetzt.
_HASHED_FIELDS_V2 = (
    "id", "tenant_id", "time_entry_id", "user_id", "changed_by",
    "action", "source",
    "old_date", "old_start_time", "old_end_time", "old_break_minutes", "old_note",
    "new_date", "new_start_time", "new_end_time", "new_break_minutes", "new_note",
    "change_request_id",
)
_V2_REF_SUBSTITUTES = {
    "time_entry_id": "entry_ref",
    "changed_by": "changed_by_ref",
    "change_request_id": "change_request_ref",
}

_HASHED_FIELDS_V3 = (
    "hash_version", "id", "tenant_id", "entry_ref", "user_id", "changed_by_ref",
    "action", "source",
    "old_date", "old_start_time", "old_end_time", "old_break_minutes", "old_note",
    "old_raw_start_time", "old_raw_end_time", "old_presence_end_time", "old_uncredited_minutes",
    "new_date", "new_start_time", "new_end_time", "new_break_minutes", "new_note",
    "new_raw_start_time", "new_raw_end_time", "new_presence_end_time", "new_uncredited_minutes",
    "change_request_ref", "created_at",
)

# Fremdschluessel → feste Kopie (v3: FK muss NULL oder gleich der Kopie sein).
FK_REFS = (
    ("time_entry_id", "entry_ref"),
    ("changed_by", "changed_by_ref"),
    ("change_request_id", "change_request_ref"),
)


def _derive(info: bytes) -> bytes:
    """32-byte HMAC key from SECRET_KEY. Cheap — not cached so tests that
    monkeypatch SECRET_KEY get the matching key."""
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=info,
    ).derive(settings.SECRET_KEY.encode("utf-8"))


def _audit_key() -> bytes:
    return _derive(_HKDF_INFO)


def canonical_timestamp(value) -> str:
    """created_at kanonisch: UTC, Mikrosekunden. PostgreSQL liefert ein
    zeitzonenbehaftetes Datum (Sitzungszeitzone), SQLite ein naives — das
    Anlegen setzt UTC, naive Werte gelten also als UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    return str(value)


def _value(audit, field: str, version: int):
    if version == 2:
        field = _V2_REF_SUBSTITUTES.get(field, field)
    value = getattr(audit, field, None)
    if field == "created_at" and value is not None:
        return canonical_timestamp(value)
    return value


def _canonical(audit, version: int) -> bytes:
    # Laengen-praefigiert + feldbenannt: ein '|' / Newline im Wert (nur die
    # *_note-Felder sind Freitext) kann die Feldgrenzen nicht verschieben, und
    # eine Umsortierung der Felder ist ausgeschlossen. NULL ('N') und der
    # Leerstring ('0:') bleiben unterscheidbar.
    fields = _HASHED_FIELDS_V3 if version == 3 else _HASHED_FIELDS_V2
    parts = []
    for field in fields:
        value = _value(audit, field, version)
        if value is None:
            parts.append(f"{field}:N")
        else:
            s = str(value)
            parts.append(f"{field}:{len(s)}:{s}")
    return "\n".join(parts).encode("utf-8")


def row_version(audit) -> int:
    return 3 if getattr(audit, "hash_version", None) == 3 else 2


def compute_row_hash(audit) -> str:
    """HMAC-SHA256 hex digest (64 chars) im Schema der Zeile (v2/v3)."""
    return hmac.new(_audit_key(), _canonical(audit, row_version(audit)), hashlib.sha256).hexdigest()


def refs_consistent(audit) -> bool:
    """v3: ein Fremdschluessel darf nur NULL (ON DELETE SET NULL) oder gleich
    seiner festen Kopie sein — sonst wurde er umgebogen."""
    for fk, ref in FK_REFS:
        value = getattr(audit, fk, None)
        if value is not None and value != getattr(audit, ref, None):
            return False
    return True


def verify_row(audit) -> bool:
    """True wenn der gespeicherte row_hash zum neu berechneten passt (und bei v3
    die Fremdschluessel zu ihren Kopien). Konstante Zeit beim Vergleich."""
    if not audit.row_hash:
        return False
    if row_version(audit) == 3 and not refs_consistent(audit):
        return False
    return hmac.compare_digest(audit.row_hash, compute_row_hash(audit))


def compute_chain_hash(tenant_id, seq: int, row_id, prev: str) -> str:
    """Kettenglied: bindet Mandant, Position, Zeilen-id und das vorige Glied.
    Bewusst NICHT der Inhalt — der steht im row_hash, und ein legitimer
    Notiz-Scrub (Art. 17) soll die Kette nicht brechen."""
    msg = f"{tenant_id}\n{int(seq)}\n{row_id}\n{prev or ''}".encode("utf-8")
    return hmac.new(_derive(_HKDF_INFO_CHAIN), msg, hashlib.sha256).hexdigest()


def verify_chain_link(audit) -> bool:
    if audit.chain_seq is None or not audit.chain_hash:
        return False
    return hmac.compare_digest(
        audit.chain_hash,
        compute_chain_hash(audit.tenant_id, audit.chain_seq, audit.id, audit.chain_prev),
    )
