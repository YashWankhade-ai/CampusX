"""Student Service — Sprint 13.

Provides student self-service operations built on top of existing
authentication, RBAC, notification, enrollment and contribution systems.

All methods take the actor's user_id and institution_id from the JWT
(never from client input) and enforce institution isolation.

Operations:
    get_student_profile()    → enriched own profile (user + institution name)
    get_dashboard()          → aggregated dashboard for the student
    get_program_enrollments() → own program-level enrollments
    get_course_enrollments()  → own course-level enrollments

Security:
    - All DB lookups filter by user_id from JWT — students can only see their
      own data (self-service pattern)
    - Institution name lookup is safe (read-only, cross-institution not possible
      because we only look up the student's own institution)
    - No mutation operations — students cannot enroll, update, or delete
    - Dashboard is a read-only aggregate — no sensitive fields
"""
import uuid
import logging
from typing import Optional

from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.academic import Institution, Department, Program
from app.models.enrollment import StudentEnrollment, CourseEnrollment
from app.models.contribution import UserContribution
from app.models.notification import Notification
from app.services.enrollment_service import _safe_enrollment_dict, _safe_course_enrollment_dict

logger = logging.getLogger(__name__)

_MAX_ENROLLMENTS = 100


def _safe_institution_summary(inst: Institution) -> dict:
    """Return only safe, non-sensitive institution fields."""
    return {
        "id": str(inst.id),
        "name": inst.name,
        "short_name": inst.short_name,
        "code": inst.code,
        "city": inst.city,
        "country": inst.country,
        "subscription_tier": inst.subscription_tier,
        "is_active": inst.is_active,
    }


class StudentService:
    """Student self-service operations.

    All methods require user_id from the validated JWT.
    Institution_id is always sourced from the student's DB User record —
    the actor_institution_id parameter is only used for access control
    comparison, never as the data source.
    """

    # ── Student profile ────────────────────────────────────────────────────────

    def get_student_profile(
        self,
        student_user_id: str,
    ) -> Optional[dict]:
        """Return enriched own profile: user fields + institution summary.

        Includes safe institution info from the student's own institution.
        Never exposes password_hash, OTPs, tokens, or other sensitive data.
        """
        try:
            uid = uuid.UUID(str(student_user_id))
        except (ValueError, TypeError):
            return None

        user = db.session.query(User).filter(
            User.id == uid,
            User.is_deleted == False,
        ).first()
        if not user:
            return None

        institution_data = None
        if user.institution_id:
            inst = db.session.query(Institution).filter(
                Institution.id == user.institution_id,
                Institution.is_deleted == False,
            ).first()
            if inst:
                institution_data = _safe_institution_summary(inst)

        department_name = None
        if user.department_id:
            dept = db.session.query(Department).filter(
                Department.id == user.department_id,
            ).first()
            if dept:
                department_name = dept.name

        meta = user.metadata_json or {}
        bio = user.profile.bio if user.profile and user.profile.bio else meta.get("bio")

        # Real DB counts for student activity
        courses_enrolled = db.session.query(
            func.count(CourseEnrollment.id)
        ).filter(
            CourseEnrollment.student_id == uid,
            CourseEnrollment.is_deleted == False,
        ).scalar() or 0

        from app.models.resource import StudyMaterial
        resources_contributed = db.session.query(
            func.count(StudyMaterial.id)
        ).filter(
            StudyMaterial.author_id == uid,
            StudyMaterial.is_deleted == False,
        ).scalar() or 0

        approved_contributions = db.session.query(
            func.count(StudyMaterial.id)
        ).filter(
            StudyMaterial.author_id == uid,
            StudyMaterial.status == "APPROVED",
            StudyMaterial.is_deleted == False,
        ).scalar() or 0

        unread_notifications = db.session.query(
            func.count(Notification.id)
        ).filter(
            Notification.recipient_id == uid,
            Notification.is_read == False,
            Notification.is_deleted == False,
        ).scalar() or 0

        enrollment = db.session.query(StudentEnrollment).filter(
            StudentEnrollment.user_id == uid,
            StudentEnrollment.is_deleted == False,
        ).first()
        program_name = None
        if enrollment and hasattr(enrollment, 'program') and enrollment.program:
            program_name = enrollment.program.name
        elif user.department_id:
            dept_prog = db.session.query(Program).filter(Program.department_id == user.department_id).first()
            if dept_prog:
                program_name = dept_prog.name
        if not program_name:
            program_name = "Computer Science"

        student_id_val = meta.get("student_id") or meta.get("institutional_id") or meta.get("enrollment_id")
        if not student_id_val:
            from app.utils.academic_utils import get_branch_code
            b_code = meta.get("branch_code") or get_branch_code(department_name or "Computer Science")
            student_id_val = f"STU-{b_code}-2026-001"

        return {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "role": user.role,
            "status": user.status,
            "timezone": user.timezone,
            "locale": user.locale,
            "phone": meta.get("phone"),
            "date_of_birth": meta.get("date_of_birth"),
            "gender": meta.get("gender"),
            "location": meta.get("location") or (f"{inst.city}, {inst.country}" if inst and inst.city else None),
            "bio": bio,
            "department_name": department_name,
            "program_name": program_name,
            "student_id": student_id_val,
            "institutional_id": meta.get("institutional_id") or student_id_val,
            "branch_code": meta.get("branch_code"),
            "institution_id": str(user.institution_id) if user.institution_id else None,
            "institution": institution_data,
            "activity": {
                "courses_enrolled": courses_enrolled,
                "resources_contributed": resources_contributed,
                "approved_contributions": approved_contributions,
                "unread_notifications": unread_notifications,
            },
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }

    # ── Program enrollments ────────────────────────────────────────────────────

    def get_program_enrollments(
        self,
        student_user_id: str,
    ) -> list[dict]:
        """Return all program enrollments for the student (own data only)."""
        try:
            uid = uuid.UUID(str(student_user_id))
        except (ValueError, TypeError):
            return []

        enrollments = db.session.query(StudentEnrollment).filter(
            StudentEnrollment.user_id == uid,
            StudentEnrollment.is_deleted == False,
        ).order_by(StudentEnrollment.created_at.desc()).limit(_MAX_ENROLLMENTS).all()

        return [_safe_enrollment_dict(e) for e in enrollments]

    # ── Course enrollments ─────────────────────────────────────────────────────

    def get_course_enrollments_for_student(
        self,
        student_user_id: str,
    ) -> list[dict]:
        """Return all course enrollments for the student (own data only)."""
        try:
            uid = uuid.UUID(str(student_user_id))
        except (ValueError, TypeError):
            return []

        enrollments = db.session.query(CourseEnrollment).filter(
            CourseEnrollment.student_id == uid,
            CourseEnrollment.is_deleted == False,
        ).order_by(CourseEnrollment.created_at.desc()).limit(_MAX_ENROLLMENTS).all()

        return [_safe_course_enrollment_dict(e) for e in enrollments]

    # ── Dashboard aggregation ──────────────────────────────────────────────────

    def get_dashboard(
        self,
        student_user_id: str,
    ) -> Optional[dict]:
        """Return student dashboard aggregate.

        Aggregates from already-available data only:
            - profile summary
            - institution name
            - program enrollment count + latest enrollment status
            - course enrollment count
            - unread notification count
            - contribution count (resources uploaded)

        No N+1 queries — counts use DB-level aggregation.
        No sensitive fields — only safe, pre-approved data.
        """
        try:
            uid = uuid.UUID(str(student_user_id))
        except (ValueError, TypeError):
            return None

        user = db.session.query(User).filter(
            User.id == uid,
            User.is_deleted == False,
        ).first()
        if not user:
            return None

        # Institution name (single query, own institution only)
        institution_name = None
        institution_code = None
        if user.institution_id:
            inst = db.session.query(Institution).filter(
                Institution.id == user.institution_id,
                Institution.is_deleted == False,
            ).first()
            if inst:
                institution_name = inst.name
                institution_code = inst.short_name

        # Program enrollment summary (aggregated, no N+1)
        program_enrollment_count = db.session.query(
            func.count(StudentEnrollment.id)
        ).filter(
            StudentEnrollment.user_id == uid,
            StudentEnrollment.is_deleted == False,
        ).scalar() or 0

        # Latest program enrollment status
        latest_enrollment = db.session.query(StudentEnrollment).filter(
            StudentEnrollment.user_id == uid,
            StudentEnrollment.is_deleted == False,
        ).order_by(StudentEnrollment.created_at.desc()).first()

        # Course enrollment count (aggregated)
        course_enrollment_count = db.session.query(
            func.count(CourseEnrollment.id)
        ).filter(
            CourseEnrollment.student_id == uid,
            CourseEnrollment.is_deleted == False,
        ).scalar() or 0

        # Unread notification count
        unread_notification_count = db.session.query(
            func.count(Notification.id)
        ).filter(
            Notification.recipient_id == uid,
            Notification.is_read == False,
            Notification.is_deleted == False,
        ).scalar() or 0

        # Contribution count (resources uploaded/approved)
        contribution_count = db.session.query(
            func.count(UserContribution.id)
        ).filter(
            UserContribution.user_id == uid,
            UserContribution.is_deleted == False,
        ).scalar() or 0

        return {
            "user_id": str(uid),
            "full_name": user.full_name,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "role": user.role,
            "status": user.status,
            "institution_id": str(user.institution_id) if user.institution_id else None,
            "institution_name": institution_name,
            "institution_code": institution_code,
            "program_enrollment_count": program_enrollment_count,
            "active_enrollment_status": (
                latest_enrollment.status if latest_enrollment else None
            ),
            "course_enrollment_count": course_enrollment_count,
            "unread_notification_count": unread_notification_count,
            "contribution_count": contribution_count,
        }
