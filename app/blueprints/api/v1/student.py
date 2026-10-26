"""Student API Blueprint — Sprint 13.

Self-service endpoints for authenticated STUDENT users.

Endpoints:
    GET  /api/v1/student/profile              → own enriched profile
    GET  /api/v1/student/dashboard            → dashboard aggregate
    GET  /api/v1/student/enrollments/         → own program enrollments
    GET  /api/v1/student/enrollments/courses  → own course enrollments

Security:
    - All routes require @require_auth (401 for unauthenticated)
    - All routes require enrollment:read permission (403 for GUEST)
    - user_id is ALWAYS from request.user.id (JWT) — never from request body/path
    - institution_id is ALWAYS from request.user.institution_id (JWT)
    - No mutation operations — students cannot create/modify/delete enrollments
    - IDOR prevention: all queries are scoped to the authenticated user's own data
    - Sensitive fields never returned — StudentService uses explicit safe serializers

Architecture:
    Blueprint → StudentService → (DB queries on User, Institution, Enrollment,
                                  Notification, Contribution models)
    No new models or migrations required — Sprint 13 is read-only self-service
    on top of the existing Sprint 12 foundation.

Not implemented here (reserved for Faculty module):
    - Instructor assignment access
    - Grade submission
    - Course management
"""
from flask import Blueprint, request

from app.utils.response_utils import success_response, error_response
from app.services.student_service import StudentService
from app.middleware.auth import require_auth
from app.permissions.decorators import require_permission

student_bp = Blueprint('student', __name__)
_svc = StudentService()


# ── Profile ────────────────────────────────────────────────────────────────────

@student_bp.route('/profile', methods=['GET'])
@require_auth
@require_permission('enrollment:read')
def get_student_profile():
    """Return the authenticated student's enriched profile.

    Includes safe institution summary and department name.
    Never exposes password_hash, tokens, OTPs, or other sensitive fields.
    """
    profile = _svc.get_student_profile(student_user_id=str(request.user.id))
    if not profile:
        return error_response(code="NOT_FOUND", message="Student not found", status_code=404)
    return success_response(data=profile)


@student_bp.route('/profile', methods=['PUT'])
@require_auth
@require_permission('enrollment:read')
def update_student_profile():
    """Update editable student profile fields."""
    from app.services.user_service import UserService
    user_svc = UserService()
    data = request.get_json(silent=True) or {}
    allowed = ('full_name', 'display_name', 'avatar_url', 'timezone', 'locale', 'phone', 'bio', 'location')
    updated = user_svc.update_user_profile(
        request.user.id,
        **{k: v for k, v in data.items() if k in allowed}
    )
    if not updated:
        return error_response(code="NOT_FOUND", message="Student not found", status_code=404)
    profile = _svc.get_student_profile(student_user_id=str(request.user.id))
    return success_response(data=profile, message="Profile updated successfully")


# ── Dashboard ──────────────────────────────────────────────────────────────────

@student_bp.route('/dashboard', methods=['GET'])
@require_auth
@require_permission('enrollment:read')
def get_dashboard():
    """Return the authenticated student's dashboard aggregate.

    Includes counts of: program enrollments, course enrollments, unread
    notifications, and contributions. No sensitive data exposed.
    All counts are DB-level aggregations (no N+1 queries).
    """
    dashboard = _svc.get_dashboard(student_user_id=str(request.user.id))
    if not dashboard:
        return error_response(code="NOT_FOUND", message="Student not found", status_code=404)
    return success_response(data=dashboard)


# ── Enrollments ────────────────────────────────────────────────────────────────

@student_bp.route('/enrollments/', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('enrollment:read')
def get_my_program_enrollments():
    """Return the authenticated student's program enrollments (own data only).

    IDOR prevention:
        - user_id taken from JWT — cannot view another student's enrollments
        - Data is scoped to StudentEnrollment.user_id == authenticated_user_id
    """
    enrollments = _svc.get_program_enrollments(student_user_id=str(request.user.id))
    return success_response(
        data=enrollments,
        meta={"total": len(enrollments)},
    )


@student_bp.route('/enrollments/courses', methods=['GET'])
@require_auth
@require_permission('enrollment:read')
def get_my_course_enrollments():
    """Return the authenticated student's course enrollments (own data only).

    IDOR prevention:
        - user_id taken from JWT — cannot view another student's course enrollments
        - Data is scoped to CourseEnrollment.student_id == authenticated_user_id
    """
    enrollments = _svc.get_course_enrollments_for_student(student_user_id=str(request.user.id))
    return success_response(
        data=enrollments,
        meta={"total": len(enrollments)},
    )
