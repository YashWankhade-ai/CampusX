"""Faculty API Blueprint — Sprint 14.

Self-service and academic-visibility endpoints for authenticated FACULTY users.

Endpoints:
    GET  /api/v1/faculty/profile                          → own enriched profile
    GET  /api/v1/faculty/dashboard                        → dashboard aggregate
    GET  /api/v1/faculty/courses                          → own assigned courses
    GET  /api/v1/faculty/courses/<course_id>/students     → students in an assigned course
    GET  /api/v1/faculty/resources                        → own uploaded resources

Security:
    - All routes require @require_auth (401 for unauthenticated)
    - All routes require enrollment:read permission (403 for GUEST)
    - user_id ALWAYS from request.user.id (JWT) — never from path or body
    - institution_id ALWAYS from request.user.institution_id (JWT)
    - get_students_in_course() enforces faculty owns the assignment (IDOR)
    - No mutation operations — enrollment create/modify/delete remain admin-only
    - Sensitive fields never returned — FacultyService uses explicit safe serializers

Architecture:
    Blueprint → FacultyService → (DB queries on User, Institution, Enrollment,
                                   InstructorAssignment, StudyMaterial, Notification,
                                   Contribution models)
    No new models or migrations required — Sprint 14 is built on existing foundation.

Not implemented (reserved for other modules):
    - Resource approval decision (moderator)
    - Role or institution change (admin)
    - Creating course assignments (admin)
    - Placement or AI features
"""
import uuid
from flask import Blueprint, request

from app.utils.response_utils import success_response, error_response
from app.services.faculty_service import FacultyService
from app.middleware.auth import require_auth
from app.permissions.decorators import require_permission

faculty_bp = Blueprint('faculty', __name__)
_svc = FacultyService()

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


def _parse_pagination():
    try:
        limit = max(1, min(_MAX_LIMIT, int(request.args.get('limit', _DEFAULT_LIMIT))))
    except (ValueError, TypeError):
        limit = _DEFAULT_LIMIT
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    return page, limit


# ── Profile ────────────────────────────────────────────────────────────────────

@faculty_bp.route('/profile', methods=['GET'])
@require_auth
@require_permission('enrollment:read')
def get_faculty_profile():
    """Return the authenticated faculty member's enriched profile.

    Includes safe institution summary and department name.
    Never exposes password_hash, tokens, OTPs, or storage_path.
    """
    profile = _svc.get_faculty_profile(faculty_user_id=str(request.user.id))
    if not profile:
        return error_response(code="NOT_FOUND", message="Faculty member not found", status_code=404)
    return success_response(data=profile)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@faculty_bp.route('/dashboard', methods=['GET'])
@require_auth
@require_permission('enrollment:read')
def get_dashboard():
    """Return the authenticated faculty member's dashboard aggregate.

    Aggregates: assigned course count, resource counts by status,
    unread notifications, and contributions. DB-level counts only — no N+1.
    No sensitive data exposed.
    """
    dashboard = _svc.get_dashboard(faculty_user_id=str(request.user.id))
    if not dashboard:
        return error_response(code="NOT_FOUND", message="Faculty member not found", status_code=404)
    return success_response(data=dashboard)


# ── Assigned courses ───────────────────────────────────────────────────────────

@faculty_bp.route('/courses', methods=['GET'])
@require_auth
@require_permission('enrollment:read')
def get_assigned_courses():
    """Return courses assigned to the authenticated faculty member.

    IDOR prevention:
        - instructor_id taken from JWT — cannot view another faculty's assignments
        - Scoped to InstructorAssignment.instructor_id == authenticated_user_id
    """
    assignments = _svc.get_instructor_assignments(faculty_user_id=str(request.user.id))
    return success_response(
        data=assignments,
        meta={"total": len(assignments)},
    )


# ── Students in an assigned course ────────────────────────────────────────────

@faculty_bp.route('/courses/<course_id>/students', methods=['GET'])
@require_auth
@require_permission('enrollment:read')
def get_students_in_course(course_id):
    """Return students enrolled in a course assigned to the authenticated faculty.

    Security:
        - Faculty must be assigned to <course_id> in InstructorAssignment.
          If not, returns 404 (IDOR-safe — same response as non-existent course).
        - Returns only: id, full_name, display_name, role, status.
          No email, last_login_at, or sensitive fields.
        - Faculty cannot use this to enumerate students in unassigned courses.
    """
    try:
        uuid.UUID(course_id)
    except (ValueError, TypeError):
        return error_response(code="NOT_FOUND", message="Course not found", status_code=404)

    students, err = _svc.get_students_in_course(
        faculty_user_id=str(request.user.id),
        course_id=course_id,
    )
    if err:
        return error_response(code="NOT_FOUND", message="Course not found", status_code=404)
    return success_response(
        data=students,
        meta={"total": len(students)},
    )


# ── Own resources ──────────────────────────────────────────────────────────────

@faculty_bp.route('/resources', methods=['GET'])
@require_auth
@require_permission('resources:read')
def get_my_resources():
    """Return study materials authored by the authenticated faculty member.

    IDOR prevention:
        - author_id taken from JWT — cannot view another faculty's resources
        - Scoped to StudyMaterial.author_id == authenticated_user_id
    Storage paths are never returned.
    Optional query params: status (PENDING|APPROVED|REJECTED), limit, page.
    """
    page, limit = _parse_pagination()
    offset = (page - 1) * limit
    status_filter = request.args.get('status')

    resources = _svc.get_my_resources(
        faculty_user_id=str(request.user.id),
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return success_response(
        data=resources,
        meta={"page": page, "limit": limit, "total": len(resources)},
    )
