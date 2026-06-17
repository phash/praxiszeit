"""Widen users.totp_secret 64 -> 255 for Fernet-encrypted TOTP secrets.

DSGVO Audit 2026-06-17 (HIGH, Art. 32): the TOTP shared secret is now stored
ENCRYPTED (Fernet, key derived from SECRET_KEY via HKDF — see
app/core/totp_crypto.py) instead of plaintext base32. A Fernet token for a
~32-char base32 secret is ~140 chars and overflows the original String(64).

Legacy plaintext rows keep verifying (decrypt is tolerant) and are re-encrypted
on the next successful 2FA login — so there is intentionally NO key-dependent
data migration here (one that would silently no-op without SECRET_KEY present).

Revision ID: 050_widen_totp_secret
Revises: 049_rls_stripe_signup_audit
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '050_widen_totp_secret'
down_revision = '049_rls_stripe_signup_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'users', 'totp_secret',
        existing_type=sa.String(64),
        type_=sa.String(255),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Note: only safe if no encrypted (long) secrets are present.
    op.alter_column(
        'users', 'totp_secret',
        existing_type=sa.String(255),
        type_=sa.String(64),
        existing_nullable=True,
    )
