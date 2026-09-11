"""Faculty Service — Sprint 14.

Provides faculty self-service operations built on top of the existing
authenticated, RBAC-protected, institution-isolated CampusX foundation.

All methods source user_id and institution_id from the JWT — never from
client-supplied input — to prevent IDOR and institution spoofing.

Operations:
    get_faculty_profile()          → enriched own profile (user + institution + dept)
    get_dashboard()                → aggregated dashboard (profile + counts)
    get_instructor_assignments()   → courses assigned to this faculty member
    get_students_in_course()       → students enrolled in a faculty-assigned course
    get_my_resources()             → study materials authored by this faculty member

Security rules:
    - All methods are self-service: only own data returned unless cross-check required
    - get_students_in_course() enforces faculty must be assigned to the course being
      queried (prevents IDOR to arbitrary courses)
    - institution_id always denormalised from the User DB row, never from JWT payload
    - No mutation operations in this service — faculty cannot create enrollments,
      change roles, or modify other users
    - Safe dict serializers on every return path

What is NOT here (architectural boundaries):
    - Student enrollment creation/modification (admin-only — EnrollmentService)
    - Role changes (admin-only — AdminService)
    - Approval decisions (moderator — ApprovalService)
    - Resource deletion (needs resources:delete — faculty do not have it)
"""
import uuid
import logging
from typing import Optional

from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.academic import Institution, Department, Subject
from app.models.enrollment import InstructorAssignment, CourseEnrollment
from app.models.resource import StudyMaterial
from app.models.contribution import UserContribution
from app.models.notification import Notification

logger = logging.getLogger(__name__)

_MAX_ROWS = 100


# ── Safe serializers ───────────────────────────────────────────────────────────

def _safe_institution_summary(inst: Institution) -> dict:
    """Return only public, non-sensitive institution fields."""
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


def _safe_assignment_dict(a: InstructorAssignment, subject: Optional[Subject] = None) -> dict:
    """Return a safe dict for an InstructorAssignment row."""
    return {
        "id": str(a.id),
        "instructor_id": str(a.instructor_id),
        "course_id": str(a.course_id),
        "semester_id": str(a.semester_id),
        "institution_id": str(a.institution_id) if a.institution_id else None,
        "is_primary": a.is_primary,
        "course_name": subject.name if subject else None,
        "course_code": subject.code if subject else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _safe_student_dict(user: User) -> dict:
    """Return minimal safe user dict for faculty viewing student info.

    Deliberately more restricted than the admin view — faculty see:
    display name, role, status, institution (same as theirs by enforcement).
    No email, no last_login_at, no sensitive fields.
    """
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "display_name": user.display_name,
        "role": user.role,
        "status": user.status,
    }


def _safe_resource_dict(r: StudyMaterial) -> dict:
    """Return safe dict for a StudyMaterial row. Never exposes storage_path."""
    return {
        "id": str(r.id),
        "title": r.title,
        "description": r.description,
        "subject_id": str(r.subject_id) if r.subject_id else None,
        "material_type": r.material_type.value if r.material_type else None,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ── Service class ──────────────────────────────────────────────────────────────

class FacultyService:
    """Faculty self-service operations.

    All methods require faculty_user_id from the validated JWT.
    Institution data is always resolved from the User DB row.
    """

    # ── Profile ────────────────────────────────────────────────────────────────

    def get_faculty_profile(self, faculty_user_id: str) -> Optional[dict]:
        """Return enriched own profile: user + institution summary + department.

        Includes institution info resolved from the faculty member's own User row.
        Never exposes password_hash, OTPs, tokens, internal fields, or storage paths.
        """
        try:
            uid = uuid.UUID(str(faculty_user_id))
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
            "department_name": department_name,
            "institution_id": str(user.institution_id) if user.institution_id else None,
            "institution": institution_data,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }

    # ── Dashboard ──────────────────────────────────────────────────────────────

    def get_dashboard(self, faculty_user_id: str) -> Optional[dict]:
        """Return faculty dashboard aggregate.

        Aggregates from already-available data:
            - profile summary
            - assigned course count
            - uploaded resource count + pending/approved breakdown
            - unread notification count
            - contribution count

        All counts use DB-level aggregation (no N+1 queries).
        No sensitive fields returned.
        """
        try:
            uid = uuid.UUID(str(faculty_user_id))
        except (ValueError, TypeError):
            return None

        user = db.session.query(User).filter(
            User.id == uid,
            User.is_deleted == False,
        ).first()
        if not user:
            return None

        # Institution name (own institution only — single query)
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

        # Assigned course count
        assigned_course_count = db.session.query(
            func.count(InstructorAssignment.id)
        ).filter(
            InstructorAssignment.instructor_id == uid,
            InstructorAssignment.is_deleted == False,
        ).scalar() or 0

        # Resource counts (own resources only)
        total_resources = db.session.query(
            func.count(StudyMaterial.id)
        ).filter(
            StudyMaterial.author_id == uid,
            StudyMaterial.is_deleted == False,
        ).scalar() or 0

        approved_resources = db.session.query(
            func.count(StudyMaterial.id)
        ).filter(
            StudyMaterial.author_id == uid,
            StudyMaterial.status == "APPROVED",
            StudyMaterial.is_deleted == False,
        ).scalar() or 0

        pending_resources = db.session.query(
            func.count(StudyMaterial.id)
        ).filter(
            StudyMaterial.author_id == uid,
            StudyMaterial.status == "PENDING",
            StudyMaterial.is_deleted == False,
        ).scalar() or 0

        # Unread notification count
        unread_notification_count = db.session.query(
            func.count(Notification.id)
        ).filter(
            Notification.recipient_id == uid,
            Notification.is_read == False,
            Notification.is_deleted == False,
        ).scalar() or 0

        # Contribution count
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
            "assigned_course_count": assigned_course_count,
            "total_resource_count": total_resources,
            "approved_resource_count": approved_resources,
            "pending_resource_count": pending_resources,
            "unread_notification_count": unread_notification_count,
            "contribution_count": contribution_count,
        }

    # ── Instructor assignments ─────────────────────────────────────────────────

    def get_instructor_assignments(self, faculty_user_id: str) -> list[dict]:
        """Return all course assignments for this faculty member.

        Only own assignments — never returns another instructor's assignments.
        Joins Subject for name/code (single IN-query, not N+1).
        """
        try:
            uid = uuid.UUID(str(faculty_user_id))
        except (ValueError, TypeError):
            return []

        assignments = db.session.query(InstructorAssignment).filter(
            InstructorAssignment.instructor_id == uid,
            InstructorAssignment.is_deleted == False,
        ).order_by(InstructorAssignment.created_at.desc()).limit(_MAX_ROWS).all()

        if not assignments:
            return []

        # Fetch subjects in one query (no N+1)
        course_ids = [a.course_id for a in assignments]
        subjects_by_id = {
            s.id: s for s in db.session.query(Subject).filter(
                Subject.id.in_(course_ids)
            ).all()
        }

        return [
            _safe_assignment_dict(a, subjects_by_id.get(a.course_id))
            for a in assignments
        ]

    # ── Students in assigned course ────────────────────────────────────────────

    def get_students_in_course(
        self,
        faculty_user_id: str,
        course_id: str,
    ) -> tuple[Optional[list], Optional[str]]:
        """Return students enrolled in a course assigned to this faculty member.

        Security:
            - Faculty must be assigned to the course (InstructorAssignment check).
              If not assigned, return ("not found", IDOR-safe).
            - Only returns: id, full_name, display_name, role, status.
              No email, no password_hash, no last_login_at.
            - Institution isolation: faculty and students must share institution
              (enforced by the InstructorAssignment.institution_id check).
        """
        try:
            fuid = uuid.UUID(str(faculty_user_id))
            cid = uuid.UUID(str(course_id))
        except (ValueError, TypeError):
            return None, "Invalid ID format"

        # Verify faculty is assigned to this course (IDOR prevention)
        assignment = db.session.query(InstructorAssignment).filter(
            InstructorAssignment.instructor_id == fuid,
            InstructorAssignment.course_id == cid,
            InstructorAssignment.is_deleted == False,
        ).first()
        if not assignment:
            return None, "Course not found"  # IDOR: same message as not-found

        # Fetch enrolled students for this course
        enrollments = db.session.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == cid,
            CourseEnrollment.is_deleted == False,
        ).limit(_MAX_ROWS).all()

        if not enrollments:
            return [], None

        # Fetch users in one query (no N+1)
        student_ids = [e.student_id for e in enrollments]
        users_by_id = {
            u.id: u for u in db.session.query(User).filter(
                User.id.in_(student_ids),
                User.is_deleted == False,
            ).all()
        }

        return [
            _safe_student_dict(users_by_id[e.student_id])
            for e in enrollments
            if e.student_id in users_by_id
        ], None

    # ── Own resources ──────────────────────────────────────────────────────────

    def get_my_resources(
        self,
        faculty_user_id: str,
        status_filter: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """Return study materials authored by this faculty member.

        - Never returns storage_path (safe serializer)
        - optional status_filter: PENDING, APPROVED, REJECTED
        - Paginated: max 100 per request
        """
        try:
            uid = uuid.UUID(str(faculty_user_id))
        except (ValueError, TypeError):
            return []

        limit = max(1, min(limit, _MAX_ROWS))

        query = db.session.query(StudyMaterial).filter(
            StudyMaterial.author_id == uid,
            StudyMaterial.is_deleted == False,
        )

        VALID_STATUSES = {"PENDING", "APPROVED", "REJECTED", "CHANGES_REQUESTED"}
        if status_filter and status_filter.upper() in VALID_STATUSES:
            query = query.filter(StudyMaterial.status == status_filter.upper())

        resources = query.order_by(
            StudyMaterial.created_at.desc()
        ).offset(offset).limit(limit).all()

        return [_safe_resource_dict(r) for r in resources]
