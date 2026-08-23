"""Analytics API — Sprint 10.

Routes:
    GET /api/v1/analytics/me            Personal stats (any authenticated user)
    GET /api/v1/analytics/institution   Institution stats (analytics:read required)

Security:
    - All routes require @require_auth.
    - Institution scope is derived from JWT (request.user.institution_id).
    - Client-supplied institution_id in query params is IGNORED.
    - Students do not have analytics:read and cannot see institution stats.
    - The old /dashboard and /overview routes are preserved for backward
      compat but now correctly use @require_permission.
"""
import logging
from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.analytics_service import AnalyticsService
from app.middleware.auth import require_auth
from app.permissions.rbac import require_permission

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__)
_analytics_service = AnalyticsService()


@analytics_bp.route('/me', methods=['GET'], strict_slashes=False)
@require_auth
def personal_stats():
    """Personal contribution statistics for the requesting user."""
    user_id = str(request.user.id)
    stats = _analytics_service.get_personal_stats(user_id)
    return success_response(data=stats)


@analytics_bp.route('/institution', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('analytics:read')
def institution_stats():
    """Institution-scoped statistics.

    institution_id is derived from JWT — never from query params.
    MODERATOR, FACULTY, INSTITUTION_ADMIN, SUPER_ADMIN have analytics:read.
    STUDENT and GUEST do not.
    """
    institution_id = str(request.user.institution_id) if request.user.institution_id else None
    if not institution_id:
        return error_response(
            code="MISSING_INSTITUTION",
            message="Your account is not associated with an institution.",
            status_code=400
        )
    stats = _analytics_service.get_institution_stats(institution_id)
    return success_response(data=stats)


# ── Legacy routes (backward compat) ────────────────────────────────────────

@analytics_bp.route('/dashboard', methods=['GET'], strict_slashes=False)
@require_auth
def user_dashboard():
    """Legacy alias for /me — kept for backward compatibility."""
    stats = _analytics_service.get_user_dashboard(str(request.user.id))
    return success_response(data=stats)


@analytics_bp.route('/overview', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('analytics:export')
def platform_overview():
    """Platform-wide overview — SUPER_ADMIN and INSTITUTION_ADMIN only."""
    stats = _analytics_service.get_platform_overview()
    return success_response(data=stats)
