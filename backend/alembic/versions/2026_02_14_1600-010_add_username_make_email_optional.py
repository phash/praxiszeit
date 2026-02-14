"""add username column, make email optional

Revision ID: 010
Revises: 009
Create Date: 2026-02-14 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add username column (nullable first for backfill)
    op.add_column('users', sa.Column('username', sa.String(100), nullable=True))

    # 2. Backfill: set username = email for existing users
    op.execute("UPDATE users SET username = email WHERE username IS NULL")

    # 3. Make username NOT NULL and add unique index
    op.alter_column('users', 'username', nullable=False)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)

    # 4. Make email nullable
    op.alter_column('users', 'email',
                    existing_type=sa.String(255),
                    nullable=True)

    # 5. Drop unique index on email, recreate as non-unique index
    op.drop_index('ix_users_email', table_name='users')
    op.create_index('ix_users_email', 'users', ['email'], unique=False)


def downgrade() -> None:
    # 1. Restore unique index on email
    op.drop_index('ix_users_email', table_name='users')
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 2. Make email NOT NULL again (backfill from username if needed)
    op.execute("UPDATE users SET email = username WHERE email IS NULL")
    op.alter_column('users', 'email',
                    existing_type=sa.String(255),
                    nullable=False)

    # 3. Drop username column and index
    op.drop_index('ix_users_username', table_name='users')
    op.drop_column('users', 'username')
