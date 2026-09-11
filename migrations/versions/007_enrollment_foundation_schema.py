"""007 Enrollment Foundation Schema

Revision ID: 007_enrollment_foundation_schema
Revises: 006_notifications_schema
Create Date: 2026-09-01 00:00:00.000000

Sprint 12 schema changes — Enrollment Foundation:

Establishes the minimum enrollment schema required before Student/Faculty
workflows can be implemented.

Tables created:
    academic_years          — academic year reference table (2024–2025 etc.)
    student_enrollments     — user ↔ program ↔ academic_year link
    course_enrollments      — student ↔ subject ↔ semester link
    instructor_assignments  — instructor ↔ subject ↔ semester link

Key constraints added:
    - institution_id on all enrollment tables (denormalised for tenant isolation)
    - UniqueConstraint on each enrollment table to prevent duplicate enrollments
    - Indexes on user/student/instructor_id and institution_id for query perf

Previous models were scaffolds with no migration and no unique constraints.
This migration creates them fresh with the Sprint 12 security-correct schema.

Upgrade:   creates all enrollment tables.
Downgrade: drops them in reverse FK dependency order.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '007_enrollment_foundation_schema'
down_revision = '006_notifications_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. academic_years ─────────────────────────────────────────────────────
    op.create_table(
        'academic_years',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('start_year', sa.Integer(), nullable=False),
        sa.Column('end_year', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=50), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('start_year', 'end_year', name='uq_academic_years_start_end'),
    )

    # ── 2. student_enrollments ────────────────────────────────────────────────
    op.create_table(
        'student_enrollments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('program_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('academic_year_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('academic_years.id', ondelete='CASCADE'), nullable=False),
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            'user_id', 'program_id', 'academic_year_id',
            name='uq_student_enrollments_user_program_year'
        ),
    )
    op.create_index('ix_student_enrollments_user_id', 'student_enrollments', ['user_id'])
    op.create_index('ix_student_enrollments_institution_id', 'student_enrollments', ['institution_id'])
    op.create_index('ix_student_enrollments_status', 'student_enrollments', ['status'])

    # ── 3. course_enrollments ─────────────────────────────────────────────────
    op.create_table(
        'course_enrollments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('student_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('subjects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('semester_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('semesters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('grade', sa.String(length=5), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            'student_id', 'course_id', 'semester_id',
            name='uq_course_enrollments_student_course_semester'
        ),
    )
    op.create_index('ix_course_enrollments_student_id', 'course_enrollments', ['student_id'])
    op.create_index('ix_course_enrollments_institution_id', 'course_enrollments', ['institution_id'])

    # ── 4. instructor_assignments ─────────────────────────────────────────────
    op.create_table(
        'instructor_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('instructor_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('subjects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('semester_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('semesters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('institution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            'instructor_id', 'course_id', 'semester_id',
            name='uq_instructor_assignments_instructor_course_semester'
        ),
    )
    op.create_index('ix_instructor_assignments_instructor_id', 'instructor_assignments', ['instructor_id'])
    op.create_index('ix_instructor_assignments_institution_id', 'instructor_assignments', ['institution_id'])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index('ix_instructor_assignments_institution_id', table_name='instructor_assignments')
    op.drop_index('ix_instructor_assignments_instructor_id', table_name='instructor_assignments')
    op.drop_table('instructor_assignments')

    op.drop_index('ix_course_enrollments_institution_id', table_name='course_enrollments')
    op.drop_index('ix_course_enrollments_student_id', table_name='course_enrollments')
    op.drop_table('course_enrollments')

    op.drop_index('ix_student_enrollments_status', table_name='student_enrollments')
    op.drop_index('ix_student_enrollments_institution_id', table_name='student_enrollments')
    op.drop_index('ix_student_enrollments_user_id', table_name='student_enrollments')
    op.drop_table('student_enrollments')

    op.drop_table('academic_years')
