from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.notification_service import NotificationService
from app.middleware.auth import require_auth

notifications_bp = Blueprint('notifications', __name__)
notification_service = NotificationService()

@notifications_bp.route('/', methods=['GET'])
@require_auth
def get_notifications():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    notifications, total = notification_service.get_user_notifications(request.user.id, page, limit)
    meta = {"page": page, "limit": limit, "total": total}
    return success_response(data=notifications, meta=meta)

@notifications_bp.route('/read-all', methods=['POST'])
@require_auth
def mark_all_read():
    notification_service.mark_all_as_read(request.user.id)
    return success_response(data=None, message="All notifications marked as read")

@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@require_auth
def mark_read(notification_id):
    notification_service.mark_as_read(notification_id, request.user.id)
    return success_response(data=None, message="Notification marked as read")
