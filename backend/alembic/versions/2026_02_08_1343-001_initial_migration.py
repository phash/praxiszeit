"""initial migration

Revision ID: 001
Revises:
Create Date: 2026-02-08 13:43:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table('users',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('role', sa.Enum('ADMIN', 'EMPLOYEE', name='userrole'), nullable=False),
    sa.Column('weekly_hours', sa.Numeric(precision=4, scale=1), nullable=False),
    sa.Column('vacation_days', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Create public_holidays table
    op.create_table('public_holidays',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('date')
    )
    op.create_index(op.f('ix_public_holidays_date'), 'public_holidays', ['date'], unique=False)
    op.create_index(op.f('ix_public_holidays_year'), 'public_holidays', ['year'], unique=False)

    # Create time_entries table
    op.create_table('time_entries',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('end_time', sa.Time(), nullable=False),
    sa.Column('break_minutes', sa.Integer(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'date', 'start_time', name='uq_user_date_start')
    )
    op.create_index(op.f('ix_time_entries_date'), 'time_entries', ['date'], unique=False)
    op.create_index(op.f('ix_time_entries_user_id'), 'time_entries', ['user_id'], unique=False)

    # Create absences table
    op.create_table('absences',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('type', sa.Enum('VACATION', 'SICK', 'TRAINING', 'OTHER', name='absencetype'), nullable=False),
    sa.Column('hours', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'date', 'type', name='uq_user_date_type')
    )
    op.create_index(op.f('ix_absences_date'), 'absences', ['date'], unique=False)
    op.create_index(op.f('ix_absences_user_id'), 'absences', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_absences_user_id'), table_name='absences')
    op.drop_index(op.f('ix_absences_date'), table_name='absences')
    op.drop_table('absences')
    op.drop_index(op.f('ix_time_entries_user_id'), table_name='time_entries')
    op.drop_index(op.f('ix_time_entries_date'), table_name='time_entries')
    op.drop_table('time_entries')
    op.drop_index(op.f('ix_public_holidays_year'), table_name='public_holidays')
    op.drop_index(op.f('ix_public_holidays_date'), table_name='public_holidays')
    op.drop_table('public_holidays')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.execute('DROP TYPE absencetype')
    op.execute('DROP TYPE userrole')
