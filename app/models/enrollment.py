"""Enrollment models — Sprint 12 foundation.

Establishes the minimum enrollment schema required before Student/Faculty
workflows can be implemented.

Architecture requirements:
    - StudentEnrollment: links a User to a Program for an AcademicYear.
      institution_id denormalised for efficient tenant-scoped queries.
      Unique constraint prevents duplicate enrollment in same program/year.

    - CourseEnrollment: links a Student User to a Subject for a Semester.
      institution_id denormalised for tenant isolation.
      Unique constraint prevents duplicate enrollment in same course/semester.

    - InstructorAssignment: links a Faculty User to a Subject for a Semester.
      institution_id denormalised for tenant isolation.
      Unique constraint prevents duplicate assignment.

    - AcademicYear: standalone year range entity (not institution-scoped at
      this level — shared reference table across institution as in specification).

Constraints:
    - All FK references use ondelete="CASCADE" to clean up on user deletion.
    - institution_id is indexed on all enrollment tables for tenant scoping.
    - Duplicate prevention via UniqueConstraint on each enrollment table.

What is NOT here (reserved for Student/Faculty modules):
    - Enrollment approval workflow
    - Enrollment status transitions
    - Transcript / grade aggregation
    - Timetable / schedule
"""
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Boolean, UniqueConstraint, Index
from app.models.base import BaseModel


class AcademicYear(BaseModel):
    """Reference table for academic year ranges (e.g., 2024–2025).

    Not institution-scoped — academic years are shared reference data.
    """
    __tablename__ = "academic_years"

    start_year: Mapped[int] = mapped_column(nullable=False)
    end_year: Mapped[int] = mapped_column(nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("start_year", "end_year", name="uq_academic_years_start_end"),
    )


class StudentEnrollment(BaseModel):
    """Links a student User to a Program for an AcademicYear.

    institution_id is denormalised from the student's User.institution_id
    for efficient tenant-scoped queries.

    Unique constraint prevents a student from being enrolled in the same
    program twice in the same academic year.
    """
    __tablename__ = "student_enrollments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), nullable=False
    )
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_years.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    # Valid values: active, graduated, suspended, withdrawn

    __table_args__ = (
        UniqueConstraint(
            "user_id", "program_id", "academic_year_id",
            name="uq_student_enrollments_user_program_year"
        ),
        Index("ix_student_enrollments_user_id", "user_id"),
        Index("ix_student_enrollments_institution_id", "institution_id"),
        Index("ix_student_enrollments_status", "status"),
    )


class CourseEnrollment(BaseModel):
    """Links a student User to a Subject (course) for a Semester.

    institution_id is denormalised from the student's User.institution_id.

    Unique constraint prevents a student from enrolling in the same
    course-semester combination twice.
    """
    __tablename__ = "course_enrollments"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    grade: Mapped[str | None] = mapped_column(String(5), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "student_id", "course_id", "semester_id",
            name="uq_course_enrollments_student_course_semester"
        ),
        Index("ix_course_enrollments_student_id", "student_id"),
        Index("ix_course_enrollments_institution_id", "institution_id"),
    )


class InstructorAssignment(BaseModel):
    """Links a faculty User to a Subject (course) for a Semester.

    institution_id is denormalised from the instructor's User.institution_id.

    Unique constraint prevents a faculty member from being assigned to the
    same course-semester combination twice.
    """
    __tablename__ = "instructor_assignments"

    instructor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "instructor_id", "course_id", "semester_id",
            name="uq_instructor_assignments_instructor_course_semester"
        ),
        Index("ix_instructor_assignments_instructor_id", "instructor_id"),
        Index("ix_instructor_assignments_institution_id", "institution_id"),
    )
