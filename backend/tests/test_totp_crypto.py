"""Tests for at-rest TOTP-secret encryption (DSGVO Art. 32, Audit 2026-06-17).

The router (auth.py) stores the TOTP secret Fernet-encrypted and decrypts it
before verification; legacy plaintext rows stay verifiable and get re-encrypted
on the next successful login. These unit tests pin that contract at the
``totp_crypto`` boundary so a regression can't silently re-introduce plaintext
storage.
"""
import pyotp

from app.core import totp_crypto
from app.services import auth_service


class TestTotpCryptoRoundtrip:
    def test_encrypt_then_decrypt_recovers_plaintext(self):
        """Verschlüsseln + Entschlüsseln liefert das Original-Secret zurück."""
        secret = auth_service.generate_totp_secret()
        token = totp_crypto.encrypt_secret(secret)
        assert token != secret                       # tatsächlich verschlüsselt
        assert totp_crypto.decrypt_secret(token) == secret

    def test_ciphertext_is_not_base32_plaintext(self):
        """Der gespeicherte Wert darf das Base32-Secret nicht im Klartext enthalten."""
        secret = auth_service.generate_totp_secret()
        token = totp_crypto.encrypt_secret(secret)
        assert secret not in token

    def test_is_encrypted_true_for_token_false_for_plaintext(self):
        secret = auth_service.generate_totp_secret()
        assert totp_crypto.is_encrypted(totp_crypto.encrypt_secret(secret)) is True
        assert totp_crypto.is_encrypted(secret) is False        # legacy base32
        assert totp_crypto.is_encrypted("") is False
        assert totp_crypto.is_encrypted(None) is False

    def test_decrypt_tolerates_legacy_plaintext(self):
        """Bestands-Klartext (vor der Verschlüsselung) wird unverändert
        zurückgegeben, damit Alt-Secrets weiter verifizieren."""
        legacy = pyotp.random_base32()
        assert totp_crypto.decrypt_secret(legacy) == legacy

    def test_fernet_token_fits_column(self):
        """Der Ciphertext muss in das verbreiterte VARCHAR(255) passen (Migration 050)."""
        secret = auth_service.generate_totp_secret()
        token = totp_crypto.encrypt_secret(secret)
        assert len(token) <= 255

    def test_verification_works_through_encryption(self):
        """End-to-end: ein gegen das verschlüsselte Secret entschlüsselter Code
        verifiziert korrekt (so wie der /login- und /totp/verify-Pfad es tut)."""
        secret = auth_service.generate_totp_secret()
        token = totp_crypto.encrypt_secret(secret)
        code = pyotp.TOTP(secret).now()
        accepted = auth_service.verify_totp_with_counter(
            totp_crypto.decrypt_secret(token), code, None
        )
        assert accepted is not None
