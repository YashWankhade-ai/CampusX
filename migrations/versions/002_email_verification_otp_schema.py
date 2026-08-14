"""002 Email Verification OTP Schema for CampusX

Revision ID: 002_email_verification_otp_schema
Revises: 001_core_identity_schema
Create Date: 2026-08-11 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002_email_verification_otp_schema'
down_revision = '001_core_identity_schema'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'otp_codes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('purpose', sa.String(length=30), server_default='email_verification', nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempt_count', sa.SmallInteger(), server_default='0', nullable=False),
        sa.Column('max_attempts', sa.SmallInteger(), server_default='5', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index('ix_otp_codes_email_purpose', 'otp_codes', ['email', 'purpose'])
    op.create_index('ix_otp_codes_expires_at', 'otp_codes', ['expires_at'])

def downgrade() -> None:
    op.drop_index('ix_otp_codes_expires_at', table_name='otp_codes')
    op.drop_index('ix_otp_codes_email_purpose', table_name='otp_codes')
    op.drop_table('otp_codes')
