"""Admin API Blueprint — Sprint 12.

Endpoints:

Institution Management (institutions:manage or institutions:read):
    GET    /api/v1/admin/institutions/              → list institutions
    POST   /api/v1/admin/institutions/              → create institution (SUPER_ADMIN)
    GET    /api/v1/admin/institutions/<id>          → get institution detail
    PATCH  /api/v1/admin/institutions/<id>          → update institution

User Management (users:manage):
    GET    /api/v1/admin/users/                     → list users (institution-scoped)
    GET    /api/v1/admin/users/<user_id>            → get user detail
    PATCH  /api/v1/admin/users/<user_id>/status     → activate/deactivate/suspend
    PATCH  /api/v1/admin/users/<user_id>/role       → change role

Security:
    - All routes require @require_auth + appropriate @require_permission
    - actor identity ALWAYS from request.user (JWT), never from request body
    - institution_id for scoping ALWAYS from request.user.institution_id (JWT)
    - No client-supplied institution_id override accepted for authorization
"""
from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.admin_service import AdminService
from app.middleware.auth import require_auth
from app.permissions.decorators import require_permission

admin_bp = Blueprint('admin', __name__)
_svc = AdminService()

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


def _parse_pagination():
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = max(1, min(_MAX_LIMIT, int(request.args.get('limit', _DEFAULT_LIMIT))))
    except (ValueError, TypeError):
        limit = _DEFAULT_LIMIT
    return page, limit


# ── Institution endpoints ─────────────────────────────────────────────────────

@admin_bp.route('/institutions/', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('institutions:read')
def list_institutions():
    """List institutions visible to the current actor."""
    items = _svc.list_institutions(
        actor_role=request.user.role,
        actor_institution_id=str(request.user.institution_id) if request.user.institution_id else None,
    )
    return success_response(data=items, meta={"total": len(items)})


@admin_bp.route('/institutions/', methods=['POST'], strict_slashes=False)
@require_auth
@require_permission('institutions:manage')
def create_institution():
    """Create a new institution. SUPER_ADMIN only."""
    data = request.get_json(silent=True) or {}
    result, err = _svc.create_institution(data=data, actor_role=request.user.role)
    if err:
        return error_response(code="BAD_REQUEST", message=err, status_code=400)
    return success_response(data=result, message="Institution created", status_code=201)


@admin_bp.route('/institutions/<institution_id>', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('institutions:read')
def get_institution(institution_id):
    """Get institution detail. INSTITUTION_ADMIN sees only their own."""
    result = _svc.get_institution(
        institution_id=institution_id,
        actor_role=request.user.role,
        actor_institution_id=str(request.user.institution_id) if request.user.institution_id else None,
    )
    if not result:
        return error_response(code="NOT_FOUND", message="Institution not found", status_code=404)
    return success_response(data=result)


@admin_bp.route('/institutions/<institution_id>', methods=['PATCH'], strict_slashes=False)
@require_auth
@require_permission('institutions:manage')
def update_institution(institution_id):
    """Update institution. INSTITUTION_ADMIN can update their own; SUPER_ADMIN any."""
    data = request.get_json(silent=True) or {}
    result, err = _svc.update_institution(
        institution_id=institution_id,
        data=data,
        actor_role=request.user.role,
        actor_institution_id=str(request.user.institution_id) if request.user.institution_id else None,
    )
    if err:
        status = 404 if "not found" in err.lower() else 403 if "denied" in err.lower() else 400
        return error_response(code="ERROR", message=err, status_code=status)
    return success_response(data=result, message="Institution updated")


# ── User Management endpoints ─────────────────────────────────────────────────

@admin_bp.route('/users/', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('users:manage')
def list_users():
    """List users (institution-scoped for non-SUPER_ADMIN)."""
    page, limit = _parse_pagination()
    status_filter = request.args.get('status')
    items, total = _svc.list_users(
        actor_role=request.user.role,
        actor_institution_id=str(request.user.institution_id) if request.user.institution_id else None,
        page=page,
        limit=limit,
        status_filter=status_filter,
    )
    return success_response(data=items, meta={"page": page, "limit": limit, "total": total})


@admin_bp.route('/users/<user_id>', methods=['GET'], strict_slashes=False)
@require_auth
@require_permission('users:read')
def get_user(user_id):
    """Get user detail. Institution-scoped (IDOR prevention server-side)."""
    result = _svc.get_user(
        user_id=user_id,
        actor_role=request.user.role,
        actor_institution_id=str(request.user.institution_id) if request.user.institution_id else None,
    )
    if not result:
        return error_response(code="NOT_FOUND", message="User not found", status_code=404)
    return success_response(data=result)


@admin_bp.route('/users/<user_id>/status', methods=['PATCH'], strict_slashes=False)
@require_auth
@require_permission('users:manage')
def set_user_status(user_id):
    """Activate, deactivate, or suspend a user.

    Body: { "status": "active" | "inactive" | "suspended" }
    Self-deactivation and cross-institution access both prevented server-side.
    """
    data = request.get_json(silent=True) or {}
    new_status = data.get("status", "").strip().lower()
    if not new_status:
        return error_response(code="BAD_REQUEST", message="'status' field required", status_code=400)

    result, err = _svc.set_user_status(
        user_id=user_id,
        new_status=new_status,
        actor_role=request.user.role,
        actor_institution_id=str(request.user.institution_id) if request.user.institution_id else None,
        actor_user_id=str(request.user.id),
    )
    if err:
        status = 404 if "not found" in err.lower() else 400
        return error_response(code="ERROR", message=err, status_code=status)
    return success_response(data=result, message="User status updated")


@admin_bp.route('/users/<user_id>/role', methods=['PATCH'], strict_slashes=False)
@require_auth
@require_permission('users:manage')
def change_user_role(user_id):
    """Change a user's role.

    Body: { "role": "STUDENT" | "FACULTY" | "MODERATOR" | "INSTITUTION_ADMIN" }
    Privilege escalation prevention enforced server-side.
    Self-promotion rejected. Cross-institution rejected.
    """
    data = request.get_json(silent=True) or {}
    new_role = data.get("role", "").strip().upper()
    if not new_role:
        return error_response(code="BAD_REQUEST", message="'role' field required", status_code=400)

    result, err = _svc.change_user_role(
        user_id=user_id,
        new_role=new_role,
        actor_role=request.user.role,
        actor_institution_id=str(request.user.institution_id) if request.user.institution_id else None,
        actor_user_id=str(request.user.id),
    )
    if err:
        status = 404 if "not found" in err.lower() else 403 if "privilege" in err.lower() or "cannot" in err.lower() else 400
        return error_response(code="ERROR", message=err, status_code=status)
    return success_response(data=result, message="User role updated")
