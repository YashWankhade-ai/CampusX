"""Notifications API blueprint — Sprint 11.

Routes (all require @require_auth — user_id from JWT only):

    GET  /api/v1/notifications/           → paginated notification list
    GET  /api/v1/notifications/unread     → unread notifications only
    GET  /api/v1/notifications/count      → unread count (lightweight poll)
    POST /api/v1/notifications/<id>/read  → mark single notification read
    POST /api/v1/notifications/read-all   → mark all notifications read

Security:
    - recipient_id is always taken from request.user.id (JWT), never from request body
    - mark_read enforces ownership in the repository layer (IDOR prevention)
    - pagination limit is enforced server-side (max 100)
    - Unauthenticated requests are rejected by @require_auth (401)
"""
import uuid
from flask import Blueprint, request

from app.utils.response_utils import success_response, error_response
from app.services.notification_service import NotificationService
from app.middleware.auth import require_auth

notifications_bp = Blueprint('notifications', __name__)
_service = NotificationService()

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


def _parse_pagination():
    """Parse and validate page/limit from query params."""
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = max(1, min(_MAX_LIMIT, int(request.args.get('limit', _DEFAULT_LIMIT))))
    except (ValueError, TypeError):
        limit = _DEFAULT_LIMIT
    return page, limit


@notifications_bp.route('/', methods=['GET'], strict_slashes=False)
@require_auth
def get_notifications():
    """Return the authenticated user's paginated notifications (newest first)."""
    recipient_id = str(request.user.id)
    page, limit = _parse_pagination()
    items, total = _service.get_notifications(recipient_id, unread_only=False, page=page, limit=limit)
    return success_response(
        data=items,
        meta={"page": page, "limit": limit, "total": total},
    )


@notifications_bp.route('/unread', methods=['GET'], strict_slashes=False)
@require_auth
def get_unread_notifications():
    """Return only unread notifications for the authenticated user."""
    recipient_id = str(request.user.id)
    page, limit = _parse_pagination()
    items, total = _service.get_notifications(recipient_id, unread_only=True, page=page, limit=limit)
    return success_response(
        data=items,
        meta={"page": page, "limit": limit, "total": total},
    )


@notifications_bp.route('/count', methods=['GET'], strict_slashes=False)
@require_auth
def get_unread_count():
    """Return unread notification count. Lightweight — suitable for badge polling."""
    recipient_id = str(request.user.id)
    count = _service.get_unread_count(recipient_id)
    return success_response(data={"unread_count": count})


@notifications_bp.route('/<notification_id>/read', methods=['POST'], strict_slashes=False)
@require_auth
def mark_notification_read(notification_id):
    """Mark a single notification as read.

    Enforces ownership: the notification must belong to the authenticated user.
    Returns 404 if not found or not owned (prevents IDOR).
    """
    # Validate UUID format before hitting the DB
    try:
        uuid.UUID(notification_id)
    except (ValueError, TypeError):
        return error_response(code="NOT_FOUND", message="Notification not found", status_code=404)

    recipient_id = str(request.user.id)
    updated = _service.mark_read(notification_id=notification_id, recipient_id=recipient_id)
    if not updated:
        return error_response(code="NOT_FOUND", message="Notification not found", status_code=404)
    return success_response(data=None, message="Notification marked as read")


@notifications_bp.route('/read-all', methods=['POST'], strict_slashes=False)
@require_auth
def mark_all_read():
    """Mark all of the authenticated user's unread notifications as read."""
    recipient_id = str(request.user.id)
    count = _service.mark_all_read(recipient_id)
    return success_response(data={"marked_read": count}, message="All notifications marked as read")
