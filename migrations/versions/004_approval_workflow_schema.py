"""004 Approval Workflow Tables + Study Materials

Revision ID: 004_approval_workflow_schema
Revises: 003_rbac_role_permission_tables
Create Date: 2026-08-22 00:00:00.000000

Schema change covered:
- Creates study_materials table (prerequisite FK target for approval_actions)
- Creates approval_workflows, approval_steps, approval_requests tables
- Creates approval_actions table with resource_id (FK → study_materials.id)

IMPORTANT — resource_id vs request_id:
  The Sprint 8 model changed ApprovalAction.request_id (which pointed to
  approval_requests.id) to resource_id (which points to study_materials.id).
  This migration creates the table with the CORRECT column name (resource_id)
  from the start, since the table was never previously migrated.

FK notes for study_materials:
  - topic_id and subject_id are nullable and their referenced tables
    (topics, subjects) do not yet exist in migrations.  The FK constraints
    for those columns are deferred to the academic-schema migration.
  - author_id → users.id is created here (users exists in migration 001).

Upgrade:  creates study_materials, approval_workflows, approval_steps,
          approval_requests, approval_actions.

Downgrade: drops them in reverse dependency order (approval_actions first).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004_approval_workflow_schema'
down_revision = '003_rbac_role_permission_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. study_materials ─────────────────────────────────────────────────
    # Required before approval_actions (resource_id FK target).
    # topic_id / subject_id FKs are deferred: those tables are created in the
    # academic-schema migration which does not yet exist.
    op.create_table(
        'study_materials',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        # nullable FK to topics — constraint added when topics migration exists
        sa.Column('topic_id', postgresql.UUID(as_uuid=True), nullable=True),
        # nullable FK to subjects — constraint added when subjects migration exists
        sa.Column('subject_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            'author_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'material_type',
            sa.String(length=50),
            nullable=False,
            server_default='NOTE',
        ),
        sa.Column(
            'status',
            sa.String(length=50),
            nullable=False,
            server_default='PENDING',
        ),
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
    op.create_index('ix_study_materials_title', 'study_materials', ['title'])
    op.create_index('ix_study_materials_material_type', 'study_materials', ['material_type'])
    op.create_index('ix_study_materials_status', 'study_materials', ['status'])

    # ── 2. approval_workflows ──────────────────────────────────────────────
    op.create_table(
        'approval_workflows',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
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

    # ── 3. approval_steps ─────────────────────────────────────────────────
    op.create_table(
        'approval_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'workflow_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('approval_workflows.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'role_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('roles.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('step_order', sa.Integer(), nullable=False, server_default='1'),
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

    # ── 4. approval_requests ───────────────────────────────────────────────
    op.create_table(
        'approval_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'workflow_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('approval_workflows.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'requester_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('target_resource_id', sa.String(length=100), nullable=True),
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

    # ── 5. approval_actions ────────────────────────────────────────────────
    # SCHEMA CHANGE (P0): resource_id FK → study_materials.id
    # The original unmigrated model had request_id → approval_requests.id.
    # This migration creates the table with the correct Sprint 8 schema.
    op.create_table(
        'approval_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'resource_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('study_materials.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'approver_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
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
    op.create_index('ix_approval_actions_resource_id', 'approval_actions', ['resource_id'])
    op.create_index('ix_approval_actions_approver_id', 'approval_actions', ['approver_id'])


def downgrade() -> None:
    # Drop in reverse FK dependency order
    op.drop_index('ix_approval_actions_approver_id', table_name='approval_actions')
    op.drop_index('ix_approval_actions_resource_id', table_name='approval_actions')
    op.drop_table('approval_actions')

    op.drop_table('approval_requests')
    op.drop_table('approval_steps')
    op.drop_table('approval_workflows')

    op.drop_index('ix_study_materials_status', table_name='study_materials')
    op.drop_index('ix_study_materials_material_type', table_name='study_materials')
    op.drop_index('ix_study_materials_title', table_name='study_materials')
    op.drop_table('study_materials')
