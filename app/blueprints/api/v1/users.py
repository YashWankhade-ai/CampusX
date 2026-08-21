from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.user_service import UserService
from app.schemas.user import UserResponseSchema, UserUpdateSchema
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role, require_permission
from app.schemas.base import ValidationError

users_bp = Blueprint('users', __name__)
user_service = UserService()

@users_bp.route('/me', methods=['GET'])
@require_auth
def get_me():
    user = user_service.get_user_profile(request.user.id)
    if not user:
        return error_response(code="NOT_FOUND", message="User not found", status_code=404)
    return success_response(data=user.to_dict())

@users_bp.route('/me', methods=['PUT'])
@require_auth
def update_me():
    data = request.get_json(silent=True) or {}
    user = user_service.update_user_profile(request.user.id, **{k: v for k, v in data.items() if k in ('full_name', 'display_name', 'avatar_url', 'timezone', 'locale')})
    if not user:
        return error_response(code="NOT_FOUND", message="User not found", status_code=404)
    return success_response(data=user.to_dict(), message="Profile updated")

@users_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    limit = request.args.get('limit', 10, type=int)
    users = user_service.get_leaderboard(limit)
    return success_response(data=UserResponseSchema(many=True).dump(users))

@users_bp.route('/', methods=['GET'])
@require_auth
@require_permission('users:manage')
def list_users():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit
    users = user_service.list_users(limit=limit, offset=offset)
    meta = {"page": page, "limit": limit, "total": len(users)}
    return success_response(data=[u.to_dict() for u in users], meta=meta)

@users_bp.route('/<string:user_id>', methods=['GET'])
@require_auth
def get_user(user_id):
    return error_response(code="NOT_IMPLEMENTED", message="Not implemented", status_code=501)

@users_bp.route('/<string:user_id>', methods=['PUT'])
@require_auth
def update_user(user_id):
    return error_response(code="NOT_IMPLEMENTED", message="Not implemented", status_code=501)

@users_bp.route('/<string:user_id>', methods=['DELETE'])
@require_auth
@require_permission('users:delete')
def delete_user(user_id):
    return error_response(code="NOT_IMPLEMENTED", message="Not implemented", status_code=501)
