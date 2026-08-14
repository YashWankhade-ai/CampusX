from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.user_service import UserService
from app.schemas.user import UserResponseSchema, UserUpdateSchema
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role
from app.schemas.base import ValidationError

users_bp = Blueprint('users', __name__)
user_service = UserService()

@users_bp.route('/me', methods=['GET'])
@require_auth
def get_me():
    user = user_service.get_by_id(request.user.id)
    return success_response(data=UserResponseSchema().dump(user))

@users_bp.route('/me', methods=['PUT'])
@require_auth
def update_me():
    try:
        data = UserUpdateSchema().load(request.json)
        user = user_service.update_profile(request.user.id, data)
        return success_response(data=UserResponseSchema().dump(user), message="Profile updated")
    except ValidationError as e:
        return error_response(code="VALIDATION_ERROR", message=e.messages, status_code=400)

@users_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    limit = request.args.get('limit', 10, type=int)
    users = user_service.get_leaderboard(limit)
    return success_response(data=UserResponseSchema(many=True).dump(users))

@users_bp.route('/', methods=['GET'])
@require_auth
@require_role(['admin'])
def list_users():
    role = request.args.get('role')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    users, total = user_service.list_users(role, page, limit)
    meta = {"page": page, "limit": limit, "total": total}
    return success_response(data=UserResponseSchema(many=True).dump(users), meta=meta)
