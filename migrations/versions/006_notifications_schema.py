"""006 Notifications Schema

Revision ID: 006_notifications_schema
Revises: 005_analytics_contribution_schema
Create Date: 2026-08-27 00:00:00.000000

Sprint 11 schema changes:

Notifications table — completely new (no prior migration).
The scaffold model existed but was never migrated.

Schema:
  notifications:
    - id                UUID PK
    - recipient_id      UUID FK users.id CASCADE
    - institution_id    UUID nullable (denormalized tenant scope)
    - notification_type VARCHAR(60) NOT NULL (allowlisted in service)
    - title             VARCHAR(255) NOT NULL
    - message           TEXT NOT NULL
    - resource_id       UUID FK study_materials.id SET NULL nullable
    - is_read           BOOLEAN default false
    - read_at           TIMESTAMP WITH TZ nullable
    - action_url        VARCHAR(500) nullable
    - created_at / updated_at / is_deleted / deleted_at (from BaseModel)

Indexes:
  - ix_notifications_recipient_created  (recipient_id, created_at)   — primary query
  - ix_notifications_recipient_is_read  (recipient_id, is_read)       — unread filter
  - ix_notifications_institution_id     (institution_id)              — admin queries

Scaffold tables kept from prior schema:
  - notification_templates  (not wired, Sprint 11)
  - user_devices            (not wired, Sprint 11)

Upgrade:  creates notifications, notification_templates, user_devices
Downgrade: drops in reverse dependency order
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '006_notifications_schema'
down_revision = '005_analytics_contribution_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. notification_templates ─────────────────────────────────────────
    op.create_table(
        'notification_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('body_template', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── 2. notifications ──────────────────────────────────────────────────
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'recipient_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        # institution_id denormalized — no FK (institutions may not exist in all envs)
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('notification_type', sa.String(length=60), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column(
            'resource_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('study_materials.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('action_url', sa.String(length=500), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Primary query: user's inbox ordered by recency
    op.create_index(
        'ix_notifications_recipient_created',
        'notifications',
        ['recipient_id', 'created_at'],
    )
    # Unread filter (most common API call)
    op.create_index(
        'ix_notifications_recipient_is_read',
        'notifications',
        ['recipient_id', 'is_read'],
    )
    # Institution-scoped admin queries
    op.create_index(
        'ix_notifications_institution_id',
        'notifications',
        ['institution_id'],
    )

    # ── 3. user_devices (scaffold) ────────────────────────────────────────
    op.create_table(
        'user_devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('device_token', sa.String(length=255), nullable=False, unique=True),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('user_devices')

    op.drop_index('ix_notifications_institution_id', table_name='notifications')
    op.drop_index('ix_notifications_recipient_is_read', table_name='notifications')
    op.drop_index('ix_notifications_recipient_created', table_name='notifications')
    op.drop_table('notifications')

    op.drop_table('notification_templates')
