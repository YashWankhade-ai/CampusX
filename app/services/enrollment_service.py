"""Enrollment Service — Sprint 12 Foundation.

Provides the minimum backend foundation for enrollment operations.
Does NOT implement Student or Faculty modules.

Operations:
    enroll_student()             → enroll a student in a program/year
    enroll_student_in_course()   → enroll a student in a course/semester
    assign_instructor()          → assign a faculty to a course/semester
    get_student_enrollments()    → list a student's enrollments (institution-scoped)

Security rules:
    - institution_id always denormalised from the student/instructor's User row
      (never from client input — prevents institution spoofing)
    - Duplicate enrollment is caught at DB UniqueConstraint level; service
      also checks explicitly to return a clean error message
    - All queries include institution_id filter to enforce tenant isolation
"""
import uuid
import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user import User
from app.models.enrollment import StudentEnrollment, CourseEnrollment, InstructorAssignment, AcademicYear
from app.permissions.roles import Role

logger = logging.getLogger(__name__)


def _safe_enrollment_dict(e: StudentEnrollment) -> dict:
    return {
        "id": str(e.id),
        "user_id": str(e.user_id),
        "program_id": str(e.program_id),
        "academic_year_id": str(e.academic_year_id),
        "institution_id": str(e.institution_id) if e.institution_id else None,
        "status": e.status,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _safe_course_enrollment_dict(e: CourseEnrollment) -> dict:
    return {
        "id": str(e.id),
        "student_id": str(e.student_id),
        "course_id": str(e.course_id),
        "semester_id": str(e.semester_id),
        "institution_id": str(e.institution_id) if e.institution_id else None,
        "grade": e.grade,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _resolve_user_institution(user_id: str) -> Optional[uuid.UUID]:
    """Look up a user's institution_id from the DB — never trust caller input."""
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None
    user = db.session.query(User).filter(
        User.id == uid,
        User.is_deleted == False,
    ).first()
    return user.institution_id if user else None


class EnrollmentService:
    # ── Student → Program enrollment ──────────────────────────────────────────

    def enroll_student(
        self,
        student_id: str,
        program_id: str,
        academic_year_id: str,
        actor_role: str,
        actor_institution_id: Optional[str],
    ) -> tuple[Optional[dict], Optional[str]]:
        """Enroll a student in a program for an academic year.

        institution_id is resolved from the student's User record — never from
        caller. Actor must be in the same institution as the student (or SUPER_ADMIN).
        """
        # Resolve institution from DB
        student_institution_id = _resolve_user_institution(student_id)
        if student_institution_id is None:
            return None, "Student not found"

        # Institution isolation
        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id:
                return None, "Access denied"
            if str(student_institution_id) != str(actor_institution_id):
                return None, "Student not found"  # IDOR

        # Duplicate check
        try:
            sid = uuid.UUID(student_id)
            pid = uuid.UUID(program_id)
            ayid = uuid.UUID(academic_year_id)
        except (ValueError, TypeError):
            return None, "Invalid ID format"

        existing = db.session.query(StudentEnrollment).filter(
            StudentEnrollment.user_id == sid,
            StudentEnrollment.program_id == pid,
            StudentEnrollment.academic_year_id == ayid,
            StudentEnrollment.is_deleted == False,
        ).first()
        if existing:
            return None, "Student is already enrolled in this program for this academic year"

        enrollment = StudentEnrollment(
            id=uuid.uuid4(),
            user_id=sid,
            program_id=pid,
            academic_year_id=ayid,
            institution_id=student_institution_id,
            status="active",
        )
        db.session.add(enrollment)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return None, "Duplicate enrollment — already enrolled"
        except Exception as e:
            db.session.rollback()
            return None, str(e)

        return _safe_enrollment_dict(enrollment), None

    # ── Student → Course enrollment ────────────────────────────────────────────

    def enroll_student_in_course(
        self,
        student_id: str,
        course_id: str,
        semester_id: str,
        actor_role: str,
        actor_institution_id: Optional[str],
    ) -> tuple[Optional[dict], Optional[str]]:
        """Enroll a student in a subject/course for a semester."""
        student_institution_id = _resolve_user_institution(student_id)
        if student_institution_id is None:
            return None, "Student not found"

        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id:
                return None, "Access denied"
            if str(student_institution_id) != str(actor_institution_id):
                return None, "Student not found"  # IDOR

        try:
            sid = uuid.UUID(student_id)
            cid = uuid.UUID(course_id)
            semid = uuid.UUID(semester_id)
        except (ValueError, TypeError):
            return None, "Invalid ID format"

        existing = db.session.query(CourseEnrollment).filter(
            CourseEnrollment.student_id == sid,
            CourseEnrollment.course_id == cid,
            CourseEnrollment.semester_id == semid,
            CourseEnrollment.is_deleted == False,
        ).first()
        if existing:
            return None, "Student is already enrolled in this course for this semester"

        enrollment = CourseEnrollment(
            id=uuid.uuid4(),
            student_id=sid,
            course_id=cid,
            semester_id=semid,
            institution_id=student_institution_id,
        )
        db.session.add(enrollment)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return None, "Duplicate enrollment — already enrolled"
        except Exception as e:
            db.session.rollback()
            return None, str(e)

        return _safe_course_enrollment_dict(enrollment), None

    # ── List student enrollments ────────────────────────────────────────────────

    def get_student_enrollments(
        self,
        student_id: str,
        actor_role: str,
        actor_institution_id: Optional[str],
    ) -> tuple[Optional[list], Optional[str]]:
        """Return a student's program enrollments, institution-scoped."""
        student_institution_id = _resolve_user_institution(student_id)
        if student_institution_id is None:
            return None, "Student not found"

        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id:
                return None, "Access denied"
            if str(student_institution_id) != str(actor_institution_id):
                return None, "Student not found"  # IDOR

        try:
            sid = uuid.UUID(student_id)
        except (ValueError, TypeError):
            return None, "Invalid student ID"

        enrollments = db.session.query(StudentEnrollment).filter(
            StudentEnrollment.user_id == sid,
            StudentEnrollment.is_deleted == False,
        ).order_by(StudentEnrollment.created_at.desc()).all()

        return [_safe_enrollment_dict(e) for e in enrollments], None

    # ── List course enrollments ────────────────────────────────────────────────

    def get_course_enrollments(
        self,
        student_id: str,
        actor_role: str,
        actor_institution_id: Optional[str],
    ) -> tuple[Optional[list], Optional[str]]:
        """Return a student's course/subject enrollments, institution-scoped.

        A student may call this with their own user_id (actor_role=STUDENT,
        actor_institution_id from JWT).
        """
        student_institution_id = _resolve_user_institution(student_id)
        if student_institution_id is None:
            return None, "Student not found"

        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id:
                return None, "Access denied"
            if str(student_institution_id) != str(actor_institution_id):
                return None, "Student not found"  # IDOR

        try:
            sid = uuid.UUID(student_id)
        except (ValueError, TypeError):
            return None, "Invalid student ID"

        enrollments = db.session.query(CourseEnrollment).filter(
            CourseEnrollment.student_id == sid,
            CourseEnrollment.is_deleted == False,
        ).order_by(CourseEnrollment.created_at.desc()).all()

        return [_safe_course_enrollment_dict(e) for e in enrollments], None

    # ── Instructor assignment ──────────────────────────────────────────────────

    def assign_instructor(
        self,
        instructor_id: str,
        course_id: str,
        semester_id: str,
        actor_role: str,
        actor_institution_id: str | None,
        is_primary: bool = True,
    ) -> tuple[dict | None, str | None]:
        """Assign an instructor (faculty) to a course (subject) for a semester.

        Institution integrity enforcement (Hardening 2):
            1. instructor's institution_id is resolved from the User DB row —
               never from caller input.
            2. course's institution is inferred via:
               Subject → Program → Department → Department.institution_id
            3. Both must match each other AND the actor's institution
               (or actor must be SUPER_ADMIN).
            4. Client-supplied institution_id is NEVER used to set the
               InstructorAssignment.institution_id.

        Security:
            - Cross-institution assignment is rejected with an IDOR-safe message.
            - Duplicate assignment is caught and reported cleanly.
        """
        # Validate IDs
        try:
            fuid = uuid.UUID(instructor_id)
            cid = uuid.UUID(course_id)
            semid = uuid.UUID(semester_id)
        except (ValueError, TypeError):
            return None, "Invalid ID format"

        # 1. Resolve instructor's institution from DB
        instructor_institution_id = _resolve_user_institution(instructor_id)
        if instructor_institution_id is None:
            return None, "Instructor not found"

        # 2. Resolve course's institution via Subject → Program → Department
        from app.models.academic import Subject, Program, Department
        subject = db.session.query(Subject).filter(Subject.id == cid).first()
        if not subject:
            return None, "Course (subject) not found"

        program = db.session.query(Program).filter(Program.id == subject.program_id).first()
        if not program:
            return None, "Course program not found"

        department = db.session.query(Department).filter(Department.id == program.department_id).first()
        if not department:
            return None, "Course department not found"

        course_institution_id = department.institution_id

        # 3. Integrity check: instructor and course must share the same institution
        if str(instructor_institution_id) != str(course_institution_id):
            return None, "Instructor not found"  # IDOR-safe: reveals nothing

        # 4. Actor isolation: non-SUPER_ADMIN must be in the same institution
        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id:
                return None, "Access denied"
            if str(instructor_institution_id) != str(actor_institution_id):
                return None, "Instructor not found"  # IDOR-safe

        # 5. Duplicate check
        existing = db.session.query(InstructorAssignment).filter(
            InstructorAssignment.instructor_id == fuid,
            InstructorAssignment.course_id == cid,
            InstructorAssignment.semester_id == semid,
            InstructorAssignment.is_deleted == False,
        ).first()
        if existing:
            return None, "Instructor is already assigned to this course for this semester"

        # 6. Verify instructor has FACULTY role (or higher — MODERATOR+ can also teach)
        instructor_user = db.session.query(User).filter(
            User.id == fuid,
            User.is_deleted == False,
        ).first()
        if not instructor_user:
            return None, "Instructor not found"

        from app.permissions.roles import get_role_level
        if get_role_level(instructor_user.role) < get_role_level(Role.FACULTY):
            return None, "User is not eligible to be assigned as an instructor"

        # 7. Create assignment — institution_id from DB, never from caller
        assignment = InstructorAssignment(
            id=uuid.uuid4(),
            instructor_id=fuid,
            course_id=cid,
            semester_id=semid,
            institution_id=instructor_institution_id,  # always from DB
            is_primary=is_primary,
        )
        db.session.add(assignment)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return None, "Duplicate assignment"
        except Exception as e:
            db.session.rollback()
            return None, str(e)

        return {
            "id": str(assignment.id),
            "instructor_id": str(assignment.instructor_id),
            "course_id": str(assignment.course_id),
            "semester_id": str(assignment.semester_id),
            "institution_id": str(assignment.institution_id) if assignment.institution_id else None,
            "is_primary": assignment.is_primary,
            "created_at": assignment.created_at.isoformat() if assignment.created_at else None,
        }, None
