"""Approval workflow API endpoints.

All routes require authentication and resources:approve permission.
Institution isolation is enforced via request.user (from JWT).
Routes are thin — all business logic lives in ApprovalService.
"""
from flask import Blueprint, request
from app.utils.response_utils import success_response, error_response
from app.services.approval_service import ApprovalService
from app.middleware.auth import require_auth
from app.permissions.rbac import require_permission

approvals_bp = Blueprint('approvals', __name__)
approval_service = ApprovalService()


@approvals_bp.route('/pending', methods=['GET'])
@require_auth
@require_permission('resources:approve')
def get_pending_approvals():
    """List resources pending review within the reviewer's institution."""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)

    # Institution from JWT — never from query params
    institution_id = str(request.user.institution_id)

    all_pending = approval_service.get_pending_queue(institution_id=institution_id)
    items = [r.to_dict() for r in all_pending]
    start = (page - 1) * limit
    paginated = items[start:start + limit]
    meta = {"page": page, "limit": limit, "total": len(items)}
    return success_response(data=paginated, meta=meta)


@approvals_bp.route('/<string:resource_id>/approve', methods=['POST'])
@require_auth
@require_permission('resources:approve')
def approve_resource(resource_id):
    """Approve a pending resource. Requires resources:approve permission.

    Reviewer identity and institution are derived from JWT.
    Self-approval is rejected. Cross-institution approval is rejected.
    """
    reviewer_id = str(request.user.id)
    reviewer_institution_id = str(request.user.institution_id)

    try:
        result = approval_service.approve_material(
            resource_id=resource_id,
            reviewer_id=reviewer_id,
            reviewer_institution_id=reviewer_institution_id
        )
        return success_response(data=result, message="Resource approved")
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            return error_response(code="NOT_FOUND", message=msg, status_code=404)
        return error_response(code="VALIDATION_ERROR", message=msg, status_code=400)


@approvals_bp.route('/<string:resource_id>/reject', methods=['POST'])
@require_auth
@require_permission('resources:approve')
def reject_resource(resource_id):
    """Reject a pending resource. Requires resources:approve permission.

    Expects JSON body: {"reason": "..."} (optional but recommended).
    """
    reviewer_id = str(request.user.id)
    reviewer_institution_id = str(request.user.institution_id)
    data = request.get_json(silent=True) or {}
    reason = data.get('reason', '')

    try:
        result = approval_service.reject_material(
            resource_id=resource_id,
            reviewer_id=reviewer_id,
            reviewer_institution_id=reviewer_institution_id,
            reason=reason
        )
        return success_response(data=result, message="Resource rejected")
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            return error_response(code="NOT_FOUND", message=msg, status_code=404)
        return error_response(code="VALIDATION_ERROR", message=msg, status_code=400)


@approvals_bp.route('/<string:resource_id>/request-changes', methods=['POST'])
@require_auth
@require_permission('resources:approve')
def request_changes(resource_id):
    """Request changes on a pending resource. Requires resources:approve permission.

    Expects JSON body: {"feedback": "..."}.
    """
    reviewer_id = str(request.user.id)
    reviewer_institution_id = str(request.user.institution_id)
    data = request.get_json(silent=True) or {}
    feedback = data.get('feedback', '')

    try:
        result = approval_service.request_changes(
            resource_id=resource_id,
            reviewer_id=reviewer_id,
            reviewer_institution_id=reviewer_institution_id,
            feedback=feedback
        )
        return success_response(data=result, message="Changes requested")
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            return error_response(code="NOT_FOUND", message=msg, status_code=404)
        return error_response(code="VALIDATION_ERROR", message=msg, status_code=400)


@approvals_bp.route('/<string:resource_id>/history', methods=['GET'])
@require_auth
@require_permission('resources:approve')
def get_approval_history(resource_id):
    """Get the audit trail for a resource's approval decisions."""
    history = approval_service.get_approval_history(resource_id)
    return success_response(data=history)
