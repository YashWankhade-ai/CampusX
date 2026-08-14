"""001 Core Identity & Institution Schema for CampusX

Revision ID: 001_core_identity_schema
Revises: 
Create Date: 2026-08-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_core_identity_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Create institutions table
    op.create_table(
        'institutions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('short_name', sa.String(length=50), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('domain_whitelist', sa.JSON(), nullable=False),
        sa.Column('logo_url', sa.String(length=2048), nullable=True),
        sa.Column('website_url', sa.String(length=2048), nullable=True),
        sa.Column('address_line1', sa.String(length=200), nullable=True),
        sa.Column('address_line2', sa.String(length=200), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=100), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True, server_default='India'),
        sa.Column('postal_code', sa.String(length=20), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('accreditation_code', sa.String(length=50), nullable=True),
        sa.Column('subscription_tier', sa.String(length=50), nullable=False, server_default='free'),
        sa.Column('subscription_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('max_storage_bytes', sa.BigInteger(), nullable=False, server_default='10737418240'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('settings_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index('ix_institutions_code', 'institutions', ['code'], unique=True)
    op.create_index('ix_institutions_is_active', 'institutions', ['is_active'])

    # 2. Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('institutions.id', ondelete='CASCADE'), nullable=True),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('email_normalized', sa.String(length=320), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.Column('display_name', sa.String(length=80), nullable=True),
        sa.Column('avatar_url', sa.String(length=2048), nullable=True),
        sa.Column('department_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('password_hash', sa.String(length=512), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending_verification'),
        sa.Column('failed_login_attempts', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='Asia/Kolkata'),
        sa.Column('locale', sa.String(length=10), nullable=False, server_default='en'),
        sa.Column('notification_prefs_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('institution_id', 'email_normalized', name='uq_users_email_normalized_per_institution')
    )
    op.create_index('ix_users_institution_id', 'users', ['institution_id'])
    op.create_index('uq_users_email_normalized', 'users', ['email_normalized'])
    op.create_index('ix_users_status', 'users', ['status'])

def downgrade() -> None:
    op.drop_index('ix_users_status', table_name='users')
    op.drop_index('uq_users_email_normalized', table_name='users')
    op.drop_index('ix_users_institution_id', table_name='users')
    op.drop_table('users')

    op.drop_index('ix_institutions_is_active', table_name='institutions')
    op.drop_index('ix_institutions_code', table_name='institutions')
    op.drop_table('institutions')
