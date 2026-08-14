from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.approval_service import ApprovalService
from app.middleware.auth import require_auth
from app.permissions.rbac import require_role

approvals_bp = Blueprint('approvals', __name__)
approval_service = ApprovalService()

@approvals_bp.route('/pending', methods=['GET'])
@require_auth
@require_role(['admin', 'moderator'])
def get_pending_approvals():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    approvals, total = approval_service.get_pending(page, limit)
    meta = {"page": page, "limit": limit, "total": total}
    return success_response(data=approvals, meta=meta)

@approvals_bp.route('/<int:item_id>/approve', methods=['POST'])
@require_auth
@require_role(['admin', 'moderator'])
def approve_item(item_id):
    result = approval_service.approve(item_id, request.user.id)
    return success_response(data=result, message="Item approved")

@approvals_bp.route('/<int:item_id>/reject', methods=['POST'])
@require_auth
@require_role(['admin', 'moderator'])
def reject_item(item_id):
    reason = request.json.get('reason')
    result = approval_service.reject(item_id, request.user.id, reason)
    return success_response(data=result, message="Item rejected")

@approvals_bp.route('/<int:item_id>/request-changes', methods=['POST'])
@require_auth
@require_role(['admin', 'moderator'])
def request_changes(item_id):
    feedback = request.json.get('feedback')
    result = approval_service.request_changes(item_id, request.user.id, feedback)
    return success_response(data=result, message="Changes requested")
