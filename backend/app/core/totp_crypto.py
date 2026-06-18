"""At-rest encryption for TOTP secrets (DSGVO Art. 32 / Audit 2026-06-17 HIGH).

The TOTP shared secret IS a credential: anyone holding the plaintext can mint
valid 2FA codes, so storing it in the clear defeats the second factor entirely
if the database is exfiltrated. We encrypt it with Fernet (AES-128-CBC + HMAC),
keyed by a value DERIVED from ``SECRET_KEY`` via HKDF-SHA256. The key therefore
lives OUTSIDE the database (SECRET_KEY is persisted in ``config/.secret-key`` /
the environment, never in a table) and we add no new key-file/config surface.

Backward compatibility: ``decrypt_secret`` tolerates legacy plaintext base32
secrets written before this change. Callers re-encrypt opportunistically after a
successful verification (same pattern as the bcrypt_sha256 rehash-on-login), so
existing rows migrate to ciphertext WITHOUT a key-dependent Alembic data
migration (which would silently no-op if SECRET_KEY were absent at migrate time).

⚠️ Rotating ``SECRET_KEY`` makes stored TOTP secrets undecryptable — the same
blast radius as session invalidation. Affected users must re-enroll 2FA. This is
documented and acceptable for the on-prem single-instance deployment model.
"""
import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

logger = logging.getLogger(__name__)

# Versioned context label — changing it (or SECRET_KEY) invalidates old tokens.
_HKDF_INFO = b"praxiszeit-totp-secret-encryption-v1"


def _looks_like_token(stored: str) -> bool:
    """Heuristik: Fernet-Tokens sind urlsafe-base64 eines fuehrenden 0x80-
    Versionsbytes und beginnen daher IMMER mit ``gAAAAA``. Legacy-base32-TOTP-
    Secrets bestehen nur aus Grossbuchstaben A-Z und Ziffern 2-7 (nie lowercase)."""
    return stored.startswith("gAAAAA")


def _fernet() -> Fernet:
    """Derive the Fernet instance from SECRET_KEY. Cheap (a few hash ops) — not
    cached so tests that monkeypatch SECRET_KEY get the matching key."""
    key_material = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt_secret(plain: str) -> str:
    """Encrypt a plaintext base32 TOTP secret to a Fernet token (ASCII str)."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(stored: str) -> str:
    """Return the plaintext TOTP secret.

    Tolerant of legacy rows: if ``stored`` is not a valid Fernet token we treat
    it as a pre-encryption base32 secret and return it unchanged.
    """
    if not stored:
        return stored
    try:
        return _fernet().decrypt(stored.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        if _looks_like_token(stored):
            # Sieht aus wie ein Fernet-Token, laesst sich aber nicht entschluesseln
            # -> SECRET_KEY wurde rotiert / passt nicht. Das Secret ist verloren;
            # der Nutzer muss 2FA neu einrichten. Laut loggen, sonst aeussert es
            # sich nur als "Ungueltiger TOTP-Code" (sieht aus wie Tippfehler/Drift).
            logger.warning(
                "TOTP-Secret nicht entschluesselbar (SECRET_KEY rotiert?). "
                "Betroffener Nutzer muss 2FA neu einrichten."
            )
        return stored


def is_encrypted(stored: str) -> bool:
    """True if ``stored`` is a Fernet token we can decrypt (vs. legacy plaintext)."""
    if not stored:
        return False
    try:
        _fernet().decrypt(stored.encode("ascii"))
        return True
    except (InvalidToken, ValueError):
        return False
