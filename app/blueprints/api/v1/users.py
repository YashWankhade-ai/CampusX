"""Users API Blueprint — Sprint 12 hardening.

Endpoints:
    GET    /api/v1/users/me            → own profile (authenticated)
    PUT    /api/v1/users/me            → update own profile (authenticated)
    GET    /api/v1/users/leaderboard   → institution-scoped leaderboard (authenticated)
    GET    /api/v1/users/              → list users (users:manage, institution-scoped)
    GET    /api/v1/users/<user_id>     → user detail (authenticated, IDOR-safe)

Removed 501 stubs:
    PUT    /api/v1/users/<user_id>     → REMOVED (admin-only; lives in /admin/users/<id>/role)
    DELETE /api/v1/users/<user_id>     → REMOVED (admin-only; lives in /admin/users/<id>/status)

Security:
    - All routes require @require_auth
    - institution_id ALWAYS from request.user (JWT), never from request body or query param
    - get_user_by_id enforces institution isolation server-side (IDOR prevention)
    - leaderboard requires auth and is institution-scoped
    - list_users requires users:manage and is institution-scoped
    - No raw ORM objects ever returned — all responses via UserService safe dict
"""
from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.user_service import UserService
from app.middleware.auth import require_auth
from app.permissions.decorators import require_permission

users_bp = Blueprint('users', __name__)
_svc = UserService()

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


# ── Own profile ────────────────────────────────────────────────────────────────

@users_bp.route('/me', methods=['GET'])
@require_auth
def get_me():
    """Return the authenticated user's own profile."""
    profile = _svc.get_user_profile(request.user.id)
    if not profile:
        return error_response(code="NOT_FOUND", message="User not found", status_code=404)
    return success_response(data=profile)


@users_bp.route('/me', methods=['PUT'])
@require_auth
def update_me():
    """Update the authenticated user's own profile.

    Accepted fields: full_name, display_name, avatar_url, timezone, locale, phone, bio, location.
    All other fields silently ignored.
    """
    data = request.get_json(silent=True) or {}
    allowed = ('full_name', 'display_name', 'avatar_url', 'timezone', 'locale', 'phone', 'bio', 'location')
    profile = _svc.update_user_profile(
        request.user.id,
        **{k: v for k, v in data.items() if k in allowed}
    )
    if not profile:
        return error_response(code="NOT_FOUND", message="User not found", status_code=404)
    return success_response(data=profile, message="Profile updated")


# ── Leaderboard ────────────────────────────────────────────────────────────────

@users_bp.route('/leaderboard', methods=['GET'])
@require_auth
def get_leaderboard():
    """Return institution-scoped contribution leaderboard.

    Requires authentication. institution_id is always from the JWT — never
    accepted from query params to prevent cross-institution data access.
    Limit is capped at 50.
    """
    try:
        limit = max(1, min(50, int(request.args.get('limit', 10))))
    except (ValueError, TypeError):
        limit = 10

    actor_institution_id = (
        str(request.user.institution_id) if request.user.institution_id else None
    )
    ranking = _svc.get_leaderboard(
        actor_institution_id=actor_institution_id,
        limit=limit,
    )
    return success_response(data=ranking, meta={"institution_scoped": True, "limit": limit})


# ── User list (admin-facing, institution-scoped) ───────────────────────────────

@users_bp.route('/', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('users:manage')
def list_users():
    """List users. Institution-scoped — SUPER_ADMIN sees all.

    Note: Full admin functionality (pagination by total, status filter) lives
    in /api/v1/admin/users/. This endpoint is the lighter version for internal
    users:manage consumers.
    """
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = max(1, min(_MAX_LIMIT, int(request.args.get('limit', _DEFAULT_LIMIT))))
    except (ValueError, TypeError):
        limit = _DEFAULT_LIMIT
    offset = (page - 1) * limit

    actor_institution_id = (
        str(request.user.institution_id) if request.user.institution_id else None
    )
    users = _svc.list_users(
        actor_role=request.user.role,
        actor_institution_id=actor_institution_id,
        limit=limit,
        offset=offset,
    )
    return success_response(data=users, meta={"page": page, "limit": limit, "total": len(users)})


# ── User detail (IDOR-safe) ────────────────────────────────────────────────────

@users_bp.route('/<string:user_id>', methods=['GET'])
@require_auth
def get_user(user_id):
    """Return a user's profile.

    Any authenticated user can look up another user's public profile IF they
    share the same institution. SUPER_ADMIN can look up any user.

    IDOR prevention:
        - Institution check is server-side (from JWT, never from client)
        - Cross-institution lookup returns 404 (not 403) to prevent enumeration
        - Response never includes password_hash, tokens, OTPs, or secrets
    """
    actor_institution_id = (
        str(request.user.institution_id) if request.user.institution_id else None
    )
    profile = _svc.get_user_by_id(
        user_id=user_id,
        actor_role=request.user.role,
        actor_institution_id=actor_institution_id,
    )
    if not profile:
        return error_response(code="NOT_FOUND", message="User not found", status_code=404)
    return success_response(data=profile)

# NOTE: PUT /users/<id> (admin update) → use PATCH /api/v1/admin/users/<id>/role
# NOTE: DELETE /users/<id> (admin deactivate) → use PATCH /api/v1/admin/users/<id>/status
# Both 501 stubs have been removed. Admin operations live exclusively in the admin blueprint.
