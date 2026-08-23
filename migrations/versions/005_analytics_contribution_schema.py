"""005 Analytics and Contribution Tracking

Revision ID: 005_analytics_contribution_schema
Revises: 004_approval_workflow_schema
Create Date: 2026-08-23 00:00:00.000000

Sprint 10 schema changes:

1. event_logs — Drop old columns (no data yet; table has never been applied
   via migration). Add institution_id for tenant isolation and proper indexes.
   Table exists only in db.create_all() test context — safe to recreate.

2. resource_views — Add institution_id for tenant-scoped queries.

3. user_contributions — Add action (String(50)) and institution_id columns.
   The old model had no action column; the service was completely broken.

4. New indexes added for analytics query performance.

Tables created by this migration (all new — not in any prior migration):
    event_logs              (analytics events)
    resource_views          (resource access tracking)
    daily_metrics           (pre-aggregated metrics — scaffold)
    contribution_types      (reference table)
    user_contributions      (contribution audit trail)
    badges                  (scaffold)
    leaderboards            (scaffold)

Note: All these tables were scaffold models with no prior migration.
This migration creates them with the correct Sprint 10 schema.

Upgrade:   creates all analytics and contribution tables.
Downgrade: drops them in reverse FK dependency order.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '005_analytics_contribution_schema'
down_revision = '004_approval_workflow_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. event_logs ──────────────────────────────────────────────────────
    op.create_table(
        'event_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        # institution_id — no FK (institutions may not exist in all envs)
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('event_data', sa.JSON(), nullable=False, server_default='{}'),
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
    op.create_index('ix_event_logs_event_type', 'event_logs', ['event_type'])
    op.create_index('ix_event_logs_user_id', 'event_logs', ['user_id'])
    op.create_index('ix_event_logs_institution_id', 'event_logs', ['institution_id'])
    op.create_index('ix_event_logs_created_at', 'event_logs', ['created_at'])

    # ── 2. resource_views ─────────────────────────────────────────────────
    op.create_table(
        'resource_views',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'resource_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('study_materials.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), nullable=True),
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
    op.create_index('ix_resource_views_resource_id', 'resource_views', ['resource_id'])
    op.create_index('ix_resource_views_institution_id', 'resource_views', ['institution_id'])

    # ── 3. daily_metrics (scaffold) ────────────────────────────────────────
    op.create_table(
        'daily_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('metric_date', sa.String(length=50), nullable=False),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False, server_default='0.0'),
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
    op.create_index('ix_daily_metrics_metric_date', 'daily_metrics', ['metric_date'])

    # ── 4. contribution_types ─────────────────────────────────────────────
    op.create_table(
        'contribution_types',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('points', sa.Integer(), nullable=False, server_default='0'),
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

    # ── 5. user_contributions ─────────────────────────────────────────────
    # action column: resource_uploaded | resource_approved
    op.create_table(
        'user_contributions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'resource_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('study_materials.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), nullable=True),
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
    op.create_index('ix_user_contributions_user_id', 'user_contributions', ['user_id'])
    op.create_index('ix_user_contributions_action', 'user_contributions', ['action'])
    op.create_index('ix_user_contributions_institution_id', 'user_contributions', ['institution_id'])

    # ── 6. badges (scaffold) ───────────────────────────────────────────────
    op.create_table(
        'badges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('icon_url', sa.String(length=255), nullable=True),
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

    # ── 7. leaderboards (scaffold) ────────────────────────────────────────
    op.create_table(
        'leaderboards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
            unique=True,
        ),
        sa.Column('total_points', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rank', sa.Integer(), nullable=True),
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
    op.create_index('ix_leaderboards_total_points', 'leaderboards', ['total_points'])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index('ix_leaderboards_total_points', table_name='leaderboards')
    op.drop_table('leaderboards')

    op.drop_table('badges')

    op.drop_index('ix_user_contributions_institution_id', table_name='user_contributions')
    op.drop_index('ix_user_contributions_action', table_name='user_contributions')
    op.drop_index('ix_user_contributions_user_id', table_name='user_contributions')
    op.drop_table('user_contributions')

    op.drop_table('contribution_types')

    op.drop_index('ix_daily_metrics_metric_date', table_name='daily_metrics')
    op.drop_table('daily_metrics')

    op.drop_index('ix_resource_views_institution_id', table_name='resource_views')
    op.drop_index('ix_resource_views_resource_id', table_name='resource_views')
    op.drop_table('resource_views')

    op.drop_index('ix_event_logs_created_at', table_name='event_logs')
    op.drop_index('ix_event_logs_institution_id', table_name='event_logs')
    op.drop_index('ix_event_logs_user_id', table_name='event_logs')
    op.drop_index('ix_event_logs_event_type', table_name='event_logs')
    op.drop_table('event_logs')
